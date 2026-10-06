"""Cryo-EM style work with density maps, in NumPy (no VMD needed): arithmetic on maps, and fitting a model into a map.

VMD's own ``volutil`` binary did not load on the build tested, and VMD's fitting tools need NAMD, so these are done
here. Both read and write OpenDX, which every VMD map tool and the scene renderer understand.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from scipy import ndimage
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from vmd_agent import progress, security
from vmd_agent.inputs.volume import read_volume, summarize, write_dx
from vmd_agent.vmdkit import script as S

OPS = {"add": "A + B (same grid)", "subtract": "A - B (same grid)", "multiply": "A * B (same grid)",
       "average": "(A + B) / 2 (same grid)", "threshold": "A where A >= value, else 0",
       "clamp": "A limited to the range [0, value]", "smooth": "Gaussian blur of A with a width of `value` angstrom",
       "normalize": "A shifted and scaled to mean 0 and standard deviation 1", "mask": "A where B >= value, else 0 (same grid)",
       "scale": "A * value"}
NEEDS_B = ("add", "subtract", "multiply", "average", "mask")
NEEDS_VALUE = ("threshold", "clamp", "smooth", "mask", "scale")


def map_arithmetic(map_a: str, op: str, out_dx: str, map_b: Optional[str] = None, value: Optional[float] = None) -> dict:
    """Combine or clean density maps and write the result as OpenDX. Operations: see ``OPS``."""
    S.choice(op, list(OPS), "op")
    S.keep_inputs([out_dx], [map_a, map_b])
    if op in NEEDS_B and not map_b:
        raise security.InvalidInput(f"{op} needs a second map (map_b)")
    if op in NEEDS_VALUE and value is None:
        raise security.InvalidInput(f"{op} needs a value")
    v = S.num(value, "value") if value is not None else None
    a = read_volume(map_a)
    da = np.asarray(a["data"], dtype=float)
    spacing = [abs(x) for x in a["delta"]]
    if op in NEEDS_B:
        b = read_volume(map_b)                                     # type: ignore[arg-type]
        if b["data"].shape != da.shape or not np.allclose([abs(x) for x in b["delta"]], spacing) \
                or not np.allclose(b["origin"], a["origin"], atol=1e-3):
            raise security.InvalidInput("the two maps are not on the same grid (size, spacing and origin must match)")
        db = np.asarray(b["data"], dtype=float)
    if op == "add":
        out = da + db
    elif op == "subtract":
        out = da - db
    elif op == "multiply":
        out = da * db
    elif op == "average":
        out = (da + db) / 2.0
    elif op == "threshold":
        out = np.where(da >= v, da, 0.0)
    elif op == "clamp":
        out = np.clip(da, 0.0, v)
    elif op == "smooth":
        out = ndimage.gaussian_filter(da, sigma=[v / s for s in spacing])
    elif op == "normalize":
        sd = da.std()
        out = (da - da.mean()) / sd if sd > 0 else da - da.mean()
    elif op == "mask":
        out = np.where(db >= v, da, 0.0)
    else:
        out = da * v
    os.makedirs(os.path.dirname(os.path.abspath(out_dx)), exist_ok=True)
    write_dx(out_dx, out, a["origin"], spacing, comment=f"vmd-agent {op}")
    return {"ok": True, "engine": "NumPy (no VMD)", "op": op, "map_path": out_dx, **summarize(
        {"data": out, "origin": a["origin"], "delta": spacing})}


# ---------------------------------------------------------------- fitting a model into a map
def _simulate(coords: np.ndarray, weights: np.ndarray, shape, origin, spacing, resolution: float) -> np.ndarray:
    """A density map of the atoms on the given grid: each atom a Gaussian (sigma = 0.225 x the resolution, the usual
    convention for 'resolution' in cryo-EM), by depositing the weights on the grid and blurring."""
    grid = np.zeros(shape)
    idx = np.rint((coords - origin) / spacing).astype(int)
    ok = np.all((idx >= 0) & (idx < np.array(shape)), axis=1)
    np.add.at(grid, tuple(idx[ok].T), weights[ok])
    return ndimage.gaussian_filter(grid, sigma=0.225 * resolution / np.asarray(spacing))


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    keep = (a > a.max() * 0.01) | (b > b.max() * 0.01)
    if keep.sum() < 10:
        return 0.0
    x, y = a[keep], b[keep]
    return float(np.corrcoef(x, y)[0, 1])


def fit_to_map(model: str, map_file: str, resolution: float = 8.0, selection: str = "protein",
               out_pdb: Optional[str] = None, rotation_search: bool = True) -> dict:
    """Move a model as a rigid body to where it fits a density map best, like Chimera's fitmap or VMD's rigid-body fit:
    it maximises the average map value at the atoms' positions, then reports the map-model correlation before and
    after. Returns the transform and, if asked, writes the moved model. ``resolution`` (angstrom) is how blurred a map
    made from the model is when it is compared with the experimental one."""
    from vmd_agent.inputs.molio import load_universe
    S.keep_inputs([out_pdb], [model, map_file])
    res = S.num(resolution, "resolution")
    if res <= 0:
        raise security.InvalidInput("resolution must be positive")
    vol = read_volume(map_file)
    exp = np.asarray(vol["data"], dtype=float)
    origin, spacing = np.asarray(vol["origin"], float), np.array([abs(x) for x in vol["delta"]], float)
    u = load_universe(model)
    atoms = u.select_atoms(S.sel(selection))
    if atoms.n_atoms < 3:
        raise security.InvalidInput("the selection has fewer than 3 atoms")
    xyz0 = atoms.positions.astype(float)
    mass = np.asarray(atoms.masses, float)
    centre = np.average(xyz0, axis=0, weights=mass)

    def moved(p, pts=None):
        rot = Rotation.from_rotvec(p[:3])
        return rot.apply((xyz0 if pts is None else pts) - centre) + centre + p[3:]

    def neg_score(p):
        pos = (moved(p) - origin) / spacing
        return -float(ndimage.map_coordinates(exp, pos.T, order=1, mode="constant", cval=0.0).mean())

    progress.report("fitting the model into the map")
    starts = [np.zeros(6)]
    if rotation_search:                                          # a few turned starting points guard against a poor first guess
        starts += [np.r_[Rotation.from_euler("xyz", e, degrees=True).as_rotvec(), 0, 0, 0]
                   for e in ([30, 0, 0], [0, 30, 0], [0, 0, 30], [-30, 0, 0], [0, -30, 0], [0, 0, -30])]
    best = None
    for s in starts:
        r = minimize(neg_score, s, method="Powell", options={"xtol": 1e-3, "ftol": 1e-6, "maxiter": 4000})
        if best is None or r.fun < best.fun:
            best = r
    p = best.x
    before = _correlation(_simulate(xyz0, mass, exp.shape, origin, spacing, res), exp)
    xyz1 = moved(p)
    after = _correlation(_simulate(xyz1, mass, exp.shape, origin, spacing, res), exp)
    rot = Rotation.from_rotvec(p[:3])
    result = {"ok": True, "engine": "NumPy (no VMD)", "n_atoms_fitted": int(atoms.n_atoms),
              "correlation_before": before, "correlation_after": after,
              "mean_map_value_before": -neg_score(np.zeros(6)), "mean_map_value_after": -float(best.fun),
              "rotation_degrees": float(np.degrees(np.linalg.norm(p[:3]))), "translation_A": [float(x) for x in p[3:]],
              "rotation_matrix": rot.as_matrix().tolist(), "about_point_A": [float(x) for x in centre],
              "rmsd_moved_A": float(np.sqrt(((xyz1 - xyz0) ** 2).sum(1).mean())),
              "note": "A rigid-body fit finds a local optimum: check the result in a picture (vmd_render_scene with the map as "
                      "an isosurface). It cannot fix a wrong handedness or a model that does not match the map."}
    if out_pdb:
        everything = u.atoms
        everything.positions = moved(p, everything.positions.astype(float)).astype("float32")
        os.makedirs(os.path.dirname(os.path.abspath(out_pdb)), exist_ok=True)
        everything.write(out_pdb)
        result["fitted_pdb"] = out_pdb
    return result
