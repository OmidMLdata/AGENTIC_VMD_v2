"""Blinded expert-rating study for the automatic representation policy.

The rule-based policy in :func:`vmd_agent.recipes._auto_protein_reps` is
plausible but unvalidated. This module builds the instrument to test it: for
each structure it renders the same view under several policies, shuffles the
images behind opaque IDs, and writes a spreadsheet for domain scientists to
rate. :func:`summarize_ratings` unblinds with the key file and compares
policies with paired statistics.

Policies requiring different VMD representations need the VMD renderer; the
sheet/key/analysis machinery works with any set of pre-made images via
:func:`make_sheet_from_images`.
"""
from __future__ import annotations

import csv
import json
import os
import random
from typing import Dict, List, Optional, Sequence

import numpy as np

POLICIES = {
    "auto": {},
    "naive_cartoon": {"representation": "NewCartoon"},
    "lines": {"representation": "Lines"},
}
CRITERIA = ["legibility", "accuracy_of_depiction", "publication_suitability"]


def make_sheet_from_images(images: Dict[str, Dict[str, str]], out_dir: str,
                           seed: int = 0) -> dict:
    """``images[structure][policy] = png``  ->  blinded sheet + key.

    Copies images to ``out_dir/images/<blind_id>.png`` (names reveal nothing),
    writes ``ratings.csv`` for raters and ``key.json`` for the analyst.
    """
    import shutil
    rng = random.Random(seed)
    os.makedirs(os.path.join(out_dir, "images"), exist_ok=True)
    items = [(s, p, path) for s, d in images.items() for p, path in d.items()]
    rng.shuffle(items)
    key, rows = {}, []
    for i, (s, p, path) in enumerate(items):
        bid = f"R{i:04d}"
        shutil.copyfile(path, os.path.join(out_dir, "images", f"{bid}.png"))
        key[bid] = {"structure": s, "policy": p}
        rows.append({"blind_id": bid, "image": f"images/{bid}.png",
                     **{c: "" for c in CRITERIA}})
    with open(os.path.join(out_dir, "ratings.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["blind_id", "image"] + CRITERIA)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out_dir, "key.json"), "w") as fh:
        json.dump(key, fh, indent=2)
    with open(os.path.join(out_dir, "INSTRUCTIONS.txt"), "w") as fh:
        fh.write(
            "Rate each image 1 (poor) to 5 (excellent) on each column of "
            "ratings.csv:\n"
            "  legibility               can you read the fold / components?\n"
            "  accuracy_of_depiction    does it show the molecule faithfully?\n"
            "  publication_suitability  would you use it as a figure?\n"
            "Do not look at key.json. Leave a cell blank to skip.\n")
    return {"n_images": len(items), "sheet": os.path.join(out_dir,
                                                          "ratings.csv"),
            "key": os.path.join(out_dir, "key.json")}


def make_rating_sheet(structures: Sequence[str], out_dir: str,
                      policies: Sequence[str] = ("auto", "naive_cartoon",
                                                 "lines"),
                      view: str = "front", vmd_path: Optional[str] = None,
                      seed: int = 0) -> dict:
    """Render every structure under every policy with VMD and build the sheet."""
    from vmd_agent.visual.renderers import VMDRenderer
    from vmd_agent.structure.detect import detect_system
    from vmd_agent.visual.recipes import generate_visualization_recipe
    rend = VMDRenderer(vmd_path)
    if not rend.available():
        return {"ok": False, "error": "This study varies the drawn "
                "representation, which needs VMD. Provide VMD or build the "
                "sheet from existing images with make_sheet_from_images."}
    images: Dict[str, Dict[str, str]] = {}
    for si, path in enumerate(structures):
        det = detect_system(path)
        if det.get("error"):
            continue
        for pol in policies:
            kw = POLICIES[pol]
            d = os.path.join(out_dir, "_work", f"S{si:03d}_{pol}")
            os.makedirs(d, exist_ok=True)
            rec = os.path.join(d, "recipe.tcl")
            generate_visualization_recipe(det, out_path=rec, **kw)
            rv = rend.render_views(path, None, detection=det,
                                   recipe_path=rec, views=[view], out_dir=d)
            if rv.get("images", {}).get(view):
                images.setdefault(f"S{si:03d}", {})[pol] = rv["images"][view]
    out = make_sheet_from_images(images, out_dir, seed=seed)
    out["ok"] = True
    return out


def summarize_ratings(ratings_csv: str, key_json: str, n_boot: int = 2000,
                      seed: int = 0) -> dict:
    """Unblind and compare policies (paired by structure)."""
    from scipy import stats
    with open(key_json) as fh:
        key = json.load(fh)
    scores: Dict[str, Dict[str, Dict[str, List[float]]]] = {}
    with open(ratings_csv) as fh:
        for row in csv.DictReader(fh):
            k = key.get(row["blind_id"])
            if not k:
                continue
            for c in CRITERIA:
                if row.get(c, "").strip():
                    scores.setdefault(c, {}).setdefault(
                        k["policy"], {}).setdefault(
                        k["structure"], []).append(float(row[c]))
    rng = np.random.default_rng(seed)
    out: Dict[str, dict] = {}
    for c, by_pol in scores.items():
        means = {p: {s: float(np.mean(v)) for s, v in d.items()}
                 for p, d in by_pol.items()}
        out[c] = {"per_policy": {}, "vs_auto": {}}
        for p, d in means.items():
            vals = np.array(list(d.values()))
            boots = [rng.choice(vals, len(vals)).mean()
                     for _ in range(n_boot)]
            out[c]["per_policy"][p] = {
                "mean": float(vals.mean()), "n_structures": len(vals),
                "ci95": [float(np.percentile(boots, 2.5)),
                         float(np.percentile(boots, 97.5))]}
        if "auto" in means:
            for p in means:
                if p == "auto":
                    continue
                common = sorted(set(means["auto"]) & set(means[p]))
                if len(common) < 3:
                    continue
                a = np.array([means["auto"][s] for s in common])
                b = np.array([means[p][s] for s in common])
                try:
                    w = stats.wilcoxon(a, b)
                    pval = float(w.pvalue)
                except ValueError:       # all differences zero
                    pval = 1.0
                out[c]["vs_auto"][p] = {"n_pairs": len(common),
                                        "mean_diff_auto_minus_other":
                                        float(np.mean(a - b)),
                                        "wilcoxon_p": pval}
    return out
