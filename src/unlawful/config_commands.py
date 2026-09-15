from __future__ import annotations

import copy
import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from datetime import datetime

from .config import (
    DEFAULT_CONFIG,
    ConfigError,
    config_file,
    ensure_layout,
    get_config_value,
    load_config,
    set_config_value,
    validate_config,
    write_config,
)

USAGE = "Usage: ul config path|show|get|set|edit|check|reset"


def _display(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _parse_value(raw: str) -> object:
    try:
        return tomllib.loads(f"value = {raw}")["value"]
    except tomllib.TOMLDecodeError:
        return raw


def _edit() -> int:
    path = config_file()
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    command = [*shlex.split(editor), str(path)] if editor else ["open", "-t", str(path)]
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"unlaw config: Could not open editor: {error}", file=sys.stderr)
        return 1


def config_command(argv: Sequence[str]) -> int:
    ensure_layout()
    args = list(argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0 if args else 2
    action, rest = args[0], args[1:]
    try:
        if action == "path" and not rest:
            print(config_file())
            return 0
        if action == "show" and not rest:
            print(config_file().read_text(encoding="utf-8"), end="")
            return 0
        if action == "get" and len(rest) == 1:
            print(_display(get_config_value(rest[0])))
            return 0
        if action == "set" and len(rest) >= 2:
            value = _parse_value(" ".join(rest[1:]))
            set_config_value(rest[0], value)
            print(f"Set {rest[0]} = {_display(value)}")
            return 0
        if action == "edit" and not rest:
            return _edit()
        if action == "check" and not rest:
            errors = validate_config(load_config())
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 2
            print(f"Configuration is valid: {config_file()}")
            return 0
        if action == "reset":
            if rest != ["--yes"]:
                print("unlaw config: Reset requires --yes.", file=sys.stderr)
                return 2
            stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
            backup = config_file().with_name(f"config.toml.backup-{stamp}")
            shutil.copy2(config_file(), backup)
            write_config(copy.deepcopy(DEFAULT_CONFIG))
            print(f"Configuration reset. Backup: {backup}")
            return 0
    except (ConfigError, OSError) as error:
        print(f"unlaw config: {error}", file=sys.stderr)
        return 2
    print(USAGE, file=sys.stderr)
    return 2
