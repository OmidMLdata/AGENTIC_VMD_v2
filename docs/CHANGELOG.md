# Changelog

## 0.39.0: the earlier research study is removed from the product

* **Removed** (about 3,600 lines of code, 1,500 lines of tests and 1,500 lines of paper), none of it used by anything a person runs: the end-to-end automation benchmark for language-model agents
  (`bench/agent`, `vmd-agent bench agent-suite|agent-run|agent-preflight|agent-plan|agent-compare`), the grounded-interpretation study (`bench run`, `bench truth`, the questions, conditions, scorer and runner),
  the sampling and event studies (`bench sampling|events`), the rating-study instrument, the container wrapper for them (`bench docker` and the `bench*` compose services), the `anthropic` extra, and the research
  paper with its preregistration (`docs/reference/RESEARCH.md`). The Git tag `archive/research-benchmark` holds the repository as it was just before, so nothing is lost.
* **Also removed** as no longer used: the frame-selection scoring helpers that only the old study and the tests used (now `tests/keyframe_theory.py`), a leftover help string, the methods-page sections describing the removed studies, the `requires_api` test marker, and ignore rules for folders nothing writes any more.
* **Old history removed:** the changelog entries before 0.24.0 (they describe things since replaced) are condensed to a pointer, and the "changes from the first version" notes in module docstrings are rewritten to say how the code works now.
* **Kept:** `bench tools`, `bench models`, `bench dataset`, `bench validate`, `bench validate-dssp` and `bench synth` (the structure generator the tool test set is made from).

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

## Before 0.24.0

Versions 0.9 to 0.23 built the earlier shape of the project: the installer and setup, the first command-line tools, the web page with its own viewer, the model benchmark and the first agent loop. Their details describe
things that have since been replaced; they are in the Git history (`git log`), and the research benchmark and paper of that period are in the tag `archive/research-benchmark`.
