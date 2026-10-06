"""Trajectory analysis, cross-validated against independent NumPy."""
from conftest import UBQ_MD_DIR
import os
import MDAnalysis as mda
import numpy as np
import pytest
from vmd_agent.dynamics.analysis import analyze_trajectory, pbc_diagnostics


def _coords(pdb, dcd, sel):
    u = mda.Universe(pdb, dcd)
    ag = u.select_atoms(sel)
    return np.array([ag.positions.copy() for _ in u.trajectory]), \
        np.array([ag.masses for _ in [0]])[0]


def kabsch_rmsd(P, Q):
    """Independent RMSD after optimal superposition (centred, no mass weights)."""
    P = P - P.mean(0)
    Q = Q - Q.mean(0)
    H = P.T @ Q
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.diag([1, 1, d])
    R = U @ D @ Vt
    return float(np.sqrt(np.mean(np.sum((P @ R - Q) ** 2, axis=1))))


@pytest.fixture
def run(sample, tmp_path):
    pdb, dcd = sample
    return analyze_trajectory(pdb, dcd, ["rmsd", "rgyr", "rmsf", "contacts",
                                         "distance", "hbonds", "density",
                                         "convergence", "bogus"],
                              selection="protein", sel2="resname LIG",
                              cutoff=6.0, out_dir=str(tmp_path))


def test_rmsd_matches_independent_kabsch(sample, run):
    pdb, dcd = sample
    xyz, _ = _coords(pdb, dcd, "protein")
    expected = [kabsch_rmsd(f, xyz[0]) for f in xyz]
    got_summary = run["results"]["rmsd"]["summary"]
    assert got_summary["mean"] == pytest.approx(np.mean(expected), rel=0.02,
                                                abs=0.02)
    assert got_summary["last"] == pytest.approx(expected[-1], rel=0.02,
                                                abs=0.02)


def test_rgyr_matches_independent_formula(sample, run):
    pdb, dcd = sample
    u = mda.Universe(pdb, dcd)
    ag = u.select_atoms("protein")
    m = ag.masses
    rg = []
    for _ in u.trajectory:
        x = ag.positions
        com = (x * m[:, None]).sum(0) / m.sum()
        rg.append(np.sqrt((m * ((x - com) ** 2).sum(1)).sum() / m.sum()))
    assert run["results"]["rgyr"]["summary"]["mean"] == pytest.approx(
        np.mean(rg), rel=1e-4)


def test_contacts_match_brute_force(sample, run):
    pdb, dcd = sample
    u = mda.Universe(pdb, dcd)
    a, b = u.select_atoms("protein"), u.select_atoms("resname LIG")
    counts = []
    for _ in u.trajectory:
        d = np.linalg.norm(a.positions[:, None] - b.positions[None], axis=2)
        counts.append(int((d < 6.0).sum()))
    assert run["results"]["contacts"]["summary"]["mean"] == pytest.approx(
        np.mean(counts))


def test_distance_matches_independent_com(sample, run):
    pdb, dcd = sample
    u = mda.Universe(pdb, dcd)
    a, b = u.select_atoms("protein"), u.select_atoms("resname LIG")
    d = [np.linalg.norm(a.center_of_mass() - b.center_of_mass())
         for _ in u.trajectory]
    assert run["results"]["distance"]["summary"]["mean"] == pytest.approx(
        np.mean(d), rel=1e-5)


def test_rmsf_is_per_residue_and_flags_the_loop(run):
    r = run["results"]["rmsf"]
    assert r["level"].startswith("per-residue")
    assert len(r["rmsf_values"]) == 12                 # one value per residue
    assert len(set(r["most_flexible_residues"])) == 5  # distinct residues
    assert set(r["most_flexible_residues"]) >= {8, 9, 10}  # the drifting loop


def test_short_trajectory_is_not_called_stable(run):
    """8 frames cannot support a stability claim; the old code said 'stable'."""
    interp = run["results"]["rmsd"]["interpretation"]
    assert "too few" in interp
    assert "stable" not in interp.lower()


def test_unknown_analysis_is_reported_not_raised(run):
    assert "unknown analysis" in run["results"]["bogus"]["error"]


def test_timed_trajectory_axis_is_time(run):
    ta = run["time_axis"]
    assert ta["label"] == "time (ps)" and ta["from_trajectory"]
    assert "DCDReader" in ta["source"] and "warning" in ta


def test_striding_keeps_original_frame_axis(sample, tmp_path):
    pdb, dcd = sample
    r = analyze_trajectory(pdb, dcd, ["rgyr"], step=2, out_dir=str(tmp_path))
    assert r["n_frames"] == 4 and r["step"] == 2


def test_untimed_trajectory_is_labelled_frame_index(sample, tmp_path):
    """Multi-model PDB carries no timing: axis must say 'frame index'."""
    pdb, dcd = sample
    u = mda.Universe(pdb, dcd)
    multi = tmp_path / "multi.pdb"
    with mda.Writer(str(multi), n_atoms=len(u.atoms), multiframe=True) as w:
        for _ in u.trajectory:
            w.write(u.atoms)
    r = analyze_trajectory(str(multi), str(multi), ["rgyr"], step=2,
                           out_dir=str(tmp_path / "o"))
    assert r["time_axis"]["label"] == "frame index"
    assert not r["time_axis"]["from_trajectory"]
    assert any("frame index" in n for n in r["notes"])


def test_batch_order_does_not_corrupt_density(sample, tmp_path):
    """RMSF aligns in memory; it must not leak into later analyses."""
    pdb, dcd = sample
    alone = analyze_trajectory(pdb, dcd, ["density"], out_dir=str(tmp_path / "a"))
    both = analyze_trajectory(pdb, dcd, ["rmsf", "density"],
                              out_dir=str(tmp_path / "b"))
    assert alone["results"]["density"]["peak_position"] == pytest.approx(
        both["results"]["density"]["peak_position"])


def test_hbonds_without_hydrogens_carries_caveat(run):
    r = run["results"]["hbonds"]
    assert r["method"] == "distance_only" and "overestimate" in r["caveat"]


def test_empty_selection_is_an_error_not_a_crash(sample, tmp_path):
    pdb, dcd = sample
    r = analyze_trajectory(pdb, dcd, ["rmsd"], selection="resname NOPE",
                           out_dir=str(tmp_path))
    assert "matched 0 atoms" in r["results"]["rmsd"]["error"]


def test_convergence_reports_blocks_and_never_says_converged(run):
    c = run["results"]["convergence"]
    assert set(c["series"]) == {"rmsd", "rgyr"}
    assert "cannot show" in c["interpretation"]


def test_plots_are_written(run):
    import os
    for k in ("rmsd", "rgyr", "rmsf", "contacts", "distance", "hbonds",
              "density"):
        assert os.path.exists(run["results"][k]["plot"])


@pytest.fixture
def wrapped_run(tmp_path):
    """A rigid 6-atom 'molecule' drifting across a 20 Å box with wrapping."""
    from MDAnalysis.coordinates.memory import MemoryReader
    n_atoms = 6
    u = mda.Universe.empty(n_atoms, n_residues=1, atom_resindex=[0] * n_atoms,
                           trajectory=True)
    u.add_TopologyAttr("names", ["CA"] * n_atoms)
    u.add_TopologyAttr("resnames", ["ALA"])
    u.add_TopologyAttr("resids", [1])
    u.add_TopologyAttr("elements", ["C"] * n_atoms)
    shape = np.array([[0, 0, 0], [1.5, 0, 0], [3, 0, 0], [0, 1.5, 0],
                      [1.5, 1.5, 0], [3, 1.5, 0]], float)
    frames = []
    for f in range(40):
        p = shape + np.array([f * 0.9, 5.0, 5.0])
        frames.append(np.mod(p, 20.0))              # wrap into the box
    u.load_new(np.array(frames, dtype=np.float32), format=MemoryReader,
               dimensions=np.tile([20, 20, 20, 90, 90, 90], (40, 1)))
    return u


def test_pbc_diagnostic_flags_wrapped_molecule(wrapped_run):
    r = pbc_diagnostics(wrapped_run, "all")
    assert r["checked"] and r["n_split_frames"] > 0 and "split" in r["warning"]


def test_pbc_diagnostic_quiet_for_whole_molecule(sample):
    pdb, dcd = sample
    r = pbc_diagnostics(mda.Universe(pdb, dcd), "protein")
    assert r["checked"] and r["n_jump_frames"] == 0 and "warning" not in r


def test_unwrap_repairs_a_torn_molecule(wrapped_run, tmp_path):
    """Rg of a rigid molecule must be constant once it is made whole."""
    pdb, dcd = str(tmp_path / "w.pdb"), str(tmp_path / "w.dcd")
    wrapped_run.trajectory[0]
    wrapped_run.atoms.write(pdb)
    with mda.Writer(dcd, n_atoms=len(wrapped_run.atoms)) as w:
        for _ in wrapped_run.trajectory:
            w.write(wrapped_run.atoms)
    raw = analyze_trajectory(pdb, dcd, ["rgyr"], selection="all",
                             out_dir=str(tmp_path / "a"))
    fixed = analyze_trajectory(pdb, dcd, ["rgyr"], selection="all",
                               out_dir=str(tmp_path / "b"), unwrap=True)
    assert raw["pbc"]["n_split_frames"] > 0
    assert raw["results"]["rgyr"]["summary"]["std"] > 0.5      # torn molecule
    assert fixed["results"]["rgyr"]["summary"]["std"] < 0.05   # whole again
    assert any("guessed" in n for n in fixed["notes"])




@pytest.fixture(scope="module")
def ubq_md():
    return (os.path.join(UBQ_MD_DIR, "protein.pdb"),
            os.path.join(UBQ_MD_DIR, "protein.dcd"))


def test_dcd_header_time_is_flagged_not_trusted(ubq_md, tmp_path):
    """Real data: this DCD says 1 ps/frame; its manifest says 400 ps."""
    r = analyze_trajectory(*ubq_md, ["rgyr"], out_dir=str(tmp_path))
    ta = r["time_axis"]
    assert ta["source"].startswith("trajectory header")
    assert "dt_ps" in ta["warning"]
    assert any("DCD headers" in n for n in r["notes"])


def test_dt_ps_overrides_the_header(ubq_md, tmp_path):
    import json
    manifest = json.load(open(os.path.join(UBQ_MD_DIR, "prep_manifest.json")))
    dt = manifest["subset_time_per_frame_ps"]
    r = analyze_trajectory(*ubq_md, ["rgyr"], step=5, dt_ps=dt,
                           out_dir=str(tmp_path))
    assert r["time_axis"] == {"label": "time (ps)", "from_trajectory": True,
                              "source": "user-supplied dt_ps", "dt_ps": dt}
    assert "warning" not in r["time_axis"]


# ------------------------------------------------------------ audit fixes
def test_contacts_and_distance_require_a_second_selection(sample, tmp_path):
    """Previously sel2 silently defaulted to the selection itself: 333
    'contacts' (self-pairs, each pair twice) and a COM distance of exactly 0."""
    pdb, dcd = sample
    r = analyze_trajectory(pdb, dcd, ["contacts", "distance", "rgyr"],
                           selection="protein", out_dir=str(tmp_path))
    assert "needs sel2" in r["results"]["contacts"]["error"]
    assert "needs sel2" in r["results"]["distance"]["error"]
    assert "error" not in r["results"]["rgyr"]            # others unaffected


def test_memory_guard_refuses_and_suggests_a_step(sample, tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_MAX_MEMORY_GB", "0.000001")
    pdb, dcd = sample
    r = analyze_trajectory(pdb, dcd, ["rgyr"], out_dir=str(tmp_path))
    assert "memory" in r["error"] and r["suggested_step"] > 1
    assert r["limit_gb"] == pytest.approx(1e-6)


def test_memory_guard_allows_normal_runs(sample, tmp_path):
    pdb, dcd = sample
    assert "error" not in analyze_trajectory(pdb, dcd, ["rgyr"],
                                             out_dir=str(tmp_path))


def test_box_validity_rules():
    from vmd_agent.dynamics.analysis import _valid_box
    assert _valid_box([0, 0, 0, 90, 90, 90]) is None      # PDB without CRYST1
    assert _valid_box([np.nan, 1, 1, 90, 90, 90]) is None
    assert _valid_box(None) is None and _valid_box([1, 2, 3]) is None
    assert _valid_box([10, 10, 10, 90, 90, 90]).shape == (6,)


@pytest.mark.parametrize("dt", [0, -5, float("nan"), float("inf"), "abc"])
def test_dt_ps_must_be_positive_and_finite(sample, tmp_path, dt):
    """These used to be accepted and produce a 'user-supplied' axis of NaN."""
    pdb, dcd = sample
    r = analyze_trajectory(pdb, dcd, ["rgyr"], dt_ps=dt, out_dir=str(tmp_path))
    assert "dt_ps must be" in r["error"]


def test_step_below_one_is_reported_not_silently_changed(sample, tmp_path):
    pdb, dcd = sample
    r = analyze_trajectory(pdb, dcd, ["rgyr"], step=-3, out_dir=str(tmp_path))
    assert r["step"] == 1 and any("treated as 1" in n for n in r["notes"])


def test_nonfinite_frames_are_reported_not_silently_dropped(sample, tmp_path):
    """Found by the automation benchmark: frames with NaN coordinates were
    excluded from the statistics with no warning (n quietly shrank)."""
    pdb, dcd = sample
    u = mda.Universe(pdb, dcd)
    ag = u.atoms
    pos = np.array([ag.positions.copy() for _ in u.trajectory])
    pos[2:4, :5, :] = np.nan
    bad = str(tmp_path / "bad.dcd")
    with mda.Writer(bad, n_atoms=ag.n_atoms) as w:
        for f in range(len(pos)):
            ag.positions = pos[f]
            w.write(ag)
    r = analyze_trajectory(pdb, bad, ["rgyr"], selection="all",
                           out_dir=str(tmp_path))
    assert any("non-finite" in n and "2 of" in n for n in r["notes"])
    ok = analyze_trajectory(pdb, dcd, ["rgyr"], out_dir=str(tmp_path))
    assert not any("non-finite" in n for n in ok["notes"])
