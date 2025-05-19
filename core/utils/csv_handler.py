import os
import pandas
import glob
from datetime import datetime
from pathlib import Path

DUMP_DIR = Path(os.getcwd()) / "dump"
TMP_DIR = Path(os.getcwd()) / "tmp"
OUTPUT_DIR = Path(os.getcwd())

def generate_files(file):
    try:
        TMP_DIR.resolve()
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        df = pandas.read_csv(os.path.join(DUMP_DIR, file))
        Metrics = ["Voltage", "Screen", "GPS", "Camera", "Audio", "Mobile radio active", "Coulomb charge", "Top app", "Wifi on", "Wifi radio", "Video", "Wakelock_in"]
        for metric in Metrics:
            result = df[df["metric"] == metric]
            result.to_csv(os.path.join(TMP_DIR, f'{metric}.csv'), index=False)
    except Exception as e:
        print(f"[Debug] Error in generate_files() at line {e.__traceback__.tb_lineno}: {e}")
        raise

def union_time():
    all_csv_files = glob.glob(str(TMP_DIR / "*.csv"))
    ensembles_temps = set()
    for file_name in all_csv_files:
        df = pandas.read_csv(file_name)
        for index, row in df.iterrows():
            start_time = row['start_time']
            end_time = row['end_time']
            ensembles_temps.add(start_time)
            ensembles_temps.add(end_time)

    list_temp = list(ensembles_temps)
    list_temp.sort()
    return list_temp

def look_up(file_name, start_time, end_time):
    file_readed = pandas.read_csv(TMP_DIR / file_name)
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    if(len(found)==0):
        metric_value = 0.0
    else:
        metric_value = found["value"].values
    return metric_value

def look_up_intensity(file_name, start_time, end_time):
    file_readed = pandas.read_csv(TMP_DIR / file_name)
    file_readed["next_value"] = file_readed["value"].shift(-1)
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]

    if len(found) == 0:
        amp = 0
    else:
        charge_consumed = found["value"] - found["next_value"]
        duration_sec = (file_readed.end_time - file_readed.start_time) / 1000
        duration_hr = duration_sec / 3600
        duration_hr = duration_hr.replace(0, float('nan')) if hasattr(duration_hr, 'replace') else duration_hr
        amp_value = charge_consumed / duration_hr
        amp = amp_value.dropna()
    return amp.values

def look_up_bool(file_name, start_time, end_time):
    file_readed = pandas.read_csv(TMP_DIR / file_name)
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    if(len(found)==0):
        metric_value = False
    else:
        metric_value = True
    return metric_value

def process_csv_file(init_test_time, end_test_time):
    try:
        metrics = [
            "Voltage.csv", "Screen.csv", "GPS.csv", "Camera.csv", "Audio.csv",
            "Mobile radio active.csv", "Coulomb charge.csv", "Top app.csv",
            "Wifi on.csv", "Wifi radio.csv", "Video.csv", "Wakelock_in.csv"
        ]
        columns = [
            "start_time", "end_time", "Duration (mS)", "Voltage (mV)", "Remaining_charge (mAh)",
            "Intensity (mA)", "Power (W)", "Consumed charge(mAh)", "Energy (J)", "Top app", "Screen(ON/OFF)",
            "GPS(ON/OFF)", "Mobile_Radio(ON/OFF)", "WiFi(ON/OFF)", "Wifi radio", "Camera(ON/OFF)",
            "Video (ON/OFF)", "Audio(ON/OFF)", "Wakelock_in (Service)"
        ]
        rows = []

        time_intervals = [t for t in union_time() if init_test_time <= t <= end_test_time]
        n_intervals = len(time_intervals) - 1

        if n_intervals <= 0:
            print("[DEBUG] Aucun intervalle trouvé, vérifie les timestamps !")
            return None

        def safe_first(val):
            try:
                if hasattr(val, '__len__') and not isinstance(val, str):
                    return val[0] if len(val) > 0 else None
                return val if val != 0.0 else None
            except Exception:
                return None

        for i in range(n_intervals):
            start_time, end_time = time_intervals[i], time_intervals[i + 1]
            duration = end_time - start_time

            volt = look_up("Voltage.csv", start_time, end_time)
            coulomb = look_up("Coulomb charge.csv", start_time, end_time)
            amp = look_up_intensity("Coulomb charge.csv", start_time, end_time)
            app = look_up("Top app.csv", start_time, end_time)
            wakelock_in = look_up("Wakelock_in.csv", start_time, end_time)

            # Calculs directs pour les colonnes dérivées
            voltage = safe_first(volt)
            intensity = safe_first(amp)
            duration_sec = duration / 1000 if duration else 0
            duration_hr = duration_sec / 3600 if duration_sec else 0
            convert_V = voltage / 1000 if voltage else 0
            convert_A = intensity / 1000 if intensity else 0

            power = convert_V * convert_A
            consumed_charge = intensity * duration_hr if intensity else 0
            energy = power * duration_sec

            row = {
                "start_time": start_time,
                "end_time": end_time,
                "Duration (mS)": duration,
                "Voltage (mV)": voltage,
                "Remaining_charge (mAh)": safe_first(coulomb),
                "Intensity (mA)": intensity,
                "Power (W)": power,
                "Consumed charge(mAh)": consumed_charge,
                "Energy (J)": energy,
                "Top app": safe_first(app),
                "Screen(ON/OFF)": look_up_bool("Screen.csv", start_time, end_time),
                "GPS(ON/OFF)": look_up_bool("GPS.csv", start_time, end_time),
                "Mobile_Radio(ON/OFF)": look_up_bool("Mobile radio active.csv", start_time, end_time),
                "WiFi(ON/OFF)": look_up_bool("Wifi on.csv", start_time, end_time),
                "Wifi radio": look_up_bool("Wifi radio.csv", start_time, end_time),
                "Camera(ON/OFF)": look_up_bool("Camera.csv", start_time, end_time),
                "Video (ON/OFF)": look_up_bool("Video.csv", start_time, end_time),
                "Audio(ON/OFF)": look_up_bool("Audio.csv", start_time, end_time),
                "Wakelock_in (Service)": safe_first(wakelock_in)
            }
            rows.append(row)

        output_df = pandas.DataFrame(rows, columns=columns)

        csv_filename = os.path.join(OUTPUT_DIR, f'PowDroid_{datetime.now().timestamp()}.csv')
        output_df.to_csv(csv_filename, float_format='%f', index=False)

        return csv_filename
    except Exception as e:
        print(f"[Debug] Error in process_csv_file() at line {e.__traceback__.tb_lineno}: {e}")
        raise
