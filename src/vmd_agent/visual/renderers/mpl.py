"""Pure-Python renderer: no VMD, no ray tracer, no display.

This exists so the toolkit (and its Docker image and CI) can produce real
molecular figures with only open-source dependencies, and so the benchmark can
compare renderers. It is *not* a replacement for Tachyon-quality figures.

What it draws, using VMD's own palette so the visual legend stays true:

* protein / nucleic backbone as a coloured trace through CA (or P), coloured by
  DSSP secondary structure, by chain, or by B-factor (pLDDT for AlphaFold);
* ligands and lipids as sticks (bonds inferred from covalent radii) in element
  colours, with VMD's cyan carbon;
* ions and inorganic atoms as spheres; water only on request.

Known differences from VMD output are listed in :attr:`MatplotlibRenderer.caveats`
and returned with every render so an agent can state them.
"""
from __future__ import annotations

import os
import tempfile
from typing import Dict, List, Optional

import numpy as np

from vmd_agent.visual.renderers import Renderer

_DPI = 100

# VMD colour for each DSSP code (matches colorkey.STRUCTURE_COLORS)
_SS_HEX = {"H": "#a000ff", "G": "#0000ff", "I": "#ff0000", "E": "#ffff00",
           "B": "#d2b48c", "T": "#00ffff", "S": "#ffffff", "-": "#ffffff",
           "?": "#ffffff"}
_HALO = "#3a3a3a"


def _rx(a):
    c, s = np.cos(np.radians(a)), np.sin(np.radians(a))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a):
    c, s = np.cos(np.radians(a)), np.sin(np.radians(a))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


# Mirrors render._VIEW_ROT: VMD applies the listed screen rotations in order.
_VIEW_MAT = {
    "front": np.eye(3),
    "side": _ry(90),
    "top": _rx(90),
    "iso": _ry(-30) @ _rx(30),
}


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _plddt_hex(b: float) -> str:
    if b > 90:
        return "#0000ff"
    if b > 70:
        return "#00ffff"
    if b > 50:
        return "#ffff00"
    return "#ff0000"


def _check_size(width, height):
    """Error text for an unusable image size, else ``None``."""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return f"width and height must be integers, got {width!r} x {height!r}"
    if not (1 <= w <= 20000 and 1 <= h <= 20000):
        return f"image size must be 1..20000 pixels per side, got {w} x {h}"
    return None


class _Scene:
    """Topology-level drawing plan; coordinates are supplied per frame."""

    def __init__(self, u, detection: dict, plddt: bool, show_water: bool):
        from vmd_agent.visual.colorkey import ELEMENT_COLORS, chain_colors
        from vmd_agent.structure.stats import _elements, _infer_bonds
        self.u = u
        self.plddt = plddt
        comp = detection.get("components", {})
        sels = detection.get("suggested_selections", {})
        chains = comp.get("protein", {}).get("chains", []) or []
        self.chain_hex = {c["label"].replace("chain ", ""): c["hex"]
                          for c in chain_colors(chains)}

        def elem_hex(sym):
            return ELEMENT_COLORS.get(str(sym).upper(), ("gray", "#808080"))[1]
        self._elem_hex = elem_hex

        # --- backbone traces (one per chain) --------------------------------
        self.traces: List[dict] = []
        self.sticks = []     # (atom_i, atom_j, hex_i, hex_j, lw_scale, layer)
        self.spheres = []    # (atom_idx array, hex array, size_scale)
        if "protein" in sels:
            ca = u.select_atoms(f"({sels['protein']}) and name CA")
            self._add_traces(ca, kind="protein")
        if "nucleic" in sels:
            nuc = u.select_atoms(f"({sels['nucleic']}) and (name P or name \"C4'\")")
            self._add_traces(nuc, kind="nucleic")

        # --- sticks: ligands + lipids ---------------------------------------
        for key, lw in (("ligand", 1.0), ("lipid", 0.45)):
            if key not in sels:
                continue
            ag = u.select_atoms(sels[key])
            if not len(ag) or len(ag) > 60000:
                continue
            el = _elements(ag)
            pairs, _ = _infer_bonds(ag, el, None, max_atoms=60000)
            hexes = np.array([elem_hex(e) for e in el])
            idx = ag.indices
            if pairs is not None and len(pairs):
                for a, b in pairs:
                    self.sticks.append((idx[a], idx[b], hexes[a], hexes[b], lw))
            # isolated atoms (no bond) still need to appear
            bonded = set(pairs.ravel().tolist()) if pairs is not None \
                and len(pairs) else set()
            lone = [i for i in range(len(ag)) if i not in bonded]
            if lone:
                self.spheres.append((idx[lone], hexes[lone], 0.7))

        # --- spheres: ions, material, optional water -------------------------
        if "ions" in sels:
            ag = u.select_atoms(sels["ions"])
            if len(ag):
                el = _elements(ag)
                self.spheres.append((ag.indices,
                                     np.array([elem_hex(e) for e in el]), 1.6))
        if comp.get("material_inorganic", {}).get("present"):
            ag = u.select_atoms("not (protein or nucleic or water)")
            if len(ag):
                el = _elements(ag)
                self.spheres.append((ag.indices,
                                     np.array([elem_hex(e) for e in el]), 1.0))
        self.water_idx = None
        if show_water and "water" in sels:
            w = u.select_atoms("name OW O* and (" + sels["water"] + ")")
            if len(w):
                self.water_idx = w.indices

        drawn = []
        for t in self.traces:
            drawn.append(t["idx"])
        for a, b, *_ in self.sticks[:50000]:
            drawn.append(np.array([a, b]))
        for idx, _h, _s in self.spheres:
            drawn.append(np.asarray(idx))
        self.drawn_idx = (np.unique(np.concatenate(drawn))
                          if drawn else np.arange(len(u.atoms)))

    def _add_traces(self, ag, kind):
        if not len(ag):
            return
        labels = []
        try:
            cid = ag.chainIDs
            labels = [str(c).strip() or str(s) for c, s in zip(cid, ag.segids)]
        except Exception:
            labels = [str(s) for s in ag.segids]
        groups: Dict[str, List[int]] = {}
        for i, lab in enumerate(labels):
            groups.setdefault(lab, []).append(i)
        for lab, ii in groups.items():
            self.traces.append({"kind": kind, "chain": lab,
                                "idx": ag.indices[ii],
                                "resid": ag.resids[ii],
                                "bfac": (np.asarray(ag.tempfactors)[ii]
                                         if hasattr(ag, "tempfactors") else None)})

    # ---------------------------------------------------------------- colours
    def trace_colors(self, tr, color_method: str, ss_codes: Optional[dict]):
        n = len(tr["idx"])
        if tr["kind"] == "nucleic":
            return [self._elem_hex("P")] * n
        if color_method == "Beta" and tr["bfac"] is not None:
            return [_plddt_hex(b) if self.plddt else self._bfac_hex(b)
                    for b in tr["bfac"]]
        if color_method == "Chain":
            return [self.chain_hex.get(tr["chain"], "#808080")] * n
        # Structure
        if ss_codes is None:
            return ["#ffffff"] * n
        return [_SS_HEX.get(ss_codes.get(int(r), "-"), "#ffffff")
                for r in tr["resid"]]

    @staticmethod
    def _bfac_hex(b):
        # low -> blue, mid -> white, high -> red (colorkey.beta_key, crystal)
        return "#0000ff" if b < 20 else ("#ffffff" if b < 50 else "#ff0000")


class MatplotlibRenderer(Renderer):
    name = "matplotlib"
    caveats = (
        "Backbone is drawn as a coloured trace through CA atoms (like a Tube), "
        "not as ribbons or arrows; helix and sheet appear as colours only.",
        "Painter's-algorithm drawing with no depth buffer: ligands and ions are "
        "drawn on top of the backbone, so occlusion by protein is not shown.",
        "No ray-traced shading, shadows or ambient occlusion.",
        "Surface, pocket and performance focus modes are not supported; a "
        "backbone trace is drawn instead.",
    )

    def available(self) -> bool:
        try:
            import matplotlib  # noqa: F401
            return True
        except Exception:                                  # pragma: no cover
            return False

    # ------------------------------------------------------------------ reps
    def protein_reps(self, detection, plddt_coloring=False, focus="overview"):
        p = detection.get("components", {}).get("protein", {})
        n_chains = len(p.get("chains", []) or [])
        if plddt_coloring:
            return [("Tube", "Beta",
                     "Backbone trace coloured by AlphaFold pLDDT confidence "
                     "from the B-factor column.")]
        if n_chains >= 2:
            return [("Tube", "Chain",
                     f"Backbone trace, one colour per chain ({n_chains} "
                     "chains).")]
        return [("Tube", "Structure",
                 "Backbone trace coloured by DSSP secondary structure.")]

    # --------------------------------------------------------------- drawing
    def _geometry(self, scene: _Scene, pos: np.ndarray, R: np.ndarray,
                  center: np.ndarray):
        return (pos - center) @ R.T

    def _draw(self, scene, pos, view, out_png, width, height, background,
              camera, color_method, ss_codes, title=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection

        center, radius = camera
        R = _VIEW_MAT.get(view, np.eye(3))
        P = self._geometry(scene, pos, R, center)
        bg = "#ffffff" if background == "white" else "#000000"
        fig = plt.figure(figsize=(width / _DPI, height / _DPI), dpi=_DPI,
                         facecolor=bg)
        ax = fig.add_axes([0, 0, 1, 1], facecolor=bg)
        asp = width / height
        ax.set_xlim(-radius * max(asp, 1), radius * max(asp, 1))
        ax.set_ylim(-radius * max(1 / asp, 1), radius * max(1 / asp, 1))
        ax.set_aspect("equal")
        ax.axis("off")
        k = height / 1050.0

        def segs(a, b):
            return np.stack([P[a][:, :2], P[b][:, :2]], axis=1)

        # water (faint)
        if scene.water_idx is not None:
            w = P[scene.water_idx]
            ax.scatter(w[:, 0], w[:, 1], s=2 * k, c="#b0b0ff", linewidths=0,
                       zorder=1)

        # lipid / ligand sticks
        if scene.sticks:
            a = np.array([s[0] for s in scene.sticks])
            b = np.array([s[1] for s in scene.sticks])
            ha = [s[2] for s in scene.sticks]
            hb = [s[3] for s in scene.sticks]
            lw = np.array([s[4] for s in scene.sticks])
            mid = (P[a] + P[b]) / 2
            depth = mid[:, 2]
            order = np.argsort(depth)
            half1 = np.stack([P[a][:, :2], mid[:, :2]], axis=1)
            half2 = np.stack([mid[:, :2], P[b][:, :2]], axis=1)
            for lc_segs in (half1, half2):
                ax.add_collection(LineCollection(
                    lc_segs[order], colors=_HALO,
                    linewidths=(4.2 * k * lw)[order] + 1.4, zorder=3,
                    capstyle="round"))
            for lc_segs, cols in ((half1, ha), (half2, hb)):
                ax.add_collection(LineCollection(
                    lc_segs[order], colors=[cols[i] for i in order],
                    linewidths=(4.2 * k * lw)[order], zorder=4,
                    capstyle="round"))

        # backbone traces
        for tr in scene.traces:
            idx = tr["idx"]
            if len(idx) < 2:
                continue
            cols = scene.trace_colors(tr, color_method, ss_codes)
            pts3 = pos[idx]
            gap = np.linalg.norm(pts3[1:] - pts3[:-1], axis=1)
            ok = gap < (8.0 if tr["kind"] == "nucleic" else 4.6)
            a, b = idx[:-1][ok], idx[1:][ok]
            if not len(a):
                continue
            cs = [cols[i] for i in np.where(ok)[0]]
            mid = (P[a] + P[b]) / 2
            order = np.argsort(mid[:, 2])
            sg = segs(a, b)[order]
            ax.add_collection(LineCollection(
                sg, colors=_HALO, linewidths=7.5 * k + 1.6, zorder=2,
                capstyle="round"))
            ax.add_collection(LineCollection(
                sg, colors=[cs[i] for i in order], linewidths=7.5 * k,
                zorder=2.1, capstyle="round"))

        # spheres (ions, lone atoms, material)
        for idx, hexes, scale in scene.spheres:
            q = P[np.asarray(idx)]
            order = np.argsort(q[:, 2])
            size = ((scale * 9.0 * k) ** 2)
            ax.scatter(q[order, 0], q[order, 1], s=size,
                       c=[hexes[i] for i in order], edgecolors=_HALO,
                       linewidths=0.8, zorder=5)
        if title:
            ax.text(0.01, 0.99, title, transform=ax.transAxes, va="top",
                    fontsize=9 * k + 4,
                    color="#202020" if background == "white" else "#e0e0e0")
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        fig.savefig(out_png, dpi=_DPI, facecolor=bg)
        plt.close(fig)
        return out_png

    # ------------------------------------------------------------- interface
    def _prepare(self, topology, trajectory, detection, plddt, show_water):
        from vmd_agent.inputs.molio import load_universe
        from vmd_agent.structure.detect import detect_system
        det = detection or detect_system(topology, trajectory)
        if det.get("error"):
            raise ValueError(det["error"])
        u = load_universe(topology, trajectory)
        return u, det, _Scene(u, det, plddt, show_water)

    @staticmethod
    def _camera(scene, u):
        pos = u.atoms.positions[scene.drawn_idx]
        pos = pos[np.isfinite(pos).all(axis=1)]       # NaN/Inf atoms are skipped
        if not len(pos):
            raise ValueError("no atom has finite coordinates; nothing to draw")
        center = pos.mean(axis=0)
        radius = float(np.linalg.norm(pos - center, axis=1).max()) * 1.08 or 1.0
        return center, radius

    @staticmethod
    def _ss_for_frame(u, scene, color_method):
        if color_method != "Structure":
            return None
        from vmd_agent.structure.dssp import assign_dssp
        try:
            res = assign_dssp(u.select_atoms("protein"))
            return {int(r): c for r, c in zip(res["resids"], res["codes"])}
        except Exception:
            return None

    def _render_views(self, topology, trajectory=None, frame=-1, detection=None,
                     recipe_path=None, views=("front", "side", "top"),
                     out_dir=None, width=1400, height=1050,
                     background="white", show_water=False,
                     plddt_coloring=False, focus="overview", **_ignored):
        try:
            u, det, scene = self._prepare(topology, trajectory, detection,
                                          plddt_coloring, show_water)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        reps = self.protein_reps(det, plddt_coloring, focus)
        color_method = reps[0][1] if reps else "Structure"
        u.trajectory[frame if frame >= 0 else len(u.trajectory) - 1]
        pos = u.atoms.positions.copy()
        ss = self._ss_for_frame(u, scene, color_method)
        camera = self._camera(scene, u)
        out_dir = os.path.abspath(out_dir or tempfile.mkdtemp(prefix="mpl_views_"))
        bad = _check_size(width, height)
        if bad:
            return {"ok": False, "error": bad, "renderer": self.name}
        ignored = [v for v in views if v not in _VIEW_MAT]
        views = [v for v in views if v in _VIEW_MAT] or ["front"]
        images = {}
        for v in views:
            png = os.path.join(out_dir, f"{v}.png")
            self._draw(scene, pos, v, png, width, height, background, camera,
                       color_method, ss)
            images[v] = png
        out = {"ok": True, "images": images, "out_dir": out_dir,
               "renderer": self.name, "caveats": list(self.caveats)}
        if ignored or not images:
            out["ignored_views"] = ignored
            out["view_note"] = (f"unknown view(s) {ignored} ignored; valid "
                                f"views are {sorted(_VIEW_MAT)}; drew 'front' "
                                "because no valid view was requested")
        if focus not in ("overview", "fold", "interactions"):
            out["focus_note"] = (f"focus='{focus}' is not supported by the "
                                 "matplotlib backend; drew the backbone trace.")
        return out

    def _render_frames(self, topology, trajectory, frames, detection=None,
                      out_dir=None, name_fmt="frame_{k:05d}.png",
                      view="front", width=1280, height=720,
                      background="white", show_water=False,
                      plddt_coloring=False, focus="overview", **_ignored):
        try:
            u, det, scene = self._prepare(topology, trajectory, detection,
                                          plddt_coloring, show_water)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        reps = self.protein_reps(det, plddt_coloring, focus)
        color_method = reps[0][1] if reps else "Structure"
        bad = _check_size(width, height)
        if bad:
            return {"ok": False, "error": bad, "renderer": self.name}
        out_dir = os.path.abspath(out_dir or tempfile.mkdtemp(prefix="mpl_frames_"))
        n = len(u.trajectory)
        requested = [int(f) for f in frames]
        dropped = [f for f in requested if not 0 <= f < n]
        frames = [f for f in requested if 0 <= f < n]
        if not frames:
            return {"ok": False, "error": "no valid frames requested."}
        u.trajectory[frames[0]]
        camera = self._camera(scene, u)           # fixed camera for all frames
        images = []
        for k, f in enumerate(frames):
            u.trajectory[f]
            ss = self._ss_for_frame(u, scene, color_method)
            png = os.path.join(out_dir, name_fmt.format(k=k, frame=f))
            self._draw(scene, u.atoms.positions.copy(), view, png, width,
                       height, background, camera, color_method, ss)
            images.append({"k": k, "frame": f, "path": png})
        return {"ok": True, "images": images, "out_dir": out_dir,
                "n_requested": len(requested), "n_rendered": len(images),
                "frames_failed": dropped, "renderer": self.name,
                "caveats": list(self.caveats)}

    # Public entry points: drawing must never raise (the toolkit's contract is
    # a result dict), whatever the structure contains.
    def render_views(self, *args, **kwargs):
        try:
            return self._render_views(*args, **kwargs)
        except Exception as e:                        # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}",
                    "renderer": self.name}

    def render_frames(self, *args, **kwargs):
        try:
            return self._render_frames(*args, **kwargs)
        except Exception as e:                        # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}",
                    "renderer": self.name}
