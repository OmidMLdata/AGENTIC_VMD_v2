"""Putting a model's tool arguments right: each correction has one sensible reading, and anything ambiguous is left alone."""
import json
import os
import shutil

import pytest

from vmd_agent import agent, argfix, toolset
from vmd_agent.toolhints import CHOICES

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
FILES = ["protein.pdb", "protein.dcd", "runs/other.dcd", "clip.mp4", "figure.png", "notes.txt"]


def schema(tool):
    return toolset.tool_schema(toolset.TOOLS[tool])["input_schema"]


def fix(tool, args, files=FILES):
    return argfix.fix(tool, args, schema(tool), CHOICES, files)


def test_types_are_put_right():
    args, notes = fix("select_keyframes", {"topology": "protein.pdb", "trajectory": "protein.dcd", "k": "3", "step": 2.0})
    assert args["k"] == 3 and isinstance(args["k"], int) and args["step"] == 2 and len(notes) == 2
    args, _ = fix("analyze_trajectory", {"topology": "protein.pdb", "trajectory": "protein.dcd", "analyses": "rmsd"})
    assert args["analyses"] == ["rmsd"]
    args, _ = fix("analyze_trajectory", {"topology": "protein.pdb", "trajectory": "protein.dcd", "analyses": "rmsd, rgyr"})
    assert args["analyses"] == ["rmsd", "rgyr"]
    args, _ = fix("analyze_trajectory", {"topology": "protein.pdb", "trajectory": "protein.dcd", "analyses": '["rmsd", "rgyr"]', "unwrap": "true"})
    assert args["analyses"] == ["rmsd", "rgyr"] and args["unwrap"] is True


def test_a_correct_call_is_left_exactly_as_it_was():
    given = {"topology": "protein.pdb", "trajectory": "protein.dcd", "analyses": ["rmsd"], "step": 2}
    args, notes = fix("analyze_trajectory", given)
    assert args == given and notes == []


def test_choices_are_matched_without_case_or_punctuation():
    args, notes = fix("find_interactions", {"topology": "protein.pdb", "kind": "Salt-Bridges"})
    assert args["kind"] == "salt_bridges" and notes
    args, _ = fix("measure_with_vmd", {"topology": "protein.pdb", "kind": "RMSD"})
    assert args["kind"] == "rmsd"
    args, notes = fix("measure_with_vmd", {"topology": "protein.pdb", "kind": "banana"})
    assert args["kind"] == "banana" and not notes                                          # a wrong value is the tool's to refuse


def test_known_aliases_are_read_as_the_parameter_the_tool_has():
    args, notes = fix("analyze_trajectory", {"top": "protein.pdb", "traj": "protein.dcd", "analyses": ["rmsd"]})
    assert args["topology"] == "protein.pdb" and args["trajectory"] == "protein.dcd" and "top" not in args and len(notes) == 2
    args, _ = fix("detect_system", {"topology": "protein.pdb", "trajectory": "protein.dcd", "sel": "protein"})
    assert "sel" in args                                                                    # this tool has no selection: left for the tool to reject


def test_a_file_name_without_its_folder_is_found_when_it_is_unique():
    args, notes = fix("probe_video", {"video": "clip.mp4"}, ["a/clip.mp4"])
    assert args["video"] == "a/clip.mp4" and notes
    args, notes = fix("probe_video", {"video": "clip.mp4"}, ["a/clip.mp4", "b/clip.mp4"])
    assert args["video"] == "clip.mp4" and not notes                                        # two candidates: not guessed
    args, _ = fix("probe_video", {"video": "/abs/clip.mp4"}, ["a/clip.mp4"])
    assert args["video"] == "/abs/clip.mp4"                                                 # absolute paths are the sandbox's business


def test_a_trajectory_given_as_the_topology_is_turned_round():
    args, notes = fix("analyze_trajectory", {"topology": "protein.dcd", "trajectory": "protein.pdb", "analyses": ["rmsd"]})
    assert (args["topology"], args["trajectory"]) == ("protein.pdb", "protein.dcd") and notes
    args, notes = fix("analyze_trajectory", {"topology": "protein.dcd", "analyses": ["rmsd"]})
    assert args["trajectory"] == "protein.dcd" and args["topology"] == "protein.pdb"         # and the missing topology is the folder's only structure


def test_a_missing_required_file_is_filled_only_when_one_file_fits():
    args, notes = fix("structure_stats", {})
    assert args["topology"] == "protein.pdb" and "only structure file" in notes[0]
    args, notes = fix("structure_stats", {}, ["a.pdb", "b.pdb"])
    assert "topology" not in args and not notes
    args, _ = fix("analyze_trajectory", {"analyses": ["rmsd"]}, ["protein.pdb", "protein.dcd"])
    assert args["topology"] == "protein.pdb" and args["trajectory"] == "protein.dcd"
    args, _ = fix("analyze_trajectory", {"analyses": ["rmsd"]}, ["protein.pdb", "a.dcd", "b.dcd"])
    assert "trajectory" not in args                                                         # two trajectories: the model must choose
    args, _ = fix("structure_stats", {}, ["system.psf", "system.pdb"])
    assert args["topology"] == "system.pdb"                                                 # a PSF alone is not coordinates


def test_the_folder_listing_is_shallow_and_leaves_out_hidden_files(tmp_path):
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    for p in ("x.pdb", "a/y.dcd", "a/b/z.png", "a/b/c/deep.pdb", ".hidden"):
        (tmp_path / p).write_text("x")
    assert argfix.list_files(str(tmp_path)) == ["a/b/z.png", "a/y.dcd", "x.pdb"]


# ---------------------------------------------------------- inside the agent, with the real tools
@pytest.fixture()
def folder(tmp_path, monkeypatch):
    for f in ("protein.pdb", "protein.dcd"):
        shutil.copy(os.path.join(DATA, "sample", "sample.pdb" if f.endswith("pdb") else "sample.dcd"), tmp_path / f)
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    return tmp_path


def test_the_agent_repairs_a_call_runs_it_and_tells_the_model(folder):
    a = agent.Agent("http://127.0.0.1:1/v1", "m")
    out = json.loads(a.run_tool({"id": "1", "name": "analyze_trajectory", "arguments": {"traj": "protein.dcd", "analyses": "rgyr", "step": "2"}}))
    assert "rgyr" in out["results"] and "error" not in out
    assert "was read as" in out["note_on_arguments"] and "only structure file" in out["note_on_arguments"]
    logged = a.call_log[0]
    assert logged["arguments"]["trajectory"] == "protein.dcd" and logged["arguments"]["step"] == 2 and len(logged["repairs"]) >= 3


def test_with_repair_off_the_model_meets_its_own_mistake(folder):
    a = agent.Agent("http://127.0.0.1:1/v1", "m", repair=False)
    out = json.loads(a.run_tool({"id": "1", "name": "analyze_trajectory", "arguments": {"traj": "protein.dcd", "analyses": "rgyr"}}))
    assert "bad arguments" in out["error"] and "note_on_arguments" not in out


def test_housekeeping_fields_are_not_sent_to_the_model_but_stay_in_the_log():
    result = {"ok": True, "n": 3, "reproduce_script": "/x/a.tcl", "reproduce_with": "vmd -e a.tcl", "tachyon_stderr": "", "inner": [{"how_to_view": "x", "v": 1}]}
    shown = agent.digest(result)
    assert shown == {"ok": True, "n": 3, "reproduce_script": "/x/a.tcl", "inner": [{"v": 1}]} and "reproduce_with" in result


def test_a_file_that_does_not_exist_but_has_a_companion_of_the_same_name_is_read_as_the_companion():
    args, notes = fix("analyze_trajectory", {"topology": "protein.psf", "trajectory": "protein.dcd", "analyses": ["rmsd"]}, ["protein.pdb", "protein.dcd", "other.pdb"])
    assert args["topology"] == "protein.pdb" and "same name" in notes[0]
    args, _ = fix("analyze_trajectory", {"topology": "protein.psf", "trajectory": "protein.dcd", "analyses": ["rmsd"]}, ["protein.pdb", "protein.gro", "protein.dcd"])
    assert args["topology"] == "protein.psf"                                                  # two files of that name: not guessed


def test_a_trajectory_named_twice_gets_the_structure_that_goes_with_it():
    files = ["protein.pdb", "protein.dcd", "moved.pdb"]
    args, notes = fix("measure_with_vmd", {"topology": "protein.dcd", "trajectory": "protein.dcd", "kind": "rmsd"}, files)
    assert (args["topology"], args["trajectory"]) == ("protein.pdb", "protein.dcd") and "is a trajectory" in notes[0]
    args, _ = fix("measure_with_vmd", {"topology": "protein.dcd", "kind": "rmsd"}, ["a.pdb", "b.pdb", "protein.dcd"])
    assert args["topology"] == "protein.dcd"                                                  # two structures and none of the same name: left for the tool to refuse
