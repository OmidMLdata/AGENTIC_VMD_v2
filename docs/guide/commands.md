# The command line

There are few commands, and no command that does what a tool already does: **every tool of the [library](tools.md) is run with `vmd-agent tool NAME`**, with flags made from the tool's own parameters.
`vmd-agent --help` lists the commands in the order below; `vmd-agent <command> --help` shows one command's flags. File names in examples are examples.

## 1. Set up

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent setup` | first-time setup: finds VMD, picks your files folder, sets up the AI | `--yes` accept defaults · `--check` only show the settings · `--use local\|online\|app\|skip` · `--model NAME` · `--data-dir FOLDER` · `--vmd PATH` |
| `vmd-agent doctor` | what this computer has, whether VMD really starts, which chat model is ready, what to do next | none |
| `vmd-agent models` | the suggested free models, with the date they were checked | `--check` ask the Ollama library again |
| `vmd-agent start ["question"]` | the Docker route: picks native or Docker from the facts and starts the chat | `--mode auto\|docker\|native` · `--model` · `--data-dir` · `--base-url` · `--print-plan` (show, run nothing) · `--down` (stop the containers) |

## 2. Ask in plain language

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent ui` | the toolkit in a web page on this computer: your files, a remote for a real VMD window, the chat with the seconds each step took, the whole jobs | `--data-dir FOLDER` · `--port N` · `--no-browser` · `--base-url ADDRESS` · `--model NAME` · `--api-key KEY` · `--tools all\|auto` |
| `vmd-agent chat ["question"]` | talk to the tools with a language model in the terminal | see [Ways to work](using.md#ways-to-work) |
| `vmd-agent` (or `menu`) | the numbered menu | none |

## 3. The tool library

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent tools` | list the tools, in groups, with what each does | `--size` (how much of a model's context the descriptions take) |
| `vmd-agent tool NAME ...` | run one tool | `--out PATH` where the result goes · `--full` print every value · `--quiet` no progress · plus the tool's own flags: `vmd-agent tool NAME --help` |

How a tool's parameters become flags: its required files are positional (`vmd-agent tool detect_system run.psf run.dcd`), its outputs are `--out`, every other parameter is a `--kebab-case` flag
(`--step 10`, `--selection "name CA"`), a yes/no option that is on by default is switched off with `--no-NAME` (`--no-align`), a list takes several words (`--analyses rmsd rgyr`), and a scene is a JSON
file or JSON text (`--scene scene.json`). A result is JSON; long lists are shortened unless you add `--full`. A tool that runs VMD saves the Tcl it ran and names it in `reproduce_script`. The exit code is 1
when the tool says `"ok": false`.

**The commands you will use most**, by what you want to do (all of them are `vmd-agent tool ...`; the library page has every tool):

| You want to | Command |
|---|---|
| know what kind of files these are and what is missing | `vmd-agent tool inspect_files run.dcd run.psf` |
| see what is in a system | `vmd-agent tool detect_system run.psf run.dcd` |
| count bonds, disulfides, hydrogen bonds | `vmd-agent tool structure_stats 1ubq.pdb` |
| download a structure | `vmd-agent tool fetch_structure 1UBQ --out pdbs` |
| find PDB IDs by keyword | `vmd-agent tool search_pdb hemoglobin --limit 5` |
| draw a structure from several angles and describe it | `vmd-agent tool visualize_and_interpret 1ubq.pdb --views front side --out figures` |
| draw one picture, or a scene you describe | `vmd-agent tool render_image run.pdb run.dcd --scene scene.json --out picture.png` |
| measure a simulation | `vmd-agent tool analyze_trajectory run.psf run.dcd --analyses rmsd rmsf rgyr` |
| pick the frames where something happens | `vmd-agent tool select_keyframes run.psf run.dcd --k 6` |
| check a statement against the data | `vmd-agent tool verify_claims 1ubq.pdb "It has one chain"` |
| check a video | `vmd-agent tool probe_video clip.mp4 --expect-width 320 --expect-height 240` |
| re-check the hashes of an earlier run | `vmd-agent tool verify_provenance session1` |

Pictures use VMD + Tachyon when you have them (best), or a built-in matplotlib drawing (backbone trace, no shading, no surfaces). Every result says *how* it was obtained. These need no VMD: inspecting files,
loading PDB / PSF / GRO / XTC / DCD and mmCIF (read natively), detecting components, integrity checks, bonds, disulfides, H-bonds, salt bridges, secondary structure (DSSP), trajectory analysis,
keyframes and claim checking.

## 4. Whole jobs

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent workflow` | list the workflows, what each does and which files it needs | none |
| `vmd-agent workflow NAME FILE ...` | run one: several tools in order, graded findings, a report | `--out-dir DIR` · `--option KEY=VALUE` (repeat) · `--quiet` |

See [Whole jobs](workflows.md).

## 5. Claude Code or Claude Desktop as the assistant

Only if you want one of them, rather than a model run by vmd-agent, to do the thinking.

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent mcp-config` | the settings that connect Claude Desktop / Code to the tools | `--write` add them to Claude Desktop (with a backup) · `--roots FOLDER ...` · `--vmd PATH` |
| `vmd-agent mcp-check` | test an MCP server install the way a real client uses it | `--roots` · `--vmd` · `--render` · `--command` · `--args` · `--env KEY=VALUE` |

## 6. Benchmarks and cross-checks

| Command | What it does | Flags worth knowing |
|---|---|---|
| `vmd-agent bench models` | put language models in front of the tools: tasks per kind of functionality, graded by a program, with seconds (see [the model benchmark](../benchmarks/model-benchmark.md)) | `--model` · `--base-url` · `--api-key` · `--categories` · `--only` · `--repeats` · `--tools all\|auto` · `--smoke` · `--catalogue` · `--pull` · `--oracle` · `--reference` · `--no-guard` · `--skip` · `--list` · `--summarize` |
| `vmd-agent bench tools` | run every tool on a generated dataset whose answers are known, with the seconds each took (see [the tool test set](../benchmarks/tool-test-set.md)) | `--data-dir` · `--only` · `--skip` · `--list` · `--json` |
| `vmd-agent bench validate TOP TRAJ` | cross-check the analysis against independent NumPy | `--sel` · `--sel2` · `--cutoff` |
| `vmd-agent bench validate-dssp ID_OR_FILE ...` | compare the secondary-structure code with the PDB's own annotations | `--cache DIR` · `--mdtraj` |
| `vmd-agent bench ...` | the research benchmark, also in a container with your VMD (`vmd-agent bench docker`) | see [Development](../reference/development.md#running-and-reproducing) and [Docker](docker.md#docker) |

`vmd-agent --help` shows every command grouped in the order of this page.

**Flags that mean the same everywhere**

| Flag | Meaning |
|---|---|
| `--out PATH` | where a tool writes its result (a folder, a file or a name prefix, as the tool says) |
| `--selection "..."`, `--selection2 "..."` | a VMD atom selection, and a second one |
| `--vmd PATH` | use this VMD instead of the one found automatically |
| `--views`, `--focus`, `--renderer`, `--style`, `--background` | how pictures look |
| `--step N` | use every Nth frame |
| `--yes` | accept the defaults without asking (setup) |
| `--full` | everything, not shortened (`tool`) |
