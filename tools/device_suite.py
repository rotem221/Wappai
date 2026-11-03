"""Device test suite (no human): long subtitle, meeting recorded through the board's own mic, timer alarm.
Screenshots -> scripts/logs/t_*.png. Usage: device_suite.py PORT TOKEN"""
import sys, time, json, subprocess, urllib.request
port, token = sys.argv[1], sys.argv[2]
H = "http://192.168.1.10:8770"
def say(text, emo="happy"):
    req = urllib.request.Request(f"{H}/api/say?token={token}", data=json.dumps({"text": text, "emotion": emo}).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=10).read()
def serial_cmd(*cmds, secs=2.6):
    out = subprocess.run([sys.executable, "tools/serial_probe.py", port, str(secs), *cmds], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if not l.startswith("ui:")]
def shot(name):
    subprocess.run([sys.executable, "tools/screenshot.py", port, f"scripts/logs/t_{name}.png"], capture_output=True)
    print("shot", name, flush=True)

print("== long subtitle while talking")
say("השעה עכשיו עשר וחמישים בערב. מחר יהיה מעונן חלקית, בין שמונה עשרה לעשרים ושבע מעלות, וכמעט בלי סיכוי לגשם. אפשר לצאת בלי מטרייה.")
time.sleep(2.2); shot("talk1")
time.sleep(12)

print("== meeting through the mic")
print(serial_cmd("meet"))
time.sleep(1)
shot("meeting")
say("נתחיל. הוחלט שההשקה תהיה ביום ראשון. יוסי מכין את המצגת עד יום חמישי. תודה לכולם.", "speaking")
time.sleep(11)
print(serial_cmd("meet"))
time.sleep(1.5); shot("summary_wait")
time.sleep(14); shot("summary")
time.sleep(10)
