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
- Unplug the phone as soon as the recording page asks for it, and plug it back only after stopping

### Initial configuration

First, activate *USB Debugging* in your Android phone in *developer options*.
To verify and facilitate the use of "PowDroid" it is advised to do the first "Handshake" between your phone and the computer by connecting the phone through USB to the computer and type in a command prompt or shell the following: `adb devices`.
On your phone a prompt should appear asking for permission for debugging. If the computer is your personal computer and safe, you should check *Always allow from this computer*.

### Running and Using PowDroid (CLI or GUI)

- Graphical interface (GUI): run `python /path/to/powdroid.py` without arguments.
  Results are written to `~/PowDroid` by default (configurable from the home screen), the report page shows charts, a data table and can export an HTML report.
- Command-line interface (CLI): run `python /path/to/powdroid.py -o csv` (or `-o csv,html`) and follow the on-screen instructions.
  Use `-d DIR` to choose the output folder, `-s SERIAL` when several devices are connected, and `--help` for all options.

Battery data is read with `adb shell dumpsys batterystats -c` (a few seconds) and parsed directly in Python; earlier versions needed the Go runtime, battery-historian and a slow `adb bugreport`.

### Output files (format v3)

Each session produces, in the output folder:
- `PowDroid_<date>.csv`: one row per interval during which no tracked state changed; the rows cover the whole session. Columns:
  - time: `start_ms`, `end_ms` (device epoch ms), `elapsed_s` (since the session start), `duration_ms`;
  - battery: `battery_level_pct`, `voltage_mv`, `charge_mah` (coulomb counter), `current_ma`, `power_w`, `energy_j`, `consumed_mah`, `temperature_c`;
  - components (0/1): `plugged`, `screen`, `cpu_running`, `wifi`, `wifi_radio`, `mobile_radio`, `gps`, `bluetooth`, `camera`, `video`, `audio`, `flashlight`, `sensor`, `battery_saver`, plus `brightness` (0–4);
  - `top_app` (while the screen is on) and `wakelocks` (all held, `;`-separated).

  Empty cells mean unknown. In particular, current, power and energy are left empty while the phone is plugged in, because the coulomb counter then measures charging.
- `PowDroid_<date>.json`: the device, the requested and measured session start and stop, the clock offset, totals (energy, average power and current, consumed charge, measured time) and warnings about the reliability of the results (phone plugged in, history overflow, too little charge consumed for the 1 mAh counter resolution).
- `PowDroid_<date>.html` when requested, and the raw `dumpsys` output in `dump/`.

How the figures are obtained:
- The current comes from the battery coulomb counter: for each reading, the charge drop until the next reading divided by the time in between. The counter has a 1 mAh resolution, so energy and power are known to about ±1 mAh relative to the charge consumed (shown as ± % in the reports). Some phones update the reading only every minute or so: the power is then an average over such periods (PowDroid warns about it).
- The voltage is interpolated between the phone's readings (except across plugging or unplugging). Power is voltage × current and energy is power × duration, row by row.
- If the session starts before the phone is unplugged or ends after it is plugged back in, those edges are left out. Plugging in during the session is reported, and those rows have no current, power or energy.
- Device and computer clocks are aligned when the results are collected, to a few milliseconds.

Run the tests with `python -m unittest discover tests`. They need no phone: `tests/fake_adb.py` simulates a device, including plugging, clock skew and the battery history.

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
