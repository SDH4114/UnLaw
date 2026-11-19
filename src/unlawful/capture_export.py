"""Export of Studio projects: the separate tracks of a project become one video (or audio file).

The timeline is cut into intervals at pauses and scene switches; each interval is rendered by one
ffmpeg run with that scene's layout, the chunks are joined by stream copy, and the sound (system
sound and microphone, each at its own start offset) is mixed per segment and muxed at the end.
Masks, borders and shadows are PNGs drawn here (no image library).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .capture_project import (
    _even,
    ProjectError,
    canvas_size,
    effective_placements,
    load_setup,
    read_project,
    save_setup,
    timeline_intervals,
    validate_export,
    video_bitrate,
    write_json_atomic,
    write_project,
)
from .config import load_config, storage_path

EXPORT_LOCK = "export"
FFMPEG_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
AUDIO_CODECS = {
    "m4a": ["-c:a", "aac", "-b:a", "256k"],
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-c:a", "pcm_s16le"],
}
DEFAULT_EXPORT = {
    "canvas": "16:9",
    "height": 1440,
    "fps": 60,
    "codec": "h264",
    "quality": "high",
    "container": "mov",
    "normalize": True,
    "delete_sources": False,
}


class ExportError(Exception):
    """An export that could not be made; the project is left as it was."""


# ---------------------------------------------------------------- PNG drawing


def _png(width: int, height: int, color_type: int, rows: list[bytes]) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def _rounded_distance(px: float, py: float, width: float, height: float, radius: float) -> float:
    """Signed distance from a point to a rounded rectangle at (0, 0) (negative inside)."""
    radius = min(radius, width / 2, height / 2)
    qx = abs(px - width / 2) - (width / 2 - radius)
    qy = abs(py - height / 2) - (height / 2 - radius)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - radius


def _coverage(distance: float) -> float:
    return min(1.0, max(0.0, 0.5 - distance))


def png_gray(width: int, height: int, alpha: Callable[[int, int], int]) -> bytes:
    return _png(
        width,
        height,
        0,
        [bytes(alpha(x, y) for x in range(width)) for y in range(height)],
    )


def png_rgba(
    width: int, height: int, pixel: Callable[[int, int], tuple[int, int, int, int]]
) -> bytes:
    rows = [b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height)]
    return _png(width, height, 6, rows)


def mask_png(width: int, height: int, radius_px: float) -> bytes:
    """Grayscale alpha of a rounded rectangle, anti-aliased; only the corner squares are computed."""
    radius = max(0.0, min(radius_px, width / 2, height / 2))
    corner = int(math.ceil(radius))
    full = b"\xff" * width
    rows = []
    for y in range(height):
        if corner == 0 or corner <= y < height - corner:
            rows.append(full)
            continue
        row = bytearray(full)
        cy = y + 0.5
        for x in list(range(min(corner, width))) + list(
            range(max(width - corner, corner), width)
        ):
            row[x] = round(
                255 * _coverage(_rounded_distance(x + 0.5, cy, width, height, radius))
            )
        rows.append(bytes(row))
    return _png(width, height, 0, rows)


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _frame_pad(width: int, height: int, shadow: bool) -> int:
    """Room around the box for the shadow (blur plus its downward drop)."""
    blur = max(8, round(min(width, height) * 0.06)) if shadow else 0
    return blur + blur // 3


def frame_png(
    width: int, height: int, radius_px: float, border_px: int, color: str, shadow: bool
) -> tuple[bytes, int]:
    """Border ring (inside the box) and soft shadow (outside, lower), overlaid over the source at
    (x - pad, y - pad); the box itself stays transparent."""
    pad = _frame_pad(width, height, shadow)
    blur = max(8, round(min(width, height) * 0.06)) if shadow else 0
    red, green, blue = _rgb(color)
    radius = max(0.0, min(radius_px, width / 2, height / 2))
    drop = blur / 3

    def pixel(x: int, y: int) -> tuple[int, int, int, int]:
        px, py = x - pad + 0.5, y - pad + 0.5
        distance = _rounded_distance(px, py, width, height, radius)
        if distance < 0:
            if border_px and distance > -border_px - 0.5:
                alpha = (
                    _coverage(-border_px - distance)
                    if distance < -border_px + 0.5
                    else 1.0
                )
                alpha = min(alpha, _coverage(distance))
                return red, green, blue, round(255 * alpha)
            return 0, 0, 0, 0
        edge = _coverage(distance)
        if border_px and edge > 0:
            return red, green, blue, round(255 * edge)
        if shadow:
            fall = _rounded_distance(px, py - drop, width, height, radius)
            strength = max(0.0, 1.0 - max(fall, 0.0) / blur) ** 2 * 0.45
            return 0, 0, 0, round(255 * strength)
        return 0, 0, 0, 0

    return png_rgba(width + 2 * pad, height + 2 * pad, pixel), pad


# ---------------------------------------------------------------- settings and geometry


def export_settings(project: dict, setup_export: dict, overrides: dict) -> dict:
    """Defaults < last settings used anywhere (setup) < this project's last export < this export's choices."""
    settings = dict(DEFAULT_EXPORT)
    settings["container"] = load_config().get("capture", {}).get("video_format", "mov")
    if settings["container"] not in ("mov", "mp4"):
        settings["container"] = "mov"
    for layer in (setup_export or {}, project.get("export") or {}):
        settings.update(
            {key: value for key, value in layer.items() if key in DEFAULT_EXPORT}
        )
    if project.get("mode") == "camera" and "height" not in (
        project.get("export") or {}
    ):
        settings["height"] = 1080
    chosen = {key: value for key, value in overrides.items() if value is not None}
    if (
        "canvas" in chosen
        and "height" not in chosen
        and chosen["canvas"] != settings["canvas"]
    ):
        settings["height"] = (
            1440
            if chosen["canvas"] == "16:9" and project.get("mode") == "screen"
            else 1080
        )
    settings.update(chosen)
    settings["delete_sources"] = bool(chosen.get("delete_sources", False))
    return validate_export(settings, "export")


def _even_up(value: float) -> int:
    return max(2, int(math.ceil(value / 2 - 1e-6)) * 2)


def placement_px(item: dict, width: int, height: int) -> tuple[int, int, int, int]:
    x, y, box_width, box_height = item["box"]
    return (
        round(x * width),
        round(y * height),
        _even(box_width * width),
        _even(box_height * height),
    )


def _fit(
    source: tuple[int, int], box: tuple[int, int], fit: str, focus: list[float]
) -> tuple[list[str], int, int, int, int]:
    """Filters that make the source fill (`cover`, cropped around focus) or fit (`contain`) the box;
    returns them with the result's size and its offset inside the box."""
    source_width, source_height = source
    box_width, box_height = box
    if fit == "cover":
        scale = max(box_width / source_width, box_height / source_height)
        width, height = (
            max(box_width, _even_up(source_width * scale)),
            max(box_height, _even_up(source_height * scale)),
        )
        crop_x = round((width - box_width) * focus[0])
        crop_y = round((height - box_height) * focus[1])
        return (
            [
                f"scale={width}:{height}",
                f"crop={box_width}:{box_height}:{crop_x}:{crop_y}",
            ],
            box_width,
            box_height,
            0,
            0,
        )
    scale = min(box_width / source_width, box_height / source_height)
    width, height = (
        min(box_width, _even(source_width * scale)),
        min(box_height, _even(source_height * scale)),
    )
    return (
        [f"scale={width}:{height}"],
        width,
        height,
        (box_width - width) // 2,
        (box_height - height) // 2,
    )


def _probe_media(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        streams = json.loads(result.stdout or "{}").get("streams", [])
    except json.JSONDecodeError:
        streams = []
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), {}
    )
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "audio": any(stream.get("codec_type") == "audio" for stream in streams),
    }


def _track_info(folder: Path, segment: dict, track: str) -> dict:
    info = (segment.get("info") or {}).get(track)
    if isinstance(info, dict) and info.get("width") is not None:
        return info
    info = _probe_media(folder / segment["files"][track])
    segment.setdefault("info", {})[track] = info
    return info


def _cached_png(cache: Path, name: str, data: Callable[[], bytes]) -> Path:
    path = cache / name
    if not path.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".png.", dir=cache)
        with os.fdopen(handle, "wb") as stream:
            stream.write(data())
        os.replace(temporary, path)
    return path


def _encoder(settings: dict, width: int, height: int) -> list[str]:
    fps = settings["fps"]
    codec = (
        ["-c:v", "hevc_videotoolbox", "-tag:v", "hvc1"]
        if settings["codec"] == "hevc"
        else ["-c:v", "h264_videotoolbox"]
    )
    return [
        *codec,
        "-b:v",
        str(video_bitrate(width, height, fps, settings["codec"], settings["quality"])),
        "-g",
        str(2 * fps),
        "-r",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
    ]


def interval_argv(
    folder: Path, project: dict, interval: dict, settings: dict, out: Path, cache: Path
) -> list[str]:
    """One ffmpeg run that renders one interval of the timeline with its scene's layout."""
    width, height = canvas_size(settings["canvas"], settings["height"])
    fps, length, start = settings["fps"], interval["length"], interval["start"]
    segment = project["segments"][interval["segment"]]
    background, placements = effective_placements(
        project, interval["scene"], settings["canvas"]
    )
    color = (
        background.get("color", "#000000")
        if background["kind"] == "color"
        else "#000000"
    )
    inputs = ["-f", "lavfi", "-i", f"color=c=0x{color[1:]}:s={width}x{height}:r={fps}"]
    graph: list[str] = []
    count = 1
    current = "[0:v]"

    def media_input(track: str) -> int:
        nonlocal count
        local = start - segment["starts"].get(track, 0.0)
        if local > 0:
            inputs.extend(["-ss", f"{local:.3f}"])
        elif local < 0:
            inputs.extend(["-itsoffset", f"{-local:.3f}"])
        inputs.extend(["-i", str(folder / segment["files"][track])])
        count += 1
        return count - 1

    def still_input(path: Path) -> int:
        nonlocal count
        inputs.extend(["-loop", "1", "-t", f"{length:.3f}", "-i", str(path)])
        count += 1
        return count - 1

    if background["kind"] == "blur" and "screen" in segment["files"]:
        index = media_input("screen")
        graph.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"boxblur=40:2,setsar=1[bg];{current}[bg]overlay=0:0:eof_action=pass[base]"
        )
        current = "[base]"
    sources = {source["id"]: source for source in project["sources"]}
    for number, (source_id, item) in enumerate(placements):
        source = sources[source_id]
        x, y, box_width, box_height = placement_px(item, width, height)
        filters = ["hflip"] if item["mirror"] else []
        if source["kind"] in ("screen", "camera"):
            info = _track_info(folder, segment, source["kind"])
            index = media_input(source["kind"])
            fitted, shown_width, shown_height, offset_x, offset_y = _fit(
                (info["width"] or box_width, info["height"] or box_height),
                (box_width, box_height),
                item["fit"],
                item["focus"],
            )
            filters += fitted
        else:
            index = still_input(folder / "assets" / source["asset"])
            ratio = "increase" if item["fit"] == "cover" else "decrease"
            filters.append(
                f"scale={box_width}:{box_height}:force_original_aspect_ratio={ratio}"
            )
            if item["fit"] == "cover":
                filters.append(f"crop={box_width}:{box_height}")
            shown_width, shown_height, offset_x, offset_y = box_width, box_height, 0, 0
        filters.append("setsar=1")
        radius = item["radius"] * min(shown_width, shown_height)
        label = f"[s{number}]"
        if radius >= 1:
            key = f"{shown_width}x{shown_height}-{radius:.2f}"
            mask = _cached_png(
                cache,
                f"mask-{key}.png",
                lambda: mask_png(shown_width, shown_height, radius),
            )
            mask_index = still_input(mask)
            graph.append(
                f"[{index}:v]{','.join(filters)},format=yuva420p[v{number}];"
                f"[{mask_index}:v]format=gray[m{number}];[v{number}][m{number}]alphamerge{label}"
            )
        else:
            graph.append(f"[{index}:v]{','.join(filters)}{label}")
        left, top = x + offset_x, y + offset_y
        graph.append(f"{current}{label}overlay={left}:{top}:eof_action=pass[o{number}]")
        current = f"[o{number}]"
        border = round(item["border"]["width"] * min(width, height) / 1080)
        if border or item["shadow"]:
            key = hashlib.sha1(
                f"{shown_width}x{shown_height}-{radius:.2f}-{border}-{item['border']['color']}-{item['shadow']}".encode()
            ).hexdigest()[:16]
            color = item["border"]["color"]
            path = _cached_png(
                cache,
                f"frame-{key}.png",
                lambda: frame_png(shown_width, shown_height, radius, border, color, item["shadow"])[0],
            )
            pad = _frame_pad(shown_width, shown_height, item["shadow"])
            frame_index = still_input(path)
            graph.append(
                f"{current}[{frame_index}:v]overlay={left - pad}:{top - pad}:eof_action=pass[f{number}]"
            )
            current = f"[f{number}]"
    graph.append(f"{current}format=yuv420p[vout]")
    return [
        *FFMPEG_BASE,
        *inputs,
        "-filter_complex",
        ";".join(graph),
        "-map",
        "[vout]",
        "-an",
        *_encoder(settings, width, height),
        "-t",
        f"{length:.3f}",
        "-progress",
        "pipe:1",
        "-nostats",
        str(out),
    ]


def audio_argv(
    folder: Path, project: dict, segment: int, settings: dict, out: Path
) -> list[str] | None:
    """System sound (from the screen file) and the microphone of one segment, each at its start offset,
    mixed to stereo 48 kHz WAV of exactly the segment's length; None when nothing is audible."""
    part = project["segments"][segment]
    duration = part["duration"]
    audio = project["audio"]
    chosen = []
    if (
        "screen" in part["files"]
        and audio["system"]["enabled"]
        and not audio["system"]["muted"]
    ):
        if _track_info(folder, part, "screen").get("audio"):
            chosen.append(("screen", audio["system"]["volume"]))
    if "mic" in part["files"] and not audio["mic"]["muted"]:
        chosen.append(("mic", audio["mic"]["volume"]))
    if not chosen:
        return None
    inputs: list[str] = []
    graph: list[str] = []
    labels = []
    for index, (track, volume) in enumerate(chosen):
        inputs.extend(["-i", str(folder / part["files"][track])])
        start = part["starts"].get(track, 0.0)
        chain = f"[{index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={volume:g}"
        if start > 0:
            chain += f",adelay={round(start * 1000)}:all=1"
        elif start < 0:
            chain += f",atrim=start={-start:.3f},asetpts=PTS-STARTPTS"
        graph.append(f"{chain}[a{index}]")
        labels.append(f"[a{index}]")
    if len(labels) > 1:
        graph.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[mix]"
        )
        last = "[mix]"
    else:
        last = labels[0]
    graph.append(f"{last}apad,atrim=0:{duration:.3f}[aout]")
    return [
        *FFMPEG_BASE,
        *inputs,
        "-filter_complex",
        ";".join(graph),
        "-map",
        "[aout]",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(out),
    ]


def _silence_argv(duration: float, out: Path) -> list[str]:
    return [
        *FFMPEG_BASE,
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-t",
        f"{duration:.3f}",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]


def _concat_argv(files: list[Path], listing: Path, out: Path) -> list[str]:
    listing.write_text(
        "".join("file '" + str(path).replace("'", "'\\''") + "'\n" for path in files),
        encoding="utf-8",
    )
    return [
        *FFMPEG_BASE,
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-c",
        "copy",
        str(out),
    ]


# ---------------------------------------------------------------- running


def export_status_file() -> Path:
    return storage_path("runtime", "export.json")


def read_export_status() -> dict:
    try:
        data = json.loads(export_status_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"phase": "idle"}
    except (OSError, ValueError):
        return {"phase": "idle"}


class _Status:
    """export.json for the desk, the TUI and `ul capture export --status`, written at most twice a second."""

    def __init__(self, project: Path) -> None:
        self.data = {
            "project": str(project),
            "phase": "queued",
            "percent": 0,
            "eta": None,
            "output": None,
            "error": None,
            "started": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.began = time.monotonic()
        self.written = 0.0
        self.write(force=True)

    def write(self, *, force: bool = False, **changes: object) -> None:
        self.data.update(changes)
        now = time.monotonic()
        if force or now - self.written >= 0.5:
            self.written = now
            try:
                write_json_atomic(export_status_file(), self.data)
            except OSError:
                pass

    def progress(self, fraction: float) -> None:
        fraction = min(max(fraction, 0.0), 1.0)
        spent = time.monotonic() - self.began
        eta = round(spent / fraction - spent) if fraction > 0.02 else None
        self.write(percent=min(99, int(fraction * 100)), eta=eta)


def _run_ffmpeg(
    argv: list[str],
    log: Path,
    what: str,
    on_time: Callable[[float], None] | None = None,
) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as stream:
        stream.write(("$ " + " ".join(argv) + "\n").encode())
        stream.flush()
        with subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stream,
            text=True,
        ) as process:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    if on_time and line.startswith("out_time_us="):
                        try:
                            on_time(int(line.split("=", 1)[1]) / 1e6)
                        except ValueError:
                            pass
            except BaseException:
                process.kill()  # Ctrl-C or a failing callback: never leave an encoder running
                raise
            code = process.wait()
    if code != 0:
        tail = [
            line
            for line in log.read_text(errors="replace").splitlines()
            if line and not line.startswith("$ ")
        ][-2:]
        raise ExportError(f"{what} failed: {' '.join(tail) or f'exit {code}'}")


def free_name(path: Path) -> Path:
    """Never overwrite: `name.mov` → `name 2.mov` → `name 3.mov`."""
    if not path.exists():
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.stem} {number}{path.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def _publish(temporary: Path, target: Path) -> Path:
    """Move the finished file into place without ever replacing one (a hard link fails if the name exists)."""
    while True:
        target = free_name(target)
        try:
            os.link(temporary, target)
        except FileExistsError:
            continue
        except OSError:
            with target.open("xb") as out, temporary.open("rb") as source:
                shutil.copyfileobj(source, out)
        temporary.unlink(missing_ok=True)
        return target


def _trash(folder: Path) -> Path:
    trash = Path.home() / ".Trash"
    trash.mkdir(exist_ok=True)
    target = free_name(trash / folder.name)
    shutil.move(str(folder), target)
    return target


def _canvas_label(canvas: str) -> str:
    return canvas.replace(":", "x")


def export_project(
    folder: Path,
    settings: dict,
    output: Path | None = None,
    progress: Callable[[float], None] | None = None,
) -> Path:
    """Render the project; one export at a time (`export.lock`), a second one waits as `queued`."""
    status = _Status(folder)
    lock = storage_path("runtime", f"{EXPORT_LOCK}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            status.write(force=True, phase="running")
            if hasattr(os, "nice"):
                try:
                    os.nice(
                        10
                    )  # never slow down a recording that runs at the same time
                except OSError:
                    pass
            result = _export(folder, settings, output, status, progress)
        except (ExportError, ProjectError, OSError) as error:
            status.write(force=True, phase="failed", error=str(error))
            raise ExportError(str(error)) from error
        except BaseException as error:
            status.write(
                force=True, phase="failed", error=f"stopped ({type(error).__name__})"
            )
            raise
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    status.write(force=True, phase="done", percent=100, eta=0, output=str(result))
    return result


def _export(
    folder: Path,
    settings: dict,
    output: Path | None,
    status: _Status,
    progress: Callable[[float], None] | None,
) -> Path:
    if shutil.which("ffmpeg") is None:
        raise ExportError("ffmpeg is required to export (brew install ffmpeg)")
    project = read_project(folder)
    settings = validate_export(dict(settings), "export")
    if not project["segments"]:
        raise ExportError("the project has no recorded media")
    audio_only = project["mode"] == "audio" or not any(
        track in segment["files"]
        for segment in project["segments"]
        for track in ("screen", "camera")
    )
    if audio_only:
        extension = project.get("audio_format") or load_config().get("capture", {}).get(
            "audio_format", "m4a"
        )
        if extension not in AUDIO_CODECS:
            extension = "m4a"
        name = f"{project['name']}.{extension}"
    else:
        extension = settings["container"]
        name = f"{project['name']} {_canvas_label(settings['canvas'])}.{extension}"
    target = (
        output if output is not None else storage_path("captures", "recordings") / name
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    work = folder / "cache" / "render"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    log = folder / "logs" / "export.log"
    temporary = target.parent / f".{target.stem}.part-{os.getpid()}.{extension}"

    def report(fraction: float) -> None:
        status.progress(fraction)
        if progress:
            progress(fraction)

    try:
        # Sound: one WAV per segment (silence where nothing is audible), joined.
        audio_parts = []
        for index, segment in enumerate(project["segments"]):
            if segment["duration"] < 1 / settings["fps"]:
                continue
            wav = work / f"audio-{index:03d}.wav"
            argv = audio_argv(folder, project, index, settings, wav)
            _run_ffmpeg(
                argv or _silence_argv(segment["duration"], wav), log, "mixing the sound"
            )
            audio_parts.append(wav)
        audible = any(
            audio_argv(folder, project, index, settings, Path(os.devnull))
            for index in range(len(project["segments"]))
        )
        sound = work / "audio.wav"
        if audible:
            _run_ffmpeg(
                _concat_argv(audio_parts, work / "audio.txt", sound),
                log,
                "joining the sound",
            )
        report(0.05)
        loud = (
            ["-af", "loudnorm=I=-14:TP=-1:LRA=11,aresample=48000"]
            if settings["normalize"]
            else []
        )
        if audio_only:
            if not audible:
                raise ExportError("the project has no sound to export")
            _run_ffmpeg(
                [
                    *FFMPEG_BASE,
                    "-i",
                    str(sound),
                    *loud,
                    *AUDIO_CODECS[extension],
                    str(temporary),
                ],
                log,
                "saving the sound",
            )
        else:
            video = work / "video.mp4"
            if settings["canvas"] == "source":
                track = (
                    "screen"
                    if any(
                        "screen" in segment["files"] for segment in project["segments"]
                    )
                    else "camera"
                )
                files = [
                    folder / segment["files"][track]
                    for segment in project["segments"]
                    if track in segment["files"]
                ]
                _run_ffmpeg(
                    _concat_argv(files, work / "video.txt", video),
                    log,
                    "joining the video",
                )
            else:
                intervals = timeline_intervals(project, settings["fps"])
                total = sum(interval["length"] for interval in intervals) or 1.0
                done = 0.0
                chunks = []
                for number, interval in enumerate(intervals):
                    chunk = work / f"chunk-{number:04d}.mp4"
                    _run_ffmpeg(
                        interval_argv(
                            folder, project, interval, settings, chunk, folder / "cache"
                        ),
                        log,
                        "rendering the video",
                        lambda seconds, done=done: report(
                            0.05
                            + 0.85 * (done + min(seconds, interval["length"])) / total
                        ),
                    )
                    done += interval["length"]
                    chunks.append(chunk)
                if not chunks:
                    raise ExportError("the recording is shorter than one frame")
                _run_ffmpeg(
                    _concat_argv(chunks, work / "video.txt", video),
                    log,
                    "joining the video",
                )
            report(0.92)
            if audible:
                mux = [
                    *FFMPEG_BASE,
                    "-i",
                    str(video),
                    "-i",
                    str(sound),
                    "-map",
                    "0:v",
                    "-map",
                    "1:a",
                    "-c:v",
                    "copy",
                    *loud,
                    "-c:a",
                    "aac",
                    "-b:a",
                    "256k",
                    "-movflags",
                    "+faststart",
                    "-shortest",
                    str(temporary),
                ]
            else:
                mux = [
                    *FFMPEG_BASE,
                    "-i",
                    str(video),
                    "-map",
                    "0:v",
                    "-c:v",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(temporary),
                ]
            _run_ffmpeg(mux, log, "saving the video")
        result = _publish(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)
    report(1.0)
    remembered = {
        key: value for key, value in settings.items() if key != "delete_sources"
    }
    project = read_project(folder)
    project["export"] = dict(remembered, delete_sources=False)
    project["exports"].append(
        {
            **remembered,
            "path": str(result),
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    write_project(folder, project)
    try:
        setup, _ = load_setup()
        setup["export"] = dict(remembered, delete_sources=False)
        save_setup(setup)
    except (ProjectError, OSError):
        pass
    if settings["delete_sources"]:
        _trash(folder)
    return result

