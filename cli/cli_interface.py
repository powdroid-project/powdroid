from datetime import datetime
from core.utils import adb_runner
from core.utils import csv_handler
from core.utils import html_renderer
import os

def initialize_connection(verbose=False):
    print("[PowDroid Step 1/4] Initializing device connection...")
    try:
        connected_devices = adb_runner.get_connected_device()
        if (connected_devices):
            print("[PowDroid] Device already connected.")
            if verbose:
                print(f"[PowDroid] Connected devices. Serial ID: {connected_devices[0]}")
        else:
            print("[PowDroid] No device detected. Please connect your device via USB.")
            adb_runner.wait_for_device_connection()
        print("[PowDroid] Preparing device for the test session...")
        input("=> Press ENTER when you are ready to proceed.")
        adb_runner.kill_all(verbose=verbose)
        adb_runner.clear_batterystats(verbose=verbose)
        print("[PowDroid] Device preparation completed successfully.")
    except Exception as e:
        print(f"[Debug] Error in initialize_connection() at line {e.__traceback__.tb_lineno}: {e}")

def record_test_session():
    print("[PowDroid Step 2/4] Starting recording session...")
    print("[PowDroid] Please unplug your device and follow the instructions.")
    adb_runner.wait_for_device_disconnection()
    input("=> Press ENTER to start recording your test session.")
    start_user_test_session = datetime.now().timestamp() * 1000
    print("[PowDroid] Recording in progress...")

    input("=> Press ENTER once you finished your test session.")
    stop_user_test_session = datetime.now().timestamp() * 1000
    print("[PowDroid] Recording session completed.")
    return start_user_test_session, stop_user_test_session

def process_batterystats(verbose=False):
    print("[PowDroid Step 3/4] Processing BatteryStats data...")
    print("[PowDroid] Please reconnect your device via USB.")
    try:
        adb_runner.wait_for_device_connection()
        print("[PowDroid] Processing data. This may take a few moments...")
        adb_runner.dump_batterystats(verbose=verbose)
        file_name = adb_runner.conversion_batterystats()
        print(f"[PowDroid] BatteryStats data processed successfully.")
        return file_name
    except Exception as e:
        print(f"[Debug] Error in process_batterystats() at line {e.__traceback__.tb_lineno}: {e}")
        exit(1)

def generate_output(file_name, start_user_test_session, stop_user_test_session, output, traceback):
    print("[PowDroid Step 4/4] Generating output files...")
    try:
        csv_full_path = None
        if "csv" in output:
            csv_handler.generate_files(file_name)
            csv_full_path = csv_handler.process_csv_file(start_user_test_session, stop_user_test_session)

        if "html" in output:
            if not csv_full_path:
                csv_handler.generate_files(file_name)
                csv_full_path = csv_handler.process_csv_file(start_user_test_session, stop_user_test_session)
            html_content = html_renderer.process_html_file(csv_full_path)
            output_file = os.path.splitext(csv_full_path)[0] + ".html"
            with open(output_file, "w") as html_file:
                html_file.write(html_content)
            print(f"[PowDroid] HTML file generated successfully: {output_file}")
            if not traceback and "csv" not in output:
                if os.path.exists(csv_full_path):
                    os.remove(csv_full_path)
                    print("[PowDroid] Temporary CSV file deleted.")
    except Exception as e:
        print(f"[Debug] Error in generate_csv() at line {e.__traceback__.tb_lineno}: {e}")
        exit(1)

def main(output, verbose=False, traceback=False):
    if verbose:
        print("[PowDroid] INFO | Verbose mode enabled.")
    if traceback:
        print("[PowDroid] INFO | Traceback mode enabled.")
    if output:
        print(f"[PowDroid] INFO | Specified output formats: {', '.join(output)}")
    print("[PowDroid] INFO | CLI executed successfully.")

    print(r"  ____               ____            _     _ ")
    print(r" |  _ \ _____      _|  _ \ _ __ ___ (_) __| |")
    print(r" | |_) / _ \ \ /\ / / | | | '__/ _ \| |/ _` |")
    print(r" |  __/ (_) \ V  V /| |_| | | | (_) | | (_| |")
    print(r" |_|   \___/ \_/\_/ |____/|_|  \___/|_|\__,_|")
    print()
    print("[PowDroid] Welcome to PowDroid CLI!")
    print()

    initialize_connection(verbose=verbose)
    start_user_test_session, stop_user_test_session = record_test_session()
    file_name = process_batterystats(verbose=verbose)
    generate_output(file_name, start_user_test_session, stop_user_test_session, output, traceback)
    
    if not traceback:
        if verbose:
            print("[PowDroid] Cleaning up temporary files...")
        adb_runner.delete_directory(adb_runner.DUMP_DIR)
        csv_handler.delete_directory(csv_handler.TMP_DIR)
        if verbose:
            print("[PowDroid] Temporary files cleaned up successfully.")
    else:
        if verbose:
            print("[PowDroid] Traceback mode enabled. No files or directories will be deleted.")
        
    print("[PowDroid] All tasks completed successfully. Thank you for using PowDroid!")
