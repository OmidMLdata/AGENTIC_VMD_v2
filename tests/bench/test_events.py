"""Real-noise event study."""
from conftest import UBQ_MD_FILES
import numpy as np
import pytest
from vmd_agent.bench import events as E, synth






@pytest.fixture(scope="module")
def base():
    return E.load_real_positions(*UBQ_MD_FILES)


def test_real_trajectory_loads(base):
    assert base["pos"].shape == (50, 1240, 3)
    assert base["masses"].shape == (1240,)


def test_pingpong_is_locally_continuous(base):
    ext = E.pingpong(base["pos"], 160)
    assert len(ext) == 160
    # every step is a step the real data took (or its reverse)
    real = {tuple(np.round(f.ravel()[:6], 4)) for f in base["pos"]}
    assert all(tuple(np.round(f.ravel()[:6], 4)) in real for f in ext)
    assert np.allclose(ext[49], base["pos"][49]) and np.allclose(ext[50],
                                                                 base["pos"][48])


def test_kabsch_series_ignores_rigid_motion(base):
    rng = np.random.default_rng(0)
    frames = base["pos"][:5].copy()
    for i in range(1, 5):
        frames[i] = frames[0] @ synth._random_rotation(rng).T + rng.normal(size=3)
    assert E.kabsch_rmsd_series(frames).max() < 1e-6


def test_dissociation_moves_exactly_the_tail_by_the_magnitude(base):
    ext = E.pingpong(base["pos"], 100)
    g = E.event_groups(base["resindices"])
    inj = E.inject_event(ext, g, "dissociation", start=30, length=10,
                         magnitude=6.0, rng=np.random.default_rng(1))
    mv = g["dissociation"]
    rest = np.setdiff1d(np.arange(ext.shape[1]), mv)
    assert np.allclose(inj["pos"][:30], ext[:30])                # before: untouched
    assert np.allclose(inj["pos"][:, rest], ext[:, rest])        # rest never moves
    shift = np.linalg.norm(inj["pos"][99, mv] - ext[99, mv], axis=1)
    assert np.allclose(shift, 6.0, atol=1e-6)                    # held at magnitude
    mid = np.linalg.norm(inj["pos"][35, mv] - ext[35, mv], axis=1)
    assert np.allclose(mid, 3.0, atol=1e-6)                      # halfway up the ramp
    assert inj["event"] == {"kind": "dissociation", "start": 30, "end": 40,
                            "magnitude": 6.0}


def test_hinge_is_rigid_for_the_moving_group(base):
    ext = E.pingpong(base["pos"], 80)
    g = E.event_groups(base["resindices"])
    inj = E.inject_event(ext, g, "hinge", 20, 10, 30.0, np.random.default_rng(2))
    mv = g["hinge"][:40]
    d0 = np.linalg.norm(ext[79, mv][:, None] - ext[79, mv][None], axis=2)
    d1 = np.linalg.norm(inj["pos"][79, mv][:, None] - inj["pos"][79, mv][None],
                        axis=2)
    assert np.allclose(d0, d1, atol=1e-6)                        # internal geometry kept
    assert not np.allclose(inj["pos"][79, mv], ext[79, mv])      # but it moved


def test_expansion_scales_radius_of_gyration(base):
    ext = E.pingpong(base["pos"], 60)
    g = E.event_groups(base["resindices"])
    inj = E.inject_event(ext, g, "expansion", 10, 10, 0.10)
    r0 = E.signals_from_positions(ext, base["masses"])["rgyr"][-1]
    r1 = E.signals_from_positions(inj["pos"], base["masses"])["rgyr"][-1]
    assert r1 / r0 == pytest.approx(1.10, rel=1e-3)


def test_inputs_never_mutated_and_bad_kind_rejected(base):
    ext = E.pingpong(base["pos"], 40)
    keep = ext.copy()
    E.inject_event(ext, E.event_groups(base["resindices"]), "expansion", 5, 5, .1)
    assert np.array_equal(ext, keep)
    with pytest.raises(ValueError):
        E.inject_event(ext, {}, "teleport", 1, 1, 1)


def test_event_study_shows_the_advantage_on_a_strong_short_event(base):
    st = E.event_study(base, kinds=("dissociation",), lengths=(5,),
                       magnitudes={"dissociation": (6.0,)}, n_frames=150,
                       n_trials=12, seed=0)
    row = st["rows"][0]
    assert row["effect_in_noise_sd"] > 3
    assert row["hit_event_aware"] >= 0.8 and row["hit_uniform"] <= 0.5
    assert "| dissociation |" in E.table_markdown(st)


def test_event_study_gives_no_advantage_when_the_event_is_undetectable(base):
    """A 10-degree hinge is ~0.5 noise sd: the selector must not pretend."""
    st = E.event_study(base, kinds=("hinge",), lengths=(5,),
                       magnitudes={"hinge": (3.0,)}, n_frames=150, n_trials=20,
                       seed=1)
    r = st["rows"][0]
    assert r["effect_in_noise_sd"] < 1.5
    assert r["hit_event_aware"] <= r["hit_uniform"] + 0.35


def test_negative_control_does_not_flood_the_budget(base):
    r = E.negative_control(base, n_frames=300)
    assert r["budget_spent_on_events"] <= 2 and r["k"] == 9
