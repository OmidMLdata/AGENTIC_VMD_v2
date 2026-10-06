"""Accumulate findings across a session and assemble a scientific report.

The report follows the VMD-Agent output contract (system overview, inputs,
components, visualization method, structural + dynamic observations, key
interactions, stability, quantitative results, significance, limitations, next
steps). It clearly separates measured quantities (from analysis) from
agent-supplied visual interpretation (hypotheses).
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional


class Session:
    """A lightweight on-disk store of everything gathered for one system."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        os.makedirs(self.path, exist_ok=True)
        self.file = os.path.join(self.path, "session.json")
        self.data = {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "inspection": None, "detection": None,
                     "recipe": None, "analysis": None, "claims": None,
                     "provenance": None, "renderer": None,
                     "image_interpretations": [], "video_interpretations": [],
                     "figures": []}
        if os.path.exists(self.file):
            try:
                with open(self.file) as fh:
                    self.data.update(json.load(fh))
            except (json.JSONDecodeError, OSError):
                # keep the unreadable file for inspection rather than losing it
                os.replace(self.file, self.file + ".corrupt")

    def update(self, **kw):
        self.data.update(kw)
        self._save()

    def add_figure(self, path, caption=""):
        self.data["figures"].append({"path": path, "caption": caption})
        self._save()

    def add_image_interpretation(self, text, source=""):
        self.data["image_interpretations"].append({"source": source, "text": text})
        self._save()

    def add_video_interpretation(self, text, source=""):
        self.data["video_interpretations"].append({"source": source, "text": text})
        self._save()

    def add_claims(self, result):
        self.data["claims"] = result
        self._save()

    def _save(self):
        # write-then-rename so an interrupted save cannot truncate the session
        tmp = self.file + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.data, fh, indent=2, default=str)
        os.replace(tmp, self.file)


def _g(v) -> str:
    """Format a number, tolerating missing values."""
    try:
        return f"{float(v):.3g}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_summary(s: dict) -> str:
    if not s:
        return "n/a"
    return (f"mean {_g(s.get('mean'))}, sd {_g(s.get('std'))}, "
            f"range [{_g(s.get('min'))}, {_g(s.get('max'))}], "
            f"final {_g(s.get('last'))}")


def assemble_report(session: dict, title: str = "VMD-Agent Analysis Report",
                    out_path: Optional[str] = None) -> dict:
    """Compose a Markdown scientific report from a session dict."""
    insp = session.get("inspection") or {}
    det = session.get("detection") or {}
    rec = session.get("recipe") or {}
    ana = session.get("analysis") or {}
    L = []

    L.append(f"# {title}\n")
    L.append(f"*Generated {time.strftime('%Y-%m-%d %H:%M')} by vmd_agent.*\n")

    # A. System overview
    L.append("## A. System Overview\n")
    stype = det.get("system_type", "unknown")
    L.append(f"- **System type (inferred):** {stype}")
    if det:
        L.append(f"- **Atoms:** {det.get('n_atoms')}, "
                 f"**residues:** {det.get('n_residues')}, "
                 f"**segments:** {det.get('n_segments')}, "
                 f"**frames:** {det.get('n_frames')}")
        if det.get("box"):
            L.append(f"- **Box (a,b,c,α,β,γ):** {det['box']}")
    L.append("")

    # B. Inputs & components
    L.append("## B. Input Files and Detected Components\n")
    if insp.get("files"):
        L.append("| file | role | format |")
        L.append("|---|---|---|")
        for f in insp["files"]:
            L.append(f"| {os.path.basename(f['path'])} | {f['role']} | "
                     f"{f.get('format')} |")
        L.append("")
    if insp.get("missing"):
        L.append("**Missing / issues:**")
        for m in insp["missing"]:
            L.append(f"- {m}")
        L.append("")
    comp = det.get("components", {})
    present = [k for k, v in comp.items() if isinstance(v, dict) and v.get("present")]
    if present:
        L.append("**Molecular components present:** " + ", ".join(present) + "\n")
        for k in present:
            v = comp[k]
            bits = [f"{kk}={vv}" for kk, vv in v.items()
                    if kk not in ("present",) and vv not in ([], "", None)]
            L.append(f"- *{k}*: " + ", ".join(str(b) for b in bits))
        L.append("")

    # C. Visualization method
    L.append("## C. Visualization Method\n")
    if rec:
        L.append(f"- Recipe style: **{rec.get('style')}**, "
                 f"background: {rec.get('background')}")
        for r in rec.get("representations_added", []):
            L.append(f"  - {r}")
        if rec.get("written_to"):
            L.append(f"- Tcl recipe: `{rec['written_to']}`")
    else:
        L.append("- No recipe recorded.")
    L.append("")

    # D. Structural observations (from detection) + visual interpretation
    L.append("## D. Structural Observations\n")
    if det.get("warnings"):
        L.append("**Automated integrity checks:**")
        for w in det["warnings"]:
            L.append(f"- ⚠ {w}")
        L.append("")
    else:
        L.append("- No geometry/integrity warnings raised.\n")
    imgint = session.get("image_interpretations") or []
    if imgint:
        L.append("**Visual interpretation (agent, hypothesis-level):**")
        for it in imgint:
            L.append(f"- ({it.get('source','image')}) {it['text']}")
        L.append("")

    # E. Dynamic behaviour
    L.append("## E. Dynamic Behaviour\n")
    res = ana.get("results", {}) if ana else {}
    if res:
        for name, r in res.items():
            if r.get("error"):
                L.append(f"- **{name}**: not available ({r['error']})")
                continue
            s = r.get("summary", {})
            line = f"- **{name.upper()}**: {_fmt_summary(s)}"
            if r.get("interpretation"):
                line += f" — {r['interpretation']}"
            L.append(line)
        L.append("")
    else:
        L.append("- No trajectory analysis recorded (static structure or "
                 "analysis not run).\n")
    vidint = session.get("video_interpretations") or []
    if vidint:
        L.append("**Video interpretation (agent, hypothesis-level):**")
        for it in vidint:
            L.append(f"- ({it.get('source','video')}) {it['text']}")
        L.append("")

    # F. Key interactions
    L.append("## F. Key Molecular Interactions\n")
    hb = res.get("hbonds"); ct = res.get("contacts")
    if hb and not hb.get("error"):
        L.append(f"- Hydrogen bonds: {_fmt_summary(hb.get('summary', {}))}")
    if ct and not ct.get("error"):
        L.append(f"- Interface contacts (<{ct.get('cutoff')} Å): "
                 f"{_fmt_summary(ct.get('summary', {}))} — "
                 f"{ct.get('interpretation','')}")
    if not (hb or ct):
        L.append("- No interaction analysis run; recommend H-bond/contact/salt-"
                 "bridge analysis (see next steps).")
    L.append("")

    # G. Stability assessment
    L.append("## G. Stability Assessment\n")
    rmsd = res.get("rmsd"); rg = res.get("rgyr")
    verdicts = []
    if rmsd and not rmsd.get("error"):
        verdicts.append(rmsd.get("interpretation", ""))
    if rg and not rg.get("error"):
        verdicts.append(f"radius of gyration indicates {rg.get('interpretation','')}")
    if verdicts:
        for v in verdicts:
            L.append(f"- {v}")
    else:
        L.append("- Insufficient dynamic data for a stability verdict; a single "
                 "structure/image cannot establish stability.")
    L.append("")

    # H. Quantitative results table
    L.append("## H. Quantitative Results\n")
    if res:
        L.append("| metric | mean | sd | min | max | final |")
        L.append("|---|---|---|---|---|---|")
        for name, r in res.items():
            s = r.get("summary", {})
            if s:
                L.append(f"| {name} | {_g(s.get('mean'))} | {_g(s.get('std'))} | "
                         f"{_g(s.get('min'))} | {_g(s.get('max'))} | "
                         f"{_g(s.get('last'))} |")
        L.append("")
    else:
        L.append("- None computed.\n")

    # I. Significance
    L.append("## I. Interpretation & Significance\n")
    L.append(_significance(stype, det, res))
    L.append("")

    # J. Limitations
    L.append("## J. Limitations\n")
    for lim in _limitations(session, det, ana):
        L.append(f"- {lim}")
    L.append("")

    # K. Recommended next analyses
    L.append("## K. Recommended Next Analyses\n")
    for nxt in _next_steps(stype, res):
        L.append(f"- {nxt}")
    L.append("")

    # L. Claim verification
    claims = session.get("claims")
    if claims:
        L.append("## L. Claim Verification\n")
        c = claims.get("counts", {})
        rate = claims.get("contradiction_rate")
        L.append(f"Of {claims.get('n_claims')} statement(s): "
                 f"{c.get('supported', 0)} supported, "
                 f"{c.get('contradicted', 0)} contradicted, "
                 f"{c.get('unverifiable', 0)} unverifiable, "
                 f"{c.get('unparsed', 0)} not checked (unparsed)."
                 + (f" Contradiction rate among checkable claims: "
                    f"{100 * rate:.0f}%." if rate is not None else ""))
        L.append("")
        L.append("| verdict | claim | evidence |")
        L.append("|---|---|---|")
        for r in claims.get("results", []):
            text = (r.get("claim") or {}).get("text") or str(r.get("claim"))
            L.append(f"| {r['verdict']} | {text} | "
                     f"{r.get('explanation', '')} |")
        L.append("")
        L.append(f"*{claims.get('note', '')}*\n")

    # M. Reproducibility
    prov = session.get("provenance")
    rend = session.get("renderer")
    if prov or rend:
        L.append("## M. Reproducibility\n")
        if rend:
            L.append(f"- Renderer: **{rend.get('used')}**")
            for cav in rend.get("caveats", []):
                L.append(f"  - caveat: {cav}")
        if prov:
            L.append(f"- Provenance record: `{prov}` (software versions, "
                     "input hashes, exact Tcl recipe)")
        L.append("")

    # figures (paths relative to the report so the folder can be moved)
    figs = session.get("figures") or []
    plot_figs = [r.get("plot") for r in res.values()
                 if isinstance(r, dict) and r.get("plot")]

    def _rel(path):
        if out_path:
            try:
                return os.path.relpath(path, os.path.dirname(
                    os.path.abspath(out_path)))
            except ValueError:
                pass
        return path

    if figs or plot_figs:
        L.append("## Figures\n")
        for p in plot_figs:
            L.append(f"![{os.path.basename(p)}]({_rel(p)})")
        for f in figs:
            L.append(f"![{f.get('caption','')}]({_rel(f['path'])})")
        L.append("")

    md = "\n".join(L)
    written = None
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w") as fh:
            fh.write(md)
        written = os.path.abspath(out_path)
    return {"markdown": md, "written_to": written}


def _significance(stype, det, res):
    base = {
        "membrane-protein": "Behaviour at the protein–lipid interface and any "
            "channel/pore hydration governs transport and function.",
        "membrane/lipid-bilayer": "Bilayer integrity, area-per-lipid and any "
            "water/ion leakage across the membrane are the key readouts.",
        "protein-ligand complex": "Ligand pose persistence and the specific "
            "contacts maintained indicate binding-mode stability and affinity trends.",
        "protein-protein complex": "Interface contact persistence and buried "
            "surface area reflect complex stability and biological relevance.",
        "protein-nucleic complex": "Protein–nucleic contacts and groove binding "
            "drive recognition specificity.",
        "material/inorganic": "Lattice integrity, defect evolution and surface "
            "adsorption/diffusion characterise material stability and function.",
        "hybrid bio-material": "Biomolecule–surface adsorption geometry and "
            "interfacial water structure control the hybrid interface.",
    }.get(stype, "Global and local structural behaviour over the trajectory "
          "characterises the system's stability and function.")
    return base


def _limitations(session, det, ana):
    out = ["Interpretations from single images/frames are qualitative and cannot "
           "establish stability, binding, or transport on their own.",
           "Automated component/material detection is heuristic (residue-name and "
           "element based) and should be verified for nonstandard systems."]
    if det.get("warnings"):
        out.append("Geometry/integrity warnings above may bias analyses if not "
                   "resolved (missing residues, overlaps).")
    if not (ana and ana.get("results")):
        out.append("No trajectory analysis was performed, so dynamic claims are "
                   "not yet supported by quantitative evidence.")
    else:
        out.append("A 'no detectable drift' verdict means drift was not "
                   "detected in the sampled window; it does not show "
                   "convergence or the absence of slow, unsampled processes.")
        pbc = (ana or {}).get("pbc") or {}
        if pbc.get("warning"):
            out.append("Periodic-boundary warning: " + pbc["warning"])
        thin = [k for k, v in (ana.get("results") or {}).items()
                if isinstance(v, dict) and
                (v.get("stationarity") or {}).get("verdict")
                == "insufficient_data"]
        if thin:
            out.append("Too few independent samples to judge drift for: "
                       + ", ".join(thin) + ".")
        for n in ana.get("notes", []):
            out.append(n)
        for k, v in (ana.get("results") or {}).items():
            if isinstance(v, dict) and v.get("caveat"):
                out.append(f"{k}: {v['caveat']}")
    rend = session.get("renderer") or {}
    for cav in rend.get("caveats", []):
        out.append(f"Renderer ({rend.get('used')}): {cav}")
    return out


def _next_steps(stype, res):
    done = set(res.keys())
    generic = [("rmsd", "RMSD vs. time to assess equilibration and drift."),
               ("rmsf", "Per-residue RMSF to localise flexible regions."),
               ("rgyr", "Radius of gyration for compaction/expansion."),
               ("hbonds", "Hydrogen-bond occupancy over time.")]
    steps = [msg for key, msg in generic if key not in done]
    extra = {
        "membrane-protein": ["Pore-radius profile (HOLE) and water/ion permeation counts.",
                             "Lipid order parameters and membrane thickness."],
        "membrane/lipid-bilayer": ["Area per lipid, order parameters, water flux, "
                             "and ion rejection across the bilayer."],
        "protein-ligand complex": ["Ligand RMSD in the pocket, per-contact occupancy, "
                             "and MM/PBSA-style binding-energy estimate."],
        "protein-protein complex": ["Buried surface area and per-residue interface "
                             "contact maps over time."],
        "material/inorganic": ["Radial distribution functions, defect counting, "
                             "and mean-squared displacement for diffusion."],
    }.get(stype, [])
    return steps + extra
