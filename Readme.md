# PowDroid: A lightweight tool for measuring the energy footprint of any android application
***
Powdroid is a command-line tool for measuring energy consumption of android apps. Just test your app for several minutes and get a csv output file with different energy-related metrics.

## 🔧 Setup

Install the following dependencies:
- Android SDK platform tools (https://developer.android.com/studio/releases/platform-tools)
- Python 3+ runtime (https://www.python.org/downloads/)
- Pandas module
- GO runtime (https://go.dev/dl/)

⚠️ Then you must add command `adb` to your environment PATH (python and go should already be in the path, if not add them like adb):
- On Windows, edit the PATH environment variable in Advanced System Settings, then System Properties, then Environment Variables, and finally choose Path and edit it by adding the new path (the location where you installed platform-tools).
- On Unix-style systems: `export PATH=/the/path/to/target/:$PATH` to your .profile or .bashrc file.

## 🚀 Getting started

### Optimal test conditions

- Disable the Battery Saver Mode
- Set the brightness and sound level at 50%
- A minimum 3-minute session (Battery level must decrease)

### Initial configuration

First, activate *USB Debugging* in your Android phone in *developer options*.
To verify and facilitate the use of "PowDroid" it is advised to do the first "Handshake" between your phone and the computer by connecting the phone through USB to the computer and type in a command prompt or shell the following: `adb devices`.
On your phone a prompt should appear asking for permission for debugging. If the computer is your personal computer and safe, you should check *Always allow from this computer*.

### Running and Using PowDroid

Just run `python powdroid.py` in your terminal and follow the on-screen instructions.

#### Explanation of steps

First, plug your phone to the computer.
When it's plugged in you can validate the first prompt by hitting *Enter*.

This will attempt (if the manufacturer allows it) to kill all background process then proceed to clear a log file of android call *batterystats*.

You will be prompted to disconnect your device, then hit *enter*. It's important to hit enter **after** disconnecting the device otherwise the program will crash when collecting the data.

At this moment the consumption is being recorded. You can do the testing.

After the testing period is over, press *enter*. Wait for the next prompt to plug the device to the computer. It's important to connect the device **before** hitting enter otherwise the program will crash when collecting the data.

Data collection is in progress and can take several minutes. No user action is needed afterwards. Be sure to not disconnect the phone during the whole data collection process.

When PowDroid finished processing the data, it will generate a CSV file in the ```output``` folder and prints the path to the file on the terminal.


## 🤝🏿 Contributors

The project is developed and maintained by:
- Olivier Le Goaër
- Adel Noureddine

Contributors :
- Fares Bouaffar (initial author)
- Pierre-Antoine Larguet
- Alex Striedelmeyer
- Johan Pelay

PowDroid was first released on [our old git repository here](https://git.univ-pau.fr/powdroid/powdroid).

## 🔗 How to cite this work?

F. Bouaffar, O. L. Goaer and A. Noureddine, "PowDroid: Energy Profiling of Android Applications," 2021 36th IEEE/ACM International Conference on Automated Software Engineering Workshops (ASEW), 2021, pp. 251-254, doi: 10.1109/ASEW52652.2021.00055.


## :newspaper: License

PowDroid is licensed under the GNU GPL 3 license only (GPL-3.0-only).

Copyright (c) 2021-2022, Université de Pau et des Pays de l'Adour.
All rights reserved. This program and the accompanying materials are made available under the terms of the GNU General Public License v3.0 only (GPL-3.0-only) which accompanies this distribution, and is available at: https://www.gnu.org/licenses/gpl-3.0.en.html
