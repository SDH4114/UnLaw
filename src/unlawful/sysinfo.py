from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from xml.parsers.expat import ExpatError

from unlawful.command_help import COMMAND_HELP

SECTIONS = ("system", "cpu", "gpu", "memory", "disk", "battery", "top")
SECTION_NAMES = {
    "cpu": "cpu",
    "gpu": "gpu",
    "mem": "memory",
    "memory": "memory",
    "ram": "memory",
    "disk": "disk",
    "disks": "disk",
    "battery": "battery",
    "batt": "battery",
    "top": "top",
}
USAGE = "Usage: ul sys [cpu|gpu|mem|disk|battery|top] [--json] [--watch [seconds]]  (ul sys --help)"
DEFAULT_WATCH = 2.0
MAX_WATCH = 3600.0
BAR_WIDTH = 20
LABEL_WIDTH = 9
TOP_COUNT = 5

PRESSURE_NAMES = {1: "normal", 2: "warning", 4: "critical"}
# Mounts that are implementation details of macOS, simulators or installers, not drives a person uses.
HIDDEN_MOUNT_PREFIXES = ("/Library/Developer/", "/private/", "/System/Volumes/")
UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


class UsageError(Exception):
    pass


# ---------------------------------------------------------------- running tools


def run_tool(command: list[str], timeout: float = 5.0) -> bytes | None:
    """stdout of a read-only system tool, or None when it is missing, slow or fails."""
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def tool_text(command: list[str], timeout: float = 5.0) -> str | None:
    raw = run_tool(command, timeout)
    return None if raw is None else raw.decode("utf-8", errors="replace")


def sysctl_text(key: str) -> str | None:
    text = tool_text(["sysctl", "-n", key])
    return text.strip() if text and text.strip() else None


def sysctl_int(key: str) -> int | None:
    text = sysctl_text(key)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


# ---------------------------------------------------------------- parsers


def parse_top(text: str) -> dict | None:
    """CPU split and load average from `top -l 2`: the last sample, because the first one covers the time since boot."""
    cpu = re.findall(
        r"CPU usage:\s*([\d.]+)% user,\s*([\d.]+)% sys,\s*([\d.]+)% idle", text
    )
    if not cpu:
        return None
    user, system, idle = (float(value) for value in cpu[-1])
    load = re.findall(r"Load Avg:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", text)
    return {
        "user": user,
        "system": system,
        "idle": idle,
        "load": [float(value) for value in load[-1]] if load else None,
    }


def parse_vm_stat(text: str) -> dict | None:
    size = re.search(r"page size of (\d+) bytes", text)
    if size is None:
        return None
    result: dict = {"page_size": int(size.group(1))}
    for line in text.splitlines():
        match = re.match(r'^"?([^":]+?)"?:\s+(\d+)\.?\s*$', line)
        if match:
            result[match.group(1)] = int(match.group(2))
    return result if len(result) > 1 else None


def parse_swap(text: str) -> tuple[int, int] | None:
    """(total, used) bytes from `sysctl vm.swapusage`."""
    match = re.search(r"total = ([\d.]+)([KMGT]).*?used = ([\d.]+)([KMGT])", text)
    if match is None:
        return None
    total = round(float(match.group(1)) * UNITS[match.group(2)])
    used = round(float(match.group(3)) * UNITS[match.group(4)])
    return total, used


def memory_info(
    vm: dict, total_bytes: int, swap_text: str, pressure_level: int | None
) -> dict:
    """Memory the way Activity Monitor counts it: used = app + wired + compressed."""
    page = vm["page_size"]
    app = max(vm.get("Anonymous pages", 0) - vm.get("Pages purgeable", 0), 0) * page
    wired = vm.get("Pages wired down", 0) * page
    compressed = vm.get("Pages occupied by compressor", 0) * page
    cached = (vm.get("File-backed pages", 0) + vm.get("Pages purgeable", 0)) * page
    free = (vm.get("Pages free", 0) + vm.get("Pages speculative", 0)) * page
    swap = parse_swap(swap_text)
    return {
        "total_bytes": total_bytes,
        "used_bytes": app + wired + compressed,
        "app_bytes": app,
        "wired_bytes": wired,
        "compressed_bytes": compressed,
        "cached_bytes": cached,
        "free_bytes": free,
        "swap_total_bytes": swap[0] if swap else None,
        "swap_used_bytes": swap[1] if swap else None,
        "pressure": PRESSURE_NAMES.get(pressure_level)
        if pressure_level is not None
        else None,
        "pressure_level": pressure_level,
    }


DF_LINE = re.compile(
    r"^(?P<device>\S.*?)\s+(?P<blocks>\d+)\s+(?P<used>\d+)\s+(?P<avail>\d+)\s+\d+%\s+\d+\s+\d+\s+(?:\d+%|-)\s+(?P<mount>/.*)$"
)


def parse_df(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        match = DF_LINE.match(line)
        if match:
            rows.append(
                {
                    "device": match.group("device"),
                    "mount": match.group("mount"),
                    "total_bytes": int(match.group("blocks")) * 1024,
                    "free_bytes": int(match.group("avail")) * 1024,
                }
            )
    return rows


def real_disks(rows: list[dict]) -> list[dict]:
    """Volumes a person recognises. APFS volumes of one container share its space, so each container is listed once."""
    disks = []
    seen: set[tuple[str, int, int]] = set()
    for row in rows:
        mount = row["mount"]
        if not row["device"].startswith("/dev/") or row["total_bytes"] <= 0:
            continue
        if mount.startswith(HIDDEN_MOUNT_PREFIXES) and mount != "/System/Volumes/Data":
            continue
        container = re.match(r"/dev/(disk\d+)", row["device"])
        key = (
            container.group(1) if container else row["device"],
            row["total_bytes"],
            row["free_bytes"],
        )
        if key in seen:
            continue
        seen.add(key)
        used = max(row["total_bytes"] - row["free_bytes"], 0)
        disks.append(
            {
                "mount": mount,
                "device": row["device"],
                "total_bytes": row["total_bytes"],
                "used_bytes": used,
                "free_bytes": row["free_bytes"],
                "used_percent": round(100 * used / row["total_bytes"], 1),
            }
        )
    return disks


def parse_ps(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        match = re.match(r"^\s*(\d+)\s+([\d.]+)\s+(\d+)\s+(\S.*?)\s*$", line)
        if match:
            rows.append(
                {
                    "pid": int(match.group(1)),
                    "name": match.group(4).rsplit("/", 1)[-1],
                    "cpu_percent": float(match.group(2)),
                    "memory_bytes": int(match.group(3)) * 1024,
                }
            )
    return rows


def top_processes(rows: list[dict], by: str, count: int) -> list[dict]:
    key = "cpu_percent" if by == "cpu" else "memory_bytes"
    return sorted(rows, key=lambda row: (-row[key], row["pid"]))[:count]


def parse_gpu(text: str) -> dict | None:
    usage = re.search(r'"Device Utilization %"\s*=\s*(\d+)', text)
    if usage is None:
        return None
    cores = re.search(r'"gpu-core-count"\s*=\s*(\d+)', text)
    name = re.search(r'"model"\s*=\s*"([^"]*)"', text)
    return {
        "usage_percent": int(usage.group(1)),
        "cores": int(cores.group(1)) if cores else None,
        "name": name.group(1) if name else None,
    }


def parse_boot_time(text: str) -> int | None:
    match = re.search(r"sec\s*=\s*(\d+)", text)
    return int(match.group(1)) if match else None


def uptime_seconds(boot: int, now: float) -> int:
    return max(int(now - boot), 0)


def profiler_battery(text: str | None) -> dict:
    """The battery health fields of `system_profiler SPPowerDataType -json` (empty when unreadable)."""
    try:
        for item in json.loads(text or "")["SPPowerDataType"]:
            health = item.get("sppower_battery_health_info")
            if isinstance(health, dict):
                return health
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return {}


def parse_battery(raw: bytes, profiler: str | None) -> dict | None:
    """{"present": False} for a Mac without battery, None when the plist cannot be read."""
    if not raw.strip():
        return {"present": False}
    try:
        data = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ExpatError, ValueError, OverflowError):
        return None
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict) or data.get("BatteryInstalled") is False:
        return {"present": False}

    detail = (
        data.get("BatteryData") if isinstance(data.get("BatteryData"), dict) else {}
    )
    health = profiler_battery(profiler)

    def number(*names: str) -> int | float | None:
        for source in (data, detail):
            for name in names:
                value = source.get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return value
        return None

    current, maximum = number("CurrentCapacity"), number("MaxCapacity")
    percent = None
    if current is not None:
        percent = (
            round(100 * current / maximum)
            if maximum and maximum != 100
            else round(current)
        )
    charging = bool(data.get("IsCharging"))
    plugged = bool(data.get("ExternalConnected"))
    if charging:
        state = "charging"
    elif plugged and (data.get("FullyCharged") or (percent or 0) >= 100):
        state = "charged"
    elif plugged:
        state = "not_charging"
    else:
        state = "discharging"
    minutes = number("TimeRemaining")
    if (
        minutes is None
        or minutes < 0
        or minutes >= 65535
        or state in ("charged", "not_charging")
    ):
        minutes = None
    design, raw_max = number("DesignCapacity"), number("AppleRawMaxCapacity")
    capacity = None
    match = re.match(
        r"\s*(\d+)\s*%", str(health.get("sppower_battery_health_maximum_capacity", ""))
    )
    if match:
        capacity = int(match.group(1))  # what System Settings shows
    elif design and raw_max:
        capacity = round(100 * raw_max / design)
    temperature = number("Temperature")
    cycles = number("CycleCount")
    if cycles is None:
        cycles = health.get("sppower_battery_cycle_count")
    condition = health.get("sppower_battery_health")
    return {
        "present": True,
        "percent": percent,
        "state": state,
        "charging": charging,
        "plugged_in": plugged,
        "time_remaining_minutes": minutes,
        "cycle_count": cycles,
        "condition": condition if isinstance(condition, str) else None,
        "max_capacity_percent": capacity,
        "design_capacity_mah": design,
        "max_capacity_mah": raw_max,
        "temperature_c": round(temperature / 100, 2)
        if temperature is not None
        else None,
    }


# ---------------------------------------------------------------- collectors


def collect_system(now: float) -> dict:
    hardware: dict = {}
    text = tool_text(["system_profiler", "SPHardwareDataType", "-json"])
    try:
        hardware = json.loads(text or "")["SPHardwareDataType"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        hardware = {}
    version = tool_text(["sw_vers", "-productVersion"])
    boot_text = sysctl_text("kern.boottime")
    boot = parse_boot_time(boot_text) if boot_text else None
    return {
        "model": hardware.get("machine_name"),
        "identifier": hardware.get("machine_model") or sysctl_text("hw.model"),
        "chip": hardware.get("chip_type") or sysctl_text("machdep.cpu.brand_string"),
        "os": f"macOS {version.strip()}" if version and version.strip() else None,
        "uptime_seconds": uptime_seconds(boot, now) if boot is not None else None,
    }


def collect_cpu() -> dict | None:
    # One `top -l 2 -s 1` takes ~1.3 s; the second sample is a true one-second interval. The first sample and
    # `top -l 1` average over the time since boot, and `-s 0` gives a ~0.1 s window that jumps between runs.
    text = tool_text(["top", "-l", "2", "-n", "0", "-s", "1"], timeout=10.0)
    parsed = parse_top(text) if text else None
    if parsed is None:
        return None
    performance = sysctl_int("hw.perflevel0.logicalcpu")
    efficiency = sysctl_int("hw.perflevel1.logicalcpu")
    if performance is None or efficiency is None:
        performance = efficiency = None
    total = sysctl_int("hw.ncpu") or os.cpu_count()
    usage = min(max(100 - parsed["idle"], 0.0), 100.0)
    return {
        "usage_percent": round(usage, 1),
        "user_percent": round(parsed["user"], 1),
        "system_percent": round(parsed["system"], 1),
        "idle_percent": round(parsed["idle"], 1),
        "cores": {"total": total, "performance": performance, "efficiency": efficiency},
        "load_average": parsed["load"],
    }


def collect_gpu() -> dict | None:
    text = tool_text(["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"])
    return parse_gpu(text) if text else None


def collect_memory() -> dict | None:
    vm_text = tool_text(["vm_stat"])
    vm = parse_vm_stat(vm_text) if vm_text else None
    total = sysctl_int("hw.memsize")
    if vm is None or total is None:
        return None
    swap_text = tool_text(["sysctl", "vm.swapusage"]) or ""
    return memory_info(
        vm, total, swap_text, sysctl_int("kern.memorystatus_vm_pressure_level")
    )


def collect_disk() -> list[dict] | None:
    text = tool_text(["df", "-k"])
    rows = parse_df(text) if text else []
    return real_disks(rows) if rows else None


def collect_battery() -> dict | None:
    raw = run_tool(["ioreg", "-r", "-c", "AppleSmartBattery", "-a"])
    if raw is None:
        return None
    if not raw.strip():
        return {"present": False}
    return parse_battery(
        raw, tool_text(["system_profiler", "SPPowerDataType", "-json"])
    )


def collect_top() -> dict | None:
    text = tool_text(["ps", "-Ao", "pid,pcpu,rss,comm"])
    rows = parse_ps(text) if text else []
    if not rows:
        return None
    return {
        "cpu": top_processes(rows, "cpu", TOP_COUNT),
        "memory": top_processes(rows, "memory", TOP_COUNT),
    }


def safely(function: Callable[[], object]) -> object:
    try:
        return function()
    except Exception:  # noqa: BLE001 - a broken tool output must degrade to "n/a", never to a traceback
        return None


def collect(sections: Sequence[str], now: float | None = None) -> dict:
    """The data of the chosen sections; a part that cannot be read is None. Slow collectors run side by side."""
    moment = time.time() if now is None else now
    jobs: dict[str, Callable[[], object]] = {
        "system": lambda: collect_system(moment),
        "cpu": collect_cpu,
        "gpu": collect_gpu,
        "memory": collect_memory,
        "disk": collect_disk,
        "battery": collect_battery,
        "top": collect_top,
    }
    chosen = [name for name in sections if name in jobs]
    pool = ThreadPoolExecutor(max_workers=len(chosen) or 1)
    try:
        futures = {name: pool.submit(safely, jobs[name]) for name in chosen}
        return {name: future.result() for name, future in futures.items()}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------- formatting


def bar(percent: float, width: int = BAR_WIDTH) -> str:
    filled = min(max(round(percent / 100 * width), 0), width)
    return "█" * filled + "░" * (width - filled)


def human_bytes(count: float, binary: bool = False) -> str:
    base = 1024 if binary else 1000
    value = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < base or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= base
    return f"{value:.1f} TB"


def human_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def use_color(stream: object) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty()) and not os.environ.get("NO_COLOR")


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def paint(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self.paint("1", text)

    def dim(self, text: str) -> str:
        return self.paint("2", text)

    def meter(
        self, percent: float, text: str | None = None, invert: bool = False
    ) -> str:
        """A bar (green, yellow, red as it fills; the other way round for a battery) followed by the text."""
        level = 100 - percent if invert else percent
        code = "32" if level < 60 else "33" if level < 85 else "31"
        return self.paint(code, bar(percent)) + (f" {text}" if text else "")


def row(style: Style, label: str, body: str) -> str:
    return f"{style.bold(label.ljust(LABEL_WIDTH))}{body}"


def render_system(style: Style, system: dict | None) -> list[str]:
    if not system or all(value is None for value in system.values()):
        return [row(style, "System", "n/a")]
    name = system["model"] or system["identifier"] or "Mac"
    parts = [style.bold(name)]
    if system["model"] and system["identifier"]:
        parts[0] += f" ({system['identifier']})"
    for part in (system["chip"], system["os"]):
        if part:
            parts.append(part)
    if system["uptime_seconds"] is not None:
        parts.append(f"up {human_duration(system['uptime_seconds'])}")
    return ["  ".join(parts)]


def render_cpu(style: Style, cpu: dict | None) -> list[str]:
    if not cpu:
        return [row(style, "CPU", "n/a")]
    cores = cpu["cores"]
    if cores["performance"] is not None:
        core_text = f"{cores['performance']}P + {cores['efficiency']}E cores"
    elif cores["total"]:
        core_text = f"{cores['total']} cores"
    else:
        core_text = ""
    load = (
        " ".join(f"{value:.2f}" for value in cpu["load_average"])
        if cpu["load_average"]
        else None
    )
    details = [
        f"user {cpu['user_percent']}%",
        f"system {cpu['system_percent']}%",
        core_text,
    ]
    if load:
        details.append(f"load {load}")
    body = style.meter(cpu["usage_percent"], f"{cpu['usage_percent']:5.1f}%")
    return [
        row(
            style,
            "CPU",
            body + "  " + style.dim("  ".join(part for part in details if part)),
        )
    ]


def render_gpu(style: Style, gpu: dict | None) -> list[str]:
    if not gpu:
        return [row(style, "GPU", "n/a")]
    detail = " ".join(
        part
        for part in (gpu["name"], f"{gpu['cores']} cores" if gpu["cores"] else None)
        if part
    )
    body = style.meter(gpu["usage_percent"], f"{gpu['usage_percent']:5d}%")
    return [row(style, "GPU", body + ("  " + style.dim(detail) if detail else ""))]


def render_memory(style: Style, memory: dict | None) -> list[str]:
    if not memory:
        return [row(style, "Memory", "n/a")]
    total, used = memory["total_bytes"], memory["used_bytes"]
    percent = 100 * used / total if total else 0.0
    text = f"{human_bytes(used, True)} of {human_bytes(total, True)} ({percent:.0f}%)"
    details = [
        f"app {human_bytes(memory['app_bytes'], True)}",
        f"wired {human_bytes(memory['wired_bytes'], True)}",
        f"compressed {human_bytes(memory['compressed_bytes'], True)}",
        f"pressure {memory['pressure'] or 'n/a'}",
    ]
    lines = [
        row(
            style,
            "Memory",
            style.meter(percent, text) + "  " + style.dim("  ".join(details)),
        )
    ]
    if memory["swap_total_bytes"] is not None:
        swap_used, swap_total = memory["swap_used_bytes"], memory["swap_total_bytes"]
        swap_percent = 100 * swap_used / swap_total if swap_total else 0.0
        swap_text = f"{human_bytes(swap_used, True)} of {human_bytes(swap_total, True)}"
        lines.append(row(style, "Swap", style.meter(swap_percent, swap_text)))
    else:
        lines.append(row(style, "Swap", "n/a"))
    return lines


def render_disk(style: Style, disks: list[dict] | None) -> list[str]:
    if disks is None:
        return [row(style, "Disks", "n/a")]
    if not disks:
        return [row(style, "Disks", "none")]
    width = max(len(disk["mount"]) for disk in disks)
    lines = [style.bold("Disks")]
    for disk in disks:
        text = f"{human_bytes(disk['used_bytes'])} of {human_bytes(disk['total_bytes'])} ({disk['used_percent']:.0f}%)"
        free = style.dim(f"free {human_bytes(disk['free_bytes'])}")
        lines.append(
            f"  {disk['mount'].ljust(width)}  {style.meter(disk['used_percent'], text)}  {free}"
        )
    return lines


def render_battery(style: Style, battery: dict | None) -> list[str]:
    if not battery:
        return [row(style, "Battery", "n/a")]
    if not battery["present"]:
        return [row(style, "Battery", "no battery")]
    state = {
        "charging": "charging",
        "charged": "charged",
        "not_charging": "plugged in, not charging",
        "discharging": "discharging",
    }[battery["state"]]
    minutes = battery["time_remaining_minutes"]
    if minutes is not None:
        suffix = "to full" if battery["state"] == "charging" else "left"
        state += f", {human_duration(minutes * 60)} {suffix}"
    details = [state]
    if battery["cycle_count"] is not None:
        details.append(f"{battery['cycle_count']} cycles")
    if battery["condition"]:
        details.append(f"condition {battery['condition']}")
    if battery["max_capacity_percent"] is not None:
        capacity = f"max capacity {battery['max_capacity_percent']}%"
        if battery["max_capacity_mah"] and battery["design_capacity_mah"]:
            capacity += f" ({battery['max_capacity_mah']} of {battery['design_capacity_mah']} mAh)"
        details.append(capacity)
    if battery["temperature_c"] is not None:
        details.append(f"{battery['temperature_c']:.1f} °C")
    if battery["percent"] is None:
        return [row(style, "Battery", "  ".join(details))]
    body = style.meter(battery["percent"], f"{battery['percent']:5d}%", invert=True)
    return [row(style, "Battery", body + "  " + style.dim("  ".join(details)))]


def render_top(style: Style, top: dict | None) -> list[str]:
    if not top:
        return [row(style, "Top", "n/a")]
    lines: list[str] = []
    for title, key in (("Top CPU", "cpu"), ("Top memory", "memory")):
        lines.append(style.bold(title))
        for process in top[key]:
            cpu = f"{process['cpu_percent']:5.1f}%"
            memory = human_bytes(process["memory_bytes"]).rjust(9)
            lines.append(f"  {process['pid']:>6}  {cpu}  {memory}  {process['name']}")
    return lines


RENDERERS = {
    "system": render_system,
    "cpu": render_cpu,
    "gpu": render_gpu,
    "memory": render_memory,
    "disk": render_disk,
    "battery": render_battery,
    "top": render_top,
}


def render(data: dict, color: bool) -> str:
    style = Style(color)
    blocks = [RENDERERS[name](style, value) for name, value in data.items()]
    # The header line stands apart; the meters follow without blank lines, the process lists get one.
    lines: list[str] = []
    for name, block in zip(data, blocks):
        if name in ("system", "top") and lines:
            lines.append("")
        lines.extend(block)
        if name == "system":
            lines.append("")
    return "\n".join(lines).rstrip("\n")


# ---------------------------------------------------------------- command line


def parse_interval(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise UsageError(f"--watch needs a number of seconds, got {text!r}") from None
    if not 0 < value <= MAX_WATCH:
        raise UsageError(f"--watch seconds must be between 0 and {MAX_WATCH:.0f}")
    return value


def is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def parse_args(args: Sequence[str]) -> tuple[str | None, bool, float | None]:
    """(section, json, watch interval); section None means everything."""
    section: str | None = None
    as_json = False
    interval: float | None = None
    items = list(args)
    index = 0
    while index < len(items):
        arg = items[index]
        index += 1
        if arg == "--json":
            as_json = True
        elif arg == "--watch":
            interval = DEFAULT_WATCH
            if index < len(items) and is_number(items[index]):
                interval = parse_interval(items[index])
                index += 1
        elif arg.startswith("--watch="):
            interval = parse_interval(arg.split("=", 1)[1])
        elif arg.startswith("-"):
            raise UsageError(f"unknown option {arg}")
        elif arg in SECTION_NAMES:
            if section is not None:
                raise UsageError("only one section at a time")
            section = SECTION_NAMES[arg]
        else:
            raise UsageError(f"unknown section {arg!r}")
    return section, as_json, interval


def watch(sections: Sequence[str], as_json: bool, interval: float) -> int:
    """Redraw in place until Ctrl+C. JSON mode prints one object per line instead of redrawing."""
    out = sys.stdout
    color = use_color(out)
    redraw = color and not as_json
    if redraw:
        out.write("\x1b[?25l\x1b[2J")
        out.flush()
    try:
        while True:
            started = time.monotonic()
            data = collect(sections)
            if as_json:
                out.write(json.dumps(data) + "\n")
            elif redraw:
                lines = render(data, color).split("\n")
                out.write(
                    "\x1b[H" + "".join(line + "\x1b[K\n" for line in lines) + "\x1b[J"
                )
            else:
                out.write(render(data, color) + "\n\n")
            out.flush()
            time.sleep(max(interval - (time.monotonic() - started), 0.0))
    except KeyboardInterrupt:
        pass
    finally:
        if redraw:
            out.write("\x1b[?25h\n")
            out.flush()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "help" or any(arg in {"-h", "--help"} for arg in args):
        print(COMMAND_HELP["sys"], end="")
        return 0
    try:
        section, as_json, interval = parse_args(args)
    except UsageError as error:
        print(f"ul sys: {error}\n{USAGE}", file=sys.stderr)
        return 2
    sections = SECTIONS if section is None else (section,)
    if interval is not None:
        return watch(sections, as_json, interval)
    data = collect(sections)
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        print(render(data, use_color(sys.stdout)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
