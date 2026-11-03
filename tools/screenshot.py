"""Grab the device screen over USB serial (no extra libraries): python3 screenshot.py PORT out.png"""
import struct, sys, time, zlib
import serial
port, out = sys.argv[1], sys.argv[2]
s = serial.Serial(port, 115200, timeout=2)
time.sleep(0.3); s.reset_input_buffer()
s.write(b"shot\n")
t0 = time.time(); w = h = 0
while time.time() - t0 < 10:
    l = s.readline()
    if l.startswith(b"SHOT "):
        w, h = map(int, l.split()[1:3]); break
if not w:
    print("no screenshot header"); sys.exit(1)
need = w * h * 2; buf = bytearray()
while len(buf) < need and time.time() - t0 < 30:
    buf += s.read(need - len(buf))
rows = bytearray()
for y in range(h):
    rows.append(0)
    for x in range(w):
        i = (y * w + x) * 2
        v = (buf[i] << 8) | buf[i + 1] if i + 1 < len(buf) else 0
        rows += bytes((((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b"")
open(out, "wb").write(png)
print("saved", out, len(buf), "bytes")
