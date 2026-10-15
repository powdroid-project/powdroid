import json
import re
import tempfile
import unittest
from pathlib import Path

from powdroid.core import metrics, session
from tests.fixtures import (
    FROZEN_COUNTER_HISTORY, HISTORY, LEVEL_COUNTER_HISTORY, LEVEL_HISTORY, OUT_OF_ORDER_HISTORY, T0,
)


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
        self.assertIn("This phone does not report its battery coulomb counter: current, power and energy are "
                      "estimated from the battery level drops, counting each 1 % as 30 mAh, 1 % of the battery "
                      "capacity reported by Android (3000 mAh). They are only known between the first and last "
                      "level drops, and are overestimated if the battery has worn", text)
        self.assertIn("Only 60 mAh (2 % of the battery) were measured: with the battery level's 1 % "
                      "resolution, energy and power are only known to about ±50 %", text)
        self.assertIn("a level drop of at least 20 % for ±5 %", text)
        self.assertNotIn("coulomb counter's 1 mAh", text)
        data = json.loads(result.json_path.read_text())
        self.assertEqual((data["current_source"], data["battery_capacity_mah"], data["battery_capacity_source"]),
                         ("battery_level", 3000, "reported"))

    def test_learned_capacity_is_preferred(self):
        # bt: ..., estimated capacity 2900 mAh, learned capacities 2700000 to 2850000 µAh, ...
        text = LEVEL_HISTORY + "9,0,l,bt,0,1,2,3,4,5,6,7,2900,2700000,2850000,0\n"
        result = self.run_process(text, 0, 150000)
        self.assertAlmostEqual(result.summary.charge_mah, 57)  # two 1 % drops of 2850 mAh
        self.assertIn("1 % of the battery capacity learned by the fuel gauge (2850 mAh). They are only known "
                      "between the first and last level drops.", " ".join(result.warnings))
        for bt, expected in (("2900,-1,-1", (2900, "estimated")), ("-1,-1,-1", (3000, "reported"))):
            text = LEVEL_HISTORY + f"9,0,l,bt,0,1,2,3,4,5,6,7,{bt},0\n"
            data = json.loads(self.run_process(text, 0, 150000).json_path.read_text())
            self.assertEqual((data["battery_capacity_mah"], data["battery_capacity_source"]), expected)
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


class CounterTest(unittest.TestCase):
    def run_process(self, text, start, stop):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        dump = Path(d.name) / "dump.txt"
        dump.write_text(text)
        return session.process(dump, T0 + start, T0 + stop, Path(d.name) / "PowDroid_x.csv")

    def test_counter_following_the_level(self):
        result = self.run_process(LEVEL_COUNTER_HISTORY, 0, 160_000)
        data = json.loads(result.json_path.read_text())
        self.assertEqual(data["current_source"], "coulomb_counter")
        self.assertEqual((data["charge_resolution_mah"], data["counter_follows_level"]), (44.0, True))
        self.assertTrue(any("only changes when the battery level does, by about 44 mAh" in w
                            for w in result.warnings))
        # 3 steps of 44-45 mAh: about ±33 %, so a longer session is asked for.
        self.assertTrue(any("±33 %" in w and "coulomb counter's 44 mAh resolution" in w for w in result.warnings))

    def test_frozen_counter_falls_back_to_the_level(self):
        result = self.run_process(FROZEN_COUNTER_HISTORY, 0, 150_000)
        self.assertEqual(result.summary.current_source, "battery_level")
        self.assertIn("The battery's charge counter did not change while the phone was unplugged (it stayed at "
                      "2500 mAh): the energy is estimated from the battery level drops instead.", result.warnings)
        self.assertAlmostEqual(result.summary.charge_mah, 60, places=6)  # two 1 % drops of 3000 mAh


class MarkerTest(unittest.TestCase):
    def test_markers_and_renaming(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        dump = Path(d.name) / "dump.txt"
        dump.write_text(HISTORY)
        markers = [{"time_ms": T0 + 60000, "label": "Video"}, {"time_ms": T0 + 20000, "label": "Scroll"}]
        result = session.process(dump, T0, T0 + 70000, Path(d.name) / "PowDroid_x.csv", html=True, markers=markers)
        self.assertEqual([(p["label"], p["marker"]) for p in result.phases],
                         [("Start", None), ("Scroll", 1), ("Video", 0)])
        session.rename_marker(result, 1, "Scrolling")
        saved = json.loads(result.json_path.read_text())
        self.assertEqual([m["label"] for m in saved["markers"]], ["Video", "Scrolling"])
        self.assertEqual([p["label"] for p in saved["phases"]], ["Start", "Scrolling", "Video"])
        self.assertIn("Scrolling", result.html_path.read_text())
        loaded = session.load(result.csv_path)
        self.assertEqual([p["label"] for p in loaded.phases], ["Start", "Scrolling", "Video"])
