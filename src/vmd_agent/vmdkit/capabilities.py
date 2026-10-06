"""What the installed VMD can do, and which of it this toolkit wraps.

Scans the plugins of the real VMD installation and classifies each one, so "how complete is the
wrapper?" has an exact answer for the VMD you have, not a claim. Statuses:

  wrapped            a vmd-agent tool does this (the tool is named)
  library            a Tcl helper library other plugins use; no user-facing feature
  gui_only           works through VMD's windows; no scripting interface worth wrapping headless
  external_program   needs a program that is not VMD (NAMD, APBS, PROPKA, ...)
  not_wrapped        scriptable and useful, but no vmd-agent tool yet
  unclassified       a plugin newer than this table: look at it, then add it here
"""
from __future__ import annotations

import glob
import os
import re
from typing import Dict, Optional, Tuple

from vmd_agent.vmdkit import script as S

W, L, G, X, N = "wrapped", "library", "gui_only", "external_program", "not_wrapped"

COVERAGE: Dict[str, Tuple[str, str]] = {
    "alascanfep": (X, "NAMD free-energy perturbation"), "apbsrun": (X, "APBS electrostatics"),
    "atomedit": (G, ""), "autoimd": (X, "NAMD + GUI"), "autoionize": (W, "vmd_build_system"),
    "autopsf": (W, "vmd_build_system (protein)"), "bdtk": (N, "Brownian dynamics toolkit"),
    "bendix": (N, "helix bending analysis"), "bfeestimator": (X, "NAMD free-energy analysis"),
    "bignum": (L, ""), "biocore": (L, ""), "blast": (X, "BLAST"), "bossconvert": (X, "BOSS"),
    "cgenffcaller": (X, "CGenFF web service"), "cgtools": (N, "coarse-grained model builder"),
    "chirality": (W, "vmd_structure_check"), "cionize": (X, "cionize"), "cispeptide": (W, "vmd_structure_check"),
    "clonerep": (G, ""), "cliptool": (G, ""), "clustalw": (X, "ClustalW"), "colorscalebar": (G, ""),
    "contactmap": (W, "vmd_interactions (kind=contacts)"), "cv_dashboard": (X, "NAMD colvars"),
    "dataimport": (G, ""), "demomaster": (G, ""), "dipwatch": (G, ""), "dowser": (X, "Dowser"),
    "exectool": (L, ""), "extendedpdb": (L, ""), "fftk": (X, "NAMD / QM force-field toolkit"),
    "gofrgui": (W, "vmd_measure (kind=gofr)"), "hbonds": (W, "vmd_interactions (kind=hbonds)"),
    "heatmapper": (G, ""), "hesstrans": (N, "Hessian transforms"), "idatm": (N, "atom typing"),
    "ilstools": (N, "implicit ligand sampling"), "imdmenu": (G, "interactive MD"), "infobutton": (G, ""),
    "inorganicbuilder": (G, ""), "json": (L, ""), "libbiokit": (L, ""), "mafft": (X, "MAFFT"),
    "mdff": (X, "NAMD flexible fitting"), "membrane": (W, "vmd_build_membrane"), "membranemixer": (G, ""),
    "mergestructs": (W, "vmd_merge_structures"), "modelmaker": (G, ""), "moltoptools": (N, "topology helpers"),
    "multimolanim": (G, ""), "multiplot": (G, ""), "multiseq": (X, "sequence/structure alignment (GUI, BLAST/STAMP)"),
    "multiseqdialog": (G, ""), "multitext": (G, ""), "mutator": (W, "vmd_mutate_residue"),
    "namdenergy": (X, "NAMD"), "namdgui": (X, "NAMD"), "namdplot": (G, ""), "namdserver": (X, "NAMD"),
    "nanotube": (W, "vmd_build_nanotube"), "navfly": (G, ""), "navigate": (G, ""), "networkview": (G, ""),
    "nmwiz": (G, "normal-mode wizard (needs ProDy)"), "optimization": (L, ""), "palettetool": (G, ""),
    "paratool": (G, "QM parametrisation"), "parsefep": (X, "NAMD FEP"), "pbctools": (W, "vmd_pbc_info, vmd_convert_trajectory"),
    "pdbtool": (G, ""), "phylotree": (G, ""), "plumed": (X, "PLUMED"), "pmepot": (W, "vmd_volmap (kind=electrostatic)"),
    "propka": (X, "PROPKA"), "psfgen": (W, "vmd_build_system"), "psipred": (X, "PSIPRED"), "qmtool": (X, "QM"),
    "qwikfold": (X, "AlphaFold/ColabFold"), "qwikmd": (X, "NAMD + GUI"), "ramaplot": (W, "vmd_backbone_torsions"),
    "readcharmmpar": (L, "used by vmd_build_system"), "readcharmmtop": (L, "used by vmd_build_system"),
    "remote": (G, ""), "resptool": (X, "QM"), "rmsd": (W, "vmd_measure (kind=rmsd)"),
    "rmsdtt": (W, "vmd_measure (kind=rmsd)"), "rmsdvt": (W, "vmd_measure (kind=rmsd)"), "rnaview": (X, "RNAView"),
    "ruler": (G, ""), "runante": (X, "AmberTools"), "runsqm": (X, "AmberTools"), "saltbr": (W, "vmd_interactions (kind=salt_bridges)"),
    "seqdata": (L, ""), "seqedit": (G, ""), "signalproc": (N, "signal processing helpers"), "solvate": (W, "vmd_build_system"),
    "ssrestraints": (X, "NAMD restraints"), "stamp": (X, "STAMP"), "stingtool": (G, ""),
    "structurecheck": (W, "vmd_structure_check"), "symmetrytool": (G, ""), "tablelist": (L, ""),
    "timeline": (W, "vmd_secondary_structure"), "tktooltip": (L, ""), "topotools": (N, "topology writers (LAMMPS, GROMACS top)"),
    "torsionplot": (W, "vmd_backbone_torsions"), "trunctraj": (W, "vmd_convert_trajectory"), "utilities": (L, ""),
    "vdna": (G, "DNA builder (needs Tk: it fails without a window)"), "viewchangerender": (G, ""), "viewmaster": (G, ""), "vmddebug": (L, ""),
    "vmdlite": (G, ""), "vmdmovie": (W, "render_movie"), "vmdprefs": (G, ""), "vmdtkcon": (G, ""), "vnd": (G, ""),
    "volmapgui": (W, "vmd_volmap"), "volutil": (X, "volume arithmetic: runs its own helper binary (failed to load on the macOS build tested)"), "zoomseq": (G, ""),
    "irspecgui": (N, "IR spectrum from dipole autocorrelation"), "molefacture": (G, "molecule editor"),
}


def _base(dirname: str) -> str:
    return re.sub(r"[\d.]+$", "", dirname)


def vmd_capabilities(vmd_path: Optional[str] = None, verbose: bool = False) -> dict:
    """The plugins and file formats of the installed VMD, each marked wrapped / not wrapped. The short form (default)
    lists plugin names by status; ``verbose`` gives every plugin with its version and the tool that wraps it."""
    res = S.run(["emit DIR $::env(VMDDIR)", "emit VER [vmdinfo version]"], vmd_path)
    if not res["ok"]:
        return res if res.get("error") else S.no_vmd()
    vmd_dir = " ".join(res["rows"]["DIR"][0])
    plugins = {}
    for d in sorted(glob.glob(os.path.join(vmd_dir, "plugins", "*", "tcl", "*"))):
        if os.path.isdir(d):
            name = _base(os.path.basename(d))
            ver = os.path.basename(d)[len(name):]
            status, detail = COVERAGE.get(name, ("unclassified", ""))
            plugins[name] = {"version": ver, "status": status, "detail": detail}
    formats = sorted({os.path.basename(f)[: -len("plugin.so")] for f in glob.glob(os.path.join(vmd_dir, "plugins", "*", "molfile", "*plugin.*"))
                      if "libmolfile" not in f})
    counts: Dict[str, int] = {}
    for p in plugins.values():
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    user_facing = sum(v for k, v in counts.items() if k in (W, N, "unclassified"))
    by_status: Dict[str, Dict[str, str]] = {}
    for n, p in plugins.items():
        by_status.setdefault(p["status"], {})[n] = p["detail"]
    shown = ({"plugins": plugins} if verbose else
             {"wrapped": by_status.get(W, {}), **{k: sorted(v) for k, v in by_status.items() if k != W}})
    return {"ok": True, "vmd_version": res["rows"]["VER"][0][0], "vmd_dir": vmd_dir, **shown,
            "counts": counts, "file_formats": formats if verbose else f"{len(formats)} (verbose=true lists them)",
            "wrapped_fraction_of_scriptable_plugins": (counts.get(W, 0) / user_facing) if user_facing else None,
            "note": "gui_only and external_program plugins are listed, not wrapped: they need a window or another program."}
