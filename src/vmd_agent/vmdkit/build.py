"""Build simulation-ready systems with VMD's psfgen, solvate and autoionize, and mutate residues.

The CHARMM36 topology files come from the VMD installation itself (readcharmmtop plugin), so
nothing is downloaded. Only standard protein is parameterised here; everything else in the
input (ligands, nucleic acids, lipids, crystal waters) is reported as excluded, never silently
dropped.
"""
from __future__ import annotations

import os
from typing import Optional

from vmd_agent import security
from vmd_agent.vmdkit import script as S

_TOPDIR = "[file join $::env(VMDDIR) plugins noarch tcl readcharmmtop1.2]"


def _prefix(out_prefix: str) -> str:
    p = security.tcl_path(out_prefix)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def build_system(input_pdb: str, out_prefix: str, selection: str = "protein", solvate: bool = True,
                 padding: float = 10.0, ionize: bool = True, salt_concentration: float = 0.15,
                 histidine: str = "HSD", vmd_path: Optional[str] = None) -> dict:
    """PDB -> CHARMM36 PSF/PDB (psfgen), then a water box (solvate) and neutralising ions at the given
    salt concentration (autoionize). Writes `<out_prefix>.psf/.pdb` (the dry protein) and, when asked,
    `<out_prefix>_wat.*` and `<out_prefix>_ion.*`. Reports charge, atom counts, box size and what was left out."""
    S.choice(histidine, ("HSD", "HSE", "HSP"), "histidine")
    pre = _prefix(out_prefix)
    S.keep_inputs([pre + ext for ext in (".psf", ".pdb", "_wat.psf", "_wat.pdb", "_ion.psf", "_ion.pdb")], [input_pdb])
    sel = S.sel(selection)
    pad, conc = S.num(padding, "padding"), S.num(salt_concentration, "salt_concentration")
    if pad <= 0 or conc < 0:
        raise security.InvalidInput("padding must be positive and salt_concentration >= 0")
    body = S.load(input_pdb) + [
        "package require psfgen", "package require solvate", "package require autoionize",
        f"set td {_TOPDIR}",
        "topology [file join $td top_all36_prot.rtf]", "topology [file join $td toppar_water_ions_namd.str]",
        f"pdbalias residue HIS {histidine}", "pdbalias atom ILE CD1 CD",
        'progress "reading the protein"',
        f"set prot [atomselect top {{({sel}) and protein}}]",
        f"set other [atomselect top {{not (({sel}) and protein)}}]",
        'emit EXCL [$other num] [join [lsort -unique [$other get resname]] ,]',
        'if {[$prot num] == 0} { error "no protein atoms in the selection" }',
        "set chains [lsort -unique [$prot get chain]]", "set i 0",
        "foreach ch $chains {",
        '  set c [atomselect top "(protein) and chain \\"$ch\\""]',
        f'  $c writepdb "{pre}_chain$i.pdb"',
        f'  segment P$i {{pdb "{pre}_chain$i.pdb"}}', f'  coordpdb "{pre}_chain$i.pdb" P$i',
        "  incr i", "}",
        'progress "placing missing atoms (psfgen)"', "guesscoord", f'writepsf "{pre}.psf"', f'writepdb "{pre}.pdb"',
        "emit CHAINS $i"]
    final = pre
    if solvate:
        body += ['progress "adding a water box (solvate; this is the slow step)"',
                 f'solvate "{pre}.psf" "{pre}.pdb" -t {pad} -o "{pre}_wat"']
        final = pre + "_wat"
        if ionize:
            body += ['progress "adding ions (autoionize)"', f'autoionize -psf "{pre}_wat.psf" -pdb "{pre}_wat.pdb" -sc {conc} -o "{pre}_ion"']
            final = pre + "_ion"
    body += [f'mol new "{final}.psf" type psf waitfor all', f'mol addfile "{final}.pdb" type pdb waitfor all',
             "set all [atomselect top all]", "set q [measure sumweights $all weight charge]",
             "set mm [measure minmax $all]",
             "emit SYS [$all num] [[atomselect top {water and name OH2}] num] "
             "[[atomselect top {resname SOD CLA}] num] $q [join [join $mm { }] { }]"]
    res = S.run(body, vmd_path, timeout=1800)
    for tmp in range(int(res["rows"].get("CHAINS", [["0"]])[0][0]) if res["ok"] else 0):
        try:
            os.remove(f"{out_prefix}_chain{tmp}.pdb")
        except OSError:
            pass
    if not res["ok"]:
        return {"ok": False, "error": res.get("error"), "log": res.get("log", "")[-500:]}
    atoms, waters, ions, q, *box = res["rows"]["SYS"][0]
    excl = res["rows"]["EXCL"][0]
    mn, mx = [float(x) for x in box[:3]], [float(x) for x in box[3:6]]
    return {"ok": True, "engine": "VMD psfgen/solvate/autoionize", "force_field": "CHARMM36",
            "final_psf": final + ".psf", "final_pdb": final + ".pdb",
            "n_chains": int(res["rows"]["CHAINS"][0][0]), "n_atoms": int(atoms), "n_waters": int(waters),
            "n_ions": int(ions), "net_charge": round(float(q), 4),
            "box_size_A": [round(b - a, 2) for a, b in zip(mn, mx)],
            "excluded_atoms": int(excl[0]), "excluded_residue_names": excl[1].split(",") if len(excl) > 1 else [],
            "warning": ("Excluded atoms (ligands, nucleic acids, crystal water, ...) are NOT in the system; "
                        "parametrise them separately.") if int(excl[0]) else None}


def mutate_residue(psf: str, pdb: str, out_prefix: str, segid: str, resid: int, new_resname: str,
                   vmd_path: Optional[str] = None) -> dict:
    """Mutate one residue in a PSF/PDB pair with VMD's mutator plugin (psfgen based)."""
    S.choice(new_resname, ("ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HSD", "HSE", "HSP", "ILE",
                           "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL"), "new_resname")
    seg = security.tcl_word(segid, "segid")
    pre = _prefix(out_prefix)
    S.keep_inputs([pre + ".psf", pre + ".pdb"], [psf, pdb])
    body = ["package require mutator",
            f'mutator -psf "{security.tcl_path(psf)}" -pdb "{security.tcl_path(pdb)}" -o "{pre}" '
            f"-ressegname {seg} -resid {S.whole(resid, 'resid')} -mut {new_resname}",
            f'mol new "{pre}.psf" type psf waitfor all', f'mol addfile "{pre}.pdb" type pdb waitfor all',
            f'set r [atomselect top "segname {seg} and resid {int(resid)} and name CA"]',
            "emit M [[atomselect top all] num] [$r get resname]"]
    res = S.run(body, vmd_path, timeout=900)
    if not res["ok"]:
        hint = (" Mutate the dry system (vmd_build_system with solvate=false), then solvate: the mutator plugin failed on a solvated one."
                if "topology file" in str(res.get("error")) else "")
        return {"ok": False, "error": str(res.get("error")) + hint, "log": res.get("log", "")[-400:]}
    n, rn = res["rows"]["M"][0]
    if rn != new_resname:
        return {"ok": False, "error": f"mutation did not take effect (residue is still {rn})"}
    return {"ok": True, "engine": "VMD mutator", "psf": pre + ".psf", "pdb": pre + ".pdb",
            "n_atoms": int(n), "new_resname": rn}


def merge_structures(psf_a: str, pdb_a: str, psf_b: str, pdb_b: str, out_prefix: str,
                     vmd_path: Optional[str] = None) -> dict:
    """Combine two PSF/PDB systems into one (VMD topotools `mergemols`); writes `<out_prefix>.psf/.pdb`."""
    pre = _prefix(out_prefix)
    S.keep_inputs([pre + ".psf", pre + ".pdb"], [psf_a, pdb_a, psf_b, pdb_b])

    def load(psf, pdb):
        return [f'mol new "{security.tcl_path(psf)}" type psf waitfor all',
                f'mol addfile "{security.tcl_path(pdb)}" type pdb waitfor all', "lappend ids [molinfo top get id]"]
    body = ["package require topotools", "set ids {}"] + load(psf_a, pdb_a) + load(psf_b, pdb_b) + [
        "set m [::TopoTools::mergemols $ids]", "set all [atomselect $m all]",
        f'$all writepsf "{pre}.psf"', f'$all writepdb "{pre}.pdb"',
        "emit MERGED [$all num] [llength [lsort -unique [$all get segname]]]"]
    res = S.run(body, vmd_path, timeout=900)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    n, segs = res["rows"]["MERGED"][0]
    return {"ok": True, "engine": "VMD topotools", "psf": pre + ".psf", "pdb": pre + ".pdb", "n_atoms": int(n),
            "n_segments": int(segs),
            "warning": ("both systems use the same segment name(s), so they now share them: rename one before "
                        "simulating") if int(segs) < 2 else None}


def build_membrane(out_prefix: str, lipid: str = "POPC", x_size: float = 80.0, y_size: float = 80.0,
                   force_field: str = "c36", vmd_path: Optional[str] = None) -> dict:
    """A lipid bilayer patch with VMD's membrane plugin (psfgen based): `<out_prefix>.psf/.pdb`. Reports lipids per
    leaflet and the bilayer thickness (phosphate to phosphate)."""
    S.choice(lipid, ("POPC", "POPE"), "lipid")
    S.choice(force_field, ("c27", "c36"), "force_field")
    xs, ys = S.num(x_size, "x_size"), S.num(y_size, "y_size")
    if not (20 <= xs <= 500 and 20 <= ys <= 500):
        raise security.InvalidInput("x_size and y_size must be between 20 and 500 Angstrom")
    pre = _prefix(out_prefix)
    body = ["package require membrane", f'membrane -l {lipid} -x {xs} -y {ys} -o "{pre}" -top {force_field}',
            f'mol new "{pre}.psf" type psf waitfor all', f'mol addfile "{pre}.pdb" type pdb waitfor all',
            "set p [atomselect top {name P}]", "set z [lsort -real [$p get z]]",
            "set mid [expr {([lindex $z 0] + [lindex $z end]) / 2.0}]",
            "set up 0; set dn 0; set zu 0; set zd 0",
            "foreach v $z { if {$v > $mid} { incr up; set zu [expr {$zu + $v}] } else { incr dn; set zd [expr {$zd + $v}] } }",
            "emit MEM [[atomselect top all] num] $up $dn [expr {$up ? $zu / $up : 0}] [expr {$dn ? $zd / $dn : 0}] "
            "[measure sumweights [atomselect top all] weight charge]"]
    res = S.run(body, vmd_path, timeout=900)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error"), "log": res.get("log", "")[-400:]}
    atoms, up, dn, zu, zd, q = res["rows"]["MEM"][0]
    return {"ok": True, "engine": "VMD membrane plugin", "psf": pre + ".psf", "pdb": pre + ".pdb", "lipid": lipid,
            "n_atoms": int(atoms), "n_lipids": int(up) + int(dn), "upper_leaflet": int(up), "lower_leaflet": int(dn),
            "thickness_P_to_P_A": round(float(zu) - float(zd), 2), "net_charge": round(float(q), 3)}


def build_nanotube(out_pdb: str, n: int = 6, m: int = 6, length_nm: float = 10.0,
                   material: str = "C-C", vmd_path: Optional[str] = None) -> dict:
    """A single-wall nanotube of chirality (n, m) with VMD's nanotube builder (C-C carbon or B-N boron nitride);
    writes a PDB. The radius is checked against the analytic value for the chirality. The length is rounded to whole
    translation periods, so chiral tubes can come out longer than asked."""
    S.choice(material, ("C-C", "B-N"), "material")
    n_, m_ = S.whole(n, "n"), S.whole(m, "m")
    length = S.num(length_nm, "length_nm")
    if m_ == 0:
        raise security.InvalidInput("VMD's nanotube builder fails for zigzag tubes (m = 0: 'domain error' in the "
                                    "version tested); use m >= 1")
    if n_ < 1 or m_ < 1 or m_ > n_ or not (1 <= length <= 200):
        raise security.InvalidInput("need n >= m >= 1 and 1 <= length_nm <= 200")
    out = security.tcl_path(out_pdb)
    body = ["package require nanotube", f"nanotube -l {length} -n {n_} -m {m_} -ma {material}",
            "set a [atomselect top all]", f'$a writepdb "{out}"',
            "set x [$a get x]; set y [$a get y]; set r 0.0",
            "foreach xi $x yi $y { set r [expr {$r + sqrt($xi*$xi + $yi*$yi)}] }",
            "emit NT [$a num] [expr {$r / [$a num]}] [measure minmax $a]"]
    res = S.run(body, vmd_path, timeout=600)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    atoms, radius, *mm = res["rows"]["NT"][0]
    import math
    expected = 0.0783 * math.sqrt(n_ * n_ + n_ * m_ + m_ * m_) / 2 * 10          # carbon nanotube radius, Angstrom
    return {"ok": True, "engine": "VMD nanotube builder", "pdb": out_pdb, "n_atoms": int(atoms),
            "mean_radius_A": round(float(radius), 3), "analytic_radius_A_for_carbon": round(expected, 3),
            "chirality": [n_, m_], "material": material}
