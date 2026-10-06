# Technical reference

Architecture, methods, security model and Docker. For the research questions and evidence see
[PAPER.md](PAPER.md).

**Contents:** [Architecture](#architecture) · [Methods](#methods) · [Security](#security) · [Docker](#docker)

---

## Architecture

**v0.7.0 · 27 MCP tools · CLI · library**

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
  server.py       MCP surface: 27 tools, sandboxed
  mcp_check.py    `vmd-agent mcp-check`: starts the server and checks it with the real MCP client
  auto.py         one-call pipelines: fetch_and_visualize, visualize_and_interpret
  environment.py  find VMD/Tachyon/ffmpeg, list renderers
  security.py     path sandbox, Tcl deny-list

  inputs/         molio      load_universe + native mmCIF reader
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
                  media      ffprobe/ffmpeg video evidence
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
| `inputs`, `environment`, `security` | nothing else in the package |
| `structure` | `inputs`, `security` (to sanitise residue names from files) |
| `dynamics` | `inputs`, `structure` |
| `visual` | `inputs`, `structure`, `environment`, `security` |
| `evidence` | `inputs`, `structure`, `dynamics`, `environment`, `security` |
| `bench` | all of the above and `auto` |
| `auto.py`, `cli.py`, `server.py`, `mcp_check.py`, `__init__.py` | anything: they are the only places that compose units |

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
(the server through the real MCP SDK, CLI) and `system/` (security, environment). About 500 tests, about a minute.
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
See [the grounding study](PAPER.md#appendix-e-grounding-study-specification). Cluster bootstrap over structures (1000 resamples default); unpaired
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

> Also read [NOTICE.md](../NOTICE.md): MDAnalysis is GPL-licensed, which affects redistributing an image
> that bundles it.

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
| **Mounted VMD** (`MODE=hostvmd`) | Linux host, VMD installed there, same CPU architecture as the image. | `MODE=hostvmd VMD_HOME=/opt/vmd docker/bench.sh ...` |
| **Baked VMD** (`MODE=withvmd`) | **Use this on a Mac.** Put the **Linux** VMD tarball in `docker/vmd-dist/`; it is installed inside a local image. Local use only; never push. | `MODE=withvmd docker/bench.sh ...` |

A Mac's VMD.app is a macOS binary and **cannot run in a Linux container**, so mounting it fails (`docker/bench.sh
check-vmd` says so). VMD is also architecture-specific: the Linux tarball must match `VMD_PLATFORM` (default
`linux/amd64`; on Apple Silicon this runs under emulation, which is slow). Check what VMD offers for your CPU.

```bash
export ANTHROPIC_API_KEY=...        # a dedicated key with a spending limit; passed by name, never stored
export DATA_DIR=$PWD/data           # holds your trajectories; the suite and outputs go here too

MODE=withvmd docker/bench.sh preflight --arms vmd_agent python_mdanalysis vmd_plain \
    --allow-exec --model anthropic:<id> --live-api            # first: prove VMD, selection, key, scrubbing
MODE=withvmd docker/bench.sh suite --out /data/suite --seed 100 \
    --base /data/top.pdb /data/traj.dcd --structures /data/real/*.pdb
MODE=withvmd docker/bench.sh plan --suite /data/suite --labels 6 --repeats 3 --price-in <USD/M> --price-out <USD/M>
MODE=withvmd docker/bench.sh run --suite /data/suite --out-dir /data/out --repeats 3 --allow-exec \
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

> **Status: never run against Docker or a real VMD.** Neither exists on the machine this was written on. What is
> tested without them: the shell scripts' syntax, the compose file's structure, the macOS-binary guard, the scrubbed
> environment, input screening before anything launches, preflight decisions, and the manifest. The tests that need a
> real VMD (headless load, selection evaluation, rendering, the plain-VMD arm) are in the suite, skip where VMD is
> absent, and have never been run by the author. Whether `install_vmd.sh` works for your tarball, whether the image
> builds, and whether VMD behaves headless in the container are unverified. `preflight` is how you find out, and
> `pytest -m requires_vmd -rs` runs the real-VMD tests on a machine that has it.

### Hardening used by the compose file

Non-root user (uid 10001), read-only root filesystem, tmpfs `/tmp` and `/home/vmdagent`, all capabilities dropped,
`no-new-privileges`, and `VMD_AGENT_ALLOWED_ROOTS=/data` so the **server** tools can only touch `/data`.
For analysis-only work add `--network none` (downloads from RCSB/AlphaFold then fail by design).

### Status: not yet built or run

The Dockerfile, entrypoint, compose file and `install_vmd.sh` were written **without Docker available**.
They are syntactically checked (YAML parses) and the CI workflow builds the open-source image and smoke-tests
it on first push. In particular **`docker/install_vmd.sh` is untested against a real VMD tarball**; VMD's
`configure` layout varies between releases. If it fails, use the mounted-VMD route above.

Apple-silicon note: VMD's Linux builds are x86-64 (and some aarch64); mounting a host install requires the
same architecture as the container.
