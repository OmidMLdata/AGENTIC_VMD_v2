"""Validation of the toolkit against independent implementations: analysis
against independent NumPy, DSSP against PDB annotations and MDTraj."""
import os

import pytest
from conftest import DATA


# ----------------------------------------------- analysis vs independent NumPy
def test_cross_check_agrees_with_independent_numpy(sample):
    from vmd_agent.evidence import validation
    pdb, dcd = sample
    r = validation.cross_check(pdb, dcd, sel2="resname LIG", cutoff=6.0)
    assert r["ok"], r["rows"]
    assert {x["quantity"].split()[0] for x in r["rows"]} >= {"RMSD", "radius",
                                                             "atom", "COM"}
    assert "| quantity |" in validation.table_markdown(r)


def test_cross_check_empty_selection(sample):
    from vmd_agent.evidence import validation
    pdb, dcd = sample
    assert not validation.cross_check(pdb, dcd, selection="resname NOPE")["ok"]


# ------------------------------------------ DSSP vs PDB annotations and MDTraj
def test_pdb_record_parser(tmp_path):
    from vmd_agent.evidence.validation import parse_pdb_ss_records
    p = tmp_path / "x.pdb"
    p.write_text(
        "HELIX    1   1 ALA A    2  ALA A    5  1                                   4\n"
        "SHEET    1   A 2 ALA A   8  ALA A  10  0\n"
        "END\n")
    ref = parse_pdb_ss_records(str(p))
    assert ref == {("A", 2): "H", ("A", 3): "H", ("A", 4): "H", ("A", 5): "H",
                   ("A", 8): "E", ("A", 9): "E", ("A", 10): "E"}


@pytest.mark.parametrize("name,floor", [("1ubq", .75), ("1lyz", .65),
                                        ("4hhb", .78), ("1beb", .85)])
def test_dssp_agrees_with_pdb_annotation(name, floor):
    from vmd_agent.evidence.validation import dssp_vs_records
    r = dssp_vs_records(os.path.join(DATA, f"{name}.pdb"))
    assert r["ok"] and r["q3"] >= floor


def test_no_records_is_an_error(tmp_path):
    from vmd_agent.evidence.validation import dssp_vs_records
    p = tmp_path / "x.pdb"
    p.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\nEND\n")
    assert not dssp_vs_records(str(p))["ok"]


def test_dssp_agrees_with_an_independent_implementation():
    pytest.importorskip("mdtraj")
    from vmd_agent.evidence.validation import dssp_vs_mdtraj
    rows = [dssp_vs_mdtraj(os.path.join(DATA, f"{n}.pdb"))
            for n in ("1ubq", "1lyz", "4hhb", "1beb")]
    assert all(r["ok"] for r in rows)
    q = [r["q3_vs_mdtraj"] for r in rows]
    assert sum(q) / len(q) > 0.93 and min(q) > 0.88
