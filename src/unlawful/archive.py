from __future__ import annotations

import argparse
import bz2
import getpass
import gzip
import lzma
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from unlawful.command_help import COMMAND_HELP
from unlawful.config import ConfigError, load_config

FORMATS = {
    "zip": ".zip",
    "7z": ".7z",
    "rar": ".rar",
    "tar.zst": ".tar.zst",
    "tar.xz": ".tar.xz",
    "tar.gz": ".tar.gz",
}
FORMAT_ALIASES = {
    "zst": "tar.zst",
    "zstd": "tar.zst",
    "tzst": "tar.zst",
    "xz": "tar.xz",
    "txz": "tar.xz",
    "gz": "tar.gz",
    "tgz": "tar.gz",
}
OUTPUT_SUFFIXES = {
    **{suffix: name for name, suffix in FORMATS.items()},
    ".tzst": "tar.zst",
    ".txz": "tar.xz",
    ".tgz": "tar.gz",
}
# One 0-9 scale for every format, named after the 7-Zip presets.
LEVEL_NAMES = {"store": 0, "fastest": 1, "fast": 3, "normal": 5, "max": 7, "ultra": 9}
# Native settings per level. zstd and gzip have no "store", so 0 means their fastest level;
# zstd 9 uses --ultra -22 with a 128 MiB window, which every zstd decoder accepts by default.
_RAR_LEVELS = (0, 1, 2, 2, 3, 3, 4, 4, 5, 5)
_ZSTD_LEVELS = (1, 1, 3, 6, 9, 12, 15, 17, 19, 22)
# Already-compressed media: stronger levels cost minutes for gains well under 1%.
INCOMPRESSIBLE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".avif", ".mp4", ".m4v", ".mov", ".mkv",
    ".webm", ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".zip", ".7z", ".rar", ".gz", ".tgz",
    ".bz2", ".xz", ".zst", ".dmg", ".pkg", ".ipa", ".apk", ".jar", ".docx", ".xlsx", ".pptx", ".epub", ".woff2",
}
MEDIA_SHARE = 0.9
JUNK_NAMES = {".DS_Store", "__MACOSX", "Thumbs.db", "desktop.ini"}
TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz", ".tar.zst", ".tzst", ".tar.zstd")
ARCHIVE_SUFFIXES = (
    *TAR_SUFFIXES,
    ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".zst", ".cab", ".iso", ".cpio", ".xar", ".lzh", ".arj", ".7z.001", ".zip.001",
)
_STRIPPED_SUFFIXES = {
    ".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".tbz", ".tbz2", ".xz", ".txz", ".zst", ".tzst",
    ".zstd", ".cab", ".iso", ".cpio", ".xar", ".lzh", ".arj", ".dmg", ".001",
}
ACTIONS = {"x": "extract", "extract": "extract", "ls": "list", "test": "test", "c": "create", "create": "create"}


class ArchiveError(Exception):
    pass


def _error(message: str) -> int:
    print(f"unlaw zip: {message}", file=sys.stderr)
    return 1


def _display(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text == home or text.startswith(home + os.sep) else text


def _size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def _is_junk(name: str) -> bool:
    return name in JUNK_NAMES or name.startswith("._")


def _tree_size(paths: Sequence[Path], keep_junk: bool) -> tuple[int, int]:
    """Return the total input size and how much of it is already-compressed media."""
    total = media = 0

    def add(path: str) -> None:
        nonlocal total, media
        try:
            size = os.lstat(path).st_size
        except OSError:
            return
        total += size
        if os.path.splitext(path)[1].lower() in INCOMPRESSIBLE_SUFFIXES:
            media += size

    for path in paths:
        if path.is_symlink() or path.is_file():
            add(str(path))
            continue
        for root, directories, files in os.walk(path):
            if not keep_junk:
                directories[:] = [name for name in directories if not _is_junk(name)]
            for name in files:
                if keep_junk or not _is_junk(name):
                    add(os.path.join(root, name))
    return total, media


def parse_level(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 9:
        return value
    text = str(value).strip().lower()
    if text.isdigit() and 0 <= int(text) <= 9:
        return int(text)
    if text in LEVEL_NAMES:
        return LEVEL_NAMES[text]
    raise ArchiveError(f"Invalid level: {value}. Use 0-9 or {', '.join(LEVEL_NAMES)}")


def level_name(level: int) -> str:
    name = next((name for name, number in LEVEL_NAMES.items() if number == level), None)
    return f"{level} ({name})" if name else str(level)


def _seven_zip() -> str | None:
    return next((found for name in ("7zz", "7z", "7za") if (found := shutil.which(name))), None)


def _progress() -> str:
    return "-bsp1" if sys.stdout.isatty() else "-bsp0"


def _tar() -> str:
    return shutil.which("bsdtar") or shutil.which("tar") or "tar"


def _unique(path: Path, suffix: str | None = None) -> Path:
    if not path.exists() and not path.is_symlink():
        return path
    if suffix is None:
        suffix = "" if path.is_dir() else path.suffix
    base = path.name[: -len(suffix)] if suffix and path.name.endswith(suffix) else path.name
    number = 2
    while True:
        candidate = path.with_name(f"{base} {number}{suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        number += 1


def archive_stem(path: Path) -> str:
    name = path.name
    while True:
        lowered = name.lower()
        match = re.search(r"\.part\d+$", lowered)
        if match:
            name = name[: match.start()]
            continue
        suffix = Path(lowered).suffix
        if suffix not in _STRIPPED_SUFFIXES or len(name) == len(suffix):
            return name or path.name
        name = name[: -len(suffix)]


def looks_like_archive(path: Path) -> bool:
    return path.is_file() and path.name.lower().endswith(ARCHIVE_SUFFIXES)


def normalize_format(value: str) -> str:
    lowered = value.lower().lstrip(".")
    lowered = FORMAT_ALIASES.get(lowered, lowered)
    if lowered not in FORMATS:
        raise ArchiveError(f"Unknown format: {value}. Use one of: {', '.join(FORMATS)}")
    return lowered


def _output_format(output: str) -> str | None:
    lowered = output.lower()
    for suffix in sorted(OUTPUT_SUFFIXES, key=len, reverse=True):
        if lowered.endswith(suffix):
            return OUTPUT_SUFFIXES[suffix]
    return None


def archive_target(sources: Sequence[Path], output: str | None, format_name: str) -> Path:
    suffix = FORMATS[format_name]
    if len(sources) == 1:
        source = sources[0]
        base = source.name if source.is_dir() else (source.stem or source.name)
    else:
        base = "Archive"
    if output:
        target = Path(output).expanduser()
        if target.is_dir() or output.endswith(os.sep):
            target = target / f"{base}{suffix}"
        elif _output_format(target.name) is None:
            target = target.with_name(target.name + suffix)
    else:
        target = (sources[0].parent if len(sources) == 1 else Path.cwd()) / f"{base}{suffix}"
    target = Path(os.path.abspath(target))
    actual_suffix = next(
        (known for known in sorted(OUTPUT_SUFFIXES, key=len, reverse=True) if target.name.lower().endswith(known)),
        suffix,
    )
    return _unique(target, target.name[len(target.name) - len(actual_suffix):])


def _ask_password(confirm: bool) -> str:
    if not sys.stdin.isatty():
        raise ArchiveError("A password needs an interactive terminal.")
    password = getpass.getpass("Archive password: ")
    if not password:
        raise ArchiveError("Password must not be empty.")
    if confirm and getpass.getpass("Repeat password: ") != password:
        raise ArchiveError("Passwords do not match.")
    return password


def create_commands(
    sources: Sequence[Path],
    temporary: Path,
    format_name: str,
    level: int,
    *,
    password: bool,
    keep_junk: bool,
    seven_zip: str | None,
) -> list[list[str]]:
    names = [str(source) for source in sources]
    if format_name in {"zip", "7z"}:
        if seven_zip:
            command = [seven_zip, "a", f"-t{format_name}", f"-mx={level}", "-bso0", _progress(), "-y"]
            if format_name == "zip":
                command.append("-mcu=on")
            else:
                command.extend(["-ms=on", "-mmt=on"])
            if password:
                command.extend(["-p", "-mem=AES256"] if format_name == "zip" else ["-p", "-mhe=on"])
            if not keep_junk:
                command.extend(f"-xr!{pattern}" for pattern in (*sorted(JUNK_NAMES), "._*"))
            return [[*command, str(temporary), *names]]
        if format_name == "7z":
            raise ArchiveError("7z needs 7-Zip. Install: brew install sevenzip")
        if password:
            raise ArchiveError("Encrypted zip needs 7-Zip for AES-256. Install: brew install sevenzip")
        commands = []
        for source in sources:
            command = ["zip", "-r", "-y", "-X", "-q", f"-{level}", str(temporary), source.name]
            if not keep_junk:
                command.extend(["-x", "*.DS_Store", "*/._*", "._*", "*__MACOSX*", "*Thumbs.db", "*desktop.ini"])
            commands.append(command)
        return commands
    if format_name == "rar":
        if not shutil.which("rar"):
            raise ArchiveError("Creating .rar needs the rar tool. Install: brew install --cask rar")
        command = ["rar", "a", f"-m{_RAR_LEVELS[level]}", "-ma5", "-r", "-ep1", "-rr3%", "-idq", "-y"]
        if password:
            command.append("-hp")
        if not keep_junk:
            command.extend(f"-x{pattern}" for pattern in ("*.DS_Store", "*/._*", "._*", "*__MACOSX", "*Thumbs.db", "*desktop.ini"))
        return [[*command, str(temporary), *names]]
    if password:
        raise ArchiveError("tar formats cannot be encrypted; use --format zip, 7z or rar.")
    tar = [_tar(), "-cf", "-" if format_name == "tar.zst" else str(temporary), "--no-mac-metadata"]
    if format_name == "tar.xz":
        tar.extend(["-J", "--options", f"xz:compression-level={level},xz:threads=0"])
    elif format_name == "tar.gz":
        tar.extend(["-z", "--options", f"gzip:compression-level={max(level, 1)}"])
    if not keep_junk:
        for pattern in (*sorted(JUNK_NAMES), "._*"):
            tar.extend(["--exclude", pattern])
    for source in sources:
        tar.extend(["-C", str(source.parent), source.name])
    if format_name == "tar.zst":
        if not shutil.which("zstd"):
            raise ArchiveError("tar.zst needs zstd. Install: brew install zstd")
        native = _ZSTD_LEVELS[level]
        tuning = ["--ultra", f"-{native}", "--long=27"] if native > 19 else [f"-{native}"]
        return [tar, ["zstd", *tuning, "-T0", "-q", "-c"]]
    return [tar]


def _run_create(commands: list[list[str]], format_name: str, temporary: Path, sources: Sequence[Path], password: str | None) -> int:
    environment = {**os.environ, "COPYFILE_DISABLE": "1"}
    if format_name == "tar.zst":
        with temporary.open("xb") as output:
            producer = subprocess.Popen(commands[0], stdout=subprocess.PIPE, env=environment)
            compressor = subprocess.Popen(commands[1], stdin=producer.stdout, stdout=output)
            assert producer.stdout is not None
            producer.stdout.close()
            compressed, archived = compressor.wait(), producer.wait()
        return archived or compressed
    for command, source in zip(commands, sources if len(commands) > 1 else [sources[0]]):
        result = subprocess.run(
            command,
            check=False,
            env=environment,
            cwd=source.parent if command[0] == "zip" else None,
            input=f"{password}\n{password}\n" if password is not None else None,
            text=True if password is not None else None,
        )
        if result.returncode:
            return result.returncode
    return 0


def create(
    paths: Sequence[str],
    *,
    output: str | None,
    format_name: str,
    level: int | None,
    default_level: int,
    password: bool,
    keep_junk: bool,
) -> int:
    sources = [Path(os.path.abspath(Path(path).expanduser())) for path in paths]
    for source in sources:
        if not source.exists() and not source.is_symlink():
            raise ArchiveError(f"Not found: {_display(source)}")
        if source.parent == source:
            raise ArchiveError("Refusing to archive the filesystem root.")
    names = [source.name for source in sources]
    duplicate = next((name for name in names if names.count(name) > 1), None)
    if duplicate:
        raise ArchiveError(f"Two inputs share the name {duplicate!r}; archive them separately or rename one.")
    target = archive_target(sources, output, format_name)
    for source in sources:
        if source.is_dir() and not source.is_symlink() and target.is_relative_to(source):
            raise ArchiveError(f"The archive cannot be written inside the folder being archived: {_display(source)}")
    before, media = _tree_size(sources, keep_junk)
    if level is None:
        level = default_level
        if level > 1 and before and media / before >= MEDIA_SHARE:
            print(
                f"unlaw zip: {media * 100 / before:.0f}% is already-compressed media; using level 1 "
                "because stronger levels only cost time. Pass a level (e.g. -9) to override.",
                file=sys.stderr,
            )
            level = 1
    target.parent.mkdir(parents=True, exist_ok=True)
    # A fresh private directory guarantees 7-Zip/RAR never append to a stale partial archive.
    workspace = Path(tempfile.mkdtemp(prefix=".unlaw-zip-", dir=target.parent))
    temporary = workspace / target.name
    try:
        commands = create_commands(
            sources, temporary, format_name, level, password=password, keep_junk=keep_junk, seven_zip=_seven_zip()
        )
        secret = _ask_password(confirm=True) if password and format_name != "rar" else None
        started = time.perf_counter()
        code = _run_create(commands, format_name, temporary, sources, secret)
        elapsed = time.perf_counter() - started
        if code or not temporary.is_file():
            return _error(f"Could not create {_display(target)} (exit {code or 1}).") if code != 130 else 130
        target = _unique(target, FORMATS[format_name] if target.name.endswith(FORMATS[format_name]) else None)
        os.rename(temporary, target)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    after = target.stat().st_size
    ratio = f" ({after * 100 / before:.0f}%)" if before else ""
    lock = ", encrypted" if password else ""
    print(
        f"Created {_display(target)}  {_size(before)} → {_size(after)}{ratio}"
        f"  level {level_name(level)}, {elapsed:.1f}s{lock}"
    )
    return 0


def detect(path: Path) -> str:
    """Return tar, stream:<codec>, zip, 7z, rar or other."""
    name = path.name.lower()
    if name.endswith(TAR_SUFFIXES):
        return "tar"
    with path.open("rb") as handle:
        head = handle.read(512)
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "zip"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if head.startswith(b"Rar!\x1a\x07"):
        return "rar"
    if head[257:262] == b"ustar":
        return "tar"
    openers = {b"\x1f\x8b": ("gz", gzip.open), b"BZh": ("bz2", bz2.open), b"\xfd7zXZ\x00": ("xz", lzma.open)}
    for magic, (codec, opener) in openers.items():
        if head.startswith(magic):
            try:
                with opener(path, "rb") as stream:
                    inner = stream.read(512)
            except (OSError, EOFError, lzma.LZMAError):
                inner = b""
            return "tar" if inner[257:262] == b"ustar" else f"stream:{codec}"
    if head.startswith(b"\x28\xb5\x2f\xfd"):
        return "stream:zst"
    return "other"


def _encrypted(seven_zip: str, archive: Path) -> bool:
    result = subprocess.run(
        [seven_zip, "l", "-slt", str(archive)],
        check=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
    )
    output = result.stdout + result.stderr
    return "Encrypted = +" in output or (result.returncode != 0 and "password" in output.lower())


def _decompress_stream(archive: Path, codec: str, destination: Path | None) -> int:
    """Decompress one gz/bz2/xz/zst stream into destination, or only verify it when None."""
    if codec == "zst":
        if not shutil.which("zstd"):
            raise ArchiveError("Extracting .zst needs zstd. Install: brew install zstd")
        if destination is None:
            return subprocess.run(["zstd", "-t", "-q", str(archive)], check=False).returncode
        with destination.open("xb") as output:
            return subprocess.run(["zstd", "-d", "-q", "-c", str(archive)], check=False, stdout=output).returncode
    opener = {"gz": gzip.open, "bz2": bz2.open, "xz": lzma.open}[codec]
    try:
        with opener(archive, "rb") as source:
            if destination is None:
                while source.read(1024 * 1024):
                    pass
            else:
                with destination.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
    except (OSError, EOFError, lzma.LZMAError) as error:
        print(f"unlaw zip: {archive.name}: {error}", file=sys.stderr)
        return 1
    return 0


def _extract_into(archive: Path, kind: str, directory: Path) -> int:
    if kind.startswith("stream:"):
        return _decompress_stream(archive, kind.split(":", 1)[1], directory / archive_stem(archive))
    seven_zip = _seven_zip()
    if kind == "tar" or seven_zip is None:
        return subprocess.run([_tar(), "-xf", str(archive), "-C", str(directory)], check=False).returncode
    password = _ask_password(confirm=False) if _encrypted(seven_zip, archive) else None
    command = [seven_zip, "x", f"-o{directory}", "-aou", "-bso0", _progress(), str(archive)]
    if password is None:
        return subprocess.run(command, check=False, stdin=subprocess.DEVNULL).returncode
    return subprocess.run(command, check=False, input=f"{password}\n", text=True).returncode


def _move(source: Path, destination: Path) -> Path:
    target = _unique(destination)
    os.rename(source, target)
    return target


def _promote(directory: Path, parent: Path, name: str, *, here: bool, keep_junk: bool) -> list[Path]:
    if not keep_junk:
        for junk in list(directory.iterdir()):
            if not _is_junk(junk.name):
                continue
            if junk.is_dir() and not junk.is_symlink():
                shutil.rmtree(junk)
            else:
                junk.unlink()
    entries = sorted(directory.iterdir())
    if not entries:
        raise ArchiveError("The archive is empty.")
    if here or len(entries) == 1:
        return [_move(entry, parent / entry.name) for entry in entries]
    return [_move(directory, parent / name)]


def extract(archive_name: str, *, output: str | None, here: bool, keep_junk: bool) -> int:
    archive = Path(os.path.abspath(Path(archive_name).expanduser()))
    if not archive.is_file():
        raise ArchiveError(f"Archive not found: {_display(archive)}")
    parent = Path(os.path.abspath(Path(output).expanduser())) if output else archive.parent
    parent.mkdir(parents=True, exist_ok=True)
    kind = detect(archive)
    directory = Path(tempfile.mkdtemp(prefix=".unlaw-extract-", dir=parent))
    try:
        code = _extract_into(archive, kind, directory)
        if code:
            return _error(f"Could not extract {_display(archive)} (exit {code}).") if code != 130 else 130
        results = _promote(directory, parent, archive_stem(archive), here=here, keep_junk=keep_junk)
    finally:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
    shown = _display(results[0]) if len(results) == 1 else f"{len(results)} items in {_display(parent)}"
    print(f"Extracted {archive.name} → {shown}")
    return 0


def inspect(archive_name: str, *, test: bool) -> int:
    archive = Path(os.path.abspath(Path(archive_name).expanduser()))
    if not archive.is_file():
        raise ArchiveError(f"Archive not found: {_display(archive)}")
    kind = detect(archive)
    seven_zip = _seven_zip()
    if kind.startswith("stream:"):
        if not test:
            print(f"{archive_stem(archive)}  (single compressed file)")
            return 0
        code = _decompress_stream(archive, kind.split(":", 1)[1], None)
    elif kind == "tar" or seven_zip is None:
        command = [_tar(), "-tf" if test else "-tvf", str(archive)]
        code = subprocess.run(command, check=False, stdout=subprocess.DEVNULL if test else None).returncode
    else:
        password = _ask_password(confirm=False) if _encrypted(seven_zip, archive) else None
        command = [seven_zip, "t" if test else "l", *(["-bso0", _progress()] if test else []), str(archive)]
        if password is None:
            code = subprocess.run(command, check=False, stdin=subprocess.DEVNULL).returncode
        else:
            code = subprocess.run(command, check=False, input=f"{password}\n", text=True).returncode
    if code:
        return _error(f"{'Test failed' if test else 'Could not list'}: {_display(archive)} (exit {code}).")
    if test:
        print(f"OK  {_display(archive)}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ul zip", add_help=False, allow_abbrev=False)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("-o", "--output")
    parser.add_argument("-f", "--format")
    parser.add_argument("-l", "--level")
    for name, number in LEVEL_NAMES.items():
        parser.add_argument(f"--{name}", dest="level", action="store_const", const=number)
    for number in range(10):
        parser.add_argument(f"-{number}", dest="level", action="store_const", const=number)
    parser.add_argument("-p", "--password", action="store_true")
    parser.add_argument("--keep-junk", action="store_true")
    parser.add_argument("--here", action="store_true")
    return parser


def _settings() -> dict:
    settings = dict(load_config().get("zip", {}))
    format_name = normalize_format(str(settings.get("format", "zip")))
    try:
        level = parse_level(settings.get("level", "max"))
    except ArchiveError as error:
        raise ArchiveError(f"zip.level: {error}") from None
    keep_junk = settings.get("keep_junk", False)
    if not isinstance(keep_junk, bool):
        raise ArchiveError("Invalid zip.keep_junk: expected true or false")
    return {"format": format_name, "level": level, "keep_junk": keep_junk}


def _run(args: list[str]) -> int:
    action = ACTIONS.get(args[0]) if args else None
    if action:
        args = args[1:]
    try:
        options = _parser().parse_intermixed_args(args)
    except SystemExit as exit_:
        return 2 if exit_.code else 0
    if not options.paths:
        print("Usage: ul zip <path>... | ul zip x <archive>... — see `ul zip --help`", file=sys.stderr)
        return 2
    if action is None:
        paths = [Path(path).expanduser() for path in options.paths]
        action = "extract" if all(looks_like_archive(path) for path in paths) else "create"
    if action != "create":
        used = [flag for flag, value in (("--format", options.format), ("a level", options.level is not None),
                                         ("--password", options.password)) if value]
        if used:
            raise ArchiveError(f"{', '.join(used)} only applies when creating an archive.")
    if action in {"list", "test"} and (options.output or options.here or options.keep_junk):
        raise ArchiveError("--output, --here and --keep-junk do not apply to ls/test.")
    if action == "create" and options.here:
        raise ArchiveError("--here only applies when extracting.")
    if action in {"list", "test"}:
        return max(inspect(path, test=action == "test") for path in options.paths)
    settings = _settings()
    keep_junk = options.keep_junk or settings["keep_junk"]
    if action == "extract":
        codes = [extract(path, output=options.output, here=options.here, keep_junk=keep_junk) for path in options.paths]
        return max(codes)
    format_name = normalize_format(options.format) if options.format else None
    inferred = _output_format(Path(options.output).name) if options.output else None
    if format_name and inferred and format_name != inferred:
        raise ArchiveError(f"--format {format_name} conflicts with the output name {options.output}.")
    return create(
        options.paths,
        output=options.output,
        format_name=format_name or inferred or settings["format"],
        level=None if options.level is None else parse_level(options.level),
        default_level=settings["level"],
        password=options.password,
        keep_junk=keep_junk,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"} or "-h" in args or "--help" in args:
        print(COMMAND_HELP['zip'], end="")
        return 0
    try:
        return _run(args)
    except (ArchiveError, ConfigError, OSError) as error:
        return _error(str(error))
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
