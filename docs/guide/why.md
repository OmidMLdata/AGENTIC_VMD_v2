# Why use vmd-agent

vmd-agent sits on top of VMD and your analysis libraries. Here is what that gives you that a plain VMD session, or a handful of your own scripts, does not.

## Answers you can check

* **Every number comes from a tool.** The model chooses tools and reads their results; it does not compute. A data question answered without a tool is sent back, and a number that no tool returned is sent back once and then flagged.
* **Statements get verdicts.** Give it a sentence about your system ("76 residues, and the radius of gyration stays below 13 Å") and `verify_claims` returns supported, contradicted or "cannot tell", with the evidence behind each part.
* **Two engines, compared.** Where it matters, a measurement is made twice, once by the toolkit and once by VMD itself, and the report says whether they agree.

## Statistics VMD does not give you

`analyze_trajectory` goes beyond a number or a plot: RMSD, RMSF, radius of gyration, contacts, hydrogen bonds, distances, surface area and density, with convergence tests (effective sample size, trend, first half against second half). Its verdicts are worded carefully: "no drift detected" is not "converged", and the result says so.
`select_keyframes` picks the frames where something changes rather than every n-th frame.

## Everything can be repeated

* Every tool that runs VMD saves the exact Tcl it used, so you can open the same steps in your own VMD.
* A whole-job report records the SHA-256 of each input file, the methods, every caveat the tools raised, and the Tcl of every VMD step. `verify_provenance` re-checks those hashes later.
* `export_session` writes a folder you can open in VMD and keep working in.

## A safe way to let a model near VMD

If you want an assistant to operate VMD, the usual shortcut is raw Tcl and a shell. Here the model gets a fixed, validated set of commands instead:

* it reads and writes only inside your files folder, and cannot touch vmd-agent's own settings;
* the link to the VMD window listens on your own computer only, needs a one-time token, accepts 21 fixed commands, and has none that runs Tcl, runs a program or reads a file;
* scripts are built from checked values and run headless with a cleaned environment and a time limit; the free-form Tcl tool is off unless you switch it on.

## Everything VMD can do, in one place

Fifty-seven tools in eleven groups sit behind one interface. They cover the steps between the interesting parts: fetching a structure, converting a trajectory, building a solvated and neutral CHARMM36 system, mutating a residue, adding a membrane or a nanotube, fitting a model into a cryo-EM map, writing NAMD and SLURM files, reading a video's real metadata. [The list](tools.md).

You can reach all of them from:

* the **web page**, which is a remote control for a real VMD window, with a form for every tool;
* the **chat**, in plain language, with a local open-source model by default so nothing leaves your computer;
* the **command line**, with no model at all, for scripts and batches;
* **Claude Code or Claude Desktop**, through MCP.

## Whole jobs, with a report

Six workflows run several tools in a fixed order, grade what they find (ok, note, warning, problem), give a verdict and write `report.md` and `report.html`: has this run settled, what is in this structure, which interactions persist, how do two runs compare, prepare a simulation, fit a model into a map. They bundle good practice, so a routine check is one request and the report can be sent on as it is. [Whole jobs](workflows.md).

## A real VMD, not an imitation

The agent drives the VMD window you can see. Every picture and number is VMD's own. A result can be drawn straight into that window (`show_in_window`), and the page lets you rotate, zoom, change representations and step through frames while you talk to the agent. [Your VMD window](window.md).

## Who it suits

* **People new to VMD or to trajectory analysis**, who can ask in plain words and get a checked answer with the method shown.
* **Labs that want routine checks done the same way every time**, with a report that records what was done and on which files.
* **Anyone who wants an assistant to work with VMD under clear limits**, rather than with free access to a shell.

Pick the model for your own computer with the [model benchmark](../benchmarks/model-benchmark.md), and see [Install and set up](install.md) to begin.
