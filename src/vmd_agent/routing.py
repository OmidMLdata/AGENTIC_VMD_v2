"""Which tools to offer a model for a question.

Offering all 53 tools costs about 8,000 tokens of descriptions with every question and gives a small model a long list to choose from.
Most questions need a handful. This module picks them from the wording of the question and the kinds of files it names; it
decides nothing else (the model still chooses which of the offered tools to call and with what).

The groups follow the pipeline of the README. A small **base** set is always offered (look at files, describe a system, check a statement,
run a whole job), a group is added for each kind of request the question mentions, and a question that matches nothing gets the base set plus
the commonest groups (about half the tools), never an empty menu. If the model asks for a tool outside the offered set the agent offers it from then on (see
:mod:`vmd_agent.agent`), so a wrong guess here costs one round trip, not the answer.

Pure text in, tool names out: nothing here runs a tool or reads a file.
"""
from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

#: always offered: what is this, what is in it, is this true, run a whole job
BASE: Tuple[str, ...] = ("inspect_files", "detect_system", "structure_stats", "verify_claims", "list_workflows", "run_workflow")

#: group -> (tools, wording that asks for it); the wording is matched case-insensitively against the question
GROUPS: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "environment": (("probe_environment", "vmd_capabilities"),
                    r"\b(this computer|my computer|installed|available|which version|what can (you|vmd|this)|plugins?|capabilit\w+|can you drive|supported)\b"),
    "trajectory": (("analyze_trajectory", "select_keyframes", "vmd_measure", "vmd_pbc_info"),
                   r"\b(rmsd|rmsf|radius of gyration|rgyr|gyration|trajector\w+|simulation|frames?|converge\w*|settled|equilibrat\w*|drift\w*|fluctuat\w+|"
                   r"flexib\w+|periodic|box|sasa|solvent accessible|distance|g\(r\)|cluster\w*|informative|interesting|events?)\b|\.(dcd|xtc|trr|nc)\b"),
    "interactions": (("vmd_interactions", "vmd_secondary_structure", "analyze_trajectory"),
                     r"\b(hydrogen bonds?|h-?bonds?|salt bridges?|contacts?|persist\w*|interact\w*|secondary structure|helix|helices|strand|sheet|stride|dssp)\b"),
    "checks": (("vmd_backbone_torsions", "vmd_structure_check", "vmd_align_structures"),
               r"\b(torsions?|dihedrals?|ramachandran|phi|psi|outliers?|chirality|cis|trans|peptide bonds?|steric|clash\w*|geometry|sane|sanity|chain gaps?|structure check|superpos\w+|align\w*|overlay\w*|fit .* onto)\b"),
    "files": (("vmd_convert_trajectory", "vmd_write_structure"),
              r"\b(convert\w*|write|save|export|extract|slice|cut( out)?|trim|only the|every (\w+ )?(\d+(st|nd|rd|th)?|tenth|fifth|second|other)|alpha carbons?|backbone atoms?|strip|subset|smaller file|as an? (pdb|dcd|xtc|gro|psf))\b"),
    "build": (("vmd_build_system", "vmd_mutate_residue", "vmd_merge_structures", "vmd_build_membrane", "vmd_build_nanotube", "vmd_prepare_namd", "vmd_slurm_script"),
              r"\b(build|solvat\w+|water box|neutral\w*|ionize|mutat\w+|swap\w*|replac\w+|substitut\w+|point mutation|merge|combine|join|membrane|bilayer|popc|pope|lipid|nanotube|namd|slurm|sbatch|cluster|"
              r"job script|hpc|psfgen|prepare .* (simulation|namd)|simulation input)\b"),
    "maps": (("vmd_volmap", "vmd_volume_info", "vmd_map_arithmetic", "vmd_fit_to_map"),
             r"\b(density|map|cryo-?em|isosurface|occupancy|volmap|grid|electrostatic|potential)\b|\.(dx|mrc|ccp4|cube|situs|map)\b"),
    "render": (("render_image", "render_movie", "vmd_render_scene", "vmd_render_turntable", "export_vmd_session", "visualize_and_interpret",
                "generate_visualization_recipe", "annotate_image", "view_image", "color_key", "list_representations", "describe_representation"),
               r"\b(draw|render\w*|picture|image|figure|movie|animat\w+|flip-?book|time-?lapse|turntable|rotat\w+|spin\w*|record\w* .{0,20}video|scene|colou?rs?|cartoon|licorice|surface|quicksurf|represent\w+|"
               r"drawing style|show me|display|visuali[sz]\w+|tachyon|vmd script|tcl|recipe|session|label\w*|key)\b|\.(png|jpg|jpeg|tcl)\b"),
    "video": (("probe_video", "validate_video", "extract_video_frames", "interpret_video"),
              r"\b(video|clip|mp4|frame rate|fps|resolution|stills?|decode\w*|codec)\b|\.(mp4|mov|webm|gif)\b"),
    "records": (("verify_provenance", "assemble_report", "record_visual_interpretation"),
                r"\b(provenance|checksums?|hash\w*|sha-?256|re-?check\w*|integrity|unchanged|tamper\w*|report|write up|session folder|recorded)\b"),
    "network": (("search_pdb", "fetch_structure", "fetch_and_visualize"),
                r"\b(download\w*|fetch\w*|grab\w*|pull\w* .{0,30}from|search the pdb|find (pdb )?entries|pdb entr\w+|from (the )?(pdb|rcsb|protein data bank)|alphafold|uniprot|rcsb)\b|\b[1-9][A-Za-z0-9]{3}\b(?=[ ,.?]|$)"),
    "tcl": (("run_vmd_tcl",), r"\btcl\b"),
}
_COMPILED = {g: re.compile(p, re.I) for g, (_, p) in GROUPS.items()}

#: offered when nothing matches: a question with no recognisable subject is most often "what is in my files" or "what can you do"
FALLBACK_GROUPS: Tuple[str, ...] = ("environment", "trajectory", "interactions", "checks", "render")


def matched_groups(question: str) -> List[str]:
    """The groups whose wording the question uses, in the order of GROUPS."""
    return [g for g, rx in _COMPILED.items() if rx.search(question)]


def select(question: str, available: Sequence[str]) -> List[str]:
    """The tool names to offer for ``question``: the base set plus the tools of every group the question asks for, only those in ``available``,
    in the order of ``available`` (stable, so the model sees the same list for the same kind of question)."""
    groups = matched_groups(question) or list(FALLBACK_GROUPS)
    want = set(BASE)
    for g in groups:
        want.update(GROUPS[g][0])
    return [n for n in available if n in want]


def group_of(tool: str) -> str:
    """The first group that holds ``tool`` ('' if it is only in the base set)."""
    return next((g for g, (tools, _) in GROUPS.items() if tool in tools), "")


#: the agent-internal tool a model uses to ask for more tools when the routed set lacks one (it is not one of the 53 and exists only in "auto")
OFFER = "offer_tools"


def offer_spec(offered: Sequence[str], available: Sequence[str]) -> dict:
    """The description of ``offer_tools``: the groups that still have tools the model has not been given, with their names."""
    pending = {g: [t for t in tools if t in available and t not in offered] for g, (tools, _) in GROUPS.items()}
    pending = {g: t for g, t in pending.items() if t}
    return {"name": OFFER,
            "description": "The tools offered so far are the ones that fit the question. If you need one that is not offered, ask for its group here, then use it. "
                           "Groups: " + "; ".join(f"{g} ({', '.join(t)})" for g, t in pending.items()),
            "input_schema": {"type": "object", "properties": {"group": {"type": "string", "enum": sorted(pending)}}, "required": ["group"]}} if pending else {}


def offer(group: str, offered: Sequence[str], available: Sequence[str]) -> List[str]:
    """The tools of ``group`` not yet offered (empty list for an unknown group)."""
    tools = GROUPS.get(group, ((), ""))[0]
    return [t for t in tools if t in available and t not in offered]
