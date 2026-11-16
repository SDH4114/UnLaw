from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from unlawful.command_help import COMMAND_HELP
from unlawful.config import ConfigError, load_config


# apps.editor = "auto": the first of these that `open -a` finds, else Finder.
AUTO_EDITORS = ("Zed", "Visual Studio Code", "Cursor", "Sublime Text")


def _open_in_editor(editor: str, folder: str) -> int:
    if editor.strip() and editor != "auto":
        return subprocess.run(["open", "-a", editor, folder], check=False).returncode
    for name in AUTO_EDITORS:
        # `open -a` fails at once (exit 1, a message on stderr) when the app is not installed.
        if subprocess.run(["open", "-a", name, folder], check=False, stderr=subprocess.DEVNULL).returncode == 0:
            return 0
    return subprocess.run(["open", folder], check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP['work'], end="")
        return 0
    if args:
        print("Usage: ul work", file=sys.stderr)
        return 2
    try:
        settings = load_config()["apps"]
        browser = subprocess.run(["open", str(settings["lofi_url"])], check=False)
        if browser.returncode != 0:
            return browser.returncode
        return _open_in_editor(str(settings["editor"]), str(Path.cwd()))
    except (ConfigError, OSError) as error:
        print(f"unlaw work: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
