"""Cross-check the toolkit's numbers against independent implementations.

``cross_check`` recomputes RMSD (Kabsch superposition via SVD), radius of
gyration, selection-selection contacts and centre-of-mass distance with plain
NumPy, shares no code with :mod:`vmd_agent.dynamics.analysis`, and reports the largest
disagreement. A reviewer, or a user with a new force field or file format, can
run it on their own trajectory to confirm the analysis agrees with first
principles before trusting a figure.

It does **not** compare against GROMACS, cpptraj or VMD themselves; see
``docs/reference/RESEARCH.md`` (Appendix F, "Not verified") for how to do that comparison by hand.
"""
from __future__ import annotations

import tempfile
from typing import Optional

import numpy as np


def _kabsch_rmsd(P: np.ndarray, Q: np.ndarray) -> float:
    P = P - P.mean(0)
    Q = Q - Q.mean(0)
    U, _S, Vt = np.linalg.svd(P.T @ Q)
    d = np.sign(np.linalg.det(U @ Vt))
    R = U @ np.diag([1.0, 1.0, d]) @ Vt
    return float(np.sqrt(np.mean(np.sum((P @ R - Q) ** 2, axis=1))))


def cross_check(topology: str, trajectory: str, selection: str = "protein",
                sel2: Optional[str] = None, cutoff: float = 4.5,
                rtol: float = 0.01, atol: float = 0.02) -> dict:
    """Compare analysis results with independent NumPy implementations."""
    from vmd_agent.dynamics.analysis import analyze_trajectory
    from vmd_agent.inputs.molio import load_universe

    u = load_universe(topology, trajectory)
    ag = u.select_atoms(selection)
    if not len(ag):
        return {"ok": False, "error": f"selection '{selection}' matched 0 atoms"}
    masses = ag.masses
    ref = None
    rmsd, rg = [], []
    for _ in u.trajectory:
        x = ag.positions.astype(float)
        if ref is None:
            ref = x.copy()
        rmsd.append(_kabsch_rmsd(x, ref))
        com = (x * masses[:, None]).sum(0) / masses.sum()
        rg.append(np.sqrt((masses * ((x - com) ** 2).sum(1)).sum()
                          / masses.sum()))
    want = ["rmsd", "rgyr"]
    contacts_exp = com_exp = None
    if sel2:
        b = u.select_atoms(sel2)
        contacts_exp, com_exp = [], []
        for _ in u.trajectory:
            d = np.linalg.norm(ag.positions[:, None] - b.positions[None],
                               axis=2)
            contacts_exp.append(int((d < cutoff).sum()))
            com_exp.append(float(np.linalg.norm(
                ag.center_of_mass() - b.center_of_mass())))
        want += ["contacts", "distance"]
    got = analyze_trajectory(topology, trajectory, analyses=want,
                             selection=selection, sel2=sel2, cutoff=cutoff,
                             out_dir=tempfile.mkdtemp(prefix="vmd_agent_xcheck_"))
    res = got["results"]
    rows = []

    def row(name, expected, key):
        r = res.get(key, {})
        if r.get("error"):
            rows.append({"quantity": name, "ok": False, "error": r["error"]})
            return
        e = float(np.mean(expected))
        g = float(r["summary"]["mean"])
        diff = abs(g - e)
        rows.append({"quantity": name, "independent": e, "toolkit": g,
                     "abs_diff": diff,
                     "ok": bool(diff <= atol + rtol * abs(e))})

    row("RMSD to frame 0 (Å, Kabsch)", rmsd, "rmsd")
    row("radius of gyration (Å, mass-weighted)", rg, "rgyr")
    if sel2:
        row(f"atom contacts < {cutoff} Å", contacts_exp, "contacts")
        row("COM distance (Å)", com_exp, "distance")
    return {"ok": all(r["ok"] for r in rows), "n_frames": len(rmsd),
            "tolerance": {"rtol": rtol, "atol": atol}, "rows": rows,
            "note": "Agreement with independent NumPy implementations of the "
                    "same definitions. It does not validate the physics or "
                    "compare against GROMACS/cpptraj/VMD."}


def table_markdown(result: dict) -> str:
    L = ["| quantity | independent | toolkit | abs. diff | agree |",
         "|---|---|---|---|---|"]
    for r in result["rows"]:
        if "error" in r:
            L.append(f"| {r['quantity']} | – | – | – | ERROR: {r['error']} |")
        else:
            L.append(f"| {r['quantity']} | {r['independent']:.4f} | "
                     f"{r['toolkit']:.4f} | {r['abs_diff']:.2g} | "
                     f"{'yes' if r['ok'] else 'NO'} |")
    return "\n".join(L) + "\n"


# ------------------------------------------------ DSSP vs PDB annotation
def parse_pdb_ss_records(path: str) -> dict:
    """Per-residue 3-state reference from the HELIX / SHEET records of a PDB file.

    Returns ``{(chain, resid): "H" | "E"}``; residues in neither are coil.
    These records are produced by the PDB's annotation pipeline (DSSP-based,
    sometimes author-edited), so they are an *external consistency check*, not
    ground truth and not identical to ``mkdssp`` output.
    """
    ref = {}

    def span(chain1, a, chain2, b, code):
        try:
            a, b = int(a), int(b)
        except ValueError:
            return
        if chain1.strip() != chain2.strip():
            return
        for r in range(a, b + 1):
            ref.setdefault((chain1.strip(), r), code)

    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("HELIX "):
                span(line[19], line[21:25], line[31], line[33:37], "H")
            elif line.startswith("SHEET "):
                span(line[21], line[22:26], line[32], line[33:37], "E")
    return ref


def dssp_vs_records(path: str) -> dict:
    """Compare the built-in DSSP with a PDB file's own HELIX/SHEET records."""
    import MDAnalysis as mda
    from vmd_agent.structure.dssp import assign_dssp, three_state

    ref = parse_pdb_ss_records(path)
    if not ref:
        return {"ok": False, "path": path,
                "error": "no HELIX/SHEET records to compare against"}
    u = mda.Universe(path)
    res = assign_dssp(u.atoms)
    mine = three_state(res["codes"])
    truth, pred = [], []
    for code3, key in zip(mine, zip(res["chains"], res["resids"])):
        if res["codes"][len(pred)] == "?":
            truth.append(None)
            pred.append(code3)
            continue
        truth.append(ref.get(key, "C"))
        pred.append(code3)
    pairs = [(t, p) for t, p in zip(truth, pred) if t is not None]
    n = len(pairs)
    if not n:
        return {"ok": False, "path": path, "error": "no residues compared"}
    out = {"ok": True, "path": path, "n_residues": n,
           "q3": sum(t == p for t, p in pairs) / n}
    for cls in ("H", "E"):
        tp = sum(t == cls and p == cls for t, p in pairs)
        fp = sum(t != cls and p == cls for t, p in pairs)
        fn = sum(t == cls and p != cls for t, p in pairs)
        out[f"{cls}_precision"] = tp / (tp + fp) if tp + fp else None
        out[f"{cls}_recall"] = tp / (tp + fn) if tp + fn else None
        out[f"{cls}_fraction_reference"] = sum(t == cls for t, _ in pairs) / n
    return out


def dssp_benchmark(pdb_ids, cache_dir: str) -> dict:
    """Download PDB entries and aggregate :func:`dssp_vs_records`."""
    from vmd_agent.inputs.fetch import fetch_structure
    rows, skipped = [], []
    for pid in pdb_ids:
        got = fetch_structure(pid, out_dir=cache_dir, file_format="pdb")
        if not got.get("ok") or got.get("format") != "pdb":
            skipped.append({"id": pid, "reason": got.get("error", "no PDB file")})
            continue
        try:
            r = dssp_vs_records(got["path"])
        except Exception as e:                              # pragma: no cover
            skipped.append({"id": pid, "reason": f"{type(e).__name__}: {e}"})
            continue
        if not r.get("ok"):
            skipped.append({"id": pid, "reason": r["error"]})
            continue
        r["id"] = pid.upper()
        rows.append(r)
    if not rows:
        return {"ok": False, "rows": [], "skipped": skipped}
    q3 = np.array([r["q3"] for r in rows])
    tot = sum(r["n_residues"] for r in rows)
    return {"ok": True, "n_structures": len(rows), "n_residues": tot,
            "q3_mean": float(q3.mean()), "q3_median": float(np.median(q3)),
            "q3_min": float(q3.min()), "q3_max": float(q3.max()),
            "q3_residue_weighted": float(sum(r["q3"] * r["n_residues"]
                                             for r in rows) / tot),
            "rows": rows, "skipped": skipped}


def dssp_vs_mdtraj(path: str) -> dict:
    """Compare the built-in DSSP with MDTraj's independent implementation.

    Reports three agreements per structure so annotation differences can be
    separated from implementation differences:

    ``q3_vs_mdtraj``           this toolkit vs MDTraj (implementation check)
    ``q3_mine_vs_records``     this toolkit vs the PDB HELIX/SHEET records
    ``q3_mdtraj_vs_records``   MDTraj vs the same records (the ceiling an
                               established implementation reaches here)

    Requires ``mdtraj`` (``pip install mdtraj``); it is not a dependency.
    """
    try:
        import mdtraj as md
    except ImportError:
        return {"ok": False, "error": "mdtraj is not installed"}
    import MDAnalysis as mda
    from vmd_agent.structure.dssp import assign_dssp, three_state

    ref = parse_pdb_ss_records(path)
    if not ref:
        return {"ok": False, "path": path, "error": "no HELIX/SHEET records"}
    res = assign_dssp(mda.Universe(path).atoms)
    keep = [i for i, c in enumerate(res["codes"]) if c != "?"]
    mine = [three_state(res["codes"])[i] for i in keep]
    keys = [(res["chains"][i], res["resids"][i]) for i in keep]

    traj = md.load(path)
    codes = md.compute_dssp(traj[0], simplified=True)[0]
    prot = [r for r in traj.topology.residues if r.is_protein]
    if len(prot) != len(res["codes"]):
        return {"ok": False, "path": path,
                "error": f"residue count differs ({len(prot)} vs "
                         f"{len(res['codes'])}); cannot align"}
    theirs = [str(codes[prot[i].index]) for i in keep]
    theirs = ["C" if c in ("NA", " ") else c for c in theirs]
    truth = [ref.get(k, "C") for k in keys]
    n = len(keep)
    q = lambda a, b: sum(x == y for x, y in zip(a, b)) / n
    return {"ok": True, "path": path, "n_residues": n,
            "q3_vs_mdtraj": q(mine, theirs),
            "q3_mine_vs_records": q(mine, truth),
            "q3_mdtraj_vs_records": q(theirs, truth)}
