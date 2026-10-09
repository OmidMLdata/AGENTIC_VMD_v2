# vmd-agent

You ask a question about a molecular system in ordinary words, and vmd-agent answers it by running real measurements. What's in this file? Has my run settled? Is this statement true? It uses
[VMD](https://www.ks.uiuc.edu/Research/vmd/) for the measuring and the drawing. A language model sits in the middle: it decides which tools to run, reads what they return, and writes the answer. Any number
in that answer has to have come from a tool, and if one didn't, it gets sent back or flagged.

By default the model is a free, open-source one running on your own computer, so nothing leaves your machine. If you'd rather have Claude Code or Claude Desktop do the thinking, you can pick that in setup;
vmd-agent then just hands them its tools.

You need a Mac, Windows or Linux computer and an internet connection. VMD itself is free from UIUC and worth having, because pictures and many of the tools use it. You don't need Python, Git, Docker or an account.

## Why use it

* **Answers you can check.** Every number in an answer comes from a tool. A statement about your system, such as "76 residues and the radius of gyration stays below 13 Å", comes back supported, contradicted or "can't tell", with the evidence.
* **Statistics on top of VMD.** Convergence tests with effective sample sizes, careful wording ("no drift detected" is not "converged"), and key frames chosen where something changes. Where it matters, VMD and the toolkit each measure and the report says whether they agree.
* **Everything can be repeated.** Each VMD step saves its exact Tcl, and a whole-job report records input checksums, methods and caveats.
* **A safe way to let a model near VMD.** A fixed set of validated commands, a files-folder sandbox and a loopback-only link, with no raw Tcl or shell handed over.
* **One place for the whole toolbox,** from fetching and converting to building systems, fitting cryo-EM maps and writing NAMD and SLURM files, reachable from a web page, a chat, scripts and MCP clients.
* **A real VMD.** It drives the window you can see, and every picture is VMD's own.

More: [Why use vmd-agent](docs/guide/why.md).

## Install

Open a terminal (on a Mac, press `Cmd` + `Space` and type `Terminal`; on Windows, search the Start menu for `PowerShell`), paste one line, and answer a few questions.

Mac or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.ps1 | iex"
```

The installer puts the program in one folder (`~/vmd-agent`) and needs no administrator rights. Setup then finds VMD and starts it once to make sure it runs, asks for a files folder (the agent can only
see that folder), and asks who should answer your questions: a free model on your computer (recommended), an online service, Claude Code or Desktop, or nobody. Nothing big is downloaded without asking first.
The details are in [Install and set up](docs/guide/install.md).

If you'd rather keep everything, including the model, inside your project folder, `vmd-agent setup --home here` creates a `.vmd-agent` folder there and offers to move an existing model into it.
Git ignores that folder.

`vmd-agent doctor` shows what it found on your computer (system, memory, graphics card, VMD, Ollama) and what to do next.

## Using it

There are four ways in, and they all use the same tools.

* **The web page** (`vmd-agent ui`) is a remote control for a real VMD window. It's laid out like VMD, with a molecule list, a representations editor, animation controls and a console, and the picture in the
  middle is VMD's own. Alongside it you get the chat, a form for every tool, a tab for whole jobs, and a terminal for developers.
* **The menu** (`vmd-agent`) is a numbered list in plain words: look at a structure, analyse a simulation, check a statement.
* **The chat** (`vmd-agent chat`) is the same conversation in the terminal.
* **The command line** (`vmd-agent tool NAME ...`) runs any single tool without a model, which is handy for scripts.

Put your structure and trajectory files in your files folder and ask for them by name: *"What is in protein.pdb?"*, *"Has my run settled? Use run.psf and run.dcd."*, *"Which salt bridges persist?"*,
*"Build a solvated, neutral system from 1ubq.pdb."*

```bash
vmd-agent tools                                                          # the library, in groups
vmd-agent tool fetch_structure 1UBQ --out pdbs                           # download a structure
vmd-agent tool analyze_trajectory run.psf run.dcd --analyses rmsd rgyr   # measure a simulation
vmd-agent tool verify_claims my.pdb "It has 4 disulfide bridges"         # check a statement against the data
vmd-agent tool measure_with_vmd run.pdb run.dcd --kind rgyr              # one of VMD's own measurements
vmd-agent workflow equilibration_check run.psf run.dcd                   # a whole job, with a report
```

### Driving your VMD window

The page opens a VMD window for you when it loads (if VMD is installed; `--no-vmd` turns that off). The agent can work the VMD window you're looking at: load a system, draw it as a cartoon or a surface, colour it, zoom to the ligand, step through frames, ask what a selection contains, take a picture. Every
picture and number comes from VMD. A small script inside VMD listens on your own machine only and accepts a short, fixed list of commands, none of which runs arbitrary Tcl. Many analysis tools also take
`show_in_window`, which draws their result in that window afterwards (the salt bridges as licorice, a fitted model inside its map, and so on). [How it works](docs/guide/window.md).

## The tools

There are **57 tools** in eleven groups. A tool does one thing, and each one is available to the chat, to MCP clients and to `vmd-agent tool NAME`. [Every tool, what it does, and whether it needs VMD](docs/guide/tools.md).

| Group | Tools |
|---|---|
| **Look at this computer and your files** (4) | `probe_environment` · `inspect_files` · `detect_system` · `structure_stats` |
| **Get a structure** (2) | `search_pdb` · `fetch_structure` |
| **Draw** (10) | `visualize_and_interpret` · `render_image` · `render_movie` · `annotate_image` · `view_image` · `generate_visualization_recipe` · `list_representations` · `color_key` · `export_session` · `run_tcl` |
| **Control your VMD window** (13) | `window_open` · `window_load` · `window_molecules` · `window_representation` · `window_display` · `window_view` · `window_animate` · `window_query` · `window_snapshot` · `window_scene` · `window_visualize` · `window_movie` · `window_save` |
| **Measure a simulation** (4) | `analyze_trajectory` · `measure_with_vmd` · `select_keyframes` · `periodic_box` |
| **Interactions and structure quality** (5) | `find_interactions` · `secondary_structure` · `backbone_torsions` · `check_structure` · `align_structures` |
| **Convert and write files** (2) | `convert_trajectory` · `write_structure` |
| **Density maps (cryo-EM and more)** (4) | `make_map` · `inspect_map` · `combine_maps` · `fit_to_map` |
| **Build and prepare a simulation** (7) | `build_system` · `mutate_residue` · `merge_structures` · `build_membrane` · `build_nanotube` · `prepare_namd` · `write_slurm_script` |
| **Video** (2) | `probe_video` · `interpret_video` |
| **Evidence and records** (4) | `verify_claims` · `record_visual_interpretation` · `assemble_report` · `verify_provenance` |

In plain terms, they cover:

* **Understanding a structure:** what it contains (chains, ligands, water, ions, lipids, nucleic acids), bonds, disulfides, hydrogen bonds, secondary structure, chirality and chain gaps, and pictures from several angles with a legend.
  Structures can come from your files, the PDB, AlphaFold or a URL.
* **Measuring a simulation:** RMSD, RMSF, radius of gyration, contacts, hydrogen bonds, distances, surface area and density, with tests for whether a run has converged, and keyframes picked from where something
  actually happens. You can also check a written statement against the data and get back supported, contradicted or "can't tell", with the evidence.
* **Running VMD itself:** its `measure` commands, trajectory conversion, density maps, solvated CHARMM36 systems, mutations, membranes, nanotubes, rendered scenes and movies, and NAMD and SLURM files. Each tool that
  runs VMD saves the exact Tcl it used, so you can repeat it in your own VMD. [More on VMD](docs/guide/vmd.md).
* **Videos and records:** read a video's real metadata, pull stills and map them back to simulation frames, re-check recorded hashes, and put a report together from a session.

## Whole jobs

A workflow isn't a tool. It runs several tools in a fixed order, grades what it finds (ok, note, warning, problem), gives a verdict, and writes `report.md` and `report.html` with the figures, every caveat the tools
raised, the SHA-256 of your input files and the Tcl of each VMD step. The agent reaches all six through one call, `run_workflow`; from a terminal it's `vmd-agent workflow NAME FILE ...`.
[Workflows](docs/guide/workflows.md).

| Workflow | Files | What it does |
|---|---|---|
| `structure_overview` | structure | what's in it and whether it's in good shape: composition, torsions, chirality, gaps, pictures |
| `equilibration_check` | topology, trajectory | has the run settled: RMSD and size convergence, periodic box, two engines compared |
| `interaction_report` | topology, trajectory | hydrogen bonds and salt bridges (and contacts with a partner group), as how often each is present |
| `compare_runs` | topology, two trajectories | RMSD, size and fluctuation of two runs side by side |
| `prepare_simulation` | structure | check the input, build a solvated neutral CHARMM36 system, write NAMD and SLURM files |
| `cryoem_fit` | model, map | fit a model into a cryo-EM map, with a picture and a session for VMD |

## How the agent works

One module runs the model, the tools and the checks, and every front end sits on top of it, so the chat, the web page and the benchmark behave alike.

* **Routing.** By default (`--tools auto`) the model is offered only the tools that fit your question, plus a way to ask for more. A small model's context is limited, and all 57 descriptions take most of it.
  `--tools all` offers everything. [Which tools a model sees](docs/guide/tools.md#does-the-model-see-all-of-them-at-once).
* **Argument repair.** If the model writes a number as text, `RMSD` instead of `rmsd`, or a file name without its folder, that's fixed when there's only one sensible reading, and the result says so.
* **The guard.** A data question answered without a tool is sent back once. An answer containing a number no tool returned is sent back once, then flagged. Requests that can't be answered are declined, not guessed.
* **Timing.** Every model call and every tool call shows how long it took.
* **MCP.** The same tools work as an MCP server for Claude Code, Claude Desktop or any other client. [MCP clients](docs/guide/mcp.md).

More in [the architecture notes](docs/reference/architecture.md#the-agent-and-what-surrounds-the-model).

## Choosing a model

`vmd-agent models` reads your computer (memory, graphics card) and says which of the suggested models fit, tight or too big, and which one it suggests first. If you said no to a download in setup, you can change your mind any time: `vmd-agent models --install`, or **Model > Download a model** in the web page. Nothing large is fetched without your yes.

Models differ a lot in how well they use tools. There's a built-in benchmark that gives a model 67 plain-language requests across 15 kinds of work (inspecting files, claims, trajectories, VMD measurements,
building, maps, rendering, driving the VMD window, video, whole jobs and requests that should be declined). Each task has a correct answer worked out from data built to have known properties, and a program grades it.
See [every prompt and its correct answer](docs/benchmarks/model-benchmark-tasks.md). The suggested models are listed in [Models](docs/guide/models.md).

```bash
vmd-agent bench models --list --reference          # every prompt and what a correct answer says
vmd-agent bench models --model granite4.1:8b       # one model on your local server
vmd-agent bench models --catalogue --pull          # every suggested model, one after another (downloaded into the private Ollama)
vmd-agent bench models --summarize                 # the comparison: success by model and by kind of work, seconds, tokens
vmd-agent bench tools                              # every tool on generated data with known answers
```

More: [the model benchmark](docs/benchmarks/model-benchmark.md) and [the tool test set](docs/benchmarks/tool-test-set.md).

## Safety

The agent can only read and write inside your files folder, and it can't touch its own settings folder at all. Tcl is never taken from a caller: each VMD command builds its script from validated values and
runs it headless, with a cleaned environment and a time limit. The free-form Tcl tool is off unless you switch it on. Downloads are limited to the sources you name, and the private model server is checked against its
published checksum before it runs. [Security](docs/reference/security.md).

## What's in this repository

```
src/vmd_agent/     the package: the agent, the tools, the VMD wrappers (vmdkit/), analysis, drawing, the web page, the benchmarks
install/           the one-line installers (install.sh for Mac and Linux, install.ps1 for Windows)
docker/            Dockerfile, compose files and helpers for the container routes
docs/              the manual: guide/ (using it), benchmarks/ (choosing a model), reference/ (architecture, methods, security, research), CHANGELOG and NOTICE
tests/             the test suite, laid out like the package
.github/           CI
```

## Documentation

[All the pages](docs/index.md): [Why use it](docs/guide/why.md) · [Install and set up](docs/guide/install.md) · [Ways to work](docs/guide/using.md) · [The command line](docs/guide/commands.md) · [Models](docs/guide/models.md) ·
[Whole jobs](docs/guide/workflows.md) · [VMD](docs/guide/vmd.md) · [Your VMD window](docs/guide/window.md) · [The tool library](docs/guide/tools.md) · [MCP clients](docs/guide/mcp.md) · [Docker](docs/guide/docker.md) ·
[The model benchmark](docs/benchmarks/model-benchmark.md) · [Development](docs/reference/development.md) · [Architecture](docs/reference/architecture.md) · [Methods](docs/reference/methods.md) ·
[Security](docs/reference/security.md) · [Research paper](docs/reference/RESEARCH.md) · [Changelog](docs/CHANGELOG.md)

## Contributing

`pip install -e ".[dev]"`, then `ruff check src tests`, `vulture` and `pytest -rs`. See [Development](docs/reference/development.md).

MIT licence ([LICENSE](LICENSE)). Third-party notes, including **VMD and MDAnalysis (GPL)**: [NOTICE](docs/NOTICE.md).
