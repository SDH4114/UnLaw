from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import quote

from unlawful.config import ConfigError, load_config


def _apple_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        settings = load_config()["apps"]
    except ConfigError as error:
        print(f"unlaw music: {error}", file=sys.stderr)
        return 2
    application = str(settings["spotify"])
    if not args:
        return subprocess.run(["open", "-a", application], check=False).returncode
    query = " ".join(args).strip()
    if not query:
        print("Usage: ul music [track]", file=sys.stderr)
        return 2
    uri = f"spotify:search:{quote(query)}"
    script = f'''set searchQuery to "{_apple_string(query)}"
tell application "{_apple_string(application)}"
    activate
    open location "{_apple_string(uri)}"
end tell
delay {float(settings["spotify_autoplay_delay"]):g}
tell application "System Events"
    tell process "{_apple_string(application)}"
        key code 48
        key code 36
    end tell
end tell'''
    try:
        result = subprocess.run(["osascript", "-e", script], check=False)
    except OSError as error:
        print(f"unlaw music: {error}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print("unlaw music: allow Accessibility control for your terminal to auto-play results.", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
