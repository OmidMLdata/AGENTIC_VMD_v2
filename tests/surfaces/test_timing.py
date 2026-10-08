"""Wall-clock time of every model call and tool call: in the chat, and in the benchmark's records.

The model is a real local HTTP server that speaks the chat API and takes a known time to answer, so the numbers the
chat reports can be compared with a time we chose. The tool is a real tool."""
import json
import time

from conftest import DELAY, scripted_server
from vmd_agent import agent, chat


def test_a_turn_reports_where_the_time_went():
    call = {"content": None, "tool_calls": [{"id": "c1", "type": "function",
                                              "function": {"name": "probe_environment", "arguments": "{}"}}]}
    srv, url, calls = scripted_server([call, {"content": "All good."}])
    try:
        s = agent.Agent(url, "m", guard=False)
        started = time.time()
        answer = s.ask("how is my setup?")
        wall = time.time() - started
    finally:
        srv.shutdown()
    t = s.last_turn
    assert answer == "All good." and len(calls) == 2
    assert t["model_calls"] == 2 and 2 * DELAY <= t["model_s"] < 2 * DELAY + 1.5      # two replies, each DELAY long
    assert [c["name"] for c in t["tool_calls"]] == ["probe_environment"] and t["tool_s"] > 0
    assert t["tool_s"] + t["model_s"] <= t["wall_s"] + 0.05 and abs(t["wall_s"] - wall) < 0.5
    line = agent.clock_line(t)
    assert "model" in line and "2 calls" in line and "tools" in line and "1 call" in line


def test_the_session_adds_up_its_turns_and_a_second_question_is_timed_alone():
    srv, url, _ = scripted_server([{"content": "one"}, {"content": "two"}])
    try:
        s = agent.Agent(url, "m", guard=False)
        s.ask("hello")
        first = dict(s.last_turn)
        s.ask("hello again")
    finally:
        srv.shutdown()
    assert s.clock["model_calls"] == 2 and s.last_turn["model_calls"] == 1
    assert abs(s.clock["model_s"] - (first["model_s"] + s.last_turn["model_s"])) < 1e-6
    assert s.clock["wall_s"] >= 2 * DELAY


def test_each_tool_call_is_timed_and_shown():
    seen = []
    s = agent.Agent("http://127.0.0.1:1/v1", "m", echo=seen.append)
    s.run_tool({"id": "1", "name": "list_representations", "arguments": {}})
    assert len(s.turn["tool_calls"]) == 1 and s.turn["tool_calls"][0]["name"] == "list_representations"
    assert any(line.strip().endswith(" s") for line in seen)


def test_the_time_command_reports_the_session_totals(capsys):
    srv, url, _ = scripted_server([{"content": "hi"}])
    lines = iter(["hello", "/time", "/quit"])
    try:
        chat.main(base_url=url, model="m", check_model=False, input_fn=lambda _: next(lines), stream=False)
    finally:
        srv.shutdown()
    out = capsys.readouterr().out
    assert "took" in out and "this conversation:" in out and "model" in out


def test_run_returns_everything_about_the_question():
    call = {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "list_representations", "arguments": json.dumps({"category": "surface"})}}]}
    srv, url, _ = scripted_server([call, {"content": "Surf and QuickSurf."}])
    try:
        a = agent.Agent(url, "m", guard=False)
        r = a.run("Which styles draw surfaces?")
        second = a.run("And?")
    finally:
        srv.shutdown()
    assert r.answer == "Surf and QuickSurf." and [c["name"] for c in r.calls] == ["list_representations"] and r.calls[0]["arguments"] == {"category": "surface"}
    assert r.clock["model_calls"] == 2 and r.tokens_in == 10 and r.tokens_out == 4 and r.widened == [] and r.calls[0]["repairs"] == []
    assert second.calls == [] and second.tokens_in == 5                 # a second question reports only its own calls and tokens
