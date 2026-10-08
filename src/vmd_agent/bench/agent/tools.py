"""The tool environment an agent works in, and the arms compared.

An **arm** is a named set of tools. Comparing arms on identical tasks is the
experiment: what does the toolkit add over a model that writes its own code?

====================  =========================================================
``vmd_agent``         the toolkit's analysis, selection, claim and render tools
``vmd_agent_no_verify``   same, without ``verify_claims`` (ablation)
``vmd_agent_no_keyframes``  same, without ``select_keyframes`` (ablation)
``python_mdanalysis``  ``run_python``: the model writes MDAnalysis/NumPy itself
``vmd_plain``          ``run_tcl``: the model writes Tcl for a real VMD
====================  =========================================================

Every arm also gets ``list_files``, ``read_text_file`` and ``submit_answer``.

Safety. File arguments are confined to the task's workspace. ``run_python``
runs model-written code in a subprocess with a timeout; that is **not a
sandbox**. Enable it (``allow_exec=True``) only inside a container or VM.
``run_tcl`` goes through the toolkit's Tcl screen, which is an accident
guard, not a boundary (see ``README.md#security``), and needs a real VMD.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Callable, Dict, List, Optional

from vmd_agent import security
from vmd_agent.llm_client import compact, render_result  # noqa: F401


COMMON = ("list_files", "read_text_file", "submit_answer")
ARMS: Dict[str, tuple] = {
    "vmd_agent": COMMON + (
        "probe_environment", "inspect_files", "detect_system",
        "structure_stats", "analyze_trajectory", "select_keyframes",
        "verify_claims"),
    "vmd_agent_no_verify": COMMON + (
        "probe_environment", "inspect_files", "detect_system",
        "structure_stats", "analyze_trajectory", "select_keyframes"),
    "vmd_agent_no_keyframes": COMMON + (
        "probe_environment", "inspect_files", "detect_system",
        "structure_stats", "analyze_trajectory", "verify_claims"),
    "python_mdanalysis": COMMON + ("run_python",),
    "vmd_plain": COMMON + ("run_tcl",),
}
NEEDS_EXEC = {"run_python", "run_tcl"}
PYTHON_TIMEOUT_S = 120
VMD_TIMEOUT_S = 300

# Environment variables model-written code may see. Everything else, above all
# API keys and cloud credentials, is dropped: the benchmark process holds the
# model API key, and code the model writes must not be able to read or print it.
_ENV_ALLOW = ("PATH", "HOME", "USER", "LANG", "TZ", "TMPDIR", "TERM",
              "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "MPLCONFIGDIR",
              "MPLBACKEND", "DISPLAY", "TCL_LIBRARY", "TK_LIBRARY",
              "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
              "VMD_AGENT_ALLOWED_ROOTS",
              # Windows: programs fail to start or find system DLLs without these
              "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP",
              "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
              "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES",
              "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
_ENV_ALLOW_PREFIX = ("LC_", "VMD")


def sanitized_env(extra: Optional[dict] = None) -> dict:
    """A minimal environment for running model-written code or VMD.

    A whitelist, not a blacklist: a variable is passed only if it is known to be
    needed (search paths, locale, VMD's own ``VMDDIR`` and friends)."""
    env = {k: v for k, v in os.environ.items()
           if k in _ENV_ALLOW or k.startswith(_ENV_ALLOW_PREFIX)}
    env.update(extra or {})
    return env


class StepLimit(Exception):
    pass


# compact() and render_result() live in vmd_agent.llm_client (shared with the chat
# command) and are re-exported here.


# ------------------------------------------------------------ environment
class Environment:
    """One task's workspace and the tools an arm may use."""

    def __init__(self, task: dict, arm: str, allow_exec: bool = False,
                 vmd_path: Optional[str] = None, max_steps: int = 30):
        if arm not in ARMS:
            raise ValueError(f"unknown arm '{arm}'; choose from "
                             f"{sorted(ARMS)}")
        self.task, self.arm = task, arm
        self.workdir = os.path.realpath(task["workdir"])
        self.allow_exec, self.vmd_path = allow_exec, vmd_path
        self.max_steps = max_steps
        self.names = [n for n in ARMS[arm]
                      if allow_exec or n not in NEEDS_EXEC]
        self.submitted: Optional[dict] = None
        self.log: List[dict] = []
        self.blocked = 0
        self.tool_errors = 0
        self.t0 = time.time()
        self.tool_s = 0.0

    # ---- specs
    def tool_specs(self) -> List[dict]:
        return [{"name": n, "description": _SPECS[n][0],
                 "input_schema": _SPECS[n][1]} for n in self.names]

    # ---- paths
    def path(self, p) -> str:
        if not isinstance(p, str) or not p:
            raise ValueError("a path string is required")
        full = p if os.path.isabs(p) else os.path.join(self.workdir, p)
        real = os.path.realpath(full)
        if not security.is_within(real, self.workdir):
            raise PermissionError(
                f"'{p}' is outside the task workspace ({self.workdir})")
        return real

    def _opt(self, p):
        return None if p in (None, "") else self.path(p)

    # ---- dispatch
    def call(self, name: str, args: Optional[dict] = None) -> dict:
        args = args if isinstance(args, dict) else {}
        started = time.time()
        if name not in self.names:
            res = {"error": f"unknown tool '{name}'"
                            if name not in _SPECS else
                            f"tool '{name}' is not available in this setup"}
        elif len(self.log) >= self.max_steps and name != "submit_answer":
            raise StepLimit(f"step limit {self.max_steps} reached")
        else:
            try:
                res = _IMPL[name](self, **args)
            except PermissionError as e:
                self.blocked += 1
                res = {"error": str(e), "blocked": True}
            except TypeError as e:
                res = {"error": f"bad arguments for {name}: {e}"}
            except Exception as e:
                res = {"error": f"{type(e).__name__}: {e}"}
        failed = isinstance(res, dict) and bool(res.get("error"))
        if failed and not res.get("blocked"):
            self.tool_errors += 1
        seconds = time.time() - started
        self.tool_s += seconds
        self.log.append({"tool": name, "args": compact(args),
                         "error": failed, "seconds": round(seconds, 3)})
        return res

    def stats(self) -> dict:
        return {"tool_calls": len(self.log), "tool_errors": self.tool_errors,
                "tool_s": round(self.tool_s, 2),
                "blocked": self.blocked,
                "wall_s": round(time.time() - self.t0, 2)}


# ------------------------------------------------------------ tool bodies
def _list_files(env, path: str = ".") -> dict:
    root = env.path(path)
    out = []
    for dp, _dn, fs in os.walk(root):
        for f in sorted(fs):
            if f.startswith("."):
                continue
            fp = os.path.join(dp, f)
            out.append({"path": fp, "bytes": os.path.getsize(fp)})
        if len(out) >= 200:
            break
    return {"files": out[:200], "workspace": env.workdir}


def _read_text_file(env, path: str, max_bytes: int = 8000) -> dict:
    p = env.path(path)
    with open(p, "rb") as fh:
        raw = fh.read(min(int(max_bytes), 20000))
    if b"\x00" in raw:
        return {"error": "binary file; use an analysis tool instead"}
    return {"text": raw.decode("utf-8", "replace"),
            "truncated": os.path.getsize(p) > len(raw)}


def _submit_answer(env, answer) -> dict:
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except ValueError:
            return {"error": "answer must be a JSON object"}
    if not isinstance(answer, dict):
        return {"error": "answer must be a JSON object"}
    env.submitted = answer
    return {"ok": True, "recorded": True}


def _probe_environment(env) -> dict:
    from vmd_agent import auto
    return auto.probe_environment(None)


def _inspect_files(env, paths) -> dict:
    from vmd_agent.inputs import inspection
    return inspection.inspect_files([env.path(p) for p in paths])


def _detect_system(env, topology: str, trajectory: Optional[str] = None
                   ) -> dict:
    from vmd_agent.structure import detect
    return detect.detect_system(env.path(topology), env._opt(trajectory))


def _structure_stats(env, topology: str, trajectory: Optional[str] = None,
                     frame: int = 0) -> dict:
    from vmd_agent.structure import stats
    st = stats.structure_stats(env.path(topology), env._opt(trajectory),
                               frame=frame)
    if isinstance(st, dict) and not st.get("error"):
        st["caption_lines"] = stats.stats_caption(st)
    return st


def _analyze_trajectory(env, topology: str, trajectory: str,
                        analyses=("rmsd", "rgyr"), selection: str = "protein",
                        sel2: Optional[str] = None, cutoff: float = 4.0,
                        step: int = 1, unwrap: bool = False,
                        dt_ps: Optional[float] = None) -> dict:
    from vmd_agent.dynamics import analysis
    return analysis.analyze_trajectory(
        env.path(topology), env.path(trajectory), list(analyses),
        selection=selection, sel2=sel2, cutoff=cutoff, step=step,
        out_dir=os.path.join(env.workdir, "out"), unwrap=unwrap, dt_ps=dt_ps)


def _select_keyframes(env, topology: str, trajectory: str, k: int = 9,
                      selection: str = "protein", sel2: Optional[str] = None,
                      render: bool = False, renderer: str = "auto",
                      step: int = 1) -> dict:
    from vmd_agent import auto
    return auto.select_keyframes(
        env.path(topology), env.path(trajectory), k=k, selection=selection,
        sel2=sel2, step=step, out_dir=os.path.join(env.workdir, "out"),
        render=render, renderer=renderer, vmd_path=env.vmd_path)


def _verify_claims(env, topology: str, claims, trajectory: Optional[str] = None,
                   frame: int = 0) -> dict:
    from vmd_agent.evidence import claims as cl
    return cl.verify_claims(env.path(topology), list(claims),
                            env._opt(trajectory), frame=frame)


def _run_python(env, code: str) -> dict:
    if not env.allow_exec:
        raise PermissionError("code execution is disabled (allow_exec=False)")
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=env.workdir,
                                     delete=False) as fh:
        fh.write(code)
        path = fh.name
    try:
        r = subprocess.run([sys.executable, path], cwd=env.workdir,
                           capture_output=True, text=True,
                           timeout=PYTHON_TIMEOUT_S, env=sanitized_env())
        return {"returncode": r.returncode, "stdout": r.stdout[-4000:],
                "stderr": r.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {PYTHON_TIMEOUT_S}s"}
    finally:
        os.unlink(path)


def _run_vmd_tcl(env, script: str) -> dict:
    if not env.allow_exec:
        raise PermissionError("code execution is disabled (allow_exec=False)")
    from vmd_agent.visual import render
    r = render.run_tcl(script, env.vmd_path, timeout=VMD_TIMEOUT_S,
                           cwd=env.workdir, env=sanitized_env())
    return {k: r.get(k) for k in ("ok", "error", "blocked", "returncode",
                                  "stdout", "stderr") if k in r}


_IMPL: Dict[str, Callable] = {
    "list_files": _list_files, "read_text_file": _read_text_file,
    "submit_answer": _submit_answer, "probe_environment": _probe_environment,
    "inspect_files": _inspect_files, "detect_system": _detect_system,
    "structure_stats": _structure_stats,
    "analyze_trajectory": _analyze_trajectory,
    "select_keyframes": _select_keyframes, "verify_claims": _verify_claims,
    "run_python": _run_python, "run_tcl": _run_vmd_tcl,
}

_STR = {"type": "string"}


def _obj(props, required=()):
    return {"type": "object", "properties": props,
            "required": list(required)}


_SPECS: Dict[str, tuple] = {
    "list_files": ("List the files in the task workspace.",
                   _obj({"path": _STR})),
    "read_text_file": ("Read the start of a text file (PDB, JSON, ...).",
                       _obj({"path": _STR, "max_bytes": {"type": "integer"}},
                            ["path"])),
    "submit_answer": ("Submit the final answer as a JSON object in the format "
                      "the task asks for. Ends the task.",
                      _obj({"answer": {"type": "object"}}, ["answer"])),
    "probe_environment": ("Report what this machine can do (renderers, "
                          "libraries).", _obj({})),
    "inspect_files": ("Classify files and report missing companions.",
                      _obj({"paths": {"type": "array", "items": _STR}},
                           ["paths"])),
    "detect_system": ("Load a system, classify its components and report "
                      "integrity warnings.",
                      _obj({"topology": _STR, "trajectory": _STR},
                           ["topology"])),
    "structure_stats": ("Bonds, disulfides, H-bonds, chains and DSSP "
                        "secondary-structure content.",
                        _obj({"topology": _STR, "trajectory": _STR,
                              "frame": {"type": "integer"}}, ["topology"])),
    "analyze_trajectory": (
        "Run rmsd, rmsf, rgyr, hbonds, contacts, distance, sasa, density or "
        "convergence on a trajectory with honest time axes, statistics and "
        "periodic-boundary checks. Read the notes and pbc fields.",
        _obj({"topology": _STR, "trajectory": _STR,
              "analyses": {"type": "array", "items": _STR},
              "selection": _STR, "sel2": _STR, "cutoff": {"type": "number"},
              "step": {"type": "integer"}, "unwrap": {"type": "boolean"},
              "dt_ps": {"type": "number"}}, ["topology", "trajectory"])),
    "select_keyframes": (
        "Pick the k most informative frames by detecting change points; "
        "render=true draws each chosen frame to its own image.",
        _obj({"topology": _STR, "trajectory": _STR,
              "k": {"type": "integer"}, "selection": _STR, "sel2": _STR,
              "render": {"type": "boolean"}, "renderer": _STR,
              "step": {"type": "integer"}}, ["topology", "trajectory"])),
    "verify_claims": (
        "Check statements about the system against measurements; each is "
        "supported / contradicted / unverifiable / unparsed.",
        _obj({"topology": _STR, "claims": {"type": "array", "items": _STR},
              "trajectory": _STR, "frame": {"type": "integer"}},
             ["topology", "claims"])),
    "run_python": ("Run a Python 3 script (NumPy, SciPy, MDAnalysis, "
                   "matplotlib are installed) in the workspace; returns "
                   "stdout and stderr.", _obj({"code": _STR}, ["code"])),
    "run_tcl": (
        "Run a Tcl script in headless VMD (text mode, no display) and return "
        "its stdout/stderr. Only what you `puts` is returned. Relative paths "
        "resolve in the workspace. Load with `mol new FILE type pdb waitfor "
        "all` and `mol addfile TRAJ type dcd waitfor all`; select with "
        "`atomselect top \"...\"`; write images with `render TachyonInternal "
        "out.tga` (the `snapshot` renderer needs a display). The script is "
        "screened: exec, open, source, file deletion and similar are refused.",
        _obj({"script": _STR}, ["script"])),
}
