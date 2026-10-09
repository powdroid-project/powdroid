"""Turn battery history intervals into PowDroid's per-interval energy CSV."""

import csv
from dataclasses import dataclass

COLUMNS = [
    "start_time",
    "end_time",
    "Duration (mS)",
    "Voltage (mV)",
    "Remaining_charge (mAh)",
    "Intensity (mA)",
    "Power (W)",
    "Consumed charge(mAh)",
    "Energy (J)",
    "Top app",
    "Screen(ON/OFF)",
    "GPS(ON/OFF)",
    "Mobile_Radio(ON/OFF)",
    "WiFi(ON/OFF)",
    "Wifi radio",
    "Camera(ON/OFF)",
    "Video (ON/OFF)",
    "Audio(ON/OFF)",
    "Wakelock_in (Service)",
]

# CSV column -> history metric, for the on/off columns.
BOOL_COLUMNS = {
    "Screen(ON/OFF)": "Screen",
    "GPS(ON/OFF)": "GPS",
    "Mobile_Radio(ON/OFF)": "Mobile radio active",
    "WiFi(ON/OFF)": "Wifi on",
    "Wifi radio": "Wifi radio",
    "Camera(ON/OFF)": "Camera",
    "Video (ON/OFF)": "Video",
    "Audio(ON/OFF)": "Audio",
}
TEXT_COLUMNS = {"Top app", "Wakelock_in (Service)"}
NUMERIC_COLUMNS = set(COLUMNS) - set(BOOL_COLUMNS) - TEXT_COLUMNS
FLOAT_COLUMNS = {"Intensity (mA)", "Power (W)", "Consumed charge(mAh)", "Energy (J)"}


def _with_intensity(coulomb):
    """Current (mA) of each coulomb-counter interval: charge drop to the next reading over its duration."""
    result = []
    for i, iv in enumerate(coulomb):
        hours = (iv.end - iv.start) / 3_600_000
        if i + 1 < len(coulomb) and hours > 0:
            result.append((iv, (iv.value - coulomb[i + 1].value) / hours))
        else:
            result.append((iv, None))
    return result


class _Sweep:
    """Finds, for successive increasing segments [a, b], the intervals containing them."""

    def __init__(self, items, key=lambda x: x):
        self.items = items
        self.key = key
        self.next = 0
        self.active = []

    def containing(self, a, b):
        while self.next < len(self.items) and self.key(self.items[self.next]).start <= a:
            self.active.append(self.items[self.next])
            self.next += 1
        self.active = [x for x in self.active if self.key(x).end >= b]
        return self.active


def compute_rows(intervals, start_ms, stop_ms):
    """Build one CSV row per elementary interval between start_ms and stop_ms (device time)."""
    times = sorted({t for ivs in intervals.values() for iv in ivs for t in (iv.start, iv.end)
                    if start_ms <= t <= stop_ms})
    if len(times) < 2:
        return []

    sweeps = {m: _Sweep(ivs) for m, ivs in intervals.items()}
    intensity = _Sweep(_with_intensity(intervals.get("Coulomb charge", [])), key=lambda x: x[0])

    def first(metric, a, b):
        found = sweeps[metric].containing(a, b) if metric in sweeps else []
        return found[0].value if found else None

    rows = []
    for a, b in zip(times, times[1:]):
        duration = b - a
        voltage = first("Voltage", a, b)
        found = intensity.containing(a, b)
        current = found[0][1] if found else None

        seconds = duration / 1000
        power = (voltage or 0) / 1000 * (current or 0) / 1000
        row = {
            "start_time": a,
            "end_time": b,
            "Duration (mS)": duration,
            "Voltage (mV)": voltage,
            "Remaining_charge (mAh)": first("Coulomb charge", a, b),
            "Intensity (mA)": current,
            "Power (W)": power,
            "Consumed charge(mAh)": (current or 0) * seconds / 3600,
            "Energy (J)": power * seconds,
            "Wakelock_in (Service)": first("Wakelock_in", a, b),
        }
        for column, metric in BOOL_COLUMNS.items():
            row[column] = first(metric, a, b) is not None
        # As in battery-historian, the top app only counts while the screen is on.
        row["Top app"] = first("Top app", a, b) if row["Screen(ON/OFF)"] else None
        rows.append(row)
    return rows


def format_value(column, value):
    if value is None:
        return ""
    if column in FLOAT_COLUMNS:
        return f"{value:f}"
    return str(value)


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([format_value(c, row.get(c)) for c in COLUMNS])


def _number(text):
    try:
        return float(text) if text not in ("", None) else None
    except ValueError:
        return None


def parse_row(raw):
    """Type one CSV row given as {column: text}: numbers as float, on/off as bool."""
    row = {}
    for column, text in raw.items():
        if column in BOOL_COLUMNS:
            row[column] = text == "True"
        elif column in TEXT_COLUMNS:
            row[column] = text or None
        else:
            row[column] = _number(text)
    return row


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [parse_row(raw) for raw in csv.DictReader(f)]


@dataclass
class Summary:
    duration_s: float = 0.0
    energy_j: float = 0.0
    mean_power_w: float = 0.0
    peak_power_w: float = 0.0
    charge_mah: float = 0.0
    voltage_min_mv: float = None
    voltage_max_mv: float = None


def summarize(rows):
    if not rows:
        return Summary()
    duration = (rows[-1]["end_time"] - rows[0]["start_time"]) / 1000
    energy = sum(r["Energy (J)"] or 0 for r in rows)
    volts = [r["Voltage (mV)"] for r in rows if r["Voltage (mV)"]]
    return Summary(
        duration_s=duration,
        energy_j=energy,
        mean_power_w=energy / duration if duration else 0.0,
        peak_power_w=max((r["Power (W)"] or 0 for r in rows), default=0.0),
        charge_mah=sum(r["Consumed charge(mAh)"] or 0 for r in rows),
        voltage_min_mv=min(volts, default=None),
        voltage_max_mv=max(volts, default=None),
    )


def summary_items(s):
    """Formatted summary figures as (key, text) pairs, shared by the GUI and the HTML report."""
    voltage = ("—" if s.voltage_min_mv is None
               else f"{s.voltage_min_mv / 1000:.2f}–{s.voltage_max_mv / 1000:.2f} V")
    return [
        ("duration", format_duration(s.duration_s)),
        ("energy", format_energy(s.energy_j)),
        ("mean_power", f"{s.mean_power_w:.3f} W"),
        ("peak_power", f"{s.peak_power_w:.3f} W"),
        ("charge", f"{s.charge_mah:.2f} mAh"),
        ("voltage", voltage),
    ]


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
