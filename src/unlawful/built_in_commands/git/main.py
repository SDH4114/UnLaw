from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

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


def _commit_message(tokens: list[str]) -> str | None:
    if tokens:
        return " ".join(tokens).strip()
    try:
        message = input("Commit message: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nunlaw git: commit cancelled.", file=sys.stderr)
        return None
    if not message:
        print("unlaw git: commit message cannot be empty.", file=sys.stderr)
        return None
    return message


def _commit_workflow(tokens: list[str], *, push: bool) -> int:
    code = _run_all([["git", "add", "."]])
    if code:
        return code
    message = _commit_message(tokens)
    if message is None:
        return 2
    commands = [["git", "commit", "-m", message]]
    if push:
        commands.append(["git", "push"])
    return _run_all(commands)


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
        return _commit_workflow(args[1:], push=False)
    if args and args[0] == "sync":
        code = _run_all([["git", "pull", "--rebase"]])
        return code or _commit_workflow(args[1:], push=True)

    return _commit_workflow(args, push=True)


if __name__ == "__main__":
    raise SystemExit(main())
