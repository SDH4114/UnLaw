"""Studio setup and recording projects: pure data (no external tools).

The setup (`storage.root/studio/setup.json`) is what the Studio records next:
sources, devices, scenes, one layout per format and export choices. Every
recording copies it into a project folder whose `project.json` says how to put
the separate tracks back together.
"""

from __future__ import annotations

import copy
import fcntl
import json
import math
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import load_config, storage_path

CANVASES = ("16:9", "9:16", "1:1", "4:5", "source")
RATIOS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
HEIGHTS = (1080, 1440, 2160)
FPS = (30, 60)
CODECS = ("h264", "hevc")
QUALITIES = ("high", "max")
CONTAINERS = ("mov", "mp4")
COUNTDOWNS = (0, 3, 5, 10)
CAMERA_QUALITY = {
    "max": (1080, 12_000_000),
    "high": (1080, 6_000_000),
    "light": (720, 3_000_000),
}
MIC_FORMATS = {"flac": ".flac", "wav": ".wav", "m4a": ".m4a"}
# shape: (box width, box height in pixels, corner radius as a share of the short side)
SHAPES = {
    "circle": (1, 1, 0.5),
    "square": (1, 1, 0.0),
    "rounded": (1, 1, 0.18),
    "wide": (16, 9, 0.0),
    "tall": (9, 16, 0.0),
}
ANCHORS = ("top-left", "top-right", "bottom-left", "bottom-right")
SCENES = (
    ("screen-camera", "Screen + camera"),
    ("screen", "Screen"),
    ("camera", "Camera"),
    ("side", "Side by side"),
)
SOURCE_KINDS = ("screen", "camera", "image", "text")
MAX_SCENES = 9
MAX_SOURCES = 12
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_MODE = re.compile(r"[1-9][0-9]{1,4}x[1-9][0-9]{1,4}@[0-9]{1,3}(\.[0-9]{1,6})?")
_AREA = re.compile(r"[0-9]{1,5},[0-9]{1,5},[1-9][0-9]{0,4},[1-9][0-9]{0,4}")
BLACK = {"kind": "color", "color": "#000000"}


class ProjectError(ValueError):
    """A setup or project file that is not what the Studio wrote."""


# ---------------------------------------------------------------- placements


def placement(
    box: list[float],
    *,
    fit: str = "cover",
    mirror: bool = False,
    anchor: str | None = None,
) -> dict:
    return {
        "visible": True,
        "box": list(box),
        "fit": fit,
        "focus": [0.5, 0.5],
        "radius": 0.0,
        "border": {"width": 0, "color": "#ffc933"},
        "shadow": False,
        "mirror": mirror,
        "anchor": anchor,
    }


def _scene(background: dict, **placements: dict) -> dict:
    return {"background": dict(background), "placements": placements}


def default_layouts() -> dict:
    """One layout per format and scene (Haos: 16:9 camera wide, flush bottom-left; vertical camera on top at 40 %)."""
    layouts: dict = {}
    for canvas in RATIOS:
        if canvas == "16:9":
            layouts[canvas] = {
                "screen-camera": _scene(
                    BLACK,
                    screen=placement([0, 0, 1, 1], fit="contain"),
                    camera=placement(
                        [0, 0.76, 0.24, 0.24], mirror=True, anchor="bottom-left"
                    ),
                ),
                "screen": _scene(BLACK, screen=placement([0, 0, 1, 1], fit="contain")),
                "camera": _scene(BLACK, camera=placement([0, 0, 1, 1], mirror=True)),
                "side": _scene(
                    BLACK,
                    screen=placement([0, 0, 2 / 3, 1], fit="contain"),
                    camera=placement([2 / 3, 0, 1 / 3, 1], mirror=True),
                ),
            }
        else:
            layouts[canvas] = {
                "screen-camera": _scene(
                    BLACK,
                    camera=placement([0, 0, 1, 0.4], mirror=True),
                    screen=placement([0, 0.4, 1, 0.6]),
                ),
                "screen": _scene(
                    {"kind": "blur"}, screen=placement([0, 0, 1, 1], fit="contain")
                ),
                "camera": _scene(BLACK, camera=placement([0, 0, 1, 1], mirror=True)),
                "side": _scene(
                    BLACK,
                    camera=placement([0, 0, 1, 0.5], mirror=True),
                    screen=placement([0, 0.5, 1, 0.5]),
                ),
            }
    return layouts


def pin(item: dict, anchor: str | None) -> dict:
    """The box moved flush into a corner (None only clears the pin)."""
    result = copy.deepcopy(item)
    result["anchor"] = anchor
    if anchor is None:
        return result
    x, y, width, height = result["box"]
    x = 0 if anchor.endswith("left") else 1 - width
    y = 0 if anchor.startswith("top") else 1 - height
    result["box"] = [round(x, 9), round(y, 9), width, height]
    return result


def apply_shape(item: dict, shape: str, canvas: str) -> dict:
    """Change the box to a shape preset; the width and a pinned corner stay."""
    if shape not in SHAPES:
        raise ProjectError(f"unknown shape: {shape}")
    if canvas not in RATIOS:
        raise ProjectError(f"shapes need a format with a ratio, not {canvas}")
    shape_width, shape_height, radius = SHAPES[shape]
    canvas_width, canvas_height = RATIOS[canvas]
    result = copy.deepcopy(item)
    x, y, width, _ = result["box"]
    height = width * (canvas_width / canvas_height) * (shape_height / shape_width)
    if height > 1:
        width, height = width / height, 1.0
    result["box"] = [x, y, width, height]
    result["radius"] = radius
    if result.get("anchor"):
        return pin(result, result["anchor"])
    result["box"] = [
        min(max(x, 0.0), 1 - width),
        min(max(y, 0.0), 1 - height),
        width,
        height,
    ]
    return result


# ---------------------------------------------------------------- sizes


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


def canvas_size(canvas: str, height: int) -> tuple[int, int]:
    """Pixel size of a format; `height` is the short side (1080, 1440, 2160)."""
    if canvas not in RATIOS:
        raise ProjectError(f"no fixed size for the format {canvas}")
    ratio_width, ratio_height = RATIOS[canvas]
    if ratio_width >= ratio_height:
        return _even(height * ratio_width / ratio_height), height
    return height, _even(height * ratio_height / ratio_width)


def video_bitrate(width: int, height: int, fps: int, codec: str, quality: str) -> int:
    """About 0.11 bit per pixel per frame for H.264; `max` x1.5, HEVC x0.65."""
    rate = width * height * fps * 0.11
    if quality == "max":
        rate *= 1.5
    if codec == "hevc":
        rate *= 0.65
    return round(rate)


# ---------------------------------------------------------------- setup


def default_setup(capture: dict) -> dict:
    """A first setup from the `[capture]` config keys (devices, sounds, clicks, container)."""
    container = capture.get("video_format", "mov")
    return {
        "version": 1,
        "sources": [
            {
                "id": "screen",
                "kind": "screen",
                "enabled": True,
                "display": 1,
                "area": None,
                "clicks": bool(capture.get("show_clicks", True)),
            },
            {
                "id": "camera",
                "kind": "camera",
                "enabled": False,
                "device": str(capture.get("camera_device", "default")) or "default",
                "mode": "auto",
                "quality": "high",
            },
        ],
        "audio": {
            "mic": {
                "enabled": bool(capture.get("screen_audio", True)),
                "device": str(capture.get("audio_device", "default")) or "default",
                "format": "flac",
                "volume": 1.0,
                "muted": False,
            },
            "system": {
                "enabled": bool(capture.get("system_audio", True)),
                "volume": 1.0,
                "muted": False,
            },
        },
        "scenes": [{"id": scene, "name": name} for scene, name in SCENES],
        "scene": "screen-camera",
        "canvas": "16:9",
        "layouts": default_layouts(),
        "countdown": 3,
        "menubar": True,
        "export": {
            "canvas": "16:9",
            "height": 1440,
            "fps": 60,
            "codec": "h264",
            "quality": "high",
            "container": container if container in CONTAINERS else "mov",
            "normalize": True,
            "delete_sources": False,
        },
    }


def _fail(where: str, message: str) -> None:
    raise ProjectError(f"{where}: {message}")


def _dict(value: object, where: str) -> dict:
    if not isinstance(value, dict):
        _fail(where, "must be an object")
    return value  # type: ignore[return-value]


def _bool(value: object, where: str) -> bool:
    if type(value) is not bool:
        _fail(where, "must be true or false")
    return value  # type: ignore[return-value]


def _numeric(value: object, where: str, low: float, high: float) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not low <= value <= high
    ):  # type: ignore[arg-type]
        _fail(where, f"must be a number from {low} to {high}")
    return float(value)  # type: ignore[arg-type]


def _choice(value: object, where: str, choices: tuple) -> object:
    if type(value) is bool or value not in choices:
        _fail(where, "must be one of " + ", ".join(str(choice) for choice in choices))
    return value


def _text(value: object, where: str, limit: int = 200, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (not value.strip() and not empty)
    ):
        _fail(where, f"must be text of at most {limit} characters")
    if any(ord(char) < 32 for char in value):  # type: ignore[union-attr]
        _fail(where, "must not contain control characters")
    return value  # type: ignore[return-value]


def _ident(value: object, where: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail(where, "must be lowercase letters, digits and dashes (at most 32)")
    return value  # type: ignore[return-value]


def _color(value: object, where: str) -> str:
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        _fail(where, "must be a colour like #ffc933")
    return value  # type: ignore[return-value]


def asset_name(value: object, where: str) -> str:
    name = _text(value, where, 120)
    if "/" in name or "\\" in name or name.startswith("."):
        _fail(where, "must be a file name inside the assets folder")
    return name


def validate_placement(value: object, where: str) -> dict:
    item = _dict(value, where)
    _bool(item.get("visible"), f"{where}.visible")
    box = item.get("box")
    if not isinstance(box, list) or len(box) != 4:
        _fail(f"{where}.box", "must be [x, y, width, height]")
    _numeric(box[0], f"{where}.box", -1, 1)
    _numeric(box[1], f"{where}.box", -1, 1)
    for size in box[2:]:
        if _numeric(size, f"{where}.box", 0, 2) <= 0:
            _fail(f"{where}.box", "width and height must be above 0")
    _choice(item.get("fit"), f"{where}.fit", ("cover", "contain"))
    focus = item.get("focus")
    if not isinstance(focus, list) or len(focus) != 2:
        _fail(f"{where}.focus", "must be [x, y]")
    for value_ in focus:
        _numeric(value_, f"{where}.focus", 0, 1)
    _numeric(item.get("radius"), f"{where}.radius", 0, 0.5)
    border = _dict(item.get("border"), f"{where}.border")
    if type(border.get("width")) is not int or not 0 <= border["width"] <= 40:
        _fail(f"{where}.border.width", "must be a whole number from 0 to 40")
    _color(border.get("color"), f"{where}.border.color")
    _bool(item.get("shadow"), f"{where}.shadow")
    _bool(item.get("mirror"), f"{where}.mirror")
    if item.get("anchor") is not None:
        _choice(item.get("anchor"), f"{where}.anchor", ANCHORS)
    return item


def validate_background(value: object, where: str) -> dict:
    background = _dict(value, where)
    kind = _choice(background.get("kind"), f"{where}.kind", ("color", "blur"))
    if kind == "color":
        _color(background.get("color"), f"{where}.color")
    return background


def validate_layouts(
    value: object, scene_ids: set[str], where: str = "layouts"
) -> dict:
    layouts = _dict(value, where)
    for canvas, scenes in layouts.items():
        _choice(canvas, where, tuple(RATIOS))
        for scene, layout in _dict(scenes, f"{where}.{canvas}").items():
            if scene not in scene_ids:
                _fail(f"{where}.{canvas}", f"unknown scene {scene!r}")
            layout = _dict(layout, f"{where}.{canvas}.{scene}")
            validate_background(
                layout.get("background"), f"{where}.{canvas}.{scene}.background"
            )
            for source, item in _dict(
                layout.get("placements"), f"{where}.{canvas}.{scene}.placements"
            ).items():
                _ident(source, f"{where}.{canvas}.{scene}.placements")
                validate_placement(
                    item, f"{where}.{canvas}.{scene}.placements.{source}"
                )
    return layouts


def validate_sources(value: object, where: str = "sources") -> list:
    if not isinstance(value, list) or len(value) > MAX_SOURCES:
        _fail(where, f"must be a list of at most {MAX_SOURCES} sources")
    seen: set[str] = set()
    kinds: set[str] = set()
    for index, item in enumerate(value):  # type: ignore[arg-type]
        here = f"{where}[{index}]"
        source = _dict(item, here)
        ident = _ident(source.get("id"), f"{here}.id")
        if ident in seen:
            _fail(f"{here}.id", f"{ident!r} is used twice")
        seen.add(ident)
        kind = _choice(source.get("kind"), f"{here}.kind", SOURCE_KINDS)
        if kind in ("screen", "camera"):
            if kind in kinds:
                _fail(here, f"only one {kind} source")
            kinds.add(kind)  # type: ignore[arg-type]
        _bool(source.get("enabled"), f"{here}.enabled")
        if kind == "screen":
            if (
                type(source.get("display")) is not int
                or not 1 <= source["display"] <= 16
            ):
                _fail(f"{here}.display", "must be a display number from 1 to 16")
            area = source.get("area")
            if area is not None and (
                not isinstance(area, str) or not _AREA.fullmatch(area)
            ):
                _fail(f"{here}.area", "must be X,Y,WIDTH,HEIGHT in points or null")
            _bool(source.get("clicks"), f"{here}.clicks")
        elif kind == "camera":
            device = _text(source.get("device"), f"{here}.device")
            if device.startswith("-"):
                _fail(f"{here}.device", "must be a device name")
            mode = source.get("mode")
            if mode != "auto" and (
                not isinstance(mode, str) or not _MODE.fullmatch(mode)
            ):
                _fail(f"{here}.mode", "must be auto or WIDTHxHEIGHT@FPS")
            _choice(source.get("quality"), f"{here}.quality", tuple(CAMERA_QUALITY))
        else:
            asset_name(source.get("asset"), f"{here}.asset")
            if kind == "text":
                _text(source.get("text"), f"{here}.text", 500)
                _text(source.get("font"), f"{here}.font", 100)
                if (
                    type(source.get("size")) is not int
                    or not 8 <= source["size"] <= 400
                ):
                    _fail(f"{here}.size", "must be a whole number from 8 to 400")
                _color(source.get("color"), f"{here}.color")
                background = source.get("background")
                if background is not None:
                    _color(background, f"{here}.background")
    return value  # type: ignore[return-value]


def validate_audio(value: object, where: str = "audio") -> dict:
    audio = _dict(value, where)
    mic = _dict(audio.get("mic"), f"{where}.mic")
    _bool(mic.get("enabled"), f"{where}.mic.enabled")
    device = _text(mic.get("device"), f"{where}.mic.device")
    if device.startswith("-"):
        _fail(f"{where}.mic.device", "must be a device name")
    _choice(mic.get("format"), f"{where}.mic.format", tuple(MIC_FORMATS))
    system = _dict(audio.get("system"), f"{where}.system")
    _bool(system.get("enabled"), f"{where}.system.enabled")
    for name, part in (("mic", mic), ("system", system)):
        _numeric(part.get("volume"), f"{where}.{name}.volume", 0, 2)
        _bool(part.get("muted"), f"{where}.{name}.muted")
    return audio


def validate_scenes(value: object, where: str = "scenes") -> set[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SCENES:
        _fail(where, f"must be a list of 1 to {MAX_SCENES} scenes")
    ids: set[str] = set()
    for index, item in enumerate(value):  # type: ignore[arg-type]
        scene = _dict(item, f"{where}[{index}]")
        ident = _ident(scene.get("id"), f"{where}[{index}].id")
        if ident in ids:
            _fail(f"{where}[{index}].id", f"{ident!r} is used twice")
        ids.add(ident)
        _text(scene.get("name"), f"{where}[{index}].name", 40)
    return ids


def validate_export(value: object, where: str = "export") -> dict:
    settings = _dict(value, where)
    _choice(settings.get("canvas"), f"{where}.canvas", CANVASES)
    _choice(settings.get("height"), f"{where}.height", HEIGHTS)
    _choice(settings.get("fps"), f"{where}.fps", FPS)
    _choice(settings.get("codec"), f"{where}.codec", CODECS)
    _choice(settings.get("quality"), f"{where}.quality", QUALITIES)
    _choice(settings.get("container"), f"{where}.container", CONTAINERS)
    _bool(settings.get("normalize"), f"{where}.normalize")
    _bool(settings.get("delete_sources"), f"{where}.delete_sources")
    return settings


def validate_setup(data: object) -> dict:
    setup = _dict(data, "setup")
    if setup.get("version") != 1:
        _fail("setup.version", "must be 1")
    validate_sources(setup.get("sources"))
    validate_audio(setup.get("audio"))
    scene_ids = validate_scenes(setup.get("scenes"))
    if setup.get("scene") not in scene_ids:
        _fail("setup.scene", "must be one of the scenes")
    _choice(setup.get("canvas"), "setup.canvas", CANVASES)
    validate_layouts(setup.get("layouts"), scene_ids)
    _choice(setup.get("countdown"), "setup.countdown", COUNTDOWNS)
    _bool(setup.get("menubar"), "setup.menubar")
    validate_export(setup.get("export"))
    return setup


def setup_path() -> Path:
    return storage_path("studio", "setup.json")


@contextmanager
def _file_lock(name: str) -> Iterator[None]:
    lock = storage_path("studio", f"{name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def load_setup() -> tuple[dict, list[str]]:
    """The saved setup, or a default one; a damaged file is moved aside, never overwritten."""
    path = setup_path()
    with _file_lock("setup"):
        if not path.is_file():
            return default_setup(dict(load_config().get("capture", {}))), []
        try:
            return validate_setup(json.loads(path.read_text(encoding="utf-8"))), []
        except (OSError, ValueError) as error:
            aside = path.with_name(f"setup.json.damaged-{_stamp()}")
            number = 2
            while aside.exists():
                aside = path.with_name(f"setup.json.damaged-{_stamp()}-{number}")
                number += 1
            os.replace(path, aside)
            warning = f"the studio setup was damaged ({error}); it was moved to {aside} and defaults are used"
            return default_setup(dict(load_config().get("capture", {}))), [warning]


def save_setup(data: dict) -> dict:
    setup = validate_setup(data)
    with _file_lock("setup"):
        write_json_atomic(setup_path(), setup)
    return setup


# ---------------------------------------------------------------- projects

PROJECT_FORMAT = "unlaw-studio-project"
PROJECT_STATES = ("recording", "saving", "ready", "incomplete")
TRACKS = ("screen", "camera", "mic")


def projects_dir() -> Path:
    return storage_path("captures", "projects")


def assets_dir() -> Path:
    return storage_path("studio", "assets")


def inside(folder: Path, relative: object, where: str) -> Path:
    """A path written in a project, refused unless it stays inside the folder (no `..`, no symlink)."""
    if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")):
        _fail(where, "must be a path relative to the project folder")
    parts = Path(relative).parts  # type: ignore[arg-type]
    if ".." in parts or any(part.startswith("~") for part in parts[:1]):
        _fail(where, "must stay inside the project folder")
    path = folder / relative  # type: ignore[operator]
    if path.is_symlink():
        _fail(where, "must not be a symbolic link")
    root = folder.resolve()
    if not path.resolve().is_relative_to(root):
        _fail(where, "must stay inside the project folder")
    return path


def _validate_events(value: object, scene_ids: set[str], where: str = "events") -> list:
    if not isinstance(value, list):
        _fail(where, "must be a list")
    for index, item in enumerate(value):  # type: ignore[arg-type]
        event = _dict(item, f"{where}[{index}]")
        _numeric(event.get("t"), f"{where}[{index}].t", 0, 1e7)
        if "scene" in event:
            if event["scene"] not in scene_ids:
                _fail(f"{where}[{index}].scene", "must be one of the scenes")
        else:
            _text(event.get("mark"), f"{where}[{index}].mark", 200, empty=True)
    return value  # type: ignore[return-value]


def validate_project(data: object, folder: Path) -> dict:
    project = _dict(data, "project")
    if project.get("format") != PROJECT_FORMAT or project.get("version") != 1:
        _fail("project", f"is not an {PROJECT_FORMAT} version 1 file")
    _text(project.get("name"), "project.name", 200)
    name = project["name"]
    if "/" in name or "\\" in name or name.startswith("."):
        _fail("project.name", "must be a plain file name (it names the export)")
    _choice(project.get("mode"), "project.mode", ("screen", "camera", "audio"))
    _choice(project.get("state"), "project.state", PROJECT_STATES)
    problems = project.get("problems")
    if not isinstance(problems, list) or not all(isinstance(item, str) for item in problems):
        _fail("project.problems", "must be a list of messages")
    _numeric(project.get("duration"), "project.duration", 0, 1e7)
    validate_sources(project.get("sources"), "project.sources")
    validate_audio(project.get("audio"), "project.audio")
    scene_ids = validate_scenes(project.get("scenes"), "project.scenes")
    validate_layouts(project.get("layouts"), scene_ids, "project.layouts")
    _validate_events(project.get("events"), scene_ids, "project.events")
    segments = project.get("segments")
    if not isinstance(segments, list):
        _fail("project.segments", "must be a list")
    for index, item in enumerate(segments):  # type: ignore[arg-type]
        here = f"project.segments[{index}]"
        segment = _dict(item, here)
        _numeric(segment.get("duration"), f"{here}.duration", 0, 1e7)
        for track, relative in _dict(segment.get("files"), f"{here}.files").items():
            _choice(track, f"{here}.files", TRACKS)
            inside(folder, relative, f"{here}.files.{track}")
        for track, start in _dict(segment.get("starts"), f"{here}.starts").items():
            _choice(track, f"{here}.starts", TRACKS)
            _numeric(start, f"{here}.starts.{track}", -1e5, 1e5)
        for track, info in _dict(segment.get("info", {}), f"{here}.info").items():
            _choice(track, f"{here}.info", TRACKS)
            info = _dict(info, f"{here}.info.{track}")
            for key in ("width", "height"):
                value = info.get(key)
                if value is not None and (type(value) is not int or not 0 <= value <= 20000):
                    _fail(f"{here}.info.{track}.{key}", "must be a whole number of pixels")
            if type(info.get("audio", False)) is not bool:
                _fail(f"{here}.info.{track}.audio", "must be true or false")
    validate_export(project.get("export"), "project.export")
    if "edit" in project:
        validate_edit(project["edit"], folder)
    exports = project.get("exports")
    if not isinstance(exports, list) or not all(isinstance(item, dict) for item in exports):
        _fail("project.exports", "must be a list")
    return project


def read_project(folder: Path) -> dict:
    path = folder / "project.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ProjectError(f"{folder} is not a Studio project (no project.json)") from error
    except (OSError, ValueError) as error:
        raise ProjectError(f"{path}: {error}") from error
    return validate_project(data, folder)


def write_project(folder: Path, data: dict) -> None:
    validate_project(data, folder)
    write_json_atomic(folder / "project.json", data)


def create_project(kind: str, setup: dict, recorded: dict) -> Path:
    """A new project folder (never reused) holding a copy of the setup; `recorded` adds device facts."""
    root = projects_dir()
    root.mkdir(parents=True, exist_ok=True)
    base = f"{kind}-{_stamp()}"
    folder, number = root / base, 2
    while True:
        try:
            folder.mkdir()
            break
        except FileExistsError:
            folder, number = root / f"{base} {number}", number + 1
    for sub in ("media", "assets", "logs", "cache"):
        (folder / sub).mkdir()
    sources = copy.deepcopy(setup["sources"])
    for source in sources:
        source.update(recorded.get(source["id"], {}))
        if source["kind"] in ("image", "text") and source["enabled"]:
            asset = assets_dir() / source["asset"]
            if asset.is_file() and not asset.is_symlink():
                (folder / "assets" / source["asset"]).write_bytes(asset.read_bytes())
    audio = copy.deepcopy(setup["audio"])
    audio["mic"].update(recorded.get("mic", {}))
    mode = "audio" if kind == "audio" else "camera" if kind == "camera" else "screen"
    export = dict(setup["export"], canvas=setup["canvas"])
    project = {
        "format": PROJECT_FORMAT,
        "version": 1,
        "name": folder.name,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "state": "recording",
        "problems": [],
        "duration": 0.0,
        "sources": sources,
        "audio": audio,
        "segments": [],
        "scenes": copy.deepcopy(setup["scenes"]),
        "layouts": copy.deepcopy(setup["layouts"]),
        "events": [{"t": 0.0, "scene": setup["scene"]}],
        "export": export,
        "exports": [],
    }
    write_project(folder, project)
    return folder


def add_event(folder: Path, event: dict) -> dict:
    with _file_lock("project"):
        project = read_project(folder)
        project["events"].append(event)
        write_project(folder, project)
    return project


def segment_starts(durations: dict[str, float], reference: str) -> dict[str, float]:
    """Where each track starts on the reference track's clock: all recorders stop together, so their ends line up."""
    end = durations[reference]
    return {track: round(end - length, 3) + 0.0 for track, length in durations.items()}


def timeline_intervals(project: dict, fps: int) -> list[dict]:
    """The recording cut at pauses and scene switches, on frame boundaries; pieces shorter than a frame go."""
    frame = 1 / fps

    def snap(value: float) -> float:
        return round(value * fps) / fps

    # Sorted by time (stable): two switches written close together may be stored out of order.
    changes = sorted(((snap(event["t"]), event["scene"]) for event in project["events"] if "scene" in event), key=lambda change: change[0])

    def scene_at(moment: float) -> str:
        active = changes[0][1] if changes else "screen"
        for at, scene in changes:
            if at <= moment + 1e-9:
                active = scene
        return active

    intervals: list[dict] = []
    elapsed = 0.0
    for index, segment in enumerate(project["segments"]):
        begin, finish = snap(elapsed), snap(elapsed + segment["duration"])
        elapsed += segment["duration"]
        if segment["duration"] < frame:
            continue  # the export drops such a part from the sound too; its time still counts for scene events
        cuts = sorted({begin, finish, *(at for at, _ in changes if begin < at < finish)})
        for start, end in zip(cuts, cuts[1:]):
            if end - start < frame - 1e-9:
                continue
            scene = scene_at(start)
            last = intervals[-1] if intervals else None
            if last and last["segment"] == index and last["scene"] == scene and abs(last["start"] + last["length"] - (start - begin)) < 1e-6:
                last["length"] = round(last["length"] + end - start, 6)
                continue
            intervals.append({"segment": index, "start": round(start - begin, 6) + 0.0, "length": round(end - start, 6), "scene": scene})
    return intervals


def recorded_tracks(project: dict) -> set[str]:
    return {track for segment in project["segments"] for track in segment["files"]}


def effective_placements(
    project: dict, scene: str, canvas: str, tracks: set[str] | None = None
) -> tuple[dict, list[tuple[str, dict]]]:
    """Background and visible placements in z order; a source that was not recorded is skipped, and a scene
    left with only the screen uses the `screen` scene's layout. `tracks` = the tracks of one segment (a
    recorder that hung or died leaves a later part without its track); default: any segment's."""
    if tracks is None:
        tracks = recorded_tracks(project)
    available = {
        source["id"]
        for source in project["sources"]
        if source["enabled"] and (source["kind"] in ("image", "text") or source["kind"] in tracks)
    }
    layouts = project["layouts"].get(canvas, {})

    def pick(name: str) -> tuple[dict, list[tuple[str, dict]], bool]:
        layout = layouts.get(name)
        if layout is None:
            return dict(BLACK), [], False
        chosen, dropped = [], False
        for source in project["sources"]:
            item = layout["placements"].get(source["id"])
            if item is None or not item["visible"]:
                continue
            if source["id"] in available:
                chosen.append((source["id"], item))
            else:
                dropped = True
        return layout["background"], chosen, dropped

    background, chosen, dropped = pick(scene)
    only_screen = [source for source, _ in chosen] == ["screen"]
    if scene != "screen" and (not chosen or (only_screen and dropped)) and "screen" in layouts:
        background, chosen, _ = pick("screen")
    return background, chosen


# ---------------------------------------------------------------- the montage (Edit tab)
#
# project["edit"] (optional; without it a project exports as recorded):
#   clips     ranges of the recording's own clock ({id, in, out}), played one after another (ripple, no gaps);
#   captions  subtitle lines on the recording's clock ({id, in, out, text, asset}), so they follow every cut;
#             `asset` is the line drawn to a PNG by the page ("" until drawn);
#   texts     text on the output timeline ({id, start, end, text, asset, x, y, w}: centre and width as fractions);
#   audio     music and voice-over on the output timeline ({id, asset, name, start, in, out, volume, fade_in, fade_out}).

EDIT_VERSION = 1
CAPTION_STYLE = {"font": "system-ui", "size": 54, "color": "#ffffff", "outline": "#000000", "box": False, "position": "bottom"}
CAPTION_FONTS = ("system-ui", "serif", "monospace", "rounded")
CAPTION_POSITIONS = ("bottom", "middle", "top")
AUDIO_ASSETS = (".m4a", ".mp3", ".wav", ".flac", ".aac", ".aiff", ".caf")
IMAGE_ASSETS = (".png", ".jpg", ".jpeg")
EDIT_LIMITS = {"clips": 5000, "captions": 10000, "texts": 500, "audio": 200}
_EDIT_KEYS = {"version", "clips", "captions", "caption_style", "texts", "audio"}


def default_edit(project: dict) -> dict:
    return {
        "version": EDIT_VERSION,
        "clips": [{"id": "c1", "in": 0.0, "out": float(project["duration"])}],
        "captions": [],
        "caption_style": dict(CAPTION_STYLE),
        "texts": [],
        "audio": [],
    }


def _edit_list(edit: dict, key: str) -> list:
    value = edit.get(key)
    if not isinstance(value, list) or len(value) > EDIT_LIMITS[key]:
        _fail(f"edit.{key}", f"must be a list of at most {EDIT_LIMITS[key]} items")
    ids: set[str] = set()
    for index, item in enumerate(value):  # type: ignore[arg-type]
        here = f"edit.{key}[{index}]"
        _dict(item, here)
        ident = _ident(item.get("id"), f"{here}.id")
        if ident in ids:
            _fail(f"{here}.id", "is used twice")
        ids.add(ident)
    return value  # type: ignore[return-value]


def _span(item: dict, here: str, first: str, last: str) -> None:
    low = _numeric(item.get(first), f"{here}.{first}", 0, 1e7)
    if _numeric(item.get(last), f"{here}.{last}", 0, 1e7) <= low:
        _fail(f"{here}.{last}", f"must be after {first}")


def _edit_asset(folder: Path, value: object, where: str, suffixes: tuple, empty: bool = False) -> None:
    if empty and value == "":
        return
    name = asset_name(value, where)
    if Path(name).suffix.casefold() not in suffixes:
        _fail(where, "must be a " + "/".join(suffix[1:] for suffix in suffixes) + " file")
    inside(folder, f"assets/{name}", where)


def validate_edit(value: object, folder: Path) -> dict:
    edit = _dict(value, "edit")
    if edit.get("version") != EDIT_VERSION:
        _fail("edit.version", f"must be {EDIT_VERSION}")
    unknown = set(edit) - _EDIT_KEYS
    if unknown:
        _fail("edit", "has unknown keys: " + ", ".join(sorted(unknown)))
    for index, clip in enumerate(_edit_list(edit, "clips")):
        _span(clip, f"edit.clips[{index}]", "in", "out")
    for index, line in enumerate(_edit_list(edit, "captions")):
        here = f"edit.captions[{index}]"
        _span(line, here, "in", "out")
        _text(line.get("text"), f"{here}.text", 500)
        _edit_asset(folder, line.get("asset"), f"{here}.asset", (".png",), empty=True)
    style = _dict(edit.get("caption_style"), "edit.caption_style")
    if set(style) != set(CAPTION_STYLE):
        _fail("edit.caption_style", "must have " + ", ".join(sorted(CAPTION_STYLE)))
    _choice(style["font"], "edit.caption_style.font", CAPTION_FONTS)
    _numeric(style["size"], "edit.caption_style.size", 12, 240)
    _color(style["color"], "edit.caption_style.color")
    if style["outline"] != "":
        _color(style["outline"], "edit.caption_style.outline")
    _bool(style["box"], "edit.caption_style.box")
    _choice(style["position"], "edit.caption_style.position", CAPTION_POSITIONS)
    for index, item in enumerate(_edit_list(edit, "texts")):
        here = f"edit.texts[{index}]"
        _span(item, here, "start", "end")
        _text(item.get("text"), f"{here}.text", 500)
        _edit_asset(folder, item.get("asset"), f"{here}.asset", (".png",), empty=True)
        _numeric(item.get("x"), f"{here}.x", 0, 1)
        _numeric(item.get("y"), f"{here}.y", 0, 1)
        _numeric(item.get("w"), f"{here}.w", 0.01, 1)
    for index, item in enumerate(_edit_list(edit, "audio")):
        here = f"edit.audio[{index}]"
        _edit_asset(folder, item.get("asset"), f"{here}.asset", AUDIO_ASSETS)
        _text(item.get("name"), f"{here}.name", 200)
        _numeric(item.get("start"), f"{here}.start", 0, 1e7)
        _span(item, here, "in", "out")
        _numeric(item.get("volume"), f"{here}.volume", 0, 4)
        _numeric(item.get("fade_in"), f"{here}.fade_in", 0, 600)
        _numeric(item.get("fade_out"), f"{here}.fade_out", 0, 600)
    return edit


def _snap(value: float, fps: int) -> float:
    return round(value * fps) / fps


def edit_clips(project: dict, fps: int) -> list[dict]:
    """The clips on frame boundaries with their place on the output (`at`); pieces under a frame go."""
    edit = project.get("edit")
    raw = edit["clips"] if edit else [{"in": 0.0, "out": float(project["duration"])}]
    clips, at = [], 0.0
    for clip in raw:
        begin, end = _snap(clip["in"], fps), _snap(clip["out"], fps)
        if end - begin < 1 / fps - 1e-9:
            continue
        clips.append({"in": begin, "out": end, "at": round(at, 6)})
        at += end - begin
    return clips


def edit_length(project: dict, fps: int) -> float:
    return round(sum(clip["out"] - clip["in"] for clip in edit_clips(project, fps)), 6)


def edit_pieces(project: dict, fps: int) -> list[dict]:
    """timeline_intervals cut to the clips, in output order; each piece knows its place on the output (`at`)."""
    frame = 1 / fps
    intervals, begins, elapsed = timeline_intervals(project, fps), [], 0.0
    for segment in project["segments"]:
        begins.append(_snap(elapsed, fps))
        elapsed += segment["duration"]
    pieces = []
    for clip in edit_clips(project, fps):
        at = clip["at"]
        for interval in intervals:
            start = begins[interval["segment"]] + interval["start"]
            low, high = max(start, clip["in"]), min(start + interval["length"], clip["out"])
            if high - low < frame - 1e-9:
                continue
            pieces.append({
                "segment": interval["segment"],
                "start": round(low - begins[interval["segment"]], 6) + 0.0,
                "length": round(high - low, 6),
                "scene": interval["scene"],
                "at": round(at + low - clip["in"], 6) + 0.0,
            })
    return pieces


def caption_spans(project: dict, fps: int) -> list[dict]:
    """Captions on the output: each line clipped to what the cuts keep (a line across a cut stays one line)."""
    edit = project.get("edit") or {}
    clips = edit_clips(project, fps)
    spans = []
    for line in sorted(edit.get("captions", []), key=lambda item: item["in"]):
        parts = []
        for clip in clips:
            low, high = max(line["in"], clip["in"]), min(line["out"], clip["out"])
            if high > low:
                parts.append((clip["at"] + low - clip["in"], clip["at"] + high - clip["in"]))
        if not parts:
            continue
        start, end = parts[0][0], parts[-1][1]
        if end - start < 1 / fps:
            continue
        spans.append({"start": round(start, 3) + 0.0, "end": round(end, 3) + 0.0, "text": line["text"], "asset": line.get("asset", "")})
    return spans


def _srt_time(value: float) -> str:
    millis = round(value * 1000)
    return f"{millis // 3600000:02d}:{millis // 60000 % 60:02d}:{millis // 1000 % 60:02d},{millis % 1000:03d}"


def srt_text(spans: list[dict]) -> str:
    return "\n".join(
        f"{number}\n{_srt_time(span['start'])} --> {_srt_time(span['end'])}\n{span['text']}\n"
        for number, span in enumerate(spans, 1)
    )
