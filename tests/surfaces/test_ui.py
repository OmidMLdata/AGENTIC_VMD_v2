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
    assert status["model"] == "m" and status["n_tools"] == 44 and status["data_dir"] == os.path.realpath(page.root)
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
    for name, ctype in (("style.css", "text/css"), ("app.js", "text/javascript"), ("viewer.js", "text/javascript"), ("selection.js", "text/javascript"),
                        ("commands.js", "text/javascript"), ("markdown.js", "text/javascript")):
        s, b, h = page.req("GET", "/assets/" + name)
        assert s == 200 and h["Content-Type"].startswith(ctype) and len(b) > 500
        assert page.req("GET", "/assets/" + name, cookie=False)[0] == 403
    assert page.req("GET", "/assets/index.html")[0] == 404 and page.req("GET", "/assets/..%2Fui.py")[0] == 404


def test_the_viewer_gets_atoms_bonds_and_other_frames(page):
    shutil.copy(os.path.join(DATA, "ubq_md", "protein.pdb"), os.path.join(page.root, "md.pdb"))
    shutil.copy(os.path.join(DATA, "ubq_md", "protein.dcd"), os.path.join(page.root, "md.dcd"))
    s, body, _ = page.req("GET", "/api/structure?path=md.pdb&traj=md.dcd")
    mol = json.loads(body)
    assert s == 200 and mol["frames"] > 1 and len(mol["xyz"]) == 3 * mol["n_atoms"] and len(mol["bonds"]) > mol["n_atoms"] * 0.8
    assert not mol["reduced"] and len(mol["element"]) == mol["n_atoms"] and mol["radius"] > 5
    f0 = json.loads(page.req("GET", "/api/frame?path=md.pdb&traj=md.dcd&i=0")[1])["xyz"]
    f3 = json.loads(page.req("GET", "/api/frame?path=md.pdb&traj=md.dcd&i=3")[1])["xyz"]
    assert len(f0) == len(f3) == len(mol["xyz"]) and f0 != f3                              # the same atoms, moved
    assert page.req("GET", "/api/structure?path=..%2F..%2Fetc%2Fpasswd")[0] == 404
    assert page.req("GET", "/api/structure?path=missing.pdb")[0] == 404
    open(os.path.join(page.root, "notes.pdb"), "w").write("this is not a structure\n")
    s, body, _ = page.req("GET", "/api/structure?path=notes.pdb")
    assert s == 415 and "cannot show" in json.loads(body)["error"]
    assert page.req("GET", "/api/structure", cookie=False)[0] == 403


def test_the_tools_the_chat_offers_can_be_changed_from_the_page(page):
    s, body, _ = page.post("/api/profile", {"tools": "auto"})
    status = json.loads(body)
    assert s == 200 and status["profile"] == "auto" and status["profiles"]["all"] == 45
    assert page.post("/api/profile", {"tools": "nonsense"})[0] == 400
    assert json.loads(page.post("/api/profile", {"tools": "all"})[1])["tools_in_chat"] == 45
