# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open the current directory in the configured editor."""
from __future__ import annotations

COMMAND_HELP = 'Open the current directory in the configured editor.\nUsage: ul zed\nSetting: apps.editor ("auto" = the first installed of Zed, Visual Studio Code, Cursor,\n  Sublime Text; Finder when none is; or an app name such as "Zed")\nExample: ul zed\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'apps': {'editor': 'auto'}}


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



# apps.editor = "auto": the first of these that `open -a` finds, else Finder.
AUTO_EDITORS = ("Zed", "Visual Studio Code", "Cursor", "Sublime Text")


def _open_in_editor(editor: str, folder: str) -> int:
    if editor.strip() and editor != "auto":
        return subprocess.run(["open", "-a", editor, folder], check=False).returncode
    for name in AUTO_EDITORS:
        # `open -a` fails at once (exit 1, a message on stderr) when the app is not installed.
        if subprocess.run(["open", "-a", name, folder], check=False, stderr=subprocess.DEVNULL).returncode == 0:
            return 0
    return subprocess.run(["open", folder], check=False).returncode


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
        return _open_in_editor(editor, str(Path.cwd()))
    except (ConfigError, OSError) as error:
        print(f"unlaw zed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
