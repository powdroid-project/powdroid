import tempfile
import unittest
from pathlib import Path

from core import history, html_report, metrics, session
from tests.fixtures import HISTORY, T0

V3_COLUMNS = [
    "start_ms", "end_ms", "elapsed_s", "duration_ms",
    "battery_level_pct", "voltage_mv", "charge_mah", "current_ma", "power_w", "energy_j", "consumed_mah",
    "temperature_c", "brightness",
    "plugged", "screen", "cpu_running", "wifi", "wifi_radio", "mobile_radio", "gps", "bluetooth",
    "camera", "video", "audio", "flashlight", "sensor", "battery_saver",
    "top_app", "wakelocks",
]


def rel(rows):
    return [(r["start_ms"] - T0, r["end_ms"] - T0) for r in rows]


class MetricsTest(unittest.TestCase):
    def setUp(self):
        self.hist = history.parse_history(HISTORY)
        self.rows = metrics.compute_rows(self.hist, T0 + 2000, T0 + 70000)
        self.by_start = {r["start_ms"] - T0: r for r in self.rows}

    def test_columns(self):
        self.assertEqual(metrics.COLUMNS, V3_COLUMNS)

    def test_rows_tile_the_session(self):
        self.assertEqual(rel(self.rows), [
            (2000, 5000), (5000, 10000), (10000, 15000), (15000, 20000), (20000, 35000),
            (35000, 45000), (45000, 50000), (50000, 55000), (55000, 65000), (65000, 70000)])
        self.assertEqual(sum(r["duration_ms"] for r in self.rows), 68000)
        self.assertEqual(self.rows[0]["elapsed_s"], 0)
        self.assertEqual(self.by_start[5000]["elapsed_s"], 3)

    def test_values(self):
        # Voltage read 3990 mV at 5 s and 3980 mV at 35 s: 3989 mV in the middle of 5-10 s.
        # Coulomb 3000 -> 2999 mAh over 15 s => 240 mA.
        r = self.by_start[5000]
        self.assertEqual(r["voltage_mv"], 3989)
        self.assertEqual(r["charge_mah"], 3000)
        self.assertEqual(r["battery_level_pct"], 90)
        self.assertEqual(r["temperature_c"], 25.0)
        self.assertEqual(r["brightness"], 2)
        self.assertAlmostEqual(r["current_ma"], 240.0)
        self.assertAlmostEqual(r["power_w"], 3.989 * 0.24)
        self.assertAlmostEqual(r["energy_j"], 3.989 * 0.24 * 5)
        self.assertAlmostEqual(r["consumed_mah"], 240 * 5 / 3600)
        self.assertEqual(r["top_app"], "com.example.app")
        self.assertTrue(r["gps"] and r["screen"])
        self.assertFalse(r["wifi"])

    def test_voltage_is_interpolated_between_readings_but_not_across_plugging(self):
        def voltages(text, start, stop):
            return [r["voltage_mv"] for r in metrics.compute_rows(history.parse_history(text), T0 + start, T0 + stop)]

        reset = f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bv=4000\n"
        self.assertEqual(voltages(reset + "9,h,10000,Bv=3900\n", 2000, 3000), [3975])
        # The 4200 mV reading is taken while charging: the 4000 mV reading is held until then.
        self.assertEqual(voltages(reset + "9,h,5000,+BP\n9,h,5000,Bv=4200\n", 2000, 3000), [4000])
        # After the last reading, it is held.
        self.assertEqual(voltages(reset + "9,h,10000,Bv=3900\n9,h,5000,+S\n", 11000, 12000), [3900])

    def test_all_wakelocks(self):
        self.assertEqual(self.by_start[10000]["wakelocks"], "*alarm*;*job*/com.example.app/.Sync")
        self.assertIsNone(self.by_start[20000]["wakelocks"])

    def test_top_app_only_with_screen_on(self):
        self.assertEqual(self.by_start[15000]["top_app"], "com.other.app")
        self.assertIsNone(self.by_start[35000]["top_app"])

    def test_no_energy_while_plugged(self):
        self.assertAlmostEqual(self.by_start[35000]["current_ma"], 360.0)
        for start in (45000, 50000, 55000):  # plugged, or coulomb interval spanning the replug
            r = self.by_start[start]
            self.assertIsNone(r["current_ma"])
            self.assertIsNone(r["energy_j"])
        self.assertTrue(self.by_start[45000]["plugged"])
        self.assertFalse(self.by_start[55000]["plugged"])
        self.assertAlmostEqual(self.by_start[65000]["current_ma"], 720.0)

    def test_summary(self):
        s = metrics.summarize(self.rows)
        self.assertEqual(s.duration_s, 68)
        self.assertEqual(s.plugged_s, 10)
        self.assertEqual(s.measured_s, 68 - 20)
        self.assertEqual((s.level_start_pct, s.level_end_pct), (90, 89))
        self.assertAlmostEqual(s.energy_j, sum(r["energy_j"] or 0 for r in self.rows))
        self.assertAlmostEqual(s.mean_power_w, s.energy_j / s.measured_s)
        self.assertAlmostEqual(s.mean_current_ma, s.charge_mah / (s.measured_s / 3600))

    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.csv"
            metrics.write_csv(self.rows, path)
            header, first = path.read_text().splitlines()[:2]
            self.assertEqual(header.split(","), V3_COLUMNS)
            self.assertNotIn("True", first)
            self.assertNotIn(".000000", first)
            back = metrics.read_csv(path)
            self.assertEqual(len(back), len(self.rows))
            for a, b in zip(back, self.rows):
                for c in V3_COLUMNS:
                    if isinstance(b[c], float):
                        self.assertAlmostEqual(a[c], b[c], places=6)
                    else:
                        self.assertEqual(a[c], b[c], c)

    def test_read_rejects_old_csv(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.csv"
            path.write_text("start_time,end_time,Energy (J)\n1,2,3\n")
            with self.assertRaises(metrics.CsvFormatError):
                metrics.read_csv(path)

    def test_html_escapes_and_shows_warnings(self):
        hist = history.parse_history(HISTORY.replace("com.example.app", "</script><b>x"))
        rows = metrics.compute_rows(hist, T0, T0 + 70000)
        result = session.Result(Path("out.csv"), rows, metrics.summarize(rows), ["Plugged <in>"])
        page = html_report.generate(result)
        self.assertNotIn("</script><b>", page)
        self.assertIn("Plugged &lt;in&gt;", page)


if __name__ == "__main__":
    unittest.main()
