import { locateEyes } from "./pip-eyes.js";
// Shared pixel artwork; only visible canvases animate, at most 30 frames/s.
const catalog = await fetch("/sim/pixel-motions.json").then((r) => r.json());
const images = new Map(),
  eyeCache = new Map();
function image(url) {
  if (!images.has(url)) {
    const i = new Image();
    i.src = url;
    images.set(url, i);
  }
  return images.get(url);
}
export class PipPlayer {
  constructor(canvas, pip) {
    this.canvas = canvas;
    this.pip = pip;
    this.motion = "idle";
    this.running = true;
    this.last = 0;
    this.tick = this.tick.bind(this);
    this.frame = requestAnimationFrame(this.tick);
  }
  stop() {
    this.running = false;
    cancelAnimationFrame(this.frame);
  }
  tick(t) {
    if (!this.running) return;
    this.frame = requestAnimationFrame(this.tick);
    if (
      document.hidden ||
      t - this.last < 33 ||
      !this.canvas.getClientRects().length
    )
      return;
    this.last = t;
    this.draw(t);
  }
  draw(t) {
    const c = this.canvas,
      ctx = c.getContext("2d"),
      p = this.pip;
    if (!p) return;
    const reduced =
      matchMedia("(prefers-reduced-motion: reduce)").matches || this.reduced;
    const motion = reduced ? "idle" : this.motion;
    const frames = catalog.motions[motion] || catalog.motions.idle;
    const total = frames.reduce((n, f) => n + f.ms, 0);
    let phase = reduced ? 0 : t % total,
      pose = frames[0].pose;
    for (const f of frames) {
      pose = f.pose;
      if (phase < f.ms) break;
      phase -= f.ms;
    }
    if (motion === "dizzy") pose = 0;
    const img = image(
      p.asset_id
        ? `/v1/pip-assets/${encodeURIComponent(p.asset_id)}/atlas.png`
        : `/sim/pixel-${p.rig || 0}-${pose}.png`,
    );
    ctx.clearRect(0, 0, c.width, c.height);
    if (!img.complete || !img.naturalWidth) return;
    ctx.save();
    ctx.scale(c.width / 120, c.height / 120);
    ctx.translate(60, 61 + (reduced ? 0 : Math.sin(t / 550) * 1.6));
    if (motion === "dizzy") ctx.rotate(Math.sin(t / 180) * 0.09);
    ctx.imageSmoothingEnabled = false;
    if (p.asset_id) {
      const columns = img.naturalWidth / 96;
      ctx.drawImage(
        img,
        (pose % columns) * 96,
        Math.floor(pose / columns) * 96,
        96,
        96,
        -48,
        -48,
        96,
        96,
      );
    } else ctx.drawImage(img, -48, -48, 96, 96);
    if (motion === "dizzy") {
      const key = p.asset_id || `rig-${p.rig || 0}`;
      const anchors = !p.asset_id
        ? catalog.characters[p.rig || 0]?.dizzyEyes
        : null;
      if (!anchors && !eyeCache.has(key)) eyeCache.set(key, locateEyes(img));
      const eyes = anchors || eyeCache.get(key);
      ctx.lineWidth = 1.5;
      for (const [x, y, rx, ry] of eyes) {
        ctx.fillStyle = "#fff8e2";
        ctx.strokeStyle = "#173640";
        ctx.beginPath();
        ctx.ellipse(x - 48, y - 48, rx, ry, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.beginPath();
        for (let k = 0; k <= 70; k++) {
          const a = (k / 70) * Math.PI * 4 + t / 180,
            r = (k / 70) * 0.73;
          const px = x - 48 + Math.cos(a) * rx * r,
            py = y - 48 + Math.sin(a) * ry * r;
          k ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
        }
        ctx.stroke();
      }
    }
    ctx.restore();
  }
}
