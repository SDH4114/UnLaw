from __future__ import annotations

import os
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


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config_home = Path(self.temp.name) / "config"
        self.env = {"XDG_CONFIG_HOME": str(self.config_home)}

    def _command(self, name: str, body: str) -> Path:
        command = self.config_home / "unlaw" / "commands" / name
        command.mkdir(parents=True)
        script = command / "main.py"
        script.write_text(body, encoding="utf-8")
        return script

    def test_user_command_receives_arguments_and_exit_code(self) -> None:
        from unlawful.cli import main

        output = Path(self.temp.name) / "args.txt"
        self._command(
            "echoargs",
            "import pathlib, sys\n"
            f"pathlib.Path({str(output)!r}).write_text('|'.join(sys.argv[1:]))\n"
            "raise SystemExit(7)\n",
        )
        with patch.dict(os.environ, self.env, clear=False):
            code = main(["echoargs", "hello", "world"])
        self.assertEqual(code, 7)
        self.assertEqual(output.read_text(), "hello|world")

    def test_user_command_overrides_builtin(self) -> None:
        from unlawful.runner import resolve_command

        script = self._command("app", "print('custom')\n")
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(resolve_command("app"), script)

    def test_help_is_shown_without_command(self) -> None:
        from unlawful.cli import main

        output = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            code = main([])
        self.assertEqual(code, 0)
        self.assertIn("Usage: ul", output.getvalue())

    def test_unknown_command_is_an_error(self) -> None:
        from unlawful.cli import main

        error = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stderr(error):
            code = main(["missing-command"])
        self.assertEqual(code, 2)
        self.assertIn("Unknown command", error.getvalue())

    def test_cli_reports_version_2_1_3(self) -> None:
        from unlawful.cli import main

        output = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(main(["--version"]), 0)
        self.assertEqual(output.getvalue(), "Unlaw 2.1.3\n")

    def test_cli_routes_templates_and_list_as_system_commands(self) -> None:
        from unlawful.cli import main

        with patch.dict(os.environ, self.env, clear=False), patch(
            "unlawful.cli.SYSTEM_COMMANDS",
            {"templates": lambda args: 7, "list": lambda args: 8},
        ):
            self.assertEqual(main(["templates"]), 7)
            self.assertEqual(main(["list"]), 8)

    def test_direct_template_invocation_requires_shell_integration(self) -> None:
        from unlawful.cli import main
        from unlawful.workspace_templates import create_workspace_template

        project = Path(self.temp.name) / "HearMe"
        project.mkdir()
        error = StringIO()
        with patch.dict(os.environ, self.env, clear=False):
            create_workspace_template("hearme", project, "zed", False)
            with redirect_stderr(error):
                self.assertEqual(main(["hearme"]), 1)
        self.assertIn("doctor --fix", error.getvalue())

    def test_hidden_template_helpers_resolve_and_launch(self) -> None:
        from unlawful.cli import main
        from unlawful.workspace_templates import create_workspace_template

        project = Path(self.temp.name) / "HearMe"
        project.mkdir()
        with patch.dict(os.environ, self.env, clear=False):
            create_workspace_template("hearme", project, "zed", False)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["_template-path", "hearme"]), 0)
            self.assertEqual(output.getvalue().strip(), str(project.resolve()))
            with patch("unlawful.cli.launch_workspace_template", return_value=6) as launch:
                self.assertEqual(main(["_template-launch", "hearme"]), 6)
        launch.assert_called_once()

    def test_hidden_template_helpers_reject_extra_arguments(self) -> None:
        from unlawful.cli import main

        with patch.dict(os.environ, self.env, clear=False), redirect_stderr(StringIO()):
            self.assertEqual(main(["_template-path", "one", "two"]), 2)
            self.assertEqual(main(["_template-launch", "one", "two"]), 2)


if __name__ == "__main__":
    unittest.main()
