from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

from unlawful.config import ConfigError, load_config


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("Usage: ul browser", file=sys.stderr)
        return 2
    try:
        url = str(load_config()["apps"]["browser_url"])
        return subprocess.run(["open", url], check=False).returncode
    except (ConfigError, OSError) as error:
        print(f"unlaw browser: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
