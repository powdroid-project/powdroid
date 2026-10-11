"""The collection and processing pipeline shared by the CLI and the GUI.

A session produces, next to each other: PowDroid_<date>.csv (the rows),
PowDroid_<date>.json (device, session span, summary, warnings) and optionally
PowDroid_<date>.html.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core import PowDroidError, __version__, adb, history, html_report, metrics

MAX_UNCERTAINTY_PCT = 5  # i.e. at least 20 mAh consumed, given the 1 mAh counter resolution


class NoDataError(PowDroidError):
    """Raised when the dump cannot produce energy figures for the recorded session."""


@dataclass
class Result:
    """A processed session: its rows and what was concluded from them."""

    csv_path: Path
    rows: list
    summary: metrics.Summary
    warnings: list = field(default_factory=list)
    html_path: Path = None

    @property
    def json_path(self):
        return self.csv_path.with_suffix(".json")


def collect(device, start, stop, out_dir, html=False, report=lambda step: None):
    """After a session, read the battery statistics from the device and write the reports.

    start and stop are host datetimes; they are converted to device time using the
    device clock offset measured now. report(step) is called with "offset", "dump"
    and "parse" as the work progresses. Returns a Result.
    """
    report("offset")
    offset = adb.clock_offset_ms(device.serial)
    to_device_ms = lambda dt: int(dt.timestamp() * 1000) + offset  # noqa: E731
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir).expanduser()
    dump_path = out_dir / "dump" / f"batterystats_{stamp}.txt"
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    report("dump")
    dump_ms = to_device_ms(datetime.now())
    adb.dump_batterystats(device.serial, dump_path)
    report("parse")
    meta = {"device": {k: v for k, v in asdict(device).items() if k != "state"},
            "clock_offset_ms": offset}
    return process(dump_path, to_device_ms(start), to_device_ms(stop),
                   out_dir / f"PowDroid_{stamp}.csv", html=html, meta=meta, dump_ms=dump_ms)


def unplugged_span(hist, start_ms, stop_ms):
    """Shrink [start_ms, stop_ms] so that it neither starts nor ends while plugged in.

    The time before the phone is unplugged, or after it is plugged back in, is charging
    time, not part of the measurement. Plugging in the middle of a session is kept and
    reported (those rows have no energy).
    """
    for p in hist.intervals["plugged"]:
        if p.start <= start_ms < p.end:
            start_ms = min(p.end, stop_ms)
        if p.start < stop_ms <= p.end:
            stop_ms = max(p.start, start_ms)
    return start_ms, stop_ms


def charge_update_interval_s(hist, start_ms, stop_ms):
    """Average time between the phone's battery charge readings, around the session."""
    spans = [iv for iv in hist.intervals["charge_mah"] if iv.start < stop_ms and iv.end > start_ms]
    return sum(iv.end - iv.start for iv in spans) / len(spans) / 1000 if spans else None


def check(hist, requested, measured, summary):
    """Return the warnings about the reliability of the results.

    requested is the (start, stop) asked for, measured its unplugged part.
    """
    (requested_start, requested_stop), (start_ms, stop_ms) = requested, measured
    warnings = []
    trimmed = []
    if start_ms - requested_start >= 1000:
        trimmed.append(f"the first {(start_ms - requested_start) / 1000:.0f} s")
    if requested_stop - stop_ms >= 1000:
        trimmed.append(f"the last {(requested_stop - stop_ms) / 1000:.0f} s")
    if trimmed:
        warnings.append(f"The phone was still plugged in during {' and '.join(trimmed)} of the session: "
                        "that time was left out.")
    if hist.overflow_ms is not None and hist.overflow_ms < stop_ms:
        lost = (stop_ms - max(hist.overflow_ms, start_ms)) / 1000
        warnings.append(f"The device's battery history buffer overflowed: the last {lost:.0f} s "
                        "of the session have no data. Record shorter sessions.")
    if hist.start_ms is not None and requested_start < hist.start_ms:
        warnings.append("The session starts before the battery statistics were reset.")
    if hist.end_ms is not None and requested_stop > hist.end_ms:
        warnings.append("The session ends after the battery statistics were read: "
                        "check the device and computer clocks.")
    if summary.plugged_s:
        warnings.append(f"The phone was plugged in for {summary.plugged_s:.0f} s during the session: "
                        "no energy is reported for that time.")
    if summary.uncertainty_pct is None or summary.uncertainty_pct > MAX_UNCERTAINTY_PCT:
        warnings.append(f"Only {summary.charge_mah:.1f} mAh were consumed: with the coulomb counter's "
                        f"1 mAh resolution, energy and power are only known to about "
                        f"±{summary.uncertainty_pct or 100:.0f} %. Record a longer session "
                        f"(at least {100 / MAX_UNCERTAINTY_PCT:.0f} mAh for ±{MAX_UNCERTAINTY_PCT} %).")
    update_s = charge_update_interval_s(hist, start_ms, stop_ms)
    if update_s and update_s > (stop_ms - start_ms) / 3000:
        warnings.append(f"The phone updated its battery charge reading only every {update_s:.0f} s on "
                        "average: power values are averages over such periods and cannot show "
                        "shorter variations.")
    return warnings


def process(dump_path, start_ms, stop_ms, csv_path, html=False, meta=None, dump_ms=None):
    """Parse a batterystats dump and write the CSV, the session JSON and optionally the HTML report.

    start_ms, stop_ms and dump_ms (when the dump was taken) are in device time.
    """
    hist = history.parse_file(dump_path, end_ms=dump_ms)
    if not hist.has_coulomb:
        raise NoDataError("This device does not report its battery coulomb counter, "
                          "so its energy consumption cannot be measured.")
    measured = unplugged_span(hist, start_ms, stop_ms)
    rows = metrics.compute_rows(hist, *measured)
    summary = metrics.summarize(rows)
    if not summary.measured_s:
        raise NoDataError("No battery data found for the recorded session. Make sure the phone "
                          "stays unplugged and the session lasts long enough for the battery charge to drop.")

    result = Result(Path(csv_path), rows, summary, check(hist, (start_ms, stop_ms), measured, summary))
    result.csv_path.parent.mkdir(parents=True, exist_ok=True)
    metrics.write_csv(rows, result.csv_path)
    session = {
        "powdroid_version": __version__,
        "csv_format": 3,
        **(meta or {}),
        "requested_start_ms": start_ms,
        "requested_stop_ms": stop_ms,
        "start_ms": measured[0],
        "stop_ms": measured[1],
        "dump_ms": dump_ms,
        "dump_file": str(dump_path),
        "charge_update_interval_s": charge_update_interval_s(hist, *measured),
        "summary": asdict(summary),
        "warnings": result.warnings,
    }
    result.json_path.write_text(json.dumps(session, indent=2), encoding="utf-8")
    if html:
        result.html_path = html_report.write(result)
    return result


def load(csv_path):
    """Read a session back from its CSV, with the warnings of its JSON file when there is one."""
    rows = metrics.read_csv(csv_path)
    result = Result(Path(csv_path), rows, metrics.summarize(rows))
    try:
        result.warnings = json.loads(result.json_path.read_text(encoding="utf-8"))["warnings"]
    except FileNotFoundError:
        pass  # a CSV without its session file: no warnings to show
    except (OSError, ValueError, KeyError) as e:
        result.warnings = [f"The session file {result.json_path.name} could not be read ({e}): "
                           "its reliability warnings are not shown."]
    return result
