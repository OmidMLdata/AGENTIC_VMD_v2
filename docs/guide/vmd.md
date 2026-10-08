# VMD: versions, and driving it

## Which VMD version?

**Use a VMD 1.9.x release** ([download](https://www.ks.uiuc.edu/Research/vmd/); the toolkit never downloads VMD for you, because
VMD's licence requires you to accept it yourself).

* **Tested:** VMD **1.9.4a57**, macOS on Apple Silicon (run from its disk image), on 2026-10-06: the tests that need a real VMD
  passed (loading, selections agreeing with MDAnalysis, Tachyon renders, several views and frame sets in one session, movies, the
  safe-Tcl tool, the benchmark preflight, and each of the [tools that drive VMD itself](#driving-vmd-itself), whose numbers were
  compared with MDAnalysis, NumPy or SciPy where an independent implementation exists).
* **Not tested:** any other VMD version, **Linux or Windows builds** of VMD, the Docker route.
* The version is **not enforced**. It is read (`vmdinfo version`), shown by `vmd-agent doctor` and setup, recorded in every
  provenance record, and flagged when it is not a tested version or is outside 1.9.x (2.0, 1.8, a dev build), where VMD's scripting
  may behave differently. The tested list is `VMD_VERSIONS_TESTED` in `environment.py`; to add yours, run
  `pytest -rs` with VMD installed and tell the author what passed.
* VMD's own pages list 1.9.3 and 1.9.4 as of 2026-10-06; which one is the current stable release was not confirmed.

**How VMD is handled:** the toolkit finds VMD on your OS, proves it starts (and says why if not: missing `tcsh`, missing libraries,
wrong CPU), runs it headless with a timeout and a cleaned environment, and confines it to your data folder. Arbitrary Tcl exists only
if you switch it on with `VMD_AGENT_ENABLE_TCL=1`, and is not a security boundary. Without VMD everything else still works, with
simpler built-in pictures. How much of VMD is wrapped is in [below](#how-much-of-vmd-is-this).

## Driving VMD itself

**Is it a separate thing? No: these are tools of the [library](tools.md) like any other.** The ones marked "VMD" in its last column need VMD (the cryo-EM, map, NAMD and SLURM ones need not even that): no
language model, no chat, no internet. They are VMD's own `measure` commands, its plugins, system building, density maps, scenes and a hand-off to the VMD GUI, run headless and returned as
numbers. You can reach them in four ways, and every way gives the same answer:

| Way | How | Good for |
|---|---|---|
| **The command line** | `vmd-agent tool measure_with_vmd run.pdb run.dcd --kind rgyr` | scripts, batches, no AI |
| **Chat** | ask: *"Which salt bridges persist in run.dcd?"* | exploring in plain words |
| **An MCP client** | Claude Desktop / Code, after `vmd-agent mcp-config --write` | working inside an AI app |
| **Python** | `from vmd_agent.vmdkit.measure import measure` | your own analysis code |

`vmd-agent tool NAME --help` shows one tool's flags and an example. Required structure files are positional (`TOPOLOGY [TRAJECTORY]`), anything written goes to `--out`, options are `--kebab-case` flags,
a yes/no option that is on by default turns off with `--no-<name>`, and `--vmd PATH` points at a particular VMD. A scene is described in JSON (`--scene file.json`, or the JSON text itself). Results
are JSON with long lists shortened; add `--full` for everything. Every tool that runs VMD saves the Tcl it ran (`reproduce_script` in the result).

**Requirements:** a real VMD (1.9.x; see [Which VMD version?](#which-vmd-version)). Every command says plainly when there is none.
**Safety:** a caller never supplies Tcl. Each command builds its script from validated values (paths, a restricted selection language,
numbers, choices from fixed lists), runs it in headless VMD with a scrubbed environment, and parses the numbers back.

### The tools

| Command | What it does | Checked against |
|---|---|---|
| `vmd-agent tool build_system` | PDB to a solvated, neutral CHARMM36 system (psfgen, solvate, autoionize) | MDAnalysis (atoms, charge, residues) |
| `vmd-agent tool mutate_residue` | Mutate one residue of a PSF/PDB pair | MDAnalysis residue names |
| `vmd-agent tool merge_structures` | Combine two PSF/PDB systems into one | atom counts |
| `vmd-agent tool build_membrane` | Build a POPC or POPE lipid bilayer patch | MDAnalysis atoms; P-to-P thickness against the known ~38 A |
| `vmd-agent tool build_nanotube` | Build a carbon or boron-nitride nanotube | the analytic radius for the chirality |
| `vmd-agent tool probe_environment --plugins` | List the plugins of your VMD and which of them this toolkit wraps | every plugin of the installed VMD is classified |
| `vmd-agent tool check_structure` | Chirality errors, cis peptides and chain gaps (the structurecheck plugin) | a clean structure and one with residues deleted |
| `vmd-agent tool periodic_box` | Periodic box per frame: is there one, and does its volume drift | MDAnalysis box |
| `vmd-agent tool inspect_map` | What is in a density map file (dx, mrc, ccp4, cube, situs): grid, range, suggested isosurface levels | synthetic maps written to spec |
| `vmd-agent tool measure_with_vmd` | VMD's measure commands over a trajectory: radius of gyration, SASA, RMSD, RMSF, distances, g(r), clusters ... | MDAnalysis, NumPy, SciPy (KD-tree), an independent Shrake-Rupley |
| `vmd-agent tool find_interactions` | Hydrogen bonds, salt bridges or contacts, as how often each pair is present | the known K27-D52 salt bridge of ubiquitin |
| `vmd-agent tool secondary_structure` | Secondary structure of every residue in every frame (what the Timeline window shows) | the toolkit's own DSSP (Q3 agreement) |
| `vmd-agent tool backbone_torsions` | Phi/psi angles and coarse Ramachandran regions of one frame | NumPy dihedrals |
| `vmd-agent tool align_structures` | Superpose one structure on another and report the RMSD | a known rotation and translation |
| `vmd-agent tool make_map` | Make a density, occupancy, distance, mask or electrostatic-potential map | density integrates to the selection's mass |
| `vmd-agent tool convert_trajectory` | Write a trajectory in another format, or just some atoms/frames, wrapped or fitted | coordinates read back |
| `vmd-agent tool write_structure` | Write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin | atom counts |
| `vmd-agent tool render_image --scene` | Draw a scene you describe (representations, isosurfaces, camera) to a PNG | image content |
| `vmd-agent tool render_movie --spin` | A rotating-view movie of a scene | the video read back with ffmpeg (frames, size) |
| `vmd-agent tool export_session` | Write a folder you can open in your own VMD (session.tcl, inputs, checksums) | opened again in a fresh VMD from another location |
| `vmd-agent tool fit_to_map` | Cryo-EM: fit a model into a density map as a rigid body, and report the correlation before and after (NumPy, no VMD) | a model displaced by a known rotation and shift is put back within 0.5 A |
| `vmd-agent tool combine_maps` | Add, subtract, mask, smooth, threshold or normalise density maps (NumPy, no VMD; VMD's own `volutil` did not load) | NumPy and SciPy results |
| `vmd-agent tool prepare_namd` | Write a NAMD input file (CHARMM36, PME, minimise then equilibrate) for a built system | the box, atoms and parameter files match the system; **never run in NAMD** |
| `vmd-agent tool write_slurm_script` | Write a SLURM job script for a cluster (NAMD, a VMD script, or any command) | the requested resources appear in the script; **never run on a cluster** |

### One example each

```bash
vmd-agent tool build_system 1ubq.pdb --out build/ubq --padding 10
vmd-agent tool mutate_residue ubq.psf ubq.pdb P0 6 ALA --out ubq_K6A
vmd-agent tool merge_structures a.psf a.pdb b.psf b.pdb --out merged
vmd-agent tool build_membrane --out membrane --lipid POPC --x-size 80 --y-size 80
vmd-agent tool build_nanotube --out tube.pdb --n 6 --m 6 --length-nm 10
vmd-agent tool probe_environment --plugins
vmd-agent tool check_structure 1ubq.pdb
vmd-agent tool periodic_box run.pdb run.dcd --step 10
vmd-agent tool inspect_map map.mrc
vmd-agent tool measure_with_vmd run.pdb run.dcd --kind rgyr --step 10
vmd-agent tool find_interactions run.pdb run.dcd --kind salt_bridges
vmd-agent tool secondary_structure run.pdb run.dcd --step 5
vmd-agent tool backbone_torsions 1ubq.pdb
vmd-agent tool align_structures model.pdb reference.pdb --out aligned.pdb
vmd-agent tool make_map run.pdb run.dcd --out water.dx --kind occupancy --selection "water and name OH2"
vmd-agent tool convert_trajectory run.pdb run.dcd --out ca.dcd --selection "name CA" --step 5
vmd-agent tool write_structure run.pdb run.dcd --out frame10.pdb --frame 10
vmd-agent tool render_image run.pdb run.dcd --scene scene.json --out picture.png
vmd-agent tool render_movie run.pdb --spin --scene scene.json --out spin.mp4
vmd-agent tool export_session run.pdb run.dcd --scene scene.json --out session1
vmd-agent tool fit_to_map model.pdb map.mrc --resolution 6 --out fitted.pdb
vmd-agent tool combine_maps a.dx subtract --map-b b.dx --out difference.dx
vmd-agent tool prepare_namd system.psf system.pdb --out sim/equilibrate --temperature 310
vmd-agent tool write_slurm_script equilibrate.namd --kind namd --gpus 1 --modules namd/3.0 --out run.sbatch
```

A scene file (`scene.json`) is a plain description; every key is optional except `reps` or `isosurfaces`:

```json
{"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure", "material": "AOShiny"},
          {"selection": "resname ALA", "style": "Licorice", "color": "Name"}],
 "isosurfaces": [{"file": "water.dx", "isovalue": 0.3, "style": "wireframe", "color": "ColorID 3"}],
 "background": "white", "rotate": [["x", 30], ["y", -30]], "zoom": 1.0, "projection": "Orthographic",
 "ambient_occlusion": true, "shadows": true}
```

Styles: `Lines Licorice VDW CPK NewCartoon QuickSurf Surf MSMS Trace Tube Beads ...`; colours: `Name Element ResName Chain Structure Beta
Charge ... ColorID <n>`; materials: `Opaque Transparent AOShiny Glossy Glass1 ...` (`vmd-agent tool render_image --help` and
`vmd-agent tool list_representations` list them).

### Reproducibility

A VMD user's first question about any number is "can I get it in my own VMD?". Three layers answer it:

1. **Every tool that runs VMD saves the exact Tcl it ran.** The result carries `reproduce_script` (a file in `vmd_scripts/` next to your data) and
   `reproduce_with` (the command). Running it prints the same numbers as lines starting with `RESULT`. A test runs the saved script in
   plain VMD and compares.
2. **`export_session`** writes a folder: `session.tcl` (`vmd -e session.tcl` opens the scene in the GUI), `render.tcl` (headless
   Tachyon), your input files copied in so the paths are relative (the folder can be moved or sent to someone), `manifest.json` (the scene,
   the SHA-256 of every input, VMD's version) and `REPRODUCE.md`. The scene is loaded in a real VMD before the tool returns, and the result
   says how many molecules, atoms and representations it found.
3. **Provenance records** (`verify_provenance`) re-check hashes of the inputs and outputs of earlier runs.

`render_image` (with a scene) and `export_session` share one generated script, so the exported scene is what was rendered.

### How much of VMD is this?

`probe_environment --plugins` classifies every plugin of *your* VMD. The classes: **wrapped** (a tool does it), **library** (a helper other plugins
use), **gui_only** (a window with no scripting interface worth wrapping), **external_program** (needs NAMD, APBS, PROPKA, ...),
**not_wrapped** (scriptable, no tool yet) and **unclassified** (newer than the table in `vmdkit/capabilities.py`). The wrapper is therefore
not "all of VMD": the plugins that are windows or that drive another program are listed, not wrapped, and these scriptable ones are open:
coarse-graining, topotools writers (LAMMPS and GROMACS writers produced empty files in the one real test),
IR spectra, Brownian-dynamics tools, symmetry and atom typing helpers. A test fails when the
installed VMD has a plugin the table does not know, so the table cannot silently rot.

### Things that behave differently from what you might assume

* **Tested on one VMD:** 1.9.4a57, macOS Apple Silicon. Linux and Windows builds, other versions: untested.
* VMD **cannot write xtc or netcdf** (it reads them); `convert_trajectory` refuses those. Multi-frame **PDB** from VMD ends frames with a bare
  `END`; the tool rewrites it as `MODEL`/`ENDMDL` so other programs read the frames. Multi-frame **GRO** from VMD is several frames back to back;
  MDAnalysis reads only the first, VMD reads all.
* VMD's nanotube builder fails for zigzag tubes (`m = 0`: "domain error"); the tool says so up front.
* `volmap` has no frame-range option; the tool drops the frames you did not ask for and averages the rest. Mask and occupancy maps are therefore
  *fractions of frames*, not 0/1.
* SASA depends on VMD's atom radii; against an independent Shrake-Rupley with Bondi radii on heavy atoms it agrees to within about 15 %, not exactly.
* Ramachandran regions are coarse boxes, a way to find residues worth a look, not a validation score.
* Salt bridges use the oxygen-nitrogen distance criterion of the `saltbr` plugin, computed with VMD's `measure contacts`.
* The Timeline, Hydrogen Bonds and other windows are not opened; their computations are done headless.
