"""Simulated BOOT hold (serial 'bootsim'): one recording of ~3 s must come out. Also prints the UI frame stats."""
import sys, time, serial
s = serial.Serial(sys.argv[1], 115200, timeout=0.2)
def run(c, w):
    s.write((c + "\n").encode()); t0 = time.time(); out = []
    while time.time() - t0 < w:
        l = s.readline().decode(errors="replace").rstrip()
        if l: out.append(f"{time.time()-T0:5.1f} {l}")
    return out
T0 = time.time()
out = run("wake", 1) + run("bootsim 1", 3.2) + run("bootsim 0", 1) + run("bootsim -1", 12)
print("\n".join(l for l in out if any(k in l for k in ("ptt", "boot", "ui:", "spk"))))
