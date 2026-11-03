"""Read the board's serial log for N seconds and send a few diagnostic commands. Usage: serial_probe.py PORT SECONDS [cmd ...]"""
import sys, time, serial
port, secs, cmds = sys.argv[1], float(sys.argv[2]), sys.argv[3:]
s = None
for _ in range(40):
    try:
        s = serial.Serial(port, 115200, timeout=0.2); break
    except Exception:
        time.sleep(0.25)
if not s:
    print("cannot open", port); sys.exit(1)
t0 = time.time(); sent = 0
while time.time() - t0 < secs:
    try:
        line = s.readline()
    except Exception:
        s.close(); time.sleep(1.5)
        for _ in range(20):
            try:
                s = serial.Serial(port, 115200, timeout=0.2); break
            except Exception:
                time.sleep(0.5)
        continue
    if line:
        print(line.decode(errors="replace").rstrip(), flush=True)
    if sent < len(cmds) and time.time() - t0 > 2 + sent * 1.5:
        s.write((cmds[sent] + "\n").encode()); sent += 1
