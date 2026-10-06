"""Run provenance: enough to say exactly what produced an output.

A figure or number is only reproducible if you know the software versions, the
exact input bytes and the parameters behind it. :func:`record_run` appends an
entry to ``provenance.json`` in an output directory with:

* the tool and parameters,
* SHA-256 of every input file (size and mtime only above ``hash_limit_mb``),
* Python, platform and package versions, plus VMD and ffmpeg versions,
* the exact Tcl recipe text when one was used,
* output file hashes.

:func:`verify_provenance` re-hashes the inputs and reports any that changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from typing import Dict, Iterable, List, Optional

_PKGS = ("MDAnalysis", "numpy", "scipy", "matplotlib", "PIL", "pandas")
FILE = "provenance.json"


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def describe_file(path: str, hash_limit_mb: float = 2048) -> dict:
    p = os.path.abspath(path)
    if not os.path.exists(p):
        return {"path": p, "exists": False}
    st = os.stat(p)
    d = {"path": p, "exists": True, "size_bytes": st.st_size,
         "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
    if st.st_size <= hash_limit_mb * 1024 * 1024:
        d["sha256"] = sha256_file(p)
    else:
        d["sha256"] = None
        d["note"] = f"larger than {hash_limit_mb} MB; hash skipped"
    return d


def _version(mod: str) -> Optional[str]:
    try:
        m = __import__(mod)
        return getattr(m, "__version__", "unknown")
    except Exception:
        return None


def _tool_version(exe: Optional[str], args) -> Optional[str]:
    if not exe:
        return None
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True,
                             timeout=20)
        text = (out.stdout or out.stderr).strip().splitlines()
        return text[0] if text else None
    except Exception:
        return None


def collect_environment(vmd_path: Optional[str] = None,
                        query_vmd: bool = False) -> dict:
    """Software environment. ``query_vmd`` launches VMD to read its version."""
    from vmd_agent import __version__
    from vmd_agent.environment import find_vmd
    vmd = find_vmd(vmd_path)
    env = {
        "vmd_agent": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {m: _version(m) for m in _PKGS},
        "vmd_path": vmd,
        "ffmpeg": _tool_version(shutil.which("ffmpeg"), ["-version"]),
        "in_docker": os.path.exists("/.dockerenv"),
    }
    if vmd and query_vmd:
        from vmd_agent.environment import _vmd_version
        env["vmd_version"] = _vmd_version(vmd)
    return env


def record_run(out_dir: str, tool: str, params: Optional[dict] = None,
               inputs: Iterable[str] = (), outputs: Iterable[str] = (),
               recipe_text: Optional[str] = None,
               vmd_path: Optional[str] = None,
               extra: Optional[dict] = None) -> str:
    """Append one run to ``<out_dir>/provenance.json`` and return its path."""
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, FILE)
    doc: Dict = {"schema": 1, "runs": []}
    if os.path.exists(path):
        try:
            with open(path) as fh:
                doc = json.load(fh)
        except Exception:
            doc = {"schema": 1, "runs": [], "note": "previous file unreadable"}
    entry = {
        "tool": tool,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "parameters": params or {},
        "inputs": [describe_file(p) for p in inputs if p],
        "outputs": [describe_file(p) for p in outputs if p],
        "environment": collect_environment(vmd_path),
    }
    if recipe_text is not None:
        entry["recipe_sha256"] = hashlib.sha256(
            recipe_text.encode()).hexdigest()
        entry["recipe_tcl"] = recipe_text
    if extra:
        entry["extra"] = extra
    doc["runs"].append(entry)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, default=str)
    return path


def verify_provenance(path_or_dir: str) -> dict:
    """Re-hash recorded inputs/outputs and report anything that changed.

    Only the **latest** record of each file is authoritative. Re-running a
    pipeline into the same folder with different parameters legitimately
    overwrites earlier outputs, so an earlier run's hash for a path that a
    later run also recorded is reported under ``superseded``, not as a
    problem. Without this, ordinary re-runs made verification fail with no
    tampering at all.
    """
    path = path_or_dir
    if os.path.isdir(path):
        path = os.path.join(path, FILE)
    if not os.path.exists(path):
        return {"ok": False, "error": f"no provenance file at {path}"}
    with open(path) as fh:
        doc = json.load(fh)
    runs = doc.get("runs", [])
    last_run_for = {}                      # path -> index of the latest run recording it
    for i, run in enumerate(runs):
        for kind in ("inputs", "outputs"):
            for f in run.get(kind, []):
                last_run_for[f.get("path")] = i
    problems: List[str] = []
    superseded: List[str] = []
    checked = 0
    for i, run in enumerate(runs):
        for kind in ("inputs", "outputs"):
            for f in run.get(kind, []):
                want = f.get("sha256")
                if not want:
                    continue
                if last_run_for.get(f["path"]) != i:
                    superseded.append(f"run {i} {kind}: {f['path']} "
                                      f"(re-recorded by run {last_run_for[f['path']]})")
                    continue
                checked += 1
                if not os.path.exists(f["path"]):
                    problems.append(f"run {i} {kind}: missing {f['path']}")
                elif sha256_file(f["path"]) != want:
                    problems.append(f"run {i} {kind}: changed {f['path']}")
    return {"ok": not problems, "files_checked": checked,
            "problems": problems, "superseded": superseded,
            "n_runs": len(runs)}
