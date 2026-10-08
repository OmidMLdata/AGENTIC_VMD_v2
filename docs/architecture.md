# Architecture

## Design decisions

1. **Evidence, not conclusions.** The toolkit prepares and verifies evidence and says how it was obtained. The
   model interprets. Nothing here claims to have watched a video or understood a picture.
2. **VMD is optional.** It cannot be redistributed (UIUC licence), so every capability has a path without it and
   VMD is a pluggable renderer.
3. **Say what was actually done.** `bond_source`, `hbond_method`, `time_axis`, `renderer.caveats`,
   `passed: null` for unchecked expectations, `frames_visually_inspected_by_agent: false`.
4. **Fail closed.** Missing tools degrade to a structured result; unparsed claims are not guessed; too little data
   gives `insufficient_data`, never "stable".

## Layout follows the pipeline

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
  agent.py        THE AGENT: a model (any OpenAI-style server) using the tools: the loop, the guard, wall-clock, every call logged; prints nothing
  routing.py      which tools to offer a model for a question (and `offer_tools`, the way to ask for more)
  argfix.py       puts a model's unambiguous argument mistakes right, and says so
  toolhints.py    what a parameter means and its allowed values, for the model only
  chat.py         `vmd-agent chat`: the terminal front end of the agent
  ui.py           `vmd-agent ui`: the web page, a front end of the agent and of the whole jobs
  model_tasks.py  the model benchmark's tasks and graders;  model_bench.py runs them through the agent
  tool_cases.py   the tool test set (no model);  tool_dataset.py its data
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
| `inputs`, `llm_client`, `platform_info`, `settings`, `models`, `progress`, `routing`, `argfix` | nothing else in the package |
| `security` | `settings` (the saved files folder is the default sandbox) |
| `ollama_local` | `platform_info`, `settings` |
| `environment` | `platform_info`, `settings` |
| `structure` | `inputs`, `security` (to sanitise residue names from files) |
| `dynamics` | `inputs`, `structure` |
| `visual` | `inputs`, `structure`, `environment`, `security` |
| `evidence` | `inputs`, `structure`, `dynamics`, `environment`, `security` |
| `vmdkit` | `inputs`, `structure`, `visual`, `environment`, `security`, `progress` |
| `bench` | all of the above, `auto` and `llm_client` |
| `auto.py`, `cli.py`, `server.py`, `toolset.py`, `vmd_tools.py`, `vmd_cli.py`, `workflows.py`, `reporting.py`, `agent.py`, `toolhints.py`, `chat.py`, `ui.py`, `model_tasks.py`, `model_bench.py`, `tool_cases.py`, `tool_dataset.py`, `launcher.py`, `wizard.py`, `mcp_check.py`, `__init__.py` | anything: they are the only places that compose units |

`dynamics` and `visual` are siblings and never import each other, which is why rendering the chosen keyframes
(`auto.select_keyframes`) and the renderer inventory (`auto.probe_environment`) live in `auto.py`.

## The three pipelines

`fetch_and_visualize(id)`: fetch → inspect → detect → recipe → **render (chosen backend)** → annotate → package
(legend, keys, statistics, checklist, caveats, provenance).
`visualize_and_interpret(topology, trajectory)`: the same for local files.
`interpret_video(video)`: probe → decode-verify → exact-frame stills → QC → source-frame map → manifest.

## Recurring contracts

1. Every public function returns a JSON-serialisable `dict`.
2. Degrade, don't crash: missing VMD/ffmpeg/Pillow gives a structured note.
3. State the method (bond source, H-bond criterion, DSSP source, renderer, axis).
4. The agent interprets; the code prepares and verifies.

## Tests

`tests/` mirrors `src/vmd_agent/` (`inputs/ structure/ dynamics/ visual/ evidence/ bench/`) plus `surfaces/`
(the server through the real MCP SDK, CLI) and `system/` (security, environment). About 700 tests, a few minutes; `pytest -rs` runs everything.
Real data in `tests/data/`. **Nothing stands in for another program.** Tests that need a real VMD/Tachyon, ffmpeg, the MCP SDK
(Python >= 3.10), the network or a live model are marked `requires_vmd`, `requires_ffmpeg`, `requires_mcp`,
`requires_network`, `requires_api` and are **skipped, with the reason shown**, where that is missing: run `pytest -rs`
to see what did not run, and read a skip as "unverified here". Live model tests also need `VMD_AGENT_LIVE_TESTS=1`
(they spend a few cents). Full coverage needs `pip install -e ".[all]"` on Python >= 3.10 and a machine with VMD. An
independent NeRF builder validates DSSP; independent NumPy re-implementations cross-validate the analysis.

---


## The agent, and what surrounds the model

One module, [`agent.py`](../src/vmd_agent/agent.py), is where a model, the tools and the checks meet. Every front end is thin: the terminal chat prints, the web page draws,
the [model benchmark](model-benchmark.md) records and grades, and none of them chooses a tool, runs one or checks an answer. So a benchmark result describes what a person
gets, and a change to the agent shows up in the benchmark.

```
question ─► routing (auto: pick the tools that fit) ─► model ─► tool call ─► argfix (put the arguments right) ─► the real tool
               ▲                                        │  ▲                                                        │
               └── offer_tools: the model asks for more ┘  └── digest (what goes back to the model) ◄───────────────┘
answer ─► guard: a data question answered without a tool is sent back once; numbers no tool returned are flagged
```

Each part around the model can be switched off to measure the model alone (`--tools all`, `repair=False`, `--no-guard`), and each is tested without a model (a scripted server in the
chat API's wire format) and with one ([the live lane](development.md#contributing)).
