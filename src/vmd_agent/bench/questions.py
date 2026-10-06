"""Question generation for the grounded-interpretation benchmark.

Each question carries the ground-truth answer *and* the information sources
that could in principle answer it:

``image``   visible in a rendered view (given the colour conventions)
``legend``  stated by the visual legend
``stats``   stated by the structure-statistics caption

That ``sources`` field is what lets the scorer separate a wrong answer from an
*unsupported* answer: asking for a disulfide count from a bare picture is not a
vision failure, it is a question the evidence cannot settle, and the right
response is to abstain.
"""
from __future__ import annotations

from typing import List

FOLD_CHOICES = ["alpha", "beta", "mixed", "coil"]
FOLD_LABELS = {"alpha": "mostly alpha-helical",
               "beta": "mostly beta-sheet",
               "mixed": "mixed alpha/beta",
               "coil": "mostly coil / little regular structure"}


def _q(qid, text, kind, answer, sources, structure, **extra):
    q = {"id": f"{structure}:{qid}", "key": qid, "text": text, "kind": kind,
         "answer": answer, "sources": sorted(sources), "structure": structure}
    q.update(extra)
    return q


def build_questions(truth: dict, structure: str) -> List[dict]:
    """All applicable questions for one structure's ground truth."""
    if not truth.get("ok"):
        return []
    qs: List[dict] = []
    if truth["has_protein"]:
        qs.append(_q("n_chains",
                     "How many separate protein chains are shown?",
                     "numeric", truth["n_protein_chains"],
                     {"image", "stats"}, structure, tolerance=0))
    qs.append(_q("has_ligand",
                 "Does the system contain a ligand, cofactor or other "
                 "non-standard molecule (not water or simple ions)?",
                 "boolean", truth["has_ligand"], {"image", "legend"},
                 structure))
    qs.append(_q("has_lipid",
                 "Does the system contain a lipid membrane?",
                 "boolean", truth["has_lipid"], {"image", "legend"},
                 structure))
    qs.append(_q("has_nucleic",
                 "Does the system contain a nucleic acid (DNA or RNA)?",
                 "boolean", truth["has_nucleic"], {"image", "legend"},
                 structure))
    if truth.get("fold_class"):
        qs.append(_q("fold_class",
                     "Which best describes the protein's secondary "
                     "structure?",
                     "choice", truth["fold_class"], {"image", "stats"},
                     structure, choices=FOLD_CHOICES,
                     choice_labels=FOLD_LABELS))
        qs.append(_q("helix_percent",
                     "Approximately what percentage of residues are in "
                     "alpha-helices (give a number 0-100)?",
                     "numeric", truth["helix_percent"], {"stats"}, structure,
                     tolerance=10.0))
    if truth.get("n_disulfides") is not None:
        qs.append(_q("n_disulfides",
                     "How many disulfide bridges does the protein contain?",
                     "numeric", truth["n_disulfides"], {"stats"}, structure,
                     tolerance=0))
    if truth.get("ligand_buried") is not None:
        qs.append(_q("ligand_buried",
                     "Is the ligand mostly buried inside the protein "
                     "(at least half of its surface occluded)?",
                     "boolean", truth["ligand_buried"], {"image"}, structure))
    return qs


def format_prompt(q: dict) -> str:
    """The question text plus the required answer format."""
    if q["kind"] == "boolean":
        fmt = '"answer" must be true or false.'
    elif q["kind"] == "numeric":
        fmt = '"answer" must be a number.'
    else:
        opts = ", ".join(f'"{c}" ({q["choice_labels"][c]})'
                         for c in q["choices"])
        fmt = f'"answer" must be one of: {opts}.'
    return (f"{q['text']}\n\nRespond with a single JSON object: "
            f'{{"answer": ..., "confidence": <0..1>, "abstain": <true|false>}}. '
            f"{fmt} Set abstain to true (answer null) if the evidence you "
            "were given cannot settle the question.")
