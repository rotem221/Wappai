// Same one-time component analysis and bounded fallback as firmware dizzy_eyes.h.
export function locateEyes(image) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 96;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(image, 0, 0, 96, 96, 0, 0, 96, 96);
  const data = ctx.getImageData(0, 0, 96, 96).data;
  let left = 96,
    top = 96,
    right = 0,
    bottom = 0;
  for (let y = 0; y < 96; y++)
    for (let x = 0; x < 96; x++)
      if (data[(y * 96 + x) * 4 + 3] > 127) {
        left = Math.min(left, x);
        right = Math.max(right, x + 1);
        top = Math.min(top, y);
        bottom = Math.max(bottom, y + 1);
      }
  const w = right - left,
    h = bottom - top,
    cx = (left + right) / 2,
    rx = Math.max(4, Math.min(8, w * 0.08));
  let result = [
      [cx - w * 0.16, top + h * 0.38, rx, rx * 1.3],
      [cx + w * 0.16, top + h * 0.38, rx, rx * 1.3],
    ],
    best = -1e9;
  const l = Math.floor(left + w * 0.1),
    r = Math.floor(right - w * 0.1),
    t = Math.floor(top + h * 0.12),
    b = Math.floor(top + h * 0.66);
  for (const bright of [false, true]) {
    const seen = new Uint8Array(9216),
      boxes = [];
    function eligible(p) {
      const i = p * 4;
      return (
        data[i + 3] > 127 &&
        (bright
          ? Math.min(data[i], data[i + 1], data[i + 2]) >= 170
          : Math.max(data[i], data[i + 1], data[i + 2]) < 135)
      );
    }
    for (let y = t; y < b; y++)
      for (let x = l; x < r; x++) {
        const at = y * 96 + x;
        if (seen[at] || !eligible(at)) continue;
        const box = { l: x, r: x + 1, t: y, b: y + 1, area: 0 },
          stack = [at];
        seen[at] = 1;
        while (stack.length) {
          const p = stack.pop(),
            px = p % 96,
            py = Math.floor(p / 96);
          box.l = Math.min(box.l, px);
          box.r = Math.max(box.r, px + 1);
          box.t = Math.min(box.t, py);
          box.b = Math.max(box.b, py + 1);
          box.area++;
          for (const d of [-1, 1, -96, 96]) {
            const q = p + d,
              qx = q % 96,
              qy = Math.floor(q / 96);
            if (
              qx < l ||
              qx >= r ||
              qy < t ||
              qy >= b ||
              seen[q] ||
              !eligible(q)
            )
              continue;
            seen[q] = 1;
            stack.push(q);
          }
        }
        const bw = box.r - box.l,
          bh = box.b - box.t;
        if (
          bw >= 3 &&
          bw <= 18 &&
          bh >= 4 &&
          bh <= 22 &&
          box.area >= 10 &&
          box.area <= 220 &&
          bw <= bh * 2 &&
          bh <= bw * 3 &&
          boxes.length < 96
        )
          boxes.push(box);
      }
    for (const a of boxes)
      for (const b of boxes) {
        const ax = (a.l + a.r) / 2,
          bx = (b.l + b.r) / 2,
          ay = (a.t + a.b) / 2,
          by = (b.t + b.b) / 2;
        if (
          bx - ax < 10 ||
          bx - ax > 38 ||
          Math.abs(ay - by) > 5 ||
          a.area > b.area * 2.2 ||
          b.area > a.area * 2.2 ||
          Math.abs((ax + bx) / 2 - cx) > w * 0.2
        )
          continue;
        const score =
          a.area +
          b.area -
          8 * Math.abs(ay - by) -
          2 * Math.abs((ax + bx) / 2 - cx) -
          Math.abs((ay + by) / 2 - (top + h * 0.36));
        if (score <= best) continue;
        best = score;
        result = [
          [
            ax,
            ay,
            Math.min(10, (a.r - a.l) / 2 + 1.5),
            Math.min(12, (a.b - a.t) / 2 + 1.5),
          ],
          [
            bx,
            by,
            Math.min(10, (b.r - b.l) / 2 + 1.5),
            Math.min(12, (b.b - b.t) / 2 + 1.5),
          ],
        ];
      }
  }
  return result;
}
