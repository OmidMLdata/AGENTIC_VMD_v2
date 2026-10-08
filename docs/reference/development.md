# Development

## How the tools fit together

1. `probe_environment` → pick a renderer (`vmd` or `matplotlib`).
2. `inspect_files` → `detect_system` → `structure_stats`.
3. `visualize_and_interpret` / `fetch_and_visualize` → a **grounded package**: images, a legend tying every colour to a
   detected component, colour keys, statistics, a what-to-look-for checklist, renderer caveats, provenance.
4. `view_image` each image, then write the interpretation.
5. `analyze_trajectory` (+ `select_keyframes`, `interpret_video`) for dynamics.
6. **`verify_claims`** on your own write-up. Unparsed sentences were not checked.
7. `record_visual_interpretation` → `assemble_report`.


### Renderers

| Backend | Needs | Strength | Limits |
|---|---|---|---|
| `vmd` | your VMD install (+ Tachyon) | publication quality, all focus modes | not bundled; licence |
| `matplotlib` | nothing extra | always available; VMD palette so legends stay true | backbone **trace** (not ribbons), no occlusion or shading, no surface/pocket modes |

`renderer="auto"` uses VMD when present, otherwise matplotlib. Every package says which renderer drew the
images and lists its caveats; the legend is generated from what that renderer actually drew.


### The research benchmark commands

Every other command is in [Every command](../guide/using.md#ways-to-work). The benchmark ones (`vmd-agent bench <action>`; `vmd-agent bench --help`):

| Action | What it does |
|---|---|
| `agent-suite` | generate automation tasks whose answers are known by construction |
| `agent-preflight` | check that a run can work: VMD, key, container, selections, secrets |
| `agent-plan` | estimate calls, tokens and cost (no model is called) |
| `agent-run` | run scripted baselines and/or a model on a suite |
| `agent-compare` | the paired difference between two runs, with a cluster-bootstrap interval |
| `truth`, `run`, `synth`, `events`, `sampling`, `rating-sheet`, `rating-summary` | the grounding study and its supporting studies |

## Contributing

* **Set up for development:** `pip install -e ".[dev]"` (the `dev` extra is pytest, hypothesis, pyyaml, ruff and vulture; `".[all]"` adds the optional parts).
* **Check everything:** `ruff check src tests`, `vulture` and `pytest -q -rs` (lint, dead-code check, the whole suite with every skip listed; CI runs the same three).
* **Testing with a real model:** the suite runs the real tools and the real code around the model but not a model (slow, varies from run to run, not installed everywhere). One lane does, and fails when a
  change makes the agent worse: `VMD_AGENT_LIVE_LLM_MODEL=granite4.1:8b VMD_AGENT_LLM_URL=http://localhost:11434/v1 pytest tests/live -rs`. It runs the benchmark's small set
  (`vmd-agent bench models --smoke`: one or two tasks per kind of functionality) through the agent with `VMD_AGENT_LIVE_TOOLS` (default `all`, what the chat uses; `auto` and `core` also work), and fails if the share passed falls below
  `VMD_AGENT_LIVE_MIN_SUCCESS` (default 0.5; set it a little below what your model scores), if the server fails, or if a request that must be declined is answered with an invented result.
  To compare a change, run `bench models --smoke` before and after into the same `--out-dir` and read `summary.md`.
* **Test every tool:** `vmd-agent bench tools` runs all 44 tools on a generated dataset whose answers are known by construction, with the seconds each took ([the tool test set](../benchmarks/tool-test-set.md)); the same cases run inside `pytest`.
* **`.gitignore`** keeps out caches and build output, editor files, everything vmd-agent writes while running (`vmd_scripts/`, `vmd_agent_output/`,
  `pdb_cache/`, `/data/`), anything that could hold a key (`.env`, `settings.json`, `/config/`), and VMD itself (`docker/vmd-dist/*`, which UIUC's
  licence forbids committing). A test checks that these stay ignored and that the test data stay tracked.

## Running and reproducing

### 1. Install

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
UIUC, then `export VMD_BIN=/path/to/vmd` (a launcher or its install directory). `vmd-agent tool probe_environment` shows what was found.
ffmpeg comes with the install (the `imageio-ffmpeg` package); a system ffmpeg on the PATH is used first when there is one. The bundled
build has no `ffprobe`, so video metadata and frame counts are then read with `ffmpeg` itself.

### 2. Run the tests

```bash
ruff check src tests && vulture   # lint + dead-code check (settings are in pyproject.toml)
pytest -q -rs                      # the whole suite; every skip is listed with its reason
```

Tests that need something the machine lacks are skipped with the reason shown (`requires_vmd`, `requires_ffmpeg`,
`requires_mcp`, `requires_network`, `requires_api`). **A skip means "not verified here", not "passed".** Run only the
real-VMD tests with `pytest -m requires_vmd -rs`. Live model tests spend a few cents and need
`VMD_AGENT_LIVE_TESTS=1` and `ANTHROPIC_API_KEY`.

### 3. Use the toolkit

```bash
vmd-agent chat                                               # talk to it with a local or hosted model
vmd-agent tool probe_environment                             # what this machine can do
vmd-agent tool visualize_and_interpret tests/data/1ubq.pdb --renderer matplotlib --views front iso
vmd-agent tool verify_claims tests/data/1lyz.pdb "It has 4 disulfide bridges" "It has a membrane"
vmd-agent tool analyze_trajectory system.psf traj.dcd --analyses rmsd rmsf rgyr contacts convergence --dt-ps 400
vmd-agent tool select_keyframes system.psf traj.dcd --k 9 --render
```

MCP server: see [Use it from an MCP client](../guide/mcp.md#use-it-from-an-mcp-client); `vmd-agent mcp-check` verifies an install.

### 4. Reproduce the validation checks

Each command computes its numbers locally from your files and prints them. Nothing is stored in the repository.

```bash
# analysis vs independent NumPy, on any topology + trajectory
vmd-agent bench validate system.pdb traj.dcd --sel2 "resname LIG" --cutoff 6

# built-in DSSP vs the PDB's own annotations; downloads the entries
vmd-agent bench validate-dssp 1CRN 1MBN 2LZM 1UBQ --cache pdb_cache
# ... and vs MDTraj's independent DSSP on local files (pip install mdtraj)
vmd-agent bench validate-dssp my1.pdb my2.pdb --mdtraj

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
[Running the benchmark with your VMD](../guide/docker.md#running-the-benchmark-with-your-vmd-and-your-key).

### 6. Run the grounding component study

```bash
vmd-agent bench run real/*.pdb --synthetic-dir synth --dry-run --repeats 3 --price-in <USD/M> --price-out <USD/M>
vmd-agent bench run real/*.pdb --synthetic-dir synth --model anthropic:<model-id> --out-dir out_grounding --repeats 3
vmd-agent bench run real/*.pdb --model stats-reader --renderer matplotlib --out-dir out_offline   # offline control, no key
```

### 7. Before a confirmatory run

Fill the `TODO` fields in [preregistration draft](RESEARCH.md#part-ii-preregistration-draft), freeze the toolkit version, generate the
suite from data not used in development, **deposit the generated suite directory**, tag and file the plan, and only then
run the model. The model that wrote the benchmark must not run it or analyse its results.
