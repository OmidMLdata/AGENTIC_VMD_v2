"""The tools that drive VMD itself: its measure commands, plugins, system building, density maps,
scenes and session export. Registered in the same :data:`vmd_agent.toolset.TOOLS` as every other tool,
so the chat, the CLI wrappers and the MCP server all get them.

Every tool needs a real VMD, builds its Tcl from validated values (a caller never supplies Tcl), and,
where it ran a script, saves a standalone copy next to the data (``vmd_scripts/``) and returns its path
as ``reproduce_script``: open it in VMD to repeat exactly what the tool did.
"""
from __future__ import annotations

import os
from typing import Optional

from vmd_agent import security
from vmd_agent.toolset import _p, tool
from vmd_agent.vmdkit import build, capabilities, interactions, measure as measure_mod
from vmd_agent.vmdkit import scene, script, structure, volumetric
from vmd_agent.vmdkit import trajectory as traj_mod


def _script_dir() -> str:
    roots = security.allowed_roots()
    return os.path.join(roots[0] if roots else os.getcwd(), "vmd_scripts")


def _run(name: str, fn, **kw) -> dict:
    """Call a kit function, keeping a standalone copy of the Tcl it ran."""
    script.configure(_script_dir(), name)
    try:
        out = fn(**kw)
    finally:
        saved = script.last_script()
        script.configure(None)
    if isinstance(out, dict) and saved:
        out["reproduce_script"] = saved
        out["reproduce_with"] = f'vmd -dispdev text -eofexit -e "{saved}" < /dev/null'
    return out


@tool()
def vmd_capabilities(vmd_path: Optional[str] = None, verbose: bool = False) -> dict:
    """List the plugins of the installed VMD by status: wrapped by this toolkit (with the tool that does it), library,
    window-only, needing another program (NAMD, APBS, ...), or not wrapped yet. verbose=true adds every plugin's
    version and the file formats."""
    return capabilities.vmd_capabilities(_p(vmd_path), verbose=verbose)


@tool()
def vmd_measure(topology: str, trajectory: Optional[str] = None, kind: str = "rgyr", selection: str = "protein",
                selection2: Optional[str] = None, selection3: Optional[str] = None, selection4: Optional[str] = None,
                first: int = 0, last: int = -1, step: int = 1, reference_frame: int = 0, align: bool = True,
                mass_weighted: bool = True, probe_radius: float = 1.4, cutoff: float = 3.0,
                angle_cutoff: float = 20.0, delta: float = 0.1, rmax: float = 10.0, num_clusters: int = 3,
                vmd_path: Optional[str] = None) -> dict:
    """Run one of VMD's own `measure` computations over a trajectory. kind: rgyr, sasa, center, minmax, inertia,
    rmsd (fit to reference_frame when align), rmsf, distance (selection to selection2), angle (3 single atoms),
    dihedral (4 single atoms), contacts, hbonds, gofr (selection2 around selection) or cluster (frames by RMSD).
    Returns per-frame values and a summary."""
    return _run("vmd_measure", measure_mod.measure, topology=_p(topology), trajectory=_p(trajectory), kind=kind,
                selection=selection, selection2=selection2, selection3=selection3, selection4=selection4,
                first=first, last=last, step=step, reference_frame=reference_frame, align=align,
                mass_weighted=mass_weighted, probe_radius=probe_radius, cutoff=cutoff, angle_cutoff=angle_cutoff,
                delta=delta, rmax=rmax, num_clusters=num_clusters, vmd_path=_p(vmd_path))


@tool()
def vmd_interactions(topology: str, trajectory: Optional[str] = None, kind: str = "hbonds",
                     selection: str = "protein", selection2: Optional[str] = None, cutoff: float = 0.0,
                     angle_cutoff: float = 20.0, first: int = 0, last: int = -1, step: int = 1, top: int = 15,
                     vmd_path: Optional[str] = None) -> dict:
    """Hydrogen bonds, salt bridges or atom contacts between selections over a trajectory, as persistence:
    which pairs exist and in what fraction of frames. kind: hbonds (default cutoff 3.0 A), salt_bridges (4.0 A),
    contacts (4.0 A, needs selection2)."""
    return _run("vmd_interactions", interactions.interactions, topology=_p(topology), trajectory=_p(trajectory),
                kind=kind, selection=selection, selection2=selection2, cutoff=cutoff, angle_cutoff=angle_cutoff,
                first=first, last=last, step=step, top=top, vmd_path=_p(vmd_path))


@tool()
def vmd_secondary_structure(topology: str, trajectory: Optional[str] = None, selection: str = "protein",
                            first: int = 0, last: int = -1, step: int = 1, vmd_path: Optional[str] = None) -> dict:
    """Secondary structure of every residue in every frame, computed by VMD (STRIDE): helix/strand fractions
    per frame and per-residue persistence (what VMD's Timeline window shows)."""
    return _run("vmd_secondary_structure", structure.secondary_structure, topology=_p(topology),
                trajectory=_p(trajectory), selection=selection, first=first, last=last, step=step, vmd_path=_p(vmd_path))


@tool()
def vmd_backbone_torsions(topology: str, trajectory: Optional[str] = None, selection: str = "protein", frame: int = 0,
                          vmd_path: Optional[str] = None) -> dict:
    """phi/psi angles of one frame from VMD, classified into coarse Ramachandran regions; lists outlier residues."""
    return _run("vmd_backbone_torsions", structure.backbone_torsions, topology=_p(topology), trajectory=_p(trajectory),
                selection=selection, frame=frame, vmd_path=_p(vmd_path))


@tool()
def vmd_structure_check(topology: str, trajectory: Optional[str] = None, selection: str = "protein", frame: int = 0,
                        vmd_path: Optional[str] = None) -> dict:
    """VMD's structurecheck plugin on one frame: chirality errors, cis peptide bonds and chain gaps."""
    return _run("vmd_structure_check", structure.structure_check, topology=_p(topology), trajectory=_p(trajectory),
                selection=selection, frame=frame, vmd_path=_p(vmd_path))


@tool()
def vmd_align_structures(mobile: str, reference: str, mobile_selection: str = "name CA",
                         reference_selection: Optional[str] = None, out_pdb: Optional[str] = None,
                         vmd_path: Optional[str] = None) -> dict:
    """Superpose one structure onto another with VMD and report the RMSD before and after; optionally write the
    moved structure. Both selections must contain the same number of atoms."""
    return _run("vmd_align_structures", structure.align_structures, mobile=_p(mobile), reference=_p(reference),
                mobile_selection=mobile_selection, reference_selection=reference_selection, out_pdb=_p(out_pdb),
                vmd_path=_p(vmd_path))


@tool()
def vmd_pbc_info(topology: str, trajectory: Optional[str] = None, first: int = 0, last: int = -1, step: int = 1,
                 vmd_path: Optional[str] = None) -> dict:
    """Unit-cell lengths and angles per frame (VMD pbctools): is there a periodic box, is it orthorhombic,
    does its volume drift (a sign of an unequilibrated or wrongly-read run)."""
    return _run("vmd_pbc_info", traj_mod.pbc_info, topology=_p(topology), trajectory=_p(trajectory), first=first,
                last=last, step=step, vmd_path=_p(vmd_path))


@tool()
def vmd_convert_trajectory(topology: str, trajectory: Optional[str], out_path: str, fmt: Optional[str] = None,
                           selection: str = "all", first: int = 0, last: int = -1, step: int = 1, wrap: bool = False,
                           center_selection: Optional[str] = None, align: bool = False,
                           align_selection: str = "name CA", vmd_path: Optional[str] = None) -> dict:
    """Write a (sub)trajectory in another format, choosing atoms (selection), frames (first/last/step), optionally
    wrapping atoms into the unit cell around center_selection and/or fitting every frame to the first.
    Formats VMD can write: dcd xyz pdb crd binpos gro mol2 trr namdbin (not xtc or netcdf)."""
    return _run("vmd_convert_trajectory", traj_mod.convert, topology=_p(topology), trajectory=_p(trajectory),
                out_path=_p(out_path), fmt=fmt, selection=selection, first=first, last=last, step=step, wrap=wrap,
                center_selection=center_selection, align=align, align_selection=align_selection, vmd_path=_p(vmd_path))


@tool()
def vmd_write_structure(topology: str, trajectory: Optional[str], out_path: str, fmt: Optional[str] = None,
                        selection: str = "all", frame: int = 0, vmd_path: Optional[str] = None) -> dict:
    """Write one frame of a selection as pdb, psf, xyz, gro, mol2 or namdbin."""
    return _run("vmd_write_structure", traj_mod.write_structure, topology=_p(topology), trajectory=_p(trajectory),
                out_path=_p(out_path), fmt=fmt, selection=selection, frame=frame, vmd_path=_p(vmd_path))


@tool()
def vmd_volmap(topology: str, trajectory: Optional[str], out_dx: str, kind: str = "density",
               selection: str = "protein", resolution: float = 1.0, mass_weighted: bool = True, first: int = 0,
               last: int = -1, step: int = 1, cutoff: float = 2.0, vmd_path: Optional[str] = None) -> dict:
    """Compute a 3-D map with VMD volmap and write it as OpenDX. kind: density, occupancy, distance, mask, or
    electrostatic (PME potential of the whole system; needs a PSF). Returns grid, range, integral and suggested
    isosurface levels."""
    return _run("vmd_volmap", volumetric.volmap, topology=_p(topology), trajectory=_p(trajectory), out_dx=_p(out_dx),
                kind=kind, selection=selection, resolution=resolution, mass_weighted=mass_weighted, first=first,
                last=last, step=step, cutoff=cutoff, vmd_path=_p(vmd_path))


@tool()
def vmd_volume_info(path: str) -> dict:
    """What a density map file holds (OpenDX, CCP4/MRC, Gaussian cube, Situs): grid, spacing, range, integral and
    suggested isosurface levels. Works without VMD."""
    return volumetric.volume_info(_p(path))


@tool()
def vmd_build_system(input_pdb: str, out_prefix: str, selection: str = "protein", solvate: bool = True,
                     padding: float = 10.0, ionize: bool = True, salt_concentration: float = 0.15,
                     histidine: str = "HSD", vmd_path: Optional[str] = None) -> dict:
    """Use ONLY when the user asks to build, solvate or ionize a system for a simulation. Takes the user's protein
    PDB (input_pdb, an existing file) and writes new files starting with out_prefix (a path prefix, not an input):
    CHARMM36 PSF/PDB, a water box with `padding` A around the protein and neutralising ions at `salt_concentration` M.
    Reports charge, atom counts, box size and everything left out (ligands, nucleic acids, crystal water)."""
    return _run("vmd_build_system", build.build_system, input_pdb=_p(input_pdb), out_prefix=_p(out_prefix),
                selection=selection, solvate=solvate, padding=padding, ionize=ionize,
                salt_concentration=salt_concentration, histidine=histidine, vmd_path=_p(vmd_path))


@tool()
def vmd_mutate_residue(psf: str, pdb: str, out_prefix: str, segid: str, resid: int, new_resname: str,
                       vmd_path: Optional[str] = None) -> dict:
    """Mutate one residue in a PSF/PDB pair (VMD mutator plugin), e.g. segid P0, resid 6, new_resname ALA."""
    return _run("vmd_mutate_residue", build.mutate_residue, psf=_p(psf), pdb=_p(pdb), out_prefix=_p(out_prefix),
                segid=segid, resid=resid, new_resname=new_resname, vmd_path=_p(vmd_path))


@tool()
def vmd_merge_structures(psf_a: str, pdb_a: str, psf_b: str, pdb_b: str, out_prefix: str,
                         vmd_path: Optional[str] = None) -> dict:
    """Combine two PSF/PDB systems into one (VMD topotools); warns when segment names collide."""
    return _run("vmd_merge_structures", build.merge_structures, psf_a=_p(psf_a), pdb_a=_p(pdb_a), psf_b=_p(psf_b),
                pdb_b=_p(pdb_b), out_prefix=_p(out_prefix), vmd_path=_p(vmd_path))


@tool()
def vmd_build_membrane(out_prefix: str, lipid: str = "POPC", x_size: float = 80.0, y_size: float = 80.0,
                       force_field: str = "c36", vmd_path: Optional[str] = None) -> dict:
    """Build a POPC or POPE lipid bilayer patch (VMD membrane plugin, CHARMM): PSF/PDB, lipids per leaflet and the
    phosphate-to-phosphate thickness."""
    return _run("vmd_build_membrane", build.build_membrane, out_prefix=_p(out_prefix), lipid=lipid, x_size=x_size,
                y_size=y_size, force_field=force_field, vmd_path=_p(vmd_path))


@tool()
def vmd_build_nanotube(out_pdb: str, n: int = 6, m: int = 6, length_nm: float = 10.0, material: str = "C-C",
                       vmd_path: Optional[str] = None) -> dict:
    """Build a single-wall nanotube of chirality (n, m), carbon (C-C) or boron nitride (B-N), as a PDB; the radius
    is checked against the analytic value."""
    return _run("vmd_build_nanotube", build.build_nanotube, out_pdb=_p(out_pdb), n=n, m=m, length_nm=length_nm,
                material=material, vmd_path=_p(vmd_path))


@tool()
def vmd_render_scene(scene_spec: dict, topology: Optional[str], trajectory: Optional[str], out_png: str,
                     width: int = 1600, height: int = 1200, vmd_path: Optional[str] = None) -> dict:
    """Render a picture of a scene you describe, with VMD + Tachyon, using the user's own files as named. scene_spec: {reps: [{selection, style, color, material,
    params}], isosurfaces: [{file, isovalue, color, style: solid|wireframe|points}], background, frame, rotate:
    [[axis, degrees]], zoom, projection, axes, depthcue, shadows, ambient_occlusion}. Styles: Lines, Licorice, VDW,
    CPK, NewCartoon, QuickSurf, Surf, MSMS, ...; colors: Name, Element, ResName, Chain, Structure, Beta, ColorID n, ...
    Use export_vmd_session to hand the same scene to a VMD user."""
    return scene.render_scene(scene_spec, _p(topology), _p(trajectory), _p(out_png), width=width, height=height,
                              vmd_path=_p(vmd_path))


@tool()
def export_vmd_session(scene_spec: dict, topology: Optional[str], trajectory: Optional[str], out_dir: str,
                       copy_inputs: bool = True, vmd_path: Optional[str] = None) -> dict:
    """Use when the user wants to open or keep a scene in their own VMD. topology and trajectory are the user's own
    files exactly as named (for example protein.pdb and protein.dcd); do not build or convert anything first.
    Writes a folder in out_dir: session.tcl (open with `vmd -e session.tcl`), render.tcl, the input files with relative
    paths, manifest.json (scene, SHA-256 of every input, VMD version) and REPRODUCE.md. The scene is loaded in a real
    VMD to prove it opens. Same scene_spec as vmd_render_scene."""
    return scene.export_session(scene_spec, _p(topology), _p(trajectory), _p(out_dir), copy_inputs=copy_inputs,
                                vmd_path=_p(vmd_path))


@tool()
def vmd_render_turntable(scene_spec: dict, topology: Optional[str], trajectory: Optional[str], out_mp4: str,
                         frames: int = 72, degrees: float = 360.0, axis: str = "y", fps: int = 24, width: int = 960,
                         height: int = 720, vmd_path: Optional[str] = None) -> dict:
    """A rotating-view movie of a scene (same scene_spec as vmd_render_scene): the camera turns `degrees` about
    `axis` over `frames` frames, rendered with VMD + Tachyon and encoded with ffmpeg."""
    return scene.render_turntable(scene_spec, _p(topology), _p(trajectory), _p(out_mp4), frames=frames,
                                  degrees=degrees, axis=axis, fps=fps, width=width, height=height, vmd_path=_p(vmd_path))
