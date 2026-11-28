"""JSON Canvas files for `ul desk` (https://jsoncanvas.org/spec/1.0/).

Nodes and edges are Obsidian Canvas's own. Freehand drawings and shapes live in the same file
under the extra top-level key "unlaw", which Obsidian ignores. Every key that is not checked
here (on nodes, edges, elements and the top level) is kept exactly as it was read.
"""

# ruff: noqa: TRY004  (every bad input is a ValueError for the HTTP layer)
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import os
import re
import socket
import ssl
import tempfile
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from .kanban import version_of

NEW_CANVAS = {"nodes": [], "edges": []}
NODE_TYPES = {"text", "file", "link", "group"}
ELEMENT_TYPES = {
    "freedraw",
    "rectangle",
    "ellipse",
    "diamond",
    "line",
    "arrow",
    "text",
    "paint",
}
# paint = an area left by the fill tool: outer ring in points, optional holes.
POINT_TYPES = {"freedraw", "line", "arrow", "paint"}
MAX_STROKE_WIDTH = 100
MAX_ELEMENTS = 20000
MAX_NODES = 20000
MAX_EDGES = 20000
MAX_POINTS = 200000
MAX_CANVAS_TEXT = 20000
COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def _canvas_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _text(value: object, what: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{what}: text must be a string")
    if len(value) > MAX_CANVAS_TEXT:
        raise ValueError(f"{what}: text is longer than {MAX_CANVAS_TEXT} characters")


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


MAX_LAYER_NAME = 200
MAX_THREAD_POINTS = 64


def _hidden(item: dict, what: str) -> None:
    """unlawHidden: the eye of the Layers panel; unlawName: the name given in it (Obsidian ignores both keys)."""
    if "unlawHidden" in item and not isinstance(item["unlawHidden"], bool):
        raise ValueError(f"{what}: unlawHidden must be true or false")
    if "unlawName" in item:
        name = item["unlawName"]
        if not isinstance(name, str) or not name.strip() or len(name) > MAX_LAYER_NAME:
            raise ValueError(f"{what}: unlawName must be 1-{MAX_LAYER_NAME} characters")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            raise ValueError(f"{what}: unlawName must not contain control characters")


def _validate_node(node: dict) -> None:
    what = f"node {node['id']!r}"
    _hidden(node, what)
    if node.get("type") not in NODE_TYPES:
        raise ValueError(f"{what}: type must be one of {', '.join(sorted(NODE_TYPES))}")
    for key in ("x", "y", "width", "height"):
        if not _canvas_number(node.get(key)):
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
    # The spot of the card an end is tied to (thread tool), as fractions of the card box.
    for key in ("unlawFrom", "unlawTo"):
        spot = edge.get(key)
        if key in edge and not (
            isinstance(spot, list) and len(spot) == 2 and all(_canvas_number(v) and 0 <= v <= 1 for v in spot)
        ):
            raise ValueError(f"{what}: {key} must be [x, y] with numbers 0-1")
    # Pins the thread passes on its way, in canvas coordinates (Obsidian draws the edge straight).
    if "unlawPoints" in edge:
        points = edge["unlawPoints"]
        if not (
            isinstance(points, list)
            and len(points) <= MAX_THREAD_POINTS
            and all(isinstance(p, list) and len(p) == 2 and all(_canvas_number(v) for v in p) for p in points)
        ):
            raise ValueError(f"{what}: unlawPoints must be at most {MAX_THREAD_POINTS} [x, y] points")


def _validate_element(element: dict) -> int:
    """Check one drawing element; returns how many points it has."""
    what = f"element {element['id']!r}"
    _hidden(element, what)
    kind = element.get("type")
    if kind not in ELEMENT_TYPES:
        raise ValueError(
            f"{what}: type must be one of {', '.join(sorted(ELEMENT_TYPES))}"
        )
    for key in ("x", "y", "width", "height"):
        if not _canvas_number(element.get(key)):
            raise ValueError(f"{what}: {key} must be a number")
    if "angle" in element and not _canvas_number(element["angle"]):
        raise ValueError(f"{what}: angle must be a number")
    if "stroke" in element and not (
        isinstance(element["stroke"], str) and COLOR.fullmatch(element["stroke"])
    ):
        raise ValueError(f"{what}: stroke must look like #rrggbb")
    fill = element.get("fill")
    if fill is not None and not (isinstance(fill, str) and COLOR.fullmatch(fill)):
        raise ValueError(f"{what}: fill must be #rrggbb or null")
    width = element.get("strokeWidth")
    if "strokeWidth" in element and not (
        _canvas_number(width) and 1 <= width <= MAX_STROKE_WIDTH
    ):
        raise ValueError(f"{what}: strokeWidth must be 1-{MAX_STROKE_WIDTH}")
    rough = element.get("roughness")
    if "roughness" in element and not (_canvas_number(rough) and 0 <= rough <= 2):
        raise ValueError(f"{what}: roughness must be 0-2")
    if "seed" in element and (
        isinstance(element["seed"], bool) or not isinstance(element["seed"], int)
    ):
        raise ValueError(f"{what}: seed must be an integer")
    size = element.get("fontSize")
    if "fontSize" in element and not (_canvas_number(size) and 8 <= size <= 200):
        raise ValueError(f"{what}: fontSize must be 8-200")
    if kind == "text" or "text" in element:
        if "text" not in element:
            raise ValueError(f"{what}: text is missing")
        _text(element["text"], what)
    count = 0
    if kind in POINT_TYPES or "points" in element:
        count = _points(element.get("points"), f"{what}: points")
    if "holes" in element:
        holes = element["holes"]
        if not isinstance(holes, list):
            raise ValueError(f"{what}: holes must be a list of point lists")
        for ring in holes:
            count += _points(ring, f"{what}: holes")
    return count


def _points(points: object, what: str) -> int:
    if not isinstance(points, list):
        raise ValueError(f"{what} must be a list of [x, y]")
    for point in points:
        if not (
            isinstance(point, list)
            and len(point) == 2
            and all(_canvas_number(value) for value in point)
        ):
            raise ValueError(f"{what} must be a list of [x, y] numbers")
    return len(points)


def _validate_unlaw(extra: object) -> None:
    if not isinstance(extra, dict):
        raise ValueError("unlaw must be an object")
    if extra.get("version") != 1 or isinstance(extra.get("version"), bool):
        raise ValueError("unlaw.version must be 1")
    background = extra.get("background")
    if "background" in extra and not (
        isinstance(background, str) and COLOR.fullmatch(background)
    ):
        raise ValueError("unlaw.background must look like #rrggbb")
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


# ---- link cards: a page's title, description and picture, fetched once by the desk server ----
# Only public addresses (no localhost, LAN, link-local, metadata services): a canvas from someone else could
# otherwise make the desk probe this Mac's network. The connection goes to the address that was checked, so a
# second DNS answer cannot swap it, and every redirect is checked again.
LINK_TIMEOUT = 5
LINK_MAX_PAGE = 1024 * 1024
LINK_MAX_IMAGE = 5 * 1024 * 1024
LINK_REDIRECTS = 3
LINK_DEADLINE = 15  # seconds for one page or picture, redirects included
LINK_MAX_ICON = 1024 * 1024
PREVIEW_FOLDER = "attachments/.previews"


# Networks `ipaddress.is_global` still calls global but that lead back inside: IPv4-compatible IPv6, NAT64
# (64:ff9b::/96 wraps any IPv4, 127.0.0.1 included) and the old site-local block.
_INNER_NETWORKS = tuple(ipaddress.ip_network(net) for net in ("::/96", "64:ff9b::/96", "64:ff9b:1::/48", "fec0::/10"))


def _allowed(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return _allowed(address.ipv4_mapped)
        if any(address in network for network in _INNER_NETWORKS):
            return False
    return address.is_global and not address.is_multicast


def _public_address(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Unknown host {host}") from error
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if _allowed(address):
            return str(address)
    raise ValueError(f"{host} is not a public address")


class _PinnedHTTP(http.client.HTTPConnection):
    """Connects to the address that was checked, whatever DNS says the second time."""

    def __init__(self, host: str, port: int, address: str) -> None:
        super().__init__(host, port, timeout=LINK_TIMEOUT)
        self.address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self.address, self.port), LINK_TIMEOUT)


class _PinnedHTTPS(_PinnedHTTP):
    default_port = 443

    def connect(self) -> None:
        super().connect()
        self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)


def _read_until(response: http.client.HTTPResponse, limit: int, deadline: float) -> bytes:
    """At most `limit` bytes, and never past `deadline`: a server dripping a byte at a time cannot hold the desk."""
    parts, size = [], 0
    while size < limit:
        if time.monotonic() > deadline:
            raise ValueError("The page took too long")
        chunk = response.read1(min(65536, limit - size)) if hasattr(response, "read1") else response.read(min(65536, limit - size))
        if not chunk:
            break
        parts.append(chunk)
        size += len(chunk)
    return b"".join(parts)


def _fetch_public(url: str, limit: int) -> tuple[str, str, bytes, dict[str, str]]:
    """GET an http(s) URL from a public address: (final URL, content type, at most `limit` bytes, the headers
    that say whether the page may be framed)."""
    deadline = time.monotonic() + LINK_DEADLINE
    for _ in range(LINK_REDIRECTS + 1):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Only http and https links have a preview")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        kind = _PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP
        connection = kind(parts.hostname, port, _public_address(parts.hostname, port))
        try:
            target = (parts.path or "/") + ("?" + parts.query if parts.query else "")
            connection.request("GET", target, headers={
                "Host": parts.netloc.rsplit("@", 1)[-1],
                "User-Agent": "Mozilla/5.0 (Macintosh) unlaw-desk",
                "Accept": "text/html,application/xhtml+xml,image/*;q=0.8,*/*;q=0.5",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urllib.parse.urljoin(url, response.getheader("Location") or "")
                continue
            if response.status != 200:
                raise ValueError(f"The page answered {response.status}")
            body = _read_until(response, limit, deadline)
            headers = {name: ", ".join(response.headers.get_all(name) or []) for name in ("x-frame-options", "content-security-policy")}
            return url, (response.getheader("Content-Type") or "").split(";")[0].strip().lower(), body, headers
        except (OSError, http.client.HTTPException) as error:
            raise ValueError(f"Could not reach {parts.hostname}: {error}") from error
        finally:
            connection.close()
    raise ValueError("Too many redirects")


def _page_meta(raw: bytes, charset_hint: str = "") -> dict:
    """<title> and the og:/twitter: tags of a page."""
    text = raw.decode(charset_hint or "utf-8", errors="replace")
    found = re.search(r"""<meta[^>]+charset=["']?([\w-]+)""", text[:4096], re.I)
    if found and not charset_hint:
        try:
            text = raw.decode(found[1], errors="replace")
        except LookupError:
            pass

    class Meta(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.meta: dict[str, str] = {}
            self.icons: list[tuple[str, str, str]] = []  # (rel, href, sizes) of <link rel=...icon...>
            self.title: list[str] = []
            self.in_title = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            values = {key.lower(): value or "" for key, value in attrs}
            if tag == "title":
                self.in_title = True
            elif tag == "meta":
                name = (values.get("property") or values.get("name") or "").lower()
                if name and "content" in values:
                    self.meta.setdefault(name, values["content"])
            elif tag == "link" and "icon" in values.get("rel", "").lower() and values.get("href") and len(self.icons) < 50:
                self.icons.append((values["rel"].lower(), values["href"], values.get("sizes", "")))

        def handle_endtag(self, tag: str) -> None:
            if tag == "title":
                self.in_title = False

        def handle_data(self, data: str) -> None:
            if self.in_title:
                self.title.append(data)

    parser = Meta()
    try:
        parser.feed(text)
    except Exception:  # noqa: BLE001  (a broken page still gives what was read)
        pass
    meta = parser.meta
    return {
        "title": meta.get("og:title") or meta.get("twitter:title") or "".join(parser.title),
        "description": meta.get("og:description") or meta.get("twitter:description") or meta.get("description") or "",
        "image": meta.get("og:image") or meta.get("og:image:url") or meta.get("twitter:image") or "",
        "icon": _best_icon(parser.icons),
    }


def _best_icon(icons: list[tuple[str, str, str]]) -> str:
    """The site's logo: the biggest apple-touch-icon (made for home screens, so it is large and square), else the
    biggest other icon that is not SVG (the card draws pictures only); empty means /favicon.ico."""

    def size(sizes: str) -> int:
        found = re.findall(r"(\d+)x\d+", sizes)
        return max((int(value) for value in found), default=0)

    usable = [(rel, href, sizes) for rel, href, sizes in icons if not href.lower().split("?")[0].endswith(".svg")]
    for wanted in (lambda rel: "apple-touch-icon" in rel, lambda rel: True):
        picked = [icon for icon in usable if wanted(icon[0])]
        if picked:
            return max(picked, key=lambda icon: size(icon[2]))[1]
    return ""


def frameable(headers: dict[str, str]) -> bool:
    """Whether a browser will show the page inside the desk: X-Frame-Options or a CSP frame-ancestors list that
    does not let any http page in (the desk is http://127.0.0.1) means no."""
    if headers.get("x-frame-options", "").strip():
        return False
    for policy in headers.get("content-security-policy", "").split(","):
        for directive in policy.split(";"):
            words = directive.split()
            if words and words[0].lower() == "frame-ancestors":
                return any(word in ("*", "http:") for word in words[1:])
    return True


# The picture's own first bytes say what it is (a server's Content-Type is often wrong for icons).
PICTURE_MAGIC = ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"), (b"\x00\x00\x01\x00", ".ico"))


def _picture_suffix(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return next((suffix for magic, suffix in PICTURE_MAGIC if data.startswith(magic)), None)


def _save_picture(url: str, limit: int, folder: Path) -> str | None:
    """Download a picture of a page into `folder`/attachments/.previews (named by its hash, so the same logo is
    kept once); its path relative to the canvas, or None when it is missing or not a picture."""
    try:
        _, _, picture, _ = _fetch_public(url, limit)
    except ValueError:
        return None
    suffix = _picture_suffix(picture)
    if suffix is None:
        return None
    name = hashlib.sha256(picture).hexdigest()[:16] + suffix
    target = folder / PREVIEW_FOLDER / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_name("." + name + ".part")
        temporary.write_bytes(picture)
        os.replace(temporary, target)
    return f"{PREVIEW_FOLDER}/{name}"


def _clean_line(text: str, limit: int) -> str:
    return " ".join("".join(char for char in text if char.isprintable() or char.isspace()).split())[:limit]


def link_preview(url: object, folder: Path) -> dict:
    """{title, description, site, image, icon, frameable}: image (the page's picture) and icon (the site's logo)
    are saved under `folder`/attachments/.previews (so the card works offline), as paths relative to the canvas,
    or None; frameable says whether the page can be shown inside the desk."""
    if not isinstance(url, str) or len(url) > 4000:
        raise ValueError("url must be a link")
    final, kind, body, headers = _fetch_public(url.strip(), LINK_MAX_PAGE)
    site = urllib.parse.urlsplit(final).hostname or ""
    page = kind in ("text/html", "application/xhtml+xml", "")
    meta = _page_meta(body) if page else {"title": "", "description": "", "image": "", "icon": ""}
    image = _save_picture(urllib.parse.urljoin(final, meta["image"]), LINK_MAX_IMAGE, folder) if meta["image"] else None
    icon = _save_picture(urllib.parse.urljoin(final, meta["icon"] or "/favicon.ico"), LINK_MAX_ICON, folder)
    return {
        "title": _clean_line(meta["title"], 300) or site,
        "description": _clean_line(meta["description"], 600),
        "site": site,
        "image": image,
        "icon": icon,
        "frameable": page and frameable(headers),
    }
