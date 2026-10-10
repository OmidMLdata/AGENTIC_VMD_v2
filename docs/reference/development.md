# Development

## What is in this repository

```
src/vmd_agent/     the package: the agent, the tool library, VMD wrappers (vmdkit/), analysis, drawing, the web page (ui_assets/), the benchmarks
install/           the one-line installers (install.sh for Mac and Linux, install.ps1 for Windows)
docker/            Dockerfile, compose files and helpers for the container routes
docs/              the manual: guide/ (using it), benchmarks/ (choosing a model), reference/ (architecture, methods, security, research), CHANGELOG and NOTICE
tests/             the test suite, laid out like the package
.github/           CI
```

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


### The benchmark commands

Every other command is in [Every command](../guide/using.md#ways-to-work). The benchmark ones (`vmd-agent bench <action>`; `vmd-agent bench --help`):

| Action | What it does |
|---|---|
| `tools` | run every tool on a generated dataset whose answers are known by construction ([the tool test set](../benchmarks/tool-test-set.md)) |
| `models` | put language models in front of the tools, graded by a program ([the model benchmark](../benchmarks/model-benchmark.md)) |
| `dataset` | write the tool test set's files and stop |
| `validate`, `validate-dssp` | cross-check the toolkit's numbers against independent code (below) |
| `synth` | generate novel structures with known properties |

## Contributing

* **Set up for development:** `pip install -e ".[dev]"` (the `dev` extra is pytest, hypothesis, pyyaml, ruff and vulture; `".[all]"` adds the optional parts).
* **Check everything:** `ruff check src tests`, `vulture` and `pytest -q -rs` (lint, dead-code check, the whole suite with every skip listed; CI runs the same three).
* **Testing with a real model:** the suite runs the real tools and the real code around the model but not a model (slow, varies from run to run, not installed everywhere). One lane does, and fails when a
  change makes the agent worse: `VMD_AGENT_LIVE_LLM_MODEL=granite4.1:8b VMD_AGENT_LLM_URL=http://localhost:11434/v1 pytest tests/live -rs`. It runs the benchmark's small set
  (`vmd-agent bench models --smoke`: one or two tasks per kind of functionality) through the agent with `VMD_AGENT_LIVE_TOOLS` (default `all`, what the chat uses; `auto` and `core` also work), and fails if the share passed falls below
  `VMD_AGENT_LIVE_MIN_SUCCESS` (default 0.5; set it a little below what your model scores), if the server fails, or if a request that must be declined is answered with an invented result.
  To compare a change, run `bench models --smoke` before and after into the same `--out-dir` and read `summary.md`.
* **Test every tool:** `vmd-agent bench tools` runs all 57 tools on a generated dataset whose answers are known by construction, with the seconds each took ([the tool test set](../benchmarks/tool-test-set.md)); the same cases run inside `pytest`.
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
real-VMD tests with `pytest -m requires_vmd -rs`. Live model tests need a model server (see "Testing with a real model" below).

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

# novel-structure generator checked against its own design (prints agreement per property)
vmd-agent bench synth 100 --out synth --seed 1
```

The generator is **not reproducible across machines from the seed alone** (floating-point differences between NumPy
builds change discrete choices). Keep the generated files; `design.json` records a SHA-256 for each.
