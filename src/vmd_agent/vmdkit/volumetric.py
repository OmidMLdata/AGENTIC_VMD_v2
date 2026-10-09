"""Density maps: build them from a trajectory with VMD's volmap, and read any map file."""
from __future__ import annotations

from typing import Optional

from vmd_agent import security
from vmd_agent.inputs.volume import read_volume, summarize
from vmd_agent.vmdkit import script as S

KINDS = {"density": "smeared atom density (mass- or number-weighted) averaged over frames",
         "occupancy": "fraction of frames in which each voxel is occupied by the selection",
         "distance": "distance from each voxel to the nearest atom of the selection",
         "mask": "1 near the selection, 0 elsewhere (within `cutoff`)",
         "electrostatic": "PME electrostatic potential (kT/e) of the whole system at frame `first`; needs partial charges (PSF)"}


def volmap(topology: str, trajectory: Optional[str], out_dx: str, kind: str = "density",
           selection: str = "protein", resolution: float = 1.0, mass_weighted: bool = True,
           first: int = 0, last: int = -1, step: int = 1, cutoff: float = 2.0,
           vmd_path: Optional[str] = None) -> dict:
    """Compute a 3-D map with VMD `volmap` and report its statistics."""
    S.choice(kind, list(KINDS), "kind")
    first, last, step = S.frame_args(first, last, step)
    out = security.tcl_path(out_dx)
    S.keep_inputs([out_dx], [topology, trajectory])
    if kind == "electrostatic":
        body = S.load(topology, trajectory) + [
            "package require pmepot", f"animate goto {first}",
            f"pmepot -mol top -frames {first} -ewaldfactor 0.25 -grid {S.num(resolution, 'resolution')} -dxfile {{{out}}}",
            "emit OK [measure sumweights [atomselect top all] weight charge]"]
        res = S.run(body, vmd_path, timeout=1800)
        if not res["ok"]:
            return {"ok": False, "error": res.get("error")}
        info = summarize(read_volume(out_dx))
        return {"ok": True, "engine": "VMD pmepot", "kind": kind, "map_path": out_dx,
                "net_charge": float(res["rows"]["OK"][0][0]), **info,
                "note": "Units kT/e at 300 K. Meaningful only with real partial charges (a PSF) and a unit cell."}
    res_ = S.num(resolution, "resolution")
    w = "-weight mass" if mass_weighted and kind == "density" else ""
    extra = {"density": f"-res {res_} {w} -combine avg", "occupancy": f"-res {res_} -combine avg",
             "distance": f"-res {res_} -combine avg", "mask": f"-res {res_} -cutoff {S.num(cutoff, 'cutoff')} -combine avg"}[kind]
    body = S.load(topology, trajectory) + [
        # volmap has no frame-range option: drop the frames we do not want, then average over the rest
        f"set keep [framerange top {first} {last} {step}]",
        "for {set f [expr {[molinfo top get numframes] - 1}]} {$f >= 0} {incr f -1} {",
        "  if {[lsearch -exact $keep $f] < 0} { animate delete beg $f end $f top }", "}",
        f"set s [atomselect top {{{S.sel(selection)}}}]", 'progress "computing the map"',
        f"volmap {kind} $s {extra} -allframes -mol top -o {{{out}}}",
        "emit OK [molinfo top get numframes]"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    info = summarize(read_volume(out_dx))
    return {"ok": True, "engine": "VMD volmap", "kind": kind, "map_path": out_dx, **info,
            "how_to_view": "vmd_render_scene with an isosurface layer, or open the .dx file in VMD as an Isosurface representation."}


def volume_info(path: str) -> dict:
    """What a density map file contains (OpenDX, CCP4/MRC, cube, Situs): grid, range, integral, suggested levels."""
    try:
        return {"ok": True, **summarize(read_volume(path))}
    except (ValueError, OSError) as e:
        return {"ok": False, "error": str(e)}
