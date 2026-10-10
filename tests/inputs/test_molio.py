"""mmCIF reading: MDAnalysis cannot, and fetch falls back to mmCIF for large
entries, so without this the fallback produced files nothing could load."""
import numpy as np

from vmd_agent.inputs.molio import load_universe, read_mmcif, is_cif

CIF = """data_TEST
#
loop_
_entity.id
_entity.type
1 polymer
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.B_iso_or_equiv
_atom_site.auth_asym_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N . ALA A 1 ? 1.0 2.0 3.0 10.0 A 1
ATOM 2 C CA . ALA A 1 ? 2.0 2.0 3.0 11.0 A 1
ATOM 3 O "O5'" . ALA A 1 ? 3.0 2.0 3.0 12.0 A 1
ATOM 4 C CB B ALA A 1 ? 9.9 9.9 9.9 13.0 A 1
HETATM 5 NA NA . NA B 2 ? 9.0 9.0 9.0 20.0 B 1
HETATM 6 O O . HOH C 3 ? 5.0 5.0 5.0 30.0 C 1
HETATM 7 O O . HOH C 4 ? 6.0 5.0 5.0 30.0 C 1
ATOM 8 N N . ALA A 1 ? 1.5 2.0 3.0 10.0 A 2
#
"""


def test_reads_atoms_residues_chains(tmp_path):
    p = tmp_path / "t.cif"
    p.write_text(CIF)
    u = read_mmcif(str(p))
    assert len(u.atoms) == 6                      # model 2 and altloc B skipped
    assert list(u.atoms.names) == ["N", "CA", "O5'", "NA", "O", "O"]
    assert list(u.residues.resnames) == ["ALA", "NA", "HOH", "HOH"]
    assert list(u.segments.segids) == ["A", "B", "C"]
    assert np.allclose(u.atoms.positions[3], [9, 9, 9])
    assert list(u.atoms.tempfactors) == [10, 11, 12, 20, 30, 30]


def test_quoted_atom_name_keeps_apostrophe(tmp_path):
    p = tmp_path / "t.cif"
    p.write_text(CIF)
    assert "O5'" in list(load_universe(str(p)).atoms.names)


def test_waters_are_separate_residues(tmp_path):
    p = tmp_path / "t.cif"
    p.write_text(CIF)
    u = load_universe(str(p))
    assert sum(r == "HOH" for r in u.residues.resnames) == 2


def test_is_cif():
    assert is_cif("a.cif") and is_cif("A.MMCIF") and not is_cif("a.pdb")


def test_detect_works_on_cif(tmp_path):
    """The mmCIF fallback must reach detection."""
    from vmd_agent.structure.detect import detect_system
    p = tmp_path / "t.cif"
    p.write_text(CIF)
    det = detect_system(str(p))
    assert "error" not in det
    assert det["components"]["water"]["n_molecules"] == 2
    assert det["components"]["ions"]["present"]


def test_pdb_still_loads_through_same_entry_point(ubq):
    assert len(load_universe(ubq).atoms) == 660
