"""Secondary-structure assignment (Kabsch-Sander DSSP) in plain NumPy.

``MDAnalysis.analysis.dssp`` only exists from MDAnalysis 2.8, which needs
Python >= 3.10. The previous code imported it inside a bare ``except`` and so
reported "secondary structure unavailable" on every older install. This module
implements the DSSP hydrogen-bond-energy algorithm directly so secondary
structure is always available and always labelled with its source.

Algorithm (Kabsch & Sander, Biopolymers 1983)
---------------------------------------------
1. Place the amide hydrogen 1.0 Å from N, opposite the preceding C=O.
2. Electrostatic H-bond energy
   ``E = 0.084 * 332 * (1/r(ON) + 1/r(CH) - 1/r(OH) - 1/r(CN))`` kcal/mol;
   a bond exists when ``E < -0.5``.
3. n-turns (n = 3, 4, 5) are NH(i+n) -> CO(i) bonds; two consecutive n-turns
   form a G / H / I helix.
4. Bridges are parallel or antiparallel pairs of bonded residues; ladders of
   two or more bridges are strands (E), isolated ones are B.
5. Remaining turn residues are T and CA-CA-CA bends above 70 degrees are S.

Residues with no CA atom are assigned ``'?'``; ``'-'`` is coil, as in DSSP. Output is 8-state; :func:`three_state` collapses it.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np

_Q = 0.084 * 332.0
_HB_CUT = -0.5
_PEPTIDE_BOND_MAX = 2.5          # Å, C(i-1)-N(i) for a connected pair


def _backbone(ag):
    """Return per-residue N, CA, C, O coordinates (NaN where absent)."""
    res = ag.residues
    n = len(res)
    out = {k: np.full((n, 3), np.nan) for k in ("N", "CA", "C", "O")}
    names = ag.names
    resindex = ag.resindices
    first = {r.resindex: i for i, r in enumerate(res)}
    pos = ag.positions
    for a_name, a_ri, a_pos in zip(names, resindex, pos):
        i = first.get(a_ri)
        if i is None:
            continue
        key = "O" if a_name in ("O", "OXT") and np.isnan(out["O"][i, 0]) \
            else a_name
        if key in out and np.isnan(out[key][i, 0]):
            out[key][i] = a_pos
    return out, [r.resname.upper() for r in res], \
        [int(r.resid) for r in res]


def _hbond_pairs(bb, resnames) -> set:
    """Set of ``(i, j)`` with an NH(i) -> CO(j) bond (sparse: O(n) entries)."""
    N, CA, C, O = bb["N"], bb["CA"], bb["C"], bb["O"]
    n = len(N)
    H = np.full((n, 3), np.nan)
    for i in range(1, n):
        if resnames[i] == "PRO":
            continue
        if np.any(np.isnan(C[i - 1])) or np.any(np.isnan(O[i - 1])) \
                or np.any(np.isnan(N[i])):
            continue
        if np.linalg.norm(C[i - 1] - N[i]) > _PEPTIDE_BOND_MAX:
            continue                                   # chain break
        v = C[i - 1] - O[i - 1]
        nv = np.linalg.norm(v)
        if nv > 0:
            H[i] = N[i] + v / nv
    pairs = set()
    ca_ok = np.where(~np.isnan(CA[:, 0]))[0]
    if not len(ca_ok):
        return pairs
    try:
        from scipy.spatial import cKDTree
        tree = cKDTree(CA[ca_ok])
        cand = tree.query_pairs(9.0, output_type="ndarray")
        cand = np.vstack([cand, cand[:, ::-1]]) if len(cand) else cand
        cand = [(int(ca_ok[a]), int(ca_ok[b])) for a, b in cand]
    except Exception:                                  # pragma: no cover
        d = np.linalg.norm(CA[ca_ok, None] - CA[None, ca_ok], axis=-1)
        ii, jj = np.where((d < 9.0) & (d > 0))
        cand = [(int(ca_ok[a]), int(ca_ok[b])) for a, b in zip(ii, jj)]
    for a, b in cand:
        if abs(a - b) < 2 or np.isnan(H[a, 0]) \
                or np.any(np.isnan(O[b])) or np.any(np.isnan(C[b])):
            continue
        r_on = np.linalg.norm(O[b] - N[a])
        r_ch = np.linalg.norm(C[b] - H[a])
        r_oh = np.linalg.norm(O[b] - H[a])
        r_cn = np.linalg.norm(C[b] - N[a])
        if min(r_on, r_ch, r_oh, r_cn) < 0.5:
            continue
        e = _Q * (1 / r_on + 1 / r_ch - 1 / r_oh - 1 / r_cn)
        if e < _HB_CUT:
            pairs.add((a, b))
    return pairs


def assign_dssp(atomgroup) -> dict:
    """Assign DSSP codes to the protein residues of ``atomgroup``.

    Returns ``{"codes": str, "resids": [...], "resnames": [...]}`` with one
    character per residue.
    """
    prot = atomgroup.select_atoms("protein")
    if not len(prot):
        return {"codes": "", "resids": [], "resnames": [], "chains": []}
    bb, resnames, resids = _backbone(prot)
    n = len(resids)
    hb = _hbond_pairs(bb, resnames)

    def turn(i: int, k: int) -> bool:                  # NH(i+k) -> CO(i)
        return 0 <= i and i + k < n and (i + k, i) in hb

    code = np.array(["?"] * n, dtype="<U1")
    present = ~np.isnan(bb["CA"][:, 0])
    code[present] = " "

    # --- helices (H > G > I priority applied by writing in reverse order) ---
    for k, ch in ((5, "I"), (3, "G"), (4, "H")):
        for i in range(1, n - k + 1):
            if turn(i - 1, k) and turn(i, k):
                for r in range(i, min(i + k, n)):
                    if code[r] in (" ", "T", "S", "I", "G") or ch == "H":
                        code[r] = ch

    # --- bridges / ladders (sparse: work from the bond list) ---------------
    # Kabsch-Sander write Hbond(i, j) for CO(i) -> NH(j); ``hb`` stores the
    # transpose, (NH, CO), so every condition below is that definition with
    # its arguments swapped.
    par, anti = set(), set()
    for (p, q) in hb:
        # parallel: Hbond(i-1,j)&Hbond(j,i+1)  ==  (j,i-1)&(i+1,j) in hb
        if (q + 2, p) in hb and abs(q + 1 - p) >= 3:
            par.add((q + 1, p)); par.add((p, q + 1))
        # antiparallel (a): Hbond(i,j)&Hbond(j,i)
        if (q, p) in hb and abs(p - q) >= 3:
            anti.add((p, q)); anti.add((q, p))
        # antiparallel (b): Hbond(i-1,j+1)&Hbond(j-1,i+1)
        #                   ==  (j+1,i-1)&(i+1,j-1) in hb
        if (q + 2, p - 2) in hb and abs(q + 1 - (p - 1)) >= 3:
            anti.add((q + 1, p - 1)); anti.add((p - 1, q + 1))
    in_bridge = np.zeros(n, dtype=bool)
    in_ladder = np.zeros(n, dtype=bool)
    for (i, j) in par:
        in_bridge[i] = True
        if (i + 1, j + 1) in par or (i - 1, j - 1) in par:
            in_ladder[i] = True
    for (i, j) in anti:
        in_bridge[i] = True
        if (i + 1, j - 1) in anti or (i - 1, j + 1) in anti:
            in_ladder[i] = True
    for i in range(n):
        if code[i] in (" ", "T", "S"):
            if in_ladder[i]:
                code[i] = "E"
            elif in_bridge[i]:
                code[i] = "B"

    # --- turns and bends ----------------------------------------------------
    for k in (3, 4, 5):
        for i in range(n - k):
            if turn(i, k):
                for r in range(i + 1, i + k):
                    if code[r] == " ":
                        code[r] = "T"
    CA = bb["CA"]
    for i in range(2, n - 2):
        if code[i] == " " and not np.any(np.isnan(CA[[i - 2, i, i + 2]])):
            v1, v2 = CA[i] - CA[i - 2], CA[i + 2] - CA[i]
            c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            if np.degrees(np.arccos(np.clip(c, -1, 1))) > 70.0:
                code[i] = "S"
    code[code == " "] = "-"
    chains = []
    for r in prot.residues:
        try:
            c = str(r.atoms[0].chainID).strip()
        except Exception:
            c = ""
        chains.append(c or str(r.segment.segid))
    return {"codes": "".join(code), "resids": resids, "resnames": resnames,
            "chains": chains}


def three_state(codes: str) -> str:
    """Collapse 8-state DSSP to H (helix) / E (strand) / C (coil)."""
    m = {"H": "H", "G": "H", "I": "H", "E": "E", "B": "E"}
    return "".join(m.get(c, "C") for c in codes)


def secondary_structure_fractions(atomgroup) -> Optional[dict]:
    """Helix / sheet / coil percentages with the method named."""
    try:
        res = assign_dssp(atomgroup)
    except Exception as e:                                 # pragma: no cover
        return {"note": f"DSSP failed: {type(e).__name__}: {e}"}
    codes = res["codes"]
    assessed = [c for c in codes if c != "?"]
    if not assessed:
        return {"note": "no residues with a complete backbone for DSSP"}
    t = three_state("".join(assessed))
    n = len(t)
    c = Counter(t)
    return {"helix_percent": round(100 * c["H"] / n, 1),
            "sheet_percent": round(100 * c["E"] / n, 1),
            "coil_percent": round(100 * c["C"] / n, 1),
            "n_residues_assessed": n,
            "source": "built-in Kabsch-Sander DSSP (NumPy)",
            "codes": codes}
