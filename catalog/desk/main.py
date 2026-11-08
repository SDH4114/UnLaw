# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Kanban board, TODO list and pomodoro timer in the browser, on your Obsidian board file."""
from __future__ import annotations

COMMAND_HELP = 'Kanban board, TODO list and pomodoro timer in the browser, on your Obsidian board file.\nUsage: ul desk [board.md|name] [--reminders] [--port N] [--no-open]\n       ul desk new <board.md|name> | path [board.md|name] | stats [board.md|name]\n       ul desk pomodoro [status|start [minutes] [--card <text>]|pause|resume|stop|skip]\nActions:\n  no arguments     Serve the todo board (todo.vault_path + todo.file) on 127.0.0.1\n                   and open it in the browser; Ctrl+C stops the server\n  board.md         Serve another Kanban Markdown file instead\n  name             A bare name (no folder, no .md) is a board in desk.boards_dir\n  --reminders      Start on the Apple Reminders layer (see Reminders below)\n  --port N         Use exactly this port (0 = any free one); default desk.port,\n                   or the next free port after it\n  --no-open        Print the address without opening the browser\n  new <board.md>   Create a board with To do / Doing / Done columns\n  new <name>       The same in desk.boards_dir (created when missing)\n  path [board.md]  Print the board\'s path\n  stats [board.md] Focus sessions, finished tasks, streak and busiest cards\n  pomodoro         Show or control the timer from the terminal; the page shows\n                   the same timer, and a macOS notification marks each phase end\nPage: Board (drag cards between columns, double-click to edit), Today (overdue,\n  due today, in progress, next 7 days), Stats, Canvas, Games. Keys: n new card,\n  / search, space start/pause timer, 1 2 3 4 views, Esc clear filters, ? keys.\nGames: Tetris, Snake, Minesweeper, Space Invaders, Chomp and Dash from `ul game`,\n  played in the page with keyboard and mouse at easy/normal/hard. The page\n  runs `ul game --stream` (the same Rust games), so best scores are the ones\n  in storage.root/runtime/arcade.toml that the terminal arcade shows too.\n  Leaving the tab pauses a game; closing the page ends it.\nCanvas: a whiteboard in the page. Files are JSON Canvas (.canvas, jsoncanvas.org),\n  so Obsidian Canvas opens them: text, file, link and group nodes plus edges.\n  Freehand drawings and shapes (rectangle, ellipse, diamond, line, arrow, text)\n  are stored in the same file under the extra top-level key "unlaw", which\n  Obsidian ignores; every key Unlaw does not know is kept as it was. A bare\n  name opens or creates <desk.canvas_dir>/<name>.canvas; any other path must\n  end in .canvas. Saving replaces the file atomically and is refused (the page\n  reloads) when the file changed meanwhile. A new canvas is an empty\n  {"nodes": [], "edges": []}; an existing file is never overwritten on create.\nBoards: the board menu lists Apple Reminders, recent boards and the boards in\n  desk.boards_dir; "New board…" asks for a name and creates it there.\nReminders: a separate layer, never mixed into your .md boards. Each Reminders\n  list is a column, each open reminder a card (its notes as details). Changes\n  go straight to Reminders (and iCloud): add, edit, @date sets the due date,\n  drag to another column moves it to that list, done completes it, delete\n  removes it, a new column creates a list. Order inside a list stays the\n  Reminders app\'s own. Uses EventKit through osascript; the first use asks to\n  allow your terminal in System Settings > Privacy & Security > Reminders.\nCards: #tag filters, @{2026-11-01} due dates (quick add: @today @tomorrow\n  @сегодня @завтра @+3 @2026-11-01), [[note]] opens the note in Obsidian.\n  Done cards move to todo.completed_column (or the board\'s Done column).\nThe file stays the source of truth: ul todo, the agent and Obsidian see every\n  change, and edits made elsewhere appear on the page within two seconds.\nSecurity: listens on 127.0.0.1 only and needs the random token in the printed\n  address; it reads and writes only the open board, Reminders (when that\n  layer is open), canvas files you open and storage.root/desk.\nSettings: desk.port (8765), desk.open_browser (true), desk.sound (true),\n  desk.reminders (true; false hides the layer), desk.boards_dir ("boards":\n  a relative path is inside the Unlaw config directory, ~ works),\n  desk.canvas_dir ("canvas", the same rules),\n  desk.pomodoro.work (25), short_break (5), long_break (15), cycles (4) in minutes;\n  todo.vault_path, todo.file, todo.completed_column, apps.lofi_url,\n  games.difficulty (default level on the Games tab).\nStorage: storage.root/desk (timer state, pomodoro.jsonl log, recent boards,\n  recent-canvas.json with the last 8 canvases).\nDependencies: Python standard library; osascript for notifications and the\n  Reminders layer; the Games tab needs ul built with the `game` feature.\nExamples: ul desk\n          ul desk ~/notes/Project.md --no-open\n          ul desk new Work            (~/.config/unlaw/boards/Work.md by default)\n          ul desk --reminders\n          ul desk pomodoro start 50 --card "Write chapter 3"\n'

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
    newline: str = "\n"

    @classmethod
    def parse(cls, text: str) -> KanbanBoard:
        # Only \n and \r\n end a line: str.splitlines() would also split on \x0b, \x0c, \x85, \u2028 and others inside a card.
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = re.split(r"\r?\n", text)
        first_heading = next((i for i, line in enumerate(lines) if HEADING.match(line)), None)
        if first_heading is None:
            raise ValueError("TODO.md has no '##' Kanban columns")
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


def write_board(path: Path, board: KanbanBoard) -> None:
    """Replace the board file atomically (a temporary file next to it, then rename)."""
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
function wait(isDone) {
  const until = Date.now() + 60000;
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
    const store = $.EKEventStore.alloc.init;
    let status = Number($.EKEventStore.authorizationStatusForEntityType($.EKEntityTypeReminder));
    if (status === 0) {
      let answered = false;
      store.requestFullAccessToRemindersWithCompletion((granted) => { answered = true; });
      wait(() => answered);
      status = Number($.EKEventStore.authorizationStatusForEntityType($.EKEntityTypeReminder));
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
      if (!wait(() => fetched !== null)) throw new Error("Reminders did not answer");
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

    def __init__(self, timeout: float = 60, clock=time.monotonic) -> None:
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

import json
import math
import os
import re
import tempfile
from pathlib import Path


NEW_CANVAS = {"nodes": [], "edges": []}
NODE_TYPES = {"text", "file", "link", "group"}
ELEMENT_TYPES = {"freedraw", "rectangle", "ellipse", "diamond", "line", "arrow", "text"}
POINT_TYPES = {"freedraw", "line", "arrow"}
MAX_ELEMENTS = 20000
MAX_NODES = 20000
MAX_EDGES = 20000
MAX_POINTS = 200000
MAX_TEXT = 20000
COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def _number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _text(value: object, what: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{what}: text must be a string")
    if len(value) > MAX_TEXT:
        raise ValueError(f"{what}: text is longer than {MAX_TEXT} characters")


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


def _validate_node(node: dict) -> None:
    what = f"node {node['id']!r}"
    if node.get("type") not in NODE_TYPES:
        raise ValueError(f"{what}: type must be one of {', '.join(sorted(NODE_TYPES))}")
    for key in ("x", "y", "width", "height"):
        if not _number(node.get(key)):
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


def _validate_element(element: dict) -> int:
    """Check one drawing element; returns how many points it has."""
    what = f"element {element['id']!r}"
    kind = element.get("type")
    if kind not in ELEMENT_TYPES:
        raise ValueError(
            f"{what}: type must be one of {', '.join(sorted(ELEMENT_TYPES))}"
        )
    for key in ("x", "y", "width", "height"):
        if not _number(element.get(key)):
            raise ValueError(f"{what}: {key} must be a number")
    if "angle" in element and not _number(element["angle"]):
        raise ValueError(f"{what}: angle must be a number")
    if "stroke" in element and not (
        isinstance(element["stroke"], str) and COLOR.fullmatch(element["stroke"])
    ):
        raise ValueError(f"{what}: stroke must look like #rrggbb")
    fill = element.get("fill")
    if fill is not None and not (isinstance(fill, str) and COLOR.fullmatch(fill)):
        raise ValueError(f"{what}: fill must be #rrggbb or null")
    width = element.get("strokeWidth")
    if "strokeWidth" in element and not (_number(width) and 1 <= width <= 20):
        raise ValueError(f"{what}: strokeWidth must be 1-20")
    rough = element.get("roughness")
    if "roughness" in element and not (_number(rough) and 0 <= rough <= 2):
        raise ValueError(f"{what}: roughness must be 0-2")
    if "seed" in element and (
        isinstance(element["seed"], bool) or not isinstance(element["seed"], int)
    ):
        raise ValueError(f"{what}: seed must be an integer")
    size = element.get("fontSize")
    if "fontSize" in element and not (_number(size) and 8 <= size <= 200):
        raise ValueError(f"{what}: fontSize must be 8-200")
    if kind == "text" or "text" in element:
        if "text" not in element:
            raise ValueError(f"{what}: text is missing")
        _text(element["text"], what)
    count = 0
    if kind in POINT_TYPES or "points" in element:
        points = element.get("points")
        if not isinstance(points, list):
            raise ValueError(f"{what}: points must be a list of [x, y]")
        for point in points:
            if not (
                isinstance(point, list)
                and len(point) == 2
                and all(_number(value) for value in point)
            ):
                raise ValueError(f"{what}: points must be a list of [x, y] numbers")
        count = len(points)
    return count


def _validate_unlaw(extra: object) -> None:
    if not isinstance(extra, dict):
        raise ValueError("unlaw must be an object")
    if extra.get("version") != 1 or isinstance(extra.get("version"), bool):
        raise ValueError("unlaw.version must be 1")
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
  --bg: #f4f3ef; --panel: #ffffff; --column: #eae9e4; --sunken: #e2e0da; --text: #1d1d1f; --muted: #6e6e73;
  --line: #dad8d1; --accent: #3a6df0; --accent-soft: #e3eafd; --danger: #d4483b; --ok: #2f9e5b;
  --warn: #c98a12; --shadow: 0 1px 2px rgba(0,0,0,.06), 0 2px 8px rgba(0,0,0,.05);
  --lift: 0 2px 4px rgba(0,0,0,.07), 0 8px 24px rgba(0,0,0,.08);
  --radius: 12px; --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  --mono: "SF Mono", ui-monospace, Menlo, monospace;
  color-scheme: light;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #141416; --panel: #212124; --column: #1b1b1e; --sunken: #18181a; --text: #ececee; --muted: #9a9aa1;
  --line: #2f2f33; --accent: #6b93ff; --accent-soft: #263050; --danger: #ff6b5e; --ok: #4fc581;
  --warn: #f0b443; --shadow: 0 1px 2px rgba(0,0,0,.4), 0 2px 10px rgba(0,0,0,.25);
  --lift: 0 2px 6px rgba(0,0,0,.45), 0 10px 28px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--text); font: 14px/1.45 var(--font); display: flex; flex-direction: column; -webkit-font-smoothing: antialiased; }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 5px 10px; transition: background .12s, border-color .12s, color .12s; }
button:hover { border-color: var(--accent); }
button:disabled { opacity: .45; cursor: default; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
button.primary:hover { filter: brightness(1.08); }
button.ghost { border-color: transparent; background: transparent; color: var(--muted); }
button.ghost:hover { background: var(--column); color: var(--text); }
button.icon { width: 32px; height: 32px; padding: 0; display: inline-grid; place-items: center; }
button.icon svg { width: 17px; height: 17px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
input, select { border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 5px 9px; outline: none; }
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

header { display: flex; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; position: relative; z-index: 2; }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 680; letter-spacing: -.01em; }
.brand i { width: 22px; height: 22px; border-radius: 7px; background: linear-gradient(135deg, var(--accent), #8a5cf6); display: inline-block; }
#boards { max-width: 230px; border-color: transparent; background: var(--column); font-weight: 550; }
.tabs { display: flex; gap: 2px; background: var(--column); border-radius: 10px; padding: 3px; }
.tabs button { border: none; background: transparent; padding: 4px 13px; border-radius: 8px; color: var(--muted); font-weight: 550; }
.tabs button:hover { color: var(--text); }
.tabs button.on { background: var(--panel); box-shadow: var(--shadow); color: var(--text); }
.spacer { flex: 1; }
.timer { display: flex; align-items: center; gap: 8px; padding: 3px 4px 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); }
.timer .phase { font-size: 12px; color: var(--muted); }
.timer .clock { font: 600 15px var(--mono); min-width: 48px; text-align: right; }
.timer.work { border-color: color-mix(in srgb, var(--danger) 45%, var(--line)); }
.timer.work .clock { color: var(--danger); }
.timer.short .clock, .timer.long .clock { color: var(--ok); }
.timer .bar { width: 70px; height: 4px; background: var(--column); border-radius: 2px; overflow: hidden; }
.timer .bar i { display: block; height: 100%; background: currentColor; width: 0; transition: width .5s linear; }
.timer.work .bar i { background: var(--danger); }
.timer.short .bar i, .timer.long .bar i { background: var(--ok); }
.timer .linked { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--muted); }
.timer button { padding: 2px 10px; border-radius: 999px; }
.timer #play { background: var(--text); color: var(--bg); border-color: var(--text); }
.actions-bar { display: flex; gap: 2px; }

.toolbar { display: flex; align-items: center; gap: 10px; padding: 10px 16px 0; flex-wrap: wrap; }
.toolbar.hidden { display: none; }
.search { position: relative; }
.search input { width: 240px; padding-left: 30px; background: var(--panel); }
.search svg { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); width: 15px; height: 15px; stroke: var(--muted); fill: none; stroke-width: 2; }
#filter { display: none; }
#filter.on { display: inline-flex; }
.summary { display: flex; gap: 6px; flex-wrap: wrap; }
.pill { font-size: 12px; padding: 2px 9px; border-radius: 999px; background: var(--column); color: var(--muted); }
.pill b { color: var(--text); font-weight: 600; }
.pill.late b { color: var(--danger); }
.pill.today b { color: var(--warn); }

main { flex: 1; overflow: auto; }
.board { display: flex; gap: 14px; padding: 14px 16px 16px; align-items: flex-start; min-height: 100%; }
.column { background: var(--column); border-radius: var(--radius); width: 296px; flex: 0 0 296px; display: flex; flex-direction: column; max-height: calc(100vh - 128px); border-top: 3px solid transparent; }
.column.doing { border-top-color: var(--warn); }
.column.done { border-top-color: var(--ok); }
.column.drop { outline: 2px dashed var(--accent); outline-offset: -2px; }
.column h2 { font-size: 13px; font-weight: 650; margin: 0; padding: 10px 10px 6px 12px; display: flex; gap: 6px; align-items: center; }
.column h2 .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.column h2 .count { color: var(--muted); font-weight: 600; font-size: 11px; background: var(--sunken); border-radius: 999px; padding: 0 7px; line-height: 18px; }
.column h2 button { padding: 0; width: 22px; height: 22px; line-height: 1; border: none; background: transparent; color: var(--muted); border-radius: 6px; font-size: 17px; }
.column h2 button:hover { background: var(--sunken); color: var(--text); }
.cards { padding: 4px 8px; overflow-y: auto; flex: 1; min-height: 20px; }
.card { background: var(--panel); border-radius: 9px; box-shadow: var(--shadow); padding: 9px 10px; margin-bottom: 7px; display: flex; gap: 9px; align-items: flex-start; cursor: grab; position: relative; border: 1px solid transparent; transition: box-shadow .12s, transform .12s; }
.card:hover { box-shadow: var(--lift); }
.card.dragging { opacity: .4; }
.card.focus { border-color: var(--danger); box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger) 18%, transparent); }
.card.checked .text { color: var(--muted); text-decoration: line-through; }
.card .check { width: 17px; height: 17px; border-radius: 50%; border: 1.5px solid var(--muted); flex: 0 0 17px; margin-top: 1px; padding: 0; background: transparent; position: relative; }
.card .check:hover { border-color: var(--ok); background: var(--accent-soft); }
.card.checked .check { background: var(--ok); border-color: var(--ok); }
.card.checked .check::after { content: ""; position: absolute; left: 5px; top: 2px; width: 4px; height: 8px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
.card .body { flex: 1; min-width: 0; word-wrap: break-word; }
.card .meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
.card .details { margin-top: 4px; color: var(--muted); font-size: 12px; white-space: pre-wrap; }
.card .actions { display: none; gap: 2px; position: absolute; right: 6px; top: 5px; background: var(--panel); border-radius: 7px; box-shadow: var(--shadow); padding: 2px; }
.card:hover .actions { display: flex; }
.card .actions button { padding: 1px 7px; font-size: 12px; border: none; background: transparent; }
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
.newcol { flex: 0 0 220px; }
.newcol input { width: 100%; background: transparent; border-style: dashed; padding: 9px 12px; }
.page { max-width: 780px; margin: 0 auto; padding: 18px 16px 60px; }
.page h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 26px 0 8px; display: flex; align-items: center; gap: 8px; }
.page h3 .n { background: var(--column); border-radius: 999px; padding: 0 7px; letter-spacing: 0; }
.page .quick { display: flex; gap: 8px; }
.page .quick input { flex: 1; padding: 10px 14px; border-radius: 10px; box-shadow: var(--shadow); }
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

.arcade { display: grid; grid-template-columns: 272px 1fr; gap: 14px; padding: 14px 16px 16px; height: 100%; min-height: 460px; }
.side { display: flex; flex-direction: column; gap: 10px; min-height: 0; overflow-y: auto; }
.side h4 { margin: 6px 2px 0; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.levels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; background: var(--column); border-radius: 10px; padding: 3px; }
.levels button { border: none; background: transparent; border-radius: 8px; padding: 5px 0; color: var(--muted); font-weight: 550; }
.levels button.on { background: var(--panel); box-shadow: var(--shadow); color: var(--text); }
.levels button.on.hard { color: var(--danger); }
.tile { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; text-align: left; padding: 10px 12px; border-radius: 10px; background: var(--panel); border: 1px solid transparent; box-shadow: var(--shadow); }
.tile:hover { border-color: var(--accent); }
.tile.on { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.tile b { font-weight: 650; }
.tile small { grid-column: 1 / -1; color: var(--muted); font-size: 12px; line-height: 1.35; }
.tile .best { font: 600 12px var(--mono); color: var(--warn); align-self: center; }
.tile .best.none { color: var(--muted); font-weight: 400; }
.records { background: var(--panel); border-radius: 10px; box-shadow: var(--shadow); padding: 6px 10px; font-size: 12px; }
.records table { width: 100%; border-collapse: collapse; }
.records th { color: var(--muted); font-weight: 500; text-align: right; padding: 3px 0; }
.records th:first-child, .records td:first-child { text-align: left; }
.records td { text-align: right; padding: 3px 0; font-family: var(--mono); border-top: 1px solid var(--line); }
.records td:first-child { font-family: var(--font); }
.stage { display: flex; flex-direction: column; min-height: 0; min-width: 0; gap: 8px; }
.screen { flex: 1; min-height: 0; background: #0e1014; border-radius: var(--radius); display: grid; place-items: center; position: relative; overflow: hidden; box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), var(--shadow); }
.screen canvas { display: block; cursor: crosshair; }
.screen .idle { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: #c9ccd4; text-align: center; padding: 20px; }
.screen .idle b { font: 700 22px var(--mono); letter-spacing: .3em; color: #ffd84d; }
.screen .idle span { color: #8b8f98; font-size: 13px; }
.screen:fullscreen { border-radius: 0; }
.status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.status .what { font-weight: 600; }
.status .hint { color: var(--muted); font-size: 12px; flex: 1; }
.status .live { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.status .live.on { background: var(--ok); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 25%, transparent); }

#toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%) translateY(6px); background: var(--text); color: var(--bg); padding: 8px 14px; border-radius: 9px; opacity: 0; transition: opacity .2s, transform .2s; pointer-events: none; max-width: 80vw; box-shadow: var(--lift); z-index: 20; }
#toast.on { opacity: .96; transform: translateX(-50%); }
kbd { font: 11px var(--mono); border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 5px; padding: 0 5px; background: var(--panel); }
#help { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: none; place-items: center; z-index: 10; }
#help.on { display: grid; }
#help .sheet { background: var(--panel); border-radius: 14px; box-shadow: var(--lift); padding: 18px 22px; width: min(460px, 92vw); }
#help h3 { margin: 0 0 10px; font-size: 15px; }
#help dl { display: grid; grid-template-columns: auto 1fr; gap: 7px 16px; margin: 0; font-size: 13px; }
#help dt { text-align: right; white-space: nowrap; }
#help dd { margin: 0; color: var(--muted); }
.studio { display: grid; grid-template-columns: 300px 1fr; gap: 14px; padding: 14px 16px 16px; min-height: 100%; align-items: start; }
.controls { position: sticky; top: 14px; display: flex; flex-direction: column; gap: 9px; background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 12px 14px 14px; }
.controls h4 { margin: 6px 0 0; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.controls label { display: grid; gap: 3px; font-size: 12px; color: var(--muted); }
.controls label.check { display: flex; align-items: center; gap: 7px; color: var(--text); font-size: 13px; }
.controls select { width: 100%; }
.modes { grid-template-columns: repeat(2, 1fr); }
.recbox { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 12px 0 4px; }
.recbtn { width: 64px; height: 64px; border-radius: 50%; border: 3px solid var(--line); background: var(--panel); display: grid; place-items: center; padding: 0; }
.recbtn i { width: 26px; height: 26px; border-radius: 50%; background: #e5484d; transition: border-radius .15s, width .15s, height .15s; }
.recbtn.on i { width: 22px; height: 22px; border-radius: 5px; }
.recbtn:hover { border-color: #e5484d; }
.recclock { font: 600 22px var(--mono); letter-spacing: .02em; }
.recclock.live { color: #e5484d; }
.recstate { font-size: 12px; color: var(--muted); text-align: center; min-height: 16px; }
.row { display: flex; gap: 6px; flex-wrap: wrap; }
.row button { flex: 1; }
.monitor { position: relative; background: #0e1014; border-radius: var(--radius); aspect-ratio: 16 / 10; max-height: 58vh; width: 100%; overflow: hidden; display: grid; place-items: center; box-shadow: var(--shadow); }
.monitor img.screen { width: 100%; height: 100%; object-fit: contain; }
.monitor video.cam { position: absolute; width: 24%; border-radius: 10px; box-shadow: 0 4px 18px rgba(0,0,0,.5); background: #000; transform: scaleX(-1); }
.monitor video.cam.full { position: static; width: 100%; height: 100%; object-fit: contain; border-radius: 0; box-shadow: none; }
.monitor video.cam.bottom-right { right: 3%; bottom: 4%; } .monitor video.cam.bottom-left { left: 3%; bottom: 4%; }
.monitor video.cam.top-right { right: 3%; top: 4%; } .monitor video.cam.top-left { left: 3%; top: 4%; }
.monitor .note { color: #8b8f98; text-align: center; padding: 20px; font-size: 13px; }
.monitor .meter { width: 70%; height: 14px; border-radius: 7px; background: #23262d; overflow: hidden; }
.monitor .meter i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, #3ed67a, #ffd84d 75%, #ff5f57); transition: width .06s linear; }
.monitor .badge { position: absolute; left: 12px; top: 12px; background: rgba(229,72,77,.92); color: #fff; font: 600 12px var(--mono); padding: 3px 9px; border-radius: 999px; display: none; }
.monitor .badge.on { display: block; }
.monitor .badge.paused { background: rgba(120,120,128,.9); }
.monbar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin: 8px 0 4px; }
.monbar .hint { color: var(--muted); font-size: 12px; flex: 1; }
.libhead { display: flex; align-items: center; gap: 10px; margin: 16px 0 8px; }
.libhead h3 { margin: 0; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.libhead .levels { grid-template-columns: repeat(4, auto); }
.libhead .levels button { padding: 3px 10px; }
.library { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; }
.item { background: var(--panel); border-radius: 10px; box-shadow: var(--shadow); overflow: hidden; cursor: pointer; border: 1px solid transparent; text-align: left; padding: 0; display: flex; flex-direction: column; }
.item:hover { border-color: var(--accent); box-shadow: var(--lift); }
.item .pic { aspect-ratio: 16 / 10; background: #15171c center / cover no-repeat; display: grid; place-items: center; color: #8b8f98; position: relative; }
.item .pic img { width: 100%; height: 100%; object-fit: cover; }
.item .pic .len { position: absolute; right: 6px; bottom: 6px; background: rgba(0,0,0,.7); color: #fff; font: 11px var(--mono); padding: 1px 6px; border-radius: 5px; }
.item .pic svg { width: 34px; height: 34px; stroke: #8b8f98; fill: none; stroke-width: 1.6; }
.item .cap { padding: 7px 9px 8px; font-size: 12px; }
.item .cap b { display: block; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .cap span { color: var(--muted); }
.rec-pill { display: none; border: none; background: rgba(229,72,77,.12); color: #e5484d; font: 600 12px var(--mono); border-radius: 999px; padding: 4px 10px; }
.rec-pill.on { display: inline-flex; gap: 6px; align-items: center; }
.rec-pill.on::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #e5484d; animation: blink 1.2s infinite; }
.rec-pill.paused::before { animation: none; background: var(--muted); }
@keyframes blink { 50% { opacity: .25; } }
#viewer { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: none; place-items: center; z-index: 12; }
#viewer.on { display: grid; }
#viewer .sheet { background: var(--panel); border-radius: 14px; box-shadow: var(--lift); width: min(1100px, 94vw); max-height: 94vh; overflow: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
#viewer .media { background: #0e1014; border-radius: 10px; display: grid; place-items: center; min-height: 120px; }
#viewer .media video, #viewer .media img { max-width: 100%; max-height: 66vh; display: block; }
#viewer .media audio { width: 90%; margin: 30px 0; }
#viewer .top { display: flex; align-items: center; gap: 10px; background: none; box-shadow: none; padding: 0; }
#viewer .top b { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#viewer .tools { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
#viewer .tools .sep { width: 1px; height: 22px; background: var(--line); margin: 0 4px; }
#viewer .tools .mark { font: 12px var(--mono); color: var(--muted); }
.voice { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: stretch; justify-content: center; gap: 10px; padding: 18px; }
.voice-clock { font: 600 34px var(--mono); color: #f2f2f7; text-align: center; letter-spacing: .02em; }
.voice .note { position: static; }
canvas.wave { width: 100%; height: 46%; display: block; }
canvas.wave.strip { position: absolute; left: 0; right: 0; bottom: 0; height: 64px; background: linear-gradient(transparent, rgba(0,0,0,.55)); }
#viewer canvas.filewave { width: 100%; height: 96px; display: block; cursor: pointer; background: #0e1014; border-radius: 10px; }
@media (max-width: 860px) { .studio { grid-template-columns: 1fr; } .controls { position: static; } }
@media (max-width: 760px) {
  .arcade { grid-template-columns: 1fr; height: auto; }
  .screen { min-height: 360px; }
  .search input { width: 170px; }
}
</style>
</head>
<body>
<header>
  <span class="brand"><i></i>Desk</span>
  <select id="boards" title="Boards"></select>
  <div class="tabs" id="tabs">
    <button data-view="board" class="on" title="Board (1)">Board</button>
    <button data-view="today" title="Today (2)">Today</button>
    <button data-view="stats" title="Stats (3)">Stats</button>
    <button data-view="games" title="Games (4)">Games</button>
    <button data-view="studio" title="Studio: record and screenshots (5)">Studio</button>
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
    <dt><kbd>1</kbd> … <kbd>5</kbd></dt><dd>Board, Today, Stats, Games, Studio</dd>
    <dt><kbd>Esc</kbd></dt><dd>Clear search and tag filter</dd>
    <dt>double-click</dt><dd>Edit a card; drag cards between columns</dd>
    <dt>Games</dt><dd>While a game runs every key goes to it: arrows/WASD, Space, P pause, Esc leaves. Mouse works as in the terminal.</dd>
    <dt>Studio</dt><dd><kbd>r</kbd> start / stop recording, <kbd>p</kbd> pause / resume. Recording runs <code>ul capture</code>, so it keeps going when the page is closed.</dd>
    <dt><kbd>?</kbd></dt><dd>This list</dd>
  </dl>
</div></div>
<div id="viewer"><div class="sheet" id="viewerSheet"></div></div>
<div id="toast"></div>
<script>
"use strict";
const params = new URLSearchParams(location.search);
if (params.get("token")) {
  sessionStorage.setItem("desk-token", params.get("token"));
  history.replaceState(null, "", location.pathname + location.hash);
}
const TOKEN = sessionStorage.getItem("desk-token") || "";
const VIEWS = ["board", "today", "stats", "games", "studio"];
const state = { board: null, view: VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : localStorage.getItem("desk-view") || "board", query: "", tag: "", timer: null, timerAt: 0, editing: null, dragging: null, stats: null };
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
  if (!state.editing && !["games", "studio"].includes(state.view)) render();
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
      h("h2", {}, h("span", { class: "name", text: column.name, title: column.name }),
        h("span", { class: "count", text: state.query || state.tag ? shown + "/" + column.cards.length : column.cards.length }),
        h("button", { title: "Add a card to " + column.name, text: "+", onclick: () => input.focus() })),
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
  const page = h("div", { class: "page" }, h("div", { class: "quick" }, quick));
  const section = (title, items) => {
    page.append(h("h3", {}, title, h("span", { class: "n", text: items.length })));
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
  $("toolbar").classList.toggle("hidden", ["games", "stats", "studio"].includes(state.view));
  const filter = $("filter");
  filter.classList.toggle("on", Boolean(state.tag));
  filter.textContent = state.tag ? "#" + state.tag + " ✕" : "";
  renderSummary();
  if (state.view === "games") { renderGames(main); return; }
  if (state.view === "studio") { renderStudio(main); return; }
  if (!state.board) return;
  if (state.view === "stats") { renderStats(main); return; }
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
  state.view = view;
  localStorage.setItem("desk-view", view);
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
};
const PALETTE = { red: "#ff5f57", green: "#3ed67a", yellow: "#ffd84d", blue: "#4d8dff", magenta: "#d77bff", cyan: "#4fd8e8", white: "#f4f5f7", gray: "#8b8f98", darkred: "#c0392b", darkyellow: "#c9971c", darkblue: "#3159c9", darkcyan: "#1f9aa8" };
const SCREEN_BG = "#0e1014", SCREEN_FG = "#d9dce3";
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
  return best === undefined ? null : game.lower ? best + "s" : String(best);
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
  if (char === "▀" || char === "▄") {
    const middle = Math.round(y + h / 2);
    context.fillStyle = color;
    context.fillRect(left, char === "▀" ? top : middle, right - left, char === "▀" ? middle - top : bottom - middle);
    return;
  }
  context.fillStyle = color;
  context.fillText(char, x + w / 2, y + h / 2 + 1);
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

const GAME_KEYS = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "enter", Escape: "esc" };
function gameKey(event) {
  if (state.view !== "games" || !arcade.session || event.metaKey || event.ctrlKey || event.altKey) return false;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return false;
  const key = GAME_KEYS[event.key] || (event.key.length === 1 ? event.key : null);
  if (!key) return false;
  event.preventDefault();
  sendGame([{ key }]);
  return true;
}

let resizeTimer = 0;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.view === "games") fitScreen(); }, 150); });
document.addEventListener("fullscreenchange", () => setTimeout(fitScreen, 60));

// ---- studio: recording, screenshots and the library through `ul capture` ----
const studio = { info: null, devices: null, status: { active: false }, statusAt: 0, library: [], filter: localStorage.getItem("studio-filter") || "all", mode: localStorage.getItem("studio-mode") || "screen", display: 1, mic: "", cam: "", system: null, clicks: null, format: "", delay: 0, clipboard: false, preview: localStorage.getItem("studio-preview") !== "off", previewBusy: false, previewTimer: 0, camStream: null, micStream: null, audio: null, saving: false, item: null, trim: { from: null, to: null }, starting: 0, shown: 0, levels: [], analyser: null, sampler: 0, wave: null };
const media = (path, name) => path + "?t=" + encodeURIComponent(TOKEN) + (name ? "&name=" + encodeURIComponent(name) : "");

async function loadStudioInfo() {
  const { status, data } = await api("GET", "/api/studio");
  if (status !== 200) return;
  studio.info = data;
  if (data.available) loadRecordStatus();
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
    else { toast("Saved " + data.saving_done.saved.split("/").pop()); loadLibrary(true); }
  }
  if (was.active && !data.active && !studio.saving) loadLibrary();
  if (!data.active) for (const item of studio.levels) item.live = false;
  drawRecording();
  if (state.view === "studio") {
    updateStudioControls();
    // Started or finished (maybe from the terminal): bring the preview back or pause it.
    if (Boolean(was.active) !== Boolean(data.active) && !studio.starting) renderMonitor();
  }
  if ((data.active || studio.saving) && !busyTimer) pollWhileBusy();
}

function recordElapsed() {
  const s = studio.status;
  if (studio.starting) return (Date.now() - studio.starting) / 1000;
  if (!s.active) return 0;
  const value = s.elapsed + (s.phase === "recording" ? (Date.now() - studio.statusAt) / 1000 : 0);
  // Polls arrive a little late; never let the clock step backwards while recording.
  if (s.phase === "recording") studio.shown = Math.max(studio.shown, value);
  else studio.shown = value;
  return studio.shown;
}

function drawRecording() {
  const s = studio.status, pill = $("recPill");
  const live = Boolean(studio.starting) || (s.active && s.phase === "recording");
  const active = s.active || studio.saving || Boolean(studio.starting);
  pill.className = "rec-pill" + (active ? " on" : "") + (s.paused ? " paused" : "");
  pill.textContent = studio.saving || s.phase === "saving" ? "Saving…" : active ? (s.paused ? "Paused " : "REC ") + clockText(recordElapsed()) : "";
  const clock = $("recClock");
  if (clock) {
    clock.textContent = clockText(recordElapsed());
    clock.classList.toggle("live", live);
  }
  const badge = $("monBadge");
  if (badge) {
    badge.className = "badge" + (active && !studio.saving ? " on" : "") + (s.paused ? " paused" : "");
    badge.textContent = s.paused ? "❚❚ PAUSED " + clockText(recordElapsed()) : "● REC " + clockText(recordElapsed());
  }
  const waveClock = $("waveClock");
  if (waveClock) waveClock.textContent = clockText(recordElapsed());
}

async function loadDevices() {
  const { status, data } = await api("GET", "/api/studio/devices");
  if (status !== 200) { toast(data.error || "Could not list devices"); return; }
  studio.devices = data;
  if (state.view === "studio") renderStudioControls();
}

async function loadLibrary(openNewest) {
  const { status, data } = await api("GET", "/api/studio/library");
  if (status !== 200) return;
  studio.library = data;
  if (state.view === "studio") renderLibrary();
  if (openNewest && data.length) openViewer(data[0]);
}

function leaveStudio() {
  clearTimeout(studio.previewTimer);
  stopStream("camStream");
  stopStream("micStream");
  closeViewer();
}

function stopStream(key) {
  const request = key === "camStream" ? "camRequest" : "micRequest";
  studio[request] = (studio[request] || 0) + 1;
  if (studio[key]) { studio[key].getTracks().forEach((track) => track.stop()); studio[key] = null; }
  if (key === "micStream") {
    clearInterval(studio.sampler);
    studio.analyser = null;
    if (studio.audio) { studio.audio.close(); studio.audio = null; }
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

// The live microphone: bars scroll left into a playhead, red for what is being recorded.
function drawWave() {
  const canvas = $("wave");
  if (!canvas) return;
  const [context, width, height] = fitCanvas(canvas);
  const step = 5, head = Math.round(width * (canvas.classList.contains("strip") ? 0.97 : 0.72));
  context.fillStyle = "rgba(255,255,255,.10)";
  context.fillRect(0, height / 2 - 0.5, width, 1);
  const shown = studio.levels.slice(-Math.floor(head / step));
  shown.forEach((item, index) => bars(context, head - (shown.length - index) * step, height, item.v, 3, item.live ? "#ff453a" : "#8e8e93"));
  const recording = Boolean(studio.starting || (studio.status.active && studio.status.phase === "recording"));
  context.fillStyle = recording ? "#ff453a" : "#6b93ff";
  context.fillRect(head, 4, 2, height - 8);
  context.beginPath();
  context.arc(head + 1, 5, 4, 0, Math.PI * 2);
  context.fill();
}

function renderStudio(main) {
  if (!studio.info) { main.textContent = ""; main.append(h("div", { class: "page" }, h("div", { class: "empty", text: "Loading…" }))); loadStudioInfo().then(() => state.view === "studio" && render()); return; }
  if (!studio.info.available) {
    main.textContent = "";
    main.append(h("div", { class: "page" }, h("h3", { text: "Studio" }), h("div", { class: "empty", text: "The capture command is not installed in this ul. Turn on the `capture` feature with: ul features" })));
    return;
  }
  if (main.querySelector(".studio")) return;
  main.textContent = "";
  const monitor = h("div", { class: "monitor", id: "monitor" }, h("span", { class: "badge", id: "monBadge" }));
  const bar = h("div", { class: "monbar" },
    h("button", { id: "togglePreview", onclick: () => { studio.preview = !studio.preview; localStorage.setItem("studio-preview", studio.preview ? "on" : "off"); renderMonitor(); } }),
    h("button", { id: "toggleCam", onclick: toggleCamera }),
    h("button", { id: "toggleMic", onclick: toggleMeter }),
    h("span", { class: "hint", id: "monHint" }),
    h("button", { class: "ghost", text: "Devices ↻", title: "Look for cameras and microphones again", onclick: loadDevices }));
  const filters = h("div", { class: "levels", id: "libFilters" }, [["all", "All"], ["video", "Video"], ["audio", "Audio"], ["image", "Screenshots"]].map(([value, label]) =>
    h("button", { "data-filter": value, text: label, onclick: () => { studio.filter = value; localStorage.setItem("studio-filter", value); renderLibrary(); } })));
  const stage = h("section", {}, monitor, bar,
    h("div", { class: "libhead" }, h("h3", { text: "Library" }), filters, h("span", { class: "spacer" }), h("button", { class: "ghost", text: "Refresh", onclick: () => loadLibrary() })),
    h("div", { class: "library", id: "library" }));
  main.append(h("div", { class: "studio" }, h("aside", { class: "controls", id: "studioControls" }), stage));
  const settings = studio.info.settings;
  if (studio.system === null) studio.system = settings.system_audio;
  if (studio.clicks === null) studio.clicks = settings.show_clicks;
  renderStudioControls();
  renderLibrary();
  renderMonitor();
  if (!studio.devices) loadDevices();
  loadLibrary();
  loadRecordStatus();
}

function field(label, control) { return h("label", {}, label, control); }
function check(label, value, onchange) {
  const input = h("input", { type: "checkbox" });
  input.checked = value;
  input.addEventListener("change", () => onchange(input.checked));
  return h("label", { class: "check" }, input, label);
}
function select(options, value, onchange) {
  const node = h("select", {}, options.map(([v, label]) => h("option", { value: v, text: label, selected: v === value })));
  node.addEventListener("change", () => onchange(node.value));
  return node;
}

function renderStudioControls() {
  const box = $("studioControls");
  if (!box) return;
  box.textContent = "";
  const settings = studio.info.settings, devices = studio.devices;
  const screenMode = studio.mode === "screen" || studio.mode === "screen-camera";
  const cameraMode = studio.mode === "camera" || studio.mode === "screen-camera";
  box.append(h("h4", { text: "Record" }), h("div", { class: "levels modes" }, [["screen", "Screen"], ["screen-camera", "Screen + Cam"], ["camera", "Camera"], ["audio", "Audio"]].map(([value, label]) =>
    h("button", { class: value === studio.mode ? "on" : "", text: label, disabled: studio.status.active, onclick: () => { studio.mode = value; studio.format = ""; localStorage.setItem("studio-mode", value); renderStudioControls(); renderMonitor(); } }))));
  if (screenMode) {
    const displays = devices ? devices.displays.map((item) => [String(item.number), item.number + " · " + item.name]) : [["1", "1 · Main display"]];
    box.append(field("Display", select(displays, String(studio.display), (value) => { studio.display = Number(value); renderMonitor(); })));
  }
  if (cameraMode) {
    const cams = [["", "Default (" + settings.camera_device + ")"], ...(devices ? devices.cameras.map((name) => [name, name]) : [])];
    box.append(field("Camera", select(cams, studio.cam, (value) => { studio.cam = value; if (studio.camStream) { stopStream("camStream"); toggleCamera(); } })));
  }
  const mics = [["", "Default (" + settings.audio_device + ")"], ...(devices ? devices.microphones.map((item) => [item.name, item.name + (item.virtual ? " (virtual)" : "")]) : []), ...(studio.mode === "audio" ? [] : [["none", "No microphone"]])];
  box.append(field("Microphone", select(mics, studio.mic, (value) => { studio.mic = value; const chosen = devices?.microphones.find((item) => item.name === value); if (chosen?.virtual) toast(value + " is virtual: it carries app audio, not your voice"); })));
  if (screenMode) {
    box.append(check("System audio (sound of the Mac)", studio.system, (value) => { studio.system = value; }));
    box.append(check("Show clicks", studio.clicks, (value) => { studio.clicks = value; }));
  }
  const formats = studio.mode === "audio" ? [["", "Default (" + settings.audio_format + ")"], ["m4a", "M4A"], ["mp3", "MP3"], ["wav", "WAV"]] : [["", "Default (" + settings.video_format + ")"], ["mov", "MOV"], ["mp4", "MP4"]];
  box.append(field("Format", select(formats, studio.format, (value) => { studio.format = value; })));
  box.append(h("div", { class: "recbox" },
    h("button", { class: "recbtn" + (studio.status.active ? " on" : ""), id: "recButton", title: "Start / stop recording (r)", onclick: toggleRecord }, h("i")),
    h("span", { class: "recclock", id: "recClock", text: "00:00" }),
    h("div", { class: "row" },
      h("button", { id: "recPause", text: studio.status.paused ? "Resume" : "Pause", disabled: !studio.status.active || studio.saving, onclick: pauseRecord, title: "Pause / resume (p)" })),
    h("div", { class: "recstate", id: "recState" })));
  box.append(h("h4", { text: "Screenshot" }), h("div", { class: "row" },
    ["screen", "area", "window"].map((kind) => h("button", { text: kind[0].toUpperCase() + kind.slice(1), title: kind === "screen" ? "The whole display" : "Select on the Mac with the mouse", onclick: () => takeShot(kind) }))));
  box.append(field("Delay", select([["0", "No delay"], ["3", "3 s"], ["5", "5 s"], ["10", "10 s"]], String(studio.delay), (value) => { studio.delay = Number(value); })));
  box.append(check("Copy to the clipboard instead of saving", studio.clipboard, (value) => { studio.clipboard = value; }));
  updateStudioControls();
}

function updateStudioControls() {
  const s = studio.status;
  const button = $("recButton");
  if (!button) return;
  const active = Boolean(s.active || studio.starting);
  button.classList.toggle("on", active);
  $("recPause").disabled = !s.active || studio.saving || s.phase === "saving" || Boolean(studio.starting);
  $("recPause").textContent = s.paused ? "Resume" : "Pause";
  const what = s.active ? (s.camera ? "screen + camera" : s.mode) : "";
  $("recState").textContent = studio.starting ? "Starting…" : studio.saving || s.phase === "saving" ? "Saving… (adding camera and microphone)" : s.phase === "interrupted" ? "Stopped unexpectedly — press stop to save" : s.phase === "unsaved" ? "Not saved — press stop to try again" : s.active ? (s.paused ? "Paused · " : "Recording ") + what : "Ready";
  for (const node of document.querySelectorAll(".modes button")) node.disabled = active;
  drawRecording();
}

async function toggleRecord() {
  if (studio.saving || studio.starting) return;
  if (studio.status.active) {
    studio.saving = true;
    for (const item of studio.levels) item.live = false;
    updateStudioControls();
    const { status, data } = await api("POST", "/api/studio/stop", {});
    if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
    pollWhileBusy();
    return;
  }
  const body = { mode: studio.mode, display: studio.display };
  if (studio.mic) body.mic = studio.mic;
  if (studio.cam && (studio.mode === "camera" || studio.mode === "screen-camera")) body.cam = studio.cam;
  if (studio.mode === "screen" || studio.mode === "screen-camera") { body.system_audio = studio.system; body.clicks = studio.clicks; }
  if (studio.format) body.format = studio.format;
  // The page's own camera preview would hold the camera; let ffmpeg have it.
  if (studio.mode !== "screen") stopStream("camStream");
  // Show the recording at once: the recorders start in well under a second,
  // and the server's clock replaces this one when it answers.
  studio.starting = Date.now();
  studio.shown = 0;
  studio.levels = [];
  updateStudioControls();
  if (studio.mode === "audio" && !studio.micStream && studio.mic !== "none") toggleMeter();
  renderMonitor();
  const { status, data } = await api("POST", "/api/studio/record", body);
  studio.starting = 0;
  if (status !== 200) { toast(data.error || "Could not start recording"); await loadRecordStatus(); renderMonitor(); return; }
  for (const warning of data.warnings || []) toast(warning);
  studio.status = data;
  studio.statusAt = Date.now();
  updateStudioControls();
  renderMonitor();
  pollWhileBusy();
}

async function pauseRecord() {
  if (!studio.status.active || studio.saving) return;
  const { status, data } = await api("POST", studio.status.paused ? "/api/studio/resume" : "/api/studio/pause", {});
  if (status !== 200) { toast(data.error || "Could not pause"); return; }
  studio.status = data;
  studio.statusAt = Date.now();
  updateStudioControls();
}

let busyTimer = 0;
function pollWhileBusy() {
  clearTimeout(busyTimer);
  busyTimer = setTimeout(async () => {
    busyTimer = 0;
    await loadRecordStatus();
    if ((studio.status.active || studio.saving) && !busyTimer) pollWhileBusy();
    else updateStudioControls();
  }, studio.saving ? 700 : 1500);
}

async function takeShot(kind) {
  const body = { kind, display: studio.display, delay: studio.delay, clipboard: studio.clipboard };
  if (kind !== "screen") toast("Select on the Mac: drag an area or click a window (Esc cancels)");
  else if (studio.delay) toast("Screenshot in " + studio.delay + " s");
  const { status, data } = await api("POST", "/api/studio/shot", body);
  if (status !== 200) { toast(data.error || "Screenshot failed"); return; }
  if (data.clipboard) { toast("Copied to the clipboard"); return; }
  toast("Saved " + data.saved.split("/").pop());
  loadLibrary(false);
}

function renderMonitor() {
  const monitor = $("monitor");
  if (!monitor) return;
  clearTimeout(studio.previewTimer);
  for (const node of [...monitor.children]) if (node.id !== "monBadge") node.remove();
  const screenMode = studio.mode === "screen" || studio.mode === "screen-camera";
  const cameraMode = studio.mode === "camera" || studio.mode === "screen-camera";
  const recording = Boolean(studio.status.active || studio.starting);
  $("togglePreview").textContent = "Screen preview: " + (studio.preview ? "on" : "off");
  $("togglePreview").style.display = screenMode ? "" : "none";
  $("toggleCam").textContent = studio.camStream ? "Hide camera" : "Show camera";
  $("toggleCam").style.display = cameraMode && !recording ? "" : "none";
  $("toggleMic").textContent = studio.micStream ? "Hide sound" : "Show sound";
  $("monHint").textContent = recording && screenMode ? "Preview paused while recording, so the recording stays smooth." : screenMode ? "The preview refreshes every 2 s; the recording itself is smooth." : studio.mode === "audio" ? "The wave shows how loud the microphone is." : "The camera preview uses the browser; it is released when recording starts.";
  if (screenMode && studio.preview) {
    // A full-screen snapshot every 2 s would compete with the recorder, so it stops while recording.
    const image = h("img", { class: "screen", alt: "" });
    image.addEventListener("error", () => { image.remove(); monitor.prepend(h("div", { class: "note", text: "No preview: give the terminal running ul desk Screen Recording permission (System Settings > Privacy & Security)." })); });
    image.addEventListener("load", () => { if (!studio.status.active && !studio.starting) studio.previewTimer = setTimeout(refresh, 2000); });
    const refresh = () => {
      if (!image.isConnected) return;
      if (state.view === "studio" && !document.hidden && !studio.status.active && !studio.starting) image.src = media("/media/preview") + "&display=" + studio.display + "&_=" + Date.now();
      else studio.previewTimer = setTimeout(refresh, 2000);
    };
    if (recording) image.style.opacity = ".35";
    monitor.append(image);
    if (studio.lastPreview && recording) image.src = studio.lastPreview;
    else refresh();
    image.addEventListener("load", () => { if (!recording) studio.lastPreview = image.src; });
  } else if (screenMode) {
    monitor.append(h("div", { class: "note", text: "Display " + studio.display + " · preview off" }));
  }
  if (cameraMode && studio.camStream && !recording) {
    const video = h("video", { class: "cam " + (studio.mode === "camera" ? "full" : studio.info.settings.overlay), autoplay: true, muted: true, playsinline: true });
    video.muted = true;
    video.srcObject = studio.camStream;
    monitor.append(video);
  } else if (studio.mode === "camera") {
    monitor.append(h("div", { class: "note", text: recording ? "Recording the camera" : "Camera · press “Show camera” for a preview" }));
  }
  if (studio.mode === "audio") {
    monitor.append(h("div", { class: "voice" },
      h("div", { class: "voice-clock", id: "waveClock", text: clockText(recordElapsed()) }),
      h("canvas", { id: "wave", class: "wave" }),
      studio.micStream ? null : h("div", { class: "note", text: "Press “Show sound” (or start recording) to see the microphone" })));
  } else if (studio.micStream) {
    monitor.append(h("canvas", { id: "wave", class: "wave strip" }));
  }
  drawWave();
}

async function toggleCamera() {
  if (studio.camStream) { stopStream("camStream"); renderMonitor(); return; }
  if (state.view !== "studio" || studio.status.active || studio.starting) return;
  const request = studio.camRequest = (studio.camRequest || 0) + 1;
  const current = () => request === studio.camRequest && state.view === "studio" && !studio.status.active && !studio.starting;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    if (studio.cam) {
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "videoinput" && item.label === studio.cam);
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      if (found) { stream.getTracks().forEach((track) => track.stop()); stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: found.deviceId } } }); }
    }
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.camStream = stream;
  } catch (error) { if (stream) stream.getTracks().forEach((track) => track.stop()); toast("The browser could not open the camera: " + error.message); }
  renderMonitor();
}

async function toggleMeter() {
  if (studio.micStream) { stopStream("micStream"); renderMonitor(); return; }
  if (state.view !== "studio") return;
  const request = studio.micRequest = (studio.micRequest || 0) + 1;
  const current = () => request === studio.micRequest && state.view === "studio";
  try {
    const constraints = { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } };
    if (studio.mic && studio.mic !== "none") {
      // Device labels are only visible after the first permission.
      await navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => stream.getTracks().forEach((track) => track.stop()));
      if (!current()) return;
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "audioinput" && item.label.includes(studio.mic));
      if (!current()) return;
      if (found) constraints.audio.deviceId = { exact: found.deviceId };
    }
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.micStream = stream;
  } catch (error) { toast("The browser could not open the microphone: " + error.message); return; }
  studio.audio = new AudioContext();
  studio.analyser = studio.audio.createAnalyser();
  studio.analyser.fftSize = 2048;
  studio.audio.createMediaStreamSource(studio.micStream).connect(studio.analyser);
  const samples = new Float32Array(studio.analyser.fftSize);
  // Like Voice Memos: one bar per 50 ms, louder = taller, red while recording.
  studio.sampler = setInterval(() => {
    if (!studio.analyser) return;
    studio.analyser.getFloatTimeDomainData(samples);
    let sum = 0, peak = 0;
    for (const value of samples) { sum += value * value; peak = Math.max(peak, Math.abs(value)); }
    const rms = Math.sqrt(sum / samples.length);
    const db = 20 * Math.log10(Math.max(rms * 1.4, peak * 0.6, 1e-5));
    const level = Math.min(1, Math.max(0, (db + 55) / 55)) ** 1.3;
    const s = studio.status;
    studio.levels.push({ v: level, live: Boolean(studio.starting || (s.active && s.phase === "recording")) });
    if (studio.levels.length > 2400) studio.levels.splice(0, 600);
  }, 50);
  renderMonitor();
  const stream = studio.micStream;
  const loop = () => { if (studio.micStream !== stream) return; drawWave(); requestAnimationFrame(loop); };
  loop();
}

const ICONS = { audio: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" };
function sizeText(bytes) { return bytes > 1e9 ? (bytes / 1e9).toFixed(1) + " GB" : bytes > 1e6 ? (bytes / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1e3)) + " KB"; }

function renderLibrary() {
  const box = $("library");
  if (!box) return;
  for (const button of $("libFilters").children) button.classList.toggle("on", button.dataset.filter === studio.filter);
  box.textContent = "";
  const items = studio.library.filter((item) => studio.filter === "all" || item.kind === studio.filter);
  if (!items.length) { box.append(h("div", { class: "empty", text: studio.library.length ? "Nothing of this kind yet." : "No captures yet. Take a screenshot or start a recording." })); return; }
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
    const convert = select((item.kind === "video" ? [["mp4", "MP4"], ["mov", "MOV"], ["gif", "GIF"], ["m4a", "Audio M4A"], ["mp3", "Audio MP3"]] : [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"]]).filter(([value]) => !item.name.toLowerCase().endsWith("." + value)), "", () => {});
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
  const bars_ = Math.max(60, Math.min(1200, Math.floor((canvas.clientWidth || 900) / 4)));
  const { status, data } = await api("GET", "/api/studio/wave?name=" + encodeURIComponent(item.name) + "&bars=" + bars_);
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
$("recPill").addEventListener("click", () => setView("studio"));

// ---- boards ----
const REMINDERS = "reminders:";
const NEW_BOARD = "::new";
let boardsDir = "";

function boardOption(path, current) {
  return h("option", { value: path, text: path.split("/").pop().replace(/\.md$/i, "") + "  —  " + path.split("/").slice(-2, -1)[0], selected: path === current });
}

async function loadBoards() {
  const { status, data } = await api("GET", "/api/boards");
  if (status !== 200) return;
  const select = $("boards");
  select.textContent = "";
  boardsDir = data.boards_dir || "";
  if (data.reminders) {
    select.append(h("optgroup", { label: "Apple Reminders" },
      h("option", { value: REMINDERS, text: "Reminders  —  lists as columns", selected: data.current === REMINDERS })));
  }
  const recent = data.recent.length || data.current === REMINDERS ? data.recent : [data.current];
  if (recent.length) select.append(h("optgroup", { label: "Recent" }, recent.map((path) => boardOption(path, data.current))));
  const own = (data.boards || []).filter((path) => !recent.includes(path));
  if (own.length) select.append(h("optgroup", { label: "Boards folder" }, own.map((path) => boardOption(path, data.current))));
  select.append(h("option", { value: NEW_BOARD, text: "New board…" }));
  select.append(h("option", { value: "", text: "Open another board…" }));
}

async function switchBoard(path, create) {
  const { status, data } = await api("POST", "/api/boards", { path, create: Boolean(create) });
  if (status === 200) { state.tag = ""; setBoard(data); loadBoards(); toast("Opened " + data.name); return; }
  if (status === 404 && data.missing && !create && (/\.md$/i.test(path) || !path.includes("/")) && confirm("No board at\n" + path + "\n\nCreate a new board there?")) return switchBoard(path, true);
  toast(data.error || "Could not open that board");
  loadBoards();
}

$("boards").addEventListener("change", (event) => {
  const value = event.target.value;
  if (value === NEW_BOARD) {
    const name = prompt("Name of the new board. It is saved in\n" + boardsDir + "\n(desk.boards_dir; a full path to a .md file works too)", "");
    if (name && name.trim()) switchBoard(name.trim(), true);
    else loadBoards();
    return;
  }
  if (value) { switchBoard(value); return; }
  const path = prompt("Path to a Kanban board (.md), or the name of a board in " + boardsDir + ". A missing file can be created.", "~/");
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
  if (state.board && !["stats", "games", "studio"].includes(state.view)) render();
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
  if (gameKey(event)) return;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (event.key === "Escape") {
    $("help").classList.remove("on");
    closeViewer();
    if (typing) document.activeElement.blur();
    if (state.query || state.tag) { state.query = ""; state.tag = ""; $("search").value = ""; render(); }
    return;
  }
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "?") { $("help").classList.toggle("on"); return; }
  if (event.key === "/") { event.preventDefault(); if (state.view === "games" || state.view === "stats") setView("board"); $("search").focus(); }
  else if (event.key === "n") {
    event.preventDefault();
    if (state.view === "today") document.querySelector(".quick input")?.focus();
    else { if (state.view !== "board") setView("board"); document.querySelector(".add input")?.focus(); }
  }
  else if (event.key === " ") { event.preventDefault(); togglePlay(); }
  else if (event.key >= "1" && event.key <= "5") setView(VIEWS[Number(event.key) - 1]);
  else if (state.view === "studio" && event.key === "r") toggleRecord();
  else if (state.view === "studio" && event.key === "p") pauseRecord();
});

// ---- start ----
async function start() {
  if (!TOKEN) { document.body.textContent = "Open the desk with `ul desk`: this page needs its token."; return; }
  await Promise.all([loadBoard(true), loadBoards(), loadTimer(), loadGames(), loadStudioInfo()]);
  render();
  setInterval(() => { if (!document.hidden && !state.dragging && !state.editing && !["games", "studio"].includes(state.view)) loadBoard(false); }, 2000);
  setInterval(() => { if (!document.hidden) loadTimer(); }, 10000);
  setInterval(() => { if (!document.hidden && state.view === "games" && arcade.session) loadGames(); }, 5000);
  setInterval(drawTimer, 500);
  setInterval(drawRecording, 250);
  setInterval(() => { if (!document.hidden && studio.info?.available) return loadRecordStatus(); }, 8000);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (state.view === "games") pauseGame(); return; }
    loadBoard(false);
    loadTimer();
  });
}
start();
</script>
</body>
</html>
"""

import fcntl
import hmac
import json
import math
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
    "Usage: ul desk [board.md|name] [--reminders] [--port N] [--no-open] | new <board.md|name> | path [board.md] | "
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
MAX_CANVAS_BODY = 16 * 1024 * 1024
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


class CanvasConflict(Exception):
    """The canvas file changed since the client read it."""


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
        self.canvas_current: Path | None = None
        self.canvas_lock = threading.Lock()
        self.pomodoro = Pomodoro(directory, self.settings, clock)
        self.lock = threading.Lock()
        self.today: Callable[[], date] = lambda: datetime.now().astimezone().date()

    @property
    def completed_column(self) -> str:
        return str(self.config.get("todo", {}).get("completed_column", "Completed"))

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
            "items": [{"path": path, "name": Path(path).stem} for path in dict.fromkeys([*files, *self.canvas_recent()])],
        }

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

    def switch(self, raw: object, create: bool) -> dict:
        text = _clean_text(raw)
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


def board_file(raw: str, create: bool = False, boards_dir: Path | None = None) -> Path:
    """A board chosen by the user: an existing .md file, or a new one from the template.

    A bare name (no folder, no .md) is a board in desk.boards_dir, created with the folder when needed.
    """
    if boards_dir is not None and _bare_name(raw):
        if create:
            boards_dir.mkdir(parents=True, exist_ok=True)
        raw = str(boards_dir / f"{raw}.md")
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


def default_board(config: dict) -> Path:
    path = configured_board(config["todo"])
    if not path.is_file():
        raise FileNotFoundError(
            f"Kanban file not found: {path} (set todo.vault_path and todo.file, or pass a board.md)"
        )
    return path


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
        if length > limit:
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
            elif url.path.startswith("/media/"):
                self._media(url)
            else:
                self._json(404, {"error": "not found"})
        except StudioError as error:
            self._json(400, {"error": str(error)})
        except FileNotFoundError as error:
            self._json(404, {"error": str(error)})
        except (OSError, ValueError) as error:
            self._json(500, {"error": str(error)})

    def _media(self, url: urllib.parse.SplitResult) -> None:
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/media/file":
            path = self.studio.member(query.get("name", [""])[0])
        elif url.path == "/media/thumb":
            name = self.studio.member(query.get("name", [""])[0]).name
            data = self.studio.run("thumb", name, timeout=60)
            path = Path(str(data.get("thumbnail") if isinstance(data, dict) else ""))
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

    def _send_file(self, path: Path) -> None:
        """Serve a file with byte ranges, which video seeking needs."""
        kind = MEDIA_TYPES.get(path.suffix.casefold())
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
        path = urllib.parse.urlsplit(self.path).path
        try:
            body = self._body(MAX_CANVAS_BODY if path == "/api/canvas" else MAX_BODY)
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
                self._json(200, self.studio.stop())
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
        except LookupError as error:
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
        except (ValueError, TypeError, KeyError) as error:
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
        # Raw reads: a buffered readline could hold frames that select() cannot see.
        source = process.stdout.fileno()
        try:
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


CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; base-uri 'none'; form-action 'none'"


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
}
STUDIO_MODES = ("screen", "screen-camera", "camera", "audio")
STUDIO_FORMATS = ("mov", "mp4", "m4a", "mp3", "wav")


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

    def run(self, *args: str, timeout: float = 60) -> object:
        if not self.available():
            raise StudioError("the capture command is not installed (ul features)")
        try:
            with subprocess.Popen(
                [self.binary or "ul", "capture", *args, "--json"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            ) as process:
                try:
                    stdout, stderr_text = process.communicate(timeout=timeout)
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
        return data

    def record(self, body: dict) -> object:
        mode = body.get("mode")
        if mode not in STUDIO_MODES:
            raise ValueError("mode must be screen, screen-camera, camera or audio")
        args = ["record", "screen" if mode == "screen-camera" else str(mode)]
        if mode == "screen-camera":
            args.append("--camera")
        for key, flag in (("mic", "--mic"), ("cam", "--cam")):
            value = body.get(key)
            if value is not None:
                if not isinstance(value, str) or not value.strip() or len(value) > 200 or value.startswith("-"):
                    raise ValueError(f"{key} must be a device name")
                args += [flag, value]
        display = body.get("display", 1)
        if isinstance(display, bool) or not isinstance(display, int) or not 1 <= display <= 16:
            raise ValueError("display must be a number from 1")
        if mode in {"screen", "screen-camera"}:
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

    def stop(self) -> dict:
        """Saving can take minutes (camera overlay), so it runs in the background."""
        with self.lock:
            if self.saving and self.saving.is_alive():
                return {"saving": True}
            self.last = None

            def work() -> None:
                try:
                    self.last = self.run("stop", timeout=3600)  # type: ignore[assignment]
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
    def member(name: object) -> Path:
        """A file directly inside the capture folders; nothing else is ever served or changed."""
        if not isinstance(name, str) or not name or "/" in name or name.startswith("."):
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
}
LEVELS = ("easy", "normal", "hard")
GAME_KEYS = {"up", "down", "left", "right", "enter", "esc"}
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

    key = event.get("key")
    if isinstance(key, str):
        if key in GAME_KEYS or (len(key) == 1 and key.isprintable()):
            return {"key": key}
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
            games.append({"name": name, "label": label, "lower": name == "minesweeper", "best": best})
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
            raise LookupError("this game has ended")
        if self.process is None:
            raise LookupError("this game has ended")
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
                raise LookupError("this game has ended") from error

    def claim(self, session: object) -> subprocess.Popen:
        """The process whose frames one stream may read; a second reader is refused."""
        with self.lock:
            process = self._current(session)
            if self.reading:
                raise LookupError("this game is already shown in another tab")
            self.reading = True
            return process

    def stop(self, session: object = None) -> None:
        with self.lock:
            if session is not None:
                try:
                    self._current(session)
                except LookupError:
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
    server = make_server(
        desk, settings["port"] if port is None else port, token, exact=port is not None
    )
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
        stop.set()
        server.RequestHandlerClass.arcade.stop()
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
        boards_dir = boards_folder(desk_settings(config)["boards_dir"], config_dir())
        if action == "new" and len(args) == 2:
            wanted = boards_dir / f"{args[1]}.md" if _bare_name(args[1]) else Path(args[1]).expanduser()
            if wanted.exists():
                raise ValueError(f"{wanted} already exists; open it with: ul desk {args[1]}")
            path = board_file(args[1], create=True, boards_dir=boards_dir)
            print(f"Board: {path}")
            return 0
        if action == "path" and len(args) <= 2:
            print(board_file(args[1], boards_dir=boards_dir) if len(args) == 2 else default_board(config))
            return 0
        if action == "stats" and len(args) <= 2:
            return _stats_cli(
                board_file(args[1], boards_dir=boards_dir) if len(args) == 2 else default_board(config), config
            )
        if action in {"new", "path", "stats"}:
            print(USAGE, file=sys.stderr)
            return 2
        board, port, open_browser, reminders = _parse_serve(args)
        if reminders:
            if not reminders_available(desk_settings(config)["reminders"]):
                raise ValueError("The Reminders layer is off (desk.reminders) or not on macOS")
            path = board_file(board, boards_dir=boards_dir) if board else _optional_board(config)
            return serve(path, config, port, open_browser, REMINDERS)
        path = board_file(board, boards_dir=boards_dir) if board else default_board(config)
        return serve(path, config, port, open_browser)
    except (ConfigError, FileNotFoundError, OSError, ValueError) as error:
        print(f"unlaw desk: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
