from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: ul app <application>", file=sys.stderr)
        return 2
    app = " ".join(args)
    try:
        return subprocess.run(["open", "-a", app], check=False).returncode
    except OSError as error:
        print(f"unlaw app: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

