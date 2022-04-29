# Copyright (c) 2021-2022, Université de Pays et des Pays de l'Adour.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU General Public License v3.0 only (GPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/gpl-3.0.en.html

import pandas
from datetime import datetime
import os
import glob
import shutil
from pathlib import Path

TMP_DIR = Path.cwd() / Path("./tmp/")
DUMP_DIR = Path.cwd() / Path("./dump/")
OUTPUT_DIR = Path.cwd() / Path("./output/")

def dir_create():
    """ creation du dossier /tmp """
    try:
        os.mkdir(TMP_DIR)
        print(TMP_DIR)
        print(type(TMP_DIR))
    except:
        shutil.rmtree('tmp')
        os.mkdir('tmp')
        tmp_dir = 'tmp'
        print(tmp_dir)
        print(type(tmp_dir))


def generate_files(file):
    df = pandas.read_csv(os.path.join(DUMP_DIR,file))
    Metrics = ["Voltage","Screen","GPS","Camera","Audio","Mobile radio active","Coulomb charge","Top app","Wifi on","Wifi radio", "Video", "Wakelock_in"]
    for i in range(len(Metrics)):
        result = df[df["metric"] == Metrics[i]]
        if(result.empty):
            result.to_csv(os.path.join(TMP_DIR,'{0}.csv'.format(Metrics[i])), index=False)
        else:
            result.to_csv(os.path.join(TMP_DIR,'{0}.csv'.format(Metrics[i])), index=False)

"""  reformulation des plages temporaire  """
def union_time():
    all_csv_files = glob.glob(str(TMP_DIR) + "/*.csv")
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
    file_readed = pandas.read_csv(os.path.join(TMP_DIR,csv_file))
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    if(len(found)==0):
        metric_value = 0.0
    else:
        metric_value = found["value"].values
    return metric_value

def look_up_intensity(csv_file, start_time, end_time):
    file_readed = pandas.read_csv(os.path.join(TMP_DIR,csv_file))
    file_readed["next_value"] = file_readed["value"].shift(-1).dropna()
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    if(len(found)==0):
        amp = 0
    else:
        charge_consumed = found["value"] - found["next_value"]
        duration_sec = (file_readed.end_time - file_readed.start_time)/1000
        duration_hr = duration_sec / 3600
        amp_value = charge_consumed / duration_hr
        amp = amp_value.dropna()
        
    return amp.values


def look_up_bool(csv_file, start_time, end_time):
    file_readed = pandas.read_csv(os.path.join(TMP_DIR,csv_file))
    found = file_readed[(start_time >= file_readed.start_time) & (end_time <= file_readed.end_time)]
    if(len(found)==0):
        metric_value = False
    else:
        metric_value = True
    return metric_value


def process_csv_file(init_test_time, end_test_time):
    
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
        output_df.at[i,'start_time'] = start_time
        output_df['start_time'] = output_df['start_time'].astype('Int64')
        
        end_time = time_intervals[i+1]
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
        
        #Power in milliWatt
        power = float(convert_V * convert_A)
        output_df.at[i, 'Power (W)'] = power

        #Consumed charge in mAh
        consumed_charge = float(intensity * duration_hr)
        output_df.at[i, 'Consumed charge(mAh)'] = consumed_charge

        #Consumed energy in Joule
        energy = float(power * duration_sec)
        output_df.at[i, 'Energy (J)'] = energy

    CSV_FULL_FILENAME = os.path.join(OUTPUT_DIR,'PowDroid_{0}.csv'.format(datetime.now().timestamp()))
    output_df.to_csv(CSV_FULL_FILENAME, float_format='%f', index=False)

    print("[powdroid] Finished! File generated: " + CSV_FULL_FILENAME)