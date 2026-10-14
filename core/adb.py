"""Thin wrapper around the adb command-line tool."""

import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass

from core import PowDroidError, debug

logger = logging.getLogger("powdroid.adb")

# Device properties written to the debug log: they identify the phone and its software.
DEBUG_PROPS = ("ro.product.brand", "ro.product.manufacturer", "ro.product.model", "ro.product.device",
               "ro.hardware", "ro.build.version.release", "ro.build.version.sdk",
               "ro.build.version.security_patch", "ro.build.fingerprint", "persist.sys.timezone")


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


def _run(args, serial=None, timeout=30, stdout=subprocess.PIPE, poll=False):
    """Run an adb command and return its output (unless stdout is redirected, e.g. to a file).

    poll marks the commands repeated every second to watch the device: the debug log only
    shows them when their answer changes.
    """
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    if not poll and logger.isEnabledFor(logging.DEBUG):
        logger.debug("Running %s", shlex.join(cmd))
    started = time.monotonic()
    try:
        result = subprocess.run(cmd, stdout=stdout, stderr=subprocess.PIPE, timeout=timeout,
                                text=True, errors="replace")
    except FileNotFoundError:
        _log_answer(cmd, poll, "adb not found in PATH")
        raise AdbError("adb not found in PATH") from None
    except subprocess.TimeoutExpired as e:
        _log_answer(cmd, poll, f"timed out after {timeout} s", e.stdout, e.stderr)
        raise AdbError(f"'{' '.join(cmd)}' timed out after {timeout}s") from None
    except OSError as e:
        _log_answer(cmd, poll, f"could not be started: {e!r}")
        raise
    _log_answer(cmd, poll, f"exit code {result.returncode}", result.stdout, result.stderr,
                time.monotonic() - started)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise AdbError(f"'{' '.join(cmd)}' failed: {message}")
    return result.stdout


_polled = {}  # polled command -> [its last answer, how many times it was repeated since]


def _log_answer(cmd, poll, status, out=None, err=None, seconds=None):
    """Write an adb command and its answer to the debug log (polled ones only when it changes)."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    command = shlex.join(cmd)
    answer, note = (status, out, err), ""
    if poll:
        last = _polled.setdefault(command, [None, 0])
        if last[0] == answer:
            last[1] += 1
            return
        if last[1]:
            note = f" (the previous answer came {last[1] + 1} times)"
        last[:] = [answer, 0]
    lines = [f"{command}: {status}" + (f" in {seconds:.2f} s" if seconds is not None else "") + note]
    lines += [debug.indent(name, text) for name, text in (("stdout", out), ("stderr", err)) if text]
    logger.debug("\n".join(lines))


def version():
    return _run(["version"])


def start_server():
    _run(["start-server"])


def list_devices(poll=False):
    """Return every device adb knows about, including unauthorized ones."""
    devices = []
    for line in _run(["devices"], poll=poll).splitlines()[1:]:
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
        logger.info("No device found%s", f" with serial {serial}" if serial else "")
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
    logger.info("Device: %s", device)
    return device


def wait_for(connected, serial=None):
    """Block until the device is (dis)connected."""
    while True:
        try:
            if any(d.ready and serial in (None, d.serial) for d in list_devices(poll=True)) == connected:
                logger.info("Device %s%s", "connected" if connected else "disconnected",
                            f" ({serial})" if serial else "")
                return
        except AdbError:
            pass  # in the debug log
        time.sleep(1)


def log_diagnostics(serial, moment, battery=True):
    """In debug mode, log the device details that explain device-specific problems.

    battery=False leaves out `dumpsys battery`, when the caller reads it anyway. They never
    stop the session: failures are only logged.
    """
    if not logger.isEnabledFor(logging.DEBUG):
        return
    logger.info("Device diagnostics, %s", moment)
    props = f"for p in {' '.join(DEBUG_PROPS)}; do echo $p=$(getprop $p); done"
    commands = [["shell", props]] + ([["shell", "dumpsys", "battery"]] if battery else [])
    for args in commands:
        try:
            _run(args, serial=serial)
        except AdbError:
            pass  # in the log


def has_coulomb_counter(serial):
    """Whether the battery reports its coulomb counter, according to `dumpsys battery`.

    Phones without one report a charge counter of 0. Returns None when unknown (older
    Android versions do not show it, or the command failed).
    """
    try:
        out = _run(["shell", "dumpsys", "battery"], serial=serial)
    except AdbError:
        return None  # in the debug log
    m = re.search(r"^\s*Charge counter:\s*(-?\d+)", out, re.MULTILINE)
    return None if m is None else int(m.group(1)) != 0


def prepare(serial):
    """Reset battery statistics so the history only covers the coming session.

    Returns has_coulomb_counter(serial): without the counter, the energy can only be
    estimated from the battery level, which needs a much longer session.
    """
    log_diagnostics(serial, "before the session", battery=False)  # read below in any case
    coulomb = has_coulomb_counter(serial)
    if coulomb is False:
        logger.warning("The battery reports no coulomb counter (charge counter 0)")
    _run(["shell", "am", "kill-all"], serial=serial)
    _run(["shell", "dumpsys", "batterystats", "--reset"], serial=serial)
    _run(["shell", "dumpsys", "batterystats", "--enable", "full-wake-history"], serial=serial)
    return coulomb


def clock_offset_ms(serial):
    """Device clock minus host clock, in ms, compensating for the adb round trip.

    Uses nanosecond `date` output when the device supports it. Otherwise `date +%s` only
    has 1 s resolution, so the moment its value ticks over is timed instead.
    """
    def sample(fmt, poll=False):
        before = time.time()
        out = _run(["shell", "date", fmt], serial=serial, poll=poll).strip()
        return out, (before + time.time()) / 2 * 1000  # host time at the middle of the call

    out, host_ms = sample("+%s%N")
    if out.isdigit() and len(out) > 13:
        offset = round(int(out) / 1_000_000 - host_ms)
        logger.info("Clock offset: %d ms (from the nanosecond date)", offset)
        return offset
    previous = out[:10]  # the seconds, followed by an unsupported "%N"
    deadline = time.time() + 2.5
    while time.time() < deadline:
        out, host_ms = sample("+%s", poll=True)  # logged when the second ticks over
        if out != previous and out.isdigit():
            offset = round(int(out) * 1000 - host_ms)
            logger.info("Clock offset: %d ms (when the device's seconds ticked over)", offset)
            return offset
        previous = out
    offset = round(int(out) * 1000 + 500 - host_ms)  # adb too slow to see the tick: ±0.5 s
    logger.info("Clock offset: %d ms (±0.5 s: adb was too slow to see the seconds tick over)", offset)
    return offset


def dump_batterystats(serial, path, timeout=300):
    """Save the checkin-format battery statistics (including history since the last reset).

    `-c` prints the checkin format with the history; unlike `--checkin` it neither commits
    nor resets the statistics. exec-out keeps the output byte-exact (no CRLF translation).
    """
    started = time.monotonic()
    with open(path, "wb") as out:
        _run(["exec-out", "dumpsys", "batterystats", "-c"], serial=serial, timeout=timeout, stdout=out)
    logger.info("Battery statistics transferred: %d bytes written to %s in %.1f s",
                os.path.getsize(path), path, time.monotonic() - started)
