"""Run the Rust `ul` binary as a black box from the Python test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_BINARY: Path | None = None


def binary() -> Path:
    """Build once per test run; UNLAW_TEST_BINARY selects a prebuilt binary."""
    global _BINARY
    if _BINARY is None:
        explicit = os.environ.get("UNLAW_TEST_BINARY")
        if explicit:
            _BINARY = Path(explicit)
        else:
            if shutil.which("cargo") is None:
                raise unittest.SkipTest("cargo is required to build the Rust core")
            subprocess.run(["cargo", "build", "--quiet", "--bin", "ul"], cwd=ROOT, check=True)
            _BINARY = ROOT / "target" / "debug" / "ul"
    return _BINARY


class CoreTestCase(unittest.TestCase):
    """A temporary XDG config, HOME and bin directory for each test."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config_home = self.root / "config"
        self.unlaw = self.config_home / "unlaw"
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(self.config_home),
            "HOME": str(self.home),
            "UNLAW_PYTHON": sys.executable,
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        for key in ("VISUAL", "EDITOR"):
            self.env.pop(key, None)
        # The real Keychain is never queried; tests that need a token add their own.
        self.tool("security", "#!/bin/sh\nexit 44\n")

    def ul(
        self,
        *args: str,
        input: str | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(binary()), *args],
            env={**self.env, **(env or {})},
            cwd=cwd or self.root,
            input=input if input is not None else "",
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def ok(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        result = self.ul(*args, **kwargs)  # type: ignore[arg-type]
        self.assertEqual(result.returncode, 0, f"ul {' '.join(args)}\n{result.stdout}\n{result.stderr}")
        return result

    def command(self, name: str, body: str, entry: str = "main.py", *, executable: bool = False) -> Path:
        script = self.unlaw / "commands" / name / entry
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(body, encoding="utf-8")
        if executable:
            script.chmod(0o755)
        return script

    def tool(self, name: str, body: str) -> Path:
        script = self.bin / name
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
        return script

    def recording_tool(self, name: str, *, exit_code: int = 0) -> Path:
        """A fake executable that appends its argv as one line to <name>.log."""
        log = self.root / f"{name}.log"
        self.tool(
            name,
            f"#!{sys.executable}\nimport sys\n"
            f"open({str(log)!r}, 'a').write('|'.join(sys.argv[1:]) + '\\n')\n"
            f"raise SystemExit({exit_code})\n",
        )
        return log

    def calls(self, log: Path) -> list[list[str]]:
        if not log.exists():
            return []
        return [line.split("|") if line else [] for line in log.read_text(encoding="utf-8").splitlines()]

    def save_template(self, name: str, project: Path, app: str = "zed", ai: bool = False) -> None:
        answers = f"{app}\n{'y' if ai else 'n'}\n"
        self.ok("create", "template", name, input=answers, cwd=project)

