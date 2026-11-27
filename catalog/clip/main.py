# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Clipboard history in the background: list, search and copy again."""
from __future__ import annotations

COMMAND_HELP = 'Clipboard history in the background: list, search and copy again.\nUsage: ul clip [list [N] [--json] [--short]]\n       ul clip search <words...> [--json] | show <n> | copy <n> | rm <n> | clear [--yes]\n       ul clip on | off | status [--json] | pause | resume\n  list        Newest first (default 20, one-line previews; --short: JSON texts cut at 2000)\n  search      Items that contain every word, any case; numbers stay valid for copy/show/rm\n  copy <n>    Put item n back on the clipboard (it becomes the newest)\n  @<id>       In place of a number for show/copy/rm: the "id" from --json, which stays the\n              same when new copies arrive (numbers shift)\n  show <n>    The full text (control characters escaped on a terminal)\n  clear       Delete all items after a y/N question (--yes skips it)\n  on / off    Install / remove the background watcher (LaunchAgent com.unlaw.clip); off keeps the history\n  pause       The watcher keeps running but ignores copies until `resume`\nText (at most 100 KB per item), pictures (screenshots, "Copy image") and copied files (up to\n200 MB each; folders are skipped) are kept; pictures and files as copies in <storage.root>/clip/files/,\nand only the newest clip.max_files of them (default 15), older ones are deleted. Duplicates move to\nthe top, at most clip.max_items items (default 200); clip.interval (default 1 s) is how often the\npasteboard is checked. copy puts a picture or file back as itself; show prints its path.\nPrivacy: items marked concealed, transient or auto-generated (password managers set these) are\nnever stored. The history is plain text (file mode 0600) in <storage.root>/clip/ and syncs if that\nsits in iCloud/Dropbox; use pause for secrets an app does not mark. Needs macOS osascript; if copies\nstop being stored, `status` shows the newest item and the watcher log.\nExamples: ul clip on\n  ul clip search token\n  ul clip copy 3\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'}, 'clip': {'max_items': 200, 'max_files': 15, 'interval': 1.0}}


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
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path



# ul clip keeps a history of the text you copy. A LaunchAgent (com.unlaw.clip) runs `ul clip _watch`, which starts
# one long-lived `osascript -l JavaScript` helper. The helper reads NSPasteboard through the ObjC bridge, wakes every
# clip.interval seconds, compares changeCount (nothing else is read while it is unchanged) and prints one JSON line
# per change: {"count", "types", "text"}. The pasteboard types let us honour the nspasteboard.org markers that password
# managers set (concealed, transient, auto-generated). pbpaste cannot see types, so it is never used to read.
#
# History: storage.root/clip/history.json, written atomically under a flock (history.lock), mode 0600 in a 0700 folder.
#   {"version": 1, "items": [{"text": str, "time": ISO 8601 with offset}, ...]}   newest first
# Pictures and copied files (4.0.0) are items too, with a copy of their bytes in storage.root/clip/files/<id><suffix>:
#   {"text": shown name, "time": ..., "kind": "image" | "file", "id": 16 hex of the bytes' sha256, "file": "<id><suffix>",
#    "name": original name, "size": bytes}
# Only the newest clip.max_files of those are kept (default 15); a file no item names is deleted.
# Pause flag: the file storage.root/clip/paused.

LABEL = "com.unlaw.clip"
USAGE = (
    "Usage: ul clip [list [N] [--json]] | search WORDS... [--json] | show N | copy N | rm N | clear [--yes]\n"
    "       ul clip on | off | status [--json] | pause | resume\n"
)
DEFAULT_LIST = 20
MAX_BYTES = 100 * 1024
PREVIEW_WIDTH = 80
TEXT_TYPE = "public.utf8-plain-text"
# A copy that carries one of these is never stored. The first three are the nspasteboard.org conventions; the last two
# are older markers of 1Password and of "transient" in other clipboard tools, listed from memory.
PRIVATE_TYPES = frozenset(
    {
        "org.nspasteboard.ConcealedType",
        "org.nspasteboard.TransientType",
        "org.nspasteboard.AutoGeneratedType",
        "com.agilebits.onepassword",
        "de.petermaurer.TransientPasteboardType",
    }
)
# A copied file also puts its name on the pasteboard as plain text; that is a file, not text.
FILE_TYPES = frozenset({"public.file-url"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".heic", ".tiff", ".tif", ".webp", ".bmp"})
MAX_FILE_BYTES = 200 * 1024 * 1024  # a bigger copied file is skipped (the history is a copy, not a backup)
MAX_IMAGE_BYTES = 64 * 1024 * 1024  # a picture's PNG, written by the helper
DEFAULT_MAX_FILES = 15

# Runs inside `osascript -l JavaScript -e SCRIPT interval parent_pid max_chars incoming_dir`. It ends when the watcher
# is gone (parent pid changes), or on a broken pipe. Text longer than max_chars characters (so surely larger than the
# byte limit) is not sent at all. Copied files are sent as paths ("files"); a picture without text (a screenshot,
# "Copy image") is written as PNG into incoming_dir and sent as "image". Nothing is written for a private copy.
HELPER = r"""
ObjC.import('AppKit');
ObjC.import('unistd');
function run(argv) {
  var interval = parseFloat(argv[0]), parent = parseInt(argv[1]), maxChars = parseInt(argv[2]);
  var incoming = argv[3] || "";
  var hidden = ["org.nspasteboard.ConcealedType", "org.nspasteboard.TransientType", "org.nspasteboard.AutoGeneratedType",
    "com.agilebits.onepassword", "de.petermaurer.TransientPasteboardType"];
  var pasteboard = $.NSPasteboard.generalPasteboard;
  var out = $.NSFileHandle.fileHandleWithStandardOutput;
  var last = -1;
  for (;;) {
    var count = Number(pasteboard.changeCount);
    if (count !== last) {
      var line = null;
      try {
        var types = ObjC.deepUnwrap(pasteboard.types) || [];
        var text = null;
        var value = pasteboard.stringForType($.NSPasteboardTypeString);
        if (value && !value.isNil()) {
          text = ObjC.unwrap(value);
          if (text.length > maxChars) text = null;
        }
        var files = null, image = null;
        var secret = types.some(function (type) { return hidden.indexOf(type) >= 0; });
        if (!secret) {
          var items = ObjC.unwrap(pasteboard.pasteboardItems) || [];
          for (var i = 0; i < items.length; i++) {
            var link = items[i].stringForType("public.file-url");
            if (link && !link.isNil()) {
              var url = $.NSURL.URLWithString(link);
              if (url && !url.isNil() && url.isFileURL) (files = files || []).push(ObjC.unwrap(url.path));
            }
          }
          if (!files && text === null && incoming) {
            var data = pasteboard.dataForType("public.png");
            if (!data || data.isNil()) data = pasteboard.dataForType("public.tiff");
            if (data && !data.isNil() && Number(data.length) <= 64 * 1024 * 1024) {
              var picture = $.NSBitmapImageRep.imageRepWithData(data);
              var png = picture && !picture.isNil() ? picture.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $()) : null;
              var path = incoming + "/" + count + ".png";
              if (png && !png.isNil() && png.writeToFileAtomically(path, true)) image = path;
            }
          }
        }
        // Types and text must come from one copy: if the pasteboard changed while they were read (a password
        // manager copying right after another app), the sample is dropped and the same change is read again.
        if (Number(pasteboard.changeCount) === count) {
          line = JSON.stringify({count: count, types: types, text: text, files: files, image: image}) + "\n";
        } else if (image) {
          $.NSFileManager.defaultManager.removeItemAtPathError(image, null);
        }
      } catch (error) {}
      if (line !== null) {
        last = count;
        out.writeData($(line).dataUsingEncoding($.NSUTF8StringEncoding));
      }
    }
    if (Number($.getppid()) !== parent) return;
    delay(interval);
  }
}
"""


# `osascript -l JavaScript -e COPY_FILE_SCRIPT <path> <image|file>`: one pasteboard item with the file's URL (Finder,
# Mail, Messages paste the file) and, for a picture, its pixels too (editors and chats paste the picture).
COPY_FILE_SCRIPT = r"""
ObjC.import('AppKit');
function run(argv) {
  var path = argv[0], picture = argv[1] === "image";
  var item = $.NSPasteboardItem.alloc.init;
  item.setStringForType($.NSURL.fileURLWithPath(path).absoluteString, "public.file-url");
  if (picture) {
    var image = $.NSImage.alloc.initWithContentsOfFile(path);
    if (image && !image.isNil()) item.setDataForType(image.TIFFRepresentation, "public.tiff");
    if (/\.png$/i.test(path)) item.setDataForType($.NSData.dataWithContentsOfFile(path), "public.png");
  }
  var pasteboard = $.NSPasteboard.generalPasteboard;
  pasteboard.clearContents;
  return pasteboard.writeObjects($([item])) ? "ok" : "failed";
}
"""


class ClipError(Exception):
    """A problem the user can fix; `code` is the exit status (2 usage, 1 failure)."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- storage


def clip_dir() -> Path:
    return storage_path("clip")


def history_file() -> Path:
    return clip_dir() / "history.json"


def files_dir() -> Path:
    return clip_dir() / "files"


def incoming_dir() -> Path:
    return clip_dir() / "incoming"


def _private_dir() -> Path:
    directory = clip_dir()
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory


@contextmanager
def _locked() -> Iterator[None]:
    lock = _private_dir() / "history.lock"
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _valid_items(data: object) -> list[dict] | None:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return None
    for item in data["items"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("text"), str)
            or not isinstance(item.get("time"), str)
        ):
            return None
        if "kind" in item and not _valid_file_item(item):
            return None
    return data["items"]


def _valid_file_item(item: dict) -> bool:
    name = item.get("file")
    return (
        item.get("kind") in {"image", "file"}
        and isinstance(item.get("id"), str)
        and isinstance(name, str)
        and name == Path(name).name
        and not name.startswith(".")
        and isinstance(item.get("name"), str)
        and isinstance(item.get("size"), int)
        and not isinstance(item.get("size"), bool)
    )


def _damaged(path: Path) -> ClipError:
    return ClipError(
        f"{path} is damaged; move it away (or run `ul clip clear --yes`) to start a new history"
    )


def _read(repair: bool = False) -> list[dict]:
    """The stored items, newest first. A damaged file is an error, or with `repair` is moved aside first."""
    path = history_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        data = None
    items = _valid_items(data)
    if items is not None:
        return items
    if not repair:
        raise _damaged(path)
    aside = path.with_name(
        f"{path.name}.damaged-{datetime.now().astimezone():%Y%m%d-%H%M%S}"
    )
    os.replace(path, aside)
    print(f"unlaw clip: {path} was damaged; kept as {aside.name}", file=sys.stderr)
    return []


def _write(items: list[dict]) -> None:
    directory = _private_dir()
    handle, temporary = tempfile.mkstemp(prefix=".history.", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "items": items}, stream, ensure_ascii=False)
        os.replace(temporary, history_file())
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _max_items() -> int:
    value = load_config()["clip"]["max_items"]
    return (
        max(1, value) if isinstance(value, int) and not isinstance(value, bool) else 200
    )


def _max_files() -> int:
    value = load_config()["clip"].get("max_files", DEFAULT_MAX_FILES)
    return (
        max(0, value)
        if isinstance(value, int) and not isinstance(value, bool)
        else DEFAULT_MAX_FILES
    )


def _key(item: dict) -> str:
    return item["id"] if item.get("kind") else item["text"]


def _limited(items: list[dict]) -> list[dict]:
    """At most clip.max_items items, of which at most clip.max_files pictures and files (newest kept)."""
    kept, files, most_files = [], 0, _max_files()
    for item in items:
        if item.get("kind"):
            files += 1
            if files > most_files:
                continue
        kept.append(item)
    return kept[: _max_items()]


def _sweep(items: list[dict]) -> None:
    """Delete stored files no item names any more (dropped by the limits, removed, or left by a crash)."""
    named = {item["file"] for item in items if item.get("kind")}
    folder = files_dir()
    if not folder.is_dir():
        return
    for path in folder.iterdir():
        if path.name not in named and path.is_file() and not path.is_symlink():
            path.unlink(missing_ok=True)


def _interval() -> float:
    value = load_config()["clip"]["interval"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 1.0
    return min(60.0, max(0.2, float(value)))


def _to_top(items: list[dict], text: str | dict) -> list[dict]:
    """`text` (or a picture/file item) as the newest item; an older copy of it is dropped, then the limits apply."""
    new = {"text": text, "time": _now()} if isinstance(text, str) else {**text, "time": _now()}
    kept = [item for item in items if _key(item) != _key(new)]
    return _limited([new, *kept])


def _paused() -> bool:
    return (clip_dir() / "paused").exists()


def storable(types: Sequence[object], text: str) -> bool:
    """Plain text only, not blank, within the size limit, not marked private and not a copied file."""
    kinds = set(types)
    if TEXT_TYPE not in kinds or kinds & PRIVATE_TYPES or kinds & FILE_TYPES:
        return False
    if not text.strip():
        return False
    return len(text.encode("utf-8", errors="surrogatepass")) <= MAX_BYTES


def store(text: str) -> None:
    with _locked():
        _write(_to_top(_read(repair=True), text))


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()[:16]


def _suffix(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return suffix if 1 < len(suffix) <= 10 and suffix[1:].isalnum() else ""


def _png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as stream:
            head = stream.read(24)
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def _keep_file(source: Path, name: str, move: bool) -> dict | None:
    """Copy (or move, for the helper's PNG) `source` into files/ under its hash; the item for it, or None."""
    try:
        if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
            return None
        size = source.stat().st_size
        ident = _digest(source)
    except OSError:
        return None
    suffix = _suffix(name)
    folder = files_dir()
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)
    target = folder / f"{ident}{suffix}"
    if not target.exists():
        handle, temporary = tempfile.mkstemp(prefix=".in.", dir=folder)
        os.close(handle)
        try:
            if move:
                os.replace(source, temporary)
            else:
                shutil.copyfile(source, temporary)
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        except OSError:
            Path(temporary).unlink(missing_ok=True)
            return None
    elif move:
        source.unlink(missing_ok=True)
    kind = "image" if suffix in IMAGE_SUFFIXES else "file"
    shown = name
    if kind == "image" and move:
        measured = _png_size(target)
        shown = f"Image {measured[0]}×{measured[1]}" if measured else "Image"
    return {"text": shown, "kind": kind, "id": ident, "file": target.name, "name": name, "size": size}


def store_files(paths: list[str]) -> None:
    """Copied files: each becomes an item (re-copying one of ours from files/ only moves it to the top)."""
    folder = files_dir().resolve()
    with _locked():
        items = _read(repair=True)
        for raw in reversed(paths):  # the first file ends up newest, like the order they were copied in
            source = Path(raw)
            if source.parent.resolve() == folder:
                found = [item for item in items if item.get("file") == source.name]
                if found:
                    items = _to_top(items, found[0])
                continue
            item = _keep_file(source, source.name, move=False)
            if item is not None:
                items = _to_top(items, item)
        _write(items)
        _sweep(items)


def store_image(path: str) -> None:
    """A picture the helper wrote as PNG into incoming/; it moves into files/."""
    source = Path(path)
    if source.parent.resolve() != incoming_dir().resolve():
        return  # only ever the helper's own folder
    with _locked():
        try:
            if source.stat().st_size > MAX_IMAGE_BYTES:
                source.unlink(missing_ok=True)
                return
        except OSError:
            return
        item = _keep_file(source, "Image.png", move=True)
        items = _read(repair=True)
        if item is not None:
            items = _to_top(items, item)
            _write(items)
            _sweep(items)
        source.unlink(missing_ok=True)


# ---------------------------------------------------------------- watcher


def _incoming() -> Path:
    folder = incoming_dir()
    _private_dir()
    folder.mkdir(exist_ok=True)
    folder.chmod(0o700)
    for stale in folder.glob("*.png"):  # left by a watcher that stopped mid-way
        stale.unlink(missing_ok=True)
    return folder


def watch() -> int:
    if shutil.which("osascript") is None:
        raise ClipError(
            "osascript was not found on PATH; the pasteboard cannot be watched without it"
        )
    command = [
        "osascript",
        "-l",
        "JavaScript",
        "-e",
        HELPER,
        f"{_interval():g}",
        str(os.getpid()),
        str(MAX_BYTES),
        str(_incoming()),
    ]
    try:
        helper = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise ClipError(f"could not start osascript: {error}") from error
    try:
        assert helper.stdout is not None
        for line in helper.stdout:
            _handle_change(line)
    finally:
        if helper.poll() is None:
            helper.terminate()
        code = helper.wait()
    if code != 0:
        raise ClipError(
            f"the osascript pasteboard helper stopped with exit code {code}"
        )
    return 0


def _handle_change(line: str) -> None:
    try:
        data = json.loads(line)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    types, text = data.get("types"), data.get("text")
    files, image = data.get("files"), data.get("image")
    if isinstance(image, str) and (_paused() or not isinstance(types, list) or set(types) & PRIVATE_TYPES):
        if Path(image).parent.resolve() == incoming_dir().resolve():
            Path(image).unlink(missing_ok=True)  # never kept, not even for a moment longer
        return
    if isinstance(types, list) and not _paused() and not set(types) & PRIVATE_TYPES:
        try:
            if isinstance(files, list) and files and all(isinstance(path, str) for path in files):
                store_files(files)
                return
            if isinstance(image, str):
                store_image(image)
                return
        except (OSError, ValueError, ConfigError, ClipError) as error:
            print(f"unlaw clip: could not store a copy: {error}", file=sys.stderr)
            return
    if not isinstance(types, list) or not isinstance(text, str) or _paused():
        return
    # Half of a surrogate pair (an app cut an emoji in two) cannot be written as UTF-8: it becomes U+FFFD.
    text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    if not storable(types, text):
        return
    try:
        store(text)
    except (OSError, ValueError, ConfigError, ClipError) as error:
        # One failed write must not end the watcher; the next copy tries again.
        print(f"unlaw clip: could not store a copy: {error}", file=sys.stderr)


# ---------------------------------------------------------------- the launchd job


def _job_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["launchctl", *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ClipError(f"could not run launchctl: {error}") from error


def _target() -> str:
    return f"gui/{os.getuid()}/{LABEL}"


def _write_job() -> Path:
    binary = os.environ.get("UNLAW_BIN", "")
    if not binary:
        raise ClipError(
            "UNLAW_BIN is not set, so the launchd job cannot find ul; run this through `ul clip`"
        )
    if shutil.which("osascript") is None:
        raise ClipError("osascript was not found on PATH; clipboard history needs it")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "XDG_CONFIG_HOME", "UNLAW_PYTHON", "HOME")
        if os.environ.get(key)
    }
    environment.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    log = _private_dir() / "watch.log"
    plist = {
        "Label": LABEL,
        "ProgramArguments": [os.path.abspath(binary), "clip", "_watch"],
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    path = _job_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".clip-plist.", dir=path.parent)
    with os.fdopen(handle, "wb") as stream:
        stream.write(plistlib.dumps(plist))
    os.replace(temporary, path)
    return path


def job_on() -> int:
    path = _write_job()
    _launchctl("bootout", _target())
    result = _launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ClipError(
            f"launchctl bootstrap failed: {detail} (run `ul clip on` to try again)"
        )
    print(
        "Clipboard history is on: every text you copy is kept (until `ul clip off` or `pause`)."
    )
    print(
        f"History: {history_file()} (private, mode 0600). Items marked concealed by password managers are skipped."
    )
    return 0


def job_off() -> int:
    path = _job_path()
    existed = path.exists()
    # The plist goes first: launchd would otherwise restart the job from it right after the bootout.
    path.unlink(missing_ok=True)
    _launchctl("bootout", _target())
    if existed:
        print(
            "Clipboard history is off. The history is kept; `ul clip clear` deletes it."
        )
    else:
        print(
            "The clipboard watcher was not installed. The history is kept; `ul clip clear` deletes it."
        )
    return 0


def _count_text(count: int) -> str:
    return f"{count} item" if count == 1 else f"{count} items"


def status(as_json: bool = False) -> int:
    plain_plist = _job_path().exists()
    if not plain_plist:
        state, job = "off", "off (`ul clip on` starts it)"
    elif _launchctl("print", _target()).returncode == 0:
        state, job = "running", "running"
    else:
        state, job = "not_loaded", "installed but not loaded (`ul clip on` loads it)"
    newest = ""
    count: int | None = None
    try:
        items = _read()
        count = len(items)
        stored = _count_text(count)
        if items:
            newest = _when(items[0])
    except ClipError as error:
        items = []
        stored = f"unreadable ({error})"
    # Whether macOS lets the background helper read the pasteboard cannot be asked directly, so these are the
    # two clues: nothing new for a long time while copying, or osascript errors in the watcher's log.
    log = clip_dir() / "watch.log"
    log_bytes = log.stat().st_size if log.exists() else 0
    if as_json:
        print(
            json.dumps(
                {
                    "watcher": state,
                    "paused": _paused(),
                    "items": count,
                    "newest": items[0]["time"] if items else None,
                    "history": str(history_file()),
                    "files": str(files_dir()),
                    "max_files": _max_files(),
                    "log": str(log),
                    "log_bytes": log_bytes,
                },
                ensure_ascii=False,
            )
        )
        return 0
    print(f"Background watcher: {job}")
    print(f"Recording: {'paused (`ul clip resume`)' if _paused() else 'on'}")
    print(f"History: {stored} in {history_file()}")
    if newest:
        print(f"Newest item: {newest}")
    if log_bytes > 0:
        print(
            f"Watcher log: {log} ({log_bytes} bytes; read it if copies are not being stored)"
        )
    return 0


def set_paused(paused: bool) -> int:
    flag = _private_dir() / "paused"
    if paused:
        flag.touch()
        print("Clipboard history paused: copies are ignored until `ul clip resume`.")
    else:
        flag.unlink(missing_ok=True)
        print("Clipboard history resumed.")
    return 0


# ---------------------------------------------------------------- reading the history


def _escape(text: str, keep: str = "") -> str:
    """Control, format (bidi), separator and unassigned characters as \\n, \\xNN, \\uNNNN, so output cannot drive a terminal."""
    named = {"\n": "\\n", "\t": "\\t", "\r": "\\r"}
    parts: list[str] = []
    for char in text:
        if char in keep:
            parts.append(char)
        elif char in named:
            parts.append(named[char])
        elif unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"}:
            code = ord(char)
            parts.append(
                f"\\x{code:02x}"
                if code < 0x100
                else f"\\u{code:04x}"
                if code < 0x10000
                else f"\\U{code:08x}"
            )
        else:
            parts.append(char)
    return "".join(parts)


def preview(text: str, width: int = PREVIEW_WIDTH) -> str:
    # Escapes make text longer, so take a generous slice first; this also keeps a 100 KB item cheap.
    head = _escape(text[: width * 2])
    return (
        head
        if len(head) <= width and len(text) <= width * 2
        else head[: width - 1] + "…"
    )


def _when(item: dict) -> str:
    try:
        return datetime.fromisoformat(item["time"]).astimezone().strftime("%m-%d %H:%M")
    except ValueError:
        return "?"


def _numbered(items: list[dict]) -> list[tuple[int, dict]]:
    return list(enumerate(items, 1))


# `list --short`: what a list shows of each text. Unlaw.app reads 500 items at once, and full
# texts (up to 100 KB each) made that answer too big to read whole.
SHORT_TEXT = 2000


def _record(n: int, item: dict, short: bool = False) -> dict:
    text = item["text"]
    record = {"n": n, "id": item_key(item), "text": text[:SHORT_TEXT] if short else text, "time": item["time"],
              "kind": item.get("kind", "text")}
    if short and len(text) > SHORT_TEXT:
        record["clipped"] = True
    if item.get("kind"):
        record.update(file=str(files_dir() / item["file"]), name=item["name"], size=item["size"])
    return record


def _shown(item: dict) -> str:
    if item.get("kind") == "image":
        return f"[image] {preview(item['text'])}"
    if item.get("kind") == "file":
        return f"[file] {preview(item['name'])} ({_size(item['size'])})"
    return preview(item["text"])


def _size(count: int) -> str:
    for unit in ("B", "KB", "MB"):
        if count < 1000:
            return f"{count} {unit}"
        count //= 1000
    return f"{count} GB"


def _print_items(pairs: list[tuple[int, dict]], as_json: bool, short: bool = False) -> None:
    if as_json:
        print(json.dumps([_record(n, item, short) for n, item in pairs], ensure_ascii=False))
    else:
        for n, item in pairs:
            print(f"{n:>3}  {_when(item)}  {_shown(item)}")


def list_items(limit: int | None, as_json: bool, short: bool = False) -> int:
    pairs = _numbered(_read())
    if not pairs and not as_json:
        print("The clipboard history is empty (`ul clip on` starts recording).")
        return 0
    _print_items(pairs[: limit if limit is not None else DEFAULT_LIST], as_json, short)
    return 0


def search_items(words: list[str], as_json: bool) -> int:
    needles = [word.casefold() for word in words]
    pairs = [
        (n, item)
        for n, item in _numbered(_read())
        if all(word in item["text"].casefold() for word in needles)
    ]
    if not pairs and not as_json:
        print("No matches.")
        return 0
    _print_items(pairs, as_json)
    return 0


def item_id(text: str) -> str:
    """A name for an item that does not move when new copies arrive (numbers do): a hash of its text."""
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()[:12]


def item_key(item: dict) -> str:
    """The id of any item: a picture or file keeps the hash of its bytes."""
    return item["id"] if item.get("kind") else item_id(item["text"])


def _pick(items: list[dict], text: str) -> int:
    if text.startswith("@"):
        found = [index for index, item in enumerate(items) if item_key(item) == text[1:]]
        if not found:
            raise ClipError(f"no item with id {text[1:]!r} (see `ul clip list --json`)", 2)
        return found[0]
    try:
        number = int(text)
    except ValueError:
        raise ClipError(f"not a number: {text!r}", 2) from None
    if not 1 <= number <= len(items):
        raise ClipError(
            f"no item {number} (the history has {_count_text(len(items))})", 2
        )
    return number - 1


def show_item(text: str) -> int:
    items = _read()
    item = items[_pick(items, text)]
    if item.get("kind"):
        print(files_dir() / item["file"])
        return 0
    shown = item["text"]
    sys.stdout.write(_escape(shown, keep="\n\t") if sys.stdout.isatty() else shown)
    return 0


def _copy_file(item: dict) -> None:
    path = files_dir() / item["file"]
    if not path.is_file():
        raise ClipError(f"the saved copy {path} is gone; `ul clip rm` removes the item")
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", COPY_FILE_SCRIPT, str(path), item["kind"]],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ClipError(f"could not run osascript: {error}") from error
    if result.returncode != 0 or result.stdout.strip() != "ok":
        raise ClipError(f"could not put the file on the clipboard: {result.stderr.strip() or result.stdout.strip()}")


def copy_item(text: str) -> int:
    with _locked():
        items = _read()
        index = _pick(items, text)
        if items[index].get("kind"):
            _copy_file(items[index])
            _write(_to_top(items, items[index]))
            print(f"Copied: {_shown(items[index])}")
            return 0
        chosen = items[index]["text"]
        # pbcopy decodes stdin with the locale; a launchd or bare environment would garble UTF-8.
        env = {**os.environ, "LC_ALL": "en_US.UTF-8"}
        try:
            result = subprocess.run(
                ["pbcopy"],
                input=chosen.encode("utf-8"),
                env=env,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ClipError(f"could not run pbcopy: {error}") from error
        if result.returncode != 0:
            raise ClipError(f"pbcopy failed with exit code {result.returncode}")
        _write(_to_top(items, chosen))
    print(f"Copied: {preview(chosen)}")
    return 0


def remove_item(text: str) -> int:
    with _locked():
        items = _read()
        index = _pick(items, text)
        gone = items.pop(index)
        _write(items)
        _sweep(items)
    print(f"Removed {index + 1}: {_shown(gone)}")
    return 0


def _damaged_copies() -> list[Path]:
    return sorted(clip_dir().glob(f"{history_file().name}.damaged-*"))


def _delete_damaged_copies() -> None:
    for path in _damaged_copies():
        path.unlink(missing_ok=True)


def clear(yes: bool) -> int:
    with _locked():
        count = len(_read(repair=True))
        if count == 0:
            _delete_damaged_copies()
            print("The clipboard history is already empty.")
            return 0
    if not yes:
        # Asked without the lock: the watcher stores copies under it and must not wait for an answer.
        print(
            f"Delete all {_count_text(count)} of clipboard history? [y/N] ",
            end="",
            flush=True,
        )
        answer = sys.stdin.readline()
        if answer.strip().lower() not in {"y", "yes"}:
            if not answer:
                print()
            print("Cancelled; nothing was removed.")
            return 1
    with _locked():
        try:
            count = len(_read())  # copies that arrived while the question was open go too
        except ClipError:
            pass
        history_file().unlink(missing_ok=True)
        _delete_damaged_copies()
        _sweep([])
    print(f"Deleted {_count_text(count)}.")
    return 0


# ---------------------------------------------------------------- command line


def _split(args: list[str], flags: set[str]) -> tuple[list[str], set[str]]:
    words: list[str] = []
    found: set[str] = set()
    for arg in args:
        if arg in flags:
            found.add(arg)
        elif arg.startswith("-"):
            raise ClipError(f"unknown option {arg}", 2)
        else:
            words.append(arg)
    return words, found


def _no_arguments(words: list[str]) -> None:
    if words:
        raise ClipError(f"unexpected argument {words[0]!r}", 2)


def _one(words: list[str], what: str) -> str:
    if len(words) != 1:
        raise ClipError(f"use: ul clip {what} N", 2)
    return words[0]


def _dispatch(args: list[str]) -> int:
    action, rest = (args[0], args[1:]) if args else ("list", [])
    if action == "_watch":
        _no_arguments(rest)
        return watch()
    if action == "list":
        words, flags = _split(rest, {"--json", "--short"})
        if len(words) > 1:
            raise ClipError("use: ul clip list [N] [--json] [--short]", 2)
        limit = None
        if words:
            try:
                limit = int(words[0])
            except ValueError:
                raise ClipError(f"not a number: {words[0]!r}", 2) from None
            if limit < 1:
                raise ClipError("N must be at least 1", 2)
        return list_items(limit, "--json" in flags, "--short" in flags)
    if action == "--json":
        return list_items(None, True)
    if action == "search":
        words, flags = _split(rest, {"--json"})
        if not words:
            raise ClipError("use: ul clip search WORDS...", 2)
        return search_items(words, "--json" in flags)
    if action in {"show", "copy", "rm"}:
        words, _ = _split(rest, set())
        number = _one(words, action)
        return {"show": show_item, "copy": copy_item, "rm": remove_item}[action](number)
    if action == "clear":
        words, flags = _split(rest, {"--yes", "-y"})
        _no_arguments(words)
        return clear(bool(flags))
    if action == "status":
        words, flags = _split(rest, {"--json"})
        _no_arguments(words)
        return status("--json" in flags)
    simple = {
        "on": job_on,
        "off": job_off,
        "pause": lambda: set_paused(True),
    }
    simple["resume"] = lambda: set_paused(False)
    if action in simple:
        _no_arguments(rest)
        return simple[action]()
    raise ClipError(f"unknown command {action!r}", 2)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "-h" in args or "--help" in args or args[:1] == ["help"]:
        print(COMMAND_HELP, end="")
        return 0
    try:
        return _dispatch(args)
    except ClipError as error:
        print(f"unlaw clip: {error}", file=sys.stderr)
        if error.code == 2:
            print(USAGE, end="", file=sys.stderr)
        return error.code
    except ConfigError as error:
        print(f"unlaw clip: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
