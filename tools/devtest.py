"""Scripted device test over USB serial + the server API, one serial session for everything.

    python3 tools/devtest.py PORT TOKEN OUTDIR SCRIPT

SCRIPT lines:
    cmd <serial command>          send a command to the board
    wait <seconds>                read the board log for that long (printed, without 'ui:' lines)
    ui <seconds>                  same, but print only the 'ui:' performance lines
    shot <name>                   screenshot -> OUTDIR/<name>.png
    api <GET|POST> <path> [json]  call the server (http://192.168.1.10:8770, token added)
    expect <text>                 FAIL unless <text> appeared in the log since the last expect
    # comment
"""
import json
import struct
import sys
import time
import urllib.request
import zlib

import serial

port, token, outdir, script = sys.argv[1:5]
H = "http://192.168.1.10:8770"
s = serial.Serial(port, 115200, timeout=0.2)
seen = []
fails = 0


def readfor(sec, only_ui=False):
    t0 = time.time()
    while time.time() - t0 < sec:
        l = s.readline().decode(errors="replace").rstrip()
        if not l:
            continue
        seen.append(l)
        if l.startswith("ui:") == only_ui:
            print("   ", l, flush=True)


def shot(name):
    s.reset_input_buffer()
    s.write(b"shot\n")
    t0 = time.time()
    w = h = 0
    while time.time() - t0 < 10:
        l = s.readline()
        if l.startswith(b"SHOT "):
            w, h = map(int, l.split()[1:3])
            break
    if not w:
        print("   no screenshot header")
        return
    need = w * h * 2
    buf = bytearray()
    while len(buf) < need and time.time() - t0 < 30:
        buf += s.read(need - len(buf))
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            i = (y * w + x) * 2
            v = (buf[i] << 8) | buf[i + 1] if i + 1 < len(buf) else 0
            rows += bytes((((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))
    open(f"{outdir}/{name}.png", "wb").write(png)
    print(f"   shot {name}.png")


def api(method, path, body=None):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(f"{H}{path}{sep}token={token}", method=method,
                                 data=body.encode() if body else None, headers={"content-type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=60).read().decode()
    except Exception as e:
        r = f"ERROR {e}"
    print("   api", path.split("?")[0], "->", r[:300])


mark = 0
for line in open(script, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line.strip() or line.startswith("#"):
        continue
    op, _, arg = line.partition(" ")
    print(f"> {line}", flush=True)
    if op == "cmd":
        s.write((arg + "\n").encode())
        readfor(0.3)
    elif op == "wait":
        readfor(float(arg))
    elif op == "ui":
        readfor(float(arg), only_ui=True)
    elif op == "shot":
        shot(arg)
    elif op == "api":
        parts = arg.split(" ", 2)
        api(parts[0], parts[1], parts[2] if len(parts) > 2 else None)
    elif op == "expect":
        ok = any(arg in l for l in seen[mark:])
        print("   PASS" if ok else f"   FAIL: '{arg}' not seen")
        fails += not ok
        mark = len(seen)
print(f"== {fails} failed expectations")
