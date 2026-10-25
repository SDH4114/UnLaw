from __future__ import annotations

import codecs
import os
import re
import select
import shutil
import signal
import sys
import termios
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

BOLD, DIM, ITALIC, RED, GREEN, YELLOW, CYAN = 1, 2, 3, 31, 32, 33, 36
PLACEHOLDER = "Ask anything · / commands · @ files · ! shell"
MENU_ROWS = 8


class Paint:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, *codes: int) -> str:
        if not self.enabled or not codes:
            return text
        return f"\x1b[{';'.join(map(str, codes))}m{text}\x1b[0m"


def cells(text: str) -> int:
    """Terminal columns a plain string takes: wide CJK/emoji count twice, accents not at all."""
    width = 0
    for character in text:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in "WF" else 1
    return width


def fit(text: str, room: int) -> str:
    """Cut plain text to `room` columns, marking the cut with …."""
    if cells(text) <= room:
        return text
    out, used = "", 0
    for character in text:
        width = cells(character)
        if used + width > room - 1:
            break
        out, used = out + character, used + width
    return out + "…"


@dataclass
class Item:
    """One row of the / or @ menu."""

    label: str
    description: str
    insert: str
    submit: bool = False


# --- Keys --------------------------------------------------------------------

CSI = {
    ("", "A"): "up", ("", "B"): "down", ("", "C"): "right", ("", "D"): "left",
    ("", "H"): "home", ("", "F"): "end", ("", "Z"): "shift-tab",
    ("1", "~"): "home", ("7", "~"): "home", ("4", "~"): "end", ("8", "~"): "end", ("3", "~"): "delete",
    ("1;3", "D"): "word-left", ("1;5", "D"): "word-left", ("1;9", "D"): "word-left",
    ("1;3", "C"): "word-right", ("1;5", "C"): "word-right", ("1;9", "C"): "word-right",
    ("1;2", "A"): "up", ("1;2", "B"): "down",
    # Shift+Enter in terminals that report it (kitty keyboard protocol, xterm modifyOtherKeys).
    ("13;2", "u"): "newline", ("27;2;13", "~"): "newline",
}  # fmt: skip
ALT = {
    "\r": "newline",
    "\n": "newline",
    "b": "word-left",
    "f": "word-right",
    "\x7f": "word-backspace",
    "d": "word-delete",
}
CONTROL_KEYS = {
    "\r": "enter", "\n": "newline", "\t": "tab", "\x7f": "backspace", "\x08": "backspace",
    "\x01": "home", "\x05": "end", "\x02": "left", "\x06": "right", "\x10": "up", "\x0e": "down",
    "\x15": "kill-start", "\x0b": "kill-end", "\x17": "word-backspace",
    "\x03": "ctrl-c", "\x04": "ctrl-d", "\x0c": "redraw",
}  # fmt: skip


class Keyboard:
    """Raw keys from a TTY: escape sequences, Alt combinations and bracketed paste become names."""

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.buffer = ""

    def _fill(self, timeout: float | None) -> bool:
        if not select.select([self.fd], [], [], timeout)[0]:
            return False
        data = os.read(self.fd, 4096)
        if not data:
            raise EOFError
        self.buffer += self.decoder.decode(data)
        return True

    def read(self, timeout: float | None = None) -> tuple[str, str] | None:
        """("key", name), ("text", characters) or ("paste", text); None if nothing came in time."""
        if not self.buffer and not self._fill(timeout):
            return None
        if self.buffer.startswith("\x1b[200~"):
            while "\x1b[201~" not in self.buffer:
                self._fill(None)
            end = self.buffer.index("\x1b[201~")
            text, self.buffer = self.buffer[6:end], self.buffer[end + 6 :]
            return "paste", text.replace("\r\n", "\n").replace("\r", "\n")
        if self.buffer[0] == "\x1b":
            # A lone Esc is only Esc if nothing follows quickly; otherwise it starts a sequence.
            if len(self.buffer) == 1 and not self._fill(0.03):
                self.buffer = ""
                return "key", "esc"
            if self.buffer[1] in "[O":
                match = re.match(r"\x1b[\[O]([0-9;?]*)([@-~])", self.buffer)
                if not match:
                    if self._fill(0.05):
                        return self.read(0)
                    self.buffer = self.buffer[2:]
                    return "key", "esc"
                self.buffer = self.buffer[match.end() :]
                return "key", CSI.get((match.group(1), match.group(2)), "unknown")
            key, self.buffer = self.buffer[1], self.buffer[2:]
            return "key", ALT.get(key, "unknown")
        if self.buffer[0] in CONTROL_KEYS:
            key, self.buffer = self.buffer[0], self.buffer[1:]
            return "key", CONTROL_KEYS[key]
        match = re.match(r"[^\x00-\x1f\x7f]+", self.buffer)
        if not match:
            self.buffer = self.buffer[1:]
            return "key", "unknown"
        self.buffer = self.buffer[match.end() :]
        return "text", match.group(0)


class RawMode:
    """Every key straight to us (no echo, no line buffering, Ctrl+C as a key), plus bracketed paste."""

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.saved: list | None = None

    def __enter__(self) -> Self:
        self.saved = termios.tcgetattr(self.fd)
        mode = termios.tcgetattr(self.fd)
        mode[0] &= ~(termios.IXON | termios.ICRNL | termios.INLCR)
        mode[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG | termios.IEXTEN)
        mode[6][termios.VMIN], mode[6][termios.VTIME] = 1, 0
        termios.tcsetattr(self.fd, termios.TCSANOW, mode)
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()
        return self

    def __exit__(self, *exc: object) -> None:
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)


# --- @path menu --------------------------------------------------------------


def path_items(token: str, cwd: Path) -> list[Item]:
    """Files and folders for `@partial/path`; folders first, hidden ones only when asked for."""
    typed = token[1:]
    folder, slash, start = typed.rpartition("/")
    if slash:
        base = Path(folder or "/").expanduser()
        base = base if base.is_absolute() else cwd / base
        prefix = f"@{folder}/"
    else:
        base, prefix = cwd, "@"
    try:
        entries = list(base.iterdir())
    except OSError:
        return []
    wanted = start.casefold()
    hidden = start.startswith(".")
    matches = [
        entry
        for entry in entries
        if entry.name.casefold().startswith(wanted)
        and (hidden or not entry.name.startswith("."))
    ]
    matches.sort(key=lambda entry: (not entry.is_dir(), entry.name.casefold()))
    items = []
    for entry in matches[:200]:
        directory = entry.is_dir()
        name = entry.name + ("/" if directory else "")
        items.append(
            Item(
                name,
                "folder" if directory else "",
                prefix + name + ("" if directory else " "),
            )
        )
    return items


# --- The input box -----------------------------------------------------------

Completer = Callable[[str, int], tuple[list[Item], int, int]]


class Editor:
    """A bordered multi-line input with / and @ menus, history and paste, drawn below the transcript."""

    def __init__(self, paint: Paint, history: Path, complete: Completer) -> None:
        self.paint = paint
        self.history_path = history
        self.complete = complete
        self.history = self._load_history()
        self.cursor_row = 0  # rows between the top of the drawn block and the cursor
        self.resized = False

    def _load_history(self) -> list[str]:
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        return [
            line.encode("utf-8").decode("unicode_escape") if "\\" in line else line
            for line in lines
        ][-500:]

    def _remember(self, text: str) -> None:
        if not text.strip() or (self.history and self.history[-1] == text):
            return
        self.history.append(text)
        self.history = self.history[-500:]
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            encoded = (
                entry.encode("unicode_escape").decode("ascii") for entry in self.history
            )
            self.history_path.write_text("\n".join(encoded) + "\n", encoding="utf-8")
        except OSError:
            pass

    # Reading.
    def read(self, status: str) -> str:
        """The next message; EOFError when the user quits (Ctrl+D, or Ctrl+C twice)."""
        fd = sys.stdin.fileno()
        self.text, self.cursor = "", 0
        self.selected, self.dismissed, self.menu_key = 0, False, ()
        self.history_index, self.draft = len(self.history), ""
        self.notice, self.interrupted = "", 0.0
        self.status = status
        self.cursor_row = 0
        keyboard = Keyboard(fd)
        previous = signal.signal(signal.SIGWINCH, self._on_resize)
        try:
            with RawMode(fd):
                self.render()
                while True:
                    event = keyboard.read(0.2)
                    if event is None:
                        if self.resized:
                            self.resized = False
                            self.render()
                        continue
                    result = self.handle(*event)
                    if result is not None:
                        self.clear()
                        self._remember(result)
                        return result
                    self.render()
        except EOFError:
            self.clear()
            raise
        finally:
            signal.signal(signal.SIGWINCH, previous)

    def _on_resize(self, *args: object) -> None:
        self.resized = True

    def menu(self) -> tuple[list[Item], int, int]:
        if self.dismissed:
            return [], 0, 0
        items, start, end = self.complete(self.text, self.cursor)
        key = tuple(item.label for item in items)
        if key != self.menu_key:
            self.menu_key, self.selected = key, 0
        return items, start, end

    def accept(self, item: Item, start: int, end: int) -> None:
        self.text = self.text[:start] + item.insert + self.text[end:]
        self.cursor = start + len(item.insert)
        self.dismissed = False

    def insert(self, text: str) -> None:
        self.text = self.text[: self.cursor] + text + self.text[self.cursor :]
        self.cursor += len(text)
        self.dismissed = False

    def handle(self, kind: str, value: str) -> str | None:
        if kind in {"text", "paste"}:
            self.insert(value)
            return None
        items, start, end = self.menu()
        if value != "ctrl-c":
            self.notice = ""
        if value == "enter":
            if items:
                item = items[self.selected]
                self.accept(item, start, end)
                return self.text if item.submit else None
            if self.text[: self.cursor].endswith("\\"):
                self.text = (
                    self.text[: self.cursor - 1] + "\n" + self.text[self.cursor :]
                )
                return None
            return self.text
        if value == "tab":
            if items:
                self.accept(items[self.selected], start, end)
            return None
        if value in {"up", "down"}:
            if items:
                self.selected = (self.selected + (1 if value == "down" else -1)) % len(
                    items
                )
            elif not self.move_line(-1 if value == "up" else 1):
                self.browse(-1 if value == "up" else 1)
            return None
        if value == "esc":
            self.dismissed = bool(items)
            return None
        if value == "ctrl-c":
            if self.text:
                self.text, self.cursor = "", 0
                return None
            if time.monotonic() - self.interrupted < 2:
                raise EOFError
            self.interrupted = time.monotonic()
            self.notice = "Press Ctrl+C again to quit"
            return None
        if value == "ctrl-d":
            if not self.text:
                raise EOFError
            value = "delete"
        self.edit(value)
        return None

    def edit(self, key: str) -> None:
        text, cursor = self.text, self.cursor
        line_start = text.rfind("\n", 0, cursor) + 1
        line_end = text.find("\n", cursor)
        line_end = len(text) if line_end < 0 else line_end
        if key == "newline":
            self.insert("\n")
            return
        if key == "backspace" and cursor:
            text, cursor = text[: cursor - 1] + text[cursor:], cursor - 1
        elif key == "delete":
            text = text[:cursor] + text[cursor + 1 :]
        elif key == "left":
            cursor = max(0, cursor - 1)
        elif key == "right":
            cursor = min(len(text), cursor + 1)
        elif key == "home":
            cursor = line_start
        elif key == "end":
            cursor = line_end
        elif key == "word-left":
            cursor = _word_start(text, cursor)
        elif key == "word-right":
            cursor = _word_end(text, cursor)
        elif key == "word-backspace":
            start = _word_start(text, cursor)
            text, cursor = text[:start] + text[cursor:], start
        elif key == "word-delete":
            text = text[:cursor] + text[_word_end(text, cursor) :]
        elif key == "kill-start":
            text, cursor = text[:line_start] + text[cursor:], line_start
        elif key == "kill-end":
            text = text[:cursor] + text[line_end:]
        elif key == "redraw":
            sys.stdout.write("\x1b[H\x1b[2J")
            self.cursor_row = 0
        self.text, self.cursor = text, cursor
        self.dismissed = False

    def move_line(self, step: int) -> bool:
        """Up/Down inside a multi-line message; False when already on the first/last line."""
        lines = self.text.split("\n")
        row = self.text.count("\n", 0, self.cursor)
        target = row + step
        if not 0 <= target < len(lines):
            return False
        column = self.cursor - (self.text.rfind("\n", 0, self.cursor) + 1)
        start = sum(len(line) + 1 for line in lines[:target])
        self.cursor = start + min(column, len(lines[target]))
        return True

    def browse(self, step: int) -> None:
        if not self.history:
            return
        if self.history_index == len(self.history):
            self.draft = self.text
        index = max(0, min(len(self.history), self.history_index + step))
        if index == self.history_index:
            return
        self.history_index = index
        self.text = self.draft if index == len(self.history) else self.history[index]
        self.cursor = len(self.text)
        self.dismissed = True

    # Drawing.
    def layout(self) -> tuple[list[str], int, int]:
        paint = self.paint
        width = max(24, shutil.get_terminal_size().columns - 1)
        height = max(8, shutil.get_terminal_size().lines)
        room = width - 6  # "│ › " on the left, " │" on the right
        rows: list[
            tuple[str, int]
        ] = []  # (plain text, logical position of its first character)
        cursor_at = (0, 0)
        offset = 0
        for number, line in enumerate(self.text.split("\n")):
            segments = _wrap(line, room)
            for index, (start, end) in enumerate(segments):
                first = number == 0 and index == 0
                rows.append(
                    (("› " if first else "  ") + line[start:end], offset + start)
                )
                position = self.cursor - offset
                last = index == len(segments) - 1
                if start <= position <= end and (position < end or last):
                    cursor_at = (len(rows) - 1, 2 + cells(line[start:position]))
            offset += len(line) + 1
        items, _, _ = self.menu()
        menu_rows = min(len(items), MENU_ROWS)
        visible = max(1, min(len(rows), height - menu_rows - 4))
        top = min(max(0, cursor_at[0] - visible + 1), max(0, len(rows) - visible))
        border = DIM
        lines = [paint("╭" + "─" * (width - 2) + "╮", border)]
        for plain, _ in rows[top : top + visible]:
            if not self.text:
                body = paint("› ", CYAN, BOLD) + paint(fit(PLACEHOLDER, room), DIM)
                padding = room + 2 - 2 - cells(fit(PLACEHOLDER, room))
            else:
                marker, content = plain[:2], plain[2:]
                body = (
                    paint(marker, CYAN, BOLD) if marker.strip() else marker
                ) + content
                padding = room + 2 - cells(plain)
            lines.append(
                paint("│ ", border) + body + " " * max(0, padding) + paint(" │", border)
            )
        lines.append(paint("╰" + "─" * (width - 2) + "╯", border))
        if items:
            lines.extend(self.menu_lines(items, width))
        else:
            lines.append(self.status_line(width))
        return lines, 1 + cursor_at[0] - top, 2 + cursor_at[1]

    def menu_lines(self, items: list[Item], width: int) -> list[str]:
        paint = self.paint
        first = min(
            max(0, self.selected - MENU_ROWS + 1), max(0, len(items) - MENU_ROWS)
        )
        shown = items[first : first + MENU_ROWS]
        label_room = min(28, max(cells(item.label) for item in shown) + 2)
        lines = []
        for index, item in enumerate(shown, first):
            label = fit(item.label, label_room - 1)
            gap = " " * (label_room - cells(label))
            description = fit(item.description, max(0, width - label_room - 6))
            if index == self.selected:
                lines.append(
                    "  "
                    + paint("❯ " + label, CYAN, BOLD)
                    + gap
                    + paint(description, CYAN)
                )
            else:
                lines.append("    " + label + gap + paint(description, DIM))
        hidden = len(items) - len(shown)
        if hidden:
            lines.append(paint(f"    ↑↓ {hidden} more", DIM))
        return lines

    def status_line(self, width: int) -> str:
        """Status on the left; key hints on the right only while they fit next to it."""
        room = width - 2
        if self.notice:
            left = fit(self.status, max(10, room - cells(self.notice) - 2))
            gap = max(2, room - cells(left) - cells(self.notice))
            return self.paint("  " + left, DIM) + " " * gap + self.paint(self.notice, YELLOW)
        for hint in ("/ commands · @ files · Esc stops", "/ commands", ""):
            if cells(self.status) + cells(hint) + 2 <= room:
                gap = room - cells(self.status) - cells(hint)
                return self.paint("  " + self.status + " " * gap + hint, DIM)
        return self.paint("  " + fit(self.status, room), DIM)

    def render(self) -> None:
        lines, row, column = self.layout()
        out = ["\x1b[?25l"]
        if self.cursor_row:
            out.append(f"\x1b[{self.cursor_row}A")
        out.append("\r\x1b[J")
        out.append("\n".join(lines))
        up = len(lines) - 1 - row
        if up:
            out.append(f"\x1b[{up}A")
        out.append("\r")
        if column:
            out.append(f"\x1b[{column}C")
        out.append("\x1b[?25h")
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        self.cursor_row = row

    def clear(self) -> None:
        if self.cursor_row:
            sys.stdout.write(f"\x1b[{self.cursor_row}A")
        sys.stdout.write("\r\x1b[J")
        sys.stdout.flush()
        self.cursor_row = 0


def _wrap(line: str, room: int) -> list[tuple[int, int]]:
    """Character ranges of `line` that fit in `room` columns each."""
    if not line:
        return [(0, 0)]
    segments, start, used = [], 0, 0
    for index, character in enumerate(line):
        width = cells(character)
        if used + width > room and index > start:
            segments.append((start, index))
            start, used = index, 0
        used += width
    segments.append((start, len(line)))
    return segments


def _word_start(text: str, cursor: int) -> int:
    index = cursor
    while index > 0 and text[index - 1].isspace():
        index -= 1
    while index > 0 and not text[index - 1].isspace():
        index -= 1
    return index


def _word_end(text: str, cursor: int) -> int:
    index = cursor
    while index < len(text) and text[index].isspace():
        index += 1
    while index < len(text) and not text[index].isspace():
        index += 1
    return index


# --- Markdown in the transcript ----------------------------------------------

_INLINE = [
    (re.compile(r"`([^`\n]+)`"), (CYAN,)),
    (re.compile(r"\*\*([^*\n]+)\*\*"), (BOLD,)),
    (re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])"), (ITALIC,)),
]
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


def render_markdown_line(line: str, in_code: bool, paint: Paint) -> tuple[str, bool]:
    """One finished line of a streamed answer with its Markdown applied; returns (text, in_code)."""
    if line.lstrip().startswith("```"):
        return paint(line, DIM), not in_code
    if in_code:
        return paint(line, GREEN), True
    heading = re.match(r"^(#{1,6})\s+(.*)$", line)
    if heading:
        return paint(
            heading.group(2), BOLD, CYAN if len(heading.group(1)) == 1 else BOLD
        ), False
    quote = re.match(r"^>\s?(.*)$", line)
    if quote:
        return paint("│ " + quote.group(1), DIM, ITALIC), False
    bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
    if bullet:
        line = f"{bullet.group(1)}• {bullet.group(2)}"
    if re.fullmatch(r"\s*([-*_])(\s*\1){2,}\s*", line):
        return paint("─" * min(40, max(3, cells(line))), DIM), False
    line = _LINK.sub(
        lambda match: match.group(1) + paint(f" ({match.group(2)})", DIM), line
    )
    for pattern, codes in _INLINE:
        line = pattern.sub(
            lambda match, codes=codes: paint(match.group(1), *codes), line
        )
    return line, False


class MarkdownStream:
    """Streams raw text at once, then redraws each finished line with its Markdown styled."""

    def __init__(self, paint: Paint, write: Callable[[str], None]) -> None:
        self.paint, self.write = paint, write
        self.line = ""
        self.in_code = False

    def feed(self, text: str) -> None:
        while text:
            head, newline, text = text.partition("\n")
            if head:
                self.line += head
                self.write(head)
            if newline:
                self._finish()
                self.write("\n")

    def _finish(self) -> None:
        if not self.paint.enabled:
            self.line = ""
            return
        width = max(1, shutil.get_terminal_size().columns)
        rows = max(1, -(-cells(self.line) // width))
        rendered, self.in_code = render_markdown_line(
            self.line, self.in_code, self.paint
        )
        if self.line:
            self.write(
                (f"\x1b[{rows - 1}A" if rows > 1 else "") + "\r\x1b[J" + rendered
            )
        self.line = ""

    def close(self) -> None:
        """End of the answer: style the last unfinished line too."""
        if self.line:
            self._finish()
        self.in_code = False


def choose(
    options: list[str],
    read_key: Callable[[], str],
    write: Callable[[str], None],
    paint: Paint,
    shortcuts: dict[str, int],
) -> int:
    """A one-line option picker: ←/→ (or ↑/↓, Tab) and Enter, or a shortcut letter; Esc picks the last option."""
    selected = 0

    def draw() -> None:
        parts = [
            paint("❯ " + option, CYAN, BOLD)
            if index == selected
            else paint("  " + option, DIM)
            for index, option in enumerate(options)
        ]
        write("\r\x1b[K" + "   ".join(parts))

    draw()
    while True:
        key = read_key()
        if key in {"\r", "\n"}:
            break
        if key in {"\x1b[C", "\x1b[B", "\t", "\x1bOC", "\x1bOB"}:
            selected = (selected + 1) % len(options)
        elif key in {"\x1b[D", "\x1b[A", "\x1b[Z", "\x1bOD", "\x1bOA"}:
            selected = (selected - 1) % len(options)
        elif key == "\x1b" or key == "":
            selected = len(options) - 1
            break
        elif key.casefold() in shortcuts:
            selected = shortcuts[key.casefold()]
            break
        draw()
    draw()
    write("\n")
    return selected
