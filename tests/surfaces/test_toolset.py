"""The tool registry: independent of any AI client, schemas, and parity with the
MCP server (checked against the real SDK where it is installed)."""
import asyncio
import json
import os
import subprocess
import sys

import pytest

from vmd_agent import toolset

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
LIBRARY = {
    "probe_environment", "inspect_files", "detect_system", "structure_stats", "search_pdb", "fetch_structure",
    "visualize_and_interpret", "render_image", "render_movie", "annotate_image", "view_image", "generate_visualization_recipe",
    "list_representations", "color_key", "export_session", "run_tcl",
    "analyze_trajectory", "measure_with_vmd", "select_keyframes", "periodic_box",
    "find_interactions", "secondary_structure", "backbone_torsions", "check_structure", "align_structures",
    "convert_trajectory", "write_structure", "make_map", "inspect_map", "combine_maps", "fit_to_map",
    "build_system", "mutate_residue", "merge_structures", "build_membrane", "build_nanotube", "prepare_namd", "write_slurm_script",
    "probe_video", "interpret_video", "verify_claims", "record_visual_interpretation", "assemble_report", "verify_provenance",
    "window_open", "window_load", "window_molecules", "window_representation", "window_display", "window_view", "window_animate", "window_query",
    "window_snapshot", "window_scene", "window_save",
}


def test_the_registry_holds_every_tool():
    assert set(toolset.library_tools()) == LIBRARY and len(toolset.library_tools()) == 55
    assert set(toolset.TOOLS) == LIBRARY | {"run_workflow"}                  # the workflows are reached through one call, not 6 tools


def test_the_library_is_one_grouped_list():
    names = toolset.library_tools()
    assert len(names) == len(set(names))                                    # a tool is in exactly one group
    assert all(toolset.group_of(n) for n in names) and toolset.group_of("run_workflow") == ""
    assert {toolset.needs_vmd(n) for n in names} == {"yes", "no", "optional"}
    assert set(toolset.ALL) == set(toolset.TOOLS)


def test_importing_the_tools_does_not_need_the_mcp_sdk():
    code = ("import sys\n"
            "from vmd_agent import toolset\n"
            "assert len(toolset.TOOLS) == 56\n"
            "assert 'mcp' not in sys.modules, 'toolset imported the MCP SDK'\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, env={**os.environ, "PYTHONWARNINGS": "ignore"})
    assert r.returncode == 0, r.stderr[-400:]


def test_every_tool_has_a_description_and_a_valid_json_schema():
    for spec in toolset.tool_specs():
        s = spec["input_schema"]
        assert len(spec["description"]) > 30, spec["name"]
        assert s["type"] == "object" and set(s["required"]) <= set(s["properties"])
        json.dumps(spec)                                    # serialisable


def test_schema_types_follow_the_signatures():
    s = toolset.tool_schema(toolset.TOOLS["analyze_trajectory"])["input_schema"]
    p = s["properties"]
    assert p["topology"] == {"type": "string"}
    assert p["analyses"] == {"type": "array", "items": {"type": "string"}}
    assert p["cutoff"] == {"type": "number"} and p["step"] == {"type": "integer"}
    assert p["unwrap"] == {"type": "boolean"}
    assert set(s["required"]) == {"topology", "trajectory", "analyses"}


def test_a_subset_of_specs_can_be_requested():
    assert [s["name"] for s in toolset.tool_specs(["detect_system"])] == [
        "detect_system"]


def test_tools_run_for_real_and_policy_errors_are_results_not_exceptions(
        tmp_path, monkeypatch):
    r = toolset.TOOLS["detect_system"](os.path.join(DATA, "1ubq.pdb"))
    assert r["components"]["protein"]["n_residues"] == 76
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(root))
    blocked = toolset.TOOLS["detect_system"]("/etc/hosts")
    assert blocked["blocked"] and not blocked["ok"]


def test_run_vmd_tcl_is_disabled_by_default():
    r = toolset.TOOLS["run_tcl"]("puts hi")
    assert r["blocked"] and "disabled" in r["error"]


def test_view_image_returns_a_path_for_images_and_refuses_other_files(tmp_path):
    from PIL import Image
    png = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(png)
    r = toolset.TOOLS["view_image"](str(png))
    assert r["ok"] and r["image"] == str(png)
    txt = tmp_path / "a.txt"
    txt.write_text("x")
    with pytest.raises(ValueError, match="image"):
        toolset.TOOLS["view_image"](str(txt))


@pytest.mark.requires_mcp
def test_schemas_agree_with_what_the_real_mcp_sdk_publishes():
    """The registry and the MCP server describe the same parameters."""
    from vmd_agent import server
    real = {t.name: (getattr(t, "inputSchema", None) or t.input_schema)
            for t in asyncio.run(server.mcp.list_tools())}
    for spec in toolset.tool_specs():
        mine, theirs = spec["input_schema"], real[spec["name"]]
        shown = set(theirs.get("properties", {})) - set(toolset.HIDDEN_FROM_MODELS)    # models are not shown vmd_path
        assert set(mine["properties"]) == shown, spec["name"]
        assert set(mine["required"]) == set(theirs.get("required", [])), \
            spec["name"]
