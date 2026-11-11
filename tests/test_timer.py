"""`ul timer`: the seeded command run as a black box with a fake osascript."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ulbin import CoreTestCase, binary

# Logs argv as JSON; the real osascript would show a notification.
FAKE_OSASCRIPT = """import json, os, sys
open(os.environ["FAKE_DIR"] + "/osascript.log", "a").write(json.dumps(sys.argv[1:]) + "\\n")
"""


def now() -> datetime:
    return datetime.now().astimezone()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_for(condition, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return bool(condition())


class TimerBase(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fake = self.root / "fake"
        self.fake.mkdir()
        self.env["FAKE_DIR"] = str(self.fake)
        self.env["PATH"] = f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"
        self.tool("osascript", f"#!{sys.executable}\n{FAKE_OSASCRIPT}")
        self.addCleanup(self.kill_leftovers)

    def state_path(self) -> Path:
        return self.unlaw / "data" / "runtime" / "timers.json"

    def entries(self) -> list[dict]:
        path = self.state_path()
        return (
            json.loads(path.read_text(encoding="utf-8"))["timers"]
            if path.exists()
            else []
        )

    def kill_leftovers(self) -> None:
        try:
            entries = self.entries()
        except ValueError:
            return
        for entry in entries:
            pid = entry.get("pid")
            if isinstance(pid, int) and pid > 1 and alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def notifications(self) -> list[list[str]]:
        log = self.fake / "osascript.log"
        if not log.exists():
            return []
        return [
            json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
        ]

    def timer_id(self, result) -> str:
        found = re.search(r"timer (\d+)", result.stdout)
        self.assertIsNotNone(found, result.stdout)
        return found.group(1)

    def listing(self) -> list[dict]:
        return json.loads(self.ok("timer", "list", "--json").stdout)


class TimerTests(TimerBase):
    def test_help_has_no_side_effects(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("timer", flag)
            self.assertIn("ul timer", result.stdout)
        self.assertFalse(self.state_path().exists())
        self.assertEqual(self.notifications(), [])

    def test_a_timer_runs_detached_and_notifies(self) -> None:
        result = self.ok("timer", "1s", "tea", "time")
        self.timer_id(result)
        self.assertIn("tea time", result.stdout)
        self.assertRegex(result.stdout, r"\d\d:\d\d")
        self.assertTrue(wait_for(lambda: self.notifications()), "no notification")
        call = self.notifications()[0]
        self.assertIn("tea time", call)
        self.assertEqual(call[:1], ["-e"])
        # The label travels as an argument, never inside the AppleScript source.
        sources = [call[i + 1] for i, word in enumerate(call) if word == "-e"]
        self.assertFalse(any("tea" in source for source in sources))
        self.assertIn("--", call)
        self.assertTrue(wait_for(lambda: self.entries() == []), "entry not removed")

    def test_sound_follows_the_setting(self) -> None:
        self.ok("timer", "1s")
        self.assertTrue(wait_for(lambda: self.notifications()))
        self.assertIn("sound name", " ".join(self.notifications()[0]))
        self.ok("config", "set", "timer.sound", "false")
        self.ok("timer", "1s")
        self.assertTrue(wait_for(lambda: len(self.notifications()) == 2))
        self.assertNotIn("sound name", " ".join(self.notifications()[1]))

    def test_list_shows_running_timers_and_json(self) -> None:
        first = self.timer_id(self.ok("timer", "1h", "deep", "work"))
        second = self.timer_id(self.ok("timer", "90"))
        self.assertNotEqual(first, second)
        text = self.ok("timer", "list").stdout
        self.assertIn("deep work", text)
        self.assertEqual(self.ok("timer").stdout, text)
        data = self.listing()
        self.assertEqual({item["id"] for item in data}, {first, second})
        by_id = {item["id"]: item for item in data}
        self.assertEqual(by_id[first]["label"], "deep work")
        self.assertAlmostEqual(by_id[first]["remaining_seconds"], 3600, delta=30)
        self.assertAlmostEqual(by_id[second]["remaining_seconds"], 5400, delta=30)
        self.assertEqual(by_id[first]["kind"], "duration")
        self.assertTrue(by_id[first]["ends"].startswith(str(now().year)))

    def test_empty_list(self) -> None:
        self.assertIn("no timers", self.ok("timer", "list").stdout)
        self.assertEqual(self.listing(), [])

    def test_duration_forms(self) -> None:
        for text, seconds in (("30s", 30), ("5m", 300), ("1h30m", 5400), ("2", 120)):
            self.ok("timer", text)
            newest = self.listing()[-1]
            self.assertAlmostEqual(
                newest["remaining_seconds"], seconds, delta=15, msg=text
            )

    def test_bad_durations_are_refused(self) -> None:
        for text in ("0", "0m", "abc", "-5m", "1h90x", "9999h"):
            result = self.ul("timer", text)
            self.assertEqual(
                result.returncode, 2, f"{text}: {result.stdout}{result.stderr}"
            )
        self.assertEqual(self.entries(), [])

    def test_control_characters_in_labels_are_refused(self) -> None:
        result = self.ul("timer", "5m", "bad\x1b[31mlabel")
        self.assertEqual(result.returncode, 2)
        self.assertIn("control", result.stderr)
        self.assertEqual(self.entries(), [])

    def test_alarm_today_when_the_time_is_ahead(self) -> None:
        later = (now() + timedelta(hours=2)).replace(second=0, microsecond=0)
        if later.date() != now().date():
            self.skipTest("two hours from now is already tomorrow")
        self.ok("timer", "at", later.strftime("%H:%M"), "meeting")
        entry = self.listing()[0]
        self.assertEqual(entry["kind"], "alarm")
        self.assertEqual(entry["label"], "meeting")
        self.assertEqual(
            datetime.fromisoformat(entry["ends"]).replace(tzinfo=None),
            later.replace(tzinfo=None),
        )

    def test_alarm_tomorrow_when_the_time_has_passed(self) -> None:
        earlier = (now() - timedelta(minutes=5)).replace(second=0, microsecond=0)
        self.ok("timer", "at", earlier.strftime("%H:%M"))
        end = datetime.fromisoformat(self.listing()[0]["ends"]).replace(tzinfo=None)
        self.assertEqual(end, (earlier + timedelta(days=1)).replace(tzinfo=None))

    def test_bad_alarm_times_are_refused(self) -> None:
        for text in ("25:00", "18:60", "noon", "1830"):
            self.assertEqual(self.ul("timer", "at", text).returncode, 2, text)
        self.assertEqual(self.ul("timer", "at").returncode, 2)

    def test_cancel_stops_the_process_and_removes_the_entry(self) -> None:
        timer = self.timer_id(self.ok("timer", "1h"))
        pid = self.entries()[0]["pid"]
        self.assertTrue(alive(pid))
        self.ok("timer", "cancel", timer)
        self.assertEqual(self.entries(), [])
        self.assertTrue(wait_for(lambda: not alive(pid)), "process still running")
        self.assertEqual(self.notifications(), [])

    def test_cancel_all(self) -> None:
        self.ok("timer", "1h")
        self.ok("timer", "2h")
        pids = [entry["pid"] for entry in self.entries()]
        self.ok("timer", "cancel", "--all")
        self.assertEqual(self.entries(), [])
        self.assertTrue(wait_for(lambda: not any(alive(pid) for pid in pids)))

    def test_cancel_unknown_id_fails(self) -> None:
        result = self.ul("timer", "cancel", "99")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no timer 99", result.stderr)
        self.assertEqual(self.ul("timer", "cancel").returncode, 2)

    def test_stale_entries_are_cleaned_and_foreign_pids_never_signalled(self) -> None:
        sleeper = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait()))
        self.ok("timer", "1h")
        real = self.entries()[0]["pid"]
        data = json.loads(self.state_path().read_text(encoding="utf-8"))
        data["timers"][0]["pid"] = sleeper.pid  # alive, but not our seed
        data["timers"].append(
            {
                "id": "50",
                "kind": "duration",
                "label": "",
                "end": time.time() + 3600,
                "pid": 2**22 + 5,
                "lstart": "",
                "created": time.time() - 99,
            }
        )
        self.state_path().write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.listing(), [])
        self.assertIsNone(sleeper.poll())
        self.assertEqual(self.entries(), [])
        # The orphaned process notices its entry belongs to another pid and exits by itself.
        self.assertTrue(wait_for(lambda: not alive(real)))

    def test_cancel_does_not_kill_a_reused_pid(self) -> None:
        sleeper = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait()))
        timer = self.timer_id(self.ok("timer", "1h"))
        real = self.entries()[0]["pid"]
        os.kill(real, signal.SIGKILL)
        data = json.loads(self.state_path().read_text(encoding="utf-8"))
        data["timers"][0]["pid"] = sleeper.pid
        self.state_path().write_text(json.dumps(data), encoding="utf-8")
        self.ul("timer", "cancel", timer)
        self.assertIsNone(sleeper.poll())
        self.assertEqual(self.entries(), [])

    def test_wait_counts_down_and_notifies(self) -> None:
        started = time.monotonic()
        result = self.ok("timer", "wait", "1s", "quick")
        self.assertGreaterEqual(time.monotonic() - started, 0.9)
        self.assertIn("quick", result.stdout)
        self.assertEqual(len(self.notifications()), 1)
        self.assertIn("quick", self.notifications()[0])
        self.assertEqual(self.entries(), [])

    def test_ctrl_c_cancels_a_wait_without_notifying(self) -> None:
        process = subprocess.Popen(
            [str(binary()), "timer", "wait", "1h"],
            env=self.env,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        time.sleep(1.5)
        # Like a terminal's Ctrl+C: the whole foreground group gets the signal.
        os.killpg(process.pid, signal.SIGINT)
        process.communicate(timeout=10)
        self.assertIn(process.returncode, (130, -signal.SIGINT))
        self.assertEqual(self.notifications(), [])

    def test_a_damaged_state_file_is_reported_not_overwritten(self) -> None:
        self.state_path().parent.mkdir(parents=True)
        self.state_path().write_text("{nope", encoding="utf-8")
        result = self.ul("timer", "list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("timers.json", result.stderr)
        self.assertEqual(self.state_path().read_text(encoding="utf-8"), "{nope")


if __name__ == "__main__":
    unittest.main()
