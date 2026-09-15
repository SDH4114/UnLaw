from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import ConfigError, load_config

TASK = re.compile(r"^- \[([ xX])\] (.+)$")
HEADING = re.compile(r"^## (.+?)\s*$")
KANBAN_MARKER = "%% kanban:settings"
USAGE = "Usage: ul todo [open|path|search <text>|add <text> [--column <name>]|move <id> <column>|done <id>]"


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
        footer_at = next((i for i, line in enumerate(lines) if line.strip() == KANBAN_MARKER), len(lines))
        body, footer = lines[:footer_at], lines[footer_at:]
        heading_positions = [(i, match.group(1)) for i, line in enumerate(body) if (match := HEADING.match(line))]
        if not heading_positions:
            raise ValueError("TODO.md has no '##' Kanban columns")
        prefix = body[: heading_positions[0][0]]
        sections: list[Section] = []
        for position, (start, name) in enumerate(heading_positions):
            end = heading_positions[position + 1][0] if position + 1 < len(heading_positions) else len(body)
            content = body[start + 1 : end]
            starts = [i for i, line in enumerate(content) if TASK.match(line)]
            if not starts:
                sections.append(Section(name=name, preamble=_trim_blank(content)))
                continue
            preamble = _trim_blank(content[: starts[0]])
            tasks = []
            for index, task_start in enumerate(starts):
                task_end = starts[index + 1] if index + 1 < len(starts) else len(content)
                tasks.append(_trim_blank(content[task_start:task_end]))
            sections.append(Section(name=name, preamble=preamble, tasks=tasks))
        return cls(prefix=_trim_blank_right(prefix), sections=sections, footer=_trim_blank(footer))

    def section(self, name: str) -> Section:
        exact = next((section for section in self.sections if section.name == name), None)
        if exact:
            return exact
        folded = next((section for section in self.sections if section.name.casefold() == name.casefold()), None)
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


def todo_path() -> Path:
    settings = load_config()["todo"]
    vault = Path(settings["vault_path"]).expanduser()
    candidate = (vault / settings["file"]).resolve()
    try:
        candidate.relative_to(vault.resolve())
    except ValueError as error:
        raise ValueError("todo.file must stay inside todo.vault_path") from error
    return candidate


def _read() -> tuple[Path, KanbanBoard]:
    path = todo_path()
    if not path.is_file():
        raise FileNotFoundError(f"Kanban file not found: {path}")
    return path, KanbanBoard.parse(path.read_text(encoding="utf-8"))


def _write(path: Path, board: KanbanBoard) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".todo.", suffix=".tmp", delete=False
        ) as handle:
            handle.write(board.render())
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


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
            match = TASK.match(task[0])
            if match is None:
                raise ValueError(f"Task #{number} is malformed")
            title = match.group(2)
            if "[completion::" not in title:
                title += f"  [completion:: {datetime.now().astimezone().date().isoformat()}]"
            task[0] = f"- [x] {title}"
            completed = load_config()["todo"]["completed_column"]
            board.section(completed).tasks.append(task)
            _write(path, board)
            print(f"Completed #{number}: {match.group(2)}")
            return 0
    except (ConfigError, FileNotFoundError, OSError, ValueError) as error:
        print(f"unlaw todo: {error}", file=sys.stderr)
        return 2
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
