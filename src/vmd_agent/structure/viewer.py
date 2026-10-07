"""What the web page's viewer needs from a structure: atoms, bonds, and the coordinates of any frame.

The page draws the structure itself (a canvas, rotated with the mouse), so the server sends plain numbers: the atoms of one frame with
the labels used for colouring, the bonds, and later the coordinates of other frames in the same atom order. Nothing here draws.

Big systems are cut down on purpose: above ``FULL_LIMIT`` atoms only the protein's alpha carbons and the phosphorus of nucleic acids and
every atom that is neither protein, nucleic acid nor water are sent (and the payload says so), so a solvated system of 100 000 atoms
still opens at once.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from vmd_agent.inputs import molio
from vmd_agent.structure import stats

FULL_LIMIT = 40000
_WATER = set(stats._WATER_RESNAMES)

#: the order of this list is what the page's colour index means
RESTYPES = ["acidic", "basic", "polar", "nonpolar", "water", "other"]
_ACIDIC, _BASIC = {"ASP", "GLU"}, {"LYS", "ARG", "HIS", "HSD", "HSE", "HSP", "HIE", "HID", "HIP"}
_POLAR = {"SER", "THR", "ASN", "GLN", "TYR", "CYS", "CYX"}
_NONPOLAR = {"ALA", "VAL", "LEU", "ILE", "PRO", "PHE", "TRP", "MET", "GLY"}
_PROTEIN_RESNAMES = _ACIDIC | _BASIC | _POLAR | _NONPOLAR | {"MSE", "ACE", "NME", "NMA"}


def _restype(resname: str) -> int:
    r = resname.upper()
    if r in _ACIDIC:
        return 0
    if r in _BASIC:
        return 1
    if r in _POLAR:
        return 2
    if r in _NONPOLAR:
        return 3
    return 4 if r in _WATER else 5


class Model:
    """A structure (and optionally a trajectory) opened for viewing."""

    def __init__(self, topology: str, trajectory: Optional[str] = None):
        self.u = molio.load_universe(topology, trajectory)
        n_all = self.u.atoms.n_atoms
        resn = np.array([str(r).upper() for r in self.u.atoms.resnames])
        if n_all > FULL_LIMIT:
            names = np.array([str(a).upper() for a in self.u.atoms.names])
            protein = np.zeros(n_all, bool)
            protein[self.u.select_atoms("protein").indices] = True
            nucleic = np.zeros(n_all, bool)
            nucleic[self.u.select_atoms("nucleic").indices] = True
            keep = (protein & (names == "CA")) | (nucleic & (names == "P")) | (~protein & ~nucleic & ~np.isin(resn, list(_WATER)))
            self.index = np.nonzero(keep)[0]
            self.reduced = True
        else:
            self.index = np.arange(n_all)
            self.reduced = False
        self.n_all = n_all

    @property
    def n_frames(self) -> int:
        return int(self.u.trajectory.n_frames)

    def frame(self, i: int) -> np.ndarray:
        i = max(0, min(int(i), self.n_frames - 1))
        self.u.trajectory[i]
        return self.u.atoms.positions[self.index].astype(float)

    def describe(self) -> Dict[str, object]:
        ag = self.u.atoms[self.index]
        elements = stats._elements(ag)
        resn = [str(r) for r in ag.resnames]
        chains = [str(c).strip() or str(s) for c, s in zip(getattr(ag, "chainIDs", ag.segids), ag.segids)]
        pos = ag.positions.astype(float)
        bonds: List[List[int]] = []
        method = "none (a reduced view)"
        if not self.reduced:
            pairs, method = stats._infer_bonds(ag, elements, box=None)
            if pairs is not None:
                bonds = np.asarray(pairs, int).tolist()
        names = [str(n) for n in ag.names]
        uniq = lambda seq: sorted(set(seq))     # noqa: E731
        els, rns, chs = uniq(elements.tolist()), uniq(resn), uniq(chains)
        centre = pos.mean(0) if len(pos) else np.zeros(3)
        radius = float(np.linalg.norm(pos - centre, axis=1).max()) if len(pos) else 1.0
        return {"n_atoms": int(len(ag)), "n_atoms_total": int(self.n_all), "reduced": self.reduced, "frames": self.n_frames,
                "xyz": np.round(pos, 2).ravel().tolist(), "elements": els, "element": [els.index(e) for e in elements.tolist()],
                "resnames": rns, "resname": [rns.index(r) for r in resn], "restype": [_restype(r) for r in resn], "restypes": RESTYPES,
                "chains": chs, "chain": [chs.index(c) for c in chains], "resid": [int(r) for r in ag.resids],
                "is_ca": [n == "CA" for n in names], "is_protein": [bool(x) for x in np.isin(np.asarray(resn), list(_PROTEIN_RESNAMES))],
                "is_water": [r in _WATER for r in resn], "bonds": bonds, "bond_method": method,
                "centre": np.round(centre, 2).tolist(), "radius": round(radius, 2),
                "box": [float(x) for x in self.u.dimensions[:3]] if self.u.dimensions is not None and self.u.dimensions[0] > 0 else None}

