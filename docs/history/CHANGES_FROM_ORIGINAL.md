# Every difference between v2 and the original

**Original:** `~/Desktop/AGENTIC_VMD (Sri)` (untouched; no file in it was modified).
**This copy:** `~/Desktop/AGENTIC_VMD_v2`.
The "original package" below means `vmd-agent-new/` (the editable install that actually ran).
Line counts were measured with `diff`/`wc`, not estimated.

## 0. Size at a glance

| | Original | v2 |
|---|---|---|
| Package code | 17 flat modules | subpackages that follow the pipeline (inputs, structure, dynamics, visual, evidence, bench) plus composing modules |
| Tests | 1 script with **no assertions** (collected nothing) | a test suite mirroring the package (`pytest -rs`) |
| MCP tools | 24 (README said 12, then listed 15) | 27 |
| Docs | README, ARCHITECTURE (+ duplicate READMEs) | README, PAPER, TECHNICAL, PREREGISTRATION, CHANGELOG, NOTICE, this file |
| Packaging/CI | none | Dockerfile, compose, CI, LICENSE, .gitignore |

---

## 1. Repository structure

| Change | Detail |
|---|---|
| **Removed** `vmd-agent/` | Its source was byte-identical to `vmd-agent-new/`; only the README differed |
| **Removed** root `fetch.py` | Stale third copy; still had the hard-coded AlphaFold versions (4, 3, 2) that the package version had already fixed |
| **Removed** `render.dat` | Stray Tachyon scene file from an old recipe |
| **Removed** `README_1.md` | Duplicate of an older README |
| **Removed** `vmd_agent.egg-info/` | Generated artefact |
| **Renamed** `vmd-agent-new/` → `vmd-agent/` | Single package |
| **Removed from v2** all `*_run/`, `1BEB_whey_protein/`, `vmd_agent_output/` (a large set of PNG renders) | Still in the original folder. The real ubiquitin MD (`protein.pdb/.dcd`) is kept as `tests/data/ubq_md/` |
| **Added** root `README.md`, `LICENSE`, `NOTICE.md`, `CHANGELOG.md`, `.gitignore`, `.github/workflows/ci.yml` | |
| **Removed** `tests/test_fetch_offline.py` | Replaced by real assertions in `tests/test_fetch_media_report.py` |
| **Added** `tests/data/` | 4 real PDBs (1ubq, 1lyz, 4hhb, 1beb) |

## 2. Modules unchanged

`annotate.py`, `inspection.py`, `representations.py`: 0 lines differ.

## 3. Modules modified (lines added / removed)

| Module | +/− | What changed |
|---|---|---|
| `analysis.py` | +399 / −147 | Rewritten. Honest time axis (`time (ps)` only for readers that record time, else `frame index`); verdicts from `timeseries` instead of fixed thresholds; per-residue RMSF on a **copy** of the universe; angle-based H-bonds (own implementation replaces MDAnalysis `HydrogenBondAnalysis`, which needs charges); contacts report atom and residue-pair counts and fraction of frames in contact; SASA scratch dir cleaned; `convergence` analysis; PBC diagnostics (per-atom half-box jumps) and `unwrap=`; `selection matched 0 atoms` errors; mmCIF-aware loading |
| `render.py` | +311 / −167 | Scratch dirs removed after every call (`keep_work=` to retain); `render_movie` now **one VMD session, one fixed camera** (was one VMD per frame, camera reset per frame); new `render_frames`; Tachyon runs in parallel; `run_vmd_tcl` screened by `security`; timeouts return structured errors; ffmpeg-missing path keeps frames |
| `stats.py` | +200 / −111 | Partial `CONECT` bonds detected and supplemented by inference; H-bonds angle-based when hydrogens exist (`hbond_method` says which); vectorised ion mask and salt bridges (were per-atom Python loops); His excluded from salt bridges by default; secondary structure from the new DSSP; `count_hydrogen_bonds` exposed for reuse |
| `server.py` | +182 / −79 | `@tool()` wrapper turns policy violations into structured errors; path sandbox on every tool; `view_image` serves image files only; `renderer` argument; session now stores renderer + provenance; 3 new tools; `analyze_trajectory(unwrap=)` |
| `cli.py` | +151 / −3 | New subcommands `keyframes`, `claims`, `validate`, `provenance`, `renderers`, `bench {truth,run,sampling,rating-sheet,rating-summary}`; `--renderer` on `show`/`visualize`; `--unwrap` on `analyze`; renderer printed in the brief |
| `auto.py` | +102 / −34 | `renderer=` argument (`auto` falls back to matplotlib instead of returning no images); legend and colour keys built from what the backend **actually drew**; water colour key only when water shown; provenance written per run; renderer caveats added to the interpretation instructions; Tube descriptions |
| `report.py` | +102 / −15 | New sections **L** (claim verification) and **M** (reproducibility); figure paths relative to the report; atomic session writes; corrupt `session.json` quarantined instead of crashing; crash on missing numbers fixed; limitations auto-populated (PBC warning, thin data, renderer caveats) |
| `fetch.py` | +84 / −5 | `check_url` (http/https only, no loopback/private/link-local hosts), redirect-hop validation, size cap, gzip-bomb cap |
| `detect.py` | +24 / −14 | Loads via `molio` (mmCIF); O(n²) claimed-atom loop vectorised; material heuristic split into unambiguous elements (≥50 atoms) and bio-relevant S/Fe/Zn/Cu/Ni (≥500) |
| `recipes.py` | +22 / −9 | `representations_added` now reflects focus / pLDDT / explicit representation; `.mmcif`, `.ent`, `.pqr`, `.pdbqt`, `.lammps(trj)`, `.netcdf` file-type mapping; f-string nit |
| `media.py` | +20 / −7 | ffmpeg frame-select expression no longer relies on an invalid-escape string; tries both valid filter spellings and both `-fps_mode`/`-vsync` flag spellings |
| `environment.py` | +16 / −3 | Renderer inventory, `recommended_renderer`, `can_render_any`, `in_docker`; hard-coded `/home/akshay/...` examples removed; VMD "not bundled" guidance |
| `__init__.py` | +21 / −11 | Version 0.5.0 → **0.6.0**; exports `verify_claims`, `select_keyframes`, `get_renderer` |
| `colorkey.py` | +2 / −2 | "Structure" key no longer claims STRIDE-in-VMD only (also DSSP in the matplotlib backend) |

## 4. New modules

| Module | Lines | Purpose |
|---|---|---|
| `molio.py` | 181 | Native **mmCIF reader** + `load_universe` (used everywhere) |
| `dssp.py` | 206 | Kabsch-Sander **DSSP** in NumPy (sparse bridge search) |
| `timeseries.py` | 258 | Statistical inefficiency, N_eff, block averages, Mann-Kendall/Theil-Sen, half comparison, equilibration, `assess_stationarity` |
| `keyframes.py` | 334 | Event-aware keyframe selection, evaluation metrics, uniform-sampling theory |
| `claims.py` | 510 | **Claim verification**, sentence parser, Shrake-Rupley SASA / ligand burial |
| `validation.py` | 105 | Cross-check against independent NumPy implementations |
| `security.py` | 99 | Path sandbox, Tcl deny-list |
| `provenance.py` | 154 | Per-run provenance and verification |
| `renderers/` (5 files) | 706 | `base`, `vmd`, `mpl` (open-source renderer, 413 lines), `pymol` (experimental), registry |
| `bench/` (9 files) | 1,205 | `truth`, `questions`, `conditions`, `models`, `scorer`, `runner`, `sampling`, `rating_study` |

## 5. Bugs fixed (all present in the original)

1. **mmCIF fallback unusable**: `fetch` fell back to mmCIF but MDAnalysis cannot read it, so large entries failed at detection.
2. **Secondary structure never worked** on MDAnalysis < 2.8 (`MDAnalysis.analysis.dssp` import hidden by a bare `except`).
3. **Partial bond records reported as the full count** (lysozyme reported only its explicit bond records).
4. **H-bond count was distance-only**, presented as geometric.
5. **Every plot said "time (ps)"** even when x was a strided frame index.
6. **RMSF was per atom** but documented per residue; "most flexible residues" could repeat.
7. **RMSF's in-memory alignment** silently changed coordinates for later analyses in the same batch.
8. **`render_movie`** launched VMD per frame and reset the camera each frame.
9. **Scratch directories leaked** (on every render call).
10. **Colour key listed water swatches** when water was hidden.
11. **`representations_added`** ignored focus / pLDDT / explicit representation.
12. **Material heuristic** fired on ≥50 S/Fe/Zn/Cu atoms.
13. **ffmpeg `eq(n\,k)` / `-vsync`**: fragile across versions; invalid-escape warning.
14. **`Session` write** could truncate on interruption; **report** crashed on missing numbers.
15. **Hard-coded paths** (`/home/akshay/...`) in docs and messages.
16. **`run_vmd_tcl` accepted `exec`** and arbitrary Tcl.
17. **`fetch` accepted `file://`, `ftp://` and internal addresses**; no size cap.
18. **Stale docs**: README said 12 tools, listed 15, code had 24; referenced a `tests/session/` that never existed.
19. **`pyproject.toml`** would have omitted any new subpackages from an install.

## 6. Statistics: fixed thresholds replaced

| Was | Now |
|---|---|
| RMSD "stable" if std < 0.5 Å | `assess_stationarity`: autocorrelation-corrected CIs, Mann-Kendall + Theil-Sen, half-vs-half, ≥ 10 effective samples required |
| Rg "collapse/expansion" if ΔRg > 1 Å | start-vs-end windows in corrected SE units, \|z\| > 3 |
| Contacts "stable" if std < 15 % of mean | fraction of frames in contact + stationarity |
| 8 frames could be called "stable" | `insufficient_data` |
| No PBC awareness | per-atom half-box jump detection, optional `unwrap` |

## 7. New features (none existed before)

Renderer abstraction (VMD / **matplotlib**) · event-aware **keyframes** + closed-form sampling analysis ·
**claim verification** · **grounded-interpretation benchmark** (ground truth, questions, 8-condition ladder, scorer with
cluster bootstrap, runner, Anthropic adapter, sampling study, blinded rating study) · **provenance** · `validate` ·
server **sandbox** + Tcl screening + URL policy · `convergence` analysis.

## 8. Containers, CI, licensing

`Dockerfile` (targets `runtime`, `vmd-libs`, `with-vmd`) · `docker/entrypoint.sh` · `docker/install_vmd.sh` ·
`docker-compose.yml` (hardened: non-root, read-only, caps dropped) · `.dockerignore` · `vmd-dist/README.md` ·
`.github/workflows/ci.yml` (Python 3.9/3.11/3.12 + Docker build + smoke tests) · `LICENSE` (MIT) · `NOTICE.md`
(VMD not bundled; MDAnalysis is GPL) · `.gitignore` (never commit VMD).

## 9. Dependency / packaging changes

| | Original | v2 |
|---|---|---|
| Version | 0.5.0 | 0.6.0 |
| Core deps | MDAnalysis, numpy, scipy, matplotlib, networkx, pandas | **+ pillow** (was used but not declared) |
| Extras | `server`, `sasa`, `dssp` (mdtraj), `all` (mcp, freesasa, mdtraj) | `server`, `sasa`, `bench` (anthropic), `dev` (pytest), `all`; **`dssp` extra and mdtraj removed** (built-in DSSP) |
| Packages | `["vmd_agent"]` | `["vmd_agent", "vmd_agent.bench", "vmd_agent.renderers"]` |
| pytest config | none | markers, warning filters |

## 10. Behaviour changes that could affect existing callers

Review these if anything outside this repo uses the old API.

* `structure_stats(hbond_cutoff=...)`: the argument is now **accepted and ignored** (`**_legacy`). Salt bridges **exclude His by
  default** (original included it). H-bond and bond counts will differ (see §5). `n_hydrogen_bonds_geometric` is kept as an alias of `n_hydrogen_bonds`.
* `analyze_trajectory`: new `unwrap` parameter; `interpretation` strings are different; results gain `stationarity`, `time_axis`,
  `pbc`, `notes`; `hbonds` values differ (own implementation, no charges needed); `rmsf` is per residue. `drift_2nd_half` is kept.
* `render_image` / `render_views`: **no longer return `scene_file` / `scenes`** unless `keep_work=True`. `render_movie` returns
  `source_frames` and `stride`, and `frames_dir` only with `keep_frames=True`.
* `visualize_and_interpret` / `fetch_and_visualize`: new `renderer` argument. With `auto` and no VMD you now get **images from the
  matplotlib backend** (previously: no images and a note). They also write `provenance.json` into `out_dir`, and the package has new
  `renderer` and `provenance_path` keys.
* `build_color_keys`: water key only with `show_water=True`.
* `run_vmd_tcl`: may return `{"ok": False, "blocked": True}`.
* `fetch_structure(source="url")`: may refuse a URL; `_http_get` gained `max_bytes`.
* Server: tools return `{"ok": False, "blocked": True, ...}` on policy violations; `view_image` raises for non-image extensions.
* `Session` data gained `claims`, `provenance`, `renderer`; reports gain sections L and M.
* `probe_environment` gained `renderers`, `recommended_renderer`, `can_render_any`, `pymol`, `in_docker`.

## 11. Things that are the same on purpose

* The central design (code prepares evidence, the model interprets), the MCP-first shape, the 12-representation
  catalogue, VMD palette tables, focus plans, the inspection rules, and the video-verification pipeline.
* Python ≥ 3.9 for the core; the MCP server still needs ≥ 3.10.

## 12. Not changed / not done

Docker images unbuilt · real VMD/ffmpeg never run (fakes only) · no real-model benchmark results · DSSP not compared to `mkdssp` itself (it *is* compared to PDB annotations and MDTraj, see VALIDATION.md) · EGFR/TP53/PD-1 example folders are empty in the original.

---

## 13. Second round (0.7.0): evidence and a leaner repo

* **Version** 0.6.0 → **0.7.0**.
* **New modules:** `bench/events.py` (real-noise event study), `bench/synth.py` (procedural novel structures + generator
  validation). **Extended:** `validation.py` (DSSP vs PDB records and MDTraj), `bench/scorer.py` (`group_difference`,
  `contamination_estimate`), `bench/runner.py` (`groups`, `plan_benchmark`), `analysis.py` (`dt_ps`, DCD time warning),
  `stats.py` (`n_protein_chains`, `n_nucleic_chains`, `n_chains_all`), `dssp.py` (returns chain labels), `cli.py`
  (`validate-dssp`, `bench synth|events`, `--synthetic-dir`, `--dry-run`, `--price-in/--price-out`, `--dt-ps`).
* **Removed:** PyMOL backend (never run; it was added in v2, not in the original), `networkx`/`pandas` dependencies (never
  imported), unused imports, the legacy `examples/` renders, the duplicate NeRF code in `tests/conftest.py`.
* **Behaviour changes:** `stats["n_chains"]` now counts **polymer** chains (was every chain ID, including ligands and waters);
  the figure panel says "N protein chains"; `analyze_trajectory` results' `time_axis` gains `source` and (for DCD) `warning`;
  renderer choices are `auto|vmd|matplotlib`. (`params_for`, `panel_side`, the `hbond_cutoff` parameter and the
  mdtraj/networkx/pandas probes that this round removed were **restored** in 0.8.0; see section 15.)
* **Tests:** PyMOL tests removed; more added. **Docs:** VALIDATION described validation procedures.
* **Size:** the repository shrank sharply once the legacy renders were removed.

---

## 14. Third round: repository restructure (paths in sections 1 to 13 describe the *original* layout)

`src/` layout at the repo root; role-based subpackages `inputs/ structure/ dynamics/ visual/ evidence/` (+ `bench/`);
tests mirror the package; Docker files in `docker/`; `docs/TECHNICAL.md`; layering enforced by
`tests/system/test_layering.py`. `probe_environment` and `select_keyframes(render=...)` moved to `vmd_agent.auto`
(still exported from `vmd_agent`). Deep imports changed; see the table in `CHANGELOG.md`.


---

## 15. Retention audit (0.8.0): was anything from the original lost?

Method: the original `vmd-agent-new/` and this repo were compared programmatically, then run side by side.

| Check | Result |
|---|---|
| Every function and class defined in the original exists here | all retained except one internal helper (`_rmsd_interp`, below) |
| Every parameter of every same-named function | 3 public parameters were lost in an earlier round and restored (below); the only other differences are private analysis helpers that now take one context object instead of `u` and `out_dir` |
| All 24 MCP tools, with the same parameters and defaults | all retained; 3 new tools; some gained optional parameters |
| All 16 CLI subcommands and every option, default and choice | all retained unchanged; new subcommands added |
| Output keys of `inspect_files`, `detect_system`, `structure_stats`, recipes, colour keys, representations, all 9 analyses, probe | all keys retained except a few that are not functionality (below) |
| VMD/Tcl recipes for several systems and both styles | compared as text; the generated Tcl was unchanged |
| The 12 representations, focus presets, colour methods, materials | identical |

**Lost in 0.7.0 and restored in 0.8.0**

| Item | What happened | Now |
|---|---|---|
| `structure_stats(hbond_cutoff=...)` | silently swallowed by a `**kwargs` catch-all | a real parameter (donor-acceptor limit, default 3.5 Å); an unknown option raises `TypeError` |
| `annotate_image(panel_side=...)` | removed as "unused" | implemented (`right` or `left`), also on the MCP tool and CLI (`--panel-side`) |
| `representations.params_for` | removed as "unused" | restored and used by `describe_representation` |
| `probe_environment` reporting mdtraj, networkx, pandas | removed | restored in `analysis_libs` |
| `pip install vmd-agent[dssp]` extra (mdtraj) | removed | restored; also in `[all]` |

**Intentionally not carried over (no functionality lost)**

* `analysis._rmsd_interp`: its one-line verdict ("Low RMSD fluctuation, structure appears stable") judged stability
  from the size of the fluctuation, which is not a convergence test. The `interpretation` key remains and now comes from
  the autocorrelation-aware assessment.
* `secondary_structure.note`: the original returned this when its DSSP backend was missing. The built-in DSSP is always
  available, so the situation cannot occur.
* The original errors for `hbonds` and `convergence` on the sample system (they now run).
* `networkx` and `pandas` as install dependencies (never imported).
* Duplicate `vmd-agent/` tree, stale root `fetch.py`, `render.dat`, `README_1.md` (section 1).

**Same function, deliberately different answer (bug fixes, not losses)**

Values differ on the same input where the original was wrong; each is documented in sections 3 to 13:
H-bond counts (the original's distance-only count overcounted; angle-based now), salt-bridge definition, bond
inference for crystal structures with sparse CONECT, `n_chains` (polymer chains, not
every chain ID), `most_flexible_residues` (the original could list one residue repeatedly), and the wording of
interpretations. The old key `n_hydrogen_bonds_geometric` is still emitted and equals `n_hydrogen_bonds`.

**Data not in this repo**

The original's example outputs (`*_run/`, `1BEB_whey_protein/`, `vmd_agent_output/`, PNG renders) remain
only in the original folder. They are results, not functionality, and are not needed to run anything.
