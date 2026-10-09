"""Locate VMD and report the runtime capabilities of the host machine."""
from __future__ import annotations

import os
import glob
import shutil
import subprocess
from typing import Optional

from vmd_agent import platform_info as _plat
from vmd_agent import settings as _settings

# Install roots to probe when VMD is not on PATH, for the OS this runs on.
_COMMON_VMD_DIRS = _plat.vmd_search_dirs()


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def find_ffmpeg() -> Optional[str]:
    """ffmpeg: one on the PATH if there is one, otherwise the copy that comes with the
    ``imageio-ffmpeg`` package (a dependency of vmd-agent, so it lives inside the same private
    environment and nothing has to be installed system-wide). ``None`` only if neither exists."""
    found = _which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe if exe and os.path.isfile(exe) else None
    except Exception:
        return None


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
            names = _plat.vmd_executable_names()
            return [os.path.join(p, n) for n in names] + \
                   [os.path.join(p, "bin", n) for n in names] + \
                   glob.glob(os.path.join(p, "vmd_*"))
        return [p]

    if hint:
        if os.path.isfile(hint) and os.access(hint, os.X_OK):
            return hint
        candidates += from_path(hint)
    env = os.environ.get("VMD_BIN") or os.environ.get("VMDBIN")
    if env:
        candidates += from_path(env)       # documented: a directory is fine
    saved = _settings.get("vmd_path")      # chosen once in `vmd-agent setup`
    if saved:
        candidates += from_path(saved)
    onpath = _which("vmd")
    if onpath:
        candidates.append(onpath)
    names = _plat.vmd_executable_names()
    for root in _COMMON_VMD_DIRS:
        for g in glob.glob(root):
            candidates += [os.path.join(g, n) for n in names]
            candidates += glob.glob(os.path.join(g, "vmd_*"))   # macOS app binary
            for n in names:
                candidates += glob.glob(os.path.join(g, "vmd-*", n))
                candidates += glob.glob(os.path.join(g, "vmd*", "bin", n))
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
    roots += ["/usr/local/lib/vmd", "/opt/vmd"] if _plat.system() != _plat.WINDOWS else []
    for r in roots:
        for pat in ("tachyon_*", "lib*/tachyon_*", "*/tachyon_*"):
            for hit in glob.glob(os.path.join(r, pat)):
                if os.access(hit, os.X_OK):
                    return hit
    onpath = _which("tachyon")
    return onpath


def _vmd_version(vmd_path: str) -> Optional[str]:
    """Ask VMD for its version string in text mode (fast, no display).

    The script goes in a temporary file because the stdin device file exists only
    on Linux and macOS; a real file works on every OS."""
    import tempfile
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False) as fh:
            fh.write('puts "VMDVER=[vmdinfo version]"\nquit\n')
            path = fh.name
        out = subprocess.run(
            [vmd_path, "-dispdev", "text", "-e", path],
            capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL, env=vmd_runtime_env(vmd_path))
        for line in (out.stdout + out.stderr).splitlines():
            if "VMDVER=" in line:
                return line.split("VMDVER=", 1)[1].strip()
    except Exception:
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    return None


#: VMD versions the real-VMD tests (``pytest -m requires_vmd``) have passed against, and on what.
#: Add a version only after they pass on a machine that has it.
VMD_VERSIONS_TESTED: tuple = ("1.9.4a57",)             # macOS arm64 only, 2026-10-06
#: the series the code was written for (an expectation, not a test result)
VMD_SERIES_TARGETED = "1.9"


def vmd_version_note(version: Optional[str]) -> str:
    """A plain sentence on how far to trust this toolkit with the given VMD version string
    (as printed by ``vmdinfo version``, for example ``1.9.4a57``). VMD's version is not
    checked or enforced anywhere: this only tells the user where they stand."""
    if not version:
        return "VMD's version could not be read."
    v = version.strip()
    if any(v == t or v.startswith(t) for t in VMD_VERSIONS_TESTED):
        return f"VMD {v}: tested with this toolkit."
    base = (f"VMD {v}: this toolkit has not been tested with this version; it was tested with "
            f"{', '.join(VMD_VERSIONS_TESTED)} and written for the {VMD_SERIES_TARGETED}.x series.")
    if not v.startswith(VMD_SERIES_TARGETED + "."):
        base += (" This version is outside that series, so scripts may behave differently; "
                 "run `vmd-agent doctor` and check the figures yourself.")
    return base


def vmd_self_test(vmd_path: str, timeout: float = 60.0) -> dict:
    """Actually start VMD headless and make it run a one-line script. Returns
    ``{"ok", "version", "problem", "advice"}``; never raises.

    Finding a file called ``vmd`` is not the same as VMD working: a Linux launcher
    needs ``tcsh``, the program needs its shared libraries, and a macOS binary needs
    its scripts folder. A failure is explained in plain words where the cause is
    recognisable, and otherwise the program's own last lines are shown."""
    import tempfile
    res = {"ok": False, "version": None, "problem": "", "advice": "", "version_note": ""}
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False) as fh:
            fh.write('puts "VMDVER=[vmdinfo version]"\nquit\n')
            path = fh.name
        p = subprocess.run([vmd_path, "-dispdev", "text", "-e", path], capture_output=True,
                           text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           env=vmd_runtime_env(vmd_path))
        text = (p.stdout or "") + (p.stderr or "")
        for line in text.splitlines():
            if "VMDVER=" in line:
                res.update(ok=True, version=line.split("VMDVER=", 1)[1].strip())
                res["version_note"] = vmd_version_note(res["version"])
                return res
        res["problem"] = "VMD started but did not run the test script (exit code %d)." % p.returncode
        low = text.lower()
        if "tcsh" in low or "csh: " in low:
            res["advice"] = "VMD's launcher needs 'tcsh'. Install it (for example: sudo apt install tcsh)."
        elif "shared librar" in low or "cannot open shared object" in low:
            res["advice"] = "A system library VMD needs is missing; the line above names it. Install it with your package manager."
        elif "permission denied" in low:
            res["advice"] = "The file is not executable. Run: chmod +x on it."
        elif "exec format error" in low or "bad cpu type" in low:
            res["advice"] = "This VMD build is for a different CPU or OS than this computer. Download the matching build."
        else:
            res["advice"] = "Last output: " + " | ".join(text.strip().splitlines()[-3:])[:300]
    except subprocess.TimeoutExpired:
        res["problem"] = "VMD did not finish within %d seconds." % int(timeout)
        res["advice"] = "It may be waiting for a display or a licence prompt; try running it once by hand."
    except OSError as err:
        res["problem"] = f"VMD could not be started: {err}"
        res["advice"] = "Check that the path is VMD's launcher and that it is executable."
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    return res


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
        "ffmpeg": find_ffmpeg(),
        "analysis_libs": libs,
        "can_render": vmd is not None,
        "can_analyze": libs["MDAnalysis"],
        "notes": [],
    }
    report["in_docker"] = _plat.in_container()
    report["platform"] = {"system": _plat.system(), "arch": _plat.arch(),
                          "wsl": _plat.is_wsl(),
                          "docker_platform": _plat.docker_platform()}
    if not vmd:
        example = {"windows": r"C:\Program Files\University of Illinois\VMD",
                   "macos": "/Applications/VMD 1.9.4.app/Contents/vmd"
                   }.get(_plat.system(), "~/Software/vmd-1.9.4a57")
        report["notes"].append(
            f"VMD not located. Pass an explicit path or install dir "
            f"(e.g. {example}), or set $VMD_BIN. VMD is not "
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
