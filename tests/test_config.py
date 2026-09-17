from __future__ import annotations

import ast
import hashlib
import os
import sys
import tempfile
import tomllib
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
        for name in ("commands", "python", "rust", "cpp", "projects"):
            self.assertTrue((root / "templates" / name).is_dir())
        for relative in (
            "data/captures/screenshots",
            "data/captures/recordings",
            "data/telegram/downloads",
            "data/runtime",
        ):
            self.assertTrue((root / relative).is_dir(), relative)

    def test_bootstrap_seeds_every_non_system_command_into_config(self) -> None:
        from unlawful.config import ensure_layout

        with patch.dict(os.environ, self.env, clear=False):
            root = ensure_layout()
        commands = root / "commands"
        expected = {
            "app",
            "browser",
            "capture",
            "cpp",
            "game",
            "git",
            "gpt",
            "lm",
            "lofi",
            "mac",
            "minecraft",
            "music",
            "netflix",
            "obsidian",
            "py",
            "rust",
            "steam",
            "tg",
            "todo",
            "work",
            "yt",
            "zed",
        }
        self.assertTrue(expected <= {path.name for path in commands.iterdir() if path.is_dir()})
        game = (commands / "game" / "main.py").read_text(encoding="utf-8")
        self.assertIn("def main", game)
        self.assertNotIn("unlawful.", game)
        self.assertNotIn("from .", game)
        self.assertFalse((commands / "doctor").exists())

    def test_every_seeded_command_is_self_contained_python(self) -> None:
        from unlawful.config import ensure_layout

        with patch.dict(os.environ, self.env, clear=False):
            root = ensure_layout()
        for script in sorted((root / "commands").glob("*/main.py")):
            source = script.read_text(encoding="utf-8")
            self.assertNotIn("unlawful.", source, script)
            self.assertNotIn("from .", source, script)
            compile(source, str(script), "exec")

    def test_seeded_commands_include_only_their_own_config_defaults(self) -> None:
        from unlawful.config import ensure_layout

        expected = {
            "browser": {"apps": {"browser_url": "https://duckduckgo.com/"}},
            "capture": {
                "storage": {"root": "data"},
                "capture": {
                    "camera_device": "0",
                    "audio_device": "0",
                    "screen_audio": True,
                    "show_clicks": True,
                },
            },
            "cpp": {"projects": {"cpp": {"standard": 20, "initialize_git": False}}},
            "game": {"games": {"difficulty": "normal"}},
            "lm": {
                "lm": {
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model": "auto",
                    "system_prompt": "You are a concise and practical local assistant.",
                    "temperature": 0.7,
                    "timeout": 120,
                }
            },
            "lofi": {"apps": {"lofi_url": "https://lofi-engine.vercel.app/"}},
            "mac": {"mac": {"executable": "macos-harness", "timeout": 30}},
            "music": {
                "apps": {
                    "spotify": "Spotify",
                    "spotify_autoplay_delay": 2.0,
                }
            },
            "py": {"projects": {"python": {"environment": "auto", "initialize_git": False}}},
            "rust": {"projects": {"rust": {"initialize_git": False}}},
            "tg": {
                "storage": {"root": "data"},
                "telegram": {
                    "chat_id": "",
                    "api_base": "https://api.telegram.org",
                    "keychain_service": "unlaw.telegram",
                },
            },
            "todo": {
                "todo": {
                    "vault_path": "~/aiwork/data-obsidian",
                    "file": "TODO.md",
                    "completed_column": "Completed",
                }
            },
            "work": {
                "apps": {
                    "editor": "Zed",
                    "lofi_url": "https://lofi-engine.vercel.app/",
                }
            },
            "yt": {"apps": {"youtube_url": "https://www.youtube.com/"}},
            "zed": {"apps": {"editor": "Zed"}},
        }
        with patch.dict(os.environ, self.env, clear=False):
            root = ensure_layout()
        for script in sorted((root / "commands").glob("*/main.py")):
            assignments = {
                node.targets[0].id: ast.literal_eval(node.value)
                for node in ast.parse(script.read_text(encoding="utf-8")).body
                if isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "DEFAULT_CONFIG"
            }
            if script.parent.name in expected:
                self.assertEqual(assignments.get("DEFAULT_CONFIG"), expected[script.parent.name], script)
            else:
                self.assertNotIn("DEFAULT_CONFIG", assignments, script)

    def test_each_launcher_source_contains_only_its_own_target(self) -> None:
        from unlawful.config import ensure_layout

        targets = {
            "gpt": "ChatGPT",
            "minecraft": "Prism Launcher",
            "netflix": "Netflix",
            "obsidian": "Obsidian",
            "steam": "Steam",
        }
        with patch.dict(os.environ, self.env, clear=False):
            commands = ensure_layout() / "commands"
        for command, target in targets.items():
            source = (commands / command / "main.py").read_text(encoding="utf-8")
            self.assertIn(target, source)
            for other_command, other_target in targets.items():
                if other_command != command:
                    self.assertNotIn(other_target, source, f"{command} contains {other_command}")
        browser = (commands / "browser" / "main.py").read_text(encoding="utf-8")
        self.assertIn("browser_url", browser)
        self.assertNotIn("LSHandler", browser)
        self.assertNotIn("google.com", browser)

    def test_bootstrap_replaces_the_old_official_wrapper_with_full_source(self) -> None:
        from unlawful.config import ensure_layout

        legacy = self.config_home / "unlaw" / "commands" / "work" / "main.py"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(
            "from unlawful.built_in_commands.work.main import main\n\n"
            "if __name__ == \"__main__\":\n"
            "    raise SystemExit(main())\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
        source = legacy.read_text(encoding="utf-8")
        self.assertIn("def main", source)
        self.assertNotIn("unlawful.", source)

    def test_bootstrap_does_not_overwrite_customized_seed_command(self) -> None:
        from unlawful.config import ensure_layout

        custom = self.config_home / "unlaw" / "commands" / "music" / "main.py"
        custom.parent.mkdir(parents=True)
        custom.write_text("print('mine')\n", encoding="utf-8")
        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
        self.assertEqual(custom.read_text(encoding="utf-8"), "print('mine')\n")

    def test_bootstrap_upgrades_an_exact_known_official_command_source(self) -> None:
        from unlawful import command_sources
        from unlawful.config import ensure_layout

        old_source = "# old official git command\nprint('old')\n"
        digest = hashlib.sha256(old_source.encode()).hexdigest()
        command = self.config_home / "unlaw" / "commands" / "git" / "main.py"
        command.parent.mkdir(parents=True)
        command.write_text(old_source, encoding="utf-8")
        with patch.dict(command_sources.LEGACY_SOURCE_HASHES, {"git": {digest}}, clear=False), patch.dict(
            os.environ, self.env, clear=False
        ):
            ensure_layout()
        upgraded = command.read_text(encoding="utf-8")
        self.assertNotEqual(upgraded, old_source)
        self.assertIn('input("Commit message: ")', upgraded)

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

    def test_source_build_bootstraps_full_user_command_sources(self) -> None:
        from hatch_build import bootstrap_user_layout

        with patch.dict(os.environ, self.env, clear=False):
            bootstrap_user_layout()
        command = self.config_home / "unlaw" / "commands" / "music" / "main.py"
        self.assertTrue(command.is_file())
        source = command.read_text(encoding="utf-8")
        self.assertIn("def main", source)
        self.assertNotIn("unlawful.", source)

    def test_source_build_registers_the_custom_hatch_hook(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)
        self.assertIn("custom", project["tool"]["hatch"]["build"]["hooks"])


if __name__ == "__main__":
    unittest.main()
