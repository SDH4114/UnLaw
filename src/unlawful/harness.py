"""Small optional bridge to the separately installed macOS Harness CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from .config import ConfigError, load_config


def _settings() -> tuple[str | None, int]:
    try:
        settings = load_config()["mac"]
    except ConfigError as error:
        print(f"unlaw: {error}", file=sys.stderr)
        return None, 0
    executable = shutil.which(settings["executable"])
    if executable is None:
        print(f"unlaw: macOS Harness was not found: {settings['executable']}", file=sys.stderr)
    return executable, settings["timeout"]


def _run_program(statement: str) -> int:
    executable, timeout = _settings()
    if executable is None:
        return 1
    try:
        result = subprocess.run(
            [executable], input=f"{statement}\n", text=True, check=False, timeout=timeout or None
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        print("unlaw mac: macOS Harness timed out.", file=sys.stderr)
        return 124


def see(app: str) -> int:
    executable, timeout = _settings()
    if executable is None:
        return 1
    try:
        return subprocess.run(
            [executable, "see", app], check=False, timeout=timeout or None
        ).returncode
    except subprocess.TimeoutExpired:
        print("unlaw mac: macOS Harness timed out.", file=sys.stderr)
        return 124


def key(app: str, shortcut: str) -> int:
    return _run_program(f"mac.key({json.dumps(shortcut)}, app={json.dumps(app)})")


def type_text(app: str, text: str) -> int:
    return _run_program(f"mac.type({json.dumps(text)}, app={json.dumps(app)})")


def click(app: str, x: float, y: float) -> int:
    return _run_program(f"mac.click({x!r}, {y!r}, app={json.dumps(app)})")
