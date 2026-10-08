"""``vmd-agent bench models``: put a language model in front of the tools and score what it does.

For each model, each task of :mod:`vmd_agent.model_tasks` is asked in a fresh conversation, in a fresh copy of the dataset (so
what one task writes cannot help another). The real chat loop runs, with the real tools; the answer and the files the model made are graded
by a program. For every run the record says whether the right tool was used (``tool_ok``), whether the answer and files are right
(``answer_ok``), whether every number in the answer came from a tool (``grounded``), the tools called, and the wall-clock time split into
time inside the model, time inside the tools, and the whole.

Records are appended to ``<out-dir>/records.jsonl`` as they are produced and a run that is already there is skipped, so a long run can be
stopped and continued, and models served by different servers can be added one command at a time. ``summary.md`` and ``summary.json``
are rebuilt from the records. Nothing is stored in the repository: you run it on your models and your computer.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import time
from typing import Callable, Dict, List, Optional, Sequence

from vmd_agent import agent as agent_mod, model_tasks as M, security, toolset, tool_dataset as D
from vmd_agent.llm_client import LLMError
from vmd_agent.tool_cases import available

RECORDS = "records.jsonl"
CHECK_MARK = "(Check these numbers yourself"


# ---------------------------------------------------------------------- the data
def prepare(folder: str, log: Callable[[str], None] = lambda m: None) -> dict:
    """The dataset plus what some tasks start from: a dry and a solvated system (needs VMD), a folder with a provenance record, a session
    folder. Returns ``{"info": ..., "truth": ..., "extras": [...]}``."""
    folder = os.path.realpath(folder)
    info = D.make_dataset(folder)
    previous = os.environ.get(security.ENV_ROOTS)
    os.environ[security.ENV_ROOTS] = folder
    cwd = os.getcwd()
    os.chdir(folder)
    extras: List[str] = []
    try:
        top = os.path.join(folder, "protein.pdb")
        toolset.TOOLS["visualize_and_interpret"](topology=top, out_dir=os.path.join(folder, "prov"), views=["front"], renderer="matplotlib")
        toolset.TOOLS["detect_system"](topology=top, session_dir=os.path.join(folder, "sess"))
        extras += ["prov", "sess"]
        if available("vmd") is None:
            dry = toolset.TOOLS["vmd_build_system"](input_pdb=top, out_prefix=os.path.join(folder, "dry"), solvate=False)
            if dry.get("ok"):                                          # the build writes dry.psf / dry.pdb as <prefix>_ion? keep plain names
                for ext in ("psf", "pdb"):
                    src = dry.get(f"final_{ext}")
                    if src and os.path.abspath(src) != os.path.join(folder, f"dry.{ext}"):
                        shutil.copy(src, os.path.join(folder, f"dry.{ext}"))
                extras.append("dry")
            wet = toolset.TOOLS["vmd_build_system"](input_pdb=top, out_prefix=os.path.join(folder, "build", "sys"), padding=8.0)
            if wet.get("ok"):
                extras.append("build")
            else:
                log(f"could not build the solvated system: {wet.get('error')}")
    finally:
        os.chdir(cwd)
        if previous is None:
            os.environ.pop(security.ENV_ROOTS, None)
        else:
            os.environ[security.ENV_ROOTS] = previous
    return {"info": info, "truth": M.truths(info, folder), "extras": extras}


def select(categories: Optional[Sequence[str]] = None, only: Optional[Sequence[str]] = None) -> List[M.Task]:
    chosen = [t for t in M.TASKS if (not categories or t.category in categories) and (not only or t.id in only)]
    bad = [c for c in (categories or []) if c not in M.CATEGORIES] + [o for o in (only or []) if o not in {t.id for t in M.TASKS}]
    if bad:
        raise ValueError("no such category or task: " + ", ".join(bad))
    return chosen


def skip_reason(task: M.Task, extras: Sequence[str], skip: Sequence[str], unmet: Dict[str, Optional[str]]) -> str:
    for need in task.needs:
        if need in skip:
            return f"{need} left out on request"
        unmet.setdefault(need, available(need))
        if unmet[need]:
            return unmet[need] or ""
    if task.id == "mutate" and "dry" not in extras:
        return "the dry system could not be built"
    if task.id == "namd_input" and "build" not in extras:
        return "the solvated system could not be built"
    return ""


# -------------------------------------------------------------------- one run
def _strip_check(text: str) -> str:
    return text.split("\n\n" + CHECK_MARK)[0] if CHECK_MARK in text else text


def run_task(task: M.Task, model: str, base_url: str, api_key: Optional[str], base: str, truth: dict, work: str, tools: str = "all",
             max_turns: int = 12, temperature: float = 0.0, guard: bool = True, timeout: float = 600.0) -> dict:
    """Ask ``model`` one task in a fresh copy of the dataset and score it."""
    if os.path.exists(work):
        shutil.rmtree(work)
    shutil.copytree(base, work)
    previous = os.environ.get(security.ENV_ROOTS)
    os.environ[security.ENV_ROOTS] = os.path.realpath(work)
    cwd = os.getcwd()
    os.chdir(work)
    rec: dict = {"model": model, "task": task.id, "category": task.category, "tools_profile": tools, "guard": guard,
                 "success": False, "tool_ok": False, "answer_ok": False, "grounded": None, "reason": "", "tools_called": [],
                 "tool_errors": 0, "answer": "", "error": None}
    session = agent_mod.Agent(base_url, model, api_key, max_turns=max_turns, temperature=temperature, tools=tools, guard=guard,
                               timeout=timeout)
    try:
        started = time.time()
        try:
            result = session.run(task.prompt)
            text, calls = result.answer, result.calls
        except LLMError as e:
            text, calls, rec["error"] = "", [], str(e)
        wall = time.time() - started
        rec["tools_called"] = [c["name"] for c in calls]
        rec["tool_errors"] = sum(1 for c in calls if isinstance(c["result"], dict) and c["result"].get("error"))
        rec["repaired"] = sum(1 for c in calls if c.get("repairs"))
        rec["widened"] = len(session.widened)
        answer = _strip_check(text)
        rec["answer"] = answer[:1500]
        run = M.Run(answer, calls, os.path.realpath(work), truth)
        rec["tool_ok"] = True if task.decline else bool(run.called(*task.tools))
        if rec["error"]:
            rec["reason"] = "the model server failed: " + rec["error"]
        else:
            try:
                why = task.grade(run)
            except Exception as e:                                  # a grader that cannot judge is not a model failure, but is not a pass
                why = f"grader error: {type(e).__name__}: {e}"
            rec["answer_ok"] = why is None
            rec["reason"] = why or ""
        tool_texts = [json.dumps(c["result"], default=str) for c in calls]
        rec["grounded"] = not agent_mod.unsupported_numbers(answer, tool_texts) if calls else None
        rec["success"] = bool(rec["tool_ok"] and rec["answer_ok"])
        clock = session.clock
        rec.update({"wall_s": round(wall, 2), "model_s": round(clock["model_s"], 2), "tool_s": round(clock["tool_s"], 2),
                    "model_calls": clock["model_calls"], "n_tool_calls": len(calls),
                    "tokens_in": session.usage["input_tokens"], "tokens_out": session.usage["output_tokens"]})
    finally:
        os.chdir(cwd)
        if previous is None:
            os.environ.pop(security.ENV_ROOTS, None)
        else:
            os.environ[security.ENV_ROOTS] = previous
        shutil.rmtree(work, ignore_errors=True)
    return rec


# ------------------------------------------------------------------ the whole run
def load_records(out_dir: str) -> List[dict]:
    path = os.path.join(out_dir, RECORDS)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def run(models: Sequence[str], data_dir: str, out_dir: str, base_url: str, api_key: Optional[str] = None,
        categories: Optional[Sequence[str]] = None, only: Optional[Sequence[str]] = None, repeats: int = 1, tools: str = "all",
        max_turns: int = 12, temperature: float = 0.0, guard: bool = True, skip: Sequence[str] = (), force: bool = False,
        log: Callable[[str], None] = lambda m: None) -> List[dict]:
    """Run every selected task on every model; returns this run's records (also appended to ``records.jsonl``)."""
    os.makedirs(out_dir, exist_ok=True)
    tasks = select(categories, only)
    prepared = prepare(os.path.join(data_dir, "base"), log)
    base, truth, extras = prepared["info"]["folder"], prepared["truth"], prepared["extras"]
    done = {(r["model"], r["task"], r["repeat"], r.get("tools_profile"), r.get("guard")) for r in load_records(out_dir)}
    unmet: Dict[str, Optional[str]] = {}
    produced: List[dict] = []
    with open(os.path.join(out_dir, RECORDS), "a", encoding="utf-8") as fh:
        for model in models:
            for task in tasks:
                reason = skip_reason(task, extras, skip, unmet)
                for rep in range(repeats):
                    key = (model, task.id, rep, tools, guard)
                    if reason:
                        log(f"skip  {model}  {task.id:20s} {reason}")
                        break
                    if key in done and not force:
                        log(f"have  {model}  {task.id:20s} #{rep}")
                        continue
                    rec = run_task(task, model, base_url, api_key, base, truth, os.path.join(data_dir, "runs", f"{task.id}_{rep}"),
                                   tools, max_turns, temperature, guard)
                    rec["repeat"] = rep
                    produced.append(rec)
                    fh.write(json.dumps(rec, default=str) + "\n")
                    fh.flush()
                    log(f"{'pass ' if rec['success'] else 'FAIL '} {model}  {task.id:20s} #{rep} {rec['wall_s']:6.1f} s "
                        f"(model {rec['model_s']:.1f}, tools {rec['tool_s']:.1f})" + ("" if rec["success"] else "  " + rec["reason"][:110]))
    return produced


# ---------------------------------------------------------------------- summary
def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """95% interval for a proportion k/n (Wilson); (0, 0) for n = 0."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _rate(rows: Sequence[dict], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return sum(bool(v) for v in vals) / len(vals) if vals else None


def label(r: dict) -> str:
    """What a row of the summary is: the model and how it was run, so the same model with 53 tools and with routed tools sit side by side."""
    return f"{r['model']} ({r.get('tools_profile', 'all')}{'' if r.get('guard', True) else ', no guard'})"


def summarize(records: Sequence[dict]) -> dict:
    """Per model and way of running it: success overall and by category (with 95% intervals), tool choice, grounded numbers, and mean seconds."""
    out: Dict[str, dict] = {}
    for model in sorted({label(r) for r in records}):
        rows = [r for r in records if label(r) == model]
        n, k = len(rows), sum(bool(r["success"]) for r in rows)
        cats = {}
        for c in M.CATEGORIES:
            cr = [r for r in rows if r["category"] == c]
            if cr:
                ck = sum(bool(r["success"]) for r in cr)
                cats[c] = {"n": len(cr), "success": ck / len(cr), "ci95": wilson(ck, len(cr))}
        mean = lambda key: (sum(r.get(key) or 0 for r in rows) / n) if n else 0.0   # noqa: E731
        out[model] = {"n": n, "success": k / n if n else 0.0, "ci95": wilson(k, n), "by_category": cats,
                      "tool_choice": _rate([r for r in rows if r["category"] != "decline"], "tool_ok"),
                      "answer_ok": _rate(rows, "answer_ok"), "grounded": _rate(rows, "grounded"),
                      "mean_wall_s": mean("wall_s"), "mean_model_s": mean("model_s"), "mean_tool_s": mean("tool_s"),
                      "mean_model_calls": mean("model_calls"), "tokens_in": sum(r.get("tokens_in") or 0 for r in rows),
                      "tokens_out": sum(r.get("tokens_out") or 0 for r in rows),
                      "server_errors": sum(1 for r in rows if r.get("error"))}
    return out


def markdown(records: Sequence[dict]) -> str:
    s = summarize(records)
    if not s:
        return "# Model benchmark\n\nNo records yet.\n"
    models = list(s)
    pc = lambda v: "n/a" if v is None else f"{100 * v:.0f}%"                       # noqa: E731
    lines = ["# Model benchmark", "",
             "Each cell is the share of tasks passed. Intervals are 95% (Wilson) and are wide when a category has few tasks: "
             "read them as 'at least this good / at most this good', not as a ranking of close models.", "",
             "## Overall", "", "| Model | Tasks | Success | 95% interval | Right tool | Numbers grounded | Mean wall s | Model s | Tool s | Model calls | Tokens in / out |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in models:
        v = s[m]
        lines.append(f"| `{m}` | {v['n']} | {pc(v['success'])} | {pc(v['ci95'][0])} to {pc(v['ci95'][1])} | {pc(v['tool_choice'])} | {pc(v['grounded'])} | "
                     f"{v['mean_wall_s']:.1f} | {v['mean_model_s']:.1f} | {v['mean_tool_s']:.1f} | {v['mean_model_calls']:.1f} | {v['tokens_in']} / {v['tokens_out']} |")
    lines += ["", "## By category", "", "| Category | " + " | ".join(f"`{m}`" for m in models) + " |", "|---|" + "---|" * len(models)]
    for c in M.CATEGORIES:
        if any(c in s[m]["by_category"] for m in models):
            cells = [f"{pc(s[m]['by_category'][c]['success'])} (n={s[m]['by_category'][c]['n']})" if c in s[m]["by_category"] else "-" for m in models]
            lines.append(f"| {c} | " + " | ".join(cells) + " |")
    ids = [t.id for t in M.TASKS if any(r["task"] == t.id for r in records)]
    lines += ["", "## By task", "", "| Task | Category | " + " | ".join(f"`{m}`" for m in models) + " |", "|---|---|" + "---|" * len(models)]
    for tid in ids:
        task = next(t for t in M.TASKS if t.id == tid)
        cells = []
        for m in models:
            rows = [r for r in records if label(r) == m and r["task"] == tid]
            cells.append(f"{sum(bool(r['success']) for r in rows)}/{len(rows)}" if rows else "-")
        lines.append(f"| {tid} | {task.category} | " + " | ".join(cells) + " |")
    lines += ["", "Success needs the right tool called without error (not for tasks that must be declined) and an answer and files that the "
                  "program's checks accept. 'Numbers grounded' is the share of runs in which every number in the answer appears in a tool "
                  "result. Times are wall-clock on your computer and include the model server's own work."]
    return "\n".join(lines) + "\n"


def write_summary(out_dir: str) -> str:
    records = load_records(out_dir)
    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(markdown(records))
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summarize(records), fh, indent=1, default=str)
    return os.path.join(out_dir, "summary.md")
