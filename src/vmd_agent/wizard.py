"""``vmd-agent setup`` and the menu you get from plain ``vmd-agent``.

Written for someone who knows what VMD does but has never touched code: it explains each
step in ordinary words, finds things by itself, asks only what it cannot work out, remembers
the answers (:mod:`vmd_agent.settings`), and never shows a stack trace. It installs
nothing without asking, and says exactly what it is about to run.

All input and output go through a small ``IO`` object so the conversation can be tested.

Never run end to end against Ollama, Docker, Claude Desktop or Claude Code: none was
available where this was written. The decisions and the file writes are tested.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import webbrowser
from typing import Callable, List, Optional, Sequence

from vmd_agent import models, ollama_local, platform_info as P
from vmd_agent import settings

DEFAULT_DATA = os.path.join("~", "vmd-agent-data")

OLLAMA_SITE = "https://ollama.com/download"
VMD_SITE = "https://www.ks.uiuc.edu/Research/vmd/"


# --------------------------------------------------------------------- the IO
class IO:
    """Talks to the person at the keyboard."""

    def say(self, msg: str = "") -> None:
        print(msg, flush=True)

    def ask(self, prompt: str, default: Optional[str] = None) -> str:
        suffix = f" [{default}]" if default else ""
        try:
            ans = input(f"{prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(130)
        return ans or (default or "")

    def secret(self, prompt: str) -> str:
        import getpass
        try:
            return getpass.getpass(f"{prompt} (typing is hidden): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(130)

    def confirm(self, prompt: str, default: bool = True) -> bool:
        hint = "Y/n" if default else "y/N"
        ans = self.ask(f"{prompt} ({hint})").lower()
        return default if not ans else ans.startswith("y")

    def choose(self, prompt: str, options: Sequence[str], default: int = 1) -> int:
        """Ask for one of ``options`` by number; returns the 1-based number."""
        for i, o in enumerate(options, 1):
            self.say(f"  {i}. {o}")
        while True:
            ans = self.ask(prompt, str(default))
            if ans.isdigit() and 1 <= int(ans) <= len(options):
                return int(ans)
            self.say(f"  Please type a number from 1 to {len(options)}.")


def _run(argv: List[str], capture: bool = False):
    try:
        return subprocess.run(argv, text=True, capture_output=capture)
    except (OSError, subprocess.SubprocessError) as e:        # missing program etc.
        return subprocess.CompletedProcess(argv, 127, "", str(e))


# ------------------------------------------------------------------- the steps
def _check_vmd_works(io: IO, vmd: str) -> bool:
    """Run VMD headless once and say plainly whether it works."""
    from vmd_agent.environment import vmd_self_test
    io.say("  Checking that it starts (this runs VMD once, without a window)...")
    r = vmd_self_test(vmd)
    if r["ok"]:
        io.say(f"  It works. {r['version_note']}")
        return True
    io.say("  It was found but did not run: " + str(r["problem"]))
    io.say("  " + str(r["advice"]))
    return False


def step_vmd(io: IO, vmd_hint: Optional[str] = None, assume_yes: bool = False) -> Optional[str]:
    """Find VMD, or ask where it is. Returns its path, or None if there is none."""
    from vmd_agent.environment import find_tachyon, find_vmd
    io.say("\nStep 1 of 4: VMD")
    found = find_vmd(vmd_hint)
    if found:
        t = find_tachyon(found)
        io.say(f"  Found VMD: {found}")
        if not t:
            io.say("  (Its ray tracer, Tachyon, was not found next to it, so high-quality "
                   "pictures may not work; the built-in drawing still does.)")
        settings.save(vmd_path=found)
        _check_vmd_works(io, found)
        return found
    io.say("  I could not find VMD on this computer.")
    io.say("  That is fine: everything works without it, with simpler built-in pictures. "
           f"VMD is free from {VMD_SITE} . Get a 1.9.x release: that is the series this toolkit was "
           "written for (1.9.4a57 on macOS is the only build it has been tested with).")
    if assume_yes:
        return None
    where = io.ask("  If VMD is installed, type the folder it is in (or press Enter to skip)", "")
    if where:
        where = os.path.expanduser(where.strip().strip('"'))
        found = find_vmd(where)
        if found:
            io.say(f"  Found VMD: {found}")
            settings.save(vmd_path=found)
            _check_vmd_works(io, found)
            return found
        io.say(f"  I could not find a VMD program in '{where}'. Skipping; you can run setup again later.")
    if io.confirm("  Open VMD's download page in your browser? (You download and install it yourself; "
                  "then run `vmd-agent setup` again and I will find it.)", True):
        try:
            webbrowser.open(VMD_SITE)
        except Exception:
            pass
    return None


def step_data_dir(io: IO, data_dir: Optional[str] = None, assume_yes: bool = False) -> str:
    io.say("\nStep 2 of 4: Your files")
    io.say("  Put your structures and trajectories (PDB, PSF, DCD, XTC ...) in one folder. The AI "
           "can only see that folder, nothing else on your computer.")
    default = data_dir or settings.get("data_dir") or DEFAULT_DATA
    chosen = default if assume_yes else io.ask("  Which folder?", default)
    folder = os.path.abspath(os.path.expanduser(chosen))
    os.makedirs(folder, exist_ok=True)
    settings.save(data_dir=folder)
    io.say(f"  Using: {folder}")
    return folder


def _have_ollama() -> bool:
    """Some Ollama we can use: the private copy, or one already on this computer."""
    return ollama_local.find_binary() is not None or shutil.which("ollama") is not None


def _install_ollama(io: IO, system_name: str, assume_yes: bool) -> bool:
    """Offer to put a private copy of Ollama inside the vmd-agent folder (nothing system-wide,
    no administrator rights). True if there is a usable Ollama afterwards."""
    folder = ollama_local.ollama_dir()
    io.say("  Ollama is the free program that runs the model on your computer. It is not installed.")
    io.say(f"  I can keep a private copy inside {folder}: nothing is installed system-wide, no")
    io.say("  administrator rights are used, and deleting that folder removes it again.")

    try:
        name = ollama_local.asset_name(system_name)
    except ValueError:
        name = ""
    gb = ollama_local.APPROX_GB.get(name)
    size = f"about {gb:.1f} GB" if gb else "a large file"
    if assume_yes or io.confirm(f"  Download it now from Ollama's GitHub releases ({size}) "
                                "and keep it in that folder?"):
        try:
            ollama_local.install(progress=None)
            io.say("  Installed (privately).")
            return True
        except (RuntimeError, OSError, ValueError) as e:
            io.say(f"  I could not do that: {str(e)[:200]}")
    else:
        io.say("  Not downloaded.")
    io.say("  You can install Ollama yourself instead:")
    io.say(f"    1. Go to {OLLAMA_SITE} and download the installer for your computer.")
    io.say("    2. Run it, then come back and run `vmd-agent setup` again.")
    if not assume_yes and io.confirm("  Open that page in your browser now?", True):
        try:
            webbrowser.open(OLLAMA_SITE)
        except Exception:
            pass
    return False


def _start_model_server(io: IO, url: str) -> bool:
    """Make sure a model server answers at ``url``; start the private (or system) Ollama if not."""
    from vmd_agent.llm_client import LLMError, list_models
    try:
        list_models(url, timeout=3)
        return True
    except LLMError:
        pass
    io.say("  Starting the model server (Ollama)...")
    if ollama_local.find_binary():
        return ollama_local.start()
    if not shutil.which("ollama"):
        return False
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    for _ in range(15):
        time.sleep(1)
        try:
            list_models(url, timeout=3)
            return True
        except LLMError:
            continue
    return False


def setup_local_model(io: IO, system_name: str, model: Optional[str] = None,
                      assume_yes: bool = False) -> bool:
    """Set up a free open-source model on this computer. True if it is ready to use."""
    from vmd_agent.agent import DEFAULT_URL
    from vmd_agent.llm_client import LLMError, list_models
    io.say("\n  A free, open-source model that runs on your computer, so your data never leaves it.")
    io.say(f"  As of {models.MODELS_CHECKED} these exist in the Ollama library and can call tools. Only granite4.1:8b")
    io.say("  and granite4.1:3b were run with this toolkit (the 3B often misreads results); licences differ.")
    if not model:
        io.say("  Pick a size (bigger is smarter but slower and needs more memory):")
        labels = [f"{m.tag}: {m.label}, download {m.gb:.1f} GB; suits {m.suits}; {m.licence}"
                  for m in models.CATALOGUE]
        labels.append("I know the model name I want")
        default = 1 + [m.tag for m in models.CATALOGUE].index(models.DEFAULT_MODEL)
        pick = default if assume_yes else io.choose("  Which one?", labels, default=default)
        model = (models.CATALOGUE[pick - 1].tag if pick <= len(models.CATALOGUE)
                 else io.ask("  Model name (as in the Ollama library, e.g. granite4.1:8b)"))
    private = ollama_local.find_binary() is not None or not shutil.which("ollama")
    url = ollama_local.url() if private else DEFAULT_URL
    settings.save(llm_url=url, llm_model=model, llm_key=None,
                  ollama_mode="private" if private else "system")
    if not _have_ollama() and not _install_ollama(io, system_name, assume_yes):
        io.say(f"  I saved your choice ({model}); it will be used once Ollama is installed.")
        return False
    private = ollama_local.find_binary() is not None
    url = ollama_local.url() if private else DEFAULT_URL
    settings.save(llm_url=url, ollama_mode="private" if private else "system")
    if not _start_model_server(io, url):
        io.say("  I could not reach the model server. Run `vmd-agent setup` again; if it keeps "
               "failing, run `vmd-agent doctor`.")
        return False
    try:
        have = list_models(url)
    except LLMError:
        have = []
    if model in have:
        io.say(f"  The model {model} is already downloaded.")
        return True
    found = models.check(model)
    if found["exists"] is False:
        io.say(f"  The Ollama library has no model called '{model}' (it may have been renamed). "
               "Run `vmd-agent models` to see the current suggestions.")
        return False
    if found["exists"] is None:
        io.say("  I could not reach the Ollama library to confirm the name; trying anyway.")
    elif found["gb"]:
        io.say(f"  The library confirms {model} exists ({found['gb']} GB).")
    io.say(f"  Downloading {model}. This is large and happens only once; please keep this window open.")
    ok = ollama_local.pull(model) if private else _run(["ollama", "pull", model]).returncode == 0
    if not ok:
        io.say(f"  The download failed. Check your internet connection and the name '{model}', then run setup again.")
        return False
    io.say("  Done.")
    return True


def setup_online_model(io: IO, url: Optional[str] = None, model: Optional[str] = None,
                       key: Optional[str] = None) -> bool:
    """Use any online service that speaks the common (OpenAI-style) chat format."""
    from vmd_agent.llm_client import LLMError, list_models
    io.say("\n  Any online model service that offers the common 'OpenAI-compatible' chat API will work.")
    url = url or io.ask("  Its web address (it usually ends in /v1)")
    model = model or io.ask("  The model name")
    key = key if key is not None else io.secret("  Your API key (leave empty if it needs none)")
    if not url or not model:
        io.say("  I need both a web address and a model name. Nothing was saved.")
        return False
    settings.save(llm_url=url.rstrip("/"), llm_model=model, llm_key=key or None)
    io.say(f"  Saved. The key is stored in {settings.path()}, readable only by you.")
    try:
        list_models(url, key or None, timeout=10)
        io.say("  I could reach that service.")
    except LLMError as e:
        io.say(f"  Note: I could not confirm it works yet ({str(e)[:120]}). Check the address and key.")
    return True


def setup_ai_app(io: IO, data_dir: str, assume_yes: bool = False,
                 system_name: Optional[str] = None) -> bool:
    """Connect the toolkit to Claude Desktop / Claude Code (any MCP client)."""
    from vmd_agent import mcp_check
    cfg = mcp_check.build_mcp_config(roots=[data_dir], system_name=system_name)
    io.say("\n  This connects the tools to an AI app you already use (through a standard called MCP).")
    path = cfg["claude_desktop_config"]
    done = False
    if path and (assume_yes or io.confirm(f"  Add it to Claude Desktop's settings now? ({path})")):
        try:
            backup = mcp_check.write_claude_desktop_config(path, cfg["config"])
            io.say("  Done. Restart Claude Desktop. "
                   + (f"(Your old settings were copied to {backup}.)" if backup else ""))
            done = True
        except (ValueError, OSError) as e:
            io.say(f"  I could not change that file: {e}")
    if shutil.which("claude"):
        cmd = cfg["claude_code_command"]
        if assume_yes or io.confirm("  Add it to Claude Code too? I would run: " + " ".join(cmd), default=False):
            done = (_run(cmd).returncode == 0) or done
    elif not done:
        io.say("  Paste this into your AI app's MCP settings:")
        import json
        io.say(json.dumps(cfg["config"], indent=2))
    return done


# ---------------------------------------------------------------- the whole setup
MODEL_CHOICES = ["A free open-source model on this computer (recommended; works offline)",
                 "An online model service I already have access to",
                 "I already use Claude Desktop or Claude Code: connect the tools to it",
                 "Skip for now (the commands still work without a chat)"]


def setup(io: Optional[IO] = None, assume_yes: bool = False, check_only: bool = False,
          data_dir: Optional[str] = None, vmd: Optional[str] = None,
          model_choice: Optional[int] = None, model: Optional[str] = None,
          system_name: Optional[str] = None) -> int:
    """The guided setup. Returns a process exit code (0 = finished)."""
    io = io or IO()
    sysname = P.system(system_name)
    if check_only:
        return show_status(io)
    io.say("Welcome to vmd-agent.")
    io.say("It lets you ask questions about your molecular structures and simulations in plain "
           "language, and works out the answers with real measurements. This takes a few minutes, "
           "asks a few questions, and installs nothing without asking you.")
    step_vmd(io, vmd, assume_yes)
    folder = step_data_dir(io, data_dir, assume_yes)

    io.say("\nStep 3 of 4: Who will you talk to?")
    pick = model_choice or (1 if assume_yes else io.choose("  Choose one", MODEL_CHOICES, default=1))
    ready = False
    if pick == 1:
        ready = setup_local_model(io, sysname, model, assume_yes)
    elif pick == 2:
        ready = setup_online_model(io)
    elif pick == 3:
        ready = setup_ai_app(io, folder, assume_yes, sysname)
    else:
        io.say("  Skipped.")

    io.say("\nStep 4 of 4: Finishing")
    settings.save(setup_done=True)
    io.say(f"  Your choices are saved ({settings.path()}).")
    io.say("\nAll set. From now on just type:   vmd-agent        (or  vmd-agent ui  for the web page)")
    if pick in (1, 2) and not ready:
        io.say("(The chat needs the model above to be ready first; the other features work already.)")
    if not assume_yes and io.confirm("\nOpen the web page now? (your files, the chat and whole jobs, in your browser; Ctrl+C in this window stops it)", True):
        from vmd_agent import cli
        cli.main(["ui"])
    return 0


def show_status(io: Optional[IO] = None) -> int:
    """What is configured, and whether it works. Changes nothing."""
    from vmd_agent.environment import find_vmd
    from vmd_agent.llm_client import LLMError, list_models
    io = io or IO()
    s = settings.describe()
    io.say("Your vmd-agent settings:")
    io.say(f"  Files folder : {s.get('data_dir', '(not chosen: run vmd-agent setup)')}")
    vmd = find_vmd()
    io.say(f"  VMD          : {vmd or 'not found (built-in pictures are used)'}")
    url, model = s.get("llm_url"), s.get("llm_model")
    if url:
        try:
            have = list_models(url, settings.get("llm_key"), timeout=4)
            state = "reachable" if (not have or model in have) else f"reachable, but '{model}' is not installed there"
        except LLMError:
            state = "NOT reachable (is the model server running?)"
        io.say(f"  Chat model   : {model} at {url}: {state}")
    else:
        io.say("  Chat model   : not chosen")
    io.say(f"  Settings file: {settings.path()}")
    return 0


# ---------------------------------------------------------------------- the menu
def _in_data(path: str) -> str:
    """A name typed by the user, resolved inside their files folder if it is relative."""
    p = os.path.expanduser(path.strip().strip('"'))
    if os.path.isabs(p) or os.path.exists(p):
        return p
    base = settings.get("data_dir")
    return os.path.join(base, p) if base else p


MENU = ["The web page: my files, the chat, whole jobs and pictures in one browser window (recommended)",
        "Chat: ask questions about my files, or ask it to run VMD for you (measure, build a system, export a scene)",
        "Look at a structure (a PDB ID like 1UBQ, or one of my files): pictures and a description",
        "Analyse a simulation: RMSD, flexibility, size, contacts ...",
        "Check statements about a structure against its data",
        "Connect the tools to Claude Desktop or Claude Code",
        "Show my settings and check everything works",
        "Run the setup again",
        "Quit"]


def menu(io: Optional[IO] = None, run_cli: Optional[Callable[[List[str]], int]] = None) -> int:
    """The friendly front door: type ``vmd-agent`` and pick what you want."""
    io = io or IO()
    if run_cli is None:
        from vmd_agent import cli
        run_cli = cli.main
    if not settings.get("setup_done"):
        io.say("Welcome to vmd-agent. It looks like this is your first time.")
        if io.confirm("Run the short setup now?", True):
            setup(io)
    out_dir = os.path.join(settings.get("data_dir") or ".", "vmd_agent_output")
    while True:
        io.say("\nWhat would you like to do?")
        pick = io.choose("Type a number", MENU, default=1)
        try:
            if pick == 1:
                run_cli(["ui"])
            elif pick == 2:
                run_cli(["chat"])
            elif pick == 3:
                what = io.ask("A PDB ID (like 1UBQ) or the name of a file in your folder")
                if not what:
                    continue
                if os.path.exists(_in_data(what)) or "." in what:
                    traj = io.ask("A trajectory file to go with it (Enter for none)", "")
                    args = ["visualize", _in_data(what), "--out-dir", out_dir]
                    if traj:
                        args += ["--traj", _in_data(traj)]
                    run_cli(args)
                else:
                    run_cli(["show", what.upper(), "--out-dir", out_dir])
            elif pick == 4:
                top = io.ask("Structure file (PDB, PSF ...)")
                trj = io.ask("Trajectory file (DCD, XTC ...)")
                if not top or not trj:
                    continue
                what = io.ask("What to measure (rmsd rmsf rgyr contacts hbonds sasa convergence)", "rmsd rgyr")
                run_cli(["analyze", _in_data(top), _in_data(trj), "--do"] + what.split())
            elif pick == 5:
                top = io.ask("Structure file")
                claim = io.ask("A statement to check (e.g. It has 4 disulfide bridges)")
                if top and claim:
                    run_cli(["claims", _in_data(top), claim])
            elif pick == 6:
                setup_ai_app(io, settings.get("data_dir") or os.getcwd())
            elif pick == 7:
                show_status(io)
            elif pick == 8:
                setup(io)
            else:
                return 0
        except SystemExit as e:
            if e.code == 130:                                 # Ctrl-C / end of input
                return 130
            continue
        except Exception as e:                                # never show a traceback here
            io.say(f"Something went wrong: {e}")
