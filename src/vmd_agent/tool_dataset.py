"""The tool test set's data: a small folder of files whose properties are known by construction.

``make_dataset(folder)`` writes, from nothing but NumPy, MDAnalysis and the bundled ffmpeg:

=======================  ======================================================================================
``protein.pdb``          one idealised chain (:mod:`vmd_agent.bench.synth`) with a buried ligand and one disulfide;
                         what it contains is recorded in ``design.json`` and measured back from the coordinates
``protein.dcd``          20 frames of that protein: frame ``i`` is the structure moved ``DRIFT_A * i`` along x, plus
                         Gaussian noise of ``NOISE_A`` per coordinate, in a cubic ``BOX_A`` box. So the
                         un-aligned RMSD after ``i`` frames is about ``DRIFT_A * i``, the aligned RMSD is about the
                         noise, the radius of gyration does not change, and the box never changes
``moved.pdb``            the protein turned and shifted by known amounts (to be fitted back into a map)
``target.dx``            a density map simulated from the protein at 8 A resolution
``blob.dx``              a Gaussian blob on a 24 x 24 x 24 grid: shape, spacing and peak value are known
``clip.mp4``             24 frames of 160 x 120 pixels at 12 frames per second, made by ffmpeg's own test pattern
                         (only if ffmpeg is available)
``figure.png``           a 200 x 150 pixel image
``scene.json``           a scene description for the VMD rendering tools
=======================  ======================================================================================

Nothing here is a recorded result: the numbers above are what the files were *built* to have. A seed does not
guarantee byte-identical files on every machine (floating point), so the checks use tolerances, never hashes.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Dict

import numpy as np

from vmd_agent.bench import synth

N_FRAMES = 20
DRIFT_A = 0.3          # angstrom of translation along x per frame
NOISE_A = 0.05         # sigma of the per-coordinate noise
BOX_A = 80.0
SPEC = {"fold": "mixed", "n_chains": 1, "ligand": "buried", "n_disulfides": 1}
CLIP = {"width": 160, "height": 120, "fps": 12, "frames": 24}
BLOB = {"shape": (24, 24, 24), "spacing": 1.0, "peak": 5.0}


def make_dataset(folder: str, seed: int = 7) -> Dict[str, object]:
    """Write the files into ``folder`` (created if needed) and return ``{"files": {...}, "design": {...}, ...}``."""
    import MDAnalysis as mda
    from MDAnalysis.coordinates.memory import MemoryReader
    from PIL import Image
    from scipy.spatial.transform import Rotation

    from vmd_agent.inputs import volume
    from vmd_agent.vmdkit import maps

    os.makedirs(folder, exist_ok=True)
    rng = np.random.default_rng(seed)
    atoms, design = synth.assemble(dict(SPEC), rng)
    pdb = synth.write_pdb(atoms, os.path.join(folder, "protein.pdb"))
    with open(os.path.join(folder, "design.json"), "w") as fh:
        json.dump(design, fh, indent=1)

    u = mda.Universe(pdb)
    base = u.atoms.positions.astype(np.float64)
    frames = np.stack([base + [DRIFT_A * i, 0.0, 0.0] + rng.normal(0.0, NOISE_A, base.shape) for i in range(N_FRAMES)])
    dims = np.tile([BOX_A, BOX_A, BOX_A, 90.0, 90.0, 90.0], (N_FRAMES, 1)).astype(np.float32)
    traj = mda.Universe(pdb)
    traj.load_new(frames.astype(np.float32), format=MemoryReader, dimensions=dims)
    dcd = os.path.join(folder, "protein.dcd")
    with mda.Writer(dcd, traj.atoms.n_atoms) as w:
        for _ in traj.trajectory:
            w.write(traj.atoms)

    prot = u.select_atoms("protein")
    xyz = prot.positions.astype(float)
    centre = xyz.mean(0)
    spacing = np.array([2.0] * 3)
    lo = xyz.min(0) - 20
    shape = tuple(np.ceil((xyz.max(0) + 20 - lo) / spacing).astype(int))
    volume.write_dx(os.path.join(folder, "target.dx"), maps._simulate(xyz, prot.masses, shape, lo, spacing, 8.0), lo, spacing)
    moved = u.copy()
    moved.atoms.positions = (Rotation.from_euler("xyz", [12, -9, 15], degrees=True).apply(moved.atoms.positions - centre)
                             + centre + np.array([3.0, -2.5, 2.0])).astype("float32")
    moved.atoms.write(os.path.join(folder, "moved.pdb"))

    grid = np.indices(BLOB["shape"]).astype(float)
    mid = (np.array(BLOB["shape"]) - 1) / 2.0
    r2 = sum((grid[i] - mid[i]) ** 2 for i in range(3))
    volume.write_dx(os.path.join(folder, "blob.dx"), BLOB["peak"] * np.exp(-r2 / (2 * 3.0 ** 2)), np.zeros(3),
                    np.array([BLOB["spacing"]] * 3))

    Image.new("RGB", (200, 150), (40, 90, 160)).save(os.path.join(folder, "figure.png"))
    with open(os.path.join(folder, "scene.json"), "w") as fh:
        json.dump({"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure"},
                            {"selection": "resname LIG", "style": "Licorice", "color": "Name"}],
                   "background": "white"}, fh, indent=1)

    files = {n: os.path.join(folder, n) for n in ("protein.pdb", "protein.dcd", "moved.pdb", "target.dx", "blob.dx",
                                                    "figure.png", "scene.json", "design.json")}
    files["clip.mp4"] = _make_clip(os.path.join(folder, "clip.mp4"))
    return {"folder": folder, "files": {k: v for k, v in files.items() if v}, "design": design, "n_atoms": int(u.atoms.n_atoms),
            "n_frames": N_FRAMES, "clip": CLIP, "blob": BLOB}


def _make_clip(path: str):
    """ffmpeg's built-in test pattern, as a real H.264 video; None when there is no ffmpeg."""
    from vmd_agent.environment import find_ffmpeg
    ff = find_ffmpeg()
    if not ff:
        return None
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"testsrc=size={CLIP['width']}x{CLIP['height']}:rate={CLIP['fps']}", "-frames:v", str(CLIP["frames"]),
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", path], capture_output=True, text=True, timeout=120)
    return path if r.returncode == 0 and os.path.getsize(path) > 0 else None
