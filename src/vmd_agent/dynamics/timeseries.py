"""Statistics for trajectory time series.

The original analysis module called a run "stable" when the standard deviation
of RMSD was below 0.5 Å, or "collapsing" when Rg moved by more than 1 Å. Those
cut-offs depend on system size and on how correlated successive frames are, so
they are wrong for flexible loops, intrinsically disordered proteins and large
complexes alike. This module replaces them with statistics that adapt to the
data:

* **statistical inefficiency** ``g`` and the effective number of independent
  samples ``N_eff = N / g`` (Chodera et al., JCTC 2007), so error bars are not
  understated by treating correlated frames as independent;
* a **block-averaged** standard error;
* a **Mann-Kendall / Theil-Sen** monotonic-trend test;
* a first-half versus second-half **mean comparison** using the corrected error;
* **equilibration detection**: the start time that maximises ``N_eff`` of the
  retained tail.

Every verdict states what it could and could not establish. "No statistically
detectable drift" is deliberately not the same claim as "converged".
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np


# Physical observables here (RMSD in Å, counts, energies) are nowhere near this;
# beyond it squares overflow to inf and every statistic becomes NaN, so such
# values are treated as invalid, exactly like NaN and Inf.
_MAX_ABS = 1e100


def _clean(x: Sequence[float]) -> np.ndarray:
    a = np.asarray(x, dtype=float).ravel()
    return a[np.isfinite(a) & (np.abs(a) <= _MAX_ABS)]


def statistical_inefficiency(x: Sequence[float], mintime: int = 3) -> float:
    """Statistical inefficiency ``g >= 1`` of a (possibly correlated) series.

    Sums the normalised autocorrelation function until it first crosses zero,
    following the standard Chodera/pymbar estimator.
    """
    a = _clean(x)
    n = len(a)
    if n < 4:
        return 1.0
    a = a - a.mean()
    var = float(np.dot(a, a)) / n
    if var <= 1e-300:
        return 1.0
    g = 1.0
    t = 1
    while t < n - 1:
        c = float(np.dot(a[:n - t], a[t:])) / ((n - t) * var)
        if c <= 0.0 and t > mintime:
            break
        g += 2.0 * c * (1.0 - t / n)
        t += 1
    return max(g, 1.0)


def effective_samples(x: Sequence[float]) -> float:
    a = _clean(x)
    if not len(a):
        return 0.0
    return len(a) / statistical_inefficiency(a)


def mean_ci(x: Sequence[float], z: float = 1.96) -> dict:
    """Mean with an autocorrelation-corrected 95 % interval."""
    a = _clean(x)
    if not len(a):
        return {}
    g = statistical_inefficiency(a)
    n_eff = len(a) / g
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    sem = sd / np.sqrt(max(n_eff, 1.0))
    m = float(a.mean())
    return {"mean": m, "sd": sd, "sem": float(sem),
            "ci95": [m - z * sem, m + z * sem],
            "n": int(len(a)), "g": float(g), "n_eff": float(n_eff)}


def block_average(x: Sequence[float], n_blocks: int = 5) -> dict:
    """Mean and standard error from non-overlapping block means."""
    a = _clean(x)
    if len(a) < 2 * n_blocks:
        n_blocks = max(len(a) // 2, 1)
    if n_blocks < 2:
        return {"n_blocks": n_blocks, "block_means": [], "sem": None}
    size = len(a) // n_blocks
    means = np.array([a[i * size:(i + 1) * size].mean()
                      for i in range(n_blocks)])
    sem = float(means.std(ddof=1) / np.sqrt(n_blocks))
    return {"n_blocks": n_blocks, "block_size": int(size),
            "block_means": [float(m) for m in means],
            "mean": float(means.mean()), "sem": sem}


def trend_test(x: Sequence[float], t: Optional[Sequence[float]] = None) -> dict:
    """Mann-Kendall tau/p-value and Theil-Sen slope with a 95 % interval."""
    from scipy import stats
    a = np.asarray(x, dtype=float).ravel()
    tt = np.arange(len(a), dtype=float) if t is None \
        else np.asarray(t, dtype=float).ravel()
    ok = np.isfinite(a) & np.isfinite(tt)
    a, tt = a[ok], tt[ok]
    if len(a) < 8 or np.ptp(a) == 0:
        return {"tau": None, "p_value": None, "slope": None,
                "slope_ci95": None, "note": "too few or constant samples"}
    tau, p = stats.kendalltau(tt, a)
    res = stats.theilslopes(a, tt, alpha=0.95)
    # Kendall's test assumes independence; autocorrelated MD series make the
    # p-value optimistic, so callers thin the series by g before using it.
    return {"tau": float(tau), "p_value": float(p), "slope": float(res[0]),
            "slope_ci95": [float(res[2]), float(res[3])]}


def compare_halves(x: Sequence[float], g: Optional[float] = None,
                   sd: Optional[float] = None) -> dict:
    """Difference between the first and second half, in corrected SEM units.

    ``g`` and ``sd`` let the caller supply the statistical inefficiency and
    noise level estimated on *detrended* data. Without them each half's own
    ``g`` is used, which is wrong for a drifting series: a deterministic trend
    looks like extreme autocorrelation and hides the very drift being tested.
    """
    a = _clean(x)
    if len(a) < 8:
        return {"z": None, "diff": None}
    h = len(a) // 2
    f_mean, s_mean = float(a[:h].mean()), float(a[h:].mean())
    if g is not None and sd is not None:
        se = float(sd * np.sqrt(4.0 * g / len(a)))
    else:
        f, s = mean_ci(a[:h]), mean_ci(a[h:])
        se = float(np.hypot(f["sem"], s["sem"]))
    diff = s_mean - f_mean
    return {"first_half_mean": f_mean, "second_half_mean": s_mean,
            "diff": float(diff), "se": se,
            "z": float(diff / se) if se > 0 else None}


def equilibration_start(x: Sequence[float], nskip: int = 1) -> dict:
    """Frame index that maximises ``N_eff`` of the retained tail."""
    a = _clean(x)
    n = len(a)
    if n < 10:
        return {"t0": 0, "n_eff": effective_samples(a), "fraction_discarded": 0.0}
    best_t, best_neff = 0, -1.0
    for t in range(0, n - 3, max(nskip, 1)):
        neff = (n - t) / statistical_inefficiency(a[t:])
        if neff > best_neff:
            best_t, best_neff = t, neff
    return {"t0": int(best_t), "n_eff": float(best_neff),
            "fraction_discarded": float(best_t / n)}


def assess_stationarity(x: Sequence[float],
                        t: Optional[Sequence[float]] = None,
                        min_neff: float = 10.0) -> dict:
    """Combine the tests above into one honest, evidence-carrying verdict.

    The statistical inefficiency used for the drift tests is estimated on the
    *residuals of a robust linear fit*, so a real trend is not mistaken for
    autocorrelation (which would collapse ``N_eff`` and hide the drift).

    Verdicts
    --------
    ``insufficient_data``   fewer than ``min_neff`` effectively independent
                            samples (checked first, on detrended data)
    ``drifting``            trend and half-vs-half difference are both significant
    ``no_detectable_drift`` neither test significant; this is *not* proof of
                            convergence
    ``ambiguous``           exactly one test is significant
    """
    from scipy import stats as sps
    raw = np.asarray(x, dtype=float).ravel()
    ok = np.isfinite(raw) & (np.abs(raw) <= _MAX_ABS)
    a = raw[ok]
    out = {"n": int(len(a))}
    if len(a) < 4:
        out.update(verdict="insufficient_data",
                   reason="fewer than 4 finite samples")
        return out
    tt = (np.arange(len(raw), dtype=float) if t is None
          else np.asarray(t, dtype=float).ravel())[ok]

    ci = mean_ci(a)
    out.update(ci)
    out["block_average"] = block_average(a)
    out["equilibration"] = equilibration_start(a)

    # detrended noise level and inefficiency
    if len(a) >= 8 and np.ptp(a) > 0:
        slope, icpt = sps.theilslopes(a, tt)[:2]
        resid = a - (icpt + slope * tt)
    else:
        resid = a - a.mean()
    g_res = statistical_inefficiency(resid)
    sd_res = float(resid.std(ddof=1)) if len(resid) > 1 else 0.0
    n_eff_res = len(a) / g_res
    out["g_detrended"] = float(g_res)
    out["n_eff_detrended"] = float(n_eff_res)

    step = max(int(round(g_res)), 1)
    out["trend"] = trend_test(a[::step], tt[::step])
    out["half_comparison"] = compare_halves(a, g=g_res, sd=sd_res)

    p = out["trend"].get("p_value")
    z = out["half_comparison"].get("z")
    trend_sig = p is not None and p < 0.01
    half_sig = z is not None and abs(z) > 3.0
    if n_eff_res < min_neff:
        # Too few independent points for any p-value to be trusted, even a
        # perfectly monotonic one (8 correlated points can look "significant").
        tau = out["trend"].get("tau")
        visible = (" A monotonic trend is visible in the data but cannot be "
                   "assessed with this few independent samples."
                   if tau is not None and abs(tau) > 0.8 else "")
        out.update(verdict="insufficient_data",
                   reason=(f"only {n_eff_res:.1f} effectively independent "
                           f"samples (N={len(a)}, g={g_res:.1f}); too few to "
                           "judge drift or convergence." + visible))
    elif trend_sig and half_sig:
        out.update(verdict="drifting",
                   reason=(f"monotonic trend (Kendall tau="
                           f"{out['trend']['tau']:.2f}, p={p:.2g}) and the "
                           f"second half differs from the first by "
                           f"{z:+.1f} standard errors"))
    elif trend_sig or half_sig:
        out.update(verdict="ambiguous",
                   reason="one of the two drift tests is significant and the "
                          "other is not; extend sampling before concluding")
    else:
        out.update(verdict="no_detectable_drift",
                   reason="no significant trend or first/second-half "
                          "difference; this does not prove convergence, only "
                          "that drift was not detected with this much data")
    return out


def compare_endpoints(x: Sequence[float], window: float = 0.1) -> dict:
    """Change between the start and end windows, in corrected SEM units.

    Used for radius of gyration and similar scalars where the question is
    "did the system end up different from where it began".
    """
    a = _clean(x)
    n = len(a)
    if n < 8:
        return {"significant": None, "note": "too few frames"}
    w = max(int(n * window), 3)
    s, e = mean_ci(a[:w]), mean_ci(a[-w:])
    # a window of w correlated points can claim N_eff < 1; floor at 1 sample
    se = float(np.hypot(s["sem"], e["sem"]))
    diff = e["mean"] - s["mean"]
    z = diff / se if se > 0 else (0.0 if diff == 0 else float("inf"))
    return {"start_mean": s["mean"], "end_mean": e["mean"],
            "diff": float(diff), "z": float(z),
            "significant": bool(abs(z) > 3.0), "window_frames": int(w)}
