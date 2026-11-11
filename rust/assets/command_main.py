"""Custom Unlaw command."""

# The first docstring line is the description shown by `ul commands --describe`
# and Zsh completion: replace "Custom Unlaw command." with what this command does.
# Unlaw passes these environment variables to every command:
#   UNLAW_COMMAND      command name, here "{{command_name}}"
#   UNLAW_COMMAND_DIR  this command's folder (its settings live in config.toml there)
#   UNLAW_CONFIG_DIR   Unlaw configuration folder (Unlaw's own config.toml; never edit it)
#   UNLAW_STORAGE      resolved storage.root; files this command saves go to UNLAW_STORAGE/<name>/
#   UNLAW_BIN          absolute path of the running ul, for calling other commands
# Exit codes: 0 success, 1 failure, 2 wrong usage.
from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

NAME = os.environ.get("UNLAW_COMMAND") or Path(__file__).resolve().parent.name
USAGE = f"Usage: ul {NAME} [arguments]"
HELP = f"""Custom Unlaw command.
{USAGE}
Example: ul {NAME} hello
Options: -h, --help show this help."""


def settings() -> dict:
    """This command's own settings from config.toml next to main.py ({} when there is none)."""
    path = (
        Path(os.environ.get("UNLAW_COMMAND_DIR", Path(__file__).resolve().parent))
        / "config.toml"
    )
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def data_dir() -> Path:
    """The folder for files this command saves, created on first use."""
    path = Path(os.environ["UNLAW_STORAGE"]) / NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # Help comes first and has no side effects.
    if args and args[0] in {"-h", "--help", "help"}:
        print(HELP)
        return 0
    unknown = [arg for arg in args if arg.startswith("-")]
    if unknown:
        print(f"ul {NAME}: unknown option {unknown[0]}\n{USAGE}", file=sys.stderr)
        return 2
    print("Command arguments:", *args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
