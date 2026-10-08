"""Headless rendering and raw-Tcl execution against a real VMD install.

These functions require VMD (and, for publication images, the bundled Tachyon
ray tracer). They run VMD in ``-dispdev text`` mode so no X display is needed.
When VMD cannot be located they return a structured error with guidance rather
than raising, so an agent can fall back to the analysis path.

Changes from the first version
------------------------------
* Scratch directories are removed when a call finishes (they used to leak about
  5 MB of Tachyon scene data per call). Pass ``keep_work=True`` to keep them.
* ``render_movie`` renders every frame inside **one** VMD session with one fixed
  camera. It previously launched VMD once per frame, reloading the whole
  trajectory each time, and reset the camera per frame so the movie jittered.
* ``render_frames`` renders an arbitrary list of frames the same way and backs
  the event-aware keyframe feature.
* ``run_tcl`` screens scripts through :mod:`vmd_agent.security`.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Optional, Sequence

from vmd_agent.environment import find_ffmpeg, find_vmd, find_tachyon, vmd_runtime_env
from vmd_agent.inputs.inspection import _HAS_COORDS
from vmd_agent.visual.recipes import generate_visualization_recipe, _mtype
from vmd_agent import security
import functools

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_VIEW_ROT = {
    "front": [],
    "side":  ["rotate y by 90"],
    "top":   ["rotate x by 90"],
    "iso":   ["rotate x by 30", "rotate y by -30"],
}


def _bg(background: str) -> str:
    """Only ``white`` or ``black``: this value is written straight into Tcl."""
    if str(background).lower() not in ("white", "black"):
        raise security.InvalidInput("background must be 'white' or 'black'")
    return str(background).lower()


def _structured_errors(fn):
    """Turn policy/validation failures into the toolkit's usual error dict."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except (security.SecurityError, security.InvalidInput) as e:
            return {"ok": False, "error": str(e),
                    "blocked": isinstance(e, security.SecurityError)}
    return wrapper


@contextmanager
def _workdir(prefix: str, keep: bool = False):
    """Scratch directory that is deleted on exit unless ``keep`` is set."""
    path = tempfile.mkdtemp(prefix=prefix)
    try:
        yield path
    finally:
        if not keep:
            shutil.rmtree(path, ignore_errors=True)


def _ensure_png(path: str) -> bool:
    """Guarantee `path` really holds PNG bytes.

    Many VMD builds ship a Tachyon compiled without libpng ("-format PNG
    XXX Not compiled into this binary XXX"); it silently falls back to
    uncompressed Targa while still writing to whatever -o name we gave it.
    The result is a .png file that no image reader will open. Convert it
    in place when that happens.
    """
    if not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as fh:
            if fh.read(8) == _PNG_MAGIC:
                return True
    except OSError:
        return False
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(path) as im:
            im.convert("RGB").save(path, format="PNG")
        return True
    except Exception:
        return False


def _reps_only_tcl(recipe_path: str, work_dir: str) -> str:
    """Strip the standalone bits out of a saved recipe before re-sourcing it.

    A recipe written by generate_visualization_recipe is meant to be usable
    on its own in VMD, so it re-loads the molecule (`mol new`) and ends with
    its own `render Tachyon $outfile.dat`. When the render helpers source it
    into a session that has ALREADY loaded the structure, those two lines
    load the molecule a second time and dump a stray multi-MB render.dat
    into the caller's working directory. Keep the representation and scene
    settings, drop the rest.
    """
    try:
        with open(recipe_path) as fh:
            text = fh.read()
    except OSError:
        return f"source {{{security.tcl_path(recipe_path)}}}"
    kept = []
    for line in text.splitlines():
        head = line.strip()
        if head.startswith(("mol new", "mol addfile", "mol delete")):
            continue
        if head.startswith("render ") or head.startswith("set outfile"):
            continue
        kept.append(line)
    stripped = os.path.join(work_dir, "reps_from_recipe.tcl")
    with open(stripped, "w") as fh:
        fh.write("\n".join(kept) + "\n")
    return f"source {{{stripped}}}"


def _reps_tcl(work: str, detection: Optional[dict],
              recipe_path: Optional[str], background: str,
              **recipe_kw) -> str:
    """Tcl line(s) that install the representations in the open session."""
    if recipe_path and os.path.exists(recipe_path):
        return _reps_only_tcl(recipe_path, work)
    if detection is not None:
        rec = generate_visualization_recipe(detection, load_files=False,
                                            background=background,
                                            **recipe_kw)
        reps_file = os.path.join(work, "reps.tcl")
        with open(reps_file, "w") as fh:
            fh.write(rec["tcl"])
        return f"source {{{reps_file}}}"
    return "# no recipe supplied; using default representation"


def _load_lines(topology: str, trajectory: Optional[str]) -> list:
    """VMD load commands, dropping the topology's own frame when a trajectory follows.

    A coordinate-bearing topology (PDB, GRO, mmCIF, ...) contributes a frame of
    its own, so after `mol addfile` VMD holds 1 + N frames and every VMD frame
    index sits one ahead of the trajectory frame it actually shows. That offset
    silently corrupts any frame -> simulation-time mapping and puts a duplicate
    opening frame in every movie. Deleting the topology frame makes VMD frame N
    equal trajectory frame N, which is what callers assume. A topology with no
    coordinates of its own (PSF, prmtop) contributes no frame, so nothing is
    dropped.
    """
    topo = security.tcl_path(topology)
    lines = [f'mol new {{{topo}}} type {{{_mtype(topo)}}} waitfor all']
    if trajectory:
        traj = security.tcl_path(trajectory)
        lines.append(f'mol addfile {{{traj}}} type {{{_mtype(traj)}}} waitfor all')
        if os.path.splitext(topo)[1].lower() in _HAS_COORDS:
            lines.append('animate delete beg 0 end 0 top')
    return lines


def _validate_inputs(topology: str, trajectory: Optional[str],
                     background: str) -> None:
    """Refuse hostile paths and values *before* anything else (including the
    search for VMD), so the answer does not depend on what is installed."""
    _bg(background)
    security.tcl_path(topology)
    if trajectory:
        security.tcl_path(trajectory)


def _image_lines(work: str, scene: str, topology: str,
                 trajectory: Optional[str], frame: int,
                 detection: Optional[dict], recipe_path: Optional[str],
                 background: str) -> list:
    """The Tcl for one image: load, representations, one Tachyon scene."""
    return _load_lines(topology, trajectory) + [
        _reps_tcl(work, detection, recipe_path, background),
        f'animate goto {int(frame) if int(frame) >= 0 else "end"}',
        # No `display resize`: headless VMD aborts on it when stdin is not
        # a TTY (e.g. under the MCP server, whose stdin is the JSON-RPC
        # pipe). Tachyon's -res sets the resolution.
        f'color Display Background {_bg(background)}',
        'display projection Orthographic',
        'axes location off',
        'display resetview',
        f'render Tachyon {{{scene}}}',
        'quit',
    ]


def _views_lines(work: str, scenes: dict, topology: str,
                 trajectory: Optional[str], frame: int,
                 detection: Optional[dict], recipe_path: Optional[str],
                 background: str, **recipe_kw) -> list:
    """The Tcl for several orientations of one scene in a single session."""
    lines = _load_lines(topology, trajectory)
    lines += [_reps_tcl(work, detection, recipe_path, background, **recipe_kw),
              f'animate goto {int(frame) if int(frame) >= 0 else "end"}',
              f'color Display Background {_bg(background)}',
              'display projection Orthographic', 'axes location off']
    for v, scene in scenes.items():
        lines.append('display resetview')
        lines += _VIEW_ROT[v]
        lines.append(f'render Tachyon {{{scene}}}')
    lines.append('quit')
    return lines


def _frames_lines(work: str, scenes: Sequence[str], frames: Sequence[int],
                  topology: str, trajectory: Optional[str],
                  detection: Optional[dict], recipe_path: Optional[str],
                  background: str, view: str, **recipe_kw) -> list:
    """The Tcl for many frames in one session with the camera set once."""
    lines = _load_lines(topology, trajectory)
    lines += [_reps_tcl(work, detection, recipe_path, background, **recipe_kw),
              f'color Display Background {_bg(background)}',
              'display projection Orthographic', 'axes location off',
              f'animate goto {int(frames[0])}', 'display resetview']
    lines += _VIEW_ROT.get(view, [])
    for scene, f in zip(scenes, frames):
        lines.append(f'animate goto {int(f)}')
        lines.append(f'render Tachyon {{{scene}}}')
    lines.append('quit')
    return lines


def _run_vmd_text(vmd: str, tcl_path: str, timeout: int = 900,
                  cwd: Optional[str] = None,
                  env: Optional[dict] = None) -> dict:
    # No -eofexit: it makes VMD quit as soon as ANY input stream hits EOF,
    # including a nested `source {recipe.tcl}`, so the caller's own render
    # lines after the source never execute. Every script generated here ends
    # with an explicit `quit`; stdin=DEVNULL gives the same guaranteed exit
    # if a script ever falls through without one.
    try:
        proc = subprocess.run(
            [vmd, "-dispdev", "text", "-e", tcl_path],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, cwd=cwd,
            env=vmd_runtime_env(vmd, env))
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "",
                "stderr": f"VMD timed out after {timeout}s"}
    return {"returncode": proc.returncode,
            "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


def _run_tachyon(tachyon: str, scene: str, png: str, width: int, height: int,
                 aasamples: int) -> dict:
    try:
        proc = subprocess.run(
            [tachyon, scene, "-aasamples", str(aasamples), "-format", "PNG",
             "-res", str(width), str(height), "-o", png],
            capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        return {"ok": False, "stderr": "Tachyon timed out"}
    _ensure_png(png)
    return {"ok": os.path.exists(png) and os.path.getsize(png) > 0,
            "returncode": proc.returncode, "stderr": proc.stderr[-2000:]}


def _tachyon_many(tachyon: str, jobs: Sequence[tuple], width: int, height: int,
                  aasamples: int, workers: Optional[int] = None) -> dict:
    """Rasterise ``[(scene, png), ...]`` in parallel; return ``{png: result}``."""
    workers = workers or max(1, min(4, (os.cpu_count() or 2)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {png: ex.submit(_run_tachyon, tachyon, scene, png, width,
                               height, aasamples) for scene, png in jobs}
        return {png: f.result() for png, f in futs.items()}


def count_frames(topology: str, trajectory: Optional[str]) -> int:
    """Number of frames VMD will hold for this load (trajectory frames only)."""
    if not trajectory:
        return 1
    try:
        from vmd_agent.inputs.molio import load_universe
        return int(len(load_universe(topology, trajectory).trajectory))
    except Exception:
        return 0


# ------------------------------------------------------------------ raw Tcl
def run_tcl(script: str, vmd_path: Optional[str] = None,
                timeout: int = 900, allow_unsafe: Optional[bool] = None,
                cwd: Optional[str] = None, env: Optional[dict] = None) -> dict:
    """Execute a Tcl script in headless VMD and capture output.

    Scripts that can spawn processes, open sockets, delete files or evaluate
    dynamic code are rejected unless ``allow_unsafe`` (or the environment
    variable ``VMD_AGENT_ALLOW_UNSAFE_TCL=1``) is set. ``cwd`` is the working
    directory VMD runs in (relative paths in the script resolve there) and
    ``env`` replaces the process environment when given.
    """
    try:
        security.check_tcl(script, allow_unsafe)
    except security.SecurityError as e:
        return {"ok": False, "error": str(e), "blocked": True}
    vmd = find_vmd(vmd_path)
    if not vmd:
        return {"ok": False, "error": "VMD not found; pass vmd_path or set $VMD_BIN."}
    with tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False) as fh:
        fh.write(script + "\nquit\n")
        path = fh.name
    try:
        out = _run_vmd_text(vmd, path, timeout, cwd=cwd, env=env)
        out["ok"] = out["returncode"] == 0
        return out
    finally:
        os.unlink(path)


# ------------------------------------------------------------- single image
@_structured_errors
def render_image(topology: str, trajectory: Optional[str] = None,
                 frame: int = -1,
                 detection: Optional[dict] = None,
                 recipe_path: Optional[str] = None,
                 out_png: str = "vmd_render.png",
                 width: int = 1600, height: int = 1200,
                 aasamples: int = 12, background: str = "white",
                 vmd_path: Optional[str] = None,
                 keep_work: bool = False) -> dict:
    """Render a single publication-quality image via VMD + Tachyon.

    Provide *either* a ``detection`` dict (reps generated automatically) or a
    ``recipe_path`` to a Tcl file containing representation commands only.
    """
    _validate_inputs(topology, trajectory, background)
    vmd = find_vmd(vmd_path)
    if not vmd:
        return {"ok": False, "error": "VMD not found; cannot render. "
                "Analysis still works; pass vmd_path or set $VMD_BIN."}
    tachyon = find_tachyon(vmd)
    out_png = os.path.abspath(out_png)
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)

    with _workdir("vmd_render_", keep_work) as work:
        scene = os.path.join(work, "scene.dat")
        lines = _image_lines(work, scene, topology, trajectory, frame,
                             detection, recipe_path, background)
        master = os.path.join(work, "master.tcl")
        with open(master, "w") as fh:
            fh.write("\n".join(lines) + "\n")

        vmd_out = _run_vmd_text(vmd, master)
        if not os.path.exists(scene):
            return {"ok": False, "error": "VMD did not produce a Tachyon scene.",
                    "vmd_stderr": vmd_out["stderr"],
                    "vmd_stdout": vmd_out["stdout"]}
        if not tachyon:
            kept = None
            if keep_work:
                kept = scene
            return {"ok": False, "scene_file": kept,
                    "error": "Tachyon binary not found; scene could not be "
                             "rasterised. Install Tachyon next to VMD or pass "
                             "keep_work=True to retain the scene file."}
        t = _run_tachyon(tachyon, scene, out_png, width, height, aasamples)
        res = {"ok": t["ok"], "image": out_png if t["ok"] else None,
               "tachyon_returncode": t.get("returncode"),
               "tachyon_stderr": "" if t["ok"] else t.get("stderr", "")}
        if keep_work:
            res["scene_file"] = scene
            res["work_dir"] = work
        return res


# -------------------------------------------------------------- multi-view
@_structured_errors
def render_views(topology: str, trajectory: Optional[str] = None,
                 frame: int = -1, detection: Optional[dict] = None,
                 recipe_path: Optional[str] = None,
                 views=("front", "side", "top"),
                 out_dir: Optional[str] = None,
                 width: int = 1400, height: int = 1050,
                 aasamples: int = 12, background: str = "white",
                 vmd_path: Optional[str] = None,
                 keep_work: bool = False, **recipe_kw) -> dict:
    """Render several orientations of the same scene in one VMD session.

    Multiple angles make automated visual interpretation far more reliable
    (a single view hides occluded components). Returns one PNG per view.
    """
    _validate_inputs(topology, trajectory, background)
    vmd = find_vmd(vmd_path)
    if not vmd:
        return {"ok": False, "error": "VMD not found; cannot render views."}
    tachyon = find_tachyon(vmd)
    out_dir = os.path.abspath(out_dir or tempfile.mkdtemp(prefix="vmd_views_"))
    os.makedirs(out_dir, exist_ok=True)
    ignored_views = [v for v in views if v not in _VIEW_ROT]
    views = [v for v in views if v in _VIEW_ROT] or ["front"]

    with _workdir("vmd_views_work_", keep_work) as work:
        scenes = {v: os.path.join(work, f"scene_{v}.dat") for v in views}
        lines = _views_lines(work, scenes, topology, trajectory, frame,
                             detection, recipe_path, background, **recipe_kw)
        master = os.path.join(work, "master.tcl")
        with open(master, "w") as fh:
            fh.write("\n".join(lines) + "\n")

        vmd_out = _run_vmd_text(vmd, master)
        images, errors = {}, {}
        if tachyon:
            jobs = [(scenes[v], os.path.join(out_dir, f"{v}.png"))
                    for v in views if os.path.exists(scenes[v])]
            res = _tachyon_many(tachyon, jobs, width, height, aasamples)
            for v in views:
                png = os.path.join(out_dir, f"{v}.png")
                if res.get(png, {}).get("ok"):
                    images[v] = png
                elif png in res:
                    errors[v] = res[png].get("stderr", "")
        out = {"ok": bool(images), "images": images, "out_dir": out_dir,
               "tachyon_found": bool(tachyon), "ignored_views": ignored_views,
               "vmd_stderr": vmd_out["stderr"] if not images else ""}
        if errors:
            out["tachyon_errors"] = errors
        if keep_work:
            out["scenes"] = {v: scenes[v] for v in views
                             if os.path.exists(scenes[v])}
            out["work_dir"] = work
        return out


# --------------------------------------------------- many frames, one session
@_structured_errors
def render_frames(topology: str, trajectory: Optional[str],
                  frames: Sequence[int],
                  detection: Optional[dict] = None,
                  recipe_path: Optional[str] = None,
                  out_dir: Optional[str] = None,
                  name_fmt: str = "frame_{k:05d}.png",
                  view: str = "front",
                  width: int = 1280, height: int = 720,
                  aasamples: int = 6, background: str = "white",
                  vmd_path: Optional[str] = None,
                  keep_work: bool = False, **recipe_kw) -> dict:
    """Render the given trajectory frames in a single VMD session.

    The camera is set once, from the first frame, and reused, so consecutive
    images are directly comparable (and a movie does not jitter). Returns
    ``images`` as a list of ``{"k", "frame", "path"}`` in the order requested.
    """
    _validate_inputs(topology, trajectory, background)
    vmd = find_vmd(vmd_path)
    if not vmd:
        return {"ok": False, "error": "VMD not found; cannot render frames."}
    tachyon = find_tachyon(vmd)
    if not tachyon:
        return {"ok": False, "error": "Tachyon not found; cannot rasterise "
                "frames."}
    frames = [int(f) for f in frames]
    if not frames:
        return {"ok": False, "error": "no frames requested."}
    out_dir = os.path.abspath(out_dir or tempfile.mkdtemp(prefix="vmd_frames_"))
    os.makedirs(out_dir, exist_ok=True)

    with _workdir("vmd_frames_work_", keep_work) as work:
        scenes = [os.path.join(work, f"scene_{k:05d}.dat")
                  for k in range(len(frames))]
        lines = _frames_lines(work, scenes, frames, topology, trajectory,
                              detection, recipe_path, background, view,
                              **recipe_kw)
        master = os.path.join(work, "master.tcl")
        with open(master, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        vmd_out = _run_vmd_text(vmd, master, timeout=3600)

        jobs, order = [], []
        for k, f in enumerate(frames):
            png = os.path.join(out_dir, name_fmt.format(k=k, frame=f))
            order.append((k, f, png))
            if os.path.exists(scenes[k]):
                jobs.append((scenes[k], png))
        res = _tachyon_many(tachyon, jobs, width, height, aasamples)
        images = [{"k": k, "frame": f, "path": png}
                  for k, f, png in order if res.get(png, {}).get("ok")]
        missing = [f for k, f, png in order
                   if not res.get(png, {}).get("ok")]
        out = {"ok": bool(images), "images": images, "out_dir": out_dir,
               "n_requested": len(frames), "n_rendered": len(images),
               "frames_failed": missing,
               "vmd_stderr": vmd_out["stderr"] if not images else ""}
        if keep_work:
            out["work_dir"] = work
        return out


# ------------------------------------------------------------------- movie
@_structured_errors
def render_movie(topology: str, trajectory: str,
                 detection: Optional[dict] = None,
                 recipe_path: Optional[str] = None,
                 out_mp4: str = "vmd_movie.mp4",
                 width: int = 1280, height: int = 720,
                 stride: int = 1, fps: int = 24,
                 aasamples: int = 6, background: str = "white",
                 vmd_path: Optional[str] = None,
                 keep_frames: bool = False, **recipe_kw) -> dict:
    """Render a trajectory to an MP4: one VMD session, one fixed camera."""
    _validate_inputs(topology, trajectory, background)
    ffmpeg = find_ffmpeg()
    if not find_vmd(vmd_path):
        return {"ok": False, "error": "VMD not found; cannot render movie."}
    n = count_frames(topology, trajectory)
    if n <= 0:
        return {"ok": False, "error": "Could not determine trajectory length."}
    stride = max(1, int(stride))
    idx = list(range(0, n, stride))
    frames_dir = tempfile.mkdtemp(prefix="vmd_movie_frames_")
    try:
        r = render_frames(topology, trajectory, idx, detection=detection,
                          recipe_path=recipe_path, out_dir=frames_dir,
                          width=width, height=height, aasamples=aasamples,
                          background=background, vmd_path=vmd_path,
                          **recipe_kw)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error", "No frames rendered."),
                    "vmd_stderr": r.get("vmd_stderr", "")}
        rendered = r["images"]
        if not ffmpeg:
            keep_frames = True
            return {"ok": False, "frames_dir": frames_dir,
                    "error": "ffmpeg absent; frames rendered but not encoded."}
        # frame_%05d numbering must be contiguous for ffmpeg's image2 demuxer
        if len(rendered) != len(idx):
            for j, item in enumerate(rendered):
                new = os.path.join(frames_dir, f"seq_{j:05d}.png")
                os.replace(item["path"], new)
                item["path"] = new
            pattern = "seq_%05d.png"
        else:
            pattern = "frame_%05d.png"
        out_mp4 = os.path.abspath(out_mp4)
        os.makedirs(os.path.dirname(out_mp4) or ".", exist_ok=True)
        proc = subprocess.run(
            [ffmpeg, "-y", "-framerate", str(fps),
             "-i", os.path.join(frames_dir, pattern),
             "-pix_fmt", "yuv420p", "-c:v", "libx264", out_mp4],
            capture_output=True, text=True)
        ok = os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 0
        out = {"ok": ok, "movie": out_mp4 if ok else None,
               "n_frames": len(rendered), "stride": stride,
               "source_frames": [it["frame"] for it in rendered],
               "ffmpeg_stderr": "" if ok else proc.stderr[-1500:]}
        if keep_frames:
            out["frames_dir"] = frames_dir
        return out
    finally:
        if not keep_frames:
            shutil.rmtree(frames_dir, ignore_errors=True)
