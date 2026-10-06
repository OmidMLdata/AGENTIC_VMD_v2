# Preregistration (DRAFT): LLM agents automating VMD-style molecular analysis

**Status: draft, not registered.** No language model has been run on the benchmark. This becomes a
preregistration only when you fill the `TODO` fields, commit it, and deposit a copy (OSF or AsPredicted) **before the
first real-model run**. After that, changes are listed as deviations. The scripted baselines in
[the automation benchmark](PAPER.md#5-the-automation-benchmark) are harness checks and are not data for these hypotheses.

Operational rules:
* **The model that wrote this benchmark does not run it or analyse its results.**
* **Freeze the toolkit** (git hash `TODO`) before the confirmatory run. The toolkit was changed after seeing the
  benchmark during development (the NaN-frame fix); the confirmatory run must not see further tuning.
* **Use held-out suites.** Development used seeds 0 to 9. The confirmatory suite uses seed `TODO` (≥ 100) on
  trajectories and structures that were not used to develop tasks or the toolkit. **Deposit the generated suite
  directory itself** (files and their SHA-256 hashes, which the runner checks): a seed alone does not reproduce the
  synthetic structures across machines, because floating-point differences between NumPy builds flip discrete choices.

## 1. Question

When an LLM agent is asked to carry out molecular-visualization and trajectory-analysis tasks, how often is it correct,
how often is it wrong **without any warning**, and does the choice of tooling change this?

## 2. Design

* **Models:** at least 3, from different vendors/families: `TODO` (IDs and snapshot dates). Temperature `TODO`
  (suggest 0), `max_tokens`, `max_turns` (suggest 30). Analysed per model; no pooling unless a pooled model is added here.
* **Arms (tools):** `python_mdanalysis`, `vmd_agent`, `vmd_agent_no_verify`, `vmd_agent_no_keyframes`; `vmd_plain`
  only if real VMD is installed and verified (`TODO`: yes/no).
* **Tasks:** the six families in `PAPER.md#5-the-automation-benchmark`; real trajectories `TODO` (≥ 10 distinct), real structures
  `TODO` (≥ 30), synthetic structures `TODO`, chosen **before running** by this rule: `TODO` (e.g. random draw with a
  fixed seed from a stated pool).
* **Repeats:** 3 per (task, arm).
* **Isolation:** every run in a fresh workspace copy; model-written code runs only inside a container/VM.
* **Cost:** estimate from `bench agent-plan` with the real prices: `TODO`.

## 3. Confirmatory hypotheses

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

## 4. Secondary and exploratory (labelled as such; no multiplicity claims)

* **Ablations:** `vmd_agent` − `vmd_agent_no_keyframes` on `event` and `keyframes`; `vmd_agent` −
  `vmd_agent_no_verify` on `report` (**circular**: the verifier is also the scorer, so this is exploratory only).
* Per family, per model; false-alarm rate on event-free controls; abstention; calibration of stated confidence;
  tool calls, tokens, wall time and cost per solved task.
* `vmd_plain` against `python_mdanalysis` if available.
* Whether success differs on tasks the scripted reference agent could not solve with the toolkit (known gaps:
  centre-of-geometry distance, slow transitions).

## 5. Sample size

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

## 6. Analysis plan

1. Fixed exclusions: tasks whose workspace failed to build are listed and dropped for all arms; an agent crash or a
   missing submission counts as a failure (not a silent error) and is reported.
2. Contrasts in §3 with `n_boot = 10000`, seed `TODO`.
3. Report effect sizes with intervals for all contrasts, all models, including those that disagree.
4. Sensitivity: micro versus family-balanced averaging; without the `report` family; real structures only;
   excluding the two known toolkit-gap task kinds.
5. Deviations from this document are listed with reasons.

## 7. Threats, stated up front

* **Author conflict of interest** and tool-tuning: see the rules above. Prefer the framing "a benchmark with the
  toolkit as one entrant" over "the toolkit wins".
* **Synthetic events and idealised synthetic structures:** realism of conformational change is untested; one protein
  family unless more data is added.
* **Prompt and tool-description sensitivity:** one system prompt, identical across arms; tool descriptions differ by
  nature. A prompt-variation arm is an extension, not part of this registration.
* **Scorer limits:** tolerances and the "event window" are choices (constants in `bench/agent/`); report sensitivity.
* **Execution safety:** model-written code is not sandboxed by the benchmark.
* **Model drift:** record dates and snapshots.

## 8. Fields to fill before registering

`TODO` markers above (models, toolkit hash, seed, trajectory/structure sets and selection rule, temperature, budget,
bootstrap seed, whether `vmd_plain` is included). Then: commit, tag (`git tag prereg-v1`), deposit, and only then run.

---

## Appendix: grounding study (draft)

*A separate, narrower preregistration for the component study (Q7 and Q8 in [PAPER.md](PAPER.md#appendix-d-research-questions-in-detail)).
Register it separately if you run that study.*

**Status: draft, not yet registered.** Nothing here has been tested on a real model. It only becomes a
preregistration when you (1) fill the `TODO` fields, (2) commit it, and (3) ideally deposit a copy on OSF or
AsPredicted *before* any real-model run. Edit it freely until then; after the first real call, changes must be
listed as deviations. The offline baselines in `docs/PAPER.md#appendix-e-grounding-study-specification` are harness checks and are not data for these
hypotheses.

Operational rule: **the model that wrote this benchmark does not run it or analyse its results.**

### 1. Question

Given a molecular rendering, does adding structured grounding (legend tying colours to detected components,
colour key, measured statistics) change how accurately, how honestly (abstention) and how well-calibrated a
vision-language model (VLM) answers factual questions about the structure?

### 2. Hypotheses (confirmatory)

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

### 3. Secondary and exploratory (labelled as such in the paper; no multiplicity claims)

* **Trap:** accuracy and hallucination under `misleading_legend` vs `raw` (do models follow text over pixels?).
* **Calibration:** ECE and Brier per condition.
* **Abstention:** appropriate vs over-abstention per condition (`scorer` definitions).
* **Memorisation:** real-vs-synthetic gap and the difference-of-differences estimate
  `contamination_estimate` (adjusted by `text_only`); raw and adjusted reported together.
* **Renderer dependence:** repeat on VMD renders if available; report both.
* Per-question-type results, per model. Nothing here is used to decide the main conclusion.

### 4. Design

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

### 5. Sample size

The effect and the per-structure spread of the paired difference are **assumptions you must state here**: effect
`TODO`, SD of the difference `TODO`, structures `TODO`, power target `TODO`. Compute the power with the same snippet as
in section 5 above (use `n_clusters` = number of structures). Re-estimate the SD from a **small pilot on structures
that are then excluded from the confirmatory set** (suggest 10) and update this section before the confirmatory run.
If the result is a null, report it as "no effect larger than the CI bounds", not as "no effect".

### 6. Analysis plan

1. Exclusions, fixed now: structures whose
   ground truth failed (`truth.ok` false) are excluded and listed.
2. Compute the contrasts in §2 with `paired_difference(..., n_boot=10000, seed=TODO)` on real and synthetic
   structures pooled; the real-versus-synthetic split is a secondary analysis.
3. Report effect sizes with CIs for every contrast, all models, including those that disagree.
4. Sensitivity (reported, not used to pick a conclusion): alternative thresholds for "buried" and "mixed" fold
   (constants in `bench/truth.py`); excluding `has_lipid` (nearly always false, so easy by default); real
   structures only.
5. **Deviations** from this document are listed in the paper with reasons.

### 7. Known threats, stated up front

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

### 8. Fields to fill before registering

`TODO` markers above: model IDs, structure list and selection rule, synthetic seed, temperature, budget,
bootstrap seed, git hash. Then: commit, tag (`git tag prereg-v1`), deposit a copy, and only then run.
