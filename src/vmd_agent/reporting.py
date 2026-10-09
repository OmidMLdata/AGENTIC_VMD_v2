"""Turn a finished workflow into a report a colleague can read and a reviewer can check.

The report is Markdown (and a self-contained HTML copy) written next to the figures, with: the verdict and the findings,
the table of steps with the numbers each produced, the figures, every caveat the tools raised, the methods (versions,
parameters, which engine measured what), and a reproducibility section (checksums of the inputs, and the exact Tcl each VMD
step ran, copied into the folder). Every number comes from a tool result; nothing is written by a model.
"""
from __future__ import annotations

import hashlib
import html
import os
import shutil
import time
from typing import Dict, List, Optional

_ICON = {"ok": "OK", "note": "note", "warning": "WARNING", "problem": "PROBLEM"}
_CAVEAT_KEYS = ("warning", "caveat", "note", "notes", "caveats")


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize(result, limit: int = 8) -> Dict[str, object]:
    """A few scalar facts from a tool result, for the table: top-level numbers and strings, and the scalars of any
    ``summary`` dict. Long lists and big structures are left out."""
    out: Dict[str, object] = {}
    if not isinstance(result, dict):
        return out
    for key, value in result.items():
        if key in ("ok", "engine", "log", "reproduce_with") or len(out) >= limit:
            continue
        if isinstance(value, bool) or (isinstance(value, (int, float)) and not isinstance(value, bool)):
            out[key] = round(value, 4) if isinstance(value, float) else value
        elif isinstance(value, str) and len(value) <= 90 and key not in ("error",):
            out[key] = value
        elif key == "summary" and isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, (int, float)) and len(out) < limit:
                    out[f"{k}"] = round(v, 4) if isinstance(v, float) else v
    return out


def caveats(result) -> List[str]:
    found: List[str] = []

    def walk(obj, depth=0):
        if depth > 3 or not isinstance(obj, (dict, list)):
            return
        items = obj.items() if isinstance(obj, dict) else enumerate(obj)
        for k, v in items:
            if k in _CAVEAT_KEYS:
                for t in (v if isinstance(v, list) else [v]):
                    if isinstance(t, str) and t and t not in found:
                        found.append(t)
            else:
                walk(v, depth + 1)
    walk(result)
    return found


def write_report(run: dict, out_dir: str, title: Optional[str] = None) -> dict:
    """Write ``report.md`` and ``report.html`` into ``out_dir`` for the workflow record ``run`` (see
    :mod:`vmd_agent.workflows`), copying its figures and VMD scripts in so the folder stands on its own."""
    from vmd_agent import __version__
    from vmd_agent.environment import _vmd_version, find_vmd
    os.makedirs(out_dir, exist_ok=True)
    fig_dir, script_dir = os.path.join(out_dir, "figures"), os.path.join(out_dir, "scripts")
    figures: List[str] = []
    for f in run.get("figures", []):
        if os.path.isfile(f):
            os.makedirs(fig_dir, exist_ok=True)
            dest = os.path.join(fig_dir, os.path.basename(f))
            if os.path.abspath(f) != os.path.abspath(dest):
                shutil.copyfile(f, dest)
            figures.append(os.path.relpath(dest, out_dir))
    scripts: List[str] = []
    for s in run.get("scripts", []):
        if os.path.isfile(s):
            os.makedirs(script_dir, exist_ok=True)
            dest = os.path.join(script_dir, os.path.basename(s))
            if os.path.abspath(s) != os.path.abspath(dest):
                shutil.copyfile(s, dest)
            scripts.append(os.path.relpath(dest, out_dir))
    vmd = find_vmd()
    vmd_version = _vmd_version(vmd) if vmd else None
    title = title or run.get("title") or f"{run['workflow']} report"
    inputs = [(p, _sha(p)) for p in run.get("inputs", []) if os.path.isfile(p)]
    all_caveats: List[str] = []
    for st in run["steps"]:
        for c in st.get("caveats", []):
            if c not in all_caveats:
                all_caveats.append(c)
    stamp = time.strftime("%Y-%m-%d %H:%M")

    md = [f"# {title}", "", f"*{stamp}. Made by vmd-agent {__version__}"
          + (f" with VMD {vmd_version}" if vmd_version else "") + ".*", ""]
    if run.get("question"):
        md += [f"**Question.** {run['question']}", ""]
    md += ["## Verdict", "", run["verdict"], "", "## Findings", ""]
    md += ([f"* **{_ICON[f['level']]}**: {f['text']}" for f in run["findings"]] or ["* nothing to report"])
    md += ["", "## What was done", "", "| # | Step | Result | Time | Key numbers |", "|---|---|---|---|---|"]
    for st in run["steps"]:
        nums = ", ".join(f"{k} = {v}" for k, v in st["summary"].items()) or "-"
        md.append(f"| {st['n']} | `{st['tool']}` {st['label']} | {'ok' if st['ok'] else 'FAILED: ' + str(st.get('error', ''))[:80]} | "
                  f"{st['seconds']:.1f} s | {nums} |")
    if figures:
        md += ["", "## Figures", ""] + [f"![{os.path.basename(f)}]({f})" for f in figures]
    if all_caveats:
        md += ["", "## Limits and caveats raised by the tools", ""] + [f"* {c}" for c in all_caveats]
    md += ["", "## Methods", "",
           "| Setting | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in run.get("params", {}).items()]
    engines = sorted({st["engine"] for st in run["steps"] if st.get("engine")})
    if engines:
        md += ["", "Measured with: " + "; ".join(engines) + "."]
    md += ["", "## Reproduce", ""]
    if inputs:
        md += ["Input files (SHA-256):", ""] + [f"* `{os.path.basename(p)}`  `{h}`" for p, h in inputs] + [""]
    if scripts:
        md += ["The exact Tcl each VMD step ran (open in VMD, or run `vmd -dispdev text -eofexit -e FILE < /dev/null`):", ""]
        md += [f"* `{s}`" for s in scripts]
    else:
        md += ["No VMD script was needed or saved for this run."]
    md += ["", f"Re-run the whole workflow with:  `{run.get('rerun', 'vmd-agent workflow ...')}`", ""]
    text = "\n".join(md)
    md_path = os.path.join(out_dir, "report.md")
    with open(md_path, "w") as fh:
        fh.write(text)

    # HTML: built from the same data, self-contained apart from the figure files
    e = html.escape
    h = [f"<!doctype html><meta charset=utf-8><title>{e(title)}</title>",
         "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#222}"
         "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.3rem .5rem;text-align:left;font-size:13px}"
         "code{background:#f3f3f3;padding:0 .2rem}img{max-width:100%;border:1px solid #ddd}.PROBLEM{color:#b00020;font-weight:700}"
         ".WARNING{color:#a15c00;font-weight:700}</style>", f"<h1>{e(title)}</h1>",
         f"<p><em>{e(stamp)}. Made by vmd-agent {e(__version__)}" + (f" with VMD {e(str(vmd_version))}" if vmd_version else "") + ".</em></p>"]
    if run.get("question"):
        h.append(f"<p><b>Question.</b> {e(run['question'])}</p>")
    h += [f"<h2>Verdict</h2><p>{e(run['verdict'])}</p>", "<h2>Findings</h2><ul>"]
    h += [f"<li><span class='{_ICON[f['level']]}'>{_ICON[f['level']]}</span>: {e(f['text'])}</li>" for f in run["findings"]]
    h += ["</ul><h2>What was done</h2><table><tr><th>#</th><th>Step</th><th>Result</th><th>Time</th><th>Key numbers</th></tr>"]
    for st in run["steps"]:
        nums = ", ".join(f"{k} = {v}" for k, v in st["summary"].items()) or "-"
        h.append(f"<tr><td>{st['n']}</td><td><code>{e(st['tool'])}</code> {e(st['label'])}</td>"
                 f"<td>{'ok' if st['ok'] else 'FAILED'}</td><td>{st['seconds']:.1f} s</td><td>{e(nums)}</td></tr>")
    h.append("</table>")
    if figures:
        h += ["<h2>Figures</h2>"] + [f"<p><img src='{e(f)}' alt='{e(os.path.basename(f))}'></p>" for f in figures]
    if all_caveats:
        h += ["<h2>Limits and caveats raised by the tools</h2><ul>"] + [f"<li>{e(c)}</li>" for c in all_caveats] + ["</ul>"]
    h += ["<h2>Methods</h2><table>"] + [f"<tr><td>{e(str(k))}</td><td>{e(str(v))}</td></tr>" for k, v in run.get("params", {}).items()]
    h += ["</table>", "<h2>Reproduce</h2>"]
    if inputs:
        h += ["<p>Input files (SHA-256):</p><ul>"] + [f"<li><code>{e(os.path.basename(p))}</code> <code>{e(hh)}</code></li>" for p, hh in inputs] + ["</ul>"]
    h += ["<ul>" + "".join(f"<li><code>{e(s)}</code></li>" for s in scripts) + "</ul>"] if scripts else []
    h.append(f"<p>Re-run: <code>{e(run.get('rerun', ''))}</code></p>")
    html_path = os.path.join(out_dir, "report.html")
    with open(html_path, "w") as fh:
        fh.write("\n".join(h))
    return {"report_md": md_path, "report_html": html_path, "figures": figures, "scripts": scripts}
