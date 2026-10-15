![PowDroid logo](gui/ressources/PowDroid_Vertical.png)

Powdroid is an off-device energy profiler for Android.
Simply run your application for a few minutes to generate a machine-ready output file containing various energy-related metrics.

## 🔧 Setup

PowDroid only needs Python and adb:
- [Python 3.9+](https://www.python.org/downloads/). The command-line interface uses the standard library only.
- [Android SDK platform tools](https://developer.android.com/studio/releases/platform-tools) (`adb`).
- For the graphical interface: `pip install -r requirements.txt` (PyQt6 + matplotlib).

⚠️ The `adb` command must be in your PATH:
- On Windows, edit the PATH environment variable in Advanced System Settings, then System Properties, then Environment Variables, and finally choose Path and edit it by adding the new path (the location where you installed platform-tools).
- On Unix-style systems: `export PATH=/the/path/to/platform-tools:$PATH` in your .profile or .bashrc file.

## 🚀 Getting started

### Optimal test conditions

- Disable the Battery Saver Mode
- Disable screen timeout
- Set the brightness and sound level at 50%
- Kill running apps and background services
- Start with the battery below 100 %: right after a full charge, the battery voltage is temporarily higher
- Record long enough to consume at least 20 mAh (often 5 to 10 minutes): the coulomb counter has a 1 mAh resolution, so this keeps energy and power within ±5 %. PowDroid shows this uncertainty and warns when it is larger
- Some phones (e.g. the Pixel 3a) do not report their battery coulomb counter: `adb shell dumpsys battery` shows `Charge counter: 0`. PowDroid then warns before recording and estimates the energy from the battery level drops instead, which needs a much longer session: a drop of at least 10 % of the battery for about ±10 %, 20 % for ±5 %
- Unplug the phone as soon as the recording page asks for it, and plug it back only after stopping

### Initial configuration

First, activate *USB Debugging* in your Android phone in *developer options*.
To verify and facilitate the use of "PowDroid" it is advised to do the first "Handshake" between your phone and the computer by connecting the phone through USB to the computer and type in a command prompt or shell the following: `adb devices`.
On your phone a prompt should appear asking for permission for debugging. If the computer is your personal computer and safe, you should check *Always allow from this computer*.

### Running and Using PowDroid (CLI or GUI)

- Graphical interface (GUI): run `python /path/to/powdroid.py` without arguments.
  Results are written to `~/PowDroid` by default (configurable from the home screen), the report page shows charts, a data table and can export an HTML report.
  PowDroid measures with Perfetto when the phone supports it (see below); untick *Use Perfetto (Android 10+)* on the home screen to use the battery statistics only.
- Command-line interface (CLI): run `python /path/to/powdroid.py -o csv` (or `-o csv,html`) and follow the on-screen instructions.
  Use `-d DIR` to choose the output folder, `-s SERIAL` when several devices are connected, `--no-perfetto` to use the battery statistics only (see below), and `--help` for all options.

Battery data is read with `adb shell dumpsys batterystats -c` (a few seconds) and parsed directly in Python; earlier versions needed the Go runtime, battery-historian and a slow `adb bugreport`.
On Android 10 and later, PowDroid also records the battery with Perfetto, as described below.

### Measuring with Perfetto (default on Android 10+)

By default, PowDroid also records a [Perfetto](https://perfetto.dev) trace of the battery during the session, with Android's own tracing service. Use `--no-perfetto` (CLI) or untick *Use Perfetto (Android 10+)* (GUI) to measure with the battery statistics only.
- Before you unplug the phone, PowDroid starts `perfetto` in the background on the phone (`android.power` data source, battery polled every 500 ms, power rails on). The trace keeps running while the phone is unplugged. Once it is plugged back in, PowDroid stops the trace, copies it to `dump/perfetto_<date>.pftrace` and deletes it from the phone. The file opens in [ui.perfetto.dev](https://ui.perfetto.dev).
- The trace reads the same fuel gauge as the battery statistics, but in µAh instead of whole mAh, and every 500 ms while the phone is awake instead of whenever the phone pushes a new value (on some phones once a minute), along with the current and, from Android 15, the voltage. Phones with on-device power monitors (mostly recent Pixels) also report the energy of each power rail (CPU clusters, GPU, display, modem…).
- The battery statistics are still read: they give the plugged, screen, app and wakelock states, and the same session's totals without Perfetto, saved in the JSON file for comparison.
- When Perfetto is not available, PowDroid says why before recording and uses the battery statistics alone: Android 9 or older, tracing service disabled (on Android 10, some phones need `adb shell setprop persist.traced.enable 1`), or `perfetto` failing to start. The reason is in the session's JSON file (`perfetto_unavailable`) and in the debug log.
- If the trace recorded during the session cannot be used (not copied from the phone, unreadable, or without a coulomb counter), the results also come from the battery statistics, with a warning saying why.
- This measurement is new and has only been tested with a simulated phone so far: if its figures differ from the battery statistics' (both are in the JSON file), please open an issue with the debug log, the trace and the `dumpsys` output.

### Reporting a problem: the debug log

When PowDroid fails with your phone or computer, record a session with the debug log on and attach the log to your [issue](https://github.com/powdroid-project/powdroid/issues):
- CLI: add `--debug` (or `--debug FILE` to choose the file). The log is written to `DIR/logs/PowDroid_debug_<date>.log` and its path is printed at the end.
- GUI: tick *Debug log* at the bottom of the home page, then *Open folder* shows the log. The option is remembered: restart PowDroid to also log its startup.

The log contains the system, Python and adb versions, every adb command with its answer and duration, device details (`getprop`, `dumpsys battery`), a summary of the battery statistics read, the session times and every error with its traceback.
It contains your device's serial number and model and paths on your computer: review it before posting it publicly. The battery statistics in `dump/` are also useful to reproduce a problem.

### Output files (format v3)

Each session produces, in the output folder:
- `PowDroid_<date>.csv`: one row per interval during which no tracked state changed; the rows cover the whole session. Columns:
  - time: `start_ms`, `end_ms` (device epoch ms), `elapsed_s` (since the session start), `duration_ms`;
  - battery: `battery_level_pct`, `voltage_mv`, `charge_mah` (coulomb counter, empty on phones without one; with Perfetto, read in µAh, so with decimals), `current_ma`, `power_w`, `energy_j`, `consumed_mah`, `temperature_c`;
  - components (0/1): `plugged`, `screen`, `cpu_running`, `wifi`, `wifi_radio`, `mobile_radio`, `gps`, `bluetooth`, `camera`, `video`, `audio`, `flashlight`, `sensor`, `battery_saver`, plus `brightness` (0–4);
  - `top_app` (while the screen is on) and `wakelocks` (all held, `;`-separated);
  - with Perfetto, on phones that measure them, one column per power rail after the others: `rail_<name>_j`, the rail's energy in J during the row (e.g. `rail_S4M_VDD_CPUCL0_j`).

  Empty cells mean unknown. In particular, current, power and energy are left empty while the phone is plugged in, because the coulomb counter then measures charging.
- `PowDroid_<date>.json`: the device, the requested and measured session start and stop, the clock offset, where the current comes from (`current_source`: `coulomb_counter`, `battery_level` with `battery_capacity_mah`, or `perfetto`), totals (energy, average power and current, consumed charge, measured time) and warnings about the reliability of the results (phone plugged in, history overflow, too little charge consumed for the resolution of the readings, estimate from the battery level, Perfetto trace not usable and why), and `perfetto_unavailable` when Perfetto could not be used on the phone. With Perfetto, it also has `trace_file`, `perfetto` (number of battery polls, time between them, counters the phone reported, resolution of the counter, median current sample), `power_rails` (name, subsystem, CSV column, energy in J and mean power in W of each rail over the measured time) and `batterystats_summary` (the totals the battery statistics alone give for the same session).
- `PowDroid_<date>.html` when requested, and the raw `dumpsys` output (and the Perfetto trace) in `dump/`.

How the figures are obtained:
- The current comes from the battery coulomb counter: for each reading, the charge drop until the next reading divided by the time in between. The counter has a 1 mAh resolution, so energy and power are known to about ±1 mAh relative to the charge consumed (shown as ± % in the reports). Some phones update the reading only every minute or so: the power is then an average over such periods (PowDroid warns about it).
- Phones without a coulomb counter only report the battery level. Each 1 % drop then counts as 1 % of the battery's design capacity (from the phone's power profile): the current is that charge divided by the time until the next drop. It is only known between the first and last level drops of the session, has a resolution of 1 % of the capacity (shown as ± %), and is overestimated on a worn battery, whose real capacity is lower than its design capacity.
- With Perfetto, the totals still come from the coulomb counter, read in µAh: the charge used between two counter changes is exact up to the counter's resolution, whatever the current samples say. The current samples only shape the curve. The charge used between counter changes at least 5 s apart is spread over the 500 ms polls in between, in proportion to the current samples. So phones that report the current with the opposite sign or in mA still give the right energy. While the phone sleeps there are no polls: the counter alone tells the charge used during the gap, which is spread evenly over it. As with the battery statistics, the current is unknown between a plug change and the next counter change. The resolution shown (± %) is the median change between two counter readings.
- Power rail energies come from the rails' energy counters (cumulative since boot, in µWs, still counting while the phone sleeps), interpolated at the row edges. The rails sit downstream of the battery, so their energy is also known while the phone is plugged in.
- The voltage is interpolated between the phone's readings (except across plugging or unplugging): with Perfetto from Android 15, every 500 ms. Power is voltage × current and energy is power × duration, row by row.
- If the session starts before the phone is unplugged or ends after it is plugged back in, those edges are left out. Plugging in during the session is reported, and those rows have no current, power or energy.
- Device and computer clocks are aligned when the results are collected, to a few milliseconds.

Run the tests with `python -m unittest discover tests`. They need no phone: `tests/fake_adb.py` simulates a device, including plugging, clock skew, the battery history and Perfetto traces (`tests/perfetto_trace.py`).

## 🤝 Contributors

The project is developed and maintained by:
- Olivier Le Goaër
- Adel Noureddine

Previous contributors : Fares Bouaffar (initial author), Pierre-Antoine Larguet, Alex Striedelmeyer, Julien Desprez, Nathan Lorit.
PowDroid was first released on [our old university git repository here](https://git.univ-pau.fr/powdroid/powdroid), and on [our old gitlab repository here](https://gitlab.com/powdroid/powdroid-cli).

## 🔗 How to cite this work?

To cite PowDroid, please cite our paper in the 2nd International Workshop on Sustainable Software Engineering (SUSTAINSE) at ASE 2021 conference.

- **[PowDroid: Energy Profiling of Android Applications](https://hal.archives-ouvertes.fr/hal-03380605v1)**. Fares Bouaffar, Olivier Le Goaer, and Adel Noureddine. In the Second International Workshop on Sustainable Software Engineering (SUSTAINSE)/(ASE'21), Melbourne, Australia, November 2021.

```
@inproceedings{bouaffar2021powdroid,
  title = {PowDroid: Energy Profiling of Android Applications},
  author = {Bouaffar, Fares and Le Goaer, Olivier and Noureddine, Adel},
  booktitle = {2nd International Workshop on Sustainable Software Engineering (SUSTAINSE), at ASE 2021},
  address = {Melbourne, Australia}
  year = {2021}
  month = {Nov},
  keywords = {Energy consumption; Android; Battery drain; Estimation; Tool}
}
```

## :newspaper: License

PowDroid is licensed under the GNU GPL 3 license only (GPL-3.0-only).

Copyright (c) 2021-2026, Université de Pau et des Pays de l'Adour.
All rights reserved. This program and the accompanying materials are made available under the terms of the GNU General Public License v3.0 only (GPL-3.0-only) which accompanies this distribution, and is available at: https://www.gnu.org/licenses/gpl-3.0.en.html
