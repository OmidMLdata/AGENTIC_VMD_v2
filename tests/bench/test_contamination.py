"""Real-vs-novel gap, contamination estimator, groups and cost planning."""
from conftest import DATA
import json
import os
import numpy as np
import pytest
from vmd_agent.bench import synth, scorer as S
from vmd_agent.bench import models, run_benchmark, plan_benchmark


def _planted(rng, n_real, n_novel, base_acc, image_boost_real, difficulty_gap):
    """Records with a known difficulty gap (all conditions) and a known extra
    gain on REAL structures in image conditions only (memorisation)."""
    recs = []
    for g, n in (("real", n_real), ("novel", n_novel)):
        for s in range(n):
            for cond in ("text_only", "raw"):
                for q in range(6):
                    p = base_acc + (difficulty_gap if g == "real" else 0.0)
                    if cond == "raw" and g == "real":
                        p += image_boost_real
                    c = rng.random() < min(max(p, 0), 1)
                    recs.append(dict(condition=cond, group=g,
                                     structure=f"{g}{s}", key=f"q{q}",
                                     correct=c, hallucination=not c))
    return recs


def test_estimator_recovers_a_planted_memorisation_effect():
    rng = np.random.default_rng(0)
    recs = _planted(rng, 40, 40, 0.5, image_boost_real=0.25, difficulty_gap=0.10)
    est = S.contamination_estimate(recs, "raw", "real", "novel", n_boot=500)
    assert est["contamination_estimate"] == pytest.approx(0.25, abs=0.08)
    assert est["ci95"][0] > 0.05
    # the raw gap is inflated by the difficulty gap, the adjusted one is not
    raw = S.group_difference(recs, "raw", "real", "novel", n_boot=300)
    assert raw["difference"] > est["contamination_estimate"] + 0.03


def test_estimator_is_null_when_only_difficulty_differs():
    rng = np.random.default_rng(1)
    recs = _planted(rng, 40, 40, 0.5, image_boost_real=0.0, difficulty_gap=0.15)
    est = S.contamination_estimate(recs, "raw", "real", "novel", n_boot=500)
    assert est["ci95"][0] < 0 < est["ci95"][1]
    assert est["gap_reference"] == pytest.approx(0.15, abs=0.08)


def test_estimator_false_positive_rate_is_controlled():
    rng = np.random.default_rng(2)
    excl = 0
    for _ in range(40):
        recs = _planted(rng, 12, 12, 0.5, 0.0, 0.1)
        est = S.contamination_estimate(recs, "raw", "real", "novel", n_boot=150,
                                       seed=1)
        excl += not (est["ci95"][0] < 0 < est["ci95"][1])
    assert excl / 40 <= 0.2          # nominal 5 %, small-N bootstrap is liberal


def test_group_difference_without_both_groups():
    assert S.group_difference([], "raw", "a", "b")["n_a"] == 0


@pytest.fixture(scope="module")
def mixed_set(tmp_path_factory):
    d = tmp_path_factory.mktemp("syn")
    items = synth.generate_set(6, str(d), seed=21)
    real = [os.path.join(DATA, "1ubq.pdb"), os.path.join(DATA, "1lyz.pdb")]
    groups = {p: "real" for p in real}
    groups.update({i["path"]: "synthetic" for i in items})
    return real + [i["path"] for i in items], groups


def test_groups_flow_through_the_runner(mixed_set, tmp_path):
    structs, groups = mixed_set
    s = run_benchmark(structs, models.StatsReaderModel(), str(tmp_path),
                      conditions=["raw", "text_only"], renderer="matplotlib",
                      views=("front",), n_boot=60, groups=groups)
    assert s["groups"] == ["real", "synthetic"]
    assert "raw|real" in s["by_condition_group"]
    assert s["group_gaps"]["raw"]["adjusted"]["n_a"] == 2
    assert "Real-vs-novel gap" in open(tmp_path / "summary.md").read()
    rec = json.loads(open(tmp_path / "records.jsonl").readline())
    assert rec["group"] in ("real", "synthetic")


def test_text_reader_has_no_adjusted_contamination(mixed_set, tmp_path):
    structs, groups = mixed_set
    s = run_benchmark(structs, models.StatsReaderModel(), str(tmp_path),
                      conditions=["legend_stats", "text_only"],
                      renderer="matplotlib", views=("front",), n_boot=200,
                      groups=groups)
    adj = s["group_gaps"]["legend_stats"]["adjusted"]
    assert abs(adj["contamination_estimate"]) < 1e-9        # identical conditions


def test_plan_matches_the_real_call_count(mixed_set, tmp_path):
    structs, groups = mixed_set
    conds = ["blind", "raw", "text_only"]
    plan = plan_benchmark(structs, conds, n_repeats=2)
    run = run_benchmark(structs, models.ConstantModel(), str(tmp_path),
                        conditions=conds, renderer="matplotlib",
                        views=("front",), n_boot=10, n_repeats=2)
    assert plan["n_calls"] == run["n_records"]
    assert plan["est_input_tokens"] > 0 and "est_cost" not in plan


def test_plan_cost_uses_only_caller_supplied_prices(mixed_set):
    structs, _ = mixed_set
    p = plan_benchmark(structs[:2], ["raw"], price_in_per_mtok=2.0,
                       price_out_per_mtok=10.0)
    expect = (p["est_input_tokens"] * 2.0 + p["est_output_tokens"] * 10.0) / 1e6
    assert p["est_cost"] == pytest.approx(expect, rel=1e-3)
