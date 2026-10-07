# vmd-agent

Ask questions about your molecular structures and simulations **in plain language**, and get answers worked out from real measurements:
what is in a system, how it moves, whether a statement about it is true. [VMD](https://www.ks.uiuc.edu/Research/vmd/) does the measuring and
the drawing; a language model (a free one on your own computer, or an online one you choose) does the talking; vmd-agent gives it the tools and
checks its work.

* **Every number comes from a tool, and says how.** A model that answers from memory is sent back to use a tool; any number it writes that no tool
  returned is flagged.
* **A complete wrapper around VMD.** 24 commands drive VMD itself (measure, build systems and membranes, density maps, scenes, hand-offs to NAMD
  and a cluster), each saving the exact Tcl it ran so you can repeat it in your own VMD.
* **Whole jobs, not just single commands.** Workflows run several tools in a fixed order, grade the findings and write a report with the
  checksums of your inputs.
* **Four ways to work, one set of tools:** a web page with a molecule viewer, a menu, a chat, and plain commands. Everything is timed: you see how long every model call and
  every tool call took.
* **Tested.** A [tool test set](docs/tool-test-set.md) checks every tool against data with known answers, and a [model benchmark](docs/model-benchmark.md) scores any language model on tasks for
  each kind of functionality.
* **Contained.** One private folder, no administrator rights, nothing installed system-wide. Nothing is sent anywhere unless you choose an online model.

**You need** a Mac, Windows or Linux computer, an internet connection, and VMD (free, from UIUC) if you want VMD-quality pictures and the VMD-driven
tools. **You do not need** Python, Git, Docker, ffmpeg, an account or any AI app.

## Install

Open a terminal (Mac: `Cmd` + `Space`, type `Terminal`; Windows: Start menu, type `PowerShell`), paste **one line**, and answer four questions.

Mac or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.ps1 | iex"
```

Everything goes into one folder (`~/vmd-agent`); deleting it removes everything. Setup finds VMD and starts it once to prove it works, makes a files
folder the AI is confined to, and lets you choose who answers: a free model on your computer (recommended), an online service, Claude Desktop or Code, or none.
Details, other ways to install, and what to do when something fails: [Install and set up](docs/install.md).

## Use it

```bash
vmd-agent ui                         # a web page: your files, the chat, whole jobs, pictures
vmd-agent                            # a numbered menu
vmd-agent chat                       # ask in plain words, in the terminal
vmd-agent show 1UBQ                  # or commands: fetch, draw and describe a structure
```

Put your structure and trajectory files in your files folder and ask for them by name: *"What is in protein.pdb?"*, *"Has my run settled? Use run.psf and run.dcd."*,
*"Which salt bridges persist?"*, *"Build a solvated, neutral system from 1ubq.pdb."*

| I want to... | Type |
|---|---|
| work in a browser window | `vmd-agent ui` |
| ask questions in plain language | `vmd-agent chat` |
| look at a protein from the PDB | `vmd-agent show 1UBQ` |
| draw my own structure (or simulation) | `vmd-agent visualize my.pdb --traj run.dcd` |
| measure a simulation | `vmd-agent analyze my.psf run.dcd --do rmsd rmsf rgyr` |
| check a statement against the data | `vmd-agent claims my.pdb "It has 4 disulfide bridges"` |
| find when something happens in a run | `vmd-agent keyframes my.psf run.dcd -k 9` |
| run a whole job and get a report | `vmd-agent workflow equilibration_check my.psf run.dcd` |
| use VMD's own commands | `vmd-agent vmd` lists them |
| see if everything works here | `vmd-agent doctor` |
| test every tool on data with known answers | `vmd-agent bench tools` |
| score a language model on these tools | `vmd-agent bench models --model NAME` |

## The pipeline

One project goes through the same stages whichever way you work. `vmd-agent --help` lists every command in this order.

| Stage | You want to | Main commands | Detail |
|---|---|---|---|
| 1. Set up | install, find VMD, choose who answers | `vmd-agent setup`, `doctor`, `models` | [Install](docs/install.md), [Models](docs/models.md) |
| 2. Get a structure | have a file to work with | `vmd-agent fetch`, `search` | [Commands](docs/commands.md#2-get-a-structure) |
| 3. Look at it | see and describe what is in it | `vmd-agent show`, `visualize`, `inspect`, `detect`, `stats` | [Commands](docs/commands.md#3-look-at-it) |
| 4. Measure a simulation | numbers, events, true-or-false checks | `vmd-agent analyze`, `keyframes`, `claims` | [Commands](docs/commands.md#4-measure-a-simulation) |
| 5. Run a whole job | several steps, a verdict, a report | `vmd-agent workflow` | [Workflows](docs/workflows.md) |
| 6. Drive VMD itself | build systems, maps, scenes, hand-offs | `vmd-agent vmd ...` | [VMD](docs/vmd.md) |
| 7. Check and keep records | re-check hashes, videos, validation | `vmd-agent provenance`, `report`, `validate` | [Commands](docs/commands.md#7-check-and-keep-records) |

Behind all of it are **53 tools**: the 27 original ones, the 24 that drive VMD, and 2 that run whole jobs ([the list](docs/tools.md)). The chat, the web page,
the [MCP server](docs/mcp.md) and the commands all call the same functions. By default a chat model is offered **all 53 at once** (about 8,000 tokens of descriptions with every
question); `--tools core` or `--tools vmd` offers about half, which suits small models ([details](docs/tools.md#does-the-model-see-all-53-at-once)).

## What has and has not been verified

| | |
|---|---|
| **Verified by running** | the analysis and structure code, against independent implementations by procedures you can repeat; every tool, against **a real VMD 1.9.4a57 on macOS Apple Silicon** and a real ffmpeg, on a [dataset with known answers](docs/tool-test-set.md); the setup logic, menu, web page and settings; `install.sh` from a local copy; the private Ollama download and start; a real chat with `granite4.1:8b` calling the tools; both MCP SDK generations; the open-source Docker image's build and smoke test in CI |
| **Never run** | the one-line installer URLs (the repository is private for now, so they cannot be fetched), `install.ps1`, Linux, anything on Windows; any model other than `granite4.1:8b` and `granite4.1:3b`; VMD on Linux or Windows and any other VMD version; the Docker launcher routes (`vmd-agent start`, `bench docker`); any real MCP client; a NAMD run of the written input and a SLURM run of the written script |
| **Results** | **none are included.** This repository ships no measured results, benchmark scores or model evaluations; everything is produced by running the commands on your own data. |

Tests that need something the machine lacks are **skipped with the reason shown, never counted as passed**.

## Documentation

[**All the pages**](docs/index.md): [Install and set up](docs/install.md) · [Ways to work](docs/using.md) · [Command reference](docs/commands.md) · [Models](docs/models.md) ·
[Whole jobs](docs/workflows.md) · [VMD](docs/vmd.md) · [The 53 tools](docs/tools.md) · [The tool test set](docs/tool-test-set.md) · [The model benchmark](docs/model-benchmark.md) · [MCP clients](docs/mcp.md) ·
[Docker](docs/docker.md) · [Development](docs/development.md) · [Architecture](docs/architecture.md) · [Methods](docs/methods.md) · [Security](docs/security.md) ·
[Research paper](docs/RESEARCH.md) · [Changelog](CHANGELOG.md)

The repository also holds a **benchmark**: *can an LLM agent carry out VMD analysis and visualization workflows correctly, and say so when it cannot?* Six task
families with answers known by construction, scored on success and **silent errors**. `vmd-agent` is one entrant in it, not the presumed winner, and the model
that wrote the benchmark must not run it. How to run it: [Development](docs/development.md#5-run-the-automation-benchmark); the design:
[research paper](docs/RESEARCH.md).

## Contributing

`pip install -e ".[dev]"`, then `ruff check src tests`, `vulture` and `pytest -rs` (what CI runs). See [Development](docs/development.md).

MIT licence ([LICENSE](LICENSE)). Third-party notes, including **VMD and MDAnalysis (GPL)**: [NOTICE.md](NOTICE.md).
