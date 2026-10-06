"""Describe a VMD scene as data, render it, and export it as a script a VMD user can open.

One *scene spec* (a plain dict) drives both ``render_scene`` and ``export_session``, and both use
the very same generated Tcl, so the exported script reproduces what was rendered. A spec holds
representations, optional isosurfaces of density maps, camera, lighting and background.

Spec keys (all optional except ``reps`` or ``isosurfaces``):
  reps        [{selection, style, color, material, params}]   VMD representations
  isosurfaces [{file, isovalue, color, style, material}]      density maps (dx, mrc, ccp4, cube, situs)
  background  "white" | "black"        frame 0-based       rotate [["x", 30], ["y", -30]]
  zoom        float                    projection "Orthographic" | "Perspective"
  axes bool   depthcue bool            shadows bool   ambient_occlusion bool
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

from vmd_agent import progress, security
from vmd_agent.environment import find_tachyon, find_vmd
from vmd_agent.visual import render as R
from vmd_agent.vmdkit import script as S

STYLES = ("Lines", "Bonds", "DynamicBonds", "HBonds", "Points", "VDW", "CPK", "Licorice", "Beads", "Tube", "Trace",
          "Ribbons", "NewRibbons", "Cartoon", "NewCartoon", "PaperChain", "Twister", "QuickSurf", "MSMS", "Surf",
          "Dotted", "Solvent")
COLORS = ("Name", "Type", "Element", "ResName", "ResType", "ResID", "Chain", "SegName", "Structure", "Molecule",
          "Beta", "Occupancy", "Mass", "Charge", "Index", "Backbone", "Fragment", "Position")
MATERIALS = ("Opaque", "Transparent", "BrushedMetal", "Diffuse", "Ghost", "Glass1", "Glass2", "Glass3", "Glossy",
             "HardPlastic", "MetallicPastel", "Steel", "Translucent", "Edgy", "EdgyShiny", "AOShiny", "AOChalky",
             "AOEdgy", "BlownGlass", "GlassBubble", "RTChrome")
ISO_STYLES = {"solid": 0, "wireframe": 1, "points": 2}
_ROT = {"x", "y", "z"}


def _color(c: str) -> str:
    if c in COLORS:
        return c
    if isinstance(c, str) and c.startswith("ColorID ") and c[8:].isdigit() and int(c[8:]) < 1057:
        return c
    raise security.InvalidInput(f"color must be one of {', '.join(COLORS)} or 'ColorID <n>'")


def validate(spec: dict) -> dict:
    """Check a scene spec; returns a normalised copy or raises InvalidInput."""
    if not isinstance(spec, dict):
        raise security.InvalidInput("scene spec must be an object")
    reps = spec.get("reps") or []
    isos = spec.get("isosurfaces") or []
    if not reps and not isos:
        raise security.InvalidInput("a scene needs at least one rep or isosurface")
    out = {"reps": [], "isosurfaces": []}
    for r in reps:
        out["reps"].append({
            "selection": S.sel(r.get("selection", "all")), "style": S.choice(r.get("style", "NewCartoon"), STYLES, "style"),
            "color": _color(r.get("color", "Name")), "material": S.choice(r.get("material", "Opaque"), MATERIALS, "material"),
            "params": [S.num(x, "param") for x in (r.get("params") or [])][:8]})
    for i in isos:
        out["isosurfaces"].append({
            "file": os.path.abspath(str(i["file"])), "isovalue": S.num(i["isovalue"], "isovalue"),
            "color": _color(i.get("color", "ColorID 3")), "style": S.choice(i.get("style", "solid"), tuple(ISO_STYLES), "iso style"),
            "material": S.choice(i.get("material", "Transparent"), MATERIALS, "material")})
    bg = spec.get("background", "white")
    out["background"] = S.choice(bg, ("white", "black"), "background")
    out["frame"] = S.whole(spec.get("frame", 0), "frame")
    out["rotate"] = []
    for ax, deg in spec.get("rotate") or []:
        out["rotate"].append([S.choice(ax, tuple(_ROT), "rotation axis"), S.num(deg, "rotation")])
    out["zoom"] = S.num(spec.get("zoom", 1.0), "zoom")
    if out["zoom"] <= 0:
        raise security.InvalidInput("zoom must be positive")
    out["projection"] = S.choice(spec.get("projection", "Orthographic"), ("Orthographic", "Perspective"), "projection")
    for k in ("axes", "depthcue", "shadows", "ambient_occlusion"):
        out[k] = bool(spec.get(k, False))
    return out


def scene_lines(spec: dict, topology: Optional[str], trajectory: Optional[str], path_expr=None) -> List[str]:
    """Tcl that loads the data and builds the scene (no rendering). ``path_expr(path)`` may return a Tcl word
    for a path (the exporter uses it to make paths relative); the default is the absolute path in braces."""
    sp = validate(spec)
    lines: List[str] = []
    if topology:
        lines += R._load_lines(topology, trajectory) if path_expr is None else _rel_load(topology, trajectory, path_expr)
        lines += ["mol delrep 0 top", "set vmdagent_mol [molinfo top get id]"]
    for r in sp["reps"]:
        params = " ".join(repr(p) if p != int(p) else str(int(p)) for p in r["params"])
        lines += [f"mol selection {{{r['selection']}}}", f"mol representation {r['style']} {params}".rstrip(),
                  f"mol color {r['color']}", f"mol material {r['material']}", "mol addrep top"]
    for iso in sp["isosurfaces"]:
        p = path_expr(iso["file"]) if path_expr else f"{{{security.tcl_path(iso['file'])}}}"
        ext = os.path.splitext(iso["file"])[1].lstrip(".").lower()
        vtype = {"dx": "dx", "mrc": "ccp4", "map": "ccp4", "ccp4": "ccp4", "cube": "cube", "cub": "cube", "situs": "situs",
                 "sit": "situs"}.get(ext)
        if not vtype:
            raise security.InvalidInput(f"unsupported map format .{ext}")
        lines += [f"mol new {p} type {vtype} waitfor all", "mol delrep 0 top",
                  f"mol representation Isosurface {iso['isovalue']} 0 0 {ISO_STYLES[iso['style']]} 1 1",
                  f"mol color {iso['color']}", f"mol material {iso['material']}", "mol addrep top"]
    if topology and sp["isosurfaces"]:
        lines += ["mol top $vmdagent_mol"]              # frame and view commands act on the structure, not a map
    lines += [f"color Display Background {sp['background']}", f"display projection {sp['projection']}",
              f"axes location {'LowerLeft' if sp['axes'] else 'Off'}",
              f"display depthcue {'on' if sp['depthcue'] else 'off'}",
              f"display shadows {'on' if sp['shadows'] else 'off'}",
              f"display ambientocclusion {'on' if sp['ambient_occlusion'] else 'off'}"]
    if sp["ambient_occlusion"]:
        lines += ["display ambientocclusion on", "display aoambient 0.8", "display aodirect 0.3"]
    if topology:
        lines += [f"animate goto {sp['frame']}"]
    lines += ["display resetview"]
    for ax, deg in sp["rotate"]:
        lines += [f"rotate {ax} by {deg:g}"]
    if sp["zoom"] != 1.0:
        lines += [f"scale by {sp['zoom']:g}"]
    return lines


def _rel_load(topology: str, trajectory: Optional[str], path_expr) -> List[str]:
    topo = R._mtype(topology)
    out = [f"mol new {path_expr(topology)} type {{{topo}}} waitfor all"]
    if trajectory:
        out.append(f"mol addfile {path_expr(trajectory)} type {{{R._mtype(trajectory)}}} waitfor all")
        if os.path.splitext(topology)[1].lower() in R._HAS_COORDS:
            out.append("animate delete beg 0 end 0 top")
    return out


def render_scene(spec: dict, topology: Optional[str], trajectory: Optional[str], out_png: str,
                 width: int = 1600, height: int = 1200, vmd_path: Optional[str] = None) -> dict:
    """Render the scene with VMD + Tachyon to a PNG (needs a real VMD)."""
    S.keep_inputs([out_png], [topology, trajectory] + [i["file"] for i in (spec.get("isosurfaces") or [])])
    vmd, tach = find_vmd(vmd_path), None
    if not vmd:
        return S.no_vmd()
    tach = find_tachyon(vmd)
    if not tach:
        return {"ok": False, "error": "Tachyon (VMD's ray tracer) was not found next to VMD."}
    lines = scene_lines(spec, topology, trajectory)
    with tempfile.TemporaryDirectory(prefix="vmd_agent_scene_") as tmp:
        dat = os.path.join(tmp, "scene.dat")
        tcl = os.path.join(tmp, "scene.tcl")
        with open(tcl, "w") as fh:
            fh.write("\n".join(lines + [f"render Tachyon {{{dat}}}", "quit"]) + "\n")
        res = R._run_vmd_text(vmd, tcl, 900, cwd=tmp)
        if not os.path.exists(dat):
            return {"ok": False, "error": "VMD wrote no scene: " + (res.get("stderr") or res.get("stdout", ""))[-300:]}
        t = R._run_tachyon(tach, dat, os.path.abspath(out_png), int(width), int(height), 12)
    ok = t.get("ok", False)
    return {"ok": ok, "image": out_png if ok else None, "engine": "VMD + Tachyon", "width": width, "height": height,
            **({} if ok else {"error": t.get("stderr", "Tachyon failed")})}


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_session(spec: dict, topology: Optional[str], trajectory: Optional[str], out_dir: str,
                   copy_inputs: bool = True, vmd_path: Optional[str] = None) -> dict:
    """Write a folder a VMD user can open: ``session.tcl`` (open it in VMD: ``vmd -e session.tcl``),
    ``render.tcl`` (headless Tachyon render), the input files (copied, so paths are relative), a
    ``manifest.json`` with checksums and the VMD version, and ``REPRODUCE.md``. The exported scene is then
    loaded in a real VMD to prove it opens (atoms, representations)."""
    sp = validate(spec)
    os.makedirs(out_dir, exist_ok=True)
    data_dir = os.path.join(out_dir, "data")
    inputs = [p for p in [topology, trajectory] + [i["file"] for i in sp["isosurfaces"]] if p]
    rel: Dict[str, str] = {}
    for p in inputs:
        if copy_inputs:
            os.makedirs(data_dir, exist_ok=True)
            dest = os.path.join(data_dir, os.path.basename(p))
            if os.path.abspath(p) != os.path.abspath(dest):
                shutil.copyfile(p, dest)
            rel[os.path.abspath(p)] = "data/" + os.path.basename(p)

    def path_expr(p: str) -> str:
        r = rel.get(os.path.abspath(p))
        return f"[file join $::vmdagent_here {r}]" if r else f"{{{security.tcl_path(p)}}}"

    body = scene_lines(sp, topology, trajectory, path_expr)
    head = ["# Exported by vmd-agent. Open in VMD:  vmd -e session.tcl",
            "set ::vmdagent_here [file dirname [file normalize [info script]]]"]
    with open(os.path.join(out_dir, "session.tcl"), "w") as fh:
        fh.write("\n".join(head + body) + "\n")
    with open(os.path.join(out_dir, "render.tcl"), "w") as fh:
        fh.write("\n".join(["# Headless render:  vmd -dispdev text -e render.tcl   (then run Tachyon on scene.dat)",
                            "set ::vmdagent_here [file dirname [file normalize [info script]]]"] + body +
                           ["render Tachyon [file join $::vmdagent_here scene.dat]", "quit"]) + "\n")
    vmd = find_vmd(vmd_path)
    check = {"checked": False}
    version = None
    if vmd:
        from vmd_agent.environment import _vmd_version
        version = _vmd_version(vmd)
        probe = [f"source {{{security.tcl_path(os.path.join(out_dir, 'session.tcl'))}}}",
                 "foreach m [molinfo list] { emit CHK $m [molinfo $m get numatoms] [molinfo $m get numreps] "
                 "[molinfo $m get numframes] }"]
        r = S.run(probe, vmd_path)
        if r["ok"]:
            mols = [{"atoms": int(a), "representations": int(n), "frames": int(f)} for _m, a, n, f in r["rows"]["CHK"]]
            check = {"checked": True, "opens_in_vmd": True, "molecules": mols}
        else:
            check = {"checked": True, "opens_in_vmd": False, "error": r.get("error")}
    from vmd_agent import __version__
    manifest = {"vmd_agent": __version__, "vmd_version": version, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "spec": sp, "inputs": {rel.get(os.path.abspath(p), os.path.abspath(p)): _sha(p) for p in inputs},
                "round_trip_check": check}
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    with open(os.path.join(out_dir, "REPRODUCE.md"), "w") as fh:
        fh.write("# Reproduce this scene\n\n"
                 f"Made with vmd-agent {__version__} and VMD {version or '(unknown)'}.\n\n"
                 "1. Open in the VMD GUI: `vmd -e session.tcl` (run it from this folder or anywhere: paths are relative to the file).\n"
                 "2. Or render without a window: `vmd -dispdev text -e render.tcl`, then run Tachyon on `scene.dat` "
                 "(`tachyon_<ARCH> scene.dat -aasamples 12 -format PNG -res 1600 1200 -o scene.png`).\n"
                 "3. `manifest.json` records the scene spec and a SHA-256 of every input file; compare them to be sure you "
                 "have the same data.\n")
    return {"ok": True, "engine": "vmd-agent scene export", "out_dir": out_dir,
            "files": sorted(os.listdir(out_dir)), "round_trip_check": check, "vmd_version": version,
            "open_with": f"vmd -e {os.path.join(out_dir, 'session.tcl')}"}


def render_turntable(spec: dict, topology: Optional[str], trajectory: Optional[str], out_mp4: str,
                     frames: int = 72, degrees: float = 360.0, axis: str = "y", fps: int = 24,
                     width: int = 960, height: int = 720, vmd_path: Optional[str] = None) -> dict:
    """A rotating-view movie of a scene (one VMD session, the scene fixed, the camera turning about `axis`),
    encoded with ffmpeg."""
    from vmd_agent.environment import find_ffmpeg
    S.choice(axis, ("x", "y", "z"), "axis")
    S.keep_inputs([out_mp4], [topology, trajectory])
    n = S.whole(frames, "frames")
    if not 2 <= n <= 720:
        raise security.InvalidInput("frames must be between 2 and 720")
    step = S.num(degrees, "degrees") / n
    vmd = find_vmd(vmd_path)
    if not vmd:
        return S.no_vmd()
    tach, ffmpeg = find_tachyon(vmd), find_ffmpeg()
    if not tach or not ffmpeg:
        return {"ok": False, "error": "need Tachyon (next to VMD) and ffmpeg (bundled; `vmd-agent doctor` shows both)"}
    lines = scene_lines(spec, topology, trajectory)
    with tempfile.TemporaryDirectory(prefix="vmd_agent_turn_") as tmp:
        scenes = [os.path.join(tmp, f"s{i:04d}.dat") for i in range(n)]
        for sc in scenes:
            lines += [f"render Tachyon {{{sc}}}", f"rotate {axis} by {step:g}"]
        tcl = os.path.join(tmp, "turn.tcl")
        with open(tcl, "w") as fh:
            fh.write("\n".join(lines + ["quit"]) + "\n")
        progress.report(f"writing {n} scene files with VMD")
        R._run_vmd_text(vmd, tcl, 1800, cwd=tmp)
        jobs = [(sc, os.path.join(tmp, f"f{i:05d}.png")) for i, sc in enumerate(scenes) if os.path.exists(sc)]
        if len(jobs) != n:
            return {"ok": False, "error": f"VMD wrote {len(jobs)} of {n} scenes"}
        progress.report(f"ray tracing {n} frames with Tachyon (the slow step)")
        done = R._tachyon_many(tach, jobs, int(width), int(height), 8)
        if not all(r.get("ok") for r in done.values()):
            return {"ok": False, "error": "Tachyon failed on some frames"}
        progress.report("encoding the video")
        proc = subprocess.run([ffmpeg, "-y", "-framerate", str(int(fps)), "-i", os.path.join(tmp, "f%05d.png"),
                               "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", os.path.abspath(out_mp4)],
                              capture_output=True, text=True, timeout=600)
    ok = proc.returncode == 0 and os.path.exists(out_mp4)
    return {"ok": ok, "movie": out_mp4 if ok else None, "n_frames": n, "degrees_total": degrees, "axis": axis,
            "engine": "VMD + Tachyon + ffmpeg", **({} if ok else {"error": proc.stderr[-300:]})}
