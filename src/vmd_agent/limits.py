"""Requests for things this toolkit cannot do, recognised before the model is asked.

A small model that is asked for something impossible tends to do the nearest thing and let the user believe the request was met. For the few
impossible things that can be recognised from the wording, the answer is therefore fixed: say plainly that it cannot be done, and offer what can be.
The patterns are narrow on purpose (a question *about* NAMD is not a request to run it); anything they miss still reaches the model, whose
instructions say the same.

Nothing here imports the rest of the package.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

_MOUSE = re.compile(r"\b(?:click(?:ing|ed)?|mouse|cursor|hover(?:ing)?)\b[^.?\n]{0,60}\b(?:atoms?|residues?|bonds?)\b|"
                    r"\b(?:atoms?|residues?|bonds?)\b[^.?\n]{0,60}\b(?:click(?:ed|ing)?|mouse|cursor|hover(?:ed|ing)?)\b", re.I)
_TK = re.compile(r"\b(?:timeline|hydrogen ?bonds?|rmsd (?:trajectory tool|calculator)|sequence viewer|ramachandran plot|tk) (?:plugin|extension|window|console)\b|"
                 r"\b(?:open|launch|start|show|display)\b[^.?\n]{0,40}\b(?:vmd'?s? )?(?:plugin windows?|tk (?:window|console)|extensions? menu)\b", re.I)
_RUN = re.compile(r"\b(?:run|start|launch|execute|submit)\b[^.?\n]{0,30}\b(?:namd|the (?:md )?simulation|the md run|a slurm job|the (?:slurm )?job on the cluster)\b", re.I)

LIMITS: List[Tuple[re.Pattern, str]] = [
    (_MOUSE, "I cannot see or control the mouse in the VMD window, so I cannot tell which atom or residue you clicked. "
             "If you tell me a selection (for example `resid 23` or `name CA`), I can load it, draw it, and list what it contains with `window_query`."),
    (_TK, "I cannot open VMD's own plugin windows (Timeline, Hydrogen Bonds and the others), because they are Tk windows I have no way to drive. "
          "What I can do is compute the same things with tools (for example `secondary_structure` per frame, or `find_interactions`) and draw the result in the VMD window."),
    (_RUN, "I cannot run NAMD or a cluster job: I can only write the input files and the SLURM script (`prepare_namd`, `write_slurm_script`, or the `prepare_simulation` workflow), "
           "and you run them. So I also have no energies or trajectories from such a run to report."),
]


def unsupported(text: str) -> Optional[str]:
    """The plain refusal for a request that asks for something impossible, or None."""
    asking = re.match(r"\s*(?:how|what|why|when|where|which)\b", text or "", re.I)      # a question about running NAMD is not a request to run it
    for pattern, reply in LIMITS:
        if pattern is _RUN and asking:
            continue
        if pattern.search(text or ""):
            return reply
    return None
