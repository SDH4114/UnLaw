"""Studio setup and project model (`capture_project.py`): pure data, no tools."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unlawful import capture_project  # noqa: E402
from unlawful.config import ensure_layout  # noqa: E402


class ProjectTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "home").mkdir()
        environment = patch.dict(
            os.environ,
            {
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "PATH": "/usr/bin:/bin",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        ensure_layout()


class SetupTests(ProjectTestCase):
    def test_default_layouts_follow_haos_rules(self) -> None:
        layouts = capture_project.default_layouts()
        cam = layouts["16:9"]["screen-camera"]["placements"]["camera"]
        self.assertEqual(
            (cam["box"], cam["anchor"], cam["radius"], cam["fit"]),
            ([0, 0.76, 0.24, 0.24], "bottom-left", 0.0, "cover"),
        )
        self.assertEqual(
            layouts["16:9"]["screen-camera"]["placements"]["screen"]["fit"], "contain"
        )
        for canvas in ("9:16", "1:1", "4:5"):
            placements = layouts[canvas]["screen-camera"]["placements"]
            self.assertEqual(
                (placements["camera"]["box"], placements["screen"]["box"]),
                ([0, 0, 1, 0.4], [0, 0.4, 1, 0.6]),
            )
            self.assertEqual(layouts[canvas]["screen"]["background"], {"kind": "blur"})
        self.assertEqual(
            layouts["16:9"]["side"]["placements"]["camera"]["box"], [2 / 3, 0, 1 / 3, 1]
        )
        self.assertEqual(
            layouts["9:16"]["side"]["placements"]["camera"]["box"], [0, 0, 1, 0.5]
        )
        self.assertEqual(
            layouts["16:9"]["camera"]["placements"]["camera"]["box"], [0, 0, 1, 1]
        )

    def test_shapes_keep_width_and_corner(self) -> None:
        wide = capture_project.default_layouts()["16:9"]["screen-camera"]["placements"][
            "camera"
        ]
        circle = capture_project.apply_shape(wide, "circle", "16:9")
        self.assertAlmostEqual(circle["box"][2], 0.24)
        self.assertAlmostEqual(circle["box"][3], 0.24 * 16 / 9)
        self.assertEqual((circle["radius"], circle["anchor"]), (0.5, "bottom-left"))
        self.assertAlmostEqual(circle["box"][1] + circle["box"][3], 1.0)
        self.assertEqual(wide["radius"], 0.0, "the input placement is not changed")
        tall = capture_project.apply_shape(wide, "tall", "16:9")
        self.assertAlmostEqual(tall["box"][3], 0.24 * 16 / 9 * 16 / 9)

    def test_pin_moves_the_box_flush(self) -> None:
        placement = {"box": [0.3, 0.3, 0.2, 0.25], "anchor": None}
        self.assertEqual(
            capture_project.pin(placement, "bottom-right")["box"],
            [0.8, 0.75, 0.2, 0.25],
        )
        self.assertEqual(
            capture_project.pin(placement, "top-left")["box"], [0, 0, 0.2, 0.25]
        )
        self.assertIsNone(capture_project.pin(placement, None)["anchor"])

    def test_canvas_sizes_and_bitrates(self) -> None:
        size = capture_project.canvas_size
        self.assertEqual(
            [
                size("16:9", 1440),
                size("9:16", 1080),
                size("1:1", 1080),
                size("4:5", 1080),
                size("16:9", 2160),
                size("9:16", 2160),
            ],
            [
                (2560, 1440),
                (1080, 1920),
                (1080, 1080),
                (1080, 1350),
                (3840, 2160),
                (2160, 3840),
            ],
        )
        rate = capture_project.video_bitrate
        self.assertEqual(rate(2560, 1440, 60, "h264", "high"), 24_330_240)
        self.assertEqual(rate(2560, 1440, 60, "h264", "max"), 36_495_360)
        self.assertEqual(rate(2560, 1440, 60, "hevc", "high"), 15_814_656)

    def test_default_setup_reads_capture_config(self) -> None:
        setup = capture_project.default_setup(
            {
                "audio_device": "MacBook Pro Microphone",
                "system_audio": False,
                "show_clicks": False,
                "screen_audio": True,
                "camera_device": "default",
            }
        )
        self.assertEqual(setup["audio"]["mic"]["device"], "MacBook Pro Microphone")
        self.assertFalse(setup["audio"]["system"]["enabled"])
        self.assertFalse(setup["sources"][0]["clicks"])
        self.assertFalse(setup["sources"][1]["enabled"], "camera off until chosen")
        self.assertEqual(
            [scene["name"] for scene in setup["scenes"]],
            ["Screen + camera", "Screen", "Camera", "Side by side"],
        )
        self.assertEqual(capture_project.validate_setup(setup), setup)
        self.assertFalse(
            capture_project.default_setup({"screen_audio": False})["audio"]["mic"][
                "enabled"
            ]
        )

    def test_setup_validation_refuses_bad_values(self) -> None:
        good = capture_project.default_setup({})
        for path, value in (
            (("canvas",), "21:9"),
            (("countdown",), 99),
            (("export", "height"), 720),
            (("sources", 0, "id"), "../x"),
            (("audio", "mic", "volume"), 3.0),
            (("menubar",), 1),
            (("scene",), "nope"),
            (("audio", "mic", "format"), "ogg"),
            (("sources", 1, "quality"), "ultra"),
            (
                ("layouts", "16:9", "screen-camera", "placements", "camera", "radius"),
                0.9,
            ),
            (
                ("layouts", "16:9", "screen-camera", "placements", "camera", "anchor"),
                "middle",
            ),
        ):
            bad = json.loads(json.dumps(good))
            target = bad
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with (
                self.subTest(path=path),
                self.assertRaises(capture_project.ProjectError),
            ):
                capture_project.validate_setup(bad)

    def test_setup_round_trip_and_damaged_file(self) -> None:
        setup, warnings = capture_project.load_setup()
        self.assertEqual((setup["canvas"], warnings), ("16:9", []))
        setup["canvas"] = "9:16"
        capture_project.save_setup(setup)
        self.assertEqual(capture_project.load_setup()[0]["canvas"], "9:16")
        capture_project.setup_path().write_text("{broken")
        setup, warnings = capture_project.load_setup()
        self.assertEqual(setup["canvas"], "16:9")
        self.assertTrue(any("damaged" in warning for warning in warnings))
        self.assertEqual(
            len(list(capture_project.setup_path().parent.glob("setup.json.damaged-*"))),
            1,
        )


class ProjectTests(ProjectTestCase):
    def make(self) -> Path:
        return capture_project.create_project("screen", capture_project.default_setup({}), {})

    def test_intervals_split_at_segments_and_scenes(self) -> None:
        project = {
            "segments": [{"duration": 10.0}, {"duration": 5.0}],
            "events": [
                {"t": 0.0, "scene": "screen-camera"},
                {"t": 4.0, "scene": "camera"},
                {"t": 4.0, "mark": "x"},
                {"t": 12.0, "scene": "screen"},
            ],
        }
        self.assertEqual(
            capture_project.timeline_intervals(project, 60),
            [
                {"segment": 0, "start": 0.0, "length": 4.0, "scene": "screen-camera"},
                {"segment": 0, "start": 4.0, "length": 6.0, "scene": "camera"},
                {"segment": 1, "start": 0.0, "length": 2.0, "scene": "camera"},
                {"segment": 1, "start": 2.0, "length": 3.0, "scene": "screen"},
            ],
        )

    def test_intervals_round_to_frames_and_drop_empty_ones(self) -> None:
        project = {
            "segments": [{"duration": 1.0}, {"duration": 0.004}],
            "events": [
                {"t": 0.0, "scene": "screen"},
                {"t": 0.5071, "scene": "camera"},
                {"t": 0.5072, "scene": "screen"},
            ],
        }
        got = capture_project.timeline_intervals(project, 60)
        self.assertEqual([round(item["start"] * 60, 6) % 1 for item in got], [0.0] * len(got))
        self.assertTrue(all(item["length"] >= 1 / 60 for item in got))
        # The camera flick is shorter than a frame; the two screen pieces join into one.
        self.assertEqual(got, [{"segment": 0, "start": 0.0, "length": 1.0, "scene": "screen"}])

    def test_a_part_shorter_than_a_frame_gives_no_video(self) -> None:
        # The export drops such parts from the sound, so the picture must drop them too (else it runs a frame late).
        project = {"segments": [{"duration": 0.016}, {"duration": 0.012}, {"duration": 1.0}], "events": []}
        got = capture_project.timeline_intervals(project, 30)
        self.assertEqual([item["segment"] for item in got], [2])

    def test_scene_events_count_in_time_order(self) -> None:
        project = {"segments": [{"duration": 10.0}], "events": [{"t": 6.0, "scene": "screen"}, {"t": 2.0, "scene": "camera"}]}
        got = capture_project.timeline_intervals(project, 30)
        self.assertEqual([(item["start"], item["scene"]) for item in got], [(0.0, "camera"), (6.0, "screen")])

    def test_project_names_and_segment_info_are_checked(self) -> None:
        folder = self.make()
        good = capture_project.read_project(folder)
        for name in ("../../x", "a/b", ".hidden", "a\\b"):
            project = dict(good, name=name)
            with self.assertRaises(capture_project.ProjectError, msg=name):
                capture_project.validate_project(project, folder)
        segment = {"duration": 1.0, "files": {}, "starts": {}, "info": {"screen": {"width": "wide", "height": 1080, "audio": True}}}
        with self.assertRaises(capture_project.ProjectError):
            capture_project.validate_project(dict(good, segments=[segment]), folder)
        segment["info"]["screen"] = {"width": 1920, "height": 1080, "audio": True}
        capture_project.validate_project(dict(good, segments=[segment]), folder)

    def test_end_alignment(self) -> None:
        self.assertEqual(
            capture_project.segment_starts({"screen": 10.0, "camera": 9.69, "mic": 9.06}, "screen"),
            {"screen": 0.0, "camera": 0.31, "mic": 0.94},
        )
        self.assertEqual(capture_project.segment_starts({"screen": 10.0, "mic": 10.2}, "screen")["mic"], -0.2)

    def test_project_round_trip_keeps_unknown_keys_and_refuses_escapes(self) -> None:
        folder = self.make()
        self.assertEqual(folder.parent, capture_project.projects_dir())
        for sub in ("media", "assets", "logs", "cache"):
            self.assertTrue((folder / sub).is_dir())
        data = capture_project.read_project(folder)
        self.assertEqual((data["format"], data["version"], data["state"]), ("unlaw-studio-project", 1, "recording"))
        self.assertEqual(data["events"], [{"t": 0.0, "scene": "screen-camera"}])
        data["future"] = {"x": 1}
        capture_project.write_project(folder, data)
        self.assertEqual(capture_project.read_project(folder)["future"], {"x": 1})
        (folder / "media" / "link.mp4").symlink_to("/etc/hosts")
        for bad in ("media/../../etc/passwd", "/etc/passwd", "media/link.mp4", "../x.mp4"):
            data["segments"] = [{"duration": 1.0, "files": {"screen": bad}, "starts": {"screen": 0.0}}]
            with self.subTest(bad=bad), self.assertRaises(capture_project.ProjectError):
                capture_project.validate_project(data, folder)
        data["segments"] = [{"duration": 1.0, "files": {"screen": "media/screen-001.mp4"}, "starts": {"screen": 0.0}}]
        capture_project.validate_project(data, folder)

    def test_names_never_clash(self) -> None:
        first, second = self.make(), self.make()
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir() and second.is_dir())

    def test_assets_used_by_the_setup_are_copied(self) -> None:
        assets = capture_project.assets_dir()
        assets.mkdir(parents=True, exist_ok=True)
        (assets / "logo.png").write_bytes(b"png")
        setup = capture_project.default_setup({})
        setup["sources"].append({"id": "img-1", "kind": "image", "enabled": True, "asset": "logo.png"})
        folder = capture_project.create_project("screen", setup, {})
        self.assertEqual((folder / "assets" / "logo.png").read_bytes(), b"png")

    def test_events_are_added(self) -> None:
        folder = self.make()
        capture_project.add_event(folder, {"t": 2.5, "scene": "camera"})
        capture_project.add_event(folder, {"t": 3.0, "mark": "intro"})
        events = capture_project.read_project(folder)["events"]
        self.assertEqual(events[1:], [{"t": 2.5, "scene": "camera"}, {"t": 3.0, "mark": "intro"}])
        with self.assertRaises(capture_project.ProjectError):
            capture_project.add_event(folder, {"t": 1.0, "scene": "nope"})

    def test_missing_camera_falls_back_to_the_screen_layout(self) -> None:
        folder = self.make()
        project = capture_project.read_project(folder)
        project["segments"] = [{"duration": 2.0, "files": {"screen": "media/screen-001.mp4"}, "starts": {"screen": 0.0}}]
        background, placements = capture_project.effective_placements(project, "screen-camera", "9:16")
        self.assertEqual([source for source, _ in placements], ["screen"])
        self.assertEqual(background, {"kind": "blur"})
        project["segments"][0]["files"]["camera"] = "media/camera-001.mp4"
        project["sources"][1]["enabled"] = True
        _, placements = capture_project.effective_placements(project, "screen-camera", "16:9")
        self.assertEqual([source for source, _ in placements], ["screen", "camera"])


if __name__ == "__main__":
    unittest.main()
