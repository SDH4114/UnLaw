from __future__ import annotations

import json
import os
import pty
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class LauncherCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_home = self.root / "config"
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.open_log = self.root / "open.json"
        fake_open = self.bin_dir / "open"
        fake_open.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['OPEN_LOG']).write_text(json.dumps(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        fake_open.chmod(0o755)
        self.env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(self.config_home),
            "OPEN_LOG": str(self.open_log),
            "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        }

    def _run(self, name: str, *, cwd: Path | None = None, tty: bool = False) -> list[str]:
        from unlawful.config import ensure_layout

        with patch.dict(os.environ, self.env, clear=True):
            root = ensure_layout()
        script = root / "commands" / name / "main.py"
        self.assertTrue(script.is_file(), f"bootstrap did not create ul {name}")
        master = slave = None
        try:
            if tty:
                master, slave = pty.openpty()
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=cwd or self.root,
                env=self.env,
                stdin=slave,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            if master is not None:
                os.close(master)
            if slave is not None:
                os.close(slave)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(self.open_log.read_text(encoding="utf-8"))

    def test_lofi_opens_configured_website(self) -> None:
        self.assertEqual(self._run("lofi"), ["https://lofi-engine.vercel.app/"])

    def test_zed_opens_the_invocation_directory(self) -> None:
        project = self.root / "project"
        project.mkdir()
        self.assertEqual(self._run("zed", cwd=project), ["-a", "Zed", str(project.resolve())])

    def test_application_shortcuts_open_expected_macos_apps(self) -> None:
        expected = {
            "netflix": ["-a", "Netflix"],
            "obsidian": ["-a", "Obsidian"],
            "gpt": ["-a", "ChatGPT"],
            "steam": ["-a", "Steam"],
            "minecraft": ["-a", "Prism Launcher"],
        }
        for command, arguments in expected.items():
            with self.subTest(command=command):
                self.assertEqual(self._run(command), arguments)

    def test_browser_opens_the_default_browser(self) -> None:
        self.assertEqual(self._run("browser"), ["https://www.google.com/"])

    def test_tg_without_arguments_opens_telegram(self) -> None:
        self.assertEqual(self._run("tg", tty=True), ["-a", "Telegram"])


class CurlInstallerTests(unittest.TestCase):
    def test_installer_uses_uv_to_install_the_github_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            log = root / "uv-args.txt"
            uv = fake_bin / "uv"
            uv.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$@" > "$UV_LOG"\n',
                encoding="utf-8",
            )
            uv.chmod(0o755)
            installer = ROOT / "install.sh"
            self.assertTrue(installer.is_file(), "curl installer is missing")
            result = subprocess.run(
                ["sh", str(installer)],
                env={
                    **os.environ,
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                    "UV_LOG": str(log),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["tool", "install", "--force", "git+https://github.com/SDH4114/UnLaw.git"],
            )


if __name__ == "__main__":
    unittest.main()
