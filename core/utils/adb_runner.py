import os
import subprocess
import sys
import threading
import time
import itertools
from pathlib import Path

DUMP_DIR = Path(os.getcwd()) / "dump"
GO_DIR = Path(__file__).resolve().parent / "../libs/battery-historian"

def get_connected_device(id_only=False):
    try:
        output = subprocess.check_output(["adb", "devices"], text=True)
        devices = [
            line.split()[0]
            for line in output.splitlines()[1:]
            if line.strip() and line.strip().endswith("device")
        ]
        if not devices:
            return None
        device_id = devices[0]
        # Récupère les infos du device
        props = subprocess.check_output([
            "adb", "shell", "getprop"
        ], text=True)
        manufacturer = None
        model = None
        for line in props.splitlines():
            if "[ro.product.manufacturer]" in line:
                manufacturer = line.split(": ", 1)[1].strip().strip("[]")
            if "[ro.product.model]" in line:
                model = line.split(": ", 1)[1].strip().strip("[]")
        if id_only:
            return device_id
        return f"{device_id} -> {manufacturer} {model}" if manufacturer and model else device_id
    except subprocess.CalledProcessError as e:
        print(f"Error getting connected device: {e}")
        return None

def is_device_connected():
    """Vérifie si un device Android est connecté."""
    return get_connected_device() is not None

def is_adb_available():
    """Vérifie si ADB est disponible sur le système."""
    try:
        subprocess.check_output(["adb", "version"], text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_device_info():
    """Récupère les informations détaillées du device connecté."""
    try:
        if not is_device_connected():
            return None
            
        props = subprocess.check_output(["adb", "shell", "getprop"], text=True)
        info = {}
        
        for line in props.splitlines():
            if "[ro.product.manufacturer]" in line:
                info['manufacturer'] = line.split(": ", 1)[1].strip().strip("[]")
            elif "[ro.product.model]" in line:
                info['model'] = line.split(": ", 1)[1].strip().strip("[]")
            elif "[ro.build.version.release]" in line:
                info['android_version'] = line.split(": ", 1)[1].strip().strip("[]")
                
        return info if info else None
    except subprocess.CalledProcessError:
        return None

def wait_for_device_connection(verbose):
    print("[PowDroid] Waiting for device connection...")
    while True:
        device = get_connected_device()
        if device:
            print(f"[PowDroid] Device {device} connected." if verbose else "[PowDroid] Device connected.")
            break
        else:
            time.sleep(1)

def kill_all():
    try:
        subprocess.run(["adb", "shell", "am", "kill-all"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error killing adb server: {e}")

def clear_batterystats(verbose):
    try:
        subprocess.run(
            ["adb", "shell", "dumpsys", "batterystats", "--reset"],
            check=True,
            **({} if verbose else {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})
        )
    except subprocess.CalledProcessError as e:
        print(f"Error clearing battery stats: {e}")

def wait_for_device_disconnection(verbose):
    print("[PowDroid] Waiting for device disconnection...")
    last_device = get_connected_device()
    while True:
        device = get_connected_device()
        if not device:
            print(f"[PowDroid] Device {last_device} disconnected." if verbose else "[PowDroid] Device disconnected.")
            break
        else:
            time.sleep(1)

def _spinner(stop_event):
    spinner = itertools.cycle(['/', '-', '\\', '|'])
    while not stop_event.is_set():
        sys.stdout.write('\r[PowDroid] Extract battery data... ' + next(spinner))
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write('\r[PowDroid] Extract battery data... done!\n')
    sys.stdout.flush()

def dump_batterystats(verbose):
    device = get_connected_device(id_only=True)
    dump_dir = DUMP_DIR.resolve()
    dump_dir.mkdir(parents=True, exist_ok=True)
    batterystats_path = dump_dir / "batterystats.txt"
    bugreport_path = dump_dir / "battery_device.zip"
    opts = {} if verbose else {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

    spinner_stop = threading.Event()
    spinner_thread = None
    if not verbose:
        spinner_thread = threading.Thread(target=_spinner, args=(spinner_stop,))
        spinner_thread.start()

    try:
        subprocess.run(
            f"adb -s {device} shell dumpsys batterystats --enable full-wake-history > \"{batterystats_path}\"",
            shell=True, check=True, **opts
        )
        subprocess.run(
            f"adb -s {device} shell dumpsys batterystats >> \"{batterystats_path}\"",
            shell=True, check=True, **opts
        )
        subprocess.run(
            f"adb -s {device} bugreport \"{bugreport_path}\"",
            shell=True, check=True, **opts
        )
    finally:
        if not verbose:
            spinner_stop.set()
            spinner_thread.join()

def conversion_batterystats():
    file_name = "battery_device.csv"
    csv_path = str((DUMP_DIR / file_name).resolve())
    zip_path = str((DUMP_DIR / 'battery_device.zip').resolve())
    log_path = str((DUMP_DIR / 'history_parse_log.txt').resolve())
    command = (
        f'go run cmd/history-parse/local_history_parse.go --summary=totalTime '
        f'--csv="{csv_path}" --input="{zip_path}" > "{log_path}" 2>&1'
    )
    subprocess.run(command, shell=True, check=True, cwd=GO_DIR)
    return file_name
