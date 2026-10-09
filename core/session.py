"""The collection and processing pipeline shared by the CLI and the GUI."""

import time
from datetime import datetime
from pathlib import Path

from core import PowDroidError, adb, history, html_report, metrics


class NoDataError(PowDroidError):
    """Raised when the bugreport has no battery events within the recorded session."""


def collect(serial, start, stop, out_dir, html=False, report=lambda step: None):
    """After a session, pull the bugreport from the device and write the reports.

    start and stop are host datetimes; they are converted to device time using the
    device clock offset measured now. report(step) is called with "offset", "bugreport"
    and "parse" as the work progresses. Returns the list of written paths.
    """
    report("offset")
    offset = adb.device_time_ms(serial) - int(time.time() * 1000)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir).expanduser()
    bugreport_path = out_dir / "dump" / f"bugreport_{stamp}.zip"
    bugreport_path.parent.mkdir(parents=True, exist_ok=True)
    report("bugreport")
    adb.bugreport(serial, bugreport_path)
    report("parse")
    to_device_ms = lambda dt: int(dt.timestamp() * 1000) + offset  # noqa: E731
    return process(bugreport_path, to_device_ms(start), to_device_ms(stop),
                   out_dir / f"PowDroid_{stamp}.csv", html=html)


def process(bugreport_path, start_ms, stop_ms, csv_path, html=False):
    """Parse a bugreport and write the CSV (and optionally the HTML report) for [start_ms, stop_ms].

    start_ms and stop_ms must be in device time. Returns the list of written paths.
    """
    intervals = history.parse_bugreport(bugreport_path)
    rows = metrics.compute_rows(intervals, start_ms, stop_ms)
    if not rows:
        raise NoDataError(
            "No battery data found for the recorded session. Make sure the session "
            "lasted long enough for the battery level to change."
        )
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    metrics.write_csv(rows, csv_path)
    written = [csv_path]
    if html:
        written.append(html_report.write(csv_path))
    return written
