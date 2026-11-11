# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Countdown timers and alarms with macOS notifications."""
from __future__ import annotations

COMMAND_HELP = 'Countdown timers and alarms with macOS notifications.\nUsage: ul timer <duration> [label...]   Start a timer in the background\n       ul timer at HH:MM [label...]     Alarm at that time (tomorrow if it has passed)\n       ul timer [list] [--json]         Running timers with the time left\n       ul timer cancel ID|--all         Stop one timer or all of them\n       ul timer wait <duration> [label...]   Count down here (Ctrl+C cancels)\n  <duration>   30s, 5m, 1h30m or bare minutes (25); at most 7 days\nA timer runs as a detached process, so you can close the terminal. When it ends a\nnotification appears (with a sound unless timer.sound is false). `wait` shows the\ncountdown on one line and notifies too. Labels must not contain control characters.\nState: storage.root/runtime/timers.json. Entries whose process is gone are dropped.\nNeeds: macOS `osascript` for the notification.\nSettings: timer.sound (true/false), storage.root.\nExamples:\n  ul timer 25m write report\n  ul timer at 18:30 leave\n  ul timer wait 90s tea\n  ul timer cancel 2\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'}, 'timer': {'sound': True}}


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
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path



# ul timer: countdowns and alarms. Each one is a small detached process of this file (`_run <id>`) that sleeps until
# the end time and then shows a macOS notification.
#
# State: storage.root/runtime/timers.json, written atomically under a flock (timers.lock).
#   {"version": 1, "timers": [{id, kind "duration"|"alarm", label, end (epoch seconds), created, pid, lstart}]}
#   pid/lstart are filled in by the starting command right after it spawned the process (pid is null for a moment).
# An entry whose process is not alive, does not run this file with `_run <id>`, or started at another time (a reused
# pid) is stale and is dropped. A pid is never signalled unless `ps` confirms the process is ours.
# The notification text goes to osascript as arguments (`on run argv`); user text is never part of AppleScript source.

USAGE = """Usage: ul timer <duration> [label...] | at HH:MM [label...]
       ul timer [list [--json]] | cancel ID|--all | wait <duration> [label...]
Run `ul timer --help` for details.
"""

STATE_VERSION = 1
MAX_SECONDS = 7 * 24 * 3600
MAX_LABEL = 200
START_GRACE = 15
DURATION = re.compile(r"(?:([0-9]{1,9})h)?(?:([0-9]{1,9})m)?(?:([0-9]{1,9})s)?")
CLOCK = re.compile(r"([0-9]{1,2}):([0-9]{2})")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
SELF = os.path.abspath(__file__)
NOTIFY_TITLE = "Timer"
NOTIFY_DEFAULT = "Time is up"
SOUND = "Glass"


class TimerError(Exception):
    """A problem the user can fix; `code` is the exit status (2 usage, 1 failure)."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- parsing


def _local(stamp: float) -> datetime:
    return datetime.fromtimestamp(stamp, tz=UTC).astimezone()


def parse_duration(text: str) -> int:
    """Seconds for 30s, 5m, 1h30m or bare minutes (25)."""
    value = text.strip().lower()
    if re.fullmatch(r"[0-9]{1,9}", value):
        seconds = int(value) * 60
    else:
        match = DURATION.fullmatch(value)
        if not value or match is None:
            raise TimerError(
                f"not a duration: {text!r} (use 30s, 5m, 1h30m or minutes)"
            )
        hours, minutes, secs = (int(part or 0) for part in match.groups())
        seconds = hours * 3600 + minutes * 60 + secs
    if seconds <= 0:
        raise TimerError(f"the duration must be above zero: {text!r}")
    if seconds > MAX_SECONDS:
        raise TimerError(f"too long: {text!r} (at most 7 days)")
    return seconds


def parse_alarm(text: str, now: float) -> float:
    """Epoch seconds of the next HH:MM in local time (tomorrow when it has passed)."""
    match = CLOCK.fullmatch(text.strip())
    if match is None or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise TimerError(f"not a time: {text!r} (use HH:MM, 24-hour)")
    # Naive local wall-clock arithmetic, so "tomorrow 18:30" stays 18:30 across a DST change.
    today = (
        _local(now)
        .replace(tzinfo=None)
        .replace(
            hour=int(match.group(1)),
            minute=int(match.group(2)),
            second=0,
            microsecond=0,
        )
    )
    target = today if today.timestamp() > now else today + timedelta(days=1)
    return target.timestamp()


def clean_label(words: Sequence[str]) -> str:
    label = " ".join(words).strip()
    if CONTROL.search(label):
        raise TimerError("the label must not contain control characters")
    if len(label) > MAX_LABEL:
        raise TimerError(f"the label is too long (at most {MAX_LABEL} characters)")
    return label


def format_span(seconds: float) -> str:
    total = max(0, int(seconds + 0.5))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_end(end: float, now: float) -> str:
    moment = _local(end)
    if moment.date() == _local(now).date():
        return moment.strftime("%H:%M:%S")
    return moment.strftime("%a %d %b %H:%M:%S")


# ---------------------------------------------------------------- processes


def _alive(pid: object) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _command_of(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _lstart(pid: int) -> str:
    """When the process started (`ps -o lstart=`): a reused pid has another start time. `ps` prints local time, so
    it is asked in UTC and the C locale: the same pid must read the same under any TZ. "" = unknown."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={**os.environ, "TZ": "UTC", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return " ".join(result.stdout.split()) if result.returncode == 0 else ""


def _is_python(word: str) -> bool:
    return os.path.basename(word).lower().startswith("python")


def _seed_arguments(command: str) -> str | None:
    """The arguments after `<python> <this file>` in a `ps` command line, or None for any other process.
    The interpreter path may contain spaces, so this file is searched for, not split off."""
    marker = " " + SELF
    start = command.find(marker)
    while start > 0:
        rest = command[start + len(marker) :]
        if (not rest or rest.startswith(" ")) and _is_python(command[:start].strip()):
            return rest.strip()
        start = command.find(marker, start + 1)
    return None


def is_ours(entry: dict) -> bool:
    """True when the entry's pid is alive, runs `_run <id>` of this file and started when recorded."""
    pid = entry.get("pid")
    if not _alive(pid):
        return False
    arguments = _seed_arguments(_command_of(pid))
    if arguments is None or arguments.split() != ["_run", str(entry.get("id"))]:
        return False
    recorded = " ".join(str(entry.get("lstart") or "").split())
    current = _lstart(pid)
    # An unknown start time must never condemn a live timer.
    return not recorded or not current or current == recorded


# ---------------------------------------------------------------- state


def state_file() -> Path:
    return storage_path("runtime", "timers.json")


@contextmanager
def _locked() -> Iterator[None]:
    lock = storage_path("runtime", "timers.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _valid(entry: object) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("id"), str)
        and isinstance(entry.get("end"), int | float)
        and isinstance(entry.get("label"), str)
        and entry.get("kind") in ("duration", "alarm")
    )


def read_timers() -> list[dict]:
    path = state_file()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as error:
        raise TimerError(f"could not read {path}: {error}", 1) from error
    try:
        data = json.loads(text)
        timers = data["timers"]
        if data.get("version") != STATE_VERSION or not all(_valid(t) for t in timers):
            raise ValueError("unexpected content")
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise TimerError(
            f"{path} is damaged ({error}); fix or delete it to continue", 1
        ) from error
    return timers


def write_timers(timers: list[dict]) -> None:
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".timers-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"version": STATE_VERSION, "timers": timers}, handle)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def live_timers(now: float) -> list[dict]:
    """The recorded timers without stale ones. The caller holds the lock and writes the result back."""
    kept = []
    for entry in read_timers():
        starting = (
            entry.get("pid") is None and now - entry.get("created", 0) < START_GRACE
        )
        if starting or is_ours(entry):
            kept.append(entry)
    return kept


def _find(timers: list[dict], timer_id: str) -> dict | None:
    return next((entry for entry in timers if entry["id"] == timer_id), None)


def _number(entry: dict) -> int:
    return int(entry["id"]) if entry["id"].isdigit() else 0


# ---------------------------------------------------------------- notification


def notify(label: str, sound: bool) -> bool:
    script = "display notification (item 1 of argv) with title (item 2 of argv)"
    if sound:
        script += f' sound name "{SOUND}"'
    command = [
        "osascript",
        "-e",
        "on run argv",
        "-e",
        script,
        "-e",
        "end run",
        "--",
        label or NOTIFY_DEFAULT,
        NOTIFY_TITLE,
    ]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def sound_enabled() -> bool:
    try:
        return bool(load_config()["timer"]["sound"])
    except (ConfigError, KeyError, TypeError):
        return True


# ---------------------------------------------------------------- commands


def start(kind: str, end: float, label: str) -> None:
    now = time.time()
    with _locked():
        timers = live_timers(now)
        timer_id = str(max((_number(entry) for entry in timers), default=0) + 1)
        timers.append(
            {
                "id": timer_id,
                "kind": kind,
                "label": label,
                "end": end,
                "created": now,
                "pid": None,
                "lstart": "",
            }
        )
        write_timers(timers)
    try:
        process = subprocess.Popen(
            [sys.executable, SELF, "_run", timer_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as error:
        with _locked():
            write_timers([e for e in read_timers() if e["id"] != timer_id])
        raise TimerError(f"could not start the timer: {error}", 1) from error
    with _locked():
        timers = read_timers()
        entry = _find(timers, timer_id)
        if entry is not None:
            entry["pid"] = process.pid
            entry["lstart"] = _lstart(process.pid)
            write_timers(timers)
    print(
        f"timer {timer_id} set: ends {format_end(end, now)}"
        + (f" - {label}" if label else "")
    )


def run_timer(timer_id: str) -> int:
    """The detached process: sleep until the end, then drop the entry and notify (unless it was cancelled)."""
    while True:
        entry = _find(read_timers(), timer_id)
        if entry is None or entry.get("pid") not in (None, os.getpid()):
            return 0
        left = entry["end"] - time.time()
        if left <= 0:
            break
        time.sleep(min(left, 1.0))
    with _locked():
        timers = read_timers()
        entry = _find(timers, timer_id)
        if entry is None:
            return 0
        write_timers([t for t in timers if t["id"] != timer_id])
    notify(entry["label"], sound_enabled())
    return 0


def show_list(as_json: bool) -> int:
    now = time.time()
    with _locked():
        timers = live_timers(now)
        if timers != read_timers():
            write_timers(timers)
    timers.sort(key=_number)
    if as_json:
        rows = [
            {
                "id": entry["id"],
                "kind": entry["kind"],
                "label": entry["label"],
                "ends": _local(entry["end"]).isoformat(timespec="seconds"),
                "remaining_seconds": max(0, int(entry["end"] - now + 0.5)),
            }
            for entry in timers
        ]
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    if not timers:
        print("no timers running")
        return 0
    for entry in timers:
        label = f"  {entry['label']}" if entry["label"] else ""
        print(
            f"{entry['id']:>3}  {format_span(entry['end'] - now):>10} left  "
            f"ends {format_end(entry['end'], now)}{label}"
        )
    return 0


def _stop(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return
    except PermissionError:
        print(f"unlaw timer: not permitted to stop pid {pid}", file=sys.stderr)


def cancel(args: list[str]) -> int:
    if args == ["--all"]:
        wanted = None
    elif len(args) == 1 and not args[0].startswith("-"):
        wanted = args[0]
    else:
        raise TimerError("use: ul timer cancel ID|--all")
    with _locked():
        everything = read_timers()
        targets = [e for e in everything if wanted is None or e["id"] == wanted]
        if wanted is not None and not targets:
            raise TimerError(f"no timer {wanted}", 1)
        for entry in targets:
            if is_ours(entry):
                _stop(entry["pid"])
        gone = {e["id"] for e in targets}
        # Stale entries of other ids are dropped on the way.
        write_timers([e for e in live_timers(time.time()) if e["id"] not in gone])
    if wanted is None:
        print(f"cancelled {len(targets)} timer(s)" if targets else "no timers running")
    else:
        print(f"timer {wanted} cancelled")
    return 0


def wait(duration: str, words: list[str]) -> int:
    seconds = parse_duration(duration)
    label = clean_label(words)
    now = time.time()
    end = now + seconds
    live = sys.stdout.isatty()
    print(
        f"waiting {format_span(seconds)}, ends {format_end(end, now)}"
        + (f" - {label}" if label else "")
    )
    while True:
        left = end - time.time()
        if left <= 0:
            break
        if live:
            print(f"\r{format_span(left):>10} left\x1b[K", end="", flush=True)
        time.sleep(min(left, 0.2))
    if live:
        print("\r\x1b[K", end="")
    print(f"done{' - ' + label if label else ''}")
    if not notify(label, sound_enabled()):
        print("unlaw timer: could not show the notification", file=sys.stderr)
    return 0


def _dispatch(args: list[str]) -> int:
    if args[:1] == ["_run"]:
        if len(args) != 2:
            raise TimerError("_run takes a timer id")
        return run_timer(args[1])
    if not args or args[0] in ("list", "--json"):
        rest = args[1:] if args[:1] == ["list"] else args
        if any(word != "--json" for word in rest):
            raise TimerError("use: ul timer list [--json]")
        return show_list("--json" in rest)
    if args[0] == "cancel":
        return cancel(args[1:])
    if args[0] == "wait":
        if len(args) < 2:
            raise TimerError("use: ul timer wait <duration> [label...]")
        return wait(args[1], args[2:])
    if args[0] == "at":
        if len(args) < 2:
            raise TimerError("use: ul timer at HH:MM [label...]")
        label = clean_label(args[2:])
        start("alarm", parse_alarm(args[1], time.time()), label)
        return 0
    seconds = parse_duration(args[0])
    label = clean_label(args[1:])
    start("duration", time.time() + seconds, label)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "-h" in args or "--help" in args or args[:1] == ["help"]:
        print(COMMAND_HELP, end="")
        return 0
    try:
        return _dispatch(args)
    except TimerError as error:
        print(f"unlaw timer: {error}", file=sys.stderr)
        if error.code == 2:
            print(USAGE, end="", file=sys.stderr)
        return error.code
    except ConfigError as error:
        print(f"unlaw timer: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
