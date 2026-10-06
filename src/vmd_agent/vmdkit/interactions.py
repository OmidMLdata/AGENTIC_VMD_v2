"""Hydrogen bonds, salt bridges and contacts over a trajectory, from VMD's geometric measures.

Per-frame lists from VMD are collapsed into *persistence*: which pairs exist, in what fraction of
the frames, so the answer is "this bond is present 83 % of the time", not a list of snapshots.
"""
from __future__ import annotations

from typing import Dict, Optional

from vmd_agent.vmdkit import script as S

KINDS = ("hbonds", "salt_bridges", "contacts")

# acidic oxygens vs basic nitrogens (the criterion of VMD's saltbr plugin: oxygen-nitrogen distance)
_ACID = "(resname ASP and name OD1 OD2) or (resname GLU and name OE1 OE2)"
_BASE = "(resname LYS and name NZ) or (resname ARG and name NE NH1 NH2) or (resname HSP and name ND1 NE2)"


def interactions(topology: str, trajectory: Optional[str] = None, kind: str = "hbonds",
                 selection: str = "protein", selection2: Optional[str] = None,
                 cutoff: float = 0.0, angle_cutoff: float = 20.0,
                 first: int = 0, last: int = -1, step: int = 1, top: int = 15,
                 vmd_path: Optional[str] = None) -> dict:
    """Persistent hydrogen bonds / salt bridges / atom contacts between selections.

    hbonds: VMD `measure hbonds` (default cutoff 3.0 A, angle 20 deg from linear); salt_bridges:
    acidic O to basic N within the cutoff (default 4.0 A); contacts: atom pairs within the cutoff
    (default 4.0 A) between `selection` and `selection2`."""
    S.choice(kind, KINDS, "kind")
    first, last, step = S.frame_args(first, last, step)
    s1 = S.sel(selection)
    s2 = S.sel(selection2) if selection2 else None
    if kind == "contacts" and not s2:
        s2 = s1
    cut = S.num(cutoff or (3.0 if kind == "hbonds" else 4.0), "cutoff")
    body = S.load(topology, trajectory) + [f"set frames [framerange top {first} {last} {step}]",
                                            "emit INFO [llength $frames]"]
    if kind == "hbonds":
        body += [f"set a [atomselect top {{{s1}}}]"]
        if s2:
            body += [f"set b [atomselect top {{{s2}}}]"]
        call = f"measure hbonds {cut} {S.num(angle_cutoff, 'angle_cutoff')} $a" + (" $b" if s2 else "")
        body += ["foreach f $frames {", "  $a frame $f" + ("; $b frame $f" if s2 else ""),
                 f"  set h [{call}]",
                 "  foreach d [lindex $h 0] ac [lindex $h 1] {",
                 "    set x [atomselect top \"index $d\"]; set y [atomselect top \"index $ac\"]",
                 "    set dd [lindex [$x get {resname resid name}] 0]; set aa [lindex [$y get {resname resid name}] 0]",
                 "    emit P $f [join $dd :] [join $aa :]; $x delete; $y delete",
                 "  }", "}"]
    else:
        a_sel, b_sel = (f"({_ACID}) and ({s1})", f"({_BASE}) and ({s1})") if kind == "salt_bridges" else (s1, s2)
        body += [f"set a [atomselect top {{{a_sel}}}]", f"set b [atomselect top {{{b_sel}}}]",
                 "foreach f $frames {", "  $a frame $f; $b frame $f",
                 f"  set c [measure contacts {cut} $a $b]",
                 "  set seen {}",
                 "  foreach i [lindex $c 0] j [lindex $c 1] {",
                 "    set x [atomselect top \"index $i\"]; set y [atomselect top \"index $j\"]",
                 "    set u [lindex [$x get {resname resid}] 0]; set v [lindex [$y get {resname resid}] 0]",
                 "    set key \"[join $u :]|[join $v :]\"",
                 "    if {[lsearch -exact $seen $key] < 0} { lappend seen $key; emit P $f [join $u :] [join $v :] }",
                 "    $x delete; $y delete", "  }",
                 "  emit N $f [llength [lindex $c 0]]", "}"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "kind": kind, "error": res.get("error"), "log": res.get("log", "")[-500:]}
    nframes = int(res["rows"]["INFO"][0][0])
    seen: Dict[tuple, set] = {}
    per_frame: Dict[int, int] = {}
    for r in res["rows"].get("P", []):
        seen.setdefault((r[1], r[2]), set()).add(int(r[0]))
    for f in range(first, first + nframes * step, step):
        per_frame[f] = 0
    for r in res["rows"].get("P", []):
        per_frame[int(r[0])] = per_frame.get(int(r[0]), 0) + 1
    pairs = sorted(({"a": a, "b": b, "occupancy": len(fr) / nframes, "frames_present": len(fr)}
                    for (a, b), fr in seen.items()), key=lambda d: -d["occupancy"])
    counts = list(per_frame.values())
    return {"ok": True, "kind": kind, "engine": "VMD measure", "n_frames": nframes,
            "n_pairs_ever": len(pairs), "mean_per_frame": sum(counts) / max(1, len(counts)),
            "per_frame": [{"frame": f, "count": c} for f, c in per_frame.items()],
            "most_persistent": pairs[:max(1, int(top))],
            "note": "donor/first residue is `a` (resname:resid:atom for hbonds); occupancy = fraction of analysed frames."}
