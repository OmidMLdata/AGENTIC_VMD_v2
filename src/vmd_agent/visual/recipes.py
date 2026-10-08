"""Generate VMD/Tcl visualization recipes tailored to a detected system.

The output is a self-contained Tcl script the user runs in their own VMD
(``vmd -e recipe.tcl``). It picks representations, colouring, materials,
lighting, camera and background suited to the components that are present,
and is tuned for publication-quality Tachyon rendering.
"""
from __future__ import annotations

import os
from typing import Optional

from vmd_agent import security

# (style, colour) recipes per component. Each is a list of VMD rep lines.
_COMPONENT_REPS = {
    "protein":  [("NewCartoon", "Structure",
                  "Secondary structure ribbon; classic protein overview.")],
    "protein_chain": [("NewCartoon", "Chain",
                       "Colour each chain distinctly (good for complexes).")],
    "nucleic":  [("NewCartoon", "Chain",
                  "Nucleic backbone ribbon."),
                 ("Licorice", "Name",
                  "Show bases/backbone atoms as sticks.")],
    "lipid":    [("Licorice", "Name",
                  "Lipid tails/heads as thin sticks."),],
    "lipid_surf": [("QuickSurf", "ResName",
                    "Membrane as a smooth surface for context.")],
    "ligand":   [("Licorice", "Name",
                  "Ligand as thick sticks, coloured by element."),],
    "ions":     [("VDW", "Name",
                  "Ions as spheres.")],
    "water":    [("Lines", "Name",
                  "Water as faint lines (often hidden by default).")],
    "material": [("CPK", "Element",
                  "Atoms+bonds for the material/inorganic phase."),
                 ("DynamicBonds", "Element",
                  "Recompute bonds by distance — needed for lattices.")],
}

# Sensible default rep parameters (radius, resolution, thickness ...)
from vmd_agent.visual.representations import (
    REPRESENTATIONS, check_suitability, FOCUS_PLANS,
)

# Parameters come from the representation catalogue so there is a single
# source of truth.
_REP_PARAMS = {name: rep["params"] for name, rep in REPRESENTATIONS.items()}


def _auto_protein_reps(detection: dict, plddt_coloring: bool = False,
                       focus: str = "overview") -> list:
    """Pick the *best* protein representation for this particular structure.

    ``focus`` lets a user steer intent — "show me the surface", "show the
    side-chain interactions", "just the fold" — while the size/content
    heuristics below still guard against choices that would render badly.
    """
    p = detection.get("components", {}).get("protein", {})
    n_res = p.get("n_residues", 0)
    n_chains = len(p.get("chains", []) or [])
    n_atoms = detection.get("n_atoms", 0)

    # ---- explicit intent first -------------------------------------------
    if focus == "fold":
        return [("Tube", "Chain" if n_chains >= 2 else "Structure",
                 "Backbone tube — the global fold and topology, without "
                 "secondary-structure geometry.")]
    if focus == "interactions":
        return [("Tube", "ColorID 6",
                 "Faint backbone tube as context for the side chains."),
                ("Licorice", "Name",
                 "Side chains as uniform narrow cylinders — the clean way to "
                 "read hydrogen bonds and salt bridges.")]
    if focus == "surface":
        if n_atoms <= 200000:
            return [("Surf", "ResType",
                     "Solvent-accessible surface coloured by residue "
                     "chemistry — shows cavities and hydrophobic patches.")]
        return [("QuickSurf", "Chain",
                 "Fast smooth molecular envelope (system too large for Surf).")]
    if focus == "pocket":
        return [("NewCartoon", "Structure",
                 "Cartoon fold underneath the surface."),
                ("Surf", "ResType",
                 "Transparent solvent-accessible surface to expose pocket "
                 "depth around the ligand.")]
    if focus == "performance":
        return [("Lines", "Name",
                 "Wireframe — fastest option for a very large system or a "
                 "quick trajectory check.")]

    # ---- otherwise choose from the structure itself ------------------------
    if plddt_coloring:
        return [("NewCartoon", "Beta",
                 "AlphaFold model: coloured by pLDDT confidence stored in the "
                 "B-factor column (blue/high -> red/low).")]
    if n_res and n_res < 20:
        return [("Licorice", "Name",
                 f"Short peptide ({n_res} residues) — sticks show every atom; "
                 "a cartoon would render almost nothing.")]
    if n_atoms > 300000:
        return [("QuickSurf", "Chain",
                 f"Very large assembly ({n_atoms} atoms) — molecular surface "
                 "renders far faster than per-residue cartoon.")]
    if n_chains >= 2:
        return [("NewCartoon", "Chain",
                 f"Secondary-structure ribbon, one colour per chain "
                 f"({n_chains} chains) to separate the subunits.")]
    return [("NewCartoon", "Structure",
             "Secondary-structure ribbon (helix/sheet/coil) — the standard "
             "publication view for a folded protein.")]


def _rep_block(sel: str, style: str, color: str, material: str,
               comment: str) -> str:
    # Every value below is written into a script that is never screened, so
    # each is validated (see vmd_agent.security).
    style = security.tcl_word(style, "representation")
    color = security.tcl_word(color, "colour method")
    material = security.tcl_word(material, "material")
    sel = security.tcl_selection(sel)
    comment = " ".join(str(comment).split())          # one line, no injection
    params = _REP_PARAMS.get(style, "")
    return (f"# {comment}\n"
            f"mol representation {style} {params}\n"
            f"mol color {color}\n"
            f"mol selection {{{sel}}}\n"
            f"mol material {material}\n"
            f"mol addrep top\n")


def planned_reps(detection: dict, material: str = "Opaque", focus: str = "overview", representation: Optional[str] = None,
                 color_method: Optional[str] = None, plddt_coloring: bool = False, show_water: bool = False) -> tuple:
    """The representations a recipe draws for a detected system, as data: ``([{selection, style, color, material, params, comment}], warnings)``.
    The Tcl recipe and the live VMD window both draw exactly these, so a picture of the window shows what a recipe would."""
    sels = detection.get("suggested_selections", {})
    out: list = []
    suitability_warnings: list = []

    def put(sel, style, color, mat, comment):
        out.append({"selection": security.tcl_selection(sel), "style": security.tcl_word(style, "representation"),
                    "color": security.tcl_word(color, "colour method"), "material": security.tcl_word(mat, "material"),
                    "params": [float(x) for x in str(_REP_PARAMS.get(style, "")).split()], "comment": " ".join(str(comment).split())})

    def add(key, sel):
        for stylei, colori, comment in _COMPONENT_REPS[key]:
            put(sel, stylei, colori, material, comment)

    if "protein" in sels:
        if representation:
            # explicit user request wins, but we say so if it fits badly
            suitability_warnings += check_suitability(representation, detection)
            chosen = [(representation, color_method or "Structure", f"Representation explicitly requested: {representation}.")]
        else:
            chosen = _auto_protein_reps(detection, plddt_coloring, focus)
            if color_method:
                chosen = [(s, color_method, c) for s, _c, c in chosen]
        for stylei, colori, comment in chosen:
            mat = material
            # a surface drawn over a cartoon must be see-through
            if focus == "pocket" and stylei in ("Surf", "MSMS", "QuickSurf"):
                mat = "Transparent"
            put(sels["protein"], stylei, colori, mat, comment)
    if "nucleic" in sels:
        add("nucleic", sels["nucleic"])
    if "lipid" in sels:
        add("lipid", sels["lipid"])
    if "ligand" in sels:
        if focus == "pocket":
            put(sels["ligand"], "CPK", "Name", material, "Ligand as van-der-Waals spheres + bonds, to show how it fills the pocket.")
        else:
            add("ligand", sels["ligand"])
    if "ions" in sels:
        add("ions", sels["ions"])
    if "material_inorganic" in detection.get("components", {}) and detection["components"]["material_inorganic"].get("present"):
        add("material", "not (protein or nucleic or water)")
    if show_water and "water" in sels:
        add("water", sels["water"])
    return out, suitability_warnings


def generate_visualization_recipe(detection: dict,
                                  style: str = "publication",
                                  background: str = "white",
                                  show_water: bool = False,
                                  out_path: Optional[str] = None,
                                  load_files: bool = True,
                                  plddt_coloring: bool = False,
                                  focus: str = "overview",
                                  representation: Optional[str] = None,
                                  color_method: Optional[str] = None) -> dict:
    """Build a Tcl recipe from a :func:`detect_system` result.

    Parameters
    ----------
    detection : dict
        Output of ``detect_system`` (must contain ``suggested_selections``).
    style : {"publication", "presentation", "quick"}
        Controls resolution / ray-trace quality hints written into the script.
    background : {"white", "black"}
    show_water : bool
        Whether to add a (faint) water representation.
    out_path : str, optional
        If given, the Tcl is written here.
    load_files : bool
        If True, the recipe loads topology/trajectory itself; otherwise it
        assumes a molecule is already loaded as ``top``.
    """
    if detection.get("error"):
        raise security.InvalidInput(
            f"cannot build a recipe for a system that did not load: "
            f"{detection['error']}")
    sels = detection.get("suggested_selections", {})
    stype = detection.get("system_type", "unknown")
    topo = detection.get("topology")
    traj = detection.get("trajectory")

    material = "AOChalky" if style == "publication" else "Opaque"
    lines = []
    lines.append("# ==============================================")
    lines.append(f"# VMD visualization recipe  ({stype})")
    lines.append("# generated by vmd_agent")
    lines.append("# run:  vmd -e this_recipe.tcl")
    lines.append("# ==============================================\n")

    # Resolve to ABSOLUTE paths so VMD loads the right files regardless of the
    # directory it is launched from. Relative paths are the classic cause of a
    # recipe silently loading the wrong (or no) file.
    topo_abs = security.tcl_path(topo) if topo else None
    traj_abs = security.tcl_path(traj) if traj else None
    if representation is not None and representation not in REPRESENTATIONS:
        raise security.InvalidInput(
            f"unknown representation '{representation}'; choose from "
            f"{sorted(REPRESENTATIONS)}")
    if color_method is not None:
        color_method = security.tcl_word(color_method, "colour method")

    if load_files and topo_abs:
        lines.append(f"# Loading: {topo_abs}"
                     + (f"\n#      +  {traj_abs}" if traj_abs else ""))
        for pth, label in ((topo_abs, "topology"), (traj_abs, "trajectory")):
            if pth and not os.path.exists(pth):
                lines.append(f"# WARNING: {label} path does not exist: {pth}")
        if traj_abs:
            lines.append(f'mol new {{{topo_abs}}} type {{{_mtype(topo_abs)}}} '
                         f'waitfor all')
            lines.append(f'mol addfile {{{traj_abs}}} type {{{_mtype(traj_abs)}}} '
                         f'waitfor all\n')
        else:
            lines.append(f'mol new {{{topo_abs}}} type {{{_mtype(topo_abs)}}} '
                         f'waitfor all\n')
    else:
        lines.append("# (assumes molecule already loaded as 'top')\n")

    lines.append("mol delrep 0 top\n")

    # choose protein rep: chain colouring for multi-chain complexes
    prot_multi = len(detection.get("components", {})
                     .get("protein", {}).get("chains", [])) >= 2

    def add(key, sel):
        for stylei, colori, comment in _COMPONENT_REPS[key]:
            lines.append(_rep_block(sel, stylei, colori, material, comment))

    planned, suitability_warnings = planned_reps(detection, material, focus=focus, representation=representation, color_method=color_method,
                                                  plddt_coloring=plddt_coloring, show_water=show_water)
    for r in planned:
        lines.append(_rep_block(r["selection"], r["style"], r["color"], r["material"], r["comment"]))

    # ---- global scene / camera / render settings ----
    bg = "white" if background == "white" else "black"
    res = {"publication": 2000, "presentation": 1200, "quick": 800}.get(style, 1200)
    aa = {"publication": 12, "presentation": 6, "quick": 2}.get(style, 6)
    lines.append("\n# ---- scene settings ----")
    lines.append(f"color Display Background {bg}")
    lines.append("display projection Orthographic")
    lines.append("axes location off")
    lines.append("display depthcue on")
    # GLSL needs a real OpenGL display; in headless text mode VMD raises
    # "Illegal rendering mode: GLSL", and under -eofexit that Tcl error
    # aborts the whole sourcing script before anything is rendered.
    lines.append("catch {display rendermode GLSL}")
    lines.append("display resetview")
    lines.append("mol reanalyze top\n")

    # Only a standalone recipe (one that loads its own molecule) should render.
    # With load_files=False the caller is embedding these representations into
    # a session that renders itself; emitting `render` here would dump a stray
    # multi-MB render.dat into the caller's working directory.
    if load_files:
        lines.append("# ---- headless publication render (Tachyon) ----")
        lines.append("# Adjust the tachyon path if needed (see probe_environment).")
        lines.append("set outfile \"render\"")
        lines.append("render Tachyon $outfile.dat")
        lines.append("# then run the bundled ray tracer, e.g.:")
        lines.append(f"#   tachyon -aasamples {aa} $outfile.dat "
                     f"-format PNG -res {res} {int(res*0.66)} -o $outfile.png")
        lines.append("# (vmd_agent.render.render_image automates this)\n")

    tcl = "\n".join(lines)

    written = None
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w") as fh:
            fh.write(tcl)
        written = os.path.abspath(out_path)

    return {
        "system_type": stype,
        "style": style,
        "focus": focus,
        "focus_plan": FOCUS_PLANS.get(focus, ""),
        "suitability_warnings": suitability_warnings,
        "representation_rationale": [c for _s, _c, c in
                                     _auto_protein_reps(detection,
                                                        plddt_coloring, focus)]
        if ("protein" in sels and not representation) else [],
        "background": background,
        "tcl": tcl,
        "written_to": written,
        "representations_added": _summarize_reps(
            sels, prot_multi, show_water, detection,
            plddt_coloring=plddt_coloring, focus=focus,
            representation=representation, color_method=color_method),
    }


def _summarize_reps(sels, prot_multi, show_water, detection,
                    plddt_coloring=False, focus="overview",
                    representation=None, color_method=None):
    """Describe what was actually drawn (must mirror the recipe body)."""
    out = []
    if "protein" in sels:
        if representation:
            chosen = [(representation, color_method or "Structure", "")]
        else:
            chosen = _auto_protein_reps(detection, plddt_coloring, focus)
            if color_method:
                chosen = [(s, color_method, c) for s, _c, c in chosen]
        for stylei, colori, _c in chosen:
            out.append(f"protein: {stylei} / colour by {colori}")
    if "nucleic" in sels:
        out.append("nucleic: NewCartoon + Licorice")
    if "lipid" in sels:
        out.append("lipid: Licorice by Name")
    if "ligand" in sels:
        out.append("ligand: Licorice by Name (element colours)")
    if "ions" in sels:
        out.append("ions: VDW spheres")
    if detection.get("components", {}).get("material_inorganic", {}).get("present"):
        out.append("material: CPK + DynamicBonds by Element")
    if show_water and "water" in sels:
        out.append("water: faint Lines")
    return out


def _mtype(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {"pdb": "pdb", "ent": "pdb", "psf": "psf", "gro": "gro",
            "mol2": "mol2", "xyz": "xyz", "dcd": "dcd", "xtc": "xtc",
            "trr": "trr", "prmtop": "parm7", "parm7": "parm7", "nc": "netcdf",
            "netcdf": "netcdf", "data": "lammps", "lammps": "lammps",
            "lammpstrj": "lammpstrj", "cif": "pdbx", "mmcif": "pdbx",
            "pqr": "pqr", "pdbqt": "pdbqt"}.get(ext, ext)
