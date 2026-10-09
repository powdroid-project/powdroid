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


def _run(args, serial=None, timeout=30):
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, errors="replace"
        )
    except FileNotFoundError:
        raise AdbError("adb not found in PATH") from None
    except subprocess.TimeoutExpired:
        raise AdbError(f"'{' '.join(cmd)}' timed out after {timeout}s") from None
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
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


def device_time_ms(serial):
    """Current device wall-clock time in ms, used to correct host/device clock skew."""
    out = _run(["shell", "date", "+%s%N"], serial=serial).strip()
    if out.isdigit() and len(out) > 13:  # nanoseconds supported
        return int(out) // 1_000_000
    return int(out[:10]) * 1000 + 500  # seconds only: centre the rounding error


def bugreport(serial, path, timeout=900):
    _run(["bugreport", str(path)], serial=serial, timeout=timeout)
