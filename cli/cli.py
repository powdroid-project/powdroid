"""Interactive command-line workflow: prepare, record, collect, process."""

import itertools
import sys
import threading
import traceback
from datetime import datetime

from core import PowDroidError, adb, checks, metrics, session


def log(message):
    print(f"[PowDroid] {message}")


def run_checks():
    log("Checking configuration...")
    ok = True
    for result in checks.run_all():
        log(f"  {'OK   ' if result.success else 'ERROR'} {result.message}")
        if result.hint and not result.success:
            log(f"        {result.hint}")
        ok = ok and result.success
    return ok


def wait(connected, serial, verbose):
    log("Waiting for the device to be " + ("connected..." if connected else "unplugged..."))
    adb.wait_for(connected, serial)
    if verbose:
        log(f"Device {serial} {'connected' if connected else 'disconnected'}.")


def with_spinner(message, func, *args):
    done = threading.Event()

    def spin():
        for c in itertools.cycle("|/-\\"):
            if done.wait(0.1):
                break
            sys.stdout.write(f"\r[PowDroid] {message} {c}")
            sys.stdout.flush()
        sys.stdout.write(f"\r[PowDroid] {message} done.\n")

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    try:
        return func(*args)
    finally:
        done.set()
        thread.join()


def main(output_formats, out_dir, serial=None, verbose=False, show_traceback=False):
    print(r"  ____               ____            _     _ ")
    print(r" |  _ \ _____      _|  _ \ _ __ ___ (_) __| |")
    print(r" | |_) / _ \ \ /\ / / | | | '__/ _ \| |/ _` |")
    print(r" |  __/ (_) \ V  V /| |_| | | | (_) | | (_| |")
    print(r" |_|   \___/ \_/\_/ |____/|_|  \___/|_|\__,_|")
    print()
    if not run_checks():
        return 1
    try:
        return _record(output_formats, out_dir, serial, verbose)
    except (PowDroidError, OSError) as e:
        log(f"ERROR | {e}")
        if show_traceback:
            traceback.print_exc()
        return 1


def _record(output_formats, out_dir, serial, verbose):
    log("Step 1/4 | Preparing the device")
    device = adb.find_device(serial)
    if device is None or not device.ready:
        if device is not None and device.state == "unauthorized":
            log("Accept the USB debugging prompt on your phone.")
        else:
            log("No device detected. Please connect your device via USB.")
        wait(True, serial, verbose)
        device = adb.find_device(serial)
    serial = device.serial
    log(f"Using {device.label} (Android {device.android_version or '?'}, {serial}).")
    adb.prepare(serial)

    log("Step 2/4 | Recording")
    log("Unplug your device, then follow the instructions.")
    wait(False, serial, verbose)
    input("=> Press ENTER to start recording your test session.")
    start = datetime.now()
    log(f"Recording since {start:%H:%M:%S}.")
    input("=> Press ENTER once you have finished your test session.")
    stop = datetime.now()
    log(f"Session recorded: {(stop - start).total_seconds():.0f} s.")

    log("Step 3/4 | Collecting battery data")
    log("Please reconnect your device via USB.")
    wait(True, serial, verbose)
    result = with_spinner("Reading battery statistics...",
                          session.collect, device, start, stop, out_dir, "html" in output_formats)

    log("Step 4/4 | Results")
    for path in (result.csv_path, result.json_path, result.html_path):
        if path:
            log(f"Written {path}")
    figures = metrics.summary_items(result.summary)
    log(f"Energy {figures['energy']}, average power {figures['mean_power']} over "
        f"{figures['duration']} (measured time {figures['coverage']}).")
    for warning in result.warnings:
        log(f"WARNING | {warning}")
    log("All tasks completed. Thank you for using PowDroid!")
    return 0
