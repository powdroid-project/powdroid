"""Sessions recorded but not collected yet, so that they can still be collected after a crash or a Ctrl-C.

While a session goes on, what collecting it needs is kept in ~/.powdroid/pending/<serial>.json
(one per device): the device, the preparation (Perfetto trace, clock offset...), the output
folder, the start and stop times and the markers. The file is deleted once the session is
collected or discarded. The battery statistics options stay on and the Perfetto trace keeps
running on the phone meanwhile, so the session can be collected later (the trace stops by
itself after a day).
"""

import json
import logging
import os
import re
import tempfile
import time
from dataclasses import fields
from pathlib import Path

from powdroid.core import PowDroidError, __version__, adb, perfetto, session

logger = logging.getLogger("powdroid.pending")

FOLDER = Path.home() / ".powdroid" / "pending"


def _path(serial):
    return FOLDER / (re.sub(r"[^\w.-]", "_", serial) + ".json")


def save(device, preparation, out_dir, html=False, start=None, stop=None, markers=()):
    """Write (or update) the pending session of this device. Failing to write it only logs."""
    trace = preparation.trace
    data = {
        "powdroid_version": __version__,
        "saved_at": time.time(),
        "device": {f.name: getattr(device, f.name) for f in fields(device)},
        "out_dir": str(Path(out_dir).expanduser().absolute()),
        "html": html,
        "preparation": {
            "coulomb": preparation.coulomb,
            "trace": {"pid": trace.pid, "voltage": trace.voltage} if trace else None,
            "perfetto_unavailable": preparation.perfetto_unavailable,
            "notes": preparation.notes,
            "clock_offset_ms": preparation.clock_offset_ms,
        },
        "start": start,
        "stop": stop,
        "markers": list(markers),
    }
    path = _path(device.serial)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(f.name, path)  # never a half-written file
    except OSError as e:
        logger.warning("Cannot save the pending session in %s: %s", path, e)


def clear(serial):
    try:
        _path(serial).unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Cannot delete the pending session of %s: %s", serial, e)


def load_all():
    """The pending sessions (only those recording had started for), the most recent first."""
    sessions = []
    for path in FOLDER.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("start") is not None:
                sessions.append(data)
        except (OSError, ValueError) as e:
            logger.warning("Cannot read the pending session %s: %s", path, e)
    return sorted(sessions, key=lambda d: -d["start"])


def describe(data):
    """e.g. "Google Pixel 8 (FAKE123), recorded at 14:03:12 on 2026-10-15"."""
    device = adb.Device(**data["device"])
    started = time.strftime("%H:%M:%S on %Y-%m-%d", time.localtime(data["start"]))
    return f"{device.label} ({device.serial}), recorded at {started}"


def _restore(data):
    device = adb.Device(**data["device"])
    prepared = data["preparation"]
    trace = prepared.get("trace")
    preparation = session.Preparation(
        device.serial, prepared.get("coulomb"), perfetto.Trace(device.serial, trace["pid"], trace["voltage"])
        if trace else None, prepared.get("perfetto_unavailable"), list(prepared.get("notes") or []),
        clock_offset_ms=prepared.get("clock_offset_ms"))
    return device, preparation


def collect(data):
    """Collect a pending session (its device must be connected) and delete it; returns the session.Result.

    A session whose stop was not recorded (PowDroid stopped while recording) ends now: the
    time after the phone was plugged back in is left out, as for any session.
    """
    device, preparation = _restore(data)
    if not adb.is_ready(device.serial):
        raise PowDroidError(f"Connect {device.label} ({device.serial}) to collect its session.")
    stop = data.get("stop")
    if stop is None:
        preparation.notes.append("PowDroid stopped while this session was recording: it was collected later, "
                                 "and ends when the phone was plugged back in (or when it was collected).")
        stop = time.time()
    result = session.collect(device, data["start"], stop, data["out_dir"], data.get("html", False),
                             preparation=preparation, markers=data.get("markers", []))
    clear(device.serial)
    return result


def cancel(preparation):
    """Give the phone back (best effort, if connected) and forget its pending session."""
    session.cancel(preparation)
    clear(preparation.serial)


def discard(data):
    """Cancel a pending session saved by save."""
    cancel(_restore(data)[1])

