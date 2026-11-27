"""A closed terminal (its window, an ssh drop) must end every full-screen program.

crossterm's default event source loops forever on a hung-up terminal: its reads
return nothing and it never gives control back, so a signal is never noticed. An
orphaned `ule` once ran at 100% CPU for almost three days. These tests close the
terminal under ule, the arcade and the feature checklist and expect each to exit.
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

from ulbin import ROOT, CoreTestCase, binary  # noqa: E402

EXIT_WITHIN = 8.0


def ule_binary() -> Path:
    subprocess.run(["cargo", "build", "--quiet", "-p", "ule"], cwd=ROOT, check=True)
    return ROOT / "target" / "debug" / "ule"


class TerminalHangupTests(CoreTestCase):
    def run_then_close(
        self, argv: list[str], keys: bytes = b"", settle: float = 3.0
    ) -> int | None:
        """Start `argv` on a fresh terminal, type `keys`, close the terminal; the exit code, or None if it kept running."""
        master, slave = pty.openpty()
        fcntl.ioctl(
            slave, termios.TIOCSWINSZ, b"\x18\x00\x50\x00\x00\x00\x00\x00"
        )  # 24 rows, 80 columns

        def own_terminal() -> None:
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        process = subprocess.Popen(
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=self.env,
            cwd=self.root,
            preexec_fn=own_terminal,
        )
        os.close(slave)
        typed = False
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline and process.poll() is None:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    os.read(master, 65536)
                except OSError:
                    break
            if keys and not typed and time.monotonic() > deadline - settle / 2:
                os.write(master, keys)
                typed = True
        os.close(master)  # the terminal window closes
        try:
            return process.wait(timeout=EXIT_WITHIN)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return None

    def test_ule_saves_its_work_and_exits(self) -> None:
        note = self.root / "note.txt"
        note.write_text("first\n")
        env = {
            "ULE_UL": "/usr/bin/false",
            "ULE_NO_CLIPBOARD": "1",
            "TERM": "xterm-256color",
        }
        self.env.update(env)
        code = self.run_then_close(
            [str(ule_binary()), str(note)], keys=b"ihello\x1b", settle=4.0
        )
        self.assertIsNotNone(code, "ule kept running after its terminal closed")
        self.assertEqual(note.read_text(), "first\n", "the file itself is left alone")
        recovered = list((self.unlaw / "data" / "ule" / "recovered").glob("note.txt.*"))
        self.assertEqual(
            len(recovered), 1, "the unsaved change is kept as a recovery copy"
        )
        self.assertIn("hello", recovered[0].read_text())

    def test_the_arcade_exits(self) -> None:
        self.env["TERM"] = "xterm-256color"
        self.assertIsNotNone(
            self.run_then_close([str(binary()), "game"]), "ul game kept running"
        )

    def test_the_feature_checklist_exits(self) -> None:
        self.env["TERM"] = "xterm-256color"
        self.assertIsNotNone(
            self.run_then_close([str(binary()), "features", "choose"]),
            "the checklist kept running",
        )


if __name__ == "__main__":
    unittest.main()
