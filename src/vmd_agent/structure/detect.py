"""Classify a molecular system from its topology (+ optional trajectory).

Uses MDAnalysis only, so it runs on any machine. Detects proteins, nucleic
acids, lipids, water, ions, ligands/other, and (heuristically) inorganic /
material components, then infers an overall system type and emits ready-made
VMD atom-selection strings for the recipe generator.
"""
from __future__ import annotations

import os
from collections import Counter
from typing import Optional

import numpy as np

from vmd_agent import security

_WATER = {"HOH", "WAT", "TIP3", "TIP4", "TIP5", "SOL", "H2O", "SPC", "SPCE",
          "T3P", "T4P", "OPC", "OPC3", "TIP", "OH2"}
_IONS = {"NA", "CL", "K", "MG", "CA", "ZN", "FE", "MN", "CU", "LI", "CS",
         "RB", "BR", "IOD", "I", "F", "SOD", "CLA", "POT", "CAL", "MG2",
         "ZN2", "CD", "NI", "CO", "HG", "BA", "SR", "AL"}
_LIPID = {"POPC", "POPE", "POPS", "POPG", "POPA", "POPI", "DPPC", "DPPE",
          "DPPG", "DOPC", "DOPE", "DOPS", "DMPC", "DMPE", "DLPC", "DSPC",
          "SDPC", "SAPC", "PSM", "SM", "CHL1", "CHOL", "CER", "DAG", "TAG",
          "LPPC", "POPCL", "PIP2", "PIP3", "PGCL"}
# Elements that, in bulk and outside bio residues, indicate a material. Sulfur,
# iron, zinc, copper and nickel also occur in cofactors, metalloproteins and
# FeS clusters, so they only count as "material" in very large numbers.
_MATERIAL_ELEMENTS = {"SI", "AU", "AG", "PT", "PD", "TI", "AL", "MO", "W",
                      "CR", "SN", "GE", "GA", "AS", "B"}
_MATERIAL_AMBIGUOUS = {"S", "FE", "ZN", "CU", "NI"}
_MATERIAL_MIN_ATOMS = 50
_MATERIAL_AMBIGUOUS_MIN_ATOMS = 500
# residue names used by some force fields for material slabs
_MATERIAL_RESNAMES = {"GRA", "MOS", "SIO", "AU", "AG", "PT", "PD"}


def _safe_elements(u):
    try:
        el = u.atoms.elements
        if el is not None and len(el):
            return np.array([str(e).strip().upper() for e in el])
    except Exception:
        pass
    # fall back to first alpha chars of atom name
    try:
        names = u.atoms.names
        out = []
        for n in names:
            s = "".join(c for c in str(n) if c.isalpha())
            out.append((s[:2] if len(s) >= 2 and s[:2].upper() in (_MATERIAL_ELEMENTS | _MATERIAL_AMBIGUOUS)
                        else s[:1]).upper())
        return np.array(out)
    except Exception:
        return np.array([])


def _sel(u, expr):
    try:
        return u.select_atoms(expr)
    except Exception:
        return u.atoms[[]]


def _chains(ag):
    for attr in ("chainIDs", "segids"):
        try:
            vals = getattr(ag, attr)
            uniq = sorted(set(str(v) for v in vals if str(v).strip()))
            if uniq:
                return uniq
        except Exception:
            continue
    return []


def _clash_check(u, cutoff=0.5, max_atoms=40000):
    """Return count of atom pairs closer than ``cutoff`` Å (overlap signal)."""
    try:
        from MDAnalysis.lib.distances import self_capped_distance
        pos = u.atoms.positions
        if len(pos) > max_atoms:
            idx = np.random.default_rng(0).choice(len(pos), max_atoms, replace=False)
            pos = pos[idx]
        pairs, dists = self_capped_distance(pos, max_cutoff=cutoff,
                                            min_cutoff=0.05,
                                            box=u.dimensions)
        return int(len(pairs))
    except Exception:
        return -1


def _gap_check(protein):
    """Detect residue-numbering discontinuities per chain (broken chains)."""
    gaps = []
    if not len(protein):
        return gaps
    try:
        for seg in protein.segments:
            resids = sorted(set(int(r) for r in seg.atoms.residues.resids))
            for a, b in zip(resids, resids[1:]):
                if b - a > 1:
                    gaps.append(f"segment {seg.segid}: gap {a}->{b}")
    except Exception:
        pass
    return gaps[:20]


def detect_system(topology: str, trajectory: Optional[str] = None,
                  clash_check: bool = True) -> dict:
    """Load a system and describe its molecular composition and type.

    Never raises: a file MDAnalysis cannot interpret (including a trajectory
    passed where a topology is needed) comes back as ``{"error": ...}``.
    """
    try:
        return _detect_system(topology, trajectory, clash_check)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}",
                "hint": "Provide a topology with atom and residue names "
                        "(PDB, mmCIF, PSF, GRO, PRMTOP), not a bare trajectory."}


def _detect_system(topology: str, trajectory: Optional[str],
                   clash_check: bool) -> dict:
    from vmd_agent.inputs.molio import load_universe

    if not os.path.exists(topology):
        return {"error": f"topology not found: {topology}"}
    try:
        u = load_universe(topology, trajectory)
    except Exception as e:
        return {"error": f"MDAnalysis could not load system: {e}",
                "hint": "Check the file pair (topology+trajectory) and formats."}

    n_atoms = len(u.atoms)
    resnames = np.array([str(r).upper() for r in u.atoms.resnames]) \
        if hasattr(u.atoms, "resnames") else np.array([])

    protein = _sel(u, "protein")
    nucleic = _sel(u, "nucleic")
    water = u.atoms[np.isin(resnames, list(_WATER))] if len(resnames) else _sel(u, "water")
    ions = u.atoms[np.isin(resnames, list(_IONS))] if len(resnames) else u.atoms[[]]
    lipid = u.atoms[np.isin(resnames, list(_LIPID))] if len(resnames) else u.atoms[[]]

    claimed = np.zeros(n_atoms, dtype=bool)
    for ag in (protein, nucleic, water, ions, lipid):
        claimed[ag.atoms.indices] = True
    other = u.atoms[np.where(~claimed)[0]]

    # heuristic material / inorganic detection among the "other" atoms
    elements = _safe_elements(u)
    material_present = False
    material_info = {}
    if len(other) and len(elements):
        oel = elements[other.indices]
        counts = Counter(oel.tolist())
        # a material is suggested by many atoms of a metal/semiconductor
        # element; bio-relevant elements need far more before we believe it
        big = {e: c for e, c in counts.items()
               if (e in _MATERIAL_ELEMENTS and c >= _MATERIAL_MIN_ATOMS)
               or (e in _MATERIAL_AMBIGUOUS
                   and c >= _MATERIAL_AMBIGUOUS_MIN_ATOMS)}
        if big:
            material_present = True
            material_info = {"elements": big,
                             "n_atoms": int(sum(big.values())),
                             "note": "Heuristic: bulk metal/semiconductor atoms "
                                     "outside standard bio residues. Verify manually."}

    other_resnames = sorted(set(str(r).upper() for r in other.residues.resnames)) \
        if len(other) else []
    # things in 'other' that are not the flagged material are candidate ligands
    ligand_resnames = [r for r in other_resnames
                       if r not in _MATERIAL_ELEMENTS
                       and r not in _MATERIAL_RESNAMES]

    # Residue names come from the file (mmCIF allows arbitrary text) and end up
    # in VMD selections, so only plain names are kept; the rest are reported.
    ligand_resnames, bad_lig = security.safe_resnames(ligand_resnames)
    lipid_names, bad_lip = security.safe_resnames(sorted(set(
        str(r).upper() for r in lipid.residues.resnames))) if len(lipid) \
        else ([], [])
    ion_names, bad_ion = security.safe_resnames(sorted(set(
        str(r).upper() for r in ions.residues.resnames))) if len(ions) \
        else ([], [])
    rejected_names = bad_lig + bad_lip + bad_ion

    comp = {
        "protein": {"present": bool(len(protein)), "n_atoms": int(len(protein)),
                    "n_residues": int(len(protein.residues)) if len(protein) else 0,
                    "chains": _chains(protein)},
        "nucleic": {"present": bool(len(nucleic)), "n_atoms": int(len(nucleic)),
                    "n_residues": int(len(nucleic.residues)) if len(nucleic) else 0,
                    "chains": _chains(nucleic)},
        "lipid": {"present": bool(len(lipid)), "n_atoms": int(len(lipid)),
                  "n_residues": int(len(lipid.residues)) if len(lipid) else 0,
                  "resnames": lipid_names},
        "water": {"present": bool(len(water)), "n_atoms": int(len(water)),
                  "n_molecules": int(len(water.residues)) if len(water) else 0},
        "ions": {"present": bool(len(ions)), "n_atoms": int(len(ions)),
                 "resnames": ion_names},
        "ligands_or_other": {"present": bool(ligand_resnames),
                             "resnames": ligand_resnames,
                             "n_atoms": int(len(other)) if not material_present else
                             int(len(other) - material_info.get("n_atoms", 0))},
        "material_inorganic": {"present": material_present, **material_info},
    }

    # ---- infer overall system type ----
    p, nuc, lip, lig = (comp["protein"]["present"], comp["nucleic"]["present"],
                        comp["lipid"]["present"], comp["ligands_or_other"]["present"])
    mat = material_present
    n_prot_chains = len(comp["protein"]["chains"])
    if mat and not (p or nuc):
        stype = "material/inorganic"
    elif mat and (p or nuc):
        stype = "hybrid bio-material"
    elif p and lip:
        stype = "membrane-protein"
    elif lip and not p:
        stype = "membrane/lipid-bilayer"
    elif p and nuc:
        stype = "protein-nucleic complex"
    elif p and lig:
        stype = "protein-ligand complex"
    elif p and n_prot_chains >= 2:
        stype = "protein-protein complex"
    elif p:
        stype = "protein (solvated)" if comp["water"]["present"] else "protein"
    elif nuc:
        stype = "nucleic acid"
    else:
        stype = "unclassified / small-molecule or other"

    # ---- integrity checks ----
    warnings = []
    if clash_check:
        nclash = _clash_check(u)
        if nclash > 0:
            warnings.append(f"{nclash} atom pair(s) within 0.5 Å — possible "
                            "overlapping atoms / bad geometry.")
    gaps = _gap_check(protein)
    if gaps:
        warnings.append(f"{len(gaps)} residue-numbering gap(s) in protein "
                        "(possible missing residues / broken chains).")
    if not len(u.atoms):
        warnings.append("Zero atoms parsed — topology may be unsupported.")
    n_bad_xyz = int((~np.isfinite(u.atoms.positions)).any(axis=1).sum()) \
        if len(u.atoms) else 0
    if n_bad_xyz:
        warnings.append(f"{n_bad_xyz} atom(s) have non-finite (NaN/Inf) "
                        "coordinates; renders and measurements involving "
                        "them are unreliable.")
    if rejected_names:
        warnings.append(f"{len(rejected_names)} residue name(s) with unusual "
                        "characters were ignored (not drawn or selected): "
                        + ", ".join(repr(n[:20]) for n in rejected_names[:5]))

    box = None
    try:
        if u.dimensions is not None and float(u.dimensions[0]) > 0:
            box = [round(float(x), 3) for x in u.dimensions]
    except Exception:
        pass

    # ---- suggested VMD selections for the recipe generator ----
    sel = {}
    if comp["protein"]["present"]:
        sel["protein"] = "protein"
    if comp["nucleic"]["present"]:
        sel["nucleic"] = "nucleic"
    if comp["lipid"]["present"]:
        sel["lipid"] = "resname " + " ".join(comp["lipid"]["resnames"])
    if comp["ions"]["present"]:
        sel["ions"] = "resname " + " ".join(comp["ions"]["resnames"])
    if comp["water"]["present"]:
        sel["water"] = "water"
    if comp["ligands_or_other"]["present"]:
        sel["ligand"] = "resname " + " ".join(comp["ligands_or_other"]["resnames"][:20])

    return {
        "topology": topology, "trajectory": trajectory,
        "n_atoms": int(n_atoms),
        "n_residues": int(len(u.atoms.residues)),
        "n_segments": int(len(u.segments)),
        "n_frames": int(len(u.trajectory)) if trajectory else 1,
        "box": box,
        "components": comp,
        "system_type": stype,
        "gaps": gaps,
        "warnings": warnings,
        "suggested_selections": sel,
    }
