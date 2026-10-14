"""Parse the battery history of `dumpsys batterystats -c` ("9,h" checkin lines).

The history is a list of records. Each one starts with the time elapsed since the
previous record (in ms), then lists the states that changed, for example:

    9,hsp,3,10100,"com.example.app"          string pool: index 3 -> app name
    9,h,0:RESET:TIME:1700000000000           statistics reset, absolute time
    9,h,1500,Bv=4012,+S,+Etp=3               1.5 s later: voltage, screen on, top app 3

Only the metrics PowDroid reports on are extracted, following the semantics of
Google's battery-historian parser:

- integer states (voltage, coulomb counter, ...) hold their value until the next change;
- boolean states (+X / -X) are on between their + and - transitions;
- service states (top app, wakelocks) reference the string pool and can overlap.

Metric names are the PowDroid CSV column names.
"""

import logging
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from itertools import accumulate

from core import PowDroidError, debug

logger = logging.getLogger("powdroid.history")

H = "9,h,"
HSP = "9,hsp,"
PWS = "9,0,l,pws,"  # power use summary: battery capacity, then computed and drained charge (mAh)

INT_METRICS = {
    "Bv": "voltage_mv",
    "Bcc": "charge_mah",  # coulomb counter
    "Bl": "battery_level_pct",
    "Bt": "temperature_c",
    "Sb": "brightness",  # 0 (dark) .. 4 (bright)
}
INT_DIVISORS = {"Bt": 10}  # the temperature is logged in tenths of a degree
BOOL_METRICS = {
    "BP": "plugged",
    "S": "screen",
    "r": "cpu_running",
    "W": "wifi",
    "Wr": "wifi_radio",
    "Pr": "mobile_radio",
    "g": "gps",
    "b": "bluetooth",
    "ca": "camera",
    "v": "video",
    "a": "audio",
    "fl": "flashlight",
    "s": "sensor",
    "ps": "battery_saver",
    "lp": "battery_saver",  # name used before Android M
}
SERVICE_METRICS = {"Etp": "top_app", "Ewl": "wakelock"}
METRICS = sorted(set(INT_METRICS.values()) | set(BOOL_METRICS.values()) | set(SERVICE_METRICS.values()))

_RECORD_RE = re.compile(r"^(\d+)(?::(RESET:TIME|TIME|START|SHUTDOWN|\*OVERFLOW\*)(?::(\d+))?)?(.*)$")
_ITEM_RE = re.compile(r"^([+-]?)(\w+)(?:=(.*))?$")
_POOL_RE = re.compile(r"^(\d+),(-?\d+),(.*)$")


@dataclass
class Interval:
    start: int
    end: int
    value: object


@dataclass
class History:
    intervals: dict  # metric -> [Interval] sorted by start
    start_ms: int = None  # time of the statistics reset (or of the first record)
    end_ms: int = None  # time up to which the states are known
    overflow_ms: int = None  # set when the history buffer overflowed: no data after it
    capacity_mah: float = None  # battery design capacity (from the power profile), if reported

    @property
    def has_coulomb(self):
        """Whether the battery reports its coulomb counter.

        Phones without one log nothing or a constant 0. Some fuel gauges report it with an
        offset that can make it negative: only its changes are used, so any counter that
        moves counts.
        """
        values = {iv.value for iv in self.intervals["charge_mah"]}
        return len(values) > 1 or any(v > 0 for v in values)


@dataclass
class _Record:
    delta: int  # ms since the previous record
    tag: str = None  # RESET:TIME, TIME, START, SHUTDOWN, *OVERFLOW* or None for state changes
    clock: int = None  # absolute time given by RESET:TIME / TIME records
    items: list = field(default_factory=list)  # state changes, e.g. ["Bv=4012", "+S"]
    time: int = None  # absolute time of the record, set by _assign_times


class HistoryError(PowDroidError):
    """Raised when no usable battery history can be found."""


def _parse_record(body):
    m = _RECORD_RE.match(body)
    if not m:
        return None
    delta, tag, clock, rest = m.groups()
    return _Record(int(delta), tag, int(clock) if clock else None,
                   [] if tag else [i for i in rest.split(",") if i])


def _assign_times(records):
    """Give each record its absolute time, from the deltas and the TIME statements.

    As battery-historian does, the times of each boot are anchored on its last TIME
    statement: if the device clock jumped during the session (e.g. a network time sync),
    earlier events are aligned with the final clock, the one PowDroid compares with.
    """
    boots, current = [], []
    for record in records:
        if record.tag == "START":  # reboot: times cannot be carried across it
            boots.append(current)
            current = []
        current.append(record)
    boots.append(current)

    for boot in boots:
        elapsed = list(accumulate(record.delta for record in boot))
        anchors = [(e, record.clock) for record, e in zip(boot, elapsed) if record.clock is not None]
        if anchors:
            anchor_elapsed, anchor_clock = anchors[-1]
            for record, e in zip(boot, elapsed):
                record.time = anchor_clock + e - anchor_elapsed


class _Builder:
    """Replays the records and turns state changes into intervals."""

    def __init__(self, pool):
        self.pool = pool
        self.history = History(intervals={m: [] for m in METRICS})
        self.now = None
        self.ints = {}  # metric -> (start, value)
        self.bools = {}  # metric -> start
        self.services = {m: {} for m in SERVICE_METRICS.values()}  # metric -> {index: (start, name)}

    def add(self, metric, start, end, value):
        if end >= start:
            self.history.intervals[metric].append(Interval(start, end, value))

    def close_all(self):
        """End every open state now (at a reset, a reboot or the end of the history)."""
        if self.now is None:
            return
        for metric, (start, value) in self.ints.items():
            self.add(metric, start, self.now, value)
        for metric, start in self.bools.items():
            self.add(metric, start, self.now, True)
        for metric, active in self.services.items():
            for start, name in active.values():
                self.add(metric, start, self.now, name)
            active.clear()
        self.ints.clear()
        self.bools.clear()

    def record(self, record):
        """Apply one record; returns False when the history stops (buffer overflow)."""
        if record.tag == "*OVERFLOW*":
            self.history.overflow_ms = self.now
            return False
        if record.tag in ("START", "RESET:TIME"):
            self.close_all()
        if record.time is None:
            return True  # No absolute time known: the record cannot be placed on the timeline.
        self.now = record.time
        if record.tag == "RESET:TIME" or self.history.start_ms is None:
            self.history.start_ms = self.now
        for item in record.items:
            m = _ITEM_RE.match(item)
            if m:
                self.item(*m.groups())
        return True

    def item(self, tr, key, value):
        now, origin = self.now, self.history.start_ms
        if key in INT_METRICS:
            metric = INT_METRICS[key]
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return
            if key in INT_DIVISORS:
                parsed /= INT_DIVISORS[key]
            if metric in self.ints:
                start, old = self.ints[metric]
                self.add(metric, start, now, old)
            self.ints[metric] = (now, parsed)
        elif key in BOOL_METRICS and tr:
            metric = BOOL_METRICS[key]
            if tr == "+":
                self.bools.setdefault(metric, now)
            else:  # A '-' without '+' means it was already on when the history started.
                self.add(metric, self.bools.pop(metric, origin), now, True)
        elif key in SERVICE_METRICS and value is not None:
            active = self.services[SERVICE_METRICS[key]]
            name = self.pool.get(value, value)
            if tr == "-":
                start, name = active.pop(value, (origin, name))
                self.add(SERVICE_METRICS[key], start, now, name)
            else:  # '+', or no sign: already active when the history started
                active.setdefault(value, (now if tr else origin, name))


def _capacity(fields):
    """The battery capacity (mAh) at the start of a power use summary, or None if not reported."""
    try:
        capacity = float(fields.split(",", 1)[0])
    except ValueError:
        return None
    return capacity if capacity > 0 else None


def parse_lines(lines, end_ms=None):
    """Parse dumpsys lines into a History whose intervals are sorted by start time.

    end_ms is the device time of the dump: states hold until then, not just until the
    last history record (a quiet phone can log nothing for minutes).
    """
    pool, records, capacity = {}, [], None
    for line in lines:
        line = line.strip()
        if line.startswith(HSP):
            m = _POOL_RE.match(line[len(HSP):])
            if m:
                pool[m.group(1)] = m.group(3).strip().strip('"')
        elif line.startswith(H):
            record = _parse_record(line[len(H):])
            if record:
                records.append(record)
        elif line.startswith(PWS):
            capacity = _capacity(line[len(PWS):])
    if not records:
        raise HistoryError("No battery history in the dumpsys output")

    _assign_times(records)
    builder = _Builder(pool)
    for record in records:
        if not builder.record(record):
            break
    if end_ms is not None and builder.history.overflow_ms is None and builder.now is not None:
        builder.now = max(builder.now, end_ms)
    builder.close_all()

    history = builder.history
    history.end_ms = builder.now
    history.capacity_mah = capacity
    for intervals in history.intervals.values():
        intervals.sort(key=lambda iv: (iv.start, iv.end))
    if logger.isEnabledFor(logging.DEBUG):
        _log_summary(records, pool, history)
    return history


def parse_history(text):
    return parse_lines(text.splitlines())


def parse_file(path, end_ms=None):
    if logger.isEnabledFor(logging.DEBUG):
        _log_file(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_lines(f, end_ms)


def _log_summary(records, pool, history):
    """Debug log: what the parsed history contains, e.g. to see why a device gives no data."""
    tags = Counter(record.tag for record in records if record.tag)
    keys = Counter(m.group(2) for record in records for item in record.items
                   for m in [_ITEM_RE.match(item)] if m)
    charges = sorted({iv.value for iv in history.intervals["charge_mah"]})
    logger.debug(
        "Battery history: %d records (%s), %d without a known time (ignored), %d strings in the pool\n"
        "  from %s to %s%s\n"
        "  state changes by key: %s\n"
        "  intervals by metric: %s\n"
        "  charge counter: %s; battery capacity: %s",
        len(records), ", ".join(f"{tag} {n}" for tag, n in tags.items()) or "no TIME or RESET",
        sum(record.time is None for record in records), len(pool),
        debug.ms(history.start_ms), debug.ms(history.end_ms),
        f", buffer overflow at {debug.ms(history.overflow_ms)}" if history.overflow_ms is not None else "",
        ", ".join(f"{key} {n}" for key, n in keys.most_common()) or "none",
        ", ".join(f"{metric} {len(ivs)}" for metric, ivs in history.intervals.items() if ivs) or "none",
        f"{len(charges)} distinct values from {charges[0]} to {charges[-1]} mAh" if charges else "no readings",
        f"{history.capacity_mah:g} mAh" if history.capacity_mah else "not reported")


def _log_file(path, examples=5):
    """Debug log: the kinds of lines of a dump and a few of them, to spot unexpected output."""
    kinds, unexpected, versions, crlf = Counter(), [], [], 0
    first, last = [], deque(maxlen=examples)
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for line in f:
            crlf += line.endswith("\r\n")
            line = line.rstrip("\r\n")
            parts = line.split(",", 4)
            if line.startswith(H):
                kinds["h"] += 1
                if len(first) < examples:
                    first.append(line)
                last.append(line)
            elif line.startswith(HSP):
                kinds["hsp"] += 1
            elif len(parts) >= 4 and parts[0].isdigit():  # e.g. 9,0,i,vers,...: section "i,vers"
                kinds[f"{parts[2]},{parts[3]}"] += 1
                if parts[3] == "vers":
                    versions.append(line)
            elif not line:
                kinds["blank"] += 1
            else:
                kinds["unexpected"] += 1
                if len(unexpected) < examples:
                    unexpected.append(line)
    lines = [f"Dump {path}: {sum(kinds.values())} lines ({crlf} ending with CR LF)",
             "  lines by kind: " + (", ".join(f"{kind} {n}" for kind, n in kinds.most_common()) or "none"),
             debug.indent("version", "\n".join(versions) or "none")]
    if first:
        lines.append(debug.indent("first history lines", "\n".join(first)))
        lines.append(debug.indent("last history lines", "\n".join(last)))
    if unexpected:
        lines.append(debug.indent(f"first unexpected lines (of {kinds['unexpected']})", "\n".join(unexpected)))
    logger.debug("\n".join(lines))
