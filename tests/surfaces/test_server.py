"""The MCP server, exercised through the **real MCP SDK** (no stub).

Every tool is called the way a client would call it: through the SDK's own
``list_tools`` / ``call_tool``. Both SDK generations are supported (mcp 1.x
``FastMCP`` and mcp 2.x ``MCPServer``); run this file under each to check both.
Needs Python >= 3.10 and ``pip install mcp``; skipped, with the reason shown,
otherwise.
"""
import asyncio
import json
import os

import pytest

pytestmark = pytest.mark.requires_mcp


@pytest.fixture(scope="module")
def server():
    pytest.importorskip("mcp")
    from vmd_agent import server as s
    return s


def _content(res):
    """The content blocks of a ``call_tool`` result, in either SDK generation."""
    if isinstance(res, tuple):                       # (content, structured)
        res = res[0]
    return list(getattr(res, "content", res))


def call(server, name, **args):
    """Call a tool through the SDK; return the decoded dict, or the raw block
    for non-JSON results (images)."""
    res = asyncio.run(server.mcp.call_tool(name, args))
    blocks = _content(res)
    texts = [b.text for b in blocks if getattr(b, "type", None) == "text"]
    if texts:
        try:
            return json.loads(texts[0])
        except ValueError:
            return texts[0]
    return blocks[0]


def tool_names(server):
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


def test_all_tools_are_registered_with_the_sdk(server):
    from vmd_agent import toolset
    assert tool_names(server) == set(toolset.TOOLS) and len(toolset.TOOLS) == 56
    assert set(toolset.library_tools()) <= tool_names(server) and "run_workflow" in tool_names(server)


def test_tools_have_agent_facing_descriptions_and_schemas(server):
    for t in asyncio.run(server.mcp.list_tools()):
        assert t.description and len(t.description) > 30, t.name
        schema = getattr(t, "inputSchema", None) or t.input_schema   # 1.x / 2.x
        assert schema["type"] == "object", t.name


def test_a_plain_tool_call_returns_real_results(server):
    r = call(server, "list_representations")
    assert any("NewCartoon" in json.dumps(v) for v in
               (r if isinstance(r, list) else [r]))
    d = call(server, "detect_system", topology=os.path.join(
        os.path.dirname(__file__), "..", "data", "1ubq.pdb"))
    assert d["components"]["protein"]["n_residues"] == 76


def test_security_error_becomes_structured_result(server, tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(root))
    r = call(server, "detect_system", topology="/etc/passwd")
    assert r["blocked"] and not r["ok"] and "allowed roots" in r["error"]


def test_run_vmd_tcl_is_disabled_by_default(server, monkeypatch):
    """Obfuscated Tcl (names built at run time) defeats any deny-list; verified
    with a real tclsh. The tool must not run anything unless explicitly enabled."""
    from vmd_agent.visual import render
    started = []
    real = render._run_vmd_text      # counts launches; still the real function

    def counting(*a, **k):
        started.append(a)
        return real(*a, **k)
    monkeypatch.setattr(render, "_run_vmd_text", counting)
    for script in ("puts hi", "exec ls",
                   "set c ex\nappend c ec\n$c touch /tmp/x"):
        r = call(server, "run_tcl", script=script)
        assert r["blocked"] and not r["ok"] and "disabled" in r["error"]
    assert started == []                                    # VMD never launched


def test_enabled_tcl_tool_still_screens_obvious_commands(server, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ENABLE_TCL", "1")
    assert call(server, "run_tcl", script="exec ls")["blocked"]


@pytest.mark.requires_vmd
def test_enabled_tcl_tool_runs_a_safe_script_in_real_vmd(server, real_vmd,
                                                         monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ENABLE_TCL", "1")
    r = call(server, "run_tcl", script="puts mcp_says_hi", vmd_path=real_vmd)
    assert r["ok"] and "mcp_says_hi" in r["stdout"]


def test_view_image_only_serves_images(server, tmp_path):
    f = tmp_path / "secret.txt"
    f.write_text("x")
    with pytest.raises(Exception, match="image"):
        call(server, "view_image", path=str(f))
    from PIL import Image
    png = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(png)
    block = call(server, "view_image", path=str(png))
    assert getattr(block, "type", None) == "image" and block.data


def test_view_image_respects_sandbox(server, tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path / "data"))
    with pytest.raises(Exception):
        call(server, "view_image", path=str(tmp_path / "x.png"))


def test_verify_claims_tool_stores_in_session(server, lyz, tmp_path):
    r = call(server, "verify_claims", topology=lyz,
             claims=["It has one chain"], session_dir=str(tmp_path))
    assert r["counts"]["supported"] == 1
    stored = json.load(open(tmp_path / "session.json"))
    assert stored["claims"]["n_claims"] == 1


def test_visualize_tool_records_renderer_and_provenance(server, ubq, tmp_path):
    out = call(server, "visualize_and_interpret", topology=ubq,
               out_dir=str(tmp_path / "o"), views=["front"],
               session_dir=str(tmp_path / "s"), renderer="matplotlib")
    assert out["ok"]
    st = json.load(open(tmp_path / "s" / "session.json"))
    assert st["renderer"]["used"] == "matplotlib" and st["provenance"]


def test_assemble_report_tool(server, tmp_path):
    call(server, "record_visual_interpretation", session_dir=str(tmp_path),
         text="folded")
    r = call(server, "assemble_report", session_dir=str(tmp_path))
    assert r["written_to"].endswith("report.md")


def test_invalid_input_becomes_a_structured_result(server, ubq, tmp_path):
    r = call(server, "visualize_and_interpret", topology=ubq,
             out_dir=str(tmp_path),
             representation="Lines} ; exec touch /tmp/x ; {",
             renderer="matplotlib")
    assert r["ok"] is False and r["stage"] == "recipe"


def test_tool_wrapper_converts_both_policy_exception_types(server):
    """The pipeline catches bad representations itself, so the wrapper's own
    InvalidInput branch needs a direct test (found by mutation testing). Tested
    through the real SDK registry, then unregistered so the tool set is unchanged."""
    from vmd_agent.security import InvalidInput, SecurityError

    @server.tool()
    def raises_invalid():
        raise InvalidInput("bad value")

    @server.tool()
    def raises_blocked():
        raise SecurityError("not allowed")

    try:
        assert call(server, "raises_invalid") == {
            "ok": False, "blocked": False, "error": "bad value"}
        assert call(server, "raises_blocked") == {
            "ok": False, "blocked": True, "error": "not allowed"}
    finally:
        for name in ("raises_invalid", "raises_blocked"):
            try:
                server.mcp.remove_tool(name)
            except Exception:                      # SDKs differ; best effort
                pass
