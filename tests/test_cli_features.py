from __future__ import annotations

import json
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


class CliFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config_home = Path(self.temp.name) / "config"
        self.env = {"XDG_CONFIG_HOME": str(self.config_home)}

    def _command(self, name: str, body: str) -> Path:
        script = self.config_home / "unlaw" / "commands" / name / "main.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(body)
        return script

    def test_first_help_bootstraps_user_directory(self) -> None:
        from unlawful.cli import main

        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(StringIO()):
            self.assertEqual(main([]), 0)
        root = self.config_home / "unlaw"
        self.assertTrue((root / "config.toml").is_file())
        self.assertTrue((root / "commands").is_dir())

    def test_alias_expands_tokens_and_appends_arguments(self) -> None:
        from unlawful.cli import main
        from unlawful.config import ensure_layout, set_config_value

        output_file = Path(self.temp.name) / "alias.txt"
        self._command(
            "capture",
            f"import pathlib, sys\npathlib.Path({str(output_file)!r}).write_text('|'.join(sys.argv[1:]))\n",
        )
        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            set_config_value("aliases.c", ["capture", "preset"])
            self.assertEqual(main(["c", "extra"]), 0)
        self.assertEqual(output_file.read_text(), "preset|extra")

    def test_alias_cycle_is_reported_without_traceback(self) -> None:
        from unlawful.cli import main
        from unlawful.config import ensure_layout, set_config_value

        error = StringIO()
        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            set_config_value("aliases.a", ["b"])
            set_config_value("aliases.b", ["a"])
            with redirect_stderr(error):
                code = main(["a"])
        self.assertEqual(code, 2)
        self.assertIn("Alias cycle", error.getvalue())

    def test_dry_run_does_not_execute_command(self) -> None:
        from unlawful.cli import main

        marker = Path(self.temp.name) / "ran"
        self._command("touch", f"import pathlib\npathlib.Path({str(marker)!r}).touch()\n")
        output = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(main(["--dry-run", "touch"]), 0)
        self.assertFalse(marker.exists())
        self.assertIn("DRY RUN", output.getvalue())

    def test_timeout_returns_124(self) -> None:
        from unlawful.runner import run_command

        self._command("slow", "import time\ntime.sleep(2)\n")
        with patch.dict(os.environ, self.env, clear=False), redirect_stderr(StringIO()):
            self.assertEqual(run_command("slow", [], timeout=0.01), 124)

    def test_unknown_command_suggests_close_match(self) -> None:
        from unlawful.cli import main

        error = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stderr(error):
            self.assertEqual(main(["gti"]), 2)
        self.assertIn("git", error.getvalue())

    def test_commands_json_contains_source_and_path(self) -> None:
        from unlawful.config import ensure_layout, set_config_value
        from unlawful.system_commands import list_commands

        self._command("mine", "print('mine')\n")
        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            set_config_value("aliases.m", ["mine", "preset"])
        output = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(list_commands(["--json"]), 0)
        records = json.loads(output.getvalue())
        mine = next(record for record in records if record["name"] == "mine")
        alias = next(record for record in records if record["name"] == "m")
        self.assertEqual(mine["source"], "config")
        self.assertTrue(mine["path"].endswith("commands/mine/main.py"))
        self.assertEqual(alias["source"], "alias")
        self.assertEqual(alias["expansion"], ["mine", "preset"])

    def test_which_reports_user_command(self) -> None:
        from unlawful.system_commands import which_command

        script = self._command("mine", "print('mine')\n")
        output = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(which_command(["mine"]), 0)
        self.assertIn(str(script), output.getvalue())
        self.assertIn("config", output.getvalue())

    def test_which_reports_alias_expansion(self) -> None:
        from unlawful.config import ensure_layout, set_config_value
        from unlawful.system_commands import which_command

        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            set_config_value("aliases.g", ["git", "status"])
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(which_command(["g"]), 0)
        self.assertIn("alias -> git status", output.getvalue())

    def test_config_set_and_get_through_cli(self) -> None:
        from unlawful.cli import main

        output = StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(main(["config", "set", "core.command_timeout", "12"]), 0)
            self.assertEqual(main(["config", "get", "core.command_timeout"]), 0)
        self.assertTrue(output.getvalue().rstrip().endswith("12"))

    def test_config_reset_requires_yes_and_creates_backup(self) -> None:
        from unlawful.cli import main

        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["config", "reset"]), 2)
            self.assertEqual(main(["config", "set", "core.verbose", "true"]), 0)
            self.assertEqual(main(["config", "reset", "--yes"]), 0)
        backups = list((self.config_home / "unlaw").glob("config.toml.backup-*"))
        self.assertEqual(len(backups), 1)

    def test_completion_outputs_zsh_function(self) -> None:
        from unlawful.system_commands import completion_command

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(completion_command(["zsh"]), 0)
        self.assertIn("#compdef ul unlaw", output.getvalue())
        self.assertIn("_unlaw", output.getvalue())
        self.assertIn("ul templates", output.getvalue())


if __name__ == "__main__":
    unittest.main()
