"""VMD's own ``measure`` family, run headless: the numbers a VMD user would get in the Tk console.

Each kind builds a Tcl loop over frames, runs it in real VMD and returns the series plus a summary.
Where an independent implementation exists (MDAnalysis/NumPy) the tests compare against it.
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from vmd_agent import security
from vmd_agent.vmdkit import script as S

#: kind -> what it needs (used for validation and for the tool's description)
KINDS: Dict[str, str] = {
    "rgyr": "radius of gyration of `selection` per frame (mass-weighted by default)",
    "sasa": "solvent-accessible surface area of `selection` per frame (probe_radius, default 1.4 A)",
    "center": "centre (of mass by default) of `selection` per frame",
    "minmax": "bounding box of `selection` per frame",
    "inertia": "principal moments of inertia of `selection` per frame",
    "rmsd": "RMSD of `selection` to reference_frame, after fitting when align=True",
    "rmsf": "per-atom fluctuation of `selection` over the frame range (align=True fits every frame first)",
    "distance": "distance between the centres of `selection` and `selection2` per frame",
    "angle": "angle at `selection2` between the single atoms `selection`, `selection2`, `selection3`",
    "dihedral": "dihedral of the four single atoms `selection`..`selection4`",
    "contacts": "number of atom pairs closer than `cutoff` between `selection` and `selection2` per frame",
    "hbonds": "number of hydrogen bonds (VMD geometric criterion: cutoff A, angle-cutoff deg) per frame",
    "gofr": "radial distribution g(r) of `selection2` around `selection`, averaged over the frames",
    "cluster": "group the frames by RMSD of `selection` (num_clusters, cutoff)",
}
SINGLE_ATOM = ("angle", "dihedral")


def _stats(vals: List[float]) -> dict:
    if not vals:
        return {}
    return {"mean": statistics.fmean(vals), "std": statistics.pstdev(vals), "min": min(vals), "max": max(vals)}


def measure(topology: str, trajectory: Optional[str] = None, kind: str = "rgyr",
            selection: str = "protein", selection2: Optional[str] = None,
            selection3: Optional[str] = None, selection4: Optional[str] = None,
            first: int = 0, last: int = -1, step: int = 1, reference_frame: int = 0,
            align: bool = True, mass_weighted: bool = True, probe_radius: float = 1.4,
            cutoff: float = 3.0, angle_cutoff: float = 20.0, delta: float = 0.1, rmax: float = 10.0,
            num_clusters: int = 3, vmd_path: Optional[str] = None) -> dict:
    """Run one of VMD's ``measure`` computations headless over a trajectory (see KINDS)."""
    S.choice(kind, list(KINDS), "kind")
    first, last, step = S.frame_args(first, last, step)
    ref = S.whole(reference_frame, "reference_frame")
    s1 = S.sel(selection)
    extra = [x for x in (selection2, selection3, selection4)]
    need = {"distance": 2, "contacts": 1, "hbonds": 1, "gofr": 2, "angle": 3, "dihedral": 4}.get(kind, 1)
    given = [x for x in extra if x]
    if kind in ("distance", "angle", "dihedral", "gofr") and len(given) < need - 1:
        raise security.InvalidInput(f"{kind} needs {need} selections")
    if kind == "contacts" and not selection2:
        selection2 = selection
    s2 = S.sel(selection2) if selection2 else None
    s3 = S.sel(selection3) if selection3 else None
    s4 = S.sel(selection4) if selection4 else None
    w = " weight mass" if mass_weighted else ""
    body = S.load(topology, trajectory) + [
        f"set s1 [atomselect top {{{s1}}}]",
        'emit INFO natoms [$s1 num] nframes [molinfo top get numframes]',
        f"set frames [framerange top {first} {last} {step}]",
    ]
    if s2:
        body.append(f"set s2 [atomselect top {{{s2}}}]")
    if s3:
        body.append(f"set s3 [atomselect top {{{s3}}}]")
    if s4:
        body.append(f"set s4 [atomselect top {{{s4}}}]")
    loop = ["foreach f $frames {", "  $s1 frame $f"]
    if kind == "rgyr":
        loop += [f"  emit V $f [measure rgyr $s1{w}]"]
    elif kind == "sasa":
        loop += [f"  emit V $f [measure sasa {S.num(probe_radius, 'probe_radius')} $s1]"]
    elif kind == "center":
        loop += [f"  emit V $f [measure center $s1{w}]"]
    elif kind == "minmax":
        loop += ["  emit V $f [join [join [measure minmax $s1] { }] { }]"]
    elif kind == "inertia":
        loop += ["  emit V $f [join [lindex [measure inertia $s1 eigenvals] 2] { }]"]
    elif kind == "rmsd":
        loop = [f"set ref [atomselect top {{{s1}}} frame {ref}]", "set all [atomselect top all]"] + loop
        if align:
            loop += ["  $all frame $f", f"  $all move [measure fit $s1 $ref{w}]"]
        loop += [f"  emit V $f [measure rmsd $s1 $ref{w}]"]
    elif kind == "rmsf":
        loop = []
    elif kind == "distance":
        loop += ["  $s2 frame $f", f"  emit V $f [veclength [vecsub [measure center $s1{w}] [measure center $s2{w}]]]"]
    elif kind in SINGLE_ATOM:
        names = ["s1", "s2", "s3", "s4"][: 3 if kind == "angle" else 4]
        loop = []
        body += [f'if {{[${n} num] != 1}} {{ error "{kind}: every selection must be exactly one atom" }}' for n in names]
        idx = " ".join(f"[list [${n} get index] [molinfo top get id]]" for n in names)
        loop = ["foreach f $frames {"] + [f"  ${n} frame $f" for n in names] + [
            f"  emit V $f [measure {'angle' if kind == 'angle' else 'dihed'} [list {idx}] frame $f]"]
    elif kind == "contacts":
        loop += ["  $s2 frame $f", f"  emit V $f [llength [lindex [measure contacts {S.num(cutoff, 'cutoff')} $s1 $s2] 0]]"]
    elif kind == "hbonds":
        loop += [f"  emit V $f [llength [lindex [measure hbonds {S.num(cutoff, 'cutoff')} {S.num(angle_cutoff, 'angle_cutoff')} $s1] 0]]"]
    if kind == "rmsf":
        body += [f"set ref [atomselect top {{{s1}}} frame {ref}]", "set all [atomselect top all]"]
        if align:
            body += ["foreach f $frames { $all frame $f; $s1 frame $f; " + f"$all move [measure fit $s1 $ref{w}] }}"]
        body += [f"set r [measure rmsf $s1 first {first} last {last} step {step}]",
                 "set ids [$s1 get {resname resid name}]", "set k 0",
                 "foreach v $r id $ids { emit A $k [lindex $id 0] [lindex $id 1] [lindex $id 2] $v; incr k }"]
    elif kind == "gofr":
        body += ["package require pbctools",
                 f"set g [measure gofr $s1 $s2 delta {S.num(delta, 'delta')} rmax {S.num(rmax, 'rmax')} "
                 f"usepbc [expr {{[lindex [pbc get -first {first}] 0 0] > 0}}] selupdate 0 first {first} last {last} step {step}]",
                 "foreach r [lindex $g 0] v [lindex $g 1] { emit G $r $v }"]
    elif kind == "cluster":
        body += [f"set c [measure cluster $s1 num {S.whole(num_clusters, 'num_clusters')} cutoff {S.num(cutoff, 'cutoff')} "
                 f"first {first} last {last} step {step} distfunc rmsd{w}]",
                 "set i 0", "foreach cl $c { emit C $i [llength $cl] [join $cl { }]; incr i }"]
    else:
        body += loop + ["}"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "kind": kind, "error": res.get("error"), "log": res.get("log", "")[-600:]}
    rows = res["rows"]
    info = rows.get("INFO", [[]])[0]
    out = {"ok": True, "kind": kind, "selection": s1, "n_atoms": int(info[1]), "n_frames_loaded": int(info[3]),
           "engine": "VMD measure"}
    if kind in ("rmsf",):
        atoms = [{"index": int(r[0]), "resname": r[1], "resid": int(r[2]), "name": r[3], "rmsf": float(r[4])}
                 for r in rows.get("A", [])]
        out["per_atom"] = atoms
        out["summary"] = _stats([a["rmsf"] for a in atoms])
        out["most_mobile"] = sorted(atoms, key=lambda a: -a["rmsf"])[:5]
    elif kind == "gofr":
        out["r"] = [float(r[0]) for r in rows.get("G", [])]
        out["g"] = [float(r[1]) for r in rows.get("G", [])]
        out["note"] = "g(r) uses periodic boundaries when the file has a unit cell."
    elif kind == "cluster":
        out["clusters"] = [{"id": int(r[0]), "size": int(r[1]), "frames": [int(x) for x in r[2:]]}
                           for r in rows.get("C", []) if int(r[1]) > 0]
    else:
        vals = rows.get("V", [])
        out["frames"] = [int(r[0]) for r in vals]
        if kind in ("center", "minmax", "inertia"):
            out["values"] = [S.floats(r[1:]) for r in vals]
        else:
            out["values"] = [float(r[1]) for r in vals]
            out["summary"] = _stats(out["values"])
        out["units"] = {"inertia": "amu*A^2", "rgyr": "A", "sasa": "A^2", "rmsd": "A", "distance": "A", "angle": "degrees",
                        "dihedral": "degrees", "contacts": "pairs", "hbonds": "bonds"}.get(kind, "")
    return out
