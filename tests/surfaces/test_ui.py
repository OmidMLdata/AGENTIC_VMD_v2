"""`vmd-agent ui`: the real server on a real port, spoken to over real HTTP. The model is a local server with the chat API's wire
format (as in test_timing.py); the tools are the real tools."""
import http.client
import json
import os
import shutil
import threading
import time

import pytest

from vmd_agent import ui
from conftest import scripted_server as _server

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


@pytest.fixture()
def page(tmp_path, monkeypatch):
    monkeypatch.delenv("VMD_AGENT_ENABLE_TCL", raising=False)
    shutil.copy(os.path.join(DATA, "1ubq.pdb"), tmp_path / "1ubq.pdb")
    call = {"content": None, "tool_calls": [{"id": "c1", "type": "function",
                                              "function": {"name": "detect_system", "arguments": json.dumps({"topology": "1ubq.pdb"})}}]}
    model, url, calls = _server([call, {"content": "It is ubiquitin."}])
    old = os.getcwd(), os.environ.get("VMD_AGENT_ALLOWED_ROOTS")
    srv = ui.make_server(str(tmp_path), 0, url, "m")
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    class Page:
        port = srv.server_address[1]
        key = srv.state.token
        state = srv.state
        root = str(tmp_path)

        def req(self, method, path, body=None, headers=None, cookie=True, host=None):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
            h = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
            if cookie:
                h["Cookie"] = f"vmd_ui={self.key}"
            c.request(method, path, body=body, headers=h)
            r = c.getresponse()
            return r.status, r.read(), dict(r.getheaders())

        def post(self, path, obj, **kw):
            return self.req("POST", path, json.dumps(obj), {"Content-Type": "application/json"}, **kw)

        def events(self, path, obj):
            status, body, _ = self.post(path, obj)
            assert status == 200, body
            return [json.loads(line[6:]) for line in body.decode().split("\n\n") if line.startswith("data: ")]
    yield Page()
    srv.shutdown()
    srv.server_close()
    model.shutdown()
    os.chdir(old[0])
    if old[1] is None:
        os.environ.pop("VMD_AGENT_ALLOWED_ROOTS", None)
    else:
        os.environ["VMD_AGENT_ALLOWED_ROOTS"] = old[1]


def test_the_page_needs_the_key_and_the_right_host(page):
    assert page.req("GET", "/", cookie=False)[0] == 403
    assert page.req("GET", "/", host="evil.example:80")[0] == 403                      # another name for this computer (DNS rebinding)
    assert page.req("GET", "/", headers={"Origin": "http://evil.example"})[0] == 403
    status, _, headers = page.req("GET", f"/?k={page.key}", cookie=False)                # the printed address sets the cookie
    assert status == 302 and "vmd_ui=" in headers["Set-Cookie"] and "HttpOnly" in headers["Set-Cookie"]
    assert page.req("GET", "/?k=wrong", cookie=False)[0] == 403
    status, body, _ = page.req("GET", "/")
    assert status == 200 and b"vmd-agent" in body
    assert page.post("/api/reset", {}, cookie=False)[0] == 403
    assert page.state.root == os.path.realpath(page.root) and page.state.token not in body.decode()


def test_status_files_and_workflows(page):
    status = json.loads(page.req("GET", "/api/status")[1])
    assert status["model"] == "m" and status["n_tools"] == 57 and status["data_dir"] == os.path.realpath(page.root)
    assert status["model_ready"] in (True, False) and "ffmpeg" in status
    files = json.loads(page.req("GET", "/api/files")[1])["files"]
    assert [f["path"] for f in files] == ["1ubq.pdb"] and files[0]["kind"] == "structure"
    os.makedirs(os.path.join(page.root, "out", "deep"))
    open(os.path.join(page.root, "out", "deep", "a.png"), "wb").write(b"x")
    open(os.path.join(page.root, ".hidden"), "w").write("x")
    top = json.loads(page.req("GET", "/api/files")[1])
    assert [f["path"] for f in top["files"]] == ["1ubq.pdb"] and top["folders"] == [{**top["folders"][0], "path": "out", "n_files": 1}]
    assert {f["path"] for f in top["everything"]} == {"1ubq.pdb", "out/deep/a.png"}              # no hidden files
    inner = json.loads(page.req("GET", "/api/files?dir=out")[1])
    assert inner["files"] == [] and [d["path"] for d in inner["folders"]] == ["out/deep"]
    assert page.req("GET", "/api/files?dir=..%2F..")[0] == 404
    wf = json.loads(page.req("GET", "/api/workflows")[1])["workflows"]
    assert "equilibration_check" in wf


def test_files_are_served_only_from_inside_the_folder(page):
    status, body, headers = page.req("GET", "/files/1ubq.pdb")
    assert status == 200 and body.startswith(b"HEADER") or b"ATOM" in body
    assert page.req("GET", "/files/..%2F..%2F..%2Fetc%2Fpasswd")[0] in (403, 404)
    assert page.req("GET", "/files/%2Fetc%2Fpasswd")[0] in (403, 404)
    assert page.req("GET", "/files/missing.pdb")[0] == 404


def test_uploading_never_overwrites_and_refuses_odd_names(page):
    s, body, _ = page.req("POST", "/api/upload?name=1ubq.pdb", b"first")
    assert s == 200 and json.loads(body)["path"] == "1ubq_1.pdb"
    assert open(os.path.join(page.root, "1ubq.pdb"), "rb").read() != b"first"          # the original is untouched
    assert page.req("POST", "/api/upload?name=..%2Fx.pdb", b"x")[0] in (200, 400)
    assert not os.path.exists(os.path.join(os.path.dirname(page.root), "x.pdb"))
    assert page.req("POST", "/api/upload?name=%3Bbad%24%28name%29", b"x")[0] == 400


def test_a_file_can_be_looked_at_with_a_few_read_only_tools(page):
    s, body, _ = page.post("/api/look", {"tool": "detect_system", "path": "1ubq.pdb"})
    r = json.loads(body)
    assert s == 200 and r["result"]["components"]["protein"]["n_residues"] == 76 and r["seconds"] >= 0
    assert page.post("/api/look", {"tool": "run_tcl", "path": "x"})[0] == 400          # only the listed looks
    s, body, _ = page.post("/api/look", {"tool": "inspect_files", "path": "../../etc/hosts"})
    assert "error" in json.dumps(json.loads(body)["result"]).lower()                       # the sandbox applies


def test_a_chat_streams_the_model_call_the_tool_call_and_where_the_time_went(page):
    events = page.events("/api/chat", {"message": "what is in 1ubq.pdb?"})
    kinds = [e["type"] for e in events]
    assert kinds.index("model_start") < kinds.index("tool_start") < kinds.index("tool_end") < kinds.index("answer")
    start = next(e for e in events if e["type"] == "tool_start")
    end = next(e for e in events if e["type"] == "tool_end")
    answer = next(e for e in events if e["type"] == "answer")
    assert start["name"] == end["name"] == "detect_system" and end["seconds"] >= 0 and end["error"] is None
    assert answer["text"] == "It is ubiquitin." and "took" in answer["line"] and answer["clock"]["model_calls"] == 2
    assert sum(e["type"] == "model_end" for e in events) == 2
    status = json.loads(page.req("GET", "/api/status")[1])
    assert status["clock"]["model_calls"] == 2                                              # the session keeps totals
    assert page.post("/api/reset", {})[0] == 200


def test_one_job_at_a_time(page):
    assert page.state.busy.acquire(blocking=False)
    try:
        s, body, _ = page.post("/api/chat", {"message": "hi"})
        assert s == 409 and "still running" in json.loads(body)["error"]
    finally:
        page.state.busy.release()


def test_a_workflow_runs_with_progress_and_ends_with_a_report(page):
    events = page.events("/api/workflow", {"name": "structure_overview", "files": ["1ubq.pdb"]})
    done = next(e for e in events if e["type"] == "workflow")
    assert done["result"]["ok"] and done["seconds"] >= 0 and done["report_html"].endswith("report.html")
    status, body, headers = page.req("GET", "/files/" + done["report_html"])
    assert status == 200 and b"<title>" in body.lower() and "script-src" not in headers.get("Content-Security-Policy", "")
    assert "default-src 'none'" in headers["Content-Security-Policy"]                       # a report cannot run scripts
    bad = page.events("/api/workflow", {"name": "equilibration_check", "files": ["1ubq.pdb"]})
    assert "needs 2 file" in json.dumps(next(e for e in bad if e["type"] == "workflow")["result"])


def test_kinds_and_images_found_in_results(tmp_path):
    assert ui.kind_of("a.DCD") == "trajectory" and ui.kind_of("x.mrc") == "map" and ui.kind_of("zzz") == "other"
    from vmd_agent import security
    os.environ[security.ENV_ROOTS] = str(tmp_path)
    try:
        (tmp_path / "a.png").write_bytes(b"x")
        found = ui.images_in({"image": str(tmp_path / "a.png"), "other": ["/etc/hosts.png", {"deep": str(tmp_path / "a.png")}]}, str(tmp_path))
        assert found == ["a.png"]
    finally:
        os.environ.pop(security.ENV_ROOTS, None)


def test_the_command_prints_an_address_with_the_key(tmp_path, monkeypatch):
    from vmd_agent import cli
    said = []
    monkeypatch.setattr(ui, "main", lambda *a, **k: said.append(a) or 0)
    assert cli.main(["ui", "--data-dir", str(tmp_path), "--no-browser", "--port", "0"]) == 0
    assert said[0][0] == str(tmp_path) and said[0][2] is False
    time.sleep(0)


def test_the_page_is_served_as_files_with_a_strict_policy_and_no_inline_script(page):
    status, body, headers = page.req("GET", "/")
    html = body.decode()
    assert status == 200 and "<script>" not in html and 'onclick=' not in html and ' style="' not in html
    assert headers["Content-Security-Policy"].startswith("default-src 'self'") and "unsafe-inline" not in headers["Content-Security-Policy"]
    for name, ctype in (("style.css", "text/css"), ("app.js", "text/javascript"), ("commands.js", "text/javascript"), ("markdown.js", "text/javascript")):
        s, b, h = page.req("GET", "/assets/" + name)
        assert s == 200 and h["Content-Type"].startswith(ctype) and len(b) > 500
        assert page.req("GET", "/assets/" + name, cookie=False)[0] == 403
    assert page.req("GET", "/assets/index.html")[0] == 404 and page.req("GET", "/assets/..%2Fui.py")[0] == 404


def test_the_tools_the_chat_offers_can_be_changed_from_the_page(page):
    s, body, _ = page.post("/api/profile", {"tools": "auto"})
    status = json.loads(body)
    assert s == 200 and status["profile"] == "auto" and status["profiles"]["all"] == 58
    assert page.post("/api/profile", {"tools": "nonsense"})[0] == 400
    assert json.loads(page.post("/api/profile", {"tools": "all"})[1])["tools_in_chat"] == 58


def _closed_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_page_says_why_the_model_is_not_answering_and_the_chat_fails_gracefully(page):
    dead = f"http://127.0.0.1:{_closed_port()}/v1"
    s, body, _ = page.post("/api/model/use", {"base_url": dead, "model": "m"})
    info = json.loads(body)
    assert s == 200 and info["state"] == "no_server" and info["problem"]
    status = json.loads(page.req("GET", "/api/status")[1])
    assert status["model_ready"] is False and status["model_state"] == "no_server" and status["model_problem"]
    events = page.events("/api/chat", {"message": "what is in 1ubq.pdb?"})
    assert [e["type"] for e in events] == ["error"] and events[0]["kind"] == "model" and "No model is answering" in events[0]["text"]
    assert "Model" in events[0]["text"] and "work without one" in events[0]["text"]                      # the way out, and what still works
    assert page.post("/api/look", {"tool": "inspect_files", "path": "1ubq.pdb"})[0] == 200               # the rest of the page does not depend on a model


def test_a_server_without_the_model_is_told_apart_from_no_server(page):
    s, body, _ = page.post("/api/model/use", {"base_url": page.state.base_url, "model": "not-installed"})
    info = json.loads(body)
    assert s == 200 and info["state"] == "no_model" and "m" in info["available"] and "not-installed" in info["problem"]


def test_the_model_can_be_chosen_from_the_page_and_remembered(page):
    from vmd_agent import settings
    s, body, _ = page.post("/api/model/use", {"base_url": page.state.base_url, "model": "m", "api_key": "sk-secret", "remember": True})
    info = json.loads(body)
    assert s == 200 and info["state"] == "ready" and info["has_key"] is True and "sk-secret" not in body.decode()           # the key is never sent back
    assert settings.get("llm_model") == "m" and settings.get("llm_key") == "sk-secret"
    events = page.events("/api/chat", {"message": "what is in 1ubq.pdb?"})
    assert events[-1]["type"] == "answer"                                                    # the new connection really answers
    assert page.post("/api/model/use", {"base_url": "ftp://x", "model": "m"})[0] == 400      # only http(s)
    assert page.post("/api/model/use", {"base_url": page.state.base_url, "model": ""})[0] == 400
    assert page.req("GET", "/api/model", cookie=False)[0] == 403


def test_starting_the_private_model_server_says_so_when_there_is_none(page, monkeypatch):
    from vmd_agent import ollama_local
    monkeypatch.setattr(ollama_local, "find_binary", lambda root=None: None)
    s, body, _ = page.post("/api/model/start", {})
    assert s == 409 and "vmd-agent setup" in json.loads(body)["error"]


def test_every_tool_is_described_for_a_form_and_can_be_run_from_it(page):
    from vmd_agent import toolset
    cat = json.loads(page.req("GET", "/api/tools")[1])
    names = [t["name"] for g in cat["groups"] for t in g["tools"]]
    assert names == toolset.library_tools() and len(cat["groups"]) == 11
    detect = next(t for g in cat["groups"] for t in g["tools"] if t["name"] == "detect_system")
    topo = next(p for p in detect["params"] if p["name"] == "topology")
    assert topo["required"] and topo["role"] == "structure" and topo["kind"] == "string" and all(p["name"] != "vmd_path" for p in detect["params"])
    meas = next(t for g in cat["groups"] for t in g["tools"] if t["name"] == "measure_with_vmd")
    assert "rgyr" in next(p for p in meas["params"] if p["name"] == "kind")["enum"]                   # a drop-down, from the tool's own choices
    events = page.events("/api/tool", {"name": "detect_system", "args": {"topology": "1ubq.pdb", "trajectory": ""}})
    done = next(e for e in events if e["type"] == "tool_result")
    assert done["result"]["n_atoms"] > 100 and done["command"] == "vmd-agent tool detect_system 1ubq.pdb" and "1ubq.pdb" in done["files"]
    bad = page.events("/api/tool", {"name": "detect_system", "args": {}})
    assert bad[-1]["type"] == "error" and "topology" in bad[-1]["text"]
    assert page.events("/api/tool", {"name": "no_such_tool", "args": {}})[-1]["type"] == "error"
    assert page.post("/api/tool", {"name": "detect_system", "args": {}}, cookie=False)[0] == 403


def test_the_command_for_a_form_is_the_command_the_command_line_would_parse():
    from vmd_agent import cli, toolform
    p, _ = cli.build_parser()
    cmd = toolform.command_for("measure_with_vmd", {"topology": "a.pdb", "trajectory": "a.dcd", "kind": "rmsd", "align": False, "step": 5})
    a = p.parse_args(cmd.split()[1:])
    assert (a.topology, a.trajectory, a.kind, a.align, a.step) == ("a.pdb", "a.dcd", "rmsd", False, 5)


def test_the_page_terminal_runs_the_real_command_line(page):
    s, body, _ = page.post("/api/terminal", {"line": "vmd-agent tool detect_system 1ubq.pdb"})
    out = json.loads(body)
    assert s == 200 and out["ok"] and '"n_atoms"' in out["output"]
    listing = json.loads(page.post("/api/terminal", {"line": "tools"})[1])["output"]
    assert "Draw" in listing and "measure_with_vmd" in listing
    assert "usage" in json.loads(page.post("/api/terminal", {"line": "tool detect_system --help"})[1])["output"]
    bad = json.loads(page.post("/api/terminal", {"line": "tool detect_system"})[1])
    assert bad["ok"] is False and ("required" in bad["output"] or "arguments" in bad["output"])
    assert json.loads(page.post("/api/terminal", {"line": "rm -rf /"})[1])["ok"] is False
    assert page.post("/api/terminal", {"line": "tools"}, cookie=False)[0] == 403


def test_local_models_on_disk_are_listed_even_when_no_server_runs(tmp_path):
    from vmd_agent import ollama_local
    for ref in ("registry.ollama.ai/library/granite4.1/8b", "registry.ollama.ai/library/gemma4/e4b", "registry.ollama.ai/someone/custom/latest"):
        d = tmp_path / "manifests" / os.path.dirname(ref)
        d.mkdir(parents=True, exist_ok=True)
        (tmp_path / "manifests" / ref).write_text("{}")
    assert ollama_local.installed_models(str(tmp_path)) == ["gemma4:e4b", "granite4.1:8b", "someone/custom:latest"]
    assert ollama_local.installed_models(str(tmp_path / "nothing")) == []


@pytest.fixture()
def vmd_window(page):
    """A VMD with no window under the page (the commands are the same as for a window, so a test opens none)."""
    from vmd_agent import vmdlink
    vmdlink.open_window(headless=True)
    yield
    vmdlink.stop()


def test_the_page_says_so_when_no_vmd_window_is_open_and_refuses_anything_but_window_tools(page, monkeypatch):
    from vmd_agent import vmdlink
    state = json.loads(page.req("GET", "/api/window")[1])
    assert state["connected"] is False and "NewCartoon" in state["choices"]["styles"] and "black" in state["choices"]["backgrounds"]
    r = json.loads(page.post("/api/window", {"tool": "window_molecules", "args": {}})[1])
    assert r["ok"] is False and "window_open" in r["error"]
    assert page.post("/api/window", {"tool": "detect_system", "args": {"topology": "1ubq.pdb"}})[0] == 400          # the page cannot use this door for other tools
    assert page.post("/api/window", {"tool": "window_molecules", "args": {}}, cookie=False)[0] == 403
    assert page.req("GET", "/api/window/snapshot", cookie=False)[0] == 403
    monkeypatch.setattr(vmdlink, "open_window", lambda *a, **k: (_ for _ in ()).throw(vmdlink.LinkError("VMD was not found")))
    s, body, _ = page.post("/api/window/open", {})
    assert s == 409 and "VMD was not found" in json.loads(body)["error"]


@pytest.mark.requires_vmd
def test_the_page_drives_a_vmd_and_shows_vmds_own_picture(page, vmd_window):
    load = json.loads(page.post("/api/window", {"tool": "window_load", "args": {"topology": "1ubq.pdb"}})[1])
    assert load["ok"] and load["loaded"]["natoms"] > 100
    rep = json.loads(page.post("/api/window", {"tool": "window_representation", "args": {"action": "only", "selection": "protein", "style": "NewCartoon", "color": "Structure"}})[1])
    assert rep["ok"] and rep["representations"][0]["style"] == "NewCartoon"
    bad = json.loads(page.post("/api/window", {"tool": "window_representation", "args": {"action": "modify", "rep": 0, "selection": "name CAA and ("}})[1])
    assert bad["ok"] is False and "selection" in bad["error"]                                                      # VMD's own parser is the judge
    state = json.loads(page.req("GET", "/api/window")[1])
    assert state["connected"] and state["molecules"][0]["reps"][0]["selection"] == "protein" and state["display"]["background"] == "black"
    s, body, headers = page.req("GET", "/api/window/snapshot?q=tachyon")
    assert s == 200 and headers["Content-Type"] == "image/png" and body[:8] == b"\x89PNG\r\n\x1a\n" and len(body) > 2000
    assert json.loads(page.req("GET", "/api/status")[1])["window"]["connected"] is True
    events = page.events("/api/tool", {"name": "window_query", "args": {"selection": "protein"}})
    assert 0 < next(e for e in events if e["type"] == "tool_result")["result"]["natoms"] <= state["molecules"][0]["natoms"]
