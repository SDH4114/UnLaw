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
