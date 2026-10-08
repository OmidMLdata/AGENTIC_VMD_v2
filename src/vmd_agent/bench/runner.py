"""Run the grounded-interpretation benchmark end to end.

For each structure the runner computes ground truth, builds the questions,
renders the views once, assembles the evidence for every grounding condition,
queries the model, and scores the reply. Structures are given anonymous IDs
and the annotated panels carry no file name, so a model cannot identify a
molecule from a title.

Outputs in ``out_dir``: ``records.jsonl`` (one line per question x condition x
repeat, including the raw model reply), ``summary.json``, ``summary.md`` and
``manifest.json`` (software versions, structure hashes, conditions, renderer).

Caveat that belongs in any paper using this: a model may recognise a famous
structure (ubiquitin, lysozyme) from its shape and answer from memory. The
``blind`` condition does not catch that, because it shows no image. Include
structures a model is unlikely to have memorised (novel folds, AlphaFold
models of obscure proteins, designed proteins) and report them separately.
"""
from __future__ import annotations

import inspect
import json
import os
import time
from typing import Callable, Dict, List, Optional, Sequence

from vmd_agent.bench import conditions as C
from vmd_agent.bench import questions as Q
from vmd_agent.bench import scorer as S
from vmd_agent.bench.truth import ground_truth


def _redact(q: dict) -> dict:
    return {k: v for k, v in q.items() if k != "answer"}


def _accepts_question(model) -> bool:
    """True when ``model`` takes a ``question`` keyword (or **kwargs)."""
    try:
        params = inspect.signature(model).parameters
    except (TypeError, ValueError):
        return False
    return "question" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _model_name(model) -> str:
    return getattr(model, "name", None) or getattr(model, "__name__", "model")


def prepare_structure(idx: int, path: str, out_dir: str, renderer,
                      views: Sequence[str], render: bool = True) -> dict:
    """Truth, questions, renders and text evidence for one structure."""
    from vmd_agent.structure.detect import detect_system
    from vmd_agent.structure.stats import structure_stats, stats_caption
    from vmd_agent.auto import visual_legend, build_color_keys
    from vmd_agent.visual.annotate import annotate_image
    from vmd_agent.evidence import provenance

    sid = f"S{idx:03d}"
    work = os.path.join(out_dir, "structures", sid)
    os.makedirs(work, exist_ok=True)
    truth = ground_truth(path)
    if not truth.get("ok"):
        return {"id": sid, "ok": False, "path": path,
                "error": truth.get("error")}
    det = detect_system(path)
    stats = structure_stats(path)
    reps = renderer.protein_reps(det, False, "overview")
    legend = visual_legend(det, protein_reps=reps, backend=renderer.name)
    ckeys = build_color_keys(det, protein_reps=reps)
    colour_lines = []
    for ck in ckeys:
        colour_lines.append(f"{ck['method']}: " + ", ".join(
            f"{e['color']} = {e['label']}" for e in ck.get("entries", [])))
    assets = {"legend": legend, "colour_key": colour_lines,
              "stats": stats_caption(stats), "raw": {}, "annotated": {}}
    if render and renderer.available():
        rv = renderer.render_views(path, None, detection=det,
                                   views=list(views),
                                   out_dir=os.path.join(work, "raw"))
        assets["raw"] = rv.get("images", {})
        for view, img in assets["raw"].items():
            a = annotate_image(img, color_keys=ckeys,
                               stats_lines=assets["stats"],
                               legend_lines=legend,
                               title=f"structure {sid} — {view} view",
                               out_path=os.path.join(work,
                                                     f"annotated_{view}.png"))
            if a.get("ok"):
                assets["annotated"][view] = a["annotated_image"]
    qs = Q.build_questions(truth, sid)
    return {"id": sid, "ok": True, "path": path, "truth": truth,
            "questions": qs, "assets": assets,
            "sha256": provenance.describe_file(path).get("sha256")}


def run_benchmark(structures: Sequence[str], model: Callable,
                  out_dir: str,
                  conditions: Sequence[str] = tuple(C.DEFAULT_CONDITIONS),
                  renderer: str = "auto", views: Sequence[str] =
                  ("front", "side", "top"), n_repeats: int = 1,
                  render: bool = True, vmd_path: Optional[str] = None,
                  n_boot: int = 1000, seed: int = 0,
                  groups: Optional[Dict[str, str]] = None,
                  progress: Optional[Callable[[str], None]] = None) -> dict:
    """Evaluate ``model`` on ``structures`` across the grounding ladder.

    ``groups`` maps a structure path to a label (e.g. ``"real"`` /
    ``"synthetic"``). With two or more groups the summary adds per-group
    metrics and the **contamination gap** between them.
    """
    from vmd_agent.visual.renderers import get_renderer
    from vmd_agent.evidence import provenance

    unknown = [c for c in conditions if c not in C.CONDITIONS]
    if unknown:
        raise ValueError(f"unknown conditions {unknown}; "
                         f"choose from {sorted(C.CONDITIONS)}")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    rend = get_renderer(renderer, vmd_path)
    log = progress or (lambda m: None)

    prepared = []
    for i, p in enumerate(structures):
        log(f"preparing {os.path.basename(p)}")
        prepared.append(prepare_structure(i, p, out_dir, rend, views, render))
    ok_structs = [p for p in prepared if p["ok"]]
    for p in ok_structs:
        p["group"] = (groups or {}).get(p["path"], "all")
    skipped_structs = [{"path": p["path"], "error": p.get("error")}
                       for p in prepared if not p["ok"]]

    records: List[dict] = []
    skipped_cells: Dict[str, str] = {}
    needs_truth = bool(getattr(model, "needs_truth", False))
    pass_question = _accepts_question(model)
    for si, sp in enumerate(ok_structs):
        other = ok_structs[(si + 1) % len(ok_structs)]["assets"]["legend"] \
            if len(ok_structs) > 1 else None
        assets = dict(sp["assets"], other_legend=other)
        for cond in conditions:
            ctx = C.build_context(cond, assets)
            if not ctx["available"]:
                skipped_cells[f"{sp['id']}|{cond}"] = (
                    "no rendered images available for this condition")
                continue
            for q in sp["questions"]:
                answerable = C.is_answerable(q, cond)
                for rep in range(n_repeats):
                    prompt = Q.format_prompt(q)
                    arg_q = q if needs_truth else _redact(q)
                    try:
                        if pass_question:
                            reply = model(prompt, ctx["images"], ctx["text"],
                                          question=arg_q)
                        else:
                            reply = model(prompt, ctx["images"], ctx["text"])
                    except Exception as e:
                        reply = ""
                        log(f"model error on {q['id']}|{cond}: {e}")
                    parsed = S.parse_response(reply)
                    rec = S.score_response(q, parsed, answerable)
                    rec.update(structure=sp["id"], group=sp["group"],
                               key=q["key"], kind=q["kind"],
                               condition=cond, repeat=rep, qid=q["id"],
                               question_answer=q["answer"],
                               model_answer=parsed.get("answer"),
                               reply=reply)
                    records.append(rec)
        log(f"scored {sp['id']}")

    with open(os.path.join(out_dir, "records.jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r, default=str) + "\n")

    by_cond = S.summarize(records, ("condition",), n_boot=n_boot, seed=seed)
    contrasts = {}
    for a, b in (("legend", "raw"), ("legend_stats", "raw"),
                 ("multiview_legend_stats", "legend_stats"),
                 ("misleading_legend", "legend"), ("text_only", "legend_stats")):
        if a in conditions and b in conditions:
            contrasts[f"{a} - {b}"] = {
                "accuracy": S.paired_difference(records, a, b, "correct",
                                                n_boot=n_boot, seed=seed),
                "hallucination": S.paired_difference(
                    records, a, b, "hallucination", n_boot=n_boot, seed=seed)}
    labels = sorted({p["group"] for p in ok_structs})
    by_group, gaps = {}, {}
    if len(labels) > 1:
        by_group = S.summarize(records, ("condition", "group"),
                               n_boot=n_boot, seed=seed)
        if len(labels) == 2:
            for cond in conditions:
                gaps[cond] = {
                    m: S.group_difference(records, cond, labels[0], labels[1],
                                          m, n_boot=n_boot, seed=seed)
                    for m in ("correct", "hallucination")}
                if "text_only" in conditions and cond != "text_only":
                    gaps[cond]["adjusted"] = S.contamination_estimate(
                        records, cond, labels[0], labels[1], "text_only",
                        "correct", n_boot=n_boot, seed=seed)
    summary = {"model": _model_name(model), "renderer": rend.name,
               "groups": labels, "by_condition_group": by_group,
               "group_gaps": gaps,
               "n_structures": len(ok_structs), "n_records": len(records),
               "conditions": list(conditions), "by_condition": by_cond,
               "paired_contrasts": contrasts,
               "skipped_structures": skipped_structs,
               "skipped_cells": skipped_cells}
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    with open(os.path.join(out_dir, "summary.md"), "w") as fh:
        fh.write(summary_markdown(summary))
    manifest = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": _model_name(model), "renderer": rend.info(),
        "environment": provenance.collect_environment(vmd_path),
        "structures": [{"id": p["id"], "path": p["path"],
                        "sha256": p.get("sha256")} for p in ok_structs],
        "conditions": {c: {k: (sorted(v) if isinstance(v, set) else v)
                           for k, v in C.CONDITIONS[c].items()}
                       for c in conditions},
        "seed": seed, "n_repeats": n_repeats, "views": list(views),
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    summary["out_dir"] = out_dir
    return summary


def _f(x, pct=True):
    if x is None:
        return "–"
    return f"{100 * x:.0f}%" if pct else f"{x:.3f}"


def summary_markdown(summary: dict) -> str:
    L = [f"# Benchmark summary: {summary['model']}", "",
         f"Renderer: `{summary['renderer']}` · structures: "
         f"{summary['n_structures']} · records: {summary['n_records']}", "",
         "| condition | accuracy | halluc. | unsupported | abstain ok | ECE |",
         "|---|---|---|---|---|---|"]
    for cond in summary["conditions"]:
        m = summary["by_condition"].get(cond)
        if not m:
            continue
        ci = m.get("ci95", {}).get("accuracy")
        acc = _f(m["accuracy"]) + (f" [{_f(ci[0])}–{_f(ci[1])}]" if ci else "")
        L.append(f"| {cond} | {acc} | {_f(m.get('hallucination_rate'))} | "
                 f"{_f(m.get('unsupported_assertion_rate'))} | "
                 f"{_f(m.get('appropriate_abstention_rate'))} | "
                 f"{_f(m.get('ece'), pct=False)} |")
    if summary.get("paired_contrasts"):
        L += ["", "## Paired contrasts (cluster-bootstrap 95% CI)", "",
              "| contrast | Δ accuracy | Δ hallucination |", "|---|---|---|"]
        for name, d in summary["paired_contrasts"].items():
            a, h = d["accuracy"], d["hallucination"]
            fa = (f"{a['mean_difference']:+.2f} "
                  f"[{a['ci95'][0]:+.2f}, {a['ci95'][1]:+.2f}]"
                  if a.get("n_pairs") else "–")
            fh = (f"{h['mean_difference']:+.2f} "
                  f"[{h['ci95'][0]:+.2f}, {h['ci95'][1]:+.2f}]"
                  if h.get("n_pairs") else "–")
            L.append(f"| {name} | {fa} | {fh} |")
    if summary.get("group_gaps"):
        g = summary["groups"]
        L += ["", f"## Real-vs-novel gap: accuracy({g[0]}) − accuracy({g[1]})",
              "", "Raw gap mixes difficulty and memorisation. The adjusted "
              "column subtracts the `text_only` gap (a condition that cannot "
              "identify a structure), leaving the image-specific part. "
              "Cluster bootstrap, 95% CI.", "",
              "| condition | " + g[0] + " | " + g[1] + " | raw gap [CI] | "
              "adjusted [CI] |", "|---|---|---|---|---|"]
        for cond, d in summary["group_gaps"].items():
            a = d["correct"]
            if not a.get("n_a") or not a.get("n_b") or "difference" not in a:
                continue
            adj = d.get("adjusted") or {}
            adj_s = (f"{adj['contamination_estimate']:+.2f} "
                     f"[{adj['ci95'][0]:+.2f}, {adj['ci95'][1]:+.2f}]"
                     if "contamination_estimate" in adj else "–")
            L.append(f"| {cond} | {_f(a['mean_a'])} | {_f(a['mean_b'])} | "
                     f"{a['difference']:+.2f} [{a['ci95'][0]:+.2f}, "
                     f"{a['ci95'][1]:+.2f}] | {adj_s} |")
        L += ["", "An adjusted estimate clearly above 0 on image conditions is "
              "evidence of recognition from memory; it still assumes the "
              "novel and real structures differ in difficulty in the same way "
              "for images as for text (see docs/reference/RESEARCH.md#appendix-e-grounding-study-specification)."]
    if summary.get("skipped_cells"):
        L += ["", f"{len(summary['skipped_cells'])} structure×condition cells "
              "were skipped (no renderer available)."]
    return "\n".join(L) + "\n"


def plan_benchmark(structures: Sequence[str],
                   conditions: Sequence[str] = tuple(C.DEFAULT_CONDITIONS),
                   n_repeats: int = 1, n_views: int = 3,
                   image_px: Sequence[int] = (1400, 1050),
                   price_in_per_mtok: Optional[float] = None,
                   price_out_per_mtok: Optional[float] = None) -> dict:
    """Count model calls and estimate tokens **without calling any model**.

    Run this before ``run_benchmark`` with a paid model. Token estimates are
    rough (image tokens ~ width*height/750, text ~ 4 chars/token, ~60 output
    tokens per reply). Prices are *your* inputs; none are built in.
    """
    from vmd_agent.structure.detect import detect_system
    from vmd_agent.structure.stats import structure_stats, stats_caption
    from vmd_agent.auto import visual_legend
    from vmd_agent.visual.renderers import MatplotlibRenderer
    rend = MatplotlibRenderer()
    img_tok = image_px[0] * image_px[1] / 750.0
    calls = img_total = tok_in = 0
    per_struct = []
    for p in structures:
        truth = ground_truth(p)
        if not truth.get("ok"):
            continue
        qs = Q.build_questions(truth, "S")
        det = detect_system(p)
        legend = visual_legend(det, protein_reps=rend.protein_reps(det),
                               backend="matplotlib")
        stats = stats_caption(structure_stats(p))
        legend_chars = sum(len(x) for x in legend) + 200
        stats_chars = sum(len(x) for x in stats) + 40
        for cond in conditions:
            spec = C.CONDITIONS[cond]
            n_img = {"none": 0, "single": 1, "annotated": 1,
                     "multi": n_views}[spec["images"]]
            chars = (legend_chars if spec["legend"] else 0) + \
                (stats_chars if spec["stats"] else 0)
            for q in qs:
                prompt_chars = len(Q.format_prompt(q)) + 400   # + system prompt
                tok_in += n_img * img_tok + (chars + prompt_chars) / 4.0
                img_total += n_img
                calls += 1
        per_struct.append(len(qs))
    calls *= n_repeats
    tok_in *= n_repeats
    img_total *= n_repeats
    tok_out = calls * 60
    out = {"n_structures": len(per_struct), "n_questions_per_structure_mean":
           (sum(per_struct) / len(per_struct) if per_struct else 0),
           "n_conditions": len(conditions), "n_repeats": n_repeats,
           "n_calls": calls, "n_images_sent": img_total,
           "est_input_tokens": int(tok_in), "est_output_tokens": int(tok_out),
           "note": "rough estimate; images ~ w*h/750 tokens, text ~ 4 chars/token"}
    if price_in_per_mtok is not None and price_out_per_mtok is not None:
        out["est_cost"] = (tok_in * price_in_per_mtok
                           + tok_out * price_out_per_mtok) / 1e6
        out["cost_note"] = "uses the per-million-token prices you supplied"
    return out
