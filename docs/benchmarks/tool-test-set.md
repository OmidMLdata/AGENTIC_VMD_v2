# The tool test set

A test set for **every one of the 57 [tools](../guide/tools.md)** and the workflow call: a small generated dataset whose properties are known by construction, and
one or more cases per tool that run the real tool on it and check the answer. It answers "does each tool still do what it says, on
this computer, with this VMD?" and it is the quickest way to see what your setup can and cannot do.

```bash
vmd-agent bench tools                       # write the dataset into ./tool_testset and run every case
vmd-agent bench tools --list                # the cases and what each needs, run nothing
vmd-agent bench tools --only measure_with_vmd_rgyr color_key     # chosen cases (or every case of a tool)
vmd-agent bench tools --skip network        # leave out cases that need vmd, ffmpeg or network
vmd-agent bench tools --json                # the records, for another program
vmd-agent bench dataset FOLDER              # only write the dataset files
```

Each line is `pass`, `FAIL` or `skip` (with the reason: no VMD, no ffmpeg, no network), the case, and the **wall-clock seconds the tool
took**. A case that needs something the computer lacks is skipped, never counted as passed. The command exits with 1 if any case failed.

## The dataset

Written by [`tool_dataset.py`](../../src/vmd_agent/tool_dataset.py) from NumPy, MDAnalysis and the bundled ffmpeg. Nothing is
downloaded and nothing is stored in the repository: you build it.

| File | What it is, and what it was built to have |
|---|---|
| `protein.pdb`, `design.json` | one idealised chain ([`bench/synth.py`](../../src/vmd_agent/bench/synth.py)) with a buried ligand and one disulfide; `design.json` records what was designed |
| `protein.dcd` | 20 frames: frame `i` is the structure moved 0.3 A x `i` along x, plus noise of 0.05 A per coordinate, in an 80 A cubic box. So the un-aligned RMSD after 19 frames is 5.7 A, the aligned RMSD is the noise (about 0.12 A), the radius of gyration does not change and the box never changes |
| `moved.pdb`, `target.dx` | the protein turned and shifted by known amounts, and a density map simulated from the un-moved protein: the fit must put it back |
| `blob.dx` | a Gaussian blob on a 24 x 24 x 24 grid with a known spacing and peak |
| `clip.mp4` | 24 frames of 160 x 120 pixels at 12 frames per second, from ffmpeg's own test pattern |
| `figure.png`, `scene.json` | an image and a scene description for the rendering tools |

## What a case checks

Every expectation is a fact of the construction or comes from an independent implementation run on the same files; none is a recorded
result. Examples: `detect_system` finds one chain `A` and a ligand `LIG`; `structure_stats` finds exactly the designed number of
disulfide bridges; `measure_with_vmd` radius of gyration equals MDAnalysis' on the same atoms; `measure_with_vmd` RMSD without alignment ends at the
drift that was built in; `secondary_structure` finds the helix fraction the structure was designed with, to within 10 points;
`align_structures` undoes a rigid move to under 0.01 A; `make_map` integrates to the selection's mass; `build_nanotube`'s radius
equals the analytic radius for its chirality; `fit_to_map` puts the model back within 0.5 A.

Some cases are **negative**: a wrong request must be refused, not answered with something plausible (`view_image` on a text file,
`probe_video` with the wrong size expected, `verify_provenance` on a folder with none, `run_workflow` with the wrong number of files,
`mutate_residue` on a solvated system, where the mutator plugin fails and the tool says to mutate the dry system first).

## What it does not test

The NAMD input is checked against the system it was written for, never run in NAMD; the SLURM script is checked for the resources you asked
for, never run on a cluster. The network cases (`search_pdb` and `fetch_structure`) talk to the live PDB and
need a connection. Cases that need VMD were only run with VMD 1.9.4a57 on macOS. The dataset is small and idealised: it checks that the
tools work, not that their answers are good on your real systems. For that, use your own data and the [benchmark](../reference/development.md). To test a *language model* on these tools, use the [model benchmark](model-benchmark.md).

## Adding a case

A case is `Case(id, tool, args, check, needs, after)` in [`tool_cases.py`](../../src/vmd_agent/tool_cases.py): `args` and `check`
receive the dataset's context, `check` chains `.ok()`, `.eq()`, `.near()`, `.file()`, `.fails()` and friends and returns the problems
found. Put a case after the cases whose output it uses (`after`). A test fails if any tool has no case.
