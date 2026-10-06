"""Identify uploaded files and flag missing companion files.

The single most common VMD failure is loading a trajectory (DCD/XTC/...) with
no topology to supply atom names/bonds. This module classifies every path and
tells the agent exactly what, if anything, is missing.
"""
from __future__ import annotations

import os
from typing import Iterable

# extension -> (role, format, human label)
_STRUCTURE = {
    ".pdb": "PDB", ".pdbqt": "PDBQT", ".gro": "GRO", ".mol2": "MOL2",
    ".xyz": "XYZ", ".cif": "mmCIF", ".mmcif": "mmCIF", ".pqr": "PQR",
    ".psf": "PSF", ".prmtop": "AMBER prmtop", ".parm7": "AMBER prmtop",
    ".top": "GROMACS/AMBER top", ".data": "LAMMPS data", ".lammps": "LAMMPS data",
    ".car": "CAR", ".crd": "CHARMM crd", ".namdbin": "NAMD bin",
}
_TOPOLOGY_ONLY = {".psf", ".prmtop", ".parm7", ".top", ".itp", ".rtp", ".par", ".prm"}
_HAS_COORDS = {".pdb", ".pdbqt", ".gro", ".mol2", ".xyz", ".cif", ".mmcif",
               ".pqr", ".crd", ".data", ".lammps", ".car"}
_TRAJECTORY = {
    ".dcd": "CHARMM/NAMD DCD", ".xtc": "GROMACS XTC", ".trr": "GROMACS TRR",
    ".nc": "AMBER NetCDF", ".netcdf": "AMBER NetCDF", ".ncdf": "AMBER NetCDF",
    ".dump": "LAMMPS dump", ".lammpstrj": "LAMMPS dump", ".trj": "trajectory",
}
_VOLUME = {".dx": "OpenDX", ".cube": "Gaussian cube", ".ccp4": "CCP4",
           ".mrc": "MRC", ".map": "CCP4/MAP", ".situs": "Situs"}
_IMAGE = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF",
          ".tiff": "TIFF", ".bmp": "BMP", ".tga": "TARGA"}
_VIDEO = {".mp4": "MP4", ".avi": "AVI", ".mov": "MOV", ".gif": "GIF",
          ".mkv": "MKV", ".webm": "WebM", ".m4v": "M4V", ".mpg": "MPEG",
          ".mpeg": "MPEG", ".ogv": "OGV", ".wmv": "WMV"}
_SCRIPT = {".tcl": "Tcl/VMD script", ".vmd": "VMD state", ".py": "Python"}

# Trajectory format -> topology formats that pair well with it.
_TRAJ_NEEDS = {
    ".dcd": ["PSF", "PDB", "GRO", "PRMTOP"],
    ".xtc": ["GRO", "PDB", "TPR"],
    ".trr": ["GRO", "PDB", "TPR"],
    ".nc": ["PRMTOP", "PDB"],
    ".netcdf": ["PRMTOP", "PDB"],
    ".ncdf": ["PRMTOP", "PDB"],
    ".dump": ["LAMMPS data"],
    ".lammpstrj": ["LAMMPS data"],
}


def _classify_one(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else None
    entry = {"path": path, "exists": exists, "size_bytes": size,
             "ext": ext, "role": "unknown", "format": None,
             "provides_coords": False, "provides_topology": False}
    if ext in _STRUCTURE:
        entry.update(role="structure", format=_STRUCTURE[ext],
                     provides_coords=ext in _HAS_COORDS,
                     provides_topology=True)
    elif ext in _TRAJECTORY:
        entry.update(role="trajectory", format=_TRAJECTORY[ext])
    elif ext in _VOLUME:
        entry.update(role="volume", format=_VOLUME[ext])
    elif ext in _IMAGE:
        entry.update(role="image", format=_IMAGE[ext])
    elif ext in _VIDEO:
        entry.update(role="video", format=_VIDEO[ext])
    elif ext in _SCRIPT:
        entry.update(role="script", format=_SCRIPT[ext])
    if ext in _TOPOLOGY_ONLY:
        entry["provides_coords"] = False
    return entry


def inspect_files(paths: Iterable[str]) -> dict:
    """Classify a set of paths and report missing companion files.

    Returns::

        {
          "files": [ {...per-file...} ],
          "has_coordinates": bool,
          "has_topology": bool,
          "trajectories": [...],
          "missing": [ "human-readable problem", ... ],
          "load_order": [ "topology first", "then trajectory" ],
          "ready_to_load": bool,
        }
    """
    files = [_classify_one(p) for p in paths]
    missing: list[str] = []

    for f in files:
        if not f["exists"]:
            missing.append(f"File not found on disk: {f['path']}")

    has_coords = any(f["provides_coords"] for f in files if f["exists"])
    has_topology = any(f["provides_topology"] for f in files if f["exists"])
    trajs = [f for f in files if f["role"] == "trajectory"]

    # A trajectory with no coordinate/topology companion is the classic failure.
    if trajs and not (has_coords or has_topology):
        needs = sorted({n for t in trajs for n in _TRAJ_NEEDS.get(t["ext"], [])})
        missing.append(
            "Trajectory present but no topology/coordinate file to describe "
            "the atoms. Provide one of: " + ", ".join(needs) + ".")

    # DCD specifically needs bonded topology (PSF) for correct bonds/segments.
    for t in trajs:
        if t["ext"] == ".dcd":
            if not any(f["format"] == "PSF" and f["exists"] for f in files):
                missing.append(
                    "DCD trajectory loads best with a matching PSF "
                    "(a plain PDB gives coordinates but no bond/segment info).")
                break

    load_order = []
    topo = next((f for f in files if f["provides_topology"] and f["exists"]), None)
    if topo:
        load_order.append(f"Load topology first: {os.path.basename(topo['path'])}")
    for t in trajs:
        if t["exists"]:
            load_order.append(
                f"Then append trajectory: {os.path.basename(t['path'])}")

    ready = has_topology and not any("no topology" in m for m in missing)

    return {
        "files": files,
        "has_coordinates": has_coords,
        "has_topology": has_topology,
        "trajectories": [t["path"] for t in trajs],
        "images": [f["path"] for f in files if f["role"] == "image"],
        "videos": [f["path"] for f in files if f["role"] == "video"],
        "volumes": [f["path"] for f in files if f["role"] == "volume"],
        "missing": missing,
        "load_order": load_order,
        "ready_to_load": ready,
    }
