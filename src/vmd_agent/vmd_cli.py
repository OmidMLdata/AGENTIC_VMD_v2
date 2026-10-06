"""``vmd-agent vmd ...``: the tools that drive VMD itself, as ordinary commands with ordinary flags.

The commands are generated from the tools' own signatures (:mod:`vmd_agent.vmd_tools`), so a tool and its
command cannot drift apart: a tool's required structure files become positional arguments, its outputs become
``--out``, its options become ``--kebab-case`` flags, and a boolean option that defaults to true becomes
``--no-<name>``. Nothing here adds behaviour: ``vmd-agent vmd measure ...`` calls ``vmd_measure(...)``.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import typing
from typing import Callable, Dict, List

from vmd_agent import toolset
from vmd_agent.vmdkit import interactions, measure, trajectory, volumetric

#: tool name -> command name
def command_name(tool: str) -> str:
    return ("export-session" if tool == "export_vmd_session"
            else tool[4:].replace("_", "-") if tool.startswith("vmd_") else tool.replace("_", "-"))


VMD_TOOLS: List[str] = [n for n in toolset.TOOLS if n not in toolset.CORE_TOOLS]

#: parameters that name an output: always ``--out``
OUTPUTS = ("out_path", "out_dx", "out_pdb", "out_png", "out_mp4", "out_prefix", "out_dir")
#: parameters shown as a JSON file or inline JSON
JSON_PARAMS = ("scene_spec",)
CHOICES: Dict[tuple, tuple] = {
    ("vmd_measure", "kind"): tuple(measure.KINDS),
    ("vmd_interactions", "kind"): interactions.KINDS,
    ("vmd_volmap", "kind"): tuple(volumetric.KINDS),
    ("vmd_convert_trajectory", "fmt"): trajectory.TRAJ_WRITERS,
    ("vmd_write_structure", "fmt"): trajectory.STRUCT_WRITERS,
    ("vmd_build_system", "histidine"): ("HSD", "HSE", "HSP"),
    ("vmd_build_membrane", "lipid"): ("POPC", "POPE"),
    ("vmd_build_membrane", "force_field"): ("c27", "c36"),
    ("vmd_build_nanotube", "material"): ("C-C", "B-N"),
    ("vmd_render_scene", "axis"): ("x", "y", "z"),
    ("vmd_render_turntable", "axis"): ("x", "y", "z"),
}
HELP_SHORT = {  # one-line help for flags whose name alone is not enough
    "topology": "structure file (PDB, PSF, GRO, mmCIF ...)", "trajectory": "trajectory file (DCD, XTC ...), optional",
    "mobile": "the structure to move", "reference": "the structure to move it onto", "psf": "PSF file", "pdb": "PDB file",
    "psf_a": "first PSF", "pdb_a": "first PDB", "psf_b": "second PSF", "pdb_b": "second PDB", "input_pdb": "protein PDB file",
    "path": "map file", "segid": "segment name (for example P0)", "resid": "residue number", "new_resname": "new residue name (ALA ...)",
    "first": "first frame (0-based)", "last": "last frame (-1 = the end)", "step": "use every Nth frame",
    "selection": "VMD atom selection", "selection2": "second VMD atom selection", "selection3": "third selection",
    "selection4": "fourth selection", "kind": "what to compute", "fmt": "output format (default: from the file name)",
    "frame": "frame to use (0-based)", "top": "how many of the most persistent pairs to list",
    "cutoff": "distance cutoff in angstrom", "angle_cutoff": "H-bond angle cutoff in degrees",
}
SUMMARY: Dict[str, str] = {   # what the command does, in the words of a person at a terminal
    "vmd_capabilities": "list the plugins of your VMD and which of them this toolkit wraps",
    "vmd_measure": "VMD's measure commands over a trajectory: radius of gyration, SASA, RMSD, RMSF, distances, g(r), clusters ...",
    "vmd_interactions": "hydrogen bonds, salt bridges or contacts, as how often each pair is present",
    "vmd_secondary_structure": "secondary structure of every residue in every frame (what the Timeline window shows)",
    "vmd_backbone_torsions": "phi/psi angles and coarse Ramachandran regions of one frame",
    "vmd_structure_check": "chirality errors, cis peptides and chain gaps (the structurecheck plugin)",
    "vmd_align_structures": "superpose one structure on another and report the RMSD",
    "vmd_pbc_info": "periodic box per frame: is there one, and does its volume drift",
    "vmd_convert_trajectory": "write a trajectory in another format, or just some atoms/frames, wrapped or fitted",
    "vmd_write_structure": "write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin",
    "vmd_volmap": "make a density, occupancy, distance, mask or electrostatic-potential map",
    "vmd_volume_info": "what is in a density map file (dx, mrc, ccp4, cube, situs): grid, range, suggested isosurface levels",
    "vmd_build_system": "PDB to a solvated, neutral CHARMM36 system (psfgen, solvate, autoionize)",
    "vmd_mutate_residue": "mutate one residue of a PSF/PDB pair",
    "vmd_merge_structures": "combine two PSF/PDB systems into one",
    "vmd_build_membrane": "build a POPC or POPE lipid bilayer patch",
    "vmd_build_nanotube": "build a carbon or boron-nitride nanotube",
    "vmd_render_scene": "draw a scene you describe (representations, isosurfaces, camera) to a PNG",
    "vmd_render_turntable": "a rotating-view movie of a scene",
    "export_vmd_session": "write a folder you can open in your own VMD (session.tcl, inputs, checksums)",
}
EXAMPLES: Dict[str, str] = {
    "vmd_capabilities": "vmd-agent vmd capabilities",
    "vmd_measure": "vmd-agent vmd measure run.pdb run.dcd --kind rgyr --step 10",
    "vmd_interactions": "vmd-agent vmd interactions run.pdb run.dcd --kind salt_bridges",
    "vmd_secondary_structure": "vmd-agent vmd secondary-structure run.pdb run.dcd --step 5",
    "vmd_backbone_torsions": "vmd-agent vmd backbone-torsions 1ubq.pdb",
    "vmd_structure_check": "vmd-agent vmd structure-check 1ubq.pdb",
    "vmd_align_structures": "vmd-agent vmd align-structures model.pdb reference.pdb --out aligned.pdb",
    "vmd_pbc_info": "vmd-agent vmd pbc-info run.pdb run.dcd --step 10",
    "vmd_convert_trajectory": "vmd-agent vmd convert-trajectory run.pdb run.dcd --out ca.dcd --selection \"name CA\" --step 5",
    "vmd_write_structure": "vmd-agent vmd write-structure run.pdb run.dcd --out frame10.pdb --frame 10",
    "vmd_volmap": "vmd-agent vmd volmap run.pdb run.dcd --out water.dx --kind occupancy --selection \"water and name OH2\"",
    "vmd_volume_info": "vmd-agent vmd volume-info map.mrc",
    "vmd_build_system": "vmd-agent vmd build-system 1ubq.pdb --out build/ubq --padding 10",
    "vmd_mutate_residue": "vmd-agent vmd mutate-residue ubq.psf ubq.pdb P0 6 ALA --out ubq_K6A",
    "vmd_merge_structures": "vmd-agent vmd merge-structures a.psf a.pdb b.psf b.pdb --out merged",
    "vmd_build_membrane": "vmd-agent vmd build-membrane --out membrane --lipid POPC --x-size 80 --y-size 80",
    "vmd_build_nanotube": "vmd-agent vmd build-nanotube --out tube.pdb --n 6 --m 6 --length-nm 10",
    "vmd_render_scene": "vmd-agent vmd render-scene run.pdb run.dcd --scene scene.json --out picture.png",
    "vmd_render_turntable": "vmd-agent vmd render-turntable run.pdb --scene scene.json --out spin.mp4",
    "export_vmd_session": "vmd-agent vmd export-session run.pdb run.dcd --scene scene.json --out session1",
}


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _doc(fn: Callable) -> str:
    return " ".join((fn.__doc__ or "").split())


def _first_sentence(text: str, limit: int = 110) -> str:
    cut = text.split(". ")[0]
    return (cut if len(cut) <= limit else cut[: limit - 1].rstrip() + "…").rstrip(".")


def _scene(value: str) -> dict:
    """A scene spec: a path to a JSON file, or the JSON itself."""
    try:
        text = open(value).read() if os.path.isfile(value) else value
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("not an object")
        return obj
    except (OSError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"expected a JSON file or a JSON object ({e})")


def _optional(tp) -> bool:
    return typing.get_origin(tp) is typing.Union and type(None) in typing.get_args(tp)


def _kind_of(tp) -> type:
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Union:
        real = [a for a in args if a is not type(None)]
        return _kind_of(real[0]) if real else str
    return tp if tp in (str, int, float, bool, dict) else str


def add_commands(sub) -> None:
    """Register ``vmd`` and one sub-command per VMD tool on the main parser's sub-parsers."""
    vp = sub.add_parser("vmd", help="drive VMD itself: measure, build systems, density maps, scenes, session export "
                        "(needs VMD; `vmd-agent vmd` lists the commands)")
    vsub = vp.add_subparsers(dest="vmd_cmd", metavar="action")
    for name in VMD_TOOLS:
        fn = toolset.TOOLS[name]
        hints = typing.get_type_hints(fn)
        sig = inspect.signature(fn)
        extra = {"vmd_measure": measure.KINDS, "vmd_volmap": volumetric.KINDS}.get(name)
        kinds = "\n\nwhat --kind does:\n" + "\n".join(f"  {k:<14} {d}" for k, d in extra.items()) if extra else ""
        cp = vsub.add_parser(command_name(name), help=SUMMARY.get(name) or _first_sentence(_doc(fn)),
                             description=(lambda t: t[0].upper() + t[1:] + ".")(SUMMARY.get(name, _doc(fn))),
                             epilog="example:  " + EXAMPLES.get(name, "") + kinds,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
        cp.set_defaults(_tool=name)
        cp.add_argument("--full", action="store_true", help="print every value (long lists are shortened by default)")
        for pname, p in sig.parameters.items():
            raw = hints.get(pname, str)
            tp, has_default = _kind_of(raw), p.default is not inspect.Parameter.empty
            helptxt = HELP_SHORT.get(pname, pname.replace("_", " "))
            if pname == "vmd_path":
                cp.add_argument("--vmd", dest=pname, metavar="PATH", help="path to VMD (default: found automatically)")
            elif pname in OUTPUTS:
                cp.add_argument("--out", dest=pname, metavar="PATH", required=not has_default, default=p.default if has_default else None,
                                help="where to write the result")
            elif pname in JSON_PARAMS:
                cp.add_argument("--scene", dest=pname, type=_scene, required=True, metavar="FILE_OR_JSON",
                                help="the scene: a JSON file, or JSON text (representations, isosurfaces, camera ...)")
            elif pname in ("topology", "trajectory") and (_optional(raw) or has_default):
                cp.add_argument(pname, nargs="?", default=None, help=helptxt)
            elif not has_default:
                cp.add_argument(pname, type=tp, help=helptxt)                    # required: positional
            elif tp is bool:
                cp.add_argument(_flag(pname), dest=pname, action=argparse.BooleanOptionalAction, default=p.default,
                                help=f"{helptxt} (default: {'on' if p.default else 'off'})")
            else:
                kw = {"type": tp, "default": p.default, "dest": pname,
                      "help": f"{helptxt} (default: {p.default})" if p.default is not None else helptxt}
                if (name, pname) in CHOICES:
                    kw["choices"] = CHOICES[(name, pname)]
                cp.add_argument(_flag(pname), **kw)


def brief(obj, n: int = 4):
    """Shorten long lists so a result fits on a screen; ``--full`` prints everything."""
    if isinstance(obj, dict):
        return {k: brief(v, n) for k, v in obj.items()}
    if isinstance(obj, list):
        shown = [brief(v, n) for v in obj[:n]]
        return shown + [f"... {len(obj) - n} more"] if len(obj) > n + 1 else [brief(v, n) for v in obj]
    return obj


def list_commands() -> str:
    lines = ["Commands that drive VMD itself (each needs VMD):", ""]
    for name in VMD_TOOLS:
        lines.append(f"  vmd-agent vmd {command_name(name):<22} {SUMMARY.get(name, '')}")
    lines += ["", "Details and an example for one:  vmd-agent vmd <action> --help",
              "Every result is JSON; long lists are shortened (add --full for everything).",
              "Each command saves the exact Tcl it ran: see `reproduce_script` in the result."]
    return "\n".join(lines)


def run(args, print_json: Callable) -> int:
    name = getattr(args, "_tool", None)
    if not name:
        print(list_commands())
        return 0
    skip = {"cmd", "vmd_cmd", "_tool", "full"}
    kwargs = {k: v for k, v in vars(args).items() if k not in skip}
    result = toolset.TOOLS[name](**kwargs)
    print_json(result if args.full else brief(result))
    return 1 if isinstance(result, dict) and result.get("ok") is False else 0
