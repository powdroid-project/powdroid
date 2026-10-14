"""The collection and processing pipeline shared by the CLI and the GUI.

A session produces, next to each other: PowDroid_<date>.csv (the rows),
PowDroid_<date>.json (device, session span, summary, warnings) and optionally
PowDroid_<date>.html.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core import PowDroidError, __version__, adb, debug, history, html_report, metrics

logger = logging.getLogger("powdroid.session")

MAX_UNCERTAINTY_PCT = 5  # i.e. at least 20 mAh consumed with the coulomb counter, or a 20 % level drop

# Shown before recording on phones whose battery does not report its coulomb counter.
NO_COULOMB_NOTICE = ("This phone does not report its battery coulomb counter: PowDroid will estimate the "
                     "energy from the battery level drops, which is much less precise. Record a long "
                     "session: the battery level should drop by at least 10 % (for about ±10 %), "
                     "or 20 % for ±5 %.")


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
    logger.info("Collecting the session recorded on %s from %s to %s (computer time) into %s",
                device.serial, start, stop, out_dir)
    report("offset")
    offset = adb.clock_offset_ms(device.serial)
    adb.log_diagnostics(device.serial, "after the session")
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


def charge_update_interval_s(readings, start_ms, stop_ms):
    """Average time between the battery charge readings (metrics.ChargeSource), around the session."""
    spans = [iv for iv in readings if iv.start < stop_ms and iv.end > start_ms]
    return sum(iv.end - iv.start for iv in spans) / len(spans) / 1000 if spans else None


def check(hist, requested, measured, summary, source):
    """Return the warnings about the reliability of the results.

    requested is the (start, stop) asked for, measured its unplugged part, and source the
    metrics.ChargeSource the current comes from.
    """
    (requested_start, requested_stop), (start_ms, stop_ms) = requested, measured
    level = source.name == metrics.LEVEL
    warnings = []
    if level:
        warnings.append(f"This phone does not report its battery coulomb counter: current, power and energy "
                        f"are estimated from the battery level drops, counting each 1 % as "
                        f"{source.resolution_mah:g} mAh (of a {hist.capacity_mah:g} mAh design capacity). "
                        "They are only known between the first and last level drops, and are overestimated "
                        "if the battery has worn and holds less than its design capacity.")
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
        steps = 100 / MAX_UNCERTAINTY_PCT
        if level:
            consumed = (f"{summary.charge_mah:.0f} mAh ({summary.charge_mah / source.resolution_mah:.0f} % "
                        "of the battery) were measured")
            resolution, longer = "the battery level's 1 % resolution", f"a level drop of at least {steps:.0f} %"
        else:
            consumed = f"{summary.charge_mah:.1f} mAh were consumed"
            resolution, longer = "the coulomb counter's 1 mAh resolution", f"at least {steps:.0f} mAh"
        warnings.append(f"Only {consumed}: with {resolution}, energy and power are only known to about "
                        f"±{summary.uncertainty_pct or 100:.0f} %. Record a longer session "
                        f"({longer} for ±{MAX_UNCERTAINTY_PCT} %).")
    update_s = charge_update_interval_s(source.readings, start_ms, stop_ms)
    if update_s and update_s > (stop_ms - start_ms) / 3000:
        updated = "battery level dropped by 1 %" if level else "phone updated its battery charge reading"
        warnings.append(f"The {updated} only every {update_s:.0f} s on average: power values are averages "
                        "over such periods and cannot show shorter variations.")
    return warnings


def process(dump_path, start_ms, stop_ms, csv_path, html=False, meta=None, dump_ms=None):
    """Parse a batterystats dump and write the CSV, the session JSON and optionally the HTML report.

    start_ms, stop_ms and dump_ms (when the dump was taken) are in device time.
    """
    logger.info("Processing %s: session from %s to %s, dump taken at %s (device time)",
                dump_path, debug.ms(start_ms), debug.ms(stop_ms), debug.ms(dump_ms))
    hist = history.parse_file(dump_path, end_ms=dump_ms)
    source = metrics.charge_source(hist)
    if source is None:
        values = {iv.value for iv in hist.intervals["charge_mah"]}
        found = (f"its charge counter stays at {values.pop()} mAh" if values
                 else "its battery history has no charge counter")
        raise NoDataError(f"This device does not report its battery coulomb counter ({found}), nor its "
                          "battery capacity to estimate the energy from the battery level, so its energy "
                          f"consumption cannot be measured. The battery statistics are saved in {dump_path}.")
    if source.name == metrics.LEVEL:
        logger.info("No coulomb counter: the current is estimated from the battery level drops, "
                    "1 %% = %g mAh", source.resolution_mah)
    measured = unplugged_span(hist, start_ms, stop_ms)
    if measured != (start_ms, stop_ms):
        logger.info("Left out while plugged in: measuring from %s to %s", *map(debug.ms, measured))
    if measured[0] >= measured[1]:
        raise NoDataError("The battery statistics say the phone stayed plugged in during the whole "
                          "session, so no energy can be measured. Unplug the phone when the recording "
                          f"page asks for it. The battery statistics are saved in {dump_path}.")
    rows = metrics.compute_rows(hist, *measured, source)
    summary = metrics.summarize(rows, source.name, source.resolution_mah)
    logger.info("%d rows; summary: %s", len(rows), asdict(summary))
    if not summary.measured_s:
        if source.name == metrics.LEVEL:
            raise NoDataError("This device does not report its battery coulomb counter, so PowDroid estimates "
                              "the energy from the battery level drops, but the level did not drop twice while "
                              "the phone was unplugged. Record a longer session: the battery level should drop "
                              "by at least 10 %.")
        raise NoDataError("No battery data found for the recorded session. Make sure the phone "
                          "stays unplugged and the session lasts long enough for the battery charge to drop.")

    result = Result(Path(csv_path), rows, summary, check(hist, (start_ms, stop_ms), measured, summary, source))
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
        "current_source": source.name,
        "battery_capacity_mah": hist.capacity_mah,
        "charge_update_interval_s": charge_update_interval_s(source.readings, *measured),
        "summary": asdict(summary),
        "warnings": result.warnings,
    }
    result.json_path.write_text(json.dumps(session, indent=2), encoding="utf-8")
    if html:
        result.html_path = html_report.write(result)
    for warning in result.warnings:
        logger.warning(warning)
    for path in (result.csv_path, result.json_path, result.html_path):
        if path:
            logger.info("Written %s (%d bytes)", path, path.stat().st_size)
    return result


def load(csv_path):
    """Read a session back from its CSV, with the warnings of its JSON file when there is one.

    The JSON file also tells where the current came from, which sets the uncertainty.
    """
    logger.info("Loading %s", csv_path)
    rows = metrics.read_csv(csv_path)
    result = Result(Path(csv_path), rows, metrics.summarize(rows))
    try:
        saved = json.loads(result.json_path.read_text(encoding="utf-8"))
        result.warnings = saved["warnings"]
        summary = saved.get("summary", {})
        result.summary = metrics.summarize(rows, summary.get("current_source", metrics.COULOMB),
                                           summary.get("resolution_mah", 1.0))
    except FileNotFoundError:
        pass  # a CSV without its session file: no warnings to show
    except (OSError, ValueError, KeyError, AttributeError) as e:
        result.warnings = [f"The session file {result.json_path.name} could not be read ({e}): "
                           "its reliability warnings are not shown."]
    return result
