"""Map arithmetic and fitting (NumPy), the NAMD input and the SLURM script."""
import os
import re

import MDAnalysis as mda
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from vmd_agent import security
from vmd_agent.inputs import volume
from vmd_agent.vmdkit import build, maps, prepare

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
UBQ = os.path.join(DATA, "1ubq.pdb")


def _grid_map(tmp_path, name, fn):
    shape = (8, 6, 5)
    x, y, z = np.meshgrid(*[np.arange(n) for n in shape], indexing="ij")
    data = fn(x, y, z).astype(float)
    p = tmp_path / name
    volume.write_dx(str(p), data, (1.0, 2.0, 3.0), (2.0, 2.0, 2.0))
    return str(p), data


# ------------------------------------------------------------------ writing and arithmetic
def test_a_written_map_reads_back_the_same(tmp_path):
    p, data = _grid_map(tmp_path, "m.dx", lambda x, y, z: x * 100 + y * 10 + z)
    v = volume.read_volume(p)
    assert np.allclose(v["data"], data) and v["origin"] == [1.0, 2.0, 3.0] and v["delta"] == [2.0, 2.0, 2.0]


@pytest.mark.parametrize("op,expected", [("add", lambda a, b: a + b), ("subtract", lambda a, b: a - b),
                                         ("multiply", lambda a, b: a * b), ("average", lambda a, b: (a + b) / 2)])
def test_two_map_arithmetic_matches_numpy(op, expected, tmp_path):
    pa, a = _grid_map(tmp_path, "a.dx", lambda x, y, z: x + y)
    pb, b = _grid_map(tmp_path, "b.dx", lambda x, y, z: z * 2 + 1)
    r = maps.map_arithmetic(pa, op, str(tmp_path / "o.dx"), map_b=pb)
    assert r["ok"] and np.allclose(volume.read_volume(str(tmp_path / "o.dx"))["data"], expected(a, b))


def test_one_map_operations_match_numpy(tmp_path):
    from scipy import ndimage
    pa, a = _grid_map(tmp_path, "a.dx", lambda x, y, z: x * y - z)
    out = str(tmp_path / "o.dx")
    read = lambda: volume.read_volume(out)["data"]                       # noqa: E731
    maps.map_arithmetic(pa, "threshold", out, value=4)
    assert np.allclose(read(), np.where(a >= 4, a, 0))
    maps.map_arithmetic(pa, "clamp", out, value=6)
    assert np.allclose(read(), np.clip(a, 0, 6))
    maps.map_arithmetic(pa, "scale", out, value=-2)
    assert np.allclose(read(), a * -2)
    maps.map_arithmetic(pa, "normalize", out)
    assert abs(read().mean()) < 1e-6 and abs(read().std() - 1) < 1e-6
    maps.map_arithmetic(pa, "smooth", out, value=2.0)                    # 2 A on a 2 A grid = 1 voxel
    assert np.allclose(read(), ndimage.gaussian_filter(a, 1.0), atol=1e-5)
    pb, b = _grid_map(tmp_path, "b.dx", lambda x, y, z: x)
    maps.map_arithmetic(pa, "mask", out, map_b=pb, value=3)
    assert np.allclose(read(), np.where(b >= 3, a, 0))


def test_map_arithmetic_refuses_mismatched_maps_missing_inputs_and_overwriting(tmp_path):
    pa, _ = _grid_map(tmp_path, "a.dx", lambda x, y, z: x)
    volume.write_dx(str(tmp_path / "other.dx"), np.zeros((4, 4, 4)), (0, 0, 0), (1, 1, 1))
    with pytest.raises(security.InvalidInput, match="same grid"):
        maps.map_arithmetic(pa, "add", str(tmp_path / "o.dx"), map_b=str(tmp_path / "other.dx"))
    with pytest.raises(security.InvalidInput, match="second map"):
        maps.map_arithmetic(pa, "add", str(tmp_path / "o.dx"))
    with pytest.raises(security.InvalidInput, match="needs a value"):
        maps.map_arithmetic(pa, "smooth", str(tmp_path / "o.dx"))
    with pytest.raises(security.InvalidInput, match="input files"):
        maps.map_arithmetic(pa, "scale", pa, value=2)
    with pytest.raises(security.InvalidInput):
        maps.map_arithmetic(pa, "explode", str(tmp_path / "o.dx"))


# ------------------------------------------------------------------ fitting a model into a map
def _target_map(tmp_path):
    p = mda.Universe(UBQ).select_atoms("protein")
    xyz = p.positions.astype(float)
    spacing = np.array([2.0] * 3)
    lo = xyz.min(0) - 20
    shape = tuple(np.ceil((xyz.max(0) + 20 - lo) / spacing).astype(int))
    path = str(tmp_path / "target.dx")
    volume.write_dx(path, maps._simulate(xyz, p.masses, shape, lo, spacing, 8.0), lo, spacing)
    return path, xyz


def test_a_displaced_model_is_put_back_where_it_came_from(tmp_path):
    """A map is made from the real structure; the model is turned and moved by known amounts; the fit must undo that."""
    target, truth = _target_map(tmp_path)
    u = mda.Universe(UBQ)
    c = truth.mean(0)
    u.atoms.positions = (Rotation.from_euler("xyz", [12, -9, 15], degrees=True).apply(u.atoms.positions - c) + c
                         + np.array([3.0, -2.5, 2.0])).astype("float32")
    u.atoms.write(str(tmp_path / "moved.pdb"))
    r = maps.fit_to_map(str(tmp_path / "moved.pdb"), target, resolution=8.0, out_pdb=str(tmp_path / "fitted.pdb"))
    assert r["ok"] and r["correlation_before"] < 0.7 and r["correlation_after"] > 0.97
    fitted = mda.Universe(str(tmp_path / "fitted.pdb")).select_atoms("protein").positions
    assert np.sqrt(((fitted - truth) ** 2).sum(1).mean()) < 0.5                       # back within half an angstrom
    assert len(mda.Universe(str(tmp_path / "fitted.pdb")).atoms) == len(mda.Universe(UBQ).atoms)   # all atoms moved, none lost


def test_fitting_refuses_to_overwrite_its_input_and_bad_settings(tmp_path):
    target, _ = _target_map(tmp_path)
    with pytest.raises(security.InvalidInput, match="input files"):
        maps.fit_to_map(UBQ, target, out_pdb=UBQ)
    with pytest.raises(security.InvalidInput):
        maps.fit_to_map(UBQ, target, resolution=0)
    with pytest.raises(security.InvalidInput, match="fewer than 3"):
        maps.fit_to_map(UBQ, target, selection="resid 1 and name CA")


# ------------------------------------------------------------------ NAMD and SLURM
@pytest.mark.requires_vmd
def test_the_namd_input_matches_the_system_it_was_made_from(tmp_path):
    b = build.build_system(UBQ, str(tmp_path / "sys" / "ubq"), padding=8)
    r = prepare.prepare_namd(b["final_psf"], b["final_pdb"], str(tmp_path / "sys" / "eq"), temperature=300, equilibrate_ps=10,
                             minimize_steps=500)
    assert r["ok"] and "Not run in NAMD" in r["warning"]
    cfg = open(r["config"]).read()
    keys = {m.group(1): m.group(2) for m in re.finditer(r"^(\S+)\s+(.+)$", cfg, re.M) if not m.group(1).startswith("#")}
    sysm = mda.Universe(b["final_psf"], b["final_pdb"])
    span = sysm.atoms.positions.max(0) - sysm.atoms.positions.min(0)
    assert [float(keys["cellBasisVector1"].split()[0]), float(keys["cellBasisVector2"].split()[1]),
            float(keys["cellBasisVector3"].split()[2])] == pytest.approx(list(span), abs=0.01)
    assert keys["structure"] == os.path.basename(b["final_psf"]) and keys["coordinates"] == os.path.basename(b["final_pdb"])
    assert keys["rigidBonds"] == "all" and keys["PME"] == "yes" and keys["timestep"] == "2" and keys["minimize"] == "500"
    assert keys["run"] == str(int(10 * 1000 / 2)) and "300" in keys["set"]
    for p in r["parameter_files"]:                                   # every file the config names exists beside it
        assert os.path.isfile(p)
    for line in re.findall(r"^parameters\s+(\S+)", cfg, re.M):
        assert os.path.isfile(os.path.join(tmp_path, "sys", line))
    assert "langevinPiston        on" in cfg
    nvt = prepare.prepare_namd(b["final_psf"], b["final_pdb"], str(tmp_path / "sys" / "nvt"), ensemble="nvt")
    assert "langevinPiston" not in open(nvt["config"]).read()


@pytest.mark.requires_vmd
def test_the_namd_input_refuses_a_dry_protein_and_silly_settings(tmp_path):
    b = build.build_system(UBQ, str(tmp_path / "ubq"), solvate=False)
    dry = prepare.prepare_namd(b["final_psf"], b["final_pdb"], str(tmp_path / "dry"))
    assert dry["ok"] is False and "no water" in dry["error"]          # a protein alone is no periodic system
    with pytest.raises(security.InvalidInput):
        prepare.prepare_namd(b["final_psf"], b["final_pdb"], str(tmp_path / "x"), temperature=5000)


def test_the_slurm_script_has_the_requested_resources_and_safe_values(tmp_path):
    out = str(tmp_path / "job.sbatch")
    r = prepare.slurm_script("eq.namd", out, job_name="ubq-eq", partition="gpu", cpus=16, gpus=2, hours=30.5, memory_gb=64,
                             modules=["namd/3.0", "cuda"], kind="namd")
    text = open(out).read()
    assert r["ok"] and text.startswith("#!/bin/bash")
    for line in ("#SBATCH --job-name=ubq-eq", "#SBATCH --cpus-per-task=16", "#SBATCH --mem=64G", "#SBATCH --partition=gpu",
                 "#SBATCH --gres=gpu:2", "#SBATCH --time=1-06:30:00", "module load namd/3.0", "module load cuda"):
        assert line in text, line
    assert "namd3 +p${SLURM_CPUS_PER_TASK} eq.namd" in text and "+devices" in text
    assert "vmd -dispdev text -eofexit -e \"s.tcl\"" in open(_slurm(tmp_path, "s.tcl", "vmd")).read()
    for bad in ({"job_name": "a; rm -rf /"}, {"partition": "x y"}, {"modules": ["ok", "bad;module"]}, {"cpus": 0}, {"hours": 0}):
        with pytest.raises(security.InvalidInput):
            prepare.slurm_script("x", str(tmp_path / "bad.sbatch"), **bad)


def _slurm(tmp_path, command, kind):
    out = str(tmp_path / f"{kind}.sbatch")
    prepare.slurm_script(command, out, kind=kind)
    return out
