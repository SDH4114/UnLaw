# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open Spotify, or search for a track and attempt to play it."""
from __future__ import annotations

COMMAND_HELP = 'Open Spotify, or search for a track and attempt to play it.\nUsage: ul music [track]\nSettings: apps.spotify, apps.spotify_autoplay_delay.\nAutoplay requires Accessibility permission for your terminal.\nExample: ul music "Nujabes Feather"\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'apps': {'spotify': 'Spotify', 'spotify_autoplay_delay': 2.0}}


class ConfigError(ValueError):
    pass


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "unlaw"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = (
            _deep_merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else copy.deepcopy(value)
        )
    return result


def load_config() -> dict:
    path = config_dir() / "config.toml"
    try:
        with path.open("rb") as handle:
            configured = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read {path}: {error}") from error
    return _deep_merge(DEFAULT_CONFIG, configured)

import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import quote



def _apple_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
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
