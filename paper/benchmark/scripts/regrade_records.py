#!/usr/bin/env python3
"""Re-grade a finished benchmark run with the corrected text graders, without asking any model again.

    python regrade_records.py bench_runs/full/records.jsonl  out_folder

Run it from a vmd-agent checkout at version 1.1.0 or later, which contains the corrected graders. What it changes, and only this:

* tasks graded on the answer's wording alone (mentions / declined) are graded again with the task's own grader from
  model_tasks.py. Graders that need the run folder or the ground truth (files, numbers) are not re-run: their grades stand.
  As a check, the same procedure with the unpatched graders reproduces every original grade.
* 'grounded' is recomputed with the minus-sign fix. A run flips to grounded only if every number in its answer is found in the
  saved tool results (cut at 4000 characters, so this can only under-count).
* turntable and export_scene are kept, but marked invalid=True: no tool could read scene.json, so no model could solve them.

Every changed record keeps its original values in success_original / reason_original / grounded_original.
Writes out_folder/primary/records.jsonl (valid tasks) and out_folder/all_tasks/records.jsonl.
"""
import json, os, sys

from vmd_agent import agent as A, model_tasks as M

TEXT_ONLY = {"colours", "provenance", "missing_file", "outside_sandbox", "tcl_disabled", "no_such_measure", "wrong_pair", "claims_water",
             "representations", "look_at_image", "which_workflows", "inspect_system", "torsions", "window_mouse_pick", "window_tk_plugin",
             "namd_run", "window_outside"}
INVALID = {"turntable", "export_scene"}


def _result(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {"_cut": text}


def main(src, out):
    assert hasattr(M, "normalise_text"), "apply vmd-agent-audit-fixes.patch first"
    tasks = {t.id: t for t in M.TASKS}
    recs = [json.loads(l) for l in open(src) if l.strip()]
    changed = 0
    for r in recs:
        r["invalid"] = r["task"] in INVALID
        r.setdefault("success_original", r["success"]); r.setdefault("reason_original", r["reason"]); r.setdefault("grounded_original", r["grounded"])
        if r.get("error"):
            continue
        calls = [dict(c, result=_result(c.get("result"))) for c in r.get("calls") or []]
        if r["task"] in TEXT_ONLY:
            why = tasks[r["task"]].grade(M.Run(r.get("answer") or "", calls, "/nonexistent", {}))
            r["answer_ok"], r["reason"] = why is None, why or ""
            r["success"] = bool(r["tool_ok"]) and why is None
        if r["grounded"] is False:
            texts = [c.get("result") or "" for c in r.get("calls") or []] + [tasks[r["task"]].prompt]
            r["grounded"] = not A.unsupported_numbers(r.get("answer") or "", texts)
        changed += (r["success"] != r["success_original"]) or (r["grounded"] != r["grounded_original"])
    for name, keep in (("primary", lambda r: not r["invalid"]), ("all_tasks", lambda r: True)):
        os.makedirs(os.path.join(out, name), exist_ok=True)
        with open(os.path.join(out, name, "records.jsonl"), "w") as fh:
            for r in recs:
                if keep(r):
                    fh.write(json.dumps(r) + "\n")
    print(f"{len(recs)} records; {changed} changed; written to {out}/primary and {out}/all_tasks")


if __name__ == "__main__":
    main(*sys.argv[1:3])
