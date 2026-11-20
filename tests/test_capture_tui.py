"""The terminal studio of `ul capture` (`capture_tui.py`): pure frame drawing and key handling."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unlawful import capture_project, capture_tui  # noqa: E402


def model(**changes: object) -> dict:
    base = {
        "setup": capture_project.default_setup({}),
        "status": {"active": False},
        "devices": None,
        "message": "",
        "export": None,
        "screen": "main",
        "choice": None,
        "project": None,
    }
    base.update(changes)
    return base


RECORDING = {
    "active": True,
    "phase": "recording",
    "paused": False,
    "elapsed": 751.0,
    "scene": "camera",
    "level_db": -18.0,
    "warnings": ["the microphone is silent"],
    "free_bytes": 182 * 10**9,
    "camera": True,
    "mode": "screen",
    "project": "/x/screen-1",
}


class FrameTests(unittest.TestCase):
    def test_other_digit_characters_do_nothing(self) -> None:
        # A superscript digit (the key left of 1 on AZERTY) used to crash the whole studio.
        for key in ("²", "³", "¹", "٣"):
            self.assertIsNone(capture_tui.tui_action(key, model()), key)

    def test_frame_shows_recording(self) -> None:
        frame = capture_tui.render_frame(model(status=RECORDING), 100, 30)
        text = "\n".join(frame)
        self.assertIn("● REC 00:12:31", text)
        self.assertIn("3 ● Camera", text)
        self.assertIn("the microphone is silent", text)
        self.assertIn("182 GB free", text)
        self.assertIn("-18 dB", text)
        self.assertEqual(len(frame), 30)
        self.assertTrue(all(len(line) <= 100 for line in frame))

    def test_small_terminals_never_wrap_and_keep_the_key_bar(self) -> None:
        for cols, rows in ((60, 20), (40, 12), (80, 24)):
            frame = capture_tui.render_frame(model(status=RECORDING), cols, rows)
            with self.subTest(size=(cols, rows)):
                self.assertEqual(len(frame), rows)
                self.assertTrue(all(len(line) <= cols for line in frame))
                self.assertIn("Q", frame[-1])

    def test_idle_frame_shows_the_setup(self) -> None:
        setup = capture_project.default_setup({})
        setup["sources"][1]["enabled"] = True
        setup["sources"][1]["device"] = "FaceTime HD Camera"
        text = "\n".join(capture_tui.render_frame(model(setup=setup), 100, 30))
        self.assertIn("Ready", text)
        self.assertIn("1 ● Screen + camera", text)
        self.assertIn("[x] Camera", text)
        self.assertIn("FaceTime HD Camera", text)
        self.assertIn("Format 16:9", text)

    def test_paused_and_stuck(self) -> None:
        paused = dict(RECORDING, paused=True, phase="paused")
        self.assertIn(
            "❚❚ PAUSED 00:12:31",
            "\n".join(capture_tui.render_frame(model(status=paused), 100, 30)),
        )
        stuck = dict(RECORDING, phase="stuck", stuck=["screencapture"])
        self.assertIn(
            "screencapture",
            "\n".join(capture_tui.render_frame(model(status=stuck), 100, 30)),
        )

    def test_export_screen(self) -> None:
        choice = {
            "canvas": "9:16",
            "height": 1080,
            "fps": 60,
            "codec": "h264",
            "quality": "high",
            "container": "mov",
            "normalize": True,
        }
        text = "\n".join(
            capture_tui.render_frame(
                model(
                    screen="export",
                    choice=choice,
                    project="/x/screen-1",
                    export={"phase": "running", "percent": 40, "eta": 12},
                ),
                100,
                30,
            )
        )
        self.assertIn("Export screen-1", text)
        self.assertIn("9:16", text)
        self.assertIn("1080x1920", text)
        self.assertIn("40%", text)


class KeyTests(unittest.TestCase):
    def test_keys(self) -> None:
        idle = model()
        self.assertEqual(capture_tui.tui_action("r", idle), ("record",))
        self.assertEqual(capture_tui.tui_action("R", idle), ("record",))
        self.assertEqual(capture_tui.tui_action("2", idle), ("scene", "screen"))
        self.assertEqual(capture_tui.tui_action("f", idle), ("canvas", "9:16"))
        self.assertEqual(capture_tui.tui_action("c", idle), ("toggle", "camera"))
        self.assertEqual(capture_tui.tui_action("e", idle), ("export",))
        self.assertEqual(capture_tui.tui_action("q", idle), ("quit",))
        self.assertIsNone(
            capture_tui.tui_action("m", idle), "no mark without a recording"
        )
        active = model(status=RECORDING)
        self.assertEqual(capture_tui.tui_action("r", active), ("stop",))
        self.assertEqual(capture_tui.tui_action("p", active), ("pause",))
        self.assertEqual(capture_tui.tui_action("m", active), ("mark",))
        self.assertIsNone(capture_tui.tui_action("9", active), "no 9th scene")
        self.assertIsNone(
            capture_tui.tui_action("c", active), "sources do not change while recording"
        )

    def test_export_keys_cycle_choices(self) -> None:
        choice = {
            "canvas": "16:9",
            "height": 1440,
            "fps": 60,
            "codec": "h264",
            "quality": "high",
            "container": "mov",
            "normalize": True,
        }
        screen = model(screen="export", choice=choice, project="/x/p")
        self.assertEqual(
            capture_tui.tui_action("f", screen), ("choose", "canvas", "9:16")
        )
        self.assertEqual(
            capture_tui.tui_action("h", screen), ("choose", "height", 2160)
        )
        self.assertEqual(capture_tui.tui_action("t", screen), ("choose", "fps", 30))
        self.assertEqual(
            capture_tui.tui_action("k", screen), ("choose", "codec", "hevc")
        )
        self.assertEqual(
            capture_tui.tui_action("o", screen), ("choose", "container", "mp4")
        )
        self.assertEqual(
            capture_tui.tui_action("n", screen), ("choose", "normalize", False)
        )
        self.assertEqual(capture_tui.tui_action("\n", screen), ("start-export",))
        self.assertEqual(capture_tui.tui_action("q", screen), ("back",))
        done = model(
            screen="export",
            choice=choice,
            project="/x/p",
            export={"phase": "done", "output": "/x/out.mov"},
        )
        self.assertEqual(capture_tui.tui_action("o", done), ("open", "/x/out.mov"))
        self.assertEqual(capture_tui.tui_action("v", done), ("reveal", "/x/out.mov"))


if __name__ == "__main__":
    unittest.main()
