"""Procedural novel structures and generator validation."""
import json
import numpy as np
import pytest
from vmd_agent.bench import synth


def test_generation_is_deterministic(tmp_path):
    a = synth.generate_set(4, str(tmp_path / "a"), seed=5)
    b = synth.generate_set(4, str(tmp_path / "b"), seed=5)
    for x, y in zip(a, b):
        assert open(x["path"]).read() == open(y["path"]).read()
        assert x["design"] == y["design"]
    c = synth.generate_set(4, str(tmp_path / "c"), seed=6)
    assert open(a[0]["path"]).read() != open(c[0]["path"]).read()


def test_generated_files_load_and_match_design_counts(tmp_path):
    import MDAnalysis as mda
    items = synth.generate_set(10, str(tmp_path), seed=2)
    for it in items:
        u = mda.Universe(it["path"])
        d = it["design"]
        assert len(u.select_atoms("protein").segments) >= 1
        assert (len(u.select_atoms("resname LIG")) == 6) == (d["ligand"] != "none")
        assert (tmp_path / "design.json").exists()


def test_generator_matches_measured_truth(tmp_path):
    """The generator is itself validated: construction vs DSSP/SASA/geometry."""
    items = synth.generate_set(30, str(tmp_path), seed=11)
    v = synth.validate_generator(items)
    ag = v["agreement"]
    assert v["n"] == 30
    for k in ("n_chains", "has_ligand", "n_disulfides", "fold_class"):
        assert ag[k] >= 0.95, (k, ag)
    # Design intent for burial is the weakest agreement (0.67 to 0.79 on this set,
    # depending on the NumPy/Python build); the benchmark's truth is *measured*
    # from the coordinates, so this does not affect scoring. Floor, not target.
    assert ag["ligand_placement"] >= 0.6


def test_all_four_fold_classes_are_produced(tmp_path):
    from vmd_agent.bench.truth import ground_truth
    items = synth.generate_set(40, str(tmp_path), seed=4)
    classes = {ground_truth(i["path"])["fold_class"] for i in items}
    assert classes == {"alpha", "beta", "mixed", "coil"}


def test_sheet_register_search_yields_strands():
    rng = np.random.default_rng(0)
    strands = synth._strand_set(4, 7, rng)
    codes = synth._dssp_codes([r for P in strands for r in P])
    assert codes.count("E") >= 0.4 * len(codes)


def test_unknown_fold_rejected():
    with pytest.raises(ValueError):
        synth.build_fold("origami", np.random.default_rng(0))


def test_generated_structures_have_no_famous_identity(tmp_path):
    items = synth.generate_set(2, str(tmp_path), seed=0)
    text = open(items[0]["path"]).read().lower()
    assert "header" not in text and "title" not in text and "remark" not in text


def test_design_json_records_a_hash_of_every_structure(tmp_path):
    import hashlib
    items = synth.generate_set(4, str(tmp_path), seed=3)
    for it in items:
        assert it["sha256"] == hashlib.sha256(open(it["path"], "rb").read()
                                              ).hexdigest()
    saved = json.load(open(tmp_path / "design.json"))
    assert [x["sha256"] for x in saved] == [x["sha256"] for x in items]
