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
        fake_defaults = self.bin_dir / "defaults"
        fake_defaults.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' '( { LSHandlerURLScheme = http; LSHandlerRoleAll = com.google.Chrome; } )'\n",
            encoding="utf-8",
        )
        fake_defaults.chmod(0o755)
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

    def test_browser_opens_duckduckgo_by_default(self) -> None:
        self.assertEqual(self._run("browser"), ["https://duckduckgo.com/"])

    def test_browser_opens_the_user_configured_page(self) -> None:
        from unlawful.config import ensure_layout, set_config_value

        with patch.dict(os.environ, self.env, clear=True):
            ensure_layout()
            set_config_value("apps.browser_url", "https://example.com/start")
        self.assertEqual(self._run("browser"), ["https://example.com/start"])

    def test_tg_without_arguments_opens_telegram(self) -> None:
        self.assertEqual(self._run("tg", tty=True), ["-a", "Telegram"])


class CurlInstallerTests(unittest.TestCase):
    def _fake(self, directory: Path, name: str, body: str) -> None:
        script = directory / name
        script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        script.chmod(0o755)

    def _install(self, *, uv_has_unlaw: bool) -> tuple[subprocess.CompletedProcess[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        cargo_log, uv_log = root / "cargo.txt", root / "uv.txt"
        self._fake(fake_bin, "cargo", f'printf "%s\\n" "UNLAW_PYTHON=$UNLAW_PYTHON" "$@" > "{cargo_log}"\n')
        self._fake(fake_bin, "python3.13", "exit 0\n")
        listing = "unlaw v2.1.3" if uv_has_unlaw else "ruff v0.1"
        self._fake(
            fake_bin,
            "uv",
            f'if [ "$2" = list ]; then echo "{listing}"; else printf "%s\\n" "$@" > "{uv_log}"; fi\n',
        )
        installer = ROOT / "install.sh"
        result = subprocess.run(
            ["sh", str(installer)],
            env={"PATH": f"{fake_bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(root / "home")},
            capture_output=True,
            text=True,
            check=False,
        )
        return result, root

    def test_installer_builds_the_rust_core_into_local_bin(self) -> None:
        result, root = self._install(uv_has_unlaw=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (root / "cargo.txt").read_text(encoding="utf-8").splitlines(),
            [
                "UNLAW_PYTHON=python3.13",
                "install",
                "--locked",
                "--force",
                "--git",
                "https://github.com/SDH4114/UnLaw.git",
                "--root",
                str(root / "home" / ".local"),
                "unlaw",
                "ule",
            ],
        )
        self.assertFalse((root / "uv.txt").exists())

    def test_installer_removes_the_previous_uv_tool(self) -> None:
        result, root = self._install(uv_has_unlaw=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / "uv.txt").read_text(encoding="utf-8").splitlines(), ["tool", "uninstall", "unlaw"])


if __name__ == "__main__":
    unittest.main()
