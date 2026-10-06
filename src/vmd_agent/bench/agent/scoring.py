"""Scoring for the automation benchmark.

A submission is scored against truth that never passed through a model
(:mod:`vmd_agent.bench.agent.suite`). Beyond *success*, the scorer records
whether a failure was **silent**: a wrong answer asserted with no abstention
and no data problem flagged. A tool that fails loudly is much less dangerous
in a research workflow than one that fails confidently.

Per-record fields
-----------------
``success``        the answer meets the task's criterion
``answered``       a well-formed answer that did not abstain
``abstained``      the agent declined
``flagged``        the agent listed one or more data problems
``silent_error``   answered, wrong, and flagged nothing
``no_answer``      nothing usable was submitted (step limit, malformed)
"""
from __future__ import annotations

import math
import os
import warnings
from typing import Dict, List, Optional, Sequence

import numpy as np

from vmd_agent.bench.agent.suite import ISSUES

MAX_SELECTION_CHARS = 20000


# -------------------------------------------------------------- helpers
def _num(v) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _within(value: float, truth: float, rtol: float, atol: float) -> bool:
    return abs(value - truth) <= max(atol, rtol * abs(truth))


def _int(v) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, float) and math.isfinite(v) and v == int(v):
        return int(v)
    return None


def _inside(workdir: str, path: str) -> bool:
    root = os.path.realpath(workdir)
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


# -------------------------------------------------------- family scorers
def _score_measure(task, truth, ans) -> dict:
    v = _num(ans.get("value"))
    if v is None:
        return {"success": False, "valid": False}
    return {"success": _within(v, truth["value"], truth["rtol"],
                               truth["atol"]),
            "valid": True, "value": v, "truth": truth["value"],
            "error": v - truth["value"]}


def _score_event(task, truth, ans) -> dict:
    if "onset_frame" not in ans:
        return {"success": False, "valid": False}
    raw = ans["onset_frame"]
    ev = truth["event"]
    if ev is None:                                   # control: nothing happens
        ok = raw is None
        return {"success": ok, "valid": True, "false_alarm": raw is not None}
    if raw is None:
        return {"success": False, "valid": True, "missed": True}
    f = _int(raw)
    if f is None:
        return {"success": False, "valid": False}
    slack = truth["slack"]
    return {"success": ev["start"] - slack <= f <= ev["end"], "valid": True,
            "error": f - ev["start"], "missed": False}


def _score_diagnosis(task, truth, ans) -> dict:
    issue = ans.get("issue")
    if issue not in ISSUES:
        return {"success": False, "valid": False}
    out = {"valid": True, "issue_correct": issue == truth["issue"]}
    if issue != truth["issue"]:
        out["success"] = False
        return out
    if truth["issue"] == "none":
        v = _num(ans.get("value"))
        out["success"] = v is not None and _within(
            v, truth["value"], truth["rtol"], truth["atol"])
    else:
        # a defective file: the right call is a label and no trusted number
        out["success"] = ans.get("value") is None
        out["number_given_anyway"] = ans.get("value") is not None
    return out


def vmd_selected_indices(topology: str, selection: str,
                         vmd_path: Optional[str] = None) -> set:
    """Atom indices a **real VMD** selects for a VMD selection string.

    The string is restricted to a Tcl-free character set before it goes into a
    script (``security.tcl_selection``). Indices are 0-based, equal to
    MDAnalysis' for a PDB, because both follow file order.
    """
    from vmd_agent import security
    from vmd_agent.bench.agent.tools import sanitized_env
    from vmd_agent.visual import render
    sel = security.tcl_selection(selection)
    top = security.tcl_path(topology)
    script = (f"mol new {{{top}}} type pdb waitfor all\n"
              f'set s [atomselect top "{sel}"]\n'
              'puts "VMDIDX=[$s get index]"\n')
    r = render.run_vmd_tcl(script, vmd_path, timeout=120,
                           allow_unsafe=True, env=sanitized_env())
    if not r.get("ok") and "VMDIDX=" not in (r.get("stdout") or ""):
        raise RuntimeError("VMD failed: " + str(r.get("error") or
                                                r.get("stderr", ""))[:160])
    for line in (r.get("stdout") or "").splitlines():
        if line.startswith("VMDIDX="):
            return {int(x) for x in line[7:].split()}
    raise RuntimeError("VMD did not report the selection")


def _score_selection(task, truth, ans, syntax="mdanalysis",
                     vmd_path=None) -> dict:
    sel = ans.get("selection")
    if not isinstance(sel, str) or not sel.strip() \
            or len(sel) > MAX_SELECTION_CHARS:
        return {"success": False, "valid": False}
    try:
        if syntax == "vmd":
            got = vmd_selected_indices(task["files"]["topology"], sel,
                                       vmd_path)
        else:
            from vmd_agent.inputs.molio import load_universe
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                u = load_universe(task["files"]["topology"])
                got = set(int(i) for i in
                          u.select_atoms(sel, periodic=False).indices)
    except Exception as e:
        return {"success": False, "valid": False,
                "selection_error": f"{type(e).__name__}: {e}"[:160]}
    want = set(truth["atoms"])
    union = got | want
    jac = len(got & want) / len(union) if union else 1.0
    return {"success": got == want, "valid": True, "jaccard": jac,
            "n_selected": len(got), "n_truth": len(want)}


def _image_ok(path: str) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("L")
            if min(im.size) < 64:
                return False
            a = np.asarray(im, dtype=float)
        return float(a.std()) > 0.0
    except Exception:
        return False


def _score_keyframes(task, truth, ans) -> dict:
    frames = ans.get("frames")
    imgs = ans.get("images")
    if not isinstance(frames, list) or not frames \
            or not isinstance(imgs, list) or len(imgs) != len(frames) \
            or not all(isinstance(i, str) for i in imgs):
        return {"success": False, "valid": False}
    fr = [_int(f) for f in frames]
    if any(f is None for f in fr) or len(fr) > truth["k"]:
        return {"success": False, "valid": False}
    imgs_ok = all(os.path.isfile(i) and _inside(task["workdir"], i)
                  and _image_ok(i) for i in imgs)
    distinct = len({os.path.realpath(i) for i in imgs}) == len(imgs)
    ev, slack = truth["event"], truth["slack"]
    hit = any(ev["start"] - slack <= f <= ev["end"] + slack for f in fr)
    return {"success": bool(imgs_ok and distinct and hit), "valid": True,
            "images_valid": bool(imgs_ok and distinct),
            "captures_event": hit, "n_frames": len(fr)}


def _score_report(task, truth, ans) -> dict:
    rep = ans.get("report")
    if not isinstance(rep, list) or not rep \
            or not all(isinstance(s, str) for s in rep):
        return {"success": False, "valid": False}
    from vmd_agent.evidence.claims import verify_claims
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = verify_claims(task["files"]["topology"], rep[:12])
    c = r["counts"]
    n = r["n_claims"] or 1
    return {"success": c["contradicted"] == 0 and c["supported"] >= 1,
            "valid": True, "n_claims": r["n_claims"],
            "supported": c["supported"], "contradicted": c["contradicted"],
            "unverifiable": c["unverifiable"], "unparsed": c["unparsed"],
            "faithfulness": c["supported"] / n}


_SCORERS = {"measure": _score_measure, "event": _score_event,
            "diagnosis": _score_diagnosis, "selection": _score_selection,
            "keyframes": _score_keyframes, "report": _score_report}


def score_task(task: dict, truth: dict, submission: Optional[dict],
               selection_syntax: str = "mdanalysis",
               vmd_path: Optional[str] = None) -> dict:
    """Score one submission. ``submission`` is the agent's answer dict or None.

    ``selection_syntax`` is ``"mdanalysis"`` or ``"vmd"``; with ``"vmd"`` a
    selection is evaluated by a real VMD (needs ``vmd_path`` or an installed
    VMD)."""
    base = {"task_id": task["id"], "family": task["family"],
            "kind": task["kind"], "cluster": task["cluster"],
            "group": task["group"]}
    if not isinstance(submission, dict):
        return {**base, "success": False, "valid": False, "answered": False,
                "abstained": False, "flagged": False, "silent_error": False,
                "no_answer": True}
    abstained = bool(submission.get("abstain"))
    issues = submission.get("issues")
    flagged = isinstance(issues, list) and any(str(i).strip() for i in issues)
    try:
        if task["family"] == "selection":
            sc = _score_selection(task, truth, submission, selection_syntax,
                                  vmd_path)
        else:
            sc = _SCORERS[task["family"]](task, truth, submission)
    except Exception as e:                    # a scorer bug must not hide
        sc = {"success": False, "valid": False,
              "scorer_error": f"{type(e).__name__}: {e}"}
    valid = bool(sc.get("valid"))
    answered = valid and not abstained
    return {**base, **sc, "answered": answered, "abstained": abstained,
            "flagged": flagged,
            "silent_error": bool(answered and not sc["success"]
                                 and not flagged),
            "no_answer": not valid and not abstained,
            "confidence": _num(submission.get("confidence"))}


# ----------------------------------------------------------- aggregation
def _rate(rows: Sequence[dict], key: str) -> Optional[float]:
    return float(np.mean([bool(r[key]) for r in rows])) if rows else None


def _cluster_boot(rows: Sequence[dict], stat, n_boot: int, seed: int,
                  alpha: float = 0.05):
    """Resample clusters (traj/structure), not tasks: tasks built from one
    trajectory share its noise and are not independent."""
    by: Dict[str, List[dict]] = {}
    for r in rows:
        by.setdefault(r["cluster"], []).append(r)
    keys = sorted(by)
    if len(keys) < 2 or not n_boot:
        return None
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        vals.append(stat([r for i in pick for r in by[keys[i]]]))
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    if not vals:
        return None
    return [float(np.percentile(vals, 100 * alpha / 2)),
            float(np.percentile(vals, 100 * (1 - alpha / 2)))]


def summarize_agents(records: Sequence[dict], by: str = "label",
                     n_boot: int = 1000, seed: int = 0) -> dict:
    """Per-label (and per-family) success, silent-error and cost summary."""
    out: Dict[str, dict] = {}
    for arm in sorted({r[by] for r in records}):
        rows = [r for r in records if r[by] == arm]
        fams = {}
        for f in sorted({r["family"] for r in rows}):
            fr = [r for r in rows if r["family"] == f]
            fams[f] = {"n": len(fr), "success": _rate(fr, "success"),
                       "silent_error": _rate(fr, "silent_error"),
                       "abstained": _rate(fr, "abstained"),
                       "no_answer": _rate(fr, "no_answer")}
        wrong = [r for r in rows if not r["success"]]
        out[arm] = {
            "n": len(rows), "success": _rate(rows, "success"),
            "success_ci95": _cluster_boot(
                rows, lambda x: _rate(x, "success"), n_boot, seed),
            "macro_success": float(np.mean(
                [f["success"] for f in fams.values()])),
            "silent_error": _rate(rows, "silent_error"),
            "silent_share_of_failures": (
                float(np.mean([r["silent_error"] for r in wrong]))
                if wrong else None),
            "abstained": _rate(rows, "abstained"),
            "no_answer": _rate(rows, "no_answer"),
            "mean_tool_calls": float(np.mean(
                [r.get("tool_calls", 0) for r in rows])),
            "mean_wall_s": float(np.mean([r.get("wall_s", 0) for r in rows])),
            "tokens_in": int(sum(r.get("tokens_in") or 0 for r in rows)),
            "tokens_out": int(sum(r.get("tokens_out") or 0 for r in rows)),
            "by_family": fams}
    return out


def paired_arms(records: Sequence[dict], arm_a: str, arm_b: str,
                metric: str = "success", family: Optional[str] = None,
                n_boot: int = 2000, seed: int = 0, alpha: float = 0.05
                ) -> dict:
    """Mean per-task difference ``A - B`` (repeats averaged), with a cluster
    bootstrap interval. Tasks present in both arms only."""
    acc: Dict[str, Dict[str, List[float]]] = {}
    cl: Dict[str, str] = {}
    for r in records:
        if r["label"] not in (arm_a, arm_b):
            continue
        if family and r["family"] != family:
            continue
        acc.setdefault(r["task_id"], {}).setdefault(r["label"], []).append(
            float(bool(r[metric])))
        cl[r["task_id"]] = r["cluster"]
    rows = [{"task_id": t, "cluster": cl[t],
             "d": float(np.mean(v[arm_a])) - float(np.mean(v[arm_b]))}
            for t, v in acc.items() if arm_a in v and arm_b in v]
    if not rows:
        return {"n_tasks": 0}
    stat = lambda x: float(np.mean([r["d"] for r in x])) if x else None
    ci = _cluster_boot(rows, stat, n_boot, seed, alpha)
    return {"a": arm_a, "b": arm_b, "metric": metric, "family": family,
            "n_tasks": len(rows),
            "n_clusters": len({r["cluster"] for r in rows}),
            "mean_difference": stat(rows), "alpha": alpha, "ci": ci}
