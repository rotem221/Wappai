// Wappai web preview: shared pixel sprite atlas and motion catalog.
// Renders into a 466x466 ImageData exactly like the board.
"use strict";
const EYE = ["round", "arc_up", "arc_down", "heart", "star", "spiral", "x", "squint", "line"];
const MOUTH = ["curve", "o", "wave", "cat", "none"];
const ANIM = ["none", "sway", "bounce", "tremble", "float", "wobble", "lean"];
const FXN = ["hearts", "tears", "sweat", "zzz", "sparkles", "question", "exclaim", "anger", "notes", "steam", "dots", "blush"];
const DEG = Math.PI / 180;

// ---- sdf
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const len = (x, y) => Math.sqrt(x * x + y * y);
function sdRoundBox(px, py, bx, by, r) {
  const qx = Math.abs(px) - bx + r, qy = Math.abs(py) - by + r;
  return len(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r;
}
const sdCircle = (px, py, r) => len(px, py) - r;
function sdEllipse(px, py, a, b) {
  const k0 = len(px / a, py / b);
  if (k0 < 1e-4) return -Math.min(a, b);
  const k1 = len(px / (a * a), py / (b * b));
  return (k0 * (k0 - 1)) / k1;
}
function sdSegment(px, py, ax, ay, bx, by, r) {
  const pax = px - ax, pay = py - ay, bax = bx - ax, bay = by - ay;
  const h = clamp((pax * bax + pay * bay) / (bax * bax + bay * bay), 0, 1);
  return len(pax - bax * h, pay - bay * h) - r;
}
function sdArc(px, py, sa, ca, ra, rb) {
  px = Math.abs(px);
  const d = ca * px > sa * py ? len(px - sa * ra, py - ca * ra) : Math.abs(len(px, py) - ra);
  return d - rb;
}
function sdHeart(qx, qy, s) {
  const px = Math.abs(qx) / s, py = -qy / s + 0.55;
  let d;
  if (py + px > 1) d = len(px - 0.25, py - 0.75) - 0.35355339;
  else {
    const m = 0.5 * Math.max(px + py, 0);
    d = Math.sqrt(Math.min(px * px + (py - 1) ** 2, (px - m) ** 2 + (py - m) ** 2)) * (px - py < 0 ? -1 : 1);
  }
  return d * s;
}
function sdStar5(qx, qy, r, rf) {
  const k1x = 0.809016994, k1y = -0.587785252, k2x = -k1x, k2y = k1y;
  let px = Math.abs(qx), py = -qy;
  let d1 = Math.max(k1x * px + k1y * py, 0); px -= 2 * d1 * k1x; py -= 2 * d1 * k1y;
  let d2 = Math.max(k2x * px + k2y * py, 0); px -= 2 * d2 * k2x; py -= 2 * d2 * k2y;
  px = Math.abs(px); py -= r;
  const bax = -k1y * rf, bay = k1x * rf - 1;
  const h = clamp((px * bax + py * bay) / (bax * bax + bay * bay), 0, r);
  return len(px - bax * h, py - bay * h) * (py * bax - px * bay < 0 ? -1 : 1);
}
function sdSparkle(px, py, r) {
  px = Math.abs(px); py = Math.abs(py);
  return (Math.sqrt(px + 1e-3) + Math.sqrt(py + 1e-3) - Math.sqrt(r)) * Math.sqrt(r) * 1.2;
}
function sdSpiral(px, py, R, sp, w, ph) {
  const r = len(px, py), th = Math.atan2(py, px) + ph, b = sp / 6.2831853;
  const n = Math.round((r / b - th) / 6.2831853);
  return Math.max(Math.abs(r - b * (th + 6.2831853 * n)) - w, r - R);
}
function sdDrop(px, py, r, h) {
  const r1 = r, r2 = 0.4, qx = Math.abs(px), qy = -py;
  const b = (r1 - r2) / h, a = Math.sqrt(1 - b * b), k = -b * qx + a * qy;
  if (k < 0) return len(qx, qy) - r1;
  if (k > a * h) return len(qx, qy - h) - r2;
  return a * qx + b * qy - r1;
}
function sdPolyline(px, py, pts, r) {
  let d = 1e9;
  for (let i = 0; i + 1 < pts.length; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const e = sdSegment(px, py, ax, ay, bx, by, 0);
    if (e < d) d = e;
  }
  return d - r;
}
const cover = (d) => clamp(0.5 - d, 0, 1);
const rot2 = (x, y, c, s) => [x * c - y * s, x * s + y * c];
const hex = (h) => [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255];

// ---- params
const EYE_K = ["dx", "y", "w", "h", "r", "rot", "lidT", "lidTA", "lidB", "hl", "shape"];
const BROW_K = ["a", "y", "dx", "w", "th", "ang", "curve"];
function flatten(e) {   // resolved emotion -> float array (same order as C++ FaceP)
  const v = [];
  for (const s of ["eyeL", "eyeR"]) for (const k of EYE_K) v.push(k === "shape" ? EYE.indexOf(e[s][k]) : +e[s][k]);
  for (const s of ["browL", "browR"]) for (const k of BROW_K) v.push(+e[s][k]);
  const m = e.mouth;
  v.push(+m.dx, +m.y, +m.w, +m.curve, +m.open, +m.th, +m.rot, MOUTH.indexOf(m.shape));
  const f = e.face;
  v.push(+f.cheek, +f.dy, +f.scale, +f.rot);
  const c = parseInt(e.color.slice(1), 16);
  v.push(...hex(c), +f.glow, ANIM.indexOf(f.anim), +f.animAmp);
  let mask = 0;
  for (const x of f.fx) mask |= 1 << FXN.indexOf(x);
  v.push(mask);
  return v;
}
// float offsets
const O = {};
(() => {
  let i = 0;
  for (const s of [0, 1]) for (const k of EYE_K) O["e" + s + k] = i++;
  for (const s of [0, 1]) for (const k of BROW_K) O["b" + s + k] = i++;
  for (const k of ["mdx", "my", "mw", "mcurve", "mopen", "mth", "mrot", "mshape", "cheek", "dy", "scale", "rot", "cr", "cg", "cb", "glow", "anim", "animAmp", "fx"]) O[k] = i++;
  O.N = i;
})();

class Face {
  constructor(emotions) {
    this.names = Object.keys(emotions);
    this.table = this.names.map((n) => flatten(emotions[n]));
    this.cur = this.table[0].slice(); this.vel = new Array(O.N).fill(0); this.tgt = this.table[0].slice();
    this.emo = 0; this.t = 0; this.rig=0;this.art=[];
    this.artCanvas=document.createElement("canvas");this.artCanvas.width=466;this.artCanvas.height=466;
    this.artContext=this.artCanvas.getContext("2d",{willReadFrequently:true});
    this.eyeShape = [this.cur[O.e0shape], this.cur[O.e1shape]]; this.eyeShapeTgt = this.eyeShape.slice(); this.eyeSwap = [1, 1];
    this.mouthShape = this.cur[O.mshape]; this.mouthShapeTgt = this.mouthShape; this.mouthSwap = 1;
    this.anim = this.cur[O.anim]; this.fxA = new Array(12).fill(0); this.fxTgt = this.cur[O.fx];
    this.blink = 0; this.blinkT = 0; this.nextBlink = 2; this.doubleBlink = false;
    this.lx = 0; this.ly = 0; this.lvx = 0; this.lvy = 0; this.ltx = 0; this.lty = 0; this.lookHold = 0; this.nextSac = 1;
    this.talk = 0; this.talkS = 0; this.tilt = 0; this.tiltS = 0; this.att = false; this.attS = 0;
    this.gest = null; this.gestT = 0; this.gestDur = 0; this.centerDy = 0; this.centerDyS = 0;
  }
  async loadArt() {
    const catalog=await (await fetch('/sim/pixel-motions.json')).json();this.motions=catalog.motions;
    this.art=await Promise.all(catalog.characters.map(({id:rig})=>Promise.all(Array.from({length:24},(_,frame)=>new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src=`/sim/pixel-${rig}-${frame}.png`;})))));
  }
  setEmotion(name) {
    const i = this.names.indexOf(name);
    if (i < 0) return false;
    this.emo = i; this.tgt = this.table[i].slice();
    for (const e of [0, 1]) {
      const s = this.tgt[O["e" + e + "shape"]];
      if (s !== this.eyeShapeTgt[e]) { this.eyeShapeTgt[e] = s; if (this.eyeSwap[e] >= 1) this.eyeSwap[e] = 0; }
    }
    const ms = this.tgt[O.mshape];
    if (ms !== this.mouthShapeTgt) { this.mouthShapeTgt = ms; if (this.mouthSwap >= 1) this.mouthSwap = 0; }
    this.anim = this.tgt[O.anim]; this.fxTgt = this.tgt[O.fx];
    return true;
  }
  gesture(g) {
    if (g === "blink") { this.blinkT = 1e-4; return; }
    if (g === "look_left") return this.lookAt(-0.9, 0, 1200);
    if (g === "look_right") return this.lookAt(0.9, 0, 1200);
    const d = { nod: 0.9, shake: 0.8, jump: 0.55, bounce: 0.55, pop: 0.35, tilt_left: 1.4, tilt_right: 1.4, wiggle: 0.9 }[g];
    if (d) { this.gest = g === "bounce" ? "jump" : g; this.gestT = 0; this.gestDur = d; }
  }
  lookAt(x, y, ms) { this.ltx = clamp(x, -1, 1); this.lty = clamp(y, -1, 1); this.lookHold = ms / 1000; }
  update(dt) {
    dt = Math.min(dt, 0.1); this.t += dt;
    const w = 13;
    for (let i = 0; i < O.N; i++) {
      const a = w * w * (this.tgt[i] - this.cur[i]) - 2 * w * this.vel[i];
      this.vel[i] += a * dt; this.cur[i] += this.vel[i] * dt;
    }
    for (const e of [0, 1]) if (this.eyeSwap[e] < 1) {
      const b = this.eyeSwap[e]; this.eyeSwap[e] += dt / 0.24;
      if (b < 0.5 && this.eyeSwap[e] >= 0.5) this.eyeShape[e] = this.eyeShapeTgt[e];
      if (this.eyeSwap[e] >= 1) { this.eyeSwap[e] = 1; this.eyeShape[e] = this.eyeShapeTgt[e]; }
    }
    if (this.mouthSwap < 1) {
      const b = this.mouthSwap; this.mouthSwap += dt / 0.22;
      if (b < 0.5 && this.mouthSwap >= 0.5) this.mouthShape = this.mouthShapeTgt;
      if (this.mouthSwap >= 1) { this.mouthSwap = 1; this.mouthShape = this.mouthShapeTgt; }
    }
    for (let i = 0; i < 12; i++) { const tg = (this.fxTgt >> i) & 1; this.fxA[i] += clamp(tg - this.fxA[i], -dt * 3, dt * 3); }
    if (this.blinkT > 0) {
      this.blinkT += dt; const k = this.blinkT / 0.16;
      this.blink = k < 0.45 ? k / 0.45 : k < 1 ? 1 - (k - 0.45) / 0.55 : 0;
      if (k >= 1) { this.blinkT = 0; this.blink = 0; if (this.doubleBlink) { this.doubleBlink = false; this.blinkT = 1e-4; } }
    } else if (this.t > this.nextBlink) { this.blinkT = 1e-4; this.doubleBlink = Math.random() < 0.18; this.nextBlink = this.t + 2.2 + Math.random() * 4; }
    if (this.lookHold > 0) this.lookHold -= dt;
    else if (this.t > this.nextSac) {
      const amp = this.att ? 0.18 : 0.55;
      this.ltx = (Math.random() * 2 - 1) * amp; this.lty = (Math.random() * 2 - 1) * amp * 0.6;
      if (Math.random() < 0.35) { this.ltx = 0; this.lty = 0; }
      this.nextSac = this.t + (this.att ? 2.5 : 1.2) + Math.random() * 2.8;
    }
    const sw = 22;
    let a = sw * sw * (this.ltx - this.lx) - 2 * sw * this.lvx; this.lvx += a * dt; this.lx += this.lvx * dt;
    a = sw * sw * (this.lty - this.ly) - 2 * sw * this.lvy; this.lvy += a * dt; this.ly += this.lvy * dt;
    this.talkS += (this.talk - this.talkS) * clamp(dt * 22, 0, 1);
    this.tiltS += (clamp(this.tilt, -14, 14) - this.tiltS) * clamp(dt * 6, 0, 1);
    this.attS += ((this.att ? 1 : 0) - this.attS) * clamp(dt * 6, 0, 1);
    this.centerDyS += (this.centerDy - this.centerDyS) * clamp(dt * 8, 0, 1);
    if (this.gest) { this.gestT += dt; if (this.gestT >= this.gestDur) this.gest = null; }
  }

  render(img, cx, cy) {
    const W = img.width, H = img.height, D = img.data;
    for (let i = 0; i < D.length; i += 4) { D[i] = 0; D[i + 1] = 0; D[i + 2] = 0; D[i + 3] = 255; }
    const P = this.cur, t = this.t;
    let ox = 0, oy = P[O.dy] + this.centerDyS, sc = P[O.scale] * (1 + 0.035 * this.attS), rotd = P[O.rot] - this.tiltS * 0.6;
    const am = P[O.animAmp];
    switch (this.anim) {
      case 1: rotd += 4 * am * Math.sin(t * 2.1); ox += 5 * am * Math.sin(t * 2.1); break;
      case 2: oy -= Math.abs(Math.sin(t * 6.5)) * 11 * am; break;
      case 3: ox += 1.8 * am * Math.sin(t * 53); oy += 1.3 * am * Math.sin(t * 47); break;
      case 4: oy += 6 * am * Math.sin(t * 1.25); break;
      case 5: rotd += 7 * am * Math.sin(t * 3); break;
      case 6: sc *= 1 + 0.03 * am; break;
    }
    oy += 2.2 * Math.sin((t * 6.2831853) / 4.2);
    if (this.gest) {
      const k = this.gestT / this.gestDur, env = Math.sin(Math.PI * k);
      switch (this.gest) {
        case "nod": oy += 13 * Math.abs(Math.sin(k * 6.2831853)) * (1 - k * 0.4); break;
        case "shake": ox += 16 * Math.sin(k * 6.2831853 * 2) * (1 - k); break;
        case "jump": oy -= 34 * env; sc *= 1 + 0.03 * env; break;
        case "pop": sc *= 1 + 0.09 * env; break;
        case "tilt_left": rotd -= 11 * env; break;
        case "tilt_right": rotd += 11 * env; break;
        case "wiggle": rotd += 8 * Math.sin(k * 6.2831853 * 2) * (1 - k); break;
      }
    }
    ox += this.lx * 7; oy += this.ly * 5;
    const X = { cx: cx + ox, cy: cy + oy, s: sc, c: Math.cos(rotd * DEG), sn: Math.sin(rotd * DEG) };
    X.s*=.9;
    if(this.art[this.rig]) {
      const name=this.talkS>.04?'speaking':this.att?'listening':this.names[this.emo];
      const frames=this.motions[name]||this.motions.idle;
      let clock=(t*1000)%frames.reduce((s,f)=>s+f.ms,0),frame=frames[0].pose;
      for(const key of frames){if(clock<key.ms){frame=key.pose;break;}clock-=key.ms;}
      const a=this.artContext;a.resetTransform();a.fillStyle="#000";a.fillRect(0,0,W,H);a.imageSmoothingEnabled=false;
      a.save();a.translate(X.cx,X.cy);a.rotate(Math.atan2(X.sn,X.c));a.scale(X.s,X.s);
      a.drawImage(this.art[this.rig][frame],-160,-160,320,320);a.restore();D.set(a.getImageData(0,0,W,H).data);
    }
  }
}
