# vmd-agent

Ask questions about your molecular simulations in plain English, and get answers worked out from real measurements.

> *"Has my run settled?"* · *"Which salt bridges persist?"* · *"Build a solvated system from 1ubq.pdb."* · *"Is it true that the radius of gyration stays below 13 Å?"*

vmd-agent connects a language model to [VMD](https://www.ks.uiuc.edu/Research/vmd/), the molecular visualisation program. The model decides which tools to run, VMD and the analysis code do the measuring and drawing, and
every number in an answer has to come from a tool. You can watch it work in a real VMD window.

By default the model runs **on your own computer** (free and open source), so your data never leaves it. You can instead let **Claude** answer, with your own
Claude account (sign in in the browser, no API key) or with an API key.

## What you need

| | |
|---|---|
| **A computer** | Mac, Windows or Linux, with an internet connection for the install. |
| **VMD** | Free from [UIUC](https://www.ks.uiuc.edu/Research/vmd/). Recommended: it draws the pictures and runs many of the tools. Without it, most analysis still works. |
| **Memory** | 16 GB or more for the recommended model. 8 GB can run a smaller one. Setup checks your computer and tells you which models fit. |
| **Disk space** | About 6 GB for the program and the recommended model. |
| **Not needed** | Python, Git, Docker, an account or an API key (for the free model on your computer; Claude needs a Claude account). |

## Install

**1. Open a terminal.** On a Mac, press `Cmd` + `Space`, type `Terminal`, press Enter. On Windows, open the Start menu, type `PowerShell`, press Enter.

**2. Paste one line and press Enter.**

Mac or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.ps1 | iex"
```

This takes a few minutes, mostly downloading. It puts everything in one folder, `~/vmd-agent`, and needs no administrator password. It changes nothing outside that folder.

**3. Answer the setup questions.** Setup starts by itself. It explains each step, and pressing Enter accepts the suggestion every time:

| Setup asks | What to answer |
|---|---|
| **VMD** | Nothing. It finds VMD and starts it once to check that it works. If it cannot find it, type the folder VMD is in, or press Enter to skip. It never opens a web page unless you say yes. |
| **Your files folder** | Press Enter for `~/vmd-agent-data`. The agent can only read and write inside this folder. |
| **Who answers your questions** | Five choices; Enter takes the suggested one. **1.** The free model on your computer: it reads your memory and graphics card and suggests a model that fits. **2.** Your Claude account: sign in with your email or Google in the browser, no API key (needs a paid Claude plan; setup installs Claude Code, Anthropic's program, after asking). **3.** An online model service with an API key. **4.** Claude Code or Claude Desktop does the thinking in that app, and vmd-agent supplies the tools. **5.** Skip: everything but the chat still works. [What each means](docs/guide/install.md#choosing-who-answers-you-setup-step-3). |
| **Download the model** | It tells you the size and asks first. If you say no now, you can download it later (see below). |

**4. Open it.** At the end, setup offers to open the web page. Say yes.

That is the whole install. Details and other ways to install are in [Install and set up](docs/guide/install.md).

## Start it any time

```bash
~/vmd-agent/bin/vmd-agent ui
```

On Windows: `%USERPROFILE%\vmd-agent\bin\vmd-agent.cmd ui`. (If you would rather type just `vmd-agent`, add that `bin` folder to your PATH. The installer never does it for you.)

A page opens in your browser, and a real VMD window opens by itself. Put your structure and trajectory files in your files folder, then ask for them by name:

* *"What is in protein.pdb?"*
* *"Has my run settled? Use run.psf and run.dcd."*
* *"Show the protein as a surface coloured by residue type."*
* *"Check this statement against my data: it has 4 disulfide bridges."*
* *"Find the whey protein in the PDB and show chain A as a cartoon, residues 100-150 in red."* (it searches the PDB and AlphaFold itself)

Everything the agent does is listed with the seconds it took. Click any line to see the exact arguments and result.

## If something goes wrong

| What you see | What to do |
|---|---|
| `command not found` | Use the full path above, or run the install line again. |
| The chat says it has no model | Run `vmd-agent models --install`, or open **Model** in the web page and choose **Download a model**. Saying no to the download in setup is never final. |
| Claude: "cannot find Claude Code" | Open **Model** in the web page, choose **Claude Code on this computer** and press **Check**. It looks in every usual place; if it still cannot, run `which claude` in a terminal and put that path under **Where Claude Code is**. If `which claude` prints nothing, press **Install Claude Code** there. (The Claude app and claude.ai are not Claude Code.) |
| Claude: "not signed in" | In the same window press **Sign in with your Claude account** and sign in in the browser. It needs a paid Claude plan (Pro, Max, Team or Enterprise). |
| `CERTIFICATE_VERIFY_FAILED` | Update vmd-agent (run the install line again): it now uses your computer's own certificates, which also works on networks that inspect secure traffic. |
| Answers take a minute or more | A model on a computer without a suitable graphics card is slow. Choose a smaller model (`vmd-agent models`), or let Claude answer (above). |
| VMD was not found | Install VMD, then run `vmd-agent setup`. If it is somewhere unusual, run `vmd-agent setup --vmd "/path/to/VMD"`. |
| The model gives poor answers | A small model may be the cause. `vmd-agent models` shows which models fit your computer. |
| The install line fails | See [Install and set up](docs/guide/install.md#if-something-goes-wrong). |

`vmd-agent doctor` prints what it found on your computer (system, memory, graphics card, VMD, Ollama) and what to do next.

## Choosing a model

`vmd-agent models` reads your computer and marks each suggested model **fits**, **tight** or **too big**, and names the one to start with. On a 16 GB computer that is usually `granite4.1:8b` (5.4 GB). Details:
[Models](docs/guide/models.md).

**Claude** can answer instead, chosen in setup or in **Model** in the web page: Claude Fable 5.1, Opus 5.5, Sonnet 5.5 or Haiku 5.5. Either with your **Claude account**
(choose *Claude Code on this computer*; the window installs Claude Code and signs you in, no key), or with an **API key** (choose *Another server*, address
`https://api.anthropic.com/v1`, a key scoped to a workspace, and a model name such as `claude-sonnet-5-5`). [Claude](docs/guide/models.md#claude).

## Other ways to work

| Way | Start it |
|---|---|
| **The web page** (recommended): a remote control for a real VMD window, with the chat, a form for every tool, and whole jobs | `vmd-agent ui` |
| **A numbered menu** in plain words | `vmd-agent` |
| **The chat** in the terminal | `vmd-agent chat` |
| **Claude, with your Claude account,** answering in the web page and the chat (through Claude Code, which only gets vmd-agent's tools) | **Model** in the web page, or `vmd-agent setup --use claude` |
| **One command per tool**, with no model, for scripts | `vmd-agent tool NAME ...` |
| **Claude Code or Claude Desktop** as the assistant, chatting in that app, with vmd-agent supplying the tools | [MCP clients](docs/guide/mcp.md) |

```bash
vmd-agent tools                                                          # every tool, in groups
vmd-agent tool fetch_structure 1UBQ --out pdbs                           # download a structure
vmd-agent tool analyze_trajectory run.psf run.dcd --analyses rmsd rgyr   # measure a simulation
vmd-agent tool verify_claims my.pdb "It has 4 disulfide bridges"         # check a statement against the data
vmd-agent workflow equilibration_check run.psf run.dcd                   # a whole job, with a report
```

## What it can do

It has **57 tools** in eleven groups, and eleven whole-job workflows that run several tools in order and write a report.

* **Understand a structure:** what it contains, bonds, secondary structure, chain gaps and other problems, pictures from several angles.
* **Measure a simulation:** RMSD, RMSF, radius of gyration, contacts, hydrogen bonds and more, with tests for whether a run has converged.
* **Check statements:** a sentence about your system comes back supported, contradicted or "can't tell", with the evidence.
* **Drive VMD:** load, draw, colour, rotate and measure in the real window, from chat or from forms. Plain words work: "red", "CPK colours", "cartoon", "chain A", "residues 100-150", "the binding pocket".
* **Find structures:** search the PDB by name and download from the PDB, AlphaFold or a web address you give.
* **Build and convert:** solvated systems, mutations, membranes, trajectory conversion, cryo-EM map fitting, NAMD and SLURM files.
* **Whole jobs with a report:** has the run settled, which residues are flexible, does the ligand stay bound, can I trust this trajectory, how do two runs or two structures compare, are these statements true.

The full lists are in [The tool library](docs/guide/tools.md) and [Whole jobs](docs/guide/workflows.md). [Why use vmd-agent](docs/guide/why.md) explains what it adds over using VMD on its own.

## Safe by design

The agent can only read and write inside your files folder, and it cannot touch vmd-agent's own settings. It never runs Tcl handed to it by a caller: each VMD command is built from checked values and run with a time limit. Downloads are limited to
sources you name, and the model server is checked against its published checksum before it runs. When Claude Code answers, it is given vmd-agent's tools only (its own shell, file
and web tools are switched off), and your Claude password is typed on Claude's sign-in page, never into vmd-agent. [Security](docs/reference/security.md).

## Learn more

[Install and set up](docs/guide/install.md) · [How it works](docs/guide/how-it-works.md) · [Ways to work](docs/guide/using.md) · [Your VMD window](docs/guide/window.md) · [Models](docs/guide/models.md) · [The command line](docs/guide/commands.md) ·
[MCP clients](docs/guide/mcp.md) · [Docker](docs/guide/docker.md) · [Development](docs/reference/development.md) · [All the pages](docs/index.md) · [Changelog](docs/CHANGELOG.md)

## Contributing and licence

`pip install -e ".[dev]"`, then `ruff check src tests` and `pytest -rs`. See [Development](docs/reference/development.md).

MIT licence ([LICENSE](LICENSE)). Third-party notes, including **VMD and MDAnalysis (GPL)**: [NOTICE](docs/NOTICE.md).
