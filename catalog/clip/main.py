# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Clipboard history in the background: list, search and copy again."""
from __future__ import annotations

COMMAND_HELP = 'Clipboard history in the background: list, search and copy again.\nUsage: ul clip\nExample: ul clip\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'}, 'clip': {'max_items': 200, 'interval': 1.0}}


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

def storage_path(*parts: str) -> Path:
    configured = Path(str(load_config()["storage"]["root"])).expanduser()
    root = configured if configured.is_absolute() else config_dir() / configured
    return root.joinpath(*parts)

import sys
from collections.abc import Sequence



def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    print("unlaw clip: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
