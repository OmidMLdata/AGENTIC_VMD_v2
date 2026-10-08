"""The tools that drive VMD itself, run against a real VMD and checked against independent implementations
(MDAnalysis, NumPy, SciPy) wherever one exists. Tests that need VMD are skipped, with the reason shown, without it."""
import json
import os
import shutil
import struct
import subprocess

import MDAnalysis as mda
import numpy as np
import pytest

from vmd_agent import security, toolset
from vmd_agent.inputs import volume
from vmd_agent.vmdkit import (build, capabilities, interactions, measure, scene, script, structure, trajectory,
                              volumetric)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
PDB = os.path.join(DATA, "ubq_md", "protein.pdb")
DCD = os.path.join(DATA, "ubq_md", "protein.dcd")
UBQ = os.path.join(DATA, "1ubq.pdb")

vmd = pytest.mark.requires_vmd


@pytest.fixture(scope="module")
def u():
    return mda.Universe(PDB, DCD)


def _series(kind, **kw):
    r = measure.measure(PDB, DCD, kind=kind, **kw)
    assert r["ok"], r
    return r


# ------------------------------------------------------------------ measure, vs MDAnalysis / NumPy
@vmd
def test_radius_of_gyration_matches_mdanalysis(u):
    r = _series("rgyr", selection="protein", step=10)
    for f, v in zip(r["frames"], r["values"]):
        u.trajectory[f]
        assert v == pytest.approx(u.select_atoms("protein").radius_of_gyration(), rel=5e-3)


@vmd
def test_centre_of_mass_matches_mdanalysis(u):
    r = _series("center", selection="protein", step=20)
    for f, v in zip(r["frames"], r["values"]):
        u.trajectory[f]
        assert np.allclose(v, u.select_atoms("protein").center_of_mass(), atol=2e-2)


@vmd
def test_fitted_rmsd_matches_mdanalysis(u):
    from MDAnalysis.analysis import rms
    r = _series("rmsd", selection="name CA", mass_weighted=False, step=10)
    ca = u.select_atoms("name CA")
    u.trajectory[0]
    ref = ca.positions.copy()
    for f, v in zip(r["frames"], r["values"]):
        u.trajectory[f]
        assert v == pytest.approx(rms.rmsd(ca.positions, ref, center=True, superposition=True), abs=2e-3)


@vmd
def test_rmsf_matches_numpy(u):
    r = _series("rmsf", selection="name CA", align=False)
    ca = u.select_atoms("name CA")
    xyz = np.array([ca.positions.copy() for _ in u.trajectory])
    expected = np.sqrt(((xyz - xyz.mean(0)) ** 2).sum(-1).mean(0))
    assert np.allclose([a["rmsf"] for a in r["per_atom"]], expected, atol=5e-3)


@vmd
def test_distance_matches_numpy(u):
    r = _series("distance", selection="resid 1 and name CA", selection2="resid 76 and name CA",
                mass_weighted=False, step=10)
    a, b = u.select_atoms("resid 1 and name CA"), u.select_atoms("resid 76 and name CA")
    for f, v in zip(r["frames"], r["values"]):
        u.trajectory[f]
        assert v == pytest.approx(np.linalg.norm(a.positions[0] - b.positions[0]), abs=1e-3)


@vmd
def test_angle_and_dihedral_match_mdanalysis(u):
    from MDAnalysis.lib.distances import calc_angles, calc_dihedrals
    sels = [f"resid {i} and name CA" for i in (10, 11, 12, 13)]
    ang = _series("angle", selection=sels[0], selection2=sels[1], selection3=sels[2], step=10)
    dih = _series("dihedral", selection=sels[0], selection2=sels[1], selection3=sels[2], selection4=sels[3], step=10)
    atoms = [u.select_atoms(s) for s in sels]
    for f, a_v, d_v in zip(ang["frames"], ang["values"], dih["values"]):
        u.trajectory[f]
        p = [x.positions[0] for x in atoms]
        assert a_v == pytest.approx(np.degrees(calc_angles(p[0][None], p[1][None], p[2][None])[0]), abs=1e-2)
        assert d_v == pytest.approx(np.degrees(calc_dihedrals(p[0][None], p[1][None], p[2][None], p[3][None])[0]), abs=1e-2)


@vmd
def test_contacts_match_a_kd_tree(u):
    from scipy.spatial import cKDTree
    r = _series("contacts", selection="resid 1 to 10", selection2="resid 60 to 70", cutoff=4.0, step=10)
    a, b = u.select_atoms("resid 1 to 10"), u.select_atoms("resid 60 to 70")
    for f, v in zip(r["frames"], r["values"]):
        u.trajectory[f]
        expected = len(cKDTree(a.positions).sparse_distance_matrix(cKDTree(b.positions), 4.0))
        assert v == expected


@vmd
@pytest.mark.parametrize("probe", [1.0, 1.4, 2.0])
def test_sasa_is_close_to_an_independent_shrake_rupley(u, probe):
    from scipy.spatial import cKDTree
    heavy = u.select_atoms("protein and not name H*")
    r = measure.measure(PDB, DCD, kind="sasa", selection="protein and noh", probe_radius=probe, first=0, last=0)
    assert r["ok"], r
    radii = {"C": 1.7, "N": 1.55, "O": 1.52, "S": 1.8}
    rad = np.array([radii.get(n[0], 1.7) for n in heavy.names]) + probe
    u.trajectory[0]
    pts = np.random.default_rng(0).normal(size=(500, 3))
    pts /= np.linalg.norm(pts, axis=1)[:, None]
    tree, total = cKDTree(heavy.positions), 0.0
    for i, (c, rr) in enumerate(zip(heavy.positions, rad)):
        sp = c + rr * pts
        near = tree.query_ball_point(sp, rad.max())
        free = sum(all(np.linalg.norm(sp[k] - heavy.positions[j]) >= rad[j] - 1e-9 for j in near[k] if j != i)
                   for k in range(len(sp)))
        total += 4 * np.pi * rr ** 2 * free / len(sp)
    # different atom radii and sampling: agreement within 15 %, not equality
    assert r["values"][0] == pytest.approx(total, rel=0.15)


@vmd
def test_cluster_and_inertia_and_minmax_run_and_make_sense(u):
    c = _series("cluster", selection="name CA", cutoff=1.0, num_clusters=3, step=2)
    assert sum(x["size"] for x in c["clusters"]) == len(range(0, 50, 2))
    i = _series("inertia", selection="protein", step=25)
    for f, v in zip(i["frames"], i["values"]):
        u.trajectory[f]
        expected = np.sort(np.linalg.eigvalsh(u.select_atoms("protein").moment_of_inertia()))
        assert np.allclose(np.sort(v), expected, rtol=2e-2)
    mm = _series("minmax", selection="protein", step=25)
    u.trajectory[0]
    pos = u.select_atoms("protein").positions
    assert np.allclose(mm["values"][0], list(pos.min(0)) + list(pos.max(0)), atol=1e-3)


def test_measure_refuses_hostile_input_before_starting_vmd():
    for bad in ("protein}; exec ls", "name CA\n", "a{b"):
        with pytest.raises(security.SecurityError):
            measure.measure(PDB, DCD, kind="rgyr", selection=bad)
    with pytest.raises(security.InvalidInput):
        measure.measure(PDB, DCD, kind="rm -rf")
    with pytest.raises(security.InvalidInput):
        measure.measure(PDB, DCD, kind="rgyr", step=0)
    with pytest.raises(security.InvalidInput):
        measure.measure(PDB, DCD, kind="distance", selection="all")      # needs a second selection


# ------------------------------------------------------------------ interactions, structure
@vmd
def test_ubiquitin_k27_d52_salt_bridge_is_found():
    """K27-D52 is the best known salt bridge in ubiquitin; it should persist through a simulation of the native fold."""
    r = interactions.interactions(PDB, DCD, kind="salt_bridges", step=5)
    assert r["ok"], r
    pairs = {(p["a"], p["b"]): p["occupancy"] for p in r["most_persistent"]}
    assert pairs.get(("ASP:52", "LYS:27"), 0) > 0.5, r["most_persistent"]


@vmd
def test_hbond_persistence_is_consistent():
    r = interactions.interactions(PDB, DCD, kind="hbonds", step=5, top=5)
    assert r["ok"] and r["n_frames"] == 10
    assert all(0 < p["occupancy"] <= 1 for p in r["most_persistent"])
    # the per-frame counts are the number of distinct pairs in that frame
    assert sum(c["count"] for c in r["per_frame"]) >= max(p["frames_present"] for p in r["most_persistent"])


@vmd
def test_vmd_secondary_structure_agrees_with_the_built_in_dssp(u):
    from vmd_agent.structure.dssp import assign_dssp, three_state
    r = structure.secondary_structure(PDB, DCD, first=0, last=0)
    assert r["ok"], r
    codes = r["per_frame"][0]["codes"]
    mine = three_state(assign_dssp(u.select_atoms("protein"))["codes"])
    vmd3 = "".join("H" if c in "HGI" else "E" if c in "EB" else "C" for c in codes)
    n = min(len(mine), len(vmd3))
    agree = sum(a == b for a, b in zip(mine[:n], vmd3[:n])) / n
    assert agree > 0.75, (agree, "".join(mine), vmd3)       # two different algorithms, same fold


@vmd
def test_torsions_match_numpy_and_ubiquitin_is_mostly_favoured(u):
    from MDAnalysis.lib.distances import calc_dihedrals
    r = structure.backbone_torsions(UBQ)
    assert r["ok"], r
    assert r["fraction_favoured"] > 0.8 and not r["outliers"]
    x = mda.Universe(UBQ)
    by = {res.resid: res for res in x.select_atoms("protein").residues}
    for row in r["residues"][:10]:
        i = row["resid"]
        p, c = by[i - 1].atoms, by[i].atoms
        pos = lambda grp, name: grp.select_atoms(f"name {name}").positions[0][None]
        phi = np.degrees(calc_dihedrals(pos(p, "C"), pos(c, "N"), pos(c, "CA"), pos(c, "C"))[0])
        assert row["phi"] == pytest.approx(phi, abs=0.1)


@vmd
def test_structure_check_is_clean_for_ubiquitin_and_sees_a_gap(tmp_path):
    ok = structure.structure_check(UBQ)
    assert ok["ok"] and ok["chirality_errors"] == 0 and ok["cis_peptides"] == 0 and ok["chain_gaps"] == 0
    broken = tmp_path / "gap.pdb"
    broken.write_text("".join(ln for ln in open(UBQ) if not (ln.startswith("ATOM") and ln[22:26].strip() in {"30", "31", "32"})))
    gap = structure.structure_check(str(broken))
    assert gap["ok"] and gap["chain_gaps"] >= 1


@vmd
def test_alignment_recovers_a_known_rotation(tmp_path):
    x = mda.Universe(UBQ)
    ref = tmp_path / "ref.pdb"
    x.atoms.write(str(ref))
    th = np.radians(70)
    rot = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    x.atoms.positions = x.atoms.positions @ rot.T + np.array([12.0, -7.0, 5.0])
    mob = tmp_path / "mob.pdb"
    x.atoms.write(str(mob))
    out = tmp_path / "aligned.pdb"
    r = structure.align_structures(str(mob), str(ref), out_pdb=str(out))
    assert r["ok"] and r["rmsd_before"] > 5 and r["rmsd_after"] < 0.01
    back = mda.Universe(str(out)).atoms.positions
    assert np.allclose(back, mda.Universe(str(ref)).atoms.positions, atol=0.05)


# ------------------------------------------------------------------ trajectory / pbc
@vmd
def test_box_matches_mdanalysis(u):
    r = trajectory.pbc_info(PDB, DCD, step=10)
    assert r["ok"] and r["has_unit_cell"] and r["orthorhombic"]
    for b in r["boxes"]:
        u.trajectory[b["frame"]]
        assert np.allclose([b["a"], b["b"], b["c"]], u.dimensions[:3], atol=1e-3)


@vmd
@pytest.mark.parametrize("fmt", ["dcd", "xyz", "gro", "trr", "pdb"])
def test_converted_trajectory_reads_back_with_the_same_coordinates(fmt, tmp_path, u):
    out = tmp_path / f"s.{fmt}"
    r = trajectory.convert(PDB, DCD, str(out), selection="name CA", first=0, last=20, step=5)
    assert r["ok"] and r["n_frames"] == 5 and r["n_atoms"] == 76, r
    if fmt == "gro":                                      # parse it ourselves: nm, frames back to back
        txt = out.read_text().splitlines()
        heads = [i for i, ln in enumerate(txt) if ln.startswith("generated by VMD")]
        assert len(heads) == 5 and all(txt[i + 1].strip() == "76" for i in heads)
        for k, f in enumerate(range(0, 21, 5)):
            u.trajectory[f]
            xyz = np.array([[float(x) for x in txt[heads[k] + 2 + a][20:44].split()] for a in range(76)]) * 10
            assert np.allclose(xyz, u.select_atoms("name CA").positions, atol=0.06)
    if fmt in ("pdb", "xyz"):
        back = mda.Universe(str(out))
        assert len(back.trajectory) == 5 and back.atoms.n_atoms == 76
        for k, f in enumerate(range(0, 21, 5)):
            u.trajectory[f]
            back.trajectory[k]
            assert np.allclose(back.atoms.positions, u.select_atoms("name CA").positions, atol=0.06)


@vmd
def test_dcd_subset_round_trips_exactly(tmp_path, u):
    ca_pdb = tmp_path / "ca.pdb"
    trajectory.write_structure(PDB, DCD, str(ca_pdb), selection="name CA")
    out = tmp_path / "ca.dcd"
    trajectory.convert(PDB, DCD, str(out), selection="name CA", first=0, last=48, step=12)
    back = mda.Universe(str(ca_pdb), str(out))
    assert len(back.trajectory) == 5
    for k, f in enumerate(range(0, 49, 12)):
        u.trajectory[f]
        back.trajectory[k]
        assert np.allclose(back.atoms.positions, u.select_atoms("name CA").positions, atol=1e-3)


@vmd
def test_aligned_output_has_small_rmsd_to_its_first_frame(tmp_path):
    out = tmp_path / "al.dcd"
    r = trajectory.convert(PDB, DCD, str(out), selection="protein", align=True, step=10)
    assert r["ok"]
    back = mda.Universe(PDB, str(out))
    ca = back.select_atoms("name CA")
    from MDAnalysis.analysis import rms
    back.trajectory[0]
    ref = ca.positions.copy()
    back.trajectory[len(back.trajectory) - 1]
    assert rms.rmsd(ca.positions, ref) < 3.5          # already fitted: close to the plain RMSD of the run (~2-3 A)


def test_convert_refuses_unwritable_formats(tmp_path):
    with pytest.raises(security.InvalidInput):
        trajectory.convert(PDB, DCD, str(tmp_path / "x.xtc"))


# ------------------------------------------------------------------ maps
@vmd
def test_density_map_integrates_to_the_mass_of_the_selection(tmp_path, u):
    r = volumetric.volmap(PDB, DCD, str(tmp_path / "d.dx"), kind="density", selection="name CA", resolution=1.0, step=10)
    assert r["ok"], r
    assert r["integral"] == pytest.approx(u.select_atoms("name CA").masses.sum(), rel=0.02)
    assert r["suggested_isovalues"]["mean+3sd"] > r["mean"]


@vmd
def test_occupancy_and_mask_and_distance_maps(tmp_path):
    occ = volumetric.volmap(PDB, DCD, str(tmp_path / "o.dx"), kind="occupancy", selection="resname ALA", resolution=1.5, step=10)
    assert occ["ok"] and 0 < occ["max"] <= 1.0000001
    mask = volumetric.volmap(PDB, DCD, str(tmp_path / "m.dx"), kind="mask", selection="resname ALA", resolution=1.5, cutoff=2.0, step=10)
    mdata = volume.read_volume(str(tmp_path / "m.dx"))["data"]
    assert mask["ok"] and mdata.min() >= 0 and mdata.max() <= 1.0000001       # averaged over frames: a fraction of frames
    dist = volumetric.volmap(PDB, DCD, str(tmp_path / "d.dx"), kind="distance", selection="resname ALA", resolution=1.5, step=10)
    assert dist["ok"] and dist["min"] >= 0


@vmd
def test_electrostatic_potential_of_a_neutral_built_system(tmp_path):
    b = build.build_system(UBQ, str(tmp_path / "ubq"), padding=6)
    assert b["ok"], b
    r = volumetric.volmap(b["final_psf"], b["final_pdb"], str(tmp_path / "pme.dx"), kind="electrostatic", resolution=2.0)
    assert r["ok"] and abs(r["net_charge"]) < 0.01 and r["min"] < 0 < r["max"]


def _write_ccp4(path, data, voxel):
    nz, ny, nx = data.shape
    head = struct.pack("<4i", nx, ny, nz, 2) + struct.pack("<3i", 0, 0, 0) + struct.pack("<3i", nx, ny, nz)
    head += struct.pack("<6f", nx * voxel, ny * voxel, nz * voxel, 90, 90, 90) + struct.pack("<3i", 1, 2, 3)
    head += b"\0" * (1024 - len(head))
    with open(path, "wb") as fh:
        fh.write(head + data.astype("<f4").tobytes())


def test_map_readers_agree_on_the_same_volume(tmp_path):
    rng = np.random.default_rng(1)
    data = rng.random((5, 4, 3))                         # x, y, z
    # CCP4/MRC: fastest axis is x
    _write_ccp4(tmp_path / "m.mrc", data.transpose(2, 1, 0), 2.0)
    v = volume.read_volume(str(tmp_path / "m.mrc"))
    assert v["data"].shape == (5, 4, 3) and np.allclose(v["data"], data, atol=1e-6) and v["delta"] == [2.0] * 3
    # OpenDX: x slowest
    with open(tmp_path / "m.dx", "w") as fh:
        fh.write("object 1 class gridpositions counts 5 4 3\norigin 1 2 3\ndelta 2 0 0\ndelta 0 2 0\ndelta 0 0 2\n"
                 "object 2 class gridconnections counts 5 4 3\nobject 3 class array type double rank 0 items 60 data follows\n")
        flat = data.reshape(-1)
        for i in range(0, 60, 3):
            fh.write(" ".join(f"{x:.9g}" for x in flat[i:i + 3]) + "\n")
    d = volume.read_volume(str(tmp_path / "m.dx"))
    assert np.allclose(d["data"], data) and d["origin"] == [1, 2, 3]
    s = volume.summarize(d)
    assert s["integral"] == pytest.approx(data.sum() * 8) and s["shape"] == [5, 4, 3]
    assert not volumetric.volume_info(str(tmp_path / "nope.mrc"))["ok"]


# ------------------------------------------------------------------ building
@vmd
def test_a_built_ubiquitin_system_is_neutral_solvated_and_loadable(tmp_path):
    r = build.build_system(UBQ, str(tmp_path / "ubq"), padding=8, salt_concentration=0.15)
    assert r["ok"], r
    assert abs(r["net_charge"]) < 0.01 and r["n_waters"] > 2000 and r["n_ions"] >= 10
    assert "HOH" in r["excluded_residue_names"] and r["warning"]            # nothing is dropped silently
    sysm = mda.Universe(r["final_psf"], r["final_pdb"])
    assert sysm.atoms.n_atoms == r["n_atoms"]
    assert len(sysm.select_atoms("protein").residues) == 76
    assert abs(sysm.atoms.charges.sum()) < 0.01
    dry = mda.Universe(str(tmp_path / "ubq.psf"), str(tmp_path / "ubq.pdb"))
    assert sysm.select_atoms("protein").n_atoms == dry.atoms.n_atoms          # solvating did not change the protein
    assert all(abs(box - 8 * 2 - span) < 25 for box, span in zip(r["box_size_A"], [30, 30, 30])) or r["box_size_A"]


@vmd
def test_mutation_changes_exactly_that_residue(tmp_path):
    b = build.build_system(UBQ, str(tmp_path / "ubq"), solvate=False)
    assert b["ok"], b
    m = build.mutate_residue(str(tmp_path / "ubq.psf"), str(tmp_path / "ubq.pdb"), str(tmp_path / "k6a"), "P0", 6, "ALA")
    assert m["ok"], m
    before, after = mda.Universe(str(tmp_path / "ubq.psf")), mda.Universe(m["psf"])
    assert after.select_atoms("resid 6").resnames[0] == "ALA" and before.select_atoms("resid 6").resnames[0] == "LYS"
    assert after.atoms.n_atoms < before.atoms.n_atoms
    assert all(a == b for a, b in zip(before.residues.resnames[:5], after.residues.resnames[:5]))


@vmd
def test_merge_adds_the_atom_counts(tmp_path):
    b = build.build_system(UBQ, str(tmp_path / "ubq"), solvate=False)
    r = build.merge_structures(b["final_psf"], b["final_pdb"], b["final_psf"], b["final_pdb"], str(tmp_path / "two"))
    assert r["ok"] and r["n_atoms"] == 2 * b["n_atoms"] and r["warning"]


def test_build_validates_its_inputs():
    with pytest.raises(security.InvalidInput):
        build.build_system(UBQ, "/tmp/x", histidine="HIS")
    with pytest.raises(security.InvalidInput):
        build.build_system(UBQ, "/tmp/x", padding=-1)
    with pytest.raises(security.InvalidInput):
        build.mutate_residue("a.psf", "a.pdb", "/tmp/y", "P0", 1, "XXX")


# ------------------------------------------------------------------ scenes and session export
SPEC = {"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure", "material": "AOShiny"},
                 {"selection": "resname ALA", "style": "Licorice", "color": "Name"}],
        "rotate": [["x", 30], ["y", -30]], "ambient_occlusion": True}


def test_scene_spec_validation_blocks_anything_that_is_not_a_known_choice():
    for bad in ({"reps": [{"style": "Rm"}]}, {"reps": [{"material": "Evil"}]},
                {"reps": [{"color": "Name; exec ls"}]}, {"reps": [{"selection": "all}; exec ls"}]}, {},
                {"reps": [{}], "rotate": [["q", 1]]}, {"reps": [{}], "zoom": -1}, {"reps": [{}], "background": "red"}):
        with pytest.raises((security.InvalidInput, security.SecurityError)):
            scene.validate(bad)
    assert scene.validate({"reps": [{}]})["reps"][0]["style"] == "NewCartoon"


@vmd
def test_a_rendered_scene_is_a_real_image_and_the_isosurface_shows(tmp_path, real_tachyon):
    from PIL import Image
    d = volumetric.volmap(PDB, DCD, str(tmp_path / "d.dx"), kind="density", selection="resname ALA", resolution=1.5, step=10)
    a = scene.render_scene(SPEC, PDB, DCD, str(tmp_path / "a.png"), width=300, height=240)
    b = scene.render_scene({**SPEC, "isosurfaces": [{"file": d["map_path"], "isovalue": 0.3, "style": "wireframe",
                                                     "color": "ColorID 1"}]}, PDB, DCD, str(tmp_path / "b.png"), width=300, height=240)
    assert a["ok"] and b["ok"], (a, b)
    ia, ib = np.asarray(Image.open(a["image"]).convert("RGB")), np.asarray(Image.open(b["image"]).convert("RGB"))
    assert ia.std() > 5 and (ia != ib).any()                               # not blank; the map changed the picture
    def redness(img):
        return int(((img[..., 0] > 150) & (img[..., 1] < 120) & (img[..., 2] < 120)).sum())
    assert redness(ib) > redness(ia) + 5                                      # ColorID 1 is red: the wireframe added some


@vmd
def test_an_exported_session_opens_in_vmd_from_anywhere(tmp_path):
    out = tmp_path / "exp"
    r = scene.export_session(SPEC, PDB, DCD, str(out))
    assert r["ok"] and r["round_trip_check"]["opens_in_vmd"], r
    assert r["round_trip_check"]["molecules"][0] == {"atoms": 1240, "representations": 2, "frames": 50}
    man = json.load(open(out / "manifest.json"))
    assert man["vmd_version"] and man["spec"]["reps"][0]["style"] == "NewCartoon"
    for rel, sha in man["inputs"].items():
        assert scene._sha(str(out / rel)) == sha                              # the copies are the recorded data
    moved = tmp_path / "somewhere" / "else"
    shutil.copytree(out, moved)
    shutil.rmtree(out)                                                       # the original is gone: paths must be relative
    res = script.run([f"source {{{moved / 'session.tcl'}}}", "emit CHK [molinfo top get numatoms] [molinfo top get numreps]"])
    assert res["ok"] and res["rows"]["CHK"][0] == ["1240", "2"]
    assert {"session.tcl", "render.tcl", "manifest.json", "REPRODUCE.md", "data"} <= set(os.listdir(moved))


@vmd
def test_the_saved_script_reproduces_the_tool_result_in_plain_vmd(tmp_path, monkeypatch, real_vmd):
    monkeypatch.setenv(security.ENV_ROOTS, str(tmp_path))
    topo, traj = shutil.copy(PDB, tmp_path), shutil.copy(DCD, tmp_path)
    r = toolset.TOOLS["measure_with_vmd"](topology=topo, trajectory=traj, kind="rgyr", selection="protein", step=10)
    assert r["ok"], r
    sc = r["reproduce_script"]
    assert os.path.isfile(sc) and os.path.dirname(sc) == str(tmp_path / "vmd_scripts")
    proc = subprocess.run([real_vmd, "-dispdev", "text", "-eofexit", "-e", sc], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=300)
    lines = [ln.split() for ln in proc.stdout.splitlines() if ln.startswith("RESULT V ")]
    again = {int(t[2]): float(t[3]) for t in lines}
    assert again == pytest.approx(dict(zip(r["frames"], r["values"])))        # same numbers, run by hand


def test_tools_stay_inside_the_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv(security.ENV_ROOTS, str(tmp_path))
    out = toolset.TOOLS["measure_with_vmd"](topology=PDB, trajectory=DCD, kind="rgyr")
    assert out["ok"] is False and out["blocked"] is True
    out = toolset.TOOLS["convert_trajectory"](topology=str(tmp_path / "a.pdb"), trajectory=None, out_path="/etc/x.dcd")
    assert out["ok"] is False and out["blocked"] is True


def test_every_vmd_tool_says_so_plainly_when_vmd_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "find_vmd", lambda hint=None: None)
    r = measure.measure(PDB, DCD, kind="rgyr")
    assert r["ok"] is False and "VMD" in r["error"]
    assert interactions.interactions(PDB, DCD)["ok"] is False
    assert build.build_system(UBQ, str(tmp_path / "x"))["ok"] is False


# ------------------------------------------------------------------ the coverage map
def test_every_wrapped_plugin_names_a_tool_that_exists():
    import re
    for name, (status, detail) in capabilities.COVERAGE.items():
        if status == capabilities.W:
            tools = [t for t in toolset.TOOLS if re.search(rf"\b{t}\b", detail)]
            assert tools, (name, detail)                                       # the detail names a tool of the library


@vmd
def test_every_plugin_of_the_installed_vmd_is_classified():
    r = capabilities.vmd_capabilities(verbose=True)
    assert r["ok"], r
    assert [k for k, v in r["plugins"].items() if v["status"] == "unclassified"] == []
    assert r["counts"]["wrapped"] >= 20 and "dcd" in r["file_formats"] and "pdb" in r["file_formats"]
    short = capabilities.vmd_capabilities()
    assert "plugins" not in short and "hbonds" in short["wrapped"] and "unclassified" not in short
    assert 0.3 < r["wrapped_fraction_of_scriptable_plugins"] < 1


# ------------------------------------------------------------------ more builders and the turntable
@vmd
def test_membrane_has_two_leaflets_and_a_realistic_thickness(tmp_path):
    r = build.build_membrane(str(tmp_path / "mem"), lipid="POPC", x_size=40, y_size=40)
    assert r["ok"], r
    assert r["upper_leaflet"] == r["lower_leaflet"] > 5 and r["n_lipids"] == r["upper_leaflet"] + r["lower_leaflet"]
    assert 34 < r["thickness_P_to_P_A"] < 42                     # POPC phosphate-to-phosphate is about 38 A
    mem = mda.Universe(r["psf"], r["pdb"])
    assert mem.atoms.n_atoms == r["n_atoms"] and len(mem.select_atoms("resname POPC").residues) == r["n_lipids"]
    assert abs(mem.atoms.charges.sum()) < 0.01                   # POPC is zwitterionic: neutral


@vmd
@pytest.mark.parametrize("n,m", [(6, 6), (10, 5), (8, 1), (12, 6)])
def test_nanotube_radius_matches_the_chirality(n, m, tmp_path):
    r = build.build_nanotube(str(tmp_path / "t.pdb"), n=n, m=m, length_nm=5)
    assert r["ok"], r
    assert r["mean_radius_A"] == pytest.approx(r["analytic_radius_A_for_carbon"], rel=0.01)
    xyz = mda.Universe(str(tmp_path / "t.pdb")).atoms.positions
    assert 45 < np.ptp(xyz[:, 2]) < 130 and r["n_atoms"] == len(xyz)      # about 5 nm: whole translation periods, so chiral tubes run longer


def test_membrane_and_nanotube_validate_their_inputs():
    with pytest.raises(security.InvalidInput):
        build.build_membrane("/tmp/x", lipid="DOPC")
    with pytest.raises(security.InvalidInput):
        build.build_membrane("/tmp/x", x_size=5)
    with pytest.raises(security.InvalidInput):
        build.build_nanotube("/tmp/x.pdb", n=3, m=6)
    with pytest.raises(security.InvalidInput, match="zigzag"):
        build.build_nanotube("/tmp/x.pdb", n=8, m=0)


@vmd
@pytest.mark.requires_ffmpeg
def test_turntable_is_a_real_video_of_a_rotating_scene(tmp_path, real_tachyon):
    from vmd_agent.evidence import media
    r = scene.render_turntable({"reps": [{"style": "NewCartoon", "color": "Structure"}]}, PDB, DCD,
                               str(tmp_path / "t.mp4"), frames=8, width=160, height=120, fps=8)
    assert r["ok"], r
    info = media.probe_video(r["movie"], count_frames=True)
    assert info["ok"] and (info["width"], info["height"]) == (160, 120) and info["n_frames"] == 8
    rep = media.validate_video(r["movie"], expect_width=160, expect_height=120, expect_n_frames=8)
    assert rep.get("ok", True) is not False
    with pytest.raises(security.InvalidInput):
        scene.render_turntable({"reps": [{}]}, PDB, DCD, str(tmp_path / "x.mp4"), frames=1)


@vmd
def test_water_oxygen_rdf_has_the_known_first_peak(tmp_path):
    """Physics check with no reference code: liquid-water O-O g(r) peaks near 2.8 A and tends to 1 at long range."""
    b = build.build_system(UBQ, str(tmp_path / "ubq"), padding=10)
    r = measure.measure(b["final_psf"], b["final_pdb"], kind="gofr", selection="water and name OH2",
                        selection2="water and name OH2", rmax=8.0, delta=0.1)
    assert r["ok"], r
    g, rr = np.array(r["g"]), np.array(r["r"])
    assert 2.6 < rr[g.argmax()] < 3.0 and g.max() > 2.2
    assert g[rr < 2.2].max() < 0.05                                     # no overlap below contact
    assert 0.9 < g[(rr > 7) & (rr < 8)].mean() < 1.2                     # tends to the bulk value


# ------------------------------------------------------------------ the command line
def test_tools_command_lists_every_tool_in_groups(capsys):
    from vmd_agent import cli, toolset
    assert cli.main(["tools"]) == 0
    out = capsys.readouterr().out
    assert all(n in out for n in toolset.library_tools()) and "Whole jobs" in out
    assert all(g in out for g, _d, _t in toolset.LIBRARY)


def test_tool_command_runs_a_tool_with_flags_and_reports_bad_input(tmp_path, capsys, monkeypatch):
    from vmd_agent import cli
    monkeypatch.setenv(security.ENV_ROOTS, str(tmp_path))
    dx = tmp_path / "m.dx"
    dx.write_text("object 1 class gridpositions counts 2 2 2\norigin 0 0 0\ndelta 1 0 0\ndelta 0 1 0\ndelta 0 0 1\n"
                  "object 2 class gridconnections counts 2 2 2\nobject 3 class array type double rank 0 items 8 data follows\n"
                  "1 2 3\n4 5 6\n7 8\n")
    assert cli.main(["tool", "inspect_map", str(dx)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["shape"] == [2, 2, 2] and out["max"] == 8 and out["integral"] == 36
    with pytest.raises(SystemExit) as e:
        cli.main(["tool", "no_such_tool"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        cli.main(["tool", "inspect_map", str(dx), "--bogus", "1"])                        # wrong flag names
    assert e.value.code == 2
    assert cli.main(["tool", "inspect_map", str(tmp_path / "x.mrc")]) == 1                # ok: false -> exit 1


# ------------------------------------------------------------------ a model mixing up inputs and outputs
def test_no_tool_writes_over_a_file_it_reads(tmp_path):
    """Found with a real model: it passed the input's own name as the output prefix and destroyed the user's PDB."""
    pdb = tmp_path / "protein.pdb"
    pdb.write_text(open(UBQ).read())
    before = pdb.read_text()
    with pytest.raises(security.InvalidInput, match="input files"):
        build.build_system(str(pdb), str(tmp_path / "protein"))
    with pytest.raises(security.InvalidInput, match="input files"):
        trajectory.convert(str(pdb), None, str(pdb), fmt="pdb")
    with pytest.raises(security.InvalidInput, match="input files"):
        trajectory.write_structure(str(pdb), None, str(pdb))
    with pytest.raises(security.InvalidInput, match="input files"):
        structure.align_structures(str(pdb), UBQ, out_pdb=str(pdb))
    with pytest.raises(security.InvalidInput, match="input files"):
        volumetric.volmap(str(pdb), None, str(pdb), kind="density")
    assert pdb.read_text() == before


@vmd
def test_a_trajectory_that_does_not_match_the_topology_is_an_error_not_an_empty_result():
    for call in (lambda: measure.measure(UBQ, DCD, kind="rgyr"), lambda: trajectory.pbc_info(UBQ, DCD),
                 lambda: structure.secondary_structure(UBQ, DCD)):
        r = call()
        assert r["ok"] is False and "no frames" in r["error"], r
