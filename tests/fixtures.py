"""Synthetic battery history used by the tests."""

T0 = 1_700_000_000_000

HISTORY = f"""\
------ CHECKIN BATTERYSTATS (dumpsys batterystats -c) ------
9,0,i,vers,36,214,QP1A,QP1A
9,hsp,0,10100,"com.example.app"
9,hsp,1,1000,"*alarm*"
9,hsp,2,10200,"com.other.app"
9,h,0:RESET:TIME:{T0}
9,h,0,Bl=90,Bv=4000,Bcc=3000,+S,+Etp=0
9,h,5000,Bv=3990,+g,+Ewl=1
9,h,10000,Bcc=2999,-g,-Ewl=1,-Etp=0,+Etp=2
9,h,20000,Bcc=2997,Bv=3980,-S,+W
9,h,10000,-W,Bcc=2996
------ NEXT SECTION ------
9,h,0,Bv=1
"""
# Timeline (device ms, relative to T0):
#   0: reset, Bv 4000, Bcc 3000, screen on, top=com.example.app
#   5000: Bv 3990, GPS on, wakelock *alarm*
#   15000: Bcc 2999, GPS off, wakelock off, top=com.other.app
#   35000: Bcc 2997, Bv 3980, screen off, wifi on
#   45000: wifi off, Bcc 2996 (end of history)
