from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase, binary  # noqa: E402

REPOSITORY = "https://github.com/SDH4114/UnLaw.git"


class UpdateTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"

    def fake_cargo(self, *, exit_code: int = 0, version: str = "9.9.9") -> Path:
        """Logs argv and UNLAW_PYTHON, then installs a fake `ul` into --root/bin."""
        log = self.root / "cargo.log"
        self.tool(
            "cargo",
            f"#!{sys.executable}\nimport os, pathlib, sys\n"
            f"pathlib.Path({str(log)!r}).write_text('\\n'.join([os.environ.get('UNLAW_PYTHON', ''), *sys.argv[1:]]))\n"
            f"if {exit_code}: raise SystemExit({exit_code})\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1]) / 'bin'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            f"(root / 'ul').write_text('#!/bin/sh\\necho Unlaw {version}\\n')\n"
            "(root / 'ul').chmod(0o755)\n",
        )
        return log

    def fake_curl(self, body: str, *, exit_code: int = 0) -> Path:
        log = self.root / "curl.log"
        self.tool(
            "curl",
            f"#!{sys.executable}\nimport pathlib, sys\n"
            f"pathlib.Path({str(log)!r}).write_text('\\n'.join(sys.argv[1:]))\n"
            f"sys.stdout.write({body!r})\n"
            f"if {exit_code}: sys.stderr.write('404'); raise SystemExit({exit_code})\n",
        )
        return log

    def test_help_and_usage(self) -> None:
        result = self.ok("update", "--help")
        self.assertIn("Usage: ul update", result.stdout)
        self.assertIn("Example", result.stdout)
        for args in (["--branch"], ["--tag", "--check"], ["--branch", "a", "--tag", "b"], ["now"]):
            with self.subTest(args=args):
                result = self.ul("update", *args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage: ul update", result.stderr)

    def test_update_reinstalls_from_github_into_local_bin(self) -> None:
        log = self.fake_cargo()
        result = self.ok("update")
        self.assertEqual(
            log.read_text().splitlines(),
            [sys.executable, "install", "--locked", "--force", "--git", REPOSITORY, "--root", str(self.home / ".local"), "unlaw"],
        )
        self.assertIn("Updated to Unlaw 9.9.9", result.stdout)
        self.assertIn("edited ones are kept", result.stdout)

    def test_branch_tag_and_fork_are_passed_to_cargo(self) -> None:
        log = self.fake_cargo()
        self.ok("update", "--branch", "dev")
        self.assertIn("--branch\ndev\n--root", log.read_text())
        self.ok("update", "--tag", "v3.0.0", env={"UNLAW_UPDATE_REPOSITORY": "https://github.com/me/fork.git"})
        text = log.read_text()
        self.assertIn("--git\nhttps://github.com/me/fork.git\n--tag\nv3.0.0", text)

    def test_binary_in_a_bin_directory_updates_in_place(self) -> None:
        prefix = self.root / "prefix"
        (prefix / "bin").mkdir(parents=True)
        installed = prefix / "bin" / "ul"
        shutil.copy2(binary(), installed)
        log = self.fake_cargo()
        result = self.ul_with(installed, "update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"--root\n{prefix}\n", log.read_text())

    def ul_with(self, executable: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(executable), *args], env=self.env, capture_output=True, text=True, timeout=60)

    def test_failed_cargo_reports_and_keeps_exit_code(self) -> None:
        self.fake_cargo(exit_code=101)
        result = self.ul("update")
        self.assertEqual(result.returncode, 101)
        self.assertIn("was not changed", result.stderr)

    def test_missing_cargo_explains_how_to_install_rust(self) -> None:
        result = self.ul("update")
        self.assertEqual(result.returncode, 1)
        self.assertIn("rustup", result.stderr)

    def test_rustup_cargo_outside_path_is_found(self) -> None:
        cargo_bin = self.home / ".cargo" / "bin"
        cargo_bin.mkdir(parents=True)
        self.fake_cargo()
        shutil.move(self.bin / "cargo", cargo_bin / "cargo")
        result = self.ok("update")
        self.assertIn(str(cargo_bin / "cargo"), result.stdout)

    def test_check_compares_versions_without_installing(self) -> None:
        cargo_log = self.fake_cargo()
        curl_log = self.fake_curl('[package]\nname = "unlaw"\nversion = "9.0.0"\n')
        result = self.ok("update", "--check")
        self.assertEqual(result.stdout.splitlines()[:2], ["Installed: 2.1.3", "Latest:    9.0.0 (main)"])
        self.assertIn("Update available", result.stdout)
        self.assertIn("https://raw.githubusercontent.com/SDH4114/UnLaw/main/Cargo.toml", curl_log.read_text())
        self.assertFalse(cargo_log.exists())
        self.fake_curl('[package]\nversion = "2.1.3"\n')
        self.assertIn("Same version number", self.ok("update", "--check").stdout)
        self.fake_curl('[package]\nversion = "1.0.0"\n')
        self.assertIn("newer than the published", self.ok("update", "--check", "--tag", "v1").stdout)
        self.assertIn("/v1/Cargo.toml", curl_log.read_text())

    def test_check_failures(self) -> None:
        self.fake_curl("", exit_code=22)
        result = self.ul("update", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not fetch", result.stderr)
        self.fake_curl("not toml at all [")
        self.assertIn("has no package version", self.ul("update", "--check").stderr)
        result = self.ul("update", "--check", env={"UNLAW_UPDATE_REPOSITORY": "https://gitlab.com/me/fork"})
        self.assertEqual(result.returncode, 2)
        (self.bin / "curl").unlink()
        result = self.ul("update", "--check", env={"PATH": str(self.bin)})
        self.assertIn("Could not run curl", result.stderr)

    def test_update_is_a_system_command(self) -> None:
        self.assertEqual(self.ok("which", "update").stdout, "update: system\n")
        self.assertIn("--check:Compare with GitHub", self.ok("_complete", "2", "update").stdout)
        self.assertEqual(self.ul("create", "command", "update").returncode, 2)


if __name__ == "__main__":
    unittest.main()
