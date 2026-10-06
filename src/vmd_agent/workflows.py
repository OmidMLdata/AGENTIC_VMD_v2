"""Named multi-step workflows: the things a person does in a fixed order, run as one job with progress and a report.

Each workflow calls ordinary tools (the same ones the chat and the commands use), turns their results into plain
*findings* (ok / note / warning / problem), gives a verdict, and writes a report (see :mod:`vmd_agent.reporting`). Nothing is
decided by a language model: the findings come from the tools' own numbers and wording. A step that needs VMD is skipped, and
reported as skipped, when there is no VMD.

Workflows (``vmd-agent workflow``): structure_overview, equilibration_check, interaction_report, compare_runs,
prepare_simulation, cryoem_fit.
"""
from __future__ import annotations

import os
import time
from typing import Callable, Dict, List, Optional

from vmd_agent import progress, reporting, security, toolset
from vmd_agent.toolset import _p, tool

LEVELS = ("ok", "note", "warning", "problem")


class _Run:
    """The record of one workflow run: steps, findings, figures, scripts."""

    def __init__(self, name: str, title: str, question: str, params: dict, inputs: List[str], total: int):
        self.d: Dict[str, object] = {"workflow": name, "title": title, "question": question, "params": params, "steps": [],
                                     "findings": [], "figures": [], "scripts": [], "inputs": inputs}
        self.total = total
        self.results: Dict[str, dict] = {}

    def step(self, tool_name: str, label: str, **kwargs) -> dict:
        n = len(self.d["steps"]) + 1                                   # type: ignore[arg-type]
        progress.report(f"step {n} of {self.total}: {label}")
        t0 = time.time()
        try:
            result = toolset.TOOLS[tool_name](**kwargs)
        except Exception as e:                                         # noqa: BLE001 - a step must not kill the run
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        ok = not (isinstance(result, dict) and result.get("ok") is False)
        err = str(result.get("error", "")) if isinstance(result, dict) else ""
        skipped = (not ok) and err.startswith("VMD not found")
        self.d["steps"].append({                                       # type: ignore[union-attr]
            "n": n, "tool": tool_name, "label": label, "ok": ok, "seconds": time.time() - t0,
            "summary": reporting.summarize(result) if ok else {}, "error": err, "skipped": skipped,
            "engine": result.get("engine") if isinstance(result, dict) else None, "caveats": reporting.caveats(result) if ok else []})
        if isinstance(result, dict):
            if result.get("reproduce_script"):
                self.d["scripts"].append(result["reproduce_script"])   # type: ignore[union-attr]
        if skipped:
            self.finding("note", f"skipped '{label}': it needs VMD, which was not found.", n)
        elif not ok:
            self.finding("problem", f"'{label}' failed: {err[:200] or 'no reason given'}", n)
        self.results[label] = result if isinstance(result, dict) else {}
        return self.results[label]

    def finding(self, level: str, text: str, step: Optional[int] = None) -> None:
        assert level in LEVELS
        self.d["findings"].append({"level": level, "text": text, "step": step})   # type: ignore[union-attr]

    def figure(self, path: Optional[str]) -> None:
        if path and os.path.isfile(path):
            self.d["figures"].append(path)                              # type: ignore[union-attr]

    def finish(self, verdict: str, out_dir: str, rerun: str) -> dict:
        self.d["verdict"] = verdict
        self.d["rerun"] = rerun
        written = reporting.write_report(self.d, out_dir)
        counts = {lv: sum(1 for f in self.d["findings"] if f["level"] == lv) for lv in LEVELS}   # type: ignore[union-attr]
        return {"ok": True, "workflow": self.d["workflow"], "verdict": verdict, "findings": self.d["findings"],
                "finding_counts": counts, "steps": [{k: s[k] for k in ("n", "tool", "label", "ok", "seconds", "summary")}
                                                    for s in self.d["steps"]],   # type: ignore[union-attr]
                "report": os.path.abspath(written["report_md"]), "report_html": os.path.abspath(written["report_html"]),
                "out_dir": os.path.abspath(out_dir)}

    def worst(self) -> str:
        found = {f["level"] for f in self.d["findings"]}                # type: ignore[union-attr]
        return next((lv for lv in ("problem", "warning", "note") if lv in found), "ok")


def _verdict(run: _Run, good: str) -> str:
    worst = run.worst()
    n = {lv: sum(1 for f in run.d["findings"] if f["level"] == lv) for lv in LEVELS}   # type: ignore[union-attr]
    if worst == "problem":
        return f"{n['problem']} problem(s) and {n['warning']} warning(s) found: read the findings before using this."
    if worst == "warning":
        return f"{good}, with {n['warning']} warning(s) worth a look."
    return good + "."


# ---------------------------------------------------------------- the workflows
def structure_overview(structure: str, out_dir: str, options: dict) -> dict:
    run = _Run("structure_overview", "Structure overview", "What is this structure, and is it in good shape?",
               {"structure": os.path.basename(structure)}, [structure], 6)
    run.step("inspect_files", "classify the file", paths=[structure])
    det = run.step("detect_system", "find what is in it", topology=structure)
    stats = run.step("structure_stats", "count bonds, disulfides, H-bonds, secondary structure", topology=structure)
    tors = run.step("vmd_backbone_torsions", "check the backbone torsions", topology=structure)
    chk = run.step("vmd_structure_check", "check chirality, cis peptides, chain gaps", topology=structure)
    vis = run.step("visualize_and_interpret", "draw it", topology=structure, out_dir=os.path.join(out_dir, "views"),
                   views=["front", "side"], renderer=options.get("renderer", "auto"))
    for p in (vis.get("images") or {}).values():
        run.figure(p)
    comp = det.get("components", {}) if det else {}
    if det.get("ok", True) is not False:
        run.finding("note", f"system type: {det.get('system_type')}; {det.get('n_atoms')} atoms.")
        for k, v in comp.items():
            if isinstance(v, dict) and v.get("n_atoms"):
                run.finding("note", f"{k}: {v.get('n_atoms')} atoms" + (f", {v['n_residues']} residues" if v.get("n_residues") else ""))
        for w in det.get("warnings", []) or []:
            run.finding("warning", str(w))
    if stats.get("n_disulfide_bridges"):
        run.finding("note", f"{stats['n_disulfide_bridges']} disulfide bridge(s).")
    if tors.get("ok") and tors.get("n_residues"):
        frac = tors["fraction_favoured"]
        out = tors.get("outliers") or []
        lvl = "warning" if frac < 0.75 or out else "ok"          # the regions are coarse boxes: a well-refined protein scores about 85-95%
        run.finding(lvl, f"{frac:.0%} of residues are in favoured Ramachandran regions (coarse boxes)"
                         + (f"; outliers: {', '.join(str(o['resid']) for o in out[:8])}" if out else "."))
    if chk.get("ok"):
        for key, what in (("chirality_errors", "chirality error(s)"), ("cis_peptides", "cis peptide bond(s)"), ("chain_gaps", "chain gap(s)")):
            if chk.get(key):
                run.finding("warning", f"{chk[key]} {what}.")
        if not any(chk.get(k) for k in ("chirality_errors", "cis_peptides", "chain_gaps")):
            run.finding("ok", "no chirality errors, cis peptides or chain gaps.")
    return run.finish(_verdict(run, "Looks like a normal structure"), out_dir, f"vmd-agent workflow structure_overview {structure}")


def equilibration_check(topology: str, trajectory: str, out_dir: str, options: dict) -> dict:
    sel = options.get("selection", "protein")
    run = _Run("equilibration_check", "Has the run settled?", "Has this simulation equilibrated, and is the data trustworthy?",
               {"topology": os.path.basename(topology), "trajectory": os.path.basename(trajectory), "selection": sel},
               [topology, trajectory], 4)
    run.step("inspect_files", "classify the files", paths=[topology, trajectory])
    an = run.step("analyze_trajectory", "RMSD, radius of gyration, convergence tests", topology=topology, trajectory=trajectory,
                  analyses=["rmsd", "rgyr", "convergence"], selection=sel, out_dir=os.path.join(out_dir, "analysis"))
    box = run.step("vmd_pbc_info", "periodic box over time", topology=topology, trajectory=trajectory, step=max(1, int(options.get("step", 1))))
    vrms = run.step("vmd_measure", "RMSD again, with VMD (cross-check)", topology=topology, trajectory=trajectory, kind="rmsd",
                    selection=sel, mass_weighted=False)
    res = an.get("results", {}) if an.get("ok", True) is not False else {}
    for key, name in (("rmsd", "RMSD"), ("rgyr", "Radius of gyration")):
        r = res.get(key) or {}
        if r.get("interpretation"):
            run.finding("note", f"{name}: {r['interpretation']}")
        if r.get("plot"):
            run.figure(r["plot"])
    drift = (res.get("rgyr") or {}).get("start_vs_end", {})
    if drift.get("significant"):
        run.finding("warning", "the radius of gyration changed significantly between the start and the end of the run.")
    pbc = an.get("pbc") or {}
    if pbc.get("n_jump_frames") or pbc.get("n_split_frames"):
        run.finding("warning", f"the molecule is split across the periodic box in {pbc.get('n_split_frames', 0)} frame(s) "
                               "(and jumps in {0}): unwrap or re-centre before trusting distances.".format(pbc.get("n_jump_frames", 0)))
    if box.get("ok") and box.get("has_unit_cell") and box.get("volume_change_fraction") is not None:
        frac = box["volume_change_fraction"]
        run.finding("warning" if frac > 0.02 else "ok", f"the box volume changes by {frac:.2%} over the run" + (
            " (more than 2%: the system may still be compressing)." if frac > 0.02 else "."))
    elif box.get("ok") and not box.get("has_unit_cell"):
        run.finding("note", "the trajectory has no periodic box information.")
    mine = ((res.get("rmsd") or {}).get("summary") or {}).get("mean")
    theirs = (vrms.get("summary") or {}).get("mean") if vrms.get("ok") else None
    if mine and theirs:
        agree = abs(mine - theirs) / max(mine, theirs) < 0.02
        run.finding("ok" if agree else "warning", f"two independent engines measured the RMSD of '{sel}' to the first frame: the toolkit "
                    f"{mine:.3f} A and VMD {theirs:.3f} A" + (": they agree." if agree else ": they differ by more than 2%, so check "
                    "the selection, the mass weighting and the reference frame."))
    for c in an.get("notes", []) or []:
        run.finding("note", str(c))
    return run.finish(_verdict(run, "No problem found with the run's data; the convergence tests found no drift in the window sampled"),
                      out_dir, f"vmd-agent workflow equilibration_check {topology} {trajectory}")


def interaction_report(topology: str, trajectory: str, out_dir: str, options: dict) -> dict:
    sel, partner = options.get("selection", "protein"), options.get("partner")
    run = _Run("interaction_report", "Interactions over the run", "Which interactions are stable, and which come and go?",
               {"topology": os.path.basename(topology), "trajectory": os.path.basename(trajectory), "selection": sel,
                "partner": partner or "-"}, [topology, trajectory], 4 if partner else 2)
    step = max(1, int(options.get("step", 1)))
    hb = run.step("vmd_interactions", "hydrogen bonds", topology=topology, trajectory=trajectory, kind="hbonds", selection=sel, step=step)
    sb = run.step("vmd_interactions", "salt bridges", topology=topology, trajectory=trajectory, kind="salt_bridges", selection=sel, step=step)
    rows: Dict[str, dict] = {"hydrogen bonds": hb, "salt bridges": sb}
    if partner:
        rows["contacts with " + partner] = run.step("vmd_interactions", f"contacts between '{sel}' and '{partner}'", topology=topology,
                                                    trajectory=trajectory, kind="contacts", selection=sel, selection2=partner, step=step)
        run.step("vmd_measure", f"surface area of '{partner}' over time", topology=topology, trajectory=trajectory, kind="sasa",
                 selection=partner, step=step)
    for name, r in rows.items():
        if not r.get("ok"):
            continue
        pairs = [p for p in (r.get("most_persistent") or []) if not (name.startswith("contacts") and p["a"] == p["b"])]
        stable = [p for p in pairs if p["occupancy"] >= 0.8]
        transient = [p for p in pairs if p["occupancy"] < 0.2]
        run.finding("note", f"{name}: {r['n_pairs_ever']} distinct pair(s) seen in {r['n_frames']} frames; "
                            f"{len(stable)} present in at least 80% of them; mean {r['mean_per_frame']:.1f} per frame.")
        for p in stable[:5]:
            run.finding("ok", f"{name}: {p['a']} - {p['b']} is present in {p['occupancy']:.0%} of the frames.")
        if transient and not stable:
            run.finding("note", f"{name}: none persists; the most frequent ({pairs[0]['a']} - {pairs[0]['b']}) is in {pairs[0]['occupancy']:.0%}.")
    return run.finish(_verdict(run, "Interactions listed with how often each is present"), out_dir,
                      f"vmd-agent workflow interaction_report {topology} {trajectory}")


def compare_runs(topology: str, trajectory_a: str, trajectory_b: str, out_dir: str, options: dict) -> dict:
    sel = options.get("selection", "name CA")
    run = _Run("compare_runs", "Two runs side by side", "How do these two trajectories of the same system differ?",
               {"topology": os.path.basename(topology), "run A": os.path.basename(trajectory_a), "run B": os.path.basename(trajectory_b),
                "selection": sel}, [topology, trajectory_a, trajectory_b], 6)
    got: Dict[str, Dict[str, dict]] = {"A": {}, "B": {}}
    for tag, traj in (("A", trajectory_a), ("B", trajectory_b)):
        for kind, what in (("rmsd", "RMSD"), ("rgyr", "radius of gyration"), ("rmsf", "per-atom fluctuation")):
            got[tag][kind] = run.step("vmd_measure", f"{what}, run {tag}", topology=topology, trajectory=traj, kind=kind, selection=sel,
                                      mass_weighted=False)
    for kind, name, unit in (("rmsd", "RMSD", "A"), ("rgyr", "Radius of gyration", "A"), ("rmsf", "RMSF", "A")):
        a, b = got["A"][kind].get("summary"), got["B"][kind].get("summary")
        if not (a and b):
            continue
        d = b["mean"] - a["mean"]
        own = " (each run measured against its own first frame)" if kind == "rmsd" else ""
        pooled = max(1e-9, ((a["std"] ** 2 + b["std"] ** 2) / 2) ** 0.5)
        level = "warning" if kind != "rmsf" and abs(d) > 2 * pooled else "note"
        run.finding(level, f"{name}: A {a['mean']:.3f} {unit} (sd {a['std']:.3f}), B {b['mean']:.3f} {unit} (sd {b['std']:.3f}); "
                           f"B - A = {d:+.3f} {unit}" + own + (" (larger than twice the spread within a run)." if level == "warning" else "."))
    ra, rb = got["A"]["rmsf"].get("per_atom"), got["B"]["rmsf"].get("per_atom")
    if ra and rb and len(ra) == len(rb):
        diffs = sorted(((y["rmsf"] - x["rmsf"], x) for x, y in zip(ra, rb)), key=lambda t: -abs(t[0]))[:3]
        run.finding("note", "largest per-residue differences in fluctuation (B - A): " + ", ".join(
            f"{x['resname']}{x['resid']} {d:+.2f} A" for d, x in diffs))
    run.finding("note", "Each run is a single trajectory: a difference between two runs is not evidence of a difference between "
                        "the systems without replicates.")
    return run.finish(_verdict(run, "Both runs measured the same way"), out_dir,
                      f"vmd-agent workflow compare_runs {topology} {trajectory_a} {trajectory_b}")


def prepare_simulation(structure: str, out_dir: str, options: dict) -> dict:
    run = _Run("prepare_simulation", "Prepare a simulation", "Is this structure ready to simulate, and can it be built into a CHARMM36 system?",
               {"structure": os.path.basename(structure), "padding (A)": options.get("padding", 10.0), "salt (M)": options.get("salt", 0.15),
                "temperature (K)": options.get("temperature", 310.0)}, [structure], 5)
    chk = run.step("vmd_structure_check", "check the input structure", topology=structure)
    tors = run.step("vmd_backbone_torsions", "check the backbone torsions", topology=structure)
    pre = os.path.join(out_dir, "system", "system")
    built = run.step("vmd_build_system", "build, solvate and neutralise (psfgen, solvate, autoionize)", input_pdb=structure, out_prefix=pre,
                     padding=float(options.get("padding", 10.0)), salt_concentration=float(options.get("salt", 0.15)))
    namd = {}
    if built.get("ok"):
        namd = run.step("vmd_prepare_namd", "write the NAMD input", psf=built["final_psf"], pdb=built["final_pdb"],
                        out_prefix=os.path.join(out_dir, "system", "equilibrate"), temperature=float(options.get("temperature", 310.0)))
        run.step("vmd_slurm_script", "write a SLURM job script", command="equilibrate.namd", kind="namd",
                 out_path=os.path.join(out_dir, "system", "run.sbatch"))
    if chk.get("ok"):
        bad = [f"{chk[k]} {w}" for k, w in (("chirality_errors", "chirality error(s)"), ("cis_peptides", "cis peptide(s)"), ("chain_gaps", "chain gap(s)")) if chk.get(k)]
        run.finding("warning" if bad else "ok", ("input problems: " + "; ".join(bad)) if bad else "the input has no chirality errors, cis peptides or chain gaps.")
    if tors.get("ok") and tors.get("n_residues") and tors["fraction_favoured"] < 0.75:
        run.finding("warning", f"only {tors['fraction_favoured']:.0%} of residues are in favoured Ramachandran regions.")
    if built.get("ok"):
        run.finding("ok" if abs(built["net_charge"]) < 0.01 else "problem", f"the built system has {built['n_atoms']} atoms, {built['n_waters']} waters, "
                    f"{built['n_ions']} ions and net charge {built['net_charge']:+.3f}.")
        if built.get("warning"):
            run.finding("warning", f"left out of the system: {', '.join(built['excluded_residue_names'])} ({built['excluded_atoms']} atoms). "
                                   "Ligands, nucleic acids, lipids and crystal water need their own parameters.")
    if namd.get("ok"):
        run.finding("warning", "the NAMD input was generated but has not been run in NAMD: read it, and check the box and the ensemble, before submitting.")
    return run.finish(_verdict(run, "System built; the input files are ready to review"), out_dir, f"vmd-agent workflow prepare_simulation {structure}")


def cryoem_fit(model: str, map_file: str, out_dir: str, options: dict) -> dict:
    res = float(options.get("resolution", 8.0))
    run = _Run("cryoem_fit", "Fit a model into a density map", "Where does this model fit this map best, and how well?",
               {"model": os.path.basename(model), "map": os.path.basename(map_file), "resolution (A)": res}, [model, map_file], 4)
    info = run.step("vmd_volume_info", "read the map", path=map_file)
    fit = run.step("vmd_fit_to_map", "rigid-body fit", model=model, map_file=map_file, resolution=res, out_pdb=os.path.join(out_dir, "fitted.pdb"))
    if fit.get("ok"):
        scene = {"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure"}],
                 "isosurfaces": [{"file": map_file, "isovalue": float((info.get("suggested_isovalues") or {}).get("mean+3sd", 0.1)),
                                  "style": "wireframe", "color": "ColorID 1"}], "background": "white"}
        img = run.step("vmd_render_scene", "draw the fitted model inside the map", scene_spec=scene, topology=fit["fitted_pdb"], trajectory=None,
                       out_png=os.path.join(out_dir, "fit.png"), width=1000, height=800)
        run.figure(img.get("image"))
        run.step("export_vmd_session", "export a session you can open in VMD", scene_spec=scene, topology=fit["fitted_pdb"], trajectory=None,
                 out_dir=os.path.join(out_dir, "session"))
        gain = fit["correlation_after"] - fit["correlation_before"]
        run.finding("ok" if fit["correlation_after"] >= 0.7 else "warning",
                    f"map-model correlation {fit['correlation_before']:.2f} before, {fit['correlation_after']:.2f} after the fit "
                    f"(change {gain:+.2f}); the model moved {fit['rotation_degrees']:.1f} degrees and by {fit['rmsd_moved_A']:.1f} A RMS.")
        if fit["correlation_after"] < 0.7:
            run.finding("warning", "the correlation is low: the model may not match the map, or the fit may be in a wrong local optimum.")
        run.finding("note", fit["note"])
    return run.finish(_verdict(run, "Fitted; check the picture"), out_dir, f"vmd-agent workflow cryoem_fit {model} {map_file}")


class Workflow:
    def __init__(self, fn: Callable, roles: List[str], summary: str, needs_vmd: bool, example: str):
        self.fn, self.roles, self.summary, self.needs_vmd, self.example = fn, roles, summary, needs_vmd, example


WORKFLOWS: Dict[str, Workflow] = {
    "structure_overview": Workflow(structure_overview, ["structure"], "what is it, and is it in good shape (composition, torsions, chirality, "
                                   "gaps, pictures)", False, "vmd-agent workflow structure_overview 1ubq.pdb"),
    "equilibration_check": Workflow(equilibration_check, ["topology", "trajectory"], "has the run settled (RMSD and size convergence, periodic box, "
                                    "two engines compared)", False, "vmd-agent workflow equilibration_check run.psf run.dcd"),
    "interaction_report": Workflow(interaction_report, ["topology", "trajectory"], "hydrogen bonds, salt bridges and (with --option partner=...) "
                                   "contacts, as how often each is present", True, 'vmd-agent workflow interaction_report run.psf run.dcd --option partner="resname LIG"'),
    "compare_runs": Workflow(compare_runs, ["topology", "trajectory_a", "trajectory_b"], "two trajectories of one system: RMSD, size, fluctuation, side by side",
                             True, "vmd-agent workflow compare_runs system.psf run1.dcd run2.dcd"),
    "prepare_simulation": Workflow(prepare_simulation, ["structure"], "check the input, build a solvated neutral CHARMM36 system, write NAMD and SLURM files",
                                   True, "vmd-agent workflow prepare_simulation 1ubq.pdb --option padding=10"),
    "cryoem_fit": Workflow(cryoem_fit, ["model", "map_file"], "fit a model into a cryo-EM map, with a picture and a session for VMD", False,
                           "vmd-agent workflow cryoem_fit model.pdb map.mrc --option resolution=6"),
}


def run_named(name: str, files: List[str], out_dir: str, options: Optional[dict] = None) -> dict:
    """Run workflow ``name`` on ``files`` (in the order its roles list), writing the report and everything else to ``out_dir``."""
    if name not in WORKFLOWS:
        raise security.InvalidInput(f"unknown workflow '{name}'; choose one of: {', '.join(WORKFLOWS)}")
    wf = WORKFLOWS[name]
    if len(files) != len(wf.roles):
        raise security.InvalidInput(f"{name} needs {len(wf.roles)} file(s): {', '.join(wf.roles)}")
    os.makedirs(out_dir, exist_ok=True)
    return wf.fn(*files, out_dir, dict(options or {}))


# ---------------------------------------------------------------- tools
@tool()
def list_workflows() -> dict:
    """The named multi-step workflows (each runs several tools in a fixed order, reports findings and writes a report):
    what each does, which files it needs, and whether it needs VMD."""
    return {"ok": True, "workflows": {n: {"files": w.roles, "does": w.summary, "needs_vmd": w.needs_vmd, "example": w.example}
                                      for n, w in WORKFLOWS.items()}}


@tool()
def run_workflow(name: str, files: List[str], out_dir: str = "workflow_report", options: Optional[dict] = None) -> dict:
    """Run a whole job on the user's files, in one call. USE THIS (not a single measurement) when asked whether a run has settled
    or equilibrated, to compare two runs, to prepare a simulation, to fit a model into a cryo-EM map, or for an overview of a structure.
    name and the files it needs, in order: equilibration_check [topology, trajectory]; structure_overview [structure];
    interaction_report [topology, trajectory]; compare_runs [topology, trajectory_a, trajectory_b]; prepare_simulation
    [structure]; cryoem_fit [model, map]. It runs the checks, grades the findings (ok / note / warning / problem), gives a verdict
    and writes report.md and report.html into out_dir. options: {"selection": "protein"}, {"partner": "resname LIG"}, {"padding": 10},
    {"resolution": 6}."""
    return run_named(name, [_p(f) for f in files], _p(out_dir) or out_dir, options)
