from core.utils import adb_runner as adb
from core.utils import csv_handler as csv
from core.utils import html_renderer as html
from datetime import datetime

def initialize_connection(verbose):
    print("[PowDroid Step 1/4] Initializing device connection...")

    connected_device = adb.get_connected_device()
    if not connected_device:
        print("[PowDroid] No device detected. Please connect your device via USB.")
        adb.wait_for_device_connection(verbose)
        connected_device = adb.get_connected_device()
    else:
        print(f"[PowDroid] Device {connected_device} connected." if verbose else "[PowDroid] Device already connected.")
    adb.kill_all()
    adb.clear_batterystats(verbose)

def record_session(verbose):
    print("[PowDroid Step 2/4] Starting session recording...")
    print("[PowDroid] Please unplug your device and follow the instructions.")
    adb.wait_for_device_disconnection(verbose)

    input("=> Press ENTER to start recording your test session.")
    start_user_session = datetime.now()
    print(f"[PowDroid] Recording in progress from {start_user_session.strftime('%Y-%m-%d %H:%M:%S')}")

    input("=> Press ENTER once you finished your test session.")
    stop_user_session = datetime.now()
    print(f"[PowDroid] Recording session completed at {stop_user_session.strftime('%Y-%m-%d %H:%M:%S')}")

    duration = stop_user_session - start_user_session
    days = duration.days
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    duration_parts = []
    if days > 0:
        duration_parts.append(f"{days}d")
    if hours > 0:
        duration_parts.append(f"{hours}h")
    if minutes > 0:
        duration_parts.append(f"{minutes}m")
    if seconds > 0 or not duration_parts:
        duration_parts.append(f"{seconds}s")

    print(f"[PowDroid] Session finished with a duration of {' '.join(duration_parts)}")

    return start_user_session, stop_user_session

def process_batterystats(verbose):
    print("[PowDroid Step 3/4] Processing battery data...")
    print("[PowDroid] Please reconnect your device via USB.")
    adb.wait_for_device_connection(verbose)

    print("[PowDroid] This step may take a few moments, please wait while processing collected data...")

    adb.dump_batterystats(verbose)
    file_name = adb.conversion_batterystats()
    return file_name

def generate_outputs(file_name, start_user_session, stop_user_session, output_formats, verbose):
    print("[PowDroid Step 4/4] Generating output files...")

    def to_timestamp_ms(dt):
        return int(dt.timestamp() * 1000) if isinstance(dt, datetime) else dt

    start_ts = to_timestamp_ms(start_user_session)
    stop_ts = to_timestamp_ms(stop_user_session)

    csv_path = None

    if "csv" in output_formats or "html" in output_formats:
        csv.generate_files(file_name)
        csv_path = csv.process_csv_file(start_ts, stop_ts)

    if "csv" in output_formats:
        print(f"[PowDroid] CSV file generated successfully: {csv_path}")

    if "html" in output_formats:
        html_content = html.process_html_file(csv_path)
        html_path = csv_path.rsplit(".", 1)[0] + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"[PowDroid] HTML file generated successfully: {html_path}")

def main(output_formats, verbose):
    print(r"  ____               ____            _     _ ")
    print(r" |  _ \ _____      _|  _ \ _ __ ___ (_) __| |")
    print(r" | |_) / _ \ \ /\ / / | | | '__/ _ \| |/ _` |")
    print(r" |  __/ (_) \ V  V /| |_| | | | (_) | | (_| |")
    print(r" |_|   \___/ \_/\_/ |____/|_|  \___/|_|\__,_|")
    print("\n[PowDroid] Welcome to PowDroid CLI!\n")

    initialize_connection(verbose)
    start_user_session, stop_user_session = record_session(verbose)
    file_name = process_batterystats(verbose)
    generate_outputs(file_name, start_user_session, stop_user_session, output_formats, verbose)

    print("\n[PowDroid] All tasks completed successfully. Thank you for using PowDroid!")
