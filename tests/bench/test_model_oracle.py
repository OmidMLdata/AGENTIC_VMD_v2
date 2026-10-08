"""The benchmark checked against itself: a perfect agent passes every task, a lazy one passes none, and the documentation says what the code says."""
import os

import pytest

from vmd_agent import model_bench as B, model_oracle, model_tasks as M

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    folder = str(tmp_path_factory.mktemp("or") / "base")
    return folder, B.prepare(folder)


def test_every_task_has_an_oracle_and_nothing_else_does():
    assert set(model_oracle.ORACLE) == {t.id for t in M.TASKS}
    for t in M.TASKS:
        o = model_oracle.ORACLE[t.id]
        assert o.expected.strip() and callable(o.plan) and callable(o.answer)
        if t.decline:
            assert all(name not in ("vmd_measure",) for name, _ in o.plan({}))        # a refusal is never the plan to run a measurement


def test_a_perfect_agent_passes_every_task_this_computer_can_run(tmp_path):
    results = B.run_oracle(str(tmp_path), skip=["network"])
    failed = [(r["task"], r["reason"]) for r in results if r["passed"] is False]
    assert not failed, failed
    assert sum(r["passed"] is True for r in results) > 25


@pytest.mark.requires_vmd
@pytest.mark.requires_ffmpeg
def test_a_perfect_agent_passes_every_task_with_vmd_and_ffmpeg(tmp_path):
    results = B.run_oracle(str(tmp_path), skip=["network"])
    assert not [r for r in results if r["passed"] is False]
    assert all("network" in r["reason"] for r in results if r["passed"] is None), [(r["task"], r["reason"]) for r in results if r["passed"] is None]


@pytest.mark.requires_network
def test_the_network_tasks_pass_for_a_perfect_agent(tmp_path):
    results = B.run_oracle(str(tmp_path), categories=["network"])
    assert [r["task"] for r in results if r["passed"] is False] == []


def test_a_lazy_agent_that_calls_no_tool_and_says_nothing_useful_passes_no_task(prepared):
    folder, prep = prepared
    base = prep["info"]["folder"]
    passing = [t.id for t in M.TASKS if _grade(t, M.Run("Done.", [], base, prep["truth"])) is None]
    assert passing == [], f"graders that accept 'Done.': {passing}"


def test_the_right_answer_does_not_count_without_the_tool_call_that_earns_it(prepared):
    """Success needs the tool call as well as the answer (the runner's rule), so a model that states the facts from memory fails every task that has tools."""
    folder, prep = prepared
    base, truth = prep["info"]["folder"], prep["truth"]
    for t in M.TASKS:
        if t.tools:
            assert M.Run("", [], base, truth).called(*t.tools) is None


def _grade(task, run):
    try:
        return task.grade(run)
    except Exception as e:
        return f"grader error {e}"


def test_the_task_page_in_the_docs_is_the_page_the_code_makes():
    page = open(os.path.join(ROOT, "docs", "benchmarks", "model-benchmark-tasks.md"), encoding="utf-8").read()
    assert page.strip() == B.reference_markdown().strip(), "docs/benchmarks/model-benchmark-tasks.md is out of date: regenerate it with model_bench.reference_markdown()"
    assert all(f"`{t.id}`" in page for t in M.TASKS)


def test_the_command_prints_the_reference_and_runs_the_oracle(tmp_path, capsys):
    from vmd_agent import cli
    assert cli.main(["bench", "models", "--list", "--reference"]) == 0
    out = capsys.readouterr().out
    assert "expected:" in out and "binding free energy" in out
    assert cli.main(["bench", "models", "--oracle", "--only", "slurm", "which_workflows", "--data-dir", str(tmp_path)]) == 0
    assert "2 passed, 0 failed" in capsys.readouterr().out
