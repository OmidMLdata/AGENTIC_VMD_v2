"""VMD's actual colour palette, and the colour key for each colouring method.

Every rendered image needs a key saying *what each colour means*, otherwise an
interpretation of the picture is guesswork. These tables mirror VMD's own
defaults so the key matches the pixels.

A note on carbon: VMD colours carbon **cyan** in its Name/Element colouring
(PyMOL uses green, and many textbooks use grey/black). Getting this wrong makes
a legend actively misleading, so the element table below follows VMD.
"""
from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# VMD ColorID table (index -> name, approximate sRGB hex)
COLOR_IDS = {
    0: ("blue", "#0000ff"), 1: ("red", "#ff0000"), 2: ("gray", "#808080"),
    3: ("orange", "#ff8c00"), 4: ("yellow", "#ffff00"), 5: ("tan", "#d2b48c"),
    6: ("silver", "#c0c0c0"), 7: ("green", "#00ff00"), 8: ("white", "#ffffff"),
    9: ("pink", "#ff80c0"), 10: ("cyan", "#00ffff"), 11: ("purple", "#a000ff"),
    12: ("lime", "#80ff00"), 13: ("mauve", "#c08080"), 14: ("ochre", "#a06000"),
    15: ("iceblue", "#80c0ff"), 16: ("black", "#000000"),
    17: ("yellow2", "#e0e000"), 18: ("yellow3", "#c0c000"),
    19: ("green2", "#00c000"), 20: ("green3", "#00a000"),
    21: ("cyan2", "#00c0c0"), 22: ("cyan3", "#00a0a0"),
    23: ("blue2", "#4040ff"), 24: ("blue3", "#0000c0"),
    25: ("violet", "#c000ff"), 26: ("violet2", "#a000c0"),
    27: ("magenta", "#ff00ff"), 28: ("magenta2", "#c000c0"),
    29: ("red2", "#c00000"), 30: ("red3", "#a00000"),
    31: ("orange2", "#e07000"), 32: ("orange3", "#c05000"),
}

# ---- element colours as VMD draws them (Name / Element colouring) ----------
ELEMENT_COLORS = {
    "C":  ("cyan", "#00ffff"),
    "H":  ("white", "#ffffff"),
    "N":  ("blue", "#0000ff"),
    "O":  ("red", "#ff0000"),
    "S":  ("yellow", "#ffff00"),
    "P":  ("tan", "#d2b48c"),
    "F":  ("green", "#00ff00"),
    "CL": ("green", "#00ff00"),
    "BR": ("ochre", "#a06000"),
    "I":  ("purple", "#a000ff"),
    "NA": ("blue", "#0000ff"),
    "K":  ("purple", "#a000ff"),
    "MG": ("green", "#00ff00"),
    "CA": ("gray", "#808080"),
    "ZN": ("gray", "#808080"),
    "FE": ("ochre", "#a06000"),
}

# ---- secondary structure, as NewCartoon + "Structure" colours it -----------
STRUCTURE_COLORS = {
    "alpha helix":     ("purple", "#a000ff"),
    "3-10 helix":      ("blue", "#0000ff"),
    "pi helix":        ("red", "#ff0000"),
    "extended beta":   ("yellow", "#ffff00"),
    "beta bridge":     ("tan", "#d2b48c"),
    "turn":            ("cyan", "#00ffff"),
    "coil":            ("white", "#ffffff"),
}

# ---- residue chemistry, as "ResType" colours it ---------------------------
RESTYPE_COLORS = {
    "nonpolar / hydrophobic": ("white", "#ffffff"),
    "basic (positive)":       ("blue", "#0000ff"),
    "acidic (negative)":      ("red", "#ff0000"),
    "polar (uncharged)":      ("green", "#00ff00"),
}

# chains are assigned ColorIDs in order
_CHAIN_ORDER = [0, 1, 4, 7, 10, 11, 3, 9, 12, 15, 17, 19, 21, 23, 25, 27]


def chain_colors(chains) -> list:
    """Colour key for per-chain colouring, in VMD's assignment order."""
    out = []
    for i, ch in enumerate(chains or []):
        cid = _CHAIN_ORDER[i % len(_CHAIN_ORDER)]
        name, hexv = COLOR_IDS[cid]
        out.append({"label": f"chain {ch}", "color": name, "hex": hexv,
                    "color_id": cid})
    return out


def beta_key(is_alphafold: bool = False) -> list:
    """Colour key for B-factor ('Beta') colouring — a scale, not categories."""
    if is_alphafold:
        return [
            {"label": "pLDDT > 90 (very high confidence)", "color": "blue",
             "hex": "#0000ff"},
            {"label": "pLDDT 70-90 (confident)", "color": "cyan",
             "hex": "#00ffff"},
            {"label": "pLDDT 50-70 (low)", "color": "yellow", "hex": "#ffff00"},
            {"label": "pLDDT < 50 (very low / disordered)", "color": "red",
             "hex": "#ff0000"},
        ]
    return [
        {"label": "low B-factor (rigid, well ordered)", "color": "blue",
         "hex": "#0000ff"},
        {"label": "intermediate B-factor", "color": "white", "hex": "#ffffff"},
        {"label": "high B-factor (mobile, poorly ordered)", "color": "red",
         "hex": "#ff0000"},
    ]


def color_key(color_method: str, detection: Optional[dict] = None,
              is_alphafold: bool = False, elements=None) -> dict:
    """Build the colour key for one VMD colouring method.

    Returns ``{"method", "type", "description", "entries": [...]}`` where each
    entry has a human ``label``, a VMD colour ``name`` and an approximate
    ``hex`` value so it can be drawn into a legend panel.
    """
    m = (color_method or "").split()[0]
    det = detection or {}

    if m == "Structure":
        return {"method": "Structure", "type": "categorical",
                "description": "Colour by secondary structure (STRIDE in "
                               "VMD; DSSP in the matplotlib backend).",
                "entries": [{"label": k, "color": v[0], "hex": v[1]}
                            for k, v in STRUCTURE_COLORS.items()]}
    if m == "Chain":
        chains = det.get("components", {}).get("protein", {}).get("chains", [])
        return {"method": "Chain", "type": "categorical",
                "description": "One colour per chain, assigned in order.",
                "entries": [{"label": e["label"], "color": e["color"],
                             "hex": e["hex"]} for e in chain_colors(chains)]}
    if m in ("Name", "Element", "Type"):
        els = elements or ["C", "N", "O", "S", "H"]
        seen, entries = set(), []
        for e in els:
            e = str(e).upper()
            if e in ELEMENT_COLORS and e not in seen:
                seen.add(e)
                nm, hx = ELEMENT_COLORS[e]
                entries.append({"label": f"{e} ({_el_name(e)})",
                                "color": nm, "hex": hx})
        return {"method": m, "type": "categorical",
                "description": "Colour by chemical element, using VMD's "
                               "palette — note carbon is CYAN in VMD.",
                "entries": entries}
    if m == "ResType":
        return {"method": "ResType", "type": "categorical",
                "description": "Colour by residue chemistry.",
                "entries": [{"label": k, "color": v[0], "hex": v[1]}
                            for k, v in RESTYPE_COLORS.items()]}
    if m == "Beta":
        return {"method": "Beta", "type": "continuous",
                "description": ("Colour by the B-factor column — pLDDT "
                                "confidence for an AlphaFold model"
                                if is_alphafold else
                                "Colour by crystallographic B-factor "
                                "(thermal displacement)."),
                "entries": beta_key(is_alphafold)}
    if m == "ResName":
        return {"method": "ResName", "type": "categorical",
                "description": "One colour per residue type (many colours; "
                               "read specific residues from the structure "
                               "rather than the key).",
                "entries": []}
    if m == "ColorID":
        cid = 0
        try:
            cid = int((color_method or "ColorID 0").split()[1])
        except Exception:
            pass
        nm, hx = COLOR_IDS.get(cid, ("blue", "#0000ff"))
        return {"method": color_method, "type": "single",
                "description": "A single fixed colour.",
                "entries": [{"label": "this component", "color": nm, "hex": hx}]}
    return {"method": color_method or "unknown", "type": "unknown",
            "description": "No colour key available for this method.",
            "entries": []}


def _el_name(sym: str) -> str:
    return {"C": "carbon", "H": "hydrogen", "N": "nitrogen", "O": "oxygen",
            "S": "sulfur", "P": "phosphorus", "F": "fluorine",
            "CL": "chloride", "BR": "bromine", "I": "iodine", "NA": "sodium",
            "K": "potassium", "MG": "magnesium", "CA": "calcium",
            "ZN": "zinc", "FE": "iron"}.get(sym.upper(), sym)
