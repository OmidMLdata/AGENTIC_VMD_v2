"""Progress for long jobs: a tool says what it is doing, the caller decides how to show it."""
import io
import os

import pytest

from vmd_agent import agent, progress

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
PDB, DCD = os.path.join(DATA, "ubq_md", "protein.pdb"), os.path.join(DATA, "ubq_md", "protein.dcd")


def test_nothing_happens_without_a_listener_and_listeners_nest_and_end():
    progress.report("nobody is listening")                       # must not raise
    seen, inner = [], []
    with progress.listen(lambda m, f=None: seen.append(m)):
        progress.report("one")
        with progress.listen(lambda m, f=None: inner.append(m)):
            progress.report("two")
        progress.report("three")
    progress.report("after")
    assert seen == ["one", "two", "three"] and inner == ["two"]


def test_a_broken_listener_cannot_break_the_work():
    def bad(message, fraction=None):
        raise RuntimeError("the display crashed")
    with progress.listen(bad):
        progress.report("still fine")


def test_the_terminal_listener_prints_a_line_with_the_time():
    out = io.StringIO()
    with progress.listen(progress.terminal(out)):
        progress.report("solvating", 0.5)
    assert "solvating (50%)" in out.getvalue() and "[0 s]" in out.getvalue()


@pytest.mark.requires_vmd
def test_progress_written_by_a_running_vmd_reaches_the_listener():
    """A real VMD run walks 50 frames; its progress lines arrive at the listener, in order, before the result."""
    from vmd_agent.vmdkit import measure
    seen = []
    with progress.listen(lambda m, f=None: seen.append(m)):
        r = measure.measure(PDB, DCD, kind="rgyr")
    assert r["ok"] and seen[0] == "frame 5 of 50" and seen[-1] == "frame 50 of 50" and len(seen) == 10


@pytest.mark.requires_vmd
def test_the_chat_shows_a_tools_progress_under_the_call(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    for f in (PDB, DCD):
        shutil.copy(f, tmp_path)
    lines = []
    s = agent.Agent("http://127.0.0.1:1/v1", "m", echo=lines.append)
    s.run_tool({"id": "1", "name": "vmd_measure", "arguments": {"topology": "protein.pdb", "trajectory": "protein.dcd", "kind": "rgyr"}})
    assert any("frame 25 of 50" in m for m in lines) and lines[0].lstrip().startswith("->")
