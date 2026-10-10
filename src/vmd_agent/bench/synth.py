"""Procedural structures that no model can have seen, with every property known.

A language model may recognise ubiquitin or lysozyme from its shape and answer
from memory. These structures are generated from scratch, so a test built on
them (the tool test set, the model benchmark) cannot be passed from memory, while
every property it asks about is still known:

* **design intent** is recorded (chains, helices/strands, ligand placement,
  disulfides);
* **measured truth** is recomputed from the generated coordinates with the same
  routines used for real structures (DSSP, Shrake-Rupley burial, SG-SG
  geometry);
* :func:`design_agreement` compares the two, so the generator is validated, not
  assumed correct.

Folds are idealised and *not* physically realistic: segments are ideal helices
(phi/psi -57/-47) and antiparallel strands joined by straight-line linkers.
They exercise the toolkit's rendering and measurements, and they test whether
a model's reading transfers from memorised proteins to novel ones. They do not
claim to model real proteins, and a result on them says nothing about folding.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_ATOMS = (("N", "N"), ("CA", "C"), ("C", "C"), ("O", "O"), ("CB", "C"))


# ---------------------------------------------------------------- geometry
def _place(a, b, c, length, angle_deg, dihedral_deg):
    """NeRF: position d bonded to c with angle b-c-d and dihedral a-b-c-d."""
    ang, dih = np.radians(angle_deg), np.radians(dihedral_deg)
    bc = c - b
    bc = bc / np.linalg.norm(bc)
    n = np.cross(b - a, bc)
    n = n / np.linalg.norm(n)
    m = np.cross(n, bc)
    d = np.array([-length * np.cos(ang),
                  length * np.sin(ang) * np.cos(dih),
                  length * np.sin(ang) * np.sin(dih)])
    return c + d[0] * bc + d[1] * m + d[2] * n


def backbone_coords(n_res: int, phi: float, psi: float) -> np.ndarray:
    """Ideal polyalanine backbone, ``(n_res, 5, 3)`` for N, CA, C, O, CB."""
    N = np.array([0.0, 0.0, 0.0])
    CA = np.array([1.458, 0.0, 0.0])
    ang = np.radians(111.2)
    C = CA + 1.525 * np.array([-np.cos(ang), np.sin(ang), 0.0])
    out = []
    N_i, CA_i, C_i = N, CA, C
    for _ in range(n_res):
        O_i = _place(N_i, CA_i, C_i, 1.231, 120.8, psi + 180.0)
        CB_i = _place(C_i, N_i, CA_i, 1.53, 110.5, -122.5)
        out.append((N_i, CA_i, C_i, O_i, CB_i))
        N_n = _place(N_i, CA_i, C_i, 1.329, 116.2, psi)
        CA_n = _place(CA_i, C_i, N_n, 1.458, 121.7, 180.0)
        C_n = _place(C_i, N_n, CA_n, 1.525, 111.2, phi)
        N_i, CA_i, C_i = N_n, CA_n, C_n
    return np.array(out)


def _rot_to(v: np.ndarray, target: np.ndarray) -> np.ndarray:
    v = v / np.linalg.norm(v)
    t = target / np.linalg.norm(target)
    c = float(np.dot(v, t))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:
        perp = np.cross(v, [1.0, 0, 0])
        if np.linalg.norm(perp) < 1e-6:
            perp = np.cross(v, [0, 1.0, 0])
        perp /= np.linalg.norm(perp)
        return 2 * np.outer(perp, perp) - np.eye(3)
    ax = np.cross(v, t)
    s = np.linalg.norm(ax)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / s ** 2)


def _oriented(P: np.ndarray, axis: Sequence[float]) -> np.ndarray:
    """Centre a segment and rotate its principal axis onto ``axis``."""
    ca = P[:, 1, :]
    c = ca.mean(0)
    P = P - c
    _u, _s, vt = np.linalg.svd(ca - c)
    ax = vt[0] if np.dot(vt[0], ca[-1] - ca[0]) >= 0 else -vt[0]
    R = _rot_to(ax, np.asarray(axis, float))
    return P @ R.T


def _rotz(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def _random_rotation(rng) -> np.ndarray:
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


# ------------------------------------------------------------------ folds
def _helix(n: int, rng) -> np.ndarray:
    return _oriented(backbone_coords(n, -57.0, -47.0), [0, 0, 1.0])


def _dssp_codes(residues: Sequence[np.ndarray]) -> str:
    """DSSP codes for residue arrays ``(5, 3)`` held in a throw-away Universe."""
    import MDAnalysis as mda
    from vmd_agent.structure.dssp import assign_dssp
    n = len(residues)
    u = mda.Universe.empty(n * 5, n_residues=n,
                           atom_resindex=np.repeat(np.arange(n), 5),
                           trajectory=True)
    u.add_TopologyAttr("names", ["N", "CA", "C", "O", "CB"] * n)
    u.add_TopologyAttr("resnames", ["ALA"] * n)
    u.add_TopologyAttr("resids", list(range(1, n + 1)))
    u.add_TopologyAttr("elements", ["N", "C", "C", "O", "C"] * n)
    u.add_TopologyAttr("segids", ["A"])
    u.add_TopologyAttr("chainIDs", ["A"] * (n * 5))
    u.atoms.positions = np.concatenate(list(residues)).astype(np.float32)
    return assign_dssp(u.atoms)["codes"]


_SHEET_CACHE: Dict[Tuple[int, int], Tuple[float, float]] = {}


def _strands_for(m: int, length: int, dy: float, shift: float
                 ) -> List[np.ndarray]:
    base = _oriented(backbone_coords(length, -120.0, 130.0), [1.0, 0, 0])
    out = []
    for i in range(m):
        P = base.copy()
        if i % 2 == 1:
            P = P @ np.diag([-1.0, -1.0, 1.0]).T
            P[:, :, 0] += shift
        P[:, :, 1] += i * dy
        out.append(P)
    return out


def _strand_set(m: int, length: int, rng) -> List[np.ndarray]:
    """Antiparallel sheet whose strand spacing/register is chosen so DSSP
    recognises the strands (grid search, cached per size)."""
    key = (m, length)
    if key not in _SHEET_CACHE:
        best, arg = -1, (4.5, 2.0)
        for dy in (4.4, 4.5, 4.6, 4.8, 5.0):
            for shift in np.arange(-4.0, 4.01, 0.5):
                st = _strands_for(m, length, dy, float(shift))
                n_e = _dssp_codes([r for P in st for r in P]).count("E")
                if n_e > best:
                    best, arg = n_e, (dy, float(shift))
        _SHEET_CACHE[key] = arg
    dy, shift = _SHEET_CACHE[key]
    return _strands_for(m, length, dy, shift)


def _linker(a: np.ndarray, b: np.ndarray, n: int = 2) -> List[np.ndarray]:
    """Straight-line coil residues between two CA positions."""
    res = []
    for i in range(1, n + 1):
        ca = a + (b - a) * i / (n + 1)
        res.append(np.array([ca + [-1.2, 0.6, 0.0], ca, ca + [1.2, 0.6, 0.0],
                             ca + [1.8, 1.6, 0.0], ca + [0.0, -0.8, 1.3]]))
    return res


def _chain_from_segments(segs: List[Tuple[np.ndarray, str]]
                         ) -> Tuple[np.ndarray, List[str]]:
    """Concatenate segments with 2-residue linkers; return residues + SS design."""
    residues: List[np.ndarray] = []
    design: List[str] = []
    for i, (P, lab) in enumerate(segs):
        if i:
            for r in _linker(residues[-1][1], P[0, 1]):
                residues.append(r)
                design.append("C")
        for r in P:
            residues.append(r)
            design.append(lab)
    return np.array(residues), design


def build_fold(kind: str, rng) -> Tuple[np.ndarray, List[str], dict]:
    """One chain of the requested fold type.

    kinds: ``helical`` (helix bundle), ``sheet`` (antiparallel sheet),
    ``mixed`` (sheet with helices packed on one face), ``coil``
    (short disordered pieces).
    """
    segs: List[Tuple[np.ndarray, str]] = []
    info = {"kind": kind}
    if kind == "helical":
        k = int(rng.integers(3, 7))
        R = max(5.0 / np.sin(np.pi / k), 6.5)
        info["n_helices"] = k
        info["n_strands"] = 0
        for i in range(k):
            n = int(rng.integers(11, 23))
            H = _helix(n, rng)
            if i % 2:
                H = H @ np.diag([1.0, -1.0, -1.0]).T          # antiparallel
            H = H @ _rotz(rng.uniform(0, 2 * np.pi)).T
            th = 2 * np.pi * i / k
            H = H + [R * np.cos(th), R * np.sin(th), 0.0]
            segs.append((H, "H"))
    elif kind in ("sheet", "mixed"):
        m = int(rng.integers(4, 7))
        L = int(rng.integers(5, 9))
        strands = _strand_set(m, L, rng)
        info["n_strands"] = m
        info["n_helices"] = 0
        for S in strands:
            segs.append((S, "E"))
        if kind == "mixed":
            n_h = int(rng.integers(2, 4))
            info["n_helices"] = n_h
            width = m * 4.7
            for j in range(n_h):
                n = int(rng.integers(12, 20))
                H = _oriented(backbone_coords(n, -57.0, -47.0), [1.0, 0, 0])
                H = H + [3.0, width * (j + 0.5) / n_h, 10.5]
                segs.append((H, "H"))
    elif kind == "coil":
        info["n_helices"] = info["n_strands"] = 0
        for _ in range(int(rng.integers(3, 6))):
            n = int(rng.integers(4, 8))
            P = _oriented(backbone_coords(n, rng.uniform(-150, -60),
                                          rng.uniform(-60, 160)), [0, 0, 1.0])
            P = P @ _random_rotation(rng).T + rng.normal(0, 7, 3)
            segs.append((P, "C"))
    else:
        raise ValueError(f"unknown fold kind '{kind}'")
    residues, design = _chain_from_segments(segs)
    return residues, design, info


# --------------------------------------------------------------- assembly
_LIGAND = [("C1", "C", (1.4, 0.0, 0.0)), ("C2", "C", (0.7, 1.21, 0.0)),
           ("C3", "C", (-0.7, 1.21, 0.0)), ("C4", "C", (-1.4, 0.0, 0.0)),
           ("N1", "N", (-0.7, -1.21, 0.0)), ("O1", "O", (0.7, -1.21, 0.0))]


def _most_buried_point(prot_xyz: np.ndarray, centre: np.ndarray, rng,
                       n_candidates: int = 80) -> np.ndarray:
    """Pick a clash-free ligand position near ``centre`` with maximal burial."""
    from vmd_agent.evidence.claims import _sasa
    radii_lig = np.array([1.7, 1.7, 1.7, 1.7, 1.55, 1.52])
    ring = np.array([o for _n, _e, o in _LIGAND], float)
    best, best_pt = -1.0, centre
    for _ in range(n_candidates):
        pt = centre + rng.normal(0, 4.0, 3)
        xyz = ring + pt
        d = np.linalg.norm(xyz[:, None] - prot_xyz[None], axis=2).min()
        if d < 3.0:
            continue
        alone = _sasa(xyz, radii_lig)
        near = prot_xyz[np.linalg.norm(prot_xyz - pt, axis=1) < 14.0]
        shielded = _sasa(xyz, radii_lig, near, np.full(len(near), 1.7))
        frac = 1.0 - shielded / alone if alone > 0 else 0.0
        if frac > best:
            best, best_pt = frac, pt
    return best_pt


def _add_disulfides(chain_res: np.ndarray, n_pairs: int, rng
                    ) -> Tuple[Dict[int, np.ndarray], int]:
    """Choose residue pairs with nearby CB atoms and place SG atoms 2.05 Å apart."""
    cb = chain_res[:, 4, :]
    n = len(cb)
    d = np.linalg.norm(cb[:, None] - cb[None], axis=2)
    cand = [(i, j) for i in range(n) for j in range(i + 4, n)
            if 3.4 < d[i, j] < 6.2]
    rng.shuffle(cand)
    used, sg, placed = set(), {}, 0
    for i, j in cand:
        if placed >= n_pairs:
            break
        if i in used or j in used:
            continue
        mid = (cb[i] + cb[j]) / 2
        u = (cb[j] - cb[i]) / np.linalg.norm(cb[j] - cb[i])
        sg[i], sg[j] = mid - u * 1.025, mid + u * 1.025
        used.update((i, j))
        placed += 1
    return sg, placed


def assemble(spec: dict, rng) -> Tuple[List[tuple], dict]:
    """Atoms (``name, resname, resid, chain, x, y, z, element``) and design."""
    chains_atoms: List[tuple] = []
    design_chains = []
    cursor = 0.0
    centres = []
    resid = 1
    n_ss = {"H": 0, "E": 0, "C": 0}
    total_sg = 0
    first_chain_ca = None
    for ci in range(spec["n_chains"]):
        res, ss, info = build_fold(spec["fold"], rng)
        R = _random_rotation(rng) if ci else np.eye(3)
        res = res @ R.T
        res = res + [cursor - res[:, 1, 0].min(), 0.0, 0.0]
        cursor = float(res[:, 1, 0].max()) + 28.0
        sg, placed = _add_disulfides(res, spec.get("n_disulfides", 0)
                                     if ci == 0 else 0, rng)
        total_sg += placed
        chain_id = chr(ord("A") + ci)
        for r in range(len(res)):
            rn = "CYS" if r in sg else "ALA"
            for (nm, el), p in zip(_ATOMS, res[r]):
                chains_atoms.append((nm, rn, resid + r, chain_id,
                                     p[0], p[1], p[2], el))
            if r in sg:
                p = sg[r]
                chains_atoms.append(("SG", "CYS", resid + r, chain_id,
                                     p[0], p[1], p[2], "S"))
            n_ss[ss[r]] += 1
        resid += len(res) + 1
        centres.append(res[:, 1, :].mean(0))
        if first_chain_ca is None:
            first_chain_ca = res[:, 1, :]
        design_chains.append(info)

    placement = spec.get("ligand")
    if placement in ("buried", "exposed"):
        ca = first_chain_ca
        centre = ca.mean(0)
        prot = np.array([[a[4], a[5], a[6]] for a in chains_atoms])
        if placement == "exposed":
            d = rng.normal(size=3)
            d /= np.linalg.norm(d)
            centre = centre + d * (np.linalg.norm(ca - centre, axis=1).max()
                                   + 12.0)
        else:
            centre = _most_buried_point(prot, centre, rng)
        for nm, el, off in _LIGAND:
            p = centre + np.array(off)
            chains_atoms.append((nm, "LIG", 900, "L", p[0], p[1], p[2], el))
    n_res = sum(n_ss.values())
    design = {
        "fold": spec["fold"], "n_chains": spec["n_chains"],
        "n_helices_per_chain": design_chains[0].get("n_helices", 0),
        "n_strands_per_chain": design_chains[0].get("n_strands", 0),
        "ligand": placement or "none",
        "n_disulfides": total_sg,
        "n_residues": n_res,
        "designed_helix_percent": 100.0 * n_ss["H"] / n_res,
        "designed_sheet_percent": 100.0 * n_ss["E"] / n_res,
        "designed_fold_class": {"helical": "alpha", "sheet": "beta",
                                "mixed": "mixed", "coil": "coil"}[spec["fold"]],
    }
    return chains_atoms, design


def write_pdb(atoms: Sequence[tuple], path: str) -> str:
    lines = []
    prev_chain = None
    serial = 1
    for (name, resn, resid, chain, x, y, z, el) in atoms:
        if prev_chain is not None and chain != prev_chain:
            lines.append("TER")
        rec = "HETATM" if resn == "LIG" else "ATOM  "
        lines.append(f"{rec}{serial:5d} {name:<4s} {resn:>3s} {chain}"
                     f"{resid % 10000:4d}    {x:8.3f}{y:8.3f}{z:8.3f}"
                     f"  1.00  0.00          {el:>2s}")
        serial += 1
        prev_chain = chain
    lines += ["TER", "END"]
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


# ------------------------------------------------------------- generation
def sample_spec(rng, weights: Optional[dict] = None) -> dict:
    w = {"fold": [("helical", .3), ("sheet", .25), ("mixed", .25),
                  ("coil", .2)],
         "chains": [(1, .5), (2, .25), (3, .15), (4, .10)],
         "ligand": [("none", .4), ("buried", .3), ("exposed", .3)],
         "ss": [(0, .6), (1, .25), (2, .15)]}
    if weights:
        w.update(weights)

    def pick(opts):
        vals, p = zip(*opts)
        return vals[int(rng.choice(len(vals), p=np.asarray(p) / sum(p)))]

    spec = {"fold": pick(w["fold"]), "n_chains": pick(w["chains"]),
            "ligand": pick(w["ligand"]), "n_disulfides": pick(w["ss"])}
    if spec["fold"] == "coil":
        spec["n_disulfides"] = 0
    return spec


def _sha256(path: str) -> str:
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def generate_set(n: int, out_dir: str, seed: int = 0,
                 weights: Optional[dict] = None) -> List[dict]:
    """Write ``n`` structures plus ``design.json``; return ``[{path, design, sha256}]``.

    **A seed does not guarantee identical structures across machines.** The
    construction involves floating-point geometry followed by discrete choices
    (where a ligand sits, which cysteines pair); different NumPy/BLAS builds
    change the last digits and a threshold can then flip. Generate the set
    once, keep the files, and share their ``sha256`` values (recorded in
    ``design.json``) instead of relying on the seed."""
    rng = np.random.default_rng(seed)
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for i in range(n):
        spec = sample_spec(rng, weights)
        atoms, design = assemble(spec, rng)
        design["id"] = f"synth_{i:04d}"
        design["seed"] = seed
        path = write_pdb(atoms, os.path.join(out_dir, f"{design['id']}.pdb"))
        items.append({"path": path, "design": design,
                      "sha256": _sha256(path)})
    with open(os.path.join(out_dir, "design.json"), "w") as fh:
        json.dump(items, fh, indent=1)
    return items


# --------------------------------------------------- generator validation
def design_agreement(design: dict, truth: dict) -> dict:
    """Does the measured truth match what the generator intended?

    Booleans per property; ``fold_class`` compares the intended class with
    the measured DSSP class (raw helix percentages are not compared because an
    n-residue helix can yield at most n-4 helical assignments). This is the generator's own test: if DSSP, burial or the
    disulfide detector disagreed with construction, the structure set would
    not be a trustworthy benchmark.
    """
    out = {
        "n_chains": truth["n_protein_chains"] == design["n_chains"],
        "has_ligand": truth["has_ligand"] == (design["ligand"] != "none"),
        "n_disulfides": truth.get("n_disulfides") == design["n_disulfides"],
    }
    if truth.get("fold_class") is not None:
        out["fold_class"] = truth["fold_class"] == design["designed_fold_class"]
    if design["ligand"] != "none" and truth.get("ligand_buried") is not None:
        out["ligand_placement"] = (truth["ligand_buried"]
                                   == (design["ligand"] == "buried"))
    return out


def validate_generator(items: Sequence[dict]) -> dict:
    """Aggregate :func:`design_agreement` over a generated set."""
    from vmd_agent.bench.truth import ground_truth
    keys: Dict[str, List[bool]] = {}
    rows = []
    for it in items:
        t = ground_truth(it["path"])
        if not t.get("ok"):
            continue
        ag = design_agreement(it["design"], t)
        rows.append({"id": it["design"]["id"], **ag})
        for k, v in ag.items():
            keys.setdefault(k, []).append(bool(v))
    return {"n": len(rows),
            "agreement": {k: sum(v) / len(v) for k, v in keys.items()},
            "rows": rows}
