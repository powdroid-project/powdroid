import shutil
import subprocess
import sys
import signal

def command_in_path(command):
    return shutil.which(command) is not None

def check_android_sdk():
    if command_in_path("adb"):
        print("[PowDroid] OK | Android SDK platform tools are installed and in the PATH.")
    else:
        print("[Debug] Error | Android SDK platform tools are not installed or not in the PATH.")
        print("[Debug] └── Please ensure that Android SDK platform tools are installed and configured as described in the README.")
        raise SystemExit("[Debug] Exiting due to missing Android SDK platform tools.")

def check_python_version():
    if command_in_path("python"):
        try:
            result = subprocess.run(["python", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(f"[PowDroid] OK | Python is installed. Version: {result.stdout.strip() or result.stderr.strip()}")
        except Exception as e:
            print(f"[Debug] An error occurred while checking Python: {e}")
            raise SystemExit("[Debug] Exiting due to Python check error.")
    else:
        print("[Debug] Error | Python is not installed or not in the PATH.")
        print("[Debug] └── Please ensure that Python is installed and configured as described in the README.")
        raise SystemExit("[Debug] Exiting due to missing Python installation.")

def check_pandas_module():
    try:
        import pandas
        print("[PowDroid] OK | The Pandas module is installed.")
    except ImportError:
        print("[Debug] Error | The Pandas module is not installed. Run 'pip install pandas' to install it.")
        print("[Debug] └── Please ensure that all required Python modules are installed as described in the README.")
        raise SystemExit("[Debug] Exiting due to missing Pandas module.")

def check_go_runtime():
    if command_in_path("go"):
        try:
            result = subprocess.run(["go", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(f"[PowDroid] OK | Go runtime is installed. Version: {result.stdout.strip()}")
        except Exception as e:
            print(f"[Debug] An error occurred while checking the Go runtime: {e}")
            raise SystemExit("[Debug] Exiting due to Go runtime check error.")
    else:
        print("[Debug] Error | Go runtime is not installed or not in the PATH.")
        print("[Debug] └── Please ensure that the Go runtime is installed and configured as described in the README.")
        raise SystemExit("[Debug] Exiting due to missing Go runtime.")

def initialize_adb_server(verbose=False):
    if command_in_path("adb"):
        try:
            subprocess.run("adb kill-server", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
            subprocess.run("adb start-server", shell=True, check=True, stdout=None if verbose else subprocess.DEVNULL, stderr=None if verbose else subprocess.DEVNULL)
            print("[PowDroid] OK | ADB server restarted successfully.")
        except Exception as e:
            print(f"[Debug] Failed to restart ADB server in initialize_adb_server() at line {e.__traceback__.tb_lineno}: {e}")
            raise SystemExit("[Debug] Exiting due to ADB server initialization error.")
    else:
        print("[Debug] Error | ADB command not found. Ensure Android SDK platform tools are installed and in the PATH.")
        print("[Debug] └── Please ensure that ADB is installed and configured as described in the README.")
        raise SystemExit("[Debug] Exiting due to missing ADB command.")

def handle_exit(sig, frame):
    sys.exit(0)

def main(verbose=False):
    signal.signal(signal.SIGINT, handle_exit)
    print("[PowDroid] INFO | System configuration check...\n")
    errors = []

    try:
        check_android_sdk()
    except SystemExit as e:
        errors.append(str(e))

    try:
        check_python_version()
    except SystemExit as e:
        errors.append(str(e))

    try:
        check_pandas_module()
    except SystemExit as e:
        errors.append(str(e))

    try:
        check_go_runtime()
    except SystemExit as e:
        errors.append(str(e))

    try:
        initialize_adb_server(verbose=verbose)
    except SystemExit as e:
        errors.append(str(e))

    if errors:
        if signal.getsignal(signal.SIGINT) is not None:
            raise SystemExit()
        else:
            raise SystemExit("\n[PowDroid] INFO | Exiting due to the above errors.")
    else:
        print("\n[PowDroid] INFO | Check completed successfully.")

if __name__ == "__main__":
    verbose_flag = "--verbose" in sys.argv
    main(verbose=verbose_flag)
