# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Computer stats: CPU per core, GPU, RAM, network, disk, battery and power."""
from __future__ import annotations

COMMAND_HELP = "Computer stats: CPU per core, GPU, RAM, network, disk, battery and power.\nUsage: ul sys [cpu|gpu|mem|net|io|disk|battery|top ...] [--json] [--watch [seconds]]\n  (none)         One-screen summary of everything below; name one or more parts for only those\n  cpu            Usage (user/system), every core (performance and efficiency), load average\n  gpu            GPU utilization and the memory it holds (Apple Silicon)\n  mem            Used (app, wired, compressed), swap, memory pressure (like Activity Monitor)\n  net            Download and upload speed now, totals since start-up\n  io             Disk reads and writes per second\n  disk           Mounted volumes: used, free, a bar\n  battery        Charge, time left, cycles, condition, max capacity, what the Mac draws (W)\n  top            Top 5 processes by CPU and by memory, number of processes\nOptions:\n  --json             Machine-readable output: stable keys, numbers, null for n/a\n  --watch [seconds]  Refresh in place (default 2); Ctrl+C exits. With --json: one line per round\nNotes:\n  Numbers come straight from macOS: the kernel's CPU ticks and memory counters, sysctl,\n  IOKit (GPU, battery, disks) and the thermal state, the sources Activity Monitor uses.\n  CPU, network and disk speed: over 0.5 s, with --watch since the last round. Model, chip\n  and battery health are cached (runtime/sys-cache.json). A part that cannot be read is n/a.\n  Read-only, no sudo; CPU and fan temperatures would need it, so they are left out.\n  Colors only on a terminal; NO_COLOR turns them off.\nExamples:\n  ul sys\n  ul sys cpu mem --json\n  ul sys --watch 5 cpu\n"

import ctypes
import ctypes.util
import json
import os
import platform
import plistlib
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.parsers.expat import ExpatError


SECTIONS = ("system", "cpu", "gpu", "memory", "network", "io", "disk", "battery", "top")
SECTION_NAMES = {
    "cpu": "cpu",
    "gpu": "gpu",
    "net": "network",
    "network": "network",
    "io": "io",
    "mem": "memory",
    "memory": "memory",
    "ram": "memory",
    "disk": "disk",
    "disks": "disk",
    "battery": "battery",
    "batt": "battery",
    "top": "top",
}
USAGE = "Usage: ul sys [cpu|gpu|mem|net|io|disk|battery|top ...] [--json] [--watch [seconds]]  (ul sys --help)"
DEFAULT_WATCH = 2.0
MAX_WATCH = 3600.0
BAR_WIDTH = 20
LABEL_WIDTH = 9
TOP_COUNT = 5

PRESSURE_NAMES = {1: "normal", 2: "warning", 4: "critical"}
THERMAL_NAMES = {0: "nominal", 1: "fair", 2: "serious", 3: "critical"}
# Seconds between the two readings of the CPU tick, network and disk counters (they run side by side).
SAMPLE = 0.5
# How long the battery health from system_profiler is kept (it changes over weeks; one call costs ~50 ms of CPU).
POWER_CACHE_SECONDS = 600.0
# Interfaces that are tunnels, bridges or Apple's peer-to-peer links, not the Mac's connection.
VIRTUAL_INTERFACES = ("lo", "utun", "awdl", "llw", "bridge", "gif", "stf", "anpi", "ap", "ipsec", "vmenet", "pktap")
# Mounts that are implementation details of macOS, simulators or installers, not drives a person uses.
HIDDEN_MOUNT_PREFIXES = ("/Library/Developer/", "/private/", "/System/Volumes/")
UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


class UsageError(Exception):
    pass


# ---------------------------------------------------------------- native readings
#
# The numbers Activity Monitor shows come from the kernel: per-core CPU ticks
# (host_processor_info), the VM counters (host_statistics64), sysctl values and
# NSProcessInfo's thermal state. They are read here through ctypes, with no tool
# started; when that is impossible (or UNLAW_SYS_NATIVE=0, which the tests set)
# the collectors fall back to top, vm_stat and sysctl.

PROCESSOR_CPU_LOAD_INFO = 2
HOST_VM_INFO64 = 4
_LIBC: ctypes.CDLL | None = None


def native() -> ctypes.CDLL | None:
    global _LIBC
    if os.environ.get("UNLAW_SYS_NATIVE", "1") == "0" or sys.platform != "darwin":
        return None
    if _LIBC is None:
        try:
            _LIBC = ctypes.CDLL(None, use_errno=True)
            _LIBC.mach_host_self.restype = ctypes.c_uint
        except (OSError, AttributeError):
            return None
    return _LIBC


def native_sysctl(name: str) -> bytes | None:
    libc = native()
    if libc is None:
        return None
    key = name.encode()
    length = ctypes.c_size_t(0)
    if libc.sysctlbyname(key, None, ctypes.byref(length), None, ctypes.c_size_t(0)) != 0 or not length.value:
        return None
    buffer = ctypes.create_string_buffer(length.value)
    if libc.sysctlbyname(key, buffer, ctypes.byref(length), None, ctypes.c_size_t(0)) != 0:
        return None
    return buffer.raw[: length.value]


def cpu_ticks() -> list[tuple[int, int, int, int]] | None:
    """(user, system, idle, nice) ticks per logical core since boot."""
    libc = native()
    if libc is None:
        return None
    count = ctypes.c_uint(0)
    info = ctypes.POINTER(ctypes.c_int)()
    size = ctypes.c_uint(0)
    host = libc.mach_host_self()
    if libc.host_processor_info(host, PROCESSOR_CPU_LOAD_INFO, ctypes.byref(count), ctypes.byref(info), ctypes.byref(size)) != 0:
        return None
    ticks = [tuple(info[core * 4 + state] & 0xFFFFFFFF for state in range(4)) for core in range(count.value)]
    task = ctypes.c_uint.in_dll(libc, "mach_task_self_")
    libc.vm_deallocate(task, ctypes.cast(info, ctypes.c_void_p), ctypes.c_size_t(size.value * 4))
    return ticks  # type: ignore[return-value]


def core_usage(before: Sequence[tuple[int, ...]], after: Sequence[tuple[int, ...]]) -> list[dict]:
    """Per-core busy, user and system shares between two tick readings (32-bit counters may wrap)."""
    cores = []
    for old, new in zip(before, after):
        user, system, idle, nice = ((b - a) % (1 << 32) for a, b in zip(old, new))
        total = user + system + idle + nice
        cores.append(
            {
                "busy": 100 * (total - idle) / total if total else 0.0,
                "user": 100 * (user + nice) / total if total else 0.0,
                "system": 100 * system / total if total else 0.0,
                "ticks": total,
            }
        )
    return cores


class _VmStatistics64(ctypes.Structure):
    _fields_ = (
        [(name, ctypes.c_uint32) for name in ("free_count", "active_count", "inactive_count", "wire_count")]
        + [(name, ctypes.c_uint64) for name in ("zero_fill_count", "reactivations", "pageins", "pageouts", "faults", "cow_faults", "lookups", "hits", "purges")]
        + [(name, ctypes.c_uint32) for name in ("purgeable_count", "speculative_count")]
        + [(name, ctypes.c_uint64) for name in ("decompressions", "compressions", "swapins", "swapouts")]
        + [(name, ctypes.c_uint32) for name in ("compressor_page_count", "throttled_count", "external_page_count", "internal_page_count")]
        + [("total_uncompressed_pages_in_compressor", ctypes.c_uint64)]
    )


def native_vm() -> dict | None:
    """The VM counters under vm_stat's names, so memory_info reads both the same way."""
    libc = native()
    page = native_sysctl("hw.pagesize")
    if libc is None or page is None:
        return None
    stats = _VmStatistics64()
    count = ctypes.c_uint(ctypes.sizeof(stats) // 4)
    if libc.host_statistics64(libc.mach_host_self(), HOST_VM_INFO64, ctypes.byref(stats), ctypes.byref(count)) != 0:
        return None
    return {
        "page_size": int.from_bytes(page, "little"),
        "Pages free": stats.free_count,
        "Pages speculative": stats.speculative_count,
        "Pages wired down": stats.wire_count,
        "Pages purgeable": stats.purgeable_count,
        "File-backed pages": stats.external_page_count,
        "Anonymous pages": stats.internal_page_count,
        "Pages occupied by compressor": stats.compressor_page_count,
        "Pageins": stats.pageins,
        "Pageouts": stats.pageouts,
        "Swapins": stats.swapins,
        "Swapouts": stats.swapouts,
    }


def native_swap() -> tuple[int, int] | None:
    """(total, used) from the xsw_usage struct of vm.swapusage."""
    raw = native_sysctl("vm.swapusage")
    if raw is None or len(raw) < 24:
        return None
    total, _available, used = (int.from_bytes(raw[i : i + 8], "little") for i in (0, 8, 16))
    return total, used


def native_int(name: str) -> int | None:
    raw = native_sysctl(name)
    return int.from_bytes(raw, "little", signed=True) if raw is not None and len(raw) in (4, 8) else None


def native_text(name: str) -> str | None:
    raw = native_sysctl(name)
    return printable(raw.rstrip(b"\0").decode("utf-8", "replace")) if raw else None


def thermal_state() -> str | None:
    """NSProcessInfo.thermalState: how hard macOS is throttling for heat (nominal, fair, serious, critical)."""
    if native() is None:
        return None
    try:
        objc = ctypes.CDLL(ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib")
        ctypes.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p
        address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        send_object = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
        send_long = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(address)
        info = send_object(objc.objc_getClass(b"NSProcessInfo"), objc.sel_registerName(b"processInfo"))
        if not info:
            return None
        return THERMAL_NAMES.get(send_long(info, objc.sel_registerName(b"thermalState")))
    except (OSError, AttributeError, TypeError):
        return None


def boot_time() -> int | None:
    raw = native_sysctl("kern.boottime")
    if raw is not None and len(raw) >= 8:
        return int.from_bytes(raw[:8], "little")  # struct timeval: seconds first
    text = sysctl_text("kern.boottime")
    return parse_boot_time(text) if text else None


# ---------------------------------------------------------------- cache and watch state
#
# What does not change while the Mac runs (model, chip, core kinds) is read once per
# boot, the battery health from system_profiler once per POWER_CACHE_SECONDS: those
# tools cost ~100 ms of CPU, and Unlaw.app's menu bar asks every 10 s. They are kept in
# memory and in $UNLAW_STORAGE/runtime/sys-cache-2.json; a damaged file is just read again.
# Only with the native readings, so the fixture tests (UNLAW_SYS_NATIVE=0) always read
# their fake tools.

_MEMO: dict[str, tuple[float, object]] = {}
_CACHE_LOCK = threading.Lock()


def cache_file() -> Path | None:
    root = os.environ.get("UNLAW_STORAGE")
    if not root or native() is None:
        return None
    runtime = Path(root) / "runtime"
    # sys-cache.json of earlier 4.0.0 builds held the serial number and hardware UUIDs
    # (world-readable): removed, never read again.
    try:
        (runtime / "sys-cache.json").unlink()
    except OSError:
        pass
    return runtime / "sys-cache-2.json"


# Keys of sys-cache-2.json; anything else found there is dropped on the next write.
CACHE_KEYS = {"hardware_names", "core_kinds", "power"}


def cached(key: str, make: Callable[[], object], ttl: float | None = None) -> object:
    """make() through the cache; ttl None = for this boot. A failed reading (None) is not kept."""
    if native() is None:
        return make()
    now = time.time()
    with _CACHE_LOCK:
        hit = _MEMO.get(key)
        if hit is not None and (ttl is None or now - hit[0] < ttl):
            return hit[1]
        path = cache_file()
        boot = boot_time() if path is not None else None
        stored: dict = {}
        if path is not None and boot is not None:
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                stored = loaded if isinstance(loaded, dict) and loaded.get("boot") == boot else {}
            except (OSError, ValueError):
                stored = {}
            entry = stored.get(key)
            if isinstance(entry, dict) and isinstance(entry.get("time"), (int, float)) and "value" in entry:
                if ttl is None or 0 <= now - entry["time"] < ttl:
                    _MEMO[key] = (entry["time"], entry["value"])
                    return entry["value"]
    value = make()
    if value is None:
        return None
    with _CACHE_LOCK:
        _MEMO[key] = (now, value)
        if path is not None and boot is not None:
            # Read again: another thread may have stored its key while make() ran.
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                stored = loaded if isinstance(loaded, dict) and loaded.get("boot") == boot else {}
            except (OSError, ValueError):
                stored = {}
            # Only current keys are kept (an older build cached the whole hardware answer).
            stored = {name: entry for name, entry in stored.items() if name in CACHE_KEYS}
            stored = {**stored, "boot": boot, key: {"time": now, "value": value}}
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}")
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(stored))
                os.replace(temporary, path)
            except OSError:
                pass
    return value


# In --watch mode each reading of the tick, network and disk counters is kept, so the
# next round measures from it instead of sleeping SAMPLE and reading twice.
_LAST: dict[str, tuple[float, object]] = {}
_KEEP = False


def previous(key: str) -> tuple[float, object] | None:
    return _LAST.get(key) if _KEEP else None


def remember(key: str, value: object) -> None:
    if _KEEP:
        _LAST[key] = (time.monotonic(), value)


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


STRING_SYSCTLS = ("hw.model", "machdep.cpu.brand_string")


def sysctl_text(key: str) -> str | None:
    if key in STRING_SYSCTLS:
        text = native_text(key)
        if text:
            return text
    text = tool_text(["sysctl", "-n", key])
    return text.strip() if text and text.strip() else None


def sysctl_int(key: str) -> int | None:
    value = native_int(key)
    if value is not None:
        return value
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


def parse_cluster_types(raw: bytes) -> list[str] | None:
    """"P"/"E" per logical CPU, from the CPU nodes of the IOKit device tree (`ioreg -rlc IOPlatformDevice -k cluster-type -a`)."""
    try:
        nodes = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ExpatError, ValueError, OverflowError):
        return None
    kinds: dict[int, str] = {}
    for node in nodes if isinstance(nodes, list) else []:
        kind, number = (node.get("cluster-type"), node.get("logical-cpu-id")) if isinstance(node, dict) else (None, None)
        if isinstance(kind, bytes):
            kind = kind.rstrip(b"\0").decode("ascii", "replace")
        if isinstance(number, bytes):
            number = int.from_bytes(number, "little")
        if kind in ("P", "E") and isinstance(number, int) and not isinstance(number, bool):
            kinds[number] = kind
    if not kinds or sorted(kinds) != list(range(len(kinds))):
        return None
    return [kinds[number] for number in range(len(kinds))]


def parse_netstat(text: str) -> dict[str, tuple[int, int]]:
    """Bytes in and out per physical interface from `netstat -ibn` (the <Link#> row has the interface totals)."""
    counters: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 10 or not fields[2].startswith("<Link#"):
            continue
        name = fields[0].rstrip("*")
        if name.startswith(VIRTUAL_INTERFACES):
            continue
        numbers = [field for field in fields[3:] if re.fullmatch(r"\d+|-", field)]
        # Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll; the address column is missing for some interfaces.
        if len(numbers) >= 6 and numbers[2].isdigit() and numbers[5].isdigit():
            counters[name] = (int(numbers[2]), int(numbers[5]))
    return counters


def parse_block_stats(raw: bytes) -> tuple[int, int, int, int] | None:
    """(bytes read, bytes written, reads, writes) summed over every disk driver in `ioreg -r -c IOBlockStorageDriver -a`."""
    try:
        drivers = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ExpatError, ValueError, OverflowError):
        return None
    totals = [0, 0, 0, 0]
    found = False
    for driver in drivers if isinstance(drivers, list) else []:
        stats = driver.get("Statistics") if isinstance(driver, dict) else None
        if not isinstance(stats, dict):
            continue
        found = True
        for index, key in enumerate(("Bytes (Read)", "Bytes (Write)", "Operations (Read)", "Operations (Write)")):
            value = stats.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[index] += value
    return (totals[0], totals[1], totals[2], totals[3]) if found else None


def per_second(before: Sequence[int], after: Sequence[int], seconds: float) -> list[float]:
    """Rates between two counter readings; a counter that went down (a reset, a disk unplugged) counts as 0."""
    return [max(b - a, 0) / seconds if seconds > 0 else 0.0 for a, b in zip(before, after)]


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


def parse_swap(text: str | tuple[int, int] | None) -> tuple[int, int] | None:
    """(total, used) bytes from `sysctl vm.swapusage` (or already read natively)."""
    if text is None or isinstance(text, tuple):
        return text
    match = re.search(r"total = ([\d.]+)([KMGT]).*?used = ([\d.]+)([KMGT])", text)
    if match is None:
        return None
    total = round(float(match.group(1)) * UNITS[match.group(2)])
    used = round(float(match.group(3)) * UNITS[match.group(4)])
    return total, used


def memory_info(
    vm: dict,
    total_bytes: int,
    swap_text: str | tuple[int, int] | None,
    pressure_level: int | None,
    available_percent: int | None = None,
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
        # kern.memorystatus_level: the share of memory macOS considers available; Activity Monitor's
        # memory pressure graph is 100 minus it.
        "available_percent": available_percent,
        "pressure_percent": 100 - available_percent if available_percent is not None else None,
        "pageouts": vm.get("Pageouts"),
        "swapouts": vm.get("Swapouts"),
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
                    "device": printable(match.group("device")),
                    "mount": printable(match.group("mount")),
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
                    "name": printable(match.group(4).rsplit("/", 1)[-1]),
                    "cpu_percent": float(match.group(2)),
                    "memory_bytes": int(match.group(3)) * 1024,
                }
            )
    return rows


def top_processes(rows: list[dict], by: str, count: int) -> list[dict]:
    key = "cpu_percent" if by == "cpu" else "memory_bytes"
    return sorted(rows, key=lambda row: (-row[key], row["pid"]))[:count]


def printable(text: str) -> str:
    """Process and volume names are chosen by whoever started or mounted them: no escape codes."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)


def parse_gpu(text: str) -> dict | None:
    usage = re.search(r'"Device Utilization %"\s*=\s*(\d+)', text)
    if usage is None:
        return None
    cores = re.search(r'"gpu-core-count"\s*=\s*(\d+)', text)
    name = re.search(r'"model"\s*=\s*"([^"]*)"', text)

    def number(key: str) -> int | None:
        found = re.search(r'"' + re.escape(key) + r'"\s*=\s*(\d+)', text)
        return int(found.group(1)) if found else None

    return {
        "usage_percent": int(usage.group(1)),
        "renderer_percent": number("Renderer Utilization %"),
        "tiler_percent": number("Tiler Utilization %"),
        # Unified memory the GPU driver holds right now (Apple silicon shares RAM with the CPU).
        "memory_in_use_bytes": number("In use system memory"),
        "cores": int(cores.group(1)) if cores else None,
        "name": printable(name.group(1)) if name else None,
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
    telemetry = data.get("PowerTelemetryData") if isinstance(data.get("PowerTelemetryData"), dict) else {}
    adapter = data.get("AdapterDetails") if isinstance(data.get("AdapterDetails"), dict) else {}

    def milli(source: dict, name: str) -> float | None:
        value = source.get(name)
        return round(value / 1000, 2) if isinstance(value, int) and not isinstance(value, bool) else None

    # What the whole Mac draws right now (the power manager's own telemetry, in mW).
    system_power = milli(telemetry, "SystemPowerIn") if plugged else None
    if not system_power:
        system_power = milli(telemetry, "SystemLoad")
    battery_power = milli(telemetry, "BatteryPower")
    if battery_power is None:
        battery_power = milli(detail, "BatteryPower")
    adapter_watts = adapter.get("Watts")
    voltage = number("Voltage")
    amperage = number("Amperage", "InstantAmperage")
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
        "system_power_watts": system_power if system_power else None,
        # Negative while the battery is giving power, positive while it charges.
        "battery_power_watts": battery_power,
        "adapter_watts": adapter_watts if isinstance(adapter_watts, int) and not isinstance(adapter_watts, bool) and plugged else None,
        "voltage_v": round(voltage / 1000, 2) if voltage is not None else None,
        "amperage_ma": amperage,
    }


# ---------------------------------------------------------------- collectors


def read_hardware() -> dict | None:
    text = tool_text(["system_profiler", "SPHardwareDataType", "-json"])
    try:
        hardware = json.loads(text or "")["SPHardwareDataType"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    if not isinstance(hardware, dict):
        return None
    # Only what is shown: the full answer holds the serial number and hardware UUIDs, which must
    # never land in a cache file (storage.root may be synced).
    return {key: hardware[key] for key in HARDWARE_KEYS if isinstance(hardware.get(key), str)}


HARDWARE_KEYS = ("machine_name", "machine_model", "chip_type")


def without_serials(text: str | None) -> str | None:
    """system_profiler JSON without serial numbers (the battery's): it goes into the cache file."""
    try:
        data = json.loads(text or "")
    except ValueError:
        return None

    def scrub(value: object) -> object:
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items() if "serial" not in key.lower()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return json.dumps(scrub(data))


def collect_system(now: float) -> dict:
    hardware = cached("hardware_names", read_hardware)
    if not isinstance(hardware, dict):
        hardware = {}
    version = platform.mac_ver()[0] if native() is not None else None
    if not version:
        version = tool_text(["sw_vers", "-productVersion"])
    boot = boot_time()
    return {
        "thermal": thermal_state(),
        "model": hardware.get("machine_name"),
        "identifier": hardware.get("machine_model") or sysctl_text("hw.model"),
        "chip": hardware.get("chip_type") or sysctl_text("machdep.cpu.brand_string"),
        "os": f"macOS {version.strip()}" if version and version.strip() else None,
        "uptime_seconds": uptime_seconds(boot, now) if boot is not None else None,
    }


def read_core_kinds() -> list[str] | None:
    raw = run_tool(["ioreg", "-rlc", "IOPlatformDevice", "-k", "cluster-type", "-a"])
    return parse_cluster_types(raw) if raw else None


def core_kinds() -> list[str] | None:
    kinds = cached("core_kinds", read_core_kinds)
    return kinds if isinstance(kinds, list) else None


def native_cpu() -> dict | None:
    """Busy share per core over SAMPLE seconds, from the kernel's tick counters (what Activity Monitor reads)."""
    last = previous("cpu")
    if last is not None:
        before = last[1]
    else:
        before = cpu_ticks()
        if before is None:
            return None
        time.sleep(SAMPLE)
    after = cpu_ticks()
    if after is None or len(after) != len(before):  # type: ignore[arg-type]
        return None
    remember("cpu", after)
    cores = core_usage(before, after)
    ticks = sum(core["ticks"] for core in cores) or 1
    user = sum(core["user"] * core["ticks"] for core in cores) / ticks
    system = sum(core["system"] * core["ticks"] for core in cores) / ticks
    load = os.getloadavg()
    return {
        "user": user,
        "system": system,
        "idle": max(100 - user - system, 0.0),
        "load": [round(value, 2) for value in load],
        "cores": [core["busy"] for core in cores],
    }


def collect_cpu() -> dict | None:
    parsed = native_cpu()
    if parsed is None:
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
    per_core = None
    by_kind: dict[str, float | None] = {"P": None, "E": None}
    if parsed.get("cores"):
        kinds = core_kinds()
        if kinds is None or len(kinds) != len(parsed["cores"]):
            kinds = [""] * len(parsed["cores"])
        per_core = [{"kind": kind or None, "usage_percent": round(busy, 1)} for kind, busy in zip(kinds, parsed["cores"])]
        for kind in by_kind:
            shares = [busy for core_kind, busy in zip(kinds, parsed["cores"]) if core_kind == kind]
            by_kind[kind] = round(sum(shares) / len(shares), 1) if shares else None
    return {
        "usage_percent": round(usage, 1),
        "user_percent": round(parsed["user"], 1),
        "system_percent": round(parsed["system"], 1),
        "idle_percent": round(parsed["idle"], 1),
        "cores": {"total": total, "performance": performance, "efficiency": efficiency},
        "load_average": parsed["load"],
        "per_core": per_core,
        "performance_percent": by_kind["P"],
        "efficiency_percent": by_kind["E"],
    }


def collect_gpu() -> dict | None:
    text = tool_text(["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"])
    return parse_gpu(text) if text else None


def collect_memory() -> dict | None:
    vm = native_vm()
    if vm is None:
        vm_text = tool_text(["vm_stat"])
        vm = parse_vm_stat(vm_text) if vm_text else None
    total = sysctl_int("hw.memsize")
    if vm is None or total is None:
        return None
    swap: str | tuple[int, int] | None = native_swap()
    if swap is None:
        swap = tool_text(["sysctl", "vm.swapusage"]) or ""
    return memory_info(
        vm,
        total,
        swap,
        sysctl_int("kern.memorystatus_vm_pressure_level"),
        native_int("kern.memorystatus_level"),
    )


def collect_network() -> dict | None:
    """Download and upload speed over SAMPLE seconds (or since the last round of --watch), summed over the physical interfaces."""
    last = previous("network")
    if last is not None:
        started, before = last[0], last[1]
    else:
        first = tool_text(["netstat", "-ibn"])
        if first is None:
            return None
        started, before = time.monotonic(), parse_netstat(first)
        time.sleep(SAMPLE)
    second = tool_text(["netstat", "-ibn"])
    elapsed = time.monotonic() - started
    after = parse_netstat(second or "")
    if after:
        remember("network", after)
    names = sorted(set(before) & set(after))
    if not names:
        return None
    down = up = 0.0
    active = []
    for name in names:
        rates = per_second(before[name], after[name], elapsed)
        down, up = down + rates[0], up + rates[1]
        if after[name][0] or after[name][1]:
            active.append(name)
    return {
        "download_bytes_per_sec": round(down),
        "upload_bytes_per_sec": round(up),
        "received_bytes": sum(after[name][0] for name in names),
        "sent_bytes": sum(after[name][1] for name in names),
        "interfaces": active,
    }


def collect_io() -> dict | None:
    """Disk reads and writes over SAMPLE seconds, from the block storage drivers' own counters."""
    command = ["ioreg", "-r", "-c", "IOBlockStorageDriver", "-a"]
    last = previous("io")
    if last is not None:
        started, before = last[0], last[1]
    else:
        first = run_tool(command)
        before = parse_block_stats(first) if first else None
        if before is None:
            return None
        started = time.monotonic()
        time.sleep(SAMPLE)
    second = run_tool(command)
    after = parse_block_stats(second) if second else None
    if after is None:
        return None
    remember("io", after)
    read, write, reads, writes = per_second(before, after, time.monotonic() - started)  # type: ignore[arg-type]
    return {
        "read_bytes_per_sec": round(read),
        "write_bytes_per_sec": round(write),
        "read_ops_per_sec": round(reads),
        "write_ops_per_sec": round(writes),
        "read_bytes": after[0],
        "written_bytes": after[1],
    }


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
    profiler = cached(
        "power",
        lambda: without_serials(tool_text(["system_profiler", "SPPowerDataType", "-json"])),
        POWER_CACHE_SECONDS,
    )
    return parse_battery(raw, profiler if isinstance(profiler, str) else None)


def collect_top() -> dict | None:
    text = tool_text(["ps", "-Ao", "pid,pcpu,rss,comm"])
    rows = parse_ps(text) if text else []
    if not rows:
        return None
    return {
        "cpu": top_processes(rows, "cpu", TOP_COUNT),
        "memory": top_processes(rows, "memory", TOP_COUNT),
        "processes": len(rows),
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
        "network": collect_network,
        "io": collect_io,
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
    thermal = system.get("thermal")
    if thermal and thermal != "nominal":
        parts.append(style.paint("33" if thermal == "fair" else "31", f"thermal {thermal}"))
    return ["  ".join(parts)]


LEVELS = "▁▂▃▄▅▆▇█"


def sparkline(values: Sequence[float]) -> str:
    """One block character per value, 0-100."""
    return "".join(LEVELS[min(max(round(value / 100 * 7), 0), 7)] for value in values)


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
    lines = [
        row(
            style,
            "CPU",
            body + "  " + style.dim("  ".join(part for part in details if part)),
        )
    ]
    per_core = cpu.get("per_core")
    if per_core:
        groups = []
        for kind, name in (("P", "performance"), ("E", "efficiency")):
            shares = [core["usage_percent"] for core in per_core if core["kind"] == kind]
            if shares:
                groups.append(f"{sparkline(shares)} {name} {cpu[name + '_percent']:.0f}%")
        if not groups:
            groups.append(sparkline([core["usage_percent"] for core in per_core]))
        lines.append(row(style, "Cores", "   ".join(groups)))
    return lines


def render_gpu(style: Style, gpu: dict | None) -> list[str]:
    if not gpu:
        return [row(style, "GPU", "n/a")]
    memory = gpu.get("memory_in_use_bytes")
    detail = " ".join(
        part
        for part in (
            gpu["name"],
            f"{gpu['cores']} cores" if gpu["cores"] else None,
            f"memory {human_bytes(memory, True)}" if memory else None,
        )
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
        f"pressure {memory['pressure'] or 'n/a'}"
        + (f" ({memory['pressure_percent']}%)" if memory.get("pressure_percent") is not None else ""),
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


def rate(count: float) -> str:
    return human_bytes(count) + "/s"


def render_network(style: Style, network: dict | None) -> list[str]:
    if not network:
        return [row(style, "Network", "n/a")]
    names = ", ".join(network["interfaces"]) or "no traffic"
    body = f"↓ {rate(network['download_bytes_per_sec']):>10}   ↑ {rate(network['upload_bytes_per_sec']):>10}"
    total = f"{names}  received {human_bytes(network['received_bytes'])}  sent {human_bytes(network['sent_bytes'])}"
    return [row(style, "Network", body + "  " + style.dim(total))]


def render_io(style: Style, io: dict | None) -> list[str]:
    if not io:
        return [row(style, "Disk I/O", "n/a")]
    body = f"read {rate(io['read_bytes_per_sec']):>10}   write {rate(io['write_bytes_per_sec']):>10}"
    ops = f"{io['read_ops_per_sec']} reads/s  {io['write_ops_per_sec']} writes/s"
    return [row(style, "Disk I/O", body + "  " + style.dim(ops))]


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
    if battery.get("system_power_watts"):
        details.append(f"Mac draws {battery['system_power_watts']:.1f} W")
    if battery.get("adapter_watts"):
        details.append(f"{battery['adapter_watts']} W adapter")
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
    "network": render_network,
    "io": render_io,
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


def parse_args(args: Sequence[str]) -> tuple[tuple[str, ...] | None, bool, float | None]:
    """(sections, json, watch interval); sections None means everything. Several sections may be named."""
    sections: list[str] = []
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
            if SECTION_NAMES[arg] not in sections:
                sections.append(SECTION_NAMES[arg])
        else:
            raise UsageError(f"unknown section {arg!r}")
    return (tuple(sections) or None), as_json, interval


def watch(sections: Sequence[str], as_json: bool, interval: float) -> int:
    """Redraw in place until Ctrl+C. JSON mode prints one object per line instead of redrawing.
    Each round measures CPU, network and disks from the round before (`previous`), so after
    the first one nothing sleeps and every counter is read once."""
    global _KEEP
    _KEEP = True
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
    except BrokenPipeError:
        # The reader went away (Unlaw.app left the System part): end quietly, and keep
        # Python's own flush at exit from reporting the same closed pipe.
        os.dup2(os.open(os.devnull, os.O_WRONLY), out.fileno())
        return 0
    finally:
        if redraw:
            out.write("\x1b[?25h\n")
            out.flush()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "help" or any(arg in {"-h", "--help"} for arg in args):
        print(COMMAND_HELP, end="")
        return 0
    try:
        chosen, as_json, interval = parse_args(args)
    except UsageError as error:
        print(f"ul sys: {error}\n{USAGE}", file=sys.stderr)
        return 2
    sections = SECTIONS if chosen is None else chosen
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
