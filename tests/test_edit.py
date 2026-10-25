from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import ROOT, CoreTestCase  # noqa: E402


def ule_binary() -> Path:
    subprocess.run(["cargo", "build", "--quiet", "-p", "ule"], cwd=ROOT, check=True)
    return ROOT / "target" / "debug" / "ule"


class EditTests(CoreTestCase):
    def fake_editor(self) -> Path:
        """An editor that records its arguments instead of opening anything."""
        log = self.root / "editor.log"
        self.tool("fakeedit", f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {log}\n")
        return log

    def test_help_is_side_effect_free(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("edit", flag)
            self.assertIn("Usage: ul edit", result.stdout)
            self.assertIn("core.editor", result.stdout)

    def test_core_editor_opens_files(self) -> None:
        log = self.fake_editor()
        self.ok("config", "set", "core.editor", "fakeedit --wait")
        self.ok("edit", "a.txt", "src/main.rs:12")
        self.assertEqual(
            log.read_text().splitlines(), ["--wait", "a.txt", "src/main.rs:12"]
        )

    def test_config_edit_uses_the_editor_and_checks_the_result(self) -> None:
        log = self.fake_editor()
        self.ok("config", "set", "core.editor", "fakeedit")
        result = self.ok("config", "edit")
        self.assertEqual(log.read_text().strip(), str(self.unlaw / "config.toml"))
        self.assertIn("config.toml is valid", result.stdout)
        # A broken config is reported right after editing, and `ul edit` still works to fix it.
        (self.unlaw / "config.toml").write_text(
            '[core]\neditor = "fakeedit"\ncolor = "yes"\n'
        )
        result = self.ul("config", "edit")
        self.assertEqual(result.returncode, 1)
        self.assertIn("core.color", result.stderr)

    def test_auto_falls_back_to_visual_without_ule(self) -> None:
        log = self.fake_editor()
        env = {"VISUAL": "fakeedit -f"}
        result = self.ul_without_ule("edit", "x.md", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text().splitlines(), ["-f", "x.md"])
        result = self.ul_without_ule("doctor", "--verbose", env=env)
        self.assertIn("ule is not installed", result.stdout)

    def test_unknown_option(self) -> None:
        result = self.ul("edit", "--bogus")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option", result.stderr)


class UleBinaryTests(CoreTestCase):
    def ule(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ule_binary()), *args],
            env=self.env,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_help_version_and_config_path(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        help_text = self.ule("--help")
        self.assertEqual(help_text.returncode, 0)
        self.assertIn("Usage: ule", help_text.stdout)
        version = self.ule("--version").stdout.strip()
        self.assertEqual(version, f"ule {self.ok('--version').stdout.split()[1]}")
        self.assertEqual(
            self.ule("--config").stdout.strip(), str(self.unlaw / "ule.toml")
        )

    def test_health_reports_tools_and_config_errors(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        self.unlaw.mkdir(parents=True, exist_ok=True)
        (self.unlaw / "ule.toml").write_text('[editor]\ntab_width = "wide"\n')
        result = self.ule("--health")
        self.assertEqual(result.returncode, 0)
        self.assertIn("rust", result.stdout)
        self.assertIn("tab_width", result.stdout)
        self.assertIn("python", self.ule("--health", "python").stdout)

    def test_refuses_without_a_terminal_and_rejects_unknown_options(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        self.assertEqual(self.ule("file.txt").returncode, 1)
        result = self.ule("--nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option", result.stderr)


if __name__ == "__main__":
    unittest.main()
