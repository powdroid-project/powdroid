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

from core import adb, debug, metrics, session

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
        self.coulomb = adb.prepare(device.serial)
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

        self.assertIs(self.coulomb, True)
        self.assertEqual(data["current_source"], "coulomb_counter")
        rows = metrics.read_csv(result.csv_path)
        self.assertEqual(len(rows), len(result.rows))
        self.assertAlmostEqual(sum(r["duration_ms"] for r in rows) / 1000, SESSION_S, delta=0.1)
        self.assertFalse(any(r["plugged"] for r in rows))
        known = [r["current_ma"] for r in rows if r["current_ma"] is not None]
        self.assertTrue(known)
        for current in known:  # 1 mAh every 2 steps of 100 ms
            self.assertAlmostEqual(current, 18000, delta=1)

    def test_collect_without_coulomb_counter(self):
        with mock.patch.dict(os.environ, FAKE_ADB_NO_COULOMB="1"):
            result = self.record_session()
        self.assertIs(self.coulomb, False)  # known before recording
        self.assertEqual(json.loads(result.json_path.read_text())["current_source"], "battery_level")
        known = [r["current_ma"] for r in result.rows if r["current_ma"] is not None]
        self.assertTrue(known)
        for current in known:  # 1 % of 3000 mAh every 3 steps of 100 ms
            self.assertAlmostEqual(current, 360000, delta=1)

    def test_debug_log(self):
        path = debug.enable(self.dir / "debug.log")
        self.addCleanup(debug.disable)
        self.record_session()
        adb._polled.clear()
        for _ in range(3):  # polled commands are only logged when their answer changes
            adb.list_devices(poll=True)
        (self.dir / "device" / "state").unlink()
        adb.list_devices(poll=True)
        debug.disable()
        self.assertIsNone(debug.log_path())
        adb.list_devices()  # not logged any more
        log = path.read_text(encoding="utf-8")
        for expected in ("debug log, started", "adb found in PATH", "Android Debug Bridge version",
                         "Device diagnostics, before the session", "getprop $p",
                         "shell dumpsys batterystats --reset: exit code 0", "Clock offset: ",
                         "Battery statistics transferred: ", "lines by kind: h ", "| 9,0,i,vers",
                         "Battery history: ", "charge counter: ", "rows; summary: ", "Written ",
                         "Debug log stopped."):
            self.assertIn(expected, log)
        polled = log.split("Written ")[-1]
        self.assertEqual(polled.count("adb devices: exit code 0"), 2)
        self.assertIn("(the previous answer came 3 times)", polled)
        self.assertNotIn("Running adb devices", polled)

    def test_clock_offset_with_seconds_only_date(self):
        with mock.patch.dict(os.environ, FAKE_ADB_SECONDS_ONLY="1"):
            self.assertAlmostEqual(adb.clock_offset_ms("FAKE123"), 30000, delta=100)


if __name__ == "__main__":
    unittest.main()
