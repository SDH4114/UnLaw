"""Apple Reminders as a Kanban layer for `ul desk`: every list is a column, every open reminder a card.

Seeded into the desk command's source. It talks to EventKit through `osascript -l JavaScript`
(stdlib only): the Reminders app's Apple Events take 10-20 s on a list with hundreds of finished
reminders, EventKit answers in a fraction of a second.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .kanban import KanbanBoard, Section, version_of

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
