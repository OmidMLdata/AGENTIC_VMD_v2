"""Build a tiny synthetic multi-component system + 8-frame trajectory.

Components: a 12-residue poly-ALA chain (protein), 6 waters, 2 Na + 2 Cl ions,
and one 5-carbon 'LIG' ligand. Writes sample.pdb (topology) and sample.dcd
(trajectory) so the whole vmd_agent pipeline can be tested without VMD.
"""
import os
import numpy as np
import MDAnalysis as mda
from MDAnalysis.coordinates.memory import MemoryReader

rng = np.random.default_rng(0)
here = os.path.dirname(os.path.abspath(__file__))


def build():
    atoms = []  # (name, element, resname, resid, segid)
    # --- protein: 12 ALA residues, backbone + CB ---
    bb = [("N", "N"), ("CA", "C"), ("C", "C"), ("O", "O"), ("CB", "C")]
    for r in range(1, 13):
        for name, el in bb:
            atoms.append((name, el, "ALA", r, "A"))
    # --- ligand: 5 carbons ---
    for i in range(5):
        atoms.append((f"C{i+1}", "C", "LIG", 100, "L"))
    # --- ions ---
    atoms.append(("NA", "NA", "NA", 200, "I"))
    atoms.append(("NA", "NA", "NA", 201, "I"))
    atoms.append(("CL", "CL", "CL", 202, "I"))
    atoms.append(("CL", "CL", "CL", 203, "I"))
    # --- water: 6 x (O,H,H) ---
    for w in range(6):
        atoms.append(("OW", "O", "HOH", 300 + w, "W"))
        atoms.append(("HW1", "H", "HOH", 300 + w, "W"))
        atoms.append(("HW2", "H", "HOH", 300 + w, "W"))

    n = len(atoms)
    names = [a[0] for a in atoms]
    elements = [a[1] for a in atoms]
    resnames_list = [a[2] for a in atoms]
    resids_list = [a[3] for a in atoms]
    segids_list = [a[4] for a in atoms]

    # residue bookkeeping
    res_keys, atom_resindex, res_resnames, res_resids, res_segindex = [], [], [], [], []
    seg_keys, seg_ids = [], []
    for (rn, ri, sg) in zip(resnames_list, resids_list, segids_list):
        key = (sg, ri, rn)
        if key not in res_keys:
            res_keys.append(key)
            res_resnames.append(rn); res_resids.append(ri)
            if sg not in seg_keys:
                seg_keys.append(sg); seg_ids.append(sg)
            res_segindex.append(seg_keys.index(sg))
        atom_resindex.append(res_keys.index(key))

    u = mda.Universe.empty(
        n_atoms=n, n_residues=len(res_keys), n_segments=len(seg_keys),
        atom_resindex=np.array(atom_resindex),
        residue_segindex=np.array(res_segindex), trajectory=True)
    u.add_TopologyAttr("names", names)
    u.add_TopologyAttr("elements", elements)
    u.add_TopologyAttr("types", elements)
    u.add_TopologyAttr("resnames", res_resnames)
    u.add_TopologyAttr("resids", res_resids)
    u.add_TopologyAttr("segids", seg_ids)
    u.add_TopologyAttr("chainIDs", segids_list)

    # --- base coordinates: helix-ish protein + scattered others ---
    base = np.zeros((n, 3))
    ai = 0
    for r in range(12):
        t = r * 1.5
        c = np.array([np.cos(t) * 4, np.sin(t) * 4, r * 1.5])
        offs = [(0, 0, 0), (1.2, 0, 0.3), (2.0, 1.0, 0.4),
                (2.0, 2.1, 0.4), (1.2, -1.0, 1.0)]
        for o in offs:
            base[ai] = c + np.array(o); ai += 1
    for i in range(5):  # ligand near the protein
        base[ai] = np.array([6 + i * 1.4, 2.0, 8.0]); ai += 1
    for i in range(4):  # ions
        base[ai] = np.array([-8 + i * 3, -6, 5]); ai += 1
    for w in range(6):  # waters
        c = np.array([-10 + w * 3, 8, 2.0])
        base[ai] = c; base[ai+1] = c + [0.9, 0, 0]; base[ai+2] = c + [-0.3, 0.9, 0]
        ai += 3

    # --- 8 frames: small thermal noise + slow drift of a flexible loop ---
    frames = []
    for f in range(8):
        pos = base + rng.normal(0, 0.15, size=base.shape)
        # residues 8-12 (a "loop") drift progressively -> RMSF localised there
        loop = slice(7 * 5, 12 * 5)
        pos[loop] += np.array([0.25 * f, 0.1 * f, 0.0])
        frames.append(pos)
    frames = np.array(frames, dtype=np.float32)

    u.load_new(frames, format=MemoryReader)
    u.dimensions = np.array([60, 60, 60, 90, 90, 90], dtype=np.float32)

    pdb = os.path.join(here, "sample.pdb")
    dcd = os.path.join(here, "sample.dcd")
    u.atoms.write(pdb)  # writes frame 0 as topology+coords
    with mda.Writer(dcd, n_atoms=n) as W:
        for ts in u.trajectory:
            W.write(u.atoms)
    print("wrote", pdb, "and", dcd, "  n_atoms =", n, " frames =", len(frames))
    return pdb, dcd


if __name__ == "__main__":
    build()
