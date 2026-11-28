"""`ule --stream`: the editor Unlaw.app's Edit shows, driven as a black box over JSON lines."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_terminal_hangup import ule_binary  # noqa: E402
from ulbin import CoreTestCase  # noqa: E402


class UleStreamTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env.update({"ULE_UL": "/usr/bin/false", "ULE_NO_CLIPBOARD": "1"})

    def run_ule(
        self, events: list[dict], *files: Path, wait: float = 1.0
    ) -> tuple[subprocess.CompletedProcess, list[dict]]:
        """Sends `events`, keeps stdin open `wait` seconds, then closes it (the app went away)."""
        process = subprocess.Popen(
            [str(ule_binary()), "--stream", "--size", "12x60", *map(str, files)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            cwd=self.root,
        )
        assert process.stdin is not None
        for event in events:
            process.stdin.write((json.dumps(event) + "\n").encode())
        process.stdin.flush()
        time.sleep(wait)
        out, err = process.communicate(timeout=15)
        frames = [
            json.loads(line) for line in out.decode().splitlines() if line.strip()
        ]
        return subprocess.CompletedProcess(
            process.args, process.returncode, out.decode(), err.decode()
        ), frames

    @staticmethod
    def key(code: str, **flags: bool) -> dict:
        return {"key": {"code": code, **flags}}

    def test_typing_and_saving_change_the_file(self) -> None:
        note = self.root / "note.md"
        note.write_text("one\n")
        events = [
            self.key("G"),
            self.key("o"),
            *(self.key(c) for c in "two"),
            self.key("Esc"),
            self.key("s", ctrl=True),
        ]
        result, frames = self.run_ule(events, note)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(note.read_text(), "one\ntwo\n")
        last = frames[-1]
        self.assertEqual((last["rows"], last["cols"]), (12, 60))
        self.assertEqual(last["buffers"][0]["path"], str(note.resolve()))
        self.assertFalse(last["buffers"][0]["modified"])
        self.assertFalse(last["typing"], "back in normal mode")

    def test_frames_say_when_keys_are_text(self) -> None:
        note = self.root / "a.txt"
        note.write_text("x\n")
        _, frames = self.run_ule([self.key("i")], note)
        self.assertTrue(frames[-1]["typing"], "insert mode")
        self.assertFalse(frames[0]["typing"])

    def test_closing_stdin_keeps_unsaved_work_as_a_recovery_copy(self) -> None:
        note = self.root / "keep.txt"
        note.write_text("first\n")
        result, _ = self.run_ule(
            [self.key("A"), {"paste": " more"}, self.key("Esc")], note
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(note.read_text(), "first\n", "the file itself is left alone")
        recovered = list((self.unlaw / "data" / "ule" / "recovered").glob("keep.txt.*"))
        self.assertEqual(len(recovered), 1, result.stderr)
        self.assertIn("first more", recovered[0].read_text())

    def test_files_open_show_and_close_by_path(self) -> None:
        first, second = self.root / "a.rs", self.root / "b.rs"
        first.write_text("fn a() {}\n")
        second.write_text("fn b() {}\n")
        events = [
            {"open": {"path": str(second)}},
            {"show": str(first)},
            {"close": str(second)},
        ]
        _, frames = self.run_ule(events, first)
        paths = [buffer["path"] for buffer in frames[-1]["buffers"]]
        self.assertEqual(paths, [str(first.resolve())])

    def test_resize_and_bad_lines_are_handled(self) -> None:
        note = self.root / "a.txt"
        note.write_text("x\n")
        events: list = [
            {"resize": {"rows": 20, "cols": 70}},
            {"key": {"code": "Nope"}},
            {"open": {"path": "relative"}},
        ]
        process = subprocess.Popen(
            [str(ule_binary()), "--stream", str(note)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            cwd=self.root,
        )
        assert process.stdin is not None
        process.stdin.write(
            b"not json\n" + "".join(json.dumps(e) + "\n" for e in events).encode()
        )
        process.stdin.flush()
        time.sleep(1)
        out, _ = process.communicate(timeout=15)
        last = json.loads(out.decode().splitlines()[-1])
        self.assertEqual((last["rows"], last["cols"]), (20, 70))
        self.assertEqual(process.returncode, 0)

    def test_terminal_handoffs_are_refused_in_a_window(self) -> None:
        note = self.root / "a.txt"
        note.write_text("x\n")
        events = [
            self.key(":", shift=False),
            *(self.key(c) for c in "terminal"),
            self.key("Enter"),
        ]
        result, frames = self.run_ule(events, note)
        self.assertEqual(result.returncode, 0, result.stderr)
        screen = "".join(run[1] for line in frames[-1]["lines"] for run in line)
        self.assertIn(":terminal needs a terminal", screen)

    def test_standard_editing_types_without_modes(self) -> None:
        note = self.root / "plain.txt"
        note.write_text("end\n")
        events = [
            {"set": {"name": "editing", "value": "standard"}},
            *(self.key(c) for c in "go "),
            self.key("Esc"),
            self.key("s", ctrl=True),
        ]
        result, frames = self.run_ule(events, note)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(note.read_text(), "go end\n", "letters type at once; Esc keeps typing")
        self.assertEqual(frames[-1]["editing"], "standard")
        self.assertTrue(frames[-1]["typing"])
        screen = "".join(run[1] for line in frames[-1]["lines"] for run in line)
        self.assertIn("EDIT", screen)

    def test_theme_and_window_commands(self) -> None:
        note = self.root / "a.txt"
        note.write_text("x\n")
        events = [
            {"set": {"name": "theme", "value": "nord"}},
            {"set": {"name": "nope", "value": "1"}},
            {"command": "command_palette"},
        ]
        _, frames = self.run_ule(events, note)
        theme = frames[-1]["theme"]
        self.assertEqual(theme["name"], "nord")
        self.assertEqual(theme["bg"], "#2e3440")
        screen = "".join(run[1] for line in frames[-1]["lines"] for run in line)
        self.assertIn("Commands", screen, "the command list is open")

    def test_cd_sets_the_project_folder(self) -> None:
        project = self.root / "project"
        (project / "src").mkdir(parents=True)
        (project / "src" / "deep_file.rs").write_text("fn main() {}\n")
        (self.root / "outside_file.rs").write_text("\n")
        note = project / "a.txt"
        note.write_text("x\n")
        events = [{"cd": str(project)}, {"command": "file_picker"}]
        _, frames = self.run_ule(events, note, wait=2.0)
        screen = "\n".join("".join(run[1] for run in line) for line in frames[-1]["lines"])
        self.assertIn("src/deep_file.rs", screen)
        self.assertNotIn("outside_file", screen)

    def test_zed_keys_from_the_window_edit_at_several_cursors(self) -> None:
        note = self.root / "multi.txt"
        note.write_text("foo bar foo\nbaz\n")
        events = [
            {"set": {"name": "editing", "value": "standard"}},
            {"command": "select_next_occurrence"},
            {"command": "select_next_occurrence"},
            self.key("x"),
            {"command": "select_line"},
            {"command": "single_cursor"},
            {"command": "search_selection"},
            self.key("Esc"),
            self.key("s", ctrl=True),
        ]
        result, frames = self.run_ule(events, note)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(note.read_text(), "x bar x\nbaz\n")
        refused = self.run_ule([{"command": "rm_rf"}, {"command": "quit_all"}], note)[1]
        self.assertTrue(refused, "unknown and unlisted commands are ignored, ule keeps running")

    def test_alt_click_adds_a_cursor(self) -> None:
        note = self.root / "click.txt"
        note.write_text("ab\ncd\n")
        events = [
            {"set": {"name": "editing", "value": "standard"}},
            {"set": {"name": "line_numbers", "value": "off"}},
            {"mouse": {"kind": "down", "x": 0, "y": 1, "alt": True}},
            {"mouse": {"kind": "up", "x": 0, "y": 1}},
            self.key("-"),
            self.key("s", ctrl=True),
        ]
        result, _ = self.run_ule(events, note)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(note.read_text(), "-ab\n-cd\n")

    def test_stream_refuses_stdin_text(self) -> None:
        result = subprocess.run(
            [str(ule_binary()), "--stream", "-"],
            input="x",
            capture_output=True,
            text=True,
            env=self.env,
            timeout=15,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--stream reads its input from stdin", result.stderr)


if __name__ == "__main__":
    unittest.main()
