"""`ul awake`: the seeded command run as a black box with fake caffeinate, sudo, pmset and visudo."""

from __future__ import annotations

import json
import os
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

# Sleeps like caffeinate: ends after -t seconds, when the -w pid is gone, or on a signal.
FAKE_CAFFEINATE = """import json, os, sys, time
a = sys.argv[1:]
d = os.environ["FAKE_DIR"]
open(d + "/caffeinate.log", "a").write(json.dumps(a) + "\\n")
open(d + "/caffeinate.pids", "a").write(str(os.getpid()) + "\\n")
end = time.time() + float(a[a.index("-t") + 1]) if "-t" in a else None
watched = int(a[a.index("-w") + 1]) if "-w" in a else None
while end is None or time.time() < end:
    if watched is not None:
        try:
            os.kill(watched, 0)
        except ProcessLookupError:
            break
    time.sleep(0.05)
"""

# Logs argv. `-n -l` answers from the rule file; `-n /usr/bin/pmset ...` runs the fake pmset.
FAKE_SUDO = """import json, os, subprocess, sys
a = sys.argv[1:]
d = os.environ["FAKE_DIR"]
open(d + "/sudo.log", "a").write(json.dumps(a) + "\\n")
has_rule = os.path.exists(d + "/rule_ok")
if a[:2] == ["-n", "-l"]:
    raise SystemExit(0 if has_rule else 1)
if a[:2] == ["-n", "/usr/bin/pmset"]:
    if not has_rule or os.path.exists(d + "/sudo_fail"):
        raise SystemExit(1)
    if a[-1] == "0" and os.path.exists(d + "/sudo_fail_restore"):
        raise SystemExit(1)
    here = os.path.dirname(os.path.abspath(sys.argv[0]))
    raise SystemExit(subprocess.call([here + "/pmset", *a[2:]]))
raise SystemExit(1 if os.path.exists(d + "/sudo_fail_other") else 0)
"""

FAKE_PMSET = """import os, sys
a = sys.argv[1:]
d = os.environ["FAKE_DIR"]
state = d + "/sleepdisabled"
if a == ["-g"]:
    value = open(state).read().strip() if os.path.exists(state) else "0"
    print("System-wide power settings:\\n SleepDisabled\\t\\t" + value + "\\n sleep\\t1")
elif a == ["-g", "batt"]:
    source = "Battery Power" if os.path.exists(d + "/on_battery") else "AC Power"
    print("Now drawing from '" + source + "'")
elif a[:2] == ["-a", "disablesleep"]:
    open(state, "w").write(a[2])
    open(d + "/pmset.log", "a").write(a[2] + "\\n")
else:
    raise SystemExit(64)
"""

FAKE_VISUDO = """import os, shutil, sys
a = sys.argv[1:]
d = os.environ["FAKE_DIR"]
open(d + "/visudo.log", "a").write("|".join(a) + "\\n")
if a[0] == "-cf":
    shutil.copy(a[1], d + "/visudo.seen")
raise SystemExit(1 if os.path.exists(d + "/visudo_fail") else 0)
"""

SUDOERS_PATH = "/etc/sudoers.d/unlaw-awake"
JSON_KEYS = {
    "active",
    "kind",
    "started",
    "ends",
    "remaining_seconds",
    "display",
    "lid",
    "source",
    "supervisor_pid",
    "caffeinate_pid",
    "sleep_disabled",
    "lid_restore_failed",
}


def now() -> datetime:
    return datetime.now().astimezone()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_for(condition, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return bool(condition())


class AwakeTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fake = self.root / "fake"
        self.fake.mkdir()
        self.env["FAKE_DIR"] = str(self.fake)
        self.env["PATH"] = f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"
        self.env["LOGNAME"] = "tester"
        for name, body in (
            ("caffeinate", FAKE_CAFFEINATE),
            ("sudo", FAKE_SUDO),
            ("pmset", FAKE_PMSET),
            ("visudo", FAKE_VISUDO),
        ):
            self.tool(name, f"#!{sys.executable}\n{body}")
        self.addCleanup(self.kill_leftovers)

    # ---------------------------------------------------------------- helpers

    def kill_leftovers(self) -> None:
        state = self.state()
        pids = (
            [state.get("supervisor_pid"), state.get("caffeinate_pid")] if state else []
        )
        pids += [int(p) for p in self.read("caffeinate.pids").split()]
        for pid in pids:
            if pid and alive(pid):
                os.kill(pid, signal.SIGKILL)

    def read(self, name: str) -> str:
        path = self.fake / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def jlog(self, name: str) -> list[list[str]]:
        return [json.loads(line) for line in self.read(name).splitlines()]

    def state_path(self) -> Path:
        return self.unlaw / "data" / "runtime" / "awake.json"

    def state(self) -> dict | None:
        path = self.state_path()
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def allow_lid(self) -> None:
        (self.fake / "rule_ok").write_text("")

    def sleep_disabled(self) -> str:
        return self.read("sleepdisabled").strip() or "0"

    def start(self, *args: str) -> subprocess.CompletedProcess[str]:
        logged = len(self.read("caffeinate.log").splitlines())
        result = self.ok("awake", *args)
        self.assertTrue(
            wait_for(lambda: (self.state() or {}).get("caffeinate_pid")),
            "session did not start",
        )
        # The fake logs its argv a moment after it is started.
        self.assertTrue(
            wait_for(lambda: len(self.read("caffeinate.log").splitlines()) > logged),
            "caffeinate did not run",
        )
        return result

    def status(self) -> dict:
        return json.loads(self.ok("awake", "status", "--json").stdout)

    def ends_in(self, seconds: float, slack: float = 120) -> None:
        state = self.state()
        self.assertIsNotNone(state)
        left = (
            datetime.fromisoformat(state["ends"]) - now().astimezone()
        ).total_seconds()
        self.assertAlmostEqual(left, seconds, delta=slack)

    def caffeinate_args(self) -> list[str]:
        calls = self.jlog("caffeinate.log")
        self.assertTrue(calls, "caffeinate was not started")
        return calls[-1]

    def seconds_of(self, call: list[str]) -> int:
        return int(call[call.index("-t") + 1])

    # ---------------------------------------------------------------- help

    def test_help_has_no_side_effects_and_stays_short(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("awake", flag)
            self.assertIn("ul awake", result.stdout)
            self.assertLess(len(result.stdout.splitlines()), 30)
            for needle in (
                "until",
                "--lid",
                "--display",
                "--pid",
                "lid setup",
                "Example",
            ):
                self.assertIn(needle, result.stdout)
        self.assertIsNone(self.state())
        for name in ("caffeinate.log", "sudo.log", "pmset.log", "visudo.log"):
            self.assertEqual(self.read(name), "", name)

    def test_help_after_double_dash_belongs_to_the_command(self) -> None:
        result = self.ok(
            "awake", "--", sys.executable, "-c", "print('child', 'ran')", "-h"
        )
        self.assertIn("child ran", result.stdout)

    # ---------------------------------------------------------------- durations

    def test_durations_become_caffeinate_seconds(self) -> None:
        for text, seconds in (
            ("30m", 1800),
            ("2h", 7200),
            ("1h30m", 5400),
            ("90", 5400),
            ("45s", 45),
            ("168h", 604800),
        ):
            self.start(text)
            call = self.caffeinate_args()
            self.assertEqual(self.seconds_of(call), seconds, text)
            self.assertIn("-i", call)
            self.assertIn("-s", call)
            self.assertNotIn("-d", call)
            self.assertEqual(self.state()["kind"], "duration")
            self.ok("awake", "off")

    def test_display_adds_d_flag(self) -> None:
        self.start("10m", "--display")
        self.assertIn("-d", self.caffeinate_args())
        self.assertTrue(self.state()["display"])

    def test_bad_durations_are_refused_and_start_nothing(self) -> None:
        for text in ("0", "0m", "abc", "-5", "169h", "10000000", "1x", "1.5h", ""):
            result = self.ul("awake", text)
            self.assertEqual(
                result.returncode, 2, f"{text!r}: {result.stdout}{result.stderr}"
            )
            self.assertIn("awake", result.stderr)
        self.assertEqual(self.read("caffeinate.log"), "")
        self.assertIsNone(self.state())

    # ---------------------------------------------------------------- until

    def test_until_a_later_time_today(self) -> None:
        target = now() + timedelta(hours=2)
        self.start("until", target.strftime("%H:%M"))
        self.assertAlmostEqual(self.seconds_of(self.caffeinate_args()), 7200, delta=120)
        self.assertEqual(self.state()["kind"], "until")
        self.ends_in(7200)

    def test_until_a_time_already_past_means_tomorrow(self) -> None:
        target = now() - timedelta(minutes=1)
        self.start("until", target.strftime("%H:%M"))
        self.assertAlmostEqual(
            self.seconds_of(self.caffeinate_args()), 86400 - 60, delta=3700
        )
        left = datetime.fromisoformat(self.state()["ends"]).astimezone()
        self.assertEqual(left.strftime("%H:%M"), target.strftime("%H:%M"))
        self.assertGreater(left, now() + timedelta(hours=22))

    def test_until_with_a_date(self) -> None:
        target = now() + timedelta(days=2)
        self.start("until", target.strftime("%Y-%m-%d"), target.strftime("%H:%M"))
        self.ends_in(2 * 86400, slack=3700)

    def test_bad_until_is_refused(self) -> None:
        past = (now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        far = (now() + timedelta(days=9)).strftime("%Y-%m-%d %H:%M")
        for words in (
            ["25:00"],
            ["12:60"],
            ["noon"],
            [],
            ["2026-13-01", "10:00"],
            past.split(),
            far.split(),
        ):
            result = self.ul("awake", "until", *words)
            self.assertEqual(
                result.returncode, 2, f"{words}: {result.stdout}{result.stderr}"
            )
        self.assertEqual(self.read("caffeinate.log"), "")

    # ---------------------------------------------------------------- on / off / replace

    def test_on_has_no_end_and_off_stops_it(self) -> None:
        self.start("on")
        call = self.caffeinate_args()
        self.assertNotIn("-t", call)
        state = self.state()
        self.assertEqual(
            (state["kind"], state["ends"], state["source"], state["version"]),
            ("on", None, "manual", 1),
        )
        supervisor, caffeinate = state["supervisor_pid"], state["caffeinate_pid"]
        self.assertTrue(alive(supervisor) and alive(caffeinate))
        result = self.ok("awake", "off")
        self.assertIn("stopped", result.stdout.lower())
        self.assertTrue(
            wait_for(lambda: not alive(supervisor) and not alive(caffeinate))
        )
        self.assertIsNone(self.state())
        self.assertFalse(self.status()["active"])

    def test_off_without_a_session_is_fine(self) -> None:
        result = self.ok("awake", "off")
        self.assertIn("nothing", result.stdout.lower())

    def test_a_new_session_replaces_the_current_one(self) -> None:
        self.start("1h")
        old = self.state()
        result = self.start("2h")
        self.assertIn("Replaced", result.stdout)
        self.assertTrue(
            wait_for(
                lambda: (
                    not alive(old["supervisor_pid"])
                    and not alive(old["caffeinate_pid"])
                )
            )
        )
        new = self.state()
        self.assertNotEqual(new["supervisor_pid"], old["supervisor_pid"])
        self.assertTrue(alive(new["supervisor_pid"]) and alive(new["caffeinate_pid"]))
        self.ends_in(7200)

    def test_session_ends_by_itself_and_cleans_up(self) -> None:
        self.start("2s")
        pid = self.state()["supervisor_pid"]
        self.assertTrue(wait_for(lambda: self.state() is None and not alive(pid)))

    def stale_state(self, pid: int) -> None:
        self.state_path().parent.mkdir(parents=True, exist_ok=True)
        self.state_path().write_text(
            json.dumps(
                {
                    "version": 1,
                    "supervisor_pid": pid,
                    "caffeinate_pid": pid,
                    "started": "2026-01-01T00:00:00+00:00",
                    "ends": None,
                    "kind": "on",
                    "display": False,
                    "lid": False,
                    "lid_previous": None,
                    "lid_restore_failed": False,
                    "source": "manual",
                }
            )
        )

    def test_stale_state_is_cleaned_and_a_foreign_process_is_never_signalled(
        self,
    ) -> None:
        bystander = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: (bystander.kill(), bystander.wait()))
        for pid in (bystander.pid, 2**22 - 7):
            self.stale_state(pid)
            self.assertFalse(self.status()["active"])
            self.assertIsNone(self.state())
            self.stale_state(pid)
            self.ok("awake", "off")
            self.assertIsNone(self.state())
        self.assertIsNone(bystander.poll(), "off killed a process that is not ours")

    def test_broken_state_file_counts_as_no_session(self) -> None:
        self.state_path().parent.mkdir(parents=True, exist_ok=True)
        self.state_path().write_text("{not json")
        self.assertFalse(self.status()["active"])
        self.start("5m")
        self.assertEqual(self.state()["kind"], "duration")

    # ---------------------------------------------------------------- status

    def test_status_inactive(self) -> None:
        self.assertIn("off", self.ok("awake").stdout.lower())
        data = self.status()
        self.assertEqual(set(data), JSON_KEYS)
        self.assertFalse(data["active"])
        self.assertIsNone(data["kind"])

    def test_status_active_text_and_json(self) -> None:
        self.start("1h", "--display")
        data = self.status()
        self.assertEqual(set(data), JSON_KEYS)
        self.assertTrue(data["active"])
        self.assertEqual(
            (data["kind"], data["display"], data["lid"], data["source"]),
            ("duration", True, False, "manual"),
        )
        self.assertAlmostEqual(data["remaining_seconds"], 3600, delta=120)
        self.assertEqual(data["supervisor_pid"], self.state()["supervisor_pid"])
        text = self.ok("awake").stdout
        self.assertIn("duration", text)
        self.assertIn("display", text.lower())
        # Only the countdown may differ between two runs.
        self.assertEqual(
            self.ok("awake", "status").stdout.splitlines()[1:], text.splitlines()[1:]
        )

    def test_status_shows_sleep_disabled_when_set(self) -> None:
        (self.fake / "sleepdisabled").write_text("1")
        self.assertTrue(self.status()["sleep_disabled"])
        self.assertIn("SleepDisabled", self.ok("awake").stdout)

    # ---------------------------------------------------------------- -- command

    def test_command_exit_code_passes_through_and_caffeinate_watches_the_child(
        self,
    ) -> None:
        pidfile = self.root / "child.pid"
        script = (
            "import os, time\n"
            f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
            f"while not os.path.exists({str(self.fake / 'caffeinate.log')!r}):\n"
            "    time.sleep(0.02)\n"
            "raise SystemExit(7)"
        )
        result = self.ul("awake", "--", sys.executable, "-c", script)
        self.assertEqual(result.returncode, 7, result.stderr)
        call = self.caffeinate_args()
        self.assertEqual(call[call.index("-w") + 1], pidfile.read_text())
        self.assertNotIn("-t", call)
        self.assertTrue(wait_for(lambda: self.state() is None))
        self.assertEqual(self.ul("awake", "--", "true").returncode, 0)

    def test_command_state_while_running(self) -> None:
        probe = (
            "import os, time\n"
            f"while not os.path.exists({str(self.fake / 'caffeinate.log')!r}):\n"
            "    time.sleep(0.02)\n"
            f"print(open({str(self.state_path())!r}).read())"
        )
        result = self.ok("awake", "--display", "--", sys.executable, "-c", probe)
        state = json.loads(result.stdout)
        self.assertEqual(
            (state["kind"], state["display"], state["ends"]), ("command", True, None)
        )
        self.assertIn("-d", self.caffeinate_args())

    def test_missing_command_exits_127(self) -> None:
        result = self.ul("awake", "--", "no-such-tool-here")
        self.assertEqual(result.returncode, 127)
        self.assertIn("no-such-tool-here", result.stderr)
        self.assertIsNone(self.state())

    def run_in_background(self, *args: str) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            [str(binary()), "awake", *args],
            env=self.env,
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self.addCleanup(lambda: (process.kill(), process.wait()))
        return process

    def waiting_script(self, started: Path, release: Path) -> str:
        return (
            "import os, time\n"
            f"open({str(started)!r}, 'w').write(str(os.getpid()))\n"
            f"while not os.path.exists({str(release)!r}):\n"
            "    time.sleep(0.05)\n"
        )

    def test_command_session_cannot_be_replaced_or_stopped_from_outside(self) -> None:
        started, release = self.root / "started", self.root / "release"
        wrapper = self.run_in_background(
            "--", sys.executable, "-c", self.waiting_script(started, release)
        )
        self.assertTrue(wait_for(started.exists))
        result = self.ul("awake", "1h")
        self.assertEqual(result.returncode, 1)
        self.assertIn("command", result.stderr)
        self.assertEqual(self.ul("awake", "off").returncode, 1)
        self.assertIsNone(wrapper.poll(), "the user's command must keep running")
        release.write_text("")
        self.assertEqual(wrapper.wait(timeout=10), 0)
        self.assertTrue(wait_for(lambda: self.state() is None))

    def test_termination_of_the_wrapper_stops_the_child_and_cleans_up(self) -> None:
        started, release = self.root / "started", self.root / "release"
        wrapper = self.run_in_background(
            "--", sys.executable, "-c", self.waiting_script(started, release)
        )
        self.assertTrue(wait_for(started.exists))
        os.kill(self.state()["supervisor_pid"], signal.SIGTERM)
        self.assertEqual(wrapper.wait(timeout=10), 143)
        self.assertTrue(wait_for(lambda: self.state() is None))
        self.assertTrue(wait_for(lambda: not alive(int(started.read_text()))))

    # ---------------------------------------------------------------- --pid

    def test_pid_session_follows_the_process(self) -> None:
        sleeper = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait()))
        self.start("--pid", str(sleeper.pid))
        call = self.caffeinate_args()
        self.assertEqual(call[call.index("-w") + 1], str(sleeper.pid))
        self.assertEqual(self.state()["kind"], "pid")
        supervisor = self.state()["supervisor_pid"]
        sleeper.kill()
        sleeper.wait()
        self.assertTrue(
            wait_for(lambda: self.state() is None and not alive(supervisor))
        )

    def test_pid_that_does_not_exist_or_is_not_a_number(self) -> None:
        for value in ("4194000", "abc", "0", "-3"):
            result = self.ul("awake", "--pid", value)
            self.assertNotEqual(result.returncode, 0, value)
        self.assertEqual(self.read("caffeinate.log"), "")

    def test_conflicting_modes_are_refused(self) -> None:
        self.assertEqual(
            self.ul("awake", "30m", "--pid", str(os.getpid())).returncode, 2
        )
        self.assertEqual(self.ul("awake", "30m", "--", "true").returncode, 2)
        self.assertEqual(self.ul("awake", "--lid").returncode, 2)
        self.assertEqual(self.read("caffeinate.log"), "")

    # ---------------------------------------------------------------- lid

    def test_lid_sets_disablesleep_and_off_restores_it(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        self.assertIn(
            ["-n", "/usr/bin/pmset", "-a", "disablesleep", "1"], self.jlog("sudo.log")
        )
        self.assertEqual(self.sleep_disabled(), "1")
        state = self.state()
        self.assertEqual(
            (state["lid"], state["lid_previous"], state["lid_restore_failed"]),
            (True, 0, False),
        )
        self.assertTrue(self.status()["lid"])
        self.ok("awake", "off")
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIn(
            ["-n", "/usr/bin/pmset", "-a", "disablesleep", "0"], self.jlog("sudo.log")
        )
        self.assertIsNone(self.state())

    def test_lid_is_restored_when_a_timed_session_ends(self) -> None:
        self.allow_lid()
        self.start("2s", "--lid")
        self.assertEqual(self.sleep_disabled(), "1")
        self.assertTrue(wait_for(lambda: self.state() is None))
        self.assertEqual(self.sleep_disabled(), "0")

    def test_lid_is_restored_after_a_command(self) -> None:
        self.allow_lid()
        result = self.ul(
            "awake", "--lid", "--", sys.executable, "-c", "raise SystemExit(3)"
        )
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_lid_is_not_restored_when_it_was_already_disabled(self) -> None:
        self.allow_lid()
        (self.fake / "sleepdisabled").write_text("1")
        self.start("on", "--lid")
        self.assertIsNone(
            self.state()["lid_previous"]
            if self.state()["lid_previous"] is None
            else None
        )
        self.assertEqual(self.state()["lid_previous"], 1)
        self.ok("awake", "off")
        self.assertEqual(self.sleep_disabled(), "1")
        self.assertNotIn(
            ["-n", "/usr/bin/pmset", "-a", "disablesleep", "0"], self.jlog("sudo.log")
        )

    def test_lid_without_the_sudoers_rule_starts_nothing(self) -> None:
        result = self.ul("awake", "1h", "--lid")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ul awake lid setup", result.stderr)
        self.assertEqual(self.read("caffeinate.log"), "")
        self.assertIsNone(self.state())
        self.assertEqual(self.sleep_disabled(), "0")

    def test_lid_refusal_keeps_the_running_session(self) -> None:
        self.start("1h")
        old = self.state()
        self.assertEqual(self.ul("awake", "2h", "--lid").returncode, 1)
        self.assertEqual(self.state()["supervisor_pid"], old["supervisor_pid"])
        self.assertTrue(alive(old["supervisor_pid"]))

    def test_lid_command_failing_after_the_check_starts_nothing(self) -> None:
        self.allow_lid()
        (self.fake / "sudo_fail").write_text("")
        result = self.ul("awake", "1h", "--lid")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.read("caffeinate.log"), "")
        self.assertIsNone(self.state())

    def test_failed_restore_leaves_a_marker_that_off_clears(self) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        (self.fake / "sudo_fail_restore").write_text("")
        pid = self.state()["supervisor_pid"]
        result = self.ul("awake", "off")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("ul awake off", result.stderr)
        self.assertTrue(wait_for(lambda: not alive(pid)))
        state = self.state()
        self.assertIsNotNone(state)
        self.assertTrue(state["lid_restore_failed"])
        self.assertIsNone(state["supervisor_pid"])
        self.assertEqual(self.sleep_disabled(), "1")
        data = self.status()
        self.assertFalse(data["active"])
        self.assertTrue(data["lid_restore_failed"])
        self.assertIn("ul awake off", self.ok("awake").stdout)
        (self.fake / "sudo_fail_restore").unlink()
        result = self.ok("awake", "off")
        self.assertIn("restored", result.stdout.lower())
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_a_killed_supervisor_leaves_lid_debt_that_the_next_call_repays(
        self,
    ) -> None:
        self.allow_lid()
        self.start("on", "--lid")
        state = self.state()
        os.kill(state["supervisor_pid"], signal.SIGKILL)
        os.kill(state["caffeinate_pid"], signal.SIGKILL)
        self.assertTrue(wait_for(lambda: not alive(state["supervisor_pid"])))
        self.assertFalse(self.status()["active"])
        self.assertEqual(self.sleep_disabled(), "0")
        self.assertIsNone(self.state())

    def test_lid_on_battery_warns_but_starts(self) -> None:
        self.allow_lid()
        (self.fake / "on_battery").write_text("")
        result = self.start("10m", "--lid")
        self.assertIn("battery", result.stderr.lower())
        self.assertTrue(self.state()["lid"])

    def test_lid_on_ac_does_not_warn(self) -> None:
        self.allow_lid()
        result = self.start("10m", "--lid")
        self.assertNotIn("battery", result.stderr.lower())

    # ---------------------------------------------------------------- lid setup / remove / status

    def test_lid_setup_writes_the_exact_rule_after_confirmation(self) -> None:
        result = self.ok("awake", "lid", "setup", input="y\n")
        line = "tester ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 0, /usr/bin/pmset -a disablesleep 1"
        seen = self.read("visudo.seen")
        self.assertIn(line, seen.splitlines())
        self.assertEqual(
            [
                entry
                for entry in seen.splitlines()
                if not entry.startswith("#") and entry
            ],
            [line],
        )
        self.assertTrue(self.read("visudo.log").startswith("-cf|"))
        install = next(call for call in self.jlog("sudo.log") if call[0] == "install")
        self.assertEqual(install[1:7], ["-m", "0440", "-o", "root", "-g", "wheel"])
        self.assertEqual(install[-1], SUDOERS_PATH)
        self.assertFalse(Path(install[-2]).exists(), "the temporary file is removed")
        self.assertIn(SUDOERS_PATH, result.stdout)
        self.assertIn(line, result.stdout)

    def test_lid_setup_needs_confirmation(self) -> None:
        result = self.ul("awake", "lid", "setup", input="n\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.read("sudo.log"), "")
        self.assertEqual(self.read("visudo.log"), "")
        self.assertEqual(self.ul("awake", "lid", "setup", input="").returncode, 1)
        self.assertEqual(self.read("sudo.log"), "")
        self.ok("awake", "lid", "setup", "--yes")
        self.assertTrue(any(call[0] == "install" for call in self.jlog("sudo.log")))

    def test_lid_setup_refuses_a_bad_user_name_and_a_rule_visudo_rejects(self) -> None:
        for name in ("bad name", "a;b", "x\nroot", "a,b"):
            result = self.ul(
                "awake", "lid", "setup", "--yes", env={"LOGNAME": name, "USER": name}
            )
            self.assertNotEqual(result.returncode, 0, repr(name))
        self.assertEqual(self.read("sudo.log"), "")
        (self.fake / "visudo_fail").write_text("")
        result = self.ul("awake", "lid", "setup", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(any(call[0] == "install" for call in self.jlog("sudo.log")))

    def test_lid_remove_deletes_only_our_file_after_confirmation(self) -> None:
        self.assertEqual(self.ul("awake", "lid", "remove", input="n\n").returncode, 1)
        self.assertEqual(self.read("sudo.log"), "")
        result = self.ok("awake", "lid", "remove", input="y\n")
        self.assertIn(SUDOERS_PATH, result.stdout)
        self.assertEqual(self.jlog("sudo.log"), [["rm", "-f", SUDOERS_PATH]])

    def test_lid_status_reports_whether_the_rule_works(self) -> None:
        result = self.ul("awake", "lid", "status")
        self.assertEqual(result.returncode, 1)
        self.assertIn("lid setup", result.stdout + result.stderr)
        self.allow_lid()
        result = self.ok("awake", "lid", "status")
        self.assertIn("ready", result.stdout.lower())
        calls = self.jlog("sudo.log")
        self.assertIn(["-n", "-l", "/usr/bin/pmset", "-a", "disablesleep", "1"], calls)

    def test_unknown_lid_action_is_a_usage_error(self) -> None:
        self.assertEqual(self.ul("awake", "lid", "nope").returncode, 2)
        self.assertEqual(self.ul("awake", "lid").returncode, 2)


if __name__ == "__main__":
    unittest.main()
