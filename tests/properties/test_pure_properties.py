"""Invariants checked on generated inputs (Hypothesis): nothing here may raise,
and each result must satisfy its stated bounds. This found a real bug: values near
1e154 overflowed to NaN in the time-series statistics."""
import math
import os

import numpy as np
from hypothesis import HealthCheck, given, settings, strategies as st

S = settings(max_examples=120, deadline=None, suppress_health_check=list(HealthCheck))
floats = st.floats(allow_nan=True, allow_infinity=True, width=64)
finite = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)

# ---------------- timeseries
from vmd_agent.dynamics import timeseries as ts
@S
@given(st.lists(floats, max_size=300))
def test_stat_inefficiency_never_raises_and_is_at_least_one(x):
    g = ts.statistical_inefficiency(x)
    assert math.isfinite(g) and g >= 1.0

@S
@given(st.lists(floats, max_size=300))
def test_assess_stationarity_total(x):
    r = ts.assess_stationarity(x)
    assert r["verdict"] in {"insufficient_data", "drifting", "no_detectable_drift", "ambiguous"}

@S
@given(st.lists(floats, max_size=200))
def test_mean_ci_block_trend_halves_never_raise(x):
    ts.mean_ci(x); ts.block_average(x); ts.trend_test(x); ts.compare_halves(x)
    ts.equilibration_start(x); ts.compare_endpoints(x)

# ---------------- keyframes
from vmd_agent.dynamics import keyframes as kf
@S
@given(st.integers(1, 5000), st.integers(1, 60))
def test_uniform_frames_valid(n, k):
    f = kf.uniform_frames(n, k)
    assert f == sorted(set(f)) and f[0] == 0 and all(0 <= i < n for i in f) and len(f) <= max(k, 1)

@S
@given(st.lists(st.lists(finite, min_size=1, max_size=400), min_size=1, max_size=3), st.integers(1, 40))
def test_select_keyframes_invariants(sigs, k):
    n = min(len(s) for s in sigs); sigs = {f"s{i}": np.array(s[:n]) for i, s in enumerate(sigs)}
    r = kf.select_keyframes_from_signals(sigs, k=k)
    idx = r["indices"]
    assert idx == sorted(set(idx)) and all(0 <= i < n for i in idx)
    assert len(idx) <= max(k, 2) or len(idx) == n
    if n > 1 and k >= 2: assert 0 in idx and n - 1 in idx

@S
@given(st.lists(st.integers(0, 999), max_size=30), st.integers(0, 900), st.integers(0, 100), st.integers(0, 10))
def test_evaluate_sampling_bounds(sel, start, length, tol):
    r = kf.evaluate_sampling(sel, [{"start": start, "end": start + length}], tol)
    assert 0 <= r["recall_hit"] <= 1 and 0 <= r["recall_bracketed"] <= 1

@S
@given(st.integers(2, 100000), st.integers(2, 200), st.integers(1, 5000))
def test_hit_probability_in_unit_interval(n, k, L):
    assert 0.0 <= kf.hit_probability_uniform(n, k, L) <= 1.0

@S
@given(st.integers(10, 100000), st.integers(1, 5000), st.floats(0.05, 0.99))
def test_frames_needed_meets_target(n, L, p):
    k = kf.frames_needed_uniform(n, L, p)
    assert k >= 1 and (k == 1 or kf.hit_probability_uniform(n, k, L) >= p - 1e-9 or L + 1 >= n)

# ---------------- the structure generator's fold classification
from vmd_agent.bench.truth import classify_fold
@S
@given(st.floats(0, 100), st.floats(0, 100))
def test_classify_fold_total(h, s):
    assert classify_fold(h, s) in {"alpha", "beta", "mixed", "coil"}

# ---------------- claims parser
from vmd_agent.evidence import claims as cl
@S
@given(st.text(max_size=600))
def test_claim_parser_total_and_consistent(t):
    c = cl.parse_claim_text(t)
    assert "type" in c
    if c["type"] is not None:                       # accepted => nothing unaccounted
        assert cl._scope_note(c, t.strip()) is None

# ---------------- security
from vmd_agent import security as sec
@S
@given(st.text(max_size=300))
def test_check_tcl_total(t):
    try: sec.check_tcl(t)
    except sec.SecurityError: pass

@S
@given(st.text(max_size=200))
def test_tcl_path_invariant(p):
    try: out = sec.tcl_path(p)
    except sec.SecurityError: return
    assert not any(ch in out for ch in "{}\\") and not any(ord(ch) < 32 or ord(ch) == 127 for ch in out)

@S
@given(st.text(max_size=120))
def test_tcl_selection_invariant(s):
    try: out = sec.tcl_selection(s)
    except sec.SecurityError: return
    assert not any(ch in out for ch in "{}[];$\"\\\n")

@S
@given(st.lists(st.text(max_size=20), max_size=10))
def test_safe_resnames_partition(names):
    ok, bad = sec.safe_resnames(names)
    assert sorted(ok + bad) == sorted(map(str, names))
    assert all(len(n) <= 8 and not any(c in n for c in "{}[];$\" \\\n") for n in ok)

@S
@given(st.text(max_size=200))
def test_check_path_total(p):
    os.environ["VMD_AGENT_ALLOWED_ROOTS"] = "/tmp/vmd_prop_root"
    try:
        try: sec.check_path(p)
        except sec.SecurityError: pass
    finally:
        os.environ.pop("VMD_AGENT_ALLOWED_ROOTS")

# ---------------- fetch URL policy
from vmd_agent.inputs import fetch as fe
@S
@given(st.text(max_size=120))
def test_check_url_only_raises_unsafeurl(u):
    try: fe.check_url(u)
    except fe.UnsafeURL: pass

# ---------------- mmCIF tokenizer
from vmd_agent.inputs import molio
@S
@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=300))
def test_cif_tokenizer_total(line):
    molio._tokens(line)
