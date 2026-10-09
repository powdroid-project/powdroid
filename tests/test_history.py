import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from core import history
from tests.fixtures import HISTORY, T0


def spans(intervals, metric):
    return [(iv.start - T0, iv.end - T0, iv.value) for iv in intervals[metric]]


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.iv = history.parse_history(HISTORY)

    def test_int_steps(self):
        self.assertEqual(spans(self.iv, "Voltage"), [(0, 5000, 4000), (5000, 35000, 3990), (35000, 45000, 3980)])
        self.assertEqual(spans(self.iv, "Coulomb charge"),
                         [(0, 15000, 3000), (15000, 35000, 2999), (35000, 45000, 2997), (45000, 45000, 2996)])

    def test_bools(self):
        self.assertEqual(spans(self.iv, "Screen"), [(0, 35000, True)])
        self.assertEqual(spans(self.iv, "GPS"), [(5000, 15000, True)])
        self.assertEqual(spans(self.iv, "Wifi on"), [(35000, 45000, True)])
        self.assertEqual(spans(self.iv, "Camera"), [])

    def test_services_use_string_pool(self):
        self.assertEqual(spans(self.iv, "Top app"),
                         [(0, 15000, "com.example.app"), (15000, 45000, "com.other.app")])
        self.assertEqual(spans(self.iv, "Wakelock_in"), [(5000, 15000, "*alarm*")])

    def test_lines_outside_checkin_section_ignored(self):
        self.assertNotIn(1, [iv.value for iv in self.iv["Voltage"]])

    def test_orphan_minus_starts_at_reset(self):
        iv = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,1000,-a\n")
        self.assertEqual(spans(iv, "Audio"), [(0, 1000, True)])

    def test_overflow_stops_parsing(self):
        iv = history.parse_history(f"9,h,0:RESET:TIME:{T0}\n9,h,0,+ca\n9,h,10:*OVERFLOW*\n9,h,1000,-ca\n")
        self.assertEqual(spans(iv, "Camera"), [(0, 0, True)])

    def test_time_jump_is_aligned_to_last_clock(self):
        # The clock jumps +60s at the second TIME line; earlier events are shifted to match it.
        text = f"9,h,0:RESET:TIME:{T0}\n9,h,1000,+ca\n9,h,1000:TIME:{T0 + 62000}\n9,h,1000,-ca\n"
        iv = history.parse_history(text)
        self.assertEqual(spans(iv, "Camera"), [(61000, 63000, True)])

    def test_no_history(self):
        with self.assertRaises(history.HistoryError):
            history.parse_history("nothing here")

    def test_read_zip_main_entry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "br.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("main_entry.txt", "bugreport-x.txt")
                z.writestr("bugreport-x.txt", HISTORY)
                z.writestr("bugreport-big-other.txt", "x" * 100000)
            self.assertEqual(spans(history.parse_bugreport(path), "GPS"), [(5000, 15000, True)])


if __name__ == "__main__":
    unittest.main()
