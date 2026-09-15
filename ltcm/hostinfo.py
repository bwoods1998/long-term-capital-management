"""Where the floor is running: a Sailbox, or the owner's machine.

`describe_host()` answers the one question the ops stream, the health file and the operator CLI
all want: is this process on the cloud box, and which one? It is deliberately incurious -- it
reads a handful of environment variables and three files under `/proc`, never opens a socket,
never touches a credential and never raises. On anything that is not a Sailbox it degrades to a
truthful local description rather than guessing.

The Sailbox markers come from the guest environment Sail sets on every command it runs. The SDK
reference calls them "reserved variables that identify the Sailbox (such as `SAILBOX_ID`)", set
alongside the `IS_SANDBOX=1` sandbox marker, and says a caller's own `env` cannot override them
(https://docs.sailresearch.com/sailbox-sdk). `SAIL_APP` names the app a Sailbox belongs to
(https://docs.sailresearch.com/harbor). Anything Sail does not set is simply left out of the
result: a key that is absent is never invented.

Every source of truth is injectable, so the tests describe a box and a laptop without either.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import time
from pathlib import Path
from typing import Any, Callable, Mapping

#: Environment variables that identify a Sailbox, most specific first.
BOX_ID_VARS = ("SAILBOX_ID", "SAIL_SAILBOX_ID")
APP_VARS = ("SAIL_APP", "SAILBOX_APP", "SAIL_APP_NAME")
REGION_VARS = ("SAIL_REGION", "SAILBOX_REGION", "FLY_REGION")
#: Set to `1` inside any Sail sandbox, including one whose id variable is missing.
SANDBOX_VARS = ("IS_SANDBOX",)

_PROC_UPTIME = "/proc/uptime"
_BOOT_ID = "/proc/sys/kernel/random/boot_id"
_MEMINFO = "/proc/meminfo"

#: `describe_host` never returns a value longer than this, whatever the environment holds.
MAX_VALUE = 200


def _text(path: str, reader: Callable[[str], str] | None = None) -> str:
    """Read a small file, or return empty. Never raises, never follows anything surprising."""
    try:
        if reader is not None:
            return reader(path)
        return Path(path).read_text(encoding="utf-8", errors="replace")[:65536]
    except Exception:
        return ""


def _clean(value: Any) -> str | None:
    """A short, printable scalar, or None. Nothing from the environment is trusted to be either."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > MAX_VALUE or any(ord(c) < 32 for c in value):
        return None
    return value


def _first(env: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = _clean(env.get(name))
        if value:
            return value
    return None


def uptime_seconds(reader: Callable[[str], str] | None = None) -> float | None:
    """Seconds since this kernel booted, from `/proc/uptime`. None where there is no `/proc`."""
    raw = _text(_PROC_UPTIME, reader).split()
    if not raw:
        return None
    try:
        return round(float(raw[0]), 3)
    except ValueError:
        return None


def memory_bytes(reader: Callable[[str], str] | None = None) -> dict[str, int]:
    """Total and available memory from `/proc/meminfo`, in bytes. Empty where it is unreadable."""
    wanted = {"MemTotal": "memory_total_bytes", "MemAvailable": "memory_available_bytes"}
    out: dict[str, int] = {}
    for line in _text(_MEMINFO, reader).splitlines():
        key, _, rest = line.partition(":")
        if key in wanted:
            parts = rest.split()
            if parts and parts[0].isdigit():
                out[wanted[key]] = int(parts[0]) * 1024
    return out


def describe_host(
    env: Mapping[str, str] | None = None,
    *,
    reader: Callable[[str], str] | None = None,
    clock: Callable[[], float] = time.time,
    disk_usage: Callable[[str], Any] | None = None,
    hostname: Callable[[], str] | None = None,
    root: str | Path = "/",
) -> dict[str, Any]:
    """Describe the machine this process is on.

    Always returns a dict with at least `host` (`"sailbox"` or `"local"`), `uptime_seconds` and
    `checked_at`. `box_id`, `app`, `region` and the resource keys appear only when they are known.
    """
    env = os.environ if env is None else env
    report: dict[str, Any] = {"host": "local", "checked_at": _iso(clock)}

    box = _first(env, BOX_ID_VARS)
    app = _first(env, APP_VARS)
    region = _first(env, REGION_VARS)
    sandbox = _first(env, SANDBOX_VARS) in ("1", "true", "yes")
    markers = [name for name in BOX_ID_VARS + SANDBOX_VARS if _clean(env.get(name))]

    if box:
        report.update(host="sailbox", box_id=box, detected_via=markers[0])
    elif sandbox:
        # A Sail sandbox that did not hand us an id: honest about the box, silent about which.
        report.update(host="sailbox", detected_via="IS_SANDBOX")
    if app:
        report["app"] = app
    if region:
        report["region"] = region
    report["sandbox"] = sandbox

    report["uptime_seconds"] = uptime_seconds(reader)
    boot = _clean(_text(_BOOT_ID, reader).strip())
    if boot:
        report["boot_id"] = boot
    report.update(memory_bytes(reader))

    usage = disk_usage or shutil.disk_usage
    try:
        total, _used, free = usage(str(root))
        report["disk_total_bytes"], report["disk_free_bytes"] = int(total), int(free)
    except Exception:
        pass

    try:
        report["hostname"] = _clean((hostname or socket.gethostname)()) or "unknown"
    except Exception:
        report["hostname"] = "unknown"
    report["platform"] = f"{platform.system().lower()}-{platform.machine()}"[:MAX_VALUE]
    report["python"] = platform.python_version()
    report["pid"] = os.getpid()
    try:
        report["cpu_count"] = os.cpu_count()
    except Exception:
        report["cpu_count"] = None
    return report


def _iso(clock: Callable[[], float]) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(clock())))
    except Exception:  # pragma: no cover - a clock that will not tick
        return "1970-01-01T00:00:00Z"


def on_sailbox(env: Mapping[str, str] | None = None) -> bool:
    """True when this process is on a Sailbox. The cheap form of `describe_host`."""
    env = os.environ if env is None else env
    return bool(_first(env, BOX_ID_VARS)) or _first(env, SANDBOX_VARS) in ("1", "true", "yes")
