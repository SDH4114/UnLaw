from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from unlawful.command_help import COMMAND_HELP
from .config import ConfigError, load_config
from .kanban import TASK, KanbanBoard, complete_task, completed_section, configured_board, write_board

USAGE = "Usage: ul todo [open|path|search <text>|add <text> [--column <name>]|move <id> <column>|done <id>]"


def todo_path() -> Path:
    return configured_board(load_config()["todo"])


def _read() -> tuple[Path, KanbanBoard]:
    path = todo_path()
    if not path.is_file():
        raise FileNotFoundError(f"Kanban file not found: {path}")
    return path, KanbanBoard.parse(path.read_text(encoding="utf-8"))


def _write(path: Path, board: KanbanBoard) -> None:
    write_board(path, board)


def _print_tasks(board: KanbanBoard, query: str | None = None) -> int:
    found = 0
    previous: str | None = None
    for number, section, task in board.numbered_tasks():
        full = "\n".join(task)
        if query is not None and query.casefold() not in full.casefold():
            continue
        if found == 0 or previous != section.name:
            if found:
                print()
            print(section.name)
        match = TASK.match(task[0])
        marker, title = (match.group(1), match.group(2)) if match else (" ", task[0])
        print(f"  {number}. [{'x' if marker.casefold() == 'x' else ' '}] {title}")
        for detail in task[1:]:
            print(f"     {detail.strip()}")
        previous = section.name
        found += 1
    if not found:
        print("No matching tasks." if query else "No tasks.")
        return 1 if query else 0
    return 0


def _parse_add(args: list[str]) -> tuple[str, str]:
    column = "To do"
    if "--column" in args:
        position = args.index("--column")
        if position + 1 >= len(args) or position + 2 != len(args):
            raise ValueError("--column requires one quoted column name at the end")
        column = args[position + 1]
        args = args[:position]
    text = " ".join(args).strip()
    if not text:
        raise ValueError("Task text cannot be empty")
    return text, column


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP['todo'], end="")
        return 0
    try:
        path, board = _read()
        if not args:
            return _print_tasks(board)
        action, rest = args[0], args[1:]
        if action in {"-h", "--help", "help"}:
            print(USAGE)
            return 0
        if action == "path" and not rest:
            print(path)
            return 0
        if action == "open" and not rest:
            return subprocess.run(["open", "-a", "Obsidian", str(path)], check=False).returncode
        if action == "search" and rest:
            return _print_tasks(board, " ".join(rest))
        if action == "add":
            text, column = _parse_add(rest)
            board.section(column).tasks.append([f"- [ ] {text}"])
            _write(path, board)
            print(f"Added to {column}: {text}")
            return 0
        if action == "move" and len(rest) >= 2:
            number = int(rest[0])
            target_name = " ".join(rest[1:])
            source, task = board.pop_task(number)
            target = board.section(target_name)
            target.tasks.append(task)
            _write(path, board)
            print(f"Moved #{number}: {source.name} -> {target.name}")
            return 0
        if action == "done" and len(rest) == 1:
            number = int(rest[0])
            _, task = board.pop_task(number)
            if TASK.match(task[0]) is None:
                raise ValueError(f"Task #{number} is malformed")
            title = complete_task(task, datetime.now().astimezone().date())
            completed_section(board, load_config()["todo"]["completed_column"]).tasks.append(task)
            _write(path, board)
            print(f"Completed #{number}: {title}")
            return 0
    except (ConfigError, FileNotFoundError, OSError, ValueError) as error:
        print(f"unlaw todo: {error}", file=sys.stderr)
        return 2
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
