"""What the web page's viewer is sent: atoms, labels, bonds and frames, from the real test structures."""
import os

import numpy as np
import pytest

from vmd_agent.structure import viewer

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
UBQ = os.path.join(DATA, "1ubq.pdb")


def test_a_structure_is_described_for_drawing():
    m = viewer.Model(UBQ)
    d = m.describe()
    n = d["n_atoms"]
    assert n == d["n_atoms_total"] and not d["reduced"] and d["frames"] == 1
    assert len(d["xyz"]) == 3 * n and len(d["element"]) == len(d["restype"]) == len(d["is_ca"]) == len(d["chain"]) == n
    assert sum(d["is_ca"]) == 76 and all(d["is_protein"][i] for i, c in enumerate(d["is_ca"]) if c)      # ubiquitin: 76 residues
    assert d["chains"] and d["bond_method"].startswith("distance-based")
    pairs = np.asarray(d["bonds"])
    xyz = np.asarray(d["xyz"]).reshape(-1, 3)
    lengths = np.linalg.norm(xyz[pairs[:, 0]] - xyz[pairs[:, 1]], axis=1)
    assert 0.9 < lengths.mean() < 1.9 and lengths.max() < 3.2                                         # bonds are bond-length
    assert d["radius"] > 10 and np.allclose(np.asarray(d["centre"]), xyz.mean(0), atol=0.05)


def test_colour_labels_cover_the_residue_kinds():
    assert [viewer._restype(r) for r in ("ASP", "LYS", "SER", "ALA", "HOH", "LIG")] == [0, 1, 2, 3, 4, 5]
    assert viewer.RESTYPES == ["acidic", "basic", "polar", "nonpolar", "water", "other"]


def test_other_frames_come_in_the_same_atom_order():
    m = viewer.Model(os.path.join(DATA, "ubq_md", "protein.pdb"), os.path.join(DATA, "ubq_md", "protein.dcd"))
    d = m.describe()
    assert d["frames"] > 1
    f0, f2 = m.frame(0), m.frame(2)
    assert f0.shape == f2.shape == (d["n_atoms"], 3) and not np.allclose(f0, f2)
    assert np.allclose(m.frame(10 ** 6), m.frame(d["frames"] - 1))                                    # past the end is the last frame
    assert np.allclose(np.round(f0, 2).ravel(), d["xyz"], atol=0.006)


def test_a_big_system_is_cut_down_to_backbone_and_non_solvent_and_says_so(monkeypatch):
    monkeypatch.setattr(viewer, "FULL_LIMIT", 100)                                                     # the real structure is bigger than this
    m = viewer.Model(os.path.join(DATA, "1lyz.pdb"))
    d = m.describe()
    assert d["reduced"] and d["n_atoms"] < d["n_atoms_total"] and d["bonds"] == []
    assert sum(d["is_ca"]) == 129 and not any(d["is_water"])                                           # lysozyme: 129 residues, water dropped
    assert len(d["xyz"]) == 3 * d["n_atoms"]


def test_a_file_that_is_not_a_structure_raises_instead_of_drawing_nothing(tmp_path):
    bad = tmp_path / "x.pdb"
    bad.write_text("nothing here\n")
    with pytest.raises(Exception):
        viewer.Model(str(bad)).describe()
