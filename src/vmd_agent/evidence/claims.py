"""Verify an agent's statements about a system against measurements.

The toolkit already separates measured results from agent-written
interpretation in the report, but nothing *checked* the interpretation against
the data. This module closes that loop: each factual claim is routed to the
measurement that can settle it and labelled

``supported``       the data agree with the claim
``contradicted``    the data disagree
``unverifiable``    the data cannot settle it (too little sampling, missing
                    trajectory, or a property no measurement here covers)
``unparsed``        free text that does not match the supported vocabulary

Claims may be structured dicts (preferred, exact) or plain sentences matched
by a small set of templates (:func:`parse_claim_text`). A sentence the parser
does not recognise is reported as ``unparsed``, never guessed at: the layer
fails closed so it cannot hand out false assurance.

Verification here is only as good as the measurement behind it; every verdict
carries its evidence and the criterion used.

Structured claim types
----------------------
``n_chains`` {value}                    ``has_component`` {component, present}
``system_type`` {value}                 ``n_residues`` {value, tol}
``secondary_structure`` {kind, op, value}   kind: helix | sheet | coil
``n_disulfides`` {value}                ``ligand_buried`` {min_fraction}
``rmsd_stable``                         ``rg_change`` {direction}
``contact_persists`` {sel1, sel2, cutoff, min_fraction}
``signal_change`` {signal, direction, start_frame, end_frame}
"""
from __future__ import annotations

import operator
import re
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

SUPPORTED, CONTRADICTED = "supported", "contradicted"
UNVERIFIABLE, UNPARSED = "unverifiable", "unparsed"

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt,
        "<=": operator.le, "==": operator.eq, "~": None}

# Bondi van der Waals radii (Å) for burial calculations
_VDW = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80,
        "F": 1.47, "CL": 1.75, "BR": 1.85, "I": 1.98, "NA": 2.27, "MG": 1.73,
        "K": 2.75, "CA": 2.31, "ZN": 1.39, "FE": 1.40}

_COMPONENT_ALIASES = {
    "protein": "protein", "peptide": "protein", "nucleic": "nucleic",
    "dna": "nucleic", "rna": "nucleic", "nucleic acid": "nucleic",
    "lipid": "lipid", "membrane": "lipid", "bilayer": "lipid",
    "water": "water", "solvent": "water", "ion": "ions", "ions": "ions",
    "ligand": "ligands_or_other", "ligands": "ligands_or_other",
    "cofactor": "ligands_or_other", "inhibitor": "ligands_or_other",
    "material": "material_inorganic", "surface": "material_inorganic",
}


def _result(claim, verdict, explanation, evidence=None, criterion=None):
    r = {"claim": claim, "verdict": verdict, "explanation": explanation}
    if evidence is not None:
        r["evidence"] = evidence
    if criterion:
        r["criterion"] = criterion
    return r


# --------------------------------------------------------------- parsing
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "single": 1, "a": 1}


def _to_int(tok: str) -> Optional[int]:
    tok = tok.lower()
    if tok.isdigit():
        return int(tok)
    return _NUM.get(tok)


MAX_CLAIM_CHARS = 400

_NUMWORDS = set(_NUM) | {"zero", "no", "single"}
_BASE = {"a", "an", "the", "is", "are", "it", "its", "this", "that", "there",
         "has", "have", "contains", "contain", "containing", "with", "without",
         "no", "not", "protein", "structure", "system", "complex", "model"}
_COMPONENT_WORDS = {w for alias in _COMPONENT_ALIASES for w in alias.split()}


def _forms(*words):
    out = set()
    for w in words:
        out.add(w)
        out.add(w + "s")
    return out


# Words each claim type can fully account for. Anything else in the sentence
# is a qualifier the measurement does not check ("near the loop", "between
# residues 40 and 60", "intact", "for 40 ns"), so the sentence is not parsed
# rather than being reduced to a weaker claim and reported as supported.
_ALLOWED = {
    "has_component": _BASE | _COMPONENT_WORDS | _forms(
        "present", "exist", "molecule", "component", "lipid", "ion",
        "ligand", "cofactor", "inhibitor", "chain", "atom") | _forms("membrane"),
    "secondary_structure": _BASE | _forms(
        "mostly", "predominantly", "largely", "mainly", "dominated", "rich",
        "helical", "helix", "helice", "alpha", "beta", "sheet", "strand",
        "content", "secondary", "lack", "absent", "mixed", "regular", "all",
        "α", "β") | {"helices"},
    "ligand_buried": _BASE | _forms(
        "buried", "bound", "pocket", "cleft", "inside", "within", "in",
        "occupy", "occupies", "ligand", "inhibitor", "cofactor", "substrate",
        "heme", "drug", "binding", "site"),
    "rmsd_stable": _BASE | {
        "stable", "equilibrated", "equilibrium", "plateau", "plateaus", "drift",
        "drifts", "drifting", "converged", "remains", "remain", "stays",
        "stay", "structurally", "over", "time", "simulation", "run",
        "trajectory", "during", "throughout", "and", "does", "do"},
    "rg_change": _BASE | {
        "compacts", "compact", "compaction", "collapses", "collapse", "shrinks",
        "shrink", "expands", "expand", "expansion", "unfolds", "unfold",
        "swells", "over", "time", "during", "simulation", "run", "trajectory",
        "throughout"},
    "contact_persists": _BASE | {
        "stays", "stay", "remains", "remain", "bound", "in", "contact",
        "attached", "associated", "persistent", "stable", "binding",
        "interface", "throughout", "during", "simulation", "run",
        "trajectory", "to", "over", "time", "ligand", "whole", "entire"},
    "n_chains": _BASE | _NUMWORDS | _forms(
        "chain", "monomer", "dimer", "tetramer", "monomeric", "dimeric",
        "tetrameric", "consist", "of", "composed", "made", "up", "single",
        "subunit"),
    "n_disulfides": _BASE | _NUMWORDS | _forms(
        "disulfide", "bond", "bridge", "cystine", "cysteine"),
}


def _scope_note(claim: dict, text: str) -> Optional[str]:
    """Words in ``text`` the claim type cannot account for, or ``None``."""
    allowed = _ALLOWED.get(claim.get("type"))
    if allowed is None:
        return None
    words = re.findall(r"[A-Za-z0-9α-ωÅ%µ']+", text)
    left = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in allowed:
            continue
        if lw.isdigit() and claim.get("type") in ("n_chains", "n_disulfides"):
            continue                          # the count itself
        if i == 0 and w[0].isupper():        # subject name: "Lysozyme has ..."
            continue
        left.append(w)
    if claim["type"] == "has_component":
        kinds = {c for a, c in _COMPONENT_ALIASES.items()
                 if re.search(rf"\b{re.escape(a)}s?\b", text.lower())}
        if len(kinds - {"protein"}) > 1 or (
                "protein" in kinds and len(kinds) > 2):
            # "protein" is usually just the subject ("the protein has a
            # ligand"); two *other* components make the claim ambiguous.
            left.append("(several components in one sentence)")
    return ", ".join(left[:6]) if left else None


def parse_claim_text(text: str) -> dict:
    """Map a plain sentence onto a structured claim, or ``{"type": None}``.

    Fails closed: a sentence longer than ``MAX_CLAIM_CHARS``, or one that says
    more than the matched claim type can check, is returned unparsed with a
    ``note`` saying why.
    """
    t = text.strip()
    if len(t) > MAX_CLAIM_CHARS:
        return {"text": t[:MAX_CLAIM_CHARS], "type": None,
                "note": f"sentence longer than {MAX_CLAIM_CHARS} characters"}
    claim = _parse_raw(t)
    if claim.get("type"):
        extra = _scope_note(claim, t)
        if extra:
            return {"text": t, "type": None,
                    "note": "the sentence says more than can be checked "
                            f"(unaccounted words: {extra})"}
    return claim


def _parse_raw(text: str) -> dict:
    t = text.strip()
    low = t.lower()
    base = {"text": t}

    m = re.search(r"\b(\w+)\s+(?:protein\s+)?chains?\b", low)
    if m and _to_int(m.group(1)) is not None and "disulfide" not in low:
        return {**base, "type": "n_chains", "value": _to_int(m.group(1))}
    if re.search(r"\bmonomer(ic)?\b|\bsingle[- ]chain\b", low):
        return {**base, "type": "n_chains", "value": 1}
    if re.search(r"\bdimer(ic)?\b", low):
        return {**base, "type": "n_chains", "value": 2}
    if re.search(r"\btetramer(ic)?\b", low):
        return {**base, "type": "n_chains", "value": 4}

    m = re.search(r"(\w+)\s+disulfide", low)
    if m and _to_int(m.group(1)) is not None:
        return {**base, "type": "n_disulfides", "value": _to_int(m.group(1))}
    if re.search(r"\bno disulfide", low):
        return {**base, "type": "n_disulfides", "value": 0}

    if re.search(r"buried|bound (?:in|within)|inside the (?:pocket|cleft)|"
                 r"occupies? (?:a|the) (?:pocket|cleft)|in a pocket", low) \
            and re.search(r"ligand|inhibitor|cofactor|substrate|heme|drug", low):
        return {**base, "type": "ligand_buried", "min_fraction": 0.5}

    if re.search(r"\b(stays?|remains?|stay|remain)\b.*\b(bound|in contact|"
                 r"attached|associated)\b|persistent contact|stable (?:binding|"
                 r"interface)", low):
        return {**base, "type": "contact_persists"}

    if re.search(r"\b(compact(s|ed|ion)?|collaps\w*|shrink\w*)\b", low):
        return {**base, "type": "rg_change", "direction": "compaction"}
    if re.search(r"\b(expand\w*|unfold\w*|swell\w*|extend\w* conformation)\b",
                 low):
        return {**base, "type": "rg_change", "direction": "expansion"}
    if re.search(r"\b(stable|equilibrated|equilibrium|plateau\w*|"
                 r"not drift\w*|no drift|converged)\b", low):
        return {**base, "type": "rmsd_stable"}

    for kind, pat in (("helix", r"helic|helix|helices"),
                      ("sheet", r"sheet|strand|beta|β")):
        if re.search(pat, low):
            if re.search(r"mostly|predominantly|largely|mainly|dominated|"
                         r"all[- ]|rich", low):
                return {**base, "type": "secondary_structure", "kind": kind,
                        "op": "majority"}
            if re.search(r"\bno\b|lack|without|absent", low):
                return {**base, "type": "secondary_structure", "kind": kind,
                        "op": "<", "value": 5.0}
            return {**base, "type": "secondary_structure", "kind": kind,
                    "op": ">", "value": 10.0}
    if re.search(r"mixed\s+(?:α|alpha)\s*/?\s*(?:β|beta)|alpha/beta|α/β", low):
        return {**base, "type": "secondary_structure", "kind": "mixed",
                "op": "mixed"}

    neg = bool(re.search(r"\b(no|without|lacks?|absent|not contain|does not "
                         r"(?:have|contain))\b", low))
    # The claimed component is the *object* of the sentence: in "the protein
    # has no ligand" the subject is the protein but the claim is about the
    # ligand. Search after the first containing/binding verb when there is one.
    verb = re.search(r"\b(contains?|has|have|includes?|including|with|without|"
                     r"lacks?|no|binds?|bound to|hosts?|embedded in|"
                     r"surrounded by|in complex with|carries)\b", low)
    segment = low[verb.end():] if verb else low
    best = None
    for alias, comp in _COMPONENT_ALIASES.items():
        m = re.search(rf"\b{re.escape(alias)}s?\b", segment)
        if m and (best is None or m.start() < best[0]
                  or (m.start() == best[0] and len(alias) > len(best[2]))):
            best = (m.start(), comp, alias)
    if best:
        return {**base, "type": "has_component", "component": best[1],
                "present": not neg}
    return {**base, "type": None}


def normalise(claim: Union[str, dict]) -> dict:
    if isinstance(claim, str):
        return parse_claim_text(claim)
    if not isinstance(claim, dict):
        return {"text": repr(claim)[:MAX_CLAIM_CHARS], "type": None,
                "note": "a claim must be a sentence or a dict, "
                        f"not {type(claim).__name__}"}
    c = dict(claim)
    c.setdefault("text", str(claim))
    return c


# --------------------------------------------------------------- measurement
def _sasa(coords: np.ndarray, radii: np.ndarray, env_coords=None,
          env_radii=None, probe: float = 1.4, n_points: int = 240) -> float:
    """Total Shrake-Rupley SASA (Å²) of ``coords``, optionally shielded by env."""
    from scipy.spatial import cKDTree
    n = len(coords)
    if not n:
        return 0.0
    k = np.arange(n_points) + 0.5
    phi = np.arccos(1 - 2 * k / n_points)
    theta = np.pi * (1 + 5 ** 0.5) * k
    unit = np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi),
                     np.cos(phi)], axis=1)
    if env_coords is not None and len(env_coords):
        allc = np.vstack([coords, env_coords])
        allr = np.concatenate([radii, env_radii])
    else:
        allc, allr = coords, radii
    tree = cKDTree(allc)
    rmax = float(allr.max()) + probe
    total = 0.0
    for i in range(n):
        ri = radii[i] + probe
        pts = coords[i] + ri * unit
        nb = [j for j in tree.query_ball_point(coords[i], ri + rmax) if j != i]
        if nb:
            d = np.linalg.norm(pts[:, None, :] - allc[nb][None, :, :], axis=2)
            buried = np.any(d < (allr[nb] + probe)[None, :], axis=1)
            frac = 1.0 - buried.mean()
        else:
            frac = 1.0
        total += frac * 4 * np.pi * ri ** 2
    return float(total)


def burial_fraction(ligand_ag, env_ag) -> dict:
    """Fraction of a ligand's isolated SASA that is occluded by its environment."""
    from vmd_agent.structure.stats import _elements

    def radii(ag):
        return np.array([_VDW.get(e, 1.7) for e in _elements(ag)])

    lig_xyz, lig_r = ligand_ag.positions, radii(ligand_ag)
    alone = _sasa(lig_xyz, lig_r)
    # only environment atoms near the ligand can occlude it
    from scipy.spatial import cKDTree
    env_xyz = env_ag.positions
    tree = cKDTree(env_xyz)
    near = sorted({j for p in lig_xyz for j in tree.query_ball_point(p, 10.0)})
    env = env_ag[near] if near else env_ag[[]]
    in_complex = _sasa(lig_xyz, lig_r, env.positions,
                       radii(env) if len(env) else None)
    frac = 1.0 - in_complex / alone if alone > 0 else 0.0
    return {"sasa_isolated": alone, "sasa_in_complex": in_complex,
            "buried_fraction": float(max(0.0, min(1.0, frac)))}


# ------------------------------------------------------------- verification
class _Evidence:
    """Lazily computed measurements shared across claims."""

    def __init__(self, topology: str, trajectory: Optional[str], frame: int,
                 step: int):
        self.topology, self.trajectory = topology, trajectory
        self.frame, self.step = frame, step
        self._cache: Dict[str, object] = {}

    def get(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    @property
    def detection(self):
        from vmd_agent.structure.detect import detect_system
        return self.get("det", lambda: detect_system(self.topology,
                                                     self.trajectory))

    @property
    def stats(self):
        from vmd_agent.structure.stats import structure_stats
        return self.get("stats", lambda: structure_stats(
            self.topology, self.trajectory, frame=max(self.frame, 0)))

    def analysis(self, which: Sequence[str], **kw):
        from vmd_agent.dynamics.analysis import analyze_trajectory
        key = "an:" + ",".join(sorted(which)) + repr(sorted(kw.items()))
        return self.get(key, lambda: analyze_trajectory(
            self.topology, self.trajectory, analyses=list(which),
            step=self.step, **kw))

    def universe(self):
        from vmd_agent.inputs.molio import load_universe
        def load():
            u = load_universe(self.topology, self.trajectory)
            if self.trajectory:
                u.trajectory[self.frame if self.frame >= 0
                             else len(u.trajectory) - 1]
            return u
        return self.get("u", load)


def _secondary_structure_verdict(c: dict, ss: dict) -> dict:
    """Decide a secondary-structure claim from measured DSSP fractions.

    A pure function of the claim and the percentages (``helix_percent``,
    ``sheet_percent``, ``coil_percent``), so the thresholds can be tested at
    their boundaries without loading a structure."""
    if ss.get("helix_percent") is None:
        return _result(c, UNVERIFIABLE,
                       "secondary structure could not be assigned.", ss)
    h, e, co = ss["helix_percent"], ss["sheet_percent"], ss["coil_percent"]
    ev_ = {"helix_percent": h, "sheet_percent": e, "coil_percent": co,
           "source": ss.get("source")}
    kind, op = c.get("kind"), c.get("op", ">")
    if op == "mixed":
        ok = h >= 15 and e >= 15
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"helix {h}% and sheet {e}% (mixed needs both >= "
                       "15%).", ev_, "DSSP fractions")
    val = {"helix": h, "sheet": e, "coil": co}.get(kind)
    if val is None:
        return _result(c, UNVERIFIABLE, f"unknown kind '{kind}'.")
    if op == "majority":
        # Coil is the remainder, not a competing fold class, so "mostly
        # helical" means helix dominates the *regular* structure and is a
        # substantial part of the chain.
        other = e if kind == "helix" else h
        ok = val >= 30.0 and val > other
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"{kind} is {val}% (helix {h}, sheet {e}, coil "
                       f"{co}); 'mostly {kind}' requires >= 30% and more "
                       f"than the other regular class ({other}%).", ev_,
                       "DSSP fractions; coil excluded from the comparison")
    fn = _OPS.get(op)
    ok = fn(val, float(c["value"])) if fn else False
    return _result(c, SUPPORTED if ok else CONTRADICTED,
                   f"{kind} content is {val}%; claim requires {op} "
                   f"{c['value']}%.", ev_, "DSSP fractions")


def _verify_one(c: dict, ev: _Evidence) -> dict:
    t = c.get("type")
    if t is None:
        return _result(c, UNPARSED,
                       (c.get("note") or "Sentence is outside the supported "
                        "claim vocabulary") + "; restate it as a structured "
                       "claim or check it by hand.")
    det = ev.detection
    if det.get("error"):
        return _result(c, UNVERIFIABLE, f"system could not be loaded: "
                       f"{det['error']}")
    comp = det.get("components", {})

    if t == "n_chains":
        chains = comp.get("protein", {}).get("chains", [])
        n = len(chains) or (1 if comp.get("protein", {}).get("present") else 0)
        ok = n == int(c["value"])
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"{n} protein chain(s) detected (chains {chains}); "
                       f"claim says {c['value']}.",
                       {"detected_chains": chains, "n_chains": n},
                       "count of distinct protein chain / segment IDs")

    if t == "has_component":
        key = c["component"]
        key = _COMPONENT_ALIASES.get(key, key)
        present = bool(comp.get(key, {}).get("present"))
        want = bool(c.get("present", True))
        return _result(c, SUPPORTED if present == want else CONTRADICTED,
                       f"{key} is {'present' if present else 'absent'} in the "
                       f"detected composition; claim expects "
                       f"{'present' if want else 'absent'}.",
                       {key: comp.get(key)},
                       "residue-name based component detection")

    if t == "system_type":
        got = det.get("system_type", "")
        ok = str(c["value"]).lower() in got.lower()
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"detected system type is '{got}'.",
                       {"system_type": got})

    if t == "n_residues":
        n = det.get("n_residues")
        tol = int(c.get("tol", 0))
        ok = n is not None and abs(n - int(c["value"])) <= tol
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"{n} residues counted (all components).",
                       {"n_residues": n})

    if t == "n_disulfides":
        got = ev.stats.get("n_disulfide_bridges")
        if got is None:
            return _result(c, UNVERIFIABLE, "no disulfide count available.")
        ok = got == int(c["value"])
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"{got} disulfide bridge(s) (SG-SG < 2.5 Å).",
                       {"n_disulfides": got, "pairs":
                        ev.stats.get("disulfide_pairs")})

    if t == "secondary_structure":
        return _secondary_structure_verdict(
            c, ev.stats.get("secondary_structure") or {})

    if t == "ligand_buried":
        sel = det.get("suggested_selections", {})
        if "ligand" not in sel or "protein" not in sel:
            return _result(c, UNVERIFIABLE,
                           "no ligand and protein pair detected.")
        u = ev.universe()
        lig = u.select_atoms(c.get("selection") or sel["ligand"])
        env = u.select_atoms("protein")
        lig = lig.select_atoms("not name H*")
        if not len(lig):
            return _result(c, UNVERIFIABLE, "ligand selection is empty.")
        b = burial_fraction(lig, env)
        thr = float(c.get("min_fraction", 0.5))
        ok = b["buried_fraction"] >= thr
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"{100 * b['buried_fraction']:.0f}% of the ligand's "
                       f"solvent-accessible surface is occluded by protein "
                       f"(threshold {100 * thr:.0f}%).", b,
                       "Shrake-Rupley SASA, probe 1.4 Å, ligand alone vs in "
                       "complex")

    # ---- dynamics: need a trajectory -------------------------------------
    if t in ("rmsd_stable", "rg_change", "contact_persists", "signal_change"):
        if not ev.trajectory:
            return _result(c, UNVERIFIABLE, "this claim concerns dynamics, "
                           "but no trajectory was supplied.")

    if t == "rmsd_stable":
        r = ev.analysis(["rmsd"], selection=c.get("selection", "protein"))
        res = r.get("results", {}).get("rmsd", {})
        st = res.get("stationarity") or {}
        v = st.get("verdict")
        if res.get("error") or v is None:
            return _result(c, UNVERIFIABLE, res.get("error", "no RMSD"))
        if v == "no_detectable_drift":
            return _result(c, SUPPORTED, st["reason"], st,
                           "Mann-Kendall trend + half-vs-half test")
        if v == "drifting":
            return _result(c, CONTRADICTED, st["reason"], st,
                           "Mann-Kendall trend + half-vs-half test")
        return _result(c, UNVERIFIABLE, st.get("reason", v), st)

    if t == "rg_change":
        r = ev.analysis(["rgyr"], selection=c.get("selection", "protein"))
        res = r.get("results", {}).get("rgyr", {})
        end = res.get("start_vs_end") or {}
        if res.get("error") or end.get("significant") is None:
            return _result(c, UNVERIFIABLE, res.get("error",
                           "too few frames to compare start and end."))
        d = c.get("direction", "compaction")
        actual = ("none" if not end["significant"]
                  else "compaction" if end["diff"] < 0 else "expansion")
        ok = actual == d
        return _result(c, SUPPORTED if ok else CONTRADICTED,
                       f"start-vs-end Rg change is {end['diff']:+.2f} Å "
                       f"(z={end['z']:.1f}, {actual}); claim says {d}.", end,
                       "start/end window comparison, |z| > 3")

    if t == "contact_persists":
        sel = det.get("suggested_selections", {})
        s1 = c.get("sel1") or sel.get("ligand")
        s2 = c.get("sel2") or sel.get("protein")
        if not (s1 and s2):
            return _result(c, UNVERIFIABLE, "no two selections to compare.")
        r = ev.analysis(["contacts"], selection=s1, sel2=s2,
                        cutoff=float(c.get("cutoff", 4.5)))
        res = r.get("results", {}).get("contacts", {})
        if res.get("error"):
            return _result(c, UNVERIFIABLE, res["error"])
        frac = res.get("fraction_frames_in_contact", 0.0)
        thr = float(c.get("min_fraction", 0.9))
        return _result(c, SUPPORTED if frac >= thr else CONTRADICTED,
                       f"contact present in {100 * frac:.0f}% of frames "
                       f"(needs >= {100 * thr:.0f}%).",
                       {"fraction_frames_in_contact": frac,
                        "stationarity": res.get("stationarity")},
                       "fraction of analysed frames with any atom pair "
                       "within the cutoff")

    if t == "signal_change":
        from vmd_agent.dynamics.keyframes import trajectory_signals
        try:
            sig = trajectory_signals(
                ev.topology, ev.trajectory,
                selection=c.get("selection", "protein"), sel2=c.get("sel2"),
                step=ev.step)
        except Exception as e:
            return _result(c, UNVERIFIABLE, f"{type(e).__name__}: {e}")
        name = c.get("signal", "rmsd")
        if name not in sig["signals"]:
            return _result(c, UNVERIFIABLE,
                           f"signal '{name}' unavailable (have "
                           f"{sorted(sig['signals'])}).")
        fr = np.asarray(sig["frames"])
        x = sig["signals"][name]
        s, e = int(c["start_frame"]), int(c["end_frame"])
        before = x[fr <= s]
        after = x[fr >= e]
        if len(before) < 3 or len(after) < 3:
            return _result(c, UNVERIFIABLE,
                           "too few frames before/after the stated window.")
        from vmd_agent.dynamics import timeseries as tsm
        a, b = tsm.mean_ci(before), tsm.mean_ci(after)
        diff = b["mean"] - a["mean"]
        se = float(np.hypot(a["sem"], b["sem"]))
        z = diff / se if se > 0 else float("inf")
        want = c.get("direction", "increase")
        actual = ("none" if abs(z) < 3 else
                  "increase" if diff > 0 else "decrease")
        return _result(c, SUPPORTED if actual == want else CONTRADICTED,
                       f"{name} changes by {diff:+.3g} between the frames "
                       f"before {s} and after {e} (z={z:.1f}, {actual}).",
                       {"before": a["mean"], "after": b["mean"], "z": z})

    return _result(c, UNPARSED, f"unknown claim type '{t}'.")


def verify_claims(topology: str, claims: Sequence[Union[str, dict]],
                  trajectory: Optional[str] = None, frame: int = 0,
                  step: int = 1) -> dict:
    """Check each claim against measurements and summarise.

    ``contradiction_rate`` is contradicted / (supported + contradicted): the
    share of *checkable* claims the data refuted. Unverifiable and unparsed
    claims are reported separately and never counted as support.
    """
    ev = _Evidence(topology, trajectory, frame, step)
    results: List[dict] = []
    for raw in claims:
        c = normalise(raw)
        try:
            results.append(_verify_one(c, ev))
        except Exception as e:                              # fail closed
            results.append(_result(c, UNVERIFIABLE,
                                   f"verifier error: {type(e).__name__}: {e}"))
    counts = {k: sum(r["verdict"] == k for r in results)
              for k in (SUPPORTED, CONTRADICTED, UNVERIFIABLE, UNPARSED)}
    checkable = counts[SUPPORTED] + counts[CONTRADICTED]
    return {
        "n_claims": len(results), "counts": counts,
        "contradiction_rate": (counts[CONTRADICTED] / checkable
                               if checkable else None),
        "results": results,
        "note": "supported means the measurement agrees with the claim under "
                "the stated criterion, not that the claim is true in general. "
                "Unverifiable/unparsed claims received no check.",
    }
