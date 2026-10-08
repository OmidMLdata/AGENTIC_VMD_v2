"use strict";
/* The page. Everything the user can do is an action (menus, the command palette, keyboard shortcuts and the console all run the same ones); the
 * viewer (viewer.js) draws; the server (vmd_agent.ui) runs the agent, the tools and the whole jobs. No framework, no build step. */
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
const S = { everything: [], open: new Set(), selected: null, status: {}, busy: false, figures: [], repIndex: 0, history: [], histAt: 0, anim: { timer: null, dir: 1, fps: 8, style: "loop" } };
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
  $("#ver").textContent = "v" + s.version; document.title = "vmd-agent " + s.version;
  const left = $("#statusleft"); left.textContent = "";
  left.append(dot(s.model_ready ? "ok" : "bad", "model", s.model), dot(s.vmd ? "ok" : "warn", "VMD", s.vmd ? (s.vmd_version || "found") : "not found"), dot(s.ffmpeg ? "ok" : "warn", "ffmpeg", s.ffmpeg ? "ready" : "missing"));
  $("#folder").textContent = s.data_dir.split(/[\\/]/).slice(-2).join("/"); $("#folder").title = s.data_dir;
  const sel = $("#profile"); sel.textContent = "";
  for (const [k, n] of Object.entries(s.profiles)) sel.append(new Option(n ? `${k} (${n})` : `${k} (fits the question)`, k));
  sel.value = s.profile;
  $("#banner").textContent = "";
  if (!s.model_ready) { const b = el("div", "banner"); b.append(document.createTextNode("The chat needs a model and none answers right now: " + (s.model_problem || "") + " Viewing, files and whole jobs work without one. Run "), el("code", null, "vmd-agent setup"), document.createTextNode(" to choose a model.")); $("#banner").append(b); }
  $("#about-text").textContent = `Version ${s.version}. Model: ${s.model}. VMD: ${s.vmd ? s.vmd + " (" + (s.vmd_version || "version unknown") + ")" : "not found"}. Files folder: ${s.data_dir}. ${s.n_tools} tools; the chat is offered ${s.tools_in_chat}.`;
  totals(s.clock);
}
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

// ------------------------------------------------------------------------------------------------ molecules
function partnerStructure(path) {
  const stem = path.replace(/\.[^.]+$/, ""), s = S.everything.filter(x => x.kind === "structure");
  return s.find(x => x.path.replace(/\.[^.]+$/, "") === stem) || (V.topMol && s.find(x => x.path === V.topMol.path)) || (s.length === 1 ? s[0] : null);
}
async function fetchMolecule(path, traj) {
  const r = await api("/api/structure?path=" + encodeURIComponent(path) + (traj ? "&traj=" + encodeURIComponent(traj) : "")), data = await r.json();
  if (data.error) throw new Error(data.error); return data;
}
async function loadMolecule(path, traj) {
  const t0 = performance.now(); clog("cmd", `mol new ${path}${traj ? "  +  " + traj : ""}`);
  try {
    const data = await fetchMolecule(path, traj), m = V.addMolecule(base(path), data, traj); m.path = path;
    if (!traj) { const t = S.everything.find(x => x.kind === "trajectory" && x.path.replace(/\.[^.]+$/, "") === path.replace(/\.[^.]+$/, "")); if (t) await addTrajectory(t.path, m.id, true); }
    clog("ok", `✓ molecule ${m.id}: ${data.n_atoms} atoms, ${data.bonds.length} bonds, ${data.frames} frame${data.frames === 1 ? "" : "s"}  ${fmt((performance.now() - t0) / 1000)}${data.reduced ? "  (backbone and non-solvent atoms only: the system is large)" : ""}`);
    return m;
  } catch (e) { clog("err", "✗ " + e.message); toast(e.message, "err"); return null; }
}
async function addTrajectory(path, id, quiet) {
  const m = id == null ? V.topMol : V.mol(id);
  if (!m) { const s = partnerStructure(path); if (!s) { toast("Load a structure first (double-click a .pdb or .psf).", "err"); return; } return loadMolecule(s.path, path); }
  clog("cmd", `mol addfile ${path} ${m.id}`);
  try { const data = await fetchMolecule(m.path, path); V.replaceData(m, data, path); await gotoFrame(0); if (!quiet) clog("ok", `✓ ${data.frames} frames loaded into molecule ${m.id}`); }
  catch (e) { clog("err", "✗ " + e.message); toast(e.message, "err"); }
}
function renderMolecules() {
  const tb = $("#mols tbody"); tb.textContent = ""; $("#mols-empty").hidden = V.mols.length > 0; $("#mols").hidden = V.mols.length === 0;
  for (const m of V.mols) {
    const tr = el("tr", m.id === V.top ? "sel" : ""); tr.title = m.path || m.name;
    const tog = (on, label, fn) => { const b = el("button", "toggle " + (on ? "on" : "off"), on ? "✓" : ""); b.setAttribute("aria-pressed", on); b.setAttribute("aria-label", label); b.onclick = e => { e.stopPropagation(); fn(); }; return b; };
    const c = (...n) => { const td = el("td"); td.append(...n); return td; };
    const nameTd = c(m.name), nTd = c(String(m.data.n_atoms)), fTd = c(String(m.data.frames)); nameTd.className = "name"; nTd.className = "num"; fTd.className = "num";
    tr.append(c(String(m.id)), c(tog(m.id === V.top, "Make molecule " + m.id + " the top molecule", () => V.setTop(m.id))), c(tog(m.drawn, (m.drawn ? "Hide" : "Show") + " molecule " + m.id, () => V.setDrawn(m.id, !m.drawn))), nameTd, nTd, fTd);
    tr.onclick = () => V.setTop(m.id); tb.append(tr);
  }
}

// ------------------------------------------------------------------------------------------------ display
function media(rel, kind) {
  const m = $("#media"); m.textContent = ""; m.classList.add("on"); $("#nodata").hidden = true;
  const node = el(kind === "video" ? "video" : "img"); node.src = url(rel); if (kind === "video") node.controls = true; node.alt = rel;
  const back = el("button", "btn small back", "Back to the molecule"); back.onclick = () => { m.classList.remove("on"); updateCaption(); };
  m.append(node, back); $("#caption").textContent = rel;
}
function updateCaption() {
  const m = V.topMol; $("#nodata").hidden = V.mols.some(x => x.drawn);
  $("#caption").textContent = m ? `${m.name}${m.traj ? " + " + base(m.traj) : ""} · ${m.data.n_atoms} atoms${m.data.reduced ? " of " + m.data.n_atoms_total + " (backbone and non-solvent only)" : ""} · ${m.data.frames} frame${m.data.frames === 1 ? "" : "s"} · top molecule ${m.id}` : "";
}
function setMouse(mode) {
  V.set("mouse", mode); $$("#mousemodes button").forEach(b => b.setAttribute("aria-checked", b.dataset.mode === mode)); $("#view").classList.toggle("pick", mode === "pick");
  $("#mousestat").textContent = "Mouse: " + { rotate: "Rotate", translate: "Move", scale: "Zoom", pick: "Query atom" }[mode]; store.set("mouse", mode);
  if (mode !== "pick") { V.picked = null; $("#pickinfo").hidden = true; V.dirty = true; }
}
$$("#mousemodes button").forEach(b => { b.onclick = () => setMouse(b.dataset.mode); });
function applySettings() { const s = V.settings; store.set("display", { projection: s.projection, depthcue: s.depthcue, axes: s.axes, background: s.background }); $("#view").dataset.bg = s.background; }

// animation (VMD's Animate): the top molecule's frames
function animState() { const m = V.topMol, n = m ? m.data.frames : 0; return { m, n }; }
function refreshAnim() {
  const { m, n } = animState(), bar = $("#anim"); bar.classList.toggle("off", !(m && n > 1));
  $("#slider").max = Math.max(0, n - 1); $("#slider").value = m ? m.frame : 0; $("#frame-n").max = Math.max(0, n - 1); $("#frame-n").value = m ? m.frame : 0; $("#flabel").textContent = "of " + Math.max(1, n);
}
async function gotoFrame(i) {
  const { m, n } = animState(); if (!m || n < 1) return;
  i = Math.max(0, Math.min(n - 1, Math.round(i)));
  if (!m.frames.has(i) || m.frames.get(i) === null) {
    const r = await getJSON("/api/frame?path=" + encodeURIComponent(m.path) + "&traj=" + encodeURIComponent(m.traj || "") + "&i=" + i);
    if (r.error) { toast(r.error, "err"); return; } m.frames.set(i, Float32Array.from(r.xyz));
  }
  V.setFrame(m, i, m.frames.get(i)); refreshAnim();
}
function setPlayIcon(playing) { $("#anim-play use").setAttribute("href", playing ? "#i-pause" : "#i-play"); $("#anim-play").setAttribute("aria-label", playing ? "Pause" : "Play"); }
function stopAnim() { if (S.anim.timer) { clearTimeout(S.anim.timer); S.anim.timer = null; } setPlayIcon(false); }
function playAnim(dir) {
  stopAnim(); const { m, n } = animState(); if (!m || n < 2) return; S.anim.dir = dir; setPlayIcon(true);
  const tick = async () => {
    const mm = V.topMol; if (!mm) return stopAnim(); let next = mm.frame + S.anim.dir;
    if (next >= n || next < 0) {
      if (S.anim.style === "once") return stopAnim();
      if (S.anim.style === "rock") { S.anim.dir = -S.anim.dir; next = mm.frame + S.anim.dir; } else next = next >= n ? 0 : n - 1;
    }
    await gotoFrame(next); if (S.anim.timer) S.anim.timer = setTimeout(tick, 1000 / S.anim.fps);
  };
  S.anim.timer = setTimeout(tick, 0);
}
$$("#anim [data-a]").forEach(b => b.onclick = async () => {
  const { m, n } = animState(); if (!m) return; const a = b.dataset.a;
  if (a === "play") return S.anim.timer ? stopAnim() : playAnim(1);
  if (a === "reverse") return playAnim(-1);
  stopAnim(); await gotoFrame(a === "first" ? 0 : a === "last" ? n - 1 : m.frame + (a === "next" ? 1 : -1));
});
$("#slider").oninput = e => { stopAnim(); gotoFrame(Number(e.target.value)); };
$("#frame-n").onchange = e => { stopAnim(); gotoFrame(Number(e.target.value)); };
$("#speed").oninput = e => { S.anim.fps = Number(e.target.value); $("#speed-n").textContent = S.anim.fps + "/s"; store.set("speed", S.anim.fps); };
$("#style").onchange = e => { S.anim.style = e.target.value; };

// gallery of pictures the tools made
function addFigure(rel) { if (S.figures.includes(rel)) return; S.figures.push(rel); const i = el("img"); i.src = url(rel); i.alt = rel; i.title = rel; i.onclick = () => media(rel, "image"); $("#gallery").append(i); }
function figs(paths) { const d = el("div", "figs"); for (const p of paths || []) { const i = el("img"); i.src = url(p); i.alt = p; i.title = p; i.onclick = () => media(p, "image"); d.append(i); addFigure(p); } return d; }

// ------------------------------------------------------------------------------------------------ representations (VMD's Graphics, Representations)
const PRESETS = ["all", "protein", "backbone", "sidechain", "not protein and not water", "water", "nucleic", "hydrogen"];
function fillRepOptions() {
  const st = $("#rep-style"), co = $("#rep-color"), id = $("#rep-colorid"), pre = $("#rep-presets");
  STYLES.forEach(s => st.append(new Option(s, s))); COLOR_METHODS.forEach(c => co.append(new Option(c, c))); VMD_IDS.forEach(([n], i) => id.append(new Option(`${i} ${n}`, i)));
  PRESETS.forEach(p => { const b = el("button", null, p); b.type = "button"; b.onclick = () => { $("#rep-sel").value = p; commitRep(); }; pre.append(b); });
}
function repMol() { return V.mol(Number($("#rep-mol").value)) || V.topMol; }
function svgIcon(name) {
  const ns = "http://www.w3.org/2000/svg", s = document.createElementNS(ns, "svg"), u = document.createElementNS(ns, "use"); s.setAttribute("class", "ic"); u.setAttribute("href", "#" + name); s.append(u); return s;
}
function renderReps() {
  const msel = $("#rep-mol"), keep = msel.value; msel.textContent = "";
  V.mols.forEach(m => msel.append(new Option(`${m.id}: ${m.name}`, m.id))); msel.value = keep !== "" && V.mol(Number(keep)) ? keep : (V.top != null ? V.top : "");
  const m = repMol(), list = $("#replist"); list.textContent = "";
  if (!m) { list.append(el("p", "empty", "No molecule is loaded.")); $("#repform").hidden = true; return; }
  $("#repform").hidden = false; S.repIndex = Math.min(S.repIndex, Math.max(0, m.reps.length - 1));
  m.reps.forEach((r, i) => {
    const row = el("div", "rep" + (i === S.repIndex ? " sel" : "") + (r.error ? " bad" : "")); row.setAttribute("role", "option"); row.setAttribute("aria-selected", i === S.repIndex);
    const eye = el("button", "tool icon"); eye.setAttribute("aria-label", r.shown ? "Hide this representation" : "Show this representation"); eye.append(svgIcon(r.shown ? "i-eye" : "i-eye-off"));
    eye.onclick = e => { e.stopPropagation(); V.setRep(m, i, { shown: !r.shown }); };
    row.append(eye, el("span", "sel-txt", r.sel), el("span", "tag", r.style), el("span", "tag", r.color === "ColorID" ? VMD_IDS[r.colorId % 16][0] : r.color));
    row.onclick = () => { S.repIndex = i; renderReps(); }; list.append(row);
  });
  const r = m.reps[S.repIndex];
  if (r) { $("#rep-sel").value = r.sel; $("#rep-style").value = r.style; $("#rep-color").value = r.color; $("#rep-colorid").value = r.colorId; $("#rep-id-row").hidden = r.color !== "ColorID"; $("#rep-err").textContent = r.error || ""; }
}
function commitRep() {
  const m = repMol(); if (!m || !m.reps[S.repIndex]) return;
  V.setRep(m, S.repIndex, { sel: $("#rep-sel").value.trim() || "all", style: $("#rep-style").value, color: $("#rep-color").value, colorId: Number($("#rep-colorid").value) });
}
$("#rep-mol").onchange = () => { S.repIndex = 0; renderReps(); };
$("#rep-sel").onchange = commitRep; $("#rep-sel").onkeydown = e => { if (e.key === "Enter") commitRep(); };
["#rep-style", "#rep-color", "#rep-colorid"].forEach(s => { $(s).onchange = commitRep; });
$("#rep-add").onclick = () => { const m = repMol(); if (m) { V.addRep(m, {}); S.repIndex = m.reps.length - 1; } };
$("#rep-del").onclick = () => { const m = repMol(); if (m && m.reps.length) V.deleteRep(m, S.repIndex); };
function toggleReps(force) { const w = $("#repwin"); w.hidden = force === undefined ? !w.hidden : !force; $("#reps-btn").setAttribute("aria-pressed", !w.hidden); if (!w.hidden) renderReps(); }
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
  const m = id => (id == null ? V.topMol : V.mol(id)), need = id => { const x = m(id); if (!x) clog("err", id == null ? "no molecule is loaded" : `no molecule ${id}`); return x; };
  switch (c.cmd) {
    case "help": return help();
    case "clear": return $("#consolelog").replaceChildren();
    case "files": return S.everything.forEach(f => clog("t", `${f.path}   (${f.kind})`));
    case "ask": showTab("chat"); return send(c.text);
    case "look": return look(c.tool, c.file);
    case "workflow": showTab("jobs"); return runWorkflow(c.name, c.files);
    case "mol.new": return loadMolecule(c.file);
    case "mol.addfile": return addTrajectory(c.file, c.id);
    case "mol.delete": { const x = need(c.id); if (x) { V.removeMolecule(x.id); clog("ok", `deleted molecule ${x.id}`); } return; }
    case "mol.top": return need(c.id) && V.setTop(c.id);
    case "mol.list": return V.mols.forEach(x => clog("t", `${x.id}${x.id === V.top ? " (top)" : ""}  ${x.name}  ${x.data.n_atoms} atoms  ${x.data.frames} frames  ${x.drawn ? "drawn" : "hidden"}  reps: ${x.reps.map(r => `[${r.sel} / ${r.style} / ${r.color}]`).join(" ")}`));
    case "mol.default": { const x = V.topMol; if (!x) return clog("err", "no molecule is loaded"); Object.assign(x.defaults, { ...(c.style && { style: c.style }), ...(c.color && { color: c.color }), ...(c.sel && { sel: c.sel }) }); return clog("ok", `next representation: ${x.defaults.sel} / ${x.defaults.style} / ${x.defaults.color}`); }
    case "mol.addrep": { const x = need(c.id); if (x) { V.addRep(x, {}); clog("ok", `added representation ${x.reps.length - 1}`); } return; }
    case "mol.modrep": { const x = need(c.id); if (!x) return; if (!x.reps[c.rep]) return clog("err", `molecule ${x.id} has no representation ${c.rep}`); const p = {}; for (const k of ["sel", "style", "color", "shown"]) if (k in c) p[k] = c[k]; V.setRep(x, c.rep, p); const r = x.reps[c.rep]; return r.error ? clog("err", r.error) : clog("ok", `representation ${c.rep}: ${r.sel} / ${r.style} / ${r.color}  (${r.count} atoms)`); }
    case "mol.delrep": { const x = need(c.id); if (x) V.deleteRep(x, c.rep); return; }
    case "animate.goto": stopAnim(); return gotoFrame(c.frame === Infinity ? 1e9 : c.frame);
    case "animate.forward": return playAnim(1);
    case "animate.reverse": return playAnim(-1);
    case "animate.pause": return stopAnim();
    case "animate.speed": S.anim.fps = Math.min(30, c.fps); $("#speed").value = S.anim.fps; $("#speed-n").textContent = S.anim.fps + "/s"; return;
    case "animate.style": S.anim.style = c.style; $("#style").value = c.style; return;
    case "display.projection": return V.set("projection", c.projection);
    case "display.depthcue": return V.set("depthcue", c.on);
    case "display.reset": return V.resetView();
    case "axes": return V.set("axes", c.location);
    case "background": return V.set("background", c.color);
    case "rotate": return V.rotateAbout(c.axis, c.degrees);
    case "scale": V.zoom = c.mode === "by" ? V.zoom * c.factor : c.factor; V.dirty = true; return;
  }
}
$("#conform").onsubmit = e => { e.preventDefault(); const line = $("#conin").value.trim(); $("#conin").value = ""; if (!line) return; S.history.push(line); S.histAt = S.history.length; runCommand(line); };
$("#conin").onkeydown = e => {
  if (e.key === "ArrowUp" && S.histAt > 0) { e.preventDefault(); $("#conin").value = S.history[--S.histAt]; }
  else if (e.key === "ArrowDown") { e.preventDefault(); S.histAt = Math.min(S.history.length, S.histAt + 1); $("#conin").value = S.history[S.histAt] || ""; }
};
$("#clear").onclick = () => $("#consolelog").replaceChildren();
$("#console-fold").onclick = () => { const c = $("#console"); c.classList.toggle("min"); $("#console-fold").textContent = c.classList.contains("min") ? "▴" : "▾"; document.documentElement.style.setProperty("--console", c.classList.contains("min") ? "32px" : (store.get("console", 190) + "px")); };

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
function showTab(p) { $$(".tab").forEach(t => { const on = t.dataset.p === p; t.classList.toggle("on", on); t.setAttribute("aria-selected", on); }); $$("#chat,#jobs").forEach(x => x.classList.toggle("on", x.id === p)); if (p === "chat") $("#q").focus(); }
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
      think.hidden = false; log.append(think);
    }
    else if (ev.type === "answer") {
      think.remove(); show(textBlock(), ev.text);
      log.append(el("div", "clock", ev.line)); clog("ok", ev.line); loadStatus();
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
["What is in my files?", "Has my run settled?", "Which hydrogen bonds persist?", "What can VMD do here?"].forEach(h => { const b = el("button", "hint", h); b.type = "button"; b.onclick = () => { $("#q").value = h; $("#q").focus(); }; $("#hints").append(b); });

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
act("file.save", "File", "Save picture (PNG)…", async () => { const b = await V.png(), a = el("a"); a.href = URL.createObjectURL(b); a.download = ((V.topMol && V.topMol.name) || "view").replace(/\W+/g, "_") + ".png"; a.click(); toast("Picture saved", "ok"); }, { key: "Ctrl S" });
act("file.refresh", "File", "Refresh the file list", () => { loadFiles(); loadStatus(); });
act("mol.new", "Molecule", "New molecule…", async () => { const p = await choose("New molecule: choose a structure", fileChoices("structure")); if (p) loadMolecule(p); });
act("mol.addfile", "Molecule", "Load data into the top molecule…", async () => { const p = await choose("Load a trajectory into the top molecule", fileChoices("trajectory")); if (p) addTrajectory(p); });
act("mol.delete", "Molecule", "Delete the top molecule", () => { const m = V.topMol; if (m) { V.removeMolecule(m.id); toast(`Deleted molecule ${m.id}`, ""); } }, { enabled: () => !!V.topMol });
act("mol.toggle", "Molecule", "Show or hide the top molecule", () => { const m = V.topMol; if (m) V.setDrawn(m.id, !m.drawn); }, { enabled: () => !!V.topMol });
act("mol.inspect", "Molecule", "Describe the top molecule (detect system)", () => { const m = V.topMol; if (m) look("detect_system", m.path); }, { enabled: () => !!V.topMol });
act("reps.open", "Graphics", "Representations…", () => toggleReps(true), { key: "Ctrl R" });
act("rep.add", "Graphics", "Create a representation", () => { const m = V.topMol; if (m) { V.addRep(m, {}); S.repIndex = m.reps.length - 1; toggleReps(true); } }, { enabled: () => !!V.topMol });
act("rep.delete", "Graphics", "Delete the selected representation", () => { const m = V.topMol; if (m && m.reps.length) V.deleteRep(m, S.repIndex); }, { enabled: () => !!V.topMol });
act("proj.persp", "Display", "Perspective", () => V.set("projection", "Perspective"), { checked: () => V.settings.projection === "Perspective" });
act("proj.ortho", "Display", "Orthographic", () => V.set("projection", "Orthographic"), { checked: () => V.settings.projection === "Orthographic" });
act("display.depth", "Display", "Depth cueing", () => V.set("depthcue", !V.settings.depthcue), { checked: () => V.settings.depthcue });
act("display.axes", "Display", "Axes (lower left)", () => V.set("axes", V.settings.axes === "Off" ? "LowerLeft" : "Off"), { checked: () => V.settings.axes !== "Off" });
["black", "gray", "white"].forEach(c => act("bg." + c, "Display", "Background: " + c, () => V.set("background", c), { checked: () => V.settings.background === c }));
act("view.reset", "Display", "Reset view", () => V.resetView(), { key: "=" });
act("view.fit", "Display", "Fit all drawn molecules", () => { V.fit(); V.resetView(); });
[["rotate", "Rotate", "R"], ["translate", "Move", "T"], ["scale", "Zoom", "S"], ["pick", "Query atom", "Q"]].forEach(([m, l, k]) => act("mouse." + m, "Mouse", l, () => setMouse(m), { key: k, checked: () => V.settings.mouse === m }));
act("anim.play", "Animation", "Play or pause", () => (S.anim.timer ? stopAnim() : playAnim(1)), { key: "Space" });
act("anim.next", "Animation", "Next frame", () => { const m = V.topMol; if (m) { stopAnim(); gotoFrame(m.frame + 1); } }, { key: "→" });
act("anim.prev", "Animation", "Previous frame", () => { const m = V.topMol; if (m) { stopAnim(); gotoFrame(m.frame - 1); } }, { key: "←" });
act("ext.chat", "Extensions", "Chat with the agent", () => showTab("chat"), { key: "Ctrl J" });
act("ext.jobs", "Extensions", "Whole jobs (workflows)…", () => showTab("jobs"));
act("ext.console", "Extensions", "Go to the console", () => { $("#console").classList.remove("min"); $("#conin").focus(); }, { key: "/" });
act("help.shortcuts", "Help", "Keyboard shortcuts", () => { fillShortcuts(); $("#shortcuts").showModal(); }, { key: "?" });
act("help.console", "Help", "Console commands", () => { $("#console").classList.remove("min"); help(); });
act("help.about", "Help", "About vmd-agent", () => $("#about").showModal());
const MENUS = [["File", ["file.add", "file.save", "file.refresh"]], ["Molecule", ["mol.new", "mol.addfile", "-", "mol.toggle", "mol.inspect", "-", "mol.delete"]], ["Graphics", ["reps.open", "rep.add", "rep.delete"]],
               ["Display", ["proj.persp", "proj.ortho", "-", "display.depth", "display.axes", "-", "bg.black", "bg.gray", "bg.white", "-", "view.reset", "view.fit"]], ["Mouse", ["mouse.rotate", "mouse.translate", "mouse.scale", "mouse.pick"]],
               ["Animation", ["anim.play", "anim.prev", "anim.next"]], ["Extensions", ["ext.chat", "ext.jobs", "ext.console"]], ["Help", ["help.shortcuts", "help.console", "help.about"]]];
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
$("#palette-btn").onclick = openPalette;
$("#palette").addEventListener("click", e => { if (e.target.id === "palette") $("#palette").close(); });
function fillShortcuts() {
  const t = $("#sc-table"); t.textContent = "";
  const rows = [["Ctrl K", "Search every action"], ...Object.values(A).filter(a => a.key).map(a => [a.key, a.label]), ["Shift-drag", "Move the molecule in any mouse mode"], ["Wheel", "Zoom"], ["Double-click the display", "Reset the view"], ["↑ ↓ in the console", "Earlier commands"]];
  rows.forEach(([k, d]) => { const tr = el("tr"); tr.append(el("td", null, keyText(k)), el("td", null, d)); t.append(tr); });
}
document.addEventListener("keydown", e => {
  const typing = e.target.closest && e.target.closest("input, textarea, select, [contenteditable]"), mod = e.ctrlKey || e.metaKey, key = e.key.toLowerCase();
  if (mod && key === "k") { e.preventDefault(); return openPalette(); }
  if (mod && key === "s") { e.preventDefault(); return A["file.save"].run(); }
  if (mod && key === "j") { e.preventDefault(); return A["ext.chat"].run(); }
  if (mod && key === "r") { e.preventDefault(); return A["reps.open"].run(); }
  if (e.key === "Escape") { $("#pickinfo").hidden = true; V.picked = null; V.dirty = true; }
  if (typing || mod || e.altKey || document.querySelector("dialog[open]")) return;
  const map = { r: "mouse.rotate", t: "mouse.translate", s: "mouse.scale", q: "mouse.pick", "=": "view.reset", " ": "anim.play", arrowright: "anim.next", arrowleft: "anim.prev", "?": "help.shortcuts", "/": "ext.console" };
  const id = map[key]; if (id) { e.preventDefault(); A[id].run(); }
});

// ------------------------------------------------------------------------------------------------ layout: splitters, theme
function splitter(id, opts) {
  const s = $(id); let drag = null;
  const apply = v => { v = Math.max(opts.min, Math.min(opts.max(), v)); document.documentElement.style.setProperty(opts.prop, v + "px"); if (opts.key) store.set(opts.key, v); if (V) V.dirty = true; return v; };
  const saved = opts.key ? store.get(opts.key, null) : null; if (saved) apply(saved);
  s.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, v: opts.current() }; s.setPointerCapture(e.pointerId); s.classList.add("drag"); });
  s.addEventListener("pointermove", e => { if (drag) apply(drag.v + opts.delta(e.clientX - drag.x, e.clientY - drag.y)); });
  const end = () => { drag = null; s.classList.remove("drag"); }; s.addEventListener("pointerup", end); s.addEventListener("pointercancel", end);
  s.addEventListener("keydown", e => { const step = e.shiftKey ? 48 : 16, d = { ArrowLeft: -step, ArrowUp: -step, ArrowRight: step, ArrowDown: step }[e.key]; if (d !== undefined) { e.preventDefault(); apply(opts.current() + opts.delta(d, d)); } });
  s.addEventListener("dblclick", () => { document.documentElement.style.removeProperty(opts.prop); if (opts.key) store.set(opts.key, null); });
}
function theme(mode) {
  const root = document.documentElement; if (mode === "auto") root.removeAttribute("data-theme"); else root.dataset.theme = mode; store.set("theme", mode);
  $("#theme").title = "Colour theme: " + mode + " (click to change)";
}
$("#theme").onclick = () => theme({ auto: "light", light: "dark", dark: "auto" }[store.get("theme", "auto")]);

// ------------------------------------------------------------------------------------------------ start up
V = new Viewer($("#view"));
V.onchange = kind => {
  if (kind === "settings") applySettings();
  renderMolecules(); updateCaption(); refreshAnim(); if (!$("#repwin").hidden) renderReps();
};
V.onpick = info => { const box = $("#pickinfo"); box.hidden = !info; if (info) { box.replaceChildren(); box.append(el("b", null, `${info.molName} #${info.mol}`), document.createTextNode(`  ${info.resname}${info.resid}:${info.name}  index ${info.index}  ${info.element}  chain ${info.chain}  (${info.x.toFixed(2)}, ${info.y.toFixed(2)}, ${info.z.toFixed(2)})`)); clog("t", `picked ${info.molName} ${info.resname}${info.resid} ${info.name} (index ${info.index})`); } };
const savedDisplay = store.get("display", null); if (savedDisplay) Object.assign(V.settings, savedDisplay);
S.anim.fps = store.get("speed", 8); $("#speed").value = S.anim.fps; $("#speed-n").textContent = S.anim.fps + "/s";
fillRepOptions(); buildMenus(); applySettings(); setMouse(store.get("mouse", "rotate")); theme(store.get("theme", "auto"));
splitter("#split-left", { prop: "--left", key: "left", min: 220, max: () => innerWidth * 0.45, current: () => $("#left").getBoundingClientRect().width, delta: dx => dx });
splitter("#split-right", { prop: "--right", key: "right", min: 300, max: () => innerWidth * 0.55, current: () => $("#right").getBoundingClientRect().width, delta: dx => -dx });
splitter("#split-console", { prop: "--console", key: "console", min: 40, max: () => innerHeight * 0.6, current: () => $("#console").getBoundingClientRect().height, delta: (dx, dy) => -dy });
splitter("#split-mol", { prop: "--molrows", key: "molrows", min: 90, max: () => innerHeight * 0.6, current: () => $("#molpane").getBoundingClientRect().height, delta: (dx, dy) => dy });
$("#mol-load").onclick = () => A["mol.new"].run(); $("#mol-delete").onclick = () => A["mol.delete"].run();
renderMolecules(); refreshAnim(); updateCaption();
clog("job", "vmd-agent ready. Type help for the console commands, or press Ctrl+K to search every action.");
loadFiles().then(() => { const s = S.everything.filter(f => f.kind === "structure"); if (s.length === 1 && !V.mols.length) loadMolecule(s[0].path); });
loadWorkflows(); loadStatus();
setInterval(() => { if (!S.busy) loadFiles(); }, 15000);
