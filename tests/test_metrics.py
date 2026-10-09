import tempfile
import unittest
from pathlib import Path

from core import history, html_report, metrics, session
from tests.fixtures import HISTORY, T0

ORIGINAL_COLUMNS = [
    "start_time", "end_time", "Duration (mS)", "Voltage (mV)", "Remaining_charge (mAh)",
    "Intensity (mA)", "Power (W)", "Consumed charge(mAh)", "Energy (J)", "Top app",
    "Screen(ON/OFF)", "GPS(ON/OFF)", "Mobile_Radio(ON/OFF)", "WiFi(ON/OFF)", "Wifi radio",
    "Camera(ON/OFF)", "Video (ON/OFF)", "Audio(ON/OFF)", "Wakelock_in (Service)",
]


class MetricsTest(unittest.TestCase):
    def setUp(self):
        self.rows = metrics.compute_rows(history.parse_history(HISTORY), T0, T0 + 45000)

    def test_columns_unchanged(self):
        self.assertEqual(metrics.COLUMNS, ORIGINAL_COLUMNS)

    def test_segments(self):
        self.assertEqual([(r["start_time"] - T0, r["end_time"] - T0) for r in self.rows],
                         [(0, 5000), (5000, 15000), (15000, 35000), (35000, 45000)])

    def test_values(self):
        r = self.rows[1]  # 5s..15s: 3990 mV, coulomb 3000 -> 2999 over 15 s => 240 mA
        self.assertEqual(r["Voltage (mV)"], 3990)
        self.assertEqual(r["Remaining_charge (mAh)"], 3000)
        self.assertAlmostEqual(r["Intensity (mA)"], 240.0)
        self.assertAlmostEqual(r["Power (W)"], 3.99 * 0.24)
        self.assertAlmostEqual(r["Energy (J)"], 3.99 * 0.24 * 10)
        self.assertAlmostEqual(r["Consumed charge(mAh)"], 240 * 10 / 3600)
        self.assertEqual(r["Top app"], "com.example.app")
        self.assertEqual(r["Wakelock_in (Service)"], "*alarm*")
        self.assertTrue(r["GPS(ON/OFF)"] and r["Screen(ON/OFF)"])
        self.assertFalse(r["WiFi(ON/OFF)"])

    def test_last_coulomb_has_no_intensity(self):
        last = self.rows[-1]  # Bcc 2997 -> 2996 over 10 s
        self.assertAlmostEqual(last["Intensity (mA)"], 360.0)
        self.assertIsNone(last["Top app"])
        self.assertTrue(last["WiFi(ON/OFF)"])

    def test_window_filter(self):
        rows = metrics.compute_rows(history.parse_history(HISTORY), T0 + 6000, T0 + 40000)
        self.assertEqual([(r["start_time"] - T0) for r in rows], [15000])

    def test_roundtrip_summary_and_html(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.csv"
            metrics.write_csv(self.rows, path)
            rows = metrics.read_csv(path)
            self.assertEqual(len(rows), 4)
            s = metrics.summarize(rows)
            self.assertAlmostEqual(s.energy_j, sum(r["Energy (J)"] for r in self.rows), places=4)
            self.assertEqual(s.duration_s, 45)
            self.assertIn("Top app", html_report.generate(path))

    def test_html_escapes_script(self):
        text = HISTORY.replace("com.example.app", "</script><b>x")
        rows = metrics.compute_rows(history.parse_history(text), T0, T0 + 45000)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.csv"
            metrics.write_csv(rows, path)
            page = html_report.generate(path)
            self.assertNotIn("</script><b>", page)

    def test_session_no_data(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "br.txt"
            src.write_text(HISTORY)
            with self.assertRaises(session.NoDataError):
                session.process(src, T0 + 100_000, T0 + 200_000, Path(d) / "x.csv")
            written = session.process(src, T0, T0 + 45000, Path(d) / "x.csv", html=True)
            self.assertEqual([p.suffix for p in written], [".csv", ".html"])


if __name__ == "__main__":
    unittest.main()
