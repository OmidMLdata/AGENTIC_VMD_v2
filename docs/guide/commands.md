# Command reference

`vmd-agent --help` lists every command grouped in the order of the pipeline; `vmd-agent <command> --help` shows one command's flags. File names in examples are examples. The commands that drive VMD itself (`vmd-agent vmd ...`) are in [Driving VMD itself](vmd.md#6-drive-vmd-itself).

## 2. Get a structure

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent fetch ID` | download a PDB ID, UniProt (AlphaFold) accession or URL to a file | `--out-dir DIR` · `--source auto\|rcsb\|alphafold\|url` · `--format auto\|pdb\|cif` |
| `vmd-agent search words ...` | find PDB IDs by keyword | `--limit N` |

Or use your own files: put them in your files folder. `vmd-agent inspect FILE ...` says what kind of files they are and which companion
file (for example the PSF that goes with a DCD) is missing.

## 3. Look at it

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent show ID` | download a PDB ID, UniProt accession or URL, draw it, describe it | `--views front side top iso` · `--focus overview\|fold\|interactions\|surface\|pocket` · `--rep QuickSurf` · `--renderer auto\|vmd\|matplotlib` · `--source auto\|rcsb\|alphafold\|url` · `--out-dir DIR` · `--style` · `--bg` · `--water` |
| `vmd-agent visualize FILE` | draw your structure (or a simulation) from several angles and explain every colour | `--traj FILE` · `--views` · `--focus` · `--rep` · `--renderer` · `--out-dir DIR` · `--style` · `--bg` · `--no-render` (just the description and script) |
| `vmd-agent inspect FILE ...` | what kind of files these are and what companion file is missing | none |
| `vmd-agent detect FILE` | what is in the system: protein, ligand, water, ions, lipids, nucleic acids | `--traj FILE` |
| `vmd-agent stats FILE` | bond, disulfide, H-bond and salt-bridge counts, secondary structure, a colour key | `--traj FILE` · `--json` |
| `vmd-agent render FILE` | one VMD + Tachyon image | `--traj FILE` · `-o out.png` · `--frame N` · `--vmd PATH` |
| `vmd-agent recipe FILE` | write a VMD script that draws this system sensibly | `--traj FILE` · `-o script.tcl` · `--style` · `--bg` · `--water` |
| `vmd-agent reps` | the VMD representations and when to use each | `--category backbone\|atomic\|surface\|special` · `--name NAME` |
| `vmd-agent annotate IMAGE` | draw a colour key and statistics onto an image | `--topology FILE` · `--title TEXT` · `-o out.png` · `--panel-side right\|left` |

Pictures use VMD + Tachyon when you have them (best), or a built-in matplotlib drawing (backbone trace, no shading, no surfaces).

## 4. Measure a simulation

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent analyze TOP TRAJ` | RMSD, flexibility, size, contacts, H-bonds and a verdict on whether the run has settled | `--do rmsd rmsf rgyr hbonds contacts distance sasa density convergence` · `--sel "protein"` · `--sel2 "resname LIG"` (for contacts and distance) · `--cutoff A` · `--step N` · `--unwrap` (make molecules whole across the box) · `--dt-ps T` (the true time between frames when the header is wrong) · `--out-dir DIR` |
| `vmd-agent keyframes TOP TRAJ` | the frames where something actually happens, not evenly spaced ones | `-k N` how many · `--sel` · `--sel2` · `--step` · `--z-min` · `--render` draw them · `--renderer` · `--out-dir DIR` |
| `vmd-agent claims FILE "statement" ...` | check statements against the data: supported, contradicted, or "cannot tell" | `--traj FILE` · `--step N` |

Every result says *how* it was obtained. These need no VMD: inspecting files, loading PDB / PSF / GRO / XTC / DCD and mmCIF (read
natively), detecting components, integrity checks, bonds, disulfides, H-bonds, salt bridges, secondary structure (DSSP), trajectory
analysis, keyframes and claim checking.

## 7. Check and keep records

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent provenance PATH` | re-check the hashes of the inputs and outputs of an earlier run | none |
| `vmd-agent report SESSION_DIR` | assemble a written report from a finished session | `--out FILE` · `--title TEXT` |
| `vmd-agent probe-video VIDEO` | read a video's metadata and prove it decodes (uses the bundled ffmpeg) | `--count-frames` |
| `vmd-agent interpret-video VIDEO` | verify a video and pull out stills you can map back to simulation frames | `-n N` stills · `--out-dir DIR` · `--timestamps ...` · `--stride N` · `--first-frame N` · `--time-per-frame T` · `--time-unit` · `--count-frames` |
| `vmd-agent validate TOP TRAJ` | cross-check the analysis against independent NumPy | `--sel` · `--sel2` · `--cutoff` |
| `vmd-agent validate-dssp ID_OR_FILE ...` | compare the secondary-structure code with the PDB's own annotations | `--cache DIR` · `--mdtraj` |
| `vmd-agent bench models` | put language models in front of the tools: tasks per kind of functionality, graded by a program, with seconds (see [the model benchmark](../benchmarks/model-benchmark.md)) | `--model` · `--base-url` · `--api-key` · `--categories` · `--only` · `--repeats` · `--tools all\|core\|vmd\|auto` · `--smoke` · `--catalogue` · `--pull` · `--oracle` · `--reference` · `--no-guard` · `--skip` · `--list` · `--summarize` |
| `vmd-agent bench tools` | run every tool on a generated dataset whose answers are known, with the seconds each took (see [the tool test set](../benchmarks/tool-test-set.md)) | `--data-dir` · `--only` · `--skip` · `--list` · `--json` |
| `vmd-agent bench ...` | the research benchmark, also in a container with your VMD (`vmd-agent bench docker`) | see [Development](../reference/development.md#running-and-reproducing) and [Docker](docker.md#docker) |

## Other commands

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent setup` | first-time setup: finds VMD, picks your files folder, sets up the AI | `--yes` accept defaults · `--check` only show the settings · `--use local\|online\|app\|skip` · `--model NAME` · `--data-dir FOLDER` · `--vmd PATH` |
| `vmd-agent` (or `menu`) | the numbered menu | none |
| `vmd-agent chat ["question"]` | talk to the tools with a language model | see [Ways to work](using.md#ways-to-work) |
| `vmd-agent ui` | the toolkit in a web page on this computer: your files, the chat with the seconds each step took, the whole jobs | `--data-dir FOLDER` · `--port N` · `--no-browser` · `--base-url ADDRESS` · `--model NAME` · `--api-key KEY` · `--tools all\|core\|vmd` |
| `vmd-agent doctor` | what this computer has, whether VMD really starts, which chat model is ready, what to do next | none |
| `vmd-agent models` | the suggested free models, with the date they were checked | `--check` ask the Ollama library again |
| `vmd-agent start ["question"]` | the Docker route: picks native or Docker from the facts and starts the chat | `--mode auto\|docker\|native` · `--model` · `--data-dir` · `--base-url` · `--print-plan` (show, run nothing) · `--down` (stop the containers) |
| `vmd-agent probe` / `vmd-agent renderers` | what VMD, drawing backends and libraries this computer has | `--vmd PATH` |
| `vmd-agent mcp-config` | the settings that connect Claude Desktop / Code to the tools | `--write` add them to Claude Desktop (with a backup) · `--roots FOLDER ...` · `--vmd PATH` |
| `vmd-agent mcp-check` | test an MCP server install the way a real client uses it | `--roots` · `--vmd` · `--render` · `--command` · `--args` · `--env KEY=VALUE` |
| `vmd-agent tools` | list every tool the chat and MCP server offer | `--group all\|core\|vmd` · `--size` (how much of a model's context the descriptions take) |
| `vmd-agent tool NAME '{json}'` | run any one tool with its arguments as JSON | example: `vmd-agent tool probe_environment '{}'` |

`vmd-agent --help` shows every command grouped in the order of this page; `vmd-agent <command> --help` shows one command's flags.

**Flags that mean the same everywhere**

| Flag | Meaning |
|---|---|
| `--traj FILE` (also `--trajectory`) | the trajectory that goes with the structure |
| `--sel "..."` (also `--selection`), `--sel2 "..."` | a VMD atom selection, and a second one |
| `--vmd PATH` | use this VMD instead of the one found automatically |
| `--out-dir DIR`, `-o FILE`, `--out PATH` | where results are written |
| `--views`, `--focus`, `--rep`, `--renderer`, `--style`, `--bg` | how pictures look |
| `--step N` | use every Nth frame |
| `--json` | machine-readable output where a command prints a summary |
| `--yes` | accept the defaults without asking (setup) |
| `--full` | everything, not shortened (the `vmd` commands) |
