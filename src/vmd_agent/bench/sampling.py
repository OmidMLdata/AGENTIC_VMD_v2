"""Simulation study: uniform versus event-aware frame selection.

Question: for a fixed frame budget ``k``, how often does each strategy place a
frame inside an event of a given length and signal-to-noise ratio?

Signals are autocorrelated AR(1) noise (like an MD observable) plus an injected
transition at a random position: a ramp of ``event_len`` frames followed by a
sustained shift of ``snr`` noise standard deviations. The same series is given
to both selectors, so differences are due to the strategy alone. The analytic
hit probability of uniform sampling is reported alongside the simulated value
as a check.
"""
from __future__ import annotations

from typing import List, Sequence

import numpy as np

from vmd_agent.dynamics.keyframes import (
    select_keyframes_from_signals, uniform_frames, evaluate_sampling,
    hit_probability_uniform, frames_needed_uniform,
)


def _ar1(rng, n: int, phi: float) -> np.ndarray:
    e = rng.normal(0, 1, n)
    x = np.zeros(n)
    s = np.sqrt(1 - phi ** 2)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + s * e[i]
    return x


def simulate_sampling_study(n_frames: int = 1000, k: int = 9,
                            event_lengths: Sequence[int] = (5, 10, 20, 50, 100),
                            snrs: Sequence[float] = (4.0, 8.0),
                            n_trials: int = 200, phi: float = 0.9,
                            z_min: float = 6.0, seed: int = 0) -> dict:
    """Return a table of hit/bracket rates for each strategy."""
    rng = np.random.default_rng(seed)
    rows: List[dict] = []
    for L in event_lengths:
        for snr in snrs:
            hit = {"uniform": 0, "event_aware": 0}
            bra = {"uniform": 0, "event_aware": 0}
            err = {"uniform": [], "event_aware": []}
            for _ in range(n_trials):
                start = int(rng.integers(int(0.1 * n_frames),
                                         int(0.9 * n_frames) - L))
                x = _ar1(rng, n_frames, phi)
                ramp = np.linspace(0, snr, L)
                x[start:start + L] += ramp
                x[start + L:] += snr
                y = _ar1(rng, n_frames, phi)           # an uninformative signal
                ev = [{"start": start, "end": start + L}]
                sel_u = uniform_frames(n_frames, k)
                sel_e = select_keyframes_from_signals(
                    {"obs": x, "other": y}, k=k, z_min=z_min)["indices"]
                for name, sel in (("uniform", sel_u), ("event_aware", sel_e)):
                    r = evaluate_sampling(sel, ev)
                    hit[name] += r["recall_hit"]
                    bra[name] += r["recall_bracketed"]
                    err[name].append(r["mean_localisation_error"])
            rows.append({
                "event_len": L, "snr": snr, "n_trials": n_trials,
                "hit_uniform": hit["uniform"] / n_trials,
                "hit_event_aware": hit["event_aware"] / n_trials,
                "hit_uniform_analytic": hit_probability_uniform(n_frames, k, L),
                "bracketed_uniform": bra["uniform"] / n_trials,
                "bracketed_event_aware": bra["event_aware"] / n_trials,
                "loc_err_uniform": float(np.mean(err["uniform"])),
                "loc_err_event_aware": float(np.mean(err["event_aware"])),
                "frames_needed_uniform_95": frames_needed_uniform(n_frames, L),
            })
    return {"n_frames": n_frames, "k": k, "phi": phi, "z_min": z_min,
            "seed": seed, "rows": rows}


def table_markdown(study: dict) -> str:
    L = [f"Budget k={study['k']} of {study['n_frames']} frames, AR(1) "
         f"phi={study['phi']}, {study['rows'][0]['n_trials']} trials each.", "",
         "| event len | SNR | hit: uniform (analytic) | hit: event-aware | "
         "loc. err uniform | loc. err event-aware | k for 95% uniform |",
         "|---|---|---|---|---|---|---|"]
    for r in study["rows"]:
        L.append(f"| {r['event_len']} | {r['snr']:g} | "
                 f"{r['hit_uniform']:.2f} ({r['hit_uniform_analytic']:.2f}) | "
                 f"{r['hit_event_aware']:.2f} | {r['loc_err_uniform']:.0f} | "
                 f"{r['loc_err_event_aware']:.0f} | "
                 f"{r['frames_needed_uniform_95']} |")
    return "\n".join(L) + "\n"
