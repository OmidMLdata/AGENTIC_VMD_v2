"""Task suite for the VMD-automation benchmark.

Each task is a natural-language request an analyst might give an assistant:
measure something on a trajectory, find when a structural event starts, notice
that the data are damaged, write a selection, produce a figure at the right
moment, describe a system without saying anything false.

**Ground truth never comes from a model or from the code under test.** It is
either computed here with independent NumPy/SciPy code on the coordinates, or
it is known by construction because the event or the defect was injected into a
real trajectory (:mod:`vmd_agent.bench.events`).

Families
--------
``measure``    a number from a trajectory (RMSD, Rg, a distance, elapsed time);
               one task has an untrustworthy file header
``event``      onset frame of an injected event, or ``null`` on a control
``diagnosis``  a clean trajectory or one with a defect: periodic-boundary
               splitting, atom-count mismatch, NaN coordinates
``selection``  an atom selection scored by atom-set overlap with the truth
``keyframes``  a rendered figure plus frame numbers that capture a transition
``report``     a short factual description scored by claim verification

What the generated files reveal: file names are anonymous and no truth is in a
workspace. The suite directory holds ``tasks.json`` (public) and
``truth.json`` (never shown to an agent).
"""
from __future__ import annotations

import json
import os
import shutil
import warnings
from typing import Dict, List, Optional, Sequence

import numpy as np

from vmd_agent.bench import events as E

FAMILIES = ("measure", "event", "diagnosis", "selection", "keyframes",
            "report")
ISSUES = ("none", "pbc_broken", "atom_count_mismatch", "nonfinite_coordinates")

N_FRAMES = 120                       # length of generated event trajectories
EVENT_PRESETS = {                    # unmistakable events; see docs
    "hinge": 40.0, "dissociation": 8.0, "expansion": 0.08}
NEAR_CUTOFF = 4.5
INTERFACE_CUTOFF = 5.0
BOX = 45.0

_ANSWER_COMMON = (
    '"issues": [data problems you noticed, empty list if none], '
    '"confidence": 0 to 1, "abstain": true only if you cannot answer')


# --------------------------------------------------------------------- io
def file_sha256(path: str) -> str:
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def verify_suite_files(tasks) -> list:
    """Task files whose bytes no longer match what the suite recorded."""
    bad = []
    for t in tasks:
        for name, path in t["files"].items():
            want = t.get("files_sha256", {}).get(name)
            if want is None or not os.path.exists(path) \
                    or file_sha256(path) != want:
                bad.append(f"{t['id']}:{name}")
    return bad


def _quiet():
    warnings.simplefilter("ignore")


def _load(topology: str, trajectory: Optional[str] = None):
    from vmd_agent.inputs.molio import load_universe
    with warnings.catch_warnings():
        _quiet()
        return load_universe(topology, trajectory)


def _write_system(ag, pos: Optional[np.ndarray], folder: str,
                  dt_header_ps: float = 2.0, box: Optional[float] = None,
                  drop_last_atoms: int = 0) -> dict:
    """Write ``system.pdb`` (and ``traj.dcd`` from ``pos``) into ``folder``.

    ``drop_last_atoms`` makes the topology disagree with the trajectory.
    """
    import MDAnalysis as mda
    os.makedirs(folder, exist_ok=True)
    top = os.path.join(folder, "system.pdb")
    out = {"topology": top}
    with warnings.catch_warnings():
        _quiet()
        ag.universe.trajectory[0]
        if pos is not None:
            full = os.path.join(folder, ".full.pdb")
            ag.write(full)
            tmp = mda.Universe(full)
            dcd = os.path.join(folder, "traj.dcd")
            with mda.Writer(dcd, n_atoms=tmp.atoms.n_atoms,
                            dt=dt_header_ps) as w:
                for f in range(len(pos)):
                    tmp.atoms.positions = pos[f]
                    if box:
                        tmp.dimensions = [box, box, box, 90, 90, 90]
                    w.write(tmp.atoms)
            os.remove(full)
            out["trajectory"] = dcd
        (ag[:-drop_last_atoms] if drop_last_atoms else ag).write(top)
    return out


# ------------------------------------------------------- independent truth
def cog_distance(pos: np.ndarray, idx_a: np.ndarray, idx_b: np.ndarray,
                 frame: int) -> float:
    a = pos[frame, idx_a].mean(0)
    b = pos[frame, idx_b].mean(0)
    return float(np.linalg.norm(a - b))


def residues_near(coords: np.ndarray, resindices: np.ndarray, target: int,
                  cutoff: float) -> np.ndarray:
    """Atom indices of residues (other than ``target``) with an atom within
    ``cutoff`` of any atom of residue ``target``. KD-tree, no MDAnalysis."""
    from scipy.spatial import cKDTree
    tgt = np.where(resindices == target)[0]
    tree = cKDTree(coords[tgt])
    dist, _ = tree.query(coords, k=1)
    near_atoms = np.where(dist <= cutoff)[0]
    res = set(resindices[near_atoms].tolist()) - {target}
    return np.where(np.isin(resindices, list(res)))[0]


def atoms_within(coords: np.ndarray, idx_a: np.ndarray, idx_b: np.ndarray,
                 cutoff: float) -> np.ndarray:
    """Members of ``idx_a`` within ``cutoff`` of any atom of ``idx_b``."""
    from scipy.spatial import cKDTree
    tree = cKDTree(coords[idx_b])
    dist, _ = tree.query(coords[idx_a], k=1)
    return np.asarray(idx_a)[dist <= cutoff]


# --------------------------------------------------------------- builders
class _Builder:
    def __init__(self, out_dir: str, seed: int):
        self.out = os.path.abspath(out_dir)
        self.rng = np.random.default_rng(seed)
        self.tasks: List[dict] = []
        self.truth: Dict[str, dict] = {}
        self._n = 0
        os.makedirs(os.path.join(self.out, "work"), exist_ok=True)

    def workdir(self, family: str) -> tuple:
        self._n += 1
        tid = f"{family[:4]}{self._n:03d}"
        d = os.path.join(self.out, "work", tid)
        os.makedirs(d, exist_ok=True)
        return tid, d

    def add(self, tid: str, family: str, kind: str, cluster: str, group: str,
            prompt: str, files: dict, answer_format: str, workdir: str,
            truth: dict, **extra):
        self.tasks.append({
            "id": tid, "family": family, "kind": kind, "cluster": cluster,
            "group": group, "workdir": workdir, "files": files,
            "files_sha256": {k: file_sha256(v) for k, v in files.items()},
            "prompt": prompt + "\n\nFinish by submitting a JSON answer: "
                      + answer_format,
            **extra})
        self.truth[tid] = truth


def _base_arrays(base: dict):
    u = _load(base["topology"], base["trajectory"])
    ag = u.select_atoms("protein")
    data = E.load_real_positions(base["topology"], base["trajectory"])
    return u, ag, data


def _add_measure(b: _Builder, base: dict, cid: str, ag, data: dict):
    pos, masses = data["pos"], data["masses"]
    n = len(pos)
    ca = ag.select_atoms("name CA")
    ca_pos = pos[:, np.isin(ag.indices, ca.indices)]
    resids = np.unique(ag.resids)
    a0, a1 = int(resids[0]), int(resids[min(9, len(resids) - 1)])
    b0, b1 = int(resids[max(len(resids) - 10, 0)]), int(resids[-1])
    last = n - 1

    def files_for(pos_=pos, header=1.0):
        tid, d = b.workdir("measure")
        f = _write_system(ag, pos_, d, dt_header_ps=header)
        return tid, d, f

    # 1. RMSD of last frame vs first, C-alpha, after superposition
    tid, d, f = files_for()
    truth = float(E.kabsch_rmsd_series(ca_pos)[last])
    b.add(tid, "measure", "rmsd_last", cid, "real",
          "Using the topology and trajectory, report the root-mean-square "
          "deviation (angstrom) of the last frame from the first frame, "
          "computed on C-alpha atoms (name CA) after optimal rigid-body "
          "superposition.", f,
          '{"value": number, ' + _ANSWER_COMMON + "}", d,
          {"value": truth, "rtol": 0.03, "atol": 0.05, "unit": "A"})

    # 2. mean mass-weighted radius of gyration over all frames
    tid, d, f = files_for()
    rg = float(E.signals_from_positions(pos, masses)["rgyr"].mean())
    b.add(tid, "measure", "rg_mean", cid, "real",
          "Report the mean radius of gyration (angstrom) of the protein "
          "(selection `protein`, mass-weighted) averaged over every frame.",
          f, '{"value": number, ' + _ANSWER_COMMON + "}", d,
          {"value": rg, "rtol": 0.02, "atol": 0.05, "unit": "A"})

    # 3. distance between centres of geometry of two terminal segments
    tid, d, f = files_for()
    idx_a = np.where(np.isin(ag.resids, np.arange(a0, a1 + 1)))[0]
    idx_b = np.where(np.isin(ag.resids, np.arange(b0, b1 + 1)))[0]
    b.add(tid, "measure", "cog_distance", cid, "real",
          f"In the last frame, what is the distance (angstrom) between the "
          f"centre of geometry (unweighted mean position) of all atoms of "
          f"protein residues {a0}-{a1} and that of residues {b0}-{b1}?",
          f, '{"value": number, ' + _ANSWER_COMMON + "}", d,
          {"value": cog_distance(pos, idx_a, idx_b, last), "rtol": 0.02,
           "atol": 0.1, "unit": "A"})

    # 4. elapsed time with an untrustworthy header
    tid, d, f = files_for(header=2.0)
    b.add(tid, "measure", "elapsed_ns", cid, "real",
          "Frames in this trajectory were saved every 400 ps (the time "
          "stored in the file header is not reliable). How many nanoseconds "
          "pass between the first and the last frame?", f,
          '{"value": number, ' + _ANSWER_COMMON + "}", d,
          {"value": (n - 1) * 0.4, "rtol": 0.01, "atol": 0.0, "unit": "ns"})


def _event_trajectory(b: _Builder, ag, data: dict, kind: Optional[str],
                      length: int, n_frames: int = N_FRAMES):
    ext = E.pingpong(data["pos"], n_frames)
    if kind is None:
        return ext, None
    groups = E.event_groups(data["resindices"])
    start = int(b.rng.integers(int(0.25 * n_frames),
                               int(0.7 * n_frames) - length))
    inj = E.inject_event(ext, groups, kind, start, length,
                         EVENT_PRESETS[kind], b.rng)
    return inj["pos"], inj["event"]


def _add_events(b: _Builder, ag, data: dict, cid: str, n_events: int,
                n_controls: int, n_keyframes: int):
    kinds = list(EVENT_PRESETS)
    for i in range(n_events):
        kind, length = kinds[i % 3], (10, 30)[(i // 3) % 2]
        pos, ev = _event_trajectory(b, ag, data, kind, length)
        tid, d = b.workdir("event")
        f = _write_system(ag, pos, d)
        b.add(tid, "event", "onset", cid, "real",
              f"This trajectory has {len(pos)} frames (0-based). Does it "
              "contain one sustained, directional structural change (as "
              "opposed to thermal fluctuation)? If yes, report the frame at "
              "which it begins; if not, report null.", f,
              '{"onset_frame": integer or null, ' + _ANSWER_COMMON + "}", d,
              {"event": ev, "kind": kind, "slack": 5})
    for _ in range(n_controls):
        pos, _ev = _event_trajectory(b, ag, data, None, 0)
        tid, d = b.workdir("event")
        f = _write_system(ag, pos, d)
        b.add(tid, "event", "control", cid, "real",
              f"This trajectory has {len(pos)} frames (0-based). Does it "
              "contain one sustained, directional structural change (as "
              "opposed to thermal fluctuation)? If yes, report the frame at "
              "which it begins; if not, report null.", f,
              '{"onset_frame": integer or null, ' + _ANSWER_COMMON + "}", d,
              {"event": None, "kind": None, "slack": 5})
    for i in range(n_keyframes):
        kind = kinds[i % 3]
        pos, ev = _event_trajectory(b, ag, data, kind, 10)
        tid, d = b.workdir("keyframes")
        f = _write_system(ag, pos, d)
        k = 4
        b.add(tid, "keyframes", "transition", cid, "real",
              f"This trajectory has {len(pos)} frames (0-based) and contains "
              f"a structural transition. Pick at most {k} frames that show "
              "the transition itself while it is happening, render each "
              "chosen frame to its own image file inside your working "
              f"directory ({d}), and report the frame numbers and the image "
              "paths in the same order.", f,
              '{"frames": [integers], "images": ["one image path per frame"], '
              + _ANSWER_COMMON + "}", d,
              {"event": ev, "k": k, "slack": 5})


def _add_diagnosis(b: _Builder, ag, data: dict, cid: str):
    pos = data["pos"][:40].copy()
    n = len(pos)
    ca_pos = pos[:, np.isin(ag.indices, ag.select_atoms("name CA").indices)]
    clean_rmsd = float(E.kabsch_rmsd_series(ca_pos)[n - 1])
    prompt = ("Report the root-mean-square deviation (angstrom) of the last "
              "frame from the first frame on C-alpha atoms (name CA) after "
              "optimal superposition. If the data have a problem that makes "
              "this number unreliable or impossible, do not guess a number: "
              "set value to null and name the problem in `issue`, one of "
              f"{list(ISSUES)}.")
    fmt = ('{"value": number or null, "issue": one of '
           f'{list(ISSUES)}, ' + _ANSWER_COMMON + "}")

    def one(label, pos_, **kw):
        tid, d = b.workdir("diagnosis")
        f = _write_system(ag, pos_, d, **kw)
        b.add(tid, "diagnosis", label, cid, "real", prompt, f, fmt, d,
              {"issue": label,
               "value": clean_rmsd if label == "none" else None,
               "rtol": 0.03, "atol": 0.05})

    one("none", pos)
    moved = np.arange(int(0.9 * pos.shape[1]), pos.shape[1])
    p = pos.copy()
    p[n // 2:, moved, 0] += BOX
    one("pbc_broken", p, box=BOX)
    one("atom_count_mismatch", pos, drop_last_atoms=5)
    p = pos.copy()
    p[n // 3: n // 3 + 3, :50, :] = np.nan
    one("nonfinite_coordinates", p)


def chain_labels(prot) -> Optional[List[str]]:
    """Per-atom chain labels (chainIDs, else segids) if the system has two or
    more distinct non-blank chains; otherwise ``None``."""
    for attr in ("chainIDs", "segids"):
        try:
            vals = [str(c).strip() for c in getattr(prot, attr)]
        except Exception:
            continue
        if len({c for c in vals if c}) >= 2:
            return vals
    return None


def _add_selection(b: _Builder, topology: str, cid: str, group: str,
                   trajectory: Optional[str] = None, n_near: int = 2):
    """Selection tasks on frame 0 of a system."""
    u = _load(topology, trajectory)
    u.trajectory[0]
    prot = u.select_atoms("protein")
    if not len(prot):
        return
    coords = prot.positions.astype(float)
    resind = prot.resindices
    ures = np.unique(resind)
    pick = b.rng.choice(len(ures), size=min(n_near, len(ures)),
                        replace=False)
    def ws_files(d):
        top = os.path.join(d, "system.pdb")
        with warnings.catch_warnings():
            _quiet()
            u.atoms.write(top)
        return {"topology": top}

    labels = chain_labels(prot)
    for ri in pick:
        r = int(ures[ri])
        first = int(np.where(resind == r)[0][0])
        resid = int(prot.resids[first])
        where = f"{resid} of chain {labels[first]}" if labels else f"{resid}"
        sel_idx = residues_near(coords, resind, r, NEAR_CUTOFF)
        tid, d = b.workdir("selection")
        b.add(tid, "selection", "near_residue", cid, group,
              f"At frame 0, select every atom of the protein residues "
              f"(other than residue {where} itself) that have at least one "
              f"atom within {NEAR_CUTOFF} A of any atom of protein residue "
              f"{where}. Whole residues are wanted, not just the close "
              "atoms. Use the coordinates as they are in the file (no "
              "periodic images). Give the selection as a single "
              "MDAnalysis selection string.",
              ws_files(d),
              '{"selection": "MDAnalysis selection string", '
              + _ANSWER_COMMON + "}", d,
              {"atoms": sorted(int(prot.indices[i]) for i in sel_idx)})
    # sidechain heavy atoms of a residue range
    rs = np.unique(prot.resids)
    lo, hi = int(rs[len(rs) // 4]), int(rs[len(rs) // 4 + min(7, len(rs) // 2)])
    sub = prot.select_atoms(
        f"resid {lo}:{hi} and not (name N CA C O) and not name H*")
    tid, d = b.workdir("selection")
    b.add(tid, "selection", "sidechain_range", cid, group,
          f"Select the heavy (non-hydrogen) side-chain atoms of protein "
          f"residues {lo} to {hi} (in every chain, if there are several): "
          "every atom of those residues except the backbone atoms N, CA, C, "
          "O and except hydrogens. Give the "
          "selection as a single MDAnalysis selection string.",
          ws_files(d),
          '{"selection": "MDAnalysis selection string", '
          + _ANSWER_COMMON + "}", d,
          {"atoms": sorted(int(i) for i in sub.indices)})
    # interface between two chains
    if labels:
        cids = sorted({c for c in labels if c})
        a, c2 = cids[0], cids[1]
        ia = np.where(np.asarray(labels) == a)[0]
        ib = np.where(np.asarray(labels) == c2)[0]
        near = atoms_within(coords, ia, ib, INTERFACE_CUTOFF)
        tid, d = b.workdir("selection")
        b.add(tid, "selection", "chain_interface", cid, group,
              f"At frame 0, select the protein atoms of chain {a} that are "
              f"within {INTERFACE_CUTOFF} A of any protein atom of chain "
              f"{c2}. Chain identifiers are those in the file. Use the "
              "coordinates as they are (no periodic images). Give the "
              "selection as a single MDAnalysis selection string.",
              ws_files(d),
              '{"selection": "MDAnalysis selection string", '
              + _ANSWER_COMMON + "}", d,
              {"atoms": sorted(int(prot.indices[i]) for i in near)})


def _add_report(b: _Builder, path: str, cid: str, group: str):
    tid, d = b.workdir("report")
    top = os.path.join(d, "system.pdb")
    shutil.copy(path, top)
    b.add(tid, "report", "composition", cid, group,
          "Describe this system in three to five short, factual sentences "
          "(components present, number of chains, secondary structure, "
          "ligands). State only what you are able to support from the data.",
          {"topology": top},
          '{"report": ["one sentence per list item"], '
          + _ANSWER_COMMON + "}", d, {})


# ------------------------------------------------------------------ entry
def build_suite(out_dir: str, bases: Sequence[dict],
                structures: Sequence[str] = (),
                synthetic: Sequence[str] = (), seed: int = 0,
                n_events: int = 6, n_controls: int = 2,
                n_keyframes: int = 3,
                families: Optional[Sequence[str]] = None) -> dict:
    """Generate workspaces, ``tasks.json`` and ``truth.json`` under ``out_dir``.

    ``bases``       real trajectories, ``[{"id", "topology", "trajectory"}]``
    ``structures``  real static structure files
    ``synthetic``   synthetic static structures (:mod:`vmd_agent.bench.synth`)
    The cluster of a task (the unit the bootstrap resamples) is its base or
    structure: tasks derived from one trajectory share its noise and are not
    independent.
    """
    fams = set(families or FAMILIES)
    unknown = fams - set(FAMILIES)
    if unknown:
        raise ValueError(f"unknown families {sorted(unknown)}; "
                         f"choose from {list(FAMILIES)}")
    if os.path.exists(os.path.join(out_dir, "tasks.json")):
        raise FileExistsError(f"{out_dir} already holds a suite; choose a "
                              "new directory")
    b = _Builder(out_dir, seed)
    for base in bases:
        _u, ag, data = _base_arrays(base)
        cid = str(base["id"])
        if "measure" in fams:
            _add_measure(b, base, cid, ag, data)
        if fams & {"event", "keyframes"}:
            _add_events(b, ag, data, cid,
                        n_events if "event" in fams else 0,
                        n_controls if "event" in fams else 0,
                        n_keyframes if "keyframes" in fams else 0)
        if "diagnosis" in fams:
            _add_diagnosis(b, ag, data, cid)
        if "selection" in fams:
            _add_selection(b, base["topology"], cid, "real",
                           base["trajectory"])
    groups = [(p, "real") for p in structures] + \
             [(p, "synthetic") for p in synthetic]
    for i, (p, g) in enumerate(groups):
        cid = f"s{i:03d}"
        if "selection" in fams:
            _add_selection(b, p, cid, g)
        if "report" in fams:
            _add_report(b, p, cid, g)
    suite = {"seed": seed, "n_tasks": len(b.tasks),
             "families": {f: sum(t["family"] == f for t in b.tasks)
                          for f in FAMILIES},
             "clusters": sorted({t["cluster"] for t in b.tasks})}
    with open(os.path.join(b.out, "truth.json"), "w") as fh:
        json.dump(b.truth, fh)
    with open(os.path.join(b.out, "tasks.json"), "w") as fh:
        json.dump({"suite": suite, "tasks": b.tasks}, fh, indent=1)
    return {"suite": suite, "tasks": b.tasks, "truth": b.truth}


def load_suite(out_dir: str) -> dict:
    with open(os.path.join(out_dir, "tasks.json")) as fh:
        d = json.load(fh)
    with open(os.path.join(out_dir, "truth.json")) as fh:
        d["truth"] = json.load(fh)
    return d


def public_view(task: dict) -> dict:
    """What an agent may see: no truth, no cluster/group labels."""
    keep = ("id", "family", "prompt", "files", "workdir")
    return {k: task[k] for k in keep}
