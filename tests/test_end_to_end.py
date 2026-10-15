"""The whole collection pipeline (adb -> dumpsys / perfetto -> CSV/JSON/HTML) against tests/fake_adb.py."""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import set_fake_state, use_fake_adb
from powdroid.cli import cli
from powdroid.core import adb, debug, metrics, pending, session

SESSION_S = 1.5


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        use_fake_adb(self, self.dir / "device")
        self.set_state("device")

    def set_state(self, state):
        set_fake_state(self.dir / "device", state)
        adb.list_devices()  # the fake logs plug transitions when devices are listed

    def record_session(self, use_perfetto=False):
        device = adb.find_device()
        self.assertEqual((device.serial, device.model, device.android_version), ("FAKE123", "Pixel 8 (fake)", "15"))
        self.preparation = session.prepare(device.serial, use_perfetto)
        self.coulomb = self.preparation.coulomb
        self.set_state(None)
        start = time.time()
        time.sleep(SESSION_S)
        stop = time.time()
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
        for expected in ("debug log, started", "adb programs found", "adb used: ", "Android Debug Bridge version",
                         "Device diagnostics, before the session", "getprop $p",
                         "shell dumpsys batterystats --reset: exit code 0", "Clock offset: ",
                         "Battery statistics (history) transferred: ", "lines by kind: h ", "| 9,0,i,vers",
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
        self.assertEqual(Path(data["trace_file"]).parent, Path("dump"))  # relative to the JSON file
        self.assertTrue((result.json_path.parent / data["trace_file"]).stat().st_size)
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
        # Over the ~1.2 s measured, the mean depends on where the 800 ms cycles start and stop.
        self.assertAlmostEqual(result.summary.mean_current_ma, 20000, delta=3500)
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

    def options(self):
        """The batterystats options turned on on the fake phone."""
        path = self.dir / "device" / "options"
        return path.read_text().split() if path.exists() else []

    def test_cancel_stops_the_trace(self):
        preparation = session.prepare("FAKE123", use_perfetto=True)
        self.assertTrue((self.dir / "device" / "perfetto").exists())
        self.assertEqual(self.options(), ["full-wake-history", "no-auto-reset"])
        session.cancel(preparation)
        self.assertFalse((self.dir / "device" / "perfetto").exists())
        self.assertEqual(self.options(), [])
        self.set_state(None)
        session.cancel(preparation)  # already cancelled, and unplugged: no error
        self.set_state("device")
        preparation = session.prepare("FAKE123", use_perfetto=True)
        self.set_state(None)
        session.cancel(preparation)  # unplugged: no error either

    def test_options_are_turned_off_after_the_session(self):
        self.record_session()
        self.assertTrue(self.preparation.restored)
        self.assertEqual(self.options(), [])

    def test_background_apps_cannot_be_stopped(self):
        with mock.patch.dict(os.environ, FAKE_ADB_NO_KILL_ALL="1"):
            result = self.record_session()
        self.assertTrue(result.warnings[0].startswith("The background apps could not be stopped before the "
                                                      "session ('adb -s FAKE123 shell am kill-all' failed: "
                                                      "java.lang.SecurityException"))

    def test_a_phone_is_preferred_to_an_emulator(self):
        with mock.patch.dict(os.environ, FAKE_ADB_OTHERS="emulator-5554:device,0123:no permissions"):
            devices = adb.list_devices()
            self.assertEqual([(d.serial, d.state, d.emulator) for d in devices], [
                ("emulator-5554", "device", True), ("0123", "no permissions", False), ("FAKE123", "device", False)])
            self.assertEqual(adb.find_device().serial, "FAKE123")
            self.set_state(None)
            self.assertEqual(adb.find_device().serial, "emulator-5554")

    def test_clock_offset_from_the_fastest_sample(self):
        delays = iter([0.2, 0.0, 0.2, 0.2, 0.2])  # only the 2nd round trip is short

        def run(args, **kw):
            time.sleep(next(delays) / 2)
            return f"{round((time.time() + 30) * 1e9)}\n"  # the phone is 30 s ahead, read right away

        with mock.patch.object(adb, "_run", run):
            self.assertAlmostEqual(adb.clock_offset_ms("FAKE123"), 30000, delta=5)

    def test_clock_drift_is_reported(self):
        preparation = session.prepare("FAKE123")
        preparation.clock_offset_ms -= 5000  # as if the phone's clock had been set 5 s forward meanwhile
        self.set_state(None)
        start = time.time()
        time.sleep(0.3)
        stop = time.time()
        self.set_state("device")
        result = session.collect(adb.find_device(), start, stop, self.dir / "out", preparation=preparation)
        self.assertIn("The phone's clock moved by +5.0 s relative to the computer's during the session",
                      result.warnings[0])
        data = json.loads(result.json_path.read_text())
        self.assertAlmostEqual(data["clock_offset_at_start_ms"], 25000, delta=100)

    def test_history_only_dump(self):
        result = self.record_session()
        dump = result.json_path.parent / json.loads(result.json_path.read_text())["dump_file"]
        self.assertNotIn("9,0,l,pws", dump.read_text())  # the statistics were not computed
        with mock.patch.dict(os.environ, FAKE_ADB_NO_HISTORY_OPTION="1"):
            result = self.record_session()
        dump = result.json_path.parent / json.loads(result.json_path.read_text())["dump_file"]
        self.assertIn("9,0,l,pws", dump.read_text())  # full statistics, as --history printed no history
        with mock.patch.dict(os.environ, FAKE_ADB_NO_COULOMB="1"):
            result = self.record_session()
        dump = result.json_path.parent / json.loads(result.json_path.read_text())["dump_file"]
        self.assertIn("9,0,l,pws", dump.read_text())  # the battery capacity is needed

    def test_reprocess(self):
        import shutil

        from powdroid.__main__ import main

        result = self.record_session(use_perfetto=True)
        original = json.loads(result.json_path.read_text())
        moved = self.dir / "moved"
        shutil.move(self.dir / "out", moved)  # the session folder can be moved
        json_path = moved / result.json_path.name
        again = session.reprocess(json_path, html=True)
        self.assertEqual(again.csv_path, moved / result.csv_path.name)
        self.assertEqual(again.csv_path.read_text(), (moved / result.csv_path.name).read_text())
        data = json.loads(json_path.read_text())
        for key in ("summary", "warnings", "device", "clock_offset_ms", "dump_file", "trace_file", "power_rails"):
            self.assertEqual(data[key], original[key], key)
        self.assertTrue(again.html_path.exists())

        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["powdroid", "--reprocess", str(json_path), "-d", str(self.dir / "new")]), \
                redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("Measured with: Perfetto", output.getvalue())
        self.assertTrue((self.dir / "new" / result.csv_path.name).exists())

        (moved / original["dump_file"]).unlink()
        with self.assertRaisesRegex(session.NoDataError, "are missing: it cannot be processed again"):
            session.reprocess(json_path)

    def test_track_devices(self):
        tracker = adb.DeviceTracker()
        updates = iter(tracker)
        try:
            self.assertEqual([(d.serial, d.state) for d in next(updates)], [("FAKE123", "device")])
            set_fake_state(self.dir / "device", None)
            self.assertEqual(next(updates), [])
            set_fake_state(self.dir / "device", "unauthorized")
            self.assertEqual([(d.serial, d.state) for d in next(updates)], [("FAKE123", "unauthorized")])
        finally:
            tracker.close()
        self.assertEqual(list(updates), [])  # closed: the iteration ends

    def test_unreadable_clock(self):
        with mock.patch.object(adb, "_run", return_value="Thu Oct 15 12:00:00 UTC 2026\n"):
            with self.assertRaisesRegex(adb.AdbError, "cannot read the phone's clock"):
                adb.clock_offset_ms("FAKE123")

    def run_cli(self, out, answers=None, **kw):
        """A whole CLI session; returns its output and session JSON.

        answers are what is typed at each prompt (by default ENTER after 0.5 s); with
        answers=[], nothing may be asked.
        """
        self.waits = []

        def wait(connected, serial, verbose):
            self.waits.append(("connected" if connected else "unplugged", serial))
            time.sleep(0 if connected else 0.2)
            self.set_state("device" if connected else None)

        def wait_power(plugged, serial, verbose):
            self.waits.append(("charging" if plugged else "on battery", serial))
            time.sleep(0.2)
            (self.dir / "device" / "power").write_text("1" if plugged else "0")
            adb.battery_status(serial)  # the fake logs the plug change

        typed = iter(answers if answers is not None else [])

        def answer(prompt):
            time.sleep(0.5)
            if answers is None:
                return ""
            try:
                return next(typed)
            except StopIteration:
                self.fail(f"Unexpected question: {prompt}")

        output = io.StringIO()
        with mock.patch.object(cli, "wait", wait), mock.patch.object(cli, "wait_power", wait_power), \
                mock.patch("builtins.input", answer), redirect_stdout(output):
            code = cli.main(["csv"], self.dir / out, **kw)
        self.assertEqual(code, 0, output.getvalue())
        return output.getvalue(), json.loads(next((self.dir / out).glob("PowDroid_*.json")).read_text())

    def test_cli_markers(self):
        text, data = self.run_cli("markers", answers=["", "Scroll", "Video", ""], use_perfetto=False)
        self.assertRegex(text, r"Marker 'Scroll', 0\.\d s after the start\.")
        self.assertEqual([m["label"] for m in data["markers"]], ["Scroll", "Video"])
        self.assertEqual([p["label"] for p in data["phases"]], ["Start", "Scroll", "Video"])
        self.assertIn("Phase 'Video': ", text)

    def run_interrupted_cli(self, out, answers=None):
        """A CLI session interrupted by Ctrl-C at the prompt after the given answers.

        Without answers, it is interrupted while waiting for the phone to be unplugged.
        """
        typed = iter(answers or [])

        def answer(prompt):
            time.sleep(0.3)
            try:
                return next(typed)
            except StopIteration:
                raise KeyboardInterrupt from None

        def wait(connected, serial, verbose):
            if answers is None:
                raise KeyboardInterrupt
            self.set_state("device" if connected else None)

        output = io.StringIO()
        with mock.patch.object(cli, "wait", wait), mock.patch("builtins.input", answer), redirect_stdout(output), \
                self.assertRaises(KeyboardInterrupt):
            cli.main(["csv"], self.dir / out)
        return output.getvalue()

    def test_interrupted_before_recording(self):
        text = self.run_interrupted_cli("before")  # while waiting for the phone to be unplugged
        self.assertNotIn("collect it later", text)
        self.assertEqual(pending.load_all(), [])
        self.assertFalse(list(pending.FOLDER.glob("*.json")))
        self.assertEqual(self.options(), [])  # the phone is given back
        self.assertFalse((self.dir / "device" / "perfetto").exists())

    def test_interrupted_session_is_collected_later(self):
        from powdroid.__main__ import main

        text = self.run_interrupted_cli("later", ["", "Scroll"])  # Ctrl-C while recording, after a marker
        self.assertIn("The recorded session is kept: collect it later with powdroid --collect-pending.", text)
        (saved,) = pending.load_all()
        self.assertEqual((saved["device"]["serial"], saved["stop"], saved["markers"][0]["label"]),
                         ("FAKE123", None, "Scroll"))
        self.assertTrue((self.dir / "device" / "perfetto").exists())  # the trace still runs
        self.assertEqual(self.options(), ["full-wake-history", "no-auto-reset"])

        time.sleep(0.5)
        self.set_state("device")  # plugged back in: the end of the session
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["powdroid", "--collect-pending"]), redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("Collecting the session of Google Pixel 8 (fake) (FAKE123), recorded at", output.getvalue())
        self.assertEqual(pending.load_all(), [])
        self.assertEqual(self.options(), [])
        data = json.loads(next((self.dir / "later").glob("PowDroid_*.json")).read_text())
        self.assertEqual(data["current_source"], "perfetto")
        self.assertIn("PowDroid stopped while this session was recording", data["warnings"][0])
        self.assertEqual([m["label"] for m in data["markers"]], ["Scroll"])
        self.assertLess(data["stop_ms"], data["requested_stop_ms"])  # ends when the phone was plugged back in

        with mock.patch.object(sys, "argv", ["powdroid", "--collect-pending"]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(), 0)
        self.assertIn("No session waiting to be collected.", out.getvalue())

    def test_cli_duration(self):
        started = time.monotonic()
        text, data = self.run_cli("duration", answers=[], duration=1.0, use_perfetto=False)
        self.assertGreater(time.monotonic() - started, 1.0)
        self.assertIn("Recording for 1s, until", text)
        self.assertEqual(self.waits, [("unplugged", "FAKE123"), ("connected", "FAKE123")])  # replugged over USB
        self.assertAlmostEqual((data["requested_stop_ms"] - data["requested_start_ms"]) / 1000, 1.0, delta=0.1)

    def use_wifi(self):
        patcher = mock.patch.dict(os.environ, FAKE_ADB_WIRELESS="1")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.set_state("device")

    def test_cli_over_wifi(self):
        self.use_wifi()
        text, data = self.run_cli("wifi", answers=["", "Scroll", ""])
        self.assertIn("Using Google Pixel 8 (fake) (Android 15, 192.168.1.20:5555).", text)
        self.assertIn("Unplug the phone from its charger: it stays connected over Wi-Fi.", text)
        self.assertEqual(self.waits, [("on battery", "192.168.1.20:5555")])  # never unplugged nor replugged
        self.assertEqual((data["transport"], data["current_source"]), ("wifi", "perfetto"))
        self.assertIn(session.WIFI_NOTE, data["warnings"])
        self.assertEqual([p["label"] for p in data["phases"]], ["Start", "Scroll"])
        rows = metrics.read_csv(next((self.dir / "wifi").glob("PowDroid_*.csv")))
        self.assertFalse(any(r["plugged"] for r in rows))  # the battery history saw it unplugged
        self.assertTrue(any(r["current_ma"] is not None for r in rows))

    def test_cli_unattended_over_wifi(self):
        self.use_wifi()
        (self.dir / "device" / "power").write_text("0")  # already on battery: starts at once
        text, data = self.run_cli("unattended", answers=[], duration=1.0)
        self.assertIn("The phone is running on battery.", text)
        self.assertEqual(self.waits, [])
        self.assertEqual(data["transport"], "wifi")

    def test_connect(self):
        self.assertEqual(adb.connect("192.168.1.20:5555"), "192.168.1.20:5555")
        self.assertIn("Successfully paired", adb.pair("192.168.1.20:37000", "123456"))
        with self.assertRaisesRegex(adb.AdbError, "Cannot pair with 192.168.1.20:37000: Failed: Wrong password"):
            adb.pair("192.168.1.20:37000", "000000")
        with mock.patch.dict(os.environ, FAKE_ADB_CONNECT_FAIL="1"):
            with self.assertRaisesRegex(adb.AdbError, "Cannot connect to 10.0.0.9:5555: failed to connect"):
                adb.connect("10.0.0.9:5555")
        with mock.patch.object(adb.time, "sleep"):
            self.assertEqual(adb.switch_to_wifi("FAKE123"), "192.168.1.20:5555")
        self.assertEqual(adb.battery_status("FAKE123"), adb.BatteryStatus(True, 3000000, 90))

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
        from powdroid.__main__ import main

        for argv, expected in ((["-o", "csv"], True), (["--no-perfetto"], False)):
            with mock.patch.object(sys, "argv", ["powdroid.py", *argv]), \
                    mock.patch("powdroid.cli.cli.main", return_value=0) as cli_main:
                self.assertEqual(main(), 0)
            self.assertIs(cli_main.call_args.args[5], expected)

    def test_clock_offset_with_seconds_only_date(self):
        with mock.patch.dict(os.environ, FAKE_ADB_SECONDS_ONLY="1"):
            self.assertAlmostEqual(adb.clock_offset_ms("FAKE123"), 30000, delta=100)


if __name__ == "__main__":
    unittest.main()
