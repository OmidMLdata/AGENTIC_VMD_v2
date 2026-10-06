# vmd-agent

Ask questions about your molecular structures and simulations **in plain language** and get answers worked out from real
measurements: what is in a system, how it moves, whether a statement about it is true. VMD (free, from UIUC) does the
measuring and the drawing; a language model does the talking (a free open-source one on your own computer, or an online one you
choose); this program gives the model the tools and checks its work.

**You need:** a Mac, Windows or Linux computer, an internet connection, and VMD if you want VMD-quality pictures and the VMD-driven
tools. **You do not need:** Python, Git, Docker, ffmpeg, an account, or any AI app.

## The pipeline

One project goes through the same stages whichever way you work (the menu, the chat, commands, or an AI app). Each stage is a
section below.

| Stage | You want to | Main commands |
|---|---|---|
| [1. Set up](#1-set-up) | install, find VMD, choose who answers | `vmd-agent setup` · `doctor` · `models` |
| [2. Get a structure](#2-get-a-structure) | have a file to work with | `vmd-agent fetch` · `search` |
| [3. Look at it](#3-look-at-it) | see and describe what is in it | `vmd-agent show` · `visualize` · `inspect` · `detect` · `stats` |
| [4. Measure a simulation](#4-measure-a-simulation) | numbers, events, true-or-false checks | `vmd-agent analyze` · `keyframes` · `claims` |
| [5. Run a whole job](#5-run-a-whole-job-and-get-a-report) | several steps, a verdict, a written report | `vmd-agent workflow` |
| [6. Drive VMD itself](#6-drive-vmd-itself) | build systems, maps, scenes, hand-offs | `vmd-agent vmd ...` |
| [7. Check and keep records](#7-check-and-keep-records) | re-check hashes, videos, validation | `vmd-agent provenance` · `report` · `validate` |

Around the pipeline: [ways to work](#ways-to-work) (menu, chat, commands), [troubleshooting](#if-something-goes-wrong),
[what has been verified](#what-has-and-has-not-been-verified), and a [reference](#reference) for AI-app connections,
development, architecture, methods, security and Docker.

## 1. Set up

### Install (about 5 minutes)

**Open a terminal.** Mac: press `Cmd` + `Space`, type `Terminal`, press Enter. Windows: Start menu, type `PowerShell`, press
Enter. Linux: your terminal app. **Paste ONE line and press Enter.** Mac or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.ps1 | iex"
```

It puts a small helper called [uv](https://docs.astral.sh/uv/) (which fetches Python for you) and vmd-agent, with everything they
need including a bundled ffmpeg for movies, into **one private folder** (`~/vmd-agent`; Windows `%USERPROFILE%\vmd-agent`). No
administrator password, no changes to your PATH or to any file outside that folder. It takes a few minutes, mostly downloading.
The two installers (`install.sh`, `install.ps1`) are separate files only because a Mac's shell and PowerShell cannot read each
other's language, and they must run before Python exists; they do the same thing.

### Answer the setup questions

The installer starts `vmd-agent setup`. It explains each step and asks four things:

| Step | What happens | What you answer |
|---|---|---|
| 1. VMD | looks for VMD, **starts it once to prove it works**, and tells you its version | nothing, unless it cannot find it (then: the folder VMD is in, or Enter to skip) |
| 2. Your files | makes a folder, by default `~/vmd-agent-data`. The AI can **only see this folder**. | Enter to accept, or type another |
| 3. The AI | you choose who answers (below) | a number from 1 to 4 |
| 4. Finish | saves your choices | nothing |

From now on run `~/vmd-agent/bin/vmd-agent` (Windows: `%USERPROFILE%\vmd-agent\bin\vmd-agent.cmd`). Put your structure and
trajectory files in your files folder and ask for them by name. (Add that `bin` folder to your PATH yourself if you want to type just
`vmd-agent`; the installer never does it for you. Examples here write `vmd-agent`.) `vmd-agent setup` can be run again at any time to
change a choice, and `vmd-agent doctor` says what this computer has, whether VMD really starts, which model is ready, and what to do
next.

### Choosing who answers you (setup step 3)

| Choice | What it is | Good to know |
|---|---|---|
| **1. A free model on this computer** (recommended) | An open-source model run by a free program called Ollama. Works offline; your data never leaves the computer. | It asks before downloading anything. It keeps a **private copy of Ollama inside the vmd-agent folder** (about 0.2 GB on a Mac, 1.4 to 1.6 GB on Linux and Windows), checked against Ollama's published checksum, plus the model (2 to 18 GB, see below). If you already have Ollama it uses that instead. Downloads happen once. |
| **2. An online model service** | Any service with the common "OpenAI-compatible" chat interface: you give a web address, a model name and your key. | The key is saved in a file only you can read. |
| **3. Claude Desktop or Claude Code** | Connects the tools to an AI app you already use ([details](#use-it-from-an-mcp-client)). | It edits that app's settings file only after you say yes, and keeps a backup. |
| **4. Skip** | No chat. | Every other command still works. |

A model on a computer without a graphics card can take a minute or more per answer. On a Mac, running Ollama directly (which setup
does) uses the Mac's graphics chip and is much faster than running it inside Docker.

### Free models (as of 2026-10-06)

These are the open-source models this toolkit suggests. On **2026-10-06**, while writing the code, each was checked against
the public [Ollama library](https://ollama.com/library): the name exists, the download size is what the registry reported,
the licence is what it serves, and the library page marks it as able to call tools (which this toolkit needs). Names move
quickly, so `vmd-agent models --check` asks the library again, and setup does that before it downloads anything.

| Model | Download | Licence | Suits | Note |
|---|---|---|---|---|
| `granite4.1:3b` | 2.1 GB | Apache 2.0 | 8 GB of memory | small and fast |
| `granite4.1:8b` | 5.35 GB | Apache 2.0 | 16 GB of memory, or a graphics card | **default** |
| `gemma4:e4b` | 6.58 GB | Apache 2.0 | 16 GB of memory, or a graphics card | alternative |
| `lfm2.5:8b` | 5.16 GB | LFM Open License v1.0 (not Apache; read it) | 16 GB of memory | fast on a plain CPU |
| `gemma4:12b` | 8.02 GB | Apache 2.0 | 32 GB of memory, or a good graphics card | larger |
| `gpt-oss:20b` | 13.79 GB | Apache 2.0 | 32 GB of memory, or a 16 GB graphics card | larger |
| `qwen3.8:27b` | 17.74 GB | Apache 2.0 | 48 GB of memory, or a 24 GB graphics card | largest listed |

**Read this before trusting it:** the sizes, names and licences were checked on that date, and the "suits" column is a rough
guide, not a measurement. **Only `granite4.1:8b` and `granite4.1:3b` were run with this toolkit** (on a Mac, 2026-10-06, a few dozen
questions about local files, trajectories and system building; this is not a benchmark). The 8B chose the right tools and reported
their numbers correctly in the questions tried, though it sometimes fills arguments badly. The 3B chose tools but often misread what
they returned, which is why the chat flags any number a tool did not return; **start with the 8B or larger**. The others are
unverified. Any other Ollama model, or any online OpenAI-compatible service, can be used instead. `vmd-agent claims` checks any
statement against the data.

### Which VMD version?

**Use a VMD 1.9.x release** ([download](https://www.ks.uiuc.edu/Research/vmd/); the toolkit never downloads VMD for you, because
VMD's licence requires you to accept it yourself).

* **Tested:** VMD **1.9.4a57**, macOS on Apple Silicon (run from its disk image), on 2026-10-06: the tests that need a real VMD
  passed (loading, selections agreeing with MDAnalysis, Tachyon renders, several views and frame sets in one session, movies, the
  safe-Tcl tool, the benchmark preflight, and each of the [24 tools that drive VMD itself](#6-drive-vmd-itself), whose numbers were
  compared with MDAnalysis, NumPy or SciPy where an independent implementation exists).
* **Not tested:** any other VMD version, **Linux or Windows builds** of VMD, the Docker route.
* The version is **not enforced**. It is read (`vmdinfo version`), shown by `vmd-agent doctor` and setup, recorded in every
  provenance record, and flagged when it is not a tested version or is outside 1.9.x (2.0, 1.8, a dev build), where VMD's scripting
  may behave differently. The tested list is `VMD_VERSIONS_TESTED` in `environment.py`; to add yours, run
  `python scripts/dev.py test` with VMD installed and tell the author what passed.
* VMD's own pages list 1.9.3 and 1.9.4 as of 2026-10-06; which one is the current stable release was not confirmed.

**How VMD is handled:** the toolkit finds VMD on your OS, proves it starts (and says why if not: missing `tcsh`, missing libraries,
wrong CPU), runs it headless with a timeout and a cleaned environment, and confines it to your data folder. Arbitrary Tcl exists only
if you switch it on with `VMD_AGENT_ENABLE_TCL=1`, and is not a security boundary. Without VMD everything else still works, with
simpler built-in pictures. How much of VMD is wrapped is in [stage 6](#how-much-of-vmd-is-this).

### Where everything lives, updating, uninstalling

The installer puts **everything** in one folder, by default `~/vmd-agent`: the helper tool, Python, the program and its packages
(including ffmpeg), your settings, and, if you choose a free local model, a private copy of Ollama and its models. It uses no
administrator rights, installs nothing system-wide and does not edit your shell's startup files. Your own data folder
(`~/vmd-agent-data`) and VMD itself are separate and are never touched. **Update:** run the install line again. **Uninstall:** delete
the `~/vmd-agent` folder. (If you used Docker, `vmd-agent start --down` stops it and `docker compose down -v` removes its model
volume.)

### Other ways to install

* **You already use Python:** `pip install "vmd-agent[server] @ https://github.com/OmidMLdata/AGENTIC_VMD_v2/archive/refs/heads/main.zip"`,
  then `vmd-agent setup`. The packages are listed once, in [`pyproject.toml`](pyproject.toml) (`[all]` adds the optional ones).
* **From a downloaded copy:** run `./install.sh` (Mac/Linux) or `install.ps1` (Windows) from inside the folder; it installs that copy.
* **Docker (advanced):** `vmd-agent start` picks native or Docker from the facts about your computer and starts the chat
  (`--print-plan` shows what it would do, `--down` stops the containers). Docker cannot run a Mac or Windows VMD (it needs VMD's
  **Linux** build in `docker/vmd-dist/`) and on a Mac cannot use the Mac's graphics chip. See [Docker](#docker).
* **An MCP client** (Claude Code, Claude Desktop, others): [Use it from an MCP client](#use-it-from-an-mcp-client).

## Ways to work

Three ways in. They all call the same tools, so pick whichever suits you:

| Way | For whom | How |
|---|---|---|
| **The menu** | you would rather not learn commands | type `vmd-agent`, pick a number |
| **Chat** | you want to ask in plain words | `vmd-agent chat` (or `vmd-agent chat "your question"` for a single answer) |
| **Commands** | scripts, batches, no AI | `vmd-agent <command> ...`, in the stages below |

Things to type into `vmd-agent chat` (examples of what to ask, not results): *"What is in 1ubq.pdb?"*, *"Draw it from the front and
the side and tell me what each colour means."*, *"Has my run settled? Use run.psf and run.dcd."*, *"Which salt bridges persist?"*,
*"Build a solvated, neutral system from 1ubq.pdb."*, *"Does this structure really have a ligand and a disulfide bond?"* Inside the
chat, `/tools` lists the tools, `/reset` starts over, `/help` shows this, `/quit` leaves. `vmd-agent tools` lists all 53 tools; for
small models, `vmd-agent chat --tools core` or `--tools vmd` gives a shorter menu.

You can *see* what is happening: the answer appears as the model writes it (`--no-stream` to wait for the whole thing), each tool call
is shown with its progress ("frame 20 of 50", "adding a water box", "ray tracing 72 frames") and, for long ones, how long it took, and
a line says so when the model is still thinking. The `vmd` and `workflow` commands print the same progress on the error stream
(`--quiet` hides it), so the result on standard output stays clean to pipe.

### How the chat keeps a model honest

Language models guess; these checks stop a guess from passing as a measurement.

* **A data question needs a tool.** If a model answers a question about your files from memory, the chat sends it back once and
  requires a tool call.
* **Numbers are checked.** After the answer, every number the model wrote is compared with what the tools returned; any that no tool
  returned is listed under the answer ("check these numbers yourself").
* **Inputs are protected.** No tool writes over a file the same call reads, and a trajectory that does not match its topology is an
  error, not an empty result.
* **Invented settings are ignored.** Models are not shown the `vmd_path` parameter (they invent paths); the toolkit finds VMD itself.
* **The context is big enough.** The private Ollama runs with a 16384-token context (Ollama's default of 4096 cuts off the model's own
  instructions and tools). With your own Ollama, set `OLLAMA_CONTEXT_LENGTH=16384`.
* **Answers are capped** (3000 tokens), so a rambling model is cut off instead of waited for.

`vmd-agent chat` options: `--model NAME`, `--base-url ADDRESS`, `--api-key KEY`, `--roots FOLDER ...` (what the AI may see),
`--tools all|core|vmd`, `--max-turns N`, `--temperature T`, `--no-stream`, `--no-check`.

## 2. Get a structure

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent fetch ID` | download a PDB ID, UniProt (AlphaFold) accession or URL to a file | `--out-dir DIR` · `--source auto\|rcsb\|alphafold\|url` · `--format auto\|pdb\|cif` |
| `vmd-agent search words ...` | find PDB IDs by keyword | `--limit N` |

Or use your own files: put them in your files folder. `vmd-agent inspect FILE ...` says what kind of files they are and which companion
file (for example the PSF that goes with a DCD) is missing.

## 3. Look at it

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent show ID` | download a PDB ID, UniProt accession or URL, draw it, describe it | `--views front side top iso` · `--focus overview\|fold\|interactions\|surface\|pocket` · `--rep QuickSurf` · `--renderer auto\|vmd\|matplotlib` · `--source auto\|rcsb\|alphafold\|url` · `--out-dir DIR` · `--style` · `--bg` · `--water` |
| `vmd-agent visualize FILE` | draw your structure (or a simulation) from several angles and explain every colour | `--traj FILE` · `--views` · `--focus` · `--rep` · `--renderer` · `--out-dir DIR` · `--style` · `--bg` · `--no-render` (just the description and script) |
| `vmd-agent inspect FILE ...` | what kind of files these are and what companion file is missing | none |
| `vmd-agent detect FILE` | what is in the system: protein, ligand, water, ions, lipids, nucleic acids | `--traj FILE` |
| `vmd-agent stats FILE` | bond, disulfide, H-bond and salt-bridge counts, secondary structure, a colour key | `--traj FILE` · `--json` |
| `vmd-agent render FILE` | one VMD + Tachyon image | `--traj FILE` · `-o out.png` · `--frame N` · `--vmd PATH` |
| `vmd-agent recipe FILE` | write a VMD script that draws this system sensibly | `--traj FILE` · `-o script.tcl` · `--style` · `--bg` · `--water` |
| `vmd-agent reps` | the VMD representations and when to use each | `--category backbone\|atomic\|surface\|special` · `--name NAME` |
| `vmd-agent annotate IMAGE` | draw a colour key and statistics onto an image | `--topology FILE` · `--title TEXT` · `-o out.png` · `--panel-side right\|left` |

Pictures use VMD + Tachyon when you have them (best), or a built-in matplotlib drawing (backbone trace, no shading, no surfaces).

## 4. Measure a simulation

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent analyze TOP TRAJ` | RMSD, flexibility, size, contacts, H-bonds and a verdict on whether the run has settled | `--do rmsd rmsf rgyr hbonds contacts distance sasa density convergence` · `--sel "protein"` · `--sel2 "resname LIG"` (for contacts and distance) · `--cutoff A` · `--step N` · `--unwrap` (make molecules whole across the box) · `--dt-ps T` (the true time between frames when the header is wrong) · `--out-dir DIR` |
| `vmd-agent keyframes TOP TRAJ` | the frames where something actually happens, not evenly spaced ones | `-k N` how many · `--sel` · `--sel2` · `--step` · `--z-min` · `--render` draw them · `--renderer` · `--out-dir DIR` |
| `vmd-agent claims FILE "statement" ...` | check statements against the data: supported, contradicted, or "cannot tell" | `--traj FILE` · `--step N` |

Every result says *how* it was obtained. These need no VMD: inspecting files, loading PDB / PSF / GRO / XTC / DCD and mmCIF (read
natively), detecting components, integrity checks, bonds, disulfides, H-bonds, salt bridges, secondary structure (DSSP), trajectory
analysis, keyframes and claim checking.

## 5. Run a whole job and get a report

A workflow is a named job that runs several tools in a fixed order, the way a person would, and ends with a **verdict**, a list of
**findings** and a **report**. Nothing in it is decided by a language model: the findings come from the tools' own numbers and wording, and each is
graded **ok**, **note**, **warning** or **problem**. A step that needs VMD is skipped, and reported as skipped, when there is no VMD.

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent workflow` | list the workflows and the files each needs | none |
| `vmd-agent workflow NAME FILE ...` | run the job, collect findings, write `report.md` and `report.html` | `--out-dir DIR` · `--option KEY=VALUE` (repeat) · `--quiet` |

```bash
vmd-agent workflow                                          # the list
vmd-agent workflow equilibration_check run.psf run.dcd      # runs, shows progress, writes equilibration_check_report/
```

| Workflow | Files | What it does |
|---|---|---|
| `structure_overview` | structure | what is in it (components, bonds, disulfides, secondary structure), backbone torsions, chirality, cis peptides, chain gaps, two pictures |
| `equilibration_check` | topology, trajectory | RMSD and size with convergence tests, the periodic box over time, and the RMSD measured a second time by VMD as a cross-check (the two engines must agree to 2%) |
| `interaction_report` | topology, trajectory | hydrogen bonds and salt bridges as how often each pair is present; `--option partner="resname LIG"` adds contacts with that group and its surface area |
| `compare_runs` | topology, trajectory A, trajectory B | RMSD, radius of gyration and per-residue fluctuation side by side, with the caveat that one run each is not evidence about the systems |
| `prepare_simulation` | structure | checks the input, builds a solvated neutral CHARMM36 system, writes a NAMD input and a SLURM script; warns about everything that was left out |
| `cryoem_fit` | model, map | fits the model into the map, draws it inside the isosurface, exports a session for VMD |

Settings go in `--option key=value`: `selection`, `partner`, `step`, `padding`, `salt`, `temperature`, `resolution`, `renderer`.
In the chat, ask in words (*"Has my run settled? Use run.psf and run.dcd."*). When a question clearly matches a workflow (settled / equilibrated, compare runs, prepare a simulation, fit into a cryo-EM map, overview), the toolkit tells the model which workflow fits and the model makes the call (`run_workflow`); it then quotes the verdict and findings and gives you the report path.

**The report** (`report.md`, and `report.html` to open in a browser) is written next to the figures, which it copies in, so the folder can be
sent to someone. It holds: the verdict and findings; a table of every step with its time and key numbers; the figures; every **caveat the
tools raised** (for example "DCD headers often hold a default timestep"); the methods (settings, the version of VMD and of this toolkit, which engine
measured what); and a reproducibility section with the **SHA-256 of every input file** and the **exact Tcl of every VMD step**, copied into
`scripts/`. A reviewer can re-run it with the one command printed at the bottom.

Each workflow was run on real data and its findings checked (the two RMSD engines agree to three decimals on the test run; the known
K27-D52 salt bridge is found; a model displaced by a known amount is put back within half an angstrom). **Not tested:** `prepare_simulation`'s NAMD
input has never been run in NAMD, and the SLURM script has never been run on a cluster; `cryoem_fit` was tested on a map simulated from
the structure itself, not on an experimental map from the EMDB.

## 6. Drive VMD itself

**Is it a separate thing? Yes.** These twenty-four commands need only VMD (the cryo-EM, map, NAMD and SLURM ones need not even that): no language model, no chat, no internet. They are VMD's own
`measure` commands, its plugins, system building, density maps, scenes and a hand-off to the VMD GUI, run headless and returned as
numbers. You can reach the same commands in four ways, and every way gives the same answer:

| Way | How | Good for |
|---|---|---|
| **Commands** | `vmd-agent vmd measure run.pdb run.dcd --kind rgyr` | scripts, batches, no AI |
| **Chat** | ask: *"Which salt bridges persist in run.dcd?"* | exploring in plain words |
| **An MCP client** | Claude Desktop / Code, after `vmd-agent mcp-config --write` | working inside an AI app |
| **Python** | `from vmd_agent.vmdkit.measure import measure` | your own analysis code |

`vmd-agent vmd` lists the commands in the order a project goes (build, check, measure, convert, render, fit and hand off); `vmd-agent vmd <action> --help` shows one command's flags and an example. Required structure
files are positional (`TOPOLOGY [TRAJECTORY]`), anything written goes to `--out`, options are `--kebab-case` flags, a yes/no option that is on by
default turns off with `--no-<name>`, and `--vmd PATH` points at a particular VMD. A scene is described in JSON (`--scene file.json`,
or the JSON text itself). Results are JSON with long lists shortened; add `--full` for everything. Every command saves the Tcl it ran
(`reproduce_script` in the result).

**Requirements:** a real VMD (1.9.x; see [Which VMD version?](#which-vmd-version)). Every command says plainly when there is none.
**Safety:** a caller never supplies Tcl. Each command builds its script from validated values (paths, a restricted selection language,
numbers, choices from fixed lists), runs it in headless VMD with a scrubbed environment, and parses the numbers back.

### The commands

| Command | What it does | Checked against |
|---|---|---|
| `vmd-agent vmd build-system` | PDB to a solvated, neutral CHARMM36 system (psfgen, solvate, autoionize) | MDAnalysis (atoms, charge, residues) |
| `vmd-agent vmd mutate-residue` | Mutate one residue of a PSF/PDB pair | MDAnalysis residue names |
| `vmd-agent vmd merge-structures` | Combine two PSF/PDB systems into one | atom counts |
| `vmd-agent vmd build-membrane` | Build a POPC or POPE lipid bilayer patch | MDAnalysis atoms; P-to-P thickness against the known ~38 A |
| `vmd-agent vmd build-nanotube` | Build a carbon or boron-nitride nanotube | the analytic radius for the chirality |
| `vmd-agent vmd capabilities` | List the plugins of your VMD and which of them this toolkit wraps | every plugin of the installed VMD is classified |
| `vmd-agent vmd structure-check` | Chirality errors, cis peptides and chain gaps (the structurecheck plugin) | a clean structure and one with residues deleted |
| `vmd-agent vmd pbc-info` | Periodic box per frame: is there one, and does its volume drift | MDAnalysis box |
| `vmd-agent vmd volume-info` | What is in a density map file (dx, mrc, ccp4, cube, situs): grid, range, suggested isosurface levels | synthetic maps written to spec |
| `vmd-agent vmd measure` | VMD's measure commands over a trajectory: radius of gyration, SASA, RMSD, RMSF, distances, g(r), clusters ... | MDAnalysis, NumPy, SciPy (KD-tree), an independent Shrake-Rupley |
| `vmd-agent vmd interactions` | Hydrogen bonds, salt bridges or contacts, as how often each pair is present | the known K27-D52 salt bridge of ubiquitin |
| `vmd-agent vmd secondary-structure` | Secondary structure of every residue in every frame (what the Timeline window shows) | the toolkit's own DSSP (Q3 agreement) |
| `vmd-agent vmd backbone-torsions` | Phi/psi angles and coarse Ramachandran regions of one frame | NumPy dihedrals |
| `vmd-agent vmd align-structures` | Superpose one structure on another and report the RMSD | a known rotation and translation |
| `vmd-agent vmd volmap` | Make a density, occupancy, distance, mask or electrostatic-potential map | density integrates to the selection's mass |
| `vmd-agent vmd convert-trajectory` | Write a trajectory in another format, or just some atoms/frames, wrapped or fitted | coordinates read back |
| `vmd-agent vmd write-structure` | Write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin | atom counts |
| `vmd-agent vmd render-scene` | Draw a scene you describe (representations, isosurfaces, camera) to a PNG | image content |
| `vmd-agent vmd render-turntable` | A rotating-view movie of a scene | the video read back with ffmpeg (frames, size) |
| `vmd-agent vmd export-session` | Write a folder you can open in your own VMD (session.tcl, inputs, checksums) | opened again in a fresh VMD from another location |
| `vmd-agent vmd fit-to-map` | Cryo-EM: fit a model into a density map as a rigid body, and report the correlation before and after (NumPy, no VMD) | a model displaced by a known rotation and shift is put back within 0.5 A |
| `vmd-agent vmd map-arithmetic` | Add, subtract, mask, smooth, threshold or normalise density maps (NumPy, no VMD; VMD's own `volutil` did not load) | NumPy and SciPy results |
| `vmd-agent vmd prepare-namd` | Write a NAMD input file (CHARMM36, PME, minimise then equilibrate) for a built system | the box, atoms and parameter files match the system; **never run in NAMD** |
| `vmd-agent vmd slurm-script` | Write a SLURM job script for a cluster (NAMD, a VMD script, or any command) | the requested resources appear in the script; **never run on a cluster** |

### One example each

```bash
vmd-agent vmd build-system 1ubq.pdb --out build/ubq --padding 10
vmd-agent vmd mutate-residue ubq.psf ubq.pdb P0 6 ALA --out ubq_K6A
vmd-agent vmd merge-structures a.psf a.pdb b.psf b.pdb --out merged
vmd-agent vmd build-membrane --out membrane --lipid POPC --x-size 80 --y-size 80
vmd-agent vmd build-nanotube --out tube.pdb --n 6 --m 6 --length-nm 10
vmd-agent vmd capabilities
vmd-agent vmd structure-check 1ubq.pdb
vmd-agent vmd pbc-info run.pdb run.dcd --step 10
vmd-agent vmd volume-info map.mrc
vmd-agent vmd measure run.pdb run.dcd --kind rgyr --step 10
vmd-agent vmd interactions run.pdb run.dcd --kind salt_bridges
vmd-agent vmd secondary-structure run.pdb run.dcd --step 5
vmd-agent vmd backbone-torsions 1ubq.pdb
vmd-agent vmd align-structures model.pdb reference.pdb --out aligned.pdb
vmd-agent vmd volmap run.pdb run.dcd --out water.dx --kind occupancy --selection "water and name OH2"
vmd-agent vmd convert-trajectory run.pdb run.dcd --out ca.dcd --selection "name CA" --step 5
vmd-agent vmd write-structure run.pdb run.dcd --out frame10.pdb --frame 10
vmd-agent vmd render-scene run.pdb run.dcd --scene scene.json --out picture.png
vmd-agent vmd render-turntable run.pdb --scene scene.json --out spin.mp4
vmd-agent vmd export-session run.pdb run.dcd --scene scene.json --out session1
vmd-agent vmd fit-to-map model.pdb map.mrc --resolution 6 --out fitted.pdb
vmd-agent vmd map-arithmetic a.dx subtract --map-b b.dx --out difference.dx
vmd-agent vmd prepare-namd system.psf system.pdb --out sim/equilibrate --temperature 310
vmd-agent vmd slurm-script equilibrate.namd --kind namd --gpus 1 --modules namd/3.0 --out run.sbatch
```

A scene file (`scene.json`) is a plain description; every key is optional except `reps` or `isosurfaces`:

```json
{"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure", "material": "AOShiny"},
          {"selection": "resname ALA", "style": "Licorice", "color": "Name"}],
 "isosurfaces": [{"file": "water.dx", "isovalue": 0.3, "style": "wireframe", "color": "ColorID 3"}],
 "background": "white", "rotate": [["x", 30], ["y", -30]], "zoom": 1.0, "projection": "Orthographic",
 "ambient_occlusion": true, "shadows": true}
```

Styles: `Lines Licorice VDW CPK NewCartoon QuickSurf Surf MSMS Trace Tube Beads ...`; colours: `Name Element ResName Chain Structure Beta
Charge ... ColorID <n>`; materials: `Opaque Transparent AOShiny Glossy Glass1 ...` (`vmd-agent vmd render-scene --help` and
`vmd-agent reps` list them).

### Reproducibility

A VMD user's first question about any number is "can I get it in my own VMD?". Three layers answer it:

1. **Every VMD tool saves the exact Tcl it ran.** The result carries `reproduce_script` (a file in `vmd_scripts/` next to your data) and
   `reproduce_with` (the command). Running it prints the same numbers as lines starting with `RESULT`. A test runs the saved script in
   plain VMD and compares.
2. **`export_vmd_session`** writes a folder: `session.tcl` (`vmd -e session.tcl` opens the scene in the GUI), `render.tcl` (headless
   Tachyon), your input files copied in so the paths are relative (the folder can be moved or sent to someone), `manifest.json` (the scene,
   the SHA-256 of every input, VMD's version) and `REPRODUCE.md`. The scene is loaded in a real VMD before the tool returns, and the result
   says how many molecules, atoms and representations it found.
3. **Provenance records** (`verify_provenance`) re-check hashes of the inputs and outputs of earlier runs.

`vmd_render_scene` and `export_vmd_session` share one generated script, so the exported scene is what was rendered.

### How much of VMD is this?

`vmd_capabilities` classifies every plugin of *your* VMD. The classes: **wrapped** (a tool does it), **library** (a helper other plugins
use), **gui_only** (a window with no scripting interface worth wrapping), **external_program** (needs NAMD, APBS, PROPKA, ...),
**not_wrapped** (scriptable, no tool yet) and **unclassified** (newer than the table in `vmdkit/capabilities.py`). The wrapper is therefore
not "all of VMD": the plugins that are windows or that drive another program are listed, not wrapped, and these scriptable ones are open:
coarse-graining, topotools writers (LAMMPS and GROMACS writers produced empty files in the one real test),
IR spectra, Brownian-dynamics tools, symmetry and atom typing helpers. A test fails when the
installed VMD has a plugin the table does not know, so the table cannot silently rot.

### Things that behave differently from what you might assume

* **Tested on one VMD:** 1.9.4a57, macOS Apple Silicon. Linux and Windows builds, other versions: untested.
* VMD **cannot write xtc or netcdf** (it reads them); `vmd_convert_trajectory` refuses those. Multi-frame **PDB** from VMD ends frames with a bare
  `END`; the tool rewrites it as `MODEL`/`ENDMDL` so other programs read the frames. Multi-frame **GRO** from VMD is several frames back to back;
  MDAnalysis reads only the first, VMD reads all.
* VMD's nanotube builder fails for zigzag tubes (`m = 0`: "domain error"); the tool says so up front.
* `volmap` has no frame-range option; the tool drops the frames you did not ask for and averages the rest. Mask and occupancy maps are therefore
  *fractions of frames*, not 0/1.
* SASA depends on VMD's atom radii; against an independent Shrake-Rupley with Bondi radii on heavy atoms it agrees to within about 15 %, not exactly.
* Ramachandran regions are coarse boxes, a way to find residues worth a look, not a validation score.
* Salt bridges use the oxygen-nitrogen distance criterion of the `saltbr` plugin, computed with VMD's `measure contacts`.
* The Timeline, Hydrogen Bonds and other windows are not opened; their computations are done headless.

## 7. Check and keep records

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent provenance PATH` | re-check the hashes of the inputs and outputs of an earlier run | none |
| `vmd-agent report SESSION_DIR` | assemble a written report from a finished session | `--out FILE` · `--title TEXT` |
| `vmd-agent probe-video VIDEO` | read a video's metadata and prove it decodes (uses the bundled ffmpeg) | `--count-frames` |
| `vmd-agent interpret-video VIDEO` | verify a video and pull out stills you can map back to simulation frames | `-n N` stills · `--out-dir DIR` · `--timestamps ...` · `--stride N` · `--first-frame N` · `--time-per-frame T` · `--time-unit` · `--count-frames` |
| `vmd-agent validate TOP TRAJ` | cross-check the analysis against independent NumPy | `--sel` · `--sel2` · `--cutoff` |
| `vmd-agent validate-dssp ID_OR_FILE ...` | compare the secondary-structure code with the PDB's own annotations | `--cache DIR` · `--mdtraj` |
| `vmd-agent bench ...` | the research benchmark, also in a container with your VMD (`vmd-agent bench docker`) | see [Development](#running-and-reproducing) and [Docker](#docker) |

## Other commands

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent setup` | first-time setup: finds VMD, picks your files folder, sets up the AI | `--yes` accept defaults · `--check` only show the settings · `--use local\|online\|app\|skip` · `--model NAME` · `--data-dir FOLDER` · `--vmd PATH` |
| `vmd-agent` (or `menu`) | the numbered menu | none |
| `vmd-agent chat ["question"]` | talk to the tools with a language model | see [Ways to work](#ways-to-work) |
| `vmd-agent doctor` | what this computer has, whether VMD really starts, which chat model is ready, what to do next | none |
| `vmd-agent models` | the suggested free models, with the date they were checked | `--check` ask the Ollama library again |
| `vmd-agent start ["question"]` | the Docker route: picks native or Docker from the facts and starts the chat | `--mode auto\|docker\|native` · `--model` · `--data-dir` · `--base-url` · `--print-plan` (show, run nothing) · `--down` (stop the containers) |
| `vmd-agent probe` / `vmd-agent renderers` | what VMD, drawing backends and libraries this computer has | `--vmd PATH` |
| `vmd-agent mcp-config` | the settings that connect Claude Desktop / Code to the tools | `--write` add them to Claude Desktop (with a backup) · `--roots FOLDER ...` · `--vmd PATH` |
| `vmd-agent mcp-check` | test an MCP server install the way a real client uses it | `--roots` · `--vmd` · `--render` · `--command` · `--args` · `--env KEY=VALUE` |
| `vmd-agent tools` | list every tool the chat and MCP server offer | `--group all\|core\|vmd` |
| `vmd-agent tool NAME '{json}'` | run any one tool with its arguments as JSON | example: `vmd-agent tool probe_environment '{}'` |

`vmd-agent --help` shows every command grouped in the order of this page; `vmd-agent <command> --help` shows one command's flags.

**Flags that mean the same everywhere**

| Flag | Meaning |
|---|---|
| `--traj FILE` (also `--trajectory`) | the trajectory that goes with the structure |
| `--sel "..."` (also `--selection`), `--sel2 "..."` | a VMD atom selection, and a second one |
| `--vmd PATH` | use this VMD instead of the one found automatically |
| `--out-dir DIR`, `-o FILE`, `--out PATH` | where results are written |
| `--views`, `--focus`, `--rep`, `--renderer`, `--style`, `--bg` | how pictures look |
| `--step N` | use every Nth frame |
| `--json` | machine-readable output where a command prints a summary |
| `--yes` | accept the defaults without asking (setup) |
| `--full` | everything, not shortened (the `vmd` commands) |

## If something goes wrong

| What you see | What to do |
|---|---|
| `vmd-agent: command not found` | use the full path `~/vmd-agent/bin/vmd-agent` (the installer does not change your PATH on purpose), or run the install line again |
| the model answers without looking at your files, or ignores its tools | the model is too small, or its context is too short: use `granite4.1:8b` or larger, and if you run your own Ollama set `OLLAMA_CONTEXT_LENGTH=16384` |
| "cannot reach the model server" | run `vmd-agent setup` again (it starts it); if you use your own Ollama, start it. `vmd-agent setup --check` shows what is reachable. |
| "VMD was found but did not run" | the message names the likely cause (for example Linux needs `tcsh`: `sudo apt install tcsh`). `vmd-agent doctor` repeats it. |
| It cannot find VMD | `vmd-agent setup --vmd "<VMD's folder>"`. VMD is optional: without it, pictures use the built-in drawing. |
| "outside the allowed roots" | the AI can only use your files folder; put the file there, or choose another with `vmd-agent setup --data-dir` |
| the model's answers are poor or wrong | a small model may be the cause: try a larger one (`vmd-agent setup`, option 1) or an online model. `vmd-agent claims` checks any statement against the data. |
| anything else | run `vmd-agent doctor` and read its notes |

## What has and has not been verified

| | |
|---|---|
| **Verified by running** | the analysis and structure code (against independent implementations by procedures you can repeat, see the [development guide](#4-reproduce-the-validation-checks)); the tools against **a real VMD 1.9.4a57 on macOS Apple Silicon** and a real ffmpeg; the setup logic, menu and settings; `install.sh` from a local copy; the private Ollama download and start; a real chat with `granite4.1:8b` calling the tools; both MCP SDK generations |
| **Never run** | the one-line installer URLs (the repository is private for now, so they cannot be fetched), `install.ps1`, Linux, anything on Windows; any model other than the two named above; VMD on Linux or Windows and any other VMD version; the Docker images and route; any real MCP client; a NAMD run of the written input and a SLURM run of the written script |
| **Results** | **none are included.** This repository ships no measured results, benchmark scores or model evaluations; everything is produced by running the commands on your own data. |

Tests that need something the machine lacks are **skipped with the reason shown, never counted as passed**. Run everything with
`python scripts/dev.py test` (lint, dead-code check, the whole suite, every skip listed).

The repository also holds a **benchmark** (*can an LLM agent carry out VMD analysis and visualization workflows correctly, and say so
when it cannot?*): six task families with answers known by construction, scored on success and **silent errors**. `vmd-agent` is one
entrant in it, not the presumed winner, and the model that wrote the benchmark must not run it. How to run it:
[development guide](#5-run-the-automation-benchmark); the design: [research paper](docs/RESEARCH.md); the draft analysis plan:
[preregistration draft](docs/RESEARCH.md#part-ii-preregistration-draft).

---

# Reference

For integrators and developers. Everything above is enough to use the toolkit.

## Use it from an MCP client

Optional. The chat (`vmd-agent chat`) needs no MCP client; this is for people who already use Claude Code, Claude Desktop or another MCP client.

The same 53 tools are available to any MCP client (Claude Code, Claude Desktop and others) through an MCP server. The server exposes the 53 tools below to an MCP client (Claude Code, Claude Desktop, or any other) over stdio. This
section is everything needed to run it on a **Linux machine that has VMD installed**.

### 1. What the Linux machine needs

| Need | Detail | Required? |
|---|---|---|
| **Python >= 3.10** | `python3 --version`. The MCP SDK needs it; the rest of the toolkit also runs on 3.9. | yes |
| **The toolkit with the server extra** | `python3 -m venv ~/vmd-agent-venv && ~/vmd-agent-venv/bin/pip install -e ".[server]"` (add `.[sasa]` for SASA analysis). Both MCP SDK generations (1.x and 2.x) are supported. | yes |
| **A data directory** | everything the agent reads or writes must be inside it (see the sandbox below) | yes |
| **VMD** | for VMD renders. Without it the server still works and draws with the built-in matplotlib renderer. | optional |
| `tcsh` and VMD's shared libraries | VMD's `vmd` launcher is a tcsh script, and the binary links OpenGL/X11 libraries even when run headless. `docker/Dockerfile` lists the Debian packages used for this (`tcsh libgl1 libglu1-mesa libx11-6 libxi6 libxinerama1 libxft2 libfontconfig1 libxext6 libxrender1`). That list is **untested against a real VMD**. | only with VMD |
| **Tachyon** | ships inside a VMD install (`tachyon_LINUXAMD64` or similar). The VMD renderer needs it to make images. | only with VMD |
| `ffmpeg` | only for the movie and video tools (`render_movie`, `probe_video`, `validate_video`, `interpret_video`, `extract_video_frames`) | optional; a copy comes with the `imageio-ffmpeg` dependency, so nothing to install |
| Outbound HTTPS | only for `fetch_structure`, `fetch_and_visualize` and `search_pdb` (RCSB, UniProt, AlphaFold) | optional |

No display is needed: VMD is always run headless (`-dispdev text`).

### 2. Check the install before connecting a client

Run these **as the same user the server will run as**:

```bash
~/vmd-agent-venv/bin/vmd-agent probe          # does this machine have VMD, Tachyon, ffmpeg, the libraries?
~/vmd-agent-venv/bin/vmd-agent mcp-check --roots /srv/md-data --vmd /opt/vmd/bin/vmd --render
```

`mcp-check` starts the server and talks to it with the real MCP client over stdio, which is what your client will do. It
gives the server **only** the environment you pass it (MCP clients typically do not forward your shell's exports or
`PATH`, and the SDK's own client does not), so a variable that works in your terminal but is missing from the client's
configuration shows up here. It reports:
`connect` (the server starts and speaks MCP), `tools` (53 registered), `analysis_libraries`, `vmd` and `tachyon` (found?
which version?), `ffmpeg`, the sandbox (a path outside the roots is refused; relative paths resolve inside the first root),
whether the raw Tcl tool is disabled, and with `--render` a real VMD + Tachyon render of a tiny structure. `FAIL` means a
client cannot work; `WARN` means reduced capability or a risk (no VMD, no sandbox). Exit code 2 on any `FAIL`.

### 3. Connect a client

The server command is the console script `vmd-agent-server` in the virtualenv (use its **absolute path**; a client does
not activate your virtualenv). Do not assume your shell's environment reaches the server; **list the variables you
need in the client's configuration**:

* `VMD_AGENT_ALLOWED_ROOTS`: the directory (or several, separated by `:`) the agent may read and write. **Set it.**
* `VMD_BIN`: your VMD launcher or install directory. Without it the server looks on `PATH` and a few common locations;
  do not rely on that.

**a. Claude Code on the same Linux machine**

```bash
claude mcp add vmd-agent \
  -e VMD_BIN=/opt/vmd/bin/vmd -e VMD_AGENT_ALLOWED_ROOTS=/srv/md-data \
  -- /home/you/vmd-agent-venv/bin/vmd-agent-server
```

(Check `claude mcp add --help` for your version's exact flags; then `claude mcp list` should show it connected.)

**b. A client on another machine (for example Claude Desktop on your laptop), over SSH**

The server runs on the Linux machine; the client starts it through `ssh`. Use key-based, non-interactive SSH, and make
sure the remote shell prints **nothing** on login (no banners, no output from `.bashrc`): anything written to stdout other
than MCP messages corrupts the connection. (The SSH route and the `claude mcp add` flags have **not been tested by the
author**; `mcp-check --command ssh --args -T you@linux-host "<remote command>"` tests the same path.)

```json
{ "mcpServers": { "vmd-agent": {
    "command": "ssh",
    "args": ["-T", "you@linux-host",
             "env VMD_BIN=/opt/vmd/bin/vmd VMD_AGENT_ALLOWED_ROOTS=/srv/md-data /home/you/vmd-agent-venv/bin/vmd-agent-server"] } } }
```

**c. Any client on the same machine (JSON config)**

```json
{ "mcpServers": { "vmd-agent": {
    "command": "/home/you/vmd-agent-venv/bin/vmd-agent-server",
    "env": { "VMD_BIN": "/opt/vmd/bin/vmd", "VMD_AGENT_ALLOWED_ROOTS": "/srv/md-data" } } } }
```

**d. In Docker with your VMD mounted** (Linux host, VMD build matching the image architecture; the image has no VMD of
its own). Build the `vmd-libs` image first (see [Docker](#docker)); **never built or run by the
author**:

```json
{ "mcpServers": { "vmd-agent": { "command": "docker",
    "args": ["run", "-i", "--rm", "--read-only", "--tmpfs", "/tmp", "--tmpfs", "/home/vmdagent", "--cap-drop", "ALL",
             "-v", "/srv/md-data:/data", "-v", "/opt/vmd:/opt/vmd:ro", "-e", "VMD_BIN=/opt/vmd/bin/vmd",
             "vmd-agent:hostvmd"] } } }
```

Inside the container the data directory is `/data` and the sandbox is already set to it. Without VMD, use the plain
`vmd-agent` image and drop the VMD lines.

### 4. How the server behaves

* **The sandbox.** With `VMD_AGENT_ALLOWED_ROOTS` set, every path a tool receives (inputs *and* output directories) must
  resolve inside one of the roots, with symlinks, `..` and prefix tricks resolved. **A relative path is taken relative
  to the first root**, not to the server's working directory, so a tool's default output directory (`vmd_agent_output`)
  lands inside it. **With it unset the sandbox is off** and the server prints a warning to stderr.
* **`run_vmd_tcl` is disabled** (it returns a refusal) unless the server environment has `VMD_AGENT_ENABLE_TCL=1`. The
  Tcl screen is an accident guard, not a security boundary: enable it only for a client and agent you trust.
* **Downloads** refuse non-http(s) URLs and loopback/private/link-local hosts (also after redirects). Optional:
  `VMD_AGENT_ALLOW_PRIVATE_URLS=1` for an internal mirror, `VMD_AGENT_MAX_DOWNLOAD_MB` for the size cap.
* **Renderers.** `renderer="auto"` uses VMD when it and Tachyon are found, otherwise matplotlib; every result says which
  drew the pictures. `view_image` returns images, so the client must support image content.
* **Logs** go to stderr only; stdout is the protocol stream. If you wrap the server in your own script, print nothing to
  stdout.

### 5. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| client says the server exited / will not connect | run the exact command by hand and read stderr; usual causes: Python < 3.10, `mcp` not installed in *that* environment, or a relative or wrong path to `vmd-agent-server`. `mcp-check --command <your command>` tests the same command. |
| tool results say `vmd_found: false` | `VMD_BIN` is not in the **client's** `env` block. Your shell's `PATH` and exports may not be forwarded. |
| `path ... is outside the allowed roots` | the path (or an output directory) is not under `VMD_AGENT_ALLOWED_ROOTS`; use a path inside it, or add the directory to the roots. |
| renders fall back to "matplotlib" though VMD is installed | Tachyon was not found next to VMD, or VMD does not run headless here (missing `tcsh` or libraries). `vmd-agent probe` shows `tachyon_path`; try `vmd -dispdev text -eof` by hand. |
| `VMD did not produce a Tachyon scene` | VMD started but failed: run `mcp-check --render`, then run VMD by hand with a small script. Use `renderer="matplotlib"` meanwhile. |
| the connection works over SSH for a while, then breaks | something on the remote side wrote to stdout (login banner, `.bashrc` output). Make the remote shell silent. |
| movies or video tools fail | `vmd-agent probe` shows whether ffmpeg was found (the bundled copy normally is); check that the server runs in the environment where vmd-agent was installed. |

53 tools. The original 27: `probe_environment` · `inspect_files` · `detect_system` · `generate_visualization_recipe` · `structure_stats` ·
`color_key` · `annotate_image` · `list_representations` · `describe_representation` · `render_image` · `render_movie` ·
`run_vmd_tcl` · `search_pdb` · `fetch_structure` · `fetch_and_visualize` · `visualize_and_interpret` ·
`analyze_trajectory` · `select_keyframes` · `verify_claims` · `verify_provenance` · `extract_video_frames` ·
`probe_video` · `validate_video` · `interpret_video` · `view_image` · `record_visual_interpretation` · `assemble_report`. The 24 that drive VMD itself ([Driving VMD itself](#6-drive-vmd-itself)): `vmd_capabilities` · `vmd_measure` · `vmd_interactions` · `vmd_secondary_structure` · `vmd_backbone_torsions` · `vmd_structure_check` · `vmd_align_structures` · `vmd_pbc_info` · `vmd_convert_trajectory` · `vmd_write_structure` · `vmd_volmap` · `vmd_volume_info` · `vmd_build_system` · `vmd_mutate_residue` · `vmd_merge_structures` · `vmd_render_scene` · `vmd_render_turntable` · `vmd_build_membrane` · `vmd_build_nanotube` · `export_vmd_session` · `vmd_fit_to_map` · `vmd_map_arithmetic` · `vmd_prepare_namd` · `vmd_slurm_script`. And the two that run whole jobs ([Whole jobs](#5-run-a-whole-job-and-get-a-report)): `list_workflows` · `run_workflow`.

## Development

### How the tools fit together

1. `probe_environment` → pick a renderer (`vmd` or `matplotlib`).
2. `inspect_files` → `detect_system` → `structure_stats`.
3. `visualize_and_interpret` / `fetch_and_visualize` → a **grounded package**: images, a legend tying every colour to a
   detected component, colour keys, statistics, a what-to-look-for checklist, renderer caveats, provenance.
4. `view_image` each image, then write the interpretation.
5. `analyze_trajectory` (+ `select_keyframes`, `interpret_video`) for dynamics.
6. **`verify_claims`** on your own write-up. Unparsed sentences were not checked.
7. `record_visual_interpretation` → `assemble_report`.


#### Renderers

| Backend | Needs | Strength | Limits |
|---|---|---|---|
| `vmd` | your VMD install (+ Tachyon) | publication quality, all focus modes | not bundled; licence |
| `matplotlib` | nothing extra | always available; VMD palette so legends stay true | backbone **trace** (not ribbons), no occlusion or shading, no surface/pocket modes |

`renderer="auto"` uses VMD when present, otherwise matplotlib. Every package says which renderer drew the
images and lists its caveats; the legend is generated from what that renderer actually drew.


#### The research benchmark commands

Every other command is in [Every command](#ways-to-work). The benchmark ones (`vmd-agent bench <action>`; `vmd-agent bench --help`):

| Action | What it does |
|---|---|
| `agent-suite` | generate automation tasks whose answers are known by construction |
| `agent-preflight` | check that a run can work: VMD, key, container, selections, secrets |
| `agent-plan` | estimate calls, tokens and cost (no model is called) |
| `agent-run` | run scripted baselines and/or a model on a suite |
| `agent-compare` | the paired difference between two runs, with a cluster-bootstrap interval |
| `truth`, `run`, `synth`, `events`, `sampling`, `rating-sheet`, `rating-summary` | the grounding study and its supporting studies |

### Contributing and publishing

* **Set up for development:** `pip install -e ".[dev]"` (the `dev` extra is pytest, hypothesis, pyyaml, ruff and vulture; `".[all]"` adds the optional parts).
* **Check everything:** `python scripts/dev.py test` runs lint, the dead-code check and the whole suite (CI runs the same command).
* **Publish to GitHub:** `python scripts/dev.py publish` (`--no-push` for a local commit only; `--branch NAME`; `GITHUB_REPO=owner/name` to publish elsewhere; `--skip-workflows` if your token lacks the `workflow` scope). It starts a git
  repository if there is none, starts a new branch from the remote's main or fast-forwards a branch you already published (it never overwrites or forces), refuses to commit anything that looks like a secret (an API key, a private key, a saved `llm_key`) or any file over 5 MB
  outside `tests/data`, shows what it will commit, then pushes with the GitHub CLI or tells you the two commands to run by hand.
* **`.gitignore`** keeps out caches and build output, editor files, everything vmd-agent writes while running (`vmd_scripts/`, `vmd_agent_output/`,
  `pdb_cache/`, `/data/`), anything that could hold a key (`.env`, `settings.json`, `/config/`), and VMD itself (`docker/vmd-dist/*`, which UIUC's
  licence forbids committing). A test checks that these stay ignored and that the test data stay tracked.

### Running and reproducing

#### 1. Install

```bash
git clone https://github.com/OmidMLdata/AGENTIC_VMD_v2.git && cd AGENTIC_VMD_v2
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # core + tests. Python >= 3.9
pip install -e ".[server]"         # + the MCP server (Python >= 3.10; mcp 1.x and 2.x both work)
pip install -e ".[bench]"          # + the Anthropic SDK, to run a model on the benchmark
pip install mdtraj                 # optional: independent DSSP for `validate-dssp`
pip install -e ".[all]"            # everything above (Python >= 3.10)
```

VMD is **optional** and never bundled. For VMD rendering and the plain-VMD benchmark arm, install it yourself from
UIUC, then `export VMD_BIN=/path/to/vmd` (a launcher or its install directory). `vmd-agent probe` shows what was found.
ffmpeg comes with the install (the `imageio-ffmpeg` package); a system ffmpeg on the PATH is used first when there is one. The bundled
build has no `ffprobe`, so video metadata and frame counts are then read with `ffmpeg` itself.

#### 2. Run the tests

```bash
python scripts/dev.py test    # lint + dead-code check + the whole suite, skip reasons listed; works on every OS
pytest -rs                    # or just the tests
```

Tests that need something the machine lacks are skipped with the reason shown (`requires_vmd`, `requires_ffmpeg`,
`requires_mcp`, `requires_network`, `requires_api`). **A skip means "not verified here", not "passed".** Run only the
real-VMD tests with `pytest -m requires_vmd -rs`. Live model tests spend a few cents and need
`VMD_AGENT_LIVE_TESTS=1` and `ANTHROPIC_API_KEY`.

#### 3. Use the toolkit

```bash
vmd-agent chat                                               # talk to it with a local or hosted model
vmd-agent probe                                              # what this machine can do
vmd-agent visualize tests/data/1ubq.pdb --renderer matplotlib --views front iso
vmd-agent claims tests/data/1lyz.pdb "It has 4 disulfide bridges" "It has a membrane"
vmd-agent analyze system.psf traj.dcd --do rmsd rmsf rgyr contacts convergence --dt-ps 400
vmd-agent keyframes system.psf traj.dcd -k 9 --render
```

MCP server: see [Use it from an MCP client](#use-it-from-an-mcp-client); `vmd-agent mcp-check` verifies an install.

#### 4. Reproduce the validation checks

Each command computes its numbers locally from your files and prints them. Nothing is stored in the repository.

```bash
# analysis vs independent NumPy, on any topology + trajectory
vmd-agent validate system.pdb traj.dcd --sel2 "resname LIG" --cutoff 6

# built-in DSSP vs the PDB's own annotations; downloads the entries
vmd-agent validate-dssp 1CRN 1MBN 2LZM 1UBQ --cache pdb_cache
# ... and vs MDTraj's independent DSSP on local files (pip install mdtraj)
vmd-agent validate-dssp my1.pdb my2.pdb --mdtraj

# event-aware vs uniform keyframes on YOUR real trajectory, with injected events, plus a no-event control
vmd-agent bench events top.pdb traj.dcd --trials 100 --frames 300 -k 9 --seed 0
vmd-agent bench sampling --n-frames 1000 -k 9 --trials 200          # idealised AR(1) version

# novel-structure generator checked against its own design (prints agreement per property)
vmd-agent bench synth 100 --out synth --seed 1
```

The generator is **not reproducible across machines from the seed alone** (floating-point differences between NumPy
builds change discrete choices). Keep the generated files; `design.json` records a SHA-256 for each.

#### 5. Run the automation benchmark

```bash
# a. tasks with answers known by construction (use your own trajectories; one is not enough for statistics)
vmd-agent bench agent-suite --out suite --seed 100 \
    --base top1.pdb traj1.dcd --base top2.pdb traj2.dcd --structures real/*.pdb --synthetic-dir synth

# b. prove the setup before spending anything: VMD, selection scoring, sandbox, key
vmd-agent bench agent-preflight --suite suite --arms vmd_agent python_mdanalysis vmd_plain \
    --allow-exec --model anthropic:<model-id>              # add --live-api for one tiny real call

# c. scripted baselines: no model, no network. They check the scorers; they are not model results
vmd-agent bench agent-run --suite suite --baselines oracle sloppy reference --out-dir out_baselines

# d. estimate cost (calls no model; no prices are built in)
vmd-agent bench agent-plan --suite suite --labels 6 --repeats 3 --price-in <USD/M tokens> --price-out <USD/M tokens>

# e. a real model. python/Tcl arms run model-written code: use a container or VM
#    open-source model (Ollama or any OpenAI-compatible server):  --model openai:granite4.1:8b --base-url http://localhost:11434/v1
#    hosted Anthropic model (needs ANTHROPIC_API_KEY):             --model anthropic:<model-id>
vmd-agent bench agent-run --suite suite --model anthropic:<model-id> \
    --arms vmd_agent vmd_agent_no_verify python_mdanalysis vmd_plain --allow-exec --repeats 3 --out-dir out
```

Compare two runs (label A minus label B, repeats averaged, cluster-bootstrap interval; use `--alpha 0.0167` for the three
confirmatory hypotheses in the preregistration):

```bash
vmd-agent bench agent-compare out/records.jsonl --a "anthropic:<id>@vmd_agent" --b "anthropic:<id>@python_mdanalysis" --metric silent_error
```

Outputs in `--out-dir`: `records.jsonl` (every run), `summary.md` and `summary.json`, `manifest.json` (versions, VMD,
renderer, container flag, suite hash; no secrets). Every run uses a fresh copy of its task workspace, and the runner
refuses a suite whose files changed.

**In Docker with your own VMD** (VMD is never baked into an image you could publish):

```bash
export ANTHROPIC_API_KEY=...                     # a dedicated key with a spending limit
export DATA_DIR=$PWD/data                        # your trajectories; the suite and outputs go here too
vmd-agent bench docker preflight --mode withvmd --arms vmd_agent python_mdanalysis vmd_plain --allow-exec --model anthropic:<id>
vmd-agent bench docker suite --mode withvmd --out /data/suite --seed 100 --base /data/top.pdb /data/traj.dcd --structures /data/real/*.pdb
vmd-agent bench docker run --mode withvmd --suite /data/suite --out-dir /data/out --repeats 3 --allow-exec --model anthropic:<id> --arms vmd_agent python_mdanalysis
```

`--mode withvmd` builds VMD from a **Linux** tarball you place in `docker/vmd-dist/`; `--mode hostvmd` with `VMD_HOME=...` mounts a
Linux install. A Mac's VMD.app cannot run in a Linux container (run natively instead). Details:
[Running the benchmark with your VMD](#running-the-benchmark-with-your-vmd-and-your-key).

#### 6. Run the grounding component study

```bash
vmd-agent bench run real/*.pdb --synthetic-dir synth --dry-run --repeats 3 --price-in <USD/M> --price-out <USD/M>
vmd-agent bench run real/*.pdb --synthetic-dir synth --model anthropic:<model-id> --out-dir out_grounding --repeats 3
vmd-agent bench run real/*.pdb --model stats-reader --renderer matplotlib --out-dir out_offline   # offline control, no key
```

#### 7. Before a confirmatory run

Fill the `TODO` fields in [preregistration draft](docs/RESEARCH.md#part-ii-preregistration-draft), freeze the toolkit version, generate the
suite from data not used in development, **deposit the generated suite directory**, tag and file the plan, and only then
run the model. The model that wrote the benchmark must not run it or analyse its results.

## Architecture

### Design decisions

1. **Evidence, not conclusions.** The toolkit prepares and verifies evidence and says how it was obtained. The
   model interprets. Nothing here claims to have watched a video or understood a picture.
2. **VMD is optional.** It cannot be redistributed (UIUC licence), so every capability has a path without it and
   VMD is a pluggable renderer.
3. **Say what was actually done.** `bond_source`, `hbond_method`, `time_axis`, `renderer.caveats`,
   `passed: null` for unchecked expectations, `frames_visually_inspected_by_agent: false`.
4. **Fail closed.** Missing tools degrade to a structured result; unparsed claims are not guessed; too little data
   gives `insufficient_data`, never "stable".

### Layout follows the pipeline

```
 inputs ──► structure ──► dynamics ──► visual ──► evidence          bench (on top)
 get data   one frame     trajectories draw       verify + record    measure the model
```

```
src/vmd_agent/
  cli.py          command-line surface (mirrors the tools)
  settings.py     remembered choices (files folder, VMD, model): per-OS config file, private, never raises
  wizard.py       `vmd-agent setup` and the plain-language menu behind a bare `vmd-agent`
  platform_info.py  OS, CPU, Docker, GPU, Ollama; where VMD and client configs live on each OS
  launcher.py     `vmd-agent start` / `doctor`: picks native or Docker from the facts and runs it
  toolset.py      the 53 tools as plain functions + JSON schemas (no MCP, no AI client); the 27 original ones are `CORE_TOOLS`
  vmd_tools.py    the 24 tools that drive VMD itself, built on vmdkit/ (each saves the Tcl it ran)
  workflows.py    named multi-step jobs (structure_overview, equilibration_check, ...): findings, a verdict, a report
  reporting.py    writes report.md / report.html from a workflow: findings, figures, caveats, methods, checksums, the Tcl
  progress.py     what a long job reports as it runs, and who listens (the terminal, the chat)
  models.py       the dated catalogue of suggested open-source models + a live registry check
  ollama_local.py a private copy of Ollama inside the vmd-agent folder (checksum-verified download)
  server.py       MCP surface: registers the toolset with the MCP SDK
  chat.py         `vmd-agent chat`: the tools given to an OpenAI-compatible model (local or hosted)
  llm_client.py   stdlib client for the OpenAI-style chat API (Ollama, llama.cpp, vLLM, LM Studio, hosted)
  mcp_check.py    `vmd-agent mcp-check`: starts the server and checks it with the real MCP client
  auto.py         one-call pipelines: fetch_and_visualize, visualize_and_interpret
  environment.py  find VMD/Tachyon/ffmpeg, list renderers
  security.py     path sandbox, Tcl deny-list

  vmdkit/         script (run generated Tcl in headless VMD, parse results) · measure · interactions · structure · trajectory
                  volumetric · build · scene (render + export_session) · maps (cryo-EM fitting, map arithmetic) · prepare (NAMD, SLURM) · capabilities (plugin coverage map)
  inputs/         molio      load_universe + native mmCIF reader
                  volume     read OpenDX / CCP4 / MRC / cube / Situs maps
                  fetch      RCSB / AlphaFold / URL, with a safe downloader
                  inspection classify files, flag missing companions
  structure/      detect     components, system type, integrity checks
                  stats      bonds, disulfides, H-bonds, salt bridges, chain counts
                  dssp       Kabsch-Sander DSSP in NumPy
  dynamics/       analysis   RMSD/RMSF/Rg/H-bonds/contacts/SASA/density/convergence, PBC, time axis
                  timeseries autocorrelation-aware statistics and verdicts
                  keyframes  change-point frame selection + sampling theory
  visual/         recipes, representations, colorkey, annotate
                  render     VMD driver (one session, fixed camera, scratch cleanup)
                  renderers/ interface + VMD backend + registry (__init__), mpl (open-source backend)
  evidence/       claims     statements -> measurements -> verdicts
                  validation vs independent NumPy; DSSP vs PDB annotations and MDTraj
                  provenance versions, hashes, exact Tcl
                  media      video evidence (ffmpeg; ffprobe if present, else read through ffmpeg)
                  report     Session + the A-M Markdown report
  bench/          grounding study: truth, questions, conditions, models, scorer, runner (+ cost planner)
  bench/agent/    automation benchmark: suite (tasks + truth), tools (arms, sandboxed env), agents, scoring, runner
                  synth      procedural novel structures with measured truth
                  events     real-noise event study
                  sampling   AR(1) sampling study
                  rating_study  blinded expert-rating instrument
```

Dependencies point one way, and **`tests/system/test_layering.py` enforces it** (every import, including lazy
ones; no cycles):

| unit | may import |
|---|---|
| `inputs`, `llm_client`, `platform_info`, `settings`, `models`, `progress` | nothing else in the package |
| `security` | `settings` (the saved files folder is the default sandbox) |
| `ollama_local` | `platform_info`, `settings` |
| `environment` | `platform_info`, `settings` |
| `structure` | `inputs`, `security` (to sanitise residue names from files) |
| `dynamics` | `inputs`, `structure` |
| `visual` | `inputs`, `structure`, `environment`, `security` |
| `evidence` | `inputs`, `structure`, `dynamics`, `environment`, `security` |
| `vmdkit` | `inputs`, `structure`, `visual`, `environment`, `security`, `progress` |
| `bench` | all of the above, `auto` and `llm_client` |
| `auto.py`, `cli.py`, `server.py`, `toolset.py`, `vmd_tools.py`, `vmd_cli.py`, `workflows.py`, `reporting.py`, `chat.py`, `launcher.py`, `wizard.py`, `mcp_check.py`, `__init__.py` | anything: they are the only places that compose units |

`dynamics` and `visual` are siblings and never import each other, which is why rendering the chosen keyframes
(`auto.select_keyframes`) and the renderer inventory (`auto.probe_environment`) live in `auto.py`.

### The three pipelines

`fetch_and_visualize(id)`: fetch → inspect → detect → recipe → **render (chosen backend)** → annotate → package
(legend, keys, statistics, checklist, caveats, provenance).
`visualize_and_interpret(topology, trajectory)`: the same for local files.
`interpret_video(video)`: probe → decode-verify → exact-frame stills → QC → source-frame map → manifest.

### Recurring contracts

1. Every public function returns a JSON-serialisable `dict`.
2. Degrade, don't crash: missing VMD/ffmpeg/Pillow gives a structured note.
3. State the method (bond source, H-bond criterion, DSSP source, renderer, axis).
4. The agent interprets; the code prepares and verifies.

### Tests

`tests/` mirrors `src/vmd_agent/` (`inputs/ structure/ dynamics/ visual/ evidence/ bench/`) plus `surfaces/`
(the server through the real MCP SDK, CLI) and `system/` (security, environment). About 700 tests, a few minutes; `python scripts/dev.py test` runs everything.
Real data in `tests/data/`. **Nothing stands in for another program.** Tests that need a real VMD/Tachyon, ffmpeg, the MCP SDK
(Python >= 3.10), the network or a live model are marked `requires_vmd`, `requires_ffmpeg`, `requires_mcp`,
`requires_network`, `requires_api` and are **skipped, with the reason shown**, where that is missing: run `pytest -rs`
to see what did not run, and read a skip as "unverified here". Live model tests also need `VMD_AGENT_LIVE_TESTS=1`
(they spend a few cents). Full coverage needs `pip install -e ".[all]"` on Python >= 3.10 and a machine with VMD. An
independent NeRF builder validates DSSP; independent NumPy re-implementations cross-validate the analysis.

---

## Methods

*Every algorithm and threshold.*

Every algorithm, its parameters, and its known limits.

### Structure loading
`molio.load_universe` builds an MDAnalysis `Universe`. mmCIF is parsed natively: the first `_atom_site`
loop, **model 1 only**, first alternate location, auth_* identifiers preferred, CIF quoting rules respected
(`O5'`). Residues are contiguous runs of (chain, resid, resname, insertion code).

### Component detection (`detect`)
Residue-name sets for water, ions, lipids; MDAnalysis `protein`/`nucleic` keywords; the rest is
"ligand/other". **Material/inorganic** needs ≥ 50 atoms of an unambiguous element (Si, Au, Ag, Pt, Pd, Ti,
Al, Mo, W, Cr, Sn, Ge, Ga, As, B) or ≥ 500 of an element that is also common in biology (S, Fe, Zn, Cu, Ni).
Integrity checks: atom pairs closer than 0.5 Å (sampled to 40 k atoms) and residue-numbering gaps.
Limit: residue-name based; non-standard naming defeats it.

### Bonds (`stats`)
Explicit topology bonds are used only when there are ≥ 0.6 per non-ion atom. PDB files normally carry only
`CONECT` records, so fewer than that is treated as **partial** and supplemented by distance inference:
bond if `d ≤ r_cov(i) + r_cov(j) + 0.45 Å`, free monatomic ions excluded, skipped above 60 k atoms.
`bond_source` always states what happened.

### Hydrogen bonds
* **With hydrogens:** H···A ≤ 2.5 Å and D–H···A ≥ 120°, acceptor O, different residues, water excluded
  (in `stats`; the trajectory analysis lets the selection decide). Parent heavy atom = nearest within 1.3 Å.
* **Without hydrogens:** N/O heavy-atom pairs within 3.5 Å (≥ 2.2 Å), different residues. Labelled
  `distance_only` because this overestimates.

### Salt bridges, disulfides
Salt bridge: Asp OD1/OD2 or Glu OE1/OE2 within 4.0 Å of Lys NZ or Arg NH1/NH2/NE, counted per residue
pair (His excluded by default). Disulfide: Cys SG–SG within 2.5 Å.

### Secondary structure (`dssp`)
Kabsch & Sander (1983): amide H placed 1.0 Å from N opposite the preceding C=O; bond if
`0.084·332·(1/r_ON + 1/r_CH − 1/r_OH − 1/r_CN) < −0.5 kcal/mol` for CA–CA < 9 Å. n-turns (3,4,5) → G/H/I,
bridges → B/E (ladders of ≥ 2 are E), then T and S (bend > 70°). 3-state: H/G/I → helix, E/B → sheet.
The tests check it on NeRF-built ideal helix and strand structures. To compare it with PDB annotations and MDTraj on
structures of your choice, run `vmd-agent validate-dssp <PDB ids> --cache DIR`; compare with `mkdssp` yourself.

### Time series (`timeseries`)
* **Statistical inefficiency** `g = 1 + 2 Σ (1 − t/N) C(t)`, truncated at the first non-positive
  autocorrelation (Chodera et al. 2007). `N_eff = N/g`. The tests compare it with `(1+φ)/(1−φ)` for AR(1).
* `g` for the drift tests is estimated on residuals of a **Theil-Sen linear fit**, so a real trend is not
  mistaken for autocorrelation (which would collapse `N_eff` and hide the drift).
* **Drift:** Mann-Kendall on the series thinned by `g`, plus first-half vs second-half difference in
  corrected standard errors. `drifting` needs p < 0.01 **and** |z| > 3.
* **Gate:** fewer than 10 effectively independent samples → `insufficient_data`, even if the data look monotone.
* `no_detectable_drift` ≠ converged. Equilibration start = index maximising `N_eff` of the tail.
* The false-positive rate of the drift test and the coverage of the confidence interval are properties to check on
  your own data lengths; the tests simulate stationary AR(1) series for this.

### Trajectory analysis (`analysis`)
Time axis uses `ts.time` only for readers that record it (XTC, TRR, DCD, NetCDF, H5MD, TNG, GRO) and
strictly increasing; otherwise the axis is `frame index` and the result says so. RMSD: superposition
to frame 0 (MDAnalysis `RMSD`). RMSF: per-residue mean of per-atom RMSF about the average structure, on a
**copy** of the universe. **PBC:** any atom moving > ½ box between frames flags the selection as *split*
(some atoms) or *whole-wrapped* (all); `unwrap=True` makes the selection whole using bonds (guessed if
absent).

### Event-aware keyframes (`keyframes`)
Signals: RMSD to frame 0, Rg, optionally COM distance, contacts, helix %. Score at index *i* =
|mean(next *w*) − mean(previous *w*)|, `w = max(3, n/25)`; standardised by the **median/MAD of the score
distribution itself** (adapts to autocorrelation and non-Gaussian noise); max over signals; non-maximum
suppression; keep z ≥ 6. Always keep first and last; spend ≤ 70 % of the rest on change points; fill by
bisecting the largest gaps. **Uniform sampling:** an event of *L* frames at random position is hit by *k*
evenly spaced frames with probability `min(1,(L+1)(k−1)/(n−1))` (verified by simulation).
Limit: only events that move a chosen signal are detectable.

### Claim verification (`claims`)
Sentences → structured claims via templates, otherwise `unparsed` (never guessed). A matched sentence is accepted
only if **every word** is accounted for by that claim type (`_ALLOWED`); anything else is a qualifier the measurement
does not check ("near the loop", "between residues 40 and 60", "intact", "for 40 ns", a second component) and the
sentence is returned unparsed with a note. Sentences over 400 characters are refused. An audit found the earlier
parser reduced such sentences to a weaker claim ("bridge the ligand and Asp 52" → "has water") and reported them
*supported*. Verdicts:
supported / contradicted / unverifiable. "Mostly helical" = helix ≥ 30 % and larger than the sheet fraction
(coil is the remainder, not a competing class). **Ligand burial** = 1 − SASA(ligand in complex)/SASA(ligand
alone), Shrake-Rupley, probe 1.4 Å, 240 points, Bondi radii; buried if ≥ 0.5. Dynamic claims reuse the
statistics above, so a short trajectory yields `unverifiable`, not support.

### Automation benchmark (`bench/agent`)

* **Tasks** are generated from real trajectories and structures; **truth is independent of any model and of the toolkit's
  analysis code**: RMSD by an NumPy Kabsch (`bench/events.kabsch_rmsd_series`), mass-weighted Rg, centre-of-geometry
  distance, a SciPy KD-tree for residue neighbourhoods and chain interfaces, injected events (known onset) and injected
  defects (periodic-boundary shift of one segment by one box length, topology with 5 atoms removed, NaN coordinates).
* **Scoring.** Numbers: `|x - t| <= max(atol, rtol*|t|)` (RMSD 3 %, Rg/distance 2 %, elapsed time 1 %). Events: onset in
  `[start - 5, end]`; controls require `null`. Diagnosis: the exact label; for a damaged file a number counts against the
  answer. Selections: exact atom-set equality, evaluated with `periodic=False`. Keyframes: distinct, non-blank images
  inside the workspace plus one frame within 5 of the event window. Report: claim verification, any contradicted claim fails.
* **Silent error** = answered, wrong, not abstained, no data problem flagged.
* **Statistics.** Differences paired by task (repeats averaged); bootstrap resamples *clusters* (trajectory or structure).
  Intervals use `alpha`, so a Bonferroni-corrected family is `alpha = 0.05/m`.
* **Events** are rigid hinge/translation/scaling on real ping-pong-extended noise (see the next section); 120 frames,
  abrupt (10-frame) and slow (30-frame) ramps.

### Real-noise event study (`bench/events`)
Real trajectory frames extended by ping-pong reflection (preserves every real frame-to-frame step; makes the base
signal periodic with period 2(F−1)). Events: `hinge` (first half of the residues rotates about a pivot near the
rest, ramping to the stated angle), `dissociation` (last ~10 % of residues translate away, ramping to the stated
distance), `expansion` (uniform scaling about the centroid). Ramp over `length` frames, then held. Signals:
Kabsch RMSD to frame 0, mass-weighted Rg, and moving-vs-rest COM distance for hinge/dissociation. Hit = a selected
frame inside the event window. Negative control = no event. The event is synthetic by design.

### Procedural structures (`bench/synth`)
NeRF-built ideal helices (φ,ψ = −57,−47) arranged on a ring with alternating direction; antiparallel strands in a
plane with spacing/register chosen by grid search so DSSP recognises them; coil = short random-φ,ψ pieces; 2-residue
straight linkers; chains replicated with random rotations ≥ 28 Å apart; ligand = a 6-atom ring, "buried" at the
clash-free point (≥ 3 Å from protein) with the highest Shrake-Rupley burial among 80 candidates, "exposed" ≥ 12 Å
outside; disulfides = residue pairs with CB atoms 3.4 to 6.2 Å apart and SG atoms placed 2.05 Å apart.
**Idealised and not physically realistic.**

### Analysis guards
`contacts` and `distance` require `sel2` (they used to default to the selection itself, comparing it with itself).
`analyze_trajectory` estimates the memory needed (all atoms of every kept frame as float32, doubled for the transient
stack) and refuses above `VMD_AGENT_MAX_MEMORY_GB` (default 4), returning the `step` that would fit.

### Time axis
`ts.time` is trusted only for readers that record it and only when strictly increasing; for DCD it is flagged
because headers often keep a default or pre-stride timestep. `dt_ps` overrides.

### Chain counting
`n_protein_chains` / `n_nucleic_chains` count chain IDs (or segment IDs) among polymer atoms only; `n_chains_all`
includes ligand/water chain IDs.

### Benchmark statistics
See [the grounding study](docs/RESEARCH.md#appendix-e-grounding-study-specification). Cluster bootstrap over structures (1000 resamples default); unpaired
cluster bootstrap for group gaps; difference-of-differences for the adjusted contamination estimate.

---

## Security

An MCP server lets a model read paths, write paths, download files and run Tcl on your machine. These
controls limit the damage; none is a complete sandbox. **The container is the real boundary.**

### Path sandbox
`VMD_AGENT_ALLOWED_ROOTS` (an `os.pathsep`-separated list) confines every path the **server tools** read
or write. Paths are resolved through symlinks, so `..`, symlink escapes and prefix-sibling tricks
(`/data-evil` vs `/data`) are blocked. Unset = unrestricted (fine for a single-user local install). The
Docker image sets it to `/data`. The CLI is operator-run and is not sandboxed.
`view_image` only serves image files.

### `run_vmd_tcl` is off by default
Tcl can run any program, and **no filter can stop it**: command names can be built at run time
(`set c ex; append c ec; $c cmd`, `catch $built_script`, `\x65xec`, `rename exec e`). A second audit confirmed this
with a real `tclsh`: scripts that passed the deny-list below created files. The first audit "closed" five specific bypasses,
which was true only for those strings. So the MCP tool is **disabled unless the server is started with
`VMD_AGENT_ENABLE_TCL=1`**, and enabling it means trusting the caller with code execution on that machine.

When enabled (or when calling `vmd_agent.visual.render.run_vmd_tcl` from your own code), a deny-list still rejects the obvious
dangerous commands, in command position (start of a line, or after `;` `[` `{` `"`): `exec`, `open`, `source`, `play`,
`socket`, destructive `file` operations, `cd`, `system`, `eval`, `uplevel`, `interp`, `subst`, `load`, `unix`,
`mol urlload`, `render <method> <file> <command>`, and `package require` outside a short allow-list. That catches accidents
and careless scripts. It is **not a boundary**, and the Tcl screen is not a path sandbox either (`mol load` reads any path).
`VMD_AGENT_ALLOW_UNSAFE_TCL=1` disables even the guard rail.

### Scripts the toolkit generates
The Tcl the toolkit writes itself (recipes, render scripts) is **not** passed through the screen, so every value
interpolated into it is validated instead (`security.tcl_path`, `tcl_selection`, `tcl_word`, `safe_resnames`):

* paths must not contain braces, backslashes or control characters;
* selections are a character whitelist; representation, colour and material names are letters/digits/spaces and the
  representation must be in the catalogue; `background` must be `white` or `black`;
* **residue names read from a structure file are filtered** (`^[A-Za-z0-9_+\-']{1,8}$`), because mmCIF allows arbitrary
  text. Before this was fixed a crafted file could close a Tcl brace and run commands when rendered with VMD.
  Rejected names are reported in `detect_system(...)["warnings"]`.

Violations return a structured error (`blocked: true`), never an exception.

### Downloads (`fetch`)
http(s) only (no `file://`, `ftp://`), hosts resolving to loopback/private/link-local/reserved addresses
refused, every redirect hop re-checked, body capped (default 1024 MB, `VMD_AGENT_MAX_DOWNLOAD_MB`),
gzip decompression capped. Not defended: DNS rebinding between check and request. Run the container without
internal-network access if that matters. `VMD_AGENT_ALLOW_PRIVATE_URLS=1` lifts the address rule.

### Container hardening
Non-root (uid 10001), read-only root, tmpfs `/tmp`, `--cap-drop ALL`, `no-new-privileges`, data at `/data`
only; `--network none` for analysis-only work.

### Not covered
Prompt injection through file *contents* (a PDB `REMARK` line is data the model may read); resource
exhaustion by very large trajectories; the security of VMD/ffmpeg themselves. Treat model-driven access to
sensitive data accordingly.

---

## Docker

### Why VMD is not in the image

VMD's license (<https://www.ks.uiuc.edu/Research/vmd/current/LICENSE.html>) lets you build tools that
interoperate with VMD and point users to the official download, but restricts redistributing VMD itself,
and requires a commercial license for commercial use. A published image containing VMD would likely
breach that. So the **published image is open source and contains no VMD**. VMD is something *you*
supply, on *your* machine. (This is not legal advice; contact `vmd@ks.uiuc.edu` before redistributing.)

> Also read [NOTICE.md](NOTICE.md): MDAnalysis is GPL-licensed, which affects redistributing an image
> that bundles it.

### Operating systems

All OS differences are in `platform_info.py` (and the few places that consume it), written as functions of the OS name so they are
tested for Linux, macOS and Windows from any OS: VMD install folders and file names (`vmd.exe` on Windows, the app bundle's
`vmd_MACOSX*` binary on macOS), Claude Desktop's config location, the Docker platform, case-insensitive path comparison for the sandbox,
Windows paths turned into forward slashes for Tcl, the Windows system variables a child process needs, a console that cannot show a
character, and the version check that no longer relies on a Linux/macOS-only device file. **Only macOS has been run by the author.**

### The all-in-one chat stack (`vmd-agent start`)

`vmd-agent start` (in Docker mode; `--down` stops it) runs `docker/chat.compose.yml`: an **Ollama** model server (official image, models
kept in a named volume so they download once) and the `vmd-agent` image running `vmd-agent chat`, with your `./data` folder
mounted at `/data` as the only place the agent can read or write (read-only root, no capabilities). If a Linux VMD tarball
is in `docker/vmd-dist/` the image is built with it (`VMD_TARGET=with-vmd`, never to be shared); otherwise figures use the
built-in renderer. `docker/chat.gpu.yml` adds NVIDIA GPU access when `nvidia-smi` and Docker's NVIDIA runtime are found.
A Mac's Docker cannot use its GPU, so the model runs on the CPU there. The default model `granite4.1:8b` is a suggestion
that has not been tested; choose another with `--model`. **Never run:** the tests check the compose structure, the plan the
launcher makes and the no-Docker error path only.

### Three images

| Target | Contains | Use |
|---|---|---|
| `runtime` (default) | Python, toolkit, ffmpeg, matplotlib renderer | everything except VMD rendering. **Safe to publish.** |
| `vmd-libs` | `runtime` + shared libraries VMD needs | mount **your** VMD at `/opt/vmd` |
| `with-vmd` | `vmd-libs` + VMD built from **your** tarball | local use only. **Never push.** |

```bash
# from the repository root
docker build -f docker/Dockerfile -t vmd-agent .                              # open-source image
docker build -f docker/Dockerfile --target vmd-libs -t vmd-agent:hostvmd .     # libs only
docker build -f docker/Dockerfile --target with-vmd -t vmd-agent:vmd-local .   # needs docker/vmd-dist/*.tar.gz
```

#### Open-source image

```bash
docker run --rm -v "$PWD/data:/data" vmd-agent probe
docker run --rm -v "$PWD/data:/data" vmd-agent \
    visualize /data/protein.pdb --out-dir /data/out --renderer matplotlib
docker run -i --rm -v "$PWD/data:/data" vmd-agent            # MCP server on stdio
```

#### With your VMD, mounted (Linux hosts)

Install VMD on a **Linux host of the same CPU architecture** (on a Mac use the baked-in image below), then:

```bash
docker run -i --rm \
  -v "$PWD/data:/data" -v /opt/vmd-1.9.4:/opt/vmd:ro \
  -e VMD_BIN=/opt/vmd/bin/vmd \
  vmd-agent:hostvmd
```

(or `VMD_HOME=/opt/vmd-1.9.4 docker compose -f docker/docker-compose.yml --profile hostvmd run --rm hostvmd probe`).

#### With VMD baked in (local use)

1. Download the Linux binary from the VMD site after accepting its license.
2. Put `vmd-*.tar.gz` in `docker/vmd-dist/`.
3. `docker build -f docker/Dockerfile --target with-vmd -t vmd-agent:vmd-local .`

The image is labelled `vmd-agent.redistributable=false`.

### Running the benchmark with your VMD (and your key)

Three ways to supply VMD. Pick by where you work:

| Route | When | Command prefix |
|---|---|---|
| **Native** | You run on the machine that has VMD (a Mac with VMD.app, or a Linux box). Simplest, but model-written code runs on your machine: use a disposable VM. | `vmd-agent bench ... --vmd <path>` |
| **Mounted VMD** (`--mode hostvmd`) | Linux host, VMD installed there, same CPU architecture as the image. | `VMD_HOME=/opt/vmd vmd-agent bench docker ... --mode hostvmd` |
| **Baked VMD** (`--mode withvmd`) | **Use this on a Mac.** Put the **Linux** VMD tarball in `docker/vmd-dist/`; it is installed inside a local image. Local use only; never push. | `vmd-agent bench docker ... --mode withvmd` |

A Mac's VMD.app is a macOS binary and **cannot run in a Linux container**, so mounting it fails (`vmd-agent bench docker
check-vmd` says so). VMD is also architecture-specific: the Linux tarball must match `VMD_PLATFORM` (default
`linux/amd64`; on Apple Silicon this runs under emulation, which is slow). Check what VMD offers for your CPU.

```bash
export ANTHROPIC_API_KEY=...        # a dedicated key with a spending limit; passed by name, never stored
export DATA_DIR=$PWD/data           # holds your trajectories; the suite and outputs go here too

vmd-agent bench docker preflight --mode withvmd --arms vmd_agent python_mdanalysis vmd_plain \
    --allow-exec --model anthropic:<id> --live-api            # first: prove VMD, selection, key, scrubbing
vmd-agent bench docker suite --mode withvmd --out /data/suite --seed 100 \
    --base /data/top.pdb /data/traj.dcd --structures /data/real/*.pdb
vmd-agent bench docker plan --mode withvmd --suite /data/suite --labels 6 --repeats 3 --price-in <USD/M> --price-out <USD/M>
vmd-agent bench docker run --mode withvmd --suite /data/suite --out-dir /data/out --repeats 3 --allow-exec \
    --model anthropic:<id> --arms vmd_agent vmd_agent_no_verify python_mdanalysis vmd_plain
```

Native equivalent: `vmd-agent bench agent-preflight --vmd "/Applications/VMD 1.9.4.app/Contents/vmd" --arms vmd_plain
--allow-exec --no-require-container`. On macOS the app's bare `vmd_MACOSX...` binary is found and `VMDDIR` is set for you
when it is unset.

**What `preflight` checks** (and `agent-run` re-runs, refusing to start if a blocking check fails): VMD found and
launching headless; a PDB loads and counts atoms; VMD evaluates a selection to 0-based indices (how the plain-VMD arm
is scored); `render TachyonInternal` writes an image (the plain-VMD arm's only way to make keyframe images); code
execution only with `--allow-exec` and only inside a container; model-written code sees no key, token or secret
variable; the key is set and the SDK installed; the suite and output directories exist. A model call is made only
with `--live-api`. The run's `manifest.json` records versions, the VMD path and version, the renderer, whether it ran in
a container and a hash of the suite, never a secret.

**What protects the key.** The benchmark process holds `ANTHROPIC_API_KEY`. Code the model writes (`run_python`,
`run_vmd_tcl`) runs with a **whitelisted environment** (search paths, locale, `VMD*`), so it cannot read the key. This is
not a sandbox: that code can still use the network from inside the container, so use a dedicated, spend-capped key and
a throwaway data directory. The container is also limited (`pids_limit`, `mem_limit`, read-only root, no
capabilities, no new privileges).

**Selections differ by arm.** For the plain-VMD arm the task asks for a *VMD* atom-selection string and a real VMD
scores it; every other arm uses MDAnalysis syntax. Results on the `selection` family therefore compare tool-native
syntax, not identical strings.

> **Status: never run against Docker or a Linux VMD.** Docker does not exist on the machine this was written on. The
> real-VMD tests (headless load, selection evaluation, rendering, the plain-VMD arm's workspace) were run once, on
> 2026-10-06, against VMD 1.9.4a57 on macOS Apple Silicon, and passed; they have not been run on Linux or Windows. What
> is tested without Docker: the shell scripts' syntax, the compose file's structure, the macOS-binary guard, the scrubbed
> environment, input screening before anything launches, preflight decisions, and the manifest. Whether `docker/install_vmd.sh` works for your tarball, whether the image
> builds, and whether VMD behaves headless in the container are unverified. `preflight` is how you find out, and
> `pytest -m requires_vmd -rs` runs the real-VMD tests on a machine that has it.

### Hardening used by the compose file

Non-root user (uid 10001), read-only root filesystem, tmpfs `/tmp` and `/home/vmdagent`, all capabilities dropped,
`no-new-privileges`, and `VMD_AGENT_ALLOWED_ROOTS=/data` so the **server** tools can only touch `/data`.
For analysis-only work add `--network none` (downloads from RCSB/AlphaFold then fail by design).

### Status: not yet built or run

The Dockerfile, entrypoint, compose file and `docker/install_vmd.sh` were written **without Docker available**.
They are syntactically checked (YAML parses) and the CI workflow builds the open-source image and smoke-tests
it on first push. In particular **`docker/install_vmd.sh` is untested against a real VMD tarball**; VMD's
`configure` layout varies between releases. If it fails, use the mounted-VMD route above.

Apple-silicon note: VMD's Linux builds are x86-64 (and some aarch64); mounting a host install requires the
same architecture as the container.

---

## More

[Research paper, preregistration and comparison with the original project](docs/RESEARCH.md) · [Changelog](CHANGELOG.md) · [Notices](NOTICE.md)

MIT licence ([LICENSE](LICENSE)). Third-party notes, including **VMD and MDAnalysis (GPL)**: [NOTICE.md](NOTICE.md).
