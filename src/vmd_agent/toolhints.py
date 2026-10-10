"""What a model needs to know about a parameter that its name does not say.

The tool schemas come from the functions' signatures: names and types, nothing about meaning. A model reads ``align`` or ``step`` and guesses. This
adds, for the model only, a one-line meaning to the parameters that are ambiguous and the allowed values (``enum``) to the parameters that take one
of a fixed list, so that "without aligning" becomes ``align = false`` instead of a default the model never knew it could change.

Parameters that are obvious from their names (``topology``, ``trajectory``, ``out_path``) get nothing, to keep the descriptions short:
every word here is sent with every question.
"""
from __future__ import annotations

import copy
from typing import Dict, List

from vmd_agent import vmdlink
from vmd_agent.vmdkit import interactions, maps, measure, trajectory, volumetric

#: (tool, parameter) -> the allowed values, for the parameters that take one of a fixed list
CHOICES: Dict[tuple, tuple] = {
    ("measure_with_vmd", "kind"): tuple(measure.KINDS),
    ("find_interactions", "kind"): interactions.KINDS,
    ("make_map", "kind"): tuple(volumetric.KINDS),
    ("convert_trajectory", "fmt"): trajectory.TRAJ_WRITERS,
    ("write_structure", "fmt"): trajectory.STRUCT_WRITERS,
    ("build_system", "histidine"): ("HSD", "HSE", "HSP"),
    ("build_membrane", "lipid"): ("POPC", "POPE"),
    ("build_membrane", "force_field"): ("c27", "c36"),
    ("build_nanotube", "material"): ("C-C", "B-N"),
    ("render_movie", "axis"): ("x", "y", "z"),
    ("combine_maps", "op"): tuple(maps.OPS),
    ("prepare_namd", "ensemble"): ("npt", "nvt"),
    ("write_slurm_script", "kind"): ("namd", "vmd", "shell"),
    ("fetch_structure", "source"): ("auto", "rcsb", "alphafold", "url"),
    ("fetch_structure", "file_format"): ("auto", "pdb", "cif"),
    ("visualize_and_interpret", "renderer"): ("auto", "vmd", "matplotlib"),
    ("select_keyframes", "renderer"): ("auto", "vmd", "matplotlib"),
    ("visualize_and_interpret", "focus"): ("overview", "fold", "interactions", "surface", "pocket", "performance"),
    ("annotate_image", "panel_side"): ("right", "left"),
    ("window_molecules", "action"): ("list", "top", "show", "hide", "rename", "delete", "clear"),
    ("window_representation", "action"): ("list", "add", "modify", "delete", "only"),
    ("window_representation", "style"): vmdlink.STYLES,
    ("window_representation", "color"): vmdlink.COLORS,
    ("window_representation", "material"): vmdlink.MATERIALS,
    ("window_display", "setting"): tuple(vmdlink.DISPLAY),
    ("window_view", "action"): ("reset", "rotate", "scale", "translate", "center", "save", "restore"),
    ("window_view", "axis"): ("x", "y", "z"),
    ("window_animate", "action"): ("goto", "forward", "reverse", "pause", "style", "speed"),
    ("window_animate", "style"): ("once", "loop", "rock"),
    ("window_query", "measure"): ("bond", "angle", "dihedral", "sasa"),
    ("window_snapshot", "quality"): ("fast", "tachyon"),
    ("window_movie", "action"): ("trajectory", "spin"),
    ("window_movie", "axis"): ("x", "y", "z"),
    ("window_movie", "quality"): ("fast", "tachyon"),
    ("window_visualize", "focus"): ("overview", "fold", "interactions", "surface", "pocket", "performance"),
    ("window_visualize", "background"): vmdlink.BACKGROUNDS,
}

#: parameter name -> what it means, where the name alone does not say
PARAM_HELP: Dict[str, str] = {
    "color_method": "how to colour: Structure = secondary structure (helix, sheet, coil); ResType = residue type; Name = by element; Chain = by chain; Beta = by B-factor; leave empty for the default",
    "align": "superpose every frame on the reference frame first (true, the default); false measures the raw movement",
    "mass_weighted": "weight atoms by mass (true) or count them equally (false)",
    "wrap": "wrap molecules back into the periodic box",
    "unwrap": "make molecules whole across the periodic box before measuring",
    "step": "use every Nth frame (1 = all)",
    "first": "first frame to use, counting from 0",
    "last": "last frame to use; -1 means the end",
    "frame": "which frame, counting from 0; -1 is the last",
    "selection": "VMD atom selection, for example 'protein', 'name CA', 'resname LIG'",
    "selection2": "a second selection, the partner of the first",
    "cutoff": "distance cutoff in angstrom",
    "padding": "water padding around the solute in angstrom",
    "solvate": "add a water box (true) or build the dry system only (false)",
    "resolution": "map resolution in angstrom",
    "analyses": "which analyses to run, a list: rmsd, rmsf, rgyr, hbonds, contacts, distance, sasa, density, convergence",
    "claims": "statements to check, a list of plain sentences such as 'It has 4 disulfide bridges'",
    "k": "how many frames to pick",
    "views": "which views to draw: front, side, top, iso",
    "renderer": "auto, vmd or matplotlib (matplotlib needs no VMD)",
    "out_dir": "folder to write into",
    "session_dir": "folder that records this run for a report",
    "kind": "which measurement or analysis",
    "op": "the operation",
    "value": "the number the operation needs",
    "show_in_window": "also draw the result in the VMD window (opened if needed), so you see it in VMD itself",
}
_MAX_ENUM = 14


def enrich(specs: List[dict]) -> List[dict]:
    """Copies of the tool specs with meanings and allowed values added to the parameters that need them."""
    out = []
    for spec in specs:
        spec = copy.deepcopy(spec)
        props = spec.get("input_schema", {}).get("properties", {})
        for name, schema in props.items():
            allowed = CHOICES.get((spec["name"], name))
            if allowed and len(allowed) <= _MAX_ENUM:
                schema["enum"] = list(allowed)
            help_ = PARAM_HELP.get(name)
            if help_ and "description" not in schema:
                schema["description"] = help_
        out.append(spec)
    return out
