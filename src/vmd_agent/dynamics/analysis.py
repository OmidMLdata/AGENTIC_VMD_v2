"""Trajectory analysis built on MDAnalysis (runs with no VMD required).

Each analysis is independent and defensive: a failure in one returns an
``error`` field instead of aborting the batch. Numeric summaries are returned
as JSON and, where useful, a PNG plot is written to the output directory.

What it does
------------
* **Honest time axes.** Plots and summaries use the trajectory's own times when
  the format records them and the frame index otherwise, and the axis label says
  which.
* **Statistics, not fixed thresholds.** "Stable" and "drifting" verdicts come
  from :mod:`vmd_agent.timeseries` (autocorrelation-corrected error bars,
  Mann-Kendall trend, first-vs-second-half comparison) rather than cut-offs such
  as "std < 0.5 Å".
* **Per-residue RMSF**.
* **Angle-based H-bonds** shared with :mod:`vmd_agent.stats`.
* **Periodic-boundary diagnostics** and an optional ``unwrap`` step.
* A **convergence** analysis reporting block averages and a suggested
  equilibration cut.
"""
from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from typing import Optional, Sequence

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from vmd_agent.dynamics import timeseries as tsm
from vmd_agent.inputs.molio import load_universe

# Readers whose ``ts.time`` comes from the file rather than being invented
# from a default timestep.
_TIMED_READERS = {"XTCReader", "TRRReader", "DCDReader", "NCDFReader",
                  "H5MDReader", "TNGReader", "GROReader"}


def _valid_box(dim):
    """Return a usable (6,) box array or ``None`` if the box is absent/invalid.

    Trajectories written without unit-cell records (or with object-dtype
    dimensions) otherwise poison PBC-aware distance calls and ``transfer_to_
    memory``. We treat those as "no periodic box".
    """
    try:
        d = np.asarray(dim, dtype=np.float32)
        if d.shape == (6,) and np.all(np.isfinite(d)) and d[0] > 0:
            return d
    except Exception:
        pass
    return None


def _select(u, expr):
    ag = u.select_atoms(expr)
    if not len(ag):
        raise ValueError(f"selection '{expr}' matched 0 atoms")
    return ag


# ---------------------------------------------------------------- loading
def _time_axis(u, step: int, dt_ps: Optional[float] = None):
    """Times of the frames that will be analysed, and an honest axis label.

    Returns ``(times, label, from_trajectory, info)``. Trajectory headers are
    not always right: a DCD that was strided or rewritten commonly keeps a
    default timestep (the real ubiquitin run in the tests reports 1.0 ps for
    frames that are 400 ps apart). ``dt_ps`` (picoseconds between *saved*
    frames of the original trajectory) overrides the header, and a header-derived
    DCD time always carries a warning.
    """
    rname = type(u.trajectory).__name__
    if dt_ps is not None:
        t = np.arange(0, len(u.trajectory), step, dtype=float) * float(dt_ps)
        return t, "time (ps)", True, {
            "source": "user-supplied dt_ps", "dt_ps": float(dt_ps)}
    times = []
    for ts in u.trajectory[::step]:
        try:
            times.append(float(ts.time))
        except Exception:
            times.append(float("nan"))
    t = np.asarray(times, dtype=float)
    ok = (rname in _TIMED_READERS and len(t) >= 2 and np.all(np.isfinite(t))
          and np.all(np.diff(t) > 0))
    if ok:
        info = {"source": f"trajectory header ({rname})"}
        if rname == "DCDReader":
            info["warning"] = (
                "DCD headers often hold a default or pre-stride timestep "
                f"(dt here = {float(np.diff(t).mean()) / step:.4g} ps per "
                "frame). Verify it, or pass dt_ps to set the real spacing.")
        return t, "time (ps)", True, info
    return (np.arange(len(t), dtype=float) * step, "frame index", False,
            {"source": "frame index (no usable time in the file)"})


def _sanitize_to_memory(u, step=1, unwrap_sel: Optional[str] = None):
    """Load coordinates into a MemoryReader with clean float boxes.

    This applies frame striding, removes the object-dtype/None box values that
    break MDAnalysis alignment on some DCD/LAMMPS files, and optionally makes
    ``unwrap_sel`` whole across periodic boundaries frame by frame.
    """
    from MDAnalysis.coordinates.memory import MemoryReader
    notes = []
    wrap_ag = None
    if unwrap_sel:
        wrap_ag = u.select_atoms(unwrap_sel)
        if not len(wrap_ag):
            wrap_ag = None
        else:
            try:
                has_bonds = len(wrap_ag.bonds) > 0
            except Exception:
                has_bonds = False
            if not has_bonds:
                try:
                    wrap_ag.guess_bonds()
                    notes.append("topology had no bonds; guessed them from "
                                 "distances to unwrap the selection")
                except Exception as e:
                    notes.append(f"unwrap skipped: could not obtain bonds ({e})")
                    wrap_ag = None
    coords, boxes, ok_box = [], [], True
    for ts in u.trajectory[::step]:
        if wrap_ag is not None:
            try:
                wrap_ag.unwrap(compound="fragments")
            except Exception as e:
                notes.append(f"unwrap failed on a frame: {e}")
                wrap_ag = None
        coords.append(u.atoms.positions.copy())
        b = _valid_box(ts.dimensions)
        if b is None:
            ok_box = False
            b = np.zeros(6, dtype=np.float32)
        boxes.append(b)
    coords = np.asarray(coords, dtype=np.float32)
    boxes = np.asarray(boxes, dtype=np.float32)
    bad = np.where(~np.isfinite(coords).all(axis=(1, 2)))[0]
    if len(bad):
        first = [int(b) * step for b in bad[:5]]
        notes.append(
            f"{len(bad)} of {len(coords)} analysed frame(s) contain non-finite "
            f"(NaN/inf) coordinates (first, in original frame numbers: "
            f"{first}); per-frame values there are NaN and summary statistics "
            "exclude them. The trajectory is damaged; do not treat these "
            "numbers as a clean analysis.")
    try:
        if ok_box:
            u.load_new(coords, format=MemoryReader, dimensions=boxes)
        else:
            u.load_new(coords, format=MemoryReader)
    except TypeError:
        u.load_new(coords, format=MemoryReader)       # older MDAnalysis
    return u, notes


def pbc_diagnostics(u, selection: str = "protein", max_report: int = 5) -> dict:
    """Detect periodic-boundary artefacts in the selection.

    A molecule that is split across the box edge makes RMSD, Rg and contact
    numbers meaningless without any error being raised. In a continuous
    trajectory no atom moves more than half a box length between consecutive
    frames, so such a jump means the atom was re-wrapped. Two cases matter:

    * **split**  only *some* atoms jumped: the molecule is torn across the edge
    * **whole**  *all* atoms jumped together: a rigid wrap; internal geometry is
      fine but centre-of-mass distances and densities are broken

    (Testing the centroid alone misses the first case, because atom-by-atom
    wrapping moves the centroid smoothly while destroying the molecule.)
    """
    try:
        ag = u.select_atoms(selection)
        if not len(ag):
            return {"checked": False, "reason": "empty selection"}
        prev, split, whole = None, [], []
        any_box = False
        for i, ts in enumerate(u.trajectory):
            pos = ag.positions.copy()
            box = _valid_box(ts.dimensions)
            if box is not None:
                any_box = True
            if prev is not None and box is not None:
                jump = np.any(np.abs(pos - prev) > 0.5 * box[:3], axis=1)
                nj = int(jump.sum())
                if nj == len(ag):
                    whole.append(i)
                elif nj > 0:
                    split.append(i)
            prev = pos
        if i < 1:
            return {"checked": False, "reason": "single frame"}
        if not any_box:
            return {"checked": False, "reason": "no unit-cell information"}
        bad = sorted(set(split) | set(whole))
        out = {"checked": True, "n_jump_frames": len(bad),
               "jump_frames": bad[:max_report],
               "n_split_frames": len(split), "n_whole_wrap_frames": len(whole)}
        if split:
            out["warning"] = (
                f"atoms of '{selection}' jump by more than half the box "
                f"between consecutive frames at {len(split)} frame(s) (first: "
                f"{split[:max_report]}), so the molecule is split across "
                "periodic boundaries; RMSD/Rg/contacts are unreliable. Re-run "
                "with unwrap=True or make the molecule whole first.")
        elif whole:
            out["warning"] = (
                f"the whole selection '{selection}' re-wraps at "
                f"{len(whole)} frame(s) (first: {whole[:max_report]}). "
                "Internal geometry is intact but centre-of-mass distances and "
                "density profiles will jump.")
        return out
    except Exception as e:                                  # pragma: no cover
        return {"checked": False, "reason": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------- plotting
def _plot(x, y, xlabel, ylabel, title, out_png, mean_band=None):
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=140)
    ax.plot(x, y, lw=1.3)
    if mean_band is not None:
        lo, hi = mean_band
        ax.axhspan(lo, hi, color="C1", alpha=0.18,
                   label="95% CI of mean")
        ax.legend(frameon=False, fontsize=8)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.set_title(title)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_png); plt.close(fig)
    return out_png


def _summary(arr):
    arr = np.asarray(arr, float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return {}
    return {"mean": float(arr.mean()), "std": float(arr.std()),
            "min": float(arr.min()), "max": float(arr.max()),
            "last": float(arr[-1]), "n": int(len(arr))}


def _interpret_stationarity(label: str, unit: str, st: dict) -> str:
    """Plain-language reading of an :func:`assess_stationarity` result."""
    v = st.get("verdict")
    if v == "insufficient_data":
        return f"{label}: {st.get('reason', 'insufficient data')}."
    mean = st.get("mean")
    ci = st.get("ci95") or [None, None]
    core = (f"{label} mean {mean:.3g} {unit} "
            f"(95% CI {ci[0]:.3g}-{ci[1]:.3g}, N_eff={st['n_eff']:.0f})")
    if v == "drifting":
        return (f"{core}. Drifting: {st['reason']}. The run has not reached a "
                "plateau over this window.")
    if v == "ambiguous":
        return f"{core}. Ambiguous: {st['reason']}."
    return f"{core}. {st['reason'].capitalize()}."


# ---------------------------------------------------------------- analyses
def _rmsd(ctx, select):
    from MDAnalysis.analysis import rms
    u = ctx.u
    _select(u, select)
    R = rms.RMSD(u, select=select, ref_frame=0)
    R.run()
    vals = R.results.rmsd[:, 2]
    st = tsm.assess_stationarity(vals, ctx.t)
    ci = st.get("ci95")
    png = _plot(ctx.t, vals, ctx.xlabel, "RMSD (Å)", f"RMSD  ({select})",
                os.path.join(ctx.out_dir, "rmsd.png"),
                mean_band=tuple(ci) if ci else None)
    half = vals[len(vals) // 2:]
    return {"selection": select, "reference": "frame 0 (first analysed frame)",
            "summary": _summary(vals),
            "drift_2nd_half": float(half[-1] - half[0]) if len(half) > 1 else None,
            "stationarity": st, "plot": png,
            "interpretation": _interpret_stationarity("RMSD", "Å", st)}


def _rmsf(ctx, select):
    from MDAnalysis.analysis import align, rms
    # AlignTraj(in_memory=True) rewrites coordinates in place, which would
    # corrupt later analyses (density, contacts) in the same batch, so the
    # alignment runs on a private copy of the universe.
    u = ctx.u.copy()
    prot = _select(u, select)
    avg = align.AverageStructure(u, u, select=select, ref_frame=0).run()
    align.AlignTraj(u, avg.results.universe, select=select,
                    in_memory=True).run()
    R = rms.RMSF(prot).run()
    atom_rmsf = np.asarray(R.results.rmsf)
    # one value per residue: mean over that residue's atoms
    ridx = prot.resindices
    uniq, inv = np.unique(ridx, return_inverse=True)
    sums = np.bincount(inv, weights=atom_rmsf)
    cnt = np.bincount(inv)
    per_res = sums / cnt
    resids = np.array([int(u.residues[i].resid) for i in uniq])
    order = np.argsort(resids, kind="stable")
    png = _plot(resids[order], per_res[order], "residue", "RMSF (Å)",
                f"RMSF per residue ({select})",
                os.path.join(ctx.out_dir, "rmsf.png"))
    top = np.argsort(per_res)[-5:][::-1]
    return {"selection": select, "level": "per-residue (mean over atoms)",
            "summary": _summary(per_res),
            "most_flexible_residues": [int(resids[i]) for i in top],
            "rmsf_values": {int(resids[i]): float(per_res[i])
                            for i in order[:2000]},
            "plot": png,
            "note": "Fluctuations are about the average structure after "
                    "alignment; they depend on the sampled window length."}


def _rgyr(ctx, select):
    ag = _select(ctx.u, select)
    rg = np.array([ag.radius_of_gyration() for _ in ctx.u.trajectory])
    st = tsm.assess_stationarity(rg, ctx.t)
    end = tsm.compare_endpoints(rg)
    ci = st.get("ci95")
    png = _plot(ctx.t, rg, ctx.xlabel, "Rg (Å)",
                f"Radius of gyration ({select})",
                os.path.join(ctx.out_dir, "rgyr.png"),
                mean_band=tuple(ci) if ci else None)
    if end.get("significant") is None:
        reading = "too few frames to compare start and end"
    elif not end["significant"]:
        reading = "no significant change in global size between start and end"
    elif end["diff"] < 0:
        reading = "compaction (end window significantly smaller than start)"
    else:
        reading = "expansion (end window significantly larger than start)"
    return {"selection": select, "summary": _summary(rg),
            "start_vs_end": end, "stationarity": st, "plot": png,
            "interpretation": f"{reading}. "
                              + _interpret_stationarity("Rg", "Å", st)}


def _hbonds(ctx, select):
    from vmd_agent.structure.stats import count_hydrogen_bonds
    u = ctx.u
    ag = _select(u, select)
    counts, method, desc = [], None, None
    for ts in u.trajectory:
        r = count_hydrogen_bonds(ag, _valid_box(ts.dimensions),
                                 exclude_water=False)
        if r is None:
            return {"error": "empty selection"}
        n, method, desc = r
        counts.append(n)
    counts = np.asarray(counts, float)
    st = tsm.assess_stationarity(counts, ctx.t)
    png = _plot(ctx.t, counts, ctx.xlabel, "# H-bonds",
                f"Hydrogen bonds ({select})",
                os.path.join(ctx.out_dir, "hbonds.png"))
    out = {"selection": select, "method": method, "criterion": desc,
           "summary": _summary(counts), "stationarity": st, "plot": png,
           "interpretation": _interpret_stationarity("H-bond count", "", st)}
    if method == "distance_only":
        out["caveat"] = ("Structure has no hydrogens: counts are heavy-atom "
                         "N/O pairs and overestimate true H-bonds. Use a "
                         "topology with hydrogens (PSF, PRMTOP, GRO) for "
                         "angle-based counts.")
    return out


def _contacts(ctx, sel1, sel2, cutoff):
    from MDAnalysis.lib.distances import capped_distance
    u = ctx.u
    a, b = _select(u, sel1), _select(u, sel2)
    n_atom, n_res = [], []
    ra, rb = a.resindices, b.resindices
    for ts in u.trajectory:
        pairs, _ = capped_distance(a.positions, b.positions,
                                   max_cutoff=cutoff,
                                   box=_valid_box(ts.dimensions))
        n_atom.append(len(pairs))
        n_res.append(len(np.unique(
            np.stack([ra[pairs[:, 0]], rb[pairs[:, 1]]], 1), axis=0))
            if len(pairs) else 0)
    n_atom = np.asarray(n_atom, float)
    n_res = np.asarray(n_res, float)
    st = tsm.assess_stationarity(n_atom, ctx.t)
    png = _plot(ctx.t, n_atom, ctx.xlabel, f"# atom contacts < {cutoff} Å",
                "Interface contacts", os.path.join(ctx.out_dir, "contacts.png"))
    in_contact = float(np.mean(n_atom > 0))
    reading = (f"contact present in {100 * in_contact:.0f}% of frames. "
               + _interpret_stationarity("Atom contacts", "", st))
    if in_contact < 1.0 and in_contact > 0:
        reading += " The interface breaks and re-forms during the run."
    return {"sel1": sel1, "sel2": sel2, "cutoff": cutoff,
            "summary": _summary(n_atom),
            "residue_pair_summary": _summary(n_res),
            "fraction_frames_in_contact": in_contact,
            "stationarity": st, "plot": png, "interpretation": reading}


def _distance(ctx, sel1, sel2):
    u = ctx.u
    a, b = _select(u, sel1), _select(u, sel2)
    d = np.array([float(np.linalg.norm(a.center_of_mass()
                                       - b.center_of_mass()))
                  for _ in u.trajectory])
    st = tsm.assess_stationarity(d, ctx.t)
    png = _plot(ctx.t, d, ctx.xlabel, "COM distance (Å)",
                "Distance between selections",
                os.path.join(ctx.out_dir, "distance.png"))
    return {"sel1": sel1, "sel2": sel2, "summary": _summary(d),
            "stationarity": st, "plot": png,
            "interpretation": _interpret_stationarity("COM distance", "Å", st),
            "note": "Centre-of-mass distances are not minimum-image corrected; "
                    "check pbc diagnostics for wrapped systems."}


def _sasa(ctx, select, max_frames=25):
    """Solvent-accessible surface area via freesasa on subsampled frames."""
    try:
        import freesasa
    except Exception as e:
        return {"error": f"freesasa unavailable: {e}"}
    u = ctx.u
    ag = _select(u, select)
    n = len(u.trajectory)
    frames = np.linspace(0, n - 1, min(max_frames, n), dtype=int)
    t, sasa = [], []
    with tempfile.TemporaryDirectory(prefix="vmd_agent_sasa_") as tmp:
        for i in frames:
            u.trajectory[int(i)]
            pdb = os.path.join(tmp, f"f{i}.pdb")
            ag.write(pdb)
            try:
                res = freesasa.calc(freesasa.Structure(pdb))
                sasa.append(res.totalArea())
                t.append(ctx.t[int(i)])
            except Exception:
                continue
    if not sasa:
        return {"error": "SASA computation produced no values."}
    png = _plot(t, sasa, ctx.xlabel, "SASA (Å²)", f"SASA ({select})",
                os.path.join(ctx.out_dir, "sasa.png"))
    return {"selection": select, "n_frames_used": len(sasa),
            "summary": _summary(sasa), "plot": png}


def _density_axis(ctx, select, axis, nbins):
    """1-D number-density profile along an axis (membranes / permeation)."""
    u = ctx.u
    ag = _select(u, select)
    ax_i = {"x": 0, "y": 1, "z": 2}[axis]
    L = None
    d = _valid_box(u.dimensions)
    if d is not None:
        L = float(d[ax_i])
    allpos = np.concatenate([ag.positions[:, ax_i] for _ in u.trajectory])
    hist, edges = np.histogram(allpos, bins=nbins)
    centers = 0.5 * (edges[1:] + edges[:-1])
    dens = hist / max(len(u.trajectory), 1)
    png = _plot(centers, dens, f"{axis} (Å)", "avg count / bin",
                f"Density profile along {axis} ({select})",
                os.path.join(ctx.out_dir, f"density_{axis}.png"))
    return {"selection": select, "axis": axis, "box_length": L,
            "peak_position": float(centers[int(np.argmax(dens))]),
            "plot": png}


def _convergence(ctx, select):
    """Block averages, N_eff and a suggested equilibration cut for RMSD and Rg.

    Reports what the sampled window can and cannot support; it never declares
    a simulation "converged".
    """
    from MDAnalysis.analysis import rms
    u = ctx.u
    ag = _select(u, select)
    rmsd = rms.RMSD(u, select=select, ref_frame=0).run().results.rmsd[:, 2]
    rg = np.array([ag.radius_of_gyration() for _ in u.trajectory])
    out = {}
    for name, series, unit in (("rmsd", rmsd, "Å"), ("rgyr", rg, "Å")):
        st = tsm.assess_stationarity(series, ctx.t)
        eq = st.get("equilibration", {})
        out[name] = {
            "unit": unit, "verdict": st.get("verdict"),
            "reason": st.get("reason"), "n": st.get("n"),
            "statistical_inefficiency": st.get("g"),
            "n_eff": st.get("n_eff"),
            "block_average": st.get("block_average"),
            "suggested_discard_frames": eq.get("t0"),
            "suggested_discard_fraction": eq.get("fraction_discarded"),
        }
    worst = [k for k, v in out.items() if v["verdict"] == "drifting"]
    thin = [k for k, v in out.items() if v["verdict"] == "insufficient_data"]
    msg = []
    if worst:
        msg.append(f"{', '.join(worst)} still drifting")
    if thin:
        msg.append(f"{', '.join(thin)} has too few independent samples")
    return {"selection": select, "series": out,
            "interpretation": ("; ".join(msg) + ". " if msg else "")
            + "These tests detect drift in the sampled window only; they "
              "cannot show that unsampled slow processes are absent."}


# ---------------------------------------------------------------- dispatcher
def _need_sel2(sel2, name):
    """``contacts`` and ``distance`` compare two selections.

    Defaulting the second to the first silently compared a selection with
    itself (self-pairs at distance 0, every pair counted twice, COM distance
    exactly 0), which is never what anyone wants.
    """
    if not sel2:
        raise ValueError(f"'{name}' needs sel2, a second selection to compare "
                         "with the first")
    return sel2


ENV_MAX_GB = "VMD_AGENT_MAX_MEMORY_GB"


def _memory_check(n_atoms: int, n_kept: int, step: int, n_total: int):
    """Refuse a load that would not fit, with the step that would.

    All atoms of every kept frame are copied into RAM as float32 (plus a
    transient second copy while stacking), so 100 000 atoms x 5 000 frames is
    ~12 GB at peak. Returns an error dict, or ``None`` when it fits.
    """
    limit = float(os.environ.get(ENV_MAX_GB, "4"))
    need = n_atoms * n_kept * 12 * 2 / 1e9
    if need <= limit:
        return None
    ratio = need / limit
    return {"error": (f"analysis would need ~{need:.1f} GB of memory for "
                      f"{n_atoms} atoms x {n_kept} frames (limit {limit:g} GB). "
                      f"Use step >= {int(np.ceil(step * ratio))} or set "
                      f"{ENV_MAX_GB} higher."),
            "estimated_gb": round(need, 1), "limit_gb": limit,
            "suggested_step": int(np.ceil(step * ratio)),
            "n_frames_total": n_total}


def analyze_trajectory(topology: str, trajectory: str,
                       analyses: Sequence[str] = ("rmsd", "rgyr"),
                       selection: str = "protein",
                       sel2: Optional[str] = None,
                       cutoff: float = 4.0,
                       axis: str = "z",
                       nbins: int = 50,
                       step: int = 1,
                       out_dir: Optional[str] = None,
                       unwrap: bool = False,
                       dt_ps: Optional[float] = None) -> dict:
    """Run one or more analyses on a trajectory.

    ``analyses`` may contain: ``rmsd rmsf rgyr hbonds contacts distance
    sasa density convergence``. ``contacts``/``distance`` require ``sel2``.
    Set ``unwrap=True`` to make ``selection`` whole across periodic
    boundaries before analysing. ``dt_ps`` sets the real time between saved
    frames when the trajectory header is wrong or missing.
    """
    if not (os.path.exists(topology) and os.path.exists(trajectory)):
        return {"error": "topology or trajectory not found"}
    out_dir = out_dir or tempfile.mkdtemp(prefix="vmd_agent_analysis_")
    os.makedirs(out_dir, exist_ok=True)

    try:
        u = load_universe(topology, trajectory)
    except Exception as e:
        return {"error": f"could not load: {e}"}

    if dt_ps is not None:
        try:
            ok_dt = np.isfinite(float(dt_ps)) and float(dt_ps) > 0
        except (TypeError, ValueError):
            ok_dt = False
        if not ok_dt:
            return {"error": "dt_ps must be a positive, finite number "
                             f"(picoseconds between saved frames), got {dt_ps!r}"}
    step_note = ([f"step={step} is below 1 and was treated as 1"]
                 if int(step) < 1 else [])
    step = max(1, int(step))
    too_big = _memory_check(len(u.atoms), len(range(0, len(u.trajectory), step)),
                            step, len(u.trajectory))
    if too_big:
        return too_big
    notes = list(step_note)
    pbc = pbc_diagnostics(u, selection) if len(u.trajectory) > 1 else \
        {"checked": False, "reason": "single frame"}
    t, xlabel, from_traj, time_info = _time_axis(u, step, dt_ps)
    try:
        u, wnotes = _sanitize_to_memory(u, step=step,
                                        unwrap_sel=selection if unwrap else None)
        notes += wnotes
    except Exception as e:
        return {"error": f"could not prepare trajectory in memory: {e}"}
    if unwrap and pbc.get("warning"):
        pbc["action_taken"] = "selection unwrapped before analysis"

    ctx = SimpleNamespace(u=u, t=t, xlabel=xlabel, out_dir=out_dir, step=step)
    n_frames = len(u.trajectory)
    results = {"topology": topology, "trajectory": trajectory,
               "n_frames": int(n_frames), "step": step, "out_dir": out_dir,
               "time_axis": {"label": xlabel, "from_trajectory": from_traj,
                             **time_info},
               "pbc": pbc, "notes": notes, "results": {}}
    if time_info.get("warning"):
        notes.append(time_info["warning"])
    if not from_traj:
        notes.append("Trajectory has no usable time information; the x axis "
                     "is the frame index (in original-trajectory frames).")

    dispatch = {
        "rmsd": lambda: _rmsd(ctx, selection),
        "rmsf": lambda: _rmsf(ctx, selection),
        "rgyr": lambda: _rgyr(ctx, selection),
        "hbonds": lambda: _hbonds(ctx, selection),
        "contacts": lambda: _contacts(ctx, selection,
                                      _need_sel2(sel2, "contacts"), cutoff),
        "distance": lambda: _distance(ctx, selection,
                                      _need_sel2(sel2, "distance")),
        "sasa": lambda: _sasa(ctx, selection),
        "density": lambda: _density_axis(ctx, selection, axis, nbins),
        "convergence": lambda: _convergence(ctx, selection),
    }
    for a in analyses:
        key = a.lower().strip()
        if key not in dispatch:
            results["results"][key] = {"error": f"unknown analysis '{a}'",
                                       "available": sorted(dispatch)}
            continue
        try:
            u.trajectory[0]
            results["results"][key] = dispatch[key]()
        except Exception as e:  # keep the batch alive
            results["results"][key] = {"error": f"{type(e).__name__}: {e}"}
    return results
