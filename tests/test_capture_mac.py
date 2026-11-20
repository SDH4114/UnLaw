"""The macOS backend of `ul capture` (`capture_mac.py`), with fake tools on a restricted PATH."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "capture"
sys.path.insert(0, str(ROOT / "src"))

from unlawful import capture_mac  # noqa: E402
from unlawful.config import ensure_layout, storage_path  # noqa: E402

PLAN = {
    "display": 2,
    "area": None,
    "clicks": True,
    "system": True,
    "camera": "Haos's Phone Camera",
    "mode": {"width": 1920, "height": 1080, "fps": "30.000000"},
    "bitrate": 6_000_000,
    "mic": "Haos's Phone Microphone «Ü»",
    "mic_format": "flac",
}


class MacBackendTests(unittest.TestCase):
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
        self.backend = capture_mac.MacBackend()

    def tool(self, name: str, body: str) -> Path:
        log = self.root / f"{name}.log"
        script = self.bin / name
        script.write_text(
            f"#!{sys.executable}\nimport sys\nopen({str(log)!r}, 'a').write('|'.join(sys.argv[1:]) + '\\n')\n{body}",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return log

    def test_modes_are_parsed_and_picked(self) -> None:
        modes = capture_mac.parse_modes((FIXTURES / "camera-modes.txt").read_text())
        self.assertEqual(len(modes), 7)
        self.assertIn(
            {
                "width": 1920,
                "height": 1080,
                "min_fps": "15.000000",
                "max_fps": "30.000000",
            },
            modes,
        )
        pick = capture_mac.pick_mode
        self.assertEqual(
            pick(modes, "high"), {"width": 1920, "height": 1080, "fps": "30.000000"}
        )
        self.assertEqual(
            pick(modes, "max"), {"width": 1920, "height": 1080, "fps": "30.000000"}
        )
        self.assertEqual(
            pick(modes, "light"), {"width": 1280, "height": 720, "fps": "30.000000"}
        )
        square = [
            {
                "width": 1552,
                "height": 1552,
                "min_fps": "1.000000",
                "max_fps": "30.000030",
            }
        ]
        self.assertEqual(
            pick(square, "high"), {"width": 1552, "height": 1552, "fps": "30.000030"}
        )
        self.assertEqual(
            pick(modes, "high", "1280x720@30"),
            {"width": 1280, "height": 720, "fps": "30.000000"},
        )
        self.assertEqual(
            pick(modes, "high", "999x999@30"),
            {"width": 1920, "height": 1080, "fps": "30.000000"},
        )
        self.assertIsNone(pick([], "high"))

    def test_camera_modes_are_probed_once_and_cached(self) -> None:
        log = self.tool(
            "ffmpeg",
            f"sys.stderr.write(open({str(FIXTURES / 'camera-modes.txt')!r}).read())\nraise SystemExit(1)\n",
        )
        first = self.backend.camera_modes("FaceTime HD Camera")
        second = self.backend.camera_modes("FaceTime HD Camera")
        self.assertEqual(first, second)
        self.assertEqual(len(log.read_text().splitlines()), 1)
        self.assertIn("-framerate|1000|-i|FaceTime HD Camera:none", log.read_text())
        cache = json.loads(storage_path("runtime", "camera-modes.json").read_text())
        self.assertIn("FaceTime HD Camera", cache)
        self.backend.camera_modes("FaceTime HD Camera", refresh=True)
        self.assertEqual(len(log.read_text().splitlines()), 2)

    def test_ul_rec_is_used_next_to_ul_on_macos_15_or_later(self) -> None:
        rec = self.bin / "ul-rec"
        rec.write_text("#!/bin/sh\n")
        rec.chmod(0o755)
        environment = {"UNLAW_BIN": str(self.bin / "ul")}
        with patch.dict(os.environ, environment), patch.object(capture_mac, "macos_major", return_value=15):
            os.environ.pop("UNLAW_CAPTURE_REC", None)
            self.assertEqual(self.backend.native_recorder(), str(rec))
        with patch.dict(os.environ, environment), patch.object(capture_mac, "macos_major", return_value=14):
            os.environ.pop("UNLAW_CAPTURE_REC", None)
            self.assertIsNone(self.backend.native_recorder(), "SCRecordingOutput needs macOS 15")
        with patch.dict(os.environ, {**environment, "UNLAW_CAPTURE_REC": "off"}):
            self.assertIsNone(self.backend.native_recorder(), "off goes back to screencapture and ffmpeg")
        rec.chmod(0o644)
        with patch.dict(os.environ, {"UNLAW_CAPTURE_REC": str(rec)}):
            self.assertIsNone(self.backend.native_recorder(), "only an executable")

    def test_ul_rec_request_carries_the_plan(self) -> None:
        plan = {
            "display": 2, "area": "0,0,800,600", "clicks": False, "system": True, "camera": "FaceTime HD Camera",
            "mode": {"width": 1920, "height": 1080, "fps": "30.000030"}, "bitrate": 8_000_000, "mic": "default",
        }
        files = {"screen": Path("/p/.screen-001.mov"), "camera": Path("/p/.camera-001.mov"), "mic": Path("/p/.mic-001.wav")}
        request = self.backend.native_request(plan, files, Path("/p/rec.jsonl"), Path("/p/levels.txt"))
        self.assertEqual(request["screen"], {
            "path": "/p/.screen-001.mov", "display": 2, "area": "0,0,800,600", "clicks": False, "system_audio": True, "fps": 60,
        })
        self.assertEqual(request["camera"], {
            "path": "/p/.camera-001.mov", "device": "FaceTime HD Camera", "width": 1920, "height": 1080,
            "fps": "30.000030", "bitrate": 8_000_000,
        })
        self.assertEqual(request["mic"], {"path": "/p/.mic-001.wav", "device": "default", "format": "wav"})
        only_mic = self.backend.native_request(plan, {"mic": Path("/p/mic-001.m4a")}, Path("/e"), Path("/l"))
        self.assertEqual((only_mic["screen"], only_mic["camera"], only_mic["mic"]["format"]), (None, None, "m4a"))

    def test_camera_on_libx264_keeps_bitrate_and_420(self) -> None:
        camera = self.backend.camera_argv({**PLAN, "encoder": "libx264"}, Path("c.mp4"))
        self.assertEqual(camera[camera.index("-c:v") + 1], "libx264")
        self.assertEqual(camera[camera.index("-preset") + 1], "veryfast")
        self.assertEqual(camera[camera.index("-pix_fmt") + 1], "yuv420p")
        self.assertEqual(camera[camera.index("-b:v") + 1], "6000000")
        self.assertEqual(camera[camera.index("-maxrate") + 1], "9000000")
        self.assertEqual(camera[camera.index("-g") + 1], "30")
        self.assertEqual(camera[-1], "c.mp4")
        old = self.backend.camera_argv(PLAN, Path("c.mp4"))
        self.assertEqual(old[old.index("-c:v") + 1], "h264_videotoolbox", "a state from 3.21.0 has no encoder")

    def test_device_names_stay_one_argument(self) -> None:
        camera = self.backend.camera_argv(PLAN, Path("c.mp4"))
        self.assertIn("Haos's Phone Camera:none", camera)
        self.assertEqual(camera[camera.index("-framerate") + 1], "30.000000")
        self.assertEqual(camera[camera.index("-video_size") + 1], "1920x1080")
        self.assertEqual(camera[camera.index("-b:v") + 1], "6000000")
        self.assertEqual(camera[camera.index("-g") + 1], "30")
        self.assertIn("+frag_keyframe+empty_moov+default_base_moof", camera)
        self.assertEqual(camera[-1], "c.mp4")
        self.assertNotIn(
            "-pixel_format", self.backend.camera_argv(PLAN, Path("c.mp4"), nv12=False)
        )
        mic = self.backend.mic_argv(PLAN, Path("m.flac"))
        self.assertIn(":Haos's Phone Microphone «Ü»", mic)
        self.assertIn("mic-levels.txt", mic[mic.index("-filter_complex") + 1])
        self.assertEqual(mic[mic.index("-c:a") + 1], "flac")
        self.assertEqual(
            self.backend.screen_argv(PLAN, Path("s.mov")),
            ["screencapture", "-v", "-x", "-D2", "-k", "-A", "s.mov"],
        )
        quiet = dict(PLAN, area="10,20,800,600", clicks=False, system=False)
        self.assertEqual(
            self.backend.screen_argv(quiet, Path("s.mov")),
            ["screencapture", "-v", "-x", "-D2", "-R10,20,800,600", "s.mov"],
        )
        m4a = self.backend.mic_argv(dict(PLAN, mic_format="m4a"), Path("m.m4a"))
        self.assertEqual(m4a[m4a.index("-c:a") + 1], "aac")

    def test_responsible_app_skips_python(self) -> None:
        chain = {
            500: "400 /opt/homebrew/Cellar/python@3.15/3.15.2/Frameworks/Python.framework/Versions/3.15/Resources/Python.app/Contents/MacOS/Python",
            400: "300 -zsh",
            300: "200 /usr/bin/login",
            200: "1 /Applications/Ghostty.app/Contents/MacOS/ghostty",
        }
        self.tool("ps", f"chain = {chain!r}\nprint(chain.get(int(sys.argv[-1]), ''))\n")
        self.assertEqual(self.backend.responsible_app(500), "Ghostty")
        self.tool("ps", "print('1 /bin/zsh')\n")
        self.assertIsNone(self.backend.responsible_app(500))

    def test_permission_probe(self) -> None:
        # The real tool refuses hidden file names for screenshots (and exits 0), so the probe must not use one.
        self.tool(
            "screencapture",
            "import os\nif not os.path.basename(sys.argv[-1]).startswith('.'):\n    open(sys.argv[-1], 'wb').write(b'png')\n",
        )
        self.assertEqual(self.backend.permission_probe(), {"screen": True})
        self.tool("screencapture", "raise SystemExit(1)\n")
        self.assertEqual(self.backend.permission_probe(), {"screen": False})

    def test_settings_urls(self) -> None:
        url = self.backend.settings_url
        self.assertEqual(
            url("screen"),
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
        )
        self.assertEqual(
            url("camera"),
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
        )
        self.assertEqual(
            url("microphone"),
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
        )
        with self.assertRaises(ValueError):
            url("keychain")


if __name__ == "__main__":
    unittest.main()
