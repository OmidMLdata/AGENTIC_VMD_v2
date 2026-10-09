"""``vmd-agent setup`` and the menu you get from plain ``vmd-agent``.

Written for someone who knows what VMD does but has never touched code: it explains each
step in ordinary words, finds things by itself, asks only what it cannot work out, remembers
the answers (:mod:`vmd_agent.settings`), and never shows a stack trace. It installs
nothing without asking, and says exactly what it is about to run.

All input and output go through a small ``IO`` object so the conversation can be tested.

Run end to end on macOS (Apple Silicon) with the private Ollama: install, start, model download and chat.
Not run: Linux, Windows, Docker, or registering with Claude Desktop or Claude Code. The decisions and the file writes are tested.
"""
from __future__ import annotations

import os
import re
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
    if not settings.get("vmd_page_offered") and io.confirm("  Open VMD's download page in your browser? (You download and install it yourself; "
                                                           "then run `vmd-agent setup` again and I will find it.)", False):
        try:
            webbrowser.open(VMD_SITE)
        except Exception:
            pass
    settings.save(vmd_page_offered=True)                       # asked once; never again, and never opened without a yes
    io.say("  Later: install VMD, then run `vmd-agent setup` (or `vmd-agent setup --vmd /path/to/VMD` if it is somewhere unusual).")
    return None


def _server_running() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", ollama_local.port()), timeout=0.5):
            return True
    except OSError:
        return False


def _offer_move(io: IO, dst: str, assume_yes: bool) -> None:
    """Offer to move the model server and models (and the settings) from the old place into ``dst``."""
    src = settings.previous_home()
    items = settings.movable(src, dst)
    if not items:
        return
    size = ""
    if "ollama" in items:
        try:
            total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _d, fs in os.walk(os.path.join(src, "ollama")) for f in fs if os.path.isfile(os.path.join(dp, f)))
            size = f" ({total / 1e9:.1f} GB)"
        except OSError:
            pass
    io.say(f"  Found earlier data in {src}: {', '.join(items)}{size}.")
    if "ollama" in items and _server_running():
        io.say("  The private model server is running; stop it (or close the chat page) and run  vmd-agent setup --home here  again to move it. Skipped.")
        items = [i for i in items if i != "ollama"]
    if items and (assume_yes or io.confirm("  Move it into the working folder? (a rename on the same disk, so instant; nothing is copied or lost)", True)):
        moved = settings.move_data(src, dst)
        io.say(f"  Moved: {', '.join(moved)}." if moved else "  Nothing moved.")


def step_home(io: IO, where: Optional[str] = None, assume_yes: bool = False) -> str:
    """Where vmd-agent keeps its own data. ``where`` is 'here' (a .vmd-agent folder in this folder) or 'user'
    (the installer's or per-user folder); None asks. Returns the folder in use. Earlier data is moved only if you agree."""
    if os.environ.get(settings.ENV_HOME) or os.environ.get(settings.ENV_DIR):
        io.say(f"\nvmd-agent's own data folder was chosen by the environment: {settings.home_dir()}")
        return settings.home_dir()
    existing = settings.local_home()
    here = os.path.join(os.getcwd(), settings.LOCAL)
    if not existing:
        if where is None and os.path.realpath(os.getcwd()) == os.path.realpath(os.path.expanduser("~")):
            where = "user"                                   # a hidden folder in your home directory helps nobody: keep it with the install
            io.say(f"\nvmd-agent keeps its own data in {settings.home_dir()}. (To keep it inside a project instead, open a terminal in that folder and run  vmd-agent setup --home here .)")
        if where is None:
            if assume_yes:
                where = "user"
            else:
                io.say("\nWhere should vmd-agent keep its own data (your settings, the link to your VMD window, and the free model if you use one)?")
                installer = bool(os.environ.get(settings.ENV_INSTALL))
                pick = io.choose("  Choose one", [f"In this folder: {here} (delete or move the folder and everything goes with it; the model needs a few GB here)",
                                                  f"In one place for your whole account: {settings.previous_home()}"], default=2 if installer else 1)
                where = "here" if pick == 1 else "user"
        if where != "here":
            io.say(f"  vmd-agent keeps its own data in {settings.home_dir()}.")
            return settings.home_dir()
        before = settings.load()                           # carry earlier choices over
        existing = settings.make_local(os.getcwd())
        if before and not settings.load():
            settings.save(**{k: v for k, v in before.items() if k in settings.KEYS})
        io.say(f"  vmd-agent keeps its own data in {existing} (Git ignores it).")
    else:
        io.say(f"\nvmd-agent keeps its own data in {existing} (it belongs to this working folder).")
    _offer_move(io, os.path.realpath(existing), assume_yes and where == "here")
    return existing


def step_data_dir(io: IO, data_dir: Optional[str] = None, assume_yes: bool = False) -> str:
    io.say("\nStep 2 of 4: Your files")
    io.say("  Put your structures and trajectories (PDB, PSF, DCD, XTC ...) in one folder. The AI "
           "can only see that folder, nothing else on your computer.")
    local = settings.local_home()
    default = data_dir or settings.get("data_dir") or (os.path.dirname(local) if local else DEFAULT_DATA)
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
    if not assume_yes and io.confirm("  Open that page in your browser now?", False):
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
        ram, gpu_name, vram = P.memory_gb(system_name), P.nvidia_gpu(), P.nvidia_vram_gb()
        gpu = bool(gpu_name)
        io.say("  This computer: " + models.describe_device(ram, gpu_name, vram, apple_silicon=(P.system(system_name) == P.MACOS and P.arch() == "arm64")) + ".")
        fits = {a["tag"]: a["fit"] for a in models.advise(ram, vram)}
        note = {"fits": "fits this computer", "tight": "tight for this computer", "too big": "too big for this computer", "unknown": ""}
        labels = [f"{m.tag}: {m.label}, download {m.gb:.1f} GB; suits {m.suits}; {m.licence}" + (f" [{note[fits[m.tag]]}]" if note[fits[m.tag]] else "")
                  for m in models.CATALOGUE]
        labels.append("I know the model name I want")
        suggested = models.recommend(ram, gpu and bool(vram is None or vram >= models.by_tag()[models.DEFAULT_MODEL].min_vram_gb))
        if suggested is None:
            io.say(f"  This computer has {ram} GB of memory, which is little for a model that can use tools. The smallest one below may be slow or fail;")
            io.say("  an online service (setup option 2) or Claude (option 3) is the easier route.")
            suggested = models.CATALOGUE[0]
        else:
            io.say(f"  For this computer ({f'{ram} GB of memory' if ram else 'memory not read'}{', NVIDIA graphics card' if gpu else ''}) "
                   f"the suggestion is {suggested.tag}.")
        default = 1 + [m.tag for m in models.CATALOGUE].index(suggested.tag)
        pick = default if assume_yes else io.choose("  Which one?", labels, default=default)
        model = (models.CATALOGUE[pick - 1].tag if pick <= len(models.CATALOGUE)
                 else io.ask("  Model name (as in the Ollama library, e.g. granite4.1:8b)"))
    private = ollama_local.find_binary() is not None or not shutil.which("ollama")
    url = ollama_local.url() if private else DEFAULT_URL
    settings.save(llm_url=url, llm_model=model, llm_key=None,
                  ollama_mode="private" if private else "system")
    if not _have_ollama() and not _install_ollama(io, system_name, assume_yes):
        io.say(f"  I saved your choice ({model}); it will be used once Ollama is installed.")
        io.say(f"  Change your mind any time: run  vmd-agent models --install {model}  or use the Model button in the web page (vmd-agent ui).")
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
    size = f" ({found['gb']} GB)" if found.get("gb") else ""
    if not (assume_yes or io.confirm(f"  Download {model}{size} now? It happens once and needs the window kept open.", True)):
        io.say(f"  Not downloaded. Your choice ({model}) is saved. Download it whenever you like:  vmd-agent models --install {model}")
        io.say("  or use the Model button in the web page (vmd-agent ui).")
        return False
    io.say(f"  Downloading {model}. Please keep this window open.")
    ok = ollama_local.pull(model) if private else _run(["ollama", "pull", model]).returncode == 0
    if not ok:
        io.say(f"  The download failed. Check your internet connection and the name '{model}', then try again:  vmd-agent models --install {model}")
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
    """Let Claude Desktop / Claude Code (any MCP client) be the assistant: they do the thinking, vmd-agent supplies the tools."""
    from vmd_agent import mcp_check
    cfg = mcp_check.build_mcp_config(roots=[data_dir], system_name=system_name)
    io.say("\n  Claude Code or Claude Desktop will do the thinking, and vmd-agent will be one of their tools (through a standard called MCP).")
    io.say("  The chat and the web page of vmd-agent itself still need a model of their own; you can add one later (vmd-agent models --install, or Model in the web page).")
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
def _saved_online_service() -> Optional[str]:
    """The address of an online (not on this computer) model service the user has already saved, if any."""
    url = settings.get("llm_url")
    if url and not re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])", url):
        return url
    return None


def assistant_choices() -> tuple:
    """The choices for who answers, and the one to offer first: the free local model, unless the user already has an online service saved.
    Claude Code or Desktop is an alternative to a model here, never an extra step on top of one."""
    online = _saved_online_service()
    found = shutil.which("claude") is not None or bool(P.claude_desktop_config_path() and os.path.isdir(os.path.dirname(P.claude_desktop_config_path())))
    labels = ["A free open-source model on this computer (recommended: works offline, nothing leaves your computer)",
              "An online model service" + (f" (you already saved one: {online})" if online else " (you need its web address, a model name and usually an API key)"),
              "Claude Code or Claude Desktop does the thinking instead; vmd-agent only supplies the tools" + (" (found on this computer)" if found else ""),
              "Skip for now (the commands still work without a chat)"]
    return labels, (2 if online else 1)


def setup(io: Optional[IO] = None, assume_yes: bool = False, check_only: bool = False,
          data_dir: Optional[str] = None, vmd: Optional[str] = None,
          model_choice: Optional[int] = None, model: Optional[str] = None,
          system_name: Optional[str] = None, home: Optional[str] = None) -> int:
    """The guided setup. Returns a process exit code (0 = finished)."""
    io = io or IO()
    sysname = P.system(system_name)
    if check_only:
        return show_status(io)
    io.say("Welcome to vmd-agent.")
    ram = P.memory_gb(sysname)
    io.say(f"This computer: {sysname}, {P.arch()}" + (f", {ram} GB of memory" if ram else "") + ".")
    io.say("It lets you ask questions about your molecular structures and simulations in plain "
           "language, and works out the answers with real measurements. This takes a few minutes, "
           "asks a few questions, and installs nothing without asking you.")
    step_home(io, home, assume_yes)
    step_vmd(io, vmd, assume_yes)
    folder = step_data_dir(io, data_dir, assume_yes)

    io.say("\nStep 3 of 4: Who will you talk to?")
    labels, default = assistant_choices()
    pick = model_choice or (default if assume_yes else io.choose("  Choose one", labels, default=default))
    ready = False
    if pick == 1:
        ready = setup_local_model(io, sysname, model, assume_yes)
    elif pick == 2:
        ready = setup_online_model(io)
        if not ready and (assume_yes or io.confirm("  No online service was set up. Use the free model on this computer instead?", True)):
            pick = 1
            ready = setup_local_model(io, sysname, model, assume_yes)
    elif pick == 3:
        ready = setup_ai_app(io, folder, assume_yes, sysname)
    else:
        io.say("  Skipped.")

    io.say("\nStep 4 of 4: Finishing")
    settings.save(setup_done=True)
    io.say(f"  Your choices are saved ({settings.path()}).")
    io.say("\nAll set. From now on just type:   vmd-agent        (or  vmd-agent ui  for the web page)")
    if pick in (1, 2) and not ready:
        io.say("(The chat needs the model above to be ready first. To get it later: vmd-agent models --install, or Model in the web page. Everything else works already.)")
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
                    args = ["tool", "visualize_and_interpret", _in_data(what)] + ([_in_data(traj)] if traj else []) + ["--out", out_dir]
                    run_cli(args)
                else:
                    from vmd_agent import toolset
                    got = toolset.TOOLS["fetch_structure"](what.upper(), out_dir=out_dir)
                    if not got.get("ok"):
                        io.say(f"Could not fetch {what.upper()}: {got.get('error')}")
                        continue
                    run_cli(["tool", "visualize_and_interpret", got["path"], "--out", out_dir])
            elif pick == 4:
                top = io.ask("Structure file (PDB, PSF ...)")
                trj = io.ask("Trajectory file (DCD, XTC ...)")
                if not top or not trj:
                    continue
                what = io.ask("What to measure (rmsd rmsf rgyr contacts hbonds sasa convergence)", "rmsd rgyr")
                run_cli(["tool", "analyze_trajectory", _in_data(top), _in_data(trj), "--analyses"] + what.split())
            elif pick == 5:
                top = io.ask("Structure file")
                claim = io.ask("A statement to check (e.g. It has 4 disulfide bridges)")
                if top and claim:
                    run_cli(["tool", "verify_claims", _in_data(top), claim])
            elif pick == 6:
                show_status(io)
            elif pick == 7:
                setup(io)
            else:
                return 0
        except SystemExit as e:
            if e.code == 130:                                 # Ctrl-C / end of input
                return 130
            continue
        except Exception as e:                                # never show a traceback here
            io.say(f"Something went wrong: {e}")
