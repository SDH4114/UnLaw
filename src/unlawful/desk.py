from __future__ import annotations

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

from unlawful.command_help import COMMAND_HELP

from .canvas import NEW_CANVAS, read_canvas, render_canvas, write_canvas
from .config import ConfigError, config_dir, load_config, storage_path
from .desk_ui import PAGE
from .kanban import (
    DONE_COLUMNS,
    NEW_BOARD,
    KanbanBoard,
    Section,
    card,
    complete_task,
    completed_section,
    configured_board,
    quick_text,
    reopen_task,
    version_of,
    write_board,
)
from .reminders import REMINDERS, Reminders, boards_folder, reminders_available

USAGE = (
    "Usage: ul desk [board] [--reminders] [--port N] [--no-open] | list [--json] | "
    "show [board] [--reminders] [--json] | add <text> [--column C] [-b board] | "
    "move <n> <column> [-b board] | done <n> [-b board] | new <name> | path [board] | stats [board] | "
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
CHOOSE_TIMEOUT = 600
MAX_CANVAS_NUMBER = 10000


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
        self.choose_lock = threading.Lock()
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
                    try:  # a hard link fails when the name was taken meanwhile, so nothing is overwritten
                        os.link(path, target)
                    except FileExistsError as error:
                        raise ValueError(f"A canvas named {clean} already exists") from error
                    os.unlink(path)
            version, canvas = read_canvas(target)
            self._canvas_shown(target)
        return self._canvas_json(target, version, canvas)

    def canvas_choose(self) -> dict:
        """Ask for a .canvas file in the macOS open dialog: {"path": None} when cancelled,
        {"unavailable": True} without osascript (the page then asks for a path)."""
        osascript = shutil.which("osascript")
        if osascript is None:
            return {"unavailable": True}
        if not self.choose_lock.acquire(blocking=False):
            raise ValueError("The file dialog is already open")
        try:
            start = self.canvas_dir if self.canvas_dir.is_dir() else Path.home()
            command = [osascript]
            for line in CHOOSE_CANVAS_SCRIPT:
                command += ["-e", line]
            try:
                result = subprocess.run(
                    [*command, str(start)], capture_output=True, text=True, timeout=CHOOSE_TIMEOUT, check=False
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
            elif path == "/api/canvas/new":
                self._json(200, self.desk.canvas_new())
            elif path == "/api/canvas/rename":
                self._json(200, self.desk.canvas_rename(body.get("path"), body.get("name")))
            elif path == "/api/canvas/choose":
                self._json(200, self.desk.canvas_choose())
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


def _board_choice(args: list[str]) -> tuple[str | None, list[str]]:
    """`--board NAME` (or `-b`) anywhere in args; the rest stays in order."""
    rest, board = [], None
    position = 0
    while position < len(args):
        arg = args[position]
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
    """add / move / done on a .md board, the same edits the page makes."""
    raw, rest = _board_choice(args)
    path = _chosen_board(raw, config, boards_dir)
    board = KanbanBoard.parse(path.read_bytes().decode("utf-8"))
    if action == "add":
        column: str | None = None
        if "--column" in rest:
            at = rest.index("--column")
            if at + 1 >= len(rest):
                raise ValueError("--column needs a column name")
            column = rest[at + 1]
            rest = rest[:at] + rest[at + 2 :]
        text = quick_text(" ".join(rest), datetime.now().astimezone().date())
        if not text or "\n" in text or "\r" in text:
            raise ValueError("The task text must be one non-empty line")
        if not board.sections:
            raise ValueError(f"{path} has no columns")
        section = board.section(column) if column else board.sections[0]
        section.tasks.append([f"- [ ] {text}"])
        write_board(path, board)
        print(f"Added to {section.name}: {text}")
        return 0
    if not rest or not rest[0].isdigit():
        raise ValueError(f"{action} needs a card number from: ul desk show")
    number = int(rest[0])
    if action == "move":
        if len(rest) < 2:
            raise ValueError("move needs a card number and a column")
        target = board.section(" ".join(rest[1:]))
        source, task = board.pop_task(number)
        target.tasks.append(task)
        write_board(path, board)
        print(f"Moved #{number}: {source.name} -> {target.name}")
        return 0
    if len(rest) != 1:
        raise ValueError("done takes one card number")
    target = completed_section(board, str(config.get("todo", {}).get("completed_column", "Completed")))
    _, task = board.pop_task(number)
    title = complete_task(task, datetime.now().astimezone().date())
    target.tasks.append(task)
    write_board(path, board)
    print(f"Completed #{number}: {title}")
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
        print(COMMAND_HELP["desk"], end="")
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
        if action == "show":
            return _show_cli(args[1:], config, boards_dir)
        if action == "list":
            return _list_cli(args[1:], config, boards_dir)
        if action in {"add", "move", "done"}:
            return _change_cli(action, args[1:], config, boards_dir)
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
