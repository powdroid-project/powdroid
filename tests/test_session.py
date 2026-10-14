import json
import re
import tempfile
import unittest
from pathlib import Path

from core import metrics, session
from tests.fixtures import HISTORY, LEVEL_HISTORY, OUT_OF_ORDER_HISTORY, T0


class SessionTest(unittest.TestCase):
    def run_process(self, text, start, stop, **kw):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        dump = Path(d.name) / "dump.txt"
        dump.write_text(text)
        return session.process(dump, T0 + start, T0 + stop, Path(d.name) / "PowDroid_x.csv", **kw)

    def test_outputs_and_json(self):
        result = self.run_process(HISTORY, 0, 70000, html=True, meta={"device": {"model": "Pixel"}})
        self.assertTrue(result.csv_path.exists() and result.html_path.exists())
        data = json.loads(result.json_path.read_text())
        self.assertEqual(data["csv_format"], 3)
        self.assertEqual(data["device"], {"model": "Pixel"})
        self.assertEqual(data["start_ms"], T0)
        self.assertEqual(data["summary"]["plugged_s"], 10)
        self.assertEqual(data["warnings"], result.warnings)
        loaded = session.load(result.csv_path)
        self.assertEqual((loaded.warnings, len(loaded.rows)), (result.warnings, len(result.rows)))
        self.assertAlmostEqual(loaded.summary.energy_j, result.summary.energy_j, places=6)

    def test_load_without_or_with_broken_session_file(self):
        result = self.run_process(HISTORY, 0, 70000)
        result.json_path.unlink()
        self.assertEqual(session.load(result.csv_path).warnings, [])
        result.json_path.write_text("{not json")
        self.assertIn("could not be read", session.load(result.csv_path).warnings[0])

    def test_warnings(self):
        warnings = self.run_process(HISTORY, 0, 80000).warnings
        text = " ".join(warnings)
        self.assertIn("plugged in for 10 s", text)
        self.assertIn("only known to about ±17 %", text)  # 6 mAh consumed
        self.assertNotIn("updated its battery charge", text)  # 7 charge readings over 80 s
        self.assertIn("after the battery statistics were read", text)

    def test_states_hold_until_the_dump(self):
        result = self.run_process(HISTORY, 0, 90000, dump_ms=T0 + 95000)
        self.assertFalse(any("after the battery statistics" in w for w in result.warnings))
        last = metrics.read_csv(result.csv_path)[-1]
        self.assertEqual((last["end_ms"] - T0, last["voltage_mv"]), (90000, 3980))

    def test_short_unplugged_session(self):
        warnings = self.run_process(HISTORY, 0, 40000).warnings  # 3.5 mAh consumed
        self.assertFalse(any("plugged" in w for w in warnings))
        self.assertTrue(any("±29 %" in w for w in warnings))
        # Charge readings at 0, 15, 35 and 45 s: every 15 s on average, for a 40 s session.
        self.assertTrue(any("only every 15 s" in w for w in warnings))

    def test_plugged_edges_are_trimmed(self):
        # The phone is plugged in from 45 s to 55 s.
        result = self.run_process(HISTORY, 50000, 70000)
        data = json.loads(result.json_path.read_text())
        self.assertEqual((data["requested_start_ms"] - T0, data["start_ms"] - T0), (50000, 55000))
        self.assertEqual(result.summary.plugged_s, 0)
        self.assertTrue(any("during the first 5 s of the session" in w for w in result.warnings))

        result = self.run_process(HISTORY, 30000, 50000)
        self.assertEqual(json.loads(result.json_path.read_text())["stop_ms"] - T0, 45000)
        self.assertTrue(any("during the last 5 s of the session" in w for w in result.warnings))

    def test_overflow_warning(self):
        text = HISTORY.replace("9,h,5000,Bcc=2998\n", "9,h,5000:*OVERFLOW*\n")
        warnings = self.run_process(text, 0, 70000).warnings
        self.assertTrue(any("overflowed" in w for w in warnings))

    def test_no_coulomb_counter_nor_capacity(self):
        text = f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bv=4000\n9,h,60000,Bv=3990\n"
        with self.assertRaisesRegex(session.NoDataError, "has no charge counter.*capacity.*dump.txt"):
            self.run_process(text, 0, 60000)
        text = f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bv=4000,Bcc=0\n9,h,60000,Bv=3990\n"
        with self.assertRaisesRegex(session.NoDataError, "stays at 0 mAh"):
            self.run_process(text, 0, 60000)

    def test_estimate_from_the_battery_level(self):
        result = self.run_process(LEVEL_HISTORY, 0, 150000)
        self.assertEqual(result.summary.current_source, "battery_level")
        self.assertAlmostEqual(result.summary.charge_mah, 60)
        self.assertEqual((result.summary.measured_s, result.summary.uncertainty_pct), (90, 50))
        text = " ".join(result.warnings)
        self.assertIn("estimated from the battery level drops, counting each 1 % as 30 mAh "
                      "(of a 3000 mAh design capacity)", text)
        self.assertIn("Only 60 mAh (2 % of the battery) were measured: with the battery level's 1 % "
                      "resolution, energy and power are only known to about ±50 %", text)
        self.assertIn("a level drop of at least 20 % for ±5 %", text)
        self.assertNotIn("coulomb counter's 1 mAh", text)
        data = json.loads(result.json_path.read_text())
        self.assertEqual((data["current_source"], data["battery_capacity_mah"]), ("battery_level", 3000))
        self.assertEqual(data["charge_update_interval_s"], 40)  # level steps of 60, 30 and 30 s
        loaded = session.load(result.csv_path)  # the uncertainty needs the source, saved in the JSON
        self.assertEqual((loaded.summary.current_source, loaded.summary.uncertainty_pct), ("battery_level", 50))

    def test_battery_level_must_drop_twice(self):
        # Unplugged at 10 s, the level only drops at 30 s before the session stops at 25 s.
        with self.assertRaisesRegex(session.NoDataError, "level did not drop twice"):
            self.run_process(LEVEL_HISTORY, 0, 25000)

    def test_negative_coulomb_counter(self):
        # A counter with a negative offset gives the same results: only its changes matter.
        shifted = re.sub(r"Bcc=(\d+)", lambda m: f"Bcc={int(m.group(1)) - 5000}", HISTORY)
        expected, result = self.run_process(HISTORY, 0, 70000), self.run_process(shifted, 0, 70000)
        self.assertEqual([r["current_ma"] for r in result.rows], [r["current_ma"] for r in expected.rows])
        self.assertEqual(result.summary.energy_j, expected.summary.energy_j)
        self.assertEqual(result.rows[0]["charge_mah"], -2000)

    def test_unplug_written_out_of_order(self):
        # The unplug record has a negative time delta (Android 14+): it must not be lost, or
        # the phone looks plugged in during the whole session.
        result = self.run_process(OUT_OF_ORDER_HISTORY, 0, 160000)
        data = json.loads(result.json_path.read_text())
        self.assertEqual((data["start_ms"] - T0, data["stop_ms"] - T0), (5000, 160000))
        self.assertEqual(result.summary.measured_s, 120)
        self.assertAlmostEqual(result.summary.charge_mah, 41)

    def test_plugged_in_during_the_whole_session(self):
        with self.assertRaisesRegex(session.NoDataError, "stayed plugged in during the whole session"):
            self.run_process(HISTORY, 46000, 54000)  # plugged in from 45 s to 55 s

    def test_no_data_in_window(self):
        with self.assertRaises(session.NoDataError):
            self.run_process(HISTORY, 45000, 60000)  # only plugged / unknown rows


if __name__ == "__main__":
    unittest.main()
