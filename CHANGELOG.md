# Changelog

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

