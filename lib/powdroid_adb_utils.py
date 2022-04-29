# Copyright (c) 2021-2022, Université de Pays et des Pays de l'Adour.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU General Public License v3.0 only (GPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/gpl-3.0.en.html

import os
import subprocess
from datetime import datetime
from pathlib import Path

WORKSPACE_DIR = Path.cwd()
GO_DIR = Path.cwd() / Path("./lib/battery-historian/")
TMP_DIR = Path.cwd() / Path("./tmp/")
DUMP_DIR = Path.cwd() / Path("./dump/")

def get_connected_device(ip="", port=7777):
    if ip:
        p = subprocess.check_output("adb -s {}:{} shell getprop ro.product.model".format(ip, port), shell=True)
    else:
        p = subprocess.check_output("adb shell getprop ro.product.model", shell=True)
    return p.decode('utf-8').strip().replace(" ", "")

def clear_batterystats(device=""):
    device = "-s " + device if device else ""
    subprocess.call("adb {} shell dumpsys batterystats --reset".format(device), shell=True)

def dump_batterystats(device=""):
    device = ("-s " + device) if device else ""
    os.chdir(DUMP_DIR)
    subprocess.call("adb {} shell dumpsys batterystats --enable full-wake-history > batterystats.txt".format(device), shell=True)
    subprocess.call("adb {} shell dumpsys batterystats >> batterystats.txt".format(device), shell=True)
    exec_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    subprocess.call("adb bugreport battery_device.zip", shell=True)
    os.chdir(WORKSPACE_DIR)

def conversion_batterystats(device=""):
    os.chdir(GO_DIR)
    file_name = "battery_device.csv"
    subprocess.call("go run cmd/history-parse/local_history_parse.go --summary=totalTime --csv={0}/{1} --input={0}/battery_device.zip > {0}/history_parse_log.txt 2>&1".format(DUMP_DIR,file_name), shell=True)
    os.chdir(WORKSPACE_DIR)
    return file_name
    
def install_apk(apk, device=""):
    device = "-s " + device if device else ""
    subprocess.call("adb {} install -r ".format(device) + apk, shell=False)

def uninstall_apk(pkg, device=""):
    device = "-s " + device if device else ""
    subprocess.call("adb {} uninstall ".format(device) + pkg, shell=False)

def kill_all():
    # kill all background processes
    subprocess.call("adb shell am kill-all", shell=True)
