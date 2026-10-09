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
from typing import Dict, List, NamedTuple, Optional

MODELS_CHECKED = "2026-10-06"
REGISTRY = "https://registry.ollama.ai/v2/library"
MANIFEST_TYPE = "application/vnd.docker.distribution.manifest.v2+json"


class Model(NamedTuple):
    tag: str            # what you give `ollama pull`
    label: str          # plain-language size class
    gb: float           # download size reported by the registry on MODELS_CHECKED
    licence: str
    suits: str          # what computer it suits (a rough guide, not a measurement)
    min_ram_gb: int = 0  # the memory the "suits" line asks for, as a number (used to pick one for this computer)
    min_vram_gb: int = 0  # the graphics-card memory that is enough on its own (0: no card size is listed)


CATALOGUE: List[Model] = [
    Model("granite4.1:3b", "Small and fast", 2.10, "Apache 2.0", "8 GB of memory", 8, 4),
    Model("granite4.1:8b", "Recommended", 5.35, "Apache 2.0", "16 GB of memory, or a graphics card", 16, 8),
    Model("gemma4:e4b", "Recommended, alternative", 6.58, "Apache 2.0", "16 GB of memory, or a graphics card", 16, 8),
    Model("lfm2.5:8b", "Fast on a plain CPU", 5.16, "LFM Open License v1.0 (read it; it is not Apache)", "16 GB of memory", 16),
    Model("gemma4:12b", "Larger", 8.02, "Apache 2.0", "32 GB of memory, or a good graphics card", 32, 12),
    Model("gpt-oss:20b", "Larger", 13.79, "Apache 2.0", "32 GB of memory, or a 16 GB graphics card", 32, 16),
    Model("qwen3.8:27b", "Largest listed", 17.74, "Apache 2.0", "48 GB of memory, or a 24 GB graphics card", 48, 24),
]
DEFAULT_MODEL = "granite4.1:8b"


def recommend(ram_gb: Optional[float], nvidia_gpu: bool = False) -> Optional[Model]:
    """The model to suggest for a computer with ``ram_gb`` of memory: the default if it fits, else the small one, else None (too little memory to
    run a model that can use tools: an online service or Claude is the way). Unknown memory gets the default, which `vmd-agent doctor` then checks.
    The default is the suggestion, not the biggest that fits: bigger models are slower, and the benchmark (``vmd-agent bench models``) says which is better for you."""
    known = by_tag()
    if ram_gb is None or nvidia_gpu or ram_gb >= known[DEFAULT_MODEL].min_ram_gb:
        return known[DEFAULT_MODEL]
    small = known["granite4.1:3b"]
    return small if ram_gb >= small.min_ram_gb else None


def fit(m: Model, ram_gb: Optional[float], vram_gb: Optional[float] = None) -> str:
    """How ``m`` suits a computer with ``ram_gb`` of memory (and a graphics card with ``vram_gb``): ``fits``, ``tight`` (it may run, slowly, or fail
    when other programs are open), ``too big``, or ``unknown`` when the memory could not be read. A rough guide from the "suits" column, not a measurement."""
    if vram_gb is not None and m.min_vram_gb and vram_gb >= m.min_vram_gb:
        return "fits"
    if ram_gb is None:
        return "unknown"
    if ram_gb >= m.min_ram_gb:
        return "fits"
    return "tight" if ram_gb >= 0.75 * m.min_ram_gb else "too big"


def advise(ram_gb: Optional[float], vram_gb: Optional[float] = None, installed: Optional[List[str]] = None) -> List[Dict[str, object]]:
    """Every model of the catalogue with how it suits this computer, whether it is already downloaded, and which one is suggested first."""
    pick = recommend(ram_gb, bool(vram_gb and vram_gb >= by_tag()[DEFAULT_MODEL].min_vram_gb))
    return [{"tag": m.tag, "label": m.label, "gb": m.gb, "licence": m.licence, "suits": m.suits, "fit": fit(m, ram_gb, vram_gb),
             "installed": m.tag in (installed or []), "recommended": bool(pick and pick.tag == m.tag)} for m in CATALOGUE]


def by_tag() -> Dict[str, Model]:
    return {m.tag: m for m in CATALOGUE}


def describe_device(ram_gb: Optional[float], gpu: Optional[str], vram_gb: Optional[float], apple_silicon: bool = False) -> str:
    """One line saying what the suggestion is based on."""
    bits = [f"{ram_gb:g} GB of memory" if ram_gb else "memory not read"]
    if gpu:
        bits.append(f"{gpu}" + (f" with {vram_gb:g} GB" if vram_gb else ""))
    elif apple_silicon:
        bits.append("Apple Silicon (the memory is shared with the graphics, so it all counts)")
    else:
        bits.append("no NVIDIA graphics card")
    return ", ".join(bits)


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


def table(ram_gb: Optional[float] = None, vram_gb: Optional[float] = None, installed: Optional[List[str]] = None) -> str:
    """The catalogue as plain text; with the computer's memory it also says how each model suits it and which are downloaded."""
    rows = []
    for a in advise(ram_gb, vram_gb, installed):
        mark = ("  <- suggested" if a["recommended"] else "") + ("  [downloaded]" if a["installed"] else "")
        suit = f"  {str(a['fit']):<8}" if ram_gb is not None or vram_gb is not None else ""
        rows.append(f"{a['tag']:<16} {a['gb']:>6.2f} GB{suit}  {a['licence']:<46} {a['label']}: {a['suits']}{mark}")
    head = f"As of {MODELS_CHECKED} (checked against the Ollama registry):"
    if ram_gb is not None or vram_gb is not None:
        head += "  (the third column is how each suits this computer)"
    return head + "\n" + "\n".join(rows)
