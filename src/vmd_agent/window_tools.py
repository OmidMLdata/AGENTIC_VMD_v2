"""The tools that drive a real VMD window (see :mod:`vmd_agent.vmdlink`).

Every picture and every number these return is VMD's own: the commands run inside the VMD you can see, so what the agent does is what you
are looking at. They are registered in the same :data:`vmd_agent.toolset.TOOLS` as every other tool, so the chat, the web page, the command
line and the MCP server all get them.
"""
from __future__ import annotations

import functools
import os
from typing import Callable, List, Optional

from vmd_agent import security, vmdlink
from vmd_agent.toolset import _p, tool
from vmd_agent.vmdkit import scene

_NO_WINDOW = "no VMD window is open: use window_open (or window_load, which opens one) first"


def _live(fn: Callable) -> Callable:
    """Turn a refused or failed window command into a plain result instead of an exception."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except vmdlink.LinkError as e:
            return {"ok": False, "error": str(e)}
    return wrapper


def _window(open_if_needed: bool = False, vmd_path: Optional[str] = None) -> vmdlink.Window:
    link = vmdlink.attach()
    if link is None:
        if not open_if_needed:
            raise vmdlink.LinkError(_NO_WINDOW)
        link = vmdlink.open_window(vmd_path)
    return vmdlink.Window(link)


def _top(win: vmdlink.Window, molecule: Optional[int]) -> int:
    if molecule is not None:
        return int(molecule)
    for m in win.molecules():
        if m["top"]:
            return int(m["id"])
    raise vmdlink.LinkError("no molecule is loaded in the VMD window: use window_load first")


def _brief(win: vmdlink.Window) -> list:
    return [{"id": m["id"], "name": m["name"], "top": m["top"], "shown": m["shown"], "atoms": m["natoms"], "frames": m["nframes"],
             "frame": m["frame"], "representations": m["numreps"]} for m in win.molecules()]


def _done(win: vmdlink.Window, summary: str, **extra) -> dict:
    return {"ok": True, "summary": summary, **extra, "molecules": _brief(win)}


@tool()
@_live
def window_open(vmd_path: Optional[str] = None, headless: bool = False) -> dict:
    """Open a VMD window (or reuse the one already open) that the other window_* tools control. Everything the window shows is VMD's own
    drawing, and the commands run inside that VMD, so the user sees what you do. Returns what the window holds."""
    link = vmdlink.open_window(_p(vmd_path), headless=headless)
    win = vmdlink.Window(link)
    st = win.state()
    where = "with no window (headless)" if link.headless else "with its window"
    return _done(win, f"VMD {st['vmd']} is running {where}; {len(st['molecules'])} molecule(s) loaded.", vmd_version=st["vmd"], headless=link.headless)


@tool()
@_live
def window_molecules(action: str = "list", molecule: Optional[int] = None, name: Optional[str] = None) -> dict:
    """The molecules in the VMD window. action: list (default), top (make `molecule` the top one: view, animation and the next
    representations act on it), show or hide (draw it or not), rename (to `name`), delete, clear (delete them all)."""
    win = _window()
    if action == "list":
        return _done(win, f"{len(win.molecules())} molecule(s) in the VMD window.")
    if action == "clear":
        r = win.clear()
        return _done(win, f"Deleted {r['deleted']} molecule(s).")
    if molecule is None:
        molecule = _top(win, None)
    if action == "top":
        win.top(molecule)
    elif action in ("show", "hide"):
        win.show(molecule, action == "show")
    elif action == "rename":
        if not name:
            raise security.InvalidInput("rename needs a name")
        win.rename(molecule, name)
    elif action == "delete":
        win.delete(molecule)
    else:
        raise security.InvalidInput("action must be one of: list, top, show, hide, rename, delete, clear")
    return _done(win, f"{action} done for molecule {molecule}.")


@tool()
@_live
def window_load(topology: Optional[str] = None, trajectory: Optional[str] = None, map_file: Optional[str] = None,
                molecule: Optional[int] = None) -> dict:
    """Load data into the VMD window (opening it if needed). topology (a PDB, PSF, GRO, mmCIF ...) loads a new molecule, with trajectory
    (DCD, XTC ...) read into it as its frames. trajectory with `molecule` and no topology adds frames to a molecule already loaded.
    map_file (a .dx, .mrc, .ccp4, .cube) loads a density map as a molecule (draw it with window_representation, style Isosurface)."""
    win = _window(open_if_needed=True)
    if map_file:
        full = _p(map_file)
        r = win.new_molecule(full, vmdlink.MAP_TYPES.get(os.path.splitext(full)[1].lower().lstrip("."), None) or vmdlink.file_type(full))
        return _done(win, f"Loaded the map {os.path.basename(full)} as molecule {r['id']}.", loaded=r)
    if topology:
        top = _p(topology)
        r = win.new_molecule(top)
        if trajectory:
            r = win.add_file(r["id"], _p(trajectory), drop_first=os.path.splitext(top)[1].lower() in vmdlink.HAS_COORDS)
        return _done(win, f"Loaded {os.path.basename(top)}: {r['natoms']} atoms, {r['nframes']} frame(s), as molecule {r['id']}.", loaded=r)
    if trajectory:
        mid = _top(win, molecule)
        first = next((m["file"] for m in win.molecules() if m["id"] == mid), "")
        r = win.add_file(mid, _p(trajectory), drop_first=os.path.splitext(first)[1].lower() in vmdlink.HAS_COORDS and next(
            m["nframes"] for m in win.molecules() if m["id"] == mid) == 1)
        return _done(win, f"Molecule {mid} now has {r['nframes']} frame(s).", loaded=r)
    raise security.InvalidInput("give a topology, a trajectory (with molecule) or a map_file")


@tool()
@_live
def window_representation(action: str = "list", molecule: Optional[int] = None, rep: Optional[int] = None, selection: Optional[str] = None,
                          style: Optional[str] = None, color: Optional[str] = None, material: Optional[str] = None,
                          params: Optional[List[float]] = None, shown: Optional[bool] = None) -> dict:
    """The representations (drawing methods) of a molecule in the VMD window, on the top molecule unless `molecule` is given. action: list
    (default), add (a new one from selection, style, color, material), modify (change representation number `rep`: any of selection, style,
    color, material, shown), delete (`rep`), or only (delete all of them and draw just this one: the usual "show it as ..."). selection is
    VMD's own language ('protein', 'resname LIG', 'within 5 of resname LIG', 'name CA'). style: NewCartoon, Licorice, CPK, VDW, Lines, Tube,
    QuickSurf, Surf, MSMS, Beads, Isosurface (params: isovalue 0 0 0 1 1) ... color: Name (by element), ResType (acidic, basic, polar, nonpolar), Structure (BY SECONDARY STRUCTURE: helix, sheet, coil), Chain,
    ResName, Element, Beta, ... or 'ColorID 3'. params are the style's numbers (for example Licorice: bond radius, resolution)."""
    win = _window()
    mid = _top(win, molecule)
    if action == "list":
        return {"ok": True, "molecule": mid, "representations": win.reps(mid), "summary": f"Molecule {mid} has {len(win.reps(mid))} representation(s)."}
    if action == "only":
        for i in range(len(win.reps(mid)) - 1, -1, -1):
            win.delete_rep(mid, i)
    if action in ("add", "only"):
        r = win.add_rep(mid, selection or "all", style or "NewCartoon", color or "Name", material or "Opaque", params)
        return {"ok": True, "molecule": mid, "representation": r["index"], "representations": win.reps(mid),
                "summary": f"Molecule {mid} now draws {selection or 'all'} as {style or 'NewCartoon'}, colored by {color or 'Name'}."}
    if rep is None:
        raise security.InvalidInput(f"{action} needs the representation number (rep); window_representation with action list shows them")
    if action == "delete":
        win.delete_rep(mid, rep)
        return {"ok": True, "molecule": mid, "representations": win.reps(mid), "summary": f"Deleted representation {rep} of molecule {mid}."}
    if action != "modify":
        raise security.InvalidInput("action must be one of: list, add, modify, delete, only")
    changed = []
    for key, value in (("selection", selection), ("style", style), ("color", color), ("material", material), ("show", shown)):
        if value is not None:
            win.modify_rep(mid, rep, key, value, params if key == "style" else None)
            changed.append(key)
    if not changed:
        raise security.InvalidInput("modify needs at least one of selection, style, color, material, shown")
    return {"ok": True, "molecule": mid, "representations": win.reps(mid), "summary": f"Changed {', '.join(changed)} of representation {rep} of molecule {mid}."}


@tool()
@_live
def window_display(setting: str, value: str) -> dict:
    """A display setting of the VMD window. setting and its values: projection (Perspective, Orthographic), depthcue (on, off), background
    (black, white, gray, ...), axes (Off, LowerLeft, LowerRight, UpperLeft, UpperRight, Origin), shadows (on, off), ambientocclusion (on, off),
    culling (on, off), antialias (on, off), and the numbers cuestart, cueend, cuedensity, aoambient, aodirect."""
    win = _window()
    win.display(setting, value)
    return _done(win, f"Display {setting} set to {value}.")


@tool()
@_live
def window_view(action: str = "reset", axis: Optional[str] = None, degrees: Optional[float] = None, factor: Optional[float] = None,
                x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None, selection: Optional[str] = None,
                molecule: Optional[int] = None, name: Optional[str] = None) -> dict:
    """Move the view in the VMD window. action: reset (fit everything), rotate (about `axis` x, y or z by `degrees`), scale (zoom by
    `factor`: 2 is twice as close), translate (by x, y, z), center (put the middle of `selection` in the centre of the view), save or restore
    (a view called `name`)."""
    win = _window()
    if action == "rotate":
        if axis is None or degrees is None:
            raise security.InvalidInput("rotate needs axis and degrees")
        win.view("rotate", axis, degrees)
    elif action == "scale":
        if factor is None:
            raise security.InvalidInput("scale needs a factor")
        win.view("scale", factor)
    elif action == "translate":
        win.view("translate", x or 0.0, y or 0.0, z or 0.0)
    elif action == "center":
        if not selection:
            raise security.InvalidInput("center needs a selection")
        win.view("center", selection, _top(win, molecule))
    elif action in ("save", "restore"):
        if not name:
            raise security.InvalidInput(f"{action} needs a name")
        win.view(action, name)
    elif action == "reset":
        win.view("reset")
    else:
        raise security.InvalidInput("action must be one of: reset, rotate, scale, translate, center, save, restore")
    return _done(win, f"View {action} done.")


@tool()
@_live
def window_animate(action: str = "goto", frame: Optional[int] = None, style: Optional[str] = None, speed: Optional[float] = None) -> dict:
    """Frames of the top molecule in the VMD window. action: goto (to `frame`, counting from 0), forward, reverse or pause (play in
    the window), style (`style`: once, loop or rock), speed (`speed` from 0 to 1)."""
    win = _window()
    if action == "goto":
        if frame is None:
            raise security.InvalidInput("goto needs a frame")
        r = win.animate("goto", frame)
    elif action == "style":
        r = win.animate("style", style)
    elif action == "speed":
        r = win.animate("speed", speed)
    elif action in ("forward", "reverse", "pause"):
        r = win.animate(action)
    else:
        raise security.InvalidInput("action must be one of: goto, forward, reverse, pause, style, speed")
    return _done(win, f"Molecule {r['molecule']} is at frame {r['frame']} of {r['nframes']}.", frame=r["frame"], n_frames=r["nframes"])


@tool()
@_live
def window_query(selection: str = "all", molecule: Optional[int] = None, measure: Optional[str] = None, atoms: Optional[List[int]] = None,
                 probe_radius: float = 1.4) -> dict:
    """Ask the VMD window about the frame it is showing. Without `measure`: what `selection` (VMD's selection language) holds: atoms,
    residues, chains, residue names with counts, centre, extent and (mass-weighted) radius of gyration. With measure: bond (two atom indices in `atoms`),
    angle (three), dihedral (four) or sasa (solvent-accessible area of `selection`, with `probe_radius`)."""
    win = _window()
    mid = _top(win, molecule)
    if measure is None:
        r = win.query(selection, mid)
        return {"ok": True, "molecule": mid, "selection": selection, "summary": f"'{selection}' matches {r['natoms']} atoms in molecule {mid}.", **r}
    if measure == "sasa":
        r = win.measure("sasa", mid, probe_radius, selection)
    else:
        r = win.measure(measure, mid, *(atoms or []))
    return {"ok": True, "molecule": mid, "summary": f"{measure}: {r['value']:.4g}" + (f" {r['unit']}" if r.get("unit") else ""), **r}


@tool()
@_live
def window_snapshot(out_png: str = "window.png", quality: str = "fast") -> dict:
    """A picture of what the VMD window shows right now, saved as a PNG. quality: fast (the window's own picture, the default) or tachyon
    (VMD's built-in ray tracer). The picture is VMD's own drawing."""
    win = _window()
    r = win.snapshot(_p(out_png), quality)
    return {"ok": True, "image": r["path"], "width": r["width"], "height": r["height"], "renderer": r["renderer"],
            "summary": f"Saved {os.path.basename(r['path'])} ({r['width']} x {r['height']}), drawn by VMD ({r['renderer']})."}


def apply_scene(win: vmdlink.Window, scene_spec: dict, topology: Optional[str] = None, trajectory: Optional[str] = None) -> dict:
    """Set up a scene (the description render_image takes) in the VMD window: load, representations, isosurfaces, display and view."""
    spec = scene.validate(scene_spec)
    if topology:
        top = _p(topology)
        r = win.new_molecule(top)
        if trajectory:
            win.add_file(r["id"], _p(trajectory), drop_first=os.path.splitext(top)[1].lower() in vmdlink.HAS_COORDS)
        mid = int(r["id"])
    else:
        mid = _top(win, None)
    for i in range(len(win.reps(mid)) - 1, -1, -1):
        win.delete_rep(mid, i)
    for rep in spec["reps"]:
        win.add_rep(mid, rep["selection"], rep["style"], rep["color"], rep["material"], rep["params"])
    for iso in spec["isosurfaces"]:
        full = _p(iso["file"])
        m = win.new_molecule(full, vmdlink.MAP_TYPES.get(os.path.splitext(full)[1].lower().lstrip("."), None) or vmdlink.file_type(full))
        for i in range(len(win.reps(m["id"])) - 1, -1, -1):
            win.delete_rep(m["id"], i)
        win.add_rep(m["id"], "all", "Isosurface", iso["color"], iso["material"], [iso["isovalue"], 0, 0, scene.ISO_STYLES[iso["style"]], 1, 1])
    win.top(mid)
    for key, value in (("background", spec["background"]), ("projection", spec["projection"]), ("axes", "LowerLeft" if spec["axes"] else "Off"),
                       ("depthcue", spec["depthcue"]), ("shadows", spec["shadows"]), ("ambientocclusion", spec["ambient_occlusion"])):
        win.display(key, value)
    if spec["frame"]:
        win.animate("goto", spec["frame"])
    win.view("reset")
    for axis, deg in spec["rotate"]:
        win.view("rotate", axis, deg)
    if spec["zoom"] != 1.0:
        win.view("scale", spec["zoom"])
    return _done(win, f"Scene set up: {len(spec['reps'])} representation(s) and {len(spec['isosurfaces'])} isosurface(s) on molecule {mid}.", molecule=mid)


@tool()
@_live
def window_scene(scene_spec: dict, topology: Optional[str] = None, trajectory: Optional[str] = None) -> dict:
    """Set up a whole scene in the VMD window at once, from the same description as render_image: {reps: [{selection, style, color, material,
    params}], isosurfaces: [{file, isovalue, color, style: solid|wireframe|points}], background, frame, rotate: [[axis, degrees]], zoom,
    projection, axes, depthcue, shadows, ambient_occlusion}. With topology (and trajectory) it loads them first; without, it redraws the
    top molecule. The user can then keep working in the window; use window_save to keep the scene."""
    scene.validate(scene_spec)
    return apply_scene(_window(open_if_needed=True), scene_spec, topology, trajectory)


@tool()
@_live
def window_visualize(topology: Optional[str] = None, trajectory: Optional[str] = None, focus: str = "overview", representation: Optional[str] = None,
                     color_method: Optional[str] = None, show_water: bool = False, background: str = "white") -> dict:
    """Draw a system in the VMD window the way generate_visualization_recipe would: it detects what the system holds (protein chains, ligands, ions,
    water, lipids, nucleic acids) and draws each part in a fitting way, with the recipe's own scene settings. Same choices as visualize_and_interpret, but
    in VMD itself. With topology (and trajectory) it loads them first, or reuses the molecule if it is already in the window; without, it redraws the top
    molecule. focus: overview, fold, interactions, surface, pocket, performance. representation forces one style (for example QuickSurf). Returns what
    was drawn, why, and a legend of what each colour and shape means."""
    from vmd_agent import window_present as W
    win = _window(open_if_needed=True)
    if topology:
        held = W._molecule_holding(win, topology)
        mid = int(held["id"]) if held else int(W.load(win, topology, trajectory)["id"])
        top_path, trj_path = topology, trajectory
    else:
        mid = _top(win, None)
        files = next(m["files"] for m in win.molecules() if m["id"] == mid)
        top_path, trj_path = files[0], (files[1] if len(files) > 1 else None)
    out = W.visualize(win, mid, top_path, trj_path, focus=focus, representation=representation, color_method=color_method, show_water=show_water, background=background)
    win.top(mid)
    return _done(win, f"Drew molecule {mid} in the VMD window the way the recipe draws it: {len(out['representations'])} representation(s).", **out)


@tool()
@_live
def window_movie(out_mp4: str = "window_movie.mp4", action: str = "trajectory", stride: int = 1, first: int = 0, last: int = -1, fps: int = 12,
                 frames: int = 36, degrees: float = 360.0, axis: str = "y", quality: str = "fast") -> dict:
    """A movie of the VMD window, drawn by VMD and encoded with ffmpeg. action: trajectory (play the top molecule's frames from `first` to `last`,
    every `stride`th) or spin (a turntable: the view turns `degrees` about `axis` over `frames` frames). quality: fast (the window's own picture) or
    tachyon (VMD's built-in ray tracer, slower). The view is put back afterwards."""
    import tempfile
    from vmd_agent import progress
    from vmd_agent.environment import find_ffmpeg
    from vmd_agent.evidence import media
    if action not in ("trajectory", "spin"):
        raise security.InvalidInput("action must be one of: trajectory, spin")
    if quality not in ("fast", "tachyon"):
        raise security.InvalidInput("quality must be fast or tachyon")
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise vmdlink.LinkError("ffmpeg was not found, so a movie cannot be encoded")
    win = _window()
    mid = _top(win, None)
    out = _p(out_mp4)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if action == "trajectory":
        n = next(m["nframes"] for m in win.molecules() if m["id"] == mid)
        last = n - 1 if last < 0 or last >= n else last
        indices = list(range(max(0, first), last + 1, max(1, stride)))
    else:
        indices = list(range(int(frames)))
    if not 1 <= len(indices) <= 720:
        raise security.InvalidInput("a movie has from 1 to 720 frames")
    start_frame = next(m["frame"] for m in win.molecules() if m["id"] == mid)
    win.view("save", "_vmdagent_movie")
    from PIL import Image
    with tempfile.TemporaryDirectory(dir=os.path.dirname(out)) as tmp:
        try:
            for k, idx in enumerate(indices):
                progress.report(f"frame {k + 1} of {len(indices)}", (k + 1) / len(indices))
                if action == "trajectory":
                    win.animate("goto", idx)
                elif k:
                    win.view("rotate", axis, float(degrees) / len(indices))
                png = os.path.join(tmp, f"f{k:05d}.png")
                win.snapshot(png, quality)
                with Image.open(png) as im:                                    # yuv420p needs even sides
                    w, h = im.size
                    if w % 2 or h % 2:
                        im.crop((0, 0, w - w % 2, h - h % 2)).save(png)
        finally:
            win.view("restore", "_vmdagent_movie")
            if action == "trajectory":
                win.animate("goto", start_frame)
        import subprocess
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(int(fps)), "-i", os.path.join(tmp, "f%05d.png"), "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if done.returncode != 0 or not os.path.isfile(out):
            raise vmdlink.LinkError("ffmpeg could not encode the movie: " + done.stderr[-300:])
    check = media.validate_video(out, expect_fps=float(fps), expect_n_frames=len(indices))
    return {"ok": True, "movie": out, "n_frames": len(indices), "fps": fps, "validation": check, "summary": f"A {len(indices)}-frame movie of the VMD window ({action}) is saved as {os.path.basename(out)}.",
            "next_step": "Call interpret_video on `movie` to sample and verify stills before describing it."}


@tool()
@_live
def window_save(out_vmd: str = "session.vmd") -> dict:
    """Save the state of the VMD window (its molecules, representations and view) as a .vmd file that VMD opens again with `vmd -e FILE`."""
    win = _window()
    full = _p(out_vmd)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    win.save_state(full)
    return {"ok": True, "path": full, "summary": f"Saved the window's state to {os.path.basename(full)}; open it later with vmd -e."}
