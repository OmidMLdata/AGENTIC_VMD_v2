"""The correct way to do every benchmark task: the tool calls a perfect agent makes and the answer it gives.

Each task of :mod:`vmd_agent.model_tasks` has an :class:`Oracle` here: ``plan`` (the tool calls, with their arguments), ``answer`` (the final answer, written
from what the dataset was built to contain and from the tools' own results), and ``expected`` (what a correct answer says, in words, for the documentation).

Two uses:

* **The benchmark is checked against itself.** ``vmd-agent bench models --oracle`` runs every task's plan through the real tools and grades the reference answer with the
  task's own grader. If a task cannot be passed by doing exactly the right thing, the task is wrong, not the model. A test does this for every task a computer can run.
* **Reference outputs.** ``vmd-agent bench models --list --reference`` prints each prompt with its expected tools and the correct answer computed on your files.

The reference answers are the *facts*, not a style to imitate: a model may word its answer differently, and the graders accept any wording that states the facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple

Call = Tuple[str, dict]


@dataclass
class Oracle:
    plan: Callable[[dict], List[Call]]
    answer: Callable[[dict, Sequence[dict]], str]
    expected: str


def _o(plan, answer, expected) -> Oracle:
    return Oracle(plan if callable(plan) else (lambda t, p=plan: p), answer if callable(answer) else (lambda t, r, a=answer: a), expected)


TOP, TRJ = "protein.pdb", "protein.dcd"
_SCENE = {"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure"}, {"selection": "resname LIG", "style": "Licorice", "color": "Name"}],
          "background": "white"}

ORACLE: Dict[str, Oracle] = {
    # ---- inspect
    "inspect_files": _o([("inspect_files", {"paths": [TOP, TRJ]})],
                        "protein.pdb is a structure (topology) file and protein.dcd is a trajectory; the trajectory loads on the structure, so nothing is missing.",
                        "protein.pdb: a structure with coordinates and topology; protein.dcd: a trajectory; nothing missing (the structure supplies the topology)."),
    "inspect_system": _o([("detect_system", {"topology": TOP})],
                         "protein.pdb is a protein-ligand complex: one protein chain (A) and one ligand, LIG (6 atoms), with no water or ions.",
                         "A protein-ligand complex: 1 protein chain (A), 111 residues, and a ligand named LIG. No water, ions, lipid or nucleic acid."),
    "environment": _o([("probe_environment", {})],
                      lambda t, r: ("VMD is available" + (f", version {r[0]['vmd_version']}" if r and r[0].get("vmd_version") else "") + "; the analysis libraries are installed."
                                    if r and r[0].get("vmd_found") else "VMD was not found on this computer; the analysis tools work without it and pictures use the built-in drawing."),
                      "Whatever probe_environment reports about this computer: whether VMD is found and its version, ffmpeg, the analysis libraries."),
    "stats": _o([("structure_stats", {"topology": TOP})], "protein.pdb has 1 disulfide bridge and 111 protein residues (112 residues in all, counting the ligand).",
                "1 disulfide bridge (CYS31-CYS40) and 111 protein residues."),
    "colours": _o([("color_key", {"color_method": "Structure"})],
                  "Coloured by Structure: purple is alpha helix, blue is 3-10 helix, red is pi helix, yellow is beta strand, and so on; the key lists each secondary-structure type with its colour.",
                  "A key for secondary-structure colouring: helix types (alpha, 3-10, pi) and strand/sheet types each with a colour."),
    "representations": _o([("list_representations", {"name": "QuickSurf"})],
                          "For a pocket surface use QuickSurf (or Surf): it draws a smooth continuous molecular surface that shows the shape and depth of a cavity.",
                          "A surface style (QuickSurf, Surf or MSMS) and what it draws: the molecular surface, good for pockets and cavities."),
    # ---- claims
    "claims_mixed": _o([("verify_claims", {"topology": TOP, "claims": ["It has 1 disulfide bond", "It has 2 chains", "It contains a ligand"]})],
                       "Statement (1) is true (1 disulfide bond is found) and (3) is true (a ligand, LIG, is present). Statement (2) is false: there is 1 protein chain, not 2 chains.",
                       "(1) true, (3) true, (2) false: one protein chain."),
    "claims_water": _o([("detect_system", {"topology": TOP})], "No: protein.pdb contains no water molecules and no ions.", "No water and no ions."),
    # ---- trajectory
    "rg": _o([("analyze_trajectory", {"topology": TOP, "trajectory": TRJ, "analyses": ["rgyr"]})],
             lambda t, r: f"The mean radius of gyration of the protein is {t['rg']:.2f} A, essentially constant over the 20 frames.",
             "The mean radius of gyration, computed independently with MDAnalysis from the files (the structure only translates, so it is constant)."),
    "rmsd_settled": _o([("analyze_trajectory", {"topology": TOP, "trajectory": TRJ, "analyses": ["rmsd", "convergence"]})],
                       lambda t, r: f"After alignment the mean RMSD is {t['aligned_rmsd']:.2f} A, which is only the coordinate noise: it has converged, with no drift.",
                       "About 0.12 A (the built-in noise of 0.05 A per coordinate, differenced between frames) and no drift: converged."),
    "keyframes": _o([("select_keyframes", {"topology": TOP, "trajectory": TRJ, "k": 3})], "The three most informative frames are 0 (the first), 3 (a change in RMSD) and 19 (the last).",
                    "Three frames that include the first (0) and the last (19)."),
    "drift": _o([("measure_with_vmd", {"topology": TOP, "trajectory": TRJ, "kind": "rmsd", "align": False})],
                lambda t, r: f"Without alignment the RMSD reaches {t['drift_total']:.1f} A at the last frame: the protein moves 0.3 A per frame along x.",
                "5.7 A at the last frame (19 frames x 0.3 A drift per frame)."),
    "rmsf": _o([("analyze_trajectory", {"topology": TOP, "trajectory": TRJ, "analyses": ["rmsf"]})],
               "The RMSF analysis gives each residue's fluctuation; residues fluctuate by about the same small amount (the motion is noise plus a rigid drift), no region is flexible.",
               "Per-residue RMSF reported; fluctuations are uniformly small (no flexible region was built in)."),
    # ---- measure_with_vmd
    "contacts": _o([("find_interactions", {"topology": TOP, "trajectory": TRJ, "kind": "contacts", "selection2": "resname LIG", "cutoff": 5.0})],
                   lambda t, r: "Residues in persistent contact with the ligand (within 5 A, present in every frame): " + ", ".join(str(x) for x in t["near_ligand"]) + ".",
                   "The residues of the protein within 5 A of the buried ligand in every frame (computed with MDAnalysis)."),
    "secondary": _o([("secondary_structure", {"topology": TOP, "step": 5})],
                    lambda t, r: f"About {t['helix_percent']:.0f}% of the residues are helix and about 31% are strand (VMD's STRIDE).",
                    "About 47% helix and about 31% strand (the structure was designed with these)."),
    "pbc": _o([("detect_system", {"topology": TOP, "trajectory": TRJ})], lambda t, r: f"Yes, the periodic box is constant: {t['box']:.0f} x {t['box']:.0f} x {t['box']:.0f} A, with no change in volume.",
              "Constant, 80 x 80 x 80 A, 0% volume change."),
    "torsions": _o([("backbone_torsions", {"topology": TOP})],
                   lambda t, r: ("Backbone torsions: " + ", ".join(f"{v} {k}" for k, v in (r[0].get("counts") or {}).items()) + "; outliers are listed with their residues.") if r else "",
                   "Counts of favoured, allowed and outlier residues, and the outliers by residue (the idealised helices and strands put a few residues outside the boxes)."),
    "structure_check": _o([("check_structure", {"topology": TOP})],
                          lambda t, r: f"The structure check found {r[0].get('chirality_errors')} chirality errors and {r[0].get('cis_peptides')} cis peptides, and no chain gaps (0 chain gaps).",
                          "0 chain gaps (one continuous chain), plus the chirality and cis-peptide counts the tool reports."),
    "align": _o([("align_structures", {"mobile": "moved.pdb", "reference": TOP, "out_pdb": "aligned.pdb"})],
                lambda t, r: f"Superposing on the alpha carbons took the RMSD from {r[0]['rmsd_before']:.2f} A before to {r[0]['rmsd_after']:.4f} A after; saved as aligned.pdb.",
                "A large RMSD before (the model was turned and shifted), about 0 after (a rigid move is undone exactly); aligned.pdb written."),
    "capabilities": _o([("probe_environment", {"plugins": True})], "This VMD has plugins in several classes: wrapped (I can drive them), gui-only, needing an external program, and not wrapped; the wrapped ones include autopsf, mutator, pmepot and more.",
                       "The plugin classes from probe_environment(plugins=true): wrapped, library, gui_only, external_program, not_wrapped."),
    # ---- files
    "convert": _o([("convert_trajectory", {"topology": TOP, "trajectory": TRJ, "out_path": "ca.dcd", "selection": "name CA", "step": 5})],
                  "Wrote ca.dcd with the 111 alpha carbons of frames 0, 5, 10 and 15 (4 frames).", "ca.dcd: 111 atoms x 4 frames."),
    "write_frame": _o([("write_structure", {"topology": TOP, "trajectory": TRJ, "out_path": "frame5.pdb", "frame": 5})], "Saved frame 5 as frame5.pdb (563 atoms).", "frame5.pdb with all 563 atoms."),
    # ---- build
    "build_solvated": _o([("build_system", {"input_pdb": TOP, "out_prefix": "build/sys", "padding": 8.0})],
                         "Built a solvated system in a water box with 8 A padding; it is neutral (net charge 0) after adding ions. The ligand was left out and needs its own parameters.",
                         "A water box and ions, net charge 0; the ligand is excluded and reported."),
    "mutate": _o([("mutate_residue", {"psf": "dry.psf", "pdb": "dry.pdb", "out_prefix": "mutant", "segid": "P0", "resid": 5, "new_resname": "GLY"})],
                 "Residue 5 of segment P0 is now glycine; the mutated system is written as mutant.psf and mutant.pdb.", "mutant.psf/pdb with residue 5 = GLY (fewer atoms than alanine)."),
    "merge": _o([("merge_structures", {"psf_a": "dry.psf", "pdb_a": "dry.pdb", "psf_b": "dry.psf", "pdb_b": "dry.pdb", "out_prefix": "two"})],
                "Merged the system with itself into two.psf and two.pdb, which holds twice the atoms; both copies share segment names, so rename one before simulating.", "two.psf/pdb with twice the atoms."),
    "membrane": _o([("build_membrane", {"out_prefix": "membrane/mem", "x_size": 40.0, "y_size": 40.0})],
                   lambda t, r: f"Built a POPC bilayer of 40 x 40 A; its thickness, phosphate to phosphate, is {r[0].get('thickness_P_to_P_A')} A (a POPC bilayer is about 38 A thick).",
                   "A POPC bilayer, thickness about 38 A (between 30 and 45)."),
    "nanotube": _o([("build_nanotube", {"out_pdb": "tube.pdb", "n": 6, "m": 6, "length_nm": 2.0})],
                   lambda t, r: f"Built a (6,6) carbon nanotube, 2 nm long, as tube.pdb; its radius is {t['tube_radius']:.2f} A.", "Radius 4.07 A (2.46 x sqrt(108) / 2 pi)."),
    "namd_input": _o([("prepare_namd", {"psf": "build/sys_ion.psf", "pdb": "build/sys_ion.pdb", "out_prefix": "eq"})],
                     "Wrote the NAMD input eq.namd (CHARMM36, PME, minimise then equilibrate) with its parameter files; it has not been run in NAMD.", "eq.namd and the parameter files, with a warning that it was not run."),
    # ---- maps
    "volume_info": _o([("inspect_map", {"path": "blob.dx"})], lambda t, r: f"blob.dx is a 24 x 24 x 24 grid with 1.0 A spacing; its highest value is {t['blob_peak']:.2f}.",
                      "Grid 24 x 24 x 24, spacing 1.0 A, maximum 4.80."),
    "map_scale": _o([("combine_maps", {"map_a": "blob.dx", "op": "scale", "out_dx": "blob2.dx", "value": 2.0})],
                    lambda t, r: f"Doubled the map and saved blob2.dx; the new maximum is {2 * t['blob_peak']:.2f}.", "blob2.dx, maximum 9.59."),
    "fit_map": _o([("fit_to_map", {"model": "moved.pdb", "map_file": "target.dx", "resolution": 8.0, "out_pdb": "fitted.pdb"})],
                  lambda t, r: f"The fit raised the correlation from {r[0]['correlation_before']:.2f} to {r[0]['correlation_after']:.2f}; the fitted model is fitted.pdb.",
                  "Correlation from below 0.7 to above 0.97; the model is put back where it started (within 0.5 A)."),
    "density": _o([("make_map", {"topology": TOP, "trajectory": TRJ, "out_dx": "lig.dx", "kind": "occupancy", "selection": "resname LIG"})], "Wrote the occupancy map of the ligand as lig.dx.", "lig.dx written."),
    # ---- render
    "render": _o([("render_image", {"topology": TOP, "out_png": "out.png", "width": 320, "height": 240})], "Rendered protein.pdb at 320 by 240 into out.png.", "out.png, 320 x 240."),
    "scene": _o([("render_image", {"scene_spec": _SCENE, "topology": TOP, "trajectory": TRJ, "out_png": "scene.png", "width": 320, "height": 240})],
                "Drew the protein as a cartoon coloured by secondary structure with the ligand as licorice into scene.png (320 by 240).", "scene.png from a scene with two representations."),
    "turntable": _o([("render_movie", {"spin": True, "scene_spec": _SCENE, "topology": TOP, "trajectory": TRJ, "out_mp4": "spin.mp4", "frames": 6, "width": 320, "height": 240})],
                    "Made a 6-frame rotating movie as spin.mp4.", "spin.mp4 with 6 frames."),
    "export_scene": _o([("export_session", {"scene_spec": _SCENE, "topology": TOP, "trajectory": TRJ, "out_dir": "session"})],
                       "Exported the scene to the folder session; open it in your own VMD with `vmd -e session/session.tcl`.", "session/ with session.tcl, the inputs and a manifest."),
    "recipe": _o([("generate_visualization_recipe", {"topology": TOP, "out_path": "recipe.tcl"})], "Wrote a VMD script that draws protein.pdb sensibly as recipe.tcl.", "recipe.tcl."),
    "figure_labels": _o([("annotate_image", {"image_path": "figure.png", "topology": TOP, "out_path": "labelled.png"})], "Added a colour key and the structure's statistics to figure.png; saved as labelled.png.", "labelled.png."),
    "look_at_image": _o([("view_image", {"path": "figure.png"})], "Yes, figure.png is an image file I can show.", "It is an image."),
    "movie": _o([("render_movie", {"topology": TOP, "trajectory": TRJ, "out_mp4": "movie.mp4", "stride": 5, "fps": 5, "width": 320, "height": 240})], "Rendered every 5th frame (4 frames) as movie.mp4 at 320 by 240.", "movie.mp4 with 4 frames."),
    "draw_matplotlib": _o([("visualize_and_interpret", {"topology": TOP, "out_dir": "pics", "views": ["front", "side"], "renderer": "matplotlib"})], "Drew front and side views without VMD into the folder pics.", "Pictures in pics/."),
    # ---- video
    "probe_video": _o([("probe_video", {"video": "clip.mp4"})], "clip.mp4 is 160 x 120 pixels, 12 frames per second, 24 frames (2 seconds).", "160 x 120, 12 fps, 24 frames."),
    "validate_video": _o([("probe_video", {"video": "clip.mp4", "expect_width": 320, "expect_height": 240})], "No: clip.mp4 is 160 by 120, not 320 by 240.", "No: it is 160 x 120."),
    "stills": _o([("interpret_video", {"video": "clip.mp4", "n_frames": 3})], "Extracted 3 evenly spaced stills from clip.mp4; they decode.", "3 stills."),
    # ---- workflows
    "settled": _o([("run_workflow", {"name": "equilibration_check", "files": [TOP, TRJ]})], lambda t, r: "The run has settled: " + str((r[0] or {}).get("verdict", "")) + " The full report is written to report.md and report.html.",
                  "Yes, settled: no drift, with the verdict and the report location."),
    "overview": _o([("run_workflow", {"name": "structure_overview", "files": [TOP]})], lambda t, r: "Structure overview: " + str((r[0] or {}).get("verdict", "")), "A verdict with findings; a protein-ligand complex."),
    "which_workflows": _o([("run_workflow", {})], "The workflows are structure_overview, equilibration_check, interaction_report, compare_runs, prepare_simulation and cryoem_fit.", "The six workflows by name."),
    "prepare": _o([("run_workflow", {"name": "prepare_simulation", "files": [TOP]})], lambda t, r: "Prepared the simulation: " + str((r[0] or {}).get("verdict", "")) + " A NAMD input was written; it has not been run.", "A checked input, a solvated neutral system and a NAMD input."),
    # ---- hand-off
    "slurm": _o([("write_slurm_script", {"command": "eq.namd", "out_path": "job.sbatch", "gpus": 1, "hours": 2.0, "kind": "namd"})], "Wrote job.sbatch: NAMD on eq.namd for 2 hours on 1 GPU (--time=02:00:00, --gres=gpu:1).", "job.sbatch with the time, the GPU and eq.namd."),
    # ---- records
    "provenance": _o([("verify_provenance", {"path_or_dir": "prov"})], "The recorded inputs and outputs in prov match their checksums: nothing has changed.", "Verified: hashes match."),
    "report": _o([("assemble_report", {"session_dir": "sess", "out_path": "report.md"})], "Wrote report.md from the session: the protein-ligand complex, its composition and warnings.", "report.md."),
    # ---- network
    "search": _o([("search_pdb", {"query": "ubiquitin", "limit": 5})], lambda t, r: "PDB entries about ubiquitin include " + ", ".join((r[0].get("ids") or [])[:3]) + ".", "A list of PDB IDs (four characters each)."),
    "fetch": _o([("fetch_structure", {"identifier": "1UBQ", "out_dir": "pdbs"}), ("detect_system", {"topology": "pdbs/1ubq.pdb"})], "Downloaded 1UBQ into pdbs; ubiquitin has 76 residues.", "76 residues."),
    # ---- decline
    "missing_file": _o([("analyze_trajectory", {"topology": "missing.pdb", "trajectory": "missing.dcd", "analyses": ["rmsd"]})],
                       "I cannot compute that: missing.pdb and missing.dcd do not exist in your files folder.", "A refusal: the files do not exist; no RMSD is given."),
    "outside_sandbox": _o([("inspect_files", {"paths": ["/etc/hosts"]})], "I cannot do that: /etc/hosts is outside the files folder I am allowed to use.", "A refusal: outside the allowed folder."),
    "tcl_disabled": _o([("run_tcl", {"script": "puts [molinfo top get numatoms]"})], "I cannot run that: the Tcl tool is disabled for safety, so nothing was run.", "A refusal: the Tcl tool is disabled."),
    "no_such_measure": _o([], "I cannot answer that: no tool here computes a binding free energy, so I cannot give one.", "A refusal: no tool measures a binding free energy; no number is given."),
    "wrong_pair": _o([("probe_video", {"video": "clip.mp4"})], "I cannot compute that: clip.mp4 is a video, not a trajectory, so there is no RMSD.", "A refusal: a video is not a trajectory."),
}
