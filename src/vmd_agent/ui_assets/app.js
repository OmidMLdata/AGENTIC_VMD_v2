"use strict";
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const fmt = s => s < 10 ? s.toFixed(2) + " s" : s < 100 ? s.toFixed(1) + " s" : Math.round(s) + " s";
const size = n => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB";
const url = rel => "/files/" + rel.split("/").map(encodeURIComponent).join("/");
const api = (p, body) => fetch(p, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const getJSON = async p => (await api(p)).json();

const S = { files: [], everything: [], open: new Set(), selected: null, top: null, traj: null, status: {}, busy: false, figures: [], mol: null, playing: null };
let viewer;

// ------------------------------------------------------------------------------------------ console
function clog(cls, text) {
  const box = $("#consolelog"), row = el("div"), t = new Date().toTimeString().slice(0, 8);
  row.append(el("span", "t", t + "  "), el("span", cls, text));
  box.append(row); box.scrollTop = box.scrollHeight;
  while (box.childNodes.length > 400) box.removeChild(box.firstChild);
}
function totals(c) {
  if (!c) return;
  $("#totals").textContent = `session ${fmt(c.wall_s)}  model ${fmt(c.model_s)} in ${c.model_calls} calls  tools ${fmt(c.tool_s)} in ${c.tool_calls.length} calls`;
}

// ------------------------------------------------------------------------------------------- status
function dot(cls, label, value) { const s = el("span"); s.append(el("span", "dot " + cls), document.createTextNode(label + " "), el("b", null, value)); return s; }
async function loadStatus() {
  const s = S.status = await getJSON("/api/status");
  $("#ver").textContent = "v" + s.version;
  const left = $("#statusleft"); left.textContent = "";
  left.append(dot(s.model_ready ? "ok" : "bad", "model", s.model), dot(s.vmd ? "ok" : "warn", "VMD", s.vmd ? (s.vmd_version || "found") : "not found"),
              dot(s.ffmpeg ? "ok" : "warn", "ffmpeg", s.ffmpeg ? "ready" : "missing"));
  $("#folder").textContent = s.data_dir; $("#folder").title = s.data_dir;
  const sel = $("#profile"); sel.textContent = "";
  for (const [k, n] of Object.entries(s.profiles)) sel.append(new Option(n ? `${k} (${n})` : `${k} (fits the question)`, k));
  sel.value = s.profile;
  $("#banner").textContent = "";
  if (!s.model_ready) $("#banner").append(el("div", "banner", "The chat needs a model and none answers right now: " + (s.model_problem || "") +
    "  Viewing, files and whole jobs work without one. Run `vmd-agent setup` to choose a model."));
  totals(s.clock);
}
$("#profile").onchange = async e => {
  const r = await api("/api/profile", { tools: e.target.value });
  if (r.ok) { $("#log").textContent = ""; clog("job", `the chat now offers the "${e.target.value}" tools`); loadStatus(); } else { alert((await r.json()).error); loadStatus(); }
};

// ---------------------------------------------------------------------------------- molecules (files)
const KIND = { structure: "PDB", trajectory: "TRJ", image: "IMG", video: "MP4", map: "MAP", report: "DOC", data: "JSON", script: "TCL", other: "—" };
async function fill(box, dir, depth) {
  const r = await getJSON("/api/files" + (dir ? "?dir=" + encodeURIComponent(dir) : ""));
  if (!dir) S.everything = r.everything || [];
  for (const d of r.folders) {
    const row = el("div", "mol folder"); row.style.paddingLeft = (10 + depth * 14) + "px";
    row.append(el("span"), el("span", "flag", S.open.has(d.path) ? "−" : "+"), el("span", "nm", d.path.split("/").pop() + "/"), el("span", "meta", d.n_files + " files"));
    row.onclick = () => { S.open.has(d.path) ? S.open.delete(d.path) : S.open.add(d.path); loadFiles(); };
    const inner = el("div"); box.append(row, inner);
    if (S.open.has(d.path)) await fill(inner, d.path, depth + 1);
  }
  r.files.forEach(f => {
    const row = el("div", "mol" + (f.path === S.selected ? " sel" : "")); row.style.paddingLeft = (10 + depth * 14) + "px";
    const isTop = f.path === S.top;
    row.append(el("span", "flag" + (isTop ? " on" : ""), isTop ? "T" : ""), el("span", "k " + f.kind, KIND[f.kind] || "—"), el("span", "nm", f.path.split("/").pop()), el("span", "meta", size(f.size)));
    row.title = f.path + "  (double-click to draw)";
    row.onclick = () => select(f); row.ondblclick = () => draw(f);
    box.append(row);
  });
  return r;
}
async function loadFiles() {
  const fresh = el("div"), r = await fill(fresh, "", 0), box = $("#files");
  box.textContent = ""; box.append(fresh);
  if (!r.files.length && !r.folders.length) box.append(el("div", "empty", "No files yet. Drop a structure (.pdb) and a trajectory (.dcd) here, or put them in this folder on your computer."));
  fillWorkflowFiles();
}
function partnerStructure(f) {
  const stem = f.path.replace(/\.[^.]+$/, ""), s = S.everything.filter(x => x.kind === "structure");
  return (s.find(x => x.path.replace(/\.[^.]+$/, "") === stem) || s.find(x => x.path === S.top) || (s.length === 1 ? s[0] : null));
}
function select(f) {
  S.selected = f.path; loadFiles();
  const box = $("#info"); box.hidden = false; box.textContent = "";
  box.append(el("h3", null, f.path));
  const dl = el("dl"); [["kind", f.kind], ["size", size(f.size)]].forEach(([k, v]) => dl.append(el("dt", null, k), el("dd", null, v))); box.append(dl);
  const row = el("div", "row"), out = el("div");
  const b = (label, fn) => { const x = el("button", "btn small", label); x.onclick = fn; row.append(x); return x; };
  if (["structure", "trajectory", "image", "video"].includes(f.kind)) b("Draw", () => draw(f));
  const looks = f.kind === "structure" || f.kind === "trajectory" ? ["inspect_files", "detect_system", "structure_stats"] : f.kind === "video" ? ["probe_video"] : [];
  for (const t of looks) b(t.replace(/_/g, " "), async x => {
    clog("job", "▸ " + t + " " + f.path); out.textContent = "…";
    const r = await (await api("/api/look", { tool: t, path: f.path })).json();
    clog(r.result && r.result.error ? "err" : "ok", `${r.result && r.result.error ? "✗" : "✓"} ${t}  ${fmt(r.seconds || 0)}`);
    out.textContent = ""; out.append(el("pre", "look", JSON.stringify(r.result || r, null, 1).slice(0, 5000)));
  });
  if (f.kind === "structure" || f.kind === "trajectory") b("Ask about it", () => { $("#q").value = "What is in " + f.path + "?"; showTab("chat"); $("#q").focus(); });
  box.append(row, out);
}

// ----------------------------------------------------------------------------------------- display
function media(rel, kind) {
  const m = $("#media"); m.textContent = ""; m.classList.add("on");
  const node = el(kind === "video" ? "video" : "img"); node.src = url(rel); if (kind === "video") node.controls = true;
  m.append(node); $("#caption").textContent = rel; $("#frames").classList.remove("on"); $("#nodata").hidden = true;
  const back = el("button", "btn small", "Back to 3D"); back.style.position = "absolute"; back.style.top = "10px"; back.style.right = "10px";
  back.onclick = () => { m.classList.remove("on"); $("#caption").textContent = S.mol ? S.top : ""; showFrames(); $("#nodata").hidden = !!S.mol; };
  m.append(back);
}
async function draw(f) {
  if (f.kind === "image" || f.kind === "video") return media(f.path, f.kind);
  let top = f, traj = null;
  if (f.kind === "trajectory") { top = partnerStructure(f); traj = f.path; if (!top) { clog("err", "no structure to go with " + f.path); alert("Pick the structure for this trajectory first (double-click a .pdb or .psf)."); return; } top = { path: top.path }; }
  else if (f.kind === "structure") { const t = S.everything.find(x => x.kind === "trajectory" && x.path.replace(/\.[^.]+$/, "") === f.path.replace(/\.[^.]+$/, "")); traj = t ? t.path : null; }
  else return;
  const t0 = performance.now();
  clog("job", `▸ drawing ${top.path}${traj ? " with " + traj : ""}`);
  $("#nodata").hidden = true; $("#media").classList.remove("on");
  const r = await api("/api/structure?path=" + encodeURIComponent(top.path) + (traj ? "&traj=" + encodeURIComponent(traj) : ""));
  const mol = await r.json();
  if (mol.error) { clog("err", "✗ " + mol.error); $("#nodata").hidden = false; $("#nodata").lastChild.textContent = mol.error; return; }
  S.mol = mol; S.top = top.path; S.traj = traj; stop(); viewer.load(mol);
  $("#caption").textContent = `${top.path}${traj ? " + " + traj.split("/").pop() : ""}   ${mol.n_atoms} atoms${mol.reduced ? " of " + mol.n_atoms_total + " (backbone and non-solvent only)" : ""}   ${mol.frames} frame${mol.frames === 1 ? "" : "s"}`;
  showFrames(); loadFiles();
  clog("ok", `✓ drawn ${mol.n_atoms} atoms, ${mol.bonds.length} bonds, ${mol.frames} frames  ${fmt((performance.now() - t0) / 1000)}`);
}
function showFrames() {
  const on = S.mol && S.mol.frames > 1; $("#frames").classList.toggle("on", !!on);
  if (on) { const sl = $("#slider"); sl.max = S.mol.frames - 1; sl.value = viewer.frame; $("#flabel").textContent = `frame ${viewer.frame + 1} / ${S.mol.frames}`; }
}
async function gotoFrame(i) {
  i = Math.max(0, Math.min(S.mol.frames - 1, i));
  if (!viewer.frames.has(i)) { const q = "/api/frame?path=" + encodeURIComponent(S.top) + "&traj=" + encodeURIComponent(S.traj || "") + "&i=" + i; const r = await getJSON(q); viewer.frames.set(i, Float32Array.from(r.xyz)); }
  viewer.setFrame(i, viewer.frames.get(i)); $("#slider").value = i; $("#flabel").textContent = `frame ${i + 1} / ${S.mol.frames}`;
}
function stop() { if (S.playing) { clearInterval(S.playing); S.playing = null; $("#play").textContent = "▶"; } }
$("#play").onclick = () => {
  if (S.playing) return stop();
  $("#play").textContent = "❚❚";
  S.playing = setInterval(() => gotoFrame((viewer.frame + 1) % S.mol.frames), 1000 / Number($("#fps").value));
};
$("#fps").onchange = () => { if (S.playing) { stop(); $("#play").click(); } };
$("#slider").oninput = e => { stop(); gotoFrame(Number(e.target.value)); };
$("#rep").onchange = e => { viewer.rep = e.target.value; viewer.dirty = true; };
$("#color").onchange = e => { viewer.color = e.target.value; viewer.dirty = true; };
["protein", "other", "water"].forEach(k => { $("#show-" + k).onchange = e => { viewer.show[k] = e.target.checked; viewer.dirty = true; }; });
$("#reset").onclick = () => viewer.reset();
$("#snap").onclick = async () => { const b = await viewer.png(), a = el("a"); a.href = URL.createObjectURL(b); a.download = (S.top || "view").replace(/\W+/g, "_") + ".png"; a.click(); };
function addFigure(rel) {
  if (S.figures.includes(rel)) return; S.figures.push(rel);
  const i = el("img"); i.src = url(rel); i.title = rel; i.onclick = () => media(rel, "image"); $("#gallery").append(i);
}
function figs(paths) { const d = el("div", "figs"); for (const p of paths || []) { const i = el("img"); i.src = url(p); i.title = p; i.onclick = () => media(p, "image"); d.append(i); addFigure(p); } return d; }

// ---------------------------------------------------------------------------------------- uploads
const drop = $("#drop");
async function upload(list) { for (const f of list) { const r = await fetch("/api/upload?name=" + encodeURIComponent(f.name), { method: "POST", body: f }); const j = await r.json(); j.error ? alert(f.name + ": " + j.error) : clog("ok", "✓ added " + j.path); } loadFiles(); }
drop.onclick = () => $("#pick").click();
$("#pick").onchange = e => upload([...e.target.files]);
["dragenter", "dragover"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => upload([...e.dataTransfer.files]));

// ------------------------------------------------------------------------------------ server events
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
function showTab(p) { document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.dataset.p === p)); document.querySelectorAll("#chat,#jobs").forEach(x => x.classList.toggle("on", x.id === p)); }
document.querySelectorAll(".tab").forEach(t => t.onclick = () => showTab(t.dataset.p));

// -------------------------------------------------------------------------------------------- chat
const log = $("#log"), scroller = $("#scroll");
const toBottom = () => { scroller.scrollTop = scroller.scrollHeight; };
async function send(text) {
  if (S.busy || !text.trim()) return;
  S.busy = true; $("#send").disabled = true; $("#q").value = ""; autosize();
  log.append(el("div", "msg me", text)); clog("job", "? " + text);
  const think = el("div", "think"); think.append(document.createTextNode("the model is working"), el("span", "dots")); log.append(think);
  const running = new Set(); let current = null, block = null, said = "";
  const place = node => log.insertBefore(node, think.isConnected ? think : null);
  const textBlock = () => { if (!block) { block = el("div", "msg ai"); place(block); said = ""; } return block; };
  const ticker = setInterval(() => { for (const t of running) t.sec.textContent = fmt((performance.now() - t.t) / 1000); }, 200);
  await stream("/api/chat", { message: text }, ev => {
    if (ev.type === "token") { think.hidden = true; said += ev.text; textBlock().textContent = said; }
    else if (ev.type === "model_start") { think.hidden = false; log.append(think); }
    else if (ev.type === "model_end") { think.hidden = true; place(el("div", "mline", "model call " + fmt(ev.seconds))); clog("mod", "model call " + fmt(ev.seconds)); }
    else if (ev.type === "tool_start") {
      think.hidden = true; block = null;
      const box = el("div", "tool run"), head = el("div", "head"), sec = el("span", "sec", "0.00 s"), args = el("div", "args", Object.entries(ev.args || {}).map(([k, v]) => k + "=" + v).join("  "));
      head.append(el("span", "name", ev.name), sec); head.onclick = () => box.classList.toggle("open");
      const prog = el("div", "prog"), bar = el("div", "bar"); bar.append(el("div")); bar.hidden = true;
      box.append(head, args, prog, bar); place(box);
      current = { box, sec, prog, bar, name: ev.name, t: performance.now() }; running.add(current); clog("job", "▸ " + ev.name + "  " + Object.entries(ev.args || {}).map(([k, v]) => k + "=" + v).join(" ").slice(0, 160));
    }
    else if (ev.type === "tool_progress" && current) {
      current.prog.textContent = ev.text; if (ev.fraction != null) { current.bar.hidden = false; current.bar.firstChild.style.width = Math.round(ev.fraction * 100) + "%"; }
    }
    else if (ev.type === "tool_end" && current) {
      running.delete(current); current.box.classList.remove("run"); current.sec.textContent = fmt(ev.seconds); current.bar.hidden = true;
      if (ev.error) { current.box.classList.add("err"); current.prog.textContent = ev.error; }
      if (ev.images && ev.images.length) current.box.append(figs(ev.images));
      clog(ev.error ? "err" : "ok", `${ev.error ? "✗" : "✓"} ${ev.name}  ${fmt(ev.seconds)}${ev.error ? "  " + ev.error.slice(0, 120) : ""}`);
      think.hidden = false; log.append(think);
    }
    else if (ev.type === "answer") {
      think.remove(); if (!block || !ev.streamed || ev.text !== said) textBlock().textContent = ev.text;
      log.append(el("div", "clock", ev.line)); clog("ok", ev.line); loadStatus();
    }
    else if (ev.type === "error") { think.remove(); textBlock().textContent = "Something went wrong: " + ev.text; clog("err", "✗ " + ev.text); }
    toBottom();
  });
  clearInterval(ticker); think.remove(); S.busy = false; $("#send").disabled = false; $("#q").focus(); loadFiles();
}
const autosize = () => { const q = $("#q"); q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 140) + "px"; };
$("#q").addEventListener("input", autosize);
$("#q").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send($("#q").value); } });
$("#send").onclick = () => send($("#q").value);
$("#new").onclick = async () => { await api("/api/reset", {}); log.textContent = ""; clog("job", "new conversation"); loadStatus(); };
["What is in my files?", "Has my run settled?", "Which hydrogen bonds persist?", "What can VMD do here?"].forEach(h => { const b = el("button", "hint", h); b.onclick = () => { $("#q").value = h; $("#q").focus(); }; $("#hints").append(b); });

// ---------------------------------------------------------------------------------------- whole jobs
let workflows = {};
function fillWorkflowFiles() { if ($("#wfname")) renderSlots(); }
async function loadWorkflows() {
  workflows = (await getJSON("/api/workflows")).workflows || {};
  const box = $("#wf"); box.textContent = "";
  box.append(el("div", "does", "A whole job runs several tools in a fixed order, grades what it finds, and writes a report you can send to someone. No model is involved."));
  box.append(el("label", null, "Job")); const sel = el("select"); sel.id = "wfname";
  for (const k of Object.keys(workflows)) sel.append(new Option(k.replace(/_/g, " "), k));
  const why = el("div", "does"); why.id = "wfdoes"; sel.onchange = renderSlots; box.append(sel, why, el("div")); box.lastChild.id = "slots";
  const run = el("button", "btn primary", "Run"); run.id = "runwf"; run.style.marginTop = "12px"; run.onclick = runWorkflow; box.append(run, el("div")); box.lastChild.id = "wfout";
  renderSlots();
}
function renderSlots() {
  const w = workflows[$("#wfname").value]; if (!w) return;
  $("#wfdoes").textContent = w.does + (w.needs_vmd ? " (needs VMD)" : "");
  const box = $("#slots"), old = [...box.querySelectorAll("select")].map(s => s.value); box.textContent = "";
  w.files.forEach((slot, i) => {
    box.append(el("label", null, slot.replace(/_/g, " "))); const s = el("select"); s.dataset.slot = i;
    const want = /traj/.test(slot) ? "trajectory" : /map/.test(slot) ? "map" : "structure";
    for (const f of S.everything.filter(f => f.kind === want)) s.append(new Option(f.path, f.path));
    if (old[i]) s.value = old[i]; else if (want === "structure" && S.top) s.value = S.top; box.append(s);
  });
}
async function runWorkflow() {
  if (S.busy) return; S.busy = true;
  const name = $("#wfname").value, chosen = [...document.querySelectorAll("#slots select")].map(s => s.value), out = $("#wfout"); out.textContent = ""; $("#runwf").disabled = true;
  if (chosen.some(c => !c)) { out.append(el("div", "banner", "Pick a file for each line first (add files on the left).")); S.busy = false; $("#runwf").disabled = false; return; }
  const prog = el("div", "prog", "starting…"), bar = el("div", "bar"); bar.append(el("div")); bar.hidden = true; out.append(prog, bar);
  clog("job", `▸ workflow ${name}  ${chosen.join(" ")}`);
  await stream("/api/workflow", { name, files: chosen }, ev => {
    if (ev.type === "tool_progress") { prog.textContent = ev.text; clog("job", "  " + ev.text); if (ev.fraction != null) { bar.hidden = false; bar.firstChild.style.width = Math.round(ev.fraction * 100) + "%"; } }
    else if (ev.type === "error") { out.append(el("div", "banner", "Something went wrong: " + ev.text)); clog("err", "✗ " + ev.text); }
    else if (ev.type === "workflow") {
      prog.remove(); bar.remove(); const r = ev.result;
      if (r.error) { out.append(el("div", "banner", r.error)); clog("err", "✗ " + r.error); return; }
      out.append(el("div", "verdict", r.verdict), el("div", "clock", "the whole job took " + fmt(ev.seconds))); clog("ok", `✓ workflow ${name}  ${fmt(ev.seconds)}`);
      for (const f of r.findings || []) { const row = el("div", "finding"); row.append(el("span", "badge " + f.level, f.level), el("span", null, f.text)); out.append(row); }
      const t = el("table", "steps"); const hr = el("tr"); ["#", "step", "tool", "seconds"].forEach(h => hr.append(el("th", null, h))); t.append(hr);
      for (const s of r.steps || []) { const tr = el("tr"); tr.append(el("td", null, s.n), el("td", null, s.label + (s.ok ? "" : "  (failed)")), el("td", null, s.tool), el("td", null, Number(s.seconds).toFixed(2))); t.append(tr); clog(s.ok ? "ok" : "err", `  ${s.ok ? "✓" : "✗"} ${s.tool}  ${Number(s.seconds).toFixed(2)} s  ${s.label}`); }
      out.append(t, figs(ev.images));
      if (ev.report_html) { const a = el("a", null, "Open the report (report.html)"); a.href = url(ev.report_html); a.target = "_blank"; const d = el("div"); d.style.marginTop = "10px"; d.append(a); out.append(d); }
      loadFiles();
    }
  });
  S.busy = false; $("#runwf").disabled = false;
}

// -------------------------------------------------------------------------------------- start up
const root = document.documentElement;
try { const t = localStorage.getItem("vmd-theme"); if (t) root.dataset.theme = t; } catch (e) { /* storage may be blocked */ }
$("#theme").onclick = () => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark"; try { localStorage.setItem("vmd-theme", root.dataset.theme); } catch (e) { /* ignore */ }
};
$("#console > header").onclick = e => { if (e.target.id !== "clear") $("#console").classList.toggle("min"); };
$("#clear").onclick = () => { $("#consolelog").textContent = ""; };
viewer = new Viewer($("#view"));
clog("job", "vmd-agent ready");
loadFiles().then(async () => { const s = S.everything.filter(f => f.kind === "structure"); if (s.length === 1) draw(s[0]); });
loadWorkflows(); loadStatus();
setInterval(() => { if (!S.busy) loadFiles(); }, 10000);
