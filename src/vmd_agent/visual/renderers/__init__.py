"""Drawing backends: the shared interface, the VMD backend, and the registry that picks one.

A backend turns ``(topology, trajectory, frame, detection)`` into PNG files.
Keeping this behind one interface does three things:

* the Docker image can run fully open source (the Matplotlib backend in
  :mod:`vmd_agent.visual.renderers.mpl` needs no VMD), while VMD remains an
  optional, user-supplied backend;
* the benchmark can measure how much a model's accuracy depends on the
  renderer, which is itself a scientific question;
* the legend can never drift from the picture, because each backend reports the
  protein representation it actually draws via :meth:`Renderer.protein_reps`.

``get_renderer("auto")`` returns VMD when a working VMD+Tachyon install exists
and otherwise the dependency-free Matplotlib backend, so every pipeline works
anywhere and says honestly which renderer made the pictures.

VMD itself is **not** bundled with this package. UIUC's license allows
interoperating tools that direct users to download VMD, but not redistributing
it. Install VMD yourself and point ``$VMD_BIN`` (or ``vmd_path``) at it.
"""
from __future__ import annotations

from typing import Optional, Sequence

from vmd_agent.visual import render as _render
from vmd_agent.environment import find_vmd, find_tachyon

NAMES = ("auto", "vmd", "matplotlib")


# ------------------------------------------------------------- the interface
class Renderer:
    """Abstract drawing backend."""

    name = "base"
    #: short description of known visual differences from VMD output
    caveats: Sequence[str] = ()

    def available(self) -> bool:                              # pragma: no cover
        raise NotImplementedError

    def info(self) -> dict:
        return {"name": self.name, "available": self.available(),
                "caveats": list(self.caveats)}

    def protein_reps(self, detection: dict, plddt_coloring: bool = False,
                     focus: str = "overview") -> list:
        """``[(style, colour_method, comment)]`` actually drawn for protein."""
        raise NotImplementedError

    def render_views(self, topology: str, trajectory: Optional[str] = None,
                     frame: int = -1, detection: Optional[dict] = None,
                     recipe_path: Optional[str] = None,
                     views=("front", "side", "top"),
                     out_dir: Optional[str] = None,
                     width: int = 1400, height: int = 1050,
                     background: str = "white", **kw) -> dict:
        raise NotImplementedError

    def render_frames(self, topology: str, trajectory: Optional[str],
                      frames: Sequence[int], detection: Optional[dict] = None,
                      out_dir: Optional[str] = None,
                      width: int = 1280, height: int = 720,
                      background: str = "white", **kw) -> dict:
        raise NotImplementedError


# ------------------------------------------- VMD + Tachyon (reference renderer)
class VMDRenderer(Renderer):
    name = "vmd"
    caveats = ()

    def __init__(self, vmd_path: Optional[str] = None):
        self.vmd_path = vmd_path

    def available(self) -> bool:
        vmd = find_vmd(self.vmd_path)
        return bool(vmd and find_tachyon(vmd))

    def info(self) -> dict:
        vmd = find_vmd(self.vmd_path)
        d = super().info()
        d.update(vmd_path=vmd, tachyon_path=find_tachyon(vmd) if vmd else None)
        return d

    def protein_reps(self, detection, plddt_coloring=False, focus="overview"):
        from vmd_agent.visual.recipes import _auto_protein_reps
        return _auto_protein_reps(detection, plddt_coloring, focus)

    def render_views(self, topology, trajectory=None, frame=-1, detection=None,
                     recipe_path=None, views=("front", "side", "top"),
                     out_dir=None, width=1400, height=1050,
                     background="white", **kw):
        return _render.render_views(
            topology, trajectory, frame=frame, detection=detection,
            recipe_path=recipe_path, views=views, out_dir=out_dir,
            width=width, height=height, background=background,
            vmd_path=self.vmd_path, **kw)

    def render_frames(self, topology, trajectory, frames, detection=None,
                      out_dir=None, width=1280, height=720,
                      background="white", **kw):
        return _render.render_frames(
            topology, trajectory, frames, detection=detection,
            out_dir=out_dir, width=width, height=height,
            background=background, vmd_path=self.vmd_path, **kw)


# Imported after Renderer exists: the Matplotlib backend subclasses it.
from vmd_agent.visual.renderers.mpl import MatplotlibRenderer  # noqa: E402


def get_renderer(name: str = "auto", vmd_path: Optional[str] = None) -> Renderer:
    """Return a renderer instance; ``auto`` prefers VMD, then Matplotlib."""
    name = (name or "auto").lower()
    if name == "vmd":
        return VMDRenderer(vmd_path)
    if name in ("matplotlib", "mpl"):
        return MatplotlibRenderer()
    if name == "auto":
        vmd = VMDRenderer(vmd_path)
        return vmd if vmd.available() else MatplotlibRenderer()
    raise ValueError(f"unknown renderer '{name}'; choose from {NAMES[1:]}")


def list_renderers(vmd_path: Optional[str] = None) -> dict:
    """Availability of every backend, for ``probe_environment``."""
    return {r.name: r.info() for r in (VMDRenderer(vmd_path),
                                       MatplotlibRenderer())}


__all__ = ["Renderer", "VMDRenderer", "MatplotlibRenderer",
           "get_renderer", "list_renderers", "NAMES"]
