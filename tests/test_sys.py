"""`ul sys`: parsers on outputs captured from a real Mac (tests/fixtures/sys), rendering, JSON, fallbacks.

No test reaches a real system tool: every tool is a fake executable on a restricted PATH that prints a fixture.
"""

from __future__ import annotations

import io
import json
import os
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from ulbin import CoreTestCase

from unlawful import sysinfo

FIXTURES = HERE / "fixtures" / "sys"

# One script for every faked tool; it answers from the fixture files by tool name and arguments.
FAKE_TOOL = r"""import os, sys
tool = os.path.basename(sys.argv[0])
args = sys.argv[1:]
fixtures = os.environ["FAKE_FIXTURES"]
override = os.environ.get("FAKE_OVERRIDE", "")


def emit(name):
    for folder in (override, fixtures):
        path = os.path.join(folder, name) if folder else ""
        if path and os.path.exists(path):
            sys.stdout.buffer.write(open(path, "rb").read())
            raise SystemExit(0)
    sys.stderr.write("fake " + tool + ": no fixture " + name + "\n")
    raise SystemExit(1)


if tool == "sysctl":
    key = args[-1]
    emit("swapusage.txt" if key == "vm.swapusage" else "sysctl_" + key.replace(".", "_") + ".txt")
if tool == "ioreg":
    emit("ioreg_battery.plist" if "AppleSmartBattery" in args else "ioreg_gpu.txt")
if tool == "system_profiler":
    emit("system_profiler_power.json" if "SPPowerDataType" in args else "system_profiler_hardware.json")
if tool == "sw_vers":
    emit("sw_vers.txt")
emit(tool + ".txt")
"""

ALL_TOOLS = (
    "top",
    "vm_stat",
    "sysctl",
    "df",
    "ps",
    "ioreg",
    "system_profiler",
    "sw_vers",
)
NOW = 1793399528 + 11 * 86400 + 12 * 3600 + 5 * 60


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def install_tools(directory: Path, names: tuple[str, ...] = ALL_TOOLS) -> None:
    for name in names:
        script = directory / name
        script.write_text(f"#!{sys.executable}\n{FAKE_TOOL}", encoding="utf-8")
        script.chmod(0o755)


class FakeToolsCase(unittest.TestCase):
    """A restricted PATH (only the fakes) for in-process tests of the module."""

    tools: tuple[str, ...] = ALL_TOOLS

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.bin = Path(temp.name) / "bin"
        self.bin.mkdir()
        self.override = Path(temp.name) / "override"
        self.override.mkdir()
        install_tools(self.bin, self.tools)
        env = mock.patch.dict(
            os.environ,
            {
                "PATH": str(self.bin),
                "FAKE_FIXTURES": str(FIXTURES),
                "FAKE_OVERRIDE": str(self.override),
            },
        )
        env.start()
        self.addCleanup(env.stop)

    def run_main(
        self, *args: str, tty: bool = False, no_color: bool = False
    ) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        out.isatty = lambda: tty  # type: ignore[method-assign]
        env = {"NO_COLOR": "1"} if no_color else {}
        with (
            mock.patch.object(sys, "stdout", out),
            mock.patch.object(sys, "stderr", err),
            mock.patch.dict(os.environ, env),
        ):
            if not no_color:
                os.environ.pop("NO_COLOR", None)
            code = sysinfo.main(list(args))
        return code, out.getvalue(), err.getvalue()


class ParserTests(unittest.TestCase):
    def test_top_uses_the_last_cpu_sample_and_the_load_average(self) -> None:
        result = sysinfo.parse_top(fixture("top.txt"))
        # The first sample of `top -l 2` covers the time since boot; only the second one is a real interval.
        self.assertEqual(result["user"], 19.2)
        self.assertEqual(result["system"], 7.83)
        self.assertEqual(result["idle"], 73.13)
        self.assertEqual(result["load"], [5.24, 4.35, 3.67])

    def test_top_garbage_is_none(self) -> None:
        self.assertIsNone(sysinfo.parse_top(""))
        self.assertIsNone(sysinfo.parse_top("Processes: 1 total\n"))

    def test_vm_stat_counts_and_page_size(self) -> None:
        result = sysinfo.parse_vm_stat(fixture("vm_stat.txt"))
        self.assertEqual(result["page_size"], 16384)
        self.assertEqual(result["Pages free"], 19914)
        self.assertEqual(result["Anonymous pages"], 408428)
        self.assertEqual(result["Pages occupied by compressor"], 255497)
        self.assertIsNone(sysinfo.parse_vm_stat("nothing useful"))

    def test_memory_follows_activity_monitor(self) -> None:
        vm = sysinfo.parse_vm_stat(fixture("vm_stat.txt"))
        swap = fixture("swapusage.txt")
        memory = sysinfo.memory_info(vm, int(fixture("sysctl_hw_memsize.txt")), swap, 1)
        page = 16384
        self.assertEqual(memory["total_bytes"], 19327352832)
        # App memory = anonymous pages minus purgeable ones; used = app + wired + compressed.
        self.assertEqual(memory["app_bytes"], (408428 - 6156) * page)
        self.assertEqual(memory["wired_bytes"], 229886 * page)
        self.assertEqual(memory["compressed_bytes"], 255497 * page)
        self.assertEqual(
            memory["used_bytes"],
            memory["app_bytes"] + memory["wired_bytes"] + memory["compressed_bytes"],
        )
        self.assertEqual(memory["cached_bytes"], (213737 + 6156) * page)
        self.assertEqual(memory["swap_total_bytes"], 2048 * 1024 * 1024)
        self.assertEqual(memory["swap_used_bytes"], round(970.44 * 1024 * 1024))
        self.assertEqual(memory["pressure"], "normal")
        self.assertEqual(memory["pressure_level"], 1)

    def test_memory_pressure_names(self) -> None:
        vm = sysinfo.parse_vm_stat(fixture("vm_stat.txt"))
        names = [
            sysinfo.memory_info(vm, 1 << 34, "", level)["pressure"]
            for level in (1, 2, 4, None)
        ]
        self.assertEqual(names, ["normal", "warning", "critical", None])

    def test_memory_without_swap_text_has_no_swap(self) -> None:
        vm = sysinfo.parse_vm_stat(fixture("vm_stat.txt"))
        memory = sysinfo.memory_info(vm, 1 << 34, "", 1)
        self.assertIsNone(memory["swap_used_bytes"])
        self.assertIsNone(memory["swap_total_bytes"])

    def test_swap_units(self) -> None:
        self.assertEqual(
            sysinfo.parse_swap(
                "vm.swapusage: total = 1.50G  used = 0.00M  free = 1.50G  (encrypted)"
            ),
            (1610612736, 0),
        )

    def test_df_keeps_real_volumes_once_per_container(self) -> None:
        rows = sysinfo.real_disks(sysinfo.parse_df(fixture("df.txt")))
        # `/` (sealed system), Data, Preboot, Recovery... share one APFS container: one row, counted container-wide.
        self.assertEqual([row["mount"] for row in rows], ["/"])
        row = rows[0]
        self.assertEqual(row["total_bytes"], 971350180 * 1024)
        self.assertEqual(row["free_bytes"], 366329800 * 1024)
        self.assertEqual(row["used_bytes"], (971350180 - 366329800) * 1024)
        self.assertEqual(
            row["used_percent"], round(100 * (971350180 - 366329800) / 971350180, 1)
        )

    def test_df_external_volume_with_spaces_and_junk_mounts(self) -> None:
        text = fixture("df.txt") + (
            "/dev/disk5s1  1000000  250000  750000    25%  10 7500000  0%   /Volumes/My Drive\n"
            "//user@nas/share  5000000  1000000  4000000  20%  1 2 0%  /Volumes/share\n"
            "garbage line\n"
        )
        rows = sysinfo.real_disks(sysinfo.parse_df(text))
        self.assertEqual([row["mount"] for row in rows], ["/", "/Volumes/My Drive"])
        self.assertEqual(rows[1]["device"], "/dev/disk5s1")
        self.assertEqual(rows[1]["used_percent"], 25.0)

    def test_df_empty_is_empty(self) -> None:
        self.assertEqual(sysinfo.parse_df(""), [])
        self.assertEqual(sysinfo.real_disks([]), [])

    def test_ps_top_lists(self) -> None:
        rows = sysinfo.parse_ps(fixture("ps.txt"))
        by_cpu = sysinfo.top_processes(rows, "cpu", 5)
        by_mem = sysinfo.top_processes(rows, "memory", 5)
        self.assertEqual(len(by_cpu), 5)
        self.assertEqual(by_cpu[0]["pid"], 65871)
        self.assertEqual(by_cpu[0]["name"], "Claude Helper (Renderer)")
        self.assertEqual(by_cpu[0]["cpu_percent"], 201.8)
        self.assertEqual(by_cpu[0]["memory_bytes"], 522928 * 1024)
        cpus = [row["cpu_percent"] for row in by_cpu]
        self.assertEqual(cpus, sorted(cpus, reverse=True))
        mems = [row["memory_bytes"] for row in by_mem]
        self.assertEqual(mems, sorted(mems, reverse=True))

    def test_ps_names_with_spaces_and_no_path(self) -> None:
        rows = sysinfo.parse_ps(
            "  PID  %CPU    RSS COMM\n"
            "  801   0.0   5184 Core Audio Driver (BlackHole2ch.driver)\n"
            "  802   1.5   2000 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
            "  bad line\n"
        )
        self.assertEqual(
            [row["name"] for row in rows],
            ["Core Audio Driver (BlackHole2ch.driver)", "Google Chrome"],
        )

    def test_gpu_utilization_and_cores(self) -> None:
        result = sysinfo.parse_gpu(fixture("ioreg_gpu.txt"))
        self.assertEqual(result["usage_percent"], 30)
        self.assertEqual(result["cores"], 18)
        self.assertEqual(result["name"], "Apple M3 Pro")

    def test_gpu_without_statistics_is_none(self) -> None:
        self.assertIsNone(sysinfo.parse_gpu(""))
        self.assertIsNone(sysinfo.parse_gpu('+-o Something\n  { "model" = "Intel" }\n'))

    def test_boot_time_and_uptime(self) -> None:
        boot = sysinfo.parse_boot_time(fixture("sysctl_kern_boottime.txt"))
        self.assertEqual(boot, 1793399528)
        self.assertEqual(
            sysinfo.uptime_seconds(boot, NOW), 11 * 86400 + 12 * 3600 + 5 * 60
        )
        self.assertIsNone(sysinfo.parse_boot_time("garbage"))
        self.assertEqual(sysinfo.uptime_seconds(NOW + 100, NOW), 0)

    def test_battery_from_the_real_plist(self) -> None:
        info = sysinfo.parse_battery(
            (FIXTURES / "ioreg_battery.plist").read_bytes(),
            fixture("system_profiler_power.json"),
        )
        self.assertTrue(info["present"])
        self.assertEqual(info["percent"], 97)
        self.assertTrue(info["charging"])
        self.assertTrue(info["plugged_in"])
        self.assertEqual(info["state"], "charging")
        self.assertEqual(info["time_remaining_minutes"], 21)
        self.assertEqual(info["cycle_count"], 526)
        self.assertEqual(info["condition"], "Good")
        self.assertEqual(info["design_capacity_mah"], 6249)
        self.assertEqual(info["max_capacity_mah"], 5403)
        # System Settings shows the system_profiler value (87%), which the raw ratio (86.5%) does not equal.
        self.assertEqual(info["max_capacity_percent"], 87)
        self.assertIsNone(info["temperature_c"])

    def test_battery_without_system_profiler_computes_capacity(self) -> None:
        info = sysinfo.parse_battery(
            (FIXTURES / "ioreg_battery.plist").read_bytes(), None
        )
        self.assertEqual(info["max_capacity_percent"], round(100 * 5403 / 6249))
        self.assertIsNone(info["condition"])

    def battery_plist(self, **changes: object) -> bytes:
        data = plistlib.loads((FIXTURES / "ioreg_battery.plist").read_bytes())[0]
        data.update(changes)
        return plistlib.dumps([data])

    def test_battery_discharging_and_unknown_time(self) -> None:
        info = sysinfo.parse_battery(
            self.battery_plist(
                IsCharging=False,
                ExternalConnected=False,
                TimeRemaining=134,
                Temperature=3012,
            ),
            None,
        )
        self.assertEqual(info["state"], "discharging")
        self.assertFalse(info["plugged_in"])
        self.assertEqual(info["time_remaining_minutes"], 134)
        self.assertEqual(info["temperature_c"], 30.12)
        unknown = sysinfo.parse_battery(
            self.battery_plist(
                IsCharging=False, ExternalConnected=False, TimeRemaining=65535
            ),
            None,
        )
        self.assertIsNone(unknown["time_remaining_minutes"])

    def test_battery_charged_on_ac(self) -> None:
        info = sysinfo.parse_battery(
            self.battery_plist(
                IsCharging=False,
                ExternalConnected=True,
                FullyCharged=True,
                TimeRemaining=65535,
            ),
            None,
        )
        self.assertEqual(info["state"], "charged")
        self.assertIsNone(info["time_remaining_minutes"])

    def test_battery_absent_on_a_desktop(self) -> None:
        for raw in (b"", plistlib.dumps([]), b"  \n"):
            self.assertEqual(sysinfo.parse_battery(raw, None), {"present": False})

    def test_battery_broken_plist_is_none(self) -> None:
        self.assertIsNone(sysinfo.parse_battery(b"<not a plist", None))


class FormatTests(unittest.TestCase):
    def test_bar(self) -> None:
        self.assertEqual(sysinfo.bar(0, 10), "░" * 10)
        self.assertEqual(sysinfo.bar(100, 10), "█" * 10)
        self.assertEqual(sysinfo.bar(50, 10), "█████░░░░░")
        self.assertEqual(sysinfo.bar(250, 10), "█" * 10)
        self.assertEqual(sysinfo.bar(-5, 10), "░" * 10)

    def test_bytes(self) -> None:
        self.assertEqual(sysinfo.human_bytes(0), "0 B")
        self.assertEqual(sysinfo.human_bytes(1_500_000), "1.5 MB")
        self.assertEqual(sysinfo.human_bytes(19327352832, binary=True), "18.0 GB")
        self.assertEqual(sysinfo.human_bytes(971350180 * 1024), "994.7 GB")

    def test_duration(self) -> None:
        self.assertEqual(sysinfo.human_duration(45), "45s")
        self.assertEqual(sysinfo.human_duration(5 * 60 + 3), "5m")
        self.assertEqual(sysinfo.human_duration(3 * 3600 + 20 * 60), "3h 20m")
        self.assertEqual(
            sysinfo.human_duration(11 * 86400 + 12 * 3600 + 5 * 60), "11d 12h"
        )


class CollectTests(FakeToolsCase):
    def test_every_section_from_fixtures(self) -> None:
        data = sysinfo.collect(sysinfo.SECTIONS, now=NOW)
        self.assertEqual(data["system"]["model"], "MacBook Pro")
        self.assertEqual(data["system"]["identifier"], "Mac15,6")
        self.assertEqual(data["system"]["chip"], "Apple M3 Pro")
        self.assertEqual(data["system"]["os"], "macOS 27.2")
        self.assertEqual(
            data["system"]["uptime_seconds"], 11 * 86400 + 12 * 3600 + 5 * 60
        )
        cpu = data["cpu"]
        self.assertEqual(cpu["usage_percent"], 26.9)
        self.assertEqual(cpu["cores"], {"total": 12, "performance": 6, "efficiency": 6})
        self.assertEqual(cpu["load_average"], [5.24, 4.35, 3.67])
        self.assertEqual(data["gpu"]["usage_percent"], 30)
        self.assertEqual(data["memory"]["total_bytes"], 19327352832)
        self.assertEqual(data["memory"]["pressure"], "normal")
        self.assertEqual([disk["mount"] for disk in data["disk"]], ["/"])
        self.assertEqual(data["battery"]["cycle_count"], 526)
        self.assertEqual(len(data["top"]["cpu"]), 5)
        self.assertEqual(len(data["top"]["memory"]), 5)

    def test_only_the_asked_section_runs_its_tools(self) -> None:
        # Only df is installed: asking for disks works, nothing else is attempted or needed.
        for tool in ALL_TOOLS:
            if tool != "df":
                (self.bin / tool).unlink()
        data = sysinfo.collect(("disk",), now=NOW)
        self.assertEqual(list(data), ["disk"])
        self.assertEqual(data["disk"][0]["mount"], "/")

    def test_cpu_total_is_one_hundred_minus_idle(self) -> None:
        self.assertEqual(
            sysinfo.collect(("cpu",))["cpu"]["usage_percent"], round(100 - 73.13, 1)
        )

    def test_intel_mac_without_perf_levels_or_gpu_stats(self) -> None:
        (self.override / "sysctl_hw_perflevel0_logicalcpu.txt").write_text(
            ""
        )  # an empty answer is not a number
        data = sysinfo.collect(("cpu", "gpu"))
        self.assertEqual(
            data["cpu"]["cores"], {"total": 12, "performance": None, "efficiency": None}
        )
        (self.override / "ioreg_gpu.txt").write_text(
            '+-o X\n  {\n    "model" = "Intel"\n  }\n'
        )
        self.assertIsNone(sysinfo.collect(("gpu",))["gpu"])

    def test_desktop_battery(self) -> None:
        (self.override / "ioreg_battery.plist").write_bytes(plistlib.dumps([]))
        self.assertEqual(sysinfo.collect(("battery",))["battery"], {"present": False})


class MissingToolTests(FakeToolsCase):
    tools = ()

    def test_no_tools_means_n_a_everywhere(self) -> None:
        data = sysinfo.collect(sysinfo.SECTIONS, now=NOW)
        for name in ("cpu", "gpu", "memory", "disk", "battery", "top"):
            self.assertIsNone(data[name], name)
        for value in data["system"].values():
            self.assertIsNone(value)

    def test_text_and_exit_code_without_tools(self) -> None:
        code, out, err = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertNotIn("Traceback", out)
        self.assertGreaterEqual(out.count("n/a"), 6)

    def test_json_without_tools_has_null_sections(self) -> None:
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIsNone(data["cpu"])
        self.assertIsNone(data["battery"])

    def test_failing_tools_are_n_a_too(self) -> None:
        for tool in ALL_TOOLS:
            script = self.bin / tool
            script.write_text("#!/bin/sh\necho 'boom' >&2\nexit 7\n")
            script.chmod(0o755)
        code, out, err = self.run_main("cpu")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("n/a", out)

    def test_garbage_output_is_n_a_not_a_traceback(self) -> None:
        for tool in ALL_TOOLS:
            script = self.bin / tool
            script.write_text("#!/bin/sh\necho 'total nonsense 12 %% ;;;'\n")
            script.chmod(0o755)
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("Traceback", out)
        self.assertIn("n/a", out)


class PartialToolTests(FakeToolsCase):
    tools = ("df", "ps")

    def test_missing_top_only_hides_the_cpu(self) -> None:
        code, out, _ = self.run_main("--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIsNone(data["cpu"])
        self.assertEqual(data["disk"][0]["mount"], "/")
        self.assertEqual(data["top"]["cpu"][0]["name"], "Claude Helper (Renderer)")


class RenderTests(FakeToolsCase):
    def test_summary_text_has_every_part(self) -> None:
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        for needle in (
            "MacBook Pro",
            "Apple M3 Pro",
            "macOS 27.2",
            "CPU",
            "26.9%",
            "6P + 6E",
            "load 5.24 4.35 3.67",
            "GPU",
            "30%",
            "Memory",
            "pressure normal",
            "Swap",
            "Disks",
            "Battery",
            "97%",
            "526 cycles",
            "Good",
            "Top CPU",
            "Claude Helper (Renderer)",
            "Top memory",
        ):
            self.assertIn(needle, out)
        self.assertIn("█", out)
        self.assertIn("░", out)

    def test_no_colors_when_piped(self) -> None:
        _, out, _ = self.run_main()
        self.assertNotIn("\x1b", out)

    def test_colors_on_a_tty(self) -> None:
        _, out, _ = self.run_main(tty=True)
        self.assertIn("\x1b[", out)

    def test_no_color_variable_wins_over_a_tty(self) -> None:
        _, out, _ = self.run_main(tty=True, no_color=True)
        self.assertNotIn("\x1b", out)

    def test_section_shows_only_that_section(self) -> None:
        _, out, _ = self.run_main("disk")
        self.assertIn("Disks", out)
        self.assertNotIn("Battery", out)
        self.assertNotIn("CPU", out)

    def test_battery_discharging_text(self) -> None:
        data = plistlib.loads((FIXTURES / "ioreg_battery.plist").read_bytes())[0]
        data.update(
            IsCharging=False,
            ExternalConnected=False,
            TimeRemaining=134,
            CurrentCapacity=18,
        )
        (self.override / "ioreg_battery.plist").write_bytes(plistlib.dumps([data]))
        _, out, _ = self.run_main("battery")
        self.assertIn("18%", out)
        self.assertIn("discharging", out)
        self.assertIn("2h 14m left", out)

    def test_desktop_battery_text(self) -> None:
        (self.override / "ioreg_battery.plist").write_bytes(plistlib.dumps([]))
        _, out, _ = self.run_main("battery")
        self.assertIn("no battery", out)


class JsonTests(FakeToolsCase):
    def test_json_keys_and_numbers(self) -> None:
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(
            set(data), {"system", "cpu", "gpu", "memory", "disk", "battery", "top"}
        )
        self.assertEqual(
            set(data["cpu"]),
            {
                "usage_percent",
                "user_percent",
                "system_percent",
                "idle_percent",
                "cores",
                "load_average",
            },
        )
        self.assertEqual(
            set(data["memory"]),
            {
                "total_bytes", "used_bytes", "app_bytes", "wired_bytes", "compressed_bytes", "cached_bytes",
                "free_bytes", "swap_total_bytes", "swap_used_bytes", "pressure", "pressure_level",
            },
        )  # fmt: skip
        self.assertEqual(
            set(data["disk"][0]),
            {
                "mount",
                "device",
                "total_bytes",
                "used_bytes",
                "free_bytes",
                "used_percent",
            },
        )
        self.assertEqual(
            set(data["battery"]),
            {
                "present", "percent", "state", "charging", "plugged_in", "time_remaining_minutes", "cycle_count",
                "condition", "max_capacity_percent", "design_capacity_mah", "max_capacity_mah", "temperature_c",
            },
        )  # fmt: skip
        self.assertEqual(
            set(data["top"]["cpu"][0]), {"pid", "name", "cpu_percent", "memory_bytes"}
        )
        self.assertEqual(
            set(data["system"]), {"model", "identifier", "chip", "os", "uptime_seconds"}
        )
        for value in (
            data["cpu"]["usage_percent"],
            data["memory"]["used_bytes"],
            data["disk"][0]["total_bytes"],
        ):
            self.assertIsInstance(value, (int, float))
        self.assertNotIn("\x1b", out)

    def test_json_section_only(self) -> None:
        code, out, _ = self.run_main("cpu", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(list(json.loads(out)), ["cpu"])


class CommandLineTests(FakeToolsCase):
    def test_help_before_any_side_effect(self) -> None:
        # Even with no tools at all and a bad section behind it, --help just prints and returns 0.
        for flag in ("--help", "-h"):
            code, out, err = self.run_main("nonsense", flag)
            self.assertEqual((code, err), (0, ""))
            self.assertIn("ul sys", out)
            self.assertLess(len(out.splitlines()), 26)
            for needle in (
                "--json",
                "--watch",
                "cpu",
                "gpu",
                "mem",
                "disk",
                "battery",
                "top",
                "Example",
                "sudo",
            ):
                self.assertIn(needle, out)

    def test_unknown_section_and_option_are_usage_errors(self) -> None:
        for args in (("nonsense",), ("--bogus",), ("cpu", "disk")):
            code, out, err = self.run_main(*args)
            self.assertEqual(code, 2, args)
            self.assertEqual(out, "")
            self.assertIn("ul sys", err)

    def test_section_aliases(self) -> None:
        for alias, heading in (
            ("memory", "Memory"),
            ("ram", "Memory"),
            ("disks", "Disks"),
            ("batt", "Battery"),
        ):
            code, out, _ = self.run_main(alias)
            self.assertEqual(code, 0, alias)
            self.assertIn(heading, out)

    def test_watch_interval_parsing(self) -> None:
        self.assertEqual(sysinfo.parse_args(["--watch"]), (None, False, 2.0))
        self.assertEqual(sysinfo.parse_args(["--watch", "5"]), (None, False, 5.0))
        self.assertEqual(
            sysinfo.parse_args(["--watch=0.5", "cpu"]), ("cpu", False, 0.5)
        )
        self.assertEqual(
            sysinfo.parse_args(["--watch", "cpu", "--json"]), ("cpu", True, 2.0)
        )
        for bad in (
            ["--watch", "0"],
            ["--watch=-1"],
            ["--watch=abc"],
            ["--watch", "99999"],
        ):
            with self.assertRaises(sysinfo.UsageError, msg=bad):
                sysinfo.parse_args(bad)

    def test_bad_watch_interval_exits_2(self) -> None:
        code, _, err = self.run_main("--watch=0")
        self.assertEqual(code, 2)
        self.assertIn("--watch", err)


class WatchTests(FakeToolsCase):
    def watch(
        self, *args: str, tty: bool, frames: int = 2
    ) -> tuple[int, str, list[float]]:
        sleeps: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) >= frames:
                raise KeyboardInterrupt

        with mock.patch.object(sysinfo.time, "sleep", fake_sleep):
            code, out, err = self.run_main("--watch", *args, tty=tty)
        self.assertEqual(err, "")
        return code, out, sleeps

    def test_ctrl_c_exits_cleanly_and_restores_the_cursor(self) -> None:
        code, out, sleeps = self.watch("cpu", tty=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(out.count("\x1b[?25l"), 1)  # hidden once ...
        self.assertTrue(
            out.endswith(("\x1b[?25h\n", "\x1b[?25h"))
        )  # ... and always shown again
        self.assertEqual(
            out.count("\x1b[H"), 2
        )  # each frame redraws from the top-left corner

    def test_piped_watch_prints_frames_without_escape_codes(self) -> None:
        code, out, _ = self.watch("cpu", tty=False)
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b", out)
        self.assertEqual(out.count("CPU"), 2)

    def test_default_interval_is_two_seconds_minus_the_sampling_time(self) -> None:
        _, _, sleeps = self.watch("cpu", tty=False, frames=1)
        self.assertTrue(0 < sleeps[0] <= 2.0)

    def test_json_watch_is_one_object_per_line(self) -> None:
        code, out, _ = self.watch("cpu", "--json", tty=True, frames=3)
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(list(json.loads(line)), ["cpu"])

    def test_interrupt_while_sampling_is_clean_too(self) -> None:
        with mock.patch.object(sysinfo, "collect", side_effect=KeyboardInterrupt):
            code, out, err = self.run_main("--watch", tty=True)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("\x1b[?25h", out)


class CommandRunTests(CoreTestCase):
    """The seeded command through the real `ul` binary; PATH holds only the fakes."""

    def setUp(self) -> None:
        super().setUp()
        install_tools(self.bin)
        self.env["PATH"] = str(self.bin)
        self.env["FAKE_FIXTURES"] = str(FIXTURES)
        self.env.pop("NO_COLOR", None)

    def test_ul_sys_json(self) -> None:
        data = json.loads(self.ok("sys", "--json").stdout)
        self.assertEqual(data["cpu"]["cores"]["performance"], 6)
        self.assertEqual(data["battery"]["cycle_count"], 526)

    def test_ul_sys_text_and_help(self) -> None:
        out = self.ok("sys", "mem").stdout
        self.assertIn("Memory", out)
        self.assertIn("pressure normal", out)
        self.assertIn("ul sys", self.ok("sys", "-h").stdout)
        self.assertEqual(self.ul("sys", "nonsense").returncode, 2)

    def test_ul_sys_with_no_tools_at_all(self) -> None:
        for tool in ALL_TOOLS:
            (self.bin / tool).unlink()
        result = self.ok("sys")
        self.assertIn("n/a", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
