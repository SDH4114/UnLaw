"""Export of Studio projects (`capture_export.py`): geometry, ffmpeg commands, files, with fake tools."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_command_paths import FAKE_FFMPEG  # noqa: E402
from unlawful import capture_export, capture_project  # noqa: E402
from unlawful.config import ensure_layout, storage_path  # noqa: E402

FAKE_FFPROBE = """import json, os
name = os.path.basename(sys.argv[-1])
sizes = {"screen": (3600, 2338), "camera": (1920, 1080)}
kind = next((key for key in sizes if name.startswith(key)), None)
streams = [{"codec_type": "audio", "codec_name": "aac"}]
if kind:
    streams.insert(0, {"codec_type": "video", "codec_name": "h264", "width": sizes[kind][0], "height": sizes[kind][1]})
print(json.dumps({"format": {"duration": "10.0"}, "streams": streams}))
"""


def decode_png(data: bytes) -> tuple[int, int, list[bytes]]:
    """Width, height and rows (filter byte removed) of a PNG written with filter 0."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, idat, width, height, channels = 8, b"", 0, 0, 1
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        if kind == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
            channels = {0: 1, 6: 4}[body[9]]
        elif kind == b"IDAT":
            idat += body
        offset += 12 + length
    raw = zlib.decompress(idat)
    stride = width * channels + 1
    rows = [raw[y * stride + 1 : (y + 1) * stride] for y in range(height)]
    assert all(raw[y * stride] == 0 for y in range(height))
    return width, height, rows


PNG_1x1 = capture_export.png_rgba(1, 1, lambda x, y: (255, 255, 255, 255)) if hasattr(capture_export, "png_rgba") else b""


class ExportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.root / "home").mkdir()
        environment = patch.dict(
            os.environ,
            {
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        ensure_layout()
        self.ffmpeg_log = self.tool("ffmpeg", FAKE_FFMPEG)
        self.tool("ffprobe", FAKE_FFPROBE)

    def tool(self, name: str, body: str) -> Path:
        log = self.root / f"{name}.log"
        script = self.bin / name
        script.write_text(
            f"#!{sys.executable}\nimport sys\nopen({str(log)!r}, 'a').write('|'.join(sys.argv[1:]) + '\\n')\n{body}",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return log

    def calls(self) -> list[list[str]]:
        return (
            [line.split("|") for line in self.ffmpeg_log.read_text().splitlines()]
            if self.ffmpeg_log.exists()
            else []
        )

    def make_project(
        self, *, camera: bool = True, segments: int = 1, mode: str = "screen"
    ) -> Path:
        setup = capture_project.default_setup({})
        setup["sources"][1]["enabled"] = camera
        folder = capture_project.create_project(
            "screen-camera" if camera else mode, setup, {}
        )
        project = capture_project.read_project(folder)
        project["mode"] = mode
        project["segments"] = []
        for number in range(1, segments + 1):
            files, starts = {}, {}
            if mode == "screen":
                files["screen"] = f"media/screen-{number:03d}.mp4"
                starts["screen"] = 0.0
            if camera:
                files["camera"] = f"media/camera-{number:03d}.mp4"
                starts["camera"] = 0.31
            files["mic"] = f"media/mic-{number:03d}.flac"
            starts["mic"] = 0.94
            for track, relative in files.items():
                (folder / relative).write_bytes(f"{track}{number}".encode())
            project["segments"].append(
                {
                    "duration": 10.0,
                    "files": files,
                    "starts": starts,
                    "info": {
                        "screen": {"width": 3600, "height": 2338, "audio": True},
                        "camera": {"width": 1920, "height": 1080, "audio": False},
                    },
                }
            )
        project["duration"] = 10.0 * segments
        project["state"] = "ready"
        if mode == "audio":
            project["audio_format"] = "mp3"
        capture_project.write_project(folder, project)
        return folder

    def settings(self, folder: Path, **overrides: object) -> dict:
        return capture_export.export_settings(
            capture_project.read_project(folder), {}, overrides
        )

    def graph(self, argv: list[str]) -> str:
        return argv[argv.index("-filter_complex") + 1]


class GeometryTests(ExportTestCase):
    def test_mask_alpha(self) -> None:
        width, height, rows = decode_png(capture_export.mask_png(100, 60, 30))
        self.assertEqual((width, height), (100, 60))
        self.assertEqual(rows[30][50], 255)
        self.assertEqual(rows[0][0], 0)
        self.assertTrue(any(0 < value < 255 for row in rows[:30] for value in row), "anti-aliased corner edge")
        self.assertTrue(
            all(
                value == 255
                for row in decode_png(capture_export.mask_png(10, 6, 0))[2]
                for value in row
            )
        )

    def test_frame_has_a_border_ring_and_a_transparent_middle(self) -> None:
        data, pad = capture_export.frame_png(100, 60, 0, 4, "#ff0000", True)
        width, height, rows = decode_png(data)
        self.assertEqual((width, height), (100 + 2 * pad, 60 + 2 * pad))
        middle = rows[pad + 30][4 * (pad + 50) : 4 * (pad + 50) + 4]
        self.assertEqual(middle[3], 0, "the source shows through")
        ring = rows[pad + 30][4 * (pad + 1) : 4 * (pad + 1) + 4]
        self.assertEqual(tuple(ring), (255, 0, 0, 255))
        below = rows[pad + 60 + 2][4 * (pad + 50) : 4 * (pad + 50) + 4]
        self.assertTrue(0 < below[3] < 255, "a soft shadow under the box")

    def test_16x9_camera_and_screen_geometry(self) -> None:
        folder = self.make_project()
        project = capture_project.read_project(folder)
        settings = self.settings(folder, canvas="16:9", height=1440, fps=60)
        interval = {"segment": 0, "start": 0.0, "length": 2.0, "scene": "screen-camera"}
        argv = capture_export.interval_argv(
            folder, project, interval, settings, Path("o.mp4"), folder / "cache"
        )
        graph = self.graph(argv)
        self.assertIn("scale=2218:1440", graph)
        self.assertIn("overlay=171:0", graph)
        self.assertIn("hflip", graph)
        self.assertIn("crop=614:346", graph)
        self.assertIn("overlay=0:1094", graph)
        self.assertIn("color=c=0x000000:s=2560x1440:r=60", argv)
        self.assertEqual(argv[argv.index("-b:v") + 1], "24330240")
        self.assertIn("h264_videotoolbox", argv)
        self.assertEqual(
            argv[argv.index("-itsoffset") + 1],
            "0.310",
            "the camera started 0.31 s after the screen",
        )
        self.assertEqual(argv[argv.index("-t") + 1], "2.000")
        self.assertEqual(argv[-1], "o.mp4")

    def test_seek_into_a_later_interval(self) -> None:
        folder = self.make_project()
        project = capture_project.read_project(folder)
        settings = self.settings(folder)
        interval = {"segment": 0, "start": 4.0, "length": 6.0, "scene": "screen-camera"}
        argv = capture_export.interval_argv(
            folder, project, interval, settings, Path("o.mp4"), folder / "cache"
        )
        seeks = [argv[index + 1] for index, value in enumerate(argv) if value == "-ss"]
        self.assertEqual(
            seeks, ["4.000", "3.690"], "screen from 4 s, camera from 4 - 0.31 s"
        )
        self.assertNotIn("-itsoffset", argv)

    def test_9x16_stack_crops_around_focus_and_rounds_corners(self) -> None:
        folder = self.make_project()
        project = capture_project.read_project(folder)
        project["layouts"]["9:16"]["screen-camera"]["placements"]["camera"][
            "radius"
        ] = 0.1
        settings = self.settings(folder, canvas="9:16", height=1080)
        interval = {"segment": 0, "start": 0.0, "length": 2.0, "scene": "screen-camera"}
        argv = capture_export.interval_argv(
            folder, project, interval, settings, Path("o.mp4"), folder / "cache"
        )
        graph = self.graph(argv)
        self.assertIn("crop=1080:768:143:0", graph)
        self.assertIn("crop=1080:1152:347:0", graph)
        self.assertIn("overlay=0:768", graph)
        self.assertIn("alphamerge", graph)
        masks = list((folder / "cache").glob("mask-*.png"))
        self.assertEqual(len(masks), 1)
        self.assertEqual(decode_png(masks[0].read_bytes())[:2], (1080, 768))

    def test_blur_background_for_the_screen_scene_in_vertical(self) -> None:
        folder = self.make_project()
        project = capture_project.read_project(folder)
        settings = self.settings(folder, canvas="9:16", height=1080)
        interval = {"segment": 0, "start": 0.0, "length": 2.0, "scene": "screen"}
        graph = self.graph(
            capture_export.interval_argv(
                folder, project, interval, settings, Path("o.mp4"), folder / "cache"
            )
        )
        self.assertIn("boxblur", graph)
        self.assertNotIn("hflip", graph, "no camera in the screen scene")

    def test_audio_mixes_system_sound_and_mic_with_offsets(self) -> None:
        folder = self.make_project()
        project = capture_project.read_project(folder)
        argv = capture_export.audio_argv(
            folder, project, 0, self.settings(folder), Path("a.wav")
        )
        graph = self.graph(argv)
        self.assertIn("adelay=940:all=1", graph)
        self.assertIn("amix=inputs=2:normalize=0", graph)
        self.assertIn("atrim=0:10.000", graph)
        project["audio"]["mic"]["muted"] = True
        project["audio"]["system"]["muted"] = True
        self.assertIsNone(
            capture_export.audio_argv(
                folder, project, 0, self.settings(folder), Path("a.wav")
            )
        )

    def test_settings_validate_and_prefill(self) -> None:
        folder = self.make_project()
        self.assertEqual(self.settings(folder)["height"], 1440)
        self.assertEqual(
            self.settings(folder, canvas="9:16")["height"],
            1080,
            "vertical defaults to 1080",
        )
        with self.assertRaises(capture_project.ProjectError):
            self.settings(folder, height=720)
        project = capture_project.read_project(folder)
        project["export"]["canvas"] = "4:5"
        project["export"]["height"] = 2160
        settings = capture_export.export_settings(project, {"canvas": "16:9"}, {})
        self.assertEqual(
            (settings["canvas"], settings["height"]),
            ("4:5", 2160),
            "the project's last export wins",
        )


class ExportRunTests(ExportTestCase):
    def test_export_records_itself_and_never_overwrites(self) -> None:
        folder = self.make_project(segments=2)
        settings = self.settings(folder)
        first = capture_export.export_project(folder, settings)
        second = capture_export.export_project(folder, settings)
        self.assertEqual(first.parent, storage_path("captures", "recordings"))
        self.assertEqual(first.name, f"{folder.name} 16x9.mov")
        self.assertEqual(second.name, f"{folder.name} 16x9 2.mov")
        project = capture_project.read_project(folder)
        self.assertEqual(
            [item["path"] for item in project["exports"]], [str(first), str(second)]
        )
        self.assertEqual(project["export"]["canvas"], "16:9")
        status = capture_export.read_export_status()
        self.assertEqual(
            (status["phase"], status["percent"], status["output"]),
            ("done", 100, str(second)),
        )
        self.assertEqual(
            list((folder / "cache" / "render").glob("*")), [], "chunks are removed"
        )
        concat = [call for call in self.calls() if "concat" in call]
        self.assertTrue(concat)
        self.assertEqual(
            sum(
                1
                for call in self.calls()
                if "color=c=0x000000:s=2560x1440:r=60" in call
            ),
            4,
            "two scenes-free intervals x two exports",
        )

    def test_source_canvas_copies_the_screen(self) -> None:
        folder = self.make_project(segments=2)
        out = capture_export.export_project(
            folder, self.settings(folder, canvas="source", container="mp4")
        )
        self.assertEqual(out.name, f"{folder.name} source.mp4")
        self.assertFalse(
            any(
                "-filter_complex" in call and "overlay" in "|".join(call)
                for call in self.calls()
            )
        )
        listing = [call for call in self.calls() if "concat" in call and "-c" in call]
        self.assertTrue(listing, "segments joined by stream copy")

    def test_paths_with_spaces_cyrillic_and_quotes(self) -> None:
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "Студия 'x'")}):
            ensure_layout()
            folder = self.make_project(segments=2)
            out = capture_export.export_project(folder, self.settings(folder))
            self.assertTrue(out.is_file())
            self.assertIn("Студия 'x'", str(out))

    def test_a_failed_export_leaves_no_partial_file(self) -> None:
        folder = self.make_project()
        before = (folder / "project.json").read_bytes()
        with (
            patch.dict(os.environ, {"FAKE_FFMPEG_FAIL": "overlay"}),
            self.assertRaises(capture_export.ExportError),
        ):
            capture_export.export_project(folder, self.settings(folder))
        recordings = storage_path("captures", "recordings")
        self.assertEqual([path.name for path in recordings.iterdir()], [])
        self.assertEqual((folder / "project.json").read_bytes(), before)
        self.assertEqual(capture_export.read_export_status()["phase"], "failed")

    def test_delete_sources_moves_the_project_to_the_trash(self) -> None:
        folder = self.make_project()
        out = capture_export.export_project(
            folder, self.settings(folder, delete_sources=True)
        )
        self.assertTrue(out.is_file())
        self.assertFalse(folder.exists())
        self.assertTrue(
            (self.root / "home" / ".Trash" / folder.name / "project.json").is_file()
        )

    def test_a_trash_that_fails_keeps_the_export(self) -> None:
        folder = self.make_project()
        with patch.object(capture_export, "_trash", side_effect=OSError("no Trash access")):
            out = capture_export.export_project(folder, self.settings(folder, delete_sources=True))
        self.assertTrue(out.is_file())
        status = capture_export.read_export_status()
        self.assertEqual(status["phase"], "done")
        self.assertIn("no Trash access", status["warning"])
        self.assertTrue(folder.exists(), "the project stays when it could not be moved")

    def test_a_dead_export_is_not_reported_as_running(self) -> None:
        capture_export.write_json_atomic(
            capture_export.export_status_file(), {"project": "/p", "phase": "running", "pid": 2**22 + 12345}
        )
        self.assertEqual(capture_export.read_export_status()["phase"], "idle")
        capture_export.write_json_atomic(
            capture_export.export_status_file(), {"project": "/p", "phase": "running", "pid": os.getpid()}
        )
        self.assertEqual(capture_export.read_export_status()["phase"], "running")

    def test_a_failed_copy_leaves_no_partial_target(self) -> None:
        temporary = self.root / ".part"
        temporary.write_bytes(b"x" * 10)
        target = self.root / "out" / "video.mov"
        target.parent.mkdir()

        def broken_copy(source, out):
            out.write(b"half")
            raise OSError("disk full")

        with (
            patch.object(capture_export.os, "link", side_effect=OSError(18, "cross-device")),
            patch.object(capture_export.shutil, "copyfileobj", side_effect=broken_copy),
            self.assertRaises(OSError),
        ):
            capture_export._publish(temporary, target)
        self.assertFalse(target.exists())

    def test_the_failure_message_comes_from_this_run(self) -> None:
        log = self.root / "logs" / "export.log"
        log.parent.mkdir()
        log.write_text("$ ffmpeg old\nOld error from yesterday\n")
        self.tool("ffmpeg", "raise SystemExit(3)\n")
        with self.assertRaises(capture_export.ExportError) as caught:
            capture_export._run_ffmpeg(["ffmpeg", "-i", "x"], log, "joining")
        self.assertNotIn("yesterday", str(caught.exception))
        self.assertIn("exit 3", str(caught.exception))

    def test_a_symlinked_cache_is_refused_and_nothing_behind_it_is_deleted(self) -> None:
        folder = self.make_project()
        outside = self.root / "elsewhere"
        (outside / "render").mkdir(parents=True)
        (outside / "render" / "keep.txt").write_text("mine")
        shutil.rmtree(folder / "cache", ignore_errors=True)
        (folder / "cache").symlink_to(outside)
        with self.assertRaises(capture_export.ExportError):
            capture_export.export_project(folder, self.settings(folder))
        self.assertEqual((outside / "render" / "keep.txt").read_text(), "mine")

    def edit(self, folder: Path, clips: list, tracks: list | None = None) -> dict:
        project = capture_project.read_project(folder)
        edit = capture_project.default_edit(project)
        if tracks is not None:
            edit["tracks"] = tracks
        edit["clips"] = clips
        project["edit"] = edit
        capture_project.write_project(folder, project)
        return project

    @staticmethod
    def clip(ident: str, track: str, source: str, start: float, begin: float, end: float, link: str = "", **more: object) -> dict:
        item = {"id": ident, "track": track, "source": source, "start": start, "in": begin, "out": end, "link": link}
        if track.startswith("a"):
            item.update(name="", asset="", volume=1.0, fade_in=0.0, fade_out=0.0)
        item.update(more)
        return item

    def recording(self, number: int, start: float, begin: float, end: float) -> list[dict]:
        link = f"l{number}"
        return [self.clip(f"v{number}", "v1", "recording", start, begin, end, link),
                self.clip(f"m{number}", "a1", "mic", start, begin, end, link),
                self.clip(f"s{number}", "a2", "system", start, begin, end, link)]

    def test_an_edit_cuts_the_picture_and_the_sound(self) -> None:
        folder = self.make_project(segments=2)
        (folder / "assets" / "cap.png").write_bytes(PNG_1x1)
        (folder / "assets" / "song.m4a").write_bytes(b"song")
        self.edit(folder, [
            *self.recording(1, 0.0, 12.0, 14.0), *self.recording(2, 2.0, 1.0, 3.0),
            self.clip("w1", "s1", "caption", 1.0, 0.0, 1.0, text="Привет", asset="cap.png"),
            self.clip("x1", "a3", "asset", 0.5, 0.0, 2.0, name="Song", asset="song.m4a", volume=0.4, fade_in=0.5, fade_out=0.5),
        ])
        out = capture_export.export_project(folder, self.settings(folder))
        calls = self.calls()
        chunks = [call for call in calls if any(arg.endswith(".mp4") and "chunk-" in arg for arg in call[-1:])]
        self.assertEqual(len(chunks), 2, "one chunk per clip")
        first = chunks[0]
        self.assertIn("2.000", first[first.index("-ss") + 1], "the first clip starts 2 s into part 2")
        self.assertIn("enable='between(t,1.000,2.000)'", self.graph(first), "the caption shows in its second")
        self.assertIn(str(folder / "assets" / "cap.png"), first)
        self.assertNotIn("cap.png", " ".join(chunks[1]), "the second clip has no caption")
        cut = next(call for call in calls if any("amix=inputs=5" in arg for arg in call))
        graph = self.graph(cut)
        self.assertEqual(graph.count("atrim=start=12.000000:end=14.000000"), 2, "the microphone and the Mac sound are cut alike")
        self.assertIn("adelay=2000:all=1", graph, "the second clip plays 2 s into the output")
        self.assertIn("afade=t=out:st=1.500:d=0.500", graph)
        self.assertIn("adelay=500:all=1", graph)
        self.assertIn("volume=0.4", graph)
        # One input per clip: two branches of one input into amix stall ffmpeg (it waits forever).
        self.assertEqual(cut.count(str(folder / "cache" / "render" / "mic.wav")), 2)
        self.assertNotIn("[0:a]atrim", graph.split(";", 1)[1])
        srt = out.with_suffix(".srt")
        self.assertEqual(srt.read_text(encoding="utf-8"), "1\n00:00:01,000 --> 00:00:02,000\nПривет\n")

    def test_the_microphone_and_the_mac_sound_are_separate_tracks(self) -> None:
        folder = self.make_project()
        project = self.edit(folder, self.recording(1, 0.0, 1.0, 3.0))
        tracks = project["edit"]["tracks"]
        tracks[4]["muted"] = True
        self.edit(folder, self.recording(1, 0.0, 1.0, 3.0), tracks)
        capture_export.export_project(folder, self.settings(folder))
        calls = self.calls()
        mixes = [call for call in calls if call[-1].endswith(("mic.wav", "system.wav"))]
        self.assertEqual([Path(call[-1]).name for call in mixes], ["mic.wav"], "a muted Mac sound is not even prepared")
        part = next(call for call in calls if call[-1].endswith("mic-000.wav"))
        self.assertIn(str(folder / "media" / "mic-001.flac"), part)
        self.assertNotIn(str(folder / "media" / "screen-001.mp4"), part, "the microphone file holds only the microphone")

    def test_a_gap_on_the_timeline_is_black(self) -> None:
        folder = self.make_project()
        self.edit(folder, self.recording(1, 1.5, 0.0, 2.0))
        capture_export.export_project(folder, self.settings(folder))
        chunks = [call for call in self.calls() if "chunk-" in call[-1]]
        self.assertEqual(len(chunks), 2)
        gap = chunks[0]
        self.assertTrue(any(arg.startswith("color=c=0x000000") for arg in gap))
        self.assertEqual(gap[gap.index("-t") + 1], "1.500")
        self.assertNotIn(str(folder / "media" / "screen-001.mp4"), gap)

    def test_an_undrawn_caption_stops_the_export_with_a_reason(self) -> None:
        folder = self.make_project()
        self.edit(folder, [*self.recording(1, 0.0, 0.0, 3.0), self.clip("w1", "s1", "caption", 1.0, 0.0, 1.0, text="hi", asset="gone.png")])
        with self.assertRaises(capture_export.ExportError) as caught:
            capture_export.export_project(folder, self.settings(folder))
        self.assertIn("Edit tab", str(caught.exception))
        # A line transcribed but never drawn (exported before the page drew it) is not silently left out.
        self.edit(folder, [*self.recording(1, 0.0, 0.0, 3.0), self.clip("w1", "s1", "caption", 1.0, 0.0, 1.0, text="hi", asset="")])
        with self.assertRaises(capture_export.ExportError) as caught:
            capture_export.export_project(folder, self.settings(folder))
        self.assertIn("Edit tab", str(caught.exception))

    def test_an_edited_audio_project_exports_only_sound(self) -> None:
        folder = self.make_project(camera=False, mode="audio")
        self.edit(folder, [self.clip("a", "a1", "mic", 0.0, 2.0, 4.0), self.clip("b", "a1", "mic", 2.0, 6.0, 7.0)])
        out = capture_export.export_project(folder, self.settings(folder))
        self.assertEqual(out.suffix, ".mp3")
        mix = next(call for call in self.calls() if any("amix=inputs=2" in arg for arg in call))
        self.assertIn("apad=whole_dur=3.000000,atrim=0:3.000000", self.graph(mix), "the output ends with its last clip")
        for call in self.calls():
            if "-filter_complex" in call:
                self.assertNotRegex(self.graph(call), r"apad[,\[]", "a bare apad never ends and can hang ffmpeg")

    def test_an_empty_edit_says_so(self) -> None:
        folder = self.make_project()
        self.edit(folder, [])
        with self.assertRaises(capture_export.ExportError) as caught:
            capture_export.export_project(folder, self.settings(folder))
        self.assertIn("empty", str(caught.exception))

    def test_an_edit_as_recorded_reencodes_the_screen(self) -> None:
        folder = self.make_project()
        self.edit(folder, [*self.recording(1, 0.0, 1.0, 2.0), *self.recording(2, 2.0, 3.0, 4.0)])
        capture_export.export_project(folder, self.settings(folder, canvas="source"))
        chunks = [call for call in self.calls() if "chunk-" in call[-1]]
        self.assertIn(str(folder / "media" / "screen-001.mp4"), chunks[0])
        self.assertIn("scale=3600:2338", self.graph(chunks[0]))
        self.assertTrue(any(arg.startswith("color=c=0x000000:s=3600x2338") for arg in chunks[1]), "a gap in a source export is black at the screen's size")

    def test_zero_length_segments_export(self) -> None:
        folder = self.make_project(segments=2)
        project = capture_project.read_project(folder)
        project["segments"][1]["duration"] = 0.004
        capture_project.write_project(folder, project)
        capture_export.export_project(folder, self.settings(folder))
        self.assertEqual(
            sum(
                1
                for call in self.calls()
                if any(arg.startswith("color=c=") for arg in call)
            ),
            1,
        )

    def drop_track(self, folder: Path, segment: int, track: str) -> None:
        project = capture_project.read_project(folder)
        relative = project["segments"][segment]["files"].pop(track)
        project["segments"][segment]["starts"].pop(track, None)
        (folder / relative).unlink()
        project["state"] = "incomplete"
        capture_project.write_project(folder, project)

    def test_a_segment_without_a_track_exports_without_it(self) -> None:
        # A screen recorder that hung (stop --force) or a display that went away leaves the
        # second part without a screen: that part shows what it has instead of crashing.
        folder = self.make_project(segments=2)
        self.drop_track(folder, 1, "screen")
        capture_export.export_project(folder, self.settings(folder))
        renders = [call for call in self.calls() if any(arg.startswith("color=c=") for arg in call)]
        self.assertEqual(len(renders), 2)
        self.assertIn("screen-001.mp4", "|".join(renders[0]))
        self.assertNotIn("screen-002.mp4", "|".join(renders[1]))
        self.assertIn("camera-002.mp4", "|".join(renders[1]))

    def test_source_canvas_refuses_a_part_without_the_screen(self) -> None:
        folder = self.make_project(segments=2)
        self.drop_track(folder, 1, "screen")
        with self.assertRaises(capture_export.ExportError) as caught:
            capture_export.export_project(folder, self.settings(folder, canvas="source"))
        self.assertIn("part 2", str(caught.exception))

    def test_a_recording_shorter_than_a_frame_says_so(self) -> None:
        folder = self.make_project(segments=1)
        project = capture_project.read_project(folder)
        project["segments"][0]["duration"] = 0.004
        capture_project.write_project(folder, project)
        with self.assertRaises(capture_export.ExportError) as caught:
            capture_export.export_project(folder, self.settings(folder))
        self.assertIn("shorter than one frame", str(caught.exception))
        self.assertFalse(self.calls(), "no ffmpeg run for nothing")

    def test_a_symlinked_asset_is_refused(self) -> None:  # Review Focus 5
        folder = self.make_project(segments=1)
        project = capture_project.read_project(folder)
        project["sources"].append({"id": "image-1", "kind": "image", "enabled": True, "asset": "logo.png"})
        scene = project["layouts"]["16:9"]["screen-camera"]
        scene["placements"]["image-1"] = dict(scene["placements"]["camera"])
        outside = self.root / "outside.png"
        outside.write_bytes(b"\x89PNG elsewhere")
        (folder / "assets").mkdir(exist_ok=True)
        (folder / "assets" / "logo.png").symlink_to(outside)
        capture_project.write_project(folder, project)
        with self.assertRaises(capture_export.ExportError) as caught:
            capture_export.export_project(folder, self.settings(folder))
        self.assertIn("symbolic link", str(caught.exception))
        self.assertFalse(any(str(outside) in "|".join(call) for call in self.calls()))

    def test_audio_projects_export_audio(self) -> None:
        folder = self.make_project(camera=False, mode="audio")
        out = capture_export.export_project(folder, self.settings(folder))
        self.assertEqual(out.name, f"{folder.name}.mp3")
        self.assertIn("libmp3lame", self.calls()[-1])


@unittest.skipUnless(
    os.environ.get("UNLAW_REAL_MEDIA") == "1",
    "opt-in: real ffmpeg on synthetic sources",
)
class RealFfmpegTests(unittest.TestCase):
    def test_real_ffmpeg_export(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        self.assertIsNotNone(ffmpeg)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        with patch.dict(
            os.environ, {"HOME": str(root), "XDG_CONFIG_HOME": str(root / "config")}
        ):
            ensure_layout()
            setup = capture_project.default_setup({})
            setup["sources"][1]["enabled"] = True
            folder = capture_project.create_project("screen-camera", setup, {})
            media = folder / "media"

            def make(args: list[str]) -> None:
                subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],
                    check=True,
                )

            make(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=s=3600x2338:r=60:d=2",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=f=440:d=2",
                    "-c:v",
                    "h264_videotoolbox",
                    "-b:v",
                    "20M",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(media / "screen-001.mp4"),
                ]
            )
            make(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=s=1920x1080:r=30:d=1.7",
                    "-c:v",
                    "h264_videotoolbox",
                    "-b:v",
                    "6M",
                    str(media / "camera-001.mp4"),
                ]
            )
            make(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=f=220:d=1.8",
                    "-c:a",
                    "flac",
                    str(media / "mic-001.flac"),
                ]
            )
            project = capture_project.read_project(folder)
            project["segments"] = [
                {
                    "duration": 2.0,
                    "files": {
                        "screen": "media/screen-001.mp4",
                        "camera": "media/camera-001.mp4",
                        "mic": "media/mic-001.flac",
                    },
                    "starts": {"screen": 0.0, "camera": 0.3, "mic": 0.2},
                }
            ]
            project["events"].append({"t": 1.0, "scene": "camera"})
            project["layouts"]["16:9"]["screen-camera"]["placements"]["camera"][
                "radius"
            ] = 0.5
            project["layouts"]["16:9"]["screen-camera"]["placements"]["camera"][
                "border"
            ] = {"width": 6, "color": "#ffc933"}
            project["layouts"]["16:9"]["screen-camera"]["placements"]["camera"][
                "shadow"
            ] = True
            project["duration"] = 2.0
            capture_project.write_project(folder, project)
            for canvas, height, size in (
                ("16:9", 1440, "2560x1440"),
                ("9:16", 1080, "1080x1920"),
            ):
                settings = capture_export.export_settings(
                    project, {}, {"canvas": canvas, "height": height, "fps": 60}
                )
                out = capture_export.export_project(folder, settings)
                probe = json.loads(
                    subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-show_entries",
                            "stream=codec_type,width,height,r_frame_rate:format=duration",
                            "-of",
                            "json",
                            str(out),
                        ],
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout
                )
                video = next(
                    stream
                    for stream in probe["streams"]
                    if stream["codec_type"] == "video"
                )
                self.assertEqual(
                    (f"{video['width']}x{video['height']}", video["r_frame_rate"]),
                    (size, "60/1"),
                )
                self.assertTrue(
                    any(stream["codec_type"] == "audio" for stream in probe["streams"])
                )
                self.assertAlmostEqual(
                    float(probe["format"]["duration"]), 2.0, delta=0.1
                )


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.environ.get("UNLAW_REAL_MEDIA") == "1", "opt-in: real ffmpeg on synthetic sources")
class RealEditTests(unittest.TestCase):
    def test_real_edited_export_with_captions_music_and_srt(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        with patch.dict(os.environ, {"HOME": str(root), "XDG_CONFIG_HOME": str(root / "config")}):
            ensure_layout()
            folder = capture_project.create_project("screen", capture_project.default_setup({}), {})

            def make(*args: str) -> None:
                subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)

            make("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=4", "-f", "lavfi", "-i", "sine=f=440:d=4",
                 "-c:v", "h264_videotoolbox", "-b:v", "4M", "-c:a", "aac", "-shortest", str(folder / "media" / "screen-001.mp4"))
            make("-f", "lavfi", "-i", "sine=f=220:d=4", "-c:a", "flac", str(folder / "media" / "mic-001.flac"))
            make("-f", "lavfi", "-i", "sine=f=660:d=3", "-c:a", "aac", str(folder / "assets" / "song.m4a"))
            (folder / "assets" / "cap.png").write_bytes(capture_export.png_rgba(400, 60, lambda x, y: (255, 255, 255, 200)))
            project = capture_project.read_project(folder)
            project["segments"] = [{"duration": 4.0, "files": {"screen": "media/screen-001.mp4", "mic": "media/mic-001.flac"},
                                    "starts": {"screen": 0.0, "mic": 0.0}}]
            project["duration"] = 4.0
            edit = capture_project.default_edit(project)

            def clip(ident: str, track: str, source: str, start: float, begin: float, end: float, link: str = "", **more: object) -> dict:
                item = {"id": ident, "track": track, "source": source, "start": start, "in": begin, "out": end, "link": link}
                if track.startswith("a"):
                    item.update(name="", asset="", volume=1.0, fade_in=0.0, fade_out=0.0)
                item.update(more)
                return item

            edit["clips"] = [
                clip("v1", "v1", "recording", 0.0, 0.5, 1.5, "l1"), clip("m1", "a1", "mic", 0.0, 0.5, 1.5, "l1"), clip("s1", "a2", "system", 0.0, 0.5, 1.5, "l1"),
                clip("v2", "v1", "recording", 1.0, 2.5, 3.5, "l2"), clip("m2", "a1", "mic", 1.0, 2.5, 3.5, "l2"),
                clip("w1", "s1", "caption", 0.5, 0.0, 1.0, text="hello", asset="cap.png"),
                clip("t1", "t1", "text", 0.0, 0.0, 1.0, text="title", asset="cap.png", x=0.5, y=0.2, w=0.4, color="#ffffff", background=""),
                clip("x1", "a3", "asset", 0.2, 0.0, 1.5, name="Song", asset="song.m4a", volume=0.5, fade_in=0.3, fade_out=0.3),
            ]
            project["edit"] = edit
            capture_project.write_project(folder, project)
            for canvas in ("16:9", "source"):
                settings = capture_export.export_settings(project, {}, {"canvas": canvas, "height": 1080, "fps": 30})
                out = capture_export.export_project(folder, settings)
                duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                                                capture_output=True, text=True, check=True).stdout)
                self.assertAlmostEqual(duration, 2.0, delta=0.1, msg=canvas)
                self.assertIn("00:00:00,500 --> 00:00:01,500", out.with_suffix(".srt").read_text())


class ProxyTests(ExportTestCase):
    """Light copies for the Edit tab (Resolve's optimized media): 1080p H.264 with a keyframe a second, AAC sound."""

    def test_proxies_are_made_once_per_file(self) -> None:
        from unlawful import capture

        folder = self.make_project()
        files = capture.make_proxies(folder)["files"]
        self.assertEqual(files, {
            "media/screen-001.mp4": {"video": "cache/proxy/screen-001.mp4", "audio": "cache/proxy/screen-001-system.m4a"},
            "media/camera-001.mp4": {"video": "cache/proxy/camera-001.mp4"},
            "media/mic-001.flac": {"audio": "cache/proxy/mic-001.m4a"},
        })
        for entry in files.values():
            for relative in entry.values():
                self.assertTrue((folder / relative).is_file(), relative)
        calls = [call for call in self.calls() if "-i" in call]
        screen = next(call for call in calls if call[-1].endswith("screen-001.mp4.part.mp4"))
        self.assertIn("-an", screen)
        self.assertIn("h264_videotoolbox", screen)
        self.assertIn("expr:gte(t,n_forced*1)", screen, "a keyframe every second: seeking is instant")
        self.assertIn("scale=-2:'min(1080,ih)'", screen[screen.index("-vf") + 1])
        sound = next(call for call in calls if call[-1].endswith("screen-001-system.m4a.part.m4a"))
        self.assertIn("-vn", sound)
        self.assertNotIn(str(folder / "media" / "mic-001.flac"), screen)
        count = len(self.calls())
        self.assertEqual(capture.make_proxies(folder)["files"], files)
        self.assertEqual(len(self.calls()), count, "up-to-date proxies are not made again")

    def test_a_screen_without_sound_has_no_sound_proxy(self) -> None:
        from unlawful import capture

        folder = self.make_project(camera=False)
        project = capture_project.read_project(folder)
        project["segments"][0]["info"]["screen"]["audio"] = False
        capture_project.write_project(folder, project)
        files = capture.make_proxies(folder)["files"]
        self.assertEqual(files["media/screen-001.mp4"], {"video": "cache/proxy/screen-001.mp4"})

    def test_a_symlinked_cache_is_refused(self) -> None:
        from unlawful import capture

        folder = self.make_project()
        outside = self.root / "elsewhere"
        outside.mkdir()
        (folder / "cache").rename(self.root / "old-cache") if (folder / "cache").exists() else None
        (folder / "cache").symlink_to(outside)
        with self.assertRaises(capture.CaptureError):
            capture.make_proxies(folder)
        self.assertEqual(list(outside.iterdir()), [])


class TranscribeTests(ExportTestCase):
    def test_lines_come_back_on_the_recording_clock(self) -> None:
        from unlawful import capture

        folder = self.make_project(segments=2)
        log = self.tool("ul", """import json
if "mic-002" in sys.argv[3]:
    print(json.dumps({"language": "ru", "segments": [{"start": 1.0, "end": 2.5, "text": " Привет\\u0007 мир "}, {"start": 9.5, "end": 12.0, "text": "end"}]}))
else:
    print(json.dumps({"language": "ru", "segments": [{"start": 0.0, "end": 1.0, "text": "one"}, {"start": 3.0, "end": 3.0, "text": "empty"}]}))
""")
        with patch.dict(os.environ, {"UNLAW_BIN": str(self.bin / "ul")}):
            data = capture.transcribe_project(folder, "ru", None)
        self.assertEqual(data["language"], "ru")
        # The microphone starts 0.94 s into each 10 s part; a line that starts past the part's end is dropped.
        self.assertEqual(
            [(line["in"], line["out"], line["text"]) for line in data["captions"]],
            [(0.94, 1.94, "one"), (11.94, 13.44, "Привет мир")],
        )
        self.assertIn("-l|ru", log.read_text())

    def test_a_speech_model_is_picked_when_several_are_downloaded(self) -> None:
        # ul lm refuses to guess between two speech models with no default; the Edit tab must still work.
        from unlawful import capture

        folder = self.make_project()
        models = [
            {"id": "big/chat", "type": "text", "format": "mlx", "default": True, "runnable": True},
            {"id": "handy/whisper-gguf", "type": "stt", "format": "gguf", "default": False, "runnable": True},
            {"id": "mlx-community/whisper-large-v3-turbo", "type": "stt", "format": "mlx", "default": False, "runnable": True},
            {"id": "broken/stt", "type": "stt", "format": "mlx", "default": False, "runnable": False},
        ]
        log = self.tool("ul", f"""import json
if sys.argv[1:3] == ["lm", "list"]:
    print(json.dumps({models!r}))
else:
    print(json.dumps({{"language": "en", "segments": [{{"start": 0.0, "end": 1.0, "text": "hi"}}]}}))
""")
        with patch.dict(os.environ, {"UNLAW_BIN": str(self.bin / "ul")}):
            listed = capture.speech_models()
            data = capture.transcribe_project(folder)
        self.assertEqual([item["id"] for item in listed], ["mlx-community/whisper-large-v3-turbo", "handy/whisper-gguf"])
        self.assertEqual(data["model"], "mlx-community/whisper-large-v3-turbo")
        self.assertIn("-m|mlx-community/whisper-large-v3-turbo", log.read_text())
        # A default speech model wins; a model named by the user is passed as it is.
        models[1]["default"] = True
        self.tool("ul", f"""import json
if sys.argv[1:3] == ["lm", "list"]:
    print(json.dumps({models!r}))
else:
    print(json.dumps({{"segments": []}}))
""")
        with patch.dict(os.environ, {"UNLAW_BIN": str(self.bin / "ul")}):
            self.assertEqual(capture.speech_models()[0]["id"], "handy/whisper-gguf")
            self.assertEqual(capture.transcribe_project(folder, None, "my/model")["model"], "my/model")

    def test_without_a_speech_model_the_error_says_how_to_get_one(self) -> None:
        from unlawful import capture

        folder = self.make_project()
        self.tool("ul", "import json\nprint(json.dumps([{'id': 'a/chat', 'type': 'text', 'format': 'mlx', 'default': True, 'runnable': True}]))\n")
        with patch.dict(os.environ, {"UNLAW_BIN": str(self.bin / "ul")}), self.assertRaises(capture.CaptureError) as caught:
            capture.transcribe_project(folder)
        self.assertIn("ul lm pull mlx-community/whisper-large-v3-turbo", str(caught.exception))

    def test_a_failing_recogniser_reports_why(self) -> None:
        from unlawful import capture

        folder = self.make_project()
        self.tool("ul", "print('no speech model: run ul lm pull ...', file=sys.stderr)\nraise SystemExit(1)\n")
        with patch.dict(os.environ, {"UNLAW_BIN": str(self.bin / "ul")}), self.assertRaises(capture.CaptureError) as caught:
            capture.transcribe_project(folder)
        self.assertIn("no speech model", str(caught.exception))
        with self.assertRaises(capture.CaptureError):
            capture.transcribe_project(folder, "--rm")
