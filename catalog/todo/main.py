# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Read and update the configured Obsidian TODO board."""
from __future__ import annotations

COMMAND_HELP = 'Read and update the configured Obsidian TODO board.\nUsage: ul todo [open|path|search <text>|add <text> [--column <name>]|move <id> <column>|done <id>]\nActions:\n  no arguments   List tasks with numeric IDs\n  open / path    Open the board in Obsidian / print its path\n  search <text>  Find matching tasks\n  add <text>     Add a task; --column selects its section\n  move <id> <column> Move a task to another section\n  done <id>      Mark complete and move to todo.completed_column\nSettings: todo.vault_path, todo.file, todo.completed_column.\nExample: ul todo add "Study Python" --column "To do"\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'todo': {'vault_path': '~/aiwork/data-obsidian',
          'file': 'TODO.md',
          'completed_column': 'Completed'}}


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

"""Obsidian Kanban boards (`## Column` + `- [ ] task`), shared by `ul todo` and `ul desk`.

Seeded into both commands' sources, so each stays standalone.
"""


import hashlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

TASK = re.compile(r"^- \[([ xX])\] (.+)$")
HEADING = re.compile(r"^## (.+?)\s*$")
KANBAN_MARKER = "%% kanban:settings"
DONE_COLUMNS = {"done", "completed", "finished", "готово", "сделано", "выполнено"}
TAG = re.compile(r"(?<![\w&/])#([^\s#\[\]{}(),.;:!?'\"]+)")
DUE = re.compile(r"@\{(\d{4}-\d{2}-\d{2})\}|📅\s*(\d{4}-\d{2}-\d{2})")
LINK = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
COMPLETION = re.compile(r"\s*\[completion::\s*(\d{4}-\d{2}-\d{2})\]")
NEW_BOARD = '---\n\nkanban-plugin: board\n\n---\n\n## To do\n\n## Doing\n\n## Done\n\n%% kanban:settings\n```\n{"kanban-plugin":"board"}\n```\n%%\n'


@dataclass
class Section:
    name: str
    preamble: list[str] = field(default_factory=list)
    tasks: list[list[str]] = field(default_factory=list)


@dataclass
class KanbanBoard:
    prefix: list[str]
    sections: list[Section]
    footer: list[str]

    @classmethod
    def parse(cls, text: str) -> KanbanBoard:
        lines = text.splitlines()
        footer_at = next(
            (i for i, line in enumerate(lines) if line.strip() == KANBAN_MARKER),
            len(lines),
        )
        body, footer = lines[:footer_at], lines[footer_at:]
        heading_positions = [
            (i, match.group(1))
            for i, line in enumerate(body)
            if (match := HEADING.match(line))
        ]
        if not heading_positions:
            raise ValueError("TODO.md has no '##' Kanban columns")
        prefix = body[: heading_positions[0][0]]
        sections: list[Section] = []
        for position, (start, name) in enumerate(heading_positions):
            end = (
                heading_positions[position + 1][0]
                if position + 1 < len(heading_positions)
                else len(body)
            )
            content = body[start + 1 : end]
            starts = [i for i, line in enumerate(content) if TASK.match(line)]
            if not starts:
                sections.append(Section(name=name, preamble=_trim_blank(content)))
                continue
            preamble = _trim_blank(content[: starts[0]])
            tasks = []
            for index, task_start in enumerate(starts):
                task_end = (
                    starts[index + 1] if index + 1 < len(starts) else len(content)
                )
                tasks.append(_trim_blank(content[task_start:task_end]))
            sections.append(Section(name=name, preamble=preamble, tasks=tasks))
        return cls(
            prefix=_trim_blank_right(prefix),
            sections=sections,
            footer=_trim_blank(footer),
        )

    def section(self, name: str) -> Section:
        exact = next(
            (section for section in self.sections if section.name == name), None
        )
        if exact:
            return exact
        folded = next(
            (
                section
                for section in self.sections
                if section.name.casefold() == name.casefold()
            ),
            None,
        )
        if folded:
            return folded
        available = ", ".join(section.name for section in self.sections)
        raise ValueError(f"Unknown column '{name}'. Available: {available}")

    def numbered_tasks(self) -> list[tuple[int, Section, list[str]]]:
        result: list[tuple[int, Section, list[str]]] = []
        number = 1
        for section in self.sections:
            for task in section.tasks:
                result.append((number, section, task))
                number += 1
        return result

    def pop_task(self, number: int) -> tuple[Section, list[str]]:
        for current, section, task in self.numbered_tasks():
            if current == number:
                section.tasks.remove(task)
                return section, task
        raise ValueError(f"Task #{number} does not exist")

    def render(self) -> str:
        lines = list(self.prefix)
        if lines:
            lines.append("")
        for section in self.sections:
            lines.append(f"## {section.name}")
            lines.append("")
            if section.preamble:
                lines.extend(section.preamble)
                lines.append("")
            for task in section.tasks:
                lines.extend(task)
            lines.append("")
        if self.footer:
            lines.extend(self.footer)
        return "\n".join(lines).rstrip() + "\n"


def configured_board(settings: dict) -> Path:
    """The `ul todo` board: todo.file inside todo.vault_path."""
    vault = Path(str(settings["vault_path"])).expanduser()
    candidate = (vault / str(settings["file"])).resolve()
    try:
        candidate.relative_to(vault.resolve())
    except ValueError as error:
        raise ValueError("todo.file must stay inside todo.vault_path") from error
    return candidate


def completed_section(board: KanbanBoard, configured: str) -> Section:
    """todo.completed_column, or the board's own Done-like column when that one is missing."""
    try:
        return board.section(configured)
    except ValueError:
        for section in board.sections:
            if section.name.casefold() in DONE_COLUMNS:
                return section
        raise


def complete_task(task: list[str], today: date) -> str:
    """Check a task and stamp its completion date; returns its title."""
    match = TASK.match(task[0])
    if match is None:
        raise ValueError("The task is malformed")
    title = match.group(2)
    if "[completion::" not in title:
        title += f"  [completion:: {today.isoformat()}]"
    task[0] = f"- [x] {title}"
    return match.group(2)


def reopen_task(task: list[str]) -> None:
    match = TASK.match(task[0])
    if match is None:
        raise ValueError("The task is malformed")
    task[0] = f"- [ ] {COMPLETION.sub('', match.group(2)).rstrip()}"


def _trim_blank(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _trim_blank_right(lines: list[str]) -> list[str]:
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    return lines[:end]


def write_board(path: Path, board: KanbanBoard) -> None:
    """Replace the board file atomically (a temporary file next to it, then rename)."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".todo.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(board.render())
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def version_of(data: bytes) -> str:
    """A short content hash: the board's version for conflict checks and ETags."""
    return hashlib.sha256(data).hexdigest()[:16]


def card(task: list[str]) -> dict:
    """A task as JSON for `ul desk`: title, checkbox, details, tags, due date, links, completion."""
    match = TASK.match(task[0])
    checked, title = (
        (match.group(1).casefold() == "x", match.group(2))
        if match
        else (False, task[0])
    )
    due = DUE.search(title)
    completed = COMPLETION.search(title)
    return {
        "line": task[0],
        "title": title,
        "checked": checked,
        "details": [line.strip() for line in task[1:]],
        "tags": sorted({tag.casefold() for tag in TAG.findall(title)}),
        "due": (due.group(1) or due.group(2)) if due else None,
        "links": LINK.findall(title),
        "completed": completed.group(1) if completed else None,
    }


QUICK_DATES = {"today": 0, "сегодня": 0, "tomorrow": 1, "завтра": 1}


def quick_text(text: str, today: date) -> str:
    """Quick-add shortcuts: `@today`/`@сегодня`, `@tomorrow`/`@завтра`, `@2026-11-01`, `@+3` become `@{date}`."""

    def replace(match: re.Match[str]) -> str:
        word = match.group(1)
        if word.casefold() in QUICK_DATES:
            return (
                "@{"
                + (today + timedelta(days=QUICK_DATES[word.casefold()])).isoformat()
                + "}"
            )
        if word.startswith("+") and word[1:].isdigit():
            return "@{" + (today + timedelta(days=int(word[1:]))).isoformat() + "}"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", word):
            try:
                return "@{" + date.fromisoformat(word).isoformat() + "}"
            except ValueError:
                pass
        return match.group(0)

    return re.sub(r"(?<![\w{])@([^\s{}]+)", replace, text).strip()

import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path


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
        print(COMMAND_HELP, end="")
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
