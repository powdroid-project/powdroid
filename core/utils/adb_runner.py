import subprocess
import time
import os
from datetime import datetime
from pathlib import Path
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_DIR = Path(BASE_DIR) / "../dump"
GO_DIR = Path(BASE_DIR) / "../libs/battery-historian"

def start_adb_server(verbose=False):
    try:
        subprocess.run("adb get-state", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
        print("[PowDroid] ADB server is already running.")
    except:
        try:
            subprocess.run("adb start-server", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
            print("[PowDroid] ADB server started successfully.")
        except Exception as e:
            print(f"[Debug] Failed to start ADB server in start_adb_server() at line {e.__traceback__.tb_lineno}: {e}")
            raise

def get_connected_device():
    try:
        output = subprocess.check_output("adb devices", shell=True).decode("utf-8").strip()
        devices = []
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line:
                devices.append(line.split()[0])
        return devices
    except Exception as e:
        print(f"[Debug] Error in get_connected_device() at line {e.__traceback__.tb_lineno}: {e}")
        raise

def wait_for_device_connection(verbose=False):
    print("[PowDroid] Waiting for device connection...")
    while True:
        try:
            devices = get_connected_device()
            if devices:
                for device in devices:
                    # Check if the device is in file transfer (mtp) mode
                    output = subprocess.check_output(f"adb -s {device} shell getprop sys.usb.config", shell=True).decode("utf-8").strip()
                    if "mtp" in output:
                        if verbose:
                            print("[PowDroid] Device connected in file transfer mode.")
                        return
                    else:
                        if verbose:
                            print(f"[PowDroid] Device {device} is not in file transfer mode. Current mode: {output}")
            else:
                if verbose:
                    print("[PowDroid] No devices connected.")
        except Exception as e:
            print(f"[Debug] Error in wait_for_device_connection() at line {e.__traceback__.tb_lineno}: {e}")
            raise
        time.sleep(1)

def kill_all(verbose=False):
    subprocess.run("adb shell am kill-all", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)

def clear_batterystats(device="", verbose=False):
    device = f"-s {device}" if device else ""
    subprocess.run(f"adb {device} shell dumpsys batterystats --reset", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)

def wait_for_device_disconnection(verbose=False):
    print("[PowDroid] Waiting for device disconnection...")
    previous_devices = get_connected_device()
    while True:
        current_devices = get_connected_device()
        disconnected_devices = set(previous_devices) - set(current_devices)
        if disconnected_devices:
            print("[PowDroid] Device disconnected.")
            if verbose:
                for device in disconnected_devices:
                    print(f"[PowDroid] Disconnected device. Serial ID: {device}")
            break
        previous_devices = current_devices
        time.sleep(1)

def create_directory(path, verbose=False):
    try:
        os.makedirs(path, exist_ok=True)
        if verbose:
            print(f"[PowDroid] Directory created or already exists.")
            print(f"[PowDroid] Directory path: {os.path.abspath(path)}")
    except Exception as e:
        print(f"[PowDroid] Error in create_directory() at line {e.__traceback__.tb_lineno}: {e}")
        raise

def delete_directory(path, verbose=False):
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
            if verbose:
                print("[PowDroid] Directory deleted.")
        else:
            if verbose:
                print("[PowDroid] Directory does not exist.")
    except Exception as e:
        print(f"[PowDroid] Error in delete_directory() at line {e.__traceback__.tb_lineno}: {e}")
        raise

def dump_batterystats(device="", verbose=False):
    try:
        create_directory(DUMP_DIR)
        os.chdir(DUMP_DIR)
        subprocess.run(f"adb {device} shell dumpsys batterystats --enable full-wake-history > batterystats.txt", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
        subprocess.run(f"adb {device} shell dumpsys batterystats >> batterystats.txt", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
        exec_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        subprocess.run("adb bugreport battery_device.zip", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
        os.chdir(BASE_DIR)
    except Exception as e:
        print(f"[Debug] Error in dump_batterystats() at line {e.__traceback__.tb_lineno}: {e}")
        raise

def conversion_batterystats(device="", verbose=False):
    try:
        os.chdir(GO_DIR)
        file_name = "battery_device.csv"
        command = (
            f"go run cmd/history-parse/local_history_parse.go --summary=totalTime "
            f"--csv=\"{DUMP_DIR / file_name}\" --input=\"{DUMP_DIR / 'battery_device.zip'}\" "
            f"> \"{DUMP_DIR / 'history_parse_log.txt'}\" 2>&1"
        )
        if verbose:
            print(f"[PowDroid] Running command: {command}")
        subprocess.call(command, shell=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
        os.chdir(BASE_DIR)
        if verbose:
            print(f"[PowDroid] Check logs in: \"{DUMP_DIR / 'history_parse_log.txt'}\"")
        return file_name
    except Exception as e:
        print(f"[Debug] Error in conversion_batterystats() at line {e.__traceback__.tb_lineno}: {e}")
        raise
