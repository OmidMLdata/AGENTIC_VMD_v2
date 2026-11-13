#!/usr/bin/env python3
"""Analyse vmd-agent model-benchmark records and draw the comparison figure.

    python analyze_benchmark.py bench_runs/full            # reads records.jsonl (+ manifest_full.json) there
    python analyze_benchmark.py bench_runs/full --price claude-opus-5-5=4,20   # optional: USD per million tokens in,out

Statistics (all at the level of the task, because the repeats of one task are not independent):
  * a model's success = the mean over tasks of the share of its repeats that passed (every task weighs the same);
  * 95% intervals: bootstrap over tasks (tasks resampled with replacement, all their repeats kept together);
  * a comparison of two models: the per-task difference in success, its mean with a bootstrap interval, and an exact or
    Monte-Carlo sign-flip permutation test on those differences; p-values Holm-adjusted across the comparisons made;
  * pass^k: the share of tasks a model passed on every one of its k repeats (consistency); pass@k: on at least one.
Only tasks that every model ran are compared. Runs that failed at the server (records with an `error`) are excluded and counted.

Writes to <records dir>/analysis/: metrics.csv, by_category.csv, paired.csv, per_task.csv, figure.pdf/.svg/.png,
source_data_panel_*.csv, and results.md (the numbers in sentences, for the text and the caption).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

CATEGORY_ORDER = ["inspect", "claims", "trajectory", "measure_with_vmd", "files", "build", "maps", "render", "window", "video",
                  "workflows", "hand_off", "records", "network", "decline"]
CATEGORY_LABEL = {"inspect": "Inspect files", "claims": "Check claims", "trajectory": "Trajectory analysis",
                  "measure_with_vmd": "Measure in VMD", "files": "Write files", "build": "Build systems", "maps": "Density maps",
                  "render": "Render images", "window": "Drive VMD window", "video": "Video", "workflows": "Whole jobs",
                  "hand_off": "HPC hand-off", "records": "Provenance", "network": "PDB search", "decline": "Refuse correctly"}
DISPLAY = {"claude-opus-5-5": "Claude Opus 5.5", "granite4.1:8b": "Granite 4.1 8B", "gemma4:e4b": "Gemma 4 E4B"}
# Okabe-Ito (colour-blind safe). The proprietary model is the focal series; the two open models are the comparators.
COLOR = {"claude-opus-5-5": "#D55E00", "granite4.1:8b": "#0072B2", "gemma4:e4b": "#009E73"}
FALLBACK = ["#CC79A7", "#E69F00", "#56B4E9", "#000000"]
GREY = "#6B6B6B"
RNG = np.random.default_rng(20261028)
B_BOOT = 10_000


# ------------------------------------------------------------------ loading
def load(folder: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    path = os.path.join(folder, "records.jsonl")
    if not os.path.isfile(path):
        sys.exit(f"no records.jsonl in {folder}")
    df = pd.DataFrame([json.loads(l) for l in open(path, encoding="utf-8") if l.strip()])
    errors = df[df["error"].notna() & (df["error"].astype(str) != "")] if "error" in df else df.iloc[:0]
    df = df.drop(errors.index)
    man = {}
    for f in sorted(os.listdir(folder)):
        if f.startswith("manifest_") and f.endswith(".json"):
            man = json.load(open(os.path.join(folder, f)))
    return df, errors, man


def order_models(models) -> list[str]:
    known = [m for m in DISPLAY if m in models]
    return [m for m in known if m != "claude-opus-5-5"] + (["claude-opus-5-5"] if "claude-opus-5-5" in models else []) \
        + sorted(m for m in models if m not in DISPLAY)


def colour(m: str, models: list[str]) -> str:
    return COLOR.get(m) or FALLBACK[[x for x in models if x not in COLOR].index(m) % len(FALLBACK)]


def name(m: str) -> str:
    return DISPLAY.get(m, m)


# ------------------------------------------------------------------ statistics
def task_table(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """tasks x models: the mean of `col` over each model's repeats of each task (NaN where a value is undefined)."""
    d = df[["task", "model", col]].copy()
    d[col] = d[col].astype(float)
    return d.groupby(["task", "model"])[col].mean().unstack("model")


def boot_mean(per_task: np.ndarray) -> tuple[float, float, float]:
    x = per_task[~np.isnan(per_task)]
    if len(x) == 0:
        return (np.nan, np.nan, np.nan)
    idx = RNG.integers(0, len(x), size=(B_BOOT, len(x)))
    means = x[idx].mean(axis=1)
    if np.all(x == 1) or np.all(x == 0):
        # every task at 100% (or 0%): the bootstrap interval collapses to a point, so give the exact (Clopper-Pearson)
        # 95% interval for n out of n tasks instead: [0.025^(1/n), 1] (or its mirror image)
        edge = 0.025 ** (1 / len(x))
        return (1.0, edge, 1.0) if x[0] == 1 else (0.0, 0.0, 1 - edge)
    return float(x.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def sign_flip_p(d: np.ndarray) -> float:
    """Two-sided paired permutation test of mean(d) = 0 by flipping the signs of the per-task differences."""
    d = d[~np.isnan(d)]
    nz = d[d != 0]
    if len(nz) == 0:
        return 1.0
    obs = abs(d.mean())
    if len(nz) <= 20:                                         # exact
        signs = np.array(list(itertools.product([-1, 1], repeat=len(nz))))
        stats = np.abs((signs * nz).sum(axis=1) / len(d))
    else:
        signs = RNG.choice([-1, 1], size=(200_000, len(nz)))
        stats = np.abs((signs * nz).sum(axis=1) / len(d))
    return float((np.sum(stats >= obs - 1e-12) + (0 if len(nz) <= 20 else 1)) / (len(stats) + (0 if len(nz) <= 20 else 1)))


def holm(p: list[float]) -> list[float]:
    order = np.argsort(p)
    adj = np.empty(len(p))
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[i]))
        adj[i] = running
    return adj.tolist()


def pass_k(df: pd.DataFrame, model: str) -> tuple[float, float, int]:
    g = df[df["model"] == model].groupby("task")["success"]
    k = int(g.size().max()) if len(g.size()) else 0
    full = g.size()[g.size() == k].index
    s = df[(df["model"] == model) & df["task"].isin(full)].groupby("task")["success"]
    return float(s.all().mean()), float(s.any().mean()), k


# ------------------------------------------------------------------ analysis
def analyse(df: pd.DataFrame, price: dict) -> dict:
    models = order_models(df["model"].unique())
    tasks_per_model = {m: set(df.loc[df["model"] == m, "task"]) for m in models}
    common = set.intersection(*tasks_per_model.values())
    dropped = {m: sorted(tasks_per_model[m] - common) for m in models}
    df = df[df["task"].isin(common)].copy()
    df["tool_ok_nd"] = np.where(df["category"] == "decline", np.nan, df["tool_ok"].astype(float))
    df["decline_ok"] = np.where(df["category"] == "decline", df["success"].astype(float), np.nan)
    df["grounded_f"] = df["grounded"].map(lambda v: np.nan if v is None or (isinstance(v, float) and np.isnan(v)) else float(v))
    df["tokens_total"] = df["tokens_in"].fillna(0) + df["tokens_out"].fillna(0)
    df["call_ok"] = np.where(df["n_tool_calls"] > 0, 1 - df["tool_errors"] / df["n_tool_calls"].where(df["n_tool_calls"] > 0), np.nan)

    rows = []
    for m in models:
        r = {"model": m, "display": name(m), "n_tasks": len(common), "n_runs": int((df["model"] == m).sum())}
        for key, col in [("success", "success"), ("answer_correct", "answer_ok"), ("right_tool", "tool_ok_nd"),
                         ("numbers_grounded", "grounded_f"), ("refuses_correctly", "decline_ok"), ("tool_calls_without_error", "call_ok")]:
            mean, lo, hi = boot_mean(task_table(df, col)[m].to_numpy())
            r[key], r[key + "_lo"], r[key + "_hi"] = mean, lo, hi
        r["pass^k"], r["pass@k"], r["k"] = pass_k(df, m)
        d = df[df["model"] == m]
        r["median_wall_s"] = float(d["wall_s"].median())
        r["wall_s_q1"], r["wall_s_q3"] = float(d["wall_s"].quantile(.25)), float(d["wall_s"].quantile(.75))
        r["mean_model_s"], r["mean_tool_s"] = float(d["model_s"].mean()), float(d["tool_s"].mean())
        r["mean_model_calls"] = float(d["model_calls"].mean())
        r["mean_tokens_in"], r["mean_tokens_out"] = float(d["tokens_in"].mean()), float(d["tokens_out"].mean())
        r["tokens_in_total"], r["tokens_out_total"] = int(d["tokens_in"].sum()), int(d["tokens_out"].sum())
        if m in price:
            pin, pout = price[m]
            r["usd_per_run"] = (r["mean_tokens_in"] * pin + r["mean_tokens_out"] * pout) / 1e6
            r["usd_total"] = (r["tokens_in_total"] * pin + r["tokens_out_total"] * pout) / 1e6
        rows.append(r)
    metrics = pd.DataFrame(rows)

    succ = task_table(df, "success")[models]
    cat = df.groupby(["category", "model"])["success"].mean().unstack("model").reindex([c for c in CATEGORY_ORDER if c in set(df["category"])])
    cat_n = df.groupby("category")["task"].nunique().reindex(cat.index)

    paired = []
    ref = "claude-opus-5-5" if "claude-opus-5-5" in models else models[-1]
    for m in [x for x in models if x != ref]:
        d = (succ[ref] - succ[m]).to_numpy()
        mean, lo, hi = boot_mean(d)
        paired.append({"comparison": f"{name(ref)} minus {name(m)}", "reference": ref, "other": m, "n_tasks": int(np.sum(~np.isnan(d))),
                       "mean_difference": mean, "ci_lo": lo, "ci_hi": hi,
                       "tasks_reference_better": int(np.sum(d > 0)), "tasks_other_better": int(np.sum(d < 0)), "tasks_tied": int(np.sum(d == 0)),
                       "p_sign_flip": sign_flip_p(d)})
    if paired:
        for p_, a in zip(paired, holm([p["p_sign_flip"] for p in paired])):
            p_["p_holm"] = a
    return {"df": df, "models": models, "metrics": metrics, "succ": succ, "cat": cat, "cat_n": cat_n,
            "paired": pd.DataFrame(paired), "ref": ref, "common": sorted(common), "dropped": dropped}


# ------------------------------------------------------------------ figure
def style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7, "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titlelocation": "left", "axes.titlepad": 4,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "savefig.dpi": 600, "figure.dpi": 150,
        "lines.linewidth": 0.9, "legend.frameon": False,
    })


def letter(ax, s: str) -> None:
    ax.text(-0.02, 1.02, s, transform=ax.transAxes, fontsize=9, fontweight="bold", va="bottom", ha="right")


def pct(ax, axis: str = "x") -> None:
    fmt = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%")
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_formatter(fmt)


def draw(res: dict, out: str, watermark: str | None = None) -> list[str]:
    style()
    models, M, df = res["models"], res["metrics"].set_index("model"), res["df"]
    col = {m: colour(m, models) for m in models}
    nT, k = len(res["common"]), int(M["k"].max())
    fig = plt.figure(figsize=(183 / 25.4, 132 / 25.4))
    # fixed positions (figure fractions): two columns of panels, and the heatmap on the right with its labels outside it
    pos = {"a": [0.115, 0.625, 0.235, 0.315], "c": [0.525, 0.625, 0.165, 0.315],
           "d": [0.115, 0.095, 0.235, 0.33], "e": [0.475, 0.095, 0.215, 0.33], "b": [0.735, 0.13, 0.115, 0.70]}
    src = {}

    # a: overall success with intervals, and pass^k
    ax = fig.add_axes(pos["a"]); letter(ax, "a")
    y = np.arange(len(models))
    for i, m in enumerate(models):
        r = M.loc[m]
        ax.plot([r["success_lo"], r["success_hi"]], [i, i], color=col[m], lw=1.6, solid_capstyle="butt")
        ax.plot(r["success"], i, "o", ms=5.5, color=col[m], mec="white", mew=0.6, zorder=3)
        ax.plot(r["pass^k"], i - 0.28, "D", ms=3.2, mfc="white", mec=col[m], mew=0.8, zorder=3)
        ax.text(r["success_hi"] + 0.03, i, f"{r['success'] * 100:.0f}%", va="center", fontsize=6, color=col[m])
    ax.set_yticks(y, [name(m) for m in models]); ax.set_ylim(-0.7, len(models) - 0.4)
    ax.set_xlim(0, 1.08); pct(ax); ax.set_xlabel("Tasks solved")
    ax.set_title("Overall task success")
    ax.plot([], [], "o", color=GREY, ms=4, label=f"mean over {k} tries (95% CI)")
    ax.plot([], [], "D", mfc="white", mec=GREY, ms=3, label=f"solved on all {k} tries")
    ax.legend(loc="upper left", bbox_to_anchor=(-0.02, -0.3), ncol=2, handletextpad=0.3, columnspacing=1.0, borderaxespad=0)
    src["a"] = M[["display", "success", "success_lo", "success_hi", "pass^k", "pass@k", "k", "n_tasks", "n_runs"]]

    # b: per-category heatmap
    ax = fig.add_axes(pos["b"])
    fig.text(pos["b"][0] - 0.012, 0.952, "c", fontsize=9, fontweight="bold", ha="right", va="bottom")
    cat = res["cat"][models]
    cmap = LinearSegmentedColormap.from_list("succ", ["#F7F7F7", "#C6DBEF", "#6BAED6", "#2171B5", "#08306B"])
    im = ax.imshow(cat.to_numpy(dtype=float), cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for (i, j), v in np.ndenumerate(cat.to_numpy(dtype=float)):
        ax.text(j, i, "–" if np.isnan(v) else f"{v * 100:.0f}", ha="center", va="center", fontsize=6,
                color="white" if (not np.isnan(v) and v > 0.6) else "black")
    ax.set_xticks(range(len(models)), [name(m) for m in models], rotation=40, ha="left", rotation_mode="anchor")
    for t, m in zip(ax.get_xticklabels(), models):
        t.set_color(col[m])
    ax.set_yticks(range(len(cat)), [f"{CATEGORY_LABEL.get(c, c)} ({res['cat_n'][c]})" for c in cat.index])
    ax.tick_params(length=0); [s.set_visible(False) for s in ax.spines.values()]
    ax.xaxis.tick_top(); ax.yaxis.tick_right()
    fig.text(pos["b"][0], 0.952, "Success by kind of task (tasks per kind)", fontsize=7, ha="left", va="bottom")
    cax = fig.add_axes([pos["b"][0], 0.075, pos["b"][2], 0.012])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_ticks([0, .5, 1]); cb.set_ticklabels(["0%", "50%", "100%"]); cb.outline.set_linewidth(0.4)
    cb.set_label("Share of runs passed", fontsize=6); cb.ax.tick_params(labelsize=6, length=2)
    src["b"] = cat.rename(columns=name).assign(n_tasks=res["cat_n"])

    # c: how the agent behaves
    ax = fig.add_axes(pos["c"]); letter(ax, "b")
    rows = [("right_tool", "Called a correct tool"), ("numbers_grounded", "Every number in a tool result"),
            ("tool_calls_without_error", "Tool calls without error"), ("refuses_correctly", "Refuses impossible requests")]
    off = np.linspace(-0.22, 0.22, len(models))
    for j, (key, lab) in enumerate(rows):
        for o, m in zip(off, models):
            r = M.loc[m]
            if np.isnan(r[key]):
                continue
            ax.plot([r[key + "_lo"], r[key + "_hi"]], [j + o] * 2, color=col[m], lw=1.1)
            ax.plot(r[key], j + o, "o", ms=3.6, color=col[m], mec="white", mew=0.4, zorder=3)
    ax.set_yticks(range(len(rows)), [l for _, l in rows]); ax.invert_yaxis()
    ax.set_xlim(-0.03, 1.03); pct(ax); ax.set_xlabel("Share (95% CI)")
    ax.set_title("Agent behaviour")
    src["c"] = M[["display"] + [c for key, _ in rows for c in (key, key + "_lo", key + "_hi")]]

    # d: paired per-task differences
    ax = fig.add_axes(pos["d"]); letter(ax, "d")
    P = res["paired"]
    ref = res["ref"]
    for i, (_, p) in enumerate(P.iterrows()):
        d = (res["succ"][ref] - res["succ"][p["other"]]).to_numpy()
        jit = RNG.uniform(-0.13, 0.13, len(d))
        ax.scatter(d, i + jit, s=5, color=col[p["other"]], alpha=0.45, lw=0, zorder=2)
        ax.plot([p["ci_lo"], p["ci_hi"]], [i - 0.3] * 2, color="black", lw=1.4)
        ax.plot(p["mean_difference"], i - 0.3, "o", ms=4.5, color="black", zorder=3)
        ptxt = "p < 0.001" if p["p_holm"] < 0.001 else f"p = {p['p_holm']:.2g}"
        ax.text(1.02, i - 0.3, f"{p['mean_difference'] * 100:+.0f} pts\n{ptxt}", va="center", ha="left", fontsize=6,
                transform=ax.get_yaxis_transform())
    ax.axvline(0, color=GREY, lw=0.6, ls=(0, (2, 2)), zorder=1)
    ax.set_yticks(range(len(P)), [f"vs {name(o)}" for o in P["other"]])
    ax.set_ylim(-0.85, len(P) - 0.45); ax.invert_yaxis()
    ax.set_xlim(-1.08, 1.08); ax.set_xticks([-1, -.5, 0, .5, 1], ["−100", "−50", "0", "+50", "+100"])
    ax.set_xlabel(f"Per-task difference in success (points)")
    ax.set_title(f"{name(ref)}, task by task")
    ax.text(0.98, 1.0, f"{name(ref).split()[0]} better →", transform=ax.transAxes, ha="right", va="top", fontsize=6, color=GREY)
    ax.text(0.02, 1.0, f"← {name(ref).split()[0]} worse", transform=ax.transAxes, ha="left", va="top", fontsize=6, color=GREY)
    src["d"] = pd.DataFrame({f"{name(ref)} minus {name(o)}": (res["succ"][ref] - res["succ"][o]) for o in P["other"]})

    # e: accuracy against time
    ax = fig.add_axes(pos["e"]); letter(ax, "e")
    ys = sorted(models, key=lambda m: M.loc[m, "success"])
    lab_y, last = {}, -1.0
    for m in ys:                                          # labels at least 0.07 apart in y, at the right of the panel
        lab_y[m] = max(M.loc[m, "success"], last + 0.07); last = lab_y[m]
    for m in models:
        r = M.loc[m]
        ax.plot([r["wall_s_q1"], r["wall_s_q3"]], [r["success"]] * 2, color=col[m], lw=1.0)
        ax.plot([r["median_wall_s"]] * 2, [r["success_lo"], r["success_hi"]], color=col[m], lw=1.0)
        ax.plot(r["median_wall_s"], r["success"], "o", ms=5, color=col[m], mec="white", mew=0.5, zorder=3)
        ax.annotate(name(m), (r["wall_s_q3"], r["success"]), xytext=(r["wall_s_q3"] * 1.15, lab_y[m]), textcoords="data",
                    fontsize=6, color=col[m], va="center",
                    arrowprops=dict(arrowstyle="-", color=col[m], lw=0.5, shrinkA=0, shrinkB=1) if abs(lab_y[m] - r["success"]) > 0.01 else None)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    lo = max(1, M["wall_s_q1"].min() / 2.5); hi = M["wall_s_q3"].max() * 6
    ax.set_xlim(lo, hi); ax.set_ylim(0, 1.05); pct(ax, "y")
    ax.set_xlabel("Seconds per task (median, IQR)"); ax.set_ylabel("Tasks solved (95% CI)")
    ax.set_title("Accuracy against wall-clock time")
    src["e"] = M[["display", "success", "success_lo", "success_hi", "median_wall_s", "wall_s_q1", "wall_s_q3", "mean_model_s", "mean_tool_s"]]

    if watermark:
        fig.text(0.5, 0.5, watermark, fontsize=26, color="#C00000", alpha=0.22, rotation=24, ha="center", va="center",
                 fontweight="bold", zorder=100)

    os.makedirs(out, exist_ok=True)
    paths = []
    for ext in ("pdf", "svg", "png"):
        p = os.path.join(out, f"figure.{ext}")
        fig.savefig(p)
        paths.append(p)
    for k_, v in src.items():
        v.to_csv(os.path.join(out, f"source_data_panel_{k_}.csv"))
    # overlap check (text boxes against each other), reported not silenced
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    texts = [t for t in fig.findobj(matplotlib.text.Text) if t.get_text().strip() and t.get_visible() and t.get_text() != watermark
             and not t.get_rotation()]                                    # rotated labels: their boxes overlap though the text does not
    boxes = [(t, t.get_window_extent(r)) for t in texts]
    clash = [(a.get_text()[:30], b.get_text()[:30]) for i, (a, ba) in enumerate(boxes) for b, bb in boxes[i + 1:] if ba.overlaps(bb)]
    plt.close(fig)
    if clash:
        print("label overlaps to fix:", clash[:10])
    return paths


# ------------------------------------------------------------------ text
def sentences(res: dict, errors: pd.DataFrame, man: dict) -> str:
    M = res["metrics"].set_index("model")
    P = res["paired"]
    k = int(M["k"].max())
    f = lambda v: f"{v * 100:.0f}%"                                                          # noqa: E731
    ci = lambda m, key: f"{f(M.loc[m, key])} (95% CI {f(M.loc[m, key + '_lo'])}–{f(M.loc[m, key + '_hi'])})"  # noqa: E731
    out = ["# Results, in sentences", "",
           "Generated from the records by analyze_benchmark.py; edit the wording, not the numbers.", ""]
    held = man.get("held_fixed", {})
    out.append(f"**Design.** Each model attempted the same {len(res['common'])} tasks {k} times, through the same agent "
               f"(tool offering `{held.get('tools', '?')}`, guard {'on' if held.get('guard', True) else 'off'}, at most "
               f"{held.get('max_turns', '?')} turns), on vmd-agent {man.get('vmd_agent_version', '?')} (commit "
               f"{str(man.get('git_commit', '?'))[:7]}). A program graded every answer against values known from how the test data "
               f"were built; no model judged another.")
    if len(errors):
        out.append(f"{len(errors)} run(s) failed at the model server and were excluded: " +
                   ", ".join(f"{name(m)} {n}" for m, n in errors["model"].value_counts().items()) + ".")
    if any(res["dropped"].values()):
        out.append("Tasks not run by every model were left out of the comparison: " +
                   "; ".join(f"{name(m)}: {', '.join(v)}" for m, v in res["dropped"].items() if v) + ".")
    out += ["", "**Accuracy.** " + " ".join(f"{name(m)} solved {ci(m, 'success')} of tasks, and solved {f(M.loc[m, 'pass^k'])} "
                                            f"on all {k} tries." for m in res["models"])]
    for _, p in P.iterrows():
        ptxt = "p < 0.001" if p["p_holm"] < 0.001 else f"p = {p['p_holm']:.2g}"
        out.append(f"Task by task, {name(p['reference'])} scored {p['mean_difference'] * 100:+.1f} points relative to {name(p['other'])} on average "
                   f"(95% CI {p['ci_lo'] * 100:+.1f} to {p['ci_hi'] * 100:+.1f}; paired sign-flip test, Holm-adjusted {ptxt}); "
                   f"it did better on {p['tasks_reference_better']} tasks, worse on {p['tasks_other_better']}, and the same on {p['tasks_tied']}.")
    out += ["", "**Behaviour.** " + " ".join(
        f"{name(m)} called a correct tool in {f(M.loc[m, 'right_tool'])} of answerable tasks, gave answers in which every number "
        f"appears in a tool result in {f(M.loc[m, 'numbers_grounded'])}, and refused {f(M.loc[m, 'refuses_correctly'])} of impossible or "
        f"disallowed requests correctly." for m in res["models"])]
    out += ["", "**Cost in time and tokens.** " + " ".join(
        f"{name(m)} took a median {M.loc[m, 'median_wall_s']:.0f} s per task (IQR {M.loc[m, 'wall_s_q1']:.0f}–{M.loc[m, 'wall_s_q3']:.0f} s) "
        f"and used on average {M.loc[m, 'mean_tokens_in'] / 1e3:.1f}k input and {M.loc[m, 'mean_tokens_out'] / 1e3:.1f}k output tokens per task"
        + (f" (about ${M.loc[m, 'usd_per_run']:.3f} per task at the prices given)" if "usd_per_run" in M and not np.isnan(M.loc[m].get("usd_per_run", np.nan)) else "")
        + "." for m in res["models"])]
    if man:
        w = {c["model"]: c for c in man.get("conditions", [])}
        out += ["", "**Setup (for Methods).** " + f"{man.get('cpu', '?')}, {man.get('memory_gb', '?')} GB memory, {man.get('os', '?')}; "
                f"VMD at {man.get('vmd', '?')}; Ollama {man.get('ollama_version', '?')}. " + " ".join(
                    f"{name(m)}: {c.get('server')}, temperature {c.get('temperature')}"
                    + (f", weights {c['weights'].get('digest', '')[:12]} ({c['weights'].get('parameter_size')}, {c['weights'].get('quantization')})"
                       if c.get("weights") else "") + "." for m, c in w.items())]
    out += ["", "**Figure caption (draft).** "
            f"**Claude Opus 5.5 and two open-weight models driving VMD through the same agent.** "
            f"**a**, Share of the {len(res['common'])} benchmark tasks solved, averaged over {k} tries per task (circles; bars, 95% "
            f"bootstrap CI over tasks; where every task scored 100%, the exact Clopper-Pearson interval over tasks) and solved on all "
            f"{k} tries (diamonds). **b**, Agent behaviour: a correct tool called (answerable tasks), every number in the answer "
            f"found, at the precision shown, in a tool result (numbers the model derived, such as differences or rounded values, "
            f"count as not found), tool calls that returned without error, and correct refusals of impossible or disallowed "
            f"requests. **c**, Success by kind of task; numbers in cells are percentages of runs passed, numbers in brackets the "
            f"tasks per kind. **d**, Per-task difference in success between Claude Opus 5.5 and "
            f"each open model (small points, one per task); black, mean with 95% bootstrap CI; p, paired sign-flip permutation test, "
            f"Holm-adjusted. **e**, Accuracy against median wall-clock time per task (bars: IQR of time, 95% CI of success). "
            f"Open models ran locally through Ollama; Claude Opus 5.5 through the Anthropic API, so times are not hardware-matched."]
    return "\n".join(out) + "\n"


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("folder")
    a.add_argument("--price", nargs="*", default=[], help="MODEL=IN,OUT in USD per million tokens (only used if given)")
    a.add_argument("--watermark", help=argparse.SUPPRESS)
    args = a.parse_args()
    price = {}
    for p in args.price:
        m, v = p.split("=")
        price[m] = tuple(float(x) for x in v.split(","))
    df, errors, man = load(args.folder)
    res = analyse(df, price)
    out = os.path.join(args.folder, "analysis")
    os.makedirs(out, exist_ok=True)
    res["metrics"].to_csv(os.path.join(out, "metrics.csv"), index=False)
    res["cat"].rename(columns=name).assign(n_tasks=res["cat_n"]).to_csv(os.path.join(out, "by_category.csv"))
    res["paired"].to_csv(os.path.join(out, "paired.csv"), index=False)
    res["succ"].rename(columns=name).to_csv(os.path.join(out, "per_task.csv"))
    draw(res, out, args.watermark)
    with open(os.path.join(out, "results.md"), "w") as fh:
        fh.write(sentences(res, errors, man))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
