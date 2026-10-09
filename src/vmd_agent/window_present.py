"""Show what a tool found in the VMD window.

Many tools produce something you would want to *see* in VMD: the residues of the persistent hydrogen bonds, the outliers of a Ramachandran check, a map as an
isosurface with the fitted model inside it, two superposed structures, a built system, the frames picked as informative. Those tools take ``show_in_window=true``:
they do exactly what they always did, and then draw the result in the VMD window (opened if needed), so the picture is VMD's own. The same goes for a whole job
(``run_workflow(show_in_window=true)``) and for the auto-drawing of ``visualize_and_interpret``.

``shows_in_window`` adds the parameter to a tool; :data:`PRESENTERS` holds, per tool, what is drawn. Nothing here talks to VMD except through
:class:`vmd_agent.vmdlink.Window`, so everything stays inside its fixed command set.
"""
from __future__ import annotations

import functools
import inspect
import os
import typing
from typing import Callable, Dict, List, Optional

from vmd_agent import security, vmdlink

PRESENTERS: Dict[str, Callable] = {}
#: what the extra parameter says, for a model and for a person
SHOW_HELP = "also draw the result in the VMD window (opened if needed), so you see it in VMD itself"


def presenter(*names: str):
    def deco(fn):
        for n in names:
            PRESENTERS[n] = fn
        return fn
    return deco


def shows_in_window(fn: Callable) -> Callable:
    """Give a tool the parameter ``show_in_window``: after it has run, its result is also drawn in the VMD window and the result gains a ``window`` entry."""
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn)                              # resolved here: the wrapper lives in another module, where a string annotation would not resolve

    @functools.wraps(fn)
    def wrapper(*args, show_in_window: bool = False, **kwargs):
        result = fn(*args, **kwargs)
        if show_in_window and isinstance(result, dict) and result.get("ok", True) is not False:
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            result["window"] = present(fn.__name__, dict(bound.arguments), result)
        return result
    params = [p.replace(annotation=hints.get(p.name, inspect.Parameter.empty)) for p in sig.parameters.values()]
    params.append(inspect.Parameter("show_in_window", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation=bool))
    wrapper.__signature__ = sig.replace(parameters=params, return_annotation=hints.get("return", inspect.Signature.empty))
    wrapper.__annotations__ = {**hints, "show_in_window": bool}
    wrapper.__doc__ = fn.__doc__                                    # the parameter says what it does (toolhints.PARAM_HELP), so the description does not repeat it
    return wrapper


def present(tool: str, args: dict, result: dict) -> dict:
    """Draw ``result`` of ``tool`` in the VMD window. A failure here never fails the tool: it is reported under ``window``."""
    fn = PRESENTERS.get(tool)
    if fn is None:
        return {"ok": False, "error": f"{tool} has nothing to draw"}
    try:
        win = vmdlink.Window(vmdlink.open_window())
        before = _fingerprint(win)
        out = fn(win, args, result)
        out.setdefault("ok", True)
        out["changed"] = _fingerprint(win) != before                # said by the window, not by the presenter: did anything in it actually change?
        if not out["changed"]:
            out["summary"] = "The VMD window already showed this, so nothing new was drawn."
        out["molecules"] = [{"id": m["id"], "name": m["name"], "top": m["top"], "frame": m["frame"], "frames": m["nframes"], "representations": m["numreps"]} for m in win.molecules()]
        return out
    except (vmdlink.LinkError, security.SecurityError, security.InvalidInput, OSError, ValueError, KeyError) as e:
        return {"ok": False, "error": str(e) or type(e).__name__}


# ------------------------------------------------------------------------------------------------ helpers
def _real(path: str) -> str:
    return os.path.realpath(security.check_path(path))


def _fingerprint(win: vmdlink.Window) -> list:
    """What the window holds, to tell afterwards whether anything was drawn: each molecule with its representations, visibility and frame."""
    return [(m["id"], m["numreps"], m["top"], m.get("shown"), m["frame"], m["nframes"]) for m in win.molecules()]


def _molecule_holding(win: vmdlink.Window, path: str) -> Optional[dict]:
    want = _real(path)
    for m in win.molecules():
        if m.get("files") and os.path.realpath(m["files"][0]) == want:
            return m
    return None


def load(win: vmdlink.Window, topology: str, trajectory: Optional[str] = None) -> dict:
    """Load a structure (and its trajectory) as a new molecule, with the structure's own frame dropped when a trajectory follows (VMD frame N is trajectory frame N)."""
    r = win.new_molecule(topology)
    if trajectory:
        r = win.add_file(r["id"], trajectory, drop_first=os.path.splitext(topology)[1].lower() in vmdlink.HAS_COORDS)
    return r


def clear_reps(win: vmdlink.Window, mid: int) -> None:
    for i in range(len(win.reps(mid)) - 1, -1, -1):
        win.delete_rep(mid, i)


def visualize(win: vmdlink.Window, mid: int, topology: str, trajectory: Optional[str] = None, focus: str = "overview", representation: Optional[str] = None,
              color_method: Optional[str] = None, show_water: bool = False, plddt_coloring: bool = False, background: Optional[str] = "white") -> dict:
    """Draw molecule ``mid`` the way ``generate_visualization_recipe`` would draw it: the recipe's own representations for what the system contains, and its scene settings."""
    from vmd_agent import auto as auto_mod
    from vmd_agent.structure import detect as detect_mod
    from vmd_agent.visual import recipes
    det = detect_mod.detect_system(security.check_path(topology), security.check_path(trajectory) if trajectory else None)
    if det.get("error"):
        raise vmdlink.LinkError(f"cannot draw a system that did not load: {det['error']}")
    planned, warnings = recipes.planned_reps(det, "Opaque", focus=focus, representation=representation, color_method=color_method, plddt_coloring=plddt_coloring, show_water=show_water)
    clear_reps(win, mid)
    for r in planned:
        win.add_rep(mid, r["selection"], r["style"], r["color"], r["material"], r["params"])
    if background:
        win.display("background", background)
        win.display("projection", "Orthographic")
        win.display("axes", "Off")
        win.display("depthcue", True)
        win.view("reset")
    return {"molecule": mid, "system_type": det.get("system_type"), "focus": focus, "preliminary_explanation": auto_mod.describe_from_detection(det),
            "visual_legend": auto_mod.visual_legend(det, plddt_coloring=plddt_coloring, focus=focus, protein_reps=None, backend="vmd"),
            "what_to_look_for": auto_mod._what_to_look_for(det.get("system_type", "unknown")), "suitability_warnings": warnings,
            "representations": [{"selection": r["selection"], "style": r["style"], "color": r["color"], "why": r["comment"]} for r in planned]}


def ensure(win: vmdlink.Window, topology: str, trajectory: Optional[str] = None) -> int:
    """The id of the molecule that holds ``topology``: the one already in the window, or a newly loaded one drawn as a recipe would draw it."""
    held = _molecule_holding(win, topology)
    if held is not None:
        if trajectory and held["nframes"] <= 1:
            win.add_file(held["id"], security.check_path(trajectory), drop_first=os.path.splitext(topology)[1].lower() in vmdlink.HAS_COORDS)
        win.top(held["id"])
        return int(held["id"])
    mid = int(load(win, topology, trajectory)["id"])
    try:
        visualize(win, mid, topology, trajectory)
    except (vmdlink.LinkError, OSError, ValueError, KeyError):
        pass                                                      # the structure is shown anyway, drawn by VMD's default
    win.top(mid)
    return mid


def _resids(labels: List[str]) -> List[int]:
    out = set()
    for label in labels:
        parts = str(label).split(":")
        if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            out.add(int(parts[1]))
    return sorted(out)


def _highlight(win: vmdlink.Window, mid: int, resids: List[int], color: str = "Name", style: str = "Licorice", params: Optional[list] = None) -> Optional[str]:
    if not resids:
        return None
    selection = "resid " + " ".join(str(r) for r in resids)
    win.add_rep(mid, selection, style, color, "Opaque", params)
    return selection


def _goto(win: vmdlink.Window, frame) -> None:
    try:
        if frame is not None and int(frame) >= 0:
            win.animate("goto", int(frame))
    except (vmdlink.LinkError, ValueError, TypeError):
        pass


def show_map(win: vmdlink.Window, path: str, level: Optional[float] = None, color: str = "ColorID 3", style: str = "wireframe") -> dict:
    """Load a density map as a molecule drawn as an isosurface (at ``level``, or at the map's mean + 3 standard deviations)."""
    from vmd_agent import toolset
    from vmd_agent.vmdkit import scene
    full = security.check_path(path)
    if level is None:
        info = toolset.TOOLS["inspect_map"](path=full)
        levels = info.get("suggested_isovalues") or {}
        level = float(levels.get("mean+3sd") or levels.get("mean+1sd") or 0.1)
    r = win.new_molecule(full, vmdlink.MAP_TYPES.get(os.path.splitext(full)[1].lower().lstrip("."), None) or vmdlink.file_type(full))
    clear_reps(win, r["id"])
    win.add_rep(r["id"], "all", "Isosurface", color, "Transparent", [level, 0, 0, scene.ISO_STYLES[style], 1, 1])
    return {"map_molecule": int(r["id"]), "isovalue": level}


def _load_simple(win: vmdlink.Window, path: str, color: str, style: str = "NewCartoon") -> int:
    r = win.new_molecule(security.check_path(path))
    clear_reps(win, r["id"])
    win.add_rep(r["id"], "all", style, color, "Opaque")
    return int(r["id"])


# ------------------------------------------------------------------------------------------------ what each tool draws
@presenter("visualize_and_interpret")
def _visualize_and_interpret(win, a, r):
    held = _molecule_holding(win, a["topology"])
    mid = int(held["id"]) if held else int(load(win, a["topology"], a.get("trajectory"))["id"])
    out = visualize(win, mid, a["topology"], a.get("trajectory"), focus=a.get("focus") or "overview", representation=a.get("representation"),
                    show_water=bool(a.get("show_water")), plddt_coloring=bool(a.get("plddt_coloring")), background=a.get("background") or "white")
    win.top(mid)
    return {**out, "summary": f"Drew {os.path.basename(a['topology'])} in the VMD window the way the recipe draws it ({len(out['representations'])} representation(s))."}


@presenter("render_image", "export_session")
def _scene_or_recipe(win, a, r):
    spec = a.get("scene_spec")
    if spec:
        from vmd_agent import window_tools
        return window_tools.apply_scene(win, spec, a.get("topology"), a.get("trajectory"))
    return _visualize_and_interpret(win, a, r)


@presenter("find_interactions")
def _interactions(win, a, r):
    mid = ensure(win, a["topology"], a.get("trajectory"))
    pairs = (r.get("most_persistent") or [])[:10]
    resids = _resids([x for p in pairs for x in (p["a"], p["b"])])
    sel = _highlight(win, mid, resids)
    if sel and a.get("kind", "hbonds") == "hbonds":
        win.add_rep(mid, sel, "HBonds", "Name", "Opaque", [3.0, 20.0, 1])
    return {"molecule": mid, "highlighted_residues": resids, "summary": (f"Highlighted the residues of the {len(pairs)} most persistent {a.get('kind', 'hbonds')} pair(s) in the VMD window."
                                                                           if resids else "No pairs were found, so there is nothing to highlight.")}


@presenter("backbone_torsions")
def _torsions(win, a, r):
    mid = ensure(win, a["topology"], a.get("trajectory"))
    _goto(win, a.get("frame"))
    resids = sorted({int(o["resid"]) for o in r.get("outliers") or []})
    _highlight(win, mid, resids, "ColorID 1")
    return {"molecule": mid, "highlighted_residues": resids, "summary": f"{len(resids)} Ramachandran outlier residue(s) are drawn in red in the VMD window."}


@presenter("check_structure")
def _structure_check(win, a, r):
    mid = ensure(win, a["topology"], a.get("trajectory"))
    _goto(win, a.get("frame"))
    return {"molecule": mid, "summary": "The structure is shown in the VMD window; the structure check reports counts, not residues, so nothing is highlighted."}


@presenter("secondary_structure")
def _secondary_structure(win, a, r):
    mid = ensure(win, a["topology"], a.get("trajectory"))
    clear_reps(win, mid)
    win.add_rep(mid, a.get("selection") or "protein", "NewCartoon", "Structure", "Opaque")
    return {"molecule": mid, "summary": "Drawn as a cartoon coloured by secondary structure (VMD's own assignment) in the VMD window."}


@presenter("select_keyframes")
def _keyframes(win, a, r):
    mid = ensure(win, a["topology"], a["trajectory"])
    frames = r.get("frames") or []
    _goto(win, frames[0] if frames else 0)
    return {"molecule": mid, "frames": frames, "summary": f"The VMD window is on frame {frames[0] if frames else 0}; the informative frames are {frames}. Step through them with window_animate."}


@presenter("align_structures")
def _align(win, a, r):
    aligned = r.get("aligned_pdb")
    if not aligned:
        return {"ok": False, "error": "give out_pdb to see the superposition: the moved structure has to be written to be drawn"}
    ref = _load_simple(win, a["reference"], "ColorID 8")
    mov = _load_simple(win, aligned, "ColorID 0")
    win.top(mov)
    return {"reference_molecule": ref, "aligned_molecule": mov, "summary": "The reference (white) and the superposed structure (blue) are drawn in the VMD window."}


@presenter("fit_to_map")
def _fit(win, a, r):
    fitted = r.get("fitted_pdb")
    if not fitted:
        return {"ok": False, "error": "give out_pdb to see the fit: the fitted model has to be written to be drawn"}
    shown = show_map(win, a["map_file"])
    mid = _load_simple(win, fitted, "Structure")
    win.top(mid)
    return {"model_molecule": mid, **shown, "summary": f"The fitted model is drawn inside the map (isosurface at {shown['isovalue']:.3g}) in the VMD window; correlation {r.get('correlation_after', 0):.2f}."}


@presenter("make_map")
def _make_map(win, a, r):
    shown = show_map(win, r.get("map_path") or a["out_dx"])
    return {**shown, "summary": f"The map is drawn as an isosurface at {shown['isovalue']:.3g} in the VMD window."}


@presenter("combine_maps")
def _combine_maps(win, a, r):
    shown = show_map(win, a["out_dx"])
    return {**shown, "summary": f"The combined map is drawn as an isosurface at {shown['isovalue']:.3g} in the VMD window."}


@presenter("inspect_map")
def _inspect_map(win, a, r):
    shown = show_map(win, a["path"])
    return {**shown, "summary": f"The map is drawn as an isosurface at {shown['isovalue']:.3g} in the VMD window."}


def _show_built(win, psf: Optional[str], pdb: str, what: str) -> dict:
    if psf and os.path.isfile(psf):
        r = win.new_molecule(security.check_path(psf))
        win.add_file(r["id"], security.check_path(pdb), drop_first=False)
        mid = int(r["id"])
    else:
        mid = int(win.new_molecule(security.check_path(pdb))["id"])
    try:
        visualize(win, mid, psf or pdb, pdb if psf else None)
    except (vmdlink.LinkError, OSError, ValueError, KeyError):
        pass
    win.top(mid)
    return {"molecule": mid, "summary": f"The {what} is loaded in the VMD window."}


@presenter("build_system")
def _built_system(win, a, r):
    return _show_built(win, r.get("final_psf"), r["final_pdb"], "built system")


@presenter("mutate_residue", "merge_structures", "build_membrane")
def _built_psf_pdb(win, a, r):
    return _show_built(win, r.get("psf"), r["pdb"], "result")


@presenter("build_nanotube")
def _nanotube(win, a, r):
    return _show_built(win, None, r["pdb"], "nanotube")


# ------------------------------------------------------------------------------------------------ whole jobs
def present_workflow(name: str, files: List[str], result: dict, out_dir: str) -> dict:
    """Show the outcome of a whole job in the VMD window: what its figures show, but in VMD."""
    try:
        win = vmdlink.Window(vmdlink.open_window())
        before = _fingerprint(win)
        from vmd_agent import toolset
        shown: dict = {}
        facts = result.get("facts") or {}
        if name in ("flexibility_report", "ligand_report"):
            top, trj = files[0], files[1]
            mid = ensure(win, top, trj)
            shown["molecule"] = mid
            if name == "flexibility_report":
                _highlight(win, mid, [int(r) for r in facts.get("flexible_residues") or []], "ColorID 1")
            else:
                if facts.get("ligand"):
                    win.add_rep(mid, str(facts["ligand"]), "Licorice", "Name", "Opaque", None)
                _highlight(win, mid, [int(r) for r in facts.get("touching_residues") or []], "ColorID 4")
        elif name == "compare_structures":
            shown.update(PRESENTERS["align_structures"](win, {"mobile": facts.get("mobile"), "reference": facts.get("reference")},
                                                         {"aligned_pdb": facts.get("aligned_pdb")}))
        elif name in ("trajectory_qc", "check_claims"):
            return {"ok": True, "changed": False, "summary": f"The outcome of {name} is statements and numbers (see the report); there is nothing to draw, so the VMD window was left as it was."}
        elif name in ("structure_overview", "equilibration_check", "interaction_report"):
            top = files[0]
            trj = files[1] if len(files) > 1 else None
            mid = ensure(win, top, trj)
            shown["molecule"] = mid
            if name == "structure_overview":
                tors = toolset.TOOLS["backbone_torsions"](topology=top)
                _highlight(win, mid, sorted({int(o["resid"]) for o in tors.get("outliers") or []}), "ColorID 1")
            elif name == "interaction_report":
                for kind in ("hbonds", "salt_bridges"):
                    r = toolset.TOOLS["find_interactions"](topology=top, trajectory=trj, kind=kind)
                    if r.get("ok"):
                        PRESENTERS["find_interactions"](win, {"topology": top, "trajectory": trj, "kind": kind}, r)
        elif name == "compare_runs":
            top, a, b = files
            first = _load_simple(win, top, "ColorID 0")
            win.add_file(first, security.check_path(a), drop_first=os.path.splitext(top)[1].lower() in vmdlink.HAS_COORDS)
            second = _load_simple(win, top, "ColorID 1")
            win.add_file(second, security.check_path(b), drop_first=os.path.splitext(top)[1].lower() in vmdlink.HAS_COORDS)
            shown.update(molecule_a=first, molecule_b=second)
        elif name == "prepare_simulation":
            pre = os.path.join(out_dir, "system", "system")
            psf = next((pre + s + ".psf" for s in ("_ion", "_wb", "") if os.path.isfile(pre + s + ".psf")), None)
            if psf is None:
                return {"ok": False, "error": "no built system was written, so there is nothing to show"}
            shown.update(_show_built(win, psf, psf[:-4] + ".pdb", "built system"))
        elif name == "cryoem_fit":
            fitted = os.path.join(out_dir, "fitted.pdb")
            if not os.path.isfile(fitted):
                return {"ok": False, "error": "the fit did not write a model, so there is nothing to show"}
            shown.update(show_map(win, files[1]))
            mid = _load_simple(win, fitted, "Structure")
            win.top(mid)
            shown["model_molecule"] = mid
        changed = _fingerprint(win) != before
        summary = (f"The outcome of {name} is drawn in the VMD window." if changed and name != "equilibration_check" else
                   "The system and its trajectory are loaded in the VMD window. The analysis itself is numbers and figures (see the report); VMD draws the structure, not the statistics."
                   if changed else
                   "The VMD window already showed this system, so nothing new was drawn. The outcome of "
                   f"{name} is numbers and figures (see the report), not something VMD draws.")
        return {"ok": True, **shown, "changed": changed, "summary": summary}
    except (vmdlink.LinkError, security.SecurityError, security.InvalidInput, OSError, ValueError, KeyError) as e:
        return {"ok": False, "error": str(e) or type(e).__name__}
