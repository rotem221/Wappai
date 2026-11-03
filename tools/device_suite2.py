"""Device test suite 2 (no human): voice latency, barge-in (hush while speaking), timer alarm and dismiss.
Usage: device_suite2.py PORT TOKEN      Screenshots -> scripts/logs/u_*.png"""
import sys, time, json, re, subprocess, threading, urllib.request, serial
port, token = sys.argv[1], sys.argv[2]
H = "http://192.168.1.10:8770"

def post(path, body):
    req = urllib.request.Request(f"{H}{path}?token={token}", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=10).read()

class Board:
    def __init__(self):
        self.lines, self.s, self.run = [], None, False
    def open(self):
        for _ in range(40):
            try:
                self.s = serial.Serial(port, 115200, timeout=0.2); break
            except Exception:
                time.sleep(0.25)
        self.run = True
        threading.Thread(target=self._rd, daemon=True).start()
    def _rd(self):
        while self.run:
            try:
                l = self.s.readline().decode(errors="replace").rstrip()
            except Exception:
                break
            if l and not l.startswith("ui:"):
                self.lines.append((time.time(), l))
    def close(self):
        self.run = False; time.sleep(0.3); self.s.close()
    def cmd(self, c, wait=1.0):
        n = len(self.lines); self.s.write((c + "\n").encode()); time.sleep(wait)
        return [l for _, l in self.lines[n:]]
    def state(self):
        st = [l for l in self.cmd("state") if l.startswith("state:")]
        return st[-1] if st else "(no state)"
    def since(self, n):
        return [l for _, l in self.lines[n:]]

def shot(b, name):
    b.close()
    subprocess.run([sys.executable, "tools/screenshot.py", port, f"scripts/logs/u_{name}.png"], capture_output=True)
    b.open()
    print("  shot", name)

b = Board(); b.open(); b.cmd("wake")
ok = {}

print("== 1. latency: release -> first sound (2 rounds, board hears its own speaker)")
lat = []
for q in ["פיקו, כמה זה שבע כפול שמונה?", "פיקו, מה בירת צרפת?"]:
    n = len(b.lines)
    b.cmd("ptt", 0.6)
    post("/api/say", {"text": q, "emotion": "listening"})
    time.sleep(4.2)
    b.cmd("ptt", 0.2)
    time.sleep(12)
    seq = b.since(n)
    stop = next((int(re.search(r"at (\d+)", l).group(1)) for l in seq if l.startswith("ptt: stop")), None)
    spk = [int(l.split()[2]) for l in seq if l.startswith("spk: on")]
    after = [t for t in spk if stop and t > stop]
    if stop and after:
        lat.append((after[0] - stop) / 1000)
        print(f"  '{q}': first sound {lat[-1]:.2f}s after release")
    else:
        print("  no answer audio seen:", seq[-6:])
ok["latency"] = bool(lat)

print("== 2. barge-in: short press while Piko speaks")
post("/api/say", {"text": "זה משפט ארוך במיוחד שנועד לבדוק שאפשר להשתיק אותי באמצע הדיבור בלחיצה קצרה על הכפתור, בלי לחכות שאסיים.", "emotion": "happy"})
time.sleep(3.0)
s1 = b.state(); b.cmd("tap", 0.8); s2 = b.state()
print("  before:", s1); print("  after :", s2)
ok["barge_in"] = "playing=1" in s1 and "playing=0" in s2
time.sleep(2)

print("== 3. timer: 6 s alarm, then dismiss with a short press")
post("/api/ask", {"text": "תפעיל טיימר לשש שניות בשם בדיקה"})
time.sleep(16)
s1 = b.state(); print("  ringing:", s1)
shot(b, "alarm")
b.cmd("tap", 0.8); time.sleep(1.5); s2 = b.state(); print("  after tap:", s2)
ok["timer"] = "alarm=1" in s1 and "alarm=0" in s2 and "playing=0" in s2
b.close()
print("RESULTS:", ok, "latency:", lat)
