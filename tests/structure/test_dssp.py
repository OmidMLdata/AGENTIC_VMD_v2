"""DSSP validated three independent ways:
1. NeRF-built ideal helix / strand geometry (no data files involved),
2. ubiquitin and lysozyme, whose secondary structure is textbook,
3. structural invariants (no H-bonds -> no helix)."""
import MDAnalysis as mda

from vmd_agent.structure.dssp import (
    assign_dssp, three_state, secondary_structure_fractions,
)


def _codes(path):
    u = mda.Universe(path)
    return assign_dssp(u.atoms)["codes"]


def test_ideal_alpha_helix_is_helix(helix_pdb):
    codes = _codes(helix_pdb)
    assert len(codes) == 24
    assert codes.count("H") >= 16                    # termini cannot be H
    assert "E" not in codes


def test_ideal_strand_has_no_helix(strand_pdb):
    assert "H" not in _codes(strand_pdb)


def test_three_state_collapse():
    assert three_state("HGIEB-TS?") == "HHHEECCCC"


def test_ubiquitin_matches_published_secondary_structure(ubq):
    f = secondary_structure_fractions(mda.Universe(ubq).atoms)
    codes = f["codes"]
    # published: helix 23-34, strands 1-7 / 10-17 / 40-45 / 66-72
    assert sum(c in "H" for c in codes[22:34]) >= 10
    assert sum(c in "E" for c in codes[1:7]) >= 4
    assert sum(c in "E" for c in codes[65:72]) >= 4
    assert 20 <= f["helix_percent"] <= 28
    assert 28 <= f["sheet_percent"] <= 40


def test_lysozyme_is_alpha_rich(lyz):
    f = secondary_structure_fractions(mda.Universe(lyz).atoms)
    assert 35 <= f["helix_percent"] <= 48
    assert f["sheet_percent"] < 15


def test_hemoglobin_is_almost_all_helix(hbb):
    f = secondary_structure_fractions(mda.Universe(hbb).atoms)
    assert f["helix_percent"] > 70 and f["sheet_percent"] < 5


def test_source_is_labelled(ubq):
    f = secondary_structure_fractions(mda.Universe(ubq).atoms)
    assert "DSSP" in f["source"]


def test_empty_selection():
    u = mda.Universe.empty(3, trajectory=True)
    u.add_TopologyAttr("names", ["C1", "C2", "C3"])
    u.add_TopologyAttr("resnames", ["LIG"])
    assert assign_dssp(u.atoms)["codes"] == ""


def test_parallel_sheet_is_recognised():
    """Guards the parallel-bridge convention (found by mutation testing: the
    antiparallel-only tests could not see it break)."""
    import numpy as np
    from vmd_agent.bench import synth

    def parallel(m, length, dy, shift):
        base = synth._oriented(synth.backbone_coords(length, -120.0, 130.0),
                               [1.0, 0, 0])
        out = []
        for i in range(m):
            P = base.copy()
            P[:, :, 0] += shift * (i % 2)
            P[:, :, 1] += i * dy
            out.append(P)
        return out

    best = max(synth._dssp_codes([r for P in parallel(4, 8, dy, float(sh))
                                  for r in P]).count("E")
               for dy in (4.4, 4.8, 5.2, 5.6) for sh in np.arange(-4, 4.01, 0.5))
    assert best >= 10            # 16 of 32 with the correct convention, 0 with the wrong one
