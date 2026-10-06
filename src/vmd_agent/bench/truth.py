"""Ground truth for benchmark questions, computed from the structure itself.

Nothing here involves a model: every fact is derived from the coordinates and
topology with the same validated routines the toolkit uses elsewhere
(DSSP, Shrake-Rupley burial, disulfide geometry). Thresholds that turn a
continuous measurement into a category are named constants so a reader can see
and change them.
"""
from __future__ import annotations

from typing import Optional

# category boundaries (percent of residues)
HELIX_DOMINANT = 30.0
SHEET_DOMINANT = 30.0
OTHER_CLASS_MAX = 15.0
MIXED_MIN = 15.0
BURIED_FRACTION = 0.5


def classify_fold(helix: float, sheet: float) -> str:
    """Dominant regular secondary structure.

    ``alpha``   helix >= 30 % and sheet < 15 %
    ``beta``    sheet >= 30 % and helix < 15 %
    ``mixed``   helix >= 15 % and sheet >= 15 %
    ``coil``    otherwise (little regular structure)
    """
    if helix >= HELIX_DOMINANT and sheet < OTHER_CLASS_MAX:
        return "alpha"
    if sheet >= SHEET_DOMINANT and helix < OTHER_CLASS_MAX:
        return "beta"
    if helix >= MIXED_MIN and sheet >= MIXED_MIN:
        return "mixed"
    return "coil"


def ground_truth(topology: str, trajectory: Optional[str] = None,
                 frame: int = 0) -> dict:
    """Facts about one structure, each with how it was obtained."""
    from vmd_agent.structure.detect import detect_system
    from vmd_agent.structure.stats import structure_stats
    from vmd_agent.evidence.claims import burial_fraction
    from vmd_agent.inputs.molio import load_universe

    det = detect_system(topology, trajectory)
    if det.get("error"):
        return {"ok": False, "error": det["error"]}
    st = structure_stats(topology, trajectory, frame=frame)
    comp = det["components"]
    ss = st.get("secondary_structure") or {}
    truth = {
        "ok": True,
        "topology": topology,
        "system_type": det["system_type"],
        "n_atoms": det["n_atoms"],
        "n_protein_chains": len(comp["protein"]["chains"]) or
        (1 if comp["protein"]["present"] else 0),
        "n_protein_residues": comp["protein"]["n_residues"],
        "has_protein": comp["protein"]["present"],
        "has_nucleic": comp["nucleic"]["present"],
        "has_lipid": comp["lipid"]["present"],
        "has_ligand": comp["ligands_or_other"]["present"],
        "ligand_resnames": comp["ligands_or_other"].get("resnames", []),
        "has_ions": comp["ions"]["present"],
        "n_disulfides": st.get("n_disulfide_bridges"),
        "n_salt_bridges": st.get("n_salt_bridges"),
        "helix_percent": ss.get("helix_percent"),
        "sheet_percent": ss.get("sheet_percent"),
        "coil_percent": ss.get("coil_percent"),
        "fold_class": (classify_fold(ss["helix_percent"], ss["sheet_percent"])
                       if ss.get("helix_percent") is not None else None),
        "provenance": {
            "composition": "residue-name detection (vmd_agent.structure.detect)",
            "secondary_structure": ss.get("source"),
            "disulfides": "SG-SG < 2.5 Å",
        },
    }
    # ligand burial (only meaningful with both a protein and a ligand)
    if truth["has_ligand"] and truth["has_protein"]:
        try:
            u = load_universe(topology, trajectory)
            if trajectory:
                u.trajectory[frame]
            sel = det["suggested_selections"]["ligand"]
            lig = u.select_atoms(sel).select_atoms("not name H*")
            if len(lig):
                b = burial_fraction(lig, u.select_atoms("protein"))
                truth["ligand_buried_fraction"] = b["buried_fraction"]
                truth["ligand_buried"] = b["buried_fraction"] >= BURIED_FRACTION
        except Exception as e:                              # pragma: no cover
            truth["ligand_burial_error"] = f"{type(e).__name__}: {e}"
    return truth
