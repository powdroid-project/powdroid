"""Turn a parsed battery history into PowDroid's per-interval energy CSV (format v3).

Each row covers an interval during which no tracked state changed. Rows tile the
recorded session exactly, from its start to its stop. Unknown values are left empty;
in particular the current (and so power and energy) is unknown while the phone is
plugged in, because the coulomb counter then measures charging, not consumption.

The current comes from the battery's coulomb counter. Phones without one only report
the battery level: the current is then estimated from the level drops, 1 % of the
battery capacity at a time, which is far less precise.
"""

import csv
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from core import PowDroidError
from core.history import Interval

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
INT_COLUMNS = {"start_ms", "end_ms", "duration_ms", "battery_level_pct", "voltage_mv", "charge_mah", "brightness"}
FLOAT_COLUMNS = {"elapsed_s", "current_ma", "power_w", "energy_j", "consumed_mah", "temperature_c"}
TEXT_COLUMNS = {"top_app", "wakelocks"}


COULOMB, LEVEL = "coulomb_counter", "battery_level"  # where the current comes from


@dataclass
class ChargeSource:
    """The battery charge readings the current is computed from."""

    name: str  # COULOMB or LEVEL
    readings: list  # [Interval] of the remaining charge, in mAh
    resolution_mah: float  # charge step between readings: the uncertainty of a consumed charge


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


def charge_source(history):
    """The coulomb counter if the battery reports one, else the battery level (None: neither is usable)."""
    if history.has_coulomb:
        return ChargeSource(COULOMB, history.intervals["charge_mah"], 1)
    if history.capacity_mah:
        return ChargeSource(LEVEL, _level_readings(history), history.capacity_mah / 100)
    return None


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
    times = sorted({start_ms, stop_ms} | {
        t for intervals in history.intervals.values() for iv in intervals for t in (iv.start, iv.end)
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
    states["current_ma"] = column(_currents(source.readings, history.intervals["plugged"]) if source else [])
    if not (source and source.name == COULOMB):
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
    if column in FLOAT_COLUMNS:
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


_FORMATTERS = [(c, _formatter(c)) for c in COLUMNS]


def format_row(row):
    """The CSV cells of a row, in COLUMNS order."""
    return [format_cell(row[c]) for c, format_cell in _FORMATTERS]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(format_row(row) for row in rows)


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


def summarize(rows, current_source=COULOMB, resolution_mah=1.0):
    if not rows:
        return Summary(current_source=current_source, resolution_mah=resolution_mah)
    measured = [r for r in rows if r["power_w"] is not None]
    measured_s = sum(r["duration_ms"] for r in measured) / 1000
    energy = sum(r["energy_j"] for r in measured)
    charge = sum(r["consumed_mah"] for r in measured)
    volts = [r["voltage_mv"] for r in rows if r["voltage_mv"]]
    levels = [r["battery_level_pct"] for r in rows if r["battery_level_pct"] is not None]
    return Summary(
        duration_s=(rows[-1]["end_ms"] - rows[0]["start_ms"]) / 1000,
        measured_s=measured_s,
        plugged_s=sum(r["duration_ms"] for r in rows if r["plugged"]) / 1000,
        energy_j=energy,
        mean_power_w=energy / measured_s if measured_s else 0.0,
        mean_current_ma=charge / (measured_s / 3600) if measured_s else 0.0,
        charge_mah=charge,
        voltage_min_mv=min(volts, default=None),
        voltage_max_mv=max(volts, default=None),
        level_start_pct=levels[0] if levels else None,
        level_end_pct=levels[-1] if levels else None,
        uncertainty_pct=100 * resolution_mah / charge if charge > 0 else None,
        current_source=current_source,
        resolution_mah=resolution_mah,
    )


# English names of the summary figures (the GUI translates the same keys).
SUMMARY_LABELS = {
    "duration": "Duration", "energy": "Total energy", "mean_power": "Average power",
    "mean_current": "Average current", "charge": "Consumed charge", "level": "Battery level",
    "voltage": "Voltage", "coverage": "Measured time",
}


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
    }


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
