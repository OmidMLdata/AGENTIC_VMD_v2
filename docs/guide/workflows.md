# Whole jobs: workflows and reports

Tools and workflows are different layers. A [tool](tools.md) does one thing; a workflow is a job above the tools. There are eleven, and the agent reaches them through one call, `run_workflow` (with no name it lists them), so they are not among the tools of the library.

A workflow is a named job that runs several [tools](tools.md) in a fixed order, the way a person would, and ends with a **verdict**, a list of
**findings** and a **report**. Nothing in it is decided by a language model: the findings come from the tools' own numbers and wording, and each is
graded **ok**, **note**, **warning** or **problem**. A step that needs VMD is skipped, and reported as skipped, when there is no VMD.

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent workflow` | list the workflows and the files each needs | none |
| `vmd-agent workflow NAME FILE ...` | run the job, collect findings, write `report.md` and `report.html` | `--out-dir DIR` · `--option KEY=VALUE` (repeat) · `--quiet` |

```bash
vmd-agent workflow                                          # the list
vmd-agent workflow equilibration_check run.psf run.dcd      # runs, shows progress, writes equilibration_check_report/
```

| Workflow | Files | What it does |
|---|---|---|
| `structure_overview` | structure | what is in it (components, bonds, disulfides, secondary structure), backbone torsions, chirality, cis peptides, chain gaps, two pictures |
| `equilibration_check` | topology, trajectory | RMSD and size with convergence tests, the periodic box over time, and the RMSD measured a second time by VMD as a cross-check (the two engines must agree to 2%) |
| `interaction_report` | topology, trajectory | hydrogen bonds and salt bridges as how often each pair is present; `--option partner="resname LIG"` adds contacts with that group and its surface area |
| `compare_runs` | topology, trajectory A, trajectory B | RMSD, radius of gyration and per-residue fluctuation side by side, with the caveat that one run each is not evidence about the systems |
| `prepare_simulation` | structure | checks the input, builds a solvated neutral CHARMM36 system, writes a NAMD input and a SLURM script; warns about everything that was left out |
| `cryoem_fit` | model, map | fits the model into the map, draws it inside the isosurface, exports a session for VMD |
| `flexibility_report` | topology, trajectory | which residues are most flexible and most rigid (fluctuation per residue), the radius of gyration, and whether the helix and strand content holds over the run (VMD's STRIDE) |
| `ligand_report` | topology, trajectory | does the ligand stay bound: its distance from the protein over time, how often it is within the cutoff, which residues touch it, and its hydrogen bonds; `--option ligand="resname XXX"` names it when it cannot be found by itself |
| `trajectory_qc` | topology, trajectory | can the trajectory be trusted: it loads with its topology, the frame count, the time step in the header, molecules split across the periodic box, the unit cell over time, the geometry of the first frame |
| `compare_structures` | structure A, structure B | superposes A onto B on `name CA` (or `--option selection=...`), reports the RMSD before and after and what each contains, and writes the superposed structure |
| `check_claims` | topology | grades each statement you give (`--option claims="A; B"`, optionally `trajectory=FILE`, or `claims_file=FILE` with one per line) as supported, contradicted or not checkable, and says what kinds of statement can be checked |

Settings go in `--option key=value`: `selection`, `partner`, `ligand`, `protein`, `cutoff`, `top`, `claims`, `claims_file`, `trajectory`, `step`, `padding`, `salt`, `temperature`, `resolution`, `renderer`.
In the chat, ask in words (*"Has my run settled? Use run.psf and run.dcd."*). When a question clearly matches a workflow (settled / equilibrated, which residues are flexible, does the ligand stay bound, can I trust this trajectory, compare runs or structures, prepare a simulation, fit into a cryo-EM map, overview), the toolkit tells the model which workflow fits and the model makes the call (`run_workflow`); it then quotes the verdict and findings and gives you the report path.

**The report** (`report.md`, and `report.html` to open in a browser) is written next to the figures, which it copies in, so the folder can be
sent to someone. It holds: the verdict and findings; a table of every step with its time and key numbers; the figures; every **caveat the
tools raised** (for example "DCD headers often hold a default timestep"); the methods (settings, the version of VMD and of this toolkit, which engine
measured what); and a reproducibility section with the **SHA-256 of every input file** and the **exact Tcl of every VMD step**, copied into
`scripts/`. A reviewer can re-run it with the one command printed at the bottom.

Each workflow was run on real data and its findings checked (the two RMSD engines agree to three decimals on the test run; the known
K27-D52 salt bridge is found; a model displaced by a known amount is put back within half an angstrom). **Not tested:** `prepare_simulation`'s NAMD
input has never been run in NAMD, and the SLURM script has never been run on a cluster; `cryoem_fit` was tested on a map simulated from
the structure itself, not on an experimental map from the EMDB.
