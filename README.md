# vmd-agent

Ask questions about your molecular structures and simulations **in plain language** and get answers worked out from real measurements: what is in a system, how it moves,
whether a statement about it is true. [VMD](https://www.ks.uiuc.edu/Research/vmd/) does the measuring and the drawing; vmd-agent is the **agent** in between, a language model
that decides which VMD tools to use, runs them, and has every answer checked against what the tools actually returned.

It works out for itself what computer it is on (Mac, Windows or Linux) and runs the model **on your own computer with a free open-source model by default**. Prefer Claude Code or Claude Desktop as the assistant? Choose that
in setup instead of a local model; vmd-agent then just supplies the tools, like any other MCP server.

## Highlights

* **An agent for VMD.** Describe what you want; the agent picks from **55 tools** in eleven groups, runs them, and answers from their numbers. It says how each number was obtained.
* **Open-source first.** Free models run locally through a private copy of Ollama, chosen to fit your memory. Nothing leaves your computer unless you choose an online model.
* **An agent over your own VMD.** The agent drives the VMD window you can see: load a system, draw it as a cartoon or a surface, colour it, zoom to the ligand, step through frames, ask what is selected, take a picture. Every picture and number is VMD's own; nothing is imitated. [Your VMD window](docs/guide/window.md).
* **A complete wrapper around VMD.** The library covers VMD itself: measurements, interactions, trajectory conversion, density maps, system building, scenes, movies and hand-offs to NAMD and
  a cluster. Each tool that runs VMD saves the exact Tcl it ran, so you can repeat it in your own VMD.
* **Whole jobs, not only single tools.** Six workflows sit above the tools: each runs several of them in a fixed order, grades what it finds and writes a report with the checksums of your inputs and the Tcl of every step.
* **Four ways to work, one library.** A web page that looks like VMD and drives a real one, a numbered menu, a terminal chat, and one command, `vmd-agent tool`, that runs any tool.
* **Honest answers.** Every number must come from a tool; a model that answers from memory is sent back to use one, a number no tool returned is sent back or flagged, and a request that cannot be answered
  is declined rather than guessed.
* **Everything is timed.** You see how long each model call and each tool call took.
* **Contained.** One private folder, no administrator rights, nothing installed system-wide. The agent can only read and write inside the files folder you choose.
* **Pick a model by measuring.** A built-in benchmark scores any model on 65 tasks, one per kind of functionality, so you can choose the model that suits your work and your computer.

**You need** a Mac, Windows or Linux computer, an internet connection, and VMD (free, from UIUC) for VMD-quality pictures and the VMD-driven tools. **You do not need** Python, Git, Docker, ffmpeg, an account or any AI app.

## Install

Open a terminal (Mac: `Cmd` + `Space`, type `Terminal`; Windows: Start menu, type `PowerShell`), paste **one line**, and answer four questions.

Mac or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.ps1 | iex"
```

Everything goes into one folder (`~/vmd-agent`); deleting it removes everything. Setup finds VMD and starts it once to prove it works, makes a files folder the agent is confined to, and lets you
choose who answers: a free model on your computer (recommended), an online service, Claude Desktop or Code, or none. More: [Install and set up](docs/guide/install.md).

### What it works out by itself

| It looks at | And then |
|---|---|
| the **operating system and CPU** (macOS, Linux, Windows, WSL, a container; Apple Silicon or not) | finds VMD where that system keeps it, uses the right launcher, paths and settings folder, and tells you what cannot work here (for example, a Mac's VMD cannot run inside Docker) |
| the **memory and graphics card** | suggests the model that fits: the 8B default from 16 GB (or with an NVIDIA card), the 3B from 8 GB, and says plainly when there is too little for a model that can use tools |
| **VMD**: whether it is there, starts, and its version | uses it for pictures and the tools that run VMD; without it every other tool still works, with built-in pictures |
| **Ollama** | runs the open-source model through a private copy kept inside the vmd-agent folder (or yours, if you have one), downloading a model only after asking |
| **Claude Code or Desktop** | notes whether they are installed, and offers them as an *alternative* assistant in setup (the choice is yours; nothing is registered unless you pick it) |

`vmd-agent doctor` prints all of this and what to do next.

## Four ways to work

| Way | What it is | Start it |
|---|---|---|
| **The web page** | A remote for a **real VMD window**, laid out like VMD in your browser: menus and a command palette, the molecule list, **representations** (selection, drawing method, colour, material), animation and a console, all acting on VMD, and a display that shows **VMD's own pictures**; plus the chat with every tool call shown with its progress and seconds, **a form for every tool** (drop-downs, check boxes, buttons), a tab that runs whole jobs, and a terminal for developers | `vmd-agent ui` |
| **The menu** | Numbered choices in plain words: look at a structure, analyse a simulation, check a statement, connect an AI app | `vmd-agent` |
| **The chat** | Ask in plain language in the terminal; answers stream as they are written, with the time each step took | `vmd-agent chat` |
| **The command line** | Scripts and batches without any model: any tool of the library, with flags made from its parameters | `vmd-agent tool NAME ...` |

```bash
vmd-agent tools                                                          # the library, in groups
vmd-agent tool fetch_structure 1UBQ --out pdbs                           # download a structure
vmd-agent tool analyze_trajectory run.psf run.dcd --analyses rmsd rgyr   # measure a simulation
vmd-agent tool verify_claims my.pdb "It has 4 disulfide bridges"         # check a statement against the data
vmd-agent tool measure_with_vmd run.pdb run.dcd --kind rgyr              # one of VMD's own measurements
vmd-agent workflow equilibration_check run.psf run.dcd                   # a whole job, with a report
```

Put your structure and trajectory files in your files folder and ask for them by name: *"What is in protein.pdb?"*, *"Has my run settled? Use run.psf and run.dcd."*, *"Which salt bridges persist?"*,
*"Build a solvated, neutral system from 1ubq.pdb."*

## What it can do

### The tool library: 55 tools in eleven groups

A tool does one thing. Every tool is available to the chat, to an MCP client and to `vmd-agent tool NAME`; there is no second list. [Every tool, with what it does and whether it needs VMD](docs/guide/tools.md).

| Group | Tools |
|---|---|
| **Look at this computer and your files** (4) | `probe_environment` · `inspect_files` · `detect_system` · `structure_stats` |
| **Get a structure** (2) | `search_pdb` · `fetch_structure` |
| **Draw** (10) | `visualize_and_interpret` · `render_image` · `render_movie` · `annotate_image` · `view_image` · `generate_visualization_recipe` · `list_representations` · `color_key` · `export_session` · `run_tcl` |
| **Control your VMD window** (11) | `window_open` · `window_load` · `window_molecules` · `window_representation` · `window_display` · `window_view` · `window_animate` · `window_query` · `window_snapshot` · `window_scene` · `window_save` |
| **Measure a simulation** (4) | `analyze_trajectory` · `measure_with_vmd` · `select_keyframes` · `periodic_box` |
| **Interactions and structure quality** (5) | `find_interactions` · `secondary_structure` · `backbone_torsions` · `check_structure` · `align_structures` |
| **Convert and write files** (2) | `convert_trajectory` · `write_structure` |
| **Density maps (cryo-EM and more)** (4) | `make_map` · `inspect_map` · `combine_maps` · `fit_to_map` |
| **Build and prepare a simulation** (7) | `build_system` · `mutate_residue` · `merge_structures` · `build_membrane` · `build_nanotube` · `prepare_namd` · `write_slurm_script` |
| **Video** (2) | `probe_video` · `interpret_video` |
| **Evidence and records** (4) | `verify_claims` · `record_visual_interpretation` · `assemble_report` · `verify_provenance` |

* **Understand a structure.** Detects what a system contains (protein chains, ligands, water, ions, lipids, nucleic acids, materials), counts bonds, disulfides, hydrogen bonds and salt bridges, assigns secondary
  structure, checks chirality, cis peptides and chain gaps, and draws it from several angles with a legend that ties every colour to what it shows. Structures come from your files, the PDB, AlphaFold or a URL.
* **Measure a simulation.** RMSD, RMSF, radius of gyration, contacts, hydrogen bonds, distances, solvent-accessible area and density, with convergence tests that say whether a run has settled; event-aware
  keyframes that pick the frames where something actually happens; and **claim checking**: a statement about the system comes back supported, contradicted or "cannot tell", with the evidence.
* **Drive VMD itself.** VMD's own `measure` commands, interactions as how often each pair is present, secondary structure per frame, Ramachandran regions, trajectory conversion, density maps, solvated
  CHARMM36 systems, mutations, membranes and nanotubes, scenes rendered to images and rotating movies or exported as a folder you can open in your own VMD, cryo-EM map fitting, NAMD inputs and SLURM scripts.
  `probe_environment` with `plugins` classifies every plugin of *your* VMD as driven, GUI-only, needing another program, or not yet wrapped. [VMD](docs/guide/vmd.md).
* **Videos and records.** Read a video's real metadata, prove it decodes and pull stills you can map back to simulation frames; re-check the hashes recorded for an earlier run; assemble a written report from a session.

### Workflows: whole jobs above the tools

A workflow is not a tool: it runs several tools in a fixed order, grades the findings (ok, note, warning, problem), gives a verdict and writes `report.md` and `report.html` with the figures, every caveat the
tools raised, the methods, the SHA-256 of every input and the Tcl of every VMD step. The agent reaches all six through one call, `run_workflow`; from a terminal it is `vmd-agent workflow NAME FILE ...`. [Workflows](docs/guide/workflows.md).

| Workflow | Files | What it does |
|---|---|---|
| `structure_overview` | structure | what is in it, and is it in good shape: composition, torsions, chirality, gaps, pictures |
| `equilibration_check` | topology, trajectory | has the run settled: RMSD and size convergence, periodic box, two engines compared |
| `interaction_report` | topology, trajectory | hydrogen bonds and salt bridges (and contacts with a partner group), as how often each is present |
| `compare_runs` | topology, two trajectories | RMSD, size and fluctuation of two runs side by side |
| `prepare_simulation` | structure | check the input, build a solvated neutral CHARMM36 system, write NAMD and SLURM files |
| `cryoem_fit` | model, map | fit a model into a cryo-EM map, with a picture and a session for VMD |

## The agent

One module runs the model, the tools and the checks, and every screen is a thin front end on it, so the chat, the web page and the benchmark behave the same.

* **Routing.** `--tools auto` offers the model only the tools that fit the question, plus a way to ask for more; `--tools all` (the default) gives it the whole library.
  [Which tools a model sees](docs/guide/tools.md#does-the-model-see-all-of-them-at-once).
* **Argument repair.** A number written as text, `RMSD` for `rmsd`, a missing folder in a file name, a trajectory given as the topology: put right when there is only one way to read it, and the result says so.
* **Plain results.** The results models misread most start with a one-sentence summary, and parameters whose names do not say what they do are described to the model.
* **The guard.** A data question answered without a tool is sent back once; an answer with a number no tool returned is sent back once, then flagged.
* **MCP.** The same tools are an MCP server for Claude Code, Claude Desktop or any client. [MCP clients](docs/guide/mcp.md).

More: [architecture](docs/reference/architecture.md#the-agent-and-what-surrounds-the-model).

## Choosing a model

The suggested open-source models ([the list](docs/guide/models.md), each checked against the Ollama library) differ in how well they use tools. The built-in benchmark puts a model in front of the tools with 58
plain-language requests in 15 kinds of functionality (inspecting files, claims, trajectories, VMD measurements, conversion, building, maps, rendering, driving a VMD window, video, whole jobs, hand-offs, records, network, and requests
that must be declined). Each task has the tools that answer it and the **correct answer**, worked out from data built to have known properties ([every prompt and its correct answer](docs/benchmarks/model-benchmark-tasks.md)),
and is graded by a program, with the seconds of every model call and tool call.

```bash
vmd-agent bench models --list --reference          # every prompt and what a correct answer says
vmd-agent bench models --model granite4.1:8b       # one model on your local server
vmd-agent bench models --catalogue --pull          # every suggested model, one after another (downloaded into the private Ollama)
vmd-agent bench models --summarize                 # the comparison: success by model and by kind of functionality, seconds, tokens
vmd-agent bench tools                              # every tool on generated data with known answers
```

Details: [the model benchmark](docs/benchmarks/model-benchmark.md), [the tool test set](docs/benchmarks/tool-test-set.md).

## Safe by design

The agent can only read and write inside your files folder. Tcl is never taken from a caller: each VMD command builds its script from validated values and runs it headless with a scrubbed environment and a timeout.
The free-form Tcl tool is off unless you switch it on. Downloads are limited to the sources you name, and the private model server is checked against its published checksum before it runs. [Security](docs/reference/security.md).

## Repository layout

```
src/vmd_agent/     the package: the agent, the tool library, VMD wrappers (vmdkit/), analysis, drawing, the web page, the benchmarks
install/           the one-line installers (install.sh for Mac and Linux, install.ps1 for Windows)
docker/            Dockerfile, compose files and helpers for the container routes
docs/              the manual: guide/ (using it), benchmarks/ (choosing a model), reference/ (architecture, methods, security, research), CHANGELOG and NOTICE
tests/             the test suite, mirrored on the package
.github/           CI
```

## Documentation

[**All the pages**](docs/index.md): [Install and set up](docs/guide/install.md) · [Ways to work](docs/guide/using.md) · [The command line](docs/guide/commands.md) · [Models](docs/guide/models.md) ·
[Whole jobs](docs/guide/workflows.md) · [VMD](docs/guide/vmd.md) · [The tool library](docs/guide/tools.md) · [MCP clients](docs/guide/mcp.md) · [Docker](docs/guide/docker.md) ·
[The model benchmark](docs/benchmarks/model-benchmark.md) · [Development](docs/reference/development.md) · [Architecture](docs/reference/architecture.md) · [Methods](docs/reference/methods.md) ·
[Security](docs/reference/security.md) · [Research paper](docs/reference/RESEARCH.md) · [Changelog](docs/CHANGELOG.md)

## Contributing

`pip install -e ".[dev]"`, then `ruff check src tests`, `vulture` and `pytest -rs`. See [Development](docs/reference/development.md).

MIT licence ([LICENSE](LICENSE)). Third-party notes, including **VMD and MDAnalysis (GPL)**: [NOTICE](docs/NOTICE.md).
