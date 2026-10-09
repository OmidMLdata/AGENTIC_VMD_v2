"""The OpenAI-style client. Parsing is tested on the documented response *format*
(plain data, not a pretend server); error handling runs over real sockets; the
success path against a real model is a live test (``requires_llm``)."""
import http.server
import json
import os
import socket
import threading

import pytest

from vmd_agent import llm_client as L
from vmd_agent import toolset


def _reply(message, usage=None, finish="stop"):
    return {"choices": [{"message": message, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 11, "completion_tokens": 5}}


def _tc(name, args, id_="call_1"):
    return {"id": id_, "type": "function",
            "function": {"name": name, "arguments": args}}


# --------------------------------------------------------------------- parsing
def test_a_plain_answer():
    p = L.parse_choice(_reply({"role": "assistant", "content": "It is a protein."}))
    assert p["content"] == "It is a protein." and p["tool_calls"] == []
    assert p["usage"] == {"input_tokens": 11, "output_tokens": 5}


def test_tool_calls_with_json_string_arguments():
    p = L.parse_choice(_reply({"role": "assistant", "content": None, "tool_calls": [
        _tc("detect_system", '{"topology": "a.pdb"}')]}))
    c = p["tool_calls"][0]
    assert c == {"id": "call_1", "name": "detect_system",
                 "arguments": {"topology": "a.pdb"}, "arguments_error": None}


def test_tool_calls_with_object_arguments_and_missing_ids():
    p = L.parse_choice(_reply({"content": "", "tool_calls": [
        {"function": {"name": "probe_environment", "arguments": {}}}]}))
    assert p["tool_calls"][0]["arguments"] == {} and p["tool_calls"][0]["id"]


def test_unreadable_arguments_are_reported_not_raised():
    p = L.parse_choice(_reply({"content": None, "tool_calls": [
        _tc("detect_system", "{not json")]}))
    c = p["tool_calls"][0]
    assert c["arguments"] == {} and "not a JSON object" in c["arguments_error"]
    fenced = L.parse_choice(_reply({"content": None, "tool_calls": [
        _tc("detect_system", '```json\n{"topology": "x.pdb"}\n```')]}))
    assert fenced["tool_calls"][0]["arguments"] == {"topology": "x.pdb"}


NAMES = list(toolset.TOOLS)


def test_a_tool_call_written_as_text_is_accepted_only_for_known_tools():
    text = '{"name": "detect_system", "arguments": {"topology": "a.pdb"}}'
    p = L.parse_choice(_reply({"content": text}), NAMES)
    assert p["content"] is None and p["tool_calls"][0]["name"] == "detect_system"
    assert p["tool_calls"][0]["arguments"] == {"topology": "a.pdb"}
    fenced = L.parse_choice(_reply({"content": "```json\n" + text + "\n```"}), NAMES)
    assert len(fenced["tool_calls"]) == 1
    alias = L.parse_choice(_reply({"content": json.dumps(
        {"name": "detect_system", "parameters": {"topology": "z"}})}), NAMES)
    assert alias["tool_calls"][0]["arguments"] == {"topology": "z"}
    # not a known tool, or ordinary prose: stays an answer
    unknown = L.parse_choice(_reply({"content": '{"name": "rm_rf", "arguments": {}}'}), NAMES)
    assert unknown["tool_calls"] == [] and unknown["content"]
    prose = L.parse_choice(_reply({"content": 'The key "name" is detect_system.'}), NAMES)
    assert prose["tool_calls"] == []
    assert L.parse_choice(_reply({"content": text})) ["tool_calls"] == []   # no names given


def test_a_malformed_reply_is_an_error_not_a_crash():
    for bad in ({}, {"choices": []}, {"error": "x"}, None):
        with pytest.raises(L.LLMError):
            L.parse_choice(bad)


def test_the_history_messages_have_the_shape_the_api_expects():
    parsed = L.parse_choice(_reply({"content": "", "tool_calls": [
        _tc("detect_system", '{"topology": "a.pdb"}')]}))
    a = L.assistant_message(parsed)
    assert a["role"] == "assistant" and a["tool_calls"][0]["type"] == "function"
    assert json.loads(a["tool_calls"][0]["function"]["arguments"]) == {"topology": "a.pdb"}
    t = L.tool_message("call_1", "detect_system", "{}")
    assert t == {"role": "tool", "tool_call_id": "call_1",
                 "name": "detect_system", "content": "{}"}


def test_the_tool_specs_become_chat_api_tools():
    tools = L.to_openai_tools(toolset.tool_specs(["analyze_trajectory"]))
    f = tools[0]["function"]
    assert tools[0]["type"] == "function" and f["name"] == "analyze_trajectory"
    assert f["parameters"]["required"] == ["topology", "trajectory", "analyses"]


def test_long_results_are_compacted_for_a_model():
    out = json.loads(L.render_result({"x": list(range(5000)), "s": "a" * 9000}))
    assert out["x"]["_list"] == 5000 and out["x"]["max"] == 4999
    assert len(L.render_result({"s": "a" * 9000}, cap=500)) <= 520


# ----------------------------------------------- errors, over real sockets
def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_a_server_that_is_not_running_gives_a_helpful_error():
    with pytest.raises(L.LLMError, match="cannot reach the model server"):
        L.list_models(f"http://127.0.0.1:{_closed_port()}/v1", timeout=3)


class _H(http.server.BaseHTTPRequestHandler):
    status, body = 200, b""

    def do_GET(self):
        self.send_response(self.status)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    do_POST = do_GET

    def log_message(self, *a):
        pass


def _serve(status, body):
    handler = type("H", (_H,), {"status": status, "body": body})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


def test_http_errors_and_non_json_bodies_are_reported_with_the_server_text():
    srv, url = _serve(500, b'{"error": "model not found, try pulling it"}')
    try:
        with pytest.raises(L.LLMError, match="HTTP 500.*try pulling"):
            L.chat_completion(url, "m", [{"role": "user", "content": "hi"}])
    finally:
        srv.shutdown()
    srv, url = _serve(200, b"<html>this is not an API</html>")
    try:
        with pytest.raises(L.LLMError, match="did not return JSON"):
            L.list_models(url)
    finally:
        srv.shutdown()


# ---------------------------------------------------------------- live model
@pytest.mark.requires_llm
def test_a_real_model_answers_and_lists_itself():
    url = os.environ.get("VMD_AGENT_LLM_URL", "http://localhost:11434/v1")
    model = os.environ["VMD_AGENT_LIVE_LLM_MODEL"]
    assert model in L.list_models(url) or L.list_models(url) == []
    r = L.chat_completion(url, model, [{"role": "user", "content": "Say OK."}],
                          max_tokens=16, api_key=os.environ.get("VMD_AGENT_LLM_KEY"))
    assert L.parse_choice(r)["content"]


# ------------------------------------------------------------------ streaming, against a real HTTP server
import http.server  # noqa: E402


def _sse_server(events):
    """A real local HTTP server that answers /chat/completions with the given server-sent events (an OpenAI-style
    streaming reply). It exercises the real client code, which is what is under test."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for ev in events:
                self.wfile.write(f"data: {ev}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_a_streamed_answer_arrives_in_pieces_and_is_rebuilt():
    import json
    from vmd_agent import llm_client as L
    ev = [json.dumps({"choices": [{"delta": {"content": t}, "finish_reason": None}]}) for t in ("Hel", "lo ", "world")]
    ev.append(json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}))
    srv = _sse_server(ev)
    try:
        got = []
        resp = L.chat_completion(f"http://127.0.0.1:{srv.server_port}/v1", "m", [{"role": "user", "content": "hi"}],
                                 on_token=got.append)
    finally:
        srv.shutdown()
    parsed = L.parse_choice(resp)
    assert got == ["Hel", "lo ", "world"] and parsed["content"] == "Hello world"
    assert parsed["finish_reason"] == "stop" and parsed["usage"] == {"input_tokens": 7, "output_tokens": 3}


def test_a_streamed_tool_call_is_rebuilt_from_its_pieces():
    import json
    from vmd_agent import llm_client as L
    ev = [json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "inspect_files", "arguments": ""}}]}}]}),
          json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"paths": '}}]}}]}),
          json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '["a.pdb"]}'}}]}, "finish_reason": "tool_calls"}]})]
    srv = _sse_server(ev)
    try:
        resp = L.chat_completion(f"http://127.0.0.1:{srv.server_port}/v1", "m", [{"role": "user", "content": "x"}], on_token=lambda t: None)
    finally:
        srv.shutdown()
    call = L.parse_choice(resp)["tool_calls"][0]
    assert call["name"] == "inspect_files" and call["arguments"] == {"paths": ["a.pdb"]} and call["id"] == "c1"
