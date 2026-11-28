"""ule in a terminal, standard mode: the bytes a terminal (Ghostty) sends for each key.

Ghostty keeps most Cmd keys for itself and sends Cmd-Left/Right/Backspace as
Ctrl-A/Ctrl-E/Ctrl-U, Option-Left/Right as Esc b / Esc f; other combinations come
as CSI sequences (ule asks for the kitty "disambiguate" mode). Each test types
the bytes on a real pty, saves with Ctrl-S and compares the file.
"""

from __future__ import annotations

import fcntl
import os
import pty
import select
import subprocess
import sys
import termios
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_terminal_hangup import ule_binary  # noqa: E402
from ulbin import CoreTestCase  # noqa: E402

CTRL_S = b"\x13"


def csi_u(code: int, mods: int) -> bytes:
    """Kitty keyboard protocol: mods = 1 + shift(1) + alt(2) + ctrl(4)."""
    return f"\x1b[{code};{mods}u".encode()


def arrow(letter: str, mods: int) -> bytes:
    return f"\x1b[1;{mods}{letter}".encode()


class UleTerminalKeysTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        config = self.root / "ule.toml"
        config.write_text('[editor]\nediting = "standard"\nline_numbers = "off"\nrestore_cursor = false\n')
        self.env.update(
            {
                "ULE_CONFIG": str(config),
                "ULE_NO_CLIPBOARD": "1",
                "ULE_UL": "/usr/bin/false",
            }
        )

    def typed(self, text: str, *keys: bytes) -> str:
        """Opens a file holding `text`, sends `keys` one by one, saves, returns the file."""
        note = self.root / "note.txt"
        note.write_text(text)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, b"\x18\x00\x50\x00\x00\x00\x00\x00")

        def own_terminal() -> None:
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        process = subprocess.Popen(
            [str(ule_binary()), str(note)],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=self.env,
            cwd=self.root,
            preexec_fn=own_terminal,
        )
        os.close(slave)

        def drain(seconds: float) -> None:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        os.read(master, 65536)
                    except OSError:
                        return

        try:
            drain(1.5)
            for key in (*keys, CTRL_S):
                os.write(master, key)
                drain(0.15)
            drain(0.8)
            return note.read_text()
        finally:
            os.close(master)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def test_typing_needs_no_mode(self) -> None:
        self.assertEqual(self.typed("end\n", b"go "), "go end\n")

    def test_cmd_arrows_and_backspace_as_ghostty_sends_them(self) -> None:
        # Cmd-Right (Ctrl-E) then text; Cmd-Left (Ctrl-A) then text.
        self.assertEqual(self.typed("abc\n", b"\x05", b"!", b"\x01", b">"), ">abc!\n")
        # Cmd-Backspace (Ctrl-U) deletes to the line start.
        self.assertEqual(self.typed("abc def\nx\n", b"\x05", b"\x15"), "\nx\n")

    def test_option_words(self) -> None:
        # Option-Right twice (Esc f), then Option-Backspace (Esc DEL).
        self.assertEqual(
            self.typed("one two three\n", b"\x1bf", b"\x1bf", b"\x1b\x7f"),
            "one  three\n",
        )

    def test_lines_move_and_duplicate(self) -> None:
        self.assertEqual(
            self.typed("a\nb\n", arrow("B", 3)), "b\na\n", "Option-Down moves the line"
        )
        self.assertEqual(
            self.typed("a\nb\n", arrow("B", 4)),
            "a\na\nb\n",
            "Option-Shift-Down duplicates",
        )

    def test_several_cursors(self) -> None:
        # Ctrl-D twice on "foo", then type.
        self.assertEqual(self.typed("foo x foo\n", b"\x04", b"\x04", b"z"), "z x z\n")
        # Ctrl-Shift-L: every match.
        self.assertEqual(
            self.typed("ab ab ab\n", b"\x04", csi_u(ord("l"), 6), b"c"), "c c c\n"
        )
        # Ctrl-Alt-Down: a cursor below.
        self.assertEqual(self.typed("x\ny\n", arrow("B", 7), b"-"), "-x\n-y\n")

    def test_line_actions(self) -> None:
        self.assertEqual(
            self.typed("a\nb\nc\n", b"\x0c", b"\x7f"),
            "b\nc\n",
            "Ctrl-L selects the line",
        )
        self.assertEqual(
            self.typed("x\n", csi_u(ord("]"), 5)), "    x\n", "Ctrl-] indents"
        )
        self.assertEqual(
            self.typed("a\nb\n", csi_u(13, 5), b"n"),
            "a\nn\nb\n",
            "Ctrl-Enter: new line below",
        )
        self.assertEqual(
            self.typed("ab\n", b"\x05", b"\x14"), "ba\n", "Ctrl-T transposes"
        )

    def test_select_all_and_undo(self) -> None:
        self.assertEqual(
            self.typed("a\nb\n", csi_u(ord("a"), 6), b"z"),
            "z\n",
            "Ctrl-Shift-A selects all",
        )
        self.assertEqual(
            self.typed("a\n", b"xyz", b"\x1a"), "a\n", "Ctrl-Z undoes the typing"
        )

    def test_expand_selection(self) -> None:
        self.assertEqual(
            self.typed(
                "f(a, b)\n", b"\x1b[C", b"\x1b[C", arrow("C", 6), arrow("C", 6), b"q"
            ),
            "f(q)\n",
        )


if __name__ == "__main__":
    unittest.main()
