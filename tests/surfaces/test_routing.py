"""Routing: which tools a question gets.

The keywords of the router were written while looking at the benchmark's prompts, so those prompts prove little. ``PARAPHRASES`` is a
second set, worded differently on purpose, with the tools that would answer each; routing must keep at least one of them. Words
added to the router to fix a miss here make this set less independent, so new misses are added as new questions, not edited away."""
import json

import pytest

from vmd_agent import model_tasks as M, routing, toolset

ALL = list(toolset.ALL)

PARAPHRASES = [
    ("How compact is the protein over time in run1.xtc?", {"analyze_trajectory", "measure_with_vmd"}),
    ("Is my simulation stable?", {"analyze_trajectory", "run_workflow"}),
    ("Which atoms of chain A are near the drug?", {"find_interactions", "analyze_trajectory"}),
    ("Are there any steric clashes or odd geometry in my model?", {"check_structure", "detect_system"}),
    ("Give me a nicer picture of 4hhb", {"visualize_and_interpret", "render_image"}),
    ("Grab hemoglobin from the PDB", {"search_pdb", "fetch_structure"}),
    ("Make me a production NAMD setup for this protein", {"prepare_namd", "run_workflow", "build_system"}),
    ("Cut out just the backbone atoms from my trajectory and save them", {"convert_trajectory"}),
    ("How wide is the box?", {"periodic_box", "detect_system", "analyze_trajectory"}),
    ("Is the density map lined up with my model?", {"fit_to_map", "inspect_map"}),
    ("Make a flipbook of my simulation", {"render_movie"}),
    ("How long is that video and does it play?", {"probe_video"}),
    ("Do the checksums still match?", {"verify_provenance"}),
    ("Swap residue 20 of segment P0 for an alanine", {"mutate_residue"}),
    ("Overlay model.pdb on reference.pdb", {"align_structures"}),
    ("I want to see the secondary structure content", {"secondary_structure", "structure_stats"}),
    ("List the water molecules", {"detect_system", "structure_stats"}),
    ("How many frames does the dcd have?", {"inspect_files", "detect_system"}),
    ("Which plugins does my VMD have?", {"probe_environment"}),
    ("Smooth the density with a gaussian", {"combine_maps"}),
    ("Turn the density into an isosurface picture", {"render_image"}),
    ("Create a cluster job file for 4 nodes", {"write_slurm_script"}),
    ("Is residue 5 cis or trans?", {"check_structure", "backbone_torsions"}),
    ("Which residues move the most?", {"analyze_trajectory", "measure_with_vmd"}),
    ("Show hydrogen bonding between the two chains", {"find_interactions", "analyze_trajectory", "structure_stats"}),
    ("Slice every tenth frame out into a smaller file", {"convert_trajectory"}),
    ("Put a legend on my picture", {"annotate_image", "color_key"}),
    ("What is the colour scheme in this figure?", {"color_key"}),
    ("Is this PDB sane?", {"run_workflow", "detect_system", "check_structure"}),
    ("Write the first frame as a gro file", {"write_structure"}),
]


#: a second paraphrased set, written after the first had been used to widen the router's vocabulary: 20 of its 24 were routed correctly
#: before the four last misses were fixed ("integrity", "dihedrals", "spinning", "join"), so expect a router like this to miss roughly one
#: question in six it has not seen; the model's `offer_tools` is how it recovers.
FRESH = [
    ("Plot how the protein's size changes frame by frame", {"analyze_trajectory", "measure_with_vmd"}),
    ("Where does the protein flex the most?", {"analyze_trajectory", "measure_with_vmd"}),
    ("Are there ionic contacts between Lys and Asp?", {"find_interactions", "analyze_trajectory"}),
    ("Tell me how many waters surround the ligand over time", {"measure_with_vmd", "analyze_trajectory", "find_interactions"}),
    ("Make a pretty ray traced image with ambient occlusion", {"render_image"}),
    ("Take 1ubq from RCSB", {"fetch_structure"}),
    ("Is there a 4ake structure I could download?", {"search_pdb", "fetch_structure"}),
    ("Convert this xtc to dcd", {"convert_trajectory"}),
    ("Wrap the molecules back into the box and write a new trajectory", {"convert_trajectory"}),
    ("Compute an electron-density-like map of the ligand", {"make_map"}),
    ("Take the difference between map A and map B", {"combine_maps"}),
    ("Which VMD features can't you use?", {"probe_environment"}),
    ("Does VMD exist on this machine?", {"probe_environment"}),
    ("Check the file integrity of my previous run", {"verify_provenance"}),
    ("Make a report for my advisor", {"assemble_report", "run_workflow"}),
    ("What's the frame rate of the animation file?", {"probe_video"}),
    ("Put a K6A mutation in", {"mutate_residue"}),
    ("Which backbone dihedrals look weird?", {"backbone_torsions"}),
    ("Show me solvent accessible area per residue", {"analyze_trajectory", "measure_with_vmd"}),
    ("Let me look at the surface of the pocket", {"render_image", "visualize_and_interpret"}),
    ("Record a spinning video of the protein", {"render_movie"}),
    ("Join two PSF systems into one", {"merge_structures"}),
    ("What's the thickness of my bilayer?", {"build_membrane", "analyze_trajectory", "measure_with_vmd"}),
    ("Give me a sbatch file", {"write_slurm_script"}),
]


def test_the_second_paraphrased_set_is_routed_too():
    missed = [q for q, want in FRESH if not (want & set(routing.select(q, ALL)))]
    assert not missed, missed


def test_a_question_keeps_a_tool_that_answers_it_in_the_paraphrased_set():
    missed = [(q, sorted(want), routing.matched_groups(q)) for q, want in PARAPHRASES if not (want & set(routing.select(q, ALL)))]
    assert len(missed) <= 0.1 * len(PARAPHRASES), "routing drops the right tools for: " + "; ".join(q for q, _, _ in missed)


def test_every_benchmark_prompt_keeps_a_tool_that_answers_it():
    missed = [t.id for t in M.TASKS if t.tools and not (set(t.tools) & set(routing.select(t.prompt, ALL)))]
    assert not missed, missed


def test_the_offered_set_is_small_and_never_empty():
    sizes = [len(routing.select(t.prompt, ALL)) for t in M.TASKS]
    assert min(sizes) >= len(routing.BASE) and sum(sizes) / len(sizes) < 0.5 * len(ALL)
    assert set(routing.select("zzzz qqqq", ALL)) >= set(routing.BASE) and len(routing.select("zzzz qqqq", ALL)) < len(ALL)


def test_the_selection_is_stable_and_in_registration_order():
    a, b = routing.select("Has my run settled? Use run.psf and run.dcd.", ALL), routing.select("Has my run settled? Use run.psf and run.dcd.", ALL)
    assert a == b and a == [n for n in ALL if n in a]
    assert "run_workflow" in a and "analyze_trajectory" in a and "build_system" not in a


def test_only_available_tools_are_offered():
    assert set(routing.select("build a membrane and draw it", ["inspect_files", "build_membrane"])) == {"inspect_files", "build_membrane"}


@pytest.mark.parametrize("tool", sorted(set(ALL)))
def test_every_tool_belongs_to_the_base_or_a_group(tool):
    assert tool in routing.BASE or routing.group_of(tool), f"{tool} can never be offered by routing"


# ------------------------------------------------------------------------------------ inside the agent
from conftest import scripted_server as _server
from vmd_agent import agent  # noqa: E402


def _call(name, **args):
    return {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def _tool_names(request):
    return [t["function"]["name"] for t in request.get("tools", [])]


def test_in_auto_the_model_is_sent_only_the_tools_that_fit_and_a_way_to_ask_for_more(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    srv, url, requests = _server([{"content": "Done."}])
    try:
        a = agent.Agent(url, "m", tools="auto", guard=False)
        a.ask("Has my run settled? Use run.psf and run.dcd.")
        a_all = agent.Agent(url, "m", tools="all", guard=False)
        a_all.ask("hello")
    finally:
        srv.shutdown()
    sent, sent_all = _tool_names(requests[0]), _tool_names(requests[1])
    assert "analyze_trajectory" in sent and "run_workflow" in sent and "build_system" not in sent and routing.OFFER in sent
    assert len(sent) < 0.4 * len(sent_all) and len(sent_all) == 45 and routing.OFFER not in sent_all
    assert len(json.dumps(requests[0]["tools"])) < 0.5 * len(json.dumps(requests[1]["tools"]))        # and so are the tokens it costs


def test_the_model_can_ask_for_a_group_it_was_not_given_and_then_use_it(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    srv, url, requests = _server([_call(routing.OFFER, group="build"), _call("build_nanotube", out_pdb="t.pdb"), {"content": "Asked, then used."}])
    try:
        a = agent.Agent(url, "m", tools="auto", guard=False)
        a.ask("Hello there")
    finally:
        srv.shutdown()
    assert "build_system" not in _tool_names(requests[0]) and "build_system" in _tool_names(requests[1])
    assert "build_system" in a.widened and a.call_log[0]["name"] == "build_nanotube" and "unknown tool" not in str(a.call_log[0]["result"])   # it ran (or needed VMD), it was not refused


def test_a_tool_outside_the_offered_set_is_allowed_in_auto_and_refused_otherwise(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    auto = agent.Agent("http://127.0.0.1:1/v1", "m", tools="auto")
    auto.names = routing.select("what is in x.pdb", list(toolset.ALL))
    assert "write_slurm_script" not in auto.names
    out = auto.run_tool({"id": "1", "name": "write_slurm_script", "arguments": {"command": "eq.namd", "out_path": "j.sbatch", "kind": "namd"}})
    assert "sbatch" in out and "write_slurm_script" in auto.widened
    fixed = agent.Agent("http://127.0.0.1:1/v1", "m", tools="all")
    fixed.names = [n for n in fixed.names if n != "measure_with_vmd"]
    assert "unknown tool" in fixed.run_tool({"id": "1", "name": "measure_with_vmd", "arguments": {}})


def test_each_question_is_routed_afresh(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    srv, url, requests = _server([{"content": "ok"}])
    try:
        a = agent.Agent(url, "m", tools="auto", guard=False)
        a.ask("Grab 1UBQ from the PDB")
        a.ask("Build a membrane")
    finally:
        srv.shutdown()
    assert "fetch_structure" in _tool_names(requests[0]) and "build_membrane" not in _tool_names(requests[0])
    assert "build_membrane" in _tool_names(requests[1]) and "fetch_structure" not in _tool_names(requests[1])
