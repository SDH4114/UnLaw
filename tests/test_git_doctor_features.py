from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tests import fake_git_hosts


class GitDoctorFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env_patch = patch.dict(
            os.environ, {"XDG_CONFIG_HOME": str(Path(self.temp.name) / "config")}, clear=False
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_git_status_was_removed_and_runs_nothing(self) -> None:
        fake_git_hosts.install()
        from unlawful.built_in_commands.git import main as git_command

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(git_command.subprocess, "run", return_value=completed) as run:
            self.assertEqual(git_command.main(["status"]), 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
