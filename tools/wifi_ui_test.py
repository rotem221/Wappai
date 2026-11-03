"""Drives the on-device Wi-Fi setup screen through serial taps and takes screenshots (does NOT connect).
Usage: wifi_ui_test.py PORT     -> scripts/logs/w_list.png, w_keys.png, w_keys2.png"""
import sys, time, subprocess, serial
port = sys.argv[1]
def cmds(*cs, wait=0.4):
    s = serial.Serial(port, 115200, timeout=0.2)
    out = []
    for c in cs:
        s.write((c + "\n").encode()); time.sleep(wait)
        while True:
            l = s.readline()
            if not l: break
            l = l.decode(errors="replace").rstrip()
            if l and not l.startswith("ui:"): out.append(l)
    s.close(); return out
def shot(n):
    subprocess.run([sys.executable, "tools/screenshot.py", port, f"scripts/logs/{n}.png"], capture_output=True); print("shot", n)
print(cmds("state", "wifiui"))
time.sleep(7)                     # scan
shot("w_list")
print(cmds("tapxy 233 132"))      # first network
time.sleep(0.5)
for xy in ["122 159", "196 159", "270 159", "344 159", "122 215"]:   # a b c d e
    cmds("tapxy " + xy, wait=0.15)
cmds("tapxy 160 384", wait=0.2)   # shift
cmds("tapxy 122 159", wait=0.2)   # A
cmds("tapxy 233 384", wait=0.2)   # next page (p-z)
cmds("tapxy 233 384", wait=0.2)   # next page (123)
cmds("tapxy 122 159", wait=0.2)   # 1
cmds("tapxy 233 105", wait=0.2)   # show password
time.sleep(0.3)
shot("w_keys")
cmds("tapxy 233 384", wait=0.2)   # -> symbols page
time.sleep(0.3)
shot("w_keys2")
print(cmds("tapxy 233 62", "tapxy 233 40", "state"))   # back to the list, close
