"""Progress for long jobs: a tool says what it is doing, whoever called it decides how to show that.

A tool (building a system, rendering a movie, walking a long trajectory) calls :func:`report`. The caller wraps the call
in :func:`listen` to receive the messages: the command line prints them to the terminal, the chat shows them under the
tool call. Nothing is shown unless somebody is listening, and a listener that fails can never break the tool.

Nothing here imports the rest of the package.
"""
from __future__ import annotations

import contextvars
import sys
import time
from contextlib import contextmanager
from typing import Callable, Optional

Listener = Callable[[str, Optional[float]], None]
_listeners: contextvars.ContextVar = contextvars.ContextVar("vmd_agent_progress", default=())


def report(message: str, fraction: Optional[float] = None) -> None:
    """Tell the listeners what is happening now. ``fraction`` (0 to 1) says how far along it is, when known."""
    for fn in _listeners.get():
        try:
            fn(message, fraction)
        except Exception:                      # a broken display must not break the analysis
            pass


@contextmanager
def listen(callback: Listener):
    """Deliver the progress of everything called inside the ``with`` block to ``callback(message, fraction)``."""
    token = _listeners.set(_listeners.get() + (callback,))
    try:
        yield
    finally:
        _listeners.reset(token)


def terminal(stream=None, prefix: str = "  ... ") -> Listener:
    """A listener that prints one line per message, with the seconds elapsed since it was made."""
    out = stream or sys.stderr
    start = time.time()

    def show(message: str, fraction: Optional[float] = None) -> None:
        pct = f" ({int(round(fraction * 100))}%)" if fraction is not None else ""
        print(f"{prefix}{message}{pct}   [{time.time() - start:.0f} s]", file=out, flush=True)
    return show
