"""Trajectory and structure conversion, trimming, periodic-box handling and alignment, done by VMD."""
from __future__ import annotations

import os
from typing import Optional

from vmd_agent import security
from vmd_agent.vmdkit import script as S

#: trajectory formats VMD 1.9.4 can write (checked against a real VMD; xtc and netcdf are not writable by it)
TRAJ_WRITERS = ("dcd", "xyz", "pdb", "crd", "binpos", "gro", "mol2", "trr", "namdbin")
#: single-structure formats VMD can write
STRUCT_WRITERS = ("pdb", "psf", "xyz", "gro", "mol2", "namdbin")


def pbc_info(topology: str, trajectory: Optional[str] = None, first: int = 0, last: int = -1,
             step: int = 1, vmd_path: Optional[str] = None) -> dict:
    """Unit-cell lengths and angles per frame (VMD pbctools `pbc get`)."""
    first, last, step = S.frame_args(first, last, step)
    body = S.load(topology, trajectory) + ["package require pbctools",
                                            f"foreach f [framerange top {first} {last} {step}] {{ emit B $f [join [lindex [pbc get -first $f -last $f] 0] {{ }}] }}"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    boxes = [{"frame": int(r[0]), "a": float(r[1]), "b": float(r[2]), "c": float(r[3]),
              "alpha": float(r[4]), "beta": float(r[5]), "gamma": float(r[6])} for r in res["rows"]["B"]]
    has = any(b["a"] > 0 for b in boxes)
    vols = [b["a"] * b["b"] * b["c"] for b in boxes]
    return {"ok": True, "engine": "VMD pbctools", "has_unit_cell": has, "boxes": boxes,
            "orthorhombic": all(abs(b["alpha"] - 90) < 1e-3 and abs(b["beta"] - 90) < 1e-3 and abs(b["gamma"] - 90) < 1e-3
                                for b in boxes),
            "volume_change_fraction": (max(vols) - min(vols)) / max(vols) if has and max(vols) else None}


def convert(topology: str, trajectory: Optional[str], out_path: str, fmt: Optional[str] = None,
            selection: str = "all", first: int = 0, last: int = -1, step: int = 1,
            wrap: bool = False, center_selection: Optional[str] = None, align: bool = False,
            align_selection: str = "name CA", vmd_path: Optional[str] = None) -> dict:
    """Write a (sub)trajectory in another format: pick atoms, frames and stride, optionally wrap
    atoms into the unit cell (pbctools) centred on `center_selection`, and/or fit every frame to the
    first (`align`). Formats VMD can write: dcd xyz pdb crd binpos gro mol2 trr namdbin."""
    fmt = fmt or os.path.splitext(out_path)[1].lstrip(".").lower()
    S.choice(fmt, TRAJ_WRITERS, "format")
    first, last, step = S.frame_args(first, last, step)
    out = security.tcl_path(out_path)
    S.keep_inputs([out_path], [topology, trajectory])
    s1 = S.sel(selection)
    body = S.load(topology, trajectory) + ["package require pbctools",
                                            f"set frames [framerange top {first} {last} {step}]",
                                            "set all [atomselect top all]",
                                            f"set s [atomselect top {{{s1}}}]"]
    if wrap:
        cs = S.sel(center_selection or "protein")
        body += [f"pbc wrap -center com -centersel {{{cs}}} -compound residue -first {first} -last {last} -all"]
    if align:
        body += [f"set ref [atomselect top {{{S.sel(align_selection)}}} frame {first}]",
                 f"set mv [atomselect top {{{S.sel(align_selection)}}}]",
                 "foreach f $frames { $all frame $f; $mv frame $f; $all move [measure fit $mv $ref] }"]
    body += [f"animate write {fmt} {{{out}}} beg {first} end [lindex $frames end] skip {step} waitfor all sel $s",
             "emit W [llength $frames] [$s num]"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    n, atoms = res["rows"]["W"][0]
    if fmt == "pdb" and int(n) > 1 and os.path.exists(out_path):
        _standard_models(out_path)
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return {"ok": False, "error": f"VMD finished but wrote no {fmt} file; the log says: {res['log'][-200:]}"}
    return {"ok": True, "engine": "VMD animate write", "out_path": out_path, "format": fmt, "n_frames": int(n),
            "n_atoms": int(atoms), "wrapped": wrap, "aligned": align, "bytes": os.path.getsize(out_path)}


def _standard_models(path: str) -> None:
    """VMD ends each frame of a multi-frame PDB with a bare END line, which other programs (MDAnalysis, PyMOL,
    ...) do not read as separate frames. Rewrite it with the standard MODEL / ENDMDL records."""
    with open(path) as fh:
        lines = fh.read().splitlines()
    out, model, frame, header = [], 0, [], []
    for ln in lines:
        if ln.startswith("END") and not ln.startswith("ENDMDL"):
            model += 1
            out += [f"MODEL     {model:>4}"] + frame + ["ENDMDL"]
            frame = []
        elif ln.startswith(("ATOM", "HETATM", "TER")):
            frame.append(ln)
        elif not model:
            header.append(ln)
    with open(path, "w") as fh:
        fh.write("\n".join(header + out + ["END"]) + "\n")


def write_structure(topology: str, trajectory: Optional[str], out_path: str, fmt: Optional[str] = None,
                    selection: str = "all", frame: int = 0, vmd_path: Optional[str] = None) -> dict:
    """Write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin."""
    fmt = fmt or os.path.splitext(out_path)[1].lstrip(".").lower()
    S.choice(fmt, STRUCT_WRITERS, "format")
    out = security.tcl_path(out_path)
    S.keep_inputs([out_path], [topology, trajectory])
    body = S.load(topology, trajectory) + [
        f"set s [atomselect top {{{S.sel(selection)}}} frame {S.whole(frame, 'frame')}]",
        f"$s write{fmt} {{{out}}}", "emit W [$s num]"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    return {"ok": True, "engine": "VMD", "out_path": out_path, "format": fmt, "n_atoms": int(res["rows"]["W"][0][0])}
