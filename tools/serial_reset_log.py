"""Listen; if the board is silent, hard-reset it (RTS, like esptool) and log the boot. Usage: serial_reset_log.py PORT SECONDS [cmd ...]"""
import sys, time, serial
port, secs, cmds = sys.argv[1], float(sys.argv[2]), sys.argv[3:]
s = serial.Serial(port, 115200, timeout=0.2)
def listen(t, send=()):
    got = 0; t0 = time.time(); sent = 0
    while time.time() - t0 < t:
        try:
            line = s.readline()
        except Exception:
            time.sleep(1); return got
        if line:
            got += 1; print(line.decode(errors="replace").rstrip(), flush=True)
        if sent < len(send) and time.time() - t0 > 1 + sent * 1.5:
            s.write((send[sent] + "\n").encode()); sent += 1
    return got
print("-- probe")
if listen(6, ["info", "state"]) == 0:
    print("-- silent: hard reset")
    s.setDTR(False); s.setRTS(True); time.sleep(0.2); s.setRTS(False); s.close()
    time.sleep(2.5)
    for _ in range(30):
        try:
            s = serial.Serial(port, 115200, timeout=0.2); break
        except Exception:
            time.sleep(0.5)
listen(secs, cmds)
