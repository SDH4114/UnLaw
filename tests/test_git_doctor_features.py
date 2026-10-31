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


def staged_run(command, check=False):
    """`git diff --cached --quiet` exits 1: there is something to commit."""
    return subprocess.CompletedProcess(command, 1 if command[:2] == ["git", "diff"] else 0)


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

        with patch.object(git_command.subprocess, "run", side_effect=staged_run) as run:
            self.assertEqual(git_command.main(["commit", "fix", "parser"]), 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(["git", "add", "."], check=False),
                call(["git", "diff", "--cached", "--quiet"], check=False),
                call(["git", "commit", "-m", "fix parser"], check=False),
            ],
        )

    def test_git_default_always_pushes(self) -> None:
        from unlawful.built_in_commands.git import main as git_command
        from unlawful.config import ensure_layout, set_config_value

        ensure_layout()
        set_config_value("git.auto_push", False)
        with patch.object(git_command.subprocess, "run", side_effect=staged_run) as run:
            self.assertEqual(git_command.main(["message"]), 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(["git", "add", "."], check=False),
                call(["git", "diff", "--cached", "--quiet"], check=False),
                call(["git", "commit", "-m", "message"], check=False),
                call(["git", "push"], check=False),
            ],
        )

    def test_git_sync_pulls_rebases_commits_and_pushes(self) -> None:
        from unlawful.built_in_commands.git import main as git_command

        with patch.object(git_command.subprocess, "run", side_effect=staged_run) as run:
            self.assertEqual(git_command.main(["sync", "daily"]), 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(["git", "pull", "--rebase"], check=False),
                call(["git", "add", "."], check=False),
                call(["git", "diff", "--cached", "--quiet"], check=False),
                call(["git", "commit", "-m", "daily"], check=False),
                call(["git", "push"], check=False),
            ],
        )


if __name__ == "__main__":
    unittest.main()
