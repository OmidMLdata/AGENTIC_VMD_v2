"""Quantitative structure statistics to annotate a rendered image.

Counts bonds and links so a figure can be labelled with real numbers rather
than adjectives: total bonds, bonds by element pair, disulfide bridges,
hydrogen bonds, salt bridges, and secondary-structure content.

Many structure files (a plain PDB, most materials) carry **no bond records**,
so bonds are inferred by distance when the topology has none; the returned
``bond_source`` field always says which happened, because "1,842 bonds" means
something different if they were guessed. The same honesty applies to
hydrogen bonds: when hydrogens are present they are counted with the standard
H...A distance and D-H...A angle criteria; when absent the count falls back to
heavy-atom distance and ``hbond_method`` says so, because that overcounts.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np

# Covalent radii (Å) for distance-based bond inference.
_COVALENT = {
    "H": 0.31, "C": 0.76, "N": 0.71, "O": 0.66, "S": 1.05, "P": 1.07,
    "F": 0.57, "CL": 1.02, "BR": 1.20, "I": 1.39, "NA": 1.66, "K": 2.03,
    "MG": 1.41, "CA": 1.76, "ZN": 1.22, "FE": 1.32, "SI": 1.11,
}
_DEFAULT_RADIUS = 0.8
_BOND_TOLERANCE = 0.45      # Å slack on the sum of covalent radii

_MONATOMIC_IONS = {"NA", "CL", "K", "MG", "CA", "ZN", "FE", "MN", "CU", "LI",
                   "CS", "RB", "BR", "I", "F", "SOD", "CLA", "POT", "CAL",
                   "IOD", "NI", "CO", "CD", "HG", "BA", "SR", "AL"}

_WATER_RESNAMES = ["HOH", "WAT", "TIP3", "TIP4", "TIP5", "SOL", "H2O", "SPC",
                   "SPCE", "T3P", "T4P", "OPC", "OPC3", "TIP", "OH2"]

# H-bond criteria
HBOND_HA_MAX = 2.5          # Å, H...acceptor
HBOND_DA_MAX = 3.5          # Å, donor...acceptor (heavy-atom fallback)
HBOND_ANGLE_MIN = 120.0     # degrees, D-H...A


def _elements(ag):
    """Best-effort element symbols for an AtomGroup."""
    try:
        el = ag.elements
        if el is not None and len(el):
            return np.array([str(e).strip().upper() for e in el])
    except Exception:
        pass
    out = []
    for n in ag.names:
        s = "".join(c for c in str(n) if c.isalpha()).upper()
        out.append(s[:2] if s[:2] in _COVALENT else s[:1])
    return np.array(out)


def _ion_mask(ag, elements):
    """True for atoms that are free monatomic ions (never covalently bonded).

    Without this, distance-based inference invents Na-Cl and Na-Na "bonds"
    between solvated ions, putting chemically wrong numbers on a figure.
    """
    n = len(ag)
    if not n:
        return np.zeros(0, dtype=bool)
    try:
        resnames = np.array([str(r).upper() for r in ag.resnames])
    except Exception:
        return np.zeros(n, dtype=bool)
    try:
        ri = ag.resindices
        single = np.bincount(ri)[ri] == 1
    except Exception:
        single = np.ones(n, dtype=bool)
    named = np.isin(resnames, list(_MONATOMIC_IONS)) | \
        np.isin(np.asarray(elements), list(_MONATOMIC_IONS))
    return single & named


def _infer_bonds(ag, elements, box=None, max_atoms=60000):
    """Distance-based bond inference using covalent radii.

    Free monatomic ions are excluded, since they form no covalent bonds.
    """
    from MDAnalysis.lib.distances import self_capped_distance
    pos = ag.positions
    if len(pos) > max_atoms:
        return None, "too many atoms for distance-based inference"
    radii = np.array([_COVALENT.get(e, _DEFAULT_RADIUS) for e in elements])
    ions = _ion_mask(ag, elements)
    max_cut = float(radii.max() * 2 + _BOND_TOLERANCE)
    pairs, dists = self_capped_distance(pos, max_cutoff=max_cut,
                                        min_cutoff=0.1, box=box)
    if not len(pairs):
        return np.empty((0, 2), int), "distance-based (covalent radii)"
    limit = radii[pairs[:, 0]] + radii[pairs[:, 1]] + _BOND_TOLERANCE
    keep = (dists <= limit) & ~ions[pairs[:, 0]] & ~ions[pairs[:, 1]]
    return pairs[keep], ("distance-based (covalent radii; free ions excluded)")


def _secondary_structure(u, select="protein"):
    """Secondary-structure fractions from the built-in DSSP."""
    from vmd_agent.structure.dssp import secondary_structure_fractions
    ss = secondary_structure_fractions(u.select_atoms(select))
    if ss and "codes" in ss and len(ss["codes"]) > 1500:
        ss.pop("codes")
    return ss


def _describe(method, ha_max, da_max, angle_min):
    if method == "angle":
        return (f"H...acceptor <= {ha_max} Å, donor-acceptor <= {da_max} Å and "
                f"D-H...A angle >= {angle_min:.0f}°, different residues, "
                "water excluded")
    return (f"no hydrogens in this structure, so heavy-atom N/O pairs within "
            f"{da_max} Å were counted (distance only, no angle test); this "
            "overestimates relative to angle-based counts")


def count_hydrogen_bonds(ag, box=None, exclude_water=True, ha_max=HBOND_HA_MAX,
                         da_max=HBOND_DA_MAX, angle_min=HBOND_ANGLE_MIN):
    """Count H-bonds between different residues of an AtomGroup.

    Uses H...A and D-H...A criteria when hydrogens exist, otherwise falls back
    to N/O heavy-atom distance. Returns ``(count, method, description)`` or
    ``None`` for an empty group. Water is excluded unless ``exclude_water`` is
    False (trajectory analysis lets the user's selection decide).
    """
    from MDAnalysis.lib.distances import capped_distance
    solute = ag
    if exclude_water and len(ag):
        resn = np.array([str(r).upper() for r in ag.resnames])
        solute = ag[~np.isin(resn, _WATER_RESNAMES)]
    if not len(solute):
        return None
    el = _elements(solute)
    heavy_polar = np.isin(el, ["N", "O"])
    hydrogens = el == "H"
    acc_idx = np.where(el == "O")[0]
    ri = solute.resindices
    pos = solute.positions

    if hydrogens.any():
        h_idx = np.where(hydrogens)[0]
        heavy_idx = np.where(~hydrogens)[0]
        desc = _describe("angle", ha_max, da_max, angle_min)
        # parent heavy atom = nearest heavy atom within 1.3 Å
        pairs, d = capped_distance(pos[h_idx], pos[heavy_idx], max_cutoff=1.3,
                                   box=box)
        parent = np.full(len(h_idx), -1)
        best = np.full(len(h_idx), np.inf)
        for (a, b), dd in zip(pairs, d):
            if dd < best[a]:
                best[a], parent[a] = dd, heavy_idx[b]
        is_don = parent >= 0
        is_don[is_don] = heavy_polar[parent[is_don]]
        h_idx, parent = h_idx[is_don], parent[is_don]
        if not len(h_idx) or not len(acc_idx):
            return 0, "angle", desc
        pairs, _ = capped_distance(pos[h_idx], pos[acc_idx],
                                   max_cutoff=ha_max, min_cutoff=1.2, box=box)
        seen = set()
        for a, b in pairs:
            d_atom, a_atom, h_atom = parent[a], acc_idx[b], h_idx[a]
            if ri[d_atom] == ri[a_atom] or d_atom == a_atom:
                continue
            if np.linalg.norm(pos[d_atom] - pos[a_atom]) > da_max:
                continue
            v1 = pos[d_atom] - pos[h_atom]
            v2 = pos[a_atom] - pos[h_atom]
            denom = np.linalg.norm(v1) * np.linalg.norm(v2)
            if denom == 0:
                continue
            ang = np.degrees(np.arccos(np.clip(np.dot(v1, v2) / denom, -1, 1)))
            if ang >= angle_min:
                seen.add((int(d_atom), int(a_atom)))
        return len(seen), "angle", desc

    desc = _describe("distance_only", ha_max, da_max, angle_min)
    don_idx = np.where(heavy_polar)[0]
    if not len(don_idx) or not len(acc_idx):
        return 0, "distance_only", desc
    pairs, _ = capped_distance(pos[don_idx], pos[acc_idx], max_cutoff=da_max,
                               min_cutoff=2.2, box=box)
    seen = set()
    for a, b in pairs:
        d_atom, a_atom = don_idx[a], acc_idx[b]
        if ri[d_atom] != ri[a_atom]:
            seen.add((int(min(d_atom, a_atom)), int(max(d_atom, a_atom))))
    return len(seen), "distance_only", desc


def _count_salt_bridges(u, box, cutoff=4.0, include_his=False):
    """Salt bridges as unique residue pairs with an Asp/Glu O near a Lys/Arg N."""
    from MDAnalysis.lib.distances import capped_distance
    an = u.select_atoms("(resname ASP and name OD1 OD2) or "
                        "(resname GLU and name OE1 OE2)")
    cat_expr = ("(resname LYS and name NZ) or "
                "(resname ARG and name NH1 NH2 NE)")
    if include_his:
        cat_expr += " or (resname HIS and name ND1 NE2)"
    ca = u.select_atoms(cat_expr)
    if not (len(an) and len(ca)):
        return 0
    pairs, _ = capped_distance(an.positions, ca.positions, max_cutoff=cutoff,
                               min_cutoff=0.5, box=box)
    if not len(pairs):
        return 0
    res = np.stack([an.resindices[pairs[:, 0]], ca.resindices[pairs[:, 1]]], 1)
    return int(len(np.unique(res, axis=0)))


def structure_stats(topology: str, trajectory: Optional[str] = None,
                    frame: int = 0, hbond_cutoff: float = HBOND_DA_MAX,
                    saltbridge_cutoff: float = 4.0,
                    include_his_salt_bridges: bool = False) -> dict:
    """Count bonds, links and interactions for annotating a figure.

    ``hbond_cutoff`` is the donor-acceptor heavy-atom distance limit (Å) of a
    hydrogen bond; the hydrogen-acceptor distance and angle limits stay at
    their defaults."""
    from vmd_agent.inputs.molio import load_universe
    try:
        u = load_universe(topology, trajectory)
    except Exception as e:
        return {"error": f"could not load structure: {e}"}
    if not (hasattr(u.atoms, "names") and hasattr(u.atoms, "resnames")):
        return {"error": "this file has no atom or residue names (is it a "
                         "trajectory?); give a topology such as PDB, PSF or GRO"}
    if trajectory:
        try:
            u.trajectory[frame if frame >= 0 else len(u.trajectory) - 1]
        except Exception:
            pass

    atoms = u.atoms
    elements = _elements(atoms)
    box = None
    try:
        d = np.asarray(u.dimensions, dtype=np.float32)
        if d.shape == (6,) and np.all(np.isfinite(d)) and d[0] > 0:
            box = d
    except Exception:
        box = None

    out = {"n_atoms": int(len(atoms)),
           "n_residues": int(len(atoms.residues)),
           "n_segments": int(len(u.segments))}

    # ---- bonds -------------------------------------------------------------
    # PDB files usually carry only CONECT records for hetero groups and
    # disulfides, so MDAnalysis reports a handful of bonds for a protein with
    # thousands. A complete topology has roughly one bond per atom, so anything
    # far below that is treated as partial and supplemented by inference.
    explicit = None
    try:
        if hasattr(atoms, "bonds") and len(atoms.bonds) > 0:
            explicit = np.asarray(atoms.bonds.indices)
    except Exception:
        explicit = None
    n_heavyish = max(int((~_ion_mask(atoms, elements)).sum()), 1)
    complete = explicit is not None and len(explicit) >= 0.6 * n_heavyish
    if complete:
        bonds_idx, source = explicit, "topology file (explicit bond records)"
    else:
        inferred, why = _infer_bonds(atoms, elements, box)
        if explicit is None:
            bonds_idx, source = inferred, why
        elif inferred is None:
            bonds_idx = explicit
            source = (f"topology file, PARTIAL ({len(explicit)} explicit "
                      "records only); too large to infer the rest")
        else:
            both = np.vstack([np.sort(explicit, axis=1),
                              np.sort(inferred, axis=1)])
            bonds_idx = np.unique(both, axis=0)
            source = (f"topology file, partial ({len(explicit)} explicit "
                      f"records, e.g. CONECT) + {why}")
    out["bond_source"] = source
    out["bonds_explicit"] = int(len(explicit)) if explicit is not None else 0

    if bonds_idx is None:
        out["n_bonds"] = None
        out["bond_note"] = "System too large for distance-based inference."
    else:
        out["n_bonds"] = int(len(bonds_idx))
        pair_counts = Counter()
        if len(bonds_idx):
            a, b = elements[bonds_idx[:, 0]], elements[bonds_idx[:, 1]]
            for x, y in zip(a, b):
                pair_counts["-".join(sorted((x, y)))] += 1
        out["bonds_by_element_pair"] = dict(
            sorted(pair_counts.items(), key=lambda kv: -kv[1])[:12])
        if len(atoms):
            out["mean_bonds_per_atom"] = round(
                2 * len(bonds_idx) / len(atoms), 2)

    # ---- disulfide bridges -------------------------------------------------
    try:
        sg = u.select_atoms("name SG and resname CYS CYX")
        n_ss, ss_pairs = 0, []
        if len(sg) > 1:
            from MDAnalysis.lib.distances import self_capped_distance
            pairs, dists = self_capped_distance(sg.positions, max_cutoff=2.5,
                                                min_cutoff=0.5, box=box)
            for (i, j), dd in zip(pairs, dists):
                n_ss += 1
                ss_pairs.append(
                    f"CYS{int(sg[i].resid)}-CYS{int(sg[j].resid)} "
                    f"({dd:.2f} Å)")
        out["n_disulfide_bridges"] = int(n_ss)
        if ss_pairs:
            out["disulfide_pairs"] = ss_pairs[:12]
    except Exception:
        pass

    # ---- hydrogen bonds ----------------------------------------------------
    try:
        res = count_hydrogen_bonds(u.atoms, box, da_max=hbond_cutoff)
        if res is not None:
            n, method, desc = res
            out["n_hydrogen_bonds"] = int(n)
            out["hbond_method"] = method
            out["hbond_criterion"] = desc
    except Exception as e:                                  # pragma: no cover
        out["hbond_error"] = f"{type(e).__name__}: {e}"

    # ---- salt bridges ------------------------------------------------------
    try:
        if len(u.select_atoms("protein")):
            out["n_salt_bridges"] = _count_salt_bridges(
                u, box, saltbridge_cutoff, include_his_salt_bridges)
            out["saltbridge_criterion"] = (
                f"Asp/Glu carboxylate O within {saltbridge_cutoff} Å of "
                "Lys NZ or Arg N, counted per residue pair"
                + ("" if include_his_salt_bridges
                   else "; His excluded (mostly neutral at pH 7)"))
    except Exception as e:                                  # pragma: no cover
        out["saltbridge_error"] = f"{type(e).__name__}: {e}"

    # ---- composition -------------------------------------------------------
    # Chain IDs are also given to ligands, waters and glycans, so counting all
    # of them over-reports "chains" (a 3-chain protein with its ligand on chain
    # L would read as 4). Count polymer chains by kind, and keep the raw total.
    def _chain_ids(ag):
        try:
            ids = [str(c).strip() or str(s) for c, s in
                   zip(ag.chainIDs, ag.segids)]
        except Exception:
            ids = [str(s) for s in ag.segids]
        return len(set(i for i in ids if i))

    try:
        out["n_chains_all"] = _chain_ids(atoms)
        prot_atoms = u.select_atoms("protein")
        nuc_atoms = u.select_atoms("nucleic")
        if len(prot_atoms):
            out["n_protein_chains"] = _chain_ids(prot_atoms)
        if len(nuc_atoms):
            out["n_nucleic_chains"] = _chain_ids(nuc_atoms)
        # chains of the polymer (protein + nucleic), or all chains if there is no polymer
        out["n_chains"] = (out.get("n_protein_chains", 0)
                           + out.get("n_nucleic_chains", 0)
                           or out["n_chains_all"])
    except Exception:
        pass
    out["elements_present"] = dict(
        sorted(Counter(elements.tolist()).items(), key=lambda kv: -kv[1])[:12])
    if len(u.select_atoms("protein")):
        out["secondary_structure"] = _secondary_structure(u)
    return out


def stats_caption(stats: dict) -> list:
    """Compact human-readable lines for drawing onto a figure."""
    if not stats or stats.get("error"):
        return []
    L = [f"{stats.get('n_atoms', '?')} atoms · "
         f"{stats.get('n_residues', '?')} residues"]
    if stats.get("n_protein_chains"):
        n = stats["n_protein_chains"]
        L[0] += f" · {n} protein chain{'s' if n != 1 else ''}"
    if stats.get("n_nucleic_chains"):
        n = stats["n_nucleic_chains"]
        L[0] += f" · {n} nucleic chain{'s' if n != 1 else ''}"
    if not (stats.get("n_protein_chains") or stats.get("n_nucleic_chains")) \
            and stats.get("n_chains"):
        L[0] += f" · {stats['n_chains']} chains"
    if stats.get("n_bonds") is not None:
        L.append(f"{stats['n_bonds']} bonds "
                 f"({stats.get('mean_bonds_per_atom', '?')} per atom)")
        top = stats.get("bonds_by_element_pair") or {}
        if top:
            L.append("  " + ", ".join(f"{k}: {v}" for k, v in
                                      list(top.items())[:5]))
    if stats.get("bond_source"):
        L.append(f"bonds from {stats['bond_source']}")
    if stats.get("n_disulfide_bridges"):
        L.append(f"{stats['n_disulfide_bridges']} disulfide bridge(s)")
    if stats.get("n_hydrogen_bonds") is not None:
        if stats.get("hbond_method") == "angle":
            L.append(f"{stats['n_hydrogen_bonds']} H-bonds (distance + angle)")
        else:
            L.append(f"{stats['n_hydrogen_bonds']} H-bond candidates "
                     "(heavy-atom distance only; overestimates)")
    if stats.get("n_salt_bridges") is not None:
        L.append(f"{stats['n_salt_bridges']} salt bridge(s)")
    ss = stats.get("secondary_structure") or {}
    if ss.get("helix_percent") is not None:
        L.append(f"{ss['helix_percent']}% helix · {ss['sheet_percent']}% sheet "
                 f"· {ss['coil_percent']}% coil (DSSP)")
    return L
