from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    print("Command arguments:", *args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
