# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Kanban board, TODO list and pomodoro timer in the browser, on your Obsidian board file."""
from __future__ import annotations

COMMAND_HELP = 'Kanban board, TODO list and pomodoro timer in the browser, on your Obsidian board file.\nUsage: ul desk [board.md] [--port N] [--no-open]\n       ul desk new <board.md> | path [board.md] | stats [board.md]\n       ul desk pomodoro [status|start [minutes] [--card <text>]|pause|resume|stop|skip]\nActions:\n  no arguments     Serve the todo board (todo.vault_path + todo.file) on 127.0.0.1\n                   and open it in the browser; Ctrl+C stops the server\n  board.md         Serve another Kanban Markdown file instead\n  --port N         Use exactly this port (0 = any free one); default desk.port,\n                   or the next free port after it\n  --no-open        Print the address without opening the browser\n  new <board.md>   Create a board with To do / Doing / Done columns\n  path [board.md]  Print the board\'s path\n  stats [board.md] Focus sessions, finished tasks, streak and busiest cards\n  pomodoro         Show or control the timer from the terminal; the page shows\n                   the same timer, and a macOS notification marks each phase end\nPage: Board (drag cards between columns, double-click to edit), Today (overdue,\n  due today, in progress, next 7 days), Stats. Keys: n new card, / search,\n  space start/pause timer, 1 2 3 views, Esc clear filters.\nCards: #tag filters, @{2026-11-01} due dates (quick add: @today @tomorrow\n  @сегодня @завтра @+3 @2026-11-01), [[note]] opens the note in Obsidian.\n  Done cards move to todo.completed_column (or the board\'s Done column).\nThe file stays the source of truth: ul todo, the agent and Obsidian see every\n  change, and edits made elsewhere appear on the page within two seconds.\nSecurity: listens on 127.0.0.1 only and needs the random token in the printed\n  address; it reads and writes only the open board and storage.root/desk.\nSettings: desk.port (8765), desk.open_browser (true), desk.sound (true),\n  desk.pomodoro.work (25), short_break (5), long_break (15), cycles (4) in minutes;\n  todo.vault_path, todo.file, todo.completed_column, apps.lofi_url.\nStorage: storage.root/desk (timer state, pomodoro.jsonl log, recent boards).\nDependencies: Python standard library; osascript for notifications.\nExamples: ul desk\n          ul desk ~/notes/Project.md --no-open\n          ul desk pomodoro start 50 --card "Write chapter 3"\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'},
 'todo': {'vault_path': '~/aiwork/data-obsidian',
          'file': 'TODO.md',
          'completed_column': 'Completed'},
 'desk': {'port': 8765,
          'open_browser': True,
          'sound': True,
          'pomodoro': {'work': 25, 'short_break': 5, 'long_break': 15, 'cycles': 4}},
 'apps': {'lofi_url': 'https://lofi-engine.vercel.app/'}}


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

def storage_path(*parts: str) -> Path:
    configured = Path(str(load_config()["storage"]["root"])).expanduser()
    root = configured if configured.is_absolute() else config_dir() / configured
    return root.joinpath(*parts)

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

"""The `ul desk` page: one HTML document with inline CSS and JS, served by desk.py.

Board text is user data, so the script builds every node with textContent and never uses innerHTML.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Desk</title>
<style>
:root {
  --bg: #f6f5f2; --panel: #ffffff; --column: #ecebe7; --text: #1d1d1f; --muted: #6e6e73;
  --line: #dcdad4; --accent: #3a6df0; --accent-soft: #e3eafd; --danger: #d4483b; --ok: #2f9e5b;
  --warn: #c98a12; --shadow: 0 1px 2px rgba(0,0,0,.06), 0 2px 8px rgba(0,0,0,.05);
  --radius: 10px; --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  --mono: "SF Mono", ui-monospace, Menlo, monospace;
  color-scheme: light;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #161618; --panel: #222225; --column: #1c1c1f; --text: #ececee; --muted: #9a9aa1;
  --line: #303034; --accent: #6b93ff; --accent-soft: #2a3352; --danger: #ff6b5e; --ok: #4fc581;
  --warn: #f0b443; --shadow: 0 1px 2px rgba(0,0,0,.4), 0 2px 10px rgba(0,0,0,.25);
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--text); font: 14px/1.45 var(--font); display: flex; flex-direction: column; }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 5px 10px; }
button:hover { border-color: var(--accent); }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
button.ghost { border-color: transparent; background: transparent; }
button.ghost:hover { background: var(--column); border-color: transparent; }
input, select { border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 5px 9px; outline: none; }
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
header { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; }
.brand { font-weight: 650; letter-spacing: -.01em; margin-right: 4px; }
#boards { max-width: 240px; }
.tabs { display: flex; gap: 2px; background: var(--column); border-radius: 9px; padding: 2px; }
.tabs button { border: none; background: transparent; padding: 4px 12px; border-radius: 7px; }
.tabs button.on { background: var(--panel); box-shadow: var(--shadow); }
#search { width: 200px; }
.spacer { flex: 1; }
#filter { display: none; }
#filter.on { display: inline-flex; }
.timer { display: flex; align-items: center; gap: 8px; padding: 3px 4px 3px 10px; border: 1px solid var(--line); border-radius: 999px; }
.timer .phase { font-size: 12px; color: var(--muted); }
.timer .clock { font: 600 15px var(--mono); min-width: 48px; text-align: right; }
.timer.work .clock { color: var(--danger); }
.timer.short .clock, .timer.long .clock { color: var(--ok); }
.timer .bar { width: 70px; height: 4px; background: var(--column); border-radius: 2px; overflow: hidden; }
.timer .bar i { display: block; height: 100%; background: currentColor; width: 0; transition: width .5s linear; }
.timer .linked { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--muted); }
.timer button { padding: 2px 9px; border-radius: 999px; }
main { flex: 1; overflow: auto; }
.board { display: flex; gap: 12px; padding: 16px; align-items: flex-start; min-height: 100%; }
.column { background: var(--column); border-radius: var(--radius); width: 290px; flex: 0 0 290px; display: flex; flex-direction: column; max-height: calc(100vh - 100px); }
.column.drop { outline: 2px dashed var(--accent); outline-offset: -2px; }
.column h2 { font-size: 13px; font-weight: 650; margin: 0; padding: 10px 12px 6px; display: flex; gap: 6px; align-items: center; }
.column h2 .count { color: var(--muted); font-weight: 500; }
.column.doing h2::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
.column.done h2::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--ok); }
.cards { padding: 4px 8px; overflow-y: auto; flex: 1; min-height: 20px; }
.card { background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); padding: 8px 10px; margin-bottom: 7px; display: flex; gap: 8px; align-items: flex-start; cursor: grab; position: relative; border: 1px solid transparent; }
.card:hover { border-color: var(--line); }
.card.dragging { opacity: .4; }
.card.focus { border-color: var(--danger); }
.card.checked .text { color: var(--muted); text-decoration: line-through; }
.card .check { width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid var(--muted); flex: 0 0 16px; margin-top: 2px; padding: 0; background: transparent; }
.card .check:hover { border-color: var(--ok); background: var(--accent-soft); }
.card.checked .check { background: var(--ok); border-color: var(--ok); }
.card .body { flex: 1; min-width: 0; word-wrap: break-word; }
.card .meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.card .details { margin-top: 4px; color: var(--muted); font-size: 12px; white-space: pre-wrap; }
.card .actions { display: none; gap: 2px; position: absolute; right: 6px; top: 5px; background: var(--panel); border-radius: 6px; }
.card:hover .actions { display: flex; }
.card .actions button { padding: 1px 6px; font-size: 12px; border: none; }
.card .actions button:hover { background: var(--column); }
.card input.edit { width: 100%; }
.chip { display: inline-block; font-size: 11px; padding: 0 7px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); cursor: pointer; border: none; line-height: 18px; }
.chip.due { background: var(--column); color: var(--muted); cursor: default; }
.chip.today { background: #fdf0d5; color: #8a5d00; }
.chip.late { background: #fde2df; color: #a8291d; }
:root[data-theme="dark"] .chip.today { background: #4a3a14; color: #f5cf7a; }
:root[data-theme="dark"] .chip.late { background: #4d1f1b; color: #ff9d93; }
.link { color: var(--accent); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.add { padding: 6px 8px 10px; }
.add input { width: 100%; background: transparent; border-style: dashed; }
.add input:focus { background: var(--panel); border-style: solid; }
.newcol { flex: 0 0 200px; }
.newcol input { width: 100%; }
.page { max-width: 760px; margin: 0 auto; padding: 24px 16px 60px; }
.page h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 26px 0 8px; }
.page .quick { display: flex; gap: 8px; }
.page .quick input { flex: 1; padding: 9px 12px; }
.page .card { cursor: default; }
.page .where { font-size: 11px; color: var(--muted); }
.empty { color: var(--muted); padding: 8px 2px; }
.numbers { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.number { background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px; }
.number b { display: block; font-size: 26px; font-weight: 650; letter-spacing: -.02em; }
.number span { color: var(--muted); font-size: 12px; }
.week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; align-items: end; height: 160px; background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px; }
.day { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 4px; font-size: 11px; color: var(--muted); }
.day .bars { display: flex; gap: 3px; align-items: flex-end; flex: 1; }
.day .bars i { display: block; width: 12px; border-radius: 3px 3px 0 0; min-height: 2px; }
.day .bars i.f { background: var(--danger); }
.day .bars i.d { background: var(--ok); }
.legend { display: flex; gap: 14px; font-size: 12px; color: var(--muted); margin-top: 6px; }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; }
.top { background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 6px 14px; }
.top div { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--line); }
.top div:last-child { border-bottom: none; }
#toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); background: var(--text); color: var(--bg); padding: 8px 14px; border-radius: 8px; opacity: 0; transition: opacity .2s; pointer-events: none; max-width: 80vw; }
#toast.on { opacity: .95; }
.keys { color: var(--muted); font-size: 12px; padding: 0 16px 10px; }
kbd { font: 11px var(--mono); border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; background: var(--panel); }
</style>
</head>
<body>
<header>
  <span class="brand">Desk</span>
  <select id="boards" title="Boards"></select>
  <div class="tabs" id="tabs">
    <button data-view="board" class="on">Board</button>
    <button data-view="today">Today</button>
    <button data-view="stats">Stats</button>
  </div>
  <input id="search" type="search" placeholder="Search  /">
  <button id="filter" class="chip" title="Clear tag filter"></button>
  <span class="spacer"></span>
  <div class="timer" id="timer">
    <span class="phase" id="phase">Ready</span>
    <span class="bar"><i id="progress"></i></span>
    <span class="clock" id="clock">25:00</span>
    <span class="linked" id="linked"></span>
    <button id="play" title="Start / pause (space)">Start</button>
    <button id="skip" class="ghost" title="Skip to the next phase">Skip</button>
    <button id="stop" class="ghost" title="Stop">Stop</button>
  </div>
  <button id="obsidian" class="ghost" title="Open this board in Obsidian">Obsidian</button>
  <button id="lofi" class="ghost" title="Open lofi music">Lofi</button>
  <button id="theme" class="ghost" title="Light / dark">Theme</button>
</header>
<main id="main"></main>
<div class="keys"><kbd>n</kbd> new card · <kbd>/</kbd> search · <kbd>space</kbd> timer · <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> views · <kbd>Esc</kbd> clear · drag cards between columns</div>
<div id="toast"></div>
<script>
"use strict";
const params = new URLSearchParams(location.search);
if (params.get("token")) {
  sessionStorage.setItem("desk-token", params.get("token"));
  history.replaceState(null, "", location.pathname + location.hash);
}
const TOKEN = sessionStorage.getItem("desk-token") || "";
const state = { board: null, view: ["board", "today", "stats"].includes(location.hash.slice(1)) ? location.hash.slice(1) : localStorage.getItem("desk-view") || "board", query: "", tag: "", timer: null, timerAt: 0, editing: null, dragging: null, stats: null };
const $ = (id) => document.getElementById(id);

function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

let toastTimer = 0;
function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("on"), 2600);
}

async function api(method, path, body, headers) {
  const response = await fetch(path, {
    method,
    headers: { "X-Desk-Token": TOKEN, "Content-Type": "application/json", ...(headers || {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status === 304) return { status: 304 };
  let data = {};
  try { data = await response.json(); } catch (error) { data = {}; }
  return { status: response.status, data };
}

// ---- board ----
async function loadBoard(force) {
  const headers = !force && state.board ? { "If-None-Match": state.board.version } : {};
  const { status, data } = await api("GET", "/api/board", undefined, headers);
  if (status === 304) return;
  if (status !== 200) { toast(data.error || "Could not read the board"); return; }
  setBoard(data);
}

function setBoard(board) {
  state.board = board;
  document.title = board.name + " · Desk";
  if (!state.editing) render();
}

function findCard(board, line, hint) {
  for (const [c, column] of board.columns.entries()) {
    for (const [i, card] of column.cards.entries()) {
      if (card.line === line && (hint === undefined || c === hint)) return { column: c, index: i };
    }
  }
  return hint === undefined ? null : findCard(board, line);
}

// Sends one change; when the file changed meanwhile, finds the card again and retries once.
async function change(op, retried) {
  const request = { ...op, version: state.board.version };
  const { status, data } = await api("POST", "/api/board", request);
  if (status === 200) { setBoard(data); return true; }
  if (status === 409 && data.board) {
    const previous = state.board;
    state.board = data.board;
    if (!retried) {
      const byName = (at) => {
        const name = previous.columns[at] && previous.columns[at].name;
        return data.board.columns.findIndex((column) => column.name === name);
      };
      const again = { ...op };
      if (op.line !== undefined) {
        const found = findCard(data.board, op.line, byName(op.column));
        if (!found) { render(); toast("That card changed in the file; reloaded"); return false; }
        again.column = found.column;
        again.index = found.index;
      } else if (op.column !== undefined) {
        again.column = byName(op.column);
      }
      if (op.to_column !== undefined) again.to_column = byName(op.to_column);
      if (again.column < 0 || again.to_column < 0) { render(); toast("A column changed in the file; reloaded"); return false; }
      toast("The file changed; applied on top");
      return change(again, true);
    }
    render();
    toast("The board changed; reloaded");
    return false;
  }
  toast(data.error || "Could not save");
  if (status === 404 || status === 500) loadBoard(true);
  return false;
}

const MARKUP = /(\[\[[^\]]+\]\])|(?<![\w&/])#([^\s#\[\]{}(),.;:!?'"]+)|@\{(\d{4}-\d{2}-\d{2})\}|📅\s*(\d{4}-\d{2}-\d{2})|\s*\[completion::\s*\d{4}-\d{2}-\d{2}\]/gu;

function dueChip(due) {
  if (!due) return null;
  const today = state.board.today;
  const kind = due < today ? "late" : due === today ? "today" : "";
  const label = due === today ? "today" : due === addDays(today, 1) ? "tomorrow" : due < today ? "overdue " + due.slice(5) : due.slice(5);
  return h("span", { class: "chip due " + kind, title: due, text: label });
}

function titleNodes(card) {
  const nodes = [];
  let last = 0;
  for (const match of card.title.matchAll(MARKUP)) {
    if (match.index > last) nodes.push(card.title.slice(last, match.index));
    last = match.index + match[0].length;
    if (match[1]) {
      const name = match[1].slice(2, -2).split(/[|#]/)[0];
      const label = match[1].slice(2, -2).split("|").pop();
      nodes.push(h("span", { class: "link", title: "Open in Obsidian", text: label, onclick: (event) => { event.stopPropagation(); openNote(name); } }));
    }
  }
  if (last < card.title.length) nodes.push(card.title.slice(last));
  return nodes;
}

function matches(card) {
  if (state.tag && !card.tags.includes(state.tag)) return false;
  if (!state.query) return true;
  const haystack = (card.title + " " + card.details.join(" ")).toLowerCase();
  return state.query.toLowerCase().split(/\s+/).every((word) => haystack.includes(word));
}

function cardNode(card, column, index, options) {
  const where = { line: card.line, column, index };
  const focused = state.timer && state.timer.card && state.timer.card === plain(card) && state.timer.phase !== "idle";
  const node = h("div", { class: "card" + (card.checked ? " checked" : "") + (focused ? " focus" : ""), draggable: options.drag ? "true" : null });
  if (state.editing && state.editing.line === card.line && state.editing.column === column) {
    const input = h("input", { class: "edit", value: card.title });
    const finish = async (save) => {
      if (!state.editing) return;
      state.editing = null;
      const text = input.value.trim();
      if (save && text && text !== card.title) await change({ op: "edit", text, ...where });
      else render();
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") finish(true);
      if (event.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    node.append(input);
    setTimeout(() => { input.focus(); input.select(); }, 0);
    return node;
  }
  const check = h("button", { class: "check", title: card.checked ? "Reopen" : "Done", onclick: (event) => { event.stopPropagation(); change({ op: card.checked ? "reopen" : "done", ...where }); } });
  const meta = h("div", { class: "meta" },
    card.tags.map((tag) => h("button", { class: "chip", text: "#" + tag, title: "Filter by #" + tag, onclick: (event) => { event.stopPropagation(); setTag(tag); } })),
    card.checked ? null : dueChip(card.due));
  const body = h("div", { class: "body" },
    h("div", { class: "text" }, titleNodes(card)),
    card.tags.length || card.due ? meta : null,
    card.details.length ? h("div", { class: "details", text: card.details.join("\n") }) : null,
    options.where ? h("div", { class: "where", text: options.where }) : null);
  const actions = h("div", { class: "actions" },
    card.checked ? null : h("button", { title: "Focus on this card (pomodoro)", text: "Focus", onclick: (event) => { event.stopPropagation(); timer("start", plain(card)); } }),
    h("button", { title: "Edit", text: "Edit", onclick: (event) => { event.stopPropagation(); state.editing = where; render(); } }),
    h("button", { title: "Delete", text: "✕", onclick: (event) => { event.stopPropagation(); if (confirm("Delete this card?\n\n" + card.title)) change({ op: "delete", ...where }); } }));
  node.append(check, body, actions);
  node.addEventListener("dblclick", () => { state.editing = where; render(); });
  if (options.drag) {
    node.addEventListener("dragstart", (event) => {
      state.dragging = where;
      node.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.title);
    });
    node.addEventListener("dragend", () => { state.dragging = null; node.classList.remove("dragging"); });
  }
  return node;
}

function plain(card) {
  return card.title.replace(MARKUP, (whole, link) => link ? link.slice(2, -2).split("|").pop() : "").replace(/\s+/g, " ").trim() || card.title;
}

function dropIndex(container, y) {
  const cards = [...container.querySelectorAll(".card:not(.dragging)")];
  for (const [i, card] of cards.entries()) {
    const box = card.getBoundingClientRect();
    if (y < box.top + box.height / 2) return Number(card.dataset.index ?? i);
  }
  return cards.length ? Number(cards[cards.length - 1].dataset.index) + 1 : 0;
}

function renderBoard(main) {
  const board = state.board;
  const wrap = h("div", { class: "board" });
  board.columns.forEach((column, c) => {
    const list = h("div", { class: "cards" });
    let shown = 0;
    column.cards.forEach((card, i) => {
      if (!matches(card)) return;
      const node = cardNode(card, c, i, { drag: !state.query && !state.tag });
      node.dataset.index = i;
      list.append(node);
      shown += 1;
    });
    const input = h("input", { placeholder: "+ Add a card", "data-column": c });
    input.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && input.value.trim()) {
        const text = input.value.trim();
        input.value = "";
        if (await change({ op: "add", column: c, text })) {
          const again = document.querySelector('.add input[data-column="' + c + '"]');
          if (again) again.focus();
        }
      }
      if (event.key === "Escape") input.blur();
    });
    const done = column.name === board.done_column;
    const node = h("section", { class: "column" + (column.doing ? " doing" : "") + (done ? " done" : "") },
      h("h2", {}, column.name, h("span", { class: "count", text: state.query || state.tag ? shown + "/" + column.cards.length : column.cards.length })),
      list, h("div", { class: "add" }, input));
    node.addEventListener("dragover", (event) => {
      if (!state.dragging) return;
      event.preventDefault();
      node.classList.add("drop");
    });
    node.addEventListener("dragleave", (event) => { if (!node.contains(event.relatedTarget)) node.classList.remove("drop"); });
    node.addEventListener("drop", (event) => {
      event.preventDefault();
      node.classList.remove("drop");
      const from = state.dragging;
      if (!from) return;
      let to = dropIndex(list, event.clientY);
      if (from.column === c && from.index < to) to -= 1;
      if (from.column === c && from.index === to) return;
      change({ op: "move", ...from, to_column: c, to_index: to });
    });
    wrap.append(node);
  });
  const newColumn = h("input", { placeholder: "+ Add a column" });
  newColumn.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && newColumn.value.trim()) change({ op: "column", name: newColumn.value.trim() });
  });
  wrap.append(h("div", { class: "newcol" }, newColumn));
  main.append(wrap);
}

function renderToday(main) {
  const board = state.board;
  const today = board.today;
  const late = [], due = [], doing = [], soon = [];
  board.columns.forEach((column, c) => column.cards.forEach((card, i) => {
    if (card.checked || column.name === board.done_column || !matches(card)) return;
    const item = { card, c, i, where: column.name };
    if (card.due && card.due < today) late.push(item);
    else if (card.due === today) due.push(item);
    else if (column.doing) doing.push(item);
    else if (card.due && card.due <= addDays(today, 7)) soon.push(item);
  }));
  soon.sort((a, b) => a.card.due.localeCompare(b.card.due));
  const quick = h("input", { placeholder: "Add a task: text #tag @today @tomorrow @+3 @2026-12-01" });
  quick.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter" || !quick.value.trim()) return;
    const first = board.columns.findIndex((column) => column.name !== board.done_column && !column.doing);
    const text = quick.value.trim();
    quick.value = "";
    if (await change({ op: "add", column: Math.max(0, first), text })) document.querySelector(".quick input")?.focus();
  });
  const page = h("div", { class: "page" }, h("div", { class: "quick" }, quick));
  const section = (title, items) => {
    page.append(h("h3", { text: title + " · " + items.length }));
    if (!items.length) page.append(h("div", { class: "empty", text: "Nothing here." }));
    for (const item of items) page.append(cardNode(item.card, item.c, item.i, { where: item.where }));
  };
  section("Overdue", late);
  section("Today", due);
  section("In progress", doing);
  section("Next 7 days", soon);
  main.append(page);
}

function addDays(iso, days) {
  const date = new Date(iso + "T12:00:00");
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

async function renderStats(main) {
  const { status, data } = await api("GET", "/api/stats");
  if (status !== 200) { toast(data.error || "Could not load stats"); return; }
  if (state.view !== "stats") return;
  main.textContent = "";
  const page = h("div", { class: "page" });
  page.append(h("h3", { text: "Today" }), h("div", { class: "numbers" },
    h("div", { class: "number" }, h("b", { text: data.today.pomodoros }), h("span", { text: "focus sessions" })),
    h("div", { class: "number" }, h("b", { text: Math.round(data.today.minutes) }), h("span", { text: "focus minutes" })),
    h("div", { class: "number" }, h("b", { text: data.today.done }), h("span", { text: "tasks done" })),
    h("div", { class: "number" }, h("b", { text: data.streak }), h("span", { text: "day streak" }))));
  const most = Math.max(1, ...data.week.map((day) => Math.max(day.pomodoros, day.done)));
  page.append(h("h3", { text: "Last 7 days" }), h("div", { class: "week" }, data.week.map((day) => h("div", { class: "day", title: day.date + ": " + day.pomodoros + " focus, " + day.minutes + " min, " + day.done + " done" },
    h("div", { class: "bars" }, h("i", { class: "f", style: "height:" + (day.pomodoros / most * 100) + "%" }), h("i", { class: "d", style: "height:" + (day.done / most * 100) + "%" })),
    h("span", { text: new Date(day.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short" }) })))));
  page.append(h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:var(--danger)" }), "focus sessions"), h("span", {}, h("i", { style: "background:var(--ok)" }), "tasks done")));
  page.append(h("h3", { text: "Most focused cards" }));
  page.append(data.cards.length
    ? h("div", { class: "top" }, data.cards.map((item) => h("div", {}, h("span", { text: item.card }), h("span", { class: "where", text: Math.round(item.minutes) + " min" }))))
    : h("div", { class: "empty", text: "Start a focus session from a card (Focus) to see time per card." }));
  page.append(h("div", { class: "where", style: "margin-top:18px", text: "All time: " + data.total_pomodoros + " focus sessions" }));
  main.append(page);
}

function render() {
  const main = $("main");
  for (const button of $("tabs").children) button.classList.toggle("on", button.dataset.view === state.view);
  const filter = $("filter");
  filter.classList.toggle("on", Boolean(state.tag));
  filter.textContent = state.tag ? "#" + state.tag + " ✕" : "";
  if (!state.board) return;
  if (state.view === "stats") { renderStats(main); return; }
  const scroll = main.querySelector(".board") ? main.querySelector(".board").parentElement.scrollLeft : 0;
  const active = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.column : undefined;
  main.textContent = "";
  if (state.view === "today") renderToday(main);
  else renderBoard(main);
  main.scrollLeft = scroll;
  if (active !== undefined) document.querySelector('.add input[data-column="' + active + '"]')?.focus();
}

function setView(view) {
  state.view = view;
  localStorage.setItem("desk-view", view);
  history.replaceState(null, "", location.pathname + "#" + view);
  render();
}

function setTag(tag) {
  state.tag = state.tag === tag ? "" : tag;
  render();
}

// ---- boards ----
async function loadBoards() {
  const { status, data } = await api("GET", "/api/boards");
  if (status !== 200) return;
  const select = $("boards");
  select.textContent = "";
  for (const path of data.recent.length ? data.recent : [data.current]) {
    select.append(h("option", { value: path, text: path.split("/").pop().replace(/\.md$/i, "") + "  —  " + path.split("/").slice(-2, -1)[0], selected: path === data.current }));
  }
  select.append(h("option", { value: "", text: "Open another board…" }));
}

async function switchBoard(path, create) {
  const { status, data } = await api("POST", "/api/boards", { path, create: Boolean(create) });
  if (status === 200) { state.tag = ""; setBoard(data); loadBoards(); toast("Opened " + data.name); return; }
  if (status === 404 && data.missing && !create && /\.md$/i.test(path) && confirm("No board at\n" + path + "\n\nCreate a new board there?")) return switchBoard(path, true);
  toast(data.error || "Could not open that board");
  loadBoards();
}

$("boards").addEventListener("change", (event) => {
  const value = event.target.value;
  if (value) { switchBoard(value); return; }
  const path = prompt("Path to a Kanban board (.md). A missing file can be created.", "~/");
  if (path && path.trim()) switchBoard(path.trim());
  else loadBoards();
});

async function openNote(name) {
  const { data } = await api("POST", "/api/obsidian", name ? { note: name } : {});
  if (!data.ok) toast(name ? "Note not found next to the board: " + name : "Could not open Obsidian");
}

// ---- pomodoro ----
async function loadTimer() {
  const { status, data } = await api("GET", "/api/pomodoro");
  if (status === 200) { state.timer = data; state.timerAt = Date.now(); drawTimer(); }
}

async function timer(action, card) {
  const body = { action };
  if (card !== undefined) body.card = card;
  const { status, data } = await api("POST", "/api/pomodoro", body);
  if (status !== 200) { toast(data.error || "Timer error"); return; }
  const linkedBefore = state.timer && state.timer.card;
  state.timer = data;
  state.timerAt = Date.now();
  drawTimer();
  if (card && card !== linkedBefore) toast("Focus: " + card);
  if (state.board && state.view !== "stats") render();
}

function remaining() {
  const t = state.timer;
  if (!t) return 0;
  return t.running ? Math.max(0, t.remaining - (Date.now() - state.timerAt) / 1000) : t.remaining;
}

function format(seconds) {
  const s = Math.ceil(seconds);
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

function drawTimer() {
  const t = state.timer;
  if (!t) return;
  const left = remaining();
  $("timer").className = "timer " + t.phase;
  $("phase").textContent = t.label + (t.phase === "work" ? " " + (t.cycle + 1) + "/" + t.cycles : "") + " · " + t.today + " today";
  $("clock").textContent = format(left);
  $("progress").style.width = (t.phase === "idle" ? 0 : (1 - left / t.length) * 100) + "%";
  $("linked").textContent = t.card ? "· " + t.card : "";
  $("linked").title = t.card || "";
  $("play").textContent = t.phase === "idle" ? "Start" : t.paused ? "Resume" : "Pause";
  $("skip").disabled = t.phase === "idle";
  $("stop").disabled = t.phase === "idle" && !t.card;
  const name = state.board ? state.board.name : "Desk";
  document.title = t.phase === "idle" ? name + " · Desk" : format(left) + " " + (t.phase === "work" ? "Focus" : "Break") + " · " + name;
  if (t.running && left <= 0 && Date.now() - state.timerAt > 900) loadTimer();
}

function togglePlay() {
  const t = state.timer;
  if (!t || t.phase === "idle") timer("start");
  else timer(t.paused ? "resume" : "pause");
}

$("play").addEventListener("click", togglePlay);
$("skip").addEventListener("click", () => timer("skip"));
$("stop").addEventListener("click", () => timer(state.timer && state.timer.phase === "idle" ? "unlink" : "stop"));
$("obsidian").addEventListener("click", () => openNote(""));
$("lofi").addEventListener("click", async () => { const { data } = await api("POST", "/api/lofi", {}); if (!data.ok) toast("Set apps.lofi_url to a web address"); });
$("filter").addEventListener("click", () => setTag(state.tag));
for (const button of $("tabs").children) button.addEventListener("click", () => setView(button.dataset.view));

// ---- theme, search, keys ----
function applyTheme(theme) {
  const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
applyTheme(localStorage.getItem("desk-theme"));
$("theme").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("desk-theme", next);
  applyTheme(next);
});

$("search").addEventListener("input", (event) => { state.query = event.target.value.trim(); render(); });

document.addEventListener("keydown", (event) => {
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (event.key === "Escape") {
    if (typing) document.activeElement.blur();
    if (state.query || state.tag) { state.query = ""; state.tag = ""; $("search").value = ""; render(); }
    return;
  }
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "/") { event.preventDefault(); $("search").focus(); }
  else if (event.key === "n") {
    event.preventDefault();
    if (state.view === "today") document.querySelector(".quick input")?.focus();
    else { if (state.view !== "board") setView("board"); document.querySelector(".add input")?.focus(); }
  }
  else if (event.key === " ") { event.preventDefault(); togglePlay(); }
  else if (event.key === "1") setView("board");
  else if (event.key === "2") setView("today");
  else if (event.key === "3") setView("stats");
});

// ---- start ----
async function start() {
  if (!TOKEN) { document.body.textContent = "Open the desk with `ul desk`: this page needs its token."; return; }
  await Promise.all([loadBoard(true), loadBoards(), loadTimer()]);
  render();
  setInterval(() => { if (!document.hidden && !state.dragging && !state.editing) loadBoard(false); }, 2000);
  setInterval(() => { if (!document.hidden) loadTimer(); }, 10000);
  setInterval(drawTimer, 500);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { loadBoard(false); loadTimer(); } });
}
start();
</script>
</body>
</html>
"""

import fcntl
import hmac
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path



USAGE = (
    "Usage: ul desk [board.md] [--port N] [--no-open] | new <board.md> | path [board.md] | "
    "stats [board.md] | pomodoro [status|start [minutes] [--card <text>]|pause|resume|stop|skip]"
)
PHASES = {
    "work": "Focus",
    "short": "Short break",
    "long": "Long break",
    "idle": "Ready",
}
DOING_COLUMNS = {"doing", "in progress", "in work", "в работе", "делаю", "в процессе"}
MAX_BODY = 64 * 1024
MAX_TEXT = 500
RECENT = 8


def _number(value: object, default: float, minimum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value < minimum
    ):
        return default
    return float(value)


def desk_settings(config: dict) -> dict:
    """[desk] with every value checked, so a bad config never breaks the server."""
    desk = config.get("desk", {}) if isinstance(config.get("desk"), dict) else {}
    pomodoro = (
        desk.get("pomodoro", {}) if isinstance(desk.get("pomodoro"), dict) else {}
    )
    port = desk.get("port", 8765)
    return {
        "port": port
        if isinstance(port, int) and not isinstance(port, bool) and 0 <= port <= 65535
        else 8765,
        "open_browser": desk.get("open_browser", True) is not False,
        "sound": desk.get("sound", True) is not False,
        "work": _number(pomodoro.get("work"), 25, 0.01),
        "short_break": _number(pomodoro.get("short_break"), 5, 0.01),
        "long_break": _number(pomodoro.get("long_break"), 15, 0.01),
        "cycles": int(_number(pomodoro.get("cycles"), 4, 1)),
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".desk.", delete=False
    ) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _read_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    """One writer at a time across the server and `ul desk pomodoro` calls."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def notify(title: str, message: str, sound: bool) -> None:
    """A macOS notification; failures (no osascript) are ignored."""
    script = (
        f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    )
    if sound:
        script += ' sound name "Glass"'
    try:
        subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        pass


IDLE = {
    "phase": "idle",
    "ends_at": None,
    "paused": None,
    "length": 0,
    "started_at": None,
    "cycle": 0,
    "card": None,
}


class Pomodoro:
    """Timer state in storage.root/desk/pomodoro.json, finished focus sessions in pomodoro.jsonl."""


    def __init__(
        self, directory: Path, settings: dict, clock: Callable[[], float] = time.time
    ) -> None:
        self.directory = directory
        self.settings = settings
        self.clock = clock

    @property
    def state_file(self) -> Path:
        return self.directory / "pomodoro.json"

    @property
    def log_file(self) -> Path:
        return self.directory / "pomodoro.jsonl"

    def _load(self) -> dict:
        state = _read_json(self.state_file, {})
        return {**IDLE, **state} if isinstance(state, dict) else dict(IDLE)

    def _save(self, state: dict) -> None:
        _write_json(self.state_file, state)

    def _minutes(self, phase: str) -> float:
        return {
            "work": self.settings["work"],
            "short": self.settings["short_break"],
            "long": self.settings["long_break"],
        }[phase]

    def _begin(self, state: dict, phase: str, minutes: float | None = None) -> None:
        length = (minutes or self._minutes(phase)) * 60
        now = self.clock()
        state.update(
            phase=phase,
            length=length,
            started_at=now,
            ends_at=now + length,
            paused=None,
        )

    def _log(self, state: dict, board: str | None) -> None:
        end = self.clock()
        entry = {
            "start": datetime.fromtimestamp(state["started_at"])
            .astimezone()
            .isoformat(timespec="seconds"),
            "end": datetime.fromtimestamp(end)
            .astimezone()
            .isoformat(timespec="seconds"),
            "minutes": round(state["length"] / 60, 2),
            "card": state.get("card"),
            "board": board,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def tick(self, board: str | None = None) -> dict | None:
        """Finish a phase whose time is up; returns what ended (for a notification)."""
        with _locked(self.directory):
            state = self._load()
            if (
                state["phase"] == "idle"
                or state["paused"] is not None
                or self.clock() < (state["ends_at"] or 0)
            ):
                return None
            ended = state["phase"]
            if ended == "work":
                self._log(state, board)
                state["cycle"] += 1
                long_break = state["cycle"] % self.settings["cycles"] == 0
                self._begin(state, "long" if long_break else "short")
            else:
                state.update(IDLE, cycle=state["cycle"], card=state["card"])
            self._save(state)
            return {"ended": ended, "next": state["phase"], "card": state["card"]}

    def act(
        self, action: str, minutes: float | None = None, card_title: str | None = None
    ) -> dict:
        with _locked(self.directory):
            state = self._load()
            now = self.clock()
            if action == "start":
                if card_title is not None:
                    state["card"] = card_title.strip()[:MAX_TEXT] or None
                self._begin(state, "work", minutes)
            elif (
                action == "pause"
                and state["phase"] != "idle"
                and state["paused"] is None
            ):
                state["paused"] = max(0.0, state["ends_at"] - now)
            elif action == "resume" and state["paused"] is not None:
                state["ends_at"], state["paused"] = now + state["paused"], None
            elif action == "stop":
                state = {**IDLE, "cycle": state["cycle"], "card": state["card"]}
            elif action == "skip" and state["phase"] != "idle":
                if state["phase"] == "work":
                    state["cycle"] += 1
                    self._begin(
                        state,
                        "long"
                        if state["cycle"] % self.settings["cycles"] == 0
                        else "short",
                    )
                else:
                    state = {
                        **IDLE,
                        "cycle": state["cycle"],
                        "card": state["card"],
                    }
            elif action == "unlink":
                state["card"] = None
            elif action not in {"pause", "resume", "skip"}:
                raise ValueError(f"Unknown pomodoro action: {action}")
            self._save(state)
        return self.status()

    def status(self) -> dict:
        state = self._load()
        if state["phase"] == "idle":
            remaining = self._minutes("work") * 60
        elif state["paused"] is not None:
            remaining = state["paused"]
        else:
            remaining = max(0.0, state["ends_at"] - self.clock())
        today = datetime.now().astimezone().date().isoformat()
        done_today = sum(
            1 for entry in self.entries() if str(entry.get("end", "")).startswith(today)
        )
        return {
            "phase": state["phase"],
            "label": PHASES[state["phase"]],
            "running": state["phase"] != "idle" and state["paused"] is None,
            "paused": state["paused"] is not None,
            "remaining": round(remaining, 1),
            "length": state["length"] or self._minutes("work") * 60,
            "cycle": state["cycle"] % self.settings["cycles"],
            "cycles": self.settings["cycles"],
            "card": state["card"],
            "today": done_today,
        }

    def entries(self) -> list[dict]:
        try:
            lines = self.log_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        entries = []
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries


def stats(board: KanbanBoard | None, entries: list[dict], today: date) -> dict:
    """Focus sessions and finished tasks per day for the last week, the streak and the busiest cards."""
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    focus: dict[str, list[float]] = {}
    per_card: dict[str, float] = {}
    for entry in entries:
        day = str(entry.get("end", ""))[:10]
        minutes = entry.get("minutes", 0)
        minutes = (
            float(minutes)
            if isinstance(minutes, (int, float)) and not isinstance(minutes, bool)
            else 0.0
        )
        focus.setdefault(day, []).append(minutes)
        if entry.get("card"):
            per_card[str(entry["card"])] = (
                per_card.get(str(entry["card"]), 0.0) + minutes
            )
    done: dict[str, int] = {}
    if board is not None:
        for section in board.sections:
            for task in section.tasks:
                completed = card(task)["completed"]
                if completed:
                    done[completed] = done.get(completed, 0) + 1
    week = [
        {
            "date": day.isoformat(),
            "pomodoros": len(focus.get(day.isoformat(), [])),
            "minutes": round(sum(focus.get(day.isoformat(), [])), 1),
            "done": done.get(day.isoformat(), 0),
        }
        for day in days
    ]
    streak, day = 0, today

    def active(day: date) -> bool:
        return bool(focus.get(day.isoformat())) or bool(done.get(day.isoformat()))

    if not active(day):
        day -= timedelta(days=1)
    while active(day):
        streak += 1
        day -= timedelta(days=1)
    top = sorted(per_card.items(), key=lambda item: -item[1])[:5]
    return {
        "today": week[-1],
        "week": week,
        "streak": streak,
        "cards": [
            {"card": name, "minutes": round(minutes, 1)} for name, minutes in top
        ],
        "total_pomodoros": sum(len(items) for items in focus.values()),
    }


class Conflict(Exception):
    """The board changed since the client read it."""


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("text must be a string")
    text = " ".join(value.split())
    if not text:
        raise ValueError("text cannot be empty")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text is longer than {MAX_TEXT} characters")
    return text


def _index(value: object, size: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < size:
        raise ValueError(f"{name} is out of range")
    return value


class Desk:
    """One open board file plus the timer; every board change checks the version first."""

    def __init__(
        self,
        path: Path,
        config: dict,
        directory: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self.config = config
        self.directory = directory
        self.settings = desk_settings(config)
        self.pomodoro = Pomodoro(directory, self.settings, clock)
        self.lock = threading.Lock()
        self.today: Callable[[], date] = lambda: datetime.now().astimezone().date()

    @property
    def completed_column(self) -> str:
        return str(self.config.get("todo", {}).get("completed_column", "Completed"))

    def read(self) -> tuple[str, KanbanBoard]:
        data = self.path.read_bytes()
        return version_of(data), KanbanBoard.parse(data.decode("utf-8"))

    def board_json(self) -> dict:
        version, board = self.read()
        return self.render(version, board)

    def render(self, version: str, board: KanbanBoard) -> dict:
        try:
            done_name = completed_section(board, self.completed_column).name
        except ValueError:
            done_name = None
        return {
            "version": version,
            "path": str(self.path),
            "name": self.path.stem,
            "today": self.today().isoformat(),
            "done_column": done_name,
            "columns": [
                {
                    "name": section.name,
                    "doing": section.name.casefold() in DOING_COLUMNS,
                    "cards": [card(task) for task in section.tasks],
                }
                for section in board.sections
            ],
        }

    def change(self, request: dict) -> dict:
        with self.lock:
            version, board = self.read()
            if request.get("version") != version:
                raise Conflict
            self.apply(board, request)
            write_board(self.path, board)
            return self.board_json()

    def _task(
        self, board: KanbanBoard, request: dict
    ) -> tuple[Section, int, list[str]]:
        section = board.sections[
            _index(request.get("column"), len(board.sections), "column")
        ]
        index = _index(request.get("index"), len(section.tasks), "index")
        task = section.tasks[index]
        if task[0] != request.get("line"):
            raise Conflict
        return section, index, task

    def apply(self, board: KanbanBoard, request: dict) -> None:
        op = request.get("op")
        today = self.today()
        if op == "add":
            section = board.sections[
                _index(request.get("column"), len(board.sections), "column")
            ]
            task = [f"- [ ] {quick_text(_clean_text(request.get('text')), today)}"]
            if request.get("top"):
                section.tasks.insert(0, task)
            else:
                section.tasks.append(task)
        elif op == "edit":
            _, _, task = self._task(board, request)
            mark = (
                "x"
                if task[0].startswith("- [x]") or task[0].startswith("- [X]")
                else " "
            )
            task[0] = (
                f"- [{mark}] {quick_text(_clean_text(request.get('text')), today)}"
            )
        elif op == "move":
            section, index, task = self._task(board, request)
            target = board.sections[
                _index(request.get("to_column"), len(board.sections), "to_column")
            ]
            section.tasks.pop(index)
            position = request.get("to_index", len(target.tasks))
            if isinstance(position, bool) or not isinstance(position, int):
                raise ValueError("to_index must be a number")
            target.tasks.insert(max(0, min(position, len(target.tasks))), task)
        elif op == "done":
            section, index, task = self._task(board, request)
            target = completed_section(board, self.completed_column)
            section.tasks.pop(index)
            complete_task(task, today)
            target.tasks.append(task)
        elif op == "reopen":
            section, index, task = self._task(board, request)
            reopen_task(task)
            section.tasks.pop(index)
            finished = {*DONE_COLUMNS, self.completed_column.casefold()}
            first = next((item for item in board.sections if item.name.casefold() not in finished), board.sections[0])
            first.tasks.append(task)
        elif op == "delete":
            section, index, _ = self._task(board, request)
            section.tasks.pop(index)
        elif op == "column":
            name = _clean_text(request.get("name"))
            if any(
                section.name.casefold() == name.casefold() for section in board.sections
            ):
                raise ValueError(f"Column '{name}' already exists")
            board.sections.append(Section(name=name))
        else:
            raise ValueError(f"Unknown operation: {op}")

    def recent(self) -> list[str]:
        items = _read_json(self.directory / "recent.json", [])
        paths = (
            [item for item in items if isinstance(item, str)]
            if isinstance(items, list)
            else []
        )
        return [path for path in paths if Path(path).is_file()]

    def remember(self) -> None:
        paths = [
            str(self.path),
            *[path for path in self.recent() if path != str(self.path)],
        ][:RECENT]
        _write_json(self.directory / "recent.json", paths)

    def switch(self, raw: object, create: bool) -> dict:
        path = board_file(_clean_text(raw), create=create)
        with self.lock:
            self.path = path
            self.remember()
        return self.board_json()


def board_file(raw: str, create: bool = False) -> Path:
    """A board chosen by the user: an existing .md file, or a new one from the template."""
    path = Path(raw).expanduser().resolve()
    if path.suffix.casefold() != ".md":
        raise ValueError(f"A board is a Markdown file (.md): {path}")
    if not path.exists():
        if not create:
            raise FileNotFoundError(
                f"Board not found: {path}. Create it with: ul desk new {raw}"
            )
        if not path.parent.is_dir():
            raise FileNotFoundError(f"Folder not found: {path.parent}")
        with path.open("x", encoding="utf-8") as handle:
            handle.write(NEW_BOARD)
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    KanbanBoard.parse(path.read_text(encoding="utf-8"))
    return path


def default_board(config: dict) -> Path:
    path = configured_board(config["todo"])
    if not path.is_file():
        raise FileNotFoundError(
            f"Kanban file not found: {path} (set todo.vault_path and todo.file, or pass a board.md)"
        )
    return path


def _find_note(root: Path, name: str) -> Path | None:
    wanted = f"{name}.md".casefold()
    for path in root.rglob("*.md"):
        if path.name.casefold() == wanted:
            return path
    return None


class Handler(BaseHTTPRequestHandler):
    desk: Desk
    token: str
    port: int
    server_version = "UnlawDesk"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(
        self, status: int, body: bytes, kind: str, headers: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(
        self, status: int, data: object, headers: dict[str, str] | None = None
    ) -> None:
        self._send(
            status,
            json.dumps(data, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
            headers,
        )

    def _allowed_host(self) -> bool:
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def _authorized(self, token: str | None) -> bool:
        return token is not None and hmac.compare_digest(token, self.token)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("request body is too large")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise TypeError("expected a JSON object")
        return data

    def _guard(self) -> bool:
        if not self._allowed_host():
            self._send(403, b"Forbidden host", "text/plain; charset=utf-8")
            return False
        if self.path.startswith("/api/") and not self._authorized(
            self.headers.get("X-Desk-Token")
        ):
            self._json(
                403, {"error": "missing or wrong token; open the page from `ul desk`"}
            )
            return False
        return True

    def do_GET(self) -> None:
        if not self._guard():
            return
        url = urllib.parse.urlsplit(self.path)
        try:
            if url.path == "/":
                token = urllib.parse.parse_qs(url.query).get("token", [None])[0]
                if not self._authorized(token):
                    self._send(
                        403,
                        b"Open the desk with `ul desk`: the page needs its token.",
                        "text/plain; charset=utf-8",
                    )
                    return
                self._send(
                    200,
                    PAGE.encode(),
                    "text/html; charset=utf-8",
                    {"Content-Security-Policy": CSP},
                )
            elif url.path == "/api/board":
                board = self.desk.board_json()
                if self.headers.get("If-None-Match") == board["version"]:
                    self._send(304, b"", "application/json", {"ETag": board["version"]})
                else:
                    self._json(200, board, {"ETag": board["version"]})
            elif url.path == "/api/pomodoro":
                # Only the ticker thread finishes phases, so its notification is never lost.
                self._json(200, self.desk.pomodoro.status())
            elif url.path == "/api/stats":
                try:
                    _, board = self.desk.read()
                except (OSError, ValueError):
                    board = None
                self._json(
                    200, stats(board, self.desk.pomodoro.entries(), self.desk.today())
                )
            elif url.path == "/api/boards":
                self._json(
                    200, {"current": str(self.desk.path), "recent": self.desk.recent()}
                )
            else:
                self._json(404, {"error": "not found"})
        except (OSError, ValueError) as error:
            self._json(500, {"error": str(error)})

    def do_POST(self) -> None:
        if not self._guard():
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            body = self._body()
            if path == "/api/board":
                self._json(200, self.desk.change(body))
            elif path == "/api/pomodoro":
                minutes = body.get("minutes")
                if minutes is not None and (
                    isinstance(minutes, bool)
                    or not isinstance(minutes, (int, float))
                    or not 0 < minutes <= 600
                ):
                    raise ValueError("minutes must be between 0 and 600")
                card_title = body.get("card")
                if card_title is not None and not isinstance(card_title, str):
                    raise ValueError("card must be text")
                self._json(
                    200,
                    self.desk.pomodoro.act(
                        str(body.get("action")), minutes, card_title
                    ),
                )
            elif path == "/api/boards":
                self._json(
                    200, self.desk.switch(body.get("path"), bool(body.get("create")))
                )
            elif path == "/api/obsidian":
                self._json(200, {"ok": self._open_obsidian(body.get("note"))})
            elif path == "/api/lofi":
                url = str(self.desk.config.get("apps", {}).get("lofi_url", ""))
                ok = (
                    url.startswith(("http://", "https://"))
                    and subprocess.run(["open", url], check=False).returncode == 0
                )
                self._json(200, {"ok": ok})
            else:
                self._json(404, {"error": "not found"})
        except Conflict:
            self._json(
                409,
                {
                    "error": "the board changed; reloaded",
                    "board": self.desk.board_json(),
                },
            )
        except FileNotFoundError as error:
            self._json(404, {"error": str(error), "missing": True})
        except (ValueError, TypeError, KeyError) as error:
            self._json(400, {"error": str(error)})
        except OSError as error:
            self._json(500, {"error": str(error)})

    def _open_obsidian(self, note: object) -> bool:
        target = self.desk.path
        if isinstance(note, str) and note.strip():
            found = _find_note(self.desk.path.parent, note.strip())
            if found is None:
                return False
            target = found
        url = "obsidian://open?path=" + urllib.parse.quote(str(target), safe="")
        return subprocess.run(["open", url], check=False).returncode == 0


CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'"


def make_server(desk: Desk, port: int, token: str, exact: bool) -> ThreadingHTTPServer:
    """Bind 127.0.0.1 on `port` (0: any free port), trying the next ones unless `exact`."""
    last_error: OSError | None = None
    for candidate in (
        [port] if exact or port == 0 else range(port, min(port + 20, 65536))
    ):
        handler = type(
            "DeskHandler", (Handler,), {"desk": desk, "token": token, "port": candidate}
        )
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as error:
            last_error = error
            continue
        handler.port = server.server_address[1]
        server.daemon_threads = True
        return server
    raise OSError(f"no free port from {port}: {last_error}")


def _ticker(desk: Desk, stop: threading.Event) -> None:
    while not stop.wait(0.5):
        try:
            event = desk.pomodoro.tick(str(desk.path))
        except OSError:
            continue
        if event:
            ended = "Focus finished" if event["ended"] == "work" else "Break is over"
            following = (
                PHASES[event["next"]].lower()
                if event["next"] != "idle"
                else "start the next focus when ready"
            )
            notify("Unlaw desk", f"{ended}: {following}", desk.settings["sound"])


def serve(path: Path, config: dict, port: int | None, open_browser: bool) -> int:
    desk = Desk(path, config, storage_path("desk"))
    desk.remember()
    token = secrets.token_urlsafe(18)
    settings = desk.settings
    server = make_server(
        desk, settings["port"] if port is None else port, token, exact=port is not None
    )
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    print(f"Desk: {url}", flush=True)
    print(f"Board: {path}", flush=True)
    print("Ctrl+C stops it.", flush=True)
    stop = threading.Event()
    threading.Thread(target=_ticker, args=(desk, stop), daemon=True).start()
    if open_browser and settings["open_browser"]:
        subprocess.run(["open", url], check=False)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        stop.set()
        server.server_close()
    return 0


def _format_minutes(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _pomodoro_cli(args: list[str], config: dict) -> int:
    pomodoro = Pomodoro(storage_path("desk"), desk_settings(config))
    action = args[0] if args else "status"
    rest = args[1:]
    minutes: float | None = None
    card_title: str | None = None
    if "--card" in rest:
        at = rest.index("--card")
        if at + 1 >= len(rest):
            raise ValueError("--card needs the task text")
        card_title = " ".join(rest[at + 1 :])
        rest = rest[:at]
    if action == "start" and rest:
        minutes = float(rest[0])
        if not 0 < minutes <= 600 or len(rest) > 1:
            raise ValueError("start takes one length in minutes (0-600)")
        rest = []
    if rest or action not in {"status", "start", "pause", "resume", "stop", "skip"}:
        print(USAGE, file=sys.stderr)
        return 2
    event = pomodoro.tick()
    if event:
        print(f"Finished: {PHASES[event['ended']]}")
    status = (
        pomodoro.status()
        if action == "status"
        else pomodoro.act(action, minutes, card_title)
    )
    state = (
        "paused"
        if status["paused"]
        else ("running" if status["running"] else "not running")
    )
    linked = f" · {status['card']}" if status["card"] else ""
    print(f"{status['label']}: {_format_minutes(status['remaining'])} {state}{linked}")
    print(f"Today: {status['today']} focus session(s)")
    return 0


def _stats_cli(path: Path | None, config: dict) -> int:
    pomodoro = Pomodoro(storage_path("desk"), desk_settings(config))
    board = KanbanBoard.parse(path.read_text(encoding="utf-8")) if path else None
    result = stats(board, pomodoro.entries(), datetime.now().astimezone().date())
    print(
        f"Today: {result['today']['pomodoros']} focus session(s), {result['today']['minutes']} min, {result['today']['done']} done"
    )
    print(f"Streak: {result['streak']} day(s)")
    for day in result["week"]:
        bar = "█" * day["pomodoros"]
        print(
            f"  {day['date']}  {day['pomodoros']:>2} focus  {day['done']:>2} done  {bar}"
        )
    for item in result["cards"]:
        print(f"  {item['minutes']:>6} min  {item['card']}")
    return 0


def _parse_serve(args: list[str]) -> tuple[str | None, int | None, bool]:
    board: str | None = None
    port: int | None = None
    open_browser = True
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--no-open":
            open_browser = False
        elif arg == "--port":
            if not rest or not rest[0].isdigit() or int(rest[0]) > 65535:
                raise ValueError("--port needs a number from 0 to 65535")
            port = int(rest.pop(0))
        elif arg.startswith("-") or board is not None:
            raise ValueError(f"Unexpected argument: {arg}")
        else:
            board = arg
    return board, port, open_browser


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    try:
        config = load_config()
        action = args[0] if args else ""
        if action == "pomodoro":
            return _pomodoro_cli(args[1:], config)
        if action == "new" and len(args) == 2:
            if Path(args[1]).expanduser().exists():
                raise ValueError(f"{args[1]} already exists; open it with: ul desk {args[1]}")
            path = board_file(args[1], create=True)
            print(f"Board: {path}")
            return 0
        if action == "path" and len(args) <= 2:
            print(board_file(args[1]) if len(args) == 2 else default_board(config))
            return 0
        if action == "stats" and len(args) <= 2:
            return _stats_cli(
                board_file(args[1]) if len(args) == 2 else default_board(config), config
            )
        if action in {"new", "path", "stats"}:
            print(USAGE, file=sys.stderr)
            return 2
        board, port, open_browser = _parse_serve(args)
        path = board_file(board) if board else default_board(config)
        return serve(path, config, port, open_browser)
    except (ConfigError, FileNotFoundError, OSError, ValueError) as error:
        print(f"unlaw desk: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
