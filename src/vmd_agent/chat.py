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
from typing import Callable, List, Optional

from vmd_agent import models, ollama_local, security, toolset
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
`reproduce_script`. When the user asks what VMD can do, call vmd_capabilities."""


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
        self.reset()

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
        try:
            result = fn(**args)
        except TypeError as e:
            expected = toolset.tool_schema(fn)["input_schema"]
            result = {"error": f"bad arguments for {name}: {e}",
                      "parameters": expected["properties"],
                      "required": expected["required"]}
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        if isinstance(result, dict) and result.get("error"):
            self.echo(f"     ! {str(result['error'])[:140]}")
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
    def ask(self, text: str) -> str:
        self.messages.append({"role": "user", "content": text})
        used_tool = nudged = False
        for _ in range(self.max_turns):
            self._trim()
            resp = chat_completion(self.base_url, self.model, self.messages,
                                   tools=self.tools, api_key=self.api_key,
                                   temperature=self.temperature,
                                   timeout=self.timeout, max_tokens=self.max_tokens,
                                   tool_choice="required" if nudged and not used_tool else None)
            parsed = parse_choice(resp, self.names)
            for k in self.usage:
                self.usage[k] += parsed["usage"][k]
            if not parsed["tool_calls"] and self.guard and not used_tool and not nudged \
                    and _DATA_WORDS.search(text):
                # a question about data answered from memory: send it back once, and require a tool call
                self.echo("  (the model answered without a tool; asking it to use one)")
                self.messages.append({"role": "user", "content": NUDGE})
                nudged = True
                continue
            self.messages.append(assistant_message(parsed))
            if not parsed["tool_calls"]:
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


# ----------------------------------------------------------------------- CLI
HELP = """commands:  /tools  list the tools    /reset  start over    /help    /quit
Ask in plain language, e.g. "what is in protein.pdb?" or "does the RMSD drift in run1.dcd?"."""


def main(base_url: Optional[str] = None, model: Optional[str] = None,
         api_key: Optional[str] = None, roots: Optional[List[str]] = None,
         max_turns: int = 20, temperature: float = 0.0,
         prompt: Optional[str] = None, check_model: bool = True, tools: str = "all",
         out=None, input_fn: Callable[[str], str] = input) -> int:
    """Run the chat. With ``prompt`` it answers once and exits; otherwise it is
    an interactive session. Returns a process exit code."""
    out = out or sys.stdout
    say = lambda m="": print(m, file=out, flush=True)
    from vmd_agent import settings
    base_url = (base_url or os.environ.get(ENV_URL) or settings.get("llm_url")
                or DEFAULT_URL)
    model = (model or os.environ.get(ENV_MODEL) or settings.get("llm_model")
             or DEFAULT_MODEL)
    api_key = api_key or os.environ.get(ENV_KEY) or settings.get("llm_key")
    if settings.get("ollama_mode") == "private" and base_url == ollama_local.url():
        ollama_local.start()                         # our own copy, inside the vmd-agent folder
    if roots:
        os.environ[security.ENV_ROOTS] = os.pathsep.join(
            os.path.realpath(r) for r in roots)
    rts = ensure_roots()

    try:
        available = list_models(base_url, api_key) if check_model else []
    except LLMError as e:
        say(f"vmd-agent chat: {e}")
        say("Start your model server first (for Ollama: `ollama serve`), or point "
            f"--base-url / ${ENV_URL} at it.")
        return 2
    if check_model and available and model not in available:
        say(f"vmd-agent chat: the model '{model}' is not available on that server.")
        say("Available: " + ", ".join(available[:12]) +
            ("" if len(available) <= 12 else ", ..."))
        say(f"For Ollama, install it with `ollama pull {model}`.")
        return 2

    session = ChatSession(base_url, model, api_key, max_turns, temperature,
                          echo=say, tools=tools)
    try:
        if prompt:
            say(session.ask(prompt))
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
        if line == "/tools":
            say(", ".join(session.names))
            continue
        try:
            say("\nagent> " + session.ask(line))
        except LLMError as e:
            say(f"\n[model error] {e}")
        except KeyboardInterrupt:
            say("\n(interrupted)")

