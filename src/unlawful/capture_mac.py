"""The macOS side of `ul capture`: devices, recorder commands, permissions.

Everything that names `screencapture`, AVFoundation or System Settings lives
here, so a Windows or Linux backend can replace this one module.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .config import storage_path

# Virtual devices that carry app audio, not a voice; picking one as the microphone is a common mistake.
VIRTUAL_WORDS = (
    "blackhole",
    "loopback",
    "soundflower",
    "teams audio",
    "zoomaudio",
    "aggregate",
)
SETTINGS_PANES = {
    "screen": "Privacy_ScreenCapture",
    "camera": "Privacy_Camera",
    "microphone": "Privacy_Microphone",
}
_MODE_LINE = re.compile(r"(\d+)x(\d+)@\[([0-9.]+) ([0-9.]+)\]fps")
_TARGET_HEIGHT = {"max": 1080, "high": 1080, "light": 720}
FFMPEG_QUIET = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
LEVELS_FILE = "mic-levels.txt"


# The menu-bar helper (osascript -l JavaScript): a status item that shows the recording clock and runs
# `ul capture <action>` through NSTask with an argument array (no shell). It reads the state file once a
# second and quits when the recording ends. argv: [ul binary, state file].
MENUBAR_JS = r"""
ObjC.import('Cocoa');
function readJSON(path) {
  const text = $.NSString.stringWithContentsOfFileEncodingError(path, $.NSUTF8StringEncoding, null);
  if (text.isNil()) return null;
  try { return JSON.parse(ObjC.unwrap(text)); } catch (error) { return null; }
}
function clock(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60, s = seconds % 60;
  const two = (n) => (n < 10 ? '0' : '') + n;
  return (h ? h + ':' + two(m) : two(m)) + ':' + two(s);
}
function run(argv) {
  const ul = argv[0], statePath = argv[1];
  const first = readJSON(statePath);
  if (!first || !first.project) return;
  const project = readJSON(first.project + '/project.json') || {};
  const scenes = Array.isArray(project.scenes) ? project.scenes : [];
  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  ObjC.registerSubclass({
    name: 'UnlawRecordingMenu',
    methods: {
      'act:': {
        types: ['void', ['id']],
        implementation: function (sender) {
          const task = $.NSTask.alloc.init;
          task.launchPath = ul;
          task.arguments = ObjC.wrap(JSON.parse(ObjC.unwrap(sender.representedObject)));
          task.launch;
        },
      },
    },
  });
  const target = $.UnlawRecordingMenu.alloc.init;
  const item = $.NSStatusBar.systemStatusBar.statusItemWithLength($.NSVariableStatusItemLength);
  let shown = '';
  function entry(menu, title, args, checked) {
    const row = $.NSMenuItem.alloc.initWithTitleActionKeyEquivalent(title, 'act:', '');
    row.target = target;
    row.representedObject = $(JSON.stringify(args));
    if (checked) row.state = $.NSControlStateValueOn;
    menu.addItem(row);
  }
  function build(state) {
    const menu = $.NSMenu.alloc.init;
    entry(menu, 'Stop and save', ['capture', 'stop'], false);
    entry(menu, state.paused ? 'Resume' : 'Pause', ['capture', state.paused ? 'resume' : 'pause'], false);
    menu.addItem($.NSMenuItem.separatorItem);
    scenes.forEach((scene, index) => entry(menu, (index + 1) + '  ' + scene.name, ['capture', 'scene', scene.id], scene.id === state.scene));
    menu.addItem($.NSMenuItem.separatorItem);
    entry(menu, 'Add mark', ['capture', 'mark'], false);
    entry(menu, 'Open Studio', ['desk'], false);
    item.menu = menu;
  }
  const mask = $.NSEventMaskAny || $.NSAnyEventMask;
  while (true) {
    const state = readJSON(statePath);
    if (!state || state.project !== first.project) break;
    const running = state.segment_started && !state.paused;
    const elapsed = state.elapsed + (running ? Date.now() / 1000 - state.segment_started : 0);
    item.button.title = (state.paused ? '❚❚ ' : '● ') + clock(elapsed);
    const key = [state.phase, state.paused, state.scene].join('|');
    if (key !== shown) { build(state); shown = key; }
    const until = $.NSDate.dateWithTimeIntervalSinceNow(1.0);
    while (true) {
      const event = app.nextEventMatchingMaskUntilDateInModeDequeue(mask, until, $.NSDefaultRunLoopMode, true);
      if (event.isNil()) break;
      app.sendEvent(event);
    }
  }
  $.NSStatusBar.systemStatusBar.removeStatusItem(item);
}
"""


class BackendError(Exception):
    """Recording is not possible here (wrong system, missing tool)."""


def virtual_device(name: str) -> bool:
    return any(word in name.casefold() for word in VIRTUAL_WORDS)


def parse_modes(text: str) -> list[dict]:
    """`WxH@[min max]fps` lines that ffmpeg prints when a camera refuses a framerate."""
    modes = []
    for match in _MODE_LINE.finditer(text):
        mode = {
            "width": int(match[1]),
            "height": int(match[2]),
            "min_fps": match[3],
            "max_fps": match[4],
        }
        if mode not in modes:
            modes.append(mode)
    return modes


def _fps_string(mode: dict, wanted: float) -> str | None:
    low, high = float(mode["min_fps"]), float(mode["max_fps"])
    if abs(wanted - high) < 0.01:
        return mode["max_fps"]
    if abs(wanted - low) < 0.01:
        return mode["min_fps"]
    if low <= wanted <= high:
        return f"{wanted:.6f}"
    return None


def pick_mode(modes: list[dict], quality: str, wanted: str = "auto") -> dict | None:
    """The mode to record: the one asked for when the camera has it, else 1080p (720p for `light`) at the
    highest framerate, else the largest 16:9 mode, else the largest. Framerates stay the device's own strings."""
    if not modes:
        return None
    if wanted != "auto":
        size, _, rate = wanted.partition("@")
        width, _, height = size.partition("x")
        for mode in modes:
            if f"{mode['width']}x{mode['height']}" == f"{width}x{height}":
                fps = _fps_string(mode, float(rate or mode["max_fps"]))
                if fps:
                    return {
                        "width": mode["width"],
                        "height": mode["height"],
                        "fps": fps,
                    }

    def best(mode: dict) -> dict:
        fps = mode["max_fps"] if float(mode["max_fps"]) <= 60.5 else "60.000000"
        return {"width": mode["width"], "height": mode["height"], "fps": fps}

    def rate(mode: dict) -> float:
        return min(float(mode["max_fps"]), 60.5)

    target = _TARGET_HEIGHT.get(quality, 1080)
    wide = [mode for mode in modes if mode["width"] * 9 == mode["height"] * 16]
    exact = [mode for mode in wide if mode["height"] == target]
    if exact:
        return best(max(exact, key=rate))
    smaller = [mode for mode in wide if mode["height"] <= target]
    if smaller:
        return best(max(smaller, key=lambda mode: (mode["height"], rate(mode))))
    pool = wide or modes
    return best(
        max(pool, key=lambda mode: (mode["width"] * mode["height"], rate(mode)))
    )


class MacBackend:
    """macOS: screencapture for the screen and the Mac's sound, ffmpeg AVFoundation for camera and microphone."""

    def list_avfoundation(self) -> tuple[list[str], list[str]]:
        if shutil.which("ffmpeg") is None:
            return [], []
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-f",
                "avfoundation",
                "-list_devices",
                "true",
                "-i",
                "",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        cameras: list[str] = []
        microphones: list[str] = []
        current: list[str] | None = None
        for line in result.stderr.splitlines():
            if "video devices:" in line:
                current = cameras
            elif "audio devices:" in line:
                current = microphones
            elif current is not None and "] [" in line:
                name = line.split("] [", 1)[1].split("] ", 1)
                if len(name) == 2 and not name[1].startswith("Capture screen"):
                    current.append(name[1].strip())
        return cameras, microphones

    def displays(self) -> list[dict]:
        """Displays numbered like `screencapture -D` (1 is the main display)."""
        try:
            result = subprocess.run(
                ["system_profiler", "-json", "SPDisplaysDataType"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            data = json.loads(result.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            data = {}
        screens = [
            screen
            for gpu in data.get("SPDisplaysDataType", [])
            for screen in gpu.get("spdisplays_ndrvs", [])
            if isinstance(screen, dict)
        ]
        screens.sort(
            key=lambda screen: screen.get("spdisplays_main") != "spdisplays_yes"
        )
        return [
            {
                "number": index,
                "name": str(screen.get("_name", f"Display {index}")),
                "pixels": str(screen.get("_spdisplays_pixels", "")),
            }
            for index, screen in enumerate(screens, 1)
        ] or [{"number": 1, "name": "Main display", "pixels": ""}]

    def devices(self) -> dict:
        cameras, microphones = self.list_avfoundation()
        return {
            "displays": self.displays(),
            "cameras": cameras,
            "microphones": [
                {"name": name, "virtual": virtual_device(name)} for name in microphones
            ],
            "ffmpeg": shutil.which("ffmpeg") is not None,
        }

    def camera_modes(self, name: str, *, refresh: bool = False) -> list[dict]:
        """Modes the camera offers; asking ffmpeg costs a moment of camera light, so answers are cached."""
        cache_path = storage_path("runtime", "camera-modes.json")
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(cache, dict):
                cache = {}
        except (OSError, ValueError):
            cache = {}
        known = cache.get(name)
        if (
            not refresh
            and isinstance(known, dict)
            and isinstance(known.get("modes"), list)
            and known["modes"]
        ):
            return known["modes"]
        if shutil.which("ffmpeg") is None:
            return []
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostdin",
                    "-f",
                    "avfoundation",
                    "-framerate",
                    "1000",
                    "-i",
                    f"{name}:none",
                    "-t",
                    "0.1",
                    "-f",
                    "null",
                    "-",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        modes = parse_modes(result.stderr)
        if modes:
            cache[name] = {
                "modes": modes,
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                prefix=".camera-modes.", dir=cache_path.parent
            )
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(cache, stream, indent=2)
            os.replace(temporary, cache_path)
        return modes

    def screen_argv(self, plan: dict, out: Path) -> list[str]:
        command = ["screencapture", "-v", "-x", f"-D{plan['display']}"]
        if plan.get("area"):
            command.append(f"-R{plan['area']}")
        if plan.get("clicks"):
            command.append("-k")
        if plan.get("system"):
            command.append("-A")
        if plan.get("mic_in_screen"):
            command.append("-g")  # only without ffmpeg: the default microphone inside the screen file
        return [*command, str(out)]

    def camera_encoder(self) -> str:
        """libx264 when this ffmpeg has it. screencapture keeps the Mac's video encoder busy at full
        resolution: a camera on h264_videotoolbox then got 2-5 frames a second (measured on an M3 Pro),
        on libx264 veryfast a steady 30 for about half a CPU core."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "h264_videotoolbox"
        found = re.search(r"^\s*V\S*\s+libx264\s", result.stdout, re.MULTILINE)
        return "libx264" if found else "h264_videotoolbox"

    def camera_argv(self, plan: dict, out: Path, *, nv12: bool = True) -> list[str]:
        mode = plan["mode"]
        pixel = ["-pixel_format", "nv12"] if nv12 else []
        bitrate = int(plan["bitrate"])
        if plan.get("encoder") == "libx264":
            codec = [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-b:v",
                str(bitrate),
                "-maxrate",
                str(bitrate * 3 // 2),
                "-bufsize",
                str(bitrate * 2),
            ]
        else:  # a 3.21.0 state has no encoder
            codec = ["-c:v", "h264_videotoolbox", "-b:v", str(bitrate)]
        return [
            *FFMPEG_QUIET,
            "-f",
            "avfoundation",
            *pixel,
            "-framerate",
            mode["fps"],
            "-video_size",
            f"{mode['width']}x{mode['height']}",
            "-i",
            f"{plan['camera']}:none",
            *codec,
            "-g",
            str(round(float(mode["fps"]))),
            "-movflags",
            "+frag_keyframe+empty_moov+default_base_moof",
            str(out),
        ]

    def mic_argv(self, plan: dict, out: Path) -> list[str]:
        """The microphone to its own file, plus peak levels (about 10 a second) in `mic-levels.txt` in the
        recorder's working directory, so the path never needs filtergraph escaping."""
        codec = {
            "flac": ["-c:a", "flac"],
            "wav": ["-c:a", "pcm_s16le"],
            "m4a": [
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-movflags",
                "+frag_keyframe+empty_moov",
            ],
        }[plan["mic_format"]]
        graph = (
            "[0:a]asplit=2[rec][mon];[mon]astats=metadata=1:reset=4,"
            f"ametadata=mode=print:key=lavfi.astats.Overall.Peak_level:file={LEVELS_FILE},anullsink"
        )
        return [
            *FFMPEG_QUIET,
            "-f",
            "avfoundation",
            "-i",
            f":{plan['mic']}",
            "-filter_complex",
            graph,
            "-map",
            "[rec]",
            *codec,
            str(out),
        ]

    def native_recorder(self) -> str | None:
        """ul-rec next to ul (macOS 15+): one process records the screen with ScreenCaptureKit and the
        camera and microphone with AVFoundation, on one clock, like OBS and Cap. `UNLAW_CAPTURE_REC`
        names another binary, or `off` for the separate tools (screencapture and ffmpeg)."""
        chosen = os.environ.get("UNLAW_CAPTURE_REC", "")
        if chosen == "off":
            return None
        if chosen:
            path = Path(chosen)
        else:
            unlaw_bin = os.environ.get("UNLAW_BIN")
            if not unlaw_bin or macos_major() < 15:  # SCRecordingOutput came with macOS 15
                return None
            path = Path(unlaw_bin).with_name("ul-rec")
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None

    def native_request(self, plan: dict, files: dict[str, Path], events: Path, levels: Path) -> dict:
        """The JSON plan ul-rec reads (its format is at the top of rust/src/bin/ul-rec.rs)."""
        request: dict = {"events": str(events), "levels": str(levels), "screen": None, "camera": None, "mic": None}
        if "screen" in files:
            request["screen"] = {
                "path": str(files["screen"]),
                "display": plan["display"],
                "area": plan["area"],
                "clicks": plan["clicks"],
                "system_audio": plan["system"],
                "fps": 60,
            }
        if "camera" in files:
            mode = plan["mode"] or {}
            request["camera"] = {
                "path": str(files["camera"]),
                "device": plan["camera"],
                "width": mode.get("width"),
                "height": mode.get("height"),
                "fps": mode.get("fps"),
                "bitrate": plan["bitrate"],
            }
        if "mic" in files:
            request["mic"] = {
                "path": str(files["mic"]),
                "device": plan["mic"],
                "format": "m4a" if files["mic"].suffix == ".m4a" else "wav",
            }
        return request

    def preview_argv(self, display: int, out: Path) -> list[str]:
        return ["screencapture", "-x", "-tjpg", f"-D{display}", str(out)]

    def permission_probe(self) -> dict:
        """Can this process record the screen? A 1x1-pixel screenshot answers in a moment."""
        folder = storage_path("runtime")
        folder.mkdir(parents=True, exist_ok=True)
        # Not a dot name: screencapture refuses hidden file names for screenshots and still exits 0.
        handle, name = tempfile.mkstemp(prefix="permission-probe-", suffix=".png", dir=folder)
        os.close(handle)
        probe = Path(name)
        probe.unlink()
        try:
            result = subprocess.run(
                ["screencapture", "-x", "-R0,0,1,1", str(probe)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=15,
                check=False,
            )
            ok = result.returncode == 0 and probe.is_file() and probe.stat().st_size > 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        finally:
            probe.unlink(missing_ok=True)
        return {"screen": ok}

    def responsible_app(self, pid: int | None = None) -> str | None:
        """The app macOS asks for Screen Recording, Camera and Microphone: the first `.app` above this process
        (Homebrew's Python.app is only the interpreter)."""
        current = os.getpid() if pid is None else pid
        for _ in range(40):
            if current <= 1:
                return None
            try:
                line = subprocess.run(
                    ["ps", "-o", "ppid=,comm=", "-p", str(current)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                ).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                return None
            parent, _, command = line.partition(" ")
            if not parent.strip().isdigit():
                return None
            parts = Path(command.strip()).parts
            apps = [part for part in parts if part.endswith(".app")]
            if apps and "Python.framework" not in parts and apps[0] != "Python.app":
                return apps[0][: -len(".app")]
            current = int(parent)
        return None

    def menubar_argv(self, unlaw_bin: str, state_file: Path) -> list[str]:
        return ["osascript", "-l", "JavaScript", "-e", MENUBAR_JS, unlaw_bin, str(state_file)]

    def settings_url(self, kind: str) -> str:
        if kind not in SETTINGS_PANES:
            raise ValueError(f"no privacy pane for {kind}")
        return f"x-apple.systempreferences:com.apple.preference.security?{SETTINGS_PANES[kind]}"


def macos_major() -> int:
    """The macOS major version (15 for Sequoia); 0 when unknown or not a Mac."""
    try:
        return int(platform.mac_ver()[0].split(".")[0])
    except ValueError:
        return 0


def backend() -> MacBackend:
    if sys.platform != "darwin" and not os.environ.get("UNLAW_CAPTURE_ANY_SYSTEM"):
        raise BackendError(
            "recording is not supported on this system yet (macOS only for now)"
        )
    return MacBackend()
