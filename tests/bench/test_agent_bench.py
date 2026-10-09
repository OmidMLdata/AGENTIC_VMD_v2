"""The automation benchmark: suite, scorers, tools, runner, agents."""
import json
import os

import numpy as np
import pytest
from conftest import DATA, UBQ_MD_DIR

from vmd_agent.bench.agent import suite as S
from vmd_agent.bench.agent import scoring, tools
from vmd_agent.bench.agent.agents import (
    LLMAgent, OracleAgent, ReferenceAgent, SloppyAgent)
from vmd_agent.bench.agent.runner import (
    plan_agent_run, run_agent_benchmark)

BASE = {"id": "b0", "topology": os.path.join(UBQ_MD_DIR, "protein.pdb"),
        "trajectory": os.path.join(UBQ_MD_DIR, "protein.dcd")}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("suite"))
    out = S.build_suite(
        d + "/s", [BASE],
        structures=[os.path.join(DATA, "4hhb.pdb"),
                    os.path.join(DATA, "1lyz.pdb")], seed=3)
    return d + "/s", out


def _task(built, tid):
    return next(t for t in built[1]["tasks"] if t["id"] == tid)


def _by_kind(built, kind, n=0):
    return [t for t in built[1]["tasks"] if t["kind"] == kind][n]


# ------------------------------------------------------------------ suite
def test_suite_has_every_family_and_is_deterministic(built, tmp_path):
    fams = built[1]["suite"]["families"]
    assert all(fams[f] > 0 for f in S.FAMILIES)
    again = S.build_suite(str(tmp_path / "again"), [BASE],
                          structures=[os.path.join(DATA, "4hhb.pdb"),
                                      os.path.join(DATA, "1lyz.pdb")], seed=3)
    assert again["truth"].keys() == built[1]["truth"].keys()
    for k, v in built[1]["truth"].items():
        assert json.dumps(v, sort_keys=True) == \
            json.dumps(again["truth"][k], sort_keys=True)


def test_public_view_leaks_nothing(built):
    v = S.public_view(_by_kind(built, "onset"))
    assert set(v) == {"id", "family", "prompt", "files", "workdir"}
    text = json.dumps(v)
    for secret in ("start", "magnitude", "truth", "control", "hinge"):
        assert secret not in text


def test_no_truth_inside_any_workspace(built):
    for _dp, _dn, fs in os.walk(os.path.join(built[0], "work")):
        for f in fs:
            assert f in ("system.pdb", "traj.dcd"), f


def test_suite_refuses_to_overwrite_and_unknown_family(built, tmp_path):
    with pytest.raises(FileExistsError):
        S.build_suite(built[0], [BASE])
    with pytest.raises(ValueError, match="unknown families"):
        S.build_suite(str(tmp_path / "x"), [BASE], families=["nope"])


def test_numeric_truth_matches_the_toolkit_independently(built):
    """Truth is computed here with NumPy; the toolkit must agree to its own
    precision (cross-check of two independent implementations)."""
    from vmd_agent.dynamics.analysis import analyze_trajectory
    t = _by_kind(built, "rmsd_last")
    r = analyze_trajectory(t["files"]["topology"], t["files"]["trajectory"],
                           ["rmsd"], selection="name CA")
    truth = built[1]["truth"][t["id"]]["value"]
    assert r["results"]["rmsd"]["summary"]["last"] == pytest.approx(
        truth, rel=1e-3)
    t = _by_kind(built, "rg_mean")
    r = analyze_trajectory(t["files"]["topology"], t["files"]["trajectory"],
                           ["rgyr"])
    assert r["results"]["rgyr"]["summary"]["mean"] == pytest.approx(
        built[1]["truth"][t["id"]]["value"], rel=1e-3)


def test_injected_event_is_really_in_the_coordinates(built):
    from vmd_agent.bench import events as E
    t = _by_kind(built, "onset")
    ev = built[1]["truth"][t["id"]]["event"]
    d = E.load_real_positions(t["files"]["topology"],
                              t["files"]["trajectory"])
    sig = E.signals_from_positions(d["pos"], d["masses"])
    key = {"hinge": "rmsd", "expansion": "rgyr"}.get(ev["kind"])
    if key:
        x = sig[key]
        noise = E.robust_noise(x[: ev["start"]])
        assert abs(x[-1] - x[ev["start"] - 1]) > 4 * noise
    assert len(d["pos"]) == S.N_FRAMES


def test_defective_workspaces_are_really_defective(built):
    from vmd_agent.dynamics.analysis import analyze_trajectory
    for kind, probe in (("pbc_broken", lambda r: r["pbc"].get("warning")),
                        ("nonfinite_coordinates",
                         lambda r: any("non-finite" in n
                                       for n in r["notes"])),
                        ("atom_count_mismatch", lambda r: r.get("error"))):
        t = _by_kind(built, kind)
        r = analyze_trajectory(t["files"]["topology"],
                               t["files"]["trajectory"], ["rmsd"],
                               selection="name CA")
        assert probe(r), kind
    t = _by_kind(built, "none")
    r = analyze_trajectory(t["files"]["topology"], t["files"]["trajectory"],
                           ["rmsd"], selection="name CA")
    assert "error" not in r and not r["pbc"].get("warning")


def test_selection_truth_uses_independent_geometry(built):
    """The KD-tree truth must equal MDAnalysis' own distance selection."""
    import MDAnalysis as mda
    t = _by_kind(built, "chain_interface")
    u = mda.Universe(t["files"]["topology"])
    truth = set(built[1]["truth"][t["id"]]["atoms"])
    import re
    a, c = re.search(r"of chain (\S+) that are within [\d.]+ A of any "
                     r"protein atom of chain (\S+)\.", t["prompt"]).groups()
    got = set(u.select_atoms(
        f"protein and chainID {a} and around {S.INTERFACE_CUTOFF} "
        f"(protein and chainID {c})", periodic=False).indices)
    assert got == truth


# ---------------------------------------------------------------- scoring
def test_measure_tolerance_and_malformed_answers(built):
    t = _by_kind(built, "rg_mean")
    v = built[1]["truth"][t["id"]]["value"]
    ok = scoring.score_task(t, built[1]["truth"][t["id"]], {"value": v})
    off = scoring.score_task(t, built[1]["truth"][t["id"]],
                             {"value": v * 1.2})
    assert ok["success"] and not off["success"]
    for bad in ({"value": True}, {"value": "x"}, {"value": float("nan")},
                {}):
        assert not scoring.score_task(
            t, built[1]["truth"][t["id"]], bad)["valid"]


def test_a_confident_wrong_answer_is_a_silent_error(built):
    t = _by_kind(built, "rg_mean")
    tr = built[1]["truth"][t["id"]]
    wrong = tr["value"] * 2
    loud = scoring.score_task(t, tr, {"value": wrong,
                                      "issues": ["file looks odd"]})
    quiet = scoring.score_task(t, tr, {"value": wrong})
    shy = scoring.score_task(t, tr, {"abstain": True})
    assert quiet["silent_error"] and not loud["silent_error"]
    assert shy["abstained"] and not shy["silent_error"]
    assert not shy["success"]
    gone = scoring.score_task(t, tr, None)
    assert gone["no_answer"] and not gone["silent_error"]


def test_event_scoring_rewards_nulls_on_controls_and_punishes_false_alarms(
        built):
    ctl = _by_kind(built, "control")
    tr = built[1]["truth"][ctl["id"]]
    assert scoring.score_task(ctl, tr, {"onset_frame": None})["success"]
    fa = scoring.score_task(ctl, tr, {"onset_frame": 40})
    assert not fa["success"] and fa["false_alarm"]
    ev = _by_kind(built, "onset")
    te = built[1]["truth"][ev["id"]]["event"]
    t2 = built[1]["truth"][ev["id"]]
    assert scoring.score_task(ev, t2, {"onset_frame": te["start"]})["success"]
    assert not scoring.score_task(ev, t2, {"onset_frame": te["start"] - 30}
                                  )["success"]
    after = scoring.score_task(ev, t2, {"onset_frame": te["end"] + 20})
    assert not after["success"] and after["error"] == te["end"] + 20 - te["start"]
    assert scoring.score_task(ev, t2, {"onset_frame": te["end"]})["success"]
    assert scoring.score_task(ev, t2, {"onset_frame": None})["missed"]
    assert not scoring.score_task(ev, t2, {"onset_frame": True})["valid"]


def test_diagnosis_wants_a_label_and_no_trusted_number_for_bad_data(built):
    bad = _by_kind(built, "pbc_broken")
    tr = built[1]["truth"][bad["id"]]
    good = scoring.score_task(bad, tr, {"value": None,
                                        "issue": "pbc_broken"})
    num = scoring.score_task(bad, tr, {"value": 1.0, "issue": "pbc_broken"})
    miss = scoring.score_task(bad, tr, {"value": 1.0, "issue": "none"})
    assert good["success"]
    assert not num["success"] and num["number_given_anyway"]
    assert miss["silent_error"]
    assert not scoring.score_task(bad, tr, {"issue": "made_up"})["valid"]
    clean = _by_kind(built, "none")
    tc = built[1]["truth"][clean["id"]]
    assert scoring.score_task(clean, tc, {"value": tc["value"],
                                          "issue": "none"})["success"]
    assert not scoring.score_task(clean, tc, {"value": None,
                                              "issue": "pbc_broken"}
                                  )["success"]


def test_selection_scoring_is_exact_set_equality_and_safe(built):
    t = _by_kind(built, "sidechain_range")
    tr = built[1]["truth"][t["id"]]
    exact = "index " + " ".join(map(str, tr["atoms"]))
    assert scoring.score_task(t, tr, {"selection": exact})["success"]
    near = scoring.score_task(t, tr, {"selection": "protein"})
    assert not near["success"] and 0 < near["jaccard"] < 1
    junk = scoring.score_task(t, tr, {"selection": "this is ((( not valid"})
    assert not junk["valid"] and junk["selection_error"]
    assert not scoring.score_task(t, tr, {"selection": ""})["valid"]
    assert not scoring.score_task(
        t, tr, {"selection": "a" * (scoring.MAX_SELECTION_CHARS + 1)}
    )["valid"]


def test_keyframes_need_real_distinct_images_inside_the_workspace(
        built, tmp_path):
    from PIL import Image
    t = dict(_by_kind(built, "transition"))
    tr = built[1]["truth"][t["id"]]
    ev = tr["event"]
    rng = np.random.default_rng(0)

    def img(name, folder=t["workdir"]):
        p = os.path.join(folder, name)
        Image.fromarray(rng.integers(0, 255, (80, 80, 3),
                                     dtype=np.uint8)).save(p)
        return p
    a, b = img("t_a.png"), img("t_b.png")
    ok = scoring.score_task(t, tr, {"frames": [ev["start"], 0],
                                    "images": [a, b]})
    assert ok["success"]
    far = scoring.score_task(t, tr, {"frames": [0, 119], "images": [a, b]})
    assert far["images_valid"] and not far["captures_event"]
    assert not scoring.score_task(t, tr, {"frames": [ev["start"], 0],
                                          "images": [a, a]})["success"]
    outside = img("t_out.png", str(tmp_path))
    assert not scoring.score_task(t, tr, {"frames": [ev["start"]],
                                          "images": [outside]})["success"]
    assert not scoring.score_task(t, tr, {"frames": [ev["start"]],
                                          "images": [str(tmp_path / "no.png")]
                                          })["success"]
    too_many = {"frames": list(range(tr["k"] + 1)),
                "images": [a] * (tr["k"] + 1)}
    assert not scoring.score_task(t, tr, too_many)["valid"]
    flat = os.path.join(t["workdir"], "flat.png")
    Image.new("RGB", (80, 80), (9, 9, 9)).save(flat)
    assert not scoring.score_task(t, tr, {"frames": [ev["start"]],
                                          "images": [flat]})["success"]


def test_report_is_scored_by_claim_verification(built):
    t = _by_kind(built, "composition", 0)
    tr = built[1]["truth"][t["id"]]
    from vmd_agent.bench import truth as bt
    g = bt.ground_truth(t["files"]["topology"])
    n = g["n_protein_chains"]
    right = scoring.score_task(
        t, tr, {"report": [f"It has {n} protein chains"]})
    wrong = scoring.score_task(
        t, tr, {"report": [f"It has {n + 3} protein chains"]})
    assert right["success"] and right["faithfulness"] == 1.0
    assert not wrong["success"] and wrong["contradicted"] == 1
    mixed = scoring.score_task(
        t, tr, {"report": [f"It has {n} protein chains",
                           f"It has {n + 3} protein chains"]})
    assert mixed["supported"] == 1 and mixed["contradicted"] == 1
    assert not mixed["success"]              # one false claim spoils the report
    prose = scoring.score_task(t, tr, {"report": ["It is lovely."]})
    assert not prose["success"] and prose["unparsed"] == 1
    assert not scoring.score_task(t, tr, {"report": "text"})["valid"]


def test_scorer_bug_is_reported_not_swallowed(built):
    t = dict(_by_kind(built, "rg_mean"))
    r = scoring.score_task(t, {"nope": 1}, {"value": 1.0})
    assert not r["success"] and "scorer_error" in r


# ------------------------------------------------------------------ tools
def test_workspace_sandbox_blocks_paths_outside(built, tmp_path):
    t = _by_kind(built, "rmsd_last")
    env = tools.Environment(t, "vmd_agent")
    out = env.call("read_text_file", {"path": "/etc/hosts"})
    assert out["blocked"] and env.blocked == 1
    out = env.call("analyze_trajectory", {
        "topology": "../../../../etc/hosts", "trajectory": "x"})
    assert out["blocked"]
    link = os.path.join(t["workdir"], "escape")
    os.symlink("/etc", link)
    try:
        assert env.call("read_text_file",
                        {"path": "escape/hosts"})["blocked"]
    finally:
        os.unlink(link)
    assert env.call("list_files", {})["files"]
    assert env.call("read_text_file", {"path": "system.pdb"})["text"]


def test_arms_expose_the_expected_tools_and_exec_is_off_by_default(built):
    t = _by_kind(built, "rmsd_last")
    names = lambda arm, **k: {x["name"] for x in
                              tools.Environment(t, arm, **k).tool_specs()}
    assert "verify_claims" in names("vmd_agent")
    assert "verify_claims" not in names("vmd_agent_no_verify")
    assert "select_keyframes" not in names("vmd_agent_no_keyframes")
    assert "run_python" not in names("python_mdanalysis")
    assert "run_python" in names("python_mdanalysis", allow_exec=True)
    assert {"list_files", "submit_answer"} <= names("vmd_plain")
    env = tools.Environment(t, "python_mdanalysis")
    assert "not available" in env.call("run_python", {"code": "1"})["error"]
    with pytest.raises(ValueError, match="unknown arm"):
        tools.Environment(t, "nope")


def test_run_python_runs_in_the_workspace(built):
    t = _by_kind(built, "rmsd_last")
    env = tools.Environment(t, "python_mdanalysis", allow_exec=True)
    r = env.call("run_python", {"code": "import os;print(os.getcwd())"})
    assert os.path.realpath(t["workdir"]) in r["stdout"]
    assert env.call("run_python", {"code": "raise SystemExit(3)"}
                    )["returncode"] == 3


def test_submit_and_bad_calls_and_step_limit(built):
    t = _by_kind(built, "rmsd_last")
    env = tools.Environment(t, "vmd_agent", max_steps=4)
    assert "error" in env.call("submit_answer", {"answer": "not json"})
    assert env.call("submit_answer", {"answer": '{"value": 1}'})["ok"]
    assert env.submitted == {"value": 1}
    assert "error" in env.call("no_such_tool", {})
    assert "error" in env.call("list_files", {"bogus": 1})
    assert env.tool_errors == 3
    with pytest.raises(tools.StepLimit):
        env.call("list_files", {})
    assert env.call("submit_answer", {"answer": {"value": 2}})["ok"]


def test_compact_shrinks_long_results_without_losing_the_range():
    big = {"x": list(range(1000)), "s": "a" * 5000, "nested": [{"v": [1.0] * 50}]}
    c = tools.compact(big)
    assert c["x"]["_list"] == 1000 and c["x"]["max"] == 999
    assert len(c["s"]) < 700
    assert len(tools.render_result(big, cap=500)) <= 520


# ----------------------------------------------------------------- runner
@pytest.fixture(scope="module")
def baseline_run(built, tmp_path_factory):
    truth = built[1]["truth"]
    runs = [{"label": "oracle", "agent": OracleAgent(truth),
             "arm": "vmd_agent"},
            {"label": "sloppy", "agent": SloppyAgent(), "arm": "vmd_agent"},
            {"label": "reference", "agent": ReferenceAgent(),
             "arm": "vmd_agent"}]
    out = str(tmp_path_factory.mktemp("run"))
    return run_agent_benchmark(built[0], runs, out, n_boot=100), out


def test_the_oracle_scores_everything_and_the_sloppy_agent_does_not(
        baseline_run):
    s = baseline_run[0]["summary"]
    assert s["oracle"]["success"] == 1.0 and s["oracle"]["silent_error"] == 0
    assert s["sloppy"]["success"] < 0.5
    assert s["sloppy"]["silent_error"] > 0.3
    assert s["reference"]["success"] > s["sloppy"]["success"] + 0.3
    for fam, m in s["oracle"]["by_family"].items():
        assert m["success"] == 1.0, fam


def test_runs_are_isolated_and_recorded(baseline_run):
    res, out = baseline_run
    lines = [json.loads(x) for x in open(os.path.join(out, "records.jsonl"))]
    assert len(lines) == res["n_records"]
    assert {"label", "tool_calls", "silent_error", "wall_s"} <= set(lines[0])
    assert os.path.isdir(os.path.join(out, "runs", "oracle"))
    assert os.path.exists(os.path.join(out, "summary.md"))


def test_reference_agent_failures_are_the_expected_toolkit_gaps(baseline_run):
    """Documented limits, not bugs in the benchmark: the toolkit's distance is
    mass-weighted and its detector misses slow transitions."""
    fails = {(r["kind"]) for r in baseline_run[0]["records"]
             if r["label"] == "reference" and not r["success"]}
    assert fails <= {"cog_distance", "onset", "transition"}


def test_runner_rejects_bad_specs(built, tmp_path):
    a = OracleAgent(built[1]["truth"])
    with pytest.raises(ValueError, match="unique"):
        run_agent_benchmark(built[0], [
            {"label": "x", "agent": a, "arm": "vmd_agent"},
            {"label": "x", "agent": a, "arm": "vmd_agent"}], str(tmp_path))
    with pytest.raises(ValueError, match="unknown arm"):
        run_agent_benchmark(built[0], [
            {"label": "x", "agent": a, "arm": "nope"}], str(tmp_path))
    with pytest.raises(ValueError, match="code execution"):
        run_agent_benchmark(built[0], [
            {"label": "x", "agent": a, "arm": "python_mdanalysis"}],
            str(tmp_path))


def test_agent_crash_is_a_failure_not_a_crash_of_the_benchmark(built,
                                                               tmp_path):
    class Boom:
        name = "boom"
        scripted = False

        def run(self, task, env):
            raise RuntimeError("model API down")
    r = run_agent_benchmark(built[0], [{"label": "b", "agent": Boom(),
                                        "arm": "vmd_agent"}],
                            str(tmp_path), families=["measure"], n_boot=0)
    assert r["summary"]["b"]["no_answer"] == 1.0
    assert all("model API down" in x["agent_error"] for x in r["records"])


def test_plan_makes_no_calls_and_never_invents_prices(built):
    p = plan_agent_run(built[0], n_labels=2, repeats=3)
    assert p["estimated_cost"] is None and "note" in p
    q = plan_agent_run(built[0], 2, 3, price_in=1.0, price_out=2.0)
    assert q["estimated_cost"] == pytest.approx(
        (q["input_tokens"] * 1.0 + q["output_tokens"] * 2.0) / 1e6)
    assert q["runs"] == p["runs"] == 2 * 3 * built[1]["suite"]["n_tasks"]


# -------------------------------------------------------------- statistics
def _recs(label, succ, n=12):
    return [{"label": label, "task_id": f"t{i}", "cluster": f"c{i % 6}",
             "family": "measure", "success": s, "silent_error": not s,
             "abstained": False, "no_answer": False}
            for i, s in zip(range(n), succ)]


def test_paired_arm_difference_detects_a_gap_and_respects_clusters():
    recs = _recs("a", [True] * 12) + _recs("b", [False] * 12)
    d = scoring.paired_arms(recs, "a", "b", n_boot=300)
    assert d["mean_difference"] == 1.0 and d["n_clusters"] == 6
    assert d["ci"][0] > 0.9
    same = scoring.paired_arms(recs, "a", "a", n_boot=100)
    assert same["mean_difference"] == 0
    assert scoring.paired_arms(recs, "a", "zzz")["n_tasks"] == 0
    wide = scoring.paired_arms(recs, "a", "b", n_boot=300, alpha=0.01)["ci"]
    assert wide[0] <= d["ci"][0]


def test_summary_reports_silent_share_of_failures():
    recs = _recs("a", [True, False, False, True] * 3)
    recs[1]["silent_error"] = False
    m = scoring.summarize_agents(recs, n_boot=50)["a"]
    assert m["success"] == 0.5 and m["silent_share_of_failures"] == 5 / 6
    assert m["macro_success"] == 0.5               # one family: same as micro


# --------------------------------------------------------------- LLM agent
@pytest.mark.requires_api
def test_a_real_model_drives_the_tool_loop_end_to_end(built, tmp_path):
    """Live: a real model uses the real tools on a real task. It must complete the
    protocol (call tools, submit a well-formed answer, token counts recorded).
    Whether it gets the number right is the benchmark's question, not this test's."""
    import anthropic
    from vmd_agent.bench.agent import runner
    t = _by_kind(built, "rg_mean")
    staged = runner._stage(t, str(tmp_path / "w"))
    env = tools.Environment(staged, "vmd_agent", max_steps=12)
    agent = LLMAgent(anthropic.Anthropic(),
                     os.environ.get("VMD_AGENT_LIVE_MODEL",
                                    "claude-haiku-4-5-20251001"))
    meta = agent.run(S.public_view(staged), env)
    sc = scoring.score_task(staged, built[1]["truth"][t["id"]], env.submitted)
    assert env.submitted is not None and sc["valid"], env.log
    assert meta["tokens_in"] > 0 and meta["tokens_out"] > 0
    assert any(c["tool"] != "submit_answer" for c in env.log)   # it used a tool


def test_a_changed_workspace_file_stops_the_run(built, tmp_path):
    """Results from a suite whose files were edited or regenerated are not
    comparable; the runner must refuse rather than score them."""
    import shutil
    d = str(tmp_path / "copy")
    shutil.copytree(built[0], d)
    t = S.load_suite(d)["tasks"][0]
    # point the copy's tasks at its own files so only the *bytes* differ
    raw = open(os.path.join(d, "tasks.json")).read().replace(built[0], d)
    open(os.path.join(d, "tasks.json"), "w").write(raw)
    t = S.load_suite(d)["tasks"][0]
    assert S.verify_suite_files(S.load_suite(d)["tasks"]) == []
    with open(next(iter(t["files"].values())), "ab") as fh:
        fh.write(b"\nREMARK edited after the suite was built\n")
    with pytest.raises(ValueError, match="changed since it was generated"):
        run_agent_benchmark(d, [{"label": "o", "agent": OracleAgent(
            S.load_suite(d)["truth"]), "arm": "vmd_agent"}],
            str(tmp_path / "out"), n_boot=0)


@pytest.mark.requires_llm
def test_an_open_model_drives_the_tool_loop_end_to_end(built, tmp_path):
    """Live: a real local model through the OpenAI-style API. It must complete the
    protocol (call tools, submit a well-formed answer); whether it is *right* is the
    benchmark's question. Small local models may fail this: that is a result."""
    from vmd_agent.bench.agent import runner
    from vmd_agent.bench.agent.agents import OpenAICompatAgent
    t = _by_kind(built, "rg_mean")
    staged = runner._stage(t, str(tmp_path / "w"))
    env = tools.Environment(staged, "vmd_agent", max_steps=12)
    agent = OpenAICompatAgent(
        os.environ.get("VMD_AGENT_LLM_URL", "http://localhost:11434/v1"),
        os.environ["VMD_AGENT_LIVE_LLM_MODEL"], os.environ.get("VMD_AGENT_LLM_KEY"))
    meta = agent.run(S.public_view(staged), env)
    assert any(c["tool"] != "submit_answer" for c in env.log), env.log
    assert meta["tokens_in"] > 0


def test_agent_compare_command_reports_the_paired_difference(tmp_path, capsys):
    """The CLI command reads the records agent-run wrote and prints paired_arms."""
    import json
    from vmd_agent import cli
    rows = [{"label": lab, "task_id": f"t{i}", "cluster": f"c{i % 3}", "family": "measure",
             "success": lab == "a" or i % 2 == 0}
            for lab in ("a", "b") for i in range(12)]
    p = tmp_path / "records.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    assert cli.main(["bench", "agent-compare", str(p), "--a", "a", "--b", "b"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["n_tasks"] == 12 and out["n_clusters"] == 3
    assert abs(out["mean_difference"] - 0.5) < 1e-9          # a always succeeds; b on every other task
