"""The grounding ladder: what evidence a model is given with each question.

The research question is whether *structured grounding* improves a model's
reading of a molecular visualization. The conditions form an ablation ladder
from no evidence to everything the toolkit produces, plus adversarial
conditions that give the model grounding that is deliberately wrong.

=========================  =======  ======  =======  ===========================
condition                  images   legend  stats    sources it can use
=========================  =======  ======  =======  ===========================
blind                      -        -       -        none (measures priors/guess)
raw                        1 view   -       -        image
legend                     1 view   yes     -        image, legend
annotated                  1 panel  baked   baked    image, legend, stats
legend_stats               1 view   yes     yes      image, legend, stats
multiview_legend_stats     3 views  yes     yes      image, legend, stats
text_only                  -        yes     yes      legend, stats
misleading_legend          1 view   WRONG   -        image (legend is a trap)
=========================  =======  ======  =======  ===========================

``blind`` and ``text_only`` are controls. ``blind`` shows what a model
asserts without evidence (hallucination by prior); ``text_only`` shows how much
of the task the structured text alone can answer, i.e. how much the images add.
``misleading_legend`` tests whether a model blindly trusts grounding text that
contradicts the picture, which is the failure grounding could introduce.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

CONDITIONS: Dict[str, dict] = {
    "blind": {"images": "none", "legend": False, "stats": False,
              "sources": set()},
    "raw": {"images": "single", "legend": False, "stats": False,
            "sources": {"image"}},
    "legend": {"images": "single", "legend": True, "stats": False,
               "sources": {"image", "legend"}},
    "annotated": {"images": "annotated", "legend": False, "stats": False,
                  "sources": {"image", "legend", "stats"}},
    "legend_stats": {"images": "single", "legend": True, "stats": True,
                     "sources": {"image", "legend", "stats"}},
    "multiview_legend_stats": {"images": "multi", "legend": True,
                               "stats": True,
                               "sources": {"image", "legend", "stats"}},
    "text_only": {"images": "none", "legend": True, "stats": True,
                  "sources": {"legend", "stats"}},
    "misleading_legend": {"images": "single", "legend": "misleading",
                          "stats": False, "sources": {"image"}},
}

DEFAULT_CONDITIONS = ["blind", "raw", "legend", "annotated", "legend_stats",
                      "multiview_legend_stats", "text_only",
                      "misleading_legend"]

_SWAPS = [("purple", "yellow"), ("helix", "strand"), ("cyan", "green"),
          ("blue", "red")]


def misleading_legend(lines: Sequence[str],
                      other: Optional[Sequence[str]] = None) -> List[str]:
    """A legend that contradicts the picture.

    With ``other`` (the legend of a different structure) the mismatched legend
    is returned; otherwise colours and secondary-structure words are swapped
    pairwise (``purple helix`` becomes ``yellow strand`` and so on).
    """
    if other:
        return list(other)
    out = []
    for ln in lines:
        s = ln
        for a, b in _SWAPS:
            s = re.sub(rf"\b{a}\b", "\0A", s)
            s = re.sub(rf"\b{b}\b", a, s)
            s = s.replace("\0A", b)
        out.append(s)
    return out


def is_answerable(question: dict, condition: str) -> bool:
    """Whether the evidence in ``condition`` could settle ``question``."""
    return bool(set(question["sources"]) & CONDITIONS[condition]["sources"])


def build_context(condition: str, assets: dict) -> dict:
    """Images and text a model receives under ``condition``.

    ``assets`` holds: ``raw`` {view: path}, ``annotated`` {view: path},
    ``legend`` [str], ``colour_key`` [str], ``stats`` [str] and
    ``other_legend`` [str] (a different structure's legend).
    """
    spec = CONDITIONS[condition]
    images: List[str] = []
    raw = assets.get("raw") or {}
    mode = spec["images"]
    if mode == "single" and raw:
        images = [raw.get("front") or next(iter(raw.values()))]
    elif mode == "multi" and raw:
        images = list(raw.values())
    elif mode == "annotated":
        ann = assets.get("annotated") or {}
        if ann:
            images = [ann.get("front") or next(iter(ann.values()))]

    parts: List[str] = []
    if spec["legend"] is True:
        parts.append("VISUAL LEGEND (what each colour/shape in the image is):\n"
                     + "\n".join(f"- {ln.replace('**', '')}"
                                 for ln in assets.get("legend", [])))
        if assets.get("colour_key"):
            parts.append("COLOUR KEY:\n" + "\n".join(assets["colour_key"]))
    elif spec["legend"] == "misleading":
        wrong = misleading_legend(assets.get("legend", []),
                                  assets.get("other_legend"))
        parts.append("VISUAL LEGEND (what each colour/shape in the image is):\n"
                     + "\n".join(f"- {ln.replace('**', '')}" for ln in wrong))
    if spec["stats"]:
        parts.append("STRUCTURE STATISTICS:\n"
                     + "\n".join(assets.get("stats", [])))
    needs_images = mode != "none"
    return {"images": images, "text": "\n\n".join(parts),
            "available": (bool(images) or not needs_images)}
