from __future__ import annotations

import fcntl
import getpass
import json
import math
import os
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as clock_time
from pathlib import Path

from unlawful.command_help import COMMAND_HELP

from .config import ConfigError, storage_path

# ul awake keeps the Mac awake with `caffeinate`, and with the lid closed through `pmset -a disablesleep`.
#
# Session state: storage.root/runtime/awake.json, written atomically under a flock (awake.lock).
#   version            1
#   supervisor_pid     the detached supervisor, or for kind "command" the foreground `ul awake -- ...` process;
#                      null in a "marker" (see lid_restore_failed)
#   caffeinate_pid     the caffeinate child (null in a marker)
#   started, ends      ISO 8601 with offset; ends is null for kinds "on", "pid" and "command"
#   kind               "duration" | "until" | "on" | "pid" | "command"
#   display, lid       the --display / --lid options
#   lid_previous       0 or 1: SleepDisabled before the session; null without --lid. 0 means a restore is owed:
#                      whoever ends the session runs `pmset -a disablesleep 0`
#   lid_restore_failed true when that restore failed; the state then stays as a marker (supervisor_pid null) until
#                      `ul awake off` (or the next session) manages to restore it
#   source             "manual" ("schedule:<id>" for sessions that schedules start)
#   watch_pid, command extras for kinds "pid" and "command"
# Schedules: storage.root/runtime/awake-schedules.json, written atomically under its own flock (awake-schedules.lock).
#   {"version": 1, "schedules": [{id, start "HH:MM", end "HH:MM", days [0-6, Mon=0] or null (every day), date
#   "YYYY-MM-DD" or null (one-off), display, lid, name, created}]}. One LaunchAgent (~/Library/LaunchAgents/
#   com.unlaw.awake.plist) runs `ul awake _scheduled` at every window start (and at load); that run starts a session
#   until the end of the window that contains now.
# A state whose supervisor is not alive (or whose `ps` line is not ours) is stale: it is settled and treated as no
# session. A pid is never signalled unless `ps` confirms the process is ours.

USAGE = """Usage: ul awake [status [--json]]
       ul awake <duration> | until [YYYY-MM-DD] HH:MM | on | off [--display] [--lid]
       ul awake --pid PID | -- <command...>
       ul awake lid setup|remove|status
       ul awake schedule add HH:MM-HH:MM [--days D | --date YYYY-MM-DD] [--display] [--lid] [--name TEXT]
       ul awake schedule list [--json] | rm ID|--all
Run `ul awake --help` for details.
"""

STATE_VERSION = 1
MAX_SECONDS = 7 * 24 * 3600
PMSET = "/usr/bin/pmset"
SUDOERS_FILE = "/etc/sudoers.d/unlaw-awake"
USER_NAME = re.compile(r"[A-Za-z0-9._-]+")
DURATION = re.compile(r"(?:([0-9]{1,9})h)?(?:([0-9]{1,9})m)?(?:([0-9]{1,9})s)?")
SELF = os.path.abspath(__file__)
KINDS_WITH_TIMER = ("duration", "until")
SCHEDULE_VERSION = 1
SCHEDULE_LOCK = "awake-schedules.lock"
JOB_LABEL = "com.unlaw.awake"
DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WINDOW = re.compile(r"([0-9]{1,2}):([0-9]{2})-([0-9]{1,2}):([0-9]{2})")
CLOCK = re.compile(r"([0-9]{2}):([0-9]{2})")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SCHEDULE_USAGE = (
    "use: ul awake schedule add HH:MM-HH:MM [options] | list [--json] | rm ID|--all"
)


class AwakeError(Exception):
    """A problem the user can fix; `code` is the exit status (2 usage, 1 failure)."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Plan:
    """What a session should do. `ends` is a timestamp; schedules set `source` to "schedule:<id>"."""

    kind: str
    seconds: int | None = None
    ends: float | None = None
    watch_pid: int | None = None
    command: list[str] | None = None
    display: bool = False
    lid: bool = False
    source: str = "manual"


# ---------------------------------------------------------------- time


def _local(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp).astimezone()


def _iso(timestamp: float) -> str:
    return _local(timestamp).isoformat(timespec="seconds")


def _span(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def parse_duration(text: str) -> int:
    """`30m`, `2h`, `1h30m`, `45s` or bare minutes (`90`) → seconds, 1 s to 7 days."""
    compact = re.sub(r"\s+", "", text).lower()
    if re.fullmatch(r"[0-9]{1,9}", compact):
        seconds = int(compact) * 60
    else:
        match = DURATION.fullmatch(compact)
        if not compact or match is None:
            raise AwakeError(
                f"not a duration: {text!r} (use 30m, 2h, 1h30m or minutes)"
            )
        hours, minutes, secs = (int(part or 0) for part in match.groups())
        seconds = hours * 3600 + minutes * 60 + secs
    if seconds <= 0:
        raise AwakeError(f"the duration must be longer than zero: {text!r}")
    if seconds > MAX_SECONDS:
        raise AwakeError(f"too long: {text!r} (at most 7 days)")
    return seconds


def parse_until(words: Sequence[str], now: float | None = None) -> float:
    """`HH:MM` (tomorrow when already past) or `YYYY-MM-DD HH:MM`, local time → a timestamp within 7 days."""
    text = " ".join(words).strip()
    now = time.time() if now is None else now
    current = _local(now).replace(tzinfo=None)
    clock = re.fullmatch(r"([0-9]{1,2}):([0-9]{2})", text)
    dated = re.fullmatch(
        r"([0-9]{4})-([0-9]{2})-([0-9]{2})[ T]([0-9]{1,2}):([0-9]{2})", text
    )
    try:
        if clock:
            target = current.replace(
                hour=int(clock[1]), minute=int(clock[2]), second=0, microsecond=0
            )
            if target.timestamp() <= now:
                target += timedelta(days=1)
        elif dated:
            year, month, day, hour, minute = (int(part) for part in dated.groups())
            target = current.replace(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        else:
            raise AwakeError(f"not a time: {text!r} (use HH:MM or YYYY-MM-DD HH:MM)")
    except ValueError as error:
        raise AwakeError(f"not a time: {text!r} ({error})") from error
    timestamp = target.timestamp()
    if timestamp <= now:
        raise AwakeError(f"that time is already past: {text!r}")
    if timestamp - now > MAX_SECONDS:
        raise AwakeError(f"too far away: {text!r} (at most 7 days)")
    return timestamp


# ---------------------------------------------------------------- state


def state_file() -> Path:
    return storage_path("runtime", "awake.json")


@contextmanager
def _locked(name: str = "awake.lock") -> Iterator[None]:
    """Serialize state changes across CLI processes and supervisors; never held while waiting."""
    lock = storage_path("runtime", name)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _read() -> dict | None:
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # missing or damaged: no session
    return data if isinstance(data, dict) else None


def _write(state: dict) -> None:
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".awake.", dir=path.parent)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(state, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_state() -> dict | None:
    """The raw state file (a session, a stale leftover or a marker), or None."""
    with _locked():
        return _read()


def write_state(state: dict) -> None:
    with _locked():
        _write(state)


def clear_state(owner: int | None = None) -> None:
    """Remove the state file; with `owner` only when that supervisor still owns it."""
    with _locked():
        state = _read()
        if (
            owner is not None
            and state is not None
            and state.get("supervisor_pid") != owner
        ):
            return
        state_file().unlink(missing_ok=True)


def _note(message: str) -> None:
    """A loud message on stderr, also in runtime/awake.log (supervisors have no terminal)."""
    print(f"unlaw awake: {message}", file=sys.stderr)
    _log(message)


def _log(message: str) -> None:
    try:
        log = storage_path("runtime", "awake.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{_iso(time.time())} {message}\n")
    except OSError:
        return  # the message is already on stderr


# ---------------------------------------------------------------- processes


def _alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 1:
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


def is_ours(state: dict) -> bool:
    """True when the supervisor pid in `state` is alive and `ps` shows it is this command, not a reused pid."""
    pid = state.get("supervisor_pid")
    if not _alive(pid):
        return False
    command = _command_of(pid)
    if state.get("kind") == "command":
        return "awake" in command
    return "_supervise" in command and SELF in command


def _caffeinate_is_ours(pid: object) -> bool:
    return _alive(pid) and "caffeinate" in _command_of(pid)  # type: ignore[arg-type]


def _wait_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


# ---------------------------------------------------------------- pmset / sudo (lid)


def read_sleep_disabled() -> bool | None:
    """SleepDisabled from `pmset -g`; None when pmset is missing or does not say."""
    pmset = shutil.which("pmset")
    if pmset is None:
        return None
    try:
        result = subprocess.run(
            [pmset, "-g"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"^\s*SleepDisabled\s+([01])\s*$", result.stdout, re.MULTILINE)
    return None if match is None else match[1] == "1"


def _on_battery() -> bool:
    pmset = shutil.which("pmset")
    if pmset is None:
        return False
    try:
        result = subprocess.run(
            [pmset, "-g", "batt"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "Battery Power" in result.stdout


def _sudo(*arguments: str) -> bool:
    try:
        result = subprocess.run(
            ["sudo", "-n", *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def set_sleep_disabled(disabled: bool) -> bool:
    """`sudo -n pmset -a disablesleep 1|0`; only works through the sudoers rule from `ul awake lid setup`."""
    return _sudo(PMSET, "-a", "disablesleep", "1" if disabled else "0")


def lid_rule_works() -> bool:
    return all(_sudo("-l", PMSET, "-a", "disablesleep", value) for value in ("1", "0"))


def _require_lid_rule() -> None:
    if not lid_rule_works():
        raise AwakeError(
            "--lid needs a sudoers rule that lets pmset change lid sleep without a password: run `ul awake lid setup`",
            1,
        )


# ---------------------------------------------------------------- sessions


def _base_state(plan: Plan, lid_previous: int | None) -> dict:
    return {
        "version": STATE_VERSION,
        "supervisor_pid": None,
        "caffeinate_pid": None,
        "started": _iso(time.time()),
        "ends": None if plan.ends is None else _iso(plan.ends),
        "kind": plan.kind,
        "display": plan.display,
        "lid": plan.lid,
        "lid_previous": lid_previous,
        "lid_restore_failed": False,
        "source": plan.source,
        "watch_pid": plan.watch_pid,
        "command": None if plan.command is None else shlex.join(plan.command),
    }


def caffeinate_args(
    caffeinate: str, state: dict, seconds: int | None, watch_pid: int | None
) -> list[str]:
    """-i (idle sleep) and -s (system sleep on AC), -d with the display, -t for timed sessions, -w to follow a pid."""
    args = [caffeinate, "-i", "-s"]
    if state["display"]:
        args.append("-d")
    if state["kind"] in KINDS_WITH_TIMER and seconds is not None:
        args += ["-t", str(seconds)]
    if watch_pid is not None:
        args += ["-w", str(watch_pid)]
    return args


def describe(state: dict) -> str:
    kind = state.get("kind")
    ends = state.get("ends")
    when = (
        f" until {datetime.fromisoformat(ends).astimezone():%Y-%m-%d %H:%M}"
        if ends
        else ""
    )
    if kind == "pid":
        return f"while process {state.get('watch_pid')} lives"
    if kind == "command":
        return f"while `{state.get('command')}` runs"
    if kind == "on":
        return "on, until `ul awake off`"
    return f"{kind}{when}"


def live_session() -> dict | None:
    """The running session, or None. Stale state (dead or foreign supervisor) is settled on the way."""
    state = read_state()
    if state is None:
        return None
    if state.get("supervisor_pid") is None:
        return None  # a marker, not a session (see lid_restore_failed)
    if is_ours(state):
        return state
    _settle_stale(state)
    return None


def _settle_stale(state: dict) -> None:
    """A session whose supervisor died (kill -9, reboot): stop its caffeinate and repay the lid setting."""
    pid = state.get("caffeinate_pid")
    if _caffeinate_is_ours(pid):
        os.kill(pid, signal.SIGTERM)
    if state.get("lid_previous") == 0 and not set_sleep_disabled(False):
        _mark_restore_failed(state, owner=state.get("supervisor_pid"))
        return
    clear_state(owner=state.get("supervisor_pid"))


def _mark_restore_failed(state: dict, owner: int | None) -> None:
    """Keep a marker so `ul awake status` and `ul awake off` know lid sleep is still disabled."""
    with _locked():
        current = _read()
        if current is not None and current.get("supervisor_pid") != owner:
            return
        _write(
            {
                **state,
                "supervisor_pid": None,
                "caffeinate_pid": None,
                "lid_restore_failed": True,
            }
        )
    _note("lid sleep is still disabled and could not be restored: run `ul awake off`")


def _lid_debt() -> bool:
    """True when an earlier session left lid sleep disabled (marker) and it still cannot be restored."""
    state = read_state()
    if (
        state is None
        or not state.get("lid_restore_failed")
        or state.get("supervisor_pid") is not None
    ):
        return False
    if set_sleep_disabled(False):
        clear_state()
        return False
    return True


def stop_session(state: dict) -> None:
    """Stop a live session: SIGTERM the supervisor (it ends caffeinate and repays the lid), SIGKILL as a last resort."""
    pid = state["supervisor_pid"]
    if not is_ours(state):
        return
    if state.get("kind") == "command":
        raise AwakeError(
            f"a `ul awake -- {state.get('command')}` session (pid {pid}) is running; stop that command to end it",
            1,
        )
    os.kill(pid, signal.SIGTERM)
    if _wait_gone(pid, 10):
        return
    if is_ours(state):
        os.kill(pid, signal.SIGKILL)
        _wait_gone(pid, 5)
    _settle_stale(state)


def _prepare(plan: Plan) -> tuple[int | None, str | None]:
    """Everything before a session starts: lid rule check, replace the running session, set the lid.

    Returns (lid_previous, description of the replaced session). Nothing is stopped when the lid check fails.
    """
    if shutil.which("caffeinate") is None:
        raise AwakeError("caffeinate was not found (it ships with macOS)", 1)
    if plan.lid:
        _require_lid_rule()
    replaced = None
    current = live_session()
    if current is not None:
        replaced = describe(current)
        # Raises for a foreground `-- command` session: that is never replaced.
        stop_session(current)
    lid_previous: int | None = 0 if _lid_debt() else None
    if plan.lid:
        if lid_previous is None:
            disabled = read_sleep_disabled()
            if disabled is None:
                raise AwakeError("could not read SleepDisabled from `pmset -g`", 1)
            lid_previous = 1 if disabled else 0
        if _on_battery():
            _note(
                "warning: on battery power; a closed MacBook stays awake and gets hot in a bag and drains the battery"
            )
        if not set_sleep_disabled(True):
            raise AwakeError(
                "could not run `sudo -n pmset -a disablesleep 1`: run `ul awake lid setup`",
                1,
            )
    return lid_previous, replaced


def _repay_lid(lid_previous: int | None) -> None:
    if lid_previous == 0:
        set_sleep_disabled(False)


def start_session(plan: Plan) -> str | None:
    """Start a detached session (every kind except "command"). Returns the description of a replaced session."""
    lid_previous, replaced = _prepare(plan)
    caffeinate = shutil.which("caffeinate")
    spec = {
        "state": _base_state(plan, lid_previous),
        "caffeinate": caffeinate,
        "seconds": plan.seconds,
        "watch_pid": plan.watch_pid,
    }
    supervisor = subprocess.Popen(
        [sys.executable, SELF, "_supervise", json.dumps(spec)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = read_state()
        if (
            state
            and state.get("supervisor_pid") == supervisor.pid
            and state.get("caffeinate_pid")
        ):
            return replaced
        if supervisor.poll() is not None:
            break
        time.sleep(0.05)
    if supervisor.poll() is None:
        supervisor.terminate()
    _repay_lid(lid_previous)
    raise AwakeError("the session did not start (see runtime/awake.log)", 1)


def supervise(spec: dict) -> int:
    """The detached supervisor: run caffeinate, wait for it or a signal, then clean up."""
    stopped: list[int] = []

    def request_stop(signum: int, frame: object) -> None:
        stopped.append(signum)

    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        signal.signal(getattr(signal, name), request_stop)
    state = spec["state"]
    args = caffeinate_args(
        spec["caffeinate"], state, spec.get("seconds"), spec.get("watch_pid")
    )
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        _note(f"could not start caffeinate: {error}")
        _repay_lid(state.get("lid_previous"))
        return 1
    state = {**state, "supervisor_pid": os.getpid(), "caffeinate_pid": process.pid}
    try:
        write_state(state)
        while process.poll() is None and not stopped:
            time.sleep(0.1)
    finally:
        _terminate(process)
        _finish(state)
    return 0


def _finish(state: dict) -> None:
    """End of any session: repay the lid, then drop the state (or leave a marker when that failed)."""
    if state.get("lid_previous") == 0 and not set_sleep_disabled(False):
        _mark_restore_failed(state, owner=os.getpid())
        return
    clear_state(owner=os.getpid())


def run_command(plan: Plan) -> int:
    """`ul awake -- cmd`: run cmd in the foreground, awake while it runs, exit with its code."""
    assert plan.command is not None
    lid_previous, replaced = _prepare(plan)
    if replaced:
        print(f"Replaced: {replaced}")
    try:
        child = subprocess.Popen(plan.command)
    except FileNotFoundError:
        _repay_lid(lid_previous)
        print(f"unlaw awake: command not found: {plan.command[0]}", file=sys.stderr)
        return 127
    except OSError as error:
        _repay_lid(lid_previous)
        print(f"unlaw awake: cannot run {plan.command[0]}: {error}", file=sys.stderr)
        return 126
    state = _base_state(plan, lid_previous)
    state["supervisor_pid"] = os.getpid()
    caffeinate = None
    previous: dict[int, object] = {}
    try:

        def forward(signum: int, frame: object) -> None:
            if child.poll() is None:
                child.send_signal(signum)

        for number in (signal.SIGTERM, signal.SIGHUP):
            previous[number] = signal.signal(number, forward)
        # A terminal's Ctrl-C reaches the child itself; like a shell, wait for it instead of dying first.
        previous[signal.SIGINT] = signal.signal(signal.SIGINT, signal.SIG_IGN)
        args = caffeinate_args(
            shutil.which("caffeinate") or "caffeinate", state, None, child.pid
        )
        caffeinate = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        state["caffeinate_pid"] = caffeinate.pid
        write_state(state)
        code = child.wait()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        if caffeinate is not None:
            _terminate(caffeinate)
        for number, handler in previous.items():
            signal.signal(number, handler)  # type: ignore[arg-type]
        _finish(state)
    return 128 - code if code < 0 else code


# ---------------------------------------------------------------- status


def status_info() -> dict:
    """The stable status record used by `status --json` (keys are always present)."""
    session = live_session()
    marker = None if session else read_state()
    remaining = None
    if session and session.get("ends"):
        remaining = max(
            0, round(datetime.fromisoformat(session["ends"]).timestamp() - time.time())
        )
    return {
        "active": session is not None,
        "kind": session.get("kind") if session else None,
        "started": session.get("started") if session else None,
        "ends": session.get("ends") if session else None,
        "remaining_seconds": remaining,
        "display": bool(session and session.get("display")),
        "lid": bool(session and session.get("lid")),
        "source": session.get("source") if session else None,
        "supervisor_pid": session.get("supervisor_pid") if session else None,
        "caffeinate_pid": session.get("caffeinate_pid") if session else None,
        "sleep_disabled": read_sleep_disabled(),
        "lid_restore_failed": bool(marker and marker.get("lid_restore_failed")),
    }


def _status_text(info: dict) -> str:
    lines = []
    if info["active"]:
        state = read_state() or {}
        lines.append(f"Awake: on, {describe(state)}")
        if info["remaining_seconds"] is not None:
            lines[0] += f" ({_span(info['remaining_seconds'])} left)"
        lines.append(f"  display: {'stays on' if info['display'] else 'may sleep'}")
        lines.append(
            f"  lid: {'closed lid stays awake' if info['lid'] else 'not held (use --lid)'}"
        )
        lines.append(f"  started {info['started']}, source {info['source']}")
    else:
        lines.append("Awake: off")
    if info["lid_restore_failed"]:
        lines.append("Lid sleep is still disabled: run `ul awake off` to restore it.")
    elif info["sleep_disabled"]:
        lines.append("SleepDisabled=1: lid sleep is disabled on this Mac.")
    return "\n".join(lines)


def stop_command() -> int:
    session = live_session()
    if session is not None:
        description = describe(session)
        stop_session(session)
        marker = read_state()
        if marker and marker.get("lid_restore_failed"):
            print(
                f"Awake stopped ({description}), but lid sleep is still disabled.",
                file=sys.stderr,
            )
            print(
                "unlaw awake: could not restore lid sleep; fix `ul awake lid status`, then run `ul awake off`",
                file=sys.stderr,
            )
            return 1
        print(f"Awake stopped ({description}).")
        return 0
    marker = read_state()
    if marker and marker.get("lid_restore_failed"):
        if set_sleep_disabled(False):
            clear_state()
            print("Lid sleep restored.")
            return 0
        raise AwakeError(
            "lid sleep is still disabled and could not be restored; check `ul awake lid status`",
            1,
        )
    print("Nothing to stop: awake is off.")
    return 0


# ---------------------------------------------------------------- lid setup


def _confirm(yes: bool) -> bool:
    if yes:
        return True
    try:
        answer = input("Continue? [y/N] ")
    except EOFError:
        print()
        return False
    return answer.strip().lower() in {"y", "yes"}


def sudoers_rule(user: str) -> str:
    if not USER_NAME.fullmatch(user):
        raise AwakeError(
            f"user name {user!r} has characters that are not allowed in the sudoers rule"
        )
    return f"{user} ALL=(root) NOPASSWD: {PMSET} -a disablesleep 0, {PMSET} -a disablesleep 1"


def lid_setup(yes: bool) -> int:
    try:
        user = getpass.getuser()
    except (KeyError, OSError) as error:
        raise AwakeError(f"could not find the current user name: {error}", 1) from error
    rule = sudoers_rule(user)
    print(f"Will install a sudoers rule in {SUDOERS_FILE} (root:wheel, mode 0440):")
    print(f"  {rule}")
    print(
        "It lets you run exactly those two pmset commands without a password, nothing else."
    )
    print(
        "Steps: check it with `visudo -cf`, then `sudo install ...` (sudo asks for your password once)."
    )
    if not _confirm(yes):
        print("Cancelled.")
        return 1
    content = f"# Written by `ul awake lid setup`. Remove with `ul awake lid remove`.\n{rule}\n"
    visudo = shutil.which("visudo") or "/usr/sbin/visudo"
    with tempfile.TemporaryDirectory(prefix="unlaw-awake-") as folder:
        candidate = Path(folder) / "unlaw-awake"
        candidate.write_text(content, encoding="utf-8")
        candidate.chmod(0o600)
        try:
            check = subprocess.run(
                [visudo, "-cf", str(candidate)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise AwakeError(f"could not run visudo: {error}", 1) from error
        if check.returncode != 0:
            detail = (check.stdout + check.stderr).strip()
            raise AwakeError(
                f"visudo rejected the rule, nothing was installed: {detail}", 1
            )
        try:
            install = subprocess.run(
                [
                    "sudo",
                    "install",
                    "-m",
                    "0440",
                    "-o",
                    "root",
                    "-g",
                    "wheel",
                    str(candidate),
                    SUDOERS_FILE,
                ],
                check=False,
            )
        except OSError as error:
            raise AwakeError(f"could not run sudo: {error}", 1) from error
    if install.returncode != 0:
        raise AwakeError("sudo could not install the rule", 1)
    print(f"Installed {SUDOERS_FILE}. `ul awake --lid` is ready.")
    return 0


def lid_remove(yes: bool) -> int:
    print(f"Will run: sudo rm -f {SUDOERS_FILE}")
    print(
        "After that `ul awake --lid` stops working until `ul awake lid setup` is run again."
    )
    if not _confirm(yes):
        print("Cancelled.")
        return 1
    try:
        result = subprocess.run(["sudo", "rm", "-f", SUDOERS_FILE], check=False)
    except OSError as error:
        raise AwakeError(f"could not run sudo: {error}", 1) from error
    if result.returncode != 0:
        raise AwakeError("sudo could not remove the rule", 1)
    print(f"Removed {SUDOERS_FILE}.")
    return 0


def lid_status() -> int:
    if lid_rule_works():
        print(
            "Lid rule: ready (`sudo -n pmset -a disablesleep 0|1` works without a password)."
        )
        return 0
    print("Lid rule: not installed or not working. Run `ul awake lid setup`.")
    return 1


# ---------------------------------------------------------------- schedules


def schedules_file() -> Path:
    return storage_path("runtime", "awake-schedules.json")


def _damaged(path: Path, why: str) -> AwakeError:
    return AwakeError(f"{path} is damaged ({why}); fix or delete it", 1)


def _valid_schedule(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    days = item.get("days")
    day = item.get("date")
    try:
        if day is not None:
            date.fromisoformat(day)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(item.get("id"), int)
        and all(
            isinstance(item.get(key), str) and CLOCK.fullmatch(item[key])
            for key in ("start", "end")
        )
        and (
            days is None
            or (
                isinstance(days, list)
                and all(isinstance(d, int) and 0 <= d <= 6 for d in days)
            )
        )
    )


def load_schedules() -> list[dict]:
    """The stored schedules; a missing file is none, a damaged one an error (it is never overwritten)."""
    path = schedules_file()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as error:
        raise AwakeError(f"cannot read {path}: {error}", 1) from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise _damaged(path, "not JSON") from error
    items = data.get("schedules") if isinstance(data, dict) else None
    if not isinstance(items, list) or not all(_valid_schedule(i) for i in items):
        raise _damaged(path, "unexpected content")
    return items


def _save_schedules(items: list[dict]) -> None:
    path = schedules_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".awake-schedules.", dir=path.parent)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump({"version": SCHEDULE_VERSION, "schedules": items}, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def parse_window(text: str) -> tuple[str, str]:
    """`HH:MM-HH:MM` → ("HH:MM", "HH:MM"). The end may be earlier (the window crosses midnight), never equal."""
    match = WINDOW.fullmatch(text.strip())
    if match is None:
        raise AwakeError(f"not a window: {text!r} (use HH:MM-HH:MM, like 23:00-06:00)")
    hour1, minute1, hour2, minute2 = (int(part) for part in match.groups())
    if hour1 > 23 or hour2 > 23 or minute1 > 59 or minute2 > 59:
        raise AwakeError(f"not a window: {text!r} (hours 0-23, minutes 0-59)")
    if (hour1, minute1) == (hour2, minute2):
        raise AwakeError(f"the window is empty: {text!r} (start and end are the same)")
    return f"{hour1:02d}:{minute1:02d}", f"{hour2:02d}:{minute2:02d}"


def parse_days(text: str) -> list[int] | None:
    """`daily`, `weekdays`, `weekends` or `mon,tue,...` (English short names, any case) → weekdays Mon=0, None = daily."""
    word = text.strip().lower()
    groups = {
        "daily": None,
        "weekdays": [0, 1, 2, 3, 4],
        "weekends": [5, 6],
    }
    if word in groups:
        return groups[word]
    days: set[int] = set()
    for part in word.split(","):
        if part.strip() not in DAY_NAMES:
            raise AwakeError(
                f"not a day list: {text!r} (use daily, weekdays, weekends or mon,tue,wed,thu,fri,sat,sun)"
            )
        days.add(DAY_NAMES.index(part.strip()))
    return None if len(days) == 7 else sorted(days)


def parse_date(text: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text.strip()):
        raise AwakeError(f"not a date: {text!r} (use YYYY-MM-DD)")
    try:
        return date.fromisoformat(text.strip()).isoformat()
    except ValueError as error:
        raise AwakeError(f"not a date: {text!r} ({error})") from error


def _clean_name(text: str) -> str:
    name = text.strip()
    if CONTROL.search(name):
        raise AwakeError("the name has control characters")
    if len(name) > 60:
        raise AwakeError("the name is longer than 60 characters")
    return name


def _hm(text: str) -> clock_time:
    hour, minute = text.split(":")
    return clock_time(int(hour), int(minute))


def _window_on(item: dict, day: date) -> tuple[float, float]:
    """The window that starts on `day` as local timestamps; it ends the next day when end < start."""
    start = datetime.combine(day, _hm(item["start"]))
    end = datetime.combine(day, _hm(item["end"]))
    if end <= start:
        end += timedelta(days=1)
    return start.timestamp(), end.timestamp()


def _starts_on(item: dict, day: date) -> bool:
    if item.get("date"):
        return item["date"] == day.isoformat()
    days = item.get("days")
    return days is None or day.weekday() in days


def open_window(item: dict, now: float) -> tuple[float, float] | None:
    """The window of `item` that contains `now`. Yesterday's counts too: it may run past midnight."""
    today = _local(now).date()
    for day in (today - timedelta(days=1), today):
        if _starts_on(item, day):
            start, end = _window_on(item, day)
            if start <= now < end:
                return start, end
    return None


def next_start(item: dict, now: float) -> float | None:
    today = _local(now).date()
    for offset in range(8):
        day = today + timedelta(days=offset)
        if _starts_on(item, day):
            start, _ = _window_on(item, day)
            if start > now:
                return start
    return None


def _is_over(item: dict, now: float) -> bool:
    """A one-off whose window has ended."""
    if not item.get("date"):
        return False
    return _window_on(item, date.fromisoformat(item["date"]))[1] <= now


def _days_label(item: dict) -> str:
    if item.get("date"):
        return item["date"]
    days = item.get("days")
    if days is None:
        return "daily"
    if days == [0, 1, 2, 3, 4]:
        return "weekdays"
    if days == [5, 6]:
        return "weekends"
    return ",".join(DAY_NAMES[d] for d in days)


# ---------------------------------------------------------------- the launchd job


def _job_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{JOB_LABEL}.plist"


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
        raise AwakeError(f"could not run launchctl: {error}", 1) from error


def _target() -> str:
    return f"gui/{os.getuid()}/{JOB_LABEL}"


def calendar_intervals(items: list[dict]) -> list[dict]:
    """One StartCalendarInterval per window start. launchd numbers Sunday 0 (or 7) and Monday 1; we use Mon=0."""
    result: list[dict] = []
    for item in items:
        at = _hm(item["start"])
        if item.get("date"):
            day = date.fromisoformat(item["date"])
            entries = [{"Month": day.month, "Day": day.day}]
        elif item.get("days") is None:
            entries = [{}]
        else:
            entries = [{"Weekday": (d + 1) % 7} for d in item["days"]]
        for entry in entries:
            interval = {**entry, "Hour": at.hour, "Minute": at.minute}
            if interval not in result:
                result.append(interval)
    return result


def _write_job(items: list[dict]) -> Path:
    binary = os.environ.get("UNLAW_BIN", "")
    if not binary:
        raise AwakeError(
            "UNLAW_BIN is not set, so the launchd job cannot find ul; run this through `ul awake`",
            1,
        )
    environment = {
        key: os.environ[key]
        for key in ("PATH", "XDG_CONFIG_HOME", "UNLAW_PYTHON", "HOME")
        if os.environ.get(key)
    }
    environment.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    log = storage_path("runtime", "awake-launchd.log")
    plist = {
        "Label": JOB_LABEL,
        "ProgramArguments": [os.path.abspath(binary), "awake", "_scheduled"],
        "EnvironmentVariables": environment,
        "StartCalendarInterval": calendar_intervals(items),
        # Runs at load too, so a window that is already open starts right away.
        "RunAtLoad": True,
        # The supervisor of a session is a child of this job; launchd must not kill it when the job exits.
        "AbandonProcessGroup": True,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    path = _job_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".awake-plist.", dir=path.parent)
    with os.fdopen(handle, "wb") as stream:
        stream.write(plistlib.dumps(plist))
    os.replace(temporary, path)
    return path


def remove_job() -> None:
    """Boot the job out of launchd and delete its plist."""
    path = _job_path()
    if path.exists():
        _launchctl("bootout", _target())
        path.unlink(missing_ok=True)


def sync_job(items: list[dict]) -> None:
    """Make launchd match `items`: write the plist and reload it, or remove the job when nothing is scheduled."""
    if not items:
        remove_job()
        return
    path = _write_job(items)
    _launchctl("bootout", _target())
    result = _launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise AwakeError(
            f"launchctl bootstrap failed: {detail} (the schedules are saved; add or remove one to try again)",
            1,
        )


# ---------------------------------------------------------------- schedule commands


def _printable(text: str) -> str:
    return CONTROL.sub("?", text)


def _fmt(timestamp: float | None) -> str:
    return "-" if timestamp is None else f"{_local(timestamp):%Y-%m-%d %H:%M}"


def _reject_options(args: list[str]) -> None:
    unknown = next((arg for arg in args if arg.startswith("-")), None)
    if unknown is not None:
        raise AwakeError(f"unknown option: {unknown}")


def schedule_add(args: list[str]) -> int:
    display, lid = _flag(args, "--display"), _flag(args, "--lid")
    days_text, date_text = _take(args, "--days"), _take(args, "--date")
    name_text = _take(args, "--name")
    _reject_options(args)
    if len(args) != 1:
        raise AwakeError("use: ul awake schedule add HH:MM-HH:MM [options]")
    start, end = parse_window(args[0])
    if days_text is not None and date_text is not None:
        raise AwakeError("--days and --date cannot be used together")
    days = None if days_text is None else parse_days(days_text)
    day = None if date_text is None else parse_date(date_text)
    name = _clean_name(name_text or "")
    now = time.time()
    item = {
        "id": 0,
        "start": start,
        "end": end,
        "days": days,
        "date": day,
        "display": display,
        "lid": lid,
        "name": name,
        "created": _iso(now),
    }
    if _is_over(item, now):
        raise AwakeError(f"that window is already over: {day} {start}-{end}")
    if lid:
        _require_lid_rule()
    with _locked(SCHEDULE_LOCK):
        items = [i for i in load_schedules() if not _is_over(i, now)]
        item["id"] = max((i["id"] for i in items), default=0) + 1
        items.append(item)
        _save_schedules(items)
        sync_job(items)
    extras = ", ".join(
        label for label, on in (("display", display), ("lid", lid)) if on
    )
    print(
        f"Scheduled {item['id']}: {start}-{end} {_days_label(item)}"
        + (f" ({extras})" if extras else "")
        + f". Next start: {_fmt(next_start(item, now))}."
    )
    return 0


def schedule_list(args: list[str]) -> int:
    as_json = _flag(args, "--json")
    _reject_options(args)
    if args:
        raise AwakeError("use: ul awake schedule list [--json]")
    now = time.time()
    items = load_schedules()
    if as_json:
        rows = []
        for item in items:
            upcoming = next_start(item, now)
            rows.append(
                {**item, "next_start": None if upcoming is None else _iso(upcoming)}
            )
        print(json.dumps({"schedules": rows}, indent=2))
        return 0
    if not items:
        print("No schedules. Add one with: ul awake schedule add HH:MM-HH:MM")
        return 0
    table = [("ID", "WINDOW", "DAYS", "FLAGS", "NAME", "NEXT START")]
    for item in items:
        flags = ",".join(
            label
            for label, on in (("display", item["display"]), ("lid", item["lid"]))
            if on
        )
        table.append(
            (
                str(item["id"]),
                f"{item['start']}-{item['end']}",
                _days_label(item),
                flags or "-",
                _printable(item.get("name") or "-"),
                _fmt(next_start(item, now)),
            )
        )
    widths = [max(len(row[column]) for row in table) for column in range(6)]
    for row in table:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
    return 0


def schedule_rm(args: list[str]) -> int:
    everything = _flag(args, "--all")
    _reject_options(args)
    if everything == bool(args) or len(args) > 1:
        raise AwakeError("use: ul awake schedule rm ID | --all")
    wanted = None
    if args:
        if not re.fullmatch(r"[0-9]{1,9}", args[0]):
            raise AwakeError(f"not a schedule id: {args[0]!r}")
        wanted = int(args[0])
    with _locked(SCHEDULE_LOCK):
        items = load_schedules()
        removed = [i for i in items if wanted is None or i["id"] == wanted]
        if wanted is not None and not removed:
            raise AwakeError(f"no schedule with id {wanted}", 1)
        keep = [i for i in items if i not in removed]
        session = live_session()
        if session is not None and session.get("source") in {
            f"schedule:{i['id']}" for i in removed
        }:
            stop_session(session)
        _save_schedules(keep)
        sync_job(keep)
    print("Removed all schedules." if wanted is None else f"Removed schedule {wanted}.")
    return 0


def schedule_main(args: list[str]) -> int:
    if not args:
        raise AwakeError(SCHEDULE_USAGE)
    action, rest = args[0], list(args[1:])
    if action == "add":
        return schedule_add(rest)
    if action in {"list", "ls"}:
        return schedule_list(rest)
    if action in {"rm", "remove"}:
        return schedule_rm(rest)
    raise AwakeError(f"unknown schedule action: {action!r}; {SCHEDULE_USAGE}")


# ---------------------------------------------------------------- the launchd run


def _parse_now(text: str | None) -> float:
    if text is None:
        return time.time()
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError as error:
        raise AwakeError(f"not an ISO time: {text!r}") from error


def _start_due(items: list[dict], now: float) -> None:
    """Start a session for the open window that ends last, unless a better session already runs."""
    due = [(window[1], item) for item in items if (window := open_window(item, now))]
    if not due:
        return
    end, item = max(due, key=lambda pair: pair[0])
    source = f"schedule:{item['id']}"
    current = live_session()
    if current is not None:
        if current.get("kind") == "command":
            _log(f"{source} not started: a `-- command` session is running")
            return
        current_end = (
            datetime.fromisoformat(current["ends"]).timestamp()
            if current.get("ends")
            else None
        )
        if current_end is None or current_end > end + 0.5:
            _log(
                f"{source} not started: the running {current.get('source', 'manual')} session lasts longer"
            )
            return
        if current.get("source") == source and abs(current_end - end) < 1:
            return
    lid = bool(item.get("lid"))
    if lid and not lid_rule_works():
        _note(
            f"{source}: the sudoers rule for --lid is gone, keeping awake with the lid open only (run `ul awake lid setup`)"
        )
        lid = False
    plan = Plan(
        "until",
        seconds=max(1, math.ceil(end - now)),
        ends=end,
        display=bool(item.get("display")),
        lid=lid,
        source=source,
    )
    replaced = start_session(plan)
    _log(
        f"started {source} until {_iso(end)}"
        + (f" (replaced: {replaced})" if replaced else "")
    )


def run_scheduled(args: list[str]) -> int:
    """`ul awake _scheduled [--now ISO]`: what the launchd job runs. Exit 0 when there is nothing to do."""
    now_text = _take(args, "--now")
    if args:
        raise AwakeError("_scheduled takes only --now ISO")
    now = _parse_now(now_text)
    code = 0
    with _locked(SCHEDULE_LOCK):
        items = load_schedules()
        live = [i for i in items if not _is_over(i, now)]
        try:
            _start_due(live, now)
        except AwakeError as error:
            _note(str(error))
            code = 1
        if len(live) != len(items):
            _log(f"dropped {len(items) - len(live)} past one-off schedule(s)")
            _save_schedules(live)
            if live:
                # Rewritten, not reloaded: bootout would kill this very run; launchd reads it at the next load.
                _write_job(live)
            else:
                remove_job()  # last, because launchd stops this job as part of the bootout
    return code


# ---------------------------------------------------------------- CLI


def _flag(args: list[str], name: str) -> bool:
    found = name in args
    args[:] = [arg for arg in args if arg != name]
    return found


def _take(args: list[str], name: str) -> str | None:
    for index, arg in enumerate(args):
        if arg == name:
            if index + 1 >= len(args):
                raise AwakeError(f"{name} needs a value")
            value = args[index + 1]
            del args[index : index + 2]
            return value
        if arg.startswith(name + "="):
            del args[index]
            return arg[len(name) + 1 :]
    return None


def _pid(text: str) -> int:
    try:
        pid = int(text)
    except ValueError as error:
        raise AwakeError(f"not a process id: {text!r}") from error
    if pid <= 1:
        raise AwakeError(f"not a process id: {text!r}")
    if not _alive(pid):
        raise AwakeError(f"no process with pid {pid}", 1)
    return pid


def _announce(plan: Plan, replaced: str | None) -> None:
    if replaced:
        print(f"Replaced: {replaced}")
    state = _base_state(plan, None)
    extras = (", display stays on" if plan.display else "") + (
        ", lid closed too" if plan.lid else ""
    )
    print(f"Awake {describe(state)}{extras}.")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "_supervise":
        return supervise(json.loads(args[1]))
    command: list[str] | None = None
    if "--" in args:
        split = args.index("--")
        args, command = args[:split], args[split + 1 :]
    if "-h" in args or "--help" in args or args[:1] == ["help"]:
        print(COMMAND_HELP["awake"], end="")
        return 0
    try:
        return _dispatch(args, command)
    except AwakeError as error:
        print(f"unlaw awake: {error}", file=sys.stderr)
        if error.code == 2:
            print(USAGE, end="", file=sys.stderr)
        return error.code
    except ConfigError as error:
        print(f"unlaw awake: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print()
        return 130


def _dispatch(args: list[str], command: list[str] | None) -> int:
    if args[:1] == ["_scheduled"] and command is None:
        return run_scheduled(args[1:])
    if args[:1] == ["schedule"]:
        if command is not None:
            raise AwakeError("schedule does not take `-- command`")
        return schedule_main(args[1:])
    as_json, yes = _flag(args, "--json"), _flag(args, "--yes")
    display, lid = _flag(args, "--display"), _flag(args, "--lid")
    pid_text = _take(args, "--pid")
    unknown = next((arg for arg in args if arg.startswith("-") and len(arg) > 1), None)
    if unknown is not None:
        raise AwakeError(f"unknown option: {unknown}")
    words = args
    options = display or lid
    if words[:1] == ["lid"]:
        if (
            len(words) != 2
            or words[1] not in {"setup", "remove", "status"}
            or options
            or pid_text
            or command
        ):
            raise AwakeError("use: ul awake lid setup|remove|status")
        return {
            "setup": lambda: lid_setup(yes),
            "remove": lambda: lid_remove(yes),
            "status": lid_status,
        }[words[1]]()
    if (as_json or yes) and words[:1] != ["status"] and words:
        raise AwakeError("--json belongs to status and --yes to lid setup/remove")
    if command is not None:
        if words or pid_text:
            raise AwakeError(
                "use either a duration, --pid or `-- command`, not several"
            )
        if not command:
            raise AwakeError("nothing to run after --")
        return run_command(Plan("command", command=command, display=display, lid=lid))
    if pid_text is not None:
        if words:
            raise AwakeError(
                "use either a duration, --pid or `-- command`, not several"
            )
        watched = _pid(pid_text)
        plan = Plan("pid", watch_pid=watched, display=display, lid=lid)
    elif not words or words == ["status"]:
        if options:
            raise AwakeError(
                "--display and --lid need a duration, until, on, --pid or -- command"
            )
        info = status_info()
        print(json.dumps(info, indent=2) if as_json else _status_text(info))
        return 0
    elif words == ["off"]:
        if options:
            raise AwakeError("off takes no options")
        return stop_command()
    elif words == ["on"]:
        plan = Plan("on", display=display, lid=lid)
    elif words[0] == "until":
        ends = parse_until(words[1:])
        plan = Plan(
            "until",
            seconds=max(1, math.ceil(ends - time.time())),
            ends=ends,
            display=display,
            lid=lid,
        )
    else:
        seconds = parse_duration("".join(words))
        plan = Plan(
            "duration",
            seconds=seconds,
            ends=time.time() + seconds,
            display=display,
            lid=lid,
        )
    replaced = start_session(plan)
    _announce(plan, replaced)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
