"""MCP server exposing the VMD-Agent toolkit to any MCP client.

Run on the machine that has the data (and, optionally, VMD)::

    vmd-agent-server            # stdio

then register it in the client's MCP config (see the README). The tools
themselves live in :mod:`vmd_agent.toolset` and do not depend on MCP; this module
only registers them with the MCP SDK. They return JSON so the agent can chain
them, and ``view_image`` returns the image itself.

You do not need an MCP client to use the toolkit: ``vmd-agent chat`` runs the same
tools with any OpenAI-compatible model (see :mod:`vmd_agent.chat`).

Security
--------
Set ``VMD_AGENT_ALLOWED_ROOTS`` to confine every path the tools read or write
(the Docker image sets it to ``/data``). ``run_vmd_tcl`` is disabled unless
``VMD_AGENT_ENABLE_TCL=1``. See :mod:`vmd_agent.security`.
"""
from __future__ import annotations

try:
    from mcp.server.fastmcp import FastMCP, Image          # mcp 1.x
except ModuleNotFoundError:
    try:
        # mcp 2.x renamed FastMCP to MCPServer; the parts used here are the same
        from mcp.server.mcpserver import MCPServer as FastMCP, Image
    except ModuleNotFoundError as _e:  # pragma: no cover
        raise SystemExit(
            "The MCP server needs the 'mcp' SDK, which requires Python >=3.10.\n"
            "  - Check your version:  python --version\n"
            "  - If >=3.10:  pip install mcp   (or: pip install -e '.[server]')\n"
            "  - If <3.10:   run the server under a newer Python (e.g. a conda env:\n"
            "                conda create -n vmd-agent python=3.11 && conda activate vmd-agent\n"
            "                then pip install -e '.[all]')\n"
            "The rest of the toolkit (inspect/detect/recipe/analyze/report + CLI) "
            "works without 'mcp' on Python 3.9."
        ) from _e

from vmd_agent import security
from vmd_agent import toolset
from vmd_agent.toolset import ENV_ENABLE_TCL, TOOLS  # noqa: F401

mcp = FastMCP("vmd-agent")


def tool():
    """Register a function as an MCP tool, turning policy violations into
    structured results instead of protocol failures."""
    def deco(fn):
        return mcp.tool()(toolset.guard(fn))
    return deco


for _name, _fn in TOOLS.items():
    if _name != "view_image":                  # returns an image to MCP clients
        mcp.tool()(_fn)


@mcp.tool()
def view_image(path: str) -> Image:
    """Return an image (render, frame, or analysis plot) for the agent to see."""
    toolset.TOOLS["view_image"](path)           # policy and file-type checks
    return Image(path=path)


def main():
    if security.allowed_roots() is None:
        import sys
        # stderr only: stdout carries the JSON-RPC stream to the client.
        print("vmd-agent: WARNING: VMD_AGENT_ALLOWED_ROOTS is not set, so the "
              "file sandbox is OFF and tools can read any file this user can. "
              "Set it to the directory (or os.pathsep-separated directories) "
              "the agent may use.", file=sys.stderr, flush=True)
    mcp.run()


if __name__ == "__main__":
    main()
