from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config_home = Path(self.temp.name) / "xdg"
        self.env = {"XDG_CONFIG_HOME": str(self.config_home)}

    def test_bootstrap_creates_complete_layout_on_first_run(self) -> None:
        from unlawful.config import ensure_layout

        with patch.dict(os.environ, self.env, clear=False):
            root = ensure_layout()
        self.assertEqual(root, self.config_home / "unlaw")
        self.assertTrue((root / "config.toml").is_file())
        self.assertTrue((root / "commands").is_dir())
        for name in ("commands", "python", "rust", "cpp"):
            self.assertTrue((root / "templates" / name).is_dir())

    def test_bootstrap_seeds_every_non_system_command_into_config(self) -> None:
        from unlawful.config import ensure_layout

        with patch.dict(os.environ, self.env, clear=False):
            root = ensure_layout()
        commands = root / "commands"
        expected = {"app", "capture", "cpp", "game", "git", "lm", "mac", "music", "py", "rust", "tg", "todo", "work", "yt"}
        self.assertTrue(expected <= {path.name for path in commands.iterdir() if path.is_dir()})
        wrapper = (commands / "game" / "main.py").read_text(encoding="utf-8")
        self.assertIn("unlawful.built_in_commands.game.main", wrapper)
        self.assertFalse((commands / "doctor").exists())

    def test_bootstrap_does_not_overwrite_customized_seed_command(self) -> None:
        from unlawful.config import ensure_layout

        custom = self.config_home / "unlaw" / "commands" / "music" / "main.py"
        custom.parent.mkdir(parents=True)
        custom.write_text("print('mine')\n", encoding="utf-8")
        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
        self.assertEqual(custom.read_text(encoding="utf-8"), "print('mine')\n")

    def test_storage_defaults_inside_program_config_and_accepts_custom_root(self) -> None:
        from unlawful.config import ensure_layout, set_config_value, storage_path

        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            self.assertEqual(storage_path("captures"), self.config_home / "unlaw" / "data" / "captures")
            custom = Path(self.temp.name) / "everything"
            set_config_value("storage.root", str(custom))
            self.assertEqual(storage_path("telegram"), custom / "telegram")

    def test_bootstrap_never_overwrites_existing_config(self) -> None:
        from unlawful.config import ensure_layout

        with patch.dict(os.environ, self.env, clear=False):
            root = ensure_layout()
            config = root / "config.toml"
            config.write_text("[core]\nverbose = true\n")
            ensure_layout()
        self.assertEqual(config.read_text(), "[core]\nverbose = true\n")

    def test_partial_config_is_merged_with_defaults(self) -> None:
        from unlawful.config import config_file, ensure_layout, load_config

        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            config_file().write_text('[core]\nverbose = true\n[aliases]\ng = ["git"]\n')
            config = load_config()
        self.assertTrue(config["core"]["verbose"])
        self.assertTrue(config["core"]["color"])
        self.assertEqual(config["aliases"]["g"], ["git"])
        self.assertEqual(config["projects"]["cpp"]["standard"], 20)

    def test_config_value_round_trip_is_atomic_and_keeps_unknown_keys(self) -> None:
        from unlawful.config import (
            ensure_layout,
            get_config_value,
            load_config,
            set_config_value,
        )

        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            config = load_config()
            config["custom"] = {"answer": 42}
            from unlawful.config import write_config

            write_config(config)
            set_config_value("aliases.g", ["git"])
            set_config_value("core.command_timeout", 15)
            self.assertEqual(get_config_value("aliases.g"), ["git"])
            self.assertEqual(get_config_value("core.command_timeout"), 15)
            self.assertEqual(load_config()["custom"]["answer"], 42)

    def test_invalid_known_value_has_clear_error(self) -> None:
        from unlawful.config import ConfigError, config_file, ensure_layout, load_config

        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            config_file().write_text('[core]\ncommand_timeout = "forever"\n')
            with self.assertRaisesRegex(ConfigError, "core.command_timeout"):
                load_config()


if __name__ == "__main__":
    unittest.main()
