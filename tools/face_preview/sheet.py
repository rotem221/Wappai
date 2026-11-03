"""Turn preview frames into PNG contact sheet / GIF.  python3 sheet.py all <dir> <out.png> | gif <dir> <out.gif>"""
import sys, pathlib, numpy as np
from PIL import Image, ImageDraw, ImageFont
W = H = 466
def load(p):
    a = np.fromfile(p, dtype="<u2").reshape(H, W).astype(np.uint32)
    r = ((a >> 11) & 31) * 255 // 31; g = ((a >> 5) & 63) * 255 // 63; b = (a & 31) * 255 // 31
    img = Image.fromarray(np.dstack([r, g, b]).astype(np.uint8))
    m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).ellipse((0, 0, W - 1, H - 1), fill=255)
    bg = Image.new("RGB", (W, H), (28, 28, 32)); bg.paste(img, mask=m); return bg
mode, d, out = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3]
if mode == "all":
    files = sorted(d.glob("*.rgb565"), key=lambda p: p.stat().st_mtime)
    cols = 6; s = 220; rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * s, rows * (s + 24)), (18, 18, 22)); dr = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = load(f).resize((s - 10, s - 10), Image.LANCZOS)
        x, y = (i % cols) * s, (i // cols) * (s + 24)
        sheet.paste(im, (x + 5, y + 5)); dr.text((x + 8, y + s - 2), f.stem, fill=(220, 220, 220))
    sheet.save(out)
else:
    frames = [load(f).resize((300, 300), Image.LANCZOS) for f in sorted(d.glob("f*.rgb565"))]
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=40, loop=0)
print(out)
