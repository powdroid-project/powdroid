# Copyright (c) 2021-2022, Université de Pays et des Pays de l'Adour.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU General Public License v3.0 only (GPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/gpl-3.0.en.html

import lib.powdroid_adb_utils as adb
import lib.powdroid_csv_utils as csvutils
from datetime import datetime

print()
print("  ____               ____            _     _ ")
print(" |  _ \ _____      _|  _ \ _ __ ___ (_) __| |")
print(" | |_) / _ \ \ /\ / / | | | '__/ _ \| |/ _` |")
print(" |  __/ (_) \ V  V /| |_| | | | (_) | | (_| |")
print(" |_|   \___/ \_/\_/ |____/|_|  \___/|_|\__,_|")
print()

# Intialize ADB and connection to phone

print("[PowDroid] **Please, plug the phone to the USB port**")
print("[PowDroid] Press ENTER when you are ready to record your test session")
user_response = input()
adb.kill_all()
adb.clear_batterystats()

# Get start time

print("[PowDroid] Unplug your phone and press ENTER")
user_response = input()
start_user_test_session = datetime.now().timestamp() * 1000

print("[PowDroid] Recording...")

# Get end time

print("[PowDroid] Press ENTER once you finished your test session")
user_response = input()
stop_user_test_session = datetime.now().timestamp() * 1000 

# Process BatteryStats data recordings

print("[PowDroid] Test session finished! ** Please, plug the phone to the USB port and press ENTER **")
user_response = input()

print("[PowDroid] Please wait while processing collected data and generating power readings...")

adb.dump_batterystats()
file_name = adb.conversion_batterystats()

# Generate CSV file with power readings

csvutils.generate_files(file_name)
csvutils.process_csv_file(start_user_test_session, stop_user_test_session)
