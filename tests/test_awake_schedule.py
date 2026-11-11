"""`ul awake schedule` and the hidden `_scheduled` run, with a fake launchctl next to the fake caffeinate."""

# ruff: noqa: DTZ001, DTZ005, DTZ011, PLW1510  (schedules are local wall-clock times, so naive datetimes are the point)
from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_awake import AwakeBase, wait_for
from ulbin import ROOT, binary

FAKE_LAUNCHCTL = """import json, os, sys
d = os.environ["FAKE_DIR"]
open(d + "/launchctl.log", "a").write(json.dumps(sys.argv[1:]) + "\\n")
raise SystemExit(1 if os.path.exists(d + "/launchctl_fail") and sys.argv[1] == "bootstrap" else 0)
"""

LABEL = "com.unlaw.awake"


def clock(moment: datetime) -> str:
    return f"{moment:%H:%M}"


def window(before: int = 30, after: int = 90) -> str:
    """A window that contains the real now: `before` minutes back to `after` minutes ahead."""
    moment = datetime.now()
    return f"{clock(moment - timedelta(minutes=before))}-{clock(moment + timedelta(minutes=after))}"


def end_of_window(text: str) -> datetime:
    """The next occurrence of the end time of 'HH:MM-HH:MM', as a naive local datetime."""
    hour, minute = (int(part) for part in text.split("-")[1].split(":"))
    moment = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return moment if moment > datetime.now() else moment + timedelta(days=1)


class ScheduleTests(AwakeBase):
    def setUp(self) -> None:
        super().setUp()
        self.tool("launchctl", f"#!{sys.executable}\n{FAKE_LAUNCHCTL}")
        self.plist_path = self.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    # ---------------------------------------------------------------- helpers

    def add(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.ok("awake", "schedule", "add", *args)

    def refuse(self, *args: str, code: int = 2) -> subprocess.CompletedProcess[str]:
        result = self.ul("awake", "schedule", *args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def schedules_path(self) -> Path:
        return self.unlaw / "data" / "runtime" / "awake-schedules.json"

    def schedules(self) -> list[dict]:
        path = self.schedules_path()
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))["schedules"]

    def plist(self) -> dict:
        return plistlib.loads(self.plist_path.read_bytes())

    def intervals(self) -> list[dict]:
        return self.plist()["StartCalendarInterval"]

    def launchctl(self) -> list[list[str]]:
        return self.jlog("launchctl.log")

    def run_scheduled(self, now: str | None = None) -> subprocess.CompletedProcess[str]:
        args = ["awake", "_scheduled"] + (["--now", now] if now else [])
        return self.ok(*args)

    def wait_session(self) -> dict:
        self.assertTrue(
            wait_for(lambda: (self.state() or {}).get("caffeinate_pid")),
            "no session started",
        )
        return self.state()

    def no_session(self) -> None:
        self.assertIsNone(self.state())
        self.assertEqual(self.read("caffeinate.log"), "")

    # ---------------------------------------------------------------- help

    def test_help_mentions_schedules_and_stays_short(self) -> None:
        result = self.ok("awake", "--help")
        self.assertIn("schedule add", result.stdout)
        self.assertIn("list [--json]", result.stdout)
        self.assertIn("rm ID|--all", result.stdout)
        self.assertIn("not woken", result.stdout)
        self.assertLess(len(result.stdout.splitlines()), 30)
        self.assertEqual(self.schedules(), [])
        self.assertEqual(self.launchctl(), [])

    def test_schedule_help_has_no_side_effects(self) -> None:
        for args in (("schedule", "add", "-h"), ("schedule", "--help")):
            result = self.ok("awake", *args)
            self.assertIn("schedule add", result.stdout)
        self.assertEqual(self.launchctl(), [])
        self.assertFalse(self.plist_path.exists())

    # ---------------------------------------------------------------- parsing

    def test_a_window_may_cross_midnight(self) -> None:
        self.add("23:00-06:00")
        (item,) = self.schedules()
        self.assertEqual((item["start"], item["end"]), ("23:00", "06:00"))
        self.assertIsNone(item["days"])
        self.assertIsNone(item["date"])
        self.assertEqual(
            (item["display"], item["lid"], item["name"]), (False, False, "")
        )
        self.assertTrue(item["created"])

    def test_single_digit_hours_are_normalised(self) -> None:
        self.add("9:05-17:30")
        self.assertEqual(
            [(s["start"], s["end"]) for s in self.schedules()], [("09:05", "17:30")]
        )

    def test_bad_windows_are_refused_and_change_nothing(self) -> None:
        for window_text in (
            "09:00-09:00",
            "25:00-26:00",
            "10:60-11:00",
            "9-10",
            "10:00",
            "10:00-",
            "abc",
            "10:00-11:00-12:00",
        ):
            with self.subTest(window=window_text):
                self.refuse("add", window_text)
        self.refuse("add")
        self.assertEqual(self.schedules(), [])
        self.assertEqual(self.launchctl(), [])
        self.assertFalse(self.plist_path.exists())

    def test_days_names_and_groups(self) -> None:
        cases = {
            "weekdays": [0, 1, 2, 3, 4],
            "weekends": [5, 6],
            "Mon,WED": [0, 2],
            "sun,mon,mon": [0, 6],
            "mon,tue,wed,thu,fri,sat,sun": None,
            "daily": None,
        }
        for text, days in cases.items():
            with self.subTest(days=text):
                self.add("09:00-10:00", "--days", text)
                self.assertEqual(self.schedules()[-1]["days"], days)

    def test_bad_days_are_refused(self) -> None:
        for text in ("funday", "monday", "mon,,tue", "", "mon;tue", "7"):
            with self.subTest(days=text):
                self.refuse("add", "09:00-10:00", "--days", text)
        self.assertEqual(self.schedules(), [])

    def test_date_makes_a_one_off(self) -> None:
        day = (date.today() + timedelta(days=3)).isoformat()
        self.add("09:00-10:00", "--date", day)
        (item,) = self.schedules()
        self.assertEqual((item["date"], item["days"]), (day, None))

    def test_a_date_in_the_past_or_a_bad_date_is_refused(self) -> None:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        for text in (yesterday, "2026-13-01", "2026-02-30", "tomorrow", "2026/12/01"):
            with self.subTest(date=text):
                self.refuse("add", "09:00-10:00", "--date", text)
        self.assertEqual(self.schedules(), [])

    def test_a_window_that_already_ended_today_is_past(self) -> None:
        moment = datetime.now()
        if moment.hour < 2:
            self.skipTest("no earlier window fits before 02:00")
        earlier = f"00:00-{clock(moment - timedelta(minutes=1))}"
        self.refuse("add", earlier, "--date", date.today().isoformat())

    def test_a_window_open_now_is_allowed_for_today(self) -> None:
        self.add(window(), "--date", date.today().isoformat())
        self.assertEqual(len(self.schedules()), 1)

    def test_days_and_date_exclude_each_other(self) -> None:
        day = (date.today() + timedelta(days=3)).isoformat()
        result = self.refuse("add", "09:00-10:00", "--days", "mon", "--date", day)
        self.assertIn("--days", result.stderr)
        self.assertIn("--date", result.stderr)

    def test_unknown_option_and_stray_words_are_refused(self) -> None:
        self.refuse("add", "09:00-10:00", "--nope")
        self.refuse("add", "09:00-10:00", "extra")
        self.refuse("frobnicate")
        self.refuse("rm")
        self.assertEqual(self.schedules(), [])

    def test_name_is_kept_and_control_characters_are_refused(self) -> None:
        self.add("09:00-10:00", "--name", "night build")
        self.assertEqual(self.schedules()[0]["name"], "night build")
        self.refuse("add", "09:00-10:00", "--name", "bad\x1b[31mname")
        self.assertEqual(len(self.schedules()), 1)

    def test_ids_are_the_next_free_integer_and_not_reused(self) -> None:
        self.add("09:00-10:00")
        self.add("11:00-12:00")
        self.add("13:00-14:00")
        self.ok("awake", "schedule", "rm", "2")
        self.add("15:00-16:00")
        self.assertEqual([item["id"] for item in self.schedules()], [1, 3, 4])

    # ---------------------------------------------------------------- the lid

    def test_lid_needs_the_sudoers_rule_at_add_time(self) -> None:
        result = self.refuse("add", "09:00-10:00", "--lid", code=1)
        self.assertIn("ul awake lid setup", result.stderr)
        self.assertEqual(self.schedules(), [])
        self.assertEqual(self.launchctl(), [])
        self.allow_lid()
        self.add("09:00-10:00", "--lid", "--display")
        (item,) = self.schedules()
        self.assertEqual((item["lid"], item["display"]), (True, True))

    # ---------------------------------------------------------------- launchd

    def test_daily_schedule_writes_the_job(self) -> None:
        self.add("23:00-06:00")
        plist = self.plist()
        self.assertEqual(plist["Label"], LABEL)
        self.assertEqual(
            plist["ProgramArguments"],
            [os.path.abspath(binary()), "awake", "_scheduled"],
        )
        self.assertTrue(plist["RunAtLoad"])
        self.assertEqual(self.intervals(), [{"Hour": 23, "Minute": 0}])
        self.assertEqual(plist["EnvironmentVariables"]["HOME"], str(self.home))
        self.assertEqual(
            self.launchctl(),
            [
                ["bootout", f"gui/{os.getuid()}/{LABEL}"],
                ["bootstrap", f"gui/{os.getuid()}", str(self.plist_path)],
            ],
        )

    def test_weekdays_use_launchd_numbering(self) -> None:
        # launchd: 0 and 7 are Sunday, Monday is 1.
        self.add("08:15-09:00", "--days", "mon,wed,sat,sun")
        self.assertEqual(
            self.intervals(),
            [
                {"Weekday": 1, "Hour": 8, "Minute": 15},
                {"Weekday": 3, "Hour": 8, "Minute": 15},
                {"Weekday": 6, "Hour": 8, "Minute": 15},
                {"Weekday": 0, "Hour": 8, "Minute": 15},
            ],
        )

    def test_one_off_uses_month_and_day(self) -> None:
        day = date.today() + timedelta(days=5)
        self.add("21:30-22:30", "--date", day.isoformat())
        self.assertEqual(
            self.intervals(),
            [{"Month": day.month, "Day": day.day, "Hour": 21, "Minute": 30}],
        )

    def test_several_schedules_become_several_intervals_without_duplicates(
        self,
    ) -> None:
        self.add("09:00-10:00")
        self.add("09:00-11:00")
        self.add("12:00-13:00", "--days", "weekends")
        self.assertEqual(
            self.intervals(),
            [
                {"Hour": 9, "Minute": 0},
                {"Weekday": 6, "Hour": 12, "Minute": 0},
                {"Weekday": 0, "Hour": 12, "Minute": 0},
            ],
        )

    def test_a_missing_unlaw_bin_is_an_error(self) -> None:
        env = {key: value for key, value in self.env.items() if key != "UNLAW_BIN"}
        env["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-m", "unlawful.awake", "schedule", "add", "09:00-10:00"],
            env=env,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("UNLAW_BIN", result.stderr)
        self.assertFalse(self.plist_path.exists())

    def test_a_failing_bootstrap_is_reported_but_the_schedule_is_kept(self) -> None:
        (self.fake / "launchctl_fail").write_text("")
        result = self.refuse("add", "09:00-10:00", code=1)
        self.assertIn("launchctl", result.stderr)
        self.assertEqual(len(self.schedules()), 1)

    # ---------------------------------------------------------------- list

    def test_list_without_schedules(self) -> None:
        self.assertIn("No schedules", self.ok("awake", "schedule", "list").stdout)
        data = json.loads(self.ok("awake", "schedule", "list", "--json").stdout)
        self.assertEqual(data, {"schedules": []})

    def test_list_shows_window_days_flags_name_and_next_start(self) -> None:
        self.allow_lid()
        self.add("23:00-06:00", "--display", "--lid", "--name", "night")
        self.add("09:00-10:00", "--days", "weekdays")
        day = (date.today() + timedelta(days=4)).isoformat()
        self.add("07:00-08:00", "--date", day)
        text = self.ok("awake", "schedule", "list").stdout
        lines = text.splitlines()
        self.assertTrue(lines[0].split()[:2] == ["ID", "WINDOW"], text)
        first, second, third = lines[1:4]
        self.assertTrue(first.split()[0] == "1" and "23:00-06:00" in first, first)
        self.assertIn("daily", first)
        self.assertIn("display", first)
        self.assertIn("lid", first)
        self.assertIn("night", first)
        self.assertIn("weekdays", second)
        self.assertIn(day, third)
        self.assertIn(f"{day} 07:00", third)

    def test_list_json_has_the_next_start(self) -> None:
        self.add("23:00-06:00")
        day = (date.today() + timedelta(days=4)).isoformat()
        self.add("07:00-08:00", "--date", day)
        data = json.loads(self.ok("awake", "schedule", "list", "--json").stdout)
        first, second = data["schedules"]
        for key in (
            "id",
            "start",
            "end",
            "days",
            "date",
            "display",
            "lid",
            "name",
            "created",
            "next_start",
        ):
            self.assertIn(key, first)
        moment = datetime.fromisoformat(first["next_start"])
        self.assertEqual((moment.hour, moment.minute), (23, 0))
        self.assertGreater(moment.timestamp(), datetime.now().timestamp())
        self.assertLess(moment.timestamp() - datetime.now().timestamp(), 24 * 3600 + 60)
        self.assertTrue(second["next_start"].startswith(f"{day}T07:00"))

    def test_next_start_follows_the_days(self) -> None:
        self.add("09:00-10:00", "--days", "sat")
        data = json.loads(self.ok("awake", "schedule", "list", "--json").stdout)
        moment = datetime.fromisoformat(data["schedules"][0]["next_start"])
        self.assertEqual(moment.weekday(), 5)
        self.assertEqual((moment.hour, moment.minute), (9, 0))

    # ---------------------------------------------------------------- rm

    def test_rm_unknown_id_fails_and_keeps_everything(self) -> None:
        self.add("09:00-10:00")
        self.refuse("rm", "7", code=1)
        self.refuse("rm", "x")
        self.assertEqual(len(self.schedules()), 1)

    def test_rm_rewrites_the_job_and_the_last_rm_removes_it(self) -> None:
        self.add("09:00-10:00")
        self.add("12:00-13:00")
        self.ok("awake", "schedule", "rm", "1")
        self.assertEqual(self.intervals(), [{"Hour": 12, "Minute": 0}])
        before = len(self.launchctl())
        self.ok("awake", "schedule", "rm", "2")
        self.assertFalse(self.plist_path.exists())
        self.assertEqual(self.schedules(), [])
        self.assertEqual(
            self.launchctl()[before:], [["bootout", f"gui/{os.getuid()}/{LABEL}"]]
        )

    def test_rm_all(self) -> None:
        self.add("09:00-10:00")
        self.add("12:00-13:00")
        self.ok("awake", "schedule", "rm", "--all")
        self.assertEqual(self.schedules(), [])
        self.assertFalse(self.plist_path.exists())
        self.assertEqual(self.launchctl()[-1][0], "bootout")

    def test_rm_all_with_nothing_scheduled_is_fine(self) -> None:
        self.ok("awake", "schedule", "rm", "--all")
        self.assertFalse(self.plist_path.exists())

    def test_rm_stops_the_session_of_that_schedule_only(self) -> None:
        self.add(window())
        self.add(window(20, 60))
        self.run_scheduled()
        state = self.wait_session()
        self.assertEqual(state["source"], "schedule:1")
        self.ok("awake", "schedule", "rm", "2")
        self.assertEqual(
            self.state()["source"], "schedule:1", "another schedule's session lives on"
        )
        self.ok("awake", "schedule", "rm", "1")
        self.assertTrue(wait_for(lambda: self.state() is None))

    def test_rm_leaves_a_manual_session_alone(self) -> None:
        self.add(window())
        self.start("2h")
        pid = self.state()["supervisor_pid"]
        self.ok("awake", "schedule", "rm", "1")
        self.assertEqual(self.state()["supervisor_pid"], pid)

    # ---------------------------------------------------------------- _scheduled

    def test_inside_the_window_a_session_runs_until_its_end(self) -> None:
        text = window()
        self.add(text, "--display")
        self.run_scheduled()
        state = self.wait_session()
        self.assertEqual((state["kind"], state["source"]), ("until", "schedule:1"))
        self.assertTrue(state["display"])
        self.assertFalse(state["lid"])
        ends = datetime.fromisoformat(state["ends"]).replace(tzinfo=None)
        self.assertEqual(ends, end_of_window(text))
        self.assertTrue(wait_for(lambda: self.read("caffeinate.log")))
        call = self.caffeinate_args()
        self.assertIn("-d", call)
        left = (end_of_window(text) - datetime.now()).total_seconds()
        self.assertAlmostEqual(self.seconds_of(call), left, delta=120)
        self.assertIn("schedule:1", self.read_log())

    def read_log(self) -> str:
        path = self.unlaw / "data" / "runtime" / "awake.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_outside_the_window_nothing_happens(self) -> None:
        self.add(window(-120, 180))
        result = self.run_scheduled()
        self.assertEqual(result.stdout.strip(), "")
        self.no_session()

    def test_nothing_scheduled_is_a_quiet_success(self) -> None:
        self.run_scheduled()
        self.no_session()

    def test_a_window_that_started_yesterday_still_counts(self) -> None:
        self.add("23:00-06:00")
        self.run_scheduled("2030-01-02T02:00:00")
        state = self.wait_session()
        self.assertEqual(
            datetime.fromisoformat(state["ends"]).replace(tzinfo=None),
            datetime(2030, 1, 2, 6, 0),
        )
        self.assertTrue(wait_for(lambda: self.read("caffeinate.log")))
        self.assertAlmostEqual(
            self.seconds_of(self.caffeinate_args()), 4 * 3600, delta=2
        )

    def test_before_midnight_the_same_window_ends_tomorrow(self) -> None:
        self.add("23:00-06:00")
        self.run_scheduled("2030-01-02T23:30:00")
        state = self.wait_session()
        self.assertEqual(
            datetime.fromisoformat(state["ends"]).replace(tzinfo=None),
            datetime(2030, 1, 3, 6, 0),
        )

    def test_the_window_end_itself_is_outside(self) -> None:
        self.add("23:00-06:00")
        self.run_scheduled("2030-01-02T06:00:00")
        self.no_session()

    def test_days_limit_the_window(self) -> None:
        # 2030-01-02 is a Wednesday, 2030-01-05 a Saturday.
        self.add("09:00-17:00", "--days", "weekdays")
        self.run_scheduled("2030-01-05T10:00:00")
        self.no_session()
        self.run_scheduled("2030-01-02T10:00:00")
        self.assertEqual(self.wait_session()["source"], "schedule:1")

    def test_a_cross_midnight_window_belongs_to_the_day_it_started(self) -> None:
        self.add("23:00-06:00", "--days", "mon")  # 2030-01-07 is a Monday
        self.run_scheduled(
            "2030-01-07T02:00:00"
        )  # Sunday night's tail: not Monday's window
        self.no_session()
        self.run_scheduled("2030-01-08T02:00:00")  # Monday night's tail
        self.assertEqual(self.wait_session()["source"], "schedule:1")

    def test_of_several_open_windows_the_latest_end_wins(self) -> None:
        self.add(window(30, 60))
        self.add(window(30, 120))
        self.run_scheduled()
        self.assertEqual(self.wait_session()["source"], "schedule:2")

    def test_running_twice_does_not_restart_the_session(self) -> None:
        self.add(window())
        self.run_scheduled()
        pid = self.wait_session()["supervisor_pid"]
        # The fake logs its argv a moment after it is started.
        self.assertTrue(wait_for(lambda: self.read("caffeinate.log")))
        self.run_scheduled()
        self.assertEqual(self.state()["supervisor_pid"], pid)
        self.assertEqual(len(self.read("caffeinate.log").splitlines()), 1)

    def test_a_later_manual_session_is_not_cut_short(self) -> None:
        self.add(window())
        self.start("10h")
        pid = self.state()["supervisor_pid"]
        self.run_scheduled()
        state = self.state()
        self.assertEqual((state["supervisor_pid"], state["source"]), (pid, "manual"))

    def test_an_endless_manual_session_is_left_alone(self) -> None:
        self.add(window())
        self.start("on")
        pid = self.state()["supervisor_pid"]
        self.run_scheduled()
        self.assertEqual(self.state()["supervisor_pid"], pid)
        self.assertEqual(self.state()["kind"], "on")

    def test_a_pid_session_is_left_alone(self) -> None:
        self.add(window())
        self.start("--pid", str(os.getpid()))
        pid = self.state()["supervisor_pid"]
        self.run_scheduled()
        self.assertEqual(self.state()["supervisor_pid"], pid)

    def test_an_earlier_ending_manual_session_is_extended(self) -> None:
        self.add(window())
        self.start("30m")
        pid = self.state()["supervisor_pid"]
        self.run_scheduled()
        self.assertTrue(
            wait_for(lambda: (self.state() or {}).get("source") == "schedule:1")
        )
        self.assertNotEqual(self.state()["supervisor_pid"], pid)

    def test_a_command_session_is_never_touched(self) -> None:
        self.add(window())
        started, release = self.root / "started", self.root / "release"
        wrapper = self.run_in_background(
            "--", sys.executable, "-c", self.waiting_script(started, release)
        )
        self.assertTrue(wait_for(started.exists))
        self.assertTrue(wait_for(lambda: (self.state() or {}).get("caffeinate_pid")))
        self.run_scheduled()
        self.assertEqual(self.state()["kind"], "command")
        self.assertIsNone(wrapper.poll())
        release.write_text("")
        self.assertEqual(wrapper.wait(timeout=10), 0)

    def test_a_schedule_session_replaces_an_older_schedule_session(self) -> None:
        self.add(window(30, 60))
        self.run_scheduled()
        first = self.wait_session()["supervisor_pid"]
        self.add(window(30, 120))
        self.run_scheduled()
        self.assertTrue(
            wait_for(lambda: (self.state() or {}).get("source") == "schedule:2")
        )
        self.assertNotEqual(self.state()["supervisor_pid"], first)

    def test_a_schedule_session_that_ends_later_is_not_cut_short(self) -> None:
        self.add(window(30, 120))
        self.run_scheduled()
        first = self.wait_session()["supervisor_pid"]
        self.add(window(30, 60))
        self.run_scheduled()
        self.assertEqual(self.state()["supervisor_pid"], first)
        self.assertEqual(self.state()["source"], "schedule:1")

    def test_a_past_one_off_is_dropped_and_the_job_rewritten(self) -> None:
        day = (date.today() + timedelta(days=2)).isoformat()
        self.add("09:00-10:00", "--date", day)
        self.add("09:00-10:00")
        self.assertEqual(len(self.intervals()), 2)
        later = (date.today() + timedelta(days=9)).isoformat()
        self.run_scheduled(f"{later}T12:00:00")
        self.assertEqual([item["id"] for item in self.schedules()], [2])
        self.assertEqual(self.intervals(), [{"Hour": 9, "Minute": 0}])

    def test_dropping_the_last_one_off_removes_the_job(self) -> None:
        day = (date.today() + timedelta(days=2)).isoformat()
        self.add("09:00-10:00", "--date", day)
        later = (date.today() + timedelta(days=9)).isoformat()
        self.run_scheduled(f"{later}T12:00:00")
        self.assertEqual(self.schedules(), [])
        self.assertFalse(self.plist_path.exists())
        self.assertEqual(self.launchctl()[-1][0], "bootout")

    def test_a_one_off_runs_on_its_day_only(self) -> None:
        day = date.today() + timedelta(days=2)
        self.add("09:00-10:00", "--date", day.isoformat())
        self.run_scheduled(f"{day - timedelta(days=1)}T09:30:00")
        self.no_session()
        self.run_scheduled(f"{day}T09:30:00")
        state = self.wait_session()
        self.assertEqual(state["source"], "schedule:1")
        self.assertEqual(
            datetime.fromisoformat(state["ends"]).replace(tzinfo=None),
            datetime.combine(day, datetime.min.time()).replace(hour=10),
        )

    def test_a_cross_midnight_one_off_covers_the_next_morning(self) -> None:
        day = date.today() + timedelta(days=2)
        self.add("23:00-06:00", "--date", day.isoformat())
        self.run_scheduled(f"{day + timedelta(days=1)}T03:00:00")
        self.assertEqual(self.wait_session()["source"], "schedule:1")
        self.assertEqual(len(self.schedules()), 1, "still running, so not dropped")

    def test_a_scheduled_lid_session_sets_the_lid(self) -> None:
        self.allow_lid()
        self.add(window(), "--lid")
        self.run_scheduled()
        state = self.wait_session()
        self.assertTrue(state["lid"])
        self.assertEqual(self.sleep_disabled(), "1")

    def test_without_the_rule_a_scheduled_lid_session_still_keeps_awake(self) -> None:
        self.allow_lid()
        self.add(window(), "--lid")
        (self.fake / "rule_ok").unlink()
        self.run_scheduled()
        state = self.wait_session()
        self.assertFalse(state["lid"])
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIn("lid", self.read_log())

    def test_a_bad_now_is_a_usage_error(self) -> None:
        self.add(window())
        result = self.ul("awake", "_scheduled", "--now", "yesterday-ish")
        self.assertEqual(result.returncode, 2)
        self.no_session()

    def test_a_damaged_schedule_file_is_reported_and_not_overwritten(self) -> None:
        self.add("09:00-10:00")
        self.schedules_path().write_text("{not json", encoding="utf-8")
        result = self.ul("awake", "schedule", "add", "11:00-12:00")
        self.assertEqual(result.returncode, 1)
        self.assertIn("awake-schedules.json", result.stderr)
        self.assertEqual(self.schedules_path().read_text(encoding="utf-8"), "{not json")


if __name__ == "__main__":
    unittest.main()
