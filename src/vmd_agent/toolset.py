"""The toolkit's tools as plain Python functions, independent of any AI client.

Every tool is a function with a docstring and typed parameters, registered in
:data:`TOOLS`. Two front ends use the same registry:

* :mod:`vmd_agent.server` registers each function with the MCP SDK, so any MCP
  client can call them;
* :mod:`vmd_agent.chat` gives them to a language model (a local open-source one
  or a hosted one) through the OpenAI-style tool-calling API.

Nothing in this module imports the MCP SDK, so it works on Python 3.9 and needs
no client.

Security
--------
Set ``VMD_AGENT_ALLOWED_ROOTS`` to confine every path the tools read or write
(the Docker image sets it to ``/data``). ``run_tcl`` is disabled unless
``VMD_AGENT_ENABLE_TCL=1``. See :mod:`vmd_agent.security`.
"""
from __future__ import annotations

import functools
import inspect
import os
import typing
from typing import Callable, Dict, List, Optional

from vmd_agent.inputs import inspection
from vmd_agent.structure import detect as detect_mod
from vmd_agent.visual import recipes
from vmd_agent.dynamics import analysis
from vmd_agent.visual import render as render_mod
from vmd_agent.evidence import media, report as report_mod
from vmd_agent import auto as auto_mod
from vmd_agent import security
from vmd_agent.window_present import shows_in_window

#: name -> callable, in registration order
TOOLS: Dict[str, Callable] = {}

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}


def guard(fn: Callable) -> Callable:
    """Turn policy violations into structured results instead of exceptions."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except security.SecurityError as e:
            return {"ok": False, "blocked": True, "error": str(e)}
        except security.InvalidInput as e:
            return {"ok": False, "blocked": False, "error": str(e)}
    return wrapper


def tool():
    """Register a function as a tool (with :func:`guard` applied)."""
    def deco(fn):
        wrapped = guard(fn)
        TOOLS[fn.__name__] = wrapped
        return wrapped
    return deco


def _p(path):
    return security.check_path(path)


# ---- session helpers ------------------------------------------------------
def _store(session_dir: Optional[str], key: str, value):
    if not session_dir:
        return
    s = report_mod.Session(_p(session_dir))
    s.update(**{key: value})


# ---- environment / inspection --------------------------------------------
@tool()
def probe_environment(vmd_path: Optional[str] = None, plugins: bool = False, verbose: bool = False) -> dict:
    """Report what this machine can do: VMD/Tachyon/ffmpeg, analysis libraries and which renderers (vmd, matplotlib) are
    available. Call this first to choose a renderer; the matplotlib backend works without VMD. plugins=true also lists the
    plugins of the installed VMD by status: wrapped by this toolkit (with the tool that does it), library, window-only,
    needing another program (NAMD, APBS, ...), or not wrapped yet (use it when asked what VMD can do); verbose=true adds
    every plugin's version and the file formats."""
    r = auto_mod.probe_environment(_p(vmd_path))
    if plugins:
        from vmd_agent.vmdkit import capabilities
        r["vmd_plugins"] = capabilities.vmd_capabilities(_p(vmd_path), verbose=verbose)
    return r


@tool()
def inspect_files(paths: List[str]) -> dict:
    """START HERE for any file in the data folder: says what each local file is (structure, trajectory, map, image)
    and which companion file is missing (e.g. a PSF for a DCD). Reads local files only; downloads nothing."""
    return inspection.inspect_files([_p(x) for x in paths])


@tool()
def detect_system(topology: str, trajectory: Optional[str] = None,
                  session_dir: Optional[str] = None) -> dict:
    """Load a LOCAL structure (and optional trajectory) and classify its components and overall type: protein chains,
    ligands, water, ions, lipids, nucleic acids, and the type of system."""
    r = detect_mod.detect_system(_p(topology), _p(trajectory))
    r["summary"] = _detect_summary(r)
    _store(session_dir, "detection", r)
    return r


def _detect_summary(r: dict) -> str:
    """One plain sentence on what is in the system, for a reader (or a model) who would otherwise pick the wrong field."""
    c = r.get("components", {})
    parts = [f"{r.get('system_type', 'system')}: {r.get('n_atoms')} atoms, {r.get('n_frames')} frame(s)"]
    prot = c.get("protein", {})
    if prot.get("present"):
        chains = prot.get("chains", [])
        parts.append(f"protein: {prot.get('n_residues')} residues in {len(chains)} chain{'s' if len(chains) != 1 else ''} ({', '.join(chains)})")
    other = c.get("ligands_or_other", {})
    if other.get("present"):
        parts.append(f"ligand or other: {', '.join(other.get('resnames', []))} ({other.get('n_atoms')} atoms)")
    for key, label in (("water", "water"), ("ions", "ions"), ("lipid", "lipid"), ("nucleic", "nucleic acid")):
        if c.get(key, {}).get("present"):
            parts.append(f"{label}: present")
    absent = [label for key, label in (("water", "water"), ("ions", "ions"), ("lipid", "lipid"), ("nucleic", "nucleic acid")) if not c.get(key, {}).get("present")]
    if absent:
        parts.append("no " + ", no ".join(absent))
    return "; ".join(parts) + "."


# ---- visualization --------------------------------------------------------
@tool()
def generate_visualization_recipe(topology: str,
                                  trajectory: Optional[str] = None,
                                  style: str = "publication",
                                  background: str = "white",
                                  show_water: bool = False,
                                  out_path: Optional[str] = None,
                                  session_dir: Optional[str] = None) -> dict:
    """Detect the system and emit a tailored VMD/Tcl visualization recipe."""
    det = detect_mod.detect_system(_p(topology), _p(trajectory))
    rec = recipes.generate_visualization_recipe(
        det, style=style, background=background, show_water=show_water,
        out_path=_p(out_path))
    _store(session_dir, "detection", det)
    _store(session_dir, "recipe", {k: v for k, v in rec.items() if k != "tcl"})
    return rec


@tool()
def structure_stats(topology: str, trajectory: Optional[str] = None,
                    frame: int = 0) -> dict:
    """Count bonds, links and interactions for annotating a figure: total bonds
    and bonds by element pair, disulfide bridges, hydrogen bonds (angle-based
    when hydrogens exist), salt bridges, chains, elements and DSSP
    secondary-structure content. Always reports how bonds and H-bonds were
    obtained (topology records vs inferred; angle vs distance only)."""
    from vmd_agent.structure import stats as stats_mod
    st = stats_mod.structure_stats(_p(topology), _p(trajectory), frame=frame)
    st["caption_lines"] = stats_mod.stats_caption(st)
    st["summary"] = (f"{st.get('n_atoms')} atoms; {st.get('n_protein_residues', 0)} protein residues in {st.get('n_protein_chains', 0)} protein chain(s); "
                     f"{st.get('n_disulfide_bridges', 0)} disulfide bridge(s); {st.get('n_hydrogen_bonds', 0)} hydrogen bond(s) ({st.get('hbond_method')}); "
                     f"{st.get('n_salt_bridges', 0)} salt bridge(s). n_residues ({st.get('n_residues')}) counts every residue, ligand and water included.")
    return st


@tool()
def color_key(color_method: str, topology: Optional[str] = None,
              is_alphafold: bool = False) -> dict:
    """Explain what each colour in a render means, for one VMD colouring method
    ('Structure', 'Chain', 'Name'/'Element', 'ResType', 'Beta', 'ColorID').
    Returns labelled swatches with VMD colour names and hex values. Note VMD
    draws carbon CYAN, not grey or green."""
    from vmd_agent.visual import colorkey as ck_mod
    det = None
    if topology:
        det = detect_mod.detect_system(_p(topology))
    return ck_mod.color_key(color_method, det, is_alphafold=is_alphafold)


@tool()
def annotate_image(image_path: str, topology: Optional[str] = None,
                   trajectory: Optional[str] = None,
                   title: str = "", out_path: Optional[str] = None,
                   panel_side: str = "right") -> dict:
    """Draw the colour key and structure statistics onto an existing rendered
    image, making the figure self-describing. Returns the annotated image path
    (view it with view_image)."""
    from vmd_agent.visual import annotate as ann_mod
    from vmd_agent.structure import stats as stats_mod
    from vmd_agent import auto as a_mod
    ckeys, slines, llines = [], [], []
    if topology:
        det = detect_mod.detect_system(_p(topology), _p(trajectory))
        ckeys = a_mod.build_color_keys(det)
        llines = a_mod.visual_legend(det)
        slines = stats_mod.stats_caption(
            stats_mod.structure_stats(_p(topology), _p(trajectory)))
    return ann_mod.annotate_image(_p(image_path), color_keys=ckeys,
                                  stats_lines=slines, legend_lines=llines,
                                  title=title, out_path=_p(out_path),
                                  panel_side=panel_side)


@tool()
def list_representations(category: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Catalogue of VMD graphical representations, colour methods and materials. Consult this to choose or explain a
    drawing style. Categories: 'backbone' (NewCartoon, Tube, Ribbons), 'atomic' (CPK, Licorice, Lines, VDW),
    'surface' (QuickSurf, Surf, MSMS), 'special' (DynamicBonds, HBonds). Give name (for example 'QuickSurf') instead
    for the full detail on one representation: what it draws, what it is best for, its VMD command with default
    parameters, and its limitations."""
    from vmd_agent.visual import representations as reps_mod
    return reps_mod.describe_representation(name) if name else reps_mod.list_representations(category)


@tool()
def search_pdb(query: str, limit: int = 10) -> dict:
    """Find PDB IDs by keyword/molecule name (e.g. 'hemoglobin', 'CRISPR Cas9').
    Use when the user names a molecule but not an ID."""
    from vmd_agent.inputs import fetch as fetch_mod
    return fetch_mod.search_pdb(query, limit=limit)


@tool()
def fetch_structure(identifier: str, out_dir: str = "structures",
                    source: str = "auto", file_format: str = "auto") -> dict:
    """Download a structure from the web to a local file. Use ONLY when the entry is not already in the data folder;
    for a file that is already there use inspect_files, detect_system or structure_stats. To see it afterwards, call visualize_and_interpret on the saved file.

    identifier: PDB ID (e.g. '1UBQ'), UniProt accession for an AlphaFold model
    (e.g. 'P69905'), or a direct URL. Falls back to mmCIF when the legacy PDB
    format is unavailable (large structures); mmCIF is read natively."""
    from vmd_agent.inputs import fetch as fetch_mod
    return fetch_mod.fetch_structure(identifier, out_dir=_p(out_dir),
                                     source=source, file_format=file_format)


@tool()
@shows_in_window
def visualize_and_interpret(topology: str, trajectory: Optional[str] = None,
                            out_dir: str = "vmd_agent_output",
                            views: Optional[List[str]] = None,
                            style: str = "publication",
                            background: str = "white",
                            frame: int = -1,
                            focus: str = "overview",
                            representation: Optional[str] = None,
                            annotate: bool = True,
                            session_dir: Optional[str] = None,
                            vmd_path: Optional[str] = None,
                            renderer: str = "auto") -> dict:
    """AUTO pipeline: inspect -> detect -> recipe -> render multi-view images ->
    return a grounded interpretation package (legend + what-to-look-for +
    preliminary explanation + image paths + provenance record). After calling
    this, view each image with view_image and write the interpretation, then
    verify_claims and assemble_report.

    This is the one-call entry point for "visualize an uploaded file and
    interpret it"."""
    pkg = auto_mod.visualize_and_interpret(
        _p(topology), _p(trajectory), out_dir=_p(out_dir),
        views=tuple(views) if views else ("front", "side", "top"),
        style=style, background=background, frame=frame, focus=focus,
        representation=representation, annotate=annotate,
        vmd_path=_p(vmd_path), renderer=renderer)
    if session_dir and pkg.get("ok"):
        _store(session_dir, "inspection", pkg.get("inspection"))
        _store(session_dir, "detection", pkg.get("detection"))
        _store(session_dir, "renderer", pkg.get("renderer"))
        _store(session_dir, "provenance", pkg.get("provenance_path"))
        for v, p in (pkg.get("images") or {}).items():
            report_mod.Session(_p(session_dir)).add_figure(
                p, caption=f"Render ({v} view)")
    return pkg


@tool()
@shows_in_window
def render_image(topology: Optional[str] = None, trajectory: Optional[str] = None,
                 frame: int = -1, out_png: str = "vmd_render.png",
                 width: int = 1600, height: int = 1200,
                 background: str = "white",
                 recipe_path: Optional[str] = None,
                 scene_spec: Optional[dict] = None,
                 vmd_path: Optional[str] = None) -> dict:
    """Render one publication image via headless VMD+Tachyon. Requires VMD (use visualize_and_interpret with
    renderer='matplotlib' without it). With only topology (and trajectory) it draws the system the way detect_system
    suggests. To draw a scene you describe, pass scene_spec: {reps: [{selection, style, color, material, params}],
    isosurfaces: [{file, isovalue, color, style: solid|wireframe|points}], background, frame, rotate: [[axis, degrees]],
    zoom, projection, axes, depthcue, shadows, ambient_occlusion}. Styles: Lines, Licorice, VDW, CPK, NewCartoon, QuickSurf,
    Surf, MSMS, ...; colors: Name, Element, ResName, Chain, Structure, Beta, ColorID n, ... (topology may then be left out
    for a map-only scene). Use export_session to hand the same scene to a VMD user."""
    if scene_spec is not None:
        from vmd_agent.vmdkit import scene
        return scene.render_scene(scene_spec, _p(topology), _p(trajectory), _p(out_png), width=width, height=height,
                                  vmd_path=_p(vmd_path))
    if not topology:
        raise security.InvalidInput("give a topology, or a scene_spec that describes what to draw")
    det = None
    if not recipe_path:
        det = detect_mod.detect_system(_p(topology), _p(trajectory))
    return render_mod.render_image(
        _p(topology), _p(trajectory), frame=frame, detection=det,
        recipe_path=_p(recipe_path), out_png=_p(out_png), width=width,
        height=height, background=background, vmd_path=_p(vmd_path))


@tool()
def render_movie(topology: str, trajectory: Optional[str] = None,
                 out_mp4: str = "vmd_movie.mp4", stride: int = 1,
                 fps: int = 24, width: int = 1280, height: int = 720,
                 spin: bool = False, scene_spec: Optional[dict] = None,
                 frames: int = 72, degrees: float = 360.0, axis: str = "y",
                 vmd_path: Optional[str] = None) -> dict:
    """Render a movie via VMD+Tachyon+ffmpeg. Requires VMD. By default it plays a trajectory (give trajectory) in ONE VMD
    session with a fixed camera. With spin=true it is a rotating-view movie instead (a turntable) of the scene in
    scene_spec (same form as in render_image): the camera turns `degrees` about `axis` over `frames` frames."""
    if spin:
        from vmd_agent.vmdkit import scene
        return scene.render_turntable(scene_spec or {}, _p(topology), _p(trajectory), _p(out_mp4), frames=frames,
                                      degrees=degrees, axis=axis, fps=fps, width=width, height=height, vmd_path=_p(vmd_path))
    if not trajectory:
        raise security.InvalidInput("a movie of a trajectory needs a trajectory (or use spin=true for a rotating view of one structure)")
    topology, trajectory = _p(topology), _p(trajectory)
    det = detect_mod.detect_system(topology, trajectory)
    r = render_mod.render_movie(
        topology, trajectory, detection=det, out_mp4=_p(out_mp4), stride=stride,
        fps=fps, width=width, height=height, vmd_path=_p(vmd_path))
    # A movie is not delivered until the encoded file has been checked: decode
    # it and confirm it matches what was asked for, then hand back the numbers
    # needed to map any still to its trajectory frame.
    if r.get("ok") and r.get("movie"):
        r["validation"] = media.validate_video(
            r["movie"], expect_width=width, expect_height=height,
            expect_fps=float(fps), expect_n_frames=r.get("n_frames"))
        r["frame_to_source_mapping"] = {
            "fps": fps, "stride": stride, "first_frame": 0,
            "relation": "source_frame = video_frame * stride"}
        r["next_step"] = ("Call interpret_video on `movie` to sample and "
                          "verify stills, then view_image each one before "
                          "describing what the movie shows.")
    return r


ENV_ENABLE_TCL = "VMD_AGENT_ENABLE_TCL"


@tool()
def run_tcl(script: str, vmd_path: Optional[str] = None) -> dict:
    """Run Tcl in headless VMD (escape hatch for VMD-only analyses).

    DISABLED unless the server is started with VMD_AGENT_ENABLE_TCL=1: Tcl can
    run arbitrary programs, and no filter can stop that (command names can be
    built at run time), so enabling this tool means trusting the caller with
    code execution on this machine. When enabled, a deny-list still rejects
    the obvious dangerous commands as an accident guard, not a boundary."""
    if os.environ.get(ENV_ENABLE_TCL) != "1":
        return {"ok": False, "blocked": True,
                "error": "run_tcl is disabled. Tcl can run arbitrary "
                         "programs and cannot be made safe by filtering; set "
                         f"{ENV_ENABLE_TCL}=1 on the server only if you fully "
                         "trust the caller."}
    return render_mod.run_tcl(script, vmd_path=_p(vmd_path))


# ---- analysis -------------------------------------------------------------
@tool()
def analyze_trajectory(topology: str, trajectory: str,
                       analyses: List[str],
                       selection: str = "protein",
                       sel2: Optional[str] = None,
                       cutoff: float = 4.0, axis: str = "z",
                       step: int = 1,
                       out_dir: Optional[str] = None,
                       session_dir: Optional[str] = None,
                       unwrap: bool = False,
                       dt_ps: Optional[float] = None) -> dict:
    """Run rmsd/rmsf/rgyr/hbonds/contacts/distance/sasa/density/convergence on
    a trajectory. Verdicts such as 'drifting' come from autocorrelation-aware
    statistics, not fixed thresholds, and say when there are too few
    independent samples. The result includes periodic-boundary diagnostics
    (set unwrap=true to make the selection whole) and an honest time axis;
    DCD header times are flagged as unreliable, so pass dt_ps (ps between saved
    frames) when you know the real spacing."""
    r = analysis.analyze_trajectory(
        _p(topology), _p(trajectory), analyses=analyses, selection=selection,
        sel2=sel2, cutoff=cutoff, axis=axis, step=step, out_dir=_p(out_dir),
        unwrap=unwrap, dt_ps=dt_ps)
    _store(session_dir, "analysis", r)
    return r


@tool()
@shows_in_window
def select_keyframes(topology: str, trajectory: str, k: int = 9,
                     selection: str = "protein", sel2: Optional[str] = None,
                     out_dir: Optional[str] = None, render: bool = False,
                     renderer: str = "auto", step: int = 1,
                     vmd_path: Optional[str] = None) -> dict:
    """Pick the k most informative trajectory frames by detecting change points
    in RMSD, Rg (and contacts / COM distance when sel2 is given), instead of
    sampling uniformly. A uniform baseline is returned for comparison. With
    render=true the frames are drawn with one fixed camera. View the frames
    before interpreting; an event that moves none of the signals is missed."""
    return auto_mod.select_keyframes(
        _p(topology), _p(trajectory), k=k, selection=selection, sel2=sel2,
        step=step, out_dir=_p(out_dir), render=render, renderer=renderer,
        vmd_path=_p(vmd_path))


@tool()
def verify_claims(topology: str, claims: List[str],
                  trajectory: Optional[str] = None, frame: int = 0,
                  step: int = 1, session_dir: Optional[str] = None) -> dict:
    """Check statements about the system against measurements. Each claim is
    labelled supported / contradicted / unverifiable / unparsed with its
    evidence and criterion. Pass plain sentences ('The ligand is buried', 'It
    has 4 disulfide bridges', 'The protein is mostly helical', 'The system is
    stable') or structured dicts. Run this on your own write-up before
    assemble_report; unparsed sentences were not checked at all."""
    from vmd_agent.evidence import claims as claims_mod
    r = claims_mod.verify_claims(_p(topology), claims, _p(trajectory),
                                 frame=frame, step=step)
    if session_dir:
        report_mod.Session(_p(session_dir)).add_claims(r)
    return r


# ---- media / interpretation ----------------------------------------------
@tool()
def probe_video(video: str, count_frames: bool = False,
                expect_width: Optional[int] = None,
                expect_height: Optional[int] = None,
                expect_fps: Optional[float] = None,
                expect_n_frames: Optional[int] = None,
                expect_min_duration_s: Optional[float] = None) -> dict:
    """Read a video's real codec/geometry/timing metadata and prove it decodes.

    Use on any encoded movie -- including one the user supplies. Encoded video
    is rendered visual evidence, NOT a molecular trajectory: VMD cannot load an
    MP4 as coordinates, so route such input here, never to detect_system.
    To check that it matches what was asked for (size, frame rate, frame count,
    length), give the expect_* values: the answer then has a `validation` with
    one line per check, and an expectation left unset is reported as "not checked"
    rather than passing, so a thin check never reads as a thorough one.
    """
    r = media.probe_video(_p(video), count_frames=count_frames)
    if r.get("ok") and r.get("width"):
        r["summary"] = (f"{r.get('width')} x {r.get('height')} pixels (width x height), {r.get('fps')} frames per second, {r.get('n_frames')} frames, "
                        f"{r.get('duration_s')} s long, {r.get('codec')}, file size {r.get('size_bytes')} bytes (not the picture size).")
    if any(v is not None for v in (expect_width, expect_height, expect_fps, expect_n_frames, expect_min_duration_s)):
        r["validation"] = media.validate_video(
            _p(video), expect_width=expect_width, expect_height=expect_height, expect_fps=expect_fps,
            expect_n_frames=expect_n_frames, expect_min_duration_s=expect_min_duration_s)
    return r


@tool()
def interpret_video(video: str, n_frames: int = 9,
                    out_dir: Optional[str] = None,
                    timestamps: Optional[List[float]] = None,
                    stride: int = 1, first_frame: int = 0,
                    time_per_frame: Optional[float] = None,
                    time_unit: str = "ns",
                    source_topology: Optional[str] = None,
                    source_trajectory: Optional[str] = None,
                    count_frames: bool = False,
                    session_dir: Optional[str] = None) -> dict:
    """ONE CALL: verify a video and return inspectable stills for interpretation (n_frames evenly spaced ones, or
    stills at the given timestamps).

    Probes the file, proves it decodes, extracts stills at known timestamps
    FROM THE ENCODED OUTPUT, runs quality control (blank/frozen frames), maps
    each still back to its source trajectory frame, and writes a manifest.

    Returns evidence, not conclusions: afterwards call view_image on every path
    in `frames`, then write the interpretation and store it with
    record_visual_interpretation(kind='video'). Never claim to have watched a
    video you have not sampled and viewed.
    """
    pkg = media.interpret_video(
        _p(video), n_frames=n_frames, out_dir=_p(out_dir),
        timestamps=timestamps, stride=stride, first_frame=first_frame,
        time_per_frame=time_per_frame, time_unit=time_unit,
        source_topology=_p(source_topology),
        source_trajectory=_p(source_trajectory), count_frames=count_frames)
    _store(session_dir, "video_evidence", pkg)
    return pkg


@tool()
def view_image(path: str) -> dict:
    """Check that a file is an image the agent can be shown (render, frame or
    analysis plot) and return its path. MCP clients receive the image itself; a
    text-only model receives the path and should describe results from the
    measured statistics instead."""
    _p(path)
    if os.path.splitext(path)[1].lower() not in _IMAGE_EXT:
        raise ValueError("view_image only serves image files "
                         f"({', '.join(sorted(_IMAGE_EXT))}).")
    return {"ok": True, "image": os.path.abspath(path),
            "note": "image file; a text-only model cannot see it"}


@tool()
def record_visual_interpretation(session_dir: str, text: str,
                                 source: str = "image",
                                 kind: str = "image") -> dict:
    """Store the agent's visual interpretation into the session for the report."""
    s = report_mod.Session(_p(session_dir))
    if kind == "video":
        s.add_video_interpretation(text, source)
    else:
        s.add_image_interpretation(text, source)
    return {"ok": True, "stored": kind}


# ---- reporting / provenance ----------------------------------------------
@tool()
def assemble_report(session_dir: str,
                    title: str = "VMD-Agent Analysis Report",
                    out_path: Optional[str] = None) -> dict:
    """Compose the full scientific report from everything stored in a session."""
    s = report_mod.Session(_p(session_dir))
    if out_path is None:
        out_path = os.path.join(session_dir, "report.md")
    return report_mod.assemble_report(s.data, title=title, out_path=_p(out_path))


@tool()
def verify_provenance(path_or_dir: str) -> dict:
    """Re-hash the inputs/outputs recorded in a provenance.json and report any
    that changed, so a figure or number can be tied to the exact bytes and
    software that produced it."""
    from vmd_agent.evidence import provenance
    return provenance.verify_provenance(_p(path_or_dir))


# ----------------------------------------------------------- JSON schemas
_SIMPLE = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _json_type(tp) -> dict:
    """JSON-schema fragment for a type annotation (the subset the tools use)."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin is typing.Union:
        real = [a for a in args if a is not type(None)]
        return _json_type(real[0]) if len(real) == 1 else {}
    if origin in (list, typing.List, tuple, typing.Sequence):
        return {"type": "array", "items": _json_type(args[0]) if args else {}}
    if origin in (dict, typing.Dict):
        return {"type": "object"}
    if tp in _SIMPLE:
        return {"type": _SIMPLE[tp]}
    if tp is dict:
        return {"type": "object"}
    return {}


#: parameters a language model is never shown: it fills them with invented values (a made-up VMD path),
#: and the toolkit already finds VMD by itself. They stay available to Python callers.
HIDDEN_FROM_MODELS = ("vmd_path", "headless")


def tool_schema(fn: Callable) -> dict:
    """Name, description and JSON input schema of one tool, from its signature."""
    hints = typing.get_type_hints(fn)
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        if name in HIDDEN_FROM_MODELS:
            continue
        props[name] = _json_type(hints.get(name, str))
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"name": fn.__name__,
            "description": " ".join((fn.__doc__ or "").split()),
            "input_schema": {"type": "object", "properties": props,
                             "required": required}}


def tool_specs(names: Optional[List[str]] = None) -> List[dict]:
    """Specs for every tool (or the named subset), in registration order."""
    return [tool_schema(f) for n, f in TOOLS.items()
            if names is None or n in names]


# The tools that drive VMD itself, and the workflow entry point, register themselves into TOOLS on import.
from vmd_agent import vmd_tools, window_tools, workflows  # noqa: F401

#: the one call that reaches the workflows (a layer above the tools: it runs several of them in a fixed order)
WORKFLOW_ENTRY = "run_workflow"

#: the tool library, as the README and ``vmd-agent tools`` show it: (group, what the group is for, [(tool, needs VMD)]).
#: ``needs`` is "yes", "no", or "optional" (a built-in drawing is used when VMD is missing).
LIBRARY: List[tuple] = [
    ("Look at this computer and your files", "what is here, and what is in it", [
        ("probe_environment", "no"), ("inspect_files", "no"), ("detect_system", "no"), ("structure_stats", "no")]),
    ("Get a structure", "from the PDB, AlphaFold or a web address", [
        ("search_pdb", "no"), ("fetch_structure", "no")]),
    ("Draw", "pictures, movies and scenes", [
        ("visualize_and_interpret", "optional"), ("render_image", "yes"), ("render_movie", "yes"), ("annotate_image", "no"), ("view_image", "no"),
        ("generate_visualization_recipe", "no"), ("list_representations", "no"), ("color_key", "no"), ("export_session", "yes"), ("run_tcl", "yes")]),
    ("Control your VMD window", "drive the VMD you can see: what it loads, draws, shows and answers", [
        ("window_open", "yes"), ("window_load", "yes"), ("window_molecules", "yes"), ("window_representation", "yes"), ("window_display", "yes"),
        ("window_view", "yes"), ("window_animate", "yes"), ("window_query", "yes"), ("window_snapshot", "yes"), ("window_scene", "yes"),
        ("window_visualize", "yes"), ("window_movie", "yes"), ("window_save", "yes")]),
    ("Measure a simulation", "size, shape, flexibility, convergence, box", [
        ("analyze_trajectory", "no"), ("measure_with_vmd", "yes"), ("select_keyframes", "no"), ("periodic_box", "yes")]),
    ("Interactions and structure quality", "who touches whom, secondary structure, geometry", [
        ("find_interactions", "yes"), ("secondary_structure", "yes"), ("backbone_torsions", "yes"), ("check_structure", "yes"), ("align_structures", "yes")]),
    ("Convert and write files", "other formats, fewer atoms or frames", [
        ("convert_trajectory", "yes"), ("write_structure", "yes")]),
    ("Density maps (cryo-EM and more)", "make, read, combine and fit maps", [
        ("make_map", "yes"), ("inspect_map", "no"), ("combine_maps", "no"), ("fit_to_map", "no")]),
    ("Build and prepare a simulation", "systems, mutations, membranes, nanotubes, input files", [
        ("build_system", "yes"), ("mutate_residue", "yes"), ("merge_structures", "yes"), ("build_membrane", "yes"), ("build_nanotube", "yes"),
        ("prepare_namd", "no"), ("write_slurm_script", "no")]),
    ("Video", "check and sample an encoded movie", [
        ("probe_video", "no"), ("interpret_video", "no")]),
    ("Evidence and records", "check claims, keep provenance, write the report", [
        ("verify_claims", "no"), ("record_visual_interpretation", "no"), ("assemble_report", "no"), ("verify_provenance", "no")]),
]


def library_tools() -> List[str]:
    """Every tool of the library, in the order of :data:`LIBRARY` (the workflow entry point is not one of them)."""
    return [n for _g, _d, ts in LIBRARY for n, _v in ts]


def group_of(name: str) -> str:
    """The library group a tool belongs to ('' for the workflow entry point)."""
    return next((g for g, _d, ts in LIBRARY for n, _v in ts if n == name), "")


def needs_vmd(name: str) -> str:
    """'yes', 'no' or 'optional': whether the tool needs VMD installed."""
    return next((v for _g, _d, ts in LIBRARY for n, v in ts if n == name), "no")


#: what the chat is offered: every tool and the workflow entry point (the chat can instead narrow them per question, see routing)
ALL = tuple(library_tools()) + (WORKFLOW_ENTRY,)
