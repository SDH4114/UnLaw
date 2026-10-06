from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

from unlawful.command_help import COMMAND_HELP


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP['steam'], end="")
        return 0
    if args:
        print("Usage: ul steam", file=sys.stderr)
        return 2
    try:
        return subprocess.run(["open", "-a", "Steam"], check=False).returncode
    except OSError as error:
        print(f"unlaw steam: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
