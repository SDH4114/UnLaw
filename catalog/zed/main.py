# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open the current directory in the configured editor (default: Zed)."""
from __future__ import annotations

COMMAND_HELP = 'Open the current directory in the configured editor (default: Zed).\nUsage: ul zed\nSetting: apps.editor\nExample: ul zed\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'apps': {'editor': 'Zed'}}


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
from pathlib import Path



def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    if args:
        print("Usage: ul zed", file=sys.stderr)
        return 2
    try:
        editor = str(load_config()["apps"]["editor"])
        return subprocess.run(["open", "-a", editor, str(Path.cwd())], check=False).returncode
    except (ConfigError, OSError) as error:
        print(f"unlaw zed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
