"""``vmd-agent tool NAME ...``: every tool of the library as an ordinary command with ordinary flags.

There is one list of tools and one way to run each from a terminal. The commands are generated from the tools' own signatures
(:mod:`vmd_agent.toolset`), so a tool, the chat's call of it, the MCP server's and its command cannot drift apart: a tool's required
files become positional arguments, its outputs become ``--out``, its options become ``--kebab-case`` flags, and a boolean option
that defaults to true becomes ``--no-<name>``. Nothing here adds behaviour: ``vmd-agent tool measure_with_vmd ...`` calls ``measure_with_vmd(...)``.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import typing
from typing import Callable, Dict

from vmd_agent import progress, toolset
from vmd_agent.toolhints import CHOICES
from vmd_agent.vmdkit import measure, volumetric

#: parameters that name an output: always ``--out``
OUTPUTS = ("out_path", "out_dx", "out_pdb", "out_png", "out_mp4", "out_prefix", "out_dir")
#: parameters given as a JSON file or inline JSON (the flag drops the ``_spec``: ``--scene``)
JSON_PARAMS = ("scene_spec",)
#: a required list that reads naturally as the trailing words of the command (``inspect_files a.psf a.dcd``); any other required list is a flag
POSITIONAL_LISTS = ("paths", "claims")
HELP_SHORT = {  # one-line help for flags whose name alone is not enough
    "topology": "structure file (PDB, PSF, GRO, mmCIF ...)", "trajectory": "trajectory file (DCD, XTC ...), optional",
    "mobile": "the structure to move", "reference": "the structure to move it onto", "psf": "PSF file", "pdb": "PDB file",
    "psf_a": "first PSF", "pdb_a": "first PDB", "psf_b": "second PSF", "pdb_b": "second PDB", "input_pdb": "protein PDB file",
    "path": "map file", "command": "what to run: a .namd file, a Tcl script, or a command line (quote it)",
    "model": "the model to fit (PDB)", "map_file": "the density map (dx, mrc, ccp4, cube, situs)", "map_a": "the map",
    "op": "what to do", "map_b": "second map on the same grid (for add, subtract, multiply, average, mask)",
    "value": "the number the operation needs (threshold, width in angstrom, ...)", "segid": "segment name (for example P0)", "resid": "residue number", "new_resname": "new residue name (ALA ...)",
    "first": "first frame (0-based)", "last": "last frame (-1 = the end)", "step": "use every Nth frame",
    "selection": "VMD atom selection", "selection2": "second VMD atom selection", "selection3": "third selection",
    "selection4": "fourth selection", "kind": "what to compute", "fmt": "output format (default: from the file name)",
    "frame": "frame to use (0-based)", "top": "how many of the most persistent pairs to list",
    "cutoff": "distance cutoff in angstrom", "angle_cutoff": "H-bond angle cutoff in degrees",
    "paths": "the files to describe", "claims": "the statements to check, each in quotes", "identifier": "PDB ID, UniProt accession or a web address",
    "query": "what to search for", "video": "the video file", "image_path": "the image to annotate", "color_method": "VMD colouring method (Chain, Name, ResType, Structure, Beta ...)",
    "name": "the representation to describe (for example QuickSurf)", "script": "Tcl for VMD (needs VMD_AGENT_ENABLE_TCL=1)",
    "show_in_window": "also draw the result in the VMD window (opened if needed)",
    "analyses": "what to measure: rmsd rmsf rgyr hbonds contacts distance sasa density convergence", "session_dir": "a folder that records this run for a report",
}
SUMMARY: Dict[str, str] = {   # what the tool does, in the words of a person at a terminal
    "probe_environment": "what this computer can do: VMD, ffmpeg, drawing backends, libraries (--plugins: which of VMD's plugins this toolkit can drive)",
    "inspect_files": "say what kind of files these are and what is missing (a trajectory without its structure ...)",
    "detect_system": "find what is in a system: protein, ligand, water, ions, lipids, nucleic acids",
    "structure_stats": "bond and link counts for a structure: disulfides, hydrogen bonds, bonds by element pair",
    "search_pdb": "find PDB IDs by keyword",
    "fetch_structure": "download a structure (PDB ID, UniProt accession for AlphaFold, or a URL)",
    "visualize_and_interpret": "draw your file from several angles and describe it (VMD if installed, else the built-in drawing)",
    "render_image": "draw one image with VMD, of a system or of a scene you describe (--scene)",
    "render_movie": "a movie with VMD: a trajectory played, or a rotating view of a scene (--spin)",
    "annotate_image": "draw the colour key and statistics onto an image",
    "view_image": "check that a file is an image and give its path",
    "generate_visualization_recipe": "write a VMD script that draws this system sensibly",
    "list_representations": "VMD drawing styles and when to use them (--name QuickSurf: one in detail)",
    "color_key": "what each colour of a colouring method means",
    "export_session": "write a folder you can open in your own VMD (session.tcl, inputs, checksums)",
    "window_open": "open a VMD window (or reuse the open one) that the window_* tools control",
    "window_load": "load a structure, trajectory or density map into the VMD window",
    "window_molecules": "list, show, hide, rename or delete the molecules in the VMD window",
    "window_representation": "list, add, change or delete how the VMD window draws a molecule (selection, style, color)",
    "window_display": "set the VMD window's projection, background, axes, depth cueing, shadows",
    "window_view": "rotate, zoom, move, centre, save or restore the view in the VMD window",
    "window_animate": "go to a frame, play, or set the style and speed in the VMD window",
    "window_query": "ask the VMD window what a selection holds, or measure a bond, angle, dihedral or SASA",
    "window_snapshot": "a picture of what the VMD window shows right now (VMD's own drawing)",
    "window_scene": "set up a whole scene in the VMD window from a description (representations, isosurfaces, view)",
    "window_visualize": "draw a system in the VMD window the way the recipe would (what it holds, drawn to suit), with a legend",
    "window_movie": "a movie of the VMD window: the trajectory played, or a turntable",
    "window_save": "save the VMD window's state as a .vmd file that VMD opens again",
    "run_tcl": "run Tcl in headless VMD (off unless VMD_AGENT_ENABLE_TCL=1)",
    "analyze_trajectory": "measure a simulation: RMSD, flexibility, size, contacts, hydrogen bonds, SASA, convergence",
    "measure_with_vmd": "VMD's own measure commands over a trajectory: radius of gyration, SASA, RMSD, RMSF, distances, g(r), clusters ...",
    "select_keyframes": "pick the most informative frames of a trajectory",
    "periodic_box": "periodic box per frame: is there one, and does its volume drift",
    "find_interactions": "hydrogen bonds, salt bridges or contacts, as how often each pair is present",
    "secondary_structure": "secondary structure of every residue in every frame (what the Timeline window shows)",
    "backbone_torsions": "phi/psi angles and coarse Ramachandran regions of one frame",
    "check_structure": "chirality errors, cis peptides and chain gaps (the structurecheck plugin)",
    "align_structures": "superpose one structure on another and report the RMSD",
    "convert_trajectory": "write a trajectory in another format, or just some atoms or frames, wrapped or fitted",
    "write_structure": "write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin",
    "make_map": "make a density, occupancy, distance, mask or electrostatic-potential map",
    "inspect_map": "what is in a density map file (dx, mrc, ccp4, cube, situs): grid, range, suggested isosurface levels",
    "combine_maps": "add, subtract, mask, smooth, threshold or normalise density maps",
    "fit_to_map": "cryo-EM: fit a model into a density map as a rigid body, and report the correlation before and after",
    "build_system": "PDB to a solvated, neutral CHARMM36 system (psfgen, solvate, autoionize)",
    "mutate_residue": "mutate one residue of a PSF/PDB pair",
    "merge_structures": "combine two PSF/PDB systems into one",
    "build_membrane": "build a POPC or POPE lipid bilayer patch",
    "build_nanotube": "build a carbon or boron-nitride nanotube",
    "prepare_namd": "write a NAMD input file (CHARMM36, PME, minimise then equilibrate) for a built system",
    "write_slurm_script": "write a SLURM job script for a cluster (NAMD, a VMD script, or any command)",
    "probe_video": "a video's real size, frame rate, length and codec, proof that it decodes, and (--expect-width ...) a check against what was asked for",
    "interpret_video": "verify a video and pull evenly spaced stills out of it for a look",
    "verify_claims": "check statements against measurements: supported, contradicted or unverifiable",
    "record_visual_interpretation": "keep what was seen in a picture or video in the session, for the report",
    "assemble_report": "write the report from everything a session recorded",
    "verify_provenance": "re-hash the recorded inputs and outputs of a run and say what changed",
}
EXAMPLES: Dict[str, str] = {
    "probe_environment": "vmd-agent tool probe_environment --plugins",
    "inspect_files": "vmd-agent tool inspect_files run.dcd run.psf",
    "detect_system": "vmd-agent tool detect_system run.psf run.dcd",
    "structure_stats": "vmd-agent tool structure_stats 1ubq.pdb",
    "search_pdb": "vmd-agent tool search_pdb hemoglobin --limit 5",
    "fetch_structure": "vmd-agent tool fetch_structure 1UBQ --out pdbs",
    "visualize_and_interpret": "vmd-agent tool visualize_and_interpret 1ubq.pdb --views front side --out figures",
    "render_image": "vmd-agent tool render_image run.pdb run.dcd --scene scene.json --out picture.png",
    "render_movie": "vmd-agent tool render_movie run.pdb --spin --scene scene.json --out spin.mp4",
    "annotate_image": "vmd-agent tool annotate_image picture.png 1ubq.pdb --out labelled.png",
    "view_image": "vmd-agent tool view_image picture.png",
    "generate_visualization_recipe": "vmd-agent tool generate_visualization_recipe 1ubq.pdb --out draw.tcl",
    "list_representations": "vmd-agent tool list_representations --category surface",
    "color_key": "vmd-agent tool color_key Chain 1ubq.pdb",
    "export_session": "vmd-agent tool export_session run.pdb run.dcd --scene scene.json --out session1",
    "window_open": "vmd-agent tool window_open",
    "window_load": "vmd-agent tool window_load run.pdb run.dcd",
    "window_molecules": "vmd-agent tool window_molecules --action list",
    "window_representation": "vmd-agent tool window_representation --action only --selection protein --style NewCartoon --color Structure",
    "window_display": "vmd-agent tool window_display projection Orthographic",
    "window_view": "vmd-agent tool window_view --action rotate --axis x --degrees 30",
    "window_animate": "vmd-agent tool window_animate --action goto --frame 20",
    "window_query": "vmd-agent tool window_query --selection \"resname LIG\"",
    "window_snapshot": "vmd-agent tool window_snapshot --out window.png",
    "window_scene": "vmd-agent tool window_scene run.pdb run.dcd --scene scene.json",
    "window_visualize": "vmd-agent tool window_visualize run.pdb run.dcd --focus pocket",
    "window_movie": "vmd-agent tool window_movie --out spin.mp4 --action spin --frames 36",
    "window_save": "vmd-agent tool window_save --out session.vmd",
    "run_tcl": "VMD_AGENT_ENABLE_TCL=1 vmd-agent tool run_tcl 'puts [vmd_version]'",
    "analyze_trajectory": "vmd-agent tool analyze_trajectory run.psf run.dcd --analyses rmsd rgyr --step 5",
    "measure_with_vmd": "vmd-agent tool measure_with_vmd run.pdb run.dcd --kind rgyr --step 10",
    "select_keyframes": "vmd-agent tool select_keyframes run.psf run.dcd --k 6",
    "periodic_box": "vmd-agent tool periodic_box run.pdb run.dcd --step 10",
    "find_interactions": "vmd-agent tool find_interactions run.pdb run.dcd --kind salt_bridges",
    "secondary_structure": "vmd-agent tool secondary_structure run.pdb run.dcd --step 5",
    "backbone_torsions": "vmd-agent tool backbone_torsions 1ubq.pdb",
    "check_structure": "vmd-agent tool check_structure 1ubq.pdb",
    "align_structures": "vmd-agent tool align_structures model.pdb reference.pdb --out aligned.pdb",
    "convert_trajectory": "vmd-agent tool convert_trajectory run.pdb run.dcd --out ca.dcd --selection \"name CA\" --step 5",
    "write_structure": "vmd-agent tool write_structure run.pdb run.dcd --out frame10.pdb --frame 10",
    "make_map": "vmd-agent tool make_map run.pdb run.dcd --out water.dx --kind occupancy --selection \"water and name OH2\"",
    "inspect_map": "vmd-agent tool inspect_map map.mrc",
    "combine_maps": "vmd-agent tool combine_maps a.dx subtract --map-b b.dx --out difference.dx",
    "fit_to_map": "vmd-agent tool fit_to_map model.pdb map.mrc --resolution 6 --out fitted.pdb",
    "build_system": "vmd-agent tool build_system 1ubq.pdb --out build/ubq --padding 10",
    "mutate_residue": "vmd-agent tool mutate_residue ubq.psf ubq.pdb P0 6 ALA --out ubq_K6A",
    "merge_structures": "vmd-agent tool merge_structures a.psf a.pdb b.psf b.pdb --out merged",
    "build_membrane": "vmd-agent tool build_membrane --out membrane --lipid POPC --x-size 80 --y-size 80",
    "build_nanotube": "vmd-agent tool build_nanotube --out tube.pdb --n 6 --m 6 --length-nm 10",
    "prepare_namd": "vmd-agent tool prepare_namd system.psf system.pdb --out sim/equilibrate --temperature 310",
    "write_slurm_script": "vmd-agent tool write_slurm_script equilibrate.namd --kind namd --gpus 1 --modules namd/3.0 --out run.sbatch",
    "probe_video": "vmd-agent tool probe_video clip.mp4 --expect-width 320 --expect-height 240",
    "interpret_video": "vmd-agent tool interpret_video clip.mp4 --n-frames 6 --out stills",
    "verify_claims": "vmd-agent tool verify_claims 1ubq.pdb \"It has one chain\" \"It has no ligand\"",
    "record_visual_interpretation": "vmd-agent tool record_visual_interpretation session1 \"The helix packs against the sheet\"",
    "assemble_report": "vmd-agent tool assemble_report session1 --out session1/report.md",
    "verify_provenance": "vmd-agent tool verify_provenance session1",
}


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _doc(fn: Callable) -> str:
    return " ".join((fn.__doc__ or "").split())


def _first_sentence(text: str, limit: int = 110) -> str:
    cut = text.split(". ")[0]
    return (cut if len(cut) <= limit else cut[: limit - 1].rstrip() + "…").rstrip(".")


def _json_arg(value: str) -> dict:
    """A JSON object: a path to a JSON file, or the JSON itself."""
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


def _is_list(tp) -> bool:
    inner = [a for a in typing.get_args(tp) if a is not type(None)] if typing.get_origin(tp) is typing.Union else [tp]
    return bool(inner) and typing.get_origin(inner[0]) in (list, typing.List)


def _kind_of(tp) -> type:
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Union:
        real = [a for a in args if a is not type(None)]
        return _kind_of(real[0]) if real else str
    return tp if tp in (str, int, float, bool, dict) else str


def _kinds_epilog(name: str) -> str:
    extra = {"measure_with_vmd": measure.KINDS, "make_map": volumetric.KINDS}.get(name)
    return "\n\nwhat --kind does:\n" + "\n".join(f"  {k:<14} {d}" for k, d in extra.items()) if extra else ""


def add_commands(sub) -> None:
    """Register ``tool`` and one sub-command per tool of the library on the main parser's sub-parsers."""
    tp_ = sub.add_parser("tool", help="run one tool of the library (`vmd-agent tools` lists them)")
    tsub = tp_.add_subparsers(dest="tool_name", metavar="NAME")
    for name in toolset.library_tools():
        fn = toolset.TOOLS[name]
        hints = typing.get_type_hints(fn)
        sig = inspect.signature(fn)
        cp = tsub.add_parser(name, help=SUMMARY.get(name) or _first_sentence(_doc(fn)),
                             description=(lambda t: t[0].upper() + t[1:] + ".")(SUMMARY.get(name, _doc(fn))),
                             epilog="example:  " + EXAMPLES.get(name, "") + _kinds_epilog(name),
                             formatter_class=argparse.RawDescriptionHelpFormatter)
        cp.set_defaults(_tool=name)
        cp.add_argument("--full", action="store_true", help="print every value (long lists are shortened by default)")
        cp.add_argument("--quiet", action="store_true", help="do not show progress while it runs")
        has_required_list = any(n in POSITIONAL_LISTS and p.default is inspect.Parameter.empty for n, p in sig.parameters.items())
        for pname, p in sig.parameters.items():
            raw = hints.get(pname, str)
            tp, has_default = _kind_of(raw), p.default is not inspect.Parameter.empty
            helptxt = HELP_SHORT.get(pname, pname.replace("_", " "))
            if pname == "vmd_path":
                cp.add_argument("--vmd", dest=pname, metavar="PATH", help="path to VMD (default: found automatically)")
            elif pname in OUTPUTS:
                cp.add_argument("--out", dest=pname, metavar="PATH", required=not has_default, default=p.default if has_default else None,
                                help="where to write the result" + (f" (default: {p.default})" if has_default and p.default else ""))
            elif pname in JSON_PARAMS:
                cp.add_argument("--scene", dest=pname, type=_json_arg, required=not has_default, default=None, metavar="FILE_OR_JSON",
                                help="the scene: a JSON file, or JSON text (representations, isosurfaces, camera ...)")
            elif tp is dict:
                cp.add_argument(_flag(pname), dest=pname, type=_json_arg, default=None, metavar="FILE_OR_JSON", help=f"{helptxt} (JSON)")
            elif pname in ("topology", "trajectory") and (_optional(raw) or has_default) and not has_required_list:
                cp.add_argument(pname, nargs="?", default=None, help=helptxt)
            elif _is_list(raw):
                if has_default or pname not in POSITIONAL_LISTS:
                    cp.add_argument(_flag(pname), dest=pname, nargs="+", default=None, required=not has_default, help=f"{helptxt} (one or more)")
                else:
                    cp.add_argument(pname, nargs="+", help=helptxt)
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
    """The tool library, grouped, one line per tool (what ``vmd-agent tools`` and a bare ``vmd-agent tool`` print)."""
    lines = [f"{len(toolset.library_tools())} tools, in groups. Run one with:  vmd-agent tool NAME ...   (details: vmd-agent tool NAME --help)"]
    for group, what, tools in toolset.LIBRARY:
        lines += ["", f"{group}: {what}"]
        lines += [f"  {n:<30} {SUMMARY.get(n, '')}" for n, _v in tools]
    lines += ["", "Whole jobs that run several tools in a fixed order:  vmd-agent workflow",
              "Every result is JSON; long lists are shortened (add --full for everything).",
              "A tool that runs VMD saves the exact Tcl it ran: see `reproduce_script` in the result."]
    return "\n".join(lines)


def run(args, print_json: Callable, print_brief: Callable) -> int:
    name = getattr(args, "_tool", None)
    if not name:
        print(list_commands())
        return 0
    skip = {"cmd", "tool_name", "_tool", "full", "quiet"}
    kwargs = {k: v for k, v in vars(args).items() if k not in skip}
    if args.quiet:
        result = toolset.TOOLS[name](**kwargs)
    else:
        with progress.listen(progress.terminal()):                       # progress goes to stderr; the result to stdout
            result = toolset.TOOLS[name](**kwargs)
    if name == "visualize_and_interpret" and isinstance(result, dict) and result.get("ok") and not args.full:
        print_brief(result)                                              # the reading a person wants, not the JSON
    else:
        print_json(result if args.full else brief(result))
    return 1 if isinstance(result, dict) and result.get("ok") is False else 0
