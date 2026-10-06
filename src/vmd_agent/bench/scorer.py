"""Scoring: correctness, hallucination, abstention, calibration, uncertainty.

Definitions (per condition, over its questions)
-----------------------------------------------
accuracy                  correct / all questions (abstaining counts as wrong)
coverage                  answered / all
hallucination_rate        wrong / answered. An answer is a hallucination when
                          the model asserted something the ground truth refutes
unsupported_assertion     answered / unanswerable. The condition's evidence
                          could not settle the question, so the model should
                          have abstained
appropriate_abstention    abstained / unanswerable
over_abstention           abstained / answerable
ece, brier                calibration of stated confidence on answered items

Confidence intervals are a **cluster bootstrap over structures**: questions
about one structure are not independent, so resampling individual questions
would understate uncertainty.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Sequence

import numpy as np


def _first_answer_object(text: str):
    """First JSON object in ``text`` that has an ``answer`` key.

    Scans each ``{`` with a real JSON decoder, so trailing prose or braces
    ("... (note: {unused})") cannot corrupt the parse the way a greedy
    ``{.*}`` match does.
    """
    dec = json.JSONDecoder()
    fallback = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            if "answer" in obj:
                return obj
            fallback = fallback or obj
    return fallback


def parse_response(text: str) -> dict:
    """Extract ``{answer, confidence, abstain}`` from a model reply."""
    out = {"answer": None, "confidence": None, "abstain": False,
           "parsed": False}
    if not text:
        out["abstain"] = True
        return out
    d = _first_answer_object(text)
    if d is not None:
        out["answer"] = d.get("answer")
        try:
            c = d.get("confidence")
            out["confidence"] = float(c) if c is not None else None
        except (TypeError, ValueError):
            out["confidence"] = None
        out["abstain"] = bool(d.get("abstain", False)) \
            or d.get("answer") is None
        out["parsed"] = True
        return out
    low = text.strip().lower()
    if low.startswith(("yes", "true")):
        out.update(answer=True, parsed=True)
    elif low.startswith(("no", "false")):
        out.update(answer=False, parsed=True)
    else:
        n = re.search(r"-?\d+(?:\.\d+)?", low)
        if n:
            out.update(answer=float(n.group(0)), parsed=True)
        else:
            out["abstain"] = True
    return out


def _as_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "y", "1"):
            return True
        if s in ("false", "no", "n", "0"):
            return False
    if isinstance(v, (int, float)):
        return bool(v)
    return None


def is_correct(q: dict, answer) -> bool:
    if answer is None:
        return False
    k = q["kind"]
    if k == "boolean":
        b = _as_bool(answer)
        return b is not None and b == bool(q["answer"])
    if k == "numeric":
        if isinstance(answer, bool):          # true/false is not a number
            return False
        try:
            return abs(float(answer) - float(q["answer"])) <= \
                float(q.get("tolerance", 0)) + 1e-9
        except (TypeError, ValueError):
            return False
    s = str(answer).strip().lower()
    if s == str(q["answer"]).lower():
        return True
    label = q.get("choice_labels", {}).get(q["answer"], "").lower()
    return bool(label) and s == label


def score_response(q: dict, parsed: dict, answerable: bool) -> dict:
    abstained = bool(parsed.get("abstain")) or parsed.get("answer") is None
    answered = not abstained
    correct = answered and is_correct(q, parsed.get("answer"))
    return {"answered": answered, "abstained": abstained, "correct": correct,
            "hallucination": answered and not correct,
            "answerable": answerable,
            "unsupported_assertion": answered and not answerable,
            "appropriate_abstention": abstained and not answerable,
            "over_abstention": abstained and answerable,
            "confidence": parsed.get("confidence")}


def ece(conf: Sequence[float], correct: Sequence[bool], bins: int = 10) -> float:
    conf = np.asarray(conf, float)
    corr = np.asarray(correct, float)
    if not len(conf):
        return float("nan")
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs(conf[m].mean() - corr[m].mean())
    return float(total)


def _metrics(rows: Sequence[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    ans = [r for r in rows if r["answered"]]
    unans = [r for r in rows if not r["answerable"]]
    able = [r for r in rows if r["answerable"]]
    conf = [r["confidence"] for r in ans if r["confidence"] is not None]
    corr = [r["correct"] for r in ans if r["confidence"] is not None]
    m = {
        "n": n,
        "accuracy": sum(r["correct"] for r in rows) / n,
        "coverage": len(ans) / n,
        "hallucination_rate": (sum(r["hallucination"] for r in ans) / len(ans)
                               if ans else None),
        "accuracy_answerable": (sum(r["correct"] for r in able) / len(able)
                                if able else None),
        "unsupported_assertion_rate": (
            sum(r["unsupported_assertion"] for r in unans) / len(unans)
            if unans else None),
        "appropriate_abstention_rate": (
            sum(r["appropriate_abstention"] for r in unans) / len(unans)
            if unans else None),
        "over_abstention_rate": (
            sum(r["over_abstention"] for r in able) / len(able)
            if able else None),
        "n_answerable": len(able), "n_unanswerable": len(unans),
    }
    if conf:
        m["ece"] = ece(conf, corr)
        m["brier"] = float(np.mean((np.asarray(conf) - np.asarray(corr,
                                                                  float)) ** 2))
    return m


def summarize(records: Sequence[dict], by: Sequence[str] = ("condition",),
              n_boot: int = 1000, seed: int = 0) -> dict:
    """Metrics per group with cluster-bootstrap 95 % CIs on the key rates."""
    rng = np.random.default_rng(seed)
    groups: Dict[tuple, List[dict]] = {}
    for r in records:
        groups.setdefault(tuple(r[b] for b in by), []).append(r)
    out = {}
    for key, rows in groups.items():
        base = _metrics(rows)
        structs = sorted({r["structure"] for r in rows})
        by_struct = {s: [r for r in rows if r["structure"] == s]
                     for s in structs}
        ci: Dict[str, List[float]] = {}
        if len(structs) >= 2 and n_boot:
            boots = {k: [] for k in ("accuracy", "hallucination_rate",
                                     "unsupported_assertion_rate")}
            for _ in range(n_boot):
                pick = rng.choice(len(structs), len(structs))
                sample = [r for i in pick for r in by_struct[structs[i]]]
                mm = _metrics(sample)
                for k in boots:
                    if mm.get(k) is not None:
                        boots[k].append(mm[k])
            for k, v in boots.items():
                if v:
                    ci[k] = [float(np.percentile(v, 2.5)),
                             float(np.percentile(v, 97.5))]
        base["ci95"] = ci
        base["n_structures"] = len(structs)
        out["|".join(map(str, key))] = base
    return out


def paired_difference(records: Sequence[dict], cond_a: str, cond_b: str,
                      metric: str = "correct", n_boot: int = 2000,
                      seed: int = 0, keys: Optional[Sequence[str]] = None,
                      alpha: float = 0.05) -> dict:
    """Mean per-question difference ``A - B`` with a cluster-bootstrap CI.

    Questions are paired by ``(structure, key)``; only pairs present in both
    conditions are used. ``keys`` restricts to those question keys (e.g.
    ``["ligand_buried"]``); ``alpha`` sets the interval (``0.05`` gives a 95 %
    CI; use ``0.05 / m`` for ``m`` confirmatory tests). Structures contribute
    in proportion to how many questions they have.
    """
    # Several repeats of one (structure, question) are averaged, not
    # overwritten: with n_repeats > 1 the last repeat used to silently win.
    acc: Dict[tuple, Dict[str, List[float]]] = {}
    for r in records:
        if r["condition"] in (cond_a, cond_b) and (
                keys is None or r["key"] in keys):
            acc.setdefault((r["structure"], r["key"]), {}).setdefault(
                r["condition"], []).append(float(r[metric]))
    pairs = [(k, float(np.mean(v[cond_a])) - float(np.mean(v[cond_b])))
             for k, v in acc.items() if cond_a in v and cond_b in v]
    if not pairs:
        return {"n_pairs": 0}
    structs = sorted({k[0] for k, _ in pairs})
    by = {s: [d for (k, d) in pairs if k[0] == s] for s in structs}
    mean = float(np.mean([d for _, d in pairs]))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(len(structs), len(structs))
        vals = [d for i in pick for d in by[structs[i]]]
        boots.append(np.mean(vals))
    return {"a": cond_a, "b": cond_b, "metric": metric, "n_pairs": len(pairs),
            "n_structures": len(structs), "mean_difference": mean,
            "alpha": alpha,
            "ci": [float(np.percentile(boots, 100 * alpha / 2)),
                   float(np.percentile(boots, 100 * (1 - alpha / 2)))],
            "ci95": [float(np.percentile(boots, 2.5)),
                     float(np.percentile(boots, 97.5))]}


def group_difference(records: Sequence[dict], condition: str, group_a: str,
                     group_b: str, metric: str = "correct",
                     n_boot: int = 2000, seed: int = 0) -> dict:
    """Mean ``A - B`` of ``metric`` between two structure groups.

    Used for the *contamination gap*: accuracy on real (possibly memorised)
    structures minus accuracy on procedurally generated novel ones. The groups
    contain different structures, so the bootstrap is **unpaired**: structures
    are resampled within each group.
    """
    def by_struct(g):
        d: Dict[str, List[float]] = {}
        for r in records:
            if r["condition"] == condition and r.get("group") == g:
                d.setdefault(r["structure"], []).append(float(r[metric]))
        return d
    A, B = by_struct(group_a), by_struct(group_b)
    if not A or not B:
        return {"n_a": len(A), "n_b": len(B)}
    mean = lambda d: float(np.mean([x for v in d.values() for x in v]))
    rng = np.random.default_rng(seed)
    ka, kb = list(A), list(B)
    boots = []
    for _ in range(n_boot):
        pa = [A[ka[i]] for i in rng.choice(len(ka), len(ka))]
        pb = [B[kb[i]] for i in rng.choice(len(kb), len(kb))]
        boots.append(np.mean([x for v in pa for x in v])
                     - np.mean([x for v in pb for x in v]))
    return {"condition": condition, "metric": metric, "a": group_a,
            "b": group_b, "n_a": len(A), "n_b": len(B),
            "mean_a": mean(A), "mean_b": mean(B),
            "difference": mean(A) - mean(B),
            "ci95": [float(np.percentile(boots, 2.5)),
                     float(np.percentile(boots, 97.5))]}


def contamination_estimate(records: Sequence[dict], condition: str,
                           group_a: str, group_b: str,
                           reference: str = "text_only",
                           metric: str = "correct", n_boot: int = 2000,
                           seed: int = 0) -> dict:
    """Difficulty-adjusted real-vs-novel gap (a difference of differences).

    ``gap(condition) - gap(reference)`` where ``gap = mean(A) - mean(B)``. The
    ``text_only`` reference gives a model no way to identify a structure, so
    its gap measures only how much harder one group is; subtracting it leaves
    what the *image* adds on real structures relative to novel ones, which is
    the signature of recognition from memory. Structures are resampled within
    each group (cluster bootstrap) with the same draw used for both gaps.
    """
    def by_struct(g, cond):
        d: Dict[str, List[float]] = {}
        for r in records:
            if r["condition"] == cond and r.get("group") == g:
                d.setdefault(r["structure"], []).append(float(r[metric]))
        return d
    A, B = by_struct(group_a, condition), by_struct(group_b, condition)
    Ar, Br = by_struct(group_a, reference), by_struct(group_b, reference)
    common_a = sorted(set(A) & set(Ar))
    common_b = sorted(set(B) & set(Br))
    if not common_a or not common_b:
        return {"n_a": len(common_a), "n_b": len(common_b)}

    def gap(d_a, d_b, ka, kb):
        return (np.mean([x for k in ka for x in d_a[k]])
                - np.mean([x for k in kb for x in d_b[k]]))

    point = (gap(A, B, common_a, common_b) - gap(Ar, Br, common_a, common_b))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        ka = [common_a[i] for i in rng.choice(len(common_a), len(common_a))]
        kb = [common_b[i] for i in rng.choice(len(common_b), len(common_b))]
        boots.append(gap(A, B, ka, kb) - gap(Ar, Br, ka, kb))
    return {"condition": condition, "reference": reference, "metric": metric,
            "gap_condition": float(gap(A, B, common_a, common_b)),
            "gap_reference": float(gap(Ar, Br, common_a, common_b)),
            "contamination_estimate": float(point),
            "ci95": [float(np.percentile(boots, 2.5)),
                     float(np.percentile(boots, 97.5))],
            "n_a": len(common_a), "n_b": len(common_b)}
