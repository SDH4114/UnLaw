from __future__ import annotations

import sys
from collections.abc import Sequence

from unlawful.command_help import COMMAND_HELP


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP["timer"], end="")
        return 0
    print("unlaw timer: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
