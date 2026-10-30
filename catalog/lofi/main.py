# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open the configured lofi website in your default browser."""
from __future__ import annotations

COMMAND_HELP = 'Open the configured lofi website in your default browser.\nUsage: ul lofi\nSetting: apps.lofi_url\nExample: ul lofi\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'apps': {'lofi_url': 'https://lofi-engine.vercel.app/'}}


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

import subprocess
import sys
from collections.abc import Sequence



def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    if args:
        print("Usage: ul lofi", file=sys.stderr)
        return 2
    try:
        url = str(load_config()["apps"]["lofi_url"])
        return subprocess.run(["open", url], check=False).returncode
    except (ConfigError, OSError) as error:
        print(f"unlaw lofi: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
