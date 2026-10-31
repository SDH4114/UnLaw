"""`ul reinstall`, `ul remove` and `ul remove <command>`, with fake cargo, launchctl and security."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from ulbin import CoreTestCase, binary  # noqa: E402
from unlawful.command_sources import command_source  # noqa: E402

BLOCK = '# >>> Unlaw shell integration >>>\neval "$(command ul _shell-init zsh)"\n# <<< Unlaw shell integration <<<\n'


class RemoveTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Only fakes: the real cargo, launchctl and Keychain are never reached.
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.env.pop("CARGO_TARGET_DIR", None)
        self.launchctl = self.recording_tool("launchctl")
        self.cargo = self.recording_tool("cargo")
        self.ok("init")

    def features(self) -> str:
        return self.ok("config", "get", "core.features").stdout.strip()

    def test_a_command_folder_is_deleted_after_confirmation(self) -> None:
        self.command("hello", "print('hi')\n")
        (self.unlaw / "commands" / "hello" / "help.txt").write_text("Say hi\n")
        result = self.ul("remove", "hello", input="n\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Cancelled", result.stdout)
        self.assertTrue((self.unlaw / "commands" / "hello").is_dir())
        self.assertEqual(self.ul("remove", "hello").returncode, 1, "no answer means no")
        result = self.ok("remove", "hello", input="y\n")
        self.assertIn("Removed hello", result.stdout)
        self.assertFalse((self.unlaw / "commands" / "hello").exists())

    def test_a_default_command_leaves_core_features_and_is_not_seeded_again(self) -> None:
        self.assertTrue((self.unlaw / "commands" / "todo").is_dir())
        result = self.ok("remove", "todo", "--yes")
        self.assertIn("ul features add todo", result.stdout)
        self.ok("init")
        self.assertFalse((self.unlaw / "commands" / "todo").exists())
        self.assertNotIn("todo", self.features())
        self.assertIn("yt", self.features())

    def test_a_symlinked_command_loses_only_the_link(self) -> None:
        target = self.root / "mine"
        target.mkdir()
        (target / "main.py").write_text("print(1)\n")
        (self.unlaw / "commands" / "mine").symlink_to(target)
        self.ok("remove", "mine", "-y")
        self.assertFalse((self.unlaw / "commands" / "mine").is_symlink())
        self.assertTrue((target / "main.py").is_file())

    def test_what_cannot_be_removed_is_refused_before_anything_is_deleted(self) -> None:
        self.command("hello", "print('hi')\n")
        cases = {"config": "system command", "zip": "core", "game": "ul features remove game", "nope": "No command named nope", "../x": "Invalid"}
        for name, message in cases.items():
            with self.subTest(name=name):
                result = self.ul("remove", "hello", name, "--yes")
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
        self.assertTrue((self.unlaw / "commands" / "hello").is_dir())

    def install_fakes(self) -> None:
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        for name in ("ul", "unlaw", "ula", "ule"):
            (bin_dir / name).write_text("#!/bin/sh\n")
        (self.home / ".zshrc").write_text(f"export A=1\n\n{BLOCK}alias b=c\n")
        cache = self.home / "Library" / "Caches" / "unlaw" / "cargo-target"
        cache.mkdir(parents=True)
        agents = self.home / "Library" / "LaunchAgents"
        agents.mkdir(parents=True)
        (agents / "com.unlaw.agent.plist").write_text("<plist/>")

    def test_remove_asks_and_cancelling_keeps_everything(self) -> None:
        self.install_fakes()
        result = self.ul("remove", input="no\n")
        self.assertEqual(result.returncode, 1)
        for text in ("ul, unlaw, ula, ule", "every command", "background job", "~/.zshrc", "cannot be undone"):
            self.assertIn(text, result.stdout)
        self.assertTrue((self.unlaw / "config.toml").is_file())
        self.assertTrue((self.home / ".local" / "bin" / "ul").exists())
        self.assertEqual(self.calls(self.launchctl), [])

    def test_remove_deletes_the_program_and_its_files(self) -> None:
        self.install_fakes()
        outside = self.root / "storage"
        self.ok("config", "set", "storage.root", str(outside))
        self.ok("init")
        result = self.ok("remove", input="y\n")
        self.assertIn("Kept: models in the Hugging Face cache", result.stdout)
        self.assertIn(str(outside), result.stdout)
        self.assertFalse(self.unlaw.exists())
        self.assertTrue(outside.is_dir(), "storage outside the config folder is kept")
        self.assertEqual(list((self.home / ".local" / "bin").iterdir()), [])
        self.assertFalse((self.home / "Library" / "Caches" / "unlaw").exists())
        self.assertFalse((self.home / "Library" / "LaunchAgents" / "com.unlaw.agent.plist").exists())
        self.assertEqual((self.home / ".zshrc").read_text(), "export A=1\nalias b=c\n")
        self.assertEqual(self.calls(self.launchctl)[0][0], "bootout")
        self.assertEqual([call[0] for call in self.calls(self.cargo)], ["uninstall", "uninstall"])


class ReinstallTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.env.pop("CARGO_TARGET_DIR", None)
        self.cache = self.home / "Library" / "Caches" / "unlaw" / "cargo-target"
        self.cache.mkdir(parents=True)
        (self.cache / "old").write_text("x")
        self.ok("init")

    def fake_cargo(self, *, exit_code: int = 0) -> Path:
        """Logs each call and whether the cache still exists, then installs a ul that runs this build."""
        log = self.root / "cargo.log"
        self.tool(
            "cargo",
            f"#!{sys.executable}\nimport pathlib, sys\n"
            f"open({str(log)!r}, 'a').write(sys.argv[-1] + ' cache=' + str(pathlib.Path({str(self.cache)!r}).exists()) + '\\n')\n"
            f"if {exit_code}: raise SystemExit({exit_code})\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1]) / 'bin'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            f"(root / 'ul').write_text('#!/bin/sh\\nexec {binary()} \"$@\"\\n')\n"
            "(root / 'ul').chmod(0o755)\n",
        )
        return log

    def test_cancel_changes_nothing(self) -> None:
        log = self.fake_cargo()
        result = self.ul("reinstall", input="\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Kept: commands you wrote", result.stdout)
        self.assertFalse(log.exists())
        self.assertTrue(self.cache.exists())

    def test_reinstall_rebuilds_and_resets_settings_but_keeps_user_files(self) -> None:
        log = self.fake_cargo()
        self.ok("config", "set", "games.difficulty", "hard")
        self.ok("config", "set", "core.features", '["yt", "todo"]')
        self.ok("config", "set", "storage.root", "elsewhere")
        (self.unlaw / "ule.toml").write_text("tab_width = 8\n")
        todo = self.unlaw / "commands" / "todo" / "main.py"
        todo.write_text(todo.read_text() + "# mine\n")
        self.command("hello", "print('hi')\n")
        (self.unlaw / "templates" / "python" / "keep.txt").write_text("t")

        result = self.ok("reinstall", input="y\n")
        self.assertEqual(log.read_text().splitlines(), ["unlaw cache=False", "ule cache=False"])
        self.assertEqual(self.ok("config", "get", "games.difficulty").stdout.strip(), "normal")
        self.assertEqual(json.loads(self.ok("config", "get", "core.features").stdout), ["yt", "todo"])
        self.assertEqual(self.ok("config", "get", "storage.root").stdout.strip(), "elsewhere")
        self.assertFalse((self.unlaw / "ule.toml").exists())
        self.assertEqual(todo.read_text(), command_source("todo"))
        self.assertTrue((self.unlaw / "commands" / "yt" / "main.py").is_file())
        self.assertTrue((self.unlaw / "commands" / "hello" / "main.py").is_file())
        self.assertTrue((self.unlaw / "templates" / "python" / "keep.txt").is_file())
        backups = list((self.unlaw / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertIn("hard", (backups[0] / "config.toml").read_text())
        self.assertTrue((backups[0] / "ule.toml").is_file())
        self.assertIn("# mine", (backups[0] / "commands" / "todo" / "main.py").read_text())
        self.assertFalse((backups[0] / "commands" / "yt").exists(), "untouched seeds are not backed up")
        self.assertIn("Edited default commands saved there: todo", result.stdout)

    def test_a_failed_build_resets_nothing(self) -> None:
        self.fake_cargo(exit_code=3)
        self.ok("config", "set", "games.difficulty", "hard")
        result = self.ul("reinstall", "--yes")
        self.assertEqual(result.returncode, 3)
        self.assertIn("were not reset", result.stderr)
        self.assertEqual(self.ok("config", "get", "games.difficulty").stdout.strip(), "hard")
        self.assertFalse((self.unlaw / "backups").exists())

    def test_usage(self) -> None:
        result = self.ul("reinstall", "now")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ul reinstall", result.stderr)


if __name__ == "__main__":
    unittest.main()
