"""A fake `adb` simulating one Android device, for tests without a phone.

State lives in $FAKE_ADB_DIR:
- `state`: "device", "unauthorized" or absent (unplugged);
- plug/unplug transitions seen by `adb devices` are logged, so the batterystats dump
  contains matching +BP/-BP events.

The device clock runs $FAKE_ADB_SKEW_MS (default 30 s) ahead of the host. `date +%s%N`
is supported unless $FAKE_ADB_SECONDS_ONLY is set (like older Android versions).
The simulated battery loses 1 mAh every 2 history steps (of $FAKE_ADB_STEP_MS) while unplugged.
With $FAKE_ADB_NO_COULOMB set, it has no coulomb counter (it reports 0) and its level drops
by 1 % (30 mAh) every 3 steps while unplugged instead.
As on Android 14+, plug changes are written after the record of their step, with a negative
time delta.

Perfetto: the device has API level $FAKE_ADB_SDK (default 35) and its tracing service
runs unless $FAKE_ADB_TRACED says otherwise (e.g. "stopped"). A trace started with
`perfetto --background` is written when it is stopped (`perfetto_trace`): one battery
poll every step, a current of 30 A and 10 A in turn every 400 ms while unplugged (2 A of
charging while plugged in), a coulomb counter counting in steps of 50 µAh, and two power
rails unless $FAKE_ADB_NO_RAILS is set. With $FAKE_ADB_OLD_PERFETTO, perfetto rejects
BATTERY_COUNTER_VOLTAGE, as versions before 2024 do. With $FAKE_ADB_NO_PULL, `adb pull`
fails (the trace is then copied with `exec-out cat`).
"""

import os
import re
import shutil
import sys
import time

from perfetto_trace import simulate

DIR = os.environ.get("FAKE_ADB_DIR", "/tmp/fake_adb")
SKEW_MS = int(os.environ.get("FAKE_ADB_SKEW_MS", "30000"))
STEP_MS = int(os.environ.get("FAKE_ADB_STEP_MS", "1000"))  # time between history records
NO_COULOMB = bool(os.environ.get("FAKE_ADB_NO_COULOMB"))
SDK = os.environ.get("FAKE_ADB_SDK", "35")
TRACED = os.environ.get("FAKE_ADB_TRACED", "running")
TRACE_PATH = "/data/misc/perfetto-traces/powdroid.pftrace"
PERFETTO_PID = 4242
RAILS = [("S4M_VDD_CPUCL0", "CPU(LITTLE)", 1.5), ("VSYS_PWR_DISPLAY", "Display", 0.5)]


def read(name, default=""):
    try:
        with open(os.path.join(DIR, name)) as f:
            return f.read().strip()
    except OSError:
        return default


def write(name, text, mode="w"):
    with open(os.path.join(DIR, name), mode) as f:
        f.write(text)


def history(reset_ms, now_ms, plugs):
    lines = ['9,0,i,vers,36,214,AP2A,AP2A', '9,hsp,0,10100,"com.example.app"',
             '9,hsp,1,1000,"*alarm*"', '9,hsp,2,1000,"*job*/com.example.sync"',
             f"9,h,0:RESET:TIME:{reset_ms}",
             f"9,h,0,Bl=90,Bv=4200,Bcc={0 if NO_COULOMB else 3000},Bt=281,Sb=2,+S,+Etp=0,+W,+BP"]
    t, charge, level, i, plugged = reset_ms, 3000, 90, 0, True
    printed = t  # time of the last record written: the deltas are relative to it
    while t + STEP_MS < now_ms:
        i += 1
        t += STEP_MS
        items, plug_items = [], []
        if i % 2 == 0:  # the charge changes according to the state during the last step
            charge += 1 if plugged else -1
            items += ([] if NO_COULOMB else [f"Bcc={charge}"]) + [f"Bv={4200 - i // 2}"]
        if NO_COULOMB and i % 3 == 0 and not plugged:
            level -= 1
            items.append(f"Bl={level}")
        for at, state in plugs:
            if t - STEP_MS < at <= t:
                plugged = state
                plug_items.append("+BP" if state else "-BP")
        if i % 10 == 5:
            items += ["-S", "-Etp=0"]
        if i % 10 == 0:
            items += ["+S", "+Etp=0"]
        if i % 6 == 3:
            items += ["+Ewl=1", "+g"]
        if i % 6 == 5:
            items += ["-Ewl=1", "-g"]
        if i % 8 == 4:
            items.append("+Ewl=2")
        if i % 8 == 7:
            items.append("-Ewl=2")
        if i == 20 and not NO_COULOMB:
            items.append("Bl=89")
        lines.append(f"9,h,{t - printed}" + "".join("," + item for item in items))
        printed = t
        if plug_items:  # written late, stamped a little before the step's record
            lines.append(f"9,h,{-(STEP_MS // 2)}," + ",".join(plug_items))
            printed = t - STEP_MS // 2
    return "\n".join(lines) + "\n9,0,l,bt,0,0,0\n9,0,l,pws,3000,0,0,0\n"


def trace_current(plugs):
    """The battery current of the fake trace (mA) at device time t: plugged in until the first unplug."""
    def current(t):
        plugged = True
        for at, state in plugs:
            if at <= t:
                plugged = state
        return -2000 if plugged else 30000 if t // 400 % 2 == 0 else 10000
    return current


def perfetto(command, now_ms, plugs):
    """Answer the perfetto commands of core/perfetto.py; returns the exit code."""
    running = read("perfetto")  # "<start ms> <voltage recorded>" while a trace runs
    trace = os.path.join(DIR, "trace.pftrace")
    if command.startswith("shell perfetto "):
        config = sys.stdin.read()
        if os.environ.get("FAKE_ADB_OLD_PERFETTO") and "BATTERY_COUNTER_VOLTAGE" in config:
            print("Unexpected value 'BATTERY_COUNTER_VOLTAGE' for enum BatteryCounters", file=sys.stderr)
            return 1
        if 'name: "android.power"' not in config or f"-o {TRACE_PATH}" not in command:
            print(f"fake perfetto: unexpected trace: {command}\n{config}", file=sys.stderr)
            return 1
        write("perfetto", f"{now_ms} {int('BATTERY_COUNTER_VOLTAGE' in config)}")
        print(PERFETTO_PID)
    elif "kill -TERM" in command and "echo stopped" in command:  # stop
        if running:
            start_ms, voltage = map(int, running.split())
            with open(trace, "wb") as f:
                f.write(simulate(start_ms, now_ms, trace_current(plugs), poll_ms=STEP_MS, resolution_uah=50,
                                 voltage=bool(voltage), rails=[] if os.environ.get("FAKE_ADB_NO_RAILS") else RAILS))
            os.remove(os.path.join(DIR, "perfetto"))
        print("stopped" if running else "already-stopped")
    elif "[ -d /proc/" in command:  # is it still running?
        print("running" if running else "stopped")
    elif "pkill -f" in command and re.search(command.split("'")[1], command):
        return 143  # as on a phone: the pattern matches the command line of the shell running pkill
    elif "kill -TERM" in command or "pkill" in command:  # cancel, or clean up a trace left running
        for name in ("perfetto", "trace.pftrace"):
            if os.path.exists(os.path.join(DIR, name)):
                os.remove(os.path.join(DIR, name))
    elif command == f"shell rm -f {TRACE_PATH}":
        if os.path.exists(trace):
            os.remove(trace)
    elif command.startswith(f"pull {TRACE_PATH} "):
        if os.environ.get("FAKE_ADB_NO_PULL") or not os.path.exists(trace):
            print(f"adb: error: failed to stat remote object '{TRACE_PATH}': Permission denied", file=sys.stderr)
            return 1
        shutil.copyfile(trace, command.split(" ", 2)[2])
        print(f"{TRACE_PATH}: 1 file pulled, 0 skipped.")
    elif command == f"exec-out cat {TRACE_PATH}":
        with open(trace, "rb") as f:
            sys.stdout.buffer.write(f.read())
    else:
        return None
    return 0


def main(args):
    os.makedirs(DIR, exist_ok=True)
    if args[:1] == ["-s"]:
        args = args[2:]
    state = read("state")
    now_ms = int(time.time() * 1000) + SKEW_MS
    command = " ".join(args)

    if args[0] in ("version", "start-server"):
        print("Android Debug Bridge version 1.0.41 (fake)")
        return 0
    if args[0] == "devices":
        plugged = state == "device"
        log = read("plugs").split()
        if plugged != (log[-1].endswith(":1") if log else True):
            write("plugs", f"{now_ms}:{int(plugged)}\n", "a")
        print("List of devices attached")
        if state:
            print(f"FAKE123\t{state}")
        return 0
    if args[0] not in ("shell", "exec-out", "pull"):
        print(f"fake adb: unsupported command: {command}", file=sys.stderr)
        return 1
    if state != "device":
        print("adb: no devices/emulators found", file=sys.stderr)
        return 1
    plugs = [(int(at), state == "1") for at, state in (e.split(":") for e in read("plugs").split())]
    code = perfetto(command, now_ms, plugs)
    if code is not None:
        return code
    if "init.svc.traced" in command:
        print(f"{SDK}\n{TRACED}")
    elif "getprop" in command:
        print("Google\nPixel 8 (fake)\n15")
    elif "--reset" in command:
        write("reset", str(now_ms))
        write("plugs", "")
    elif args[1] == "date":
        seconds_only = os.environ.get("FAKE_ADB_SECONDS_ONLY") or args[2] == "+%s"
        print(now_ms // 1000 if seconds_only else now_ms * 1_000_000)
    elif args[1:] == ["dumpsys", "battery"]:
        print(f"Current Battery Service state:\n  level: 90\n  Charge counter: {0 if NO_COULOMB else 3000000}")
    elif args[1:] == ["dumpsys", "batterystats", "-c"]:
        sys.stdout.write(history(int(read("reset", now_ms)), now_ms, plugs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
