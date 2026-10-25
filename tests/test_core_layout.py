"""Bootstrap, seeding and help of the Rust core, checked against the Python sources it embeds."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from ulbin import CoreTestCase  # noqa: E402
from unlawful.command_help import COMMAND_HELP  # noqa: E402
from unlawful.command_sources import LEGACY_SOURCE_HASHES, command_source  # noqa: E402
from unlawful.config import DEFAULT_COMMAND_NAMES, DEFAULT_CONFIG, serialize_config  # noqa: E402

SYSTEM_COMMANDS = (
    "commands", "completion", "config", "create", "doctor", "init", "list", "templates", "update", "venv", "version",
    "which",
)


class LayoutTests(CoreTestCase):
    def commands_dir(self) -> Path:
        return self.unlaw / "commands"

    def test_bootstrap_creates_complete_layout_on_first_run(self) -> None:
        self.ok("init")
        self.assertTrue((self.unlaw / "config.toml").is_file())
        for name in ("commands", "python", "rust", "cpp", "projects"):
            self.assertTrue((self.unlaw / "templates" / name).is_dir())
        for relative in ("data/captures/screenshots", "data/captures/recordings", "data/telegram/downloads", "data/runtime"):
            self.assertTrue((self.unlaw / relative).is_dir(), relative)

    def test_embedded_defaults_match_python(self) -> None:
        self.ok("init")
        self.assertEqual((self.unlaw / "config.toml").read_text(), serialize_config(DEFAULT_CONFIG))

    def test_bootstrap_seeds_current_python_sources_for_every_command(self) -> None:
        self.ok("init")
        seeded = {path.name for path in self.commands_dir().iterdir() if path.is_dir()}
        self.assertEqual(seeded, set(DEFAULT_COMMAND_NAMES))
        self.assertFalse((self.commands_dir() / "doctor").exists())
        for name in DEFAULT_COMMAND_NAMES:
            with self.subTest(name=name):
                source = (self.commands_dir() / name / "main.py").read_text()
                self.assertEqual(source, command_source(name))
                self.assertNotIn("unlawful.", source)
                compile(source, name, "exec")
                summary = COMMAND_HELP[name].splitlines()[0]
                self.assertEqual(source.splitlines()[1], f'"""{summary}"""')

    def test_bootstrap_replaces_the_old_official_wrapper_with_full_source(self) -> None:
        legacy = self.command(
            "work",
            "from unlawful.built_in_commands.work.main import main\n\n"
            'if __name__ == "__main__":\n    raise SystemExit(main())\n',
        )
        self.ok("init")
        self.assertEqual(legacy.read_text(), command_source("work"))

    def test_untouched_source_from_the_previous_release_is_upgraded(self) -> None:
        current = command_source("git")
        lines = current.splitlines(keepends=True)
        previous = lines[0] + "".join(lines[2:])  # 2.1.3 had no summary docstring
        self.assertIn(hashlib.sha256(previous.encode()).hexdigest(), LEGACY_SOURCE_HASHES["git"])
        script = self.command("git", previous)
        self.ok("init")
        self.assertEqual(script.read_text(), current)

    def test_bootstrap_does_not_overwrite_customized_seed_command(self) -> None:
        custom = self.command("music", "print('mine')\n")
        edited = self.command("yt", command_source("yt") + "\n# My custom change\n")
        self.ok("init")
        self.assertEqual(custom.read_text(), "print('mine')\n")
        self.assertTrue(edited.read_text().endswith("# My custom change\n"))

    def test_bootstrap_never_overwrites_existing_config(self) -> None:
        self.ok("init")
        config = self.unlaw / "config.toml"
        config.write_text("[core]\nverbose = true\n")
        self.ok("init")
        self.assertEqual(config.read_text(), "[core]\nverbose = true\n")

    def test_partial_config_is_merged_with_defaults(self) -> None:
        self.ok("init")
        (self.unlaw / "config.toml").write_text('[core]\nverbose = true\n[aliases]\ng = ["git"]\n')
        self.assertEqual(self.ok("config", "get", "core.verbose").stdout, "true\n")
        self.assertEqual(self.ok("config", "get", "core.color").stdout, "true\n")
        self.assertEqual(self.ok("config", "get", "projects.cpp.standard").stdout, "20\n")
        self.assertIn('"g": [', self.ok("config", "get", "aliases").stdout)

    def test_storage_root_is_configurable(self) -> None:
        self.assertIn(f"Storage: {self.unlaw / 'data'}", self.ok("init").stdout)
        custom = self.root / "everything"
        self.ok("config", "set", "storage.root", str(custom))
        self.assertIn(f"Storage: {custom}", self.ok("init").stdout)
        self.assertTrue((custom / "telegram" / "downloads").is_dir())

    def test_invalid_known_value_has_clear_error(self) -> None:
        self.ok("init")
        (self.unlaw / "config.toml").write_text('[core]\ncommand_timeout = "forever"\n')
        result = self.ul("git")
        self.assertEqual(result.returncode, 2)
        self.assertIn("core.command_timeout", result.stderr)


class HelpTests(CoreTestCase):
    def test_every_system_command_has_help_without_side_effects(self) -> None:
        for name in SYSTEM_COMMANDS:
            outputs = set()
            for flag in ("--help", "-h", "help"):
                with self.subTest(name=name, flag=flag):
                    result = self.ok(name, flag)
                    self.assertIn(f"ul {name}", result.stdout)
                    self.assertIn("Example", result.stdout)
                    outputs.add(result.stdout)
            self.assertEqual(len(outputs), 1, name)
        self.assertFalse((self.unlaw / "commands" / "--help").exists())
        self.assertEqual(self.ok("templates").stdout, "")

    def test_cli_help_alias_and_new_command_template(self) -> None:
        self.assertEqual(self.ok("help", "yt").stdout, COMMAND_HELP["yt"])
        self.ok("create", "command", "hello")
        self.assertIn("Usage: ul hello", self.ok("hello", "--help").stdout)
        self.ok("config", "set", "aliases.youtube", '["yt"]')
        self.assertIn("ul yt download", self.ok("youtube", "--help").stdout)


if __name__ == "__main__":
    unittest.main()


class SeedUpgradeTests(CoreTestCase):
    """Copies that differ from an official source only in blank lines or the summary
    docstring are untouched and get upgraded; real edits are kept."""

    def test_copies_without_docstring_are_upgraded_and_edits_kept(self) -> None:
        self.ok("version")
        seed = (self.unlaw / "commands" / "tg" / "main.py").read_text(encoding="utf-8")
        lines = seed.splitlines()
        self.assertTrue(lines[1].startswith('"""'))
        mangled = "\n".join(lines[:1] + lines[2:]).replace("\n\n\n", "\n\n\n\n") + "\n"
        (self.unlaw / "commands" / "tg" / "main.py").write_text(mangled, encoding="utf-8")
        edited = seed + "\nprint('mine')\n"
        (self.unlaw / "commands" / "todo" / "main.py").write_text(edited, encoding="utf-8")
        self.ok("version")
        self.assertEqual((self.unlaw / "commands" / "tg" / "main.py").read_text(encoding="utf-8"), seed)
        self.assertEqual((self.unlaw / "commands" / "todo" / "main.py").read_text(encoding="utf-8"), edited)
        self.assertIn("Open Telegram", self.ok("commands", "--describe").stdout)

    def test_python_and_rust_normalize_alike(self) -> None:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from unlawful.command_sources import command_source, is_replaceable_command_source, normalized_source

        source = command_source("todo")
        self.assertFalse(normalized_source(source).startswith('"""'))
        stripped = "\n".join(line for line in source.splitlines() if not line.startswith('"""Read'))
        self.assertTrue(is_replaceable_command_source(stripped, "todo"))
        self.assertFalse(is_replaceable_command_source(source + "\nprint('mine')\n", "todo"))
