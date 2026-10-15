"""Turn a parsed battery history into PowDroid's per-interval energy CSV (format v3).

Each row covers an interval during which no tracked state changed. Rows tile the
recorded session exactly, from its start to its stop. Unknown values are left empty;
in particular the current (and so power and energy) is unknown while the phone is
plugged in, because the coulomb counter then measures charging, not consumption.

The current comes from the battery's coulomb counter. Phones without one only report
the battery level: the current is then estimated from the level drops, 1 % of the
battery capacity at a time, which is far less precise. With a Perfetto trace
(core/perfetto.py), the counter is read in µAh twice a second and the current samples
shape the curve; the trace can add one energy column per power rail.
"""

import csv
import statistics
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from powdroid.core import PowDroidError
from powdroid.core.history import Interval

# The on/off columns and their display names (GUI chart bands).
LABELS = {
    "plugged": "Plugged", "screen": "Screen", "cpu_running": "CPU running", "wifi": "WiFi",
    "wifi_radio": "WiFi radio", "mobile_radio": "Mobile radio", "gps": "GPS", "bluetooth": "Bluetooth",
    "camera": "Camera", "video": "Video", "audio": "Audio", "flashlight": "Flashlight",
    "sensor": "Sensors", "battery_saver": "Battery saver",
}
BOOL_COLUMNS = list(LABELS)
COLUMNS = [
    "start_ms", "end_ms", "elapsed_s", "duration_ms",
    "battery_level_pct", "voltage_mv", "charge_mah", "current_ma", "power_w", "energy_j", "consumed_mah",
    "temperature_c", "brightness",
    *BOOL_COLUMNS,
    "top_app", "wakelocks",
]
INT_COLUMNS = {"start_ms", "end_ms", "duration_ms", "battery_level_pct", "voltage_mv", "brightness"}
FLOAT_COLUMNS = {"elapsed_s", "charge_mah", "current_ma", "power_w", "energy_j", "consumed_mah", "temperature_c"}
TEXT_COLUMNS = {"top_app", "wakelocks"}
# Optional columns after COLUMNS, from Perfetto traces: the energy (J) of each power rail,
# e.g. rail_S4M_VDD_CPUCL0_j.
RAIL_PREFIX = "rail_"


# Where the current comes from: the coulomb counter or the battery level in the battery
# history, or the coulomb counter in a Perfetto trace.
COULOMB, LEVEL, PERFETTO = "coulomb_counter", "battery_level", "perfetto"


@dataclass
class ChargeSource:
    """The battery charge readings the current is computed from."""

    name: str  # COULOMB, LEVEL or PERFETTO
    readings: list  # [Interval] of the remaining charge, in mAh
    resolution_mah: float  # charge step between readings: the uncertainty of a consumed charge
    currents: list = None  # [Interval] of current (mA), if not computed from the readings (Perfetto)
    follows_level: bool = False  # a counter that only changes with the battery level (see counter_resolution)


def _level_readings(history):
    """Charge readings estimated from the battery level, for phones without a coulomb counter.

    When the level changes, the charge has just crossed a 1 % step of the capacity: it is
    known at that moment, so each change starts a reading. The level held when the history
    starts (or resumes after a gap) only covers part of a step and is left out.
    """
    runs = []  # the level intervals, with repeated readings of the same level merged
    for iv in history.intervals["battery_level_pct"]:
        if runs and runs[-1].end == iv.start and runs[-1].value == iv.value:
            runs[-1] = Interval(runs[-1].start, iv.end, iv.value)
        else:
            runs.append(iv)
    return [Interval(iv.start, iv.end, iv.value * history.capacity_mah / 100)
            for previous, iv in zip(runs, runs[1:]) if previous.end == iv.start]


def counter_resolution(history):
    """The charge step (mAh) of the battery history's coulomb counter, and whether it follows the level.

    The history logs the counter in whole mAh: 1 mAh for a real coulomb counter. Some fuel
    gauges derive the counter from the battery level instead: it then changes only when the
    level does, by about 1 % of the capacity each time, which is its real resolution.
    """
    readings = history.intervals["charge_mah"]
    changes = [(b.start, abs(b.value - a.value)) for a, b in zip(readings, readings[1:]) if b.value != a.value]
    levels = history.intervals["battery_level_pct"]
    level_changes = {b.start for a, b in zip(levels, levels[1:]) if b.value != a.value}
    if len(changes) >= 3 and sum(t in level_changes for t, _ in changes) >= 0.8 * len(changes):
        return max(1.0, float(statistics.median(step for _, step in changes))), True
    return 1.0, False


def level_source(history):
    """The charge estimated from the battery level drops (None without the battery capacity)."""
    if not history.capacity_mah:
        return None
    return ChargeSource(LEVEL, _level_readings(history), history.capacity_mah / 100)


def charge_source(history):
    """The coulomb counter if the battery reports one, else the battery level (None: neither is usable)."""
    if history.has_coulomb:
        resolution, follows_level = counter_resolution(history)
        return ChargeSource(COULOMB, history.intervals["charge_mah"], resolution, follows_level=follows_level)
    return level_source(history)


def _currents(readings, plugged):
    """Intervals of known current (mA), one per charge reading.

    The current of a reading is the charge drop until the next reading over the time in
    between. It is unknown for the last reading, before a gap in the readings (e.g. a
    reboot) and while the phone is plugged in.
    """
    currents = []
    for iv, following in zip(readings, readings[1:]):
        hours = (iv.end - iv.start) / 3_600_000
        if (hours > 0 and following.start == iv.end
                and not any(p.start < iv.end and p.end > iv.start for p in plugged)):
            currents.append(Interval(iv.start, iv.end, (iv.value - following.value) / hours))
    return currents


def _voltages(history, times):
    """Battery voltage (mV) at each of the given times, interpolated between readings.

    Phones log the voltage only now and then (sometimes once a minute), so holding the
    last reading lags behind and, during a discharge, overestimates it. Between two
    readings the voltage is interpolated linearly, except across a plug-in or unplug
    (the charging voltage differs), where the last reading is held.
    """
    readings = history.intervals["voltage_mv"]
    plug_changes = [t for p in history.intervals["plugged"] for t in (p.start, p.end)]
    segments = []  # (start, end, value at start, value at end)
    for iv, following in zip(readings, readings[1:] + [None]):
        end_value = iv.value
        if (following is not None and following.start == iv.end
                and not any(iv.start < t <= iv.end for t in plug_changes)):
            end_value = following.value
        segments.append((iv.start, iv.end, iv.value, end_value))
    starts = [s[0] for s in segments]

    voltages = []
    for t in times:
        k = bisect_right(starts, t) - 1
        if k < 0 or t > segments[k][1]:
            voltages.append(None)
            continue
        start, end, v0, v1 = segments[k]
        voltages.append(round(v0 + (v1 - v0) * (t - start) / (end - start)) if end > start else v0)
    return voltages


def compute_rows(history, start_ms, stop_ms, source=None):
    """Build the rows covering [start_ms, stop_ms] (device time).

    The row boundaries are the session start and stop plus every state change in
    between, so each history interval covers a contiguous run of rows. The current comes
    from source (by default, charge_source(history)).
    """
    if stop_ms <= start_ms:
        return []
    source = source or charge_source(history)
    currents = []
    if source:
        currents = source.currents if source.currents is not None else _currents(
            source.readings, history.intervals["plugged"])
    times = sorted({start_ms, stop_ms} | {
        t for intervals in (*history.intervals.values(), currents) for iv in intervals for t in (iv.start, iv.end)
        if start_ms < t < stop_ms})
    count = len(times) - 1

    def row_ranges(intervals):
        """(first row, end row, value) for each interval overlapping the session."""
        for iv in intervals:
            first = bisect_left(times, max(iv.start, start_ms))
            end = bisect_left(times, min(iv.end, stop_ms))
            if first < end:
                yield first, end, iv.value

    def column(intervals):
        values = [None] * count
        # Filled latest first so that, where intervals overlap, the earliest one wins.
        for first, end, value in row_ranges(reversed(intervals)):
            values[first:end] = [value] * (end - first)
        return values

    # Wakelocks can overlap and are all kept (below); other states keep one value per row.
    states = {metric: column(intervals) for metric, intervals in history.intervals.items()
              if metric != "wakelock"}
    states["current_ma"] = column(currents)
    if source is None or source.name == LEVEL:
        states["charge_mah"] = [None] * count  # no coulomb counter (its readings are 0)
    states["voltage_mv"] = _voltages(history, [(a + b) / 2 for a, b in zip(times, times[1:])])
    wakelocks = [set() for _ in range(count)]
    for first, end, name in row_ranges(history.intervals["wakelock"]):
        for i in range(first, end):
            wakelocks[i].add(name)

    rows = []
    for i, (a, b) in enumerate(zip(times, times[1:])):
        seconds = (b - a) / 1000
        voltage, current = states["voltage_mv"][i], states["current_ma"][i]
        power = voltage * current / 1e6 if voltage is not None and current is not None else None
        row = {
            "start_ms": a,
            "end_ms": b,
            "elapsed_s": (a - start_ms) / 1000,
            "duration_ms": b - a,
            "battery_level_pct": states["battery_level_pct"][i],
            "voltage_mv": voltage,
            "charge_mah": states["charge_mah"][i],
            "current_ma": current,
            "power_w": power,
            "energy_j": power * seconds if power is not None else None,
            "consumed_mah": current * seconds / 3600 if current is not None else None,
            "temperature_c": states["temperature_c"][i],
            "brightness": states["brightness"][i],
            "wakelocks": ";".join(sorted(wakelocks[i])) or None,
        }
        for column_name in BOOL_COLUMNS:
            row[column_name] = bool(states[column_name][i])
        # As in battery-historian, the top app only counts while the screen is on.
        row["top_app"] = states["top_app"][i] if row["screen"] else None
        rows.append(row)
    return rows


def _formatter(column):
    """CSV text of a value of this column; None (unknown) is an empty cell."""
    if column in BOOL_COLUMNS:
        return lambda v: "1" if v else "0"
    if column in FLOAT_COLUMNS or column.startswith(RAIL_PREFIX):
        return lambda v: "" if v is None else f"{v:.10g}"
    return lambda v: "" if v is None else str(v)


def _parser(column):
    """Value of this column from its CSV text."""
    if column in BOOL_COLUMNS:
        return lambda text: text == "1"
    if column in TEXT_COLUMNS:
        return lambda text: text or None
    number = int if column in INT_COLUMNS else float
    return lambda text: number(text) if text else None


def columns(rows):
    """The columns of these rows: COLUMNS, then their power rail columns if they have any."""
    return COLUMNS + ([c for c in rows[0] if c.startswith(RAIL_PREFIX)] if rows else [])


def row_formatter(names=COLUMNS):
    """A function giving the CSV cells of a row, for these columns."""
    formatters = [(c, _formatter(c)) for c in names]
    return lambda row: [format_cell(row.get(c)) for c, format_cell in formatters]


format_row = row_formatter()  # the CSV cells of a row, in COLUMNS order


def write_csv(rows, path):
    names = columns(rows)
    format_cells = row_formatter(names)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(names)
        writer.writerows(format_cells(row) for row in rows)


class CsvFormatError(PowDroidError):
    """Raised when a file is not a valid PowDroid v3 CSV."""


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        missing = [c for c in COLUMNS if c not in header]
        if missing:
            raise CsvFormatError(f"{path} is not a PowDroid v3 CSV (missing columns: {', '.join(missing)})")
        parsers = [_parser(c) for c in header]
        try:
            return [{c: parse(text) for c, parse, text in zip(header, parsers, cells)} for cells in reader]
        except ValueError as e:
            raise CsvFormatError(f"{path}, line {reader.line_num}: {e}") from None


@dataclass
class Summary:
    duration_s: float = 0.0
    measured_s: float = 0.0  # time with a known current (not plugged, not after the last reading)
    plugged_s: float = 0.0
    energy_j: float = 0.0
    mean_power_w: float = 0.0
    mean_current_ma: float = 0.0
    charge_mah: float = 0.0
    voltage_min_mv: int = None
    voltage_max_mv: int = None
    level_start_pct: int = None
    level_end_pct: int = None
    # Relative uncertainty of charge, energy and power: the resolution of the charge readings
    # over the consumed charge.
    uncertainty_pct: float = None
    current_source: str = COULOMB
    resolution_mah: float = 1.0  # 1 mAh for the coulomb counter, 1 % of the capacity for the level
    # When the current is not known all the time the phone was unplugged: the mean power over
    # that whole time, an estimate of the energy it used (None when the energy is fully measured).
    extrapolated_energy_j: float = None


def summarize(rows, current_source=COULOMB, resolution_mah=1.0):
    if not rows:
        return Summary(current_source=current_source, resolution_mah=resolution_mah)
    measured = [r for r in rows if r["power_w"] is not None]
    measured_s = sum(r["duration_ms"] for r in measured) / 1000
    energy = sum(r["energy_j"] for r in measured)
    charge = sum(r["consumed_mah"] for r in measured)
    volts = [r["voltage_mv"] for r in rows if r["voltage_mv"]]
    levels = [r["battery_level_pct"] for r in rows if r["battery_level_pct"] is not None]
    duration_s = (rows[-1]["end_ms"] - rows[0]["start_ms"]) / 1000
    plugged_s = sum(r["duration_ms"] for r in rows if r["plugged"]) / 1000
    mean_power = energy / measured_s if measured_s else 0.0
    unplugged_s = duration_s - plugged_s
    return Summary(
        duration_s=duration_s,
        measured_s=measured_s,
        plugged_s=plugged_s,
        energy_j=energy,
        mean_power_w=mean_power,
        mean_current_ma=charge / (measured_s / 3600) if measured_s else 0.0,
        charge_mah=charge,
        voltage_min_mv=min(volts, default=None),
        voltage_max_mv=max(volts, default=None),
        level_start_pct=levels[0] if levels else None,
        level_end_pct=levels[-1] if levels else None,
        uncertainty_pct=100 * resolution_mah / charge if charge > 0 else None,
        current_source=current_source,
        resolution_mah=resolution_mah,
        extrapolated_energy_j=mean_power * unplugged_s if measured_s and measured_s < unplugged_s - 0.001 else None,
    )


# English names of the summary figures (the GUI translates the same keys).
SUMMARY_LABELS = {
    "duration": "Duration", "energy": "Total energy", "mean_power": "Average power",
    "mean_current": "Average current", "charge": "Consumed charge", "level": "Battery level",
    "voltage": "Voltage", "coverage": "Measured time", "extrapolated": "Estimated total (extrapolated)",
    "source": "Measured with",
}
SOURCE_NAMES = {COULOMB: "Coulomb counter", LEVEL: "Battery level", PERFETTO: "Perfetto"}


def source_label(s):
    """Where the current comes from and the resolution of its charge readings, e.g. "Perfetto (0.05 mAh steps)"."""
    unit = "mAh per %" if s.current_source == LEVEL else "mAh steps"
    return f"{SOURCE_NAMES.get(s.current_source, s.current_source)} ({s.resolution_mah:g} {unit})"


def summary_items(s):
    """Formatted summary figures by key (see SUMMARY_LABELS), shared by the CLI, GUI and HTML report."""
    voltage = ("—" if s.voltage_min_mv is None
               else f"{s.voltage_min_mv / 1000:.2f}–{s.voltage_max_mv / 1000:.2f} V")
    level = "—" if s.level_start_pct is None else f"{s.level_start_pct} → {s.level_end_pct} %"
    coverage = f"{100 * s.measured_s / s.duration_s:.0f} %" if s.duration_s else "—"
    plus_minus = f" ± {s.uncertainty_pct:.0f} %" if s.uncertainty_pct and s.uncertainty_pct >= 1 else ""
    return {
        "duration": format_duration(s.duration_s),
        "energy": format_energy(s.energy_j) + plus_minus,
        "mean_power": f"{s.mean_power_w:.3f} W" + plus_minus,
        "mean_current": f"{s.mean_current_ma:.0f} mA",
        "charge": f"{s.charge_mah:.2f} mAh",
        "level": level,
        "voltage": voltage,
        "coverage": coverage,
        "extrapolated": "—" if s.extrapolated_energy_j is None else format_energy(s.extrapolated_energy_j) + plus_minus,
        "source": source_label(s),
    }


def format_power(watts):
    return "—" if watts is None else f"{watts:.3f} W"


RAIL_HEADERS = ["Rail", "Subsystem", "Energy", "Mean power"]


def rail_rows(rails):
    """Table rows of the power rails of a session JSON (its power_rails), the most energy first."""
    ordered = sorted(rails, key=lambda r: -(r.get("energy_j") or 0))
    return [[r["name"], r.get("subsystem") or "", "—" if r.get("energy_j") is None else format_energy(r["energy_j"]),
             format_power(r.get("mean_power_w"))] for r in ordered]


def phase_summaries(rows, markers):
    """Energy and power of each phase of a session cut by its markers.

    markers are [{"time_ms": device time, "label": text}]. The first phase ("Start") runs
    from the session start to the first marker, then each marker starts a phase named after
    it (its index in markers is the phase's "marker"), the last one ending with the session.
    A row cut by a marker is split in proportion to time (its power is constant). Returns []
    without markers inside the session.
    """
    if not rows:
        return []
    start, stop = rows[0]["start_ms"], rows[-1]["end_ms"]
    inside = sorted((i for i, m in enumerate(markers) if start < m["time_ms"] < stop),
                    key=lambda i: markers[i]["time_ms"])
    if not inside:
        return []
    edges = [start] + [markers[i]["time_ms"] for i in inside] + [stop]
    labels = ["Start"] + [markers[i]["label"] for i in inside]
    phases = []
    for marker, label, a, b in zip([None] + inside, labels, edges, edges[1:]):
        energy = measured = 0.0
        for row in rows:
            overlap = min(b, row["end_ms"]) - max(a, row["start_ms"])
            if overlap > 0 and row["power_w"] is not None:
                energy += row["power_w"] * overlap / 1000
                measured += overlap / 1000
        phases.append({"label": label, "marker": marker, "from_s": (a - start) / 1000, "start_ms": a, "end_ms": b,
                       "duration_s": (b - a) / 1000, "measured_s": measured, "energy_j": energy,
                       "mean_power_w": energy / measured if measured else None})
    return phases


PHASE_HEADERS = ["Phase", "From", "Duration", "Energy", "Average power", "Measured time"]


def phase_rows(phases):
    """Table rows of phase_summaries."""
    return [[p["label"], format_duration(p["from_s"]), format_duration(p["duration_s"]), format_energy(p["energy_j"]),
             format_power(p["mean_power_w"]), f"{100 * p['measured_s'] / p['duration_s']:.0f} %" if p["duration_s"]
             else "—"] for p in phases]


def measurement_lines(summary, details):
    """(label, value) rows describing how a session was measured, from its summary and session JSON."""
    lines = [["Measured with", source_label(summary)]]
    if details.get("transport") == "wifi":
        lines.append(["Connection", "Wi-Fi (adb over the network)"])
    if details.get("battery_capacity_mah") and summary.current_source == LEVEL:
        lines.append(["Battery capacity", f"{details['battery_capacity_mah']:g} mAh "
                                          f"({details.get('battery_capacity_source') or 'reported'})"])
    trace = details.get("perfetto")
    if trace:
        interval = trace.get("median_poll_interval_ms")
        lines.append(["Perfetto battery polls", f"{trace['battery_polls']}, every "
                                                f"{f'{interval:g}' if interval else '?'} ms (median)"])
    other = details.get("batterystats_summary")
    if other:
        lines.append(["Battery statistics alone", f"{format_energy(other['energy_j'])}, "
                                                  f"{other['charge_mah']:.2f} mAh over "
                                                  f"{format_duration(other['measured_s'])} measured"])
    if details.get("clock_offset_ms") is not None:
        lines.append(["Phone clock − computer clock", f"{details['clock_offset_ms'] / 1000:+.3f} s"])
    return lines


def format_energy(joules):
    if abs(joules) >= 1e6:
        return f"{joules / 1e6:.2f} MJ"
    if abs(joules) >= 1e3:
        return f"{joules / 1e3:.2f} kJ"
    return f"{joules:.2f} J"


def format_duration(seconds):
    seconds = int(round(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = [f"{v}{u}" for v, u in ((days, "d"), (hours, "h"), (minutes, "m")) if v]
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
