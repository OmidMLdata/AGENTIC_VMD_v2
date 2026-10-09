"""``vmd-agent start`` and ``vmd-agent doctor``: work out what this computer can do and
run the chat the right way for it.

The decision is made from facts about the machine (:mod:`vmd_agent.platform_info`):

* **native**: run the chat in this Python against a model server on this computer
  (Ollama and friends). This can use your own VMD and, on a Mac, the Mac's GPU.
* **docker**: run a model server and the chat in containers (the ``docker/chat.compose.yml``
  stack). Needs only Docker; VMD can be used only if you supply a *Linux* build.

``auto`` picks native on macOS and Windows when a model server is installed (a Mac's or
Windows' VMD cannot run in Docker, and Docker on a Mac cannot use its GPU), and Docker
otherwise when it is ready. Every decision is returned as data, and ``--print-plan``
shows it without running anything.

Never run end to end: the Docker path needs Docker and the native path a model server,
neither of which was available where this was written.
"""
from __future__ import annotations

import glob
import os
import subprocess
import time
from typing import Callable, Dict, List, Optional

from vmd_agent import models, ollama_local, platform_info as P

DEFAULT_MODEL = models.DEFAULT_MODEL
COMPOSE = os.path.join("docker", "chat.compose.yml")
GPU_OVERRIDE = os.path.join("docker", "chat.gpu.yml")


# -------------------------------------------------------------------- locating
def find_repo(start: Optional[str] = None) -> Optional[str]:
    """The checkout that holds ``docker/chat.compose.yml``, searching upward from
    ``start`` (default: the current directory, then this package)."""
    for base in ([start] if start else [os.getcwd(), os.path.dirname(__file__)]):
        d = os.path.abspath(base)
        while True:
            if os.path.exists(os.path.join(d, COMPOSE)):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return None


def vmd_tarball(repo: str) -> Optional[str]:
    """A Linux VMD tarball the user placed in ``docker/vmd-dist/``, if any."""
    for pat in ("vmd*.tar.gz", "vmd*.tgz", "vmd*.tar.Z"):
        hits = sorted(glob.glob(os.path.join(repo, "docker", "vmd-dist", pat)))
        if hits:
            return hits[0]
    return None


def compose_data_dir(path: str, system_name: Optional[str] = None) -> str:
    """The data folder as Docker Compose wants it: forward slashes on Windows
    (``C:\\Users\\me\\data`` -> ``C:/Users/me/data``)."""
    if P.system(system_name) == P.WINDOWS:
        return os.path.abspath(path).replace("\\", "/") if os.name == "nt" \
            else path.replace("\\", "/")
    return os.path.abspath(path)


# ------------------------------------------------------------------- the plan
def make_plan(info: Dict[str, object], model: str = DEFAULT_MODEL,
              data_dir: str = "data", repo: Optional[str] = None,
              mode: str = "auto", docker: str = "docker",
              tarball: Optional[str] = None,
              model_server_up: bool = False) -> dict:
    """Decide how to run on this machine.

    ``info`` is :func:`vmd_agent.platform_info.detect`. Returns ``{"mode", "reason",
    "problems", "notes", "commands", "env"}``; ``problems`` non-empty means it cannot
    run and ``notes`` explain choices. Pure: nothing is run or changed here."""
    sysname = str(info["system"])
    d: dict = info["docker"]                                   # type: ignore[assignment]
    docker_ready = bool(d.get("installed") and d.get("running") and d.get("compose"))
    native_ready = bool(info.get("ollama") or model_server_up)
    notes: List[str] = []
    problems: List[str] = []

    if mode not in ("auto", "docker", "native"):
        raise ValueError("mode must be auto, docker or native")
    chosen, reason = mode, "you asked for it"
    if mode == "auto":
        desktop = sysname in (P.MACOS, P.WINDOWS)
        if desktop and native_ready:
            chosen, reason = "native", (
                f"on {sysname} your own VMD cannot run in Docker"
                + (" and Docker cannot use the Mac's GPU" if sysname == P.MACOS
                   else "") + ", and a model server is available here")
        elif docker_ready:
            chosen, reason = "docker", "Docker is ready, so everything runs in containers"
        elif native_ready:
            chosen, reason = "native", "Docker is not ready but a model server is available"
        else:
            chosen, reason = "none", "neither Docker nor a model server is available"

    plan = {"mode": chosen, "reason": reason, "problems": problems,
            "notes": notes, "commands": [], "env": {},
            "system": sysname, "arch": info["arch"]}

    if chosen == "none":
        problems.append("Nothing to run it with yet.")
        problems += P.advice(info)
        problems.append("Simplest: install Docker (" + P.docker_install_url(sysname) +
                        "), then run this again. Or install Ollama (https://ollama.com), "
                        f"`ollama pull {model}`, then run this again.")
        return plan

    if chosen == "native":
        if not native_ready:
            problems.append("No model server found. Install Ollama (https://ollama.com) "
                            f"and run `ollama pull {model}`, or point --base-url at one.")
        plan["commands"] = ([f"ollama pull {model}   (if the model is not there yet)"]
                            if info.get("ollama") else []) + [
            f"vmd-agent chat --model {model}"]
        notes.append("Native: your own VMD is used if it is found (`vmd-agent doctor`).")
        if info.get("apple_silicon"):
            notes.append("Ollama uses the Mac's GPU natively, which is much faster than Docker here.")
        return plan

    # ---- docker
    if not docker_ready:
        problems += [m for m in P.advice(info) if "Docker" in m]
        if not d.get("installed"):
            problems.append("Install Docker: " + P.docker_install_url(sysname))
    if repo is None:
        problems.append("Cannot find the vmd-agent folder with docker/chat.compose.yml. "
                        "Run this from a clone of the repository.")
        return plan
    files = ["-f", os.path.join(repo, COMPOSE)]
    target = "runtime"
    if tarball:
        target = "with-vmd"
        notes.append("VMD tarball found: the image is built with VMD. Never share that image.")
        if info.get("apple_silicon"):
            notes.append("This Mac is arm64: the tarball must be VMD's Linux ARM64 build, or the "
                         "build will fail or run under slow emulation.")
    else:
        notes.append("No VMD tarball in docker/vmd-dist/: figures use the built-in renderer. "
                     "(A Mac or Windows VMD cannot run in Docker; download VMD's Linux build to use VMD here.)")
    if info.get("nvidia_gpu") and d.get("nvidia_runtime"):
        files += ["-f", os.path.join(repo, GPU_OVERRIDE)]
        notes.append(f"NVIDIA GPU ({info['nvidia_gpu']}): the model will use it.")
    else:
        notes.append("No GPU available to Docker: the model runs on the CPU (slower)."
                     + (" Docker on a Mac cannot use the Mac's GPU." if sysname == P.MACOS else ""))
    plan["env"] = {"MODEL": model, "DATA_DIR": compose_data_dir(data_dir, sysname),
                   "VMD_TARGET": target}
    c = [docker, "compose"] + files
    plan["compose"] = c
    plan["commands"] = [
        " ".join(c + ["up", "-d", "ollama"]),
        " ".join(c + ["exec", "-T", "ollama", "ollama", "pull", model]) + "   (if not downloaded yet)",
        " ".join(c + ["build", "vmd-agent"]),
        " ".join(c + ["run", "--rm", "vmd-agent", "chat"])]
    return plan


# ------------------------------------------------------------------ executing
def _say(m: str = "") -> None:
    print(m, flush=True)


def _run(argv: List[str], env: Optional[dict] = None, capture: bool = False):
    return subprocess.run(argv, env=env, text=True, capture_output=capture)


def run_docker(plan: dict, prompt: Optional[str], say: Callable = _say,
               wait_seconds: int = 180) -> int:
    c: List[str] = plan["compose"]
    env = {**os.environ, **plan["env"]}
    try:
        os.makedirs(plan["env"]["DATA_DIR"], exist_ok=True)
    except OSError:
        pass
    say("Starting the model server...")
    if _run(c + ["up", "-d", "ollama"], env).returncode != 0:
        say("Could not start the model server (see the error above).")
        return 1
    deadline = time.time() + wait_seconds
    have = None
    while time.time() < deadline:
        r = _run(c + ["exec", "-T", "ollama", "ollama", "list"], env, capture=True)
        if r.returncode == 0:
            have = r.stdout
            break
        time.sleep(3)
    if have is None:
        say("The model server did not become ready in time.")
        return 1
    model = plan["env"]["MODEL"]
    if any(line.startswith(model) for line in have.splitlines()):
        say(f"Model {model} is already downloaded.")
    else:
        say(f"Downloading model {model} (several GB, first time only)...")
        if _run(c + ["exec", "-T", "ollama", "ollama", "pull", model], env).returncode != 0:
            say(f"Could not download {model}. Check the name and your connection.")
            return 1
    say("Building the vmd-agent image (first time only)...")
    if _run(c + ["build", "vmd-agent"], env).returncode != 0:
        return 1
    say(f"\nReady. Your files go in: {plan['env']['DATA_DIR']}")
    return _run(c + ["run", "--rm", "vmd-agent", "chat"] + ([prompt] if prompt else []),
                env).returncode


def run_native(plan: dict, model: str, base_url: Optional[str], data_dir: str,
               prompt: Optional[str], info: Dict[str, object], say: Callable = _say) -> int:
    from vmd_agent import agent, chat, settings
    from vmd_agent.llm_client import LLMError, list_models
    private = settings.get("ollama_mode") == "private" and ollama_local.find_binary() is not None
    url = base_url or (ollama_local.url() if private else agent.DEFAULT_URL)
    private = private and url == ollama_local.url()
    if private:
        ollama_local.start()
    try:
        have = list_models(url)
    except LLMError:
        have = None
    if have is None:
        say(f"No model server answered at {url}. Start it (for Ollama: open the Ollama app, "
            "or run `ollama serve` in another window) and run this again.")
        return 2
    if have is not None and model not in have and (private or info.get("ollama")):
        say(f"Downloading model {model} (several GB, first time only)...")
        ok = ollama_local.pull(model) if private else _run(["ollama", "pull", model]).returncode == 0
        if not ok:
            say(f"Could not download {model}.")
            return 1
    os.makedirs(data_dir, exist_ok=True)
    return chat.main(base_url=url, model=model, roots=[data_dir], prompt=prompt)


# --------------------------------------------------------- the benchmark in a container
#: how VMD is supplied: no VMD (matplotlib renderer), a Linux VMD mounted from the host, or one baked into a local image
BENCH_MODES = {"plain": "bench", "hostvmd": "bench-hostvmd", "withvmd": "bench-withvmd"}
BENCH_ACTIONS = {"preflight": "agent-preflight", "suite": "agent-suite", "plan": "agent-plan", "run": "agent-run"}
_MACHO = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce")


def check_vmd_home(home: Optional[str], say: Callable = _say) -> int:
    """Is ``home`` a VMD install a Linux container can use? 0 yes, 1 no, 2 not given. A macOS VMD is refused: it is a
    macOS program and cannot run in a Linux container (the executable's first bytes are Mach-O's magic number)."""
    if not home:
        say("set VMD_HOME to your VMD install directory")
        return 2
    exe = next((c for c in (os.path.join(home, "bin", "vmd"), os.path.join(home, "vmd")) if os.path.isfile(c)), None)
    if not exe:
        say(f"no vmd launcher in {home} (looked for bin/vmd and vmd)")
        return 1
    with open(exe, "rb") as fh:
        if fh.read(4) in _MACHO:
            say(f"{exe} is a macOS binary. A Linux container cannot run it.\n"
                "Use mode withvmd with the Linux tarball in docker/vmd-dist/, or run natively:\n"
                "  vmd-agent bench agent-preflight --vmd <path-to-your-mac-vmd> ...")
            return 1
    say(f"found {exe}")
    if P.system() != P.LINUX:
        say(f"note: this computer is {P.system()}; the mounted VMD must still be a Linux build matching "
            f"VMD_PLATFORM={os.environ.get('VMD_PLATFORM', 'linux/amd64')}")
    return 0


def docker_bench(action: str, args: Optional[List[str]] = None, mode: str = "plain", docker: str = "docker",
                 say: Callable = _say) -> int:
    """Run the benchmark commands inside a container with your VMD (``vmd-agent bench docker``). ``action``: check-vmd,
    preflight, suite, plan, run or shell. ``mode`` says how VMD is supplied (``BENCH_MODES``)."""
    if mode not in BENCH_MODES:
        say(f"mode must be plain, hostvmd or withvmd (got '{mode}')")
        return 2
    if action == "check-vmd":
        return check_vmd_home(os.environ.get("VMD_HOME"), say)
    if action != "shell" and action not in BENCH_ACTIONS:
        say("action must be one of: check-vmd, " + ", ".join(list(BENCH_ACTIONS) + ["shell"]))
        return 2
    repo = find_repo()
    if repo is None:
        say("Cannot find the vmd-agent folder with docker/chat.compose.yml. Run this from a clone of the repository.")
        return 2
    if mode == "hostvmd" and check_vmd_home(os.environ.get("VMD_HOME"), say) != 0:
        return 1
    service = BENCH_MODES[mode]
    os.makedirs(os.environ.get("DATA_DIR") or os.path.join(repo, "data"), exist_ok=True)
    cmd = [docker, "compose", "-f", os.path.join(repo, "docker", "docker-compose.yml"), "--profile", service, "run", "--rm", service]
    cmd += ["sh"] if action == "shell" else ["bench", BENCH_ACTIONS[action]] + list(args or [])
    return _run(cmd).returncode


# ----------------------------------------------------------------------- main
def stop_docker(docker: str = "docker", say: Callable = _say) -> int:
    """Stop the Docker model server and chat (``vmd-agent start --down``)."""
    repo = find_repo()
    if repo is None:
        say("Cannot find the vmd-agent folder with docker/chat.compose.yml.")
        return 2
    return _run([docker, "compose", "-f", os.path.join(repo, COMPOSE), "down"]).returncode


def start(model: Optional[str] = None, data_dir: Optional[str] = None, mode: str = "auto",
          base_url: Optional[str] = None, prompt: Optional[str] = None,
          print_plan: bool = False, docker: str = "docker", say: Callable = _say) -> int:
    from vmd_agent import settings
    model = (model or os.environ.get("VMD_AGENT_LLM_MODEL")
             or settings.get("llm_model") or DEFAULT_MODEL)
    data_dir = data_dir or settings.get("data_dir") or "data"
    info = P.detect(docker)
    info["ollama"] = bool(info["ollama"]) or ollama_local.find_binary() is not None
    from vmd_agent.llm_client import LLMError, list_models
    up = False
    try:
        list_models(base_url or (ollama_local.url() if settings.get("ollama_mode") == "private"
                                 else "http://localhost:11434/v1"), timeout=2)
        up = True
    except LLMError:
        pass
    repo = find_repo()
    plan = make_plan(info, model, data_dir, repo, mode, docker,
                     vmd_tarball(repo) if repo else None, model_server_up=up)
    say(f"This computer: {info['system']} / {info['arch']}"
        f"{' (WSL)' if info['wsl'] else ''}.  Plan: {plan['mode']} ({plan['reason']}).")
    for n in plan["notes"]:
        say("  note: " + n)
    if plan["problems"]:
        say("")
        for pr in plan["problems"]:
            say("  ! " + pr)
        return 2
    if print_plan:
        say("\nCommands:")
        for cmd in plan["commands"]:
            say("  " + cmd)
        if plan["env"]:
            say("  with " + ", ".join(f"{k}={v}" for k, v in plan["env"].items()))
        return 0
    if plan["mode"] == "docker":
        return run_docker(plan, prompt, say)
    return run_native(plan, model, base_url, data_dir, prompt, info, say)


def doctor(docker: str = "docker") -> Dict[str, object]:
    """Facts about this machine, VMD, and what to do next."""
    from vmd_agent.environment import find_ffmpeg, find_tachyon, find_vmd, vmd_self_test
    info = P.detect(docker)
    info["ollama"] = bool(info["ollama"]) or ollama_local.find_binary() is not None
    vmd = find_vmd()
    info["vmd"] = {"path": vmd, "tachyon": find_tachyon(vmd) if vmd else None,
                   "ffmpeg": find_ffmpeg(),
                   "self_test": vmd_self_test(vmd) if vmd else None}
    from vmd_agent import settings
    from vmd_agent.llm_client import LLMError, list_models
    url = settings.get("llm_url")
    chat_model = {"model": settings.get("llm_model"), "url": url, "reachable": None, "downloaded": None,
                  "private": settings.get("ollama_mode") == "private"}
    if url:
        try:
            have = list_models(url, settings.get("llm_key"), timeout=3)
            chat_model.update(reachable=True, downloaded=chat_model["model"] in have)
        except LLMError:
            chat_model["reachable"] = False
    info["chat_model"] = chat_model
    repo = find_repo()
    info["repo"] = repo
    info["next_steps"] = P.advice(info)
    return info


def doctor_text(info: Dict[str, object]) -> str:
    d: dict = info["docker"]                                   # type: ignore[assignment]
    v: dict = info["vmd"]                                      # type: ignore[assignment]
    yes = lambda b: "yes" if b else "no"
    lines = [f"System:      {info['system']} / {info['arch']}"
             + (" (WSL)" if info["wsl"] else "")
             + (" (inside a container)" if info["in_container"] else ""),
             f"Python:      {info['python']}",
             f"Memory:      {info['ram_gb'] if info.get('ram_gb') else 'could not be read'} GB"
             + (lambda m: f" (suggested model: {m.tag})" if m else " (too little for a model that can use tools: use an online model or Claude)")(
                 models.recommend(info.get("ram_gb"), bool(info.get("nvidia_gpu")))),
             "Claude Code: " + ("not installed" if not info["claude_code"]["installed"] else
                                "installed, vmd-agent is registered as an MCP server" if info["claude_code"]["registered"] else
                                "installed; vmd-agent is not one of its tools (only needed if you want Claude Code, not a model here, to be the assistant: `vmd-agent mcp-config`)"),
             f"Docker:      installed {yes(d['installed'])}, running {yes(d['running'])}, "
             f"compose {yes(d['compose'])}, NVIDIA runtime {yes(d['nvidia_runtime'])}",
             f"GPU:         {info['nvidia_gpu'] or 'no NVIDIA GPU'}"
             + (" (Apple Silicon)" if info["apple_silicon"] else ""),
             f"Ollama:      {'installed' if info['ollama'] else 'not installed'}",
             "Chat model:  " + (
                 f"{info['chat_model']['model']} at {info['chat_model']['url']}: "
                 + (("not running right now; it starts by itself when you chat" if info['chat_model']['private'] else
                     "not reachable (run `vmd-agent setup`)") if info['chat_model']['reachable'] is False else
                    "reachable, downloaded" if info['chat_model']['downloaded'] else
                    "reachable, NOT downloaded yet (run `vmd-agent setup`)")
                 if info['chat_model']['url'] else "none chosen yet (run `vmd-agent setup`)"),
             f"VMD:         {v['path'] or 'not found'}"
             + (f" (Tachyon: {v['tachyon'] or 'not found'})" if v["path"] else ""),
             ("VMD check:   " + ("works. " + str(v["self_test"]["version_note"])
                                 if v["self_test"]["ok"] else
                                 "FAILED. " + v["self_test"]["problem"] + " " + v["self_test"]["advice"])
              if v.get("self_test") else "VMD check:   skipped (VMD not found)"),
             f"ffmpeg:      {v['ffmpeg'] or 'not found'}",
             f"Repo:        {info['repo'] or 'no clone with docker/chat.compose.yml found'}"]
    if info["next_steps"]:
        lines += ["", "Notes:"] + ["  - " + n for n in info["next_steps"]]
    return "\n".join(lines)
