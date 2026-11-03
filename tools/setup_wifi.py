"""Interactive Wi-Fi setup for Piko over USB: pick the network from what the DEVICE sees, type the password.
   python3 setup_wifi.py PORT"""
import getpass, sys, time
import serial

REASONS = {"201": "הרשת לא נמצאה", "202": "הסיסמה נדחתה (סיסמה שגויה)", "15": "סיסמה שגויה", "204": "סיסמה שגויה"}

def open_port(port):
    for _ in range(40):
        try:
            return serial.Serial(port, 115200, timeout=0.3)
        except Exception:
            time.sleep(0.25)
    sys.exit("❌ לא מצליח לפתוח את חיבור ה-USB למכשיר")

def read_until(s, secs, stop=None):
    lines, t0 = [], time.time()
    while time.time() - t0 < secs:
        try:
            l = s.readline()
        except Exception:
            s.close(); time.sleep(1.5); s = open_port(s.port); continue
        if l:
            l = l.decode(errors="replace").rstrip()
            lines.append(l)
            if stop and stop(l):
                break
    return s, lines

port = sys.argv[1]
s = open_port(port)
print("מאתחל את המכשיר וסורק רשתות…")
s.write(b"reboot\n")
time.sleep(1)
s, lines = read_until(s, 14, lambda l: l.startswith("wifi"))
nets = []
for l in lines:
    if l.startswith("net: "):
        name, rssi, auth = l[5:].rsplit("|", 2)
        if name not in [n[0] for n in nets]:
            nets.append((name, int(rssi), auth))
if not nets:
    sys.exit("❌ המכשיר לא החזיר רשימת רשתות. נסה שוב.")
nets.sort(key=lambda n: -n[1])
print("\nהרשתות שהמכשיר רואה (2.4GHz):")
for i, (n, r, a) in enumerate(nets, 1):
    print(f"  {i}. {n}   ({r} dBm, {a})")
while True:
    c = input("\nמספר הרשת: ").strip()
    if c.isdigit() and 1 <= int(c) <= len(nets):
        ssid = nets[int(c) - 1][0]; break
    print("בחר מספר מהרשימה")
pw = getpass.getpass(f"סיסמה עבור '{ssid}' (לא תוצג): ")
s.write(("wifiset " + ssid + "\t" + pw + "\n").encode())
pw = None
print("מתחבר…")
time.sleep(1)
s, lines = read_until(s, 45, lambda l: l.startswith("wifi: connected") or l.startswith("wifi: failed"))
res = [l for l in lines if l.startswith("wifi: connected") or l.startswith("wifi: failed")]
if res and res[-1].startswith("wifi: connected"):
    print("✅ המכשיר מחובר ל-Wi-Fi:", res[-1].split("connected", 1)[1].strip())
    s, lines = read_until(s, 25, lambda l: l.startswith("ws: connected"))
    print("✅ מחובר לשרת" if any(l.startswith("ws: connected") for l in lines) else "⏳ עדיין מתחבר לשרת")
else:
    codes = res[-1].split("reasons:")[1].split()[:2] if res and "reasons:" in res[-1] else []
    why = REASONS.get(codes[0], "שגיאה " + codes[0]) if codes else "לא ידוע"
    print("❌ החיבור נכשל:", why, "- אפשר להריץ שוב")
