"""Putting a model's tool arguments right when there is only one way to read them.

Models fill arguments badly in small, regular ways: a number written as a string, a list written as one word, ``RMSD`` where the tool wants
``rmsd``, ``traj`` for ``trajectory``, a file name without its folder, the trajectory given as the topology, a required file left out when the
folder holds exactly one that fits. Each of these has one sensible reading, so the agent corrects it and tells the model what it did (the
result carries ``note_on_arguments``). Anything ambiguous or wrong in a way a person would have to decide (two structure files, a name that
exists nowhere, a value outside the allowed choices) is left alone, and the tool's own error says what is wrong.

Pure functions over the arguments, the tool's schema and a folder listing; no tool is run.
"""
from __future__ import annotations

import ast
import json
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

KIND_EXT: Dict[str, Tuple[str, ...]] = {
    "structure": (".pdb", ".cif", ".mmcif", ".gro", ".psf", ".mol2", ".xyz", ".prmtop", ".parm7", ".pqr"),
    "trajectory": (".dcd", ".xtc", ".trr", ".nc", ".mdcrd", ".trj", ".lammpstrj"),
    "video": (".mp4", ".mov", ".webm", ".gif", ".avi"),
    "image": (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"),
    "map": (".dx", ".mrc", ".ccp4", ".cube", ".situs", ".map"),
}
#: parameter name -> the kind of file it takes (a parameter not listed here is never treated as a file)
FILE_PARAMS: Dict[str, str] = {
    "topology": "structure", "trajectory": "trajectory", "video": "video", "image_path": "image", "model": "structure", "map_file": "map",
    "map_a": "map", "map_b": "map", "mobile": "structure", "reference": "structure", "input_pdb": "structure", "psf": "structure", "pdb": "structure",
}
ALIASES: Dict[str, str] = {"traj": "trajectory", "trajectory_file": "trajectory", "topology_file": "topology", "top": "topology", "structure": "topology",
                           "pdb_file": "topology", "sel": "selection", "sel2": "selection2", "out": "out_path", "output": "out_path",
                           "video_path": "video", "image": "image_path", "map": "map_file"}


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(text).lower())


def list_files(folder: str, depth: int = 2) -> List[str]:
    """Files under ``folder`` (relative, forward slashes), two levels deep, hidden ones left out."""
    out: List[str] = []
    base = os.path.realpath(folder)
    for here, dirs, names in os.walk(base):
        level = os.path.relpath(here, base).count(os.sep) + (0 if here == base else 1)
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "vmd_scripts")] if level < depth else []
        out += [os.path.relpath(os.path.join(here, n), base).replace(os.sep, "/") for n in names if not n.startswith(".")]
    return sorted(out)


def _kind_of(path: str) -> Optional[str]:
    ext = os.path.splitext(path)[1].lower()
    return next((k for k in ("structure", "trajectory", "map", "video", "image") if ext in KIND_EXT[k]), None)


def _coerce(value, schema: dict):
    """The value in the type the schema asks for, or the value unchanged if that is not clearly possible."""
    kind = schema.get("type")
    if kind in ("integer", "number") and isinstance(value, str):
        try:
            number = float(value.strip())
            return int(number) if kind == "integer" and number == int(number) else number
        except ValueError:
            return value
    if kind in ("integer", "number") and isinstance(value, float) and kind == "integer" and value == int(value):
        return int(value)
    if kind == "boolean" and isinstance(value, str):
        low = value.strip().lower()
        return True if low in ("true", "yes", "1") else False if low in ("false", "no", "0") else value
    if kind == "array":
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                for loader in (json.loads, ast.literal_eval):
                    try:
                        parsed = loader(text)
                        if isinstance(parsed, list):
                            return parsed
                    except (ValueError, SyntaxError):
                        pass
            return [p for p in re.split(r"[,\s]+", text) if p] if text else value
        if not isinstance(value, (list, tuple)):
            return [value]
    if kind == "object" and isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else value
        except ValueError:
            return value
    return value


def fix(tool: str, args: dict, schema: dict, choices: Optional[Dict[Tuple[str, str], Sequence[str]]] = None,
        files: Sequence[str] = ()) -> Tuple[dict, List[str]]:
    """``(arguments, notes)``: the arguments with every unambiguous mistake corrected, and one sentence per correction.

    ``schema`` is the tool's ``input_schema`` (properties and required); ``choices`` maps ``(tool, parameter)`` to the allowed values;
    ``files`` is the folder listing the model works in."""
    props = schema.get("properties", {})
    required = schema.get("required", [])
    out, notes = dict(args), []
    for key in list(out):                                           # a known alias for a parameter this tool has
        if key not in props and ALIASES.get(key) in props and ALIASES[key] not in out:
            out[ALIASES[key]] = out.pop(key)
            notes.append(f"{key} was read as {ALIASES[key]}")
    for key, value in list(out.items()):
        if key in props:
            new = _coerce(value, props[key])
            if new != value or type(new) is not type(value):
                out[key] = new
                notes.append(f"{key}: {value!r} was read as {new!r}")
    for key, value in list(out.items()):                            # RMSD -> rmsd, salt-bridges -> salt_bridges
        allowed = (choices or {}).get((tool, key))
        if allowed and isinstance(value, str) and value not in allowed:
            same = [a for a in allowed if _norm(a) == _norm(value)]
            if len(same) == 1:
                out[key] = same[0]
                notes.append(f"{key}: {value!r} was read as {same[0]!r}")
    present = set(files)
    base: Dict[str, List[str]] = {}
    for f in files:
        base.setdefault(os.path.basename(f).lower(), []).append(f)
    def same_stem(value: str, kind: str) -> List[str]:
        stem = os.path.splitext(os.path.basename(value))[0].lower()
        return [f for f in files if os.path.splitext(os.path.basename(f))[0].lower() == stem and _kind_of(f) == kind]

    for key, value in list(out.items()):                            # a file name without its folder, or with the extension of its companion
        if key in FILE_PARAMS and isinstance(value, str) and value and value not in present and not os.path.isabs(value):
            hit = base.get(os.path.basename(value).lower(), [])
            if len(hit) == 1:
                out[key] = hit[0]
                notes.append(f"{key}: {value!r} was found at {hit[0]!r}")
            elif not hit and len(same_stem(value, FILE_PARAMS[key])) == 1:
                out[key] = same_stem(value, FILE_PARAMS[key])[0]
                notes.append(f"{key}: there is no {value!r}; {out[key]!r} has the same name and was used")
    top, traj = out.get("topology"), out.get("trajectory")           # a trajectory given as the topology
    if "topology" in props and "trajectory" in props and isinstance(top, str) and _kind_of(top) == "trajectory" and (not traj or _kind_of(str(traj)) in ("structure", "trajectory")):
        structures = same_stem(top, "structure") or [f for f in files if _kind_of(f) == "structure" and not f.lower().endswith(".psf")]
        if traj and _kind_of(str(traj)) == "structure":                 # given the wrong way round
            out["topology"], out["trajectory"] = traj, top
            notes.append("the trajectory was given as the topology; they were put the right way round")
        elif len(structures) == 1:                                       # the trajectory named twice, or alone: the topology is its structure
            out["topology"], out["trajectory"] = structures[0], top
            notes.append(f"topology: {top!r} is a trajectory; {structures[0]!r} was used as the structure")
    for key in required:                                            # a required file left out, and one file in the folder fits
        kind = FILE_PARAMS.get(key)
        if kind and key not in out:
            fits = [f for f in files if _kind_of(f) == kind]
            if kind == "structure":
                fits = [f for f in fits if not f.lower().endswith(".psf")] or fits
            if len(fits) == 1:
                out[key] = fits[0]
                notes.append(f"{key}: {fits[0]!r} was used (the only {kind} file in the folder)")
    return out, notes
