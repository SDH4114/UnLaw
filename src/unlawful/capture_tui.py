"""The terminal studio of `ul capture`: a full-screen curses view over the same recording engine.

`render_frame` and `tui_action` are pure (tested without a terminal); `run_tui` draws them with curses
and calls the engine through the functions it is given, so this module never imports the CLI.
Quitting never stops a recording.
"""

from __future__ import annotations

import curses
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .capture_project import CANVASES, CODECS, FPS, HEIGHTS, ProjectError, canvas_size

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
