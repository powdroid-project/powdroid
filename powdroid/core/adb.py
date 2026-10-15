"""Thin wrapper around the adb command-line tool."""

import logging
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from powdroid.core import PowDroidError, debug

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
    state: str  # "device", "unauthorized", "offline", "no permissions", ...
    manufacturer: str = ""
    model: str = ""
    android_version: str = ""

    @property
    def ready(self):
        return self.state == "device"

    @property
    def emulator(self):
        return self.serial.startswith("emulator-")

    @property
    def wireless(self):
        """Connected over Wi-Fi (adb connect, or paired with wireless debugging on Android 11+)."""
        return ":" in self.serial or "._adb-tls-connect._tcp" in self.serial

    @property
    def label(self):
        name = f"{self.manufacturer} {self.model}".strip()
        return name or self.serial


ADB_NAME = "adb.exe" if os.name == "nt" else "adb"
NOT_FOUND = ("adb not found: install the Android SDK platform tools, then add them to your PATH, set ANDROID_HOME "
             "to the SDK folder, or give the adb program with the ADB environment variable (CLI: --adb)")

_command = None  # how adb is started, once found (see command)


def sdk_folders():
    """The Android SDK folders that may hold platform-tools, in the order they are searched."""
    home = Path.home()
    folders = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
               home / "Library" / "Android" / "sdk",  # Android Studio on macOS
               home / "Android" / "Sdk"]  # Android Studio on Linux
    if os.environ.get("LOCALAPPDATA"):  # Android Studio on Windows
        folders.append(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk")
    return [Path(folder) for folder in folders if folder]


def _executable(path):
    return path.is_file() and os.access(path, os.X_OK)


def candidates():
    """Every adb program found, in the order they are tried: the PATH, then the Android SDK folders.

    Only absolute PATH entries are searched: unlike a shell on Windows, PowDroid never runs an
    adb.exe that happens to be in the current folder.
    """
    paths = [Path(d) / ADB_NAME for d in os.environ.get("PATH", "").split(os.pathsep) if d and os.path.isabs(d)]
    paths += [folder / "platform-tools" / ADB_NAME for folder in sdk_folders()]
    return [path for path in dict.fromkeys(paths) if _executable(path)]


def set_executable(path):
    """Use this adb program (CLI --adb) instead of looking for one."""
    global _command
    path = Path(path).expanduser().absolute()
    if not _executable(path):
        raise AdbError(f"{path} is not an adb program")
    _command = [str(path)]


def command():
    """The command line starting adb: [absolute path of adb]. Raises AdbError if adb is not found.

    The ADB environment variable names the program to use; otherwise the first of
    candidates() is used. The result is kept once found.
    """
    global _command
    if _command is None:
        if os.environ.get("ADB"):
            set_executable(os.environ["ADB"])
        else:
            found = candidates()
            if not found:
                raise AdbError(NOT_FOUND)
            _command = [str(found[0])]
            logger.info("Using %s", found[0])
    return _command


def _run(args, serial=None, timeout=30, stdout=subprocess.PIPE, poll=False, input=None):
    """Run an adb command and return its output (unless stdout is redirected, e.g. to a file).

    poll marks the commands repeated every second to watch the device: the debug log only
    shows them when their answer changes. input is text sent to the command's stdin.
    """
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)  # as logged and shown in errors
    if not poll and logger.isEnabledFor(logging.DEBUG):
        logger.debug("Running %s%s", shlex.join(cmd), "\n" + debug.indent("stdin", input) if input else "")
    started = time.monotonic()
    try:
        result = subprocess.run(command() + cmd[1:], input=input, stdout=stdout, stderr=subprocess.PIPE,
                                timeout=timeout, text=True, errors="replace")
    except FileNotFoundError:
        _log_answer(cmd, poll, f"{command()[-1]} not found")
        raise AdbError(f"{command()[-1]} not found: {NOT_FOUND}") from None
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


# Why a device that adb lists cannot be used yet, by its state, and what to do.
STATE_HINTS = {
    "unauthorized": "Accept the USB debugging prompt on your phone.",
    "no permissions": "No permission to use the device. On Linux, install the udev rules for Android devices "
                      "(e.g. the android-sdk-platform-tools-common package) and add your user to the plugdev "
                      "group, then plug the phone in again.",
    "offline": "The device is offline. Unplug and plug the phone in again; if it stays offline, revoke the USB "
               "debugging authorizations in the developer options, then accept the prompt again.",
}
MIN_PLATFORM_TOOLS = (29,)  # adb exec-out and shell stdin as PowDroid uses them, wait-for-disconnect


def version():
    return _run(["version"])


def platform_tools_version(text=None):
    """The platform-tools version of adb (e.g. (35, 0, 2)) from `adb version`, None if not shown."""
    m = re.search(r"^Version (\d+(?:\.\d+)*)", version() if text is None else text, re.MULTILINE)
    return tuple(int(n) for n in m.group(1).split(".")) if m else None


def start_server():
    _run(["start-server"])


def parse_devices(text):
    """The devices of an `adb devices` listing (its "List of devices attached" line is skipped)."""
    devices = []
    for line in text.splitlines():
        serial, tab, state = line.partition("\t")
        if tab and serial.strip():
            # e.g. "no permissions (user in plugdev group; are your udev rules wrong?); see [...]"
            state = "no permissions" if state.startswith("no permissions") else state.strip()
            devices.append(Device(serial=serial.strip(), state=state))
    return devices


def list_devices(poll=False):
    """Return every device adb knows about, including unauthorized ones."""
    return parse_devices(_run(["devices"], poll=poll))


def preferred(devices):
    """The device to use when none was chosen: a ready phone first, then a ready emulator, then any."""
    return min(devices, key=lambda d: (not d.ready, d.emulator), default=None)


def describe(device):
    """Fill in the manufacturer, model and Android version of a ready device (left empty if it fails)."""
    if device.ready:
        try:
            props = _run(["shell", "getprop ro.product.manufacturer; getprop ro.product.model;"
                                   " getprop ro.build.version.release"], serial=device.serial).splitlines()
        except AdbError:
            props = []  # e.g. disconnected meanwhile; in the debug log
        device.manufacturer, device.model, device.android_version = (p.strip() for p in (props + ["", "", ""])[:3])
    return device


def find_device(serial=None, devices=None):
    """Return the requested device (or the preferred one), with its properties filled in if ready.

    `devices` can be passed to reuse an `adb devices` listing the caller already has.
    """
    if devices is None:
        devices = list_devices()
    if serial:
        devices = [d for d in devices if d.serial == serial]
    if not devices:
        logger.info("No device found%s", f" with serial {serial}" if serial else "")
        return None
    device = describe(preferred(devices))
    logger.info("Device: %s", device)
    return device


class DeviceTracker:
    """Follows the device list with `adb track-devices`, which writes it again at every change.

    Iterating yields the [Device] list at each change (the first one at once), until close()
    is called from another thread or adb stops. Each list is sent as 4 hexadecimal digits
    giving its length, then the `adb devices` lines.
    """

    def __init__(self):
        cmd = command() + ["track-devices"]
        logger.debug("Running adb track-devices")
        self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL)

    def __iter__(self):
        stream = self.process.stdout
        while True:
            try:
                header = stream.read(4)
                size = int(header, 16)
                text = stream.read(size).decode("utf-8", "replace")
            except (ValueError, OSError) as e:  # closed, ended, or not the expected output
                logger.debug("adb track-devices stopped (%r)", e)
                return
            logger.debug("adb track-devices:\n%s", debug.indent("devices", text or "(none)"))
            yield parse_devices(text)

    def close(self):
        self.process.kill()
        self.process.wait()
        self.process.stdout.close()


def is_ready(serial=None, devices=None):
    """Whether adb lists the device (any device without a serial) as ready.

    `devices` can be passed to reuse an `adb devices` listing the caller already has.
    """
    return any(d.ready and serial in (None, d.serial) for d in (list_devices() if devices is None else devices))


def _wait_until(condition, interval=1.0):
    """Block until condition() is true; an AdbError (e.g. Wi-Fi briefly lost) counts as false."""
    while True:
        try:
            if condition():
                return
        except AdbError:
            pass  # in the debug log
        time.sleep(interval)


def wait_for(connected, serial=None):
    """Block until the device is (dis)connected."""
    _wait_until(lambda: is_ready(serial, list_devices(poll=True)) == connected)
    logger.info("Device %s%s", "connected" if connected else "disconnected", f" ({serial})" if serial else "")


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


@dataclass
class BatteryStatus:
    """What `dumpsys battery` says (None: not shown)."""

    plugged: bool = None  # powered by AC, USB, a wireless charger or a dock
    charge_counter_uah: int = None
    level_pct: int = None


def parse_battery(text):
    """The BatteryStatus of a `dumpsys battery` output."""
    def value(name):
        m = re.search(rf"^\s*{name}:\s*(\S+)", text, re.MULTILINE)
        return m.group(1) if m else None

    powered = [value(f"{source} powered") for source in ("AC", "USB", "Wireless", "Dock")]
    number = lambda v: int(v) if v and v.lstrip("-").isdigit() else None  # noqa: E731
    return BatteryStatus(plugged=None if all(p is None for p in powered) else "true" in powered,
                         charge_counter_uah=number(value("Charge counter")), level_pct=number(value("level")))


def battery_status(serial, poll=False):
    """The BatteryStatus of the phone (AdbError if it cannot be read)."""
    return parse_battery(_run(["shell", "dumpsys", "battery"], serial=serial, poll=poll))


def has_coulomb_counter(serial):
    """Whether the battery reports its coulomb counter, according to `dumpsys battery`.

    Phones without one report a charge counter of 0. Returns None when unknown (older
    Android versions do not show it, or the command failed).
    """
    try:
        counter = battery_status(serial).charge_counter_uah
    except AdbError:
        return None  # in the debug log
    return None if counter is None else counter != 0


def wait_for_power(plugged, serial, interval=1.0):
    """Block until the phone is (un)plugged, according to `dumpsys battery` (for Wi-Fi connections)."""
    _wait_until(lambda: battery_status(serial, poll=True).plugged == plugged, interval)
    logger.info("Phone %s", "plugged in" if plugged else "running on battery")


def connect(address):
    """Connect to a phone over Wi-Fi (adb connect HOST:PORT); returns its serial.

    adb connect exits with 0 even when it fails: its message tells.
    """
    out = _run(["connect", address], timeout=20).strip()
    if not re.match(r"(already )?connected to ", out):
        raise AdbError(f"Cannot connect to {address}: {out or 'no answer'}")
    return out.split(" to ", 1)[1].strip()


def pair(address, code):
    """Pair with a phone's wireless debugging (Android 11+): adb pair HOST:PORT CODE."""
    out = _run(["pair", address, code], timeout=30).strip()
    if "Successfully paired" not in out:
        raise AdbError(f"Cannot pair with {address}: {out or 'no answer'}")
    return out


def wifi_address(serial):
    """The IPv4 address of the phone on its Wi-Fi network (AdbError if it has none)."""
    out = _run(["shell", "ip -f inet addr show wlan0"], serial=serial)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
    if not m:
        raise AdbError("The phone is not connected to a Wi-Fi network (wlan0 has no address)")
    return m.group(1)


def switch_to_wifi(serial, port=5555):
    """Make a USB-connected phone also listen over Wi-Fi (adb tcpip), connect to it and return its new serial."""
    address = f"{wifi_address(serial)}:{port}"
    _run(["tcpip", str(port)], serial=serial)
    deadline = time.monotonic() + 10
    while True:  # adbd restarts in TCP mode
        time.sleep(1)
        try:
            return connect(address)
        except AdbError:
            if time.monotonic() > deadline:
                raise


# Battery statistics options turned on for a session, and off again by restore:
# - full-wake-history records every wakelock in the history, not just the first one;
# - no-auto-reset stops Android from resetting the statistics when the phone is unplugged
#   with a high battery level, which would erase the history of the time before.
SESSION_OPTIONS = ("full-wake-history", "no-auto-reset")


def _try(serial, args, failure):
    """Run an adb command whose failure must not stop the session: returns None, or why it failed."""
    try:
        _run(args, serial=serial)
    except AdbError as e:
        logger.warning("%s: %s", failure, e)
        return f"{failure} ({e})."
    return None


def prepare(serial):
    """Reset battery statistics so the history only covers the coming session.

    Returns (has_coulomb_counter(serial), notes). Without the counter, the energy can only
    be estimated from the battery level, which needs a much longer session. notes say what
    could not be done, which does not prevent recording (e.g. a phone forbidding am kill-all).
    """
    log_diagnostics(serial, "before the session", battery=False)  # read below in any case
    coulomb = has_coulomb_counter(serial)
    if coulomb is False:
        logger.warning("The battery reports no coulomb counter (charge counter 0)")
    notes = [_try(serial, ["shell", "am", "kill-all"], "The background apps could not be stopped before the session")]
    _run(["shell", "dumpsys", "batterystats", "--reset"], serial=serial)
    notes += [_try(serial, ["shell", "dumpsys", "batterystats", "--enable", option],
                   f"The battery statistics option {option} could not be turned on") for option in SESSION_OPTIONS]
    return coulomb, [note for note in notes if note]


def restore(serial):
    """Turn the battery statistics options of prepare off again (best effort: the phone may be gone)."""
    for option in SESSION_OPTIONS:
        _try(serial, ["shell", "dumpsys", "batterystats", "--disable", option],
             f"The battery statistics option {option} could not be turned off")


def clock_offset_ms(serial, samples=5):
    """Device clock minus host clock, in ms, compensating for the adb round trip.

    Uses nanosecond `date` output when the device supports it: the device read its clock
    somewhere during the round trip, so of several samples the one with the shortest round
    trip is kept (its error is at most half of it; Wi-Fi round trips vary a lot). Otherwise
    `date +%s` only has 1 s resolution, so the moment its value ticks over is timed instead.
    """
    def sample(fmt, poll=False):
        before = time.time()
        out = _run(["shell", "date", fmt], serial=serial, poll=poll).strip()
        after = time.time()
        return out, (before + after) / 2 * 1000, (after - before) * 1000  # host time at the middle, round trip

    out, host_ms, rtt = sample("+%s%N")
    if out.isdigit() and len(out) > 13:
        best = (rtt, round(int(out) / 1_000_000 - host_ms))
        for _ in range(samples - 1):
            out, host_ms, rtt = sample("+%s%N", poll=True)
            if out.isdigit():
                best = min(best, (rtt, round(int(out) / 1_000_000 - host_ms)))
        logger.info("Clock offset: %d ms (±%.0f ms, from the nanosecond date)", best[1], best[0] / 2)
        return best[1]
    previous = out[:10]  # the seconds, followed by an unsupported "%N"
    deadline = time.time() + 2.5
    while time.time() < deadline:
        out, host_ms, _ = sample("+%s", poll=True)  # logged when the second ticks over
        if out != previous and out.isdigit():
            offset = round(int(out) * 1000 - host_ms)
            logger.info("Clock offset: %d ms (when the device's seconds ticked over)", offset)
            return offset
        previous = out
    if not out.isdigit():
        raise AdbError(f"cannot read the phone's clock: 'date +%s' printed {out!r}")
    offset = round(int(out) * 1000 + 500 - host_ms)  # adb too slow to see the tick: ±0.5 s
    logger.info("Clock offset: %d ms (±0.5 s: adb was too slow to see the seconds tick over)", offset)
    return offset


def dump_batterystats(serial, path, history_only=True, timeout=300):
    """Save the checkin-format battery statistics (including history since the last reset).

    `-c` prints the checkin format with the history; unlike `--checkin` it neither commits
    nor resets the statistics. With `--history` (Android 5.0+), only the history is printed:
    the per-app statistics, slow to compute, are skipped, and with them the battery capacity
    (the bt and pws lines). If the phone prints no history that way, the full statistics are
    saved. exec-out keeps the output byte-exact (no CRLF translation).

    Returns whether the file only holds the history.
    """
    started = time.monotonic()
    with open(path, "wb") as out:
        _run(["exec-out", "dumpsys", "batterystats", "-c"] + (["--history"] if history_only else []),
             serial=serial, timeout=timeout, stdout=out)
    if history_only and not _has_history(path):
        logger.info("No battery history printed with --history: reading the full battery statistics")
        return dump_batterystats(serial, path, history_only=False, timeout=timeout)
    logger.info("Battery statistics%s transferred: %d bytes written to %s in %.1f s",
                " (history)" if history_only else "", os.path.getsize(path), path, time.monotonic() - started)
    return history_only


def _has_history(path):
    with open(path, "rb") as f:
        return any(line.startswith(b"9,h,") for line in f)


def shell(serial, command, timeout=30, input=None):
    """Run a shell command line on the device and return its output (AdbError if it fails)."""
    return _run(["shell", command], serial=serial, timeout=timeout, input=input)


def pull(serial, remote, path, timeout=300):
    """Copy a file from the device to path.

    Some Android versions do not let `adb pull` read every folder the shell can read: the
    file is then copied with `cat` (exec-out keeps it byte-exact).
    """
    try:
        _run(["pull", remote, str(path)], serial=serial, timeout=timeout)
    except AdbError:
        logger.info("adb pull failed, copying %s with cat instead", remote)
        with open(path, "wb") as out:
            _run(["exec-out", "cat", remote], serial=serial, timeout=timeout, stdout=out)
    logger.info("Copied %s to %s (%d bytes)", remote, path, os.path.getsize(path))
