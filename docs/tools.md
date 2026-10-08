# The 53 tools

Everything vmd-agent can do is a **tool**: a plain Python function with a JSON description, in [`toolset.py`](../src/vmd_agent/toolset.py).
The chat gives them to the model, the [MCP server](mcp.md) gives them to an AI app, the command line runs them as commands, the
web page runs them for you, and the [tool test set](tool-test-set.md) runs every one of them on data whose answers are known.
They are the same functions in every case, so a number does not depend on how you asked for it.

There are **53** in three groups. The count is checked by a test, so this page cannot drift from the code:

| Group | Count | What they are | Needs VMD? |
|---|---|---|---|
| **Original** (`CORE_TOOLS`) | 27 | The toolkit as first designed: look at files, describe a system, draw it, measure a trajectory, check claims, handle videos and records. | no, except the ones that draw with VMD |
| **Drive VMD itself** | 24 | VMD's own `measure` commands and plugins, system building, density maps, scenes, hand-offs to NAMD and a cluster. Also `vmd-agent vmd ...` on the command line. | yes, except `vmd_fit_to_map`, `vmd_map_arithmetic`, `vmd_volume_info` and `vmd_slurm_script`, which are NumPy or plain text |
| **Whole jobs** | 2 | List the workflows, run one: several tools in a fixed order, graded findings, a report. | some steps |

Older notes and one help string said "47 tools (27 plus 20)". That was the count before the later VMD tools and the two workflow tools
were added: 27 + 24 + 2 = 53.

## Does the model see all 53 at once?

**By default, yes.** `vmd-agent chat` and the web page send the description of every tool the model may use with *every* question, and with all 53
that is about 38,000 characters, roughly **9,500 tokens**, before the model has read your question. The short sets are about half that:

| `--tools` | Tools | Descriptions sent with every question |
|---|---|---|
| `all` (default) | 53 | about 9,500 tokens |
| `core` | 27 | about 4,400 tokens |
| `vmd` | 28 | about 5,300 tokens |
| `auto` | the ones that fit the question, plus `offer_tools` | well under `all` |

(`vmd-agent tools --group all --size` measures this on your copy; 4 characters per token is a rough rule.) This matters for two reasons:

* **Context.** The private Ollama keeps a 16,384-token context, so the descriptions take more than half of it before anything else is said. A model with
  a small context, or a small model that picks worse from a long list, does better with `--tools core` or `--tools vmd`.
* **Speed.** A model reads those tokens on every call, so the first answer is slower with all 53.

**`--tools auto`** offers only the tools that fit each question, plus one more, `offer_tools`, which lets the model ask for another group when it needs one:

* The router ([`routing.py`](../src/vmd_agent/routing.py)) reads the question's wording and the kinds of files it names, adds the tools of each group it mentions (trajectory, interactions, checks,
  files, build, maps, render, video, records, network, ...) to a small base set (look at files, describe a system, check a statement, run a whole job), and so usually offers well under half of the tools.
  A question that matches nothing gets a wider set, never an empty menu.
* **It is keyword matching, so it misses.** Questions worded differently from what its vocabulary expects can reach the model without the tool that would answer them (the tests keep two sets of such paraphrases, and every miss found was added as a new question). That is why `offer_tools` exists: a model that needs a tool it was not given asks for its group, and a model that calls a real tool it was not offered is allowed it (the agent says so). If
  your model does not use `offer_tools`, `--tools all` is the safe choice.
* Whether `auto` is better than `all` for your model is a measurement, not a given: run the [model benchmark](model-benchmark.md) with each (`--tools all`, then `--tools auto`) and compare; the summary puts
  both side by side.

The web page has a "chat tools" menu in its status bar to switch between them without restarting. Which set suits which model is something the
[model benchmark](model-benchmark.md) can tell you: run it with `--tools all`, then `--tools core`, and compare. Nothing here chooses a subset for
you per question yet; the chat only points the model at a whole-job workflow when the question clearly matches one.

## Who gets which tools

| Where | Tools | Why |
|---|---|---|
| The MCP server and `vmd-agent tools` | all 53 | an AI app can handle a long list |
| `vmd-agent chat` and the web page | all 53 at once by default; `--tools core` gives the original 27, `--tools vmd` gives 28: the 24, the 2 workflow tools, `inspect_files` and `probe_environment` | a small local model chooses better from a shorter list |
| The benchmark's arms (`vmd-agent bench agent-run`) | **their own small sets**: `vmd_agent` 10, `vmd_agent_no_verify` 9, `vmd_agent_no_keyframes` 9, `python_mdanalysis` 4, `vmd_plain` 4 | an arm is a controlled experiment: what does the toolkit add over a model that writes its own code? Each arm also gets `list_files`, `read_text_file` and `submit_answer`, which exist only inside the benchmark |

The benchmark's tools are separate on purpose: they are confined to one task's folder, they have no way to draw or download, and
`submit_answer` ends the task. They are the "internal" tools of the research benchmark, not part of the 53.

## The original 27

| Tool | What it does |
|---|---|
| `probe_environment` | Report what this machine can do: VMD/Tachyon/ffmpeg, analysis libraries and which renderers (vmd, matplotlib) are available |
| `inspect_files` | START HERE for any file in the data folder: says what each local file is (structure, trajectory, map, image) and which companion file is missing (e.g. a PSF for a DCD) |
| `detect_system` | Load a LOCAL structure (and optional trajectory) and classify its components and overall type: protein chains, ligands, water, ions, lipids, nucleic acids, and the type of system |
| `generate_visualization_recipe` | Detect the system and emit a tailored VMD/Tcl visualization recipe |
| `structure_stats` | Count bonds, links and interactions for annotating a figure: total bonds and bonds by element pair, disulfide bridges, hydrogen bonds (angle-based when hydrogens exist), salt bridges, chains, elements and DSSP secondary-structure content |
| `color_key` | Explain what each colour in a render means, for one VMD colouring method ('Structure', 'Chain', 'Name'/'Element', 'ResType', 'Beta', 'ColorID') |
| `annotate_image` | Draw the colour key and structure statistics onto an existing rendered image, making the figure self-describing |
| `list_representations` | Catalogue of VMD graphical representations, colour methods and materials |
| `describe_representation` | Full detail on one representation: what it draws, what it is best for, its VMD command with default parameters, and its limitations |
| `search_pdb` | Find PDB IDs by keyword/molecule name (e.g. 'hemoglobin', 'CRISPR Cas9') |
| `fetch_structure` | Download a structure from the web to a local file |
| `fetch_and_visualize` | ONE CALL: download a protein from the PDB (or AlphaFold/URL), pick the best representation automatically, render it from several viewpoints, and return a grounded interpretation package with the saved image paths |
| `visualize_and_interpret` | AUTO pipeline: inspect -> detect -> recipe -> render multi-view images -> return a grounded interpretation package (legend + what-to-look-for + preliminary explanation + image paths + provenance record) |
| `render_image` | Render one publication image via headless VMD+Tachyon |
| `render_movie` | Render a trajectory to an MP4 via VMD+Tachyon+ffmpeg in ONE VMD session with a fixed camera |
| `run_vmd_tcl` | Run Tcl in headless VMD (escape hatch for VMD-only analyses) |
| `analyze_trajectory` | Run rmsd/rmsf/rgyr/hbonds/contacts/distance/sasa/density/convergence on a trajectory |
| `select_keyframes` | Pick the k most informative trajectory frames by detecting change points in RMSD, Rg (and contacts / COM distance when sel2 is given), instead of sampling uniformly |
| `verify_claims` | Check statements about the system against measurements |
| `extract_video_frames` | Extract evenly-spaced stills from a VMD movie/GIF for interpretation |
| `probe_video` | Read a video's real codec/geometry/timing metadata and prove it decodes |
| `validate_video` | Verify an encoded video decodes and matches the requested settings |
| `interpret_video` | ONE CALL: verify a video and return inspectable stills for interpretation |
| `view_image` | Check that a file is an image the agent can be shown (render, frame or analysis plot) and return its path |
| `record_visual_interpretation` | Store the agent's visual interpretation into the session for the report |
| `assemble_report` | Compose the full scientific report from everything stored in a session |
| `verify_provenance` | Re-hash the inputs/outputs recorded in a provenance.json and report any that changed, so a figure or number can be tied to the exact bytes and software that produced it |

## The 24 that drive VMD itself

Described with examples in [Driving VMD itself](vmd.md#6-drive-vmd-itself).

| Tool | What it does |
|---|---|
| `vmd_capabilities` | List the plugins of the installed VMD by status: wrapped by this toolkit (with the tool that does it), library, window-only, needing another program (NAMD, APBS, ...), or not wrapped yet. verbose=true adds every plugin's version and the file formats |
| `vmd_measure` | Run one of VMD's own `measure` computations over a trajectory. kind: rgyr, sasa, center, minmax, inertia, rmsd (fit to reference_frame when align), rmsf, distance (selection to selection2), angle (3 single atoms), dihedral (4 single atoms), contacts, hbonds, gofr (selection2 around selection) or cluster (frames by RMSD) |
| `vmd_interactions` | Hydrogen bonds, salt bridges or atom contacts between selections over a trajectory, as persistence: which pairs exist and in what fraction of frames. kind: hbonds (default cutoff 3.0 A), salt_bridges (4.0 A), contacts (4.0 A, needs selection2) |
| `vmd_secondary_structure` | Secondary structure of every residue in every frame, computed by VMD (STRIDE): helix/strand fractions per frame and per-residue persistence (what VMD's Timeline window shows) |
| `vmd_backbone_torsions` | phi/psi angles of one frame from VMD, classified into coarse Ramachandran regions; lists outlier residues |
| `vmd_structure_check` | VMD's structurecheck plugin on one frame: chirality errors, cis peptide bonds and chain gaps |
| `vmd_align_structures` | Superpose one structure onto another with VMD and report the RMSD before and after; optionally write the moved structure |
| `vmd_pbc_info` | Unit-cell lengths and angles per frame (VMD pbctools): is there a periodic box, is it orthorhombic, does its volume drift (a sign of an unequilibrated or wrongly-read run) |
| `vmd_convert_trajectory` | Write a (sub)trajectory in another format, choosing atoms (selection), frames (first/last/step), optionally wrapping atoms into the unit cell around center_selection and/or fitting every frame to the first |
| `vmd_write_structure` | Write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin |
| `vmd_volmap` | Compute a 3-D map with VMD volmap and write it as OpenDX. kind: density, occupancy, distance, mask, or electrostatic (PME potential of the whole system; needs a PSF) |
| `vmd_volume_info` | What a density map file holds (OpenDX, CCP4/MRC, Gaussian cube, Situs): grid, spacing, range, integral and suggested isosurface levels |
| `vmd_build_system` | Use ONLY when the user asks to build, solvate or ionize a system for a simulation |
| `vmd_mutate_residue` | Mutate one residue in a PSF/PDB pair (VMD mutator plugin), e.g. segid P0, resid 6, new_resname ALA |
| `vmd_merge_structures` | Combine two PSF/PDB systems into one (VMD topotools); warns when segment names collide |
| `vmd_build_membrane` | Build a POPC or POPE lipid bilayer patch (VMD membrane plugin, CHARMM): PSF/PDB, lipids per leaflet and the phosphate-to-phosphate thickness |
| `vmd_build_nanotube` | Build a single-wall nanotube of chirality (n, m), carbon (C-C) or boron nitride (B-N), as a PDB; the radius is checked against the analytic value |
| `vmd_render_scene` | Render a picture of a scene you describe, with VMD + Tachyon, using the user's own files as named. scene_spec: {reps: [{selection, style, color, material, params}], isosurfaces: [{file, isovalue, color, style: solid/wireframe/points}], background, frame, rotate: [[axis, degrees]], zoom, projection, axes, depthcue, shadows, ambient_occlusion} |
| `export_vmd_session` | Use when the user wants to open or keep a scene in their own VMD. topology and trajectory are the user's own files exactly as named (for example protein.pdb and protein.dcd); do not build or convert anything first |
| `vmd_render_turntable` | A rotating-view movie of a scene (same scene_spec as vmd_render_scene): the camera turns `degrees` about `axis` over `frames` frames, rendered with VMD + Tachyon and encoded with ffmpeg |
| `vmd_fit_to_map` | Cryo-EM: move a model as a rigid body to where it fits a density map (OpenDX, CCP4/MRC, cube, Situs) best, and report the map-model correlation before and after. resolution is the blur in angstrom of a map made from the model |
| `vmd_map_arithmetic` | Combine or clean density maps and write OpenDX. op: add, subtract, multiply, average, mask (A where B >= value), threshold, clamp, smooth (blur of `value` angstrom), normalize, scale |
| `vmd_prepare_namd` | Write a NAMD input file (CHARMM36, PME, rigid bonds, minimisation then equilibration at `temperature` K, npt or nvt) for a solvated PSF/PDB such as vmd_build_system makes; the box is read from the coordinates and the parameter files are copied beside it |
| `vmd_slurm_script` | Write a SLURM batch script for a cluster. kind: namd (command is a .namd file), vmd (a Tcl script, run headless) or shell (any command line) |

## The 2 whole-job tools

Described in [Whole jobs](workflows.md).

| Tool | What it does |
|---|---|
| `list_workflows` | The named multi-step workflows (each runs several tools in a fixed order, reports findings and writes a report): what each does, which files it needs, and whether it needs VMD |
| `run_workflow` | Run a whole job on the user's files, in one call |
