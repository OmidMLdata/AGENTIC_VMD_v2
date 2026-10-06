"""Recipe generation and the automatic representation policy."""
import os
import pytest
from vmd_agent.structure.detect import detect_system


def test_recipe_summary_reflects_focus_and_plddt(ubq):
    """Regression: representations_added ignored focus/pLDDT/explicit reps."""
    from vmd_agent.visual.recipes import generate_visualization_recipe
    det = detect_system(ubq)
    assert "Tube" in str(generate_visualization_recipe(det, focus="fold")
                         ["representations_added"])
    assert "Beta" in str(generate_visualization_recipe(det, plddt_coloring=True)
                         ["representations_added"])
    assert "QuickSurf" in str(generate_visualization_recipe(
        det, representation="QuickSurf")["representations_added"])


def test_recipe_uses_catch_for_glsl_and_absolute_paths(ubq, tmp_path):
    from vmd_agent.visual.recipes import generate_visualization_recipe
    tcl = generate_visualization_recipe(detect_system(ubq))["tcl"]
    assert "catch {display rendermode GLSL}" in tcl
    assert os.path.abspath(ubq) in tcl


def test_mmcif_extension_maps_to_vmd_pdbx():
    from vmd_agent.visual.recipes import _mtype
    assert _mtype("x.mmcif") == "pdbx" and _mtype("x.cif") == "pdbx"


@pytest.mark.parametrize("n_res,n_chains,n_atoms,plddt,focus,expect", [
    (12, 1, 100, False, "overview", ("Licorice", "Name")),      # peptide < 20
    (120, 1, 1000, False, "overview", ("NewCartoon", "Structure")),
    (120, 2, 2000, False, "overview", ("NewCartoon", "Chain")),
    (120, 1, 400000, False, "overview", ("QuickSurf", "Chain")),
    (120, 1, 1000, True, "overview", ("NewCartoon", "Beta")),   # AlphaFold
    (120, 1, 1000, False, "fold", ("Tube", "Structure")),
    (120, 3, 1000, False, "fold", ("Tube", "Chain")),
    (120, 1, 1000, False, "surface", ("Surf", "ResType")),
    (120, 1, 300000, False, "surface", ("QuickSurf", "Chain")),
    (120, 1, 1000, False, "performance", ("Lines", "Name")),
])
def test_auto_representation_policy(n_res, n_chains, n_atoms, plddt, focus,
                                    expect):
    from vmd_agent.visual.recipes import _auto_protein_reps
    det = {"n_atoms": n_atoms, "components": {"protein": {
        "present": True, "n_residues": n_res,
        "chains": [chr(65 + i) for i in range(n_chains)]}}}
    got = _auto_protein_reps(det, plddt, focus)
    assert got[0][:2] == expect


def test_pocket_focus_is_cartoon_plus_transparent_surface(ubq):
    from vmd_agent.visual.recipes import generate_visualization_recipe
    tcl = generate_visualization_recipe(detect_system(ubq), focus="pocket")["tcl"]
    assert "NewCartoon" in tcl and "mol material Transparent" in tcl


def test_suitability_warnings(ubq):
    from vmd_agent.visual.representations import check_suitability
    det = {"n_atoms": 500000, "components": {"protein": {"present": True,
                                                         "n_residues": 8}}}
    w = " ".join(check_suitability("NewCartoon", det) + check_suitability("Surf", det)
                 + check_suitability("MSMS", det))
    assert "only 8 residues" in w and "slow above" in w and "msms" in w.lower()


# ------------------------------------ audit: values that reach the Tcl recipe
def _det(ligand="resname LIG"):
    return {"suggested_selections": {"protein": "protein", "ligand": ligand},
            "components": {"protein": {"chains": [], "n_residues": 50,
                                       "present": True}},
            "n_atoms": 500, "topology": "/data/a.pdb", "system_type": "t"}


def test_unknown_or_hostile_representation_is_rejected():
    from vmd_agent.security import InvalidInput
    from vmd_agent.visual.recipes import generate_visualization_recipe
    for bad in ("Lines} ; exec touch /tmp/x ; {", "NotARepresentation"):
        with pytest.raises(InvalidInput):
            generate_visualization_recipe(_det(), representation=bad)


def test_hostile_colour_method_and_selection_are_rejected():
    from vmd_agent.security import SecurityError
    from vmd_agent.visual.recipes import generate_visualization_recipe
    with pytest.raises(SecurityError):
        generate_visualization_recipe(_det(), color_method="Name} ; exec ls")
    with pytest.raises(SecurityError):
        generate_visualization_recipe(_det("resname x} ; exec touch /tmp/x ; {"))


def test_recipe_comments_cannot_start_new_commands():
    from vmd_agent.visual.recipes import _rep_block
    block = _rep_block("protein", "Lines", "Name", "Opaque",
                       "harmless\nexec touch /tmp/x")
    assert all(not l.lstrip().startswith("exec") for l in block.splitlines())


def test_valid_recipes_are_unchanged_by_the_hardening(ubq):
    from vmd_agent.structure.detect import detect_system
    from vmd_agent.visual.recipes import generate_visualization_recipe
    tcl = generate_visualization_recipe(detect_system(ubq),
                                        representation="QuickSurf",
                                        color_method="ColorID 6")["tcl"]
    assert "mol representation QuickSurf" in tcl and "mol color ColorID 6" in tcl


def test_params_for_and_describe_agree():
    from vmd_agent.visual.representations import (
        REPRESENTATIONS, params_for, describe_representation)
    assert params_for("NewCartoon") == REPRESENTATIONS["NewCartoon"]["params"]
    assert params_for("NoSuchStyle") == ""
    assert describe_representation("newcartoon")["vmd_command"].endswith(
        params_for("NewCartoon"))
