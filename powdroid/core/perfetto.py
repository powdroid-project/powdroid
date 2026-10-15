"""Optional battery measurement with Perfetto, Android's system tracing service (Android 10+).

The batterystats history only gets a coulomb counter reading when the health HAL pushes
one (on some phones once a minute), in whole mAh. Perfetto's android.power data source
runs on the phone and polls the same fuel gauge through the health HAL every POLL_MS while
the phone is awake: charge counter in µAh, current in µA, voltage in µV and battery level.
The trace keeps running while the phone is unplugged: PowDroid starts it before the phone
is unplugged, then stops and copies it once the phone is plugged back in. On phones with
on-device power monitors (ODPM, mostly recent Pixels), it also records the energy of each
power rail.

The batterystats history is still read for the plugged, screen, app and wakelock states;
the trace replaces its battery readings (battery_history, charge_source).

The trace is a protobuf file. The few fields PowDroid needs are decoded with the standard
library, using the field numbers of perfetto's protos/perfetto/trace/*.proto.
"""

import logging
import re
import statistics
import struct
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from pathlib import Path

from powdroid.core import PowDroidError, adb, debug, metrics
from powdroid.core.history import Interval

logger = logging.getLogger("powdroid.perfetto")

REMOTE_PATH = "/data/misc/perfetto-traces/powdroid.pftrace"  # perfetto may only write in this folder
# Matches the perfetto command writing REMOTE_PATH, but not the shell running pkill or pgrep
# with this pattern (its command line contains "[p]owdroid", not "powdroid"), as long as that
# command line does not also contain REMOTE_PATH.
PROCESS_PATTERN = "perfetto.*[p]owdroid.pftrace"
POLL_MS = 500
MIN_SDK = 29  # Android 10: battery counters and power rails in the android.power data source
VOLTAGE_SDK = 35  # BATTERY_COUNTER_VOLTAGE was added to perfetto at the end of 2023 (Android 15)
MAX_DURATION_MS = 24 * 3600 * 1000  # the trace stops by itself if PowDroid never stops it
MAX_FILE_SIZE = 256 * 1024 * 1024  # bytes, at most, of the phone's storage the trace may use
GAP_MS = 3 * POLL_MS  # longer without a poll: the phone was asleep (suspended)
MIN_SEGMENT_MS = 5000  # see _currents

CONFIG = """\
buffers {{
  size_kb: 4096
  fill_policy: RING_BUFFER
}}
data_sources {{
  config {{
    name: "android.power"
    android_power_config {{
      battery_poll_ms: {poll_ms}
{counters}
      collect_power_rails: true
    }}
  }}
}}
write_into_file: true
file_write_period_ms: 2500
max_file_size_bytes: {max_file_size}
duration_ms: {duration_ms}
"""

# SIGTERM makes perfetto write the end of the trace and exit; wait for it (up to 30 s).
# The command line is checked first: after a crash, the PID could belong to another process.
STOP_SCRIPT = (
    "p={pid}; if grep -q perfetto /proc/$p/cmdline 2>/dev/null; then kill -TERM $p; i=0; "
    "while [ -d /proc/$p ] && [ $i -lt 150 ]; do sleep 0.2; i=$((i+1)); done; "
    "[ -d /proc/$p ] && echo running || echo stopped; else echo already-stopped; fi")


class Unavailable(PowDroidError):
    """Raised when Perfetto cannot record on this phone; the message says why."""


class TraceError(PowDroidError):
    """Raised when a trace file cannot be read."""


@dataclass
class Trace:
    """A trace recording on the device."""

    serial: str
    pid: int  # of the perfetto command, running in the background
    voltage: bool  # whether the voltage is recorded (else it comes from the battery history)
    local_path: Path = None  # the copy on this computer, once stopped


def trace_config(voltage=True):
    """The trace config, in protobuf text format."""
    counters = ["CHARGE", "CAPACITY_PERCENT", "CURRENT"] + (["VOLTAGE"] if voltage else [])
    return CONFIG.format(poll_ms=POLL_MS, duration_ms=MAX_DURATION_MS, max_file_size=MAX_FILE_SIZE,
                         counters="\n".join(f"      battery_counters: BATTERY_COUNTER_{c}" for c in counters))


def start(serial):
    """Start recording the battery counters, before the phone is unplugged.

    Raises Unavailable when Perfetto cannot be used: before Android 10, when the tracing
    service is disabled (on Android 10 unless persist.traced.enable is set) or when the
    perfetto command fails.
    """
    try:
        lines = adb.shell(serial, "getprop ro.build.version.sdk; getprop init.svc.traced").splitlines()
        sdk, traced = (line.strip() for line in (lines + ["", ""])[:2])
        if not sdk.isdigit() or int(sdk) < MIN_SDK:
            raise Unavailable(f"it needs Android 10 or newer (API level {MIN_SDK}) and this phone has "
                              f"API level {sdk or 'unknown'}")
        if traced != "running":
            raise Unavailable(f"its tracing service is not running (init.svc.traced is {traced or 'not set'}); "
                              "on Android 10, enable it with: adb shell setprop persist.traced.enable 1")
        # A trace left running by an earlier session that was never collected.
        adb.shell(serial, f"pkill -f '{PROCESS_PATTERN}'; true")
        adb.shell(serial, f"rm -f {REMOTE_PATH}")
        voltage = int(sdk) >= VOLTAGE_SDK
        try:
            pid = _launch(serial, voltage)
        except (adb.AdbError, Unavailable) as e:
            if not voltage:
                raise
            logger.info("perfetto failed with the voltage counter, retrying without it (%s)", e)
            voltage = False
            pid = _launch(serial, voltage)
    except adb.AdbError as e:
        raise Unavailable(f"the perfetto command failed ({e})") from None
    logger.info("Perfetto trace started (PID %d, voltage %srecorded)", pid, "" if voltage else "not ")
    return Trace(serial, pid, voltage)


def _launch(serial, voltage):
    """Start the perfetto command in the background and return its PID once it runs."""
    out = adb.shell(serial, f"perfetto --background --txt -c - -o {REMOTE_PATH}", input=trace_config(voltage))
    pids = re.findall(r"^\s*(\d+)\s*$", out, re.MULTILINE)  # printed when it goes to the background
    if not pids:
        pids = adb.shell(serial, f"pgrep -f '{PROCESS_PATTERN}'; true").split()
    if not pids:
        raise Unavailable(f"perfetto did not start (it printed: {out.strip() or 'nothing'})")
    pid = int(pids[0])
    # In the background, perfetto connects to the tracing service after printing its PID.
    if adb.shell(serial, f"sleep 1; [ -d /proc/{pid} ] && echo running || echo stopped").strip() != "running":
        raise Unavailable("perfetto stopped right after starting (its reason is in the phone's logcat)")
    return pid


def stop(trace, path):
    """Stop the trace and copy it to path, once: a retried collection gets the same file.

    Returns the local path. Raises AdbError or TraceError when no trace can be copied.
    """
    if trace.local_path is not None:
        return trace.local_path
    state = adb.shell(trace.serial, STOP_SCRIPT.format(pid=trace.pid), timeout=60).strip()
    if state == "already-stopped":
        logger.warning("perfetto had already stopped: the trace may end before the session")
    elif state != "stopped":
        logger.warning("perfetto is still writing the trace after 30 s (%s): copying what is written", state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    adb.pull(trace.serial, REMOTE_PATH, path)
    if path.stat().st_size == 0:
        raise TraceError("the trace copied from the phone is empty")
    try:
        adb.shell(trace.serial, f"rm -f {REMOTE_PATH}")
    except adb.AdbError:
        pass  # in the debug log; the next trace replaces it
    trace.local_path = path
    return path


def cancel(trace):
    """Stop the trace without keeping it (best effort: the phone may be unplugged)."""
    if trace.local_path is not None:
        return
    try:
        adb.shell(trace.serial, f"p={trace.pid}; grep -q perfetto /proc/$p/cmdline 2>/dev/null && kill -TERM $p; "
                                f"rm -f {REMOTE_PATH}; true")
    except adb.AdbError:
        pass  # in the debug log; the next session stops it, or it stops after MAX_DURATION_MS


# -- protobuf decoding ------------------------------------------------------

VARINT, FIXED64, LENGTH, FIXED32 = 0, 1, 2, 5  # wire types

# Field numbers, from perfetto's protos/perfetto/trace/*.proto.
PACKET = 1  # Trace.packet
TIMESTAMP, TIMESTAMP_CLOCK_ID, CLOCK_SNAPSHOT, BATTERY, POWER_RAILS = 8, 58, 6, 38, 40  # TracePacket
CLOCKS, PRIMARY_TRACE_CLOCK = 1, 2  # ClockSnapshot
CLOCK_ID, CLOCK_TIMESTAMP = 1, 2  # ClockSnapshot.Clock
REALTIME, BOOTTIME, MAX_BUILTIN_CLOCK = 1, 6, 63  # BuiltinClock
CHARGE_COUNTER_UAH, CAPACITY_PERCENT, CURRENT_UA, BATTERY_NAME, VOLTAGE_UV = 1, 2, 3, 5, 7  # BatteryCounters
RAIL_DESCRIPTOR, ENERGY_DATA = 1, 2  # PowerRails
RAIL_INDEX, RAIL_NAME, SUBSYS_NAME = 1, 2, 3  # PowerRails.RailDescriptor
ENERGY_INDEX, ENERGY_TIMESTAMP_MS, ENERGY = 1, 2, 3  # PowerRails.EnergyData (energy since boot, µWs)


def _varint(buf, pos):
    value = shift = 0
    while True:
        if pos >= len(buf):
            raise TraceError("truncated protobuf varint")
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
        if shift >= 70:
            raise TraceError("invalid protobuf varint")


def fields(buf):
    """Yield (field number, wire type, value) for each field of a protobuf message.

    Varints are unsigned integers, length-delimited fields (nested messages, strings)
    memoryviews and fixed-size fields raw bytes.
    """
    buf = memoryview(buf)
    pos, end = 0, len(buf)
    while pos < end:
        tag, pos = _varint(buf, pos)
        number, wire = tag >> 3, tag & 7
        if wire == VARINT:
            value, pos = _varint(buf, pos)
        elif wire == LENGTH:
            size, pos = _varint(buf, pos)
            value, pos = buf[pos:pos + size], pos + size
        elif wire in (FIXED64, FIXED32):
            size = 8 if wire == FIXED64 else 4
            value, pos = bytes(buf[pos:pos + size]), pos + size
        else:
            raise TraceError(f"unsupported protobuf wire type {wire} (field {number})")
        if pos > end:
            raise TraceError(f"truncated protobuf field {number}")
        yield number, wire, value


def _message(buf):
    """The fields of a message by number (the last one of each number)."""
    return {number: value for number, _, value in fields(buf)}


def _int64(value):
    """A varint read as a two's complement int64."""
    return value - (1 << 64) if value >= 1 << 63 else value


def _text(value):
    return bytes(value).decode("utf-8", "replace")


# -- trace contents ---------------------------------------------------------

@dataclass
class Sample:
    """One poll of the battery counters (None: not reported)."""

    time_ms: int  # device time
    charge_uah: int = None
    level_pct: float = None
    current_ua: int = None
    voltage_uv: int = None


@dataclass
class Rail:
    """A power rail measured by the on-device power monitors."""

    name: str
    subsystem: str
    column: str  # its CSV column
    readings: list = field(default_factory=list)  # [(device time ms, energy since boot in µWs)]


@dataclass
class TraceData:
    samples: list  # [Sample], by time
    rails: list  # [Rail]
    packets: int


def parse_file(path):
    with open(path, "rb") as f:
        return parse(f.read())


def parse(data):
    """Decode the battery counters and power rails of a trace."""
    try:
        return _parse(data)
    except (TypeError, ValueError, KeyError, struct.error) as e:  # fields of unexpected types
        raise TraceError(f"unexpected trace contents ({e!r})") from None


def _parse(data):
    offsets, primary = {}, BOOTTIME  # clock id -> REALTIME minus that clock (ns)
    batteries, descriptors, energies, packets = {}, {}, [], 0
    for number, wire, packet in fields(data):
        if number != PACKET or wire != LENGTH:
            continue
        packets += 1
        p = _message(packet)
        clock, ts = p.get(TIMESTAMP_CLOCK_ID), p.get(TIMESTAMP)
        if CLOCK_SNAPSHOT in p:
            snapshot = _message(p[CLOCK_SNAPSHOT])
            primary = snapshot.get(PRIMARY_TRACE_CLOCK, primary)
            clocks = {}
            for n, _, c in fields(p[CLOCK_SNAPSHOT]):
                if n == CLOCKS:
                    c = _message(c)
                    clocks[c.get(CLOCK_ID, 0)] = c.get(CLOCK_TIMESTAMP, 0)
            if REALTIME in clocks:  # the last snapshot wins, as the last TIME of the battery history
                offsets.update({k: clocks[REALTIME] - v for k, v in clocks.items() if k <= MAX_BUILTIN_CLOCK})
        if BATTERY in p and ts is not None:
            b = _message(p[BATTERY])
            name = _text(b[BATTERY_NAME]) if BATTERY_NAME in b else ""
            batteries.setdefault(name, []).append((clock, ts, Sample(
                0,
                _int64(b[CHARGE_COUNTER_UAH]) if CHARGE_COUNTER_UAH in b else None,
                struct.unpack("<f", b[CAPACITY_PERCENT])[0] if CAPACITY_PERCENT in b else None,
                _int64(b[CURRENT_UA]) if CURRENT_UA in b else None,
                _int64(b[VOLTAGE_UV]) if VOLTAGE_UV in b else None)))
        if POWER_RAILS in p:
            for n, wire, value in fields(p[POWER_RAILS]):
                m = _message(value) if wire == LENGTH else {}
                if n == RAIL_DESCRIPTOR:
                    descriptors[m.get(RAIL_INDEX, 0)] = (_text(m.get(RAIL_NAME, b"")), _text(m.get(SUBSYS_NAME, b"")))
                elif n == ENERGY_DATA and ENERGY in m:
                    index = m.get(ENERGY_INDEX, 0)
                    if m.get(ENERGY_TIMESTAMP_MS):  # since boot
                        energies.append((index, BOOTTIME, m[ENERGY_TIMESTAMP_MS] * 1_000_000, m[ENERGY]))
                    elif ts is not None:
                        energies.append((index, clock, ts, m[ENERGY]))
    if packets and not offsets:
        raise TraceError("the trace has no clock snapshot to convert its times to device time")

    def device_ms(clock, ns):
        offset = offsets.get(primary if clock is None else clock)
        return None if offset is None else round((ns + offset) / 1e6)

    samples = []
    if batteries:
        if len(batteries) > 1:
            logger.info("Battery counters of several batteries: %s", ", ".join(map(repr, batteries)))
        name = "" if "" in batteries else max(batteries, key=lambda n: len(batteries[n]))
        for clock, ts, sample in batteries[name]:
            sample.time_ms = device_ms(clock, ts)
            if sample.time_ms is not None:
                samples.append(sample)
        samples.sort(key=lambda s: s.time_ms)

    rails, columns = {}, set()
    for index, clock, ts, energy in energies:
        time_ms = device_ms(clock, ts)
        if time_ms is None:
            continue
        if index not in rails:
            name, subsystem = descriptors.get(index, ("", ""))
            name = name or f"rail{index}"
            column = f"{metrics.RAIL_PREFIX}{re.sub(r'[^0-9A-Za-z]+', '_', name).strip('_')}_j"
            if column in columns or column in metrics.COLUMNS:
                column = f"{column[:-2]}_{index}_j"
            columns.add(column)
            rails[index] = Rail(name, subsystem, column)
        rails[index].readings.append((time_ms, energy))
    for rail in rails.values():
        rail.readings.sort()
    trace = TraceData(samples, [rails[i] for i in sorted(rails)], packets)
    if logger.isEnabledFor(logging.DEBUG):
        _log_summary(trace)
    return trace


def _log_summary(trace):
    """Debug log: what the trace contains, e.g. to see why a phone gives no data."""
    s = trace.samples
    lines = [f"Perfetto trace: {trace.packets} packets, {len(s)} battery polls"
             + (f" from {debug.ms(s[0].time_ms)} to {debug.ms(s[-1].time_ms)}" if s else "")]
    for name in ("charge_uah", "current_ua", "voltage_uv", "level_pct"):
        values = [getattr(sample, name) for sample in s if getattr(sample, name) is not None]
        lines.append(f"  {name}: " + (f"{len(values)} values, {len(set(values))} distinct, from {min(values)} to "
                                      f"{max(values)}, median {statistics.median(values)}" if values else "none"))
    gaps = [b.time_ms - a.time_ms for a, b in zip(s, s[1:])]
    if gaps:
        lines.append(f"  time between polls: median {statistics.median(gaps)} ms, longest {max(gaps)} ms, "
                     f"{sum(g > GAP_MS for g in gaps)} longer than {GAP_MS} ms")
    lines.append("  power rails: " + (", ".join(f"{r.name} ({r.subsystem}, {len(r.readings)} readings)"
                                                for r in trace.rails) or "none"))
    logger.debug("\n".join(lines))


# -- measurements -----------------------------------------------------------

def _steps(values, merge=True):
    """[Interval] holding each (time, value) until the next one; repeated values are merged."""
    steps = []
    for k, (time_ms, value) in enumerate(values):
        end = values[k + 1][0] if k + 1 < len(values) else time_ms
        if merge and steps and steps[-1].value == value:
            steps[-1] = Interval(steps[-1].start, end, value)
        else:
            steps.append(Interval(time_ms, end, value))
    return steps


def charge_source(trace, plugged):
    """The metrics.ChargeSource of the trace's coulomb counter, or None if it has none.

    plugged is the [Interval] of the plugged state, from the battery history. The
    resolution is the median change of the counter: the gauge updates it less often than
    it is polled, and some count in steps of a fraction of a mAh, not of a µAh.
    """
    samples = [s for s in trace.samples if s.charge_uah]  # always 0 without a coulomb counter
    if len({s.charge_uah for s in samples}) < 2:
        return None
    readings = _steps([(s.time_ms, s.charge_uah / 1000) for s in samples])
    resolution = statistics.median(abs(a.value - b.value) for a, b in zip(readings, readings[1:]))
    return metrics.ChargeSource(metrics.PERFETTO, readings, float(f"{resolution:.2g}"), _currents(samples, plugged))


def _currents(samples, plugged):
    """Intervals of current (mA, positive when discharging) between polls.

    The charge comes from the coulomb counter and the shape of the curve from the current
    samples:
    - the polls are cut into segments at counter changes (the polls where a new value is
      first seen) at least MIN_SEGMENT_MS apart: a shorter segment would mostly measure
      when the gauge happened to update its counter. Around a gap between polls (the
      phone slept), the last change before it and the first one after it are kept, so
      that the segment holding the gap is mostly asleep;
    - the charge used during a segment is spread over its poll intervals in proportion to
      the current samples (the mean of the samples at both ends of each interval), or
      evenly over a segment holding a gap: only the counter knows what the phone used
      while it slept.
    Android reports a negative current while discharging, but some phones report a
    positive one, or mA instead of µA: only the shape of the samples is used, so neither
    matters. Segments never span a plugged-in time (the counter then measures charging):
    as with the battery history, the current is unknown from a plug change, or the start
    or end of the trace, to the nearest counter change.
    """
    t = [s.time_ms for s in samples]
    q = [s.charge_uah for s in samples]
    i = [s.current_ua for s in samples]
    unplugged = [c for c, s in zip(i, samples)
                 if c is not None and not any(p.start <= s.time_ms < p.end for p in plugged)]
    sign = 1 if unplugged and statistics.median(unplugged) > 0 else -1
    gaps = [0]  # gaps[k]: number of gaps between the polls before poll k
    for k in range(1, len(t)):
        gaps.append(gaps[-1] + (t[k] - t[k - 1] > GAP_MS))

    currents, run = [], 0  # run: first poll of the current run of polls with no plugged-in time between them
    for k in range(1, len(t) + 1):
        if k == len(t) or any(p.start < t[k] and p.end > t[k - 1] for p in plugged):
            changes = [c for c in range(run + 1, k) if q[c] != q[c - 1]]
            anchors = []
            for j, c in enumerate(changes):
                following = changes[j + 1] if j + 1 < len(changes) else None
                if (not anchors or t[c] - t[anchors[-1]] >= MIN_SEGMENT_MS or following is None
                        or gaps[following] > gaps[c] or gaps[c] > gaps[anchors[-1]]):
                    anchors.append(c)
            currents += _segment_currents(anchors, t, q, i, sign, gaps)
            run = k
    return currents


def _segment_currents(anchors, t, q, i, sign, gaps):
    """The currents of the segments between consecutive anchors (see _currents)."""
    currents = []
    for a, b in zip(anchors, anchors[1:]):
        if t[b] <= t[a]:
            continue
        used = q[a] - q[b]  # µAh; over ms, × 3600 for mA
        weights = None
        if gaps[b] == gaps[a] and all(i[k] is not None for k in range(a, b + 1)):
            weights = [max(sign * (i[k] + i[k + 1]) / 2, 0) * (t[k + 1] - t[k]) for k in range(a, b)]
        if weights and sum(weights) > 0:
            total = sum(weights)
            currents += [Interval(t[k], t[k + 1], used * 3600 * w / total / (t[k + 1] - t[k]))
                         for k, w in zip(range(a, b), weights) if t[k + 1] > t[k]]
        else:
            currents.append(Interval(t[a], t[b], used * 3600 / (t[b] - t[a])))
    return currents


def battery_history(hist, trace, source):
    """A copy of the battery history whose battery readings come from the trace.

    The coulomb counter, the voltage and the battery level, when the trace has them,
    replace those of the history: the trace reads them at every poll.
    """
    intervals = dict(hist.intervals)
    intervals["charge_mah"] = source.readings
    voltages = [(s.time_ms, round(s.voltage_uv / 1000)) for s in trace.samples if s.voltage_uv]
    if voltages:
        intervals["voltage_mv"] = _steps(voltages, merge=False)  # interpolated between readings
    levels = [(s.time_ms, round(s.level_pct)) for s in trace.samples if s.level_pct is not None]
    if levels:
        intervals["battery_level_pct"] = _steps(levels)
    return replace(hist, intervals=intervals)


def _energy_between(readings):
    """A function giving the energy (µWs) used between two times, or None if unknown.

    The counters accumulate energy since boot, also while the phone sleeps: the energy at
    a given time is interpolated between readings. A counter that goes back (it was reset)
    leaves its interval unknown.
    """
    times = [r[0] for r in readings]
    values = [r[1] for r in readings]
    resets = [(times[k], times[k + 1]) for k in range(len(times) - 1) if values[k + 1] < values[k]]

    def at(t):
        k = bisect_right(times, t) - 1
        if k < 0 or t > times[-1]:
            return None
        if k == len(times) - 1:
            return values[k]
        return values[k] + (values[k + 1] - values[k]) * (t - times[k]) / (times[k + 1] - times[k])

    def between(start, end):
        a, b = at(start), at(end)
        if a is None or b is None or any(r0 < end and r1 > start for r0, r1 in resets):
            return None
        return b - a

    return between


def add_rail_energy(rows, rails):
    """Add each rail's energy during each row (J), in the rail's column.

    The rails sit downstream of the battery, so their energy stays valid while the phone
    is plugged in.
    """
    for rail in rails:
        between = _energy_between(rail.readings)
        for row in rows:
            energy = between(row["start_ms"], row["end_ms"])
            row[rail.column] = None if energy is None else energy / 1e6


def rail_totals(rails, start_ms, stop_ms):
    """Each rail's energy and mean power over [start_ms, stop_ms], for the session JSON."""
    totals = []
    for rail in rails:
        energy = _energy_between(rail.readings)(start_ms, stop_ms)
        totals.append({
            "name": rail.name, "subsystem": rail.subsystem, "column": rail.column,
            "energy_j": None if energy is None else energy / 1e6,
            "mean_power_w": None if energy is None or stop_ms <= start_ms else energy / 1e3 / (stop_ms - start_ms),
        })
    return totals


def describe(trace, source):
    """What the session JSON records about the trace."""
    gaps = [b.time_ms - a.time_ms for a, b in zip(trace.samples, trace.samples[1:])]
    currents = [s.current_ua for s in trace.samples if s.current_ua is not None]
    return {
        "battery_polls": len(trace.samples),
        "median_poll_interval_ms": statistics.median(gaps) if gaps else None,
        "longest_poll_interval_ms": max(gaps, default=None),
        "counters": [name for name in ("charge_uah", "current_ua", "voltage_uv", "level_pct")
                     if any(getattr(s, name) is not None for s in trace.samples)],
        "charge_resolution_mah": source.resolution_mah if source else None,
        "median_current_sample_ua": statistics.median(currents) if currents else None,
        "power_rails": len(trace.rails),
    }
