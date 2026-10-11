"""Synthetic `dumpsys batterystats -c` output used by the tests."""

T0 = 1_700_000_000_000

HISTORY = f"""\
9,0,i,vers,36,214,QP1A,QP1A
9,hsp,0,10100,"com.example.app"
9,hsp,1,1000,"*alarm*"
9,hsp,2,10200,"com.other.app"
9,hsp,3,10300,"*job*/com.example.app/.Sync"
9,h,0:RESET:TIME:{T0}
9,h,0,Bl=90,Bv=4000,Bcc=3000,Bt=250,Sb=2,+S,+Etp=0
9,h,5000,Bv=3990,+g,+Ewl=1
9,h,5000,+Ewl=3
9,h,5000,Bcc=2999,-g,-Ewl=1,-Etp=0,+Etp=2
9,h,5000,-Ewl=3
9,h,15000,Bcc=2997,Bv=3980,-S,+W,Bl=89
9,h,10000,+BP,Bcc=2996
9,h,5000,Bcc=2998
9,h,5000,-BP
9,h,10000,Bcc=2997,-W
9,h,10000,Bcc=2995
9,0,l,bt,0,0,0,0,0
"""
# Timeline (device ms relative to T0):
#       0  reset; level 90 %, 4000 mV, 3000 mAh, 25.0 °C, screen on, top app com.example.app
#    5000  3990 mV, GPS on, wakelock *alarm*
#   10000  second wakelock *job*/...
#   15000  3000 -> 2999 mAh, GPS off, *alarm* released, top app com.other.app
#   20000  *job* released
#   35000  2997 mAh, 3980 mV, screen off, WiFi on, level 89 %
#   45000  plugged in, 2996 mAh
#   50000  2998 mAh (charging)
#   55000  unplugged
#   65000  2997 mAh, WiFi off
#   75000  2995 mAh (end of history)
# Currents: [0,15s) 240 mA, [15,35s) 360 mA, [35,45s) 360 mA, [45,50s) and [50,65s) unknown
# (plugged), [65,75s) 720 mA.
