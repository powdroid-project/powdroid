"""Thin wrapper around the adb command-line tool."""

import shutil
import subprocess
import time
from dataclasses import dataclass

from core import PowDroidError


class AdbError(PowDroidError):
    """Raised when an adb command fails or adb is missing."""


@dataclass
class Device:
    serial: str
    state: str  # "device", "unauthorized", "offline", ...
    manufacturer: str = ""
    model: str = ""
    android_version: str = ""

    @property
    def ready(self):
        return self.state == "device"

    @property
    def label(self):
        name = f"{self.manufacturer} {self.model}".strip()
        return name or self.serial


def is_available():
    return shutil.which("adb") is not None


def _run(args, serial=None, timeout=30, stdout=subprocess.PIPE):
    """Run an adb command and return its output (unless stdout is redirected, e.g. to a file)."""
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    try:
        result = subprocess.run(cmd, stdout=stdout, stderr=subprocess.PIPE, timeout=timeout,
                                text=True, errors="replace")
    except FileNotFoundError:
        raise AdbError("adb not found in PATH") from None
    except subprocess.TimeoutExpired:
        raise AdbError(f"'{' '.join(cmd)}' timed out after {timeout}s") from None
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise AdbError(f"'{' '.join(cmd)}' failed: {message}")
    return result.stdout


def start_server():
    _run(["start-server"])


def list_devices():
    """Return every device adb knows about, including unauthorized ones."""
    devices = []
    for line in _run(["devices"]).splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append(Device(serial=parts[0], state=parts[1]))
    return devices


def find_device(serial=None, devices=None):
    """Return the requested device (or the first one), with its properties filled in if ready.

    `devices` can be passed to reuse an `adb devices` listing the caller already has.
    """
    if devices is None:
        devices = list_devices()
    if serial:
        devices = [d for d in devices if d.serial == serial]
    if not devices:
        return None
    device = next((d for d in devices if d.ready), devices[0])
    if device.ready:
        props = _run(
            ["shell", "getprop ro.product.manufacturer; getprop ro.product.model;"
             " getprop ro.build.version.release"],
            serial=device.serial,
        ).splitlines() + ["", "", ""]
        device.manufacturer, device.model, device.android_version = (
            p.strip() for p in props[:3]
        )
    return device


def wait_for(connected, serial=None):
    """Block until the device is (dis)connected."""
    while True:
        try:
            if any(d.ready and serial in (None, d.serial) for d in list_devices()) == connected:
                return
        except AdbError:
            pass
        time.sleep(1)


def prepare(serial):
    """Reset battery statistics so the history only covers the coming session."""
    _run(["shell", "am", "kill-all"], serial=serial)
    _run(["shell", "dumpsys", "batterystats", "--reset"], serial=serial)
    _run(["shell", "dumpsys", "batterystats", "--enable", "full-wake-history"], serial=serial)


def clock_offset_ms(serial):
    """Device clock minus host clock, in ms, compensating for the adb round trip.

    Uses nanosecond `date` output when the device supports it. Otherwise `date +%s` only
    has 1 s resolution, so the moment its value ticks over is timed instead.
    """
    def sample(fmt):
        before = time.time()
        out = _run(["shell", "date", fmt], serial=serial).strip()
        return out, (before + time.time()) / 2 * 1000  # host time at the middle of the call

    out, host_ms = sample("+%s%N")
    if out.isdigit() and len(out) > 13:
        return round(int(out) / 1_000_000 - host_ms)
    previous = out[:10]  # the seconds, followed by an unsupported "%N"
    deadline = time.time() + 2.5
    while time.time() < deadline:
        out, host_ms = sample("+%s")
        if out != previous and out.isdigit():
            return round(int(out) * 1000 - host_ms)
        previous = out
    return round(int(out) * 1000 + 500 - host_ms)  # adb too slow to see the tick: ±0.5 s


def dump_batterystats(serial, path, timeout=300):
    """Save the checkin-format battery statistics (including history since the last reset).

    `-c` prints the checkin format with the history; unlike `--checkin` it neither commits
    nor resets the statistics. exec-out keeps the output byte-exact (no CRLF translation).
    """
    with open(path, "wb") as out:
        _run(["exec-out", "dumpsys", "batterystats", "-c"], serial=serial, timeout=timeout, stdout=out)
