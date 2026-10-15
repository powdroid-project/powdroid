# Changelog

## 3.0.0a1 (alpha)

PowDroid 3 is a rewrite. It needs no Go runtime, battery-historian or `adb bugreport`: it reads the battery statistics directly and adds a Perfetto measurement. This first alpha is meant for testing on as many phones as possible: please report problems with the debug log (see the README).

### Measurement
- The battery statistics are read with `dumpsys batterystats -c --history` (seconds instead of minutes) and parsed in Python, including the Android 14+ records written out of order and the Android 15+ tags written in full.
- On Android 10+, the battery is also recorded with Perfetto by default. It polls the coulomb counter in µAh and the current twice a second, plus the energy of each power rail on phones that measure them (mostly Pixels). `--no-perfetto` (CLI) or the home page option turns it off.
- Phones without a coulomb counter: the energy is estimated from the battery level drops, using the capacity learned by the fuel gauge when Android reports it.
- A charge counter that only follows the battery level gets its real resolution and a warning. A frozen counter falls back to the battery level.
- Every result says how precise it is (± %) and warns when the session was too short, when the phone was plugged in, when the history overflowed, or when a clock moved during the session.
- An extrapolated energy covers the unplugged time when the current is not known all along.
- The clock offset between the phone and the computer keeps the fastest of several samples.

### Recording
- Wi-Fi debugging: a phone connected over Wi-Fi is recorded when it runs on battery, and its data is read without plugging it back in. The GUI can switch a USB phone to Wi-Fi, pair it (Android 11+) or connect to it; the CLI has `--connect HOST:PORT`.
- Markers (GUI button or M key; CLI typed labels) split a session into phases, each with its energy and power. Markers can be renamed on the report.
- `--duration SECONDS` records without any question; over Wi-Fi, this gives fully unattended runs.
- A session recorded but not collected (crash, Ctrl-C, PowDroid closed) is kept and can be collected later: GUI home page, or `powdroid --collect-pending`.
- `powdroid --reprocess PowDroid_<date>.json` processes a saved session again, without the phone.
- The phone is given back as it was found: the battery statistics options PowDroid turns on are turned off again, and a Perfetto trace is never left running when a session is cancelled.

### Interface and reports
- New GUI with a home page (checks, device choice, Wi-Fi), a recording page and a report page (summary, charts with markers, data table, details: phases, power rails, how the session was measured).
- With several devices connected (or an emulator running), the GUI lets you choose one and follows only that one. It notices at once when the phone is unplugged (`adb track-devices`).
- The HTML report is self-contained (Chart.js is included) and handles long sessions.
- Optional debug log (CLI `--debug`, GUI option) to attach to bug reports.

### Output
- CSV format v3, not compatible with PowDroid 2: one row per interval during which no tracked state changed. Next to it, a session JSON with the summary, the warnings, the device, how the session was measured, the markers and phases, and the power rails.

### Installation
- Python 3.11+. The CLI needs only the standard library; the GUI needs PyQt6 6.11+ and matplotlib 3.11+.
- PowDroid is a Python package: installing it with pip (`powdroid[gui]` for the graphical interface) gives the `powdroid` and `powdroid-gui` commands. Packaged applications for Windows, macOS and Linux are attached to the GitHub releases. `python powdroid.py` still works from a source checkout.
- adb is found in the `ADB` environment variable, the PATH, or the Android SDK (`ANDROID_HOME`, `ANDROID_SDK_ROOT`, or the folder Android Studio installs it in); `--adb PATH` chooses it.
