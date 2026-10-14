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
"""

import os
import sys
import time

DIR = os.environ.get("FAKE_ADB_DIR", "/tmp/fake_adb")
SKEW_MS = int(os.environ.get("FAKE_ADB_SKEW_MS", "30000"))
STEP_MS = int(os.environ.get("FAKE_ADB_STEP_MS", "1000"))  # time between history records
NO_COULOMB = bool(os.environ.get("FAKE_ADB_NO_COULOMB"))


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
    while t + STEP_MS < now_ms:
        i += 1
        t += STEP_MS
        items = []
        if i % 2 == 0:  # the charge changes according to the state during the last step
            charge += 1 if plugged else -1
            items += ([] if NO_COULOMB else [f"Bcc={charge}"]) + [f"Bv={4200 - i // 2}"]
        if NO_COULOMB and i % 3 == 0 and not plugged:
            level -= 1
            items.append(f"Bl={level}")
        for at, state in plugs:
            if t - STEP_MS < at <= t:
                plugged = state
                items.append("+BP" if state else "-BP")
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
        lines.append(f"9,h,{STEP_MS}" + "".join("," + item for item in items))
    return "\n".join(lines) + "\n9,0,l,bt,0,0,0\n9,0,l,pws,3000,0,0,0\n"


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
    if args[0] not in ("shell", "exec-out"):
        print(f"fake adb: unsupported command: {command}", file=sys.stderr)
        return 1
    if state != "device":
        print("adb: no devices/emulators found", file=sys.stderr)
        return 1
    if "getprop" in command:
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
        plugs = [(int(at), state == "1") for at, state in (e.split(":") for e in read("plugs").split())]
        sys.stdout.write(history(int(read("reset", now_ms)), now_ms, plugs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
