"""The agent: a language model that uses the toolkit's tools to answer a question.

This is the one place where a model, the tools and the checks meet. It sends the model the tools it may use for the question, runs the
tool calls the model makes, feeds the results back, and loops until the model answers; it keeps the wall-clock of every model call and
every tool call, and every tool call's arguments and result. It prints nothing and knows nothing about screens: the terminal chat
(:mod:`vmd_agent.chat`), the web page (:mod:`vmd_agent.ui`), the model benchmark (:mod:`vmd_agent.model_bench`) are thin front ends on it, so
what the benchmark measures is what a person gets.

Whether a model does this *well* depends on the model: tool calling and multi-step analysis are hard for small models. What the agent adds
around the model is deliberate and each part can be switched off to measure the model alone:

* **routing** (``tools="auto"``): only the tools that fit the question are offered (:mod:`vmd_agent.routing`), not all of them;
* **argument repair** (:mod:`vmd_agent.argfix`): wrong types, wrong case, a missing or swapped file name are put right when it is unambiguous, and the model is told;
* **the guard**: a data question answered without a tool is sent back once; numbers no tool returned are flagged;
* **compact results**: what goes back to the model is shortened and stripped of housekeeping.

Safety defaults: if ``VMD_AGENT_ALLOWED_ROOTS`` is unset the agent is confined to the current directory; ``run_tcl`` stays disabled unless
``VMD_AGENT_ENABLE_TCL=1``.
"""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from vmd_agent import argfix, models, ollama_local, progress, routing, security, toolhints, toolset
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
8. Tools that run VMD itself save the exact Tcl they ran \
(`reproduce_script` in the result): mention it when the user may want to repeat the \
analysis in their own VMD, and offer export_session to hand over a scene as a \
folder they can open. Never write or paraphrase Tcl yourself: give only the path from \
`reproduce_script`. When the user asks what VMD can do, call probe_environment with plugins=true.
9. For a whole job (has a run settled, what interacts, compare two runs, prepare a simulation, fit a model into a map) call \
run_workflow (with no name it lists the workflows): it runs the steps, grades the findings and writes a report. Quote its verdict and findings and \
give the report path."""


_DATA_WORDS = re.compile(
    r"\.(pdb|psf|dcd|xtc|trr|gro|cif|mmcif|mol2|xyz|prmtop|nc|dx|mrc|ccp4|cube|mp4|png)\b|"
    r"\b(measure|analy[sz]e|rmsd|rmsf|radius of gyration|salt bridges?|hydrogen bonds?|h-bonds?|contacts?|secondary structure|"
    r"render|draw|plot|build|solvate|mutate|trajector(?:y|ies)|simulations?|runs?|frames?|disulfides?|ligands?|box|density|plugins?)\b",
    re.I)

#: a number, with thousands groups ("127 906", "1,280", written with a space, comma or narrow space) read as one number; an exponent only when no letter follows it
#: (a hex-like word such as 2e408ce5 is not 2 x 10^408)
_NUM = re.compile(r"(?<![\w.])-?(?:\d{1,3}(?:[ ,\u202f\u00a0]\d{3})+(?![\d])(?:\.\d+)?|\d+(?:\.\d+)?(?:[eE][-+]?\d+(?![A-Za-z\d]))?)")


#: what is not a claim about a measurement: a path (anything with a slash) and an identifier made of hex groups
_NOT_NUMBERS = re.compile(r"\S*[/\\]\S*|\b[0-9a-fA-F]{6,}(?:-[0-9a-fA-F]{2,})+\b")


def numbers(text: str):
    out = []
    for m in _NUM.finditer(_NOT_NUMBERS.sub(" ", text)):
        tok = re.sub(r"[ ,\u202f\u00a0](?=\d{3})", "", m.group(0)) if re.search(r"\d[ ,\u202f\u00a0]\d{3}", m.group(0)) else m.group(0)
        try:
            out.append((float(tok), len(tok.split(".")[1].split("e")[0].split("E")[0]) if "." in tok else 0))
        except ValueError:
            pass
    return out


def unsupported_numbers(answer: str, tool_texts) -> List[str]:
    """Numbers in a model's answer that appear in no tool result. A decimal number counts as supported if some
    tool number matches it at the precision the answer shows (also as a percentage, x100); integers below 100 are
    ignored (counts, indices, step sizes). A small model that misreads a result shows up here."""
    have = [v for t in tool_texts for v, _ in numbers(t)]
    bad: List[str] = []
    for v, dec in numbers(re.sub(r"```.*?```", "", answer, flags=re.S)):
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


#: a question that is a list of statements to be judged true or false: verify_claims does exactly that, and a model reading detect_system's fields instead can misjudge them
_CLAIMS = re.compile(r"\b(which (of (these|them)|ones?) (are|is) (true|correct)|(are|is) (these|this|it|that) (true|correct)|true or false|check (these|the following|whether|that)\b.{0,40}\b(statements?|claims?)|"
                     r"(statements?|claims?) about|verify (these|the following|that))\b", re.I)


def claims_hint(text: str) -> bool:
    return bool(_CLAIMS.search(text))


GROUND = ("Some numbers in your answer are in no tool result: {numbers}. Use only what the tools returned. If the question cannot be answered "
          "with the tools you have, say so plainly instead of estimating.")

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


# ------------------------------------------------------------------ what goes back to the model
#: bookkeeping a model does not need and a small one is distracted by; the result kept in ``call_log`` still has them
_HOUSEKEEPING = ("reproduce_with", "how_to_view", "tachyon_stderr", "ffmpeg_stderr")


def digest(result):
    """A tool result as the model sees it: without bookkeeping fields (the saved script's path, ``reproduce_script``, stays)."""
    if isinstance(result, dict):
        kept = {k: digest(v) for k, v in result.items() if not (k in _HOUSEKEEPING and (not v or k in ("reproduce_with", "how_to_view")))}
        if "n_protein_chains" in kept:                                  # n_chains_all counts the ligand's segment too and was read as "2 chains" for one protein chain
            kept.pop("n_chains_all", None)
        if isinstance(kept.get("summary"), str):                       # the plain sentence first: it is what a small model reads best
            kept = {"summary": kept.pop("summary"), **kept}
        return kept
    if isinstance(result, list):
        return [digest(v) for v in result]
    return result


def _choices():
    """The allowed values of the tools' choice parameters (the same table the command line uses)."""
    from vmd_agent import toolhints
    return toolhints.CHOICES


@dataclass
class Result:
    """What one question produced: the answer, every tool call it made (name, arguments as run, result, seconds, corrections), the wall-clock
    split into the model's time and the tools', the tokens, and which tools were added to the offered set during the question."""
    answer: str
    calls: List[dict] = field(default_factory=list)
    clock: dict = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    widened: List[str] = field(default_factory=list)
    streamed: bool = False


# ------------------------------------------------------------------ session
class Agent:
    """A conversation with a model that can call the toolkit's tools."""

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None,
                 max_turns: int = 20, temperature: float = 0.0,
                 system: str = SYSTEM_PROMPT,
                 echo: Optional[Callable[[str], None]] = None,
                 max_history_chars: int = 60000, timeout: float = 900.0,
                 tools: str = "all", guard: bool = True, max_tokens: int = 3000, repair: bool = True):
        self.base_url, self.model, self.api_key = base_url, model, api_key
        self.max_turns, self.temperature = max_turns, temperature
        self.max_history_chars, self.timeout = max_history_chars, timeout
        self.system = system
        self.guard = guard
        self.max_tokens = max_tokens          # a model that rambles or repeats itself is cut off, not waited for
        self.echo = echo or (lambda m: None)
        if tools not in ("all", "auto"):
            raise ValueError("tools must be 'all' or 'auto'")
        self.profile = tools
        self.names = list(toolset.ALL)     # what is offered now; "auto" narrows it per question
        self.repair = repair                   # put unambiguous argument mistakes right (and say so); off to measure the model alone
        self.widened: List[str] = []           # tools added after the router's choice, because the model asked for them
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.clock = new_clock()               # wall-clock of the whole session
        self.last_turn: dict = new_clock()     # wall-clock of the latest question
        self.turn: dict = self.last_turn
        self.call_log: List[dict] = []         # every tool call so far: name, arguments, the result as returned, seconds
        self.on_event: Optional[Callable[[dict], None]] = None   # structured events for a screen (the web page); see _emit
        self.reset()

    @property
    def tools(self) -> List[dict]:
        """The tool descriptions sent with the next request: what is offered now, and in "auto" the way to ask for more."""
        specs = toolhints.enrich(toolset.tool_specs(self.names))
        if self.profile == "auto":
            meta = routing.offer_spec(self.names, list(toolset.TOOLS))
            if meta:
                specs = specs + [meta]
        return to_openai_tools(specs)

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
        if name == routing.OFFER and self.profile == "auto":
            return self._offer(args.get("group"))
        if name in toolset.TOOLS and name not in self.names and self.profile == "auto":
            self.names.append(name)                                    # the model remembered a tool the router did not offer: allow it
            self.widened.append(name)
            self.echo(f"  (the tool {name} was not offered for this question; allowed)")
        fn = toolset.TOOLS.get(name) if name in self.names else None
        if fn is None:
            return render_result({"error": f"unknown tool '{name}'",
                                  "available": self.names})
        notes: List[str] = []
        if self.repair:
            args, notes = argfix.fix(name, args, toolset.tool_schema(fn)["input_schema"], _choices(), argfix.list_files(self.root()))
            if notes:
                self.echo("     arguments put right: " + "; ".join(notes))
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
        if notes and isinstance(result, dict):
            result = {**result, "note_on_arguments": "; ".join(notes)}
        self.call_log.append({"name": name, "arguments": args, "result": result, "seconds": round(seconds, 3), "repairs": notes})
        self.echo(f"     {seconds:.1f} s")
        failed = isinstance(result, dict) and bool(result.get("error"))
        if failed:
            self.echo(f"     ! {str(result['error'])[:140]}")
        self._emit(type="tool_end", name=name, seconds=round(seconds, 3), error=str(result["error"])[:300] if failed else None,
                   result=result)
        return render_result(digest(result))

    def _offer(self, group) -> str:
        added = routing.offer(str(group), self.names, list(toolset.TOOLS))
        if not added:
            return render_result({"error": f"no more tools in the group '{group}'", "offered": self.names})
        self.names += added
        self.widened += added
        self.echo(f"  (offered the group '{group}': {', '.join(added)})")
        return render_result({"ok": True, "now_offered": added})

    def root(self) -> str:
        """The folder the agent works in: the first allowed root, else the current directory."""
        return (security.allowed_roots() or [os.getcwd()])[0]

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
    def run(self, text: str, on_token: Optional[Callable[[str], None]] = None) -> Result:
        """:meth:`ask`, with everything about the question returned (see :class:`Result`)."""
        before, used = len(self.call_log), dict(self.usage)
        answer = self.ask(text, on_token)
        return Result(answer, self.call_log[before:], self.last_turn, self.usage["input_tokens"] - used["input_tokens"],
                      self.usage["output_tokens"] - used["output_tokens"], list(self.widened), bool(self.streamed))

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
        if self.profile == "auto":
            self.names = routing.select(text, list(toolset.ALL))
            self.widened = []
            self.echo(f"  (offering {len(self.names)} of {len(toolset.ALL)} tools for this question)")
        hint = route(text) if "run_workflow" in self.names else None
        note = ""
        if hint:
            note = (f"\n\n[hint from the toolkit: the workflow `{hint}` answers this question properly (several checks, graded findings, a report). "
                    f"Call run_workflow with name=\"{hint}\" and the file names from the question.]")
            self.echo(f"  (the workflow '{hint}' fits this question)")
        elif "verify_claims" in self.names and claims_hint(text):
            note = ("\n\n[hint from the toolkit: these are statements to be judged true or false. Call verify_claims with each statement as a plain sentence "
                    "in `claims`, and report its verdicts.]")
            self.echo("  (verify_claims fits this question)")
        self.messages.append({"role": "user", "content": text + note})
        used_tool = nudged = regrounded = False
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
                    bad = unsupported_numbers(answer, [m["content"] for m in self.messages if m["role"] == "tool"] + [text])
                    if bad and not regrounded and not on_token:
                        # numbers that no tool returned: send the answer back once. (An answer delivered piece by piece has already been shown, so there it is only flagged below.)
                        regrounded = True
                        self.echo("  (the answer has numbers no tool returned; asking the model to correct it)")
                        self.messages.append({"role": "user", "content": GROUND.format(numbers=", ".join(bad[:8]))})
                        continue
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


