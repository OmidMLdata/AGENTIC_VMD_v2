"""One-shot: turn an uploaded molecular file into a VMD visualization plus a
grounded interpretation package.

Pipeline:  inspect -> detect -> recipe -> render (multi-view via VMD) -> brief.

The natural-language *reading of the picture* is done by the vision agent, but
this module gives it everything needed to be accurate rather than guess:
  * a **visual legend** mapping each colour/shape in the render to a real,
    detected component (so "orange sticks" is known to be ligand LIG, etc.),
  * a **preliminary explanation** derived purely from the detected composition,
  * a system-type-specific **what-to-look-for** checklist,
  * the rendered images themselves.

Without VMD it still returns detection + legend + preliminary explanation and
notes that images are unavailable.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence

from vmd_agent import security
from vmd_agent.inputs.inspection import inspect_files
from vmd_agent.structure.detect import detect_system
from vmd_agent.visual.recipes import generate_visualization_recipe


# ---- grounding: map rendered representations to detected components --------
_REP_DESCRIPTION = {
    ("NewCartoon", "Structure"): "Ribbon / cartoon coloured by secondary "
                                 "structure (helix / sheet / coil)",
    ("NewCartoon", "Chain"): "Ribbon / cartoon with one colour per chain",
    ("NewCartoon", "Beta"): "Ribbon / cartoon coloured by pLDDT confidence "
                            "from the B-factor column (blue = confident, "
                            "red = low confidence)",
    ("Licorice", "Name"): "All-atom sticks coloured by element "
                          "(VMD palette: cyan C, red O, blue N, yellow S)",
    ("QuickSurf", "Chain"): "Molecular surface with one colour per chain",
    ("Tube", "Structure"): "Backbone trace coloured by secondary structure "
                           "(purple helix, yellow strand, cyan turn, white coil)",
    ("Tube", "Chain"): "Backbone trace with one colour per chain",
    ("Tube", "Beta"): "Backbone trace coloured by pLDDT confidence from the "
                      "B-factor column (blue = confident, red = low)",
}


def visual_legend(detection: dict, plddt_coloring: bool = False,
                  focus: str = "overview", protein_reps: Optional[list] = None,
                  backend: str = "vmd") -> list:
    """Explain what each thing in the render *is*, so the reading is grounded.

    The protein entry is derived from the representation the *renderer that
    drew the picture* reports (``protein_reps``; VMD's choice from
    :func:`recipes._auto_protein_reps` by default), so the legend can never
    describe a different picture from the one that was rendered. Descriptions
    fall back to the representation catalogue for any pair not spelled out
    here.
    """
    from vmd_agent.visual.recipes import _auto_protein_reps
    from vmd_agent.visual.representations import REPRESENTATIONS, COLOUR_METHODS

    comp = detection.get("components", {})
    legend = []
    if comp.get("protein", {}).get("present"):
        reps = protein_reps if protein_reps is not None else \
            _auto_protein_reps(detection, plddt_coloring, focus)
        for stylei, colori, _c in reps:
            desc = _REP_DESCRIPTION.get((stylei, colori))
            if not desc:
                base = REPRESENTATIONS.get(stylei, {}).get("summary", stylei)
                cmeth = COLOUR_METHODS.get(colori.split()[0], "")
                desc = base.rstrip(".") + f", coloured by {colori}"
                if cmeth:
                    desc += f" ({cmeth.split('.')[0].lower()})"
            legend.append(f"{desc} = **protein** "
                          f"({comp['protein']['n_residues']} residues, "
                          f"chains {comp['protein']['chains'] or 'n/a'}).")
    if comp.get("nucleic", {}).get("present"):
        if backend == "matplotlib":
            legend.append("Phosphate-backbone trace = **nucleic acid** "
                          f"({comp['nucleic']['n_residues']} residues).")
        else:
            legend.append("Ribbon backbone + sticks = **nucleic acid** "
                          f"({comp['nucleic']['n_residues']} residues).")
    if comp.get("lipid", {}).get("present"):
        legend.append("Thin sticks forming a slab/bilayer = **lipid membrane** "
                      f"({', '.join(comp['lipid'].get('resnames', [])) or 'lipids'}).")
    if comp.get("ligands_or_other", {}).get("present"):
        legend.append("Thick sticks in element colours (cyan C, red O, blue N, yellow S) "
                      f"= **ligand / non-standard residue** "
                      f"({', '.join(comp['ligands_or_other']['resnames'][:8])}).")
    if comp.get("ions", {}).get("present"):
        legend.append("Isolated spheres = **ions** "
                      f"({', '.join(comp['ions'].get('resnames', []))}).")
    if comp.get("material_inorganic", {}).get("present"):
        el = comp["material_inorganic"].get("elements", {})
        legend.append("Spheres joined by distance-based bonds = "
                      f"**material / inorganic phase** ({', '.join(el.keys())}).")
    return legend


def build_color_keys(detection: dict, plddt_coloring: bool = False,
                     focus: str = "overview",
                     protein_reps: Optional[list] = None,
                     show_water: bool = False) -> list:
    """Colour keys for every representation actually drawn in the scene."""
    from vmd_agent.visual.recipes import _auto_protein_reps
    from vmd_agent.visual.colorkey import color_key

    comp = detection.get("components", {})
    keys, seen = [], set()
    element_syms = []

    def add(method, elements=None):
        # Element-based keys are accumulated and merged into ONE key at the
        # end; otherwise the panel repeats "COLOUR KEY — Name" per component.
        if method in ("Name", "Element", "Type"):
            for e in (elements or []):
                e = str(e).strip().upper()
                if e and e not in element_syms:
                    element_syms.append(e)
            return
        if method in seen or not method:
            return
        seen.add(method)
        ck = color_key(method, detection, is_alphafold=plddt_coloring)
        if ck.get("entries") or ck.get("type") == "continuous":
            keys.append(ck)

    if comp.get("protein", {}).get("present"):
        reps = protein_reps if protein_reps is not None else \
            _auto_protein_reps(detection, plddt_coloring, focus)
        for _s, colori, _c in reps:
            add(colori)
    if comp.get("ligands_or_other", {}).get("present"):
        add("Name", ["C", "N", "O", "S"])
    if comp.get("ions", {}).get("present"):
        add("Name", [r.strip() for r in
                     comp["ions"].get("resnames", [])][:8] or ["NA", "CL"])
    if comp.get("material_inorganic", {}).get("present"):
        add("Element", list(comp["material_inorganic"]
                            .get("elements", {}).keys())[:8])
    # Water is hidden unless requested, so it must not get a key either.
    if show_water and comp.get("water", {}).get("present"):
        add("Name", ["O", "H"])

    if element_syms:
        ck = color_key("Name", detection, elements=element_syms)
        if ck.get("entries"):
            keys.append(ck)
    return keys


def _what_to_look_for(stype: str) -> list:
    base = ["Overall shape and how compact vs. extended the assembly looks.",
            "Whether any component is clearly separate from (or detached from) the rest."]
    extra = {
        "protein": ["Fold type and secondary-structure content (mostly helical, "
                    "sheet, or mixed).", "Exposed vs. buried termini and any obvious "
                    "domains or cavities."],
        "protein (solvated)": ["Fold and secondary-structure content.",
                    "Whether the surface looks well-packed (folded) or frayed."],
        "protein-ligand complex": ["Whether the ligand sits inside a pocket/cleft "
                    "or on the surface.", "How enclosed the ligand is by protein "
                    "(buried = likely specific binding)."],
        "protein-protein complex": ["The interface between chains and how large the "
                    "contact area looks.", "Relative orientation of the partners."],
        "protein-nucleic complex": ["Where the protein contacts the nucleic acid "
                    "(major/minor groove, backbone).", "Whether binding looks "
                    "wrapped/clamped or glancing."],
        "membrane-protein": ["Which part of the protein spans the lipid slab "
                    "(transmembrane region) vs. sits in solvent.",
                    "Whether a pore/channel axis is visible through the membrane."],
        "membrane/lipid-bilayer": ["Bilayer continuity and the two leaflets.",
                    "Any pores, thinning, or defects."],
        "material/inorganic": ["Lattice regularity and the exposed surface/facet.",
                    "Visible defects, vacancies, or adsorbates on the surface."],
        "hybrid bio-material": ["How the biomolecule sits on the surface (footprint, "
                    "orientation).", "Whether it lies flat or stands up on the material."],
        "nucleic acid": ["Helix type and groove pattern.",
                    "Whether strands stay paired or fray at the ends."],
    }.get(stype, ["Key structural features that stand out.",
                  "Anything unusual in geometry or packing."])
    return base + extra


def describe_from_detection(detection: dict) -> str:
    """A preliminary, vision-free explanation grounded in composition alone."""
    stype = detection.get("system_type", "unknown")
    comp = detection.get("components", {})
    n_atoms = detection.get("n_atoms")
    parts = [f"This appears to be a **{stype}** system with {n_atoms} atoms."]
    bits = []
    if comp.get("protein", {}).get("present"):
        p = comp["protein"]
        bits.append(f"a protein of {p['n_residues']} residues across "
                    f"{len(p['chains']) or 1} chain(s)")
    if comp.get("nucleic", {}).get("present"):
        bits.append(f"a nucleic acid ({comp['nucleic']['n_residues']} residues)")
    if comp.get("lipid", {}).get("present"):
        bits.append("a lipid membrane")
    if comp.get("ligands_or_other", {}).get("present"):
        bits.append("one or more ligands/non-standard residues "
                    f"({', '.join(comp['ligands_or_other']['resnames'][:6])})")
    if comp.get("ions", {}).get("present"):
        bits.append(f"ions ({', '.join(comp['ions'].get('resnames', []))})")
    if comp.get("material_inorganic", {}).get("present"):
        bits.append("an inorganic/material phase")
    if comp.get("water", {}).get("present"):
        bits.append(f"{comp['water']['n_molecules']} water molecules")
    if bits:
        parts.append("It contains " + "; ".join(bits) + ".")
    # significance line reused from report logic
    from vmd_agent.evidence.report import _significance
    parts.append(_significance(stype, detection, {}))
    if detection.get("warnings"):
        parts.append("Note: automated checks flagged — " +
                     "; ".join(detection["warnings"]) + ".")
    return " ".join(parts)


def fetch_and_visualize(identifier: str,
                        out_dir: str = "vmd_agent_output",
                        source: str = "auto",
                        views: Sequence[str] = ("front", "side", "top", "iso"),
                        style: str = "publication",
                        background: str = "white",
                        show_water: bool = False,
                        focus: str = "overview",
                        representation: Optional[str] = None,
                        annotate: bool = True,
                        vmd_path: Optional[str] = None,
                        renderer: str = "auto") -> dict:
    """Download a structure from the web, then visualize and interpret it.

    ``identifier`` may be a PDB ID (``1UBQ``), a UniProt accession for an
    AlphaFold model (``P69905``), or a direct URL. The structure is saved to
    ``out_dir/structures``, rendered from several viewpoints with the
    automatically-chosen best representation, and returned as the same
    interpretation package as :func:`visualize_and_interpret`.
    """
    from vmd_agent.inputs.fetch import fetch_structure

    out_dir = os.path.abspath(out_dir)
    got = fetch_structure(identifier, out_dir=os.path.join(out_dir, "structures"),
                          source=source)
    if not got.get("ok"):
        return {"ok": False, "stage": "fetch", **got}

    pkg = visualize_and_interpret(
        got["path"], trajectory=None, out_dir=out_dir, views=views,
        style=style, background=background, show_water=show_water,
        plddt_coloring=(got.get("source") == "alphafold"),
        focus=focus, representation=representation, annotate=annotate,
        vmd_path=vmd_path, renderer=renderer)

    pkg["fetched"] = {k: v for k, v in got.items() if k != "ok"}
    meta = got.get("metadata") or {}
    if meta:
        # Put the database's own description in front of the agent so the
        # write-up names the actual molecule rather than guessing from shape.
        bits = []
        if meta.get("title"):
            bits.append(f"PDB entry {got.get('identifier')}: {meta['title']}")
        if meta.get("experimental_method"):
            res = meta.get("resolution_A")
            bits.append(f"determined by {meta['experimental_method']}"
                        + (f" at {res} Å resolution" if res else ""))
        if bits:
            pkg["database_description"] = "; ".join(bits) + "."
            pkg["preliminary_explanation"] = (
                pkg["database_description"] + " "
                + pkg.get("preliminary_explanation", ""))
    if got.get("note"):
        pkg.setdefault("source_notes", []).append(got["note"])
    return pkg


def visualize_and_interpret(topology: str, trajectory: Optional[str] = None,
                            out_dir: str = "vmd_agent_output",
                            views: Sequence[str] = ("front", "side", "top"),
                            style: str = "publication",
                            background: str = "white",
                            frame: int = -1,
                            render: bool = True,
                            show_water: bool = False,
                            plddt_coloring: bool = False,
                            focus: str = "overview",
                            representation: Optional[str] = None,
                            annotate: bool = True,
                            vmd_path: Optional[str] = None,
                            renderer: str = "auto") -> dict:
    """Full auto pipeline for one file (pair). Returns an interpretation package.

    ``renderer`` is ``"auto"`` (VMD if installed, otherwise the open-source
    matplotlib backend), ``"vmd"`` or ``"matplotlib"``. The legend
    and colour keys are derived from the representation that backend actually
    draws, and the package states which renderer produced the images.

    The agent should then **view each image** and write the final reading,
    guided by ``visual_legend`` and ``what_to_look_for``.
    """
    from vmd_agent.visual.renderers import get_renderer
    from vmd_agent.evidence import provenance

    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    paths = [p for p in (topology, trajectory) if p]
    insp = inspect_files(paths)
    if not insp["ready_to_load"]:
        return {"ok": False, "stage": "inspection", "inspection": insp,
                "message": "Cannot load yet — resolve missing files first.",
                "missing": insp["missing"]}

    det = detect_system(topology, trajectory)
    if det.get("error"):
        return {"ok": False, "stage": "detection", "error": det["error"]}

    try:
        rend = get_renderer(renderer, vmd_path)
    except ValueError as e:
        return {"ok": False, "stage": "renderer", "error": str(e)}

    recipe_path = os.path.join(out_dir, "recipe.tcl")
    try:
        rec = generate_visualization_recipe(
            det, style=style, background=background, show_water=show_water,
            out_path=recipe_path, plddt_coloring=plddt_coloring, focus=focus,
            representation=representation)
    except (security.SecurityError, security.InvalidInput) as e:
        return {"ok": False, "stage": "recipe", "error": str(e)}

    from vmd_agent.structure.stats import structure_stats, stats_caption
    stats = structure_stats(topology, trajectory)
    # Legend and keys follow what the chosen backend really draws.
    if representation and rend.name == "vmd":
        reps = None                      # recipe honours an explicit request
    else:
        reps = rend.protein_reps(det, plddt_coloring, focus)
    ckeys = build_color_keys(det, plddt_coloring, focus, protein_reps=reps,
                             show_water=show_water)
    legend = visual_legend(det, plddt_coloring=plddt_coloring, focus=focus,
                           protein_reps=reps, backend=rend.name)

    package = {
        "ok": True,
        "structure_stats": stats,
        "stats_caption": stats_caption(stats),
        "color_keys": ckeys,
        "inspection": insp,
        "detection": det,
        "recipe_path": recipe_path,
        "system_type": det["system_type"],
        "preliminary_explanation": describe_from_detection(det),
        "visual_legend": legend,
        "focus": focus,
        "renderer": {"requested": renderer, "used": rend.name,
                     "available": rend.available(),
                     "caveats": list(rend.caveats)},
        "representation_rationale": rec.get("representation_rationale", []),
        "suitability_warnings": rec.get("suitability_warnings", []),
        "what_to_look_for": _what_to_look_for(det["system_type"]),
        "images": {},
        "interpretation_instructions": (
            "Call view_image on each rendered image below. Using the "
            "visual_legend to identify what each colour/shape is, describe what "
            "you actually see for each item in what_to_look_for. Keep visual "
            "claims separate from measured facts, and do not infer dynamics or "
            "binding strength from a static image. Then (optionally) run "
            "analyze_trajectory for quantitative backing and call "
            "assemble_report."),
    }
    if rend.caveats:
        package["interpretation_instructions"] += (
            " The images come from the '" + rend.name + "' renderer, which "
            "differs from VMD in ways listed under renderer.caveats; do not "
            "read those differences as properties of the molecule.")
    if representation and rend.name != "vmd":
        package.setdefault("source_notes", []).append(
            f"representation='{representation}' is honoured only by the VMD "
            f"recipe; the {rend.name} backend drew its own backbone trace.")

    def _finish():
        outputs = [recipe_path] + list(package.get("images", {}).values())
        package["provenance_path"] = provenance.record_run(
            out_dir, "visualize_and_interpret",
            params={"style": style, "background": background, "frame": frame,
                    "focus": focus, "representation": representation,
                    "views": list(views), "renderer": rend.name,
                    "show_water": show_water,
                    "plddt_coloring": plddt_coloring},
            inputs=paths, outputs=outputs, recipe_text=rec["tcl"],
            vmd_path=vmd_path)
        return package

    if not render:
        package["note"] = "Rendering skipped by request; detection-only package."
        return _finish()
    if not rend.available():
        package["note"] = (
            f"Renderer '{rend.name}' is not available, so no images were "
            "rendered. The preliminary explanation and legend are still valid. "
            "For VMD set VMD_BIN or pass vmd_path (VMD is not bundled); or use "
            "renderer='matplotlib' for an open-source fallback.")
        return _finish()

    rv = rend.render_views(topology, trajectory, frame=frame, detection=det,
                           recipe_path=recipe_path, views=views,
                           out_dir=os.path.join(out_dir, "views"),
                           background=background, show_water=show_water,
                           plddt_coloring=plddt_coloring, focus=focus)
    package["images"] = rv.get("images", {})
    package["render_ok"] = rv.get("ok", False)
    if rv.get("focus_note"):
        package.setdefault("source_notes", []).append(rv["focus_note"])

    # Composite the colour key + statistics onto every rendered view so each
    # image is self-describing.
    if rv.get("images") and annotate:
        from vmd_agent.visual.annotate import annotate_image
        annotated = {}
        for view, img in rv["images"].items():
            a = annotate_image(
                img, color_keys=ckeys,
                stats_lines=package.get("stats_caption", []),
                legend_lines=package.get("visual_legend", []),
                title=f"{os.path.basename(topology)} — {view} view "
                      f"({det.get('system_type')}; {rend.name} renderer)")
            if a.get("ok"):
                annotated[view] = a["annotated_image"]
        if annotated:
            package["annotated_images"] = annotated
    if not rv.get("ok"):
        package["render_error"] = (rv.get("error")
                                   or rv.get("vmd_stderr", "")[:600])
    return _finish()


def probe_environment(vmd_path: Optional[str] = None) -> dict:
    """Host capabilities plus the drawing backends available on this machine.

    Call this first: ``recommended_renderer`` is ``"vmd"`` when a working
    VMD+Tachyon exists, otherwise ``"matplotlib"``.
    """
    from vmd_agent import environment
    from vmd_agent.visual.renderers import list_renderers
    report = environment.probe_environment(vmd_path)
    rend = list_renderers(vmd_path)
    report["renderers"] = rend
    report["can_render_any"] = any(r["available"] for r in rend.values())
    report["recommended_renderer"] = (
        "vmd" if rend["vmd"]["available"]
        else "matplotlib" if rend["matplotlib"]["available"] else None)
    return report


def select_keyframes(topology: str, trajectory: str, k: int = 9,
                     selection: str = "protein", sel2: Optional[str] = None,
                     cutoff: float = 4.5, step: int = 1, z_min: float = 6.0,
                     include_ss: bool = False, out_dir: Optional[str] = None,
                     render: bool = False, renderer: str = "auto",
                     vmd_path: Optional[str] = None, width: int = 960,
                     height: int = 720) -> dict:
    """Pick event-aware keyframes and optionally render them (one fixed camera).

    Selection lives in :mod:`vmd_agent.dynamics.keyframes`; drawing lives in
    :mod:`vmd_agent.visual`; this function is where the two are composed.
    """
    from vmd_agent.dynamics import keyframes
    out = keyframes.select_keyframes(
        topology, trajectory, k=k, selection=selection, sel2=sel2,
        cutoff=cutoff, step=step, z_min=z_min, include_ss=include_ss,
        out_dir=out_dir)
    if not (render and out.get("ok")):
        return out
    from vmd_agent.visual.renderers import get_renderer
    rend = get_renderer(renderer, vmd_path)
    det = detect_system(topology, trajectory)
    out["rendered"] = rend.render_frames(
        topology, trajectory, out["frames"], detection=det,
        out_dir=os.path.join(out_dir or ".", "keyframes"),
        width=width, height=height)
    out["renderer"] = rend.name
    return out
