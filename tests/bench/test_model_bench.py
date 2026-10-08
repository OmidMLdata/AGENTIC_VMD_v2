"""The model benchmark's machinery: the tasks, the graders, the runner and the summary.

No language model is judged here. The "model" is a small local server that answers with scripted replies in the chat API's wire format,
so the real chat loop, the real tools and the real graders run, and we can check that a good transcript passes, a lazy one fails, and an
invented number is caught."""
import json
import os

import pytest

from vmd_agent import model_bench as B, model_tasks as M, toolset
from conftest import scripted_server as _server


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    folder = str(tmp_path_factory.mktemp("mb") / "base")
    return folder, B.prepare(folder)


def _call(name, **args):
    return {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def _ask(prepared, tmp_path, task_id, replies, **kw):
    folder, prep = prepared
    srv, url, _ = _server(replies)
    try:
        return B.run_task(next(t for t in M.TASKS if t.id == task_id), "scripted", url, None, prep["info"]["folder"], prep["truth"],
                          str(tmp_path / "work"), **kw)
    finally:
        srv.shutdown()


# ------------------------------------------------------------------------- the task list
def test_tasks_are_well_formed():
    ids = [t.id for t in M.TASKS]
    assert len(ids) == len(set(ids)) and all(t.category in M.CATEGORIES for t in M.TASKS)
    assert all(t.tools and t.decline is False or t.decline and not t.tools for t in M.TASKS), "a task names its tools unless it must be declined"
    assert all(set(t.tools) <= set(toolset.TOOLS) for t in M.TASKS)
    assert all(n in ("vmd", "ffmpeg", "network") for t in M.TASKS for n in t.needs)
    assert all(M.by_category()[c] for c in M.CATEGORIES), "every category has tasks"


def test_every_tool_is_asked_for_by_some_task_or_excused():
    asked = {n for t in M.TASKS for n in t.tools}
    missing = set(toolset.TOOLS) - asked - set(M.NOT_ASKED)
    assert not missing, f"tools no task asks for and nothing excuses: {sorted(missing)}"
    assert set(M.NOT_ASKED) <= set(toolset.TOOLS)


def test_prompts_name_only_files_that_exist_or_are_made(prepared):
    folder, prep = prepared
    import re
    made = {"ca.dcd", "frame5.pdb", "aligned.pdb", "build/sys", "mutant", "two", "membrane/mem", "tube.pdb", "blob2.dx", "fitted.pdb", "lig.dx", "out.png", "view.png",
            "scene.png", "spin.mp4", "session", "recipe.tcl", "labelled.png", "pics", "job.sbatch", "report.md", "pdbs", "eq", "eq.namd", "movie.mp4", "dry.psf", "dry.pdb", "build/sys_ion.psf", "build/sys_ion.pdb", "provenance.json"}
    absent_on_purpose = {"missing.pdb", "missing.dcd", "/etc/hosts"}
    for t in M.TASKS:
        for f in re.findall(r"[\w/]+\.(?:pdb|dcd|psf|dx|mp4|png|json|namd|tcl|sbatch|md)\b", t.prompt):
            assert f in made or f in absent_on_purpose or os.path.exists(os.path.join(folder, f)), f"{t.id}: {f}"


def test_the_truth_comes_from_the_files_not_from_a_run(prepared):
    truth = prepared[1]["truth"]
    assert truth["n_residues"] == 111 and truth["disulfides"] == 1 and truth["ligand"] == "LIG"
    assert abs(truth["rg"] - 12.3) < 0.2 and abs(truth["drift_total"] - 5.7) < 1e-9
    assert len(truth["near_ligand"]) >= 3 and "prov" in prepared[1]["extras"] and "sess" in prepared[1]["extras"]


# --------------------------------------------------------------------------- the graders
def test_numbers_are_matched_with_a_tolerance_and_as_percentages():
    assert M.has_number("the mean is 12.31 A", 12.30, 0.05) and not M.has_number("the mean is 13.9 A", 12.30, 0.05)
    assert M.has_number("about 47% helix", 0.47, 0.1, percent=True) and M.has_number("0.47 helix", 0.47, 0.1, percent=True)
    assert M.declined(M.Run("I cannot find missing.pdb", [], ".", {})) is None
    assert M.declined(M.Run("The RMSD is 2.0 A.", [], ".", {})) is not None


# ----------------------------------------------------------------------------- the runner
def test_a_good_transcript_passes_and_is_timed(prepared, tmp_path):
    rec = _ask(prepared, tmp_path, "inspect_system", [_call("detect_system", topology="protein.pdb"),
                                                      {"content": "protein.pdb has one protein chain (A) and a ligand, LIG."}])
    assert rec["success"] and rec["tool_ok"] and rec["answer_ok"] and rec["tools_called"] == ["detect_system"] and rec["grounded"] in (True, None)
    assert rec["model_calls"] == 2 and rec["wall_s"] >= rec["model_s"] >= 0.5 and rec["tool_s"] >= 0 and rec["n_tool_calls"] == 1 and rec["tokens_in"] > 0


def test_answering_without_a_tool_fails_even_if_the_words_are_right(prepared, tmp_path):
    rec = _ask(prepared, tmp_path, "inspect_system", [{"content": "It has one protein chain A and a ligand LIG."}], guard=False)
    assert not rec["success"] and rec["answer_ok"] and not rec["tool_ok"] and rec["tools_called"] == []


def test_a_wrong_number_fails_and_an_invented_one_is_marked_ungrounded(prepared, tmp_path):
    ok = _ask(prepared, tmp_path, "stats", [_call("structure_stats", topology="protein.pdb"),
                                            {"content": "It has 1 disulfide bridge and 111 residues."}])
    assert ok["success"]
    bad = _ask(prepared, tmp_path, "stats", [_call("structure_stats", topology="protein.pdb"),
                                             {"content": "It has 3 disulfide bridges and 111 residues. The solvent area is 8421.55."}])
    assert not bad["success"] and "disulfide" in bad["reason"] and bad["grounded"] is False


def test_files_the_model_made_are_checked(prepared, tmp_path):
    good = _ask(prepared, tmp_path, "recipe", [_call("generate_visualization_recipe", topology="protein.pdb", out_path="recipe.tcl"),
                                               {"content": "Saved recipe.tcl."}])
    assert good["success"]
    nothing = _ask(prepared, tmp_path, "recipe", [{"content": "Saved recipe.tcl."}], guard=False)
    assert not nothing["success"] and "recipe.tcl was not written" in nothing["reason"]


def test_a_request_that_cannot_be_done_is_passed_only_by_saying_so(prepared, tmp_path):
    honest = _ask(prepared, tmp_path, "missing_file", [_call("analyze_trajectory", topology="missing.pdb", trajectory="missing.dcd", analyses=["rmsd"]),
                                                       {"content": "I could not do that: missing.pdb does not exist in your files folder."}])
    assert honest["success"] and honest["tool_errors"] == 1
    invented = _ask(prepared, tmp_path, "missing_file", [{"content": "The RMSD of missing.pdb over missing.dcd is 1.84 Å."}], guard=False)
    assert not invented["success"]
    tcl = _ask(prepared, tmp_path, "tcl_disabled", [_call("run_tcl", script="puts hi"), {"content": "That tool is disabled, so I did not run it."}])
    assert tcl["success"]


def test_a_model_server_that_fails_is_recorded_not_raised(prepared, tmp_path):
    folder, prep = prepared
    rec = B.run_task(M.TASKS[0], "m", "http://127.0.0.1:1/v1", None, prep["info"]["folder"], prep["truth"], str(tmp_path / "w"))
    assert not rec["success"] and rec["error"] and "model server failed" in rec["reason"]


def test_a_grader_that_crashes_is_marked_as_a_grader_error(prepared, tmp_path, monkeypatch):
    task = next(t for t in M.TASKS if t.id == "look_at_image")
    monkeypatch.setattr(task, "grade", lambda r: 1 / 0)
    rec = _ask(prepared, tmp_path, "look_at_image", [_call("view_image", path="figure.png"), {"content": "It is an image."}])
    assert not rec["success"] and rec["reason"].startswith("grader error")


# -------------------------------------------------------------------- the whole run, resumed, summarised
def test_a_run_is_resumable_and_summarised(tmp_path):
    srv, url, _ = _server([_call("detect_system", topology="protein.pdb"), {"content": "One chain A and a ligand LIG."}])
    try:
        out, data = str(tmp_path / "out"), str(tmp_path / "data")
        first = B.run(["scripted"], data, out, url, only=["inspect_system", "tcl_disabled"], skip=["vmd"])
        assert [r["task"] for r in first] == ["inspect_system", "tcl_disabled"]
        again = B.run(["scripted"], data, out, url, only=["inspect_system"], skip=["vmd"])
        assert again == []                                                  # already recorded: nothing is asked again
        forced = B.run(["scripted"], data, out, url, only=["inspect_system"], skip=["vmd"], force=True)
        assert len(forced) == 1
    finally:
        srv.shutdown()
    records = B.load_records(out)
    s = B.summarize(records)["scripted (all)"]
    assert s["n"] == 3 and s["ci95"][0] <= s["success"] <= s["ci95"][1] and "inspect" in s["by_category"]
    path = B.write_summary(out)
    text = open(path).read()
    assert "`scripted (all)`" in text and "## By category" in text and "## By task" in text and "inspect_system" in text
    assert json.load(open(os.path.join(out, "summary.json")))["scripted (all)"]["n"] == 3


def test_the_interval_is_honest_for_small_samples():
    lo, hi = B.wilson(3, 3)
    assert lo < 0.5 and hi == 1.0                                           # three out of three is not "certain"
    assert B.wilson(0, 0) == (0.0, 0.0) and B.wilson(5, 10)[0] < 0.5 < B.wilson(5, 10)[1]


def test_unknown_categories_and_tasks_are_refused():
    with pytest.raises(ValueError, match="no such category or task"):
        B.select(["nonsense"])
    assert [t.id for t in B.select(only=["recipe"])] == ["recipe"]
    assert {t.category for t in B.select(["decline"])} == {"decline"}


def test_the_command_lists_summarises_and_refuses_without_a_model(tmp_path, capsys):
    from vmd_agent import cli
    assert cli.main(["bench", "models", "--list"]) == 0
    assert f"{len(M.TASKS)} tasks in {len(M.CATEGORIES)} categories" in capsys.readouterr().out
    assert cli.main(["bench", "models"]) == 2
    out = str(tmp_path / "o")
    os.makedirs(out)
    assert cli.main(["bench", "models", "--summarize", "--out-dir", out]) == 0
    assert "No records yet" in open(os.path.join(out, "summary.md")).read()


def test_a_wrong_chain_or_residue_count_is_not_waved_through(prepared, tmp_path):
    two = _ask(prepared, tmp_path, "inspect_system", [_call("detect_system", topology="protein.pdb"),
                                                      {"content": "It has a ligand, LIG, and the system has 2 protein chains."}])
    assert not two["success"] and "more than one chain" in two["reason"]
    off_by_one = _ask(prepared, tmp_path, "stats", [_call("structure_stats", topology="protein.pdb"),
                                                    {"content": "It has 1 disulfide bridge and 112 protein residues."}])
    assert not off_by_one["success"] and "residue" in off_by_one["reason"]


def test_listing_only_the_true_statements_is_a_good_answer_and_calling_the_false_one_true_is_not(prepared, tmp_path):
    call = _call("verify_claims", topology="protein.pdb", claims=["It has 1 disulfide bond", "It has 2 chains", "It contains a ligand"])
    only_true = _ask(prepared, tmp_path, "claims_mixed", [call, {"content": "True: (1) one disulfide bond is supported and (3) the ligand is present."}])
    assert only_true["success"], only_true["reason"]
    says_false = _ask(prepared, tmp_path, "claims_mixed", [call, {"content": "(1) is true, (3) is true; (2) 2 chains is false, there is only 1 chain."}])
    assert says_false["success"]
    wrong = _ask(prepared, tmp_path, "claims_mixed", [call, {"content": "All three are true: (2) 2 chains is supported."}])
    assert not wrong["success"] and "true" in wrong["reason"]


def test_the_whole_job_route_counts_as_a_fit_when_it_reports_a_good_correlation(prepared, tmp_path):
    folder, prep = prepared
    run = M.Run("The fit reached a correlation of 0.99.", [{"name": "run_workflow", "arguments": {"name": "cryoem_fit"}, "result": {"ok": True}}], folder, prep["truth"])
    task = next(t for t in M.TASKS if t.id == "fit_map")
    assert task.grade(run) is None
    assert task.grade(M.Run("It fitted well.", run.calls, folder, prep["truth"])) is not None
    assert task.grade(M.Run("It fitted well.", [], folder, prep["truth"])) == "no fit was run"


def test_the_catalogue_option_runs_the_models_the_server_has_and_skips_the_rest(tmp_path, capsys):
    from vmd_agent import cli, models
    have = models.CATALOGUE[1].tag
    srv, url, requests = _server([_call("run_workflow"), {"content": "The workflows are structure_overview, equilibration_check, interaction_report, compare_runs, prepare_simulation and cryoem_fit."}],
                                 models=(have,))
    try:
        code = cli.main(["bench", "models", "--catalogue", "--base-url", url, "--only", "which_workflows", "--data-dir", str(tmp_path / "d"), "--out-dir", str(tmp_path / "o")])
    finally:
        srv.shutdown()
    out = capsys.readouterr().out
    assert code == 0 and f"pass  {have}  which_workflows" in out
    assert out.count("not on the server (add --pull to download it); skipped") == len(models.CATALOGUE) - 1
    assert {r["model"] for r in B.load_records(str(tmp_path / "o"))} == {have}


def test_without_a_model_or_the_catalogue_the_command_says_what_to_give(capsys):
    from vmd_agent import cli
    assert cli.main(["bench", "models"]) == 2
    assert "--catalogue" in capsys.readouterr().err


def test_unloading_a_model_asks_the_server_to_free_it(monkeypatch):
    import json as _json
    import threading
    import http.server
    from vmd_agent import ollama_local
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, _json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(ollama_local, "port", lambda: srv.server_port)
    try:
        assert ollama_local.unload("granite4.1:8b") is True
    finally:
        srv.shutdown()
    assert seen == [("/api/generate", {"model": "granite4.1:8b", "keep_alive": 0})]
    assert ollama_local.unload("x", timeout=1) is False                              # no server there any more: False, not an exception
