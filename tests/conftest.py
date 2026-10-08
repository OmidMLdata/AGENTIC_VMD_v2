"""Shared fixtures: real structures, synthetic builders and real-tool gates.

Nothing here pretends to be another program. Tests that need VMD, Tachyon,
ffmpeg, the MCP SDK, a model API or the network use the real thing and are
**skipped, with the reason shown**, on a machine that does not have it. Run
``pytest -rs`` to see exactly what was skipped; a skipped test is a test that
did not run, not a test that passed.

* real VMD / Tachyon:  set ``VMD_BIN`` or install VMD; marker ``requires_vmd``
* real ffmpeg:         ``requires_ffmpeg``
* real MCP SDK:        Python >= 3.10 and ``pip install mcp``; ``requires_mcp``
* real model API:      ``VMD_AGENT_LIVE_TESTS=1`` and ``ANTHROPIC_API_KEY``
                       (spends a few cents); ``requires_api``
* real local model:    a running OpenAI-style server (e.g. Ollama) and
                       ``VMD_AGENT_LIVE_LLM_MODEL=<name>``; ``requires_llm``
* real network:        reachable rcsb.org; ``requires_network``
"""
import http.server
import json
import threading
import time
import os
import sys
import warnings

import numpy as np
import pytest

from vmd_agent.environment import find_ffmpeg

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SAMPLE_DIR = os.path.join(DATA, "sample")
UBQ_MD_DIR = os.path.join(DATA, "ubq_md")          # real 20 ns ubiquitin MD, 50 frames
UBQ_MD_FILES = (os.path.join(UBQ_MD_DIR, "protein.pdb"),
                os.path.join(UBQ_MD_DIR, "protein.dcd"))


# ------------------------------------------------------------ real structures
@pytest.fixture(scope="session")
def ubq():
    return os.path.join(DATA, "1ubq.pdb")          # ubiquitin, 76 res


@pytest.fixture(scope="session")
def lyz():
    return os.path.join(DATA, "1lyz.pdb")          # lysozyme, 4 disulfides


@pytest.fixture(scope="session")
def hbb():
    return os.path.join(DATA, "4hhb.pdb")          # hemoglobin + heme


@pytest.fixture(scope="session")
def whey():
    return os.path.join(DATA, "1beb.pdb")


@pytest.fixture(scope="session")
def sample():
    """Synthetic protein+ligand+ions+water system with an 8-frame DCD."""
    pdb = os.path.join(SAMPLE_DIR, "sample.pdb")
    dcd = os.path.join(SAMPLE_DIR, "sample.dcd")
    if not (os.path.exists(pdb) and os.path.exists(dcd)):
        sys.path.insert(0, SAMPLE_DIR)
        import make_sample
        make_sample.build()
    return pdb, dcd


# -------------------------------------------------------- synthetic builders
def pdb_text(atoms):
    """``atoms``: (name, resname, resid, chain, x, y, z, element) tuples."""
    out = []
    for i, (name, resn, resid, chain, x, y, z, el) in enumerate(atoms, 1):
        out.append(f"ATOM  {i:5d} {name:<4s} {resn:>3s} {chain}{resid:4d}    "
                   f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {el:>2s}")
    return "\n".join(out) + "\nEND\n"


@pytest.fixture
def write_pdb(tmp_path):
    def _write(atoms, name="x.pdb"):
        p = tmp_path / name
        p.write_text(pdb_text(atoms))
        return str(p)
    return _write


def backbone_atoms(n_res, phi, psi, chain="A", offset=(0.0, 0.0, 0.0)):
    """Idealised polyalanine backbone as PDB atom tuples (N, CA, C, O, CB)."""
    from vmd_agent.bench.synth import backbone_coords
    P = backbone_coords(n_res, phi, psi) + np.asarray(offset)
    atoms = []
    for r in range(n_res):
        for (name, el), q in zip((("N", "N"), ("CA", "C"), ("C", "C"),
                                  ("O", "O"), ("CB", "C")), P[r]):
            atoms.append((name, "ALA", r + 1, chain, q[0], q[1], q[2], el))
    return atoms


@pytest.fixture
def helix_pdb(write_pdb):
    return write_pdb(backbone_atoms(24, -57.0, -47.0), "helix.pdb")


@pytest.fixture
def strand_pdb(write_pdb):
    return write_pdb(backbone_atoms(12, -120.0, 130.0), "strand.pdb")


# ----------------------------------------------------------- real-tool gates
def _find_real_vmd():
    """Resolve VMD once, before any test edits the environment."""
    from vmd_agent.environment import find_vmd
    return find_vmd()


REAL_VMD = _find_real_vmd()


no_real_vmd = pytest.mark.skipif(
    REAL_VMD is not None,
    reason="a real VMD is installed here, so 'VMD absent' cannot be tested")


def _have_mcp():
    try:
        import mcp  # noqa: F401
        from vmd_agent import server  # noqa: F401
        return True
    except BaseException:                              # SystemExit when absent
        return False


_NET = {}


def have_network() -> bool:
    """Can this machine reach the structure databases the fetch code uses?"""
    if "ok" not in _NET:
        import socket
        try:
            for host in ("files.rcsb.org", "alphafold.ebi.ac.uk"):
                socket.create_connection((host, 443), timeout=4).close()
            _NET["ok"] = True
        except OSError:
            _NET["ok"] = False
    return _NET["ok"]


_LLM = {}


def have_llm() -> bool:
    """A real model server is reachable and a model is named for live tests:
    VMD_AGENT_LIVE_LLM_MODEL (and VMD_AGENT_LLM_URL unless it is Ollama's default)."""
    if "ok" not in _LLM:
        _LLM["ok"] = False
        model = os.environ.get("VMD_AGENT_LIVE_LLM_MODEL")
        if model:
            try:
                from vmd_agent.llm_client import list_models
                url = os.environ.get("VMD_AGENT_LLM_URL",
                                     "http://localhost:11434/v1")
                have = list_models(url, os.environ.get("VMD_AGENT_LLM_KEY"),
                                   timeout=4)
                _LLM["ok"] = (not have) or model in have
            except Exception:
                _LLM["ok"] = False
    return _LLM["ok"]


def pytest_report_header(config):
    from vmd_agent.environment import find_tachyon
    return [
        f"real VMD:     {REAL_VMD or 'NOT FOUND (requires_vmd tests will be skipped)'}",
        f"real Tachyon: {(find_tachyon(REAL_VMD) if REAL_VMD else None) or 'not found'}",
        f"real ffmpeg:  {find_ffmpeg() or 'NOT FOUND (requires_ffmpeg tests will be skipped)'}",
        f"real MCP SDK: {'yes' if _have_mcp() else 'NOT AVAILABLE (requires_mcp tests will be skipped)'}",
        f"real network: {'reachable' if have_network() else 'UNREACHABLE (requires_network tests will be skipped)'}",
        "live local-model tests: " + ("ON" if have_llm() else
                                      "off (set VMD_AGENT_LIVE_LLM_MODEL and run a model server)"),
        "live model API tests: " + ("ON" if os.environ.get("VMD_AGENT_LIVE_TESTS") == "1"
                                    and os.environ.get("ANTHROPIC_API_KEY") else "off"),
    ]


def pytest_collection_modifyitems(config, items):
    """Apply the gates for the markers, so a test says what it needs once."""
    skips = {
        "requires_vmd": (REAL_VMD is None, "no real VMD found (set VMD_BIN)"),
        "requires_ffmpeg": (find_ffmpeg() is None, "no real ffmpeg (not on PATH and imageio-ffmpeg missing)"),
        "requires_network": (not have_network(),
                             "cannot reach files.rcsb.org / alphafold.ebi.ac.uk"),
        "requires_llm": (not have_llm(),
                         "no reachable model server with VMD_AGENT_LIVE_LLM_MODEL set "
                         "(e.g. `ollama serve` and `ollama pull <model>`)"),
        "requires_mcp": (not _have_mcp(), "real MCP SDK not importable "
                         "(needs Python >= 3.10 and `pip install mcp`)"),
        "requires_api": (not (os.environ.get("VMD_AGENT_LIVE_TESTS") == "1"
                              and os.environ.get("ANTHROPIC_API_KEY")),
                         "live model tests are off (set VMD_AGENT_LIVE_TESTS=1 "
                         "and ANTHROPIC_API_KEY; this spends a few cents)"),
    }
    for item in items:
        for marker, (missing, why) in skips.items():
            if marker in item.keywords and missing:
                item.add_marker(pytest.mark.skip(reason=why))


@pytest.fixture(scope="session")
def real_vmd():
    """Path to a real VMD launcher (tests using this are marked requires_vmd)."""
    return REAL_VMD


@pytest.fixture(scope="session")
def real_tachyon(real_vmd):
    from vmd_agent.environment import find_tachyon
    t = find_tachyon(real_vmd)
    if not t:
        pytest.skip("VMD found but no Tachyon ray tracer next to it")
    return t


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Never read or write the developer's real vmd-agent settings."""
    monkeypatch.setenv("VMD_AGENT_CONFIG_DIR", str(tmp_path / "_vmd_agent_config"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Tests must not inherit a developer's sandbox settings (VMD_BIN is kept: the
    real VMD must stay discoverable)."""
    for k in ("VMD_AGENT_ALLOWED_ROOTS", "VMD_AGENT_ALLOW_UNSAFE_TCL",
              "VMD_AGENT_ALLOW_PRIVATE_URLS", "VMD_AGENT_ENABLE_TCL"):
        monkeypatch.delenv(k, raising=False)


# ---- a model server for tests of the agent: real HTTP, the chat API's wire format, scripted replies (no model is judged with it)
DELAY = 0.25


def scripted_server(replies):
    """Answers each POST with the next of ``replies`` (a dict: content and/or tool_calls) after DELAY seconds, as plain JSON."""
    calls = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
            time.sleep(DELAY)
            msg = {"role": "assistant", **replies[min(len(calls), len(replies)) - 1]}
            usage = {"prompt_tokens": 5, "completion_tokens": 2}
            if calls[-1].get("stream"):                       # the same reply as server-sent events, as streaming clients ask for
                delta = {k: v for k, v in msg.items() if k != "role" and v}
                if "tool_calls" in delta:
                    delta["tool_calls"] = [{"index": i, **c} for i, c in enumerate(delta["tool_calls"])]
                events = [{"choices": [{"delta": delta, "finish_reason": None}]},
                          {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": usage}]
                body = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"
                ctype = "text/event-stream"
            else:
                body = json.dumps({"choices": [{"message": msg, "finish_reason": "stop"}], "usage": usage}).encode()
                ctype = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1", calls
