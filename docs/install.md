# Install and set up

Everything about getting vmd-agent onto a computer and choosing who answers your questions. The short version is on the [README](../README.md#install).

## Install (about 5 minutes)

**Open a terminal.** Mac: press `Cmd` + `Space`, type `Terminal`, press Enter. Windows: Start menu, type `PowerShell`, press
Enter. Linux: your terminal app. **Paste ONE line and press Enter.** Mac or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.ps1 | iex"
```

It puts a small helper called [uv](https://docs.astral.sh/uv/) (which fetches Python for you) and vmd-agent, with everything they
need including a bundled ffmpeg for movies, into **one private folder** (`~/vmd-agent`; Windows `%USERPROFILE%\vmd-agent`). No
administrator password, no changes to your PATH or to any file outside that folder. It takes a few minutes, mostly downloading.
The two installers (`install.sh`, `install.ps1`) are separate files only because a Mac's shell and PowerShell cannot read each
other's language, and they must run before Python exists; they do the same thing.

## Answer the setup questions

The installer starts `vmd-agent setup`. It explains each step and asks four things:

| Step | What happens | What you answer |
|---|---|---|
| 1. VMD | looks for VMD, **starts it once to prove it works**, and tells you its version | nothing, unless it cannot find it (then: the folder VMD is in, or Enter to skip) |
| 2. Your files | makes a folder, by default `~/vmd-agent-data`. The AI can **only see this folder**. | Enter to accept, or type another |
| 3. The AI | you choose who answers (below) | a number from 1 to 4 |
| 4. Finish | saves your choices | nothing |

From now on run `~/vmd-agent/bin/vmd-agent` (Windows: `%USERPROFILE%\vmd-agent\bin\vmd-agent.cmd`). Put your structure and
trajectory files in your files folder and ask for them by name. (Add that `bin` folder to your PATH yourself if you want to type just
`vmd-agent`; the installer never does it for you. Examples here write `vmd-agent`.) `vmd-agent setup` can be run again at any time to
change a choice, and `vmd-agent doctor` says what this computer has, whether VMD really starts, which model is ready, and what to do
next.

## Choosing who answers you (setup step 3)

| Choice | What it is | Good to know |
|---|---|---|
| **1. A free model on this computer** (recommended) | An open-source model run by a free program called Ollama. Works offline; your data never leaves the computer. | It asks before downloading anything. It keeps a **private copy of Ollama inside the vmd-agent folder** (about 0.2 GB on a Mac, 1.4 to 1.6 GB on Linux and Windows), checked against Ollama's published checksum, plus the model (2 to 18 GB, see below). If you already have Ollama it uses that instead. Downloads happen once. |
| **2. An online model service** | Any service with the common "OpenAI-compatible" chat interface: you give a web address, a model name and your key. | The key is saved in a file only you can read. |
| **3. Claude Desktop or Claude Code** | Connects the tools to an AI app you already use ([details](mcp.md#use-it-from-an-mcp-client)). | It edits that app's settings file only after you say yes, and keeps a backup. |
| **4. Skip** | No chat. | Every other command still works. |

A model on a computer without a graphics card can take a minute or more per answer. On a Mac, running Ollama directly (which setup
does) uses the Mac's graphics chip and is much faster than running it inside Docker.

## Where everything lives, updating, uninstalling

The installer puts **everything** in one folder, by default `~/vmd-agent`: the helper tool, Python, the program and its packages
(including ffmpeg), your settings, and, if you choose a free local model, a private copy of Ollama and its models. It uses no
administrator rights, installs nothing system-wide and does not edit your shell's startup files. Your own data folder
(`~/vmd-agent-data`) and VMD itself are separate and are never touched. **Update:** run the install line again. **Uninstall:** delete
the `~/vmd-agent` folder. (If you used Docker, `vmd-agent start --down` stops it and `docker compose down -v` removes its model
volume.)

## Other ways to install

* **You already use Python:** `pip install "vmd-agent[server] @ https://github.com/OmidMLdata/AGENTIC_VMD_v2/archive/refs/heads/main.zip"`,
  then `vmd-agent setup`. The packages are listed once, in [`pyproject.toml`](../pyproject.toml) (`[all]` adds the optional ones).
* **From a downloaded copy:** run `./install.sh` (Mac/Linux) or `install.ps1` (Windows) from inside the folder; it installs that copy.
* **Docker (advanced):** `vmd-agent start` picks native or Docker from the facts about your computer and starts the chat
  (`--print-plan` shows what it would do, `--down` stops the containers). Docker cannot run a Mac or Windows VMD (it needs VMD's
  **Linux** build in `docker/vmd-dist/`) and on a Mac cannot use the Mac's graphics chip. See [Docker](docker.md#docker).
* **An MCP client** (Claude Code, Claude Desktop, others): [Use it from an MCP client](mcp.md#use-it-from-an-mcp-client).

## If something goes wrong

| What you see | What to do |
|---|---|
| `vmd-agent: command not found` | use the full path `~/vmd-agent/bin/vmd-agent` (the installer does not change your PATH on purpose), or run the install line again |
| the model answers without looking at your files, or ignores its tools | the model is too small, or its context is too short: use `granite4.1:8b` or larger, and if you run your own Ollama set `OLLAMA_CONTEXT_LENGTH=16384` |
| "cannot reach the model server" | run `vmd-agent setup` again (it starts it); if you use your own Ollama, start it. `vmd-agent setup --check` shows what is reachable. |
| "VMD was found but did not run" | the message names the likely cause (for example Linux needs `tcsh`: `sudo apt install tcsh`). `vmd-agent doctor` repeats it. |
| It cannot find VMD | `vmd-agent setup --vmd "<VMD's folder>"`. VMD is optional: without it, pictures use the built-in drawing. |
| "outside the allowed roots" | the AI can only use your files folder; put the file there, or choose another with `vmd-agent setup --data-dir` |
| the model's answers are poor or wrong | a small model may be the cause: try a larger one (`vmd-agent setup`, option 1) or an online model. `vmd-agent claims` checks any statement against the data. |
| anything else | run `vmd-agent doctor` and read its notes |
