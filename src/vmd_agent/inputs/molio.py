"""Load molecular systems, including mmCIF which MDAnalysis cannot read.

``fetch_structure`` falls back to mmCIF for entries too large for the legacy PDB
format (ribosomes, capsids). MDAnalysis has no mmCIF parser, so without this
module those downloads could be fetched but never analysed. :func:`load_universe`
is the single entry point every analysis module uses to build a ``Universe``.

Only the first model and the first alternate location of each atom are read.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterator, List, Optional

import numpy as np

_CIF_EXT = {".cif", ".mmcif"}

# one CIF token: a quoted string (quote closes only before whitespace/EOL) or a
# bare word. Atom names such as O5' rely on that quoting rule.
_TOKEN = re.compile(r"""'(?:[^']|'(?!\s|$))*'|"(?:[^"]|"(?!\s|$))*"|\S+""")


def is_cif(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _CIF_EXT


def _tokens(line: str) -> List[str]:
    out = []
    for m in _TOKEN.finditer(line):
        t = m.group(0)
        if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
            t = t[1:-1]
        out.append(t)
    return out


def _atom_site_rows(path: str) -> Iterator[Dict[str, str]]:
    """Yield one dict per ``_atom_site`` row, keyed by the column suffix."""
    with open(path, "r", errors="replace") as fh:
        lines = iter(fh)
        stack: List[str] = []

        def nxt() -> Optional[str]:
            return stack.pop() if stack else next(lines, None)

        while True:
            raw = nxt()
            if raw is None:
                return
            if not raw.strip().startswith("loop_"):
                continue
            headers: List[str] = []
            first = None
            while True:
                raw = nxt()
                if raw is None:
                    return
                if raw.strip().startswith("_"):
                    headers.append(raw.strip().split()[0])
                else:
                    first = raw
                    break
            is_atoms = (headers and all(h.startswith("_atom_site.")
                                        for h in headers)
                        and "_atom_site.Cartn_x" in headers)
            if not is_atoms:
                stack.append(first)       # may itself be the next loop_
                continue
            cols = [h.split(".", 1)[1] for h in headers]
            pending: List[str] = []
            raw = first
            while raw is not None:
                s = raw.strip()
                if (not s or s.startswith("#") or s.startswith("loop_")
                        or s.startswith("_") or s.startswith("data_")):
                    return
                pending += _tokens(raw)
                while len(pending) >= len(cols):
                    row, pending = pending[:len(cols)], pending[len(cols):]
                    yield dict(zip(cols, row))
                raw = nxt()
            return


def read_mmcif(path: str):
    """Parse an mmCIF file into an MDAnalysis ``Universe`` (model 1 only)."""
    import MDAnalysis as mda

    rows = []
    first_model = None
    for r in _atom_site_rows(path):
        model = r.get("pdbx_PDB_model_num", "1")
        if first_model is None:
            first_model = model
        if model != first_model:
            break
        alt = r.get("label_alt_id", ".")
        if alt not in (".", "?", "A", "1"):
            continue
        rows.append(r)
    if not rows:
        raise ValueError(f"no _atom_site records found in {path}")

    n = len(rows)
    xyz = np.empty((n, 3), dtype=np.float32)
    names, elements, resnames, chains = [], [], [], []
    resids, bfac, rec = [], [], []
    for i, r in enumerate(rows):
        xyz[i] = (float(r["Cartn_x"]), float(r["Cartn_y"]), float(r["Cartn_z"]))
        names.append(r.get("auth_atom_id") or r.get("label_atom_id", "X"))
        elements.append((r.get("type_symbol") or "X").upper())
        resnames.append(r.get("auth_comp_id") or r.get("label_comp_id", "UNK"))
        chains.append(r.get("auth_asym_id") or r.get("label_asym_id", "A"))
        sid = r.get("auth_seq_id") or r.get("label_seq_id") or "0"
        try:
            resids.append(int(sid))
        except ValueError:
            resids.append(0)
        try:
            bfac.append(float(r.get("B_iso_or_equiv", 0.0)))
        except ValueError:
            bfac.append(0.0)
        rec.append(r.get("group_PDB", "ATOM"))

    # residues are contiguous runs of (chain, resid, resname, insertion code)
    res_index = np.empty(n, dtype=int)
    res_chain, res_id, res_name = [], [], []
    prev = None
    for i in range(n):
        icode = rows[i].get("pdbx_PDB_ins_code", "?")
        key = (chains[i], resids[i], resnames[i], icode)
        if key != prev:
            res_chain.append(chains[i]); res_id.append(resids[i])
            res_name.append(resnames[i])
            prev = key
        res_index[i] = len(res_chain) - 1

    seg_names: List[str] = []
    res_seg = []
    for c in res_chain:
        if c not in seg_names:
            seg_names.append(c)
        res_seg.append(seg_names.index(c))

    u = mda.Universe.empty(n_atoms=n, n_residues=len(res_chain),
                           n_segments=len(seg_names),
                           atom_resindex=res_index,
                           residue_segindex=np.array(res_seg),
                           trajectory=True)
    u.add_TopologyAttr("names", names)
    u.add_TopologyAttr("types", elements)
    u.add_TopologyAttr("elements", elements)
    u.add_TopologyAttr("resnames", res_name)
    u.add_TopologyAttr("resids", res_id)
    u.add_TopologyAttr("segids", seg_names)
    u.add_TopologyAttr("chainIDs", [chains[i] for i in range(n)])
    u.add_TopologyAttr("tempfactors", bfac)
    u.add_TopologyAttr("record_types", rec)
    u.atoms.positions = xyz
    return u


def load_universe(topology: str, trajectory: Optional[str] = None):
    """Build a ``Universe`` from any supported topology (+ trajectory).

    mmCIF topologies are read natively; everything else goes through
    MDAnalysis. A trajectory cannot be attached to an mmCIF topology by
    MDAnalysis, so for that combination the coordinates of the CIF are kept and
    the trajectory is loaded on top of them.
    """
    import MDAnalysis as mda

    if is_cif(topology):
        u = read_mmcif(topology)
        if trajectory:
            u.load_new(trajectory)
        return u
    return mda.Universe(topology, trajectory) if trajectory \
        else mda.Universe(topology)
