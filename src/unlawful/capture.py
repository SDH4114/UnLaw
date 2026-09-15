from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from .config import ConfigError, load_config, storage_path

USAGE = """Usage: ul capture <action> [output]

Actions:
  screenshot       Capture the full screen as PNG
  area             Select an area to capture
  window           Select a window to capture
  screen           Start a screen recording with microphone
  camera           Start camera and microphone recording through ffmpeg
  audio            Start microphone recording through ffmpeg
  devices          List camera and audio devices
  stop             Stop the active recording
  last             Open the latest capture
"""


def recording_state_file() -> Path:
    return storage_path("runtime", "recording.json")


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _output_path(mode: str, supplied: str | None) -> Path:
    if supplied:
        return Path(supplied).expanduser()
    if mode in {"screenshot", "area", "window"}:
        return storage_path("captures", "screenshots", f"{mode}-{_timestamp()}.png")
    extension = ".m4a" if mode == "audio" else ".mov"
    return storage_path("captures", "recordings", f"{mode}-{_timestamp()}{extension}")


def recording_command(
    mode: str,
    output: Path,
    *,
    camera_device: str,
    audio_device: str,
    duration: int = 0,
    screen_audio: bool = True,
    show_clicks: bool = True,
) -> list[str]:
    if mode == "screen":
        command = ["screencapture", "-v"]
        if screen_audio:
            command.append("-g")
        if show_clicks:
            command.append("-k")
        if duration > 0:
            command.append(f"-V{duration}")
        return [*command, str(output)]
    if mode == "camera":
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "avfoundation",
            "-framerate",
            "30",
            "-i",
            f"{camera_device}:{audio_device}",
            "-c:v",
            "h264_videotoolbox",
            "-c:a",
            "aac",
        ]
        if duration > 0:
            command.extend(["-t", str(duration)])
        return [*command, str(output)]
    if mode == "audio":
        command = ["ffmpeg", "-y", "-f", "avfoundation", "-i", f":{audio_device}", "-c:a", "aac"]
        if duration > 0:
            command.extend(["-t", str(duration)])
        return [*command, str(output)]
    raise ValueError(f"Unknown recording mode: {mode}")


def _screenshot(mode: str, output: Path) -> int:
    flags = {
        "screenshot": ["-x"],
        "area": ["-i", "-s"],
        "window": ["-i", "-W"],
    }[mode]
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["screencapture", *flags, str(output)], check=False)
    if result.returncode == 0:
        print(output)
    return result.returncode


def _start_recording(mode: str, output: Path, settings: dict[str, object], duration: int) -> int:
    state_path = recording_state_file()
    if state_path.exists():
        print("unlaw capture: a recording is already active; run `ul capture stop`.", file=sys.stderr)
        return 1
    if mode in {"camera", "audio"} and shutil.which("ffmpeg") is None:
        print("unlaw capture: ffmpeg is required for camera and audio recording.", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    command = recording_command(
        mode,
        output,
        camera_device=str(settings["camera_device"]),
        audio_device=str(settings["audio_device"]),
        duration=duration,
        screen_audio=bool(settings["screen_audio"]),
        show_clicks=bool(settings["show_clicks"]),
    )
    log_path = storage_path("runtime", "recording.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    state_path.write_text(
        json.dumps({"pid": process.pid, "mode": mode, "output": str(output), "command": command}, indent=2),
        encoding="utf-8",
    )
    print(f"Recording {mode}: {output}")
    print("Stop with: ul capture stop")
    return 0


def _stop() -> int:
    state_path = recording_state_file()
    if not state_path.is_file():
        print("unlaw capture: no active recording.", file=sys.stderr)
        return 1
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        pid = int(state["pid"])
        os.kill(pid, signal.SIGINT)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"unlaw capture: could not stop recording: {error}", file=sys.stderr)
        return 1
    finally:
        state_path.unlink(missing_ok=True)
    print(f"Saved: {state['output']}")
    return 0


def latest_capture() -> Path | None:
    roots = [storage_path("captures", "screenshots"), storage_path("captures", "recordings")]
    files = [item for root in roots if root.is_dir() for item in root.iterdir() if item.is_file()]
    return max(files, key=lambda item: item.stat().st_mtime, default=None)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(USAGE, end="")
        return 0 if args else 2
    try:
        settings = load_config()["capture"]
        action, rest = args[0], args[1:]
        if action == "stop" and not rest:
            return _stop()
        if action == "devices" and not rest:
            if shutil.which("ffmpeg") is None:
                raise OSError("ffmpeg is not installed")
            return subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""], check=False
            ).returncode
        if action == "last" and not rest:
            latest = latest_capture()
            if latest is None:
                raise FileNotFoundError("no captures found")
            return subprocess.run(["open", str(latest)], check=False).returncode
        if action not in {"screenshot", "area", "window", "screen", "camera", "audio"}:
            raise ValueError(f"Unknown capture action: {action}")
        duration = 0
        if "--duration" in rest:
            at = rest.index("--duration")
            if at + 1 >= len(rest):
                raise ValueError("--duration requires seconds")
            duration = int(rest[at + 1])
            if duration < 1:
                raise ValueError("duration must be positive")
            del rest[at : at + 2]
        if len(rest) > 1:
            raise ValueError("only one output path is allowed")
        output = _output_path(action, rest[0] if rest else None)
        if action in {"screenshot", "area", "window"}:
            return _screenshot(action, output)
        return _start_recording(action, output, settings, duration)
    except (ConfigError, FileNotFoundError, OSError, ValueError) as error:
        print(f"unlaw capture: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
