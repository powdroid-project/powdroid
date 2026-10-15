"""The collection and processing pipeline shared by the CLI and the GUI.

A session produces, next to each other: PowDroid_<date>.csv (the rows),
PowDroid_<date>.json (device, session span, summary, warnings) and optionally
PowDroid_<date>.html. The battery data comes from a Perfetto trace recorded during the
session (core/perfetto.py), or from the batterystats history when Perfetto is not wanted or
not available.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core import PowDroidError, __version__, adb, debug, history, html_report, metrics, perfetto

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
class Preparation:
    """A device ready to record a session (see prepare)."""

    coulomb: bool = None  # whether the battery reports its coulomb counter (None: unknown)
    trace: perfetto.Trace = None  # the Perfetto trace recording the session, if any
    perfetto_unavailable: str = None  # why Perfetto cannot be used on this phone, when it is wanted

    @property
    def perfetto_notice(self):
        """What to tell the user when Perfetto is not available (None otherwise)."""
        if self.perfetto_unavailable:
            return (f"Perfetto is not available because {self.perfetto_unavailable}: "
                    "PowDroid uses the battery statistics instead.")
        return None


def prepare(serial, use_perfetto=True):
    """Before the phone is unplugged: reset the battery statistics and start the Perfetto trace.

    Without Perfetto (use_perfetto=False, or it is not available on this phone), the
    session is measured with the battery statistics alone. Why Perfetto is not available
    is kept in perfetto_unavailable, and in the session JSON.
    """
    preparation = Preparation(adb.prepare(serial))
    if use_perfetto:
        try:
            preparation.trace = perfetto.start(serial)
        except perfetto.Unavailable as e:
            logger.info("Perfetto is not available, using the battery statistics: %s", e)
            preparation.perfetto_unavailable = str(e)
    return preparation


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


def collect(device, start, stop, out_dir, html=False, report=lambda step: None, preparation=None):
    """After a session, read the battery statistics from the device and write the reports.

    start and stop are host datetimes; they are converted to device time using the
    device clock offset measured now. preparation is what prepare returned: its Perfetto
    trace, if any, is stopped and copied. report(step) is called with "offset", "trace"
    (with a trace), "dump" and "parse" as the work progresses. Returns a Result.
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
    notes, trace_path = [], None
    if preparation and preparation.trace:
        report("trace")
        try:
            trace_path = perfetto.stop(preparation.trace, dump_path.with_name(f"perfetto_{stamp}.pftrace"))
        except PowDroidError as e:  # AdbError, TraceError
            logger.warning("The Perfetto trace could not be copied: %s", e, exc_info=True)
            notes.append(f"The Perfetto trace could not be copied from the phone ({e}): the results come "
                         "from the battery statistics.")
    report("dump")
    dump_ms = to_device_ms(datetime.now())
    adb.dump_batterystats(device.serial, dump_path)
    report("parse")
    meta = {"device": {k: v for k, v in asdict(device).items() if k != "state"},
            "clock_offset_ms": offset}
    if preparation and preparation.perfetto_unavailable:
        meta["perfetto_unavailable"] = preparation.perfetto_unavailable
    return process(dump_path, to_device_ms(start), to_device_ms(stop), out_dir / f"PowDroid_{stamp}.csv",
                   html=html, meta=meta, dump_ms=dump_ms, trace_path=trace_path, notes=notes)


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
            resolution = f"the coulomb counter's {source.resolution_mah:g} mAh resolution"
            longer = f"at least {steps * source.resolution_mah:g} mAh"
        warnings.append(f"Only {consumed}: with {resolution}, energy and power are only known to about "
                        f"±{summary.uncertainty_pct or 100:.0f} %. Record a longer session "
                        f"({longer} for ±{MAX_UNCERTAINTY_PCT} %).")
    update_s = charge_update_interval_s(source.readings, start_ms, stop_ms)
    if update_s and update_s > (stop_ms - start_ms) / 3000:
        updated = "battery level dropped by 1 %" if level else "phone updated its battery charge reading"
        warnings.append(f"The {updated} only every {update_s:.0f} s on average: power values are averages "
                        "over such periods and cannot show shorter variations.")
    return warnings


def _perfetto_source(trace_path, hist, notes):
    """The trace's data, its metrics.ChargeSource and the battery history it gives (None if unusable).

    Why it cannot be used is added to notes.
    """
    try:
        trace = perfetto.parse_file(trace_path)
    except (PowDroidError, OSError) as e:
        logger.warning("Cannot read the Perfetto trace %s: %s", trace_path, e, exc_info=True)
        notes.append(f"The Perfetto trace could not be read ({e}): the results come from the battery statistics.")
        return None, None, hist
    source = perfetto.charge_source(trace, hist.intervals["plugged"])
    if source is None:
        charges = {s.charge_uah for s in trace.samples if s.charge_uah is not None}
        counter = f"always {charges.pop()} µAh" if len(charges) == 1 else "unusable" if charges else "not reported"
        found = f"{len(trace.samples)} battery polls, charge counter {counter}"
        logger.warning("The Perfetto trace has no usable coulomb counter (%s)", found)
        notes.append(f"The Perfetto trace has no usable coulomb counter ({found}): the results come from the "
                     "battery statistics.")
        return trace, None, hist
    logger.info("Current from the Perfetto trace's coulomb counter: %d readings, resolution %g mAh",
                len(source.readings), source.resolution_mah)
    return trace, source, perfetto.battery_history(hist, trace, source)


def process(dump_path, start_ms, stop_ms, csv_path, html=False, meta=None, dump_ms=None, trace_path=None,
            notes=()):
    """Parse a batterystats dump and write the CSV, the session JSON and optionally the HTML report.

    start_ms, stop_ms and dump_ms (when the dump was taken) are in device time. With
    trace_path, a Perfetto trace of the session, the battery readings come from the trace
    if it has a coulomb counter, and its power rails are added. notes are warnings to add
    (e.g. why the trace could not be copied from the phone).
    """
    logger.info("Processing %s: session from %s to %s, dump taken at %s (device time)%s",
                dump_path, debug.ms(start_ms), debug.ms(stop_ms), debug.ms(dump_ms),
                f", Perfetto trace {trace_path}" if trace_path else "")
    notes = list(notes)
    hist = history.parse_file(dump_path, end_ms=dump_ms)
    trace, source, battery_hist = _perfetto_source(trace_path, hist, notes) if trace_path else (None, None, hist)
    batterystats_source = metrics.charge_source(hist)
    source = source or batterystats_source
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
    rows = metrics.compute_rows(battery_hist, *measured, source)
    if trace:
        perfetto.add_rail_energy(rows, trace.rails)
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

    warnings = notes + check(hist, (start_ms, stop_ms), measured, summary, source)
    if source.name == metrics.PERFETTO:
        first, last = trace.samples[0].time_ms, trace.samples[-1].time_ms
        if first > measured[0] + perfetto.GAP_MS or last < measured[1] - perfetto.GAP_MS:
            warnings.append(f"The Perfetto trace only covers the session from {(first - measured[0]) / 1000:.0f} s "
                            f"to {(last - measured[0]) / 1000:.0f} s: the rest has no current.")
    result = Result(Path(csv_path), rows, summary, warnings)
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
        "trace_file": str(trace_path) if trace_path else None,
        "current_source": source.name,
        "battery_capacity_mah": hist.capacity_mah,
        "charge_update_interval_s": charge_update_interval_s(source.readings, *measured),
        "summary": asdict(summary),
        "warnings": result.warnings,
    }
    if trace:
        session["perfetto"] = perfetto.describe(trace, source if source.name == metrics.PERFETTO else None)
        session["power_rails"] = perfetto.rail_totals(trace.rails, *measured)
    if source.name == metrics.PERFETTO and batterystats_source:
        session["batterystats_summary"] = _batterystats_summary(hist, measured, batterystats_source, summary)
    result.json_path.write_text(json.dumps(session, indent=2), encoding="utf-8")
    if html:
        result.html_path = html_report.write(result)
    for warning in result.warnings:
        logger.warning(warning)
    for path in (result.csv_path, result.json_path, result.html_path):
        if path:
            logger.info("Written %s (%d bytes)", path, path.stat().st_size)
    return result


def _batterystats_summary(hist, measured, source, summary):
    """The summary the battery statistics alone give for the same session, to compare with Perfetto's."""
    other = metrics.summarize(metrics.compute_rows(hist, *measured, source), source.name, source.resolution_mah)
    logger.info("Same session from the battery statistics (%s): %.3f J and %.3f mAh over %.0f s measured, "
                "against %.3f J and %.3f mAh over %.0f s from Perfetto", source.name, other.energy_j,
                other.charge_mah, other.measured_s, summary.energy_j, summary.charge_mah, summary.measured_s)
    return asdict(other)


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
