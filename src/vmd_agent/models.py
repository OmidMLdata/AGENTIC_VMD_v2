"""The open-source models this toolkit suggests, and a live check that they still exist.

``CATALOGUE`` was checked by hand against the public Ollama registry and library pages on
``MODELS_CHECKED``. Sizes are the real download sizes the registry reported that day, licences
are the ones the registry serves with each model, and "tools" is the badge the Ollama library
page showed (the toolkit needs a model that can call tools). Model names move fast, so a
name that existed on that day may be renamed or gone later: :func:`check` asks the registry
again, and the setup does that before it downloads anything.

Only granite4.1:8b and granite4.1:3b were run with this toolkit (2026-10-06). Whether one drives VMD well is exactly what
the benchmark is for; the list is a starting point, not a recommendation backed by results.

Nothing here imports the rest of the package.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List, NamedTuple

MODELS_CHECKED = "2026-10-06"
REGISTRY = "https://registry.ollama.ai/v2/library"
MANIFEST_TYPE = "application/vnd.docker.distribution.manifest.v2+json"


class Model(NamedTuple):
    tag: str            # what you give `ollama pull`
    label: str          # plain-language size class
    gb: float           # download size reported by the registry on MODELS_CHECKED
    licence: str
    suits: str          # what computer it suits (a rough guide, not a measurement)


CATALOGUE: List[Model] = [
    Model("granite4.1:3b", "Small and fast", 2.10, "Apache 2.0", "8 GB of memory"),
    Model("granite4.1:8b", "Recommended", 5.35, "Apache 2.0", "16 GB of memory, or a graphics card"),
    Model("gemma4:e4b", "Recommended, alternative", 6.58, "Apache 2.0", "16 GB of memory, or a graphics card"),
    Model("lfm2.5:8b", "Fast on a plain CPU", 5.16, "LFM Open License v1.0 (read it; it is not Apache)", "16 GB of memory"),
    Model("gemma4:12b", "Larger", 8.02, "Apache 2.0", "32 GB of memory, or a good graphics card"),
    Model("gpt-oss:20b", "Larger", 13.79, "Apache 2.0", "32 GB of memory, or a 16 GB graphics card"),
    Model("qwen3.8:27b", "Largest listed", 17.74, "Apache 2.0", "48 GB of memory, or a 24 GB graphics card"),
]
DEFAULT_MODEL = "granite4.1:8b"


def _split(tag: str):
    name, _, version = tag.partition(":")
    return name, (version or "latest")


def check(tag: str, timeout: float = 15.0, registry: str = REGISTRY) -> Dict[str, object]:
    """Ask the Ollama registry whether ``tag`` exists. Returns
    ``{"tag", "exists": True|False|None, "gb": float|None, "error": str}``;
    ``exists`` is None when the registry could not be reached (offline), which is
    not the same as "does not exist"."""
    name, version = _split(tag)
    req = urllib.request.Request(f"{registry}/{name}/manifests/{version}",
                                 headers={"Accept": MANIFEST_TYPE, "User-Agent": "vmd-agent"})
    out: Dict[str, object] = {"tag": tag, "exists": None, "gb": None, "error": ""}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            m = json.loads(r.read().decode("utf-8", "replace"))
        total = sum(int(l.get("size", 0)) for l in m.get("layers", []))
        out.update(exists=True, gb=round(total / 1e9, 2))
    except urllib.error.HTTPError as e:
        out.update(exists=False if e.code == 404 else None, error=f"HTTP {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        out["error"] = str(getattr(e, "reason", e))[:120]
    return out


def table() -> str:
    """The catalogue as plain text."""
    rows = [f"{m.tag:<16} {m.gb:>6.2f} GB  {m.licence:<46} {m.label}: {m.suits}" for m in CATALOGUE]
    return f"As of {MODELS_CHECKED} (checked against the Ollama registry):\n" + "\n".join(rows)
