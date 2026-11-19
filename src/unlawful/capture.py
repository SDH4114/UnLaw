from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import select
import shlex
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

from unlawful.command_help import COMMAND_HELP

from .capture_mac import LEVELS_FILE, BackendError, backend, pick_mode, virtual_device
from .capture_project import (
    CAMERA_QUALITY,
    CANVASES,
    MIC_FORMATS,
    ProjectError,
    add_event,
    create_project,
    load_setup,
    projects_dir,
    read_project,
    segment_starts,
    write_project,
)
from .config import ConfigError, load_config, storage_path

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
    """A problem the user can fix; `code` is the exit status, `data` extra JSON keys."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.data: dict = {}


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
def _locked(name: str = "recording", *, refuse_saving: bool = False) -> Iterator[None]:
    """Serialize recording changes or screenshot allocation across CLI processes. A new recording
    (`refuse_saving`) does not wait behind a stop that is still saving: it answers at once."""
    lock = storage_path("runtime", f"{name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        if refuse_saving:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if _phase_on_disk() == "saving":
                        raise CaptureError("the previous recording is still saving; try again in a moment", 1) from None
                    time.sleep(0.1)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _phase_on_disk() -> str | None:
    try:
        state = json.loads(recording_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return state.get("phase") if isinstance(state, dict) else None


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


def devices() -> dict:
    return _backend().devices()


def _resolve(value: str, names: list[str], kind: str) -> str | None:
    """Config/flag value → the AVFoundation name (`default` = the system choice, None = off)."""
    text = str(value).strip()
    if text.casefold() in {"", "default", "auto"}:
        return "default"
    if text.casefold() in {"none", "off", "no"}:
        return None
    if _digits(text):
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


# ---------------------------------------------------------------- recording
#
# A recording is a project folder (capture_project.py): every track goes to its own
# file in media/, one set of files per segment (a pause ends a segment). The state
# file runtime/recording.json (version 2) points at the project while it records.

STATE_VERSION = 2
START_CHECK = 0.7
STOP_GRACE = 30.0
TERM_GRACE = 10.0
KILL_GRACE = 2.0
SILENCE_SECONDS = 10.0
SILENCE_DB = -60.0
LOW_SPACE = 5 * 10**9
PROGRAMS = ("screencapture", "ffmpeg", "osascript")
PHASES = ("recording", "paused", "saving", "interrupted", "unsaved", "stuck")
TRACK_ORDER = ("screen", "camera", "mic")
FALLBACK_MODE = {"width": 1280, "height": 720, "fps": "30"}


def _backend():
    try:
        return backend()
    except BackendError as error:
        raise CaptureError(str(error), 1) from error


def _finite(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and abs(value) < 1e12  # type: ignore[arg-type]
    except OverflowError:  # an int too large for a float
        return False


def _valid_processes(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, dict)
        and type(item.get("pid")) is int
        and 0 < item["pid"] <= 2**31 - 1
        and item.get("program") in PROGRAMS
        and isinstance(item.get("track"), str)
        for item in value
    )


def _valid_plan(plan: object) -> bool:
    if not isinstance(plan, dict):
        return False
    if type(plan.get("display")) is not int or plan["display"] < 1:
        return False
    if not all(
        type(plan.get(key)) is bool
        for key in ("clicks", "system", "mic_in_screen", "nv12")
    ):
        return False
    if not all(
        plan.get(key) is None or isinstance(plan.get(key), str)
        for key in ("area", "camera", "mic")
    ):
        return False
    if any(key not in plan for key in ("area", "camera", "mic", "mode")):
        return False
    mode = plan["mode"]
    if mode is not None and not (
        isinstance(mode, dict)
        and type(mode.get("width")) is int
        and type(mode.get("height")) is int
        and isinstance(mode.get("fps"), str)
    ):
        return False
    return (
        type(plan.get("bitrate")) is int
        and plan.get("mic_format") in MIC_FORMATS
        and plan.get("audio_format") in AUDIO_FORMATS
    )


def _valid_state(state: object) -> bool:
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return False
    if state.get("mode") not in MODES or state.get("phase") not in PHASES:
        return False
    if not all(
        isinstance(state.get(key), str) and state[key]
        for key in ("project", "started", "scene")
    ):
        return False
    if state.get("output") is not None and not isinstance(state.get("output"), str):
        return False
    if state.get("export") is not None and not isinstance(state.get("export"), dict):
        return False
    if type(state.get("paused")) is not bool or not _finite(state.get("elapsed")):
        return False
    if state.get("segment_started") is not None and not _finite(
        state.get("segment_started")
    ):
        return False
    segments, durations = state.get("segments"), state.get("durations")
    if not isinstance(segments, list) or not all(
        isinstance(files, dict)
        and all(
            track in TRACK_ORDER and isinstance(path, str) and path
            for track, path in files.items()
        )
        for files in segments
    ):
        return False
    if not isinstance(durations, list) or not all(
        _finite(value) for value in durations
    ):
        return False
    for key in ("warnings", "problems", "stuck"):
        value = state.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            return False
    return (
        _valid_processes(state.get("processes"))
        and _valid_processes(state.get("helpers"))
        and _valid_plan(state.get("plan"))
    )


def _load_state() -> dict | None:
    path = recording_state_file()
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(state, dict) and "version" not in state and "parts" in state:
            return _wrap_legacy_state(state)
        if not _valid_state(state):
            raise ValueError("not a recording state")
        return state
    except (OSError, ValueError) as error:
        path.unlink(missing_ok=True)
        raise CaptureError(
            f"could not read the recording state ({error}); it was reset", 1
        ) from error


def _wrap_legacy_state(old: dict) -> dict:
    """A recording started by 3.20 or earlier (state version 1): its parts move into a project so that
    `ul capture stop` can still finish it. The old `output` stays the file it is exported to."""
    segments, processes = old.get("segments"), old.get("processes", [])
    if not isinstance(segments, list) or not all(
        isinstance(files, dict) for files in segments
    ):
        raise ValueError("an old recording state without segments")
    if not isinstance(processes, list):
        raise ValueError("an old recording state without processes")
    mode = old.get("mode") if old.get("mode") in MODES else "screen"
    setup, _ = load_setup()
    folder = create_project(mode, setup, {})
    moved: list[dict] = []
    for index, files in enumerate(segments, 1):
        entry = {}
        for key, value in files.items():
            track = "mic" if key in ("audio", "mic") else key
            source = Path(value) if isinstance(value, str) else None
            if track not in TRACK_ORDER or source is None or not source.is_file():
                continue
            dot = "" if track == "mic" else "."
            relative = f"media/{dot}{track}-{index:03d}{source.suffix.casefold()}"
            os.replace(source, folder / relative)
            entry[track] = relative
        moved.append(entry)
    plan = old.get("plan") if isinstance(old.get("plan"), dict) else {}
    output = old.get("output") if isinstance(old.get("output"), str) else None
    audio_format = Path(output).suffix[1:] if output and mode == "audio" else "m4a"
    state = {
        "version": STATE_VERSION,
        "mode": mode,
        "project": str(folder),
        "output": output,
        "export": {} if output else None,
        "phase": "paused" if old.get("paused") is True else "recording",
        "paused": old.get("paused") is True,
        "elapsed": float(old["elapsed"]) if _finite(old.get("elapsed")) else 0.0,
        "segment_started": old.get("segment_started")
        if _finite(old.get("segment_started"))
        else None,
        "started": str(
            old.get("started")
            or datetime.now().astimezone().isoformat(timespec="seconds")
        ),
        "scene": setup["scene"],
        "segments": moved,
        "durations": [],
        "processes": [
            {"pid": item["pid"], "program": item["program"], "track": item["program"]}
            for item in processes
            if isinstance(item, dict)
            and type(item.get("pid")) is int
            and item.get("program") in PROGRAMS
        ],
        "helpers": [],
        "warnings": [],
        "problems": [],
        "stuck": [],
        "plan": {
            "display": plan.get("display")
            if type(plan.get("display")) is int and plan["display"] >= 1
            else 1,
            "area": None,
            "clicks": True,
            "system": True,
            "mic_in_screen": False,
            "camera": None,
            "mode": None,
            "bitrate": 0,
            "nv12": True,
            "mic": None,
            "mic_format": "flac",
            "audio_format": audio_format if audio_format in AUDIO_FORMATS else "m4a",
        },
    }
    parts = old.get("parts")
    if (
        isinstance(parts, str)
        and Path(parts).is_dir()
        and not any(Path(parts).iterdir())
    ):
        Path(parts).rmdir()
    _write_json(recording_state_file(), state)
    return state


def _track_files(state: dict, index: int) -> dict[str, str]:
    """Files of one segment, relative to the project. Video tracks start with a dot until they are
    remuxed at stop (a file that is still being written is never offered to a player)."""
    plan, number = state["plan"], index + 1
    files = {}
    if state["mode"] == "screen":
        files["screen"] = f"media/.screen-{number:03d}.mov"
    if plan["camera"]:
        files["camera"] = f"media/.camera-{number:03d}.mp4"
    if plan["mic"]:
        files["mic"] = f"media/mic-{number:03d}{MIC_FORMATS[plan['mic_format']]}"
    return files


def _recorder(state: dict, track: str, out: Path) -> tuple[str, list[str]]:
    plan, mac = state["plan"], _backend()
    if track == "screen":
        return "screencapture", mac.screen_argv(plan, out)
    if track == "camera":
        return "ffmpeg", mac.camera_argv(plan, out, nv12=plan["nv12"])
    return "ffmpeg", mac.mic_argv(plan, out)


def _log_size(folder: Path, track: str) -> int:
    log = folder / "logs" / f"{track}.log"
    return log.stat().st_size if log.exists() else 0


def _log_tail(folder: Path, track: str, start: int) -> str:
    log = folder / "logs" / f"{track}.log"
    try:
        with log.open("rb") as stream:
            stream.seek(start)
            text = stream.read().decode(errors="replace")
    except OSError:
        return ""
    lines = [
        line for line in text.splitlines() if line.strip() and not line.startswith("$ ")
    ]
    return " ".join(lines[-2:])


def _spawn(command: list[str], folder: Path, track: str) -> subprocess.Popen:
    logs = folder / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"{track}.log").open("ab") as log:
        log.write(f"$ {shlex.join(command)}\n".encode())
        log.flush()
        return subprocess.Popen(
            command,
            cwd=logs,  # the microphone writes mic-levels.txt here
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            # Safe: only the single-threaded CLI spawns recorders (the desk runs `ul capture`).
            preexec_fn=_default_signals,  # noqa: PLW1509
        )


def _permission_hint(what: str) -> str:
    app = _backend().responsible_app()
    who = app or "the app that runs ul (your terminal or editor)"
    return (
        f"Give {who} {what} permission: System Settings > Privacy & Security > {what}, "
        f"then restart {app or 'it'}. `ul capture doctor --open screen` opens the page."
    )


def _start_failure(track: str, reason: str) -> str:
    what = {"screen": "Screen Recording", "camera": "Camera", "mic": "Microphone"}[
        track
    ]
    return f"the {track} recorder could not start: {reason or 'it stopped right away'}. {_permission_hint(what)}"


def _start_segment(state: dict) -> None:
    folder = Path(state["project"])
    files = _track_files(state, len(state["segments"]))
    offsets = {track: _log_size(folder, track) for track in files}
    started: list[tuple[str, str, subprocess.Popen]] = []
    # The clock starts when the recorders start, not after the start check below.
    spawned = time.time()
    try:
        for track, relative in files.items():
            program, command = _recorder(state, track, folder / relative)
            started.append((track, program, _spawn(command, folder, track)))
        # A missing permission or a busy device makes the tools exit within a moment;
        # later failures show up as the `interrupted` phase in `status`.
        deadline = time.monotonic() + START_CHECK
        while time.monotonic() < deadline:
            for position, (track, program, process) in enumerate(started):
                if process.poll() is None:
                    continue
                reason = _log_tail(folder, track, offsets[track])
                if (
                    track == "camera"
                    and state["plan"]["nv12"]
                    and "pixel format" in reason
                ):
                    # Some cameras (iPhone, capture cards) refuse nv12: try once with their own format.
                    state["plan"]["nv12"] = False
                    offsets[track] = _log_size(folder, track)
                    _, command = _recorder(state, track, folder / files[track])
                    started[position] = (track, program, _spawn(command, folder, track))
                    deadline = time.monotonic() + START_CHECK
                    continue
                raise CaptureError(_start_failure(track, reason), 1)
            time.sleep(0.1)
        state["segments"].append(files)
        state["processes"] = [
            {"pid": process.pid, "program": program, "track": track}
            for track, program, process in started
        ]
        state["segment_started"] = spawned
        state["paused"] = False
        state["phase"] = "recording"
        _write_json(recording_state_file(), state)
    except BaseException:
        # Until the state is committed, only these Popen handles can stop the
        # detached recorders. This also covers Ctrl-C and a full state-file disk.
        for _, _, process in started:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        for _, _, process in started:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise


def _alive(pid: int, program: str) -> bool:
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    command = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    # A reused pid (after a reboot) must never be signalled: it has to be our tool.
    return program in command


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


def _elapsed_now(state: dict) -> float:
    running = state.get("segment_started") and not state["paused"]
    return state["elapsed"] + (
        time.time() - state["segment_started"] if running else 0.0
    )


def _stop_segment(state: dict, *, force: bool = False) -> list[str]:
    """Stop every recorder together: SIGINT lets them finish their files. One that is still alive after
    SIGTERM is never killed unless `force` (a killed screencapture loses its whole file); it is returned."""
    stopped_at = time.time()
    running = bool(state.get("segment_started")) and not state["paused"]
    elapsed = _elapsed_now(state)
    processes = state["processes"]

    def alive() -> list[dict]:
        return [item for item in processes if _alive(item["pid"], item["program"])]

    steps = [
        (signal.SIGINT, max(STOP_GRACE, 0.05 * elapsed)),
        (signal.SIGTERM, TERM_GRACE),
    ]
    if force:
        steps.append((signal.SIGKILL, KILL_GRACE))
    for number, wait in steps:
        current = alive()
        if not current:
            break
        _signal_all(current, number)
        deadline = time.monotonic() + wait
        while alive() and time.monotonic() < deadline:
            time.sleep(0.05)
    left = alive()
    if running:
        state["durations"].append(round(stopped_at - state["segment_started"], 3))
        state["elapsed"] = elapsed
    state["processes"] = left
    state["segment_started"] = None
    state["stuck"] = sorted({item["program"] for item in left})
    return state["stuck"]


def _scene_id(scenes: list[dict], value: str) -> str:
    text = str(value).strip()
    listing = ", ".join(
        f"{number} {scene['name']}" for number, scene in enumerate(scenes, 1)
    )
    if _digits(text):
        number = int(text)
        if 1 <= number <= len(scenes):
            return scenes[number - 1]["id"]
        raise CaptureError(f"there is no scene {number}; scenes: {listing}")
    for scene in scenes:
        if (
            text in (scene["id"], scene["name"])
            or scene["name"].casefold() == text.casefold()
        ):
            return scene["id"]
    raise CaptureError(f"no scene {text!r}; scenes: {listing}")


def _source(setup: dict, kind: str) -> dict | None:
    return next((source for source in setup["sources"] if source["kind"] == kind), None)


def _plain(value: str) -> bool:
    return value.strip().casefold() in {"", "default", "auto", "none", "off", "no"}


def start_recording(
    mode: str = "screen",
    *,
    scene: str | None = None,
    canvas: str | None = None,
    overrides: dict | None = None,
) -> dict:
    """Start a recording in the background; `stop_recording` saves the project.

    `overrides` (CLI flags, the desk's request) change this recording only: camera (bool), cam,
    cam_mode, cam_quality, mic (`none` = off), mic_format, system_audio, display, rect, clicks,
    format (container of the export), output and export (export right after stop)."""
    if mode not in MODES:
        raise CaptureError(f"unknown recording mode: {mode} (screen, camera or audio)")
    options = dict(overrides or {})
    settings = _settings()
    setup, setup_warnings = load_setup()
    setup = copy.deepcopy(setup)
    screen_source, camera_source = _source(setup, "screen"), _source(setup, "camera")
    fmt = options.get("format")
    video_format = (
        settings["video_format"] if settings["video_format"] in VIDEO_FORMATS else "mov"
    )
    audio_format = (
        settings["audio_format"] if settings["audio_format"] in AUDIO_FORMATS else "m4a"
    )
    if mode == "audio":
        audio_format = fmt or audio_format
        if audio_format not in AUDIO_FORMATS:
            raise CaptureError(
                f"audio format must be one of {', '.join(AUDIO_FORMATS)}"
            )
    else:
        video_format = fmt or video_format
        if video_format not in VIDEO_FORMATS:
            raise CaptureError(
                f"video format must be one of {', '.join(VIDEO_FORMATS)}"
            )
    rect = options.get("rect")
    if rect is not None:
        numbers = rect.split(",")
        if (
            mode != "screen"
            or len(numbers) != 4
            or not all(_digits(number.strip()) for number in numbers)
        ):
            raise CaptureError(
                "--rect needs X,Y,WIDTH,HEIGHT in points and only works for the screen"
            )
        rect = ",".join(number.strip() for number in numbers)
    display = options.get("display") or (
        screen_source["display"] if screen_source else 1
    )
    if display < 1:
        raise CaptureError("--display starts at 1 (the main display)")
    if canvas is not None and canvas not in CANVASES:
        raise CaptureError(f"--canvas must be one of {', '.join(CANVASES)}")
    quality = options.get("cam_quality") or (
        camera_source["quality"] if camera_source else "high"
    )
    if quality not in CAMERA_QUALITY:
        raise CaptureError("--cam-quality must be max, high or light")
    mic_format = options.get("mic_format") or setup["audio"]["mic"]["format"]
    if mic_format not in MIC_FORMATS:
        raise CaptureError("--mic-format must be flac, wav or m4a")
    camera_wanted = options.get("camera")
    if camera_wanted is None:
        camera_wanted = (
            bool(camera_source and camera_source["enabled"]) and mode == "screen"
        )
    want_camera = mode == "camera" or bool(camera_wanted and mode == "screen")
    if mode == "screen":
        _need("screencapture", "for screen recording")
    mic_setup = setup["audio"]["mic"]
    if options.get("mic") is not None:
        mic_value = str(options["mic"])
    elif mode != "screen" or mic_setup["enabled"]:
        mic_value = mic_setup["device"]
    else:
        mic_value = "none"
    plain_mic = _plain(mic_value)
    has_ffmpeg = shutil.which("ffmpeg") is not None
    if want_camera or mode == "audio" or not plain_mic:
        _need("ffmpeg", "for camera, microphone and audio recording")
    cam_value = str(
        options.get("cam") or (camera_source["device"] if camera_source else "default")
    )
    # Listing devices costs ffmpeg half a second; `default` and `none` need no list.
    must_list = not plain_mic or (want_camera and not _plain(cam_value))
    cameras, microphones = _backend().list_avfoundation() if must_list else ([], [])
    mic_name = _resolve(mic_value, microphones, "microphone")
    if mode == "audio" and mic_name is None:
        raise CaptureError("audio recording needs a microphone")
    camera_name = _resolve(cam_value, cameras, "camera") if want_camera else None
    if want_camera and camera_name is None:
        raise CaptureError(
            "the camera is off; pick one with --cam NAME or capture.camera_device"
        )
    system = (
        setup["audio"]["system"]["enabled"]
        if options.get("system_audio") is None
        else options["system_audio"]
    )
    if system and mode != "screen":
        if options.get("system_audio"):
            raise CaptureError("system audio is recorded with the screen only")
        system = False
    warnings = list(setup_warnings)
    mic_in_screen = mode == "screen" and mic_name == "default" and not has_ffmpeg
    if mic_in_screen:
        warnings.append(
            "ffmpeg is not installed: the microphone goes into the screen track (brew install ffmpeg)"
        )
    if mic_name and virtual_device(mic_name):
        warnings.append(
            f"{mic_name} is a virtual device: it records app audio routed to it, not your voice"
        )
    camera_mode = None
    if camera_name:
        wanted = options.get("cam_mode") or (
            camera_source["mode"] if camera_source else "auto"
        )
        camera_mode = pick_mode(
            _backend().camera_modes(camera_name), quality, wanted
        ) or dict(FALLBACK_MODE)
    if mode == "camera":
        scene_id = (
            "camera"
            if any(item["id"] == "camera" for item in setup["scenes"])
            else setup["scene"]
        )
    else:
        scene_id = (
            _scene_id(setup["scenes"], scene) if scene is not None else setup["scene"]
        )
    clicks = options.get("clicks")
    if clicks is None:
        clicks = screen_source["clicks"] if screen_source else True
    output = None
    if options.get("output"):
        extension = "." + (audio_format if mode == "audio" else video_format)
        path = Path(options["output"]).expanduser().absolute()
        output = str(
            path if path.suffix.casefold() == extension else path.with_suffix(extension)
        )
    if mode == "screen" and not _backend().permission_probe()["screen"]:
        raise CaptureError(
            f"screen recording is not allowed. {_permission_hint('Screen Recording')}",
            1,
        )
    # This recording's choices go into the project's copy of the setup, never into the saved setup.
    setup["scene"] = scene_id
    if canvas:
        setup["canvas"] = canvas
    setup["export"]["container"] = video_format
    if camera_source:
        camera_source["enabled"] = want_camera
        if camera_name:
            camera_source["device"] = camera_name
            camera_source["quality"] = quality
    if screen_source:
        screen_source.update(
            display=display, area=rect, clicks=bool(clicks), enabled=mode == "screen"
        )
    mic_setup.update(enabled=mic_name is not None, format=mic_format)
    if mic_name:
        mic_setup["device"] = mic_name
    setup["audio"]["system"]["enabled"] = bool(system)
    recorded = {}
    if camera_name and camera_mode:
        recorded["camera"] = {
            "mode": f"{camera_mode['width']}x{camera_mode['height']}@{camera_mode['fps']}"
        }
    with _locked(refuse_saving=True):
        try:
            running = _load_state()
        except CaptureError:
            running = None  # a damaged state file was reset; start fresh
        if running is not None:
            raise CaptureError(
                "a recording is already running; stop it with `ul capture stop`", 1
            )
        kind = "screen-camera" if mode == "screen" and want_camera else mode
        try:
            folder = create_project(kind, setup, recorded)
        except ProjectError as error:
            raise CaptureError(str(error), 1) from error
        state = {
            "version": STATE_VERSION,
            "mode": mode,
            "project": str(folder),
            "output": output,
            "export": {} if output or options.get("export") else None,
            "phase": "recording",
            "paused": False,
            "elapsed": 0.0,
            "segment_started": None,
            "started": datetime.now().astimezone().isoformat(timespec="seconds"),
            "scene": scene_id,
            "segments": [],
            "durations": [],
            "processes": [],
            "helpers": [],
            "warnings": warnings,
            "problems": [],
            "stuck": [],
            "plan": {
                "display": display,
                "area": rect,
                "clicks": bool(clicks),
                "system": bool(system),
                "mic_in_screen": mic_in_screen,
                "camera": camera_name,
                "mode": camera_mode,
                "bitrate": CAMERA_QUALITY[quality][1],
                "nv12": True,
                "mic": None if mic_in_screen else mic_name,
                "mic_format": mic_format,
                "audio_format": audio_format,
            },
        }
        try:
            _start_segment(state)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return status()


def pause_recording() -> dict:
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("nothing is recording", 1)
        if state["paused"]:
            return status()
        stuck = _stop_segment(state)
        state["paused"] = True
        state["phase"] = "stuck" if stuck else "paused"
        _write_json(recording_state_file(), state)
    if stuck:
        raise CaptureError(_stuck_message(stuck), 1)
    return status()


def resume_recording() -> dict:
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("nothing is recording", 1)
        if state["phase"] == "stuck":
            raise CaptureError(_stuck_message(state["stuck"]), 1)
        if not state["paused"]:
            return status()
        _start_segment(state)
    return status()


def switch_scene(scene: str) -> dict:
    """Switch the scene now; while paused it applies from the resume point."""
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("nothing is recording", 1)
        folder = Path(state["project"])
        try:
            scene_id = _scene_id(read_project(folder)["scenes"], scene)
            add_event(folder, {"t": round(_elapsed_now(state), 3), "scene": scene_id})
        except ProjectError as error:
            raise CaptureError(str(error), 1) from error
        state["scene"] = scene_id
        _write_json(recording_state_file(), state)
    return status()


def add_mark(label: str = "") -> dict:
    if len(label) > 200 or any(ord(char) < 32 for char in label):
        raise CaptureError("a mark is one line of at most 200 characters")
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("nothing is recording", 1)
        at = round(_elapsed_now(state), 3)
        try:
            add_event(Path(state["project"]), {"t": at, "mark": label})
        except ProjectError as error:
            raise CaptureError(str(error), 1) from error
    return {**status(), "mark": {"t": at, "label": label}}


def _mic_level(state: dict) -> tuple[float | None, bool]:
    """The newest microphone peak (dBFS) and whether it stayed below SILENCE_DB for SILENCE_SECONDS."""
    if not state["plan"]["mic"] or state["paused"]:
        return None, False
    path = Path(state["project"]) / "logs" / LEVELS_FILE
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            text = stream.read().decode(errors="replace")
    except OSError:
        return None, False
    samples: list[tuple[float, float]] = []
    moment = 0.0
    for line in text.splitlines():
        if "pts_time:" in line:
            try:
                moment = float(line.rsplit("pts_time:", 1)[1].split()[0])
            except (ValueError, IndexError):
                continue
        elif "Peak_level=" in line:
            try:
                level = float(line.rsplit("=", 1)[1])
            except ValueError:
                continue
            if not math.isnan(level):
                samples.append((moment, level))
    if not samples:
        return None, False
    last_time, last_level = samples[-1]
    window = [level for at, level in samples if at >= last_time - SILENCE_SECONDS]
    silent = last_time >= SILENCE_SECONDS and all(
        level < SILENCE_DB for level in window
    )
    return (round(last_level, 1) if math.isfinite(last_level) else -120.0), silent


def status() -> dict:
    try:
        state = _load_state()
    except CaptureError:
        state = None
    if state is None:
        return {"active": False}
    elapsed = _elapsed_now(state)
    alive = [
        item for item in state["processes"] if _alive(item["pid"], item["program"])
    ]
    phase = state["phase"]
    if (
        phase == "recording"
        and state["processes"]
        and len(alive) < len(state["processes"])
    ):
        phase = "interrupted"
    warnings = list(state["warnings"])
    level, silent = _mic_level(state) if phase == "recording" else (None, False)
    if silent:
        warnings.append(
            f"the microphone is silent (below {SILENCE_DB:.0f} dB for {SILENCE_SECONDS:.0f} s)"
        )
    try:
        free = shutil.disk_usage(state["project"]).free
    except OSError:
        free = None
    if free is not None and free < LOW_SPACE:
        warnings.append(f"only {free / 1e9:.1f} GB free on the recording disk")
    tracks = sorted(
        {track for files in state["segments"] for track in files}, key=TRACK_ORDER.index
    )
    return {
        "active": True,
        "version": STATE_VERSION,
        "mode": state["mode"],
        "camera": bool(state["plan"]["camera"]),
        "phase": phase,
        "paused": state["paused"],
        "elapsed": round(elapsed, 1),
        "project": state["project"],
        "output": state["output"] or state["project"],
        "started": state["started"],
        "scene": state["scene"],
        "tracks": tracks,
        "level_db": level,
        "stuck": state["stuck"],
        "free_bytes": free,
        "warnings": warnings,
    }


# ---------------------------------------------------------------- finishing


def _probe(path: str) -> dict:
    empty = {
        "duration": 0.0,
        "audio": False,
        "video": False,
        "width": 0,
        "height": 0,
        "codecs": [],
    }
    if shutil.which("ffprobe") is None:
        return empty
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
        return empty
    streams = data.get("streams", [])
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), {}
    )
    try:
        duration = float(data.get("format", {}).get("duration", 0) or 0)
    except ValueError:
        duration = 0.0
    return {
        "duration": duration if math.isfinite(duration) else 0.0,
        "audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "video": bool(video),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "codecs": [stream.get("codec_name") for stream in streams],
    }


def _repair_wav(path: Path) -> None:
    """ffmpeg writes the WAV sizes at the end; a recorder stopped hard leaves them 0. Set them from the file."""
    try:
        with path.open("r+b") as stream:
            head = stream.read(12)
            if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return
            size = path.stat().st_size
            offset = 12
            while offset + 8 <= size:
                stream.seek(offset)
                chunk = stream.read(8)
                name, length = chunk[:4], int.from_bytes(chunk[4:], "little")
                if name == b"data":
                    actual = size - offset - 8
                    if length != actual:
                        stream.seek(offset + 4)
                        stream.write(min(actual, 0xFFFFFFFF).to_bytes(4, "little"))
                        stream.seek(4)
                        stream.write(min(size - 8, 0xFFFFFFFF).to_bytes(4, "little"))
                    return
                offset += 8 + length + (length & 1)
    except OSError:
        return


def _finished_track(folder: Path, track: str, relative: str) -> str | None:
    """The track's playable file (relative), remuxing a dot file the first time; None if nothing was recorded."""
    path = folder / relative
    name = Path(relative).name
    if not name.startswith("."):
        if path.suffix == ".wav" and path.is_file():
            _repair_wav(path)
        return relative if path.is_file() and path.stat().st_size > 0 else None
    has_ffmpeg = shutil.which("ffmpeg") is not None
    final_name = Path(name[1:]).with_suffix(".mp4" if has_ffmpeg else path.suffix).name
    final_relative = f"media/{final_name}"
    final = folder / final_relative
    if path.is_file() and path.stat().st_size > 0:
        if has_ffmpeg:
            temporary = final.with_name(f".remux-{final.name}")
            try:
                _run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-nostdin",
                        "-y",
                        "-i",
                        str(path),
                        "-map",
                        "0",
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(temporary),
                    ],
                    f"saving the {track} recording",
                )
                os.replace(temporary, final)
            finally:
                temporary.unlink(missing_ok=True)
            path.unlink()
        else:
            os.replace(path, final)
        return final_relative
    if final.is_file() and final.stat().st_size > 0:
        return final_relative  # remuxed by an earlier try
    return None


def _finish(state: dict) -> dict:
    """Write what was recorded into project.json: playable files, durations, start offsets, problems."""
    folder = Path(state["project"])
    try:
        project = read_project(folder)
    except ProjectError as error:
        raise CaptureError(str(error), 1) from error
    stuck_tracks = {item["track"] for item in state["processes"]}
    problems = list(state["problems"])
    segments = []
    for index, files in enumerate(state["segments"]):
        final: dict[str, str] = {}
        lengths: dict[str, float] = {}
        info: dict[str, dict] = {}
        for track, relative in files.items():
            done = (
                None
                if track in stuck_tracks and index == len(state["segments"]) - 1
                else _finished_track(folder, track, relative)
            )
            if done is None:
                why = "is still running" if track in stuck_tracks else "is missing"
                problems.append(f"part {index + 1}: the {track} recording {why}")
                continue
            final[track] = done
            probed = _probe(str(folder / done))
            lengths[track] = probed["duration"]
            if probed["video"] or probed["audio"]:
                info[track] = {"width": probed["width"], "height": probed["height"], "audio": probed["audio"]}
        if not final:
            continue
        measured = state["durations"][index] if index < len(state["durations"]) else 0.0
        reference = next(
            (track for track in TRACK_ORDER if lengths.get(track, 0) > 0), None
        )
        if reference is None:
            starts, duration = {track: 0.0 for track in final}, measured
        else:
            known = {track: length for track, length in lengths.items() if length > 0}
            starts = {track: 0.0 for track in final} | segment_starts(known, reference)
            duration = lengths[reference]
        segments.append(
            {"duration": round(duration, 3), "files": final, "starts": starts, "info": info}
        )
    if not segments and not stuck_tracks:
        media = folder / "media"
        if folder.parent == projects_dir() and not any(
            item.is_file() and item.stat().st_size for item in media.iterdir()
        ):
            shutil.rmtree(folder, ignore_errors=True)
        recording_state_file().unlink(missing_ok=True)
        raise CaptureError(
            "nothing was recorded (check the Screen Recording, Camera and Microphone permissions)",
            1,
        )
    project["segments"] = segments
    project["duration"] = round(sum(segment["duration"] for segment in segments), 3)
    project["problems"] = problems
    project["state"] = "incomplete" if problems else "ready"
    if state["mode"] == "audio":
        project["audio_format"] = state["plan"]["audio_format"]
    try:
        write_project(folder, project)
    except ProjectError as error:
        raise CaptureError(str(error), 1) from error
    return {
        "active": False,
        "project": str(folder),
        "saved": str(folder),
        "elapsed": round(state["elapsed"], 1),
        "state": project["state"],
        "problems": problems,
    }


def _stuck_message(stuck: list[str]) -> str:
    tools = ", ".join(stuck)
    return (
        f"{tools} did not stop. The project was saved without that track. "
        "Run `ul capture stop` to try again, or `ul capture stop --force` to end it (its track is lost)."
    )


def stop_recording(*, force: bool = False) -> dict:
    """Stop all recorders and save the project; a recorder that hangs is reported, not killed."""
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("no active recording", 1)
        if state["phase"] == "recording" and not state["paused"]:
            for item in state["processes"]:
                if not _alive(item["pid"], item["program"]):
                    state["problems"].append(
                        f"the {item['track']} recorder stopped during the recording"
                    )
        stuck = _stop_segment(state, force=force)
        _stop_helpers(state)
        state["phase"] = "saving"
        _write_json(recording_state_file(), state)
        try:
            result = _finish(state)
            if stuck:
                state["phase"] = "stuck"
                _write_json(recording_state_file(), state)
                error = CaptureError(_stuck_message(stuck), 1)
                error.data = {"stuck": stuck, "project": result["project"]}
                raise error
            result = _export_after_stop(state, result)
        except CaptureError:
            if recording_state_file().exists() and state["phase"] != "stuck":
                state["phase"] = "unsaved"
                _write_json(recording_state_file(), state)
            raise
        except BaseException:  # also Ctrl-C while saving: never stay "saving"
            if recording_state_file().exists():
                state["phase"] = "unsaved"
                _write_json(recording_state_file(), state)
            raise
        recording_state_file().unlink(missing_ok=True)
    return result


def _stop_helpers(state: dict) -> None:
    """The menu-bar helper only shows the recording; it is told to quit and never waited for."""
    _signal_all(state["helpers"], signal.SIGTERM)
    state["helpers"] = []


def _export_after_stop(state: dict, result: dict) -> dict:
    return result


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
        _run(_backend().preview_argv(display, temporary), "the preview")
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


def _digits(text: str) -> bool:
    """ASCII digits only: str.isdigit() also accepts "²", which int() refuses."""
    return text.isascii() and text.isdigit()


def _number(text: str | None, flag: str, default: int, minimum: int = 0) -> int:
    if text is None:
        return default
    if not _digits(text) or int(text) < minimum:
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
        "stuck": "A recorder does not stop",
    }.get(info["phase"], info["phase"])
    line = f"{state} {what} {_clock(info['elapsed'])} → {info['output']}"
    if info["phase"] in {"interrupted", "unsaved"}:
        line += "\nRun `ul capture stop` to save what was recorded."
    if info["phase"] == "stuck":
        line += f"\n{', '.join(info['stuck'])} still runs: `ul capture stop` tries again, `ul capture stop --force` ends it."
    return line


def _saved_text(result: dict) -> str:
    if result["saved"] != result.get("project"):
        return f"Saved: {result['saved']}"
    text = f"Saved project: {result['saved']}"
    if result.get("problems"):
        text += "\nIncomplete: " + "; ".join(result["problems"])
    return text + "\nExport a video: ul capture export last"


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
            print(_saved_text(stop_recording()))
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
    if not _digits(choice) or not 1 <= int(choice) <= len(options):
        raise CaptureError(f"pick a number from 1 to {len(options)}")
    options[int(choice) - 1][1]()
    return 0


def _record_now(mode: str, camera: bool) -> None:
    info = start_recording(mode, overrides={"camera": camera})
    for warning in info.get("warnings", []):
        print(f"Note: {warning}")
    print(_saved_text(_watch(None)))


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
        if resolved and virtual_device(resolved):
            lines.append(
                f"Warning: capture.audio_device picks {resolved}, a virtual device. Use your microphone: ul config set capture.audio_device default"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = False
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP["capture"], end="")
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
                raise CaptureError(f"unknown recording mode: {mode} (screen, camera or audio)")
            options: dict = {
                "output": _take(rest, "--output"),
                "mic": _take(rest, "--mic"),
                "cam": _take(rest, "--cam"),
                "cam_mode": _take(rest, "--cam-mode"),
                "cam_quality": _take(rest, "--cam-quality"),
                "mic_format": _take(rest, "--mic-format"),
                "rect": _take(rest, "--rect"),
                "format": _take(rest, "--format"),
            }
            scene = _take(rest, "--scene")
            canvas = _take(rest, "--canvas")
            if _flag(rest, "--no-mic"):
                options["mic"] = "none"
            if _flag(rest, "--system-audio"):
                options["system_audio"] = True
            elif _flag(rest, "--no-system-audio"):
                options["system_audio"] = False
            if _flag(rest, "--camera"):
                options["camera"] = True
            elif _flag(rest, "--no-camera"):
                options["camera"] = False
            display = _take(rest, "--display")
            if display is not None:
                options["display"] = _number(display, "--display", 1, 1)
            if _flag(rest, "--no-clicks"):
                options["clicks"] = False
            options["export"] = _flag(rest, "--export")
            duration_text = _take(rest, "--duration")
            duration = _number(duration_text, "--duration", 0, 1) if duration_text is not None else None
            wait = _flag(rest, "--wait")
            if rest and not rest[0].startswith("-") and options["output"] is None:
                options["output"] = rest.pop(0)
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            if options.get("camera") and mode != "screen":
                raise CaptureError("--camera adds the camera to a screen recording")
            info = start_recording(
                mode, scene=scene, canvas=canvas, overrides={key: value for key, value in options.items() if value is not None}
            )
            for warning in info.get("warnings", []):
                print(f"Note: {warning}", file=sys.stderr)
            if duration is not None or wait:
                result = _watch(float(duration) if duration is not None else None)
                _print(result, as_json, _saved_text(result))
                return 0
            what = "screen + camera" if info["camera"] else mode
            _print(info, as_json, f"Recording {what}: {info['project']}\nPause: ul capture pause · Stop and save: ul capture stop")
            return 0
        if action == "scene":
            if len(rest) != 1:
                raise CaptureError("usage: ul capture scene N|ID")
            info = switch_scene(rest[0])
            _print(info, as_json, f"Scene: {info['scene']}")
            return 0
        if action == "mark":
            info = add_mark(" ".join(rest))
            _print(info, as_json, f"Mark at {_clock(info['mark']['t'])}")
            return 0
        if action == "stop":
            force = _flag(rest, "--force")
            if rest:
                raise CaptureError("stop takes no arguments (only --force)")
            result = stop_recording(force=force)
            _print(result, as_json, _saved_text(result))
            return 0
        if rest and action in {"pause", "resume", "status", "devices"}:
            raise CaptureError(f"{action} takes no arguments")
        if action == "pause":
            info = pause_recording()
            _print(info, as_json, _describe(info))
            return 0
        if action == "resume":
            info = resume_recording()
            _print(info, as_json, _describe(info))
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
            print(json.dumps({"error": str(error), **error.data}, ensure_ascii=False))
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
