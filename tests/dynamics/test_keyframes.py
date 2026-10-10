import numpy as np
import pytest

from vmd_agent import auto
import keyframe_theory as kt
from vmd_agent.dynamics import keyframes as kf


def ar1(rng, n, phi=0.9):
    e = rng.normal(0, 1, n)
    x = np.zeros(n)
    s = np.sqrt(1 - phi ** 2)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + s * e[i]
    return x


def test_uniform_frames_include_endpoints():
    f = kf.uniform_frames(1000, 9)
    assert f[0] == 0 and f[-1] == 999 and len(f) == 9
    assert kf.uniform_frames(1, 5) == [0] and kf.uniform_frames(10, 1) == [0]


def test_injected_event_is_found_and_uniform_misses_it():
    rng = np.random.default_rng(1)
    n = 1000
    x = ar1(rng, n)
    x[400:420] += np.linspace(0, 12, 20)
    x[420:] += 12
    ev = [{"start": 400, "end": 420}]
    sel = kf.select_keyframes_from_signals({"obs": x, "noise": ar1(rng, n)},
                                           k=9)["indices"]
    assert kt.evaluate_sampling(sel, ev)["recall_hit"] == 1.0
    assert kt.evaluate_sampling(kf.uniform_frames(n, 9), ev)["recall_hit"] == 0.0


def test_budget_and_endpoints_respected():
    rng = np.random.default_rng(2)
    r = kf.select_keyframes_from_signals({"a": ar1(rng, 500)}, k=7)
    assert len(r["indices"]) == 7
    assert r["indices"][0] == 0 and r["indices"][-1] == 499
    assert r["reasons"][0] == "first frame"


def test_pure_noise_gets_even_coverage_not_phantom_events():
    rng = np.random.default_rng(3)
    r = kf.select_keyframes_from_signals({"a": ar1(rng, 1000)}, k=9, z_min=8)
    gaps = np.diff(r["indices"])
    assert gaps.max() < 3 * gaps.min() + 5          # roughly even
    assert sum("change" in v for v in r["reasons"].values()) <= 1


def test_constant_signal_does_not_crash():
    r = kf.select_keyframes_from_signals({"a": np.ones(100)}, k=5)
    assert len(r["indices"]) == 5


def test_budget_larger_than_trajectory_returns_all():
    r = kf.select_keyframes_from_signals({"a": np.arange(5.0)}, k=20)
    assert r["indices"] == [0, 1, 2, 3, 4]


def test_change_scores_peak_at_the_step():
    x = np.concatenate([np.zeros(50), np.ones(50)])
    s = kf.change_scores(x, 10)
    assert abs(int(np.argmax(s)) - 50) <= 1


def test_evaluate_sampling_metrics():
    ev = [{"start": 10, "end": 20}, {"start": 50, "end": 60}]
    r = kt.evaluate_sampling([0, 15, 99], ev)
    assert r["recall_hit"] == 0.5 and r["recall_bracketed"] == 1.0
    assert r["per_event"][0]["localisation_error_frames"] == 0
    assert kt.evaluate_sampling([0, 12, 55, 99], ev)["recall_hit"] == 1.0


def test_analytic_uniform_hit_probability_matches_simulation():
    rng = np.random.default_rng(4)
    n, k = 1000, 9
    sel = kf.uniform_frames(n, k)
    for L in (20, 50, 100):
        hits = 0
        N = 4000
        for _ in range(N):
            s = int(rng.integers(100, 900 - L))
            hits += kt.evaluate_sampling(sel, [{"start": s, "end": s + L}])[
                "recall_hit"]
        assert hits / N == pytest.approx(kt.hit_probability_uniform(n, k, L),
                                         abs=0.04)


def test_frames_needed_is_consistent_with_probability():
    k = kt.frames_needed_uniform(1000, 20, p=0.95)
    assert kt.hit_probability_uniform(1000, k, 20) >= 0.95
    assert kt.hit_probability_uniform(1000, k - 1, 20) < 0.95


def test_end_to_end_on_a_trajectory(sample, tmp_path):
    pdb, dcd = sample
    r = auto.select_keyframes(pdb, dcd, k=4, sel2="resname LIG",
                            out_dir=str(tmp_path), render=True,
                            renderer="matplotlib", width=160, height=120)
    assert r["ok"] and r["frames"][0] == 0 and r["frames"][-1] == 7
    assert len(r["uniform_baseline"]) == 4
    assert {"rmsd", "rgyr", "contacts", "com_distance"} <= set(r["signals_used"])
    assert r["rendered"]["ok"] and r["rendered"]["n_rendered"] == len(r["frames"])
    import os
    assert os.path.exists(r["signal_plot"])
    assert "view the frames" in r["caveat"].lower()


def test_bad_selection_is_structured_error(sample):
    pdb, dcd = sample
    r = kf.select_keyframes(pdb, dcd, selection="resname NOPE")
    assert not r["ok"] and "matched 0 atoms" in r["error"]


def test_event_aware_selection_beats_uniform_on_an_abrupt_event_and_uniform_matches_its_theory():
    """A short event (10 of 600 frames) in autocorrelated noise: nine uniform frames mostly miss it, as the closed-form hit probability says; the event-aware selection finds it."""
    rng = np.random.default_rng(0)
    n, k, length, snr, phi, trials = 600, 9, 10, 8.0, 0.9, 60

    def ar1():
        e, x = rng.normal(0, 1, n), np.zeros(n)
        x[0] = e[0]
        for i in range(1, n):
            x[i] = phi * x[i - 1] + np.sqrt(1 - phi ** 2) * e[i]
        return x
    hit = {"uniform": 0, "event_aware": 0}
    for _ in range(trials):
        start = int(rng.integers(int(0.1 * n), int(0.9 * n) - length))
        x = ar1()
        x[start:start + length] += np.linspace(0, snr, length)
        x[start + length:] += snr
        events = [{"start": start, "end": start + length}]
        picks = {"uniform": kf.uniform_frames(n, k),
                 "event_aware": kf.select_keyframes_from_signals({"obs": x, "other": ar1()}, k=k, z_min=6.0)["indices"]}
        for name, sel in picks.items():
            hit[name] += kt.evaluate_sampling(sel, events)["recall_hit"]
    assert hit["uniform"] / trials < 0.3 and hit["event_aware"] / trials > 0.8
    assert abs(hit["uniform"] / trials - kt.hit_probability_uniform(n, k, length)) < 0.15          # simulated uniform sampling agrees with the closed form


@pytest.mark.parametrize("k", [0, -1, 2.5, None, True])
def test_k_must_be_a_positive_integer(sample, k):
    """k <= 0 used to be silently answered with two frames."""
    r = kf.select_keyframes(*sample, k=k)
    assert r["ok"] is False and "k must be" in r["error"]
