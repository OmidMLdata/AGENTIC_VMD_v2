"""The statistics replace fixed thresholds, so they need their own validation:
known autocorrelation, false-positive rate and power."""
import numpy as np

from vmd_agent.dynamics import timeseries as ts


def ar1(rng, n, phi):
    e = rng.normal(0, 1, n)
    x = np.zeros(n)
    s = np.sqrt(1 - phi ** 2)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + s * e[i]
    return x


def test_white_noise_has_unit_inefficiency():
    rng = np.random.default_rng(0)
    gs = [ts.statistical_inefficiency(rng.normal(size=2000)) for _ in range(20)]
    assert 0.9 < np.mean(gs) < 1.3


def test_ar1_inefficiency_matches_theory():
    # g = (1 + phi) / (1 - phi) for an AR(1) process
    rng = np.random.default_rng(1)
    phi = 0.8
    gs = [ts.statistical_inefficiency(ar1(rng, 20000, phi)) for _ in range(6)]
    assert abs(np.mean(gs) - (1 + phi) / (1 - phi)) < 2.0   # theory: 9


def test_ci_widens_with_autocorrelation():
    rng = np.random.default_rng(2)
    a = rng.normal(size=1000)
    b = ar1(rng, 1000, 0.95)
    assert ts.mean_ci(b)["sem"] / b.std() > ts.mean_ci(a)["sem"] / a.std()


def test_ci_covers_true_mean():
    rng = np.random.default_rng(3)
    covered = 0
    for _ in range(200):
        x = 5.0 + ar1(rng, 600, 0.8)
        lo, hi = ts.mean_ci(x)["ci95"]
        covered += lo <= 5.0 <= hi
    assert covered / 200 > 0.85           # nominal 95 %, estimator is slightly liberal


def test_clear_drift_is_detected():
    rng = np.random.default_rng(4)
    x = ar1(rng, 1500, 0.8) + np.linspace(0, 8, 1500)
    assert ts.assess_stationarity(x)["verdict"] == "drifting"


def test_stationary_series_is_rarely_flagged():
    rng = np.random.default_rng(5)
    flagged = sum(ts.assess_stationarity(ar1(rng, 1500, 0.8))["verdict"]
                  == "drifting" for _ in range(60))
    assert flagged <= 6                   # false-positive rate <= 10 %


def test_too_few_independent_samples_is_not_called_stable():
    rng = np.random.default_rng(6)
    x = ar1(rng, 40, 0.97)                # N=40 but N_eff is tiny
    st = ts.assess_stationarity(x)
    assert st["verdict"] == "insufficient_data"
    assert "independent" in st["reason"]


def test_no_drift_verdict_does_not_claim_convergence():
    rng = np.random.default_rng(7)
    st = ts.assess_stationarity(rng.normal(size=800))
    assert st["verdict"] == "no_detectable_drift"
    assert "not prove convergence" in st["reason"]


def test_equilibration_start_skips_initial_transient():
    rng = np.random.default_rng(8)
    x = ar1(rng, 1000, 0.5)
    x[:150] += np.linspace(10, 0, 150)
    assert 60 < ts.equilibration_start(x)["t0"] < 400


def test_block_average_requires_data():
    assert ts.block_average([1.0])["sem"] is None


def test_endpoint_comparison():
    rng = np.random.default_rng(9)
    x = ar1(rng, 600, 0.5)
    x[-60:] += 6
    r = ts.compare_endpoints(x)
    assert r["significant"] and r["diff"] > 0
    assert ts.compare_endpoints(ar1(rng, 600, 0.5))["significant"] in (False, True)
    assert ts.compare_endpoints([1, 2, 3])["significant"] is None
