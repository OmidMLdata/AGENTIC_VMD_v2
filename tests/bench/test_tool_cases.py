"""The tool test set: every tool has a case, the dataset is what it was built to be, and the cases pass on this machine."""
import json
import math
import os

import pytest

from vmd_agent import toolset
from vmd_agent import tool_cases, tool_dataset as D


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    folder = str(tmp_path_factory.mktemp("toolset"))
    return folder, D.make_dataset(folder)


def test_every_tool_has_a_case():
    assert set(toolset.TOOLS) <= tool_cases.covered_tools(), sorted(set(toolset.TOOLS) - tool_cases.covered_tools())


def test_every_case_names_a_real_tool_and_unique_id_and_what_it_needs():
    ids = [c.id for c in tool_cases.CASES]
    assert len(ids) == len(set(ids))
    assert all(c.tool in toolset.TOOLS for c in tool_cases.CASES)
    assert all(n in ("vmd", "ffmpeg", "network") for c in tool_cases.CASES for n in c.needs)
    known = set(ids)
    assert all(d in known and ids.index(d) < ids.index(c.id) for c in tool_cases.CASES for d in c.after), "a case comes after what it uses"


def test_the_dataset_is_what_it_was_built_to_be(dataset):
    import MDAnalysis as mda
    import numpy as np
    folder, info = dataset
    assert set(info["files"]) >= {"protein.pdb", "protein.dcd", "moved.pdb", "target.dx", "blob.dx", "figure.png", "scene.json"}
    u = mda.Universe(os.path.join(folder, "protein.pdb"), os.path.join(folder, "protein.dcd"))
    assert u.trajectory.n_frames == D.N_FRAMES and u.atoms.n_atoms == info["n_atoms"]
    first = u.trajectory[0].positions.copy()
    last = u.trajectory[-1].positions.copy()
    shift = (last - first).mean(0)
    assert abs(shift[0] - D.DRIFT_A * (D.N_FRAMES - 1)) < 0.05 and abs(shift[1]) < 0.05       # drifts along x by construction
    assert np.allclose(u.trajectory[3].dimensions[:3], D.BOX_A)
    design = json.load(open(os.path.join(folder, "design.json")))
    assert design["n_disulfides"] == 1 and design["ligand"] == "buried" and design["n_chains"] == 1


def test_the_dataset_is_the_same_every_time(tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    D.make_dataset(a)
    D.make_dataset(b)
    import numpy as np
    import MDAnalysis as mda
    pa = mda.Universe(os.path.join(a, "protein.pdb"), os.path.join(a, "protein.dcd")).trajectory[7].positions
    pb = mda.Universe(os.path.join(b, "protein.pdb"), os.path.join(b, "protein.dcd")).trajectory[7].positions
    assert np.allclose(pa, pb)


def test_the_cases_pass_on_this_machine(tmp_path):
    """Everything that can run here: cases needing VMD, ffmpeg or the network are skipped (with the reason) when they are absent."""
    records = tool_cases.run(str(tmp_path / "run"), skip=["network"])
    failed = [(r.id, r.problems) for r in records if r.status == "FAIL"]
    assert not failed, failed
    summ = tool_cases.summary(records)
    assert summ["pass"] > 20 and all(r.seconds >= 0 for r in records)
    assert all(r.reason for r in records if r.status == "skip")


@pytest.mark.requires_vmd
def test_the_cases_that_need_vmd_pass_with_a_real_vmd(tmp_path):
    records = tool_cases.run(str(tmp_path / "run"), skip=["network"])
    assert not [r for r in records if r.status == "FAIL"]
    assert all("network" in r.reason for r in records if r.status == "skip")        # only the network was left out
    assert {r.tool for r in records if r.status == "pass"} >= set(toolset.TOOLS) - {"search_pdb", "fetch_structure"}


def test_a_wrong_expectation_is_reported_not_hidden(tmp_path):
    """The checker fails a case whose expectation is false (so a pass means something)."""
    k = tool_cases.Check({"n_atoms": 563, "ok": True})
    assert not k.eq("n_atoms", 563).problems
    assert tool_cases.Check({"n_atoms": 563}).eq("n_atoms", 564).problems
    assert tool_cases.Check({"error": "boom"}).ok().problems
    assert not tool_cases.Check({"error": "boom"}).fails("boom").problems
    assert tool_cases.Check({"x": 1.0}).near("x", 1.5, 0.1).problems
    assert tool_cases.Check({"x": {"y": [3, 4]}}).eq("x.y.1", 4).problems == []


def test_only_selects_cases_and_what_they_come_after():
    ids = [c.id for c in tool_cases.select(["mutate_residue"])]
    assert ids == ["build_system_dry", "build_system_solvated", "mutate_residue", "mutate_residue_solvated"]
    assert [c.id for c in tool_cases.select(["color_key"])] == ["color_key"]
    with pytest.raises(ValueError, match="no such case"):
        tool_cases.select(["no_such_tool"])


def test_the_command_runs_a_case_and_lists_them(tmp_path, capsys):
    from vmd_agent import cli
    assert cli.main(["bench", "tools", "--list"]) == 0
    assert "list_representations_one" in capsys.readouterr().out
    assert cli.main(["bench", "tools", "--data-dir", str(tmp_path / "d"), "--only", "color_key", "inspect_files"]) == 0
    out = capsys.readouterr().out
    assert "pass  color_key" in out and "2 passed, 0 failed" in out
    assert cli.main(["bench", "tools", "--only", "nonsense", "--data-dir", str(tmp_path / "e")]) == 2
    assert math.isfinite(1.0)
