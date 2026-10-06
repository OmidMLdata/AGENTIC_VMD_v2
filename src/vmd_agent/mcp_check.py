"""Check an MCP server installation the way a real client would use it.

``vmd-agent mcp-check`` launches the server as a subprocess, speaks to it with the
MCP SDK's own **client** over stdio, and reports what works. That is the same path
Claude Code, Claude Desktop or any other MCP client takes, so a pass here means a
client can connect, and a fail names the missing piece.

Like the SDK's own client (and clients such as Claude Desktop) it passes the server
**only the environment you give it** (plus the SDK's safe defaults such as ``PATH``
and ``HOME``), not your whole shell environment. A variable that works in your
terminal but is missing from the client's configuration (``VMD_BIN`` above all)
therefore shows up here.

Each check is ``{"name", "status", "detail"}`` with status ``ok``, ``warn``,
``fail`` or ``skip``. A ``fail`` means a client would not work; a ``warn`` means
it works with reduced capability or a risk (for example no sandbox).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from typing import Dict, List, Optional, Sequence

_PDB = """\
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00           C
ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.00           C
ATOM      4  O   ALA A   1       1.251   2.390   0.000  1.00  0.00           O
ATOM      5  CB  ALA A   1       1.986  -0.760  -1.216  1.00  0.00           C
END
"""


def _c(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _decode(result) -> object:
    content = result[0] if isinstance(result, tuple) else result
    blocks = list(getattr(content, "content", content))
    texts = [b.text for b in blocks if getattr(b, "type", None) == "text"]
    if not texts:
        return {}
    try:
        return json.loads(texts[0])
    except ValueError:
        return texts[0]


async def _check(command: str, args: Sequence[str], env: Dict[str, str],
                 render: bool, timeout: float) -> List[dict]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    out: List[dict] = []
    params = StdioServerParameters(command=command, args=list(args), env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await asyncio.wait_for(s.initialize(), timeout)
            out.append(_c("connect", "ok",
                          f"server started: {command} {' '.join(args)}"))

            async def call(name, arguments=None):
                res = await asyncio.wait_for(
                    s.call_tool(name, arguments or {}), timeout)
                return _decode(res)

            names = {t.name for t in (await s.list_tools()).tools}
            try:
                from vmd_agent import server as local
                expected = {t.name for t in await local.mcp.list_tools()}
            except BaseException:                     # SystemExit when no SDK
                expected = set()
            missing = sorted(expected - names)
            out.append(_c("tools", "fail" if missing else "ok",
                          f"{len(names)} tools" + (
                              f"; missing {missing}" if missing else "")))

            p = await call("probe_environment")
            libs = p.get("analysis_libs", {})
            out.append(_c("analysis_libraries",
                          "ok" if libs.get("MDAnalysis") else "fail",
                          "MDAnalysis " + ("importable" if libs.get("MDAnalysis")
                                           else "MISSING in the server's Python")))
            vmd = bool(p.get("vmd_found"))
            out.append(_c("vmd", "ok" if vmd else "warn",
                          f"{p.get('vmd_path')} (version {p.get('vmd_version')})"
                          if vmd else
                          "not found by the server: set VMD_BIN in the client's "
                          "env block (the server gets only the env you give it); "
                          "renders fall back to the matplotlib renderer"))
            if vmd:
                tach = p.get("tachyon_path")
                out.append(_c("tachyon", "ok" if tach else "warn",
                              tach or "not found next to VMD; the VMD renderer "
                                      "needs it to make images"))
            out.append(_c("ffmpeg", "ok" if p.get("ffmpeg") else "warn",
                          p.get("ffmpeg") or "not found; only movies and the "
                                             "video tools need it"))
            out.append(_c("renderer", "ok",
                          f"recommended: {p.get('recommended_renderer')}"))

            roots = [r for r in (env.get("VMD_AGENT_ALLOWED_ROOTS", "")
                                 .split(os.pathsep)) if r.strip()]
            if not roots:
                out.append(_c("sandbox", "warn",
                              "VMD_AGENT_ALLOWED_ROOTS is not set: the file "
                              "sandbox is OFF, and tools can read any file the "
                              "server's user can"))
            else:
                bad = [r for r in roots if not os.path.isdir(r)]
                if bad:
                    out.append(_c("sandbox", "fail",
                                  f"allowed root does not exist: {bad}"))
                else:
                    outside = "/etc/hosts" if os.path.exists("/etc/hosts") \
                        else os.path.dirname(os.path.realpath(roots[0]))
                    blocked = await call("detect_system",
                                         {"topology": outside})
                    rel = await call("verify_provenance",
                                     {"path_or_dir": "_mcp_check_relative"})
                    ok_block = isinstance(blocked, dict) and blocked.get("blocked")
                    ok_rel = not (isinstance(rel, dict) and rel.get("blocked"))
                    out.append(_c(
                        "sandbox", "ok" if ok_block and ok_rel else "fail",
                        f"roots {roots}; a path outside them is "
                        f"{'refused' if ok_block else 'NOT refused'}; a "
                        f"relative path resolves "
                        f"{'inside' if ok_rel else 'OUTSIDE'} the first root"))

            tcl = await call("run_vmd_tcl", {"script": "puts check"})
            disabled = isinstance(tcl, dict) and "disabled" in str(
                tcl.get("error", ""))
            out.append(_c("raw_tcl_tool", "ok",
                          "run_vmd_tcl is disabled (the safe default)"
                          if disabled else
                          "run_vmd_tcl is ENABLED (VMD_AGENT_ENABLE_TCL=1): the "
                          "agent can run Tcl; the screen is an accident guard, "
                          "not a security boundary"))

            if render:
                if not vmd:
                    out.append(_c("render", "skip", "needs a VMD the server can find"))
                else:
                    base = roots[0] if roots else tempfile.gettempdir()
                    work = tempfile.mkdtemp(prefix="_mcp_check_", dir=base)
                    try:
                        pdb = os.path.join(work, "t.pdb")
                        with open(pdb, "w") as fh:
                            fh.write(_PDB)
                        png = os.path.join(work, "t.png")
                        r = await call("render_image", {
                            "topology": pdb, "out_png": png, "width": 200,
                            "height": 150})
                        good = isinstance(r, dict) and r.get("ok") and \
                            os.path.exists(png)
                        out.append(_c("render", "ok" if good else "fail",
                                      "VMD + Tachyon produced an image" if good
                                      else f"render failed: {str(r)[:200]}"))
                    finally:
                        shutil.rmtree(work, ignore_errors=True)
    return out


def check_mcp_server(roots: Optional[Sequence[str]] = None,
                     vmd: Optional[str] = None,
                     extra_env: Optional[Dict[str, str]] = None,
                     command: Optional[str] = None,
                     args: Optional[Sequence[str]] = None,
                     render: bool = False, timeout: float = 120.0) -> dict:
    """Run the checks; returns ``{"ready", "checks"}``. ``ready`` is false on any fail."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        return {"ready": False, "checks": [_c(
            "mcp_sdk", "fail",
            "the MCP SDK is not installed here: Python >= 3.10 and "
            "`pip install -e '.[server]'`")]}
    from vmd_agent import settings
    from vmd_agent.environment import find_vmd
    env: Dict[str, str] = dict(extra_env or {})
    roots = roots or ([settings.get("data_dir")] if settings.get("data_dir") else None)   # what setup chose
    if roots:
        env["VMD_AGENT_ALLOWED_ROOTS"] = os.pathsep.join(roots)
    vmd = vmd or find_vmd()
    if vmd:
        env["VMD_BIN"] = vmd
    for var in (settings.ENV_HOME, settings.ENV_DIR):          # let the server see the same saved settings
        if os.environ.get(var):
            env.setdefault(var, os.environ[var])
    command = command or sys.executable
    args = list(args) if args is not None else (
        ["-m", "vmd_agent.server"] if command == sys.executable else [])
    try:
        checks = asyncio.run(_check(command, args, env, render, timeout))
    except BaseException as e:
        return {"ready": False, "checks": [_c(
            "connect", "fail",
            f"{type(e).__name__}: {e}. The server must print nothing but "
            f"MCP messages on stdout, and the command must exist: "
            f"{command} {' '.join(args)}")]}
    return {"ready": not any(c["status"] == "fail" for c in checks),
            "checks": checks}


def report_text(result: dict) -> str:
    mark = {"ok": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "skip"}
    lines = [f"{mark[c['status']]:4}  {c['name']:20} {c['detail']}"
             for c in result["checks"]]
    lines.append("")
    lines.append("READY: a client can use this server" if result["ready"]
                 else "NOT READY: fix the FAIL lines above")
    return "\n".join(lines)


# ------------------------------------------------------------ client config
def build_mcp_config(roots: Optional[Sequence[str]] = None, vmd: Optional[str] = None,
                     system_name: Optional[str] = None,
                     server_command: Optional[str] = None) -> dict:
    """The MCP client configuration for this machine, ready to paste.

    Detects VMD when ``vmd`` is not given, uses the absolute path of the installed
    ``vmd-agent-server`` (a client does not activate your virtualenv), and says where
    each client keeps its configuration on this OS."""
    from vmd_agent import platform_info as P
    from vmd_agent.environment import find_vmd
    from vmd_agent import settings
    sysname = P.system(system_name)
    vmd = vmd or find_vmd()
    roots = roots or ([settings.get("data_dir")] if settings.get("data_dir") else None)   # what setup chose
    cmd = server_command or P.server_command_path(sysname)
    env: Dict[str, str] = {}
    if os.environ.get(settings.ENV_HOME):                      # a contained install keeps its settings in one folder
        env[settings.ENV_HOME] = os.environ[settings.ENV_HOME]
    if vmd:
        env["VMD_BIN"] = vmd
    if roots:
        env["VMD_AGENT_ALLOWED_ROOTS"] = os.pathsep.join(
            os.path.abspath(r) for r in roots) if sysname != P.WINDOWS \
            else ";".join(roots)
    server = {"command": cmd}
    if env:
        server["env"] = env
    claude_code = ["claude", "mcp", "add", "vmd-agent"] + sum(
        (["-e", f"{k}={v}"] for k, v in env.items()), []) + ["--", cmd]
    return {"system": sysname, "config": {"mcpServers": {"vmd-agent": server}},
            "claude_desktop_config": P.claude_desktop_config_path(sysname),
            "claude_code_command": claude_code,
            "notes": ([] if vmd else ["VMD was not found; renders will use the built-in "
                                      "renderer. Pass --vmd to set it."]) +
                     ([] if roots else ["No --roots given: the file sandbox would be OFF. "
                                        "Pass --roots <your data folder>."])}


def write_claude_desktop_config(path: str, server_block: dict) -> str:
    """Merge the ``vmd-agent`` server into Claude Desktop's config file, keeping a
    backup. Refuses to touch a file that is not valid JSON. Returns the backup path
    (or ``""`` if the file did not exist)."""
    import shutil
    data: dict = {}
    backup = ""
    if os.path.exists(path):
        with open(path) as fh:
            raw = fh.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except ValueError as e:
            raise ValueError(f"{path} is not valid JSON ({e}); not modified") from e
        if not isinstance(data, dict):
            raise ValueError(f"{path} does not hold a JSON object; not modified")
        backup = path + ".vmd-agent.bak"
        shutil.copyfile(path, backup)
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"'mcpServers' in {path} is not an object; not modified")
    servers["vmd-agent"] = server_block["mcpServers"]["vmd-agent"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    return backup

