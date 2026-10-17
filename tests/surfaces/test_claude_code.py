"""Claude Code as the chat's assistant: the command it is run with, and how its stream becomes the chat's events and answer.

A stand-in `claude` replays Claude Code's stream-json events (the same shapes as Claude Code 2.x prints), so the test needs neither
Claude Code nor a sign-in. Whether a real Claude Code connects to the tools is checked when one is installed."""
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

from vmd_agent import claude_code as C
from vmd_agent.llm_client import LLMError

FAKE = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("9.9.9 (Claude Code)"); sys.exit(0)
if args == ["--help"]:
    print("  --tools <tools...>  ...\n  --permission-mode <mode> (choices: \"dontAsk\", \"plan\")"); sys.exit(0)
question = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({"args": args, "question": question, "cwd": os.getcwd()}) + "\n")
mode = os.environ.get("FAKE_MODE", "ok")
def out(o): print(json.dumps(o), flush=True)
out({"type": "system", "subtype": "init", "session_id": "sess-1", "mcp_servers": [{"name": "vmd-agent", "status": "connected"}], "tools": []})
if mode == "login":
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": "Not logged in · Please run /login"}]}})
    out({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login", "session_id": "sess-1"}); sys.exit(1)
if mode == "crash":
    print("boom", file=sys.stderr); sys.exit(3)
out({"type": "assistant", "message": {"content": [{"type": "text", "text": "Loading it."},
     {"type": "tool_use", "id": "t1", "name": "mcp__vmd-agent__window_load", "input": {"topology": "1beb.pdb"}}]}})
out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
     "content": [{"type": "text", "text": json.dumps({"ok": True, "summary": "Loaded 1beb.pdb"})}]}]}})
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "mcp__vmd-agent__window_snapshot", "input": {"out_png": "w.png"}}]}})
out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "is_error": False,
     "content": [{"type": "text", "text": json.dumps({"ok": True, "image": "w.png"})}]}]}})
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t3", "name": "mcp__vmd-agent__window_view", "input": {"action": "spin"}}]}})
out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t3",
     "content": [{"type": "text", "text": json.dumps({"ok": False, "error": "action must be one of: reset, rotate"})}]}]}})
out({"type": "result", "subtype": "success", "is_error": False, "result": "1BEB has two chains; the picture is w.png.", "session_id": "sess-1",
     "num_turns": 4, "duration_api_ms": 2500, "total_cost_usd": 0.01, "usage": {"input_tokens": 100, "output_tokens": 20}})
'''


@pytest.fixture
def claude(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "claude"
    exe.write_text(FAKE.replace("{python}", sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    data = tmp_path / "data"
    data.mkdir()
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(data))
    _fresh_search()
    return {"exe": str(exe), "data": str(data), "log": log}


def _fresh_search():
    C._help_cache.clear()
    C._checked.clear()
    C._found.update(path=None, when=0.0, searched=[])


def _calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


@pytest.mark.skipif(os.name == "nt", reason="the stand-in is a shell-less script")
def test_a_question_becomes_tool_events_and_an_answer_and_the_conversation_continues(claude):
    s = C.Session("sonnet", root=claude["data"])
    events = []
    s.on_event = events.append
    answer = s.ask("what is in 1beb.pdb?")
    assert answer == "1BEB has two chains; the picture is w.png."
    starts = [e for e in events if e["type"] == "tool_start"]
    ends = [e for e in events if e["type"] == "tool_end"]
    assert [e["name"] for e in starts] == ["window_load", "window_snapshot", "window_view"]          # vmd-agent's names, as the chat shows them
    assert ends[0]["result"] == {"ok": True, "summary": "Loaded 1beb.pdb"} and ends[1]["result"]["image"] == "w.png"
    assert ends[0]["error"] is None and "action must be one of" in ends[2]["error"]
    assert s.last_turn["model_calls"] == 4 and s.last_turn["model_s"] == 2.5 and len(s.last_turn["tool_calls"]) == 3
    first = _calls(claude["log"])[0]
    assert first["question"] == "what is in 1beb.pdb?" and os.path.realpath(first["cwd"]) == os.path.realpath(claude["data"])
    a = first["args"]
    assert a[0] == "-p" and a[a.index("--output-format") + 1] == "stream-json" and "--strict-mcp-config" in a
    assert a[a.index("--tools") + 1] == "" and a[a.index("--permission-mode") + 1] == "dontAsk"               # no built-in tools, nothing asked
    assert a[a.index("--allowedTools") + 1] == "mcp__vmd-agent" and a[a.index("--model") + 1] == "sonnet" and "--resume" not in a
    s.ask("and the ligand?")
    second = _calls(claude["log"])[1]["args"]
    assert second[second.index("--resume") + 1] == "sess-1"                                         # the same conversation
    s.reset()
    s.ask("new question")
    assert "--resume" not in _calls(claude["log"])[2]["args"]


@pytest.mark.skipif(os.name == "nt", reason="the stand-in is a shell-less script")
def test_the_tools_given_to_claude_code_are_sandboxed_to_the_files_folder(claude):
    cfg = C.mcp_config(claude["data"])["mcpServers"]["vmd-agent"]
    assert cfg["env"]["VMD_AGENT_ALLOWED_ROOTS"] == os.path.realpath(claude["data"])
    assert os.path.isabs(cfg["command"])


@pytest.mark.skipif(os.name == "nt", reason="the stand-in is a shell-less script")
def test_not_signed_in_says_how_to_sign_in(claude, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "login")
    with pytest.raises(LLMError, match="not signed in"):
        C.Session(root=claude["data"]).ask("hi")


@pytest.mark.skipif(os.name == "nt", reason="the stand-in is a shell-less script")
def test_a_crash_says_what_claude_code_printed(claude, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "crash")
    with pytest.raises(LLMError, match="boom"):
        C.Session(root=claude["data"]).ask("hi")


def test_no_claude_code_says_how_to_install_it(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "find", lambda: None)
    i = C.info("default")
    assert i["state"] == "no_server" and "claude.com/claude-code" in i["problem"]
    with pytest.raises(LLMError, match="cannot find Claude Code"):
        C.Session(root=str(tmp_path)).ask("hi")


def test_the_choice_is_recognised_however_it_is_written():
    assert C.is_claude_code("claude-code:") and C.is_claude_code("Claude-Code:/") and not C.is_claude_code("http://localhost:11434/v1")


@pytest.mark.skipif(os.name == "nt", reason="the stand-in is a shell-less script")
def test_the_page_uses_claude_code_when_it_is_chosen(claude, monkeypatch):
    from vmd_agent import ui, settings
    monkeypatch.setattr(settings, "save", lambda **k: None)
    srv = ui.make_server(claude["data"], 0, base_url="http://127.0.0.1:9/v1", model="x")
    st = srv.state
    st.reconnect(C.URL, "claude-opus-5-5", None)
    assert isinstance(st.session, C.Session) and st.session.model == "claude-opus-5-5"
    info = st.model_info()
    assert info["backend"] == "claude-code" and info["state"] == "ready" and info["claude_version"].startswith("9.9.9")
    assert st.status()["model"] == "Claude Code (Claude Opus 5.5)"
    srv.server_close()


@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code is not installed here")
def test_a_real_claude_code_connects_to_the_tools_and_has_none_of_its_own(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps(C.mcp_config(str(tmp_path))))
    _fresh_search()
    r = subprocess.run(C.command(C.find(refresh=True), str(cfg), C.DEFAULT, None, "test"), input="hi", capture_output=True, text=True, cwd=tmp_path, timeout=240)
    init = json.loads(r.stdout.splitlines()[0])
    assert {"name": "vmd-agent", "status": "connected"}.items() <= next(s for s in init["mcp_servers"] if s["name"] == "vmd-agent").items()
    assert [t for t in init["tools"] if not t.startswith("mcp__")] == []
    assert sum(t.startswith("mcp__vmd-agent__") for t in init["tools"]) >= 50


# ------------------------------------------------------------------ finding Claude Code
def _program(path, says="9.9.9 (Claude Code)"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(f"#!/bin/sh\necho '{says}'\n")
    os.chmod(path, 0o755)
    return path


@pytest.fixture
def nowhere(tmp_path, monkeypatch):
    """A home folder with no Claude Code, a PATH with none, and a login shell that knows none."""
    from vmd_agent import settings
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("SHELL", _program(str(tmp_path / "sh" / "fakeshell"), says=""))
    monkeypatch.delenv(C.ENV_PATH, raising=False)
    saved = {}
    monkeypatch.setattr(settings, "get", lambda k, d=None: saved.get(k, d))
    monkeypatch.setattr(settings, "save", lambda **k: saved.update({a: b for a, b in k.items() if b is not None}))
    monkeypatch.setattr(C, "_candidates", lambda real=C._candidates: [p for p in real() if p.startswith(str(home))])  # not this machine's own
    _fresh_search()
    yield {"home": str(home), "settings": saved}
    _fresh_search()


@pytest.mark.skipif(os.name == "nt", reason="shell scripts stand in for programs")
def test_claude_code_installed_with_npm_under_nvm_or_conda_is_found(nowhere):
    for where in (".nvm/versions/node/v22.3.0/bin/claude", "miniconda3/envs/tools/bin/claude"):
        exe = _program(os.path.join(nowhere["home"], where))
        _fresh_search()
        assert C.find() == exe and C.info(C.DEFAULT)["state"] == "ready" and C.info(C.DEFAULT)["claude_version"] == "9.9.9"
        os.remove(exe)
        assert C.find() != exe                                                                  # gone: not remembered


@pytest.mark.skipif(os.name == "nt", reason="shell scripts stand in for programs")
def test_the_claude_desktop_apps_own_copy_is_found(nowhere):
    exe = _program(os.path.join(nowhere["home"], "Library", "Application Support", "Claude", "claude-code", "2.1.0", "claude"))
    _program(os.path.join(nowhere["home"], "Library", "Application Support", "Claude", "Claude"), says="not it")   # the app, not Claude Code
    assert C.find() == exe


@pytest.mark.skipif(os.name == "nt", reason="shell scripts stand in for programs")
def test_a_program_called_claude_that_is_not_claude_code_is_never_used(nowhere):
    _program(os.path.join(nowhere["home"], ".local", "bin", "claude"), says="Claude desktop 1.0")
    assert C.find() is None
    i = C.info(C.DEFAULT)
    assert i["state"] == "no_server" and "which claude" in i["problem"] and any(".local/bin/claude" in p for p in i["claude_searched"])


@pytest.mark.skipif(os.name == "nt", reason="shell scripts stand in for programs")
def test_the_terminals_own_path_is_asked(nowhere, tmp_path, monkeypatch):
    exe = _program(str(tmp_path / "odd place" / "claude"))
    monkeypatch.setenv("SHELL", _program(str(tmp_path / "sh2" / "zsh"), says=f"welcome banner\n{exe}"))
    assert C.find() == exe


@pytest.mark.skipif(os.name == "nt", reason="shell scripts stand in for programs")
def test_a_location_typed_in_the_model_window_is_used_and_a_wrong_one_is_named(nowhere, tmp_path):
    from vmd_agent import settings
    exe = _program(str(tmp_path / "mine" / "claude"))
    settings.save(claude_path=exe)
    _fresh_search()
    assert C.find() == exe and C.info(C.DEFAULT)["state"] == "ready"
    wrong = _program(str(tmp_path / "wrong" / "claude"), says="hello")
    settings.save(claude_path=wrong)
    _fresh_search()
    i = C.info(C.DEFAULT)
    assert i["state"] == "no_server" and "is not Claude Code" in i["problem"]


def test_the_models_are_offered_with_their_versions():
    ids = [m["id"] for m in C.MODELS]
    assert ids[0] == C.DEFAULT and {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"} <= set(ids)
    assert all(any(ch.isdigit() for ch in m["label"]) for m in C.MODELS[1:])                       # "Claude Opus 5.5", not "Opus"
    assert C.command("/x/claude", "/c.json", "claude-opus-5-5", None, "s")[-2:] == ["--model", "claude-opus-5-5"]
