# Changelog

## 0.38.0: the checks on what an answer says get stricter

* **Explanations and causes no tool measured are flagged** (mechanisms such as van der Waals or stacking, "driven by", "caused by", free energy, affinity), unless the question or a result says them. The tools measure; they do not explain.
* **Counts are typed.** "5 frames" is accepted only from a result that holds a number of frames, "6 residues" only from one about residues; a number that is merely a residue id in a list no longer passes as a count. Where no result has any value of that kind the older loose rule still applies.
* **Firm conclusions are refused when the results say the data are thin** ("too few frames", "insufficient data"): "stays bound", "is stable", "has settled", "proves" are sent back unless the sentence says it is about the frames that were seen. The real 8B model said "the ligand stays bound" from 8 frames; it is now sent back, and a scoped rewording passes.
* **A job's own verdict and grading are appended to the answer, word for word, marked as the tool's.**
* **What an answer says about colour and drawing style is checked against what the window tool reported drawing.** Found by the benchmark: the real model called `window_visualize` with `color_method='Beta'` and told the user the protein was coloured by secondary structure. The parameter now says what each colouring method means (Structure = secondary structure), the model picks it correctly, and a mismatch is flagged.
* Limits that remain: explanations phrased in ways the lists do not cover, and conclusions drawn too firmly from correct numbers where the results do not say the data are thin.

## 0.37.0: what an audit of the tools, the jobs and a new user's first run found

* **Every tool and job was run against a real VMD.** All 57 tools have a case on generated data with known answers (83 cases, all pass); all eleven jobs ran with and without `show_in_window`.
* **A job now stops before any work if a file is missing or plainly the wrong kind** (a trajectory where the topology goes, the files the wrong way round, a non-map for a map). Before, swapping the two files of `equilibration_check` still wrote a report that said "no problem found".
* **First-run crashes found by running 300 scripted new-user sessions with random answers at every prompt** (numbers in and out of range, blanks, words, odd paths): giving an existing *file* as the files folder, a folder that cannot be made, and an online-service address that is not a web address (`7`, `not a url`) each ended in a traceback. They now say what is wrong and ask again, or fall back. After the fixes, 240 further sessions produced no crash and no inconsistent saved settings.
* Stale wording from the removed imitation viewer ("the viewer, the look buttons") is gone from the page and the docs.

## 0.36.0: more exact checks on what an answer says

* **Counts, residue numbers, files and conclusions are checked against the structured results.** A count of frames, residues, atoms, bonds and so on that no result contains, a residue number no result mentions, a file that is not in your files, the question or a result, and a conclusion of "no problems" or "no warnings" over a workflow that graded some, are sent back once, then flagged. A count is accepted if the same whole number appears anywhere in the results, so a coincidence can still pass.
* Checked on real model answers: the true ligand and flexibility answers produce no flags, an invented one is caught, and six of seven real-model answers in a benchmark run raised none (the seventh failed its grade because the model, correctly, used the new `flexibility_report`: that task now accepts it).

## 0.35.0: five more whole jobs (eleven in all)

* **`flexibility_report`**: which residues are most flexible and most rigid, the size, and whether helix and strand content holds over the run.
* **`ligand_report`**: does the ligand stay bound: its distance from the protein over time, how often it is in contact, the residues that touch it, its hydrogen bonds; it warns when too few frames were analysed to say so.
* **`trajectory_qc`**: can the trajectory be trusted: loads with its topology, frame count, the header's time step, molecules split across the periodic box, the unit cell over time, first-frame geometry.
* **`compare_structures`**: two structures superposed: RMSD before and after, what each contains, the superposed structure written out.
* **`check_claims`**: each statement you give graded supported, contradicted or not checkable, with what can be checked.
* The chat is pointed at the right job for questions about flexibility, a ligand staying bound, trusting a trajectory, and comparing structures. With `show_in_window`, the flexible residues, the ligand and its contacts, or the two superposed structures are drawn (checked against a real VMD); the jobs that produce statements say there is nothing to draw.
* **The guard also checks claims that a tool or workflow was run**: an answer that says `trajectory_qc` was run when it was not is sent back. Found by a real model embellishing a ligand answer. The agent's instructions also say not to explain mechanisms no tool measured.
* Fixed a stale count in the tool page (it said 55 tools).

## 0.34.1: a first-run checklist, and a way to ask the version

* **[First-run checklist](reference/first-run-checklist.md)**: a walk-through for a person on a fresh computer (install, setup, saying no to the download and doing it later, the page, first questions, things it must refuse, removing it) and what to report.
* `vmd-agent --version`, and `vmd-agent doctor` prints the version, so a report can say which one it was.

## 0.34.0: it only says what the tools did

* **The guard checks claims, not only numbers.** An answer that says something is shown or drawn in the VMD window needs a tool that changed the window; one that says a file was written needs a tool result that names it. Otherwise the answer is sent back once, then flagged.
* **Tools report what really happened.** Presenting a result in the VMD window now says whether the window changed (`changed`), and says "nothing new was drawn" when it did not. This was the cause of a false "displayed in the VMD window" in a demo: the tool's own summary over-claimed.
* **Impossible requests are refused before the model sees them** (`limits.py`): clicking atoms with the mouse, VMD's own plugin windows, running NAMD. The agent's instructions also say what it cannot do and to say only what tools show. Three new benchmark tasks (70 in all).
* **Fixed: the web page lost the project's `.vmd-agent`.** The page's server works inside the files folder, so a project's data folder was not found any more and a second Ollama and a second set of settings were created in the per-user folder. The folder is now pinned at start-up.
* Download progress in the Model window no longer shows terminal control codes.
* **The installers run in CI** on Linux, macOS and Windows, from this commit into a throwaway folder, followed by setup, `doctor` and a tool.

## 0.33.0: a friendlier first run

* **README rewritten around installing and starting**: what you need, four install steps with the answers to give, how to start it, what to do when something goes wrong. The detail moved to pages: [How it works](guide/how-it-works.md), the model benchmark commands to [Models](guide/models.md), the repository layout to [Development](reference/development.md), and a cleaner [Install and set up](guide/install.md).
* **Setup no longer opens the VMD website by itself.** The question defaulted to yes and came back on every run. It now defaults to no, is asked once, and says how to point setup at VMD later (`vmd-agent setup --vmd PATH`). The same for Ollama's page.
* **Setup never makes a hidden data folder in your home directory**, and after the installer its default is the installer's folder (a project's `.vmd-agent` is one answer away).
* **Messages point the same way:** a missing model says `vmd-agent models --install` or the Model window, a missing VMD says `setup --vmd PATH`, and `vmd-agent ui` tells a first-time user to run setup.
* **`vmd-agent start` is labelled the Docker route** and listed under its own heading, not under Set up. Docstrings no longer say the Ollama install was never run.

## 0.32.0: models that suit this computer, and a way back after saying no

* **Suggestions from your hardware.** `vmd-agent models`, setup and the web page's Model window read the memory (and any NVIDIA card and its memory; on Apple Silicon the shared memory counts) and mark every model
  *fits*, *tight* or *too big*, name the suggested one, and show which are already downloaded (`models.advise`, `platform_info.nvidia_vram_gb`).
* **Saying no is no longer final.** Setup now asks before the model download too, with its size; a no keeps the choice and prints how to download later. `vmd-agent models --install [MODEL]` (with `--yes`) downloads at any time, setting up the
  private Ollama first if there is none; the Model window has **Download a model**, with a consent box naming the sizes, streamed progress, and a switch to the new model when it is done (`POST /api/model/install`).

## 0.31.0: the page opens VMD by itself

* **`vmd-agent ui` opens a real VMD window when the page loads**, if VMD is installed and no window is open, so the display is never empty and nobody has to find a button. Turn it off in the File menu (remembered by the browser) or start the page with `--no-vmd`.

## 0.30.3: why use it

* A new page, [Why use vmd-agent](guide/why.md), and a short section in the README: checked answers, statistics beyond VMD, repeatable steps, safe access for a model, one toolbox, a real VMD, whole jobs.

## 0.30.2: the page no longer freezes on a streaming table

* **Fixed a freeze**: when a model's answer streamed a Markdown table, the header row arrived before its separator row and the page's renderer looped forever on it (the chat stayed busy, the page stopped responding).
  A table row without its separator is now plain text until the separator arrives. Found by driving the real page in a browser; a test streams a table one character at a time.

## 0.30.1: dead code removed, models cannot be committed

* **Removed** what nothing used: the window's label commands (`label_add`, `label_clear`: the bridge now accepts 21 commands) and two helpers (`group_of` in `routing.py` and `toolset.py`) that only a test called.
* **`.gitignore`** now ignores `.vmd-agent/`, `/ollama/`, `*.gguf` and `*.safetensors` itself, besides the ignore file inside `.vmd-agent`; a test checks it.

## 0.30.0: the model and settings can be moved into the working folder

* **`vmd-agent setup --home here`** (or answering the question) offers to **move** the private Ollama with its models and the settings from the installer's or per-user folder into `.vmd-agent` in the working folder: a rename, nothing
  copied or overwritten, refused while the model server runs.
* The installer's launcher now sets `VMD_AGENT_INSTALL` (the folder holding the program) instead of `VMD_AGENT_HOME`, which an environment can still set to override everything; a working folder's `.vmd-agent` now wins over the installer's folder.

## 0.29.0: vmd-agent's own data can live in the working folder

* **`.vmd-agent` in the working folder**: settings, the VMD window link and a private Ollama with its models resolve to a `.vmd-agent` folder in the current folder or any folder above it, before the per-user folder
  (`VMD_AGENT_HOME` / `VMD_AGENT_CONFIG_DIR` still win). `vmd-agent setup` asks (or `--home here|user`), copies earlier settings, and the folder ignores itself in Git.
* **The tools cannot touch it**: every path check now refuses vmd-agent's own data folder, also when it is inside the files folder.

## 0.28.1: the Docker check and the manual follow the unified commands

* **CI**: the Docker smoke test still called the commands removed in 0.23.0 (`probe`, `visualize`); it now runs `tool probe_environment` and `tool visualize_and_interpret`. The same stale `probe` was in the
  compose file and the Docker guide.
* **Manual**: `vmd-agent validate`, `validate-dssp`, `analyze` and `claims` in the research paper are now `bench validate`, `bench validate-dssp`, `tool analyze_trajectory` and `tool verify_claims`; the page guide no
  longer says the picture is vmd-agent's own drawing; the paper counts 57 tools.
* **A test keeps it so**: every `vmd-agent NAME` (and `tool NAME`) in the manual, the CI workflow and the Docker files must be a command or tool that exists.
* Removed `extract_frames` (no caller since the video tools were merged) and a stale tool count in a comment.

## 0.28.0: what the tools find can be shown in your VMD window

* **`show_in_window`** on the tools that find something to look at (`find_interactions`, `backbone_torsions`, `check_structure`, `secondary_structure`, `select_keyframes`, `align_structures`, `fit_to_map`, `make_map`,
  `combine_maps`, `inspect_map`, the five build tools, `visualize_and_interpret`, `render_image`, `export_session`) and on `run_workflow`: the tool runs as before, then the result is drawn in the VMD window
  (`window_present.py`): the persistent salt bridges as licorice, the Ramachandran outliers in red, a fitted model inside its map, two superposed structures, a built system, the outcome of a whole job.
* **`window_visualize`** draws a system the way the recipe does, from the same representation choices (`recipes.planned_reps`, now shared by the Tcl recipe and the window), and returns the legend;
  **`window_movie`** makes a movie of the window (the trajectory, or a turntable). The library is 57 tools.
* **The chat and the page offer the tools that fit each question by default** (`--tools auto`): the 57 tools' descriptions took about 12,000 tokens of a 16,384-token context. `--tools all` remains.
* The Whole jobs tab can show the outcome in the VMD window; a benchmark has two more window tasks (the figure drawing, a turntable).

## 0.27.0: the agent drives a real VMD window, and the page stops pretending to be VMD

* **The VMD window** (`vmdlink.py`, `vmdkit/live_bridge.tcl`, `window_tools.py`): eleven `window_*` tools that start or find a VMD with its window and drive it: load, molecules, representations (any of VMD's
  styles, colours and materials), display, view, animation, queries and measurements, snapshots, whole scenes, saved states. A small bridge inside VMD (127.0.0.1, one-time token, a fixed list of 23 commands, every argument checked twice,
  nothing evaluated) takes the commands; the same tools serve the chat, the page, the command line (`vmd-agent tool window_*`, across separate commands) and an MCP client. The library is now 55 tools in eleven groups.
* **The page is a remote for that window**: its display shows VMD's own snapshots, dragging, the wheel, the molecule list, the Representations window, the animation bar, the menus and the console all send commands to
  VMD and read its state back. The canvas viewer and its JavaScript selection language, which imitated VMD, are removed (`structure/viewer.py`, `viewer.js`, `selection.js`).
* **Selections are VMD's**: an invalid selection is refused with VMD's own message instead of being accepted and drawing nothing.
* **A benchmark category for the window** (6 tasks and a decline task), graded by asking the VMD the model worked with what it holds afterwards (the representations, the frame, the display), run with a VMD with no window.
* Tests: the bridge is attacked directly (wrong token, unknown command, `eval`, `[exit]`, relative and brace paths) and the answers are compared with MDAnalysis; the window tools run in the tool test set with no window.

## 0.26.0: every tool as a form, a terminal for developers, and local models found on disk

* **A Tools tab**: every tool of the library as a form built from its own signature (`toolform.py`): drop-downs for files (by kind) and fixed choices, check boxes, number and text boxes, a box for a scene's JSON;
  results as a summary, facts, pictures and the files written, with the equivalent `vmd-agent tool ...` command. `/api/tools`, `/api/tool`.
* **A terminal in the console**: `tools`, `tool NAME ...`, `tool NAME --help`, `workflow` run the real command line in the files folder (`/api/terminal`), beside VMD's viewer commands.
* **The Model dialog lists the models downloaded on this computer** (read from the private model folder, so it works while the server is off), the model servers found answering on this computer, and choosing a local
  model starts its server.
* **Numbers in an answer are read better by the number check**: "127 906" is 127906, and hex-like words and paths no longer produce phantom numbers (`2e408...` was read as infinity).

## 0.25.0: the page is connected to the model and fails gracefully; Claude Code is a choice, not an extra

* **The web page knows what is wrong with the model** (no server, or the server lacks the model), starts the private local server for you on request or when a question is asked, lets you choose another
  model or server from the page (**Extensions, Model…**, remembered), and answers a question asked with no model with an explanation and the way out instead of an error. `/api/model`, `/api/model/start`, `/api/model/use`.
* **Setup no longer offers to register Claude Code after choosing a model that runs here.** Claude Code or Desktop is one of the choices of who answers, an alternative to a model; the menu's "Connect the tools to
  Claude" step is gone (`vmd-agent mcp-config` remains). The choices say what was found, and the free local model is offered first unless an online service is already saved; if an online service is chosen
  and none is given, setup offers the local model instead.

## 0.24.1: the web page looks like VMD's windows

* Flat grey faces, bevelled buttons, sunken white lists, small type, square corners and no accent colour: the Molecules list, a black display, Graphical Representations (Selected Atoms, Drawing Method,
  Coloring Method), a console with a `vmd >` prompt and a status bar of sunken fields. The chat is a plain transcript (You / Agent) with one line per tool call; the logo, the search button, the suggestion chips
  and the rounded cards are gone (Ctrl/⌘ K and Extensions, Search actions remain).

## 0.24.0: one tool library, workflows above it, and no second set of commands

* **One list of 44 tools, in ten groups** (`toolset.LIBRARY`). The old division into "the original 27" and "the 24 that drive VMD" is gone, and so are the `core` and `vmd` chat profiles (`--tools` is now
  `all` or `auto`). The README and `docs/guide/tools.md` list the groups, and a test keeps them equal to the code.
* **Merged tools**, so one function does one job: `vmd_capabilities` into `probe_environment(plugins=true)`; `describe_representation` into `list_representations(name=...)`; `vmd_render_scene` into
  `render_image(scene_spec=...)`; `vmd_render_turntable` into `render_movie(spin=true)`; `validate_video` into `probe_video(expect_*)`; `extract_video_frames` into `interpret_video`; `fetch_and_visualize`
  removed (`fetch_structure` then `visualize_and_interpret`); `list_workflows` into `run_workflow` (no name lists them).
* **Renamed** without the `vmd_` prefix, by what they do: `measure_with_vmd`, `find_interactions`, `secondary_structure`, `backbone_torsions`, `check_structure`, `align_structures`, `periodic_box`,
  `convert_trajectory`, `write_structure`, `make_map`, `inspect_map`, `combine_maps`, `fit_to_map`, `build_system`, `mutate_residue`, `merge_structures`, `build_membrane`, `build_nanotube`, `prepare_namd`,
  `write_slurm_script`, `export_session`, `run_tcl`.
* **Workflows are a layer above the tools**, not tools: six jobs reached through one call, `run_workflow`.
* **One way to run a tool from a terminal**: `vmd-agent tool NAME ...`, with flags generated from the tool's own parameters (`toolcli.py`). The hand-written duplicates (`probe`, `inspect`, `detect`,
  `stats`, `render`, `recipe`, `reps`, `annotate`, `fetch`, `search`, `show`, `visualize`, `analyze`, `keyframes`, `claims`, `report`, `probe-video`, `interpret-video`, `provenance`, `renderers`, and the whole
  `vmd` group) are removed. `validate` and `validate-dssp` moved under `bench`.

## 0.23.0: the web page follows VMD's interface

* **Menus, command palette and shortcuts**: File, Molecule, Graphics, Display, Mouse, Animation, Extensions and Help menus; Ctrl/⌘ K searches every action; a shortcuts sheet (`?`); keyboard-operable menus,
  splitters and dialogs; light, dark or automatic theme; resizable, remembered columns.
* **Several molecules** with VMD's ID / T / D table, and **representations** per molecule: selection, drawing method and colouring method, with VMD's selection language (`selection.js`) evaluated in the page.
* **A console that speaks VMD** (`commands.js`): `mol new|addfile|addrep|modselect|modstyle|modcolor|delrep|top|delete`, `animate ...`, `display ...`, `axes`, `rotate`, `scale`, plus `ask`, `look`, `workflow`.
* **Display**: Query-atom mode, orthographic projection, depth cueing, background colour, animation styles (loop, once, rock), nucleic acids and `Licorice`, `CPK`, `Tube` drawings.
* **Chat**: Markdown answers rendered without raw HTML (`markdown.js`), collapsible tool cards with results, copy button.

## 0.22.0: the computer decides, the benchmark checks itself, and every suggested model can be tested in one command

* **It reads the computer** (`platform_info.py`, `models.recommend`): memory on macOS, Linux and Windows, an NVIDIA card, Claude Code (installed? already registered as an MCP server?). Setup names the computer and
  suggests the model that fits its memory (the default from 16 GB or with an NVIDIA card, the small one from 8 GB, and a plain warning below that), offers to register vmd-agent with Claude Code when `claude`
  is installed, and `vmd-agent doctor` shows all of it.
* **The benchmark has correct answers** (`model_oracle.py`, `docs/model-benchmark-tasks.md`): for each of the 58 tasks, the tool calls a perfect agent makes and the answer it gives, from what the dataset was
  built to contain. `vmd-agent bench models --oracle` does every task perfectly with the real tools and grades that with the task's own grader, so a task that cannot be passed is found as a bug in the task;
  `--list --reference` prints each prompt with its expected tools and facts; the task page in the docs is generated from the code and a test keeps them equal.
* **`bench models --catalogue [--pull]`** runs every suggested model one after another (downloading missing ones into the private Ollama when asked, unloading each when done).
* **A test no longer downloads into your home folder**: the first version of a setup test reached the install step and installed the private Ollama and a model into the developer's real data folder. Tests now
  run with `VMD_AGENT_HOME` pointed at a temporary folder.

## 0.21.0: the agent is its own layer, with routing, argument repair and a test lane that uses a model

* **`agent.py`**: the language model as a tool-calling agent, separate from any screen. The loop, the guard, the wall-clock and every tool call's arguments and result live there
  (`Agent.run()` returns them as a `Result`); the terminal chat, the web page and the model benchmark are thin front ends on it, so a benchmark result describes what a person gets.
  `chat.py` is now only the terminal.
* **Routing** (`--tools auto`, `routing.py`): only the tools that fit the question are offered, plus `offer_tools` to ask for another group; a real tool the model calls that was not offered is
  allowed. It is keyword matching and misses some differently worded questions (two paraphrase sets are kept in the tests); `--tools all` remains.
* **Argument repair** (`argfix.py`): wrong types, case and punctuation of a choice, known aliases, a file name without its folder, the trajectory given as the topology, a required file left out
  when the folder has exactly one that fits: corrected, and the result carries `note_on_arguments`. Ambiguous cases are left to the tool.
* **What the model reads**: results lose bookkeeping fields (`digest`), `detect_system` and `structure_stats` begin with a plain `summary` sentence (and `structure_stats` has `n_protein_residues`:
  a model read the all-residue count as the protein's), and parameters whose names do not say what they do (`align`, `step`, `solvate`...) and choices with fixed values are described (`toolhints.py`).
  Numbers the user wrote in the question are no longer flagged as invented.
* **Grounding is enforced, not only flagged**: an answer that states a number no tool returned is sent back once (where it is not being streamed); a list of statements to be judged is pointed at
  `verify_claims`. Both were added after the benchmark showed a model estimating a binding free energy that no tool can measure, and judging a statement from the wrong field.
* **A test lane with a real model** (`tests/live`, skipped unless `VMD_AGENT_LIVE_LLM_MODEL` is set): the benchmark's small set (`bench models --smoke`) through the agent, failing below a threshold you set
  for your model, or when a request that must be declined is answered with an invented result.
* **The model benchmark**: summary rows are labelled with how the model was run (`model (all)`, `model (auto)`), so tool sets compare side by side; the claims task accepts an answer that lists only the
  true statements.

## 0.20.0: a workbench page with a molecule viewer, and a model benchmark

* **The web page is a workbench laid out like VMD's own windows**: molecules (files; the drawn one is marked T), a black display with a viewer, the assistant (chat and whole jobs), and a
  console with the seconds of every call, plus a status bar. The viewer draws a structure (and its trajectory, with a frame slider) with VMD's drawing and colour names (Trace, Lines, VDW,
  Points; Name, Chain, ResType, Resid, Index) and its default colours, rotates with the mouse, saves a PNG, and shows the figures the tools make. Served as plain files with a strict
  content-security policy (no inline script); the server sends atoms, bonds and frames from `structure/viewer.py`. The chat's tool set (all, core, vmd) can be changed from the status bar.
* **The model benchmark** (`vmd-agent bench models`): 58 plain-language tasks in 14 categories, one per kind of functionality (inspect, claims, trajectory, VMD measurements, files, building,
  maps, rendering, video, whole jobs, hand-offs, records, network, and requests that must be declined), asked of any OpenAI-compatible model in a fresh conversation and a fresh copy of the
  generated dataset, and graded by a program. Per run: right tool, right answer and files, numbers grounded, the tools called, seconds (whole, in the model, in the tools), tokens. Resumable;
  `summary.md` compares models with 95% intervals. Checked against a real model, which showed two graders were too lenient (a "2 chains" answer; 112 residues with the ligand counted); both fixed
  and tested.
* **"Does the model see all 53 tools at once?"** Answered in `docs/tools.md`: by default yes, about 8,000 tokens of descriptions with every question (`vmd-agent tools --size` measures it);
  `--tools core` and `--tools vmd` are about half. A test keeps the page's numbers true.
* The chat records every tool call (`call_log`: arguments and results), which the benchmark reads.

## 0.19.0: a README and docs, a web page, a tool test set, wall-clock times

* **README and docs.** The README is now a README (what it is, install, use, the pipeline, what is verified, links); everything else moved into `docs/`:
  install, ways to work, the command reference, models, workflows, VMD, the tools, MCP, Docker, development, architecture, methods, security, with an index.
* **`vmd-agent ui`**: the toolkit in a web page on your computer (files with drop-to-add, the chat with every tool call as a card with its progress, pictures
  and seconds, and a tab for whole jobs). Standard library only; listens on 127.0.0.1 only, with a one-time key, and reads and writes only inside your
  files folder. The installer's last words, the end of setup and the first menu item all lead to it.
* **The tool test set** (`vmd-agent bench tools`, `bench dataset`): a generated dataset whose properties are known by construction (a drifting trajectory, a
  disulfide, a ligand, a density map, a video) and at least one case for each of the 53 tools, with negative cases (a wrong request must be refused). A test
  fails if any tool has no case. It found two things: the settled-run check graded a statistically detectable 0.03 % change in the radius of gyration a
  warning (it is now a warning only above 1 %), and mutating a solvated system fails in VMD's mutator (the error now says to mutate the dry system first).
* **Wall-clock time of every execution.** Each model call and each tool call is timed: the terminal chat prints it per tool and per answer (`/time` for the
  totals), the web page shows it per card, and the benchmark's records have `model_s`, `model_calls` and `tool_s` next to `wall_s`.
* **Tool counts.** The stale "47 tools (27 plus 20)" in `docs/RESEARCH.md` and the chat help is corrected: 27 original + 24 that drive VMD + 2 whole-job tools = 53
  (`docs/tools.md`, which says who gets which tools and what the benchmark's separate arm tools are).

## 0.18.0: fewer files, one flow

* **Fewer files, nothing lost.** `start.sh` and `start.ps1` became `vmd-agent start` (and `vmd-agent start --down` stops the containers);
  `docker/bench.sh` became `vmd-agent bench docker ACTION [--mode plain|hostvmd|withvmd]` (same actions, same exit codes, the macOS-binary refusal
  is kept); the checks are plain `ruff check src tests`, `vulture` and `pytest -rs` (no helper scripts ship in the repository); `requirements.txt` and `requirements-all.txt` were removed (`pyproject.toml` is the
  one list; `pip install -e ".[all]"`). CI actions bumped to checkout v7 and setup-python v7. `install.sh` and `install.ps1` stay a pair: they run before Python exists, in two different shells.
* **One flow.** The README follows the pipeline (set up, get a structure, look, measure, run a whole job, drive VMD, check and keep records);
  `vmd-agent --help` and `vmd-agent vmd` list commands in that same order.

## 0.17.0: whole jobs, reports, progress, more of VMD

* **Workflows** (`workflows.py`, `vmd-agent workflow`): `structure_overview`, `equilibration_check`, `interaction_report`, `compare_runs`, `prepare_simulation`, `cryoem_fit`. Each runs
  several tools in a fixed order, grades findings (ok / note / warning / problem) from the tools' own numbers and wording, gives a verdict and writes a report. In the chat the toolkit
  points the model at the workflow that fits a question (a model left to itself answered "has my run settled?" with one RMSD and an invented criterion; routed, it ran the workflow).
* **Reports** (`reporting.py`): `report.md` and `report.html` with findings, step table, figures, every caveat the tools raised, methods, SHA-256 of the inputs and the exact Tcl of each VMD step.
* **Progress** (`progress.py`): long jobs say what they are doing (frames done, "adding a water box", "ray tracing 72 frames"); the commands print it to stderr, the chat shows it under the
  tool call and how long it took. **Streaming**: the chat prints answers as they are written (`--no-stream` to turn off); an answer the guard is about to send back is held, not shown.
* **More of VMD:** `vmd fit-to-map` (cryo-EM rigid-body fit, NumPy), `vmd map-arithmetic` (add, subtract, mask, smooth, threshold, normalise; replaces the VMD `volutil` binary that did not load),
  `vmd prepare-namd` (NAMD input for a built system) and `vmd slurm-script` (cluster job). 24 `vmd` commands, 53 tools. **Never run:** the NAMD input in NAMD, the SLURM script on a cluster.
* The progress, a streamed reply and the workflows were run against the real VMD and the real local model; the SSE parser is also tested against a local HTTP server speaking the format.

## 0.16.1: ready to publish

* **`scripts/publish.sh`** (replaces the old `push_to_github.sh`): starts git if needed, refuses secrets and big files, commits, creates the repository and pushes (`--no-push` to try
  it locally). Tried in a scratch copy: 151 files tracked, a planted API key and a 6 MB file were both refused, running it again did nothing.
* `publish.sh --branch NAME` publishes to a new branch that grows from the remote's `main` (never overwriting a branch), and `--skip-workflows` leaves `.github/workflows` out when the token
  lacks GitHub's `workflow` scope. Tests run it against a real local remote, with `gh` hidden so no test can reach GitHub. Test data no longer carries a collaborator's home path.
* **`.gitignore` rewritten** (root-anchored runtime folders, secrets, editor and OS files) and checked path by path with `git check-ignore`; a test keeps it that way.
* **Clean-room install tested:** the installer fed through a pipe, from a GitHub-style zip, into a folder whose path contains a space, with no existing Python: it downloaded uv and
  CPython 3.12 into that folder, installed 53 packages, `doctor`, `vmd` commands and the real MCP server (47 tools) worked, and nothing was written outside the folder.
  The tests also pass from a fresh `git clone`.
* **Fix found there:** an MCP server started by a client could not see the settings saved by `setup` (the contained folder, the VMD found, the files folder). `mcp-config` and
  `mcp-check` now pass `VMD_AGENT_HOME`, default the sandbox to the folder chosen in setup, and find VMD the same way the CLI does.
* `pyproject.toml`: lower bounds on dependencies, project URLs, classifiers, `ruff` and `vulture` settings, `dev` extra includes them.

## 0.16.0: a command line that is organised and documented

No behaviour changed; everything that worked before still works with the same flags.

* **`vmd-agent --help` is grouped** (Get started, Look at a structure, Measure a simulation, Drive VMD itself, Get structures, Videos/reports, Connect other programs,
  Advanced) instead of one flat list of 38; a test checks every command is in exactly one group.
* **`vmd-agent vmd <action>`**: the 20 tools that drive VMD are ordinary commands with ordinary flags, generated from the tools' signatures (`vmd_cli.py`): structure files are
  positional, outputs are `--out`, options are `--kebab-case` flags, `--no-<name>` turns a default-on option off, `--scene file.json` takes a scene, `--full` prints everything.
  `vmd-agent vmd` lists them; `vmd-agent vmd <action> --help` has an example. They need only VMD (no model, no chat).
* New spellings added beside the old ones: `--trajectory` (for `--traj`), `--selection` / `--selection2` (for `--sel` / `--sel2`).
* **Sweep for stale code:** removed `push_to_github.sh` (it assumed a git history that does not exist), the unused `ollama_context` setting, an unused test helper and
  stale `noqa` comments; fixed unused loop variables, a README path and leftover references to documents that were merged; CI now runs `scripts/test.py`.
  A test runs all twenty `vmd` commands from the command line against a real VMD.
* **README**: "Every command" lists all commands with their useful flags, grouped as in `--help`, plus a table of flags that mean the same everywhere. Tests check that every
  command and every flag the README names exists, and that every `vmd` command is documented with an example that parses.

## 0.15.0: run for real, with a real model; one README

First run of the installer, the private Ollama and a real chat (macOS, Apple Silicon, 2026-10-06). Everything below that is a *fix* was found by that run.

* **Ran:** `install.sh` end to end from a local copy; `vmd-agent setup` downloaded Ollama's standalone build (checksum-verified), started it on the private port
  and pulled `granite4.1:8b`; the chat called the tools. `granite4.1:3b` was also tried.
* **Fixes from the real model:**
  * Ollama's default 4096-token context silently cut off the model's instructions and tools, so it answered from memory. The private server now runs with 16384
    (`OLLAMA_CONTEXT_LENGTH`; set it in the environment to change it).
  * A data question answered without a tool is sent back once with `tool_choice=required` (`chat.NUDGE`); tool descriptions say "local file" vs "download".
  * Every number in the final answer is checked against the tool results; unreturned numbers are listed under the answer (a 3B model's invented values showed up this way).
  * Models are no longer shown `vmd_path` (they invented `/usr/local/vmd`); `null` for `first`/`last`/`step` means the default; answers are capped at 3000 tokens (an unbounded
    generation once ran for minutes).
  * No VMD tool writes over a file the same call reads (a model passed `protein.pdb` as the output prefix and destroyed the input); a trajectory that does not match its
    topology is now an error ("no frames were read"), not an empty result or a `KeyError`.
  * `vmd_capabilities` returns a short form by default (the long one made the model write for three minutes).
  * `doctor` knows about the private Ollama, shows the chat model and whether it is downloaded, and no longer nags about Docker when Docker is absent.
  * `install.sh` tested for a usable terminal (`/dev/tty` can be readable and still fail).
* **One README.** `docs/TECHNICAL`, `DEVELOPMENT`, `MCP` and `VMD` are sections of `README.md` (user guide first, a Reference part after); the paper, preregistration and comparison
  with the original project are `docs/RESEARCH.md`. CHANGELOG condensed. Layering and architecture text updated for `models`, `ollama_local`, `vmdkit`, `vmd_tools`.

## 0.14.0: a much fuller wrapper around VMD itself

* **20 new tools that run VMD** (`vmd_agent/vmdkit/`, `vmd_tools.py`): VMD's `measure` family (rgyr, sasa, center, minmax, inertia, rmsd with fit, rmsf,
  distance, angle, dihedral, contacts, hbonds, gofr, cluster); hydrogen bonds / salt bridges / contacts as persistence; secondary structure over time (STRIDE);
  backbone torsions; the structurecheck plugin; superposition; pbctools; trajectory conversion/trimming/wrapping/fitting; structure writing; `volmap` and `pmepot`
  maps plus a native reader for OpenDX/CCP4/MRC/cube/Situs; psfgen + solvate + autoionize system building; mutator; topotools merge; scene rendering with
  isosurfaces; session export; and `vmd_capabilities`, which classifies every plugin of the installed VMD (wrapped / library / GUI-only / needs another program / not wrapped).
* **Reproducibility.** Every VMD tool saves the exact Tcl it ran (`reproduce_script`); `export_vmd_session` writes a relocatable folder a VMD user opens with
  `vmd -e session.tcl` (inputs copied, SHA-256 manifest, round-trip check in a real VMD). Tests re-run the saved script and the exported folder in plain VMD.
* 47 tools in total; the original 27 are untouched (`toolset.CORE_TOOLS`). `vmd-agent chat --tools all|core|vmd` picks the menu (small models do better with fewer),
  `vmd-agent tools` lists them, `vmd-agent tool NAME '{json}'` runs one.
* Found while testing against real VMD: `volmap` has no frame range; VMD cannot write xtc/netcdf; its multi-frame PDB is not read as frames by MDAnalysis (rewritten
  with MODEL/ENDMDL); the LAMMPS/GROMACS topotools writers produced empty files; the nanotube builder cannot build zigzag (m=0) tubes; SASA *decreases* with probe radius for a compact protein (a wrong test assumption of mine).
* New tests: `tests/vmdkit/`, each VMD number checked against MDAnalysis/NumPy/SciPy where an independent implementation exists. Only run against VMD 1.9.4a57, macOS arm64.

## 0.13.1: first run against a real VMD

* Real VMD 1.9.4a57 (macOS Apple Silicon, from its disk image) is now available here. 26 of the 27 `requires_vmd` tests passed (the 27th needs ffmpeg and skipped) and a real
  Tachyon render was inspected by eye. `VMD_VERSIONS_TESTED` now lists it; the README says Linux/Windows builds, other versions,
  ffmpeg and Docker remain untested. Dead-code sweep: nothing removed (every flagged name is a registered tool or is used by a test or a documented analysis).
* **ffmpeg is now part of the install.** `imageio-ffmpeg` is a core dependency (a bundled ffmpeg inside the same private environment);
  `environment.find_ffmpeg` prefers a system one, else the bundled one, and every movie/video path uses it. The bundled build has no
  ffprobe, so video probing and exact frame counts fall back to reading `ffmpeg -i` output (tested on a real H.264 video). The movie
  tests that were skipped for lack of ffmpeg now run, with real VMD.
* **Cleanup.** Removed the duplicate key `n_hydrogen_bonds_geometric` and a redundant alias; abstract bases (`Renderer`, `_Scripted`) are real
  ABCs, not `NotImplementedError` stubs; `dssp_vs_mdtraj` and `scoring.paired_arms` (documented in the study plan but unreachable) now have CLI
  entry points (`validate-dssp --mdtraj`, `bench agent-compare`). README rewritten for a non-programmer; developer, MCP and benchmark material folded into one README (the paper, preregistration and comparison with the original are `docs/RESEARCH.md`); a test checks that every Markdown link resolves.
* `scripts/test.py`: one command (`python scripts/test.py`) that runs lint, dead-code check and the whole suite, with every skip reason listed; works on every OS.

## 0.13.0: contained install, checked model list, VMD self-test

* **Everything in one folder.** The installers put uv, Python, vmd-agent, its settings and (optionally) Ollama with its models under
  one folder (`~/vmd-agent`, or `$VMD_AGENT_HOME`) by pointing uv's own variables there; no sudo, no PATH or shell-file edits,
  uninstall = delete the folder. A launcher `bin/vmd-agent` sets the folder. New `settings.home_dir`, `ollama_mode`, `ollama_port`.
* **Private Ollama (`ollama_local.py`).** Downloads Ollama's standalone archive for this OS and CPU into the folder, refuses to
  install it unless its SHA-256 matches the release's `sha256sum.txt`, refuses archive paths that escape, runs it on a private port
  with `OLLAMA_MODELS` inside the folder. The brew / winget / `curl | sh` installs are gone (the Linux one needed sudo).
  **Never run**: no Ollama binary was downloaded where this was written.
* **Checked model list (`models.py`).** Replaced the `qwen2.5` suggestions (and an unverified `qwen2.5:14b`) with models checked on
  2026-10-06 against the Ollama registry (existence, size, licence) and library pages (tool-calling badge). `vmd-agent models
  [--check]` and the setup re-check the registry before downloading. The README leads with the dated table. None was run with this
  toolkit.
* **VMD self-test.** `environment.vmd_self_test` starts VMD headless and runs a one-line script; `doctor` and setup step 1 report
  working or failing with the likely cause (tcsh, shared libraries, permissions, wrong CPU).
* **VMD version policy.** The version is read and recorded but was never checked or stated. Now: README section "Which VMD version?",
  `environment.vmd_version_note` (shown by `doctor` and setup), an empty `VMD_VERSIONS_TESTED` that grows only after the real-VMD tests pass.
* Tests: `tests/system/test_contained.py` (real archives, a real local HTTP server, the live registry under `requires_network`).

## 0.12.0: install in one line, set up by answering questions

For someone who knows VMD but not code, Git, Docker or AI apps.

* **One-line installers** (`install.sh` for Mac/Linux, `install.ps1` for Windows): install `uv` (its official installer), then vmd-agent
  from GitHub's zip (no Git needed) into a private folder, then start the setup. No administrator rights. **Never run.**
* **`vmd-agent setup`** (guided, plain words): finds VMD (or asks where it is), makes a files folder, and sets up who answers
  (a free local model through Ollama with a choice of sizes, an online OpenAI-compatible service, Claude Desktop/Code, or none).
  Installs nothing without asking and prints the exact command first. `--yes`, `--check`, `--use`, `--model`, `--data-dir`, `--vmd` for scripts.
* **A friendly menu**: plain `vmd-agent` opens it (chat, look at a structure, analyse a simulation, check a statement, connect Claude,
  check settings), runs the real commands, and never shows a traceback.
* **`settings.py`**: the answers are remembered (per-OS location, private file) and used as defaults everywhere: the chat's model, VMD for
  every renderer and the MCP server, and the files folder as the **default sandbox** for the chat and the MCP server.
* Plain-language `--help` for every command with examples, and README rewritten for a non-technical newcomer (install, what can I do,
  options per feature, troubleshooting, update/uninstall). `requirements.txt` and `requirements-all.txt` for people who manage packages themselves.
* Tests drive the setup and menu with typed answers and run the real tools; the installers are checked statically only.

## 0.11.0: OS-aware

The code now works out what kind of computer it is on and runs accordingly.

* **`platform_info.py`**: OS, CPU, WSL, container, Docker (installed / running / Compose / NVIDIA runtime), NVIDIA GPU, Ollama; per-OS
  VMD locations and file names; Claude Desktop config path; Docker platform; plain-language advice per OS. Never raises.
* **`vmd-agent start`**: detects the machine and picks native or Docker (`--print-plan` shows the decision and commands without running).
  **`vmd-agent doctor`** reports the machine and next steps. **`vmd-agent mcp-config`** prints the MCP client config for this OS with VMD
  filled in, and `--write` merges it into Claude Desktop's config (with a backup; refuses a broken file).
* **Windows defects fixed** (found by auditing the code for OS assumptions; the Windows fixes are tested as rules, never run on Windows):
  every path was refused for VMD scripts because backslashes were rejected (now converted to forward slashes on Windows); the VMD version
  check used the stdin device file (not on Windows); VMD was never found (no `vmd.exe`, no Windows install folders); the sandbox compared paths
  case-sensitively; child processes lost the Windows system variables; a console that cannot show a character (an angstrom sign) could crash
  printing. Fonts now come from matplotlib on every OS. `.gitattributes` keeps shell scripts LF on Windows checkouts.
* Verified on macOS only.

## 0.10.0: no AI client required

The toolkit now stands on its own: a local open-source model (or a hosted one) can use the tools directly.

* **`vmd-agent chat`**: an interactive or one-shot chat in which any OpenAI-compatible model (Ollama, llama.cpp, vLLM, LM Studio,
  hosted services) calls the toolkit's tools. Confined to a data folder by default; raw Tcl stays disabled; a model that
  misuses a tool is told how to call it; long histories are trimmed. No MCP client needed.
* **`toolset.py`**: the 27 tools as plain functions with generated JSON schemas, independent of MCP. `server.py` is now a thin
  registration layer over it (the MCP server is unchanged for clients, and still tested against the real SDK, both generations).
* **`llm_client.py`**: a stdlib client for the OpenAI-style API with tool calling; also accepts tool calls that a model writes
  as JSON text, only for known tool names.
* **One-script start:** `start.sh` / `start.ps1` + `docker/chat.compose.yml` (+ `chat.gpu.yml`): Docker starts a local model
  server and the chat; VMD is optional (Linux tarball you supply). **Never run** (no Docker, model server or VMD available);
  the model quality is unknown.
* **Benchmark for open models:** `--model openai:<id> --base-url ...` runs the automation benchmark on any OpenAI-compatible
  model (`OpenAICompatAgent`); preflight checks the model server.
* Live tests for a real local model are opt-in (`requires_llm`, `VMD_AGENT_LIVE_LLM_MODEL`) and have not been run.

## 0.9.4 and earlier (condensed)

* **0.9.x:** MCP on Linux checked end to end with the real MCP SDK; every recorded result removed from the repository (instructions only);
  fake VMD/Tachyon/ffmpeg and mocked network removed (tests that need the real thing are marked `requires_*` and skip with a reason);
  bring-your-own-VMD benchmark runs.
* **0.8.x:** the automation benchmark (task families with answers known by construction, tool arms, silent-error metric, cluster
  bootstrap); a retention audit showed no function of the original project was lost.
* **0.7.x:** adversarial audits (path sandbox, input validation, hypothesis property tests), repository restructure into
  `inputs / structure / dynamics / visual / evidence / bench`, event-aware keyframes, claim verification, validation procedures.
* **0.6.0:** the consolidated starting point of this copy of the original project (see the comparison in `docs/RESEARCH.md`, Part III).

