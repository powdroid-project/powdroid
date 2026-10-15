![PowDroid logo](powdroid/gui/ressources/PowDroid_Vertical.png)

Powdroid is an off-device energy profiler for Android.
Simply run your application for a few minutes to generate a machine-ready output file containing various energy-related metrics.

> **PowDroid 3 is in alpha** (3.0.0a1). It has been rewritten: no Go runtime or battery-historian any more, Perfetto measurements, Wi-Fi debugging, markers, and a new interface ([CHANGELOG](CHANGELOG.md)). Its output (CSV format v3) differs from PowDroid 2. Please try it on your phones and [report problems](#-reporting-a-problem-the-debug-log) with the debug log.

## 🔧 Setup

PowDroid needs:
- An Android phone with *USB debugging* enabled: Android 5.0 or newer, Android 10 or newer for Perfetto measurements.
- The [Android SDK platform tools](https://developer.android.com/studio/releases/platform-tools) (`adb`), version 29 or newer.

Then install PowDroid in one of these ways:
- **Application** (Windows, macOS, Linux): download it from the [releases](https://github.com/powdroid-project/powdroid/releases). The macOS application is not signed: right-click it and choose *Open* the first time.
- **With pip** ([Python 3.11+](https://www.python.org/downloads/)): `pip install "powdroid[gui] @ git+https://github.com/powdroid-project/powdroid@v3.0.0a1"` (or the `.whl` file of a release, with `[gui]`), then run `powdroid-gui` (graphical interface) or `powdroid` (command line). The command line needs no other package: without `[gui]`, PyQt6 and matplotlib are not installed.
- **From a source checkout**: `pip install -r requirements.txt` (PyQt6 and matplotlib, for the graphical interface), then `python powdroid.py`.

PowDroid finds adb by itself. In this order, it uses:
1. the `ADB` environment variable (or `--adb PATH` on the command line);
2. the `PATH`;
3. the `platform-tools` folder of the Android SDK in `ANDROID_HOME` or `ANDROID_SDK_ROOT`;
4. the folder where Android Studio installs the SDK: `~/Library/Android/sdk` on macOS, `%LOCALAPPDATA%\Android\Sdk` on Windows, `~/Android/Sdk` on Linux.

PowDroid never runs an `adb.exe` from the current folder.

On Linux, adb needs udev rules to use a phone over USB: install them (e.g. the `android-sdk-platform-tools-common` package) and add your user to the `plugdev` group. Otherwise PowDroid shows the device as *No permission to use the device*.

## 🚀 Getting started

### Optimal test conditions

- Disable the Battery Saver Mode
- Disable screen timeout
- Set the brightness and sound level at 50%
- Kill running apps and background services
- Start with the battery below 100 %: right after a full charge, the battery voltage is temporarily higher
- Record long enough to consume at least 20 mAh (often 5 to 10 minutes): the coulomb counter has a 1 mAh resolution, so this keeps energy and power within ±5 %. PowDroid shows this uncertainty and warns when it is larger
- Some phones (e.g. the Pixel 3a) do not report their battery coulomb counter: `adb shell dumpsys battery` shows `Charge counter: 0`. PowDroid then warns before recording and estimates the energy from the battery level drops instead, which needs a much longer session: a drop of at least 10 % of the battery for about ±10 %, 20 % for ±5 %
- Unplug the phone as soon as the recording page asks for it, and plug it back only after stopping (over USB)

### Initial configuration

First, activate *USB Debugging* in your Android phone in *developer options*.
To verify and facilitate the use of "PowDroid" it is advised to do the first "Handshake" between your phone and the computer by connecting the phone through USB to the computer and type in a command prompt or shell the following: `adb devices`.
On your phone a prompt should appear asking for permission for debugging. If the computer is your personal computer and safe, you should check *Always allow from this computer*.

### Running and Using PowDroid (CLI or GUI)

**Graphical interface (GUI)**: run the application, `powdroid-gui`, or `python powdroid.py` without arguments.
- When several devices are connected, choose one on the home page. Emulators are listed but never chosen first.
- Results are written to `~/PowDroid` by default (configurable from the home page).
- The report page shows the summary, charts (with markers), the data table and a *Details* tab: phases between markers, power rails, how the session was measured. It can export an HTML report.
- PowDroid measures with Perfetto when the phone supports it (see below); untick *Use Perfetto (Android 10+)* on the home page to use the battery statistics only.

**Command-line interface (CLI)**: run `powdroid -o csv` (or `python powdroid.py -o csv`) and follow the on-screen instructions. While recording, type a label and press ENTER to add a marker; press ENTER alone to stop. The options:
- `-o csv,html`: also write the HTML report.
- `-d DIR`: the output folder (default: the current folder).
- `-s SERIAL`: the device, when several are connected.
- `--duration SECONDS`: record for this long, without asking anything. The session starts when the phone is unplugged and stops after that time.
- `--connect HOST:PORT`: first connect to a phone over Wi-Fi.
- `--no-perfetto`: use the battery statistics only.
- `--adb PATH`: the adb program to use.
- `--reprocess PowDroid_<date>.json`: process a saved session again (see below).
- `--collect-pending`: collect a session that was recorded but not collected (see below).
- `--debug`: write the debug log (see below).
- `--help`: all the options.

The battery data is read with `adb shell dumpsys batterystats -c --history` (a few seconds) and parsed directly in Python; earlier versions needed the Go runtime, battery-historian and a slow `adb bugreport`.
On Android 10 and later, PowDroid also records the battery with Perfetto, as described below.

### Measuring over Wi-Fi

Over USB, the cable charges the phone, so it must be unplugged while recording, and plugged back in to read the data. Over Wi-Fi debugging the phone stays connected:
- PowDroid records once the phone runs on battery, and reads the data as soon as you stop, without plugging it back in. With `--duration`, a whole session runs unattended: start it, run your scenario (e.g. with UI Automator or Espresso), and the results are written at the end.
- To connect a phone over Wi-Fi in the GUI, click *Connect over Wi-Fi…* on the home page. You can switch a USB phone to Wi-Fi (`adb tcpip`), pair a phone with *Wireless debugging* (Android 11+), or connect to an address. On the command line: `adb pair` / `adb connect`, or `--connect HOST:PORT`. The phone and the computer must be on the same network.
- While recording, PowDroid sends nothing to the phone, so that it can sleep normally. The Wi-Fi connection used by adb still adds a little to the measured energy, so the report warns about it.

### Markers and phases

Mark the moments of a scenario while recording, for example when a scroll or a video starts: *Add marker* (or the M key) in the GUI, or a typed label in the CLI. Each marker starts a phase. The reports give the energy, average power and measured time of each phase (`phases` in the JSON), and the charts show the markers. Markers can be renamed in the *Details* tab of the GUI report.

### What PowDroid changes on the phone

To record a session, PowDroid:
- resets the battery statistics (Settings › Battery usage starts again from the session);
- stops the background apps (`am kill-all`);
- turns on two battery statistics options during the session:
  - `full-wake-history` records every wakelock;
  - `no-auto-reset` stops Android from resetting the statistics when the phone is unplugged with a high battery level.

  It turns them off again once the data is read, or when the session is cancelled;
- with Perfetto, records a trace in `/data/misc/perfetto-traces/powdroid.pftrace` (at most 256 MB). It copies it, then deletes it from the phone. A trace left behind stops by itself after a day and is removed by the next session.

### Measuring with Perfetto (default on Android 10+)

By default, PowDroid also records a [Perfetto](https://perfetto.dev) trace of the battery during the session, with Android's own tracing service. Use `--no-perfetto` (CLI) or untick *Use Perfetto (Android 10+)* (GUI) to measure with the battery statistics only.
- Before you unplug the phone, PowDroid starts `perfetto` in the background on the phone (`android.power` data source, battery polled every 500 ms, power rails on). The trace keeps running while the phone is unplugged. Once the session is over, PowDroid stops the trace, copies it to `dump/perfetto_<date>.pftrace` and deletes it from the phone. The file opens in [ui.perfetto.dev](https://ui.perfetto.dev).
- The trace reads the same fuel gauge as the battery statistics, but in µAh instead of whole mAh, and every 500 ms while the phone is awake instead of whenever the phone pushes a new value (on some phones once a minute), along with the current and, from Android 15, the voltage. Phones with on-device power monitors (mostly recent Pixels) also report the energy of each power rail (CPU clusters, GPU, display, modem…).
- The battery statistics are still read: they give the plugged, screen, app and wakelock states, and the same session's totals without Perfetto, saved in the JSON file for comparison.
- When Perfetto is not available, PowDroid says why before recording and uses the battery statistics alone: Android 9 or older, tracing service disabled (on Android 10, some phones need `adb shell setprop persist.traced.enable 1`), or `perfetto` failing to start. The reason is in the session's JSON file (`perfetto_unavailable`) and in the debug log.
- If the trace recorded during the session cannot be used (not copied from the phone, unreadable, or without a coulomb counter), the results also come from the battery statistics, with a warning saying why.
- This measurement is new and has only been tested with a simulated phone so far: if its figures differ from the battery statistics' (both are in the JSON file and in the report's *Details*), please open an issue with the debug log, the trace and the `dumpsys` output.

### Sessions not collected, and processing a session again

While a session goes on, PowDroid keeps what it needs to read its data in `~/.powdroid/pending/`. If PowDroid stops before reading the phone's data (crash, Ctrl-C, or closed while recording), the phone keeps its battery history and Perfetto trace. The session can then be collected later: on the GUI home page, or with `powdroid --collect-pending`. A session whose stop is unknown ends when the phone was plugged back in.

`powdroid --reprocess PowDroid_<date>.json` processes a saved session again from its battery statistics and Perfetto trace (in `dump/`), without the phone, for example with a newer PowDroid. The CSV, JSON (and HTML with `-o csv,html`) are written again, next to the JSON file or in `-d DIR`. The session folder can be moved: the JSON file names the dump and trace relative to itself.

## 🐞 Reporting a problem: the debug log

When PowDroid fails with your phone or computer, record a session with the debug log on and attach the log to your [issue](https://github.com/powdroid-project/powdroid/issues):
- CLI: add `--debug` (or `--debug FILE` to choose the file). The log is written to `DIR/logs/PowDroid_debug_<date>.log` and its path is printed at the end.
- GUI: tick *Debug log* at the bottom of the home page, then *Open folder* shows the log. The option is remembered: restart PowDroid to also log its startup.

The log contains:
- the system, Python and adb versions, and the adb programs found;
- every adb command with its answer and duration;
- device details (`getprop`, `dumpsys battery`);
- a summary of the battery statistics read;
- the session times;
- every error with its traceback.

It contains your device's serial number and model and paths on your computer: review it before posting it publicly. The battery statistics in `dump/` are also useful to reproduce a problem.

## 📄 Output files (format v3)

Each session produces, in the output folder:
- `PowDroid_<date>.csv`: one row per interval during which no tracked state changed; the rows cover the whole session. Columns:
  - time: `start_ms`, `end_ms` (device epoch ms), `elapsed_s` (since the session start), `duration_ms`;
  - battery: `battery_level_pct`, `voltage_mv`, `charge_mah` (coulomb counter, empty on phones without one; with Perfetto, read in µAh, so with decimals), `current_ma`, `power_w`, `energy_j`, `consumed_mah`, `temperature_c`;
  - components (0/1): `plugged`, `screen`, `cpu_running`, `wifi`, `wifi_radio`, `mobile_radio`, `gps`, `bluetooth`, `camera`, `video`, `audio`, `flashlight`, `sensor`, `battery_saver`, plus `brightness` (0–4);
  - `top_app` (while the screen is on) and `wakelocks` (all held, `;`-separated);
  - with Perfetto, on phones that measure them, one column per power rail after the others: `rail_<name>_j`, the rail's energy in J during the row (e.g. `rail_S4M_VDD_CPUCL0_j`).

  Empty cells mean unknown. In particular, current, power and energy are left empty while the phone is plugged in, because the coulomb counter then measures charging.
- `PowDroid_<date>.json`, which holds:
  - the device, the connection (`transport`: `usb` or `wifi`), and the requested and measured session start and stop;
  - the clock offsets (when prepared and when collected);
  - where the current comes from (`current_source`: `coulomb_counter`, `battery_level` or `perfetto`), with `charge_resolution_mah`, `counter_follows_level`, `battery_capacity_mah` and `battery_capacity_source` (`learned`, `estimated` or `reported`);
  - the totals (`summary`: energy, average power and current, consumed charge, measured time, `extrapolated_energy_j`);
  - the `markers` and `phases`;
  - the warnings about the reliability of the results: phone plugged in, history overflow, too little charge consumed for the resolution of the readings, estimate from the battery level, clock moved, Perfetto trace not usable and why, Wi-Fi connection;
  - `perfetto_unavailable` when Perfetto could not be used on the phone;
  - the dump and trace files, relative to the JSON file;
  - with Perfetto: `perfetto` (number of battery polls, time between them, counters the phone reported, resolution of the counter, median current sample), `power_rails` (name, subsystem, CSV column, energy in J and mean power in W of each rail over the measured time) and `batterystats_summary` (the totals the battery statistics alone give for the same session).
- `PowDroid_<date>.html` when requested: a self-contained page (it works offline) with the summary, charts, phases, power rails and the data table.
- The raw `dumpsys` output (and the Perfetto trace) in `dump/`.

How the figures are obtained:
- The current comes from the battery coulomb counter: for each reading, the charge drop until the next reading divided by the time in between. The battery statistics give the counter in whole mAh, so energy and power are known to about ±1 mAh relative to the charge consumed (shown as ± % in the reports). Some fuel gauges compute the counter from the battery level: it then only changes with the level, by about 1 % of the capacity. PowDroid detects this, uses that step as the resolution and warns about it. Some phones update the reading only every minute or so: the power is then an average over such periods (PowDroid warns about it).
- Phones without a coulomb counter only report the battery level; so do phones whose counter does not change during the session. Each 1 % drop then counts as 1 % of the battery capacity: the current is that charge divided by the time until the next drop.
  - The capacity is, when Android reports it: the one learned by the fuel gauge (its full charge, which follows battery wear), else Android's own estimate, else the reported capacity (the design capacity up to Android 12).
  - The current is only known between the first and last level drops of the session, and has a resolution of 1 % of the capacity (shown as ± %).
- With Perfetto, the totals still come from the coulomb counter, read in µAh: the charge used between two counter changes is exact up to the counter's resolution, whatever the current samples say. The current samples only shape the curve:
  - The charge used between counter changes at least 5 s apart is spread over the 500 ms polls in between, in proportion to the current samples. So phones that report the current with the opposite sign or in mA still give the right energy.
  - While the phone sleeps there are no polls: the counter alone tells the charge used during the gap, which is spread evenly over it.
  - As with the battery statistics, the current is unknown between a plug change and the next counter change.
  - The resolution shown (± %) is the median change between two counter readings.
- Power rail energies come from the rails' energy counters (cumulative since boot, in µWs, still counting while the phone sleeps), interpolated at the row edges. The rails sit downstream of the battery, so their energy is also known while the phone is plugged in.
- The voltage is interpolated between the phone's readings (except across plugging or unplugging): with Perfetto from Android 15, every 500 ms. Power is voltage × current and energy is power × duration, row by row.
- If the session starts before the phone is unplugged or ends after it is plugged back in, those edges are left out. Plugging in during the session is reported, and those rows have no current, power or energy.
- When the current is not known all the time the phone was unplugged (before the first counter change, after the last one), the total energy only covers the measured time. The extrapolated energy (average power × unplugged time) estimates the whole session.
- Device and computer clocks are aligned when the session is prepared and when it is collected, to a few milliseconds (the fastest of several round trips); a difference between the two is warned about.

## 🛠️ Development

- Tests: `python -m unittest discover tests`. They need no phone: `tests/fake_adb.py` simulates a device. It covers USB and Wi-Fi connections, plugging, clock skew, several devices, the battery history and Perfetto traces (`tests/perfetto_trace.py`). The GUI tests run without a display (`QT_QPA_PLATFORM=offscreen`) when PyQt6 and matplotlib are installed.
- Lint: `ruff check .`
- Every push runs the lint, the tests on Linux, macOS and Windows, the GUI tests and a package build (`.github/workflows/ci.yml`).
- Pushing a tag such as `v3.0.0a1` builds the Python package and the applications. It attaches them to a draft GitHub release (`.github/workflows/release.yml`).

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
Chart.js, included in HTML reports (`powdroid/core/vendor`), is licensed under the MIT license.

Copyright (c) 2021-2026, Université de Pau et des Pays de l'Adour.
All rights reserved. This program and the accompanying materials are made available under the terms of the GNU General Public License v3.0 only (GPL-3.0-only) which accompanies this distribution, and is available at: https://www.gnu.org/licenses/gpl-3.0.en.html
