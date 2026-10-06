# vmd-agent

A toolkit **and a benchmark** for LLM-driven molecular visualization and trajectory analysis (VMD-style workflows):
an MCP server, CLI and Python library that let an agent inspect, measure, render and verify, plus a benchmark that
measures how well agents automate these workflows and whether they **fail loudly or silently**.

> **VMD is optional and not bundled** (UIUC licence). Everything works without it using an open-source
> renderer. See [NOTICE.md](NOTICE.md) and [docs/TECHNICAL.md](docs/TECHNICAL.md#docker).

## Status

| | |
|---|---|
| **Toolkit** | loads PDB/mmCIF/PSF/DCD/XTC, classifies systems, measures structure and dynamics, renders figures, detects damaged data, verifies statements; sandboxed MCP server. Its measurements are checked against independent implementations by procedures you can run yourself (see **How to run**). |
| **Automation benchmark** | *can an LLM agent carry out analysis and visualization workflows correctly, and say so when it cannot?* Six task families with answers known by construction; arms compare tool access (plain Python, plain VMD, this toolkit, ablations); scored on success and **silent errors**. |
| **Results** | **None are included.** This repository ships no measured results, no benchmark scores and no model evaluations. Everything is produced by running the commands below on your own data. |

Not verified by the author: real VMD (none was available, so tests that need it are marked `requires_vmd` and are
**skipped, not passed**, where VMD is absent), the Docker images, any live model, any real MCP client. The benchmark
should not be run by the same model that wrote it. `vmd-agent` is **one entrant** in the benchmark, not the presumed
winner. The study design is in [docs/PAPER.md](docs/PAPER.md) and the draft analysis plan in
[docs/PREREGISTRATION.md](docs/PREREGISTRATION.md).

## How to run

### 1. Install

```bash
git clone <this repo> && cd <this repo>
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # core + tests. Python >= 3.9
pip install -e ".[server]"         # + the MCP server (Python >= 3.10; mcp 1.x and 2.x both work)
pip install -e ".[bench]"          # + the Anthropic SDK, to run a model on the benchmark
pip install mdtraj                 # optional: independent DSSP for `validate-dssp`
pip install -e ".[all]"            # everything above (Python >= 3.10)
```

VMD is **optional** and never bundled. For VMD rendering and the plain-VMD benchmark arm, install it yourself from
UIUC, then `export VMD_BIN=/path/to/vmd` (a launcher or its install directory). `vmd-agent probe` shows what was found.

### 2. Run the tests

```bash
pytest -rs
```

Tests that need something the machine lacks are skipped with the reason shown (`requires_vmd`, `requires_ffmpeg`,
`requires_mcp`, `requires_network`, `requires_api`). **A skip means "not verified here", not "passed".** Run only the
real-VMD tests with `pytest -m requires_vmd -rs`. Live model tests spend a few cents and need
`VMD_AGENT_LIVE_TESTS=1` and `ANTHROPIC_API_KEY`.

### 3. Use the toolkit

```bash
vmd-agent probe                                              # what this machine can do
vmd-agent visualize tests/data/1ubq.pdb --renderer matplotlib --views front iso
vmd-agent claims tests/data/1lyz.pdb "It has 4 disulfide bridges" "It has a membrane"
vmd-agent analyze system.psf traj.dcd --do rmsd rmsf rgyr contacts convergence --dt-ps 400
vmd-agent keyframes system.psf traj.dcd -k 9 --render
```

MCP server: see [MCP server](#mcp-server) below; `vmd-agent mcp-check` verifies an install.

### 4. Reproduce the validation checks

Each command computes its numbers locally from your files and prints them. Nothing is stored in the repository.

```bash
# analysis vs independent NumPy, on any topology + trajectory
vmd-agent validate system.pdb traj.dcd --sel2 "resname LIG" --cutoff 6

# built-in DSSP vs the PDB's own annotations (and vs MDTraj if installed); downloads the entries
vmd-agent validate-dssp 1CRN 1MBN 2LZM 1UBQ --cache pdb_cache

# event-aware vs uniform keyframes on YOUR real trajectory, with injected events, plus a no-event control
vmd-agent bench events top.pdb traj.dcd --trials 100 --frames 300 -k 9 --seed 0
vmd-agent bench sampling --n-frames 1000 -k 9 --trials 200          # idealised AR(1) version

# novel-structure generator checked against its own design (prints agreement per property)
vmd-agent bench synth 100 --out synth --seed 1
```

The generator is **not reproducible across machines from the seed alone** (floating-point differences between NumPy
builds change discrete choices). Keep the generated files; `design.json` records a SHA-256 for each.

### 5. Run the automation benchmark

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

# e. a real model (needs ANTHROPIC_API_KEY). python/Tcl arms run model-written code: use a container or VM
vmd-agent bench agent-run --suite suite --model anthropic:<model-id> \
    --arms vmd_agent vmd_agent_no_verify python_mdanalysis vmd_plain --allow-exec --repeats 3 --out-dir out
```

Outputs in `--out-dir`: `records.jsonl` (every run), `summary.md` and `summary.json`, `manifest.json` (versions, VMD,
renderer, container flag, suite hash; no secrets). Every run uses a fresh copy of its task workspace, and the runner
refuses a suite whose files changed.

**In Docker with your own VMD** (VMD is never baked into an image you could publish):

```bash
export ANTHROPIC_API_KEY=...                     # a dedicated key with a spending limit
export DATA_DIR=$PWD/data                        # your trajectories; the suite and outputs go here too
MODE=withvmd docker/bench.sh preflight --arms vmd_agent python_mdanalysis vmd_plain --allow-exec --model anthropic:<id>
MODE=withvmd docker/bench.sh suite --out /data/suite --seed 100 --base /data/top.pdb /data/traj.dcd --structures /data/real/*.pdb
MODE=withvmd docker/bench.sh run --suite /data/suite --out-dir /data/out --repeats 3 --allow-exec --model anthropic:<id> --arms vmd_agent python_mdanalysis
```

`MODE=withvmd` builds VMD from a **Linux** tarball you place in `docker/vmd-dist/`; `MODE=hostvmd VMD_HOME=...` mounts a
Linux install. A Mac's VMD.app cannot run in a Linux container (run natively instead). Details:
[docs/TECHNICAL.md](docs/TECHNICAL.md#running-the-benchmark-with-your-vmd-and-your-key).

### 6. Run the grounding component study

```bash
vmd-agent bench run real/*.pdb --synthetic-dir synth --dry-run --repeats 3 --price-in <USD/M> --price-out <USD/M>
vmd-agent bench run real/*.pdb --synthetic-dir synth --model anthropic:<model-id> --out-dir out_grounding --repeats 3
vmd-agent bench run real/*.pdb --model stats-reader --renderer matplotlib --out-dir out_offline   # offline control, no key
```

### 7. Before a confirmatory run

Fill the `TODO` fields in [docs/PREREGISTRATION.md](docs/PREREGISTRATION.md), freeze the toolkit version, generate the
suite from data not used in development, **deposit the generated suite directory**, tag and file the plan, and only then
run the model. The model that wrote the benchmark must not run it or analyse its results.

## Repository layout

```
.
├── src/vmd_agent/
│   ├── cli.py · server.py · auto.py       entry points; one-call pipelines
│   ├── environment.py · security.py       host probing; path sandbox, Tcl screen, URL policy
│   ├── inputs/      molio (native mmCIF) · fetch · inspection
│   ├── structure/   detect · stats · dssp
│   ├── dynamics/    analysis · timeseries · keyframes
│   ├── visual/      recipes · representations · colorkey · annotate · render · renderers/(vmd, mpl)
│   ├── evidence/    claims · validation · provenance · media · report
│   └── bench/       automation benchmark: agent/{suite · tools · agents · scoring · runner}
│                    grounding study: truth · questions · conditions · models · scorer · runner
│                    shared: synth · events · sampling · rating_study
├── tests/           mirrors src/: inputs/ structure/ dynamics/ visual/ evidence/ bench/ surfaces/ system/
│   └── data/        4 real PDBs, a real 20 ns ubiquitin MD (50 frames), a synthetic sample system
├── docs/            PAPER · TECHNICAL (architecture, methods, security, Docker) · PREREGISTRATION (draft) · history/
├── docker/          Dockerfile · docker-compose.yml · entrypoint · install_vmd.sh · vmd-dist/ (your VMD tarball)
├── .github/workflows/ci.yml
└── pyproject.toml · LICENSE · NOTICE.md · CHANGELOG.md
```

The subpackages follow the pipeline: **inputs → structure → dynamics → visual → evidence**, with
`bench/` on top. Details in [docs/TECHNICAL.md](docs/TECHNICAL.md#architecture).

## What it does

| Capability | VMD needed? | Notes |
|---|---|---|
| Inspect files, flag missing companions (DCD without PSF…) | no | |
| Load PDB / PSF / GRO / XTC / DCD / … **and mmCIF** | no | mmCIF read natively (MDAnalysis cannot) |
| Detect components + system type, integrity checks | no | |
| Bonds, disulfides, **angle-based H-bonds**, salt bridges, **DSSP** | no | each result states *how* it was obtained |
| Tailored VMD/Tcl recipes, 12-representation catalogue, focus modes | no | |
| Render views | **optional** | VMD+Tachyon or **matplotlib** (open source) |
| Render movies | VMD + ffmpeg | one VMD session, fixed camera |
| Trajectory analysis (RMSD, RMSF, Rg, H-bonds, contacts, distance, SASA, density, convergence) | no | autocorrelation-aware statistics, honest time axes, PBC diagnostics |
| Event-aware keyframe selection | no | change points instead of uniform stills |
| Claim verification | no | supported / contradicted / unverifiable / unparsed |
| Video probing, decode check, QC, still→source-frame mapping | ffmpeg | evidence, never "I watched it" |
| Provenance records (versions, hashes, exact Tcl) | no | `vmd-agent provenance <dir>` re-verifies |
| Automation benchmark: task suite with known answers, tool arms, scorers, runner, cost planner | no | [docs/PAPER.md](docs/PAPER.md#5-the-automation-benchmark) |
| Grounding component study: truth, conditions, scorer, novel structures | no | [docs/PAPER.md](docs/PAPER.md#appendix-e-grounding-study-specification) |
| Validation: vs NumPy; DSSP vs PDB annotations and MDTraj | no | `vmd-agent validate`, `validate-dssp` |

## The agent loop

1. `probe_environment` → pick a renderer (`vmd` or `matplotlib`).
2. `inspect_files` → `detect_system` → `structure_stats`.
3. `visualize_and_interpret` / `fetch_and_visualize` → a **grounded package**: images, a legend tying every colour to a
   detected component, colour keys, statistics, a what-to-look-for checklist, renderer caveats, provenance.
4. `view_image` each image, then write the interpretation.
5. `analyze_trajectory` (+ `select_keyframes`, `interpret_video`) for dynamics.
6. **`verify_claims`** on your own write-up. Unparsed sentences were not checked.
7. `record_visual_interpretation` → `assemble_report`.

## MCP server

The MCP server exposes the 27 tools below to an MCP client (Claude Code, Claude Desktop, or any other) over stdio. This
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
| `ffmpeg` | only for the movie and video tools (`render_movie`, `probe_video`, `validate_video`, `interpret_video`, `extract_video_frames`) | optional |
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
`connect` (the server starts and speaks MCP), `tools` (27 registered), `analysis_libraries`, `vmd` and `tachyon` (found?
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
its own). Build the `vmd-libs` image first (see [docs/TECHNICAL.md](docs/TECHNICAL.md#docker)); **never built or run by the
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
| movies or video tools fail | `ffmpeg` is not on the server's `PATH` (the client may not forward yours; set `PATH` in its `env` block). |

27 tools: `probe_environment` · `inspect_files` · `detect_system` · `generate_visualization_recipe` · `structure_stats` ·
`color_key` · `annotate_image` · `list_representations` · `describe_representation` · `render_image` · `render_movie` ·
`run_vmd_tcl` · `search_pdb` · `fetch_structure` · `fetch_and_visualize` · `visualize_and_interpret` ·
`analyze_trajectory` · `select_keyframes` · `verify_claims` · `verify_provenance` · `extract_video_frames` ·
`probe_video` · `validate_video` · `interpret_video` · `view_image` · `record_visual_interpretation` · `assemble_report`.

## CLI

```bash
vmd-agent probe | renderers
vmd-agent inspect|detect|stats system.psf [--traj traj.dcd]
vmd-agent show 1UBQ [--renderer matplotlib]                 # fetch + render + interpret
vmd-agent visualize system.psf --traj traj.dcd --renderer auto
vmd-agent analyze system.psf traj.dcd --do rmsd rmsf rgyr contacts convergence [--unwrap] [--dt-ps 400]
vmd-agent keyframes system.psf traj.dcd -k 9 --sel2 "resname LIG" [--render]
vmd-agent claims system.pdb "The ligand is buried" "It has 4 disulfide bridges"
vmd-agent validate system.psf traj.dcd --sel2 "resname LIG"
vmd-agent validate-dssp 1CRN 1MBN 2LZM --cache pdb_cache
vmd-agent provenance ./vmd_agent_output
vmd-agent bench agent-suite|agent-preflight|agent-run|agent-plan ...   # automation benchmark
vmd-agent bench truth|run|synth|events|sampling|rating-sheet|rating-summary ...   # grounding study
vmd-agent report ./session --out report.md
```

## Renderers

| Backend | Needs | Strength | Limits |
|---|---|---|---|
| `vmd` | your VMD install (+ Tachyon) | publication quality, all focus modes | not bundled; licence |
| `matplotlib` | nothing extra | always available; VMD palette so legends stay true | backbone **trace** (not ribbons), no occlusion or shading, no surface/pocket modes |

`renderer="auto"` uses VMD when present, otherwise matplotlib. Every package says which renderer drew the
images and lists its caveats; the legend is generated from what that renderer actually drew.

## Documentation

[PAPER](docs/PAPER.md) (the whole study as a research paper; appendices hold the research-question map, the grounding-study
specification and the verification record) ·
[PREREGISTRATION](docs/PREREGISTRATION.md) (draft analysis plan) ·
[TECHNICAL](docs/TECHNICAL.md) ([architecture](docs/TECHNICAL.md#architecture), [methods](docs/TECHNICAL.md#methods), [security](docs/TECHNICAL.md#security), [Docker](docs/TECHNICAL.md#docker)) ·
[CHANGELOG](CHANGELOG.md) · [changes from the original project](docs/history/CHANGES_FROM_ORIGINAL.md)

MIT licence ([LICENSE](LICENSE)). Third-party notes, including **VMD and MDAnalysis (GPL)**: [NOTICE.md](NOTICE.md).
