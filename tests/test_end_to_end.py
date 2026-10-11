"""The whole collection pipeline (adb -> dumpsys -> CSV/JSON/HTML) against tests/fake_adb.py."""

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from core import adb, metrics, session

FAKE_ADB = Path(__file__).with_name("fake_adb.py")
SESSION_S = 1.5


@unittest.skipIf(os.name == "nt", "the fake adb launcher is a shell script")
class EndToEndTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        launcher = self.dir / "bin" / "adb"
        launcher.parent.mkdir()
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_ADB}" "$@"\n')
        launcher.chmod(0o755)
        environment = mock.patch.dict(os.environ, {
            "PATH": f"{launcher.parent}{os.pathsep}{os.environ['PATH']}",
            "FAKE_ADB_DIR": str(self.dir / "device"),
            "FAKE_ADB_STEP_MS": "100",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.set_state("device")

    def set_state(self, state):
        path = self.dir / "device" / "state"
        path.parent.mkdir(exist_ok=True)
        if state:
            path.write_text(state)
        else:
            path.unlink(missing_ok=True)
        adb.list_devices()  # the fake logs plug transitions when devices are listed

    def record_session(self):
        device = adb.find_device()
        self.assertEqual((device.serial, device.model, device.android_version), ("FAKE123", "Pixel 8 (fake)", "15"))
        adb.prepare(device.serial)
        self.set_state(None)
        start = datetime.now()
        time.sleep(SESSION_S)
        stop = datetime.now()
        self.set_state("device")
        return session.collect(device, start, stop, self.dir / "out", html=True)

    def test_collect(self):
        result = self.record_session()
        data = json.loads(result.json_path.read_text())
        self.assertEqual(data["device"]["model"], "Pixel 8 (fake)")
        self.assertAlmostEqual(data["clock_offset_ms"], 30000, delta=50)
        self.assertTrue(result.html_path.exists())
        self.assertEqual(len(list((self.dir / "out" / "dump").glob("batterystats_*.txt"))), 1)

        rows = metrics.read_csv(result.csv_path)
        self.assertEqual(len(rows), len(result.rows))
        self.assertAlmostEqual(sum(r["duration_ms"] for r in rows) / 1000, SESSION_S, delta=0.1)
        self.assertFalse(any(r["plugged"] for r in rows))
        known = [r["current_ma"] for r in rows if r["current_ma"] is not None]
        self.assertTrue(known)
        for current in known:  # 1 mAh every 2 steps of 100 ms
            self.assertAlmostEqual(current, 18000, delta=1)

    def test_clock_offset_with_seconds_only_date(self):
        with mock.patch.dict(os.environ, FAKE_ADB_SECONDS_ONLY="1"):
            self.assertAlmostEqual(adb.clock_offset_ms("FAKE123"), 30000, delta=100)


if __name__ == "__main__":
    unittest.main()
