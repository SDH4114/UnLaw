from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from unlawful.config import ConfigError, load_config


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("Usage: ul work", file=sys.stderr)
        return 2
    try:
        settings = load_config()["apps"]
        browser = subprocess.run(["open", str(settings["lofi_url"])], check=False)
        if browser.returncode != 0:
            return browser.returncode
        return subprocess.run(["open", "-a", str(settings["editor"]), str(Path.cwd())], check=False).returncode
    except (ConfigError, OSError) as error:
        print(f"unlaw work: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
