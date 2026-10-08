"""The tool library described for a form, and a terminal line run as a command.

The web page shows every tool as a form (drop-downs, check boxes, number boxes, file pickers) generated from the tool's own signature, so a form,
the model's call and ``vmd-agent tool NAME`` cannot drift apart. :func:`catalogue` is that description, :func:`coerce` turns what a form
sends into the tool's arguments, :func:`command_for` writes the equivalent command line, and :func:`run_line` runs a line typed into the page's
terminal (``tool NAME ...``, ``tools``) through the same parser as the real command line.
"""
from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import shlex
import typing
from typing import Dict, List, Optional, Tuple

from vmd_agent import progress, toolcli, toolhints, toolset

#: parameter -> the kind of file the form offers in a drop-down (``any``: every file); anything else is a text box
FILE_ROLES: Dict[str, str] = {
    "topology": "structure", "model": "structure", "mobile": "structure", "reference": "structure", "psf": "structure", "pdb": "structure",
    "psf_a": "structure", "pdb_a": "structure", "psf_b": "structure", "pdb_b": "structure", "input_pdb": "structure",
    "trajectory": "trajectory", "map_file": "map", "map_a": "map", "map_b": "map", "video": "video", "image_path": "image", "paths": "any",
}
#: (tool, parameter) -> role, where the name alone is ambiguous
ROLE_OVERRIDES: Dict[Tuple[str, str], str] = {("inspect_map", "path"): "map", ("view_image", "path"): "image", ("verify_provenance", "path_or_dir"): "any"}
#: list parameters shown as a row of check boxes
CHECKBOX_LISTS: Dict[str, List[str]] = {"analyses": ["rmsd", "rmsf", "rgyr", "hbonds", "contacts", "distance", "sasa", "density", "convergence"],
                                        "views": ["front", "side", "top", "iso"]}
#: parameters a form shows under "more options" because most people never change them
_ADVANCED = ("vmd_path", "session_dir")


def _kind(tp) -> str:
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Union:
        real = [a for a in args if a is not type(None)]
        return _kind(real[0]) if real else "string"
    if origin in (list, typing.List):
        return "array"
    return {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object"}.get(tp, "string")


def _params(name: str) -> List[dict]:
    fn = toolset.TOOLS[name]
    hints = typing.get_type_hints(fn)
    out = []
    for pname, p in inspect.signature(fn).parameters.items():
        if pname in toolset.HIDDEN_FROM_MODELS:
            continue
        kind = _kind(hints.get(pname, str))
        required = p.default is inspect.Parameter.empty
        role = ROLE_OVERRIDES.get((name, pname)) or FILE_ROLES.get(pname) or ("output" if pname in toolcli.OUTPUTS else "")
        entry = {"name": pname, "kind": kind, "required": required, "default": None if required else p.default,
                 "help": toolcli.HELP_SHORT.get(pname) or toolhints.PARAM_HELP.get(pname) or pname.replace("_", " "), "role": role,
                 "advanced": pname in _ADVANCED or (not required and not role and pname not in CHECKBOX_LISTS and kind in ("string",) and pname.startswith("selection") and False)}
        if (name, pname) in toolhints.CHOICES:
            entry["enum"] = list(toolhints.CHOICES[(name, pname)])
        if kind == "array" and pname in CHECKBOX_LISTS:
            entry["options"] = CHECKBOX_LISTS[pname]
        out.append(entry)
    return out


def catalogue() -> dict:
    """The groups of the library, each tool with its summary, whether it needs VMD, an example command and the parameters of its form."""
    groups = []
    for group, what, tools in toolset.LIBRARY:
        items = []
        for n, needs in tools:
            items.append({"name": n, "summary": toolcli.SUMMARY.get(n, ""), "needs": needs, "example": toolcli.EXAMPLES.get(n, ""),
                          "doc": " ".join((toolset.TOOLS[n].__doc__ or "").split()), "params": _params(n)})
        groups.append({"name": group, "what": what, "tools": items})
    return {"groups": groups}


def coerce(name: str, args: dict) -> dict:
    """What a form sent, as the tool's arguments: numbers as numbers, empty boxes left out, a list given as lines or words, JSON text as an object."""
    if name not in toolset.library_tools():
        raise ValueError(f"no such tool: {name}")
    wanted = {p["name"]: p for p in _params(name)}
    out: dict = {}
    for key, val in (args or {}).items():
        p = wanted.get(key)
        if p is None:
            raise ValueError(f"{name} has no parameter {key}")
        if val is None or (isinstance(val, str) and not val.strip()) or val == []:
            continue
        kind = p["kind"]
        try:
            if kind == "integer":
                val = int(val)
            elif kind == "number":
                val = float(val)
            elif kind == "boolean":
                val = val if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes", "on")
            elif kind == "array" and isinstance(val, str):
                val = [w for w in val.replace(",", "\n").splitlines() if w.strip()] if p["name"] in ("claims",) else shlex.split(val)
            elif kind == "object" and isinstance(val, str):
                val = json.loads(val)
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(f"{key}: {e}")
        out[key] = val
    missing = [k for k, p in wanted.items() if p["required"] and k not in out]
    if missing:
        raise ValueError("needed: " + ", ".join(missing))
    return out


def command_for(name: str, args: dict) -> str:
    """The ``vmd-agent tool`` command that does what a form asked (the same flags the command line generates from the signature)."""
    fn = toolset.TOOLS[name]
    hints = typing.get_type_hints(fn)
    sig = inspect.signature(fn)
    has_required_list = any(n in toolcli.POSITIONAL_LISTS and p.default is inspect.Parameter.empty for n, p in sig.parameters.items())
    pos: List[str] = []
    flags: List[str] = []
    for pname, p in sig.parameters.items():
        if pname not in args or args[pname] is None:
            continue
        v, has_default = args[pname], p.default is not inspect.Parameter.empty
        if has_default and v == p.default and pname not in toolcli.OUTPUTS:
            continue
        kind = _kind(hints.get(pname, str))
        if pname == "vmd_path":
            flags += ["--vmd", str(v)]
        elif pname in toolcli.OUTPUTS:
            if not (has_default and v == p.default):
                flags += ["--out", str(v)]
        elif pname in toolcli.JSON_PARAMS:
            flags += ["--scene", json.dumps(v)]
        elif kind == "object":
            flags += [toolcli._flag(pname), json.dumps(v)]
        elif pname in ("topology", "trajectory") and not has_required_list and (has_default or typing.get_origin(hints.get(pname)) is typing.Union):
            pos.append(str(v))
        elif kind == "array":
            if has_default or pname not in toolcli.POSITIONAL_LISTS:
                flags += [toolcli._flag(pname)] + [str(x) for x in v]
            else:
                pos += [str(x) for x in v]
        elif not has_default:
            pos.append(str(v))
        elif kind == "boolean":
            flags.append(toolcli._flag(pname) if v else "--no-" + pname.replace("_", "-"))
        else:
            flags += [toolcli._flag(pname), str(v)]
    return " ".join(shlex.quote(x) for x in ["vmd-agent", "tool", name, *pos, *flags])


# ------------------------------------------------------------------------------------------------ the page's terminal
class _Quiet(argparse.ArgumentParser):
    def error(self, message):                                  # a mistake in a typed line is a message, not an exit
        raise ValueError(message)


_PARSER: Optional[argparse.ArgumentParser] = None


def _parser() -> argparse.ArgumentParser:
    global _PARSER
    if _PARSER is None:
        p = _Quiet(prog="vmd-agent", add_help=False)
        sub = p.add_subparsers(dest="cmd", parser_class=_Quiet)
        sub.add_parser("tools", add_help=False)
        toolcli.add_commands(sub)
        _PARSER = p
    return _PARSER


TERMINAL_HELP = ("Terminal: the command line of vmd-agent, run in your files folder.\n"
                 "  tools                     the tool library, in groups\n"
                 "  tool NAME ...             run one tool (tool NAME --help shows its flags and an example)\n"
                 "  workflow                  list the whole jobs (run one in the Whole jobs tab)\n"
                 "A leading 'vmd-agent' is accepted. VMD's own commands (mol new, animate goto, ...) work in the console as well.")


def run_line(line: str, emit_progress=None) -> Tuple[bool, str]:
    """Run one line typed into the terminal: ``tools``, ``tool NAME ...``, ``workflow``. Returns (ok, the text it printed)."""
    try:
        words = shlex.split(line)
    except ValueError as e:
        return False, f"cannot read that line: {e}"
    if words and words[0] == "vmd-agent":
        words = words[1:]
    if not words or words[0] in ("help", "--help", "-h"):
        return True, TERMINAL_HELP
    if words[0] == "tools":
        return True, toolcli.list_commands()
    if words[0] == "workflow":
        from vmd_agent import workflows
        listing = workflows.list_named()["workflows"]
        return True, "\n".join(f"{n:<22} {w['does']}  [files: {', '.join(w['files'])}]" for n, w in listing.items())
    if words[0] != "tool":
        return False, f"unknown command '{words[0]}'. Type help."
    if len(words) == 1:
        return True, toolcli.list_commands()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            args = _parser().parse_args(words)
    except SystemExit:                                          # --help prints and exits
        return True, buf.getvalue().rstrip()
    except ValueError as e:
        return False, str(e)
    name = getattr(args, "_tool", None)
    if not name:
        return True, toolcli.list_commands()
    kwargs = {k: v for k, v in vars(args).items() if k not in {"cmd", "tool_name", "_tool", "full", "quiet"}}
    listener = emit_progress or (lambda m, f=None: None)
    with progress.listen(listener):
        result = toolset.TOOLS[name](**kwargs)
    shown = result if args.full else toolcli.brief(result)
    return not (isinstance(result, dict) and result.get("ok") is False), json.dumps(shown, indent=2, default=str)
