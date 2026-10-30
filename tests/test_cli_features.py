from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase  # noqa: E402


class CliFeatureTests(CoreTestCase):
    def test_first_help_is_read_only_and_init_bootstraps(self) -> None:
        self.ok()
        self.assertFalse(self.unlaw.exists())
        self.ok("init")
        self.assertTrue((self.unlaw / "config.toml").is_file())
        self.assertTrue((self.unlaw / "commands").is_dir())

    def test_alias_expands_tokens_and_appends_arguments(self) -> None:
        output_file = self.root / "alias.txt"
        self.command(
            "capture",
            f"import pathlib, sys\npathlib.Path({str(output_file)!r}).write_text('|'.join(sys.argv[1:]))\n",
        )
        self.ok("config", "set", "aliases.c", '["capture", "preset"]')
        self.ok("c", "extra")
        self.assertEqual(output_file.read_text(), "preset|extra")

    def test_alias_cycle_is_reported_without_traceback(self) -> None:
        self.ok("config", "set", "aliases.a", '["b"]')
        self.ok("config", "set", "aliases.b", '["a"]')
        result = self.ul("a")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Alias cycle: a -> b -> a", result.stderr)

    def test_dry_run_does_not_execute_command(self) -> None:
        marker = self.root / "ran"
        script = self.command("touch", f"import pathlib\npathlib.Path({str(marker)!r}).touch()\n")
        result = self.ok("--dry-run", "touch", "a b")
        self.assertFalse(marker.exists())
        self.assertEqual(result.stdout, f"DRY RUN: {sys.executable} {script} 'a b'\n")

    def test_timeout_returns_124(self) -> None:
        self.command("slow", "import time\ntime.sleep(5)\n")
        self.ok("config", "set", "core.command_timeout", "1")
        result = self.ul("slow")
        self.assertEqual(result.returncode, 124)
        self.assertIn("timed out", result.stderr)

    def test_verbose_reports_invocation_and_timing(self) -> None:
        self.command("quick", "print('done')\n")
        result = self.ok("--verbose", "quick")
        self.assertEqual(result.stdout, "done\n")
        self.assertIn("unlaw: running quick (config):", result.stderr)
        self.assertIn("unlaw: finished in", result.stderr)

    def test_unknown_command_suggests_close_match(self) -> None:
        result = self.ul("gti")
        self.assertEqual(result.returncode, 2)
        self.assertIn("git", result.stderr)

    def test_commands_json_contains_source_and_path(self) -> None:
        self.command("mine", "print('mine')\n")
        self.ok("config", "set", "aliases.m", '["mine", "preset"]')
        records = json.loads(self.ok("commands", "--json").stdout)
        mine = next(record for record in records if record["name"] == "mine")
        alias = next(record for record in records if record["name"] == "m")
        system = next(record for record in records if record["name"] == "doctor")
        self.assertEqual(mine["source"], "config")
        self.assertTrue(mine["path"].endswith("commands/mine/main.py"))
        self.assertEqual(alias["source"], "alias")
        self.assertEqual(alias["expansion"], ["mine", "preset"])
        self.assertEqual((system["source"], system["path"]), ("system", None))

    def test_which_reports_user_command(self) -> None:
        script = self.command("mine", "print('mine')\n")
        self.assertEqual(self.ok("which", "mine").stdout, f"mine: config {script}\n")
        self.assertEqual(self.ok("which", "doctor").stdout, "doctor: system\n")
        self.assertEqual(self.ul("which", "nope").returncode, 1)

    def test_which_reports_alias_expansion(self) -> None:
        self.ok("config", "set", "aliases.g", '["git", "status"]')
        self.assertIn("alias -> git status", self.ok("which", "g").stdout)

    def test_config_set_and_get_through_cli(self) -> None:
        self.ok("config", "set", "core.command_timeout", "12")
        self.assertEqual(self.ok("config", "get", "core.command_timeout").stdout, "12\n")
        self.ok("config", "set", "apps.editor", "Visual", "Studio", "Code")
        self.assertEqual(self.ok("config", "get", "apps.editor").stdout, "Visual Studio Code\n")
        self.assertEqual(self.ok("config", "get", "apps.spotify_autoplay_delay").stdout, "2.0\n")
        self.assertEqual(self.ul("config", "get", "core.nope").returncode, 2)

    def test_config_set_preserves_comments_and_rejects_invalid_values(self) -> None:
        self.ok("init")
        config = self.unlaw / "config.toml"
        config.write_text("# mine\n[core]\nverbose = false # quiet\n\n[custom]\nanswer = 42\n")
        self.ok("config", "set", "core.command_timeout", "15")
        text = config.read_text()
        self.assertTrue(text.startswith("# mine\n[core]\nverbose = false # quiet\ncommand_timeout = 15\n"), text)
        self.assertIn("answer = 42", text)
        result = self.ul("config", "set", "games.difficulty", "brutal")
        self.assertEqual(result.returncode, 2)
        self.assertIn("games.difficulty", result.stderr)
        self.assertEqual(config.read_text(), text)
        self.assertEqual(self.ul("config", "set", "core.color.deep", "1").returncode, 2)

    def test_config_check_reports_each_error(self) -> None:
        self.ok("init")
        (self.unlaw / "config.toml").write_text('[core]\ncommand_timeout = "forever"\n[games]\ndifficulty = "x"\n')
        result = self.ul("config", "check")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            result.stderr.splitlines(),
            ["Invalid core.command_timeout: expected int", "Invalid games.difficulty: expected one of easy, hard, normal"],
        )

    def test_config_reset_requires_yes_and_creates_backup(self) -> None:
        self.assertEqual(self.ul("config", "reset").returncode, 2)
        self.ok("config", "set", "core.verbose", "true")
        self.ok("config", "reset", "--yes")
        backups = list(self.unlaw.glob("config.toml.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("verbose = true", backups[0].read_text())
        self.assertEqual(self.ok("config", "get", "core.verbose").stdout, "false\n")

    def test_completion_outputs_zsh_function(self) -> None:
        output = self.ok("completion", "zsh").stdout
        self.assertIn("#compdef ul unlaw", output)
        self.assertIn("_unlaw", output)
        self.assertIn("command ul _complete", output)


if __name__ == "__main__":
    unittest.main()
