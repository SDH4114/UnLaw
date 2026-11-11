# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open the Claude macOS application."""
from __future__ import annotations

COMMAND_HELP = 'Open the Claude macOS application.\nUsage: ul claude\nExample: ul claude\n'

import subprocess
import sys
from collections.abc import Sequence



def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    if args:
        print("Usage: ul claude", file=sys.stderr)
        return 2
    try:
        return subprocess.run(["open", "-a", "Claude"], check=False).returncode
    except OSError as error:
        print(f"unlaw claude: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
