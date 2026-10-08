# The model benchmark

How well does a **language model** use vmd-agent's tools? This is the test to run on each model you are thinking of using, and to compare models on.
It is a different test from [the tool test set](tool-test-set.md), which runs each tool directly and asks whether the *tool* works.

```bash
vmd-agent bench models --list                                   # the tasks, by kind of functionality
vmd-agent bench models --oracle                                 # no model: do every task perfectly with the real tools, to check the benchmark itself
vmd-agent bench models --list --reference                       # every prompt, the tools that answer it and what a correct answer says
vmd-agent bench models --catalogue --pull                       # every suggested model (`vmd-agent models`), downloading the missing ones, each unloaded when done
vmd-agent bench models --model granite4.1:8b                    # one model on Ollama or any OpenAI-compatible server
vmd-agent bench models --model granite4.1:3b granite4.1:8b gemma4:e4b --repeats 3       # several, one after the other
vmd-agent bench models --model granite4.1:8b --tools core       # offer 27 tools instead of 53 (see "Does the model see all 53 at once?")
vmd-agent bench models --model granite4.1:8b --tools auto       # only the tools that fit each question; run it into the same --out-dir to see both side by side
vmd-agent bench models --model granite4.1:8b --smoke            # the small set (one or two tasks per category): the quick check after changing something
vmd-agent bench models --model m --categories trajectory decline --skip network         # a part of it
vmd-agent bench models --summarize                              # rebuild summary.md from the records so far
```

Rows in the summary are labelled with how the model was run, `model (all)`, `model (auto)`, `model (core, no guard)`, so the same model with different tool sets or without the guard sits side by side.

`--catalogue` runs the models of the suggested list one after another; without `--pull` it skips the ones the server does not have, with `--pull` it downloads them first (several GB each: 2 to 18 GB; into the private Ollama if setup chose that). A
model too big for your memory may be very slow or fail: the records say so (`error`), and a failed run is not a pass.

Options: `--base-url`, `--api-key` (for a hosted service), `--data-dir` and `--out-dir` (where things go), `--only TASK ...`, `--repeats N`, `--max-turns N`,
`--temperature T`, `--no-guard` (a raw model: no nudge to use a tool, no number check), `--skip vmd ffmpeg network`, `--force`.

## How it works

Each task is a plain-language request, asked in a **fresh conversation** and a **fresh copy** of the generated dataset (the same one as the tool test set), so what
one task writes cannot help another. The real chat loop runs with the real tools. A **program** (never another model) grades the final answer and the files the model made against
what the data was built to contain: numbers within a tolerance, words, a file read back with MDAnalysis. Records are appended to `records.jsonl` as they come, a run already
there is skipped, so you can stop and continue, add a model later, or run models served by different servers one command at a time. `summary.md` and `summary.json` are rebuilt from
the records. Nothing is stored in the repository: you run it on your models and your computer.

## The tasks

| Category | What it asks of the model | Tasks |
|---|---|---|
| `inspect` | what are these files, what is in the system, what can this computer do, what do the colours mean | 6 |
| `claims` | which of these statements are true (some are false) | 2 |
| `trajectory` | radius of gyration, RMSD and convergence, informative frames, drift, fluctuation | 5 |
| `vmd_measure` | VMD's own measurements: contacts, secondary structure, box, torsions, structure checks, superposition, capabilities | 7 |
| `files` | write some atoms and frames to a new trajectory, save one frame | 2 |
| `build` | solvated system, mutation, merge, membrane, nanotube, a NAMD input | 6 |
| `maps` | read a density map, scale it, fit a model into it, make a density | 4 |
| `render` | one image, a scene, a rotating movie, a movie of a trajectory, an exported session, a script, a labelled figure, pictures without VMD | 9 |
| `video` | read a video's properties, check them against a request, pull out stills | 3 |
| `workflows` | the whole jobs: has my run settled, an overview, list them, prepare a simulation | 4 |
| `hand_off` | a SLURM script | 1 |
| `records` | re-check recorded hashes, write a report from a session | 2 |
| `network` | search the PDB, download an entry | 2 |
| `decline` | requests that cannot or must not be done: a missing file, a path outside the folder, Tcl that is disabled, a quantity no tool measures, data that do not match | 5 |

Every prompt, the tools that answer it and **what a correct answer says** are in [the task list](model-benchmark-tasks.md); `vmd-agent bench models --list --reference` prints it, and `vmd-agent bench models --oracle` does every task perfectly with the real tools and grades that (no model), so a task that a perfect agent cannot pass shows up as a bug in the task. Tasks that need VMD, ffmpeg or the network are skipped (with the reason) when the computer lacks them, and are not counted.
A test checks that every tool is asked for by some task or excused with a reason.

## What is measured

For every run: whether the **right tool** was called and did not fail (`tool_ok`, not required for tasks that must be declined), whether the **answer and files are right** (`answer_ok`),
whether **every number in the answer came from a tool result** (`grounded`), which tools were called and how many failed, and the **wall-clock seconds**: the whole run, the time inside
the model's calls, the time inside the tools, plus the number of model calls and the tokens. A task is a **success** when the right tool was used and the answer is right; for a `decline`
task, success is saying that it cannot be done without inventing a number or running what is disabled.

The summary gives, per model: success overall with a 95% (Wilson) interval, by category, by task, the right-tool rate, the grounded rate, and mean seconds, with token totals.
With few tasks per category the intervals are wide; use `--repeats` (models vary from run to run) and do not rank models that are close.

## Reading the results fairly

* **Repeats need a temperature.** At `--temperature 0` (the default) a model usually gives the same answer to the same question every time, so `--repeats 3` is three copies of one sample, and the
  intervals, which assume independent runs, are too narrow. To see how much a model varies, use a small temperature (for example `--temperature 0.4 --repeats 3`). The same goes for comparing tool sets: at
  temperature 0 a model can pass a task with one set and fail it with another because the exact wording of the prompt changed, which says little about either set. Compare on many tasks or several samples.
* **Same conditions.** Compare models with the same `--tools`, `--temperature`, `--max-turns` and guard setting. The records say which were used.
* **What is being measured.** The model *and* the agent around it (routing, argument repair, compact results, the guard: see [Architecture](architecture.md#the-agent-and-what-surrounds-the-model)). To tell a model's
  ability from the agent's help, run the same model with `--tools all --no-guard` and with the defaults.
* **Comparing a change to the agent.** Run `--smoke` before and after into the same `--out-dir` (a change to the agent and a change to a grader are different things: the records do not say which graders
  were in force, so re-run both sides after changing a task). One run of 23 tasks cannot tell a few points apart; use `--repeats`.
* **The guard.** By default the chat's own safeguards are on (a model that answers a data question from memory is sent back once to use a tool; numbers are checked), so you measure
  the product. `--no-guard` measures the model alone.
* **A slow answer is not a wrong one.** Time includes the model server's own load and your hardware. The first call of a model also loads it into memory.
* **The graders are strict on purpose and can still be wrong.** They were checked against a real model's answers, and two were tightened because they let wrong answers through (a
  "2 protein chains" answer, and a residue count that included the ligand). If you find a task that fails a correct answer or passes a wrong one, that is a bug in the task: tell the author.
* **Do not run it with the model that wrote it.** Whatever model helped to write this benchmark should not be one of the models it is used to rank.

## Adding a task

A task is `Task(id, category, prompt, tools, grade, needs)` in [`model_tasks.py`](../src/vmd_agent/model_tasks.py): `grade(run)` receives the answer, every tool call with its result, and the
folder the model worked in, and returns `None` for a pass or a reason for a fail. Compute the truth from the dataset, not from a run.
