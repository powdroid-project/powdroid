"""Parse the battery history ("9,h" checkin lines) of an Android bugreport.

This replaces the Go battery-historian `history-parse` tool previously used by
PowDroid. Only the metrics PowDroid reports on are extracted, following the
semantics of battery-historian's parseutils:

- integer states (voltage, coulomb counter) hold their value until the next change;
- boolean states (+X / -X) are on between their + and - transitions;
- service states (top app, wakelock_in) reference the history string pool.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core import PowDroidError

VERSION = "9"
H = f"{VERSION},h,"
HSP = f"{VERSION},hsp,"

INT_METRICS = {"Bv": "Voltage", "Bcc": "Coulomb charge"}
BOOL_METRICS = {
    "S": "Screen",
    "g": "GPS",
    "Pr": "Mobile radio active",
    "W": "Wifi on",
    "Wr": "Wifi radio",
    "a": "Audio",
    "ca": "Camera",
    "v": "Video",
}
SERVICE_METRICS = {"Etp": "Top app", "Ewl": "Wakelock_in"}
METRICS = list(INT_METRICS.values()) + list(BOOL_METRICS.values()) + list(SERVICE_METRICS.values())

_TIME_RE = re.compile(r"^(\d+):(?:RESET:)?TIME:(\d+)$")
_ITEM_RE = re.compile(r"^([+-]?)(\w+)(?:=(.*))?$")
_POOL_RE = re.compile(r'^(\d+),(-?\d+),(.*)$')
_DELTA_RE = re.compile(r"^(\d+)(.*)$")


@dataclass
class Interval:
    start: int
    end: int
    value: object


class HistoryError(PowDroidError):
    """Raised when no usable battery history can be found."""


def read_history_lines(path):
    """Return the history lines of a bugreport (.zip from `adb bugreport` or plain .txt).

    Bugreports are large (often 50-150 MB), so the text is streamed instead of loaded whole.
    """
    path = Path(path)
    if not zipfile.is_zipfile(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            return history_lines(f)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        entry = None
        if "main_entry.txt" in names:
            entry = archive.read("main_entry.txt").decode().strip()
        if entry not in names:
            candidates = [i for i in archive.infolist() if i.filename.endswith(".txt")
                          and Path(i.filename).name.startswith("bugreport")]
            if not candidates:
                raise HistoryError(f"No bugreport text file found in {path.name}")
            entry = max(candidates, key=lambda i: i.file_size).filename
        with io.TextIOWrapper(archive.open(entry), encoding="utf-8", errors="replace") as f:
            return history_lines(f)


def history_lines(lines):
    """Return the battery history lines, preferring the CHECKIN BATTERYSTATS section."""
    prefixes = (H, HSP, "NEXT:")
    everywhere, section, in_section = [], None, False
    for line in lines:
        if "CHECKIN BATTERYSTATS" in line:
            section, in_section = [], True
            continue
        if in_section and line.startswith("------ "):
            in_section = False
        line = line.strip()
        if line.startswith(prefixes):
            (section if in_section else everywhere).append(line)
    return section if section is not None else everywhere


def _split(line):
    """Split a '9,h,...' line into (delta, rest) where rest is either ':TAG...' or ',items'."""
    m = _DELTA_RE.match(line[len(H):])
    if not m:
        return None, ""
    return int(m.group(1)), m.group(2)


def _fix_timeline(lines):
    """Make TIME statements consistent with the last one, as battery-historian does.

    The device clock can jump during a session (e.g. network time sync). Walking
    backwards from the last TIME statement and subtracting deltas gives the
    timestamps that match the final clock, which is the one PowDroid compares to.
    """
    lines = list(lines)
    time = None
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if not line.startswith(H):
            continue
        delta, rest = _split(line)
        if delta is None:
            continue
        if time is not None:
            if rest in (":START", ":SHUTDOWN"):
                time = None
                continue
            if ":TIME:" in rest:
                lines[i] = line.split(":TIME:")[0] + f":TIME:{time}"
            time -= delta
        else:
            m = _TIME_RE.match(f"{delta}{rest}")
            if m:
                time = int(m.group(2)) - delta
    return lines


class _Parser:
    def __init__(self):
        self.intervals = {m: [] for m in METRICS}
        self.pool = {}
        self.now = None
        self.summary_start = None
        self.ints = {}  # metric -> (start, value)
        self.bools = {}  # metric -> start
        self.services = {m: {} for m in SERVICE_METRICS.values()}  # metric -> {idx: (start, name)}

    def close_all(self):
        if self.now is None:
            return
        for metric, (start, value) in self.ints.items():
            self._add(metric, start, self.now, value)
        for metric, start in self.bools.items():
            self._add(metric, start, self.now, True)
        for metric, active in self.services.items():
            for start, name in active.values():
                self._add(metric, start, self.now, name)
            active.clear()
        self.ints.clear()
        self.bools.clear()

    def _add(self, metric, start, end, value):
        if end >= start:
            self.intervals[metric].append(Interval(start, end, value))

    def line(self, line):
        if line.startswith("NEXT:"):
            self.pool.clear()
            return True
        if line.startswith(HSP):
            m = _POOL_RE.match(line[len(HSP):])
            if m:
                self.pool[m.group(1)] = m.group(3).strip().strip('"')
            return True

        delta, rest = _split(line)
        if delta is None:
            return True
        if rest.startswith(":"):
            tag = rest[1:]
            if tag == "*OVERFLOW*":
                return False
            if tag.startswith("RESET:TIME:"):
                self.close_all()
                self.now = self.summary_start = int(tag.split(":")[-1])
            elif tag.startswith("TIME:"):
                self.now = int(tag.split(":")[-1])
                if self.summary_start is None:
                    self.summary_start = self.now
            elif tag == "START":
                self.close_all()
            elif tag == "SHUTDOWN" and self.now is not None:
                self.now += delta
            return True

        if self.now is None:
            return True  # No absolute time yet: nothing can be placed on the timeline.
        self.now += delta
        for item in rest.split(",")[1:]:
            m = _ITEM_RE.match(item)
            if m:
                self.item(*m.groups())
        return True

    def item(self, tr, key, value):
        now = self.now
        if key in INT_METRICS:
            metric = INT_METRICS[key]
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return
            if metric in self.ints:
                start, old = self.ints[metric]
                self._add(metric, start, now, old)
            self.ints[metric] = (now, parsed)
        elif key in BOOL_METRICS and tr:
            metric = BOOL_METRICS[key]
            if tr == "+" and metric not in self.bools:
                self.bools[metric] = now
            elif tr == "-":
                # A '-' without '+' means it was already on when the history started.
                start = self.bools.pop(metric, self.summary_start)
                self._add(metric, start, now, True)
        elif key in SERVICE_METRICS and value is not None:
            metric = SERVICE_METRICS[key]
            active = self.services[metric]
            name = self.pool.get(value, value)
            if tr == "+":
                active.setdefault(value, (now, name))
            elif tr == "-":
                start, name = active.pop(value, (self.summary_start, name))
                self._add(metric, start, now, name)
            else:
                active.setdefault(value, (self.summary_start, name))


def parse_lines(lines):
    """Parse history lines into {metric name: [Interval, ...]} sorted by start time."""
    if not any(l.startswith(H) for l in lines):
        raise HistoryError("No battery history found in the bugreport")
    parser = _Parser()
    for line in _fix_timeline(lines):
        if not parser.line(line):
            break
    parser.close_all()
    for values in parser.intervals.values():
        values.sort(key=lambda iv: (iv.start, iv.end))
    return parser.intervals


def parse_history(text):
    return parse_lines(history_lines(text.splitlines()))


def parse_bugreport(path):
    return parse_lines(read_history_lines(path))
