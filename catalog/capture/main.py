# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Screenshots, screen/camera/audio recording projects and video export on macOS."""
from __future__ import annotations

COMMAND_HELP = 'Screenshots, screen/camera/audio recording projects and video export on macOS.\nUsage: ul capture                 the studio in a terminal (scenes, sources, REC, export)\n       ul capture shot [screen|area|window] [options] [PATH]\n       ul capture record [screen|camera|audio] [options] [PATH]\n       ul capture pause | resume | status | scene N | mark [TEXT] | stop [--force] [--export]\n       ul capture projects | project X | export X [options] | setup | doctor | devices [--modes]\n       ul capture list | last | open | reveal | copy | delete | trim | convert | wave\nScreenshots (shot):\n  screen (default) the whole display; area / window let you select with the mouse\n  --display N      which display (1 = main; see `devices`)   --delay S  wait S seconds\n  --clipboard      copy instead of saving   --cursor  include the pointer\n  --jpg            JPEG instead of PNG      --open    open the file afterwards\nRecording (record) runs in the background until `ul capture stop`. Every recording is a\nproject folder in storage.root/captures/projects: the screen, the camera and the\nmicrophone are separate files in media/, and project.json says how to put them\ntogether (scenes, layouts per format, marks). Nothing is re-encoded while recording.\n  screen (default) the display with the Mac\'s sound and the microphone\n  camera           the camera with the microphone (scene Camera)\n  audio            the microphone only\n  --camera / --no-camera   add the camera to a screen recording (or not)\n  --scene N|ID     the scene to start with (1 Screen + camera, 2 Screen, 3 Camera, 4 Side by side)\n  --canvas C       16:9, 9:16, 1:1, 4:5 or source: the format the project opens in\n  --mic NAME|N     microphone by name or number; --no-mic records without it\n  --cam NAME|N     camera by name or number (default: capture.camera_device)\n  --cam-mode WxH@FPS|auto   a camera mode from `devices --modes` (auto: 1080p, highest fps)\n  --cam-quality max|high|light   camera file: 1080p 12 Mbps, 1080p 6 Mbps (default), 720p 3 Mbps\n  --mic-format flac|wav|m4a      microphone file: lossless flac (default), wav, or AAC\n  --system-audio / --no-system-audio   sound of the Mac (screen only)\n  --display N      --rect X,Y,W,H (part of the screen, in points)   --no-clicks\n  --countdown N    wait N seconds before recording\n  --duration S     record S seconds in the foreground, then save\n  --wait           stay in the foreground: Enter stops, p + Enter pauses\n  --export         export right after stop (with the last export settings)\n  --output PATH    export to PATH after stop (.mov or .mp4 picks the container)\n  --format F       mov|mp4 (or m4a|mp3|wav for audio): the export\'s container\n  pause / resume   pause and continue; every pause starts a new part\n  scene N|ID       switch the scene now (it is written into the timeline)\n  mark [TEXT]      put a marker at the current time\n  stop             stop every recorder together and save the project; a recorder that\n                   does not stop is never killed: the rest is saved and `stop` tries again\n  stop --force     end a recorder that hangs (its track is lost)\n  stop --export [export options]   save and export at once\n  status           what is recording, for how long, the scene, mic level and warnings\nProjects and export (the export never changes the project):\n  projects         the projects, newest first, with state, length, size and exports\n  project X        a project\'s details (X: name, folder or `last`); --remember lists a\n                   folder from elsewhere; --set-json - saves edits read from stdin\n  export X         render a video: --canvas 16:9|9:16|1:1|4:5|source (source = the screen\n                   as recorded, ready in seconds), --height 1080|1440|2160 (short side),\n                   --fps 60|30, --codec h264|hevc, --quality high|max, --format mov|mp4,\n                   --no-normalize (loudness -14 LUFS is on), --delete-sources (move the\n                   project to the Trash afterwards), --output PATH, --background\n                   Defaults: the project\'s last export, else the last one anywhere,\n                   else 16:9 1440p 60 fps H.264 (vertical formats 1080).\n  export --status  progress of the running export\n                   An edit made in the desk\'s Edit tab (project.json `edit`: cuts, subtitles,\n                   text, music) is applied; subtitles are burned in and saved as a .srt too.\n  setup            the studio setup (sources, devices, scenes, layouts, export defaults)\n                   as JSON; --set-json - saves it from stdin, --reset restores defaults\n  doctor           Screen Recording permission, ffmpeg, and which app needs the\n                   permissions; --open screen|camera|microphone opens System Settings\nLibrary:\n  list [N] [--all] the newest exported files and screenshots with kind, length and size\n  last [--reveal]  open the newest capture (or show it in Finder)\n  open|reveal X    open a capture, or show it in Finder (X: name, path or `last`)\n  copy X           put a screenshot on the clipboard\n  delete X         move a capture or a project to the Trash (only from the capture folders)\n  trim X --from T [--to T]   cut a recording exactly (T: seconds or m:ss); keeps the original\n  convert X --to mp4|mov|gif|m4a|mp3|wav   a new file next to the original\n  devices          displays, cameras and microphones with their numbers\n  devices --modes [--camera NAME]   the modes each camera offers (turns its light on briefly)\n  wave X [--bars N] the loudness of a recording as bars (like Voice Memos)\n                    (--project P: X is a file of project P, up to 20000 bars)\n  transcribe P      subtitles for project P from `ul lm transcribe` (--language CODE --model NAME), JSON with --json\n  thumb X / preview [--display N]   small JPEGs (used by `ul desk`)\nAdd --json to any action for machine-readable output.\nFiles: storage.root/captures/projects, /recordings (exports) and /screenshots; never\n  overwritten (" 2" is added). The studio setup is storage.root/studio/setup.json.\nSettings: capture.audio_device and capture.camera_device (`default` = what macOS\n  uses, a name, or a number from `devices`), capture.screen_audio (microphone in\n  screen recordings, true), capture.system_audio (true), capture.show_clicks (true),\n  capture.video_format (mov) and capture.audio_format (m4a) for exports.\nPermissions: macOS gives Screen Recording, Camera and Microphone to the app that\n  starts ul (Ghostty, Zed, ...). `ul capture doctor` names it.\nEngine: on macOS 15+ ul-rec (installed next to ul) records screen, Mac sound, camera\n  and microphone in one process on one clock; UNLAW_CAPTURE_REC=off uses the tools below.\nDependencies: macOS screencapture; ffmpeg + ffprobe (brew install ffmpeg) for export,\n  trim and convert, and without ul-rec for the camera, the microphone track and audio.\n`ul desk` has a Studio tab with the same controls, a live layout and an export dialog.\nExamples: ul capture record --camera; ul capture scene 3; ul capture stop\n  ul capture export last --canvas 9:16; ul capture record audio --duration 60\n'

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

"""Studio setup and recording projects: pure data (no external tools).

The setup (`storage.root/studio/setup.json`) is what the Studio records next:
sources, devices, scenes, one layout per format and export choices. Every
recording copies it into a project folder whose `project.json` says how to put
the separate tracks back together.
"""


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

"""The macOS side of `ul capture`: devices, recorder commands, permissions.

Everything that names `screencapture`, AVFoundation or System Settings lives
here, so a Windows or Linux backend can replace this one module.
"""


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

    def native_devices(self) -> dict | None:
        """Cameras with their modes and microphones from `ul-rec --devices` (AVFoundation reads the formats
        without opening the camera); None without ul-rec or when it fails."""
        rec = self.native_recorder()
        if rec is None:
            return None
        try:
            result = subprocess.run(
                [rec, "--devices"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, check=False
            )
            data = json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        cameras = []
        for camera in data.get("cameras", []):
            if not isinstance(camera, dict) or not isinstance(camera.get("name"), str):
                continue
            modes: list[dict] = []
            for mode in camera.get("modes", []):
                try:
                    item = {
                        "width": int(mode["width"]),
                        "height": int(mode["height"]),
                        "min_fps": f"{float(mode['min_fps']):.6f}",
                        "max_fps": f"{float(mode['max_fps']):.6f}",
                    }
                except (KeyError, TypeError, ValueError):
                    continue
                if item not in modes:
                    modes.append(item)
            cameras.append({"name": camera["name"], "modes": modes})
        microphones = [name for name in data.get("microphones", []) if isinstance(name, str)]
        default = data.get("default_camera")
        return {
            "cameras": cameras,
            "microphones": microphones,
            "default_camera": default if isinstance(default, str) else None,
        }

    def list_avfoundation(self) -> tuple[list[str], list[str]]:
        native = self.native_devices()
        if native is not None:
            return [camera["name"] for camera in native["cameras"]], native["microphones"]
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
        native = self.native_devices()
        if native is not None:
            if name == "default":
                name = native["default_camera"] or ""
            return next((camera["modes"] for camera in native["cameras"] if camera["name"] == name), [])
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

"""Export of Studio projects: the separate tracks of a project become one video (or audio file).

The timeline is cut into intervals at pauses and scene switches; each interval is rendered by one
ffmpeg run with that scene's layout, the chunks are joined by stream copy, and the sound (system
sound and microphone, each at its own start offset) is mixed per segment and muxed at the end.
Masks, borders and shadows are PNGs drawn here (no image library).
"""


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
        project, interval["scene"], settings["canvas"], set(segment["files"])
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
            try:
                still = inside(folder, f"assets/{source['asset']}", f"source {source_id}")
            except ProjectError as error:
                raise ExportError(str(error)) from error
            index = still_input(still)
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
    current = _overlay_stills(interval.get("overlays", []), width, height, still_input, graph, current)
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


def _overlay_stills(overlays: list[dict], width: int, height: int, still_input: Callable[[Path], int], graph: list[str], current: str) -> str:
    """Captions and text drawn by the page (PNG), each shown only between its `start` and `end` in this chunk.

    A caption PNG is drawn at twice the size for a 1080-line frame (sharp up to 4K) and scaled with the
    canvas; it sits centred at the bottom,
    middle or top. A text PNG is scaled to its width (`w` of the canvas) around its centre (`x`, `y`).
    """
    for number, item in enumerate(overlays):
        index = still_input(item["path"])
        when = f"enable='between(t,{item['start']:.3f},{item['end']:.3f})'"
        if item["kind"] == "caption":
            scale = min(width, height) / 2160
            graph.append(f"[{index}:v]scale=iw*{scale:.5f}:ih*{scale:.5f}[t{number}]")
            margin = round(min(width, height) * 0.07)
            y = {"bottom": f"H-h-{margin}", "middle": "(H-h)/2", "top": str(margin)}[item["position"]]
            graph.append(f"{current}[t{number}]overlay=(W-w)/2:{y}:{when}:eof_action=pass[x{number}]")
        else:
            box = max(2, round(item["w"] * width))
            graph.append(f"[{index}:v]scale={box}:-1[t{number}]")
            graph.append(
                f"{current}[t{number}]overlay={item['x'] * width:.1f}-w/2:{item['y'] * height:.1f}-h/2:{when}:eof_action=pass[x{number}]"
            )
        current = f"[x{number}]"
    return current


def piece_overlays(folder: Path, project: dict, settings: dict, at: float, length: int | float) -> list[dict]:
    """The captions and texts of the edit that show during [at, at + length) of the output, in chunk time."""
    edit = project.get("edit") or {}
    found = []
    style = edit.get("caption_style", {})
    items = [("caption", span) for span in caption_spans(project, settings["fps"])]
    items += [("text", item) for item in edit.get("texts", [])]
    for kind, item in items:
        low, high = max(item["start"], at), min(item["end"], at + length)
        if high <= low:
            continue
        if not item.get("asset"):
            raise ExportError(f"the {kind} “{item['text'][:40]}” is not drawn yet: open the project in the Edit tab")
        try:
            path = inside(folder, f"assets/{item['asset']}", f"{kind} {item.get('id', item['text'][:20])}")
        except ProjectError as error:
            raise ExportError(str(error)) from error
        if not path.is_file():
            raise ExportError(f"the {kind} “{item['text'][:40]}” is not drawn yet: open the project in the Edit tab")
        entry = {"kind": kind, "path": path, "start": round(low - at, 3), "end": round(high - at, 3)}
        if kind == "caption":
            entry["position"] = style.get("position", "bottom")
        else:
            entry.update(x=item["x"], y=item["y"], w=item["w"])
        found.append(entry)
    return found


def source_piece_argv(folder: Path, project: dict, piece: dict, track: str, settings: dict, out: Path) -> list[str]:
    """One piece of an edited "as recorded" export: the track itself, cut and re-encoded, with captions on top."""
    segment = project["segments"][piece["segment"]]
    info = _track_info(folder, segment, track)
    width, height = _even(info["width"] or 1920), _even(info["height"] or 1080)
    local = piece["start"] - segment["starts"].get(track, 0.0)
    inputs = (["-ss", f"{local:.3f}"] if local > 0 else ["-itsoffset", f"{-local:.3f}"] if local < 0 else [])
    inputs += ["-i", str(folder / segment["files"][track])]
    count = 1

    def still_input(path: Path) -> int:
        nonlocal count
        inputs.extend(["-loop", "1", "-t", f"{piece['length']:.3f}", "-i", str(path)])
        count += 1
        return count - 1

    graph = [f"[0:v]scale={width}:{height},fps={settings['fps']},setsar=1[base]"]
    current = _overlay_stills(piece.get("overlays", []), width, height, still_input, graph, "[base]")
    graph.append(f"{current}format=yuv420p[vout]")
    return [
        *FFMPEG_BASE, *inputs, "-filter_complex", ";".join(graph), "-map", "[vout]", "-an",
        *_encoder(settings, width, height), "-t", f"{piece['length']:.3f}", "-progress", "pipe:1", "-nostats", str(out),
    ]


def edited_sound_argv(folder: Path, project: dict, settings: dict, recording: Path | None, out: Path) -> list[str] | None:
    """The recording's sound cut to the clips, with music and voice-over mixed in; None when nothing is audible."""
    edit = project["edit"]
    clips = edit_clips(project, settings["fps"])
    total = sum(clip["out"] - clip["in"] for clip in clips)
    inputs: list[str] = []
    graph: list[str] = []
    labels: list[str] = []
    if recording is not None and clips:
        inputs += ["-i", str(recording)]
        for number, clip in enumerate(clips):
            graph.append(f"[0:a]atrim=start={clip['in']:.6f}:end={clip['out']:.6f},asetpts=PTS-STARTPTS[c{number}]")
        graph.append("".join(f"[c{number}]" for number in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1[main]")
        labels.append("[main]")
    for item in edit["audio"]:
        if item["start"] >= total:
            continue
        try:
            path = inside(folder, f"assets/{item['asset']}", f"audio {item['name']}")
        except ProjectError as error:
            raise ExportError(str(error)) from error
        if not path.is_file():
            raise ExportError(f"the sound file {item['asset']} is missing from the project")
        index = len(inputs) // 2
        inputs += ["-i", str(path)]
        length = item["out"] - item["in"]
        chain = (
            f"[{index}:a]atrim=start={item['in']:.3f}:end={item['out']:.3f},asetpts=PTS-STARTPTS,"
            f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={item['volume']:g}"
        )
        if item["fade_in"] > 0:
            chain += f",afade=t=in:d={min(item['fade_in'], length):.3f}"
        if item["fade_out"] > 0:
            fade = min(item["fade_out"], length)
            chain += f",afade=t=out:st={length - fade:.3f}:d={fade:.3f}"
        if item["start"] > 0:
            chain += f",adelay={round(item['start'] * 1000)}:all=1"
        graph.append(f"{chain}[m{index}]")
        labels.append(f"[m{index}]")
    if not labels:
        return None
    if len(labels) > 1:
        graph.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[mix]")
        last = "[mix]"
    else:
        last = labels[0]
    graph.append(f"{last}apad,atrim=0:{total:.6f}[aout]")
    return [
        *FFMPEG_BASE, *inputs, "-filter_complex", ";".join(graph), "-map", "[aout]",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(out),
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
    except (OSError, ValueError):
        return {"phase": "idle"}
    if not isinstance(data, dict):
        return {"phase": "idle"}
    if data.get("phase") in ("queued", "running") and not _process_alive(data.get("pid")):
        return {"phase": "idle"}  # the exporting process was killed (terminal closed, power loss)
    return data


def _process_alive(pid: object) -> bool:
    """An old status without a pid counts as alive, as before."""
    if pid is None:
        return True
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
            "pid": os.getpid(),
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
        offset = stream.tell()  # the error message quotes this run only, not an older one in the same log
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
        with log.open("rb") as stream:
            stream.seek(offset)
            text = stream.read().decode(errors="replace")
        tail = [line for line in text.splitlines() if line and not line.startswith("$ ")][-2:]
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
            # No hard links here (exFAT, a network volume): copy, and never leave half a file behind.
            try:
                out = target.open("xb")
            except FileExistsError:
                continue
            try:
                with out, temporary.open("rb") as source:
                    shutil.copyfileobj(source, out)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
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
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)  # inside the try: Ctrl-C while queued is reported too
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



def _render_edit(folder: Path, project: dict, settings: dict, work: Path, video: Path, log: Path, report: Callable[[float], None]) -> None:
    """The edited picture: one chunk per piece of a clip (cut at pauses and scene switches), joined."""
    pieces = edit_pieces(project, settings["fps"])
    if not pieces:
        raise ExportError("the edit keeps less than one frame of picture")
    source = settings["canvas"] == "source"
    track = "screen" if any("screen" in segment["files"] for segment in project["segments"]) else "camera"
    total = sum(piece["length"] for piece in pieces) or 1.0
    done = 0.0
    chunks = []
    for number, piece in enumerate(pieces):
        piece["overlays"] = piece_overlays(folder, project, settings, piece["at"], piece["length"])
        chunk = work / f"chunk-{number:04d}.mp4"
        if source:
            if track not in project["segments"][piece["segment"]]["files"]:
                raise ExportError(
                    f"part {piece['segment'] + 1} has no {track} track (its recorder stopped early): "
                    "export to a format such as 16:9 instead of source"
                )
            argv = source_piece_argv(folder, project, piece, track, settings, chunk)
        else:
            argv = interval_argv(folder, project, piece, settings, chunk, folder / "cache")
        _run_ffmpeg(
            argv,
            log,
            "rendering the video",
            lambda seconds, done=done, length=piece["length"]: report(0.05 + 0.85 * (done + min(seconds, length)) / total),
        )
        done += piece["length"]
        chunks.append(chunk)
    _run_ffmpeg(_concat_argv(chunks, work / "video.txt", video), log, "joining the video")


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
    # Never follow a symlinked cache or logs folder out of the project (rmtree would empty its target).
    for relative in ("cache", "cache/render", "logs"):
        inside(folder, relative, relative)
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
        # Parts shorter than one frame are dropped everywhere (a stop or pause right after a start).
        kept = [
            index
            for index, segment in enumerate(project["segments"])
            if segment["duration"] >= 1 / settings["fps"]
        ]
        if not kept:
            raise ExportError("the recording is shorter than one frame")
        edited = "edit" in project
        if edited and edit_length(project, settings["fps"]) <= 0:
            raise ExportError("the edit is empty: every clip was cut away")
        # Sound: one WAV per segment (silence where nothing is audible), joined. An edit keeps every part with
        # any length, so the joined sound runs on the recording's own clock, which the clips are written in.
        audio_parts = []
        sound_parts = [index for index, segment in enumerate(project["segments"]) if segment["duration"] > 0] if edited else kept
        for index in sound_parts:
            segment = project["segments"][index]
            wav = work / f"audio-{index:03d}.wav"
            argv = audio_argv(folder, project, index, settings, wav)
            _run_ffmpeg(
                argv or _silence_argv(segment["duration"], wav), log, "mixing the sound"
            )
            audio_parts.append(wav)
        audible = any(
            audio_argv(folder, project, index, settings, Path(os.devnull))
            for index in sound_parts
        )
        sound = work / "audio.wav"
        if edited:
            recording = work / "recording.wav" if audible else None
            if recording is not None:
                _run_ffmpeg(_concat_argv(audio_parts, work / "audio.txt", recording), log, "joining the sound")
            argv = edited_sound_argv(folder, project, settings, recording, sound)
            audible = argv is not None
            if argv is not None:
                _run_ffmpeg(argv, log, "cutting the sound")
        elif audible:
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
            if edited:
                _render_edit(folder, project, settings, work, video, log, report)
            elif settings["canvas"] == "source":
                track = (
                    "screen"
                    if any(
                        "screen" in segment["files"] for segment in project["segments"]
                    )
                    else "camera"
                )
                for index in kept:
                    if track not in project["segments"][index]["files"]:
                        # Skipping the part would put the sound after it out of sync.
                        raise ExportError(
                            f"part {index + 1} has no {track} track (its recorder stopped early): "
                            "export to a format such as 16:9 instead of source"
                        )
                files = [folder / project["segments"][index]["files"][track] for index in kept]
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
        if edited:
            spans = caption_spans(project, settings["fps"])
            if spans:
                # The subtitles also go next to the video as a file, for YouTube and players.
                srt = work / "captions.srt"
                srt.write_text(srt_text(spans), encoding="utf-8")
                _publish(srt, result.with_suffix(".srt"))
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
        try:
            _trash(folder)
        except OSError as error:
            # The video is saved and listed; a Trash that refuses must not turn that into a failure.
            status.write(force=True, warning=f"the project was not moved to the Trash: {error}")
    return result

"""The terminal studio of `ul capture`: a full-screen curses view over the same recording engine.

`render_frame` and `tui_action` are pure (tested without a terminal); `run_tui` draws them with curses
and calls the engine through the functions it is given, so this module never imports the CLI.
Quitting never stops a recording.
"""


import curses
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path


CYCLE_CANVASES = ("16:9", "9:16", "1:1", "4:5")
KEY_BAR = "R record/stop  P pause  1-9 scene  M mark  F format  C camera  V mic  S sound  D camera device  E export  Q quit"
EXPORT_BAR = (
    "F format  H height  T fps  K codec  O mp4/mov  N loudness  Enter export  Q back"
)
DONE_BAR = "O open  V show in Finder  Q back"


def _tui_clock(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    hours, rest = divmod(seconds, 3600)
    return f"{hours:02d}:{rest // 60:02d}:{rest % 60:02d}"


def _tui_next(values: tuple, current: object) -> object:
    return (
        values[(values.index(current) + 1) % len(values)]
        if current in values
        else values[0]
    )


def _tui_meter(level: float | None, width: int = 20) -> str:
    if level is None:
        return "-" * width + "   -- dB"
    filled = round(min(max((level + 60) / 60, 0.0), 1.0) * width)
    return "█" * filled + "░" * (width - filled) + f"  {level:.0f} dB"


def _tui_source(setup: dict, kind: str) -> dict | None:
    return next((item for item in setup["sources"] if item["kind"] == kind), None)


def _tui_fit(lines: list[str], cols: int, rows: int, bottom: list[str]) -> list[str]:
    """Exactly `rows` lines of at most `cols` characters; the bottom lines always stay."""
    body_rows = max(rows - len(bottom), 0)
    body = lines[:body_rows] + [""] * max(body_rows - len(lines), 0)
    return [line[:cols] for line in (body + bottom)[-rows:]] if rows else []


def _wrap_bar(text: str, cols: int) -> list[str]:
    """The key bar on as many lines as the width needs (words are never cut)."""
    lines, current = [], ""
    for word in text.split("  "):
        candidate = f"{current}  {word}" if current else word
        if len(candidate) <= cols or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    return [*lines, current]


def _main_lines(model: dict, cols: int) -> list[str]:
    setup, status = model["setup"], model["status"] or {"active": False}
    active = status.get("active")
    if active:
        if status.get("phase") == "stuck":
            state = "! STUCK " + _tui_clock(status.get("elapsed", 0))
        elif status.get("paused"):
            state = "❚❚ PAUSED " + _tui_clock(status.get("elapsed", 0))
        else:
            state = "● REC " + _tui_clock(status.get("elapsed", 0))
    else:
        state = "Ready"
    title = " Unlaw Studio"
    lines = [
        title + " " * max(cols - len(title) - len(state) - 1, 1) + state,
        "─" * cols,
    ]
    current_scene = status.get("scene") if active else setup["scene"]
    scenes = ["Scenes"] + [
        f"  {number} {'●' if scene['id'] == current_scene else ' '} {scene['name']}"
        for number, scene in enumerate(setup["scenes"], 1)
    ]
    screen, camera = _tui_source(setup, "screen"), _tui_source(setup, "camera")
    mic, system = setup["audio"]["mic"], setup["audio"]["system"]
    sources = ["Sources"]
    if screen:
        area = f"area {screen['area']}" if screen["area"] else "whole display"
        sources.append(
            f"  [{'x' if screen['enabled'] else ' '}] Screen   display {screen['display']}, {area}"
        )
    if camera:
        sources.append(
            f"  [{'x' if camera['enabled'] else ' '}] Camera   {camera['device']}  {camera['quality']}"
        )
    sources.append(
        f"  [{'x' if mic['enabled'] else ' '}] Mic      {mic['device']}  {mic['format']}"
    )
    sources.append(f"  [{'x' if system['enabled'] else ' '}] Mac sound")
    if cols >= 72:
        width = max(len(line) for line in scenes) + 4
        rows = max(len(scenes), len(sources))
        scenes += [""] * (rows - len(scenes))
        sources += [""] * (rows - len(sources))
        lines += [left.ljust(width) + right for left, right in zip(scenes, sources)]
    else:
        lines += scenes + sources
    lines.append("")
    lines.append(
        f"Format {setup['canvas']}   Countdown {setup['countdown']} s   Menu bar {'on' if setup['menubar'] else 'off'}"
    )
    if active:
        lines.append(f"Mic  {_tui_meter(status.get('level_db'))}")
        free = status.get("free_bytes")
        if free is not None:
            lines.append(f"{free / 1e9:.0f} GB free")
        if status.get("phase") == "stuck":
            lines.append(
                f"! {', '.join(status.get('stuck', []))} does not stop: R tries again, `ul capture stop --force` ends it"
            )
        if status.get("phase") == "interrupted":
            lines.append("! a recorder stopped: R saves what was recorded")
        lines += [f"! {warning}" for warning in status.get("warnings", [])]
    if model.get("message"):
        lines.append(model["message"])
    return lines


def _export_lines(model: dict, cols: int) -> list[str]:
    choice, export = model["choice"] or {}, model.get("export") or {}
    name = Path(model.get("project") or "").name
    lines = [f" Export {name}", "─" * cols]
    canvas = choice.get("canvas", "16:9")
    if canvas == "source":
        size = "as recorded"
    else:
        try:
            width, height = canvas_size(canvas, choice.get("height", 1080))
            size = f"{width}x{height}"
        except ProjectError:
            size = "?"
    lines += [
        f"  Format    {canvas}  ({size})",
        f"  Height    {choice.get('height')}",
        f"  FPS       {choice.get('fps')}",
        f"  Codec     {choice.get('codec')}",
        f"  File      .{choice.get('container')}",
        f"  Loudness  {'-14 LUFS' if choice.get('normalize') else 'as recorded'}",
        "",
    ]
    phase = export.get("phase")
    if phase in ("queued", "running"):
        percent = int(export.get("percent") or 0)
        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
        eta = f"  about {export['eta']} s left" if export.get("eta") else ""
        lines.append(
            f"  {'Waiting for another export' if phase == 'queued' else 'Exporting'}  {bar}  {percent}%{eta}"
        )
    elif phase == "done" and export.get("output"):
        lines.append(f"  Saved: {export['output']}")
    elif phase == "failed":
        lines.append(f"  Export failed: {export.get('error')}")
    if model.get("message"):
        lines.append(model["message"])
    return lines


def render_frame(model: dict, cols: int, rows: int) -> list[str]:
    if model.get("screen") == "export":
        done = (model.get("export") or {}).get("phase") == "done"
        return _tui_fit(
            _export_lines(model, cols),
            cols,
            rows,
            _wrap_bar(DONE_BAR if done else EXPORT_BAR, cols),
        )
    return _tui_fit(_main_lines(model, cols), cols, rows, _wrap_bar(KEY_BAR, cols))


def tui_action(key: str, model: dict) -> tuple | None:
    lower = key.lower() if len(key) == 1 else key
    if model.get("screen") == "export":
        export = model.get("export") or {}
        if export.get("phase") in ("queued", "running"):
            return ("back",) if lower == "q" else None
        if export.get("phase") == "done" and export.get("output"):
            return {
                "o": ("open", export["output"]),
                "v": ("reveal", export["output"]),
                "q": ("back",),
            }.get(lower)
        choice = model.get("choice") or {}
        if lower == "f":
            return ("choose", "canvas", _tui_next(CANVASES, choice.get("canvas")))
        if lower == "h":
            return ("choose", "height", _tui_next(HEIGHTS, choice.get("height")))
        if lower == "t":
            return ("choose", "fps", _tui_next(tuple(reversed(FPS)), choice.get("fps")))
        if lower == "k":
            return ("choose", "codec", _tui_next(CODECS, choice.get("codec")))
        if lower == "o":
            return (
                "choose",
                "container",
                "mp4" if choice.get("container") == "mov" else "mov",
            )
        if lower == "n":
            return ("choose", "normalize", not choice.get("normalize", True))
        if key in ("\n", "\r", "KEY_ENTER"):
            return ("start-export",)
        if lower in ("q", "\x1b"):
            return ("back",)
        return None
    active = bool((model.get("status") or {}).get("active"))
    setup = model["setup"]
    if lower == "q":
        return ("quit",)
    if lower == "r":
        return ("stop",) if active else ("record",)
    if len(key) == 1 and key in "123456789":  # not isdigit(): "²" is a digit to Python, but int() refuses it
        number = int(key)
        return (
            ("scene", setup["scenes"][number - 1]["id"])
            if number <= len(setup["scenes"])
            else None
        )
    if active:
        return {"p": ("pause",), "m": ("mark",)}.get(lower)
    if lower == "f":
        return ("canvas", _tui_next(CYCLE_CANVASES, setup["canvas"]))
    if lower == "c":
        return ("toggle", "camera")
    if lower == "v":
        return ("toggle", "mic")
    if lower == "s":
        return ("toggle", "system")
    if lower == "d":
        return ("devices",)
    if lower == "e":
        return ("export",)
    return None


# ---------------------------------------------------------------- curses


def _apply_setup(setup: dict, action: tuple, cameras: list[str]) -> dict:
    """A changed copy of the setup for idle actions (scene, format, sources, camera device)."""
    import copy

    changed = copy.deepcopy(setup)
    if action[0] == "scene":
        changed["scene"] = action[1]
    elif action[0] == "canvas":
        changed["canvas"] = action[1]
    elif action[0] == "toggle":
        if action[1] == "camera":
            camera = _tui_source(changed, "camera")
            if camera:
                camera["enabled"] = not camera["enabled"]
        else:
            part = changed["audio"][action[1]]
            part["enabled"] = not part["enabled"]
    elif action[0] == "devices":
        camera = _tui_source(changed, "camera")
        if camera:
            options = ["default", *cameras]
            camera["device"] = _tui_next(tuple(options), camera["device"])
    return changed


def run_tui(api: dict[str, Callable]) -> int:
    """`api`: load_setup, save_setup, status, devices, start, stop, pause, resume, scene, mark,
    last_project, export_defaults, export, export_status (all from the CLI module)."""
    return curses.wrapper(lambda window: _loop(window, api))


def _loop(window, api: dict[str, Callable]) -> int:
    curses.curs_set(0)
    window.timeout(250)
    setup, warnings = api["load_setup"]()
    model = {
        "setup": setup,
        "status": api["status"](),
        "devices": None,
        "message": "; ".join(warnings),
        "export": None,
        "screen": "main",
        "choice": None,
        "project": None,
    }
    worker: threading.Thread | None = None
    while True:
        model["status"] = api["status"]()
        if model["screen"] == "export":
            current = api["export_status"]()
            if current.get("project") == model["project"] or worker is not None:
                model["export"] = current if current.get("phase") != "idle" else None
        rows, cols = window.getmaxyx()
        window.erase()
        for row, line in enumerate(render_frame(model, cols - 1, rows)):
            try:
                window.addstr(row, 0, line)
            except curses.error:
                pass
        window.refresh()
        try:
            key = window.get_wch()
        except curses.error:
            continue
        key = (
            key
            if isinstance(key, str)
            else {curses.KEY_ENTER: "KEY_ENTER"}.get(key, "")
        )
        action = tui_action(key, model) if key else None
        if action is None:
            continue
        model["message"] = ""
        try:
            name = action[0]
            if name == "quit":
                return 0
            if name == "record":
                for left in range(model["setup"]["countdown"], 0, -1):
                    model["message"] = f"Recording in {left}…"
                    _draw_message(window, model)
                    time.sleep(1)
                model["message"] = ""
                api["start"]()
            elif name == "stop":
                result = api["stop"]()
                _open_export(model, api, result["project"])
            elif name == "pause":
                (api["resume"] if model["status"].get("paused") else api["pause"])()
            elif name == "mark":
                api["mark"]()
                model["message"] = "Mark added"
            elif name == "scene" and model["status"].get("active"):
                api["scene"](action[1])
            elif name in ("scene", "canvas", "toggle", "devices"):
                cameras = api["devices"]()["cameras"] if name == "devices" else []
                model["setup"] = api["save_setup"](
                    _apply_setup(model["setup"], action, cameras)
                )
            elif name == "export":
                _open_export(model, api, api["last_project"]())
            elif name == "choose":
                model["choice"][action[1]] = action[2]
                if (
                    action[1] == "canvas"
                    and action[2] in ("9:16", "1:1", "4:5")
                    and model["choice"]["height"] == 1440
                ):
                    model["choice"]["height"] = 1080
            elif name == "start-export":
                choice, folder = dict(model["choice"]), model["project"]
                model["export"] = {"phase": "queued", "percent": 0}

                def work(choice: dict = choice, folder: str = folder) -> None:
                    try:
                        api["export"](folder, choice)
                    except (
                        Exception
                    ) as error:  # shown on the export screen; the project is untouched
                        model["message"] = f"Export failed: {error}"

                worker = threading.Thread(target=work, daemon=True)
                worker.start()
            elif name == "back":
                model.update(screen="main", export=None, choice=None, project=None)
                worker = None
            elif name in ("open", "reveal"):
                subprocess.run(
                    ["open", *(["-R"] if name == "reveal" else []), action[1]],
                    check=False,
                )
        except (
            Exception
        ) as error:  # every engine error is a message, the studio stays open
            model["message"] = f"! {error}"


def _open_export(model: dict, api: dict[str, Callable], folder: str) -> None:
    model.update(
        screen="export",
        project=folder,
        export=None,
        choice=api["export_defaults"](folder),
    )


def _draw_message(window, model: dict) -> None:
    rows, cols = window.getmaxyx()
    window.erase()
    for row, line in enumerate(render_frame(model, cols - 1, rows)):
        try:
            window.addstr(row, 0, line)
        except curses.error:
            pass
    window.refresh()

import copy
import fcntl
import hashlib
import json
import math
import os
import re
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



USAGE = """Usage: ul capture                      (the studio in a terminal)
       ul capture shot [screen|area|window] [--display N] [--delay S] [--clipboard] [--cursor] [--jpg] [--open] [--output PATH]
       ul capture record [screen|camera|audio] [--camera] [--scene N] [--canvas C] [--mic NAME|--no-mic] [--cam NAME]
                         [--cam-quality max|high|light] [--mic-format flac|wav|m4a] [--display N] [--rect X,Y,W,H]
                         [--duration S] [--wait] [--countdown N] [--export] [--output PATH]
       ul capture pause|resume|status|scene N|mark [TEXT]|stop [--force] [--export]
       ul capture projects|project X|export X [options]|transcribe X [--language CODE]|setup|doctor|devices [--modes]
       ul capture list|last|open|reveal|copy|delete|trim|convert
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
READY_WAIT = 6.0  # the microphone and camera wake up in 1-2 s (measured on an M3 Pro)
STOP_GRACE = 30.0
TERM_GRACE = 10.0
KILL_GRACE = 2.0
SILENCE_SECONDS = 10.0
SILENCE_DB = -60.0
LOW_SPACE = 5 * 10**9
PROGRAMS = ("screencapture", "ffmpeg", "osascript", "ul-rec")
NATIVE_WAIT = 40.0  # ul-rec lists the screens (up to 20 s) and waits 15 s for every device
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
    if plan.get("encoder", "h264_videotoolbox") not in ("libx264", "h264_videotoolbox"):
        return False
    if plan.get("engine", "tools") not in ("tools", "native"):
        return False
    if plan.get("engine") == "native" and not isinstance(plan.get("rec"), str):
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
    early = state.get("early", [])
    if not isinstance(early, list) or not all(
        isinstance(tracks, list) and all(track in TRACK_ORDER for track in tracks)
        for tracks in early
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
    native = plan.get("engine") == "native"
    files = {}
    if state["mode"] == "screen":
        files["screen"] = f"media/.screen-{number:03d}.mov"
    if plan["camera"]:
        files["camera"] = f"media/.camera-{number:03d}.{'mov' if native else 'mp4'}"
    if plan["mic"]:
        if native and plan["mic_format"] != "m4a":
            # AVFoundation writes WAV (float, as the device gives it); stop turns it into the chosen format.
            files["mic"] = f"media/.mic-{number:03d}.wav"
        else:
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


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _wait_until_live(folder: Path, files: dict[str, str], started: list, levels_from: int) -> None:
    """Return once the microphone delivers sound and the camera its first frames (or after READY_WAIT),
    so `recording` is reported when speaking is recorded, not 1-2 s earlier."""
    deadline = time.monotonic() + READY_WAIT
    levels = folder / "logs" / LEVELS_FILE
    while time.monotonic() < deadline:
        if any(process.poll() is not None for _, _, process in started):
            return  # a recorder that stopped shows up as the interrupted phase
        waiting = ("mic" in files and _file_size(levels) <= levels_from) or (
            "camera" in files and _file_size(folder / files["camera"]) == 0
        )
        if not waiting:
            return
        time.sleep(0.05)


def _native_events(folder: Path, number: int) -> list[dict]:
    """What ul-rec reported for segment `number` (logs/rec-NNN.jsonl); unreadable lines are skipped."""
    try:
        text = (folder / "logs" / f"rec-{number:03d}.jsonl").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    events = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def _native_lost(events: list[dict]) -> list[str]:
    """Tracks that failed after the recording began, as `the camera recording stopped: why`."""
    ready = next((index for index, item in enumerate(events) if item.get("event") == "ready"), None)
    if ready is None:
        return []
    return [
        f"the {item.get('track')} recording stopped: {_plain_text(str(item.get('error') or 'it stopped'))}"
        for item in events[ready + 1 :]
        if item.get("event") == "failed" and item.get("track") in TRACK_ORDER
    ]


def _native_starts(events: list[dict]) -> dict[str, float]:
    """When each track's first data was written (unix seconds, ul-rec's clock)."""
    return {
        item["track"]: float(item["wall"])
        for item in events
        if item.get("event") == "started" and item.get("track") in TRACK_ORDER and _finite(item.get("wall"))
    }


def _plain_text(text: str) -> str:
    return "".join(character for character in text if character.isprintable())[:300]


def _start_native_segment(state: dict) -> None:
    """One ul-rec for every track of the segment; it reports `ready` once each track writes or failed."""
    folder = Path(state["project"])
    number = len(state["segments"]) + 1
    files = _track_files(state, number - 1)
    logs = folder / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    events_file = logs / f"rec-{number:03d}.jsonl"
    events_file.unlink(missing_ok=True)  # left by a start that failed
    _remove_part_files(folder, files)
    log_from = _log_size(folder, "rec")
    request = _backend().native_request(
        state["plan"], {track: folder / relative for track, relative in files.items()}, events_file, logs / LEVELS_FILE
    )
    request_file = logs / f"rec-{number:03d}.json"
    _write_json(request_file, request)
    spawned = time.time()
    process = _spawn([state["plan"]["rec"], str(request_file)], folder, "rec")
    try:
        deadline = time.monotonic() + NATIVE_WAIT
        events: list[dict] = []
        while time.monotonic() < deadline:
            events = _native_events(folder, number)
            if any(item.get("event") == "ready" for item in events) or process.poll() is not None:
                break
            time.sleep(0.05)
        failed = {
            item["track"]: _plain_text(str(item.get("error") or ""))
            for item in events
            if item.get("event") == "failed" and item.get("track") in files
        }
        for track in files:
            if track in failed:
                raise CaptureError(_start_failure(track, failed[track]), 1)
        ready = any(item.get("event") == "ready" for item in events)
        if not ready or process.poll() is not None:
            reason = _log_tail(folder, "rec", log_from) or "ul-rec did not start"
            raise CaptureError(f"the recorder could not start: {reason}", 1)
        starts = _native_starts(events)
        state["segments"].append(files)
        state["processes"] = [{"pid": process.pid, "program": "ul-rec", "track": track} for track in files]
        # The clock starts with the first track's data; a value outside this start is not trusted.
        first = min(starts.values(), default=spawned)
        state["segment_started"] = first if spawned <= first <= time.time() else spawned
        state["paused"] = False
        state["phase"] = "recording"
        _write_json(recording_state_file(), state)
    except BaseException:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=STOP_GRACE)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        _remove_part_files(folder, files)  # the next try reuses the part number and these names
        raise


def _remove_part_files(folder: Path, files: dict[str, str]) -> None:
    """Files of a part that never became a segment (a failed start); AVFoundation refuses to record over a file."""
    for relative in files.values():
        (folder / relative).unlink(missing_ok=True)


def _start_segment(state: dict) -> None:
    if state["plan"].get("engine") == "native":
        _start_native_segment(state)
        return
    folder = Path(state["project"])
    files = _track_files(state, len(state["segments"]))
    offsets = {track: _log_size(folder, track) for track in files}
    levels_from = _file_size(folder / "logs" / LEVELS_FILE)
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
        _wait_until_live(folder, files, started, levels_from)
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
    # A reused pid (after a reboot) must never be signalled: it has to be our tool, as the program itself
    # (or the script an interpreter runs), not a command that only mentions it (`cargo build --bin ul-rec`).
    words = command.split()
    return any(Path(word).name == program for word in words[:2])


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

    if running:
        # A recorder that is already gone did not stop with the others, so its end must not be lined up
        # with theirs (`_finish`); pause and stop both come through here, so neither loses the problem.
        part = len(state["durations"]) + 1
        early = sorted({item["track"] for item in processes if not _alive(item["pid"], item["program"])})
        for track in early:
            state["problems"].append(f"part {part}: the {track} recorder stopped during the recording")
        state["early"] = state.get("early", []) + [[]] * (part - 1 - len(state.get("early", []))) + [early]

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
    if not fmt and options.get("output"):
        suffix = Path(options["output"]).suffix[1:].casefold()
        if mode == "audio" and suffix in AUDIO_FORMATS:
            audio_format = suffix
        elif mode != "audio" and suffix in VIDEO_FORMATS:
            video_format = suffix
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
    rec = _backend().native_recorder()
    if rec is None and (want_camera or mode == "audio" or not plain_mic):
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
    mic_in_screen = mode == "screen" and mic_name == "default" and not has_ffmpeg and rec is None
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
                "encoder": _backend().camera_encoder() if camera_name and rec is None else "h264_videotoolbox",
                "engine": "native" if rec else "tools",
                "rec": rec,
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
        if setup["menubar"]:
            _start_menubar(state)
    return status()


def _start_menubar(state: dict) -> None:
    """Show the recording in the menu bar; a helper that cannot start changes nothing."""
    program = os.environ.get("UNLAW_BIN")
    if not program or shutil.which("osascript") is None:
        return
    try:
        helper = subprocess.Popen(
            _backend().menubar_argv(program, recording_state_file()),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return
    state["helpers"].append({"pid": helper.pid, "program": "osascript", "track": "menubar"})
    _write_json(recording_state_file(), state)


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
    if state["plan"].get("engine") == "native" and state["segments"]:
        warnings.extend(_native_lost(_native_events(Path(state["project"]), len(state["segments"]))))
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


def _finished_wav(folder: Path, relative: str, mic_format: str) -> str | None:
    """ul-rec's microphone WAV (float) in the chosen format: FLAC, or a 24-bit WAV; as it is without ffmpeg."""
    path = folder / relative
    stem = Path(relative).name[1:]
    has_ffmpeg = shutil.which("ffmpeg") is not None
    extension = MIC_FORMATS[mic_format] if has_ffmpeg and mic_format in ("flac", "wav") else ".wav"
    final_relative = f"media/{Path(stem).with_suffix(extension).name}"
    final = folder / final_relative
    if not (path.is_file() and path.stat().st_size > 0):
        return final_relative if final.is_file() and final.stat().st_size > 0 else None
    if not has_ffmpeg:
        os.replace(path, final)
        return final_relative
    codec = ["-c:a", "flac"] if extension == ".flac" else ["-c:a", "pcm_s24le"]
    temporary = final.with_name(f".convert-{final.name}")
    try:
        _run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(path), *codec, str(temporary)],
            "saving the mic recording",
        )
        os.replace(temporary, final)
    finally:
        temporary.unlink(missing_ok=True)
    path.unlink()
    return final_relative


def _finished_track(folder: Path, track: str, relative: str, mic_format: str = "flac") -> str | None:
    """The track's playable file (relative), remuxing a dot file the first time; None if nothing was recorded."""
    path = folder / relative
    name = Path(relative).name
    if name.startswith(".") and path.suffix == ".wav":
        return _finished_wav(folder, relative, mic_format)
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
                else _finished_track(folder, track, relative, state["plan"]["mic_format"])
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
        early = state.get("early", [])
        died = set(early[index]) if index < len(early) else set()
        known = {track: length for track, length in lengths.items() if length > 0}
        # Recorders that stopped together line up at their ends; one that died early began with the others.
        together = {track: length for track, length in known.items() if track not in died}
        reference = next((track for track in TRACK_ORDER if track in together), None)
        starts = {track: 0.0 for track in final}
        events = _native_events(folder, index + 1) if state["plan"].get("engine") == "native" else []
        problems.extend(f"part {index + 1}: {lost}" for lost in _native_lost(events))
        walls = {track: wall for track, wall in _native_starts(events).items() if track in final}
        if walls and set(walls) >= set(known):
            # ul-rec timed every track on one clock: exact starts instead of lining up the ends.
            first = min(walls.values())
            starts |= {track: round(wall - first, 3) for track, wall in walls.items()}
            duration = max((starts[track] + length for track, length in known.items()), default=measured)
        elif reference is not None:
            starts |= segment_starts(together, reference)
            duration = together[reference]
        elif known:
            duration = max(known.values())
        else:
            duration = measured
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


def stop_recording(*, force: bool = False, export: dict | None = None) -> dict:
    """Stop all recorders and save the project; a recorder that hangs is reported, not killed."""
    with _locked():
        state = _load_state()
        if state is None:
            raise CaptureError("no active recording", 1)
        if export is not None:
            state["export"] = {**(state["export"] or {}), **export}
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
    return _export_after_stop(state, result)


def _stop_helpers(state: dict) -> None:
    """The menu-bar helper only shows the recording; it is told to quit and never waited for."""
    _signal_all(state["helpers"], signal.SIGTERM)
    state["helpers"] = []


def _export_after_stop(state: dict, result: dict) -> dict:
    """`record --output/--export` and `stop --export`: export right away (outside the recording lock,
    so a new recording can start meanwhile). A failed export keeps the saved project."""
    if state["export"] is None:
        return result
    folder = Path(result["project"])
    overrides = dict(state["export"])
    if state["output"] and state["mode"] != "audio":
        overrides["container"] = Path(state["output"]).suffix[1:].casefold()
    try:
        project = read_project(folder)
        setup, _ = load_setup()
        settings = export_settings(project, setup["export"], overrides)
        path = export_project(folder, settings, Path(state["output"]) if state["output"] else None)
    except (ExportError, ProjectError) as error:
        return {**result, "export_error": str(error)}
    return {**result, "saved": str(path)}


# ---------------------------------------------------------------- projects


def _recent_projects_file() -> Path:
    return storage_path("studio", "recent-projects.json")


def _recent_projects() -> list[str]:
    try:
        data = json.loads(_recent_projects_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in data if isinstance(item, str)] if isinstance(data, list) else []


def remember_project(folder: Path) -> None:
    """Projects opened from elsewhere (a moved folder) stay listed; at most 20."""
    items = [str(folder)] + [item for item in _recent_projects() if item != str(folder)]
    write_json_atomic(_recent_projects_file(), items[:20])


def _project_folders() -> list[Path]:
    root = projects_dir()
    found = [item for item in root.iterdir() if (item / "project.json").is_file()] if root.is_dir() else []
    for item in _recent_projects():
        path = Path(item)
        if (path / "project.json").is_file() and path not in found:
            found.append(path)
    return found


def project_summary(folder: Path) -> dict | None:
    try:
        project = read_project(folder)
    except ProjectError:
        return None
    size = sum(item.stat().st_size for item in (folder / "media").iterdir() if item.is_file()) if (folder / "media").is_dir() else 0
    return {
        "name": project["name"],
        "path": str(folder),
        "created": project["created"],
        "mode": project["mode"],
        "state": project["state"],
        "problems": project["problems"],
        "duration": project["duration"],
        "size": size,
        "tracks": sorted({track for segment in project["segments"] for track in segment["files"]}, key=TRACK_ORDER.index),
        "exports": [item.get("path") for item in project["exports"] if isinstance(item.get("path"), str)],
        "canvas": project["export"]["canvas"],
    }


def list_projects() -> list[dict]:
    items = [summary for folder in _project_folders() if (summary := project_summary(folder))]
    items.sort(key=lambda item: item["created"], reverse=True)
    return items


def find_project(name: str) -> Path:
    """`last`, a project name in the projects folder, or the path of a project folder."""
    if name == "last":
        items = list_projects()
        if not items:
            raise CaptureError("no Studio projects yet; record one with `ul capture record`")
        return Path(items[0]["path"])
    if "/" not in name and (projects_dir() / name / "project.json").is_file():
        return projects_dir() / name
    path = Path(name).expanduser().absolute()
    if (path / "project.json").is_file():
        return path
    if path.name == "project.json" and path.is_file():
        return path.parent
    raise CaptureError(f"no Studio project named {name!r}; see `ul capture projects`")


# Recorded facts a page or a person editing project.json can never change.
_RECORDED_KEYS = ("format", "version", "name", "created", "mode", "state", "problems", "duration", "segments", "exports")


_LANGUAGE = re.compile(r"[a-z]{2,3}(-[A-Za-z]{2,4})?")


def transcribe_project(folder: Path, language: str | None = None, model: str | None = None) -> dict:
    """Subtitles for a project from `ul lm transcribe` (local speech recognition), on the recording's clock.

    Each part is transcribed from its microphone, else from the screen's sound; lines come back as
    {in, out, text} so the Edit tab can lay them over its cuts.
    """
    if language is not None and not _LANGUAGE.fullmatch(language):
        raise CaptureError("--language must be a code such as en or ru")
    if model is not None and (not model.strip() or model.startswith("-") or not model.isprintable() or len(model) > 200):
        raise CaptureError("--model must be a model name")
    ul = os.environ.get("UNLAW_BIN") or shutil.which("ul")
    if not ul:
        raise CaptureError("ul was not found to run ul lm transcribe")
    try:
        project = read_project(folder)
    except ProjectError as error:
        raise CaptureError(str(error), 1) from error
    captions: list[dict] = []
    found_language = None
    elapsed = 0.0
    for segment in project["segments"]:
        begin, elapsed = elapsed, elapsed + segment["duration"]
        files = segment["files"]
        track = "mic" if "mic" in files else "screen" if (segment.get("info", {}).get("screen", {}).get("audio", True) and "screen" in files) else None
        if track is None or segment["duration"] <= 0:
            continue
        argv = [ul, "lm", "transcribe", str(folder / files[track]), "--json"]
        if language:
            argv += ["-l", language]
        if model:
            argv += ["-m", model]
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            lines = (result.stderr or result.stdout).strip().splitlines()
            reason = _plain_text(lines[-1]) if lines else ""
            raise CaptureError(f"ul lm transcribe failed: {reason or 'exit ' + str(result.returncode)}", 1)
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as error:
            raise CaptureError("ul lm transcribe did not answer with JSON", 1) from error
        found_language = found_language or data.get("language")
        offset = begin + segment["starts"].get(track, 0.0)
        for line in data.get("segments") or []:
            text = " ".join(_plain_text(str(line.get("text", ""))).split())[:500]
            try:
                start, end = float(line["start"]) + offset, float(line["end"]) + offset
            except (KeyError, TypeError, ValueError):
                continue
            start, end = max(begin, start), min(begin + segment["duration"], end)
            if text and end > start:
                captions.append({"in": round(start, 3), "out": round(end, 3), "text": text})
    return {"captions": captions, "language": found_language}


def update_project(folder: Path, data: object) -> dict:
    """Save edits (layouts, scenes, sources, sound, events, export choices) and keep what was recorded."""
    if not isinstance(data, dict):
        raise CaptureError("a project must be a JSON object")
    try:
        current = read_project(folder)
        merged = {**current, **{key: value for key, value in data.items() if key not in _RECORDED_KEYS and key != "path"}}
        for key in _RECORDED_KEYS:
            merged[key] = current[key]
        write_project(folder, merged)
    except ProjectError as error:
        raise CaptureError(str(error)) from error
    return merged


def _export_flags(rest: list[str]) -> dict:
    """Export choices from flags; unknown values are refused with the allowed ones."""
    chosen: dict = {}
    for flag, key, allowed, cast in (
        ("--canvas", "canvas", CANVASES, str),
        ("--height", "height", HEIGHTS, int),
        ("--fps", "fps", FPS, int),
        ("--codec", "codec", CODECS, str),
        ("--quality", "quality", QUALITIES, str),
        ("--format", "container", ("mov", "mp4"), str),
    ):
        value = _take(rest, flag)
        if value is None:
            continue
        names = [str(item) for item in allowed]
        if value not in names:
            listing = ", ".join(names[:-1]) + " or " + names[-1] if flag != "--canvas" else ", ".join(names)
            raise CaptureError(f"{flag} must be {'one of ' if flag == '--canvas' else ''}{listing}")
        chosen[key] = cast(value)
    if _flag(rest, "--no-normalize"):
        chosen["normalize"] = False
    elif _flag(rest, "--normalize"):
        chosen["normalize"] = True
    if _flag(rest, "--delete-sources"):
        chosen["delete_sources"] = True
    return chosen


def export_recording(name: str, overrides: dict, output: str | None = None) -> dict:
    folder = find_project(name)
    try:
        project = read_project(folder)
        setup, _ = load_setup()
        settings = export_settings(project, setup["export"], overrides)
        path = export_project(folder, settings, Path(output).expanduser().absolute() if output else None)
    except (ExportError, ProjectError) as error:
        raise CaptureError(str(error), 1) from error
    return {"saved": str(path), "project": str(folder), "settings": settings}


def _export_in_background(arguments: list[str]) -> dict:
    """Re-run the same export detached (the desk does not wait minutes for an HTTP answer)."""
    program = os.environ.get("UNLAW_BIN")
    if not program:
        raise CaptureError("--background needs UNLAW_BIN (run it through ul)", 2)
    log = storage_path("runtime", "export-background.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as stream:
        subprocess.Popen(
            [program, "capture", "export", *arguments],
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
    return {"queued": True}


def doctor() -> dict:
    mac = _backend()
    return {
        "screen": mac.permission_probe()["screen"],
        "app": mac.responsible_app(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "screencapture": shutil.which("screencapture") is not None,
    }


def _doctor_text(info: dict) -> str:
    app = info["app"] or "the app that runs ul"
    lines = [
        f"Screen Recording: {'allowed' if info['screen'] else f'NOT allowed for {app}'}",
        f"ffmpeg: {'found' if info['ffmpeg'] else 'missing (brew install ffmpeg): no camera, microphone track or export'}",
        f"ffprobe: {'found' if info['ffprobe'] else 'missing (comes with ffmpeg)'}",
        f"Permissions belong to the app that starts ul ({app}).",
        "Camera and Microphone are checked when a recording starts; to change them:",
        "  ul capture doctor --open screen|camera|microphone",
    ]
    return "\n".join(lines)


def _projects_text(items: list[dict]) -> str:
    if not items:
        return "No Studio projects yet. Try: ul capture record"
    return "\n".join(
        f"{item['created'][:16].replace('T', ' ')}  {item['state']:<10}  {_clock(item['duration']):>8}"
        f"  {item['size'] / 1e6:8.1f} MB  {item['name']}" + (f"  ({len(item['exports'])} exported)" if item["exports"] else "")
        for item in items
    )


def _modes_text(modes: dict) -> str:
    lines = []
    for name, items in modes.items():
        lines.append(f"{name}:")
        lines += [
            f"  {item['width']}x{item['height']} {float(item['min_fps']):g}-{float(item['max_fps']):g} fps" for item in items
        ] or ["  no modes reported"]
    return "\n".join(lines) or "No cameras."


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
    try:
        folder = find_project(name) if name != "last" else None
    except CaptureError:
        folder = None
    if folder is not None:
        if folder.is_symlink() or folder.parent != projects_dir():
            raise CaptureError("delete only removes projects from the projects folder")
        trash = Path.home() / ".Trash"
        trash.mkdir(exist_ok=True)
        target = _free(trash / folder.name)
        shutil.move(str(folder), target)
        return target
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


def project_media(folder: Path, relative: str) -> Path:
    """A file of a project's media/ or assets/ folder (the Edit tab draws their sound)."""
    parts = Path(relative).parts
    if len(parts) < 2 or parts[0] not in {"media", "assets"}:
        raise CaptureError("the file must be in the project's media or assets folder")
    try:
        path = inside(folder, relative, "file")
    except ProjectError as error:
        raise CaptureError(str(error)) from error
    if not path.is_file():
        raise CaptureError(f"no such file in the project: {relative}")
    return path


def waveform(name: str, bars: int = 400, project: Path | None = None) -> dict:
    """Loudness bars (0..1) of a recording's sound, cached in storage.root/runtime/waves.

    ffmpeg decodes a small mono stream, so an hour of audio stays a few MB. With `project`, `name` is a file
    of that project and up to 20000 bars may be asked for (the Edit tab's timeline zooms in).
    """
    path = project_media(project, name) if project is not None else find_capture(name)
    if project is None and _kind(path) not in {"audio", "video"}:
        raise CaptureError("only recordings have sound")
    most = 20000 if project is not None else 2000
    if not 10 <= bars <= most:
        raise CaptureError(f"--bars must be between 10 and {most}")
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
    # Not a dot name: screencapture refuses hidden file names for screenshots (and still exits 0),
    # which left the desk without a preview.
    handle, name = tempfile.mkstemp(prefix=f"{target.stem}-tmp-", suffix=".jpg", dir=target.parent)
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


def _countdown(seconds: int, *, quiet: bool) -> None:
    for left in range(seconds, 0, -1):
        if not quiet:
            print(f"Recording in {left}…", file=sys.stderr, flush=True)
        time.sleep(1)


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
                line = _describe(info).splitlines()[0]
                if info.get("level_db") is not None:
                    line += f"  mic {info['level_db']:.0f} dB"
                sys.stdout.write("\r" + line[:120] + "   ")
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


def _studio() -> int:
    """`ul capture` in a terminal: the curses studio (capture_tui.py) over this module's functions."""

    def export_defaults(folder: str) -> dict:
        settings = export_settings(read_project(Path(folder)), load_setup()[0]["export"], {})
        return {key: value for key, value in settings.items() if key != "delete_sources"}

    return run_tui(
        {
            "load_setup": load_setup,
            "save_setup": save_setup,
            "status": status,
            "devices": devices,
            "start": lambda: start_recording("screen"),
            "stop": stop_recording,
            "pause": pause_recording,
            "resume": resume_recording,
            "scene": switch_scene,
            "mark": lambda: add_mark(""),
            "last_project": lambda: str(find_project("last")),
            "export_defaults": export_defaults,
            "export": lambda folder, choice: export_recording(folder, choice),
            "export_status": read_export_status,
        }
    )


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
        print(COMMAND_HELP, end="")
        return 0
    try:
        as_json = _flag(args, "--json")
        load_config()  # report a broken config.toml before touching anything
        if not args:
            if not sys.stdin.isatty():
                print(USAGE, end="")
                return 2
            return _studio()
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
            countdown = _number(_take(rest, "--countdown"), "--countdown", 0)
            if rest and not rest[0].startswith("-") and options["output"] is None:
                options["output"] = rest.pop(0)
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            if options.get("camera") and mode != "screen":
                raise CaptureError("--camera adds the camera to a screen recording")
            _countdown(min(countdown, 60), quiet=as_json)
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
            export = _flag(rest, "--export")
            chosen = _export_flags(rest)
            if rest:
                raise CaptureError("stop takes no arguments (only --force and --export with export flags)")
            if chosen and not export:
                raise CaptureError("export flags need --export")
            result = stop_recording(force=force, export=chosen if export else None)
            if result.get("export_error"):
                print(f"unlaw capture: the project was saved, but the export failed: {result['export_error']}", file=sys.stderr)
            _print(result, as_json, _saved_text(result))
            return 0
        if action == "devices":
            modes = _flag(rest, "--modes")
            camera = _take(rest, "--camera")
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            info = devices()
            if not modes and camera is None:
                _print(info, as_json, _devices_text(info))
                return 0
            names = info["cameras"]
            if camera is not None:
                resolved = _resolve(camera, names, "camera")
                names = [resolved] if resolved else []
            info["modes"] = {name: _backend().camera_modes(name, refresh=True) for name in names}
            _print(info, as_json, _modes_text(info["modes"]))
            return 0
        if action == "transcribe":
            language = _take(rest, "--language")
            model = _take(rest, "--model")
            if len(rest) != 1 or rest[0].startswith("-"):
                raise CaptureError("usage: ul capture transcribe PROJECT [--language CODE] [--model NAME]")
            data = transcribe_project(find_project(rest[0]), language, model)
            _print(data, as_json, "\n".join(f"{line['in']:8.2f}  {line['text']}" for line in data["captions"]))
            return 0
        if action == "projects":
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            items = list_projects()
            _print(items, as_json, _projects_text(items))
            return 0
        if action == "project":
            set_json = _take(rest, "--set-json")
            remember = _flag(rest, "--remember")
            if len(rest) != 1 or set_json not in (None, "-"):
                raise CaptureError("usage: ul capture project NAME|PATH|last [--set-json -] [--remember]")
            folder = find_project(rest[0])
            if set_json == "-":
                try:
                    data = json.loads(sys.stdin.read())
                except ValueError as error:
                    raise CaptureError(f"not JSON: {error}") from error
                update_project(folder, data)
            if remember:
                remember_project(folder)
            try:
                project = read_project(folder)
            except ProjectError as error:
                raise CaptureError(str(error), 1) from error
            summary = project_summary(folder) or {}
            _print({**project, "path": str(folder), "size": summary.get("size", 0)}, as_json, _projects_text([summary]))
            return 0
        if action == "export":
            if _flag(rest, "--status"):
                if rest:
                    raise CaptureError(f"unexpected argument: {rest[0]}")
                info = read_export_status()
                text = f"{info.get('phase', 'idle')} {info.get('percent', '')}% {info.get('output') or info.get('error') or ''}".strip()
                _print(info, as_json, text)
                return 0
            background = _flag(rest, "--background")
            arguments = list(rest)
            output = _take(rest, "--output")
            chosen = _export_flags(rest)
            if len(rest) != 1 or rest[0].startswith("-"):
                raise CaptureError(
                    "usage: ul capture export NAME|PATH|last [--canvas C] [--height H] [--fps F] [--codec C] "
                    "[--quality Q] [--format mov|mp4] [--no-normalize] [--delete-sources] [--output PATH] [--background]"
                )
            if background:
                folder = find_project(rest[0])
                arguments[arguments.index(rest[0])] = str(folder)
                write_json_atomic(
                    storage_path("runtime", "export.json"),
                    {"project": str(folder), "phase": "queued", "percent": 0, "eta": None, "output": None, "error": None},
                )
                info = _export_in_background(arguments)
                _print(info, as_json, "Export started; see `ul capture export --status`.")
                return 0
            if not as_json and sys.stderr.isatty():
                print("Exporting… (ul capture export --status shows the progress)", file=sys.stderr, flush=True)
            result = export_recording(rest[0], chosen, output)
            _print(result, as_json, f"Saved: {result['saved']}")
            return 0
        if action == "setup":
            set_json = _take(rest, "--set-json")
            reset = _flag(rest, "--reset")
            if rest or set_json not in (None, "-"):
                raise CaptureError("usage: ul capture setup [--set-json -] [--reset]")
            try:
                if reset:
                    save_setup(default_setup(_settings()))
                elif set_json == "-":
                    try:
                        data = json.loads(sys.stdin.read())
                    except ValueError as error:
                        raise CaptureError(f"not JSON: {error}") from error
                    save_setup(data)
                setup, warnings = load_setup()
            except ProjectError as error:
                raise CaptureError(str(error)) from error
            for warning in warnings:
                print(f"Note: {warning}", file=sys.stderr)
            _print(setup, as_json, json.dumps(setup, indent=2, ensure_ascii=False))
            return 0
        if action == "doctor":
            kind = _take(rest, "--open")
            if rest:
                raise CaptureError(f"unexpected argument: {rest[0]}")
            if kind is not None:
                if kind not in ("screen", "camera", "microphone"):
                    raise CaptureError("--open takes screen, camera or microphone")
                subprocess.run(["open", _backend().settings_url(kind)], check=False)
            info = doctor()
            _print(info, as_json, _doctor_text(info))
            return 0
        if rest and action in {"pause", "resume", "status"}:
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
            project = _take(rest, "--project")
            if len(rest) != 1:
                raise CaptureError("usage: ul capture wave <name|last|path> [--bars N] [--project P]")
            data = waveform(rest[0], bars, find_project(project) if project else None)
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
