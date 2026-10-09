"""
vmd_agent
=========

An agentic toolkit for molecular visualization workflows: file inspection,
system detection, tailored visualization recipes, rendering (VMD or an
open-source fallback), trajectory analysis with statistically grounded
verdicts, event-aware keyframe selection, claim verification, and a
benchmark for grounded interpretation.

Two ways to use it:

1. As an **MCP server** (``python -m vmd_agent.server``) so an LLM agent
   (e.g. Claude Desktop) can call the tools directly. Run it on the machine
   (or container) that holds the data.

2. As a **CLI / Python library** for scripted use.

Design contract
---------------
* Inspection, detection, trajectory analysis, claim verification and the
  matplotlib renderer use only open-source Python packages, so they work on
  any machine, VMD present or not. VMD is **not bundled** (UIUC license).
* VMD rendering and ``run_tcl`` locate a user-installed VMD and fail
  gracefully with actionable messages when it is missing.
* Every public function returns a JSON-serialisable ``dict`` so calls chain.
* Results state how they were obtained (bond source, H-bond method, renderer,
  time axis) and what they cannot show.
"""

__version__ = "0.34.1"

from vmd_agent.inputs.inspection import inspect_files
from vmd_agent.structure.detect import detect_system
from vmd_agent.visual.recipes import generate_visualization_recipe
from vmd_agent.dynamics.analysis import analyze_trajectory
from vmd_agent.auto import (visualize_and_interpret, fetch_and_visualize,
                            probe_environment, select_keyframes)
from vmd_agent.inputs.fetch import fetch_structure, search_pdb
from vmd_agent.evidence.claims import verify_claims
from vmd_agent.visual.renderers import get_renderer

__all__ = [
    "__version__",
    "probe_environment",
    "inspect_files",
    "detect_system",
    "generate_visualization_recipe",
    "analyze_trajectory",
    "visualize_and_interpret",
    "fetch_structure",
    "search_pdb",
    "fetch_and_visualize",
    "verify_claims",
    "select_keyframes",
    "get_renderer",
]
