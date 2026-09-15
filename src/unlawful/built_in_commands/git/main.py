from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

from unlawful.config import ConfigError, load_config

USAGE = "Usage: ul git [message|status|pull|push|commit [message]|sync [message]]"


def _run_all(commands: list[list[str]]) -> int:
    try:
        for command in commands:
            code = subprocess.run(command, check=False).returncode
            if code:
                return code
    except OSError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 1
    return 0


def _commit(message: list[str]) -> list[list[str]]:
    command = ["git", "commit", "-m", " ".join(message)] if message else ["git", "commit"]
    return [["git", "add", "."], command]


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0
    if args and args[0] in {"status", "pull", "push"}:
        if len(args) != 1:
            print(USAGE, file=sys.stderr)
            return 2
        return _run_all([["git", args[0]]])
    if args and args[0] == "commit":
        return _run_all(_commit(args[1:]))
    if args and args[0] == "sync":
        return _run_all([["git", "pull", "--rebase"], *_commit(args[1:]), ["git", "push"]])

    try:
        auto_push = load_config()["git"]["auto_push"]
    except ConfigError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 2
    commands = _commit(args)
    if auto_push:
        commands.append(["git", "push"])
    return _run_all(commands)


if __name__ == "__main__":
    raise SystemExit(main())
