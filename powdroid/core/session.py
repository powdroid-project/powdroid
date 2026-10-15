"""The collection and processing pipeline shared by the CLI and the GUI.

A session produces, next to each other: PowDroid_<date>.csv (the rows),
PowDroid_<date>.json (device, session span, summary, warnings) and optionally
PowDroid_<date>.html. The battery data comes from a Perfetto trace recorded during the
session (core/perfetto.py), or from the batterystats history when Perfetto is not wanted or
not available.
"""

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from powdroid.core import PowDroidError, __version__, adb, debug, history, html_report, metrics, perfetto
from powdroid.core.history import Interval

logger = logging.getLogger("powdroid.session")

MAX_UNCERTAINTY_PCT = 5  # i.e. at least 20 mAh consumed with the coulomb counter, or a 20 % level drop
MAX_CLOCK_DRIFT_MS = 1000  # between the clock offsets measured when preparing and when collecting

# Added to the warnings of sessions recorded over Wi-Fi debugging.
WIFI_NOTE = ("PowDroid was connected to the phone over Wi-Fi: the Wi-Fi connection used by adb adds to the "
             "measured energy, a little while the phone sleeps (PowDroid sends it nothing while recording).")

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

    serial: str
    coulomb: bool = None  # whether the battery reports its coulomb counter (None: unknown)
    trace: perfetto.Trace = None  # the Perfetto trace recording the session, if any
    perfetto_unavailable: str = None  # why Perfetto cannot be used on this phone, when it is wanted
    notes: list = field(default_factory=list)  # what could not be prepared, added to the session warnings
    restored: bool = False  # whether the phone was given back its battery statistics options (adb.restore)
    clock_offset_ms: int = None  # device clock minus computer clock when prepared

    @property
    def perfetto_notice(self):
        """What to tell the user when Perfetto is not available (None otherwise)."""
        if self.perfetto_unavailable:
            return (f"Perfetto is not available because {self.perfetto_unavailable}: "
                    "PowDroid uses the battery statistics instead.")
        return None

    def restore(self):
        """Turn the battery statistics options off again (adb.restore), unless already done."""
        if not self.restored:
            adb.restore(self.serial)
            self.restored = True


def prepare(serial, use_perfetto=True):
    """Before the phone is unplugged: reset the battery statistics and start the Perfetto trace.

    Without Perfetto (use_perfetto=False, or it is not available on this phone), the
    session is measured with the battery statistics alone. Why Perfetto is not available
    is kept in perfetto_unavailable, and in the session JSON.
    """
    coulomb, notes = adb.prepare(serial)
    preparation = Preparation(serial, coulomb, notes=notes, clock_offset_ms=adb.clock_offset_ms(serial))
    if use_perfetto:
        try:
            preparation.trace = perfetto.start(serial)
        except perfetto.Unavailable as e:
            logger.info("Perfetto is not available, using the battery statistics: %s", e)
            preparation.perfetto_unavailable = str(e)
    return preparation


def cancel(preparation):
    """Give the phone back as it was found when a prepared session is not collected (best effort).

    Stops the Perfetto trace and turns the battery statistics options off again. Does nothing
    for what collect already did, and fails silently when the phone is not connected (the next
    session stops a trace left running, which also stops by itself after a day).
    """
    if preparation.trace:
        perfetto.cancel(preparation.trace)
    preparation.restore()


@dataclass
class Result:
    """A processed session: its rows and what was concluded from them."""

    csv_path: Path
    rows: list
    summary: metrics.Summary
    warnings: list = field(default_factory=list)
    html_path: Path = None
    details: dict = field(default_factory=dict)  # the session JSON (how it was measured, power rails...)
    markers: list = field(default_factory=list)  # [{"time_ms": device time, "label": text}]
    phases: list = field(default_factory=list)  # metrics.phase_summaries between the markers

    @property
    def json_path(self):
        return self.csv_path.with_suffix(".json")


def collect(device, start, stop, out_dir, html=False, report=lambda step: None, *, preparation, markers=()):
    """After a session, read the battery statistics from the device and write the reports.

    start and stop are computer times (epoch seconds, as time.time() gives); they are
    converted to device time using the device clock offset measured now. preparation is
    what prepare returned: its Perfetto trace, if any, is stopped and copied. report(step)
    is called with "offset", "trace" (with a trace), "dump" and "parse" as the work
    progresses. markers are [{"time": computer time, "label": text}]. Returns a Result.
    """
    logger.info("Collecting the session recorded on %s from %s to %s (computer time) into %s",
                device.serial, debug.ms(start * 1000), debug.ms(stop * 1000), out_dir)
    report("offset")
    offset = adb.clock_offset_ms(device.serial)
    adb.log_diagnostics(device.serial, "after the session")
    to_device_ms = lambda seconds: round(seconds * 1000) + offset  # noqa: E731
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir).expanduser()
    dump_path = out_dir / "dump" / f"batterystats_{stamp}.txt"
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    notes, trace_path = list(preparation.notes), None
    if device.wireless:
        notes.append(WIFI_NOTE)
    if preparation.clock_offset_ms is not None:
        drift = offset - preparation.clock_offset_ms
        if abs(drift) > MAX_CLOCK_DRIFT_MS:
            logger.warning("The clock offset changed by %d ms during the session", drift)
            notes.append(f"The phone's clock moved by {drift / 1000:+.1f} s relative to the computer's during the "
                         "session (a clock was set or synchronized): the start and stop of the session may be "
                         "off by up to that much.")
    if preparation.trace:
        report("trace")
        try:
            trace_path = perfetto.stop(preparation.trace, dump_path.with_name(f"perfetto_{stamp}.pftrace"))
        except PowDroidError as e:  # AdbError, TraceError
            logger.warning("The Perfetto trace could not be copied: %s", e, exc_info=True)
            notes.append(f"The Perfetto trace could not be copied from the phone ({e}): the results come "
                         "from the battery statistics.")
    report("dump")
    dump_ms = to_device_ms(time.time())
    # Estimating the energy from the battery level needs the capacity, only in the full statistics:
    # read them at once without a coulomb counter, or when the counter turns out not to change.
    if (adb.dump_batterystats(device.serial, dump_path, history_only=preparation.coulomb is not False)
            and not _counter_changes(dump_path)):
        logger.info("The charge counter does not change: reading the full battery statistics for the capacity")
        adb.dump_batterystats(device.serial, dump_path, history_only=False)
    preparation.restore()
    report("parse")
    meta = {"device": {k: v for k, v in asdict(device).items() if k != "state"},
            "clock_offset_ms": offset,
            "clock_offset_at_start_ms": preparation.clock_offset_ms,
            "transport": "wifi" if device.wireless else "usb"}
    if preparation.perfetto_unavailable:
        meta["perfetto_unavailable"] = preparation.perfetto_unavailable
    markers = [{"time_ms": to_device_ms(m["time"]), "label": m["label"]} for m in markers]
    return process(dump_path, to_device_ms(start), to_device_ms(stop), out_dir / f"PowDroid_{stamp}.csv",
                   html=html, meta=meta, dump_ms=dump_ms, trace_path=trace_path, notes=notes, markers=markers)


def _counter_changes(dump_path):
    """Whether the coulomb counter of a battery history dump takes at least two values."""
    values = set()
    with open(dump_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(history.H):
                values.update(re.findall(r"(?:^|,)Bcc=(-?\d+)", line))
                if len(values) > 1:
                    return True
    return False


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
    if source.follows_level:
        warnings.append(f"This phone's charge counter only changes when the battery level does, by about "
                        f"{source.resolution_mah:g} mAh at a time: it is computed from the battery level rather "
                        "than measured by a coulomb counter, so the results are much less precise.")
    if level:
        capacity = f"{history.CAPACITY_SOURCES[hist.capacity_source]} ({hist.capacity_mah:g} mAh)"
        warnings.append(("Current" if hist.has_coulomb else "This phone does not report its battery coulomb counter: "
                                                            "current")
                        + f", power and energy are estimated from the battery level drops, counting each "
                        f"1 % as {source.resolution_mah:g} mAh, 1 % of the {capacity}. They are only known between "
                        "the first and last level drops"
                        + ("." if hist.capacity_source == "learned" else
                           ", and are overestimated if the battery has worn and holds less than that capacity."))
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
    plugged = list(hist.intervals["plugged"])
    if hist.start_ms is not None and trace.samples and trace.samples[0].time_ms < hist.start_ms:
        # Before the battery history starts (e.g. Android reset it when the phone was unplugged),
        # the plug state is unknown: counted as plugged in, so no current spans charging time.
        plugged.insert(0, Interval(trace.samples[0].time_ms, hist.start_ms, True))
    source = perfetto.charge_source(trace, plugged)
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
            notes=(), markers=()):
    """Parse a batterystats dump and write the CSV, the session JSON and optionally the HTML report.

    start_ms, stop_ms and dump_ms (when the dump was taken) are in device time. With
    trace_path, a Perfetto trace of the session, the battery readings come from the trace
    if it has a coulomb counter, and its power rails are added. notes are warnings to add
    (e.g. why the trace could not be copied from the phone). markers ({"time_ms": device
    time, "label": text}) cut the session into phases.
    """
    collection_notes = list(notes)
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
    summary = metrics.summarize(rows, source.name, source.resolution_mah)
    if not summary.measured_s and source.name == metrics.COULOMB:
        source, rows, summary = _level_fallback(hist, measured, source, rows, summary, notes)
    if trace:
        perfetto.add_rail_energy(rows, trace.rails)
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
    result = Result(Path(csv_path), rows, summary, warnings, markers=[dict(m) for m in markers])
    result.phases = metrics.phase_summaries(rows, result.markers)
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
        # Relative to this file when possible, so that the folder can be moved (see reprocess).
        "dump_file": _relative(dump_path, result.csv_path.parent),
        "trace_file": _relative(trace_path, result.csv_path.parent) if trace_path else None,
        "current_source": source.name,
        "charge_resolution_mah": source.resolution_mah,
        "counter_follows_level": source.follows_level,
        "battery_capacity_mah": hist.capacity_mah,
        "battery_capacity_source": hist.capacity_source,
        "charge_update_interval_s": charge_update_interval_s(source.readings, *measured),
        "summary": asdict(summary),
        "markers": result.markers,
        "phases": result.phases,
        "notes": collection_notes,  # the warnings from the collection, kept by reprocess
        "warnings": result.warnings,
    }
    if trace:
        session["perfetto"] = perfetto.describe(trace, source if source.name == metrics.PERFETTO else None)
        session["power_rails"] = perfetto.rail_totals(trace.rails, *measured)
    if source.name == metrics.PERFETTO and batterystats_source:
        session["batterystats_summary"] = _batterystats_summary(hist, measured, batterystats_source, summary)
    result.json_path.write_text(json.dumps(session, indent=2), encoding="utf-8")
    result.details = session
    if html:
        result.html_path = html_report.write(result)
    for warning in result.warnings:
        logger.warning(warning)
    for path in (result.csv_path, result.json_path, result.html_path):
        if path:
            logger.info("Written %s (%d bytes)", path, path.stat().st_size)
    return result


def _relative(path, base):
    """path relative to the folder base (with / separators), or absolute if it is on another drive."""
    try:
        return Path(os.path.relpath(Path(path).absolute(), Path(base).absolute())).as_posix()
    except ValueError:  # Windows: another drive
        return str(Path(path).absolute())


# What the session JSON keeps from the collection, for reprocess.
COLLECTION_META = ("device", "clock_offset_ms", "clock_offset_at_start_ms", "perfetto_unavailable", "transport")


def reprocess(json_path, out_dir=None, html=False):
    """Process a saved session again, e.g. with a newer PowDroid, from its session JSON file.

    The battery statistics and Perfetto trace it names are read again; the CSV, JSON (and
    HTML) are written again in out_dir, by default next to the JSON file, which is replaced.
    """
    json_path = Path(json_path)
    try:
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        start_ms, stop_ms = saved["requested_start_ms"], saved["requested_stop_ms"]
    except (ValueError, KeyError, TypeError) as e:
        raise NoDataError(f"{json_path} is not a PowDroid session file ({e!r})") from None

    def saved_path(key):
        value = saved.get(key)
        path = Path(value) if value else None
        return path if path is None or path.is_absolute() else json_path.parent / path

    dump_path, trace_path = saved_path("dump_file"), saved_path("trace_file")
    if dump_path is None or not dump_path.exists():
        raise NoDataError(f"The battery statistics of this session ({dump_path}) are missing: it cannot be "
                          "processed again.")
    notes = list(saved.get("notes", []))
    if trace_path is not None and not trace_path.exists():
        notes.append(f"The Perfetto trace of this session ({trace_path}) is missing: the results come from the "
                     "battery statistics.")
        trace_path = None
    logger.info("Processing %s again (recorded with PowDroid %s)", json_path, saved.get("powdroid_version"))
    out_dir = Path(out_dir).expanduser() if out_dir else json_path.parent
    meta = {key: saved[key] for key in COLLECTION_META if key in saved}
    return process(dump_path, start_ms, stop_ms, out_dir / json_path.with_suffix(".csv").name, html=html,
                   meta=meta, dump_ms=saved.get("dump_ms"), trace_path=trace_path, notes=notes,
                   markers=saved.get("markers", []))


def _level_fallback(hist, measured, source, rows, summary, notes):
    """When the coulomb counter never changed while unplugged, the estimate from the battery level, if any.

    Returns the source, rows and summary to use; why the level is used is added to notes.
    """
    level = metrics.level_source(hist)
    if level is None:
        return source, rows, summary
    level_rows = metrics.compute_rows(hist, *measured, level)
    level_summary = metrics.summarize(level_rows, level.name, level.resolution_mah)
    if not level_summary.measured_s:
        return source, rows, summary
    values = sorted({iv.value for iv in hist.intervals["charge_mah"]
                     if iv.start < measured[1] and iv.end > measured[0]})
    logger.warning("The coulomb counter did not change while unplugged (%s): using the battery level", values)
    notes.append("The battery's charge counter did not change while the phone was unplugged"
                 + (f" (it stayed at {values[0]:g} mAh)" if len(values) == 1 else "")
                 + ": the energy is estimated from the battery level drops instead.")
    return level, level_rows, level_summary


def _batterystats_summary(hist, measured, source, summary):
    """The summary the battery statistics alone give for the same session, to compare with Perfetto's."""
    other = metrics.summarize(metrics.compute_rows(hist, *measured, source), source.name, source.resolution_mah)
    logger.info("Same session from the battery statistics (%s): %.3f J and %.3f mAh over %.0f s measured, "
                "against %.3f J and %.3f mAh over %.0f s from Perfetto", source.name, other.energy_j,
                other.charge_mah, other.measured_s, summary.energy_j, summary.charge_mah, summary.measured_s)
    return asdict(other)


def rename_marker(result, index, label):
    """Rename a marker of a processed session: its phases, session JSON and HTML report (if any) follow."""
    result.markers[index]["label"] = label
    result.phases = metrics.phase_summaries(result.rows, result.markers)
    result.details.update(markers=result.markers, phases=result.phases)  # the session JSON, as written or loaded
    result.json_path.write_text(json.dumps(result.details, indent=2), encoding="utf-8")
    if result.csv_path.with_suffix(".html").exists():
        result.html_path = html_report.write(result)


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
        result.details = saved
        result.markers = saved.get("markers", [])
        result.phases = saved.get("phases") or metrics.phase_summaries(rows, result.markers)
        summary = saved.get("summary", {})
        result.summary = metrics.summarize(rows, summary.get("current_source", metrics.COULOMB),
                                           summary.get("resolution_mah", 1.0))
    except FileNotFoundError:
        pass  # a CSV without its session file: no warnings to show
    except (OSError, ValueError, KeyError, AttributeError) as e:
        result.warnings = [f"The session file {result.json_path.name} could not be read ({e}): "
                           "its reliability warnings are not shown."]
    return result
