"""Read what a person (or a model) meant by a drawing style, a colour, a material, a background or a selection.

People say "red", "cartoon", "CPK colors", "chainA" and "residues 100-150"; VMD wants ``ColorID 1``, ``NewCartoon``, ``Name``, ``chain A``
and ``resid 100 to 150``. Every function here turns the common ways of saying a thing into VMD's own word and returns anything it does not
recognise unchanged, so the strict checks that follow still refuse what is really wrong (with their list of what is allowed).

Pure text in, text out: nothing here runs VMD or writes Tcl, and nothing here loosens the character checks of :mod:`vmd_agent.security`.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# ------------------------------------------------------------------------------------------------ colours
#: VMD's default colour table (id, name, rgb), used for colour names and for the nearest colour to a hex code
VMD_COLORS = (
    (0, "blue", (0.0, 0.0, 1.0)), (1, "red", (1.0, 0.0, 0.0)), (2, "gray", (0.35, 0.35, 0.35)), (3, "orange", (1.0, 0.5, 0.0)),
    (4, "yellow", (1.0, 1.0, 0.0)), (5, "tan", (0.5, 0.5, 0.2)), (6, "silver", (0.6, 0.6, 0.6)), (7, "green", (0.0, 1.0, 0.0)),
    (8, "white", (1.0, 1.0, 1.0)), (9, "pink", (1.0, 0.6, 0.6)), (10, "cyan", (0.25, 0.75, 0.75)), (11, "purple", (0.65, 0.0, 0.65)),
    (12, "lime", (0.5, 0.9, 0.4)), (13, "mauve", (0.9, 0.4, 0.7)), (14, "ochre", (0.5, 0.3, 0.0)), (15, "iceblue", (0.5, 0.5, 0.75)),
    (16, "black", (0.0, 0.0, 0.0)), (25, "violet", (0.65, 0.4, 1.0)), (27, "magenta", (1.0, 0.0, 1.0)),
)
_COLOR_ID = {name: cid for cid, name, _ in VMD_COLORS}
_COLOR_ID.update({"grey": 2, "brown": 14, "gold": 4, "navy": 0, "teal": 10, "aqua": 10, "light blue": 15, "lightblue": 15, "dark gray": 2,
                  "dark grey": 2, "light gray": 6, "light grey": 6})

#: colouring methods, by the ways people ask for them
_METHODS = {
    "name": "Name", "atom name": "Name", "cpk": "Name", "cpk colors": "Name", "cpk colours": "Name", "by atom": "Name", "atom": "Name",
    "element": "Element", "by element": "Element", "elements": "Element", "atom type": "Type", "type": "Type",
    "resname": "ResName", "residue name": "ResName", "by residue": "ResName", "residue": "ResName", "amino acid": "ResName",
    "restype": "ResType", "residue type": "ResType", "polarity": "ResType", "resid": "ResID", "residue number": "ResID",
    "chain": "Chain", "by chain": "Chain", "chains": "Chain", "chainid": "Chain", "segname": "SegName", "segment": "SegName",
    "structure": "Structure", "secondary structure": "Structure", "ss": "Structure", "by secondary structure": "Structure",
    "molecule": "Molecule", "beta": "Beta", "b-factor": "Beta", "bfactor": "Beta", "b factor": "Beta", "temperature factor": "Beta",
    "plddt": "Beta", "occupancy": "Occupancy", "mass": "Mass", "charge": "Charge", "index": "Index", "backbone": "Backbone",
    "fragment": "Fragment", "position": "Position",
}


def _key(value: Any) -> str:
    return re.sub(r"[\s_]+", " ", str(value).strip().lower())


def nearest_color_id(hex_code: str) -> Optional[int]:
    """The VMD colour id closest to a ``#rrggbb`` (or ``#rgb``) code."""
    h = hex_code.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", h):
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    rgb = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return min(VMD_COLORS, key=lambda c: sum((a - b) ** 2 for a, b in zip(c[2], rgb)))[0]


def color(value: Any, methods=("Name", "Type", "Element", "ResName", "ResType", "ResID", "Chain", "SegName", "Structure", "Molecule",
                               "Beta", "Occupancy", "Mass", "Charge", "Index", "Backbone", "Fragment", "Position")) -> Any:
    """A colouring method or a solid colour, as VMD names it: 'red' -> 'ColorID 1', 'CPK' -> 'Name', 'secondary structure' -> 'Structure',
    '#ff0000' -> 'ColorID 1', 3 -> 'ColorID 3'. Anything else comes back unchanged."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)) and float(value).is_integer():
        return f"ColorID {int(value)}"
    text = str(value).strip()
    for m in methods:
        if text.lower() == m.lower():
            return m
    m = re.fullmatch(r"(?i)(?:color\s*id|colorid|colour\s*id|color|colour|id)?\s*(\d{1,4})", text)
    if m:
        return f"ColorID {int(m.group(1))}"
    if text.startswith("#"):
        cid = nearest_color_id(text)
        return f"ColorID {cid}" if cid is not None else value
    k = _key(text)
    for cand in (k, re.sub(r"^colou?r(ed)?( by)? ", "", k), re.sub(r"^(colou?r(ed)? )?by ", "", k), k.rstrip("s")):
        if cand in _COLOR_ID:
            return f"ColorID {_COLOR_ID[cand]}"
        if cand in _METHODS and _METHODS[cand] in methods:
            return _METHODS[cand]
    return value


def background(value: Any, allowed=("black", "white")) -> Any:
    """A background colour VMD accepts: names in any case ('Grey' -> gray, 'navy' -> blue when blue is allowed), and a hex code that is
    close to an allowed colour ('#ffffff' -> white). A colour that is not allowed is returned unchanged, to be refused, rather than swapped
    for a different one."""
    if value is None:
        return value
    text = str(value).strip()
    low = re.sub(r"\s+", " ", text.lower()).replace("grey", "gray")
    if low in allowed:
        return low
    names = {i: name for i, name, _ in VMD_COLORS}
    if low in _COLOR_ID:
        name = names.get(_COLOR_ID[low])
        return name if name in allowed else value
    if text.startswith("#"):
        h = text.lstrip("#")
        h = "".join(c * 2 for c in h) if re.fullmatch(r"[0-9a-fA-F]{3}", h) else h
        if re.fullmatch(r"[0-9a-fA-F]{6}", h):
            rgb = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
            near = [(sum((a - b) ** 2 for a, b in zip(c, rgb)), name) for _, name, c in VMD_COLORS if name in allowed]
            if near:
                dist, name = min(near)
                if dist <= 0.1:                          # close enough to be the same colour
                    return name
    return value


# ------------------------------------------------------------------------------------------------ styles and materials
_STYLES = {
    "cartoon": "NewCartoon", "cartoons": "NewCartoon", "new cartoon": "NewCartoon", "ribbon": "NewRibbons", "ribbons": "NewRibbons",
    "new ribbons": "NewRibbons", "stick": "Licorice", "sticks": "Licorice", "licorice": "Licorice", "liquorice": "Licorice",
    "ball and stick": "CPK", "ball-and-stick": "CPK", "balls and sticks": "CPK", "ball & stick": "CPK", "cpk": "CPK",
    "spacefill": "VDW", "space fill": "VDW", "space-filling": "VDW", "spacefilling": "VDW", "sphere": "VDW", "spheres": "VDW",
    "vdw": "VDW", "van der waals": "VDW", "surface": "QuickSurf", "surfaces": "QuickSurf", "quick surface": "QuickSurf",
    "quicksurf": "QuickSurf", "molecular surface": "QuickSurf", "line": "Lines", "lines": "Lines", "wire": "Lines", "wireframe": "Lines",
    "tube": "Tube", "tubes": "Tube", "trace": "Trace", "backbone trace": "Trace", "bead": "Beads", "beads": "Beads", "point": "Points",
    "points": "Points", "dots": "Dotted", "hydrogen bonds": "HBonds", "h-bonds": "HBonds", "hbonds": "HBonds", "isosurface": "Isosurface",
}


def choice(value: Any, allowed, aliases: Optional[dict] = None) -> Any:
    """``value`` as spelled in ``allowed`` (any case, spaces or underscores), or through ``aliases``; unchanged when nothing fits."""
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip()
    if text in allowed:                                  # already VMD's own word
        return text
    if aliases:
        k = re.sub(r"[\s_]+", " ", text.lower())
        hit = aliases.get(k) or aliases.get(k.rstrip("s"))
        if hit in allowed:
            return hit
    squash = re.sub(r"[\s_\-]+", "", text.lower())
    for a in allowed:
        if squash == re.sub(r"[\s_\-]+", "", a.lower()):
            return a
    return value


def style(value: Any, allowed) -> Any:
    """A drawing style: 'cartoon' -> NewCartoon, 'sticks' -> Licorice, 'ball and stick' -> CPK, 'surface' -> QuickSurf, ..."""
    return choice(value, allowed, _STYLES)


_MATERIALS = {"glass": "Glass1", "metal": "BrushedMetal", "metallic": "BrushedMetal", "shiny": "Glossy", "plastic": "HardPlastic",
              "see through": "Transparent", "see-through": "Transparent", "solid": "Opaque", "matte": "Diffuse"}


def material(value: Any, allowed) -> Any:
    return choice(value, allowed, _MATERIALS)


def projection(value: Any) -> Any:
    return choice(value, ("Orthographic", "Perspective"), {"ortho": "Orthographic", "orthogonal": "Orthographic", "persp": "Perspective"})


# ------------------------------------------------------------------------------------------------ selections
#: anything that is not protein, nucleic acid or water: the ligands, cofactors and ions
LIGAND = "not (protein or nucleic or water)"
#: the protein residues with an atom within 5 A of a ligand
POCKET = f"protein and same residue as within 5 of ({LIGAND})"
_NAMED = {
    "everything": "all", "all atoms": "all", "the whole thing": "all", "whole system": "all", "the protein": "protein",
    "whole protein": "protein", "proteins": "protein", "ligand": LIGAND, "ligands": LIGAND, "the ligand": LIGAND, "small molecules": LIGAND,
    "heteroatoms": LIGAND, "het": LIGAND, "hetatm": LIGAND, "binding pocket": POCKET, "the binding pocket": POCKET, "pocket": POCKET,
    "binding site": POCKET, "the binding site": POCKET, "active site": POCKET, "waters": "water", "solvent": "water",
    "dna": "nucleic", "rna": "nucleic", "nucleic acid": "nucleic", "nucleic acids": "nucleic", "alpha carbons": "name CA",
    "c-alpha": "name CA", "calpha": "name CA", "ca atoms": "name CA", "side chains": "sidechain", "sidechains": "sidechain",
}
_PHRASE = re.compile(r"\b(?:the\s+)?(binding pocket|binding site|active site|ligands?|pocket)\b", re.I)


def selection(value: Any) -> Any:
    """A VMD selection from the usual ways of writing one: 'chainA' -> 'chain A', 'residues 100-150' -> 'resid 100 to 150', 'protein chain A'
    -> 'protein and chain A', and the words 'ligand' and 'binding pocket' (protein residues within 5 A of a ligand). Text already in VMD's
    language passes unchanged."""
    if value is None:
        return value
    if re.search(r"[^\S ]|[{}\[\];$\\\"]", str(value)):  # a newline, tab or Tcl character: leave it for the security check to refuse as it is
        return value
    text = re.sub(r" +", " ", str(value).strip())
    whole = text.lower().rstrip(".")
    if whole in _NAMED:
        return _NAMED[whole]
    t = re.sub(r"\b(?i:chain)[_\-]?([A-Z0-9])\b", r"chain \1", text)                                        # chainA, chain_A
    t = re.sub(r"(?i)\b(?:resids?|residues?|res|residue numbers?)\s+(-?\d+)\s*(?:-|–|—|\.\.|:)\s*(-?\d+)\b", r"resid \1 to \2", t)  # 100-150
    t = re.sub(r"(?i)\b(?:residues?|res|residue numbers?)\s+(-?\d+)\s+(?:to|through|thru)\s+(-?\d+)\b", r"resid \1 to \2", t)  # people mean resid
    t = re.sub(r"(?i)\b(?:residues|res)\s+(?=-?\d)", "resid ", t)                                             # residues 5 7 9
    t = re.sub(r"(?i)\b(protein|nucleic|water|backbone|sidechain|all)\s+(?=(chain|resid|resname|name|segname|index)\b)", r"\1 and ", t)
    t = _PHRASE.sub(lambda m: "(" + (POCKET if "ligand" not in m.group(1).lower() else LIGAND) + ")", t) if not re.search(r"\bresname\b", t, re.I) else t
    return t


# ------------------------------------------------------------------------------------------------ file arguments
_PLACEHOLDER = re.compile(r"(?i)^\s*(<[^>]*>|\{[^}]*\}|\[[^\]]*\]|none|null|nil|n/?a|undefined|optional|\.|-|your[_ ]\w+.*|path/to/.*)\s*$")
#: words a model writes instead of a file name ('topology', 'structure.pdb'). They are placeholders only where a file is expected:
#: 'Structure' is also VMD's own colouring method (by secondary structure), and must reach VMD when it is given as a colour.
_FILE_WORD = re.compile(r"(?i)^\s*(topology|trajectory|structure|file|filename|map|map_file)(\.\w+)?\s*$")
_FILE_PARAM = re.compile(r"(?i)(^|_)(topology|trajectory|file|files|path|dir|pdb|psf|dcd|xtc|mp4|png|map|video|spec)($|_)|^out_")


def is_file_parameter(name: Optional[str]) -> bool:
    """Whether a tool parameter of this name takes a file or folder (topology, trajectory, map_file, out_png, session_dir ...)."""
    return bool(name) and bool(_FILE_PARAM.search(str(name)))


def is_placeholder(value: Any, param: Optional[str] = None) -> bool:
    """A value a model put in place of 'not given': '', '<your_topology>', 'None', 'path/to/file.pdb', and, for a parameter that takes
    a file (or when no parameter is named), a bare word such as 'topology' or 'structure'."""
    if not isinstance(value, str):
        return False
    if not value.strip() or _PLACEHOLDER.match(value):
        return True
    return bool(_FILE_WORD.match(value)) and (param is None or is_file_parameter(param))
