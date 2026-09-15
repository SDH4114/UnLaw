from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import urlencode

from unlawful.config import ConfigError, load_config


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    query = " ".join(args).strip()
    try:
        homepage = str(load_config()["apps"]["youtube_url"])
        url = homepage if not query else homepage.rstrip("/") + "/results?" + urlencode({"search_query": query})
        return subprocess.run(["open", url], check=False).returncode
    except (ConfigError, OSError) as error:
        print(f"unlaw yt: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
