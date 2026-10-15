"""Perfetto traces: protobuf decoding, battery counters, current estimate, power rails, sessions."""

import json
import struct
import tempfile
import unittest
from pathlib import Path

from powdroid.core import history, metrics, perfetto, session
from powdroid.core.history import Interval
from tests import perfetto_trace as pt
from tests.fixtures import HISTORY, T0

S = 1_000_000_000  # ns


def currents_over(source, start, end):
    """Charge (mAh) of the source's currents between two device times."""
    return sum(iv.value * (min(iv.end, end) - max(iv.start, start)) / 3.6e6
               for iv in source.currents if iv.end > start and iv.start < end)


def current_at(source, t):
    return next(iv.value for iv in source.currents if iv.start <= t < iv.end)


class ProtobufTest(unittest.TestCase):
    def test_every_wire_type(self):
        data = (pt.uint(1, 150) + pt.uint(2, -5) + pt.tag(3, 1) + struct.pack("<d", 1.5)
                + pt.tag(4, 5) + struct.pack("<f", 2.5) + pt.message(5, pt.uint(1, 7)) + pt.string(6, "µA"))
        fields = list(perfetto.fields(data))
        self.assertEqual([(n, w) for n, w, _ in fields], [(1, 0), (2, 0), (3, 1), (4, 5), (5, 2), (6, 2)])
        self.assertEqual(fields[0][2], 150)
        self.assertEqual(perfetto._int64(fields[1][2]), -5)
        self.assertEqual(struct.unpack("<d", fields[2][2])[0], 1.5)
        self.assertEqual(struct.unpack("<f", fields[3][2])[0], 2.5)
        self.assertEqual(perfetto._message(fields[4][2]), {1: 7})
        self.assertEqual(perfetto._text(fields[5][2]), "µA")

    def test_malformed(self):
        data = pt.message(1, pt.uint(1, 300))
        for broken in (data[:-1], data[:2], b"\x80", pt.tag(1, 3)):
            with self.assertRaises(perfetto.TraceError):
                list(perfetto.fields(broken))
        with self.assertRaises(perfetto.TraceError):
            perfetto.parse(pt.packet(pt.clock_snapshot({1: 0, 6: 0})) + data[:-1])


class ParseTest(unittest.TestCase):
    def snapshot(self, realtime_ms=T0, boottime_s=1000, **kw):
        return pt.packet(pt.clock_snapshot({pt.REALTIME: realtime_ms * 10**6, pt.BOOTTIME: boottime_s * S}, **kw))

    def test_battery_counters(self):
        trace = perfetto.parse(
            pt.packet(pt.skipped_fields())
            + pt.packet(pt.battery(2_999_500, 87.5, -312_000, 3_912_000), timestamp=1000 * S + 500_000_000)
            + self.snapshot()
            + pt.packet(pt.battery(charge_uah=2_999_400), timestamp=(T0 + 1000) * 10**6, clock_id=pt.REALTIME)
            + pt.packet(pt.battery(charge_uah=1), timestamp=5, clock_id=64)  # a sequence-scoped clock: skipped
            + pt.packet(pt.battery(charge_uah=2)))  # no timestamp: skipped
        self.assertEqual(trace.packets, 6)
        self.assertEqual(trace.samples, [perfetto.Sample(T0 + 500, 2_999_500, 87.5, -312_000, 3_912_000),
                                         perfetto.Sample(T0 + 1000, 2_999_400)])
        self.assertEqual(trace.rails, [])

    def test_times_follow_the_last_clock_snapshot(self):
        # The wall clock was set 10 s back during the trace: times are aligned on the last snapshot.
        trace = perfetto.parse(self.snapshot(T0 + 10_000, 1000) + pt.packet(pt.battery(5), timestamp=1001 * S)
                               + self.snapshot(T0 + 1000, 1001))
        self.assertEqual(trace.samples[0].time_ms, T0 + 1000)

    def test_primary_trace_clock(self):
        clocks = {pt.REALTIME: T0 * 10**6, pt.MONOTONIC: 900 * S, pt.BOOTTIME: 1000 * S}
        trace = perfetto.parse(pt.packet(pt.clock_snapshot(clocks, primary=pt.MONOTONIC))
                               + pt.packet(pt.battery(5), timestamp=901 * S))
        self.assertEqual(trace.samples[0].time_ms, T0 + 1000)

    def test_clock_snapshot_needed(self):
        with self.assertRaisesRegex(perfetto.TraceError, "no clock snapshot"):
            perfetto.parse(pt.packet(pt.battery(5), timestamp=S))
        self.assertEqual(perfetto.parse(b""), perfetto.TraceData([], [], 0))

    def test_several_batteries(self):
        trace = perfetto.parse(self.snapshot() + pt.packet(pt.battery(1, name="aux"), timestamp=1000 * S)
                               + pt.packet(pt.battery(2), timestamp=1000 * S))
        self.assertEqual([s.charge_uah for s in trace.samples], [2])  # the main (unnamed) battery

    def test_power_rails(self):
        trace = perfetto.parse(
            self.snapshot()
            + pt.packet(pt.power_rails([(0, "S4M_VDD_CPUCL0", "CPU(LITTLE)"), (1, "VSYS PWR-DISPLAY", "Display"),
                                        (2, "VSYS_PWR_DISPLAY", "")], session_uuid=7))
            + pt.packet(pt.power_rails(energy=[(0, 1_000_000, 2_000_000), (1, 1_000_000, 10), (3, 1_000_000, 1)]))
            # Without timestamp_ms, the packet's time is used.
            + pt.packet(pt.message(40, pt.message(2, pt.uint(1, 0), pt.uint(3, 3_500_000))), timestamp=1001 * S)
            + pt.packet(pt.power_rails(energy=[(2, 1_000_500, 4)])))
        self.assertEqual([(r.name, r.subsystem, r.column) for r in trace.rails], [
            ("S4M_VDD_CPUCL0", "CPU(LITTLE)", "rail_S4M_VDD_CPUCL0_j"),
            ("VSYS PWR-DISPLAY", "Display", "rail_VSYS_PWR_DISPLAY_j"),
            ("VSYS_PWR_DISPLAY", "", "rail_VSYS_PWR_DISPLAY_2_j"),  # same column name: made unique
            ("rail3", "", "rail_rail3_j")])  # energy of an undescribed rail
        self.assertEqual(trace.rails[0].readings, [(T0, 2_000_000), (T0 + 1000, 3_500_000)])
        self.assertEqual(trace.rails[2].readings, [(T0 + 500, 4)])


class ChargeSourceTest(unittest.TestCase):
    def source(self, current_ma, plugged=(), duration_s=120, **kw):
        return perfetto.charge_source(perfetto.parse(pt.simulate(T0, T0 + duration_s * 1000, current_ma, **kw)),
                                      list(plugged))

    def test_no_coulomb_counter(self):
        self.assertIsNone(self.source(lambda t: 300, counter=False))
        trace = perfetto.parse(pt.simulate(T0, T0 + 10_000, lambda t: 0))  # it never changes
        self.assertIsNone(perfetto.charge_source(trace, []))

    def test_coarse_counter(self):
        # 300 mA with a counter counting by 0.5 mAh: it changes every 6 s, the first time after 3.12 s.
        source = self.source(lambda t: 300, resolution_uah=500, charge_uah=3_000_260)
        self.assertEqual((source.name, source.resolution_mah), (metrics.PERFETTO, 0.5))
        self.assertEqual([(iv.start - T0, iv.end - T0) for iv in source.readings[:2]], [(0, 3500), (3500, 9500)])
        # Unknown until the first change and after the last one: a part of a step.
        self.assertEqual((source.currents[0].start - T0, source.currents[-1].end - T0), (3500, 117_500))
        self.assertAlmostEqual(currents_over(source, T0 + 10_000, T0 + 110_000), 300 * 100 / 3600, delta=0.01)
        for iv in source.currents:
            self.assertAlmostEqual(iv.value, 300, delta=1e-6)

    def test_current_samples_shape_the_curve(self):
        # 500 mA and 100 mA in turn every 2 s: shorter than the counter's segments (5 s or more).
        def current(t):
            return 500 if (t - T0) // 2000 % 2 == 0 else 100

        source = self.source(current, resolution_uah=100)
        self.assertAlmostEqual(currents_over(source, T0 + 10_000, T0 + 110_000), 300 * 100 / 3600, delta=0.02)
        for t in range(T0 + 10_000, T0 + 110_000, 2000):  # the middle of each phase
            self.assertAlmostEqual(current_at(source, t + 1000), current(t), delta=0.15 * current(t))

        # Phones reporting positive currents while discharging, or mA: only the shape matters.
        for scale in (1, 1000):
            other = self.source(current, resolution_uah=100, current_scale=scale)
            self.assertEqual(len(other.currents), len(source.currents))
            for a, b in zip(other.currents, source.currents):
                self.assertAlmostEqual(a.value, b.value, delta=1e-6)

    def test_sleep(self):
        # Awake at 400 mA, then asleep at 5 mA for 10 min (no polls): the counter tells the gap's current.
        sleep = (T0 + 20_000, T0 + 620_000)

        def asleep(t):
            return sleep[0] <= t < sleep[1]

        source = self.source(lambda t: 5 if asleep(t) else 400, duration_s=640, resolution_uah=10, asleep=asleep)
        gap = current_at(source, T0 + 300_000)
        self.assertEqual(next(iv for iv in source.currents if iv.start <= T0 + 300_000 < iv.end).start, sleep[0] - 500)
        self.assertGreater(gap, 5)  # with the last 0.5 s awake: 5.33 mA
        self.assertLess(gap, 5.7)
        self.assertAlmostEqual(current_at(source, T0 + 10_000), 400, delta=20)
        self.assertAlmostEqual(current_at(source, T0 + 630_000), 400, delta=20)
        # Known from the first counter change (the second poll) to the end.
        expected = (400 * 39.5 + 5 * 600) / 3600
        self.assertAlmostEqual(currents_over(source, T0 + 500, T0 + 640_000), expected, delta=0.005)

    def test_unknown_while_plugged(self):
        plugged = [Interval(T0 + 30_200, T0 + 50_200, True)]

        def current(t):
            return -1000 if plugged[0].start <= t < plugged[0].end else 300

        source = self.source(current, plugged, resolution_uah=1)
        self.assertFalse([iv for iv in source.currents if iv.start < plugged[0].end and iv.end > plugged[0].start])
        # Unknown from the last counter change before plugging in to the first one after unplugging.
        self.assertEqual(max(iv.end for iv in source.currents if iv.end <= plugged[0].start), T0 + 30_000)
        self.assertEqual(min(iv.start for iv in source.currents if iv.start >= plugged[0].end), T0 + 51_000)
        self.assertAlmostEqual(currents_over(source, T0 + 51_000, T0 + 120_000), 300 * 69 / 3600, delta=0.01)


class RailsTest(unittest.TestCase):
    def test_energy_per_row(self):
        rail = perfetto.Rail("S4M_VDD_CPUCL0", "CPU", "rail_S4M_VDD_CPUCL0_j",
                             [(T0, 1_000_000), (T0 + 1000, 3_000_000), (T0 + 2000, 100), (T0 + 3000, 1_100)])
        rows = [{"start_ms": T0 + a, "end_ms": T0 + b} for a, b in
                ((-500, 0), (0, 500), (500, 1000), (250, 1000), (500, 1500), (2000, 3000), (2500, 3500))]
        perfetto.add_rail_energy(rows, [rail])
        # 2 J per s until the counter is reset between 1 and 2 s; then 1 mJ per s.
        self.assertEqual([r[rail.column] for r in rows], [None, 1.0, 1.0, 1.5, None, 0.001, None])
        self.assertEqual(perfetto.rail_totals([rail], T0, T0 + 1000), [{
            "name": "S4M_VDD_CPUCL0", "subsystem": "CPU", "column": "rail_S4M_VDD_CPUCL0_j",
            "energy_j": 2.0, "mean_power_w": 2.0}])
        self.assertIsNone(perfetto.rail_totals([rail], T0, T0 + 3000)[0]["energy_j"])

    def test_csv_columns(self):
        rows = metrics.compute_rows(history.parse_history(HISTORY), T0, T0 + 10_000)
        for row in rows:
            row["rail_X_j"] = 0.25
        self.assertEqual(metrics.columns(rows), metrics.COLUMNS + ["rail_X_j"])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.csv"
            metrics.write_csv(rows, path)
            self.assertEqual([r["rail_X_j"] for r in metrics.read_csv(path)], [0.25] * len(rows))


class ConfigTest(unittest.TestCase):
    def test_config(self):
        config = perfetto.trace_config()
        for line in ('name: "android.power"', "battery_poll_ms: 500", "battery_counters: BATTERY_COUNTER_CHARGE",
                     "battery_counters: BATTERY_COUNTER_CURRENT", "battery_counters: BATTERY_COUNTER_CAPACITY_PERCENT",
                     "battery_counters: BATTERY_COUNTER_VOLTAGE", "collect_power_rails: true",
                     "write_into_file: true", "duration_ms: 86400000"):
            self.assertIn(line, config)
        self.assertEqual(config.count("{"), config.count("}"))
        self.assertNotIn("VOLTAGE", perfetto.trace_config(voltage=False))


class SessionTest(unittest.TestCase):
    """session.process with a trace of the tests.fixtures.HISTORY session (plugged in from 45 to 55 s)."""

    @staticmethod
    def current(t):
        return -1000 if T0 + 45_000 <= t < T0 + 55_000 else 300

    def run_process(self, trace, start=0, stop=70_000):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        dump, trace_path = Path(d.name) / "dump.txt", Path(d.name) / "trace.pftrace"
        dump.write_text(HISTORY)
        trace_path.write_bytes(trace)
        result = session.process(dump, T0 + start, T0 + stop, Path(d.name) / "PowDroid_x.csv", html=True,
                                 trace_path=trace_path, notes=["A note."])
        return result, json.loads(result.json_path.read_text())

    def test_measured_with_perfetto(self):
        rails = [("S4M_VDD_CPUCL0", "CPU(LITTLE)", 1.5)]
        result, data = self.run_process(pt.simulate(T0 - 5000, T0 + 80_000, self.current, rails=rails))
        s = result.summary
        self.assertEqual((s.current_source, data["current_source"]), ("perfetto", "perfetto"))
        self.assertEqual(result.warnings[0], "A note.")
        self.assertFalse([w for w in result.warnings if "±" in w or "only every" in w])
        # Unplugged for 60 s, minus the first poll interval after unplugging (polls at each plug change)
        # and the first one after the history starts: before it, the plug state is unknown.
        self.assertEqual(s.measured_s, 59.0)
        self.assertAlmostEqual(s.charge_mah, 300 * 59.0 / 3600, delta=0.002)
        self.assertEqual(result.rows[0]["voltage_mv"], 3997)
        self.assertEqual(result.rows[0]["charge_mah"], 2999.583)  # µAh: 5 s at 300 mA after 3000 mAh
        plugged = [r for r in result.rows if r["plugged"]]
        self.assertTrue(plugged and all(r["current_ma"] is None for r in plugged))
        self.assertTrue(all(r["rail_S4M_VDD_CPUCL0_j"] is not None for r in plugged))  # valid while plugged in

        self.assertEqual(data["trace_file"], "trace.pftrace")  # relative to the JSON file
        self.assertEqual(data["perfetto"]["counters"], ["charge_uah", "current_ua", "voltage_uv", "level_pct"])
        self.assertEqual(data["perfetto"]["median_poll_interval_ms"], 500)
        rail = data["power_rails"][0]
        self.assertEqual((rail["name"], rail["column"]), ("S4M_VDD_CPUCL0", "rail_S4M_VDD_CPUCL0_j"))
        self.assertAlmostEqual(rail["energy_j"], 1.5 * 70, places=3)
        self.assertAlmostEqual(sum(r["rail_S4M_VDD_CPUCL0_j"] for r in result.rows), 1.5 * 70, places=3)
        compared = data["batterystats_summary"]  # 240 mA for 15 s, 360 mA for 30 s, 720 mA for 5 s
        self.assertEqual((compared["current_source"], compared["charge_mah"]), ("coulomb_counter", 5.0))

        loaded = session.load(result.csv_path)
        self.assertEqual(loaded.summary.current_source, "perfetto")
        self.assertAlmostEqual(loaded.summary.energy_j, s.energy_j, places=6)
        self.assertEqual(metrics.columns(loaded.rows)[-1], "rail_S4M_VDD_CPUCL0_j")
        self.assertIn('"rail_S4M_VDD_CPUCL0_j"', result.html_path.read_text())

    def test_totals_come_from_the_counter(self):
        # Current samples ten times too high (in mA × 10 000): same totals.
        expected, _ = self.run_process(pt.simulate(T0 - 5000, T0 + 80_000, self.current))
        result, _ = self.run_process(pt.simulate(T0 - 5000, T0 + 80_000, self.current, current_scale=-10_000))
        self.assertAlmostEqual(result.summary.charge_mah, expected.summary.charge_mah, places=6)
        self.assertAlmostEqual(result.summary.energy_j, expected.summary.energy_j, places=6)

    def test_falls_back_to_the_battery_statistics(self):
        result, data = self.run_process(pt.simulate(T0, T0 + 80_000, self.current, counter=False))
        self.assertEqual(data["current_source"], "coulomb_counter")
        self.assertIn("The Perfetto trace has no usable coulomb counter (161 battery polls, charge counter always "
                      "0 µAh): the results come from the battery statistics.", result.warnings)
        self.assertNotIn("batterystats_summary", data)

        result, data = self.run_process(b"not a trace")
        self.assertEqual(data["current_source"], "coulomb_counter")
        self.assertTrue(any(w.startswith("The Perfetto trace could not be read") for w in result.warnings))

    def test_partial_trace(self):
        result, _ = self.run_process(pt.simulate(T0 + 20_000, T0 + 40_000, self.current))
        self.assertIn("The Perfetto trace only covers the session from 20 s to 40 s: the rest has no current.",
                      result.warnings)
        self.assertEqual(result.summary.measured_s, 19.5)  # from the first counter change


if __name__ == "__main__":
    unittest.main()
