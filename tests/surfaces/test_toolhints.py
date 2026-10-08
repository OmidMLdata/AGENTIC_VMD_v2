"""What a model is told about parameters, and the plain sentence at the top of a result."""
import json
import os
import shutil

from vmd_agent import agent, toolhints, toolset

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def _spec(name):
    return toolhints.enrich(toolset.tool_specs([name]))[0]["input_schema"]["properties"]


def test_ambiguous_parameters_get_a_meaning_and_choice_parameters_their_allowed_values():
    props = _spec("vmd_measure")
    assert "superpose" in props["align"]["description"] and "false" in props["align"]["description"]
    assert "rmsd" in props["kind"]["enum"] and "rgyr" in props["kind"]["enum"]
    assert "enum" in _spec("vmd_interactions")["kind"] and "salt_bridges" in _spec("vmd_interactions")["kind"]["enum"]
    assert "topology" in _spec("vmd_measure") and "description" not in _spec("vmd_measure")["topology"]      # obvious names stay bare


def test_the_original_specs_are_not_changed():
    before = json.dumps(toolset.tool_specs(["vmd_measure"]))
    toolhints.enrich(toolset.tool_specs(["vmd_measure"]))
    assert json.dumps(toolset.tool_specs(["vmd_measure"])) == before and "description" not in json.loads(before)[0]["input_schema"]["properties"]["align"]


def test_the_agent_sends_the_hints(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    sent = {t["function"]["name"]: t["function"]["parameters"]["properties"] for t in agent.Agent("http://x/v1", "m", tools="core").tools}
    assert "description" in sent["analyze_trajectory"]["analyses"]


def test_system_and_stats_start_with_a_plain_sentence_that_cannot_be_misread(tmp_path, monkeypatch):
    for name in ("sample.pdb",):
        shutil.copy(os.path.join(DATA, "sample", name), tmp_path / name)
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    d = toolset.TOOLS["detect_system"]("sample.pdb")
    assert d["summary"].startswith(d["system_type"]) and "protein: 12 residues in 1 chain (A)" in d["summary"] and "LIG" in d["summary"] and "water: present" in d["summary"]
    st = toolset.TOOLS["structure_stats"]("sample.pdb")
    assert st["n_protein_residues"] == 12 and "12 protein residues in 1 protein chain" in st["summary"] and f"n_residues ({st['n_residues']}) counts every residue" in st["summary"]
    assert list(agent.digest(st))[0] == "summary"                                            # the sentence comes first for the model


def test_a_video_probe_says_which_number_is_the_picture_size(tmp_path, monkeypatch):
    from vmd_agent import tool_dataset
    tool_dataset.make_dataset(str(tmp_path))
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    r = toolset.TOOLS["probe_video"](str(tmp_path / "clip.mp4"))
    if r.get("ok"):                                                                      # needs ffmpeg
        assert "160 x 120 pixels" in r["summary"] and "file size" in r["summary"] and list(agent.digest(r))[0] == "summary"


def test_the_ligands_segment_is_not_offered_to_the_model_as_a_second_chain():
    shown = agent.digest({"n_chains": 1, "n_protein_chains": 1, "n_chains_all": 2, "summary": "x"})
    assert "n_chains_all" not in shown and shown["n_protein_chains"] == 1
    assert agent.digest({"n_chains_all": 2})["n_chains_all"] == 2                         # without a protein count there is nothing to contradict
