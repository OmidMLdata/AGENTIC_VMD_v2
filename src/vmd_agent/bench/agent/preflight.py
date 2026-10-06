"""Readiness checks before a benchmark run.

Everything that can go wrong with a bring-your-own-VMD, bring-your-own-key
run is cheaper to find here than 200 model calls into a run: VMD missing or not
launching, no ray tracer, a selection that VMD cannot evaluate, code execution
requested outside a container, an API key that model-written code could read.

Each check returns ``{"name", "status", "detail", "needed_for"}`` with status
``ok``, ``warn``, ``fail`` or ``skip``. A ``fail`` blocks only the arms that
need that check. The model API is **not** called unless ``live_api`` is set.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from typing import List, Optional, Sequence

from vmd_agent.bench.agent.tools import (
    ARMS, NEEDS_EXEC, PYTHON_TIMEOUT_S, sanitized_env)

_PDB = """\
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00           C
ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.00           C
ATOM      4  O   ALA A   1       1.251   2.390   0.000  1.00  0.00           O
ATOM      5  CB  ALA A   1       1.986  -0.760  -1.216  1.00  0.00           C
END
"""


def _c(name, status, detail, needed_for=()):
    return {"name": name, "status": status, "detail": detail,
            "needed_for": list(needed_for)}


def in_container() -> bool:
    """Best-effort: Docker, Podman or a cgroup that names a container runtime."""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    try:
        with open("/proc/1/cgroup") as fh:
            t = fh.read()
        return any(k in t for k in ("docker", "containerd", "kubepods", "lxc"))
    except OSError:
        return False


def _vmd_checks(vmd_path: Optional[str], tmp: str) -> List[dict]:
    from vmd_agent.environment import find_vmd, find_tachyon, _vmd_version
    out = []
    vmd = find_vmd(vmd_path)
    if not vmd:
        hint = ("set VMD_BIN to the vmd launcher or its install directory, or "
                "pass --vmd")
        if platform.system() == "Darwin":
            hint += (" (macOS: look inside /Applications/VMD*.app/Contents/vmd"
                     "; a Linux container needs the Linux VMD tarball instead)")
        return [_c("vmd_found", "fail", "VMD not found; " + hint,
                   ["vmd_plain"]),
                _c("vmd_smoke", "skip", "needs VMD", ["vmd_plain"]),
                _c("vmd_selection", "skip", "needs VMD", ["vmd_plain"]),
                _c("tachyon_internal", "skip", "needs VMD", ["vmd_plain"]),
                _c("tachyon", "skip", "needs VMD", [])]
    ver = _vmd_version(vmd)
    out.append(_c("vmd_found", "ok", f"{vmd} (version {ver or 'unknown'})",
                  ["vmd_plain"]))
    pdb = os.path.join(tmp, "pf.pdb")
    with open(pdb, "w") as fh:
        fh.write(_PDB)
    from vmd_agent.visual import render
    smoke = render.run_vmd_tcl(
        f'mol new {{{pdb}}} type pdb waitfor all\n'
        'puts "PFATOMS=[[atomselect top all] num]"\n', vmd, timeout=120,
        env=sanitized_env())
    n = [ln for ln in (smoke.get("stdout") or "").splitlines()
         if ln.startswith("PFATOMS=")]
    if n and n[0] == "PFATOMS=5":
        out.append(_c("vmd_smoke", "ok",
                      "headless (-dispdev text) load and atom count work",
                      ["vmd_plain"]))
    else:
        out.append(_c("vmd_smoke", "fail",
                      "VMD ran but did not load a PDB headlessly: "
                      + str(smoke.get("error") or smoke.get("stderr")
                            or smoke.get("stdout"))[:200], ["vmd_plain"]))
    try:
        from vmd_agent.bench.agent.scoring import vmd_selected_indices
        got = vmd_selected_indices(pdb, "index 0 1 2", vmd)
        out.append(_c("vmd_selection",
                      "ok" if got == {0, 1, 2} else "fail",
                      "VMD evaluates a selection to 0-based indices"
                      if got == {0, 1, 2} else f"unexpected result {sorted(got)}",
                      ["vmd_plain"]))
    except Exception as e:                              # noqa: BLE001
        out.append(_c("vmd_selection", "fail",
                      f"{type(e).__name__}: {e}"[:200], ["vmd_plain"]))
    tga = os.path.join(tmp, "pf.tga")
    r = render.run_vmd_tcl(
        f'mol new {{{pdb}}} type pdb waitfor all\n'
        'display resize 64 64\n'
        f'render TachyonInternal {{{tga}}}\n', vmd, timeout=120,
        env=sanitized_env())
    if os.path.exists(tga) and os.path.getsize(tga) > 0:
        out.append(_c("tachyon_internal", "ok",
                      "built-in ray tracer writes an image headlessly",
                      ["vmd_plain"]))
    else:
        out.append(_c("tachyon_internal", "warn",
                      "no image from `render TachyonInternal`; the plain-VMD "
                      "arm will not be able to make keyframe images: "
                      + str(r.get("stderr") or r.get("error") or "")[:160],
                      ["vmd_plain"]))
    t = find_tachyon(vmd)
    out.append(_c("tachyon", "ok" if t else "warn",
                  t or "external Tachyon not found; the toolkit's VMD "
                       "renderer needs it (the matplotlib renderer does not)",
                  []))
    return out


def preflight(arms: Sequence[str] = ("vmd_agent",),
              vmd_path: Optional[str] = None, allow_exec: bool = False,
              suite_dir: Optional[str] = None, out_dir: Optional[str] = None,
              model: Optional[str] = None, live_api: bool = False,
              require_container: bool = True) -> dict:
    """Run the checks relevant to ``arms``; see the module docstring."""
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        raise ValueError(f"unknown arms {unknown}; choose from {sorted(ARMS)}")
    checks: List[dict] = []
    checks.append(_c("python", "ok" if sys.version_info >= (3, 9) else "fail",
                     platform.python_version(), list(ARMS)))
    libs = []
    for mod in ("MDAnalysis", "numpy", "scipy", "matplotlib", "PIL"):
        try:
            __import__(mod)
        except Exception:                               # noqa: BLE001
            libs.append(mod)
    checks.append(_c("libraries", "fail" if libs else "ok",
                     "missing: " + ", ".join(libs) if libs
                     else "MDAnalysis, numpy, scipy, matplotlib, Pillow",
                     list(ARMS)))
    with tempfile.TemporaryDirectory(prefix="vmd_agent_pf_") as tmp:
        checks += _vmd_checks(vmd_path, tmp)
    from vmd_agent.environment import _which
    checks.append(_c("ffmpeg", "ok" if _which("ffmpeg") else "warn",
                     _which("ffmpeg") or "not found (only movies need it)",
                     []))

    exec_arms = [a for a in arms if set(ARMS[a]) & NEEDS_EXEC]
    if exec_arms:
        checks.append(_c("code_execution",
                         "ok" if allow_exec else "fail",
                         "enabled" if allow_exec else
                         "these arms run model-written code; pass "
                         "--allow-exec (inside a container or VM)",
                         exec_arms))
        cont = in_container()
        checks.append(_c(
            "container", "ok" if cont else
            ("fail" if require_container and allow_exec else "warn"),
            "running inside a container" if cont else
            "NOT inside a container: model-written code would run on this "
            "machine with your user's permissions. Use the Docker image, or "
            "pass --no-require-container if this is a disposable VM",
            exec_arms))
        env = sanitized_env()
        leaked = [k for k in env if any(
            w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD",
                                     "CREDENTIAL"))]
        r = subprocess.run(
            [sys.executable, "-c",
             "import os;print(sorted(k for k in os.environ if any("
             "w in k.upper() for w in ('KEY','TOKEN','SECRET','PASSWORD')))) "],
            capture_output=True, text=True, timeout=PYTHON_TIMEOUT_S, env=env)
        checks.append(_c("secrets_scrubbed",
                         "ok" if not leaked and r.returncode == 0 and
                         r.stdout.strip() == "[]" else "fail",
                         "model-written code sees no key/token/secret "
                         "variables" if not leaked else
                         "would expose: " + ", ".join(leaked), exec_arms))

    if model:
        key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        checks.append(_c("api_key", "ok" if key else "fail",
                         "ANTHROPIC_API_KEY is set" if key else
                         "ANTHROPIC_API_KEY is not set", ["model"]))
        try:
            import anthropic
            checks.append(_c("anthropic_sdk", "ok",
                             f"anthropic {anthropic.__version__}", ["model"]))
        except ImportError:
            anthropic = None
            checks.append(_c("anthropic_sdk", "fail",
                             "pip install anthropic", ["model"]))
        if live_api and key and anthropic is not None:
            try:
                anthropic.Anthropic().messages.create(
                    model=model, max_tokens=8,
                    messages=[{"role": "user", "content": "ping"}])
                checks.append(_c("api_call", "ok",
                                 f"model '{model}' answered a 1-line ping",
                                 ["model"]))
            except Exception as e:                      # noqa: BLE001
                checks.append(_c("api_call", "fail",
                                 f"{type(e).__name__}: {e}"[:200], ["model"]))
        else:
            checks.append(_c("api_call", "skip",
                             "not called (pass --live-api to spend a few "
                             "tokens on one ping)", ["model"]))
    if suite_dir:
        ok = os.path.exists(os.path.join(suite_dir, "tasks.json")) and \
            os.path.exists(os.path.join(suite_dir, "truth.json"))
        checks.append(_c("suite", "ok" if ok else "fail",
                         suite_dir if ok else
                         f"no tasks.json/truth.json in {suite_dir}; run "
                         "`bench agent-suite` first", list(ARMS)))
    if out_dir:
        try:
            os.makedirs(out_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=out_dir):
                pass
            checks.append(_c("out_dir", "ok", f"{out_dir} is writable",
                             list(ARMS)))
        except OSError as e:
            checks.append(_c("out_dir", "fail", str(e)[:160], list(ARMS)))

    relevant = set(arms) | ({"model"} if model else set())
    blocking = [c for c in checks if c["status"] == "fail"
                and (set(c["needed_for"]) & relevant)]
    advisory = [c for c in checks if c["status"] == "warn"
                and (not c["needed_for"] or set(c["needed_for"]) & relevant)]
    # Renderer actually used by the toolkit arms: VMD when present, else
    # matplotlib. Results differ, so a run must record which.
    vmd_ok = any(c["name"] == "vmd_found" and c["status"] == "ok"
                 for c in checks)
    return {"ready": not blocking, "arms": list(arms),
            "toolkit_renderer": "vmd" if vmd_ok else "matplotlib",
            "blocking": [c["name"] for c in blocking],
            "advisory": [c["name"] for c in advisory], "checks": checks}


def report_text(result: dict) -> str:
    mark = {"ok": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "skip"}
    L = [f"{mark[c['status']]:4}  {c['name']:18} {c['detail']}"
         for c in result["checks"]]
    L.append("")
    L.append(f"toolkit arms will render with: {result['toolkit_renderer']}")
    L.append("READY" if result["ready"] else
             "NOT READY: fix " + ", ".join(result["blocking"]))
    return "\n".join(L)
