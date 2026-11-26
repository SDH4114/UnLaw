# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Kanban boards (Obsidian .md files), Apple Reminders, pomodoro and canvas in the browser."""
from __future__ import annotations

COMMAND_HELP = 'Kanban boards (Obsidian .md files), Apple Reminders, pomodoro and canvas in the browser.\nUsage: ul desk [board] [--reminders] [--port N] [--no-open]\n       ul desk list | show [board] | add <text> | move <n> <column> | done <n>\n       ul desk new <name> | rm <board> | path [board] | stats [board] | pomodoro [...]\nPage:\n  ul desk           Open the board shown last on 127.0.0.1 (first time the default\n                    <desk.boards_dir>/board.md; todo.vault_path + todo.file pick another)\n  [board]           A name = <desk.boards_dir>/<name>.md, or a path to any .md board\n  --reminders       Open Apple Reminders as a board (lists = columns)\nTerminal (for you and AI agents):\n  list [--json]     Default, recent and named boards, and whether Reminders is on\n  show [board]      Columns and numbered cards; --json for scripts, --reminders\n  add <text>        New card in the first column (--column C; @today/@tomorrow dates)\n  move <n> <col>    Move card n; done <n> checks it and moves it to the Done column\n                    add/move/done take -b <board>; without it the default board\n  new <name>        Create a board with To do / Doing / Done\n  rm <board>        Move a board to the Trash (not the default board)\n  stats, pomodoro   Focus statistics and the timer the page shows too\nThe .md file is the source of truth: Obsidian, the page and these commands all\nsee every change. Tabs on the page: Board, Today (with focus stats), Games, Studio, Canvas.\nSettings: desk.port, desk.boards_dir, desk.canvas_dir, desk.reminders, desk.pomodoro.*,\n  todo.vault_path (empty = desk.boards_dir), todo.file, todo.completed_column.\nExamples: ul desk\n          ul desk show Work --json\n          ul desk add "Call the bank @tomorrow" -b Work\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'},
 'todo': {'vault_path': '', 'file': 'board.md', 'completed_column': 'Completed'},
 'desk': {'port': 8765,
          'open_browser': True,
          'sound': True,
          'reminders': True,
          'boards_dir': 'boards',
          'canvas_dir': 'canvas',
          'pomodoro': {'work': 25, 'short_break': 5, 'long_break': 15, 'cycles': 4}},
 'games': {'difficulty': 'normal'},
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
DUE = re.compile(r"@\{(\d{4}-\d{2}-\d{2})\}|\U0001F4C5\s*(\d{4}-\d{2}-\d{2})")  # the calendar emoji, escaped: one astral character makes Python store the whole seed at 4 bytes per character
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
    newline: str = "\n"

    @classmethod
    def parse(cls, text: str) -> KanbanBoard:
        # Only \n and \r\n end a line: str.splitlines() would also split on \x0b, \x0c, \x85, \u2028 and others inside a card.
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = re.split(r"\r?\n", text)
        first_heading = next((i for i, line in enumerate(lines) if HEADING.match(line)), None)
        if first_heading is None:
            raise ValueError("the board has no '##' Kanban columns")
        # The footer starts at Obsidian's `***` archive separator or at the settings block, whichever comes first.
        footer_at = next(
            (
                i
                for i, line in enumerate(lines)
                if line.strip() == KANBAN_MARKER or (i > first_heading and line.rstrip() == "***")
            ),
            len(lines),
        )
        body, footer = lines[:footer_at], lines[footer_at:]
        heading_positions = [
            (i, match.group(1))
            for i, line in enumerate(body)
            if (match := HEADING.match(line))
        ]
        if not heading_positions:
            raise ValueError("the board has no '##' Kanban columns")
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
                # Everything up to the next card belongs to this card, so the file keeps its order on save.
                tasks.append(_trim_blank(content[task_start:task_end]))
            sections.append(Section(name=name, preamble=preamble, tasks=tasks))
        return cls(
            prefix=_trim_blank_right(prefix),
            sections=sections,
            footer=_trim_blank(footer),
            newline=newline,
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
        return self.newline.join(lines).rstrip() + self.newline


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


class BoardChanged(ValueError):
    """The file changed between reading and writing it (the page, Obsidian or another `ul desk`)."""


def write_board(path: Path, board: KanbanBoard, expected: str | None = None) -> None:
    """Replace the board file atomically (a temporary file next to it, then rename). With `expected` (the
    version that was read), a file that changed meanwhile is left alone and BoardChanged is raised."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=".todo.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(board.render())
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        # The temporary file is created 0600; the board keeps the mode it had.
        try:
            os.chmod(temporary, path.stat().st_mode & 0o7777)
        except FileNotFoundError:
            pass
        if expected is not None and version_of(path.read_bytes()) != expected:
            raise BoardChanged(f"{path.name} changed while it was being edited")
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
        # ASCII digits, at most 5 (274 years): `@+²` or `@+99999999999` stay plain text.
        days = word[1:]
        if word.startswith("+") and days.isascii() and days.isdigit() and len(days) <= 5:
            try:
                return "@{" + (today + timedelta(days=int(days))).isoformat() + "}"
            except OverflowError:
                return match.group(0)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", word):
            try:
                return "@{" + date.fromisoformat(word).isoformat() + "}"
            except ValueError:
                pass
        return match.group(0)

    return re.sub(r"(?<![\w{])@([^\s{}]+)", replace, text).strip()

"""Apple Reminders as a Kanban layer for `ul desk`: every list is a column, every open reminder a card.

Seeded into the desk command's source. It talks to EventKit through `osascript -l JavaScript`
(stdlib only): the Reminders app's Apple Events take 10-20 s on a list with hundreds of finished
reminders, EventKit answers in a fraction of a second.
"""


import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


REMINDERS = "reminders:"
DUE_TOKEN = re.compile(r"\s*@\{(\d{4}-\d{2}-\d{2})\}")
MAX_NOTE_LINES = 20

# One request per run: argv[0] is a JSON object with "op"; the answer is JSON on stdout.
EVENTKIT_SCRIPT = r"""
ObjC.import("EventKit");
function wait(isDone, seconds) {
  const until = Date.now() + seconds * 1000;
  while (!isDone() && Date.now() < until) $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.02));
  return isDone();
}
function text(value) { const s = ObjC.unwrap(value); return typeof s === "string" ? s : ""; }
function day(components) {
  if (!components || components.isNil()) return null;
  const y = Number(components.year), m = Number(components.month), d = Number(components.day);
  if (!(y > 0 && y < 10000 && m >= 1 && m <= 12 && d >= 1 && d <= 31)) return null;
  return String(y).padStart(4, "0") + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
}
function check(ok, error, what) {
  if (!ok) throw new Error(what + ": " + (error[0] && !error[0].isNil() ? text(error[0].localizedDescription) : "unknown error"));
}
function run(argv) {
  try {
    const request = JSON.parse(argv[0]);
    const access = () => Number($.EKEventStore.authorizationStatusForEntityType($.EKEntityTypeReminder));
    let store = $.EKEventStore.alloc.init;
    let status = access();
    if (status === 0) {
      // First run: macOS asks the user. The completion block may never reach this run loop,
      // so the status itself is polled too; a store made before the answer sees no data.
      let answered = false;
      store.requestFullAccessToRemindersWithCompletion((granted) => { answered = true; });
      wait(() => answered || access() !== 0, 90);
      status = access();
      if (status === 0) return JSON.stringify({ error: "macOS is still asking for access to Reminders: answer the dialog, then try again" });
      store = $.EKEventStore.alloc.init;
    }
    if (status !== 3) return JSON.stringify({ error: "no access to Reminders: allow your terminal in System Settings > Privacy & Security > Reminders" });
    const item = (id) => {
      const found = store.calendarItemWithIdentifier(id);
      if (!found || found.isNil() || !found.isKindOfClass($.EKReminder)) throw new Error("the reminder no longer exists");
      return found;
    };
    const list = (id) => {
      const found = store.calendarWithIdentifier(id);
      if (!found || found.isNil()) throw new Error("the list no longer exists");
      return found;
    };
    const setDue = (reminder, due) => {
      if (due === undefined) return;
      if (due === null) { reminder.setDueDateComponents($()); return; }
      if (day(reminder.dueDateComponents) === due) return;  // keeps a time of day the reminder already had
      const parts = due.split("-").map(Number);
      const components = $.NSDateComponents.alloc.init;
      components.setYear(parts[0]); components.setMonth(parts[1]); components.setDay(parts[2]);
      reminder.setDueDateComponents(components);
    };
    const save = (reminder) => { const error = Ref(); check(store.saveReminderCommitError(reminder, true, error), error, "could not save the reminder"); };
    const op = request.op;
    if (op === "list") {
      const calendars = store.calendarsForEntityType($.EKEntityTypeReminder);
      const lists = [];
      for (let i = 0; i < calendars.count; i++) {
        const c = calendars.objectAtIndex(i);
        lists.push({ id: text(c.calendarIdentifier), title: text(c.title), writable: Boolean(c.allowsContentModifications) });
      }
      let fetched = null;
      store.fetchRemindersMatchingPredicateCompletion(store.predicateForIncompleteRemindersWithDueDateStartingEndingCalendars($(), $(), $()), (items) => { fetched = items; });
      if (!wait(() => fetched !== null, 20)) throw new Error("Reminders did not answer");
      const items = [];
      for (let i = 0; i < fetched.count; i++) {
        const r = fetched.objectAtIndex(i);
        const created = r.creationDate;
        items.push({ id: text(r.calendarItemIdentifier), title: text(r.title), list: text(r.calendar.calendarIdentifier), due: day(r.dueDateComponents), notes: text(r.notes), created: created && !created.isNil() ? Number(created.timeIntervalSince1970) : 0 });
      }
      return JSON.stringify({ lists, items });
    }
    if (op === "add") {
      const reminder = $.EKReminder.reminderWithEventStore(store);
      reminder.setTitle(request.title);
      reminder.setCalendar(list(request.list));
      setDue(reminder, request.due);
      save(reminder);
      return JSON.stringify({ id: text(reminder.calendarItemIdentifier) });
    }
    if (op === "edit") { const r = item(request.id); r.setTitle(request.title); setDue(r, request.due); save(r); return "{}"; }
    if (op === "move") { const r = item(request.id); r.setCalendar(list(request.list)); save(r); return "{}"; }
    if (op === "done") { const r = item(request.id); r.setCompleted(true); save(r); return "{}"; }
    if (op === "delete") { const error = Ref(); check(store.removeReminderCommitError(item(request.id), true, error), error, "could not delete the reminder"); return "{}"; }
    if (op === "new_list") {
      const source = store.defaultCalendarForNewReminders.source;
      const calendar = $.EKCalendar.calendarForEntityTypeEventStore($.EKEntityTypeReminder, store);
      calendar.setTitle(request.title);
      calendar.setSource(source);
      const error = Ref();
      check(store.saveCalendarCommitError(calendar, true, error), error, "could not create the list");
      return JSON.stringify({ id: text(calendar.calendarIdentifier) });
    }
    return JSON.stringify({ error: "unknown operation " + op });
  } catch (error) {
    return JSON.stringify({ error: String(error && error.message || error) });
  }
}
"""


class RemindersError(OSError):
    """Reminders could not be read or changed (an OSError, so the desk reports it like a file error)."""


def split_due(text: str) -> tuple[str, str | None]:
    """`Buy milk @{2026-11-09}` -> ("Buy milk", "2026-11-09"); the first date wins, every token is removed."""
    match = DUE_TOKEN.search(text)
    title = " ".join(DUE_TOKEN.sub(" ", text).split())
    if not title:
        raise ValueError("text cannot be empty")
    return title, match.group(1) if match else None


def reminders_available(enabled: bool) -> bool:
    return (
        enabled and sys.platform == "darwin" and shutil.which("osascript") is not None
    )


class Reminders:
    """A cached snapshot of the open reminders plus the writes; one osascript run per call."""

    MAX_AGE = 1.5

    # Above the script's own waits (90 s for the access dialog + 20 s for the fetch),
    # so a slow first run ends with the script's message, not a kill.
    def __init__(self, timeout: float = 120, clock=time.monotonic) -> None:
        self.timeout = timeout
        self.clock = clock
        self.lock = threading.Lock()
        self._snapshot: dict | None = None
        self._read_at = 0.0

    def call(self, request: dict) -> dict:
        try:
            done = subprocess.run(
                [
                    "osascript",
                    "-l",
                    "JavaScript",
                    "-e",
                    EVENTKIT_SCRIPT,
                    json.dumps(request, ensure_ascii=False),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RemindersError("Reminders did not answer in time") from error
        except OSError as error:
            raise RemindersError(f"could not run osascript: {error}") from error
        if done.returncode != 0:
            lines = done.stderr.strip().splitlines()
            raise RemindersError(
                f"osascript failed: {lines[-1] if lines else done.returncode}"
            )
        try:
            data = json.loads(done.stdout)
        except ValueError as error:
            raise RemindersError(
                "osascript returned something that is not JSON"
            ) from error
        if not isinstance(data, dict):
            raise RemindersError("osascript returned something that is not an object")
        if data.get("error"):
            raise RemindersError(str(data["error"]))
        return data

    def snapshot(self, fresh: bool = False) -> dict:
        with self.lock:
            if (
                fresh
                or self._snapshot is None
                or self.clock() - self._read_at > self.MAX_AGE
            ):
                self._snapshot = _normalized(self.call({"op": "list"}))
                self._read_at = self.clock()
            return self._snapshot

    def invalidate(self) -> None:
        with self.lock:
            self._snapshot = None

    def read(
        self, fresh: bool = False
    ) -> tuple[str, KanbanBoard, list[list[str]], list[str]]:
        """(version, board, reminder ids per column, list ids) of the current snapshot."""
        snapshot = self.snapshot(fresh)
        version = version_of(
            json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()
        )
        sections: list[Section] = []
        ids: list[list[str]] = []
        column_of = {}
        for position, item in enumerate(snapshot["lists"]):
            column_of[item["id"]] = position
            sections.append(Section(name=item["title"]))
            ids.append([])
        for reminder in snapshot["items"]:
            position = column_of.get(reminder["list"])
            if position is None:
                continue
            line = f"- [ ] {reminder['title']}" + (
                f" @{{{reminder['due']}}}" if reminder["due"] else ""
            )
            notes = [
                f"    {note}" for note in reminder["notes"].splitlines() if note.strip()
            ][:MAX_NOTE_LINES]
            sections[position].tasks.append([line, *notes])
            ids[position].append(reminder["id"])
        board = KanbanBoard(prefix=[], sections=sections, footer=[])
        return version, board, ids, [item["id"] for item in snapshot["lists"]]

    def add(self, list_id: str, text: str) -> None:
        title, due = split_due(text)
        self.call({"op": "add", "list": list_id, "title": title, "due": due})

    def edit(self, reminder: str, text: str) -> None:
        title, due = split_due(text)
        self.call({"op": "edit", "id": reminder, "title": title, "due": due})

    def move(self, reminder: str, list_id: str) -> None:
        self.call({"op": "move", "id": reminder, "list": list_id})

    def complete(self, reminder: str) -> None:
        self.call({"op": "done", "id": reminder})

    def delete(self, reminder: str) -> None:
        self.call({"op": "delete", "id": reminder})

    def new_list(self, title: str) -> None:
        self.call({"op": "new_list", "title": title})


def _normalized(data: dict) -> dict:
    """Only well-formed lists and reminders, titles on one line, reminders in creation order."""
    lists = [
        {
            "id": item["id"],
            "title": " ".join(str(item.get("title", "")).split()) or "Untitled",
        }
        for item in data.get("lists", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    ]
    items = []
    for item in data.get("items", []):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"]
        ):
            continue
        due = item.get("due")
        created = item.get("created")
        items.append(
            {
                "id": item["id"],
                "title": " ".join(str(item.get("title", "")).split()) or "Untitled",
                "list": str(item.get("list", "")),
                "due": due
                if isinstance(due, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", due)
                else None,
                "notes": str(item.get("notes") or ""),
                "created": created
                if isinstance(created, (int, float)) and not isinstance(created, bool)
                else 0,
            }
        )
    items.sort(key=lambda item: (item["created"], item["id"]))
    return {"lists": lists, "items": items}


def boards_folder(raw: object, config_directory: Path) -> Path:
    """desk.boards_dir: `~` expands, a relative path is inside the Unlaw config directory."""
    configured = Path(str(raw or "boards")).expanduser()
    return configured if configured.is_absolute() else config_directory / configured

"""JSON Canvas files for `ul desk` (https://jsoncanvas.org/spec/1.0/).

Nodes and edges are Obsidian Canvas's own. Freehand drawings and shapes live in the same file
under the extra top-level key "unlaw", which Obsidian ignores. Every key that is not checked
here (on nodes, edges, elements and the top level) is kept exactly as it was read.
"""

# ruff: noqa: TRY004  (every bad input is a ValueError for the HTTP layer)

import hashlib
import http.client
import ipaddress
import json
import math
import os
import re
import socket
import ssl
import tempfile
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path


NEW_CANVAS = {"nodes": [], "edges": []}
NODE_TYPES = {"text", "file", "link", "group"}
ELEMENT_TYPES = {
    "freedraw",
    "rectangle",
    "ellipse",
    "diamond",
    "line",
    "arrow",
    "text",
    "paint",
}
# paint = an area left by the fill tool: outer ring in points, optional holes.
POINT_TYPES = {"freedraw", "line", "arrow", "paint"}
MAX_STROKE_WIDTH = 100
MAX_ELEMENTS = 20000
MAX_NODES = 20000
MAX_EDGES = 20000
MAX_POINTS = 200000
MAX_CANVAS_TEXT = 20000
COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def _canvas_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _text(value: object, what: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{what}: text must be a string")
    if len(value) > MAX_CANVAS_TEXT:
        raise ValueError(f"{what}: text is longer than {MAX_CANVAS_TEXT} characters")


def _id(item: object, what: str, seen: set[str]) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"{what} must be an object")
    key = item.get("id")
    if not isinstance(key, str) or not key:
        raise ValueError(f"{what}: id must be a non-empty string")
    if key in seen:
        raise ValueError(f"{what}: duplicate id {key!r}")
    seen.add(key)
    return item


def _hidden(item: dict, what: str) -> None:
    """unlawHidden: the eye of the Layers panel (Obsidian ignores the key and still shows the item)."""
    if "unlawHidden" in item and not isinstance(item["unlawHidden"], bool):
        raise ValueError(f"{what}: unlawHidden must be true or false")


def _validate_node(node: dict) -> None:
    what = f"node {node['id']!r}"
    _hidden(node, what)
    if node.get("type") not in NODE_TYPES:
        raise ValueError(f"{what}: type must be one of {', '.join(sorted(NODE_TYPES))}")
    for key in ("x", "y", "width", "height"):
        if not _canvas_number(node.get(key)):
            raise ValueError(f"{what}: {key} must be a number")
    if "text" in node:
        _text(node["text"], what)


def _validate_edge(edge: dict) -> None:
    what = f"edge {edge['id']!r}"
    for key in ("fromNode", "toNode"):
        if not isinstance(edge.get(key), str) or not edge[key]:
            raise ValueError(f"{what}: {key} must be a non-empty string")
    if "label" in edge:
        _text(edge["label"], what)
    # The spot of the card an end is tied to (thread tool), as fractions of the card box.
    for key in ("unlawFrom", "unlawTo"):
        spot = edge.get(key)
        if key in edge and not (
            isinstance(spot, list) and len(spot) == 2 and all(_canvas_number(v) and 0 <= v <= 1 for v in spot)
        ):
            raise ValueError(f"{what}: {key} must be [x, y] with numbers 0-1")


def _validate_element(element: dict) -> int:
    """Check one drawing element; returns how many points it has."""
    what = f"element {element['id']!r}"
    _hidden(element, what)
    kind = element.get("type")
    if kind not in ELEMENT_TYPES:
        raise ValueError(
            f"{what}: type must be one of {', '.join(sorted(ELEMENT_TYPES))}"
        )
    for key in ("x", "y", "width", "height"):
        if not _canvas_number(element.get(key)):
            raise ValueError(f"{what}: {key} must be a number")
    if "angle" in element and not _canvas_number(element["angle"]):
        raise ValueError(f"{what}: angle must be a number")
    if "stroke" in element and not (
        isinstance(element["stroke"], str) and COLOR.fullmatch(element["stroke"])
    ):
        raise ValueError(f"{what}: stroke must look like #rrggbb")
    fill = element.get("fill")
    if fill is not None and not (isinstance(fill, str) and COLOR.fullmatch(fill)):
        raise ValueError(f"{what}: fill must be #rrggbb or null")
    width = element.get("strokeWidth")
    if "strokeWidth" in element and not (
        _canvas_number(width) and 1 <= width <= MAX_STROKE_WIDTH
    ):
        raise ValueError(f"{what}: strokeWidth must be 1-{MAX_STROKE_WIDTH}")
    rough = element.get("roughness")
    if "roughness" in element and not (_canvas_number(rough) and 0 <= rough <= 2):
        raise ValueError(f"{what}: roughness must be 0-2")
    if "seed" in element and (
        isinstance(element["seed"], bool) or not isinstance(element["seed"], int)
    ):
        raise ValueError(f"{what}: seed must be an integer")
    size = element.get("fontSize")
    if "fontSize" in element and not (_canvas_number(size) and 8 <= size <= 200):
        raise ValueError(f"{what}: fontSize must be 8-200")
    if kind == "text" or "text" in element:
        if "text" not in element:
            raise ValueError(f"{what}: text is missing")
        _text(element["text"], what)
    count = 0
    if kind in POINT_TYPES or "points" in element:
        count = _points(element.get("points"), f"{what}: points")
    if "holes" in element:
        holes = element["holes"]
        if not isinstance(holes, list):
            raise ValueError(f"{what}: holes must be a list of point lists")
        for ring in holes:
            count += _points(ring, f"{what}: holes")
    return count


def _points(points: object, what: str) -> int:
    if not isinstance(points, list):
        raise ValueError(f"{what} must be a list of [x, y]")
    for point in points:
        if not (
            isinstance(point, list)
            and len(point) == 2
            and all(_canvas_number(value) for value in point)
        ):
            raise ValueError(f"{what} must be a list of [x, y] numbers")
    return len(points)


def _validate_unlaw(extra: object) -> None:
    if not isinstance(extra, dict):
        raise ValueError("unlaw must be an object")
    if extra.get("version") != 1 or isinstance(extra.get("version"), bool):
        raise ValueError("unlaw.version must be 1")
    background = extra.get("background")
    if "background" in extra and not (
        isinstance(background, str) and COLOR.fullmatch(background)
    ):
        raise ValueError("unlaw.background must look like #rrggbb")
    elements = extra.get("elements")
    if not isinstance(elements, list):
        raise ValueError("unlaw.elements must be a list")
    if len(elements) > MAX_ELEMENTS:
        raise ValueError(f"unlaw.elements has more than {MAX_ELEMENTS} elements")
    seen: set[str] = set()
    points = 0
    for element in elements:
        points += _validate_element(_id(element, "element", seen))
        if points > MAX_POINTS:
            raise ValueError(f"unlaw.elements has more than {MAX_POINTS} points")


def validate_canvas(data: object) -> dict:
    """The document with `nodes` and `edges` present; ValueError says what is wrong."""
    if not isinstance(data, dict):
        raise ValueError("a canvas must be a JSON object")
    for key, limit in (("nodes", MAX_NODES), ("edges", MAX_EDGES)):
        if key not in data:
            data[key] = []
        if not isinstance(data[key], list):
            raise ValueError(f"{key} must be a list")
        if len(data[key]) > limit:
            raise ValueError(f"{key} has more than {limit} entries")
    seen: set[str] = set()
    for node in data["nodes"]:
        _validate_node(_id(node, "node", seen))
    seen = set()
    for edge in data["edges"]:
        _validate_edge(_id(edge, "edge", seen))
    if "unlaw" in data:
        _validate_unlaw(data["unlaw"])
    return data


def render_canvas(data: dict) -> bytes:
    """Obsidian's layout: tab indentation, real Unicode."""
    return json.dumps(validate_canvas(data), indent="\t", ensure_ascii=False).encode(
        "utf-8"
    )


def parse_canvas(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError(f"the canvas is not UTF-8 text: {error}") from error
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f"the canvas is not valid JSON: {error}") from error
    return validate_canvas(data)


def read_canvas(path: Path) -> tuple[str, dict]:
    """(version, document) of a canvas file; the version is a hash of its bytes."""
    raw = path.read_bytes()
    return version_of(raw), parse_canvas(raw)


def write_canvas(path: Path, data: dict) -> str:
    """Replace the file atomically (temporary file next to it, then rename); returns the new version."""
    raw = render_canvas(data)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=".canvas.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # The temporary file is created 0600; the canvas keeps the mode it had.
        try:
            os.chmod(temporary, path.stat().st_mode & 0o7777)
        except FileNotFoundError:
            pass
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return version_of(raw)


# ---- link cards: a page's title, description and picture, fetched once by the desk server ----
# Only public addresses (no localhost, LAN, link-local, metadata services): a canvas from someone else could
# otherwise make the desk probe this Mac's network. The connection goes to the address that was checked, so a
# second DNS answer cannot swap it, and every redirect is checked again.
LINK_TIMEOUT = 5
LINK_MAX_PAGE = 1024 * 1024
LINK_MAX_IMAGE = 5 * 1024 * 1024
LINK_REDIRECTS = 3
LINK_DEADLINE = 15  # seconds for one page or picture, redirects included
LINK_MAX_ICON = 1024 * 1024
PREVIEW_FOLDER = "attachments/.previews"


# Networks `ipaddress.is_global` still calls global but that lead back inside: IPv4-compatible IPv6, NAT64
# (64:ff9b::/96 wraps any IPv4, 127.0.0.1 included) and the old site-local block.
_INNER_NETWORKS = tuple(ipaddress.ip_network(net) for net in ("::/96", "64:ff9b::/96", "64:ff9b:1::/48", "fec0::/10"))


def _allowed(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return _allowed(address.ipv4_mapped)
        if any(address in network for network in _INNER_NETWORKS):
            return False
    return address.is_global and not address.is_multicast


def _public_address(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Unknown host {host}") from error
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if _allowed(address):
            return str(address)
    raise ValueError(f"{host} is not a public address")


class _PinnedHTTP(http.client.HTTPConnection):
    """Connects to the address that was checked, whatever DNS says the second time."""

    def __init__(self, host: str, port: int, address: str) -> None:
        super().__init__(host, port, timeout=LINK_TIMEOUT)
        self.address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self.address, self.port), LINK_TIMEOUT)


class _PinnedHTTPS(_PinnedHTTP):
    default_port = 443

    def connect(self) -> None:
        super().connect()
        self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)


def _read_until(response: http.client.HTTPResponse, limit: int, deadline: float) -> bytes:
    """At most `limit` bytes, and never past `deadline`: a server dripping a byte at a time cannot hold the desk."""
    parts, size = [], 0
    while size < limit:
        if time.monotonic() > deadline:
            raise ValueError("The page took too long")
        chunk = response.read1(min(65536, limit - size)) if hasattr(response, "read1") else response.read(min(65536, limit - size))
        if not chunk:
            break
        parts.append(chunk)
        size += len(chunk)
    return b"".join(parts)


def _fetch_public(url: str, limit: int) -> tuple[str, str, bytes, dict[str, str]]:
    """GET an http(s) URL from a public address: (final URL, content type, at most `limit` bytes, the headers
    that say whether the page may be framed)."""
    deadline = time.monotonic() + LINK_DEADLINE
    for _ in range(LINK_REDIRECTS + 1):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Only http and https links have a preview")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        kind = _PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP
        connection = kind(parts.hostname, port, _public_address(parts.hostname, port))
        try:
            target = (parts.path or "/") + ("?" + parts.query if parts.query else "")
            connection.request("GET", target, headers={
                "Host": parts.netloc.rsplit("@", 1)[-1],
                "User-Agent": "Mozilla/5.0 (Macintosh) unlaw-desk",
                "Accept": "text/html,application/xhtml+xml,image/*;q=0.8,*/*;q=0.5",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urllib.parse.urljoin(url, response.getheader("Location") or "")
                continue
            if response.status != 200:
                raise ValueError(f"The page answered {response.status}")
            body = _read_until(response, limit, deadline)
            headers = {name: ", ".join(response.headers.get_all(name) or []) for name in ("x-frame-options", "content-security-policy")}
            return url, (response.getheader("Content-Type") or "").split(";")[0].strip().lower(), body, headers
        except (OSError, http.client.HTTPException) as error:
            raise ValueError(f"Could not reach {parts.hostname}: {error}") from error
        finally:
            connection.close()
    raise ValueError("Too many redirects")


def _page_meta(raw: bytes, charset_hint: str = "") -> dict:
    """<title> and the og:/twitter: tags of a page."""
    text = raw.decode(charset_hint or "utf-8", errors="replace")
    found = re.search(r"""<meta[^>]+charset=["']?([\w-]+)""", text[:4096], re.I)
    if found and not charset_hint:
        try:
            text = raw.decode(found[1], errors="replace")
        except LookupError:
            pass

    class Meta(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.meta: dict[str, str] = {}
            self.icons: list[tuple[str, str, str]] = []  # (rel, href, sizes) of <link rel=...icon...>
            self.title: list[str] = []
            self.in_title = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            values = {key.lower(): value or "" for key, value in attrs}
            if tag == "title":
                self.in_title = True
            elif tag == "meta":
                name = (values.get("property") or values.get("name") or "").lower()
                if name and "content" in values:
                    self.meta.setdefault(name, values["content"])
            elif tag == "link" and "icon" in values.get("rel", "").lower() and values.get("href") and len(self.icons) < 50:
                self.icons.append((values["rel"].lower(), values["href"], values.get("sizes", "")))

        def handle_endtag(self, tag: str) -> None:
            if tag == "title":
                self.in_title = False

        def handle_data(self, data: str) -> None:
            if self.in_title:
                self.title.append(data)

    parser = Meta()
    try:
        parser.feed(text)
    except Exception:  # noqa: BLE001  (a broken page still gives what was read)
        pass
    meta = parser.meta
    return {
        "title": meta.get("og:title") or meta.get("twitter:title") or "".join(parser.title),
        "description": meta.get("og:description") or meta.get("twitter:description") or meta.get("description") or "",
        "image": meta.get("og:image") or meta.get("og:image:url") or meta.get("twitter:image") or "",
        "icon": _best_icon(parser.icons),
    }


def _best_icon(icons: list[tuple[str, str, str]]) -> str:
    """The site's logo: the biggest apple-touch-icon (made for home screens, so it is large and square), else the
    biggest other icon that is not SVG (the card draws pictures only); empty means /favicon.ico."""

    def size(sizes: str) -> int:
        found = re.findall(r"(\d+)x\d+", sizes)
        return max((int(value) for value in found), default=0)

    usable = [(rel, href, sizes) for rel, href, sizes in icons if not href.lower().split("?")[0].endswith(".svg")]
    for wanted in (lambda rel: "apple-touch-icon" in rel, lambda rel: True):
        picked = [icon for icon in usable if wanted(icon[0])]
        if picked:
            return max(picked, key=lambda icon: size(icon[2]))[1]
    return ""


def frameable(headers: dict[str, str]) -> bool:
    """Whether a browser will show the page inside the desk: X-Frame-Options or a CSP frame-ancestors list that
    does not let any http page in (the desk is http://127.0.0.1) means no."""
    if headers.get("x-frame-options", "").strip():
        return False
    for policy in headers.get("content-security-policy", "").split(","):
        for directive in policy.split(";"):
            words = directive.split()
            if words and words[0].lower() == "frame-ancestors":
                return any(word in ("*", "http:") for word in words[1:])
    return True


# The picture's own first bytes say what it is (a server's Content-Type is often wrong for icons).
PICTURE_MAGIC = ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"), (b"\x00\x00\x01\x00", ".ico"))


def _picture_suffix(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return next((suffix for magic, suffix in PICTURE_MAGIC if data.startswith(magic)), None)


def _save_picture(url: str, limit: int, folder: Path) -> str | None:
    """Download a picture of a page into `folder`/attachments/.previews (named by its hash, so the same logo is
    kept once); its path relative to the canvas, or None when it is missing or not a picture."""
    try:
        _, _, picture, _ = _fetch_public(url, limit)
    except ValueError:
        return None
    suffix = _picture_suffix(picture)
    if suffix is None:
        return None
    name = hashlib.sha256(picture).hexdigest()[:16] + suffix
    target = folder / PREVIEW_FOLDER / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_name("." + name + ".part")
        temporary.write_bytes(picture)
        os.replace(temporary, target)
    return f"{PREVIEW_FOLDER}/{name}"


def _clean_line(text: str, limit: int) -> str:
    return " ".join("".join(char for char in text if char.isprintable() or char.isspace()).split())[:limit]


def link_preview(url: object, folder: Path) -> dict:
    """{title, description, site, image, icon, frameable}: image (the page's picture) and icon (the site's logo)
    are saved under `folder`/attachments/.previews (so the card works offline), as paths relative to the canvas,
    or None; frameable says whether the page can be shown inside the desk."""
    if not isinstance(url, str) or len(url) > 4000:
        raise ValueError("url must be a link")
    final, kind, body, headers = _fetch_public(url.strip(), LINK_MAX_PAGE)
    site = urllib.parse.urlsplit(final).hostname or ""
    page = kind in ("text/html", "application/xhtml+xml", "")
    meta = _page_meta(body) if page else {"title": "", "description": "", "image": "", "icon": ""}
    image = _save_picture(urllib.parse.urljoin(final, meta["image"]), LINK_MAX_IMAGE, folder) if meta["image"] else None
    icon = _save_picture(urllib.parse.urljoin(final, meta["icon"] or "/favicon.ico"), LINK_MAX_ICON, folder)
    return {
        "title": _clean_line(meta["title"], 300) or site,
        "description": _clean_line(meta["description"], 600),
        "site": site,
        "image": image,
        "icon": icon,
        "frameable": page and frameable(headers),
    }

"""The Studio's Edit tab for `ul desk`: a track timeline in vanilla JS (no framework, no build step).

It works like DaVinci Resolve and Premiere Pro: video, audio, text and subtitle tracks the user adds and
names, linked picture and sound clips that can be cut apart (Alt-click), lift and ripple delete, a blade
tool, trims bound by the source, snapping, mute/solo/lock. The edit lives in project.json under `edit`
(capture_project.validate_edit, version 2); recorded files are never changed.

Playback: Web Audio plays every sound clip sample-exact and is the clock; the video elements follow it (a
browser that cannot decode a big screen recording in time only drops frames, the voice never stutters).
Light copies from `ul capture proxy` are played when ready. Captions and texts are drawn here to PNG and
uploaded into the project's assets/, because the export burns them in with ffmpeg's overlay filter.
"""

EDIT_CSS = r""".editor { display: grid; grid-template-columns: var(--pool, 250px) 6px minmax(260px, 1fr) 6px var(--insp, 290px);
  grid-template-rows: auto minmax(150px, 1fr) 6px var(--tl, 330px); height: calc(100vh - 150px); min-height: 560px; }
.editor .edbar { grid-column: 1 / -1; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding-bottom: 6px; }
.editor .edbar b { font-size: 13px; }
.editor .edbar .tools { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.editor .edbar .tools button { border: 0; border-radius: 0; display: inline-flex; align-items: center; gap: 4px; }
.editor .edbar .tools button.on, .editor .edbar button.on { background: var(--accent); color: var(--on-accent); }
.editor .edbar > button { display: inline-flex; align-items: center; gap: 4px; }
.editor .pane { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: auto; min-height: 0; min-width: 0; }
.editor .pane h5 { margin: 0; padding: 8px 10px 6px; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.editor .edpool { grid-column: 1; grid-row: 2; padding-bottom: 8px; }
.editor .edinspect { grid-column: 5; grid-row: 2; padding-bottom: 8px; }
.editor .edinspect textarea { width: calc(100% - 20px); margin: 0 10px 6px; box-sizing: border-box; }
.editor .edview { grid-column: 3; grid-row: 2; display: flex; flex-direction: column; gap: 6px; min-height: 0; min-width: 0; }
.editor .vg { grid-row: 2; cursor: col-resize; border-radius: 3px; }
.editor .vg.left { grid-column: 2; } .editor .vg.right { grid-column: 4; }
.editor .hg { grid-column: 1 / -1; grid-row: 3; cursor: row-resize; border-radius: 3px; }
.editor .vg:hover, .editor .hg:hover { background: var(--line); }
.editor .edpool .row, .editor .edinspect .row, .editor .edinspect .prow { padding: 3px 10px; }
.editor .edinspect .row { display: flex; flex-wrap: wrap; gap: 4px; }
.editor .media { display: flex; align-items: center; gap: 8px; margin: 3px 8px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 7px; cursor: grab; background: var(--bg); }
.editor .media .ico { flex: none; }
.editor .media span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.editor .media button { padding: 2px 7px; font-size: 11px; }
.editor .edpool button.wide { display: flex; align-items: center; gap: 6px; width: calc(100% - 16px); margin: 3px 8px; }
.editor .note { padding: 0 10px; font-size: 11px; color: var(--muted); }
.editor .caplist { display: flex; flex-direction: column; gap: 2px; padding: 0 6px; }
.editor .caplist .cap { display: grid; grid-template-columns: 54px 1fr; gap: 6px; align-items: center; padding: 3px 4px; border-radius: 5px; }
.editor .caplist .cap.on { background: color-mix(in srgb, var(--accent) 22%, transparent); }
.editor .caplist .cap span { font: 11px ui-monospace, monospace; color: var(--muted); cursor: pointer; }
.editor .caplist .cap input { width: 100%; min-width: 0; font-size: 12px; }
.editor .edview .stagebox { flex: 1; min-height: 0; position: relative; container-type: size; display: grid; place-items: center; }
.editor .stageui { display: none; }
.editor .stage { pointer-events: none; }
.editor .edview canvas.edwave { position: absolute; inset: 0; width: 100%; height: 100%; display: block; border-radius: 8px; background: var(--panel); }
.editor .edover { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
.editor .edover .edgap { position: absolute; inset: 0; background: #000; display: none; }
.editor .edover .ecap { position: absolute; left: 50%; transform: translateX(-50%); text-align: center; max-width: 84%; font-weight: 700; line-height: 1.2; white-space: pre-wrap; }
.editor .edover img { position: absolute; transform: translate(-50%, -50%); }
.editor .edtrans { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.editor .edtrans .clock { font: 600 15px ui-monospace, monospace; min-width: 120px; text-align: center; }
.editor .edtl { grid-column: 1 / -1; grid-row: 4; display: grid; grid-template-rows: 30px 26px minmax(0, 1fr); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; position: relative; }
.editor .tlbar { display: flex; align-items: center; gap: 6px; padding: 0 8px; border-bottom: 1px solid var(--line); }
.editor .tlbar button { display: inline-flex; align-items: center; gap: 4px; }
.editor .tlbar .tc { font: 600 13px ui-monospace, monospace; min-width: 110px; }
.editor .tlbar input[type=range] { width: 110px; }
.editor .rulerrow { display: grid; grid-template-columns: var(--head) 1fr; border-bottom: 1px solid var(--line); }
.editor .rulerrow canvas, .editor .tlbody canvas { display: block; width: 100%; touch-action: none; }
.editor .rulerrow canvas { height: 26px; cursor: pointer; }
.editor .tlbody { display: grid; grid-template-columns: var(--head) 1fr; overflow-y: auto; overflow-x: hidden; min-height: 0; align-content: start; }
.editor .heads { border-right: 1px solid var(--line); }
.editor .trow { display: flex; align-items: center; gap: 2px; padding: 0 4px 0 8px; border-bottom: 1px solid color-mix(in srgb, var(--line) 60%, transparent); box-sizing: border-box; overflow: hidden; }
.editor .trow.on { background: color-mix(in srgb, var(--accent) 16%, transparent); }
.editor .trow .tname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; cursor: default; }
.editor .trow .tag { font: 600 10px ui-monospace, monospace; color: var(--muted); width: 22px; }
.editor .trow button { padding: 1px 5px; font: 600 10px ui-monospace, monospace; min-width: 20px; }
.editor .trow button.solo.on { background: #e8b500; color: #000; }
.editor .trow button.mute.on { background: #e5484d; color: #fff; }
.editor .trow .ib { width: 22px; height: 22px; }
.editor .playhead { position: absolute; top: 30px; bottom: 0; width: 2px; margin-left: -1px; background: var(--energy); pointer-events: none; z-index: 2; }
.editor .playhead::before { content: ""; position: absolute; top: 0; left: -5px; border: 6px solid transparent; border-top: 8px solid var(--energy); }
.editor.busy { opacity: .7; }
.edpick { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.audioview { display: flex; flex-direction: column; gap: 8px; }
.audioview canvas { width: 100%; height: 280px; display: block; border-radius: 10px; background: var(--panel); border: 1px solid var(--line); }
"""

EDIT_JS = r"""// ---- Edit tab: tracks of clips like DaVinci Resolve and Premiere Pro ----
Object.assign(STUDIO_ICON, {
  pointer: "M5 3l14 8-6 2-2 6z",
  blade: "M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM8.1 8.1L20 20M8.1 15.9L20 4",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  magnet: "M6 3v9a6 6 0 0 0 12 0V3h-4v9a2 2 0 0 1-4 0V3z",
  start: "M6 5v14M18 5l-9 7 9 7z",
  end: "M18 5v14M6 5l9 7-9 7z",
  rewind: "M11 5l-8 7 8 7zM21 5l-8 7 8 7z",
  forward: "M13 5l8 7-8 7zM3 5l8 7-8 7z",
});
const ED_RATE = 25;  // waveform bars per second
const ED_HEAD = 176;
const ED_ROW = { video: 56, audio: 62, text: 30, subtitle: 30 };
const ED_FILL = { video: "#3c6fd6", audio: "#2c9a6a", text: "#8456ea", subtitle: "#178fa6" };
const ED_KIND_NAME = { video: "Video", audio: "Audio", text: "Text", subtitle: "Subtitles" };
const ED_TAG = { video: "V", audio: "A", text: "T", subtitle: "S" };
const ED_SOURCE_NAME = { recording: "Recording", mic: "Mic", system: "Mac sound" };
const CAPTION_DEFAULT = { font: "system-ui", size: 54, color: "#ffffff", outline: "#000000", box: false, position: "bottom" };
const CAPTION_FONTS = [["system-ui", "System"], ["serif", "Serif"], ["monospace", "Mono"], ["rounded", "Rounded"]];
const ED_LANGUAGES = [["", "Detect"], ["en", "English"], ["ru", "Русский"], ["az", "Azərbaycan"], ["tr", "Türkçe"], ["de", "Deutsch"], ["fr", "Français"], ["es", "Español"], ["uk", "Українська"]];
const ED_FONT_CSS = { "system-ui": "system-ui, -apple-system, sans-serif", serif: "Georgia, serif", monospace: "ui-monospace, Menlo, monospace", rounded: "ui-rounded, 'SF Pro Rounded', system-ui, sans-serif" };
const ed = { zoom: 0, scroll: 0, t: 0, playing: false, sel: new Set(), tool: "select", track: null, in: null, out: null,
  snap: localStorage.getItem("edit-snap") !== "off", linked: localStorage.getItem("edit-linked") !== "off", rows: Number(localStorage.getItem("edit-rows")) || 1,
  peaks: null, peaksFor: "", rec: {}, recFor: "", assetPeaks: {}, imported: [], busy: "",
  language: localStorage.getItem("edit-language") || "", model: localStorage.getItem("edit-model") || "", models: null,
  proxy: { state: "idle", files: {} }, proxyFor: "", proxyTimer: 0,
  ctx: null, buffers: {}, nodes: [], playT0: 0, playAt: 0, playPerf: 0, raf: 0, drawTimer: 0, assetTimer: 0, audioTimer: 0,
  drag: null, frameClip: null, frameScene: null, overlayKey: "", observer: null, warned: {} };

// ---- pure model (tested in tests/test_desk_ui.cjs; the export reads the same in capture_project.py) ----
function round3(value) { return Math.round(value * 1000) / 1000; }
function edId(list, prefix) { let n = 1; const used = new Set(list.map((item) => item.id)); while (used.has(prefix + n)) n++; return prefix + n; }
function clipEnd(clip) { return clip.start + clip.out - clip.in; }
function trackOf(edit, id) { return edit.tracks.find((track) => track.id === id) || null; }
function kindOf(edit, clip) { const track = trackOf(edit, clip.track); return track ? track.kind : ""; }
function trackLocked(edit, id) { const track = trackOf(edit, id); return !track || track.locked; }
function newTrack(id, kind, name) { return { id, kind, name, hidden: false, muted: false, solo: false, locked: false, volume: 1 }; }
function defaultTracks() {
  return [newTrack("s1", "subtitle", "Subtitles"), newTrack("t1", "text", "Text"), newTrack("v1", "video", "Video 1"),
    newTrack("a1", "audio", "Mic"), newTrack("a2", "audio", "Mac sound"), newTrack("a3", "audio", "Music")];
}
function screenHasSound(segment) { return Boolean(segment.files.screen) && !(segment.info && segment.info.screen && segment.info.screen.audio === false); }
function recordingSounds(project) {
  return { mic: project.segments.some((segment) => segment.files.mic), system: project.segments.some(screenHasSound) };
}
function audioOnly(project) { return !project.segments.some((segment) => segment.files.screen || segment.files.camera); }
function soundClip(id, track, source, start, from, to, link, more) {
  return Object.assign({ id, track, source, start, in: from, out: to, link, name: "", asset: "", volume: 1, fade_in: 0, fade_out: 0 }, more || {});
}
function defaultEdit(project) {
  const edit = { version: 2, tracks: defaultTracks(), clips: [], caption_style: { ...CAPTION_DEFAULT } };
  if (project.duration > 0) insertMedia(edit, project, "recording", 0, {});
  return edit;
}
function editOf(project) {
  if (!project.edit && project.duration > 0) project.edit = defaultEdit(project);
  return project.edit && project.edit.version === 2 ? project.edit : null;
}
function edLength(edit) { return round3(edit.clips.reduce((end, clip) => Math.max(end, clipEnd(clip)), 0)); }
function freshLink(edit, taken) {
  const used = new Set([...edit.clips.map((clip) => clip.link), ...(taken || [])]);
  let n = 1;
  while (used.has("l" + n)) n++;
  return "l" + n;
}
function linkedIds(edit, ids) {
  const links = new Set(), out = new Set(ids);
  for (const clip of edit.clips) if (out.has(clip.id) && clip.link) links.add(clip.link);
  for (const clip of edit.clips) if (clip.link && links.has(clip.link)) out.add(clip.id);
  return [...out];
}
// Split one clip at timeline time t; the right part is returned (placed after it in the list).
function splitClip(edit, clip, t) {
  const cut = round3(clip.in + t - clip.start);
  const right = { ...clip, id: edId(edit.clips, "c"), start: round3(t), in: cut };
  if ("fade_in" in clip) { right.fade_in = 0; clip.fade_out = 0; }
  clip.out = cut;
  edit.clips.splice(edit.clips.indexOf(clip) + 1, 0, right);
  return right;
}
// Cut at t: the given clips, or every clip under t on an unlocked track. Right halves of a linked group stay
// linked to each other (a cut picture and its sound still move together). Returns how many clips were cut.
function bladeAt(edit, t, ids) {
  const wanted = ids ? new Set(ids) : null;
  const hit = edit.clips.filter((clip) => (!wanted || wanted.has(clip.id)) && !trackLocked(edit, clip.track) && t > clip.start + 0.02 && t < clipEnd(clip) - 0.02);
  const links = {}, taken = [];
  for (const clip of hit) {
    const right = splitClip(edit, clip, t);
    if (clip.link) {
      if (!links[clip.link]) { links[clip.link] = freshLink(edit, taken); taken.push(links[clip.link]); }
      right.link = links[clip.link];
    }
  }
  return hit.length;
}
function liftClips(edit, ids) {
  const gone = new Set(ids), before = edit.clips.length;
  edit.clips = edit.clips.filter((clip) => !gone.has(clip.id) || trackLocked(edit, clip.track));
  return edit.clips.length < before;
}
// Make [a, b) of a track empty (overwrite): clips inside go, clips across the edges are trimmed or split.
// Returns whether anything changed.
function clearRange(edit, trackId, a, b, except, links) {
  let changed = false;
  links = links || {};
  for (const clip of edit.clips.filter((item) => item.track === trackId && !(except && except.has(item.id)))) {
    const start = clip.start, end = clipEnd(clip);
    if (end <= a + 1e-6 || start >= b - 1e-6) continue;
    changed = true;
    if (start >= a - 1e-6 && end <= b + 1e-6) { edit.clips.splice(edit.clips.indexOf(clip), 1); continue; }
    if (start < a && end > b) {
      // The right part is a new piece: like the blade, linked right parts get one fresh link of their own, so
      // the left part and the right part are not one group.
      const right = splitClip(edit, clip, b);
      if (clip.link) right.link = links[clip.link] || (links[clip.link] = freshLink(edit, Object.values(links)));
      clip.out = round3(clip.in + a - start);
      continue;
    }
    if (start < a) clip.out = round3(clip.in + a - start);
    else { clip.in = round3(clip.in + b - start); clip.start = round3(b); }
  }
  return changed;
}
// Empty [a, b) on every unlocked track and leave the gap (Premiere's lift).
function liftRange(edit, a, b) {
  let changed = false;
  const links = {};
  for (const track of edit.tracks) if (!track.locked && clearRange(edit, track.id, a, b, null, links)) changed = true;
  return changed;
}
// Take [a, b) out of every unlocked track and close the gap (Premiere's extract, Resolve's ripple).
function extractRange(edit, a, b) {
  if (!(b - a > 0.01)) return false;
  const links = {};
  for (const track of edit.tracks) {
    if (track.locked) continue;
    clearRange(edit, track.id, a, b, null, links);
    for (const clip of edit.clips) if (clip.track === track.id && clip.start >= b - 1e-6) clip.start = round3(clip.start - (b - a));
  }
  return true;
}
function mergeRanges(ranges) {
  const sorted = ranges.filter(([a, b]) => b - a > 1e-6).sort((x, y) => x[0] - y[0]), out = [];
  for (const [a, b] of sorted) {
    const last = out[out.length - 1];
    if (last && a <= last[1] + 1e-6) last[1] = Math.max(last[1], b); else out.push([a, b]);
  }
  return out;
}
function rippleDelete(edit, ids) {
  const chosen = edit.clips.filter((clip) => ids.includes(clip.id) && !trackLocked(edit, clip.track));
  if (!chosen.length) return false;
  const ranges = mergeRanges(chosen.map((clip) => [clip.start, clipEnd(clip)]));
  liftClips(edit, chosen.map((clip) => clip.id));
  for (const [a, b] of ranges.reverse()) extractRange(edit, a, b);
  return true;
}
// Move clips by dt seconds and rowDelta tracks (only onto unlocked tracks of the same kind); what they land on
// is overwritten. Returns false (and changes nothing) when a clip cannot go there.
function moveClips(edit, ids, dt, rowDelta) {
  const moving = edit.clips.filter((clip) => ids.includes(clip.id) && !trackLocked(edit, clip.track));
  if (!moving.length) return false;
  const targets = new Map();
  for (const clip of moving) {
    const target = edit.tracks[edit.tracks.findIndex((track) => track.id === clip.track) + rowDelta];
    if (!target || target.kind !== kindOf(edit, clip) || target.locked) return false;
    targets.set(clip.id, target.id);
  }
  const shift = Math.max(-Math.min(...moving.map((clip) => clip.start)), dt);
  const except = new Set(moving.map((clip) => clip.id));
  for (const clip of moving) { clip.track = targets.get(clip.id); clip.start = round3(clip.start + shift); }
  for (const clip of moving) clearRange(edit, clip.track, clip.start, clipEnd(clip), except);
  return true;
}
// How far a clip's source reaches: the recording, an imported sound (once its length is known), or free.
function sourceLimit(project, clip) {
  if (clip.source === "recording" || clip.source === "mic" || clip.source === "system") return [0, project.duration];
  if (clip.source === "asset") { const known = ed.assetPeaks[clip.asset]; return [0, known && known.duration ? known.duration : Infinity]; }
  return [-Infinity, Infinity];
}
// Drag one edge of a clip (and of its linked partners at the same place) to t, stopping at the source's ends
// and at the neighbours on each track.
function trimClip(edit, id, side, t, project, linked) {
  const clip = edit.clips.find((item) => item.id === id);
  if (!clip || trackLocked(edit, clip.track)) return false;
  const edgeOf = (item) => side === "start" ? item.start : clipEnd(item);
  const edge = edgeOf(clip);
  const group = linked && clip.link ? edit.clips.filter((item) => item.link === clip.link && Math.abs(edgeOf(item) - edge) < 1e-3 && !trackLocked(edit, item.track)) : [clip];
  const members = new Set(group.map((item) => item.id));
  let low = side === "start" ? 0 : -Infinity, high = Infinity;
  for (const item of group) {
    const [min, max] = sourceLimit(project, item);
    const others = edit.clips.filter((other) => other.track === item.track && !members.has(other.id));
    if (side === "start") {
      low = Math.max(low, item.start - (item.in - min), ...others.filter((other) => clipEnd(other) <= item.start + 1e-6).map(clipEnd));
      high = Math.min(high, clipEnd(item) - 0.05);
    } else {
      low = Math.max(low, item.start + 0.05);
      high = Math.min(high, item.start + (max - item.in), ...others.filter((other) => other.start >= clipEnd(item) - 1e-6).map((other) => other.start));
    }
  }
  if (low > high) return false;
  const next = round3(Math.max(low, Math.min(high, t)));
  for (const item of group) {
    if (side !== "start") item.out = round3(item.in + next - item.start);
    else if (sourceLimit(project, item)[0] === -Infinity) {
      // Text and captions have no source to slide through: the start moves, `in` stays 0 (the project refuses
      // a negative one) and the length follows.
      const end = clipEnd(item);
      item.start = next; item.out = round3(item.in + end - next);
    } else { item.in = round3(item.in + next - item.start); item.start = next; }
  }
  return true;
}
function covering(edit, kind, t) {
  const rows = new Map(edit.tracks.map((track, index) => [track.id, index]));
  return edit.clips.filter((clip) => { const track = trackOf(edit, clip.track); return track && track.kind === kind && !track.hidden && t >= clip.start - 1e-9 && t < clipEnd(clip) - 1e-9; })
    .sort((a, b) => rows.get(a.track) - rows.get(b.track));
}
function videoAt(edit, t) { return covering(edit, "video", t)[0] || null; }  // the upper track covers the lower
function captionAt(edit, t) { return covering(edit, "subtitle", t)[0] || null; }
function textsAt(edit, t) { return covering(edit, "text", t).reverse(); }  // lower tracks first, the upper drawn over
function audibleClips(edit) {
  const audio = edit.tracks.filter((track) => track.kind === "audio");
  const solo = audio.some((track) => track.solo);
  const heard = new Set(audio.filter((track) => !track.muted && (!solo || track.solo)).map((track) => track.id));
  return edit.clips.filter((clip) => heard.has(clip.track));
}
function addTrack(edit, kind) {
  const prefix = { video: "v", audio: "a", text: "t", subtitle: "s" }[kind];
  const id = edId(edit.tracks, prefix);
  const same = edit.tracks.map((item, index) => [item, index]).filter(([item]) => item.kind === kind);
  const track = newTrack(id, kind, ED_KIND_NAME[kind] + " " + (same.length + 1));
  let at;
  if (kind === "audio") at = same.length ? same[same.length - 1][1] + 1 : edit.tracks.length;
  else if (same.length) at = same[0][1];  // a new picture, text or subtitle layer goes on top of its kind
  else at = { subtitle: 0, text: edit.tracks.filter((item) => item.kind === "subtitle").length, video: edit.tracks.filter((item) => item.kind !== "audio").length }[kind];
  edit.tracks.splice(at, 0, track);
  return track;
}
function firstTrack(edit, kind, skip) {
  return edit.tracks.find((track) => track.kind === kind && !track.locked && !(skip || []).includes(track.id)) || addTrack(edit, kind);
}
// Put media on the timeline at t (overwriting what is there): the recording as linked picture + mic + Mac
// sound, one of its parts, a text, or an imported sound. Returns the new clip ids.
function insertMedia(edit, project, kind, t, where) {
  where = where || {};
  const start = round3(Math.max(0, t)), length = round3(project.duration), added = [];
  const place = (clip) => { clearRange(edit, clip.track, clip.start, clipEnd(clip), null); edit.clips.push(clip); added.push(clip.id); };
  if (kind === "recording" || kind === "picture" || kind === "mic" || kind === "system") {
    const sounds = recordingSounds(project), link = kind === "recording" ? freshLink(edit) : "";
    if ((kind === "recording" || kind === "picture") && !audioOnly(project)) place({ id: edId(edit.clips, "c"), track: where.video || firstTrack(edit, "video").id, source: "recording", start, in: 0, out: length, link });
    let mic = null;
    if ((kind === "recording" || kind === "mic") && sounds.mic) { mic = where.mic || firstTrack(edit, "audio").id; place(soundClip(edId(edit.clips, "c"), mic, "mic", start, 0, length, link)); }
    if ((kind === "recording" || kind === "system") && sounds.system) place(soundClip(edId(edit.clips, "c"), where.system || firstTrack(edit, "audio", mic ? [mic] : []).id, "system", start, 0, length, link));
  } else if (kind === "text") {
    place({ id: edId(edit.clips, "c"), track: where.track || firstTrack(edit, "text").id, source: "text", start, in: 0, out: where.length || 3, link: "",
      text: where.text || "Title", asset: "", x: 0.5, y: 0.2, w: 0.4, color: "#ffffff", background: "" });
  } else if (kind === "asset") {
    const span = where.length || 10;
    const free = edit.tracks.find((track) => track.kind === "audio" && !track.locked && !edit.clips.some((clip) => clip.track === track.id && clipEnd(clip) > start && clip.start < start + span));
    place(soundClip(edId(edit.clips, "c"), where.track || (free || addTrack(edit, "audio")).id, "asset", start, 0, round3(span), "", { asset: where.asset, name: (where.name || "Sound").slice(0, 200) }));
  }
  return added;
}
function toggleLink(edit, ids) {
  const clips = edit.clips.filter((clip) => ids.includes(clip.id));
  if (clips.some((clip) => clip.link)) {
    const group = new Set(linkedIds(edit, ids));
    for (const clip of edit.clips) if (group.has(clip.id)) clip.link = "";
    return "unlinked";
  }
  if (clips.length < 2) return "";
  const link = freshLink(edit);
  for (const clip of clips) clip.link = link;
  return "linked";
}
// Where the recording's sound sits: per part, its file and how far into the part that file starts.
function soundParts(project, source) {
  const parts = [];
  let begin = 0;
  project.segments.forEach((segment, index) => {
    const track = source === "mic" ? "mic" : "screen";
    const file = source === "mic" ? segment.files.mic : screenHasSound(segment) ? segment.files.screen : null;
    if (file) parts.push({ segment: index, begin: round3(begin), end: round3(begin + segment.duration), file, offset: (segment.starts || {})[track] || 0 });
    begin += segment.duration;
  });
  return parts;
}
// Lines of the recording's clock -> subtitle clips, through the clips that carry the voice (mic, else picture).
function captionsToClips(edit, project, lines) {
  const voice = edit.clips.filter((clip) => clip.source === "mic");
  const carriers = voice.length ? voice : edit.clips.filter((clip) => clip.source === "recording" || clip.source === "system");
  const track = firstTrack(edit, "subtitle");
  edit.clips = edit.clips.filter((clip) => clip.track !== track.id);
  let count = 0, last = 0;
  for (const line of [...lines].sort((a, b) => a.in - b.in)) {
    const parts = carriers.map((clip) => {
      const low = Math.max(line.in, clip.in), high = Math.min(line.out, clip.out);
      return high > low ? [clip.start + low - clip.in, clip.start + high - clip.in] : null;
    }).filter(Boolean).sort((a, b) => a[0] - b[0]);
    if (!parts.length || !line.text) continue;
    const start = round3(Math.max(last, parts[0][0])), end = round3(parts[parts.length - 1][1]);
    if (end - start < 0.05) continue;
    edit.clips.push({ id: edId(edit.clips, "c"), track: track.id, source: "caption", start, in: 0, out: round3(end - start), link: "", text: String(line.text).slice(0, 500), asset: "" });
    last = end;
    count++;
  }
  return count;
}
function mergeCaption(edit, id) {
  const clip = edit.clips.find((item) => item.id === id);
  if (!clip || clip.source !== "caption") return false;
  const next = edit.clips.filter((item) => item.track === clip.track && item.start > clip.start).sort((a, b) => a.start - b.start)[0];
  if (!next) return false;
  clip.out = round3(clip.in + clipEnd(next) - clip.start);
  clip.text = (clip.text + " " + next.text).trim().slice(0, 500);
  clip.asset = "";
  edit.clips.splice(edit.clips.indexOf(next), 1);
  return true;
}
// Quiet stretches (peaks below `level` for at least `least` seconds), shrunk by `pad` on both sides.
function silences(peaks, rate, level, least, pad) {
  const found = [];
  let start = -1;
  for (let i = 0; i <= peaks.length; i++) {
    const quiet = i < peaks.length && peaks[i] < level;
    if (quiet && start < 0) start = i;
    if (!quiet && start >= 0) {
      const a = start / rate + pad, b = i / rate - pad;
      if (i / rate - start / rate >= least && b - a > 0.05) found.push([round3(a), round3(b)]);
      start = -1;
    }
  }
  return found;
}
// Cut every pause of the voice (recording-clock peaks of the mic) out of the timeline; returns the seconds removed.
function removeSilences(edit, project, peaks) {
  const quiet = silences(peaks, ED_RATE, 0.12, 0.6, 0.12);
  const voice = edit.clips.filter((clip) => clip.source === "mic" && !trackLocked(edit, clip.track));
  const carriers = voice.length ? voice : edit.clips.filter((clip) => clip.source === "system");
  const ranges = [];
  for (const clip of carriers) for (const [a, b] of quiet) {
    const low = Math.max(a, clip.in), high = Math.min(b, clip.out);
    if (high - low > 0.05) ranges.push([round3(clip.start + low - clip.in), round3(clip.start + high - clip.in)]);
  }
  const merged = mergeRanges(ranges);
  for (const [a, b] of [...merged].reverse()) extractRange(edit, a, b);
  return round3(merged.reduce((sum, [a, b]) => sum + b - a, 0));
}
function snapTime(t, targets, tolerance) {
  let best = t, distance = tolerance;
  for (const target of targets) if (Math.abs(target - t) < distance) { best = target; distance = Math.abs(target - t); }
  return best;
}
function edEdges(edit, except) {
  const edges = [0];
  for (const clip of edit.clips) if (!except || !except.has(clip.id)) edges.push(clip.start, clipEnd(clip));
  return edges;
}
function hashText(text) {
  let a = 0x811c9dc5, b = 0x01000193;
  for (let i = 0; i < text.length; i++) { const code = text.charCodeAt(i); a = Math.imul(a ^ code, 16777619) >>> 0; b = Math.imul(b ^ code, 2246822519) >>> 0; }
  return a.toString(16).padStart(8, "0") + b.toString(16).padStart(8, "0");
}
function captionAssetName(text, style) { return "cap-" + hashText(text + "\u0000" + JSON.stringify(style)) + ".png"; }
function textAssetName(item) { return "text-" + hashText([item.text, item.color, item.background].join("\u0000")) + ".png"; }
// Sound of several parts on one clock: [{start, peaks, duration}] -> bars at `rate`.
function joinPeaks(parts, duration, rate) {
  const out = new Array(Math.max(1, Math.ceil(duration * rate))).fill(0);
  for (const part of parts) {
    const per = part.duration / Math.max(1, part.peaks.length);
    part.peaks.forEach((value, i) => {
      const at = Math.floor((part.start + i * per) * rate);
      if (at >= 0 && at < out.length && value > out[at]) out[at] = value;
    });
  }
  return out;
}
function soundFiles(project) {
  const files = [];
  let start = 0;
  for (const segment of project.segments) {
    const track = segment.files.mic ? "mic" : screenHasSound(segment) ? "screen" : null;
    if (track) files.push({ file: segment.files[track], start: start + ((segment.starts || {})[track] || 0), duration: segment.duration });
    start += segment.duration;
  }
  return files;
}
function edTimecode(t) {
  const frames = Math.max(0, Math.round(t * 30));
  const two = (n) => String(n).padStart(2, "0");
  return two(Math.floor(frames / 108000)) + ":" + two(Math.floor(frames / 1800) % 60) + ":" + two(Math.floor(frames / 30) % 60) + ":" + two(frames % 30);
}
function selIds() { if (!ed.sel || typeof ed.sel.has !== "function") ed.sel = new Set(); return [...ed.sel]; }

// ---- loading: waves, light copies, speech models ----
async function edWave(project, file, bars) {
  const { status, data } = await api("GET", "/api/studio/project/wave?path=" + encodeURIComponent(project.path) + "&file=" + encodeURIComponent(file) + "&bars=" + bars);
  return status === 200 && Array.isArray(data.peaks) ? data : null;
}
// The whole recording's sound on one clock (the Projects page of an audio project).
async function edPeaks(project) {
  if (ed.peaksFor === project.path && ed.peaks) return ed.peaks;
  ed.peaksFor = project.path;
  ed.peaks = null;
  const parts = [];
  for (const item of soundFiles(project)) {
    const wave = await edWave(project, item.file, Math.max(10, Math.min(20000, Math.round(item.duration * ED_RATE))));
    if (wave) parts.push({ start: item.start, peaks: wave.peaks, duration: wave.duration || item.duration });
  }
  if (ed.peaksFor !== project.path) return null;
  ed.peaks = joinPeaks(parts, project.duration, ED_RATE);
  drawAudioView();
  return ed.peaks;
}
// The mic and the Mac sound separately, on the recording's clock, for the audio clips' waves.
async function edRecordingPeaks(project) {
  if (ed.recFor === project.path) return;
  ed.recFor = project.path;
  ed.rec = {};
  for (const source of ["mic", "system"]) {
    const parts = [];
    for (const part of soundParts(project, source)) {
      const wave = await edWave(project, part.file, Math.max(10, Math.min(20000, Math.round((part.end - part.begin) * ED_RATE))));
      if (wave) parts.push({ start: part.begin + part.offset, peaks: wave.peaks, duration: wave.duration || part.end - part.begin });
    }
    if (ed.recFor !== project.path) return;
    if (parts.length) ed.rec[source] = joinPeaks(parts, project.duration, ED_RATE);
    edDraw();
  }
  if (studio.tab === "edit") edPool();
  if (!$("stage")) drawAudioWave();
}
async function edAssetPeaks(project, asset) {
  if (ed.assetPeaks[asset]) return;
  ed.assetPeaks[asset] = { peaks: [], duration: 0 };
  const wave = await edWave(project, "assets/" + asset, 4000);
  if (wave) ed.assetPeaks[asset] = { peaks: wave.peaks, duration: wave.duration || 0 };
  edDraw();
}
async function edProxies(project) {
  if (ed.proxyFor !== project.path) { ed.proxyFor = project.path; ed.proxy = { state: "idle", files: {} }; }
  clearTimeout(ed.proxyTimer);
  const url = "/api/studio/project/proxy?path=" + encodeURIComponent(project.path);
  let { status, data } = await api("GET", url);
  if (status === 200 && data.state !== "running" && data.state !== "done") ({ status, data } = await api("POST", "/api/studio/project/proxy", { path: project.path }));
  if (studio.project !== project || status !== 200 || !data || typeof data.state !== "string") return;
  const was = ed.proxy.state;
  ed.proxy = { state: data.state, files: data.files || {}, error: data.error || "" };
  if (data.state === "running" && studio.tab === "edit") ed.proxyTimer = setTimeout(() => edProxies(project), 1500);
  if (data.state === "done" && was !== "done") { edShowFrame(true); edLoadSounds(project); if (ed.playing) edRestartAudio(); }
  edProxyNote();
}
function edProxyNote() {
  const node = $("edProxy");
  if (!node) return;
  const state = ed.proxy.state;
  node.textContent = state === "running" ? "Preparing light copies for smooth playback…" : state === "failed" ? "Light copies failed (" + (ed.proxy.error || "unknown") + "); playing the originals" : "";
}
async function edLoadModels() {
  const { status, data } = await api("GET", "/api/studio/speech-models");
  ed.models = status === 200 && Array.isArray(data) ? data : [];
  if (!ed.models.some((item) => item.id === ed.model)) ed.model = ed.models.length ? ed.models[0].id : "";
  if (state.view === "studio" && studio.tab === "edit") edPool();
}

// ---- opening and leaving ----
async function openEdit(path) {
  if (!studio.project || studio.project.path !== path) await openProject(path);
  if (!studio.project) return;
  edEnter();
}
function edEnter() {
  const project = studio.project;
  studio.tab = "edit";
  localStorage.setItem("studio-tab", "edit");
  localStorage.setItem("studio-edit-path", project.path);
  const fresh = !project.edit;
  editOf(project);
  if (fresh && project.edit) { startHistory(project); saveProjectSoon(); }
  ed.t = 0; ed.sel = new Set(); ed.in = ed.out = null; ed.zoom = 0; ed.scroll = 0; ed.track = null; ed.frameClip = null;
  if (ed.proxyFor !== project.path) ed.imported = [];
  const player = studio.player;
  if (player) {
    // In the editor Web Audio plays every sound: the media elements only show pictures.
    clearInterval(player.timer);
    player.timer = 0;
    player.playing = false;
    for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause();
    player.screen.muted = true;
  }
  if (!ed.ctx && typeof AudioContext !== "undefined") { try { ed.ctx = new AudioContext({ latencyHint: "interactive" }); } catch (error) { ed.ctx = null; } }
  renderStudioBody();
  edProxies(project);
  edLoadSounds(project);
  if (ed.models === null) edLoadModels();
}
function edLeave() {
  edPause();
  clearTimeout(ed.proxyTimer);
  const player = studio.player;
  if (player) {
    player.screen.muted = false;
    player.segment = -1;  // the Projects page loads its own files again
    if (!player.timer) player.timer = setInterval(syncPlayer, 200);
  }
  if (ed.observer) { ed.observer.disconnect(); ed.observer = null; }
  ed.buffers = {};
}

// ---- changes: every one is undoable and saved ----
function edChanged(redraw) {
  rememberEdit();
  saveProjectSoon();
  edScheduleAssets();
  if (ed.playing) edRestartAudio();
  if (redraw === "all") { renderEdit(); return; }
  edHeads();
  edDraw();
  renderEditSide();
  edOverlay(true);
  edShowFrame(true);
}

// ---- playback: Web Audio is the clock, the pictures follow ----
function edNow() {
  if (!ed.playing) return ed.t;
  const elapsed = ed.ctx ? ed.ctx.currentTime - ed.playAt : (performance.now() - ed.playPerf) / 1000;
  return ed.playT0 + Math.max(0, elapsed);
}
function edAudioFile(source, file) {
  const proxy = ed.proxy.files && ed.proxy.files[file];
  if (proxy && proxy.audio) return proxy.audio;
  return source === "mic" ? file : null;  // the Mac sound needs its light copy (the screen file is huge)
}
function edClipPieces(project, clip) {
  if (clip.source === "asset") return [{ url: projectMedia(project.path, "assets/" + clip.asset), start: clip.start, offset: clip.in, length: clip.out - clip.in }];
  const pieces = [];
  for (const part of soundParts(project, clip.source)) {
    const file = edAudioFile(clip.source, part.file);
    if (!file) continue;
    // The file covers [begin + offset, end] of the recording.
    const low = Math.max(clip.in, part.begin + Math.max(0, part.offset)), high = Math.min(clip.out, part.end);
    if (high - low <= 0.001) continue;
    pieces.push({ url: projectMedia(project.path, file), start: clip.start + low - clip.in, offset: low - part.begin - part.offset, length: high - low });
  }
  return pieces;
}
function edLoadBuffer(url) {
  if (ed.buffers[url] || !ed.ctx || typeof ed.ctx.decodeAudioData !== "function") return;
  ed.buffers[url] = "loading";
  fetch(url).then((response) => response.arrayBuffer()).then((bytes) => ed.ctx.decodeAudioData(bytes)).then((buffer) => {
    ed.buffers[url] = buffer;
    if (ed.playing) edRestartAudio();
  }).catch(() => { ed.buffers[url] = "failed"; });
}
function edLoadSounds(project) {
  const edit = project.edit;
  if (!edit || !ed.ctx) return;
  for (const clip of edit.clips) if (kindOf(edit, clip) === "audio") for (const piece of edClipPieces(project, clip)) edLoadBuffer(piece.url);
}
function edStopAudio() {
  for (const node of ed.nodes) { try { node.stop(); } catch (error) { /* it had already ended */ } }
  ed.nodes = [];
}
function edScheduleAudio() {
  edStopAudio();
  const project = studio.project, edit = project && project.edit, ctx = ed.ctx;
  if (!edit || !ctx || typeof ctx.createBufferSource !== "function") return;
  const t0 = ed.playT0, at0 = ed.playAt, when = (t) => at0 + (t - t0);
  let missing = false;
  for (const clip of audibleClips(edit)) {
    const track = trackOf(edit, clip.track), volume = clip.volume * track.volume, end = clipEnd(clip);
    if (end <= t0 || volume <= 0) continue;
    const gainAt = (t) => volume * Math.max(0, Math.min(1, clip.fade_in > 0 ? (t - clip.start) / clip.fade_in : 1, clip.fade_out > 0 ? (end - t) / clip.fade_out : 1));
    for (const piece of edClipPieces(project, clip)) {
      const pieceEnd = piece.start + piece.length;
      if (pieceEnd <= t0) continue;
      const buffer = ed.buffers[piece.url];
      if (!buffer || typeof buffer === "string") { if (!buffer) edLoadBuffer(piece.url); missing = true; continue; }
      const begin = Math.max(piece.start, t0);
      const source = ctx.createBufferSource(), gain = ctx.createGain();
      source.buffer = buffer;
      source.connect(gain);
      gain.connect(ctx.destination);
      gain.gain.setValueAtTime(gainAt(begin), when(begin));
      if (clip.fade_in > 0 && begin < clip.start + clip.fade_in) gain.gain.linearRampToValueAtTime(volume, when(clip.start + clip.fade_in));
      if (clip.fade_out > 0) {
        const from = Math.max(begin, end - clip.fade_out);
        gain.gain.setValueAtTime(gainAt(from), when(from));
        gain.gain.linearRampToValueAtTime(0, when(end));
      }
      source.start(when(begin), Math.max(0, piece.offset + begin - piece.start), pieceEnd - begin);
      ed.nodes.push(source);
    }
  }
  if (missing && !ed.warned.audio) { ed.warned.audio = true; toast("Some sound is still loading; it joins in a moment"); }
}
function edRestartAudio() {
  if (!ed.playing) return;
  ed.t = edNow();
  ed.playT0 = ed.t;
  ed.playAt = ed.ctx ? ed.ctx.currentTime + 0.05 : 0;
  ed.playPerf = performance.now() + 50;
  edScheduleAudio();
}
function edSeek(t) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  ed.t = round3(Math.max(0, Math.min(edLength(edit), t)));
  if (ed.playing) edRestartAudio();
  edShowFrame(true);
  edPlayhead();
  edOverlay();
}
function edPlay() {
  const edit = studio.project && studio.project.edit;
  if (!edit || ed.playing) return;
  if (ed.t >= edLength(edit) - 0.05) ed.t = 0;
  if (ed.ctx && ed.ctx.state === "suspended" && ed.ctx.resume) ed.ctx.resume();
  ed.playing = true;
  ed.warned.audio = false;
  ed.playT0 = ed.t;
  ed.playAt = ed.ctx ? ed.ctx.currentTime + 0.05 : 0;
  ed.playPerf = performance.now() + 50;
  edScheduleAudio();
  edShowFrame(true);
  cancelAnimationFrame(ed.raf);
  ed.raf = requestAnimationFrame(edLoop);
  edClock();
}
function edPause() {
  if (ed.playing) ed.t = round3(edNow());
  ed.playing = false;
  cancelAnimationFrame(ed.raf);
  edStopAudio();
  const player = studio.player;
  if (player) for (const track of ["screen", "camera"]) if (player[track].pause) player[track].pause();
  edShowFrame(true);
  edClock();
}
function edToggle() { if (ed.playing) edPause(); else edPlay(); }
function edLoop() {
  const edit = studio.project && studio.project.edit;
  if (!ed.playing || !edit) return;
  ed.t = edNow();
  const end = edLength(edit);
  if (ed.t >= end) { ed.t = end; edPause(); edPlayhead(); return; }
  edShowFrame(false);
  edFollow();
  edPlayhead();
  edOverlay();
  ed.raf = requestAnimationFrame(edLoop);
}
function edMediaFile(file) {
  const proxy = ed.proxy.files && ed.proxy.files[file];
  return proxy && proxy.video ? proxy.video : file;
}
// The picture at the playhead: the top visible video clip moves the screen/camera elements to its moment.
function edShowFrame(force) {
  const project = studio.project, edit = project && project.edit, player = studio.player;
  if (!edit) return;
  if (!$("stage")) { drawAudioWave(); return; }
  const clip = videoAt(edit, ed.t);
  const gap = $("edGap");
  if (gap) gap.style.display = clip ? "none" : "block";
  if (!clip || !player) {
    if (player) for (const track of ["screen", "camera"]) if (player[track].pause && !player[track].paused) player[track].pause();
    ed.frameClip = null;
    return;
  }
  const recording = clip.in + ed.t - clip.start;
  const { segment, local } = projectClock(project, recording);
  if (segment < 0) return;
  const part = project.segments[segment], starts = part.starts || {};
  const jumped = force || ed.frameClip !== clip.id || player.segment !== segment;
  player.segment = segment;
  for (const track of ["screen", "camera"]) {
    const file = part.files[track], node = player[track];
    if (file) { const url = projectMedia(project.path, edMediaFile(file)); if (node._src !== url) { node._src = url; node.src = url; } }
    else if (node._src) { node.pause(); if (node.removeAttribute) node.removeAttribute("src"); node._src = ""; }
  }
  ed.frameClip = clip.id;
  player.t = recording;
  for (const track of ["screen", "camera"]) {
    if (!part.files[track]) continue;
    const node = player[track], wanted = Math.max(0, local - (starts[track] || 0));
    if (jumped) { setMediaTime(node, wanted); node.playbackRate = 1; } else if (ed.playing) follow(node, wanted);
    if (ed.playing && node.paused && !node.ended) playMedia(node);
    if (!ed.playing && !node.paused) node.pause();
  }
  const scene = sceneAt(project, recording);
  if (scene !== ed.frameScene) { ed.frameScene = scene; drawStage(); }
}
function edClock() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  for (const id of ["edClock", "edTc"]) { const node = $(id); if (node) node.textContent = edTimecode(ed.t); }
  const total = $("edTotal");
  if (total) total.textContent = "/ " + edTimecode(edLength(edit));
  const play = $("edPlay");
  if (play && play._playing !== ed.playing) { play._playing = ed.playing; play.textContent = ""; play.append(studioIcon(ed.playing ? "pause" : "play")); }
}

// ---- the page ----
function edLayout() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("edit-layout") || "{}") || {}; } catch (error) { saved = {}; }
  const pick = (value, low, high, fallback) => Number.isFinite(value) && value >= low && value <= high ? value : fallback;
  return { pool: pick(saved.pool, 160, 700, 250), insp: pick(saved.insp, 200, 700, 290), tl: pick(saved.tl, 150, 1400, 330) };
}
function renderEdit() {
  const box = $("studioEdit");
  if (!box) return;
  box.textContent = "";
  const project = studio.project;
  if (!project) { edPicker(box); return; }
  const edit = editOf(project);
  if (!edit) { box.append(h("div", { class: "empty", text: "This project has nothing recorded to edit." })); return; }
  const video = !audioOnly(project);
  const layout = edLayout();
  const root = h("div", { class: "editor" + (ed.busy ? " busy" : ""), id: "edRoot", style: "--pool:" + layout.pool + "px;--insp:" + layout.insp + "px;--tl:" + layout.tl + "px;--head:" + ED_HEAD + "px" });
  const tool = (name, icon, label, title) => h("button", { class: ed.tool === name ? "on" : "", title, onclick: () => edSetTool(name) }, studioIcon(icon), label);
  root.append(h("div", { class: "edbar" },
    h("button", { class: "ghost back", onclick: () => { edLeave(); closeProject().then(() => setStudioTab("projects")); } }, studioIcon("back"), "Projects"),
    h("b", { text: project.name }), h("span", { class: "where", id: "edLen" }),
    h("span", { class: "spacer" }),
    h("div", { class: "tools" }, tool("select", "pointer", "Select", "Selection tool (A or V)"), tool("blade", "blade", "Blade", "Blade tool: click a clip to cut it (B)")),
    h("button", { class: ed.snap ? "on" : "", title: "Snapping to the playhead and clip edges (N)", onclick: edToggleSnap }, studioIcon("magnet"), "Snap"),
    h("button", { class: ed.linked ? "on" : "", title: "Linked selection: a picture and its sound are picked together (⇧⌘L; Alt-click picks one)", onclick: edToggleLinked }, studioIcon("link"), "Linked"),
    iconButton("undo", "Undo (⌘Z; ⇧⌘Z redoes)", () => undoEdit(false)),
    video ? h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
      h("button", { class: studio.projectCanvas === value ? "on" : "", text: label, onclick: () => { studio.projectCanvas = value; ed.frameScene = null; renderEdit(); } }))) : null,
    h("button", { class: "primary", text: ed.busy === "export" ? "Preparing…" : "Export…", disabled: Boolean(ed.busy) || null, onclick: edExport })));
  root.append(h("div", { class: "pane edpool", id: "edPool" }), edGutter("left"));
  const view = h("div", { class: "edview" });
  if (video) view.append(h("div", { class: "stagebox", id: "stageBox" }, stageFrame()));
  else view.append(h("div", { class: "stagebox" }, h("canvas", { class: "edwave", id: "edWave" }), h("div", { class: "edover", id: "edOver" })));
  view.append(h("div", { class: "edtrans" },
    iconButton("start", "To the start (Home)", () => edSeek(0)),
    iconButton("rewind", "Back 5 s (J)", () => edSeek(ed.t - 5)),
    h("button", { id: "edPlay", class: "ib", title: "Play / pause (Space, K stops, L plays)", "aria-label": "Play / pause", onclick: edToggle }, studioIcon(ed.playing ? "pause" : "play")),
    iconButton("forward", "Forward 5 s", () => edSeek(ed.t + 5)),
    iconButton("end", "To the end (End)", () => edSeek(edLength(edit))),
    h("span", { class: "clock", id: "edClock" }), h("span", { class: "where", id: "edTotal" }),
    h("span", { class: "spacer" }), h("span", { class: "where", id: "edProxy" })));
  root.append(view, edGutter("right"), h("div", { class: "pane edinspect", id: "edInspect" }), edGutter("bottom"));
  root.append(edTimeline());
  box.append(root);
  if (video) {
    const wrap = $("stageWrap") || $("stageBox");
    if (wrap) wrap.append(h("div", { class: "edover", id: "edOver" }, h("div", { class: "edgap", id: "edGap" })));
    watchStageSize();
    ed.frameScene = null;
  }
  edHeads();
  renderEditSide();
  edRecordingPeaks(project);
  for (const clip of edit.clips) if (clip.source === "asset") edAssetPeaks(project, clip.asset);
  if (!studio.projects.length && !studio.projectsLoaded) loadProjects();
  edSeek(ed.t);
  edClock();
  edDraw();
  edProxyNote();
  if (typeof ResizeObserver !== "undefined") {
    if (ed.observer) ed.observer.disconnect();
    ed.observer = new ResizeObserver(() => { edDraw(); edOverlay(true); });
    ed.observer.observe($("edBody"));
  }
  edScheduleAssets();
}
// Every border is draggable; the sizes are kept for the next visit.
function edGutter(kind) {
  const node = h("div", { class: kind === "bottom" ? "hg" : "vg " + kind, title: "Drag to resize" });
  node.addEventListener("pointerdown", (event) => {
    const root = $("edRoot");
    if (!root) return;
    event.preventDefault();
    const layout = edLayout(), start = { x: event.clientX, y: event.clientY, ...layout };
    const move = (moved) => {
      if (moved.buttons === 0) { up(); return; }
      if (kind === "left") layout.pool = Math.max(160, Math.min(700, start.pool + moved.clientX - start.x));
      if (kind === "right") layout.insp = Math.max(200, Math.min(700, start.insp - (moved.clientX - start.x)));
      if (kind === "bottom") layout.tl = Math.max(150, Math.min(1400, window.innerHeight - 260, start.tl - (moved.clientY - start.y)));
      root.style.setProperty("--pool", layout.pool + "px");
      root.style.setProperty("--insp", layout.insp + "px");
      root.style.setProperty("--tl", layout.tl + "px");
      localStorage.setItem("edit-layout", JSON.stringify(layout));
      edDraw();
      edOverlay(true);
    };
    const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); };
    addEventListener("pointermove", move); addEventListener("pointerup", up); addEventListener("pointercancel", up);
  });
  return node;
}
function edTimeline() {
  const rows = h("input", { type: "range", min: "0.6", max: "2", step: "0.1", value: String(ed.rows), title: "Track height" });
  rows.addEventListener("input", () => { ed.rows = Number(rows.value); localStorage.setItem("edit-rows", String(ed.rows)); edHeads(); edDraw(); });
  const zoom = (factor) => () => { ed.zoom = Math.max(0.2, Math.min(2000, (ed.zoom || 1) * factor)); edDraw(); };
  const bar = h("div", { class: "tlbar" },
    h("span", { class: "tc", id: "edTc" }),
    h("button", { title: "Add a track", onclick: (event) => edTrackMenu(event.currentTarget) }, studioIcon("plus"), "Track"),
    h("span", { class: "where", id: "edRange" }),
    h("span", { class: "spacer" }),
    h("span", { class: "lbl", text: "Height" }), rows,
    iconButton("minus", "Zoom out (⌘−, or ⌥/⌘ with the wheel)", zoom(1 / 1.5)),
    iconButton("plus", "Zoom in (⌘=)", zoom(1.5)),
    h("button", { title: "Fit the whole timeline (⇧Z)", text: "Fit", onclick: () => { ed.zoom = 0; edDraw(); } }));
  const ruler = h("canvas", { id: "edRuler", "aria-label": "Time ruler" });
  const tracks = h("canvas", { id: "edTracks", "aria-label": "Timeline tracks" });
  const body = h("div", { class: "tlbody", id: "edBody" }, h("div", { class: "heads", id: "edHeads" }), tracks);
  const node = h("div", { class: "edtl", id: "edTl" }, bar, h("div", { class: "rulerrow" }, h("div", {}), ruler), body, h("div", { class: "playhead", id: "edHead" }));
  edRulerEvents(ruler);
  edTrackEvents(tracks);
  return node;
}
function edVisibleTracks(edit) {
  const project = studio.project;
  return edit.tracks.filter((track) => !(track.kind === "video" && project && audioOnly(project)));
}
function edRowsOf(edit) {
  let y = 0;
  return edVisibleTracks(edit).map((track) => { const height = Math.round(ED_ROW[track.kind] * ed.rows); const row = { track, y, height }; y += height; return row; });
}
function edHeads() {
  const box = $("edHeads"), edit = studio.project && studio.project.edit;
  if (!box || !edit) return;
  box.textContent = "";
  for (const row of edRowsOf(edit)) {
    const track = row.track;
    const flag = (key, label, title, extra) => h("button", { class: extra + (track[key] ? " on" : ""), title, text: label, onclick: (event) => { event.stopPropagation(); edToggleTrack(track.id, key); } });
    const buttons = track.kind === "audio"
      ? [flag("muted", "M", "Mute this track", "mute"), flag("solo", "S", "Solo: hear only solo tracks", "solo")]
      : [iconButton(track.hidden ? "eyeOff" : "eye", track.hidden ? "Show this track" : "Hide this track", (event) => { event.stopPropagation(); edToggleTrack(track.id, "hidden"); }, track.hidden ? "dim" : "")];
    buttons.push(iconButton(track.locked ? "lock" : "unlock", track.locked ? "Locked: cuts, moves and ripples leave it alone" : "Lock this track", (event) => { event.stopPropagation(); edToggleTrack(track.id, "locked"); }, track.locked ? "" : "dim"));
    const same = edit.tracks.filter((item) => item.kind === track.kind), index = same.indexOf(track);
    const tag = ED_TAG[track.kind] + (track.kind === "audio" ? index + 1 : same.length - index);
    box.append(h("div", { class: "trow " + track.kind + (ed.track === track.id ? " on" : ""), style: "height:" + row.height + "px", title: "Click for its settings · double-click to rename · right-click for more",
      onclick: () => { ed.track = track.id; ed.sel = new Set(); edHeads(); edDraw(); renderEditSide(); },
      ondblclick: () => edRenameTrack(track.id), oncontextmenu: (event) => edTrackContext(event, track.id) },
      h("span", { class: "tag", text: tag }), h("span", { class: "tname", text: track.name }), ...buttons));
  }
}
function edToggleTrack(id, key) {
  const edit = studio.project && studio.project.edit, track = edit && trackOf(edit, id);
  if (!track) return;
  track[key] = !track[key];
  edChanged();
}
function cleanName(text, limit) { return String(text).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, limit); }
function edRenameTrack(id) {
  const edit = studio.project.edit, track = trackOf(edit, id);
  const name = prompt("Track name", track.name);
  if (name === null || !cleanName(name, 60)) return;
  track.name = cleanName(name, 60);
  edChanged();
}
function edTrackMenu(anchor) {
  const edit = studio.project.edit;
  const kinds = [["video", "Video track (covers the ones below)"], ["audio", "Audio track"], ["text", "Text track"], ["subtitle", "Subtitle track"]]
    .filter(([kind]) => kind !== "video" || !audioOnly(studio.project));
  openStudioMenu(anchor, kinds.map(([kind, label]) => h("button", { onclick: () => {
    closeStudioMenu();
    if (edit.tracks.length >= 40) { toast("At most 40 tracks"); return; }
    ed.track = addTrack(edit, kind).id;
    ed.sel = new Set();
    edChanged();
  } }, studioIcon("plus"), label)));
}
function edTrackContext(event, id) {
  const edit = studio.project.edit, track = trackOf(edit, id);
  const same = edit.tracks.filter((item) => item.kind === track.kind), at = same.indexOf(track);
  const swap = (other) => { const a = edit.tracks.indexOf(track), b = edit.tracks.indexOf(other); edit.tracks[a] = other; edit.tracks[b] = track; edChanged(); };
  const used = edit.clips.filter((clip) => clip.track === id).length;
  contextMenu(event, [
    ["Rename…", () => edRenameTrack(id)],
    ["Move up", () => swap(same[at - 1]), at === 0],
    ["Move down", () => swap(same[at + 1]), at === same.length - 1],
    "-",
    ["Delete track" + (used ? " and its " + used + " clip" + (used === 1 ? "" : "s") : ""), () => {
      if (same.length === 1 && track.kind !== "audio") { toast("Keep one " + ED_KIND_NAME[track.kind].toLowerCase() + " track"); return; }
      if (used && !confirm("Delete the track “" + track.name + "” with its " + used + " clips?")) return;
      edit.clips = edit.clips.filter((clip) => clip.track !== id);
      edit.tracks = edit.tracks.filter((item) => item.id !== id);
      ed.track = null;
      edChanged();
    }],
  ]);
}
function edPicker(box) {
  box.append(h("div", { class: "projbar" }, h("b", { text: "Pick a project to edit" })));
  const grid = h("div", { class: "library edpick" });
  box.append(grid);
  if (!studio.projectsLoaded) loadProjects().then(() => state.view === "studio" && studio.tab === "edit" && !studio.project && renderEdit());
  if (!studio.projects.length) { grid.append(h("div", { class: "empty", text: "No projects yet. Record something on the Record tab." })); return; }
  for (const item of studio.projects.slice(0, 200)) {
    const card = projectCard(item);
    card.onclick = () => openEdit(item.path);
    grid.append(card);
  }
}
function renderEditSide() {
  edPool();
  edInspector();
  const len = $("edLen"), edit = studio.project && studio.project.edit;
  if (len && edit) len.textContent = clockText(edLength(edit));
}

// ---- media pool: what can go on the timeline ----
function edMediaItem(label, icon, payload, title) {
  const node = h("div", { class: "media", draggable: "true", title: title + " · drag it onto a track, or + puts it at the playhead" },
    studioIcon(icon), h("span", { text: label }), h("button", { text: "+", title: "Put it at the playhead", onclick: (event) => { event.stopPropagation(); edDrop(payload, ed.t, null); } }));
  node.addEventListener("dragstart", (event) => { if (event.dataTransfer) { event.dataTransfer.setData("application/x-unlaw-edit", JSON.stringify(payload)); event.dataTransfer.effectAllowed = "copy"; } });
  return node;
}
function edPool() {
  const box = $("edPool"), project = studio.project;
  if (!box || !project || !project.edit) return;
  const edit = project.edit;
  box.textContent = "";
  const sounds = recordingSounds(project);
  box.append(h("h5", { text: "Media" }));
  if (!audioOnly(project)) {
    box.append(edMediaItem("Recording (picture + sound)", "screen", { kind: "recording" }, "The recording with its scenes, mic and Mac sound, linked"));
    box.append(edMediaItem("Picture only", "scene", { kind: "picture" }, "The composed picture without sound"));
  }
  if (sounds.mic) box.append(edMediaItem("Mic", "mic", { kind: "mic" }, "The microphone of the recording"));
  if (sounds.system) box.append(edMediaItem("Mac sound", "speaker", { kind: "system" }, "The sound of the Mac (apps, video calls)"));
  const assets = new Map();
  for (const clip of edit.clips) if (clip.source === "asset" && !assets.has(clip.asset)) assets.set(clip.asset, clip.name || clip.asset);
  for (const item of ed.imported) if (!assets.has(item.asset)) assets.set(item.asset, item.name);
  for (const [asset, name] of assets) box.append(edMediaItem(name, "audio", { kind: "asset", asset, name }, "An imported sound"));
  box.append(edMediaItem("Text", "text", { kind: "text" }, "A title over the picture (T)"));
  const file = h("input", { type: "file", accept: "audio/*,.m4a,.mp3,.wav,.flac,.aac,.aiff,.caf", style: "display:none" });
  file.addEventListener("change", () => { if (file.files[0]) edImportFile(file.files[0]); file.value = ""; });
  box.append(file,
    h("button", { class: "wide", onclick: () => file.click() }, studioIcon("audio"), "Import music or a sound…"),
    h("button", { class: "wide", onclick: (event) => edVoiceMenu(event.currentTarget) }, studioIcon("mic"), "Voice-over from an audio recording…"));
  box.append(h("h5", { text: "Subtitles" }));
  const language = studioSelect(ED_LANGUAGES, ed.language, (value) => { ed.language = value; localStorage.setItem("edit-language", value); });
  const models = ed.models === null ? [["", "Looking for speech models…"]] : ed.models.length ? ed.models.map((item) => [item.id, item.id.split("/").pop() + (item.default ? " (default)" : "")]) : [["", "No speech model"]];
  const model = studioSelect(models, ed.model, (value) => { ed.model = value; localStorage.setItem("edit-model", value); });
  box.append(prow("Language", language), prow("Model", model));
  const captions = edit.clips.filter((clip) => clip.source === "caption").sort((a, b) => a.start - b.start);
  box.append(h("div", { class: "row" }, h("button", { text: ed.busy === "transcribe" ? "Listening…" : captions.length ? "Transcribe again" : "Transcribe", disabled: Boolean(ed.busy) || (ed.models !== null && !ed.models.length) || null, onclick: edTranscribe })));
  if (ed.models !== null && !ed.models.length) box.append(h("p", { class: "note", text: "Download one in a terminal: ul lm pull mlx-community/whisper-large-v3-turbo" }));
  else if (!captions.length) box.append(h("p", { class: "note", text: "Speech to text on this Mac (ul lm). The lines follow your cuts." }));
  const list = h("div", { class: "caplist" });
  for (const clip of captions.slice(0, 400)) {
    const input = h("input", { type: "text", value: clip.text, maxlength: "500" });
    input.addEventListener("change", () => { const text = cleanName(input.value, 500); if (!text) return; clip.text = text; clip.asset = ""; edChanged(); });
    input.addEventListener("focus", () => { ed.sel = new Set([clip.id]); edSeek(clip.start + 0.01); edDraw(); edInspector(); });
    list.append(h("div", { class: "cap" + (ed.sel.has(clip.id) ? " on" : "") },
      h("span", { text: clockText(clip.start), onclick: () => { ed.sel = new Set([clip.id]); edSeek(clip.start + 0.01); renderEditSide(); edDraw(); } }), input));
  }
  box.append(list);
  box.append(h("h5", { text: "Clean up" }),
    h("button", { class: "wide", disabled: (!ed.rec.mic && !ed.rec.system) || null, title: "Cut every pause of the voice longer than 0.6 s out of the timeline (⌘Z brings them back)", onclick: edRemoveSilences }, studioIcon("minus"), "Remove silences"));
}

// ---- inspector: the selected clip or track, else the subtitle style ----
function edNumber(value, onchange, step, min) {
  const input = h("input", { type: "number", value: String(round3(value)), step: String(step || 0.1), min: min === undefined ? null : String(min) });
  input.addEventListener("change", () => { const next = Number(input.value); if (Number.isFinite(next)) onchange(next); });
  return input;
}
function edVolume(value, onchange) {
  const input = h("input", { type: "range", min: "0", max: "2", step: "0.01", value: String(value) });
  const label = h("span", { class: "where", text: "" });
  const show = () => { const v = Number(input.value), db = 20 * Math.log10(v); label.textContent = v <= 0 ? "−∞ dB" : (db >= 0 ? "+" : "") + db.toFixed(1) + " dB"; };
  show();
  input.addEventListener("input", show);
  input.addEventListener("change", () => onchange(Number(input.value)));
  return [input, label];
}
function edInspector() {
  const box = $("edInspect"), project = studio.project;
  if (!box || !project || !project.edit) return;
  const edit = project.edit;
  box.textContent = "";
  const chosen = edit.clips.filter((clip) => ed.sel.has(clip.id));
  if (chosen.length > 1) {
    box.append(h("h5", { text: chosen.length + " clips" }),
      h("div", { class: "row" },
        h("button", { text: chosen.some((clip) => clip.link) ? "Unlink (⌘L)" : "Link (⌘L)", onclick: edLink }),
        h("button", { text: "Cut at playhead (⌘B)", onclick: edBladePlayhead }),
        h("button", { text: "Delete (⌫)", onclick: () => edDelete(false) }),
        h("button", { text: "Ripple delete (⇧⌫)", onclick: () => edDelete(true) })));
    return;
  }
  const clip = chosen[0];
  if (clip) {
    const kind = kindOf(edit, clip), length = clip.out - clip.in;
    const title = clip.source === "asset" ? clip.name || clip.asset : clip.source === "text" ? "Text" : clip.source === "caption" ? "Subtitle" : ED_SOURCE_NAME[clip.source];
    box.append(h("h5", { text: title + " · " + (trackOf(edit, clip.track) || {}).name }));
    if (kind === "text" || kind === "subtitle") {
      const area = h("textarea", { rows: "3", maxlength: "500" });
      area.value = clip.text;
      area.addEventListener("change", () => { const text = cleanName(area.value, 500); if (text) { clip.text = text; clip.asset = ""; edChanged(); } });
      box.append(area);
    }
    box.append(prow("Start", edNumber(clip.start, (value) => { if (moveClips(edit, [clip.id], round3(Math.max(0, value)) - clip.start, 0)) edChanged(); }, 0.1, 0)),
      prow("Length", edNumber(length, (value) => { if (value >= 0.05 && trimClip(edit, clip.id, "end", clip.start + value, project, false)) edChanged(); }, 0.1, 0.05)));
    if (kind === "video" || clip.source === "mic" || clip.source === "system" || clip.source === "asset")
      box.append(prow("Source in", edNumber(clip.in, (value) => { if (trimClip(edit, clip.id, "start", clip.start + value - clip.in, project, false)) edChanged(); }, 0.1, 0)));
    if (kind === "audio") {
      const [volume, label] = edVolume(clip.volume, (value) => { clip.volume = Math.max(0, Math.min(4, value)); edChanged(); });
      box.append(prow("Volume", volume, label),
        prow("Fade in", edNumber(clip.fade_in, (value) => { clip.fade_in = Math.max(0, Math.min(600, value)); edChanged(); }, 0.1, 0)),
        prow("Fade out", edNumber(clip.fade_out, (value) => { clip.fade_out = Math.max(0, Math.min(600, value)); edChanged(); }, 0.1, 0)));
    }
    if (kind === "text") {
      const color = h("input", { type: "color", value: clip.color || "#ffffff" });
      color.addEventListener("change", () => { clip.color = color.value; clip.asset = ""; edChanged(); });
      const back = h("input", { type: "color", value: clip.background || "#000000" });
      back.addEventListener("change", () => { clip.background = back.value; clip.asset = ""; edChanged(); });
      const slider = (key, label) => {
        const input = h("input", { type: "range", min: key === "w" ? "0.05" : "0", max: "1", step: "0.01", value: String(clip[key]) });
        input.addEventListener("input", () => { clip[key] = Number(input.value); edOverlay(true); });
        input.addEventListener("change", () => edChanged());
        return prow(label, input);
      };
      box.append(prow("Colour", color), prow("Box", back, studioCheck(Boolean(clip.background), (on) => { clip.background = on ? back.value : ""; clip.asset = ""; edChanged(); }, "show")),
        slider("x", "Across"), slider("y", "Down"), slider("w", "Width"));
    }
    if (kind === "subtitle") box.append(h("div", { class: "row" }, h("button", { text: "Merge with next", onclick: () => { if (mergeCaption(edit, clip.id)) edChanged(); } })));
    box.append(h("div", { class: "row" },
      h("button", { text: "Cut at playhead (⌘B)", onclick: edBladePlayhead }),
      h("button", { text: "Unlink (⌘L)", disabled: !clip.link || null, onclick: edLink }),
      h("button", { class: "ghost", text: "Delete (⌫)", onclick: () => edDelete(false) }),
      h("button", { class: "ghost", text: "Ripple delete (⇧⌫)", onclick: () => edDelete(true) })));
    if (kind === "subtitle") { box.append(h("hr")); edCaptionStyle(box, edit); }
    return;
  }
  const track = ed.track && trackOf(edit, ed.track);
  if (track) {
    const name = h("input", { type: "text", value: track.name, maxlength: "60" });
    name.addEventListener("change", () => { const text = cleanName(name.value, 60); if (text) { track.name = text; edChanged(); } });
    box.append(h("h5", { text: ED_KIND_NAME[track.kind] + " track" }), prow("Name", name));
    if (track.kind === "audio") {
      const [volume, label] = edVolume(track.volume, (value) => { track.volume = Math.max(0, Math.min(4, value)); edChanged(); });
      box.append(prow("Volume", volume, label), prow("Mute", studioCheck(track.muted, () => edToggleTrack(track.id, "muted"), "silent")), prow("Solo", studioCheck(track.solo, () => edToggleTrack(track.id, "solo"), "only solo tracks play")));
    } else box.append(prow("Hidden", studioCheck(track.hidden, () => edToggleTrack(track.id, "hidden"), "not shown or exported")));
    box.append(prow("Locked", studioCheck(track.locked, () => edToggleTrack(track.id, "locked"), "cuts and ripples leave it alone")));
    if (track.kind === "subtitle") { box.append(h("hr")); edCaptionStyle(box, edit); }
    return;
  }
  box.append(h("h5", { text: "Timeline" }), h("p", { class: "note", text: "Click a clip to change it, a track name for the track. Alt-click picks a picture without its sound. ⌫ deletes and leaves a gap, ⇧⌫ closes it. I and O mark a range: ' takes it out, ; leaves a gap." }));
  edCaptionStyle(box, edit);
}
function edCaptionStyle(box, edit) {
  const style = edit.caption_style;
  const restyle = () => { for (const clip of edit.clips) if (clip.source === "caption") clip.asset = ""; edChanged(); };
  const color = h("input", { type: "color", value: style.color });
  color.addEventListener("change", () => { style.color = color.value; restyle(); });
  const outline = h("input", { type: "color", value: style.outline || "#000000" });
  outline.addEventListener("change", () => { style.outline = outline.value; restyle(); });
  const size = h("input", { type: "range", min: "24", max: "120", step: "2", value: String(style.size) });
  size.addEventListener("input", () => { style.size = Number(size.value); edOverlay(true); });
  size.addEventListener("change", restyle);
  box.append(h("h5", { text: "Subtitle style" }),
    prow("Font", studioSelect(CAPTION_FONTS, style.font, (value) => { style.font = value; restyle(); })),
    prow("Size", size),
    prow("Colour", color),
    prow("Outline", outline, studioCheck(Boolean(style.outline), (on) => { style.outline = on ? outline.value : ""; restyle(); }, "on")),
    prow("Box", studioCheck(style.box, (on) => { style.box = on; restyle(); }, "dark box behind")),
    prow("Place", studioSelect([["bottom", "Bottom"], ["middle", "Middle"], ["top", "Top"]], style.position, (value) => { style.position = value; restyle(); })),
    h("p", { class: "note", text: "Exports burn the subtitles in and save a .srt next to the video." }));
}

// ---- viewer overlay: the subtitle and texts at the playhead, as the export draws them ----
function edOverlay(force) {
  const box = $("edOver"), project = studio.project, edit = project && project.edit;
  if (!box || !edit) return;
  const caption = captionAt(edit, ed.t), texts = textsAt(edit, ed.t);
  const key = [caption ? caption.id + caption.text : "", ...texts.map((item) => item.id + item.asset + item.x + item.y + item.w)].join("|");
  if (!force && key === ed.overlayKey) return;
  ed.overlayKey = key;
  for (const node of [...box.children]) if (node.id !== "edGap") node.remove();
  const frame = box.getBoundingClientRect();
  const short = Math.min(frame.width, frame.height) || 1;
  if (caption) {
    const style = edit.caption_style, scale = short / 1080;
    const node = h("div", { class: "ecap", text: caption.text });
    node.style.fontFamily = ED_FONT_CSS[style.font] || "system-ui";
    node.style.fontSize = Math.max(8, style.size * scale) + "px";
    node.style.color = style.color;
    if (style.outline) node.style.textShadow = [[-1, -1], [1, -1], [-1, 1], [1, 1], [0, 2], [2, 0], [0, -2], [-2, 0]].map(([x, y]) => x * scale * 2.5 + "px " + y * scale * 2.5 + "px 0 " + style.outline).join(",");
    if (style.box) { node.style.background = "rgba(0,0,0,.62)"; node.style.padding = "0.15em 0.5em"; node.style.borderRadius = "0.25em"; }
    const margin = Math.round(short * 0.07);
    if (style.position === "top") node.style.top = margin + "px";
    else if (style.position === "middle") { node.style.top = "50%"; node.style.transform = "translate(-50%, -50%)"; }
    else node.style.bottom = margin + "px";
    box.append(node);
  }
  for (const item of texts) {
    if (!item.asset) continue;
    const img = h("img", { src: projectMedia(project.path, "assets/" + item.asset), alt: "" });
    img.style.left = item.x * 100 + "%";
    img.style.top = item.y * 100 + "%";
    img.style.width = item.w * frame.width + "px";
    box.append(img);
  }
}
// The viewer of an audio project: the sound around the playhead, Voice Memos style.
function edWaveAt(edit, t) {
  let loudest = 0;
  for (const clip of audibleClips(edit)) {
    if (t < clip.start || t >= clipEnd(clip)) continue;
    const at = clip.in + t - clip.start;
    let value = 0;
    if (clip.source === "asset") { const wave = ed.assetPeaks[clip.asset]; if (wave && wave.duration) value = wave.peaks[Math.floor(at / wave.duration * wave.peaks.length)] || 0; }
    else if (ed.rec[clip.source]) value = ed.rec[clip.source][Math.floor(at * ED_RATE)] || 0;
    loudest = Math.max(loudest, value * clip.volume);
  }
  return Math.min(1, loudest);
}
function drawAudioWave() {
  const canvas = $("edWave"), edit = studio.project && studio.project.edit;
  if (!canvas || !edit) return;
  const box = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(2, Math.round(box.width * ratio));
  canvas.height = Math.max(2, Math.round(box.height * ratio));
  const context = canvas.getContext("2d");
  const styles = getComputedStyle(document.body);
  context.scale(ratio, ratio);
  context.clearRect(0, 0, box.width, box.height);
  const middle = box.height / 2, pps = box.width / 8, length = edLength(edit);
  context.fillStyle = (styles.getPropertyValue("--ink") || "").trim() || "#ddd";
  for (let x = 0; x < box.width; x += 3) {
    const t = ed.t + (x - box.width / 2) / pps;
    if (t < 0 || t > length) continue;
    const height = Math.max(1.5, edWaveAt(edit, t) * (box.height * 0.42));
    context.globalAlpha = t <= ed.t ? 1 : 0.4;
    context.fillRect(x, middle - height, 2, height * 2);
  }
  context.globalAlpha = 1;
  context.fillStyle = "#ff3b30";
  context.fillRect(Math.round(box.width / 2) - 1, 8, 2, box.height - 16);
}

// ---- timeline drawing: only when something changed; the playhead is its own element ----
function edFitZoom(canvas) {
  return Math.max(0.2, ((canvas.clientWidth || 800) - 30) / Math.max(10, edLength(studio.project.edit) * 1.04));
}
function edGeometry(canvas) {
  if (!ed.zoom) { ed.zoom = edFitZoom(canvas); ed.scroll = 0; }
  return { width: canvas.clientWidth || 800, x: (t) => (t - ed.scroll) * ed.zoom, t: (x) => x / ed.zoom + ed.scroll };
}
function edDraw() {
  cancelAnimationFrame(ed.drawTimer);
  ed.drawTimer = requestAnimationFrame(edPaint);
}
function edPaint() {
  const canvas = $("edTracks"), ruler = $("edRuler"), project = studio.project, edit = project && project.edit;
  if (!canvas || !edit) return;
  const rows = edRowsOf(edit), height = rows.reduce((sum, row) => sum + row.height, 0);
  canvas.style.height = height + "px";
  const ratio = window.devicePixelRatio || 1, g = edGeometry(canvas);
  canvas.width = Math.max(2, Math.round(g.width * ratio));
  canvas.height = Math.max(2, Math.round(height * ratio));
  const c = canvas.getContext("2d");
  const css = getComputedStyle(document.body), v = (name, fallback) => (css.getPropertyValue(name) || "").trim() || fallback;
  const ink = v("--ink", "#ddd"), muted = v("--muted", "#888"), line = v("--line", "#333"), accent = v("--accent", "#ffc933");
  c.scale(ratio, ratio);
  c.clearRect(0, 0, g.width, height);
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];
  const step = steps.find((value) => value * ed.zoom >= 80) || 1800;
  rows.forEach((row, index) => { c.fillStyle = index % 2 ? "rgba(127,127,127,.06)" : "rgba(127,127,127,.02)"; c.fillRect(0, row.y, g.width, row.height); c.fillStyle = line; c.fillRect(0, row.y + row.height - 1, g.width, 1); });
  c.fillStyle = "rgba(127,127,127,.12)";
  for (let t = Math.floor(ed.scroll / step) * step; g.x(t) < g.width; t += step) c.fillRect(Math.round(g.x(t)), 0, 1, height);
  const length = edLength(edit);
  if (ed.in !== null || ed.out !== null) {
    const a = g.x(ed.in ?? 0), b = g.x(ed.out ?? length);
    c.fillStyle = "rgba(120,170,255,.14)";
    c.fillRect(a, 0, Math.max(0, b - a), height);
  }
  const heard = new Set(audibleClips(edit).map((clip) => clip.track));
  c.font = "11px system-ui, sans-serif";
  c.textBaseline = "top";
  for (const row of rows) {
    const track = row.track, dim = track.hidden || (track.kind === "audio" && !heard.has(track.id));
    for (const clip of edit.clips) {
      if (clip.track !== track.id) continue;
      const x1 = g.x(clip.start), x2 = g.x(clipEnd(clip));
      if (x2 < 0 || x1 > g.width) continue;
      const left = Math.max(-4, x1), right = Math.min(g.width + 4, x2), top = row.y + 2, h2 = row.height - 5;
      c.globalAlpha = dim ? 0.38 : 1;
      c.fillStyle = ED_FILL[track.kind];
      c.beginPath(); c.roundRect(left, top, Math.max(1, right - left - 1), h2, 4); c.fill();
      c.save(); c.beginPath(); c.rect(left, top, Math.max(0, right - left - 1), h2); c.clip();
      if (track.kind === "audio") {
        const peaks = clip.source === "asset" ? null : ed.rec[clip.source], wave = clip.source === "asset" ? ed.assetPeaks[clip.asset] : null;
        c.fillStyle = "rgba(255,255,255,.55)";
        const middle = top + h2 * 0.58, scale = h2 * 0.36 * Math.min(2, clip.volume * track.volume);
        for (let x = Math.max(0, left); x < Math.min(g.width, right); x += 2) {
          const at = clip.in + g.t(x) - clip.start;
          const value = peaks ? peaks[Math.floor(at * ED_RATE)] || 0 : wave && wave.duration ? wave.peaks[Math.floor(at / wave.duration * wave.peaks.length)] || 0 : 0;
          const bar = Math.max(0.5, value * scale);
          c.fillRect(x, middle - bar, 1.5, bar * 2);
        }
        c.strokeStyle = "rgba(255,255,255,.8)";
        if (clip.fade_in > 0) { c.beginPath(); c.moveTo(x1, top + h2); c.lineTo(g.x(clip.start + clip.fade_in), top); c.stroke(); }
        if (clip.fade_out > 0) { c.beginPath(); c.moveTo(g.x(clipEnd(clip) - clip.fade_out), top); c.lineTo(x2, top + h2); c.stroke(); }
      }
      c.fillStyle = "#fff";
      const label = clip.source === "recording" ? "Recording · " + sceneName(sceneAt(project, clip.in)) : clip.source === "asset" ? clip.name || clip.asset : clip.text || ED_SOURCE_NAME[clip.source];
      c.fillText((clip.link ? "⧉ " : "") + label, Math.max(left, 0) + 5, top + 3);
      c.restore();
      if (ed.sel.has(clip.id)) { c.globalAlpha = 1; c.strokeStyle = accent; c.lineWidth = 2; c.beginPath(); c.roundRect(left + 1, top + 1, Math.max(1, right - left - 3), h2 - 2, 4); c.stroke(); c.lineWidth = 1; }
    }
  }
  c.globalAlpha = 1;
  if (ruler) {
    ruler.width = Math.max(2, Math.round(g.width * ratio));
    ruler.height = Math.round(26 * ratio);
    const r = ruler.getContext("2d");
    r.scale(ratio, ratio);
    r.clearRect(0, 0, g.width, 26);
    r.font = "10px ui-monospace, Menlo, monospace";
    r.textBaseline = "top";
    r.fillStyle = muted;
    for (let t = Math.floor(ed.scroll / step) * step; g.x(t) < g.width; t += step) {
      const x = Math.round(g.x(t));
      if (x < 0) continue;
      r.fillRect(x, 14, 1, 12);
      r.fillText(step < 1 ? edTimecode(t) : clockText(t), x + 3, 2);
      for (let k = 1; k < 5; k++) r.fillRect(Math.round(g.x(t + step * k / 5)), 21, 1, 5);
    }
    if (ed.in !== null || ed.out !== null) { r.fillStyle = "rgba(120,170,255,.45)"; const a = g.x(ed.in ?? 0), b = g.x(ed.out ?? length); r.fillRect(a, 20, Math.max(2, b - a), 6); }
    r.fillStyle = ink;
    for (const mark of edMarks(project, edit)) { const x = g.x(mark); r.beginPath(); r.moveTo(x - 4, 14); r.lineTo(x + 4, 14); r.lineTo(x, 20); r.fill(); }
  }
  const range = $("edRange");
  if (range) range.textContent = ed.in !== null || ed.out !== null ? "In " + clockText(ed.in ?? 0) + " · Out " + clockText(ed.out ?? length) + " (' takes it out, ; leaves a gap, ⌥X clears)" : "";
  edPlayhead();
}
// Recording marks where they are on the timeline (through the clips that show them).
function edMarks(project, edit) {
  const out = [];
  for (const event of project.events || []) {
    if (!("mark" in event)) continue;
    const clip = edit.clips.find((item) => (item.source === "recording" || item.source === "mic") && event.t >= item.in && event.t < item.out);
    if (clip) out.push(clip.start + event.t - clip.in);
  }
  return out;
}
function edPlayhead() {
  const node = $("edHead"), canvas = $("edTracks");
  if (node && canvas) {
    const x = (ed.t - ed.scroll) * ed.zoom;
    node.style.display = x < 0 || x > (canvas.clientWidth || 800) ? "none" : "block";
    node.style.left = ED_HEAD + x + "px";
  }
  edClock();
}
function edFollow() {
  const canvas = $("edTracks");
  if (!canvas || !ed.zoom) return;
  const visible = (canvas.clientWidth || 800) / ed.zoom;
  if (ed.t > ed.scroll + visible * 0.94 || ed.t < ed.scroll) { ed.scroll = Math.max(0, ed.t - visible * 0.1); edDraw(); }
}

// ---- timeline pointer: select, move, trim, blade, scrub; media dropped from the pool ----
function edHit(edit, canvas, event) {
  const box = canvas.getBoundingClientRect(), x = event.clientX - box.left, y = event.clientY - box.top;
  const rows = edRowsOf(edit), index = rows.findIndex((item) => y >= item.y && y < item.y + item.height);
  const g = edGeometry(canvas), t = g.t(x);
  const row = index >= 0 ? rows[index] : null;
  if (!row) return { t, row: null, index, clip: null };
  const edge = 7 / ed.zoom;
  const near = edit.clips.filter((item) => item.track === row.track.id && t >= item.start - edge && t <= clipEnd(item) + edge);
  const clip = near.find((item) => t >= item.start && t <= clipEnd(item)) || near[0] || null;
  if (!clip) return { t, row, index, clip: null };
  let side = "body";
  if ((clipEnd(clip) - clip.start) * ed.zoom > 16) side = Math.abs(t - clip.start) <= edge ? "start" : Math.abs(t - clipEnd(clip)) <= edge ? "end" : "body";
  if (side === "body" && !(t >= clip.start && t <= clipEnd(clip))) return { t, row, index, clip: null };
  return { t, row, index, clip, side };
}
function edSnapTargets(edit, except) {
  if (!ed.snap) return [];
  return [ed.t, ...(ed.in !== null ? [ed.in] : []), ...(ed.out !== null ? [ed.out] : []), ...edEdges(edit, except), ...edMarks(studio.project, edit)];
}
function edDragLoop(onmove, onup) {
  const move = (event) => { if (event.buttons === 0) { up(); return; } onmove(event); };
  const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); if (onup) onup(); };
  addEventListener("pointermove", move); addEventListener("pointerup", up); addEventListener("pointercancel", up);
}
function edRulerEvents(ruler) {
  ruler.addEventListener("pointerdown", (event) => {
    if (!studio.project || event.button !== 0) return;
    const scrub = (moved) => { const box = ruler.getBoundingClientRect(); edSeek((moved.clientX - box.left) / ed.zoom + ed.scroll); };
    scrub(event);
    edDragLoop(scrub);
  });
}
function edTrackEvents(canvas) {
  canvas.addEventListener("wheel", (event) => {
    const edit = studio.project && studio.project.edit;
    if (!edit) return;
    if (!event.ctrlKey && !event.metaKey && !event.altKey && Math.abs(event.deltaY) > Math.abs(event.deltaX) && !event.shiftKey) return;  // the wheel scrolls the tracks up and down
    event.preventDefault();
    const box = canvas.getBoundingClientRect();
    if (event.ctrlKey || event.metaKey || event.altKey) {
      const at = (event.clientX - box.left) / ed.zoom + ed.scroll;
      ed.zoom = Math.max(0.2, Math.min(2000, ed.zoom * Math.exp(-event.deltaY * 0.01)));
      ed.scroll = Math.max(0, at - (event.clientX - box.left) / ed.zoom);
    } else ed.scroll = Math.max(0, ed.scroll + (event.deltaX || event.deltaY) / ed.zoom);
    edDraw();
  }, { passive: false });
  canvas.addEventListener("pointermove", (event) => {
    if (ed.drag || !studio.project || !studio.project.edit) return;
    const hit = edHit(studio.project.edit, canvas, event);
    canvas.style.cursor = ed.tool === "blade" && hit.clip ? "crosshair" : hit.clip && hit.side !== "body" ? "ew-resize" : hit.clip ? "grab" : "default";
  });
  canvas.addEventListener("dragover", (event) => { if (event.dataTransfer && [...(event.dataTransfer.types || [])].includes("application/x-unlaw-edit")) event.preventDefault(); });
  canvas.addEventListener("drop", (event) => {
    const edit = studio.project && studio.project.edit, raw = event.dataTransfer && event.dataTransfer.getData("application/x-unlaw-edit");
    if (!edit || !raw) return;
    event.preventDefault();
    let payload;
    try { payload = JSON.parse(raw); } catch (error) { return; }
    const hit = edHit(edit, canvas, event);
    edDrop(payload, snapTime(Math.max(0, hit.t), edSnapTargets(edit), 8 / ed.zoom), hit.row ? hit.row.track : null);
  });
  canvas.addEventListener("dblclick", (event) => {
    const edit = studio.project && studio.project.edit, hit = edit && edHit(edit, canvas, event);
    const area = hit && hit.clip && (hit.clip.source === "text" || hit.clip.source === "caption") && $("edInspect") && $("edInspect").querySelector("textarea");
    if (area) area.focus();
  });
  canvas.addEventListener("contextmenu", (event) => {
    const edit = studio.project && studio.project.edit, hit = edit && edHit(edit, canvas, event);
    if (!hit || !hit.clip) return;
    if (!ed.sel.has(hit.clip.id)) { ed.sel = new Set(ed.linked && !event.altKey ? linkedIds(edit, [hit.clip.id]) : [hit.clip.id]); edDraw(); renderEditSide(); }
    const linked = selIds().some((id) => (edit.clips.find((clip) => clip.id === id) || {}).link);
    contextMenu(event, [
      ["Cut at the playhead (⌘B)", edBladePlayhead],
      ["Delete, leave a gap (⌫)", () => edDelete(false)],
      ["Ripple delete (⇧⌫)", () => edDelete(true)],
      "-",
      [linked ? "Unlink picture and sound (⌘L)" : "Link (⌘L)", edLink],
      hit.clip.source === "caption" ? ["Merge with the next line", () => { if (mergeCaption(edit, hit.clip.id)) edChanged(); }] : null,
    ]);
  });
  canvas.addEventListener("pointerdown", (event) => {
    const project = studio.project, edit = project && project.edit;
    if (!edit || event.button !== 0) return;
    const hit = edHit(edit, canvas, event);
    if (ed.tool === "blade" && hit.clip) {
      const at = snapTime(hit.t, ed.snap ? [ed.t] : [], 8 / ed.zoom);
      const ids = ed.linked && !event.altKey ? linkedIds(edit, [hit.clip.id]) : [hit.clip.id];
      if (bladeAt(edit, at, ids)) edChanged(); else toast("Too close to the clip's edge");
      return;
    }
    if (!hit.clip) {
      // An empty place: deselect and move the playhead there (drag to scrub).
      ed.sel = new Set();
      if (hit.row) ed.track = hit.row.track.id;
      edSeek(hit.t);
      edHeads(); edDraw(); renderEditSide();
      edDragLoop((moved) => { const box = canvas.getBoundingClientRect(); edSeek((moved.clientX - box.left) / ed.zoom + ed.scroll); });
      return;
    }
    const clip = hit.clip;
    const group = ed.linked && !event.altKey ? linkedIds(edit, [clip.id]) : [clip.id];
    if (event.shiftKey || event.metaKey) {
      const next = new Set(ed.sel), on = !next.has(clip.id);
      for (const id of group) if (on) next.add(id); else next.delete(id);
      ed.sel = next;
    } else if (!ed.sel.has(clip.id)) ed.sel = new Set(group);
    ed.track = null;
    edHeads(); edDraw(); renderEditSide();
    const before = JSON.stringify(edit.clips), startX = event.clientX, startY = event.clientY, startRow = hit.index;
    let moved = false;
    ed.drag = true;
    edDragLoop((pointer) => {
      if (!moved && Math.hypot(pointer.clientX - startX, pointer.clientY - startY) < 3) return;
      moved = true;
      edit.clips = JSON.parse(before);
      const delta = (pointer.clientX - startX) / ed.zoom, tolerance = 8 / ed.zoom;
      if (hit.side !== "body") {
        const edge = hit.side === "start" ? clip.start : clipEnd(clip);
        trimClip(edit, clip.id, hit.side, snapTime(edge + delta, edSnapTargets(edit, new Set(group)), tolerance), project, ed.linked && !event.altKey);
      } else {
        const ids = selIds();
        const moving = edit.clips.filter((item) => ids.includes(item.id));
        const first = Math.min(...moving.map((item) => item.start)), last = Math.max(...moving.map(clipEnd));
        const targets = edSnapTargets(edit, new Set(ids));
        let dt = delta;
        const a = snapTime(first + delta, targets, tolerance), b = snapTime(last + delta, targets, tolerance);
        if (a !== first + delta) dt = a - first; else if (b !== last + delta) dt = b - last;
        const rows = edRowsOf(edit), now = edHit(edit, canvas, pointer).index;
        const rowDelta = startRow >= 0 && now >= 0 ? edit.tracks.indexOf(rows[now].track) - edit.tracks.indexOf(rows[startRow].track) : 0;
        if (!moveClips(edit, ids, dt, rowDelta)) { edit.clips = JSON.parse(before); moveClips(edit, ids, dt, 0); }
      }
      edDraw();
      edOverlay();
    }, () => {
      ed.drag = null;
      if (JSON.stringify(edit.clips) !== before) edChanged();
      else if (!moved && clip.source !== "caption") edSeek(hit.t);
    });
  });
}
// Media from the pool onto the timeline at t (onto the given track when it fits).
function edDrop(payload, t, track) {
  const project = studio.project, edit = project && project.edit;
  if (!edit || !payload) return;
  const fits = (kind) => track && track.kind === kind && !track.locked;
  const where = {};
  if ((payload.kind === "recording" || payload.kind === "picture") && fits("video")) where.video = track.id;
  if (payload.kind === "mic" && fits("audio")) where.mic = track.id;
  if (payload.kind === "system" && fits("audio")) where.system = track.id;
  if (payload.kind === "text" && fits("text")) where.track = track.id;
  if (payload.kind === "asset") {
    Object.assign(where, { asset: payload.asset, name: payload.name, length: (ed.assetPeaks[payload.asset] && ed.assetPeaks[payload.asset].duration) || 10 });
    if (fits("audio")) where.track = track.id;
  }
  const ids = insertMedia(edit, project, payload.kind, t, where);
  if (!ids.length) { toast("Nothing to add"); return; }
  ed.sel = new Set(ids);
  edLoadSounds(project);
  edChanged();
}

// ---- actions ----
function edSetTool(tool) {
  ed.tool = tool;
  const root = $("edRoot");
  if (root && root.querySelectorAll) for (const button of root.querySelectorAll(".tools button")) button.classList.toggle("on", button.textContent === (tool === "blade" ? "Blade" : "Select"));
}
function edToggleSnap() { ed.snap = !ed.snap; localStorage.setItem("edit-snap", ed.snap ? "on" : "off"); renderEdit(); toast(ed.snap ? "Snapping on" : "Snapping off"); }
function edToggleLinked() { ed.linked = !ed.linked; localStorage.setItem("edit-linked", ed.linked ? "on" : "off"); renderEdit(); toast(ed.linked ? "Linked selection on" : "Linked selection off: picture and sound are picked apart"); }
function edBladePlayhead() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  const ids = selIds();
  const count = bladeAt(edit, ed.t, ids.length ? (ed.linked ? linkedIds(edit, ids) : ids) : null);
  if (count) edChanged(); else toast("Put the playhead inside a clip to cut");
}
function edDelete(ripple) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  if (ed.in !== null || ed.out !== null) {
    const a = ed.in ?? 0, b = ed.out ?? edLength(edit);
    if (ripple ? extractRange(edit, a, b) : liftRange(edit, a, b)) { ed.in = ed.out = null; ed.sel = new Set(); ed.t = a; edChanged(); edSeek(a); }
    return;
  }
  const ids = selIds();
  if (!ids.length) { toast("Select a clip, or mark a range with I and O"); return; }
  if (!(ripple ? rippleDelete(edit, ids) : liftClips(edit, ids))) { toast("Its track is locked"); return; }
  ed.sel = new Set();
  edChanged();
  edSeek(ed.t);
}
function edLink() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  const result = toggleLink(edit, selIds());
  if (!result) { toast("Select two clips or more to link them"); return; }
  if (result === "unlinked") ed.sel = new Set(selIds().slice(0, 1));
  edChanged();
  toast(result === "linked" ? "Linked: they move and cut together" : "Unlinked: picture and sound are separate now");
}
function edEdgeJump(direction) {
  const edges = [...new Set(edEdges(studio.project.edit).map(round3))].sort((a, b) => a - b);
  const next = direction > 0 ? edges.find((t) => t > ed.t + 0.01) : [...edges].reverse().find((t) => t < ed.t - 0.01);
  if (next !== undefined) edSeek(next);
}
function edRemoveSilences() {
  const project = studio.project, edit = project && project.edit;
  const peaks = ed.rec.mic || ed.rec.system;
  if (!edit || !peaks) return;
  const removed = removeSilences(edit, project, peaks);
  if (!removed) { toast("No pauses longer than 0.6 s"); return; }
  edChanged();
  toast("Removed " + clockText(removed) + " of pauses (⌘Z brings them back)");
}
function edAddText() {
  const project = studio.project, edit = project && project.edit;
  if (!edit) return;
  if (edit.clips.filter((clip) => clip.source === "text").length >= 500) { toast("At most 500 texts"); return; }
  ed.sel = new Set(insertMedia(edit, project, "text", ed.t, {}));
  edChanged();
}
async function edTranscribe() {
  const project = studio.project, edit = project && project.edit;
  if (!edit || ed.busy) return;
  const existing = edit.clips.filter((clip) => clip.source === "caption").length;
  if (existing && !confirm("Replace the " + existing + " subtitle lines with a new transcription?")) return;
  ed.busy = "transcribe";
  edPool();
  toast("Listening to the recording on this Mac… (a long recording takes a few minutes)");
  const { status, data } = await api("POST", "/api/studio/transcribe", { path: project.path, language: ed.language, model: ed.model });
  ed.busy = "";
  if (studio.project !== project) return;
  if (status !== 200) { toast(data.error || "Transcription failed"); edPool(); return; }
  const count = captionsToClips(edit, project, data.captions || []);
  toast(count ? count + " subtitle lines" + (data.language ? " (" + data.language + ")" : "") : "No speech found");
  edChanged();
}
async function edImportFile(file) {
  const project = studio.project;
  if (!project || !project.edit) return;
  toast("Adding " + file.name + "…");
  let response, data = {};
  try {
    response = await fetch("/api/studio/project/asset?path=" + encodeURIComponent(project.path) + "&name=" + encodeURIComponent(file.name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: file });
    data = await response.json();
  } catch (error) { data = { error: "Could not reach the desk: " + error.message }; }
  if (!response || response.status !== 200) { toast(data.error || "Upload failed"); return; }
  await edAddSound(data.asset, file.name.replace(/\.[^.]+$/, ""));
}
function edVoiceMenu(anchor) {
  const project = studio.project;
  const voices = studio.projects.filter((item) => item.path !== project.path && !item.tracks.includes("screen") && !item.tracks.includes("camera") && item.tracks.includes("mic"));
  if (!voices.length) { toast("Record one with “Record audio only” (A) on the Record tab, then add it here"); return; }
  openStudioMenu(anchor, voices.slice(0, 30).map((item) => h("button", { onclick: () => { closeStudioMenu(); edVoiceOver(item); } }, studioIcon("mic"), item.name + " · " + clockText(item.duration))));
}
async function edVoiceOver(item) {
  const { status, data } = await api("GET", "/api/studio/project?path=" + encodeURIComponent(item.path));
  if (status !== 200) { toast(data.error || "Could not read that recording"); return; }
  const files = soundFiles(data);
  if (!files.length) { toast("That recording has no sound"); return; }
  const copied = await api("POST", "/api/studio/project/import", { path: studio.project.path, from: item.path, file: files[0].file });
  if (copied.status !== 200) { toast(copied.data.error || "Could not copy the voice-over"); return; }
  await edAddSound(copied.data.asset, "Voice " + item.name.replace(/^audio-/, ""));
}
async function edAddSound(asset, name) {
  const project = studio.project;
  delete ed.assetPeaks[asset];
  await edAssetPeaks(project, asset);
  if (studio.project !== project) return;
  ed.imported.push({ asset, name: name.slice(0, 200) || "Sound" });
  edDrop({ kind: "asset", asset, name }, ed.t, null);
}

// ---- drawing captions and texts for the export (PNG into the project's assets/) ----
function edDrawText(text, options) {
  const scale = 2, size = options.size * scale;
  const measure = document.createElement("canvas").getContext("2d");
  const font = "700 " + size + "px " + (ED_FONT_CSS[options.font] || "system-ui");
  measure.font = font;
  const limit = options.wrap * scale, lines = [];
  let current = "";
  for (const word of text.split(/\s+/)) {
    const next = current ? current + " " + word : word;
    if (current && measure.measureText(next).width > limit) { lines.push(current); current = word; } else current = next;
  }
  if (current) lines.push(current);
  const pad = Math.round(size * (options.box ? 0.35 : 0.18)), lineHeight = Math.round(size * 1.22), stroke = options.outline ? Math.max(2, Math.round(size * 0.12)) : 0;
  const width = Math.ceil(Math.max(...lines.map((line) => measure.measureText(line).width))) + pad * 2 + stroke * 2;
  const height = lineHeight * lines.length + pad * 2 + stroke * 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(2, width);
  canvas.height = Math.max(2, height);
  const c = canvas.getContext("2d");
  if (options.box) { c.fillStyle = typeof options.box === "string" ? options.box : "rgba(0,0,0,0.62)"; c.beginPath(); c.roundRect(0, 0, canvas.width, canvas.height, Math.round(size * 0.25)); c.fill(); }
  c.font = font;
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.lineJoin = "round";
  lines.forEach((line, index) => {
    const y = pad + stroke + lineHeight * (index + 0.5);
    if (stroke) { c.strokeStyle = options.outline; c.lineWidth = stroke * 2; c.strokeText(line, canvas.width / 2, y); }
    c.fillStyle = options.color;
    c.fillText(line, canvas.width / 2, y);
  });
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}
async function edUpload(project, name, blob) {
  try {
    const response = await fetch("/api/studio/project/asset?path=" + encodeURIComponent(project.path) + "&name=" + encodeURIComponent(name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: blob });
    const data = await response.json();
    return response.status === 200 ? data.asset : null;
  } catch (error) { return null; }
}
// Every subtitle and text has a current PNG; returns false when one could not be drawn.
async function edEnsureAssets() {
  const project = studio.project, edit = project && project.edit;
  if (!edit || edit.version !== 2) return true;
  let changed = false, ok = true;
  const style = edit.caption_style;
  for (const clip of edit.clips) {
    if (clip.source !== "caption" && clip.source !== "text") continue;
    const name = clip.source === "caption" ? captionAssetName(clip.text, style) : textAssetName(clip);
    if (clip.asset === name || (clip.asset && clip.asset.startsWith(name.slice(0, -4) + " "))) continue;
    const blob = clip.source === "caption"
      ? await edDrawText(clip.text, { size: style.size, font: style.font, color: style.color, outline: style.outline, box: style.box, wrap: 900 })
      : await edDrawText(clip.text, { size: 120, font: "system-ui", color: clip.color || "#ffffff", outline: "", box: clip.background || false, wrap: 4000 });
    const asset = blob && await edUpload(project, name, blob);
    if (studio.project !== project) return false;
    if (asset) { clip.asset = asset; changed = true; } else ok = false;
  }
  if (changed) { studio.historyLast = JSON.stringify(project); saveProjectSoon(); edOverlay(true); }
  return ok;
}
function edScheduleAssets() {
  clearTimeout(ed.assetTimer);
  ed.assetTimer = setTimeout(edEnsureAssets, 1200);
}
async function edExport() {
  const project = studio.project;
  if (!project || ed.busy) return;
  edPause();
  ed.busy = "export";
  renderEdit();
  const ok = await edEnsureAssets();
  if (studio.projectTimer) await flushProject();
  ed.busy = "";
  renderEdit();
  if (!ok) { toast("Some subtitles or texts could not be drawn; try again"); return; }
  renderExportDialog(project);
}

// ---- keys: Resolve's and Premiere's where they agree ----
function editKeydown(event) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return false;
  if (event.key === "Escape" && studio.menu) { closeStudioMenu(); return true; }
  const meta = event.metaKey || event.ctrlKey;
  const zoom = (factor) => { ed.zoom = Math.max(0.2, Math.min(2000, (ed.zoom || 1) * factor)); edDraw(); };
  if (meta && (event.code === "Equal" || event.code === "Minus")) { zoom(event.code === "Equal" ? 1.5 : 1 / 1.5); return true; }
  if (meta && (event.code === "KeyB" || event.code === "KeyK")) { edBladePlayhead(); return true; }
  if (meta && event.code === "KeyL") { if (event.shiftKey) edToggleLinked(); else edLink(); return true; }
  if (meta && event.code === "KeyA") { ed.sel = new Set(edit.clips.filter((clip) => !trackLocked(edit, clip.track)).map((clip) => clip.id)); edDraw(); renderEditSide(); return true; }
  if (event.altKey && event.code === "KeyX") { ed.in = ed.out = null; edDraw(); return true; }
  if (meta || event.altKey) return false;
  switch (event.code) {
    case "Space": edToggle(); return true;
    case "KeyK": if (ed.playing) edPause(); return true;
    case "KeyL": if (!ed.playing) edPlay(); return true;
    case "KeyJ": edSeek(ed.t - 5); return true;
    case "ArrowLeft": edSeek(ed.t - (event.shiftKey ? 1 : 1 / 30)); return true;
    case "ArrowRight": edSeek(ed.t + (event.shiftKey ? 1 : 1 / 30)); return true;
    case "ArrowUp": edEdgeJump(-1); return true;
    case "ArrowDown": edEdgeJump(1); return true;
    case "Home": edSeek(0); return true;
    case "End": edSeek(edLength(edit)); return true;
    case "KeyA": case "KeyV": edSetTool("select"); return true;
    case "KeyB": edSetTool("blade"); return true;
    case "Delete": edDelete(true); return true;
    case "Backspace": edDelete(event.shiftKey); return true;
    case "Quote": if (ed.in !== null || ed.out !== null) edDelete(true); return true;
    case "Semicolon": if (ed.in !== null || ed.out !== null) edDelete(false); return true;
    case "KeyI": ed.in = round3(ed.t); if (ed.out !== null && ed.out <= ed.in) ed.out = null; edDraw(); return true;
    case "KeyO": ed.out = round3(ed.t); if (ed.in !== null && ed.in >= ed.out) ed.in = null; edDraw(); return true;
    case "KeyN": edToggleSnap(); return true;
    case "KeyZ": if (event.shiftKey) { ed.zoom = 0; edDraw(); return true; } return false;
    case "Equal": zoom(1.5); return true;
    case "Minus": zoom(1 / 1.5); return true;
    case "KeyT": edAddText(); return true;
    case "Escape": ed.sel = new Set(); ed.track = null; edHeads(); renderEditSide(); edDraw(); return true;
    default: return false;
  }
}

// ---- Projects tab: an audio project shows its sound, not a video stage ----
function renderAudioProject(box) {
  const project = studio.project;
  const canvas = h("canvas", { id: "audioWave", "aria-label": "Sound of the recording" });
  canvas.addEventListener("pointerdown", (event) => {
    const rect = canvas.getBoundingClientRect();
    seekProject(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * project.duration);
    drawAudioView();
  });
  const seek = h("input", { type: "range", id: "projSeek", min: "0", max: String(project.duration), step: "0.01", value: "0" });
  seek.addEventListener("input", () => { seekProject(Number(seek.value)); drawAudioView(); });
  box.append(h("div", { class: "audioview" }, canvas,
    h("div", { class: "player" }, h("button", { id: "projPlay", title: "Play / pause", "aria-label": "Play / pause", onclick: () => { toggleProjectPlay(); drawAudioView(); } }, studioIcon("play")), seek, h("span", { class: "where", id: "projTime" }))));
  edPeaks(project);
  clearInterval(ed.audioTimer);
  ed.audioTimer = setInterval(() => { if (!$("audioWave")) { clearInterval(ed.audioTimer); return; } if (studio.player && studio.player.playing) drawAudioView(); }, 80);
  requestAnimationFrame(drawAudioView);
}
function drawAudioView() {
  const canvas = $("audioWave"), project = studio.project;
  if (!canvas || !project) return;
  const box = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(2, Math.round(box.width * ratio));
  canvas.height = Math.max(2, Math.round(box.height * ratio));
  const c = canvas.getContext("2d"), css = getComputedStyle(document.body);
  c.scale(ratio, ratio);
  const ink = (css.getPropertyValue("--ink") || "").trim() || "#ddd", muted = (css.getPropertyValue("--muted") || "").trim() || "#888";
  const t = studio.player ? studio.player.t : 0, middle = box.height / 2 + 6;
  c.font = "600 12px system-ui, sans-serif";
  c.fillStyle = muted;
  c.fillText(project.name, 14, 20);
  c.font = "600 26px ui-monospace, Menlo, monospace";
  c.fillStyle = ink;
  c.textAlign = "right";
  c.fillText(voiceClock(t), box.width - 14, 30);
  c.textAlign = "left";
  const peaks = ed.peaksFor === project.path ? ed.peaks : null;
  if (!peaks) { c.fillStyle = muted; c.font = "12px system-ui"; c.fillText("Reading the sound…", 14, middle); return; }
  const columns = Math.floor((box.width - 28) / 3), span = project.duration / Math.max(1, columns);
  for (let i = 0; i < columns; i++) {
    let value = 0;
    const from = Math.floor(i * span * ED_RATE), to = Math.max(from + 1, Math.floor((i + 1) * span * ED_RATE));
    for (let j = from; j < to && j < peaks.length; j++) value = Math.max(value, peaks[j]);
    const height = Math.max(1, value * (box.height * 0.36));
    c.fillStyle = i * span <= t ? ink : muted;
    c.globalAlpha = i * span <= t ? 1 : 0.55;
    c.fillRect(14 + i * 3, middle - height, 2, height * 2);
  }
  c.globalAlpha = 1;
  c.fillStyle = "#ff3b30";
  c.fillRect(14 + (t / Math.max(0.001, project.duration)) * (box.width - 28) - 1, 44, 2, box.height - 56);
  drawPlayerClock();
}
"""

"""The Studio tab of the `ul desk` page: its CSS and JS, injected into desk_ui.PAGE.

Device names, project names and texts are user data, so nodes are built with textContent, never innerHTML.
Recording, projects and export all go through `ul capture ... --json` on the server (desk.py `Studio`);
the page only edits the shared setup (storage.root/studio/setup.json) and shows what capture reports.
"""



STUDIO_CSS = r""".studio { display: flex; flex-direction: column; gap: 10px; padding: 12px 16px 18px; min-height: 100%; }
.sthead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sthead .seg { display: flex; gap: 2px; background: var(--column); border: 1px solid var(--line); border-radius: 8px; padding: 2px; }
.sthead .seg button { border: none; background: transparent; padding: 3px 11px; border-radius: 6px; color: var(--muted); font-weight: 550; }
.sthead .seg button.on { background: var(--panel); color: var(--text); box-shadow: var(--shadow), 0 0 0 1px var(--line); }
.sthead .seg button:disabled { opacity: .45; }
.sthead .fmt button.on { color: var(--accent-ink); box-shadow: 0 0 0 1px var(--accent); }
.sthead .lbl { color: var(--muted); font-size: 12px; }
.recgrid { display: grid; grid-template-columns: 230px minmax(0, 1fr) 270px; gap: 12px; align-items: start; }
.pane { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 9px 10px 10px; margin-bottom: 10px; box-shadow: var(--shadow); }
.pane h5 { margin: 0 0 7px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; display: flex; align-items: center; gap: 6px; }
.pane h5 .add { margin-left: auto; border: none; background: transparent; padding: 0 2px; color: var(--accent-ink); text-transform: none; letter-spacing: 0; font-size: 12px; font-weight: 600; }
:is(.pane, .inspector, .stmenu) .prow { display: flex; align-items: center; gap: 7px; margin: 6px 0; font-size: 12.5px; }
:is(.pane, .inspector, .stmenu) .prow > .lbl { color: var(--muted); width: 74px; flex: none; font-size: 12px; }
:is(.pane, .inspector, .stmenu) .prow select, :is(.pane, .inspector, .stmenu) .prow input[type=text], :is(.pane, .inspector, .stmenu) .prow input[type=number] { flex: 1; min-width: 0; padding: 3px 7px; font-size: 12.5px; }
:is(.pane, .inspector, .stmenu) .prow input[type=range] { flex: 1; min-width: 0; }
:is(.pane, .inspector, .stmenu) .prow input[type=color] { width: 26px; height: 22px; padding: 0; border-radius: 5px; }
:is(.pane, .inspector, .stmenu) .prow .val { color: var(--muted); font: 11.5px var(--mono); min-width: 38px; text-align: right; }
:is(.pane, .inspector, .stmenu, .dock) .note { color: var(--muted); font-size: 11.5px; margin: 4px 0 0; }
.scenes { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.scn { position: relative; border-radius: 6px; border: 1px solid var(--line); background: var(--sunken); overflow: hidden; padding: 0; aspect-ratio: 16 / 10; text-align: left; }
.scn.on { box-shadow: 0 0 0 2px var(--accent); border-color: var(--accent); }
.scn .mini { position: absolute; border-radius: 2px; background: var(--muted); opacity: .45; }
.scn .mini.camera { background: var(--accent); opacity: .8; }
.scn .mini.image, .scn .mini.text { background: var(--energy); opacity: .7; }
.scn kbd { position: absolute; right: 3px; top: 3px; font-size: 10px; }
.scn span { position: absolute; left: 5px; bottom: 3px; right: 4px; font-size: 10.5px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.srcs .src { display: flex; align-items: center; gap: 7px; width: 100%; border: none; background: transparent; padding: 5px 6px; border-radius: 6px; text-align: left; font-size: 12.5px; }
.srcs .src:hover { background: var(--column); }
.srcs .src.on { background: var(--sunken); box-shadow: inset 2px 0 0 var(--accent); }
.srcs .src.off { color: var(--muted); }
.srcs .src .ico { width: 16px; text-align: center; color: var(--muted); }
.srcs .src .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.srcs .src .eye { border: none; background: transparent; padding: 0 3px; color: var(--muted); font-size: 12px; }
.srcs .src .eye.hidden { opacity: .4; }
.stmenu { position: absolute; z-index: 20; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--lift); padding: 4px; display: flex; flex-direction: column; gap: 2px; min-width: 150px; }
.stmenu button { border: none; background: transparent; text-align: left; padding: 5px 9px; border-radius: 5px; font-size: 12.5px; }
.stmenu button:hover { background: var(--column); }
.stmenu label { display: flex; align-items: center; gap: 6px; padding: 4px 9px; font-size: 12px; color: var(--muted); }
.centre { min-width: 0; }
.banner { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; background: color-mix(in srgb, var(--danger) 12%, var(--panel)); border: 1px solid color-mix(in srgb, var(--danger) 45%, var(--line)); color: var(--text); border-radius: var(--r); padding: 8px 10px; margin-bottom: 8px; font-size: 12.5px; }
.banner b { color: var(--danger); }
.stage { position: relative; margin: 0 auto; border-radius: 8px; overflow: hidden; background: var(--sunken); box-shadow: var(--shadow); user-select: none; touch-action: none; }
.stage .bg { position: absolute; inset: -8%; width: 116%; height: 116%; object-fit: cover; filter: blur(18px) brightness(.8); }
.stage .ph { position: absolute; overflow: hidden; cursor: grab; box-sizing: border-box; }
.stage .ph > img, .stage .ph > video { width: 100%; height: 100%; display: block; pointer-events: none; }
.stage .ph .camph { width: 100%; height: 100%; display: grid; place-items: center; background: var(--column); color: var(--muted); font-size: 12px; text-align: center; }
.stage .float { position: absolute; z-index: 5; display: flex; gap: 4px; align-items: center; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 3px 5px; box-shadow: var(--lift); }
.shapes { display: flex; gap: 3px; }
.shapes button, .corners button { width: 24px; height: 24px; padding: 0; display: grid; place-items: center; border-radius: 5px; font-size: 12px; }
.shapes button.on, .corners button.on { border-color: var(--accent); color: var(--accent-ink); }
.shapes button i { display: block; background: var(--muted); }
.shapes button.on i { background: var(--accent); }
.corners { display: flex; gap: 3px; }
.stage .badge { position: absolute; right: 8px; top: 8px; z-index: 6; background: var(--panel); color: var(--danger); font: 700 11px var(--mono); padding: 2px 7px; border-radius: 5px; display: none; box-shadow: var(--shadow); }
.stage .badge.on { display: block; }
.stage .badge.paused { color: var(--muted); }
.stage .count { position: absolute; inset: 0; z-index: 7; display: grid; place-items: center; background: color-mix(in srgb, var(--bg) 55%, transparent); font: 700 96px var(--mono); color: var(--accent-ink); }
.stage .empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: 12.5px; text-align: center; padding: 20px; }
.sthint { color: var(--muted); font-size: 11.5px; text-align: center; margin: 5px 0 0; }
.recclock { font: 600 21px var(--mono); letter-spacing: .02em; }
.recclock.live { color: var(--danger); }
.recstate { color: var(--muted); font-size: 12px; }
.warns { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.warns div { display: flex; align-items: center; gap: 8px; border-radius: var(--r-sm); padding: 5px 9px; font-size: 12.5px; background: color-mix(in srgb, var(--warn) 14%, var(--panel)); border: 1px solid color-mix(in srgb, var(--warn) 40%, var(--line)); }
.warns div button { margin-left: auto; padding: 2px 9px; }
.meter { flex: 1; height: 7px; border-radius: 4px; background: var(--sunken); overflow: hidden; min-width: 40px; }
.meter i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--ok) 0 60%, var(--warn) 60% 85%, var(--danger) 85%); background-size: var(--full, 100px) 100%; transition: width .08s linear; }
.tag { font-size: 10px; color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 3px; }
.projbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.projbar .levels { grid-template-columns: repeat(3, auto); }
.projbar .levels button { padding: 3px 12px; }
.library { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.item { background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); overflow: hidden; cursor: pointer; border: 1px solid var(--line); text-align: left; padding: 0; display: flex; flex-direction: column; }
.item:hover { border-color: var(--accent); box-shadow: var(--lift); }
.item .pic { aspect-ratio: 16 / 10; background: var(--sunken); display: grid; place-items: center; color: var(--muted); position: relative; }
.item .pic img { width: 100%; height: 100%; object-fit: cover; }
.item .pic .len { position: absolute; right: 6px; bottom: 6px; background: var(--panel); color: var(--text); font: 11px var(--mono); padding: 1px 6px; border-radius: 5px; }
.item .pic .state { position: absolute; left: 6px; top: 6px; background: var(--panel); color: var(--text); font-size: 10.5px; font-weight: 650; padding: 1px 6px; border-radius: 5px; }
.item .pic .state.incomplete { color: var(--danger); }
.item .pic .kind { position: absolute; left: 6px; bottom: 6px; background: var(--panel); color: var(--muted); font-size: 10px; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; padding: 1px 6px; border-radius: 5px; }
.item .pic .cardwave { position: absolute; inset: 14px 10px 26px; width: calc(100% - 20px); height: calc(100% - 40px); }
.item .cap { position: relative; }
.item .cap .quick { position: absolute; right: 8px; top: 6px; font-size: 11.5px; font-weight: 650; padding: 2px 9px; border-radius: 6px; border: 1px solid var(--line); background: var(--panel); opacity: 0; transition: opacity .12s; }
.item:hover .cap .quick, .item:focus-within .cap .quick { opacity: 1; }
.item .cap .quick:hover { border-color: var(--accent-ink); color: var(--accent-ink); }
.item .pic svg { width: 34px; height: 34px; stroke: var(--muted); fill: none; stroke-width: 1.6; }
.item .cap { padding: 7px 9px 8px; font-size: 12px; }
.item .cap b { display: block; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .cap span { color: var(--muted); }
.projpage { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 12px; align-items: start; }
.projpage .player { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
.projpage .player input[type=range] { flex: 1; }
.projpage .scenelist { display: flex; flex-direction: column; gap: 3px; font-size: 12px; }
.projpage .scenelist div { display: flex; gap: 8px; }
.projpage .scenelist .t { font-family: var(--mono); color: var(--muted); width: 48px; }
.progress { height: 6px; border-radius: 3px; background: var(--sunken); overflow: hidden; margin: 6px 0; }
.progress i { display: block; height: 100%; width: 0; background: var(--accent); transition: width .3s; }
.rec-pill { display: none; border: none; background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); font: 600 12px var(--mono); border-radius: 999px; padding: 4px 10px; }
.rec-pill.on { display: inline-flex; gap: 6px; align-items: center; }
.rec-pill.on::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--danger); animation: blink 1.2s infinite; }
.rec-pill.paused::before { animation: none; background: var(--muted); }
@keyframes blink { 50% { opacity: .25; } }
#viewer { position: fixed; inset: 0; background: rgba(10,8,4,.6); display: none; place-items: center; z-index: 12; }
#viewer.on { display: grid; }
#viewer .sheet { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--lift); width: min(1100px, 94vw); max-height: 94vh; overflow: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
#viewer .media { background: #0c0c0b; border-radius: 12px; display: grid; place-items: center; min-height: 120px; }
#viewer .media video, #viewer .media img { max-width: 100%; max-height: 66vh; display: block; }
#viewer .media audio { width: 90%; margin: 30px 0; }
#viewer .top { display: flex; align-items: center; gap: 10px; background: none; box-shadow: none; padding: 0; }
#viewer .top b { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#viewer .tools { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
#viewer .tools .sep { width: 1px; height: 22px; background: var(--line); margin: 0 4px; }
#viewer .tools .mark { font: 12px var(--mono); color: var(--muted); }
#viewer canvas.filewave { width: 100%; height: 96px; display: block; cursor: pointer; background: #0c0c0b; border-radius: 12px; }
#viewer .export { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px 12px; }
#viewer .export label { display: grid; gap: 3px; font-size: 12px; color: var(--muted); }
#viewer .export label.check { display: flex; align-items: center; gap: 7px; color: var(--text); }
.studio.rec { height: 100%; padding: 8px 10px 10px; gap: 8px; box-sizing: border-box; }
.obs { flex: 1; min-height: 600px; display: grid; grid-template-columns: minmax(0, 1fr) 8px var(--right, 300px); grid-template-rows: minmax(200px, 1fr) 8px var(--bottom, 238px); }
.obs .slot { min-width: 0; min-height: 0; display: flex; border-radius: 10px; transition: box-shadow .12s, opacity .12s; }
.obs .slot > * { flex: 1; min-width: 0; min-height: 0; }
.obs .slot.s0 { grid-column: 3; grid-row: 1; }
.obs .slot.s4 { grid-column: 3; grid-row: 3; }
.obs .slot > * > header { cursor: grab; }
.obs .slot.lifted { opacity: .55; }
.obs .slot.droptarget { box-shadow: 0 0 0 2px var(--accent); }
body.moving-panel, body.moving-panel * { cursor: grabbing !important; user-select: none; }
body.resizing, body.resizing * { user-select: none; }
body.resizing.col-resize, body.resizing.col-resize * { cursor: col-resize !important; }
body.resizing.row-resize, body.resizing.row-resize * { cursor: row-resize !important; }
.obs .gut { position: relative; z-index: 2; touch-action: none; }
.obs .gut::after { content: ""; position: absolute; border-radius: 2px; background: var(--accent); opacity: 0; transition: opacity .12s; }
.obs .gut:hover::after, body.resizing .obs .gut:active::after { opacity: .7; }
.obs .gut-right { grid-column: 2; grid-row: 1 / -1; cursor: col-resize; }
.obs .gut-right::after { left: 3px; width: 2px; top: 30%; bottom: 30%; }
.obs .gut-bottom { grid-column: 1; grid-row: 2; cursor: row-resize; }
.obs .gut-bottom::after { top: 3px; height: 2px; left: 30%; right: 30%; }
.obs .gut-col { cursor: col-resize; }
.obs .gut-col::after { left: 3px; width: 2px; top: 20%; bottom: 20%; }
.obs .preview { grid-column: 1; grid-row: 1; display: flex; flex-direction: column; min-height: 0; min-width: 0; background: #0f0f0f; border-radius: 10px; border: 1px solid var(--line); overflow: hidden; position: relative; }
.obs .pvtop { position: absolute; left: 10px; right: 10px; top: 10px; z-index: 9; display: flex; flex-direction: column; gap: 6px; pointer-events: none; }
.obs .pvtop > * > * { pointer-events: auto; }
.obs .stagebox { flex: 1; min-height: 0; container-type: size; display: grid; place-items: center; padding: 14px; }
.stagewrap { position: relative; margin: 0 auto; }
.stagewrap > .stage { width: 100%; height: 100%; border-radius: 2px; box-shadow: 0 0 0 1px rgba(255, 255, 255, .14); }
.stageui { position: absolute; inset: 0; pointer-events: none; z-index: 6; }
.stage .ph:hover { outline: 1px solid color-mix(in srgb, var(--accent) 70%, transparent); outline-offset: -1px; }
.stage .ph.locked { cursor: default; }
.selbox { position: absolute; box-sizing: border-box; outline: 2px solid var(--accent); pointer-events: none; }
.selbox.locked { outline-style: dashed; }
.selbox .handle { position: absolute; width: 10px; height: 10px; box-sizing: border-box; background: #fff; border: 2px solid var(--accent); border-radius: 2px; pointer-events: auto; touch-action: none; }
.selbox .handle.hd-top-left { left: -6px; top: -6px; cursor: nwse-resize; }
.selbox .handle.hd-top { left: calc(50% - 5px); top: -6px; cursor: ns-resize; }
.selbox .handle.hd-top-right { right: -6px; top: -6px; cursor: nesw-resize; }
.selbox .handle.hd-right { right: -6px; top: calc(50% - 5px); cursor: ew-resize; }
.selbox .handle.hd-bottom-right { right: -6px; bottom: -6px; cursor: nwse-resize; }
.selbox .handle.hd-bottom { left: calc(50% - 5px); bottom: -6px; cursor: ns-resize; }
.selbox .handle.hd-bottom-left { left: -6px; bottom: -6px; cursor: nesw-resize; }
.selbox .handle.hd-left { left: -6px; top: calc(50% - 5px); cursor: ew-resize; }
.obs .voice { position: absolute; left: 0; top: 0; width: 100%; height: calc(100% - 34px); display: none; z-index: 8; background: #1c1c1e; }
.obs .voice.on { display: block; }
.obs .pvbar { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-top: 1px solid #262626; background: #151515; min-height: 34px; }
.obs .pvbar .sthint { margin: 0; color: #8f8f8f; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pvbar .live { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 3px 11px; font-size: 12px; background: #232323; color: #d8d8d8; border: 1px solid #343434; flex: none; }
.pvbar .live i { width: 7px; height: 7px; border-radius: 50%; background: #6b6b6b; }
.pvbar .live.on { color: #fff; border-color: #3b8a4a; }
.pvbar .live.on i { background: #3fbf5a; box-shadow: 0 0 6px #3fbf5a; }
.obs .inspector { overflow: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; min-height: 0; transition: box-shadow .3s; }
.obs .inspector.flash { box-shadow: 0 0 0 2px var(--accent); }
.inspector .ihead { display: flex; align-items: center; gap: 8px; padding: 9px 12px; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--panel); z-index: 1; }
.inspector .ihead b { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.inspector .hint, .dock header .hint { margin-left: auto; color: var(--muted); font-size: 10.5px; text-transform: none; letter-spacing: 0; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inspector .pad { padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.inspector .prow .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.isec { border-bottom: 1px solid var(--line); padding: 0 12px 8px; }
.isec > summary { cursor: pointer; list-style: none; padding: 8px 0 3px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; user-select: none; }
.isec > summary::-webkit-details-marker { display: none; }
.isec > summary::before { content: ""; display: inline-block; width: 5px; height: 5px; margin: 0 8px 2px 1px; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; transform: rotate(45deg); }
.isec:not([open]) > summary::before { transform: rotate(-45deg); margin-bottom: 0; }
.xywh { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; margin: 6px 0; }
.xywh label { display: flex; align-items: center; gap: 3px; font-size: 11px; color: var(--muted); }
.xywh input { width: 100%; min-width: 0; padding: 3px 4px; font: 11.5px var(--mono); }
.btnrow { display: flex; gap: 4px; flex-wrap: wrap; margin: 6px 0; }
.btnrow button { padding: 3px 9px; font-size: 12px; }
.obs .docks { grid-column: 1; grid-row: 3; display: grid; grid-template-columns: minmax(0, var(--c1, 1fr)) 8px minmax(0, var(--c2, 1.15fr)) 8px minmax(0, var(--c3, 1.35fr)); min-height: 0; }
.dock { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow: hidden; }
.dock > header { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; border-bottom: 1px solid var(--line); background: var(--column); }
.dock .dlist { flex: 1; overflow: auto; padding: 4px; min-height: 0; }
.dock > footer { display: flex; align-items: center; gap: 1px; padding: 3px 6px; border-top: 1px solid var(--line); background: var(--column); }
.dock > footer .spacer { flex: 1; }
.drow { display: flex; align-items: center; gap: 7px; padding: 4px 6px; border-radius: 6px; font-size: 12.5px; cursor: default; user-select: none; outline: none; }
.drow:hover { background: var(--column); }
.drow:focus-visible { box-shadow: inset 0 0 0 1px var(--accent); }
.drow.on { background: color-mix(in srgb, var(--accent) 24%, var(--panel)); }
.drow .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.drow.off .name { color: var(--muted); }
.drow kbd { font-size: 10px; }
.drow input.rename { flex: 1; min-width: 0; font-size: 12.5px; padding: 1px 5px; }
.studio svg.ico, #viewer svg.ico { width: 15px; height: 15px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.studio .drow > svg.ico { color: var(--muted); }
.studio .ib, .stmenu .ib { border: none; background: transparent; padding: 4px; border-radius: 5px; color: var(--text); display: inline-grid; place-items: center; line-height: 0; box-shadow: none; }
.studio .ib:hover:not(:disabled) { background: var(--sunken); }
.studio .ib:disabled { opacity: .3; }
.studio .ib.dim { color: var(--muted); opacity: .5; }
.studio .ib.danger { color: var(--danger); }
.drow .ib { padding: 2px; }
.stmenu svg.ico { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; vertical-align: -2px; margin-right: 6px; }
.stmenu hr { border: none; border-top: 1px solid var(--line); margin: 3px 2px; }
.stmenu button:disabled { opacity: .4; }
.stmenu .settingsbox { padding: 6px 8px; width: 300px; }
.stmenu .settingsbox h5 { margin: 0 0 4px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.mixer { flex: 1; overflow: auto; padding: 8px 10px; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.chan .chead { display: flex; align-items: center; gap: 6px; font-size: 12.5px; }
.chan .chead b { font-weight: 600; flex: none; }
.chan .chead select { flex: 1; min-width: 0; font-size: 12px; padding: 2px 5px; }
.chan .chead .note { margin: 0; flex: 1; }
.chan .db { font: 11px var(--mono); color: var(--muted); min-width: 46px; text-align: right; flex: none; }
.chan .meter { display: block; height: 8px; margin: 6px 0 4px; background: repeating-linear-gradient(90deg, var(--sunken) 0 calc(10% - 1px), color-mix(in srgb, var(--line) 80%, transparent) calc(10% - 1px) 10%); }
.chan .meter i { transition: none; }
.chan .cctl { display: flex; align-items: center; gap: 6px; }
.chan .cctl input[type=range] { flex: 1; min-width: 0; }
.chan .cctl .val { font: 11px var(--mono); color: var(--muted); min-width: 36px; text-align: right; }
.chan.muted .meter, .chan.muted input[type=range] { opacity: .35; }
.chan .tiny { padding: 1px 7px; font-size: 11px; }
.controls .cbody { flex: 1; padding: 9px 10px; display: flex; flex-direction: column; gap: 7px; overflow: auto; min-height: 0; }
.controls .recbtn { width: 100%; min-height: 38px; border-radius: 8px; border: 1px solid var(--line); background: var(--sunken); display: flex; align-items: center; justify-content: center; gap: 9px; font-weight: 650; font-size: 13px; color: var(--text); }
.controls .recbtn i { width: 13px; height: 13px; border-radius: 50%; background: var(--danger); flex: none; transition: border-radius .15s; }
.controls .recbtn:hover { border-color: var(--danger); }
.controls .recbtn.on { background: var(--danger); border-color: var(--danger); color: #fff; }
.controls .recbtn.on i { background: #fff; border-radius: 2px; }
.controls .audiobtn { justify-content: center; }
.controls .crow { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.controls .crow .recclock { font-size: 18px; }
.controls .pill { display: inline-flex; gap: 5px; align-items: center; border-radius: 999px; padding: 3px 10px; font-size: 12px; }
.studio .pill svg.ico, .warns svg.ico, .markname svg.ico { width: 13px; height: 13px; }
.warns div svg.ico { color: var(--warn); flex: none; }
.corners button svg.ico { width: 14px; height: 14px; }
.stage .badge .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: currentColor; margin-right: 5px; vertical-align: 1px; }
.projbar .back { display: inline-flex; align-items: center; gap: 4px; }
.markname { display: inline-flex; align-items: center; gap: 4px; }
#projPlay { display: inline-grid; place-items: center; width: 32px; height: 28px; padding: 0; }
.controls .info { color: var(--muted); font-size: 11px; line-height: 1.45; margin-top: auto; }
@media (max-width: 1100px) {
  .obs { grid-template-columns: 1fr; grid-template-rows: minmax(320px, 58vh) auto auto auto; gap: 8px; }
  .obs > *, .obs .slot.s0, .obs .slot.s4 { grid-column: 1; grid-row: auto; }
  .obs .gut { display: none; }
  .obs .docks { grid-template-columns: 1fr 1fr; gap: 8px; } .obs .docks > .slot { min-height: 200px; }
}
@media (max-width: 860px) { .projpage { grid-template-columns: 1fr; } .obs .docks { grid-template-columns: 1fr; } }
"""

STUDIO_JS = r"""// ---- studio: Record (scenes, sources, live preview) and Projects, all through `ul capture` ----
const studio = { info: null, setup: null, devices: null, modes: {}, doctor: null, status: { active: false }, statusAt: 0, shown: 0, starting: 0, saving: false,
  tab: ["projects", "edit"].includes(localStorage.getItem("studio-tab")) ? localStorage.getItem("studio-tab") : "record", selected: "camera", library: [], projects: [], filter: localStorage.getItem("studio-filter") || "projects",
  camStream: null, camVideo: null, micStream: null, audio: null, analyser: null, sampler: 0, levels: [], wave: [], screenUrl: "", screenFailed: false, previewTimer: 0,
  drag: null, saveTimer: 0, counting: 0, countTimer: 0, countdownDone: null, menu: null, delay: 0, clipboard: false,
  item: null, trim: { from: null, to: null }, project: null, projectCanvas: "16:9", projectTimer: 0, player: null, projectsLoaded: false, libraryLoaded: false, exportJob: null, exportTimer: 0 };
const media = (path, name) => path + "?t=" + encodeURIComponent(TOKEN) + (name ? "&name=" + encodeURIComponent(name) : "");

// ---- studio geometry: the same numbers as capture_project.py (apply_shape, pin) and capture_export.py (placement_px) ----
const STUDIO_RATIOS = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1], "4:5": [4, 5] };
const STUDIO_FORMATS = [["16:9", "16:9"], ["9:16", "9:16"], ["1:1", "1:1"], ["4:5", "4:5"], ["source", "As recorded"]];
const STUDIO_SHAPES = { circle: [1, 1, 0.5], square: [1, 1, 0], rounded: [1, 1, 0.18], wide: [16, 9, 0], tall: [9, 16, 0] };
const STUDIO_ANCHORS = ["top-left", "top-right", "bottom-left", "bottom-right"];
const SNAP = 0.02, MIN_BOX = 0.04;
const studioClone = (value) => JSON.parse(JSON.stringify(value));
// Python's round(): halves go to the even neighbour, so page and export agree on pixels.
function roundHalfEven(value) {
  const rounded = Math.round(value);
  return Math.abs(value % 1) === 0.5 && rounded % 2 !== 0 ? rounded - 1 : rounded;
}
const evenPx = (value) => Math.max(2, roundHalfEven(value / 2) * 2);

function pinPlacement(item, anchor) {
  const out = studioClone(item);
  out.anchor = anchor || null;
  if (!anchor) return out;
  const [, , width, height] = out.box;
  out.box = [anchor.endsWith("left") ? 0 : 1 - width, anchor.startsWith("top") ? 0 : 1 - height, width, height];
  return out;
}

function applyShape(item, shape, canvas) {
  const out = studioClone(item);
  if (!STUDIO_SHAPES[shape] || !STUDIO_RATIOS[canvas]) return out;
  const [shapeWidth, shapeHeight, radius] = STUDIO_SHAPES[shape];
  const [canvasWidth, canvasHeight] = STUDIO_RATIOS[canvas];
  const [x, y] = out.box;
  let width = out.box[2];
  let height = width * (canvasWidth / canvasHeight) * (shapeHeight / shapeWidth);
  if (height > 1) { width = width / height; height = 1; }
  out.box = [x, y, width, height];
  out.radius = radius;
  if (out.anchor) return pinPlacement(out, out.anchor);
  out.box = [Math.min(Math.max(x, 0), 1 - width), Math.min(Math.max(y, 0), 1 - height), width, height];
  return out;
}

// The shape preset a placement matches (box aspect in pixels and radius), or null.
function shapeOf(item, canvas) {
  if (!item || !STUDIO_RATIOS[canvas]) return null;
  const [canvasWidth, canvasHeight] = STUDIO_RATIOS[canvas];
  const aspect = (item.box[2] * canvasWidth) / (item.box[3] * canvasHeight);
  for (const [name, [w, h, radius]] of Object.entries(STUDIO_SHAPES)) {
    if (Math.abs(aspect - w / h) < 0.02 && Math.abs(item.radius - radius) < 0.005) return name;
  }
  return null;
}

function placementPx(item, width, height) {
  const [x, y, w, h] = item.box;
  return { x: roundHalfEven(x * width), y: roundHalfEven(y * height), w: evenPx(w * width), h: evenPx(h * height) };
}

// After a drag: near a corner the box is pinned there (anchor), near an edge it sits flush on it.
function snapPlacement(item, canvas) {
  const out = studioClone(item);
  let [x, y, width, height] = out.box;
  const near = (a, b) => Math.abs(a - b) <= SNAP;
  const left = near(x, 0), right = near(x + width, 1), top = near(y, 0), bottom = near(y + height, 1);
  if ((left || right) && (top || bottom)) return pinPlacement(out, (top ? "top" : "bottom") + "-" + (left ? "left" : "right"));
  if (left) x = 0; else if (right) x = 1 - width;
  if (top) y = 0; else if (bottom) y = 1 - height;
  out.box = [x, y, width, height];
  out.anchor = null;
  return out;
}

// Dragging inside a `cover` box pans what it shows: the picture follows the pointer.
function moveFocus(item, dx, dy) {
  const out = studioClone(item);
  const clamp = (value) => Math.min(1, Math.max(0, value));
  out.focus = [clamp(out.focus[0] - dx), clamp(out.focus[1] - dy)];
  return out;
}

// Resize from one corner; the opposite corner stays, and a pinned box stays pinned.
function resizePlacement(item, corner, dx, dy, keepAspect) {
  const out = studioClone(item);
  const [x, y, width, height] = out.box;
  const right = corner.endsWith("right"), bottom = corner.startsWith("bottom");
  let newWidth = Math.max(MIN_BOX, width + (right ? dx : -dx));
  let newHeight = keepAspect ? newWidth * (height / width) : Math.max(MIN_BOX, height + (bottom ? dy : -dy));
  if (newWidth > 1) { if (keepAspect) newHeight /= newWidth; newWidth = 1; }
  if (newHeight > 1) { if (keepAspect) newWidth /= newHeight; newHeight = 1; }
  out.box = [right ? x : x + width - newWidth, bottom ? y : y + height - newHeight, newWidth, newHeight];
  return out.anchor ? pinPlacement(out, out.anchor) : out;
}

// R record/stop, A audio only (stops too), P pause, M mark, 1-9 scenes (by key position, so every keyboard layout works).
function studioKey(code, current) {
  if (current.typing) return null;
  if (code === "KeyR") return current.active ? "stop" : "record";
  if (code === "KeyA") return current.active ? "stop" : "audio";
  if (code === "KeyP") return "pause";
  if (code === "KeyM") return "mark";
  const digit = /^Digit([1-9])$/.exec(code);
  if (digit) {
    const scene = (current.scenes || [])[Number(digit[1]) - 1];
    return scene ? "scene:" + scene : null;
  }
  return null;
}

// Status polling: never while the page is hidden; every second while a recording runs on the Studio tab,
// every 5 s otherwise (the REC pill also shows recordings started from the terminal).
function studioPollDelay(visible, recording, onStudio) {
  if (!visible) return null;
  return recording && onStudio ? 1000 : 5000;
}

function countdownSteps(n) { return Array.from({ length: Math.max(0, n) }, (_, index) => n - index); }

// ---- studio data ----
function cameraSource() { return studio.setup ? studio.setup.sources.find((item) => item.kind === "camera") || null : null; }
function screenSource() { return studio.setup ? studio.setup.sources.find((item) => item.kind === "screen") || null : null; }
// The layout being edited: the studio setup on the Record tab, or the open project (saved to that project).
function studioDoc() { return studio.project || studio.setup; }
function sourceById(id) { const doc = studioDoc(); return doc ? doc.sources.find((item) => item.id === id) || null : null; }
function currentCanvas() { return studio.project ? studio.projectCanvas : studio.setup ? studio.setup.canvas : "16:9"; }
function currentScene() {
  if (studio.project) return sceneAt(studio.project, studio.player ? studio.player.t : 0);
  return (studio.status.active && studio.status.scene) || (studio.setup ? studio.setup.scene : "screen-camera");
}
function currentLayout() {
  const doc = studioDoc();
  const layouts = doc && doc.layouts[currentCanvas()];
  return layouts ? layouts[currentScene()] || null : null;
}
function placementOf(id) { const layout = currentLayout(); return layout ? layout.placements[id] || null : null; }
function recordingNow() { return Boolean(studio.starting || (studio.status.active && studio.status.phase === "recording")); }
function recordingAudio() { return studio.starting ? studio.startingMode === "audio" : Boolean(studio.status.active && studio.status.mode === "audio"); }
function sourceName(source) {
  if (source.kind === "screen") return "Screen";
  if (source.kind === "camera") return "Camera";
  if (source.kind === "text") return "Text “" + source.text + "”";
  return source.asset;
}
const CAMERA_MB = { max: 90, high: 45, light: 22 };
const MIC_MB = { flac: 3, wav: 6, m4a: 2 };
// screencapture has no bitrate option; ~25-70 MB per minute was measured, so the middle is shown.
function megabytesPerMinute(setup) {
  if (!setup) return 0;
  const camera = setup.sources.find((item) => item.kind === "camera");
  return 45 + (camera && camera.enabled ? CAMERA_MB[camera.quality] || 0 : 0) + (setup.audio.mic.enabled ? MIC_MB[setup.audio.mic.format] || 0 : 0);
}
function gigabytes(bytes) { return bytes === null || bytes === undefined ? "" : (bytes / 1e9).toFixed(bytes > 1e11 ? 0 : 1) + " GB"; }

async function loadStudioInfo() {
  const { status, data } = await api("GET", "/api/studio");
  // A failed answer is kept and shown (with Retry); returning without it made renderStudio ask again at once, forever.
  if (status !== 200) { studio.info = { available: false, error: (data && data.error) || "The desk did not answer (" + status + ")" }; return; }
  studio.info = data;
  if (data.available) { loadRecordStatus(); loadSetup(); scheduleStudioPoll(); }
}

async function loadSetup() {
  const { status, data } = await api("GET", "/api/studio/setup");
  if (status !== 200) { studio.setupError = data.error || "Could not read the studio setup"; toast(studio.setupError); return; }
  studio.setupError = "";
  for (const warning of data.warnings || []) toast(warning);
  delete data.warnings;
  studio.setup = data;
  startHistory(studio.project || data);
  if (!sourceById(studio.selected)) studio.selected = data.sources[0].id;
}

async function loadDevices() {
  const { status, data } = await api("GET", "/api/studio/devices");
  if (status !== 200) { toast(data.error || "Could not list devices"); return; }
  studio.devices = data;
  if (state.view === "studio") { renderSound(); renderProps(); updateRecordControls(); }
}

async function loadDoctor() {
  const { status, data } = await api("GET", "/api/studio/doctor");
  if (status !== 200) return;
  studio.doctor = data;
  renderBanner();
}

// Edits go to the shared setup file half a second after the last change.
function saveSetupSoon() {
  clearTimeout(studio.saveTimer);
  studio.saveTimer = setTimeout(flushSetup, 500);
}

async function flushSetup() {
  clearTimeout(studio.saveTimer);
  studio.saveTimer = 0;
  if (!studio.setup) return;
  const request = api("POST", "/api/studio/setup", studio.setup);
  studio.savingSetup = request;  // a recording that starts now waits for this save too
  let answer;
  try { answer = await request; } finally { if (studio.savingSetup === request) studio.savingSetup = null; }
  const { status, data } = answer;
  if (status === 200) return;
  toast(data.error || "Could not save the studio setup");
  await loadSetup();
  if (state.view === "studio") renderStudioBody();
}

function edited(...parts) {
  rememberEdit();
  if (studio.project) saveProjectSoon();
  else saveSetupSoon();
  for (const part of parts) part();
}

// ---- recording state ----
let studioPollTimer = 0;
function scheduleStudioPoll(soon) {
  clearTimeout(studioPollTimer);
  studioPollTimer = 0;
  if (!studio.info || !studio.info.available) return;
  const busy = Boolean(studio.status.active || studio.saving || studio.starting);
  const delay = studioPollDelay(!document.hidden, busy, state.view === "studio");
  if (delay === null) return;
  studioPollTimer = setTimeout(async () => {
    studioPollTimer = 0;
    if (document.hidden) return;
    await loadRecordStatus();
    scheduleStudioPoll();
  }, soon ? 300 : delay);
}

async function loadRecordStatus() {
  const { status, data } = await api("GET", "/api/studio/status");
  if (status !== 200) return;
  const was = studio.status;
  studio.status = data;
  studio.statusAt = Date.now();
  if (studio.saving && data.saving_done) {
    studio.saving = false;
    if (data.saving_done.error) toast(data.saving_done.error);
    else recordingSaved(data.saving_done);
  }
  if (!data.active) for (const item of studio.levels) item.live = false;
  if (!data.active && !studio.starting) releaseWaveMic();
  drawRecording();
  if (state.view === "studio") {
    updateRecordControls();
    if (Boolean(was.active) !== Boolean(data.active) || was.scene !== data.scene) { renderScenes(); renderSources(); drawStage(); renderProps(); renderSound(); }
  }
}

function recordingSaved(done) {
  if (done.export_error) toast("Saved, but the export failed: " + done.export_error);
  else toast("Saved " + String(done.saved || done.project || "").split("/").pop());
  studio.projectsLoaded = false;
  if (state.view === "studio" && done.project && done.saved === done.project) openProject(done.project, true);
  else if (state.view === "studio" && studio.tab === "projects") loadProjects();
}

function recordElapsed() {
  const s = studio.status;
  if (studio.starting) return 0;  // the clock starts once the microphone and camera deliver
  if (!s.active) return 0;
  const value = s.elapsed + (s.phase === "recording" ? (Date.now() - studio.statusAt) / 1000 : 0);
  // Polls arrive a little late; never let the clock step backwards while recording.
  if (s.phase === "recording") studio.shown = Math.max(studio.shown, value);
  else studio.shown = value;
  return studio.shown;
}

// ---- audio-only recording: a scrolling sound wave like Voice Memos (bars every WAVE_STEP s, newest at the centre line) ----
const WAVE_STEP = 0.08;
const WAVE_PX = 4;  // one bar per 4 px: 50 px a second

/** Keep the loudest level of each WAVE_STEP slice; slices are indexed by recording time, so a pause leaves no gap. */
function addWaveSample(wave, seconds, level) {
  const index = Math.floor(Math.max(0, seconds) / WAVE_STEP);
  const last = wave[wave.length - 1];
  if (last && last.i === index) last.v = Math.max(last.v, level);
  else if (!last || index > last.i) wave.push({ i: index, v: level });
  return wave;
}

/** The loudest slice in each of `columns` equal parts of `span` slices, in one pass. */
function wavePeaks(wave, span, columns) {
  const peaks = new Array(Math.max(0, columns)).fill(0);
  for (const item of wave) {
    const column = Math.floor((item.i / span) * columns);
    if (column >= 0 && column < columns) peaks[column] = Math.max(peaks[column], item.v);
  }
  return peaks;
}

/** 2.883 s -> "00:02,88" (minutes, seconds, hundredths), the Voice Memos clock. */
function voiceClock(seconds) {
  const total = Math.max(0, seconds);
  const hundredths = Math.floor((total % 1) * 100);
  return clockText(total) + "," + String(hundredths).padStart(2, "0");
}

/** The microphone opened only to draw the wave is closed once the recording is over. */
function releaseWaveMic() {
  if (!studio.waveMic) return;
  studio.waveMic = false;
  if (studio.micStream) { stopStream("micStream"); renderSound(); }
}

function drawVoice() {
  const canvas = $("voiceWave");
  const on = recordingAudio() || (studio.saving && studio.wave && studio.wave.length && studio.status.mode === "audio");
  if (!canvas) return;
  canvas.classList.toggle("on", Boolean(on));
  if (!on || !canvas.getContext) { studio.voiceLoop = false; return; }
  // A recording started from the terminal or the menu bar: open the page microphone for the wave too.
  if (recordingAudio() && !studio.micStream && !studio.waveMic && state.view === "studio") { studio.waveMic = true; toggleMeter(); }
  if (!studio.voiceLoop) {
    studio.voiceLoop = true;
    const loop = () => { if (!studio.voiceLoop) return; paintVoice(canvas); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }
}

function paintVoice(canvas) {
  if (!canvas.isConnected) { studio.voiceLoop = false; return; }
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return;
  if (canvas.width !== Math.round(width * ratio)) canvas.width = Math.round(width * ratio);
  if (canvas.height !== Math.round(height * ratio)) canvas.height = Math.round(height * ratio);
  const g = canvas.getContext("2d");
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  g.fillStyle = "#1c1c1e";
  g.fillRect(0, 0, width, height);
  const wave = studio.wave || [];
  const now = studio.starting ? 0 : recordElapsed();
  const live = recordingNow() && !studio.starting;
  // Title and the big clock.
  g.textAlign = "center";
  g.fillStyle = "#f2f2f7";
  g.font = "600 17px -apple-system, system-ui, sans-serif";
  g.fillText(studio.starting ? "Starting…" : studio.status.paused ? "Paused" : studio.saving ? "Saving…" : "New recording", width / 2, 34);
  g.fillStyle = "#8e8e93";
  g.font = "500 13px -apple-system, system-ui, sans-serif";
  g.fillText(new Date().toLocaleDateString(), width / 2, 54);
  g.textAlign = "right";
  g.fillStyle = "#f2f2f7";
  g.font = "600 34px ui-monospace, SFMono-Regular, Menlo, monospace";
  g.fillText(voiceClock(now), width - 22, height - 22);
  // The wave: newest slice at the centre line, older ones to the left.
  const top = 76, bottom = Math.max(top + 60, height - 150), middle = (top + bottom) / 2, half = (bottom - top) / 2 - 6;
  g.fillStyle = "#2c2c2e";
  g.fillRect(0, top, width, bottom - top);
  const centre = Math.round(width / 2);
  const nowIndex = now / WAVE_STEP;
  g.fillStyle = "#e5e5ea";
  for (let k = wave.length - 1; k >= 0; k--) {
    const x = centre - (nowIndex - wave[k].i) * WAVE_PX;
    if (x < -WAVE_PX) break;
    if (x > width) continue;
    const bar = Math.max(1.5, wave[k].v * half);
    g.fillRect(Math.round(x), Math.round(middle - bar), 2, Math.round(bar * 2));
  }
  // Seconds ruler under the wave.
  g.fillStyle = "#636366";
  g.font = "500 12px ui-monospace, SFMono-Regular, Menlo, monospace";
  g.textAlign = "left";
  const pxPerSecond = WAVE_PX / WAVE_STEP;
  for (let second = Math.max(0, Math.floor(now - centre / pxPerSecond)); second <= now + (width - centre) / pxPerSecond; second++) {
    const x = centre - (now - second) * pxPerSecond;
    g.fillRect(Math.round(x), bottom, 1, 9);
    g.fillRect(Math.round(x + pxPerSecond / 2), bottom, 1, 5);
    g.fillText(clockText(second).replace(/^0/, ""), Math.round(x) + 3, bottom + 22);
  }
  // The centre line: red while recording, grey when paused.
  g.fillStyle = live ? "#ff453a" : "#8e8e93";
  g.fillRect(centre - 1, top - 6, 2, bottom - top + 12);
  g.beginPath(); g.arc(centre, top - 6, 4, 0, Math.PI * 2); g.fill();
  g.beginPath(); g.arc(centre, bottom + 6, 4, 0, Math.PI * 2); g.fill();
  // The whole recording in one strip.
  const stripTop = bottom + 40, stripHeight = 34, stripLeft = 22, stripWidth = Math.max(40, width - 260);
  g.fillStyle = "#2c2c2e";
  g.fillRect(stripLeft, stripTop, stripWidth, stripHeight);
  if (wave.length && nowIndex > 0) {
    g.fillStyle = "#aeaeb2";
    const peaks = wavePeaks(wave, Math.max(nowIndex, 1), Math.floor(stripWidth / 3));
    peaks.forEach((peak, column) => {
      if (peak <= 0) return;
      const bar = Math.max(1, peak * (stripHeight / 2 - 3));
      g.fillRect(stripLeft + column * 3, stripTop + stripHeight / 2 - bar, 2, bar * 2);
    });
  }
}

function drawRecording() {
  drawVoice();
  const s = studio.status, pill = $("recPill");
  const active = s.active || studio.saving || Boolean(studio.starting);
  pill.className = "rec-pill" + (active ? " on" : "") + (s.paused ? " paused" : "");
  pill.textContent = studio.saving || s.phase === "saving" ? "Saving…" : active ? (s.paused ? "Paused " : "REC ") + clockText(recordElapsed()) : "";
  const clock = $("recClock");
  if (clock) {
    clock.textContent = clockText(recordElapsed());
    clock.classList.toggle("live", recordingNow());
  }
  const badge = $("stageBadge");
  if (badge) {
    badge.className = "badge" + (active && !studio.saving ? " on" : "") + (s.paused ? " paused" : "");
    badge.textContent = "";
    badge.append(h("i", { class: "dot" }), studio.starting ? "STARTING…" : (s.paused ? "PAUSED " : "REC ") + clockText(recordElapsed()));
  }
  drawMeter();
}

// Countdown before a recording: the page waits, then calls record (R again cancels).
function runCountdown(seconds) {
  return new Promise((resolve) => {
    studio.counting = seconds;
    studio.countdownDone = resolve;
    drawCountdown();
    const tick = () => {
      if (!studio.counting) return;
      studio.counting -= 1;
      drawCountdown();
      if (studio.counting <= 0) { studio.countdownDone = null; resolve(true); }
      else studio.countTimer = setTimeout(tick, 1000);
    };
    studio.countTimer = setTimeout(tick, 1000);
  });
}

function cancelCountdown() {
  clearTimeout(studio.countTimer);
  studio.counting = 0;
  const done = studio.countdownDone;
  studio.countdownDone = null;
  drawCountdown();
  if (done) done(false);
}

function drawCountdown() {
  const stage = $("stage");
  if (!stage) return;
  let node = $("countdown");
  if (!studio.counting) { if (node) node.remove(); return; }
  if (!node) { node = h("div", { class: "count", id: "countdown" }); stage.append(node); }
  node.textContent = String(studio.counting);
}

/** Start or stop. `audio` records the microphone alone (no screen, no camera) into its own project. */
async function toggleRecord(mode) {
  if (studio.counting) { cancelCountdown(); return; }
  if (studio.saving || studio.starting) return;
  if (studio.status.active) {
    studio.saving = true;
    for (const item of studio.levels) item.live = false;
    updateRecordControls();
    const { status, data } = await api("POST", "/api/studio/stop", {});
    if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
    updateRecordControls();
    scheduleStudioPoll(true);
    return;
  }
  if (studio.recordBusy) return;  // a second press while the first one is still on its way
  const seconds = studio.setup ? studio.setup.countdown : 0;
  if (seconds > 0 && !(await runCountdown(seconds))) return;
  if (studio.status.active || studio.starting || studio.saving || studio.recordBusy) return;
  studio.recordBusy = true;
  try { await startRecording(mode); } finally { studio.recordBusy = false; }
}

async function startRecording(mode) {
  // The recording copies the saved setup, so a pending edit is saved first (and one already on its way).
  if (studio.saveTimer) await flushSetup();
  if (studio.savingSetup) await studio.savingSetup;
  const body = mode === "audio" ? { mode: "audio" } : studio.setup ? { scene: studio.setup.scene, canvas: studio.setup.canvas } : {};
  // Show the recording at once; the server's clock replaces this one when it answers.
  studio.starting = Date.now();
  studio.startingMode = mode === "audio" ? "audio" : "";
  studio.shown = 0;
  studio.levels = [];
  studio.wave = [];
  updateRecordControls();
  if (mode === "audio" && !studio.micStream) { studio.waveMic = true; toggleMeter(); }  // the wave is drawn from the page's own microphone
  const { status, data } = await api("POST", "/api/studio/record", body);
  studio.starting = 0;
  if (status !== 200) {
    toast(data.error || "Could not start recording");
    if (/permission/i.test(data.error || "")) loadDoctor();
    await loadRecordStatus();
    updateRecordControls();
    return;
  }
  for (const warning of data.warnings || []) toast(warning);
  studio.status = data;
  studio.statusAt = Date.now();
  updateRecordControls();
  drawStage();
  scheduleStudioPoll();
}

async function pauseRecord() {
  if (!studio.status.active || studio.saving) return;
  const { status, data } = await api("POST", studio.status.paused ? "/api/studio/resume" : "/api/studio/pause", {});
  if (status !== 200) { toast(data.error || "Could not pause"); return; }
  studio.status = data;
  studio.statusAt = Date.now();
  updateRecordControls();
}

async function addMark() {
  if (!studio.status.active) return;
  const { status, data } = await api("POST", "/api/studio/mark", {});
  if (status !== 200) { toast(data.error || "Could not add a mark"); return; }
  toast("Mark at " + clockText(data.mark ? data.mark.t : recordElapsed()));
}

async function forceStop() {
  if (!confirm("Kill the stuck recorder? Its track is lost; the other tracks are kept.")) return;
  studio.saving = true;
  updateRecordControls();
  const { status, data } = await api("POST", "/api/studio/stop", { force: true });
  if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
  scheduleStudioPoll(true);
}

async function selectScene(id) {
  if (!studio.setup || !studio.setup.scenes.some((item) => item.id === id)) return;
  studio.setup.scene = id;
  saveSetupSoon();
  if (studio.status.active) {
    const { status, data } = await api("POST", "/api/studio/scene", { scene: id });
    if (status !== 200) toast(data.error || "Could not switch the scene");
    else { studio.status = data; studio.statusAt = Date.now(); }
  }
  renderScenes();
  renderSources();
  drawStage();
  renderProps();
}

function studioKeydown(event) {
  if (state.view !== "studio" || !studio.info || !studio.info.available) return false;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test((document.activeElement && document.activeElement.tagName) || "");
  if (typing) return false;
  if ((event.metaKey || event.ctrlKey) && event.code === "KeyZ" && (studio.project || (studio.tab === "record" && studio.setup))) {
    event.preventDefault();
    undoEdit(event.shiftKey);
    return true;
  }
  if (studio.tab === "edit") { const handled = editKeydown(event); if (handled) event.preventDefault(); return handled; }
  if (studio.tab !== "record" || studio.project) return false;
  if (event.key === "Escape" && studio.menu) { closeStudioMenu(); return true; }
  if (event.metaKey || event.ctrlKey || event.altKey) return false;
  if (studio.setup && studio.selected) {
    const step = event.shiftKey ? 10 : 1;
    const arrows = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (arrows[event.key] && nudgeSelected(...arrows[event.key])) { event.preventDefault(); return true; }
    if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); deleteSelected(); return true; }
    if (event.key === "Escape") { selectSource(null); return true; }
  }
  const action = studioKey(event.code, { active: Boolean(studio.status.active), typing, scenes: studio.setup ? studio.setup.scenes.map((item) => item.id) : [] });
  if (!action) return false;
  event.preventDefault();
  if (action === "record" || action === "stop") toggleRecord();
  else if (action === "audio") toggleRecord("audio");
  else if (action === "pause") pauseRecord();
  else if (action === "mark") addMark();
  else selectScene(action.slice(6));
  return true;
}

// ---- browser camera and microphone (preview only; the recording itself is ul capture) ----
function leaveStudio() {
  clearTimeout(studio.previewTimer);
  studio.previewTimer = 0;
  cancelCountdown();
  stopStream("camStream");
  stopStream("micStream");
  stopStream("screenStream");
  closeStudioMenu();
  closeViewer();
  edLeave();
  if (studio.projectTimer) flushProject();
  stopProjectPlayer();
  studio.project = null;
}

function stopStream(key) {
  if (key === "screenStream") {
    if (studio.screenStream) { studio.screenStream.getTracks().forEach((track) => track.stop()); studio.screenStream = null; }
    for (const video of [studio.screenVideo, studio.screenBgVideo]) if (video) video.srcObject = null;
    return;
  }
  const request = key === "camStream" ? "camRequest" : "micRequest";
  studio[request] = (studio[request] || 0) + 1;
  if (studio[key]) { studio[key].getTracks().forEach((track) => track.stop()); studio[key] = null; }
  if (key === "camStream" && studio.camVideo) studio.camVideo.srcObject = null;
  if (key === "micStream") {
    clearInterval(studio.sampler);
    studio.analyser = null;
    studio.levels = [];
    if (studio.audio) { studio.audio.close(); studio.audio = null; }
  }
}

async function toggleCamera() {
  if (studio.camStream) { stopStream("camStream"); drawStage(); return; }
  if (state.view !== "studio") return;
  const request = studio.camRequest = (studio.camRequest || 0) + 1;
  const current = () => request === studio.camRequest && state.view === "studio";
  const wanted = (cameraSource() || {}).device || "default";
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    if (wanted !== "default") {
      // Labels are only visible after the first permission; the device is matched by its name.
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "videoinput" && item.label === wanted);
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      if (found) { stream.getTracks().forEach((track) => track.stop()); stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: found.deviceId } } }); }
    }
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.camStream = stream;
  } catch (error) { if (stream) stream.getTracks().forEach((track) => track.stop()); toast("The browser could not open the camera: " + error.message); }
  drawStage();
}

function ensureCamera() {
  const camera = cameraSource();
  if (camera && camera.enabled && !studio.camStream && localStorage.getItem("studio-campreview") !== "off" && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) toggleCamera();
}

async function toggleMeter() {
  if (studio.micStream) { stopStream("micStream"); renderSound(); return; }
  const allowed = () => !studio.setup || studio.setup.audio.mic.enabled || recordingAudio();
  if (state.view !== "studio" || !allowed()) return;
  const request = studio.micRequest = (studio.micRequest || 0) + 1;
  const current = () => request === studio.micRequest && state.view === "studio" && allowed();
  const wanted = studio.setup ? studio.setup.audio.mic.device : "default";
  try {
    const constraints = { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } };
    if (wanted && wanted !== "default") {
      // Device labels are only visible after the first permission.
      await navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => stream.getTracks().forEach((track) => track.stop()));
      if (!current()) return;
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "audioinput" && item.label.includes(wanted));
      if (!current()) return;
      if (found) constraints.audio.deviceId = { exact: found.deviceId };
    }
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.micStream = stream;
  } catch (error) { toast("The browser could not open the microphone: " + error.message); return; }
  studio.audio = new AudioContext();
  studio.analyser = studio.audio.createAnalyser();
  studio.analyser.fftSize = 1024;
  studio.audio.createMediaStreamSource(studio.micStream).connect(studio.analyser);
  const samples = new Float32Array(studio.analyser.fftSize);
  studio.sampler = setInterval(() => {
    if (!studio.analyser) return;
    studio.analyser.getFloatTimeDomainData(samples);
    let peak = 0;
    for (const value of samples) peak = Math.max(peak, Math.abs(value));
    const db = 20 * Math.log10(Math.max(peak, 1e-5));
    studio.levels.push({ v: dbLevel(db), db, live: recordingNow() });
    if (recordingAudio() && recordingNow() && !studio.starting) addWaveSample(studio.wave, recordElapsed(), dbLevel(db));
    if (studio.levels.length > 600) studio.levels.splice(0, 300);
  }, 30);
  renderSound();
  const stream = studio.micStream;
  const loop = () => { if (studio.micStream !== stream) return; drawMeter(); requestAnimationFrame(loop); };
  loop();
}

const dbLevel = (db) => Math.min(1, Math.max(0, (db + 60) / 60));
// Instant rise, steady fall (peak meter ballistics), so the bar follows the voice without flicker.
function drawMeter() {
  const meter = $("micMeter");
  if (!meter) return;
  const s = studio.status, on = Boolean(studio.setup && studio.setup.audio.mic.enabled);
  let level = 0, db = null;
  if (on && s.active && typeof s.level_db === "number") { level = dbLevel(s.level_db); db = s.level_db; }
  else if (on && studio.micStream && studio.levels.length) { const last = studio.levels[studio.levels.length - 1]; level = last.v; db = last.db; }
  const now = Date.now(), shown = studio.meterShown || 0;
  const dt = Math.min(0.25, Math.max(0, (now - (studio.meterAt || now)) / 1000));
  studio.meterAt = now;
  // OBS's default "Fast" ballistics: falls 40 dB in 1.7 s (the scale here is 60 dB wide).
  studio.meterShown = level >= shown ? level : Math.max(level, shown - (dt * 40) / 1.7 / 60);
  meter.firstChild.style.width = Math.round(studio.meterShown * 100) + "%";
  // The colours (green, yellow, red) sit at fixed dB, so the gradient spans the whole meter, not the bar.
  if (meter.clientWidth) meter.firstChild.style.backgroundSize = meter.clientWidth + "px 100%";
  const text = $("micDb");
  if (text) text.textContent = !on ? "off" : db === null || db === undefined ? "" : db <= -59 ? "-∞ dB" : Math.round(db) + " dB";
}

// ---- screen preview: live through the browser (getDisplayMedia) once asked for, otherwise a snapshot
// every 2 s (every 5 s while recording, so the recording stays smooth) ----
function startPreview() {
  clearTimeout(studio.previewTimer);
  const screen = screenSource();
  if (!screen || state.view !== "studio" || studio.tab !== "record" || studio.screenStream) return;
  const again = (ms) => { studio.previewTimer = setTimeout(startPreview, ms); };
  if (document.hidden) { again(1000); return; }
  const url = media("/media/preview") + "&display=" + screen.display + "&_=" + Date.now();
  const image = new Image();
  image.onload = () => {
    if (studio.screenStream) return;
    const first = !studio.screenUrl;
    studio.screenUrl = url;
    // The first snapshot (or one after a failure) replaces the placeholder, so the stage is redrawn;
    // later ones only swap the image source.
    if (first || studio.screenFailed) { studio.screenFailed = false; drawStage(); }
    else for (const node of document.querySelectorAll("img.screen")) node.src = url;
    again(studio.status.active ? 5000 : 2000);
  };
  image.onerror = () => {
    if (!studio.screenFailed) { studio.screenFailed = true; loadDoctor(); drawStage(); }
    again(5000);
  };
  image.src = url;
}

// ---- rendering ----
function renderStudio(main) {
  if (!studio.info) { main.textContent = ""; main.append(h("div", { class: "page" }, h("div", { class: "empty", text: "Loading…" }))); loadStudioInfo().then(() => state.view === "studio" && render()); return; }
  if (!studio.info.available) {
    main.textContent = "";
    const retry = h("button", { text: "Try again", onclick: () => { studio.info = null; render(); } });
    main.append(h("div", { class: "page" }, h("h3", { text: "Studio" }), studio.info.error
      ? h("div", { class: "empty" }, h("div", { text: "The Studio could not load: " + studio.info.error }), retry)
      : h("div", { class: "empty", text: "The capture command is not installed in this ul. Turn on the `capture` feature with: ul features" })));
    return;
  }
  if (main.querySelector(".studio")) return;
  main.textContent = "";
  main.append(h("div", { class: "studio", id: "studioRoot" }));
  renderStudioBody();
  if (!studio.setup) loadSetup().then(() => state.view === "studio" && renderStudioBody());
  if (!studio.devices) loadDevices();
  loadDoctor();
  loadRecordStatus();
  scheduleStudioPoll();
}

function setStudioTab(tab) {
  if (tab === "edit") {
    if (studio.tab === "edit") return;
    clearTimeout(studio.previewTimer); stopStream("camStream"); stopStream("micStream"); stopStream("screenStream"); closeStudioMenu();
    if (studio.counting) cancelCountdown();
    if (studio.project) { edEnter(); return; }
    studio.tab = "edit";
    localStorage.setItem("studio-tab", "edit");
    renderStudioBody();
    return;
  }
  if (studio.tab === "edit") edLeave();
  if (tab === studio.tab && !studio.project) return;
  studio.tab = tab;
  localStorage.setItem("studio-tab", tab);
  if (tab !== "record" && studio.counting) cancelCountdown();
  if (tab !== "record") { clearTimeout(studio.previewTimer); stopStream("camStream"); stopStream("micStream"); stopStream("screenStream"); closeStudioMenu(); }
  if (studio.projectTimer) flushProject();
  stopProjectPlayer();
  studio.project = null;
  if (studio.setup) startHistory(studio.setup);  // ⌘Z works for the first setup edit after a project
  renderStudioBody();
}

// ---- studio layout: every panel is resized by dragging the gaps between panels and moved by dragging its
// title onto another panel (the two swap places); the layout is kept in localStorage, the preview stays put ----
const LAYOUT_KEY = "studio-layout";
const LAYOUT_PANELS = ["propsPane", "scenesPane", "sourcesPane", "soundPane", "recBar"];  // slots: right top, 3 bottom, right bottom
const LAYOUT_DEFAULT = { right: 300, bottom: 238, cols: [1, 1.15, 1.35] };
const LAYOUT_MIN = { right: 220, bottom: 110, main: 420, preview: 200, share: 0.12 };

function defaultLayout() {
  return { right: LAYOUT_DEFAULT.right, bottom: LAYOUT_DEFAULT.bottom, cols: LAYOUT_DEFAULT.cols.slice(), order: LAYOUT_PANELS.slice() };
}

/** The saved layout, every value checked; anything odd falls back to the default for that value. */
function parseLayout(text) {
  const layout = defaultLayout();
  let saved = null;
  try { saved = JSON.parse(text || "null"); } catch (error) { return layout; }
  if (!saved || typeof saved !== "object") return layout;
  const size = (value, low, high) => Number.isFinite(value) && value >= low && value <= high;
  if (size(saved.right, LAYOUT_MIN.right, 2000)) layout.right = saved.right;
  if (size(saved.bottom, LAYOUT_MIN.bottom, 2000)) layout.bottom = saved.bottom;
  if (Array.isArray(saved.cols) && saved.cols.length === 3 && saved.cols.every((value) => size(value, 0.05, 20))) layout.cols = saved.cols.slice();
  if (Array.isArray(saved.order) && saved.order.length === LAYOUT_PANELS.length && new Set(saved.order).size === LAYOUT_PANELS.length
      && LAYOUT_PANELS.every((id) => saved.order.includes(id))) layout.order = saved.order.slice();
  return layout;
}

function saveLayout() { localStorage.setItem(LAYOUT_KEY, JSON.stringify(studio.layout)); }

function layoutPanel(id) {
  return id === "propsPane" ? h("aside", { class: "inspector", id }) : h("section", { class: "dock" + (id === "recBar" ? " controls" : ""), id });
}

/** The Record tab's grid: the preview, the slots for the five panels and the gutters between them. */
function layoutFrame(preview) {
  if (!studio.layout) studio.layout = parseLayout(localStorage.getItem(LAYOUT_KEY));
  const slots = [0, 1, 2, 3, 4].map((index) => h("div", { class: "slot s" + index }));
  const gutter = (kind, index) => h("div", {
    class: "gut gut-" + kind, title: "Drag to resize; double-click resets",
    onpointerdown: (event) => startGutter(event, kind, index), ondblclick: () => resetGutter(kind, index) });
  const obs = h("div", { class: "obs", id: "obsRoot", onpointerdown: startPanelMove },
    preview, gutter("right"), slots[0], gutter("bottom"),
    h("div", { class: "docks" }, slots[1], gutter("col", 0), slots[2], gutter("col", 1), slots[3]),
    slots[4]);
  studio.layoutNodes = { obs, slots, panels: Object.fromEntries(LAYOUT_PANELS.map((id) => [id, layoutPanel(id)])) };
  applyLayout();
  return obs;
}

/** Put each panel into its slot and the sizes into the grid's CSS variables. */
function applyLayout() {
  const nodes = studio.layoutNodes;
  if (!nodes) return;
  const layout = studio.layout;
  layout.order.forEach((id, index) => {
    const slot = nodes.slots[index], panel = nodes.panels[id];
    if (panel.parentNode !== slot) slot.append(panel);  // append moves the panel with everything in it
  });
  const style = nodes.obs.style;
  if (style && style.setProperty) {
    style.setProperty("--right", layout.right + "px");
    style.setProperty("--bottom", layout.bottom + "px");
    layout.cols.forEach((value, index) => style.setProperty("--c" + (index + 1), value + "fr"));
  }
}

const clampTo = (value, low, high) => Math.min(Math.max(value, low), Math.max(low, high));

/** Resize while the pointer moves: `right` = the right column's width, `bottom` = the docks' height, `col` = two neighbouring docks. */
function resizeLayout(layout, kind, index, box, point, pair) {
  if (kind === "right") layout.right = Math.round(clampTo(box.right - point.x - 4, LAYOUT_MIN.right, box.width - LAYOUT_MIN.main));
  else if (kind === "bottom") layout.bottom = Math.round(clampTo(box.bottom - point.y - 4, LAYOUT_MIN.bottom, box.height - LAYOUT_MIN.preview));
  else {
    const total = layout.cols[index] + layout.cols[index + 1];
    const share = clampTo((point.x - pair.left) / Math.max(1, pair.right - pair.left), LAYOUT_MIN.share, 1 - LAYOUT_MIN.share);
    layout.cols[index] = +(total * share).toFixed(3);
    layout.cols[index + 1] = +(total - layout.cols[index]).toFixed(3);
  }
}

function startGutter(event, kind, index) {
  if (event.button !== 0 || !studio.layoutNodes) return;
  event.preventDefault();
  event.stopPropagation();
  const { obs, slots } = studio.layoutNodes;
  const box = obs.getBoundingClientRect();
  const pair = kind === "col" ? { left: slots[index + 1].getBoundingClientRect().left, right: slots[index + 2].getBoundingClientRect().right } : null;
  document.body.classList.add("resizing", kind === "bottom" ? "row-resize" : "col-resize");
  const move = (moved) => {
    if (moved.buttons === 0) { up(); return; }  // the release happened outside the window
    resizeLayout(studio.layout, kind, index, box, { x: moved.clientX, y: moved.clientY }, pair);
    applyLayout();
  };
  const up = () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", up);
    removeEventListener("pointercancel", up);
    document.body.classList.remove("resizing", "row-resize", "col-resize");
    saveLayout();
  };
  addEventListener("pointermove", move);
  addEventListener("pointerup", up);
  addEventListener("pointercancel", up);
}

function resetGutter(kind, index) {
  const layout = studio.layout;
  if (kind === "col") { layout.cols[index] = LAYOUT_DEFAULT.cols[index]; layout.cols[index + 1] = LAYOUT_DEFAULT.cols[index + 1]; }
  else layout[kind] = LAYOUT_DEFAULT[kind];
  saveLayout();
  applyLayout();
}

function resetLayout() {
  studio.layout = defaultLayout();
  saveLayout();
  applyLayout();
  toast("Panel layout reset");
}

/** Two slots trade their panels. */
function swapPanels(layout, from, to) {
  if (from === to || from < 0 || to < 0) return false;
  [layout.order[from], layout.order[to]] = [layout.order[to], layout.order[from]];
  return true;
}

/** Drag a panel by its title onto another panel: they swap places. A click (under 6 px) stays a click. */
function startPanelMove(event) {
  const nodes = studio.layoutNodes;
  if (!nodes || event.button !== 0 || !event.target.closest) return;
  const header = event.target.closest("header");
  if (!header || event.target.closest("button, input, select, label, a, kbd")) return;
  const from = nodes.slots.indexOf(header.parentNode && header.parentNode.parentNode);
  if (from < 0) return;
  const start = { x: event.clientX, y: event.clientY };
  let moving = false, target = -1;
  const mark = (index) => { if (target >= 0) nodes.slots[target].classList.remove("droptarget"); target = index; if (target >= 0) nodes.slots[target].classList.add("droptarget"); };
  const move = (moved) => {
    if (moved.buttons === 0) { mark(-1); up(); return; }  // released outside the window: no swap
    if (!moving && Math.hypot(moved.clientX - start.x, moved.clientY - start.y) < 6) return;
    if (!moving) { moving = true; nodes.slots[from].classList.add("lifted"); document.body.classList.add("moving-panel"); }
    const over = document.elementFromPoint(moved.clientX, moved.clientY);
    const slot = over && over.closest ? over.closest(".slot") : null;
    const index = nodes.slots.indexOf(slot);
    mark(index === from ? -1 : index);
  };
  const up = () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", up);
    removeEventListener("pointercancel", up);
    nodes.slots[from].classList.remove("lifted");
    document.body.classList.remove("moving-panel");
    const to = target;
    mark(-1);
    if (moving && swapPanels(studio.layout, from, to)) { saveLayout(); applyLayout(); }
  };
  addEventListener("pointermove", move);
  addEventListener("pointerup", up);
  addEventListener("pointercancel", up);
}

function renderStudioBody() {
  const root = $("studioRoot");
  if (!root) return;
  root.textContent = "";
  root.className = "studio" + (studio.tab === "record" && studio.setup ? " rec" : "");
  const tabs = h("div", { class: "seg" },
    h("button", { class: studio.tab === "record" ? "on" : "", text: "Record", onclick: () => setStudioTab("record") }),
    h("button", { class: studio.tab === "projects" ? "on" : "", text: "Projects", onclick: () => setStudioTab("projects") }),
    h("button", { class: studio.tab === "edit" ? "on" : "", text: "Edit", title: "Cut, subtitles, text and music for a project", onclick: () => setStudioTab("edit") }));
  const head = h("div", { class: "sthead" }, tabs, h("span", { class: "spacer" }));
  if (studio.tab === "record" && studio.setup) {
    head.append(iconButton("layout", "Reset the panel layout (drag a panel's title to move it, the gaps to resize)", resetLayout),
      iconButton("undo", "Undo (⌘Z; ⇧⌘Z redoes)", () => undoEdit(false)),
      h("span", { class: "lbl", text: "Format" }), h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
        h("button", { class: currentCanvas() === value ? "on" : "", text: label, title: value === "source" ? "The screen as recorded, no composition" : "Layout for " + value, onclick: () => { studio.setup.canvas = value; edited(renderStudioBody); } }))));
  }
  root.append(head);
  if (studio.tab === "projects") { root.append(h("div", { id: "studioProjects" })); renderProjects(); return; }
  if (studio.tab === "edit") {
    root.append(h("div", { id: "studioEdit" }));
    const last = localStorage.getItem("studio-edit-path");
    if (!studio.project && last && !studio.editTried) { studio.editTried = true; openEdit(last).catch(() => {}); }
    renderEdit();
    return;
  }
  if (!studio.setup) {
    root.append(studio.setupError
      ? h("div", { class: "empty" }, h("div", { text: "The studio setup could not be read: " + studio.setupError }),
          h("button", { text: "Try again", onclick: () => loadSetup().then(() => state.view === "studio" && renderStudioBody()) }))
      : h("div", { class: "empty", text: "Loading the studio setup…" }));
    return;
  }
  root.append(layoutFrame(h("div", { class: "preview" },
    h("div", { class: "pvtop" }, h("div", { id: "permBanner" }), h("div", { class: "warns", id: "warnStrip" })),
    h("div", { class: "stagebox", id: "stageBox" }, stageFrame()),
    h("canvas", { class: "voice", id: "voiceWave", "aria-label": "Sound wave of the audio recording" }),
    h("div", { class: "pvbar", id: "pvBar" }))));
  watchStageSize();
  renderScenes();
  renderSources();
  renderBanner();
  drawStage();
  renderPreviewBar();
  renderRecBar();
  renderSound();
  renderProps();
  updateRecordControls();
  startPreview();
  ensureCamera();
  autoMeter();
}

function permissionBanner(doctor) {
  if (!doctor || doctor.screen !== false) return null;
  const app = doctor.app || "the app that runs ul";
  return h("div", { class: "banner" },
    h("b", { text: "No screen recording permission." }),
    h("span", { text: "Give " + app + " Screen Recording permission in System Settings › Privacy & Security, then quit and reopen " + app + ". Camera and microphone still record." }),
    h("button", { text: "Open System Settings", onclick: () => openSettings("screen") }),
    h("button", { class: "ghost", text: "Check again", onclick: loadDoctor }));
}

function renderBanner() {
  const box = $("permBanner");
  if (!box) return;
  box.textContent = "";
  const banner = permissionBanner(studio.doctor);
  if (banner) box.append(banner);
}

async function openSettings(kind) {
  const { status, data } = await api("POST", "/api/studio/open-settings", { kind });
  if (status !== 200) { toast(data.error || "Could not open System Settings"); return; }
  studio.doctor = data;
  renderBanner();
}

function renderScenes() {
  const box = $("scenesPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const setup = studio.setup, current = currentScene(), recording = Boolean(studio.status.active);
  box.append(h("header", {}, h("span", { text: "Scenes" })));
  const list = h("div", { class: "dlist", role: "listbox" });
  studio.sceneRows = {};
  setup.scenes.forEach((scene, index) => {
    const name = h("span", { class: "name", text: scene.name });
    const row = h("div", { class: "drow" + (scene.id === current ? " on" : ""), role: "option", tabindex: "0", title: scene.name + " · key " + (index + 1) + " · double-click to rename · right-click for more",
      onclick: () => selectScene(scene.id), ondblclick: () => renameScene(scene.id), oncontextmenu: (event) => sceneMenu(event, scene.id) },
      studioIcon("scene"), name, h("kbd", { text: String(index + 1) }));
    studio.sceneRows[scene.id] = name;
    list.append(row);
  });
  box.append(list);
  const at = setup.scenes.findIndex((scene) => scene.id === current);
  box.append(h("footer", {},
    iconButton("plus", "Add a scene (a copy of this one)", () => addScene(current)),
    iconButton("minus", "Remove this scene", () => removeScene(current), "", recording || setup.scenes.length < 2),
    iconButton("pencil", "Rename this scene", () => renameScene(current)),
    h("span", { class: "spacer" }),
    iconButton("up", "Move up", () => moveScene(current, -1), "", at <= 0),
    iconButton("down", "Move down", () => moveScene(current, 1), "", at < 0 || at >= setup.scenes.length - 1)));
}

function addScene(from, name) {
  const setup = studio.setup;
  if (setup.scenes.length >= 9) { toast("A studio has at most 9 scenes (keys 1-9)"); return; }
  let number = setup.scenes.length + 1;
  while (setup.scenes.some((item) => item.id === "scene-" + number)) number += 1;
  const id = "scene-" + number;
  const base = from || currentScene();
  setup.scenes.splice(setup.scenes.findIndex((item) => item.id === base) + 1, 0, { id, name: (name || "Scene " + number).slice(0, 40) });
  for (const canvas of Object.keys(setup.layouts)) {
    const source = setup.layouts[canvas][base];
    if (source) setup.layouts[canvas][id] = studioClone(source);
  }
  edited();
  selectScene(id);
  renameScene(id);
}

// Rename in place: the name in the Scenes list becomes a field (Enter saves, Esc cancels).
function renameScene(id) {
  const setup = studio.setup, scene = setup.scenes.find((item) => item.id === id);
  const name = studio.sceneRows && studio.sceneRows[id];
  if (!scene || !name || !name.replaceWith) return;
  const input = h("input", { type: "text", class: "rename", value: scene.name, maxlength: "40" });
  let done = false;
  const finish = (save) => {
    if (done) return;
    done = true;
    const value = input.value.trim().slice(0, 40);
    if (save && value && value !== scene.name) { scene.name = value; edited(renderScenes, renderProps); }
    else renderScenes();
  };
  input.addEventListener("keydown", (event) => { event.stopPropagation(); if (event.key === "Enter") finish(true); else if (event.key === "Escape") finish(false); });
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("click", (event) => event.stopPropagation());
  name.replaceWith(input);
  input.focus();
  input.select();
}

function renderSources() {
  const box = $("sourcesPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  box.append(h("header", {}, h("span", { text: "Sources" }), h("span", { class: "hint", text: sceneName(currentScene()) })));
  const list = h("div", { class: "dlist", role: "listbox" });
  // Like OBS: the top of the list is in front.
  for (const source of [...studio.setup.sources].reverse()) {
    const item = placementOf(source.id);
    const visible = Boolean(item && item.visible), locked = isLocked(source.id);
    const off = source.kind !== "screen" && !source.enabled;
    list.append(h("div", { class: "drow src" + (source.id === studio.selected ? " on" : "") + (off ? " off" : ""), role: "option", tabindex: "0",
      title: "Click to select · double-click for its settings · right-click for more",
      onclick: () => selectSource(source.id), ondblclick: () => focusInspector(), oncontextmenu: (event) => sourceMenu(event, source.id) },
      studioIcon(SOURCE_ICON[source.kind]), h("span", { class: "name", text: sourceName(source) + (off ? " (off)" : "") }),
      iconButton(visible ? "eye" : "eyeOff", visible ? "Hide in this scene" : "Show in this scene", (event) => { event.stopPropagation(); toggleVisible(source.id); }, visible ? "" : "dim"),
      iconButton(locked ? "lock" : "unlock", locked ? "Locked: it cannot be moved on the preview (click to unlock)" : "Lock its position", (event) => { event.stopPropagation(); toggleLock(source.id); }, locked ? "" : "dim")));
  }
  box.append(list);
  const selected = sourceById(studio.selected);
  const at = selected ? studio.setup.sources.indexOf(selected) : -1;
  box.append(h("footer", {},
    iconButton("plus", "Add a source (image or text)", (event) => openSourceMenu(event.currentTarget)),
    iconButton("minus", "Remove the selected source (Delete)", deleteSelected, "", !selected),
    iconButton("gear", "Settings of the selected source", focusInspector, "", !selected),
    h("span", { class: "spacer" }),
    iconButton("up", "Move forward", () => moveSource(studio.selected, 1), "", at < 0 || at >= studio.setup.sources.length - 1),
    iconButton("down", "Move backward", () => moveSource(studio.selected, -1), "", at <= 0)));
}

function selectSource(id) {
  studio.selected = id;
  renderSources();
  drawStage();
  renderProps();
}

function toggleVisible(id) {
  const layout = currentLayout();
  const source = sourceById(id);
  // The eye of a camera that is off turns it on: showing it while it records nothing looked like a broken camera.
  if (source && source.kind === "camera" && !source.enabled) { setCamera(true); return; }
  if (!layout) { toast("“As recorded” has no layout; pick a format to show or hide sources"); return; }
  if (!layout.placements[id]) layout.placements[id] = defaultPlacement(source, currentCanvas());
  else layout.placements[id].visible = !layout.placements[id].visible;
  edited(renderSources, drawStage, renderProps);
}

// The camera on or off for recording; turning it on also shows it in the current scene.
function setCamera(on) {
  const source = cameraSource();
  if (!source || (studio.status && studio.status.active)) return;
  source.enabled = on;
  if (on) {
    const layout = currentLayout();
    if (layout) {
      if (!layout.placements[source.id]) layout.placements[source.id] = defaultPlacement(source, currentCanvas());
      layout.placements[source.id].visible = true;
    }
    ensureCamera();
  } else stopStream("camStream");
  edited(renderSources, drawStage, renderProps, updateRecordControls, renderRecBar);
}

function defaultPlacement(source, canvas, aspect) {
  const item = { visible: true, box: [0, 0, 1, 1], fit: "cover", focus: [0.5, 0.5], radius: 0, border: { width: 0, color: "#ffc933" }, shadow: false, mirror: false, anchor: null };
  if (source.kind === "screen") { item.fit = "contain"; return item; }
  if (source.kind === "camera") { item.mirror = true; return applyShape({ ...item, box: [0, 0, 0.24, 0.24], anchor: "bottom-left" }, "wide", canvas); }
  const [cw, ch] = STUDIO_RATIOS[canvas] || [16, 9];
  const width = 0.2, height = Math.min(1, (width * cw) / ch / (aspect || 1));
  item.fit = "contain";
  return pinPlacement({ ...item, box: [0, 0, width, height] }, "top-right");
}

function openStudioMenu(anchor, items) {
  const box = anchor.getBoundingClientRect();
  showMenu(Math.round(box.left), Math.round(box.bottom + 4), items);
}

function openSourceMenu(anchor) {
  if (studio.setup.sources.length >= 12) { toast("A studio has at most 12 sources"); return; }
  openStudioMenu(anchor, [
    h("button", { onclick: () => { closeStudioMenu(); pickImage(); } }, studioIcon("image"), "Image…"),
    h("button", { onclick: () => { closeStudioMenu(); addTextSource(); } }, studioIcon("text"), "Text"),
  ]);
}

function freeSourceId(prefix) {
  let number = 1;
  while (sourceById(prefix + "-" + number)) number += 1;
  return prefix + "-" + number;
}

async function uploadAsset(name, blob) {
  let response;
  try {
    response = await fetch("/api/studio/asset?name=" + encodeURIComponent(name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: blob });
  } catch (error) { toast("Could not reach the desk: " + error.message); return null; }
  let data = {};
  try { data = await response.json(); } catch (error) { data = {}; }
  if (response.status !== 200) { toast(data.error || "Upload failed"); return null; }
  return data.asset;
}

function imageSize(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve([image.naturalWidth || 1, image.naturalHeight || 1]);
    image.onerror = () => resolve([1, 1]);
    image.src = url;
  });
}

// A new source shows in the current scene, in every format, and is selected.
function addSourceWithPlacement(source, aspect) {
  studio.setup.sources.push(source);
  for (const [canvas, scenes] of Object.entries(studio.setup.layouts)) {
    for (const [scene, layout] of Object.entries(scenes)) {
      const item = defaultPlacement(source, canvas, aspect);
      item.visible = scene === currentScene();
      layout.placements[source.id] = item;
    }
  }
  studio.selected = source.id;
  edited(renderSources, drawStage, renderProps);
}

function pickImage() {
  const input = h("input", { type: "file", accept: "image/png,image/jpeg" });
  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) { toast("An image can be at most 50 MB"); return; }
    const asset = await uploadAsset(file.name, file);
    if (!asset) return;
    const local = URL.createObjectURL(file);
    const [width, height] = await imageSize(local);
    URL.revokeObjectURL(local);
    addSourceWithPlacement({ id: freeSourceId("img"), kind: "image", enabled: true, asset }, width / height);
  });
  input.click();
}

const TEXT_FONTS = [["-apple-system, Helvetica, sans-serif", "System"], ["Georgia, serif", "Georgia"], ["Menlo, monospace", "Menlo"], ["'Avenir Next', sans-serif", "Avenir Next"], ["'Helvetica Neue', sans-serif", "Helvetica Neue"]];

// Text sources are pictures: the page draws the text into a PNG and uploads it (ffmpeg here has no drawtext).
async function renderTextAsset(source) {
  const scale = 2, padding = Math.round(source.size * 0.35);
  const measure = document.createElement("canvas").getContext("2d");
  const font = "600 " + source.size * scale + "px " + source.font;
  measure.font = font;
  const lines = source.text.split("\n");
  const width = Math.ceil(Math.max(...lines.map((line) => measure.measureText(line).width)) + padding * 2 * scale);
  const lineHeight = Math.round(source.size * 1.25 * scale);
  const height = lineHeight * lines.length + padding * 2 * scale;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(2, width);
  canvas.height = Math.max(2, height);
  const context = canvas.getContext("2d");
  if (source.background) {
    context.fillStyle = source.background;
    context.beginPath();
    context.roundRect(0, 0, canvas.width, canvas.height, Math.round(padding * scale * 0.8));
    context.fill();
  }
  context.font = font;
  context.fillStyle = source.color;
  context.textBaseline = "middle";
  lines.forEach((line, index) => context.fillText(line, padding * scale, padding * scale + lineHeight * (index + 0.5)));
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) { toast("Could not draw the text"); return null; }
  const asset = await uploadAsset("text " + source.id + ".png", blob);
  return asset ? { asset, aspect: canvas.width / canvas.height } : null;
}

async function addTextSource() {
  const source = { id: "", kind: "text", enabled: true, asset: "", text: "Subscribe", font: TEXT_FONTS[0][0], size: 64, color: "#ffffff", background: "#000000" };
  const drawn = await renderTextAsset(source);
  if (!drawn) return;
  if (studio.setup.sources.length >= 12) { toast("A studio has at most 12 sources"); return; }
  source.id = freeSourceId("text");  // after the await: two quick additions must not share an id
  source.asset = drawn.asset;
  addSourceWithPlacement(source, drawn.aspect);
}

function removeSource(id) {
  const source = sourceById(id);
  if (!source || source.kind === "screen" || source.kind === "camera") return;
  studio.setup.sources = studio.setup.sources.filter((item) => item.id !== id);
  for (const scenes of Object.values(studio.setup.layouts)) for (const layout of Object.values(scenes)) delete layout.placements[id];
  studio.selected = null;
  edited(renderSources, drawStage, renderProps);
  toast("Removed " + sourceName(source) + " (⌘Z brings it back)");
}

function stageRatio() {
  const canvas = currentCanvas();
  if (STUDIO_RATIOS[canvas]) return STUDIO_RATIOS[canvas][0] / STUDIO_RATIOS[canvas][1];
  if (studio.project) {
    const info = ((studio.project.segments[0] || {}).info || {}).screen;
    return info && info.width && info.height ? info.width / info.height : 16 / 10;
  }
  const display = displayInfo();
  const pixels = display && /(\d+)\s*x\s*(\d+)/.exec(display.pixels || "");
  return pixels ? Number(pixels[1]) / Number(pixels[2]) : 16 / 10;
}

function displayInfo() {
  const screen = screenSource();
  return studio.devices && screen ? studio.devices.displays.find((item) => item.number === screen.display) || null : null;
}

// The preview draws every visible source with the box, fit, focus, radius, border, shadow and mirror the export uses.
function drawStage() {
  const stage = $("stage");
  if (!stage || !studioDoc()) return;  // the project page needs only the project
  const frame = $("stageWrap") || stage, overlay = $("stageUi");
  const ratio = stageRatio();
  frame.style.aspectRatio = String(ratio);
  frame.style.width = $("stageBox") ? "min(100cqw, calc(100cqh * " + ratio.toFixed(4) + "))" : "min(100%, calc(58vh * " + ratio.toFixed(4) + "))";
  stage.textContent = "";
  if (overlay) overlay.textContent = "";
  studio.stageNodes = {};
  const canvas = currentCanvas();
  const layout = currentLayout();
  const width = frame.clientWidth || 640, height = width / ratio;
  const scale = Math.min(width, height) / 1080;
  const items = [];
  if (canvas === "source") {
    const screen = studioDoc().sources.find((source) => source.kind === "screen");
    if (screen) items.push([screen, { visible: true, box: [0, 0, 1, 1], fit: "contain", focus: [0.5, 0.5], radius: 0, border: { width: 0, color: "#000000" }, shadow: false, mirror: false, anchor: null }]);
    stage.style.background = "#000000";
  } else if (studio.project) {
    const [background, placed] = projectPlacements(studio.project, currentScene(), canvas);
    stage.style.background = background.kind === "color" ? background.color : "#000000";
    items.push(...placed);
  } else if (layout) {
    const background = layout.background;
    stage.style.background = background.kind === "color" ? background.color : "#000000";
    if (background.kind === "blur") {
      if (studio.screenStream) { const video = streamVideo("screenBgVideo", studio.screenStream); video.className = "bg"; stage.append(video); }
      else if (studio.screenUrl) stage.append(h("img", { class: "bg screen", src: studio.screenUrl, alt: "" }));
    }
    for (const source of studio.setup.sources) {
      const item = layout.placements[source.id];
      if (item && item.visible) items.push([source, item]);
    }
  }
  const editable = canvas !== "source";
  if (!items.length) stage.append(h("div", { class: "empty", text: "Nothing is shown in this scene. Turn a source on with its eye in Sources." }));
  for (const [source, item] of items) {
    const node = stageNode(source, item, width, height, scale, editable);
    studio.stageNodes[source.id] = node;
    stage.append(node);
  }
  stage.append(h("span", { class: "badge", id: "stageBadge" }));
  stage.onpointerdown = (event) => { if (event.target === stage && studio.selected !== null) selectSource(null); };
  const selected = items.find(([source]) => source.id === studio.selected);
  if (selected && editable) (overlay || stage).append(selectionBox(selected[0], selected[1]));
  const hint = $("stageHint");
  if (hint) hint.textContent = canvas === "source" ? "As recorded: the screen exactly as captured, no layout." : "Drag to move (snaps to edges and the centre) · handles resize (⇧ frees the shape) · ⌥-drag pans inside · arrows nudge · Delete removes";
  if (studio.project) { resumePlayer(); return; }
  drawCountdown();
  drawRecording();
}

function stageNode(source, item, width, height, scale, editable) {
  const px = placementPx(item, width, height);
  const node = h("div", { class: "ph" + (editable && source.id === studio.selected ? " sel" : "") + (editable && isLocked(source.id) ? " locked" : "") });
  placeNode(node, item);
  node.style.borderRadius = Math.round(item.radius * Math.min(px.w, px.h)) + "px";
  if (item.border.width) node.style.border = Math.max(1, Math.round(item.border.width * scale)) + "px solid " + item.border.color;
  if (item.shadow) node.style.boxShadow = "0 " + Math.round(8 * scale) + "px " + Math.round(28 * scale) + "px rgba(0,0,0,.55)";
  const fitStyle = (child) => {
    child.style.objectFit = item.fit;
    child.style.objectPosition = item.focus[0] * 100 + "% " + item.focus[1] * 100 + "%";
    // Videos are reused across redraws, so the transform is always set (or cleared).
    child.style.transform = item.mirror ? "scaleX(-1)" : "";
    return child;
  };
  const player = studio.project && studio.player;
  if (player && (source.kind === "screen" || source.kind === "camera")) {
    node.append(fitStyle(player[source.kind]));
  } else if (player) {
    node.append(fitStyle(h("img", { src: projectMedia(studio.project.path, "assets/" + source.asset), alt: "" })));
  } else if (source.kind === "screen") {
    if (studio.screenStream) { const video = streamVideo("screenVideo", studio.screenStream); video.className = "screen live"; node.append(fitStyle(video)); }
    else if (studio.screenUrl && !studio.screenFailed) node.append(fitStyle(h("img", { class: "screen", src: studio.screenUrl, alt: "" })));
    else node.append(h("div", { class: "camph", text: studio.screenFailed ? "No screen preview (see above)" : "Screen " + source.display }));
  } else if (source.kind === "camera") {
    if (studio.camStream) node.append(fitStyle(streamVideo("camVideo", studio.camStream)));
    else node.append(h("div", { class: "camph", text: source.enabled ? "Camera" : "Camera (off)" }));
  } else {
    node.append(fitStyle(h("img", { src: media("/media/asset", source.asset), alt: "" })));
  }
  if (!editable) return node;
  node.addEventListener("pointerdown", (event) => startStageDrag(event, source.id, event.altKey ? "focus" : "move"));
  node.addEventListener("dblclick", focusInspector);
  node.addEventListener("contextmenu", (event) => { if (studio.selected !== source.id) selectSource(source.id); sourceMenu(event, source.id); });
  return node;
}

function startStageDrag(event, id, mode) {
  if (event.button !== 0) return;
  event.preventDefault();
  closeStudioMenu();
  if (studio.selected !== id) selectSource(id);
  if (isLocked(id)) return;
  const stage = $("stage"), layout = currentLayout();
  if (!stage || !layout || !layout.placements[id]) return;
  const start = studioClone(layout.placements[id]);
  const rect = stage.getBoundingClientRect();
  const source = sourceById(id);
  let moved = false;
  const move = (e) => {
    if (!moved && Math.abs(e.clientX - event.clientX) + Math.abs(e.clientY - event.clientY) < 3) return;
    moved = true;
    const dx = (e.clientX - event.clientX) / rect.width, dy = (e.clientY - event.clientY) / rect.height;
    let next;
    if (mode === "move") next = clampBox({ ...studioClone(start), box: [start.box[0] + dx, start.box[1] + dy, start.box[2], start.box[3]], anchor: null });
    else if (mode === "focus") next = moveFocus(start, dx / start.box[2], dy / start.box[3]);
    else {
      const where = mode.slice(7);
      next = clampBox(where.includes("-") ? resizePlacement(start, where, dx, dy, (source.kind !== "screen") !== e.shiftKey) : resizeEdge(start, where, dx, dy));
    }
    layout.placements[id] = next;
    placeNode(studio.stageNodes[id], next);
    placeNode($("selBox"), next);
    const node = studio.stageNodes[id], child = node && node.querySelector && node.querySelector("img, video");
    if (child && mode === "focus") child.style.objectPosition = next.focus[0] * 100 + "% " + next.focus[1] * 100 + "%";
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
    if (!moved) return;
    if (mode === "move") layout.placements[id] = snapPlacement(layout.placements[id], currentCanvas());
    if (JSON.stringify(start) !== JSON.stringify(layout.placements[id])) edited(drawStage, renderProps);
    else drawStage();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", up);
}

function shapeButtons(item, onpick) {
  const current = shapeOf(item, currentCanvas());
  const sizes = { circle: [12, 12, "50%"], square: [12, 12, "0"], rounded: [12, 12, "4px"], wide: [16, 9, "0"], tall: [9, 16, "0"] };
  return h("div", { class: "shapes" }, Object.keys(STUDIO_SHAPES).map((shape) => {
    const mark = h("i");
    Object.assign(mark.style, { width: sizes[shape][0] + "px", height: sizes[shape][1] + "px", borderRadius: sizes[shape][2] });
    return h("button", { class: current === shape ? "on" : "", title: shape[0].toUpperCase() + shape.slice(1), onclick: () => onpick(shape) }, mark);
  }));
}

function cornerButtons(item, onpick) {
  return h("div", { class: "corners" }, STUDIO_ANCHORS.map((anchor) =>
    h("button", { class: item.anchor === anchor ? "on" : "", title: "Pin to the " + anchor.replace("-", " ") + " corner", "aria-label": "Pin to the " + anchor.replace("-", " ") + " corner", onclick: () => onpick(anchor) }, studioIcon(anchor))));
}

function changePlacement(id, change) {
  const layout = currentLayout();
  if (!layout || !layout.placements[id]) return;
  layout.placements[id] = change(layout.placements[id]);
  edited(drawStage, renderScenes, renderProps);
}

function renderRecBar() {
  const box = $("recBar");
  if (!box) return;
  box.textContent = "";
  box.append(h("header", {}, h("span", { text: "Controls" })),
    h("div", { class: "cbody" },
      h("button", { class: "recbtn", id: "recButton", title: "Start / stop recording (R)", onclick: () => toggleRecord() }, h("i"), h("span", { id: "recLabel", text: "Start recording" })),
      h("button", { class: "pill audiobtn", id: "recAudio", title: "Record only the microphone, no screen or camera (A)", onclick: () => toggleRecord("audio") }, studioIcon("mic"), "Record audio only"),
      cameraSource() ? h("button", { class: "pill" + (cameraSource().enabled ? " on" : ""), id: "recCamera", title: "Record the camera with the screen (it shows in the scenes that place it)",
        disabled: Boolean(studio.status && studio.status.active) || null, onclick: () => setCamera(!cameraSource().enabled) }, studioIcon("camera"), cameraSource().enabled ? "Camera on" : "Camera off") : null,
      h("div", { class: "crow" }, h("span", { class: "recclock", id: "recClock", text: "00:00" }), h("span", { class: "recstate", id: "recState" })),
      h("div", { class: "crow" },
        h("button", { class: "pill", id: "recPause", title: "Pause / resume (P)", onclick: pauseRecord }, studioIcon("pause"), "Pause"),
        h("button", { class: "pill", id: "recMark", title: "Add a mark at this moment (M)", onclick: addMark }, studioIcon("flag"), "Mark")),
      h("div", { class: "crow" },
        h("button", { class: "pill", title: "Take a screenshot", onclick: (event) => openShotMenu(event.currentTarget) }, studioIcon("shot"), "Screenshot", studioIcon("chevron")),
        h("button", { class: "pill", title: "Recording files, countdown, menu-bar clock", onclick: (event) => openRecordSettings(event.currentTarget) }, studioIcon("gear"), "Settings")),
      h("div", { class: "info", id: "recInfo" })));
}

function openShotMenu(anchor) {
  const delay = h("select", {}, [["0", "No delay"], ["3", "3 s delay"], ["5", "5 s delay"], ["10", "10 s delay"]].map(([value, label]) => h("option", { value, text: label, selected: String(studio.delay) === value })));
  delay.addEventListener("change", () => { studio.delay = Number(delay.value); });
  const clip = h("input", { type: "checkbox" });
  clip.checked = studio.clipboard;
  clip.addEventListener("change", () => { studio.clipboard = clip.checked; });
  openStudioMenu(anchor, [
    ...["screen", "area", "window"].map((kind) => h("button", { text: kind[0].toUpperCase() + kind.slice(1), onclick: () => { closeStudioMenu(); takeShot(kind); } })),
    h("label", {}, delay), h("label", {}, clip, "Copy to the clipboard"),
  ]);
}

function updateRecordControls() {
  const s = studio.status;
  const button = $("recButton");
  if (!button) return;
  const active = Boolean(s.active || studio.starting);
  button.className = "recbtn" + (active ? " on" : "");
  const busy = studio.saving || s.phase === "saving";
  $("recLabel").textContent = studio.counting ? "Cancel (" + studio.counting + ")" : studio.starting ? "Starting…" : busy ? "Saving…" : s.active ? "Stop recording" : "Start recording";
  const pause = $("recPause");
  pause.disabled = !s.active || busy || Boolean(studio.starting);
  pause.textContent = "";
  pause.append(studioIcon(s.paused ? "play" : "pause"), s.paused ? "Resume" : "Pause");
  $("recMark").disabled = !s.active || Boolean(studio.starting);
  const audio = $("recAudio");
  if (audio) audio.disabled = active || busy || Boolean(studio.counting);
  $("recState").textContent = studio.counting ? "Starting in " + studio.counting + "…" : studio.starting ? "Waking the microphone and camera…" : busy ? "Saving…" : s.phase === "interrupted" ? "A recorder stopped; press stop to save the rest" : s.phase === "unsaved" ? "Not saved; press stop to try again" : s.phase === "stuck" ? "A recorder hangs" : s.active ? (s.paused ? "Paused" : s.mode === "audio" ? "Recording audio" : "Recording") : "Ready";
  const display = displayInfo();
  const free = s.free_bytes;
  $("recInfo").textContent = "";
  $("recInfo").append(
    h("div", { text: (display ? display.pixels.replace(/\s*x\s*/, "×") + " · " : "") + "60 fps" }),
    h("div", { text: (free ? "free " + gigabytes(free) + " · " : "") + "≈ " + megabytesPerMinute(studio.setup) + " MB/min" }));
  renderWarnings();
  drawRecording();
}

function renderWarnings() {
  const box = $("warnStrip");
  if (!box) return;
  box.textContent = "";
  const s = studio.status;
  for (const warning of s.warnings || []) box.append(h("div", {}, studioIcon("alert"), h("span", { text: warning })));
  if ((s.stuck && s.stuck.length) || s.phase === "stuck") {
    box.append(h("div", {}, studioIcon("alert"), ((s.stuck || []).join(", ") || "A recorder") + " does not stop. Stop again to retry, or kill it (its track is lost).",
      h("button", { text: "Force stop", onclick: forceStop })));
  }
}

function prow(label, ...controls) { return h("div", { class: "prow" }, h("span", { class: "lbl", text: label }), ...controls); }
function studioSelect(options, value, onchange) {
  const node = h("select", {}, options.map(([v, label]) => h("option", { value: v, text: label, selected: v === value })));
  node.addEventListener("change", () => onchange(node.value));
  return node;
}
function studioCheck(value, onchange, label) {
  const input = h("input", { type: "checkbox" });
  input.checked = Boolean(value);
  input.addEventListener("change", () => onchange(input.checked));
  return label ? h("label", { class: "check" }, input, " " + label) : input;
}
function studioRange(min, max, step, value, oninput, shown) {
  const input = h("input", { type: "range", min, max, step, value });
  const val = h("span", { class: "val", text: shown(value) });
  input.addEventListener("input", () => { val.textContent = shown(Number(input.value)); oninput(Number(input.value), false); });
  input.addEventListener("change", () => oninput(Number(input.value), true));
  return [input, val];
}

// The audio mixer: one channel per input, OBS style. The button turns the input on or off for the next
// recording (off = not recorded at all, and the page closes the microphone).
function renderSound() {
  const box = $("soundPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const audio = studio.setup.audio, devices = studio.devices, recording = Boolean(studio.status.active || studio.starting);
  box.append(h("header", {}, h("span", { text: "Audio mixer" })));
  const body = h("div", { class: "mixer" });
  const mics = [["default", "Default microphone"], ...(devices ? devices.microphones.map((item) => [item.name, item.name + (item.virtual ? " (virtual)" : "")]) : [])];
  if (!mics.some(([value]) => value === audio.mic.device)) mics.splice(1, 0, [audio.mic.device, audio.mic.device]);
  const device = studioSelect(mics, audio.mic.device, (value) => {
    audio.mic.device = value;
    const chosen = devices && devices.microphones.find((item) => item.name === value);
    if (chosen && chosen.virtual) toast(value + " is virtual: it carries app audio, not your voice");
    if (studio.micStream) { stopStream("micStream"); toggleMeter(); }
    edited(renderSound);
  });
  device.disabled = recording;
  const micOn = audio.mic.enabled;
  const level = micOn && !studio.micStream && !recording ? h("button", { class: "ghost tiny", text: "Show level", title: "Open the microphone in this page to show its level (the recording itself uses ul capture)", onclick: toggleMeter }) : null;
  body.append(h("div", { class: "chan" + (micOn ? "" : " muted") },
    h("div", { class: "chead" }, h("b", { text: "Mic" }), device, h("span", { class: "db", id: "micDb" })),
    h("div", { class: "meter", id: "micMeter", title: "-60 dB … 0 dB" }, h("i")),
    h("div", { class: "cctl" },
      iconButton(micOn ? "mic" : "micOff", micOn ? "The microphone is on: click to turn it off" : "The microphone is off (not recorded): click to turn it on", () => toggleInput("mic"), micOn ? "" : "danger", recording),
      ...studioRange(0, 200, 5, Math.round(audio.mic.volume * 100), (value, done) => { audio.mic.volume = value / 100; if (done) edited(); }, (v) => v + "%"), level)));
  const macOn = audio.system.enabled;
  body.append(h("div", { class: "chan" + (macOn ? "" : " muted") },
    h("div", { class: "chead" }, h("b", { text: "Mac sound" }), h("span", { class: "note", text: macOn ? "what the Mac plays" : "off: not recorded" })),
    h("div", { class: "cctl" },
      iconButton(macOn ? "speaker" : "speakerOff", macOn ? "The Mac's sound is recorded: click to turn it off" : "The Mac's sound is off: click to turn it on", () => toggleInput("system"), macOn ? "" : "danger", recording),
      ...studioRange(0, 200, 5, Math.round(audio.system.volume * 100), (value, done) => { audio.system.volume = value / 100; if (done) edited(); }, (v) => v + "%"))));
  if (recording) body.append(h("p", { class: "note", text: "On/off and devices apply to the next recording; volumes apply at export." }));
  box.append(body);
  drawMeter();
}

// The inspector's sections for one placement (DaVinci style): transform, shape, border and effects.
function placementControls(source, item) {
  const id = source.id, canvas = currentCanvas();
  const visible = prow("Visible", studioCheck(item.visible, (value) => changePlacement(id, (p) => ({ ...p, visible: value })), "in this scene"));
  const transform = [visible, transformFields(id, item),
    prow("Size", ...studioRange(4, 200, 1, Math.round(item.box[2] * 100), (value, done) => {
      if (!done) return;
      changePlacement(id, (p) => {
        let width = value / 100, height = p.box[3] * (width / p.box[2]);
        if (height > 2) { width = (width * 2) / height; height = 2; }
        const next = { ...studioClone(p), box: [p.box[0], p.box[1], Math.min(width, 2), height] };
        return next.anchor ? pinPlacement(next, next.anchor) : clampBox(next);
      });
    }, (v) => v + "%")),
    h("div", { class: "btnrow" },
      h("button", { text: "Fit", title: "The whole picture inside the frame", onclick: () => changePlacement(id, (p) => ({ ...p, box: [0, 0, 1, 1], fit: "contain", anchor: null })) }),
      h("button", { text: "Fill", title: "Fill the frame (the edges are cropped)", onclick: () => changePlacement(id, (p) => ({ ...p, box: [0, 0, 1, 1], fit: "cover", anchor: null })) }),
      h("button", { text: "Centre", title: "Centre in the frame", onclick: () => changePlacement(id, (p) => ({ ...p, box: [(1 - p.box[2]) / 2, (1 - p.box[3]) / 2, p.box[2], p.box[3]], anchor: null })) }),
      h("button", { text: "Reset", title: "Back to the default place and look", onclick: () => changePlacement(id, (p) => ({ ...defaultPlacement(source, canvas), visible: p.visible })) })),
    prow("Corner", cornerButtons(item, (anchor) => changePlacement(id, (p) => pinPlacement(p, anchor))),
      item.anchor ? h("button", { class: "ghost", text: "free", title: "Unpin", onclick: () => changePlacement(id, (p) => pinPlacement(p, null)) }) : null)];
  const shape = [];
  if (source.kind !== "screen") shape.push(prow("Shape", shapeButtons(item, (value) => changePlacement(id, (p) => applyShape(p, value, canvas)))));
  shape.push(prow("Fit", studioSelect([["cover", "Fill (crop)"], ["contain", "Whole picture"]], item.fit, (value) => changePlacement(id, (p) => ({ ...p, fit: value })))));
  shape.push(prow("Radius", ...studioRange(0, 50, 1, Math.round(item.radius * 100), (value, done) => { if (done) changePlacement(id, (p) => ({ ...p, radius: value / 100 })); }, (v) => v + "%")));
  if (item.fit === "cover") shape.push(h("p", { class: "note", text: "⌥-drag on the preview moves the picture inside the frame." }));
  const color = h("input", { type: "color", value: item.border.color });
  color.addEventListener("change", () => changePlacement(id, (p) => ({ ...p, border: { ...p.border, color: color.value } })));
  const effects = [
    prow("Border", color, ...studioRange(0, 40, 1, item.border.width, (value, done) => { if (done) changePlacement(id, (p) => ({ ...p, border: { ...p.border, width: value } })); }, (v) => v + " px")),
    prow("Effects", studioCheck(item.shadow, (value) => changePlacement(id, (p) => ({ ...p, shadow: value })), "shadow"),
      studioCheck(item.mirror, (value) => changePlacement(id, (p) => ({ ...p, mirror: value })), "mirror"))];
  return [inspectorSection("Transform", transform), inspectorSection("Shape & crop", shape), inspectorSection("Border & effects", effects)];
}

function renderProps() {
  if (studio.project) { renderProjectProps(); return; }
  const box = $("propsPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const source = sourceById(studio.selected);
  if (!source) { renderSceneInspector(box); return; }
  const devices = studio.devices;
  const recording = Boolean(studio.status.active);
  box.append(h("header", { class: "ihead" }, studioIcon(SOURCE_ICON[source.kind]), h("b", { text: sourceName(source) }), h("span", { class: "hint", text: "Inspector" })));
  const item = placementOf(source.id);
  if (currentCanvas() === "source") box.append(h("p", { class: "note pad", text: "“As recorded” has no layout; pick a format to place sources." }));
  else if (item && item.visible) box.append(...placementControls(source, item));
  else box.append(h("div", { class: "pad" }, h("p", { class: "note", text: "Hidden in this scene." }), h("button", { text: "Show in this scene", onclick: () => toggleVisible(source.id) })));
  const settings = [];
  if (source.kind === "camera") {
    settings.push(prow("Record", studioCheck(source.enabled, (value) => { source.enabled = value; if (value) ensureCamera(); else stopStream("camStream"); edited(renderSources, drawStage, renderProps, updateRecordControls); }, "the camera")));
    const cams = [["default", "Default camera"], ...(devices ? devices.cameras.map((name) => [name, name]) : [])];
    if (!cams.some(([value]) => value === source.device)) cams.push([source.device, source.device]);
    const device = studioSelect(cams, source.device, (value) => { source.device = value; source.mode = "auto"; if (studio.camStream) { stopStream("camStream"); toggleCamera(); } edited(renderProps); });
    device.disabled = recording;
    settings.push(prow("Device", device));
    const name = source.device === "default" ? (devices && devices.cameras[0]) || "" : source.device;
    const modes = [["auto", "Best (auto)"], ...(studio.modes[name] || []).map((mode) => [mode.width + "x" + mode.height + "@" + mode.max_fps, mode.width + "×" + mode.height + " · " + Math.round(Number(mode.max_fps)) + " fps"])];
    if (!modes.some(([value]) => value === source.mode)) modes.push([source.mode, source.mode]);
    const mode = studioSelect(modes, source.mode, (value) => { source.mode = value; edited(); });
    mode.disabled = recording;
    settings.push(prow("Mode", mode, iconButton("refresh", "Read the camera's modes (the camera light turns on for a moment)", () => loadCameraModes(name), "", recording || !name)));
    const quality = studioSelect([["max", "Max · 1080p · ~90 MB/min"], ["high", "High · 1080p · ~45 MB/min"], ["light", "Light · 720p · ~22 MB/min"]], source.quality, (value) => { source.quality = value; edited(updateRecordControls); });
    quality.disabled = recording;
    settings.push(prow("File", quality));
    settings.push(prow("Preview", studioCheck(localStorage.getItem("studio-campreview") !== "off", (value) => { localStorage.setItem("studio-campreview", value ? "on" : "off"); if (value) ensureCamera(); else { stopStream("camStream"); drawStage(); } }, "live camera in this page")));
  } else if (source.kind === "screen") {
    const displays = devices ? devices.displays.map((entry) => [String(entry.number), entry.number + " · " + entry.name + " " + entry.pixels.replace(/\s*x\s*/, "×")]) : [[String(source.display), String(source.display)]];
    const display = studioSelect(displays, String(source.display), (value) => { source.display = Number(value); studio.screenUrl = ""; edited(drawStage, updateRecordControls, startPreview); });
    display.disabled = recording;
    settings.push(prow("Display", display));
    const area = h("input", { type: "text", value: source.area || "", placeholder: "Whole display, or X,Y,W,H in points" });
    area.disabled = recording;
    area.addEventListener("change", () => {
      const value = area.value.replace(/\s+/g, "");
      if (value && !/^\d{1,5},\d{1,5},[1-9]\d{0,4},[1-9]\d{0,4}$/.test(value)) { toast("Area is X,Y,WIDTH,HEIGHT in points, e.g. 0,0,1280,720"); area.value = source.area || ""; return; }
      source.area = value || null;
      edited();
    });
    settings.push(prow("Area", area));
    settings.push(prow("Show", studioCheck(source.clicks, (value) => { source.clicks = value; edited(); }, "clicks")));
    settings.push(prow("Preview", h("button", { text: studio.screenStream ? "Stop live screen" : "Live screen", onclick: toggleLiveScreen })));
  } else if (source.kind === "text") {
    const text = h("input", { type: "text", value: source.text, maxlength: "500" });
    const font = studioSelect(TEXT_FONTS.some(([value]) => value === source.font) ? TEXT_FONTS : [...TEXT_FONTS, [source.font, source.font]], source.font, () => {});
    const size = h("input", { type: "number", min: "8", max: "400", value: String(source.size) });
    const color = h("input", { type: "color", value: source.color });
    const back = h("input", { type: "color", value: source.background || "#000000" });
    const backOn = studioCheck(Boolean(source.background), () => {});
    settings.push(prow("Text", text), prow("Font", font), prow("Size", size), prow("Colours", color, backOn, back));
    settings.push(prow("", h("button", { class: "primary", text: "Apply", onclick: async () => {
      const value = text.value.trim(), points = Number(size.value);
      if (!value) { toast("The text is empty"); return; }
      if (!Number.isInteger(points) || points < 8 || points > 400) { toast("Size is 8-400"); return; }
      const next = { ...source, text: value.slice(0, 500), font: font.value, size: points, color: color.value, background: backOn.checked ? back.value : null };
      const drawn = await renderTextAsset(next);
      if (!drawn) return;
      Object.assign(source, next, { asset: drawn.asset });
      edited(renderSources, drawStage, renderProps);
    } })));
  } else {
    settings.push(prow("File", h("span", { class: "name", text: source.asset })));
  }
  if (source.kind === "image" || source.kind === "text") {
    settings.push(prow("Use", studioCheck(source.enabled, (value) => { source.enabled = value; edited(renderSources, drawStage); }, "in recordings"), h("button", { class: "ghost", text: "Remove", onclick: () => removeSource(source.id) })));
  }
  box.append(inspectorSection(source.kind === "camera" ? "Camera" : source.kind === "screen" ? "Screen" : source.kind === "text" ? "Text" : "Image", settings));
}

// ---- Record tab, OBS style: icons, menus, docks, inspector, live screen, undo ----
// Icons are SVG strokes (24x24) drawn with currentColor, never emoji (they render in colour and differ per Mac).
const STUDIO_ICON = {
  layout: "M3 4h18v16H3zM3 14h18M15 4v10",
  eye: "M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  eyeOff: "M3 3l18 18M10.6 5.1A10.8 10.8 0 0 1 12 5c7 0 11 7 11 7a18 18 0 0 1-3.2 4M6.6 6.6C3.4 8.7 1 12 1 12s4 7 11 7a10.6 10.6 0 0 0 5.4-1.5M9.9 9.9a3 3 0 0 0 4.2 4.2",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
  unlock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 7.8-1.2",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  up: "M12 19V5M5 12l7-7 7 7",
  down: "M12 5v14M19 12l-7 7-7-7",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  pencil: "M17 3l4 4L8 20H4v-4z",
  screen: "M3 4h18v12H3zM8 20h8M12 16v4",
  camera: "M3 7h12v10H3zM15 10l6-3v10l-6-3",
  image: "M3 4h18v16H3zM8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM21 15l-5-5L5 20",
  text: "M4 7V4h16v3M9 20h6M12 4v16",
  mic: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v3",
  micOff: "M3 3l18 18M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V5a3 3 0 0 0-5.9-.6M17 16.9A7 7 0 0 1 5 12v-2M19 10v2c0 .8-.1 1.5-.4 2.2M12 19v3",
  speaker: "M11 5L6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14",
  speakerOff: "M11 5L6 9H2v6h4l5 4zM23 9l-6 6M17 9l6 6",
  scene: "M12 2l10 5-10 5L2 7zM2 17l10 5 10-5M2 12l10 5 10-5",
  undo: "M9 14L4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3",
  play: "M7 4l13 8-13 8z",
  pause: "M8 5v14M16 5v14",
  flag: "M5 21V4h12l-2 4 2 4H5",
  alert: "M12 3l10 18H2zM12 10v5M12 18h.01",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5",
  chevron: "M6 9l6 6 6-6",
  back: "M15 18l-6-6 6-6",
  shot: "M4 8h3l2-3h6l2 3h3v11H4zM12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  "top-left": "M4 4h16v16H4zM8 8h4M8 8v4",
  "top-right": "M4 4h16v16H4zM16 8h-4M16 8v4",
  "bottom-left": "M4 4h16v16H4zM8 16h4M8 16v-4",
  "bottom-right": "M4 4h16v16H4zM16 16h-4M16 16v-4",
};
const SOURCE_ICON = { screen: "screen", camera: "camera", image: "image", text: "text" };
const CANVAS_PIXELS = { "16:9": [1920, 1080], "9:16": [1080, 1920], "1:1": [1080, 1080], "4:5": [1080, 1350] };
const STAGE_HANDLES = ["top-left", "top", "top-right", "right", "bottom-right", "bottom", "bottom-left", "left"];

function studioIcon(name) {
  const svg = svgIcon(STUDIO_ICON[name] || "");
  svg.setAttribute("class", "ico");
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

function iconButton(name, title, onclick, extra, disabled) {
  return h("button", { class: "ib" + (extra ? " " + extra : ""), title, "aria-label": title, disabled: disabled || null, onclick }, studioIcon(name));
}

// ---- menus: one at a time, closed by Esc, a click outside or a choice ----
function closeStudioMenu() {
  if (studio.menu) { studio.menu.remove(); studio.menu = null; }
}

function showMenu(left, top, items) {
  closeStudioMenu();
  const menu = h("div", { class: "stmenu" }, items);
  Object.assign(menu.style, { position: "fixed", left: left + "px", top: top + "px" });
  document.body.append(menu);
  studio.menu = menu;
  if (menu.getBoundingClientRect && typeof window.innerWidth === "number") {
    const box = menu.getBoundingClientRect();
    if (box.right > window.innerWidth - 6) menu.style.left = Math.max(6, window.innerWidth - box.width - 6) + "px";
    if (box.bottom > window.innerHeight - 6) menu.style.top = Math.max(6, window.innerHeight - box.height - 6) + "px";
  }
  setTimeout(() => {
    const away = (event) => {
      if (studio.menu !== menu) { document.removeEventListener("pointerdown", away); return; }
      if (!menu.contains(event.target)) { closeStudioMenu(); document.removeEventListener("pointerdown", away); }
    };
    document.addEventListener("pointerdown", away);
  }, 0);
  return menu;
}

// items: [label, action, disabled] or "-" for a separator.
function contextMenu(event, items) {
  event.preventDefault();
  event.stopPropagation();
  showMenu(event.clientX, event.clientY, items.filter(Boolean).map((item) => item === "-" ? h("hr") :
    h("button", { text: item[0], disabled: item[2] || null, onclick: () => { closeStudioMenu(); item[1](); } })));
}

// ---- scenes ----
function moveScene(id, step) {
  const scenes = studio.setup.scenes, at = scenes.findIndex((item) => item.id === id), to = at + step;
  if (at < 0 || to < 0 || to >= scenes.length) return;
  scenes.splice(to, 0, scenes.splice(at, 1)[0]);
  edited(renderScenes);
}

function removeScene(id) {
  const setup = studio.setup, scene = setup.scenes.find((item) => item.id === id);
  if (!scene) return;
  if (studio.status.active) { toast("Scenes cannot be removed while recording"); return; }
  if (setup.scenes.length < 2) { toast("The last scene stays"); return; }
  setup.scenes = setup.scenes.filter((item) => item.id !== id);
  for (const layouts of Object.values(setup.layouts)) delete layouts[id];
  if (setup.scene === id) setup.scene = setup.scenes[0].id;
  edited(renderScenes, renderSources, drawStage, renderProps);
  toast("Removed the scene “" + scene.name + "” (⌘Z brings it back)");
}

function sceneMenu(event, id) {
  const setup = studio.setup, at = setup.scenes.findIndex((item) => item.id === id), scene = setup.scenes[at];
  if (!scene) return;
  contextMenu(event, [
    ["Switch to this scene", () => selectScene(id), id === currentScene()],
    ["Rename", () => { if (id !== currentScene()) selectScene(id); setTimeout(() => renameScene(id), 0); }],
    ["Duplicate", () => addScene(id, scene.name + " copy"), setup.scenes.length >= 9],
    "-",
    ["Move up", () => moveScene(id, -1), at === 0],
    ["Move down", () => moveScene(id, 1), at === setup.scenes.length - 1],
    "-",
    ["Remove", () => removeScene(id), setup.scenes.length < 2 || Boolean(studio.status.active)],
  ]);
}

// ---- sources ----
function lockedIds() {
  try { return new Set(JSON.parse(localStorage.getItem("studio-locked") || "[]")); } catch (error) { return new Set(); }
}
function isLocked(id) { return lockedIds().has(id); }
function toggleLock(id) {
  const ids = lockedIds();
  if (ids.has(id)) ids.delete(id); else ids.add(id);
  localStorage.setItem("studio-locked", JSON.stringify([...ids]));
  renderSources();
  drawStage();
}

// The sources list is the z order (later = in front), in every scene, like the export.
function moveSource(id, step, to) {
  const sources = studio.setup.sources, at = sources.findIndex((item) => item.id === id);
  const target = to === undefined ? at + step : to;
  if (at < 0 || target < 0 || target >= sources.length || target === at) return;
  sources.splice(target, 0, sources.splice(at, 1)[0]);
  edited(renderSources, drawStage);
}

function deleteSelected() {
  const source = sourceById(studio.selected);
  if (!source) return;
  if (source.kind === "image" || source.kind === "text") { removeSource(source.id); return; }
  const item = placementOf(source.id);
  if (item && item.visible) { toggleVisible(source.id); toast(sourceName(source) + " is hidden in this scene (the screen and the camera stay in the list)"); }
}

function sourceMenu(event, id) {
  const source = sourceById(id);
  if (!source) return;
  const item = placementOf(id), last = studio.setup.sources.length - 1, at = studio.setup.sources.indexOf(source);
  const place = (change) => () => changePlacement(id, change);
  const removable = source.kind === "image" || source.kind === "text";
  contextMenu(event, [
    [item && item.visible ? "Hide in this scene" : "Show in this scene", () => toggleVisible(id), currentCanvas() === "source"],
    [isLocked(id) ? "Unlock" : "Lock position", () => toggleLock(id)],
    "-",
    ["Bring to front", () => moveSource(id, 0, last), at === last],
    ["Move forward", () => moveSource(id, 1), at === last],
    ["Move backward", () => moveSource(id, -1), at === 0],
    ["Send to back", () => moveSource(id, 0, 0), at === 0],
    "-",
    ["Fit to the frame", place((p) => ({ ...p, box: [0, 0, 1, 1], fit: "contain", anchor: null })), !item],
    ["Fill the frame", place((p) => ({ ...p, box: [0, 0, 1, 1], fit: "cover", anchor: null })), !item],
    ["Centre", place((p) => ({ ...p, box: [(1 - p.box[2]) / 2, (1 - p.box[3]) / 2, p.box[2], p.box[3]], anchor: null })), !item],
    ["Reset transform", place((p) => ({ ...defaultPlacement(source, currentCanvas()), visible: p.visible })), !item],
    "-",
    source.kind === "camera" ? [source.enabled ? "Turn the camera off" : "Turn the camera on", () => { source.enabled = !source.enabled; if (source.enabled) ensureCamera(); else stopStream("camStream"); edited(renderSources, drawStage, renderProps, updateRecordControls); }, Boolean(studio.status.active)] : null,
    removable ? ["Remove", () => removeSource(id)] : null,
  ]);
}

function focusInspector() {
  const box = $("propsPane");
  if (!box) return;
  if (box.scrollTo) box.scrollTo({ top: 0, behavior: "smooth" });
  box.className = "inspector flash";
  setTimeout(() => { if (box.className === "inspector flash") box.className = "inspector"; }, 600);
}

// ---- stage geometry ----
function stageFrame() {
  return h("div", { class: "stagewrap", id: "stageWrap" }, h("div", { class: "stage", id: "stage" }), h("div", { class: "stageui", id: "stageUi" }));
}

// The preview keeps its pixel numbers (border widths) right when the window changes size.
function watchStageSize() {
  const box = $("stageBox");
  if (!box || typeof ResizeObserver === "undefined") return;
  if (studio.stageObserver) studio.stageObserver.disconnect();
  let last = 0, timer = 0;
  studio.stageObserver = new ResizeObserver(() => {
    const width = box.clientWidth;
    if (Math.abs(width - last) < 2) return;
    last = width;
    clearTimeout(timer);
    timer = setTimeout(() => { if ($("stageBox") === box) drawStage(); }, 80);
  });
  studio.stageObserver.observe(box);
}

function placeNode(node, item) {
  if (!node) return;
  Object.assign(node.style, { left: item.box[0] * 100 + "%", top: item.box[1] * 100 + "%", width: item.box[2] * 100 + "%", height: item.box[3] * 100 + "%" });
}

function selectionBox(source, item) {
  const locked = isLocked(source.id);
  const box = h("div", { class: "selbox" + (locked ? " locked" : ""), id: "selBox", title: locked ? "Locked (unlock it in Sources)" : "" });
  placeNode(box, item);
  if (!locked) {
    for (const where of STAGE_HANDLES) {
      const handle = h("i", { class: "handle hd-" + where });
      handle.addEventListener("pointerdown", (event) => { event.stopPropagation(); startStageDrag(event, source.id, "resize:" + where); });
      box.append(handle);
    }
  }
  return box;
}

// Keep a box inside what the setup file allows ([-1, 1] corners, sizes up to 2) and partly on the canvas.
function clampBox(item) {
  const out = studioClone(item);
  let [x, y, width, height] = out.box;
  width = Math.min(2, Math.max(MIN_BOX, width));
  height = Math.min(2, Math.max(MIN_BOX, height));
  x = Math.min(Math.min(1, 1 - 0.02), Math.max(Math.max(-1, 0.02 - width), x));
  y = Math.min(Math.min(1, 1 - 0.02), Math.max(Math.max(-1, 0.02 - height), y));
  out.box = [x, y, width, height];
  return out;
}

// Resize from an edge handle: only that side moves; a pinned corner is let go.
function resizeEdge(item, edge, dx, dy) {
  const out = studioClone(item);
  let [x, y, width, height] = out.box;
  if (edge === "right") width = Math.max(MIN_BOX, width + dx);
  else if (edge === "left") { const next = Math.max(MIN_BOX, width - dx); x += width - next; width = next; }
  else if (edge === "bottom") height = Math.max(MIN_BOX, height + dy);
  else if (edge === "top") { const next = Math.max(MIN_BOX, height - dy); y += height - next; height = next; }
  out.box = [x, y, width, height];
  out.anchor = null;
  return out;
}

function nudgeSelected(dx, dy) {
  const layout = currentLayout(), id = studio.selected;
  if (!layout || !layout.placements[id] || !layout.placements[id].visible || isLocked(id) || currentCanvas() === "source") return false;
  const [width, height] = CANVAS_PIXELS[currentCanvas()];
  const item = layout.placements[id];
  layout.placements[id] = clampBox({ ...studioClone(item), box: [item.box[0] + dx / width, item.box[1] + dy / height, item.box[2], item.box[3]], anchor: null });
  edited(drawStage, renderProps);
  return true;
}

// ---- inspector ----
function inspectorSection(title, nodes) {
  const open = localStorage.getItem("studio-closed-" + title) !== "1";
  const section = h("details", { class: "isec", open: open || null }, h("summary", { text: title }), ...nodes.filter(Boolean));
  section.addEventListener("toggle", () => localStorage.setItem("studio-closed-" + title, section.open ? "0" : "1"));
  return section;
}

// X, Y, W, H in pixels of a 1080p canvas, typed like in DaVinci's inspector.
function transformFields(id, item) {
  const [width, height] = CANVAS_PIXELS[currentCanvas()] || [1920, 1080];
  const field = (label, value, apply) => {
    const input = h("input", { type: "number", step: "1", value: String(Math.round(value)), title: label + " in pixels of a " + width + "×" + height + " frame" });
    input.addEventListener("change", () => {
      const number = Number(input.value);
      if (!Number.isFinite(number)) return;
      changePlacement(id, (p) => clampBox(apply(studioClone(p), number)));
    });
    input.addEventListener("keydown", (event) => { if (event.key === "Enter" && input.blur) input.blur(); });
    return h("label", {}, h("span", { text: label }), input);
  };
  const sized = (p, box) => { const next = { ...p, box }; return next.anchor ? pinPlacement(next, next.anchor) : next; };
  return h("div", { class: "xywh" },
    field("X", item.box[0] * width, (p, v) => ({ ...p, box: [v / width, p.box[1], p.box[2], p.box[3]], anchor: null })),
    field("Y", item.box[1] * height, (p, v) => ({ ...p, box: [p.box[0], v / height, p.box[2], p.box[3]], anchor: null })),
    field("W", item.box[2] * width, (p, v) => sized(p, [p.box[0], p.box[1], Math.max(MIN_BOX, v / width), p.box[3]])),
    field("H", item.box[3] * height, (p, v) => sized(p, [p.box[0], p.box[1], p.box[2], Math.max(MIN_BOX, v / height)])));
}

// Nothing selected: the scene itself (name, background) and how to start.
function renderSceneInspector(box) {
  const scene = studio.setup.scenes.find((item) => item.id === currentScene());
  box.append(h("header", { class: "ihead" }, studioIcon("scene"), h("b", { text: scene ? scene.name : "Scene" }), h("span", { class: "hint", text: "Inspector" })));
  const layout = currentLayout();
  const nodes = [];
  if (scene) {
    const name = h("input", { type: "text", value: scene.name, maxlength: "40" });
    name.addEventListener("change", () => { const value = name.value.trim().slice(0, 40); if (value) { scene.name = value; edited(renderScenes, renderProps); } else name.value = scene.name; });
    nodes.push(prow("Name", name));
  }
  if (layout) {
    const background = layout.background;
    const kind = studioSelect([["color", "Colour"], ["blur", "Blurred screen"]], background.kind, (value) => {
      layout.background = value === "blur" ? { kind: "blur" } : { kind: "color", color: background.color || "#000000" };
      edited(drawStage, renderProps);
    });
    const color = background.kind === "color" ? h("input", { type: "color", value: background.color }) : null;
    if (color) color.addEventListener("change", () => { layout.background = { kind: "color", color: color.value }; edited(drawStage); });
    nodes.push(prow("Background", kind, color));
    nodes.push(h("p", { class: "note", text: "The background fills what the sources leave free in " + currentCanvas() + "." }));
  } else nodes.push(h("p", { class: "note", text: "“As recorded” is the screen as captured: nothing to lay out." }));
  box.append(inspectorSection("Scene", nodes));
  box.append(inspectorSection("Tips", [h("p", { class: "note", text: "Click a source on the preview or in Sources to edit it. Right-click for its menu. 1-9 switch scenes, R records, P pauses, M marks, ⌘Z undoes." })]));
}

function openRecordSettings(anchor) {
  const box = h("div", { class: "settingsbox", id: "outputPane" });
  openStudioMenu(anchor, [box]);
  renderOutput(box);
}

// ---- audio inputs ----
function toggleInput(kind) {
  if (studio.status.active || studio.starting) { toast("This applies to the next recording; the running one keeps its inputs"); return; }
  const input = studio.setup.audio[kind];
  input.enabled = !input.enabled;
  if (kind === "mic" && !input.enabled) stopStream("micStream");
  edited(renderSound, updateRecordControls);
  if (kind === "mic" && input.enabled) autoMeter();
}

// The level meter starts by itself once the browser may use the microphone; before that it waits for a click.
async function autoMeter() {
  if (studio.micStream || !studio.setup || !studio.setup.audio.mic.enabled || !navigator.permissions || !navigator.mediaDevices) return;
  try {
    const answer = await navigator.permissions.query({ name: "microphone" });
    if (answer.state === "granted" && state.view === "studio" && studio.tab === "record" && !studio.micStream && studio.setup.audio.mic.enabled) toggleMeter();
  } catch (error) { /* this browser cannot say; the "Show level" button stays */ }
}

// ---- live screen ----
function streamVideo(key, stream) {
  if (!studio[key]) { studio[key] = h("video", { autoplay: true, playsinline: true }); studio[key].muted = true; }
  const video = studio[key];
  if (video.srcObject !== stream) video.srcObject = stream;
  const playing = video.play && video.play();
  if (playing && playing.catch) playing.catch(() => {});
  return video;
}

function renderPreviewBar() {
  const box = $("pvBar");
  if (!box) return;
  box.textContent = "";
  const live = Boolean(studio.screenStream);
  box.append(h("button", { class: "live" + (live ? " on" : ""), id: "liveBtn", onclick: toggleLiveScreen,
    title: live ? "Back to snapshots every 2 s" : "Show the screen live, 30 fps (the browser asks which screen; only this preview uses it, the recording does not)" },
    h("i"), live ? "Live" : "Live screen"), h("span", { class: "sthint", id: "stageHint" }));
}

async function toggleLiveScreen() {
  if (studio.screenStream) { stopStream("screenStream"); renderPreviewBar(); drawStage(); startPreview(); renderProps(); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) { toast("This browser cannot show the screen live; snapshots are used"); return; }
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 30, max: 60 }, displaySurface: "monitor" }, audio: false });
  } catch (error) {
    if (error && error.name !== "NotAllowedError" && error.name !== "AbortError") toast("The browser could not share the screen: " + error.message);
    return;
  }
  if (state.view !== "studio" || studio.tab !== "record") { stream.getTracks().forEach((track) => track.stop()); return; }
  stopStream("screenStream");
  studio.screenStream = stream;
  clearTimeout(studio.previewTimer);
  const track = stream.getVideoTracks()[0];
  if (track) track.onended = () => { if (studio.screenStream !== stream) return; studio.screenStream = null; renderPreviewBar(); drawStage(); startPreview(); };
  renderPreviewBar();
  drawStage();
  renderProps();
}

// ---- undo: snapshots of the setup (or the open project) before each edit ----
function rememberEdit() {
  const doc = studioDoc();
  if (!doc) return;
  const now = JSON.stringify(doc);
  if (studio.historyDoc !== doc) { studio.historyDoc = doc; studio.undo = []; studio.redo = []; studio.historyLast = now; return; }
  if (studio.historyLast && studio.historyLast !== now) {
    studio.undo.push(studio.historyLast);
    if (studio.undo.length > 100) studio.undo.shift();
    studio.redo = [];
  }
  studio.historyLast = now;
}

// Called whenever a setup or project is loaded, so the first edit can be undone.
function startHistory(doc) {
  studio.historyDoc = doc;
  studio.undo = [];
  studio.redo = [];
  studio.historyLast = doc ? JSON.stringify(doc) : "";
}

function undoEdit(redo) {
  const doc = studioDoc();
  if (!doc || studio.historyDoc !== doc) { toast(redo ? "Nothing to redo" : "Nothing to undo"); return; }
  const from = redo ? studio.redo : studio.undo, to = redo ? studio.undo : studio.redo;
  if (!from.length) { toast(redo ? "Nothing to redo" : "Nothing to undo"); return; }
  to.push(JSON.stringify(doc));
  const previous = JSON.parse(from.pop());
  for (const key of Object.keys(doc)) delete doc[key];
  Object.assign(doc, previous);
  studio.historyLast = JSON.stringify(doc);
  if (studio.selected && !sourceById(studio.selected)) studio.selected = null;
  if (studio.project && studio.tab === "edit") { saveProjectSoon(); ed.sel = new Set(); renderEdit(); return; }
  if (studio.project) { saveProjectSoon(); drawStage(); renderProps(); return; }
  saveSetupSoon();
  renderStudioBody();
}

async function loadCameraModes(name) {
  toast("Reading the modes of " + name + "…");
  const { status, data } = await api("GET", "/api/studio/camera-modes?device=" + encodeURIComponent(name));
  if (status !== 200) { toast(data.error || "Could not read the camera modes"); return; }
  Object.assign(studio.modes, data.modes || {});
  renderProps();
}

function renderOutput(target) {
  const box = target || $("outputPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const camera = cameraSource(), mic = studio.setup.audio.mic;
  box.append(h("h5", { text: "Recording" }));
  if (camera) box.append(prow("Camera", studioSelect([["max", "Max · 1080p · ~90 MB/min"], ["high", "High · 1080p · ~45 MB/min"], ["light", "Light · 720p · ~22 MB/min"]], camera.quality, (value) => { camera.quality = value; edited(renderOutput, updateRecordControls); })));
  box.append(prow("Microphone", studioSelect([["flac", "FLAC lossless · ~3 MB/min"], ["wav", "WAV lossless · ~6 MB/min"], ["m4a", "M4A (AAC) · ~2 MB/min"]], mic.format, (value) => { mic.format = value; edited(renderOutput, updateRecordControls); })));
  box.append(prow("Countdown", studioSelect([["0", "None"], ["3", "3 seconds"], ["5", "5 seconds"], ["10", "10 seconds"]], String(studio.setup.countdown), (value) => { studio.setup.countdown = Number(value); edited(); })));
  box.append(prow("Menu bar", studioCheck(studio.setup.menubar, (value) => { studio.setup.menubar = value; edited(); }, "clock while recording")));
  box.append(h("p", { class: "note", text: "This setup ≈ " + megabytesPerMinute(studio.setup) + " MB per minute (the screen alone is ~25-70 MB/min, depending on what moves). Export chooses the format, size and fps." }));
}

const ICONS = { audio: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" };
function sizeText(bytes) { return bytes > 1e9 ? (bytes / 1e9).toFixed(1) + " GB" : bytes > 1e6 ? (bytes / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1e3)) + " KB"; }

async function takeShot(kind) {
  const screen = screenSource();
  const body = { kind, display: screen ? screen.display : 1, delay: studio.delay, clipboard: studio.clipboard };
  if (kind !== "screen") toast("Select on the Mac: drag an area or click a window (Esc cancels)");
  else if (studio.delay) toast("Screenshot in " + studio.delay + " s");
  const { status, data } = await api("POST", "/api/studio/shot", body);
  if (status !== 200) { toast(data.error || "Screenshot failed"); return; }
  if (data.clipboard) { toast("Copied to the clipboard"); return; }
  toast("Saved " + data.saved.split("/").pop());
  studio.libraryLoaded = false;
}

// ---- projects tab ----
const projectMedia = (path, file) => "/media/project?t=" + encodeURIComponent(TOKEN) + "&path=" + encodeURIComponent(path) + "&file=" + encodeURIComponent(file);
const PROJECT_TRACKS = ["screen", "camera", "mic"];

// Global project time -> the segment file that plays it and the time inside that segment.
function projectClock(project, t) {
  const segments = project.segments || [];
  if (!segments.length) return { segment: -1, local: 0 };
  const at = Math.max(0, t);
  let start = 0;
  for (let index = 0; index < segments.length; index++) {
    const length = segments[index].duration;
    if (at < start + length || index === segments.length - 1) return { segment: index, local: Math.min(length, Math.max(0, at - start)) };
    start += length;
  }
  return { segment: -1, local: 0 };
}

function segmentStart(project, index) {
  let start = 0;
  for (let i = 0; i < index; i++) start += project.segments[i].duration;
  return start;
}

// The scene shown at a moment: the last scene event at or before it (marks change nothing).
function sceneAt(project, t) {
  let scene = project.scenes && project.scenes.length ? project.scenes[0].id : "screen";
  let first = true;
  for (const event of project.events || []) {
    if (!event.scene) continue;
    if (first || event.t <= t + 1e-9) scene = event.scene;
    first = false;
    if (event.t > t + 1e-9) break;
  }
  return scene;
}

function sceneName(id) {
  const doc = studioDoc();
  const scene = doc && doc.scenes.find((item) => item.id === id);
  return scene ? scene.name : id;
}

// What a project shows in a scene, like capture_project.effective_placements: sources that were not recorded
// are skipped, and a scene left with only the screen uses the `screen` scene's layout.
function projectPlacements(project, scene, canvas) {
  const tracks = new Set();
  for (const segment of project.segments) for (const track of Object.keys(segment.files || {})) tracks.add(track);
  const available = new Set(project.sources.filter((source) => source.enabled && (source.kind === "image" || source.kind === "text" || tracks.has(source.kind))).map((source) => source.id));
  const layouts = project.layouts[canvas] || {};
  const pick = (name) => {
    const layout = layouts[name];
    if (!layout) return [{ kind: "color", color: "#000000" }, [], false];
    const chosen = [];
    let dropped = false;
    for (const source of project.sources) {
      const item = layout.placements[source.id];
      if (!item || !item.visible) continue;
      if (available.has(source.id)) chosen.push([source, item]);
      else dropped = true;
    }
    return [layout.background, chosen, dropped];
  };
  let [background, chosen, dropped] = pick(scene);
  const onlyScreen = chosen.length === 1 && chosen[0][0].id === "screen";
  if (scene !== "screen" && (!chosen.length || (onlyScreen && dropped)) && layouts.screen) [background, chosen] = pick("screen");
  return [background, chosen];
}

// ---- project player: the screen video is the clock; camera and microphone follow their `starts` ----
function makePlayer() {
  const screen = h("video", { playsinline: true, preload: "auto" });
  const camera = h("video", { playsinline: true, preload: "auto" });
  camera.muted = true;
  const mic = h("audio", { preload: "auto" });
  return { screen, camera, mic, segment: -1, t: 0, playing: false, timer: 0 };
}

function stopProjectPlayer() {
  const player = studio.player;
  if (!player) return;
  clearInterval(player.timer);
  for (const track of PROJECT_TRACKS) {
    const node = player[track];
    if (node.pause) node.pause();
    if (node.removeAttribute) node.removeAttribute("src");
  }
  studio.player = null;
}

// The microphone is the clock when there is one: a browser that cannot decode a big screen video in time
// then only drops frames, while moving the voice to follow the video made it stutter.
const CLOCK_ORDER = ["mic", "screen", "camera"];
function clockTrack(segment) { return CLOCK_ORDER.find((track) => segment.files && segment.files[track]) || null; }
// Keep a follower in time with the clock: a small lag is caught up by playing a little faster or slower,
// only a big one moves it (a jump is heard and seen).
function follow(node, wanted) {
  const drift = wanted - node.currentTime;
  if (Math.abs(drift) > 0.6) { node.currentTime = wanted; node.playbackRate = 1; return; }
  node.playbackRate = Math.abs(drift) < 0.04 ? 1 : 1 + Math.max(-0.12, Math.min(0.12, drift * 0.5));
}
function playMedia(node) { const playing = node.play && node.play(); if (playing && playing.catch) playing.catch(() => {}); }
function setMediaTime(node, value) {
  if (node.readyState >= 1) node.currentTime = value;
  else node.addEventListener("loadedmetadata", () => { node.currentTime = value; }, { once: true });
}

function seekProject(t) {
  const project = studio.project, player = studio.player;
  if (!project || !player) return;
  const { segment, local } = projectClock(project, t);
  if (segment < 0) return;
  const before = currentScene();
  const part = project.segments[segment], starts = part.starts || {};
  if (segment !== player.segment) {
    player.segment = segment;
    for (const track of PROJECT_TRACKS) {
      const file = part.files && part.files[track];
      if (file) player[track].src = projectMedia(project.path, file);
      else { if (player[track].pause) player[track].pause(); if (player[track].removeAttribute) player[track].removeAttribute("src"); }
    }
  }
  player.t = segmentStart(project, segment) + local;
  for (const track of PROJECT_TRACKS) if (part.files && part.files[track]) setMediaTime(player[track], Math.max(0, local - (starts[track] || 0)));
  resumePlayer();
  drawPlayerClock();
  if (currentScene() !== before) { drawStage(); renderProjectProps(); }
}

function resumePlayer() {
  const player = studio.player;
  if (!player || !player.playing || !studio.project) return;
  const part = studio.project.segments[player.segment];
  if (part) for (const track of PROJECT_TRACKS) if (part.files && part.files[track]) playMedia(player[track]);
}

function toggleProjectPlay() {
  const player = studio.player;
  if (!player) return;
  player.playing = !player.playing;
  if (player.playing) {
    if (player.t >= studio.project.duration - 0.05) seekProject(0);
    resumePlayer();
  } else for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause();
  drawPlayerClock();
}

function syncPlayer() {
  const project = studio.project, player = studio.player;
  if (!project || !player || player.segment < 0) return;
  const part = project.segments[player.segment], clock = clockTrack(part);
  if (!clock) return;
  const starts = part.starts || {};
  const local = (player[clock].currentTime || 0) + (starts[clock] || 0);
  const before = currentScene();
  player.t = segmentStart(project, player.segment) + Math.min(local, part.duration);
  if (player.playing) {
    for (const track of PROJECT_TRACKS) {
      if (track === clock || !part.files[track]) continue;
      const node = player[track], wanted = local - (starts[track] || 0);
      if (wanted < 0) { if (!node.paused) node.pause(); continue; }
      follow(node, wanted);
      if (node.paused && !node.ended) playMedia(node);
    }
    if (player[clock].ended || local >= part.duration - 0.03) {
      if (player.segment + 1 < project.segments.length) seekProject(segmentStart(project, player.segment + 1));
      else { player.playing = false; for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause(); }
    }
  }
  drawPlayerClock();
  if (currentScene() !== before) { drawStage(); renderProjectProps(); }
}

function drawPlayerClock() {
  const player = studio.player, project = studio.project;
  if (!player || !project) return;
  const time = $("projTime"), seek = $("projSeek"), play = $("projPlay");
  if (time) time.textContent = clockText(player.t) + " / " + clockText(project.duration);
  if (seek && document.activeElement !== seek) seek.value = String(player.t);
  if (play) { play.textContent = ""; play.append(studioIcon(player.playing ? "pause" : "play")); }
}

// ---- projects list ----
async function loadLibrary() {
  studio.libraryLoaded = true;
  const { status, data } = await api("GET", "/api/studio/library");
  if (status !== 200) return;
  studio.library = Array.isArray(data) ? data : [];
  if (state.view === "studio" && studio.tab === "projects" && !studio.project) renderProjects();
}

async function loadProjects() {
  studio.projectsLoaded = true;
  const { status, data } = await api("GET", "/api/studio/projects");
  if (status !== 200) { toast(data.error || "Could not list the projects"); return; }
  studio.projects = Array.isArray(data) ? data : [];
  if (state.view === "studio" && studio.tab === "projects" && !studio.project) renderProjects();
}

function exportLabel(path) {
  const found = /\s(16x9|9x16|1x1|4x5|source)(?:\s\d+)?\.(\w+)$/.exec(path);
  return found ? found[1].replace("x", ":") + " " + found[2].toUpperCase() : String(path).split(".").pop().toUpperCase();
}

function renderProjects() {
  const box = $("studioProjects");
  if (!box) return;
  if (studio.project) { renderProjectPage(box); return; }
  box.textContent = "";
  const filters = h("div", { class: "levels", id: "libFilters" }, [["projects", "Projects"], ["exports", "Exports"], ["screenshots", "Screenshots"]].map(([value, label]) =>
    h("button", { class: studio.filter === value ? "on" : "", text: label, onclick: () => { studio.filter = value; localStorage.setItem("studio-filter", value); renderProjects(); } })));
  box.append(h("div", { class: "projbar" }, filters, h("span", { class: "spacer" }),
    h("button", { text: "Open project…", title: "Open a project folder from anywhere (a moved or copied project)", onclick: openProjectDialog }),
    h("button", { class: "ghost", text: "Refresh", onclick: () => { loadProjects(); loadLibrary(); } })));
  const grid = h("div", { class: "library", id: "library" });
  box.append(grid);
  if (studio.filter === "projects") {
    if (!studio.projectsLoaded) loadProjects();
    if (!studio.projects.length) { grid.append(h("div", { class: "empty", text: "No projects yet. Every recording becomes one." })); return; }
    for (const item of studio.projects.slice(0, 200)) grid.append(projectCard(item));
    return;
  }
  if (!studio.libraryLoaded) loadLibrary();
  renderLibrary(grid);
}

function projectCard(item) {
  const pic = h("div", { class: "pic" });
  const video = item.tracks.includes("screen") || item.tracks.includes("camera");
  if (video) pic.append(h("img", { src: media("/media/thumb") + "&path=" + encodeURIComponent(item.path), alt: "", loading: "lazy" }));
  else { const wave = h("canvas", { class: "cardwave", "aria-hidden": "true" }); pic.append(wave); cardWave(wave, item); }
  pic.append(h("span", { class: "kind", text: item.tracks.includes("screen") ? "Screen" : item.tracks.includes("camera") ? "Camera" : "Audio" }));
  pic.append(h("span", { class: "len", text: clockText(item.duration) }));
  if (item.state !== "ready") pic.append(h("span", { class: "state " + item.state, text: item.state, title: (item.problems || []).join("\n") }));
  const formats = item.exports.map(exportLabel);
  const when = new Date(item.created).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const edit = h("span", { class: "quick", role: "button", tabindex: "0", title: "Open in the Edit tab", text: "Edit",
    onclick: (event) => { event.stopPropagation(); openEdit(item.path); } });
  return h("button", { class: "item", title: item.path, onclick: () => openProject(item.path) }, pic,
    h("div", { class: "cap" }, h("b", { text: item.name }), h("span", { text: when + " · " + sizeText(item.size) + " · " + (formats.length ? formats.join(", ") : "not exported") }), edit));
}

// A small sound wave for an audio project's card (read once per page, from the first part's sound).
async function cardWave(canvas, item) {
  studio.cardWaves = studio.cardWaves || {};
  let peaks = studio.cardWaves[item.path];
  if (!peaks) {
    const project = await api("GET", "/api/studio/project?path=" + encodeURIComponent(item.path));
    const files = project.status === 200 ? soundFiles(project.data) : [];
    if (!files.length) return;
    const wave = await api("GET", "/api/studio/project/wave?path=" + encodeURIComponent(item.path) + "&file=" + encodeURIComponent(files[0].file) + "&bars=90");
    if (wave.status !== 200 || !Array.isArray(wave.data.peaks)) return;
    peaks = studio.cardWaves[item.path] = wave.data.peaks;
  }
  const width = canvas.clientWidth || 200, height = canvas.clientHeight || 120, ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const c = canvas.getContext("2d");
  c.scale(ratio, ratio);
  c.fillStyle = (getComputedStyle(document.body).getPropertyValue("--accent") || "#ffc933").trim() || "#ffc933";
  const step = width / peaks.length;
  peaks.forEach((value, i) => { const bar = Math.max(1, value * height * 0.36); c.fillRect(i * step, height / 2 - bar, Math.max(1, step - 1.2), bar * 2); });
}

async function openProjectDialog() {
  const { status, data } = await api("POST", "/api/studio/open-project", {});
  if (status !== 200) { toast(data.error || "Could not open the project"); return; }
  if (data.unavailable) { toast("The folder dialog needs macOS (osascript)"); return; }
  if (!data.path) return;
  studio.projectsLoaded = false;
  await openProject(data.path);
}

// ---- one project: synced preview, timeline, layout edits saved to the project, export ----
async function openProject(path, withExport) {
  const { status, data } = await api("GET", "/api/studio/project?path=" + encodeURIComponent(path));
  if (status !== 200) { toast(data.error || "Could not open the project"); return; }
  if (studio.projectTimer) await flushProject();
  stopProjectPlayer();
  studio.tab = "projects";
  localStorage.setItem("studio-tab", "projects");
  clearTimeout(studio.previewTimer);
  stopStream("camStream");
  stopStream("micStream");
  stopStream("screenStream");
  delete data.warnings;
  studio.project = data;
  startHistory(data);
  studio.projectCanvas = STUDIO_RATIOS[data.export.canvas] ? data.export.canvas : "16:9";
  const shown = projectPlacements(data, sceneAt(data, 0), studio.projectCanvas)[1];
  studio.selected = shown.length ? shown[shown.length - 1][0].id : data.sources[0].id;
  studio.player = makePlayer();
  studio.player.timer = setInterval(syncPlayer, 200);
  if (state.view === "studio") renderStudioBody();
  seekProject(0);
  if (withExport) renderExportDialog(data);
}

async function closeProject() {
  if (studio.projectTimer) await flushProject();
  stopProjectPlayer();
  studio.project = null;
  studio.projectsLoaded = false;
  if (studio.setup) startHistory(studio.setup);
  renderStudioBody();
}

function saveProjectSoon() {
  clearTimeout(studio.projectTimer);
  studio.projectTimer = setTimeout(flushProject, 500);
}

async function flushProject() {
  clearTimeout(studio.projectTimer);
  studio.projectTimer = 0;
  const project = studio.project;
  if (!project) return;
  // Only project.json keys go back; capture keeps what was recorded (segments, exports, ...) from disk.
  const body = {};
  for (const [key, value] of Object.entries(project)) if (!["path", "size", "warnings"].includes(key)) body[key] = value;
  const { status, data } = await api("POST", "/api/studio/project", { path: project.path, project: body });
  if (status !== 200) toast(data.error || "Could not save the project");
}

async function projectAction(action) {
  const project = studio.project;
  if (!project) return;
  if (action === "delete" && !confirm("Move the project “" + project.name + "” to the Trash? Exported videos stay.")) return;
  const { status, data } = await api("POST", "/api/studio/action", { action, path: project.path });
  if (status !== 200) { toast(data.error || "Failed"); return; }
  if (action !== "delete") return;
  toast("Moved to the Trash");
  clearTimeout(studio.projectTimer);
  studio.projectTimer = 0;
  stopProjectPlayer();
  studio.project = null;
  studio.projects = studio.projects.filter((item) => item.path !== project.path);
  if (state.view === "studio") renderStudioBody();
}

function renderProjectPage(box) {
  const project = studio.project;
  box.textContent = "";
  const meta = [clockText(project.duration), project.state, sizeText(project.size || 0)].join(" · ");
  box.append(h("div", { class: "projbar" },
    h("button", { class: "ghost back", onclick: closeProject }, studioIcon("back"), "Projects"),
    h("b", { text: project.name }), h("span", { class: "where", text: meta }), h("span", { class: "spacer" }),
    audioOnly(project) ? null : h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
      h("button", { class: studio.projectCanvas === value ? "on" : "", text: label, onclick: () => { studio.projectCanvas = value; renderProjectPage(box); } }))),
    h("button", { text: "Edit", title: "Cut, subtitles, text and music (Edit tab)", onclick: () => edEnter() }),
    h("button", { class: "primary", text: "Export…", onclick: async () => {
      // Subtitles and texts of an edit are drawn here (PNG) before the export can burn them in.
      if (project.edit && !(await edEnsureAssets())) { toast("Some subtitles or texts could not be drawn; try again"); return; }
      if (studio.projectTimer) await flushProject();
      renderExportDialog(project);
    } }),
    h("button", { text: "Show in Finder", onclick: () => projectAction("reveal") }),
    h("button", { class: "ghost", text: "Move to Trash", onclick: () => projectAction("delete") })));
  if (project.problems.length) box.append(h("div", { class: "warns" }, project.problems.map((problem) => h("div", {}, studioIcon("alert"), h("span", { text: problem })))));
  if (audioOnly(project)) { renderAudioProjectPage(box); return; }
  const seek = h("input", { type: "range", id: "projSeek", min: "0", max: String(project.duration), step: "0.01", value: "0" });
  seek.addEventListener("input", () => seekProject(Number(seek.value)));
  const timeline = h("div", { class: "scenelist" });
  for (const event of project.events) {
    if (!event.scene && !("mark" in event)) continue;
    timeline.append(h("div", { role: "button", tabindex: "0", style: "cursor:pointer", onclick: () => seekProject(event.t) },
      h("span", { class: "t", text: clockText(event.t) }), event.scene ? h("span", { text: sceneName(event.scene) }) : h("span", { class: "markname" }, studioIcon("flag"), event.mark || "mark")));
  }
  const exports = h("div", { class: "scenelist" }, project.exports.length ? project.exports.map((item) => {
    const name = String(item.path).split("/").pop();
    return h("div", { role: "button", tabindex: "0", style: "cursor:pointer", title: "Show in Finder", onclick: () => revealExport(name) }, h("span", { text: name }));
  }) : h("div", { class: "where", text: "Not exported yet." }));
  box.append(h("div", { class: "projpage" },
    h("div", { class: "centre" },
      stageFrame(),
      h("div", { class: "player" }, h("button", { id: "projPlay", title: "Play / pause", "aria-label": "Play / pause", onclick: toggleProjectPlay }, studioIcon("play")), seek, h("span", { class: "where", id: "projTime" })),
      h("div", { class: "sthint", id: "stageHint" })),
    h("div", { class: "right" },
      h("div", { class: "pane" }, h("h5", { text: "Timeline" }), timeline),
      h("div", { class: "pane", id: "propsPane" }),
      h("div", { class: "pane" }, h("h5", { text: "Exports" }), exports))));
  drawStage();
  drawPlayerClock();
  renderProjectProps();
}

// An audio-only project: its sound like Voice Memos, marks, sound settings and exports (no formats, no layout).
function renderAudioProjectPage(box) {
  const project = studio.project;
  const marks = h("div", { class: "scenelist" });
  const marked = project.events.filter((event) => "mark" in event);
  for (const event of marked)
    marks.append(h("div", { role: "button", tabindex: "0", style: "cursor:pointer", onclick: () => { seekProject(event.t); drawAudioView(); } },
      h("span", { class: "t", text: clockText(event.t) }), h("span", { class: "markname" }, studioIcon("flag"), event.mark || "mark")));
  if (!marked.length) marks.append(h("div", { class: "where", text: "No marks. Press M while recording to add one." }));
  const exports = h("div", { class: "scenelist" }, project.exports.length ? project.exports.map((item) => {
    const name = String(item.path).split("/").pop();
    return h("div", { role: "button", tabindex: "0", style: "cursor:pointer", title: "Show in Finder", onclick: () => revealExport(name) }, h("span", { text: name }));
  }) : h("div", { class: "where", text: "Not exported yet." }));
  const mic = project.audio.mic;
  const volume = h("input", { type: "range", min: "0", max: "2", step: "0.05", value: String(mic.volume) });
  volume.addEventListener("change", () => { mic.volume = Number(volume.value); rememberEdit(); saveProjectSoon(); });
  const centre = h("div", { class: "centre" });
  box.append(h("div", { class: "projpage" }, centre,
    h("div", { class: "right" },
      h("div", { class: "pane" }, h("h5", { text: "Marks" }), marks),
      h("div", { class: "pane" }, h("h5", { text: "Sound" }), prow("Volume", volume), h("p", { class: "note", text: "Export makes " + (project.audio_format || "an audio file") + " with loudness evened out. Cut pauses and add subtitles in the Edit tab." })),
      h("div", { class: "pane" }, h("h5", { text: "Exports" }), exports))));
  renderAudioProject(centre);
  drawPlayerClock();
}

function renderProjectProps() {
  const box = $("propsPane");
  if (!box || !studio.project) return;
  box.textContent = "";
  box.append(h("h5", { text: "Layout · " + sceneName(currentScene()) + " · " + currentCanvas() }));
  if (currentCanvas() === "source") { box.append(h("p", { class: "note", text: "“As recorded” is the screen as captured; pick a format to change the layout." })); return; }
  const shown = projectPlacements(studio.project, currentScene(), currentCanvas())[1].map(([source]) => source);
  if (!shown.length) { box.append(h("p", { class: "note", text: "Nothing of this project is visible in this scene." })); return; }
  if (!shown.some((source) => source.id === studio.selected)) studio.selected = shown[shown.length - 1].id;
  box.append(prow("Source", studioSelect(shown.map((source) => [source.id, sourceName(source)]), studio.selected, (value) => { studio.selected = value; drawStage(); renderProjectProps(); })));
  const source = sourceById(studio.selected), item = placementOf(studio.selected);
  if (source && item) box.append(...placementControls(source, item));
  else box.append(h("p", { class: "note", text: "Shown through the Screen scene's layout; edit it while that scene plays." }));
  box.append(h("p", { class: "note", text: "Saved to this project only; the studio setup stays as it is." }));
}

async function revealExport(name) {
  const { status, data } = await api("POST", "/api/studio/action", { action: "reveal", name });
  if (status !== 200) toast(data.error || "Not in the recordings folder");
}

// ---- export dialog ----
const EXPORT_DEFAULTS = { canvas: "16:9", height: 1440, fps: 60, codec: "h264", quality: "high", container: "mov", normalize: true, delete_sources: false };

// Pre-fill: this project's last export, else the last settings used anywhere (setup.export), like capture's export_settings.
function exportDefaults(project, setup) {
  const values = { ...EXPORT_DEFAULTS };
  for (const layer of [(setup && setup.export) || {}, (project && project.export) || {}]) {
    for (const key of Object.keys(EXPORT_DEFAULTS)) if (key in layer) values[key] = layer[key];
  }
  if (project && project.mode === "camera" && !(project.export && "height" in project.export)) values.height = 1080;
  values.delete_sources = false;
  return values;
}

function exportHeightFor(canvas, mode) { return canvas === "16:9" && mode !== "camera" ? 1440 : 1080; }

function renderExportDialog(project) {
  const sheet = $("viewerSheet");
  if (!sheet) return;
  studio.item = null;
  sheet.textContent = "";
  const values = exportDefaults(project, studio.setup);
  const audioOnly = project.mode === "audio";
  const field = (label, control) => h("label", {}, label, control);
  const tick = (label, key) => {
    const input = h("input", { type: "checkbox" });
    input.checked = values[key];
    input.addEventListener("change", () => { values[key] = input.checked; });
    return h("label", { class: "check" }, input, label);
  };
  sheet.append(h("div", { class: "top" }, h("b", { text: "Export " + project.name }), h("button", { class: "ghost", text: "Close", onclick: closeViewer })));
  const form = h("div", { class: "export" });
  if (!audioOnly) {
    const height = studioSelect([["1080", "1080p"], ["1440", "1440p"], ["2160", "2160p (4K)"]], String(values.height), (value) => { values.height = Number(value); });
    height.disabled = values.canvas === "source";
    form.append(
      field("Format", studioSelect(STUDIO_FORMATS, values.canvas, (value) => {
        values.canvas = value;
        values.height = exportHeightFor(value, project.mode);
        height.value = String(values.height);
        height.disabled = value === "source";
      })),
      field("Size (short side)", height),
      field("Frame rate", studioSelect([["60", "60 fps"], ["30", "30 fps"]], String(values.fps), (value) => { values.fps = Number(value); })),
      field("Codec", studioSelect([["h264", "H.264 (plays everywhere)"], ["hevc", "HEVC (smaller files)"]], values.codec, (value) => { values.codec = value; })),
      field("Quality", studioSelect([["high", "High"], ["max", "Max (1.5× bitrate)"]], values.quality, (value) => { values.quality = value; })),
      field("File", studioSelect([["mov", "MOV"], ["mp4", "MP4"]], values.container, (value) => { values.container = value; })));
  }
  form.append(tick("Loudness to −14 LUFS", "normalize"), tick("Delete the recorded tracks after a successful export", "delete_sources"));
  sheet.append(form);
  sheet.append(h("p", { class: "where", text: audioOnly ? "Saved to captures/recordings in the audio format of capture.audio_format." : "Saved to captures/recordings as “" + project.name + " 16x9.mov” (the format in the name), never over another file. 10 minutes of 1440p60 take about 5 minutes; “As recorded” takes seconds." }));
  sheet.append(h("div", { class: "progress" }, h("i", { id: "exportBar" })), h("div", { class: "where", id: "exportState" }));
  sheet.append(h("div", { class: "tools" }, h("button", { class: "primary", text: "Export", onclick: () => startExport(project, values) })));
  $("viewer").classList.add("on");
  if (studio.exportJob && ["queued", "running"].includes(studio.exportJob.phase)) pollExport();
}

async function startExport(project, values) {
  if (values.delete_sources && !confirm("Delete the recorded tracks of “" + project.name + "” after the export? Only the exported file stays.")) return;
  const body = project.mode === "audio"
    ? { path: project.path, normalize: values.normalize, delete_sources: values.delete_sources }
    : { path: project.path, canvas: values.canvas, height: values.height, fps: values.fps, codec: values.codec, quality: values.quality, format: values.container, normalize: values.normalize, delete_sources: values.delete_sources };
  drawExportState({ phase: "queued", percent: 0 });
  const { status, data } = await api("POST", "/api/studio/export", body);
  if (status !== 200) { drawExportState({ phase: "failed", error: data.error || "the export did not start" }); return; }
  await pollExport();
}

// One export runs at a time (capture keeps the queue); the page follows it every second until it ends.
async function pollExport() {
  clearTimeout(studio.exportTimer);
  studio.exportTimer = 0;
  const { status, data } = await api("GET", "/api/studio/export/status");
  if (status !== 200) { drawExportState({ phase: "failed", error: data.error || "no export status" }); return; }
  drawExportState(data);
  if (data.phase === "queued" || data.phase === "running") studio.exportTimer = setTimeout(pollExport, 1000);
  else if (data.phase === "done") { studio.projectsLoaded = false; studio.libraryLoaded = false; }
}

function drawExportState(job) {
  studio.exportJob = job;
  const bar = $("exportBar"), node = $("exportState");
  if (bar) bar.style.width = (job.phase === "done" ? 100 : Math.max(0, Math.min(100, Number(job.percent) || 0))) + "%";
  if (!node) return;
  node.textContent = "";
  const name = String(job.output || "").split("/").pop();
  const left = Number(job.eta) > 90 ? Math.round(job.eta / 60) + " min" : Math.round(Number(job.eta) || 0) + " s";
  if (job.phase === "queued") node.append("Waiting for the export to start…");
  else if (job.phase === "running") node.append("Exporting… " + Math.round(Number(job.percent) || 0) + "%" + (job.eta ? " · about " + left + " left" : ""));
  else if (job.phase === "done") node.append("Saved " + name + " ", h("button", { class: "ghost", text: "Show in Finder", onclick: () => revealExport(name) }));
  else if (job.phase === "failed") node.append("Export failed: " + (job.error || "unknown error"));
}

function renderLibrary(box) {
  box = box || $("library");
  if (!box) return;
  box.textContent = "";
  const kinds = { exports: ["video", "audio"], screenshots: ["image"] }[studio.filter] || ["video", "audio"];
  const items = studio.library.filter((item) => kinds.includes(item.kind));
  if (!items.length) { box.append(h("div", { class: "empty", text: "Nothing here yet." })); return; }
  for (const item of items.slice(0, 120)) {
    const pic = h("div", { class: "pic" });
    if (item.kind === "audio") pic.append(svgIcon(ICONS.audio));
    else pic.append(h("img", { src: media("/media/thumb", item.name), alt: "", loading: "lazy" }));
    if (item.duration) pic.append(h("span", { class: "len", text: format(item.duration) }));
    const when = new Date(item.modified).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    box.append(h("button", { class: "item", title: item.name, onclick: () => openViewer(item) }, pic,
      h("div", { class: "cap" }, h("b", { text: item.name }), h("span", { text: when + " · " + sizeText(item.size) }))));
  }
}

function fitCanvas(canvas) {
  const scale = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * scale) || canvas.height !== Math.round(height * scale)) {
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
  }
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);
  return [context, width, height];
}

function bars(context, x, height, value, width, color) {
  const tall = Math.max(2, value * (height - 8));
  context.fillStyle = color;
  context.beginPath();
  context.roundRect(x, (height - tall) / 2, width, tall, width / 2);
  context.fill();
}

function openViewer(item) {
  studio.item = item;
  studio.trim = { from: null, to: null };
  const sheet = $("viewerSheet");
  sheet.textContent = "";
  const source = media("/media/file", item.name);
  const player = item.kind === "video" ? h("video", { controls: true, src: source, preload: "metadata" }) : item.kind === "audio" ? h("audio", { controls: true, src: source, preload: "metadata" }) : h("img", { src: source, alt: item.name });
  const meta = [item.duration ? format(item.duration) : "", sizeText(item.size), new Date(item.modified).toLocaleString()].filter(Boolean).join(" · ");
  sheet.append(h("div", { class: "top" }, h("b", { text: item.name }), h("span", { class: "where", text: meta }), h("button", { class: "ghost", text: "Close", onclick: closeViewer })));
  sheet.append(h("div", { class: "media" }, player));
  if (item.kind !== "image") {
    const canvas = h("canvas", { class: "filewave", title: "Click to jump there" });
    sheet.append(canvas);
    fileWave(item, player, canvas);
  }
  const act = (action, extra) => async () => {
    const { status, data } = await api("POST", "/api/studio/action", { action, name: item.name, ...(extra || {}) });
    if (status !== 200) { toast(data.error || "Failed"); return null; }
    return data;
  };
  const tools = h("div", { class: "tools" },
    h("button", { text: item.kind === "image" ? "Open in Preview" : "Open in QuickTime", onclick: act("open") }),
    h("button", { text: "Show in Finder", onclick: act("reveal") }),
    item.kind === "image" ? h("button", { text: "Copy", onclick: async () => { if (await act("copy")()) toast("Copied to the clipboard"); } }) : null);
  if (item.kind !== "image") {
    const mark = h("span", { class: "mark", text: "trim: start – end" });
    const show = () => { mark.textContent = "trim: " + (studio.trim.from === null ? "start" : format(studio.trim.from)) + " – " + (studio.trim.to === null ? "end" : format(studio.trim.to)); };
    const convert = studioSelect((item.kind === "video" ? [["mp4", "MP4"], ["mov", "MOV"], ["gif", "GIF"], ["m4a", "Audio M4A"], ["mp3", "Audio MP3"]] : [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"]]).filter(([value]) => !item.name.toLowerCase().endsWith("." + value)), "", () => {});
    tools.append(h("span", { class: "sep" }),
      h("button", { text: "Set start", title: "Trim from the player position", onclick: () => { studio.trim.from = player.currentTime; show(); } }),
      h("button", { text: "Set end", onclick: () => { studio.trim.to = player.currentTime; show(); } }),
      mark,
      h("button", { text: "Save trimmed", onclick: async () => {
        const extra = {};
        if (studio.trim.from !== null) extra.from = studio.trim.from;
        if (studio.trim.to !== null) extra.to = studio.trim.to;
        if (!Object.keys(extra).length) { toast("Set a start or an end first"); return; }
        toast("Trimming…");
        const data = await act("trim", extra)();
        if (data) { toast("Saved " + data.saved.split("/").pop()); loadLibrary(); }
      } }),
      h("span", { class: "sep" }), convert,
      h("button", { text: "Convert", onclick: async () => {
        toast("Converting…");
        const data = await act("convert", { to: convert.value })();
        if (data) { toast("Saved " + data.saved.split("/").pop()); loadLibrary(); }
      } }));
  }
  tools.append(h("span", { class: "spacer", style: "flex:1" }), h("button", { class: "ghost", text: "Move to Trash", onclick: async () => {
    if (!confirm("Move " + item.name + " to the Trash?")) return;
    if (await act("delete")()) { closeViewer(); toast("Moved to the Trash"); loadLibrary(); }
  } }));
  sheet.append(tools);
  $("viewer").classList.add("on");
}

async function fileWave(item, player, canvas) {
  const count = Math.max(60, Math.min(1200, Math.floor((canvas.clientWidth || 900) / 4)));
  const { status, data } = await api("GET", "/api/studio/wave?name=" + encodeURIComponent(item.name) + "&bars=" + count);
  if (status !== 200 || studio.item !== item) { if (status !== 200) canvas.remove(); return; }
  const peaks = data.peaks;
  const total = () => (Number.isFinite(player.duration) && player.duration > 0 ? player.duration : data.duration) || 1;
  canvas.addEventListener("click", (event) => {
    const box = canvas.getBoundingClientRect();
    player.currentTime = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * total();
  });
  let drawn = "";
  const draw = () => {
    if (!canvas.isConnected) return;
    // Redraw only when something visible changed: an open, paused viewer costs nothing.
    const key = [player.currentTime, studio.trim.from, studio.trim.to, canvas.clientWidth, canvas.clientHeight, window.devicePixelRatio].join();
    if (key === drawn) { requestAnimationFrame(draw); return; }
    drawn = key;
    const [context, width, height] = fitCanvas(canvas);
    const step = width / peaks.length, at = player.currentTime / total();
    const from = studio.trim.from === null ? null : studio.trim.from / total();
    const to = studio.trim.to === null ? null : studio.trim.to / total();
    if (from !== null || to !== null) {
      context.fillStyle = "rgba(107,147,255,.16)";
      context.fillRect((from ?? 0) * width, 0, ((to ?? 1) - (from ?? 0)) * width, height);
    }
    peaks.forEach((value, index) => bars(context, index * step + 0.5, height, value, Math.max(1, step - 1.5), index / peaks.length < at ? "#ff453a" : "#8e8e93"));
    context.fillStyle = "#f2f2f7";
    context.fillRect(at * width - 1, 0, 2, height);
    requestAnimationFrame(draw);
  };
  draw();
}

function closeViewer() {
  const viewer = $("viewer");
  if (!viewer.classList.contains("on")) return;
  viewer.classList.remove("on");
  for (const node of viewer.querySelectorAll("video, audio")) node.pause();
  $("viewerSheet").textContent = "";
  studio.item = null;
}
$("viewer").addEventListener("click", (event) => { if (event.target === $("viewer")) closeViewer(); });
$("recPill").addEventListener("click", () => { if (state.view !== "studio") setView("studio"); });
window.addEventListener("resize", () => { if (state.view === "studio" && studio.tab === "record") drawStage(); });

"""

STUDIO_CSS += EDIT_CSS
STUDIO_JS += EDIT_JS

"""The `ul desk` page: one HTML document with inline CSS and JS, served by desk.py.

Board text is user data, so the script builds every node with textContent and never uses innerHTML.
"""


_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Desk</title>
<link rel="icon" id="favicon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%23fff%22/%3E%3Cpath d=%22M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5%22 fill=%22none%22 stroke=%22%23f5a300%22 stroke-width=%227%22/%3E%3C/svg%3E" data-light="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%23fff%22/%3E%3Cpath d=%22M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5%22 fill=%22none%22 stroke=%22%23f5a300%22 stroke-width=%227%22/%3E%3C/svg%3E" data-dark="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230b0b0a%22/%3E%3Cpath d=%22M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5%22 fill=%22none%22 stroke=%22%23f5a300%22 stroke-width=%227%22/%3E%3C/svg%3E">
<style>
:root {
  --bg: #f5f5f7; --panel: #ffffff; --column: #ececee; --sunken: #e3e3e6; --text: #1d1d1f; --muted: #6e6e73;
  --line: #dcdce0; --accent: #e8a530; --accent-ink: #9c5f00; --accent-soft: #fbefd5; --on-accent: #1d1d1f;
  --energy: #ff7a1a; --energy-ink: #c2500a; --danger: #e5484d; --ok: #2f9e5b; --warn: #d97706;
  --shadow: 0 1px 2px rgba(40,30,10,.05), 0 1px 1px rgba(40,30,10,.03);
  --lift: 0 4px 10px rgba(40,30,10,.07), 0 14px 32px rgba(40,30,10,.09);
  --radius: 10px; --r: 7px; --r-sm: 5px;
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  --mono: "SF Mono", ui-monospace, Menlo, monospace;
  color-scheme: light;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #1c1c1e; --panel: #2a2a2d; --column: #232325; --sunken: #313134; --text: #f2f2f4; --muted: #9b9ba1;
  --line: #38383c; --accent: #e9ae45; --accent-ink: #f2c46b; --accent-soft: #3a3122; --on-accent: #1d1d1f;
  --energy: #ff8a33; --energy-ink: #ff9d57; --danger: #ff6b5e; --ok: #4fc581; --warn: #ffb02e;
  --shadow: 0 1px 2px rgba(0,0,0,.45);
  --lift: 0 6px 14px rgba(0,0,0,.5), 0 18px 40px rgba(0,0,0,.4);
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--text); font: 14px/1.45 var(--font); display: flex; flex-direction: column; -webkit-font-smoothing: antialiased; }
::selection { background: var(--accent-soft); }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; border: 1px solid var(--line); background: var(--panel); border-radius: var(--r); padding: 5px 11px; transition: background .14s, border-color .14s, color .14s, box-shadow .14s, transform .14s; }
button:hover { border-color: var(--accent); }
button:disabled { opacity: .45; cursor: default; transform: none; }
/* A tint, not a solid yellow block (the same as Unlaw.app's primary buttons). */
button.primary { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 45%, transparent); color: var(--accent-ink); font-weight: 600; }
button.primary:hover { background: color-mix(in srgb, var(--accent) 26%, var(--panel)); }
button.ghost { border-color: transparent; background: transparent; color: var(--muted); }
button.ghost:hover { background: var(--column); color: var(--text); }
button.icon { width: 32px; height: 32px; padding: 0; display: inline-grid; place-items: center; }
button.icon svg { width: 17px; height: 17px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
input, select { border: 1px solid var(--line); background: var(--panel); border-radius: var(--r); padding: 5px 10px; outline: none; transition: border-color .14s, box-shadow .14s; }
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
input[type=range] { accent-color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent-ink); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; animation: none !important; } }

header { display: flex; align-items: center; gap: 12px; padding: 8px 14px 0 16px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; position: relative; z-index: 5; }
header > :not(.tabs) { margin-bottom: 8px; }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 680; letter-spacing: -.01em; }
.brand .mark { width: 24px; height: 24px; display: block; border-radius: 5px; box-shadow: 0 0 0 1px var(--line); }
:root[data-theme="dark"] .brand .mark.light, :root:not([data-theme="dark"]) .brand .mark.dark { display: none; }
.picker { position: relative; }
.picker .trigger { display: inline-flex; align-items: center; gap: 8px; max-width: 240px; border-color: transparent; background: transparent; font-weight: 600; padding: 4px 8px; }
.picker .trigger:hover, .picker.open .trigger { background: var(--column); }
.picker .trigger .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker .trigger::after { content: ""; flex: none; width: 6px; height: 6px; margin-top: -3px; border: solid var(--muted); border-width: 0 1.6px 1.6px 0; transform: rotate(45deg); transition: transform .16s; }
.picker.open .trigger::after { transform: rotate(225deg); margin-top: 3px; }
.picker .menu { position: absolute; top: calc(100% + 4px); left: 0; min-width: 280px; max-width: 380px; max-height: min(70vh, 520px); overflow-y: auto; display: none; flex-direction: column; gap: 1px; padding: 4px; background: var(--panel); border: 1px solid var(--line); border-radius: 9px; box-shadow: var(--lift); z-index: 40; }
.picker.open .menu { display: flex; }
.picker .menu button { display: flex; flex-direction: column; align-items: flex-start; border: none; background: transparent; border-radius: 5px; padding: 5px 10px; text-align: left; }
.picker .menu button:hover, .picker .menu button:focus-visible { background: var(--column); outline: none; }
.picker .menu button .label { max-width: 100%; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker .menu button .where { max-width: 100%; font-size: 11.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker .menu button.on { box-shadow: inset 2px 0 0 var(--accent); background: var(--column); border-radius: 0 5px 5px 0; }
.picker .menu button.on .label { font-weight: 600; }
.picker .menu button.action { color: var(--muted); }
.picker .menu button.action:hover { color: var(--text); }
.picker .menu button.action.danger:hover { color: var(--danger); }
.picker .menu .sep { height: 1px; background: var(--line); margin: 4px 0; }
.tabs { display: flex; gap: 4px; align-self: stretch; align-items: stretch; }
.tabs button { border: none; background: transparent; padding: 0 10px 8px; border-radius: 0; color: var(--muted); font-weight: 550; box-shadow: inset 0 -2px 0 transparent; }
.tabs button:hover { color: var(--text); }
.tabs button.on { color: var(--text); box-shadow: inset 0 -2px 0 var(--accent); }
.spacer { flex: 1; }
.timer { display: flex; align-items: center; gap: 8px; padding: 3px 3px 3px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); }
.timer .phase { font-size: 12px; color: var(--muted); }
.timer .clock { font: 600 15px var(--mono); min-width: 48px; text-align: right; font-variant-numeric: tabular-nums; }
.timer.work { border-color: color-mix(in srgb, var(--energy) 60%, var(--line)); }
.timer.work .clock { color: var(--energy-ink); }
.timer.short .clock, .timer.long .clock { color: var(--ok); }
.timer .bar { width: 70px; height: 4px; background: var(--sunken); border-radius: 2px; overflow: hidden; }
.timer .bar i { display: block; height: 100%; background: currentColor; width: 0; transition: width .5s linear; }
.timer.work .bar i { background: var(--energy); }
.timer.short .bar i, .timer.long .bar i { background: var(--ok); }
.timer .linked { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--muted); }
.timer button { padding: 2px 10px; border-radius: 5px; }
.timer #play { background: var(--accent-soft); color: var(--accent-ink); border-color: color-mix(in srgb, var(--accent) 45%, transparent); font-weight: 600; }
.actions-bar { display: flex; gap: 2px; }

.toolbar { display: flex; align-items: center; gap: 10px; padding: 12px 16px 0; flex-wrap: wrap; }
.toolbar.hidden { display: none; }
.search { position: relative; }
.search input { width: 240px; padding-left: 31px; background: var(--panel); }
.search svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); width: 15px; height: 15px; stroke: var(--muted); fill: none; stroke-width: 2; }
#filter { display: none; }
#filter.on { display: inline-flex; }
.summary { display: flex; gap: 6px; flex-wrap: wrap; }
.pill { font-size: 12px; padding: 1px 0; color: var(--muted); }
.pill + .pill { padding-left: 10px; border-left: 1px solid var(--line); }
.pill b { color: var(--text); font-weight: 600; }
.pill.late b { color: var(--danger); }
.pill.today b { color: var(--energy-ink); }

main { flex: 1; overflow: auto; }
.board { display: flex; gap: 12px; padding: 14px 16px 16px; align-items: flex-start; min-height: 100%; }
.column { background: var(--column); border-radius: var(--radius); width: 300px; flex: 0 0 300px; display: flex; flex-direction: column; max-height: calc(100vh - 140px); border: 1px solid transparent; }
.column.drop { outline: 2px dashed var(--accent); outline-offset: -2px; background: color-mix(in srgb, var(--accent-soft) 55%, var(--column)); }
.column h2 { font-size: 13px; font-weight: 650; margin: 0; padding: 11px 10px 6px 12px; display: flex; gap: 7px; align-items: center; }
.column h2::before { content: ""; flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.column.doing h2::before { background: var(--energy); }
.column.done h2::before { background: var(--ok); }
.column h2 .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.column h2 .count { color: var(--muted); font-weight: 500; font-size: 12px; font-variant-numeric: tabular-nums; }
.column h2 button { padding: 0; width: 22px; height: 22px; line-height: 1; border: none; background: transparent; color: var(--muted); border-radius: 6px; font-size: 17px; }
.column h2 button:hover { background: var(--panel); color: var(--text); }
.cards { padding: 4px 9px; overflow-y: auto; flex: 1; min-height: 20px; }
.card { background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); padding: 9px 10px; margin-bottom: 7px; display: flex; gap: 9px; align-items: flex-start; cursor: grab; position: relative; border: 1px solid var(--line); transition: border-color .12s; }
.card:hover { border-color: color-mix(in srgb, var(--text) 22%, var(--line)); }
.card.dragging { opacity: .4; }
.column.dragging { opacity: .4; }
.column h2[draggable="true"] { cursor: grab; }
.column.col-before { box-shadow: -3px 0 0 var(--accent-ink); }
.column.col-after { box-shadow: 3px 0 0 var(--accent-ink); }
.card.focus { border-color: var(--energy); box-shadow: inset 2px 0 0 var(--energy); }
.card.checked .text { color: var(--muted); text-decoration: line-through; }
.card .check { width: 18px; height: 18px; border-radius: 50%; border: 1.6px solid color-mix(in srgb, var(--muted) 70%, transparent); flex: 0 0 17px; margin-top: 1px; padding: 0; background: transparent; position: relative; }
.card .check:hover { border-color: var(--accent); background: var(--accent-soft); }
.card.checked .check { background: var(--accent); border-color: var(--accent); }
.card.checked .check::after { content: ""; position: absolute; left: 5.5px; top: 2.5px; width: 4px; height: 8px; border: solid var(--on-accent); border-width: 0 2px 2px 0; transform: rotate(45deg); }
.card .body { flex: 1; min-width: 0; word-wrap: break-word; }
.card .meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
.card .details { margin-top: 4px; color: var(--muted); font-size: 12px; white-space: pre-wrap; }
.card .actions { display: none; gap: 2px; position: absolute; right: 6px; top: 6px; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; box-shadow: var(--shadow); padding: 2px; }
.card:hover .actions { display: flex; }
.card .actions button { padding: 1px 7px; font-size: 12px; border: none; background: transparent; }
.card .actions button:hover { background: var(--column); }
.card .actions button.del svg { width: 13px; height: 13px; display: block; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; }
#filter svg { width: 11px; height: 11px; stroke: currentColor; fill: none; stroke-width: 2.2; stroke-linecap: round; vertical-align: -1px; }
.card input.edit { width: 100%; }
.chip { display: inline-block; font-size: 11px; font-weight: 550; padding: 0 6px; border-radius: 4px; background: var(--accent-soft); color: var(--accent-ink); cursor: pointer; border: none; line-height: 18px; }
.chip.due { background: var(--column); color: var(--muted); cursor: default; }
.chip.today { background: color-mix(in srgb, var(--energy) 15%, transparent); color: var(--energy-ink); }
.chip.late { background: #fde2df; color: #a8291d; }
:root[data-theme="dark"] .chip.late { background: #4d1f1b; color: #ff9d93; }
.link { color: var(--accent-ink); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.add { padding: 6px 9px 11px; }
.add input { width: 100%; background: transparent; border-style: dashed; }
.add input:focus { background: var(--panel); border-style: solid; }
.newcol { flex: 0 0 220px; }
.newcol input { width: 100%; background: transparent; border-style: dashed; padding: 9px 12px; }
.page { max-width: 780px; margin: 0 auto; padding: 22px 16px 60px; }
.page h3 { font-size: 13px; font-weight: 650; color: var(--text); margin: 26px 0 8px; display: flex; align-items: center; gap: 8px; }
.page h3 .n { color: var(--muted); font-weight: 500; }
.page .quick { display: flex; gap: 8px; }
.page .quick input { flex: 1; padding: 9px 12px; }
.page .card { cursor: default; }
.page .where { font-size: 11px; color: var(--muted); }
.empty { color: var(--muted); padding: 8px 2px; }
.numbers { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.today-stats { margin-bottom: 14px; }
.today-stats:empty { display: none; }
.week.mini { height: auto; min-height: 64px; padding: 8px 10px; gap: 4px; }
.week.mini .bars i { width: 6px; }
.number { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px 16px; }
.number b { display: block; font-size: 26px; font-weight: 650; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.number span { color: var(--muted); font-size: 12px; }
.week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; align-items: end; height: 170px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px; }
.day { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 4px; font-size: 11px; color: var(--muted); }
.day .bars { display: flex; gap: 3px; align-items: flex-end; flex: 1; }
.day .bars i { display: block; width: 12px; border-radius: 2px 2px 0 0; min-height: 2px; }
.day .bars i.f { background: var(--energy); }
.day .bars i.d { background: var(--ok); }
.legend { display: flex; gap: 14px; font-size: 12px; color: var(--muted); margin-top: 6px; }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; }
.top { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 6px 14px; }
.top div { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--line); }
.top div:last-child { border-bottom: none; }

.arcade { display: grid; grid-template-columns: 272px 1fr; gap: 14px; padding: 14px 16px 16px; height: 100%; min-height: 460px; }
.side { display: flex; flex-direction: column; gap: 10px; min-height: 0; overflow-y: auto; }
.side h4 { margin: 8px 2px 0; font-size: 12px; font-weight: 650; color: var(--muted); }
.levels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; background: var(--column); border-radius: 8px; padding: 2px; }
.levels button { border: none; background: transparent; border-radius: 6px; padding: 4px 0; color: var(--muted); font-weight: 550; }
.levels button:hover { color: var(--text); }
.levels button.on { background: var(--panel); box-shadow: var(--shadow), 0 0 0 1px var(--line); color: var(--text); }
.levels button.on.hard { color: var(--danger); }
.tile { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; text-align: left; padding: 10px 12px; border-radius: 8px; background: var(--panel); border: 1px solid var(--line); box-shadow: none; }
.tile:hover { border-color: color-mix(in srgb, var(--text) 22%, var(--line)); }
.tile.on { border-color: var(--accent); box-shadow: inset 2px 0 0 var(--accent); }
.tile b { font-weight: 650; }
.tile small { grid-column: 1 / -1; color: var(--muted); font-size: 12px; line-height: 1.35; }
.tile .best { font: 600 12px var(--mono); color: var(--accent-ink); align-self: center; }
.tile .best.none { color: var(--muted); font-weight: 400; }
.records { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: none; padding: 6px 10px; font-size: 12px; }
.records table { width: 100%; border-collapse: collapse; }
.records th { color: var(--muted); font-weight: 500; text-align: right; padding: 3px 0; }
.records th:first-child, .records td:first-child { text-align: left; }
.records td { text-align: right; padding: 3px 0; font-family: var(--mono); border-top: 1px solid var(--line); }
.records td:first-child { font-family: var(--font); }
.stage { display: flex; flex-direction: column; min-height: 0; min-width: 0; gap: 8px; }
.screen { flex: 1; min-height: 0; background: #0c0c0b; border-radius: var(--radius); display: grid; place-items: center; position: relative; overflow: hidden; box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), var(--shadow); }
.screen canvas { display: block; cursor: crosshair; }
.screen .idle { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: #c9ccd4; text-align: center; padding: 20px; }
.screen .idle b { font: 700 22px var(--mono); letter-spacing: .3em; color: #ffc933; }
.screen .idle span { color: #8b8f98; font-size: 13px; }
.screen:fullscreen { border-radius: 0; }
.status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.status .what { font-weight: 600; }
.status .hint { color: var(--muted); font-size: 12px; flex: 1; }
.status .live { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.status .live.on { background: var(--ok); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 25%, transparent); }

#toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(6px); background: var(--text); color: var(--bg); padding: 8px 14px; border-radius: 7px; opacity: 0; transition: opacity .2s, transform .2s; pointer-events: none; max-width: 80vw; box-shadow: var(--lift); z-index: 20; }
#toast.on { opacity: .96; transform: translateX(-50%); }
kbd { font: 11px var(--mono); border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 5px; padding: 0 5px; background: var(--panel); }
#help { position: fixed; inset: 0; background: rgba(10,8,4,.4); display: none; place-items: center; z-index: 10; }
#help.on { display: grid; }
#help .sheet { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--lift); padding: 18px 22px; width: min(460px, 92vw); }
#help h3 { margin: 0 0 10px; font-size: 15px; }
#help dl { display: grid; grid-template-columns: auto 1fr; gap: 7px 16px; margin: 0; font-size: 13px; }
#help dt { text-align: right; white-space: nowrap; }
#help dd { margin: 0; color: var(--muted); }
/*@STUDIO_CSS@*/
@media (max-width: 760px) {
  .arcade { grid-template-columns: 1fr; height: auto; }
  .screen { min-height: 360px; }
  .search input { width: 170px; }
}
.cv { display: flex; flex-direction: column; height: 100%; min-height: 420px; }
.cvbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 6px 12px; border-bottom: 1px solid var(--line); background: var(--panel); }
.cvbar .group { display: flex; align-items: center; gap: 2px; background: var(--column); border-radius: 8px; padding: 2px; }
.cvbar .group button { border: none; background: transparent; padding: 4px 6px; border-radius: 6px; color: var(--muted); font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }
.cvbar .group button svg { width: 18px; height: 18px; display: block; }
.cvbar .group button:disabled { opacity: .35; }
.cvbar .group button:hover { color: var(--text); }
.cvbar .group button.on { background: var(--accent); color: var(--on-accent); }
.cvbar .group .swatch { box-sizing: border-box; width: 18px; height: 18px; padding: 0; border-radius: 50%; margin: 0 3px; border: 2px solid var(--line); }
.cvbar .group .swatch.on { border-color: var(--accent-ink); box-shadow: 0 0 0 2px var(--accent-soft); }
.cvbar .group .swatch.custom { position: relative; display: inline-block; overflow: hidden; cursor: pointer; background: conic-gradient(#e5484d, #e8b520, #30a46c, #2aa9bd, #3a6df0, #8e4ec6, #e5484d); }
.cvbar .group .swatch.custom input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; border: 0; padding: 0; cursor: pointer; }
.cvbar .cvname { width: 150px; font-weight: 600; border: 1px solid transparent; background: transparent; border-radius: 7px; padding: 3px 7px; color: var(--text); }
.cvbar .cvname:hover, .cvbar .cvname:focus { border-color: var(--line); background: var(--column); outline: none; }
.cvbar .group button.more { position: relative; }
.cvbar .group button.more::after { content: ""; position: absolute; right: 2px; bottom: 2px; border-style: solid; border-width: 0 0 5px 5px; border-color: transparent transparent currentColor transparent; opacity: .55; }
.cvbar .cvwidth { width: 100px; margin: 0 4px; accent-color: var(--accent); }
.cvbar .cvwidthval { width: 38px; font-size: 12px; color: var(--text); text-align: center; font-variant-numeric: tabular-nums; border: 1px solid transparent; background: transparent; border-radius: 6px; padding: 2px 3px; margin-right: 2px; }
.cvbar .cvwidthval:hover, .cvbar .cvwidthval:focus { border-color: var(--line); background: var(--panel); outline: none; }
.cvmenu { position: fixed; z-index: 30; display: none; flex-direction: column; gap: 2px; padding: 4px; background: var(--panel); border: 1px solid var(--line); border-radius: 9px; box-shadow: var(--lift); }
.cvmenu.on { display: flex; }
.cvmenu button { display: flex; align-items: center; gap: 9px; border: none; background: transparent; padding: 6px 10px; border-radius: 5px; color: var(--text); font-size: 13px; text-align: left; white-space: nowrap; }
.cvmenu button:hover { background: var(--column); }
.cvmenu button.on { background: var(--accent-soft); color: var(--accent-ink); }
.cvmenu button svg { width: 18px; height: 18px; flex: none; }
.cvmenu .num { width: 18px; text-align: center; font-weight: 700; font-size: 15px; }
.cvzoom, .cvstatus { font: 12px var(--mono); color: var(--muted); min-width: 40px; text-align: center; }
.cvstage { position: relative; flex: 1; min-height: 0; overflow: hidden; }
.cvbody { flex: 1; min-height: 0; display: flex; position: relative; }
.cvbar .cvpick { display: inline-flex; gap: 5px; align-items: center; max-width: 140px; border-color: transparent; background: var(--column); color: var(--muted); }
.cvview { display: none; position: absolute; inset: 0; z-index: 6; background: var(--bg); flex-direction: column; }
.cvview.on { display: flex; }
.cvview .head { display: flex; align-items: center; gap: 10px; padding: 8px 14px; border-bottom: 1px solid var(--line); background: var(--panel); }
.cvview .head b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cvview .head .spacer { flex: 1; }
.cvview .head button { display: inline-flex; align-items: center; gap: 5px; }
.cvview .head button svg { width: 16px; height: 16px; }
.cvview .body { flex: 1; min-height: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 14px; overflow: auto; }
.cvview .body img, .cvview .body video { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; }
.cvview .body iframe { flex: 1; width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.cvview .body.text { align-items: stretch; justify-content: flex-start; }
.cvview .body pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 13px/1.5 var(--mono); color: var(--text); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
.cvview .body .sound { display: flex; flex-direction: column; align-items: center; gap: 14px; font-weight: 600; }
.cvview .body .sound > svg { width: 64px; height: 64px; color: var(--accent-ink); }
.cvview .body .sound audio { width: min(520px, 80vw); }
.cvview .body canvas.model { flex: 1; width: 100%; min-height: 200px; cursor: grab; touch-action: none; }
.cvview .note { color: var(--muted); font-size: 12px; text-align: center; }
.cvgallery { display: none; position: absolute; inset: 0; z-index: 5; background: var(--bg); overflow: auto; padding: 14px 18px 24px; }
.cvgallery.on { display: block; }
.cvgallery .head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.cvgallery .head .hint { color: var(--muted); font-size: 12px; }
.cvgallery .head .search { width: 220px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--text); font: inherit; }
.cvgallery .head .search:focus { outline: none; border-color: var(--accent-ink); }
.cvgallery > .shelves > .empty { color: var(--muted); padding: 20px 4px; }
.cvgallery .head .spacer { flex: 1; }
.cvgallery .head button { display: inline-flex; align-items: center; gap: 5px; }
.cvgallery .head button svg { width: 16px; height: 16px; }
.cvgallery .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.cvgallery .tile { position: relative; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; cursor: pointer; }
.cvgallery .tile:hover { border-color: var(--accent-ink); }
.cvgallery .tile.on { box-shadow: 0 0 0 2px var(--accent); }
.cvgallery .thumb { display: block; width: 100%; aspect-ratio: 8 / 5; background: var(--column); }
.cvgallery .meta { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; }
.cvgallery .meta .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cvgallery .meta .when { color: var(--muted); font-size: 11px; }
.cvgallery .acts { position: absolute; top: 6px; right: 6px; display: flex; gap: 4px; }
.cvgallery .acts button { display: none; border: none; border-radius: 7px; padding: 5px; background: var(--panel); color: var(--muted); box-shadow: var(--shadow); }
.cvgallery .acts svg { width: 16px; height: 16px; display: block; }
.cvgallery .tile:hover .acts button, .cvgallery .acts .fav.on { display: block; }
.cvgallery .acts .fav.on { color: var(--energy); }
.cvgallery .acts .fav.on svg { fill: currentColor; }
.cvgallery .acts button:hover { color: var(--text); }
.cvgallery .acts .del:hover { color: #e5484d; }
.cvgallery .shelf { margin-bottom: 22px; border-radius: var(--radius); }
.cvgallery .shelf.drop { outline: 2px dashed var(--accent-ink); outline-offset: 6px; }
.cvgallery .section { display: flex; align-items: center; gap: 8px; margin: 0 0 10px; color: var(--text); }
.cvgallery .section > svg { width: 16px; height: 16px; color: var(--muted); }
.cvgallery .section.favorites > svg { color: var(--energy); fill: currentColor; }
.cvgallery .section .count { color: var(--muted); font-size: 12px; }
.cvgallery .section .mini { border: none; background: transparent; padding: 3px; color: var(--muted); display: inline-flex; }
.cvgallery .section .mini svg { width: 15px; height: 15px; }
.cvgallery .section .mini:hover { color: var(--text); }
.cvgallery .shelf .empty { color: var(--muted); font-size: 12px; padding: 18px 4px; }
.cvinline { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 1; }
.cvinline iframe { position: absolute; border: 0; background: #ffffff; pointer-events: auto; box-shadow: 0 2px 10px rgba(0, 0, 0, .25); }
.cvplayers { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }
.cvlayers { display: none; width: 240px; flex: none; border-left: 1px solid var(--line); background: var(--panel); overflow: auto; font-size: 13px; }
.cvlayers.on { display: block; }
.cvlayers .head { display: flex; align-items: baseline; gap: 8px; padding: 10px 12px 6px; position: sticky; top: 0; background: var(--panel); }
.cvlayers .head .n { color: var(--muted); font-size: 11px; }
.cvlayers .head .spacer { flex: 1; }
.cvlayers .head .all { border: none; background: transparent; padding: 2px; color: var(--muted); display: inline-flex; align-self: center; }
.cvlayers .head .all svg { width: 14px; height: 14px; }
.cvlayers .head .all:hover { color: var(--text); }
.cvlayers .fold { width: 18px; flex: none; border: none; background: transparent; padding: 1px; color: var(--muted); display: inline-flex; }
.cvlayers .fold svg { width: 14px; height: 14px; }
.cvlayers .fold:hover { color: var(--text); }
.cvlayers .row.section { margin-top: 6px; color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; cursor: pointer; }
.cvlayers .row.group .name { font-weight: 600; }
.cvlayers .row .count { margin-left: auto; color: var(--muted); font-size: 11px; background: var(--column); border-radius: 8px; padding: 0 6px; }
.cvlayers .row { display: flex; align-items: center; gap: 6px; padding: 4px 8px; margin: 0 4px; border-radius: 6px; cursor: default; }
.cvlayers .row:hover { background: var(--column); }
.cvlayers .row.on { background: var(--accent-soft); }
.cvlayers .row.inner { padding-left: 32px; }
.cvlayers .row.hidden .name, .cvlayers .row.hidden > svg { opacity: .4; }
.cvlayers .row > svg { width: 16px; height: 16px; flex: none; color: var(--muted); }
.cvlayers .row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cvlayers .eye { border: none; background: transparent; padding: 2px; color: var(--muted); display: inline-flex; }
.cvlayers .eye svg { width: 16px; height: 16px; }
.cvlayers .eye:hover { color: var(--text); }
.cvlayers .empty { padding: 8px 14px; }
.cvcanvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; touch-action: none; outline: none; }
.cvedit { position: absolute; display: none; resize: none; border: 2px solid var(--accent); border-radius: 8px; background: var(--panel); color: var(--text); padding: 4px 6px; outline: none; z-index: 3; line-height: 1.3; overflow: auto; }
.cvempty { position: absolute; inset: 0; display: none; place-content: center; justify-items: center; gap: 10px; color: var(--muted); }
.cvbar .cvadd { margin-left: auto; }
.cvbar .cvadd button { gap: 5px; color: var(--text); font-weight: 600; padding: 4px 9px; }
.embed header .brand, .embed #tabs { display: none; }
.embed[data-view="canvas"] header, .embed[data-view="studio"] header { display: none; }
.cvstage.dropping::after { content: "Drop files to pin them here"; position: absolute; inset: 10px; display: grid; place-items: center; border: 3px dashed var(--accent); border-radius: 14px; background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent-ink); font-weight: 700; font-size: 18px; pointer-events: none; z-index: 4; }
</style>
</head>
<body>
<header>
  <span class="brand"><svg class="mark light" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#fff"/><path d="M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5" fill="none" stroke="#f5a300" stroke-width="7"/></svg><svg class="mark dark" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0b0b0a"/><path d="M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5" fill="none" stroke="#f5a300" stroke-width="7"/></svg>Desk</span>
  <div id="boards" class="picker"></div>
  <div class="tabs" id="tabs">
    <button data-view="board" class="on" title="Board (1)">Board</button>
    <button data-view="today" title="Today: tasks and focus stats (2)">Today</button>
    <button data-view="games" title="Games (3)">Games</button>
    <button data-view="studio" title="Studio: record and screenshots (4)">Studio</button>
    <button data-view="canvas" title="Canvas: whiteboard (5)">Canvas</button>
  </div>
  <span class="spacer"></span>
  <button id="recPill" class="rec-pill" title="Recording: open the Studio"></button>
  <div class="timer" id="timer">
    <span class="phase" id="phase">Ready</span>
    <span class="bar"><i id="progress"></i></span>
    <span class="clock" id="clock">25:00</span>
    <span class="linked" id="linked"></span>
    <button id="play" title="Start / pause (space)">Start</button>
    <button id="skip" class="ghost" title="Skip to the next phase">Skip</button>
    <button id="stop" class="ghost" title="Stop">Stop</button>
  </div>
  <div class="actions-bar">
    <button id="obsidian" class="ghost icon" title="Open this board in Obsidian"><svg viewBox="0 0 24 24"><path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg></button>
    <button id="lofi" class="ghost icon" title="Open lofi music"><svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg></button>
    <button id="theme" class="ghost icon" title="Light / dark"><svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg></button>
    <button id="helpButton" class="ghost icon" title="Keyboard shortcuts (?)"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><path d="M12 17.5h.01"/></svg></button>
  </div>
</header>
<div class="toolbar" id="toolbar">
  <label class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="search" type="search" placeholder="Search cards  /"></label>
  <button id="filter" class="chip" title="Clear tag filter"></button>
  <div class="summary" id="summary"></div>
</div>
<main id="main"></main>
<div id="help"><div class="sheet">
  <h3>Keyboard shortcuts</h3>
  <dl>
    <dt><kbd>n</kbd></dt><dd>New card (Today: quick add)</dd>
    <dt><kbd>/</kbd></dt><dd>Search cards</dd>
    <dt><kbd>space</kbd></dt><dd>Start / pause the focus timer</dd>
    <dt><kbd>1</kbd> … <kbd>5</kbd></dt><dd>Board, Today (tasks and focus stats), Games, Studio, Canvas (on the Studio Record tab the digits pick scenes)</dd>
    <dt><kbd>Esc</kbd></dt><dd>Clear search and tag filter</dd>
    <dt>double-click</dt><dd>Edit a card; drag cards between columns</dd>
    <dt>Games</dt><dd>While a game runs every key goes to it: arrows/WASD, Space, P pause, Esc leaves. Mouse works as in the terminal.</dd>
    <dt>Studio</dt><dd>Record tab: <kbd>r</kbd> start (after the countdown) / stop, <kbd>p</kbd> pause / resume, <kbd>m</kbd> mark, <kbd>1</kbd> … <kbd>9</kbd> scenes. Drag a source to move it (corners and edges snap; a corner pins it), drag its yellow corner to resize, <kbd>⌥</kbd>-drag to pan inside it. Recording runs <code>ul capture</code>, so it keeps going when the page is closed; every recording becomes a project you export from the Projects tab.</dd>
    <dt>Canvas</dt><dd>Photoshop-style keys; a tool stays until you pick another. <kbd>v</kbd> select, <kbd>h</kbd> hand (or hold <kbd>space</kbd>), <kbd>n</kbd> card, <kbd>t</kbd> text, <kbd>u</kbd> shapes (<kbd>Shift</kbd>+<kbd>u</kbd> cycles rectangle, ellipse, diamond, line, arrow; also <kbd>r</kbd> <kbd>o</kbd> <kbd>l</kbd> <kbd>a</kbd>), <kbd>b</kbd> brush, <kbd>g</kbd> fill (<kbd>Alt</kbd>+click clears; open space reaching the edge of the view fills the background), <kbd>e</kbd> eraser (<kbd>Shift</kbd>+<kbd>e</kbd> switches whole object / only where it passes). Click an active eraser or shape tool again for its options (shape evenness 3 perfect, 2, 1 rougher). The fill tool floods the area of the clicked color like a paint program. <kbd>[</kbd> <kbd>]</kbd> or <kbd>-</kbd> <kbd>=</kbd> stroke width (slider 1-100; click the number to type one), <kbd>d</kbd> default color, <kbd>Cmd/Ctrl</kbd>+<kbd>G</kbd> group, <kbd>Cmd/Ctrl</kbd>+<kbd>0</kbd> fit, <kbd>Cmd/Ctrl</kbd>+<kbd>+</kbd> <kbd>-</kbd> zoom, <kbd>Del</kbd> delete, arrows nudge, <kbd>Cmd/Ctrl</kbd>+<kbd>Z</kbd> <kbd>C</kbd> <kbd>V</kbd> <kbd>D</kbd> <kbd>A</kbd>. Wheel pans, <kbd>Ctrl</kbd>+wheel or pinch zooms, double-click edits text, drag a side dot of a card to connect (let go on empty canvas for a new card). <kbd>k</kbd> thread: click a spot on one card, then on another; drag the end of a selected edge to move it. <kbd>F7</kbd> or the layers button: Layers, the eye hides a card, group or drawing, drag rows to reorder. The name left of the tools renames the file.</dd>
    <dt><kbd>?</kbd></dt><dd>This list</dd>
  </dl>
</div></div>
<div id="viewer"><div class="sheet" id="viewerSheet"></div></div>
<div id="toast"></div>
<script>
"use strict";
const params = new URLSearchParams(location.search);
// Inside Unlaw.app each part (Board, Today, Canvas, Studio) is its own item in the
// app's sidebar: the page hides its tabs and the app switches the part.
if (params.get("embed") === "1") sessionStorage.setItem("desk-embed", "1");
const EMBED = sessionStorage.getItem("desk-embed") === "1";
if (EMBED) document.documentElement.classList.add("embed");
if (params.get("token")) {
  sessionStorage.setItem("desk-token", params.get("token"));
  history.replaceState(null, "", location.pathname + location.hash);
}
const TOKEN = sessionStorage.getItem("desk-token") || "";
const VIEWS = ["board", "today", "games", "studio", "canvas"];
// Stats became part of Today (3.22.0): an old bookmark or saved view opens Today.
const savedView = (view) => view === "stats" ? "today" : view;
const state = { board: null, view: VIEWS.includes(savedView(location.hash.slice(1))) ? savedView(location.hash.slice(1)) : savedView(localStorage.getItem("desk-view") || "board"), query: "", tag: "", timer: null, timerAt: 0, editing: null, dragging: null, draggingColumn: null, stats: null };
if (!VIEWS.includes(state.view)) state.view = "board";
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
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: { "X-Desk-Token": TOKEN, "Content-Type": "application/json", ...(headers || {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (error) {
    return { status: 0, data: { error: "Could not reach the desk: " + error.message } };
  }
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
  if (!state.editing && !["games", "studio", "canvas"].includes(state.view)) render();
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

const MARKUP = /(\[\[[^\]]+\]\])|(?<![\w&/])#([^\s#\[\]{}(),.;:!?'"]+)|@\{(\d{4}-\d{2}-\d{2})\}|\u{1F4C5}\s*(\d{4}-\d{2}-\d{2})|\s*\[completion::\s*\d{4}-\d{2}-\d{2}\]/gu;

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
    h("button", { class: "del", title: "Delete", "aria-label": "Delete", onclick: (event) => { event.stopPropagation(); if (confirm("Delete this card?\n\n" + card.title)) change({ op: "delete", ...where }); } }, svgIcon("M6 6l12 12M18 6L6 18")));
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
    const movable = board.layer !== "reminders";
    const heading = h("h2", { draggable: movable ? "true" : null, title: movable ? "Drag to move the column" : null }, h("span", { class: "name", text: column.name, title: column.name }),
        h("span", { class: "count", text: state.query || state.tag ? shown + "/" + column.cards.length : column.cards.length }),
        h("button", { title: "Add a card to " + column.name, text: "+", onclick: () => input.focus() }));
    const node = h("section", { class: "column" + (column.doing ? " doing" : "") + (done ? " done" : "") }, heading,
      list, h("div", { class: "add" }, input));
    if (movable) {
      heading.addEventListener("dragstart", (event) => {
        state.draggingColumn = c;
        node.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", column.name);
        event.dataTransfer.setDragImage(node, event.offsetX, event.offsetY);
      });
      heading.addEventListener("dragend", () => {
        state.draggingColumn = null;
        node.classList.remove("dragging");
        for (const other of wrap.querySelectorAll(".column")) other.classList.remove("col-before", "col-after");
      });
    }
    // Which side of this column a dragged column lands on: the left or right half under the pointer.
    const columnSide = (event) => {
      const box = node.getBoundingClientRect();
      return event.clientX < box.left + box.width / 2 ? "before" : "after";
    };
    node.addEventListener("dragover", (event) => {
      if (state.draggingColumn != null) {
        event.preventDefault();
        const side = state.draggingColumn === c ? null : columnSide(event);
        node.classList.toggle("col-before", side === "before");
        node.classList.toggle("col-after", side === "after");
        return;
      }
      if (!state.dragging) return;
      event.preventDefault();
      node.classList.add("drop");
    });
    node.addEventListener("dragleave", (event) => {
      if (node.contains(event.relatedTarget)) return;
      node.classList.remove("drop", "col-before", "col-after");
    });
    node.addEventListener("drop", (event) => {
      event.preventDefault();
      node.classList.remove("drop", "col-before", "col-after");
      if (state.draggingColumn != null) {
        const from = state.draggingColumn;
        state.draggingColumn = null;
        let to = columnSide(event) === "before" ? c : c + 1;
        if (from < to) to -= 1;
        if (from !== to) change({ op: "move_column", column: from, name: board.columns[from].name, to_index: to });
        return;
      }
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

function renderSummary() {
  const node = $("summary");
  node.textContent = "";
  if (!state.board) return;
  const board = state.board;
  const today = board.today;
  let open = 0, due = 0, late = 0;
  for (const column of board.columns) {
    if (column.name === board.done_column) continue;
    for (const card of column.cards) {
      if (card.checked) continue;
      open += 1;
      if (card.due && card.due < today) late += 1;
      else if (card.due === today) due += 1;
    }
  }
  const pill = (count, label, kind) => h("span", { class: "pill " + (kind || "") }, h("b", { text: count }), " " + label);
  node.append(pill(open, "open"));
  if (due) node.append(pill(due, "due today", "today"));
  if (late) node.append(pill(late, "overdue", "late"));
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
  const stats = h("div", { class: "today-stats" });
  const page = h("div", { class: "page" }, stats, h("div", { class: "quick" }, quick));
  drawTodayStats(stats);
  loadTodayStats(stats);
  const section = (title, items) => {
    page.append(h("h3", {}, title, h("span", { class: "n", text: items.length })));
    if (!items.length) page.append(h("div", { class: "empty", text: "Nothing here." }));
    for (const item of items) page.append(cardNode(item.card, item.c, item.i, { where: item.where }));
  };
  section("Overdue", late);
  section("Today", due);
  section("In progress", doing);
  section("Next 7 days", soon);
  const most = h("div", { class: "most-focused" });
  page.append(most);
  drawMostFocused(most);
  main.append(page);
}

// Calendar arithmetic in UTC: a local noon is the previous UTC day in UTC+13/+14.
function addDays(iso, days) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

// Focus numbers for Today come from /api/stats (pomodoro log + done dates); kept between renders so the
// page does not flicker, refreshed at most every 20 s or when the board/timer changes them.
let todayStatsAt = 0;
async function loadTodayStats(node) {
  if (Date.now() - todayStatsAt < 20000 && state.stats) return;
  todayStatsAt = Date.now();
  const { status, data } = await api("GET", "/api/stats");
  if (status !== 200) { todayStatsAt = 0; return; }
  state.stats = data;
  if (state.view !== "today" || !node.isConnected) return;
  drawTodayStats(node);
  const most = document.querySelector(".most-focused");
  if (most) drawMostFocused(most);
}

function drawTodayStats(node) {
  node.textContent = "";
  const data = state.stats;
  if (!data) return;
  const number = (value, label) => h("div", { class: "number" }, h("b", { text: value }), h("span", { text: label }));
  const most = Math.max(1, ...data.week.map((day) => Math.max(day.pomodoros, day.done)));
  const week = h("div", { class: "week mini", title: "Last 7 days: focus sessions (orange) and tasks done (green)" }, data.week.map((day) => h("div", { class: "day", title: day.date + ": " + day.pomodoros + " focus, " + day.minutes + " min, " + day.done + " done" },
    h("div", { class: "bars" }, h("i", { class: "f", style: "height:" + (day.pomodoros / most * 100) + "%" }), h("i", { class: "d", style: "height:" + (day.done / most * 100) + "%" })),
    h("span", { text: new Date(day.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "narrow" }) }))));
  node.append(h("div", { class: "numbers" },
    number(Math.round(data.today.minutes), "focus min today"),
    number(data.today.done, "done today"),
    number(data.streak, "day streak"),
    week));
}

function drawMostFocused(node) {
  node.textContent = "";
  const data = state.stats;
  if (!data || !data.cards.length) return;
  node.append(h("h3", {}, "Most focused cards", h("span", { class: "n", text: data.total_pomodoros + " sessions all time" })),
    h("div", { class: "top" }, data.cards.map((item) => h("div", {}, h("span", { text: item.card }), h("span", { class: "where", text: Math.round(item.minutes) + " min" })))));
}

function render() {
  const main = $("main");
  document.documentElement.dataset.view = state.view;
  for (const button of $("tabs").children) button.classList.toggle("on", button.dataset.view === state.view);
  $("toolbar").classList.toggle("hidden", ["games", "studio", "canvas"].includes(state.view));
  const filter = $("filter");
  filter.classList.toggle("on", Boolean(state.tag));
  filter.textContent = state.tag ? "#" + state.tag + " " : "";
  if (state.tag) filter.append(svgIcon("M6 6l12 12M18 6L6 18"));
  renderSummary();
  if (state.view === "games") { renderGames(main); return; }
  if (state.view === "studio") { renderStudio(main); return; }
  if (state.view === "canvas") { renderCanvas(main); return; }
  if (!state.board) return;
  const scroll = main.scrollLeft;
  const active = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.column : undefined;
  main.textContent = "";
  if (state.view === "today") renderToday(main);
  else renderBoard(main);
  main.scrollLeft = scroll;
  if (active !== undefined) document.querySelector('.add input[data-column="' + active + '"]')?.focus();
}

function setView(view) {
  if (view === state.view) return;
  if (state.view === "games") pauseGame();
  if (state.view === "studio") leaveStudio();
  if (state.view === "canvas") leaveCanvas();
  state.view = view;
  // The app chooses the part; the browser desk keeps its own last view.
  if (!EMBED) localStorage.setItem("desk-view", view);
  history.replaceState(null, "", location.pathname + "#" + view);
  render();
}

function setTag(tag) {
  state.tag = state.tag === tag ? "" : tag;
  render();
}

// ---- games: the Rust arcade streamed from `ul game --stream` ----
const GAME_INFO = {
  tetris: "7-bag, next and hold, ghost piece, wall kicks",
  snake: "Eat ● and bonus ★, grow and speed up",
  minesweeper: "First click is safe; lowest time wins",
  invaders: "Formation, shields, UFO, waves",
  chomp: "Maze chase with four hunters; new maze each level",
  dash: "Endless runner: jump, duck, faster and faster",
  pingpong: "Table tennis to 11: vs the bot or a friend (W/S and ↑/↓)",
  chess: "vs the bot or a friend, optional clock; click a piece, then its square",
};
const PALETTE = { red: "#ff5f57", green: "#3ed67a", yellow: "#ffd84d", blue: "#4d8dff", magenta: "#d77bff", cyan: "#4fd8e8", white: "#f4f5f7", gray: "#8b8f98", darkred: "#c0392b", darkyellow: "#c9971c", darkblue: "#3159c9", darkcyan: "#1f9aa8", boardlight: "#b58c63", boarddark: "#78563a", lastlight: "#aaa23a", lastdark: "#8a8228", selected: "#608c56", target: "#b05448", check: "#d63a3a", piecewhite: "#ffffff", pieceblack: "#000000" };
const SCREEN_BG = "#0e1014", SCREEN_FG = "#d9dce3";
const QUADRANTS = { "▘": 1, "▝": 2, "▖": 4, "▌": 5, "▞": 6, "▛": 7, "▗": 8, "▚": 9, "▐": 10, "▜": 11, "▙": 13, "▟": 14 };
const BOX = { "─": "0101", "│": "1010", "┌": "0110", "┐": "0011", "└": "1100", "┘": "1001", "├": "1110", "┤": "1011", "┬": "0111", "┴": "1101", "┼": "1111", "═": "0101", "║": "1010" };
const arcade = { info: null, level: localStorage.getItem("desk-level") || "", game: null, session: "", frame: null, queue: [], sending: false, abort: null, cell: { w: 10, h: 20, font: 16 }, grid: { rows: 30, cols: 100 }, hover: "", drawPending: false, ended: "" };

async function loadGames() {
  const { status, data } = await api("GET", "/api/games");
  if (status !== 200) return;
  arcade.info = data;
  if (!arcade.level) arcade.level = data.difficulty;
  if (state.view === "games") renderGameSide();
}

function bestText(game, level) {
  const best = game.best[level];
  return best === undefined ? null : best + (game.unit ?? (game.lower ? "s" : ""));
}

function renderGames(main) {
  if (main.querySelector(".arcade")) { renderGameSide(); fitScreen(); return; }
  main.textContent = "";
  const canvas = h("canvas", { id: "gameCanvas" });
  const idle = h("div", { class: "idle", id: "gameIdle" });
  const screen = h("div", { class: "screen", id: "gameScreen" }, canvas, idle);
  const status = h("div", { class: "status" },
    h("span", { class: "live", id: "gameLive" }),
    h("span", { class: "what", id: "gameWhat", text: "No game running" }),
    h("span", { class: "hint", id: "gameHint", text: "Keys go to the game while it runs. Esc leaves a game." }),
    h("button", { id: "gamePause", title: "Pause / resume (P)", text: "Pause", onclick: () => sendGame([{ key: "p" }]) }),
    h("button", { id: "gameAgain", title: "Start this game again", text: "Restart", onclick: () => startGame(arcade.game) }),
    h("button", { id: "gameStop", class: "ghost", title: "Stop the game", text: "Stop", onclick: stopGame }),
    h("button", { class: "ghost icon", title: "Full screen", onclick: () => screen.requestFullscreen?.() }, svgIcon("M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5")));
  main.append(h("div", { class: "arcade" }, h("aside", { class: "side", id: "gameSide" }), h("div", { class: "stage" }, screen, status)));
  canvas.addEventListener("mousedown", (event) => {
    if (!arcade.session) return;
    event.preventDefault();
    const at = cellAt(event);
    if (at) sendGame([{ click: { ...at, button: ["left", "middle", "right"][event.button] || "left" } }]);
  });
  canvas.addEventListener("mousemove", (event) => {
    if (!arcade.session) return;
    const at = cellAt(event);
    if (!at || at.y + ":" + at.x === arcade.hover) return;
    arcade.hover = at.y + ":" + at.x;
    sendGame([{ hover: at }]);
  });
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  renderGameSide();
  updateGameStatus();
  fitScreen();
  if (!arcade.info) loadGames();
}

function svgIcon(path) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
  node.setAttribute("d", path);
  svg.append(node);
  return svg;
}

function renderGameSide() {
  const side = $("gameSide");
  if (!side) return;
  side.textContent = "";
  const info = arcade.info;
  if (info && !info.available) {
    side.append(h("div", { class: "empty", text: "Games are not installed in this ul. Turn on the `game` feature: ul features" }));
    return;
  }
  const level = arcade.level || "normal";
  side.append(h("h4", { text: "Difficulty" }), h("div", { class: "levels" }, ["easy", "normal", "hard"].map((name) =>
    h("button", { class: (name === level ? "on " : "") + name, text: name[0].toUpperCase() + name.slice(1), onclick: () => { arcade.level = name; localStorage.setItem("desk-level", name); renderGameSide(); } }))));
  side.append(h("h4", { text: "Games" }));
  for (const game of info ? info.games : []) {
    const best = bestText(game, level);
    side.append(h("button", { class: "tile" + (arcade.session && arcade.game === game.name ? " on" : ""), title: "Play " + game.label + " (" + level + ")", onclick: () => startGame(game.name) },
      h("b", { text: game.label }),
      h("span", { class: "best" + (best ? "" : " none"), text: best ? "best " + best : "no record" }),
      h("small", { text: GAME_INFO[game.name] || "" })));
  }
  side.append(h("button", { title: "The terminal arcade menu with every game", text: "Arcade menu", onclick: () => startGame(null) }));
  if (info) {
    side.append(h("h4", { text: "Records · shared with ul game" }));
    side.append(h("div", { class: "records" }, h("table", {},
      h("tr", {}, h("th", { text: "" }), h("th", { text: "Easy" }), h("th", { text: "Normal" }), h("th", { text: "Hard" })),
      info.games.map((game) => h("tr", {}, h("td", { text: game.label }), ["easy", "normal", "hard"].map((name) => h("td", { text: bestText(game, name) || "–" })))))));
  }
}

function updateGameStatus() {
  if (!$("gameWhat")) return;
  const running = Boolean(arcade.session);
  const label = arcade.game ? (arcade.info?.games.find((game) => game.name === arcade.game)?.label || arcade.game) + " · " + (arcade.level || "normal") : "Arcade menu";
  $("gameLive").classList.toggle("on", running);
  $("gameWhat").textContent = running ? label : "No game running";
  $("gamePause").disabled = !running;
  $("gameStop").disabled = !running;
  $("gameAgain").disabled = !running && !arcade.ended;
  const idle = $("gameIdle");
  idle.textContent = "";
  idle.style.display = running ? "none" : "flex";
  if (!running) {
    idle.append(h("b", { text: "ARCADE" }), h("span", { text: arcade.ended || "Pick a game on the left, or open the arcade menu." }));
    if (arcade.ended) idle.append(h("button", { class: "primary", text: "Play again", onclick: () => startGame(arcade.game) }));
  }
}

// The grid keeps every game playable (Expert Minesweeper needs 64x21) and fills the panel.
function fitScreen() {
  const screen = $("gameScreen"), canvas = $("gameCanvas");
  if (!screen || !canvas) return null;
  const width = screen.clientWidth - 16, height = screen.clientHeight - 16;
  if (width <= 0 || height <= 0) return null;
  const context = canvas.getContext("2d");
  context.font = "100px " + getComputedStyle(document.body).getPropertyValue("--mono");
  const ratio = context.measureText("M").width / 100;
  const lineHeight = 1.22;
  // 30 rows fill the height; the longest game hint (Tetris) needs 113 columns,
  // so a narrower panel trades font size for columns (never below 80).
  let rows = 30;
  let font = height / (rows * lineHeight);
  let cols = Math.floor(width / (font * ratio));
  if (cols < 116) {
    cols = Math.max(80, Math.min(116, Math.floor(width / (11 * ratio))));
    font = width / (cols * ratio);
    rows = Math.max(24, Math.floor(height / (font * lineHeight)));
  }
  cols = Math.min(cols, 200);
  rows = Math.min(rows, 80);
  arcade.cell = { w: font * ratio, h: font * lineHeight, font };
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(cols * arcade.cell.w * scale);
  canvas.height = Math.round(rows * arcade.cell.h * scale);
  canvas.style.width = cols * arcade.cell.w + "px";
  canvas.style.height = rows * arcade.cell.h + "px";
  const changed = rows !== arcade.grid.rows || cols !== arcade.grid.cols;
  arcade.grid = { rows, cols };
  if (changed && arcade.session) sendGame([{ resize: { rows, cols } }]);
  drawGame();
  return arcade.grid;
}

function cellAt(event) {
  const box = event.target.getBoundingClientRect();
  const x = Math.floor((event.clientX - box.left) / arcade.cell.w);
  const y = Math.floor((event.clientY - box.top) / arcade.cell.h);
  return x >= 0 && y >= 0 && x < arcade.grid.cols && y < arcade.grid.rows ? { y, x } : null;
}

function scheduleDraw() {
  if (arcade.drawPending) return;
  arcade.drawPending = true;
  requestAnimationFrame(() => { arcade.drawPending = false; drawGame(); });
}

// Box-drawing and block characters are painted as shapes so lines and blocks join without gaps.
function drawCell(context, char, x, y, w, h, color) {
  const box = BOX[char];
  if (box) {
    context.strokeStyle = color;
    context.lineWidth = Math.max(1, Math.round(w / 8));
    const cx = Math.round(x + w / 2) + .5, cy = Math.round(y + h / 2) + .5;
    context.beginPath();
    if (box[0] === "1") { context.moveTo(cx, y); context.lineTo(cx, cy); }
    if (box[1] === "1") { context.moveTo(cx, cy); context.lineTo(x + w, cy); }
    if (box[2] === "1") { context.moveTo(cx, cy); context.lineTo(cx, y + h); }
    if (box[3] === "1") { context.moveTo(x, cy); context.lineTo(cx, cy); }
    context.stroke();
    return;
  }
  // Snap both edges: neighbours round the shared edge the same way, so no seams.
  const left = Math.round(x), top = Math.round(y), right = Math.round(x + w), bottom = Math.round(y + h);
  const shade = { "█": 1, "▓": .75, "▒": .5, "░": .25 }[char];
  if (shade) {
    const alpha = context.globalAlpha;
    context.globalAlpha = alpha * shade;
    context.fillStyle = color;
    context.fillRect(left, top, right - left, bottom - top);
    context.globalAlpha = alpha;
    return;
  }
  // Quadrant blocks (chess pieces): each set quarter is a rectangle on the snapped grid.
  const quad = QUADRANTS[char];
  if (quad) {
    const midX = Math.round(x + w / 2), midY = Math.round(y + h / 2);
    context.fillStyle = color;
    if (quad & 1) context.fillRect(left, top, midX - left, midY - top);
    if (quad & 2) context.fillRect(midX, top, right - midX, midY - top);
    if (quad & 4) context.fillRect(left, midY, midX - left, bottom - midY);
    if (quad & 8) context.fillRect(midX, midY, right - midX, bottom - midY);
    return;
  }
  if (char === "▀" || char === "▄") {
    const middle = Math.round(y + h / 2);
    context.fillStyle = color;
    context.fillRect(left, char === "▀" ? top : middle, right - left, char === "▀" ? middle - top : bottom - middle);
    return;
  }
  context.fillStyle = color;
  // Chess pieces (U+2654..265F) get the text-style selector: some fonts draw ♟ as a color emoji.
  const piece = char >= "\u2654" && char <= "\u265f";
  context.fillText(piece ? char + "\ufe0e" : char, x + w / 2, y + h / 2 + 1);
}

function drawGame() {
  const canvas = $("gameCanvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const scale = window.devicePixelRatio || 1;
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.fillStyle = SCREEN_BG;
  context.fillRect(0, 0, canvas.width, canvas.height);
  const frame = arcade.frame;
  if (!frame || !arcade.session) return;
  const { w, h: ch, font } = arcade.cell;
  const mono = getComputedStyle(document.body).getPropertyValue("--mono");
  context.textAlign = "center";
  context.textBaseline = "middle";
  frame.lines.forEach((runs, row) => {
    let column = 0;
    const y = row * ch;
    for (const [text, fgName, bgName, flags] of runs) {
      let fg = PALETTE[fgName] || SCREEN_FG, bg = PALETTE[bgName] || null;
      if (flags & 2) { const swap = fg; fg = bg || SCREEN_BG; bg = swap; }
      context.font = (flags & 1 ? "700 " : "400 ") + font + "px " + mono;
      context.globalAlpha = flags & 4 ? .55 : 1;
      const chars = [...text];
      if (bg) {
        const left = Math.round(column * w), top = Math.round(y);
        context.fillStyle = bg;
        context.fillRect(left, top, Math.round((column + chars.length) * w) - left, Math.round(y + ch) - top);
      }
      for (const char of chars) {
        if (char !== " ") drawCell(context, char, column * w, y, w, ch, fg);
        column += 1;
      }
    }
  });
  context.globalAlpha = 1;
}

function frameText() {
  return arcade.frame ? arcade.frame.lines.map((runs) => runs.map((run) => run[0]).join("")).join("\n") : "";
}

async function startGame(game) {
  if (arcade.info && !arcade.info.available) { toast("Games are not installed in this ul"); return; }
  if (state.view !== "games") setView("games");
  const grid = fitScreen() || arcade.grid;
  if (arcade.abort) arcade.abort.abort();
  const body = { game: game || null, rows: grid.rows, cols: grid.cols };
  if (game) body.level = arcade.level || "normal";
  const { status, data } = await api("POST", "/api/game/start", body);
  if (status !== 200) { toast(data.error || "Could not start the game"); return; }
  arcade.session = data.session;
  arcade.game = game;
  arcade.frame = null;
  arcade.queue = [];
  arcade.hover = "";
  arcade.ended = "";
  renderGameSide();
  updateGameStatus();
  streamGame(data.session);
}

async function streamGame(session) {
  const abort = new AbortController();
  arcade.abort = abort;
  try {
    const response = await fetch("/api/game/stream", { method: "POST", headers: { "X-Desk-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify({ session }), cache: "no-store", signal: abort.signal });
    if (!response.ok || !response.body) throw new Error("stream refused");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let at;
      while ((at = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, at).trim();
        buffer = buffer.slice(at + 1);
        if (!line) continue;
        const message = JSON.parse(line);
        if (message.end) continue;
        if (session === arcade.session) { arcade.frame = message; scheduleDraw(); }
      }
    }
  } catch (error) {
    if (abort.signal.aborted) return;
  }
  if (session === arcade.session) gameEnded("Game closed. Pick another one or play again.");
}

function gameEnded(message) {
  arcade.session = "";
  arcade.ended = message;
  arcade.frame = null;
  drawGame();
  updateGameStatus();
  loadGames();
}

async function sendGame(events) {
  if (!arcade.session) return;
  for (const event of events) {
    const last = arcade.queue[arcade.queue.length - 1];
    if (event.hover && last && last.hover) arcade.queue[arcade.queue.length - 1] = event;
    else arcade.queue.push(event);
  }
  if (arcade.sending) return;
  arcade.sending = true;
  while (arcade.queue.length && arcade.session) {
    const session = arcade.session;
    const batch = arcade.queue.splice(0, 64);
    const { status } = await api("POST", "/api/game/input", { session, events: batch });
    if (status === 410 && session === arcade.session) { arcade.queue = []; gameEnded("Game closed. Pick another one or play again."); }
  }
  arcade.sending = false;
}

async function stopGame() {
  const session = arcade.session;
  if (!session) return;
  if (arcade.abort) arcade.abort.abort();
  gameEnded("Stopped.");
  await api("POST", "/api/game/stop", { session });
}

// Leaving the tab or the window pauses a running game instead of losing it.
function pauseGame() {
  if (arcade.session && arcade.frame && !frameText().includes("PAUSED") && arcade.game) sendGame([{ key: "p" }]);
}

const GAME_KEYS = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "enter", Escape: "esc", Backspace: "backspace" };
function gameKey(event) {
  if (state.view !== "games" || !arcade.session || event.metaKey || event.ctrlKey || event.altKey) return false;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return false;
  const key = GAME_KEYS[event.key] || (event.key.length === 1 ? event.key : null);
  if (!key) return false;
  event.preventDefault();
  sendGame([{ key }]);
  return true;
}

// Key releases let two players hold keys at once (Ping Pong); games that did not ask ignore them.
document.addEventListener("keyup", (event) => {
  if (state.view !== "games" || !arcade.session || event.metaKey || event.ctrlKey || event.altKey) return;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
  const key = GAME_KEYS[event.key] || (event.key.length === 1 ? event.key : null);
  if (key) sendGame([{ release: key }]);
});

let resizeTimer = 0;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.view === "games") fitScreen(); }, 150); });
document.addEventListener("fullscreenchange", () => setTimeout(fitScreen, 60));

/*@STUDIO_JS@*/
// ---- boards ----
const REMINDERS = "reminders:";
let boardsDir = "";
// One flat menu that always opens below its button: a native <select> on macOS
// opens around the chosen item, so boards above it needed scrolling up.
const boardsMenu = { trigger: null, menu: null };

function boardLabel(path) {
  return { name: path.split("/").pop().replace(/\.md$/i, ""), where: path.split("/").slice(-2, -1)[0] || "" };
}

function boardItem(label, where, current, pick, kind) {
  return h("button", { type: "button", role: "menuitem", class: [kind, current ? "on" : ""].filter(Boolean).join(" ") || null, "aria-current": current ? "true" : null,
    onclick: () => { closeBoards(true); pick(); } },
    h("span", { class: "label", text: label }), where ? h("span", { class: "where", text: where }) : null);
}

function boardsOpen() { return Boolean(boardsMenu.menu && $("boards").classList.contains("open")); }

function openBoards() {
  $("boards").classList.add("open");
  boardsMenu.trigger.setAttribute("aria-expanded", "true");
  const items = [...boardsMenu.menu.querySelectorAll("button")];
  (items.find((item) => item.classList.contains("on")) || items[0])?.focus();
}

function closeBoards(refocus) {
  if (!boardsOpen()) return;
  $("boards").classList.remove("open");
  boardsMenu.trigger.setAttribute("aria-expanded", "false");
  if (refocus) boardsMenu.trigger.focus();
}

async function loadBoards() {
  const { status, data } = await api("GET", "/api/boards");
  if (status !== 200) return;
  boardsDir = data.boards_dir || "";
  const recent = (data.recent || []).length || data.current === REMINDERS ? data.recent || [] : [data.current].filter(Boolean);
  const paths = [...recent, ...(data.boards || []).filter((path) => !recent.includes(path))];
  const shown = data.current === REMINDERS ? { name: "Reminders" } : data.current ? boardLabel(data.current) : { name: "Boards" };
  const wasOpen = boardsOpen();
  const trigger = h("button", { type: "button", class: "trigger", title: "Boards", "aria-haspopup": "menu", "aria-expanded": "false",
    onclick: () => (boardsOpen() ? closeBoards(false) : openBoards()) }, h("span", { class: "name", text: shown.name }));
  const menu = h("div", { class: "menu", role: "menu" });
  if (data.reminders) menu.append(boardItem("Reminders", "Apple Reminders · lists as columns", data.current === REMINDERS, () => switchBoard(REMINDERS), "reminders"));
  for (const path of paths) {
    const label = boardLabel(path);
    menu.append(boardItem(label.name, label.where, path === data.current, () => switchBoard(path)));
  }
  menu.append(h("div", { class: "sep" }), boardItem("New board…", "", false, newBoard, "action"), boardItem("Open another board…", "", false, openOtherBoard, "action"));
  if (data.current && data.current !== REMINDERS) menu.append(boardItem("Delete this board…", shown.name + " goes to the Trash", false, () => deleteBoard(data.current, shown.name), "action danger"));
  const root = $("boards");
  root.textContent = "";
  root.append(trigger, menu);
  boardsMenu.trigger = trigger;
  boardsMenu.menu = menu;
  if (wasOpen) openBoards();
}

async function switchBoard(path, create) {
  const { status, data } = await api("POST", "/api/boards", { path, create: Boolean(create) });
  if (status === 200) { state.tag = ""; setBoard(data); loadBoards(); toast("Opened " + data.name); return; }
  if (status === 404 && data.missing && !create && (/\.md$/i.test(path) || !path.includes("/")) && confirm("No board at\n" + path + "\n\nCreate a new board there?")) return switchBoard(path, true);
  toast(data.error || "Could not open that board");
  loadBoards();
}

// New/Open show the macOS save/open dialog (through the server); without osascript the page asks for a name or path.
async function chooseBoard(create) {
  closeBoards(false);
  const { status, data } = await api("POST", "/api/boards/choose", { create });
  if (status !== 200) { toast(data.error || "Could not show the file dialog"); return null; }
  return data;
}

async function newBoard() {
  const data = await chooseBoard(true);
  if (!data) return;
  if (data.path) return switchBoard(data.path, true);
  if (!data.unavailable) return;
  const name = prompt("Name of the new board. It is saved in\n" + boardsDir + "\n(desk.boards_dir; a full path to a .md file works too)", "");
  if (name && name.trim()) switchBoard(name.trim(), true);
}

// The file goes to the Trash (the server refuses the default board); the next board opens.
async function deleteBoard(path, name) {
  closeBoards(false);
  if (!confirm("Move the board \"" + name + "\" to the Trash?\n\n" + path)) return;
  const { status, data } = await api("POST", "/api/boards/delete", { path });
  if (status !== 200) { toast(data.error || "Could not delete the board"); return; }
  state.tag = "";
  setBoard(data);
  loadBoards();
  toast("Moved " + name + " to the Trash");
}

async function openOtherBoard() {
  const data = await chooseBoard(false);
  if (!data) return;
  if (data.path) return switchBoard(data.path);
  if (!data.unavailable) return;
  const path = prompt("Path to a Kanban board (.md), or the name of a board in " + boardsDir + ". A missing file can be created.", "~/");
  if (path && path.trim()) switchBoard(path.trim());
}

$("boards").addEventListener("keydown", (event) => {
  if (!boardsOpen()) return;
  const items = [...boardsMenu.menu.querySelectorAll("button")];
  const at = items.indexOf(document.activeElement);
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const step = event.key === "ArrowDown" ? 1 : -1;
    items[at < 0 ? (step > 0 ? 0 : items.length - 1) : (at + step + items.length) % items.length]?.focus();
  } else if (event.key === "Home" || event.key === "End") {
    event.preventDefault();
    items[event.key === "Home" ? 0 : items.length - 1]?.focus();
  } else if (event.key === "Escape" || event.key === "Tab") {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); }
    closeBoards(event.key === "Escape");
  }
});
document.addEventListener("pointerdown", (event) => {
  if (boardsOpen() && !$("boards").contains(event.target)) closeBoards(false);
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
  if (state.board && !["games", "studio", "canvas"].includes(state.view)) { todayStatsAt = 0; render(); }
}

function remaining() {
  const t = state.timer;
  if (!t) return 0;
  return t.running ? Math.max(0, t.remaining - (Date.now() - state.timerAt) / 1000) : t.remaining;
}

// A running clock counts whole seconds that have passed (format() rounds up for countdowns).
function clockText(seconds) {
  const s = Math.floor(Math.max(0, seconds));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
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
$("helpButton").addEventListener("click", () => $("help").classList.toggle("on"));
$("help").addEventListener("click", (event) => { if (event.target === $("help")) $("help").classList.remove("on"); });
for (const button of $("tabs").children) button.addEventListener("click", () => setView(button.dataset.view));

// ---- canvas: JSON Canvas cards and edges plus our own drawn elements ----
// The pure helpers (geometry, hit-testing, rough strokes, edits, history) come first so the tests can call them.
// Photoshop-style keys (letters by physical key, so they work in any layout): the first one is shown in tooltips,
// the rest are aliases; Shift+U cycles the shape tools like Photoshop's tool groups.
const CV_TOOLS = { select: "vm", hand: "h", card: "n", text: "t", thread: "k", rectangle: "ur", ellipse: "o", diamond: "", line: "l", arrow: "a", freedraw: "bp", fill: "g", eraser: "e" };
const CV_LABELS = { select: "Select", hand: "Hand", card: "Card", text: "Text", thread: "Thread", rectangle: "Rectangle", ellipse: "Ellipse", diamond: "Diamond", line: "Line", arrow: "Arrow", freedraw: "Brush", fill: "Fill", eraser: "Eraser" };
const CV_BY_KEY = Object.fromEntries(Object.entries(CV_TOOLS).flatMap(([tool, keys]) => [...keys].map((key) => [key, tool])));
const CV_SHAPE_CYCLE = ["rectangle", "ellipse", "diamond", "line", "arrow"];
// 24x24 outline icons (stroke = currentColor), built with createElementNS, never innerHTML.
const CV_ICONS = {
  select: "M5 3l6.5 17.5 2.6-7.4 7.4-2.6z",
  hand: "M8 12.5V5.5a1.5 1.5 0 0 1 3 0V11 M11 10.5v-6a1.5 1.5 0 0 1 3 0V11 M14 10.5V6.5a1.5 1.5 0 0 1 3 0V14a6 6 0 0 1-6 6h-.6a6 6 0 0 1-4.7-2.3L3.8 13.6a1.6 1.6 0 0 1 2.5-2L8 13.6",
  card: "M4 4h16v11l-5 5H4z M15 20v-5h5 M8 9h8 M8 12.5h5",
  text: "M5 7V4h14v3 M12 4v16 M9 20h6",
  thread: "M3.5 6.5a2 2 0 1 0 4 0a2 2 0 1 0-4 0 M16.5 17.5a2 2 0 1 0 4 0a2 2 0 1 0-4 0 M7 8c3 9 7 2 10 8",
  audio: "M9 18V5l12-2v13 M3 18a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M15 16a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  trash: "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v5 M14 11v5",
  gallery: "M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z",
  close: "M6 6l12 12 M18 6L6 18",
  chevron: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  star: "M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z",
  back: "M15 18l-6-6 6-6",
  edit: "M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17z M14 7l3 3",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  layers: "M12 3l9 5-9 5-9-5z M3 12.5l9 5 9-5 M3 16.5l9 5 9-5",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  eyeOff: "M3 3l18 18 M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.1 3.9 M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7a10 10 0 0 0 5.4-1.6 M9.9 9.9a3 3 0 0 0 4.2 4.2",
  rectangle: "M4 6h16v12H4z",
  ellipse: "M3 12a9 7 0 1 0 18 0a9 7 0 1 0-18 0",
  diamond: "M12 3l9 9-9 9-9-9z",
  line: "M5 19L19 5",
  arrow: "M5 19L19 5 M10 5h9v9",
  freedraw: "M4 20l4-1L19 8a2.1 2.1 0 0 0-3-3L5 16z M14 7l3 3",
  fill: "M11 3l8 8-7 7-8-8z M4 10h15 M20 15.5s1.8 2.2 1.8 3.2a1.8 1.8 0 0 1-3.6 0c0-1 1.8-3.2 1.8-3.2z",
  eraser: "M7 20h13 M3.8 15.8L13.5 6a2 2 0 0 1 2.9 0l2.6 2.6a2 2 0 0 1 0 2.9L11.5 19H7z M9 10.5l5.5 5.5",
  filled: "M4 6h16v12H4z M4 10l4-4 M4 15l9-9 M7 18l12-12 M13 18l7-7",
  undo: "M9 14L4 9l5-5 M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  redo: "M15 14l5-5-5-5 M20 9H9.5a5.5 5.5 0 0 0 0 11H13",
  group: "M3 7V3h4 M17 3h4v4 M21 17v4h-4 M7 21H3v-4 M8 8h8v8H8z",
  fit: "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5",
  export: "M12 4v11 M7 10l5 5 5-5 M5 20h14",
  plus: "M12 5v14 M5 12h14",
  pin: "M9 3.5h6 M10 3.5l-.6 6L6.5 13h11l-2.9-3.5-.6-6 M12 13v8",
  attach: "M20.5 11.5l-8.4 8.4a5 5 0 0 1-7.1-7.1l8.4-8.4a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.4a1.7 1.7 0 0 1-2.4-2.4l7.7-7.7",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  erasePart: "M7 11a5 5 0 1 0 10 0a5 5 0 1 0-10 0 M3 20.5h18",
  rough3: "M5 5h14v14H5z",
  rough2: "M5 5.5c4.5-1 9 .8 14-.5 M19 5c-.9 4.6.8 9.2 0 14 M19.2 19c-4.8.8-9.4-1-14.2 0 M5 19c.8-4.6-.9-9.2 0-13.5",
  rough1: "M4.5 6c4-2.4 10 1.6 15-1.2 M18.6 4.2c-2 5.2 2.1 9.6-.3 15.3 M20 18.6c-5.3 2-10-1.8-15.6.4 M5.2 20c1.9-4.8-2.2-9.6.6-15.4",
};
const CV_INK = ["#1d1d1f", "#e5484d", "#f08c3a", "#e8b520", "#30a46c", "#3a6df0", "#8e4ec6", "#f2f2f5"];
const CV_MIN_WIDTH = 1, CV_MAX_WIDTH = 100;
// Evenness levels of the shape tools' menu: 3 is a perfect shape, 1 the roughest; the stored value is roughness.
const CV_ROUGH_LEVELS = [{ level: 3, rough: 0, label: "Perfect" }, { level: 2, rough: 1, label: "A little uneven" }, { level: 1, rough: 2, label: "More uneven" }];
const CV_ERASERS = [{ mode: "object", icon: "eraser", label: "Whole object" }, { mode: "part", icon: "erasePart", label: "Only where it passes" }];
const CV_FILL_TOLERANCE = 40;
const CV_PREFS = "desk-canvas-tools";
const CV_PRESETS = { "1": "#e5484d", "2": "#f08c3a", "3": "#e8b520", "4": "#30a46c", "5": "#2aa9bd", "6": "#8e4ec6" };
const CV_FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif';
const CV_MONO = '"SF Mono", ui-monospace, Menlo, monospace';
const CV_HAND = '"Bradley Hand", "Marker Felt", "Comic Sans MS", cursive';
const CV_MIN_ZOOM = 0.1, CV_MAX_ZOOM = 4, CV_HISTORY = 100, CV_MIN_BOX = 8;
const CV_SIDES = { top: [0, -1], right: [1, 0], bottom: [0, 1], left: [-1, 0] };
const CV_SIDE_NAMES = Object.keys(CV_SIDES);
const CV_SHAPES = new Set(["rectangle", "ellipse", "diamond", "line", "arrow", "freedraw", "text", "paint"]);
const CV_HEX = /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/;

// Detective board look (unlaw.look = "cork"): cork, paper notes, photos and red thread between push pins.
const CV_CORK = { light: "#b8875a", dark: "#5e4128" };
const CV_PAPER = "#fff1a6";
const CV_THREAD = "#c1121f";
const CV_PINS = ["#d62828", "#1d6fd8", "#2b9348", "#f4a300", "#7b2cbf", "#e5e5e5"];
const CV_IMAGE_FILE = /\.(png|jpe?g|gif|webp|ico)$/i;
const CV_CANVAS_FILE = /\.canvas$/i;
// Quick Look draws plain text as dark text on a dark page when macOS is in dark mode: these stay a paper sheet.
const CV_PLAIN_FILE = /\.(txt|text|log|csv|tsv|json|jsonl|ya?ml|toml|ini|cfg|conf|xml|html?|css|js|mjs|cjs|ts|tsx|jsx|py|rs|c|h|cc|cpp|hpp|m|swift|go|java|kt|rb|php|sh|zsh|bash|fish|sql|lua|r|jl|tex|srt|vtt)$/i;
const CV_MAX_UPLOAD = 256 * 1024 * 1024;
const CV_PLAYED = "#f5a524";
const cvNum = (value, fallback) => (typeof value === "number" && Number.isFinite(value) ? value : fallback);
const cvClone = (value) => JSON.parse(JSON.stringify(value));
const cvId = () => Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
const cvSeed = () => Math.floor(Math.random() * 2147483647);
const cvBackground = (doc) => (doc && doc.unlaw && typeof doc.unlaw.background === "string" && CV_HEX.test(doc.unlaw.background) ? doc.unlaw.background : null);

function nodeColor(color) {
  if (typeof color !== "string") return null;
  if (Object.prototype.hasOwnProperty.call(CV_PRESETS, color)) return CV_PRESETS[color];
  return CV_HEX.test(color) ? color : null;
}

function luminance(color) {
  if (typeof color !== "string" || !CV_HEX.test(color)) return null;
  let hex = color.slice(1);
  if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Stored ink never changes with the theme; only what is painted does, so near-black stays visible on dark.
function adaptInk(color, dark) {
  const light = luminance(color);
  if (light === null) return dark ? "#ececee" : "#1d1d1f";
  if (dark && light < 0.18) return "#ececee";
  if (!dark && light > 0.88) return "#1d1d1f";
  return color;
}

function noteName(file) {
  return typeof file === "string" && /\.md$/i.test(file) ? file.split("/").pop().replace(/\.md$/i, "") : null;
}

// Small seeded PRNG (mulberry32): the same seed always draws the same wobble.
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- detective board geometry: a tilt per card from its id, one pin per card, thread from pin to pin ----
const cvCork = (doc) => Boolean(doc && doc.unlaw && typeof doc.unlaw === "object" && doc.unlaw.look === "cork");
function setLook(doc, cork) {
  if (cvCork(doc) === cork) return false;
  if (cork) { ensureElements(doc); doc.unlaw.look = "cork"; } else delete doc.unlaw.look;
  return true;
}
// FNV-1a of the id as 0..1, so a card keeps its tilt and pin color on every redraw and machine.
function idHash(id, salt) {
  let h = 0x811c9dc5;
  for (const ch of String(salt || "") + String(id)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  return h / 4294967296;
}
const nodeTilt = (node) => (node.type === "group" ? 0 : (idHash(node.id) * 2 - 1) * 0.045);
const pinColor = (node) => CV_PINS[Math.floor(idHash(node.id, "pin") * CV_PINS.length)];
// A point of a card given as fractions of its unrotated box ([0.5, 0.5] = the middle), turned with the card's
// tilt on the detective board, so a pin stays on the same spot of the paper.
function anchorPoint(node, frac, tilted) {
  const tilt = tilted ? nodeTilt(node) : 0, dx = (frac[0] - 0.5) * node.width, dy = (frac[1] - 0.5) * node.height;
  return { x: node.x + node.width / 2 + Math.cos(tilt) * dx - Math.sin(tilt) * dy, y: node.y + node.height / 2 + Math.sin(tilt) * dx + Math.cos(tilt) * dy };
}
// The inverse of anchorPoint, clamped to the card.
function fracAt(node, w, tilted) {
  const tilt = tilted ? nodeTilt(node) : 0, x = w.x - (node.x + node.width / 2), y = w.y - (node.y + node.height / 2);
  const lx = Math.cos(tilt) * x + Math.sin(tilt) * y, ly = -Math.sin(tilt) * x + Math.cos(tilt) * y;
  const part = (v, size) => Math.round(Math.max(0, Math.min(1, v / (size || 1) + 0.5)) * 10000) / 10000;
  return [part(lx, node.width), part(ly, node.height)];
}
// An edge end tied to a spot of its card (the thread tool or a dragged end): unlawFrom/unlawTo, [fx, fy] in 0..1.
// Obsidian does not know the keys and keeps using fromSide/toSide, which are set to the nearest side.
function edgeAnchor(edge, end) {
  const value = edge && edge[end === "to" ? "unlawTo" : "unlawFrom"];
  return Array.isArray(value) && value.length === 2 && value.every((n) => Number.isFinite(n) && n >= 0 && n <= 1) ? value : null;
}
function pinPoint(node, frac) {
  if (frac) return anchorPoint(node, frac, true);
  const tilt = nodeTilt(node), dy = -node.height / 2 + Math.min(14, node.height / 4);
  return { x: node.x + node.width / 2 - Math.sin(tilt) * dy, y: node.y + node.height / 2 + Math.cos(tilt) * dy };
}
// The thread hangs: a quadratic sag written as a cubic, so hit-testing and labels use the edge code as is.
function threadCurve(a, b, fa, fb) {
  return sagCurve(pinPoint(a, fa), pinPoint(b, fb));
}
function sagCurve(p0, p3) {
  const length = Math.hypot(p3.x - p0.x, p3.y - p0.y);
  const q = { x: (p0.x + p3.x) / 2, y: (p0.y + p3.y) / 2 + Math.min(90, 10 + length * 0.12) };
  return { p0, c1: { x: p0.x + (2 / 3) * (q.x - p0.x), y: p0.y + (2 / 3) * (q.y - p0.y) }, c2: { x: p3.x + (2 / 3) * (q.x - p3.x), y: p3.y + (2 / 3) * (q.y - p3.y) }, p3 };
}
function mixColor(color, other, amount) {
  const parse = (c) => { let hex = c.slice(1); if (hex.length === 3) hex = hex.split("").map((x) => x + x).join(""); return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)); };
  if (!CV_HEX.test(color) || !CV_HEX.test(other)) return color;
  const a = parse(color), b = parse(other);
  return "#" + a.map((v, i) => Math.round(v + (b[i] - v) * amount).toString(16).padStart(2, "0")).join("");
}
const fileExtension = (file) => { const m = /\.([A-Za-z0-9]{1,8})$/.exec(String(file || "")); return m ? m[1].toUpperCase() : "FILE"; };
// A new file card: photos keep their proportions (a frame of 10 px and a 40 px caption around them).
function fileCardSize(image) {
  if (!image || !(image.w > 0) || !(image.h > 0)) return { width: 220, height: 280 };
  const width = 280, photo = Math.max(100, Math.min(460, ((width - 20) * image.h) / image.w));
  return { width, height: Math.round(photo + 50) };
}

// ---- view transforms: screen = world * z + (x, y) ----
const toScreen = (view, x, y) => ({ x: x * view.z + view.x, y: y * view.z + view.y });
const toWorld = (view, x, y) => ({ x: (x - view.x) / view.z, y: (y - view.y) / view.z });
const clampZoom = (z) => Math.min(CV_MAX_ZOOM, Math.max(CV_MIN_ZOOM, z));

function zoomAt(view, sx, sy, factor) {
  const z = clampZoom(view.z * factor);
  const k = z / view.z;
  return { x: sx - (sx - view.x) * k, y: sy - (sy - view.y) * k, z };
}

function fitView(bounds, width, height, pad = 60) {
  if (!bounds) return { x: width / 2, y: height / 2, z: 1 };
  const z = Math.min(1.5, clampZoom(Math.min((width - 2 * pad) / Math.max(1, bounds.width), (height - 2 * pad) / Math.max(1, bounds.height))));
  return { x: width / 2 - (bounds.x + bounds.width / 2) * z, y: height / 2 - (bounds.y + bounds.height / 2) * z, z };
}

// ---- boxes and distances ----
function normRect(x0, y0, x1, y1) {
  return { x: Math.min(x0, x1), y: Math.min(y0, y1), width: Math.abs(x1 - x0), height: Math.abs(y1 - y0) };
}
function rectsIntersect(a, b) {
  return a.x <= b.x + b.width && b.x <= a.x + a.width && a.y <= b.y + b.height && b.y <= a.y + a.height;
}
function boxContains(box, x, y, pad = 0) {
  return x >= box.x - pad && x <= box.x + box.width + pad && y >= box.y - pad && y <= box.y + box.height + pad;
}
function boxInside(inner, outer) {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;
}
function unionBox(boxes) {
  if (!boxes.length) return null;
  const x0 = Math.min(...boxes.map((b) => b.x)), y0 = Math.min(...boxes.map((b) => b.y));
  const x1 = Math.max(...boxes.map((b) => b.x + b.width)), y1 = Math.max(...boxes.map((b) => b.y + b.height));
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}
function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
function polyDist(pts, x, y, closed) {
  if (!pts.length) return Infinity;
  if (pts.length === 1) return Math.hypot(x - pts[0][0], y - pts[0][1]);
  let best = Infinity;
  const count = closed ? pts.length : pts.length - 1;
  for (let i = 0; i < count; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    best = Math.min(best, segDist(x, y, a[0], a[1], b[0], b[1]));
  }
  return best;
}
function pointInPoly(pts, x, y) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// ---- document access: lists are read defensively, but the raw objects are what gets saved ----
function cvList(doc, kind) {
  const list = kind === "n" ? doc.nodes : kind === "e" ? doc.edges : doc.unlaw && doc.unlaw.elements;
  return Array.isArray(list) ? list : [];
}
function cvLookup(doc, key) {
  const id = key.slice(2);
  return cvList(doc, key[0]).find((item) => item && item.id === id) || null;
}
const cvKey = (kind, item) => kind + ":" + item.id;
function validBox(item) {
  return Boolean(item) && typeof item === "object" && typeof item.id === "string" && Number.isFinite(item.x) && Number.isFinite(item.y) && Number.isFinite(item.width) && Number.isFinite(item.height);
}
// unlawHidden (the eye in Layers) takes a card, group or drawing out of painting and picking; `all` keeps them.
const cvHidden = (item) => Boolean(item && item.unlawHidden === true);
const docNodes = (doc, all) => cvList(doc, "n").filter((n) => validBox(n) && (all || !cvHidden(n)));
const docElements = (doc, all) => cvList(doc, "x").filter((el) => validBox(el) && CV_SHAPES.has(el.type) && (all || !cvHidden(el)));
const docEdges = (doc) => cvList(doc, "e").filter((e) => e && typeof e === "object" && typeof e.id === "string" && typeof e.fromNode === "string" && typeof e.toNode === "string");
function ensureList(doc, name) {
  if (!Array.isArray(doc[name])) doc[name] = [];
  return doc[name];
}
function ensureElements(doc) {
  if (!doc.unlaw || typeof doc.unlaw !== "object" || Array.isArray(doc.unlaw)) doc.unlaw = {};
  if (doc.unlaw.version === undefined) doc.unlaw.version = 1;
  return ensureList(doc.unlaw, "elements");
}
function sceneBounds(doc) {
  const boxes = [...docNodes(doc), ...docElements(doc)].map((item) => {
    const pad = (cvNum(item.strokeWidth, 0) || 0) / 2;
    const lift = item.type === "group" ? 28 : 0;
    return { x: item.x - pad, y: item.y - pad - lift, width: item.width + 2 * pad, height: item.height + 2 * pad + lift };
  });
  return unionBox(boxes);
}

// ---- elements: outline, hit-test, rough strokes ----
function elementPoints(el) {
  if (!Array.isArray(el.points)) return [];
  return el.points.filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])).map((p) => [el.x + p[0], el.y + p[1]]);
}

function elementOutline(el) {
  const { x, y, width, height } = el;
  if (el.type === "diamond") return [[x + width / 2, y], [x + width, y + height / 2], [x + width / 2, y + height], [x, y + height / 2]];
  if (el.type === "ellipse") {
    const out = [];
    for (let i = 0; i < 48; i++) {
      const a = (i / 48) * Math.PI * 2;
      out.push([x + width / 2 + (width / 2) * Math.cos(a), y + height / 2 + (height / 2) * Math.sin(a)]);
    }
    return out;
  }
  return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]];
}

// A world point in the element's own unrotated frame.
function localPoint(el, x, y) {
  if (!el.angle) return { x, y };
  const cx = el.x + el.width / 2, cy = el.y + el.height / 2, cos = Math.cos(-el.angle), sin = Math.sin(-el.angle);
  const dx = x - cx, dy = y - cy;
  return { x: cx + dx * cos - dy * sin, y: cy + dx * sin + dy * cos };
}

// Shapes and pen strokes that end near their start enclose an area the fill tool can paint.
function fillable(el) {
  if (el.type === "rectangle" || el.type === "ellipse" || el.type === "diamond") return true;
  if (el.type !== "freedraw") return false;
  const pts = elementPoints(el);
  if (pts.length < 3) return false;
  const [a, b] = [pts[0], pts[pts.length - 1]];
  return Math.hypot(b[0] - a[0], b[1] - a[1]) <= Math.max(12, 0.25 * Math.max(el.width, el.height));
}
const fillOutline = (el) => (el.type === "freedraw" ? elementPoints(el) : elementOutline(el));

// A paint element is an area left by the fill tool: an outer ring plus holes, filled even-odd.
function paintRings(el) {
  const rel = (ring) => (Array.isArray(ring) ? ring.filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])).map((p) => [el.x + p[0], el.y + p[1]]) : []);
  return [rel(el.points), ...(Array.isArray(el.holes) ? el.holes.map(rel) : [])].filter((ring) => ring.length >= 3);
}
function paintContains(el, x, y) {
  let inside = false;
  for (const ring of paintRings(el)) if (pointInPoly(ring, x, y)) inside = !inside;
  return inside;
}

function hitElement(el, x, y, tol) {
  ({ x, y } = localPoint(el, x, y));
  if (el.type === "text") return boxContains(el, x, y, tol);
  if (el.type === "paint") return paintContains(el, x, y);
  const reach = tol + cvNum(el.strokeWidth, 2) / 2;
  if (el.fill && fillable(el) && pointInPoly(fillOutline(el), x, y)) return true;
  if (el.type === "line" || el.type === "arrow" || el.type === "freedraw") return polyDist(elementPoints(el), x, y, false) <= reach;
  return polyDist(elementOutline(el), x, y, true) <= reach;
}

function hitGroup(node, x, y, tol) {
  if (boxContains({ x: node.x, y: node.y - 26, width: Math.min(node.width, 220), height: 26 }, x, y)) return true;
  const roomy = node.width > 2 * tol && node.height > 2 * tol;
  return boxContains(node, x, y, tol) && !(roomy && boxContains(node, x, y, -tol));
}

// ---- edges: a cubic curve leaving each node through a side ----
function sideAnchor(box, side) {
  if (side === "top") return { x: box.x + box.width / 2, y: box.y };
  if (side === "bottom") return { x: box.x + box.width / 2, y: box.y + box.height };
  if (side === "left") return { x: box.x, y: box.y + box.height / 2 };
  return { x: box.x + box.width, y: box.y + box.height / 2 };
}
function nearestSide(box, x, y) {
  const dx = (x - (box.x + box.width / 2)) / (box.width / 2 || 1), dy = (y - (box.y + box.height / 2)) / (box.height / 2 || 1);
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? "right" : "left";
  return dy > 0 ? "bottom" : "top";
}
function edgeCurve(a, sideA, b, sideB, p0 = sideAnchor(a, sideA), p3 = sideAnchor(b, sideB)) {
  const reach = Math.max(40, Math.min(200, Math.hypot(p3.x - p0.x, p3.y - p0.y) / 2));
  const v0 = CV_SIDES[sideA], v1 = CV_SIDES[sideB];
  return { p0, c1: { x: p0.x + v0[0] * reach, y: p0.y + v0[1] * reach }, c2: { x: p3.x + v1[0] * reach, y: p3.y + v1[1] * reach }, p3 };
}
function bezierPoint(c, t) {
  const u = 1 - t;
  const f = (a, b, d, e) => u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * d + t * t * t * e;
  return { x: f(c.p0.x, c.c1.x, c.c2.x, c.p3.x), y: f(c.p0.y, c.c1.y, c.c2.y, c.p3.y) };
}
function hitEdge(curve, x, y, tol) {
  const pts = [];
  for (let i = 0; i <= 32; i++) { const p = bezierPoint(curve, i / 32); pts.push([p.x, p.y]); }
  return polyDist(pts, x, y, false) <= tol + 1;
}
function edgeCurveFor(map, edge, cork) {
  const a = map.get(edge.fromNode), b = map.get(edge.toNode);
  if (!a || !b) return null;
  const fa = edgeAnchor(edge, "from"), fb = edgeAnchor(edge, "to");
  if (cork) return threadCurve(a, b, fa, fb);
  const ca = { x: a.x + a.width / 2, y: a.y + a.height / 2 }, cb = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  const p0 = fa ? anchorPoint(a, fa, false) : undefined, p3 = fb ? anchorPoint(b, fb, false) : undefined;
  const from = p0 ? nearestSide(a, p0.x, p0.y) : CV_SIDE_NAMES.includes(edge.fromSide) ? edge.fromSide : nearestSide(a, cb.x, cb.y);
  const to = p3 ? nearestSide(b, p3.x, p3.y) : CV_SIDE_NAMES.includes(edge.toSide) ? edge.toSide : nearestSide(b, ca.x, ca.y);
  return edgeCurve(a, from, b, to, p0, p3);
}
const nodeMap = (doc) => new Map(docNodes(doc).map((n) => [n.id, n]));

// Topmost thing at a world point: drawings, cards, edges, then groups (only their label and border).
function hitTest(doc, x, y, zoom) {
  const tol = 6 / (zoom || 1);
  const elements = docElements(doc), nodes = docNodes(doc);
  for (let i = elements.length - 1; i >= 0; i--) if (hitElement(elements[i], x, y, tol)) return cvKey("x", elements[i]);
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], x, y)) return cvKey("n", nodes[i]);
  const map = nodeMap(doc);
  for (const edge of docEdges(doc).reverse()) {
    const curve = edgeCurveFor(map, edge, cvCork(doc));
    if (curve && hitEdge(curve, x, y, tol)) return cvKey("e", edge);
  }
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type === "group" && hitGroup(nodes[i], x, y, tol)) return cvKey("n", nodes[i]);
  return null;
}

// What the fill tool paints at a world point: like hitTest, but the inside of an unfilled closed shape counts
// (after any drawing seen through it) and a click anywhere in a group colors the group. null = the empty background.
function fillTarget(doc, x, y, zoom) {
  const tol = 6 / (zoom || 1);
  const elements = docElements(doc), nodes = docNodes(doc);
  let hollow = null;
  for (let i = elements.length - 1; i >= 0; i--) {
    const el = elements[i], local = localPoint(el, x, y);
    if (hitElement(el, x, y, tol)) return cvKey("x", el);
    if (!hollow && fillable(el) && pointInPoly(fillOutline(el), local.x, local.y)) hollow = cvKey("x", el);
  }
  if (hollow) return hollow;
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], x, y)) return cvKey("n", nodes[i]);
  const map = nodeMap(doc);
  for (const edge of docEdges(doc).reverse()) {
    const curve = edgeCurveFor(map, edge, cvCork(doc));
    if (curve && hitEdge(curve, x, y, tol)) return cvKey("e", edge);
  }
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type === "group" && (boxContains(nodes[i], x, y) || hitGroup(nodes[i], x, y, tol))) return cvKey("n", nodes[i]);
  return null;
}

// The fill tool: enclosed areas get a fill, cards, groups and edges a color, open strokes and text a new ink.
// color null clears a fill or a card color (open strokes keep their ink). Returns whether anything changed.
function applyFill(doc, key, color) {
  const item = cvLookup(doc, key);
  if (!item) return false;
  if (key[0] === "x") {
    if (item.type === "paint") {
      if (color === null) return removeItems(doc, [key]) > 0;
      if (item.fill === color && item.stroke === color) return false;
      item.fill = color;
      item.stroke = color;
      return true;
    }
    if (fillable(item)) {
      if ((item.fill || null) === color) return false;
      item.fill = color;
    } else {
      if (color === null || item.stroke === color) return false;
      item.stroke = color;
    }
    return true;
  }
  if (color === null) {
    if (!("color" in item)) return false;
    delete item.color;
    return true;
  }
  if (item.color === color) return false;
  item.color = color;
  return true;
}

function setBackground(doc, color) {
  if (cvBackground(doc) === color) return false;
  if (color === null) {
    if (!doc.unlaw || typeof doc.unlaw !== "object") return false;
    delete doc.unlaw.background;
    return true;
  }
  ensureElements(doc);
  doc.unlaw.background = color;
  return true;
}

// Two slightly different passes per shape, wobble drawn from the element's own seed.
function roughLine(rng, a, b, rough) {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const amp = rough * Math.min(2.2, 0.6 + len / 150);
  const jitter = () => (rng() - 0.5) * 2 * amp;
  const nx = len ? -(b[1] - a[1]) / len : 0, ny = len ? (b[0] - a[0]) / len : 0;
  const bow = jitter();
  return [
    [a[0] + jitter(), a[1] + jitter()],
    [(a[0] + b[0]) / 2 + nx * bow + jitter() * 0.4, (a[1] + b[1]) / 2 + ny * bow + jitter() * 0.4],
    [b[0] + jitter(), b[1] + jitter()],
  ];
}

function roughStrokes(el) {
  if (!CV_SHAPES.has(el.type) || el.type === "text" || el.type === "paint") return [];
  const rough = Math.max(0, Math.min(2, cvNum(el.roughness, 1)));
  const rng = mulberry32(cvNum(el.seed, 1));
  const passes = rough > 0 ? 2 : 1;
  const out = [];
  if (el.type === "freedraw") {
    const pts = elementPoints(el);
    return pts.length ? [{ pts, smooth: true }] : [];
  }
  if (el.type === "line" || el.type === "arrow") {
    const pts = elementPoints(el);
    if (pts.length < 2) return pts.length ? [{ pts, smooth: false }] : [];
    for (let pass = 0; pass < passes; pass++) {
      if (!rough) { out.push({ pts, smooth: false }); continue; }
      const stroke = [];
      for (let i = 0; i < pts.length - 1; i++) {
        const seg = roughLine(rng, pts[i], pts[i + 1], rough);
        stroke.push(...(i ? seg.slice(1) : seg));
      }
      out.push({ pts: stroke, smooth: true });
    }
    return out;
  }
  const outline = elementOutline(el);
  for (let pass = 0; pass < passes; pass++) {
    if (!rough) { out.push({ pts: [...outline, outline[0]], smooth: false }); continue; }
    if (el.type === "ellipse") {
      const amp = rough * Math.min(2.2, 0.6 + (el.width + el.height) / 300), start = rng() * Math.PI * 2, steps = 40;
      const pts = [];
      for (let i = 0; i <= steps; i++) {
        const a = start + (i / steps) * Math.PI * 2;
        pts.push([el.x + el.width / 2 + (el.width / 2 + (rng() - 0.5) * 2 * amp) * Math.cos(a), el.y + el.height / 2 + (el.height / 2 + (rng() - 0.5) * 2 * amp) * Math.sin(a)]);
      }
      out.push({ pts, smooth: true });
      continue;
    }
    for (let i = 0; i < outline.length; i++) out.push({ pts: roughLine(rng, outline[i], outline[(i + 1) % outline.length], rough), smooth: true });
  }
  return out;
}

function arrowHead(from, to, size) {
  const angle = Math.atan2(to[1] - from[1], to[0] - from[0]);
  return [-0.45, 0.45].map((turn) => [to[0] - size * Math.cos(angle + turn), to[1] - size * Math.sin(angle + turn)]);
}

// ---- fill tool: flood the clicked color on a rendered snapshot, keep the area as a paint element ----
// Pixels connected (4-way) to (sx, sy) whose RGBA stays within tol of it; touches = the area reaches the image edge.
function floodRegion(data, w, h, sx, sy, tol) {
  const mask = new Uint8Array(w * h), start = sy * w + sx, k0 = start * 4;
  const r0 = data[k0], g0 = data[k0 + 1], b0 = data[k0 + 2], a0 = data[k0 + 3];
  const same = (i) => {
    const k = i * 4;
    return Math.abs(data[k] - r0) <= tol && Math.abs(data[k + 1] - g0) <= tol && Math.abs(data[k + 2] - b0) <= tol && Math.abs(data[k + 3] - a0) <= tol;
  };
  const stack = [start];
  mask[start] = 1;
  let touches = false, count = 0;
  while (stack.length) {
    const i = stack.pop(), x = i % w, y = (i - x) / w;
    count++;
    if (x === 0 || y === 0 || x === w - 1 || y === h - 1) touches = true;
    if (x > 0 && !mask[i - 1] && same(i - 1)) { mask[i - 1] = 1; stack.push(i - 1); }
    if (x < w - 1 && !mask[i + 1] && same(i + 1)) { mask[i + 1] = 1; stack.push(i + 1); }
    if (y > 0 && !mask[i - w] && same(i - w)) { mask[i - w] = 1; stack.push(i - w); }
    if (y < h - 1 && !mask[i + w] && same(i + w)) { mask[i + w] = 1; stack.push(i + w); }
  }
  return { mask, touches, count };
}

// One pixel wider on every side, so the area slips under antialiased edges instead of leaving a light seam.
function growMask(mask, w, h) {
  const out = new Uint8Array(mask);
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue;
    const x = i % w;
    if (x > 0) out[i - 1] = 1;
    if (x < w - 1) out[i + 1] = 1;
    if (i >= w) out[i - w] = 1;
    if (i < mask.length - w) out[i + w] = 1;
  }
  return out;
}

// Closed rings of pixel corners around a mask (outer border and holes). Where two pixels touch only at a corner
// the walk turns right, around the pixel it came along. Even-odd filling only needs the set of edges anyway.
function traceMask(mask, w, h) {
  const W = w + 1, next = new Map();
  const add = (x0, y0, x1, y1) => {
    const key = y0 * W + x0;
    if (!next.has(key)) next.set(key, []);
    next.get(key).push([x1, y1]);
  };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (!mask[i]) continue;
      if (y === 0 || !mask[i - w]) add(x, y, x + 1, y);
      if (x === w - 1 || !mask[i + 1]) add(x + 1, y, x + 1, y + 1);
      if (y === h - 1 || !mask[i + w]) add(x + 1, y + 1, x, y + 1);
      if (x === 0 || !mask[i - 1]) add(x, y + 1, x, y);
    }
  }
  const rings = [];
  for (const [key, list] of next) {
    while (list.length) {
      const sx = key % W, sy = (key - sx) / W, ring = [[sx, sy]];
      let px = sx, py = sy, [cx, cy] = list.pop();
      while (cx !== sx || cy !== sy) {
        ring.push([cx, cy]);
        const out = next.get(cy * W + cx);
        if (!out || !out.length) break;
        let pick = 0;
        if (out.length > 1) {
          const dx = cx - px, dy = cy - py;
          pick = Math.max(0, out.findIndex(([nx, ny]) => dx * (ny - cy) - dy * (nx - cx) > 0));
        }
        const [nx, ny] = out.splice(pick, 1)[0];
        px = cx; py = cy; cx = nx; cy = ny;
      }
      rings.push(ring);
    }
  }
  return rings;
}

function ringArea(ring) {
  let sum = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) sum += (ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1]);
  return Math.abs(sum) / 2;
}

// Douglas-Peucker on a closed ring: the pixel staircase becomes straight and diagonal runs.
function simplifyRing(ring, eps) {
  const n = ring.length;
  const pts = ring.filter((p, i) => {
    const a = ring[(i - 1 + n) % n], b = ring[(i + 1) % n];
    return (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0]) !== 0;
  });
  if (pts.length < 4) return pts;
  let far = 0, best = -1;
  pts.forEach((p, i) => { const d = Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]); if (d > best) { best = d; far = i; } });
  const rdp = (line) => {
    const keep = new Uint8Array(line.length);
    keep[0] = keep[line.length - 1] = 1;
    const stack = [[0, line.length - 1]];
    while (stack.length) {
      const [a, b] = stack.pop();
      let index = -1, dist = eps;
      for (let i = a + 1; i < b; i++) {
        const d = segDist(line[i][0], line[i][1], line[a][0], line[a][1], line[b][0], line[b][1]);
        if (d > dist) { dist = d; index = i; }
      }
      if (index >= 0) { keep[index] = 1; stack.push([a, index], [index, b]); }
    }
    return line.filter((_, i) => keep[i]);
  };
  return [...rdp(pts.slice(0, far + 1)).slice(0, -1), ...rdp([...pts.slice(far), pts[0]]).slice(0, -1)];
}

// The flooded area as a paint element in world units: rings from a snapshot drawn at view with scale k.
function paintFromMask(mask, w, h, view, k, color) {
  const traced = traceMask(mask, w, h);
  let rings = [];
  for (let eps = 0.8; eps <= 13; eps *= 2) {
    rings = traced.map((ring) => simplifyRing(ring, eps)).filter((ring) => ring.length >= 3 && ringArea(ring) >= 2);
    if (rings.reduce((sum, ring) => sum + ring.length, 0) <= 40000) break;
  }
  if (!rings.length) return null;
  const round = (v) => Math.round(v * 100) / 100;
  const world = rings.map((ring) => ring.map(([px, py]) => { const p = toWorld(view, px / k, py / k); return [p.x, p.y]; }));
  world.sort((a, b) => ringArea(b) - ringArea(a));
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const ring of world) for (const [x, y] of ring) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const rel = (ring) => ring.map(([x, y]) => [round(x - x0), round(y - y0)]);
  return { id: cvId(), type: "paint", x: round(x0), y: round(y0), width: round(x1 - x0), height: round(y1 - y0), points: rel(world[0]), holes: world.slice(1).map(rel), stroke: color, fill: color, strokeWidth: 1 };
}

// Whether a world point lies on an element's ink (its line or text), not inside its area.
function onInk(el, x, y, tol) {
  ({ x, y } = localPoint(el, x, y));
  if (el.type === "text") return boxContains(el, x, y, tol);
  if (el.type === "paint") return false;
  const reach = tol + cvNum(el.strokeWidth, 2) / 2;
  if (el.type === "line" || el.type === "arrow" || el.type === "freedraw") return polyDist(elementPoints(el), x, y, false) <= reach;
  return polyDist(elementOutline(el), x, y, true) <= reach;
}

// ---- partial eraser: cut drawn lines where a round eraser passes ----
// The element's drawn strokes in world units (rotation applied); a rough shape keeps its wobble.
function elementStrokes(el) {
  if (el.type === "text" || el.type === "paint" || !CV_SHAPES.has(el.type)) return [];
  const strokes = roughStrokes(el).filter((stroke) => stroke.pts.length);
  if (!el.angle) return strokes;
  const cx = el.x + el.width / 2, cy = el.y + el.height / 2, cos = Math.cos(el.angle), sin = Math.sin(el.angle);
  const turn = ([x, y]) => [cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos];
  return strokes.map((stroke) => ({ ...stroke, pts: stroke.pts.map(turn) }));
}

function pieceOf(el, pts, type, smooth) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const piece = cvClone(el);
  delete piece.angle;
  delete piece.holes;
  return Object.assign(piece, {
    id: cvId(), type, x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: null,
    points: pts.map(([x, y]) => [Math.round((x - x0) * 100) / 100, Math.round((y - y0) * 100) / 100]),
    roughness: type === "freedraw" && smooth ? cvNum(el.roughness, 1) : 0,
  });
}

// What is left of el after a round eraser of radius r at (x, y): null when untouched, else the pieces (maybe none).
// Shapes turn into line pieces; a filled shape keeps its fill as a paint area under them.
function cutElement(el, x, y, r) {
  const reach = r + cvNum(el.strokeWidth, 2) / 2, step = Math.max(0.5, reach / 4);
  const strokes = elementStrokes(el);
  if (!strokes.some((stroke) => polyDist(stroke.pts, x, y, false) <= reach)) return null;
  const pieces = [];
  let cut = false;
  strokes.forEach((stroke, n) => {
    const dense = [];
    stroke.pts.forEach((p, i) => {
      if (i) {
        const a = stroke.pts[i - 1];
        if (segDist(x, y, a[0], a[1], p[0], p[1]) <= reach + step) {
          const parts = Math.min(4000, Math.ceil(Math.hypot(p[0] - a[0], p[1] - a[1]) / step));
          for (let k = 1; k < parts; k++) dense.push([a[0] + ((p[0] - a[0]) * k) / parts, a[1] + ((p[1] - a[1]) * k) / parts]);
        }
      }
      dense.push(p);
    });
    const runs = [];
    let run = [];
    for (const p of dense) {
      if (Math.hypot(p[0] - x, p[1] - y) > reach) { run.push(p); continue; }
      cut = true;
      if (run.length) runs.push(run);
      run = [];
    }
    if (run.length) runs.push(run);
    const closed = dense.length > 2 && dense[0][0] === dense[dense.length - 1][0] && dense[0][1] === dense[dense.length - 1][1];
    if (closed && runs.length > 1 && runs[0][0] === dense[0] && runs[runs.length - 1].at(-1) === dense[dense.length - 1]) {
      runs[0] = [...runs.pop(), ...runs[0].slice(1)];
    }
    const lastPoint = dense[dense.length - 1];
    for (const part of runs) {
      if (part.length < 2) continue;
      if (el.type === "freedraw") { pieces.push(pieceOf(el, part, "freedraw", true)); continue; }
      const head = el.type === "arrow" && n === 0 && part[part.length - 1] === lastPoint;
      pieces.push(pieceOf(el, part, head ? "arrow" : stroke.smooth ? "freedraw" : "line", stroke.smooth));
    }
  });
  if (!cut) return null;
  if (el.fill && fillable(el)) {
    const area = elementStrokes({ ...el, roughness: 0 });
    const outline = el.type === "freedraw" ? area[0].pts : area[0].pts.slice(0, -1);
    const paint = pieceOf(el, outline, "paint", false);
    Object.assign(paint, { fill: el.fill, stroke: el.fill, strokeWidth: 1, holes: [] });
    delete paint.roughness;
    pieces.unshift(paint);
  }
  return pieces;
}

// Cuts every element the eraser touches at (x, y); returns how many changed.
function eraseAt(doc, x, y, r) {
  const list = doc.unlaw && Array.isArray(doc.unlaw.elements) ? doc.unlaw.elements : null;
  if (!list) return 0;
  let changed = 0;
  for (let i = list.length - 1; i >= 0; i--) {
    const el = list[i];
    if (!validBox(el) || !CV_SHAPES.has(el.type)) continue;
    // The pad covers half the stroke and the wobble of rough shapes, which can leave the box by a few units.
    if (!el.angle && !boxContains(el, x, y, r + cvNum(el.strokeWidth, 2) + 8)) continue;
    const pieces = cutElement(el, x, y, r);
    if (!pieces) continue;
    list.splice(i, 1, ...pieces);
    changed++;
  }
  return changed;
}

// ---- resize ----
function resizeBox(box, handle, dx, dy) {
  let x0 = box.x, y0 = box.y, x1 = box.x + box.width, y1 = box.y + box.height;
  if (handle.includes("w")) x0 = Math.min(x0 + dx, x1 - CV_MIN_BOX); else x1 = Math.max(x1 + dx, x0 + CV_MIN_BOX);
  if (handle.includes("n")) y0 = Math.min(y0 + dy, y1 - CV_MIN_BOX); else y1 = Math.max(y1 + dy, y0 + CV_MIN_BOX);
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}
function handleAt(box, sx, sy, view, radius = 8) {
  const corners = { nw: [box.x, box.y], ne: [box.x + box.width, box.y], sw: [box.x, box.y + box.height], se: [box.x + box.width, box.y + box.height] };
  for (const [name, [x, y]] of Object.entries(corners)) {
    const p = toScreen(view, x, y);
    if (Math.hypot(p.x - sx, p.y - sy) <= radius) return name;
  }
  return null;
}
// Sets the box on item from the copy taken when the drag began, scaling points and font with it.
function applyBox(item, orig, box) {
  item.x = box.x; item.y = box.y; item.width = box.width; item.height = box.height;
  if (Array.isArray(orig.points)) {
    const kx = orig.width ? box.width / orig.width : 1, ky = orig.height ? box.height / orig.height : 1;
    item.points = orig.points.map((p) => (Array.isArray(p) ? [p[0] * kx, p[1] * ky] : p));
    if (Array.isArray(orig.holes)) item.holes = orig.holes.map((ring) => (Array.isArray(ring) ? ring.map((p) => (Array.isArray(p) ? [p[0] * kx, p[1] * ky] : p)) : ring));
  }
  if (typeof orig.fontSize === "number" && orig.height > 0) item.fontSize = Math.max(8, Math.min(200, Math.round(orig.fontSize * box.height / orig.height)));
}

// ---- text ----
function wrapText(measure, text, maxWidth) {
  const lines = [];
  for (const paragraph of String(text).split("\n")) {
    let line = "";
    for (const word of paragraph.split(" ")) {
      const trial = line ? line + " " + word : word;
      if (measure(trial) <= maxWidth) { line = trial; continue; }
      if (line) lines.push(line);
      let rest = word;
      while (measure(rest) > maxWidth && rest.length > 1) {
        let n = rest.length - 1;
        while (n > 1 && measure(rest.slice(0, n)) > maxWidth) n--;
        lines.push(rest.slice(0, n));
        rest = rest.slice(n);
      }
      line = rest;
    }
    lines.push(line);
  }
  return lines;
}

// ---- creating shapes ----
function cvStyleFields(style, closed) {
  return { stroke: style.stroke, fill: closed && style.fill ? style.stroke : null, strokeWidth: style.width, roughness: style.rough };
}
function makeShape(type, x0, y0, x1, y1, style, seed) {
  const box = normRect(x0, y0, x1, y1);
  return { id: cvId(), type, x: box.x, y: box.y, width: box.width, height: box.height, ...cvStyleFields(style, true), seed };
}
function makeLinear(type, x0, y0, x1, y1, style, seed) {
  const x = Math.min(x0, x1), y = Math.min(y0, y1);
  return { id: cvId(), type, x, y, width: Math.abs(x1 - x0), height: Math.abs(y1 - y0), points: [[x0 - x, y0 - y], [x1 - x, y1 - y]], ...cvStyleFields(style, false), seed };
}
function makeFreedraw(points, style, seed) {
  const x = Math.min(...points.map((p) => p[0])), y = Math.min(...points.map((p) => p[1]));
  const width = Math.max(...points.map((p) => p[0])) - x, height = Math.max(...points.map((p) => p[1])) - y;
  return { id: cvId(), type: "freedraw", x, y, width, height, points: points.map((p) => [p[0] - x, p[1] - y]), ...cvStyleFields(style, false), seed };
}
function snapAngle(dx, dy) {
  const len = Math.hypot(dx, dy);
  const step = Math.PI / 4, angle = Math.round(Math.atan2(dy, dx) / step) * step;
  return { dx: len * Math.cos(angle), dy: len * Math.sin(angle) };
}

// ---- edits: all of them mutate the loaded objects, so keys the page does not know survive ----
function applyStyle(doc, keys, patch) {
  for (const key of keys) {
    const item = cvLookup(doc, key);
    if (!item) continue;
    if (key[0] === "x") {
      if (patch.stroke !== undefined && patch.fill === undefined && item.fill && item.fill === item.stroke) item.fill = patch.stroke;
      if (patch.stroke !== undefined) item.stroke = patch.stroke;
      if (patch.fill !== undefined) item.fill = patch.fill;
      if (patch.strokeWidth !== undefined) item.strokeWidth = patch.strokeWidth;
      if (patch.roughness !== undefined) item.roughness = patch.roughness;
    } else if (patch.stroke !== undefined) {
      item.color = patch.stroke;
    }
  }
}
function moveItems(doc, keys, dx, dy) {
  for (const key of keys) {
    if (key[0] === "e") continue;
    const item = cvLookup(doc, key);
    if (!item) continue;
    item.x += dx;
    item.y += dy;
  }
}
function containedIds(doc, group) {
  const keys = [];
  for (const node of docNodes(doc, true)) if (node.id !== group.id && boxInside(node, group)) keys.push(cvKey("n", node));
  for (const el of docElements(doc, true)) if (boxInside(el, group)) keys.push(cvKey("x", el));
  return keys;
}
function groupAround(doc, keys, id) {
  const box = unionBox(keys.filter((k) => k[0] !== "e").map((k) => cvLookup(doc, k)).filter(validBox));
  if (!box) return null;
  const pad = 24;
  ensureList(doc, "nodes").unshift({ id, type: "group", label: "Group", x: box.x - pad, y: box.y - pad, width: box.width + 2 * pad, height: box.height + 2 * pad });
  return "n:" + id;
}
function removeItems(doc, keys) {
  const gone = { n: new Set(), e: new Set(), x: new Set() };
  for (const key of keys) if (gone[key[0]]) gone[key[0]].add(key.slice(2));
  let count = 0;
  const keep = (kind, list) => list.filter((item) => {
    const drop = Boolean(item) && gone[kind].has(item.id);
    if (drop) count++;
    return !drop;
  });
  if (Array.isArray(doc.nodes)) doc.nodes = keep("n", doc.nodes);
  if (Array.isArray(doc.edges)) {
    doc.edges = keep("e", doc.edges).filter((e) => !e || (!gone.n.has(e.fromNode) && !gone.n.has(e.toNode)));
  }
  if (doc.unlaw && Array.isArray(doc.unlaw.elements)) doc.unlaw.elements = keep("x", doc.unlaw.elements);
  return count;
}
function copyItems(doc, keys) {
  const nodes = [], elements = [];
  for (const key of keys) {
    const item = cvLookup(doc, key);
    if (!item) continue;
    if (key[0] === "n") nodes.push(cvClone(item));
    else if (key[0] === "x") elements.push(cvClone(item));
  }
  const ids = new Set(nodes.map((n) => n.id));
  const edges = cvList(doc, "e").filter((e) => e && ids.has(e.fromNode) && ids.has(e.toNode)).map(cvClone);
  return { nodes, edges, elements };
}
function pasteItems(doc, bundle, offset, newId) {
  const ids = new Map(), keys = [];
  for (const node of bundle.nodes) {
    const copy = cvClone(node);
    copy.id = newId();
    ids.set(node.id, copy.id);
    copy.x += offset;
    copy.y += offset;
    ensureList(doc, "nodes").push(copy);
    keys.push("n:" + copy.id);
  }
  for (const edge of bundle.edges) {
    const copy = cvClone(edge);
    copy.id = newId();
    copy.fromNode = ids.get(edge.fromNode);
    copy.toNode = ids.get(edge.toNode);
    ensureList(doc, "edges").push(copy);
    keys.push("e:" + copy.id);
  }
  for (const el of bundle.elements) {
    const copy = cvClone(el);
    copy.id = newId();
    copy.x += offset;
    copy.y += offset;
    ensureElements(doc).push(copy);
    keys.push("x:" + copy.id);
  }
  return keys;
}

// ---- history: JSON snapshots of the whole document ----
function makeHistory(cap, snapshot) { return { cap, cur: snapshot, undo: [], redo: [] }; }
function histCommit(hist, snapshot, merge) {
  if (snapshot === hist.cur) return false;
  if (!merge || !hist.undo.length) {
    hist.undo.push(hist.cur);
    if (hist.undo.length > hist.cap) hist.undo.shift();
  }
  hist.redo = [];
  hist.cur = snapshot;
  return true;
}
function histUndo(hist) {
  if (!hist.undo.length) return null;
  hist.redo.push(hist.cur);
  hist.cur = hist.undo.pop();
  return hist.cur;
}
function histRedo(hist) {
  if (!hist.redo.length) return null;
  hist.undo.push(hist.cur);
  hist.cur = hist.redo.pop();
  return hist.cur;
}

// ---- canvas state, loading and saving ----
const cv = {
  path: "", name: "", version: "", doc: null, items: [], tool: "select", view: { x: 0, y: 0, z: 1 }, sel: [],
  style: { stroke: CV_INK[0], fill: false, width: 4, rough: 1 }, hist: null, drag: null, editing: null, space: false,
  dirty: false, saving: null, saveTimer: 0, clip: null, pasted: 0, hover: null, pointer: null, lastLabel: "", lastAt: 0,
  drawPending: false, el: null, ctx: null, w: 0, h: 0, dpr: 1, ui: {}, gesture: 1, eraser: "object", cursor: null, menu: "",
  thread: null, threadAt: null, layers: false, gallery: false, viewing: null, pasteWait: 0,
  back: [], shelf: { favorites: [], groups: [] }, gallerySearch: "", playing: null, inline: null, clickTimer: 0, folded: null, ticking: false, galleryDrag: null,
};

// The eraser mode, shape evenness and width are remembered in this browser.
function cvLoadPrefs() {
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem(CV_PREFS) || "{}") || {}; } catch { prefs = {}; }
  if (CV_ERASERS.some((e) => e.mode === prefs.eraser)) cv.eraser = prefs.eraser;
  if (CV_ROUGH_LEVELS.some((l) => l.rough === prefs.rough)) cv.style.rough = prefs.rough;
  if (Number.isInteger(prefs.width) && prefs.width >= CV_MIN_WIDTH && prefs.width <= CV_MAX_WIDTH) cv.style.width = prefs.width;
}
function cvSavePrefs() {
  try { localStorage.setItem(CV_PREFS, JSON.stringify({ eraser: cv.eraser, rough: cv.style.rough, width: cv.style.width })); } catch { /* private mode: not remembered */ }
}
cvLoadPrefs();

function cvLoad(shape) {
  if (shape.path !== cv.path) { cvStopMedia(); cvCloseInline(); cvCanvasThumbs.clear(); }
  cv.path = shape.path;
  cv.name = shape.name || "";
  cv.version = shape.version;
  const doc = shape.canvas && typeof shape.canvas === "object" && !Array.isArray(shape.canvas) ? shape.canvas : {};
  ensureList(doc, "nodes");
  ensureList(doc, "edges");
  const linked = doc.nodes.filter((node) => textToLink(node)).length;
  cv.doc = doc;
  cv.hist = makeHistory(CV_HISTORY, JSON.stringify(doc));
  cv.sel = cv.sel.filter((key) => cvLookup(doc, key));
  cv.drag = null;
  cv.hover = null;
  cv.dirty = false;
  cv.lastLabel = "";
  clearTimeout(cv.saveTimer);
  cv.saveTimer = 0;
  cvStatus("Saved");
  cvSync();
  cvDraw();
  if (linked) cvChanged(); // written back, so Obsidian sees link cards too
}

function cvStatus(text) {
  if (cv.ui.status) cv.ui.status.textContent = text;
}

function cvChanged() {
  cv.dirty = true;
  cvStatus("Unsaved");
  clearTimeout(cv.saveTimer);
  cv.saveTimer = setTimeout(saveCanvas, 800);
  cvSync();
  cvDraw();
}

// Records the document as one undo step; repeated edits with the same label inside 700 ms (arrow-key nudges) share a step.
function cvCommit(label) {
  const now = Date.now();
  const merge = Boolean(label) && label === cv.lastLabel && now - cv.lastAt < 700;
  cv.lastLabel = label || "";
  cv.lastAt = now;
  if (histCommit(cv.hist, JSON.stringify(cv.doc), merge)) cvChanged();
}

function cvRestore(snapshot) {
  cv.doc = JSON.parse(snapshot);
  cv.sel = cv.sel.filter((key) => cvLookup(cv.doc, key));
  cv.lastLabel = "";
  cvChanged();
}
function cvUndo() { const snapshot = histUndo(cv.hist); if (snapshot !== null) cvRestore(snapshot); }
function cvRedo() { const snapshot = histRedo(cv.hist); if (snapshot !== null) cvRestore(snapshot); }

async function sendCanvas() {
  const sent = cv.hist.cur;
  cvStatus("Saving…");
  const { status, data } = await api("POST", "/api/canvas", { path: cv.path, version: cv.version, canvas: cv.doc });
  if (status === 200) {
    if (typeof data.version === "string") cv.version = data.version;
    if (cv.hist.cur === sent) { cv.dirty = false; cvStatus("Saved"); }
    else cv.saveTimer = setTimeout(saveCanvas, 800);
  } else if (status === 409 && data.canvas) {
    cvLoad(data.canvas);
    toast("Canvas changed elsewhere; reloaded");
  } else {
    cvStatus("Save failed");
    toast(data.error || "Could not save the canvas");
    cv.saveTimer = setTimeout(saveCanvas, 4000);
  }
}

async function saveCanvas() {
  clearTimeout(cv.saveTimer);
  cv.saveTimer = 0;
  while (cv.saving) await cv.saving;
  if (!cv.doc || !cv.dirty) return;
  // A drag or an open editor holds changes that are not an undo step yet; they are never written half-done.
  if (cv.drag || cv.editing) { cv.saveTimer = setTimeout(saveCanvas, 300); return; }
  cv.saving = sendCanvas();
  try { await cv.saving; } finally { cv.saving = null; }
}

async function pollCanvas() {
  const idle = () => state.view === "canvas" && !document.hidden && cv.doc && !cv.drag && !cv.editing && !cv.saving && !cv.dirty;
  if (!idle()) return;
  const path = cv.path;
  const { status, data } = await api("GET", "/api/canvas?path=" + encodeURIComponent(path));
  if (status !== 200 || path !== cv.path || !idle()) return;
  if (data.version !== cv.version) { cvLoad(data); toast("Canvas updated from the file"); }
}

async function loadCanvasList() {
  const { status, data } = await api("GET", "/api/canvases");
  if (status !== 200) { toast(data.error || "Could not list the canvases"); return null; }
  cv.items = Array.isArray(data.items) ? data.items : [];
  cv.shelf = cleanShelf(data.shelf);
  cvFillPick();
  return data;
}

async function cvShow(data) {
  cvLoad(data);
  localStorage.setItem("desk-canvas", data.path);
  cvFit();
  await loadCanvasList();
}

async function cvOpen(path, create) {
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvases", { path, create });
  if (status !== 200) { toast(data.error || "Could not open the canvas"); cvFillPick(); return false; }
  await cvShow(data);
  return true;
}

// New canvas = the next free canvas-N in the canvas folder, opened at once; rename it in the name field.
async function cvNew() {
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvas/new", {});
  if (status !== 200) { toast(data.error || "Could not create a canvas"); return; }
  await cvShow(data);
}

// "Open…" shows the macOS open dialog (through the server); without it the page asks for a path.
async function cvChoose() {
  const { status, data } = await api("POST", "/api/canvas/choose", {});
  if (status !== 200) { toast(data.error || "Could not show the file dialog"); return; }
  if (data.unavailable) {
    const answer = prompt("Path or name of the canvas to open");
    if (answer && answer.trim()) await cvOpen(answer.trim(), false);
  } else if (data.path) {
    await cvOpen(data.path, false);
  }
}

async function cvRename(raw) {
  const field = cv.ui.name, name = String(raw || "").trim();
  if (!cv.path || !name || name === cv.name) { if (field) field.value = cv.name; return; }
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvas/rename", { path: cv.path, name });
  if (status !== 200) { toast(data.error || "Could not rename the canvas"); if (cv.ui.name) cv.ui.name.value = cv.name; return; }
  cv.path = data.path;
  cv.name = data.name;
  if (typeof data.version === "string" && !cv.dirty) cv.version = data.version;
  localStorage.setItem("desk-canvas", data.path);
  await loadCanvasList();
}

async function cvStart() {
  const list = await loadCanvasList();
  if (!list) return;
  let target = null;
  const read = async (query) => { const { status, data } = await api("GET", "/api/canvas" + query); return status === 200 ? data : null; };
  if (cv.path) target = await read("?path=" + encodeURIComponent(cv.path));
  if (!target && list.current) target = await read("");
  if (!target) {
    const remembered = localStorage.getItem("desk-canvas");
    const item = cv.items.find((i) => i.path === remembered) || cv.items[0];
    if (item) target = await read("?path=" + encodeURIComponent(item.path));
  }
  if (state.view !== "canvas" || !cv.el) return;
  if (target) {
    const fresh = target.path !== cv.path;
    cvLoad(target);
    if (fresh) cvFit();
  }
  cvFillPick();
  cvSync();
}

function leaveCanvas() {
  cvCancelDrag();
  cvEndEdit();
  cvCloseView();
  cvStopMedia();
  cvCloseInline();
  clearTimeout(cv.clickTimer);
  cv.gallery = false;
  cv.layerDrag = null;
  cv.thread = null;
  saveCanvas();
  cv.el = null;
  cv.ctx = null;
  cv.ui = {};
  cv.space = false;
}

// ---- painting ----
function cvPalette() {
  const css = getComputedStyle(document.documentElement);
  const get = (name) => css.getPropertyValue(name).trim();
  return { dark: document.documentElement.dataset.theme === "dark", bg: get("--bg"), panel: get("--panel"), text: get("--text"), muted: get("--muted"), line: get("--line"), accent: get("--accent-ink"), soft: get("--accent-soft") };
}

function roundPath(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function strokePath(ctx, stroke) {
  const pts = stroke.pts;
  if (!pts.length) return;
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  if (!stroke.smooth || pts.length < 3) {
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  } else {
    for (let i = 1; i < pts.length - 1; i++) ctx.quadraticCurveTo(pts[i][0], pts[i][1], (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2);
    ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
  }
  ctx.stroke();
}

function fillTriangle(ctx, tip, angle, size) {
  ctx.beginPath();
  ctx.moveTo(tip.x, tip.y);
  ctx.lineTo(tip.x - size * Math.cos(angle - 0.45), tip.y - size * Math.sin(angle - 0.45));
  ctx.lineTo(tip.x - size * Math.cos(angle + 0.45), tip.y - size * Math.sin(angle + 0.45));
  ctx.closePath();
  ctx.fill();
}

function paintElement(ctx, el, pal, hideText) {
  const ink = adaptInk(el.stroke, pal.dark);
  ctx.save();
  if (el.angle) {
    ctx.translate(el.x + el.width / 2, el.y + el.height / 2);
    ctx.rotate(el.angle);
    ctx.translate(-(el.x + el.width / 2), -(el.y + el.height / 2));
  }
  if (el.type === "text") {
    const size = Math.max(8, Math.min(200, cvNum(el.fontSize, 24)));
    if (!hideText) {
      ctx.font = size + "px " + CV_HAND;
      ctx.textBaseline = "top";
      ctx.fillStyle = ink;
      String(el.text || "").split("\n").forEach((line, i) => ctx.fillText(line, el.x, el.y + i * size * 1.25));
    }
    ctx.restore();
    return;
  }
  if (el.type === "paint") {
    ctx.beginPath();
    for (const ring of paintRings(el)) ring.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.fillStyle = adaptInk(typeof el.fill === "string" ? el.fill : el.stroke, pal.dark);
    ctx.fill("evenodd");
    ctx.restore();
    return;
  }
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = ink;
  ctx.lineWidth = Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, cvNum(el.strokeWidth, 2)));
  if (el.fill && fillable(el)) {
    ctx.fillStyle = adaptInk(el.fill, pal.dark);
    strokePathFill(ctx, fillOutline(el));
  }
  for (const stroke of roughStrokes(el)) strokePath(ctx, stroke);
  if (el.type === "arrow") {
    const pts = elementPoints(el);
    if (pts.length >= 2) {
      const size = 12 + ctx.lineWidth * 2;
      const [a, b] = arrowHead(pts[pts.length - 2], pts[pts.length - 1], size);
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
    }
  }
  ctx.restore();
}

function strokePathFill(ctx, outline) {
  ctx.beginPath();
  outline.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
  ctx.closePath();
  ctx.fill();
}

function paintLines(ctx, node, lines, font, color, lineHeight, cursor) {
  ctx.font = font;
  ctx.fillStyle = color;
  for (const line of lines) {
    ctx.fillText(line, node.x + 12, cursor.y);
    cursor.y += lineHeight;
  }
}

function paintNode(ctx, node, pal, hideText, image) {
  const color = nodeColor(node.color);
  ctx.save();
  roundPath(ctx, node.x, node.y, node.width, node.height, 8);
  ctx.fillStyle = pal.panel;
  ctx.fill();
  if (color) { ctx.globalAlpha = 0.14; ctx.fillStyle = color; ctx.fill(); ctx.globalAlpha = 1; }
  ctx.lineWidth = color ? 2 : 1.5;
  ctx.strokeStyle = color || pal.line;
  ctx.stroke();
  if (image && node.height > 60 && node.type !== "link") {
    // A picture fills the card above a one-line caption.
    ctx.save();
    roundPath(ctx, node.x + 5, node.y + 5, node.width - 10, node.height - 38, 5);
    ctx.clip();
    drawCover(ctx, image, { x: node.x + 5, y: node.y + 5, width: node.width - 10, height: node.height - 38 }, !CV_IMAGE_FILE.test(String(node.file ?? "")));
    ctx.restore();
    if (!hideText) {
      ctx.font = "600 13px " + CV_FONT;
      ctx.textBaseline = "middle";
      ctx.fillStyle = pal.text;
      ctx.fillText(fileLabel(node.file), node.x + 10, node.y + node.height - 17, Math.max(10, node.width - 20));
    }
  } else if (!hideText) {
    ctx.beginPath();
    ctx.rect(node.x + 4, node.y + 4, node.width - 8, node.height - 8);
    ctx.clip();
    ctx.textBaseline = "top";
    const cursor = { y: node.y + 12 }, room = Math.max(10, node.width - 24);
    const wrapped = (text, font) => { ctx.font = font; return wrapText((s) => ctx.measureText(s).width, String(text).slice(0, 4000), room); };
    if (node.type === "text") {
      paintLines(ctx, node, wrapped(node.text ?? "", "15px " + CV_FONT), "15px " + CV_FONT, pal.text, 21, cursor);
    } else if (node.type === "file") {
      const file = String(node.file ?? "");
      paintLines(ctx, node, ["File"], "11px " + CV_FONT, pal.muted, 16, cursor);
      paintLines(ctx, node, wrapped(file.split("/").pop(), "600 15px " + CV_FONT), "600 15px " + CV_FONT, pal.text, 21, cursor);
      if (file.includes("/")) paintLines(ctx, node, wrapped(file, "12px " + CV_FONT), "12px " + CV_FONT, pal.muted, 17, cursor);
    } else if (node.type === "link") {
      // The site's logo on top, then the page's title and the address.
      const preview = node.unlawPreview && typeof node.unlawPreview === "object" ? node.unlawPreview : null;
      const size = Math.min(72, node.height - 96, node.width - 40);
      if (size >= 24) { paintSiteLogo(ctx, image, node.x + node.width / 2, cursor.y + 2, size, pal, linkSite(node)); cursor.y += size + 14; }
      if (preview && preview.title) paintLines(ctx, node, wrapped(String(preview.title), "600 15px " + CV_FONT), "600 15px " + CV_FONT, pal.text, 21, cursor);
      paintLines(ctx, node, wrapped(node.url ?? "", "13px " + CV_MONO), "13px " + CV_MONO, pal.accent, 18, cursor);
      if (preview && preview.description) paintLines(ctx, node, wrapped(String(preview.description), "13px " + CV_FONT), "13px " + CV_FONT, pal.muted, 18, cursor);
    } else {
      paintLines(ctx, node, [String(node.type)], "12px " + CV_FONT, pal.muted, 16, cursor);
    }
  }
  ctx.restore();
}

// A logo in a rounded white square (icons are often transparent), or the site's first letter when it has none.
function paintSiteLogo(ctx, image, cx, top, size, pal, site) {
  const x = cx - size / 2;
  ctx.save();
  roundPath(ctx, x, top, size, size, size * 0.22);
  if (image) {
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.clip();
    const pad = size * 0.1;
    drawCover(ctx, image, { x: x + pad, y: top + pad, width: size - pad * 2, height: size - pad * 2 }, true);
  } else {
    ctx.fillStyle = pal.accent;
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "700 " + Math.round(size * 0.5) + "px " + CV_FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText((String(site || "").replace(/^www\./, "")[0] || "?").toUpperCase(), cx, top + size / 2 + 1);
  }
  ctx.restore();
}

function linkSite(node) {
  const preview = node.unlawPreview;
  if (preview && typeof preview === "object" && preview.site) return String(preview.site);
  const found = /^https?:\/\/([^/?#:]+)/i.exec(String(node.url ?? "").trim());
  return found ? found[1] : "";
}

// A file card's caption: the file name; a linked canvas without its .canvas.
function fileLabel(file) {
  return String(file ?? "").split("/").pop().replace(CV_CANVAS_FILE, "");
}

function linkTitle(node) {
  const preview = node.unlawPreview;
  return preview && typeof preview === "object" && preview.title ? String(preview.title) : String(node.url ?? "");
}

// Video, sound and 3D cards say so: a play button or a 3D tag over the card; a linked canvas gets a tag. A card that
// plays (media from cvMediaState) shows its progress, a sound its wave.
function paintFileBadge(ctx, node, media, cork) {
  if (node.type !== "file" || node.width < 60 || node.height < 60) return;
  const kind = cvFileKind(node.file);
  if (kind === "canvas") { paintCanvasTag(ctx, node, cork); return; }
  if (kind !== "video" && kind !== "audio" && kind !== "model") return;
  if (media) paintMediaBar(ctx, node, media, cork);
  if (media && media.playing) return;
  const r = Math.min(24, node.width / 6, node.height / 6), x = node.x + node.width / 2, y = node.y + Math.max(r + 6, (node.height - 33) / 2 + 5);
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  if (kind === "model") {
    ctx.font = "700 " + Math.round(r * 0.8) + "px " + CV_FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("3D", x, y + 1);
  } else {
    ctx.beginPath();
    ctx.moveTo(x - r * 0.3, y - r * 0.45);
    ctx.lineTo(x + r * 0.5, y);
    ctx.lineTo(x - r * 0.3, y + r * 0.45);
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();
}

// The picture area of a file card (where a photo, a video frame or a PDF page is), unrotated.
function cvPictureBox(node, cork) {
  return cork
    ? { x: node.x + 10, y: node.y + 10, width: node.width - 20, height: Math.max(10, node.height - 50) }
    : { x: node.x + 5, y: node.y + 5, width: node.width - 10, height: node.height - 38 };
}

function paintMediaBar(ctx, node, media, cork) {
  const draw = () => {
    const box = cvPictureBox(node, cork);
    if (box.width < 30 || box.height < 30) return;
    ctx.save();
    if (media.peaks && media.peaks.length) {
      const n = media.peaks.length, gap = box.width / n, tall = Math.min(56, box.height * 0.4), base = box.y + box.height - (media.idle ? 8 : 24);
      ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
      ctx.fillRect(box.x, base - tall - 6, box.width, tall + (media.idle ? 14 : 30));
      for (let i = 0; i < n; i++) {
        const tallness = Math.max(1.5, media.peaks[i] * tall);
        ctx.fillStyle = (i + 0.5) / n <= media.progress ? CV_PLAYED : "rgba(255, 255, 255, 0.8)";
        ctx.fillRect(box.x + i * gap + gap * 0.2, base - tallness, Math.max(1, gap * 0.6), tallness);
      }
    }
    if (!media.idle) {
      ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
      ctx.fillRect(box.x, box.y + box.height - 18, box.width, 18);
      ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
      ctx.fillRect(box.x + 8, box.y + box.height - 10, box.width - 16, 3);
      ctx.fillStyle = CV_PLAYED;
      ctx.fillRect(box.x + 8, box.y + box.height - 10, (box.width - 16) * media.progress, 3);
    }
    ctx.restore();
  };
  if (cork) tilted(ctx, node, draw); else draw();
}

function paintCanvasTag(ctx, node, cork) {
  const draw = () => {
    const box = cvPictureBox(node, cork);
    ctx.save();
    ctx.font = "700 11px " + CV_FONT;
    const label = "CANVAS \u2197", width = ctx.measureText(label).width + 14;
    roundPath(ctx, box.x + 6, box.y + 6, width, 20, 6);
    ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.textBaseline = "middle";
    ctx.fillText(label, box.x + 13, box.y + 16.5);
    ctx.restore();
  };
  if (cork) tilted(ctx, node, draw); else draw();
}

// ---- detective board painting ----
// Photos fill their frame (cropped); a document's preview is shown whole, so its page is never cut.
function drawCover(ctx, image, box, whole) {
  const iw = image.videoWidth || image.naturalWidth || image.width || 1, ih = image.videoHeight || image.naturalHeight || image.height || 1;
  if (whole) {
    const scale = Math.min(box.width / iw, box.height / ih), w = iw * scale, h = ih * scale;
    ctx.drawImage(image, box.x + (box.width - w) / 2, box.y + (box.height - h) / 2, w, h);
    return;
  }
  const scale = Math.max(box.width / iw, box.height / ih), sw = box.width / scale, sh = box.height / scale;
  ctx.drawImage(image, (iw - sw) / 2, (ih - sh) / 2, sw, sh, box.x, box.y, box.width, box.height);
}

// One speckled tile (seeded, so it never flickers), wrapped at the edges so it repeats without seams.
const corkTiles = {};
const corkPatterns = new WeakMap();
function corkPattern(ctx, dark) {
  const key = dark ? "dark" : "light";
  if (typeof ctx.createPattern !== "function") return null;
  let cached = corkPatterns.get(ctx);
  if (cached && cached.key === key) return cached.pattern;
  if (!corkTiles[key]) {
    const tile = document.createElement("canvas"), size = 160;
    const t = tile && typeof tile.getContext === "function" ? tile.getContext("2d") : null;
    if (!t) return null;
    tile.width = tile.height = size;
    const base = CV_CORK[key], random = mulberry32(7);
    t.fillStyle = base;
    t.fillRect(0, 0, size, size);
    for (let i = 0; i < 1500; i++) {
      const x = random() * size, y = random() * size, r = 0.4 + random() * 1.7, squash = 0.45 + random() * 0.6, turn = random() * Math.PI;
      t.globalAlpha = 0.15 + random() * 0.3;
      t.fillStyle = mixColor(base, random() < 0.45 ? "#f6dcaa" : "#24120a", 0.3 + random() * 0.45);
      for (const dx of [-size, 0, size]) for (const dy of [-size, 0, size]) {
        if (x + dx < -3 || x + dx > size + 3 || y + dy < -3 || y + dy > size + 3) continue;
        t.beginPath();
        t.ellipse(x + dx, y + dy, r, r * squash, turn, 0, Math.PI * 2);
        t.fill();
      }
    }
    t.globalAlpha = 1;
    corkTiles[key] = tile;
  }
  cached = { key, pattern: ctx.createPattern(corkTiles[key], "repeat") };
  corkPatterns.set(ctx, cached);
  return cached.pattern;
}

function tilted(ctx, node, draw) {
  const tilt = nodeTilt(node), cx = node.x + node.width / 2, cy = node.y + node.height / 2;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(tilt);
  ctx.translate(-cx, -cy);
  draw();
  ctx.restore();
}

function paperShadow(ctx, on) {
  ctx.shadowColor = on ? "rgba(30, 14, 0, 0.45)" : "rgba(0, 0, 0, 0)";
  ctx.shadowBlur = on ? 12 : 0;
  ctx.shadowOffsetX = on ? 3 : 0;
  ctx.shadowOffsetY = on ? 6 : 0;
}

// Paper with the bottom right corner lifted a little.
function paperPath(ctx, x, y, w, h, curl) {
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + w, y);
  ctx.lineTo(x + w, y + h - curl);
  ctx.quadraticCurveTo(x + w - curl * 0.15, y + h - curl * 0.15, x + w - curl, y + h);
  ctx.lineTo(x, y + h);
  ctx.closePath();
}

function paperFill(ctx, x, y, h, paper) {
  const shade = typeof ctx.createLinearGradient === "function" ? ctx.createLinearGradient(x, y, x, y + h) : null;
  if (shade && typeof shade.addColorStop === "function") {
    shade.addColorStop(0, paper);
    shade.addColorStop(1, mixColor(paper, "#000000", 0.08));
    ctx.fillStyle = shade;
  } else {
    ctx.fillStyle = paper;
  }
  ctx.fill();
}

function paperCurl(ctx, x, y, w, h, curl, paper) {
  ctx.beginPath();
  ctx.moveTo(x + w, y + h - curl);
  ctx.quadraticCurveTo(x + w - curl * 0.15, y + h - curl * 0.15, x + w - curl, y + h);
  ctx.lineTo(x + w - curl * 0.85, y + h - curl * 0.85);
  ctx.closePath();
  ctx.fillStyle = mixColor(paper, "#000000", 0.2);
  ctx.fill();
}

function handLines(ctx, node, text, top, size, color, centered) {
  const font = size + "px " + CV_HAND, room = Math.max(10, node.width - 28);
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textBaseline = "top";
  ctx.textAlign = centered ? "center" : "left";
  const lines = wrapText((s) => ctx.measureText(s).width, String(text).slice(0, 4000), room);
  let y = top;
  for (const line of lines) {
    if (y + size > node.y + node.height - 8) break;
    ctx.fillText(line, centered ? node.x + node.width / 2 : node.x + 14, y);
    y += size * 1.25;
  }
  ctx.textAlign = "left";
}

// A sticky note, a pinned photo (or document) or an index card for a link.
function paintCorkNode(ctx, node, pal, hideText, image) {
  const { x, y, width: w, height: h } = node, ink = "#2b2622";
  tilted(ctx, node, () => {
    if (node.type === "file") {
      const paper = "#fbf8f0", photo = { x: x + 10, y: y + 10, width: w - 20, height: Math.max(10, h - 50) };
      paperShadow(ctx, true);
      ctx.beginPath();
      ctx.rect(x, y, w, h);
      ctx.fillStyle = paper;
      ctx.fill();
      paperShadow(ctx, false);
      if (image) {
        const whole = !CV_IMAGE_FILE.test(String(node.file ?? ""));
        if (whole) { ctx.fillStyle = "#ece6d8"; ctx.fillRect(photo.x, photo.y, photo.width, photo.height); }
        drawCover(ctx, image, photo, whole);
      } else {
        ctx.fillStyle = "#ece6d8";
        ctx.fillRect(photo.x, photo.y, photo.width, photo.height);
        ctx.fillStyle = "#c9bfa9";
        for (let line = photo.y + 46; line < photo.y + photo.height - 10; line += 14) ctx.fillRect(photo.x + 14, line, Math.max(0, photo.width - 28) * (line % 3 ? 1 : 0.6), 3);
        const label = fileExtension(node.file);
        ctx.font = "700 15px " + CV_FONT;
        const badge = Math.min(photo.width - 20, ctx.measureText(label).width + 18);
        ctx.fillStyle = label === "PDF" ? "#c1121f" : /^DOCX?$|^PAGES$/.test(label) ? "#1d6fd8" : /^XLSX?$|^CSV$|^NUMBERS$/.test(label) ? "#2b9348" : "#6b5b45";
        ctx.fillRect(photo.x + 10, photo.y + 12, badge, 24);
        ctx.fillStyle = "#ffffff";
        ctx.textBaseline = "middle";
        ctx.fillText(label, photo.x + 19, photo.y + 24, badge - 18);
      }
      if (!hideText) {
        ctx.font = "16px " + CV_HAND;
        ctx.fillStyle = ink;
        ctx.textBaseline = "middle";
        ctx.textAlign = "center";
        ctx.fillText(fileLabel(node.file), x + w / 2, y + h - 20, Math.max(10, w - 20));
        ctx.textAlign = "left";
      }
      return;
    }
    if (node.type === "link") {
      paperShadow(ctx, true);
      ctx.beginPath();
      ctx.rect(x, y, w, h);
      ctx.fillStyle = "#fdfdf8";
      ctx.fill();
      paperShadow(ctx, false);
      ctx.fillStyle = "#e05a5a";
      ctx.fillRect(x, y + 30, w, 1.5);
      ctx.fillStyle = "#9cc3e6";
      for (let line = y + 52; line < y + h - 4; line += 22) ctx.fillRect(x, line, w, 1);
      const size = Math.min(56, h - 110, w - 40);
      if (size >= 24) paintSiteLogo(ctx, image, x + w / 2, y + 40, size, { accent: "#1d4f91" }, linkSite(node));
      if (!hideText) handLines(ctx, node, linkTitle(node) + (linkTitle(node) === String(node.url ?? "") ? "" : "\n" + String(node.url ?? "")), y + 36 + (size >= 24 ? size + 14 : 0), 16, "#1d4f91", false);
      return;
    }
    const color = nodeColor(node.color), paper = color ? mixColor(color, "#ffffff", 0.55) : CV_PAPER, curl = Math.min(22, w / 6, h / 6);
    paperShadow(ctx, true);
    paperPath(ctx, x, y, w, h, curl);
    paperFill(ctx, x, y, h, paper);
    paperShadow(ctx, false);
    paperCurl(ctx, x, y, w, h, curl, paper);
    // Text starts below the pin, where thread tied to it still passes.
    if (!hideText) handLines(ctx, node, node.type === "text" ? node.text ?? "" : String(node.type), y + 38, 19, ink, false);
  });
}

// The red thread: its shadow on the cork, a darker body, a lighter twist.
function paintThread(ctx, curve, edge, pal, selected, hideLabel) {
  const color = nodeColor(edge.color) || CV_THREAD;
  const path = (dx, dy) => {
    ctx.beginPath();
    ctx.moveTo(curve.p0.x + dx, curve.p0.y + dy);
    ctx.bezierCurveTo(curve.c1.x + dx, curve.c1.y + dy, curve.c2.x + dx, curve.c2.y + dy, curve.p3.x + dx, curve.p3.y + dy);
  };
  ctx.save();
  ctx.lineCap = "round";
  path(3, 6);
  ctx.strokeStyle = "rgba(30, 12, 0, 0.3)";
  ctx.lineWidth = 2.6;
  ctx.stroke();
  if (selected) {
    path(0, 0);
    ctx.strokeStyle = pal.accent;
    ctx.globalAlpha = 0.5;
    ctx.lineWidth = 8;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  path(0, 0);
  ctx.strokeStyle = mixColor(color, "#000000", 0.3);
  ctx.lineWidth = 2.8;
  ctx.stroke();
  path(0, 0);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.9;
  ctx.stroke();
  ctx.setLineDash([2, 4]);
  path(0, 0);
  ctx.strokeStyle = mixColor(color, "#ffffff", 0.4);
  ctx.lineWidth = 0.8;
  ctx.stroke();
  ctx.setLineDash([]);
  if (edge.label && !hideLabel) {
    // A paper tag hanging on the thread.
    const mid = bezierPoint(curve, 0.5), text = String(edge.label).slice(0, 120);
    ctx.font = "16px " + CV_HAND;
    const width = ctx.measureText(text).width + 18;
    ctx.translate(mid.x, mid.y);
    ctx.rotate((idHash(edge.id) * 2 - 1) * 0.06);
    paperShadow(ctx, true);
    ctx.fillStyle = "#f7f1e1";
    ctx.fillRect(-width / 2, -13, width, 26);
    paperShadow(ctx, false);
    ctx.fillStyle = "#2b2622";
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillText(text, 0, 1);
  }
  ctx.restore();
}

// A push pin seen from above: its shadow and needle on the cork, a round head with a cap.
function paintEndHandle(ctx, p, pal, z) {
  ctx.save();
  ctx.beginPath();
  ctx.arc(p.x, p.y, 5 / z, 0, Math.PI * 2);
  ctx.fillStyle = pal.panel || "#fff";
  ctx.fill();
  ctx.lineWidth = 2 / z;
  ctx.strokeStyle = pal.accent;
  ctx.stroke();
  ctx.restore();
}

// The thread tool between its first click and the second: a pin and thread (or a dashed line) to the pointer.
function paintThreadDraft(ctx, t, pal, cork, z) {
  ctx.save();
  if (cork) {
    const c = sagCurve(t.a, t.b);
    ctx.beginPath();
    ctx.moveTo(c.p0.x, c.p0.y);
    ctx.bezierCurveTo(c.c1.x, c.c1.y, c.c2.x, c.c2.y, c.p3.x, c.p3.y);
    ctx.strokeStyle = CV_THREAD;
    ctx.lineWidth = 2.4;
    ctx.stroke();
    ctx.restore();
    paintPin(ctx, t.a, CV_PINS[0]);
    return;
  }
  ctx.setLineDash([6 / z, 5 / z]);
  ctx.beginPath();
  ctx.moveTo(t.a.x, t.a.y);
  ctx.lineTo(t.b.x, t.b.y);
  ctx.strokeStyle = pal.accent;
  ctx.lineWidth = 2 / z;
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.arc(t.a.x, t.a.y, 4 / z, 0, Math.PI * 2);
  ctx.fillStyle = pal.accent;
  ctx.fill();
  ctx.restore();
}

function paintPin(ctx, p, color) {
  ctx.save();
  ctx.fillStyle = "rgba(25, 10, 0, 0.35)";
  ctx.beginPath();
  ctx.ellipse(p.x + 4, p.y + 6, 6.5, 5, 0.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(25, 10, 0, 0.4)";
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  ctx.moveTo(p.x, p.y);
  ctx.lineTo(p.x + 7, p.y + 9);
  ctx.stroke();
  const head = typeof ctx.createRadialGradient === "function" ? ctx.createRadialGradient(p.x - 2.5, p.y - 2.5, 0.5, p.x, p.y, 7.5) : null;
  if (head && typeof head.addColorStop === "function") {
    head.addColorStop(0, mixColor(color, "#ffffff", 0.65));
    head.addColorStop(0.45, color);
    head.addColorStop(1, mixColor(color, "#000000", 0.45));
    ctx.fillStyle = head;
  } else {
    ctx.fillStyle = color;
  }
  ctx.beginPath();
  ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = mixColor(color, "#ffffff", 0.25);
  ctx.beginPath();
  ctx.arc(p.x - 0.8, p.y - 0.8, 3.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
  ctx.beginPath();
  ctx.arc(p.x - 2.2, p.y - 2.4, 1.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function paintVignette(ctx, w, h) {
  if (typeof ctx.createRadialGradient !== "function") return;
  const shade = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.hypot(w, h) * 0.6);
  if (!shade || typeof shade.addColorStop !== "function") return;
  shade.addColorStop(0, "rgba(0, 0, 0, 0)");
  shade.addColorStop(1, "rgba(20, 8, 0, 0.32)");
  ctx.fillStyle = shade;
  ctx.fillRect(0, 0, w, h);
}

function paintGroup(ctx, node, pal, hideLabel) {
  const color = nodeColor(node.color) || pal.accent;
  ctx.save();
  roundPath(ctx, node.x, node.y, node.width, node.height, 12);
  ctx.globalAlpha = 0.06;
  ctx.fillStyle = color;
  ctx.fill();
  ctx.globalAlpha = 0.7;
  ctx.setLineDash([8, 6]);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = color;
  ctx.stroke();
  ctx.setLineDash([]);
  if (!hideLabel && node.label) {
    ctx.globalAlpha = 1;
    ctx.font = "600 13px " + CV_FONT;
    ctx.textBaseline = "bottom";
    ctx.fillStyle = pal.text;
    ctx.fillText(String(node.label).slice(0, 80), node.x + 4, node.y - 6, Math.max(20, node.width - 8));
  }
  ctx.restore();
}

function paintEdge(ctx, curve, edge, pal, selected, hideLabel) {
  const color = selected ? pal.accent : nodeColor(edge.color) || pal.muted;
  ctx.save();
  ctx.lineWidth = selected ? 3 : 2;
  ctx.lineCap = "round";
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(curve.p0.x, curve.p0.y);
  ctx.bezierCurveTo(curve.c1.x, curve.c1.y, curve.c2.x, curve.c2.y, curve.p3.x, curve.p3.y);
  ctx.stroke();
  const toward = (from, tip) => Math.atan2(tip.y - from.y, tip.x - from.x);
  if (edge.toEnd !== "none") fillTriangle(ctx, curve.p3, toward(curve.c2, curve.p3), 12);
  if (edge.fromEnd === "arrow") fillTriangle(ctx, curve.p0, toward(curve.c1, curve.p0), 12);
  if (edge.label && !hideLabel) {
    const mid = bezierPoint(curve, 0.5), text = String(edge.label).slice(0, 120);
    ctx.font = "13px " + CV_FONT;
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    const width = ctx.measureText(text).width + 12;
    ctx.fillStyle = pal.bg;
    roundPath(ctx, mid.x - width / 2, mid.y - 11, width, 22, 6);
    ctx.fill();
    ctx.fillStyle = pal.text;
    ctx.fillText(text, mid.x, mid.y);
  }
  ctx.restore();
}

function paintGrid(ctx, view, width, height, pal) {
  let step = 24 * view.z;
  if (step < 10) step *= 4;
  if (step < 10) return;
  ctx.fillStyle = pal.line;
  const x0 = ((view.x % step) + step) % step, y0 = ((view.y % step) + step) % step;
  for (let x = x0; x < width; x += step) for (let y = y0; y < height; y += step) ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
}

function singleBox(doc, sel) {
  if (sel.length !== 1 || sel[0][0] === "e") return null;
  const item = cvLookup(doc, sel[0]);
  return validBox(item) ? item : null;
}

function paintOverlay(o) {
  const { ctx, view, pal, ui, doc } = o;
  ctx.setTransform(o.scale, 0, 0, o.scale, 0, 0);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = pal.accent;
  for (const key of ui.sel) {
    const item = cvLookup(doc, key);
    if (key[0] === "e" || !validBox(item)) continue;
    const a = toScreen(view, item.x, item.y);
    ctx.setLineDash([5, 4]);
    ctx.strokeRect(a.x - 3, a.y - 3, item.width * view.z + 6, item.height * view.z + 6);
    ctx.setLineDash([]);
  }
  const solo = ui.tool === "select" && !ui.drag ? singleBox(doc, [...ui.sel]) : null;
  if (solo) {
    for (const [x, y] of [[solo.x, solo.y], [solo.x + solo.width, solo.y], [solo.x, solo.y + solo.height], [solo.x + solo.width, solo.y + solo.height]]) {
      const p = toScreen(view, x, y);
      ctx.fillStyle = pal.panel;
      ctx.fillRect(p.x - 4, p.y - 4, 8, 8);
      ctx.strokeRect(p.x - 4, p.y - 4, 8, 8);
    }
  }
  const handleKeys = ui.tool === "select" && (!ui.drag || ui.drag.mode === "connect") ? [ui.hover, ui.sel.size === 1 ? [...ui.sel][0] : null] : [];
  for (const key of new Set(handleKeys)) {
    const node = key && key[0] === "n" ? cvLookup(doc, key) : null;
    if (!validBox(node)) continue;
    for (const side of CV_SIDE_NAMES) {
      const anchor = sideAnchor(node, side), p = toScreen(view, anchor.x, anchor.y);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = pal.accent;
      ctx.fill();
    }
  }
  const drag = ui.drag;
  if (drag && drag.mode === "marquee" && drag.s2) {
    const box = normRect(drag.s.x, drag.s.y, drag.s2.x, drag.s2.y);
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = pal.accent;
    ctx.fillRect(box.x, box.y, box.width, box.height);
    ctx.globalAlpha = 1;
    ctx.strokeRect(box.x, box.y, box.width, box.height);
  }
  if (drag && drag.mode === "connect" && drag.s2) {
    const from = toScreen(view, sideAnchor(drag.from, drag.side).x, sideAnchor(drag.from, drag.side).y);
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(drag.s2.x, drag.s2.y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (ui.eraser) {
    ctx.setLineDash([]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = pal.muted;
    ctx.beginPath();
    ctx.arc(ui.eraser.x, ui.eraser.y, Math.max(2, ui.eraser.r), 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = pal.accent;
  }
  if (drag && drag.mode === "shape" && drag.tool === "card") {
    const a = toScreen(view, drag.x0, drag.y0), b = toScreen(view, drag.x1, drag.y1), box = normRect(a.x, a.y, b.x, b.y);
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(box.x, box.y, box.width, box.height);
    ctx.setLineDash([]);
  }
}

// o: {ctx, doc, view, w, h, pal, scale, ui, images, flat}; ui is null for export (no grid, handles or selection),
// images(node) gives a loaded picture of a file card or null, flat paints cork without its texture (the fill tool
// floods colors, and the speckles would stop it everywhere).
function paintScene(o) {
  const { ctx, doc, view, pal, ui } = o;
  const k = o.scale, cork = cvCork(doc), background = cvBackground(doc);
  ctx.setTransform(k, 0, 0, k, 0, 0);
  ctx.fillStyle = background || (cork ? CV_CORK[pal.dark ? "dark" : "light"] : pal.bg);
  ctx.fillRect(0, 0, o.w, o.h);
  if (ui && !cork) paintGrid(ctx, view, o.w, o.h, pal);
  ctx.setTransform(k * view.z, 0, 0, k * view.z, k * view.x, k * view.y);
  const vis = { x: -view.x / view.z - 40, y: -view.y / view.z - 40, width: o.w / view.z + 80, height: o.h / view.z + 80 };
  if (cork && !background && !o.flat) {
    const pattern = corkPattern(ctx, pal.dark);
    if (pattern) { ctx.fillStyle = pattern; ctx.fillRect(vis.x, vis.y, vis.width, vis.height); }
  }
  const editing = ui && ui.editing;
  const picture = (node) => ((node.type === "file" || node.type === "link") && o.images ? o.images(node) : null);
  const nodes = docNodes(doc), map = new Map(nodes.map((n) => [n.id, n]));
  for (const node of nodes) if (node.type === "group" && rectsIntersect(node, vis)) paintGroup(ctx, node, pal, editing === cvKey("n", node));
  const edges = docEdges(doc), selected = (edge) => Boolean(ui && ui.sel.has(cvKey("e", edge)));
  if (!cork) {
    for (const edge of edges) {
      const curve = edgeCurveFor(map, edge, false);
      if (curve) paintEdge(ctx, curve, edge, pal, selected(edge), editing === cvKey("e", edge));
    }
  }
  for (const node of nodes) {
    if (node.type === "group" || !rectsIntersect(node, vis)) continue;
    if (cork) paintCorkNode(ctx, node, pal, editing === cvKey("n", node), picture(node));
    else paintNode(ctx, node, pal, editing === cvKey("n", node), picture(node));
    paintFileBadge(ctx, node, o.media ? o.media(node) : null, cork);
  }
  if (cork) {
    // Thread goes over the paper from pin to pin; every card has its pin, a group only when thread is tied to it.
    // A thread end tied to a spot of the card gets its own pin there.
    const pinned = new Set(), spots = [];
    for (const edge of edges) {
      const curve = edgeCurveFor(map, edge, true);
      if (!curve) continue;
      paintThread(ctx, curve, edge, pal, selected(edge), editing === cvKey("e", edge));
      for (const [id, end] of [[edge.fromNode, "from"], [edge.toNode, "to"]]) {
        const spot = edgeAnchor(edge, end);
        if (spot) spots.push([map.get(id), spot]); else pinned.add(id);
      }
    }
    for (const node of nodes) {
      if ((node.type !== "group" || pinned.has(node.id)) && rectsIntersect(node, vis)) paintPin(ctx, pinPoint(node), pinColor(node));
    }
    for (const [node, spot] of spots) paintPin(ctx, pinPoint(node, spot), pinColor(node));
  }
  for (const el of docElements(doc)) if (rectsIntersect(el, vis)) paintElement(ctx, el, pal, editing === cvKey("x", el));
  if (ui && ui.draft) paintElement(ctx, ui.draft, pal, false);
  if (ui) {
    // The ends of a selected edge can be dragged to another spot of their card.
    for (const edge of edges) {
      const curve = selected(edge) && edgeCurveFor(map, edge, cork);
      if (curve) for (const p of [curve.p0, curve.p3]) paintEndHandle(ctx, p, pal, view.z);
    }
    if (ui.thread) paintThreadDraft(ctx, ui.thread, pal, cork, view.z);
  }
  if (ui && cork) { ctx.setTransform(k, 0, 0, k, 0, 0); paintVignette(ctx, o.w, o.h); }
  if (ui) paintOverlay({ ...o, ui });
}

function cvDraw() {
  if (cv.drawPending || !cv.ctx) return;
  cv.drawPending = true;
  requestAnimationFrame(() => {
    cv.drawPending = false;
    if (!cv.ctx) return;
    const pal = cvPalette();
    if (!cv.doc) {
      cv.ctx.setTransform(cv.dpr, 0, 0, cv.dpr, 0, 0);
      cv.ctx.fillStyle = pal.bg;
      cv.ctx.fillRect(0, 0, cv.w, cv.h);
      return;
    }
    const eraser = cv.tool === "eraser" && cv.eraser === "part" && cv.cursor ? { ...cv.cursor, r: cvEraserRadius() * cv.view.z } : null;
    const ui = { sel: new Set(cv.sel), hover: cv.hover, drag: cv.drag, editing: cv.editing && cv.editing.key, tool: cv.tool, draft: cvDraft(), eraser, thread: cvThreadDraft() };
    paintScene({ ctx: cv.ctx, doc: cv.doc, view: cv.view, w: cv.w, h: cv.h, pal, scale: cv.dpr, ui, images: cvImageFor, media: cvMediaState });
    cvPlaceInline();
  });
}

function cvThreadDraft() {
  const start = cv.tool === "thread" && cv.thread && cvLookup(cv.doc, "n:" + cv.thread.node);
  if (!validBox(start) || !cv.threadAt) return null;
  return { a: anchorPoint(start, cv.thread.frac, cvCork(cv.doc)), b: cv.threadAt };
}

function cvResize() {
  const el = cv.el;
  if (!el) return;
  const box = el.getBoundingClientRect();
  cv.w = Math.max(1, Math.floor(box.width));
  cv.h = Math.max(1, Math.floor(box.height));
  cv.dpr = window.devicePixelRatio || 1;
  el.width = Math.round(cv.w * cv.dpr);
  el.height = Math.round(cv.h * cv.dpr);
  cvDraw();
}

function cvZoomLabel() {
  if (cv.ui.zoom) cv.ui.zoom.textContent = Math.round(cv.view.z * 100) + "%";
}

function cvSetView(view) {
  cv.view = view;
  cvZoomLabel();
  cvDraw();
}

function cvFit() {
  if (!cv.el || !cv.doc) return;
  cvSetView(fitView(sceneBounds(cv.doc), cv.w, cv.h));
}

function cvExport() {
  const bounds = cv.doc && sceneBounds(cv.doc);
  if (!bounds) { toast("Nothing to export"); return; }
  const pad = 32, width = Math.ceil(bounds.width + pad * 2), height = Math.ceil(bounds.height + pad * 2);
  const scale = Math.max(0.25, Math.min(2, 8000 / Math.max(width, height)));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  paintScene({ ctx: canvas.getContext("2d"), doc: cv.doc, view: { x: pad - bounds.x, y: pad - bounds.y, z: 1 }, w: width, h: height, pal: cvPalette(), scale, ui: null, images: cvImageFor });
  canvas.toBlob((blob) => {
    if (!blob) { toast("Could not export the image"); return; }
    const url = URL.createObjectURL(blob);
    const link = h("a", { href: url, download: (cv.name || "canvas") + ".png" });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }, "image/png");
}

function cvIcon(name, weight) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg"), path = document.createElementNS(ns, "path");
  const attrs = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": String(weight || 1.8), "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" };
  for (const [key, value] of Object.entries(attrs)) svg.setAttribute(key, value);
  path.setAttribute("d", CV_ICONS[name] || "");
  svg.append(path);
  return svg;
}

// ---- canvas interaction ----
function cvSelect(keys) {
  cv.sel = keys;
  const only = keys.length === 1 && keys[0][0] === "x" ? cvLookup(cv.doc, keys[0]) : null;
  if (only && only.type !== "text" && only.type !== "paint") {
    cv.style = {
      stroke: typeof only.stroke === "string" ? only.stroke : cv.style.stroke,
      fill: Boolean(only.fill),
      width: cvNum(only.strokeWidth, cv.style.width),
      rough: cv.style.rough,
    };
  }
  cvSync();
  cvDraw();
}

function cvSetTool(tool) {
  cvCloseMenu();
  cv.tool = tool;
  cv.thread = null;
  cv.hover = null;
  cvSync();
  cvCursor();
  cvDraw();
}

function cvCursor() {
  if (!cv.el) return;
  const panning = cv.space || cv.tool === "hand";
  cv.el.style.cursor = panning ? (cv.drag && cv.drag.mode === "pan" ? "grabbing" : "grab") : cv.tool === "select" ? (cv.hover ? "move" : "default") : "crosshair";
}

function cvSync() {
  const ui = cv.ui;
  if (!ui.tools) return;
  cvRenderLayers();
  for (const [tool, button] of Object.entries(ui.tools)) button.classList.toggle("on", tool === cv.tool);
  CV_INK.forEach((color, i) => ui.ink[i].classList.toggle("on", color === cv.style.stroke));
  const custom = !CV_INK.includes(cv.style.stroke);
  ui.customWrap.classList.toggle("on", custom);
  ui.customWrap.style.background = custom ? cv.style.stroke : "";
  if (custom && /^#[0-9a-fA-F]{6}$/.test(cv.style.stroke) && ui.custom.value !== cv.style.stroke.toLowerCase()) ui.custom.value = cv.style.stroke.toLowerCase();
  ui.fill.classList.toggle("on", cv.style.fill);
  if (ui.cork) ui.cork.classList.toggle("on", cvCork(cv.doc));
  if (document.activeElement !== ui.width) ui.width.value = String(widthToSlider(cv.style.width));
  if (document.activeElement !== ui.widthValue) ui.widthValue.value = String(cv.style.width);
  ui.undo.disabled = !cv.hist || !cv.hist.undo.length;
  ui.redo.disabled = !cv.hist || !cv.hist.redo.length;
  cvZoomLabel();
  if (ui.empty) ui.empty.style.display = cv.doc ? "none" : "grid";
}

// Changing the style also restyles the selection.
function cvStyle(patch) {
  Object.assign(cv.style, patch);
  if (patch.width !== undefined || patch.rough !== undefined) cvSavePrefs();
  if (cv.doc && cv.sel.length) {
    applyStyle(cv.doc, cv.sel, {
      stroke: patch.stroke, strokeWidth: patch.width, roughness: patch.rough,
      fill: patch.fill !== undefined ? (cv.style.fill ? cv.style.stroke : null) : undefined,
    });
    cvCommit("style");
  }
  cvSync();
  cvDraw();
}

function cvPoint(event) {
  const box = cv.el.getBoundingClientRect();
  const s = { x: event.clientX - box.left, y: event.clientY - box.top };
  return { s, w: toWorld(cv.view, s.x, s.y) };
}

function cvDraftGeometry(d) {
  let x1 = d.x1, y1 = d.y1;
  if (d.shift) {
    const dx = x1 - d.x0, dy = y1 - d.y0;
    if (d.tool === "line" || d.tool === "arrow") {
      const snapped = snapAngle(dx, dy);
      x1 = d.x0 + snapped.dx;
      y1 = d.y0 + snapped.dy;
    } else {
      const size = Math.max(Math.abs(dx), Math.abs(dy));
      x1 = d.x0 + (dx < 0 ? -size : size);
      y1 = d.y0 + (dy < 0 ? -size : size);
    }
  }
  return { x1, y1 };
}

function cvDraft() {
  return cv.drag ? cvDraftOf(cv.drag) : null;
}

function cvDraftOf(d) {
  if (d.mode === "pen" && d.pts.length > 1) return makeFreedraw(d.pts, cv.style, d.seed);
  if (d.mode !== "shape" || d.tool === "card") return null;
  const { x1, y1 } = cvDraftGeometry(d);
  return d.tool === "line" || d.tool === "arrow" ? makeLinear(d.tool, d.x0, d.y0, x1, y1, cv.style, d.seed) : makeShape(d.tool, d.x0, d.y0, x1, y1, cv.style, d.seed);
}

function cvHoverKey(w) {
  if (cv.tool !== "select") return null;
  const nodes = docNodes(cv.doc), pad = 12 / cv.view.z;
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], w.x, w.y, pad)) return cvKey("n", nodes[i]);
  return null;
}

function cvNodeAt(w) {
  const nodes = docNodes(cv.doc);
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], w.x, w.y)) return nodes[i];
  for (let i = nodes.length - 1; i >= 0; i--) if (boxContains(nodes[i], w.x, w.y)) return nodes[i];
  return null;
}

// The four side dots of the hovered or selected card; dragging one draws an edge.
function cvSideHandle(s) {
  const keys = [cv.hover, cv.sel.length === 1 ? cv.sel[0] : null];
  for (const key of keys) {
    const node = key && key[0] === "n" ? cvLookup(cv.doc, key) : null;
    if (!validBox(node)) continue;
    for (const side of CV_SIDE_NAMES) {
      const a = sideAnchor(node, side), p = toScreen(cv.view, a.x, a.y);
      if (Math.hypot(p.x - s.x, p.y - s.y) <= 9) return { node, side };
    }
  }
  return null;
}

function cvDown(event) {
  if (!cv.doc || (event.button !== 0 && event.button !== 1)) return;
  event.preventDefault();
  const wasEditing = Boolean(cv.editing);
  if (cv.editing) cvEndEdit();
  cv.el.focus();
  if (cv.el.setPointerCapture) cv.el.setPointerCapture(event.pointerId);
  const { s, w } = cvPoint(event);
  // A PDF shown in its card closes when something else is clicked.
  if (cv.inline && hitTest(cv.doc, w.x, w.y, cv.view.z) !== "n:" + cv.inline.id) cvCloseInline();
  if (event.button === 1 || cv.tool === "hand" || cv.space) { cv.drag = { mode: "pan", s, view: { ...cv.view } }; cvCursor(); return; }
  if (cv.tool === "select") { cvDownSelect(event, s, w); return; }
  // The tool stays active, so the click that closes a card or text editor only closes it.
  if (wasEditing && (cv.tool === "text" || cv.tool === "card" || cv.tool === "thread")) return;
  if (cv.tool === "fill") { cvBucket(w, s, event.altKey); return; }
  if (cv.tool === "eraser") { cv.drag = { mode: "erase", removed: 0, last: null }; cvErase(w); return; }
  if (cv.tool === "thread") { cvThreadClick(w); return; }
  if (cv.sel.length) cvSelect([]);
  if (cv.tool === "freedraw") { cv.drag = { mode: "pen", pts: [[w.x, w.y]], seed: cvSeed() }; return; }
  if (cv.tool === "text") {
    const key = hitTest(cv.doc, w.x, w.y, cv.view.z), item = key && key[0] === "x" ? cvLookup(cv.doc, key) : null;
    if (item && item.type === "text") { cvSelect([key]); cvStartEdit(key); return; }
    cvNewText(w);
    return;
  }
  cv.drag = { mode: "shape", tool: cv.tool, x0: w.x, y0: w.y, x1: w.x, y1: w.y, shift: event.shiftKey, seed: cvSeed() };
}

function cvDownSelect(event, s, w) {
  const solo = singleBox(cv.doc, cv.sel);
  const handle = solo && handleAt(solo, s.x, s.y, cv.view);
  if (handle) { cv.drag = { mode: "resize", handle, key: cv.sel[0], orig: cvClone(solo), start: w, moved: false }; return; }
  const end = cvEdgeEndAt(s);
  if (end) { cv.drag = { mode: "anchor", key: end.key, end: end.end, moved: false }; return; }
  const side = cvSideHandle(s);
  if (side) { cv.drag = { mode: "connect", from: side.node, side: side.side, s, s2: null }; return; }
  const key = hitTest(cv.doc, w.x, w.y, cv.view.z);
  if (!key) {
    if (!event.shiftKey) cvSelect([]);
    cv.drag = { mode: "marquee", s, s2: null, w, base: event.shiftKey ? cv.sel.slice() : [] };
    return;
  }
  if (event.shiftKey) {
    if (cv.sel.includes(key)) { cvSelect(cv.sel.filter((k) => k !== key)); return; }
    cvSelect([...cv.sel, key]);
  } else if (!cv.sel.includes(key)) {
    cvSelect([key]);
  }
  const keys = new Set(cv.sel.filter((k) => k[0] !== "e"));
  for (const k of cv.sel) {
    const item = cvLookup(cv.doc, k);
    if (k[0] === "n" && item && item.type === "group") for (const inner of containedIds(cv.doc, item)) keys.add(inner);
  }
  cv.drag = { mode: "move", keys: [...keys], s, last: w, armed: false, key };
}

function cvMove(event) {
  if (!cv.doc) return;
  const { s, w } = cvPoint(event);
  const d = cv.drag;
  if (cv.tool === "eraser" && cv.eraser === "part") { cv.cursor = s; cvDraw(); }
  if (cv.tool === "thread") { cv.threadAt = w; if (cv.thread) cvDraw(); }
  if (!d) {
    const key = cvHoverKey(w);
    if (key !== cv.hover) { cv.hover = key; cvCursor(); cvDraw(); }
    return;
  }
  if (d.mode === "pan") {
    cvSetView({ ...d.view, x: d.view.x + s.x - d.s.x, y: d.view.y + s.y - d.s.y });
    return;
  }
  if (d.mode === "move") {
    if (!d.armed) {
      if (Math.hypot(s.x - d.s.x, s.y - d.s.y) < 3) return;
      d.armed = true;
    }
    moveItems(cv.doc, d.keys, w.x - d.last.x, w.y - d.last.y);
    d.last = w;
  } else if (d.mode === "resize") {
    const item = cvLookup(cv.doc, d.key);
    if (!item) return;
    applyBox(item, d.orig, resizeBox(d.orig, d.handle, w.x - d.start.x, w.y - d.start.y));
    d.moved = true;
  } else if (d.mode === "anchor") {
    if (cvMoveEnd(d, w)) d.moved = true;
  } else if (d.mode === "marquee" || d.mode === "connect") {
    d.s2 = s;
    d.w2 = w;
  } else if (d.mode === "shape") {
    d.x1 = w.x;
    d.y1 = w.y;
    d.shift = event.shiftKey;
  } else if (d.mode === "pen") {
    const last = d.pts[d.pts.length - 1];
    if (Math.hypot(w.x - last[0], w.y - last[1]) * cv.view.z > 1.5) d.pts.push([w.x, w.y]);
  } else if (d.mode === "erase") {
    cvErase(w);
  }
  cvDraw();
}

function cvUp(event) {
  const d = cv.drag;
  if (!d) return;
  cv.drag = null;
  const { w } = cvPoint(event);
  if (d.mode === "move") {
    if (d.armed) cvCommit("move");
    else if (!event.shiftKey) cvClickCard(d.key, w);
  } else if (d.mode === "resize") {
    if (d.moved) cvCommit("resize");
  } else if (d.mode === "anchor") {
    if (d.moved) cvCommit("thread end");
  } else if (d.mode === "marquee") {
    const box = normRect(d.w.x, d.w.y, w.x, w.y), picked = [];
    for (const node of docNodes(cv.doc)) if (node.type === "group" ? boxInside(node, box) : rectsIntersect(node, box)) picked.push(cvKey("n", node));
    for (const el of docElements(cv.doc)) if (rectsIntersect(el, box)) picked.push(cvKey("x", el));
    cvSelect([...new Set([...d.base, ...picked])]);
  } else if (d.mode === "connect") {
    cvFinishConnect(d, w);
  } else if (d.mode === "shape") {
    d.x1 = w.x;
    d.y1 = w.y;
    d.shift = event.shiftKey;
    cvFinishShape(d);
  } else if (d.mode === "pen") {
    if (d.pts.length > 1) {
      ensureElements(cv.doc).push(makeFreedraw(d.pts, cv.style, d.seed));
      cvCommit("draw");
    }
  } else if (d.mode === "erase") {
    if (d.removed) cvCommit("erase");
  }
  cvCursor();
  cvDraw();
}

function cvCancelDrag() {
  if (!cv.drag) return;
  const mode = cv.drag.mode;
  cv.drag = null;
  if ((mode === "move" || mode === "resize" || mode === "erase" || mode === "anchor") && cv.hist) cv.doc = JSON.parse(cv.hist.cur);
  cv.sel = cv.doc ? cv.sel.filter((key) => cvLookup(cv.doc, key)) : [];
  cvCursor();
  cvDraw();
}

function cvFinishShape(d) {
  const { x1, y1 } = cvDraftGeometry(d);
  const big = Math.hypot(x1 - d.x0, y1 - d.y0) * cv.view.z >= 4;
  if (d.tool === "card") {
    const box = big ? normRect(d.x0, d.y0, x1, y1) : { x: d.x0, y: d.y0, width: 260, height: 120 };
    const node = { id: cvId(), type: "text", text: "", x: box.x, y: box.y, width: Math.max(80, box.width), height: Math.max(48, box.height) };
    ensureList(cv.doc, "nodes").push(node);
    cvSelect([cvKey("n", node)]);
    cvStartEdit(cvKey("n", node));
    return;
  }
  if (!big) return;
  const el = cvDraftOf(d);
  if (!el) return;
  ensureElements(cv.doc).push(el);
  cvSelect([cvKey("x", el)]);
  cvCommit("draw");
}

function cvNewText(w) {
  const size = 24;
  const el = { id: cvId(), type: "text", x: w.x, y: w.y, width: 10, height: size * 1.25, stroke: cv.style.stroke, fill: null, strokeWidth: cv.style.width, roughness: cv.style.rough, seed: cvSeed(), text: "", fontSize: size };
  ensureElements(cv.doc).push(el);
  cvSelect([cvKey("x", el)]);
  cvStartEdit(cvKey("x", el));
}

// The scene as pixels, drawn like the screen without grid or selection; null where no canvas can be made.
function cvSnapshot() {
  if (!cv.doc || !cv.w || !cv.h) return null;
  const canvas = document.createElement("canvas");
  if (!canvas || typeof canvas.getContext !== "function") return null;
  const k = Math.min(2, cv.dpr || 1), w = Math.round(cv.w * k), h = Math.round(cv.h * k);
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  paintScene({ ctx, doc: cv.doc, view: cv.view, w: cv.w, h: cv.h, pal: cvPalette(), scale: k, ui: null, images: cvImageFor, flat: true });
  const image = ctx.getImageData(0, 0, w, h);
  return image && image.data ? { data: image.data, w, h, k } : null;
}

// Like a paint program: the area of the clicked color, bounded by anything else, gets the color as a paint element.
// Cards, groups and edges take the color, a click on a line or text recolors it, and an area that runs out of
// the view falls back to filling the shape under it or the background. Alt+click clears instead.
function cvBucket(w, s, clear) {
  const color = clear ? null : cv.style.stroke;
  const tol = 6 / cv.view.z;
  const key = fillTarget(cv.doc, w.x, w.y, cv.view.z), item = key && cvLookup(cv.doc, key);
  if (key && key[0] !== "x") { if (applyFill(cv.doc, key, color)) cvCommit("fill"); return; }
  if (item && onInk(item, w.x, w.y, tol)) {
    if (color !== null && item.stroke !== color) { item.stroke = color; cvCommit("fill"); }
    return;
  }
  if (color !== null && !(item && item.type === "paint" && item.fill === color)) {
    const shot = cvSnapshot();
    const px = shot && Math.floor(s.x * shot.k), py = shot && Math.floor(s.y * shot.k);
    if (shot && px >= 0 && py >= 0 && px < shot.w && py < shot.h) {
      const region = floodRegion(shot.data, shot.w, shot.h, px, py, CV_FILL_TOLERANCE);
      const paint = !region.touches && paintFromMask(growMask(region.mask, shot.w, shot.h), shot.w, shot.h, cv.view, shot.k, color);
      if (paint) {
        const list = ensureElements(cv.doc), at = item ? list.indexOf(item) : -1;
        // Above a filled shape it was poured into, under an empty outline so the line stays on top.
        list.splice(at < 0 ? 0 : item.fill ? at + 1 : at, 0, paint);
        cvCommit("fill");
        return;
      }
    }
  }
  if (key ? applyFill(cv.doc, key, color) : setBackground(cv.doc, color)) cvCommit("fill");
}

// Released on another card: an edge to it. Released on empty canvas (after a real drag): a new card there,
// connected and open for typing, like Obsidian.
// On a detective board the thread is tied where it was pulled from (that side's dot, not the pin on top) and where
// it was let go on the other card; a new card gets it on the side facing the first one.
const CV_SIDE_SPOTS = { top: [0.5, 0], right: [1, 0.5], bottom: [0.5, 1], left: [0, 0.5] };
function cvFinishConnect(d, w) {
  const target = cvNodeAt(w), cork = cvCork(cv.doc);
  if (target && target.id === d.from.id) return;
  const spots = (to) => (cork ? { unlawFrom: CV_SIDE_SPOTS[d.side].slice(), unlawTo: to } : {});
  if (!target) {
    if (!d.s2 || Math.hypot(d.s2.x - d.s.x, d.s2.y - d.s.y) < 24) return;
    const card = cvNewCardAt(w), c = { x: d.from.x + d.from.width / 2, y: d.from.y + d.from.height / 2 }, side = nearestSide(card, c.x, c.y);
    ensureList(cv.doc, "edges").push({ id: cvId(), fromNode: d.from.id, fromSide: d.side, toNode: card.id, toSide: side, toEnd: "arrow", ...spots(CV_SIDE_SPOTS[side].slice()) });
    cvSelect([cvKey("n", card)]);
    // Like the card tool: the card, the edge and the typed text become one undo step when the editor closes.
    cvStartEdit(cvKey("n", card));
    if (!cv.editing) cvCommit("connect");
    return;
  }
  const edge = { id: cvId(), fromNode: d.from.id, fromSide: d.side, toNode: target.id, toSide: nearestSide(target, w.x, w.y), toEnd: "arrow", ...spots(fracAt(target, w, cork)) };
  ensureList(cv.doc, "edges").push(edge);
  cvSelect([cvKey("e", edge)]);
  cvCommit("connect");
}

function cvNewCardAt(w) {
  const node = { id: cvId(), type: "text", text: "", x: Math.round(w.x - 130), y: Math.round(w.y - 60), width: 260, height: 120 };
  ensureList(cv.doc, "nodes").push(node);
  return node;
}

// Thread tool: the first click pins the start on a card at that spot, the second ends it on another card's
// spot, or on empty canvas makes a new card there. Esc or another tool drops a started thread.
function cvThreadClick(w) {
  const cork = cvCork(cv.doc), node = cvNodeAt(w);
  const start = cv.thread && cvLookup(cv.doc, "n:" + cv.thread.node);
  if (!validBox(start)) {
    cv.thread = node ? { node: node.id, frac: fracAt(node, w, cork) } : null;
    cv.threadAt = w;
    if (!node) toast("Click the spot on a card where the thread starts");
    cvDraw();
    return;
  }
  const from = cv.thread.frac;
  cv.thread = null;
  if (node && node.id === start.id) { cvDraw(); return; }
  const a = anchorPoint(start, from, cork), target = node || cvNewCardAt(w);
  const edge = { id: cvId(), fromNode: start.id, fromSide: nearestSide(start, a.x, a.y), toNode: target.id, toSide: nearestSide(target, a.x, a.y), toEnd: "arrow", unlawFrom: from };
  if (node) {
    edge.unlawTo = fracAt(node, w, cork);
    const b = anchorPoint(node, edge.unlawTo, cork);
    edge.toSide = nearestSide(node, b.x, b.y);
  }
  ensureList(cv.doc, "edges").push(edge);
  cvSelect([cvKey(node ? "e" : "n", node ? edge : target)]);
  if (!node) cvStartEdit(cvKey("n", target));
  if (!cv.editing) cvCommit("thread");
}

// An end of the single selected edge under the pointer (screen point), as {key, end}.
function cvEdgeEndAt(s) {
  if (cv.sel.length !== 1 || cv.sel[0][0] !== "e") return null;
  const edge = cvLookup(cv.doc, cv.sel[0]), curve = edge && edgeCurveFor(nodeMap(cv.doc), edge, cvCork(cv.doc));
  if (!curve) return null;
  for (const [p, end] of [[curve.p0, "from"], [curve.p3, "to"]]) {
    const at = toScreen(cv.view, p.x, p.y);
    if (Math.hypot(at.x - s.x, at.y - s.y) <= 9) return { key: cv.sel[0], end };
  }
  return null;
}

function cvMoveEnd(d, w) {
  const edge = cvLookup(cv.doc, d.key), node = edge && cvLookup(cv.doc, "n:" + (d.end === "from" ? edge.fromNode : edge.toNode));
  if (!validBox(node)) return false;
  const cork = cvCork(cv.doc), frac = fracAt(node, w, cork), p = anchorPoint(node, frac, cork);
  edge[d.end === "from" ? "unlawFrom" : "unlawTo"] = frac;
  edge[d.end === "from" ? "fromSide" : "toSide"] = nearestSide(node, p.x, p.y);
  return true;
}

function cvEraserRadius() {
  return Math.max(cv.style.width / 2, 8 / cv.view.z);
}

function cvErase(w) {
  const d = cv.drag;
  if (d && cv.eraser === "part") {
    const r = cvEraserRadius(), from = d.last || w;
    const steps = Math.min(200, Math.max(1, Math.ceil(Math.hypot(w.x - from.x, w.y - from.y) / Math.max(0.5, r / 2))));
    let changed = 0;
    for (let i = 1; i <= steps; i++) changed += eraseAt(cv.doc, from.x + ((w.x - from.x) * i) / steps, from.y + ((w.y - from.y) * i) / steps, r);
    d.last = w;
    if (changed) {
      d.removed += changed;
      cv.sel = cv.sel.filter((k) => cvLookup(cv.doc, k));
      cvDraw();
    }
    return;
  }
  const key = hitTest(cv.doc, w.x, w.y, cv.view.z);
  if (!key || !cv.drag) return;
  if (removeItems(cv.doc, [key])) {
    cv.drag.removed++;
    cv.sel = cv.sel.filter((k) => cvLookup(cv.doc, k));
    cvDraw();
  }
}

// One click works the card in place: a video or sound plays (a click on its bar seeks), a PDF opens in the card,
// a site opens inside the desk, a linked canvas opens. Two clicks open it whole: the viewer, or a site in a new tab.
// The single click waits CV_DOUBLE_MS so a double click never does both.
const CV_DOUBLE_MS = 230;
function cvClickCard(key, w) {
  const node = cv.doc && key[0] === "n" ? cvLookup(cv.doc, key) : null;
  if (!node || (node.type !== "file" && node.type !== "link")) return;
  clearTimeout(cv.clickTimer);
  cv.clickTimer = setTimeout(() => { cv.clickTimer = 0; cvCardAction(key, w); }, CV_DOUBLE_MS);
}
function cvCardAction(key, w) {
  const node = cv.doc && cvLookup(cv.doc, key);
  if (!node) return;
  if (node.type === "link") {
    // A site that refuses to be shown inside other pages would be an empty frame: it opens in a tab instead.
    if (node.unlawPreview && node.unlawPreview.frameable === false) cvOpenInApp(node); else cvView(key);
    return;
  }
  const kind = cvFileKind(node.file);
  if (kind === "canvas") cvFollowLink(node);
  else if (kind === "video" || kind === "audio") cvTogglePlay(node, w);
  else if (kind === "pdf") cvOpenInline(node);
}
function cvCardDouble(key) {
  clearTimeout(cv.clickTimer);
  cv.clickTimer = 0;
  const node = cv.doc && cvLookup(cv.doc, key);
  if (!node) return;
  if (node.type === "link") { cvOpenInApp(node); return; }
  if (cvFileKind(node.file) === "canvas") { cvFollowLink(node); return; }
  cvStopMedia();
  cvCloseInline();
  cvView(key);
}

// ---- cards that play in place: one video or sound at a time, drawn on the canvas from a hidden media element ----
const CV_WAVE_LIMIT = 60 * 1024 * 1024;
const cvWaves = new Map(); // canvas path + file -> peaks 0..1 (null while loading or when it cannot be read)
function cvMediaState(node) {
  if (node.type !== "file") return null;
  const p = cv.playing, file = String(node.file ?? "");
  if (!p || p.id !== node.id || p.path !== cv.path) {
    const peaks = cvWaves.get(cv.path + "\n" + file);
    return peaks ? { kind: "audio", playing: false, progress: 0, peaks, idle: true } : null;
  }
  const m = p.media, duration = Number.isFinite(m.duration) && m.duration > 0 ? m.duration : 0;
  return { kind: p.kind, playing: !m.paused && !m.ended, progress: duration ? Math.min(1, m.currentTime / duration) : 0, peaks: cvWaves.get(p.path + "\n" + p.file) || null, idle: false };
}
function cvTogglePlay(node, w) {
  const file = String(node.file ?? ""), kind = cvFileKind(file), p = cv.playing;
  if (p && p.id === node.id && p.path === cv.path) {
    const m = p.media, box = cvPictureBox(node, cvCork(cv.doc));
    if (w && Number.isFinite(m.duration) && m.duration > 0 && w.y >= box.y + box.height - 22 && w.y <= box.y + box.height + 2) {
      m.currentTime = Math.max(0, Math.min(1, (w.x - box.x) / box.width)) * m.duration;
    } else if (m.paused || m.ended) {
      cvPlay(m);
    } else {
      m.pause();
    }
    cvDraw();
    return;
  }
  cvStopMedia();
  if (typeof document.createElement !== "function") return;
  const media = document.createElement(kind === "video" ? "video" : "audio");
  media.preload = "auto";
  media.playsInline = true;
  media.src = cvMediaUrl(cv.path, file, "&raw=1");
  for (const type of ["loadeddata", "pause", "ended", "seeked"]) media.addEventListener(type, () => cvDraw());
  media.addEventListener("error", () => { if (cv.playing && cv.playing.media === media) toast("Could not play " + file.split("/").pop()); });
  if (cv.ui.players) cv.ui.players.append(media);
  cv.playing = { id: node.id, path: cv.path, file, kind, media };
  cvPlay(media);
  if (kind === "audio") cvLoadWave(cv.path, file);
}
function cvPlay(media) {
  const started = media.play();
  // Stopping a sound that is still starting rejects play() with AbortError: nothing to report then.
  if (started && typeof started.catch === "function") started.catch((error) => { if (error && error.name !== "AbortError") toast("Could not play: " + error.message); });
  cvTick();
}
// Redraws while something plays; stops by itself when it pauses, ends, or its card or canvas is gone.
function cvTick() {
  if (cv.ticking) return;
  cv.ticking = true;
  const step = () => {
    const p = cv.playing;
    if (p && (p.path !== cv.path || !cv.doc || !cvLookup(cv.doc, "n:" + p.id))) { cv.ticking = false; cvStopMedia(); return; }
    if (!p || !cv.ctx || p.media.paused || p.media.ended) { cv.ticking = false; cvDraw(); return; }
    cvDraw();
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function cvStopMedia() {
  const p = cv.playing;
  if (!p) return;
  cv.playing = null;
  p.media.pause();
  if (typeof p.media.removeAttribute === "function") p.media.removeAttribute("src");
  if (typeof p.media.load === "function") p.media.load(); // lets the browser drop the download
  if (typeof p.media.remove === "function") p.media.remove();
  cvDraw();
}
async function cvLoadWave(path, file) {
  const key = path + "\n" + file;
  if (cvWaves.has(key) || typeof AudioContext !== "function") return;
  cvWaves.set(key, null);
  try {
    const response = await fetch(cvMediaUrl(path, file, "&raw=1"), { cache: "force-cache" });
    if (!response.ok || Number(response.headers.get("Content-Length") || 0) > CV_WAVE_LIMIT) return;
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > CV_WAVE_LIMIT) return;
    const context = new AudioContext();
    try {
      const sound = await context.decodeAudioData(buffer);
      cvWaves.set(key, cvPeaks(sound.getChannelData(0), 160));
    } finally {
      context.close();
    }
    cvDraw();
  } catch {
    // No wave for this sound: the progress bar alone.
  }
}
function cvPeaks(samples, count) {
  // Every sample of a slice would be millions for a song: about 256 of them are enough for its loudest point.
  const peaks = [], step = Math.max(1, Math.floor(samples.length / count)), stride = Math.max(1, Math.floor(step / 256));
  for (let i = 0; i < count; i++) {
    let top = 0;
    for (let j = i * step, end = Math.min(samples.length, (i + 1) * step); j < end; j += stride) top = Math.max(top, Math.abs(samples[j]));
    peaks.push(top);
  }
  const loudest = Math.max(0.01, ...peaks);
  return peaks.map((peak) => peak / loudest);
}

// ---- a PDF read inside its card: a live frame over the card's picture, moved and turned with it ----
function cvOpenInline(node) {
  if (cv.inline && cv.inline.id === node.id && cv.inline.path === cv.path) return;
  cvCloseInline();
  const layer = cv.ui.inline;
  if (!layer) return;
  const file = String(node.file ?? ""), frame = h("iframe", { src: cvMediaUrl(cv.path, file, "&raw=1") + "#view=FitH", title: file.split("/").pop() });
  layer.append(frame);
  cv.inline = { id: node.id, path: cv.path, frame };
  cvPlaceInline();
}
function cvCloseInline() {
  const inline = cv.inline;
  if (!inline) return;
  cv.inline = null;
  if (typeof inline.frame.remove === "function") inline.frame.remove();
}
function cvPlaceInline() {
  const inline = cv.inline;
  if (!inline) return;
  const node = inline.path === cv.path && cv.doc ? cvLookup(cv.doc, "n:" + inline.id) : null;
  if (!node || cvHidden(node)) { cvCloseInline(); return; }
  const cork = cvCork(cv.doc), box = cvPictureBox(node, cork), z = cv.view.z, at = toScreen(cv.view, box.x, box.y);
  const origin = (node.x + node.width / 2 - box.x) * z + "px " + (node.y + node.height / 2 - box.y) * z + "px";
  Object.assign(inline.frame.style, {
    left: at.x + "px", top: at.y + "px", width: box.width * z + "px", height: box.height * z + "px",
    transformOrigin: origin, transform: cork ? "rotate(" + nodeTilt(node) + "rad)" : "",
  });
}

// ---- links between canvases: a file card naming a .canvas opens it; Back returns ----
// A card's path is relative to its canvas's folder (like attachments) or absolute for a canvas elsewhere.
function canvasLinkPath(from, file) {
  const name = String(file ?? ""), joined = name.startsWith("/") ? name : String(from || "").replace(/\/[^/]*$/, "") + "/" + name, parts = [];
  for (const part of joined.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") parts.pop(); else parts.push(part);
  }
  return "/" + parts.join("/");
}
function canvasLinkFile(from, target) {
  const folder = String(from || "").replace(/\/[^/]*$/, "") + "/";
  return target.startsWith(folder) ? target.slice(folder.length) : target;
}
async function cvFollowLink(node) {
  const from = cv.path, target = canvasLinkPath(from, node.file);
  if (!from || target === from) return;
  if (await cvOpen(target, false)) {
    cv.back = [...cv.back, from].slice(-30);
    cvFillPick();
  }
}
async function cvGoBack() {
  const from = cv.back[cv.back.length - 1];
  if (!from) return;
  cv.back = cv.back.slice(0, -1);
  await cvOpen(from, false);
  cvFillPick();
}
function cvAddCanvasLink(item) {
  if (!cv.doc || !cv.path || item.path === cv.path) return;
  const center = toWorld(cv.view, cv.w / 2, cv.h / 2);
  const node = { id: cvId(), type: "file", file: canvasLinkFile(cv.path, item.path), x: Math.round(center.x - 150), y: Math.round(center.y - 110), width: 300, height: 220 };
  ensureList(cv.doc, "nodes").push(node);
  cvToggleGallery(false);
  cvSelect([cvKey("n", node)]);
  cvCommit("canvas link");
  toast("\u201c" + item.name + "\u201d is linked: click the card to open it");
}
// Another canvas as a picture for its card, read without switching to it (cleared when the open canvas changes).
const cvCanvasThumbs = new Map();
function cvCanvasThumb(path) {
  let entry = cvCanvasThumbs.get(path);
  if (!entry) {
    entry = { image: null };
    cvCanvasThumbs.set(path, entry);
    cvMakeCanvasThumb(path, entry);
  }
  return entry.image;
}
async function cvMakeCanvasThumb(path, entry) {
  if (typeof document.createElement !== "function") return;
  const { status, data } = await api("GET", "/api/canvas/peek?path=" + encodeURIComponent(path));
  if (status !== 200 || !data.canvas || cvCanvasThumbs.get(path) !== entry) return;
  const picture = document.createElement("canvas"), width = 240, height = 150;
  const ctx = picture.getContext && picture.getContext("2d");
  if (!ctx) return;
  picture.width = width * 2;
  picture.height = height * 2;
  paintScene({ ctx, doc: data.canvas, view: fitView(sceneBounds(data.canvas), width, height, 12), w: width, h: height, pal: cvPalette(), scale: 2, ui: null, images: null, flat: true });
  entry.image = picture;
  cvDraw();
}

// A text card holding only a web address (or a title line above one) is a link card.
function urlCardText(text) {
  const lines = String(text ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
  if (!lines.length || lines.length > 2 || !cvHttpUrl(lines[lines.length - 1])) return null;
  if (lines.length === 2 && (lines[0].length > 200 || cvHttpUrl(lines[0]))) return null;
  return { url: lines[lines.length - 1], title: lines.length === 2 ? lines[0] : "" };
}
function textToLink(node) {
  const found = node && typeof node === "object" && node.type === "text" ? urlCardText(node.text) : null;
  if (!found) return false;
  node.type = "link";
  node.url = found.url;
  delete node.text;
  if (found.title) node.unlawPreview = { title: found.title, description: "", site: "", image: null };
  return true;
}

// Pictures of file cards: the file itself for images, a Quick Look thumbnail for anything else (PDF, documents).
// Loaded once per canvas and file; a failed one is not asked again, so the card stays a plain document.
const cvImages = new Map();
function cvImageFor(node) {
  if (node.type === "link") {
    // Cards from before logos (no icon key) ask once for the site's logo.
    const preview = node.unlawPreview && typeof node.unlawPreview === "object" ? node.unlawPreview : null;
    if (!preview || !("icon" in preview)) cvFetchPreview(node, true);
    return preview && typeof preview.icon === "string" && preview.icon ? cvImageFor({ file: preview.icon }) : null;
  }
  const file = String(node.file ?? ""), p = cv.playing;
  if (p && p.kind === "video" && p.id === node.id && p.path === cv.path && p.media.readyState >= 2) return p.media;
  if (CV_CANVAS_FILE.test(file)) return cv.path ? cvCanvasThumb(canvasLinkPath(cv.path, file)) : null;
  if (!file || !cv.path || noteName(file) || CV_PLAIN_FILE.test(file) || typeof Image !== "function") return null;
  if (CV_MODEL.test(file)) {
    const still = cvStills.get(cv.path + "\n" + file);
    if (still && still.image) return still.image;
    if (!still && typeof document.createElement === "function") cvModelStill(cv.path, file);
  }
  const key = cv.path + "\n" + file;
  let entry = cvImages.get(key);
  if (!entry) {
    const image = new Image();
    entry = { image, ok: false };
    image.onload = () => { entry.ok = true; cvDraw(); };
    image.src = "/media/canvas?t=" + encodeURIComponent(TOKEN) + "&path=" + encodeURIComponent(cv.path) + "&file=" + encodeURIComponent(file) + (CV_IMAGE_FILE.test(file) ? "" : "&thumb=1");
    cvImages.set(key, entry);
  }
  return entry.ok ? entry.image : null;
}

function cvLocalImageSize(file) {
  return new Promise((resolve) => {
    if (typeof Image !== "function" || !/^image\//.test(file.type || "") || typeof URL.createObjectURL !== "function") { resolve(null); return; }
    const url = URL.createObjectURL(file), image = new Image();
    const done = (size) => { URL.revokeObjectURL(url); resolve(size); };
    image.onload = () => done({ w: image.naturalWidth, h: image.naturalHeight });
    image.onerror = () => done(null);
    image.src = url;
  });
}

// Copy files next to the canvas (attachments/) and pin a card for each at `at` (world point; default: view center).
async function cvAddFiles(files, at) {
  const list = Array.from(files || []).slice(0, 30);
  if (!list.length) return;
  if (!cv.doc || !cv.path) { toast("Open or create a canvas first"); return; }
  const path = cv.path;
  const center = at || toWorld(cv.view, cv.w / 2, cv.h / 2);
  const added = [];
  for (const [i, file] of list.entries()) {
    if (file.size > CV_MAX_UPLOAD) { toast(file.name + " is larger than 256 MB"); continue; }
    cvStatus("Adding " + file.name + "…");
    let response, data = {};
    try {
      response = await fetch("/api/canvas/upload?path=" + encodeURIComponent(path) + "&name=" + encodeURIComponent(file.name || "file"), {
        method: "POST", headers: { "X-Desk-Token": TOKEN, "Content-Type": "application/octet-stream" }, body: file, cache: "no-store",
      });
      data = await response.json().catch(() => ({}));
    } catch (error) {
      toast("Could not reach the desk: " + error.message);
      continue;
    }
    if (!response.ok || typeof data.file !== "string") { toast(data.error || "Could not add " + file.name); continue; }
    if (cv.path !== path || !cv.doc) { toast(file.name + " was saved next to the other canvas"); continue; }
    const size = fileCardSize(await cvLocalImageSize(file));
    const node = { id: cvId(), type: "file", file: data.file, x: Math.round(center.x - size.width / 2 + i * 36), y: Math.round(center.y - size.height / 2 + i * 36), ...size };
    ensureList(cv.doc, "nodes").push(node);
    added.push(cvKey("n", node));
  }
  cvStatus("");
  if (added.length) {
    cvSelect(added);
    cvCommit("add files");
  }
}

const cvHasFiles = (event) => Boolean(event.dataTransfer && Array.from(event.dataTransfer.types || []).includes("Files"));

function cvToggleCork() {
  if (!cv.doc) return;
  if (setLook(cv.doc, !cvCork(cv.doc))) { cvCommit("look"); cvSync(); }
}

function cvDouble(event) {
  if (!cv.doc || cv.tool !== "select") return;
  const { w } = cvPoint(event);
  const key = hitTest(cv.doc, w.x, w.y, cv.view.z), item = key && key[0] === "n" ? cvLookup(cv.doc, key) : null;
  if (item && (item.type === "file" || item.type === "link")) { cvCardDouble(key); return; }
  if (key) { cvSelect([key]); cvStartEdit(key); }
}

function cvWheel(event) {
  event.preventDefault();
  if (!cv.doc) return;
  const box = cv.el.getBoundingClientRect(), unit = event.deltaMode === 1 ? 16 : 1;
  if (event.ctrlKey || event.metaKey) {
    cvSetView(zoomAt(cv.view, event.clientX - box.left, event.clientY - box.top, Math.exp(-event.deltaY * unit * (event.deltaMode === 1 ? 0.05 : 0.01))));
  } else {
    cvSetView({ ...cv.view, x: cv.view.x - event.deltaX * unit, y: cv.view.y - event.deltaY * unit });
  }
}

// ---- text editing: one floating textarea on top of the card, label or text ----
function cvMeasure(font) {
  if (cv.ctx) return (text) => { cv.ctx.font = font; return cv.ctx.measureText(text).width; };
  return (text) => text.length * parseFloat(font) * 0.55;
}

function cvStartEdit(key) {
  const item = cvLookup(cv.doc, key);
  if (!item || !cv.el || !cv.ui.editor) return;
  cvEndEdit();
  let box, text, font = "15px " + CV_FONT;
  if (key[0] === "e") {
    const curve = edgeCurveFor(nodeMap(cv.doc), item, cvCork(cv.doc));
    if (!curve) return;
    const mid = bezierPoint(curve, 0.5);
    box = { x: mid.x - 80, y: mid.y - 14, width: 160, height: 28 };
    text = item.label ?? "";
  } else if (key[0] === "x") {
    if (item.type !== "text") return;
    box = item;
    text = item.text ?? "";
    font = cvNum(item.fontSize, 24) + "px " + CV_HAND;
  } else if (item.type === "group") {
    box = { x: item.x, y: item.y - 30, width: Math.min(item.width, 260), height: 28 };
    text = item.label ?? "";
  } else if (item.type === "text") {
    box = item;
    text = item.text ?? "";
  } else {
    return;
  }
  cv.editing = { key };
  const z = cv.view.z, at = toScreen(cv.view, box.x, box.y), editor = cv.ui.editor;
  editor.value = String(text);
  Object.assign(editor.style, {
    display: "block", left: at.x + "px", top: at.y + "px", width: Math.max(box.width * z, 140) + "px", height: Math.max(box.height * z, 30) + "px",
    font: font.replace(/^[\d.]+px/, (px) => parseFloat(px) * z + "px"), color: key[0] === "x" ? adaptInk(item.stroke, cvPalette().dark) : "",
  });
  editor.focus();
  editor.select();
  cvDraw();
}

function cvEndEdit() {
  const editing = cv.editing;
  if (!editing) return;
  cv.editing = null;
  const editor = cv.ui.editor, value = editor ? editor.value : "";
  if (editor) editor.style.display = "none";
  const item = cv.doc && cvLookup(cv.doc, editing.key);
  if (item) {
    const kind = editing.key[0];
    if (kind === "e") {
      if (value) item.label = value; else delete item.label;
    } else if (kind === "x") {
      if (!value.trim()) {
        removeItems(cv.doc, [editing.key]);
        cv.sel = cv.sel.filter((key) => key !== editing.key);
      } else {
        item.text = value;
        const size = cvNum(item.fontSize, 24), measure = cvMeasure(size + "px " + CV_HAND), lines = value.split("\n");
        item.width = Math.max(10, ...lines.map((line) => measure(line)));
        item.height = lines.length * size * 1.25;
      }
    } else if (item.type === "group") {
      item.label = value;
    } else {
      item.text = value;
      if (textToLink(item)) cvFetchPreview(item);
    }
    cvCommit("text");
  }
  if (cv.el) cv.el.focus();
  cvDraw();
}

// ---- the viewer: a file or link card opened inside the page, so nothing has to leave the desk ----
const CV_VIDEO = /\.(mp4|m4v|mov|webm)$/i, CV_AUDIO = /\.(mp3|m4a|aac|wav|flac|ogg|opus)$/i, CV_PDF = /\.pdf$/i;
const CV_DOC = /\.(docx|doc|rtf|odt)$/i, CV_MODEL = /\.(glb|gltf|obj|stl)$/i, CV_NOTE = /\.(md|markdown)$/i;
const CV_TEXT_LIMIT = 2 * 1024 * 1024, CV_MODEL_LIMIT = 200 * 1024 * 1024, CV_STILL_LIMIT = 30 * 1024 * 1024;
function cvFileKind(file) {
  const name = String(file || "");
  if (CV_IMAGE_FILE.test(name)) return "image";
  if (CV_CANVAS_FILE.test(name)) return "canvas";
  if (CV_VIDEO.test(name)) return "video";
  if (CV_AUDIO.test(name)) return "audio";
  if (CV_PDF.test(name)) return "pdf";
  if (CV_DOC.test(name)) return "doc";
  if (CV_MODEL.test(name)) return "model";
  if (CV_NOTE.test(name) || CV_PLAIN_FILE.test(name)) return "text";
  return "other";
}
const cvMediaUrl = (path, file, extra) => "/media/canvas?t=" + encodeURIComponent(TOKEN) + "&path=" + encodeURIComponent(path) + "&file=" + encodeURIComponent(file) + (extra || "");
const cvHttpUrl = (url) => /^https?:\/\/[^\s]+$/i.test(String(url || "").trim());

function cvCloseView() {
  const viewing = cv.viewing, panel = cv.ui.view;
  if (!viewing) return;
  cv.viewing = null;
  if (viewing.stop) viewing.stop();
  if (!panel) return;
  for (const media of panel.querySelectorAll("video, audio")) media.pause();
  panel.textContent = "";
  panel.classList.remove("on");
  if (cv.el) cv.el.focus();
}

async function cvOpenInApp(node) {
  if (node.type === "link") {
    // Only web addresses: a canvas from someone else may carry javascript:, file: or app links.
    if (!cvHttpUrl(node.url)) { toast("Only http and https links open from the canvas"); return; }
    window.open(String(node.url).trim(), "_blank", "noopener,noreferrer");
    return;
  }
  const name = noteName(node.file);
  if (name) { openNote(name); return; }
  const { data } = await api("POST", "/api/canvas/open-file", { path: cv.path, file: String(node.file ?? "") });
  if (!data.ok) toast(data.error || "Could not open " + String(node.file ?? "").split("/").pop());
  else if (data.revealed) toast("Shown in Finder: files that would run a program are never opened from the canvas");
}

function cvView(key) {
  const node = cv.doc && cvLookup(cv.doc, key), panel = cv.ui.view;
  if (!node || !panel || (node.type !== "file" && node.type !== "link")) return false;
  cvCloseView();
  const path = cv.path, file = String(node.file ?? ""), kind = node.type === "link" ? "link" : cvFileKind(file);
  const title = node.type === "link" ? (node.unlawPreview && node.unlawPreview.title) || String(node.url || "") : file.split("/").pop();
  const outside = node.type === "link" ? "Open in browser" : noteName(file) ? "Open in Obsidian" : "Open in app";
  const openButton = h("button", { title: outside }, cvIcon(node.type === "link" ? "link" : "export"), outside);
  openButton.addEventListener("click", () => cvOpenInApp(node));
  const close = h("button", { class: "x", title: "Close (Esc)", "aria-label": "Close" }, cvIcon("close"));
  close.addEventListener("click", cvCloseView);
  const body = h("div", { class: "body " + kind });
  panel.textContent = "";
  panel.append(h("div", { class: "head" }, h("b", { text: title }), h("span", { class: "spacer" }), openButton, close), body);
  panel.classList.add("on");
  cv.viewing = { key, stop: null };
  const url = (extra) => cvMediaUrl(path, file, extra);
  if (kind === "image") body.append(h("img", { src: url(""), alt: title }));
  else if (kind === "video") body.append(h("video", { src: url("&raw=1"), controls: "", autoplay: "", playsinline: "" }));
  else if (kind === "audio") body.append(h("div", { class: "sound" }, cvIcon("audio"), h("span", { text: title }), h("audio", { src: url("&raw=1"), controls: "", autoplay: "" })));
  else if (kind === "pdf") body.append(h("iframe", { src: url("&raw=1"), title }));
  else if (kind === "doc") body.append(h("iframe", { src: url("&doc=1"), sandbox: "", title }));
  else if (kind === "text") cvShowText(body, url("&raw=1"));
  else if (kind === "model") cvShowModel(body, url("&raw=1"), file);
  else if (kind === "link") cvShowLink(body, node);
  else body.append(h("img", { src: url("&thumb=1"), alt: title }), h("div", { class: "note", text: "No live view for this kind of file in the page: Quick Look's picture of it. " + outside + " shows it whole." }));
  return true;
}

async function cvShowText(body, src) {
  let text = "";
  try {
    const response = await fetch(src, { cache: "no-store" });
    if (!response.ok) throw Error(String(response.status));
    text = await response.text();
  } catch (error) {
    body.append(h("div", { class: "note", text: "Could not read the file: " + error.message }));
    return;
  }
  const cut = text.length > CV_TEXT_LIMIT;
  body.append(h("pre", { text: cut ? text.slice(0, CV_TEXT_LIMIT) : text }));
  if (cut) body.append(h("div", { class: "note", text: "Only the first 2 MB are shown." }));
}

function cvShowLink(body, node) {
  const preview = node.unlawPreview && typeof node.unlawPreview === "object" ? node.unlawPreview : null;
  if (!cvHttpUrl(node.url)) { body.append(h("div", { class: "note", text: "This card has no web address." })); return; }
  // allow-same-origin here is the site's own origin, never the desk's; no top navigation, so it cannot take the tab.
  body.append(h("iframe", { src: String(node.url).trim(), sandbox: "allow-scripts allow-same-origin allow-forms allow-popups", referrerpolicy: "no-referrer", title: (preview && preview.title) || "Page" }));
  body.append(h("div", { class: "note", text: "Empty? Some sites (Google, GitHub, banks) refuse to be shown inside other pages: use Open in browser." }));
  if (!preview) cvFetchPreview(node);
}

// The page's title, description and picture for a link card, fetched once by the desk (public sites only).
// Cards whose preview is being fetched, by canvas and id (kept out of the node, which autosave writes to the file).
const cvPreviewing = new Set();
const cvPreviewTried = new Set(); // cards whose logo was asked for by drawing: asked once per page, even when it failed
async function cvFetchPreview(node, again) {
  const path = cv.path, busy = path + "\n" + node.id;
  if (!cvHttpUrl(node.url) || !path || cvPreviewing.has(busy) || (again && cvPreviewTried.has(busy))) return;
  cvPreviewTried.add(busy);
  cvPreviewing.add(busy);
  let answer;
  try {
    answer = await api("POST", "/api/canvas/link-preview", { path, url: String(node.url).trim() });
  } finally {
    cvPreviewing.delete(busy); // a lost connection must not block this card's preview for good
  }
  const { status, data } = answer;
  if (status !== 200 || cv.path !== path || !cv.doc) return;
  const live = cvLookup(cv.doc, cvKey("n", node));
  if (!live) return;
  live.unlawPreview = {
    title: String(data.title || ""), description: String(data.description || ""), site: String(data.site || ""),
    image: typeof data.image === "string" ? data.image : null, icon: typeof data.icon === "string" ? data.icon : null, frameable: data.frameable !== false,
  };
  cvCommit("link preview");
}

// A link pasted on the canvas becomes a link card with the page's preview.
function cvPasteText(text) {
  const found = urlCardText(text);
  if (!cv.doc || !found) return false;
  const center = toWorld(cv.view, cv.w / 2, cv.h / 2);
  const node = { id: cvId(), type: "link", url: found.url, x: Math.round(center.x - 160), y: Math.round(center.y - 120), width: 320, height: 240 };
  ensureList(cv.doc, "nodes").push(node);
  cvSelect([cvKey("n", node)]);
  cvCommit("paste link");
  cvFetchPreview(node);
  return true;
}

// ---- 3D: GLB/glTF, OBJ and STL parsed here and drawn with WebGL (no library): flat triangles with their colors ----
const CV_MAX_TRIANGLES = 3000000;
function meshFromTriangles(positions, colors) {
  const count = positions.length / 9;
  if (count > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
  const normals = new Float32Array(positions.length);
  for (let t = 0; t < count; t++) {
    const o = t * 9, ax = positions[o + 3] - positions[o], ay = positions[o + 4] - positions[o + 1], az = positions[o + 5] - positions[o + 2];
    const bx = positions[o + 6] - positions[o], by = positions[o + 7] - positions[o + 1], bz = positions[o + 8] - positions[o + 2];
    let nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
    const len = Math.hypot(nx, ny, nz) || 1;
    nx /= len; ny /= len; nz /= len;
    for (let v = 0; v < 3; v++) { normals[o + v * 3] = nx; normals[o + v * 3 + 1] = ny; normals[o + v * 3 + 2] = nz; }
  }
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3) for (let k = 0; k < 3; k++) { min[k] = Math.min(min[k], positions[i + k]); max[k] = Math.max(max[k], positions[i + k]); }
  if (!count || !min.every(Number.isFinite)) throw Error("no triangles");
  return { positions, normals, colors: colors || null, count, min, max };
}
function parseSTL(buffer) {
  const view = new DataView(buffer);
  const triangles = buffer.byteLength >= 84 ? view.getUint32(80, true) : 0;
  // Binary when the size fits the count (some exporters add a few trailing bytes) and it does not start like ASCII.
  const ascii = /^\s*solid[\s\S]*facet/.test(new TextDecoder().decode(buffer.slice(0, 512)));
  if (triangles > 0 && buffer.byteLength >= 84 + triangles * 50 && (buffer.byteLength === 84 + triangles * 50 || !ascii)) {
    if (triangles > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
    const positions = new Float32Array(triangles * 9);
    for (let t = 0; t < triangles; t++) for (let k = 0; k < 9; k++) positions[t * 9 + k] = view.getFloat32(84 + t * 50 + 12 + k * 4, true);
    return meshFromTriangles(positions);
  }
  const text = new TextDecoder().decode(buffer), points = [];
  for (const match of text.matchAll(/vertex\s+(\S+)\s+(\S+)\s+(\S+)/g)) points.push(+match[1], +match[2], +match[3]);
  return meshFromTriangles(new Float32Array(points.length - (points.length % 9)).map((_, i) => points[i]));
}
function parseOBJ(text) {
  const vertices = [], out = [];
  const at = (token) => {
    const index = parseInt(token.split("/")[0], 10);
    const i = index < 0 ? vertices.length / 3 + index : index - 1;
    return i >= 0 && i < vertices.length / 3 ? i : -1;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line.startsWith("v ")) { const p = line.split(/\s+/); vertices.push(+p[1], +p[2], +p[3]); }
    else if (line.startsWith("f ")) {
      const face = line.split(/\s+/).slice(1).map(at);
      if (face.some((i) => i < 0)) continue;
      for (let k = 1; k + 1 < face.length; k++) for (const i of [face[0], face[k], face[k + 1]]) out.push(vertices[i * 3], vertices[i * 3 + 1], vertices[i * 3 + 2]);
      if (out.length / 9 > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
    }
  }
  return meshFromTriangles(new Float32Array(out));
}
// glTF 2.0: the default scene's meshes with their node transforms and base colors (textures are not read).
async function parseGLTF(buffer, loadBuffer) {
  const view = new DataView(buffer);
  let json, bin = null;
  if (buffer.byteLength >= 12 && view.getUint32(0, true) === 0x46546c67) {
    let offset = 12;
    while (offset + 8 <= buffer.byteLength) {
      const length = view.getUint32(offset, true), type = view.getUint32(offset + 4, true), chunk = buffer.slice(offset + 8, offset + 8 + length);
      if (type === 0x4e4f534a) json = JSON.parse(new TextDecoder().decode(chunk));
      else if (type === 0x004e4942) bin = chunk;
      offset += 8 + length;
    }
  } else {
    json = JSON.parse(new TextDecoder().decode(buffer));
  }
  if (!json || !Array.isArray(json.meshes)) throw Error("not a glTF model");
  const buffers = [];
  for (const [i, b] of (json.buffers || []).entries()) {
    if (!b.uri) buffers.push(bin);
    else if (/^data:/.test(b.uri)) buffers.push(Uint8Array.from(atob(b.uri.split(",")[1] || ""), (c) => c.charCodeAt(0)).buffer);
    else buffers.push(await loadBuffer(b.uri, i));
  }
  const SIZES = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 };
  const read = (index) => {
    const acc = json.accessors[index], bv = acc && json.bufferViews[acc.bufferView], data = bv && buffers[bv.buffer];
    if (!bv) throw Error("sparse or empty accessors are not supported");
    if (!data) throw Error("a buffer of the model is missing");
    const size = SIZES[acc.type], ctor = { 5126: Float32Array, 5125: Uint32Array, 5123: Uint16Array, 5121: Uint8Array }[acc.componentType];
    if (!ctor) throw Error("unsupported accessor type");
    const stride = bv.byteStride || size * ctor.BYTES_PER_ELEMENT, base = (bv.byteOffset || 0) + (acc.byteOffset || 0), dv = new DataView(data), out = new Float64Array(acc.count * size);
    const get = { 5126: (o) => dv.getFloat32(o, true), 5125: (o) => dv.getUint32(o, true), 5123: (o) => dv.getUint16(o, true), 5121: (o) => dv.getUint8(o) }[acc.componentType];
    for (let i = 0; i < acc.count; i++) for (let k = 0; k < size; k++) out[i * size + k] = get(base + i * stride + k * ctor.BYTES_PER_ELEMENT);
    return out;
  };
  const local = (node) => {
    if (Array.isArray(node.matrix) && node.matrix.length === 16) return node.matrix;
    const [x, y, z, w] = node.rotation || [0, 0, 0, 1], [sx, sy, sz] = node.scale || [1, 1, 1], [tx, ty, tz] = node.translation || [0, 0, 0];
    return [(1 - 2 * (y * y + z * z)) * sx, 2 * (x * y + z * w) * sx, 2 * (x * z - y * w) * sx, 0,
      2 * (x * y - z * w) * sy, (1 - 2 * (x * x + z * z)) * sy, 2 * (y * z + x * w) * sy, 0,
      2 * (x * z + y * w) * sz, 2 * (y * z - x * w) * sz, (1 - 2 * (x * x + y * y)) * sz, 0, tx, ty, tz, 1];
  };
  const positions = [], colors = [];
  const addMesh = (mesh, m) => {
    for (const prim of mesh.primitives || []) {
      if ((prim.mode ?? 4) !== 4 || prim.attributes.POSITION === undefined) continue;
      const p = read(prim.attributes.POSITION), idx = prim.indices !== undefined ? read(prim.indices) : null;
      const material = (json.materials || [])[prim.material], f = (material && material.pbrMetallicRoughness && material.pbrMetallicRoughness.baseColorFactor) || [0.78, 0.78, 0.8, 1];
      const total = idx ? idx.length : p.length / 3;
      for (let i = 0; i < total; i++) {
        const v = idx ? idx[i] : i, x = p[v * 3], y = p[v * 3 + 1], z = p[v * 3 + 2];
        positions.push(m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14]);
        colors.push(f[0], f[1], f[2]);
      }
      if (positions.length / 9 > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
    }
  };
  const visit = (index, parent, depth) => {
    const node = json.nodes[index];
    if (!node || depth > 64) return;
    const m = mat4Multiply(parent, local(node));
    if (node.mesh !== undefined && json.meshes[node.mesh]) addMesh(json.meshes[node.mesh], m);
    for (const child of node.children || []) visit(child, m, depth + 1);
  };
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const scene = (json.scenes || [])[json.scene || 0];
  if (scene && Array.isArray(json.nodes)) for (const root of scene.nodes || []) visit(root, identity, 0);
  else json.meshes.forEach((mesh) => addMesh(mesh, identity));
  return meshFromTriangles(new Float32Array(positions), new Float32Array(colors));
}
async function cvLoadModel(src, file, limit = CV_MODEL_LIMIT, path = cv.path) {
  const response = await fetch(src, { cache: "no-store" });
  if (!response.ok) throw Error("could not read the model (" + response.status + ")");
  if (Number(response.headers.get("Content-Length")) > limit) throw Error("the model is larger than " + Math.round(limit / 1048576) + " MB");
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > limit) throw Error("the model is larger than " + Math.round(limit / 1048576) + " MB");
  if (/\.stl$/i.test(file)) return parseSTL(buffer);
  if (/\.obj$/i.test(file)) return parseOBJ(new TextDecoder().decode(buffer));
  const folder = file.includes("/") ? file.slice(0, file.lastIndexOf("/") + 1) : "";
  return parseGLTF(buffer, async (uri) => {
    const next = await fetch(cvMediaUrl(path, folder + decodeURIComponent(uri), "&raw=1"), { cache: "no-store" });
    if (!next.ok) throw Error("missing " + uri);
    return next.arrayBuffer();
  });
}
// Column-major 4x4 helpers for the camera.
function mat4Perspective(fov, aspect, near, far) {
  const f = 1 / Math.tan(fov / 2), nf = 1 / (near - far);
  return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
}
function mat4LookAt(eye, center, up) {
  let zx = eye[0] - center[0], zy = eye[1] - center[1], zz = eye[2] - center[2];
  let len = Math.hypot(zx, zy, zz) || 1; zx /= len; zy /= len; zz /= len;
  let xx = up[1] * zz - up[2] * zy, xy = up[2] * zx - up[0] * zz, xz = up[0] * zy - up[1] * zx;
  len = Math.hypot(xx, xy, xz) || 1; xx /= len; xy /= len; xz /= len;
  const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
  return [xx, yx, zx, 0, xy, yy, zy, 0, xz, yz, zz, 0, -(xx * eye[0] + xy * eye[1] + xz * eye[2]), -(yx * eye[0] + yy * eye[1] + yz * eye[2]), -(zx * eye[0] + zy * eye[1] + zz * eye[2]), 1];
}
function mat4Multiply(a, b) {
  const r = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let row = 0; row < 4; row++) for (let k = 0; k < 4; k++) r[c * 4 + row] += a[k * 4 + row] * b[c * 4 + k];
  return r;
}
// An orbit camera around the model's middle: drag turns it, the wheel zooms, Shift-drag moves it, double-click resets.
function makeModelView(canvas, mesh) {
  const gl = canvas.getContext("webgl", { antialias: true, preserveDrawingBuffer: true });
  if (!gl) throw Error("WebGL is off in this browser");
  const shader = (type, source) => { const s = gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s); return s; };
  const program = gl.createProgram();
  gl.attachShader(program, shader(gl.VERTEX_SHADER, "attribute vec3 p;attribute vec3 n;attribute vec3 c;uniform mat4 m;varying vec3 vn;varying vec3 vc;void main(){gl_Position=m*vec4(p,1.0);vn=n;vc=c;}"));
  gl.attachShader(program, shader(gl.FRAGMENT_SHADER, "precision mediump float;varying vec3 vn;varying vec3 vc;void main(){vec3 n=normalize(vn);float l=0.35+0.55*abs(dot(n,normalize(vec3(0.4,0.8,0.6))))+0.2*abs(dot(n,normalize(vec3(-0.6,-0.2,-0.7))));gl_FragColor=vec4(vc*l,1.0);}"));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error("WebGL could not build its shader: " + (gl.getProgramInfoLog(program) || "unknown error"));
  gl.useProgram(program);
  const attribute = (name, data) => {
    const buffer = gl.createBuffer(), at = gl.getAttribLocation(program, name);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(at);
    gl.vertexAttribPointer(at, 3, gl.FLOAT, false, 0, 0);
  };
  attribute("p", mesh.positions);
  attribute("n", mesh.normals);
  attribute("c", mesh.colors || new Float32Array(mesh.positions.length).fill(0.78));
  const where = gl.getUniformLocation(program, "m");
  const center = [0, 1, 2].map((k) => (mesh.min[k] + mesh.max[k]) / 2), radius = Math.max(1e-6, Math.hypot(...[0, 1, 2].map((k) => mesh.max[k] - mesh.min[k])) / 2);
  const start = { yaw: 0.6, pitch: 0.35, distance: radius * 2.6, pan: [0, 0, 0] };
  const cam = { ...start, pan: [0, 0, 0] };
  const draw = () => {
    const w = canvas.width, h = canvas.height;
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    const target = center.map((v, k) => v + cam.pan[k]);
    const eye = [target[0] + cam.distance * Math.cos(cam.pitch) * Math.sin(cam.yaw), target[1] + cam.distance * Math.sin(cam.pitch), target[2] + cam.distance * Math.cos(cam.pitch) * Math.cos(cam.yaw)];
    const matrix = mat4Multiply(mat4Perspective(0.8, w / Math.max(1, h), radius / 100, radius * 100), mat4LookAt(eye, target, [0, 1, 0]));
    gl.uniformMatrix4fv(where, false, new Float32Array(matrix));
    gl.drawArrays(gl.TRIANGLES, 0, mesh.count * 3);
  };
  let drag = null;
  const down = (event) => { drag = { x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 2 }; canvas.setPointerCapture && canvas.setPointerCapture(event.pointerId); };
  const move = (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    drag.x = event.clientX; drag.y = event.clientY;
    if (drag.pan) {
      const step = cam.distance / 600;
      cam.pan[0] -= Math.cos(cam.yaw) * dx * step; cam.pan[2] += Math.sin(cam.yaw) * dx * step; cam.pan[1] += dy * step;
    } else {
      cam.yaw -= dx * 0.01;
      cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + dy * 0.01));
    }
    draw();
  };
  const up = () => { drag = null; };
  const wheel = (event) => { event.preventDefault(); cam.distance = Math.max(radius * 0.2, Math.min(radius * 40, cam.distance * Math.exp(event.deltaY * 0.0015))); draw(); };
  const reset = () => { Object.assign(cam, start, { pan: [0, 0, 0] }); draw(); };
  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("wheel", wheel, { passive: false });
  canvas.addEventListener("dblclick", reset);
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  return { draw, stop: () => { const lose = gl.getExtension("WEBGL_lose_context"); if (lose) lose.loseContext(); } };
}
async function cvShowModel(body, src, file) {
  const canvas = h("canvas", { class: "model" }), note = h("div", { class: "note", text: "Loading the model…" });
  body.append(canvas, note);
  try {
    const mesh = await cvLoadModel(src, file);
    if (!canvas.isConnected) return;
    const box = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(box.width * dpr));
    canvas.height = Math.max(1, Math.round(box.height * dpr));
    const viewer = makeModelView(canvas, mesh);
    viewer.draw();
    if (cv.viewing) cv.viewing.stop = viewer.stop;
    note.textContent = mesh.count.toLocaleString() + " triangles · drag to turn, wheel to zoom, Shift-drag to move, double-click to reset";
  } catch (error) {
    note.textContent = "Could not show the model: " + error.message;
  }
}
// A 3D card shows the model itself: drawn once into a picture (in memory, per file), after the Quick Look one.
const cvStills = new Map();
async function cvModelStill(path, file) {
  const key = path + "\n" + file;
  if (cvStills.has(key)) return;
  const entry = { image: null };
  cvStills.set(key, entry);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 640; canvas.height = 480;
    const mesh = await cvLoadModel(cvMediaUrl(path, file, "&raw=1"), file, CV_STILL_LIMIT, path);
    const viewer = makeModelView(canvas, mesh);
    try {
      viewer.draw();
      const image = new Image();
      image.onload = () => { entry.image = image; cvDraw(); };
      image.src = canvas.toDataURL("image/png");
    } finally {
      viewer.stop(); // the picture is taken; the WebGL context is given back at once (browsers keep only ~16)
    }
  } catch {
    entry.failed = true;
  }
}

// ---- layers: like Photoshop's panel, topmost first (drawings over cards, cards over groups, as painted) ----
const CV_LAYERS_PREF = "desk-canvas-layers";
const CV_MAX_LAYER_ROWS = 500;
function layerName(key, item) {
  const clip = (text) => { const t = String(text || "").replace(/\s+/g, " ").trim(); return t.length > 40 ? t.slice(0, 39) + "\u2026" : t; };
  if (key[0] === "x") return item.type === "text" ? clip(item.text) || "Text" : item.type === "paint" ? "Fill" : CV_LABELS[item.type] || item.type;
  if (item.type === "group") return clip(item.label) || "Group";
  if (item.type === "file") return clip(fileLabel(item.file)) || "File";
  if (item.type === "link") return clip(item.url) || "Link";
  return clip(item.text) || "Empty card";
}
function layerIcon(row) {
  const type = row.item.type;
  if (row.key[0] === "x") return type === "paint" ? "fill" : CV_ICONS[type] ? type : "rectangle";
  return { group: "group", file: "attach", link: "link" }[type] || "card";
}
// Rows topmost first: the drawings and the cards outside groups under their own headings, then each group with the
// cards inside the smallest group around them, like layers inside a folder. `folded` holds the keys of headings and
// groups shown closed (one row with the name and a count).
function layerRows(doc, folded = new Set()) {
  const rows = [], elements = docElements(doc, true), nodes = docNodes(doc, true);
  const folder = (head, items) => {
    const shut = folded.has(head.key);
    rows.push({ ...head, depth: 0, count: items.length, folded: shut });
    if (!shut) for (const item of items) rows.push({ ...item, depth: 1 });
  };
  const topFirst = (list, kind) => list.slice().reverse().map((item) => ({ key: cvKey(kind, item), item }));
  if (elements.length) folder({ key: "sec:drawings", section: true, name: "Drawings" }, topFirst(elements, "x"));
  const groups = nodes.filter((n) => n.type === "group"), cards = nodes.filter((n) => n.type !== "group"), owner = new Map();
  for (const card of cards) {
    let best = null;
    for (const group of groups) if (boxInside(card, group) && (!best || group.width * group.height < best.width * best.height)) best = group;
    if (best) owner.set(card.id, best.id);
  }
  const loose = cards.filter((card) => !owner.has(card.id));
  if (loose.length) folder({ key: "sec:cards", section: true, name: groups.length ? "Cards outside groups" : "Cards" }, topFirst(loose, "n"));
  for (let i = groups.length - 1; i >= 0; i--) {
    folder({ key: cvKey("n", groups[i]), item: groups[i] }, topFirst(cards.filter((card) => owner.get(card.id) === groups[i].id), "n"));
  }
  return rows;
}
// Which headings and groups are folded, per canvas, in this browser (localStorage; the file never changes).
const CV_FOLDED_PREF = "desk-canvas-folded";
function cvReadFolded() {
  try {
    const all = JSON.parse(localStorage.getItem(CV_FOLDED_PREF) || "{}");
    return all && typeof all === "object" && !Array.isArray(all) ? all : {};
  } catch {
    return {};
  }
}
function cvFolded() {
  if (!cv.folded || cv.folded.path !== cv.path) {
    const keys = cvReadFolded()[cv.path];
    cv.folded = { path: cv.path, keys: new Set(Array.isArray(keys) ? keys.filter((key) => typeof key === "string") : []) };
  }
  return cv.folded.keys;
}
function cvSaveFolded() {
  const all = cvReadFolded(), keys = cvFolded();
  delete all[cv.path]; // written last again, so the oldest canvases are the ones forgotten past 50
  if (keys.size) all[cv.path] = [...keys].slice(0, 500);
  const paths = Object.keys(all);
  for (const old of paths.slice(0, Math.max(0, paths.length - 50))) delete all[old];
  try { localStorage.setItem(CV_FOLDED_PREF, JSON.stringify(all)); } catch { /* private mode: not remembered */ }
}
function cvToggleFold(key) {
  const keys = cvFolded();
  if (keys.has(key)) keys.delete(key); else keys.add(key);
  cvSaveFolded();
  cvRenderLayers();
}
// Fold or open every heading and group at once.
function cvFoldAll(fold) {
  const keys = cvFolded();
  keys.clear();
  if (fold && cv.doc) for (const row of layerRows(cv.doc)) if (row.depth === 0 && row.count) keys.add(row.key);
  cvSaveFolded();
  cvRenderLayers();
}
// The eye: hidden things are kept in the file (unlawHidden) but not painted, picked, filled or exported.
// A group takes everything inside it along.
function cvToggleHidden(key) {
  const item = cv.doc && cvLookup(cv.doc, key);
  if (!item) return;
  const hide = !cvHidden(item);
  const keys = [key, ...(key[0] === "n" && item.type === "group" ? containedIds(cv.doc, item) : [])];
  for (const k of keys) {
    const it = cvLookup(cv.doc, k);
    if (!it) continue;
    if (hide) it.unlawHidden = true; else delete it.unlawHidden;
  }
  if (hide) cv.sel = cv.sel.filter((k) => !keys.includes(k));
  cvCommit(hide ? "hide" : "show");
}
// Dropping a row on another of the same kind puts it at that place in the drawing order.
function cvReorderLayer(from, to) {
  if (!cv.doc || from === to || from[0] !== to[0] || from[0] === "e") return;
  const list = cvList(cv.doc, from[0]), a = list.indexOf(cvLookup(cv.doc, from)), b = list.indexOf(cvLookup(cv.doc, to));
  if (a < 0 || b < 0) return;
  list.splice(b, 0, ...list.splice(a, 1));
  cvCommit("order");
}
function cvToggleLayers() {
  cv.layers = !cv.layers;
  localStorage.setItem(CV_LAYERS_PREF, cv.layers ? "1" : "0");
  cvRenderLayers();
  cvResize();
}
function cvFoldArrow(row) {
  if (!row.count) return h("span", { class: "fold" });
  const arrow = h("button", { class: "fold", title: row.folded ? "Open" : "Fold", "aria-label": row.folded ? "Open" : "Fold", "aria-expanded": row.folded ? "false" : "true" }, cvIcon(row.folded ? "chevron" : "chevronDown"));
  arrow.addEventListener("click", (event) => { event.stopPropagation(); cvToggleFold(row.key); });
  return arrow;
}
function cvLayerRow(row) {
  if (row.section) {
    const node = h("div", { class: "row section" }, cvFoldArrow(row), h("span", { class: "name", text: row.name }), h("span", { class: "count", text: String(row.count) }));
    node.addEventListener("click", () => cvToggleFold(row.key));
    return node;
  }
  const hidden = cvHidden(row.item), picked = cv.sel.includes(row.key), group = row.item.type === "group";
  const eye = h("button", { class: "eye", title: hidden ? "Show" : "Hide", "aria-label": hidden ? "Show" : "Hide" }, cvIcon(hidden ? "eyeOff" : "eye"));
  eye.addEventListener("click", (event) => { event.stopPropagation(); cvToggleHidden(row.key); });
  const node = h("div", { class: "row" + (hidden ? " hidden" : "") + (picked ? " on" : "") + (row.depth ? " inner" : "") + (group ? " group" : ""), draggable: "true", title: "Click to select (Shift adds); drag onto another row to change the order" },
    group ? cvFoldArrow(row) : null, eye, cvIcon(layerIcon(row)), h("span", { class: "name", text: layerName(row.key, row.item) }),
    group && row.folded ? h("span", { class: "count", text: String(row.count) }) : null);
  node.addEventListener("click", (event) => {
    if (hidden) return;
    cvSelect(event.shiftKey ? [...new Set([...cv.sel, row.key])] : [row.key]);
  });
  node.addEventListener("dragstart", (event) => { cv.layerDrag = row.key; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", row.key); });
  node.addEventListener("dragover", (event) => { if (cv.layerDrag && cv.layerDrag[0] === row.key[0]) event.preventDefault(); });
  node.addEventListener("drop", (event) => {
    event.preventDefault();
    const from = cv.layerDrag;
    cv.layerDrag = null;
    if (from) cvReorderLayer(from, row.key);
  });
  node.addEventListener("dragend", () => { cv.layerDrag = null; });
  return node;
}
function cvRenderLayers() {
  const panel = cv.ui.layers;
  if (!panel) return;
  panel.classList.toggle("on", cv.layers);
  if (cv.ui.layersButton) cv.ui.layersButton.classList.toggle("on", cv.layers);
  if (!cv.layers) return;
  panel.textContent = "";
  const foldAll = h("button", { class: "all", title: "Fold every group" }, cvIcon("chevron"));
  foldAll.addEventListener("click", () => cvFoldAll(true));
  const openAll = h("button", { class: "all", title: "Open every group" }, cvIcon("chevronDown"));
  openAll.addEventListener("click", () => cvFoldAll(false));
  panel.append(h("div", { class: "head" }, h("b", { text: "Layers" }), h("span", { class: "n", text: "topmost first" }), h("span", { class: "spacer" }), foldAll, openAll));
  if (!cv.doc) return;
  const rows = layerRows(cv.doc, cvFolded()), list = h("div", { class: "list" });
  for (const row of rows.slice(0, CV_MAX_LAYER_ROWS)) list.append(cvLayerRow(row));
  if (rows.length > CV_MAX_LAYER_ROWS) list.append(h("div", { class: "empty", text: rows.length - CV_MAX_LAYER_ROWS + " more not listed" }));
  if (!rows.length) list.append(h("div", { class: "empty", text: "Nothing on this canvas yet." }));
  panel.append(list);
}

// ---- actions ----
function cvDelete() {
  if (!cv.sel.length) return;
  removeItems(cv.doc, cv.sel);
  cv.sel = [];
  cvCommit("delete");
  cvSync();
}

function cvGroup() {
  if (!cv.doc || !cv.sel.length) { toast("Select something to group"); return; }
  const key = groupAround(cv.doc, cv.sel, cvId());
  if (!key) { toast("Select a card or drawing to group"); return; }
  cvSelect([key]);
  cvCommit("group");
}

function cvCopy() {
  if (!cv.sel.length) return;
  cv.clip = copyItems(cv.doc, cv.sel);
  cv.pasted = 0;
}

function cvPaste(bundle) {
  if (!bundle || !(bundle.nodes.length + bundle.elements.length)) return;
  cv.pasted++;
  cvSelect(pasteItems(cv.doc, bundle, 20 * cv.pasted, cvId));
  cvCommit("paste");
}

function cvDuplicate() {
  if (!cv.sel.length) return;
  cv.pasted = 0;
  cvPaste(copyItems(cv.doc, cv.sel));
  cv.pasted = 0;
}

function cvNudge(dx, dy) {
  const keys = new Set(cv.sel.filter((k) => k[0] !== "e"));
  for (const k of cv.sel) {
    const item = cvLookup(cv.doc, k);
    if (k[0] === "n" && item && item.type === "group") for (const inner of containedIds(cv.doc, item)) keys.add(inner);
  }
  if (!keys.size) return;
  moveItems(cv.doc, [...keys], dx, dy);
  cvCommit("nudge");
}

function cvSelectAll() {
  cvSelect([...docNodes(cv.doc).map((n) => cvKey("n", n)), ...docEdges(cv.doc).map((e) => cvKey("e", e)), ...docElements(cv.doc).map((el) => cvKey("x", el))]);
}

const CV_ARROWS = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

// Returns true when the key was a canvas shortcut; the page's own keys never run in this view.
function cvZoomBy(factor) {
  cvSetView(zoomAt(cv.view, cv.w / 2, cv.h / 2, factor));
}

// The slider is logarithmic: fine steps among thin lines, big ones toward 100.
const widthToSlider = (width) => Math.round((Math.log(Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, width))) / Math.log(CV_MAX_WIDTH)) * 1000);
const sliderToWidth = (value) => Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, Math.round(Math.exp((value / 1000) * Math.log(CV_MAX_WIDTH)))));

// A width typed by hand: digits only, kept within 1-100; anything else puts the current width back.
function cvTypedWidth(text) {
  const value = Number.parseInt(String(text).trim(), 10);
  if (Number.isFinite(value) && /^\s*\d+\s*$/.test(String(text))) {
    const width = Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, value));
    if (width !== cv.style.width) cvStyle({ width });
  }
  cvSync();
}

// [ and ] (or - and =) like Photoshop's brush size: 1 below 10, 5 below 50, then 10.
function cvStepWidth(dir) {
  const w = cv.style.width, step = (dir > 0 ? w >= 50 : w > 50) ? 10 : (dir > 0 ? w >= 10 : w > 10) ? 5 : 1;
  const next = Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, w + dir * step));
  if (next !== w) cvStyle({ width: next });
}

function cvSetEraser(mode) {
  cv.eraser = mode;
  cvSavePrefs();
  cvSetTool("eraser");
}

// The bubble under an active tool's button: eraser mode, or how even the shapes are drawn.
function cvMenuItems(tool) {
  if (tool === "eraser") return CV_ERASERS.map((e) => ({ icon: e.icon, label: e.label, on: cv.eraser === e.mode, pick: () => cvSetEraser(e.mode) }));
  if (CV_SHAPE_CYCLE.includes(tool)) {
    return CV_ROUGH_LEVELS.map((l) => ({ num: String(l.level), label: l.label, on: cv.style.rough === l.rough, pick: () => { cvStyle({ rough: l.rough }); cvCloseMenu(); } }));
  }
  return null;
}

function cvOpenMenu(tool) {
  const menu = cv.ui.menu, items = cvMenuItems(tool);
  if (!menu || !items) return;
  menu.textContent = "";
  for (const item of items) {
    const button = h("button", { class: item.on ? "on" : "" }, item.icon ? cvIcon(item.icon) : h("span", { class: "num", text: item.num }), h("span", { text: item.label }));
    button.addEventListener("click", () => { item.pick(); cvCloseMenu(); });
    menu.append(button);
  }
  const anchor = cv.ui.tools[tool], box = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: 0, bottom: 0 };
  menu.style.left = Math.round(box.left) + "px";
  menu.style.top = Math.round(box.bottom + 6) + "px";
  menu.classList.add("on");
  cv.menu = tool;
}

function cvCloseMenu() {
  if (!cv.menu) return;
  cv.menu = "";
  if (cv.ui.menu) cv.ui.menu.classList.remove("on");
}

// A click on the active tool's button opens its menu; on another tool it switches.
function cvToolClick(tool) {
  if (cv.tool === tool && cvMenuItems(tool)) {
    if (cv.menu === tool) cvCloseMenu(); else cvOpenMenu(tool);
    return;
  }
  cvSetTool(tool);
}

function canvasKey(event) {
  if (event.key === "Escape" && cv.menu) { cvCloseMenu(); return true; }
  if (event.key === "Escape" && cv.viewing) { cvCloseView(); return true; }
  if (event.key === "Escape" && cv.inline) { cvCloseInline(); return true; }
  if (event.key === "Escape" && cv.gallery) { cvToggleGallery(false); return true; }
  if (cv.viewing || cv.gallery) return false;
  if (!cv.doc) return false;
  const key = event.key, mod = event.metaKey || event.ctrlKey;
  // Physical keys, so the shortcuts also work with a Russian (or any) keyboard layout.
  const code = event.code || "", physical = code.startsWith("Key") ? code.slice(3).toLowerCase() : code.startsWith("Digit") ? code.slice(5) : "";
  if (key === " " && !mod) { event.preventDefault(); cv.space = true; cvCursor(); return true; }
  if (code === "F7" || key === "F7") { event.preventDefault(); cvToggleLayers(); return true; }
  if (key === "Escape") {
    if ($("help").classList.contains("on")) return false;
    if (cv.thread) { cv.thread = null; cvDraw(); return true; }
    if (cv.drag) { cvCancelDrag(); return true; }
    if (cv.sel.length) { cvSelect([]); return true; }
    if (cv.tool !== "select") { cvSetTool("select"); return true; }
    return false;
  }
  if (mod) {
    if (code === "Equal" || code === "NumpadAdd" || code === "Minus" || code === "NumpadSubtract") {
      event.preventDefault();
      cvZoomBy(code === "Equal" || code === "NumpadAdd" ? 1.25 : 0.8);
      return true;
    }
    const letter = physical || (key.length === 1 ? key.toLowerCase() : "");
    if (!letter || !"zyacvdg0".includes(letter)) return false;
    if (letter !== "v") event.preventDefault();
    if (letter === "z") { if (event.shiftKey) cvRedo(); else cvUndo(); }
    else if (letter === "y") cvRedo();
    else if (letter === "a") cvSelectAll();
    else if (letter === "c") cvCopy();
    else if (letter === "v") {
      // The browser's paste event follows the key when the clipboard has text: a link there becomes a link card;
      // otherwise the canvas's own copied items are pasted.
      clearTimeout(cv.pasteWait);
      cv.pasteWait = setTimeout(() => { cv.pasteWait = 0; cvPaste(cv.clip); }, 80);
      return true;
    }
    else if (letter === "g") cvGroup();
    else if (letter === "0") cvFit();
    else cvDuplicate();
    return true;
  }
  if (event.altKey) return false;
  if (key === "Delete" || key === "Backspace") { event.preventDefault(); cvDelete(); return true; }
  if (CV_ARROWS[key]) {
    if (!cv.sel.length) return false;
    event.preventDefault();
    const step = event.shiftKey ? 10 : 1;
    cvNudge(CV_ARROWS[key][0] * step, CV_ARROWS[key][1] * step);
    return true;
  }
  if (code === "BracketLeft" || code === "BracketRight") { cvStepWidth(code === "BracketLeft" ? -1 : 1); return true; }
  if (code === "Minus" || code === "Equal" || code === "NumpadSubtract" || code === "NumpadAdd") { cvStepWidth(code === "Minus" || code === "NumpadSubtract" ? -1 : 1); return true; }
  const letter = physical || (key.length === 1 ? key.toLowerCase() : "");
  if (letter === "e" && event.shiftKey) {
    const mode = cv.eraser === "part" ? "object" : "part";
    cvSetEraser(mode);
    toast("Eraser: " + CV_ERASERS.find((e) => e.mode === mode).label.toLowerCase());
    return true;
  }
  if (letter === "u" && event.shiftKey) {
    const at = CV_SHAPE_CYCLE.indexOf(cv.tool);
    cvSetTool(CV_SHAPE_CYCLE[(at + 1) % CV_SHAPE_CYCLE.length]);
    return true;
  }
  if (CV_BY_KEY[letter]) { cvSetTool(CV_BY_KEY[letter]); return true; }
  if (letter === "d") { cvStyle({ stroke: CV_INK[0] }); return true; }
  if (letter === "f") { cvFit(); return true; }
  return false;
}

// ---- toolbar and view ----
function cvFillPick() {
  if (cv.gallery) cvRenderGallery();
  if (cv.ui.back) {
    cv.ui.back.style.display = cv.back.length ? "" : "none";
    cv.ui.back.title = cv.back.length ? "Back to " + cv.back[cv.back.length - 1].split("/").pop().replace(CV_CANVAS_FILE, "") : "Back";
  }
  const field = cv.ui.name;
  if (field) {
    if (document.activeElement !== field) field.value = cv.name;
    field.disabled = !cv.path;
  }
}

// ---- the canvas gallery: every canvas as a thumbnail, open with a click, delete to the Trash, drop to import ----
const cvThumbs = new Map(); // path -> {modified, shape} read through /api/canvas/peek (does not switch canvases)
function cvToggleGallery(open) {
  cv.gallery = typeof open === "boolean" ? open : !cv.gallery;
  if (cv.gallery) loadCanvasList();
  cvRenderGallery();
  if (cv.gallery && cv.ui.gallerySearch && typeof cv.ui.gallerySearch.focus === "function") cv.ui.gallerySearch.focus();
}
// The gallery's favorites and groups are a list of paths on the server (canvases.json); the files never move.
function cleanShelf(raw) {
  const paths = (list) => (Array.isArray(list) ? list.filter((path) => typeof path === "string") : []);
  const groups = raw && Array.isArray(raw.groups) ? raw.groups.filter((group) => group && typeof group.name === "string").map((group) => ({ name: group.name, paths: paths(group.paths) })) : [];
  return { favorites: paths(raw && raw.favorites), groups };
}
function shelfFavorite(shelf, path) {
  const on = shelf.favorites.includes(path);
  return { ...shelf, favorites: on ? shelf.favorites.filter((item) => item !== path) : [...shelf.favorites, path] };
}
// Into the group named `name` (out of any other), or out of every group with null.
function shelfMove(shelf, path, name) {
  return { ...shelf, groups: shelf.groups.map((group) => ({ name: group.name, paths: [...group.paths.filter((item) => item !== path), ...(group.name === name ? [path] : [])] })) };
}
const shelfName = (name) => String(name ?? "").replace(/\s+/g, " ").trim();
function shelfAddGroup(shelf, name) {
  const clean = shelfName(name);
  if (!clean || clean.length > 80 || shelf.groups.some((group) => group.name.toLowerCase() === clean.toLowerCase())) return null;
  return { ...shelf, groups: [...shelf.groups, { name: clean, paths: [] }] };
}
function shelfRenameGroup(shelf, from, to) {
  const clean = shelfName(to);
  if (!clean || clean.length > 80 || shelf.groups.some((group) => group.name !== from && group.name.toLowerCase() === clean.toLowerCase())) return null;
  return { ...shelf, groups: shelf.groups.map((group) => (group.name === from ? { ...group, name: clean } : group)) };
}
function shelfRemoveGroup(shelf, name) {
  return { ...shelf, groups: shelf.groups.filter((group) => group.name !== name) };
}
// Favorites first (they also stay in their group), then each group, then the canvases in no group. A search keeps
// the canvases whose name holds every word of it (case ignored) and drops the sections it leaves empty.
function galleryMatch(item, search) {
  const name = String(item.name ?? "").toLowerCase();
  return String(search ?? "").toLowerCase().split(/\s+/).filter(Boolean).every((word) => name.includes(word));
}
function gallerySections(items, shelf, search = "") {
  const sections = shelfSections(items, shelf);
  if (!String(search).trim()) return sections;
  return sections.map((section) => ({ ...section, items: section.items.filter((item) => galleryMatch(item, search)) })).filter((section) => section.items.length);
}
function shelfSections(items, shelf) {
  const byPath = new Map(items.map((item) => [item.path, item])), grouped = new Set(), sections = [];
  const pick = (paths) => paths.map((path) => byPath.get(path)).filter(Boolean);
  const favorites = pick(shelf.favorites);
  if (favorites.length) sections.push({ kind: "favorites", name: "Favorites", items: favorites });
  for (const group of shelf.groups) {
    group.paths.forEach((path) => grouped.add(path));
    sections.push({ kind: "group", name: group.name, items: pick(group.paths) });
  }
  sections.push({ kind: "other", name: shelf.groups.length ? "Not in a group" : "All canvases", items: items.filter((item) => !grouped.has(item.path)) });
  return sections;
}
async function cvSaveShelf(next) {
  if (!next) return false;
  cv.shelf = next;
  cvRenderGallery();
  const { status, data } = await api("POST", "/api/canvas/shelf", { shelf: next });
  if (status !== 200) { toast(data.error || "Could not save the gallery"); await loadCanvasList(); return false; }
  if (Array.isArray(data.items)) cv.items = data.items;
  cv.shelf = cleanShelf(data.shelf);
  cvRenderGallery();
  return true;
}
function cvNewGroup() {
  const name = prompt("Name of the new group");
  if (name === null) return;
  const next = shelfAddGroup(cv.shelf, name);
  if (!next) { toast("A group needs a name of its own (up to 80 characters)"); return; }
  cvSaveShelf(next);
}
function cvGallerySection(section) {
  const button = (icon, title, run) => {
    const b = h("button", { class: "mini", title, "aria-label": title }, cvIcon(icon));
    b.addEventListener("click", (event) => { event.stopPropagation(); run(); });
    return b;
  };
  const tools = section.kind === "group" ? [
    button("edit", "Rename the group", () => {
      const name = prompt("New name of the group", section.name);
      if (name === null || shelfName(name) === section.name) return;
      const next = shelfRenameGroup(cv.shelf, section.name, name);
      if (!next) toast("That name is empty or taken"); else cvSaveShelf(next);
    }),
    button("trash", "Remove the group (its canvases stay)", () => {
      if (confirm("Remove the group \u201c" + section.name + "\u201d?\nIts canvases stay where they are.")) cvSaveShelf(shelfRemoveGroup(cv.shelf, section.name));
    }),
  ] : [];
  const icon = section.kind === "favorites" ? "star" : section.kind === "group" ? "folder" : "gallery";
  const head = h("div", { class: "section " + section.kind }, cvIcon(icon), h("b", { text: section.name }), h("span", { class: "count", text: String(section.items.length) }), ...tools);
  const grid = h("div", { class: "grid" });
  for (const item of section.items) grid.append(cvGalleryTile(item));
  if (!section.items.length) grid.append(h("div", { class: "empty", text: section.kind === "group" ? "Drag canvases here." : "No canvases yet: make one with New, or drop a .canvas file here." }));
  const box = h("div", { class: "shelf" }, head, grid);
  // Dropping a tile on a group puts the canvas in it; on "Not in a group", takes it out.
  if (section.kind !== "favorites") {
    box.addEventListener("dragover", (event) => { if (cv.galleryDrag) { event.preventDefault(); box.classList.add("drop"); } });
    box.addEventListener("dragleave", (event) => { if (!box.contains(event.relatedTarget)) box.classList.remove("drop"); });
    box.addEventListener("drop", (event) => {
      box.classList.remove("drop");
      const path = cv.galleryDrag;
      cv.galleryDrag = null;
      if (!path) return;
      event.preventDefault();
      event.stopPropagation();
      cvSaveShelf(shelfMove(cv.shelf, path, section.kind === "group" ? section.name : null));
    });
  }
  return box;
}
function cvRenderGallery() {
  const panel = cv.ui.gallery;
  if (!panel) return;
  panel.classList.toggle("on", Boolean(cv.gallery));
  if (cv.ui.pick) cv.ui.pick.classList.toggle("on", Boolean(cv.gallery));
  if (!cv.gallery) return;
  // The search field survives a redraw (typing would lose focus otherwise): only the sections are rebuilt.
  if (!cv.ui.gallerySearch) {
    const field = h("input", { class: "search", type: "search", placeholder: "Search by name", spellcheck: "false", "aria-label": "Search canvases by name" });
    field.addEventListener("input", () => { cv.gallerySearch = field.value; cvRenderShelves(); });
    field.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && field.value) { event.stopPropagation(); event.preventDefault(); field.value = ""; cv.gallerySearch = ""; cvRenderShelves(); }
      else if (event.key === "Enter") { const first = cv.ui.galleryList && cv.ui.galleryList.querySelector && cv.ui.galleryList.querySelector(".tile"); if (first) first.click(); }
    });
    cv.ui.gallerySearch = field;
  }
  const search = cv.ui.gallerySearch;
  search.value = cv.gallerySearch;
  panel.textContent = "";
  const button = (icon, text, run, title) => {
    const b = h("button", { title: title || text }, cvIcon(icon), text);
    b.addEventListener("click", run);
    return b;
  };
  panel.append(h("div", { class: "head" },
    h("b", { text: "Canvases" }),
    search,
    h("span", { class: "hint", text: "Click to open \u00b7 drag a canvas onto a group \u00b7 drop a .canvas file here to import it" }),
    h("span", { class: "spacer" }),
    button("folder", "New group", cvNewGroup, "A group in this gallery; the files stay where they are"),
    button("plus", "New", () => { cvToggleGallery(false); cvNew(); }),
    button("folder", "Open file\u2026", () => { cvToggleGallery(false); cvChoose(); }, "Open a .canvas file anywhere on the Mac"),
    button("close", "", () => cvToggleGallery(false), "Close (Esc)")));
  cv.ui.galleryList = h("div", { class: "shelves" });
  panel.append(cv.ui.galleryList);
  cvRenderShelves();
}
function cvRenderShelves() {
  const list = cv.ui.galleryList;
  if (!list) return;
  list.textContent = "";
  const items = cv.items.some((item) => item.path === cv.path) || !cv.path ? cv.items : [{ path: cv.path, name: cv.name || cv.path }, ...cv.items];
  const sections = gallerySections(items, cv.shelf, cv.gallerySearch);
  for (const section of sections) list.append(cvGallerySection(section));
  if (!sections.length) list.append(h("div", { class: "empty", text: "No canvas is named like \u201c" + cv.gallerySearch.trim() + "\u201d." }));
}
function cvGalleryTile(item) {
  const thumb = h("canvas", { class: "thumb", width: "480", height: "300" });
  const when = Number.isFinite(item.modified) ? new Date(item.modified * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";
  const action = (icon, cls, title, run) => {
    const b = h("button", { class: cls, title, "aria-label": title + ": " + item.name }, cvIcon(icon));
    b.addEventListener("click", (event) => { event.stopPropagation(); run(); });
    return b;
  };
  const favorite = cv.shelf.favorites.includes(item.path);
  const actions = h("div", { class: "acts" },
    action("star", "fav" + (favorite ? " on" : ""), favorite ? "Remove from favorites" : "Add to favorites", () => cvSaveShelf(shelfFavorite(cv.shelf, item.path))),
    cv.doc && cv.path && item.path !== cv.path ? action("link", "lnk", "Put a link to this canvas on the open one", () => cvAddCanvasLink(item)) : null,
    action("trash", "del", "Move to the Trash", () => cvDeleteCanvas(item)));
  const tile = h("div", { class: "tile" + (item.path === cv.path ? " on" : ""), title: item.path, draggable: "true" },
    thumb, h("div", { class: "meta" }, h("span", { class: "name", text: item.name }), h("span", { class: "when", text: when })), actions);
  tile.addEventListener("click", async () => { cvToggleGallery(false); if (item.path !== cv.path) await cvOpen(item.path, false); });
  tile.addEventListener("dragstart", (event) => { cv.galleryDrag = item.path; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", item.name); });
  tile.addEventListener("dragend", () => { cv.galleryDrag = null; });
  cvDrawThumb(thumb, item);
  return tile;
}
async function cvDrawThumb(canvas, item) {
  let cached = cvThumbs.get(item.path);
  if (!cached || cached.modified !== item.modified) {
    const { status, data } = await api("GET", "/api/canvas/peek?path=" + encodeURIComponent(item.path));
    if (status !== 200) return;
    cached = { modified: item.modified, shape: data };
    cvThumbs.set(item.path, cached);
  }
  const ctx = canvas.getContext && canvas.getContext("2d");
  if (!ctx) return;
  const doc = item.path === cv.path && cv.doc ? cv.doc : cached.shape.canvas, width = 240, height = 150;
  paintScene({ ctx, doc, view: fitView(sceneBounds(doc), width, height, 12), w: width, h: height, pal: cvPalette(), scale: 2, ui: null, images: null, flat: true });
}
async function cvDeleteCanvas(item) {
  if (!confirm("Move \u201c" + item.name + "\u201d to the Trash?\nIts attached files stay in the folder.")) return;
  const open = item.path === cv.path;
  // A save on its way would write the file again after it went to the Trash.
  while (cv.saving) await cv.saving;
  const { status, data } = await api("POST", "/api/canvas/delete", { path: item.path });
  if (status !== 200) { toast(data.error || "Could not delete the canvas"); return; }
  if (open) { clearTimeout(cv.saveTimer); cv.saveTimer = 0; cv.dirty = false; }
  cvThumbs.delete(item.path);
  cv.items = Array.isArray(data.items) ? data.items : [];
  if (data.shelf) cv.shelf = cleanShelf(data.shelf);
  toast("\u201c" + item.name + "\u201d is in the Trash");
  if (open) {
    cv.doc = null; cv.path = ""; cv.name = ""; cv.version = ""; cv.sel = []; cv.hist = null;
    localStorage.setItem("desk-canvas", "");
    const next = data.current || (cv.items[0] && cv.items[0].path);
    if (next) await cvOpen(next, false);
    cvSync();
    cvDraw();
  }
  cvFillPick();
}
// A .canvas file dropped on the page: the browser gives only its contents, so it becomes a new canvas in the
// canvas folder. Files it names by relative path are not copied along.
async function cvImportCanvas(file) {
  let canvas;
  try { canvas = JSON.parse(await file.text()); } catch { toast(file.name + " is not a canvas file"); return false; }
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvas/import", { name: file.name, canvas });
  if (status !== 200) { toast(data.error || "Could not import " + file.name); return false; }
  cvToggleGallery(false);
  await cvShow(data);
  toast("Opened " + file.name + " as \u201c" + data.name + "\u201d in the canvas folder");
  return true;
}
const cvIsCanvasFile = (file) => /\.canvas$/i.test(String(file && file.name || ""));
async function cvDropFiles(files, at) {
  const list = Array.from(files || []), canvases = list.filter(cvIsCanvasFile), others = list.filter((file) => !cvIsCanvasFile(file));
  for (const file of canvases.slice(0, 5)) await cvImportCanvas(file);
  if (others.length) await cvAddFiles(others, canvases.length ? null : at);
}

function cvBuildBar() {
  const ui = { tools: {}, ink: [] };
  const press = (button, action) => () => { action(); button.blur(); };
  const iconButton = (icon, title, run, weight) => {
    const button = h("button", { title, "aria-label": title }, cvIcon(icon, weight));
    button.addEventListener("click", press(button, run));
    return button;
  };
  const toolButtons = Object.keys(CV_TOOLS).map((tool) => {
    const keys = CV_TOOLS[tool], shape = CV_SHAPE_CYCLE.includes(tool);
    const hint = [keys ? keys[0].toUpperCase() : "", shape ? "Shift+U cycles shapes" : ""].filter(Boolean).join("; ");
    const extra = tool === "thread" ? ". Click a spot on a card, then a spot on another card (on empty canvas: a new card)" : tool === "fill" ? ". Floods the clicked color; Alt+click clears" : tool === "eraser" ? ". Click again: whole object or only where it passes (Shift+E)" : shape ? ". Click again: how even" : "";
    const button = iconButton(tool, CV_LABELS[tool] + (hint ? " (" + hint + ")" : "") + extra, () => cvToolClick(tool));
    if (tool === "eraser" || shape) button.classList.add("more");
    ui.tools[tool] = button;
    return button;
  });
  const swatches = CV_INK.map((color) => {
    const button = h("button", { class: "swatch", title: color, style: "background:" + color });
    button.addEventListener("click", press(button, () => cvStyle({ stroke: color })));
    ui.ink.push(button);
    return button;
  });
  ui.custom = h("input", { type: "color", value: "#3a6df0", "aria-label": "Any color" });
  ui.custom.addEventListener("input", () => cvStyle({ stroke: ui.custom.value.toLowerCase() }));
  ui.customWrap = h("label", { class: "swatch custom", title: "Any color\u2026" }, ui.custom);
  ui.fill = iconButton("filled", "Draw shapes filled with the color", () => cvStyle({ fill: !cv.style.fill }));
  ui.width = h("input", { class: "cvwidth", type: "range", min: "0", max: "1000", step: "1", title: "Stroke width, 1-100 ([ ] or - = step)", "aria-label": "Stroke width" });
  ui.width.addEventListener("input", () => cvStyle({ width: sliderToWidth(Number(ui.width.value)) }));
  ui.width.addEventListener("change", () => ui.width.blur());
  // The number next to the slider is a field: type an exact width, Enter applies, Escape cancels.
  ui.widthValue = h("input", { class: "cvwidthval", type: "text", inputmode: "numeric", maxlength: "3", spellcheck: "false", title: "Stroke width: type 1-100, Enter applies", "aria-label": "Stroke width in pixels" });
  ui.widthValue.addEventListener("focus", () => ui.widthValue.select && ui.widthValue.select());
  ui.widthValue.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); ui.widthValue.blur(); }
    else if (event.key === "Escape") { ui.widthValue.value = String(cv.style.width); ui.widthValue.blur(); }
  });
  ui.widthValue.addEventListener("blur", () => cvTypedWidth(ui.widthValue.value));
  ui.menu = h("div", { class: "cvmenu" });
  ui.undo = iconButton("undo", "Undo (Cmd/Ctrl+Z)", cvUndo);
  ui.redo = iconButton("redo", "Redo (Shift+Cmd/Ctrl+Z)", cvRedo);
  ui.name = h("input", { class: "cvname", type: "text", spellcheck: "false", title: "Canvas name: click to rename", "aria-label": "Canvas name" });
  ui.name.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); ui.name.blur(); }
    else if (event.key === "Escape") { ui.name.value = cv.name; ui.name.blur(); }
  });
  ui.name.addEventListener("blur", () => cvRename(ui.name.value));
  ui.back = iconButton("back", "Back", cvGoBack);
  ui.back.style.display = "none";
  ui.pick = h("button", { class: "cvpick", title: "All canvases: open, favorites, groups, links, delete, drop a .canvas file to import" }, cvIcon("gallery"), "Canvases");
  ui.pick.addEventListener("click", press(ui.pick, cvToggleGallery));
  ui.zoom = h("span", { class: "cvzoom", title: "Zoom" });
  ui.layersButton = iconButton("layers", "Layers: every card, group and drawing; the eye hides one (F7)", cvToggleLayers);
  ui.cork = iconButton("pin", "Detective board: cork, paper notes, photos and red thread between pins", cvToggleCork);
  ui.files = h("input", { type: "file", multiple: true, style: "display:none", "aria-hidden": "true" });
  ui.files.addEventListener("change", () => { const picked = Array.from(ui.files.files || []); ui.files.value = ""; cvAddFiles(picked); });
  ui.add = h("button", { title: "Add files: pictures, PDF, documents, anything (or drop them on the canvas)", "aria-label": "Add files" }, cvIcon("attach"), "Add");
  ui.add.addEventListener("click", press(ui.add, () => ui.files.click()));
  ui.status = h("span", { class: "cvstatus" });
  ui.root = h("div", { class: "cvbar" },
    ui.name,
    h("div", { class: "group" }, ui.back, ui.pick, iconButton("plus", "New canvas (canvas-1, canvas-2, \u2026)", cvNew), iconButton("folder", "Open a canvas file\u2026", cvChoose)),
    h("div", { class: "group" }, toolButtons),
    h("div", { class: "group" }, swatches, ui.customWrap),
    h("div", { class: "group" }, ui.fill, ui.width, ui.widthValue),
    h("div", { class: "group" }, iconButton("group", "Group the selection (Cmd/Ctrl+G)", cvGroup), ui.undo, ui.redo),
    h("div", { class: "group" }, iconButton("fit", "Fit everything in view (Cmd/Ctrl+0)", cvFit), ui.zoom),
    h("div", { class: "group" }, ui.layersButton, ui.cork, iconButton("export", "Export the canvas as a PNG image", cvExport)),
    ui.status,
    h("div", { class: "group cvadd" }, ui.add, ui.files));
  return ui;
}

function renderCanvas(main) {
  if (main.querySelector(".cv")) { cvResize(); return; }
  main.textContent = "";
  const ui = cvBuildBar();
  const canvas = h("canvas", { class: "cvcanvas", tabindex: "0" });
  ui.editor = h("textarea", { class: "cvedit", spellcheck: "false" });
  ui.empty = h("div", { class: "cvempty" }, h("div", { text: "No canvas yet" }), h("button", { class: "primary", text: "New canvas", onclick: cvNew }));
  ui.inline = h("div", { class: "cvinline" });
  ui.players = h("div", { class: "cvplayers", "aria-hidden": "true" });
  const stage = h("div", { class: "cvstage" }, canvas, ui.inline, ui.players, ui.editor, ui.empty);
  ui.layers = h("div", { class: "cvlayers" });
  cv.layers = localStorage.getItem(CV_LAYERS_PREF) === "1";
  ui.gallery = h("div", { class: "cvgallery" });
  ui.view = h("div", { class: "cvview" });
  main.append(h("div", { class: "cv" }, ui.root, h("div", { class: "cvbody" }, stage, ui.layers, ui.gallery, ui.view), ui.menu));
  ui.gallery.addEventListener("dragover", (event) => { if (cvHasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; } });
  ui.gallery.addEventListener("drop", (event) => {
    if (!cvHasFiles(event)) return;
    event.preventDefault();
    const files = Array.from(event.dataTransfer.files || []).filter(cvIsCanvasFile);
    if (!files.length) { toast("Drop .canvas files here; other files go onto an open canvas"); return; }
    cvDropFiles(files);
  });
  // Files dragged in from Finder (or the desktop) are pinned where they are dropped.
  stage.addEventListener("dragover", (event) => {
    if (!cvHasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    stage.classList.add("dropping");
  });
  stage.addEventListener("dragleave", (event) => { if (!stage.contains(event.relatedTarget)) stage.classList.remove("dropping"); });
  stage.addEventListener("drop", (event) => {
    stage.classList.remove("dropping");
    if (!cvHasFiles(event)) return;
    event.preventDefault();
    cvDropFiles(event.dataTransfer.files, cvPoint(event).w);
  });
  cv.el = canvas;
  cv.ctx = canvas.getContext("2d");
  cv.ui = ui;
  canvas.addEventListener("pointerdown", cvDown);
  canvas.addEventListener("pointermove", cvMove);
  canvas.addEventListener("pointerup", cvUp);
  canvas.addEventListener("pointercancel", cvCancelDrag);
  canvas.addEventListener("pointerleave", () => { if (cv.cursor) { cv.cursor = null; cvDraw(); } });
  canvas.addEventListener("dblclick", cvDouble);
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  canvas.addEventListener("wheel", cvWheel, { passive: false });
  canvas.addEventListener("gesturestart", (event) => { event.preventDefault(); cv.gesture = cv.view.z; });
  canvas.addEventListener("gesturechange", (event) => {
    event.preventDefault();
    const box = canvas.getBoundingClientRect();
    cvSetView(zoomAt(cv.view, event.clientX - box.left, event.clientY - box.top, (cv.gesture * event.scale) / cv.view.z));
  });
  ui.editor.addEventListener("blur", cvEndEdit);
  cvResize();
  cvSync();
  cvCursor();
  cvFillPick();
  cvStart();
}

window.addEventListener("resize", () => { if (state.view === "canvas") cvResize(); });
document.addEventListener("keyup", (event) => { if (event.key === " " && cv.space) { cv.space = false; cvCursor(); } });
// A press anywhere outside the open tool menu (and its button) closes it.
document.addEventListener("pointerdown", (event) => {
  if (!cv.menu || !cv.ui.menu) return;
  const button = cv.ui.tools[cv.menu];
  if (cv.ui.menu.contains(event.target) || (button && button.contains(event.target))) return;
  cvCloseMenu();
}, true);
document.addEventListener("visibilitychange", () => { if (document.hidden && state.view === "canvas") saveCanvas(); });
// A file dropped beside the canvas must not make the browser leave the page to show it.
for (const type of ["dragover", "drop"]) document.addEventListener(type, (event) => { if (state.view === "canvas" && cvHasFiles(event)) event.preventDefault(); });
$("theme").addEventListener("click", () => { if (state.view === "canvas") cvDraw(); });
document.addEventListener("paste", (event) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || "");
  if (state.view !== "canvas" || typing || !cv.doc || cv.viewing || cv.gallery) return;
  const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
  if (!cvHttpUrl(text)) return;
  event.preventDefault();
  clearTimeout(cv.pasteWait);
  cv.pasteWait = 0;
  cvPasteText(text);
});

// ---- theme, search, keys ----
function applyTheme(theme) {
  const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  // The tab icon follows the page theme, which can differ from the system one.
  const icon = $("favicon");
  if (icon) icon.href = icon.dataset[dark ? "dark" : "light"];
}
applyTheme(localStorage.getItem("desk-theme"));
$("theme").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("desk-theme", next);
  applyTheme(next);
});

$("search").addEventListener("input", (event) => { state.query = event.target.value.trim(); render(); });

document.addEventListener("keydown", (event) => {
  // The open boards menu owns the keyboard (its own handler moves focus and closes it).
  if (boardsOpen()) { if (event.key === "Escape") closeBoards(true); return; }
  if (gameKey(event)) return;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (state.view === "canvas" && !typing && canvasKey(event)) return;
  // Studio has its own ⌘Z, Esc, arrows and Delete, so it goes before the page-wide keys.
  if (state.view === "studio" && studioKeydown(event)) return;
  if (event.key === "Escape") {
    $("help").classList.remove("on");
    closeViewer();
    if (typing) document.activeElement.blur();
    if (state.query || state.tag) { state.query = ""; state.tag = ""; $("search").value = ""; render(); }
    return;
  }
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "?") { $("help").classList.toggle("on"); return; }
  if (state.view === "canvas") {
    if (!EMBED && event.key >= "1" && event.key <= "5") setView(VIEWS[Number(event.key) - 1]);
    return;
  }
  if (event.key === "/") { event.preventDefault(); if (state.view === "games") setView("board"); $("search").focus(); }
  else if (event.key === "n") {
    event.preventDefault();
    if (state.view === "today") document.querySelector(".quick input")?.focus();
    else { if (state.view !== "board") setView("board"); document.querySelector(".add input")?.focus(); }
  }
  else if (event.key === " ") { event.preventDefault(); togglePlay(); }
  else if (!EMBED && event.key >= "1" && event.key <= "5") setView(VIEWS[Number(event.key) - 1]);
});

// Unlaw.app calls this when another desk part is picked in its sidebar.
window.deskEmbedView = (view) => { if (VIEWS.includes(view) && view !== "games") setView(view); };

// ---- start ----
async function start() {
  if (!TOKEN) { document.body.textContent = "Open the desk with `ul desk`: this page needs its token."; return; }
  await Promise.all([loadBoard(true), loadBoards(), loadTimer(), loadGames(), loadStudioInfo()]);
  render();
  setInterval(() => { if (!document.hidden && !state.dragging && state.draggingColumn == null && !state.editing && !["games", "studio", "canvas"].includes(state.view)) loadBoard(false); }, 2000);
  setInterval(pollCanvas, 3000);
  setInterval(() => { if (!document.hidden) loadTimer(); }, 10000);
  setInterval(() => { if (!document.hidden && state.view === "games" && arcade.session) loadGames(); }, 5000);
  setInterval(drawTimer, 500);
  setInterval(drawRecording, 250);
  scheduleStudioPoll();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (state.view === "games") pauseGame(); return; }
    loadBoard(false);
    loadTimer();
    scheduleStudioPoll(true);
  });
}
start();
</script>
</body>
</html>
"""
PAGE = _PAGE.replace("/*@STUDIO_CSS@*/\n", STUDIO_CSS).replace("/*@STUDIO_JS@*/\n", STUDIO_JS)

import calendar
import errno
import hashlib
import fcntl
import hmac
import json
import math
import re
import os
import secrets
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.parse
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path



USAGE = (
    "Usage: ul desk [board] [--reminders] [--port N] [--no-open] | list [--json] | "
    "show [board] [--reminders] [--json] | add <text> [--column C] [-b board] | "
    "move <n> <column> [-b board] | done <n> [-b board] | new <name> | rm <board> | path [board] | stats [board] | "
    "pomodoro [status|start [minutes] [--card <text>]|pause|resume|stop|skip]"
)
PHASES = {
    "work": "Focus",
    "short": "Short break",
    "long": "Long break",
    "idle": "Ready",
}
DOING_COLUMNS = {"doing", "in progress", "in work", "в работе", "делаю", "в процессе"}
MAX_BODY = 64 * 1024
MAX_CANVAS_BODY = 16 * 1024 * 1024
# Files dropped on a canvas are copied next to it, into this folder (a JSON Canvas file node's path is relative).
CANVAS_FILES = "attachments"
MAX_UPLOAD = 256 * 1024 * 1024
# Pictures the page shows as they are; anything else gets a Quick Look thumbnail (qlmanage).
CANVAS_IMAGES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".ico": "image/x-icon",  # site logos of link cards
}
THUMB_SIZE = 640
# What the canvas viewer may fetch as the file itself (`raw=1`). Never HTML or SVG as a page: text of any kind goes
# out as text/plain, and everything but PDF carries a sandbox CSP, so an attachment can never run script here.
CANVAS_RAW = {
    **{suffix: "video/mp4" for suffix in (".mp4", ".m4v", ".mov")},
    ".webm": "video/webm",
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".wav": "audio/wav",
    ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/ogg",
    ".pdf": "application/pdf",
    **{suffix: "application/octet-stream" for suffix in (".glb", ".gltf", ".obj", ".stl", ".bin")},
    **{suffix: "text/plain; charset=utf-8" for suffix in (
        ".md", ".markdown", ".txt", ".text", ".log", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".toml",
        ".ini", ".cfg", ".conf", ".xml", ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
        ".py", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".m", ".swift", ".go", ".java", ".kt", ".rb", ".php",
        ".sh", ".zsh", ".bash", ".fish", ".sql", ".lua", ".r", ".jl", ".tex", ".srt", ".vtt", ".svg")},
}
# Word-like documents the viewer shows as a page: `textutil -convert html`, served without scripts.
CANVAS_DOCUMENTS = {".docx", ".doc", ".rtf", ".odt"}
SANDBOX_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; media-src 'self'"
# `open` runs these (a script in Terminal, an installer, Java), so a card naming one only shows it in Finder.
RUNNABLE_SUFFIXES = {".command", ".tool", ".terminal", ".sh", ".zsh", ".bash", ".csh", ".jar", ".pkg", ".mpkg", ".app", ".workflow", ".action", ".scpt", ".applescript", ".scptd", ".osax", ".prefpane", ".inetloc", ".fileloc", ".webloc", ".definition"}
THUMB_TIMEOUT = 30
MAX_TEXT = 500
RECENT = 8
# The macOS open dialog for "Open…" in the Canvas tab; argv[1] is the folder it starts in.
CHOOSE_CANVAS_SCRIPT = (
    "on run argv",
    "activate",
    'set chosen to choose file with prompt "Open a canvas" of type {"canvas"} default location (POSIX file (item 1 of argv))',
    "return POSIX path of chosen",
    "end run",
)
# The macOS dialogs for "New board…" (save dialog, argv[2] = suggested name) and "Open another board…";
# argv[1] is the folder they start in.
CHOOSE_NEW_BOARD_SCRIPT = (
    "on run argv",
    "activate",
    'set chosen to choose file name with prompt "New board" default name (item 2 of argv) default location (POSIX file (item 1 of argv))',
    "return POSIX path of chosen",
    "end run",
)
CHOOSE_BOARD_SCRIPT = (
    "on run argv",
    "activate",
    'set chosen to choose file with prompt "Open a board" of type {"md", "net.daringfireball.markdown"} default location (POSIX file (item 1 of argv))',
    "return POSIX path of chosen",
    "end run",
)
CHOOSE_TIMEOUT = 600
CHOOSE_STATE = "choose.json"  # the folder each open/save dialog was left in, so the next one starts there
MAX_CANVAS_NUMBER = 10000
MAX_PEEK = 4 * 1024 * 1024  # canvases bigger than this get no gallery thumbnail
# The gallery's favorites and groups: only a list of canvas paths, the files never move.
SHELF_STATE = "canvases.json"
MAX_SHELF_PATHS = 2000
MAX_SHELF_GROUPS = 200


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
        "reminders": desk.get("reminders", True) is not False,
        "boards_dir": desk.get("boards_dir") if isinstance(desk.get("boards_dir"), str) and desk.get("boards_dir") else "boards",
        "canvas_dir": desk.get("canvas_dir") if isinstance(desk.get("canvas_dir"), str) and desk.get("canvas_dir") else "canvas",
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
        temporary = Path(handle.name)
        try:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
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
        raw = _read_json(self.state_file, {})
        state = {**IDLE, **raw} if isinstance(raw, dict) else dict(IDLE)

        def number(value: object) -> bool:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False
            try:
                return math.isfinite(value)
            except OverflowError:
                return False

        if (
            not isinstance(state["phase"], str) or state["phase"] not in PHASES
            or not isinstance(state["cycle"], int) or isinstance(state["cycle"], bool) or state["cycle"] < 0
            or (state["card"] is not None and not isinstance(state["card"], str))
            or not number(state["length"]) or state["length"] < 0
            or (state["paused"] is not None and (not number(state["paused"]) or state["paused"] < 0))
        ):
            return dict(IDLE)
        if state["phase"] != "idle":
            if not number(state["ends_at"]) or not number(state["started_at"]) or state["length"] <= 0:
                return dict(IDLE)
            try:
                datetime.fromtimestamp(state["started_at"], UTC)
            except (ValueError, OverflowError, OSError):
                return dict(IDLE)
        elif state["paused"] is not None:
            return dict(IDLE)
        return state

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

    def _log(self, state: dict, board: str | None, end: float | None = None) -> None:
        end = self.clock() if end is None else end
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
                # Logged when it really ended, not when the Mac woke up hours later (stats count days by the end).
                self._log(state, board, end=state["ends_at"])
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


class GameEnded(LookupError):
    """The game session the page asks about is over (HTTP 410). Its own class, so a stray KeyError or
    IndexError elsewhere is never reported to the page as "game over"."""


class CanvasConflict(Exception):
    """The canvas file changed since the client read it."""


def _clean_path(value: object) -> str:
    """A board path from the page: kept exactly (two spaces are part of a file name)."""
    if not isinstance(value, str):
        raise TypeError("path must be a string")
    text = value.strip()
    if not text or "\0" in text or len(text) > 4096:
        raise ValueError("invalid board path")
    return text


def completed_column_name(config: dict) -> str:
    return str(config.get("todo", {}).get("completed_column", "Completed"))


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
        path: Path | None,
        config: dict,
        directory: Path,
        clock: Callable[[], float] = time.time,
        layer: str | None = None,
    ) -> None:
        if path is None and layer is None:
            raise ValueError("a board file or the Reminders layer is needed")
        self.path = path
        # The Reminders layer replaces the open file while it is shown; self.path keeps the last file board.
        self.layer = layer
        self.config = config
        self.directory = directory
        self.settings = desk_settings(config)
        self.reminders = Reminders()
        self.boards_dir = boards_folder(self.settings["boards_dir"], config_dir())
        self.canvas_dir = boards_folder(self.settings["canvas_dir"], config_dir())
        # The newest recent canvas is the one the page had open: a restart (or an update) reopens it.
        recent_canvas = self.canvas_recent()
        self.canvas_current: Path | None = Path(recent_canvas[0]) if recent_canvas else None
        self.canvas_lock = threading.Lock()
        self.choose_lock = threading.Lock()
        self.pomodoro = Pomodoro(directory, self.settings, clock)
        self.lock = threading.Lock()
        self.today: Callable[[], date] = lambda: datetime.now().astimezone().date()

    @property
    def completed_column(self) -> str:
        return completed_column_name(self.config)

    @property
    def current(self) -> str:
        return REMINDERS if self.layer == REMINDERS or self.path is None else str(self.path)

    def read(self) -> tuple[str, KanbanBoard]:
        if self.layer == REMINDERS or self.path is None:
            version, board, _, _ = self.reminders.read()
            return version, board
        data = self.path.read_bytes()
        return version_of(data), KanbanBoard.parse(data.decode("utf-8"))

    def board_json(self) -> dict:
        version, board = self.read()
        return self.render(version, board)

    def render(self, version: str, board: KanbanBoard) -> dict:
        reminders = self.current == REMINDERS
        try:
            # Completed reminders leave the board, so the layer has no Done column.
            done_name = None if reminders else completed_section(board, self.completed_column).name
        except ValueError:
            done_name = None
        return {
            "version": version,
            "path": self.current,
            "name": "Reminders" if reminders or self.path is None else self.path.stem,
            "layer": "reminders" if reminders else "file",
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
        if self.current == REMINDERS:
            with self.lock:
                version, board, ids, lists = self.reminders.read(fresh=True)
                if request.get("version") != version:
                    raise Conflict
                try:
                    self.apply_reminders(board, ids, lists, request)
                finally:
                    self.reminders.invalidate()
                return self.board_json()
        with self.lock:
            version, board = self.read()
            if request.get("version") != version:
                raise Conflict
            self.apply(board, request)
            try:
                write_board(self.path, board, expected=version)
            except BoardChanged:
                raise Conflict from None
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
        elif op == "move_column":
            # The column order is the order of the ## headings; the whole section moves with its cards.
            index = _index(request.get("column"), len(board.sections), "column")
            if board.sections[index].name != request.get("name"):
                raise Conflict
            position = _index(request.get("to_index"), len(board.sections), "to_index")
            board.sections.insert(position, board.sections.pop(index))
        else:
            raise ValueError(f"Unknown operation: {op}")

    def apply_reminders(
        self, board: KanbanBoard, ids: list[list[str]], lists: list[str], request: dict
    ) -> None:
        """The board operations on Apple Reminders: a column is a list, a card a reminder."""
        op = request.get("op")
        today = self.today()
        if op == "add":
            column = _index(request.get("column"), len(board.sections), "column")
            self.reminders.add(lists[column], quick_text(_clean_text(request.get("text")), today))
        elif op == "column":
            name = _clean_text(request.get("name"))
            if any(section.name.casefold() == name.casefold() for section in board.sections):
                raise ValueError(f"List '{name}' already exists")
            self.reminders.new_list(name)
        elif op in {"edit", "move", "done", "delete"}:
            self._task(board, request)
            column, index = request["column"], request["index"]
            reminder = ids[column][index]
            if op == "edit":
                self.reminders.edit(reminder, quick_text(_clean_text(request.get("text")), today))
            elif op == "move":
                target = _index(request.get("to_column"), len(board.sections), "to_column")
                # Reminders keeps no order that EventKit could set, so only a move to another list changes anything.
                if target != column:
                    self.reminders.move(reminder, lists[target])
            elif op == "done":
                self.reminders.complete(reminder)
            else:
                self.reminders.delete(reminder)
        elif op == "reopen":
            raise ValueError("Completed reminders are not shown; reopen them in Reminders")
        elif op == "move_column":
            raise ValueError("The order of Reminders lists is set in the Reminders app")
        else:
            raise ValueError(f"Unknown operation: {op}")

    def boards(self) -> list[str]:
        """Boards in desk.boards_dir, by name."""
        try:
            return sorted(
                (str(path.resolve()) for path in self.boards_dir.glob("*.md") if path.is_file()),
                key=lambda item: Path(item).stem.casefold(),
            )
        except OSError:
            return []

    def recent(self) -> list[str]:
        items = _read_json(self.directory / "recent.json", [])
        paths = (
            [item for item in items if isinstance(item, str)]
            if isinstance(items, list)
            else []
        )
        return [path for path in paths if Path(path).is_file()]

    def remember(self) -> None:
        if self.path is None:
            return
        paths = [
            str(self.path),
            *[path for path in self.recent() if path != str(self.path)],
        ][:RECENT]
        _write_json(self.directory / "recent.json", paths)

    def canvas_recent(self) -> list[str]:
        items = _read_json(self.directory / "recent-canvas.json", [])
        paths = [item for item in items if isinstance(item, str)] if isinstance(items, list) else []
        return [path for path in paths if Path(path).is_file()]

    def canvases(self) -> dict:
        """Canvases in desk.canvas_dir by name, then the recently opened ones elsewhere."""
        try:
            files = sorted(
                (str(path.resolve()) for path in self.canvas_dir.glob("*.canvas") if path.is_file()),
                key=lambda item: Path(item).stem.casefold(),
            )
        except OSError:
            files = []
        current = self.canvas_current
        return {
            "dir": str(self.canvas_dir),
            "current": str(current) if current is not None and current.is_file() else None,
            "shelf": self.canvas_shelf(),
            "items": [
                {"path": path, "name": Path(path).stem, "modified": _modified(path)}
                for path in dict.fromkeys([*files, *self.canvas_recent()])
            ],
        }

    def canvas_shelf(self) -> dict:
        """The gallery's favorites and groups; a damaged file counts as empty (it holds no canvas data)."""
        try:
            return clean_shelf(_read_json(self.directory / SHELF_STATE, {}))
        except (ValueError, TypeError):
            return clean_shelf({})

    def canvas_shelf_save(self, data: object) -> dict:
        """Replace the favorites and groups (the page sends them whole); returns the new overview."""
        shelf = clean_shelf(data)
        with self.canvas_lock:
            _write_json(self.directory / SHELF_STATE, shelf)
        return self.canvases()

    def _shelf_move(self, old: Path, new: Path | None) -> None:
        """A renamed canvas keeps its star and group; a deleted one leaves them (the caller holds canvas_lock)."""
        shelf, before, after = self.canvas_shelf(), str(old), None if new is None else str(new)

        def swap(paths: list[str]) -> list[str]:
            return list(dict.fromkeys(after if item == before else item for item in paths if after or item != before))

        changed = {"favorites": swap(shelf["favorites"]), "groups": [{**group, "paths": swap(group["paths"])} for group in shelf["groups"]]}
        if changed != {"favorites": shelf["favorites"], "groups": shelf["groups"]}:
            try:
                _write_json(self.directory / SHELF_STATE, {**shelf, **changed})
            except OSError:
                pass

    def _canvas_json(self, path: Path, version: str, canvas: dict) -> dict:
        return {"path": str(path), "name": path.stem, "version": version, "canvas": canvas}

    def _canvas_shown(self, path: Path) -> None:
        """Make `path` the current canvas and the newest recent one (the caller holds canvas_lock)."""
        self.canvas_current = path
        paths = [str(path), *[item for item in self.canvas_recent() if item != str(path)]][:RECENT]
        _write_json(self.directory / "recent-canvas.json", paths)

    def canvas_open(self, raw: object, create: bool = False) -> dict:
        """Open a canvas by name or path (no argument: the current one); `create` makes a missing one."""
        with self.canvas_lock:
            if raw is None:
                if self.canvas_current is None:
                    raise FileNotFoundError("No canvas is open")
                path = self.canvas_current
            else:
                path = canvas_file(raw, create=create, canvas_dir=self.canvas_dir)
            version, canvas = read_canvas(path)
            self._canvas_shown(path)
        return self._canvas_json(path, version, canvas)

    def canvas_save(self, body: dict) -> dict:
        """Replace the whole canvas when the client still has the file's current version."""
        version = body.get("version")
        if not isinstance(version, str):
            raise ValueError("version must be the text from the last read")
        canvas = body.get("canvas")
        with self.canvas_lock:
            path = canvas_file(body.get("path"), create=False, canvas_dir=self.canvas_dir)
            if version_of(path.read_bytes()) != version:
                raise CanvasConflict
            new_version = write_canvas(path, canvas)
            self._canvas_shown(path)
        return self._canvas_json(path, new_version, canvas)

    def canvas_new(self) -> dict:
        """Create and open the first free canvas-N in desk.canvas_dir (never an existing file)."""
        with self.canvas_lock:
            self.canvas_dir.mkdir(parents=True, exist_ok=True)
            for number in range(1, MAX_CANVAS_NUMBER):
                path = self.canvas_dir / f"canvas-{number}.canvas"
                try:
                    with path.open("xb") as handle:
                        handle.write(render_canvas(NEW_CANVAS))
                except FileExistsError:
                    continue
                break
            else:
                raise ValueError(f"No free canvas-N name in {self.canvas_dir}")
            path = path.resolve()
            version, canvas = read_canvas(path)
            self._canvas_shown(path)
        return self._canvas_json(path, version, canvas)

    def canvas_rename(self, raw: object, name: object) -> dict:
        """Rename a canvas inside its own folder; the contents (and so the version) stay as they are."""
        clean = name.strip() if isinstance(name, str) else ""
        if clean.casefold().endswith(".canvas"):
            clean = clean[: -len(".canvas")].strip()
        if not _bare_name(clean, ".canvas") or len(clean.encode()) > 240:
            raise ValueError("A canvas name is plain text: no /, not starting with . or ~")
        with self.canvas_lock:
            path = canvas_file(raw, create=False, canvas_dir=self.canvas_dir)
            target = path.with_name(clean + ".canvas")
            if target != path:
                if target.exists() and not os.path.samefile(path, target):
                    raise ValueError(f"A canvas named {clean} already exists")
                if target.exists():  # only the letter case changes on a case-insensitive disk
                    os.rename(path, target)
                else:
                    try:
                        _rename_new(path, target)
                    except FileExistsError as error:
                        raise ValueError(f"A canvas named {clean} already exists") from error
                self._shelf_move(path, target)
            version, canvas = read_canvas(target)
            self._canvas_shown(target)
        return self._canvas_json(target, version, canvas)

    def canvas_choose(self) -> dict:
        """Ask for a .canvas file in the macOS open dialog: {"path": None} when cancelled,
        {"unavailable": True} without osascript (the page then asks for a path)."""
        start = self._choice_start("canvas", self.canvas_dir)
        return self._remember_choice("canvas", self._choose(CHOOSE_CANVAS_SCRIPT, [str(start)]))

    def _choice_start(self, kind: str, default: Path) -> Path:
        """Where a dialog opens: the folder it was left in last time, else `default`, else HOME."""
        folders = _read_json(self.directory / CHOOSE_STATE, {})
        folder = folders.get(kind) if isinstance(folders, dict) else None
        if isinstance(folder, str) and Path(folder).is_dir():
            return Path(folder)
        return default if default.is_dir() else Path.home()

    def _remember_choice(self, kind: str, answer: dict) -> dict:
        chosen = answer.get("path")
        if isinstance(chosen, str) and chosen:
            folders = _read_json(self.directory / CHOOSE_STATE, {})
            folders = folders if isinstance(folders, dict) else {}
            folders[kind] = str(Path(chosen).parent)
            try:
                _write_json(self.directory / CHOOSE_STATE, folders)
            except OSError:
                pass
        return answer

    def canvas_peek(self, raw: object) -> dict:
        """A canvas read for the gallery's thumbnail; unlike canvas_open it does not become the current one."""
        with self.canvas_lock:
            path = canvas_file(raw, create=False, canvas_dir=self.canvas_dir)
            if path.stat().st_size > MAX_PEEK:
                raise ValueError("The canvas is too big for a preview")
            version, canvas = read_canvas(path)
        return self._canvas_json(path, version, canvas)

    def canvas_delete(self, raw: object) -> dict:
        """Move a canvas to the Trash (never deleted outright; its attachments folder stays, other canvases may
        use it). A canvas reached through a symlink in the canvas folder loses only the link. When it was the
        open one, the next recent canvas becomes current. Returns the new overview."""
        if not isinstance(raw, str):
            raise TypeError("path must be a name or a .canvas file")
        with self.canvas_lock:
            path = canvas_file(raw, create=False, canvas_dir=self.canvas_dir)
            entry = Path(str(self.canvas_dir / f"{raw}.canvas") if _bare_name(raw, ".canvas") else raw).expanduser().absolute()
            if not entry.is_symlink():
                entry = _link_in(self.canvas_dir, "*.canvas", path) or path
            _to_trash(entry)
            self._shelf_move(path, None)
            recent = [item for item in self.canvas_recent() if Path(item).resolve() != path]
            _write_json(self.directory / "recent-canvas.json", recent)
            if self.canvas_current is not None and self.canvas_current.resolve() == path:
                self.canvas_current = Path(recent[0]) if recent else None
        return self.canvases()

    def canvas_import(self, name: object, canvas: object) -> dict:
        """A .canvas file dropped on the page: the browser only gives its contents, so it becomes a new canvas
        in desk.canvas_dir under a free name (`Plan`, `Plan 2`, ...), never over a file, and opens."""
        data = validate_canvas(canvas)
        clean = attachment_name(name if isinstance(name, str) else "canvas")
        if clean.casefold().endswith(".canvas"):
            clean = clean[: -len(".canvas")].strip() or "canvas"
        with self.canvas_lock:
            self.canvas_dir.mkdir(parents=True, exist_ok=True)
            content = render_canvas(data)
            path = write_unique(self.canvas_dir, clean, ".canvas", lambda handle: handle.write(content), MAX_CANVAS_NUMBER).resolve()
            version, data = read_canvas(path)
            self._canvas_shown(path)
        return self._canvas_json(path, version, data)

    def canvas_folder(self, raw: object) -> Path:
        """The folder of an existing canvas; file nodes are relative to it."""
        with self.canvas_lock:
            return canvas_file(raw, create=False, canvas_dir=self.canvas_dir).parent

    def canvas_attach(self, raw: object, name: object, source, length: int) -> dict:
        """Copy `length` bytes from `source` into the canvas's attachments folder under a free name
        (`x.pdf`, `x 2.pdf`, ...), never over a file; a cut-off upload leaves nothing behind."""
        if not 0 <= length <= MAX_UPLOAD:
            raise ValueError(f"A file on a canvas can be at most {MAX_UPLOAD // (1024 * 1024)} MB")
        clean = attachment_name(name)
        folder = self.canvas_folder(raw) / CANVAS_FILES
        folder.mkdir(parents=True, exist_ok=True)
        stem, suffix = os.path.splitext(clean)
        target = write_unique(folder, stem, suffix, lambda handle: copy_exactly(source, handle, length))
        return {"file": f"{CANVAS_FILES}/{target.name}", "name": target.name, "size": length}

    def canvas_asset(self, raw: object, file: object) -> Path:
        """A file a node of this canvas names, only when it lies inside the canvas's folder."""
        if not isinstance(file, str) or not file or "\x00" in file or file.startswith(("/", "~")):
            raise ValueError("file must be a path relative to the canvas")
        folder = self.canvas_folder(raw).resolve()
        target = (folder / file).resolve()
        if not target.is_relative_to(folder) or not target.is_file():
            raise FileNotFoundError(f"No such file next to the canvas: {file}")
        return target

    def canvas_thumb(self, path: Path) -> Path:
        """A Quick Look PNG of any file (PDF, documents, HEIC, ...), cached by path, size and time."""
        info = path.stat()
        key = hashlib.sha256(f"{path}\0{info.st_size}\0{info.st_mtime_ns}".encode()).hexdigest()[:32]
        cache = self.directory / "thumbs"
        thumb = cache / f"{key}.png"
        if thumb.is_file():
            return thumb
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache, prefix=".ql.") as work:
            try:
                subprocess.run(
                    ["qlmanage", "-t", "-s", str(THUMB_SIZE), "-o", work, str(path)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=THUMB_TIMEOUT, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise FileNotFoundError(f"No preview for {path.name}") from error
            made = Path(work) / f"{path.name}.png"
            if not made.is_file():
                raise FileNotFoundError(f"No preview for {path.name}")
            os.replace(made, thumb)
        return thumb

    def canvas_document(self, path: Path) -> Path:
        """A Word-like document as one HTML page (textutil, part of macOS), cached like the thumbnails."""
        if path.suffix.casefold() not in CANVAS_DOCUMENTS:
            raise ValueError("Only .docx, .doc, .rtf and .odt open as a page")
        info = path.stat()
        key = hashlib.sha256(f"doc\0{path}\0{info.st_size}\0{info.st_mtime_ns}".encode()).hexdigest()[:32]
        cache = self.directory / "thumbs"
        page = cache / f"{key}.html"
        if page.is_file():
            return page
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache, prefix=".doc.") as work:
            made = Path(work) / "page.html"
            try:
                result = subprocess.run(
                    ["textutil", "-convert", "html", "-output", str(made), str(path)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=THUMB_TIMEOUT, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise FileNotFoundError(f"Could not read {path.name}") from error
            if result.returncode != 0 or not made.is_file():
                raise FileNotFoundError(f"Could not read {path.name}")
            os.replace(made, page)
        return page

    def canvas_open_file(self, raw: object, file: object) -> dict:
        """Open a canvas file in its macOS app (Preview, Pages, ...). A file that `open` would run
        (scripts, executables, installers) is only shown in Finder, so a card never starts a program."""
        target = self.canvas_asset(raw, file)
        runnable = target.suffix.casefold() in RUNNABLE_SUFFIXES or (not target.suffix and os.access(target, os.X_OK))
        command = ["open", "-R", str(target)] if runnable else ["open", str(target)]
        return {"ok": subprocess.run(command, check=False).returncode == 0, "revealed": runnable}

    def board_choose(self, create: bool) -> dict:
        """The macOS save dialog for a new board (create) or the open dialog for an existing one.
        Same answers as canvas_choose; a new board's path gets .md when the name has none."""
        start = self._choice_start("board", self.boards_dir)
        if create:
            answer = self._choose(CHOOSE_NEW_BOARD_SCRIPT, [str(start), "board.md"])
            if answer.get("path") and Path(answer["path"]).suffix.casefold() != ".md":
                answer["path"] += ".md"
            return self._remember_choice("board", answer)
        return self._remember_choice("board", self._choose(CHOOSE_BOARD_SCRIPT, [str(start)]))

    def _choose(self, script: tuple[str, ...], args: list[str]) -> dict:
        osascript = shutil.which("osascript")
        if osascript is None:
            return {"unavailable": True}
        if not self.choose_lock.acquire(blocking=False):
            raise ValueError("The file dialog is already open")
        try:
            command = [osascript]
            for line in script:
                command += ["-e", line]
            try:
                result = subprocess.run(
                    [*command, *args], capture_output=True, text=True, timeout=CHOOSE_TIMEOUT, check=False
                )
            except subprocess.TimeoutExpired:
                return {"path": None}
        finally:
            self.choose_lock.release()
        if result.returncode != 0:
            if "-128" in result.stderr:  # the user pressed Cancel
                return {"path": None}
            raise ValueError("The file dialog failed: " + result.stderr.strip()[:300])
        return {"path": result.stdout.strip() or None}

    def delete_board(self, raw: object) -> dict:
        """Move a file board to the Trash; when it was open, the next recent (or folder, or default) board opens.

        The last board is refused before anything moves, unless the Reminders layer can take its place.
        """
        text = _clean_path(raw)
        path = board_file(text, boards_dir=self.boards_dir)
        _refuse_default(path, self.config)
        # The page lists boards by their resolved path: a board in the boards folder that is a
        # symlink shows its target. Trash that link, never the real file it points to.
        given = Path(text).expanduser()
        if given.is_absolute() and not given.is_symlink():
            link = _link_in(self.boards_dir, "*.md", path)
            if link is not None:
                text = str(link)
        with self.lock:
            is_open = self.path is not None and self.path.resolve() == path
            default = _optional_board(self.config)
            others = [
                item
                for item in [*self.recent(), *self.boards(), *([str(default)] if default else [])]
                if Path(item).resolve() != path
            ]
            if is_open and not others and not reminders_available(self.settings["reminders"]):
                raise ValueError("This is the only board; create another one before deleting it")
            trash_board(text, self.config, self.boards_dir)
            _write_json(self.directory / "recent.json", [item for item in self.recent() if item != str(path)])
            if is_open:
                self.path = Path(others[0]) if others else None
                if self.path is None:
                    self.layer = REMINDERS
                else:
                    self.remember()
            return self.board_json()

    def switch(self, raw: object, create: bool) -> dict:
        text = _clean_path(raw)
        if text == REMINDERS:
            if not reminders_available(self.settings["reminders"]):
                raise ValueError("The Reminders layer is off (desk.reminders) or not on macOS")
            self.reminders.read(fresh=True)
            with self.lock:
                self.layer = REMINDERS
            return self.board_json()
        path = board_file(text, create=create, boards_dir=self.boards_dir)
        with self.lock:
            self.path = path
            self.layer = None
            self.remember()
        return self.board_json()


def _rename_new(path: Path, target: Path) -> None:
    """Rename without overwriting: a hard link fails when the name was taken meanwhile.
    Volumes without hard links (exFAT, FAT, some shares) check first, then rename."""
    try:
        os.link(path, target)
    except FileExistsError:
        raise
    except OSError as error:
        if error.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM, errno.EXDEV, errno.EMLINK):
            raise
        if os.path.lexists(target):
            raise FileExistsError(errno.EEXIST, "exists", str(target)) from error
        os.rename(path, target)
        return
    os.unlink(path)


def board_file(raw: str, create: bool = False, boards_dir: Path | None = None) -> Path:
    """A board chosen by the user: an existing .md file, or a new one from the template.

    A bare name (no folder, no .md) is a board in desk.boards_dir, created with the folder when needed.
    """
    if boards_dir is not None and _bare_name(raw):
        if create:
            boards_dir.mkdir(parents=True, exist_ok=True)
        raw = str(boards_dir / f"{raw}.md")
    try:
        path = Path(raw).expanduser().resolve()
    except RuntimeError as error:  # `~name` of a user that does not exist
        raise ValueError(f"Cannot expand {raw}: {error}") from error
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


def attachment_name(raw: object) -> str:
    """A safe file name from the browser's: the last path part, no control characters,
    no leading dot, at most 200 bytes (the extension kept)."""
    if not isinstance(raw, str):
        raise TypeError("name must be text")
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isprintable()).strip().lstrip(".").strip()
    if not name:
        name = "file"
    stem, suffix = os.path.splitext(name)
    if len(suffix.encode()) > 20:
        stem, suffix = name, ""
    while len((stem + suffix).encode()) > 200:
        stem = stem[:-1]
    return (stem.rstrip() or "file") + suffix


def clean_shelf(data: object) -> dict:
    """{version, favorites: [path], groups: [{name, paths: [path]}]} checked; a canvas sits in one group at most,
    group names are unique (case ignored). Wrong types raise ValueError/TypeError (HTTP 400)."""
    data = {} if data is None else data
    if not isinstance(data, dict):
        raise TypeError("shelf must be an object")

    def paths(value: object, what: str) -> list[str]:
        if not isinstance(value, list) or len(value) > MAX_SHELF_PATHS:
            raise ValueError(f"{what} must be a list of at most {MAX_SHELF_PATHS} canvas paths")
        if not all(isinstance(item, str) and 0 < len(item) <= 4096 and item.isprintable() for item in value):
            raise ValueError(f"{what} must hold canvas paths")
        return list(dict.fromkeys(value))

    groups, names, placed = [], set(), set()
    raw_groups = data.get("groups", [])
    if not isinstance(raw_groups, list) or len(raw_groups) > MAX_SHELF_GROUPS:
        raise ValueError(f"groups must be a list of at most {MAX_SHELF_GROUPS}")
    for group in raw_groups:
        if not isinstance(group, dict):
            raise TypeError("a group must be an object")
        name = group.get("name")
        name = " ".join(name.split()) if isinstance(name, str) else ""
        if not name or len(name) > 80 or not name.isprintable():
            raise ValueError("a group name is 1-80 printable characters")
        if name.casefold() in names:
            raise ValueError(f"two groups are named {name}")
        names.add(name.casefold())
        members = [item for item in paths(group.get("paths", []), f"group {name}") if item not in placed]
        placed.update(members)
        groups.append({"name": name, "paths": members})
    return {"version": 1, "favorites": paths(data.get("favorites", []), "favorites"), "groups": groups}


def canvas_file(raw: object, create: bool, canvas_dir: Path) -> Path:
    """A canvas chosen by the user: an existing .canvas file, or a new empty one.

    A bare name (no folder, no .canvas) is a canvas in desk.canvas_dir, created with the folder when needed.
    """
    if not isinstance(raw, str):
        raise TypeError("path must be a name or a .canvas file")
    if _bare_name(raw, ".canvas"):
        if create:
            canvas_dir.mkdir(parents=True, exist_ok=True)
        raw = str(canvas_dir / f"{raw}.canvas")
    try:
        path = Path(raw).expanduser().resolve()
    except RuntimeError as error:
        raise ValueError(f"Unknown home folder in {raw}") from error
    if path.suffix.casefold() != ".canvas":
        raise ValueError(f"A canvas is a .canvas file: {path}")
    if not path.exists():
        if not create:
            raise FileNotFoundError(f"Canvas not found: {path}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"Folder not found: {path.parent}")
        try:
            with path.open("xb") as handle:
                handle.write(render_canvas(NEW_CANVAS))
        except FileExistsError:
            pass
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    return path


def _bare_name(raw: str, suffix: str = ".md") -> bool:
    return (
        bool(raw.strip())
        and "/" not in raw
        and not raw.startswith((".", "~"))
        and Path(raw).suffix.casefold() != suffix
        and not any(ord(char) < 32 for char in raw)
    )


# The default board path of releases up to 3.19.4: the maintainer's own vault, written into every new config.toml.
LEGACY_VAULT = "~/aiwork/data-obsidian"


def own_board(config: dict) -> Path | None:
    """The default board Unlaw keeps itself: desk.boards_dir/todo.file when todo.vault_path is empty.

    A config that still carries the old default vault, on a Mac without that folder, gets board.md too.
    """
    todo = config.get("todo", {}) if isinstance(config.get("todo"), dict) else {}
    vault = str(todo.get("vault_path", ""))
    if vault.strip():
        if vault != LEGACY_VAULT or Path(vault).expanduser().is_dir():
            return None
        name = "board.md"
    else:
        name = str(todo.get("file") or "board.md")
    folder = boards_folder(desk_settings(config)["boards_dir"], config_dir())
    path = (folder / name).absolute()
    if path.parent != folder.absolute() or path.suffix.casefold() != ".md":
        raise ValueError("todo.file must be a .md file name when todo.vault_path is empty")
    return path


def default_board(config: dict) -> Path:
    own = own_board(config)
    if own is not None:
        if not own.is_file() and not own.is_symlink():
            own.parent.mkdir(parents=True, exist_ok=True)
            try:
                with own.open("x", encoding="utf-8") as handle:
                    handle.write(NEW_BOARD)
            except FileExistsError:
                pass
        return own.resolve()
    path = configured_board(config["todo"])
    if not path.is_file():
        raise FileNotFoundError(
            f"Kanban file not found: {path} (set todo.vault_path and todo.file, or pass a board.md)"
        )
    return path


def _refuse_default(path: Path, config: dict) -> None:
    default = _optional_board(config)
    if default is not None and default.resolve() == path:
        raise ValueError(f"{path} is the default board (todo.vault_path + todo.file); it is not deleted")


def trash_board(raw: str, config: dict, boards_dir: Path) -> tuple[Path, Path]:
    """Move a board to ~/.Trash (never deleted outright): (the board as resolved, its place in the Trash).

    A board reached through a symlink loses only the link. The default board (todo.file) is refused:
    `ul desk show/add/done` and the agent read it.
    """
    path = board_file(raw, boards_dir=boards_dir)
    entry = Path(str(boards_dir / f"{raw}.md") if _bare_name(raw) else raw).expanduser().absolute()
    if not entry.is_symlink():
        entry = path
    _refuse_default(path, config)
    return path, _to_trash(entry)


def write_unique(folder: Path, stem: str, suffix: str, write, tries: int = 1000) -> Path:
    """Create `<stem><suffix>`, else `<stem> 2<suffix>`, ... in `folder` (exclusive create, never over a file)
    and fill it with `write(handle)`; a failed write removes the file, so nothing half-written is left."""
    for number in range(1, tries):
        target = folder / (f"{stem}{suffix}" if number == 1 else f"{stem} {number}{suffix}")
        try:
            handle = target.open("xb")
        except FileExistsError:
            continue
        try:
            with handle:
                write(handle)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
    raise ValueError(f"No free name for {stem}{suffix} in {folder}")


def copy_exactly(source, handle, length: int, head: bytes = b"") -> None:
    """Write `head`, then the rest of `length` bytes from `source` (an upload that ends early is an error)."""
    handle.write(head)
    left = length - len(head)
    while left > 0:
        chunk = source.read(min(1 << 16, left))
        if not chunk:
            raise ValueError("the upload ended early")
        handle.write(chunk)
        left -= len(chunk)


def _link_in(folder: Path, pattern: str, target: Path) -> Path | None:
    """A symlink in `folder` that points to `target`: the page lists files by their resolved path, and deleting
    such a file must trash that link, never the real file it points to."""
    try:
        return next((item for item in folder.glob(pattern) if item.is_symlink() and item.resolve() == target), None)
    except OSError:
        return None


def _to_trash(entry: Path) -> Path:
    """Move a file (or only the link, for a symlink) into ~/.Trash under a free name (`X 2.md`), never over one."""
    trash = Path.home() / ".Trash"
    trash.mkdir(exist_ok=True)
    target, number = trash / entry.name, 2
    while target.exists() or target.is_symlink():
        target = trash / f"{entry.stem} {number}{entry.suffix}"
        number += 1
    shutil.move(str(entry), str(target))
    return target


def _modified(path: str) -> float | None:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _optional_board(config: dict) -> Path | None:
    """The todo board when it exists: the Reminders layer can start without one."""
    try:
        return default_board(config)
    except (FileNotFoundError, ValueError):
        return None


def _find_note(root: Path, name: str) -> Path | None:
    wanted = f"{name}.md".casefold()
    for path in root.rglob("*.md"):
        if path.name.casefold() == wanted:
            return path
    return None


class Handler(BaseHTTPRequestHandler):
    desk: Desk
    arcade: Arcade
    studio: Studio
    token: str
    port: int
    server_version = "UnlawDesk"

    def log_message(self, format: str, *args: object) -> None:
        return

    def handle(self) -> None:
        # The page went away (reload, closed tab) before a slow answer was written: nothing to report.
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

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
        return token is not None and token.isascii() and hmac.compare_digest(token, self.token)

    def _body(self, limit: int = MAX_BODY) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        # A negative length would read until the client closes (rfile.read(-1)).
        if not 0 <= length <= limit:
            raise ValueError("request body is too large")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise TypeError("expected a JSON object")
        return data

    def _guard(self) -> bool:
        if not self._allowed_host():
            self._send(403, b"Forbidden host", "text/plain; charset=utf-8")
            return False
        if not self.path.startswith("/"):
            # An absolute-form target (`GET http://host/api/...`) would be routed by its URL path but skip a prefix check on the raw string.
            self._send(400, b"Bad request target", "text/plain; charset=utf-8")
            return False
        url = urllib.parse.urlsplit(self.path)
        if url.path.startswith("/media/"):
            # <video>/<img> cannot send headers, so media URLs carry the token.
            query = urllib.parse.parse_qs(url.query)
            if not self._authorized(query.get("t", [None])[0]):
                self._send(403, b"Forbidden", "text/plain; charset=utf-8")
                return False
        elif url.path.startswith("/api/") and not self._authorized(
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
                    200,
                    {
                        "current": self.desk.current,
                        "recent": self.desk.recent(),
                        "boards": self.desk.boards(),
                        "boards_dir": str(self.desk.boards_dir),
                        "reminders": reminders_available(self.desk.settings["reminders"]),
                    },
                )
            elif url.path == "/api/canvases":
                self._json(200, self.desk.canvases())
            elif url.path == "/api/canvas/peek":
                try:
                    self._json(200, self.desk.canvas_peek(urllib.parse.parse_qs(url.query).get("path", [""])[0]))
                except FileNotFoundError as error:
                    self._json(404, {"error": str(error), "missing": True})
                except (ValueError, TypeError) as error:
                    self._json(400, {"error": str(error)})
            elif url.path == "/api/canvas":
                try:
                    wanted = urllib.parse.parse_qs(url.query).get("path", [None])[0]
                    self._json(200, self.desk.canvas_open(wanted or None))
                except FileNotFoundError as error:
                    self._json(404, {"error": str(error), "missing": True})
                except (ValueError, TypeError) as error:
                    self._json(400, {"error": str(error)})
            elif url.path == "/api/games":
                self._json(200, self.arcade.scores())
            elif url.path == "/api/studio":
                self._json(200, self.studio.overview())
            elif url.path == "/api/studio/status":
                self._json(200, self.studio.status())
            elif url.path == "/api/studio/devices":
                self._json(200, self.studio.run("devices", timeout=30))
            elif url.path == "/api/studio/wave":
                query = urllib.parse.parse_qs(url.query)
                bars = query.get("bars", ["400"])[0]
                if not bars.isdigit() or not 10 <= int(bars) <= 2000:
                    raise StudioError("bars must be 10-2000")
                name = self.studio.member(query.get("name", [""])[0]).name
                self._json(200, self.studio.run("wave", name, "--bars", bars, timeout=300))
            elif url.path == "/api/studio/library":
                self._json(200, self.studio.run("list", "--all", timeout=120))
            elif url.path == "/api/studio/setup":
                self._json(200, self.studio.run("setup", timeout=30))
            elif url.path == "/api/studio/projects":
                self._json(200, self.studio.run("projects", timeout=120))
            elif url.path == "/api/studio/project":
                self._json(200, self.studio.project(urllib.parse.parse_qs(url.query).get("path", [""])[0]))
            elif url.path == "/api/studio/project/wave":
                query = urllib.parse.parse_qs(url.query)
                self._json(200, self.studio.project_wave(query.get("path", [""])[0], query.get("file", [""])[0], query.get("bars", ["2000"])[0]))
            elif url.path == "/api/studio/project/proxy":
                query = urllib.parse.parse_qs(url.query)
                self._json(200, self.studio.proxy(query.get("path", [""])[0], False))
            elif url.path == "/api/studio/speech-models":
                self._json(200, self.studio.run("transcribe", "--models", timeout=90))
            elif url.path == "/api/studio/export/status":
                self._json(200, self.studio.run("export", "--status", timeout=30))
            elif url.path == "/api/studio/camera-modes":
                self._json(200, self.studio.camera_modes(urllib.parse.parse_qs(url.query).get("device", [""])[0]))
            elif url.path == "/api/studio/doctor":
                self._json(200, self.studio.run("doctor", timeout=30))
            elif url.path.startswith("/media/"):
                self._media(url)
            else:
                self._json(404, {"error": "not found"})
        except StudioError as error:
            self._json(400, {"error": str(error)})
        except FileNotFoundError as error:
            self._json(404, {"error": str(error)})
        except (ValueError, TypeError, OverflowError) as error:
            # Bad input or a file that is not what it should be (a board without columns): the request failed, not the desk.
            self._json(400, {"error": str(error)})
        except OSError as error:
            self._json(500, {"error": str(error)})

    def _media(self, url: urllib.parse.SplitResult) -> None:
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/media/file":
            path = self.studio.member(query.get("name", [""])[0])
        elif url.path == "/media/thumb" and "path" in query:
            path = self.studio.project_thumb(query["path"][0])
        elif url.path == "/media/thumb":
            name = self.studio.member(query.get("name", [""])[0]).name
            data = self.studio.run("thumb", name, timeout=60)
            path = Path(str(data.get("thumbnail") if isinstance(data, dict) else ""))
        elif url.path == "/media/project":
            path = self.studio.project_file(query.get("path", [""])[0], query.get("file", [""])[0])
        elif url.path == "/media/asset":
            path = self.studio.asset_file(query.get("name", [""])[0])
        elif url.path == "/media/canvas":
            target = self.desk.canvas_asset(query.get("path", [""])[0], query.get("file", [""])[0])
            suffix = target.suffix.casefold()
            if query.get("doc", [""])[0] == "1":
                self._send_file(self.desk.canvas_document(target), "text/html; charset=utf-8", {"Content-Security-Policy": SANDBOX_CSP})
                return
            if query.get("raw", [""])[0] == "1":
                if suffix not in CANVAS_RAW:
                    raise FileNotFoundError(f"{target.name} is not served as itself")
                extra = {"Content-Disposition": "inline"}
                if suffix != ".pdf":
                    extra["Content-Security-Policy"] = SANDBOX_CSP
                self._send_file(target, CANVAS_RAW[suffix], extra)
                return
            kind = CANVAS_IMAGES.get(suffix)
            if kind is None or query.get("thumb", [""])[0] == "1":
                target, kind = self.desk.canvas_thumb(target), "image/png"
            self._send_file(target, kind)
            return
        elif url.path == "/media/preview":
            display = query.get("display", ["1"])[0]
            if not display.isdigit() or not 1 <= int(display) <= 16:
                raise ValueError("display must be a number from 1")
            data = self.studio.run("preview", "--display", display, timeout=30)
            path = Path(str(data.get("preview") if isinstance(data, dict) else ""))
        else:
            self._json(404, {"error": "not found"})
            return
        self._send_file(path)

    def _send_file(self, path: Path, kind: str | None = None, headers: dict[str, str] | None = None) -> None:
        """Serve a file with byte ranges, which video seeking needs."""
        kind = kind or MEDIA_TYPES.get(path.suffix.casefold())
        if kind is None or not path.is_file():
            self._json(404, {"error": "not found"})
            return
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        wanted = self.headers.get("Range", "")
        if wanted.startswith("bytes="):
            first, _, last = wanted[6:].split(",")[0].strip().partition("-")
            try:
                if first:
                    start, end = int(first), int(last) if last else size - 1
                else:
                    start = max(0, size - int(last))
            except ValueError:
                start, end = size, size
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = source.read(min(1 << 16, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self) -> None:
        if not self._guard():
            return
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        try:
            if path == "/api/canvas/upload":
                # The body is the file itself (not JSON), streamed to disk.
                query = urllib.parse.parse_qs(url.query)
                length = int(self.headers.get("Content-Length") or -1)
                self._json(200, self.desk.canvas_attach(query.get("path", [""])[0], query.get("name", [""])[0], self.rfile, length))
                return
            if path == "/api/studio/project/asset":
                self.close_connection = True
                length = int(self.headers.get("Content-Length") or -1)
                query = urllib.parse.parse_qs(url.query)
                self._json(200, self.studio.add_project_asset(query.get("path", [""])[0], query.get("name", [""])[0], self.rfile, length))
                return
            if path == "/api/studio/asset":
                # The body is the image itself; a refused upload may leave bytes unread, so the connection ends.
                self.close_connection = True
                length = int(self.headers.get("Content-Length") or -1)
                name = urllib.parse.parse_qs(url.query).get("name", [""])[0]
                self._json(200, self.studio.add_asset(name, self.rfile, length))
                return
            limit = MAX_CANVAS_BODY if path in {"/api/canvas", "/api/canvas/import"} else MAX_STUDIO_BODY if path in {"/api/studio/setup", "/api/studio/project"} else MAX_BODY
            body = self._body(limit)
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
            elif path == "/api/canvas":
                try:
                    self._json(200, self.desk.canvas_save(body))
                except CanvasConflict:
                    self._json(
                        409,
                        {
                            "error": "the canvas changed; reloaded",
                            "canvas": self.desk.canvas_open(body.get("path")),
                        },
                    )
            elif path == "/api/canvases":
                self._json(200, self.desk.canvas_open(body.get("path"), bool(body.get("create"))))
            elif path == "/api/canvas/new":
                self._json(200, self.desk.canvas_new())
            elif path == "/api/canvas/rename":
                self._json(200, self.desk.canvas_rename(body.get("path"), body.get("name")))
            elif path == "/api/canvas/choose":
                self._json(200, self.desk.canvas_choose())
            elif path == "/api/canvas/link-preview":
                self._json(200, link_preview(body.get("url"), self.desk.canvas_folder(body.get("path"))))
            elif path == "/api/canvas/delete":
                self._json(200, self.desk.canvas_delete(body.get("path")))
            elif path == "/api/canvas/shelf":
                self._json(200, self.desk.canvas_shelf_save(body.get("shelf")))
            elif path == "/api/canvas/import":
                self._json(200, self.desk.canvas_import(body.get("name"), body.get("canvas")))
            elif path == "/api/canvas/open-file":
                self._json(200, self.desk.canvas_open_file(body.get("path"), body.get("file")))
            elif path == "/api/boards/delete":
                self._json(200, self.desk.delete_board(body.get("path")))
            elif path == "/api/boards/choose":
                self._json(200, self.desk.board_choose(bool(body.get("create"))))
            elif path == "/api/game/start":
                session = self.arcade.start(
                    body.get("game"), body.get("level"), body.get("rows"), body.get("cols")
                )
                self._json(200, {"session": session})
            elif path == "/api/game/input":
                self.arcade.send(body.get("session"), body.get("events"))
                self._json(200, {"ok": True})
            elif path == "/api/game/stop":
                self.arcade.stop(body.get("session"))
                self._json(200, {"ok": True})
            elif path == "/api/game/stream":
                self._stream_game(self.arcade.claim(body.get("session")))
            elif path == "/api/studio/record":
                self._json(200, self.studio.record(body))
            elif path in {"/api/studio/pause", "/api/studio/resume"}:
                self._json(200, self.studio.run(path.rsplit("/", 1)[1], timeout=60))
            elif path == "/api/studio/stop":
                self._json(200, self.studio.stop(body))
            elif path == "/api/studio/setup":
                self._json(200, self.studio.save_setup(body))
            elif path == "/api/studio/scene":
                self._json(200, self.studio.scene(body))
            elif path == "/api/studio/mark":
                self._json(200, self.studio.mark(body))
            elif path == "/api/studio/project":
                self._json(200, self.studio.save_project(body))
            elif path == "/api/studio/project/proxy":
                self._json(200, self.studio.proxy(body.get("path"), True))
            elif path == "/api/studio/transcribe":
                self._json(200, self.studio.transcribe(body))
            elif path == "/api/studio/project/import":
                self._json(200, self.studio.import_sound(body))
            elif path == "/api/studio/export":
                self._json(200, self.studio.export(body))
            elif path == "/api/studio/open-settings":
                self._json(200, self.studio.open_settings(body))
            elif path == "/api/studio/open-project":
                self._json(200, self.studio.open_project())
            elif path == "/api/studio/shot":
                self._json(200, self.studio.shot(body))
            elif path == "/api/studio/action":
                self._json(200, self.studio.action(body))
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
        except GameEnded as error:
            self._json(410, {"error": str(error)})
        except StudioError as error:
            self._json(400, {"error": str(error)})
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
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            self._json(400, {"error": str(error)})
        except OSError as error:
            self._json(500, {"error": str(error)})

    def _stream_game(self, process: subprocess.Popen) -> None:
        """Relay frames as NDJSON until the game ends or the page goes away.

        Blank lines every 2 s notice a closed page while a menu sits still;
        a game nobody watches is stopped.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.close_connection = True
        assert process.stdout is not None
        # Raw reads: a buffered readline could hold frames that select() cannot see. The stream reads its own
        # copy of the descriptor: Arcade closes process.stdout when a game stops, and the number could be
        # reused by the next game's pipe while this loop still sits in select().
        source = -1
        try:
            source = os.dup(process.stdout.fileno())
            while True:
                ready, _, _ = select.select([source], [], [], 2)
                if not ready:
                    self.wfile.write(b"\n")
                    self.wfile.flush()
                    continue
                chunk = os.read(source, 1 << 16)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            self.wfile.write(b'{"end":true}\n')
            self.wfile.flush()
        except (OSError, ValueError):
            pass
        finally:
            if source >= 0:
                os.close(source)
            self.arcade.stop_if(process)

    def _open_obsidian(self, note: object) -> bool:
        target = self.desk.path
        if target is None:
            return False
        if isinstance(note, str) and note.strip():
            found = _find_note(self.desk.path.parent, note.strip())
            if found is None:
                return False
            target = found
        url = "obsidian://open?path=" + urllib.parse.quote(str(target), safe="")
        return subprocess.run(["open", url], check=False).returncode == 0


# frame-src: the canvas viewer shows PDFs and documents from here and live link pages from the web.
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; frame-src 'self' https: http:; base-uri 'none'; form-action 'none'"


MEDIA_TYPES = {
    ".mov": "video/mp4",
    ".mp4": "video/mp4",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".tiff": "image/tiff",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".aiff": "audio/aiff",
    ".caf": "audio/x-caf",
}
STUDIO_MODES = ("screen", "screen-camera", "camera", "audio")
STUDIO_FORMATS = ("mov", "mp4", "m4a", "mp3", "wav")
# Export and recording choices the page may pass on to `ul capture` (capture checks them again).
STUDIO_CANVASES = ("16:9", "9:16", "1:1", "4:5", "source")
STUDIO_EXPORT_CHOICES = {
    "canvas": ("--canvas", STUDIO_CANVASES),
    "height": ("--height", (1080, 1440, 2160)),
    "fps": ("--fps", (30, 60)),
    "codec": ("--codec", ("h264", "hevc")),
    "quality": ("--quality", ("high", "max")),
    "format": ("--format", ("mov", "mp4")),
}
STUDIO_SETTINGS = ("screen", "camera", "microphone")
STUDIO_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
# Setups and projects carry layouts for every format and scene: larger than a board change.
MAX_STUDIO_BODY = 2 * 1024 * 1024
# Images for image and text sources (the page renders text to PNG).
MAX_ASSET = 50 * 1024 * 1024
ASSET_MAGIC = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
AUDIO_ASSETS = (".m4a", ".mp3", ".wav", ".flac", ".aac", ".aiff", ".caf")
# Music and voice-over for the Edit tab (copied into the project's assets/).
MAX_PROJECT_AUDIO = 1024 * 1024 * 1024


def audio_looks_right(suffix: str, head: bytes) -> bool:
    """The first bytes of a sound file match its extension (an upload named .mp3 must be one)."""
    if suffix == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if suffix == ".flac":
        return head[:4] == b"fLaC"
    if suffix == ".mp3":
        return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    if suffix == ".m4a":
        return head[4:8] == b"ftyp"
    if suffix == ".aac":
        return len(head) > 1 and head[0] == 0xFF and head[1] & 0xF0 == 0xF0
    if suffix == ".aiff":
        return head[:4] == b"FORM"
    if suffix == ".caf":
        return head[:4] == b"caff"
    return False
CHOOSE_PROJECT_SCRIPT = (
    "on run argv",
    "activate",
    'set chosen to choose folder with prompt "Open a Studio project" default location (POSIX file (item 1 of argv))',
    "return POSIX path of chosen",
    "end run",
)


class StudioError(Exception):
    pass


class Studio:
    """The Studio tab: a thin layer over `ul capture ... --json`.

    Recording, screenshots and editing stay in the capture command, so the
    terminal and the page share one recording and one library.
    """

    def __init__(self, binary: str | None, settings: dict) -> None:
        self.binary = binary
        self.settings = settings
        self.lock = threading.Lock()
        self.saving: threading.Thread | None = None
        self.last: dict | None = None
        self._available: bool | None = None
        self._availability_lock = threading.Lock()
        self.choose_lock = threading.Lock()
        self.proxies: dict[str, dict] = {}  # project folder -> {state, files, error}

    def available(self) -> bool:
        with self._availability_lock:
            return self._probe_available()

    def _probe_available(self) -> bool:
        if self._available is None:
            self._available = False
            if self.binary:
                try:
                    result = subprocess.run(
                        [self.binary, "capture", "--help"],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    self._available = result.returncode == 0 and "record [screen" in result.stdout
                except (OSError, subprocess.TimeoutExpired):
                    pass
        return self._available

    def run(self, *args: str, timeout: float = 60, stdin: str | None = None) -> object:
        if not self.available():
            raise StudioError("the capture command is not installed (ul features)")
        try:
            with subprocess.Popen(
                [self.binary or "ul", "capture", *args, "--json"],
                stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            ) as process:
                try:
                    stdout, stderr_text = process.communicate(stdin, timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Saving/thumbnail helpers share this group; killing only the
                    # capture CLI would leave ffmpeg running after the timeout.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                    raise
                result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr_text)
        except subprocess.TimeoutExpired as error:
            raise StudioError(f"ul capture {args[0]} took too long") from error
        except OSError as error:
            raise StudioError(f"could not run ul capture {args[0]}: {error}") from error
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        try:
            data = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            data = {}
        if result.returncode != 0:
            message = data.get("error") if isinstance(data, dict) else None
            stderr = result.stderr.strip().splitlines()
            raise StudioError(message or (stderr[-1].removeprefix("unlaw capture: ") if stderr else "ul capture failed"))
        notes = [line.removeprefix("Note: ") for line in result.stderr.splitlines() if line.startswith("Note: ")]
        if notes and isinstance(data, dict):
            data["warnings"] = notes
        return data

    def overview(self) -> dict:
        settings = {
            "camera_device": "default",
            "audio_device": "default",
            "screen_audio": True,
            "system_audio": True,
            "show_clicks": True,
            "video_format": "mov",
            "audio_format": "m4a",
            "overlay": "bottom-right",
            **{key: value for key, value in self.settings.items() if isinstance(value, (str, bool))},
        }
        return {"available": self.available(), "settings": settings}

    def status(self) -> dict:
        data = self.run("status", timeout=20)
        assert isinstance(data, dict)
        data["saving_done"] = self.last
        if not data.get("active"):
            # capture reports the free space only while recording; the page shows it before, too.
            folder = storage_path("captures")
            while not folder.exists() and folder != folder.parent:
                folder = folder.parent
            try:
                data["free_bytes"] = shutil.disk_usage(folder).free
            except OSError:
                data["free_bytes"] = None
        return data

    def record(self, body: dict) -> object:
        """Record the saved setup; `scene`/`canvas` and the old keys (mode, mic, cam, ...) override it once."""
        mode = body.get("mode")
        if mode is not None and mode not in STUDIO_MODES:
            raise ValueError("mode must be screen, screen-camera, camera or audio")
        args = ["record"]
        if mode is not None:
            args.append("screen" if mode == "screen-camera" else str(mode))
        if mode == "screen-camera":
            args.append("--camera")
        if body.get("scene") is not None:
            args += ["--scene", self.scene_id(body["scene"])]
        canvas = body.get("canvas")
        if canvas is not None:
            if canvas not in STUDIO_CANVASES:
                raise ValueError("canvas must be 16:9, 9:16, 1:1, 4:5 or source")
            args += ["--canvas", canvas]
        for key, flag in (("mic", "--mic"), ("cam", "--cam")):
            value = body.get(key)
            if value is not None:
                if not isinstance(value, str) or not value.strip() or len(value) > 200 or value.startswith("-"):
                    raise ValueError(f"{key} must be a device name")
                args += [flag, value]
        display = body.get("display")
        if display is not None and (isinstance(display, bool) or not isinstance(display, int) or not 1 <= display <= 16):
            raise ValueError("display must be a number from 1")
        if mode in {None, "screen", "screen-camera"}:
            if display is not None:
                args += ["--display", str(display)]
            system = body.get("system_audio")
            if system is not None:
                args.append("--system-audio" if system is True else "--no-system-audio")
            if body.get("clicks") is False:
                args.append("--no-clicks")
        fmt = body.get("format")
        if fmt is not None:
            if fmt not in STUDIO_FORMATS:
                raise ValueError("unknown format")
            args += ["--format", fmt]
        self.last = None
        return self.run(*args, timeout=30)

    def stop(self, body: dict | None = None) -> dict:
        """Saving can take minutes (remux, a slow recorder), so it runs in the background.

        `force` kills a stuck recorder (its track is lost); `ul capture stop` never does that on its own.
        """
        force = (body or {}).get("force", False)
        if not isinstance(force, bool):
            raise TypeError("force must be true or false")
        with self.lock:
            if self.saving and self.saving.is_alive():
                return {"saving": True}
            self.last = None

            def work() -> None:
                try:
                    self.last = self.run("stop", *(["--force"] if force else []), timeout=3600)  # type: ignore[assignment]
                except StudioError as error:
                    self.last = {"error": str(error)}

            self.saving = threading.Thread(target=work, daemon=True)
            self.saving.start()
        return {"saving": True}

    def shot(self, body: dict) -> object:
        kind = body.get("kind", "screen")
        if kind not in {"screen", "area", "window"}:
            raise ValueError("kind must be screen, area or window")
        args = ["shot", str(kind)]
        delay = body.get("delay", 0)
        if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= 60:
            raise ValueError("delay must be 0-60 seconds")
        if delay:
            args += ["--delay", str(delay)]
        display = body.get("display", 1)
        if isinstance(display, bool) or not isinstance(display, int) or not 1 <= display <= 16:
            raise ValueError("display must be a number from 1")
        args += ["--display", str(display)]
        if body.get("clipboard") is True:
            args.append("--clipboard")
        # Area and window wait for the mouse on the Mac.
        return self.run(*args, timeout=delay + 300)

    def action(self, body: dict) -> object:
        action = body.get("action")
        if "path" in body:
            folder = self.project_folder(body.get("path"))
            if action == "delete":
                return self.run("delete", str(folder))
            if action == "reveal":
                return {"ok": subprocess.run(["open", "-R", str(folder)], check=False).returncode == 0}
            raise ValueError("a project can be revealed or deleted")
        name = self.member(body.get("name")).name
        if action in {"open", "reveal"}:
            ok = subprocess.run(["open", *(["-R"] if action == "reveal" else []), str(self.member(name))], check=False).returncode == 0
            return {"ok": ok}
        if action in {"copy", "delete"}:
            return self.run(action, name)
        if action == "trim":
            args = ["trim", name]
            for key in ("from", "to"):
                value = body.get(key)
                if value is not None:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)) or value < 0:
                        raise ValueError(f"{key} must be seconds")
                    args += [f"--{key}", f"{value:.3f}"]
            if len(args) == 2:
                raise ValueError("trim needs from or to")
            return self.run(*args, timeout=3600)
        if action == "convert":
            to = body.get("to")
            if to not in {"mp4", "mov", "gif", "m4a", "mp3", "wav"}:
                raise ValueError("convert to mp4, mov, gif, m4a, mp3 or wav")
            return self.run("convert", name, "--to", to, timeout=3600)
        raise ValueError("unknown action")

    @staticmethod
    def scene_id(value: object) -> str:
        """A scene id or its key number (1-9); never anything that looks like an option."""
        if not isinstance(value, str) or not STUDIO_ID.fullmatch(value):
            raise ValueError("scene must be a scene id or number")
        return value

    def save_setup(self, body: dict) -> object:
        return self.run("setup", "--set-json", "-", stdin=json.dumps(body), timeout=30)

    def scene(self, body: dict) -> object:
        return self.run("scene", self.scene_id(body.get("scene")), timeout=30)

    def mark(self, body: dict) -> object:
        label = body.get("label", "")
        if not isinstance(label, str) or len(label) > 200 or label.startswith("-") or not label.isprintable():
            raise ValueError("a mark is one line of at most 200 characters")
        return self.run("mark", *([label] if label else []), timeout=30)

    def project(self, raw: object) -> object:
        return self.run("project", str(self.project_folder(raw)), timeout=60)

    def save_project(self, body: dict) -> object:
        folder = self.project_folder(body.get("path"))
        project = body.get("project")
        if not isinstance(project, dict):
            raise TypeError("project must be a JSON object")
        return self.run("project", str(folder), "--set-json", "-", stdin=json.dumps(project), timeout=60)

    def export(self, body: dict) -> object:
        """Start an export in the background; the page follows it through export_status()."""
        args = ["export", str(self.project_folder(body.get("path")))]
        for key, (flag, allowed) in STUDIO_EXPORT_CHOICES.items():
            value = body.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or value not in allowed:
                raise ValueError(f"{key} must be one of " + ", ".join(str(item) for item in allowed))
            args += [flag, str(value)]
        for key, yes, no in (("normalize", "--normalize", "--no-normalize"), ("delete_sources", "--delete-sources", None)):
            value = body.get(key)
            if value is None:
                continue
            if not isinstance(value, bool):
                raise TypeError(f"{key} must be true or false")
            if value or no:
                args.append(yes if value else str(no))
        return self.run(*args, "--background", timeout=60)

    def camera_modes(self, device: object) -> object:
        if not isinstance(device, str) or not device.strip() or len(device) > 200 or device.startswith("-") or not device.isprintable():
            raise ValueError("device must be a camera name")
        # The probe opens the camera for a moment.
        return self.run("devices", "--modes", "--camera", device, timeout=60)

    def open_settings(self, body: dict) -> object:
        kind = body.get("kind")
        if kind not in STUDIO_SETTINGS:
            raise ValueError("kind must be screen, camera or microphone")
        return self.run("doctor", "--open", str(kind), timeout=30)

    def add_asset(self, name: object, source, length: int) -> dict:
        """Copy an uploaded PNG/JPEG into storage.root/studio/assets under a free name, never over a file."""
        if not 0 < length <= MAX_ASSET:
            raise ValueError(f"an image can be at most {MAX_ASSET // (1024 * 1024)} MB")
        clean = attachment_name(name)
        stem, suffix = os.path.splitext(clean)
        magic = ASSET_MAGIC.get(suffix.casefold())
        if magic is None:
            raise ValueError("only PNG and JPEG images can be sources")
        stem = stem[:100].rstrip() or "image"
        head = source.read(min(length, len(magic)))
        if not head.startswith(magic) or len(head) < len(magic):
            raise ValueError(f"this is not a {suffix[1:].upper()} image")
        folder = storage_path("studio", "assets")
        folder.mkdir(parents=True, exist_ok=True)
        target = write_unique(folder, stem, suffix, lambda handle: copy_exactly(source, handle, length, head))
        return {"asset": target.name}

    def add_project_asset(self, raw: object, name: object, source, length: int) -> dict:
        """A caption/text PNG or a sound file for the Edit tab, written into the project's assets/.

        Never over a file: an existing file with the same bytes is reused (captions are named by their
        content, so a redraw of an unchanged line costs nothing), anything else gets a free name.
        """
        folder = self.project_folder(raw)
        clean = attachment_name(name)
        stem, suffix = os.path.splitext(clean)
        suffix = suffix.casefold()
        image = suffix in ASSET_MAGIC
        if not image and suffix not in AUDIO_ASSETS:
            raise ValueError("only PNG/JPEG images and m4a, mp3, wav, flac, aac, aiff or caf sound can be added")
        most = MAX_ASSET if image else MAX_PROJECT_AUDIO
        if not 0 < length <= most:
            raise ValueError(f"the file can be at most {most // (1024 * 1024)} MB")
        head = source.read(min(length, 16))
        if (image and not head.startswith(ASSET_MAGIC[suffix])) or (not image and not audio_looks_right(suffix, head)):
            raise ValueError(f"this is not a {suffix[1:].upper()} file")
        assets = folder / "assets"
        if assets.is_symlink():
            raise ValueError("the project's assets folder is a link")
        assets.mkdir(exist_ok=True)
        stem = stem[:100].rstrip() or "file"
        body = None
        if image:  # small: compare with a file of the same name
            body = head + source.read(length - len(head))
            if len(body) != length:
                raise ValueError("the upload ended early")
            same = assets / f"{stem}{suffix}"
            if same.is_file() and not same.is_symlink() and same.read_bytes() == body:
                return {"asset": same.name}
        def write(handle) -> None:
            if body is not None:
                handle.write(body)
            else:
                copy_exactly(source, handle, length, head)

        return {"asset": write_unique(assets, stem, suffix, write).name}

    def import_sound(self, body: dict) -> dict:
        """Copy the sound of another project (an audio-only recording) into this one as a voice-over."""
        folder = self.project_folder(body.get("path"))
        source = self.project_file(body.get("from"), body.get("file"))
        suffix = source.suffix.casefold()
        if suffix not in AUDIO_ASSETS:
            raise ValueError("only a sound file can be imported")
        assets = folder / "assets"
        if assets.is_symlink():
            raise ValueError("the project's assets folder is a link")
        assets.mkdir(exist_ok=True)
        stem = f"{Path(str(body.get('from'))).name} {source.stem.lstrip('.')}"[:100]
        # The source is opened first: one that cannot be read leaves no empty file behind.
        with source.open("rb") as stream:
            target = write_unique(assets, stem, suffix, lambda out: shutil.copyfileobj(stream, out))
        return {"asset": target.name}

    def proxy(self, raw: object, start: bool) -> dict:
        """Light copies for the Edit tab (`ul capture proxy`), made in the background: {state, files, error}.

        `state` is idle, running, done or failed; a finished run is started again on request (it only makes
        what is missing or older than its original)."""
        folder = str(self.project_folder(raw))
        with self.lock:
            entry = self.proxies.get(folder) or {"state": "idle", "files": {}, "error": ""}
            if start and entry["state"] != "running":
                entry = {"state": "running", "files": entry["files"], "error": ""}

                def work(entry: dict = entry) -> None:
                    try:
                        data = self.run("proxy", folder, timeout=3600)
                        files = data.get("files", {}) if isinstance(data, dict) else {}
                        entry.update(state="done", files=files)
                    except Exception as error:  # the page must see "failed", never a run stuck at "running"
                        entry.update(state="failed", error=str(error) or type(error).__name__)

                threading.Thread(target=work, daemon=True).start()
            self.proxies[folder] = entry
            return dict(entry)

    def project_wave(self, raw: object, file: object, bars: object) -> object:
        folder = self.project_folder(raw)
        self.project_file(raw, file)
        if not isinstance(bars, str) or not bars.isdigit() or not 10 <= int(bars) <= 20000:
            raise ValueError("bars must be 10-20000")
        return self.run("wave", str(file), "--bars", bars, "--project", str(folder), timeout=600)

    def transcribe(self, body: dict) -> object:
        folder = self.project_folder(body.get("path"))
        args = ["transcribe", str(folder)]
        language = body.get("language")
        if language not in (None, ""):
            if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z]{2,4})?", language):
                raise ValueError("language must be a code such as en or ru")
            args += ["--language", language]
        model = body.get("model")
        if model not in (None, ""):
            if not isinstance(model, str) or len(model) > 200 or model.startswith("-") or not model.isprintable():
                raise ValueError("model must be a model name")
            args += ["--model", model]
        # Speech recognition of a long recording takes minutes; the page waits for it.
        return self.run(*args, timeout=3600)

    def open_project(self) -> dict:
        """Pick a project folder anywhere in the macOS folder dialog; capture remembers it.

        {"path": None} when cancelled, {"unavailable": True} without osascript.
        """
        osascript = shutil.which("osascript")
        if osascript is None:
            return {"unavailable": True}
        start = storage_path("captures", "projects")
        if not start.is_dir():
            start = Path.home()
        if not self.choose_lock.acquire(blocking=False):
            raise ValueError("The folder dialog is already open")
        try:
            command = [osascript]
            for line in CHOOSE_PROJECT_SCRIPT:
                command += ["-e", line]
            try:
                result = subprocess.run([*command, str(start)], capture_output=True, text=True, timeout=CHOOSE_TIMEOUT, check=False)
            except subprocess.TimeoutExpired:
                return {"path": None}
        finally:
            self.choose_lock.release()
        if result.returncode != 0:
            if "-128" in result.stderr:  # the user pressed Cancel
                return {"path": None}
            raise StudioError("The folder dialog failed: " + result.stderr.strip()[:300])
        chosen = result.stdout.strip()
        if not chosen:
            return {"path": None}
        if not chosen.startswith("/") or "\x00" in chosen:
            raise StudioError("the dialog did not answer with a folder")
        data = self.run("project", chosen.rstrip("/") or "/", "--remember", timeout=60)
        if not isinstance(data, dict) or not isinstance(data.get("path"), str):
            raise StudioError("ul capture did not describe the project")
        return {"path": data["path"], "project": data}

    @staticmethod
    def project_folder(raw: object) -> Path:
        """A project folder in captures/projects or one the user opened (recent-projects.json).

        The path must be absolute and normalised, the folder and its project.json real (no symlinks).
        """
        if not isinstance(raw, str) or not raw.startswith("/") or "\x00" in raw or os.path.normpath(raw) != raw:
            raise FileNotFoundError("unknown project")
        folder = Path(raw)
        manifest = folder / "project.json"
        if folder.is_symlink() or not folder.is_dir() or manifest.is_symlink() or not manifest.is_file():
            raise FileNotFoundError("unknown project")
        if folder.resolve().parent == storage_path("captures", "projects").resolve():
            return folder
        try:
            recent = json.loads(storage_path("studio", "recent-projects.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            recent = []
        if isinstance(recent, list) and raw in recent:
            return folder
        raise FileNotFoundError("unknown project")

    @classmethod
    def project_file(cls, raw: object, file: object) -> Path:
        """A file inside a project's media/ or assets/ folder: relative, no `..`, no symlink on the way."""
        folder = cls.project_folder(raw)
        if not isinstance(file, str) or not file or "\x00" in file or file.startswith("/") or os.path.normpath(file) != file:
            raise FileNotFoundError("unknown project file")
        parts = Path(file).parts
        proxy = len(parts) == 3 and parts[:2] == ("cache", "proxy")  # the Edit tab's light copies
        if (len(parts) < 2 or parts[0] not in {"media", "assets"} or ".." in parts) and not proxy:
            raise FileNotFoundError("unknown project file")
        target = folder
        for part in parts:
            target = target / part
            if target.is_symlink():
                raise FileNotFoundError("unknown project file")
        if not target.is_file() or not target.resolve().is_relative_to(folder.resolve()):
            raise FileNotFoundError("unknown project file")
        return target

    @staticmethod
    def asset_file(name: object) -> Path:
        """An image or rendered text in storage.root/studio/assets (no folders, no symlinks)."""
        folder = storage_path("studio", "assets")
        if not isinstance(name, str) or not name or "/" in name or "\x00" in name or name.startswith("."):
            raise FileNotFoundError("unknown asset")
        path = folder / name
        if path.suffix.casefold() not in ASSET_MAGIC or path.is_symlink() or not path.is_file() or path.resolve().parent != folder.resolve():
            raise FileNotFoundError("unknown asset")
        return path

    def project_thumb(self, raw: object) -> Path:
        """The first frame of the project's screen (or camera) track, through `ul capture thumb`."""
        folder = self.project_folder(raw)
        root = folder.resolve()
        for track in ("screen", "camera"):
            for item in sorted((folder / "media").glob(f"{track}-*.mp4")):
                # Resolved, so a symlinked media/ folder never hands out a file from elsewhere.
                if item.is_file() and not item.is_symlink() and item.resolve().is_relative_to(root):
                    data = self.run("thumb", str(item), timeout=60)
                    return Path(str(data.get("thumbnail") if isinstance(data, dict) else ""))
        raise FileNotFoundError("this project has no picture")

    @staticmethod
    def member(name: object) -> Path:
        """A file directly inside the capture folders; nothing else is ever served or changed."""
        # Not starting with "-" either: the name is passed to `ul capture`, where it would read as an option.
        if not isinstance(name, str) or not name or "/" in name or name.startswith((".", "-")):
            raise FileNotFoundError("unknown capture")
        for folder in ("screenshots", "recordings"):
            root = storage_path("captures", folder)
            path = root / name
            if path.is_file() and not path.is_symlink() and path.resolve().parent == root.resolve():
                return path
        raise FileNotFoundError(f"no capture named {name}")


GAMES = {
    "tetris": "Tetris",
    "snake": "Snake",
    "minesweeper": "Minesweeper",
    "invaders": "Space Invaders",
    "chomp": "Chomp",
    "dash": "Dash",
    "pingpong": "Ping Pong",
    "chess": "Chess",
}
# Games whose best score is the lowest, and the unit shown after it.
SCORE_UNITS = {"minesweeper": "s", "chess": " moves"}
LEVELS = ("easy", "normal", "hard")
GAME_KEYS = {"up", "down", "left", "right", "enter", "esc", "backspace"}
GAME_ROWS = (24, 80)
GAME_COLS = (72, 200)
MAX_EVENTS = 64


def _game_event(event: object) -> dict | None:
    """One browser input in the `ul game --stream` format, or None when invalid."""
    if not isinstance(event, dict):
        return None

    def cell(value: object, names: tuple[str, ...]) -> dict | None:
        if not isinstance(value, dict):
            return None
        out = {}
        for name in names:
            number = value.get(name)
            if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number < 1000:
                return None
            out[name] = number
        return out

    for kind in ("key", "release"):
        key = event.get(kind)
        if isinstance(key, str):
            if key in GAME_KEYS or (len(key) == 1 and key.isprintable()):
                return {kind: key}
            return None
    if "click" in event:
        click = cell(event["click"], ("y", "x"))
        button = event["click"].get("button", "left") if click else None
        if click is None or button not in {"left", "right", "middle"}:
            return None
        return {"click": {**click, "button": button}}
    if "hover" in event:
        hover = cell(event["hover"], ("y", "x"))
        return {"hover": hover} if hover else None
    if "resize" in event:
        size = cell(event["resize"], ("rows", "cols"))
        return {"resize": size} if size else None
    return None


class Arcade:
    """At most one `ul game --stream` process, fed by the page and read by one stream.

    The games stay in the Rust core; this only relays frames and input, so the
    desk and the terminal play the same games and share arcade.toml.
    """

    def __init__(self, binary: str | None, scores: Path, difficulty: str) -> None:
        self.binary = binary
        self.scores_file = scores
        self.difficulty = difficulty if difficulty in LEVELS else "normal"
        self.lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.session = ""
        self.reading = False
        self._available: bool | None = None
        self._availability_lock = threading.Lock()

    def available(self) -> bool:
        with self._availability_lock:
            return self._probe_available()

    def _probe_available(self) -> bool:
        if self._available is None:
            self._available = False
            if self.binary:
                try:
                    result = subprocess.run(
                        [self.binary, "game", "--help"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    self._available = result.returncode == 0 and "--stream" in result.stdout
                except (OSError, subprocess.TimeoutExpired):
                    pass
        return self._available

    def scores(self) -> dict:
        try:
            data = tomllib.loads(self.scores_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        games = []
        for name, label in GAMES.items():
            table = data.get(name) if isinstance(data.get(name), dict) else {}
            best = {
                level: table[level]
                for level in LEVELS
                if isinstance(table.get(level), int) and not isinstance(table.get(level), bool)
            }
            games.append(
                {
                    "name": name,
                    "label": label,
                    "lower": name in SCORE_UNITS,
                    "unit": SCORE_UNITS.get(name, ""),
                    "best": best,
                }
            )
        return {"available": self.available(), "difficulty": self.difficulty, "games": games}

    def start(self, game: object, level: object, rows: object, cols: object) -> str:
        if game is not None and game not in GAMES:
            raise ValueError("unknown game")
        if level is not None and (level not in LEVELS or game is None):
            raise ValueError("difficulty must be easy, normal or hard, with a game")
        sizes = []
        for value, (low, high) in ((rows, GAME_ROWS), (cols, GAME_COLS)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("rows and cols must be numbers")
            sizes.append(min(max(value, low), high))
        if not self.available():
            raise ValueError("games are not installed in this ul (feature `game`)")
        command = [self.binary or "ul", "game", "--stream", "--size", f"{sizes[0]}x{sizes[1]}"]
        if game is not None:
            command.append(str(game))
            if level is not None:
                command.append(str(level))
        with self.lock:
            self._stop_locked()
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                bufsize=0,
            )
            assert self.process.stdin is not None
            os.set_blocking(self.process.stdin.fileno(), False)
            self.session = secrets.token_hex(8)
            self.reading = False
            return self.session

    def _current(self, session: object) -> subprocess.Popen:
        if not isinstance(session, str) or not session or not hmac.compare_digest(session, self.session):
            raise GameEnded("this game has ended")
        if self.process is None:
            raise GameEnded("this game has ended")
        return self.process

    def send(self, session: object, events: object) -> None:
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            raise ValueError(f"events must be a list of at most {MAX_EVENTS}")
        lines = []
        for event in events:
            clean = _game_event(event)
            if clean is None:
                raise ValueError("invalid game input")
            lines.append(json.dumps(clean) + "\n")
        with self.lock:
            process = self._current(session)
            try:
                assert process.stdin is not None
                source = process.stdin.fileno()
                pending = memoryview("".join(lines).encode())
                deadline = time.monotonic() + 1
                while pending:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([], [source], [], remaining)[1]:
                        raise TimeoutError("the game stopped reading input")
                    try:
                        written = os.write(source, pending)
                    except BlockingIOError:
                        continue
                    pending = pending[written:]
            except (BrokenPipeError, ValueError, OSError) as error:
                # A timed-out partial JSON line must never prefix a later event.
                self._stop_locked()
                raise GameEnded("this game has ended") from error

    def claim(self, session: object) -> subprocess.Popen:
        """The process whose frames one stream may read; a second reader is refused."""
        with self.lock:
            process = self._current(session)
            if self.reading:
                raise GameEnded("this game is already shown in another tab")
            self.reading = True
            return process

    def stop(self, session: object = None) -> None:
        with self.lock:
            if session is not None:
                try:
                    self._current(session)
                except GameEnded:
                    return
            self._stop_locked()

    def stop_if(self, process: subprocess.Popen) -> None:
        with self.lock:
            if self.process is process:
                self._stop_locked()

    def _stop_locked(self) -> None:
        process, self.process, self.session = self.process, None, ""
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait()
        if process.stdout:
            process.stdout.close()


def game_binary() -> str | None:
    return os.environ.get("UNLAW_BIN") or shutil.which("ul")


def last_board(directory: Path) -> Path | None:
    """The board the page showed last (the newest entry of recent.json that still exists)."""
    items = _read_json(directory / "recent.json", [])
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str) and Path(item).is_file():
            return Path(item)
    return None


SERVER_FILE = "server.json"  # {pid, port, lstart} of the running page server


def _ps(pid: int, field: str) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", f"{field}="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env={**os.environ, "TZ": "UTC", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return " ".join(result.stdout.split())


def _outdated_server(directory: Path, port: int) -> int | None:
    """The pid of an earlier desk server holding `port` whose code has changed since it started (an update), or None.
    The page keeps its settings in localStorage, which belongs to the port: a new server on the next port would
    open an empty page, so an outdated one gives the port back. Two current desks still run side by side."""
    info = _read_json(directory / SERVER_FILE, {})
    if not isinstance(info, dict) or info.get("port") != port:
        return None
    pid = info.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1 or pid == os.getpid():
        return None
    started = _ps(pid, "lstart")
    if not started or started != info.get("lstart") or Path(__file__).name not in _ps(pid, "command"):
        return None
    try:
        began = calendar.timegm(time.strptime(started, "%a %b %d %H:%M:%S %Y"))
        changed = Path(__file__).stat().st_mtime
    except (OSError, ValueError):
        return None
    return pid if changed > began else None


def _stop_outdated(directory: Path, port: int) -> None:
    pid = _outdated_server(directory, port)
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _ps(pid, "pid"):
        time.sleep(0.1)
    print(f"Stopped the desk from before the update (pid {pid}).", flush=True)


def _record_server(directory: Path, port: int) -> None:
    _write_json(directory / SERVER_FILE, {"pid": os.getpid(), "port": port, "lstart": _ps(os.getpid(), "lstart")})


def _forget_server(directory: Path) -> None:
    info = _read_json(directory / SERVER_FILE, {})
    if isinstance(info, dict) and info.get("pid") == os.getpid():
        try:
            (directory / SERVER_FILE).unlink()
        except OSError:
            pass


def make_server(
    desk: Desk,
    port: int,
    token: str,
    exact: bool,
    arcade: Arcade | None = None,
    studio: Studio | None = None,
) -> ThreadingHTTPServer:
    """Bind 127.0.0.1 on `port` (0: any free port), trying the next ones unless `exact`."""
    last_error: OSError | None = None
    for candidate in (
        [port] if exact or port == 0 else range(port, min(port + 20, 65536))
    ):
        if arcade is None:
            arcade = Arcade(
                game_binary(),
                storage_path("runtime", "arcade.toml"),
                str(desk.config.get("games", {}).get("difficulty", "normal")),
            )
        if studio is None:
            studio = Studio(game_binary(), dict(desk.config.get("capture", {})))
        handler = type(
            "DeskHandler",
            (Handler,),
            {
                "desk": desk,
                "arcade": arcade,
                "studio": studio,
                "token": token,
                "port": candidate,
            },
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
            event = desk.pomodoro.tick(desk.current)
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


def serve(
    path: Path | None, config: dict, port: int | None, open_browser: bool, layer: str | None = None
) -> int:
    desk = Desk(path, config, storage_path("desk"), layer=layer)
    if layer == REMINDERS:
        desk.reminders.read(fresh=True)
    desk.remember()
    token = secrets.token_urlsafe(18)
    settings = desk.settings
    wanted = settings["port"] if port is None else port
    if wanted:
        _stop_outdated(desk.directory, wanted)
    server = make_server(desk, wanted, token, exact=port is not None)
    _record_server(desk.directory, server.server_address[1])

    def _terminate(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    previous_term = signal.signal(signal.SIGTERM, _terminate)
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    print(f"Desk: {url}", flush=True)
    print(f"Board: {desk.current if layer else path}", flush=True)
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
        signal.signal(signal.SIGTERM, previous_term)
        stop.set()
        server.RequestHandlerClass.arcade.stop()
        server.server_close()
        _forget_server(desk.directory)
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
        try:
            minutes = float(rest[0])
        except ValueError:
            raise ValueError(f"start takes a length in minutes, not {rest[0]!r}") from None
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


def _board_choice(args: list[str]) -> tuple[str | None, list[str]]:
    """`--board NAME` (or `-b`) anywhere before `--`; the rest stays in order (everything after `--` is text)."""
    rest, board = [], None
    position = 0
    while position < len(args):
        arg = args[position]
        if arg == "--":
            rest.extend(args[position + 1 :])
            break
        if arg in {"--board", "-b"}:
            if position + 1 >= len(args) or board is not None:
                raise ValueError(f"{arg} needs one board (a name or a .md file)")
            board = args[position + 1]
            position += 2
            continue
        rest.append(arg)
        position += 1
    return board, rest


def _chosen_board(raw: str | None, config: dict, boards_dir: Path) -> Path:
    return board_file(raw, boards_dir=boards_dir) if raw else default_board(config)


def _board_lines(board: KanbanBoard) -> list[str]:
    """Columns and numbered cards, the format `ul todo` printed (the agent reads it)."""
    lines: list[str] = []
    numbered = board.numbered_tasks()
    for section in board.sections:
        if lines:
            lines.append("")
        lines.append(section.name)
        tasks = [(number, task) for number, owner, task in numbered if owner is section]
        if not tasks:
            lines.append("  (empty)")
        for number, task in tasks:
            item = card(task)
            lines.append(f"  {number}. [{'x' if item['checked'] else ' '}] {item['title']}")
            lines.extend(f"     {detail}" for detail in item["details"] if detail)
    return lines


def _board_json(board: KanbanBoard, source: str, version: str) -> dict:
    numbered = board.numbered_tasks()
    return {
        "board": source,
        "version": version,
        "columns": [
            {
                "name": section.name,
                "cards": [
                    {"id": number, **card(task)}
                    for number, owner, task in numbered
                    if owner is section
                ],
            }
            for section in board.sections
        ],
    }


def _show_cli(args: list[str], config: dict, boards_dir: Path) -> int:
    as_json = "--json" in args
    reminders = "--reminders" in args
    rest = [arg for arg in args if arg not in {"--json", "--reminders"}]
    if len(rest) > 1 or any(arg.startswith("-") for arg in rest) or (reminders and rest):
        print(USAGE, file=sys.stderr)
        return 2
    if reminders:
        if not reminders_available(desk_settings(config)["reminders"]):
            raise ValueError("The Reminders layer is off (desk.reminders) or not on macOS")
        version, board, _, _ = Reminders().read(fresh=True)
        source = REMINDERS
    else:
        path = _chosen_board(rest[0] if rest else None, config, boards_dir)
        data = path.read_bytes()
        board, source, version = KanbanBoard.parse(data.decode("utf-8")), str(path), version_of(data)
    if as_json:
        print(json.dumps(_board_json(board, source, version), ensure_ascii=False, indent=2))
        return 0
    print(f"Board: {'Apple Reminders' if reminders else source}")
    print()
    print("\n".join(_board_lines(board)) if board.sections else "No columns.")
    return 0


def _list_cli(args: list[str], config: dict, boards_dir: Path) -> int:
    if args not in ([], ["--json"]):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        default: str | None = str(default_board(config))
    except (FileNotFoundError, ValueError):
        default = None
    try:
        boards = sorted(
            (path.resolve() for path in boards_dir.glob("*.md") if path.is_file()),
            key=lambda path: path.stem.casefold(),
        )
    except OSError:
        boards = []
    recent = _read_json(storage_path("desk") / "recent.json", [])
    recent_paths = [
        item for item in (recent if isinstance(recent, list) else [])
        if isinstance(item, str) and Path(item).is_file()
    ]
    reminders = reminders_available(desk_settings(config)["reminders"])
    if args:
        print(json.dumps({
            "default": default,
            "boards_dir": str(boards_dir),
            "boards": [{"name": path.stem, "path": str(path)} for path in boards],
            "recent": recent_paths,
            "reminders": reminders,
        }, ensure_ascii=False, indent=2))
        return 0
    print(f"Default: {default or '(none: set todo.vault_path and todo.file)'}")
    print(f"Boards in {boards_dir}:")
    width = max((len(path.stem) for path in boards), default=0)
    for path in boards:
        print(f"  {path.stem:<{width}}  {path}")
    if not boards:
        print("  (none; create one with: ul desk new <name>)")
    if recent_paths:
        print("Recent:")
        for item in recent_paths:
            print(f"  {item}")
    print(f"Reminders: {'available (ul desk show --reminders)' if reminders else 'off'}")
    return 0


def _change_cli(action: str, args: list[str], config: dict, boards_dir: Path) -> int:
    """add / move / done on a .md board, the same edits the page makes. The file is written only if it is still
    the version that was read; when the page or Obsidian changed it meanwhile, the edit is made again on the
    fresh file (a few times), so nobody's change is lost."""
    raw, rest = _board_choice(args)
    path = _chosen_board(raw, config, boards_dir)
    column: str | None = None
    if action == "add" and "--column" in rest:
        at = rest.index("--column")
        if at + 1 >= len(rest):
            raise ValueError("--column needs a column name")
        column = rest[at + 1]
        rest = rest[:at] + rest[at + 2 :]
    if action != "add" and (not rest or not rest[0].isdigit()):
        raise ValueError(f"{action} needs a card number from: ul desk show")
    if action == "move" and len(rest) < 2:
        raise ValueError("move needs a card number and a column")
    if action == "done" and len(rest) != 1:
        raise ValueError("done takes one card number")
    today = datetime.now().astimezone().date()
    text = _clean_text(quick_text(" ".join(rest), today)) if action == "add" else ""
    if action == "add" and not text:
        raise ValueError("The task text must be one non-empty line")

    # The card the user meant, by its line: a retry after a concurrent change must not act on another card
    # that now has the same number (the page checks `line` the same way).
    meant: list[str] = []

    def edit(board: KanbanBoard) -> str:
        if action == "add":
            if not board.sections:
                raise ValueError(f"{path} has no columns")
            section = board.section(column) if column else board.sections[0]
            section.tasks.append([f"- [ ] {text}"])
            return f"Added to {section.name}: {text}"
        number = int(rest[0])
        current = next((task[0] for n, _, task in board.numbered_tasks() if n == number), None)
        if current is not None:
            if meant and meant[0] != current:
                raise ValueError(f"Card #{number} changed while it was being edited; check `ul desk show` and try again")
            meant[:] = [current]
        if action == "move":
            target = board.section(" ".join(rest[1:]))
            source, task = board.pop_task(number)
            target.tasks.append(task)
            return f"Moved #{number}: {source.name} -> {target.name}"
        target = completed_section(board, completed_column_name(config))
        _, task = board.pop_task(number)
        title = complete_task(task, today)
        target.tasks.append(task)
        return f"Completed #{number}: {title}"

    for attempt in range(3):
        raw_bytes = path.read_bytes()
        board = KanbanBoard.parse(raw_bytes.decode("utf-8"))
        message = edit(board)
        try:
            write_board(path, board, expected=version_of(raw_bytes))
        except BoardChanged:
            if attempt == 2:
                raise
            continue
        print(message)
        return 0
    return 1


def _parse_serve(args: list[str]) -> tuple[str | None, int | None, bool, bool]:
    board: str | None = None
    port: int | None = None
    open_browser = True
    reminders = False
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--no-open":
            open_browser = False
        elif arg == "--reminders":
            reminders = True
        elif arg == "--port":
            if not rest or not rest[0].isdigit() or int(rest[0]) > 65535:
                raise ValueError("--port needs a number from 0 to 65535")
            port = int(rest.pop(0))
        elif arg.startswith("-") or board is not None:
            raise ValueError(f"Unexpected argument: {arg}")
        else:
            board = arg
    return board, port, open_browser, reminders


class _PlainText:
    """stdout/stderr without control characters: card text, Reminders titles and file names come
    from other programs and must not drive the terminal (newlines and tabs stay)."""

    _CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

    def __init__(self, stream) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        self._stream.write(self._CONTROL.sub("", text))
        return len(text)

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _PlainText(sys.stdout), _PlainText(sys.stderr)
    try:
        return _main(args)
    finally:
        sys.stdout, sys.stderr = saved


def _main(args: list[str]) -> int:
    try:
        config = load_config()
        action = args[0] if args else ""
        if action == "pomodoro":
            return _pomodoro_cli(args[1:], config)
        boards_dir = boards_folder(desk_settings(config)["boards_dir"], config_dir())
        if action == "new" and len(args) == 2:
            wanted = boards_dir / f"{args[1]}.md" if _bare_name(args[1]) else Path(args[1]).expanduser()
            if wanted.exists():
                raise ValueError(f"{wanted} already exists; open it with: ul desk {args[1]}")
            path = board_file(args[1], create=True, boards_dir=boards_dir)
            print(f"Board: {path}")
            return 0
        if action == "rm" and len(args) == 2:
            _, target = trash_board(args[1], config, boards_dir)
            print(f"Moved to the Trash: {target}")
            return 0
        if action == "path" and len(args) <= 2:
            print(board_file(args[1], boards_dir=boards_dir) if len(args) == 2 else default_board(config))
            return 0
        if action == "stats" and len(args) <= 2:
            return _stats_cli(
                board_file(args[1], boards_dir=boards_dir) if len(args) == 2 else default_board(config), config
            )
        if action == "show":
            return _show_cli(args[1:], config, boards_dir)
        if action == "list":
            return _list_cli(args[1:], config, boards_dir)
        if action in {"add", "move", "done"}:
            return _change_cli(action, args[1:], config, boards_dir)
        if action in {"new", "rm", "path", "stats"}:
            print(USAGE, file=sys.stderr)
            return 2
        board, port, open_browser, reminders = _parse_serve(args)
        if reminders:
            if not reminders_available(desk_settings(config)["reminders"]):
                raise ValueError("The Reminders layer is off (desk.reminders) or not on macOS")
            path = board_file(board, boards_dir=boards_dir) if board else _optional_board(config)
            return serve(path, config, port, open_browser, REMINDERS)
        path = (
            board_file(board, boards_dir=boards_dir)
            if board
            else last_board(storage_path("desk")) or default_board(config)
        )
        return serve(path, config, port, open_browser)
    except (ConfigError, FileNotFoundError, OSError, ValueError, OverflowError) as error:
        print(f"unlaw desk: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
