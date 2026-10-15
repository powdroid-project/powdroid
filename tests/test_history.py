import tempfile
import unittest
from pathlib import Path

from powdroid.core import history
from tests.fixtures import HISTORY, LEVEL_HISTORY, OUT_OF_ORDER_HISTORY, T0


def spans(hist, metric):
    return [(iv.start - T0, iv.end - T0, iv.value) for iv in hist.intervals[metric]]


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.h = history.parse_history(HISTORY)

    def test_bounds(self):
        self.assertEqual((self.h.start_ms - T0, self.h.end_ms - T0), (0, 75000))
        self.assertIsNone(self.h.overflow_ms)
        self.assertTrue(self.h.has_coulomb)

    def test_int_steps(self):
        self.assertEqual(spans(self.h, "voltage_mv"), [(0, 5000, 4000), (5000, 35000, 3990), (35000, 75000, 3980)])
        self.assertEqual(spans(self.h, "battery_level_pct"), [(0, 35000, 90), (35000, 75000, 89)])
        self.assertEqual(spans(self.h, "temperature_c"), [(0, 75000, 25.0)])
        self.assertEqual(spans(self.h, "charge_mah")[:2], [(0, 15000, 3000), (15000, 35000, 2999)])

    def test_bools(self):
        self.assertEqual(spans(self.h, "screen"), [(0, 35000, True)])
        self.assertEqual(spans(self.h, "gps"), [(5000, 15000, True)])
        self.assertEqual(spans(self.h, "plugged"), [(45000, 55000, True)])
        self.assertEqual(spans(self.h, "camera"), [])

    def test_services_use_string_pool(self):
        self.assertEqual(spans(self.h, "top_app"),
                         [(0, 15000, "com.example.app"), (15000, 75000, "com.other.app")])
        self.assertEqual(spans(self.h, "wakelock"),
                         [(5000, 15000, "*alarm*"), (10000, 20000, "*job*/com.example.app/.Sync")])

    def test_orphan_minus_starts_at_reset(self):
        h = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,1000,-a\n")
        self.assertEqual(spans(h, "audio"), [(0, 1000, True)])

    def test_overflow_is_recorded(self):
        h = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,0,+ca\n9,h,10:*OVERFLOW*\n9,h,1000,-ca\n")
        self.assertEqual(h.overflow_ms, T0)
        self.assertEqual(spans(h, "camera"), [(0, 0, True)])

    def test_time_jump_is_aligned_to_last_clock(self):
        # The clock jumps +60s at the second TIME line; earlier events are shifted to match it.
        text = f"9,h,0:RESET:TIME:{T0}\n9,h,1000,+ca\n9,h,1000:TIME:{T0 + 62000}\n9,h,1000,-ca\n"
        self.assertEqual(spans(history.parse_history(text), "camera"), [(61000, 63000, True)])

    def test_no_coulomb_counter(self):
        h = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bcc=0,Bv=4000\n9,h,1000,Bv=3999\n")
        self.assertFalse(h.has_coulomb)
        h = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bcc=-2147483,Bv=4000\n")
        self.assertFalse(h.has_coulomb)

    def test_negative_coulomb_counter(self):
        # Offset counters can be negative: they still count as long as they move.
        h = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bcc=-2\n9,h,1000,Bcc=-3\n")
        self.assertTrue(h.has_coulomb)
        self.assertEqual(spans(h, "charge_mah"), [(0, 1000, -2), (1000, 1000, -3)])

    def test_battery_capacity(self):
        self.assertIsNone(self.h.capacity_mah)  # no power use summary
        self.assertEqual(history.parse_history(LEVEL_HISTORY).capacity_mah, 3000)
        h = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,0,Bl=50\n9,0,l,pws,0,0,0,0\n")
        self.assertIsNone(h.capacity_mah)

    def test_records_written_out_of_order(self):
        # "9,h,-20,-BP": unplugged 20 ms before the previous record, applied right after it.
        h = history.parse_history(OUT_OF_ORDER_HISTORY)
        self.assertEqual(spans(h, "plugged"), [(0, 5000, True), (165000, 165000, True)])
        self.assertEqual(spans(h, "charge_mah")[1:3], [(35000, 95000, 1198), (95000, 155000, 1175)])
        self.assertEqual(h.end_ms - T0, 165000)

    def test_debug_log_shows_out_of_order_and_unreadable_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "batterystats.txt"
            path.write_text(OUT_OF_ORDER_HISTORY + "9,h,oops\n")
            with self.assertLogs("powdroid.history", "DEBUG") as logs:
                history.parse_file(path)
        text = "\n".join(logs.output)
        self.assertIn("1 out of order (up to 20 ms early)", text)
        self.assertIn("h (unreadable) 1", text)
        self.assertIn("| 9,h,oops", text)

    def test_tags_written_in_full(self):
        # Android 15+: a tag that does not fit in the string pool is written as uid:"name".
        h = history.parse_history(f"""\
9,h,0:RESET:TIME:{T0}
9,h,0,+Etp=10100:"com.example.app",+Ewl=1000:"*alarm*"
9,h,1000,-Ewl=1000:"*alarm*"
9,h,1000,-Etp=10100:"com.example.app"
""")
        self.assertEqual([(iv.start - T0, iv.end - T0, iv.value) for iv in h.intervals["top_app"]],
                         [(0, 2000, "com.example.app")])
        self.assertEqual([(iv.start - T0, iv.end - T0, iv.value) for iv in h.intervals["wakelock"]],
                         [(0, 1000, "*alarm*")])

    def test_no_history(self):
        with self.assertRaises(history.HistoryError):
            history.parse_history("nothing here")

    def test_parse_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "batterystats.txt"
            path.write_text(HISTORY)
            self.assertEqual(spans(history.parse_file(path), "gps"), [(5000, 15000, True)])


if __name__ == "__main__":
    unittest.main()
