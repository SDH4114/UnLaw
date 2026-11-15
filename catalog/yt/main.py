# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open YouTube, search, or download one YouTube video."""
from __future__ import annotations

COMMAND_HELP = 'Open YouTube, search, or download one YouTube video.\nUsage:\n  ul yt                                 Open YouTube homepage\n  ul yt <query>                         Search YouTube in your default browser\n  ul yt download <URL> [options]         Download one video (not its playlist)\nOptions:\n  --format mov|mp4|raw Video format (default: mov); raw keeps the source container\n  --audio              Save only MP3 (cannot combine with --quality or --format)\n  --sub                Save only subtitles as .md, original language by default\n  --sub-lang [code]    Choose ru/en/etc.; no value selects original. Implies --sub\n                       unless --full is used; unknown codes list available languages\n  --full               Save video with sound, separate MP3 and .md subtitles\n  --podcast            Save a small mono MP3 (64 kbps, title/channel/cover tags)\n                       into yt.podcast_dir, by default iCloud Drive/Podcasts\n  --quality <height>   Maximum video height, e.g. 720, 1080, 2160\n  --output <directory> Save into this directory (created if needed)\n  --json               One JSON line on stdout at the end: {"ok", "exit", "files": [{"path",\n                       "status": "saved"|"exists"}]}; messages and progress go to stderr\n  -h, --help           Show this help, also after download\nModes --audio, --podcast, --sub and --full cannot be combined.\nSubtitle-only mode cannot use --quality or --format; --full supports both.\nMarkdown starts with the video link, then title, language/source and cleaned text.\nAuthored captions are preferred; automatic captions may contain recognition errors.\n--full downloads media once and extracts MP3 locally. Missing/failed subtitles\nproduce a clear warning and a nonzero exit code while retaining saved media.\nDefaults: MOV video with audio; storage.root/youtube.\n--podcast saves into yt.podcast_dir (setting; --output overrides it). Its parent\nfolder must exist, so a disabled iCloud Drive is reported instead of filled locally.\nMOV/MP4 conversion uses H.264/AAC when conversion is needed; it can take time.\nRaw preserves the source codecs/container (possibly WebM); it is not camera RAW.\nDependencies: yt-dlp; video/audio also need ffmpeg/ffprobe. Deno supports YouTube.\nInstall: brew install yt-dlp ffmpeg deno\nExisting files are not overwritten: a video, MP3 or podcast that is already there is\nfound before anything is downloaded. Download progress appears in the terminal.\nExit codes: 0 saved or already there, 1 failure, 2 wrong arguments, 124 metadata timeout,\n130 Ctrl-C, 143 terminated; a failing yt-dlp/ffmpeg passes its own code. A stopped download\nremoves its temporary folder.\nExamples:\n  ul yt "omarchy linux"\n  ul yt download "https://www.youtube.com/watch?v=VIDEO_ID"\n  ul yt download "https://youtu.be/VIDEO_ID" --format mp4\n  ul yt download "https://youtu.be/VIDEO_ID" --format raw\n  ul yt download "https://youtu.be/VIDEO_ID" --audio\n  ul yt download "https://youtu.be/VIDEO_ID" --podcast\n  ul yt download "https://youtu.be/VIDEO_ID" --sub\n  ul yt download "https://youtu.be/VIDEO_ID" --sub-lang\n  ul yt download "https://youtu.be/VIDEO_ID" --sub-lang ru\n  ul yt download "https://youtu.be/VIDEO_ID" --full --sub-lang en --format mp4\n  ul yt download "https://youtu.be/VIDEO_ID" --quality 1080 --output ~/Downloads\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'},
 'apps': {'youtube_url': 'https://www.youtube.com/'},
 'yt': {'podcast_dir': '~/Library/Mobile Documents/com~apple~CloudDocs/Podcasts'}}


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

import argparse
import errno
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse



def _quality(value: str) -> int:
    try:
        height = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("quality must be a positive video height, e.g. 1080") from None
    if height < 1 or height > 16384:
        raise argparse.ArgumentTypeError("quality must be between 1 and 16384")
    return height


def _caption_tracks(info: dict) -> dict[str, tuple[list, bool]]:
    tracks = {}
    for field, automatic in (("automatic_captions", True), ("subtitles", False)):
        for language, formats in (info.get(field) or {}).items():
            if language != "live_chat" and isinstance(formats, list) and formats:
                tracks[language] = (formats, automatic)
    return tracks


def _select_subtitle(info: dict, requested: str | None) -> tuple[str, bool] | None:
    tracks = _caption_tracks(info)
    if not tracks:
        print("unlaw yt: No subtitles are available for this video.", file=sys.stderr)
        return None
    language = str(info.get("language") or "")
    original = next((key for key in tracks if key.endswith("-orig")), None)
    if requested in (None, "original"):
        # Prefer authored captions in the original language over automatic ones.
        base = original.removesuffix("-orig") if original else language
        manual = info.get("subtitles") or {}
        selected = base if base in tracks and base in manual else original
        selected = selected or (language if language in tracks else None)
        if selected is None:
            selected = next(iter(sorted(manual.keys() & tracks.keys())), None) or next(iter(sorted(tracks)))
            print(f"unlaw yt: Original language is unknown; using {selected}.", file=sys.stderr)
    else:
        requested = requested.lower().replace("_", "-")
        selected = next((key for key in tracks if key.lower() == requested), None)
        # ru should use ru-orig rather than an automatic translation of ru-orig.
        if requested not in (info.get("subtitles") or {}) and f"{requested}-orig" in tracks:
            selected = f"{requested}-orig"
        if selected is None:
            print(f"unlaw yt: Unknown subtitle language: {requested}. Available languages:", file=sys.stderr)
            for key in sorted(tracks):
                formats, automatic = tracks[key]
                label = next((item.get("name") for item in formats if item.get("name")), key)
                kind = "automatic" if automatic else "authored"
                print(f"  {key:<12} {label} ({kind})", file=sys.stderr)
            print("Use --sub-lang <code>, or --sub-lang alone for the original language.", file=sys.stderr)
            raise ValueError("Choose one of the available subtitle languages")
    return selected, tracks[selected][1]


def _subtitle_text(path: Path) -> str:
    """Remove subtitle timing/markup and only overlapping rolling-caption repeats."""
    cues = []
    source = path.read_text(encoding="utf-8-sig")
    if path.suffix == ".json3":
        data = json.loads(source)
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise ValueError("Invalid JSON3 caption structure")
        for event in data["events"]:
            if not isinstance(event, dict) or not isinstance(event.get("segs", []), list):
                raise ValueError("Invalid JSON3 caption event")
            text = "".join(segment.get("utf8", "") for segment in event.get("segs", []))
            start = float(event.get("tStartMs", 0))
            cues.append((start, start + float(event.get("dDurationMs", 0)), text))
    else:
        timestamp = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})[,.](\d{3})")

        def millis(match):
            hours, minutes, seconds, fraction = match.groups()
            return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(fraction)

        for block in re.split(r"\n\s*\n", source.replace("\r\n", "\n")):
            lines = block.splitlines()
            if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
                continue
            for index, line in enumerate(lines):
                if "-->" not in line:
                    continue
                times = list(timestamp.finditer(line))
                if len(times) >= 2:
                    text = re.sub(r"<[^>]+>", "", " ".join(lines[index + 1:]))
                    cues.append((millis(times[0]), millis(times[1]), text))
                break
    words = []
    previous = []
    previous_end = -1
    for start, end, text in cues:
        text = re.sub(r"\[(?:music|applause|laughter|музыка|аплодисменты|смех)\]", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"(?<!\S)>>(?=\s|$)", " ", text)
        current = html.unescape(text).split()
        if not current:
            continue
        overlap = 0
        if start < previous_end:
            for size in range(min(len(previous), len(current)), 0, -1):
                if previous[-size:] == current[:size]:
                    overlap = size
                    break
        words.extend(current[overlap:])
        previous, previous_end = current, end
    if not words:
        raise ValueError("Subtitle file contains no spoken text")
    paragraphs, paragraph = [], []
    for word in words:
        paragraph.append(word)
        if len(paragraph) >= 100 and word.endswith((".", "!", "?", "…")):
            paragraphs.append(" ".join(paragraph))
            paragraph = []
    if paragraph:
        paragraphs.append(" ".join(paragraph))
    return "\n\n".join(paragraphs)


def _safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text)
    return text.encode("utf-8")[:180].decode("utf-8", errors="ignore").strip(" .") or "video"


# Volumes without hard links (exFAT, FAT, most network shares) answer link(2) with one of these.
_NO_HARD_LINKS = {errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM, errno.EXDEV, errno.EMLINK}


def _copy_new(source: Path, destination: Path) -> bool:
    """Copy into a file created exclusively; False when the destination already exists."""
    try:
        target = destination.open("xb")
    except FileExistsError:
        return False
    try:
        with target, source.open("rb") as stream:
            shutil.copyfileobj(stream, target, 1024 * 1024)
    except BaseException:
        destination.unlink(missing_ok=True)  # never leave half a file under the final name
        raise
    return True


# `--json`: stdout carries one JSON object at the end, so messages and the tools' progress go to stderr.
_JSON = False
_RESULTS: list[dict] = []


def _say(text: str) -> None:
    print(text, file=sys.stderr if _JSON else sys.stdout, flush=True)


def _saved(path: Path) -> None:
    _RESULTS.append({"path": str(path), "status": "saved"})
    _say(f"Saved: {path}")


def _exists(path: Path) -> None:
    _RESULTS.append({"path": str(path), "status": "exists"})
    _say(f"Already exists: {path}")


def _tool(command: list[str]) -> int:
    """Run yt-dlp or ffmpeg with its progress on the terminal (on stderr with --json)."""
    return subprocess.run(command, check=False, **({"stdout": 2} if _JSON else {})).returncode


class _Stopped(KeyboardInterrupt):
    """SIGTERM or SIGHUP: unwind like Ctrl-C, so temporary folders are removed and the tool is stopped."""

    def __init__(self, signum: int) -> None:
        super().__init__()
        self.code = 128 + signum


def _catch_termination():
    """Turn SIGTERM/SIGHUP into _Stopped; returns a function that puts the old handlers back."""
    def stop(signum: int, frame: object) -> None:
        raise _Stopped(signum)

    previous = {}
    try:
        for number in (signal.SIGTERM, signal.SIGHUP):
            previous[number] = signal.signal(number, stop)
    except ValueError:
        pass  # not the main thread (tests): signals keep their handlers

    def restore() -> None:
        for number, handler in previous.items():
            signal.signal(number, handler)

    return restore


def _sweep(output: Path) -> None:
    """Remove staging folders a killed download left behind (older than a day, so never a running one)."""
    limit = time.time() - 24 * 3600
    for stale in output.glob(".unlaw-yt-*"):
        try:
            if stale.is_dir() and not stale.is_symlink() and stale.stat().st_mtime < limit:
                shutil.rmtree(stale, ignore_errors=True)
        except OSError:
            continue


def _probe(executable: str, url: str, stage: Path) -> Path | None:
    """One metadata request, saved as `<title> [<id>].info.json` in `stage`: its name is the file name the
    download will get, so an existing file is found before downloading, and the download reuses the metadata.
    None when it fails; the download then runs as before and reports the error itself."""
    probe = subprocess.run(
        [executable, "--ignore-config", "--no-playlist", "--skip-download", "--write-info-json", "--paths", str(stage),
         "--output", "%(title).180B [%(id)s].%(ext)s", "--", url],
        check=False, capture_output=True, text=True, timeout=120,
    )
    found = list(stage.glob("*.info.json"))
    return found[0] if probe.returncode == 0 and len(found) == 1 else None


def _publish(source: Path, destination: Path) -> None:
    # Both paths are on the same filesystem: hard-link publishes atomically,
    # including when another process creates the destination concurrently.
    try:
        os.link(source, destination)
    except FileExistsError:
        _exists(destination)
        return
    except OSError as error:
        if error.errno not in _NO_HARD_LINKS:
            raise
        if not _copy_new(source, destination):
            _exists(destination)
            return
    _saved(destination)


def _podcast_dir() -> Path:
    folder = Path(str(load_config()["yt"]["podcast_dir"])).expanduser()
    if not folder.is_absolute():
        raise ConfigError("yt.podcast_dir must be an absolute path or start with ~")
    # Create only the last folder: a missing parent usually means iCloud Drive is off,
    # and a local look-alike folder would never reach the phone.
    if not folder.parent.is_dir():
        raise OSError(f"{folder.parent} does not exist (is iCloud Drive on?); set yt.podcast_dir or use --output")
    return folder


def _selector(height: int | None) -> str:
    if height is None:
        return "bestvideo*+bestaudio/best"
    return f"bestvideo*[height<={height}]+bestaudio/best[height<={height}]"


def _subtitle_bundle(options, executable: str, output: Path) -> int:
    _say("Checking video and subtitle languages...")
    probe = subprocess.run(
        [executable, "--ignore-config", "--no-playlist", "--skip-download", "--dump-single-json", "--", options.url],
        check=False, capture_output=True, text=True, timeout=120,
    )
    if probe.returncode:
        print(probe.stderr or "unlaw yt: Could not inspect the video.", file=sys.stderr)
        return probe.returncode
    info = json.loads(probe.stdout)
    if not isinstance(info, dict) or not info.get("id") or info.get("_type", "video") != "video":
        raise ValueError("Expected metadata for one video")
    selected = _select_subtitle(info, options.sub_lang)
    if selected is None and not options.full:
        return 1
    stem = f"{_safe_name(str(info.get('title') or 'video'))} [{_safe_name(str(info['id']))}]"
    caption_failed = selected is None
    with tempfile.TemporaryDirectory(prefix=".unlaw-yt-", dir=output) as temporary:
        stage = Path(temporary)
        metadata = stage / "video.info.json"
        metadata.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        base = [executable, "--ignore-config", "--no-playlist", "--no-overwrites", "--no-post-overwrites",
                "--load-info-json", str(metadata), "--paths", str(stage)]
        if selected is not None:
            language, automatic = selected
            destination = output / f"{stem}.{_safe_name(language)}.md"
            if destination.exists():
                _exists(destination)
            else:
                _say(f"Subtitles: {language} ({'automatic' if automatic else 'authored'})")
                code = _tool([
                    *base, "--skip-download", "--write-auto-subs" if automatic else "--write-subs",
                    "--sub-format", "json3/vtt/srt", "--sub-langs", f"^{re.escape(language)}$",
                    "--output", "captions.%(ext)s",
                ])
                candidates = [p for p in stage.glob("captions.*") if p.suffix in {".json3", ".vtt", ".srt"}]
                if code or len(candidates) != 1:
                    print("unlaw yt: Subtitles could not be downloaded; no Markdown was created.", file=sys.stderr)
                    caption_failed = True
                else:
                    try:
                        text = _subtitle_text(candidates[0])
                        kind = "automatic (may contain recognition errors)" if automatic else "authored"
                        markdown = stage / "transcript.md"
                        markdown.write_text(
                            f"<{options.url}>\n\n# {str(info.get('title') or 'Video').replace(chr(10), ' ')}\n\n"
                            f"Language: {language} · Subtitles: {kind}\n\n{text}\n", encoding="utf-8",
                        )
                        _publish(markdown, destination)
                    except (ValueError, KeyError, TypeError) as error:
                        print(f"unlaw yt: Invalid subtitle data: {error}", file=sys.stderr)
                        caption_failed = True
        if options.full:
            container = options.format or "mov"
            video = output / f"{stem}.{container}" if container != "raw" else None
            audio = output / f"{stem}.mp3"
            if container == "raw":
                existing = [output / f"{stem}.{ext}" for ext in ("webm", "mkv", "mp4", "mov", "m4v")]
                video = next((path for path in existing if path.is_file()), None)
            # For raw, discover the real extension instead of inventing a .raw container.
            if video is not None and video.exists() and audio.exists():
                _exists(video)
                _exists(audio)
            else:
                _say("Downloading video once; MP3 will be extracted locally...")
                code = _tool([*base, "--format", _selector(options.quality), "--output", "media.%(ext)s"])
                if code:
                    print("unlaw yt: Video download failed; any saved Markdown is retained.", file=sys.stderr)
                    return code
                media = [p for p in stage.glob("media.*") if p.suffix in {".mp4", ".webm", ".mkv", ".mov", ".m4v"}]
                if len(media) != 1:
                    raise ValueError("Downloader did not produce one complete video file")
                source = media[0]
                command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(source)]
                converted = stage / f"finished.{container}" if container != "raw" else source
                video = video or output / f"{stem}{source.suffix}"
                needs_video = not video.exists() and container != "raw"
                needs_audio = not audio.exists()
                if needs_video:
                    command.extend(["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-crf", "18",
                                    "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                                    "-movflags", "+faststart", str(converted)])
                extracted = stage / "audio.mp3"
                if needs_audio:
                    command.extend(["-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(extracted)])
                if needs_video or needs_audio:
                    code = _tool(command)
                    if code:
                        print("unlaw yt: Media conversion failed; any saved Markdown is retained.", file=sys.stderr)
                        return code
                if not video.exists():
                    _publish(converted, video)
                if needs_audio:
                    _publish(extracted, audio)
        if caption_failed:
            print("unlaw yt: Incomplete result: subtitles are unavailable or could not be saved.", file=sys.stderr)
            return 1
    return 0


def _download(args: list[str]) -> int:
    """`ul yt download`: with --json the last line of stdout is {"ok", "exit", "files": [{"path", "status"}]}."""
    global _JSON
    wants_help = "--help" in args or "-h" in args
    _JSON = "--json" in args and not wants_help
    _RESULTS.clear()
    restore = _catch_termination()
    try:
        code = _run_download(args)
    finally:
        restore()
    if _JSON:
        _JSON = False
        print(json.dumps({"ok": code == 0, "exit": code, "files": list(_RESULTS)}, ensure_ascii=False), flush=True)
    return code


def _run_download(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ul yt download", description="Download one YouTube video.")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--format", choices=("mov", "mp4", "raw"), help="video container (default: mov); raw keeps the source format")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--audio", action="store_true", help="save audio as MP3")
    modes.add_argument("--sub", action="store_true", help="save only subtitles as Markdown")
    modes.add_argument("--full", action="store_true", help="save video, separate MP3 and Markdown subtitles")
    modes.add_argument("--podcast", action="store_true", help="save a small mono MP3 for speech into yt.podcast_dir")
    parser.add_argument("--sub-lang", nargs="?", const="original", help="subtitle language; omitted value selects original and implies --sub")
    parser.add_argument("--quality", type=_quality, help="maximum video height, e.g. 1080")
    parser.add_argument("--output", type=Path, help="output directory (default: storage.root/youtube)")
    parser.add_argument("--json", action="store_true", help="print one JSON result on stdout; progress goes to stderr")
    if "--help" in args or "-h" in args:
        print(COMMAND_HELP, end="")
        return 0
    try:
        options = parser.parse_args(args)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 2
    try:
        parsed = urlparse(options.url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        print("unlaw yt: Invalid YouTube URL.", file=sys.stderr)
        return 2
    if parsed.scheme not in {"https", "http"} or host not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be",
    } or parsed.username is not None or parsed.password is not None:
        print("unlaw yt: download requires a YouTube HTTP(S) URL.", file=sys.stderr)
        return 2
    video_path = parsed.path.strip("/")
    is_video = (
        bool(video_path) and "/" not in video_path
        if host in {"youtu.be", "www.youtu.be"}
        else (parsed.path == "/watch" and bool(parse_qs(parsed.query).get("v", [""])[0]))
        or (len(video_path.split("/")) == 2 and video_path.split("/")[0] in {"shorts", "live", "embed"})
    )
    if not is_video:
        print("unlaw yt: Provide a video URL (watch, shorts, live or youtu.be), not a playlist/channel.", file=sys.stderr)
        return 2
    audio_flag = "--podcast" if options.podcast else "--audio"
    audio_only = options.audio or options.podcast
    if audio_only and options.quality is not None:
        print(f"unlaw yt: {audio_flag} cannot be combined with --quality.", file=sys.stderr)
        return 2
    if audio_only and options.format is not None:
        print(f"unlaw yt: --format is for video; {audio_flag} saves MP3.", file=sys.stderr)
        return 2
    subtitles_only = options.sub or (options.sub_lang is not None and not options.full)
    if subtitles_only and (audio_only or options.quality is not None or options.format is not None):
        print("unlaw yt: Subtitle-only mode cannot use --audio, --podcast, --quality or --format; use --full for a bundle.", file=sys.stderr)
        return 2
    executable = shutil.which("yt-dlp")
    required = ("yt-dlp",) if subtitles_only else ("yt-dlp", "ffmpeg", "ffprobe")
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        print(f"unlaw yt: Missing tools: {', '.join(missing)}. Run: brew install yt-dlp ffmpeg deno", file=sys.stderr)
        return 1
    try:
        if options.output is not None:
            output = options.output.expanduser()
        else:
            output = _podcast_dir() if options.podcast else storage_path("youtube")
        output = output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        _sweep(output)
        if subtitles_only or options.full:
            return _subtitle_bundle(options, executable, output)
        command = [
            executable, "--ignore-config", "--no-playlist", "--no-overwrites", "--no-post-overwrites",
            "--paths", str(output), "--output", "%(title).180B [%(id)s].%(ext)s",
        ]
        if audio_only:
            command.extend(["--format", "bestaudio/best", "--extract-audio", "--audio-format", "mp3"])
            if options.podcast:
                # Speech needs little: mono 64 kbps is about 29 MB per hour. Tags and cover
                # make the episode recognisable in Files and podcast players.
                command.extend([
                    "--audio-quality", "64K", "--postprocessor-args", "ExtractAudio+ffmpeg_o:-ac 1",
                    "--embed-metadata", "--embed-thumbnail", "--convert-thumbnails", "jpg",
                ])
        else:
            selector = _selector(options.quality)
            command.extend(["--format", selector])
            container = options.format or "mov"
            if container != "raw":
                command.extend([
                    "--merge-output-format", "mkv", "--recode-video", container,
                    "--postprocessor-args",
                    "VideoConvertor+ffmpeg_o:-c:v libx264 -crf 18 -preset medium "
                    "-c:a aac -b:a 192k -pix_fmt yuv420p -vf pad=ceil(iw/2)*2:ceil(ih/2)*2 -movflags +faststart",
                ])
        _say(f"Saving to: {output}")
        # Converter postprocessors may ignore --no-post-overwrites. Keep every
        # intermediate/conversion in a private directory and publish without replacing.
        with tempfile.TemporaryDirectory(prefix=".unlaw-yt-", dir=output) as temporary:
            stage = Path(temporary)
            command[command.index("--paths") + 1] = str(stage)
            source_arguments = ["--", options.url]
            info = _probe(executable, options.url, stage)
            if info is not None:
                # The real container of a raw download is unknown until it is downloaded.
                extension = "mp3" if audio_only else options.format or "mov"
                finished = output / f"{info.name.removesuffix('.info.json')}.{extension}"
                if extension != "raw" and finished.is_file():
                    _exists(finished)
                    return 0
                source_arguments = ["--load-info-json", str(info)]
            manifest = stage / "result.json"
            command.extend(["--no-simulate", "--print-to-file", "after_move:%(filepath)j", str(manifest), *source_arguments])
            code = _tool(command)
            if code:
                return code
            source = Path(json.loads(manifest.read_text())).resolve()
            source.relative_to(stage.resolve())
            if not source.is_file():
                raise ValueError("Downloader did not produce a complete media file")
            _publish(source, output / source.name)
            return 0
    except subprocess.TimeoutExpired:
        print("unlaw yt: Video metadata request timed out. Try again later.", file=sys.stderr)
        return 124
    except (ConfigError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"unlaw yt: {error}", file=sys.stderr)
        return 2 if isinstance(error, ValueError) else 1
    except KeyboardInterrupt as stop:
        print("\nunlaw yt: download cancelled.", file=sys.stderr)
        return getattr(stop, "code", 130)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    if args and args[0] == "download":
        return _download(args[1:])
    query = " ".join(args).strip()
    try:
        homepage = str(load_config()["apps"]["youtube_url"])
        url = homepage if not query else homepage.rstrip("/") + "/results?" + urlencode({"search_query": query})
        return subprocess.run(["open", url], check=False).returncode
    except (ConfigError, OSError) as error:
        print(f"unlaw yt: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
