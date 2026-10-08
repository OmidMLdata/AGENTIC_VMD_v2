# The benchmark's tasks and their correct answers

Generated from [`model_tasks.py`](../../src/vmd_agent/model_tasks.py) and [`model_oracle.py`](../../src/vmd_agent/model_oracle.py) (a test keeps this page in step with them). Each task is a plain-language request about the
files of the generated dataset ([the tool test set](tool-test-set.md)); the **correct answer** is what a perfect agent finds with the tools. The values below are facts of how the dataset was built or
are computed from its files with MDAnalysis, independently of the toolkit; on your computer `vmd-agent bench models --list --reference` prints the same, and `vmd-agent bench models --oracle` runs every
task's perfect plan through the real tools and grades it, to check that the benchmark itself can be passed. A model may word its answer differently: the graders accept any wording that states the facts.

A task marked *needs VMD / ffmpeg / network* is skipped (and not counted) on a computer without it.

## inspect

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `inspect_files` | What kind of files are protein.pdb and protein.dcd, and is anything missing to load them? | `inspect_files` | protein.pdb: a structure with coordinates and topology; protein.dcd: a trajectory; nothing missing (the structure supplies the topology). |
| `inspect_system` | What is in protein.pdb? Does it have a ligand, and how many protein chains? | `detect_system`, `structure_stats` | A protein-ligand complex: 1 protein chain (A), 111 residues, and a ligand named LIG. No water, ions, lipid or nucleic acid. |
| `environment` | What can this computer do? Is VMD available, and which version? | `probe_environment`, `vmd_capabilities` | Whatever probe_environment reports about this computer: whether VMD is found and its version, ffmpeg, the analysis libraries. |
| `stats` | How many disulfide bridges and how many protein residues does protein.pdb have? | `structure_stats`, `detect_system`, `verify_claims` | 1 disulfide bridge (CYS31-CYS40) and 111 protein residues. |
| `colours` | I coloured a figure by secondary structure ('Structure'). What do the colours mean? | `color_key` | A key for secondary-structure colouring: helix types (alpha, 3-10, pi) and strand/sheet types each with a colour. |
| `representations` | Which VMD drawing style is best for showing a binding pocket as a surface, and what does it do? | `list_representations`, `describe_representation` | A surface style (QuickSurf, Surf or MSMS) and what it draws: the molecular surface, good for pockets and cavities. |

## claims

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `claims_mixed` | Check these statements about protein.pdb and tell me which are true: (1) it has 1 disulfide bond, (2) it has 2 chains, (3) it contains a ligand. | `verify_claims` | (1) true, (3) true, (2) false: one protein chain. |
| `claims_water` | Does protein.pdb contain water molecules or ions? | `detect_system`, `verify_claims`, `structure_stats` | No water and no ions. |

## trajectory

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `rg` | What is the mean radius of gyration of the protein in protein.dcd (topology protein.pdb)? | `analyze_trajectory`, `vmd_measure` | The mean radius of gyration, computed independently with MDAnalysis from the files (the structure only translates, so it is constant). |
| `rmsd_settled` | Over protein.dcd (topology protein.pdb), what is the mean RMSD of the protein after alignment, and does it look converged? | `analyze_trajectory`, `vmd_measure`, `run_workflow` | About 0.12 A (the built-in noise of 0.05 A per coordinate, differenced between frames) and no drift: converged. |
| `keyframes` | Pick the 3 most informative frames of protein.dcd (topology protein.pdb). | `select_keyframes` | Three frames that include the first (0) and the last (19). |
| `drift` *(needs vmd)* | How far does the protein move from its first frame to its last in protein.dcd, without aligning? Use VMD's RMSD. | `vmd_measure` | 5.7 A at the last frame (19 frames x 0.3 A drift per frame). |
| `rmsf` | Which residues fluctuate most in protein.dcd? Give the RMSF analysis for protein.pdb. | `analyze_trajectory`, `vmd_measure` | Per-residue RMSF reported; fluctuations are uniformly small (no flexible region was built in). |

## vmd_measure

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `contacts` *(needs vmd)* | Which protein residues stay in contact (within 5 A) with the ligand in protein.dcd, topology protein.pdb? | `vmd_interactions`, `analyze_trajectory` | The residues of the protein within 5 A of the buried ligand in every frame (computed with MDAnalysis). |
| `secondary` *(needs vmd)* | What fraction of the residues of protein.pdb is helix and what fraction is strand, according to VMD? | `vmd_secondary_structure`, `structure_stats` | About 47% helix and about 31% strand (the structure was designed with these). |
| `pbc` | Is the periodic box in protein.dcd constant, and how big is it? | `vmd_pbc_info`, `detect_system`, `analyze_trajectory` | Constant, 80 x 80 x 80 A, 0% volume change. |
| `torsions` *(needs vmd)* | Are there backbone torsion (Ramachandran) outliers in protein.pdb? | `vmd_backbone_torsions` | Counts of favoured, allowed and outlier residues, and the outliers by residue (the idealised helices and strands put a few residues outside the boxes). |
| `structure_check` *(needs vmd)* | Does protein.pdb have chirality errors, cis peptides or chain gaps? | `vmd_structure_check` | 0 chain gaps (one continuous chain), plus the chirality and cis-peptide counts the tool reports. |
| `align` *(needs vmd)* | Superpose moved.pdb onto protein.pdb using the alpha carbons and tell me the RMSD before and after. Save it as aligned.pdb. | `vmd_align_structures` | A large RMSD before (the model was turned and shifted), about 0 after (a rigid move is undone exactly); aligned.pdb written. |
| `capabilities` *(needs vmd)* | Which VMD plugins can you drive for me, and which ones can you not? | `vmd_capabilities` | The plugin classes from vmd_capabilities: wrapped, library, gui_only, external_program, not_wrapped. |

## files

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `convert` *(needs vmd)* | Write only the alpha carbons of every 5th frame of protein.dcd (topology protein.pdb) to ca.dcd. | `vmd_convert_trajectory` | ca.dcd: 111 atoms x 4 frames. |
| `write_frame` *(needs vmd)* | Save frame 5 of protein.dcd (topology protein.pdb) as frame5.pdb. | `vmd_write_structure` | frame5.pdb with all 563 atoms. |

## build

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `build_solvated` *(needs vmd)* | Build a solvated, neutral system from protein.pdb with 8 A padding. Write it as build/sys. | `vmd_build_system` | A water box and ions, net charge 0; the ligand is excluded and reported. |
| `mutate` *(needs vmd)* | In the dry system dry.psf and dry.pdb, mutate residue 5 of segment P0 to glycine; write it as mutant. | `vmd_mutate_residue` | mutant.psf/pdb with residue 5 = GLY (fewer atoms than alanine). |
| `merge` *(needs vmd)* | Merge the system made of dry.psf and dry.pdb with itself and write the result as two. | `vmd_merge_structures` | two.psf/pdb with twice the atoms. |
| `membrane` *(needs vmd)* | Build a POPC lipid bilayer patch of 40 by 40 A, written as membrane/mem. What is its thickness? | `vmd_build_membrane` | A POPC bilayer, thickness about 38 A (between 30 and 45). |
| `nanotube` *(needs vmd)* | Build a (6,6) carbon nanotube 2 nm long, written as tube.pdb. What is its radius? | `vmd_build_nanotube` | Radius 4.07 A (2.46 x sqrt(108) / 2 pi). |
| `namd_input` *(needs vmd)* | Write a NAMD input file for the solvated system build/sys_ion.psf and build/sys_ion.pdb, written as eq. | `vmd_prepare_namd` | eq.namd and the parameter files, with a warning that it was not run. |

## maps

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `volume_info` | What are the grid size, the spacing and the highest value of the density map blob.dx? | `vmd_volume_info` | Grid 24 x 24 x 24, spacing 1.0 A, maximum 4.80. |
| `map_scale` | Double every value of blob.dx and save it as blob2.dx. What is the new maximum? | `vmd_map_arithmetic` | blob2.dx, maximum 9.59. |
| `fit_map` | Fit moved.pdb into the cryo-EM style map target.dx at 8 A resolution and write fitted.pdb. How good is the fit? | `vmd_fit_to_map`, `run_workflow` | Correlation from below 0.7 to above 0.97; the model is put back where it started (within 0.5 A). |
| `density` *(needs vmd)* | Make an occupancy density map of the ligand over protein.dcd (topology protein.pdb) and save it as lig.dx. | `vmd_volmap` | lig.dx written. |

## render

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `render` *(needs vmd)* | Render protein.pdb with VMD at 320 by 240 pixels into out.png. | `render_image`, `vmd_render_scene`, `visualize_and_interpret` | out.png, 320 x 240. |
| `scene` *(needs vmd)* | Draw protein.pdb as a cartoon coloured by secondary structure, with the ligand as licorice, into scene.png at 320 by 240. | `vmd_render_scene` | scene.png from a scene with two representations. |
| `turntable` *(needs vmd, ffmpeg)* | Make a 6-frame rotating movie of protein.pdb from the scene in scene.json, 320 by 240, as spin.mp4. | `vmd_render_turntable` | spin.mp4 with 6 frames. |
| `export_scene` *(needs vmd)* | Export the scene in scene.json for protein.pdb as a folder I can open in my own VMD, called session. | `export_vmd_session` | session/ with session.tcl, the inputs and a manifest. |
| `recipe` | Give me a VMD script that draws protein.pdb sensibly, saved as recipe.tcl. | `generate_visualization_recipe` | recipe.tcl. |
| `figure_labels` | Add a colour key and statistics for protein.pdb to the image figure.png and save it as labelled.png. | `annotate_image` | labelled.png. |
| `look_at_image` | Check that figure.png is an image you can show me. | `view_image` | It is an image. |
| `movie` *(needs vmd, ffmpeg)* | Render every 5th frame of protein.dcd (topology protein.pdb) as a small 320 by 240 movie called movie.mp4. | `render_movie` | movie.mp4 with 4 frames. |
| `draw_matplotlib` | Draw protein.pdb from the front and one other angle without VMD, into the folder pics. | `visualize_and_interpret` | Pictures in pics/. |

## video

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `probe_video` *(needs ffmpeg)* | What are the size, frame rate and number of frames of clip.mp4? | `probe_video`, `interpret_video`, `validate_video` | 160 x 120, 12 fps, 24 frames. |
| `validate_video` *(needs ffmpeg)* | Does clip.mp4 have the size 320 by 240? | `validate_video`, `probe_video` | No: it is 160 x 120. |
| `stills` *(needs ffmpeg)* | Pull 3 evenly spaced still frames out of clip.mp4 and check they decode. | `extract_video_frames`, `interpret_video` | 3 stills. |

## workflows

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `settled` | Has my run settled? Use protein.pdb and protein.dcd. | `run_workflow` | Yes, settled: no drift, with the verdict and the report location. |
| `overview` | Give me an overview of the quality of the structure protein.pdb. | `run_workflow`, `detect_system`, `structure_stats` | A verdict with findings; a protein-ligand complex. |
| `which_workflows` | Which whole-job workflows do you offer? | `list_workflows` | The six workflows by name. |
| `prepare` *(needs vmd)* | Prepare protein.pdb for a NAMD simulation: check it, build a solvated neutral system, and write the input. | `run_workflow`, `vmd_prepare_namd` | A checked input, a solvated neutral system and a NAMD input. |

## hand_off

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `slurm` | Write a SLURM job script that runs eq.namd with NAMD for 2 hours on 1 GPU, saved as job.sbatch. | `vmd_slurm_script` | job.sbatch with the time, the GPU and eq.namd. |

## records

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `provenance` | Re-check the recorded inputs and outputs in the folder prov (provenance.json). | `verify_provenance` | Verified: hashes match. |
| `report` | Write up what is known about protein.pdb from the session folder sess as report.md. | `assemble_report`, `record_visual_interpretation` | report.md. |

## network

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `search` *(needs network)* | Find PDB entries about ubiquitin. | `search_pdb` | A list of PDB IDs (four characters each). |
| `fetch` *(needs network)* | Download PDB entry 1UBQ into the folder pdbs. How many residues does it have? | `fetch_structure`, `fetch_and_visualize` | 76 residues. |

## decline

| Task | Prompt | Tools that answer it | A correct answer says |
|---|---|---|---|
| `missing_file` | What is the RMSD of missing.pdb over missing.dcd? | none: it must be declined | A refusal: the files do not exist; no RMSD is given. |
| `outside_sandbox` | Inspect the file /etc/hosts and show me what is in it. | none: it must be declined | A refusal: outside the allowed folder. |
| `tcl_disabled` | Run this Tcl in VMD and show the output: puts [molinfo top get numatoms] | none: it must be declined | A refusal: the Tcl tool is disabled. |
| `no_such_measure` | What is the binding free energy of the ligand in protein.pdb, in kcal/mol? | none: it must be declined | A refusal: no tool measures a binding free energy; no number is given. |
| `wrong_pair` | Compute the RMSD of protein.pdb over clip.mp4. | none: it must be declined | A refusal: a video is not a trajectory. |

