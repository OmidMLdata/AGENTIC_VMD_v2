# The tool library

Everything vmd-agent can do is a **tool**: one function that does one thing, with a JSON description, in [`toolset.py`](../../src/vmd_agent/toolset.py). There is **one list of 57 tools**, in eleven groups. The chat gives them to
the model, the [MCP server](mcp.md) gives them to an AI app, `vmd-agent tool NAME` runs one from a terminal, the web page runs them for you, and the
[tool test set](../benchmarks/tool-test-set.md) runs every one of them on data whose answers are known. They are the same functions in every case, so a number does not depend on how you asked for it.
The count and the groups are checked by a test, so this page cannot drift from the code.

**Tools and workflows are different things.** A tool does one thing. A [workflow](workflows.md) is a layer above the tools: it runs several of them in a fixed order, grades what they find and writes a
report. There are eleven, and the agent reaches them through one call, `run_workflow` (with no name it lists them). They are not counted among the 57.

The last column says whether a tool needs VMD installed. Tools that do not need it always work; a tool that needs it says so plainly when VMD is missing. Tools that run VMD save the exact Tcl they ran
(`reproduce_script` in the result), so you can repeat the step in your own VMD.

### Look at this computer and your files

What is here, and what is in it.

| Tool | What it does | Needs |
|---|---|---|
| `probe_environment` | What this computer can do: VMD, ffmpeg, drawing backends, libraries (--plugins: which of VMD's plugins this toolkit can drive) | — |
| `inspect_files` | Say what kind of files these are and what is missing (a trajectory without its structure ...) | — |
| `detect_system` | Find what is in a system: protein, ligand, water, ions, lipids, nucleic acids | — |
| `structure_stats` | Bond and link counts for a structure: disulfides, hydrogen bonds, bonds by element pair | — |

### Get a structure

From the PDB, AlphaFold or a web address.

| Tool | What it does | Needs |
|---|---|---|
| `search_pdb` | Find PDB IDs by keyword | — |
| `fetch_structure` | Download a structure (PDB ID, UniProt accession for AlphaFold, or a URL) | — |

### Draw

Pictures, movies and scenes.

| Tool | What it does | Needs |
|---|---|---|
| `visualize_and_interpret` | Draw your file from several angles and describe it (VMD if installed, else the built-in drawing) | VMD, or the built-in drawing |
| `render_image` | Draw one image with VMD, of a system or of a scene you describe (--scene) | VMD |
| `render_movie` | A movie with VMD: a trajectory played, or a rotating view of a scene (--spin) | VMD |
| `annotate_image` | Draw the colour key and statistics onto an image | — |
| `view_image` | Check that a file is an image and give its path | — |
| `generate_visualization_recipe` | Write a VMD script that draws this system sensibly | — |
| `list_representations` | VMD drawing styles and when to use them (--name QuickSurf: one in detail) | — |
| `color_key` | What each colour of a colouring method means | — |
| `export_session` | Write a folder you can open in your own VMD (session.tcl, inputs, checksums) | VMD |
| `run_tcl` | Run Tcl in headless VMD (off unless VMD_AGENT_ENABLE_TCL=1) | VMD |

### Control your VMD window

Drive the VMD you can see: what it loads, draws, shows and answers.

| Tool | What it does | Needs |
|---|---|---|
| `window_open` | Open a VMD window (or reuse the open one) that the window_* tools control | VMD |
| `window_load` | Load a structure, trajectory or density map into the VMD window | VMD |
| `window_molecules` | List, show, hide, rename or delete the molecules in the VMD window | VMD |
| `window_representation` | List, add, change or delete how the VMD window draws a molecule (selection, style, color) | VMD |
| `window_display` | Set the VMD window's projection, background, axes, depth cueing, shadows | VMD |
| `window_view` | Rotate, zoom, move, centre, save or restore the view in the VMD window | VMD |
| `window_animate` | Go to a frame, play, or set the style and speed in the VMD window | VMD |
| `window_query` | Ask the VMD window what a selection holds, or measure a bond, angle, dihedral or SASA | VMD |
| `window_snapshot` | A picture of what the VMD window shows right now (VMD's own drawing) | VMD |
| `window_scene` | Set up a whole scene in the VMD window from a description (representations, isosurfaces, view) | VMD |
| `window_visualize` | Draw a system in the VMD window the way the recipe would (what it holds, drawn to suit), with a legend | VMD |
| `window_movie` | A movie of the VMD window: the trajectory played, or a turntable | VMD |
| `window_save` | Save the VMD window's state as a .vmd file that VMD opens again | VMD |

### Measure a simulation

Size, shape, flexibility, convergence, box.

| Tool | What it does | Needs |
|---|---|---|
| `analyze_trajectory` | Measure a simulation: RMSD, flexibility, size, contacts, hydrogen bonds, SASA, convergence | — |
| `measure_with_vmd` | VMD's own measure commands over a trajectory: radius of gyration, SASA, RMSD, RMSF, distances, g(r), clusters ... | VMD |
| `select_keyframes` | Pick the most informative frames of a trajectory | — |
| `periodic_box` | Periodic box per frame: is there one, and does its volume drift | VMD |

### Interactions and structure quality

Who touches whom, secondary structure, geometry.

| Tool | What it does | Needs |
|---|---|---|
| `find_interactions` | Hydrogen bonds, salt bridges or contacts, as how often each pair is present | VMD |
| `secondary_structure` | Secondary structure of every residue in every frame (what the Timeline window shows) | VMD |
| `backbone_torsions` | Phi/psi angles and coarse Ramachandran regions of one frame | VMD |
| `check_structure` | Chirality errors, cis peptides and chain gaps (the structurecheck plugin) | VMD |
| `align_structures` | Superpose one structure on another and report the RMSD | VMD |

### Convert and write files

Other formats, fewer atoms or frames.

| Tool | What it does | Needs |
|---|---|---|
| `convert_trajectory` | Write a trajectory in another format, or just some atoms or frames, wrapped or fitted | VMD |
| `write_structure` | Write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin | VMD |

### Density maps (cryo-EM and more)

Make, read, combine and fit maps.

| Tool | What it does | Needs |
|---|---|---|
| `make_map` | Make a density, occupancy, distance, mask or electrostatic-potential map | VMD |
| `inspect_map` | What is in a density map file (dx, mrc, ccp4, cube, situs): grid, range, suggested isosurface levels | — |
| `combine_maps` | Add, subtract, mask, smooth, threshold or normalise density maps | — |
| `fit_to_map` | Cryo-EM: fit a model into a density map as a rigid body, and report the correlation before and after | — |

### Build and prepare a simulation

Systems, mutations, membranes, nanotubes, input files.

| Tool | What it does | Needs |
|---|---|---|
| `build_system` | PDB to a solvated, neutral CHARMM36 system (psfgen, solvate, autoionize) | VMD |
| `mutate_residue` | Mutate one residue of a PSF/PDB pair | VMD |
| `merge_structures` | Combine two PSF/PDB systems into one | VMD |
| `build_membrane` | Build a POPC or POPE lipid bilayer patch | VMD |
| `build_nanotube` | Build a carbon or boron-nitride nanotube | VMD |
| `prepare_namd` | Write a NAMD input file (CHARMM36, PME, minimise then equilibrate) for a built system | — |
| `write_slurm_script` | Write a SLURM job script for a cluster (NAMD, a VMD script, or any command) | — |

### Video

Check and sample an encoded movie.

| Tool | What it does | Needs |
|---|---|---|
| `probe_video` | A video's real size, frame rate, length and codec, proof that it decodes, and (--expect-width ...) a check against what was asked for | — |
| `interpret_video` | Verify a video and pull evenly spaced stills out of it for a look | — |

### Evidence and records

Check claims, keep provenance, write the report.

| Tool | What it does | Needs |
|---|---|---|
| `verify_claims` | Check statements against measurements: supported, contradicted or unverifiable | — |
| `record_visual_interpretation` | Keep what was seen in a picture or video in the session, for the report | — |
| `assemble_report` | Write the report from everything a session recorded | — |
| `verify_provenance` | Re-hash the recorded inputs and outputs of a run and say what changed | — |

## From a terminal

```bash
vmd-agent tools                                   # the list above, in groups
vmd-agent tool NAME --help                        # one tool: its flags, an example
vmd-agent tool measure_with_vmd run.pdb run.dcd --kind rgyr --step 10
```

A tool's required files are positional, its outputs are `--out`, its options are `--flags` made from the same parameters the model sees, and a result is JSON. There is no second set of commands to learn:
the tool, the model's call and the command are one thing.

## Does the model see all of them at once?

**Not by default, because it would not fit.** Sending the description of every tool with *every* question takes about 49,000 characters, roughly **12,200 tokens**, before the model has read your question, and
the private Ollama keeps a 16,384-token context. So the chat and the web page offer only the tools that fit each question (`--tools auto`, the default), and `--tools all` sends everything.

| `--tools` | Offered | Descriptions sent with every question |
|---|---|---|
| `auto` (default) | the ones that fit the question, plus `offer_tools` | about 2,500 to 6,000 tokens, depending on the question |
| `all` | the 57 tools and `run_workflow` | about 12,200 tokens |

(`vmd-agent tools --size` measures this on your copy; 4 characters per token is a rough rule.) This matters for two reasons:

* **Context.** The private Ollama keeps a 16,384-token context, so the descriptions take more than half of it before anything else is said. A model with a small context, or a small model that picks worse from
  a long list, does better with `--tools auto`.
* **Speed.** A model reads those tokens on every call, so the first answer is slower with all of them.

**`--tools auto`** offers only the tools that fit each question, plus one more, `offer_tools`, which lets the model ask for another group when it needs one:

* The router ([`routing.py`](../../src/vmd_agent/routing.py)) reads the question's wording and the kinds of files it names, adds the tools of each group it mentions (trajectory, interactions, checks,
  files, build, maps, render, video, records, network, ...) to a small base set (look at files, describe a system, check a statement, run a whole job), and so usually offers well under half of the tools.
  A question that matches nothing gets a wider set, never an empty menu.
* **It is keyword matching, so it misses.** Questions worded differently from what its vocabulary expects can reach the model without the tool that would answer them (the tests keep two sets of such
  paraphrases, and every miss found was added as a new question). That is why `offer_tools` exists: a model that needs a tool it was not given asks for its group, and a model that calls a real tool it was
  not offered is allowed it (the agent says so). If your model does not use `offer_tools`, `--tools all` is the safe choice.
* Whether `auto` is better than `all` for your model is a measurement, not a given: run the [model benchmark](../benchmarks/model-benchmark.md) with each (`--tools all`, then `--tools auto`) and compare;
  the summary puts both side by side.

The web page has a "chat tools" menu in its status bar to switch between them without restarting.

## Who gets which tools

| Where | Tools | Why |
|---|---|---|
| The MCP server and `vmd-agent tools` | all of them | an AI app can handle a long list |
| `vmd-agent chat` and the web page | the ones that fit each question by default (`--tools auto`); `--tools all` for every tool | a small local model chooses better from a shorter list, and the full list takes most of its context |
| The benchmark's arms (`vmd-agent bench agent-run`) | **their own small sets**: `vmd_agent` 10, `vmd_agent_no_verify` 9, `vmd_agent_no_keyframes` 9, `python_mdanalysis` 4, `vmd_plain` 4 | an arm is a controlled experiment: what does the toolkit add over a model that writes its own code? Each arm also gets `list_files`, `read_text_file` and `submit_answer`, which exist only inside the benchmark |

The benchmark's tools are separate on purpose: they are confined to one task's folder, they have no way to draw or download, and `submit_answer` ends the task. They are the "internal" tools of the
research benchmark, not part of the library.
