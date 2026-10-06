"""Models the benchmark can evaluate.

A *model* is any callable ``model(prompt, images, text) -> str`` that returns a
response containing the JSON object requested by
:func:`vmd_agent.bench.questions.format_prompt`.

Offline baselines are included so the harness, the scorer and CI run with no
network and no API key, and so results always come with reference points:

``ConstantModel``    always answers the same thing: the "no information" floor
``RandomModel``      uniform random answers
``StatsReaderModel`` a rule-based reader of the *text* grounding only. It cannot
                     see images, so it abstains on anything the text does not
                     state; it shows what the structured text alone makes
                     answerable
``OracleModel``      knows the answers; checks the scorer and gives the ceiling
``AnthropicModel``   a real vision-language model through the Anthropic API
"""
from __future__ import annotations

import base64
import json
import random
import re
from typing import List

SYSTEM_PROMPT = (
    "You are being evaluated on reading molecular visualizations. Answer using "
    "ONLY the images and text supplied in this message. Do not rely on "
    "recognising the molecule from memory or on outside knowledge of what it "
    "might be. If the supplied evidence cannot settle the question, abstain "
    "rather than guess. Reply with the JSON object requested and nothing else."
)


def _resp(answer, conf=0.9, abstain=False):
    return json.dumps({"answer": answer, "confidence": conf,
                       "abstain": abstain})


class ConstantModel:
    name = "constant-prior"

    def __init__(self, boolean=False, numeric=1, choice="alpha"):
        self.v = {"boolean": boolean, "numeric": numeric, "choice": choice}

    def __call__(self, prompt, images, text, question=None):
        kind = (question or {}).get("kind", "boolean")
        return _resp(self.v[kind], conf=0.5)


class RandomModel:
    name = "random"

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def __call__(self, prompt, images, text, question=None):
        q = question or {}
        kind = q.get("kind", "boolean")
        if kind == "boolean":
            return _resp(self.rng.random() < 0.5, conf=0.5)
        if kind == "numeric":
            return _resp(self.rng.randint(0, 100), conf=0.5)
        return _resp(self.rng.choice(q.get("choices", ["alpha"])), conf=0.5)


class StatsReaderModel:
    """Reads only the grounding *text*; blind to images by construction."""

    name = "stats-reader"

    def __call__(self, prompt, images, text, question=None):
        q = question or {}
        key = q.get("key")
        t = text or ""
        ans = None
        if key == "n_chains":
            m = re.search(r"(\d+) protein chains?", t) or \
                re.search(r"(\d+) chains?", t)
            if m:
                ans = int(m.group(1))
            elif re.search(r"\b1 residues|atoms ·", t) and "chains" not in t:
                ans = None
        elif key == "n_disulfides":
            m = re.search(r"(\d+) disulfide bridge", t)
            if m:
                ans = int(m.group(1))
            elif "STRUCTURE STATISTICS" in t:
                ans = 0                      # caption omits the line when zero
        elif key == "helix_percent":
            m = re.search(r"([\d.]+)% helix", t)
            ans = float(m.group(1)) if m else None
        elif key == "fold_class":
            m = re.search(r"([\d.]+)% helix · ([\d.]+)% sheet", t)
            if m:
                from vmd_agent.bench.truth import classify_fold
                ans = classify_fold(float(m.group(1)), float(m.group(2)))
        elif key in ("has_ligand", "has_lipid", "has_nucleic"):
            if "VISUAL LEGEND" in t:
                needle = {"has_ligand": "ligand / non-standard",
                          "has_lipid": "lipid membrane",
                          "has_nucleic": "nucleic acid"}[key]
                ans = needle in t
        if ans is None:
            return _resp(None, conf=0.0, abstain=True)
        return _resp(ans, conf=0.95)


class OracleModel:
    """Reads the answer from the question: a control, never a candidate."""
    name = "oracle"
    needs_truth = True      # the runner withholds ground truth from everyone else

    def __call__(self, prompt, images, text, question=None):
        return _resp((question or {}).get("answer"), conf=1.0)


class AnthropicModel:
    """Vision-language model via the Anthropic Messages API.

    The API key is read from ``ANTHROPIC_API_KEY`` (the SDK default); it is never
    written to results. ``model`` must be given explicitly so a run records
    exactly which model it measured.
    """

    def __init__(self, model: str, max_tokens: int = 300,
                 client=None, temperature: float = 0.0):
        if not model:
            raise ValueError("pass the model id explicitly")
        self.name = model
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        if client is None:
            try:
                import anthropic
            except ImportError as e:                       # pragma: no cover
                raise ImportError("pip install anthropic to use "
                                  "AnthropicModel") from e
            client = anthropic.Anthropic()
        self.client = client

    def build_request(self, prompt, images, text) -> dict:
        """The exact keyword arguments sent to ``messages.create``."""
        content: List[dict] = []
        for path in images:
            with open(path, "rb") as fh:
                data = base64.standard_b64encode(fh.read()).decode()
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/png", "data": data}})
        body = (text + "\n\n" if text else "") + prompt
        content.append({"type": "text", "text": body})
        return dict(model=self.model, max_tokens=self.max_tokens,
                    temperature=self.temperature, system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}])

    def __call__(self, prompt, images, text, question=None):
        resp = self.client.messages.create(
            **self.build_request(prompt, images, text))
        return "".join(getattr(b, "text", "") for b in resp.content)
