"""Interactive command-line workflow: prepare, record, collect, process."""

import itertools
import logging
import sys
import threading
import time
import traceback

from powdroid.core import PowDroidError, adb, checks, debug, metrics, pending, perfetto, session

logger = logging.getLogger("powdroid.cli")


def log(message, level=logging.INFO):
    """Print a message, and write it to the debug log as context for what follows."""
    print(f"[PowDroid] {message}")
    logger.log(level, message)


def run_checks():
    log("Checking configuration...")
    ok = True
    for result in checks.run_all():
        log(f"  {'OK   ' if result.success else 'ERROR'} {result.message}")
        if result.hint and not result.success:
            log(f"        {result.hint}")
        if result.warning:
            log(f"        WARNING | {result.warning}", logging.WARNING)
        ok = ok and result.success
    return ok


def wait(connected, serial, verbose):
    log("Waiting for the device to be " + ("connected..." if connected else "unplugged..."))
    adb.wait_for(connected, serial)
    if verbose:
        log(f"Device {serial} {'connected' if connected else 'disconnected'}.")


def wait_power(plugged, serial, verbose):
    """Over Wi-Fi: wait for the phone to be plugged into, or unplugged from, a charger."""
    log("Waiting for the phone to be " + ("plugged in..." if plugged else "unplugged from its charger..."))
    adb.wait_for_power(plugged, serial)
    if verbose:
        log(f"Device {serial} {'plugged in' if plugged else 'running on battery'}.")


def with_spinner(message, func, *args, **kwargs):
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
        return func(*args, **kwargs)
    finally:
        done.set()
        thread.join()


def main(output_formats, out_dir, serial=None, verbose=False, show_traceback=False, use_perfetto=True,
         duration=None, connect=None):
    print(r"  ____               ____            _     _ ")
    print(r" |  _ \ _____      _|  _ \ _ __ ___ (_) __| |")
    print(r" | |_) / _ \ \ /\ / / | | | '__/ _ \| |/ _` |")
    print(r" |  __/ (_) \ V  V /| |_| | | | (_) | | (_| |")
    print(r" |_|   \___/ \_/\_/ |____/|_|  \___/|_|\__,_|")
    print()
    if debug.enabled():
        log(f"Writing a debug log to {debug.log_path()}")
    if not run_checks():
        return 1
    for data in pending.load_all():
        log(f"The session of {pending.describe(data)} was not collected: collect it with "
            "powdroid --collect-pending.", logging.WARNING)
    try:
        if connect:
            serial = serial or adb.connect(connect)
            log(f"Connected to {serial} over Wi-Fi.")
        return _record(output_formats, out_dir, serial, verbose, use_perfetto, duration)
    except (PowDroidError, OSError) as e:
        log(f"ERROR | {e}", logging.ERROR)
        logger.debug("Traceback:", exc_info=True)
        if show_traceback:
            traceback.print_exc()
        return 1


def _record(output_formats, out_dir, serial, verbose, use_perfetto, duration=None):
    log("Step 1/4 | Preparing the device")
    devices = adb.list_devices()
    device = adb.find_device(serial, devices)
    if device is None or not device.ready:
        if device is None:
            log("No device detected. Please connect your device via USB.")
        else:
            log(adb.STATE_HINTS.get(device.state, f"The device {device.serial} is not ready ({device.state})."))
        wait(True, serial, verbose)
        device = adb.find_device(serial)
    others = [d.serial for d in devices if d.ready and d.serial != device.serial]
    if others and not serial:
        log(f"Several devices are connected: use -s SERIAL to choose another one than {device.serial} "
            f"({', '.join(others)}).")
    serial = device.serial
    log(f"Using {device.label} (Android {device.android_version or '?'}, {serial}).")
    preparation = session.prepare(serial, use_perfetto)
    if preparation.coulomb is False:
        log(f"WARNING | {session.NO_COULOMB_NOTICE}", logging.WARNING)
    if preparation.trace:
        log(f"Perfetto trace started: battery readings every {perfetto.POLL_MS} ms.")
    elif preparation.perfetto_notice:
        log(preparation.perfetto_notice)
    html = "html" in output_formats
    pending.save(device, preparation, out_dir, html)
    progress = {"start": None, "stop": None, "markers": []}

    def save(**changes):  # what collecting the session later needs, in case it is interrupted
        progress.update(changes)
        pending.save(device, preparation, out_dir, html, **progress)

    try:
        result = _session(output_formats, out_dir, device, preparation, verbose, duration, save)
    except session.NoDataError:
        pending.clear(serial)  # collected, but without usable data: nothing to collect again
        raise
    except BaseException:  # error or Ctrl-C
        if progress["start"] is None:  # not recording yet: give the phone back if it is connected
            session.cancel(preparation)
            pending.clear(serial)
        else:  # recorded: kept on the phone, to be collected later
            log("The recorded session is kept: collect it later with powdroid --collect-pending.")
        raise
    pending.clear(serial)

    log("Step 4/4 | Results")
    print_result(result)
    log("All tasks completed. Thank you for using PowDroid!")
    return 0


def print_result(result):
    for path in (result.csv_path, result.json_path, result.html_path):
        if path:
            log(f"Written {path}")
    figures = metrics.summary_items(result.summary)
    log(f"Energy {figures['energy']}, average power {figures['mean_power']} over "
        f"{figures['duration']} (measured time {figures['coverage']}).")
    if result.summary.extrapolated_energy_j is not None:
        log(f"Estimated energy over all the unplugged time (extrapolated from the average power): "
            f"{figures['extrapolated']}.")
    log(f"Measured with: {figures['source']}.")
    for phase in result.phases:
        log(f"Phase {phase['label']!r}: {metrics.format_energy(phase['energy_j'])}, average power "
            f"{metrics.format_power(phase['mean_power_w'])} over {metrics.format_duration(phase['duration_s'])}.")
    for warning in result.warnings:
        log(f"WARNING | {warning}", logging.WARNING)


def collect_pending(serial=None, verbose=False, show_traceback=False):
    """Collect the sessions recorded but not collected (--collect-pending), waiting for their phone."""
    sessions = [data for data in pending.load_all() if serial in (None, data["device"]["serial"])]
    if not sessions:
        log("No session waiting to be collected.")
        return 0
    code = 0
    for data in sessions:
        log(f"Collecting the session of {pending.describe(data)}")
        try:
            if not any(d.ready and d.serial == data["device"]["serial"] for d in adb.list_devices()):
                log("Please connect this phone.")
                wait(True, data["device"]["serial"], verbose)
            result = with_spinner("Reading battery statistics...", pending.collect, data)
        except (PowDroidError, OSError) as e:
            log(f"ERROR | {e}", logging.ERROR)
            logger.debug("Traceback:", exc_info=True)
            if show_traceback:
                traceback.print_exc()
            code = 1
            continue
        print_result(result)
    return code


def reprocess(json_path, output_formats, out_dir=None, show_traceback=False):
    """Process a saved session again (--reprocess) and print its results."""
    try:
        log(f"Processing {json_path} again")
        result = session.reprocess(json_path, out_dir, "html" in output_formats)
    except (PowDroidError, OSError) as e:
        log(f"ERROR | {e}", logging.ERROR)
        logger.debug("Traceback:", exc_info=True)
        if show_traceback:
            traceback.print_exc()
        return 1
    print_result(result)
    return 0


def _session(output_formats, out_dir, device, preparation, verbose, duration=None, save=lambda **changes: None):
    """Record a session on the prepared device, then collect its data; returns the session.Result.

    Over USB, the session starts once the phone is unplugged and the data is read once it is
    plugged back in. Over Wi-Fi, it starts once the phone runs on battery, and the data is
    read right after. With a duration (seconds), nothing is asked: the session starts when
    the phone is unplugged and stops after that time. Otherwise markers can be added. save is
    called with start, stop and markers as they become known (pending sessions).
    """
    serial = device.serial
    log("Step 2/4 | Recording")
    if device.wireless:
        if adb.battery_status(serial).plugged is not False:
            log("Unplug the phone from its charger: it stays connected over Wi-Fi.")
            wait_power(False, serial, verbose)
        else:
            log("The phone is running on battery.")
    else:
        log("Unplug your device, then follow the instructions.")
        wait(False, serial, verbose)
    markers = []
    if duration:
        start = time.time()
        save(start=start)
        log(f"Recording for {metrics.format_duration(duration)}, until "
            f"{time.strftime('%H:%M:%S', time.localtime(start + duration))}.")
        time.sleep(max(0.0, start + duration - time.time()))
    else:
        input("=> Press ENTER to start recording your test session.")
        start = time.time()
        save(start=start)
        log(f"Recording since {time.strftime('%H:%M:%S', time.localtime(start))}. To mark a moment of the "
            "session (e.g. the start of a scenario step), type a label and press ENTER.")
        while True:
            label = (input("=> Press ENTER alone once you have finished your test session: ") or "").strip()
            if not label:
                break
            markers.append({"time": time.time(), "label": label})
            save(markers=markers)
            log(f"Marker {label!r}, {markers[-1]['time'] - start:.1f} s after the start.")
    stop = time.time()
    save(stop=stop)
    log(f"Session recorded: {stop - start:.0f} s.")

    log("Step 3/4 | Collecting battery data")
    if not device.wireless:
        log("Please reconnect your device via USB.")
        wait(True, serial, verbose)
    elif not any(d.ready and d.serial == serial for d in adb.list_devices()):
        log("The phone is not connected over Wi-Fi any more: waiting for it to come back.")
        wait(True, serial, verbose)
    return with_spinner("Reading battery statistics...", session.collect, device, start, stop, out_dir,
                        "html" in output_formats, preparation=preparation, markers=markers)
