"""The named workflows and the reports they write, run on real data (VMD where a step needs it)."""
import hashlib
import os
import shutil

import MDAnalysis as mda
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from vmd_agent import cli, security, toolset, workflows
from vmd_agent.inputs import volume
from vmd_agent.vmdkit import maps

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
UBQ = os.path.join(DATA, "1ubq.pdb")
PDB, DCD = os.path.join(DATA, "ubq_md", "protein.pdb"), os.path.join(DATA, "ubq_md", "protein.dcd")
vmd = pytest.mark.requires_vmd


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setenv(security.ENV_ROOTS, str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for f in (UBQ, PDB, DCD):
        shutil.copy(f, tmp_path)
    return tmp_path


def _texts(r, level=None):
    return [f["text"] for f in r["findings"] if level in (None, f["level"])]


def test_the_workflows_are_listed_with_their_files_and_an_example():
    r = toolset.TOOLS["run_workflow"]()
    assert set(r["workflows"]) == {"structure_overview", "equilibration_check", "interaction_report", "compare_runs",
                                   "prepare_simulation", "cryoem_fit", "flexibility_report", "ligand_report", "trajectory_qc",
                                   "compare_structures", "check_claims"}
    for name, w in r["workflows"].items():
        assert w["files"] and w["does"] and w["example"].startswith("vmd-agent workflow " + name)


def test_a_workflow_checks_how_many_files_it_gets_and_knows_its_name(work):
    with pytest.raises(security.InvalidInput, match="needs 2 file"):
        workflows.run_named("equilibration_check", ["only_one.pdb"], "o")
    with pytest.raises(security.InvalidInput, match="unknown workflow"):
        workflows.run_named("make_coffee", [], "o")
    out = toolset.TOOLS["run_workflow"]("make_coffee", [])
    assert out["ok"] is False and "unknown workflow" in out["error"]


@vmd
def test_equilibration_check_compares_two_engines_and_writes_a_report(work):
    r = workflows.run_named("equilibration_check", ["protein.pdb", "protein.dcd"], "eq", {})
    assert r["ok"] and [s["tool"] for s in r["steps"]] == ["inspect_files", "analyze_trajectory", "periodic_box", "measure_with_vmd"]
    both = [t for t in _texts(r) if "independent engines" in t][0]
    assert "they agree" in both                                       # the toolkit's and VMD's RMSD match to 2 %
    nums = [float(x) for x in __import__("re").findall(r"(\d+\.\d{3}) A", both)]
    assert abs(nums[0] - nums[1]) / nums[0] < 0.02
    assert any("RMSD mean" in t for t in _texts(r)) and any("box volume" in t for t in _texts(r))
    assert r["finding_counts"]["problem"] == 0


@vmd
def test_the_report_is_complete_and_checkable(work):
    r = workflows.run_named("equilibration_check", ["protein.pdb", "protein.dcd"], "eq", {})
    md = open(r["report"]).read()
    html = open(r["report_html"]).read()
    for section in ("## Verdict", "## Findings", "## What was done", "## Figures", "## Methods", "## Reproduce"):
        assert section in md, section
    assert r["verdict"] in md and __import__("html").escape(r["verdict"]) in html
    for path in (PDB, DCD):                                              # the inputs are identified by checksum
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() in md
    scripts = [f for f in os.listdir(work / "eq" / "scripts")]
    assert scripts and all(s.endswith(".tcl") for s in scripts)          # the exact Tcl of the VMD steps is in the folder
    assert os.listdir(work / "eq" / "figures") and "figures/" in md and "<img" in html
    assert "VMD 1.9" in md and "DCD headers" in md                      # versions, and a caveat a tool raised
    assert r["report"].startswith(str(work))


@vmd
def test_interaction_report_finds_the_known_salt_bridge(work):
    r = workflows.run_named("interaction_report", ["protein.pdb", "protein.dcd"], "ir", {"partner": "resid 1 to 10", "step": 5})
    assert r["ok"] and any("ASP:52 - LYS:27" in t and "100%" in t for t in _texts(r, "ok"))
    assert not any("MET:1 - MET:1" in t for t in _texts(r))             # a residue "touching itself" is not an interaction
    assert any(s["label"].startswith("surface area") for s in r["steps"])


@vmd
def test_compare_runs_says_what_each_number_is_relative_to(work):
    toolset.TOOLS["convert_trajectory"]("protein.pdb", "protein.dcd", "a.dcd", first=0, last=24)
    toolset.TOOLS["convert_trajectory"]("protein.pdb", "protein.dcd", "b.dcd", first=25, last=49)
    r = workflows.run_named("compare_runs", ["protein.pdb", "a.dcd", "b.dcd"], "cmp", {})
    assert r["ok"] and len(r["steps"]) == 6
    assert any("own first frame" in t for t in _texts(r))               # RMSDs are relative to different frames: said plainly
    assert any("replicates" in t for t in _texts(r))                    # and one run each is not evidence about systems


@vmd
def test_structure_overview_reads_a_real_structure_and_flags_nothing_wrong(work):
    r = workflows.run_named("structure_overview", ["1ubq.pdb"], "ov", {"renderer": "matplotlib"})
    assert r["ok"] and r["finding_counts"]["problem"] == 0
    assert any("76 residues" in t for t in _texts(r)) and any("no chirality errors" in t for t in _texts(r))
    assert os.listdir(work / "ov" / "figures")


def test_without_vmd_the_vmd_steps_are_skipped_and_said_so(work, monkeypatch):
    from vmd_agent.vmdkit import script
    monkeypatch.setattr(script, "find_vmd", lambda hint=None: None)
    r = workflows.run_named("structure_overview", ["1ubq.pdb"], "ov", {"renderer": "matplotlib"})
    assert r["ok"] and r["finding_counts"]["problem"] == 0
    skipped = [t for t in _texts(r, "note") if t.startswith("skipped")]
    assert len(skipped) == 2 and all("needs VMD" in t for t in skipped)  # the torsion check and the structure check
    assert any("76 residues" in t for t in _texts(r))                   # everything that does not need VMD still ran


@vmd
def test_prepare_simulation_builds_checks_and_warns_about_what_it_left_out(work):
    r = workflows.run_named("prepare_simulation", ["1ubq.pdb"], "prep", {"padding": 6})
    assert r["ok"] and [s["tool"] for s in r["steps"]][-3:] == ["build_system", "prepare_namd", "write_slurm_script"]
    assert any("net charge +0.000" in t for t in _texts(r, "ok"))
    assert any("HOH" in t and "left out" in t for t in _texts(r, "warning"))        # crystal water was not parameterised
    assert any("not been run in NAMD" in t for t in _texts(r, "warning"))
    assert os.path.isfile(work / "prep" / "system" / "equilibrate.namd") and os.path.isfile(work / "prep" / "system" / "run.sbatch")
    sysm = mda.Universe(str(work / "prep" / "system" / "system_ion.psf"), str(work / "prep" / "system" / "system_ion.pdb"))
    assert abs(sysm.atoms.charges.sum()) < 0.01


@vmd
def test_cryoem_fit_recovers_a_known_displacement_and_pictures_it(work):
    u = mda.Universe(UBQ)
    p = u.select_atoms("protein")
    xyz, spacing = p.positions.astype(float), np.array([2.0] * 3)
    lo = xyz.min(0) - 20
    volume.write_dx("target.dx", maps._simulate(xyz, p.masses, tuple(np.ceil((xyz.max(0) + 20 - lo) / spacing).astype(int)), lo, spacing, 8.0),
                    lo, spacing)
    c = xyz.mean(0)
    u.atoms.positions = (Rotation.from_euler("xyz", [10, -8, 12], degrees=True).apply(u.atoms.positions - c) + c + np.array([3, -2, 2.5])).astype("float32")
    u.atoms.write("moved.pdb")
    r = workflows.run_named("cryoem_fit", ["moved.pdb", "target.dx"], "cryo", {"resolution": 8})
    assert r["ok"] and r["finding_counts"]["problem"] == 0
    assert any("0.99 after" in t for t in _texts(r, "ok"))
    fitted = mda.Universe(str(work / "cryo" / "fitted.pdb")).select_atoms("protein").positions
    assert np.sqrt(((fitted - xyz) ** 2).sum(1).mean()) < 0.5
    assert os.path.isfile(work / "cryo" / "session" / "session.tcl") and os.listdir(work / "cryo" / "figures")


def test_the_workflow_command_lists_runs_and_reports_errors_plainly(work, capsys):
    assert cli.main(["workflow"]) == 0
    assert "structure_overview" in capsys.readouterr().out
    assert cli.main(["workflow", "structure_overview", "a.pdb", "b.pdb"]) == 2
    assert "needs 1 file" in capsys.readouterr().err
    assert cli.main(["workflow", "nonsense", "x"]) == 2
    rc = cli.main(["workflow", "structure_overview", "1ubq.pdb", "--out-dir", "cli_ov", "--option", "renderer=matplotlib", "--quiet"])
    out = capsys.readouterr().out
    assert rc == 0 and "report:" in out and os.path.isfile(work / "cli_ov" / "report.md")


# ------------------------------------------------------------------ the second set of jobs
SAMPLE = os.path.join(DATA, "sample")


@vmd
def test_flexibility_report_finds_the_floppy_c_terminus_of_ubiquitin_and_a_steady_fold(work):
    r = workflows.run_named("flexibility_report", [str(work / "protein.pdb"), str(work / "protein.dcd")], str(work / "o"), {})
    assert r["facts"]["flexible_residues"][0] == 76                                          # the free C-terminal residue moves most, as it does in ubiquitin
    assert any("most flexible residues: 76" in x for x in _texts(r, "note")) and any("is steady" in x for x in _texts(r, "ok"))
    assert os.path.isfile(r["report"]) and not _texts(r, "problem")


@vmd
def test_ligand_report_finds_the_ligand_and_the_residues_that_touch_it(work):
    for f in ("sample.pdb", "sample.dcd"):
        shutil.copy(os.path.join(SAMPLE, f), work / f)
    r = workflows.run_named("ligand_report", [str(work / "sample.pdb"), str(work / "sample.dcd")], str(work / "lig"), {})
    assert r["facts"]["ligand"] == "resname LIG" and r["facts"]["touching_residues"]
    assert any("within 4 A of the protein in 100% of the frames" in x for x in _texts(r, "ok"))


def test_ligand_report_says_so_when_there_is_no_ligand(work):
    r = workflows.run_named("ligand_report", [str(work / "protein.pdb"), str(work / "protein.dcd")], str(work / "none"), {})
    assert r["verdict"] == "No ligand to report on." and any("no ligand was found" in x for x in _texts(r, "problem"))


@vmd
def test_trajectory_qc_passes_a_clean_run_and_notes_the_unchecked_time_step(work):
    r = workflows.run_named("trajectory_qc", [str(work / "protein.pdb"), str(work / "protein.dcd")], str(work / "qc"), {})
    assert any("no periodic-box jumps" in x for x in _texts(r, "ok")) and any("dt here" in x for x in _texts(r, "warning"))
    assert not _texts(r, "problem")


@vmd
def test_compare_structures_superposes_and_reports_the_rmsd(work):
    r = workflows.run_named("compare_structures", [str(work / "1ubq.pdb"), str(work / "protein.pdb")], str(work / "cmp"), {})
    assert any("RMSD is 1.2" in x for x in _texts(r)) and os.path.isfile(r["facts"]["aligned_pdb"])
    same = workflows.run_named("compare_structures", [str(work / "protein.pdb"), str(work / "protein.pdb")], str(work / "same"), {})
    assert any("RMSD is 0.00 A" in x and "very similar" in x for x in _texts(same, "ok"))


def test_check_claims_grades_each_statement_and_says_what_it_cannot_check(work):
    r = workflows.run_named("check_claims", [str(work / "protein.pdb")], str(work / "claims"),
                            {"claims": "It has one chain; It has a ligand; It has 76 residues"})
    assert any(x.startswith('supported: "It has one chain"') for x in _texts(r, "ok"))
    assert any(x.startswith('contradicted: "It has a ligand"') for x in _texts(r, "problem"))
    assert any(x.startswith('not checkable as written: "It has 76 residues"') and "What can be checked" in x for x in _texts(r, "note"))
    assert r["verdict"].startswith("1 of 3 statement(s) supported, 1 contradicted")


def test_check_claims_reads_a_file_of_statements_only_from_inside_the_files_folder(work, tmp_path_factory):
    (work / "statements.txt").write_text("# statements\nIt has one chain\n")
    r = workflows.run_named("check_claims", [str(work / "protein.pdb")], str(work / "c2"), {"claims_file": str(work / "statements.txt")})
    assert r["verdict"].startswith("1 of 1 statement(s) supported")
    outside = tmp_path_factory.mktemp("elsewhere") / "s.txt"
    outside.write_text("It has one chain\n")
    with pytest.raises(security.SecurityError):
        workflows.run_named("check_claims", [str(work / "protein.pdb")], str(work / "c3"), {"claims_file": str(outside)})
    assert workflows.run_named("check_claims", [str(work / "protein.pdb")], str(work / "c4"), {})["verdict"] == "Nothing to check."


def test_a_job_stops_before_any_work_when_a_file_is_missing_or_the_files_are_the_wrong_way_round(work):
    with pytest.raises(security.InvalidInput, match="was not found"):
        workflows.run_named("trajectory_qc", [str(work / "nope.pdb"), str(work / "protein.dcd")], str(work / "o"), {})
    with pytest.raises(security.InvalidInput, match="wrong way round"):
        workflows.run_named("equilibration_check", [str(work / "protein.dcd"), str(work / "protein.pdb")], str(work / "o"), {})
    with pytest.raises(security.InvalidInput, match="not a density map"):
        workflows.run_named("cryoem_fit", [str(work / "protein.pdb"), str(work / "protein.pdb")], str(work / "o"), {})
    r = toolset.TOOLS["run_workflow"](name="equilibration_check", files=["protein.dcd", "protein.pdb"], out_dir=str(work / "o2"))
    assert r["ok"] is False and "wrong way round" in r["error"] and not (work / "o2").exists()                  # nothing was written
