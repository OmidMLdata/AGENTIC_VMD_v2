import numpy as np
import pytest

from vmd_agent.evidence import claims
from vmd_agent.evidence.claims import parse_claim_text as P, verify_claims, _sasa, SUPPORTED, CONTRADICTED, UNVERIFIABLE, UNPARSED


# ----------------------------------------------------------------- parsing
@pytest.mark.parametrize("text,expect", [
    ("The protein has no ligand", {"type": "has_component", "present": False,
                                   "component": "ligands_or_other"}),
    ("The protein contains a ligand", {"type": "has_component", "present": True,
                                       "component": "ligands_or_other"}),
    ("It has a lipid membrane", {"type": "has_component", "component": "lipid"}),
    ("Hemoglobin has four chains", {"type": "n_chains", "value": 4}),
    ("It is a dimer", {"type": "n_chains", "value": 2}),
    ("It has 4 disulfide bridges", {"type": "n_disulfides", "value": 4}),
    ("There are no disulfide bonds", {"type": "n_disulfides", "value": 0}),
    ("The structure is mostly helical", {"type": "secondary_structure",
                                         "kind": "helix", "op": "majority"}),
    ("The ligand is buried in a pocket", {"type": "ligand_buried"}),
    ("The system is stable and equilibrated", {"type": "rmsd_stable"}),
    ("The protein compacts over time", {"type": "rg_change",
                                         "direction": "compaction"}),
    ("The protein unfolds", {"type": "rg_change", "direction": "expansion"}),
    ("The ligand stays bound throughout", {"type": "contact_persists"}),
])
def test_parses_known_sentences(text, expect):
    got = P(text)
    for k, v in expect.items():
        assert got[k] == v, (text, got)


def test_unrecognised_sentence_is_unparsed_not_guessed():
    assert P("There is a cat in the box")["type"] is None


def test_structured_claims_pass_through():
    assert claims.normalise({"type": "n_chains", "value": 2})["value"] == 2


# ------------------------------------------------------- static verification
def verdicts(topology, sentences, **kw):
    r = verify_claims(topology, sentences, **kw)
    return [x["verdict"] for x in r["results"]], r


def test_lysozyme_claims(lyz):
    v, r = verdicts(lyz, ["Lysozyme has one chain", "It has 4 disulfide bridges",
                          "It has 3 disulfide bonds", "It is mostly helical",
                          "It has a membrane", "It contains no ligand"])
    assert v == [SUPPORTED, SUPPORTED, CONTRADICTED, SUPPORTED, CONTRADICTED,
                 SUPPORTED]
    assert r["contradiction_rate"] == pytest.approx(2 / 6)


def test_mostly_helical_ignores_coil_as_a_competitor(lyz):
    """Coil (48 %) must not beat helix (42 %) and refute 'mostly helical' for the
    textbook alpha-rich lysozyme."""
    r = verify_claims(lyz, ["The protein is mostly helical"])
    assert r["results"][0]["verdict"] == SUPPORTED
    assert "coil excluded" in r["results"][0]["criterion"]


def test_mixed_alpha_beta(ubq):
    assert verdicts(ubq, [{"type": "secondary_structure", "kind": "mixed",
                           "op": "mixed"}])[0] == [SUPPORTED]
    assert verdicts(ubq, ["The protein is mostly helical"])[0] == [CONTRADICTED]


def test_hemoglobin_chains_and_heme(hbb):
    v, _ = verdicts(hbb, ["Hemoglobin has four chains", "It has two chains",
                          "It contains a ligand"])
    assert v == [SUPPORTED, CONTRADICTED, SUPPORTED]


def test_ligand_buried_heme_supported_but_threshold_matters(hbb):
    assert verdicts(hbb, ["The ligand is buried in a pocket"])[0] == [SUPPORTED]
    strict = verify_claims(hbb, [{"type": "ligand_buried",
                                  "min_fraction": 0.95}])
    assert strict["results"][0]["verdict"] == CONTRADICTED
    ev = strict["results"][0]["evidence"]
    assert 0.5 < ev["buried_fraction"] < 0.95


def test_unparsed_and_dynamics_without_trajectory(ubq):
    v, r = verdicts(ubq, ["There is a cat in the box", "The system is stable"])
    assert v == [UNPARSED, UNVERIFIABLE]
    assert r["contradiction_rate"] is None          # nothing checkable
    assert "no trajectory" in r["results"][1]["explanation"]


def test_unreadable_system_is_unverifiable_not_a_crash():
    r = verify_claims("/nonexistent.pdb", ["It has one chain"])
    assert r["results"][0]["verdict"] == UNVERIFIABLE


def test_counts_and_note(lyz):
    r = verify_claims(lyz, ["one chain", "a cat"])
    assert r["counts"] == {SUPPORTED: 1, CONTRADICTED: 0, UNVERIFIABLE: 0,
                           UNPARSED: 1}
    assert "not that the claim is true in general" in r["note"]


# ------------------------------------------------------------------ dynamics
def test_contact_persistence_on_trajectory(sample):
    pdb, dcd = sample
    r = verify_claims(pdb, [{"type": "contact_persists", "sel1":
                             "resname LIG", "sel2": "protein", "cutoff": 6.0,
                             "min_fraction": 0.9}], dcd)
    assert r["results"][0]["verdict"] == SUPPORTED
    far = verify_claims(pdb, [{"type": "contact_persists", "sel1":
                               "resname LIG", "sel2": "resname NA",
                               "cutoff": 1.0}], dcd)
    assert far["results"][0]["verdict"] == CONTRADICTED


def test_short_trajectory_stability_claim_is_unverifiable(sample):
    """8 frames cannot support 'stable'; the layer must not rubber-stamp it."""
    pdb, dcd = sample
    r = verify_claims(pdb, ["The system is stable"], dcd)
    assert r["results"][0]["verdict"] == UNVERIFIABLE


def test_rg_change_claim_unverifiable_when_too_short(sample):
    pdb, dcd = sample
    r = verify_claims(pdb, [{"type": "rg_change", "direction": "compaction"}],
                      dcd)
    assert r["results"][0]["verdict"] in (UNVERIFIABLE, CONTRADICTED)


# ------------------------------------------------------------------ SASA
def test_sasa_of_isolated_sphere_matches_analytic():
    r, probe = 1.7, 1.4
    got = _sasa(np.zeros((1, 3)), np.array([r]), probe=probe)
    assert got == pytest.approx(4 * np.pi * (r + probe) ** 2, rel=1e-6)


def test_sasa_of_two_overlapping_spheres_is_smaller_than_sum():
    xyz = np.array([[0, 0, 0], [1.5, 0, 0]], float)
    both = _sasa(xyz, np.array([1.7, 1.7]))
    single = _sasa(xyz[:1], np.array([1.7]))
    assert both < 2 * single and both > single


def test_fully_enclosed_atom_is_buried():
    rng = np.random.default_rng(0)
    pts = rng.normal(size=(200, 3))
    pts = pts / np.linalg.norm(pts, axis=1)[:, None] * 3.0     # shell radius 3
    centre = np.zeros((1, 3))
    alone = _sasa(centre, np.array([1.7]))
    shielded = _sasa(centre, np.array([1.7]), pts, np.full(200, 1.7))
    assert shielded < 0.05 * alone


# ------------------------------------------------------------ audit fixes
@pytest.mark.parametrize("sentence", [
    "The ligand binds near the active-site loop of chain B",
    "The protein has a long helix between residues 40 and 60",
    "Water molecules bridge the ligand and Asp 52",
    "The membrane is 4 nm thick",
    "The membrane is intact",
    "The protein is stable for 40 ns",
    "The protein has a ligand and water",
    "The two chains are identical",
])
def test_sentences_that_say_more_than_can_be_checked_are_not_parsed(sentence):
    """These must not collapse to 'has water' / 'has lipid' and be SUPPORTED."""
    assert P(sentence)["type"] is None


@pytest.mark.parametrize("sentence", [
    "The protein has no ligand", "It has 4 disulfide bridges",
    "Hemoglobin has four chains", "The structure is mostly helical",
    "The ligand is buried in a pocket", "The system is stable and equilibrated",
    "The protein compacts over time", "The ligand stays bound throughout",
])
def test_plain_sentences_still_parse(sentence):
    assert P(sentence)["type"] is not None


def test_overlong_sentence_is_refused_quickly():
    import time
    t = time.time()
    c = P("a" * 50000)
    assert time.time() - t < 0.5 and c["type"] is None and "longer than" in c["note"]


def test_unparsed_result_explains_why(lyz):
    r = verify_claims(lyz, ["The membrane is intact"])["results"][0]
    assert r["verdict"] == UNPARSED and "says more than can be checked" in r["explanation"]


def _ss(helix, sheet):
    return {"helix_percent": helix, "sheet_percent": sheet,
            "coil_percent": 100 - helix - sheet, "source": "DSSP"}


@pytest.mark.parametrize("helix,sheet,verdict", [
    (45, 5, SUPPORTED), (30, 5, SUPPORTED), (29, 5, CONTRADICTED),
    (20, 2, CONTRADICTED),          # larger than sheet but below the 30 % floor
    (40, 45, CONTRADICTED),         # not larger than the sheet fraction
])
def test_mostly_helical_boundaries(helix, sheet, verdict):
    """The decision is a pure function of the measured percentages."""
    from vmd_agent.evidence.claims import _secondary_structure_verdict
    r = _secondary_structure_verdict(
        {"type": "secondary_structure", "kind": "helix", "op": "majority",
         "text": "x"}, _ss(helix, sheet))
    assert r["verdict"] == verdict


def test_secondary_structure_verdict_on_a_real_structure(lyz):
    """End to end on real lysozyme: helix is not the majority class by the
    toolkit's own DSSP, and the verdict is traceable to those fractions."""
    r = verify_claims(lyz, [{"type": "secondary_structure", "kind": "helix",
                             "op": "majority", "text": "mostly helical"}])
    res = r["results"][0]
    ev = res["evidence"]
    expected = (ev["helix_percent"] >= 30 and
                ev["helix_percent"] > ev["sheet_percent"])
    assert (res["verdict"] == SUPPORTED) == expected


def test_non_sentence_claims_are_unparsed_not_a_crash():
    """verify_claims(['', None, 3, {...}]) must not raise on None."""
    r = verify_claims(_any_structure(),
                      ["", None, 3, {"x": 1}, {"type": "n_chains"}])
    assert r["n_claims"] == 5 == sum(r["counts"].values())
    assert r["results"][1]["verdict"] == UNPARSED
    assert "not NoneType" in r["results"][1]["explanation"]


def _any_structure():
    import os
    return os.path.join(os.path.dirname(__file__), "..", "data", "1ubq.pdb")
