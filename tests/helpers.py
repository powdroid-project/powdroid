"""Shared test helpers."""

import os
import sys
from pathlib import Path
from unittest import mock

from powdroid.core import adb, pending

FAKE_ADB = Path(__file__).with_name("fake_adb.py")


def use_fake_adb(test, directory, **variables):
    """Make adb commands run tests/fake_adb.py, with its device state in directory, for this test.

    Pending sessions are kept next to directory, not in the user's folder.
    """
    for patcher in (mock.patch.object(adb, "_command", [sys.executable, str(FAKE_ADB)]),
                    mock.patch.object(pending, "FOLDER", Path(directory).parent / "pending"),
                    mock.patch.dict(os.environ, {"FAKE_ADB_DIR": str(directory), "FAKE_ADB_STEP_MS": "100",
                                                 **variables})):
        patcher.start()
        test.addCleanup(patcher.stop)


def set_fake_state(directory, state):
    """Plug the fake device in ("device"), out (None) or make it "unauthorized"."""
    path = Path(directory) / "state"
    path.parent.mkdir(parents=True, exist_ok=True)
    if state:
        path.write_text(state)
    else:
        path.unlink(missing_ok=True)
