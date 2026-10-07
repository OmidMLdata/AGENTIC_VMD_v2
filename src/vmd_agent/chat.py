"""``vmd-agent chat``: talk to the toolkit with a language model, no MCP client needed.

The model is any server that speaks the OpenAI-style chat API: an **open-source model
running on your own machine** (Ollama, llama.cpp, vLLM, LM Studio) or a hosted
one. The model is given the toolkit's tools (:mod:`vmd_agent.toolset`), decides
which to call, and the results go back to it, in a loop, until it answers.

Whether a model does this *well* depends on the model: tool calling and multi-step
analysis are hard for small models. The benchmark (``vmd-agent bench agent-run
--model openai:<id>``) measures that for any model you choose.

Safety defaults: if ``VMD_AGENT_ALLOWED_ROOTS`` is unset the agent is confined to the
current directory; ``run_vmd_tcl`` stays disabled unless ``VMD_AGENT_ENABLE_TCL=1``.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from typing import Callable, List, Optional

from vmd_agent import models, ollama_local, progress, security, toolset
from vmd_agent.llm_client import (
    LLMError, assistant_message, chat_completion, list_models, parse_choice,
    render_result, to_openai_tools, tool_message)

DEFAULT_URL = "http://localhost:11434/v1"            # Ollama's OpenAI-style API
DEFAULT_MODEL = models.DEFAULT_MODEL                 # a suggestion, not a finding
ENV_URL, ENV_MODEL, ENV_KEY = ("VMD_AGENT_LLM_URL", "VMD_AGENT_LLM_MODEL",
                               "VMD_AGENT_LLM_KEY")

SYSTEM_PROMPT = """You are vmd-agent, an assistant for molecular visualization and \
trajectory analysis. You work through tools; use them to look at the data instead \
of guessing.

Rules:
1. Never invent a number. Measure it with a tool, and say how: which selection, \
which frames, which method.
2. Files live in the data directory. Relative paths are relative to it. If you do \
not know what a file is, start with inspect_files and detect_system.
3. Read the notes and warnings in every tool result. If the data look damaged (a \
molecule split across periodic boundaries, frames with NaN coordinates, an atom \
count that does not match the topology, a time axis taken from an unreliable file \
header) say so and do not report the affected number as if it were fine.
4. If you cannot answer reliably with the data and tools you have, say that plainly.
5. Before giving a final write-up that states facts about a structure, check those \
facts with verify_claims and drop or correct anything it contradicts.
6. You cannot see images. Describe results from the measurements, not from pictures.
7. Be concise: the answer first, then how you got it.
8. Tools whose names start with vmd_ run VMD itself. They save the exact Tcl they ran \
(`reproduce_script` in the result): mention it when the user may want to repeat the \
analysis in their own VMD, and offer export_vmd_session to hand over a scene as a \
folder they can open. Never write or paraphrase Tcl yourself: give only the path from \
`reproduce_script`. When the user asks what VMD can do, call vmd_capabilities.
9. For a whole job (has a run settled, what interacts, compare two runs, prepare a simulation, fit a model into a map) call \
list_workflows, then run_workflow: it runs the steps, grades the findings and writes a report. Quote its verdict and findings and \
give the report path."""


_DATA_WORDS = re.compile(
    r"\.(pdb|psf|dcd|xtc|trr|gro|cif|mmcif|mol2|xyz|prmtop|nc|dx|mrc|ccp4|cube|mp4|png)\b|"
    r"\b(measure|analy[sz]e|rmsd|rmsf|radius of gyration|salt bridges?|hydrogen bonds?|h-bonds?|contacts?|secondary structure|"
    r"render|draw|plot|build|solvate|mutate|trajector(?:y|ies)|simulations?|runs?|frames?|disulfides?|ligands?|box|density|plugins?)\b",
    re.I)

_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _numbers(text: str):
    out = []
    for m in _NUM.finditer(text):
        tok = m.group(0)
        try:
            out.append((float(tok), len(tok.split(".")[1].split("e")[0].split("E")[0]) if "." in tok else 0))
        except ValueError:
            pass
    return out


def unsupported_numbers(answer: str, tool_texts) -> List[str]:
    """Numbers in a model's answer that appear in no tool result. A decimal number counts as supported if some
    tool number matches it at the precision the answer shows (also as a percentage, x100); integers below 100 are
    ignored (counts, indices, step sizes). A small model that misreads a result shows up here."""
    have = [v for t in tool_texts for v, _ in _numbers(t)]
    bad: List[str] = []
    for v, dec in _numbers(re.sub(r"```.*?```", "", answer, flags=re.S)):
        if dec == 0 and abs(v) < 100:
            continue
        tol = 0.51 * 10 ** (-dec)
        if any(abs(h - v) <= tol or abs(h * 100 - v) <= tol for h in have):
            continue
        s = f"{v:g}" if dec == 0 else f"{v:.{dec}f}"
        if s not in bad:
            bad.append(s)
    return bad


#: questions that a named workflow answers better than one measurement (the model is pointed at it; it still makes the call)
_ROUTES = [
    ("equilibration_check", re.compile(r"\b(settled|equilibrat\w*|converg\w*|stabili[sz]ed|steady state)\b", re.I)),
    ("compare_runs", re.compile(r"\bcompar\w*\b.*\b(runs?|trajector\w+|simulations?)\b", re.I)),
    ("prepare_simulation", re.compile(r"\b(prepare|set ?up|get ready)\b.*\b(simulation|md|namd)\b|\bready (to|for) simulat\w*", re.I)),
    ("cryoem_fit", re.compile(r"\bcryo-?em\b|\bfit\b.*\b(into|to)\b.*\bmap\b|\bdensity map\b", re.I)),
    ("structure_overview", re.compile(r"\b(overview|sanity check|structure quality|check (this|the|my) structure)\b", re.I)),
]


def route(text: str) -> Optional[str]:
    """The workflow that fits a question, if one clearly does."""
    for name, pattern in _ROUTES:
        if pattern.search(text):
            return name
    return None


NUDGE = ("You answered without using any tool, so that answer is a guess. Use a tool on the data first "
         "(for a local file start with inspect_files; use fetch_structure only to download an entry that is not "
         "already in the data folder), then answer from its result.")


# --------------------------------------------------------------------- setup
def ensure_roots(default: Optional[str] = None) -> List[str]:
    """Return the sandbox roots, defaulting to ``default`` (or the current
    directory) when none are configured, so the agent is never unconfined by
    accident."""
    roots = security.allowed_roots()
    if roots:
        return roots
    root = os.path.realpath(default or os.getcwd())
    os.environ[security.ENV_ROOTS] = root
    return [root]


def _short(value, n: int = 60) -> str:
    s = repr(value)
    return s if len(s) <= n else s[:n - 3] + "..."


# ------------------------------------------------------------------ clocks
def new_clock() -> dict:
    """Wall-clock bookkeeping: seconds waiting for the model, seconds in tools, and each tool call's own time."""
    return {"wall_s": 0.0, "model_s": 0.0, "tool_s": 0.0, "model_calls": 0, "tool_calls": [], "first_token_s": None}


def add_clock(total: dict, turn: dict) -> None:
    for k in ("wall_s", "model_s", "tool_s", "model_calls"):
        total[k] += turn[k]
    total["tool_calls"] += turn["tool_calls"]


def clock_line(c: dict) -> str:
    """One line a person can read: how long the question took, and where the time went."""
    parts = [f"model {c['model_s']:.1f} s in {c['model_calls']} call{'s' if c['model_calls'] != 1 else ''}"]
    if c["tool_calls"]:
        parts.append(f"tools {c['tool_s']:.1f} s in {len(c['tool_calls'])} call{'s' if len(c['tool_calls']) != 1 else ''}")
    first = f", first words after {c['first_token_s']:.1f} s" if c.get("first_token_s") is not None else ""
    return f"took {c['wall_s']:.1f} s ({'; '.join(parts)}{first})"


# ------------------------------------------------------------------ session
class ChatSession:
    """A conversation with a model that can call the toolkit's tools."""

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None,
                 max_turns: int = 20, temperature: float = 0.0,
                 system: str = SYSTEM_PROMPT,
                 echo: Optional[Callable[[str], None]] = None,
                 max_history_chars: int = 60000, timeout: float = 900.0,
                 tools: str = "all", guard: bool = True, max_tokens: int = 3000):
        self.base_url, self.model, self.api_key = base_url, model, api_key
        self.max_turns, self.temperature = max_turns, temperature
        self.max_history_chars, self.timeout = max_history_chars, timeout
        self.system = system
        self.guard = guard
        self.max_tokens = max_tokens          # a model that rambles or repeats itself is cut off, not waited for
        self.echo = echo or (lambda m: None)
        if tools not in toolset.PROFILES:
            raise ValueError(f"tools must be one of {', '.join(toolset.PROFILES)}")
        self.names = list(toolset.PROFILES[tools])
        self.tools = to_openai_tools(toolset.tool_specs(self.names))
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.clock = new_clock()               # wall-clock of the whole session
        self.last_turn: dict = new_clock()     # wall-clock of the latest question
        self.turn: dict = self.last_turn
        self.call_log: List[dict] = []         # every tool call so far: name, arguments, the result as returned, seconds
        self.on_event: Optional[Callable[[dict], None]] = None   # structured events for a screen (the web page); see _emit
        self.reset()

    def _emit(self, **event) -> None:
        if self.on_event:
            self.on_event(event)

    def reset(self) -> None:
        self.messages: List[dict] = [{"role": "system", "content": self.system}]

    # ---- one tool call
    def run_tool(self, call: dict) -> str:
        name = call["name"]
        args = {k: v for k, v in (call.get("arguments") or {}).items() if k not in toolset.HIDDEN_FROM_MODELS}
        if call.get("arguments_error"):
            return render_result({"error": call["arguments_error"]})
        fn = toolset.TOOLS.get(name) if name in self.names else None
        if fn is None:
            return render_result({"error": f"unknown tool '{name}'",
                                  "available": self.names})
        self.echo(f"  -> {name}({', '.join(f'{k}={_short(v)}' for k, v in args.items())})")
        self._emit(type="tool_start", name=name, args={k: _short(v, 200) for k, v in args.items()})
        started = time.time()

        def note(m, f=None):
            self.echo(f"     ... {m}")
            self._emit(type="tool_progress", name=name, text=str(m), fraction=f)
        try:
            with progress.listen(note):
                result = fn(**args)
        except TypeError as e:
            expected = toolset.tool_schema(fn)["input_schema"]
            result = {"error": f"bad arguments for {name}: {e}",
                      "parameters": expected["properties"],
                      "required": expected["required"]}
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        seconds = time.time() - started
        self.turn["tool_s"] += seconds
        self.turn["tool_calls"].append({"name": name, "seconds": round(seconds, 3)})
        self.call_log.append({"name": name, "arguments": args, "result": result, "seconds": round(seconds, 3)})
        self.echo(f"     {seconds:.1f} s")
        failed = isinstance(result, dict) and bool(result.get("error"))
        if failed:
            self.echo(f"     ! {str(result['error'])[:140]}")
        self._emit(type="tool_end", name=name, seconds=round(seconds, 3), error=str(result["error"])[:300] if failed else None,
                   result=result)
        return render_result(result)

    # ---- keep the history inside a model's context window
    def _trim(self) -> None:
        total = sum(len(str(m.get("content") or "")) for m in self.messages)
        for m in self.messages:
            if total <= self.max_history_chars:
                break
            if m["role"] == "tool" and len(m["content"]) > 200:
                total -= len(m["content"]) - 40
                m["content"] = "[older tool result omitted to save space]"

    # ---- one user turn
    def ask(self, text: str, on_token: Optional[Callable[[str], None]] = None) -> str:
        """One user turn. With ``on_token`` the answer is delivered piece by piece as the model writes it (an answer
        that the guard is about to send back is held until it is known to be kept). The full text is returned either way;
        ``self.streamed`` tells whether it was already delivered through ``on_token``."""
        self.turn = new_clock()
        began = time.time()
        try:
            return self._ask(text, on_token)
        finally:
            self.turn["wall_s"] = time.time() - began
            self.last_turn = self.turn
            add_clock(self.clock, self.turn)

    def _ask(self, text: str, on_token: Optional[Callable[[str], None]]) -> str:
        hint = route(text) if "run_workflow" in self.names else None
        self.messages.append({"role": "user", "content": text + (
            f"\n\n[hint from the toolkit: the workflow `{hint}` answers this question properly (several checks, graded findings, a report). "
            f"Call run_workflow with name=\"{hint}\" and the file names from the question.]" if hint else "")})
        if hint:
            self.echo(f"  (the workflow '{hint}' fits this question)")
        used_tool = nudged = False
        self.streamed = False
        question_about_data = bool(_DATA_WORDS.search(text))
        for _ in range(self.max_turns):
            self._trim()
            held: List[str] = []
            live = bool(on_token) and (used_tool or not (self.guard and question_about_data))
            first = {"seen": False}
            asked = time.time()
            self._emit(type="model_start")

            def piece(tok: str) -> None:
                if not first["seen"] and self.turn["first_token_s"] is None:
                    self.turn["first_token_s"] = time.time() - asked
                first["seen"] = True
                if live:
                    on_token(tok)                                   # type: ignore[misc]
                else:
                    held.append(tok)
            wait = None
            if on_token:
                wait = threading.Timer(3.0, lambda: None if first["seen"] else self.echo("  ... the model is thinking"))
                wait.daemon = True
                wait.start()
            try:
                resp = chat_completion(self.base_url, self.model, self.messages,
                                       tools=self.tools, api_key=self.api_key,
                                       temperature=self.temperature,
                                       timeout=self.timeout, max_tokens=self.max_tokens,
                                       tool_choice="required" if nudged and not used_tool else None,
                                       on_token=piece if on_token else None)
            finally:
                if wait:
                    wait.cancel()
                self.turn["model_s"] += time.time() - asked
                self.turn["model_calls"] += 1
                self._emit(type="model_end", seconds=round(time.time() - asked, 3))
            parsed = parse_choice(resp, self.names)
            for k in self.usage:
                self.usage[k] += parsed["usage"][k]
            if not parsed["tool_calls"] and self.guard and not used_tool and not nudged and question_about_data:
                # a question about data answered from memory: send it back once, and require a tool call
                self.echo("  (the model answered without a tool; asking it to use one)")
                self.messages.append({"role": "user", "content": NUDGE})
                nudged = True
                continue
            self.messages.append(assistant_message(parsed))
            if not parsed["tool_calls"]:
                if held and on_token:
                    on_token("".join(held))                         # kept after all: show what was held back
                self.streamed = bool(on_token) and (live or bool(held))
                cut = " (cut off: the model went past its length limit)" if parsed.get("finish_reason") == "length" else ""
                answer = (parsed["content"] or "") + cut
                if used_tool and self.guard:
                    bad = unsupported_numbers(answer, [m["content"] for m in self.messages if m["role"] == "tool"])
                    if bad:
                        answer += ("\n\n(Check these numbers yourself: they are in no tool result, so the model may have "
                                   "misread or invented them: " + ", ".join(bad[:8]) + ")")
                return answer
            used_tool = True
            for call in parsed["tool_calls"]:
                self.messages.append(tool_message(
                    call["id"], call["name"], self.run_tool(call)))
        return ("(I stopped after "
                f"{self.max_turns} rounds of tool calls without a final answer. "
                "Ask again more narrowly, or raise --max-turns.)")


# --------------------------------------------------------------- the model server
def resolve_connection(base_url: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None):
    """The model server, model and key to use: what was asked for, else the environment, else the saved settings, else the
    defaults. Starts the private Ollama inside the vmd-agent folder if that is what setup chose."""
    from vmd_agent import settings
    base_url = base_url or os.environ.get(ENV_URL) or settings.get("llm_url") or DEFAULT_URL
    model = model or os.environ.get(ENV_MODEL) or settings.get("llm_model") or DEFAULT_MODEL
    api_key = api_key or os.environ.get(ENV_KEY) or settings.get("llm_key")
    if settings.get("ollama_mode") == "private" and base_url == ollama_local.url():
        ollama_local.start()                         # our own copy, inside the vmd-agent folder
    return base_url, model, api_key


def check_connection(base_url: str, model: str, api_key: Optional[str] = None) -> Optional[List[str]]:
    """None if the server answers and has the model; otherwise the lines that say what is wrong and what to do."""
    try:
        available = list_models(base_url, api_key)
    except LLMError as e:
        return [f"vmd-agent chat: {e}",
                "Start your model server first (for Ollama: `ollama serve`), or point "
                f"--base-url / ${ENV_URL} at it."]
    if available and model not in available:
        return [f"vmd-agent chat: the model '{model}' is not available on that server.",
                "Available: " + ", ".join(available[:12]) + ("" if len(available) <= 12 else ", ..."),
                f"For Ollama, install it with `ollama pull {model}`."]
    return None


# ----------------------------------------------------------------------- CLI
HELP = """commands:  /tools  list the tools    /time  where the time went    /reset  start over    /help    /quit
Ask in plain language, e.g. "what is in protein.pdb?" or "does the RMSD drift in run1.dcd?"."""


def main(base_url: Optional[str] = None, model: Optional[str] = None,
         api_key: Optional[str] = None, roots: Optional[List[str]] = None,
         max_turns: int = 20, temperature: float = 0.0,
         prompt: Optional[str] = None, check_model: bool = True, tools: str = "all", stream: bool = True,
         out=None, input_fn: Callable[[str], str] = input) -> int:
    """Run the chat. With ``prompt`` it answers once and exits; otherwise it is
    an interactive session. Returns a process exit code."""
    out = out or sys.stdout
    say = lambda m="": print(m, file=out, flush=True)
    base_url, model, api_key = resolve_connection(base_url, model, api_key)
    if roots:
        os.environ[security.ENV_ROOTS] = os.pathsep.join(
            os.path.realpath(r) for r in roots)
    rts = ensure_roots()

    problem = check_connection(base_url, model, api_key) if check_model else None
    if problem:
        for line in problem:
            say(line)
        return 2

    session = ChatSession(base_url, model, api_key, max_turns, temperature,
                          echo=say, tools=tools)

    def answer(question: str, lead: str = "") -> None:
        """Ask and show the answer: piece by piece as it is written when streaming, else all at once."""
        if not stream:
            say(lead + session.ask(question))
            say(f"  ({clock_line(session.last_turn)})")
            return
        shown: List[str] = []

        def piece(tok: str) -> None:
            if not shown and lead:
                out.write(lead)
            shown.append(tok)
            out.write(tok)
            out.flush()
        full = session.ask(question, on_token=piece)
        if session.streamed:
            rest = full[len("".join(shown)):] if full.startswith("".join(shown)) else ""
            out.write(rest + "\n")
            out.flush()
        else:
            say(lead + full)
        say(f"  ({clock_line(session.last_turn)})")
    try:
        if prompt:
            answer(prompt)
            return 0
    except LLMError as e:
        say(f"vmd-agent chat: {e}")
        return 1

    from vmd_agent.environment import find_vmd
    vmd = find_vmd()
    say(f"vmd-agent chat | model {model} @ {base_url}")
    say(f"data directory (the agent can only use files here): {rts[0]}")
    say("VMD: " + (vmd if vmd else "not found (figures use the built-in "
                                    "matplotlib renderer)"))
    say(HELP)
    while True:
        try:
            line = input_fn("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            say("")
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            return 0
        if line == "/help":
            say(HELP)
            continue
        if line == "/reset":
            session.reset()
            say("(conversation cleared)")
            continue
        if line == "/time":
            c = session.clock
            say(f"this conversation: {c['wall_s']:.1f} s in all; model {c['model_s']:.1f} s over {c['model_calls']} calls, "
                f"tools {c['tool_s']:.1f} s over {len(c['tool_calls'])} calls")
            slow = sorted(c["tool_calls"], key=lambda t: -t["seconds"])[:5]
            if slow:
                say("slowest tools: " + ", ".join(f"{t['name']} {t['seconds']:.1f} s" for t in slow))
            continue
        if line == "/tools":
            say(", ".join(session.names))
            continue
        try:
            answer(line, lead="\nagent> ")
        except LLMError as e:
            say(f"\n[model error] {e}")
        except KeyboardInterrupt:
            say("\n(interrupted)")

