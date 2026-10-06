from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from unlawful.command_help import COMMAND_HELP
from unlawful.config import ConfigError, load_config


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP['zed'], end="")
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
