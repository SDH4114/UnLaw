# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open a macOS application by name."""
from __future__ import annotations

COMMAND_HELP = 'Open a macOS application by name.\nUsage: ul app <application>\nExample: ul app "Visual Studio Code"\n'

import subprocess
import sys
from collections.abc import Sequence



def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
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
