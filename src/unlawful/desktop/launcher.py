from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from unlawful.config import ConfigError, load_config

APPLICATIONS = {
    "gpt": "ChatGPT",
    "minecraft": "Prism Launcher",
    "netflix": "Netflix",
    "obsidian": "Obsidian",
    "steam": "Steam",
}

URLS = {
    "browser": "https://www.google.com/",
    "lofi": "https://lofi-engine.vercel.app/",
}


def launch(command: str, argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(f"Usage: ul {command}", file=sys.stderr)
        return 2
    try:
        if command == "zed":
            editor = str(load_config()["apps"]["editor"])
            open_args = ["open", "-a", editor, str(Path.cwd())]
        elif command == "lofi":
            url = str(load_config()["apps"]["lofi_url"])
            open_args = ["open", url]
        elif command in APPLICATIONS:
            open_args = ["open", "-a", APPLICATIONS[command]]
        else:
            open_args = ["open", URLS[command]]
        return subprocess.run(open_args, check=False).returncode
    except (ConfigError, OSError) as error:
        print(f"unlaw {command}: {error}", file=sys.stderr)
        return 1
