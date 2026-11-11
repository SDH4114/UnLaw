# ruff: noqa: DTZ001, DTZ005  (schedules are local wall-clock times, so naive datetimes are the point)
"""`ul awake`: the fixes from the review (lid safety, strict state, pid checks, skips), with fakes only."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_awake import FAKE_PMSET, AwakeBase, alive, load_awake, wait_for
from test_awake_schedule import FAKE_LAUNCHCTL, LABEL, window
from ulbin import binary

# Also records whether the plist still exists when launchd is told to boot the job out.
FAKE_LAUNCHCTL_PLIST = FAKE_LAUNCHCTL.replace(
    'open(d + "/launchctl.log"',
    'open(d + "/launchctl.plist", "a").write(("1" if os.path.exists(os.environ["FAKE_PLIST"]) else "0") + sys.argv[1] + "\\n")\n'
    'open(d + "/launchctl.log"',
)

# Records whether the state file already exists when the lid is disabled.
FAKE_PMSET_MARKER = FAKE_PMSET.replace(
    'open(state, "w").write(a[2])',
    'open(d + "/pmset.marker", "a").write(a[2] + ("1" if os.path.exists(os.environ["FAKE_STATE"]) else "0") + "\\n")\n'
    '    open(state, "w").write(a[2])\n'
    '    if a[2] == "1" and os.path.exists(d + "/slow_disable"):\n'
    '        open(d + "/slow_started", "w").write("")\n'
    '        os.remove(d + "/slow_disable")  # only the first disable is slow\n'
    '        __import__("time").sleep(1.5)',
).replace(
    "    value = open(state)",
    '    if os.path.exists(d + "/unknown_state"):\n        raise SystemExit(0)\n    value = open(state)',
)

VALID_STATE = {
    "version": 1,
    "supervisor_pid": None,
    "caffeinate_pid": None,
    "started": "2026-01-01T00:00:00+00:00",
    "ends": None,
    "kind": "on",
    "display": False,
    "lid": False,
    "lid_previous": None,
    "lid_restore_failed": False,
    "source": "manual",
    "watch_pid": None,
    "command": None,
}


class ReviewTests(AwakeBase):
    def setUp(self) -> None:
        super().setUp()
        self.plist_path = self.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        self.env["FAKE_PLIST"] = str(self.plist_path)
        self.env["FAKE_STATE"] = str(self.state_path())
        self.tool("launchctl", f"#!{sys.executable}\n{FAKE_LAUNCHCTL_PLIST}")
        self.tool("pmset", f"#!{sys.executable}\n{FAKE_PMSET_MARKER}")

    # ---------------------------------------------------------------- helpers

    @contextmanager
    def inprocess(self):
        with mock.patch.dict(os.environ, self.env):
            yield load_awake()

    def schedules_path(self) -> Path:
        return self.unlaw / "data" / "runtime" / "awake-schedules.json"

    def document(self) -> dict:
        return json.loads(self.schedules_path().read_text(encoding="utf-8"))

    def add(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.ok("awake", "schedule", "add", *args)

    def plist(self) -> dict:
        return plistlib.loads(self.plist_path.read_bytes())

    def launchctl(self) -> list[list[str]]:
        return self.jlog("launchctl.log")

    def scheduled(self, now: str | None = None) -> subprocess.CompletedProcess[str]:
        return self.ok("awake", "_scheduled", *(["--now", now] if now else []))

    def wait_session(self, source: str | None = None) -> dict:
        self.assertTrue(
            wait_for(
                lambda: (
                    (self.state() or {}).get("caffeinate_pid")
                    and (source is None or self.state().get("source") == source)
                )
            ),
            f"no session {source}",
        )
        return self.state()

    def crash(self) -> None:
        """Kill the supervisor and caffeinate the way a power loss would: no cleanup runs."""
        state = self.state()
        for pid in (state["supervisor_pid"], state["caffeinate_pid"]):
            os.kill(pid, signal.SIGKILL)
        self.assertTrue(wait_for(lambda: not alive(state["supervisor_pid"])))

    def write_state(self, **changes: object) -> None:
        path = self.state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**VALID_STATE, **changes}), encoding="utf-8")

    def dead_pid(self) -> int:
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        return process.pid

    # ---------------------------------------------------------------- 1: lid debt is settled without a manual call

    def test_a_scheduled_run_repays_the_lid_of_a_crashed_session_outside_any_window(
        self,
    ) -> None:
        self.allow_lid()
        self.add(window(-120, 180))
        self.start("on", "--lid")
        self.crash()
        self.assertEqual(self.sleep_disabled(), "1")
        self.scheduled()
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_a_scheduled_run_retries_a_failed_restore_marker(self) -> None:
        self.allow_lid()
        self.add(window(-120, 180))
        (self.fake / "sleepdisabled").write_text("1")
        self.write_state(lid=True, lid_previous=0, lid_restore_failed=True)
        self.scheduled()
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_a_lid_session_installs_a_job_even_without_schedules(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        plist = self.plist()
        self.assertTrue(plist["RunAtLoad"])
        self.assertNotIn("StartCalendarInterval", plist)
        # a supervisor killed without a reboot is repaid within minutes, not at the next login
        self.assertEqual(plist["StartInterval"], 300)
        self.assertEqual(plist["ProgramArguments"][1:], ["awake", "_scheduled"])
        self.assertEqual(self.launchctl()[-1][0], "bootstrap")

    def test_a_job_with_schedules_has_no_poll_interval(self) -> None:
        self.add("09:00-10:00")
        self.assertNotIn("StartInterval", self.plist())
        self.assertIn("StartCalendarInterval", self.plist())

    def test_the_settle_only_job_goes_when_a_lid_session_ends_by_itself(self) -> None:
        self.allow_lid()
        self.start("2s", "--lid")
        self.assertTrue(self.plist_path.exists())
        self.assertTrue(wait_for(lambda: self.state() is None))
        self.assertTrue(wait_for(lambda: not self.plist_path.exists()))
        self.assertEqual(self.sleep_disabled(), "0")

    def test_the_job_with_schedules_stays_when_a_lid_session_ends_by_itself(
        self,
    ) -> None:
        self.allow_lid()
        self.add("09:00-10:00")
        self.start("2s", "--lid")
        self.assertTrue(wait_for(lambda: self.state() is None))
        time.sleep(0.5)
        self.assertTrue(self.plist_path.exists())

    def test_dropping_the_idle_job_never_waits_for_the_schedule_lock(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        self.ok("awake", "off")  # nothing owed now; the job is gone
        self.start("on", "--lid")
        with self.inprocess() as awake, awake._locked(awake.SCHEDULE_LOCK):
            began = time.monotonic()
            awake._drop_idle_job(blocking=False)
            self.assertLess(time.monotonic() - began, 2)
        self.assertTrue(self.plist_path.exists())

    def test_a_failure_to_install_the_login_job_is_a_warning_not_a_traceback(
        self,
    ) -> None:
        with (
            self.inprocess() as awake,
            mock.patch.object(awake, "sync_job", side_effect=OSError("disk full")),
        ):
            awake._ensure_settle_job()  # must not raise

    def test_a_session_without_the_lid_installs_no_job(self) -> None:
        self.start("on")
        self.assertFalse(self.plist_path.exists())
        self.assertEqual(self.launchctl(), [])

    def test_a_lid_command_session_installs_the_job_too(self) -> None:
        self.allow_lid()
        started, release = self.root / "started", self.root / "release"
        wrapper = self.run_in_background(
            "--lid", "--", sys.executable, "-c", self.waiting_script(started, release)
        )
        self.assertTrue(wait_for(started.exists))
        self.assertTrue(wait_for(self.plist_path.exists))
        release.write_text("")
        self.assertEqual(wrapper.wait(timeout=10), 0)

    def test_the_login_run_settles_a_crash_and_removes_the_settle_only_job(
        self,
    ) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        self.crash()
        self.scheduled()
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertFalse(self.plist_path.exists())
        self.assertEqual(self.launchctl()[-1][0], "bootout")

    def test_the_settle_only_job_stays_while_the_lid_is_still_held(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        self.scheduled()
        self.assertTrue(self.plist_path.exists())
        self.assertEqual(self.sleep_disabled(), "1")
        self.assertTrue(self.status()["active"])

    def test_the_job_stays_when_a_failed_restore_cannot_be_repaid_yet(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        self.crash()
        (self.fake / "sudo_fail_restore").write_text("")
        self.scheduled()
        self.assertTrue(self.plist_path.exists())
        self.assertTrue(self.state()["lid_restore_failed"])

    def test_removing_the_last_schedule_keeps_the_job_while_the_lid_is_held(
        self,
    ) -> None:
        self.allow_lid()
        self.add("09:00-10:00")
        self.start("on", "--lid")
        self.ok("awake", "schedule", "rm", "--all")
        self.assertNotIn("StartCalendarInterval", self.plist())

    def test_off_removes_the_idle_settle_job(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        self.assertTrue(self.plist_path.exists())
        self.ok("awake", "off")
        self.assertFalse(self.plist_path.exists())

    def test_off_keeps_the_job_when_schedules_exist(self) -> None:
        self.allow_lid()
        self.add("09:00-10:00")
        self.start("on", "--lid")
        self.ok("awake", "off")
        self.assertTrue(self.plist_path.exists())

    def test_help_says_what_happens_after_a_crash(self) -> None:
        text = self.ok("awake", "--help").stdout
        self.assertIn("next login", text)
        self.assertLess(len(text.splitlines()), 30)

    # ---------------------------------------------------------------- 2: no lid leak while a start fails

    def test_the_state_exists_before_the_lid_is_disabled(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        # the last write is the real one (the rule probe before it writes the old value back): state existed
        self.assertEqual(self.read("pmset.marker").split()[-1], "11")

    def test_a_start_killed_right_after_disabling_the_lid_leaves_a_marker_that_is_repaid(
        self,
    ) -> None:
        self.allow_lid()
        (self.fake / "die_after_disable").write_text("")
        result = self.ul("awake", "1h", "--lid")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.sleep_disabled(), "1")
        marker = self.state()
        self.assertIsNotNone(marker, "the debt must be on record")
        self.assertEqual(marker["lid_previous"], 0)
        (self.fake / "die_after_disable").unlink()
        self.assertFalse(self.status()["active"])
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def start_plan(self, awake, **extra):
        return awake.Plan(
            "duration",
            seconds=60,
            ends=datetime.now().timestamp() + 60,
            lid=True,
            **extra,
        )

    def failing_popen(self, awake, error: BaseException):
        real = subprocess.Popen

        def popen(args, *more, **kwargs):
            if args and args[0] == sys.executable:  # the supervisor
                raise error
            return real(args, *more, **kwargs)

        return mock.patch.object(awake.subprocess, "Popen", popen)

    def test_a_supervisor_that_cannot_be_started_repays_the_lid(self) -> None:
        self.allow_lid()
        with (
            self.inprocess() as awake,
            self.failing_popen(awake, OSError("boom")),
            self.assertRaises(awake.AwakeError),
        ):
            awake.start_session(self.start_plan(awake))
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_an_interrupted_start_repays_the_lid_and_reraises(self) -> None:
        self.allow_lid()
        with (
            self.inprocess() as awake,
            self.failing_popen(awake, KeyboardInterrupt()),
            self.assertRaises(KeyboardInterrupt),
        ):
            awake.start_session(self.start_plan(awake))
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_a_command_that_cannot_be_executed_repays_the_lid(self) -> None:
        self.allow_lid()
        plain = self.root / "plain"
        plain.write_text("not executable")
        result = self.ul("awake", "--lid", "--", str(plain))
        self.assertEqual(result.returncode, 126, result.stderr)
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_an_interrupted_command_start_repays_the_lid(self) -> None:
        self.allow_lid()
        real = subprocess.Popen

        def interrupt(args, *more, **kwargs):
            if args == ["the-command"]:
                raise KeyboardInterrupt
            return real(args, *more, **kwargs)

        with self.inprocess() as awake:
            plan = awake.Plan("command", command=["the-command"], lid=True)
            with (
                mock.patch.object(awake.subprocess, "Popen", interrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                awake.run_command(plan)
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    # ---------------------------------------------------------------- 4: signals to processes that just died

    def test_stopping_a_session_whose_supervisor_just_died_does_not_crash(self) -> None:
        state = {**VALID_STATE, "kind": "duration", "supervisor_pid": self.dead_pid()}
        with (
            self.inprocess() as awake,
            mock.patch.object(awake, "is_ours", return_value=True),
        ):
            awake.stop_session(state)

    def test_settling_a_session_whose_caffeinate_just_died_does_not_crash(self) -> None:
        state = {**VALID_STATE, "caffeinate_pid": self.dead_pid()}
        with (
            self.inprocess() as awake,
            mock.patch.object(awake, "_caffeinate_is_ours", return_value=True),
        ):
            awake._settle_stale(state)

    def test_a_signal_that_is_not_permitted_is_an_error_not_a_traceback(self) -> None:
        state = {**VALID_STATE, "kind": "duration", "supervisor_pid": os.getpid()}
        with (
            self.inprocess() as awake,
            mock.patch.object(awake, "is_ours", return_value=True),
            mock.patch.object(awake.os, "kill", side_effect=PermissionError),
            mock.patch.object(awake, "_wait_gone", return_value=False),
            self.assertRaises(awake.AwakeError),
        ):
            awake.stop_session(state)

    def test_back_to_back_windows_do_not_crash_the_scheduled_run(self) -> None:
        self.add(window(30, 60))
        self.add(window(30, 120))
        soon = (datetime.now().astimezone() + timedelta(minutes=5)).isoformat()
        self.write_state(
            kind="until",
            source="schedule:1",
            supervisor_pid=self.dead_pid(),
            caffeinate_pid=None,
            ends=soon,
        )
        seed = (
            self.unlaw / "commands" / "awake" / "main.py"
        )  # the supervisor must run the seed
        with (
            self.inprocess() as awake,
            mock.patch.object(awake, "SELF", str(seed)),
            mock.patch.object(awake, "is_ours", return_value=True),
        ):
            self.assertEqual(awake.run_scheduled([]), 0)
        self.assertEqual(self.wait_session("schedule:2")["source"], "schedule:2")

    # ---------------------------------------------------------------- 5: a replaced session keeps its flags

    def test_a_scheduled_start_keeps_the_display_and_lid_of_the_session_it_replaces(
        self,
    ) -> None:
        self.allow_lid()
        self.add(window(30, 120))
        self.start("30m", "--lid", "--display")
        self.scheduled()
        state = self.wait_session("schedule:1")
        self.assertTrue(state["lid"])
        self.assertTrue(state["display"])
        self.assertEqual(self.sleep_disabled(), "1")

    def test_a_scheduled_start_never_drops_a_lid_it_can_no_longer_keep(self) -> None:
        self.allow_lid()
        self.add(window(30, 120))
        self.start("30m", "--lid")
        pid = self.state()["supervisor_pid"]
        (self.fake / "rule_ok").unlink()
        self.scheduled()
        self.assertEqual(self.state()["supervisor_pid"], pid)
        self.assertEqual(self.state()["source"], "manual")

    # ---------------------------------------------------------------- 6: remove_job

    def test_the_plist_is_deleted_before_launchd_is_told_to_boot_out(self) -> None:
        self.add("09:00-10:00")
        self.ok("awake", "schedule", "rm", "--all")
        lines = self.read("launchctl.plist").split()
        self.assertEqual(lines[-1], "0bootout", "the plist must be gone at bootout")
        self.assertEqual(self.launchctl()[-1][-1].rsplit("/", 1)[-1], LABEL)

    # ---------------------------------------------------------------- 8: pids are checked, not trusted

    def test_the_state_records_when_the_processes_started(self) -> None:
        self.start("on")
        state = self.state()
        self.assertTrue(state["supervisor_lstart"])
        self.assertTrue(state["caffeinate_lstart"])

    def test_a_reused_pid_with_another_start_time_is_never_signalled(self) -> None:
        self.start("on")
        state = self.state()
        self.addCleanup(
            lambda: (
                alive(state["supervisor_pid"])
                and os.kill(state["supervisor_pid"], signal.SIGKILL)
            )
        )
        self.write_state(
            **{
                **state,
                "supervisor_lstart": "Mon Jan  1 00:00:00 2001",
                "caffeinate_lstart": "Mon Jan  1 00:00:00 2001",
            }
        )
        self.assertFalse(self.status()["active"])
        self.assertTrue(alive(state["supervisor_pid"]))
        self.assertTrue(alive(state["caffeinate_pid"]))

    def test_a_process_that_only_mentions_caffeinate_is_never_signalled(self) -> None:
        bystander = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)", "caffeinate"]
        )
        self.addCleanup(lambda: (bystander.kill(), bystander.wait()))
        self.write_state(supervisor_pid=self.dead_pid(), caffeinate_pid=bystander.pid)
        self.assertFalse(self.status()["active"])
        self.assertIsNone(bystander.poll())

    # ---------------------------------------------------------------- 9: hand-edited files

    def test_damaged_schedules_give_a_clear_error_never_a_traceback(self) -> None:
        good = {
            "id": 1,
            "start": "09:00",
            "end": "10:00",
            "days": None,
            "date": None,
            "display": False,
            "lid": False,
            "name": "",
            "created": "2026-01-01T00:00:00+00:00",
        }
        cases = {
            "hour 25": {**good, "start": "25:00"},
            "minute 61": {**good, "end": "10:61"},
            "same start and end": {**good, "end": "09:00"},
            "bool id": {**good, "id": True},
            "string id": {**good, "id": "1"},
            "missing key": {k: v for k, v in good.items() if k != "name"},
            "bool day": {**good, "days": [True]},
            "empty days": {**good, "days": []},
            "display not bool": {**good, "display": "yes"},
            "name not str": {**good, "name": 5},
            "bad date": {**good, "date": "2026-13-45"},
        }
        for label, item in cases.items():
            with self.subTest(label):
                path = self.schedules_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"version": 1, "schedules": [item]}), encoding="utf-8"
                )
                for args in (("schedule", "list"), ("_scheduled",)):
                    result = self.ul("awake", *args)
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertIn("awake-schedules.json", result.stderr)

    def test_duplicate_ids_and_a_wrong_version_are_damage(self) -> None:
        self.add("09:00-10:00")
        document = self.document()
        for broken in (
            {**document, "version": 2},
            {**document, "schedules": document["schedules"] * 2},
            {**document, "skipped": "no"},
            {**document, "skipped": [{"id": 1}]},
        ):
            self.schedules_path().write_text(json.dumps(broken), encoding="utf-8")
            result = self.ul("awake", "schedule", "list")
            self.assertEqual(result.returncode, 1, broken)
            self.assertNotIn("Traceback", result.stderr)

    def test_a_state_with_wrong_types_counts_as_no_session(self) -> None:
        for changes in (
            {"ends": "garbage"},
            {"supervisor_pid": "x"},
            {"supervisor_pid": True},
            {"kind": 5},
            {"kind": "nonsense"},
            {"lid_previous": 7},
            {"display": "no"},
        ):
            with self.subTest(changes):
                self.write_state(**changes)
                result = self.ok("awake", "status", "--json")
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(json.loads(result.stdout)["active"])
        self.start("10m")
        self.assertTrue(self.status()["active"])

    # ---------------------------------------------------------------- 10: off during a window

    def test_off_during_a_scheduled_window_skips_the_rest_of_that_window(self) -> None:
        # A window that does not contain the real now, so only the fake clock decides what is open.
        base = datetime.now() + timedelta(hours=2)
        start, end = base, base + timedelta(hours=1)
        self.add(f"{start:%H:%M}-{end:%H:%M}")
        first = datetime(2030, 1, 2, start.hour, start.minute) + timedelta(minutes=10)
        window_end = datetime(2030, 1, 2, end.hour, end.minute)
        if window_end <= first - timedelta(minutes=10):
            window_end += timedelta(days=1)
        self.scheduled(first.isoformat())
        self.wait_session("schedule:1")
        self.ok("awake", "off")
        (entry,) = self.document()["skipped"]
        self.assertEqual(entry["id"], 1)
        self.assertEqual(
            datetime.fromisoformat(entry["until"]).replace(tzinfo=None), window_end
        )
        starts = len(self.read("caffeinate.log").splitlines())
        self.scheduled((first + timedelta(minutes=10)).isoformat())
        self.assertIsNone(self.state())
        self.assertEqual(len(self.read("caffeinate.log").splitlines()), starts)
        self.scheduled((first + timedelta(days=1)).isoformat())
        self.assertEqual(self.wait_session("schedule:1")["source"], "schedule:1")
        self.assertEqual(self.document()["skipped"], [], "expired skips are dropped")

    def test_off_skips_every_window_that_is_open_not_just_the_running_one(self) -> None:
        self.add(window(30, 60))
        self.add(window(30, 120))
        self.scheduled()
        self.wait_session("schedule:2")
        self.ok("awake", "off")
        self.assertEqual(sorted(e["id"] for e in self.document()["skipped"]), [1, 2])
        self.scheduled()
        self.assertIsNone(self.state())

    def test_off_of_a_manual_session_during_a_window_skips_that_window_too(
        self,
    ) -> None:
        self.add(window())
        self.start("on")
        self.ok("awake", "off")
        (entry,) = self.document()["skipped"]
        self.assertEqual(entry["id"], 1)
        self.scheduled()
        self.assertIsNone(self.state())

    def test_off_of_a_manual_session_outside_any_window_records_nothing(self) -> None:
        self.add(window(-120, 180))
        self.start("on")
        self.ok("awake", "off")
        self.assertEqual(self.document().get("skipped", []), [])

    def test_removing_a_schedule_drops_its_skip(self) -> None:
        self.add(window())
        self.scheduled()
        self.wait_session("schedule:1")
        self.ok("awake", "off")
        self.ok("awake", "schedule", "rm", "1")
        self.assertEqual(self.document().get("skipped", []), [])

    # ---------------------------------------------------------------- round 3

    def test_a_live_session_is_still_ours_under_another_time_zone(self) -> None:
        # `ps -o lstart=` prints local time: the recorded start time must not depend on the caller's TZ
        self.env["TZ"] = "UTC"
        self.allow_lid()
        self.start("on", "--lid")
        for zone in ("Asia/Tokyo", "America/Los_Angeles"):
            data = json.loads(
                self.ok("awake", "status", "--json", env={"TZ": zone}).stdout
            )
            self.assertTrue(data["active"], zone)
        self.assertEqual(self.sleep_disabled(), "1", "the lid must not be given back")

    def test_an_unknown_start_time_never_condemns_a_live_session(self) -> None:
        with self.inprocess() as awake:
            with mock.patch.object(awake, "_lstart", return_value=""):
                self.assertTrue(
                    awake._same_start(os.getpid(), "Mon Jan 1 00:00:00 2001")
                )
            with mock.patch.object(
                awake, "_lstart", return_value="Tue Jan 2 00:00:00 2001"
            ):
                self.assertFalse(
                    awake._same_start(os.getpid(), "Mon Jan 1 00:00:00 2001")
                )
                self.assertTrue(awake._same_start(os.getpid(), ""))

    def test_start_times_are_read_in_utc_and_the_c_locale(self) -> None:
        seen = {}
        real = subprocess.run

        def spy(args, *more, **kwargs):
            if args[0] == "ps" and "lstart=" in args:
                seen.update(kwargs.get("env") or {})
            return real(args, *more, **kwargs)

        with (
            self.inprocess() as awake,
            mock.patch.object(awake.subprocess, "run", spy),
        ):
            self.assertTrue(awake._lstart(os.getpid()))
        self.assertEqual((seen.get("TZ"), seen.get("LC_ALL")), ("UTC", "C"))
        self.assertIn("PATH", seen)

    def test_two_starts_at_once_do_not_lose_the_lid_debt(self) -> None:
        self.allow_lid()
        (self.fake / "slow_disable").write_text("")
        first = subprocess.Popen(
            [str(binary()), "awake", "on", "--lid"],
            env=self.env,
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(lambda: (first.kill(), first.wait()))
        # the first has disabled the lid and is still starting: the second must wait for it
        self.assertTrue(wait_for(lambda: (self.fake / "slow_started").exists()))
        second = self.ul("awake", "on", "--lid")
        _, err = first.communicate(timeout=30)
        self.assertEqual(first.returncode, 0, err)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(self.status()["active"])
        # one session only: the second start replaced the first instead of running beside it
        pids = [int(x) for x in self.read("caffeinate.pids").split()]
        self.assertEqual(sum(alive(pid) for pid in pids), 1, pids)
        self.ok("awake", "off")
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_the_start_lock_comes_after_the_schedule_lock(self) -> None:
        # `_scheduled` holds the schedule lock and starts a session (start lock); a start in progress must
        # not deadlock with it: run both orders of arrival
        self.allow_lid()
        self.add(window())
        (self.fake / "slow_disable").write_text("")
        first = subprocess.Popen(
            [str(binary()), "awake", "30m", "--lid"],
            env=self.env,
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(lambda: (first.kill(), first.wait()))
        self.assertTrue(wait_for(lambda: (self.fake / "slow_started").exists()))
        self.ok("awake", "_scheduled")
        first.wait(timeout=30)
        self.assertEqual(first.returncode, 0)
        self.assertTrue(self.status()["active"])

    def test_seed_arguments_survive_spaces_in_the_interpreter_path(self) -> None:
        with self.inprocess() as awake:
            seed = "/Users/some one/.config/unlaw/commands/awake/main.py"
            with mock.patch.object(awake, "SELF", seed):
                cases = {
                    f"/opt/My Apps/Python 3/bin/python3.13 {seed} _supervise {{}}": "_supervise {}",
                    f"/usr/bin/python3 {seed}": "",
                    f"/usr/bin/python3 {seed} -- make build": "-- make build",
                    f"/bin/sleep {seed} _supervise {{}}": None,
                    "/usr/bin/python3 /other/main.py _supervise {}": None,
                    f"/usr/bin/python3 {seed}x _supervise {{}}": None,
                    "": None,
                }
                for command, expected in cases.items():
                    with self.subTest(command=command):
                        self.assertEqual(awake._seed_arguments(command), expected)

    def test_the_rule_probe_never_writes_when_the_setting_is_unknown(self) -> None:
        (self.fake / "rule_ok").write_text("")
        (self.fake / "unknown_state").write_text("")
        result = self.ul("awake", "lid", "status")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.read("pmset.log"), "")
        self.assertEqual(self.ul("awake", "1h", "--lid").returncode, 1)
        self.assertEqual(self.read("pmset.log"), "")

    def test_the_rule_probe_waits_for_the_lid_lock(self) -> None:
        self.allow_lid()
        done = threading.Event()
        with self.inprocess() as awake:
            with awake._locked(awake.LID_LOCK):
                worker = threading.Thread(
                    target=lambda: (awake.lid_rule_works(), done.set()), daemon=True
                )
                worker.start()
                self.assertFalse(
                    done.wait(0.5), "the probe must wait while the lid is being changed"
                )
            self.assertTrue(done.wait(10))
        worker.join(5)

    def test_no_test_can_reach_a_real_tool(self) -> None:
        for name in ("sudo", "pmset", "launchctl", "caffeinate", "visudo"):
            found = shutil.which(name, path=self.env["PATH"])
            self.assertEqual(found, str(self.bin / name), name)
        self.assertEqual(self.env["UNLAW_AWAKE_SUDO"], str(self.bin / "sudo"))

    def test_help_mentions_the_skip(self) -> None:
        self.assertIn("skips", self.ok("awake", "--help").stdout)


if __name__ == "__main__":
    unittest.main()
