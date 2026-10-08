"""``vmd-agent chat``: the terminal front end of the agent (:mod:`vmd_agent.agent`).

It prints what the agent does (each tool call with its progress and seconds, the answer as it is written, where the time went) and reads
questions from the keyboard. Nothing about choosing tools, running them or checking answers is here.
"""
from __future__ import annotations

import os
import sys
from typing import Callable, List, Optional

from vmd_agent import security
from vmd_agent.agent import (Agent, check_connection, clock_line, ensure_roots,
                             resolve_connection)
from vmd_agent.llm_client import LLMError


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

    session = Agent(base_url, model, api_key, max_turns, temperature,
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

