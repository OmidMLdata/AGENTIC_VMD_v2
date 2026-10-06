"""Read 3-D density maps (OpenDX, CCP4/MRC, Gaussian cube, Situs) into NumPy, without VMD.

Used to report what a map contains (grid, spacing, range, integral) and to pick sensible
isosurface levels. Returns Angstrom units where the format defines them.
"""
from __future__ import annotations

import os
import struct
from typing import Dict

import numpy as np

_BOHR = 0.529177210903


def _dx(path: str) -> dict:
    counts = origin = None
    delta, vals = [], []
    with open(path) as fh:
        for line in fh:
            t = line.split()
            if not t or t[0] == "#":
                continue
            if t[0] == "object" and "gridpositions" in line:
                counts = [int(x) for x in t[-3:]]
            elif t[0] == "origin":
                origin = [float(x) for x in t[1:4]]
            elif t[0] == "delta":
                delta.append([float(x) for x in t[1:4]])
            elif t[0] == "object" or t[0] in ("attribute", "component"):
                continue
            else:
                try:
                    vals.extend(float(x) for x in t)
                except ValueError:
                    break
    if counts is None or origin is None or len(delta) != 3:
        raise ValueError("not a valid OpenDX grid")
    data = np.array(vals[: counts[0] * counts[1] * counts[2]], dtype=float).reshape(counts)
    return {"data": data, "origin": origin, "delta": [d[i] for i, d in enumerate(delta)]}


def _ccp4(path: str) -> dict:
    with open(path, "rb") as fh:
        raw = fh.read()
    for end in "<>":
        nx, ny, nz, mode = struct.unpack(end + "4i", raw[:16])
        if 0 < nx < 5000 and 0 < ny < 5000 and 0 < nz < 5000 and 0 <= mode <= 6:
            break
    else:
        raise ValueError("not a valid CCP4/MRC map")
    start = struct.unpack(end + "3i", raw[16:28])
    mxyz = struct.unpack(end + "3i", raw[28:40])
    cell = struct.unpack(end + "6f", raw[40:64])
    mapc, mapr, maps = struct.unpack(end + "3i", raw[64:76])
    nsym = struct.unpack(end + "i", raw[92:96])[0]
    dtype = {0: "i1", 1: "i2", 2: "f4", 6: "u2"}.get(mode)
    if dtype is None:
        raise ValueError(f"unsupported map mode {mode}")
    off = 1024 + nsym
    arr = np.frombuffer(raw, dtype=end + dtype, count=nx * ny * nz, offset=off).astype(float)
    arr = arr.reshape((nz, ny, nx))                         # fastest axis is x (section, row, column)
    spacing = [cell[0] / mxyz[0], cell[1] / mxyz[1], cell[2] / mxyz[2]]
    if (mapc, mapr, maps) != (1, 2, 3):
        raise ValueError("CCP4/MRC maps with a non-standard axis order are not supported")
    origin = [start[0] * spacing[0], start[1] * spacing[1], start[2] * spacing[2]]
    return {"data": np.transpose(arr, (2, 1, 0)), "origin": origin, "delta": spacing}


def _cube(path: str) -> dict:
    with open(path) as fh:
        lines = fh.read().splitlines()
    natoms = int(lines[2].split()[0])
    origin = [float(x) for x in lines[2].split()[1:4]]
    grid = [lines[3 + i].split() for i in range(3)]
    n = [int(g[0]) for g in grid]
    scale = _BOHR if n[0] > 0 else 1.0
    delta = [abs(float(grid[i][1 + i])) * scale for i in range(3)]
    vals = " ".join(lines[6 + abs(natoms):]).split()
    data = np.array(vals, dtype=float).reshape([abs(x) for x in n])
    return {"data": data, "origin": [o * scale for o in origin], "delta": delta}


def _situs(path: str) -> dict:
    with open(path) as fh:
        head = fh.readline().split()
        vox, ox, oy, oz, nx, ny, nz = float(head[0]), *[float(x) for x in head[1:4]], *[int(x) for x in head[4:7]]
        vals = np.array(fh.read().split(), dtype=float)
    return {"data": vals.reshape((nz, ny, nx)).transpose(2, 1, 0), "origin": [ox, oy, oz], "delta": [vox] * 3}


READERS = {".dx": _dx, ".ccp4": _ccp4, ".mrc": _ccp4, ".map": _ccp4, ".cube": _cube, ".cub": _cube, ".situs": _situs,
           ".sit": _situs}


def read_volume(path: str) -> Dict[str, object]:
    """``{"data": ndarray[nx,ny,nz], "origin": [x,y,z], "delta": [dx,dy,dz]}`` for a map file."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in READERS:
        raise ValueError(f"unsupported map format {ext!r}; supported: {', '.join(sorted(READERS))}")
    return READERS[ext](path)


def summarize(vol: Dict[str, object]) -> dict:
    d = np.asarray(vol["data"], dtype=float)
    delta = [abs(x) for x in vol["delta"]]                    # type: ignore[union-attr]
    voxel = float(np.prod(delta))
    nz = d[d != 0] if np.any(d != 0) else d
    return {"shape": list(d.shape), "origin": list(vol["origin"]), "spacing": list(vol["delta"]),  # type: ignore[arg-type]
            "extent_A": [float(s * x) for s, x in zip(d.shape, delta)], "min": float(d.min()), "max": float(d.max()),
            "mean": float(d.mean()), "std": float(d.std()), "integral": float(d.sum() * voxel),
            "suggested_isovalues": {"mean+1sd": float(d.mean() + d.std()), "mean+3sd": float(d.mean() + 3 * d.std()),
                                    "median_nonzero": float(np.median(nz))}}
