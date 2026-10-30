# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Control macOS applications through optional macos-harness."""
from __future__ import annotations

COMMAND_HELP = 'Control macOS applications through optional macos-harness.\nUsage:\n  ul mac see <application>                 Inspect an application\n  ul mac key <application> <shortcut>      Send a keyboard shortcut\n  ul mac type <application> <text>         Type text\n  ul mac click <application> <x> <y>       Click coordinates\nExample: ul mac see Zed\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'mac': {'executable': 'macos-harness', 'timeout': 30}}


class ConfigError(ValueError):
    pass


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "unlaw"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = (
            _deep_merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else copy.deepcopy(value)
        )
    return result


def load_config() -> dict:
    path = config_dir() / "config.toml"
    try:
        with path.open("rb") as handle:
            configured = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read {path}: {error}") from error
    return _deep_merge(DEFAULT_CONFIG, configured)

"""Small optional bridge to the separately installed macOS Harness CLI."""


import json
import shutil
import subprocess
import sys



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

import sys
from collections.abc import Sequence



HELP = """Usage:
  ul mac see <application>
  ul mac key <application> <shortcut>
  ul mac type <application> <text>
  ul mac click <application> <x> <y>
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP, end="")
        return 0 if args else 2
    action = args[0]
    if action == "see" and len(args) >= 2:
        return see(" ".join(args[1:]))
    if action == "key" and len(args) == 3:
        return key(args[1], args[2])
    if action == "type" and len(args) >= 3:
        return type_text(args[1], " ".join(args[2:]))
    if action == "click" and len(args) == 4:
        try:
            return click(args[1], float(args[2]), float(args[3]))
        except ValueError:
            pass
    print(HELP, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
