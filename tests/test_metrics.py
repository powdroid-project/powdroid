import tempfile
import unittest
from pathlib import Path

from powdroid.core import history, html_report, metrics, session
from tests.fixtures import HISTORY, LEVEL_HISTORY, T0

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
        # 48 of the 58 unplugged seconds are measured: the mean power over all 58 s.
        self.assertAlmostEqual(s.extrapolated_energy_j, s.mean_power_w * 58)
        self.assertEqual(metrics.summary_items(s)["extrapolated"],
                         metrics.format_energy(s.mean_power_w * 58) + " ± 21 %")
        measured = [r for r in self.rows if r["power_w"] is not None]
        self.assertIsNone(metrics.summarize(measured[:2]).extrapolated_energy_j)  # fully measured

    def test_current_from_the_battery_level_without_coulomb_counter(self):
        hist = history.parse_history(LEVEL_HISTORY)
        source = metrics.charge_source(hist)
        self.assertEqual((source.name, source.resolution_mah), (metrics.LEVEL, 30))
        # The level held since the reset is a partial step; 83 % re-logged at 70 s is the same reading.
        self.assertEqual([(iv.start - T0, iv.end - T0, iv.value) for iv in source.readings],
                         [(30000, 90000, 2490), (90000, 120000, 2460), (120000, 150000, 2430)])
        rows = metrics.compute_rows(hist, T0 + 10000, T0 + 150000)
        self.assertEqual(rel(rows), [(10000, 30000), (30000, 70000), (70000, 90000), (90000, 120000),
                                     (120000, 150000)])
        self.assertEqual([r["current_ma"] for r in rows], [None, 1800, 1800, 3600, None])
        self.assertTrue(all(r["charge_mah"] is None for r in rows))  # no coulomb counter
        self.assertEqual(rows[0]["battery_level_pct"], 84)
        s = metrics.summarize(rows, source.name, source.resolution_mah)
        self.assertAlmostEqual(s.charge_mah, 60)
        self.assertEqual((s.measured_s, s.uncertainty_pct, s.current_source), (90, 50, metrics.LEVEL))

    def test_no_current_across_a_gap_in_the_readings(self):
        # A reboot from 20 s to 30 s: the 99 mAh reading has no following one.
        text = (f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bcc=100\n9,h,10000,Bcc=99\n9,h,10000,+S\n"
                f"9,h,5000:START\n9,h,0:TIME:{T0 + 30000}\n9,h,0,Bcc=90\n9,h,10000,Bcc=89\n9,h,10000,Bcc=88\n")
        rows = metrics.compute_rows(history.parse_history(text), T0, T0 + 50000)
        currents = {r["start_ms"] - T0: r["current_ma"] for r in rows}
        self.assertEqual(currents, {0: 360, 10000: None, 20000: None, 30000: 360, 40000: 360})

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
        hist = history.parse_history(HISTORY.replace("com.example.app", "<!--<script></script><b>x__ROWS__"))
        rows = metrics.compute_rows(hist, T0, T0 + 70000)
        result = session.Result(Path("out.csv"), rows, metrics.summarize(rows), ["Plugged <in>"])
        page = html_report.generate(result)
        self.assertNotIn("<!--<script>", page)
        self.assertNotIn("</script><b>", page)
        escaped = "\\u003c!--\\u003cscript\\u003e\\u003c/script\\u003e\\u003cb\\u003ex__ROWS__"
        self.assertIn(escaped, page)  # and __ROWS__ is not replaced
        self.assertIn("Plugged &lt;in&gt;", page)

    def test_html_is_self_contained(self):
        result = session.Result(Path("out.csv"), self.rows, metrics.summarize(self.rows))
        page = html_report.generate(result)
        self.assertNotIn("<script src", page)
        self.assertNotIn("sourceMappingURL", page)
        self.assertIn("Chart.js v4.5.1", page)
        self.assertEqual(page.count("<script>"), 2)  # Chart.js and the page's own
        self.assertIn("decimation", page)
        self.assertIn("<h2>Measurement</h2>", page)
        self.assertIn("<td>Coulomb counter (1 mAh steps)</td>", page)

    def test_phases_between_markers(self):
        markers = [{"time_ms": T0 + 20000, "label": "Scroll"}, {"time_ms": T0 + 60000, "label": "Video"},
                   {"time_ms": T0 + 99000, "label": "after the end"}]
        phases = metrics.phase_summaries(self.rows, markers)
        self.assertEqual([(p["label"], p["start_ms"] - T0, p["end_ms"] - T0) for p in phases],
                         [("Start", 2000, 20000), ("Scroll", 20000, 60000), ("Video", 60000, 70000)])
        self.assertAlmostEqual(sum(p["energy_j"] for p in phases), metrics.summarize(self.rows).energy_j)
        # Plugged in from 45 to 55 s, then no current until the next counter reading at 65 s.
        self.assertEqual([p["measured_s"] for p in phases], [18, 25, 5])
        self.assertEqual(metrics.phase_summaries(self.rows, []), [])
        self.assertEqual(metrics.phase_rows(phases)[1][:3], ["Scroll", "18s", "40s"])


if __name__ == "__main__":
    unittest.main()
