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
EXPECTED = {
    "probe_environment", "inspect_files", "detect_system",
    "generate_visualization_recipe", "structure_stats", "color_key",
    "annotate_image", "list_representations", "describe_representation",
    "search_pdb", "fetch_structure", "fetch_and_visualize",
    "visualize_and_interpret", "render_image", "render_movie", "run_vmd_tcl",
    "analyze_trajectory", "select_keyframes", "verify_claims",
    "extract_video_frames", "probe_video", "validate_video", "interpret_video",
    "view_image", "record_visual_interpretation", "assemble_report",
    "verify_provenance",
}

VMD_EXPECTED = {
    "vmd_capabilities", "vmd_measure", "vmd_interactions", "vmd_secondary_structure", "vmd_backbone_torsions",
    "vmd_structure_check", "vmd_align_structures", "vmd_pbc_info", "vmd_convert_trajectory", "vmd_write_structure",
    "vmd_volmap", "vmd_volume_info", "vmd_build_system", "vmd_mutate_residue", "vmd_merge_structures",
    "vmd_render_scene", "export_vmd_session", "vmd_build_membrane", "vmd_build_nanotube", "vmd_render_turntable",
}


def test_the_registry_holds_every_tool():
    assert set(toolset.TOOLS) == EXPECTED | VMD_EXPECTED and len(toolset.TOOLS) == 47
    assert set(toolset.CORE_TOOLS) == EXPECTED and len(toolset.CORE_TOOLS) == 27      # none of the original tools was lost


def test_the_tool_profiles_are_consistent():
    assert set(toolset.PROFILES["all"]) == set(toolset.TOOLS)
    assert set(toolset.PROFILES["core"]) == EXPECTED
    assert VMD_EXPECTED <= set(toolset.PROFILES["vmd"])
    assert all(n in toolset.TOOLS for p in toolset.PROFILES.values() for n in p)


def test_importing_the_tools_does_not_need_the_mcp_sdk():
    code = ("import sys\n"
            "from vmd_agent import toolset\n"
            "assert len(toolset.TOOLS) == 47\n"
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
    r = toolset.TOOLS["run_vmd_tcl"]("puts hi")
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
