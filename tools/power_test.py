"""BOOT button + top bar + power test. Usage: power_test.py PORT TOKEN
1) 45 s window: press / hold BOOT (person needed) - every edge is logged
2) screenshot of the top bar (scripts/logs/p_bar.png)
3) wait for screen-off -> expect lowpower=1 cpu=80; server speech -> screen on (not in pocket), cpu=240"""
import sys, time, json, subprocess, threading, urllib.request, serial
port, token = sys.argv[1], sys.argv[2]
def say(t):
    req = urllib.request.Request(f"http://192.168.1.10:8770/api/say?token={token}", data=json.dumps({"text": t}).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=10).read()
s = serial.Serial(port, 115200, timeout=0.2)
lines = []
run = True
def rd():
    while run:
        try:
            l = s.readline().decode(errors="replace").rstrip()
        except Exception:
            return
        if l and not l.startswith("ui:"):
            lines.append(l)
threading.Thread(target=rd, daemon=True).start()
def cmd(c, w=1.0):
    n = len(lines); s.write((c + "\n").encode()); time.sleep(w); return lines[n:]
print("== 1. BOOT window (45 s)", flush=True)
print(cmd("btn"))
n = len(lines)
time.sleep(45)
ev = [l for l in lines[n:] if l.startswith(("boot:", "ptt:", "state"))]
print("\n".join(ev) or "(no BOOT edges seen)")
print(cmd("btn"))
print("== 2. top bar")
run = False; time.sleep(0.3); s.close()
subprocess.run([sys.executable, "tools/screenshot.py", port, "scripts/logs/p_bar.png"], capture_output=True)
s = serial.Serial(port, 115200, timeout=0.2); run = True
threading.Thread(target=rd, daemon=True).start()
print("== 3. idle until the screen is off (100 s)")
time.sleep(100)
print([l for l in cmd("state") if l.startswith("state")])
say("בדיקת חיסכון בסוללה.")
time.sleep(4)
print([l for l in cmd("state") if l.startswith("state")])
print([l for l in lines if l.startswith(("pocket", "deep"))])
run = False
