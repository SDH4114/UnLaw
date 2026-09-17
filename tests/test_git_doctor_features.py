from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class GitDoctorFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env_patch = patch.dict(
            os.environ, {"XDG_CONFIG_HOME": str(Path(self.temp.name) / "config")}, clear=False
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_git_status_is_single_passthrough(self) -> None:
        from unlawful.built_in_commands.git import main as git_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(git_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(git_command.main(["status"]), 0)
        run.assert_called_once_with(["git", "status"], check=False)

    def test_git_commit_adds_changes_but_does_not_push(self) -> None:
        from unlawful.built_in_commands.git import main as git_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(git_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(git_command.main(["commit", "fix", "parser"]), 0)
        self.assertEqual(
            run.call_args_list,
            [call(["git", "add", "."], check=False), call(["git", "commit", "-m", "fix parser"], check=False)],
        )

    def test_git_default_always_pushes(self) -> None:
        from unlawful.built_in_commands.git import main as git_command
        from unlawful.config import ensure_layout, set_config_value

        ensure_layout()
        set_config_value("git.auto_push", False)
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(git_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(git_command.main(["message"]), 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(["git", "add", "."], check=False),
                call(["git", "commit", "-m", "message"], check=False),
                call(["git", "push"], check=False),
            ],
        )

    def test_git_sync_pulls_rebases_commits_and_pushes(self) -> None:
        from unlawful.built_in_commands.git import main as git_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(git_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(git_command.main(["sync", "daily"]), 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(["git", "pull", "--rebase"], check=False),
                call(["git", "add", "."], check=False),
                call(["git", "commit", "-m", "daily"], check=False),
                call(["git", "push"], check=False),
            ],
        )

    def test_doctor_json_is_machine_readable(self) -> None:
        from unlawful.system_commands import doctor

        output = StringIO()
        with patch("unlawful.system_commands._harness_permissions", return_value=(True, "ready")), redirect_stdout(
            output
        ):
            self.assertEqual(doctor(["--json"]), 0)
        records = json.loads(output.getvalue())
        names = {record["name"] for record in records}
        self.assertTrue({"Configuration", "Python", "Git", "Cargo", "CMake", "macOS Harness"} <= names)
        self.assertTrue(all({"name", "available", "required", "detail"} <= record.keys() for record in records))

    def test_doctor_verbose_includes_config_path(self) -> None:
        from unlawful.system_commands import doctor

        output = StringIO()
        with patch("unlawful.system_commands._harness_permissions", return_value=(False, "missing permission")), redirect_stdout(
            output
        ):
            self.assertEqual(doctor(["--verbose"]), 0)
        self.assertIn(str(Path(self.temp.name) / "config" / "unlaw" / "config.toml"), output.getvalue())

    def test_doctor_checks_configured_harness_executable(self) -> None:
        from unlawful.config import ensure_layout, set_config_value
        from unlawful.system_commands import doctor

        executable = Path(self.temp.name) / "custom-harness"
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
        ensure_layout()
        set_config_value("mac.executable", str(executable))
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(doctor(["--json"]), 0)
        records = json.loads(output.getvalue())
        permissions = next(record for record in records if record["name"] == "macOS permissions")
        self.assertTrue(permissions["available"])


if __name__ == "__main__":
    unittest.main()
