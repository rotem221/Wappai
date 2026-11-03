"""Full voice-path test without a human: start push-to-talk over serial, make the board's own speaker say a question
(server TTS), stop, and print the board log. The mic hears the speaker, so this exercises mic -> STT -> Claude -> TTS.
Usage: loopback_test.py PORT TOKEN "question" """
import sys, time, json, threading, urllib.request, serial
port, token, q = sys.argv[1], sys.argv[2], sys.argv[3]
s = serial.Serial(port, 115200, timeout=0.2)
log = []
stop = False
def reader():
    while not stop:
        l = s.readline().decode(errors="replace").rstrip()
        if l and not l.startswith("ui:"):
            log.append(f"{time.time() - t0:5.1f}s {l}")
t0 = time.time()
threading.Thread(target=reader, daemon=True).start()
s.write(b"wake\n"); time.sleep(1)
s.write(b"ptt\n"); time.sleep(0.8)
req = urllib.request.Request(f"http://192.168.1.10:8770/api/say?token={token}",
                             data=json.dumps({"text": q, "emotion": "listening"}).encode(),
                             headers={"content-type": "application/json"}, method="POST")
urllib.request.urlopen(req, timeout=10).read()
time.sleep(float(sys.argv[4]) if len(sys.argv) > 4 else 4.5)
s.write(b"ptt\n")
time.sleep(14)
stop = True
print("\n".join(log))
