from __future__ import annotations

import sys
from collections.abc import Sequence

from unlawful import harness

HELP = """Usage:
  ul mac see <application>
  ul mac key <application> <shortcut>
  ul mac type <application> <text>
  ul mac click <application> <x> <y>
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP, end="")
        return 0 if args else 2
    action = args[0]
    if action == "see" and len(args) >= 2:
        return harness.see(" ".join(args[1:]))
    if action == "key" and len(args) == 3:
        return harness.key(args[1], args[2])
    if action == "type" and len(args) >= 3:
        return harness.type_text(args[1], " ".join(args[2:]))
    if action == "click" and len(args) == 4:
        try:
            return harness.click(args[1], float(args[2]), float(args[3]))
        except ValueError:
            pass
    print(HELP, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
