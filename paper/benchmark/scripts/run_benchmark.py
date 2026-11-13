#!/usr/bin/env python3
"""Claude Opus 5.5 vs two open models on vmd-agent's own model benchmark, with everything but the model held fixed.

Same agent loop, same tasks, same tool offering (`auto`), same guard, same turn limit, same number of repeats. Only the model
and its server differ. A program grades every answer (no model judges another).

Run it from your vmd-agent checkout with its .venv active:

    python run_benchmark.py --phase check      # servers, models, key; writes nothing
    python run_benchmark.py --phase oracle     # the benchmark checked against itself (no model)
    python run_benchmark.py --phase smoke      # the small set, once per model (minutes to an hour)
    python run_benchmark.py --phase full       # every task, 3 repeats per model (hours; run it overnight)

Every phase can be stopped and started again: runs already recorded are skipped. A run that failed because a server
did not answer (rate limit, timeout, network) is set aside in errors.jsonl and asked again, so it never counts as a
wrong answer. The API key is read from ANTHROPIC_API_KEY or asked for, and is never written to disk.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request

try:
    from vmd_agent import __version__ as VMD_AGENT_VERSION
    from vmd_agent import model_bench as B, model_tasks as M, settings
    from vmd_agent.environment import find_vmd
    from vmd_agent.llm_client import LLMError, list_models
except ImportError:
    sys.exit("vmd-agent is not importable. In your checkout run:  source .venv/bin/activate   then try again.")

ANTHROPIC_URL = "https://api.anthropic.com/v1"
CLAUDE = "claude-opus-5-5"
OPEN_MODELS = ["granite4.1:8b", "gemma4:e4b"]

# What is held fixed for every model. `auto` and the guard are vmd-agent's defaults, i.e. what a user gets.
TOOLS, GUARD, MAX_TURNS = "auto", True, 12
OPEN_TEMPERATURE = 0.0            # vmd-agent's default for open models
REPEATS = {"smoke": 1, "full": 3}


def say(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


# ------------------------------------------------------------------ servers
def ollama_url(override: str | None) -> str:
    if override:
        return override
    if settings.get("ollama_mode") == "private":            # setup installed vmd-agent's own Ollama
        from vmd_agent import ollama_local
        ollama_local.start()
        return ollama_local.url()
    return "http://localhost:11434/v1"


def ollama_root(url: str) -> str:
    url = url.rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def ollama_json(url: str, path: str, body: dict | None = None, timeout: float = 60) -> dict:
    req = urllib.request.Request(ollama_root(url) + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def unload(url: str, model: str) -> None:
    """Free a model's memory before the next one loads, so two models never share 16 GB (that would slow both)."""
    try:
        ollama_json(url, "/api/generate", {"model": model, "keep_alive": 0})
    except Exception as e:                                   # not fatal: Ollama frees idle models by itself
        say(f"  (could not unload {model}: {e})")


def anthropic_key(key_file: str | None = None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("VMD_AGENT_LLM_KEY")
    if not key and key_file:                                 # for unattended runs (e.g. over SSH): a file only you can read
        path = os.path.expanduser(key_file)
        if not os.path.isfile(path):
            sys.exit(f"No key file at {path}")
        if os.stat(path).st_mode & 0o077:
            sys.exit(f"{path} can be read by other users; run:  chmod 600 {path}")
        key = open(path).read().strip()
    if not key and not sys.stdin.isatty():
        sys.exit("No API key: set ANTHROPIC_API_KEY or pass --key-file (this run cannot ask, it has no terminal).")
    if not key:
        key = getpass.getpass("Anthropic API key (workspace-scoped; input hidden, not saved): ").strip()
    if not key:
        sys.exit("No API key given.")
    return key


# ------------------------------------------------------------------ what was run, for the methods section
def sh(cmd: list, cwd: str | None = None) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd).stdout.strip()
    except Exception:
        return ""


def manifest(out_dir: str, phase: str, ourl: str) -> dict:
    here = os.getcwd()
    try:
        tags = {m["name"]: {"digest": m.get("digest"), "size_bytes": m.get("size"),
                            "quantization": (m.get("details") or {}).get("quantization_level"),
                            "parameter_size": (m.get("details") or {}).get("parameter_size")}
                for m in ollama_json(ourl, "/api/tags").get("models", []) if m["name"] in OPEN_MODELS}
        oversion = ollama_json(ourl, "/api/version").get("version")
    except Exception:
        tags, oversion = {}, None
    mem = sh(["sysctl", "-n", "hw.memsize"])
    m = {
        "phase": phase, "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "vmd_agent_version": VMD_AGENT_VERSION,
        "git_commit": sh(["git", "rev-parse", "HEAD"], here),
        "git_dirty": bool(sh(["git", "status", "--porcelain", "--untracked-files=no"], here)),   # tracked files only: the kit itself is untracked
        "tcl_enabled": os.environ.get("VMD_AGENT_ENABLE_TCL") == "1", "unsafe_tcl": os.environ.get("VMD_AGENT_ALLOW_UNSAFE_TCL") == "1",
        "python": platform.python_version(), "os": platform.platform(),
        "cpu": sh(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor(),
        "memory_gb": round(int(mem) / 2**30, 1) if mem.isdigit() else None,
        "vmd": find_vmd(), "ollama_version": oversion, "ollama_url": ourl,
        "n_tasks_defined": len(M.TASKS), "smoke_tasks": list(M.SMOKE),
        "held_fixed": {"tools": TOOLS, "guard": GUARD, "max_turns": MAX_TURNS, "repeats": REPEATS.get(phase)},
        "conditions": [
            *[{"model": t, "server": "Ollama (local)", "temperature": OPEN_TEMPERATURE, "weights": tags.get(t)} for t in OPEN_MODELS],
            {"model": CLAUDE, "server": "Anthropic API (OpenAI-compatible endpoint)",
             "temperature": "not sent: vmd-agent omits it for api.anthropic.com, so the API default applies"},
        ],
    }
    with open(os.path.join(out_dir, f"manifest_{phase}.json"), "w") as fh:
        json.dump(m, fh, indent=1)
    return m


# ------------------------------------------------------------------ runs
def set_aside_errors(out_dir: str, model: str) -> int:
    """Move this model's server-failure records to errors.jsonl so they are asked again. Returns how many."""
    path = os.path.join(out_dir, B.RECORDS)
    if not os.path.isfile(path):
        return 0
    keep, bad = [], []
    for r in B.load_records(out_dir):
        (bad if r.get("model") == model and r.get("error") else keep).append(r)
    if bad:
        with open(os.path.join(out_dir, "errors.jsonl"), "a") as fh:
            for r in bad:
                fh.write(json.dumps({**r, "set_aside_utc": dt.datetime.now(dt.timezone.utc).isoformat()}, default=str) + "\n")
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            for r in keep:
                fh.write(json.dumps(r, default=str) + "\n")
        os.replace(tmp, path)
    return len(bad)


def run_model(model: str, url: str, key, temperature: float, phase: str, data_dir: str, out_dir: str,
              retries: int, wait_s: int) -> None:
    only = list(M.SMOKE) if phase == "smoke" else None
    n = 0
    for attempt in range(retries + 1):
        B.run([model], data_dir, out_dir, url, key, only=only, repeats=REPEATS[phase], tools=TOOLS, max_turns=MAX_TURNS,
              temperature=temperature, guard=GUARD, log=say)
        n = set_aside_errors(out_dir, model)
        if not n:
            return
        if attempt < retries:
            say(f"{model}: {n} run(s) failed at the server; asking again in {wait_s} s (attempt {attempt + 2} of {retries + 1})")
            time.sleep(wait_s)
    say(f"{model}: {n} run(s) still failed at the server; they are in errors.jsonl and are NOT counted. Re-run this phase later.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase", required=True, choices=["check", "oracle", "smoke", "full"])
    p.add_argument("--out", default="bench_runs", help="results go to <out>/<phase>/")
    p.add_argument("--ollama-url", help="default: vmd-agent's private Ollama if setup chose it, else http://localhost:11434/v1")
    p.add_argument("--models", nargs="+", default=OPEN_MODELS + [CLAUDE], help="a subset of the three, e.g. to add one later")
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--wait", type=int, default=90, help="seconds before asking failed runs again")
    p.add_argument("--key-file", help="file holding the Anthropic API key (chmod 600); for runs without a terminal")
    a = p.parse_args()
    bad = [m for m in a.models if m not in OPEN_MODELS + [CLAUDE]]
    if bad:
        sys.exit("Unknown model(s): " + ", ".join(bad) + ". This study compares " + ", ".join(OPEN_MODELS + [CLAUDE]))

    if os.environ.get("VMD_AGENT_ENABLE_TCL") == "1" or os.environ.get("VMD_AGENT_ALLOW_UNSAFE_TCL") == "1":
        sys.exit("Tcl is switched on in this shell (VMD_AGENT_ENABLE_TCL / VMD_AGENT_ALLOW_UNSAFE_TCL). The benchmark tests that it is off:\n"
                 "  unset VMD_AGENT_ENABLE_TCL VMD_AGENT_ALLOW_UNSAFE_TCL\nthen run this again.")
    ourl = ollama_url(a.ollama_url)
    out_dir = os.path.abspath(os.path.join(a.out, a.phase))
    data_dir = os.path.abspath(os.path.join(a.out, "_data"))
    os.makedirs(out_dir, exist_ok=True)

    if a.phase == "oracle":
        say("oracle: every task done perfectly with the real tools, graded by its own grader")
        rows = B.run_oracle(data_dir, log=say)
        with open(os.path.join(out_dir, "oracle.json"), "w") as fh:
            json.dump(rows, fh, indent=1, default=str)
        failed = [r["task"] for r in rows if r["passed"] is False]
        skipped = [r["task"] for r in rows if r["passed"] is None]
        say(f"oracle: {sum(r['passed'] is True for r in rows)} passed, {len(failed)} failed, {len(skipped)} skipped")
        if failed:
            say("A task a perfect agent fails is a bug in the task: fix it before the full run. Failed: " + ", ".join(failed))
        manifest(out_dir, a.phase, ourl)
        return 1 if failed else 0

    # check servers and models before spending hours
    want_open = [m for m in a.models if m in OPEN_MODELS]
    key = None
    if want_open:
        try:
            have = list_models(ourl)
        except LLMError as e:
            sys.exit(f"Ollama does not answer at {ourl}: {e}\nStart it (the Ollama app, or `ollama serve`) and try again.")
        missing = [m for m in want_open if m not in have]
        if missing:
            sys.exit("Not downloaded yet: " + ", ".join(missing) + "\nRun:  " + "   ".join(f"ollama pull {m}" for m in missing))
        say(f"Ollama at {ourl}: {', '.join(want_open)} present")
    if CLAUDE in a.models:
        key = anthropic_key(a.key_file)
        try:
            ids = list_models(ANTHROPIC_URL, key)
        except LLMError as e:
            sys.exit(f"The Anthropic API refused the key: {e}")
        if ids and CLAUDE not in ids:
            sys.exit(f"{CLAUDE} is not offered to this key. Offered: {', '.join(ids[:12])}")
        say(f"Anthropic API: {CLAUDE} available")
    if a.phase == "check":
        say("everything needed is there")
        return 0

    m = manifest(out_dir, a.phase, ourl)
    if m["git_dirty"]:
        say("note: tracked files in the checkout have uncommitted changes; the manifest records that (git diff shows them)")
    for model in a.models:
        if model in OPEN_MODELS:
            for other in OPEN_MODELS:
                if other != model:
                    unload(ourl, other)
            run_model(model, ourl, None, OPEN_TEMPERATURE, a.phase, data_dir, out_dir, a.retries, a.wait)
            unload(ourl, model)
        else:
            run_model(model, ANTHROPIC_URL, key, 0.0, a.phase, data_dir, out_dir, a.retries, a.wait)   # 0.0 is not sent
    B.write_summary(out_dir)
    say(f"done. Records: {os.path.join(out_dir, B.RECORDS)}   Summary: {os.path.join(out_dir, 'summary.md')}")
    say("Send records.jsonl, manifest_*.json and errors.jsonl (if any) for the analysis and the figure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
