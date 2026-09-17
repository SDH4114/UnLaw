from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("Usage: ul obsidian", file=sys.stderr)
        return 2
    try:
        return subprocess.run(["open", "-a", "Obsidian"], check=False).returncode
    except OSError as error:
        print(f"unlaw obsidian: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
