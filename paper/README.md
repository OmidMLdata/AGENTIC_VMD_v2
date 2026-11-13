# Data and scripts for the VMD-Agent paper

This folder holds what the manuscript *VMD-Agent: a tool-grounded agent for molecular visualization and analysis* reports: the records of the
three-model benchmark, the audit of every failed run, the scripts that ran and analysed it, the manual VMD scripts used for the comparison with
VMD-Agent's tools, and the source data of the figures. Nothing here is needed to use vmd-agent.

## The model benchmark (`benchmark/`)

70 tasks x 3 tries x 3 models = 630 runs, made on 8 November 2026 on an Apple M1 MacBook Pro (16 GB, macOS 26.1) with VMD 1.9.4a57 (arm64).
Claude Opus 5.5 was reached through Anthropic's API; Granite 4.1 8B (`granite4.1:8b`, Q4_K_M) and Gemma 4 E4B (`gemma4:e4b`) ran locally under
Ollama 0.40.15 at temperature 0. All models used `--tools auto`, the guard and at most 12 rounds of tool calls.

| File | What it is |
|---|---|
| `records.jsonl` | One line per run, as the benchmark driver wrote it (original grading): the answer, every tool call with its arguments and the first 4,000 characters of its result, token counts and times. File paths in it are those of the benchmark computer. |
| `records_regraded.jsonl` | The same runs after the audit: `success` with the corrected text graders, `invalid` for the two tasks no model could do, and the original values kept as `success_original`, `reason_original` and `grounded_original`. |
| `summary.md`, `summary.json` | The driver's own summary of the run (original grading). |
| `manifest_full.json`, `manifest_full_part1.json` | Run manifests: code commit, Python, VMD and Ollama versions, model weight digests, quantization and the settings held fixed. |
| `grader_audit_full_run.csv` | Each of the 152 failed runs with its classification (genuine model error, borderline, grader misjudged, task invalid) and a note. |
| `results/` | The numbers in the paper: success and intervals (`benchmark_metrics.csv`), paired comparisons (`benchmark_paired.csv`), success by category and by task, the sensitivity analyses and token throughput. |
| `scripts/` | `run_benchmark.py` (the driver), `regrade_records.py` (the audit's re-grading, offline) and `analyze_benchmark.py` (statistics and the figure). |

**Which code ran.** All runs used the code of commit 7fabd29. The open-model runs and Claude's first 49 runs used it as uncommitted changes on top of
commit 1ba5237; Claude's account then ran out of prepaid API credit (those requests were refused by the server, not graded, and repeated later), and
the remaining 161 Claude runs used the committed version. The two manifests here are from those later restarts; the run log records the first part.
The corrected graders are part of vmd-agent from version 1.1.0.

**Reproduce the paper's numbers** from the records, without asking any model again (from the repository root, with vmd-agent 1.1.0 or later installed):

```bash
python paper/benchmark/scripts/regrade_records.py paper/benchmark/records.jsonl regraded
cp paper/benchmark/manifest_full.json regraded/primary/
python paper/benchmark/scripts/analyze_benchmark.py regraded/primary
```

`regraded/primary/analysis/metrics.csv` then gives 100%, 87.3% and 52.0% success for Claude Opus 5.5, Gemma 4 E4B and Granite 4.1 8B on the 68
valid tasks, and `regraded/all_tasks` holds all 70.

**Run it again** on your own models: `vmd-agent bench models --model NAME` (see [the benchmark page](../docs/benchmarks/model-benchmark.md)), or
the driver used here, from the repository root: `python paper/benchmark/scripts/run_benchmark.py --help`.

## Manual VMD against VMD-Agent (`manual_comparison/`)

| File | What it is |
|---|---|
| `scripts/manual.tcl` | Careful manual VMD on the 50-frame test trajectory (`tests/data/ubq_md/protein.pdb`, `protein.dcd`): drops the PDB's own frame, measures radius of gyration, SASA, hydrogen bonds and backbone phi/psi, then superposes every frame on frame 0 and measures C-alpha RMSD and RMSF. Writes `manual_out.txt`. |
| `scripts/naive.tcl` | The same with common slips (PDB coordinates kept as frame 0, RMSF before fitting, and so on). Writes `naive_out.txt`. |
| `scripts/careful_raw.tcl` | Careful C-alpha RMSD and RMSF on the 20 ns production run (`structure.psf`, `prod.dcd`). Writes `careful_raw.txt`. |
| `scripts/naive_raw.tcl` | The same without superposition. Writes `naive_raw.txt`. |
| `table1_tool_vs_manual.csv` | Largest difference between VMD-Agent's tools and the careful scripts (Table 1 of the paper). |
| `raw_run_manual_vs_agent.csv` | Mean and maximum RMSD and RMSF on the 20 ns run: VMD-Agent, careful and naive manual VMD. |
| `test_set_manual_slips.csv` | Size of each slip on the 50-frame set. |

Run a script in VMD's text mode from the folder that holds its input files, for example `vmd -dispdev text -e manual.tcl`. The 50-frame test
trajectory is in `tests/data/ubq_md/`; the 20 ns production trajectory (about 0.4 GB) is not part of the repository. The scripts were drafted with
the help of an AI assistant to follow common VMD practice; VMD-Agent's values came from calling its tools directly, without a language model.

## Figure source data (`figure_source_data/`)

`fig3a_rmsd_time_series.csv`, `fig3b_rmsf_per_residue.csv` and `fig3c_manual_slips.csv` for Fig. 3; `fig4a`-`fig4e_benchmark.csv` for the
panels of Fig. 4. Supplementary Fig. 1 uses `benchmark/results/benchmark_per_task.csv`, and Supplementary Fig. 2 uses the times and token counts in
`benchmark/records_regraded.jsonl`.

## A note on fairness

Claude, the model family that scored highest, helped to build vmd-agent, the benchmark and the analysis, and Claude Opus 5.5 is one of the models
compared. The graders are programs, every failed run was audited and no grading error favoured Claude, but tasks written with one model family may
suit its habits. The records are here so that the result can be checked, and the benchmark can be run on any model.
