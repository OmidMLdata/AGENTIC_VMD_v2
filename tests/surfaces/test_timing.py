"""Wall-clock time of every model call and tool call: in the chat, and in the benchmark's records.

The model is a real local HTTP server that speaks the chat API and takes a known time to answer, so the numbers the
chat reports can be compared with a time we chose. The tool is a real tool."""
import http.server
import json
import threading
import time

from vmd_agent import chat

DELAY = 0.25


def _server(replies):
    """Answers each POST with the next of ``replies`` (a dict: content and/or tool_calls) after DELAY seconds, as plain JSON."""
    calls = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
            time.sleep(DELAY)
            msg = {"role": "assistant", **replies[min(len(calls), len(replies)) - 1]}
            usage = {"prompt_tokens": 5, "completion_tokens": 2}
            if calls[-1].get("stream"):                       # the same reply as server-sent events, as streaming clients ask for
                delta = {k: v for k, v in msg.items() if k != "role" and v}
                if "tool_calls" in delta:
                    delta["tool_calls"] = [{"index": i, **c} for i, c in enumerate(delta["tool_calls"])]
                events = [{"choices": [{"delta": delta, "finish_reason": None}]},
                          {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": usage}]
                body = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"
                ctype = "text/event-stream"
            else:
                body = json.dumps({"choices": [{"message": msg, "finish_reason": "stop"}], "usage": usage}).encode()
                ctype = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1", calls


def test_a_turn_reports_where_the_time_went():
    call = {"content": None, "tool_calls": [{"id": "c1", "type": "function",
                                              "function": {"name": "probe_environment", "arguments": "{}"}}]}
    srv, url, calls = _server([call, {"content": "All good."}])
    try:
        s = chat.ChatSession(url, "m", guard=False)
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
    line = chat.clock_line(t)
    assert "model" in line and "2 calls" in line and "tools" in line and "1 call" in line


def test_the_session_adds_up_its_turns_and_a_second_question_is_timed_alone():
    srv, url, _ = _server([{"content": "one"}, {"content": "two"}])
    try:
        s = chat.ChatSession(url, "m", guard=False)
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
    s = chat.ChatSession("http://127.0.0.1:1/v1", "m", echo=seen.append)
    s.run_tool({"id": "1", "name": "list_representations", "arguments": {}})
    assert len(s.turn["tool_calls"]) == 1 and s.turn["tool_calls"][0]["name"] == "list_representations"
    assert any(line.strip().endswith(" s") for line in seen)


def test_the_time_command_reports_the_session_totals(capsys):
    srv, url, _ = _server([{"content": "hi"}])
    lines = iter(["hello", "/time", "/quit"])
    try:
        chat.main(base_url=url, model="m", check_model=False, input_fn=lambda _: next(lines), stream=False)
    finally:
        srv.shutdown()
    out = capsys.readouterr().out
    assert "took" in out and "this conversation:" in out and "model" in out
