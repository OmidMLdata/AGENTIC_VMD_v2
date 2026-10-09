"""The documented dependency order, enforced.

    inputs  <-  structure  <-  dynamics
                    ^   ^
                    |   +---  visual  (also uses environment, security)
                    +-------  evidence (also uses dynamics, environment, security)
    bench uses everything; auto / cli / server / __init__ compose.

Every import is checked, including those inside functions, so a lazy import
cannot smuggle in a back-edge. If this fails, either fix the dependency or
update docs/reference/architecture.md and this table together.
"""
import ast
import os

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src", "vmd_agent")
FOUNDATION = ("environment", "security", "llm_client", "platform_info", "settings",
              "models", "ollama_local", "progress")

COMPOSERS = ("auto", "cli", "server", "mcp_check", "toolset", "chat", "agent",
             "launcher", "wizard", "vmd_tools", "toolcli", "toolform", "vmdlink", "window_tools", "window_present", "workflows", "reporting", "ui", "tool_cases", "tool_dataset", "model_tasks", "model_bench", "toolhints", "__init__")

ALLOWED = {
    "inputs": set(),
    "structure": {"inputs", "security"},
    "dynamics": {"inputs", "structure"},
    "visual": {"inputs", "structure", "environment", "security"},
    "evidence": {"inputs", "structure", "dynamics", "environment", "security"},
    "vmdkit": {"inputs", "structure", "visual", "environment", "security", "progress"},
    "progress": set(),
    "bench": {"inputs", "structure", "dynamics", "visual", "evidence", "auto",
              "environment", "security", "llm_client", "platform_info", "settings"},
    "environment": {"platform_info", "settings"},
    "security": {"settings"},
    "llm_client": set(),
    "platform_info": set(),
    "settings": set(),
    "models": set(),
    "ollama_local": {"platform_info", "settings"},
}


def _unit(module):
    """Which unit a dotted module belongs to (subpackage or top-level module)."""
    parts = module.split(".")
    if parts[0] != "vmd_agent" or len(parts) == 1:
        return None
    return parts[1]


def _edges():
    edges = {}
    for dp, _dn, fs in os.walk(SRC):
        for f in fs:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, os.path.dirname(SRC))[:-3]
            me = _unit(rel.replace(os.sep, ".").replace(".__init__", ""))
            if me is None:
                me = "__init__"
            for n in ast.walk(ast.parse(open(path).read())):
                if not (isinstance(n, ast.ImportFrom) and n.module
                        and n.module.split(".")[0] == "vmd_agent"):
                    continue
                if n.module == "vmd_agent":
                    targets = {a.name for a in n.names if a.name != "__version__"}
                else:
                    targets = {_unit(n.module)}
                for t in targets:
                    if t and t != me:
                        edges.setdefault(me, set()).add((t, rel))
    return edges


def test_every_unit_respects_the_layering():
    violations = []
    for src, tgts in _edges().items():
        if src in COMPOSERS:
            continue
        for t, where in tgts:
            if t not in ALLOWED.get(src, set()):
                violations.append(f"{src} -> {t}  ({where})")
    assert not violations, "\n".join(sorted(violations))


def test_no_import_cycles_between_units():
    edges = _edges()
    graph = {u: {t for t, _ in ts} for u, ts in edges.items()
             if u not in COMPOSERS}
    # depth-first search for a cycle
    state = {}

    def visit(u, stack):
        state[u] = 1
        for v in graph.get(u, ()):
            if state.get(v) == 1:
                pytest.fail(f"import cycle: {' -> '.join(stack + [u, v])}")
            if v not in state and v not in COMPOSERS:
                visit(v, stack + [u])
        state[u] = 2

    for u in list(graph):
        if u not in state:
            visit(u, [])


def test_foundation_modules_import_only_other_foundations():
    """environment may use platform_info (what OS is this); nothing else."""
    edges = _edges()
    for u in FOUNDATION:
        used = {target for target, _src in (edges.get(u) or set())}
        assert used <= set(FOUNDATION), (u, used)
