"""Configuration writes by the generated, standalone Telegram command."""

from __future__ import annotations

import os
import runpy
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unlawful.command_sources import command_source


class TelegramSeedConfigTests(unittest.TestCase):
    def test_setup_preserves_quoted_unknown_keys_as_valid_toml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"HOME": str(root), "XDG_CONFIG_HOME": str(root / "config")}):
                script = root / "tg.py"
                script.write_text(command_source("tg"), encoding="utf-8")
                namespace = runpy.run_path(str(script), run_name="seed_under_test")
                config = root / "config/unlaw/config.toml"
                config.parent.mkdir(parents=True)
                config.write_text(
                    '[telegram]\nchat_id = ""\n["custom.table"]\n"has space" = "keep"\n',
                    encoding="utf-8",
                )
                namespace["set_config_value"]("telegram.chat_id", "42")
                data = tomllib.loads(config.read_text(encoding="utf-8"))
                self.assertEqual(data["telegram"]["chat_id"], "42")
                self.assertEqual(data["custom.table"], {"has space": "keep"})
