"""Error and edge paths of the seeded command modules, run with fake external tools."""

from __future__ import annotations

import io
import json
import os
import subprocess
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
            {
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
                # The real ul-rec (next to a built ul) would record this Mac; native tests install a fake.
                "UNLAW_CAPTURE_REC": "off",
            },
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
        self.assertEqual(self.lines(log), ["pull|--rebase|--autostash"])
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
    if os.environ.get("FAKE_STUCK"):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    while not stop:
        time.sleep(0.02)
    open(out, "wb").write(b"screen")  # like the real tool: the movie is written when it stops
    raise SystemExit(0)
if "-c" in args or ("-i" in args and os.environ.get("FAKE_CANCEL")):
    raise SystemExit(0)
if os.path.basename(out).startswith("."):
    # Like the real tool (macOS 27): screenshots refuse hidden file names, and it still exits 0.
    sys.stderr.write(f"screencapture: cannot write file to intended destination, {out}\\n")
    raise SystemExit(0)
open(out, "wb").write(b"png")
"""

FAKE_MODES = (
    "[in#0 @ 0x1] Selected framerate (1000.000000) is not supported by the device.\\n"
    "[in#0 @ 0x1] Supported modes:\\n"
    "[in#0 @ 0x1]   1920x1080@[15.000000 30.000000]fps\\n"
    "[in#0 @ 0x1]   1280x720@[15.000000 30.000000]fps\\n"
)

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
if "-encoders" in args:
    if not os.environ.get("FAKE_NO_X264"):
        print(" V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)")
    print(" V....D h264_videotoolbox    VideoToolbox H.264 Encoder (codec h264)")
    raise SystemExit(0)
if "-framerate" in args and args[args.index("-framerate") + 1] == "1000":
    sys.stderr.write(""" + repr(FAKE_MODES) + """)
    raise SystemExit(1)
out = args[-1]
if out == "-":
    import array
    sys.stdout.buffer.write(array.array("h", [0, 16384, -32768, 100] * 500).tobytes())
    raise SystemExit(0)
if "avfoundation" in args:
    if os.environ.get("FAKE_NO_NV12") and "-pixel_format" in args:
        sys.stderr.write("Selected pixel format (nv12) is not supported by the input device.\\n")
        raise SystemExit(1)
    stop = []
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    time.sleep(float(os.environ.get("FAKE_SLOW_START", "0")))  # a device that takes a while to wake up
    open(out, "wb").write(b"rec")
    levels = "-filter_complex" in args and "mic-levels.txt" in args[args.index("-filter_complex") + 1]
    level = "-80.0" if os.environ.get("FAKE_SILENT") else "-21.5"
    dies = float(os.environ.get("FAKE_RECORDER_DIES", "0"))
    started = time.monotonic()
    frame = 0
    while not stop:
        if dies and time.monotonic() - started > dies:
            raise SystemExit(1)  # a device vanished mid-recording
        if levels:
            with open("mic-levels.txt", "a") as stream:
                stream.write(f"frame:{frame} pts:{frame * 4800} pts_time:{frame / 10}\\nlavfi.astats.Overall.Peak_level={level}\\n")
            frame += 1
            time.sleep(0.1)
        else:
            time.sleep(0.02)
    raise SystemExit(255)
failing = os.environ.get("FAKE_FFMPEG_FAIL")
if failing and any(failing in arg for arg in args):
    sys.stderr.write("Conversion failed!\\n")
    raise SystemExit(1)
data = b"processed"
if "concat" in args:
    data = b"".join(open(line.strip()[6:-1].replace("'\\\\''", "'"), "rb").read() for line in open(args[args.index("-i") + 1]))
elif "+faststart" in args and "copy" in args and "-i" in args:
    data = open(args[args.index("-i") + 1], "rb").read()  # a remux keeps the media
open(out, "wb").write(data)
"""

FAKE_UL_REC = """import json, os, signal, time
if sys.argv[1] == "--devices":
    mode = {"width": 1920, "height": 1080, "min_fps": 1.0, "max_fps": 30.0}
    print(json.dumps({"cameras": [{"name": "Studio Cam", "modes": [mode]}],
                      "microphones": ["Studio Mic"], "default_camera": "Studio Cam"}))
    raise SystemExit(0)
plan = json.load(open(sys.argv[1]))
events = open(plan["events"], "a")
def event(**item):
    events.write(json.dumps(item) + "\\n")
    events.flush()
stop = []
signal.signal(signal.SIGINT, lambda *_: stop.append(1))
signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
failing = os.environ.get("FAKE_REC_FAIL", "")
dropping = os.environ.get("FAKE_REC_DROP", "")
offsets = {"screen": 0.0, "mic": 0.25, "camera": 0.75}
started = []
for track in ("screen", "camera", "mic"):
    part = plan.get(track)
    if not part:
        continue
    if track == failing:
        event(track=track, event="failed", error="the camera is busy or not allowed")
        continue
    open(part["path"], "wb").write(b"rec")
    event(track=track, event="started", wall=1700000000.0 + offsets[track])
    started.append(track)
event(event="ready", tracks=started)
began = time.monotonic()
frame = 0
while not stop:
    if dropping in started and time.monotonic() - began > 0.3:
        event(track=dropping, event="failed", error="the device was disconnected")
        started.remove(dropping)
    if "mic" in started:
        with open(plan["levels"], "a") as stream:
            stream.write(f"frame:{frame} pts:0 pts_time:{frame / 10}\\nlavfi.astats.Overall.Peak_level=-21.5\\n")
        frame += 1
    time.sleep(0.1)
for track in started:
    event(track=track, event="finished")
event(event="stopped")
open(sys.argv[0] + ".exit", "w").write("stopped")
"""

FAKE_FFPROBE = """import json, os
duration = "2.5"
for part, value in json.loads(os.environ.get("FAKE_PROBE_DURATIONS", "{}")).items():
    if os.path.basename(sys.argv[-1]).startswith(part):
        duration = str(value)
print(json.dumps({"format": {"duration": duration}, "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}, {"codec_type": "audio", "codec_name": "aac"}]}))
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
        # No arguments opens the menu in a terminal; without one it prints the usage. Stdin is
        # pinned so the result does not depend on whether the suite runs in a terminal.
        with patch.object(capture.sys, "stdin", io.StringIO()):
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
            ("shot", "--display", "²"): "--display needs a whole number from 1",
            ("record", "--rect", "1,2,3,²"): "--rect needs X,Y,WIDTH,HEIGHT",
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
        self.assertNotIn("-g", command, "the microphone is its own track")
        mic = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|")
        self.assertIn(":default", mic)
        self.assertEqual(mic[mic.index("-c:a") + 1], "flac")
        code, _, error = self.run_main(capture.main, ["record", "audio"])
        self.assertEqual(code, 1)
        self.assertIn("already running", error)
        status = json.loads(self.ok("status", "--json"))
        self.assertEqual((status["phase"], status["mode"], status["camera"]), ("recording", "screen", False))
        self.assertEqual(status["tracks"], ["screen", "mic"])
        self.assertIn("Paused", self.ok("pause"))
        self.assertTrue(json.loads(self.ok("status", "--json"))["paused"])
        self.assertIn("Recording", self.ok("resume"))
        result = json.loads(self.ok("stop", "--json"))
        folder, project = self.project(result)
        self.assertEqual(result["saved"], result["project"], "no export: saved is the project folder")
        self.assertEqual(folder.parent, storage_path("captures", "projects"))
        self.assertEqual((project["state"], len(project["segments"])), ("ready", 2))
        self.assertEqual(project["segments"][1]["files"], {"screen": "media/screen-002.mp4", "mic": "media/mic-002.flac"})
        self.assertEqual((folder / "media" / "screen-001.mp4").read_bytes(), b"screen", "remuxed, not re-encoded")
        self.assertEqual(sorted(path.name for path in (folder / "media").iterdir()),
                         ["mic-001.flac", "mic-002.flac", "screen-001.mp4", "screen-002.mp4"], "no dot files left")
        self.assertFalse(capture.recording_state_file().exists())
        self.assertEqual(self.ok("status").strip(), "Not recording.")
        self.assertIn("ul capture export last", self.ok("record") and self.ok("stop"))
        code, _, error = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 1)
        self.assertIn("no active recording", error)

    def test_screen_with_camera_and_mp4(self) -> None:
        logs = self.media_tools()
        self.ok("record", "--camera", "--format", "mp4", "--no-clicks")
        screen = self.lines(logs["screencapture"])[-1].split("|")
        self.assertNotIn("-g", screen)
        self.assertNotIn("-k", screen)
        camera = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line and ":none" in line][-1].split("|")
        self.assertIn("default:none", camera, "video only: the microphone is its own track")
        self.assertEqual(camera[camera.index("-video_size") + 1], "1920x1080", "high quality = 1080p from the probed modes")
        self.assertEqual(camera[camera.index("-framerate") + 1], "30.000000", "the device's own framerate string")
        self.assertEqual(camera[camera.index("-b:v") + 1], "6000000")
        folder, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertTrue(folder.name.startswith("screen-camera-"))
        self.assertEqual((folder / "media" / "camera-001.mp4").read_bytes(), b"rec")
        self.assertEqual(project["export"]["container"], "mp4")
        self.assertEqual(project["sources"][1]["mode"], "1920x1080@30.000000")
        self.assertTrue(project["sources"][1]["enabled"])
        self.assertEqual(project["segments"][0]["starts"], {"screen": 0.0, "camera": 0.0, "mic": 0.0})

    def test_a_named_or_virtual_microphone_is_recorded_separately(self) -> None:
        logs = self.media_tools()
        set_config_value("capture.audio_device", "0")  # the old default: BlackHole here
        code, _, error = self.run_main(capture.main, ["record"])
        self.assertEqual(code, 0, error)
        self.assertIn("BlackHole 2ch is a virtual device", error)
        mic = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|")
        self.assertIn(":BlackHole 2ch", mic)
        self.ok("stop")
        set_config_value("capture.audio_device", "macbook")
        self.ok("record", "--no-system-audio", "--mic-format", "wav")
        self.assertNotIn("-A", self.lines(logs["screencapture"])[-1].split("|"))
        mic = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|")
        self.assertIn(":MacBook Pro Microphone", mic)
        self.assertTrue(mic[-1].endswith("mic-001.wav"))
        self.ok("stop")
        code, _, error = self.run_main(capture.main, ["record", "--mic", "Studio"])
        self.assertEqual(code, 2)
        self.assertIn("no microphone named 'Studio'", error)

    def test_audio_and_camera_recordings(self) -> None:
        logs = self.media_tools()
        self.ok("record", "audio", "--mic-format", "m4a")
        command = [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line][-1].split("|")
        self.assertIn(":default", command)
        self.assertIn("aac", command)
        self.assertEqual(self.lines(logs["screencapture"]), [], "no screen and no permission probe for audio")
        folder, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual((project["mode"], project["segments"][0]["files"]), ("audio", {"mic": "media/mic-001.m4a"}))
        self.assertEqual((folder / "media" / "mic-001.m4a").read_bytes(), b"rec")
        self.ok("camera", "--no-mic", "--cam", "facetime")
        self.assertIn("FaceTime HD Camera:none", [line for line in self.lines(logs["ffmpeg"]) if "avfoundation" in line and "-video_size" in line][-1].split("|"))
        folder, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertTrue(folder.name.startswith("camera-"))
        self.assertEqual(project["events"][0]["scene"], "camera")
        code, _, error = self.run_main(capture.main, ["record", "audio", "--no-mic"])
        self.assertEqual(code, 2)
        self.assertIn("needs a microphone", error)
        code, _, error = self.run_main(capture.main, ["record", "camera", "--system-audio"])
        self.assertIn("system audio is recorded with the screen only", error)

    def test_a_failed_save_keeps_the_parts_for_another_try(self) -> None:
        self.media_tools()
        self.ok("record", "--camera")
        status = json.loads(self.ok("status", "--json"))
        self.assertLess(status["elapsed"], 3.0)
        self.assertGreaterEqual(status["elapsed"], 0.6, "the clock starts with the recorders, before the start check")
        with patch.dict(os.environ, {"FAKE_FFMPEG_FAIL": "+faststart"}):
            code, _, error = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 1)
        self.assertIn("saving the screen recording failed", error)
        status = json.loads(self.ok("status", "--json"))
        self.assertEqual(status["phase"], "unsaved")
        self.assertIn("Not saved yet", self.ok("status"))
        folder, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual(project["state"], "ready")
        self.assertTrue((folder / "media" / "screen-001.mp4").is_file())
        self.assertFalse(capture.recording_state_file().exists())

    def test_a_recording_that_cannot_start_explains_permissions(self) -> None:
        self.media_tools()
        with patch.dict(os.environ, {"FAKE_FAIL": "1"}):
            code, _, error = self.run_main(capture.main, ["record"])
        self.assertEqual(code, 1)
        self.assertIn("Screen Recording permission", error)
        self.assertIn("Privacy & Security", error)
        self.assertFalse(capture.recording_state_file().exists())
        projects = storage_path("captures", "projects")
        self.assertEqual(list(projects.iterdir()) if projects.is_dir() else [], [], "no empty project is left behind")
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
        self.assertIn("Saved project:", out)
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
        folder = Path(out.split("Saved project: ", 1)[1].splitlines()[0].strip())
        self.assertEqual(json.loads((folder / "project.json").read_text())["state"], "incomplete")

    def test_ctrl_c_while_saving_keeps_the_recording_for_another_stop(self) -> None:
        self.media_tools()
        self.ok("record", "audio")
        with patch.object(capture, "_finish", side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_main(capture.main, ["stop"])[0], 130)
        self.assertEqual(json.loads(self.ok("status", "--json"))["phase"], "unsaved")
        self.assertTrue(Path(json.loads(self.ok("stop", "--json"))["project"]).is_dir())

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
        self.assertEqual(json.loads(self.ok("status", "--json"))["output"], str(original / "session.mov"))
        self.ok("stop")

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
        folder = Path(state["project"])
        screen = folder / state["segments"][0]["screen"]
        camera = folder / state["segments"][0]["camera"]
        screen.unlink()
        result = json.loads(self.ok("stop", "--json"))
        self.assertFalse(camera.exists(), "remuxed into camera-001.mp4")
        _, project = self.project(result)
        self.assertEqual(project["state"], "incomplete")
        self.assertEqual(project["segments"][0]["files"], {"camera": "media/camera-001.mp4", "mic": "media/mic-001.flac"})
        self.assertIn("part 1: the screen recording is missing", project["problems"])
        self.assertEqual((folder / "media" / "camera-001.mp4").read_bytes(), b"rec")

    def test_partial_recording_state_is_rejected_without_a_traceback(self) -> None:
        self.media_tools()
        self.ok("record")
        self.ok("pause")
        valid = capture._load_state()
        self.ok("stop")
        broken_pid = {**valid, "processes": [{"pid": "bad", "program": "ffmpeg", "track": "mic"}]}
        for state in (
            {"segments": []},
            {**valid, "segments": None},
            broken_pid,
            {**valid, "elapsed": 10**500},
            {**valid, "plan": {**valid["plan"], "display": []}},
            {**valid, "segments": [{"screen": "media/x.mov", "logs": "y"}]},
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

    def project(self, result: dict) -> tuple[Path, dict]:
        folder = Path(result["project"])
        return folder, json.loads((folder / "project.json").read_text())

    def test_scenes_and_marks_are_timestamped(self) -> None:
        self.media_tools()
        self.ok("record", "--camera")
        time.sleep(0.3)
        self.ok("scene", "3")
        time.sleep(0.2)
        self.ok("mark", "intro", "done")
        code, _, error = self.run_main(capture.main, ["scene", "9"])
        self.assertEqual(code, 2)
        self.assertIn("there is no scene 9; scenes: 1 Screen + camera", error)
        _, project = self.project(json.loads(self.ok("stop", "--json")))
        events = project["events"]
        self.assertEqual([event.get("scene") or event.get("mark") for event in events], ["screen-camera", "camera", "intro done"])
        self.assertTrue(0.2 <= events[1]["t"] < events[2]["t"])

    def test_a_stuck_screen_recorder_is_not_killed(self) -> None:
        self.media_tools()
        with patch.object(capture, "STOP_GRACE", 0.3), patch.object(capture, "TERM_GRACE", 0.2), patch.dict(os.environ, {"FAKE_STUCK": "1"}):
            self.ok("record")
            code, out, _ = self.run_main(capture.main, ["stop", "--json"])
            self.assertEqual(code, 1)
            answer = json.loads(out)
            self.assertEqual(answer["stuck"], ["screencapture"])
            status = json.loads(self.ok("status", "--json"))
            self.assertEqual((status["phase"], status["stuck"]), ("stuck", ["screencapture"]))
            folder, project = self.project(answer)
            self.assertEqual(project["state"], "incomplete")
            self.assertTrue((folder / "media" / "mic-001.flac").exists(), "the microphone track is kept")
            done = json.loads(self.ok("stop", "--force", "--json"))
        self.assertEqual(done["state"], "incomplete")
        self.assertFalse(capture.recording_state_file().exists())

    def test_a_camera_that_refuses_nv12_is_retried_without_it(self) -> None:
        logs = self.media_tools()
        with patch.dict(os.environ, {"FAKE_NO_NV12": "1"}):
            self.ok("record", "--camera")
        cameras = [line for line in self.lines(logs["ffmpeg"]) if ":none" in line and "-video_size" in line]
        self.assertEqual(["-pixel_format" in line for line in cameras[-2:]], [True, False])
        self.assertEqual(json.loads(self.ok("status", "--json"))["phase"], "recording")

    def test_the_camera_is_encoded_with_libx264_when_ffmpeg_has_it(self) -> None:
        # screencapture keeps the Mac's video encoder busy at full resolution: a camera on
        # h264_videotoolbox then got 2-5 frames a second, so it is encoded on the CPU.
        logs = self.media_tools()
        self.ok("record", "--camera")
        self.ok("stop")
        cameras = [line for line in self.lines(logs["ffmpeg"]) if ":none" in line and "-video_size" in line]
        self.assertIn("|-c:v|libx264|", "|" + cameras[-1] + "|")
        with patch.dict(os.environ, {"FAKE_NO_X264": "1"}):
            self.ok("record", "--camera")
            self.ok("stop")
        cameras = [line for line in self.lines(logs["ffmpeg"]) if ":none" in line and "-video_size" in line]
        self.assertIn("|-c:v|h264_videotoolbox|", "|" + cameras[-1] + "|")

    def native(self) -> Path:
        self.media_tools()
        log = self.tool("ul-rec", body=FAKE_UL_REC)
        environment = patch.dict(os.environ, {"UNLAW_CAPTURE_REC": str(self.bin / "ul-rec")})
        environment.start()
        self.addCleanup(environment.stop)
        return log

    def test_the_native_recorder_records_every_track_in_one_process(self) -> None:
        log = self.native()
        self.ok("record", "--camera")
        state = json.loads(capture.recording_state_file().read_text())
        self.assertEqual(state["plan"]["engine"], "native")
        self.assertEqual({item["program"] for item in state["processes"]}, {"ul-rec"})
        self.assertEqual({item["track"] for item in state["processes"]}, {"screen", "camera", "mic"})
        self.assertEqual(len({item["pid"] for item in state["processes"]}), 1, "one process records everything")
        request = json.loads(Path(next(line for line in self.lines(log) if line.endswith(".json"))).read_text())
        self.assertEqual(request["camera"]["device"], "default")
        self.assertEqual((request["camera"]["width"], request["camera"]["height"]), (1920, 1080))
        self.assertEqual(request["mic"]["format"], "wav", "flac is made from a WAV at stop")
        self.assertFalse(any(line.startswith("-v") for line in self.lines(self.root / "screencapture.log")))
        time.sleep(0.3)
        self.assertEqual(json.loads(self.ok("status", "--json"))["level_db"], -21.5)
        self.ok("pause")
        self.ok("resume")
        folder, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual(project["state"], "ready", project["problems"])
        self.assertEqual(len(project["segments"]), 2)
        for number, segment in enumerate(project["segments"], 1):
            # Exact starts from the recorder's clock, not guessed from when the tools stopped.
            self.assertEqual(segment["starts"], {"screen": 0.0, "mic": 0.25, "camera": 0.75})
            self.assertEqual(segment["duration"], 3.25)
            self.assertEqual(segment["files"]["mic"], f"media/mic-{number:03d}.flac")
            self.assertEqual(segment["files"]["screen"], f"media/screen-{number:03d}.mp4")
            self.assertEqual(segment["files"]["camera"], f"media/camera-{number:03d}.mp4")
        self.assertTrue((folder / "media" / "mic-001.flac").is_file())
        self.assertFalse((folder / "media" / ".mic-001.wav").exists())

    def test_the_native_recorder_reports_a_track_that_cannot_start(self) -> None:
        self.native()
        with patch.dict(os.environ, {"FAKE_REC_FAIL": "camera"}):
            code, _, error = self.run_main(capture.main, ["record", "--camera"])
        self.assertEqual(code, 1)
        self.assertIn("the camera recorder could not start: the camera is busy or not allowed", error)
        self.assertFalse(capture.recording_state_file().exists())
        self.assertTrue((self.bin / "ul-rec.exit").exists(), "the recorder was stopped")

    def test_the_native_recorder_reports_a_track_lost_mid_recording(self) -> None:
        self.native()
        with patch.dict(os.environ, {"FAKE_REC_DROP": "camera"}):
            self.ok("record", "--camera")
            time.sleep(0.8)
            status = json.loads(self.ok("status", "--json"))
        self.assertIn("the camera recording stopped: the device was disconnected", status["warnings"])
        _, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual(project["state"], "incomplete")
        self.assertIn("part 1: the camera recording stopped: the device was disconnected", project["problems"])

    def test_a_failed_native_resume_leaves_no_files_and_the_retry_works(self) -> None:
        self.native()
        self.ok("record", "--camera")
        self.ok("pause")
        folder = Path(json.loads(self.ok("status", "--json"))["project"])
        (folder / "logs" / "rec.log").write_text("ul-rec: an old error from part 1\n")
        with patch.dict(os.environ, {"FAKE_REC_FAIL": "camera"}):
            code, _, error = self.run_main(capture.main, ["resume"])
        self.assertEqual(code, 1)
        self.assertNotIn("old error", error)
        self.assertEqual(sorted(path.name for path in (folder / "media").glob("*002*")), [], "the failed part leaves nothing")
        self.ok("resume")
        _, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual(len(project["segments"]), 2)

    def test_a_reused_pid_is_not_taken_for_a_recorder(self) -> None:
        def ps(command: str):
            return patch.object(capture.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, command, ""))

        with patch.object(capture.os, "kill"), patch.object(capture.os, "waitpid", side_effect=ChildProcessError):
            with ps("/Users/x/.local/bin/ul-rec /p/logs/rec-001.json\n"):
                self.assertTrue(capture._alive(4242, "ul-rec"))
            with ps("/usr/bin/python3 /tmp/bin/ffmpeg -f avfoundation\n"):
                self.assertTrue(capture._alive(4242, "ffmpeg"), "a script tool runs under its interpreter")
            with ps("cargo build --bin ul-rec\n"):
                self.assertFalse(capture._alive(4242, "ul-rec"), "a command that only mentions the name")
            with ps("nvim rust/src/bin/ul-rec.rs\n"):
                self.assertFalse(capture._alive(4242, "ul-rec"))

    def test_without_ffmpeg_the_native_microphone_stays_a_wav(self) -> None:
        self.native()
        (self.bin / "ffmpeg").unlink()
        self.ok("record", "--mic", "default")
        _, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual(project["segments"][0]["files"]["mic"], "media/mic-001.wav")
        self.assertEqual(project["segments"][0]["files"]["screen"], "media/screen-001.mov")

    def test_the_native_recorder_picks_devices_by_name_without_ffmpeg(self) -> None:
        log = self.native()
        (self.bin / "ffmpeg").unlink()
        self.ok("record", "--camera", "--cam", "studio cam", "--mic", "Studio Mic")
        request = json.loads(Path(self.lines(log)[-1]).read_text())
        self.assertEqual(request["camera"]["device"], "Studio Cam")
        self.assertEqual(request["mic"]["device"], "Studio Mic")
        self.assertEqual((request["camera"]["width"], request["camera"]["fps"]), (1920, "30.000000"))
        self.ok("stop")

    def test_record_returns_once_the_microphone_and_camera_deliver(self) -> None:
        # The microphone and the camera need a second or two to wake up; "recording" is only
        # reported once they deliver, so the first words are not lost.
        self.media_tools()
        with patch.dict(os.environ, {"FAKE_SLOW_START": "1.5"}):
            started = time.monotonic()
            answer = json.loads(self.ok("record", "--camera", "--json"))
            waited = time.monotonic() - started
        folder = Path(answer["project"])
        self.assertGreater(waited, 1.5)
        self.assertTrue((folder / "logs" / "mic-levels.txt").read_text().strip(), "the microphone already delivers")
        self.assertGreater((folder / "media" / ".camera-001.mp4").stat().st_size, 0, "the camera already delivers")
        self.ok("stop")

    def test_status_warns_about_a_silent_microphone(self) -> None:
        self.media_tools()
        with patch.object(capture, "SILENCE_SECONDS", 0.5), patch.dict(os.environ, {"FAKE_SILENT": "1"}):
            self.ok("record")
            time.sleep(1.0)
            status = json.loads(self.ok("status", "--json"))
        self.assertLess(status["level_db"], -60)
        self.assertTrue(any("microphone is silent" in warning for warning in status["warnings"]))
        self.ok("stop")
        self.ok("record")
        time.sleep(0.5)
        status = json.loads(self.ok("status", "--json"))
        self.assertEqual(status["level_db"], -21.5)
        self.assertFalse(any("silent" in warning for warning in status["warnings"]))

    def test_a_dying_camera_leaves_a_project_with_the_rest(self) -> None:
        self.media_tools()
        with patch.dict(os.environ, {"FAKE_RECORDER_DIES": "0.9"}):
            self.ok("record", "--camera")
            time.sleep(1.4)
            self.assertEqual(json.loads(self.ok("status", "--json"))["phase"], "interrupted")
        _, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual(project["state"], "incomplete")
        self.assertIn("screen", project["segments"][0]["files"])
        self.assertTrue(any("stopped during the recording" in problem for problem in project["problems"]))

    def test_a_recorder_that_died_keeps_its_place_on_the_timeline(self) -> None:
        # The camera died after ~1 s of a 10 s part: its footage belongs at the start, not at the end
        # (only recorders that stop together have their ends lined up).
        self.media_tools()
        durations = {"screen-": 10.0, "camera-": 1.0, "mic-": 10.0}
        with patch.dict(os.environ, {"FAKE_RECORDER_DIES": "0.9", "FAKE_PROBE_DURATIONS": json.dumps(durations)}):
            self.ok("record", "--camera", "--no-mic")
            time.sleep(1.4)
            _, project = self.project(json.loads(self.ok("stop", "--json")))
        starts = project["segments"][0]["starts"]
        self.assertEqual(starts["camera"], 0.0)
        self.assertEqual(project["segments"][0]["duration"], 10.0)

    def test_a_recorder_that_died_before_a_pause_is_reported(self) -> None:
        self.media_tools()
        with patch.dict(os.environ, {"FAKE_RECORDER_DIES": "0.9"}):
            self.ok("record", "--camera", "--no-mic")
            time.sleep(1.4)
            self.ok("pause")
        _, project = self.project(json.loads(self.ok("stop", "--json")))
        self.assertEqual(project["state"], "incomplete")
        self.assertTrue(
            any("part 1: the camera recorder stopped during the recording" in problem for problem in project["problems"]),
            project["problems"],
        )

    def test_stop_right_after_start_saves(self) -> None:
        self.media_tools()
        self.ok("record")
        result = json.loads(self.ok("stop", "--json"))
        self.assertIn(result["state"], ("ready", "incomplete"))

    def test_start_while_saving_answers_at_once(self) -> None:
        self.media_tools()
        state = capture.recording_state_file()
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"phase": "saving"}))
        with capture._locked():
            started = time.monotonic()
            code, _, error = self.run_main(capture.main, ["record"])
        self.assertLess(time.monotonic() - started, 6)
        self.assertEqual(code, 1)
        self.assertIn("still saving", error)
        state.unlink()

    def test_a_version_1_state_is_wrapped_into_a_project(self) -> None:
        self.media_tools()
        parts = storage_path("captures", ".parts", "screen-1")
        parts.mkdir(parents=True)
        (parts / "000-screen.mov").write_bytes(b"old screen")
        output = storage_path("captures", "recordings", "screen-old.mov")
        capture.recording_state_file().write_text(json.dumps({
            "mode": "screen", "output": str(output), "parts": str(parts), "started": "2026-11-18T10:00:00+00:00",
            "elapsed": 4.0, "segments": [{"screen": str(parts / "000-screen.mov")}], "processes": [], "paused": True,
            "phase": "paused", "warnings": [], "plan": {"mode": "screen", "display": 1},
        }))
        result = json.loads(self.ok("stop", "--json"))
        folder, project = self.project(result)
        self.assertEqual(project["segments"][0]["files"], {"screen": "media/screen-001.mp4"})
        self.assertEqual((folder / "media" / "screen-001.mp4").read_bytes(), b"old screen")
        self.assertFalse(parts.exists())

    def test_new_argument_errors(self) -> None:
        cases = {
            ("record", "--canvas", "21:9"): "--canvas must be one of 16:9, 9:16, 1:1, 4:5, source",
            ("record", "--cam-quality", "ultra"): "--cam-quality must be max, high or light",
            ("record", "--mic-format", "ogg"): "--mic-format must be flac, wav or m4a",
            ("record", "--countdown", "x"): "--countdown needs a whole number from 0",
            ("export",): "usage: ul capture export",
            ("export", "last", "--height", "720"): "--height must be 1080, 1440 or 2160",
            ("export", "last", "--fps", "24"): "--fps must be 30 or 60",
            ("export", "last", "--canvas", "3:2"): "--canvas must be one of",
            ("scene",): "usage: ul capture scene",
            ("project",): "usage: ul capture project",
            ("doctor", "--open", "keys"): "--open takes screen, camera or microphone",
        }
        for args, message in cases.items():
            with self.subTest(args=args):
                code, _, error = self.run_main(capture.main, list(args))
                self.assertEqual(code, 2)
                self.assertIn(message, error)

    def test_projects_export_and_json_contracts(self) -> None:
        self.media_tools()
        code, _, error = self.run_main(capture.main, ["export", "last"])
        self.assertEqual(code, 2)
        self.assertIn("no Studio projects yet", error)
        self.ok("record")
        stop = json.loads(self.ok("stop", "--json"))
        listed = json.loads(self.ok("projects", "--json"))
        self.assertEqual(listed[0]["path"], stop["project"])
        self.assertEqual((listed[0]["state"], listed[0]["mode"]), ("ready", "screen"))
        self.assertIn(Path(stop["project"]).name, self.ok("projects"))
        out = json.loads(self.ok("export", "last", "--canvas", "source", "--format", "mp4", "--json"))
        self.assertTrue(out["saved"].endswith(" source.mp4"))
        self.assertEqual(out["project"], stop["project"])
        self.assertEqual(json.loads(self.ok("export", "--status", "--json"))["phase"], "done")
        detail = json.loads(self.ok("project", "last", "--json"))
        self.assertEqual(detail["path"], stop["project"])
        self.assertEqual(detail["exports"][0]["path"], out["saved"])
        self.assertEqual(json.loads(self.ok("project", Path(stop["project"]).name, "--json"))["path"], stop["project"])

    def test_project_edits_keep_what_was_recorded(self) -> None:
        self.media_tools()
        self.ok("record")
        folder = Path(json.loads(self.ok("stop", "--json"))["project"])
        project = json.loads(self.ok("project", "last", "--json"))
        project["layouts"]["16:9"]["screen"]["background"] = {"kind": "color", "color": "#112233"}
        project["segments"] = []
        project["state"] = "ready"
        project["exports"] = [{"path": "/etc/passwd"}]
        with patch.object(capture.sys, "stdin", io.StringIO(json.dumps(project))):
            self.ok("project", str(folder), "--set-json", "-")
        saved = json.loads((folder / "project.json").read_text())
        self.assertEqual(saved["layouts"]["16:9"]["screen"]["background"]["color"], "#112233")
        self.assertEqual(len(saved["segments"]), 1, "recorded segments are never replaced")
        self.assertEqual(saved["exports"], [])
        project["layouts"]["16:9"]["screen"]["background"] = {"kind": "color", "color": "red"}
        with patch.object(capture.sys, "stdin", io.StringIO(json.dumps(project))):
            code, _, error = self.run_main(capture.main, ["project", str(folder), "--set-json", "-"])
        self.assertEqual(code, 2)
        self.assertIn("colour", error)

    def test_record_output_still_gives_a_file(self) -> None:
        self.media_tools()
        original = self.root / "start"
        original.mkdir()
        os.chdir(original)
        self.ok("record", "--output", "talk.mp4")
        os.chdir(self.root)
        result = json.loads(self.ok("stop", "--json"))
        self.assertEqual(result["saved"], str(original / "talk.mp4"), "the file name's extension picks the container")
        self.assertTrue((original / "talk.mp4").is_file())
        self.assertTrue(Path(result["project"]).is_dir(), "the project stays for other formats")
        self.ok("record")
        result = json.loads(self.ok("stop", "--export", "--canvas", "9:16", "--json"))
        self.assertTrue(result["saved"].endswith(" 9x16.mov"))

    def test_setup_round_trip_and_doctor(self) -> None:
        logs = self.media_tools()
        setup = json.loads(self.ok("setup", "--json"))
        self.assertEqual(setup["canvas"], "16:9")
        setup["canvas"] = "9:16"
        with patch.object(capture.sys, "stdin", io.StringIO(json.dumps(setup))):
            self.ok("setup", "--set-json", "-")
        self.assertEqual(json.loads(self.ok("setup", "--json"))["canvas"], "9:16")
        setup["countdown"] = 99
        with patch.object(capture.sys, "stdin", io.StringIO(json.dumps(setup))):
            code, _, error = self.run_main(capture.main, ["setup", "--set-json", "-"])
        self.assertEqual(code, 2)
        self.assertIn("setup.countdown", error)
        self.ok("setup", "--reset")
        self.assertEqual(json.loads(self.ok("setup", "--json"))["canvas"], "16:9")
        doctor = json.loads(self.ok("doctor", "--json"))
        self.assertEqual((doctor["screen"], doctor["ffmpeg"]), (True, True))
        self.assertIn("app", doctor)
        self.assertIn("Screen Recording: allowed", self.ok("doctor"))
        self.ok("doctor", "--open", "camera")
        self.assertEqual(self.lines(logs["open"])[-1], "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera")

    def test_devices_with_camera_modes(self) -> None:
        self.media_tools()
        data = json.loads(self.ok("devices", "--modes", "--json"))
        self.assertEqual(data["modes"]["FaceTime HD Camera"][0]["width"], 1920)
        self.assertIn("1920x1080 15-30 fps", self.ok("devices", "--modes", "--camera", "facetime"))

    def test_delete_moves_a_project_to_the_trash(self) -> None:
        self.media_tools()
        self.ok("record")
        folder = Path(json.loads(self.ok("stop", "--json"))["project"])
        self.assertIn("Moved to the Trash", self.ok("delete", folder.name))
        self.assertFalse(folder.exists())
        self.assertTrue((self.root / "home" / ".Trash" / folder.name / "project.json").is_file())

    def test_help_is_static_and_lists_new_actions(self) -> None:
        help_text = self.ok("--help")
        for word in ("record [screen", "scene", "mark", "projects", "export", "setup", "doctor", "--canvas", "--cam-quality", "--mic-format", "stop --force"):
            self.assertIn(word, help_text)

    def test_menubar_helper_follows_the_recording(self) -> None:
        logs = self.media_tools()
        self.tool("osascript", body="import signal, time\nif '-l' in sys.argv:\n    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n    while True:\n        time.sleep(0.05)\n")
        with patch.dict(os.environ, {"UNLAW_BIN": "/fake/ul"}):
            self.ok("record")
            helpers = capture._load_state()["helpers"]
            self.assertEqual([item["program"] for item in helpers], ["osascript"])
            deadline = time.monotonic() + 5
            while not logs["osascript"].exists() and time.monotonic() < deadline:
                time.sleep(0.05)  # the helper is detached; it logs when it starts
            content = logs["osascript"].read_text()
            self.assertIn("-l|JavaScript|-e|", content)
            self.assertIn("NSStatusBar", content)
            self.assertTrue(content.rstrip().endswith(f"|/fake/ul|{capture.recording_state_file()}"))
            self.ok("stop")
            deadline = time.monotonic() + 5
            while capture._alive(helpers[0]["pid"], "osascript") and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(capture._alive(helpers[0]["pid"], "osascript"), "the helper quits with the recording")
            setup = json.loads(self.ok("setup", "--json"))
            setup["menubar"] = False
            with patch.object(capture.sys, "stdin", io.StringIO(json.dumps(setup))):
                self.ok("setup", "--set-json", "-")
            before = logs["osascript"].read_text()
            self.ok("record")
            self.assertEqual(capture._load_state()["helpers"], [])
            self.ok("stop")
            self.assertEqual(logs["osascript"].read_text(), before)

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
    def test_music_without_a_track_only_opens_spotify(self) -> None:
        opened, script = self.tool("open"), self.tool("osascript")
        self.assertEqual(self.run_main(music.main, [])[0], 0)
        self.assertEqual(self.lines(opened), ["-a|Spotify"])
        self.assertEqual(self.lines(script), [], "no search and no keystrokes")

    def test_music_with_a_track_opens_spotify_then_searches(self) -> None:
        opened, script = self.tool("open"), self.tool("osascript")
        self.assertEqual(self.run_main(music.main, ["Take", "Me", "Out"])[0], 0)
        self.assertEqual(self.lines(opened), ["-a|Spotify"])
        self.assertIn('open location "spotify:search:Take%20Me%20Out"', script.read_text())

    def test_music_without_the_app_uses_the_web_player(self) -> None:
        opened = self.tool("open", body="if sys.argv[1] == '-a': raise SystemExit(1)\n")
        script = self.tool("osascript")
        self.assertEqual(self.run_main(music.main, ["Take Me Out"])[0], 0)
        self.assertEqual(self.lines(opened), ["-a|Spotify", "https://open.spotify.com/search/Take%20Me%20Out"])
        self.assertEqual(self.lines(script), [])
        self.assertEqual(self.run_main(music.main, [])[0], 0)
        self.assertEqual(self.lines(opened)[-1], "https://open.spotify.com/")

    def test_music_query_is_escaped_for_applescript(self) -> None:
        self.tool("open")
        log = self.tool("osascript")
        set_config_value("apps.spotify_autoplay_delay", 0.5)
        self.assertEqual(self.run_main(music.main, ['say "hi" \\ now'])[0], 0)
        script = log.read_text().split("|", 1)[1]
        self.assertIn('set searchQuery to "say \\"hi\\" \\\\ now"', script)
        self.assertIn("spotify:search:say%20%22hi%22%20%5C%20now", script)
        self.assertIn("delay 0.5", script)

    def test_music_failures(self) -> None:
        self.tool("open")
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
