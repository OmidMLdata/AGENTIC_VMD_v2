"""Claude Code as the chat's assistant: the page's chat hands each question to Claude Code on this computer, which works with vmd-agent's own
tools over MCP.

Claude Code runs as ``claude -p`` (its non-interactive mode) with vmd-agent's MCP server as its only tool provider: Claude Code's own
tools (shell, file editing, web) are switched off, so it can do exactly what vmd-agent's tools allow, inside the files folder, as with
any other model. The tools run in the MCP server that Claude Code starts, and they drive the same VMD window as the page (the link to a
window is shared between processes). Claude Code signs in with its own login (a Claude subscription or an API key it was given), so the
page needs no key. Each question resumes the same Claude Code session, so the conversation carries on; New starts another.

What Claude Code does is reported as the chat reports any model: a line per tool call with its seconds, the pictures it made, and the answer.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, Dict, List, Optional

from vmd_agent import security, toolset
from vmd_agent.llm_client import LLMError

#: the stand-in model-server address that means "Claude Code on this computer" (saved in the settings like any address)
URL = "claude-code:"
#: what the model field holds when Claude Code should use its own default model
DEFAULT = "default"
#: the Claude models to choose from, newest generation, by their full names (Claude Code takes these as they are); the short names
#: of earlier versions of vmd-agent ("sonnet", "opus", "haiku") still work and mean the newest of each
MODELS = [
    {"id": DEFAULT, "label": "Claude Code's default", "note": "whatever Claude Code itself uses"},
    {"id": "claude-fable-5-1", "label": "Claude Fable 5.1", "note": "the most capable"},
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "note": "for complex work"},
    {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "note": "fast and capable, a good everyday choice"},
    {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "note": "the fastest"},
]
ALIASES = [m["id"] for m in MODELS] + ["sonnet", "opus", "haiku", "fable"]


def label(model: Optional[str]) -> str:
    """How a person reads the model: 'Claude Sonnet 5.5', not 'claude-sonnet-5-5'."""
    return next((m["label"] for m in MODELS if m["id"] == (model or DEFAULT)), str(model))
SERVER = "vmd-agent"
PREFIX = f"mcp__{SERVER}__"
#: Claude Code's own tools, switched off when this version cannot be told "no built-in tools" (--tools "")
BUILT_IN = ("Bash", "BashOutput", "KillShell", "Edit", "MultiEdit", "Write", "NotebookEdit", "Read", "Glob", "Grep", "LS", "WebFetch",
            "WebSearch", "Task", "TodoWrite", "PowerShell", "Workflow", "Skill", "CronCreate", "SendMessage")
LONGEST = 1800.0                     # seconds one question may take before Claude Code is stopped
_help_cache: Dict[str, str] = {}

EXTRA = """
You are working inside the vmd-agent web page: the person reads your answers in its chat and watches the VMD window it controls. Your tools \
are vmd-agent's (their names start with mcp__vmd-agent__); use them for everything, and refer to files by their names in the files folder."""


def is_claude_code(base_url: Optional[str]) -> bool:
    return str(base_url or "").strip().lower().rstrip("/") == URL.rstrip("/")


#: where a person can say where Claude Code is, when vmd-agent cannot find it (also a setting, "claude_path", set in the Model window)
ENV_PATH = "VMD_AGENT_CLAUDE"
_found: Dict[str, object] = {"path": None, "when": 0.0, "searched": []}
_checked: Dict[str, Optional[str]] = {}


def claude_version_of(path: str) -> Optional[str]:
    """The version of the Claude Code at ``path``, or None if that is not Claude Code (asked with --version, so another program called
    "claude", such as the Claude desktop app itself, is never mistaken for it)."""
    try:
        key = f"{path}|{os.path.getmtime(path)}"
    except OSError:
        return None
    if key not in _checked:
        try:
            out = _run([path, "--version"], timeout=20.0).strip()
        except (OSError, subprocess.SubprocessError, ValueError):
            out = ""
        line = out.splitlines()[0] if out else ""
        _checked[key] = line.replace("(Claude Code)", "").strip() if "claude code" in out.lower() else None
    return _checked[key]


def _executable(p: str) -> bool:
    return os.path.isfile(p) and os.access(p, os.X_OK)


def _candidates() -> List[str]:
    """Every place an installer puts ``claude``: the PATH, the native installer, npm (also under nvm, fnm, volta, asdf, pnpm, yarn and
    conda), and Homebrew."""
    import glob
    home = os.path.expanduser("~")
    names = ("claude.exe", "claude.cmd") if os.name == "nt" else ("claude",)
    out: List[str] = []
    which = shutil.which("claude")
    if which:
        out.append(which)
    dirs = [os.path.join(home, ".claude", "local"), os.path.join(home, ".local", "bin"), os.path.join(home, ".npm-global", "bin"),
            os.path.join(home, ".npm", "bin"), os.path.join(home, ".bun", "bin"), os.path.join(home, ".volta", "bin"),
            os.path.join(home, ".asdf", "shims"), os.path.join(home, "Library", "pnpm"), os.path.join(home, ".local", "share", "pnpm"),
            os.path.join(home, ".yarn", "bin"), os.path.join(home, ".config", "yarn", "global", "node_modules", ".bin"),
            "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    patterns = [os.path.join(home, ".nvm", "versions", "node", "*", "bin"),
                os.path.join(home, ".local", "share", "fnm", "node-versions", "*", "installation", "bin"),
                os.path.join(home, "Library", "Application Support", "fnm", "node-versions", "*", "installation", "bin"),
                os.path.join(home, ".fnm", "node-versions", "*", "installation", "bin")]
    for conda in ("anaconda3", "miniconda3", "miniforge3", "mambaforge", "micromamba"):
        for base in (os.path.join(home, conda), os.path.join("/opt", conda), os.path.join(home, "opt", conda)):
            dirs.append(os.path.join(base, "bin"))
            patterns.append(os.path.join(base, "envs", "*", "bin"))
    if os.name == "nt":
        dirs += [os.path.join(os.environ.get("APPDATA", ""), "npm"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "claude")]
    for pat in patterns:
        dirs += sorted(glob.glob(pat), reverse=True)                                  # the newest node first
    for d in dirs:
        for n in names:
            out.append(os.path.join(d, n))
    return out


def _from_login_shell() -> Optional[str]:
    """Where the person's own terminal finds ``claude`` (its PATH may be set in .zshrc or .bashrc, which a page started otherwise misses)."""
    if os.name == "nt":
        return None
    shell = os.environ.get("SHELL") or ("/bin/zsh" if sys.platform == "darwin" else "/bin/bash")
    try:
        r = subprocess.run([shell, "-lic", "command -v claude"], capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in reversed((r.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("/") and _executable(line):
            return line
    return None


def _desktop_app_copies() -> List[str]:
    """Copies of Claude Code that the Claude desktop app keeps for its Code tab (a file named exactly ``claude``, a few folders down)."""
    home = os.path.expanduser("~")
    roots = [os.path.join(home, "Library", "Application Support", "Claude"), os.path.join(home, ".config", "Claude")]
    if os.name == "nt":
        roots.append(os.path.join(os.environ.get("APPDATA", ""), "Claude"))
    found: List[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        base = root.count(os.sep)
        for d, subdirs, files in os.walk(root):
            if d.count(os.sep) - base >= 5:
                subdirs[:] = []
            subdirs[:] = [x for x in subdirs if x not in ("Cache", "Code Cache", "GPUCache", "IndexedDB", "Local Storage", "logs", "blob_storage")]
            for f in files:
                if f in ("claude", "claude.exe"):                                      # exact name: the app itself is "Claude"
                    found.append(os.path.join(d, f))
    return sorted(found, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)


def find(refresh: bool = False) -> Optional[str]:
    """The Claude Code program: where the person said it is, else wherever an installer or the Claude desktop app put it, confirmed by asking
    it for its version. Remembered for a while, since the page asks often."""
    from vmd_agent import settings
    now = time.time()
    remembered = _found["path"]
    if (not refresh and _found["when"] and now - float(_found["when"]) < (300 if remembered else 20)
            and (remembered is None or _executable(str(remembered)))):          # moved or uninstalled since: look again
        return remembered                                                           # type: ignore[return-value]
    searched: List[str] = []
    configured = os.environ.get(ENV_PATH) or settings.get("claude_path")
    stages = [lambda: [os.path.expanduser(str(configured))] if configured else [], _candidates,
              lambda: [p for p in [_from_login_shell()] if p], _desktop_app_copies]
    path = None
    for stage in stages:
        for cand in dict.fromkeys(stage()):
            if not _executable(cand):
                continue
            searched.append(cand)
            if claude_version_of(cand):
                path = cand
                break
        if path:
            break
    _found.update(path=path, when=now, searched=searched)
    return path


def _run(cmd: List[str], timeout: float = 20.0) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return (r.stdout or "") + (r.stderr or "")


def version(path: str) -> Optional[str]:
    return claude_version_of(path)


def _help(path: str) -> str:
    if path not in _help_cache:
        try:
            _help_cache[path] = _run([path, "--help"])
        except (OSError, subprocess.SubprocessError):
            _help_cache[path] = ""
    return _help_cache[path]


HOW_TO_INSTALL = ("vmd-agent cannot find Claude Code, the command-line program (the Claude app and claude.ai are not it). In a terminal, "
                  "run `which claude`: if it prints a path, put that path under 'Where Claude Code is' in this window; if it prints nothing, "
                  "install Claude Code from https://claude.com/claude-code, run `claude` once to sign in, and press Check")
HOW_TO_SIGN_IN = ("Claude Code is not signed in. Open a terminal, run `claude`, and sign in with your Claude account "
                  "(or set it up with an API key); then ask again here")


def info(model: str) -> dict:
    """What the Model window shows for Claude Code: whether the program is there, its version, and the models it can be asked for.
    Signing in is checked by the first question, not here: checking it costs a request each time the page looks."""
    from vmd_agent import settings
    path = find()
    out = {"backend": "claude-code", "base_url": URL, "model": model or DEFAULT, "has_key": False, "available": list(ALIASES),
           "claude_models": MODELS, "claude_path": path, "claude_path_setting": settings.get("claude_path") or "",
           "claude_version": None, "state": "ready", "problem": None}
    given = out["claude_path_setting"]
    if given and path != os.path.expanduser(given):
        out["claude_path_note"] = (f"'{given}' is not Claude Code (asked for its version, it did not answer as Claude Code)"
                                   + (f"; using {path} instead" if path else ""))
    if not path:
        out.update(state="no_server", problem=out.get("claude_path_note") or HOW_TO_INSTALL,
                   claude_searched=list(_found["searched"])[:12])   # type: ignore[arg-type]
        return out
    out["claude_version"] = version(path)
    if not out["claude_version"]:
        out.update(state="no_server", problem=f"Claude Code was found at {path} but did not start (try `claude --version` in a terminal)")
    return out


def mcp_config(root: str) -> dict:
    """The MCP configuration that connects Claude Code to vmd-agent's tools, sandboxed to the files folder (the same as `vmd-agent mcp-config`)."""
    from vmd_agent import mcp_check
    cfg = mcp_check.build_mcp_config(roots=[root])["config"]
    server = dict(cfg["mcpServers"][SERVER])
    if not os.path.isabs(server["command"]) or not os.path.exists(server["command"]):     # no console script next to this Python: run the module
        server = {"command": sys.executable, "args": ["-m", "vmd_agent.server"], **({"env": server["env"]} if server.get("env") else {})}
    env = dict(server.get("env") or {})
    env[security.ENV_ROOTS] = os.path.realpath(root)
    server["env"] = env
    return {"mcpServers": {SERVER: server}}


def command(path: str, config_file: str, model: str, session_id: Optional[str], system: str) -> List[str]:
    """The ``claude -p`` command for one question (the question itself goes in on stdin)."""
    helptext = _help(path)
    cmd = [path, "-p", "--output-format", "stream-json", "--verbose", "--mcp-config", config_file, "--strict-mcp-config",
           "--allowedTools", f"mcp__{SERVER}", "--append-system-prompt", system]
    if "--tools " in helptext:
        cmd += ["--tools", ""]                                        # none of Claude Code's own tools: only vmd-agent's
    else:
        cmd += ["--disallowedTools", ",".join(BUILT_IN)]
    if "dontAsk" in helptext:
        cmd += ["--permission-mode", "dontAsk"]                       # anything not allowed above is refused, never asked about
    if model and model != DEFAULT:
        cmd += ["--model", model]
    if session_id:
        cmd += ["--resume", session_id]
    return cmd


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def _result(text: str):
    """A tool result as vmd-agent returned it (JSON), or the text."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {"text": text}


class Session:
    """A chat with Claude Code that looks to the page like the chat with any model: ``ask`` answers, ``on_event`` reports each tool call,
    ``last_turn`` and ``clock`` say where the time went, ``reset`` starts a new conversation."""

    def __init__(self, model: str = DEFAULT, root: Optional[str] = None, echo: Optional[Callable[[str], None]] = None,
                 system: Optional[str] = None):
        from vmd_agent import agent as agent_mod
        self.model = model or DEFAULT
        self.base_url, self.api_key = URL, None
        self._root = root
        self.echo = echo or (lambda m: None)
        self.system = (system or agent_mod.SYSTEM_PROMPT) + EXTRA
        self.names = list(toolset.ALL)
        self.profile = "all"
        self.clock = agent_mod.new_clock()
        self.last_turn = agent_mod.new_clock()
        self.on_event: Optional[Callable[[dict], None]] = None
        self.streamed = False
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.cost_usd = 0.0
        self.call_log: List[dict] = []
        self.session_id: Optional[str] = None
        self.process: Optional[subprocess.Popen] = None

    def root(self) -> str:
        return self._root or (security.allowed_roots() or [os.getcwd()])[0]

    def reset(self) -> None:
        self.session_id = None                                        # the next question starts a new Claude Code conversation

    def _emit(self, **event) -> None:
        if self.on_event:
            self.on_event(event)

    def ask(self, text: str, on_token: Optional[Callable[[str], None]] = None) -> str:
        from vmd_agent import agent as agent_mod
        path = find()
        if not path:
            raise LLMError(HOW_TO_INSTALL)
        turn = agent_mod.new_clock()
        self.last_turn = turn
        began = time.time()
        with tempfile.TemporaryDirectory(prefix="vmd-agent-claude-") as tmp:
            cfg = os.path.join(tmp, "mcp.json")
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(mcp_config(self.root()), fh)
            cmd = command(path, cfg, self.model, self.session_id, self.system)
            self.echo(f"  (asking Claude Code{'' if self.model == DEFAULT else ' (' + self.model + ')'})")
            self._emit(type="model_start")
            try:
                proc = subprocess.Popen(cmd, cwd=self.root(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", errors="replace", bufsize=1)
            except OSError as e:
                raise LLMError(f"Claude Code could not be started ({e})") from e
            self.process = proc
            timer = threading.Timer(LONGEST, proc.kill)
            timer.daemon = True
            timer.start()
            errors: List[str] = []
            threading.Thread(target=lambda: errors.extend(proc.stderr.readlines()), daemon=True).start()
            try:
                proc.stdin.write(text)
                proc.stdin.close()
                final = self._read(proc, turn)
                proc.wait(timeout=30)
            finally:
                timer.cancel()
                self.process = None
                if proc.poll() is None:
                    proc.kill()
        turn["wall_s"] = time.time() - began
        agent_mod.add_clock(self.clock, turn)
        self._emit(type="model_end", seconds=round(turn["model_s"], 3))
        if final is None:
            tail = "".join(errors)[-600:].strip()
            if time.time() - began >= LONGEST:
                raise LLMError(f"Claude Code took longer than {LONGEST / 60:.0f} minutes and was stopped")
            raise LLMError("Claude Code stopped without an answer" + (f": {tail}" if tail else ""))
        answer = str(final.get("result") or "")
        if final.get("is_error") or final.get("subtype", "success") != "success":
            low = answer.lower()
            if "not logged in" in low or "/login" in low or "invalid api key" in low or "authentication" in low:
                raise LLMError(HOW_TO_SIGN_IN)
            raise LLMError("Claude Code could not answer: " + (answer or final.get("subtype") or "an error"))
        return answer

    def _read(self, proc: subprocess.Popen, turn: dict) -> Optional[dict]:
        """Follow Claude Code's stream: the session, each tool call and its result, and the final answer."""
        started: Dict[str, tuple] = {}
        final = None
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = ev.get("type")
            if kind == "system" and ev.get("subtype") == "init":
                self.session_id = ev.get("session_id") or self.session_id
                server = next((s for s in ev.get("mcp_servers") or [] if s.get("name") == SERVER), None)
                if server is not None and server.get("status") not in ("connected", None):
                    self.echo(f"  ! vmd-agent's tools did not connect to Claude Code ({server.get('status')})")
                    self._emit(type="note", text=f"vmd-agent's tools did not connect to Claude Code ({server.get('status')}); "
                                                 "run `vmd-agent mcp-check` in a terminal to see why.")
            elif kind == "assistant":
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_use":
                        name = str(block.get("name", ""))
                        short = name[len(PREFIX):] if name.startswith(PREFIX) else name
                        args = block.get("input") or {}
                        started[block.get("id")] = (short, time.time(), args)
                        self.echo(f"  -> {short}")
                        self._emit(type="tool_start", name=short, args={k: str(v)[:200] for k, v in args.items()})
            elif kind == "user":
                content = (ev.get("message") or {}).get("content")
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    short, t0, args = started.pop(block.get("tool_use_id"), ("tool", time.time(), {}))
                    seconds = time.time() - t0
                    result = _result(_text(block.get("content")))
                    failed = bool(block.get("is_error")) or (isinstance(result, dict) and bool(result.get("error")))
                    err = (result.get("error") if isinstance(result, dict) else None) or (_text(block.get("content"))[:300] if failed else None)
                    turn["tool_s"] += seconds
                    turn["tool_calls"].append({"name": short, "seconds": round(seconds, 3)})
                    self.call_log.append({"name": short, "arguments": args, "result": result, "seconds": round(seconds, 3)})
                    self.echo(f"     {seconds:.1f} s" + (f"  ! {str(err)[:140]}" if failed else ""))
                    self._emit(type="tool_end", name=short, seconds=round(seconds, 3), error=str(err)[:300] if failed else None, result=result)
            elif kind == "result":
                final = ev
                self.session_id = ev.get("session_id") or self.session_id
                turn["model_s"] = max(0.0, float(ev.get("duration_api_ms") or 0) / 1000.0)
                turn["model_calls"] = int(ev.get("num_turns") or 0)
                self.cost_usd += float(ev.get("total_cost_usd") or 0.0)
                usage = ev.get("usage") or {}
                for k in self.usage:
                    self.usage[k] += int(usage.get(k) or 0)
        return final


def check() -> Optional[List[str]]:
    """None if Claude Code is there; otherwise what to do (for the terminal chat)."""
    i = info(DEFAULT)
    return None if i["state"] == "ready" else [f"vmd-agent chat: {i['problem']}."]
