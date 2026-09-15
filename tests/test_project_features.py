from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ProjectFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.old_cwd)
        self.env_patch = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")}, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_template_renders_text_and_copies_binary(self) -> None:
        from unlawful.config import ensure_layout, templates_dir
        from unlawful.project_templates import apply_template

        ensure_layout()
        template = templates_dir() / "python"
        (template / "pkg").mkdir()
        (template / "pkg" / "name.txt").write_text("{{project_name}}")
        (template / "logo.bin").write_bytes(b"\xff\x00")
        destination = self.root / "demo"
        destination.mkdir()
        self.assertEqual(apply_template("python", destination, {"project_name": "demo"}), 2)
        self.assertEqual((destination / "pkg" / "name.txt").read_text(), "demo")
        self.assertEqual((destination / "logo.bin").read_bytes(), b"\xff\x00")

    def test_python_no_venv_and_git(self) -> None:
        from unlawful.built_in_commands.py import main as py_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(py_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(py_command.main(["demo", "--no-venv", "--git"]), 0)
        self.assertFalse((Path("demo") / ".venv").exists())
        run.assert_called_once_with(["git", "init", "demo"], check=False)

    def test_python_uv_mode_uses_uv_venv(self) -> None:
        from unlawful.built_in_commands.py import main as py_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(py_command.shutil, "which", return_value="/bin/uv"), patch.object(
            py_command.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(py_command.main(["demo", "--uv"]), 0)
        run.assert_called_once_with(["/bin/uv", "venv", "demo/.venv"], check=False)

    def test_python_missing_uv_does_not_leave_partial_project(self) -> None:
        from unlawful.built_in_commands.py import main as py_command

        with patch.object(py_command.shutil, "which", return_value=None):
            self.assertEqual(py_command.main(["demo", "--uv"]), 1)
        self.assertFalse(Path("demo").exists())

    def test_python_user_template_overrides_default_file(self) -> None:
        from unlawful.built_in_commands.py import main as py_command
        from unlawful.config import ensure_layout, templates_dir

        ensure_layout()
        (templates_dir() / "python" / "main.py").write_text("print('{{project_name}} custom')\n")
        self.assertEqual(py_command.main(["demo", "--no-venv"]), 0)
        self.assertEqual(Path("demo/main.py").read_text(), "print('demo custom')\n")

    def test_rust_lib_without_git_uses_cargo_and_template(self) -> None:
        from unlawful.built_in_commands.rust import main as rust_command
        from unlawful.config import ensure_layout, templates_dir

        ensure_layout()
        (templates_dir() / "rust" / "README.md").write_text("# {{project_name}}\n")

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess:
            Path("amber").mkdir(exist_ok=True)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(rust_command.shutil, "which", return_value="/bin/cargo"), patch.object(
            rust_command.subprocess, "run", side_effect=run
        ) as cargo:
            self.assertEqual(rust_command.main(["amber", "--lib"]), 0)
        cargo.assert_called_once_with(["/bin/cargo", "new", "amber", "--lib", "--vcs", "none"], check=False)
        self.assertEqual(Path("amber/README.md").read_text(), "# amber\n")

    def test_rust_rejects_conflicting_project_kinds(self) -> None:
        from unlawful.built_in_commands.rust import main as rust_command

        self.assertEqual(rust_command.main(["amber", "--bin", "--lib"]), 2)

    def test_cpp_standard_and_git_are_configurable(self) -> None:
        from unlawful.built_in_commands.cpp import main as cpp_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(cpp_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(cpp_command.main(["engine", "--std", "23", "--git"]), 0)
        self.assertIn("CMAKE_CXX_STANDARD 23", Path("engine/CMakeLists.txt").read_text())
        run.assert_called_once_with(["git", "init", "engine"], check=False)


if __name__ == "__main__":
    unittest.main()
