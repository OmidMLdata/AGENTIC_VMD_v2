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

from vmd_agent import vmd_cli

#: parameter name -> what it means, where the name alone does not say
PARAM_HELP: Dict[str, str] = {
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
}
_MAX_ENUM = 14


def enrich(specs: List[dict]) -> List[dict]:
    """Copies of the tool specs with meanings and allowed values added to the parameters that need them."""
    out = []
    for spec in specs:
        spec = copy.deepcopy(spec)
        props = spec.get("input_schema", {}).get("properties", {})
        for name, schema in props.items():
            allowed = vmd_cli.CHOICES.get((spec["name"], name))
            if allowed and len(allowed) <= _MAX_ENUM:
                schema["enum"] = list(allowed)
            help_ = PARAM_HELP.get(name)
            if help_ and "description" not in schema:
                schema["description"] = help_
        out.append(spec)
    return out
