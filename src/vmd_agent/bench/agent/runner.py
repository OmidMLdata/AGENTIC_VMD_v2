"""Run agents on a task suite, score them, and summarise.

A *run spec* is ``{"label": str, "agent": agent, "arm": str}``: which agent, with
which tools. Each (task, label, repeat) executes in a **fresh copy** of the
task workspace, so agents cannot see each other's files and leftover outputs
cannot be mistaken for new work.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from typing import Callable, List, Optional, Sequence


from vmd_agent.bench.agent import suite as S
from vmd_agent.bench.agent.scoring import (
    score_task, summarize_agents)
from vmd_agent.bench.agent.tools import ARMS, Environment, NEEDS_EXEC


def selection_syntax_for(arm: str) -> str:
    """Selections are written in the syntax of the tool the arm has: VMD's for
    the plain-VMD arm, MDAnalysis' otherwise."""
    return "vmd" if arm == "vmd_plain" else "mdanalysis"


def _stage(task: dict, dest: str, syntax: str = "mdanalysis") -> dict:
    """Copy the workspace to ``dest`` and return the task re-pointed at it."""
    old = task["workdir"]
    shutil.copytree(old, dest)
    t = dict(task)
    t["workdir"] = dest
    t["files"] = {k: v.replace(old, dest) for k, v in task["files"].items()}
    t["prompt"] = task["prompt"].replace(old, dest)
    if syntax == "vmd":
        t["prompt"] = t["prompt"].replace("MDAnalysis selection string",
                                          "VMD atom-selection string")
    return t


def run_agent_benchmark(suite_dir: str, runs: Sequence[dict], out_dir: str,
                        repeats: int = 1, allow_exec: bool = False,
                        vmd_path: Optional[str] = None, max_steps: int = 30,
                        families: Optional[Sequence[str]] = None,
                        n_boot: int = 1000, seed: int = 0,
                        progress: Optional[Callable[[str], None]] = None
                        ) -> dict:
    log = progress or (lambda m: None)
    suite = S.load_suite(suite_dir)
    tasks = [t for t in suite["tasks"]
             if not families or t["family"] in families]
    changed = S.verify_suite_files(tasks)
    if changed:
        raise ValueError(
            "the suite's files changed since it was generated (or are "
            f"missing): {changed[:5]}{' ...' if len(changed) > 5 else ''}. "
            "Results would not be comparable; regenerate or restore the suite.")
    labels = [r["label"] for r in runs]
    if len(set(labels)) != len(labels):
        raise ValueError("run labels must be unique")
    for r in runs:
        if r["arm"] not in ARMS:
            raise ValueError(f"unknown arm '{r['arm']}'; choose from "
                             f"{sorted(ARMS)}")
        if set(ARMS[r["arm"]]) & NEEDS_EXEC and not allow_exec:
            raise ValueError(
                f"arm '{r['arm']}' needs code execution; pass allow_exec=True "
                "and run inside a container or VM")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    recs: List[dict] = []
    with open(os.path.join(out_dir, "records.jsonl"), "w") as fh:
        for run in runs:
            agent = run["agent"]
            for task in tasks:
                for rep in range(repeats):
                    dest = os.path.join(out_dir, "runs", run["label"],
                                        task["id"], str(rep))
                    syntax = selection_syntax_for(run["arm"])
                    staged = _stage(task, dest, syntax)
                    env = Environment(staged, run["arm"], allow_exec,
                                      vmd_path, max_steps)
                    view = staged if getattr(agent, "scripted", False) \
                        else S.public_view(staged)
                    log(f"{run['label']} {task['id']} #{rep}")
                    t0 = time.time()
                    try:
                        meta = agent.run(view, env) or {}
                        err = None
                    except Exception as e:           # agent crash: a failure
                        meta, err = {}, f"{type(e).__name__}: {e}"
                    sc = score_task(staged, suite["truth"][task["id"]],
                                    env.submitted, syntax, vmd_path)
                    rec = {**sc, "label": run["label"], "arm": run["arm"],
                           "agent": getattr(agent, "name", "?"),
                           "repeat": rep, **env.stats(),
                           "tokens_in": meta.get("tokens_in"),
                           "tokens_out": meta.get("tokens_out"),
                           "model_s": meta.get("model_s"), "model_calls": meta.get("model_calls"),
                           "agent_error": err,
                           "wall_s": round(time.time() - t0, 2)}
                    recs.append(rec)
                    fh.write(json.dumps(rec, default=str) + "\n")
                    fh.flush()
    summary = summarize_agents(recs, "label", n_boot, seed)
    manifest = build_manifest(suite_dir, runs, repeats, vmd_path, allow_exec,
                              max_steps, seed)
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1, default=str)
    result = {"n_records": len(recs), "n_tasks": len(tasks),
              "labels": labels, "summary": summary,
              "suite": suite["suite"]}
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(result, fh, indent=1, default=str)
    with open(os.path.join(out_dir, "summary.md"), "w") as fh:
        fh.write(summary_markdown(result))
    result["records"] = recs
    return result


def build_manifest(suite_dir: str, runs: Sequence[dict], repeats: int,
                   vmd_path: Optional[str], allow_exec: bool, max_steps: int,
                   seed: int) -> dict:
    """What a reader needs to reproduce or question a run: versions, the exact
    suite (hash), VMD, renderer, whether it ran in a container. No secrets."""
    import hashlib
    import platform
    import time
    import vmd_agent
    from vmd_agent.bench.agent.preflight import in_container
    from vmd_agent.environment import _vmd_version, find_vmd
    vmd = find_vmd(vmd_path)
    with open(os.path.join(suite_dir, "tasks.json"), "rb") as fh:
        suite_sha = hashlib.sha256(fh.read()).hexdigest()
    return {"vmd_agent_version": vmd_agent.__version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "in_container": in_container(),
            "vmd_path": vmd, "vmd_version": _vmd_version(vmd) if vmd else None,
            "toolkit_renderer": "vmd" if vmd else "matplotlib",
            "suite_sha256": suite_sha, "repeats": repeats,
            "allow_exec": allow_exec, "max_steps": max_steps, "seed": seed,
            "runs": [{"label": r["label"], "arm": r["arm"],
                      "agent": getattr(r["agent"], "name", "?"),
                      "model": getattr(r["agent"], "model", None),
                      "temperature": getattr(r["agent"], "temperature", None),
                      "max_turns": getattr(r["agent"], "max_turns", None)}
                     for r in runs],
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _pc(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def summary_markdown(result: dict) -> str:
    fams = [f for f in S.FAMILIES if any(
        f in v["by_family"] for v in result["summary"].values())]
    L = [f"Automation benchmark: {result['n_tasks']} tasks, "
         f"{result['n_records']} runs.", "",
         "| label | success (95% CI over clusters) | mean over families | "
         "silent errors | abstained | no answer | tool calls |",
         "|---|---|---|---|---|---|---|"]
    for lab, m in result["summary"].items():
        ci = m["success_ci95"]
        cis = f" ({_pc(ci[0])} to {_pc(ci[1])})" if ci else ""
        L.append(f"| {lab} | {_pc(m['success'])}{cis} | "
                 f"{_pc(m['macro_success'])} | {_pc(m['silent_error'])} | {_pc(m['abstained'])} | "
                 f"{_pc(m['no_answer'])} | {m['mean_tool_calls']:.1f} |")
    L += ["", "Success by family:", "",
          "| label | " + " | ".join(fams) + " |",
          "|---|" + "---|" * len(fams)]
    for lab, m in result["summary"].items():
        L.append(f"| {lab} | " + " | ".join(
            _pc(m["by_family"].get(f, {}).get("success")) for f in fams)
            + " |")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ plan
def plan_agent_run(suite_dir: str, n_labels: int, repeats: int = 1,
                   avg_turns: int = 8, prompt_tokens: int = 1500,
                   tokens_per_turn_added: int = 900,
                   output_tokens_per_turn: int = 350,
                   price_in: Optional[float] = None,
                   price_out: Optional[float] = None) -> dict:
    """Estimate calls and tokens for an LLM run. **Assumptions are inputs**:
    every turn re-sends the growing conversation, so input grows roughly
    quadratically with turns. Nothing is called; no prices are built in."""
    suite = S.load_suite(suite_dir)
    n_tasks = len(suite["tasks"])
    runs = n_tasks * n_labels * repeats
    per_run_in = sum(prompt_tokens + t * tokens_per_turn_added
                     for t in range(avg_turns))
    per_run_out = avg_turns * output_tokens_per_turn
    out = {"n_tasks": n_tasks, "runs": runs, "model_calls": runs * avg_turns,
           "input_tokens": runs * per_run_in,
           "output_tokens": runs * per_run_out,
           "assumptions": {"avg_turns": avg_turns,
                           "prompt_tokens": prompt_tokens,
                           "tokens_added_per_turn": tokens_per_turn_added,
                           "output_tokens_per_turn": output_tokens_per_turn}}
    if price_in is not None and price_out is not None:
        out["estimated_cost"] = (out["input_tokens"] * price_in
                                 + out["output_tokens"] * price_out) / 1e6
    else:
        out["estimated_cost"] = None
        out["note"] = "pass --price-in and --price-out (USD per million " \
                      "tokens) for a cost estimate; none are built in"
    return out
