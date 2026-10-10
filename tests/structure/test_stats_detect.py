import numpy as np
import pytest
from vmd_agent.bench import synth
from vmd_agent.structure.detect import detect_system
from vmd_agent.structure.stats import (
    structure_stats, stats_caption, count_hydrogen_bonds,
)


# ------------------------------------------------------------------ detect
def test_sample_components(sample):
    pdb, dcd = sample
    d = detect_system(pdb, dcd)
    c = d["components"]
    assert c["protein"]["present"] and c["protein"]["n_residues"] == 12
    assert c["ions"]["resnames"] == ["CL", "NA"]
    assert c["water"]["n_molecules"] == 6
    assert c["ligands_or_other"]["resnames"] == ["LIG"]
    assert d["system_type"] == "protein-ligand complex"
    assert d["n_frames"] == 8


def test_real_structure_types(ubq, hbb):
    assert detect_system(ubq)["system_type"] == "protein (solvated)"
    d = detect_system(hbb)
    assert d["system_type"] == "protein-ligand complex"
    assert len(d["components"]["protein"]["chains"]) == 4
    assert "HEM" in d["components"]["ligands_or_other"]["resnames"]


def test_sulfur_rich_protein_is_not_a_material(write_pdb):
    """'S' (sulfur) does not make a protein a material at >= 50 atoms."""
    atoms = []
    for i in range(60):                       # 60 isolated S atoms in LIG residues
        atoms.append(("S1", "LIG", 100 + i, "L", i * 4.0, 0.0, 0.0, "S"))
    for r in range(1, 6):
        for k, n in enumerate(("N", "CA", "C", "O")):
            atoms.append((n, "ALA", r, "A", r * 3.8, k * 1.2, 0.0, n[0]))
    d = detect_system(write_pdb(atoms))
    assert not d["components"]["material_inorganic"]["present"]
    assert d["system_type"] != "hybrid bio-material"


def test_metal_slab_is_still_a_material(write_pdb):
    atoms = [("AU", "AUU", i + 1, "M", (i % 10) * 2.9, (i // 10) * 2.9, 0.0, "AU")
             for i in range(80)]
    d = detect_system(write_pdb(atoms))
    assert d["components"]["material_inorganic"]["present"]
    assert d["system_type"] == "material/inorganic"


def test_missing_file_is_reported():
    assert "error" in detect_system("/nonexistent.pdb")


# ------------------------------------------------------------------- stats
def test_partial_conect_bonds_are_supplemented(lyz):
    """A PDB with only CONECT records is not counted as '4 bonds'."""
    st = structure_stats(lyz)
    assert st["bonds_explicit"] < 50
    assert st["n_bonds"] > 900
    assert "partial" in st["bond_source"].lower()
    assert st["n_disulfide_bridges"] == 4
    assert st["bonds_by_element_pair"]["C-S"] >= 10


def test_no_bond_records_means_inferred(ubq):
    st = structure_stats(ubq)
    assert "distance-based" in st["bond_source"]
    assert 1.5 < st["mean_bonds_per_atom"] < 2.1


def test_free_ions_form_no_bonds(sample):
    pdb, _ = sample
    st = structure_stats(pdb)
    assert not any(k in st["bonds_by_element_pair"] for k in ("CL-NA", "NA-NA"))


def test_secondary_structure_in_stats(lyz):
    ss = structure_stats(lyz)["secondary_structure"]
    assert ss["helix_percent"] > 35 and "DSSP" in ss["source"]


def _water_dimer_like(hx, hy, ox, oy):
    return [("N", "ALA", 1, "A", 0.0, 0.0, 0.0, "N"),
            ("H", "ALA", 1, "A", hx, hy, 0.0, "H"),
            ("O", "ALA", 5, "A", ox, oy, 0.0, "O")]


def test_hbond_counts_linear_geometry(write_pdb):
    import MDAnalysis as mda
    u = mda.Universe(write_pdb(_water_dimer_like(1.0, 0.0, 2.9, 0.0)))
    n, method, _ = count_hydrogen_bonds(u.atoms)
    assert (n, method) == (1, "angle")


def test_hbond_rejects_bad_angle(write_pdb):
    """H...A = 1.9 Å (short enough) but the D-H...A angle is 90 degrees."""
    import MDAnalysis as mda
    u = mda.Universe(write_pdb(_water_dimer_like(1.0, 0.0, 1.0, 1.9)))
    n, method, _ = count_hydrogen_bonds(u.atoms)
    assert (n, method) == (0, "angle")


def test_hbond_rejects_long_distance(write_pdb):
    import MDAnalysis as mda
    u = mda.Universe(write_pdb(_water_dimer_like(1.0, 0.0, 4.5, 0.0)))
    assert count_hydrogen_bonds(u.atoms)[0] == 0


def test_hbond_without_hydrogens_is_labelled_distance_only(write_pdb):
    import MDAnalysis as mda
    atoms = [("N", "ALA", 1, "A", 0.0, 0.0, 0.0, "N"),
             ("O", "ALA", 5, "A", 2.9, 0.0, 0.0, "O")]
    u = mda.Universe(write_pdb(atoms))
    n, method, desc = count_hydrogen_bonds(u.atoms)
    assert method == "distance_only" and "overestimates" in desc


def test_same_residue_pairs_are_not_hbonds(write_pdb):
    import MDAnalysis as mda
    atoms = [("N", "ALA", 1, "A", 0.0, 0.0, 0.0, "N"),
             ("H", "ALA", 1, "A", 1.0, 0.0, 0.0, "H"),
             ("O", "ALA", 1, "A", 2.9, 0.0, 0.0, "O")]
    assert count_hydrogen_bonds(mda.Universe(write_pdb(atoms)).atoms)[0] == 0


def test_salt_bridge_counted_per_residue_pair(write_pdb):
    atoms = [("NZ", "LYS", 1, "A", 0.0, 0.0, 0.0, "N"),
             ("OD1", "ASP", 2, "A", 3.0, 0.0, 0.0, "O"),
             ("OD2", "ASP", 2, "A", 3.0, 1.0, 0.0, "O"),     # same pair, no double count
             ("OE1", "GLU", 3, "A", 30.0, 0.0, 0.0, "O")]    # far away
    st = structure_stats(write_pdb(atoms))
    assert st["n_salt_bridges"] == 1


def test_caption_labels_distance_only_hbonds(ubq):
    cap = " ".join(stats_caption(structure_stats(ubq)))
    assert "overestimates" in cap and "DSSP" in cap


def test_caption_is_empty_on_error():
    assert stats_caption({"error": "x"}) == []


def test_hbond_cutoff_is_honoured_not_swallowed(ubq):
    """The original API took hbond_cutoff; it must change the result (it used
    to disappear into an ignored **kwargs)."""
    loose = structure_stats(ubq, hbond_cutoff=3.5)
    tight = structure_stats(ubq, hbond_cutoff=2.7)
    assert tight["n_hydrogen_bonds"] < loose["n_hydrogen_bonds"]
    assert "2.7" in tight["hbond_criterion"]
    assert structure_stats(ubq)["n_hydrogen_bonds"] == loose["n_hydrogen_bonds"]
    with pytest.raises(TypeError):
        structure_stats(ubq, not_a_real_option=1)


# ------------------------------------------------ chain counting (benchmark-found)
def test_ligand_chain_is_not_counted_as_a_protein_chain(tmp_path):
    """A ligand on chain 'L' does not make a 3-chain protein read as 4 chains in the figure panel."""
    from vmd_agent.structure.stats import structure_stats, stats_caption
    spec = {"fold": "helical", "n_chains": 3, "ligand": "exposed",
            "n_disulfides": 0}
    atoms, _ = synth.assemble(spec, np.random.default_rng(0))
    p = synth.write_pdb(atoms, str(tmp_path / "x.pdb"))
    st = structure_stats(p)
    assert st["n_protein_chains"] == 3 and st["n_chains_all"] == 4
    assert "3 protein chains" in stats_caption(st)[0]


def test_real_structure_chain_caption(hbb):
    from vmd_agent.structure.stats import structure_stats, stats_caption
    assert "4 protein chains" in stats_caption(structure_stats(hbb))[0]
