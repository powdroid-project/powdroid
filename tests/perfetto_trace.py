"""Write Perfetto traces for the tests and tests/fake_adb.py.

Only the fields core/perfetto.py reads, plus a few it must skip. The field numbers are
written here independently of core/perfetto.py, from perfetto's protos
(protos/perfetto/trace/trace.proto, trace_packet.proto, clock_snapshot.proto,
power/battery_counters.proto and power/power_rails.proto).
"""

import math
import struct

REALTIME, MONOTONIC, BOOTTIME = 1, 3, 6  # BuiltinClock


def varint(value):
    value &= (1 << 64) - 1  # a negative int64 is written as its two's complement
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def tag(number, wire):
    return varint(number << 3 | wire)


def uint(number, value):
    return tag(number, 0) + varint(value)


def message(number, *parts):
    body = b"".join(parts)
    return tag(number, 2) + varint(len(body)) + body


def string(number, text):
    return message(number, text.encode())


def packet(*parts, timestamp=None, clock_id=None):
    """A Trace.packet (1): TracePacket with timestamp (8) and timestamp_clock_id (58)."""
    header = ([uint(8, timestamp)] if timestamp is not None else []) + (
        [uint(58, clock_id)] if clock_id is not None else [])
    return message(1, *header, *parts)


def clock_snapshot(clocks, primary=None):
    """TracePacket.clock_snapshot (6): clocks (1) of clock_id (1) and timestamp (2), primary_trace_clock (2)."""
    return message(6, *(message(1, uint(1, clock), uint(2, ns)) for clock, ns in clocks.items()),
                   *([uint(2, primary)] if primary is not None else []))


def battery(charge_uah=None, level_pct=None, current_ua=None, voltage_uv=None, name=None):
    """TracePacket.battery (38): BatteryCounters."""
    parts = []
    if charge_uah is not None:
        parts.append(uint(1, charge_uah))
    if level_pct is not None:
        parts.append(tag(2, 5) + struct.pack("<f", level_pct))
    if current_ua is not None:
        parts.append(uint(3, current_ua))
    if name is not None:
        parts.append(string(5, name))
    if voltage_uv is not None:
        parts.append(uint(7, voltage_uv))
    return message(38, *parts)


def power_rails(descriptors=(), energy=(), session_uuid=None):
    """TracePacket.power_rails (40): rail_descriptor (1) [(index, name, subsystem)] and
    energy_data (2) [(index, timestamp_ms since boot, energy in µWs)]."""
    return message(40, *(message(1, uint(1, i), string(2, name), string(3, subsystem))
                         for i, name, subsystem in descriptors),
                   *(message(2, uint(1, i), uint(2, ms), uint(3, uws)) for i, ms, uws in energy),
                   *([uint(3, session_uuid)] if session_uuid is not None else []))


def skipped_fields():
    """Fields the reader must skip: a trace config (33), a fixed64 and a fixed32."""
    return message(33, string(1, "ignored")) + tag(99, 1) + struct.pack("<Q", 1) + tag(98, 5) + b"\0\0\0\0"


def simulate(start_ms, stop_ms, current_ma, poll_ms=500, resolution_uah=1, charge_uah=3_000_000,
             current_scale=-1000, voltage=True, asleep=lambda t: False, rails=(), boot_ms=None, step_ms=10,
             counter=True):
    """A trace of a battery whose current is current_ma(t) at device time t (ms), positive when discharging.

    The coulomb counter integrates it every step_ms and counts in steps of resolution_uah
    (counter=False: it reports 0, as phones without one do).
    The battery is polled every poll_ms from start_ms to stop_ms, except while asleep(t).
    Current samples are current_ma(t) * current_scale (Android: µA, negative when discharging).
    rails are (name, subsystem, constant power in W). Times are written in BOOTTIME, the
    phone having booted at boot_ms (device time).
    """
    boot_ms = start_ms - 3_600_000 if boot_ms is None else boot_ms

    def boottime(t):
        return (t - boot_ms) * 1_000_000

    def snapshot(t):
        return packet(clock_snapshot({REALTIME: t * 1_000_000, MONOTONIC: boottime(t) - 5_000_000_000,
                                      BOOTTIME: boottime(t)}))

    packets = [snapshot(start_ms), packet(skipped_fields())]
    if rails:
        packets.append(packet(power_rails([(i, name, subsystem) for i, (name, subsystem, _) in enumerate(rails)]),
                              timestamp=boottime(start_ms)))
    used, t, next_poll = 0.0, start_ms, start_ms  # µAh
    while t <= stop_ms:
        current = current_ma(t)
        if t >= next_poll:
            next_poll += poll_ms
            if not asleep(t):
                charge = resolution_uah * math.floor((charge_uah - used) / resolution_uah) if counter else 0
                packets.append(packet(battery(charge, 90.0, round(current * current_scale),
                                              round((4000 - current / 100) * 1000) if voltage else None),
                                      timestamp=boottime(t)))
                if rails:
                    packets.append(packet(power_rails(energy=[(i, t - boot_ms, round(power * (t - boot_ms) * 1000))
                                                              for i, (_, _, power) in enumerate(rails)]),
                                          timestamp=boottime(t)))
        used += current * step_ms / 3600
        t += step_ms
    packets.append(snapshot(stop_ms))
    return b"".join(packets)
