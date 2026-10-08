"use strict";
/* The molecule viewer: several molecules, each with its own list of representations (a selection, a drawing style, a colour method), drawn on one 2D canvas
 * and moved with VMD's mouse modes. Names follow VMD's: styles Lines, Licorice, CPK, VDW, Points, Trace, Tube; colour methods Name, Chain, ResType, Resid, Index,
 * ColorID; projection Perspective or Orthographic; depth cueing; axes; background. It draws what the server sends (vmd_agent.structure.viewer) and nothing else.
 */
const VMD_IDS = [["blue", "#3b6bff"], ["red", "#ff4a4a"], ["gray", "#9aa0aa"], ["orange", "#ff9a2e"], ["yellow", "#ffe14a"], ["tan", "#d8b98a"], ["silver", "#c9ced6"], ["green", "#3fd16a"],
                 ["white", "#f4f4f4"], ["pink", "#ff9cc8"], ["cyan", "#27d8e6"], ["purple", "#a56bff"], ["lime", "#a6e22e"], ["mauve", "#c98bb4"], ["ochre", "#d6a53a"], ["iceblue", "#8ed0ff"]];
const ELEMENT_COLOR = { C: "#27d8e6", N: "#3b6bff", O: "#ff4a4a", H: "#f4f4f4", S: "#ffe14a", P: "#d8b98a", FE: "#ff9a2e", ZN: "#9aa0aa", NA: "#a56bff", CL: "#3fd16a", MG: "#3fd16a", CA: "#c9ced6" };
const RESTYPE_COLOR = ["#ff4a4a", "#3b6bff", "#3fd16a", "#f4f4f4", "#27d8e6", "#9aa0aa"];     // acidic, basic, polar, nonpolar, water, other
const RADIUS = { H: 1.1, C: 1.7, N: 1.55, O: 1.52, S: 1.8, P: 1.8, FE: 1.5, ZN: 1.4, NA: 2.2, CL: 1.75, MG: 1.7, CA: 2.3 };
const STYLES = ["Lines", "Licorice", "CPK", "VDW", "Points", "Trace", "Tube"];
const COLOR_METHODS = ["Name", "Chain", "ResType", "Resid", "Index", "ColorID"];
const BACKGROUNDS = { black: "#000000", gray: "#50545c", white: "#ffffff" };

const hex = h => { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const mix = (rgb, bg, k) => `rgb(${Math.round(rgb[0] * k + bg[0] * (1 - k))},${Math.round(rgb[1] * k + bg[1] * (1 - k))},${Math.round(rgb[2] * k + bg[2] * (1 - k))})`;
function rainbow(t) {                                   // VMD's Index and Resid scale: blue through green to red
  const stops = [[59, 107, 255], [39, 216, 230], [63, 209, 106], [255, 225, 74], [255, 74, 74]];
  const x = Math.min(0.9999, Math.max(0, t)) * (stops.length - 1), i = Math.floor(x), f = x - i;
  return stops[i].map((v, k) => v + (stops[i + 1][k] - v) * f);
}
function mul(A, B) { const C = new Array(9); for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) C[3 * i + j] = A[3 * i] * B[j] + A[3 * i + 1] * B[3 + j] + A[3 * i + 2] * B[6 + j]; return C; }
const IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1];

class Viewer {
  constructor(canvas) {
    this.cv = canvas; this.ctx = canvas.getContext("2d");
    this.mols = []; this.top = null; this.nextId = 0;
    this.R = IDENTITY.slice(); this.zoom = 1; this.pan = [0, 0];
    this.settings = { projection: "Perspective", depthcue: true, axes: "LowerLeft", background: "black", mouse: "rotate" };
    this.centre = [0, 0, 0]; this.radius = 10; this.dirty = true; this.picked = null; this.onpick = null; this.onchange = null;
    this.projected = new Map();
    const down = {};
    canvas.addEventListener("pointerdown", e => { canvas.setPointerCapture(e.pointerId); Object.assign(down, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, b: e.button, shift: e.shiftKey }); canvas.classList.add("drag"); });
    canvas.addEventListener("pointermove", e => {
      if (down.x == null) return;
      const dx = e.clientX - down.x, dy = e.clientY - down.y; down.x = e.clientX; down.y = e.clientY;
      const mode = down.b === 2 || down.shift ? "translate" : this.settings.mouse;
      if (mode === "translate") { this.pan[0] += dx; this.pan[1] += dy; }
      else if (mode === "scale") this.zoom = Math.min(40, Math.max(0.05, this.zoom * Math.exp(-dy * 0.01)));
      else if (mode === "rotate") this.rotate(dy * 0.008, dx * 0.008);
      this.dirty = true;
    });
    const up = e => {
      if (down.x != null && this.settings.mouse === "pick" && Math.hypot(e.clientX - down.x0, e.clientY - down.y0) < 4) this.pick(e);
      down.x = null; canvas.classList.remove("drag");
    };
    canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", () => { down.x = null; canvas.classList.remove("drag"); });
    canvas.addEventListener("contextmenu", e => e.preventDefault());
    canvas.addEventListener("wheel", e => { e.preventDefault(); this.zoom = Math.min(40, Math.max(0.05, this.zoom * Math.exp(-e.deltaY * 0.0015))); this.dirty = true; }, { passive: false });
    canvas.addEventListener("dblclick", () => this.resetView());
    new ResizeObserver(() => this.resize()).observe(canvas);
    const loop = () => { if (this.dirty) { this.dirty = false; this.draw(); } requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }

  // ------------------------------------------------------------------ molecules
  get topMol() { return this.mols.find(m => m.id === this.top) || null; }
  mol(id) { return this.mols.find(m => m.id === id) || null; }

  addMolecule(name, data, trajectory) {
    const m = { id: this.nextId++, name, data, traj: trajectory || null, xyz: Float32Array.from(data.xyz), frame: 0, frames: new Map([[0, null]]), drawn: true, reps: [], defaults: { style: "Lines", color: "Name", sel: "all" } };
    m.frames.set(0, m.xyz);
    this.mols.push(m); this.top = m.id;
    this.prepare(m); this.defaultReps(m); this.fit(); this.changed();
    return m;
  }
  replaceData(m, data, trajectory) {                    // a trajectory was added: the same molecule with its frames
    m.data = data; m.traj = trajectory; m.xyz = Float32Array.from(data.xyz); m.frame = 0; m.frames = new Map([[0, m.xyz]]); this.prepare(m);
    for (const r of m.reps) this.recompute(m, r); this.changed();
  }
  removeMolecule(id) {
    this.mols = this.mols.filter(m => m.id !== id);
    if (this.top === id) this.top = this.mols.length ? this.mols[this.mols.length - 1].id : null;
    this.fit(); this.changed();
  }
  setTop(id) { if (this.mol(id)) { this.top = id; this.changed(); } }
  setDrawn(id, on) { const m = this.mol(id); if (m) { m.drawn = on; this.changed(); } }

  prepare(m) {
    const d = m.data, n = d.n_atoms;
    m.group = new Uint8Array(n);
    for (let i = 0; i < n; i++) m.group[i] = d.is_water[i] ? 2 : (d.is_protein[i] || d.is_nucleic[i]) ? 0 : 1;
    let lo = 1e9, hi = -1e9;
    for (let i = 0; i < n; i++) if (m.group[i] === 0) { lo = Math.min(lo, d.resid[i]); hi = Math.max(hi, d.resid[i]); }
    if (lo >= hi) { lo = Math.min(...d.resid); hi = Math.max(...d.resid); }
    m.ridMin = lo; m.ridMax = Math.max(hi, lo + 1);
    m.hasProtein = m.group.some(g => g === 0);
  }
  defaultReps(m) {                                      // what a person wants to see first: the polymer as a trace, everything else as sticks, water hidden
    const hasOther = m.group.some(g => g === 1), hasWater = m.group.some(g => g === 2);
    if (m.hasProtein) this.addRep(m, { sel: "protein", style: "Trace", color: "Name" }, true);
    if (hasOther || !m.hasProtein) this.addRep(m, { sel: m.hasProtein ? "not protein and not water" : "not water", style: m.hasProtein ? "Licorice" : "Lines", color: "Name" }, true);
    if (hasWater) this.addRep(m, { sel: "water", style: "Points", color: "Name", shown: false }, true);
    if (!m.reps.length) this.addRep(m, { sel: "all", style: "Lines", color: "Name" }, true);
  }
  addRep(m, spec, quiet) {
    const r = { sel: spec.sel || m.defaults.sel, style: spec.style || m.defaults.style, color: spec.color || m.defaults.color, colorId: spec.colorId === undefined ? 10 : spec.colorId, shown: spec.shown !== false, mask: null, error: null };
    m.reps.push(r); this.recompute(m, r); if (!quiet) this.changed(); return r;
  }
  deleteRep(m, i) { if (m.reps[i]) { m.reps.splice(i, 1); this.changed(); } }
  recompute(m, r) {
    try { r.mask = VASelection.compile(r.sel, m.data, m.xyz); r.error = null; r.count = r.mask.reduce((a, b) => a + b, 0); }
    catch (e) { r.error = e.message; r.mask = new Uint8Array(m.data.n_atoms); r.count = 0; }
    this.dirty = true;
  }
  setRep(m, i, props) {
    const r = m.reps[i]; if (!r) return;
    Object.assign(r, props);
    if ("sel" in props) this.recompute(m, r);
    this.changed();
  }
  setFrame(m, i, xyz) {
    m.frame = i; m.xyz = Float32Array.from(xyz); m.frames.set(i, m.xyz);
    for (const r of m.reps) if (/\bwithin\b/i.test(r.sel)) this.recompute(m, r);                 // a selection that depends on where atoms are
    this.dirty = true; if (this.onchange) this.onchange("frame");
  }
  get nFrames() { const m = this.topMol; return m ? m.data.frames : 0; }

  changed() { this.dirty = true; if (this.onchange) this.onchange("molecules"); }
  set(key, value) { this.settings[key] = value; this.dirty = true; if (this.onchange) this.onchange("settings"); }

  // ------------------------------------------------------------------ the view
  resize() { const r = this.cv.getBoundingClientRect(), d = window.devicePixelRatio || 1; this.cv.width = Math.max(1, Math.round(r.width * d)); this.cv.height = Math.max(1, Math.round(r.height * d)); this.d = d; this.dirty = true; }
  rotate(ax, ay) {
    const cx = Math.cos(ax), sx = Math.sin(ax), cy = Math.cos(ay), sy = Math.sin(ay);
    this.R = mul([1, 0, 0, 0, cx, -sx, 0, sx, cx], mul([cy, 0, sy, 0, 1, 0, -sy, 0, cy], this.R));
  }
  rotateAbout(axis, degrees) {                          // `rotate x by 30`, as VMD's console does: about the screen's axis
    const a = degrees * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    const M = axis === "x" ? [1, 0, 0, 0, c, -s, 0, s, c] : axis === "y" ? [c, 0, s, 0, 1, 0, -s, 0, c] : [c, -s, 0, s, c, 0, 0, 0, 1];
    this.R = mul(M, this.R); this.dirty = true;
  }
  resetView() { this.R = IDENTITY.slice(); this.zoom = 1; this.pan = [0, 0]; this.dirty = true; }
  fit() {                                               // centre and size of everything that is drawn
    const ms = this.mols.filter(m => m.drawn); if (!ms.length) return;
    const c = [0, 0, 0]; let n = 0;
    for (const m of ms) { c[0] += m.data.centre[0]; c[1] += m.data.centre[1]; c[2] += m.data.centre[2]; n++; }
    this.centre = c.map(v => v / n);
    this.radius = Math.max(5, ...ms.map(m => Math.hypot(m.data.centre[0] - this.centre[0], m.data.centre[1] - this.centre[1], m.data.centre[2] - this.centre[2]) + m.data.radius));
    this.dirty = true;
  }

  // ------------------------------------------------------------------ colours
  atomColor(m, r, i) {
    const d = m.data;
    switch (r.color) {
      case "Chain": return hex(VMD_IDS[(d.chain[i] * 3 + 1) % VMD_IDS.length][1]);
      case "ResType": return hex(RESTYPE_COLOR[d.restype[i]] || "#9aa0aa");
      case "Index": return rainbow(i / Math.max(1, d.n_atoms - 1));
      case "Resid": return rainbow((d.resid[i] - m.ridMin) / (m.ridMax - m.ridMin));
      case "ColorID": return hex(VMD_IDS[r.colorId % VMD_IDS.length][1]);
      default: return hex(ELEMENT_COLOR[d.elements[d.element[i]]] || "#c9ced6");
    }
  }

  // ------------------------------------------------------------------ drawing
  project(m) {
    const d = m.data, n = d.n_atoms, R = this.R, c = this.centre, w = this.cv.width, h = this.cv.height, dpr = this.d || 1, xyz = m.xyz;
    const px = new Float32Array(n), py = new Float32Array(n), pz = new Float32Array(n), ps = new Float32Array(n);
    const dist = this.radius * 3.2, base = Math.min(w, h) / (2.2 * this.radius) * this.zoom, ox = w / 2 + this.pan[0] * dpr, oy = h / 2 + this.pan[1] * dpr, persp = this.settings.projection === "Perspective";
    for (let i = 0; i < n; i++) {
      const x = xyz[3 * i] - c[0], y = xyz[3 * i + 1] - c[1], z = xyz[3 * i + 2] - c[2];
      const X = R[0] * x + R[1] * y + R[2] * z, Y = R[3] * x + R[4] * y + R[5] * z, Z = R[6] * x + R[7] * y + R[8] * z, f = persp ? dist / (dist - Z) : 1;
      px[i] = ox + X * base * f; py[i] = oy - Y * base * f; pz[i] = Z; ps[i] = base * f;
    }
    return { px, py, pz, ps, base };
  }

  draw() {
    const ctx = this.ctx, w = this.cv.width, h = this.cv.height, bg = hex(BACKGROUNDS[this.settings.background]);
    ctx.fillStyle = BACKGROUNDS[this.settings.background]; ctx.fillRect(0, 0, w, h);
    this.projected.clear();
    for (const m of this.mols) {
      if (!m.drawn) continue;
      const P = this.project(m); this.projected.set(m.id, P);
      for (const r of m.reps) if (r.shown && r.mask && r.count) this.drawRep(m, r, P, bg);
    }
    if (this.settings.axes !== "Off") this.drawAxes(bg);
    if (this.picked) this.drawPick(bg);
  }

  depth(P, i, bg) {                                    // depth cueing: farther is closer to the background colour
    if (!this.settings.depthcue) return 1;
    const r = this.radius; return 0.35 + 0.65 * Math.min(1, Math.max(0, (P.pz[i] + r) / (2 * r)));
  }

  drawRep(m, r, P, bg) {
    const d = m.data, mask = r.mask, n = d.n_atoms, ctx = this.ctx, dpr = this.d || 1;
    const col = new Array(n);
    for (let i = 0; i < n; i++) if (mask[i]) col[i] = this.atomColor(m, r, i);
    const sh = (i, k) => mix(col[i], bg, this.depth(P, i, bg) * k);
    if (r.style === "VDW" && r.count <= 9000) return this.spheres(m, mask, col, P, bg, 0.62);
    if (r.style === "CPK" && r.count <= 9000) { this.sticks(m, mask, col, P, bg, 1.3 * dpr); return this.spheres(m, mask, col, P, bg, 0.26); }
    if (r.style === "Points" || r.style === "VDW" || r.style === "CPK") { const s = Math.max(1.5, dpr * 2); for (let i = 0; i < n; i++) if (mask[i]) { ctx.fillStyle = sh(i, 1); ctx.fillRect(P.px[i] - s / 2, P.py[i] - s / 2, s, s); } return; }
    if (r.style === "Trace" || r.style === "Tube") return this.trace(m, mask, col, P, bg, r.style === "Tube" ? 5.5 * dpr : 2.6 * dpr, r.style === "Tube");
    this.sticks(m, mask, col, P, bg, (r.style === "Licorice" ? 3.6 : 1.4) * dpr);
    if (r.style === "Lines") {                          // atoms without bonds (ions) would vanish: draw them as small crosses
      const bonded = m.bonded || (m.bonded = (() => { const b = new Uint8Array(n); for (const [a, c] of d.bonds) { b[a] = 1; b[c] = 1; } return b; })());
      ctx.lineWidth = dpr; for (let i = 0; i < n; i++) if (mask[i] && !bonded[i]) { ctx.strokeStyle = sh(i, 1); const x = P.px[i], y = P.py[i], k = 3 * dpr; ctx.beginPath(); ctx.moveTo(x - k, y); ctx.lineTo(x + k, y); ctx.moveTo(x, y - k); ctx.lineTo(x, y + k); ctx.stroke(); }
    }
  }

  sticks(m, mask, col, P, bg, width) {
    const ctx = this.ctx, buckets = new Map();
    for (const [a, b] of m.data.bonds) {
      if (!mask[a] || !mask[b]) continue;
      const mx = (P.px[a] + P.px[b]) / 2, my = (P.py[a] + P.py[b]) / 2, k = Math.round(this.depth(P, a, bg) * 4);
      for (const [i, x, y] of [[a, P.px[a], P.py[a]], [b, P.px[b], P.py[b]]]) {
        const key = col[i].join(",") + "|" + k; let s = buckets.get(key); if (!s) buckets.set(key, s = { c: col[i], k, seg: [] });
        s.seg.push(x, y, mx, my);
      }
    }
    ctx.lineWidth = width; ctx.lineCap = "round";
    for (const s of buckets.values()) { ctx.strokeStyle = mix(s.c, bg, s.k / 4); ctx.beginPath(); for (let i = 0; i < s.seg.length; i += 4) { ctx.moveTo(s.seg[i], s.seg[i + 1]); ctx.lineTo(s.seg[i + 2], s.seg[i + 3]); } ctx.stroke(); }
  }

  trace(m, mask, col, P, bg, width, tube) {
    const ctx = this.ctx, d = m.data, xyz = m.xyz; let prev = -1;
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    for (let i = 0; i < d.n_atoms; i++) {
      if (!mask[i] || !d.is_ca[i]) continue;
      if (prev >= 0 && d.chain[prev] === d.chain[i]) {
        const dx = xyz[3 * i] - xyz[3 * prev], dy = xyz[3 * i + 1] - xyz[3 * prev + 1], dz = xyz[3 * i + 2] - xyz[3 * prev + 2];
        if (dx * dx + dy * dy + dz * dz < 20.25) {         // 4.5 A: consecutive residues, not a gap
          const wscale = Math.min(1.6, Math.max(0.6, P.ps[i] / P.base)), g = ctx.createLinearGradient(P.px[prev], P.py[prev], P.px[i], P.py[i]);
          g.addColorStop(0, mix(col[prev], bg, this.depth(P, prev, bg))); g.addColorStop(1, mix(col[i], bg, this.depth(P, i, bg)));
          if (tube) { ctx.strokeStyle = mix([0, 0, 0], bg, 0.35); ctx.lineWidth = width * wscale + 2; ctx.beginPath(); ctx.moveTo(P.px[prev], P.py[prev]); ctx.lineTo(P.px[i], P.py[i]); ctx.stroke(); }
          ctx.strokeStyle = g; ctx.lineWidth = width * wscale; ctx.beginPath(); ctx.moveTo(P.px[prev], P.py[prev]); ctx.lineTo(P.px[i], P.py[i]); ctx.stroke();
        }
      }
      prev = i;
    }
  }

  spheres(m, mask, col, P, bg, scale) {
    const ctx = this.ctx, d = m.data, order = [];
    for (let i = 0; i < d.n_atoms; i++) if (mask[i]) order.push(i);
    order.sort((a, b) => P.pz[a] - P.pz[b]);
    for (const i of order) {
      const rad = (RADIUS[d.elements[d.element[i]]] || 1.7) * P.ps[i] * scale, x = P.px[i], y = P.py[i], k = this.depth(P, i, bg);
      ctx.fillStyle = mix(col[i], bg, k * 0.85); ctx.beginPath(); ctx.arc(x, y, rad, 0, 6.2832); ctx.fill();
      ctx.fillStyle = mix(col[i].map(v => Math.min(255, v * 1.5 + 40)), bg, k * 0.9); ctx.beginPath(); ctx.arc(x - rad * 0.32, y - rad * 0.32, rad * 0.38, 0, 6.2832); ctx.fill();
    }
  }

  drawAxes(bg) {                                        // VMD's axes, lower left: x red, y green, z blue
    const ctx = this.ctx, dpr = this.d || 1, o = [46 * dpr, this.cv.height - 46 * dpr], L = 24 * dpr, R = this.R, light = (bg[0] + bg[1] + bg[2]) / 3 > 140;
    ctx.lineWidth = 1.6 * dpr; ctx.font = `${11 * dpr}px ui-monospace, Menlo, monospace`; ctx.lineCap = "round";
    [["x", light ? "#d12" : "#ff4a4a", 0], ["y", light ? "#1a8f3c" : "#3fd16a", 1], ["z", light ? "#1c4fd8" : "#4a7bff", 2]].forEach(([label, c, k]) => {
      const ex = R[k] * L, ey = -R[3 + k] * L; ctx.strokeStyle = c; ctx.fillStyle = c; ctx.beginPath(); ctx.moveTo(o[0], o[1]); ctx.lineTo(o[0] + ex, o[1] + ey); ctx.stroke(); ctx.fillText(label, o[0] + ex * 1.2 - 3 * dpr, o[1] + ey * 1.2 + 4 * dpr);
    });
  }

  // ------------------------------------------------------------------ picking
  pick(e) {                                             // the nearest drawn atom to the click, within 12 pixels
    const rect = this.cv.getBoundingClientRect(), dpr = this.d || 1, x = (e.clientX - rect.left) * dpr, y = (e.clientY - rect.top) * dpr;
    let best = null, bd = (12 * dpr) ** 2;
    for (const m of this.mols) {
      const P = this.projected.get(m.id); if (!P || !m.drawn) continue;
      const visible = new Uint8Array(m.data.n_atoms); for (const r of m.reps) if (r.shown && r.mask) for (let i = 0; i < visible.length; i++) if (r.mask[i]) visible[i] = 1;
      for (let i = 0; i < m.data.n_atoms; i++) if (visible[i]) { const dd = (P.px[i] - x) ** 2 + (P.py[i] - y) ** 2; if (dd < bd || (dd === bd && best && P.pz[i] > best.z)) { bd = dd; best = { mol: m, i, z: P.pz[i] }; } }
    }
    this.picked = best; this.dirty = true;
    if (this.onpick) this.onpick(best ? this.describeAtom(best.mol, best.i) : null);
  }
  describeAtom(m, i) {
    const d = m.data;
    return { mol: m.id, molName: m.name, index: i, name: d.names[d.name[i]], resname: d.resnames[d.resname[i]], resid: d.resid[i], chain: d.chains[d.chain[i]], element: d.elements[d.element[i]],
             x: m.xyz[3 * i], y: m.xyz[3 * i + 1], z: m.xyz[3 * i + 2] };
  }
  drawPick(bg) {
    const { mol, i } = this.picked, P = this.projected.get(mol.id); if (!P) return;
    const ctx = this.ctx, dpr = this.d || 1; ctx.strokeStyle = (bg[0] + bg[1] + bg[2]) / 3 > 140 ? "#c00" : "#ffe14a"; ctx.lineWidth = 1.6 * dpr;
    ctx.beginPath(); ctx.arc(P.px[i], P.py[i], 8 * dpr, 0, 6.2832); ctx.stroke();
  }

  png() { return new Promise(res => this.cv.toBlob(res, "image/png")); }
}
