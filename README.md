# vmd-agent

Ask questions about your molecular structures and simulations **in plain language** and get answers worked out from real measurements: what is in a system, how it moves,
whether a statement about it is true. [VMD](https://www.ks.uiuc.edu/Research/vmd/) does the measuring and the drawing; vmd-agent is the **agent** in between, a language model
that decides which VMD tools to use, runs them, and has every answer checked against what the tools actually returned.

It works out for itself what computer it is on (Mac, Windows or Linux) and runs the model **on your own computer with a free open-source model by default**. If Claude Code
is installed, the same tools are offered to it as well, like any other MCP server.

## Highlights

* **An agent for VMD.** Describe what you want; the agent picks from **53 tools**, runs them, and answers from their numbers. It says how each number was obtained.
* **Open-source first.** Free models run locally through a private copy of Ollama, chosen to fit your memory. Nothing leaves your computer unless you choose an online model.
* **A complete wrapper around VMD.** 24 commands drive VMD itself: measurements, interactions, trajectory conversion, density maps, system building, scenes, movies and hand-offs to NAMD and
  a cluster. Each one saves the exact Tcl it ran, so you can repeat it in your own VMD.
* **Whole jobs, not only single commands.** Six workflows run several tools in a fixed order, grade what they find and write a report with the checksums of your inputs and the Tcl of every step.
* **Four ways to work, one set of tools.** A web page with a molecule viewer, a numbered menu, a terminal chat, and plain commands.
* **Honest answers.** Every number must come from a tool; a model that answers from memory is sent back to use one, a number no tool returned is sent back or flagged, and a request that cannot be answered
  is declined rather than guessed.
* **Everything is timed.** You see how long each model call and each tool call took.
* **Contained.** One private folder, no administrator rights, nothing installed system-wide. The agent can only read and write inside the files folder you choose.
* **Pick a model by measuring.** A built-in benchmark scores any model on 58 tasks, one per kind of functionality, so you can choose the model that suits your work and your computer.

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
| **VMD**: whether it is there, starts, and its version | uses it for pictures and the 24 VMD tools; without it every other tool still works, with built-in pictures |
| **Ollama** | runs the open-source model through a private copy kept inside the vmd-agent folder (or yours, if you have one), downloading a model only after asking |
| **Claude Code** | if the `claude` command is installed, offers to register vmd-agent as an MCP server so Claude Code can use VMD through it |

`vmd-agent doctor` prints all of this and what to do next.

## Four ways to work

| Way | What it is | Start it |
|---|---|---|
| **The web page** | A workbench in your browser: your files, a **molecule viewer** (backbone, bonds, spheres, points; coloured by element, chain, residue type, residue number or index; trajectory playback, saved pictures), the chat with every tool call shown with its progress and seconds, and a tab that runs whole jobs | `vmd-agent ui` |
| **The menu** | Numbered choices in plain words: look at a structure, analyse a simulation, check a statement, connect an AI app | `vmd-agent` |
| **The chat** | Ask in plain language in the terminal; answers stream as they are written, with the time each step took | `vmd-agent chat` |
| **Commands** | Scripts and batches without any model: every capability is a command with flags | `vmd-agent <command>` |

```bash
vmd-agent show 1UBQ                                         # fetch, draw and describe a structure
vmd-agent analyze run.psf run.dcd --do rmsd rmsf rgyr       # measure a simulation
vmd-agent claims my.pdb "It has 4 disulfide bridges"        # check a statement against the data
vmd-agent workflow equilibration_check run.psf run.dcd      # a whole job, with a report
vmd-agent vmd measure run.pdb run.dcd --kind rgyr           # one of VMD's own measurements
```

Put your structure and trajectory files in your files folder and ask for them by name: *"What is in protein.pdb?"*, *"Has my run settled? Use run.psf and run.dcd."*, *"Which salt bridges persist?"*,
*"Build a solvated, neutral system from 1ubq.pdb."*

## What it can do

The pipeline of a project, with the commands for each stage. `vmd-agent --help` lists every command in this order.

| Stage | You want to | Main commands | Detail |
|---|---|---|---|
| 1. Set up | install, find VMD, choose who answers | `vmd-agent setup`, `doctor`, `models` | [Install](docs/guide/install.md), [Models](docs/guide/models.md) |
| 2. Get a structure | have a file to work with | `vmd-agent fetch`, `search` | [Commands](docs/guide/commands.md#2-get-a-structure) |
| 3. Look at it | see and describe what is in it | `vmd-agent show`, `visualize`, `inspect`, `detect`, `stats` | [Commands](docs/guide/commands.md#3-look-at-it) |
| 4. Measure a simulation | numbers, events, true-or-false checks | `vmd-agent analyze`, `keyframes`, `claims` | [Commands](docs/guide/commands.md#4-measure-a-simulation) |
| 5. Run a whole job | several steps, a verdict, a report | `vmd-agent workflow` | [Workflows](docs/guide/workflows.md) |
| 6. Drive VMD itself | build systems, maps, scenes, hand-offs | `vmd-agent vmd ...` | [VMD](docs/guide/vmd.md) |
| 7. Check and keep records | re-check hashes, videos, validation | `vmd-agent provenance`, `report`, `validate` | [Commands](docs/guide/commands.md#7-check-and-keep-records) |

### Understand a structure
Detects what a system contains (protein chains, ligands, water, ions, lipids, nucleic acids, materials), counts bonds, disulfides, hydrogen bonds and salt bridges, assigns secondary structure, checks
chirality, cis peptides and chain gaps, and draws it from several angles with a legend that ties every colour to what it shows. Structures come from your files, the PDB, AlphaFold or a URL.

### Measure a simulation
RMSD, RMSF, radius of gyration, contacts, hydrogen bonds, distances, solvent-accessible area and density, with convergence tests that say whether a run has settled; event-aware keyframes that pick the frames
where something actually happens; and **claim checking**: a statement about the system comes back supported, contradicted or "cannot tell", with the evidence.

### Drive VMD itself (24 commands)
Measure commands (radius of gyration, RMSD, RMSF, g(r), SASA, clusters and more), hydrogen bonds, salt bridges and contacts as how often each pair is present, secondary structure per frame, Ramachandran
regions, structure checks, superposition, periodic box analysis; trajectory conversion and structure writing; density, occupancy and potential maps; building solvated and neutral CHARMM36 systems, mutations,
merges, membranes and nanotubes; scenes rendered to images and rotating movies, or exported as a folder you can open in your own VMD; cryo-EM map fitting and map arithmetic; NAMD inputs and SLURM scripts.
The list: [VMD](docs/guide/vmd.md). `vmd_capabilities` classifies every plugin of *your* VMD as driven, GUI-only, needing another program, or not yet wrapped.

### Whole jobs and reports
`structure_overview`, `equilibration_check`, `interaction_report`, `compare_runs`, `prepare_simulation` and `cryoem_fit` run several tools in order, grade the findings (ok, note, warning, problem), give a verdict
and write `report.md` and `report.html` with the figures, every caveat the tools raised, the methods, the SHA-256 of every input and the Tcl of every VMD step. [Workflows](docs/guide/workflows.md).

### Videos, records and hand-offs
Read a video's real metadata and prove it decodes, pull stills you can map back to simulation frames; re-check the hashes recorded for an earlier run; assemble a written report from a session; write NAMD
inputs and cluster job scripts.

## The agent

One module runs the model, the tools and the checks, and every screen is a thin front end on it, so the chat, the web page and the benchmark behave the same.

* **Routing.** `--tools auto` offers the model only the tools that fit the question, plus a way to ask for more; `--tools all` (the default), `core` and `vmd` give it a fixed set.
  [Which tools a model sees](docs/guide/tools.md#does-the-model-see-all-53-at-once).
* **Argument repair.** A number written as text, `RMSD` for `rmsd`, a missing folder in a file name, a trajectory given as the topology: put right when there is only one way to read it, and the result says so.
* **Plain results.** The results models misread most start with a one-sentence summary, and parameters whose names do not say what they do are described to the model.
* **The guard.** A data question answered without a tool is sent back once; an answer with a number no tool returned is sent back once, then flagged.
* **MCP.** The same tools are an MCP server for Claude Code, Claude Desktop or any client. [MCP clients](docs/guide/mcp.md).

More: [architecture](docs/reference/architecture.md#the-agent-and-what-surrounds-the-model).

## Choosing a model

The suggested open-source models ([the list](docs/guide/models.md), each checked against the Ollama library) differ in how well they use tools. The built-in benchmark puts a model in front of the tools with 58
plain-language requests in 14 kinds of functionality (inspecting files, claims, trajectories, VMD measurements, conversion, building, maps, rendering, video, whole jobs, hand-offs, records, network, and requests
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
src/vmd_agent/     the package: the agent, the 53 tools, VMD wrappers (vmdkit/), analysis, drawing, the web page, the benchmarks
install/           the one-line installers (install.sh for Mac and Linux, install.ps1 for Windows)
docker/            Dockerfile, compose files and helpers for the container routes
docs/              the manual: guide/ (using it), benchmarks/ (choosing a model), reference/ (architecture, methods, security, research), CHANGELOG and NOTICE
tests/             the test suite, mirrored on the package
.github/           CI
```

## Documentation

[**All the pages**](docs/index.md): [Install and set up](docs/guide/install.md) · [Ways to work](docs/guide/using.md) · [Command reference](docs/guide/commands.md) · [Models](docs/guide/models.md) ·
[Whole jobs](docs/guide/workflows.md) · [VMD](docs/guide/vmd.md) · [The 53 tools](docs/guide/tools.md) · [MCP clients](docs/guide/mcp.md) · [Docker](docs/guide/docker.md) ·
[The model benchmark](docs/benchmarks/model-benchmark.md) · [Development](docs/reference/development.md) · [Architecture](docs/reference/architecture.md) · [Methods](docs/reference/methods.md) ·
[Security](docs/reference/security.md) · [Research paper](docs/reference/RESEARCH.md) · [Changelog](docs/CHANGELOG.md)

## Contributing

`pip install -e ".[dev]"`, then `ruff check src tests`, `vulture` and `pytest -rs`. See [Development](docs/reference/development.md).

MIT licence ([LICENSE](LICENSE)). Third-party notes, including **VMD and MDAnalysis (GPL)**: [NOTICE](docs/NOTICE.md).
