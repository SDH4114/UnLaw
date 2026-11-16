from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import quote

from unlawful.command_help import COMMAND_HELP
from unlawful.config import ConfigError, load_config


WEB_PLAYER = "https://open.spotify.com/"


def _apple_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP['music'], end="")
        return 0
    try:
        settings = load_config()["apps"]
    except ConfigError as error:
        print(f"unlaw music: {error}", file=sys.stderr)
        return 2
    application = str(settings["spotify"])
    query = " ".join(args).strip()
    if args and not query:
        print("Usage: ul music [track]", file=sys.stderr)
        return 2
    try:
        # `open -a` fails at once when the app is not installed; then the web player opens instead.
        opened = subprocess.run(["open", "-a", application], check=False, stderr=subprocess.DEVNULL).returncode == 0
        if not opened:
            url = WEB_PLAYER + (f"search/{quote(query, safe='')}" if query else "")
            return subprocess.run(["open", url], check=False).returncode
    except OSError as error:
        print(f"unlaw music: {error}", file=sys.stderr)
        return 1
    if not query:
        return 0
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
