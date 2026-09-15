from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class SystemCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = {"XDG_CONFIG_HOME": str(Path(self.temp.name) / "config")}

    def test_commands_lists_system_builtin_and_user_commands_sorted(self) -> None:
        from unlawful.system_commands import list_commands

        user = Path(self.env["XDG_CONFIG_HOME"]) / "unlaw" / "commands" / "zebra"
        user.mkdir(parents=True)
        (user / "main.py").write_text("print('zebra')\n")
        output = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(list_commands(), 0)
        names = output.getvalue().splitlines()
        self.assertEqual(names, sorted(names))
        self.assertTrue({"commands", "create", "doctor", "zebra"} <= set(names))

    def test_non_system_commands_resolve_only_from_config_commands_folder(self) -> None:
        from unlawful.config import ensure_layout
        from unlawful.runner import discover_commands

        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            commands = discover_commands()
        self.assertIn("git", commands)
        self.assertTrue(commands["git"].is_relative_to(Path(self.env["XDG_CONFIG_HOME"]) / "unlaw" / "commands"))
        self.assertNotIn("built_in_commands", str(commands["git"]))

    def test_create_command_writes_working_template(self) -> None:
        from unlawful.system_commands import create_command

        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(create_command(["command", "music"]), 0)
        script = (
            Path(self.env["XDG_CONFIG_HOME"])
            / "unlaw"
            / "commands"
            / "music"
            / "main.py"
        )
        self.assertTrue(script.is_file())
        self.assertIn("def main", script.read_text())

    def test_create_command_rejects_unsafe_name(self) -> None:
        from unlawful.system_commands import create_command

        error = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stderr(error):
            code = create_command(["command", "../escape"])
        self.assertEqual(code, 2)
        self.assertFalse((Path(self.temp.name) / "escape").exists())

    def test_create_command_refuses_to_overwrite(self) -> None:
        from unlawful.system_commands import create_command

        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(create_command(["command", "music"]), 0)
            script = (
                Path(self.env["XDG_CONFIG_HOME"])
                / "unlaw"
                / "commands"
                / "music"
                / "main.py"
            )
            script.write_text("sentinel\n")
            self.assertEqual(create_command(["command", "music"]), 1)
        self.assertEqual(script.read_text(), "sentinel\n")

    def test_create_command_prefers_user_template(self) -> None:
        from unlawful.system_commands import create_command

        template = (
            Path(self.env["XDG_CONFIG_HOME"])
            / "unlaw"
            / "templates"
            / "commands"
            / "main.py"
        )
        template.parent.mkdir(parents=True)
        template.write_text("print('custom template')\n")
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(create_command(["command", "custom"]), 0)
        created = template.parents[2] / "commands" / "custom" / "main.py"
        self.assertEqual(created.read_text(), "print('custom template')\n")

    def test_cli_routes_system_commands_without_subprocess(self) -> None:
        from unlawful.cli import main

        with patch.dict(os.environ, self.env, clear=False), patch(
            "unlawful.cli.SYSTEM_COMMANDS", {"doctor": lambda args: 9}
        ):
            self.assertEqual(main(["doctor"]), 9)

    def test_doctor_distinguishes_present_and_missing_tools(self) -> None:
        from unlawful.system_commands import doctor

        output = StringIO()

        def which(name: str) -> str | None:
            return f"/bin/{name}" if name in {"python3", "git", "macos-harness"} else None

        with patch.dict(os.environ, self.env, clear=False), patch(
            "unlawful.system_commands.shutil.which", side_effect=which
        ), patch(
            "unlawful.system_commands._harness_permissions", return_value=(False, "permission check failed")
        ), redirect_stdout(output):
            code = doctor([])
        self.assertEqual(code, 0)
        report = output.getvalue()
        self.assertIn("Python", report)
        self.assertIn("✓", report)
        self.assertIn("uv", report)
        self.assertIn("○", report)
        self.assertIn("macOS permissions", report)

    def test_harness_permission_check_handles_timeout(self) -> None:
        from unlawful.system_commands import _harness_permissions

        with patch("unlawful.system_commands.shutil.which", return_value="/bin/macos-harness"), patch(
            "unlawful.system_commands.subprocess.run",
            side_effect=subprocess.TimeoutExpired("macos-harness", 10),
        ):
            available, detail = _harness_permissions()
        self.assertFalse(available)
        self.assertIn("timed out", detail)


if __name__ == "__main__":
    unittest.main()
