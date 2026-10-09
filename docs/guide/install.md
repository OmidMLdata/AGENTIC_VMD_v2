# Install and set up

Everything about getting vmd-agent onto a computer, setting it up, and changing your mind later. The short version is in the [README](../../README.md#install).

## Before you start

* **A Mac, Windows or Linux computer** with an internet connection (the install downloads about 0.3 GB, plus the model if you choose one).
* **VMD** is optional but recommended: free from [UIUC](https://www.ks.uiuc.edu/Research/vmd/) (a 1.9.x release; the toolkit was written for that series). It draws the pictures and runs many of the tools. Without it, most analysis still works and pictures use a simpler built-in drawing.
* **Memory:** 16 GB or more for the recommended model, 8 GB for a small one. Setup reads your computer and says which models fit.
* You do **not** need Python, Git, Docker, an administrator password, an account or an API key.

## Install (about 5 minutes)

**Open a terminal.** Mac: press `Cmd` + `Space`, type `Terminal`, press Enter. Windows: Start menu, type `PowerShell`, press Enter. Linux: your terminal app. **Paste ONE line and press Enter.**

Mac or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install/install.ps1 | iex"
```

It puts a small helper called [uv](https://docs.astral.sh/uv/) (which fetches Python for you) and vmd-agent, with everything they need including a bundled ffmpeg for movies, into **one private folder** (`~/vmd-agent`; Windows
`%USERPROFILE%\vmd-agent`). No administrator password, and no changes to your PATH or to any file outside that folder. It takes a few minutes, mostly downloading. The two installers are separate files only because a Mac's shell and
PowerShell cannot read each other's language; they do the same thing.

## Answer the setup questions

The installer starts `vmd-agent setup`. It explains each step and asks a few things. **Pressing Enter accepts the suggestion every time.**

| Step | What happens | What you answer |
|---|---|---|
| **Where it keeps its data** | Only asked outside your home folder: whether vmd-agent's own data (settings, the link to your VMD window, the free model) goes in a `.vmd-agent` folder inside the folder you are in, or in one place for your account. | Enter for the suggestion. See [Where everything lives](#where-everything-lives-updating-uninstalling). |
| **1. VMD** | Looks for VMD, **starts it once to prove it works**, and tells you its version. | Nothing, unless it cannot find it: then type the folder VMD is in, or Enter to skip. It never opens a web page unless you say yes, and asks that only once. |
| **2. Your files** | Makes a folder, by default `~/vmd-agent-data`. The agent can **only see this folder**. | Enter to accept, or type another. |
| **3. Who answers** | You choose who answers your questions (below). | A number from 1 to 4; Enter for the free local model. |
| **4. Finish** | Saves your choices and offers to open the web page. | Yes. |

From then on, start it with `~/vmd-agent/bin/vmd-agent ui` (Windows: `%USERPROFILE%\vmd-agent\bin\vmd-agent.cmd ui`). Put your structure and trajectory files in your files folder and ask for them by name. Add that `bin` folder to your PATH
yourself if you want to type just `vmd-agent`; the installer never does it for you. Examples in these pages write `vmd-agent`. Run `vmd-agent setup` again at any time to change a choice, and `vmd-agent doctor` to see what this computer has,
whether VMD really starts, which model is ready, and what to do next.

## What it works out by itself

Setup and `vmd-agent doctor` read the computer: the operating system and CPU (macOS, Linux, Windows, WSL, a container; Apple Silicon or not), the memory, an NVIDIA card and its memory, VMD (found where that system keeps it, then started once to
prove it works), Ollama, Docker, and Claude Code. From that:

* **Where things live and how they are run** follow the operating system (VMD's launcher, the settings folder, paths turned into what Tcl wants, Claude Desktop's config file).
* **The suggested model fits the computer.** Every model is marked *fits*, *tight* or *too big* for your memory and graphics card, and one is suggested. You choose; nothing is downloaded without asking. See [Models](models.md#which-one-suits-this-computer-and-downloading-later).
* **Claude Code and Claude Desktop:** setup notes whether they are installed and offers them as one of the choices of who answers. It never registers vmd-agent with them as an extra on top of a model that runs here.

## Choosing who answers you (setup step 3)

| Choice | What it is | Good to know |
|---|---|---|
| **1. A free model on this computer** (recommended) | An open-source model run by a free program called Ollama. Works offline; your data never leaves the computer. | It asks before every download. It keeps a **private copy of Ollama inside the vmd-agent folder** (about 0.2 GB on a Mac, 1.4 to 1.6 GB on Linux and Windows), checked against Ollama's published checksum, plus the model (2 to 18 GB). If you already have Ollama it uses that instead. Downloads happen once. |
| **2. An online model service** | Any service with the common "OpenAI-compatible" chat interface: you give a web address, a model name and your key. | The key is saved in a file only you can read. |
| **3. Claude Code or Claude Desktop instead** | They do the thinking, and vmd-agent only supplies the tools ([details](mcp.md#use-it-from-an-mcp-client)). | It edits that app's settings file only after you say yes, and keeps a backup. vmd-agent's own chat and web page still need a model of their own. |
| **4. Skip** | No chat. | Every other command still works. |

**Said no to a download? You can change your mind at any time.** Run `vmd-agent models --install`, or open **Model** in the web page and choose **Download a model**. Both name the size and ask first.

A model on a computer without a graphics card can take a minute or more per answer. On a Mac, running Ollama directly (which setup does) uses the Mac's graphics chip and is much faster than running it inside Docker.

## Where everything lives, updating, uninstalling

The installer puts **everything** in one folder, by default `~/vmd-agent`: the helper tool, Python, the program and its packages (including ffmpeg), your settings, and, if you choose a free local model, a private copy of Ollama and its models.
It uses no administrator rights, installs nothing system-wide and does not edit your shell's startup files. Your files folder (`~/vmd-agent-data`) and VMD itself are separate and are never touched.

**Keeping vmd-agent's data inside a project folder.** Open a terminal in that folder and run `vmd-agent setup --home here`. It creates a `.vmd-agent` folder there with your settings (which may hold an API key), the link to your VMD window, and the private Ollama with its
models (a few GB). Any vmd-agent command run in that folder or below it uses it. Git ignores it, the tools can never read or write it even when it sits inside your files folder, and moving or deleting the project takes it along. If the installer's
folder already holds the models, setup offers to **move** them in: a rename, so instant on the same disk with no second copy, and refused while the model server is running (stop it first). The program itself stays where the installer put it.
The order of precedence is: `VMD_AGENT_HOME` or `VMD_AGENT_CONFIG_DIR`, then a `.vmd-agent` folder here or above, then the installer's folder, then the per-user folder.

**Update:** run the install line again. **Uninstall:** delete the `~/vmd-agent` folder (and any `.vmd-agent` folder you made). If you used Docker, `vmd-agent start --down` stops it and `docker compose down -v` removes its model volume.

## Other ways to install

* **You already use Python:** `pip install "vmd-agent[server] @ https://github.com/OmidMLdata/AGENTIC_VMD_v2/archive/refs/heads/main.zip"`,
  then `vmd-agent setup`. The packages are listed once, in [`pyproject.toml`](../../pyproject.toml) (`[all]` adds the optional ones).
* **From a downloaded copy:** run `./install/install.sh` (Mac/Linux) or `install\install.ps1` (Windows) from inside the folder; it installs that copy.
* **Docker (advanced):** `vmd-agent start` picks native or Docker from the facts about your computer and starts the chat
  (`--print-plan` shows what it would do, `--down` stops the containers). Docker cannot run a Mac or Windows VMD (it needs VMD's
  **Linux** build in `docker/vmd-dist/`) and on a Mac cannot use the Mac's graphics chip. See [Docker](docker.md#docker).
* **An MCP client** (Claude Code, Claude Desktop, others): [Use it from an MCP client](mcp.md#use-it-from-an-mcp-client).

## If something goes wrong

| What you see | What to do |
|---|---|
| `vmd-agent: command not found` | use the full path `~/vmd-agent/bin/vmd-agent` (the installer does not change your PATH on purpose), or run the install line again |
| the model answers without looking at your files, or ignores its tools | the model is too small, or its context is too short: use `granite4.1:8b` or larger, and if you run your own Ollama set `OLLAMA_CONTEXT_LENGTH=16384` |
| "cannot reach the model server", or "no model" | open **Model** in the web page and choose **Start local server** or **Download a model**, or run `vmd-agent models --install`. If you use your own Ollama, start it. `vmd-agent setup --check` shows what is reachable. |
| "VMD was found but did not run" | the message names the likely cause (for example Linux needs `tcsh`: `sudo apt install tcsh`). `vmd-agent doctor` repeats it. |
| It cannot find VMD | `vmd-agent setup --vmd "<VMD's folder>"`. VMD is optional: without it, pictures use the built-in drawing. |
| "outside the allowed roots" | the AI can only use your files folder; put the file there, or choose another with `vmd-agent setup --data-dir` |
| the model's answers are poor or wrong | a small model may be the cause: try a larger one that fits (`vmd-agent models`, then `vmd-agent models --install MODEL`) or an online model. `vmd-agent tool verify_claims` checks any statement against the data. |
| anything else | run `vmd-agent doctor` and read its notes |
