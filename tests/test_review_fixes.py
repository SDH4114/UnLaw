"""Regression tests for shell file safety, --dry-run, config set types, remove and templates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase


class ZshrcSafetyTests(CoreTestCase):
    def test_doctor_fix_never_overwrites_a_zshrc_it_cannot_read(self) -> None:
        self.ok("init")
        zshrc = self.home / ".zshrc"
        original = b"export CAF\xc9=1\nalias x=y\n"
        zshrc.write_bytes(original)
        result = self.ul("doctor", "--fix", env={"PATH": str(self.bin)})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(zshrc.read_bytes(), original)

    def test_doctor_fix_writes_through_a_symlinked_zshrc(self) -> None:
        self.ok("init")
        real = self.root / "dotfiles" / "zshrc"
        real.parent.mkdir()
        real.write_text("export A=1\n", encoding="utf-8")
        real.chmod(0o600)
        link = self.home / ".zshrc"
        link.symlink_to(real)
        self.ul("doctor", "--fix", env={"PATH": str(self.bin)})
        self.assertTrue(link.is_symlink())
        self.assertIn("Unlaw shell integration", real.read_text(encoding="utf-8"))
        self.assertEqual(real.stat().st_mode & 0o777, 0o600)


class DryRunTests(CoreTestCase):
    def test_dry_run_does_not_run_system_commands(self) -> None:
        self.ok("init")
        result = self.ok("--dry-run", "config", "set", "core.verbose", "true")
        self.assertIn("DRY RUN: ul config set core.verbose true", result.stdout)
        self.assertEqual(
            self.ok("config", "get", "core.verbose").stdout.strip(), "false"
        )
        result = self.ok("--dry-run", "remove", "--yes")
        self.assertIn("DRY RUN: ul remove --yes", result.stdout)
        self.assertTrue(self.unlaw.is_dir())

    def test_dry_run_does_not_run_builtin_commands(self) -> None:
        self.ok("init")
        result = self.ok("--dry-run", "zip", "does-not-exist")
        self.assertIn("DRY RUN: ul zip does-not-exist", result.stdout)

    def test_dry_run_still_covers_user_commands(self) -> None:
        self.command("hello", "print('ran')\n")
        result = self.ok("--dry-run", "hello")
        self.assertIn("DRY RUN", result.stdout)
        self.assertNotIn("ran", result.stdout)


class ConfigSetTests(CoreTestCase):
    def test_numeric_text_for_a_string_key_is_stored_as_a_string(self) -> None:
        self.ok("init")
        self.ok("config", "set", "telegram.chat_id", "123456789")
        self.assertEqual(
            self.ok("config", "get", "telegram.chat_id").stdout.strip(), "123456789"
        )
        self.assertIn(
            'chat_id = "123456789"',
            (self.unlaw / "config.toml").read_text(encoding="utf-8"),
        )


class RemoveKeychainTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.ok("init")
        self.security = self.recording_tool("security")
        self.recording_tool("launchctl")
        self.recording_tool("cargo")

    def deleted_services(self) -> list[str]:
        return [
            call[call.index("-s") + 1]
            for call in self.calls(self.security)
            if call[0] == "delete-generic-password"
        ]

    def test_the_token_is_removed_even_when_config_toml_is_invalid(self) -> None:
        (self.unlaw / "config.toml").write_text(
            '[telegram]\nkeychain_service = "my.service"\n[core]\ncommand_timeout = "x"\n'
        )
        self.assertNotEqual(self.ul("config", "check").returncode, 0)
        self.ok("remove", "--yes")
        self.assertEqual(self.deleted_services(), ["my.service"])

    def test_the_default_service_is_used_when_config_toml_is_unreadable(self) -> None:
        (self.unlaw / "config.toml").write_text("this is [not toml\n")
        self.ok("remove", "--yes")
        self.assertEqual(self.deleted_services(), ["unlaw.telegram"])


class TemplateDiscoveryTests(CoreTestCase):
    def test_one_invalid_template_does_not_break_unknown_command_lookup(self) -> None:
        self.ok("init")
        directory = self.unlaw / "templates" / "projects"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "broken.toml").write_text("path = \n")
        result = self.ul("nosuchcommand")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown command: nosuchcommand", result.stderr)
        self.assertIn("broken", result.stderr)  # a warning names the skipped template


if __name__ == "__main__":
    unittest.main()
