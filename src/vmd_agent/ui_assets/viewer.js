"use strict";
/* A small molecular viewer on a 2D canvas: atoms, bonds and a backbone trace, rotated with the mouse.
   Colour methods and drawing styles carry VMD's names (Name, Chain, ResType, Index; Lines, Trace, VDW, Points) and its default colours.
   It draws what the server sends (vmd_agent.structure.viewer) and nothing else. */

const VMD_IDS = ["#3b6bff", "#ff4a4a", "#9aa0aa", "#ff9a2e", "#ffe14a", "#d8b98a", "#c9ced6", "#3fd16a", "#f4f4f4", "#ff9cc8",
                 "#27d8e6", "#a56bff", "#a6e22e", "#c98bb4", "#d6a53a", "#8ed0ff"];
const ELEMENT_COLOR = { C: "#27d8e6", N: "#3b6bff", O: "#ff4a4a", H: "#f4f4f4", S: "#ffe14a", P: "#d8b98a", FE: "#ff9a2e", ZN: "#9aa0aa",
                        NA: "#a56bff", CL: "#3fd16a", MG: "#3fd16a", CA: "#c9ced6" };
const RESTYPE_COLOR = ["#ff4a4a", "#3b6bff", "#3fd16a", "#f4f4f4", "#27d8e6", "#9aa0aa"];     // acidic, basic, polar, nonpolar, water, other
const RADIUS = { H: 1.1, C: 1.7, N: 1.55, O: 1.52, S: 1.8, P: 1.8, FE: 1.5, ZN: 1.4, NA: 2.2, CL: 1.75, MG: 1.7, CA: 2.3 };

function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function shade(rgb, k) { return `rgb(${Math.round(rgb[0] * k)},${Math.round(rgb[1] * k)},${Math.round(rgb[2] * k)})`; }
function rainbow(t) {                                   // VMD's Index/Timestep scale: blue through green to red
  const stops = [[59, 107, 255], [39, 216, 230], [63, 209, 106], [255, 225, 74], [255, 74, 74]];
  const x = Math.min(0.9999, Math.max(0, t)) * (stops.length - 1), i = Math.floor(x), f = x - i;
  return stops[i].map((v, k) => v + (stops[i + 1][k] - v) * f);
}

class Viewer {
  constructor(canvas) {
    this.cv = canvas; this.ctx = canvas.getContext("2d");
    this.mol = null; this.xyz = null; this.R = [1, 0, 0, 0, 1, 0, 0, 0, 1]; this.zoom = 1; this.pan = [0, 0];
    this.rep = "Trace"; this.color = "Name"; this.show = { protein: true, other: true, water: false };
    this.dirty = true; this.frames = new Map(); this.frame = 0;
    const down = {};
    canvas.addEventListener("pointerdown", e => { canvas.setPointerCapture(e.pointerId); down.x = e.clientX; down.y = e.clientY; down.b = e.button; down.shift = e.shiftKey; canvas.classList.add("drag"); });
    canvas.addEventListener("pointermove", e => {
      if (down.x == null) return;
      const dx = e.clientX - down.x, dy = e.clientY - down.y; down.x = e.clientX; down.y = e.clientY;
      if (down.b === 2 || down.shift) { this.pan[0] += dx; this.pan[1] += dy; } else this.rotate(dy * 0.008, dx * 0.008);
      this.dirty = true;
    });
    const up = () => { down.x = null; canvas.classList.remove("drag"); };
    canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("contextmenu", e => e.preventDefault());
    canvas.addEventListener("wheel", e => { e.preventDefault(); this.zoom = Math.min(30, Math.max(0.08, this.zoom * Math.exp(-e.deltaY * 0.0015))); this.dirty = true; }, { passive: false });
    canvas.addEventListener("dblclick", () => this.reset());
    new ResizeObserver(() => this.resize()).observe(canvas);
    const loop = () => { if (this.dirty) { this.dirty = false; this.draw(); } requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }

  resize() {
    const r = this.cv.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    this.cv.width = Math.max(1, Math.round(r.width * d)); this.cv.height = Math.max(1, Math.round(r.height * d)); this.d = d; this.dirty = true;
  }

  rotate(ax, ay) {                                       // a turn about the screen's x then y axis, applied to the model
    const cx = Math.cos(ax), sx = Math.sin(ax), cy = Math.cos(ay), sy = Math.sin(ay);
    const Rx = [1, 0, 0, 0, cx, -sx, 0, sx, cx], Ry = [cy, 0, sy, 0, 1, 0, -sy, 0, cy];
    this.R = mul(Rx, mul(Ry, this.R));
  }

  reset() { this.R = [1, 0, 0, 0, 1, 0, 0, 0, 1]; this.zoom = 1; this.pan = [0, 0]; this.dirty = true; }

  load(mol) {
    this.mol = mol; this.xyz = Float32Array.from(mol.xyz); this.frame = 0; this.frames = new Map(); this.frames.set(0, this.xyz);
    this.reset(); this.prepare();
  }

  setFrame(i, xyz) { this.frame = i; this.xyz = Float32Array.from(xyz); this.frames.set(i, this.xyz); this.dirty = true; }

  prepare() {                                            // everything that does not change with the frame or the view
    const m = this.mol; if (!m) return; const n = m.n_atoms;
    this.group = new Uint8Array(n);                       // 0 protein, 1 other, 2 water
    for (let i = 0; i < n; i++) this.group[i] = m.is_water[i] ? 2 : (m.is_protein[i] || m.is_ca[i] && m.restype[i] < 4) ? 0 : 1;
    const hasProtein = this.group.some(g => g === 0);
    this.rep = this.rep === "Trace" && !hasProtein ? "Lines" : this.rep;
    this.dirty = true;
  }

  atomColor(i) {
    const m = this.mol;
    switch (this.color) {
      case "Chain": return hexToRgb(VMD_IDS[(m.chain[i] * 3 + 1) % VMD_IDS.length]);
      case "ResType": return hexToRgb(RESTYPE_COLOR[m.restype[i]] || "#9aa0aa");
      case "Index": return rainbow(i / Math.max(1, m.n_atoms - 1));
      case "Resid": return rainbow((m.resid[i] - this.ridMin) / Math.max(1, this.ridMax - this.ridMin));
      case "Mono": return hexToRgb("#c9ced6");
      default: return hexToRgb(ELEMENT_COLOR[m.elements[m.element[i]]] || "#c9ced6");
    }
  }

  project() {
    const m = this.mol, n = m.n_atoms, R = this.R, c = m.centre, w = this.cv.width, h = this.cv.height, d = this.d || 1;
    const px = new Float32Array(n), py = new Float32Array(n), pz = new Float32Array(n), ps = new Float32Array(n);
    const dist = m.radius * 3.2, base = Math.min(w, h) / (2.2 * m.radius) * this.zoom, ox = w / 2 + this.pan[0] * d, oy = h / 2 + this.pan[1] * d, xyz = this.xyz;
    for (let i = 0; i < n; i++) {
      const x = xyz[3 * i] - c[0], y = xyz[3 * i + 1] - c[1], z = xyz[3 * i + 2] - c[2];
      const X = R[0] * x + R[1] * y + R[2] * z, Y = R[3] * x + R[4] * y + R[5] * z, Z = R[6] * x + R[7] * y + R[8] * z;
      const f = dist / (dist - Z);                        // perspective, as VMD's default
      px[i] = ox + X * base * f; py[i] = oy - Y * base * f; pz[i] = Z; ps[i] = base * f;
    }
    return { px, py, pz, ps, base, dist };
  }

  visible(i) { const g = this.group[i]; return g === 0 ? this.show.protein : g === 1 ? this.show.other : this.show.water; }

  draw() {
    const ctx = this.ctx, w = this.cv.width, h = this.cv.height;
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, w, h);
    const m = this.mol; if (!m) return;
    if (this.color === "Resid") {                          // the scale runs over the protein's residues, so a ligand numbered 900 does not flatten it
      let lo = 1e9, hi = -1e9; for (let i = 0; i < m.n_atoms; i++) { if (this.group[i] === 0) { lo = Math.min(lo, m.resid[i]); hi = Math.max(hi, m.resid[i]); } }
      this.ridMin = lo < hi ? lo : 0; this.ridMax = lo < hi ? hi : Math.max(1, m.n_atoms);
    }
    const P = this.project(), r = m.radius, near = -r, far = r;
    const depth = i => 0.38 + 0.62 * Math.min(1, Math.max(0, (P.pz[i] - near) / (far - near)));        // depth cueing: farther is dimmer
    const cols = new Array(m.n_atoms);
    for (let i = 0; i < m.n_atoms; i++) cols[i] = this.visible(i) ? this.atomColor(i) : null;
    const lw = Math.max(1, (this.d || 1) * 1.4);
    if (this.rep === "VDW" && m.n_atoms <= 9000) this.drawSpheres(P, cols, depth);
    else if (this.rep === "Points") this.drawPoints(P, cols, depth);
    else {
      this.drawBonds(P, cols, depth, lw, this.rep === "Trace");
      if (this.rep === "Trace") this.drawTrace(P, cols, depth, lw * 2.6);
    }
    this.drawAxes();
  }

  drawBonds(P, cols, depth, lw, skipProtein) {
    const ctx = this.ctx, m = this.mol, buckets = new Map();
    for (const [a, b] of m.bonds) {
      if (!cols[a] || !cols[b]) continue;
      if (skipProtein && this.group[a] === 0 && this.group[b] === 0) continue;
      const mx = (P.px[a] + P.px[b]) / 2, my = (P.py[a] + P.py[b]) / 2, k = Math.round(depth(a) * 3);
      for (const [i, x, y] of [[a, P.px[a], P.py[a]], [b, P.px[b], P.py[b]]]) {
        const key = cols[i].join(",") + "|" + k; let s = buckets.get(key); if (!s) buckets.set(key, s = { c: cols[i], k, seg: [] });
        s.seg.push(x, y, mx, my);
      }
    }
    ctx.lineWidth = lw; ctx.lineCap = "round";
    for (const s of buckets.values()) {
      ctx.strokeStyle = shade(s.c, 0.4 + 0.2 * s.k); ctx.beginPath();
      for (let i = 0; i < s.seg.length; i += 4) { ctx.moveTo(s.seg[i], s.seg[i + 1]); ctx.lineTo(s.seg[i + 2], s.seg[i + 3]); }
      ctx.stroke();
    }
  }

  drawTrace(P, cols, depth, lw) {                         // the alpha-carbon chain, one colour per residue, with a dimmer shadow under it
    const ctx = this.ctx, m = this.mol; let prev = -1;
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    for (let i = 0; i < m.n_atoms; i++) {
      if (!m.is_ca[i] || this.group[i] !== 0 || !cols[i]) { continue; }
      if (prev >= 0 && m.chain[prev] === m.chain[i]) {
        const dx = this.xyz[3 * i] - this.xyz[3 * prev], dy = this.xyz[3 * i + 1] - this.xyz[3 * prev + 1], dz = this.xyz[3 * i + 2] - this.xyz[3 * prev + 2];
        if (dx * dx + dy * dy + dz * dz < 20.25) {         // 4.5 A: consecutive residues, not a gap in the chain
          const g = ctx.createLinearGradient(P.px[prev], P.py[prev], P.px[i], P.py[i]);
          g.addColorStop(0, shade(cols[prev], depth(prev))); g.addColorStop(1, shade(cols[i], depth(i)));
          ctx.strokeStyle = g; ctx.lineWidth = lw * Math.min(1.6, Math.max(0.6, P.ps[i] / P.base)); ctx.beginPath(); ctx.moveTo(P.px[prev], P.py[prev]); ctx.lineTo(P.px[i], P.py[i]); ctx.stroke();
        }
      }
      prev = i;
    }
  }

  drawSpheres(P, cols, depth) {
    const ctx = this.ctx, m = this.mol, order = [];
    for (let i = 0; i < m.n_atoms; i++) if (cols[i]) order.push(i);
    order.sort((a, b) => P.pz[a] - P.pz[b]);
    for (const i of order) {
      const rad = (RADIUS[m.elements[m.element[i]]] || 1.7) * P.ps[i] * 0.55, x = P.px[i], y = P.py[i], k = depth(i);
      ctx.fillStyle = shade(cols[i], k * 0.85); ctx.beginPath(); ctx.arc(x, y, rad, 0, 6.2832); ctx.fill();
      ctx.fillStyle = shade(cols[i].map(v => Math.min(255, v * 1.5 + 40)), k * 0.9); ctx.beginPath(); ctx.arc(x - rad * 0.32, y - rad * 0.32, rad * 0.38, 0, 6.2832); ctx.fill();
    }
  }

  drawPoints(P, cols, depth) {
    const ctx = this.ctx, m = this.mol, s = Math.max(1.5, (this.d || 1) * 2);
    for (let i = 0; i < m.n_atoms; i++) { if (!cols[i]) continue; ctx.fillStyle = shade(cols[i], depth(i)); ctx.fillRect(P.px[i] - s / 2, P.py[i] - s / 2, s, s); }
  }

  drawAxes() {                                            // VMD's axes: x red, y green, z blue, bottom left
    const ctx = this.ctx, d = this.d || 1, o = [48 * d, this.cv.height - 62 * d], L = 26 * d, R = this.R;
    ctx.lineWidth = 1.6 * d; ctx.font = `${11 * d}px ui-monospace, Menlo, monospace`;
    [["x", "#ff4a4a", 0], ["y", "#3fd16a", 1], ["z", "#4a7bff", 2]].forEach(([label, col, k]) => {
      const ex = R[k] * L, ey = -R[3 + k] * L;
      ctx.strokeStyle = col; ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(o[0], o[1]); ctx.lineTo(o[0] + ex, o[1] + ey); ctx.stroke(); ctx.fillText(label, o[0] + ex * 1.18 - 3 * d, o[1] + ey * 1.18 + 4 * d);
    });
  }

  png() { return new Promise(res => this.cv.toBlob(res, "image/png")); }
}

function mul(A, B) {
  const C = new Array(9);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) C[3 * i + j] = A[3 * i] * B[j] + A[3 * i + 1] * B[3 + j] + A[3 * i + 2] * B[6 + j];
  return C;
}
