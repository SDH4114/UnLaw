# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Screenshots and screen, camera and audio recordings on macOS."""
from __future__ import annotations

COMMAND_HELP = 'Screenshots and screen, camera and audio recordings on macOS.\nUsage: ul capture                 a menu: pick what to capture (in a terminal)\n       ul capture shot [screen|area|window] [options] [PATH]\n       ul capture record [screen|camera|audio] [options] [PATH]\n       ul capture pause | resume | stop | status\n       ul capture list | last | open | reveal | copy | delete | trim | convert | devices\nScreenshots (shot):\n  screen (default) the whole display; area / window let you select with the mouse\n  --display N      which display (1 = main; see `devices`)   --delay S  wait S seconds\n  --clipboard      copy instead of saving   --cursor  include the pointer\n  --jpg            JPEG instead of PNG      --open    open the file afterwards\nRecording (record) runs in the background until `ul capture stop`:\n  screen (default) the display with system audio (macOS screencapture) and the\n                   microphone; --camera puts the camera in a corner (capture.overlay)\n  camera           the camera with the microphone\n  audio            the microphone only (m4a, mp3 or wav)\n  --mic NAME|N     microphone by name or number; --no-mic records without it\n  --cam NAME|N     camera by name or number (default: capture.camera_device)\n  --system-audio / --no-system-audio   sound of the Mac (screen only)\n  --display N      --rect X,Y,W,H (part of the screen, in points)   --no-clicks\n  --format F       mov|mp4 for video, m4a|mp3|wav for audio\n  --duration S     record S seconds in the foreground, then save\n  --wait           stay in the foreground: Enter stops, p + Enter pauses\n  pause / resume   pause and continue; the parts are joined when you stop\n  stop             stop and save (adds the camera and microphone; may take a moment)\n  status           what is recording, for how long, and where it goes\nLibrary:\n  list [N] [--all] the newest captures with kind, length and size\n  last [--reveal]  open the newest capture (or show it in Finder)\n  open|reveal X    open a capture, or show it in Finder (X: name, path or `last`)\n  copy X           put a screenshot on the clipboard\n  delete X         move a capture to the Trash (only from the capture folders)\n  trim X --from T [--to T]   cut a recording exactly (T: seconds or m:ss); keeps the original\n  convert X --to mp4|mov|gif|m4a|mp3|wav   a new file next to the original\n  devices          displays, cameras and microphones with their numbers\n  wave X [--bars N] the loudness of a recording as bars (like Voice Memos)\n  thumb X / preview [--display N]   small JPEGs (used by `ul desk`)\nAdd --json to any action for machine-readable output.\nFiles: storage.root/captures/screenshots and /recordings; never overwritten (" 2" is added).\nSettings: capture.audio_device and capture.camera_device (`default` = what macOS\n  uses, a name, or a number from `devices`), capture.screen_audio (microphone in\n  screen recordings, true), capture.system_audio (true), capture.show_clicks (true),\n  capture.video_format (mov), capture.audio_format (m4a), capture.overlay\n  (bottom-right, bottom-left, top-right, top-left).\nPermissions: the terminal (or the app running ul) needs Screen Recording, Camera\n  and Microphone in System Settings > Privacy & Security.\nDependencies: macOS screencapture; ffmpeg + ffprobe (brew install ffmpeg) for the\n  camera, a non-default microphone, audio, pause, MP4, trim and convert.\n`ul desk` has a Studio tab with the same controls, a preview and a player.\nExamples: ul capture shot area; ul capture record --camera; ul capture stop\n  ul capture record audio --duration 60; ul capture convert last --to gif\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'},
 'capture': {'camera_device': 'default',
             'audio_device': 'default',
             'screen_audio': True,
             'system_audio': True,
             'show_clicks': True,
             'video_format': 'mov',
             'audio_format': 'm4a',
             'overlay': 'bottom-right'}}


class ConfigError(ValueError):
    pass


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "unlaw"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = (
            _deep_merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else copy.deepcopy(value)
        )
    return result


def load_config() -> dict:
    path = config_dir() / "config.toml"
    try:
        with path.open("rb") as handle:
            configured = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read {path}: {error}") from error
    return _deep_merge(DEFAULT_CONFIG, configured)

def storage_path(*parts: str) -> Path:
    configured = Path(str(load_config()["storage"]["root"])).expanduser()
    root = configured if configured.is_absolute() else config_dir() / configured
    return root.joinpath(*parts)

import fcntl
import hashlib
import json
import math
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from array import array
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path



USAGE = """Usage: ul capture                      (menu: pick what to capture)
       ul capture shot [screen|area|window] [--display N] [--delay S] [--clipboard] [--cursor] [--jpg] [--open] [--output PATH]
       ul capture record [screen|camera|audio] [--camera] [--mic NAME|--no-mic] [--system-audio|--no-system-audio]
                         [--display N] [--rect X,Y,W,H] [--format mov|mp4|m4a|mp3|wav] [--duration S] [--wait] [--output PATH]
       ul capture pause|resume|stop|status
       ul capture list|last|open|reveal|copy|delete|trim|convert|devices
Run `ul capture --help` for details.
"""

VIDEO_EXT = {".mov", ".mp4"}
AUDIO_EXT = {".m4a", ".mp3", ".wav"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".heic", ".tiff"}
VIDEO_FORMATS = ("mov", "mp4")
AUDIO_FORMATS = ("m4a", "mp3", "wav")
MODES = ("screen", "camera", "audio")
CORNERS = {
    "bottom-right": "W-w-{m}:H-h-{m}",
    "bottom-left": "{m}:H-h-{m}",
    "top-right": "W-w-{m}:{m}",
    "top-left": "{m}:{m}",
}
# Virtual devices that carry app audio, not a voice; picking one as the microphone is a common mistake.
LOOPBACK_WORDS = (
    "blackhole",
    "loopback",
    "soundflower",
    "teams audio",
    "zoomaudio",
    "aggregate",
)
CAMERA_SIZE = "1280x720"
# Old one-word actions keep working.
SHORTCUTS = {
    "screenshot": ("shot", "screen"),
    "area": ("shot", "area"),
    "window": ("shot", "window"),
    "screen": ("record", "screen"),
    "camera": ("record", "camera"),
    "audio": ("record", "audio"),
}


class CaptureError(Exception):
    """A problem the user can fix; `code` is the exit status."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- helpers


def recording_state_file() -> Path:
    return storage_path("runtime", "recording.json")


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _settings() -> dict:
    settings = dict(load_config()["capture"])
    settings.setdefault("camera_device", "default")
    settings.setdefault("audio_device", "default")
    settings.setdefault("screen_audio", True)
    settings.setdefault("show_clicks", True)
    settings.setdefault("system_audio", True)
    settings.setdefault("video_format", "mov")
    settings.setdefault("audio_format", "m4a")
    settings.setdefault("overlay", "bottom-right")
    return settings


def _free(path: Path) -> Path:
    """Never overwrite: `name.mov` → `name 2.mov` → `name 3.mov`."""
    if not path.exists():
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.stem} {number}{path.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def _need(tool: str, why: str) -> str:
    found = shutil.which(tool)
    if found is None:
        hint = " (brew install ffmpeg)" if tool in {"ffmpeg", "ffprobe"} else ""
        raise CaptureError(f"{tool} is required {why}{hint}", 1)
    return found


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".capture.", dir=path.parent)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
    os.replace(temporary, path)


@contextmanager
def _locked(name: str = "recording") -> Iterator[None]:
    """Serialize recording changes or screenshot allocation across CLI processes."""
    lock = storage_path("runtime", f"{name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _seconds(text: str) -> float:
    """`90`, `1:30`, `0:01:30.5` → seconds."""
    try:
        value = 0.0
        for part in text.strip().split(":"):
            number = float(part)
            if not math.isfinite(number) or number < 0:
                raise ValueError(part)
            value = value * 60 + number
    except ValueError as error:
        raise CaptureError(f"not a time: {text!r} (use seconds or m:ss)") from error
    if value < 0 or len(text.split(":")) > 3:
        raise CaptureError(f"not a time: {text!r} (use seconds or m:ss)")
    return value


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return (
        f"{hours}:{rest // 60:02d}:{rest % 60:02d}"
        if hours
        else f"{rest // 60:02d}:{rest % 60:02d}"
    )


def _run(command: list[str], what: str) -> None:
    result = subprocess.run(
        command, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise CaptureError(
            f"{what} failed: {' '.join(detail) or 'exit ' + str(result.returncode)}", 1
        )


# ---------------------------------------------------------------- devices


def _ffmpeg_devices() -> tuple[list[str], list[str]]:
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


def _displays() -> list[dict]:
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
    screens.sort(key=lambda screen: screen.get("spdisplays_main") != "spdisplays_yes")
    return [
        {
            "number": index,
            "name": str(screen.get("_name", f"Display {index}")),
            "pixels": str(screen.get("_spdisplays_pixels", "")),
        }
        for index, screen in enumerate(screens, 1)
    ] or [{"number": 1, "name": "Main display", "pixels": ""}]


def is_loopback(name: str) -> bool:
    return any(word in name.casefold() for word in LOOPBACK_WORDS)


def devices() -> dict:
    cameras, microphones = _ffmpeg_devices()
    return {
        "displays": _displays(),
        "cameras": cameras,
        "microphones": [
            {"name": name, "virtual": is_loopback(name)} for name in microphones
        ],
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }


def _resolve(value: str, names: list[str], kind: str) -> str | None:
    """Config/flag value → the AVFoundation name (`default` = the system choice, None = off)."""
    text = str(value).strip()
    if text.casefold() in {"", "default", "auto"}:
        return "default"
    if text.casefold() in {"none", "off", "no"}:
        return None
    if text.isdigit():
        index = int(text)
        if index >= len(names):
            raise CaptureError(
                f"there is no {kind} number {index}; see `ul capture devices`"
            )
        return names[index]
    exact = [name for name in names if name.casefold() == text.casefold()]
    partial = [name for name in names if text.casefold() in name.casefold()]
    if exact or len(partial) == 1:
        return (exact or partial)[0]
    if not names:
        return text  # ffmpeg could not list devices; let it try the name
    if partial:
        raise CaptureError(f"{text!r} matches several {kind}s: {', '.join(partial)}")
    raise CaptureError(f"no {kind} named {text!r}; available: {', '.join(names)}")


# ---------------------------------------------------------------- screenshots


def shot(
    kind: str = "screen",
    *,
    display: int = 1,
    delay: int = 0,
    clipboard: bool = False,
    cursor: bool = False,
    jpg: bool = False,
    output: str | None = None,
) -> Path | None:
    """Take a screenshot; returns its path (None for the clipboard)."""
    if kind not in {"screen", "area", "window"}:
        raise CaptureError(f"unknown screenshot kind: {kind} (screen, area or window)")
    flags = {
        "screen": ["-x", f"-D{display}"],
        "area": ["-i", "-s", "-x"],
        "window": ["-i", "-W", "-x"],
    }[kind]
    if delay:
        flags.append(f"-T{delay}")
    if cursor and kind == "screen":
        flags.append("-C")
    if jpg:
        flags.append("-tjpg")
    _need("screencapture", "for screenshots")
    if clipboard:
        result = subprocess.run(["screencapture", "-c", *flags], check=False)
        if result.returncode != 0:
            raise CaptureError("screenshot failed (Screen Recording permission?)", 1)
        return None
    extension = ".jpg" if jpg else ".png"
    path = (
        Path(output).expanduser()
        if output
        else storage_path(
            "captures", "screenshots", f"{kind}-{_timestamp()}{extension}"
        )
    )
    with _locked("screenshot"):
        path = _free(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["screencapture", *flags, str(path)], check=False)
        if result.returncode != 0:
            raise CaptureError("screenshot failed (Screen Recording permission?)", 1)
        if not path.exists():
            if kind in {"area", "window"}:
                raise CaptureError("cancelled", 1)
            raise CaptureError(
                "screencapture wrote no file (Screen Recording permission?)", 1
            )
    return path


# ---------------------------------------------------------------- recording


def _alive(pid: int, program: str) -> bool:
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    command = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    # A reused pid (after a reboot) must never be signalled: it has to be our tool.
    return program in command


def _valid_state(state: object) -> bool:
    if not isinstance(state, dict):
        return False
    plan = state.get("plan")
    if not isinstance(plan, dict) or state.get("mode") not in MODES:
        return False
    if not all(
        isinstance(state.get(key), str) and state[key]
        for key in ("output", "parts", "started")
    ):
        return False
    if state.get("phase") not in ("recording", "paused", "saving", "interrupted", "unsaved"):
        return False
    if type(state.get("paused")) is not bool:
        return False
    for key in ("elapsed", "segment_started"):
        value = state.get(key)
        if key == "segment_started" and value is None:
            continue
        if type(value) not in (int, float) or not -sys.float_info.max <= value <= sys.float_info.max:
            return False
    segments, processes = state.get("segments"), state.get("processes")
    if not isinstance(segments, list) or not isinstance(processes, list):
        return False
    if any(
        not isinstance(files, dict)
        or not all(isinstance(path, str) and path for path in files.values())
        for files in segments
    ):
        return False
    for process in processes:
        if not isinstance(process, dict) or type(process.get("pid")) is not int:
            return False
        if not 0 < process["pid"] <= 2**31 - 1 or process.get("program") not in (
            "ffmpeg", "screencapture"
        ):
            return False
    if (
        plan.get("mode") != state["mode"]
        or not isinstance(plan.get("overlay"), str)
        or plan["overlay"] not in CORNERS
    ):
        return False
    if not all(type(plan.get(key)) is bool for key in ("camera", "system_audio", "clicks")):
        return False
    if type(plan.get("display")) is not int or plan["display"] < 1:
        return False
    return all(
        key in plan and (plan[key] is None or isinstance(plan[key], str))
        for key in ("camera_name", "mic", "rect")
    )


def _load_state() -> dict | None:
    path = recording_state_file()
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not _valid_state(state):
            raise ValueError("not a recording state")
        return state
    except (OSError, ValueError) as error:
        path.unlink(missing_ok=True)
        raise CaptureError(
            f"could not read the recording state ({error}); it was reset", 1
        ) from error


def _audio_codec(extension: str) -> list[str]:
    return {
        ".m4a": ["-c:a", "aac", "-b:a", "192k"],
        ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
        ".wav": ["-c:a", "pcm_s16le"],
    }[extension]


def _segment_commands(
    state: dict, index: int
) -> tuple[dict, list[tuple[str, list[str]]]]:
    """The files and processes for one segment (a new one after every resume)."""
    plan = state["plan"]
    parts = Path(state["parts"])
    ffmpeg = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "avfoundation",
    ]
    camera_input = [
        "-pixel_format",
        "nv12",
        "-framerate",
        "30",
        "-video_size",
        CAMERA_SIZE,
    ]
    files: dict = {}
    commands: list[tuple[str, list[str]]] = []
    mode, mic = plan["mode"], plan["mic"]
    if mode == "screen":
        files["screen"] = str(parts / f"{index:03d}-screen.mov")
        command = ["screencapture", "-v", "-x", f"-D{plan['display']}"]
        if plan["rect"]:
            command.append(f"-R{plan['rect']}")
        if plan["clicks"]:
            command.append("-k")
        if plan["system_audio"]:
            command.append("-A")
        if mic == "default" and not plan["camera"]:
            command.append("-g")
        commands.append(("screencapture", [*command, files["screen"]]))
        if plan["camera"]:
            files["camera"] = str(parts / f"{index:03d}-camera.mov")
            audio = ["-c:a", "aac", "-b:a", "192k"] if mic else []
            commands.append(
                (
                    "ffmpeg",
                    [
                        *ffmpeg,
                        *camera_input,
                        "-i",
                        f"{plan['camera_name']}:{mic or 'none'}",
                        "-c:v",
                        "h264_videotoolbox",
                        "-b:v",
                        "6M",
                        *audio,
                        files["camera"],
                    ],
                )
            )
        elif mic and mic != "default":
            files["mic"] = str(parts / f"{index:03d}-mic.m4a")
            commands.append(
                (
                    "ffmpeg",
                    [
                        *ffmpeg,
                        "-i",
                        f":{mic}",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        files["mic"],
                    ],
                )
            )
    elif mode == "camera":
        files["camera"] = str(parts / f"{index:03d}-camera.mov")
        audio = ["-c:a", "aac", "-b:a", "192k"] if mic else []
        commands.append(
            (
                "ffmpeg",
                [
                    *ffmpeg,
                    *camera_input,
                    "-i",
                    f"{plan['camera_name']}:{mic or 'none'}",
                    "-c:v",
                    "h264_videotoolbox",
                    "-b:v",
                    "6M",
                    *audio,
                    files["camera"],
                ],
            )
        )
    else:
        extension = Path(state["output"]).suffix
        files["audio"] = str(parts / f"{index:03d}-audio{extension}")
        commands.append(
            (
                "ffmpeg",
                [*ffmpeg, "-i", f":{mic}", *_audio_codec(extension), files["audio"]],
            )
        )
    return files, commands


def _start_segment(state: dict) -> None:
    index = len(state["segments"])
    files, commands = _segment_commands(state, index)
    log_path = storage_path("runtime", "recording.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = log_path.stat().st_size if log_path.exists() else 0
    processes: list[tuple[str, subprocess.Popen]] = []
    # The clock starts when the recorders start, not after the start check below.
    spawned = time.time()
    try:
        with log_path.open("ab") as log:
            for program, command in commands:
                log.write(f"$ {' '.join(command)}\n".encode())
                log.flush()
                processes.append(
                    (
                        program,
                        subprocess.Popen(
                            command,
                            stdin=subprocess.DEVNULL,
                            stdout=log,
                            stderr=log,
                            start_new_session=True,
                            # Safe: only the single-threaded CLI spawns recorders (the desk runs `ul capture`).
                            preexec_fn=_default_signals,  # noqa: PLW1509
                        ),
                    )
                )
        # A missing permission or a busy device makes the tools exit within a moment;
        # later failures show up as the `interrupted` phase in `status`.
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            if any(process.poll() is not None for _, process in processes):
                with log_path.open("rb") as log:
                    log.seek(start)
                    lines = [
                        line
                        for line in log.read().decode(errors="replace").splitlines()
                        if line and not line.startswith("$ ")
                    ]
                reason = " ".join(lines[-2:]) or "it stopped right away"
                hint = " Check System Settings > Privacy & Security (Screen Recording, Camera, Microphone)."
                raise CaptureError(f"recording could not start: {reason}.{hint}", 1)
            time.sleep(0.1)
        state["segments"].append(files)
        state["processes"] = [
            {"pid": process.pid, "program": program} for program, process in processes
        ]
        state["segment_started"] = spawned
        state["paused"] = False
        state["phase"] = "recording"
        _write_json(recording_state_file(), state)
    except BaseException:
        # Until the state is committed, only these Popen handles can stop the
        # detached recorders. This also covers Ctrl-C and a full state-file disk.
        for _, process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        for _, process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise


def _default_signals() -> None:
    """Runs in the recorder before exec. A parent started with Ctrl-C ignored
    (launchd, a background shell) would pass SIG_IGN on, and screencapture,
    which has no handler of its own, could then never be stopped cleanly."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGQUIT, signal.SIG_DFL)


def _signal_all(processes: list[dict], number: int) -> None:
    for item in processes:
        if _alive(item["pid"], item["program"]):
            try:
                os.kill(item["pid"], number)
            except ProcessLookupError:
                pass


def _stop_segment(state: dict) -> None:
    """SIGINT lets the tools finish their files; SIGTERM, then SIGKILL, only if they hang."""
    processes = state.get("processes", [])
    stopped_at = time.time()
    for number, wait in ((signal.SIGINT, 15), (signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        _signal_all(processes, number)
        deadline = time.monotonic() + wait
        while (
            any(_alive(item["pid"], item["program"]) for item in processes)
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        if not any(_alive(item["pid"], item["program"]) for item in processes):
            break
    if state.get("segment_started") and not state.get("paused"):
        state["elapsed"] = (
            state.get("elapsed", 0.0) + stopped_at - state["segment_started"]
        )
    state["processes"] = []
    state["segment_started"] = None


def start_recording(
    mode: str = "screen",
    *,
    camera: bool = False,
    cam: str | None = None,
    mic: str | None = None,
    system_audio: bool | None = None,
    display: int = 1,
    rect: str | None = None,
    clicks: bool | None = None,
    format: str | None = None,
    output: str | None = None,
) -> dict:
    """Start a recording in the background; `stop_recording` saves it."""
    if mode not in MODES:
        raise CaptureError(f"unknown recording mode: {mode} (screen, camera or audio)")
    settings = _settings()
    if mode == "audio":
        extension = "." + (format or settings["audio_format"])
        if extension[1:] not in AUDIO_FORMATS:
            raise CaptureError(
                f"audio format must be one of {', '.join(AUDIO_FORMATS)}"
            )
    else:
        extension = "." + (format or settings["video_format"])
        if extension[1:] not in VIDEO_FORMATS:
            raise CaptureError(
                f"video format must be one of {', '.join(VIDEO_FORMATS)}"
            )
    if rect is not None:
        numbers = rect.split(",")
        if (
            mode != "screen"
            or len(numbers) != 4
            or not all(number.strip().isdigit() for number in numbers)
        ):
            raise CaptureError(
                "--rect needs X,Y,WIDTH,HEIGHT in points and only works for the screen"
            )
        rect = ",".join(number.strip() for number in numbers)
    if display < 1:
        raise CaptureError("--display starts at 1 (the main display)")
    want_camera = mode == "camera" or camera
    if mode == "screen":
        _need("screencapture", "for screen recording")
    if mic is not None:
        mic_value = mic
    elif mode != "screen" or settings["screen_audio"]:
        mic_value = str(settings["audio_device"])
    else:
        mic_value = "none"
    plain_mic = mic_value.strip().casefold() in {
        "",
        "default",
        "auto",
        "none",
        "off",
        "no",
    }
    # The default microphone goes straight into screencapture; anything else needs ffmpeg.
    needs_ffmpeg = want_camera or mode == "audio" or not plain_mic
    if needs_ffmpeg:
        _need("ffmpeg", "for camera, microphone and audio recording")
    plain_camera = str(cam or settings["camera_device"]).strip().casefold() in {
        "",
        "default",
        "auto",
        "none",
        "off",
        "no",
    }
    # Listing devices costs ffmpeg half a second; `default` and `none` need no list.
    must_list = not plain_mic or (want_camera and not plain_camera)
    cameras, microphones = _ffmpeg_devices() if must_list else ([], [])
    mic_name = _resolve(mic_value, microphones, "microphone")
    if mode == "audio" and mic_name is None:
        raise CaptureError("audio recording needs a microphone")
    camera_name = (
        _resolve(cam or settings["camera_device"], cameras, "camera")
        if want_camera
        else None
    )
    if want_camera and camera_name is None:
        raise CaptureError(
            "capture.camera_device is off; set it to `default` or a camera name"
        )
    if mode != "audio" and extension == ".mp4":
        _need("ffmpeg", "to save MP4")
    system = settings["system_audio"] if system_audio is None else system_audio
    if system and mode != "screen":
        if system_audio:
            raise CaptureError("system audio is recorded with the screen only")
        system = False
    warnings = []
    if mic_name and is_loopback(mic_name):
        warnings.append(
            f"{mic_name} is a virtual device: it records app audio routed to it, not your voice"
        )
    with _locked():
        try:
            running = _load_state()
        except CaptureError:
            running = None  # a damaged state file was reset; start fresh
        if running is not None:
            raise CaptureError(
                "a recording is already running; stop it with `ul capture stop`", 1
            )
        if output:
            path = Path(output).expanduser().absolute()
            if path.suffix.casefold() != extension:
                path = path.with_suffix(extension)
        else:
            name = "screen-camera" if mode == "screen" and camera else mode
            folder = "recordings"
            path = storage_path("captures", folder, f"{name}-{_timestamp()}{extension}")
        path = _free(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        parts = storage_path(
            "captures",
            ".parts",
            path.stem + "-" + hashlib.sha1(str(path).encode()).hexdigest()[:8],
        )
        parts.mkdir(parents=True, exist_ok=True)
        state = {
            "mode": mode,
            "output": str(path),
            "parts": str(parts),
            "started": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed": 0.0,
            "segments": [],
            "processes": [],
            "paused": False,
            "phase": "recording",
            "warnings": warnings,
            "plan": {
                "mode": mode,
                "camera": bool(camera and mode == "screen"),
                "camera_name": camera_name,
                "mic": mic_name,
                "system_audio": bool(system),
                "display": display,
                "rect": rect,
                "clicks": settings["show_clicks"] if clicks is None else clicks,
                "overlay": settings["overlay"]
                if settings["overlay"] in CORNERS
                else "bottom-right",
            },
        }
        try:
            _start_segment(state)
        except CaptureError:
            shutil.rmtree(parts, ignore_errors=True)
            raise
    return status()


def pause_recording() -> dict:
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("nothing is recording", 1)
        if state["paused"]:
            return status()
        _need("ffmpeg", "to join the parts of a paused recording")
        _stop_segment(state)
        state["paused"] = True
        state["phase"] = "paused"
        _write_json(recording_state_file(), state)
    return status()


def resume_recording() -> dict:
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("nothing is recording", 1)
        if not state["paused"]:
            return status()
        _start_segment(state)
    return status()


def status() -> dict:
    try:
        state = _load_state()
    except CaptureError:
        state = None
    if state is None:
        return {"active": False}
    running = state.get("segment_started") and not state["paused"]
    elapsed = state.get("elapsed", 0.0) + (
        time.time() - state["segment_started"] if running else 0.0
    )
    alive = [
        item
        for item in state.get("processes", [])
        if _alive(item["pid"], item["program"])
    ]
    phase = state["phase"]
    if (
        phase == "recording"
        and state.get("processes")
        and len(alive) < len(state["processes"])
    ):
        phase = "interrupted"
    return {
        "active": True,
        "mode": state["mode"],
        "camera": state["plan"]["camera"],
        "phase": phase,
        "paused": state["paused"],
        "elapsed": round(elapsed, 1),
        "output": state["output"],
        "started": state["started"],
        "warnings": state.get("warnings", []),
    }


# ---------------------------------------------------------------- finishing


def _probe(path: str) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            path,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        data = {}
    streams = data.get("streams", [])
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), {}
    )
    try:
        duration = float(data.get("format", {}).get("duration", 0) or 0)
    except ValueError:
        duration = 0.0
    return {
        "duration": duration,
        "audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "video": bool(video),
        "width": int(video.get("width") or 0),
        "codecs": [stream.get("codec_name") for stream in streams],
    }


def _overlay(screen: str, camera: str, corner: str, output: str) -> None:
    """Camera in a corner of the screen; both stopped together, so their ends line up."""
    base, cam = _probe(screen), _probe(camera)
    offset = max(0.0, base["duration"] - cam["duration"])
    width = max(2, int(base["width"] * 0.22) // 2 * 2) if base["width"] else 640
    margin = max(8, base["width"] // 50) if base["width"] else 32
    position = CORNERS[corner].format(m=margin)
    graph = f"[1:v]scale={width}:-2,format=yuv420p[cam];[0:v][cam]overlay={position}:eof_action=pass[v]"
    audio = [
        label
        for label, present in (("[0:a]", base["audio"]), ("[1:a]", cam["audio"]))
        if present
    ]
    maps = ["-map", "[v]"]
    if len(audio) == 2:
        graph += ";[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]"
        maps += ["-map", "[a]"]
    elif audio:
        maps += ["-map", "0:a" if audio[0] == "[0:a]" else "1:a"]
    bitrate = (
        f"{max(8, min(30, base['width'] * 5 // 1000))}M" if base["width"] else "12M"
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            screen,
            "-itsoffset",
            f"{offset:.3f}",
            "-i",
            camera,
            "-filter_complex",
            graph,
            *maps,
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            bitrate,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            output,
        ],
        "adding the camera",
    )


def _mix_mic(screen: str, mic: str, output: str) -> None:
    base, voice = _probe(screen), _probe(mic)
    offset = max(0.0, base["duration"] - voice["duration"])
    if base["audio"]:
        audio = [
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
        ]
    else:
        audio = ["-map", "0:v", "-map", "1:a"]
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            screen,
            "-itsoffset",
            f"{offset:.3f}",
            "-i",
            mic,
            *audio,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            output,
        ],
        "adding the microphone",
    )


def _finish_segment(state: dict, index: int, files: dict) -> str | None:
    parts = Path(state["parts"])
    plan = state["plan"]
    existing = {
        key: value
        for key, value in files.items()
        if Path(value).is_file() and Path(value).stat().st_size > 0
    }
    if state["mode"] == "audio":
        return existing.get("audio")
    if state["mode"] == "camera":
        return existing.get("camera")
    screen = existing.get("screen")
    if screen is None:
        if existing:
            raise CaptureError(f"the screen recording is missing; other recorded parts are kept in {parts}", 1)
        return None
    if "camera" in existing:
        out = str(parts / f"{index:03d}-done.mov")
        _overlay(screen, existing["camera"], plan["overlay"], out)
        return out
    if "mic" in existing:
        out = str(parts / f"{index:03d}-done.mov")
        _mix_mic(screen, existing["mic"], out)
        return out
    return screen


def _concat(files: list[str], output: str) -> None:
    listing = Path(output).with_suffix(".txt")
    listing.write_text(
        "".join("file '" + name.replace("'", "'\\''") + "'\n" for name in files),
        encoding="utf-8",
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            output,
        ],
        "joining the parts",
    )
    listing.unlink(missing_ok=True)


def stop_recording() -> dict:
    """Stop, join paused parts, add camera/microphone, and save the final file."""
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("no active recording", 1)
        _stop_segment(state)
        state["phase"] = "saving"
        _write_json(recording_state_file(), state)
        try:
            return _save(state)
        except BaseException:  # also Ctrl-C while ffmpeg saves: never stay "saving"
            # The parts stay and `ul capture stop` tries again; an empty
            # recording was already cleaned up and must not come back.
            if recording_state_file().exists():
                state["phase"] = "unsaved"
                _write_json(recording_state_file(), state)
            raise


def _save(state: dict) -> dict:
    output = Path(state["output"])
    done = [
        path
        for index, files in enumerate(state["segments"])
        if (path := _finish_segment(state, index, files))
    ]
    if not done:
        shutil.rmtree(state["parts"], ignore_errors=True)
        recording_state_file().unlink(missing_ok=True)
        raise CaptureError(
            "nothing was recorded (check the Screen Recording, Camera and Microphone permissions)",
            1,
        )
    joined = done[0]
    if len(done) > 1:
        joined = str(Path(state["parts"]) / f"joined{Path(done[0]).suffix}")
        _concat(done, joined)
    target = _free(output) if output.exists() else output
    if Path(joined).suffix.casefold() != target.suffix.casefold():
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                joined,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(target),
            ],
            "saving MP4",
        )
    else:
        shutil.move(joined, target)
    shutil.rmtree(state["parts"], ignore_errors=True)
    recording_state_file().unlink(missing_ok=True)
    return {
        "active": False,
        "saved": str(target),
        "elapsed": round(state.get("elapsed", 0.0), 1),
    }


# ---------------------------------------------------------------- library


def _kind(path: Path) -> str | None:
    suffix = path.suffix.casefold()
    return (
        "video"
        if suffix in VIDEO_EXT
        else "audio"
        if suffix in AUDIO_EXT
        else "image"
        if suffix in IMAGE_EXT
        else None
    )


def _roots() -> list[Path]:
    return [
        storage_path("captures", "screenshots"),
        storage_path("captures", "recordings"),
    ]


def latest_capture() -> Path | None:
    files = [
        item
        for root in _roots()
        if root.is_dir()
        for item in root.iterdir()
        if item.is_file() and _kind(item)
    ]
    return max(files, key=lambda item: item.stat().st_mtime, default=None)


def library(limit: int | None = None) -> list[dict]:
    """Saved captures, newest first; durations are cached by size and mtime."""
    files = [
        item
        for root in _roots()
        if root.is_dir()
        for item in root.iterdir()
        if item.is_file() and not item.name.startswith(".") and _kind(item)
    ]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    if limit is not None:
        files = files[:limit]
    cache_path = storage_path("runtime", "captures.json")
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    probe = shutil.which("ffprobe") is not None
    items, fresh = [], {}
    for path in files:
        info = path.stat()
        kind = _kind(path)
        key = f"{path}|{info.st_size}|{int(info.st_mtime)}"
        duration = cache.get(key)
        if duration is None and kind != "image" and probe:
            duration = round(_probe(str(path))["duration"], 2)
        if duration is not None:
            fresh[key] = duration
        items.append(
            {
                "name": path.name,
                "path": str(path),
                "kind": kind,
                "size": info.st_size,
                "modified": datetime.fromtimestamp(info.st_mtime)
                .astimezone()
                .isoformat(timespec="seconds"),
                "duration": duration,
            }
        )
    if fresh != cache:
        _write_json(cache_path, fresh)
    return items


def find_capture(name: str) -> Path:
    """`last`, a file name in the capture folders, or a path."""
    if name == "last":
        latest = latest_capture()
        if latest is None:
            raise CaptureError("no captures found")
        return latest
    for root in _roots():
        candidate = root / name
        if "/" not in name and candidate.is_file():
            return candidate
    path = Path(name).expanduser()
    if path.is_file():
        return path.absolute()
    raise CaptureError(f"no capture named {name!r}; see `ul capture list`")


def _inside_captures(path: Path) -> bool:
    root = storage_path("captures").resolve()
    return path.resolve().is_relative_to(root)


def delete_capture(name: str) -> Path:
    path = find_capture(name)
    if not _inside_captures(path) or path.is_symlink():
        raise CaptureError("delete only removes files from the capture folders")
    trash = Path.home() / ".Trash"
    trash.mkdir(exist_ok=True)
    target = _free(trash / path.name)
    shutil.move(str(path), target)
    return target


def copy_capture(name: str) -> Path:
    path = find_capture(name)
    kinds = {
        ".png": "PNGf",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".gif": "GIFf",
        ".tiff": "TIFF",
    }
    kind = kinds.get(path.suffix.casefold())
    if kind is None:
        raise CaptureError("only screenshots can be copied to the clipboard")
    escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
    _run(
        [
            "osascript",
            "-e",
            f'set the clipboard to (read (POSIX file "{escaped}") as «class {kind}»)',
        ],
        "copying",
    )
    return path


def trim_capture(
    name: str, start: str, end: str | None, output: str | None = None
) -> Path:
    path = find_capture(name)
    kind = _kind(path)
    if kind not in {"video", "audio"}:
        raise CaptureError("only recordings can be trimmed")
    _need("ffmpeg", "to trim")
    begin = _seconds(start)
    finish = _seconds(end) if end else None
    if finish is not None and finish <= begin:
        raise CaptureError("--to must be after --from")
    target = _free(
        Path(output).expanduser()
        if output
        else path.with_name(f"{path.stem} trim{path.suffix}")
    )
    # Seeking on the input is fast and, because the cut is re-encoded, still exact.
    seek = ["-ss", f"{begin:.3f}"]
    window = ["-t", f"{finish - begin:.3f}"] if finish is not None else []
    if kind == "video":
        codec = [
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            "12M",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
    else:
        codec = _audio_codec(path.suffix.casefold())
    # Re-encoding (not stream copy) cuts exactly at the chosen time instead of the nearest keyframe.
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            *seek,
            "-i",
            str(path),
            *window,
            *codec,
            str(target),
        ],
        "trimming",
    )
    return target


def convert_capture(name: str, to: str, output: str | None = None) -> Path:
    path = find_capture(name)
    kind = _kind(path)
    to = to.casefold().lstrip(".")
    if kind not in {"video", "audio"}:
        raise CaptureError("only recordings can be converted")
    if to not in {*VIDEO_FORMATS, "gif", *AUDIO_FORMATS}:
        raise CaptureError("convert to mp4, mov, gif, m4a, mp3 or wav")
    if kind == "audio" and to in {*VIDEO_FORMATS, "gif"}:
        raise CaptureError("an audio recording can only become m4a, mp3 or wav")
    if path.suffix.casefold() == "." + to:
        raise CaptureError(f"{path.name} is already {to}")
    _need("ffmpeg", "to convert")
    target = _free(Path(output).expanduser() if output else path.with_suffix("." + to))
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path)]
    if to == "gif":
        graph = "fps=12,scale='min(960,iw)':-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer"
        command = [*base, "-filter_complex", graph, "-loop", "0", str(target)]
    elif to in AUDIO_FORMATS:
        command = [*base, "-vn", *_audio_codec("." + to), str(target)]
    else:
        info = _probe(str(path))
        copyable = all(
            codec in {"h264", "hevc", "aac"} for codec in info["codecs"] if codec
        )
        codec = (
            ["-c", "copy"]
            if copyable
            else ["-c:v", "h264_videotoolbox", "-b:v", "12M", "-c:a", "aac"]
        )
        command = [*base, *codec, "-movflags", "+faststart", str(target)]
    _run(command, "converting")
    return target


WAVE_RATE = (
    2000  # samples per second decoded for a waveform: plenty for bars, tiny for an hour
)


def waveform(name: str, bars: int = 400) -> dict:
    """Loudness bars (0..1) of a recording's sound, cached in storage.root/runtime/waves.

    ffmpeg decodes a small mono stream, so an hour of audio stays a few MB.
    """
    path = find_capture(name)
    if _kind(path) not in {"audio", "video"}:
        raise CaptureError("only recordings have sound")
    if not 10 <= bars <= 2000:
        raise CaptureError("--bars must be between 10 and 2000")
    _need("ffmpeg", "for waveforms")
    info = path.stat()
    digest = hashlib.sha1(
        f"{path}|{info.st_size}|{info.st_mtime}|{bars}".encode()
    ).hexdigest()[:16]
    cache = storage_path("runtime", "waves", f"{digest}.json")
    try:
        return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(WAVE_RATE),
            "-f",
            "s16le",
            "-",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    samples = array("h")
    samples.frombytes(result.stdout[: len(result.stdout) // 2 * 2])
    if result.returncode != 0 and not samples:
        raise CaptureError("this file has no sound to draw", 1)
    if sys.byteorder == "big":
        samples.byteswap()
    per = max(1, -(-len(samples) // bars))
    peaks = []
    for start in range(0, len(samples), per):
        chunk = samples[start : start + per]
        loudest = max(max(chunk), -min(chunk)) / 32768
        peaks.append(
            round(loudest**0.6, 3)
        )  # a gentle curve so quiet speech stays visible
    data = {"peaks": peaks, "duration": round(len(samples) / WAVE_RATE, 3)}
    _write_json(cache, data)
    return data


@contextmanager
def _atomic_jpeg(target: Path) -> Iterator[Path]:
    """A tool writes a temporary file that replaces `target` only when it succeeds,
    so a failed or concurrent run never leaves a half-written image to be cached or served."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".capture.", suffix=".jpg", dir=target.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        yield temporary
        if temporary.stat().st_size == 0:
            raise CaptureError(f"{target.name}: the tool wrote no image", 1)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def thumbnail(name: str) -> Path:
    """A small JPEG for a screenshot or video, cached in storage.root/runtime/thumbs."""
    path = find_capture(name)
    kind = _kind(path)
    if kind not in {"video", "image"}:
        raise CaptureError("audio has no picture")
    info = path.stat()
    digest = hashlib.sha1(
        f"{path}|{info.st_size}|{info.st_mtime}".encode()
    ).hexdigest()[:16]
    target = storage_path("runtime", "thumbs", f"{digest}.jpg")
    if target.is_file():
        return target
    with _atomic_jpeg(target) as temporary:
        _make_thumbnail(path, kind, temporary)
    return target


def _make_thumbnail(path: Path, kind: str, target: Path) -> None:
    if kind == "image":
        _run(
            [
                "sips",
                "-s",
                "format",
                "jpeg",
                "-Z",
                "480",
                str(path),
                "--out",
                str(target),
            ],
            "making a thumbnail",
        )
    else:
        _need("ffmpeg", "for video thumbnails")
        duration = _probe(str(path))["duration"]
        at = f"{min(1.0, duration / 2):.2f}"
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-ss",
                at,
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:-2",
                "-q:v",
                "5",
                str(target),
            ],
            "making a thumbnail",
        )


def preview(display: int = 1) -> Path:
    """A small JPEG of one display right now (the desk shows it as a live preview)."""
    _need("screencapture", "for the preview")
    target = storage_path("runtime", f"preview-{display}.jpg")
    with _atomic_jpeg(target) as temporary:
        _run(["screencapture", "-x", "-tjpg", f"-D{display}", str(temporary)], "the preview")
        _run(["sips", "-Z", "1280", str(temporary)], "resizing the preview")
    return target


# ---------------------------------------------------------------- CLI


def _take(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    at = args.index(flag)
    if at + 1 >= len(args) or args[at + 1].startswith("--"):
        raise CaptureError(f"{flag} needs a value")
    value = args[at + 1]
    del args[at : at + 2]
    return value


def _is_word(text: str) -> bool:
    """A kind/mode word, not a flag or an output path like `shot.png` or `~/x`."""
    return not text.startswith("-") and "/" not in text and "." not in text


def _flag(args: list[str], *names: str) -> bool:
    found = False
    for name in names:
        while name in args:
            args.remove(name)
            found = True
    return found


def _number(text: str | None, flag: str, default: int, minimum: int = 0) -> int:
    if text is None:
        return default
    if not text.isdigit() or int(text) < minimum:
        raise CaptureError(f"{flag} needs a whole number from {minimum}")
    return int(text)


def _print(data: object, as_json: bool, text: str) -> None:
    print(json.dumps(data, ensure_ascii=False) if as_json else text)


def _describe(info: dict) -> str:
    if not info.get("active"):
        return "Not recording."
    what = "screen + camera" if info["camera"] else info["mode"]
    state = {
        "recording": "● Recording",
        "paused": "❚❚ Paused",
        "saving": "Saving",
        "interrupted": "Stopped unexpectedly",
        "unsaved": "Not saved yet",
    }.get(info["phase"], info["phase"])
    line = f"{state} {what} {_clock(info['elapsed'])} → {info['output']}"
    if info["phase"] in {"interrupted", "unsaved"}:
        line += "\nRun `ul capture stop` to save what was recorded."
    return line


def _watch(duration: float | None) -> dict:
    """Foreground recording: a live timer; Enter stops, p + Enter pauses or resumes."""
    interactive = sys.stdin.isatty()
    if interactive:
        print(
            "Enter: stop and save · p + Enter: pause/resume · Ctrl+C: stop and save",
            flush=True,
        )
    try:
        while True:
            info = status()
            if not info.get("active"):
                raise CaptureError("the recording was stopped elsewhere", 1)
            if info["phase"] == "interrupted":
                # A recorder died (display or device gone, disk full): save what exists.
                print("\nA recorder stopped unexpectedly; saving what was recorded.", file=sys.stderr, flush=True)
                break
            if duration is not None and info["elapsed"] >= duration:
                break
            if interactive:
                sys.stdout.write("\r" + _describe(info).splitlines()[0][:110] + "   ")
                sys.stdout.flush()
                ready, _, _ = select.select([sys.stdin], [], [], 0.5)
                if ready:
                    line = sys.stdin.readline()
                    if not line or line.strip().casefold() in {"", "q", "s", "stop"}:
                        break
                    if line.strip().casefold() == "p":
                        if info["paused"]:
                            resume_recording()
                        else:
                            pause_recording()
            else:
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    if interactive:
        print("\nSaving…", flush=True)
    return stop_recording()


def _menu() -> int:
    current = status()
    if current.get("active"):
        print(_describe(current))
        choice = (
            input("s stop and save · p pause/resume · Enter keep recording: ")
            .strip()
            .casefold()
        )
        if choice == "s":
            print("Saved:", stop_recording()["saved"])
        elif choice == "p":
            info = pause_recording() if not current["paused"] else resume_recording()
            print(_describe(info))
        return 0
    options = [
        ("Screenshot: whole screen", lambda: print("Saved:", shot("screen"))),
        ("Screenshot: select an area", lambda: print("Saved:", shot("area"))),
        ("Screenshot: a window", lambda: print("Saved:", shot("window"))),
        (
            "Record the screen (microphone + system audio)",
            lambda: _record_now("screen", False),
        ),
        (
            "Record the screen with the camera in the corner",
            lambda: _record_now("screen", True),
        ),
        ("Record the camera", lambda: _record_now("camera", False)),
        ("Record audio from the microphone", lambda: _record_now("audio", False)),
        (
            "Open the latest capture",
            lambda: subprocess.run(["open", str(find_capture("last"))], check=False),
        ),
        (
            "Show the capture folder",
            lambda: subprocess.run(
                ["open", str(storage_path("captures"))], check=False
            ),
        ),
    ]
    print("Capture")
    for index, (label, _) in enumerate(options, 1):
        print(f"  {index}  {label}")
    choice = input("Choose 1-9 (Enter cancels): ").strip()
    if not choice:
        return 0
    if not choice.isdigit() or not 1 <= int(choice) <= len(options):
        raise CaptureError(f"pick a number from 1 to {len(options)}")
    options[int(choice) - 1][1]()
    return 0


def _record_now(mode: str, camera: bool) -> None:
    info = start_recording(mode, camera=camera)
    for warning in info.get("warnings", []):
        print(f"Note: {warning}")
    print("Saved:", _watch(None)["saved"])


def _devices_text(info: dict) -> str:
    settings = _settings()
    lines = ["Displays (--display N):"]
    lines += [
        f"  {item['number']}  {item['name']}  {item['pixels']}".rstrip()
        for item in info["displays"]
    ]
    if not info["ffmpeg"]:
        lines.append(
            "Cameras and microphones: install ffmpeg to list them (brew install ffmpeg)."
        )
        return "\n".join(lines)
    lines.append(f"Cameras (capture.camera_device = {settings['camera_device']!r}):")
    lines += [f"  {index}  {name}" for index, name in enumerate(info["cameras"])] or [
        "  none"
    ]
    lines.append(
        f"Microphones (capture.audio_device = {settings['audio_device']!r}, `default` = the system input):"
    )
    lines += [
        f"  {index}  {item['name']}"
        + ("  (virtual: app audio, not your voice)" if item["virtual"] else "")
        for index, item in enumerate(info["microphones"])
    ] or ["  none"]
    chosen = str(settings["audio_device"])
    names = [item["name"] for item in info["microphones"]]
    try:
        resolved = _resolve(chosen, names, "microphone")
    except CaptureError as error:
        lines.append(f"Warning: {error}")
    else:
        if resolved and is_loopback(resolved):
            lines.append(
                f"Warning: capture.audio_device picks {resolved}, a virtual device. Use your microphone: ul config set capture.audio_device default"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = False
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    try:
        as_json = _flag(args, "--json")
        load_config()  # report a broken config.toml before touching anything
        if not args:
            if not sys.stdin.isatty():
                print(USAGE, end="")
                return 2
            return _menu()
        action, rest = args[0], args[1:]
        if action in SHORTCUTS:
            action, kind = SHORTCUTS[action]
            rest = [kind, *rest]
        if action == "shot":
            kind = rest.pop(0) if rest and _is_word(rest[0]) else "screen"
            output = _take(rest, "--output")
            display = _number(_take(rest, "--display"), "--display", 1, 1)
            delay = _number(_take(rest, "--delay"), "--delay", 0)
            clipboard, cursor = _flag(rest, "--clipboard"), _flag(rest, "--cursor")
            jpg, open_after = _flag(rest, "--jpg"), _flag(rest, "--open")
            if rest and not rest[0].startswith("-") and output is None:
                output = rest.pop(0)
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            path = shot(
                kind,
                display=display,
                delay=delay,
                clipboard=clipboard,
                cursor=cursor,
                jpg=jpg,
                output=output,
            )
            if open_after and path:
                subprocess.run(["open", str(path)], check=False)
            _print(
                {"saved": str(path) if path else None, "clipboard": clipboard},
                as_json,
                str(path) if path else "Copied to the clipboard.",
            )
            return 0
        if action == "record":
            mode = rest.pop(0) if rest and _is_word(rest[0]) else "screen"
            if mode not in MODES:
                raise CaptureError(
                    f"unknown recording mode: {mode} (screen, camera or audio)"
                )
            output = _take(rest, "--output")
            mic = _take(rest, "--mic")
            cam = _take(rest, "--cam")
            if _flag(rest, "--no-mic"):
                mic = "none"
            system = (
                True
                if _flag(rest, "--system-audio")
                else False
                if _flag(rest, "--no-system-audio")
                else None
            )
            camera = _flag(rest, "--camera")
            display = _number(_take(rest, "--display"), "--display", 1, 1)
            rect = _take(rest, "--rect")
            fmt = _take(rest, "--format")
            clicks = False if _flag(rest, "--no-clicks") else None
            duration_text = _take(rest, "--duration")
            duration = (
                _number(duration_text, "--duration", 0, 1)
                if duration_text is not None
                else None
            )
            wait = _flag(rest, "--wait")
            if rest and not rest[0].startswith("-") and output is None:
                output = rest.pop(0)
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            if camera and mode != "screen":
                raise CaptureError("--camera adds the camera to a screen recording")
            info = start_recording(
                mode,
                camera=camera,
                cam=cam,
                mic=mic,
                system_audio=system,
                display=display,
                rect=rect,
                clicks=clicks,
                format=fmt,
                output=output,
            )
            for warning in info.get("warnings", []):
                print(f"Note: {warning}", file=sys.stderr)
            if duration is not None or wait:
                result = _watch(float(duration) if duration is not None else None)
                _print(result, as_json, f"Saved: {result['saved']}")
                return 0
            _print(
                info,
                as_json,
                f"Recording {'screen + camera' if info['camera'] else mode}: {info['output']}\nPause: ul capture pause · Stop and save: ul capture stop",
            )
            return 0
        if rest and action in {"pause", "resume", "stop", "status", "devices"}:
            raise CaptureError(f"{action} takes no arguments")
        if action == "pause":
            info = pause_recording()
            _print(info, as_json, _describe(info))
            return 0
        if action == "resume":
            info = resume_recording()
            _print(info, as_json, _describe(info))
            return 0
        if action == "stop":
            result = stop_recording()
            _print(result, as_json, f"Saved: {result['saved']}")
            return 0
        if action == "status":
            info = status()
            _print(info, as_json, _describe(info))
            return 0
        if action == "devices":
            info = devices()
            _print(info, as_json, _devices_text(info))
            return 0
        if action == "list":
            show_all = _flag(rest, "--all")
            limit = _number(rest.pop(0) if rest else None, "list", 20, 1)
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            items = library(None if show_all else limit)
            text = (
                "\n".join(
                    f"{item['modified'][:16].replace('T', ' ')}  {item['kind']:<5}  {(_clock(item['duration']) if item['duration'] else ''):>8}  {item['size'] / 1e6:7.1f} MB  {item['name']}"
                    for item in items
                )
                or "No captures yet. Try: ul capture shot"
            )
            _print(items, as_json, text)
            return 0
        if action in {"last", "open", "reveal"}:
            if action == "last" and _flag(rest, "--reveal"):
                action = "reveal"
            name = rest.pop(0) if rest else "last"
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            path = find_capture(name)
            command = (
                ["open", "-R", str(path)] if action == "reveal" else ["open", str(path)]
            )
            return subprocess.run(command, check=False).returncode
        if action == "wave":
            bars = _number(_take(rest, "--bars"), "--bars", 400, 10)
            if len(rest) != 1:
                raise CaptureError("usage: ul capture wave <name|last|path> [--bars N]")
            data = waveform(rest[0], bars)
            line = "".join(
                " ▁▂▃▄▅▆▇█"[min(8, int(value * 8.99))]
                for value in data["peaks"][:: max(1, len(data["peaks"]) // 80)]
            )
            _print(data, as_json, line)
            return 0
        if action in {"copy", "delete", "thumb"}:
            if len(rest) != 1:
                raise CaptureError(f"usage: ul capture {action} <name|last|path>")
            if action == "copy":
                path = copy_capture(rest[0])
                _print(
                    {"copied": str(path)},
                    as_json,
                    f"Copied {path.name} to the clipboard.",
                )
            elif action == "delete":
                target = delete_capture(rest[0])
                _print(
                    {"trashed": str(target)},
                    as_json,
                    f"Moved to the Trash: {target.name}",
                )
            else:
                path = thumbnail(rest[0])
                _print({"thumbnail": str(path)}, as_json, str(path))
            return 0
        if action == "preview":
            display = _number(_take(rest, "--display"), "--display", 1, 1)
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            path = preview(display)
            _print({"preview": str(path)}, as_json, str(path))
            return 0
        if action == "trim":
            start, end, output = (
                _take(rest, "--from"),
                _take(rest, "--to"),
                _take(rest, "--output"),
            )
            if len(rest) != 1 or start is None and end is None:
                raise CaptureError(
                    "usage: ul capture trim <name|last|path> --from TIME [--to TIME] [--output PATH]"
                )
            target = trim_capture(rest[0], start or "0", end, output)
            _print({"saved": str(target)}, as_json, f"Saved: {target}")
            return 0
        if action == "convert":
            to, output = _take(rest, "--to"), _take(rest, "--output")
            if len(rest) != 1 or to is None:
                raise CaptureError(
                    "usage: ul capture convert <name|last|path> --to mp4|mov|gif|m4a|mp3|wav [--output PATH]"
                )
            target = convert_capture(rest[0], to, output)
            _print({"saved": str(target)}, as_json, f"Saved: {target}")
            return 0
        raise CaptureError(f"Unknown capture action: {action}")
    except CaptureError as error:
        if as_json:
            print(json.dumps({"error": str(error)}))
        else:
            print(f"unlaw capture: {error}", file=sys.stderr)
        return error.code
    except (ConfigError, OSError) as error:
        print(f"unlaw capture: {error}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
