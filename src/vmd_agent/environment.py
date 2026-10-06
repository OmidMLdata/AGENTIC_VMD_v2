"""Locate VMD and report the runtime capabilities of the host machine."""
from __future__ import annotations

import os
import glob
import shutil
import subprocess
from typing import Optional

# Common install roots to probe when VMD is not on PATH.
_COMMON_VMD_DIRS = [
    "/usr/local/bin",
    "/usr/local/lib/vmd",
    "/opt/vmd",
    "/opt/vmd/bin",
    os.path.expanduser("~/Software"),
    os.path.expanduser("~/software"),
    os.path.expanduser("~/vmd"),
    "/Applications/VMD*.app/Contents/vmd",  # macOS
]


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def find_vmd(hint: Optional[str] = None) -> Optional[str]:
    """Return a runnable path to the ``vmd`` launcher, or ``None``.

    ``hint`` may be a direct path to the vmd executable OR to an install
    directory (e.g. ``~/Software/vmd-1.9.4a57`` or ``/opt/vmd``).
    """
    candidates: list[str] = []

    def from_path(p):
        """A file is itself; a directory is searched like an install dir."""
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            return [os.path.join(p, "vmd"), os.path.join(p, "bin", "vmd"),
                    *glob.glob(os.path.join(p, "vmd_*"))]
        return [p]

    if hint:
        if os.path.isfile(hint) and os.access(hint, os.X_OK):
            return hint
        candidates += from_path(hint)
    env = os.environ.get("VMD_BIN") or os.environ.get("VMDBIN")
    if env:
        candidates += from_path(env)       # documented: a directory is fine
    onpath = _which("vmd")
    if onpath:
        candidates.append(onpath)
    for root in _COMMON_VMD_DIRS:
        for g in glob.glob(root):
            candidates += [os.path.join(g, "vmd")]
            candidates += glob.glob(os.path.join(g, "vmd_*"))   # macOS app binary
            candidates += glob.glob(os.path.join(g, "vmd-*", "vmd"))
            candidates += glob.glob(os.path.join(g, "vmd*", "bin", "vmd"))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def vmd_runtime_env(vmd_path: str, base: Optional[dict] = None) -> dict:
    """The environment to launch ``vmd_path`` with.

    VMD finds its scripts and plugins through ``VMDDIR``. A normal Linux
    install uses a launcher script that sets it. The macOS app ships the bare
    binary (``vmd_MACOSX...``) next to ``scripts/`` and ``plugins/`` and relies
    on the app's startup script; started directly it may not find them. When
    ``VMDDIR`` is unset and the directory beside the binary looks like VMD's
    library directory, point ``VMDDIR`` at it. Never overrides a value that is
    already set.
    """
    env = dict(os.environ if base is None else base)
    if env.get("VMDDIR"):
        return env
    d = os.path.dirname(os.path.realpath(vmd_path))
    if os.path.basename(vmd_path).startswith("vmd_") and \
            os.path.isdir(os.path.join(d, "scripts")):
        env["VMDDIR"] = d
    return env


def find_tachyon(vmd_path: Optional[str]) -> Optional[str]:
    """Locate the bundled Tachyon ray tracer used for headless rendering."""
    roots = []
    if vmd_path:
        d = os.path.dirname(os.path.realpath(vmd_path))
        roots += [d, os.path.dirname(d)]
    roots += ["/usr/local/lib/vmd", "/opt/vmd"]
    for r in roots:
        for pat in ("tachyon_*", "lib*/tachyon_*", "*/tachyon_*"):
            for hit in glob.glob(os.path.join(r, pat)):
                if os.access(hit, os.X_OK):
                    return hit
    onpath = _which("tachyon")
    return onpath


def _vmd_version(vmd_path: str) -> Optional[str]:
    """Ask VMD for its version string in text mode (fast, no display)."""
    try:
        out = subprocess.run(
            [vmd_path, "-dispdev", "text", "-e", "/dev/stdin"],
            input="puts \"VMDVER=[vmdinfo version]\"\nquit\n",
            capture_output=True, text=True, timeout=30,
            env=vmd_runtime_env(vmd_path),
        )
        for line in (out.stdout + out.stderr).splitlines():
            if "VMDVER=" in line:
                return line.split("VMDVER=", 1)[1].strip()
    except Exception:
        return None
    return None


def _lib_available(mod: str) -> bool:
    import importlib
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def probe_environment(vmd_path: Optional[str] = None) -> dict:
    """Report what this machine can do (host facts only).

    Returns the VMD launcher, Tachyon, ffmpeg and the Python analysis libraries
    available. The drawing backends are added on top by
    :func:`vmd_agent.auto.probe_environment`, which is what the CLI and the MCP
    tool call; this module stays at the bottom of the dependency order.
    """
    vmd = find_vmd(vmd_path)
    tachyon = find_tachyon(vmd)
    libs = {m: _lib_available(m) for m in
            ("MDAnalysis", "freesasa", "numpy", "scipy", "matplotlib", "PIL",
              "mdtraj", "networkx", "pandas")}
    report = {
        "vmd_found": vmd is not None,
        "vmd_path": vmd,
        "vmd_version": _vmd_version(vmd) if vmd else None,
        "tachyon_path": tachyon,
        "ffmpeg": _which("ffmpeg"),
        "analysis_libs": libs,
        "can_render": vmd is not None,
        "can_analyze": libs["MDAnalysis"],
        "notes": [],
    }
    report["in_docker"] = os.path.exists("/.dockerenv")
    if not vmd:
        report["notes"].append(
            "VMD not located. Pass an explicit path or install dir "
            "(e.g. ~/Software/vmd-1.9.4a57), or set $VMD_BIN. VMD is not "
            "bundled (UIUC license); download it from "
            "https://www.ks.uiuc.edu/Research/vmd/. Analysis, recipe "
            "generation and the open-source matplotlib renderer work "
            "without it.")
    if vmd and not tachyon:
        report["notes"].append(
            "VMD found but the Tachyon ray tracer was not located next to it; "
            "headless publication rendering may be unavailable. Interactive "
            "'render snapshot' still works if an X display is present.")
    if not report["ffmpeg"]:
        report["notes"].append("ffmpeg absent: movie assembly will be skipped.")
    return report
