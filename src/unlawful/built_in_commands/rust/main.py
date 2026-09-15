from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from unlawful.config import ConfigError, load_config
from unlawful.project_templates import apply_template

VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
USAGE = "Usage: ul rust <project-name> [--bin|--lib] [--git]"


def _parse(args: list[str]) -> tuple[str, str, bool] | None:
    if not args or not VALID_NAME.fullmatch(args[0]):
        return None
    kind: str | None = None
    initialize_git = False
    for flag in args[1:]:
        if flag in {"--bin", "--lib"}:
            if kind is not None and flag != kind:
                return None
            kind = flag
        elif flag == "--git":
            initialize_git = True
        else:
            return None
    return args[0], kind or "--bin", initialize_git


def main(argv: Sequence[str] | None = None) -> int:
    parsed = _parse(list(sys.argv[1:] if argv is None else argv))
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    name, kind, git_flag = parsed
    cargo = shutil.which("cargo")
    if cargo is None:
        print("unlaw rust: Cargo is not installed or not on PATH.", file=sys.stderr)
        return 1
    try:
        initialize_git = git_flag or load_config()["projects"]["rust"]["initialize_git"]
    except ConfigError as error:
        print(f"unlaw rust: {error}", file=sys.stderr)
        return 2
    command = [cargo, "new", name, kind]
    if not initialize_git:
        command.extend(["--vcs", "none"])
    try:
        code = subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"unlaw rust: {error}", file=sys.stderr)
        return 1
    if code:
        return code
    apply_template("rust", Path(name), {"project_name": name})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
