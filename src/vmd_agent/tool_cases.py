"""The tool test set: at least one case for every tool, each checked against what the data was *built* to contain.

``vmd-agent bench tools`` writes the dataset of :mod:`vmd_agent.tool_dataset` into a folder, runs every case through
the real tool, and prints one line per case: ``pass``, ``FAIL`` or ``skip`` (with the reason: no VMD, no ffmpeg, no network),
with the wall-clock seconds the tool took. Nothing is mocked and no result is stored in the repository: the expectations are
facts of the construction (a drift of 0.3 A per frame gives an un-aligned RMSD of 5.7 A after 19 frames) or of an
independent implementation (MDAnalysis, NumPy) run on the same files.

A case is ``Case(id, tool, args, check, needs)``. ``args`` and ``check`` receive a :class:`Context`; ``check`` returns
a list of problems (empty = pass). Cases run in order and may use the outputs of earlier ones (a built system is mutated, a
visualisation's provenance is verified), so ``--only`` pulls in what a case depends on.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from vmd_agent import tool_dataset as D


# ------------------------------------------------------------------ the context a case sees
class Context:
    def __init__(self, folder: str, info: dict):
        self.folder, self.info = os.path.realpath(folder), info
        self.results: Dict[str, dict] = {}

    def p(self, name: str) -> str:
        """A dataset file."""
        return os.path.join(self.folder, name)

    def out(self, *parts: str) -> str:
        """A path for something a tool writes (its folder is made)."""
        path = os.path.join(self.folder, "out", *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    @property
    def design(self) -> dict:
        return self.info["design"]

    def universe(self, path: str):
        import MDAnalysis as mda
        return mda.Universe(path)

    def scene(self) -> dict:
        with open(self.p("scene.json")) as fh:
            return json.load(fh)


# ---------------------------------------------------------------- how a result is checked
class Check:
    """Collects problems instead of raising, so one case reports everything that is wrong with it."""

    def __init__(self, result):
        self.r, self.problems = result, []

    def get(self, path: str, default=None):
        cur = self.r
        for part in path.split("."):
            try:
                cur = cur[int(part)] if isinstance(cur, list) else cur[part]
            except (KeyError, IndexError, ValueError, TypeError):
                return default
        return cur

    def _fail(self, msg: str) -> "Check":
        self.problems.append(msg)
        return self

    def ok(self) -> "Check":
        if not isinstance(self.r, dict):
            return self._fail(f"expected a dict result, got {type(self.r).__name__}")
        if self.r.get("error") or self.r.get("ok") is False:
            return self._fail(f"the tool reported an error: {str(self.r.get('error'))[:200]}")
        return self

    def fails(self, text: str = "") -> "Check":
        """The tool must refuse (a wrong request is an error, not an empty answer)."""
        if not (isinstance(self.r, dict) and (self.r.get("error") or self.r.get("ok") is False)):
            return self._fail("expected an error, got a result")
        if text and text.lower() not in str(self.r.get("error")).lower():
            return self._fail(f"the error should mention '{text}': {str(self.r.get('error'))[:160]}")
        return self

    def eq(self, path: str, want) -> "Check":
        got = self.get(path)
        return self if got == want else self._fail(f"{path} = {got!r}, expected {want!r}")

    def near(self, path: str, want: float, tol: float) -> "Check":
        got = self.get(path)
        if not isinstance(got, (int, float)) or abs(got - want) > tol:
            return self._fail(f"{path} = {got!r}, expected {want:.4g} within {tol:g}")
        return self

    def between(self, path: str, low: float, high: float) -> "Check":
        got = self.get(path)
        if not isinstance(got, (int, float)) or not (low <= got <= high):
            return self._fail(f"{path} = {got!r}, expected between {low:g} and {high:g}")
        return self

    def has(self, *paths: str) -> "Check":
        for path in paths:
            if self.get(path) is None:
                self._fail(f"missing {path}")
        return self

    def mentions(self, text: str) -> "Check":
        if text.lower() not in json.dumps(self.r, default=str).lower():
            self._fail(f"the result never mentions '{text}'")
        return self

    def file(self, path: str, min_bytes: int = 1) -> "Check":
        target = self.get(path) if not os.path.isabs(path) else path
        if not isinstance(target, str) or not os.path.isfile(target) or os.path.getsize(target) < min_bytes:
            self._fail(f"{path} is not a file of at least {min_bytes} bytes ({target!r})")
        return self

    def when(self, condition: bool, message: str) -> "Check":
        return self if condition else self._fail(message)


@dataclass
class Case:
    id: str
    tool: str
    args: Callable[[Context], dict]
    check: Callable[[Check, Context], Check]
    needs: Sequence[str] = ()
    after: Sequence[str] = ()
    note: str = ""


# ----------------------------------------------------------------------------- helpers
def _png_size(path: str):
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def _png_not_blank(path: str) -> bool:
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        return float(np.asarray(im.convert("L")).std()) > 0.5


def _independent_rg(c: Context) -> float:
    return float(c.universe(c.p("protein.pdb")).select_atoms("protein").radius_of_gyration())


def _protein_mass(c: Context) -> float:
    return float(c.universe(c.p("protein.pdb")).select_atoms("protein").masses.sum())


def _top(c): return c.p("protein.pdb")
def _trj(c): return c.p("protein.dcd")


def _tcl_enabled() -> bool:
    return os.environ.get("VMD_AGENT_ENABLE_TCL") == "1"


def _atoms_in(path_psf: str, path_pdb: str, c: Context) -> int:
    import MDAnalysis as mda
    return int(mda.Universe(path_psf, path_pdb).atoms.n_atoms)


def _fit_error(c: Context, fitted: str) -> float:
    """RMSD in angstrom between the fitted model and where the model started (the un-moved protein)."""
    import numpy as np
    a = c.universe(fitted).select_atoms("protein").positions
    b = c.universe(c.p("protein.pdb")).select_atoms("protein").positions
    return float(np.sqrt(((a - b) ** 2).sum(1).mean()))


# ------------------------------------------------------------------------------ the cases
def _cases() -> List[Case]:
    n_res = lambda c: c.design["n_residues"]   # noqa: E731
    cases: List[Case] = [
        # ---- the environment and the files
        Case("probe_environment", "probe_environment", lambda c: {},
             lambda k, c: k.has("can_analyze", "analysis_libs").eq("analysis_libs.MDAnalysis", True)),
        Case("inspect_files", "inspect_files", lambda c: {"paths": [_top(c), _trj(c)]},
             lambda k, c: k.ok().eq("files.0.role", "structure").eq("files.1.role", "trajectory").eq("has_coordinates", True)),
        Case("detect_system", "detect_system", lambda c: {"topology": _top(c)},
             lambda k, c: k.eq("n_atoms", c.info["n_atoms"]).eq("components.protein.chains", ["A"])
             .eq("components.ligands_or_other.resnames", ["LIG"]).mentions("protein-ligand")),
        Case("structure_stats", "structure_stats", lambda c: {"topology": _top(c)},
             lambda k, c: k.eq("n_disulfide_bridges", c.design["n_disulfides"]).eq("n_protein_chains", c.design["n_chains"])
             .eq("secondary_structure.n_residues_assessed", n_res(c))),
        Case("list_representations", "list_representations", lambda c: {"category": "surface"},
             lambda k, c: k.has("representations.QuickSurf").when(
                 all(v.get("category") == "surface" for v in (k.get("representations") or {}).values()),
                 "a representation outside the asked category was listed")),
        Case("describe_representation", "describe_representation", lambda c: {"name": "NewCartoon"},
             lambda k, c: k.eq("name", "NewCartoon").has("summary", "vmd_command")),
        Case("describe_representation_unknown", "describe_representation", lambda c: {"name": "NoSuchRepresentation"},
             lambda k, c: k.fails(), note="a wrong name is refused, not answered with something plausible"),
        Case("color_key", "color_key", lambda c: {"color_method": "Structure"},
             lambda k, c: k.eq("type", "categorical").when(len(k.get("entries") or []) >= 3, "fewer than 3 colour entries")),
        Case("generate_visualization_recipe", "generate_visualization_recipe",
             lambda c: {"topology": _top(c), "out_path": c.out("recipe.tcl")},
             lambda k, c: k.ok().file(c.out("recipe.tcl"), 50)),
        # ---- looking at it
        Case("visualize_and_interpret", "visualize_and_interpret",
             lambda c: {"topology": _top(c), "out_dir": c.out("viz"), "views": ["front"], "renderer": "matplotlib"},
             lambda k, c: k.ok().eq("structure_stats.n_disulfide_bridges", c.design["n_disulfides"])
             .file(os.path.join(c.out("viz"), "provenance.json"), 10)),
        Case("annotate_image", "annotate_image",
             lambda c: {"image_path": c.p("figure.png"), "topology": _top(c), "title": "test", "out_path": c.out("annotated.png")},
             lambda k, c: k.ok().file("annotated_image").when(_png_size(c.out("annotated.png"))[0] > 200 and
                                                              _png_size(c.out("annotated.png"))[1] >= 150,
                                                              "the annotated image is not larger than the input")),
        Case("view_image", "view_image", lambda c: {"path": c.p("figure.png")}, lambda k, c: k.ok().file("image")),
        Case("view_image_refuses_a_non_image", "view_image", lambda c: {"path": c.p("design.json")}, lambda k, c: k.fails()),
        Case("render_image", "render_image",
             lambda c: {"topology": _top(c), "out_png": c.out("render.png"), "width": 320, "height": 240},
             lambda k, c: k.ok().eq("tachyon_returncode", 0).file("image").when(
                 _png_size(c.out("render.png")) == (320, 240) and _png_not_blank(c.out("render.png")),
                 "the image is not 320 x 240 or is blank"), needs=("vmd",)),
        Case("render_movie", "render_movie",
             lambda c: {"topology": _top(c), "trajectory": _trj(c), "out_mp4": c.out("movie.mp4"), "stride": 5, "fps": 5,
                        "width": 320, "height": 240},
             lambda k, c: k.ok().eq("n_frames", len(range(0, D.N_FRAMES, 5))).eq("validation.ok", True), needs=("vmd", "ffmpeg")),
        Case("run_vmd_tcl", "run_vmd_tcl", lambda c: {"script": "puts hello"},
             lambda k, c: (k.ok() if _tcl_enabled() else k.fails("disabled")),
             needs=("vmd",) if _tcl_enabled() else (), note="refused unless VMD_AGENT_ENABLE_TCL=1; with it set, it must run"),
        # ---- measuring a simulation
        Case("analyze_trajectory", "analyze_trajectory",
             lambda c: {"topology": _top(c), "trajectory": _trj(c), "analyses": ["rmsd", "rgyr", "rmsf"], "out_dir": c.out("analysis")},
             # aligned RMSD of independent noise: each frame differs from frame 0 by sqrt(2) * sigma * sqrt(3) per atom
             lambda k, c: k.ok().near("results.rmsd.summary.mean", D.NOISE_A * math.sqrt(6), 0.03)
             .near("results.rgyr.summary.mean", _independent_rg(c), 0.05).has("results.rmsf")),
        Case("select_keyframes", "select_keyframes", lambda c: {"topology": _top(c), "trajectory": _trj(c), "k": 3},
             lambda k, c: k.ok().when(len(k.get("frames") or []) == 3 and 0 in k.get("frames") and D.N_FRAMES - 1 in k.get("frames"),
                                      "expected 3 frames including the first and the last")),
        Case("verify_claims", "verify_claims",
             lambda c: {"topology": _top(c), "claims": ["It has 1 chain", f"It has {c.design['n_disulfides']} disulfide bond",
                                                        "It contains a ligand", "It has 2 chains"]},
             lambda k, c: k.eq("counts.supported", 3).eq("counts.contradicted", 1)),
        # ---- video
        Case("probe_video", "probe_video", lambda c: {"video": c.p("clip.mp4"), "count_frames": True},
             lambda k, c: k.ok().eq("width", D.CLIP["width"]).eq("height", D.CLIP["height"]).near("fps", D.CLIP["fps"], 0.01)
             .eq("n_frames", D.CLIP["frames"]).eq("decode_check.decodes", True), needs=("ffmpeg",)),
        Case("validate_video", "validate_video",
             lambda c: {"video": c.p("clip.mp4"), "expect_width": D.CLIP["width"], "expect_height": D.CLIP["height"],
                        "expect_n_frames": D.CLIP["frames"]},
             lambda k, c: k.ok(), needs=("ffmpeg",)),
        Case("validate_video_wrong_size", "validate_video", lambda c: {"video": c.p("clip.mp4"), "expect_width": 999},
             lambda k, c: k.eq("ok", False).eq("checks.width.passed", False), needs=("ffmpeg",),
             note="a video that is not the size asked for must fail the check"),
        Case("extract_video_frames", "extract_video_frames", lambda c: {"video": c.p("clip.mp4"), "n": 3, "out_dir": c.out("frames")},
             lambda k, c: k.ok().eq("n_frames", 3).when(all(os.path.isfile(f) for f in k.get("frames") or []), "a frame file is missing"),
             needs=("ffmpeg",)),
        Case("interpret_video", "interpret_video", lambda c: {"video": c.p("clip.mp4"), "n_frames": 3, "out_dir": c.out("interp")},
             lambda k, c: k.ok().eq("verification.decode_verified", True).eq("quality_control.passed", True), needs=("ffmpeg",)),
        # ---- records
        Case("detect_system_session", "detect_system", lambda c: {"topology": _top(c), "session_dir": c.out("session")},
             lambda k, c: k.eq("n_atoms", c.info["n_atoms"]), note="stores its result in a session folder"),
        Case("record_visual_interpretation", "record_visual_interpretation",
             lambda c: {"session_dir": c.out("session"), "text": "the test pattern is visible", "source": "figure.png"},
             lambda k, c: k.ok().eq("stored", "image"), after=("detect_system_session",)),
        Case("assemble_report", "assemble_report", lambda c: {"session_dir": c.out("session"), "out_path": c.out("session_report.md")},
             lambda k, c: k.file("written_to").mentions("protein-ligand"), after=("detect_system_session", "record_visual_interpretation")),
        Case("verify_provenance", "verify_provenance", lambda c: {"path_or_dir": c.out("viz")},
             lambda k, c: k.ok(), after=("visualize_and_interpret",)),
        Case("verify_provenance_missing", "verify_provenance", lambda c: {"path_or_dir": c.out("no_such_folder")},
             lambda k, c: k.fails()),
        # ---- whole jobs
        Case("list_workflows", "list_workflows", lambda c: {},
             lambda k, c: k.ok().has("workflows.structure_overview", "workflows.equilibration_check", "workflows.cryoem_fit")),
        Case("run_workflow", "run_workflow",
             lambda c: {"name": "equilibration_check", "files": [_top(c), _trj(c)], "out_dir": c.out("workflow")},
             lambda k, c: k.ok().file("report").file("report_html").eq("finding_counts.problem", 0),
             needs=("vmd",), note="the settled run must not be graded a problem; a 0.03% drift in Rg is not a warning"),
        Case("run_workflow_wrong_files", "run_workflow",
             lambda c: {"name": "equilibration_check", "files": [_top(c)], "out_dir": c.out("workflow_bad")},
             lambda k, c: k.fails("needs 2 file")),
        # ---- the tools that drive VMD itself
        Case("vmd_capabilities", "vmd_capabilities", lambda c: {},
             lambda k, c: k.ok().has("wrapped", "counts").when(k.get("counts.wrapped", 0) > 10, "fewer than 10 plugins wrapped"),
             needs=("vmd",)),
        Case("vmd_measure_rgyr", "vmd_measure", lambda c: {"topology": _top(c), "trajectory": _trj(c), "kind": "rgyr"},
             lambda k, c: k.ok().eq("n_frames_loaded", D.N_FRAMES).near("summary.mean", _independent_rg(c), 0.05)
             .when(k.get("summary.std", 1) < 0.05, "the radius of gyration should not change"), needs=("vmd",)),
        Case("vmd_measure_rmsd_unaligned", "vmd_measure",
             lambda c: {"topology": _top(c), "trajectory": _trj(c), "kind": "rmsd", "align": False},
             lambda k, c: k.ok().near("summary.max", D.DRIFT_A * (D.N_FRAMES - 1), 0.1).near("values.0", 0.0, 1e-3), needs=("vmd",),
             note="a drift of 0.3 A per frame is an un-aligned RMSD of 5.7 A after 19 frames"),
        Case("vmd_interactions", "vmd_interactions",
             lambda c: {"topology": _top(c), "trajectory": _trj(c), "kind": "contacts", "selection2": "resname LIG", "cutoff": 5.0},
             lambda k, c: k.ok().when(k.get("n_pairs_ever", 0) > 0, "a buried ligand has contacts").mentions("LIG"), needs=("vmd",)),
        Case("vmd_secondary_structure", "vmd_secondary_structure", lambda c: {"topology": _top(c), "trajectory": _trj(c), "step": 5},
             lambda k, c: k.ok().eq("n_residues", n_res(c)).eq("n_frames", 4)
             .near("mean_helix", c.design["designed_helix_percent"] / 100, 0.1), needs=("vmd",),
             note="the helix fraction VMD's STRIDE finds is the one the structure was designed with, to within 10 points"),
        Case("vmd_backbone_torsions", "vmd_backbone_torsions", lambda c: {"topology": _top(c)},
             lambda k, c: k.ok().when(sum((k.get("counts") or {}).values()) == k.get("n_residues"),
                                      "the regions do not add up to the residues"), needs=("vmd",)),
        Case("vmd_structure_check", "vmd_structure_check", lambda c: {"topology": _top(c)},
             lambda k, c: k.ok().eq("chain_gaps", 0), needs=("vmd",), note="one continuous chain has no gaps"),
        Case("vmd_align_structures", "vmd_align_structures",
             lambda c: {"mobile": c.p("moved.pdb"), "reference": _top(c), "out_pdb": c.out("aligned.pdb")},
             lambda k, c: k.ok().when(k.get("rmsd_before", 0) > 3, "the model should start far away")
             .when(k.get("rmsd_after", 1) < 0.01, "a rigid move is undone exactly").file("aligned_pdb"), needs=("vmd",)),
        Case("vmd_pbc_info", "vmd_pbc_info", lambda c: {"topology": _top(c), "trajectory": _trj(c), "step": 5},
             lambda k, c: k.ok().eq("has_unit_cell", True).near("boxes.0.a", D.BOX_A, 1e-3).near("volume_change_fraction", 0.0, 1e-6),
             needs=("vmd",)),
        Case("vmd_convert_trajectory", "vmd_convert_trajectory",
             lambda c: {"topology": _top(c), "trajectory": _trj(c), "out_path": c.out("ca.dcd"), "selection": "name CA", "step": 5},
             lambda k, c: k.ok().eq("n_frames", 4).eq("n_atoms", n_res(c)).file("out_path"), needs=("vmd",)),
        Case("vmd_write_structure", "vmd_write_structure",
             lambda c: {"topology": _top(c), "trajectory": _trj(c), "out_path": c.out("frame5.pdb"), "frame": 5},
             lambda k, c: k.ok().eq("n_atoms", c.info["n_atoms"]).when(
                 c.universe(c.out("frame5.pdb")).atoms.n_atoms == c.info["n_atoms"], "the file read back has other atoms"),
             needs=("vmd",)),
        Case("vmd_volmap", "vmd_volmap",
             lambda c: {"topology": _top(c), "trajectory": _trj(c), "out_dx": c.out("density.dx"), "kind": "density", "step": 5},
             # a mass-weighted density map integrates to the mass of the selection (the grid has 1 A cells)
             lambda k, c: k.ok().near("integral", _protein_mass(c), 0.02 * _protein_mass(c)).file("map_path"), needs=("vmd",)),
        Case("vmd_volume_info", "vmd_volume_info", lambda c: {"path": c.p("blob.dx")},
             lambda k, c: k.ok().eq("shape", list(D.BLOB["shape"])).eq("spacing", [D.BLOB["spacing"]] * 3)
             .near("max", D.BLOB["peak"] * math.exp(-0.75 / 18.0), 0.01),
             note="the nearest grid point to the centre is 0.75 A^2 away"),
        Case("vmd_build_system_dry", "vmd_build_system",
             lambda c: {"input_pdb": _top(c), "out_prefix": c.out("dry", "sys"), "solvate": False},
             lambda k, c: k.ok().eq("n_chains", c.design["n_chains"]).near("net_charge", 0.0, 0.01).mentions("LIG")
             .when(_atoms_in(k.get("final_psf"), k.get("final_pdb"), c) == k.get("n_atoms"), "the files hold other atoms than reported"),
             needs=("vmd",), note="the ligand is left out and says so"),
        Case("vmd_build_system_solvated", "vmd_build_system",
             lambda c: {"input_pdb": _top(c), "out_prefix": c.out("wet", "sys"), "padding": 8.0},
             lambda k, c: k.ok().near("net_charge", 0.0, 0.01).when(k.get("n_waters", 0) > 500, "no water box").has("box_size_A"),
             needs=("vmd",)),
        Case("vmd_mutate_residue", "vmd_mutate_residue", after=("vmd_build_system_dry",),
             args=lambda c: {"psf": c.results["vmd_build_system_dry"]["final_psf"], "pdb": c.results["vmd_build_system_dry"]["final_pdb"],
                             "out_prefix": c.out("dry", "mutant"), "segid": "P0", "resid": 5, "new_resname": "GLY"},
             check=lambda k, c: k.ok().eq("new_resname", "GLY").when(
                 k.get("n_atoms", 1e9) < c.results["vmd_build_system_dry"]["n_atoms"], "glycine has fewer atoms than alanine")
             .when(c.universe(k.get("psf")).select_atoms("resid 5").resnames[0] == "GLY", "residue 5 is not glycine in the file"),
             needs=("vmd",)),
        Case("vmd_mutate_residue_solvated", "vmd_mutate_residue", after=("vmd_build_system_solvated",),
             args=lambda c: {"psf": c.results["vmd_build_system_solvated"]["final_psf"],
                             "pdb": c.results["vmd_build_system_solvated"]["final_pdb"], "out_prefix": c.out("wet", "mutant"),
                             "segid": "P0", "resid": 5, "new_resname": "GLY"},
             check=lambda k, c: k.fails("dry system"), needs=("vmd",),
             note="a known limit: the mutator failed on a solvated system, and the error now says what to do instead"),
        Case("vmd_merge_structures", "vmd_merge_structures", after=("vmd_build_system_dry",),
             args=lambda c: {"psf_a": c.results["vmd_build_system_dry"]["final_psf"], "pdb_a": c.results["vmd_build_system_dry"]["final_pdb"],
                             "psf_b": c.results["vmd_build_system_dry"]["final_psf"], "pdb_b": c.results["vmd_build_system_dry"]["final_pdb"],
                             "out_prefix": c.out("dry", "two")},
             check=lambda k, c: k.ok().eq("n_atoms", 2 * c.results["vmd_build_system_dry"]["n_atoms"]), needs=("vmd",)),
        Case("vmd_build_membrane", "vmd_build_membrane", lambda c: {"out_prefix": c.out("membrane", "mem"), "x_size": 40.0, "y_size": 40.0},
             lambda k, c: k.ok().near("net_charge", 0.0, 0.01).between("thickness_P_to_P_A", 30, 45)
             .when(abs((k.get("upper_leaflet") or 0) - (k.get("lower_leaflet") or 0)) <= 2, "the leaflets differ by more than 2 lipids"),
             needs=("vmd",), note="a POPC bilayer is about 38 A thick, phosphate to phosphate"),
        Case("vmd_build_nanotube", "vmd_build_nanotube", lambda c: {"out_pdb": c.out("tube.pdb"), "n": 6, "m": 6, "length_nm": 2.0},
             # radius = a * sqrt(n^2 + n*m + m^2) / (2 pi), with a = 2.46 A for carbon
             lambda k, c: k.ok().near("mean_radius_A", 2.46 * math.sqrt(108) / (2 * math.pi), 0.05).file("pdb"), needs=("vmd",)),
        Case("vmd_render_scene", "vmd_render_scene",
             lambda c: {"scene_spec": c.scene(), "topology": _top(c), "trajectory": _trj(c), "out_png": c.out("scene.png"),
                        "width": 320, "height": 240},
             lambda k, c: k.ok().when(_png_size(c.out("scene.png")) == (320, 240) and _png_not_blank(c.out("scene.png")),
                                      "the image is not 320 x 240 or is blank"), needs=("vmd",)),
        Case("export_vmd_session", "export_vmd_session",
             lambda c: {"scene_spec": c.scene(), "topology": _top(c), "trajectory": _trj(c), "out_dir": c.out("session_export")},
             lambda k, c: k.ok().eq("round_trip_check.opens_in_vmd", True).eq("round_trip_check.molecules.0.atoms", c.info["n_atoms"])
             .eq("round_trip_check.molecules.0.representations", len(c.scene()["reps"]))
             .eq("round_trip_check.molecules.0.frames", D.N_FRAMES).file(os.path.join(c.out("session_export"), "manifest.json")),
             needs=("vmd",)),
        Case("vmd_render_turntable", "vmd_render_turntable",
             lambda c: {"scene_spec": c.scene(), "topology": _top(c), "trajectory": _trj(c), "out_mp4": c.out("spin.mp4"),
                        "frames": 6, "width": 320, "height": 240},
             lambda k, c: k.ok().eq("n_frames", 6).file("movie"), needs=("vmd", "ffmpeg")),
        Case("vmd_fit_to_map", "vmd_fit_to_map",
             lambda c: {"model": c.p("moved.pdb"), "map_file": c.p("target.dx"), "resolution": 8.0, "out_pdb": c.out("fitted.pdb")},
             lambda k, c: k.ok().when(k.get("correlation_before", 1) < 0.7 and k.get("correlation_after", 0) > 0.97,
                                      "the fit should raise the correlation from below 0.7 to above 0.97")
             .when(_fit_error(c, c.out("fitted.pdb")) < 0.5, "the fitted model is more than 0.5 A from where it started")),
        Case("vmd_map_arithmetic_scale", "vmd_map_arithmetic",
             lambda c: {"map_a": c.p("blob.dx"), "op": "scale", "out_dx": c.out("blob_x2.dx"), "value": 2.0},
             lambda k, c: k.ok().near("max", 2 * D.BLOB["peak"] * math.exp(-0.75 / 18.0), 0.02)),
        Case("vmd_map_arithmetic_subtract", "vmd_map_arithmetic",
             lambda c: {"map_a": c.p("blob.dx"), "op": "subtract", "map_b": c.p("blob.dx"), "out_dx": c.out("zero.dx")},
             lambda k, c: k.ok().near("max", 0.0, 1e-6).near("min", 0.0, 1e-6)),
        Case("vmd_prepare_namd", "vmd_prepare_namd", after=("vmd_build_system_solvated",),
             args=lambda c: {"psf": c.results["vmd_build_system_solvated"]["final_psf"],
                             "pdb": c.results["vmd_build_system_solvated"]["final_pdb"], "out_prefix": c.out("wet", "eq")},
             check=lambda k, c: k.ok().eq("n_atoms", c.results["vmd_build_system_solvated"]["n_atoms"]).file("config")
             .when("PME" in open(k.get("config")).read(), "the NAMD input has no PME setting")
             .when(all(os.path.isfile(f) for f in k.get("parameter_files") or []), "a parameter file is missing"),
             needs=("vmd",), note="the file is checked against the system, never run in NAMD"),
        Case("vmd_slurm_script", "vmd_slurm_script",
             lambda c: {"command": "equilibrate.namd", "out_path": c.out("job.sbatch"), "gpus": 1, "hours": 2.0, "kind": "namd"},
             lambda k, c: k.ok().file("script").when(
                 all(t in open(k.get("script")).read() for t in ("--gres=gpu:1", "--time=02:00:00", "equilibrate.namd")),
                 "the requested resources are not in the script"),
             note="the script is checked for what was asked, never run on a cluster"),
        # ---- network (the live PDB)
        Case("search_pdb", "search_pdb", lambda c: {"query": "ubiquitin", "limit": 3},
             lambda k, c: k.ok().when(len(k.get("ids") or []) > 0, "no ids"), needs=("network",)),
        Case("fetch_structure", "fetch_structure", lambda c: {"identifier": "1UBQ", "out_dir": c.out("fetched")},
             lambda k, c: k.ok().file("path", 10000).when(
                 c.universe(k.get("path")).select_atoms("protein").n_residues == 76, "1UBQ should have 76 residues"),
             needs=("network",)),
        Case("fetch_and_visualize", "fetch_and_visualize",
             lambda c: {"identifier": "1UBQ", "out_dir": c.out("fetched_viz"), "views": ["front"], "renderer": "matplotlib"},
             lambda k, c: k.ok().has("structure_stats"), needs=("network",)),
    ]
    return cases


CASES: List[Case] = _cases()


# --------------------------------------------------------------------------------- running
def available(need: str) -> Optional[str]:
    """None if the requirement is met, else the reason it is not."""
    if need == "vmd":
        from vmd_agent.environment import find_vmd
        return None if find_vmd() else "no VMD found (set VMD_BIN or run vmd-agent setup)"
    if need == "ffmpeg":
        from vmd_agent.environment import find_ffmpeg
        return None if find_ffmpeg() else "no ffmpeg"
    if need == "network":
        import urllib.request
        try:
            urllib.request.urlopen(urllib.request.Request("https://files.rcsb.org", method="HEAD"), timeout=5)
            return None
        except Exception as e:
            return f"cannot reach the PDB ({type(e).__name__})"
    return f"unknown requirement {need}"


@dataclass
class Record:
    id: str
    tool: str
    status: str                                  # pass | FAIL | skip
    seconds: float = 0.0
    problems: List[str] = field(default_factory=list)
    reason: str = ""
    note: str = ""


def covered_tools() -> set:
    return {c.tool for c in CASES}


def select(only: Optional[Sequence[str]] = None) -> List[Case]:
    """The cases to run: all, or those whose id or tool is named, plus the cases they come after."""
    if not only:
        return list(CASES)
    byid = {c.id: c for c in CASES}
    want = {c.id for c in CASES if c.id in only or c.tool in only}
    unknown = [o for o in only if o not in byid and o not in {c.tool for c in CASES}]
    if unknown:
        raise ValueError("no such case or tool: " + ", ".join(unknown))
    stack = list(want)
    while stack:
        for dep in byid[stack.pop()].after:
            if dep not in want:
                want.add(dep)
                stack.append(dep)
    return [c for c in CASES if c.id in want]


def run(folder: str, only: Optional[Sequence[str]] = None, log: Optional[Callable[[str], None]] = None,
        skip: Sequence[str] = ()) -> List[Record]:
    """Build the dataset in ``folder`` and run the cases. The sandbox is pointed at ``folder`` for the duration."""
    from vmd_agent import security, toolset
    folder = os.path.realpath(folder)
    info = D.make_dataset(folder)
    ctx = Context(folder, info)
    previous = os.environ.get(security.ENV_ROOTS)
    os.environ[security.ENV_ROOTS] = folder
    cwd = os.getcwd()
    os.chdir(folder)
    log = log or (lambda m: None)
    unmet: Dict[str, Optional[str]] = {}
    records: List[Record] = []
    try:
        for case in select(only):
            reason = ""
            for need in case.needs:
                if need in skip:
                    reason = f"{need} skipped on request"
                    break
                unmet.setdefault(need, available(need))
                if unmet[need]:
                    reason = unmet[need] or ""
                    break
            missing = [d for d in case.after if d not in ctx.results]
            if not reason and missing:
                reason = "needs " + ", ".join(missing) + " first"
            if reason:
                records.append(Record(case.id, case.tool, "skip", reason=reason, note=case.note))
                log(f"skip  {case.id:34s} {reason}")
                continue
            started = time.time()
            problems: List[str] = []
            try:
                args = case.args(ctx)
                try:
                    result = toolset.TOOLS[case.tool](**args)
                except Exception as e:             # what the chat does too: a refusal is an error result, not a crash
                    result = {"error": f"{type(e).__name__}: {e}", "raised": True}
                ctx.results[case.id] = result if isinstance(result, dict) else {"value": result}
                problems = case.check(Check(result), ctx).problems
            except Exception as e:
                problems = [f"{type(e).__name__}: {e}"]
            seconds = time.time() - started
            rec = Record(case.id, case.tool, "pass" if not problems else "FAIL", seconds, problems, note=case.note)
            records.append(rec)
            log(f"{rec.status:5s} {case.id:34s} {seconds:6.2f} s" + ("" if not problems else "   " + "; ".join(problems)))
    finally:
        os.chdir(cwd)
        if previous is None:
            os.environ.pop(security.ENV_ROOTS, None)
        else:
            os.environ[security.ENV_ROOTS] = previous
    return records


def summary(records: Sequence[Record]) -> dict:
    out = {"cases": len(records), "pass": sum(r.status == "pass" for r in records),
           "fail": sum(r.status == "FAIL" for r in records), "skip": sum(r.status == "skip" for r in records),
           "seconds": round(sum(r.seconds for r in records), 2)}
    out["tools_covered"] = len({r.tool for r in records if r.status == "pass"})
    return out
