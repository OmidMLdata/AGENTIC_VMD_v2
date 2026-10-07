# Methods

*Every algorithm and threshold.*

Every algorithm, its parameters, and its known limits.

## Structure loading
`molio.load_universe` builds an MDAnalysis `Universe`. mmCIF is parsed natively: the first `_atom_site`
loop, **model 1 only**, first alternate location, auth_* identifiers preferred, CIF quoting rules respected
(`O5'`). Residues are contiguous runs of (chain, resid, resname, insertion code).

## Component detection (`detect`)
Residue-name sets for water, ions, lipids; MDAnalysis `protein`/`nucleic` keywords; the rest is
"ligand/other". **Material/inorganic** needs ≥ 50 atoms of an unambiguous element (Si, Au, Ag, Pt, Pd, Ti,
Al, Mo, W, Cr, Sn, Ge, Ga, As, B) or ≥ 500 of an element that is also common in biology (S, Fe, Zn, Cu, Ni).
Integrity checks: atom pairs closer than 0.5 Å (sampled to 40 k atoms) and residue-numbering gaps.
Limit: residue-name based; non-standard naming defeats it.

## Bonds (`stats`)
Explicit topology bonds are used only when there are ≥ 0.6 per non-ion atom. PDB files normally carry only
`CONECT` records, so fewer than that is treated as **partial** and supplemented by distance inference:
bond if `d ≤ r_cov(i) + r_cov(j) + 0.45 Å`, free monatomic ions excluded, skipped above 60 k atoms.
`bond_source` always states what happened.

## Hydrogen bonds
* **With hydrogens:** H···A ≤ 2.5 Å and D–H···A ≥ 120°, acceptor O, different residues, water excluded
  (in `stats`; the trajectory analysis lets the selection decide). Parent heavy atom = nearest within 1.3 Å.
* **Without hydrogens:** N/O heavy-atom pairs within 3.5 Å (≥ 2.2 Å), different residues. Labelled
  `distance_only` because this overestimates.

## Salt bridges, disulfides
Salt bridge: Asp OD1/OD2 or Glu OE1/OE2 within 4.0 Å of Lys NZ or Arg NH1/NH2/NE, counted per residue
pair (His excluded by default). Disulfide: Cys SG–SG within 2.5 Å.

## Secondary structure (`dssp`)
Kabsch & Sander (1983): amide H placed 1.0 Å from N opposite the preceding C=O; bond if
`0.084·332·(1/r_ON + 1/r_CH − 1/r_OH − 1/r_CN) < −0.5 kcal/mol` for CA–CA < 9 Å. n-turns (3,4,5) → G/H/I,
bridges → B/E (ladders of ≥ 2 are E), then T and S (bend > 70°). 3-state: H/G/I → helix, E/B → sheet.
The tests check it on NeRF-built ideal helix and strand structures. To compare it with PDB annotations and MDTraj on
structures of your choice, run `vmd-agent validate-dssp <PDB ids> --cache DIR`; compare with `mkdssp` yourself.

## Time series (`timeseries`)
* **Statistical inefficiency** `g = 1 + 2 Σ (1 − t/N) C(t)`, truncated at the first non-positive
  autocorrelation (Chodera et al. 2007). `N_eff = N/g`. The tests compare it with `(1+φ)/(1−φ)` for AR(1).
* `g` for the drift tests is estimated on residuals of a **Theil-Sen linear fit**, so a real trend is not
  mistaken for autocorrelation (which would collapse `N_eff` and hide the drift).
* **Drift:** Mann-Kendall on the series thinned by `g`, plus first-half vs second-half difference in
  corrected standard errors. `drifting` needs p < 0.01 **and** |z| > 3.
* **Gate:** fewer than 10 effectively independent samples → `insufficient_data`, even if the data look monotone.
* `no_detectable_drift` ≠ converged. Equilibration start = index maximising `N_eff` of the tail.
* The false-positive rate of the drift test and the coverage of the confidence interval are properties to check on
  your own data lengths; the tests simulate stationary AR(1) series for this.

## Trajectory analysis (`analysis`)
Time axis uses `ts.time` only for readers that record it (XTC, TRR, DCD, NetCDF, H5MD, TNG, GRO) and
strictly increasing; otherwise the axis is `frame index` and the result says so. RMSD: superposition
to frame 0 (MDAnalysis `RMSD`). RMSF: per-residue mean of per-atom RMSF about the average structure, on a
**copy** of the universe. **PBC:** any atom moving > ½ box between frames flags the selection as *split*
(some atoms) or *whole-wrapped* (all); `unwrap=True` makes the selection whole using bonds (guessed if
absent).

## Event-aware keyframes (`keyframes`)
Signals: RMSD to frame 0, Rg, optionally COM distance, contacts, helix %. Score at index *i* =
|mean(next *w*) − mean(previous *w*)|, `w = max(3, n/25)`; standardised by the **median/MAD of the score
distribution itself** (adapts to autocorrelation and non-Gaussian noise); max over signals; non-maximum
suppression; keep z ≥ 6. Always keep first and last; spend ≤ 70 % of the rest on change points; fill by
bisecting the largest gaps. **Uniform sampling:** an event of *L* frames at random position is hit by *k*
evenly spaced frames with probability `min(1,(L+1)(k−1)/(n−1))` (verified by simulation).
Limit: only events that move a chosen signal are detectable.

## Claim verification (`claims`)
Sentences → structured claims via templates, otherwise `unparsed` (never guessed). A matched sentence is accepted
only if **every word** is accounted for by that claim type (`_ALLOWED`); anything else is a qualifier the measurement
does not check ("near the loop", "between residues 40 and 60", "intact", "for 40 ns", a second component) and the
sentence is returned unparsed with a note. Sentences over 400 characters are refused. An audit found the earlier
parser reduced such sentences to a weaker claim ("bridge the ligand and Asp 52" → "has water") and reported them
*supported*. Verdicts:
supported / contradicted / unverifiable. "Mostly helical" = helix ≥ 30 % and larger than the sheet fraction
(coil is the remainder, not a competing class). **Ligand burial** = 1 − SASA(ligand in complex)/SASA(ligand
alone), Shrake-Rupley, probe 1.4 Å, 240 points, Bondi radii; buried if ≥ 0.5. Dynamic claims reuse the
statistics above, so a short trajectory yields `unverifiable`, not support.

## Automation benchmark (`bench/agent`)

* **Tasks** are generated from real trajectories and structures; **truth is independent of any model and of the toolkit's
  analysis code**: RMSD by an NumPy Kabsch (`bench/events.kabsch_rmsd_series`), mass-weighted Rg, centre-of-geometry
  distance, a SciPy KD-tree for residue neighbourhoods and chain interfaces, injected events (known onset) and injected
  defects (periodic-boundary shift of one segment by one box length, topology with 5 atoms removed, NaN coordinates).
* **Scoring.** Numbers: `|x - t| <= max(atol, rtol*|t|)` (RMSD 3 %, Rg/distance 2 %, elapsed time 1 %). Events: onset in
  `[start - 5, end]`; controls require `null`. Diagnosis: the exact label; for a damaged file a number counts against the
  answer. Selections: exact atom-set equality, evaluated with `periodic=False`. Keyframes: distinct, non-blank images
  inside the workspace plus one frame within 5 of the event window. Report: claim verification, any contradicted claim fails.
* **Silent error** = answered, wrong, not abstained, no data problem flagged.
* **Statistics.** Differences paired by task (repeats averaged); bootstrap resamples *clusters* (trajectory or structure).
  Intervals use `alpha`, so a Bonferroni-corrected family is `alpha = 0.05/m`.
* **Events** are rigid hinge/translation/scaling on real ping-pong-extended noise (see the next section); 120 frames,
  abrupt (10-frame) and slow (30-frame) ramps.

## Real-noise event study (`bench/events`)
Real trajectory frames extended by ping-pong reflection (preserves every real frame-to-frame step; makes the base
signal periodic with period 2(F−1)). Events: `hinge` (first half of the residues rotates about a pivot near the
rest, ramping to the stated angle), `dissociation` (last ~10 % of residues translate away, ramping to the stated
distance), `expansion` (uniform scaling about the centroid). Ramp over `length` frames, then held. Signals:
Kabsch RMSD to frame 0, mass-weighted Rg, and moving-vs-rest COM distance for hinge/dissociation. Hit = a selected
frame inside the event window. Negative control = no event. The event is synthetic by design.

## Procedural structures (`bench/synth`)
NeRF-built ideal helices (φ,ψ = −57,−47) arranged on a ring with alternating direction; antiparallel strands in a
plane with spacing/register chosen by grid search so DSSP recognises them; coil = short random-φ,ψ pieces; 2-residue
straight linkers; chains replicated with random rotations ≥ 28 Å apart; ligand = a 6-atom ring, "buried" at the
clash-free point (≥ 3 Å from protein) with the highest Shrake-Rupley burial among 80 candidates, "exposed" ≥ 12 Å
outside; disulfides = residue pairs with CB atoms 3.4 to 6.2 Å apart and SG atoms placed 2.05 Å apart.
**Idealised and not physically realistic.**

## Analysis guards
`contacts` and `distance` require `sel2` (they used to default to the selection itself, comparing it with itself).
`analyze_trajectory` estimates the memory needed (all atoms of every kept frame as float32, doubled for the transient
stack) and refuses above `VMD_AGENT_MAX_MEMORY_GB` (default 4), returning the `step` that would fit.

## Time axis
`ts.time` is trusted only for readers that record it and only when strictly increasing; for DCD it is flagged
because headers often keep a default or pre-stride timestep. `dt_ps` overrides.

## Chain counting
`n_protein_chains` / `n_nucleic_chains` count chain IDs (or segment IDs) among polymer atoms only; `n_chains_all`
includes ligand/water chain IDs.

## Benchmark statistics
See [the grounding study](RESEARCH.md#appendix-e-grounding-study-specification). Cluster bootstrap over structures (1000 resamples default); unpaired
cluster bootstrap for group gaps; difference-of-differences for the adjusted contamination estimate.

---
