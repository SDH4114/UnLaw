from __future__ import annotations

import difflib
import sys
from collections.abc import Sequence

from . import __version__
from .config import ConfigError, ensure_layout, load_config
from .config_commands import config_command
from .runner import discover_commands, run_command
from .system_commands import (
    SYSTEM_COMMAND_NAMES,
    completion_command,
    create_command,
    doctor,
    init_command,
    list_commands,
    version_command,
    which_command,
)

SYSTEM_COMMANDS = {
    "commands": list_commands,
    "completion": completion_command,
    "config": config_command,
    "create": create_command,
    "doctor": doctor,
    "init": init_command,
    "version": version_command,
    "which": which_command,
}
RAW_SYSTEM_COMMANDS = {"completion", "config", "doctor", "init", "version"}

HELP = """Usage: ul [global-options] <command> [arguments]

Global options:
  --dry-run     Show the resolved command without running it
  --verbose     Show command source, invocation, and timing
  --no-color    Disable colored output
  --version     Show the installed version

Run `ul commands` to list available commands.
Run `ul create command <name>` to create one.
Run `ul config show` to inspect configuration.
"""


class AliasError(ValueError):
    pass


def expand_alias(argv: Sequence[str], aliases: dict[str, list[str]]) -> list[str]:
    expanded = list(argv)
    visited: list[str] = []
    while expanded and expanded[0] in aliases:
        name = expanded[0]
        if name in visited:
            cycle = " -> ".join([*visited, name])
            raise AliasError(f"Alias cycle: {cycle}")
        visited.append(name)
        expanded = [*aliases[name], *expanded[1:]]
    return expanded


def _global_options(argv: list[str]) -> tuple[dict[str, bool], list[str]]:
    options = {"dry_run": False, "verbose": False, "no_color": False}
    while argv and argv[0] in {"--dry-run", "--verbose", "--no-color"}:
        flag = argv.pop(0).removeprefix("--").replace("-", "_")
        options[flag] = True
    return options, argv


def _unknown(name: str, aliases: dict[str, list[str]]) -> int:
    available = sorted(SYSTEM_COMMAND_NAMES | discover_commands().keys() | aliases.keys())
    suggestions = difflib.get_close_matches(name, available, n=3, cutoff=0.55)
    print(f"unlaw: Unknown command: {name}", file=sys.stderr)
    if suggestions:
        print(f"Did you mean: {', '.join(suggestions)}?", file=sys.stderr)
    else:
        print("Run `ul commands` to see available commands.", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        ensure_layout()
    except OSError as error:
        print(f"unlaw: Could not initialize configuration: {error}", file=sys.stderr)
        return 1

    options, args = _global_options(args)
    if args == ["--version"]:
        print(f"Unlaw {__version__}")
        return 0
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP, end="")
        return 0

    name, command_args = args[0], args[1:]
    if name in RAW_SYSTEM_COMMANDS:
        return SYSTEM_COMMANDS[name](command_args)

    try:
        config = load_config()
        if name in SYSTEM_COMMANDS:
            return SYSTEM_COMMANDS[name](command_args)
        expanded = expand_alias([name, *command_args], config["aliases"])
    except (ConfigError, AliasError) as error:
        print(f"unlaw: {error}", file=sys.stderr)
        return 2

    name, command_args = expanded[0], expanded[1:]
    if name in SYSTEM_COMMANDS:
        return SYSTEM_COMMANDS[name](command_args)
    if name not in discover_commands():
        return _unknown(name, config["aliases"])

    core = config["core"]
    verbose = bool(options["verbose"] or core["verbose"] or core["show_timing"])
    try:
        return run_command(
            name,
            command_args,
            dry_run=options["dry_run"],
            verbose=verbose,
            timeout=core["command_timeout"],
        )
    except OSError as error:
        print(f"unlaw: Could not run {name}: {error}", file=sys.stderr)
        return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
