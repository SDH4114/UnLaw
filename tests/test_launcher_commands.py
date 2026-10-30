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

    def test_tg_without_arguments_opens_telegram(self) -> None:
        self.assertEqual(self._run("tg", tty=True), ["-a", "Telegram"])


class CurlInstallerTests(unittest.TestCase):
    def _fake(self, directory: Path, name: str, body: str) -> None:
        script = directory / name
        script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        script.chmod(0o755)

    def _install(
        self, *, uv_has_unlaw: bool, features: str | None = None, prepare: object = None
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        cargo_log, uv_log, ul_log = root / "cargo.txt", root / "uv.txt", root / "ul.txt"
        # Each cargo call is logged; installing unlaw puts a fake ul into --root/bin.
        self._fake(
            fake_bin,
            "cargo",
            f'printf "%s\\n" "UNLAW_PYTHON=$UNLAW_PYTHON" "CARGO_TARGET_DIR=$CARGO_TARGET_DIR" "$@" "==" >> "{cargo_log}"\n'
            'while [ "$1" != --root ]; do shift; done\n'
            'mkdir -p "$2/bin"\n'
            f'printf \'#!/bin/sh\\nprintf "%%s\\\\n" "$@" > "{ul_log}"\\n\' > "$2/bin/ul"\n'
            'chmod +x "$2/bin/ul"\n',
        )
        (fake_bin / "python3.13").symlink_to(sys.executable)
        listing = "unlaw v2.1.3" if uv_has_unlaw else "ruff v0.1"
        self._fake(
            fake_bin,
            "uv",
            f'if [ "$2" = list ]; then echo "{listing}"; else printf "%s\\n" "$@" > "{uv_log}"; fi\n',
        )
        if callable(prepare):
            prepare(root)
        installer = ROOT / "install.sh"
        env = {"PATH": f"{fake_bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(root / "home")}
        if features is not None:
            env["UNLAW_FEATURES"] = features
        result = subprocess.run(
            ["sh", str(installer)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            # No controlling terminal, so the checklist is skipped like in CI.
            start_new_session=True,
        )
        return result, root

    def cargo_calls(self, root: Path) -> list[list[str]]:
        calls, current = [], []
        for line in (root / "cargo.txt").read_text(encoding="utf-8").splitlines():
            if line == "==":
                calls.append(current)
                current = []
            else:
                current.append(line)
        return calls

    def test_installer_builds_the_rust_core_into_local_bin(self) -> None:
        result, root = self._install(uv_has_unlaw=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        common = [
            "UNLAW_PYTHON=python3.13",
            f"CARGO_TARGET_DIR={root / 'home' / 'Library' / 'Caches' / 'unlaw' / 'cargo-target'}",
            "install",
            "--locked",
            "--force",
            "--git",
            "https://github.com/SDH4114/UnLaw.git",
            "--root",
            str(root / "home" / ".local"),
        ]
        self.assertEqual(
            self.cargo_calls(root),
            [[*common, "--no-default-features", "--features", "lm,agent,game", "unlaw"], [*common, "ule"]],
        )
        self.assertEqual((root / "ul.txt").read_text().splitlines(), ["features", "set", "--no-build", "all"])
        self.assertIn("Installing the core and: all", result.stdout)
        self.assertFalse((root / "uv.txt").exists())

    def test_reinstalling_keeps_the_existing_choice_without_asking(self) -> None:
        def prepare(root: Path) -> None:
            config = root / "home" / ".config" / "unlaw" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text('[core]\nfeatures = ["yt", "game"]\n')

        result, root = self._install(uv_has_unlaw=False, prepare=prepare)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("keeping its features", result.stdout)
        self.assertEqual(self.cargo_calls(root)[0][-4:], ["--no-default-features", "--features", "game", "unlaw"])
        self.assertEqual((root / "ul.txt").read_text().splitlines(), ["features", "set", "--no-build", "yt", "game"])

    def test_installer_takes_features_from_the_environment(self) -> None:
        result, root = self._install(uv_has_unlaw=False, features="yt agent")
        self.assertEqual(result.returncode, 0, result.stderr)
        unlaw, ule = self.cargo_calls(root)
        self.assertEqual(unlaw[-4:], ["--no-default-features", "--features", "lm,agent", "unlaw"])
        self.assertEqual(ule[-1], "ule")
        self.assertEqual((root / "ul.txt").read_text().splitlines(), ["features", "set", "--no-build", "lm", "agent", "yt"])
        result, root = self._install(uv_has_unlaw=False, features="music")
        self.assertEqual(self.cargo_calls(root)[0][-2:], ["--no-default-features", "unlaw"])
        result, root = self._install(uv_has_unlaw=False, features="none")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / "ul.txt").read_text().splitlines(), ["features", "set", "--no-build", "none"])
        result, root = self._install(uv_has_unlaw=False, features="nope")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nope", result.stderr)
        self.assertFalse((root / "cargo.txt").exists(), "nothing is built for an unknown feature")

    def test_installer_removes_the_previous_uv_tool(self) -> None:
        result, root = self._install(uv_has_unlaw=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / "uv.txt").read_text(encoding="utf-8").splitlines(), ["tool", "uninstall", "unlaw"])


if __name__ == "__main__":
    unittest.main()
