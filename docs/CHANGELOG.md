# Changelog

## Unreleased

**Claude as the assistant**
* **Your Claude account, no API key:** a new choice, *Claude Code on this computer* (setup choice 2, `setup --use claude`, or **Model** in the
  web page). Each question runs Claude Code (`claude -p`) with vmd-agent's MCP server as its only tools (its own shell, file and web tools
  switched off), sandboxed to the files folder and driving the same VMD window; later questions continue the conversation.
* The Model window **installs Claude Code** (Anthropic's installer, after a consent box), **signs in** with Claude's own sign-in page
  (email, Google or SSO; a code box when the page shows one), shows whether it is signed in, and lists Claude Fable 5.1, Opus 5.5, Sonnet 5.5
  and Haiku 5.5.
* Claude Code is **found wherever it was installed**: the PATH, the native installer, npm under nvm, fnm, volta, asdf, pnpm, yarn or conda,
  Homebrew, the terminal's own PATH and the Claude desktop app's copy, each confirmed with `--version`; or a path given in the Model window.
* **Claude's API with a key** works through *Another server*: the `anthropic-version` header is sent and `temperature` is left out for it.

**Setup**
* Step 3 has **five choices**: the free model here, your Claude account, an online service with an API key, Claude Code or Claude Desktop
  in that app, skip. A saved Claude Code choice is no longer taken for an online service (which then asked for an address and a key).

**The chat**
* **Finds structures on the web:** naming a molecule without a file ("visualize whey protein"), or asking to search or look online, offers
  `search_pdb` and `fetch_structure`; the model is told it can reach the PDB and AlphaFold; search results carry titles, method and resolution.
* **Plain words for VMD:** colours by name or hex, colouring methods ("CPK", "by chain"), styles ("cartoon", "sticks", "surface"),
  backgrounds and selections ("chainA", "residues 100-150", "ligand", "binding pocket") reach VMD in its own words; nothing is cleaned past
  the security checks. Placeholder arguments (`<your_topology>`) are left out, a molecule already in the window is reused, and a refused
  call says what to fix and what the window holds. A request in several parts becomes one representation per part.

**Fixes**
* HTTPS uses the operating system's certificates (`truststore`), fixing `CERTIFICATE_VERIFY_FAILED` on Macs and on networks that inspect
  secure traffic, for the model and for downloads.

## 1.0.0: first release

vmd-agent: ask questions about molecular structures and simulations in plain language and get answers worked out from real measurements, with VMD doing the measuring and drawing.

* **A tool library** of 57 tools in eleven groups (look at your files, fetch structures, draw, control a real VMD window, measure a simulation, interactions and structure quality, convert files, density maps,
  build a simulation, video, evidence and records), available to the chat, the web page, the command line (`vmd-agent tool NAME`) and MCP clients.
* **Eleven whole jobs** (`structure_overview`, `equilibration_check`, `flexibility_report`, `ligand_report`, `trajectory_qc`, `interaction_report`, `compare_runs`, `compare_structures`, `check_claims`,
  `prepare_simulation`, `cryoem_fit`) that run several tools in order, grade the findings and write a report with input checksums and the Tcl of every VMD step.
* **An agent** with routing, argument repair and checks on what an answer says (numbers, counts, residues, files, window and drawing claims, explanations, firm conclusions on thin data), and a refusal, before the
  model is asked, of what the toolkit cannot do.
* **A web page** that is a remote control for a real VMD window (opened for you), with the chat, a form for every tool, whole jobs and a terminal; a numbered menu; a terminal chat.
* **A free local model by default** (a private Ollama), with suggestions from your computer's memory and graphics card, and a way to download or change the model at any time.
* **A one-line installer** for Mac, Linux and Windows, setup that asks a few questions, an optional per-project data folder, and Docker images.
* **Benchmarks**: every tool on data with known answers, language models in front of the tools, and cross-checks of the analysis against independent code.
