"use strict";
/* The page. Everything the user can do is an action (menus, the command palette, keyboard shortcuts and the console all run the same ones). It is a
 * remote for a real VMD window: commands go to VMD (the window_* tools, through the server) and the picture is a snapshot VMD draws; nothing is drawn
 * here. The server (vmd_agent.ui) also runs the agent, the tools and the whole jobs. No framework, no build step. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const fmt = s => s < 10 ? s.toFixed(2) + " s" : s < 100 ? s.toFixed(1) + " s" : Math.round(s) + " s";
const size = n => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB";
const url = rel => "/files/" + rel.split("/").map(encodeURIComponent).join("/");
const base = p => p.split("/").pop();
const api = (p, body) => fetch(p, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const getJSON = async p => (await api(p)).json();
const store = {
  get(k, d) { try { const v = localStorage.getItem("vmd-agent." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("vmd-agent." + k, JSON.stringify(v)); } catch (e) { /* storage may be blocked */ } },
};
const S = { defaults: { sel: "all", style: "Lines", color: "Name" }, cat: null, everything: [], open: new Set(), selected: null, status: {}, busy: false, figures: [], repIndex: 0, history: [], histAt: 0, anim: { timer: null, dir: 1, fps: 8, style: "loop" } };
let V;

// ------------------------------------------------------------------------------------------------ small things
function toast(msg, kind) {
  const t = el("div", "toast " + (kind || ""), msg); $("#toasts").append(t); setTimeout(() => t.remove(), kind === "err" ? 7000 : 3800);
}
function clog(cls, text) {
  const box = $("#consolelog"), row = el("div"), t = new Date().toTimeString().slice(0, 8);
  row.append(el("span", "t", t + "  "), el("span", cls, text)); box.append(row); box.scrollTop = box.scrollHeight;
  while (box.childNodes.length > 500) box.removeChild(box.firstChild);
}
function totals(c) { if (c) $("#totals").textContent = `session ${fmt(c.wall_s)} · model ${fmt(c.model_s)} (${c.model_calls} calls) · tools ${fmt(c.tool_s)} (${c.tool_calls.length} calls)`; }
function choose(title, items) {                          // a small list dialog: resolves to the chosen value, or null
  return new Promise(resolve => {
    const dlg = $("#chooser"), list = $("#chooser-list"); $("#chooser-title").textContent = title; list.textContent = "";
    if (!items.length) { toast("Nothing to choose from yet.", "err"); return resolve(null); }
    let done = false; const finish = v => { if (!done) { done = true; dlg.close(); resolve(v); } };
    items.forEach(it => { const li = el("li"); li.setAttribute("role", "option"); li.tabIndex = 0; li.append(el("span", "k " + (it.kind || ""), it.tag || ""), el("span", null, it.label)); li.onclick = () => finish(it.value); li.onkeydown = e => { if (e.key === "Enter") finish(it.value); }; list.append(li); });
    dlg.onclose = () => finish(null); dlg.showModal(); list.firstChild.focus();
  });
}

// ------------------------------------------------------------------------------------------------ status
function dot(cls, label, value) { const s = el("span"); s.append(el("span", "dot " + cls), document.createTextNode(label + " "), el("b", null, value)); return s; }
async function loadStatus() {
  const s = S.status = await getJSON("/api/status");
  $("#ver").textContent = "vmd-agent " + s.version; document.title = "vmd-agent " + s.version;
  const left = $("#statusleft"); left.textContent = "";
  left.append(dot(s.model_ready ? "ok" : "bad", "model", s.model), dot(s.vmd ? "ok" : "warn", "VMD", s.vmd ? (s.vmd_version || "found") : "not found"), dot(s.ffmpeg ? "ok" : "warn", "ffmpeg", s.ffmpeg ? "ready" : "missing"));
  $("#folder").textContent = s.data_dir.split(/[\\/]/).slice(-2).join("/"); $("#folder").title = s.data_dir;
  const sel = $("#profile"); sel.textContent = "";
  for (const [k, n] of Object.entries(s.profiles)) sel.append(new Option(n ? `${k} (${n})` : `${k} (fits the question)`, k));
  sel.value = s.profile;
  renderBanner(s);
  $("#about-text").textContent = `Version ${s.version}. Model: ${s.model}. VMD: ${s.vmd ? s.vmd + " (" + (s.vmd_version || "version unknown") + ")" : "not found"}. Files folder: ${s.data_dir}. ${s.n_tools} tools; the chat is offered ${s.tools_in_chat}.`;
  totals(s.clock);
}
function renderBanner(s) {
  const box = $("#banner"); box.textContent = "";
  if (s.model_ready) return;
  const b = el("div", "banner"), why = s.model_state === "no_model" ? `The server answers but has no model called "${s.model}".` : `No model server answers at ${s.server}.`;
  b.append(el("div", null, "The chat has no model to talk to. " + why + " The viewer, the files, the look buttons and the whole jobs work without one."));
  if ((s.local_models || []).length && s.model_state === "no_server") b.append(el("div", null, `${s.local_models.length} models are downloaded on this computer (${s.local_models.join(", ")}): start the local server and pick one.`));
  if ((s.found_servers || []).length) b.append(el("div", null, "A model server does answer at " + s.found_servers.map(f => f.base_url).join(", ") + ": choose it under Choose a model…"));
  const acts = el("div", "acts");
  if (s.model_state === "no_server" && s.private_available) { const x = el("button", "btn small", "Start the local model server"); x.onclick = startLocal; acts.append(x); }
  const m = el("button", "btn small", "Choose a model…"); m.onclick = openModel; const c = el("button", "btn small", "Check again"); c.onclick = loadStatus;
  acts.append(m, c); b.append(acts); box.append(b);
}
async function startLocal() {
  toast("Starting the local model server…", "");
  const r = await (await api("/api/model/start", {})).json();
  toast(r.error || (r.state === "ready" ? "The model server is running." : "The server started but the model is not there yet: choose one."), r.error ? "err" : "ok");
  loadStatus();
}
// the Model dialog: the same choice as in setup (a free local model, or another server)
function fillModel(info) {
  $("#model-state").textContent = info.state === "ready" ? `Using ${info.model} at ${info.base_url}.` : `Not working: ${info.problem}.`;
  const list = $("#model-list"); list.textContent = ""; (info.available || []).forEach(m => list.append(new Option(m, m)));
  const loc = $("#model-local"); loc.textContent = "";
  (info.local_models || []).forEach(m => loc.append(new Option(m, m))); if (!(info.local_models || []).length) loc.append(new Option(info.private_available ? "no model downloaded yet: run vmd-agent setup" : "no private model server yet: run vmd-agent setup", ""));
  if ((info.local_models || []).includes(info.model)) loc.value = info.model;
  const fs = $("#model-found"); fs.textContent = ""; fs.append(new Option((info.found || []).length ? "choose one…" : "none found", ""));
  (info.found || []).forEach(f => fs.append(new Option(`${f.base_url}  (${f.models.length} models)`, f.base_url)));
  fs.onchange = () => { const f = (info.found || []).find(x => x.base_url === fs.value); if (f) { $("#model-url").value = f.base_url; if (f.models.length) $("#model-name").value = f.models[0]; list.textContent = ""; f.models.forEach(m => list.append(new Option(m, m))); } };
  $("#model-start").hidden = !info.private_available;
}
function modelSource() { return $('input[name="msrc"]:checked').value; }
function showModelSource() { const local = modelSource() === "local"; $("#model-other").hidden = local; $("#model-local-box").hidden = !local; }
async function openModel() {
  const info = await getJSON("/api/model"), local = info.is_private || (!info.has_key && /^https?:\/\/(localhost|127\.0\.0\.1)/.test(info.base_url) && info.private_available);
  $$('input[name="msrc"]').forEach(r => { r.checked = r.value === (local ? "local" : "other"); });
  $("#model-url").value = local ? "" : info.base_url; $("#model-key").value = ""; $("#model-name").value = info.model; $("#model-msg").textContent = "";
  fillModel(info); showModelSource(); $("#modeldlg").showModal();
}
$$('input[name="msrc"]').forEach(r => r.onchange = showModelSource);
$("#model-close").onclick = () => $("#modeldlg").close();
$("#model-check").onclick = async () => { fillModel(await getJSON("/api/model")); loadStatus(); };
$("#model-start").onclick = async () => { $("#model-msg").textContent = "Starting…"; const r = await (await api("/api/model/start", {})).json(); $("#model-msg").textContent = r.error || ""; fillModel(r); loadStatus(); };
$("#model-use").onclick = async () => {
  const local = modelSource() === "local", body = { model: local ? $("#model-local").value : $("#model-name").value.trim(), remember: true, local };
  if (local && !body.model) { $("#model-msg").textContent = "No model is downloaded yet: run vmd-agent setup."; return; }
  if (!local) { body.base_url = $("#model-url").value.trim(); if ($("#model-key").value) body.api_key = $("#model-key").value; }
  const r = await api("/api/model/use", body), j = await r.json();
  if (!r.ok) { $("#model-msg").textContent = j.error; return; }
  fillModel(j); $("#model-msg").textContent = j.state === "ready" ? "Saved. New conversation started with this model." : "Saved, but it does not answer yet: " + j.problem + ".";
  $("#log").textContent = ""; $("#welcome").classList.remove("gone"); loadStatus();
};
$("#profile").onchange = async e => {
  const r = await api("/api/profile", { tools: e.target.value });
  if (r.ok) { $("#log").textContent = ""; $("#welcome").classList.remove("gone"); clog("job", `the chat now offers the "${e.target.value}" tools`); loadStatus(); } else { toast((await r.json()).error, "err"); loadStatus(); }
};

// ------------------------------------------------------------------------------------------------ files
const KIND = { structure: "PDB", trajectory: "TRJ", image: "IMG", video: "MP4", map: "MAP", report: "DOC", data: "JSON", script: "TCL", other: "—" };
async function fill(box, dir, depth) {
  const r = await getJSON("/api/files" + (dir ? "?dir=" + encodeURIComponent(dir) : ""));
  if (!dir) S.everything = r.everything || [];
  for (const d of r.folders) {
    const row = el("div", "mol folder"); row.classList.add("d" + Math.min(depth, 5)); row.setAttribute("role", "treeitem"); row.setAttribute("aria-expanded", S.open.has(d.path)); row.tabIndex = 0;
    row.append(el("span", "k", S.open.has(d.path) ? "−" : "+"), el("span", "nm", base(d.path) + "/"), el("span", "meta", d.n_files + " files"));
    const toggle = () => { S.open.has(d.path) ? S.open.delete(d.path) : S.open.add(d.path); loadFiles(); };
    row.onclick = toggle; row.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
    const inner = el("div"); box.append(row, inner);
    if (S.open.has(d.path)) await fill(inner, d.path, depth + 1);
  }
  for (const f of r.files) {
    const row = el("div", "mol" + (f.path === S.selected ? " sel" : "")); row.classList.add("d" + Math.min(depth, 5)); row.setAttribute("role", "treeitem"); row.tabIndex = 0;
    row.append(el("span", "k " + f.kind, KIND[f.kind] || "—"), el("span", "nm", base(f.path)), el("span", "meta", size(f.size)));
    row.title = f.path + "  (double-click or press Enter to draw)";
    row.onclick = () => select(f); row.ondblclick = () => openFile(f); row.onkeydown = e => { if (e.key === "Enter") openFile(f); };
    box.append(row);
  }
  return r;
}
async function loadFiles() {
  const fresh = el("div"), r = await fill(fresh, "", 0), box = $("#files"); box.textContent = ""; box.append(fresh);
  if (!r.files.length && !r.folders.length) box.append(el("p", "empty", "No files yet. Drop a structure (.pdb) and a trajectory (.dcd) here, or put them in this folder on your computer."));
  if ($("#wfname")) renderSlots();
}
function select(f) {
  S.selected = f.path; loadFiles();
  const box = $("#info"); box.hidden = false; box.textContent = ""; box.append(el("h3", null, f.path));
  const dl = el("dl"); [["kind", f.kind], ["size", size(f.size)]].forEach(([k, v]) => dl.append(el("dt", null, k), el("dd", null, v))); box.append(dl);
  const row = el("div", "row"), out = el("div"), add = (label, fn) => { const b = el("button", "btn small", label); b.onclick = fn; row.append(b); };
  if (["structure", "trajectory", "image", "video"].includes(f.kind)) add(f.kind === "structure" ? "Draw as new molecule" : f.kind === "trajectory" ? "Load into top molecule" : "Show", () => openFile(f));
  const looks = f.kind === "structure" || f.kind === "trajectory" ? ["inspect_files", "detect_system", "structure_stats"] : f.kind === "video" ? ["probe_video"] : [];
  for (const t of looks) add(t.replace(/_/g, " "), () => look(t, f.path, out));
  if (f.kind === "structure" || f.kind === "trajectory") add("Ask about it", () => { $("#q").value = "What is in " + f.path + "?"; showTab("chat"); $("#q").focus(); });
  box.append(row, out);
}
async function look(tool, path, out) {
  clog("cmd", `look ${tool} ${path}`); if (out) out.textContent = "…";
  const r = await (await api("/api/look", { tool, path })).json(), err = r.result && r.result.error;
  clog(err ? "err" : "ok", `${err ? "✗" : "✓"} ${tool}  ${fmt(r.seconds || 0)}${err ? "  " + String(err).slice(0, 140) : ""}`);
  if (out) { out.textContent = ""; out.append(el("pre", "look", JSON.stringify(r.result || r, null, 1).slice(0, 5000))); } else clog("t", JSON.stringify(r.result || r).slice(0, 900));
}
function openFile(f) {
  if (f.kind === "image" || f.kind === "video") return media(f.path, f.kind);
  if (f.kind === "structure") return loadMolecule(f.path);
  if (f.kind === "trajectory") return addTrajectory(f.path);
  toast("This kind of file has no picture; use the look buttons.", "");
}

// ------------------------------------------------------------------------------------------------ the VMD window
// The state of the VMD window as the server last read it, and snapshots of it. Every change is a command to VMD (a window_* tool); the page then reads VMD's state back.
const BG = { black: "#000000", white: "#ffffff", gray: "#808080", silver: "#c0c0c0", blue: "#3333ff", red: "#ff0000", orange: "#ff7f00", yellow: "#ffff00", tan: "#d2b48c", green: "#00ff00", cyan: "#00ffff", purple: "#a020f0", pink: "#ffc0cb", lime: "#80ff00", mauve: "#c08080", ochre: "#a06000", iceblue: "#99ccff" };
class Live {
  constructor(img) {
    this.img = img; this.mols = []; this.top = null; this.connected = false; this.installed = true; this.headless = false; this.version = "";
    this.settings = { projection: "Perspective", depthcue: false, axes: "LowerLeft", background: "black", shadows: false, mouse: "rotate" };
    this.choices = null; this.onchange = () => {}; this.snapping = false; this.again = false; this.lastError = "";
  }
  get topMol() { return this.mols.find(m => m.id === this.top) || null; }
  mol(id) { return this.mols.find(m => m.id === id) || null; }
  rel(p) { const d = (S.status.data_dir || "").replace(/\\/g, "/"); p = (p || "").replace(/\\/g, "/"); return d && p.startsWith(d + "/") ? p.slice(d.length + 1) : p; }
  apply(st) {
    this.installed = !!st.installed; this.connected = !!st.connected; this.headless = !!st.headless; this.version = st.vmd || "";
    if (st.choices) this.choices = st.choices;
    this.mols = (st.molecules || []).map(m => ({ id: m.id, name: m.name, drawn: m.shown, frame: m.frame, path: this.rel(m.file), data: { n_atoms: m.natoms, frames: m.nframes },
      reps: (m.reps || []).map(r => ({ sel: r.selection, style: String(r.style).split(" ")[0], color: r.color, material: r.material, shown: r.shown })) }));
    this.top = this.connected ? st.top : null;
    const d = st.display || {}; Object.assign(this.settings, { projection: d.projection || "Perspective", depthcue: !!d.depthcue, axes: d.axes || "LowerLeft", background: d.background || "black", shadows: d.shadows === "on" });
    $("#display").style.background = BG[this.settings.background] || "#000";           // the picture's own background, so no bars show around it
    this.onchange("state");
  }
  async tool(name, args) {
    const r = await api("/api/window", { tool: name, args: args || {} }), j = await r.json();
    if (!j.ok) { const e = new Error(j.error || "VMD refused the command"); throw e; }
    return j;
  }
  async refresh(snap) { const st = await getJSON("/api/window"); this.apply(st); if (snap) await this.snapshot(); return st; }
  async snapshot(quality) {                                // VMD's own picture of its window (the next one is taken when this one is done)
    if (!this.connected) return;
    if (this.snapping) { this.again = true; return; }
    this.snapping = true;
    try {                                                // the picture is a same-origin image the server asks VMD to draw
      await new Promise(done => { this.img.onload = () => { this.img.hidden = false; done(); }; this.img.onerror = () => { this.img.hidden = true; done(); }; this.img.src = "/api/window/snapshot?q=" + (quality || "fast") + "&t=" + Date.now(); });
      this.onchange("picture");
    } catch (e) { /* the window may have been closed: the next state read says so */ }
    finally { this.snapping = false; if (this.again) { this.again = false; this.snapshot(quality); } }
  }
}
async function win(name, args, quiet) {                  // one command to the VMD window; a refusal is a message, never an exception
  try { V.lastError = ""; return await V.tool(name, args); }
  catch (e) { V.lastError = e.message; if (!quiet) { clog("err", "✗ " + e.message); toast(e.message, "err"); } return null; }
}
const after = async (snap = true) => { await V.refresh(snap); };
async function openVMD() {
  toast("Opening VMD…", ""); clog("cmd", "window_open"); const b = $("#open-vmd"); if (b) b.disabled = true;
  const r = await api("/api/window/open", {}), j = await r.json();
  if (!r.ok) { clog("err", "✗ " + j.error); toast(j.error, "err"); } else clog("ok", `✓ VMD ${j.vmd} is open${j.headless ? " (no window)" : ""}`);
  V.apply(j); await V.snapshot(); loadStatus();
}
async function ensureWindow() {
  if (V.connected) return true;
  if (!V.installed) { toast("VMD was not found on this computer: install VMD, then run vmd-agent setup.", "err"); return false; }
  await openVMD(); return V.connected;
}

// ------------------------------------------------------------------------------------------------ molecules
const stem = p => p.replace(/\.[^./]+$/, "");
function partnerStructure(path) {
  const s = S.everything.filter(x => x.kind === "structure");
  return s.find(x => stem(x.path) === stem(path)) || (V.topMol && s.find(x => x.path === V.topMol.path)) || (s.length === 1 ? s[0] : null);
}
function partnerTrajectory(path) { const t = S.everything.find(x => x.kind === "trajectory" && stem(x.path) === stem(path)); return t ? t.path : null; }
async function loadMolecule(path, traj) {
  if (!(await ensureWindow())) return null;
  traj = traj || partnerTrajectory(path); clog("cmd", `window_load ${path}${traj ? " " + traj : ""}`);
  const j = await win("window_load", { topology: path, trajectory: traj || undefined });
  if (j) { clog("ok", "✓ " + j.summary); await after(); } return j;
}
async function addTrajectory(path, id) {
  if (!V.mols.length) { const s = partnerStructure(path); if (!s) { toast("Load a structure first (double-click a .pdb or .psf).", "err"); return; } return loadMolecule(s.path, path); }
  if (!(await ensureWindow())) return;
  clog("cmd", `window_load ${path} (molecule ${id == null ? V.top : id})`);
  const j = await win("window_load", { trajectory: path, molecule: id == null ? undefined : id }); if (j) { clog("ok", "✓ " + j.summary); await after(); }
}
async function moleculeAction(action, id) { const j = await win("window_molecules", { action, molecule: id }); if (j) await after(); return j; }
function renderMolecules() {
  const tb = $("#mols tbody"); tb.textContent = ""; $("#mols-empty").hidden = V.mols.length > 0; $("#mols").hidden = V.mols.length === 0;
  for (const m of V.mols) {
    const tr = el("tr", m.id === V.top ? "sel" : ""); tr.title = m.path || m.name;
    const tog = (on, label, fn) => { const b = el("button", "toggle " + (on ? "on" : "off"), on ? "✓" : ""); b.setAttribute("aria-pressed", on); b.setAttribute("aria-label", label); b.onclick = e => { e.stopPropagation(); fn(); }; return b; };
    const c = (...n) => { const td = el("td"); td.append(...n); return td; };
    const nameTd = c(m.name), nTd = c(String(m.data.n_atoms)), fTd = c(String(m.data.frames)); nameTd.className = "name"; nTd.className = "num"; fTd.className = "num";
    tr.append(c(String(m.id)), c(tog(m.id === V.top, "Make molecule " + m.id + " the top molecule", () => moleculeAction("top", m.id))), c(tog(m.drawn, (m.drawn ? "Hide" : "Show") + " molecule " + m.id, () => moleculeAction(m.drawn ? "hide" : "show", m.id))), nameTd, nTd, fTd);
    tr.onclick = () => moleculeAction("top", m.id); tb.append(tr);
  }
}

// ------------------------------------------------------------------------------------------------ display
function media(rel, kind) {
  const m = $("#media"); m.textContent = ""; m.classList.add("on");
  const node = el(kind === "video" ? "video" : "img"); node.src = url(rel); if (kind === "video") node.controls = true; node.alt = rel;
  const back = el("button", "btn small back", "Back to the VMD window"); back.onclick = () => { m.classList.remove("on"); updateCaption(); };
  m.append(node, back); $("#caption").textContent = rel;
}
function updateCaption() {
  const nd = $("#nodata"), m = V.topMol, msg = $("#nodata-msg"), btn = $("#open-vmd");
  btn.hidden = true;
  if (!V.installed) { nd.hidden = false; msg.textContent = "VMD was not found on this computer. Install VMD (free from UIUC), then run vmd-agent setup. The tools still draw built-in pictures without it."; }
  else if (!V.connected) { nd.hidden = false; msg.textContent = "No VMD window is open. This display shows snapshots of a real VMD window, which you control from here and from the chat."; btn.hidden = false; btn.disabled = false; $("#view").hidden = true; }
  else if (!V.mols.length) { nd.hidden = false; msg.textContent = "VMD is open and empty. Double-click a structure in Files, or type  mol new FILE  in the console."; }
  else nd.hidden = true;
  $("#caption").textContent = V.connected ? `VMD ${V.version}${V.headless ? " (no window)" : ""}${m ? ` · ${m.name} · ${m.data.n_atoms} atoms · frame ${m.frame} of ${m.data.frames}` : ""}` : "";
}
const MOUSE = { rotate: "Rotate", translate: "Move", scale: "Zoom" };
function setMouse(mode) {
  V.settings.mouse = mode; $$("#mousemodes button").forEach(b => b.setAttribute("aria-checked", b.dataset.mode === mode));
  $("#mousestat").textContent = "Mouse: " + MOUSE[mode]; store.set("mouse", mode);
}
$$("#mousemodes button").forEach(b => { b.onclick = () => setMouse(b.dataset.mode); });
(function mouseOnTheSnapshot() {                         // dragging the picture moves the real VMD view, then a fresh snapshot is taken
  const img = $("#view"); let drag = null, acc = null, timer = null;
  const send = async () => {
    timer = null; const a = acc; acc = null; if (!a || !V.connected) return;
    if (a.mode === "rotate") { if (a.dx) await win("window_view", { action: "rotate", axis: "y", degrees: a.dx * 0.5 }, true); if (a.dy) await win("window_view", { action: "rotate", axis: "x", degrees: a.dy * 0.5 }, true); }
    else if (a.mode === "translate") await win("window_view", { action: "translate", x: a.dx / (img.clientWidth || 1) * 2, y: -a.dy / (img.clientHeight || 1) * 2, z: 0 }, true);
    else if (a.mode === "scale") await win("window_view", { action: "scale", factor: Math.exp(-a.dy * 0.01) }, true);
    V.snapshot();
  };
  const push = (mode, dx, dy) => { acc = acc && acc.mode === mode ? { mode, dx: acc.dx + dx, dy: acc.dy + dy } : { mode, dx, dy }; if (!timer) timer = setTimeout(send, 70); };
  img.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, mode: e.shiftKey ? "translate" : V.settings.mouse }; img.setPointerCapture(e.pointerId); });
  img.addEventListener("pointermove", e => { if (!drag) return; push(drag.mode, e.clientX - drag.x, e.clientY - drag.y); drag.x = e.clientX; drag.y = e.clientY; });
  const end = () => { drag = null; }; img.addEventListener("pointerup", end); img.addEventListener("pointercancel", end);
  img.addEventListener("wheel", e => { e.preventDefault(); push("scale", 0, e.deltaY * 0.4); }, { passive: false });
  img.addEventListener("dblclick", async () => { await win("window_view", { action: "reset" }, true); V.snapshot(); });
})();
$("#open-vmd").onclick = openVMD;
$("#snap-now").onclick = () => after(true);
async function setDisplay(setting, value) { if (!(await ensureWindow())) return; if (await win("window_display", { setting, value })) await after(); }

// animation (VMD's Animate): the top molecule's frames, stepped or played inside the VMD window
function animState() { const m = V.topMol, n = m ? m.data.frames : 0; return { m, n }; }
function refreshAnim() {
  const { m, n } = animState(), bar = $("#anim"); bar.classList.toggle("off", !(m && n > 1));
  if (document.activeElement !== $("#slider")) $("#slider").value = m ? m.frame : 0;
  $("#slider").max = Math.max(0, n - 1); $("#frame-n").max = Math.max(0, n - 1); if (document.activeElement !== $("#frame-n")) $("#frame-n").value = m ? m.frame : 0; $("#flabel").textContent = "of " + Math.max(1, n);
}
async function gotoFrame(i) {
  const { m, n } = animState(); if (!m || n < 1) return;
  i = Math.max(0, Math.min(n - 1, Math.round(i))); if (await win("window_animate", { action: "goto", frame: i })) await after();
}
function setPlayIcon(playing) { $("#anim-play use").setAttribute("href", playing ? "#i-pause" : "#i-play"); $("#anim-play").setAttribute("aria-label", playing ? "Pause" : "Play"); }
async function stopAnim() {
  const was = !!S.anim.timer; if (S.anim.timer) { clearInterval(S.anim.timer); S.anim.timer = null; }
  setPlayIcon(false); if (was) { await win("window_animate", { action: "pause" }, true); await after(); }
}
async function playAnim(dir) {
  await stopAnim(); const { m, n } = animState(); if (!m || n < 2) return;
  await win("window_animate", { action: "style", style: S.anim.style }, true); await win("window_animate", { action: "speed", speed: Math.min(1, S.anim.fps / 30) }, true);
  if (!(await win("window_animate", { action: dir > 0 ? "forward" : "reverse" }))) return;
  setPlayIcon(true); let still = 0, last = m.frame;
  S.anim.timer = setInterval(async () => {                // the window plays by itself; the page keeps showing it
    await V.refresh(true); const f = V.topMol ? V.topMol.frame : last;
    still = f === last ? still + 1 : 0; last = f; if (still >= 4 && S.anim.style === "once") stopAnim();
  }, 600);
}
$$("#anim [data-a]").forEach(b => b.onclick = async () => {
  const { m, n } = animState(); if (!m) return; const a = b.dataset.a;
  if (a === "play") return S.anim.timer ? stopAnim() : playAnim(1);
  if (a === "reverse") return playAnim(-1);
  await stopAnim(); await gotoFrame(a === "first" ? 0 : a === "last" ? n - 1 : m.frame + (a === "next" ? 1 : -1));
});
let slideTimer = null;
$("#slider").oninput = e => { const v = Number(e.target.value); $("#frame-n").value = v; clearTimeout(slideTimer); slideTimer = setTimeout(async () => { await stopAnim(); gotoFrame(v); }, 120); };
$("#frame-n").onchange = async e => { await stopAnim(); gotoFrame(Number(e.target.value)); };
$("#speed").oninput = e => { S.anim.fps = Number(e.target.value); $("#speed-n").textContent = S.anim.fps + "/s"; store.set("speed", S.anim.fps); if (S.anim.timer) win("window_animate", { action: "speed", speed: Math.min(1, S.anim.fps / 30) }, true); };
$("#style").onchange = e => { S.anim.style = e.target.value; if (V.connected && V.topMol) win("window_animate", { action: "style", style: S.anim.style }, true); };

// gallery of pictures the tools made
function addFigure(rel) { if (S.figures.includes(rel)) return; S.figures.push(rel); const i = el("img"); i.src = url(rel); i.alt = rel; i.title = rel; i.onclick = () => media(rel, "image"); $("#gallery").append(i); }
function figs(paths) { const d = el("div", "figs"); for (const p of paths || []) { const i = el("img"); i.src = url(p); i.alt = p; i.title = p; i.onclick = () => media(p, "image"); d.append(i); addFigure(p); } return d; }

// ------------------------------------------------------------------------------------------------ representations (VMD's Graphics, Representations)
const PRESETS = ["all", "protein", "backbone", "sidechain", "not protein and not water", "water", "nucleic", "hydrogen"];
const COLOR_IDS = ["blue", "red", "gray", "orange", "yellow", "tan", "silver", "green", "white", "pink", "cyan", "purple", "lime", "mauve", "ochre", "iceblue", "black"];
let repOptionsFilled = false;
function fillRepOptions() {
  if (repOptionsFilled || !V.choices) return; repOptionsFilled = true;
  const st = $("#rep-style"), co = $("#rep-color"), ma = $("#rep-material"), id = $("#rep-colorid"), pre = $("#rep-presets");
  V.choices.styles.forEach(s => st.append(new Option(s, s))); ["ColorID", ...V.choices.colors].forEach(c => co.append(new Option(c, c))); V.choices.materials.forEach(x => ma.append(new Option(x, x)));
  COLOR_IDS.forEach((n, i) => id.append(new Option(`${i} ${n}`, i)));
  PRESETS.forEach(p => { const b = el("button", null, p); b.type = "button"; b.onclick = () => { $("#rep-sel").value = p; commitRep(); }; pre.append(b); });
}
function repMol() { return V.mol(Number($("#rep-mol").value)) || V.topMol; }
function svgIcon(name) {
  const ns = "http://www.w3.org/2000/svg", s = document.createElementNS(ns, "svg"), u = document.createElementNS(ns, "use"); s.setAttribute("class", "ic"); u.setAttribute("href", "#" + name); s.append(u); return s;
}
const colorOf = r => (/^ColorID (\d+)$/.test(r.color) ? { method: "ColorID", id: Number(r.color.split(" ")[1]) } : { method: r.color, id: 0 });
function renderReps() {
  fillRepOptions();
  const msel = $("#rep-mol"), keep = msel.value; msel.textContent = "";
  V.mols.forEach(m => msel.append(new Option(`${m.id}: ${m.name}`, m.id))); msel.value = keep !== "" && V.mol(Number(keep)) ? keep : (V.top != null ? V.top : "");
  const m = repMol(), list = $("#replist"); list.textContent = "";
  if (!m) { list.append(el("p", "empty", V.connected ? "No molecule is loaded in VMD." : "No VMD window is open.")); $("#repform").hidden = true; return; }
  $("#repform").hidden = false; S.repIndex = Math.min(S.repIndex, Math.max(0, m.reps.length - 1));
  m.reps.forEach((r, i) => {
    const row = el("div", "rep" + (i === S.repIndex ? " sel" : "")); row.setAttribute("role", "option"); row.setAttribute("aria-selected", i === S.repIndex);
    const eye = el("button", "tool icon"); eye.setAttribute("aria-label", r.shown ? "Hide this representation" : "Show this representation"); eye.append(svgIcon(r.shown ? "i-eye" : "i-eye-off"));
    eye.onclick = async e => { e.stopPropagation(); if (await win("window_representation", { action: "modify", molecule: m.id, rep: i, shown: !r.shown })) after(); };
    const c = colorOf(r);
    row.append(eye, el("span", "sel-txt", r.sel), el("span", "tag", r.style), el("span", "tag", c.method === "ColorID" ? COLOR_IDS[c.id % 17] : c.method));
    row.onclick = () => { S.repIndex = i; renderReps(); }; list.append(row);
  });
  const r = m.reps[S.repIndex];
  if (r) { const c = colorOf(r); $("#rep-sel").value = r.sel; $("#rep-style").value = r.style; $("#rep-color").value = c.method; $("#rep-colorid").value = c.id; $("#rep-material").value = r.material; $("#rep-id-row").hidden = c.method !== "ColorID"; }
}
async function commitRep() {
  const m = repMol(); if (!m || !m.reps[S.repIndex]) return;
  const method = $("#rep-color").value, color = method === "ColorID" ? "ColorID " + $("#rep-colorid").value : method;
  $("#rep-err").textContent = "";
  const j = await win("window_representation", { action: "modify", molecule: m.id, rep: S.repIndex, selection: $("#rep-sel").value.trim() || "all", style: $("#rep-style").value, color, material: $("#rep-material").value }, true);
  if (!j) $("#rep-err").textContent = V.lastError; await after();
}
$("#rep-mol").onchange = () => { S.repIndex = 0; renderReps(); };
$("#rep-sel").onchange = commitRep; $("#rep-sel").onkeydown = e => { if (e.key === "Enter") commitRep(); };
["#rep-style", "#rep-color", "#rep-colorid", "#rep-material"].forEach(s => { $(s).onchange = commitRep; });
async function addRep(extra) {
  if (!(await ensureWindow())) return; const m = repMol() || V.topMol; if (!m) return toast("Load a structure first.", "err");
  const j = await win("window_representation", { action: "add", molecule: m.id, selection: S.defaults.sel, style: S.defaults.style, color: S.defaults.color, ...extra });
  if (j) { await after(); S.repIndex = (V.mol(m.id).reps.length || 1) - 1; renderReps(); }
}
$("#rep-add").onclick = () => addRep();
$("#rep-del").onclick = async () => { const m = repMol(); if (m && m.reps.length && await win("window_representation", { action: "delete", molecule: m.id, rep: S.repIndex })) { S.repIndex = 0; await after(); } };
function toggleReps(force) { const w = $("#repwin"); w.hidden = force === undefined ? !w.hidden : !force; $("#reps-btn").setAttribute("aria-pressed", !w.hidden); if (!w.hidden) { if (!V.connected) V.refresh(); renderReps(); } }
$("#reps-btn").onclick = () => toggleReps(); $("#repwin-close").onclick = () => toggleReps(false);
(function floatable() {                                   // drag the Representations window by its title
  const w = $("#repwin"), h = $(".floathead", w); let d = null;
  h.addEventListener("pointerdown", e => { if (e.target.closest("button")) return; const r = w.getBoundingClientRect(), p = w.parentElement.getBoundingClientRect(); d = { x: e.clientX - r.left, y: e.clientY - r.top, px: p.left, py: p.top }; h.setPointerCapture(e.pointerId); });
  h.addEventListener("pointermove", e => { if (!d) return; w.style.left = Math.max(0, e.clientX - d.px - d.x) + "px"; w.style.top = Math.max(0, e.clientY - d.py - d.y) + "px"; w.style.right = "auto"; });
  h.addEventListener("pointerup", () => { d = null; });
})();

// ------------------------------------------------------------------------------------------------ console
function help() { VACommands.HELP.forEach(l => clog("t", l)); }
async function runCommand(line) {
  const c = VACommands.parse(line); if (!c) return;
  clog("cmd", "vmd> " + line);
  if (c.error) return clog("err", c.error);
  const window_ = async (name, args, say) => { if (!(await ensureWindow())) return null; const j = await win(name, args); if (j) { if (say) clog("ok", "✓ " + (j.summary || say)); await after(); } return j; };
  const mol = id => (id == null ? V.top : id);
  switch (c.cmd) {
    case "help": return help();
    case "clear": return $("#consolelog").replaceChildren();
    case "files": return S.everything.forEach(f => clog("t", `${f.path}   (${f.kind})`));
    case "ask": showTab("chat"); return send(c.text);
    case "look": return look(c.tool, c.file);
    case "terminal": return terminal(c.line);
    case "workflow": showTab("jobs"); return runWorkflow(c.name, c.files);
    case "mol.new": return loadMolecule(c.file);
    case "mol.addfile": return addTrajectory(c.file, c.id);
    case "mol.delete": return window_("window_molecules", { action: "delete", molecule: mol(c.id) }, "deleted");
    case "mol.top": return window_("window_molecules", { action: "top", molecule: c.id }, "top molecule changed");
    case "mol.list": await V.refresh(); return V.mols.length ? V.mols.forEach(x => clog("t", `${x.id}${x.id === V.top ? " (top)" : ""}  ${x.name}  ${x.data.n_atoms} atoms  ${x.data.frames} frames  ${x.drawn ? "drawn" : "hidden"}  reps: ${x.reps.map(r => `[${r.sel} / ${r.style} / ${r.color}]`).join(" ")}`)) : clog("t", "no molecules");
    case "mol.default": Object.assign(S.defaults, { ...(c.style && { style: c.style }), ...(c.color && { color: c.color }), ...(c.sel && { sel: c.sel }) }); return clog("ok", `next representation: ${S.defaults.sel} / ${S.defaults.style} / ${S.defaults.color}`);
    case "mol.addrep": return window_("window_representation", { action: "add", molecule: mol(c.id), selection: S.defaults.sel, style: S.defaults.style, color: S.defaults.color }, "added");
    case "mol.modrep": { const a = { action: "modify", molecule: mol(c.id), rep: c.rep }; for (const [k, v] of [["selection", c.sel], ["style", c.style], ["color", c.color], ["shown", c.shown]]) if (v !== undefined) a[k] = v; return window_("window_representation", a, "changed"); }
    case "mol.delrep": return window_("window_representation", { action: "delete", molecule: mol(c.id), rep: c.rep }, "deleted");
    case "animate.goto": await stopAnim(); return gotoFrame(c.frame === Infinity ? 1e9 : c.frame);
    case "animate.forward": return playAnim(1);
    case "animate.reverse": return playAnim(-1);
    case "animate.pause": return stopAnim();
    case "animate.speed": S.anim.fps = Math.min(30, c.fps); $("#speed").value = S.anim.fps; $("#speed-n").textContent = S.anim.fps + "/s"; return win("window_animate", { action: "speed", speed: S.anim.fps / 30 });
    case "animate.style": S.anim.style = c.style; $("#style").value = c.style; return win("window_animate", { action: "style", style: c.style });
    case "display.projection": return setDisplay("projection", c.projection);
    case "display.depthcue": return setDisplay("depthcue", c.on ? "on" : "off");
    case "display.reset": return window_("window_view", { action: "reset" });
    case "axes": return setDisplay("axes", c.location);
    case "background": return setDisplay("background", c.color);
    case "rotate": return window_("window_view", { action: "rotate", axis: c.axis, degrees: c.degrees });
    case "scale": return c.mode === "by" ? window_("window_view", { action: "scale", factor: c.factor }) : clog("err", "VMD scales by a factor (scale by 1.5); it has no absolute size");
  }
}
$("#conform").onsubmit = e => { e.preventDefault(); const line = $("#conin").value.trim(); $("#conin").value = ""; if (!line) return; S.history.push(line); S.histAt = S.history.length; runCommand(line); };
$("#conin").onkeydown = e => {
  if (e.key === "ArrowUp" && S.histAt > 0) { e.preventDefault(); $("#conin").value = S.history[--S.histAt]; }
  else if (e.key === "ArrowDown") { e.preventDefault(); S.histAt = Math.min(S.history.length, S.histAt + 1); $("#conin").value = S.history[S.histAt] || ""; }
};
$("#clear").onclick = () => $("#consolelog").replaceChildren();
$("#console-fold").onclick = () => { const c = $("#console"); c.classList.toggle("min"); $("#console-fold").textContent = c.classList.contains("min") ? "▴" : "▾"; document.documentElement.style.setProperty("--console", c.classList.contains("min") ? "32px" : (store.get("console", 190) + "px")); };

async function terminal(line) {                         // the real command line (tool, tools, workflow), run on the server in the files folder
  const r = await api("/api/terminal", { line }), j = await r.json();
  (j.output || "").split("\n").forEach(l => clog(j.ok ? "t" : "err", l));
}

// ------------------------------------------------------------------------------------------------ the Tools tab: a form for every tool
const ROLE_KIND = { structure: "structure", trajectory: "trajectory", map: "map", video: "video", image: "image", any: null };
async function loadTools() {
  S.cat = await getJSON("/api/tools");
  const box = $("#tl"); box.textContent = "";
  const gl = el("label", null, "Group"), gs = el("select"), tl = el("label", null, "Tool"), ts = el("select"), head = el("div", "toolhead"), form = el("div"), run = el("button", "btn", "Run"), out = el("div", "res");
  gs.id = "tl-group"; ts.id = "tl-tool"; gl.htmlFor = gs.id; tl.htmlFor = ts.id; run.type = "button"; form.id = "tl-form"; out.id = "tl-out";
  S.cat.groups.forEach((g, i) => gs.append(new Option(g.name, i)));
  const fillTools = () => { ts.textContent = ""; S.cat.groups[Number(gs.value)].tools.forEach(t => ts.append(new Option(t.name, t.name))); showForm(); };
  const toolNamed = n => S.cat.groups.flatMap(g => g.tools).find(t => t.name === n);
  const showForm = () => {
    const t = toolNamed(ts.value); head.textContent = ""; head.append(document.createTextNode(t.summary), el("span", "needs", t.needs === "yes" ? "  (needs VMD)" : t.needs === "optional" ? "  (VMD, or the built-in drawing)" : ""));
    form.textContent = ""; out.textContent = ""; buildForm(form, t);
  };
  gs.onchange = fillTools; ts.onchange = showForm;
  run.onclick = () => runTool(toolNamed(ts.value), form, out, run);
  box.append(gl, gs, tl, ts, head, form, run, out); fillTools();
}
function fileOptions(role) { const kind = ROLE_KIND[role]; return S.everything.filter(f => kind === null || f.kind === kind); }
function widget(t, p) {
  const id = "tlp-" + p.name, wrap = el("div");
  const label = el("label", null, p.name.replace(/_/g, " ")); label.htmlFor = id; if (p.required) label.append(el("span", "req", " *"));
  let input;
  if (p.kind === "boolean") { input = el("input"); input.type = "checkbox"; input.checked = !!p.default; label.textContent = ""; const l2 = el("label", null, " " + p.name.replace(/_/g, " ")); l2.prepend(input); l2.htmlFor = id; input.id = id; wrap.append(l2); }
  else if (p.options) { input = el("div", "checks"); input.id = id; p.options.forEach(o => { const l = el("label", null, " " + o), c = el("input"); c.type = "checkbox"; c.value = o; c.checked = ["rmsd", "rgyr", "front", "side"].includes(o) && p.required; l.prepend(c); input.append(l); }); wrap.append(label, input); }
  else if (p.enum) { input = el("select"); input.id = id; if (!p.required) input.append(new Option("(default" + (p.default ? ": " + p.default : "") + ")", "")); p.enum.forEach(v => input.append(new Option(v, v))); wrap.append(label, input); }
  else if (p.role && p.role !== "output" && fileOptions(p.role).length && p.kind === "string") {
    input = el("select"); input.id = id; if (!p.required) input.append(new Option("(none)", ""));
    fileOptions(p.role).forEach(f => input.append(new Option(f.path, f.path)));
    if (p.name === "topology" || p.name === "model") { const m = V.topMol; if (m && m.path) input.value = m.path; }
    wrap.append(label, input);
  } else if (p.role === "any" && p.kind === "array") {
    input = el("select"); input.id = id; input.multiple = true; input.size = 4; fileOptions("any").forEach(f => input.append(new Option(f.path, f.path))); wrap.append(label, input);
  } else if (p.kind === "object") {
    input = el("textarea"); input.id = id; input.placeholder = '{"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure"}]}'; input.spellcheck = false;
    const js = S.everything.filter(f => f.kind === "data" && f.path.endsWith(".json")), pick = el("select"); pick.append(new Option("load from a .json file…", ""));
    js.forEach(f => pick.append(new Option(f.path, f.path))); pick.onchange = async () => { if (pick.value) input.value = await (await fetch(url(pick.value))).text(); };
    wrap.append(label, input); if (js.length) wrap.append(pick);
  } else if (p.kind === "array") { input = el("textarea"); input.id = id; input.spellcheck = false; input.placeholder = p.name === "claims" ? "one statement per line" : "words, separated by spaces"; wrap.append(label, input); }
  else if (p.kind === "integer" || p.kind === "number") { input = el("input"); input.type = "number"; input.step = p.kind === "integer" ? "1" : "any"; input.id = id; input.placeholder = p.default === null ? "" : String(p.default); wrap.append(label, input); }
  else { input = el("input"); input.type = "text"; input.id = id; input.spellcheck = false; input.autocomplete = "off"; if (p.role === "output" && p.default) input.value = p.default; else input.placeholder = p.default === null || p.default === undefined ? "" : String(p.default); wrap.append(label, input); }
  if (p.help && p.help !== p.name.replace(/_/g, " ")) wrap.append(el("div", "hint", p.help));
  wrap.dataset.param = p.name; wrap.input = input; return wrap;
}
function buildForm(form, t) {
  const main = el("div"), more = el("details"), ms = el("summary", null, "More options");
  more.append(ms); let nmore = 0;
  t.params.forEach(p => { const w = widget(t, p), simple = p.required || p.role || p.enum || p.options || p.kind === "object"; (simple ? main : (nmore++, more)).append(w); });
  form.append(main); if (nmore) form.append(more);
  form.params = t.params;
  const top = $("[data-param=topology]", form), trj = $("[data-param=trajectory]", form);          // choosing a structure picks the trajectory that goes with it
  if (top && trj && top.input.tagName === "SELECT" && trj.input.tagName === "SELECT") {
    const stem = p => p.replace(/\.[^./]+$/, ""), match = () => { const o = [...trj.input.options].find(x => x.value && stem(x.value) === stem(top.input.value)); if (o) trj.input.value = o.value; };
    top.input.addEventListener("change", match); match();
  }
}
function readForm(form) {
  const args = {};
  $$("[data-param]", form).forEach(w => {
    const p = form.params.find(x => x.name === w.dataset.param), i = w.input;
    if (p.kind === "boolean") args[p.name] = i.checked;
    else if (p.options) { const v = $$("input:checked", i).map(c => c.value); if (v.length) args[p.name] = v; }
    else if (i.multiple) { const v = [...i.selectedOptions].map(o => o.value); if (v.length) args[p.name] = v; }
    else if (i.value.trim()) args[p.name] = i.value.trim();
  });
  return args;
}
function resultView(r) {                               // a tool's result for a person: the summary, the facts, the details, the files it made
  const d = el("div");
  if (r && typeof r === "object" && !Array.isArray(r)) {
    if (r.ok === false || r.error) d.append(el("div", "banner", String(r.error || "the tool reported a problem")));
    if (typeof r.summary === "string") d.append(el("p", null, r.summary));
    const kv = el("dl", "kv"), deep = {};
    for (const [k, v] of Object.entries(r)) {
      if (k === "summary" || k === "error") continue;
      if (v === null || ["string", "number", "boolean"].includes(typeof v)) { if (String(v).length < 300) { kv.append(el("dt", null, k), el("dd", null, String(v))); continue; } }
      deep[k] = v;
    }
    if (kv.children.length) d.append(kv);
    if (Object.keys(deep).length) { const det = el("details"); det.append(el("summary", null, "Details"), el("pre", null, JSON.stringify(deep, null, 1).slice(0, 12000))); d.append(det); }
  } else d.append(el("pre", null, JSON.stringify(r, null, 1).slice(0, 12000)));
  return d;
}
async function runTool(t, form, out, button) {
  if (S.busy) return toast("Another job is still running.", "err");
  const args = readForm(form); out.textContent = ""; S.busy = true; button.disabled = true;
  const prog = el("div", "hint", "starting…"), bar = el("div", "bar"); bar.append(el("div")); bar.hidden = true; out.append(prog, bar);
  clog("cmd", "tool " + t.name + " " + JSON.stringify(args));
  await stream("/api/tool", { name: t.name, args }, ev => {
    if (ev.type === "tool_progress") { prog.textContent = ev.text; clog("job", "  " + ev.text); if (ev.fraction != null) { bar.hidden = false; bar.firstChild.style.width = Math.round(ev.fraction * 100) + "%"; } }
    else if (ev.type === "error") { prog.remove(); bar.remove(); out.append(el("div", "banner", ev.text)); clog("err", "✗ " + ev.text); }
    else if (ev.type === "tool_result") {
      prog.remove(); bar.remove(); const bad = ev.result && ev.result.ok === false;
      out.append(el("div", "toolhead", `${bad ? "✗" : "✓"} ${t.name}  ${fmt(ev.seconds)}`), resultView(ev.result));
      const cmd = el("div", "cmd", ev.command), cp = el("button", "btn small", "Copy command"); cp.type = "button"; cp.onclick = () => navigator.clipboard && navigator.clipboard.writeText(ev.command).then(() => toast("Copied", "ok"));
      out.append(el("div", "hint", "the same from a terminal:"), cmd, cp);
      if (ev.images && ev.images.length) out.append(figs(ev.images));
      const others = (ev.files || []).filter(f => !(ev.images || []).includes(f));
      if (others.length) { const ul = el("ul", "made"); others.forEach(f => { const li = el("li"), a = el("a", null, f); a.href = url(f); a.target = "_blank"; a.rel = "noopener"; li.append(a); ul.append(li); }); out.append(el("div", "hint", "files it wrote or read:"), ul); }
      clog(bad ? "err" : "ok", `${bad ? "✗" : "✓"} ${t.name}  ${fmt(ev.seconds)}`); loadFiles();
    }
  });
  S.busy = false; button.disabled = false;
}

// ------------------------------------------------------------------------------------------------ uploads
const drop = $("#drop");
async function upload(list) { for (const f of list) { const r = await fetch("/api/upload?name=" + encodeURIComponent(f.name), { method: "POST", body: f }), j = await r.json(); j.error ? toast(f.name + ": " + j.error, "err") : (clog("ok", "✓ added " + j.path), toast("Added " + j.path, "ok")); } loadFiles(); }
const pickFiles = () => $("#pick").click();
drop.onclick = pickFiles; drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickFiles(); } };
$("#pick").onchange = e => upload([...e.target.files]);
["dragenter", "dragover"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => upload([...e.dataTransfer.files]));

// ------------------------------------------------------------------------------------------------ server events
async function stream(path, body, on) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok || !r.body) { const j = await r.json().catch(() => ({})); on({ type: "error", text: j.error || ("HTTP " + r.status) }); return; }
  const reader = r.body.getReader(), dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let i; while ((i = buf.indexOf("\n\n")) >= 0) { const chunk = buf.slice(0, i); buf = buf.slice(i + 2); if (chunk.startsWith("data: ")) on(JSON.parse(chunk.slice(6))); }
  }
}
function showTab(p) { $$(".tab").forEach(t => { const on = t.dataset.p === p; t.classList.toggle("on", on); t.setAttribute("aria-selected", on); }); $$("#chat,#jobs,#tools").forEach(x => x.classList.toggle("on", x.id === p)); if (p === "chat") $("#q").focus(); if (p === "tools" && !S.cat) loadTools(); }
$$(".tab").forEach(t => t.onclick = () => showTab(t.dataset.p));

// ------------------------------------------------------------------------------------------------ chat
const log = $("#log"), scroller = $("#scroll");
const toBottom = () => { scroller.scrollTop = scroller.scrollHeight; };
function aiBlock() {
  const b = el("div", "msg ai"), body = el("div"), cp = el("button", "tool copy", "Copy"); cp.type = "button";
  cp.onclick = () => navigator.clipboard && navigator.clipboard.writeText(b.dataset.text || "").then(() => toast("Copied", "ok"));
  b.append(cp, body); b.body = body; return b;
}
async function send(text) {
  if (S.busy || !text.trim()) return;
  S.busy = true; $("#send").disabled = true; $("#q").value = ""; autosize(); $("#welcome").classList.add("gone");
  log.append(el("div", "msg me", text)); clog("cmd", "? " + text);
  const think = el("div", "think"); think.append(el("span", "spin"), document.createTextNode("the model is working")); log.append(think);
  const running = new Set(); let current = null, block = null, said = "";
  const place = node => log.insertBefore(node, think.isConnected ? think : null);
  const textBlock = () => { if (!block) { block = aiBlock(); place(block); said = ""; } return block; };
  const show = (b, t) => { b.dataset.text = t; b.body.innerHTML = VAMarkdown.render(t); };
  const ticker = setInterval(() => { for (const t of running) t.sec.textContent = fmt((performance.now() - t.t) / 1000); }, 200);
  await stream("/api/chat", { message: text }, ev => {
    if (ev.type === "token") { think.hidden = true; said += ev.text; show(textBlock(), said); }
    else if (ev.type === "model_start") { think.hidden = false; log.append(think); }
    else if (ev.type === "model_end") { think.hidden = true; place(el("div", "mline", "model call " + fmt(ev.seconds))); clog("mod", "model call " + fmt(ev.seconds)); }
    else if (ev.type === "tool_start") {
      think.hidden = true; block = null;
      const card = el("div", "tool-card run"), head = el("button", "head"), sec = el("span", "sec", "0.00 s"), more = el("div", "more"), argsPre = el("pre", null, Object.entries(ev.args || {}).map(([k, v]) => `${k} = ${v}`).join("\n"));
      head.type = "button"; head.append(el("span", "name", ev.name), sec); head.onclick = () => { card.classList.toggle("open"); head.setAttribute("aria-expanded", card.classList.contains("open")); }; head.setAttribute("aria-expanded", "false");
      const prog = el("div", "prog"), bar = el("div", "bar"); bar.append(el("div")); bar.hidden = true;
      more.append(el("b", null, "arguments"), argsPre); card.append(head, prog, bar, more); place(card);
      current = { card, sec, prog, bar, more, name: ev.name, t: performance.now() }; running.add(current);
      clog("job", "▸ " + ev.name + "  " + Object.entries(ev.args || {}).map(([k, v]) => k + "=" + v).join(" ").slice(0, 160));
    }
    else if (ev.type === "tool_progress" && current) { current.prog.textContent = ev.text; if (ev.fraction != null) { current.bar.hidden = false; current.bar.firstChild.style.width = Math.round(ev.fraction * 100) + "%"; } }
    else if (ev.type === "tool_end" && current) {
      running.delete(current); current.card.classList.remove("run"); current.sec.textContent = fmt(ev.seconds); current.bar.hidden = true;
      if (ev.error) { current.card.classList.add("err"); current.prog.textContent = ev.error; }
      if (ev.preview) current.more.append(el("b", null, "result"), el("pre", null, ev.preview));
      if (ev.images && ev.images.length) current.card.append(figs(ev.images));
      clog(ev.error ? "err" : "ok", `${ev.error ? "✗" : "✓"} ${ev.name}  ${fmt(ev.seconds)}${ev.error ? "  " + ev.error.slice(0, 120) : ""}`);
      if (ev.name && ev.name.startsWith("window_")) V.refresh(true);              // the agent changed the VMD window: show it
      think.hidden = false; log.append(think);
    }
    else if (ev.type === "answer") {
      think.remove(); show(textBlock(), ev.text);
      log.append(el("div", "clock", ev.line)); clog("ok", ev.line); loadStatus();
    }
    else if (ev.type === "error" && ev.kind === "model") {
      think.remove(); const n = el("div", "msg sys", ev.text), acts = el("div", "acts"), m = el("button", "btn small", "Choose a model…"), r = el("button", "btn small", "Ask again");
      m.onclick = openModel; r.onclick = () => { $("#q").value = text; $("#q").focus(); }; acts.append(m, r); n.append(acts); place(n); clog("err", "✗ " + ev.text); loadStatus();
    }
    else if (ev.type === "error") { think.remove(); show(textBlock(), "Something went wrong: " + ev.text); clog("err", "✗ " + ev.text); }
    toBottom();
  });
  clearInterval(ticker); think.remove(); S.busy = false; $("#send").disabled = false; $("#q").focus(); loadFiles();
}
const autosize = () => { const q = $("#q"); q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 140) + "px"; };
$("#q").addEventListener("input", autosize);
$("#q").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($("#q").value); } });
$("#composer").onsubmit = e => { e.preventDefault(); send($("#q").value); };
$("#new").onclick = async () => { await api("/api/reset", {}); log.textContent = ""; $("#welcome").classList.remove("gone"); clog("job", "new conversation"); loadStatus(); };

// ------------------------------------------------------------------------------------------------ whole jobs
let workflows = {};
async function loadWorkflows() {
  workflows = (await getJSON("/api/workflows")).workflows || {};
  const box = $("#wf"); box.textContent = "";
  box.append(el("div", "does", "A whole job runs several tools in a fixed order, grades what it finds, and writes a report you can send to someone. No model is involved."));
  const l = el("label", null, "Job"); l.htmlFor = "wfname"; box.append(l); const sel = el("select"); sel.id = "wfname";
  for (const k of Object.keys(workflows)) sel.append(new Option(k.replace(/_/g, " "), k));
  const why = el("div", "does"); why.id = "wfdoes"; sel.onchange = renderSlots; const slots = el("div"); slots.id = "slots"; box.append(sel, why, slots);
  const run = el("button", "btn primary", "Run"); run.id = "runwf"; run.onclick = () => runWorkflow($("#wfname").value, $$("#slots select").map(s => s.value));
  const out = el("div"); out.id = "wfout"; box.append(run, out);
  renderSlots();
}
function renderSlots() {
  const w = workflows[$("#wfname").value]; if (!w) return; $("#wfdoes").textContent = w.does + (w.needs_vmd ? " (needs VMD)" : "");
  const box = $("#slots"), old = $$("select", box).map(s => s.value); box.textContent = "";
  w.files.forEach((slot, i) => {
    const l = el("label", null, slot.replace(/_/g, " ")), s = el("select"); s.id = "slot" + i; l.htmlFor = s.id; box.append(l);
    const want = /traj/.test(slot) ? "trajectory" : /map/.test(slot) ? "map" : "structure";
    for (const f of S.everything.filter(f => f.kind === want)) s.append(new Option(f.path, f.path));
    if (old[i]) s.value = old[i]; else if (want === "structure" && V.topMol && V.topMol.path) s.value = V.topMol.path; box.append(s);
  });
}
async function runWorkflow(name, chosen) {
  if (S.busy) return toast("Another job is still running.", "err");
  const out = $("#wfout"); out.textContent = "";
  if (!workflows[name]) return toast("No such workflow: " + name, "err");
  if (!chosen.length || chosen.some(c => !c)) { out.append(el("div", "banner", "Pick a file for each line first (add files on the left).")); return; }
  S.busy = true; $("#runwf").disabled = true;
  const prog = el("div", "does", "starting…"), bar = el("div", "bar"); bar.append(el("div")); bar.hidden = true; out.append(prog, bar);
  clog("cmd", `workflow ${name} ${chosen.join(" ")}`);
  await stream("/api/workflow", { name, files: chosen }, ev => {
    if (ev.type === "tool_progress") { prog.textContent = ev.text; clog("job", "  " + ev.text); if (ev.fraction != null) { bar.hidden = false; bar.firstChild.style.width = Math.round(ev.fraction * 100) + "%"; } }
    else if (ev.type === "error") { out.append(el("div", "banner", "Something went wrong: " + ev.text)); clog("err", "✗ " + ev.text); }
    else if (ev.type === "workflow") {
      prog.remove(); bar.remove(); const r = ev.result;
      if (r.error) { out.append(el("div", "banner", r.error)); clog("err", "✗ " + r.error); return; }
      out.append(el("div", "verdict", r.verdict), el("div", "clock", "the whole job took " + fmt(ev.seconds))); clog("ok", `✓ workflow ${name}  ${fmt(ev.seconds)}`);
      for (const f of r.findings || []) { const row = el("div", "finding"); row.append(el("span", "badge " + f.level, f.level), el("span", null, f.text)); out.append(row); }
      const t = el("table", "steps"), hr = el("tr"); ["#", "step", "tool", "seconds"].forEach(h => hr.append(el("th", null, h))); t.append(hr);
      for (const s of r.steps || []) { const tr = el("tr"); tr.append(el("td", null, s.n), el("td", null, s.label + (s.ok ? "" : "  (failed)")), el("td", null, s.tool), el("td", null, Number(s.seconds).toFixed(2))); t.append(tr); clog(s.ok ? "ok" : "err", `  ${s.ok ? "✓" : "✗"} ${s.tool}  ${Number(s.seconds).toFixed(2)} s  ${s.label}`); }
      out.append(t, figs(ev.images));
      if (ev.report_html) { const a = el("a", null, "Open the report (report.html)"); a.href = url(ev.report_html); a.target = "_blank"; a.rel = "noopener"; const d = el("div", "linkrow"); d.append(a); out.append(d); }
      loadFiles();
    }
  });
  S.busy = false; $("#runwf").disabled = false;
}

// ------------------------------------------------------------------------------------------------ actions, menus, palette, shortcuts
const A = {};                                              // id -> {label, group, key, run, checked, enabled}
function act(id, group, label, run, extra) { A[id] = { id, group, label, run, ...extra }; }
const fileChoices = kind => S.everything.filter(f => f.kind === kind).map(f => ({ label: f.path, value: f.path, tag: KIND[f.kind], kind: f.kind }));
const MAC = /Mac/.test(navigator.platform), keyText = k => k.replace("Ctrl", MAC ? "⌘" : "Ctrl");
act("file.add", "File", "Add files…", pickFiles);
act("file.save", "File", "Save picture (PNG)…", async () => { if (!V.connected) return toast("Open a VMD window first.", "err"); const j = await win("window_snapshot", { out_png: "vmd_window.png", quality: "tachyon" }); if (j) { clog("ok", "✓ " + j.summary); addFigure(V.rel(j.image)); media(V.rel(j.image), "image"); loadFiles(); } }, { key: "Ctrl S" });
act("file.refresh", "File", "Refresh the file list", () => { loadFiles(); loadStatus(); V.refresh(true); });
act("vmd.open", "File", "Open the VMD window", () => openVMD(), { enabled: () => !V.connected });
act("mol.new", "Molecule", "New molecule…", async () => { const p = await choose("New molecule: choose a structure", fileChoices("structure")); if (p) loadMolecule(p); });
act("mol.addfile", "Molecule", "Load data into the top molecule…", async () => { const p = await choose("Load a trajectory into the top molecule", fileChoices("trajectory")); if (p) addTrajectory(p); });
act("mol.delete", "Molecule", "Delete the top molecule", () => { if (V.topMol) moleculeAction("delete", V.top); }, { enabled: () => !!V.topMol });
act("mol.toggle", "Molecule", "Show or hide the top molecule", () => { const m = V.topMol; if (m) moleculeAction(m.drawn ? "hide" : "show", m.id); }, { enabled: () => !!V.topMol });
act("mol.inspect", "Molecule", "Describe the top molecule (detect system)", () => { const m = V.topMol; if (m && m.path) look("detect_system", m.path); }, { enabled: () => !!V.topMol });
act("reps.open", "Graphics", "Representations…", () => toggleReps(true), { key: "Ctrl R" });
act("rep.add", "Graphics", "Create a representation", async () => { toggleReps(true); await addRep(); }, { enabled: () => !!V.topMol });
act("rep.delete", "Graphics", "Delete the selected representation", () => { $("#rep-del").onclick(); }, { enabled: () => !!V.topMol });
act("proj.persp", "Display", "Perspective", () => setDisplay("projection", "Perspective"), { checked: () => V.settings.projection === "Perspective" });
act("proj.ortho", "Display", "Orthographic", () => setDisplay("projection", "Orthographic"), { checked: () => V.settings.projection === "Orthographic" });
act("display.depth", "Display", "Depth cueing", () => setDisplay("depthcue", V.settings.depthcue ? "off" : "on"), { checked: () => V.settings.depthcue });
act("display.axes", "Display", "Axes (lower left)", () => setDisplay("axes", V.settings.axes === "Off" ? "LowerLeft" : "Off"), { checked: () => V.settings.axes !== "Off" });
act("display.shadows", "Display", "Shadows", () => setDisplay("shadows", V.settings.shadows ? "off" : "on"), { checked: () => V.settings.shadows });
["black", "gray", "white"].forEach(c => act("bg." + c, "Display", "Background: " + c, () => setDisplay("background", c), { checked: () => V.settings.background === c }));
act("view.reset", "Display", "Reset view", async () => { if (await win("window_view", { action: "reset" })) V.snapshot(); }, { key: "=" });
[["rotate", "Rotate", "R"], ["translate", "Move", "T"], ["scale", "Zoom", "S"]].forEach(([m, l, k]) => act("mouse." + m, "Mouse", l, () => setMouse(m), { key: k, checked: () => V.settings.mouse === m }));
act("anim.play", "Animation", "Play or pause", () => (S.anim.timer ? stopAnim() : playAnim(1)), { key: "Space" });
act("anim.next", "Animation", "Next frame", async () => { const m = V.topMol; if (m) { await stopAnim(); gotoFrame(m.frame + 1); } }, { key: "→" });
act("anim.prev", "Animation", "Previous frame", async () => { const m = V.topMol; if (m) { await stopAnim(); gotoFrame(m.frame - 1); } }, { key: "←" });
act("ext.palette", "Extensions", "Search actions…", () => openPalette(), { key: "Ctrl K" });
act("ext.model", "Extensions", "Model…", () => openModel());
act("ext.tools", "Extensions", "Tools (forms)…", () => showTab("tools"));
act("ext.chat", "Extensions", "Chat with the agent", () => showTab("chat"), { key: "Ctrl J" });
act("ext.jobs", "Extensions", "Whole jobs (workflows)…", () => showTab("jobs"));
act("ext.console", "Extensions", "Go to the console", () => { $("#console").classList.remove("min"); $("#conin").focus(); }, { key: "/" });
act("help.shortcuts", "Help", "Keyboard shortcuts", () => { fillShortcuts(); $("#shortcuts").showModal(); }, { key: "?" });
act("help.console", "Help", "Console commands", () => { $("#console").classList.remove("min"); help(); });
act("help.about", "Help", "About vmd-agent", () => $("#about").showModal());
const MENUS = [["File", ["vmd.open", "file.add", "file.save", "file.refresh"]], ["Molecule", ["mol.new", "mol.addfile", "-", "mol.toggle", "mol.inspect", "-", "mol.delete"]], ["Graphics", ["reps.open", "rep.add", "rep.delete"]],
               ["Display", ["proj.persp", "proj.ortho", "-", "display.depth", "display.axes", "display.shadows", "-", "bg.black", "bg.gray", "bg.white", "-", "view.reset"]], ["Mouse", ["mouse.rotate", "mouse.translate", "mouse.scale"]],
               ["Animation", ["anim.play", "anim.prev", "anim.next"]], ["Extensions", ["ext.palette", "ext.model", "-", "ext.chat", "ext.tools", "ext.jobs", "ext.console"]], ["Help", ["help.shortcuts", "help.console", "help.about"]]];
function closeMenus(except) { $$(".menu.open").forEach(m => { if (m === except) return; m.classList.remove("open"); const d = $(".dropdown", m); if (d) d.remove(); $("button", m).setAttribute("aria-expanded", "false"); }); }
function buildMenus() {
  const nav = $("#menus"); nav.textContent = "";
  MENUS.forEach(([title, ids]) => {
    const wrap = el("div", "menu"), btn = el("button", null, title); btn.setAttribute("role", "menuitem"); btn.setAttribute("aria-haspopup", "true"); btn.setAttribute("aria-expanded", "false"); wrap.append(btn);
    const open = (focus) => {
      closeMenus(); wrap.classList.add("open"); btn.setAttribute("aria-expanded", "true"); const dd = el("div", "dropdown"); dd.setAttribute("role", "menu");
      ids.forEach(id => {
        if (id === "-") return dd.append(el("hr"));
        const a = A[id], it = el("button", null, a.label); it.setAttribute("role", a.checked ? "menuitemradio" : "menuitem"); if (a.checked) it.setAttribute("aria-checked", a.checked()); if (a.enabled && !a.enabled()) it.disabled = true;
        if (a.key) it.append(el("span", "grow"), el("kbd", null, keyText(a.key))); it.onclick = () => { closeMenus(); a.run(); }; dd.append(it);
      });
      wrap.append(dd); if (focus) { const first = $("button:not(:disabled)", dd); if (first) first.focus(); }
    };
    btn.onclick = () => (wrap.classList.contains("open") ? closeMenus() : open(false));
    btn.onmouseenter = () => { if ($(".menu.open") && !wrap.classList.contains("open")) open(false); };
    wrap.onkeydown = e => {
      const items = $$(".dropdown button:not(:disabled)", wrap), i = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); if (!wrap.classList.contains("open")) return open(true); (items[i + 1] || items[0] || btn).focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); (items[i - 1] || items[items.length - 1] || btn).focus(); }
      else if (e.key === "Escape") { closeMenus(); btn.focus(); }
      else if (e.key === "ArrowRight" || e.key === "ArrowLeft") { const ms = $$(".menu"), j = ms.indexOf(wrap), n = ms[(j + (e.key === "ArrowRight" ? 1 : ms.length - 1)) % ms.length]; $("button", n).click(); $("button", n).focus(); }
    };
    nav.append(wrap);
  });
}
document.addEventListener("click", e => { if (!e.target.closest(".menu")) closeMenus(); });

// the command palette
const palette = { items: [], at: 0 };
function openPalette() { const d = $("#palette"), input = $("#pal-in"); input.value = ""; palette.at = 0; renderPalette(); d.showModal(); input.focus(); }
function renderPalette() {
  const q = $("#pal-in").value.trim().toLowerCase(), list = $("#pal-list"); list.textContent = "";
  palette.items = Object.values(A).filter(a => !q || (a.group + " " + a.label).toLowerCase().includes(q)).filter(a => !a.enabled || a.enabled());
  palette.at = Math.min(palette.at, Math.max(0, palette.items.length - 1));
  palette.items.forEach((a, i) => { const li = el("li"); li.setAttribute("role", "option"); li.setAttribute("aria-selected", i === palette.at); li.append(el("span", "grp", a.group), el("span", null, a.label)); if (a.key) li.append(el("kbd", null, keyText(a.key))); li.onclick = () => runPalette(i); list.append(li); });
  const sel = $('[aria-selected="true"]', list); if (sel) sel.scrollIntoView({ block: "nearest" });
}
function runPalette(i) { const a = palette.items[i]; if (!a) return; $("#palette").close(); a.run(); }
$("#pal-in").oninput = () => { palette.at = 0; renderPalette(); };
$("#pal-in").onkeydown = e => {
  if (e.key === "ArrowDown") { e.preventDefault(); palette.at = Math.min(palette.items.length - 1, palette.at + 1); renderPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); palette.at = Math.max(0, palette.at - 1); renderPalette(); }
  else if (e.key === "Enter") { e.preventDefault(); runPalette(palette.at); }
};
$("#palette").addEventListener("click", e => { if (e.target.id === "palette") $("#palette").close(); });
function fillShortcuts() {
  const t = $("#sc-table"); t.textContent = "";
  const rows = [["Ctrl K", "Search every action"], ...Object.values(A).filter(a => a.key).map(a => [a.key, a.label]), ["Shift-drag", "Move the view in any mouse mode"], ["Wheel", "Zoom the VMD window"], ["Double-click the display", "Reset the VMD view"], ["↑ ↓ in the console", "Earlier commands"]];
  rows.forEach(([k, d]) => { const tr = el("tr"); tr.append(el("td", null, keyText(k)), el("td", null, d)); t.append(tr); });
}
document.addEventListener("keydown", e => {
  const typing = e.target.closest && e.target.closest("input, textarea, select, [contenteditable]"), mod = e.ctrlKey || e.metaKey, key = e.key.toLowerCase();
  if (mod && key === "k") { e.preventDefault(); return openPalette(); }
  if (mod && key === "s") { e.preventDefault(); return A["file.save"].run(); }
  if (mod && key === "j") { e.preventDefault(); return A["ext.chat"].run(); }
  if (mod && key === "r") { e.preventDefault(); return A["reps.open"].run(); }
  if (typing || mod || e.altKey || document.querySelector("dialog[open]")) return;
  const map = { r: "mouse.rotate", t: "mouse.translate", s: "mouse.scale", "=": "view.reset", " ": "anim.play", arrowright: "anim.next", arrowleft: "anim.prev", "?": "help.shortcuts", "/": "ext.console" };
  const id = map[key]; if (id) { e.preventDefault(); A[id].run(); }
});

// ------------------------------------------------------------------------------------------------ layout: splitters, theme
function splitter(id, opts) {
  const s = $(id); let drag = null;
  const apply = v => { v = Math.max(opts.min, Math.min(opts.max(), v)); document.documentElement.style.setProperty(opts.prop, v + "px"); if (opts.key) store.set(opts.key, v); return v; };
  const saved = opts.key ? store.get(opts.key, null) : null; if (saved) apply(saved);
  s.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, v: opts.current() }; s.setPointerCapture(e.pointerId); s.classList.add("drag"); });
  s.addEventListener("pointermove", e => { if (drag) apply(drag.v + opts.delta(e.clientX - drag.x, e.clientY - drag.y)); });
  const end = () => { drag = null; s.classList.remove("drag"); }; s.addEventListener("pointerup", end); s.addEventListener("pointercancel", end);
  s.addEventListener("keydown", e => { const step = e.shiftKey ? 48 : 16, d = { ArrowLeft: -step, ArrowUp: -step, ArrowRight: step, ArrowDown: step }[e.key]; if (d !== undefined) { e.preventDefault(); apply(opts.current() + opts.delta(d, d)); } });
  s.addEventListener("dblclick", () => { document.documentElement.style.removeProperty(opts.prop); if (opts.key) store.set(opts.key, null); });
}
function theme(mode) {
  const root = document.documentElement; if (mode === "auto") root.removeAttribute("data-theme"); else root.dataset.theme = mode; store.set("theme", mode);
  $("#theme").title = "Colour theme: " + mode + " (click to change)"; $("#theme").textContent = "theme: " + mode;
}
$("#theme").onclick = () => theme({ auto: "light", light: "dark", dark: "auto" }[store.get("theme", "auto")]);

// ------------------------------------------------------------------------------------------------ start up
V = new Live($("#view"));
V.onchange = kind => {
  if (kind === "picture") return;
  renderMolecules(); updateCaption(); refreshAnim(); if (!$("#repwin").hidden) renderReps();
};
S.anim.fps = store.get("speed", 8); $("#speed").value = S.anim.fps; $("#speed-n").textContent = S.anim.fps + "/s";
buildMenus(); setMouse(store.get("mouse", "rotate")); theme(store.get("theme", "auto"));
splitter("#split-left", { prop: "--left", key: "left", min: 220, max: () => innerWidth * 0.45, current: () => $("#left").getBoundingClientRect().width, delta: dx => dx });
splitter("#split-right", { prop: "--right", key: "right", min: 300, max: () => innerWidth * 0.55, current: () => $("#right").getBoundingClientRect().width, delta: dx => -dx });
splitter("#split-console", { prop: "--console", key: "console", min: 40, max: () => innerHeight * 0.6, current: () => $("#console").getBoundingClientRect().height, delta: (dx, dy) => -dy });
splitter("#split-mol", { prop: "--molrows", key: "molrows", min: 90, max: () => innerHeight * 0.6, current: () => $("#molpane").getBoundingClientRect().height, delta: (dx, dy) => dy });
$("#mol-load").onclick = () => A["mol.new"].run(); $("#mol-delete").onclick = () => A["mol.delete"].run();
renderMolecules(); refreshAnim(); updateCaption();
clog("job", "vmd-agent ready. Type help for the console commands, or press Ctrl+K to search every action.");
loadFiles(); loadWorkflows(); loadStatus().then(() => V.refresh(true));
setInterval(() => { if (!S.busy) { loadFiles(); if (!S.status.model_ready) loadStatus(); } }, 15000);
// the VMD window can also be changed in its own window, or by a command typed elsewhere: look again every few seconds (and take a new picture if "live" is on)
setInterval(async () => { if (document.hidden || V.snapping) return; await V.refresh($("#live").checked && V.connected); }, 3000);
