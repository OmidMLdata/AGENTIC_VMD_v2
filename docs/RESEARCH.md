# Research

The study design, the draft analysis plan and a comparison with the original project. Everything here is about *how the toolkit is evaluated*; how to use it is in the [README](../README.md). No measured results are included anywhere in this repository.

**Parts:** [I. Paper](#part-i-paper) · [II. Preregistration (draft)](#part-ii-preregistration-draft) · [III. What changed from the original project](#part-iii-what-changed-from-the-original-project)

---

## Part I: Paper

## vmd-agent: Measuring Whether LLM Agents Fail Loudly or Silently When Automating Molecular Visualization and Trajectory Analysis

*A systems-and-benchmark paper in registered-report style (Stage 1): design, methods and evaluation protocol. **This
repository contains no measured results.** The toolkit and the benchmark are built and tested; no language model has been
evaluated, and no numbers from running the validation or the benchmark are recorded anywhere in the repository. Every
quantity below is a design parameter (a threshold, a tolerance, a count of tools or task families), and every claim that
would be a result is replaced by the command that produces it. Run the commands in the [development guide](../README.md#running-and-reproducing)
to obtain your own numbers.*

---

### Abstract

Large language model (LLM) agents are increasingly asked to run the analyses that structural biologists and simulation
scientists do by hand: load a trajectory, select atoms, compute RMSD or a distance, find when something happens, render a
figure, write up what was seen. In that setting the dangerous failure is not the agent that is wrong and says so; it is the
agent that is wrong and says nothing. Accuracy alone cannot tell the two apart. We present **vmd-agent**, a toolkit and a
benchmark built around that distinction.

The **toolkit** (Python library, command line, a built-in chat front end for local or hosted models, and a Model Context Protocol server, all over the same 27 tools) prepares evidence and
states how it was obtained: a native mmCIF reader, a NumPy implementation of the Kabsch–Sander secondary-structure
assignment, autocorrelation-aware trajectory statistics with an explicit "insufficient data" verdict, per-atom
periodic-boundary diagnostics, event-aware keyframe selection, a four-valued claim verifier (supported, contradicted,
unverifiable, unparsed), provenance records, and a security model for the Tcl and file paths an agent can reach. VMD is
optional and not bundled. Procedures are provided to check the toolkit against independent implementations (independent
NumPy for analysis; PDB annotations and MDTraj for secondary structure) and to compare event-aware with uniform frame
selection on a real trajectory with injected events.

The **benchmark** generates tasks from six families (measure, event, diagnosis, selection, keyframes, report), with answers
known by construction rather than supplied by a model: computed with independent code, or established by injecting events
and data defects into real trajectories. Agents are compared across *tool arms* (plain Python, plain VMD, the toolkit, and
two ablations), and scored on success and on **silent errors** (answered, wrong, no abstention, no data problem flagged),
with a cluster bootstrap over trajectories and structures. Three scripted agents (an oracle, a deliberately careless
analyst, and a careful toolkit user) are provided as controls on the instrument itself; they are not models.

We state plainly what is missing: no model has been run, real VMD has never been executed by the authors, and the Docker
images have never been built. We provide a preregistration draft with hypotheses and the procedures that make a
confirmatory run credible.

---

### 1. Introduction

#### 1.1 The problem

A modern molecular-dynamics (MD) study ends in figures and sentences: "the ligand remains bound", "the domain opens at about
8 ns", "RMSD stabilises after 20 ns". Each sentence rests on a chain of small decisions that rarely appear in the text: which
atoms were selected, whether the molecule was made whole across periodic boundaries, whether the time axis came from the
file header or from the stride actually used, whether any frames were damaged, how many independent samples the
trajectory really holds. Agents that automate this chain inherit every one of those decisions and can get any of them
wrong.

Wrong answers are expected; automation is not worse than people at being occasionally wrong. What differs is how the error
presents. A tool that raises an exception, prints a warning, or answers "I cannot tell" costs a re-run. A tool that returns
a plausible number from a trajectory whose frames are split across a periodic boundary costs a paper. We call the second
kind a **silent error**: the agent answers, the answer is wrong, it did not abstain, and it flagged no problem with the data.

#### 1.2 Why existing evaluation does not capture this

Most evaluation of LLM tool use reports accuracy: the fraction of tasks solved. Accuracy treats a wrong answer with a loud
caveat and a wrong answer with none as the same loss. For scientific automation they are very different losses. A benchmark
for this setting must therefore (i) have answers that do not depend on a model or on the code under test, (ii) include
tasks in which the right behaviour is to refuse, and (iii) separate wrong-and-flagged from wrong-and-silent.

#### 1.3 What this paper contributes

1. **A toolkit** that makes the provenance of every number explicit and fails closed (Sections 3 and 4).
2. **A benchmark** of six task families with independently known answers, five tool arms, and silent-error accounting
   (Section 5), plus the infrastructure to run it with a real VMD and a real model in a container, with the secrets
   that matter protected from model-written code (Section 7).
3. **Evaluation procedures for both**: checks against independent implementations, and three scripted control agents
   that test whether the instrument discriminates (Section 8).
4. **The audit methods** used while building it: static analysis, probes, fuzzing, property tests, mutation testing and a
   retention audit (Section 9).
5. **A preregistration draft** that fixes hypotheses, contrasts, exclusions and sample size before any model is run
   (Section 11).

We deliberately do not claim that agents using the toolkit outperform agents without it. That is the question the benchmark
exists to ask, and its author has a conflict of interest in the answer (Section 10.4).

#### 1.3.1 What this repository provides, and what it does not

| Provided | Not provided |
|---|---|
| A toolkit and a benchmark, with tests | Any measured result, from the toolkit checks or the benchmark |
| Procedures to validate the toolkit against independent code | Evidence that any model does better with the toolkit |
| Scripted controls that test the scorers | Evidence that model behaviour resembles the scripted controls |
| Infrastructure for a credible run | The run itself |

---

### 2. Background and related work

**Molecular visualization and analysis.** VMD [Humphrey, Dalke and Schulten, 1996] is the de facto interactive and
scriptable viewer for biomolecular systems, driven by Tcl and rendered through the Tachyon ray tracer [Stone, 1998].
MDAnalysis [Michaud-Agrawal et al., 2011] and MDTraj [McGibbon et al., 2015] expose trajectories as Python objects; this
toolkit uses the former for I/O and the latter only as an independent cross-check.

**Secondary structure.** The Kabsch–Sander definition [Kabsch and Sander, 1983], based on backbone hydrogen-bond
energies, underlies DSSP. We re-implement it in NumPy, check it against two references (Section 8.1), and use it only to
label residues as helix, sheet or coil.

**Trajectory statistics.** Consecutive MD frames are correlated, so a naive standard error understates uncertainty. The
statistical inefficiency, block averaging [Flyvbjerg and Petersen, 1989] and automated equilibration detection
[Chodera et al., 2007] address this. We use the inefficiency to compute an effective sample size, and the Mann–Kendall
trend test [Mann, 1945; Kendall, 1975] with the Theil–Sen slope [Theil, 1950; Sen, 1968] to detect drift robustly.

**Solvent accessibility.** Burial of a ligand is measured with Shrake–Rupley surface-area sampling [Shrake and Rupley,
1973].

**Agent protocols.** The Model Context Protocol (MCP) exposes tools to an LLM client over a standard transport. The server
here supports both current generations of its Python SDK (Section 9).

**Benchmarks for agents.** Software-engineering and tool-use benchmarks established the practice of scoring end-to-end task
completion against hidden checks. Our contribution relative to that practice is domain-specific: ground truth from
physics and injected structure rather than from a reference solution written by a person, controls in which the right
answer is to refuse, and a metric for confident error.

*The reference list in Section 14 should be verified against the primary sources before any submission; the claims in this
paper that depend on those works are limited to their well-known definitions.*

---

### 3. System overview

#### 3.1 Design principle

> **The code prepares and verifies evidence and says how it obtained it; the model interprets; a verification layer checks
> what the model claims against the data.**

Every analysis result carries its method (bond source, hydrogen-bond criterion, DSSP source, renderer, time-axis source),
and the agent is told what each backend cannot show. Where a result cannot be trusted (too few independent samples, a
split molecule, damaged coordinates) the toolkit says so in the result, not only in the documentation.

#### 3.2 Surfaces

The same functions are exposed three ways: a Python library, a command line (`vmd-agent`, with subcommands from `probe` and
`detect` to `analyze`, `keyframes`, `claims`, `validate`, `provenance` and `bench`), an MCP server with 47 tools (27 at the time of the original study design, 20 more that drive VMD itself), and a built-in chat front end (`vmd-agent chat`) that gives the same tools to any
OpenAI-compatible model, local open-source or hosted, so no MCP client is required. The
original project this work extends exposed 24 tools and 16 command-line subcommands; all were retained (Section 12.1).

#### 3.3 Layering

Source is organised as subpackages that follow the pipeline, with allowed dependencies enforced by a test that parses
every import:

```
inputs  ->  structure  ->  dynamics  ->  visual  ->  evidence          bench (on top)
 (I/O,      (detect, stats,  (analysis,    (recipes,    (claims, validation,   (benchmarks, synthetic
  fetch)     DSSP)            statistics,   renderers)   provenance, media)     structures, events)
                              keyframes)
environment and security are foundations; auto, cli and server compose the layers.
```

#### 3.4 Optional VMD, and renderers

VMD is not bundled (its licence forbids redistribution) and is optional. Rendering goes through a renderer abstraction with
two backends: VMD plus Tachyon (publication quality, all focus modes) and matplotlib (always available; draws a backbone
trace in the VMD palette so legends remain true). Every result states which renderer drew it and lists that renderer's
caveats; the legend is generated from what the renderer actually drew.

#### 3.5 Security model

An agent that can call tools can be steered, by its prompt or by a hostile input file, into misusing them. The model
has four parts:

* **Path sandbox.** With `VMD_AGENT_ALLOWED_ROOTS` set, every path an MCP tool receives is resolved (symlinks, `..`,
  prefix-sibling tricks) and refused if it falls outside the roots. A NUL byte in a path is refused.
* **Validation of everything placed in generated Tcl.** Paths, selections, representation and colour names, backgrounds
  and *residue names read from the structure file itself* are validated against character sets with no Tcl syntax. This
  closed a real injection route: a crafted mmCIF could carry a residue name that closed a brace and ran commands
  when rendered.
* **A Tcl deny-list that is an accident guard, not a boundary.** Tested against a real `tclsh`, obfuscated
  forms (names built at run time, `catch $built`, `rename exec`) can create files despite the screen, because filtering
  cannot make arbitrary Tcl safe. The raw `run_vmd_tcl` tool is therefore **disabled by default**.
* **A URL policy** for downloads: http(s) only, no loopback/private/link-local targets (re-checked on every redirect),
  size caps on compressed and decompressed bodies.

---

### 4. Methods: the toolkit's measurements

#### 4.1 Reading structures

A native mmCIF reader is used because MDAnalysis cannot read mmCIF. For entries too large for the PDB format (RCSB
returns 404 for their `.pdb`) fetching falls back to mmCIF and the rest of the pipeline treats the result as any other
structure.

#### 4.2 System detection and integrity checks

Components (protein, nucleic acid, lipid, water, ions, ligands/other, inorganic material) are classified from residue
names and geometry. Residue names are sanitised before they can reach a selection. Non-finite coordinates are reported.
`detect_system` never raises: a topology without names yields an error dictionary rather than an exception.

#### 4.3 Bonds, interactions and chain counting

Bond sources are stated: explicit records where complete, supplemented by distance-based inference from covalent radii
where records are partial (an example is lysozyme, whose explicit records cover only a handful of bonds). Disulfides use SG–SG < 2.5 Å. Salt
bridges use a 4.0 Å limit between carboxylate oxygens of Asp/Glu and Lys NZ or Arg N, per residue pair. Hydrogen bonds use
H···A ≤ 2.5 Å, D···A ≤ 3.5 Å and a D–H···A angle ≥ 120° between different residues when hydrogens exist, with a labelled
distance-only fallback otherwise. **Chain count** is the number of polymer chains, not the number of chain identifiers
(the original counted ligand and water identifiers as chains).

#### 4.4 Secondary structure

The Kabsch–Sander energy criterion is implemented with sparse bridge detection and the standard parallel and antiparallel
bridge conventions. A pure-NumPy implementation avoids a compiled dependency; MDTraj is used only to cross-check.

#### 4.5 Trajectory analysis and honest time axes

Analyses: RMSD (after optimal superposition), RMSF, radius of gyration, hydrogen bonds, contacts, distances, SASA, density
profiles, and a convergence assessment. Three behaviours matter for correctness:

* **Time axis.** The x-axis states its source. For DCD files, headers often hold a default or pre-stride step; the result
  warns and accepts `dt_ps` for the real spacing. (In the benchmark an agent that trusts the header gets elapsed time
  wrong.)
* **Periodic boundaries.** Per-atom half-box jumps between consecutive frames flag a molecule split across the boundary
  and name the first affected frames; `unwrap=True` makes the selection whole first.
* **Damaged frames.** Frames with non-finite coordinates in the analysed atoms are reported in `notes` with their original
  frame numbers. (Before this work they were dropped from the statistics silently, so `n` merely shrank.)

#### 4.6 Autocorrelation-aware statistics

For a series *x*:

* The **statistical inefficiency** *g* is estimated from the autocorrelation function, giving an effective sample size
  N_eff = N / *g*.
* A trend is tested with **Mann–Kendall**, its slope estimated with **Theil–Sen**, and both are applied to a detrended
  estimate of *g* so that drift does not inflate the apparent correlation.
* The assessment returns a verdict from a fixed vocabulary (for example `no_detectable_drift`, a drift verdict, or
  `insufficient_data` when N_eff < 10) with a reason, so a short run is never called "stable".
* Values beyond 1e100 in magnitude and non-finite values are excluded before computation (a property test found overflow to
  NaN near 1e154).

The assessment replaced the original toolkit's "structure appears stable", which was inferred from the size of the
fluctuation and is not a convergence test.

#### 4.7 Event-aware keyframe selection

A budget of *k* frames (default 9) is chosen by robust change-point scoring. The first and last frames are always kept.
For each signal (RMSD, Rg, and with a second selection, contacts or centre-of-mass distance) windowed changes are
standardised with a median-absolute-deviation scale (window = max(3, n/25) frames), non-maximum suppression picks separated
change points with a robust score of at least `z_min` = 6, and change points may consume at most 70 % of the remaining
budget so that the rest goes to coverage by repeatedly bisecting the largest gap between chosen frames. A uniform baseline
is returned alongside, and each chosen frame carries the reason it was chosen. The
method is built for abrupt events, so it may miss slow transitions; the benchmark's slow-ramp event tasks probe this.

#### 4.8 Claim verification

An agent's sentences are routed to the measurement that can settle them:

| Verdict | Meaning |
|---|---|
| supported | measurement agrees under a stated criterion |
| contradicted | measurement disagrees |
| unverifiable | the data cannot settle it (no trajectory, too little sampling, unmeasured property) |
| unparsed | the sentence is outside the supported vocabulary, **and was not checked** |

The parser is template-based and fails closed: qualified sentences ("the ligand is buried in the active site") are returned
unparsed with a note rather than reduced to a simpler claim they do not entail. Thresholds are explicit: "mostly helical"
requires helix ≥ 30 % and larger than the sheet fraction; "mixed" requires both ≥ 15 %; ligand burial uses a 1.4 Å probe,
the ligand alone versus in complex, and a 0.5 occlusion threshold.

#### 4.9 Provenance

Each run records software versions, input and output hashes, and the exact Tcl executed. `verify_provenance` re-hashes
files and reports changes. Only the latest record per path is authoritative, so a legitimate re-run is not misreported as
tampering (a defect the second audit found).

---

### 5. The automation benchmark

#### 5.1 Research question

*Can an LLM agent automate molecular-visualization and trajectory-analysis workflows correctly, and say so when it cannot?*

#### 5.2 Design principles

1. **Truth independent of any model and of the code under test.** Computed with separate NumPy/SciPy code, or known by
   construction because an event or defect was injected into a real trajectory.
2. **Refusal is a correct answer.** Diagnosis tasks include damaged files for which the right output is a label and no
   number; event tasks include controls on which the right answer is "no event".
3. **Confident error is scored separately.**
4. **The unit of inference is the cluster** (a base trajectory or structure), because tasks built from one trajectory
   share its noise.
5. **Tool access is the experimental variable**, with the same model, prompts and tasks across arms.

#### 5.3 Task families

Generated by `bench/agent/suite.py` from real trajectories and structures.

| Family | Request | Truth | Scoring |
|---|---|---|---|
| `measure` | RMSD of last frame vs first (C-alpha, superposed); mean mass-weighted Rg; distance between centres of geometry of two terminal segments; elapsed time given a stated 400 ps step and an unreliable header | independent NumPy (Kabsch SVD, mass-weighted Rg, mean positions) | tolerance: RMSD 3 %, Rg 2 %, distance 2 %, time 1 % (with small absolute floors) |
| `event` | "does one sustained, directional structural change occur, and at which frame does it begin, or null?" Hinge (40°), tail dissociation (8 Å) or expansion (8 %); abrupt (10-frame) and slow (30-frame) ramps; plus event-free controls | the injected onset | onset within `[start − 5, end]`; any frame on a control is a false alarm |
| `diagnosis` | the RMSD request on a clean file, or one with a molecule split across the periodic boundary, a topology with 5 atoms removed, or NaN coordinates | the injected defect | exact label; for a damaged file, **a number given anyway counts against the answer** |
| `selection` | residues within 4.5 Å of a residue (whole residues); heavy side-chain atoms of a residue range; atoms at the interface between two chains | KD-tree geometry (SciPy), residue bookkeeping | exact atom-set equality, evaluated without periodic images; Jaccard is reported |
| `keyframes` | pick at most 4 frames showing a transition, render each to its own image, report frames and paths | injected event window | distinct, non-blank images inside the workspace and at least one frame within 5 of the event window |
| `report` | describe a structure in 3 to 5 factual sentences | measured structure | claim verification; any contradicted claim fails (exploratory, see 10.3) |

Workspaces contain only anonymously named `system.pdb` and `traj.dcd`; truth lives in a separate file. Each file's SHA-256
is recorded at generation and checked before a run, so a suite that was edited or regenerated is refused rather than scored.

#### 5.4 Injected events and defects

Events use real trajectory noise: a real 20 ns ubiquitin trajectory (50 frames, 400 ps apart, 1,240 protein atoms) is
extended to the required length by ping-pong reflection, which preserves every local frame-to-frame step of the real data,
and one rigid motion is injected on top: a hinge rotation of the first half of the chain about a pivot, a translation of the
last tenth of residues away from the rest, or a uniform scaling. Defects are injected into a copy: a one-box-length shift
of the last tenth of atoms from mid-trajectory (with a periodic box recorded), the last five atoms removed from the
topology, and NaN coordinates in a few frames. Each defect is checked to produce the warning or error the toolkit should
produce, and a clean file to produce neither.

#### 5.5 Arms

| Arm | Tools beyond `list_files`, `read_text_file`, `submit_answer` | Purpose |
|---|---|---|
| `python_mdanalysis` | `run_python` | the strong, realistic baseline: the model writes its own code |
| `vmd_plain` | `run_vmd_tcl` (real VMD) | plain VMD scripting |
| `vmd_agent` | analysis, keyframe selection, system detection, structure statistics, claim verification, environment probing | the toolkit |
| `vmd_agent_no_verify` | as above without `verify_claims` | what the verifier adds |
| `vmd_agent_no_keyframes` | as above without `select_keyframes` | what event-aware selection adds |

File access is confined to the task workspace. For the plain-VMD arm the task asks for a **VMD** selection string and a
real VMD evaluates it; for the others the selection is MDAnalysis syntax. The `selection` family therefore compares each
arm's native syntax.

#### 5.6 Metrics

* **Success** per task, per family, and a family-balanced mean (the selection family has many tasks on static structures
  and would otherwise dominate).
* **Silent error:** `answered and not success and not flagged`, where *flagged* means the agent listed at least one data
  problem and *answered* means a well-formed non-abstaining answer. The **silent share of failures** reports what
  fraction of failures a user would not have noticed.
* Abstention, no-answer, false-alarm rate on controls, tool calls, tokens and wall time.
* Contrasts between arms are paired by task (repeats averaged) with a cluster bootstrap whose interval width is an
  argument (`alpha = 0.05 / m` for a corrected family of `m` tests).

#### 5.7 Scoring details that matter

An unparseable or missing reply counts as incorrect and as an abstention, never as missing. A scorer exception is reported
in the record, not swallowed. Selection strings are limited in length and, for VMD evaluation, to a character set without
Tcl syntax before they reach a script.

---

### 6. The grounding component study

A narrower, controlled version of the evidence-quality idea. A model is shown a rendered image under eight conditions that
add evidence step by step: nothing; one render; render plus legend; one annotated panel; render plus legend plus measured
statistics; three views plus legend plus statistics; **text only** (legend and statistics, no image, a control for what the
text alone settles); and a **misleading legend** (a trap: does the model trust text over pixels?).

* Ground truth comes from the structure file (chain count, fold class, disulfides, presence of ligand, lipid and nucleic
  acid, ligand burial), never from a model.
* Each question lists the sources able to answer it (`image`, `legend`, `stats`); a question that no supplied source can
  answer is one for which the right answer is to abstain. This separates a wrong answer from an unsupported one.
* **Memorisation control.** A model may recognise ubiquitin from its shape. Procedurally generated structures (helix
  bundles, antiparallel sheets, mixed and coil folds; one to four chains; optional buried or exposed ligand; optional
  disulfides) provide structures no model has seen, with truth *measured from the coordinates* by the same code used on real
  structures. A **difference-of-differences** estimate subtracts the real-versus-novel gap seen under the text-only
  condition (which cannot identify a structure) from the gap under an image condition, isolating what the image adds on real
  structures. Its behaviour on planted effects (does it recover a known memorisation effect, return about zero when only difficulty
  differs, keep its false-positive rate low) is tested by the repository's tests; the tests' outcomes are not recorded here.
* The component study's hypotheses (H3 in particular, on the one question only an image can answer) are kept separate in
  the preregistration appendix.

---

### 7. Experimental infrastructure

#### 7.1 Running with a real VMD and a real model

A run needs a trajectory set, a VMD, and an API key. The toolkit ships:

* **`bench agent-preflight`**, which checks before any model call that VMD is found and loads a PDB headlessly, that it
  evaluates a selection to 0-based indices (how the plain-VMD arm is scored), that its built-in ray tracer writes an image,
  that code execution is enabled only with an explicit flag and only inside a container, that model-written code sees no
  key, token or secret variable, that the API key and SDK are present, and that the suite and output directories exist. A
  model call is made only with `--live-api`.
* **Docker**: `bench`, `bench-hostvmd` and `bench-withvmd` compose services (read-only root, no capabilities, no new
  privileges, process and memory limits, a writable tmpfs home, the key passed by name), a helper script, and a guard that
  refuses a macOS VMD for a Linux container. VMD is never baked into an image that could be published.
* **A manifest** per run: versions, VMD path and version, renderer, whether it ran in a container, the suite's hash, and
  no secrets.

#### 7.2 Protecting the key from the model

The benchmark process holds the model API key. Code the model writes would, by default, inherit it. Model-written Python
and Tcl therefore run with a **whitelisted environment** (search paths, locale, VMD's own variables); a test confirms that a
child process, and a real VMD child, cannot see the key. This is not a sandbox: such code can still use the network, so a
dedicated, spend-capped key and a throwaway data directory are required.

#### 7.3 Platform notes

A Mac's VMD.app is a macOS binary and cannot run in a Linux container; the Linux build must match the image architecture.
The macOS app ships a bare `vmd_MACOSX…` binary next to its `scripts/`; the toolkit finds it and sets `VMDDIR` when unset.

---

### 8. Evaluation protocol

No results are included. This section states each evaluation, the command that runs it, what it compares, and what would
count as a failure of the instrument. Outputs are produced locally and are not stored in the repository.

#### 8.1 Toolkit measurements against independent code

* **Analysis numbers.** `vmd-agent validate system.pdb traj.dcd --sel2 "resname LIG" --cutoff 6` recomputes RMSD (SVD
  Kabsch), mass-weighted Rg, contacts and centre-of-mass distances with separate NumPy code and prints both. Disagreement
  beyond numerical precision is a defect.
* **Secondary structure.** `vmd-agent validate-dssp <PDB ids> --cache DIR` compares the built-in assignment, per residue,
  with the HELIX/SHEET records in each file (the PDB annotation pipeline, not `mkdssp`) and, if MDTraj is installed, with
  MDTraj. Report Q3 against the records for both implementations (the established implementation is the ceiling for
  agreement with the records) and the toolkit-versus-MDTraj agreement. Choose structures that cover what you care about;
  membrane proteins, nucleic acids and NMR ensembles are outside what the toolkit has been checked on.
* **Statistics.** The tests simulate AR(1) series: statistical inefficiency should match `(1 + φ) / (1 − φ)`, intervals
  on autocorrelated series should be wider than naive ones, the drift test should rarely fire on stationary series and a
  short run must return `insufficient_data`. Check these on series with your own lengths and correlation times.

#### 8.2 Event-aware versus uniform frame selection

`vmd-agent bench events top.pdb traj.dcd --trials 100 --frames 300 -k 9 --seed 0` extends your real trajectory by ping-pong
reflection, injects one labelled rigid event (hinge, tail dissociation, expansion) at random onsets over a grid of
magnitudes and ramp lengths, and compares uniform with event-aware selection at an equal budget, plus a no-event control
that counts invented change points. Report hit rate and localisation error against the event's size **in units of the
signal's noise sd**, and state that the events are synthetic rigid motions. The false-alarm control is one realisation per
trajectory; run it on several. `vmd-agent bench sampling` runs the idealised AR(1) version and compares the simulated
hit probability with the closed form.

#### 8.3 The novel-structure generator

`vmd-agent bench synth N --out DIR --seed S` writes structures plus `design.json` (with SHA-256 hashes) and prints, per
property, how often the *measured* truth (chain count, ligand presence, disulfide count, fold class, ligand burial)
equals what the generator intended. Benchmark truth is always the measured value, so low agreement on design intent (burial
in particular) limits how well a property can be controlled by construction, not the validity of scoring. **The seed does
not define the set**: floating-point differences between NumPy builds change discrete choices, so generate once and share
the files and hashes.

#### 8.4 Scripted controls on the automation benchmark

`vmd-agent bench agent-suite ...` then `vmd-agent bench agent-run --suite SUITE --baselines oracle sloppy reference`.

| Control | What it is | A correct instrument must |
|---|---|---|
| `oracle` | knows the truth; renders its own real images | score full marks with no silent errors (otherwise a scorer is wrong) |
| `sloppy` | the mistakes of an unreviewed analysis: default selection, trusts the file header, never checks the data, always finds an event, flags nothing | score low and show its failures as *silent* |
| `reference` | a careful user of the toolkit's tools | solve the tasks the toolkit can solve; every task it cannot solve is a gap in the toolkit, to be reported and not hidden |

These are controls on the instrument. They are written by the same author as the tasks and tools, so they are not
evidence about models; do not quote their scores as model results. Inspect the `reference` agent's failures to find
toolkit gaps before a confirmatory run, and freeze the toolkit afterwards so it is not tuned to its own benchmark.

#### 8.5 The confirmatory study

Fill the preregistration, deposit the generated suite, then run models with the commands in Appendix A (or the Docker
route). Analysis follows [Part II](#part-ii-preregistration-draft).

---

### 9. Audit methods

The toolkit and benchmark were built with repeated adversarial audits. The methods are listed so you can repeat them; the
defects they found and fixed are recorded in the [CHANGELOG](../CHANGELOG.md), not claimed here as results.

* **Static analysis:** pyflakes and ruff on bug-prone rule sets; vulture for dead code.
* **Targeted probes:** hostile inputs aimed at the path sandbox, the Tcl screen (including a real `tclsh`), the URL policy,
  and every value interpolated into generated Tcl, including residue names read from a crafted mmCIF.
* **Fuzzing:** malformed structure files, random strings and pathological lengths into the parsers and the claim verifier.
* **Property tests (Hypothesis):** pure functions and the whole pipeline on random inputs; nothing may raise and results
  must satisfy their stated bounds.
* **Mutation testing:** a copy-based harness injects one defect at a time into a throwaway copy of the repository and
  checks that the suite notices. It is ad hoc and not part of continuous integration; a few dozen mutants are a small
  sample.
* **Retention audit:** the extended package was compared with the original, signature by signature and output by output,
  to confirm nothing functional was dropped ([history](#part-iii-what-changed-from-the-original-project), section 15).
* **Real-component pass:** every stand-in for another program was removed, so tests run against the real MCP SDK, the real
  network and a real local web server, or are skipped with a reason where the real thing is absent.

Two lessons from the process are methodological. First, **stand-ins hide real failures**; replacing them with real
components is a form of validation in itself. Second, **a seed is not a specification**: any generated benchmark must be
distributed as files with hashes.

---

### 10. Threats to validity and limitations

#### 10.1 Internal

* **The instrument was validated by its author with agents the author wrote.** The oracle, sloppy and reference agents
  are intended to show that the scorers discriminate; they are not independent evidence about models.
* **Tolerances and windows are choices** (3 %, 2 %, 1 %, ±5 frames, 0.5 burial, 30 % helix floor). Sensitivity must be
  reported.
* **The toolkit was changed after seeing the benchmark** (the NaN fix). The confirmatory run must freeze the toolkit.

#### 10.2 External

* **One real trajectory ships with the repository.** The trajectory families have one cluster until more MD data is added.
* **Events are synthetic rigid motions** on real noise, on one protein family. Realism of conformational change is
  untested. The toolkit's change-point detector is designed for abrupt events, which is why the event tasks include slow ramps.
* **Synthetic structures are idealised** (rods and sheets). The real-versus-novel adjustment assumes images of both are
  equally easy to read, which is untested.
* **The benchmark covers six task families.** Many real analysis tasks (free-energy estimates, clustering, long-range
  allostery) are absent.

#### 10.3 Construct

* **The `report` family is scored with the toolkit's own verifier**, which is circular for the arm that uses it. It is
  exploratory only.
* **Selection tasks differ in syntax by arm**, so they measure the model more than the tool.
* **Images are not shown to the agent** in the automation benchmark; vision is the grounding study's subject.

#### 10.4 Conflict of interest

The toolkit's author wrote the tasks, the scorers and the baselines. The first hypothesis (success, toolkit versus plain
Python) is therefore stated two-sided with no predicted direction, the toolkit is framed as one entrant, the held-out suite
must use seeds and data not used in development, and the preregistration must be filed before any real-model call. The model
that wrote the benchmark must not run it.

#### 10.5 What has not been verified

Real VMD has never been executed by the authors (their machine has none); the tests that need it are marked and skip
where it is absent. The Docker images have never been built. No language model has been run on either benchmark, and the
live-API tests have not been run. The secondary-structure assignment has not been compared with `mkdssp` itself. The MCP server
supports both current generations of the SDK and is tested through the real SDK where it is installed, but it has not been
run inside a real MCP client.

---

### 11. Preregistered analysis plan (draft)

*Status: draft; becomes a preregistration only after its `TODO` fields are filled and it is filed before the first
real-model call. Full text: [Part II](#part-ii-preregistration-draft).*

#### 11.1 Confirmatory hypotheses

Resampling unit: the cluster. Statistic: mean per-task difference between arms, repeats averaged, over the family-balanced
measure, event, diagnosis, selection and keyframes tasks.

| ID | Contrast | Prediction |
|---|---|---|
| H1 | success: `vmd_agent` − `python_mdanalysis` | two-sided, no directional prediction |
| H2 | silent-error rate: `vmd_agent` − `python_mdanalysis` | < 0 |
| H3 | success on diagnosis tasks: `vmd_agent` − `python_mdanalysis` | > 0 |

The family is H1 to H3 with Bonferroni α = 0.05 / 3 ≈ 0.0167, two-sided. All three are reported whatever the sign, for every
model. Secondary and exploratory: the two ablations, per-family and per-model results, false-alarm rate on controls,
abstention, calibration, cost per solved task, and `vmd_plain` against `python_mdanalysis`.

#### 11.2 Sample size

The effect size and the spread of cluster-level differences are assumptions to be stated before registering; no pilot data
exist and no power figures are provided. [Part II](#part-ii-preregistration-draft) contains a short script to compute power
for your own assumptions. Plan a pilot of about 10 clusters, excluded from the confirmatory set, to estimate the spread. The
repository ships one real trajectory, so trajectory-level statistics need more MD data from you. A null is reported as "no
difference larger than the interval".

#### 11.3 Procedures that make the run credible

Freeze the toolkit version; use suite seeds not used in development and **deposit the generated suite with its hashes**;
at least three models from different families; three repeats; every run in a fresh workspace copy; model-written code only
inside a container; real prices in `bench agent-plan` before any spend; analysis by someone other than the benchmark's author.

---

### 12. Engineering and reproducibility

#### 12.1 Fidelity to the original project

The extended repository was compared with the original package programmatically (function and class names, every
parameter, MCP tool signatures, command-line subcommands and options, output keys, generated VMD/Tcl, representation and
colour tables). [Part III](#part-iii-what-changed-from-the-original-project), section 15, records what was retained,
what was restored after an earlier round dropped it, and what was deliberately not carried over. Where answers differ on
the same input, the original was wrong, and each difference is documented there.

#### 12.2 Tests

Property tests (Hypothesis) cover the pure functions and the pipeline on random inputs; real-data tests use real
structures and a real 20 ns trajectory; independent re-implementations (NumPy, an NeRF structure builder) cross-validate
analysis and DSSP. **Nothing stands in for another program.** Tests that need a real VMD or Tachyon, ffmpeg, the MCP SDK,
the network or a live model are marked and are skipped, with the reason shown, where that is absent (`pytest -rs`). A skip
is "unverified here", not a pass. The network tests use the real RCSB, AlphaFold and search services (including an
mmCIF-only entry) and a real local web server that serves exact bytes for size-cap, compression-bomb and HTML checks.

#### 12.3 Environments

Python 3.9 and Python 3.12, with either MCP SDK generation (1.x or 2.x). CI runs 3.9 and 3.12, plus a job for the
older MCP generation, and cannot run the real-VMD tests (VMD is not installable from a public package); they were run locally once (VMD 1.9.4a57, macOS arm64).

#### 12.4 Layout

```
src/vmd_agent/   inputs | structure | dynamics | visual | evidence | bench (agent/) ; auto, cli, server, environment, security
tests/           mirrors src/ ; data/ holds 4 real PDBs, a real 50-frame ubiquitin MD, and a labelled synthetic sample system
docs/            PAPER (this file), TECHNICAL, PREREGISTRATION, history/
docker/          Dockerfile, compose files, install_vmd.sh, vmd-dist/
```

---

### 13. Discussion and conclusion

The central claim of this work is about measurement, not about a tool: *confident error is a different failure from error, and
a benchmark for scientific automation should score it separately.* The benchmark is built so that a wrong answer given with
a warning, a wrong answer given without one, and a refusal are three different outcomes, and so that the right answer to a
damaged file or an event-free trajectory is to say so.

What remains is to run it. The infrastructure exists to do so with a real VMD and a real model, inside a container, with the
key protected and the analysis preregistered. The result may show that tooling helps, that it does not, or that it helps
only where the agent was already careful. Any of those would be informative, and none has been measured here.

---

### 14. References (to be verified before submission)

* Chodera, J. D., Swope, W. C., Pitera, J. W., Seok, C., Dill, K. A. (2007). Use of the weighted histogram analysis method
  for the analysis of simulated and parallel tempering simulations. *J. Chem. Theory Comput.* 3, 26-41. (equilibration
  detection and statistical inefficiency)
* Flyvbjerg, H., Petersen, H. G. (1989). Error estimates on averages of correlated data. *J. Chem. Phys.* 91, 461-466.
* Humphrey, W., Dalke, A., Schulten, K. (1996). VMD: visual molecular dynamics. *J. Mol. Graphics* 14, 33-38.
* Kabsch, W., Sander, C. (1983). Dictionary of protein secondary structure: pattern recognition of hydrogen-bonded and
  geometrical features. *Biopolymers* 22, 2577-2637.
* Kendall, M. G. (1975). *Rank Correlation Methods* (4th ed.). Griffin.
* Mann, H. B. (1945). Nonparametric tests against trend. *Econometrica* 13, 245-259.
* McGibbon, R. T. et al. (2015). MDTraj: a modern open library for the analysis of molecular dynamics trajectories.
  *Biophys. J.* 109, 1528-1532.
* Michaud-Agrawal, N., Denning, E. J., Woolf, T. B., Beckstein, O. (2011). MDAnalysis: a toolkit for the analysis of
  molecular dynamics simulations. *J. Comput. Chem.* 32, 2319-2327.
* Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. *J. Am. Stat. Assoc.* 63, 1379-1389.
* Shrake, A., Rupley, J. A. (1973). Environment and exposure to solvent of protein atoms. *J. Mol. Biol.* 79, 351-371.
* Stone, J. E. (1998). *An efficient library for parallel ray tracing and animation*. M.S. thesis, University of Missouri-Rolla.
* Theil, H. (1950). A rank-invariant method of linear and polynomial regression analysis. *Proc. Kon. Ned. Akad. v.
  Wetensch.* 53, 386-392.

---

### Appendix A. Command-line reference (benchmark)

```bash
vmd-agent bench agent-suite --out suite --seed 100 --base top.pdb traj.dcd --structures real/*.pdb --synthetic-dir synth
vmd-agent bench agent-preflight --suite suite --arms vmd_agent python_mdanalysis vmd_plain --allow-exec --model anthropic:<id>
vmd-agent bench agent-run --suite suite --baselines oracle sloppy reference          # no model, no network
vmd-agent bench agent-plan --suite suite --labels 6 --repeats 3 --price-in <USD/M> --price-out <USD/M>
vmd-agent bench agent-run --suite suite --model anthropic:<id> --arms vmd_agent python_mdanalysis --allow-exec --repeats 3
```

In a container with your VMD: `vmd-agent bench docker preflight|suite|plan|run --mode withvmd ...`.

### Appendix B. Timeline of the work

| Stage | Substance |
|---|---|
| Original | VMD automation for LLM agents: 24 tools, no tests with assertions, silently wrong in several places |
| First extension | Retention of all functionality; fixes (H-bond counting, chain counting, time axis); tests; security model; native mmCIF; native DSSP; honest statistics; keyframes; claim verification; provenance |
| Research layer | Grounding study, synthetic structures, real-noise event study, contamination estimator, cost planner |
| Reframing | Primary question changed from "can a model read a picture" to "can an agent automate the workflow, and fail loudly"; automation benchmark built |
| Audits | Two adversarial rounds, mutation testing, property tests, retention audit against the original |
| Real-component pass | Fake VMD, stub SDK and mocked network removed; real-tool gates; bring-your-own-VMD and Docker wiring |

### Appendix C. Glossary

*Silent error:* answered, wrong, did not abstain, flagged no data problem. *Cluster:* a base trajectory or a structure;
the unit the bootstrap resamples. *Arm:* a named set of tools. *Control:* an event task with no event, where the right
answer is "none". *Ping-pong extension:* extending a trajectory by reflecting it at both ends, preserving every local
step. *Grounding:* evidence supplied alongside an image (legend, colour key, measured statistics).

---

### Appendix D. Research questions in detail

This appendix is the map. Each question says why it matters, how it is tested, how to obtain the evidence, what is still
open, and what a negative answer would look like. The rest of this document gives the detail.

**One standing caveat.** No language model has been run on either benchmark, and this repository records no results of any
kind. Everything below describes a design and how to obtain evidence yourself. The author wrote both the toolkit and the
benchmarks, which is a conflict of interest the design tries to contain (see the preregistration).

#### At a glance

| # | Question | Role | How to obtain evidence |
|---|---|---|---|
| Q1 | Can an LLM agent automate VMD-style analysis and visualization workflows correctly, and does it fail loudly or silently? | **Primary** | run the automation benchmark with a model (README, section 5) |
| Q2 | Which tooling makes the difference: plain Python, plain VMD, this toolkit, or its parts? | Primary (arms of Q1) | the same run across arms |
| Q3 | Are the toolkit's own measurements correct? | Supporting | `vmd-agent validate`, `validate-dssp` (section 8.1) |
| Q4 | Does event-aware frame selection find short structural events that uniform sampling misses, and when does it stop helping? | Supporting | `vmd-agent bench events` (section 8.2) |
| Q5 | Do autocorrelation-aware statistics change the conclusions drawn from a trajectory? | Supporting | not built: would be an arm of the benchmark (drifting versus stationary trajectories) |
| Q6 | Can an agent's written claims be checked against the data, and how much of what it says can be checked? | Supporting | the `report` task family and `vmd-agent claims`; coverage on real write-ups is for you to measure |
| Q7 | Does structured grounding (legend, colour key, measured statistics) help a model read a rendered image? | Secondary | `vmd-agent bench run` (Appendix E) |
| Q8 | How much of a model's performance on molecular images is memorisation of famous structures? | Secondary | the same run with `--synthetic-dir` |

#### Q1. Can an LLM agent automate VMD-style workflows, and does it fail loudly or silently?

*Why it matters.* Researchers increasingly hand analysis to agents. A wrong answer with a warning costs a re-run. A
wrong answer without one enters a paper. Accuracy alone hides that difference, so the benchmark scores **silent
errors** (answered, wrong, no abstention, no data problem flagged) separately.

*How it is tested.* The automation benchmark (below): six task families (measure, event, diagnosis, selection,
keyframes, report) with answers known by construction, run under several tool arms, scored on success and silent
error, with a cluster bootstrap over trajectories and structures. Confirmatory hypotheses H1 to H3 are in the
preregistration.

*Evidence.* None is included. The scripted controls (section 8.4) test the scorers, not models.

*Open.* Everything about real models. Also data: the repo ships one real trajectory, so trajectory-level statistics
need many more.

*A negative answer* ("agents are about as accurate with and without the toolkit") is a reportable result, and the
preregistration commits to reporting it.

#### Q2. What does the tooling add?

*Why it matters.* If a benchmark only shows that an agent with the author's tools beats one without, it proves
little. The comparison that carries information is against a model that writes its own MDAnalysis code, and against
the toolkit with parts removed.

*How it is tested.* Arms on identical tasks: `python_mdanalysis`, `vmd_plain` (needs real VMD), `vmd_agent`, and two
ablations (without `verify_claims`, without `select_keyframes`). H1 is deliberately two-sided, with no predicted
direction.

*Evidence.* None is included. Run the `reference` control and inspect its failures: each is a gap in the toolkit, to be
reported and left unfixed during a confirmatory study so the toolkit is not tuned to its own benchmark.

*Open.* All model-based comparisons; whether `vmd_plain` can be run by a model at all (the arm's workspace and scoring passed against real VMD 1.9.4a57 on macOS; no model has used it).

#### Q3. Are the toolkit's measurements correct?

*Why it matters.* A benchmark of agents is meaningless if the tools it provides compute wrong numbers.

*How it is tested.* Cross-checks against independent code and data: RMSD, Rg, contacts, SASA and others against
independent NumPy; the built-in DSSP against the PDB's own annotations and against MDTraj; the novel-structure
generator against its own design intent.

*Evidence.* None is included; produce it with `vmd-agent validate`, `validate-dssp` and `bench synth` (section 8). The
defects that validation work has found in the toolkit are recorded in the CHANGELOG.

*Open.* DSSP against `mkdssp` itself; larger and more varied structure sets (the 50 are mostly small soluble
proteins); the ffmpeg code paths (not installed where this was tested) and VMD on Linux or Windows; the VMD and Tachyon paths passed their tests against 1.9.4a57 on macOS arm64 only.

#### Q4. Does event-aware frame selection beat uniform sampling?

*Why it matters.* An agent can only interpret the frames it is shown. A short event that falls between uniform
samples is invisible, and the interpretation will say "stable".

*How it is tested.* Real ubiquitin MD noise, extended by ping-pong reflection, with one injected rigid event
(hinge, dissociation, expansion) of known size and onset; equal frame budget; detection and localisation measured
over many trials. A no-event control counts invented change points.

*Evidence.* None is included; produce it with `vmd-agent bench events` on your trajectory (section 8.2) and report hit
rate against the event's size in noise sd.

*Open.* The events are synthetic rigid motions, and the false-alarm check is one realisation per trajectory. The detector
is designed for abrupt events; the benchmark's slow-ramp event tasks probe that limit.

#### Q5. Do autocorrelation-aware statistics change the conclusions?

*Why it matters.* Consecutive MD frames are correlated, so a naive standard error overstates certainty and naive
"stable" verdicts are easy to reach. The toolkit reports statistical inefficiency, effective sample size, a trend test
(Mann-Kendall with Theil-Sen) and an explicit "insufficient data" verdict.

*Evidence.* None is included. The methods are implemented and property-tested; run `vmd-agent analyze ... --do rmsd
convergence` on your trajectory to see the effective sample size and the verdict it gives.

*Open.* **No study measures whether this changes what an agent concludes.** That would be a natural arm of the
automation benchmark (drifting versus stationary trajectories). It is not built.

#### Q6. Can written claims be verified, and how much is covered?

*Why it matters.* The strongest guard against a confident wrong write-up is to check it against the data.

*How it is tested.* A verifier maps template sentences or structured claims onto measurements (chain counts, ligand
burial, secondary-structure content, disulfides, RMSD stability, contact persistence) and returns supported,
contradicted, unverifiable or unparsed, failing closed.

*Evidence.* None is included. The verifier is unit, property and mutation tested; `vmd-agent claims` and the `report` task
family exercise it.

*Open.* **Coverage.** The parser is template-based, so many natural sentences come back unparsed. How much of a real
model's write-up is checkable is unknown. Also circularity: the verifier is part of the toolkit and also scores the
`report` task family, so that family is exploratory only.

#### Q7. Does structured grounding help a model read a rendered image?

*Why it matters.* A narrower, controlled version of the same idea: hold the picture fixed, vary the evidence given
with it (legend, colour key, measured statistics), and see what changes.

*How it is tested.* The grounding study (below): eight evidence conditions, ground truth from the structure file,
questions labelled by which source can answer them (so abstaining is scored as correct when the evidence cannot settle
the question), and traps (a deliberately wrong legend). H3 of that study, on the one question only the image can
answer, is the test of actual vision.

*Evidence.* None is included. The offline `stats-reader`, `oracle`, `constant` and `random` models exist only to test that
the harness measures what it says.

#### Q8. How much is memorisation?

*Why it matters.* A model that recognises ubiquitin from its shape can answer from memory rather than from the picture.

*How it is tested.* Procedurally generated structures no model has seen, with truth measured from the coordinates, and
a difference-of-differences estimate that uses a text-only condition as a difficulty reference.

*Evidence.* None is included. The estimator is tested on planted effects by the repository's tests.

*Open.* Whether synthetic folds (idealised rods and sheets) are as easy to read as real ones. If they are harder, the
estimate is biased, which is why raw and adjusted gaps are reported together.

#### What this repository does not claim

* That agents using it are more accurate than agents without it. That is Q1 and Q2, unrun.
* That the toolkit is a complete VMD replacement. It reads, measures, renders and checks; it does not run MD or
  replace VMD's plugins.
* That the synthetic events and structures resemble real conformational change or real proteins.
* That the scripted controls say anything about models.
* That anything has been verified against real VMD, real ffmpeg, a built Docker image, or a live model API.

#### How the questions connect

Q3 is the foundation (the tools must be right). Q4 to Q6 are the toolkit's three claims about *evidence quality*:
show the right frames, state honest statistics, check the write-up. Q1 and Q2 ask whether those claims matter to an
agent doing real work, and Q7 and Q8 isolate the vision half of the story. A paper would lead with Q1/Q2 as a
benchmark contribution, report Q3 to Q6 as supporting validation, and treat Q7/Q8 as a component study.

---

### Appendix E. Grounding study specification

*A component study (Q7 and Q8): does a legend plus measured statistics help a model read a rendered image? The
analysis plan is in the [appendix of the preregistration](#appendix-grounding-study-draft).*

> This is the **secondary** study: it isolates one ingredient of the toolkit, the evidence format given alongside a
> rendered image. The primary study is the end-to-end [automation benchmark](#5-the-automation-benchmark). Use this one to
> answer "does a legend plus measured statistics help a model *read a picture*?", not "does the agent work?".

**Research question.** Does structured grounding (visual legend, colour key, measured statistics) make a
model's reading of a molecular visualization more accurate, better calibrated and less prone to
hallucination?

**Analysis plan:** [the grounding-study appendix of Part II](#appendix-grounding-study-draft) (draft, fill the TODOs and register before running).

**Status.** The harness, ground truth, scorer, controls, a contamination-free structure generator and a
cost planner are implemented and tested. **No results are included.** Running it on real models needs your API key.

#### Design

* **Ground truth comes from the structure file**, never from a model: chain count, DSSP fold class,
  disulfides, presence of ligand/lipid/nucleic acid, ligand burial (Shrake-Rupley).
  Thresholds are named constants in `bench/truth.py`.
* Each question lists the **sources that could answer it**: `image`, `legend`, `stats`.
  Asking for a disulfide count from a bare picture is not a vision failure; it is a question the evidence
  cannot settle, so the right answer is to *abstain*. This separates wrong answers from unsupported ones.
* Structures get **anonymous IDs** and panels carry no file name, so a model cannot read the identity.
* Models are handed a **redacted question**; only the explicit oracle control sees the answer.

#### Conditions (the grounding ladder)

| condition | evidence given |
|---|---|
| `blind` | nothing (control: assertions from priors) |
| `raw` | one render |
| `legend` | + visual legend |
| `annotated` | one panel with legend, colour key and stats drawn on |
| `legend_stats` | render + legend + measured statistics |
| `multiview_legend_stats` | three views + legend + statistics |
| `text_only` | legend + statistics, **no image** (control: what the text alone settles) |
| `misleading_legend` | render + a **wrong** legend (trap: do models trust text over pixels?) |

#### Metrics (`bench/scorer.py`)

accuracy · coverage · **hallucination rate** (wrong / answered) · **unsupported-assertion rate**
(answered when the evidence could not settle it) · appropriate/over-abstention · ECE and Brier.
Confidence intervals are a **cluster bootstrap over structures** (questions about one structure are not
independent). Paired contrasts (e.g. `legend_stats − raw`) are reported with CIs.

#### Running it

```bash
# offline baselines (no key, no network)
vmd-agent bench run structures/*.pdb --model stats-reader --renderer matplotlib --out-dir out

# a real model (needs `pip install anthropic` and ANTHROPIC_API_KEY)
vmd-agent bench run structures/*.pdb --model anthropic:<model-id> --out-dir out --repeats 3
```

Outputs: `records.jsonl` (every reply), `summary.json`, `summary.md`, `manifest.json` (versions, structure
hashes, renderer, conditions).

Other studies:

```bash
vmd-agent bench sampling --n-frames 1000 -k 9        # uniform vs event-aware frame selection
vmd-agent bench rating-sheet structures/*.pdb        # blinded expert-rating sheet (needs VMD)
vmd-agent bench rating-summary ratings.csv key.json  # unblind + paired statistics
```

#### Memorisation control: novel structures and the adjusted gap

A model may recognise ubiquitin from its shape. `vmd-agent bench synth N` generates structures from scratch
(helix bundles, antiparallel sheets, mixed, coil; 1 to 4 chains; optional buried or exposed ligand; optional
disulfides). Truth is **measured from the coordinates** with the same code as for real structures, and
`design_agreement` checks measured truth against construction and `bench synth` prints the agreement per property.

```bash
vmd-agent bench synth 100 --out synth --seed 1
vmd-agent bench run real/*.pdb --synthetic-dir synth --model anthropic:<id> --out-dir out
```

Keep the generated files and share the hashes in `design.json`: **the seed alone does not reproduce the structures across
machines** (floating-point differences between NumPy builds flip discrete choices; the same seed produced different
structures on Python 3.9 and 3.12).

The summary then reports a **real-vs-novel gap**. The raw gap mixes difficulty and memorisation, so the
`text_only` condition (which cannot identify a structure) is used as a difficulty reference, and the
**adjusted estimate = gap(condition) − gap(text_only)** isolates what the *image* adds on real structures
(difference of differences, cluster bootstrap within each group). The repository's tests check it on planted effects.

Assumption: the structure kinds differ in difficulty the same way for images as for text. If synthetic
renders are intrinsically harder to read than real ones, the adjusted estimate is biased; report the raw
and adjusted gaps together.

#### Plan the cost before spending anything

```bash
vmd-agent bench run real/*.pdb --synthetic-dir synth --dry-run --repeats 3 \
    --price-in <USD per M input tokens> --price-out <USD per M output tokens>
```

Counts model calls and images and estimates tokens (images ≈ w·h/750, text ≈ 4 chars/token). **No prices are
built in**; the figures come from the numbers you supply.

#### The offline control models

`oracle` (knows the answers), `constant`, `random` and `stats-reader` (reads only the text grounding and cannot see images)
need no key and no network. They exist to test that the harness measures what it claims (the oracle must score perfectly,
the constant and random models must sit at their floors, the text reader must abstain when its text cannot settle a
question), **not** as findings. Run: `vmd-agent bench run STRUCTURES --model stats-reader --renderer matplotlib`.

#### Caveats you must address in any paper

1. **Memorisation.** `blind` cannot detect it (no image). Use the synthetic group and the adjusted gap above, and
   report raw and adjusted gaps. Synthetic folds are idealised rods and sheets, not realistic proteins.
2. **Renderer dependence.** The matplotlib renderer draws a backbone trace, not ribbons. Run with VMD too,
   and report both; renderer dependence is itself a finding.
3. **Threshold definitions** (what counts as "mixed" or "buried") are choices; report sensitivity.
4. **Small N.** Compute the power for your own assumptions before leaning on the confidence intervals.
5. Temperature, prompt wording and answer format affect results; the manifest records the model ID and seed.

---

### Appendix F. What the test suite checks, and what is not verified

**This appendix records no outcomes.** It lists what the repository's tests are designed to check, so you know what a
passing run covers, and what has never been verified. Run `pytest -rs` to see what passes, what fails, and what is skipped.

#### Checked by the test suite

| Property | How |
|---|---|
| RMSD, Rg, contacts, COM distance agree with independent NumPy | SVD-Kabsch RMSD, mass-weighted Rg, brute-force contacts; `vmd-agent validate` repeats it on your data |
| DSSP reproduces known structure | NeRF-built ideal α-helix and strand, and PDB annotations (`validate-dssp` on your structures) |
| Statistical inefficiency is right | white noise, and AR(1) against `(1 + φ) / (1 − φ)` |
| Error bars are honest | autocorrelated series give wider intervals than naive ones |
| The drift detector is not trigger-happy, and a short run is not called "stable" | stationary AR(1); `insufficient_data` |
| H-bond geometry | linear D–H···A counted; a 90° angle and a long distance rejected; same-residue ignored; heavy-atom fallback labelled |
| Partial CONECT bonds are supplemented | inferred from covalent radii and the source labelled |
| mmCIF fallback works end to end | a real RCSB entry with no PDB-format file (`requires_network`) |
| SASA | an isolated sphere equals `4π(r + probe)²`; an enclosed atom is buried |
| Uniform-sampling formula | analytic hit probability against simulation |
| Scorers | oracle, constant and random controls; bootstrap interval narrows with N |
| VMD orchestration | generated Tcl is checked as text; with a real VMD (`requires_vmd`): one launch per movie or view set, scratch removed, non-blank PNGs |
| Security | sandbox (symlink, `..`, prefix-sibling, NUL byte), Tcl screen, URL policy, size and compression-bomb caps, validation of everything placed in generated Tcl |

#### Audit methods

Static analysis, targeted probes, fuzzing, property tests, mutation testing, a retention audit against the original and a
real-component pass; see section 9. Mutation testing is an ad-hoc script on a throwaway copy of the repository, not part of
CI.

#### Not verified (be explicit about these)

* **Against GROMACS / cpptraj / VMD / MDTraj.** Only against independent NumPy code. To compare, compute RMSD/Rg/H-bonds
  for the same trajectory and selection with `gmx rms`/`gmx gyrate`/`gmx hbond` (or cpptraj `rmsd`/`radgyr`/`hbond`) and
  diff the series. Expect agreement to numerical precision for RMSD/Rg *if* you use identical atom selections, fitting and
  mass weighting; H-bond counts depend on criteria.
* **DSSP versus `mkdssp` itself.** Compare it on your structures.
* **Real VMD / Tachyon / ffmpeg:** the tests that need them are skipped where the program is absent. The VMD/Tachyon ones passed once
  against VMD 1.9.4a57 on macOS arm64; ffmpeg was absent there, and Linux and Windows VMD builds were never tried.
* **Docker images:** never built (see [Docker](../README.md#docker)).
* **The MCP SDK:** tested through the real SDK where installed; not run in a real MCP client by the author.
* **Real language models:** no benchmark has been run.
* **Keyframes on real events:** the event study keeps the noise real but the *event* synthetic (a rigid motion). It does
  not show the detector finds a real folding or unbinding event.
* **Statistical power** of the drift test at realistic MD lengths.

#### Reproduce

See the README, section "How to run": install, `pytest -rs`, the validation commands, and the benchmark commands.

---

## Part II: Preregistration (draft)

**Status: draft, not registered.** No language model has been run on the benchmark. This becomes a
preregistration only when you fill the `TODO` fields, commit it, and deposit a copy (OSF or AsPredicted) **before the
first real-model run**. After that, changes are listed as deviations. The scripted baselines in
[the automation benchmark](#5-the-automation-benchmark) are harness checks and are not data for these hypotheses.

Operational rules:
* **The model that wrote this benchmark does not run it or analyse its results.**
* **Freeze the toolkit** (git hash `TODO`) before the confirmatory run. The toolkit was changed after seeing the
  benchmark during development (the NaN-frame fix); the confirmatory run must not see further tuning.
* **Use held-out suites.** Development used seeds 0 to 9. The confirmatory suite uses seed `TODO` (≥ 100) on
  trajectories and structures that were not used to develop tasks or the toolkit. **Deposit the generated suite
  directory itself** (files and their SHA-256 hashes, which the runner checks): a seed alone does not reproduce the
  synthetic structures across machines, because floating-point differences between NumPy builds flip discrete choices.

### 1. Question

When an LLM agent is asked to carry out molecular-visualization and trajectory-analysis tasks, how often is it correct,
how often is it wrong **without any warning**, and does the choice of tooling change this?

### 2. Design

* **Models:** at least 3, from different vendors/families: `TODO` (IDs and snapshot dates). Temperature `TODO`
  (suggest 0), `max_tokens`, `max_turns` (suggest 30). Analysed per model; no pooling unless a pooled model is added here.
* **Arms (tools):** `python_mdanalysis`, `vmd_agent`, `vmd_agent_no_verify`, `vmd_agent_no_keyframes`; `vmd_plain`
  only if real VMD is installed and verified (`TODO`: yes/no).
* **Tasks:** the six families in [section 5 of Part I](#5-the-automation-benchmark); real trajectories `TODO` (≥ 10 distinct), real structures
  `TODO` (≥ 30), synthetic structures `TODO`, chosen **before running** by this rule: `TODO` (e.g. random draw with a
  fixed seed from a stated pool).
* **Repeats:** 3 per (task, arm).
* **Isolation:** every run in a fresh workspace copy; model-written code runs only inside a container/VM.
* **Cost:** estimate from `bench agent-plan` with the real prices: `TODO`.

### 3. Confirmatory hypotheses

Resampling unit: the **cluster** (a base trajectory or a structure); tasks from one cluster are not independent.
Statistic: mean per-task difference between arms, repeats averaged
(`scoring.paired_arms`), over the family-balanced set of `measure`, `event`, `diagnosis`, `selection` and
`keyframes` tasks. A task counts a **silent error** when the answer was wrong, no abstention, no data problem flagged.

| ID | Contrast | Prediction |
|---|---|---|
| H1 | success: `vmd_agent` − `python_mdanalysis` | two-sided, **no directional prediction** (a tool can help or hinder; the author has a conflict of interest) |
| H2 | silent-error rate: `vmd_agent` − `python_mdanalysis` | < 0 (the toolkit's notes, warnings and diagnostics surface problems) |
| H3 | success on **`diagnosis`** tasks: `vmd_agent` − `python_mdanalysis` | > 0 (damaged files are exactly what its checks are for) |

Family = H1–H3, Bonferroni α = 0.05 / 3 ≈ 0.0167, two-sided; a contrast is significant when
`paired_arms(..., alpha=0.05/3)` excludes 0. All three are reported whatever the sign, for every model.

### 4. Secondary and exploratory (labelled as such; no multiplicity claims)

* **Ablations:** `vmd_agent` − `vmd_agent_no_keyframes` on `event` and `keyframes`; `vmd_agent` −
  `vmd_agent_no_verify` on `report` (**circular**: the verifier is also the scorer, so this is exploratory only).
* Per family, per model; false-alarm rate on event-free controls; abstention; calibration of stated confidence;
  tool calls, tokens, wall time and cost per solved task.
* `vmd_plain` against `python_mdanalysis` if available.
* Whether success differs on tasks the scripted reference agent could not solve with the toolkit (known gaps:
  centre-of-geometry distance, slow transitions).

### 5. Sample size

There is no pilot, so the effect size and the spread of cluster-level differences are **assumptions you must state
here before registering**: effect `TODO`, SD across clusters `TODO`, clusters `TODO`, target power `TODO`. Compute the
power with the snippet below and record the result in this section.

```python
# Power of a paired, cluster-level contrast (t approximation of the cluster bootstrap).
# Run it with YOUR assumed effect and spread; no values are provided here on purpose.
import numpy as np
from scipy import stats

def power(effect, sd, n_clusters, alpha=0.05/3, sims=5000, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(effect, sd, (sims, n_clusters))
    t = x.mean(1) / (x.std(1, ddof=1) / np.sqrt(n_clusters))
    p = 2 * stats.t.sf(np.abs(t), n_clusters - 1)
    return float((p < alpha).mean())

# for n in (8, 12, 20, 40): print(n, power(effect=<assumed>, sd=<assumed>, n_clusters=n))
```

Guidance, not a result: the repository ships **one** real trajectory, which is one cluster for the trajectory families,
so the trajectory families need real MD data from you (static structures supply clusters cheaply). Plan a pilot of
about 10 clusters, **excluded from the confirmatory set**, to estimate the spread before fixing the final size. A null
result must be reported as "no difference larger than the interval", not "no difference".

### 6. Analysis plan

1. Fixed exclusions: tasks whose workspace failed to build are listed and dropped for all arms; an agent crash or a
   missing submission counts as a failure (not a silent error) and is reported.
2. Contrasts in §3 with `n_boot = 10000`, seed `TODO`.
3. Report effect sizes with intervals for all contrasts, all models, including those that disagree.
4. Sensitivity: micro versus family-balanced averaging; without the `report` family; real structures only;
   excluding the two known toolkit-gap task kinds.
5. Deviations from this document are listed with reasons.

### 7. Threats, stated up front

* **Author conflict of interest** and tool-tuning: see the rules above. Prefer the framing "a benchmark with the
  toolkit as one entrant" over "the toolkit wins".
* **Synthetic events and idealised synthetic structures:** realism of conformational change is untested; one protein
  family unless more data is added.
* **Prompt and tool-description sensitivity:** one system prompt, identical across arms; tool descriptions differ by
  nature. A prompt-variation arm is an extension, not part of this registration.
* **Scorer limits:** tolerances and the "event window" are choices (constants in `bench/agent/`); report sensitivity.
* **Execution safety:** model-written code is not sandboxed by the benchmark.
* **Model drift:** record dates and snapshots.

### 8. Fields to fill before registering

`TODO` markers above (models, toolkit hash, seed, trajectory/structure sets and selection rule, temperature, budget,
bootstrap seed, whether `vmd_plain` is included). Then: commit, tag (`git tag prereg-v1`), deposit, and only then run.

---

### Appendix: grounding study (draft)

*A separate, narrower preregistration for the component study (Q7 and Q8 in [Part I, appendix D](#appendix-d-research-questions-in-detail)).
Register it separately if you run that study.*

**Status: draft, not yet registered.** Nothing here has been tested on a real model. It only becomes a
preregistration when you (1) fill the `TODO` fields, (2) commit it, and (3) ideally deposit a copy on OSF or
AsPredicted *before* any real-model run. Edit it freely until then; after the first real call, changes must be
listed as deviations. The offline baselines in [appendix E of Part I](#appendix-e-grounding-study-specification) are harness checks and are not data for these
hypotheses.

Operational rule: **the model that wrote this benchmark does not run it or analyse its results.**

#### 1. Question

Given a molecular rendering, does adding structured grounding (legend tying colours to detected components,
colour key, measured statistics) change how accurately, how honestly (abstention) and how well-calibrated a
vision-language model (VLM) answers factual questions about the structure?

#### 2. Hypotheses (confirmatory)

Resampling unit: the **structure** (questions on one structure are not independent). The statistic is the
mean over paired `(structure, question)` cells, repeats averaged (`scorer.paired_difference`), so a structure
with more applicable questions weighs more. Conditions are defined in `bench/conditions.py`. An unanswered or
unparseable reply counts as incorrect (it cannot be right) and as an abstention, never as missing; accuracy
therefore also falls when a model abstains, which is why H2 and the abstention metrics are reported next to it.

| ID | Contrast (paired, per structure) | Prediction |
|---|---|---|
| H1 | accuracy: `legend_stats` − `raw` | > 0 |
| H2 | per-question hallucination indicator (answered *and* wrong; metric `hallucination`): `legend_stats` − `raw` | < 0 |
| H3 | accuracy on **image-only questions** (`ligand_buried`; the only question whose sole source is `image`): `multiview_legend_stats` − `raw`, `keys=["ligand_buried"]` | ≠ 0 (two-sided; no prediction, tests whether grounding helps or hurts what only pixels can answer) |

Primary family = H1–H3, Bonferroni α = 0.05 / 3 ≈ 0.0167 per test, two-sided; a contrast counts as
significant when its `paired_difference(..., alpha=0.05/3)` cluster-bootstrap interval excludes 0. All three are reported whatever the sign.

H3 matters most: H1 can be won by a model that just reads the statistics text. `text_only` is therefore a
**required reference**, not an optional extra: the part of H1 attributable to the *image* is
`(legend_stats − raw) − (text_only − blind)`, and is reported alongside it.

#### 3. Secondary and exploratory (labelled as such in the paper; no multiplicity claims)

* **Trap:** accuracy and hallucination under `misleading_legend` vs `raw` (do models follow text over pixels?).
* **Calibration:** ECE and Brier per condition.
* **Abstention:** appropriate vs over-abstention per condition (`scorer` definitions).
* **Memorisation:** real-vs-synthetic gap and the difference-of-differences estimate
  `contamination_estimate` (adjusted by `text_only`); raw and adjusted reported together.
* **Renderer dependence:** repeat on VMD renders if available; report both.
* Per-question-type results, per model. Nothing here is used to decide the main conclusion.

#### 4. Design

* **Models:** at least 3 VLMs from different vendors/families: `TODO` (IDs and the snapshot dates).
  Temperature `TODO` (suggest 0), `max_tokens` `TODO`, the prompt template as in `bench/questions.py` at the
  committed git hash `TODO`. One analysis per model; no pooling across models unless a pre-stated mixed model is
  added here first.
* **Structures:** real = `TODO` PDB IDs, **chosen before running by a rule written here** (e.g. random draw with a
  fixed seed from a stated set, stratified by system type); synthetic = `bench synth N --seed TODO`.
  Do not drop structures after seeing results; failed renders are reported, not silently removed.
* **Repeats:** 3 per cell.
* **Conditions:** all 8 default conditions.
* **Prices and budget:** run `--dry-run` first with the real prices; record the estimate here: `TODO`.
* **Software:** repository git hash, `manifest.json` from the run archived with the results.

#### 5. Sample size

The effect and the per-structure spread of the paired difference are **assumptions you must state here**: effect
`TODO`, SD of the difference `TODO`, structures `TODO`, power target `TODO`. Compute the power with the same snippet as
in section 5 above (use `n_clusters` = number of structures). Re-estimate the SD from a **small pilot on structures
that are then excluded from the confirmatory set** (suggest 10) and update this section before the confirmatory run.
If the result is a null, report it as "no effect larger than the CI bounds", not as "no effect".

#### 6. Analysis plan

1. Exclusions, fixed now: structures whose
   ground truth failed (`truth.ok` false) are excluded and listed.
2. Compute the contrasts in §2 with `paired_difference(..., n_boot=10000, seed=TODO)` on real and synthetic
   structures pooled; the real-versus-synthetic split is a secondary analysis.
3. Report effect sizes with CIs for every contrast, all models, including those that disagree.
4. Sensitivity (reported, not used to pick a conclusion): alternative thresholds for "buried" and "mixed" fold
   (constants in `bench/truth.py`); excluding `has_lipid` (nearly always false, so easy by default); real
   structures only.
5. **Deviations** from this document are listed in the paper with reasons.

#### 7. Known threats, stated up front

* **Memorisation** of famous PDB entries. `blind` cannot detect it. Mitigation: synthetic structures and the
  adjusted gap. Synthetic folds are idealised, so the adjustment assumes images of both kinds are equally easy to
  read. This assumption is untested.
* **Many questions are answerable from the legend alone** (`has_ligand`, `has_lipid`, `has_nucleic`). Grounding
  "helping" there is expected and is not evidence about vision; that is why H3 and the `text_only` reference exist.
* **The question set was written by the tool's author** and the grounding text is generated by the same
  tool that computes the truth (shared detection code). Where the legend and the ground truth derive from the same
  function, agreement is partly circular. The synthetic design check and the independent NumPy validation reduce
  but do not remove this. Use the human baseline (`bench rating-sheet`) as an outside reference.
* **Renderer:** the default open-source renderer draws a backbone trace, not ribbons.
* **Prompt sensitivity:** one prompt template. A prompt-variation arm is a possible extension, not part of this
  registration.
* **Model drift:** APIs change; record dates and model snapshots.

#### 8. Fields to fill before registering

`TODO` markers above: model IDs, structure list and selection rule, synthetic seed, temperature, budget,
bootstrap seed, git hash. Then: commit, tag (`git tag prereg-v1`), deposit a copy, and only then run.

---

## Part III: What changed from the original project

**Original:** `~/Desktop/AGENTIC_VMD (Sri)` (untouched; no file in it was modified).
**This copy:** `~/Desktop/AGENTIC_VMD_v2`.
The "original package" below means `vmd-agent-new/` (the editable install that actually ran).
Line counts were measured with `diff`/`wc`, not estimated.

### 0. Size at a glance

| | Original | v2 |
|---|---|---|
| Package code | 17 flat modules | subpackages that follow the pipeline (inputs, structure, dynamics, visual, evidence, bench) plus composing modules |
| Tests | 1 script with **no assertions** (collected nothing) | a test suite mirroring the package (`pytest -rs`) |
| MCP tools | 24 (README said 12, then listed 15) | 27 |
| Docs | README, ARCHITECTURE (+ duplicate READMEs) | README, PAPER, TECHNICAL, PREREGISTRATION, CHANGELOG, NOTICE, this file |
| Packaging/CI | none | Dockerfile, compose, CI, LICENSE, .gitignore |

---

### 1. Repository structure

| Change | Detail |
|---|---|
| **Removed** `vmd-agent/` | Its source was byte-identical to `vmd-agent-new/`; only the README differed |
| **Removed** root `fetch.py` | Stale third copy; still had the hard-coded AlphaFold versions (4, 3, 2) that the package version had already fixed |
| **Removed** `render.dat` | Stray Tachyon scene file from an old recipe |
| **Removed** `README_1.md` | Duplicate of an older README |
| **Removed** `vmd_agent.egg-info/` | Generated artefact |
| **Renamed** `vmd-agent-new/` → `vmd-agent/` | Single package |
| **Removed from v2** all `*_run/`, `1BEB_whey_protein/`, `vmd_agent_output/` (a large set of PNG renders) | Still in the original folder. The real ubiquitin MD (`protein.pdb/.dcd`) is kept as `tests/data/ubq_md/` |
| **Added** root `README.md`, `LICENSE`, `NOTICE.md`, `CHANGELOG.md`, `.gitignore`, `.github/workflows/ci.yml` | |
| **Removed** `tests/test_fetch_offline.py` | Replaced by real assertions in `tests/test_fetch_media_report.py` |
| **Added** `tests/data/` | 4 real PDBs (1ubq, 1lyz, 4hhb, 1beb) |

### 2. Modules unchanged

`annotate.py`, `inspection.py`, `representations.py`: 0 lines differ.

### 3. Modules modified (lines added / removed)

| Module | +/− | What changed |
|---|---|---|
| `analysis.py` | +399 / −147 | Rewritten. Honest time axis (`time (ps)` only for readers that record time, else `frame index`); verdicts from `timeseries` instead of fixed thresholds; per-residue RMSF on a **copy** of the universe; angle-based H-bonds (own implementation replaces MDAnalysis `HydrogenBondAnalysis`, which needs charges); contacts report atom and residue-pair counts and fraction of frames in contact; SASA scratch dir cleaned; `convergence` analysis; PBC diagnostics (per-atom half-box jumps) and `unwrap=`; `selection matched 0 atoms` errors; mmCIF-aware loading |
| `render.py` | +311 / −167 | Scratch dirs removed after every call (`keep_work=` to retain); `render_movie` now **one VMD session, one fixed camera** (was one VMD per frame, camera reset per frame); new `render_frames`; Tachyon runs in parallel; `run_vmd_tcl` screened by `security`; timeouts return structured errors; ffmpeg-missing path keeps frames |
| `stats.py` | +200 / −111 | Partial `CONECT` bonds detected and supplemented by inference; H-bonds angle-based when hydrogens exist (`hbond_method` says which); vectorised ion mask and salt bridges (were per-atom Python loops); His excluded from salt bridges by default; secondary structure from the new DSSP; `count_hydrogen_bonds` exposed for reuse |
| `server.py` | +182 / −79 | `@tool()` wrapper turns policy violations into structured errors; path sandbox on every tool; `view_image` serves image files only; `renderer` argument; session now stores renderer + provenance; 3 new tools; `analyze_trajectory(unwrap=)` |
| `cli.py` | +151 / −3 | New subcommands `keyframes`, `claims`, `validate`, `provenance`, `renderers`, `bench {truth,run,sampling,rating-sheet,rating-summary}`; `--renderer` on `show`/`visualize`; `--unwrap` on `analyze`; renderer printed in the brief |
| `auto.py` | +102 / −34 | `renderer=` argument (`auto` falls back to matplotlib instead of returning no images); legend and colour keys built from what the backend **actually drew**; water colour key only when water shown; provenance written per run; renderer caveats added to the interpretation instructions; Tube descriptions |
| `report.py` | +102 / −15 | New sections **L** (claim verification) and **M** (reproducibility); figure paths relative to the report; atomic session writes; corrupt `session.json` quarantined instead of crashing; crash on missing numbers fixed; limitations auto-populated (PBC warning, thin data, renderer caveats) |
| `fetch.py` | +84 / −5 | `check_url` (http/https only, no loopback/private/link-local hosts), redirect-hop validation, size cap, gzip-bomb cap |
| `detect.py` | +24 / −14 | Loads via `molio` (mmCIF); O(n²) claimed-atom loop vectorised; material heuristic split into unambiguous elements (≥50 atoms) and bio-relevant S/Fe/Zn/Cu/Ni (≥500) |
| `recipes.py` | +22 / −9 | `representations_added` now reflects focus / pLDDT / explicit representation; `.mmcif`, `.ent`, `.pqr`, `.pdbqt`, `.lammps(trj)`, `.netcdf` file-type mapping; f-string nit |
| `media.py` | +20 / −7 | ffmpeg frame-select expression no longer relies on an invalid-escape string; tries both valid filter spellings and both `-fps_mode`/`-vsync` flag spellings |
| `environment.py` | +16 / −3 | Renderer inventory, `recommended_renderer`, `can_render_any`, `in_docker`; hard-coded `/home/<user>/...` examples removed; VMD "not bundled" guidance |
| `__init__.py` | +21 / −11 | Version 0.5.0 → **0.6.0**; exports `verify_claims`, `select_keyframes`, `get_renderer` |
| `colorkey.py` | +2 / −2 | "Structure" key no longer claims STRIDE-in-VMD only (also DSSP in the matplotlib backend) |

### 4. New modules

| Module | Lines | Purpose |
|---|---|---|
| `molio.py` | 181 | Native **mmCIF reader** + `load_universe` (used everywhere) |
| `dssp.py` | 206 | Kabsch-Sander **DSSP** in NumPy (sparse bridge search) |
| `timeseries.py` | 258 | Statistical inefficiency, N_eff, block averages, Mann-Kendall/Theil-Sen, half comparison, equilibration, `assess_stationarity` |
| `keyframes.py` | 334 | Event-aware keyframe selection, evaluation metrics, uniform-sampling theory |
| `claims.py` | 510 | **Claim verification**, sentence parser, Shrake-Rupley SASA / ligand burial |
| `validation.py` | 105 | Cross-check against independent NumPy implementations |
| `security.py` | 99 | Path sandbox, Tcl deny-list |
| `provenance.py` | 154 | Per-run provenance and verification |
| `renderers/` (5 files) | 706 | `base`, `vmd`, `mpl` (open-source renderer, 413 lines), `pymol` (experimental), registry |
| `bench/` (9 files) | 1,205 | `truth`, `questions`, `conditions`, `models`, `scorer`, `runner`, `sampling`, `rating_study` |

### 5. Bugs fixed (all present in the original)

1. **mmCIF fallback unusable**: `fetch` fell back to mmCIF but MDAnalysis cannot read it, so large entries failed at detection.
2. **Secondary structure never worked** on MDAnalysis < 2.8 (`MDAnalysis.analysis.dssp` import hidden by a bare `except`).
3. **Partial bond records reported as the full count** (lysozyme reported only its explicit bond records).
4. **H-bond count was distance-only**, presented as geometric.
5. **Every plot said "time (ps)"** even when x was a strided frame index.
6. **RMSF was per atom** but documented per residue; "most flexible residues" could repeat.
7. **RMSF's in-memory alignment** silently changed coordinates for later analyses in the same batch.
8. **`render_movie`** launched VMD per frame and reset the camera each frame.
9. **Scratch directories leaked** (on every render call).
10. **Colour key listed water swatches** when water was hidden.
11. **`representations_added`** ignored focus / pLDDT / explicit representation.
12. **Material heuristic** fired on ≥50 S/Fe/Zn/Cu atoms.
13. **ffmpeg `eq(n\,k)` / `-vsync`**: fragile across versions; invalid-escape warning.
14. **`Session` write** could truncate on interruption; **report** crashed on missing numbers.
15. **Hard-coded paths** (`/home/<user>/...`) in docs and messages.
16. **`run_vmd_tcl` accepted `exec`** and arbitrary Tcl.
17. **`fetch` accepted `file://`, `ftp://` and internal addresses**; no size cap.
18. **Stale docs**: README said 12 tools, listed 15, code had 24; referenced a `tests/session/` that never existed.
19. **`pyproject.toml`** would have omitted any new subpackages from an install.

### 6. Statistics: fixed thresholds replaced

| Was | Now |
|---|---|
| RMSD "stable" if std < 0.5 Å | `assess_stationarity`: autocorrelation-corrected CIs, Mann-Kendall + Theil-Sen, half-vs-half, ≥ 10 effective samples required |
| Rg "collapse/expansion" if ΔRg > 1 Å | start-vs-end windows in corrected SE units, \|z\| > 3 |
| Contacts "stable" if std < 15 % of mean | fraction of frames in contact + stationarity |
| 8 frames could be called "stable" | `insufficient_data` |
| No PBC awareness | per-atom half-box jump detection, optional `unwrap` |

### 7. New features (none existed before)

Renderer abstraction (VMD / **matplotlib**) · event-aware **keyframes** + closed-form sampling analysis ·
**claim verification** · **grounded-interpretation benchmark** (ground truth, questions, 8-condition ladder, scorer with
cluster bootstrap, runner, Anthropic adapter, sampling study, blinded rating study) · **provenance** · `validate` ·
server **sandbox** + Tcl screening + URL policy · `convergence` analysis.

### 8. Containers, CI, licensing

`Dockerfile` (targets `runtime`, `vmd-libs`, `with-vmd`) · `docker/entrypoint.sh` · `docker/install_vmd.sh` ·
`docker-compose.yml` (hardened: non-root, read-only, caps dropped) · `.dockerignore` · `vmd-dist/README.md` ·
`.github/workflows/ci.yml` (Python 3.9/3.11/3.12 + Docker build + smoke tests) · `LICENSE` (MIT) · `NOTICE.md`
(VMD not bundled; MDAnalysis is GPL) · `.gitignore` (never commit VMD).

### 9. Dependency / packaging changes

| | Original | v2 |
|---|---|---|
| Version | 0.5.0 | 0.6.0 |
| Core deps | MDAnalysis, numpy, scipy, matplotlib, networkx, pandas | **+ pillow** (was used but not declared) |
| Extras | `server`, `sasa`, `dssp` (mdtraj), `all` (mcp, freesasa, mdtraj) | `server`, `sasa`, `bench` (anthropic), `dev` (pytest), `all`; **`dssp` extra and mdtraj removed** (built-in DSSP) |
| Packages | `["vmd_agent"]` | `["vmd_agent", "vmd_agent.bench", "vmd_agent.renderers"]` |
| pytest config | none | markers, warning filters |

### 10. Behaviour changes that could affect existing callers

Review these if anything outside this repo uses the old API.

* `structure_stats(hbond_cutoff=...)`: the argument is now **accepted and ignored** (`**_legacy`). Salt bridges **exclude His by
  default** (original included it). H-bond and bond counts will differ (see §5). `n_hydrogen_bonds_geometric` is kept as an alias of `n_hydrogen_bonds`.
* `analyze_trajectory`: new `unwrap` parameter; `interpretation` strings are different; results gain `stationarity`, `time_axis`,
  `pbc`, `notes`; `hbonds` values differ (own implementation, no charges needed); `rmsf` is per residue. `drift_2nd_half` is kept.
* `render_image` / `render_views`: **no longer return `scene_file` / `scenes`** unless `keep_work=True`. `render_movie` returns
  `source_frames` and `stride`, and `frames_dir` only with `keep_frames=True`.
* `visualize_and_interpret` / `fetch_and_visualize`: new `renderer` argument. With `auto` and no VMD you now get **images from the
  matplotlib backend** (previously: no images and a note). They also write `provenance.json` into `out_dir`, and the package has new
  `renderer` and `provenance_path` keys.
* `build_color_keys`: water key only with `show_water=True`.
* `run_vmd_tcl`: may return `{"ok": False, "blocked": True}`.
* `fetch_structure(source="url")`: may refuse a URL; `_http_get` gained `max_bytes`.
* Server: tools return `{"ok": False, "blocked": True, ...}` on policy violations; `view_image` raises for non-image extensions.
* `Session` data gained `claims`, `provenance`, `renderer`; reports gain sections L and M.
* `probe_environment` gained `renderers`, `recommended_renderer`, `can_render_any`, `pymol`, `in_docker`.

### 11. Things that are the same on purpose

* The central design (code prepares evidence, the model interprets), the MCP-first shape, the 12-representation
  catalogue, VMD palette tables, focus plans, the inspection rules, and the video-verification pipeline.
* Python ≥ 3.9 for the core; the MCP server still needs ≥ 3.10.

### 12. Not changed / not done

Docker images unbuilt · real VMD/ffmpeg never run (fakes only) · no real-model benchmark results · DSSP not compared to `mkdssp` itself (it *is* compared to PDB annotations and MDTraj, see VALIDATION.md) · EGFR/TP53/PD-1 example folders are empty in the original.

---

### 13. Second round (0.7.0): evidence and a leaner repo

* **Version** 0.6.0 → **0.7.0**.
* **New modules:** `bench/events.py` (real-noise event study), `bench/synth.py` (procedural novel structures + generator
  validation). **Extended:** `validation.py` (DSSP vs PDB records and MDTraj), `bench/scorer.py` (`group_difference`,
  `contamination_estimate`), `bench/runner.py` (`groups`, `plan_benchmark`), `analysis.py` (`dt_ps`, DCD time warning),
  `stats.py` (`n_protein_chains`, `n_nucleic_chains`, `n_chains_all`), `dssp.py` (returns chain labels), `cli.py`
  (`validate-dssp`, `bench synth|events`, `--synthetic-dir`, `--dry-run`, `--price-in/--price-out`, `--dt-ps`).
* **Removed:** PyMOL backend (never run; it was added in v2, not in the original), `networkx`/`pandas` dependencies (never
  imported), unused imports, the legacy `examples/` renders, the duplicate NeRF code in `tests/conftest.py`.
* **Behaviour changes:** `stats["n_chains"]` now counts **polymer** chains (was every chain ID, including ligands and waters);
  the figure panel says "N protein chains"; `analyze_trajectory` results' `time_axis` gains `source` and (for DCD) `warning`;
  renderer choices are `auto|vmd|matplotlib`. (`params_for`, `panel_side`, the `hbond_cutoff` parameter and the
  mdtraj/networkx/pandas probes that this round removed were **restored** in 0.8.0; see section 15.)
* **Tests:** PyMOL tests removed; more added. **Docs:** VALIDATION described validation procedures.
* **Size:** the repository shrank sharply once the legacy renders were removed.

---

### 14. Third round: repository restructure (paths in sections 1 to 13 describe the *original* layout)

`src/` layout at the repo root; role-based subpackages `inputs/ structure/ dynamics/ visual/ evidence/` (+ `bench/`);
tests mirror the package; Docker files in `docker/`; the Architecture and Methods sections of the [README](../README.md); layering enforced by
`tests/system/test_layering.py`. `probe_environment` and `select_keyframes(render=...)` moved to `vmd_agent.auto`
(still exported from `vmd_agent`). Deep imports changed; see the table in `CHANGELOG.md`.


---

### 15. Retention audit (0.8.0): was anything from the original lost?

Method: the original `vmd-agent-new/` and this repo were compared programmatically, then run side by side.

| Check | Result |
|---|---|
| Every function and class defined in the original exists here | all retained except one internal helper (`_rmsd_interp`, below) |
| Every parameter of every same-named function | 3 public parameters were lost in an earlier round and restored (below); the only other differences are private analysis helpers that now take one context object instead of `u` and `out_dir` |
| All 24 MCP tools, with the same parameters and defaults | all retained; 3 new tools; some gained optional parameters |
| All 16 CLI subcommands and every option, default and choice | all retained unchanged; new subcommands added |
| Output keys of `inspect_files`, `detect_system`, `structure_stats`, recipes, colour keys, representations, all 9 analyses, probe | all keys retained except a few that are not functionality (below) |
| VMD/Tcl recipes for several systems and both styles | compared as text; the generated Tcl was unchanged |
| The 12 representations, focus presets, colour methods, materials | identical |

**Lost in 0.7.0 and restored in 0.8.0**

| Item | What happened | Now |
|---|---|---|
| `structure_stats(hbond_cutoff=...)` | silently swallowed by a `**kwargs` catch-all | a real parameter (donor-acceptor limit, default 3.5 Å); an unknown option raises `TypeError` |
| `annotate_image(panel_side=...)` | removed as "unused" | implemented (`right` or `left`), also on the MCP tool and CLI (`--panel-side`) |
| `representations.params_for` | removed as "unused" | restored and used by `describe_representation` |
| `probe_environment` reporting mdtraj, networkx, pandas | removed | restored in `analysis_libs` |
| `pip install vmd-agent[dssp]` extra (mdtraj) | removed | restored; also in `[all]` |

**Intentionally not carried over (no functionality lost)**

* `analysis._rmsd_interp`: its one-line verdict ("Low RMSD fluctuation, structure appears stable") judged stability
  from the size of the fluctuation, which is not a convergence test. The `interpretation` key remains and now comes from
  the autocorrelation-aware assessment.
* `secondary_structure.note`: the original returned this when its DSSP backend was missing. The built-in DSSP is always
  available, so the situation cannot occur.
* The original errors for `hbonds` and `convergence` on the sample system (they now run).
* `networkx` and `pandas` as install dependencies (never imported).
* Duplicate `vmd-agent/` tree, stale root `fetch.py`, `render.dat`, `README_1.md` (section 1).

**Same function, deliberately different answer (bug fixes, not losses)**

Values differ on the same input where the original was wrong; each is documented in sections 3 to 13:
H-bond counts (the original's distance-only count overcounted; angle-based now), salt-bridge definition, bond
inference for crystal structures with sparse CONECT, `n_chains` (polymer chains, not
every chain ID), `most_flexible_residues` (the original could list one residue repeatedly), and the wording of
interpretations. The old key `n_hydrogen_bonds_geometric` is still emitted and equals `n_hydrogen_bonds`.

**Data not in this repo**

The original's example outputs (`*_run/`, `1BEB_whey_protein/`, `vmd_agent_output/`, PNG renders) remain
only in the original folder. They are results, not functionality, and are not needed to run anything.
