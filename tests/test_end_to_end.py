"""The whole collection pipeline (adb -> dumpsys / perfetto -> CSV/JSON/HTML) against tests/fake_adb.py."""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

from cli import cli
from core import adb, debug, metrics, perfetto, session

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

    def record_session(self, use_perfetto=False):
        device = adb.find_device()
        self.assertEqual((device.serial, device.model, device.android_version), ("FAKE123", "Pixel 8 (fake)", "15"))
        self.preparation = session.prepare(device.serial, use_perfetto)
        self.coulomb = self.preparation.coulomb
        self.set_state(None)
        start = datetime.now()
        time.sleep(SESSION_S)
        stop = datetime.now()
        self.set_state("device")
        return session.collect(device, start, stop, self.dir / "out", html=True, preparation=self.preparation)

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

    def test_collect_with_perfetto(self):
        result = self.record_session(use_perfetto=True)
        self.assertIsNone(self.preparation.perfetto_unavailable)
        self.assertTrue(self.preparation.trace.voltage)
        data = json.loads(result.json_path.read_text())
        self.assertEqual(data["current_source"], "perfetto")
        self.assertEqual(Path(data["trace_file"]).parent, self.dir / "out" / "dump")
        self.assertTrue(Path(data["trace_file"]).stat().st_size)
        self.assertFalse((self.dir / "device" / "trace.pftrace").exists())  # deleted from the phone
        self.assertFalse((self.dir / "device" / "perfetto").exists())  # stopped
        self.assertEqual(data["perfetto"]["median_poll_interval_ms"], 100)
        self.assertEqual(data["perfetto"]["counters"], ["charge_uah", "current_ua", "voltage_uv", "level_pct"])
        self.assertEqual(data["batterystats_summary"]["current_source"], "coulomb_counter")
        # At most the uncertainty: at 10 to 30 A, the counter changes by about 0.3 to 0.8 mAh between
        # two polls of 100 ms.
        self.assertLessEqual(len(data["warnings"]), 1)
        for warning in data["warnings"]:
            self.assertRegex(warning, r"with the coulomb counter's 0\.\d+ mAh resolution")

        rows = metrics.read_csv(result.csv_path)
        self.assertEqual(metrics.columns(rows)[-2:], ["rail_S4M_VDD_CPUCL0_j", "rail_VSYS_PWR_DISPLAY_j"])
        self.assertFalse(any(r["plugged"] for r in rows))
        # The fake battery draws 30 A and 10 A in turn every 400 ms: the current samples show it.
        known = [r["current_ma"] for r in rows if r["current_ma"] is not None]
        self.assertGreater(max(known), 25000)
        self.assertLess(min(known), 15000)
        self.assertAlmostEqual(result.summary.mean_current_ma, 20000, delta=2000)
        self.assertGreater(result.summary.measured_s, SESSION_S - 0.3)
        cpu = data["power_rails"][0]
        self.assertEqual((cpu["name"], cpu["subsystem"]), ("S4M_VDD_CPUCL0", "CPU(LITTLE)"))
        self.assertAlmostEqual(cpu["mean_power_w"], 1.5, places=3)
        self.assertAlmostEqual(sum(r["rail_S4M_VDD_CPUCL0_j"] for r in rows), cpu["energy_j"], places=6)

    def test_perfetto_unavailable(self):
        path = debug.enable(self.dir / "debug.log")
        self.addCleanup(debug.disable)
        for variables, reason in (
                ({"FAKE_ADB_SDK": "28"}, "it needs Android 10 or newer (API level 29) and this phone has API level 28"),
                ({"FAKE_ADB_SDK": "29", "FAKE_ADB_TRACED": ""}, "its tracing service is not running "
                 "(init.svc.traced is not set); on Android 10, enable it with: adb shell setprop "
                 "persist.traced.enable 1")):
            with self.subTest(reason=reason), mock.patch.dict(os.environ, variables):
                result = self.record_session(use_perfetto=True)
                self.assertIsNone(self.preparation.trace)
                self.assertEqual(self.preparation.perfetto_unavailable, reason)
                self.assertEqual(self.preparation.perfetto_notice, f"Perfetto is not available because {reason}: "
                                                                   "PowDroid uses the battery statistics instead.")
                data = json.loads(result.json_path.read_text())
                self.assertEqual((data["current_source"], data["trace_file"]), ("coulomb_counter", None))
                self.assertEqual(data["perfetto_unavailable"], reason)
                self.assertFalse([w for w in data["warnings"] if "Perfetto" in w])  # expected: not a warning
                self.assertIn(f"Perfetto is not available, using the battery statistics: {reason}",
                              path.read_text(encoding="utf-8"))

    def test_old_perfetto_without_voltage(self):
        # perfetto versions before 2024 reject BATTERY_COUNTER_VOLTAGE: retried without it.
        with mock.patch.dict(os.environ, FAKE_ADB_OLD_PERFETTO="1", FAKE_ADB_NO_PULL="1"):
            result = self.record_session(use_perfetto=True)
        self.assertFalse(self.preparation.trace.voltage)
        data = json.loads(result.json_path.read_text())
        self.assertEqual(data["current_source"], "perfetto")  # copied with cat, as adb pull failed
        self.assertNotIn("voltage_uv", data["perfetto"]["counters"])
        self.assertTrue(4180 <= result.summary.voltage_min_mv <= 4200)  # from the battery history

    def test_cancel_stops_the_trace(self):
        preparation = session.prepare("FAKE123", use_perfetto=True)
        self.assertTrue((self.dir / "device" / "perfetto").exists())
        perfetto.cancel(preparation.trace)
        self.assertFalse((self.dir / "device" / "perfetto").exists())
        self.set_state(None)
        perfetto.cancel(preparation.trace)  # unplugged: no error

    def run_cli(self, out, **kw):
        """A whole CLI session; returns its output and session JSON."""
        def wait(connected, serial, verbose):
            time.sleep(0 if connected else 0.2)
            self.set_state("device" if connected else None)

        output = io.StringIO()
        with mock.patch.object(cli, "wait", wait), mock.patch("builtins.input", lambda prompt: time.sleep(0.5)), \
                redirect_stdout(output):
            code = cli.main(["csv"], self.dir / out, **kw)
        self.assertEqual(code, 0, output.getvalue())
        return output.getvalue(), json.loads(next((self.dir / out).glob("PowDroid_*.json")).read_text())

    def test_cli_uses_perfetto_by_default(self):
        text, data = self.run_cli("default")
        self.assertIn("Perfetto trace started: battery readings every 500 ms.", text)
        self.assertEqual(data["current_source"], "perfetto")

        with mock.patch.dict(os.environ, FAKE_ADB_SDK="28"):
            text, data = self.run_cli("old")
        self.assertIn("[PowDroid] Perfetto is not available because it needs Android 10 or newer", text)
        self.assertNotIn("WARNING | Perfetto", text)
        self.assertEqual(data["current_source"], "coulomb_counter")

        text, data = self.run_cli("off", use_perfetto=False)
        self.assertNotIn("Perfetto", text)
        self.assertEqual(data["current_source"], "coulomb_counter")
        self.assertNotIn("perfetto_unavailable", data)

    def test_no_perfetto_argument(self):
        import powdroid

        for argv, expected in ((["-o", "csv"], True), (["--no-perfetto"], False)):
            with mock.patch.object(sys, "argv", ["powdroid.py", *argv]), \
                    mock.patch("cli.cli.main", return_value=0) as cli_main:
                self.assertEqual(powdroid.main(), 0)
            self.assertIs(cli_main.call_args.args[5], expected)

    def test_clock_offset_with_seconds_only_date(self):
        with mock.patch.dict(os.environ, FAKE_ADB_SECONDS_ONLY="1"):
            self.assertAlmostEqual(adb.clock_offset_ms("FAKE123"), 30000, delta=100)


if __name__ == "__main__":
    unittest.main()
