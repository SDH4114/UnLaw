# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Computer stats: CPU, GPU, RAM, disk, battery and charge cycles."""
from __future__ import annotations

COMMAND_HELP = 'Computer stats: CPU, GPU, RAM, disk, battery and charge cycles.\nUsage: ul sys\nExample: ul sys\n'

import sys
from collections.abc import Sequence



def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    print("unlaw sys: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
