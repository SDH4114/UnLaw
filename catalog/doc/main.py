# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open, convert and save documents: the formats behind Unlaw.app's Edit and ule."""
from __future__ import annotations

COMMAND_HELP = "Open, convert and save documents: the formats behind Unlaw.app's Edit and ule.\nUsage: ul doc info|read|write|render|pages FILE [options] [--json]\n  info FILE            Kind (text, markdown, image, pdf, document, sheet, database, ...), size,\n                       version and whether it opens as text\n  read FILE            Print a text file (--json adds its version)\n  write FILE --version V\n                       Replace FILE with stdin unless it changed since version V (from info or\n                       read); --version new creates a file that must not exist yet\n  render FILE [--width W] [--page N] [--to M]\n                       A PNG picture of the file W pixels wide (default 1024; 16-4096): images\n                       through sips, PDF pages N..M through PDFKit (at most 500 at once),\n                       everything else through Quick Look; prints the path(s)\n  pages FILE           A PDF's page count and page sizes in points\n  --json               Answer as one JSON line\nSaving never overwrites a change another program made meanwhile: exit 3 (conflict), nothing is\nwritten. Exit codes: 0 ok, 1 failed, 2 wrong call, 3 conflict.\nPictures are cached in <storage.root>/doc/cache (a week, at most 500 MB).\nNeeds macOS sips, qlmanage and osascript (PDFKit) for render. Unlaw.app's Edit and ule call this command; you rarely\nneed it yourself.\nExamples:\n  ul doc info notes.md --json\n  ul doc render photo.heic --width 800\n  ul doc render book.pdf --page 1 --to 20 --width 200 --json\n  ul doc read notes.md --json\n"

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path


# ul doc: the one place that knows file formats. Unlaw.app's Edit and the terminal editor ule
# both call it, so a file opens, converts and saves the same way in both, and a fix to a format
# fixes it everywhere. Standard library plus macOS's own tools (sips, qlmanage) only.
#
# Saving: every write names the version it was based on (sha256[:16] of the bytes, as `info`
# and `read` report it). The file is written to a temporary file in the same folder, fsynced,
# its version is checked again right before os.replace, and the old file's mode is kept, so a
# change made meanwhile by another program is never overwritten: that is exit 3 (conflict).
# Exit codes: 0 ok, 1 failed, 2 wrong call, 3 the file changed since that version.

USAGE = """Usage: ul doc info|read|write|render|pages FILE [options] [--json]
Run `ul doc --help` for details.
"""

TEXT_LIMIT = 50 * 1024 * 1024
RENDER_TIMEOUT = 20
CACHE_DAYS = 7
CACHE_BYTES = 500 * 1024 * 1024
WIDTHS = range(16, 4097)

KINDS: dict[str, tuple[str, ...]] = {
    "markdown": ("md", "markdown", "mdown"),
    "image": (
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "heic",
        "heif",
        "tif",
        "tiff",
        "bmp",
    ),
    "pdf": ("pdf",),
    "document": ("docx", "doc", "rtf", "odt", "pages"),
    "sheet": ("xlsx", "xls", "csv", "tsv", "numbers", "ods"),
    "database": ("sqlite", "sqlite3", "db"),
    "slides": ("pptx", "ppt", "key", "odp"),
    "media": ("mp4", "mov", "m4v", "mp3", "m4a", "wav", "flac", "aac"),
    "archive": ("zip", "7z", "rar", "tar", "gz", "xz", "zst", "dmg"),
}
# Kinds that are text on disk: ule edits them as they are (sheets also get a table view).
TEXT_KINDS = {"text", "markdown"}
TEXT_SHEETS = {"csv", "tsv"}
# Kinds sips draws directly; everything else goes through Quick Look.
SIPS_KINDS = {"image"}


class DocError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def version_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def suffix_kind(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    for kind, suffixes in KINDS.items():
        if suffix in suffixes:
            return kind
    return None


def looks_like_text(head: bytes) -> bool:
    if b"\0" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as error:
        # A multi-byte char cut at the end of the sample is still text.
        return error.start >= len(head) - 3
    return True


def kind_of(path: Path, head: bytes) -> str:
    kind = suffix_kind(path)
    if kind is not None:
        return kind
    # No NUL byte: text, even in an old encoding (then it does not open as text: ule edits UTF-8).
    return "binary" if b"\0" in head else "text"


def checked_file(raw: str) -> Path:
    if not raw or "\0" in raw:
        raise DocError("no file given", 2)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if path.is_dir():
        raise DocError(f"{path} is a folder", 1)
    return path


def info(path: Path) -> dict:
    try:
        stat = path.stat()
        with path.open("rb") as handle:
            head = handle.read(8192)
    except FileNotFoundError:
        raise DocError(f"{path} does not exist") from None
    except OSError as error:
        raise DocError(f"{path}: {error.strerror or error}") from None
    kind = kind_of(path, head)
    text = kind in TEXT_KINDS or (
        kind == "sheet" and path.suffix.lower().lstrip(".") in TEXT_SHEETS
    )
    utf8 = looks_like_text(head)
    data = None if stat.st_size > TEXT_LIMIT else path.read_bytes()
    return {
        "path": str(path),
        "name": path.name,
        "kind": kind,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "version": version_of(data) if data is not None else None,
        "text": text and utf8 and stat.st_size <= TEXT_LIMIT,
        "utf8": utf8,
        "writable": os.access(path, os.W_OK),
    }


def read_text(path: Path) -> dict:
    meta = info(path)
    if not meta["utf8"] and meta["kind"] in TEXT_KINDS:
        raise DocError(f"{path.name} is not UTF-8 text")
    if not meta["text"]:
        raise DocError(f"{path.name} is not a text file ({meta['kind']})")
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise DocError(f"{path.name} is not UTF-8 text") from None
    return {**meta, "version": version_of(data), "text": text}


def write_bytes(path: Path, data: bytes, expected: str | None) -> str:
    """Replaces the file with `data` unless it changed since `expected`; returns the new version."""
    exists = path.exists()
    if exists and expected is None:
        raise DocError(f"{path.name} exists: pass --version to replace it", 2)
    if not exists and expected not in (None, "new"):
        raise DocError(f"{path.name} no longer exists", 3)

    def current() -> str | None:
        try:
            return version_of(path.read_bytes())
        except FileNotFoundError:
            return None

    if exists and current() != expected:
        raise DocError(f"{path.name} changed since it was opened", 3)
    folder = path.parent
    if not folder.is_dir():
        raise DocError(f"{folder} does not exist")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=folder, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if exists:
            os.chmod(temporary, path.stat().st_mode & 0o7777)
            # Checked again right before the swap: another program may have saved meanwhile.
            if current() != expected:
                raise DocError(
                    f"{path.name} changed while saving; nothing was written", 3
                )
            os.replace(temporary, path)
        else:
            # A new file never replaces one that appeared meanwhile.
            os.link(temporary, path)
            temporary.unlink()
        temporary = None
    except FileExistsError:
        raise DocError(
            f"{path.name} appeared while saving; nothing was written", 3
        ) from None
    except PermissionError:
        raise DocError(f"no permission to write {path}") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return version_of(data)


def storage() -> Path:
    root = os.environ.get("UNLAW_STORAGE")
    return Path(root) if root else Path(tempfile.gettempdir()) / "unlaw-doc"


def cache_dir() -> Path:
    folder = storage() / "doc" / "cache"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def sweep_cache(folder: Path) -> None:
    """Drops pictures older than a week, then the oldest until the folder is under its cap."""
    now = time.time()
    entries = []
    for entry in folder.iterdir():
        try:
            stat = entry.stat()
        except OSError:
            continue
        if not entry.is_file():
            continue
        if now - stat.st_mtime > CACHE_DAYS * 86400:
            entry.unlink(missing_ok=True)
        else:
            entries.append((stat.st_mtime, stat.st_size, entry))
    total = sum(size for _, size, _ in entries)
    for _, size, entry in sorted(entries):
        if total <= CACHE_BYTES:
            break
        entry.unlink(missing_ok=True)
        total -= size


def tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise DocError(f"{name} was not found (it ships with macOS)")
    return found


# PDF pages through PDFKit in JavaScript for Automation: one osascript run answers a whole
# request (sizes, or several pages drawn), because each start costs ~0.2 s. The request is one
# JSON argument (argv, never script source). Answers are one JSON line.
PDF_SCRIPT = r"""
ObjC.import('Foundation'); ObjC.import('AppKit'); ObjC.import('PDFKit');
function run(argv) {
  const request = JSON.parse(argv[0]);
  const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(request.path));
  if (!doc || doc.isNil()) return JSON.stringify({error: 'not a PDF that macOS can read'});
  if (doc.isLocked) return JSON.stringify({error: 'the PDF is locked with a password'});
  const count = Number(doc.pageCount);
  const size = (page) => {
    const box = page.boundsForBox(1);
    const turned = Math.abs(Number(page.rotation)) % 180 === 90;
    const w = turned ? box.size.height : box.size.width, h = turned ? box.size.width : box.size.height;
    return [Math.round(w * 100) / 100, Math.round(h * 100) / 100];
  };
  if (request.sizes) {
    const sizes = [];
    for (let i = 0; i < count; i++) sizes.push(size(doc.pageAtIndex(i)));
    return JSON.stringify({pages: count, sizes});
  }
  const made = [];
  for (const job of request.jobs) {
    if (job.page > count) continue;
    const page = doc.pageAtIndex(job.page - 1);
    const [w, h] = size(page);
    const width = request.width, height = Math.max(1, Math.round(width * h / w));
    const image = page.thumbnailOfSizeForBox($.NSMakeSize(width, height), 1);
    const rep = $.NSBitmapImageRep.imageRepWithData(image.TIFFRepresentation);
    const png = rep.representationUsingTypeProperties(4, $());
    if (!png.writeToFileAtomically(job.out, true)) return JSON.stringify({error: 'could not write ' + job.out});
    made.push(job.page);
  }
  return JSON.stringify({pages: count, made});
}
"""
PDF_PAGES = 500


def pdf_call(request: dict) -> dict:
    try:
        result = subprocess.run(
            [tool("osascript"), "-l", "JavaScript", "-e", PDF_SCRIPT, json.dumps(request)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT * 3,
        )
    except subprocess.TimeoutExpired:
        raise DocError("reading the PDF took too long") from None
    try:
        answer = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise DocError(f"could not read the PDF: {result.stderr.strip() or 'no answer'}") from None
    if not isinstance(answer, dict):
        raise DocError("could not read the PDF")
    if answer.get("error"):
        raise DocError(str(answer["error"]))
    return answer


def pdf_pages(path: Path) -> dict:
    """Page count and every page's size in points (rotation applied), without drawing."""
    if info(path)["kind"] != "pdf":
        raise DocError(f"{path.name} is not a PDF", 2)
    answer = pdf_call({"path": str(path), "sizes": True})
    pages, sizes = answer.get("pages"), answer.get("sizes")
    if not isinstance(pages, int) or not isinstance(sizes, list):
        raise DocError("could not read the PDF")
    return {"pages": pages, "sizes": sizes}


def render_key(path: Path, meta: dict, width: int, page: int) -> str:
    return hashlib.sha256(f"{path}\0{meta['size']}\0{meta['mtime']}\0{width}\0{page}".encode()).hexdigest()[:24]


def render_pdf(path: Path, meta: dict, width: int, first: int, last: int) -> dict:
    """Pages first..last of a PDF, each a cached PNG; only missing ones are drawn (one run)."""
    folder = cache_dir()
    wanted = {page: folder / f"{render_key(path, meta, width, page)}.png" for page in range(first, last + 1)}
    missing = [page for page, target in wanted.items() if not target.exists()]
    pages = None
    if missing:
        sweep_cache(folder)
        with tempfile.TemporaryDirectory(dir=folder, prefix=".render-") as work:
            jobs = [{"page": page, "out": str(Path(work) / f"{page}.png")} for page in missing]
            answer = pdf_call({"path": str(path), "width": width, "jobs": jobs})
            pages = answer.get("pages")
            for page in answer.get("made", []):
                if page in wanted:
                    os.replace(Path(work) / f"{page}.png", wanted[page])
    for target in wanted.values():
        if target.exists():
            os.utime(target)
    made = [{"page": page, "png": str(target)} for page, target in wanted.items() if target.exists()]
    if not made:
        raise DocError(f"{path.name} has no page {first}")
    result = {"png": made[0]["png"], "pngs": made, "kind": "pdf", "cached": not missing}
    if pages is not None:
        result["pages"] = pages
    return result


def render(path: Path, width: int, page: int, last: int | None = None) -> dict:
    """A PNG of the file `width` pixels wide (cached by path, size, mtime, width and page).
    A PDF draws page `page` (through `last`, at most PDF_PAGES at once) with PDFKit."""
    meta = info(path)
    if meta["kind"] == "pdf":
        last = page if last is None else last
        if last < page or last - page >= PDF_PAGES:
            raise DocError(f"--to must be from --page to --page + {PDF_PAGES - 1}", 2)
        return render_pdf(path, meta, width, page, last)
    if last not in (None, page):
        raise DocError("--to is for PDF pages", 2)
    key = render_key(path, meta, width, page)
    folder = cache_dir()
    target = folder / f"{key}.png"
    if target.exists():
        os.utime(target)
        return {"png": str(target), "kind": meta["kind"], "cached": True}
    sweep_cache(folder)
    with tempfile.TemporaryDirectory(dir=folder, prefix=".render-") as work:
        work_dir = Path(work)
        if meta["kind"] in SIPS_KINDS:
            made = work_dir / "out.png"
            argv = [
                tool("sips"),
                "-s",
                "format",
                "png",
                "--resampleWidth",
                str(width),
                str(path),
                "--out",
                str(made),
            ]
        else:
            argv = [
                tool("qlmanage"),
                "-t",
                "-s",
                str(width),
                "-o",
                str(work_dir),
                str(path),
            ]
            made = work_dir / f"{path.name}.png"
        try:
            result = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=RENDER_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise DocError(
                f"drawing {path.name} took longer than {RENDER_TIMEOUT} s"
            ) from None
        if result.returncode != 0 or not made.is_file() or made.stat().st_size == 0:
            raise DocError(
                f"could not draw {path.name}: {result.stderr.strip() or 'no picture was made'}"
            )
        os.replace(made, target)
    return {"png": str(target), "kind": meta["kind"], "cached": False}


def option(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    index = args.index(name)
    if index + 1 >= len(args):
        raise DocError(f"{name} needs a value", 2)
    value = args[index + 1]
    del args[index : index + 2]
    return value


def number(text: str | None, name: str, allowed: range, default: int) -> int:
    if text is None:
        return default
    if not text.isdigit() or int(text) not in allowed:
        raise DocError(f"{name} must be {allowed.start}-{allowed.stop - 1}", 2)
    return int(text)


def show(result: dict, as_json: bool, plain: str) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(plain)


def dispatch(args: list[str]) -> int:
    # Options only before `--`: after it every word is a file name, even `--width`.
    files: list[str] = []
    if "--" in args:
        split = args.index("--")
        args, files = args[:split], args[split + 1 :]
    as_json = "--json" in args
    args = [arg for arg in args if arg != "--json"]
    if not args:
        raise DocError("no action given", 2)
    action = args.pop(0)
    version = option(args, "--version")
    width_text = option(args, "--width")
    page_text = option(args, "--page")
    to_text = option(args, "--to")
    unknown = [arg for arg in args if arg.startswith("-")]
    if unknown:
        raise DocError(f"unknown option {unknown[0]}", 2)
    args += files
    if len(args) != 1:
        raise DocError("give exactly one file", 2)
    path = checked_file(args[0])
    if action == "info":
        result = info(path)
        show(
            result,
            as_json,
            f"{result['name']}: {result['kind']}, {result['size']} bytes",
        )
    elif action == "read":
        result = read_text(path)
        if as_json:
            show(result, True, "")
        else:
            sys.stdout.write(result["text"])
    elif action == "write":
        if version is None and path.exists():
            raise DocError(
                "write needs --version (from info or read), or --version new for a new file",
                2,
            )
        data = sys.stdin.buffer.read(TEXT_LIMIT + 1)
        if len(data) > TEXT_LIMIT:
            raise DocError("the text is larger than 50 MB")
        new = write_bytes(path, data, version)
        show({"path": str(path), "version": new}, as_json, f"saved {path.name}")
    elif action == "render":
        width = number(width_text, "--width", WIDTHS, 1024)
        page = number(page_text, "--page", range(1, 100001), 1)
        last = None if to_text is None else number(to_text, "--to", range(1, 100001), page)
        result = render(path, width, page, last)
        show(result, as_json, "\n".join(item["png"] for item in result.get("pngs", [result])))
    elif action == "pages":
        result = pdf_pages(path)
        show(result, as_json, f"{result['pages']} pages")
    else:
        raise DocError(f"unknown action {action!r}", 2)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    before = args[: args.index("--")] if "--" in args else args
    if "-h" in before or "--help" in before or args[:1] == ["help"]:
        print(COMMAND_HELP, end="")
        return 0
    try:
        return dispatch(args)
    except DocError as error:
        print(f"unlaw doc: {error}", file=sys.stderr)
        if error.code == 2:
            print(USAGE, end="", file=sys.stderr)
        return error.code
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
