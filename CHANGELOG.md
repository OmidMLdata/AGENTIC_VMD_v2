# Changelog

## 0.9.4: MCP on a Linux machine, end to end

* **`vmd-agent mcp-check`**: launches the server and talks to it over stdio with the real MCP client, giving the server only
  the environment you pass it. Reports connection, the tool list, analysis libraries, VMD, Tachyon and ffmpeg, the sandbox
  (outside paths refused, relative paths resolved inside the first root), whether raw Tcl is disabled, and with `--render`
  a real render. Exit code 2 on any failure. Works with both MCP SDK generations.
* **Sandbox fix:** with `VMD_AGENT_ALLOWED_ROOTS` set, a relative path is now taken relative to the **first root**. Before,
  it was relative to the server's working directory, which is normally outside the sandbox, so the default output
  directory `vmd_agent_output` was refused on almost every call.
* **Warning when the sandbox is off:** the server prints to stderr (never stdout) if `VMD_AGENT_ALLOWED_ROOTS` is unset.
* **README:** a complete MCP section for a Linux machine with VMD (requirements, verification, four ways to connect a
  client including SSH and Docker, server behaviour, troubleshooting). The SSH route, the `claude mcp add` flags, the
  Docker route and VMD's headless library list have not been tested against a real VMD or client.

## 0.9.3: no recorded results

* **Removed every recorded result.** `docs/results/` (four JSON files of validation and baseline outputs) is deleted, and
  no measured number from running the validation or the benchmark appears in the README, `PAPER`, `TECHNICAL`,
  `PREREGISTRATION`, `CHANGELOG` or the history document. Test outcomes, scores, agreement figures, power tables and
  mutation scores are gone; thresholds, tolerances and counts of tools or task families (design parameters) remain.
* **README:** a "How to run" section (install, tests, using the toolkit, reproducing each validation check, running the
  benchmark natively and in Docker with your VMD, the grounding study, and what to do before a confirmatory run).
* **PAPER:** now a design-and-protocol paper. "Results" became an evaluation protocol (each evaluation, its command, what is
  compared); "What building it found" became the audit methods; the appendices record no outcomes.
* **PREREGISTRATION:** the power tables are replaced by a script to compute power from your own assumptions.

## 0.9.2: leaner

* **Docs:** `docs/RESEARCH.md` folded into `docs/PAPER.md` (its question map, grounding-study specification and
  verification record are Appendices D to F; the rest duplicated the paper). Docs are now `PAPER`, `TECHNICAL`,
  `PREREGISTRATION`, `history/`.
* **Source:** `visual/renderers/base.py` and `vmd.py` merged into `renderers/__init__.py` (interface, VMD backend and
  registry together; `mpl.py` stays separate). Imports from `vmd_agent.visual.renderers` are unchanged.
* **Tests:** `test_chain_counting` merged into `test_stats_detect`; `test_validation_numpy` and `test_validation_dssp`
  merged into `test_validation`. No test was removed or changed.

## 0.9.1: nothing fake

Removed every stand-in for another program. The fake `vmd`, `tachyon` and `ffmpeg` executables, the stub MCP SDK, the
fake model clients, the mocked network and a fake evidence object are gone. In their place:

* Tests that need a real VMD/Tachyon, ffmpeg, the MCP SDK, the network or a live model are marked (`requires_vmd`,
  `requires_ffmpeg`, `requires_mcp`, `requires_network`, `requires_api`) and **skipped with the reason shown** where
  the real thing is missing. `pytest -rs` lists them; the test header says what real tools were found. A skip is "not
  verified here", not a pass. The real-VMD tests have never been run by the author.
* Generated Tcl is now built by pure functions (`_image_lines`, `_views_lines`, `_frames_lines`) and checked as text;
  hostile input is refused before VMD is searched for, so the answer no longer depends on what is installed.
* Network behaviour is tested against the **real** RCSB, AlphaFold and search APIs (including mmCIF fallback on the real
  entry 9NFN, which has no PDB file) and a **real local web server** serving exact bytes for size caps, gzip bombs and
  HTML rejection. The MCP server is tested through the **real SDK**, both generations, on Python 3.12.
* The oracle baseline renders real images with the real matplotlib renderer instead of writing random pixels.

Real defects this exposed (all invisible with stand-ins), fixed:

* **The MCP server did not import with mcp 2.x**, which is what `pip install '.[server]'` now installs (`FastMCP` was
  renamed `MCPServer`). Both generations are supported and tested; CI covers `mcp<2` too.
* `check_path` raised `ValueError` instead of a policy error on a NUL byte under Python 3.12.
* The **synthetic structure generator is not reproducible across machines**: one seed gave different structures on
  Python 3.9/NumPy 1.26 and Python 3.12/NumPy 2.5 (floating-point differences flip discrete choices), and ligand-burial
  agreement with the design differed between them. `design.json` and the task suite now record SHA-256 hashes, and the runner
  refuses a suite whose files changed. The seed is documented as not sufficient.
* Replaced a fake evidence object with a pure function (`_secondary_structure_verdict`) tested at its boundaries.
* Test environment: `VMD_BIN` is no longer cleared, so a real VMD stays discoverable.

Still synthetic, by design and labelled as such: the generated protein-ligand-water test system
(`tests/data/sample`), the novel-structure generator, and injected events on real trajectories.

## 0.9.0: bring-your-own-VMD benchmark runs

* **`bench agent-preflight`**: checks VMD (found, headless load, selection evaluation, built-in ray tracer), code
  execution only inside a container, scrubbed secrets, API key and SDK, suite and output paths. `--live-api` makes one
  tiny call. `agent-run` re-runs it and refuses to start if a blocking check fails (`--skip-preflight` to bypass).
* **Plain-VMD arm made real**: runs in the task workspace, with VMD-syntax selections scored by a real VMD
  (selection strings restricted to a Tcl-free character set), and a tool description with the basics VMD needs.
* **Security**: model-written Python and Tcl run with a **whitelisted environment**, so they cannot read
  `ANTHROPIC_API_KEY`. Previously the child process inherited it.
* **Docker**: `bench` / `bench-hostvmd` / `bench-withvmd` compose services (key passed by name, pids and memory limits,
  writable tmpfs home), the image now includes the Anthropic SDK, and `docker/bench.sh` wraps preflight, suite, plan and run
  and refuses a macOS VMD for a Linux container.
* **Fixed (found by the property tests)**: the selection, word and residue-name validators accepted a trailing newline
  (`$` matches before one). Now anchored with `\Z`; regression tests added.
* **macOS**: the app's `vmd_MACOSX*` binary is discovered and `VMDDIR` is set when unset. `manifest.json` per run.
* **Untested against real VMD and Docker** (neither available here). Tested: shell syntax, compose structure,
  guards, scrubbing, scoring path and preflight logic (at the time, against a fake VMD, since removed).

## 0.8.2: documentation consolidated

Eight documents became three, plus the history. Content is unchanged except for one new section.

* `docs/PAPER.md`: **new "Research questions" section** (eight questions with motivation, test, evidence, open
  items and what a negative answer would be), then the automation benchmark, the grounding study and the validation
  evidence (formerly `AUTOMATION_BENCH`, `BENCHMARK`, `VALIDATION`).
* `docs/TECHNICAL.md`: architecture, methods, security, Docker (formerly four files).
* `docs/PREREGISTRATION.md`: the agent-study plan, with the grounding-study plan as an appendix.
* All links and anchors updated and checked.

## 0.8.1: retention audit

Compared against the original package, signature by signature and output by output
(`docs/history/CHANGES_FROM_ORIGINAL.md`, section 15). Nothing functional was missing from the original's tool
surface, but five things removed in earlier rounds are **restored**:

* `structure_stats(hbond_cutoff=)`: had been swallowed by a `**kwargs`; now a real parameter (unknown options raise).
* `annotate_image(panel_side="left"|"right")` (also MCP tool and CLI `--panel-side`), `representations.params_for`.
* `probe_environment` again reports mdtraj, networkx and pandas; the `[dssp]` (mdtraj) install extra is back.
* Removed a stray `.bak` file from the tests.

## 0.8.0: automation benchmark

Reframed the research as an end-to-end **VMD-automation benchmark** with the toolkit as one entrant.

* New `vmd_agent.bench.agent`: task suite with independently known answers (6 families: measure, event, diagnosis,
  selection, keyframes, report), tool environment with arms (plain Python, plain VMD, toolkit, two ablations) confined to
  the task workspace, scorers including **silent-error** accounting, runner with fresh workspaces per run, cost planner,
  an Anthropic tool-use agent adapter (tested with a fake client only), and scripted oracle / sloppy / reference agents.
* CLI: `bench agent-suite | agent-run | agent-plan`.
* `docs/PAPER.md#5-the-automation-benchmark`; `docs/PREREGISTRATION.md` rewritten for the agent study (the vision-only draft is kept as
  `PREREGISTRATION.md#appendix-grounding-study-draft`); `docs/PAPER.md#appendix-e-grounding-study-specification` re-labelled as the secondary component study.
* **Fixed (found by building the benchmark):** `analyze_trajectory` silently dropped frames with NaN coordinates and
  reported a smaller `n`; it now says so in `notes`.
* Added `paired_difference(keys=, alpha=)` to the grounding scorer.
* Removed dead code (`security.check_paths`, `validation.dssp_cross_benchmark`, an unused test constant); corrected stale
  module paths in strings.
* Mutation-checked the new scorers, tools, suite and runner (two scorer gaps needed an extra test).
* Honest findings recorded, not fixed (to avoid tuning the toolkit to its own benchmark): the toolkit's distance
  analysis is centre-of-mass, and its change-point detector misses slow transitions (a silent failure).

## 0.7.2: second audit

* **`run_vmd_tcl` (MCP) is disabled by default** (`VMD_AGENT_ENABLE_TCL=1` to enable). The 0.7.1 deny-list fixes closed specific
  strings, but obfuscated Tcl (names built at run time, `catch $built`, `rename exec`) passes the screen; confirmed with a real
  `tclsh` (several obfuscated forms created files). Filtering cannot make arbitrary Tcl safe, so the tool no longer runs unless enabled.

* Fixed: statistics overflowed to NaN for values near 1e154 (found by property tests); the CLI printed tracebacks (now a
  one-line error, `VMD_AGENT_DEBUG=1` restores them); `detect_system` / `structure_stats` / recipes crashed on topologies
  without atom names; provenance reported false tampering after a file was legitimately re-rendered; `dt_ps`, `k`, image
  size and unknown views were accepted silently; `install_vmd.sh` used GNU-only `sed -i`; Pillow `getdata()` deprecation.
* Added `docs/PREREGISTRATION.md` (draft analysis plan) and `paired_difference(keys=, alpha=)`.
* Added property tests and tests for every fix above, and mutation-checked the fixes.

## 0.7.1: adversarial audit

An audit (static analysis, targeted probes, a fuzz pass, mutation testing) found and fixed the following. Each fix has
a regression test, and each was checked by mutation (reverting the fix makes a test fail).

**Security (high)**
* The Tcl deny-list could be bypassed several ways (`catch "exec …"`, `open … w` + `source`, `play`,
  `render … "cmd"`, arbitrary file read). Closed; `mol urlload` also denied.
* **Tcl injection into scripts the toolkit generates** (never screened): a hostile path, `--representation`, colour
  method, `background`, or a **residue name inside a crafted mmCIF** could close a brace and run commands when rendered with
  VMD. All interpolated values are now validated; hostile residue names are dropped with a warning.

**Correctness (medium)**
* `contacts` / `distance` without `sel2` silently compared the selection with itself; now an error.
* The benchmark response parser mis-scored `{"answer": true} (note: {x})` as `0.9` and accepted `true` as a number.
* Paired contrasts silently used only the last repeat when `n_repeats > 1`; now averaged.
* The claim parser reduced qualified sentences ("water bridges the ligand and Asp 52", "membrane is intact", "stable for
  40 ns") to a weaker claim and marked them *supported*; it now refuses sentences that say more than can be checked, and
  stalled 11 s on a 50 000-character input (now capped at 400 characters).
* `analyze_trajectory` had no memory guard (all atoms of all frames copied into RAM); it now refuses with the `step` that fits.
* `VMD_BIN` pointing at an install directory was documented but ignored.
* NaN coordinates crashed the matplotlib renderer; they are now flagged by `detect_system` and skipped.

**Test-suite gaps closed** (found by mutation testing): DSSP parallel-bridge convention, ECE under-confidence, the 30 %
"mostly helical" floor, invalid-box handling, `source` rule, server wrapper branch.

**Not changed:** the Tcl screen is still a deny-list, not a sandbox; the claim parser is still template-based;
`analyze_trajectory` still copies whole-system coordinates (guarded, not reduced).

## 0.7.0 (continued): repository restructure

**Breaking for deep imports** (the top-level `from vmd_agent import ...` API is unchanged).

* **`src/` layout, flat repo root.** The doubled `vmd-agent/vmd-agent/vmd_agent/` nesting is gone:
  `src/vmd_agent/`, `tests/`, `docs/`, `docker/`, `.github/`.
* **Role-based subpackages** replace 25 flat modules:

  | was | now |
  |---|---|
  | `molio`, `fetch`, `inspection` | `vmd_agent.inputs.*` |
  | `detect`, `stats`, `dssp` | `vmd_agent.structure.*` |
  | `analysis`, `timeseries`, `keyframes` | `vmd_agent.dynamics.*` |
  | `recipes`, `representations`, `colorkey`, `annotate`, `render`, `renderers` | `vmd_agent.visual.*` |
  | `media`, `claims`, `validation`, `provenance`, `report` | `vmd_agent.evidence.*` |
  | `auto`, `environment`, `security`, `cli`, `server`, `bench` | unchanged |

* **Layering fixed and enforced.** `dynamics.keyframes` no longer imports `visual` and `environment` no longer imports
  `visual` (a lazy cycle). `probe_environment` (with the renderer inventory) and `select_keyframes(render=...)` now live
  in `vmd_agent.auto`; `environment.probe_environment` reports host facts only; `dynamics.keyframes.select_keyframes`
  is selection only. `tests/system/test_layering.py` checks every import and fails on a back-edge or a cycle
  (mutation-tested).
* **Tests mirror the package** (`inputs/ structure/ dynamics/ visual/ evidence/ bench/ surfaces/ system/`), mixed files
  split, data paths centralised in `conftest.py`; sample system moved to `tests/data/sample/`. no tests added or removed.
* **Docker files grouped in `docker/`**; build with `docker build -f docker/Dockerfile .`; `docs/TECHNICAL.md#architecture` and
  `docs/history/` hold the guide and the change history; unused imports pruned across `src/` and `tests/`.

## 0.7.0, research evidence + leaner repo

### Research additions (reproduce with the commands in the README)
* **DSSP validation** against PDB annotations and MDTraj (`validation.dssp_vs_records`, `dssp_cross_benchmark`;
  `vmd-agent validate-dssp`).
* **Real-noise event study** (`bench/events`): injected events on a real 20 ns ubiquitin trajectory, uniform vs
  event-aware frames, plus a negative control (`vmd-agent bench events`).
* **Contamination-free structures** (`bench/synth`): procedural folds with measured truth and a generator
  self-check; `bench synth`.
* **Real-vs-novel gap with a difficulty-adjusted contamination estimate** (difference of differences, cluster
  bootstrap) and structure groups in the runner.
* **Cost planner** (`bench run --dry-run`): counts calls/tokens without calling a model; prices are caller-supplied.
* `analyze_trajectory(dt_ps=...)`; DCD header times are now flagged.

### Defects found by the new evidence (fixed)
* DCD header time trusted blindly (real trajectory: 1 ps reported, 400 ps actual).
* Stats caption counted ligand/water chain IDs as protein chains (`n_protein_chains`, `n_chains_all`).

### Leaner repository
* Removed 126 MB of legacy PNG renders (`examples/`): the original folder still has them. Kept the real 20 ns ubiquitin
  MD as `tests/data/ubq_md/` because the real-data tests need it.
* Removed never-imported dependencies (`networkx`, `pandas`) and dead code (`params_for`, `panel_side`, unused imports).
* **Removed the PyMOL backend**: it was never run and could not render frame sets. Renderers: `vmd`, `matplotlib`.
* `DIFF_FROM_ORIGINAL.md` moved to `docs/history/CHANGES_FROM_ORIGINAL.md`; test helper now reuses the package's
  NeRF builder instead of a duplicate copy.

## 0.6.0, consolidated release (this copy)

Everything below was done on a **copy** of the original project; the original folder is untouched.

### Packaging, licensing, containers
* One package: the duplicate `vmd-agent/` tree, the stale root `fetch.py`, a stray `render.dat` and
  `README_1.md` were removed; past run outputs moved to `examples/`.
* `LICENSE` (MIT) and `NOTICE.md` (VMD/Tachyon not bundled; **MDAnalysis is GPL**, review before publishing an image).
* **Bring-your-own-VMD Docker setup**: `runtime` (open-source, default), `vmd-libs`, `with-vmd` targets;
  hardened compose file; entrypoint; CI workflow. *Not built here (no Docker available).*
* `pyproject.toml` now lists the new subpackages (they would otherwise be missing from installs), adds Pillow.

### Bugs fixed (present in the original)
* **mmCIF fallback was unusable**: `fetch` downloaded mmCIF for large entries but MDAnalysis cannot read it. Native reader added.
* **Secondary structure silently never worked** on MDAnalysis < 2.8 (bare `except`): replaced by a built-in DSSP.
* **Partial `CONECT` bonds reported as the full count** (a handful of bonds reported for lysozyme): detected and supplemented.
* H-bond count ignored geometry: now angle-based when hydrogens exist; heavy-atom fallback is labelled.
* All plots said "time (ps)" even when x was a strided frame index: honest axis labels.
* RMSF plotted per atom while documented per residue; duplicate "most flexible" residues.
* RMSF's in-memory alignment could corrupt later analyses in the same batch.
* `render_movie` launched VMD once per frame and reset the camera each frame; now one session, one camera.
* Scratch directories leaked ~5 MB per render call.
* Colour key listed water swatches for water that was hidden; claimed STRIDE for the matplotlib backend.
* `representations_added` ignored focus / pLDDT / explicit representation.
* "Material" detection fired on ≥ 50 sulfur / iron / zinc atoms; split into unambiguous vs bio-relevant elements.
* `-vsync` / `eq(n\,k)` ffmpeg usage fragile across versions; invalid-escape warning removed.
* `Session` could be truncated by an interrupted write or crash on a corrupt file; report crashed on missing numbers.
* Hard-coded `/home/akshay/...` paths removed from docs and messages.
* `run_vmd_tcl` accepted arbitrary Tcl (including `exec`); `fetch` accepted `file://` and internal URLs.

### Statistics replaced fixed thresholds
* "Stable if std < 0.5 Å", "collapse if ΔRg > 1 Å", etc. → autocorrelation-aware verdicts
  (`timeseries`): N_eff, Mann-Kendall + Theil-Sen, half-vs-half, equilibration detection, `insufficient_data` gate.
* PBC diagnostics (per-atom half-box jumps) and optional `unwrap`.
* `convergence` analysis.

### New features
* Renderer abstraction: **matplotlib** (open source, VMD palette), VMD, PyMOL (experimental).
* **Event-aware keyframe selection** + evaluation metrics + closed-form uniform-sampling analysis.
* **Claim verification** (`verify_claims`), with Shrake-Rupley ligand burial.
* **Grounded-interpretation benchmark** (ground truth, questions, 8-condition ladder, scorer with cluster bootstrap,
  runner, Anthropic adapter, sampling study, blinded rating-study instrument).
* **Provenance** records and verification.
* `vmd-agent validate` (cross-check vs independent NumPy).
* Server: path sandbox, Tcl screening, URL policy, 3 new tools (27 total).
* Tests added (the old "test" had no assertions).

### Known gaps
See "Honest limitations" in `vmd-agent/README.md` and `docs/PAPER.md#appendix-f-what-the-test-suite-checks-and-what-is-not-verified`.
