"""Semi-synthetic event study on *real* trajectory noise.

The AR(1) simulation in :mod:`vmd_agent.bench.sampling` shows the idea but its
noise is an idealisation. Real MD signals are non-Gaussian and correlated in
ways AR(1) is not. This module keeps the noise real and makes only the *event*
synthetic:

1. take a real trajectory (frames of an equilibrium simulation),
2. extend it to ``n_frames`` by **ping-pong reflection** (0..F-1, F-2..1, 0...),
   which preserves every local frame-to-frame step of the real data,
3. inject one labelled event on top of the real coordinates:

   ``hinge``         the first half of the chain rotates about a pivot near the
                     rest of the protein, ramping to ``magnitude`` degrees
   ``dissociation``  the last ~10 % of residues translate away from the rest,
                     ramping to ``magnitude`` Å
   ``expansion``     the whole molecule scales about its centroid, ramping to
                     ``magnitude`` (fractional change in size)

   each ramp lasts ``length`` frames and the new state is then held,
4. compute RMSD / Rg (/ moving-vs-rest COM distance) from the coordinates and
   compare uniform with event-aware frame selection at an equal budget.

A **negative control** (no event) measures how many change points the detector
invents on real noise.

Limits, which any use of this study must state: the event is synthetic (a rigid
rotation/translation/scaling, not a physical transition); ping-pong reflection
makes the base signal periodic with period ``2(F-1)``; and the chosen
signals are assumed to be the ones the researcher would examine.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from vmd_agent.dynamics.keyframes import (
    select_keyframes_from_signals, uniform_frames, evaluate_sampling,
)

KINDS = ("hinge", "dissociation", "expansion")


# ------------------------------------------------------------------ data
def load_real_positions(topology: str, trajectory: str,
                        selection: str = "protein") -> dict:
    """Coordinates ``(F, N, 3)`` of a real trajectory plus residue bookkeeping."""
    from vmd_agent.inputs.molio import load_universe
    u = load_universe(topology, trajectory)
    ag = u.select_atoms(selection)
    if not len(ag):
        raise ValueError(f"selection '{selection}' matched 0 atoms")
    pos = np.array([ag.positions.copy() for _ in u.trajectory], dtype=np.float64)
    return {"pos": pos, "masses": np.asarray(ag.masses, dtype=float),
            "resindices": ag.resindices.copy()}


def pingpong(pos: np.ndarray, n_frames: int) -> np.ndarray:
    """Extend ``pos`` to ``n_frames`` by reflecting at both ends."""
    f = len(pos)
    if f < 2:
        return np.repeat(pos, n_frames, axis=0)
    cycle = np.concatenate([np.arange(f), np.arange(f - 2, 0, -1)])
    idx = np.resize(cycle, n_frames)
    return pos[idx]


# ---------------------------------------------------------------- groups
def event_groups(resindices: np.ndarray) -> dict:
    """Atom index sets used by the three event kinds (generic, residue-based)."""
    ures = np.unique(resindices)
    half = ures[: max(len(ures) // 2, 1)]
    tail = ures[-max(len(ures) // 10, 2):]
    moving_hinge = np.where(np.isin(resindices, half))[0]
    moving_tail = np.where(np.isin(resindices, tail))[0]
    return {"hinge": moving_hinge, "dissociation": moving_tail,
            "expansion": np.arange(len(resindices))}


# --------------------------------------------------------------- events
def _ramp(n: int, start: int, length: int) -> np.ndarray:
    """0 before ``start``, linear to 1 over ``length`` frames, then 1."""
    t = np.arange(n, dtype=float)
    return np.clip((t - start) / max(length, 1), 0.0, 1.0)


def _rotation(axis: np.ndarray, angle_deg: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    th = np.radians(angle_deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K)


def inject_event(pos: np.ndarray, groups: dict, kind: str, start: int,
                 length: int, magnitude: float,
                 rng: Optional[np.random.Generator] = None) -> dict:
    """Return ``{"pos": new coordinates, "event": label}`` (input untouched)."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    rng = rng or np.random.default_rng(0)
    out = pos.copy()
    n_frames = len(pos)
    ramp = _ramp(n_frames, start, length)
    moving = groups[kind]
    rest = np.setdiff1d(np.arange(pos.shape[1]), moving)

    if kind == "hinge":
        axis = rng.normal(size=3)
        # pivot: moving-group centroid pulled to the atom nearest the rest
        c_rest = pos[0, rest].mean(0)
        d = np.linalg.norm(pos[0, moving] - c_rest, axis=1)
        pivot = pos[0, moving][np.argsort(d)[: max(len(moving) // 10, 1)]].mean(0)
        for f in range(n_frames):
            if ramp[f] > 0:
                R = _rotation(axis, magnitude * ramp[f])
                out[f, moving] = (pos[f, moving] - pivot) @ R.T + pivot
    elif kind == "dissociation":
        direction = pos[0, moving].mean(0) - pos[0, rest].mean(0)
        direction /= np.linalg.norm(direction)
        for f in range(n_frames):
            out[f, moving] = pos[f, moving] + direction * magnitude * ramp[f]
    else:  # expansion
        for f in range(n_frames):
            c = pos[f].mean(0)
            out[f] = c + (pos[f] - c) * (1.0 + magnitude * ramp[f])
    return {"pos": out, "moving": moving,
            "event": {"kind": kind, "start": int(start),
                      "end": int(start + length), "magnitude": float(magnitude)}}


# --------------------------------------------------------------- signals
def kabsch_rmsd_series(pos: np.ndarray, ref: Optional[np.ndarray] = None
                       ) -> np.ndarray:
    """RMSD of every frame to ``ref`` (default frame 0) after superposition."""
    ref = pos[0] if ref is None else ref
    Q = ref - ref.mean(0)
    out = np.empty(len(pos))
    for i, P in enumerate(pos):
        P = P - P.mean(0)
        U, _S, Vt = np.linalg.svd(P.T @ Q)
        d = np.sign(np.linalg.det(U @ Vt))
        R = U @ np.diag([1.0, 1.0, d]) @ Vt
        out[i] = np.sqrt(np.mean(np.sum((P @ R - Q) ** 2, axis=1)))
    return out


def signals_from_positions(pos: np.ndarray, masses: np.ndarray,
                           moving: Optional[np.ndarray] = None) -> dict:
    """RMSD, Rg and (with ``moving``) moving-vs-rest COM distance."""
    w = masses / masses.sum()
    com = np.einsum("a,fac->fc", w, pos)
    rg = np.sqrt(np.einsum("a,fa->f", w, ((pos - com[:, None, :]) ** 2).sum(2)))
    sig = {"rmsd": kabsch_rmsd_series(pos), "rgyr": rg}
    if moving is not None:
        rest = np.setdiff1d(np.arange(pos.shape[1]), moving)
        a = np.einsum("a,fac->fc", masses[moving] / masses[moving].sum(),
                      pos[:, moving])
        b = np.einsum("a,fac->fc", masses[rest] / masses[rest].sum(),
                      pos[:, rest])
        sig["com_distance"] = np.linalg.norm(a - b, axis=1)
    return sig


def robust_noise(x: np.ndarray) -> float:
    """MAD-based sd of the first differences / sqrt(2): a scale for 'noise'."""
    d = np.diff(np.asarray(x, float))
    mad = 1.4826 * np.median(np.abs(d - np.median(d)))
    return float(mad / np.sqrt(2)) or 1e-12


# ----------------------------------------------------------------- study
def event_study(base: dict, kinds: Sequence[str] = KINDS,
                lengths: Sequence[int] = (5, 20, 60),
                magnitudes: Optional[Dict[str, Sequence[float]]] = None,
                n_frames: int = 300, k: int = 9, z_min: float = 6.0,
                n_trials: int = 100, seed: int = 0,
                tolerance: int = 0) -> dict:
    """Uniform vs event-aware selection on real noise with injected events."""
    magnitudes = magnitudes or {"hinge": (10.0, 20.0, 40.0),
                                "dissociation": (3.0, 6.0, 12.0),
                                "expansion": (0.02, 0.05, 0.10)}
    rng = np.random.default_rng(seed)
    ext = pingpong(base["pos"], n_frames)
    groups = event_groups(base["resindices"])
    masses = base["masses"]
    sel_u = uniform_frames(n_frames, k)
    rows: List[dict] = []
    for kind in kinds:
        for mag in magnitudes[kind]:
            for L in lengths:
                hit_u = hit_e = 0
                err_u, err_e, effects = [], [], []
                for _ in range(n_trials):
                    start = int(rng.integers(int(0.15 * n_frames),
                                             int(0.85 * n_frames) - L))
                    inj = inject_event(ext, groups, kind, start, L, mag, rng)
                    moving = (inj["moving"] if kind != "expansion" else None)
                    sig = signals_from_positions(inj["pos"], masses, moving)
                    base_sig = signals_from_positions(ext, masses, moving)
                    main = {"hinge": "rmsd", "dissociation": "com_distance",
                            "expansion": "rgyr"}[kind]
                    effects.append(abs(sig[main][-1] - base_sig[main][-1])
                                   / robust_noise(base_sig[main]))
                    ev = [inj["event"]]
                    sel_e = select_keyframes_from_signals(
                        sig, k=k, z_min=z_min)["indices"]
                    ru = evaluate_sampling(sel_u, ev, tolerance)
                    re_ = evaluate_sampling(sel_e, ev, tolerance)
                    hit_u += ru["recall_hit"]
                    hit_e += re_["recall_hit"]
                    err_u.append(ru["mean_localisation_error"])
                    err_e.append(re_["mean_localisation_error"])
                rows.append({
                    "kind": kind, "magnitude": mag, "length": L,
                    "effect_in_noise_sd": float(np.median(effects)),
                    "hit_uniform": hit_u / n_trials,
                    "hit_event_aware": hit_e / n_trials,
                    "loc_err_uniform": float(np.mean(err_u)),
                    "loc_err_event_aware": float(np.mean(err_e)),
                    "n_trials": n_trials})
    return {"n_frames": n_frames, "k": k, "z_min": z_min, "seed": seed,
            "base_frames": int(len(base["pos"])), "rows": rows,
            "method": "ping-pong extension of a real trajectory + injected "
                      "synthetic event; see vmd_agent.bench.events for limits"}


def negative_control(base: dict, n_frames: int = 300, k: int = 9,
                     z_min: float = 6.0, pingpong_extend: bool = True) -> dict:
    """Change points invented on real noise with **no** event present.

    Runs the selector once on the (optionally ping-pong-extended) real
    trajectory and counts detected change points; the share of the budget spent
    on them is the cost of a false alarm. This is **one realisation** of one
    trajectory, so it is weak evidence about the false-alarm *rate*; extending
    by reflection also creates a periodic signal, which is why the unextended
    result is reported too.
    """
    ext = pingpong(base["pos"], n_frames) if pingpong_extend else base["pos"]
    n = len(ext)
    groups = event_groups(base["resindices"])
    sig = signals_from_positions(ext, base["masses"], groups["dissociation"])
    out = select_keyframes_from_signals(sig, k=k, z_min=z_min)
    n_cp = len(out["change_points"])
    used = sum("change in" in v for v in out["reasons"].values())
    return {"n_frames": n, "z_min": z_min, "change_points_detected": n_cp,
            "budget_spent_on_events": used, "k": k,
            "per_100_frames": 100.0 * n_cp / n,
            "signals": sorted(sig)}


def table_markdown(study: dict) -> str:
    L = [f"Real-noise event study: {study['base_frames']} real frames "
         f"ping-pong-extended to {study['n_frames']}; budget k={study['k']}; "
         f"z_min={study['z_min']}; {study['rows'][0]['n_trials']} trials/cell.",
         "", "| event | magnitude | length | effect (noise sd) | hit: uniform | "
         "hit: event-aware | loc. err uniform | loc. err event-aware |",
         "|---|---|---|---|---|---|---|---|"]
    for r in study["rows"]:
        L.append(f"| {r['kind']} | {r['magnitude']:g} | {r['length']} | "
                 f"{r['effect_in_noise_sd']:.1f} | {r['hit_uniform']:.2f} | "
                 f"{r['hit_event_aware']:.2f} | {r['loc_err_uniform']:.0f} | "
                 f"{r['loc_err_event_aware']:.0f} |")
    return "\n".join(L) + "\n"
