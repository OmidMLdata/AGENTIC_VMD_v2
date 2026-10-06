"""Hostile or malformed structure files must neither run code nor crash."""
import os

import pytest

from vmd_agent.auto import visualize_and_interpret
from vmd_agent.structure.detect import detect_system
from vmd_agent.visual.recipes import generate_visualization_recipe
from vmd_agent.visual.renderers import MatplotlibRenderer

CIF = """data_x
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
ATOM 1 N N . ALA A 1 ? 0.0 0.0 0.0 10 A 1
ATOM 2 C CA . ALA A 1 ? 1.4 0.0 0.0 10 A 1
ATOM 3 C C . ALA A 1 ? 2.0 1.2 0.0 10 A 1
ATOM 4 O O . ALA A 1 ? 1.5 2.3 0.0 10 A 1
HETATM 5 C C1 . 'x} ; exec touch /tmp/vmd_agent_pwned2 ; {' L 2 ? 9.0 9.0 9.0 20 L 1
HETATM 6 C C2 . LIG L 3 ? 11.0 9.0 9.0 20 L 1
"""


def test_hostile_residue_name_in_mmcif_never_reaches_a_recipe(tmp_path):
    p = tmp_path / "evil.cif"
    p.write_text(CIF)
    det = detect_system(str(p))
    assert "error" not in det
    assert det["components"]["ligands_or_other"]["resnames"] == ["LIG"]
    assert any("unusual characters" in w for w in det["warnings"])
    tcl = generate_visualization_recipe(det)["tcl"]
    assert "exec" not in tcl and "pwned" not in tcl


def test_full_pipeline_on_hostile_mmcif_writes_a_clean_recipe(tmp_path):
    p = tmp_path / "evil.cif"
    p.write_text(CIF)
    pkg = visualize_and_interpret(str(p), out_dir=str(tmp_path / "o"),
                                  renderer="matplotlib", views=("front",))
    assert pkg["ok"]
    recipe = open(pkg["recipe_path"]).read()
    assert "exec" not in recipe and not os.path.exists("/tmp/vmd_agent_pwned2")


def _nan_pdb(tmp_path):
    p = tmp_path / "nan.pdb"
    p.write_text("ATOM      1  CA  ALA A   1         nan     nan     nan  1.00  0.00           C\nEND\n")
    return str(p)


def test_non_finite_coordinates_are_flagged(tmp_path):
    det = detect_system(_nan_pdb(tmp_path))
    assert any("non-finite" in w for w in det["warnings"])


def test_non_finite_structure_is_a_result_not_an_exception(tmp_path):
    out = MatplotlibRenderer().render_views(_nan_pdb(tmp_path),
                                            out_dir=str(tmp_path / "v"))
    assert not out["ok"] and "finite" in out["error"]
    pkg = visualize_and_interpret(_nan_pdb(tmp_path), out_dir=str(tmp_path / "o"),
                                  renderer="matplotlib", views=("front",))
    assert isinstance(pkg, dict) and not pkg.get("render_ok")


def test_partly_non_finite_structure_still_renders(helix_pdb, tmp_path):
    lines = open(helix_pdb).read().splitlines()
    lines[3] = lines[3][:30] + "     nan     nan     nan" + lines[3][54:]
    p = tmp_path / "h.pdb"
    p.write_text("\n".join(lines) + "\n")
    out = MatplotlibRenderer().render_views(str(p), out_dir=str(tmp_path / "v"),
                                            views=("front",), width=200,
                                            height=200)
    assert out["ok"]


def test_trajectory_passed_as_topology_is_an_error_not_an_exception(sample):
    """detect_system raised NoDataError for a file with no atom names, so the
    library and the MCP tool broke their 'always returns a dict' contract."""
    pdb, dcd = sample
    d = detect_system(dcd)
    assert "error" in d and "topology" in d["hint"]
    from vmd_agent.structure.stats import structure_stats
    assert "no atom or residue names" in structure_stats(dcd)["error"]
    from vmd_agent.bench.truth import ground_truth
    assert ground_truth(dcd)["ok"] is False


def test_recipe_refuses_a_system_that_did_not_load(sample):
    from vmd_agent.security import InvalidInput
    with pytest.raises(InvalidInput):
        generate_visualization_recipe(detect_system(sample[1]))
