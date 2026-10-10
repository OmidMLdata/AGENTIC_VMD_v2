# Changelog

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
