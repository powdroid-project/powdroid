import os
import pandas
import glob
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_DIR = Path(BASE_DIR) / "../dump"
TMP_DIR = Path(BASE_DIR) / "../tmp"
OUTPUT_DIR = Path(os.getcwd())

def create_directory(path, verbose=False):
    try:
        os.makedirs(path, exist_ok=True)
        if verbose:
            print(f"[PowDroid] Directory created or already exists: {path}")
    except Exception as e:
        print(f"[Debug] Error in create_directory() at line {e.__traceback__.tb_lineno}: {e}")
        raise

def delete_directory(path, verbose=False):
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
            if verbose:
                print(f"[PowDroid] Directory deleted: {path}")
        else:
            if verbose:
                print(f"[PowDroid] Directory does not exist: {path}")
    except Exception as e:
        print(f"[Debug] Error in delete_directory() at line {e.__traceback__.tb_lineno}: {e}")
        raise

def generate_files(file):
    try:
        create_directory(TMP_DIR)
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

def look_up(csv_file, start_time, end_time):
    file_readed = pandas.read_csv(TMP_DIR / csv_file)
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    if(len(found)==0):
        metric_value = 0.0
    else:
        metric_value = found["value"].values
    return metric_value

def look_up_intensity(csv_file, start_time, end_time):
    file_readed = pandas.read_csv(TMP_DIR / csv_file)
    file_readed["next_value"] = file_readed["value"].shift(-1).dropna()
    
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    
    if len(found) == 0:
        amp = 0
    else:
        charge_consumed = found["value"] - found["next_value"]
        duration_sec = (file_readed.end_time - file_readed.start_time) / 1000
        duration_hr = duration_sec / 3600
        amp_value = charge_consumed / duration_hr
        amp = amp_value.dropna()
        
    return amp.values

def look_up_bool(csv_file, start_time, end_time):
    file_readed = pandas.read_csv(TMP_DIR / csv_file)
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    if(len(found)==0):
        metric_value = False
    else:
        metric_value = True
    return metric_value

def process_csv_file(init_test_time, end_test_time, verbose=False):
    try:
        if verbose:
            print(f"[PowDroid] Output directory set to: {OUTPUT_DIR}")
        create_directory(TMP_DIR, verbose=verbose)

        all_csv_files = ["Voltage.csv","Screen.csv","GPS.csv","Camera.csv","Audio.csv","Mobile radio active.csv","Coulomb charge.csv","Top app.csv","Wifi on.csv","Wifi radio.csv", "Video.csv","Wakelock_in.csv"]
        data_init_dataframe = [[0, 0, 0, 0, 0, 0, 0, 0, 0, "", 0, 0, 0, 0, 0, 0, 0, 0, ""]]
        output_df = pandas.DataFrame(data_init_dataframe)
        output_df.columns = ["start_time", "end_time", "Duration (mS)", "Voltage (mV)", "Remaining_charge (mAh)",
                             "Intensity (mA)", "Power (W)", "Consumed charge(mAh)", "Energy (J)", "Top app", "Screen(ON/OFF)",
                             "GPS(ON/OFF)", "Mobile_Radio(ON/OFF)", "WiFi(ON/OFF)",
                             "Wifi radio", "Camera(ON/OFF)","Video (ON/OFF)",
                             "Audio(ON/OFF)", "Wakelock_in (Service)"]
        
        time_intervals = list(filter(lambda t : t >= init_test_time and t <= end_test_time, union_time()))
        
        for i in range(len(time_intervals)-1):
            start_time = time_intervals[i]
            end_time = time_intervals[i+1]
            
            output_df.at[i,'start_time'] = start_time
            output_df['start_time'] = output_df['start_time'].astype('Int64')
            
            output_df.at[i,'end_time'] = end_time
            output_df['end_time'] = output_df['end_time'].astype('Int64')

            duration = end_time - start_time
            output_df.at[i, 'Duration (mS)'] = duration
            output_df['Duration (mS)'] = output_df['Duration (mS)'].astype('Int64')
            
            volt = look_up("Voltage.csv", start_time, end_time)
            output_df.at[i,'Voltage (mV)'] = volt
            output_df['Voltage (mV)'] = output_df['Voltage (mV)'].astype('Int64')

            coulomb = look_up("Coulomb charge.csv", start_time, end_time)
            output_df.at[i,'Remaining_charge (mAh)'] = coulomb
            output_df['Remaining_charge (mAh)'] = output_df['Remaining_charge (mAh)'].astype('Int64')

            amp = look_up_intensity("Coulomb charge.csv", start_time, end_time)
            output_df['Intensity (mA)'] = output_df['Intensity (mA)'].astype('Float64')
            output_df.at[i,'Intensity (mA)'] = amp

            app = look_up("Top app.csv", start_time, end_time)
            output_df.at[i,'Top app'] = app

            wakelock_in = look_up("Wakelock_in.csv", start_time, end_time)
            output_df.at[i,'Wakelock_in (Service)'] = wakelock_in
            
            screen = look_up_bool("Screen.csv", start_time, end_time)
            output_df['Screen(ON/OFF)'] = output_df['Screen(ON/OFF)'].astype('bool')
            output_df.at[i,'Screen(ON/OFF)'] = screen
            
            gps = look_up_bool("GPS.csv", start_time, end_time)
            output_df['GPS(ON/OFF)'] = output_df['GPS(ON/OFF)'].astype('bool')
            output_df.at[i,'GPS(ON/OFF)'] = gps
            
            cam = look_up_bool("Camera.csv", start_time, end_time)
            output_df['Camera(ON/OFF)'] = output_df['Camera(ON/OFF)'].astype('bool')
            output_df.at[i,'Camera(ON/OFF)'] = cam
            
            audio = look_up_bool("Audio.csv", start_time, end_time)
            output_df['Audio(ON/OFF)'] = output_df['Audio(ON/OFF)'].astype('bool')
            output_df.at[i,'Audio(ON/OFF)'] = audio
            
            mobile = look_up_bool("Mobile radio active.csv", start_time, end_time)
            output_df['Mobile_Radio(ON/OFF)'] = output_df['Mobile_Radio(ON/OFF)'].astype('bool')
            output_df.at[i,'Mobile_Radio(ON/OFF)'] = mobile
            
            wifi = look_up_bool("Wifi on.csv", start_time, end_time)
            output_df['WiFi(ON/OFF)'] = output_df['WiFi(ON/OFF)'].astype('bool')
            output_df.at[i,'WiFi(ON/OFF)'] = wifi
            
            wifi_r = look_up_bool("Wifi radio.csv", start_time, end_time)
            output_df['Wifi radio'] = output_df['Wifi radio'].astype('bool')
            output_df.at[i,'Wifi radio'] = wifi_r
            
            video = look_up_bool("Video.csv", start_time, end_time)
            output_df['Video (ON/OFF)'] = output_df['Video (ON/OFF)'].astype('bool')
            output_df.at[i,'Video (ON/OFF)'] = video

        for i in range(len(time_intervals)-1):
            start_time = time_intervals[i]
            end_time = time_intervals[i+1]
            found = output_df[(start_time >= output_df.start_time) & (end_time <= output_df.end_time)]

            duration_sec = found['Duration (mS)']/1000
            duration_hr = duration_sec / 3600
            intensity = found['Intensity (mA)']
            voltage = found['Voltage (mV)']
            convert_V = voltage /1000
            convert_A = intensity /1000
            
            power = float((convert_V * convert_A).iloc[0])
            output_df.at[i, 'Power (W)'] = power

            consumed_charge = float((intensity * duration_hr).iloc[0])
            output_df.at[i, 'Consumed charge(mAh)'] = consumed_charge

            energy = float((power * duration_sec).iloc[0])
            output_df.at[i, 'Energy (J)'] = energy

        CSV_FULL_FILENAME = os.path.join(OUTPUT_DIR,'PowDroid_{0}.csv'.format(datetime.now().timestamp()))
        output_df.to_csv(CSV_FULL_FILENAME, float_format='%f', index=False)

        print(f"[PowDroid] Finished! File generated: {CSV_FULL_FILENAME}")
        return CSV_FULL_FILENAME
    except Exception as e:
        print(f"[Debug] Error in process_csv_file() at line {e.__traceback__.tb_lineno}: {e}")
        raise
    finally:
        delete_directory(TMP_DIR, verbose=verbose)
