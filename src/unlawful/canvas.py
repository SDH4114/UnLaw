"""JSON Canvas files for `ul desk` (https://jsoncanvas.org/spec/1.0/).

Nodes and edges are Obsidian Canvas's own. Freehand drawings and shapes live in the same file
under the extra top-level key "unlaw", which Obsidian ignores. Every key that is not checked
here (on nodes, edges, elements and the top level) is kept exactly as it was read.
"""

# ruff: noqa: TRY004  (every bad input is a ValueError for the HTTP layer)
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path

from .kanban import version_of

NEW_CANVAS = {"nodes": [], "edges": []}
NODE_TYPES = {"text", "file", "link", "group"}
ELEMENT_TYPES = {"freedraw", "rectangle", "ellipse", "diamond", "line", "arrow", "text"}
POINT_TYPES = {"freedraw", "line", "arrow"}
MAX_ELEMENTS = 20000
MAX_NODES = 20000
MAX_EDGES = 20000
MAX_POINTS = 200000
MAX_TEXT = 20000
COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def _number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _text(value: object, what: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{what}: text must be a string")
    if len(value) > MAX_TEXT:
        raise ValueError(f"{what}: text is longer than {MAX_TEXT} characters")


def _id(item: object, what: str, seen: set[str]) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"{what} must be an object")
    key = item.get("id")
    if not isinstance(key, str) or not key:
        raise ValueError(f"{what}: id must be a non-empty string")
    if key in seen:
        raise ValueError(f"{what}: duplicate id {key!r}")
    seen.add(key)
    return item


def _validate_node(node: dict) -> None:
    what = f"node {node['id']!r}"
    if node.get("type") not in NODE_TYPES:
        raise ValueError(f"{what}: type must be one of {', '.join(sorted(NODE_TYPES))}")
    for key in ("x", "y", "width", "height"):
        if not _number(node.get(key)):
            raise ValueError(f"{what}: {key} must be a number")
    if "text" in node:
        _text(node["text"], what)


def _validate_edge(edge: dict) -> None:
    what = f"edge {edge['id']!r}"
    for key in ("fromNode", "toNode"):
        if not isinstance(edge.get(key), str) or not edge[key]:
            raise ValueError(f"{what}: {key} must be a non-empty string")
    if "label" in edge:
        _text(edge["label"], what)


def _validate_element(element: dict) -> int:
    """Check one drawing element; returns how many points it has."""
    what = f"element {element['id']!r}"
    kind = element.get("type")
    if kind not in ELEMENT_TYPES:
        raise ValueError(
            f"{what}: type must be one of {', '.join(sorted(ELEMENT_TYPES))}"
        )
    for key in ("x", "y", "width", "height"):
        if not _number(element.get(key)):
            raise ValueError(f"{what}: {key} must be a number")
    if "angle" in element and not _number(element["angle"]):
        raise ValueError(f"{what}: angle must be a number")
    if "stroke" in element and not (
        isinstance(element["stroke"], str) and COLOR.fullmatch(element["stroke"])
    ):
        raise ValueError(f"{what}: stroke must look like #rrggbb")
    fill = element.get("fill")
    if fill is not None and not (isinstance(fill, str) and COLOR.fullmatch(fill)):
        raise ValueError(f"{what}: fill must be #rrggbb or null")
    width = element.get("strokeWidth")
    if "strokeWidth" in element and not (_number(width) and 1 <= width <= 20):
        raise ValueError(f"{what}: strokeWidth must be 1-20")
    rough = element.get("roughness")
    if "roughness" in element and not (_number(rough) and 0 <= rough <= 2):
        raise ValueError(f"{what}: roughness must be 0-2")
    if "seed" in element and (
        isinstance(element["seed"], bool) or not isinstance(element["seed"], int)
    ):
        raise ValueError(f"{what}: seed must be an integer")
    size = element.get("fontSize")
    if "fontSize" in element and not (_number(size) and 8 <= size <= 200):
        raise ValueError(f"{what}: fontSize must be 8-200")
    if kind == "text" or "text" in element:
        if "text" not in element:
            raise ValueError(f"{what}: text is missing")
        _text(element["text"], what)
    count = 0
    if kind in POINT_TYPES or "points" in element:
        points = element.get("points")
        if not isinstance(points, list):
            raise ValueError(f"{what}: points must be a list of [x, y]")
        for point in points:
            if not (
                isinstance(point, list)
                and len(point) == 2
                and all(_number(value) for value in point)
            ):
                raise ValueError(f"{what}: points must be a list of [x, y] numbers")
        count = len(points)
    return count


def _validate_unlaw(extra: object) -> None:
    if not isinstance(extra, dict):
        raise ValueError("unlaw must be an object")
    if extra.get("version") != 1 or isinstance(extra.get("version"), bool):
        raise ValueError("unlaw.version must be 1")
    elements = extra.get("elements")
    if not isinstance(elements, list):
        raise ValueError("unlaw.elements must be a list")
    if len(elements) > MAX_ELEMENTS:
        raise ValueError(f"unlaw.elements has more than {MAX_ELEMENTS} elements")
    seen: set[str] = set()
    points = 0
    for element in elements:
        points += _validate_element(_id(element, "element", seen))
        if points > MAX_POINTS:
            raise ValueError(f"unlaw.elements has more than {MAX_POINTS} points")


def validate_canvas(data: object) -> dict:
    """The document with `nodes` and `edges` present; ValueError says what is wrong."""
    if not isinstance(data, dict):
        raise ValueError("a canvas must be a JSON object")
    for key, limit in (("nodes", MAX_NODES), ("edges", MAX_EDGES)):
        if key not in data:
            data[key] = []
        if not isinstance(data[key], list):
            raise ValueError(f"{key} must be a list")
        if len(data[key]) > limit:
            raise ValueError(f"{key} has more than {limit} entries")
    seen: set[str] = set()
    for node in data["nodes"]:
        _validate_node(_id(node, "node", seen))
    seen = set()
    for edge in data["edges"]:
        _validate_edge(_id(edge, "edge", seen))
    if "unlaw" in data:
        _validate_unlaw(data["unlaw"])
    return data


def render_canvas(data: dict) -> bytes:
    """Obsidian's layout: tab indentation, real Unicode."""
    return json.dumps(validate_canvas(data), indent="\t", ensure_ascii=False).encode(
        "utf-8"
    )


def parse_canvas(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError(f"the canvas is not UTF-8 text: {error}") from error
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f"the canvas is not valid JSON: {error}") from error
    return validate_canvas(data)


def read_canvas(path: Path) -> tuple[str, dict]:
    """(version, document) of a canvas file; the version is a hash of its bytes."""
    raw = path.read_bytes()
    return version_of(raw), parse_canvas(raw)


def write_canvas(path: Path, data: dict) -> str:
    """Replace the file atomically (temporary file next to it, then rename); returns the new version."""
    raw = render_canvas(data)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=".canvas.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # The temporary file is created 0600; the canvas keeps the mode it had.
        try:
            os.chmod(temporary, path.stat().st_mode & 0o7777)
        except FileNotFoundError:
            pass
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return version_of(raw)
