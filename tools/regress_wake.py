"""Regression for the screen-off deadlock: let the screen turn off, make the server speak, check the board still answers.
Usage: regress_wake.py PORT TOKEN"""
import sys, time, serial, json, urllib.request
port, token = sys.argv[1], sys.argv[2]
H = "http://192.168.1.10:8770"
s = serial.Serial(port, 115200, timeout=0.2)
def cmd(c, wait=1.5):
    s.reset_input_buffer(); s.write((c + "\n").encode()); t0 = time.time(); out = []
    while time.time() - t0 < wait:
        l = s.readline().decode(errors="replace").rstrip()
        if l and not l.startswith("ui:"): out.append(l)
    return [l for l in out if l.startswith(c.split()[0])] or out[-2:]
print("start:", cmd("state"))
print("waiting 100 s for the screen to turn off…", flush=True)
time.sleep(100)
print("idle :", cmd("state"))
req = urllib.request.Request(f"{H}/api/say?token={token}", data=json.dumps({"text": "בדיקה, אני ער.", "emotion": "happy"}).encode(),
                             headers={"content-type": "application/json"}, method="POST")
print("say  :", urllib.request.urlopen(req, timeout=10).read().decode())
time.sleep(8)
r = cmd("state")
print("after:", r)
h = json.loads(urllib.request.urlopen(f"{H}/api/health", timeout=5).read())
print("server sees:", [d.get("fw_version") for d in h["devices"]])
print("RESULT:", "PASS" if r and "power=0" in r[0] and "server=1" in r[0] and h["devices"] else "FAIL")
