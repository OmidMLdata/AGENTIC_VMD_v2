"""Structure-level checks done by VMD itself: secondary structure over time, backbone torsions,
the structurecheck plugin (chirality, cis peptides, chain gaps), and superposition of two structures."""
from __future__ import annotations

from typing import Optional

from vmd_agent import security
from vmd_agent.vmdkit import script as S

# VMD's structure letters (STRIDE-style) grouped into three classes
HELIX, STRAND = set("HGI"), set("EB")


def secondary_structure(topology: str, trajectory: Optional[str] = None, selection: str = "protein",
                        first: int = 0, last: int = -1, step: int = 1,
                        vmd_path: Optional[str] = None) -> dict:
    """Per-frame secondary structure by VMD (`mol ssrecalc`, STRIDE): helix/strand/other
    fractions per frame and per-residue persistence (the data behind VMD's Timeline plugin)."""
    first, last, step = S.frame_args(first, last, step)
    s1 = S.sel(selection)
    body = S.load(topology, trajectory) + [
        f"set s [atomselect top {{({s1}) and name CA}}]",
        "emit RES [join [$s get resid] { }]", "emit NAME [join [$s get resname] { }]",
        f"foreach f [framerange top {first} {last} {step}] {{",
        "  animate goto $f; mol ssrecalc top; $s frame $f; $s update",
        "  emit SS $f [join [$s get structure] {}]", "}"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error"), "log": res.get("log", "")[-400:]}
    rows = res["rows"]
    resid = [int(x) for x in rows["RES"][0]]
    names = rows["NAME"][0]
    frames = [(int(r[0]), r[1]) for r in rows.get("SS", [])]
    n = len(resid)
    per_frame, helix_n, strand_n = [], [0] * n, [0] * n
    for f, ss in frames:
        h = sum(c in HELIX for c in ss)
        e = sum(c in STRAND for c in ss)
        per_frame.append({"frame": f, "helix": h / n, "strand": e / n, "other": 1 - (h + e) / n, "codes": ss})
        for i, c in enumerate(ss):
            helix_n[i] += c in HELIX
            strand_n[i] += c in STRAND
    nf = max(1, len(frames))
    per_res = [{"resid": resid[i], "resname": names[i], "helix": helix_n[i] / nf, "strand": strand_n[i] / nf}
               for i in range(n)]
    return {"ok": True, "engine": "VMD ssrecalc (STRIDE)", "n_residues": n, "n_frames": len(frames),
            "per_frame": per_frame, "per_residue": per_res,
            "mean_helix": sum(p["helix"] for p in per_frame) / nf,
            "mean_strand": sum(p["strand"] for p in per_frame) / nf,
            "legend": "H alpha, G 3-10, I pi (helix); E strand, B bridge; T turn; C coil"}


def _rama_class(resname: str, phi: float, psi: float) -> str:
    """Coarse Ramachandran region. Boxes, not contours: a screening aid, not a validation score."""
    if resname == "GLY":
        return "allowed"
    if -160 <= phi <= -45 and -80 <= psi <= 10:
        return "favoured"          # right-handed helix
    if -180 <= phi <= -45 and (psi >= 90 or psi <= -150):
        return "favoured"          # beta / PPII
    if 30 <= phi <= 90 and 0 <= psi <= 90:
        return "allowed"           # left-handed helix
    if phi < 0:
        return "allowed"
    return "outlier"


def backbone_torsions(topology: str, trajectory: Optional[str] = None, selection: str = "protein",
                      frame: int = 0, vmd_path: Optional[str] = None) -> dict:
    """phi/psi (VMD) of one frame, classified into coarse Ramachandran regions."""
    s1 = S.sel(selection)
    body = S.load(topology, trajectory) + [
        f"set s [atomselect top {{({s1}) and name CA}} frame {S.whole(frame, 'frame')}]",
        "foreach r [$s get {resid resname phi psi}] { emit T [join $r { }] }"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    out, counts = [], {"favoured": 0, "allowed": 0, "outlier": 0}
    for r in res["rows"].get("T", []):
        phi, psi = float(r[2]), float(r[3])
        if abs(phi) < 1e-6 or abs(psi) < 1e-6:     # chain ends have no phi or psi
            continue
        cls = _rama_class(r[1], phi, psi)
        counts[cls] += 1
        out.append({"resid": int(r[0]), "resname": r[1], "phi": phi, "psi": psi, "region": cls})
    n = max(1, len(out))
    return {"ok": True, "engine": "VMD", "frame": frame, "n_residues": len(out), "counts": counts,
            "fraction_favoured": counts["favoured"] / n, "outliers": [o for o in out if o["region"] == "outlier"],
            "residues": out,
            "caveat": "Regions are coarse boxes (not MolProbity contours); use them to find residues to look at."}


def structure_check(topology: str, trajectory: Optional[str] = None, selection: str = "protein",
                    frame: int = 0, vmd_path: Optional[str] = None) -> dict:
    """VMD's structurecheck plugin: chirality errors, cis peptide bonds and chain gaps in one frame."""
    s1 = S.sel(selection)
    body = S.load(topology, trajectory) + [
        "package require structurecheck", f"animate goto {S.whole(frame, 'frame')}",
        f"set sel {{({s1}) and protein}}",
        "set c [StrctCheck::checkChirality top \"$sel\"]; emit CHIRAL [lindex $c 0]",
        "set c [StrctCheck::checkCisPeptide top \"$sel\"]; emit CIS [lindex $c 0]",
        "set g [StrctCheck::checkGaps top \"$sel\"]; emit GAPS [llength $g]"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error"), "log": res.get("log", "")[-400:]}
    r = res["rows"]
    return {"ok": True, "engine": "VMD structurecheck plugin", "frame": frame,
            "chirality_errors": int(r["CHIRAL"][0][0]), "cis_peptides": int(r["CIS"][0][0]),
            "chain_gaps": int(r["GAPS"][0][0]),
            "note": "Cis peptides are normal before proline but rare elsewhere; chirality errors mean a wrong stereocentre."}


def align_structures(mobile: str, reference: str, mobile_selection: str = "name CA",
                     reference_selection: Optional[str] = None, out_pdb: Optional[str] = None,
                     vmd_path: Optional[str] = None) -> dict:
    """Superpose `mobile` onto `reference` with VMD (`measure fit`) and report the RMSD; optionally
    write the moved structure. The two selections must have the same number of atoms."""
    ms = S.sel(mobile_selection)
    rs = S.sel(reference_selection or mobile_selection)
    out = security.tcl_path(out_pdb) if out_pdb else None
    S.keep_inputs([out_pdb], [mobile, reference])
    body = S.load(reference) + ["set refmol [molinfo top get id]"] + S.load(mobile) + [
        "set mobmol [molinfo top get id]",
        f"set a [atomselect $mobmol {{{ms}}}]", f"set b [atomselect $refmol {{{rs}}}]",
        'if {[$a num] != [$b num]} { error "selections differ in size: [$a num] vs [$b num] atoms" }',
        "set before [measure rmsd $a $b]", "set M [measure fit $a $b]",
        "set all [atomselect $mobmol all]", "$all move $M", "set after [measure rmsd $a $b]",
        "emit R [$a num] $before $after"]
    if out:
        body.append(f"$all writepdb {{{out}}}")
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    n, before, after = res["rows"]["R"][0]
    return {"ok": True, "engine": "VMD measure fit", "n_atoms_fitted": int(n), "rmsd_before": float(before),
            "rmsd_after": float(after), "aligned_pdb": out_pdb}
