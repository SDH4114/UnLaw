from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class InTemporaryDirectory(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous_cwd = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, self.previous_cwd)
        self.env_patch = patch.dict(
            os.environ, {"XDG_CONFIG_HOME": str(Path(self.temp.name) / "config")}, clear=False
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)


class AppCommandTests(unittest.TestCase):
    def test_app_uses_macos_open(self) -> None:
        from unlawful.built_in_commands.app import main as app

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(app.subprocess, "run", return_value=completed) as run:
            self.assertEqual(app.main(["Zed"]), 0)
        run.assert_called_once_with(["open", "-a", "Zed"], check=False)


class GitCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env_patch = patch.dict(
            os.environ, {"XDG_CONFIG_HOME": str(Path(self.temp.name) / "config")}, clear=False
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_git_runs_add_commit_with_message_and_push(self) -> None:
        from unlawful.built_in_commands.git import main as git_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(git_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(git_command.main(["fix", "parser"]), 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(["git", "add", "."], check=False),
                call(["git", "commit", "-m", "fix parser"], check=False),
                call(["git", "push"], check=False),
            ],
        )

    def test_git_stops_after_failed_step(self) -> None:
        from unlawful.built_in_commands.git import main as git_command

        failed = subprocess.CompletedProcess([], 3)
        with patch.object(git_command.subprocess, "run", return_value=failed) as run:
            self.assertEqual(git_command.main([]), 3)
        run.assert_called_once_with(["git", "add", "."], check=False)


class PythonCommandTests(InTemporaryDirectory):
    def test_python_creates_project_and_virtual_environment(self) -> None:
        from unlawful.built_in_commands.py import main as py_command

        with patch.object(py_command.venv.EnvBuilder, "create") as create:
            self.assertEqual(py_command.main(["test", "--venv"]), 0)
        project = Path("test")
        self.assertTrue((project / "main.py").is_file())
        self.assertTrue((project / "pyproject.toml").is_file())
        self.assertIn(".venv/", (project / ".gitignore").read_text())
        create.assert_called_once_with(project / ".venv")

    def test_python_refuses_existing_destination(self) -> None:
        from unlawful.built_in_commands.py import main as py_command

        Path("test").mkdir()
        self.assertEqual(py_command.main(["test"]), 1)


class RustCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env_patch = patch.dict(
            os.environ, {"XDG_CONFIG_HOME": str(Path(self.temp.name) / "config")}, clear=False
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_rust_delegates_to_cargo(self) -> None:
        from unlawful.built_in_commands.rust import main as rust_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(rust_command.shutil, "which", return_value="/bin/cargo"), patch.object(
            rust_command.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(rust_command.main(["amber"]), 0)
        run.assert_called_once_with(
            ["/bin/cargo", "new", "amber", "--bin", "--vcs", "none"], check=False
        )


class CppCommandTests(InTemporaryDirectory):
    def test_cpp_creates_cmake_project(self) -> None:
        from unlawful.built_in_commands.cpp import main as cpp_command

        self.assertEqual(cpp_command.main(["engine"]), 0)
        project = Path("engine")
        self.assertIn("int main()", (project / "src" / "main.cpp").read_text())
        self.assertIn("add_executable(engine", (project / "CMakeLists.txt").read_text())


class HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env_patch = patch.dict(
            os.environ, {"XDG_CONFIG_HOME": str(Path(self.temp.name) / "config")}, clear=False
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_harness_key_sends_bounded_python_program(self) -> None:
        from unlawful import harness

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(harness.shutil, "which", return_value="/bin/macos-harness"), patch.object(
            harness.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(harness.key("Spotify", "cmd+k"), 0)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["/bin/macos-harness"])
        self.assertIn('mac.key("cmd+k", app="Spotify")', kwargs["input"])
        self.assertTrue(kwargs["text"])

    def test_harness_uses_configured_executable_and_timeout(self) -> None:
        from unlawful import harness
        from unlawful.config import ensure_layout, set_config_value

        ensure_layout()
        set_config_value("mac.executable", "/custom/harness")
        set_config_value("mac.timeout", 7)
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(harness.shutil, "which", return_value="/custom/harness"), patch.object(
            harness.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(harness.type_text("Telegram", "hello"), 0)
        self.assertEqual(run.call_args.args[0], ["/custom/harness"])
        self.assertEqual(run.call_args.kwargs["timeout"], 7)

    def test_mac_command_routes_click(self) -> None:
        from unlawful.built_in_commands.mac import main as mac_command

        with patch.object(mac_command.harness, "click", return_value=4) as click:
            self.assertEqual(mac_command.main(["click", "Spotify", "500", "300"]), 4)
        click.assert_called_once_with("Spotify", 500.0, 300.0)


if __name__ == "__main__":
    unittest.main()
