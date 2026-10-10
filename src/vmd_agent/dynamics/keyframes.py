"""Event-aware keyframe selection for trajectories and movies.

Uniform sampling shows nine evenly
spaced stills. An event shorter than the spacing between stills falls between
two of them and is simply never seen: "unobserved, not absent". This module
chooses frames from the *trajectory's own signals* instead.

Method
------
1. Compute per-frame signals (RMSD to the first frame, radius of gyration, and
   optionally selection-selection contacts, COM distance and helix content).
2. For each signal, score every frame by the absolute difference between the
   means of the ``w`` frames before and after it. Scores are standardised with
   a robust (median / MAD) estimate of their own null distribution, so the
   threshold adapts to autocorrelated, non-Gaussian MD noise.
3. Combine signals by taking the maximum standardised score, apply
   non-maximum suppression, and keep peaks above ``z_min``.
4. Always keep the first and last frames, spend most of the remaining budget on
   the strongest change points, and fill the rest by bisecting the largest
   gaps so the whole run stays covered.

Also provided are the evaluation metrics and the closed-form uniform-sampling
sufficiency analysis used by ``vmd_agent.bench.sampling``.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import numpy as np

# ------------------------------------------------------------------ signals


def trajectory_signals(topology: str, trajectory: str,
                       selection: str = "protein",
                       sel2: Optional[str] = None, cutoff: float = 4.5,
                       step: int = 1, max_frames: int = 20000,
                       include_ss: bool = False) -> dict:
    """Per-frame scalar signals used to locate events.

    Returns ``frames`` (original trajectory frame indices), ``times`` (or
    ``None``) and ``signals`` (name -> array aligned with ``frames``).
    """
    from vmd_agent.inputs.molio import load_universe
    from MDAnalysis.analysis import rms
    u = load_universe(topology, trajectory)
    n = len(u.trajectory)
    step = max(int(step), 1, int(np.ceil(n / max_frames)))
    ag = u.select_atoms(selection)
    if not len(ag):
        raise ValueError(f"selection '{selection}' matched 0 atoms")
    frames = list(range(0, n, step))
    rmsd = rms.RMSD(u, select=selection, ref_frame=0)
    rmsd.run(step=step)
    sig: Dict[str, np.ndarray] = {"rmsd": np.asarray(rmsd.results.rmsd[:, 2])}
    times = []
    rg, com, cont, helix = [], [], [], []
    b = u.select_atoms(sel2) if sel2 else None
    if b is not None and not len(b):
        raise ValueError(f"sel2 '{sel2}' matched 0 atoms")
    from MDAnalysis.lib.distances import capped_distance
    for ts in u.trajectory[::step]:
        rg.append(ag.radius_of_gyration())
        times.append(ts.time)
        if b is not None:
            com.append(float(np.linalg.norm(ag.center_of_mass()
                                            - b.center_of_mass())))
            pairs, _ = capped_distance(ag.positions, b.positions,
                                       max_cutoff=cutoff)
            cont.append(len(pairs))
        if include_ss:
            from vmd_agent.structure.dssp import secondary_structure_fractions
            f = secondary_structure_fractions(u.select_atoms("protein")) or {}
            helix.append(f.get("helix_percent", np.nan))
    sig["rgyr"] = np.asarray(rg)
    if b is not None:
        sig["com_distance"] = np.asarray(com)
        sig["contacts"] = np.asarray(cont, dtype=float)
    if include_ss:
        sig["helix_percent"] = np.asarray(helix)
    t = np.asarray(times, dtype=float)
    ok = len(t) >= 2 and np.all(np.isfinite(t)) and np.all(np.diff(t) > 0)
    return {"frames": frames, "times": t.tolist() if ok else None,
            "signals": sig, "step": step, "n_frames_total": n}


# ------------------------------------------------------------- change points
def change_scores(x: Sequence[float], window: int) -> np.ndarray:
    """|mean(next w) - mean(previous w)| at every index (0 where undefined)."""
    a = np.asarray(x, dtype=float)
    n = len(a)
    score = np.zeros(n)
    w = int(window)
    if n < 2 * w + 1 or w < 1:
        return score
    c = np.concatenate([[0.0], np.cumsum(a)])
    i = np.arange(w, n - w + 1)
    left = (c[i] - c[i - w]) / w
    right = (c[np.minimum(i + w, n)] - c[i]) / w
    score[i[i < n]] = np.abs(right - left)[i < n]
    return score


def standardise_scores(score: np.ndarray) -> np.ndarray:
    """Robust z-scores against the score distribution's own median / MAD."""
    s = np.asarray(score, dtype=float)
    valid = s > 0
    if valid.sum() < 5:
        return np.zeros_like(s)
    med = np.median(s[valid])
    mad = 1.4826 * np.median(np.abs(s[valid] - med))
    if mad <= 1e-12:
        return np.zeros_like(s)
    z = (s - med) / mad
    z[~valid] = 0.0
    return z


def _nms(z: np.ndarray, min_sep: int, z_min: float) -> List[int]:
    order = np.argsort(-z)
    picked: List[int] = []
    for i in order:
        if z[i] < z_min:
            break
        if all(abs(int(i) - p) > min_sep for p in picked):
            picked.append(int(i))
    return picked


def detect_change_points(signals: Dict[str, np.ndarray],
                         window: Optional[int] = None,
                         z_min: float = 6.0) -> List[dict]:
    """Change points across signals, strongest first.

    Each entry: ``{"index", "z", "signal", "per_signal": {name: z}}``.
    """
    names = list(signals)
    if not names:
        return []
    n = len(next(iter(signals.values())))
    w = int(window or max(3, n // 25))
    zs = {k: standardise_scores(change_scores(v, w))
          for k, v in signals.items()}
    stack = np.vstack([zs[k] for k in names])
    best = stack.max(axis=0)
    which = stack.argmax(axis=0)
    pts = []
    for i in _nms(best, w, z_min):
        pts.append({"index": i, "z": float(best[i]),
                    "signal": names[int(which[i])],
                    "per_signal": {k: float(zs[k][i]) for k in names}})
    return pts


# --------------------------------------------------------------- selection
def uniform_frames(n_frames: int, k: int) -> List[int]:
    """``k`` evenly spaced frame indices including both endpoints."""
    k = max(int(k), 1)
    if n_frames <= 1:
        return [0]
    if k == 1:
        return [0]
    return sorted({int(round(i * (n_frames - 1) / (k - 1))) for i in range(k)})


def select_keyframes_from_signals(signals: Dict[str, np.ndarray], k: int = 9,
                                  window: Optional[int] = None,
                                  z_min: float = 6.0,
                                  event_fraction: float = 0.7) -> dict:
    """Choose ``k`` frame indices (into the analysed series).

    ``event_fraction`` caps how much of the budget change points may consume,
    guaranteeing the rest goes to even coverage.
    """
    n = len(next(iter(signals.values()))) if signals else 0
    k = max(int(k), 1)
    if n == 0:
        return {"indices": [], "reasons": {}, "change_points": []}
    if k >= n:
        return {"indices": list(range(n)),
                "reasons": {i: "all frames (budget >= trajectory length)"
                            for i in range(n)}, "change_points": []}
    chosen: Dict[int, str] = {0: "first frame", n - 1: "last frame"}
    cps = detect_change_points(signals, window, z_min)
    room = max(k - len(chosen), 0)
    n_events = min(int(round(event_fraction * room)), len(cps))
    for cp in cps[:n_events]:
        if cp["index"] not in chosen:
            chosen[cp["index"]] = (f"change in {cp['signal']} "
                                   f"(robust z={cp['z']:.1f})")
    # fill remaining budget by bisecting the largest gaps
    while len(chosen) < k:
        pts = sorted(chosen)
        gaps = [(pts[i + 1] - pts[i], pts[i]) for i in range(len(pts) - 1)]
        gap, left = max(gaps)
        if gap < 2:
            break
        chosen[left + gap // 2] = "coverage (largest gap)"
    return {"indices": sorted(chosen), "reasons": chosen,
            "change_points": cps, "window": int(window or max(3, n // 25))}


def select_keyframes(topology: str, trajectory: str, k: int = 9,
                     selection: str = "protein", sel2: Optional[str] = None,
                     cutoff: float = 4.5, step: int = 1,
                     z_min: float = 6.0, include_ss: bool = False,
                     out_dir: Optional[str] = None) -> dict:
    """Pick event-aware keyframes for a trajectory.

    Pure selection: this module never draws anything. To render the chosen
    frames use :func:`vmd_agent.auto.select_keyframes`, which composes this
    with a renderer."""
    if not isinstance(k, (int, np.integer)) or isinstance(k, bool) or k < 1:
        return {"ok": False, "error": f"k must be an integer >= 1, got {k!r}"}
    try:
        sig = trajectory_signals(topology, trajectory, selection, sel2, cutoff,
                                 step, include_ss=include_ss)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    chosen = select_keyframes_from_signals(sig["signals"], k=k, z_min=z_min)
    frames = [sig["frames"][i] for i in chosen["indices"]]
    times = sig["times"]
    out = {
        "ok": True, "k": k, "selection": selection, "sel2": sel2,
        "frames": frames,
        "times_ps": ([times[i] for i in chosen["indices"]] if times else None),
        "reasons": {sig["frames"][i]: r for i, r in chosen["reasons"].items()},
        "change_points": [{"frame": sig["frames"][c["index"]], "z": c["z"],
                           "signal": c["signal"]}
                          for c in chosen["change_points"]],
        "uniform_baseline": [sig["frames"][min(i, len(sig["frames"]) - 1)]
                             for i in uniform_frames(len(sig["frames"]), k)],
        "signals_used": sorted(sig["signals"]),
        "step": sig["step"], "n_frames_total": sig["n_frames_total"],
        "method": "robust change-point scoring of per-frame signals "
                  "(vmd_agent.dynamics.keyframes)",
        "caveat": "Change points are statistical features of the chosen "
                  "signals; an event that moves none of them is not detected. "
                  "Always view the frames before interpreting.",
    }
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        out["signal_plot"] = _plot_signals(sig, chosen, out_dir)
    return out


def _plot_signals(sig, chosen, out_dir) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(sig["signals"])
    fig, axes = plt.subplots(len(names), 1, figsize=(7, 1.9 * len(names)),
                             sharex=True, dpi=130)
    axes = np.atleast_1d(axes)
    x = np.asarray(sig["frames"])
    for ax, nme in zip(axes, names):
        ax.plot(x, sig["signals"][nme], lw=1.1)
        for i in chosen["indices"]:
            ax.axvline(x[i], color="C3", alpha=0.45, lw=0.9)
        ax.set_ylabel(nme, fontsize=8)
        ax.grid(alpha=0.25)
    axes[-1].set_xlabel("frame")
    fig.suptitle("Signals with selected keyframes (red)", fontsize=9)
    fig.tight_layout()
    path = os.path.join(out_dir, "keyframe_signals.png")
    fig.savefig(path)
    plt.close(fig)
    return path
