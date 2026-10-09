"""The agent with a real language model: the one lane that fails when a change makes the agent worse.

Everything else in the test suite runs the real tools and the real code around the model, but not a model, because a model is slow, varies from
run to run and is not installed on every computer. This lane is skipped unless a model is named:

    VMD_AGENT_LIVE_LLM_MODEL=granite4.1:8b VMD_AGENT_LLM_URL=http://localhost:11434/v1 pytest tests/live -rs

It runs the benchmark's small set (``model_tasks.SMOKE``: one or two tasks per kind of functionality, graded by a program) through
:mod:`vmd_agent.agent` with the tool set in ``VMD_AGENT_LIVE_TOOLS`` (default ``all``, what the chat uses; try ``auto``), and fails if the share of tasks passed falls below
``VMD_AGENT_LIVE_MIN_SUCCESS`` (default 0.5), if any request that must be declined is answered with an invented number or a disabled tool run,
or if the model server failed. Models differ, so the threshold is yours to set for the model you use: run the benchmark once, look at the
rate, and set the threshold a little below it. A run takes a few minutes with a small local model. Nothing is recorded.
"""
import os

import pytest

from vmd_agent import agent as agent_mod, model_bench as B, model_tasks as M

pytestmark = pytest.mark.requires_llm


@pytest.fixture(scope="module")
def records(tmp_path_factory):
    model = os.environ["VMD_AGENT_LIVE_LLM_MODEL"]
    url = os.environ.get("VMD_AGENT_LLM_URL", agent_mod.DEFAULT_URL)
    tools = os.environ.get("VMD_AGENT_LIVE_TOOLS", "all")
    base = tmp_path_factory.mktemp("live")
    skip = [n for n in ("network",)]
    return B.run([model], str(base / "data"), str(base / "out"), url, os.environ.get("VMD_AGENT_LLM_KEY"), only=list(M.SMOKE), tools=tools,
                 skip=skip, log=print)


def test_the_model_server_answered_every_request(records):
    assert records, "no task could run (do the tasks that need VMD or ffmpeg all lack them?)"
    failed = [r["task"] for r in records if r.get("error")]
    assert not failed, f"the model server failed on: {failed}"


def test_enough_of_the_tasks_are_passed(records):
    need = float(os.environ.get("VMD_AGENT_LIVE_MIN_SUCCESS", "0.5"))
    rate = sum(bool(r["success"]) for r in records) / len(records)
    lost = {r["task"]: r["reason"] for r in records if not r["success"]}
    assert rate >= need, f"{rate:.0%} of {len(records)} tasks passed, the threshold is {need:.0%}; failed: {lost}"


def test_requests_that_must_be_declined_are_never_answered_with_an_invented_result(records):
    wrong = {r["task"]: r["reason"] for r in records if r["category"] == "decline" and not r["success"]}
    assert not wrong, wrong


def test_every_run_has_its_time_split_into_model_and_tools(records):
    assert all(r["wall_s"] >= r["model_s"] >= 0 and r["tool_s"] >= 0 and r["model_calls"] >= 1 for r in records)
