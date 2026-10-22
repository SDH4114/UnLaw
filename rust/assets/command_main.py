"""Custom Unlaw command."""
# The first docstring line is the description shown by `ul commands --describe`
# and Zsh completion. Unlaw passes these environment variables to every command:
#   UNLAW_COMMAND      command name, e.g. "hello"
#   UNLAW_COMMAND_DIR  this command's folder
#   UNLAW_CONFIG_DIR   Unlaw configuration folder (config.toml lives here)
#   UNLAW_STORAGE      resolved storage.root folder for files your command saves
from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        name = Path(__file__).parent.name
        print(f"Custom Unlaw command.\nUsage: ul {name} [arguments]\nExample: ul {name} hello\nOptions: -h, --help show this help.")
        return 0
    print("Command arguments:", *args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
