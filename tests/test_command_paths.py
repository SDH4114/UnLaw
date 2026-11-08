"""Error and edge paths of the seeded command modules, run with fake external tools."""

from __future__ import annotations

import io
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unlawful import capture  # noqa: E402
from unlawful.built_in_commands.cpp import main as cpp_command  # noqa: E402
from unlawful.built_in_commands.git import main as git_command  # noqa: E402
from unlawful.built_in_commands.py import main as py_command  # noqa: E402
from unlawful.built_in_commands.rust import main as rust_command  # noqa: E402
from unlawful.config import config_file, ensure_layout, set_config_value, storage_path  # noqa: E402
from unlawful.desktop import music, work  # noqa: E402


class ToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        environment = patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(self.root / "config"), "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"},
        )
        environment.start()
        self.addCleanup(environment.stop)
        cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        ensure_layout()

    def tool(self, name: str, *, exit_code: int = 0, body: str = "") -> Path:
        log = self.root / f"{name}.log"
        script = self.bin / name
        script.write_text(
            f"#!{sys.executable}\nimport sys\n"
            f"open({str(log)!r}, 'a').write('|'.join(sys.argv[1:]) + '\\n')\n{body}"
            f"raise SystemExit({exit_code})\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return log

    def lines(self, log: Path) -> list[str]:
        return log.read_text().splitlines() if log.exists() else []

    # Read-only git queries of `ul git` (secrets guard, remotes, branch, upstream); they change nothing.
    GIT_QUERIES = ("diff|--cached|--name-only", "rev-parse|", "config|--get", "remote", "symbolic-ref|")

    def actions(self, log: Path) -> list[str]:
        return [line for line in self.lines(log) if not line.startswith(self.GIT_QUERIES)]

    def run_main(self, main, args: list[str]) -> tuple[int, str, str]:
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def break_config(self) -> None:
        config_file().write_text("[apps\nbroken")


class GitTests(ToolTestCase):
    def test_removed_status_and_pull_run_nothing(self) -> None:
        # `ul git status` / `ul git pull` were removed: they point to git and never commit.
        log = self.tool("git")
        for words in (["status", "extra"], ["pull"]):
            code, _, error = self.run_main(git_command.main, words)
            self.assertEqual(code, 2)
            self.assertIn(f"git {words[0]}", error)
        self.assertEqual(self.lines(log), [])

    def test_prompt_cancel_and_empty_message_stop_before_commit(self) -> None:
        log = self.tool("git", body="if sys.argv[1:] == ['diff', '--cached', '--quiet']:\n    raise SystemExit(1)\n")
        for side_effect, message in ((EOFError, "commit cancelled"), (["  "], "cannot be empty"), (KeyboardInterrupt, "cancelled")):
            with self.subTest(message=message), patch("builtins.input", side_effect=side_effect):
                code, _, error = self.run_main(git_command.main, [])
                self.assertEqual(code, 2)
                self.assertIn(message, error)
        self.assertEqual(set(self.actions(log)), {"add|.", "diff|--cached|--quiet"})

    def test_failures_stop_the_workflow(self) -> None:
        log = self.tool("git", exit_code=1)
        self.assertEqual(self.run_main(git_command.main, ["sync", "msg"])[0], 1)
        self.assertEqual(self.lines(log), ["pull|--rebase"])
        os.environ["PATH"] = "/nonexistent"
        code, _, error = self.run_main(git_command.main, ["commit", "x"])
        self.assertEqual(code, 1)
        self.assertIn("unlaw git:", error)

    def test_commit_message_tokens_are_joined(self) -> None:
        log = self.tool("git", body="if sys.argv[1:] == ['diff', '--cached', '--quiet']:\n    raise SystemExit(1)\n")
        self.assertEqual(self.run_main(git_command.main, ["fix", "the", "bug"])[0], 0)
        self.assertEqual(self.actions(log), ["add|.", "diff|--cached|--quiet", "commit|-m|fix the bug", "push"])


FAKE_SCREENCAPTURE = """import os, signal, time
args = sys.argv[1:]
out = args[-1] if args and not args[-1].startswith("-") else None
if os.environ.get("FAKE_FAIL"):
    sys.stderr.write("could not create image from display\\n")
    raise SystemExit(1)
if "-v" in args:
    stop = []
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    open(out, "wb").write(b"screen")
    while not stop:
        time.sleep(0.02)
    raise SystemExit(0)
if "-c" in args or ("-i" in args and os.environ.get("FAKE_CANCEL")):
    raise SystemExit(0)
open(out, "wb").write(b"png")
"""

FAKE_FFMPEG = """import os, signal, time
args = sys.argv[1:]
if "-list_devices" in args:
    sys.stderr.write(
        "[AVFoundation indev @ 0x1] AVFoundation video devices:\\n"
        "[AVFoundation indev @ 0x1] [0] FaceTime HD Camera\\n"
        "[AVFoundation indev @ 0x1] [1] Capture screen 0\\n"
        "[AVFoundation indev @ 0x1] AVFoundation audio devices:\\n"
        "[AVFoundation indev @ 0x1] [0] BlackHole 2ch\\n"
        "[AVFoundation indev @ 0x1] [1] MacBook Pro Microphone\\n"
    )
    raise SystemExit(1)
out = args[-1]
if out == "-":
    import array
    sys.stdout.buffer.write(array.array("h", [0, 16384, -32768, 100] * 500).tobytes())
    raise SystemExit(0)
if "avfoundation" in args:
    stop = []
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    open(out, "wb").write(b"rec")
    dies = float(os.environ.get("FAKE_RECORDER_DIES", "0"))
    started = time.monotonic()
    while not stop:
        if dies and time.monotonic() - started > dies:
            raise SystemExit(1)  # a device vanished mid-recording
        time.sleep(0.02)
    raise SystemExit(255)
failing = os.environ.get("FAKE_FFMPEG_FAIL")
if failing and any(failing in arg for arg in args):
    sys.stderr.write("Conversion failed!\\n")
    raise SystemExit(1)
data = b"processed"
if "concat" in args:
    data = b"".join(open(line.strip()[6:-1], "rb").read() for line in open(args[args.index("-i") + 1]))
open(out, "wb").write(data)
"""

FAKE_FFPROBE = """import json
print(json.dumps({"format": {"duration": "2.5"}, "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}, {"codec_type": "audio", "codec_name": "aac"}]}))
"""

FAKE_SIPS = """args = sys.argv[1:]
if "--out" in args:
    open(args[args.index("--out") + 1], "wb").write(b"jpg")
"""

FAKE_DISPLAYS = """import json
print(json.dumps({"SPDisplaysDataType": [{"spdisplays_ndrvs": [
    {"_name": "Studio Display", "_spdisplays_pixels": "5120 x 2880"},
    {"_name": "Color LCD", "_spdisplays_pixels": "3024 x 1964", "spdisplays_main": "spdisplays_yes"}]}]}))
"""


class CaptureTests(ToolTestCase):
    def setUp(self) -> None:
        super().setUp()
        home = patch.dict(os.environ, {"HOME": str(self.root / "home")})
        home.start()
        self.addCleanup(home.stop)
        (self.root / "home").mkdir()

    def media_tools(self) -> dict[str, Path]:
        logs = {
            "screencapture": self.tool("screencapture", body=FAKE_SCREENCAPTURE),
            "ffmpeg": self.tool("ffmpeg", body=FAKE_FFMPEG),
            "ffprobe": self.tool("ffprobe", body=FAKE_FFPROBE),
            "sips": self.tool("sips", body=FAKE_SIPS),
            "system_profiler": self.tool("system_profiler", body=FAKE_DISPLAYS),
        }
        for name in ("open", "osascript"):
            logs[name] = self.tool(name)
        self.addCleanup(self.stop_leftovers)
        return logs

    def stop_leftovers(self) -> None:
        if capture.recording_state_file().exists():
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                capture.main(["stop"])

    def ok(self, *args: str) -> str:
        code, out, error = self.run_main(capture.main, list(args))
        self.assertEqual(code, 0, f"{args}: {error}")
        return out

    def test_usage_and_argument_errors(self) -> None:
        code, out, _ = self.run_main(capture.main, [])
        self.assertEqual(code, 2)
        self.assertIn("Usage", out)
        self.assertEqual(self.run_main(capture.main, ["--help"])[0], 0)
        cases = {
            ("dance",): "Unknown capture action: dance",
            ("record", "--duration"): "--duration needs a value",
            ("record", "--duration", "0"): "--duration needs a whole number from 1",
            ("record", "hologram"): "unknown recording mode: hologram",
            ("record", "camera", "--camera"): "--camera adds the camera",
            ("record", "--rect", "1,2,3"): "--rect needs X,Y,WIDTH,HEIGHT",
            ("record", "--format", "gif"): "video format must be one of mov, mp4",
            ("record", "audio", "--format", "mov"): "audio format must be one of",
            ("shot", "a.png", "b.png"): "unexpected argument: b.png",
            ("shot", "selfie"): "unknown screenshot kind",
            ("shot", "--display", "0"): "--display needs a whole number from 1",
            ("stop", "now"): "stop takes no arguments",
            ("trim", "x.mov"): "usage: ul capture trim",
        }
        for args, message in cases.items():
            with self.subTest(args=args):
                code, _, error = self.run_main(capture.main, list(args))
                self.assertEqual(code, 2)
                self.assertIn(message, error)

    def test_screenshots_old_and_new_names(self) -> None:
        logs = self.media_tools()
        for args, kind, flags in (
            (["screenshot"], "screen", "-x|-D1"),
            (["shot"], "screen", "-x|-D1"),
            (["area"], "area", "-i|-s|-x"),
            (["shot", "window"], "window", "-i|-W|-x"),
            (["shot", "--display", "2", "--delay", "3", "--cursor", "--jpg"], "screen", "-x|-D2|-T3|-C|-tjpg"),
        ):
            with self.subTest(args=args):
                path = Path(self.ok(*args).strip())
                self.assertEqual(path.parent, storage_path("captures", "screenshots"))
                self.assertRegex(path.name, rf"^{kind}-\d{{8}}-\d{{6}}( \d+)?\.(png|jpg)$")
                self.assertEqual(self.lines(logs["screencapture"])[-1], f"{flags}|{path}")
        target = self.root / "x.png"
        self.assertEqual(self.ok("shot", str(target)).strip(), str(target))
        self.assertEqual(self.ok("shot", str(target)).strip(), str(self.root / "x 2.png"), "never overwrites")
        self.assertIn("clipboard", self.ok("shot", "area", "--clipboard"))
        self.assertEqual(self.lines(logs["screencapture"])[-1], "-c|-i|-s|-x")
        self.ok("shot", "--open")
        self.assertEqual(len(self.lines(logs["open"])), 1)
        with patch.dict(os.environ, {"FAKE_CANCEL": "1"}):
            code, _, error = self.run_main(capture.main, ["area"])
        self.assertEqual((code, error.strip()), (1, "unlaw capture: cancelled"))
        with patch.dict(os.environ, {"FAKE_FAIL": "1"}):
            code, _, error = self.run_main(capture.main, ["shot"])
        self.assertEqual(code, 1)
        self.assertIn("Screen Recording permission", error)

    def test_screen_recording_pauses_resumes_and_joins_the_parts(self) -> None:
        logs = self.media_tools()
        out = self.ok("record")
        self.assertIn("Recording screen:", out)
        command = self.lines(logs["screencapture"])[-1].split("|")
        self.assertEqual(command[:4], ["-v", "-x", "-D1", "-k"])
        self.assertIn("-A", command, "system audio by default")
        self.assertIn("-g", command, "the default microphone goes into screencapture")
        self.assertEqual(self.lines(logs.get("ffmpeg", Path("none"))), [], "no ffmpeg needed for a plain screen recording")
        code, _, error = self.run_main(capture.main, ["record", "audio"])
        self.assertEqual(code, 1)
        self.assertIn("already running", error)
        status = json.loads(self.ok("status", "--json"))
        self.assertEqual((status["phase"], status["mode"], status["camera"]), ("recording", "screen", False))
        self.assertIn("Paused", self.ok("pause"))
        self.assertTrue(json.loads(self.ok("status", "--json"))["paused"])
        self.assertIn("Recording", self.ok("resume"))
        saved = json.loads(self.ok("stop", "--json"))["saved"]
        path = Path(saved)
        self.assertEqual(path.parent, storage_path("captures", "recordings"))
        self.assertEqual(path.read_bytes(), b"screenscreen", "two parts joined")
        self.assertTrue(any("concat" in line for line in self.lines(logs["ffmpeg"])))
        self.assertFalse(capture.recording_state_file().exists())
        self.assertEqual(list(storage_path("captures", ".parts").iterdir()), [], "parts are cleaned up")
        self.assertEqual(self.ok("status").strip(), "Not recording.")
        code, _, error = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 1)
        self.assertIn("no active recording", error)

    def test_screen_with_camera_and_mp4(self) -> None:
        logs = self.media_tools()
        self.ok("record", "--camera", "--format", "mp4", "--no-clicks")
        screen = self.lines(logs["screencapture"])[-1].split("|")
        self.assertNotIn("-g", screen, "the microphone is recorded with the camera, in sync with the face")
        self.assertNotIn("-k", screen)
        camera = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|")
        self.assertIn("default:default", camera, "the camera macOS picks, with the default microphone")
        saved = Path(json.loads(self.ok("stop", "--json"))["saved"])
        self.assertTrue(saved.name.startswith("screen-camera-") and saved.suffix == ".mp4")
        overlay = [line for line in self.lines(logs["ffmpeg"]) if "overlay=" in line][-1]
        self.assertIn("overlay=W-w-38:H-h-38", overlay)
        self.assertIn("amix=inputs=2", overlay)
        self.assertIn("-itsoffset", overlay)
        self.assertTrue(any("+faststart" in line for line in self.lines(logs["ffmpeg"])))

    def test_a_named_or_virtual_microphone_is_recorded_separately(self) -> None:
        logs = self.media_tools()
        set_config_value("capture.audio_device", "0")  # the old default: BlackHole here
        code, _, error = self.run_main(capture.main, ["record"])
        self.assertEqual(code, 0, error)
        self.assertIn("BlackHole 2ch is a virtual device", error)
        self.assertNotIn("-g", self.lines(logs["screencapture"])[-1].split("|"))
        mic = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|")
        self.assertIn(":BlackHole 2ch", mic)
        self.ok("stop")
        self.assertTrue(any("amix" in line and "-c:v|copy" in line for line in self.lines(logs["ffmpeg"])))
        set_config_value("capture.audio_device", "macbook")
        self.ok("record", "--no-system-audio")
        self.assertNotIn("-A", self.lines(logs["screencapture"])[-1].split("|"))
        self.assertIn(":MacBook Pro Microphone", [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|"))
        self.ok("stop")
        code, _, error = self.run_main(capture.main, ["record", "--mic", "Studio"])
        self.assertEqual(code, 2)
        self.assertIn("no microphone named 'Studio'", error)

    def test_audio_and_camera_recordings(self) -> None:
        logs = self.media_tools()
        self.ok("record", "audio", "--format", "mp3")
        command = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|")
        self.assertIn(":default", command)
        self.assertIn("libmp3lame", command)
        saved = Path(json.loads(self.ok("stop", "--json"))["saved"])
        self.assertEqual((saved.suffix, saved.read_bytes()), (".mp3", b"rec"))
        self.ok("camera", "--no-mic", "--cam", "facetime")
        self.assertIn("FaceTime HD Camera:none", [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|"))
        self.assertTrue(Path(json.loads(self.ok("stop", "--json"))["saved"]).name.startswith("camera-"))
        code, _, error = self.run_main(capture.main, ["record", "audio", "--no-mic"])
        self.assertEqual(code, 2)
        self.assertIn("needs a microphone", error)
        code, _, error = self.run_main(capture.main, ["record", "camera", "--system-audio"])
        self.assertIn("system audio is recorded with the screen only", error)

    def test_a_failed_save_keeps_the_parts_for_another_try(self) -> None:
        logs = self.media_tools()
        self.ok("record", "--camera")
        status = json.loads(self.ok("status", "--json"))
        self.assertLess(status["elapsed"], 3.0)
        self.assertGreaterEqual(status["elapsed"], 0.6, "the clock starts with the recorders, before the start check")
        with patch.dict(os.environ, {"FAKE_FFMPEG_FAIL": "overlay"}):
            code, _, error = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 1)
        self.assertIn("adding the camera failed", error)
        status = json.loads(self.ok("status", "--json"))
        self.assertEqual(status["phase"], "unsaved")
        self.assertIn("Not saved yet", self.ok("status"))
        saved = Path(json.loads(self.ok("stop", "--json"))["saved"])
        self.assertTrue(saved.is_file())
        self.assertFalse(capture.recording_state_file().exists())
        self.assertGreaterEqual(sum("overlay=" in line for line in self.lines(logs["ffmpeg"])), 2)

    def test_a_recording_that_cannot_start_explains_permissions(self) -> None:
        self.media_tools()
        with patch.dict(os.environ, {"FAKE_FAIL": "1"}):
            code, _, error = self.run_main(capture.main, ["record"])
        self.assertEqual(code, 1)
        self.assertIn("could not create image from display", error)
        self.assertIn("Privacy & Security", error)
        self.assertFalse(capture.recording_state_file().exists())
        state = capture.recording_state_file()
        state.write_text("{not json")
        code, _, error = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 1)
        self.assertIn("was reset", error)
        self.assertFalse(state.exists(), "a broken state file must not block new recordings")

    def test_duration_records_in_the_foreground_and_saves(self) -> None:
        self.media_tools()
        started = time.monotonic()
        out = self.ok("record", "audio", "--duration", "1")
        self.assertIn("Saved:", out)
        self.assertGreaterEqual(time.monotonic() - started, 1.0)
        self.assertFalse(capture.recording_state_file().exists())

    def test_a_recorder_that_dies_ends_a_timed_recording_and_saves_it(self) -> None:
        self.media_tools()
        started = time.monotonic()
        with patch.dict(os.environ, {"FAKE_RECORDER_DIES": "1.0"}):
            code, out, error = self.run_main(capture.main, ["record", "audio", "--duration", "30"])
        self.assertEqual(code, 0, error)
        self.assertLess(time.monotonic() - started, 10, "it must not keep timing a dead recorder")
        self.assertIn("stopped unexpectedly", error)
        self.assertTrue(Path(out.split("Saved: ", 1)[1].strip()).is_file())

    def test_ctrl_c_while_saving_keeps_the_recording_for_another_stop(self) -> None:
        self.media_tools()
        self.ok("record", "audio")
        with patch.object(capture, "_save", side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_main(capture.main, ["stop"])[0], 130)
        self.assertEqual(json.loads(self.ok("status", "--json"))["phase"], "unsaved")
        self.assertTrue(Path(json.loads(self.ok("stop", "--json"))["saved"]).is_file())

    def test_a_failed_thumbnail_or_preview_is_never_cached(self) -> None:
        self.media_tools()
        video = storage_path("captures", "recordings", "talk.mov")
        video.write_bytes(b"v")
        with patch.dict(os.environ, {"FAKE_FFMPEG_FAIL": "scale=480"}):
            code, _, error = self.run_main(capture.main, ["thumb", "talk.mov"])
        self.assertEqual(code, 1, error)
        thumbs = storage_path("runtime", "thumbs")
        self.assertEqual([path.name for path in thumbs.iterdir()] if thumbs.is_dir() else [], [], "no half-made thumbnail may stay")
        thumb = Path(self.ok("thumb", "talk.mov").strip())
        self.assertEqual(thumb.read_bytes(), b"processed")
        with patch.dict(os.environ, {"FAKE_FAIL": "1"}):
            self.assertEqual(self.run_main(capture.main, ["preview"])[0], 1)
        self.assertEqual(list(storage_path("runtime").glob("*preview*")) + list(storage_path("runtime").glob(".capture.*")), [])
        self.assertTrue(Path(self.ok("preview").strip()).is_file())

    def test_camera_audio_and_devices_need_ffmpeg(self) -> None:
        self.tool("screencapture", body=FAKE_SCREENCAPTURE)
        for args in (["camera"], ["audio"], ["record", "--camera"], ["record", "--mic", "1"]):
            with self.subTest(args=args):
                code, _, error = self.run_main(capture.main, args)
                self.assertEqual(code, 1)
                self.assertIn("ffmpeg is required", error)
        self.assertIn("install ffmpeg", self.ok("devices"))

    def test_devices_lists_displays_cameras_and_flags_virtual_microphones(self) -> None:
        self.media_tools()
        set_config_value("capture.audio_device", "0")
        text = self.ok("devices")
        self.assertIn("1  Color LCD  3024 x 1964", text, "the main display is number 1")
        self.assertIn("2  Studio Display", text)
        self.assertIn("0  FaceTime HD Camera", text)
        self.assertNotIn("Capture screen", text)
        self.assertIn("BlackHole 2ch  (virtual", text)
        self.assertIn("ul config set capture.audio_device default", text)
        data = json.loads(self.ok("devices", "--json"))
        self.assertEqual(data["microphones"][0], {"name": "BlackHole 2ch", "virtual": True})

    def test_library_open_copy_trim_convert_thumb_and_delete(self) -> None:
        logs = self.media_tools()
        self.assertIn("No captures yet", self.ok("list"))
        code, _, error = self.run_main(capture.main, ["last"])
        self.assertEqual(code, 2)
        self.assertIn("no captures found", error)
        video = storage_path("captures", "recordings", "talk.mov")
        image = storage_path("captures", "screenshots", "shot.png")
        video.write_bytes(b"v")
        image.write_bytes(b"i")
        os.utime(video, (1, 1))
        items = json.loads(self.ok("list", "--json"))
        self.assertEqual([item["name"] for item in items], ["shot.png", "talk.mov"])
        self.assertEqual([item["kind"] for item in items], ["image", "video"])
        self.assertEqual(items[1]["duration"], 2.5)
        self.assertIsNone(items[0]["duration"])
        self.ok("last")
        self.ok("reveal", "talk.mov")
        self.ok("last", "--reveal")
        self.assertEqual(self.lines(logs["open"]), [str(image), f"-R|{video}", f"-R|{image}"])
        self.assertIn("Copied shot.png", self.ok("copy", "last"))
        self.assertIn("«class PNGf»", self.lines(logs["osascript"])[-1])
        code, _, error = self.run_main(capture.main, ["copy", "talk.mov"])
        self.assertIn("only screenshots", error)
        trimmed = Path(json.loads(self.ok("trim", "talk.mov", "--from", "0:05", "--to", "1:00.5", "--json"))["saved"])
        self.assertEqual(trimmed.name, "talk trim.mov")
        trim = self.lines(logs["ffmpeg"])[-1].split("|")
        self.assertEqual(trim[trim.index("-ss") : trim.index("-ss") + 4], ["-ss", "5.000", "-i", str(video)], "fast input seek")
        self.assertEqual(trim[trim.index("-t") + 1], "55.500")
        code, _, error = self.run_main(capture.main, ["trim", "talk.mov", "--from", "9", "--to", "3"])
        self.assertIn("--to must be after --from", error)
        self.assertEqual(Path(self.ok("convert", "talk.mov", "--to", "gif").split(": ", 1)[1].strip()).name, "talk.gif")
        self.assertIn("palettegen", self.lines(logs["ffmpeg"])[-1])
        self.ok("convert", "talk.mov", "--to", "mp4")
        self.assertIn("-c|copy", self.lines(logs["ffmpeg"])[-1], "h264/aac is remuxed, not re-encoded")
        code, _, error = self.run_main(capture.main, ["convert", "shot.png", "--to", "mp4"])
        self.assertIn("only recordings", error)
        wave = json.loads(self.ok("wave", "talk.mov", "--bars", "10", "--json"))
        self.assertEqual(len(wave["peaks"]), 10)
        self.assertEqual(wave["peaks"][0], 1.0, "the loudest sample is full scale")
        self.assertEqual(wave["duration"], 1.0)
        self.assertEqual(json.loads(self.ok("wave", "talk.mov", "--bars", "10", "--json")), wave, "cached")
        self.assertEqual(len(self.ok("wave", "talk.mov").strip()), 80)
        code, _, error = self.run_main(capture.main, ["wave", "shot.png"])
        self.assertIn("only recordings have sound", error)
        thumb = Path(self.ok("thumb", "shot.png").strip())
        self.assertEqual(thumb.read_bytes(), b"jpg")
        self.assertEqual(Path(self.ok("thumb", "shot.png").strip()), thumb, "cached")
        outside = self.root / "elsewhere.png"
        outside.write_bytes(b"x")
        code, _, error = self.run_main(capture.main, ["delete", str(outside)])
        self.assertIn("only removes files from the capture folders", error)
        self.assertIn("Moved to the Trash: shot.png", self.ok("delete", "shot.png"))
        self.assertTrue((self.root / "home" / ".Trash" / "shot.png").exists())
        self.assertFalse(image.exists())

    def test_invalid_config_is_reported(self) -> None:
        self.break_config()
        code, _, error = self.run_main(capture.main, ["screenshot"])
        self.assertEqual(code, 2)
        self.assertIn("Could not read", error)

    def test_relative_recording_output_keeps_the_starting_directory(self) -> None:
        self.media_tools()
        original = self.root / "start"
        other = self.root / "stop"
        original.mkdir()
        other.mkdir()
        os.chdir(original)
        self.ok("record", "--output", "session.mov")
        os.chdir(other)
        saved = Path(json.loads(self.ok("stop", "--json"))["saved"])
        self.assertEqual(saved, original / "session.mov")
        self.assertEqual(saved.read_bytes(), b"screen")
        self.assertFalse((other / "session.mov").exists())

    def test_failed_start_stops_spawned_recorders(self) -> None:
        self.media_tools()
        real_popen = capture.subprocess.Popen
        for failure in ("spawn", "write", "interrupt"):
            with self.subTest(failure=failure):
                spawned = []

                def spawn(command, failure=failure, spawned=spawned, **kwargs):
                    if failure == "spawn" and command[0] == "ffmpeg":
                        raise OSError("process table full")
                    process = real_popen(command, **kwargs)
                    if command[0] in {"screencapture", "ffmpeg"}:
                        spawned.append(process)
                    return process

                try:
                    with patch.object(capture.subprocess, "Popen", side_effect=spawn):
                        if failure == "write":
                            with patch.object(capture, "_write_json", side_effect=OSError("No space left on device")):
                                code, _, _ = self.run_main(capture.main, ["record"])
                        elif failure == "interrupt":
                            sleep = time.sleep
                            interrupted = False

                            def interrupt_once(seconds, sleep=sleep):
                                nonlocal interrupted
                                if not interrupted:
                                    interrupted = True
                                    raise KeyboardInterrupt
                                sleep(seconds)

                            with patch.object(capture.time, "sleep", side_effect=interrupt_once):
                                code, _, _ = self.run_main(capture.main, ["record"])
                        else:
                            code, _, _ = self.run_main(capture.main, ["record", "--camera"])
                    self.assertNotEqual(code, 0)
                    self.assertFalse(capture.recording_state_file().exists())
                    self.assertTrue(spawned)
                    self.assertTrue(all(process.poll() is not None for process in spawned), "failed start left a recorder alive")
                finally:
                    for process in spawned:
                        if process.poll() is None:
                            process.send_signal(signal.SIGINT)
                            process.wait(timeout=5)

    def test_failed_resume_state_write_stops_the_new_recorder(self) -> None:
        self.media_tools()
        self.ok("record")
        self.ok("pause")
        before = capture.recording_state_file().read_bytes()
        real_popen = capture.subprocess.Popen
        spawned = []

        def spawn(command, **kwargs):
            process = real_popen(command, **kwargs)
            if command[0] == "screencapture":
                spawned.append(process)
            return process

        try:
            with patch.object(capture.subprocess, "Popen", side_effect=spawn), patch.object(capture, "_write_json", side_effect=OSError("disk full")):
                code, _, _ = self.run_main(capture.main, ["resume"])
            self.assertNotEqual(code, 0)
            self.assertEqual(capture.recording_state_file().read_bytes(), before)
            self.assertTrue(all(process.poll() is not None for process in spawned))
        finally:
            for process in spawned:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    process.wait(timeout=5)

    def test_missing_screen_preserves_secondary_recording_and_state(self) -> None:
        self.media_tools()
        self.ok("record", "--camera")
        self.ok("pause")
        state = capture._load_state()
        screen = Path(state["segments"][0]["screen"])
        camera = Path(state["segments"][0]["camera"])
        screen.unlink()
        code, _, _ = self.run_main(capture.main, ["stop"])
        self.assertNotEqual(code, 0)
        self.assertTrue(camera.exists(), "the surviving camera recording was deleted")
        self.assertEqual(camera.read_bytes(), b"rec")
        self.assertEqual(json.loads(self.ok("status", "--json"))["phase"], "unsaved")
        screen.write_bytes(b"recovered")
        self.assertTrue(Path(json.loads(self.ok("stop", "--json"))["saved"]).exists())

    def test_partial_recording_state_is_rejected_without_a_traceback(self) -> None:
        self.media_tools()
        self.ok("record")
        self.ok("pause")
        valid = capture._load_state()
        self.ok("stop")
        broken_pid = {**valid, "processes": [{"pid": "bad", "program": "ffmpeg"}]}
        for state in (
            {"segments": []},
            {**valid, "segments": None},
            broken_pid,
            {**valid, "elapsed": 10**500},
            {**valid, "plan": {**valid["plan"], "overlay": []}},
        ):
            with self.subTest(state=state):
                capture.recording_state_file().write_text(json.dumps(state))
                try:
                    code, out, error = self.run_main(capture.main, ["stop", "--json"])
                except (KeyError, TypeError, AttributeError, OverflowError) as failure:
                    self.fail(f"partial state crashed: {failure}")
                finally:
                    capture.recording_state_file().unlink(missing_ok=True)
                self.assertNotEqual(code, 0)
                self.assertIn("recording state", json.loads(out)["error"])
                self.assertEqual(error, "")

    def test_delete_refuses_an_absolute_symlink_to_a_capture(self) -> None:
        target = storage_path("captures", "screenshots", "original.png")
        target.write_bytes(b"keep")
        link = self.root / "link.png"
        link.symlink_to(target)
        code, _, error = self.run_main(capture.main, ["delete", str(link)])
        self.assertNotEqual(code, 0)
        self.assertIn("only removes files", error)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), b"keep")

    def test_concurrent_screenshots_never_overwrite_each_other(self) -> None:
        self.tool("screencapture", body="import os, time\ntime.sleep(0.25)\nopen(sys.argv[-1], 'wb').write(str(os.getpid()).encode())\n")
        output = self.root / "same.png"
        with ThreadPoolExecutor(max_workers=2) as workers:
            paths = list(workers.map(lambda _: capture.shot(output=str(output)), range(2)))
        self.assertEqual(set(paths), {output, self.root / "same 2.png"})
        self.assertNotEqual(paths[0].read_bytes(), paths[1].read_bytes())

class MusicAndWorkTests(ToolTestCase):
    def test_music_query_is_escaped_for_applescript(self) -> None:
        log = self.tool("osascript")
        set_config_value("apps.spotify_autoplay_delay", 0.5)
        self.assertEqual(self.run_main(music.main, ['say "hi" \\ now'])[0], 0)
        script = log.read_text().split("|", 1)[1]
        self.assertIn('set searchQuery to "say \\"hi\\" \\\\ now"', script)
        self.assertIn("spotify:search:say%20%22hi%22%20%5C%20now", script)
        self.assertIn("delay 0.5", script)

    def test_music_failures(self) -> None:
        self.tool("osascript", exit_code=1)
        code, _, error = self.run_main(music.main, ["song"])
        self.assertEqual(code, 1)
        self.assertIn("Accessibility", error)
        code, _, error = self.run_main(music.main, ["  "])
        self.assertEqual(code, 2)
        (self.bin / "osascript").unlink()
        os.environ["PATH"] = str(self.bin)
        self.assertEqual(self.run_main(music.main, ["song"])[0], 1)
        self.break_config()
        self.assertEqual(self.run_main(music.main, [])[0], 2)

    def test_work_stops_when_the_browser_fails(self) -> None:
        log = self.tool("open", exit_code=3)
        self.assertEqual(self.run_main(work.main, [])[0], 3)
        self.assertEqual(len(self.lines(log)), 1)
        self.assertEqual(self.run_main(work.main, ["extra"])[0], 2)
        self.break_config()
        code, _, error = self.run_main(work.main, [])
        self.assertEqual(code, 1)
        self.assertIn("unlaw work:", error)


class ProjectGeneratorTests(ToolTestCase):
    def test_invalid_names_and_flags(self) -> None:
        for main, args in (
            (py_command.main, ["9bad"]),
            (py_command.main, ["ok", "--uv", "--venv"]),
            (py_command.main, ["ok", "--weird"]),
            (rust_command.main, []),
            (rust_command.main, ["ok", "--bin", "--lib"]),
            (cpp_command.main, ["ok", "--std"]),
            (cpp_command.main, ["ok", "--std", "98"]),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.run_main(main, args)[0], 2)

    def test_existing_destination_is_never_overwritten(self) -> None:
        for main, name in ((py_command.main, "taken-py"), (rust_command.main, "taken-rs"), (cpp_command.main, "taken-cpp")):
            with self.subTest(name=name):
                (self.root / name).mkdir()
                (self.root / name / "keep.txt").write_text("mine")
                code, _, error = self.run_main(main, [name])
                self.assertEqual(code, 1, error)
                self.assertEqual((self.root / name / "keep.txt").read_text(), "mine")

    def test_missing_tools_are_reported(self) -> None:
        os.environ["PATH"] = str(self.bin)
        code, _, error = self.run_main(rust_command.main, ["needs-cargo"])
        self.assertNotEqual(code, 0)
        self.assertTrue(error)
        self.assertFalse((self.root / "needs-cargo" / "src").exists())

    def test_invalid_config_is_reported(self) -> None:
        self.tool("cargo")
        self.break_config()
        for main, args in ((py_command.main, ["p"]), (rust_command.main, ["r"]), (cpp_command.main, ["c"])):
            with self.subTest(args=args):
                self.assertEqual(self.run_main(main, args)[0], 2)

    def test_cpp_git_initialisation(self) -> None:
        log = self.tool("git")
        code, _, error = self.run_main(cpp_command.main, ["engine", "--std", "17", "--git"])
        self.assertEqual(code, 0, error)
        self.assertIn("CMAKE_CXX_STANDARD 17", (self.root / "engine" / "CMakeLists.txt").read_text())
        self.assertEqual(self.lines(log)[0].split("|")[0], "init")


if __name__ == "__main__":
    unittest.main()
