"""Catalogue of VMD graphical representations, colouring methods and materials.

This is the toolkit's *domain knowledge* about how molecules should be drawn.
It exists as structured data rather than hard-coded defaults so that an agent
can (a) explain to a user why a representation was chosen, (b) honour a
request like "show me the surface" or "use licorice for the side chains", and
(c) warn when a style is a poor fit (a cartoon of an 8-residue peptide, an
MSMS surface of a million atoms).

Each entry records the exact VMD ``mol representation`` string and its default
parameters, so recipes generated from this table are directly runnable.
"""
from __future__ import annotations

from typing import Optional

# --------------------------------------------------------------------------
# category -> human blurb
CATEGORIES = {
    "backbone": "Backbone & secondary structure — the global fold, for "
                "overview and publication figures.",
    "atomic": "Atomic & molecular detail — specific residues, binding "
              "pockets, ligands, ions and atomic interactions.",
    "surface": "Volumetric & surface shape — the physical boundary and "
               "volume, for pocket depth, cavities and interfaces.",
    "special": "Special-purpose helpers (bonds for materials, explicit "
               "hydrogen bonds).",
}

# --------------------------------------------------------------------------
# The catalogue. `params` are VMD's positional parameters for that style.
REPRESENTATIONS = {
    # ---------------------------------------------------------- backbone ---
    "NewCartoon": {
        "category": "backbone",
        "params": "0.300000 20.000000 4.100000 0",
        "param_names": "thickness, resolution, aspect_ratio, spline_style",
        "summary": "The most common representation for publication.",
        "detail": "Renders smooth, sweeping ribbons for alpha-helices, flat "
                  "arrows for beta-sheets, and a thin tube for random coils, "
                  "so the secondary-structure content of a fold is readable "
                  "at a glance.",
        "best_for": ["publication overview figures",
                     "showing secondary structure (helix / sheet / coil)",
                     "multi-domain proteins and multi-chain complexes"],
        "colour_with": ["Structure", "Chain", "ResType", "Beta"],
        "limitations": "Requires a secondary-structure assignment (VMD runs "
                       "STRIDE); shows no side chains; nearly empty for very "
                       "short peptides or non-protein molecules.",
        "min_residues": 20,
    },
    "Tube": {
        "category": "backbone",
        "params": "0.300000 20.000000",
        "param_names": "radius, resolution",
        "summary": "A clean smooth tube through the backbone.",
        "detail": "Draws a smooth line strictly along the protein backbone "
                  "(the C-alpha trace), giving an uncluttered view of the "
                  "global fold without secondary-structure-specific geometry.",
        "best_for": ["global fold and topology", "chain tracing in crowded "
                     "complexes", "backdrop behind an atomic-detail rep"],
        "colour_with": ["Chain", "Index", "Structure", "Beta"],
        "limitations": "Carries no secondary-structure information — helices "
                       "and sheets look identical.",
    },
    "Ribbons": {
        "category": "backbone",
        "params": "0.300000 20.000000 2.000000",
        "param_names": "radius, resolution, width",
        "summary": "A flat ribbon along the backbone.",
        "detail": "Like Tube but flattened into a ribbon that follows the "
                  "backbone, showing chain twist without drawing "
                  "secondary-structure-specific shapes.",
        "best_for": ["nucleic acid backbones", "showing chain twist",
                     "a lighter alternative to NewCartoon"],
        "colour_with": ["Chain", "Structure", "ResName"],
        "limitations": "Less immediately readable than NewCartoon for "
                       "proteins; no arrows/coils distinction.",
    },
    # ------------------------------------------------------------ atomic ---
    "CPK": {
        "category": "atomic",
        "params": "1.000000 0.300000 12.000000 12.000000",
        "param_names": "sphere_radius, bond_radius, sphere_res, bond_res",
        "summary": "Spheres scaled to van der Waals radii, plus cylinder bonds.",
        "detail": "Renders atoms as spheres scaled to their van der Waals "
                  "radii and bonds as cylinders — the classic ball-and-stick "
                  "look, conveying atomic size as well as connectivity.",
        "best_for": ["highlighting single residues", "bound ligands",
                     "ions", "active-site chemistry"],
        "colour_with": ["Name", "Element", "ResName", "Charge"],
        "limitations": "Visually heavy; spheres occlude one another in large "
                       "selections. Restrict it to a small selection.",
    },
    "Licorice": {
        "category": "atomic",
        "params": "0.300000 12.000000 12.000000",
        "param_names": "bond_radius, sphere_res, bond_res",
        "summary": "Uniform narrow cylinders for atoms and bonds.",
        "detail": "Draws atoms and bonds as uniform, narrow cylinders — a "
                  "highly scannable, clean way to view amino-acid side-chain "
                  "interactions (hydrogen bonds, salt bridges) without bulky "
                  "spheres obscuring the geometry.",
        "best_for": ["side-chain interactions", "hydrogen bonds and salt "
                     "bridges", "ligands and small molecules",
                     "short peptides where a cartoon shows nothing"],
        "colour_with": ["Name", "Element", "ResName", "ResType"],
        "limitations": "All atoms drawn the same width, so relative atomic "
                       "size is not conveyed; cluttered above a few hundred "
                       "residues.",
    },
    "Lines": {
        "category": "atomic",
        "params": "1.000000",
        "param_names": "thickness",
        "summary": "The default, performance-friendly wireframe.",
        "detail": "Renders simple wireframe connections between bonded atoms. "
                  "Cheap to draw, which makes it ideal for checking raw "
                  "trajectories or viewing massive systems interactively.",
        "best_for": ["very large systems", "quick trajectory sanity checks",
                     "water and solvent context without visual weight"],
        "colour_with": ["Name", "Element", "ResName"],
        "limitations": "Thin and unshaded — poor for publication figures; "
                       "does not ray-trace attractively.",
    },
    "VDW": {
        "category": "atomic",
        "params": "1.000000 12.000000",
        "param_names": "sphere_scale, resolution",
        "summary": "Space-filling spheres, no bonds.",
        "detail": "Atoms as van der Waals spheres with no bond cylinders — "
                  "the space-filling view of molecular volume and packing.",
        "best_for": ["ions", "space-filling / packing views",
                     "materials and lattices"],
        "colour_with": ["Name", "Element", "ResName", "Index"],
        "limitations": "Completely hides interior structure.",
    },
    # ----------------------------------------------------------- surface ---
    "QuickSurf": {
        "category": "surface",
        "params": "1.000000 0.500000 1.000000 1.000000",
        "param_names": "radius_scale, density_isovalue, grid_spacing, quality",
        "summary": "Fast, smooth, continuous molecular surface.",
        "detail": "Generates a fast, smooth, continuous molecular surface. "
                  "It is exceptional for seeing the overall envelope of a "
                  "protein and, because it is quick enough to recompute every "
                  "frame, for tracking shape changes across a trajectory.",
        "best_for": ["overall molecular envelope", "shape change during a "
                     "trajectory", "very large assemblies where cartoon is "
                     "too slow"],
        "colour_with": ["Chain", "ResType", "Charge", "Structure"],
        "limitations": "Approximate surface — smoother and less exact than "
                       "Surf/MSMS; fine cavity detail is lost.",
    },
    "Surf": {
        "category": "surface",
        "params": "1.400000 0.000000",
        "param_names": "probe_radius, wireframe(0/1)",
        "summary": "Detailed solvent-accessible surface.",
        "detail": "Renders a detailed solvent-accessible surface, useful for "
                  "evaluating cavities and the interface areas where proteins "
                  "bind other molecules.",
        "best_for": ["binding-pocket depth and shape", "protein-protein "
                     "interfaces", "cavity and channel analysis"],
        "colour_with": ["ResType", "Charge", "Chain"],
        "limitations": "Much slower than QuickSurf and memory-hungry; "
                       "impractical for very large systems or long "
                       "trajectories.",
        "max_atoms": 200000,
    },
    "MSMS": {
        "category": "surface",
        "params": "1.500000 1.500000",
        "param_names": "probe_radius, density",
        "summary": "High-quality analytic solvent-excluded surface.",
        "detail": "Produces a detailed solvent-excluded (Connolly) surface "
                  "with well-defined cavities — the most accurate surface "
                  "option for evaluating pockets and interfaces.",
        "best_for": ["publication-quality cavity analysis",
                     "precise interface area visualisation"],
        "colour_with": ["ResType", "Charge", "Chain"],
        "limitations": "Requires the external `msms` binary to be installed; "
                       "fails on very large or badly-formed structures.",
        "requires_external": "msms",
        "max_atoms": 100000,
    },
    # ----------------------------------------------------------- special ---
    "DynamicBonds": {
        "category": "special",
        "params": "1.600000 0.100000 12.000000",
        "param_names": "cutoff_distance, bond_radius, resolution",
        "summary": "Bonds computed by distance, not topology.",
        "detail": "Draws a bond between any two atoms closer than a cutoff. "
                  "Essential for structures loaded without bond information "
                  "(a plain PDB of a material, a lattice, or a graphene "
                  "sheet), where VMD would otherwise draw nothing.",
        "best_for": ["materials and lattices", "structures with no bond "
                     "records", "coarse-grained models"],
        "colour_with": ["Element", "Name", "Index"],
        "limitations": "Cutoff must match the chemistry (about 1.6 Å for "
                       "C-C in graphene); too large invents spurious bonds.",
    },
    "HBonds": {
        "category": "special",
        "params": "3.000000 20.000000 3.000000",
        "param_names": "distance_cutoff, angle_cutoff, line_thickness",
        "summary": "Explicit hydrogen-bond lines.",
        "detail": "Draws dashed lines for donor-acceptor pairs satisfying "
                  "distance and angle criteria — overlay it on a Licorice "
                  "representation to make an interaction network explicit.",
        "best_for": ["hydrogen-bond networks", "binding-site interactions"],
        "colour_with": ["Name", "ResName"],
        "limitations": "Geometric criteria only, no energetics; needs "
                       "hydrogens present in the structure.",
    },
}

# --------------------------------------------------------------------------
COLOUR_METHODS = {
    "Structure": "Secondary structure — helix / sheet / coil. The default "
                 "pairing for NewCartoon on a single chain.",
    "Chain": "One colour per chain; the clearest way to separate subunits in "
             "a complex.",
    "Name": "By atom name using VMD element palette: CYAN carbon (not grey or green), red O, blue N, yellow S, white H.",
    "Element": "By chemical element — like Name but strictly elemental.",
    "ResName": "One colour per residue type.",
    "ResType": "By residue chemistry (hydrophobic / polar / acidic / basic) — "
               "good on surfaces to show patches.",
    "Beta": "By the B-factor column. For crystal structures this is thermal "
            "displacement; for AlphaFold models it holds the pLDDT confidence "
            "score, so this is the correct way to colour a predicted model.",
    "Charge": "By partial charge — useful on a surface to show electrostatic "
              "patches (requires a topology carrying charges).",
    "Index": "By atom/residue index — traces sequence direction along a chain.",
    "Timestep": "By trajectory frame; useful when overlaying many frames.",
    "ColorID": "A single fixed colour (ColorID 0-32), e.g. for a membrane or "
               "a material phase.",
}

MATERIALS = {
    "Opaque": "Plain solid shading; the fastest sensible default.",
    "AOChalky": "Matte finish that responds well to ambient occlusion — the "
                "usual choice for publication ray-traced figures.",
    "Glossy": "Shiny highlights; good for presentations and posters.",
    "Transparent": "See-through; use for a surface drawn over a cartoon so "
                   "both the envelope and the fold are visible.",
    "Ghost": "Very faint; for context that must not compete with the subject.",
}

# Focus -> the representation plan an agent should use for that intent.
FOCUS_PLANS = {
    "overview": "Best general view: NewCartoon (or size-appropriate "
                "alternative), ligands in Licorice, ions as VDW.",
    "fold": "Tube backbone only — global topology without secondary "
            "structure detail.",
    "interactions": "Licorice side chains plus HBonds, over a faint Tube "
                    "backbone.",
    "surface": "QuickSurf envelope; Surf when the system is small enough for "
               "the extra detail.",
    "pocket": "Transparent Surf over a cartoon, with the ligand in CPK.",
    "performance": "Lines — for very large systems or a fast trajectory check.",
}


# --------------------------------------------------------------------------
def list_representations(category: Optional[str] = None) -> dict:
    """Return the catalogue, optionally filtered to one category."""
    reps = {k: v for k, v in REPRESENTATIONS.items()
            if category is None or v["category"] == category}
    return {
        "categories": CATEGORIES,
        "representations": {
            k: {"category": v["category"], "summary": v["summary"],
                "detail": v["detail"], "best_for": v["best_for"],
                "colour_with": v["colour_with"],
                "limitations": v["limitations"],
                "vmd_command": f"mol representation {k} {v['params']}",
                "parameters": v["param_names"]}
            for k, v in reps.items()},
        "colour_methods": COLOUR_METHODS,
        "materials": MATERIALS,
        "focus_plans": FOCUS_PLANS,
    }


def params_for(name: str) -> str:
    """VMD parameter string for a style (empty when unknown)."""
    rep = REPRESENTATIONS.get(name)
    return rep["params"] if rep else ""


def describe_representation(name: str) -> dict:
    """Full detail for one representation, case-insensitively."""
    for k, v in REPRESENTATIONS.items():
        if k.lower() == name.lower().strip():
            return {"name": k, **v,
                    "vmd_command": f"mol representation {k} {params_for(k)}"}
    return {"error": f"Unknown representation '{name}'.",
            "available": sorted(REPRESENTATIONS)}


def check_suitability(name: str, detection: dict) -> list:
    """Warn when a representation is a poor fit for this structure."""
    rep = REPRESENTATIONS.get(name)
    if not rep:
        return [f"Unknown representation '{name}'."]
    warns = []
    n_atoms = detection.get("n_atoms", 0)
    prot = detection.get("components", {}).get("protein", {})
    n_res = prot.get("n_residues", 0)
    if rep.get("min_residues") and 0 < n_res < rep["min_residues"]:
        warns.append(
            f"{name} needs a reasonable stretch of secondary structure; this "
            f"protein has only {n_res} residues, so Licorice or Tube will "
            "show far more.")
    if rep.get("max_atoms") and n_atoms > rep["max_atoms"]:
        warns.append(
            f"{name} is slow above ~{rep['max_atoms']} atoms and this system "
            f"has {n_atoms}; QuickSurf is the practical alternative.")
    if rep.get("requires_external"):
        warns.append(
            f"{name} requires the external '{rep['requires_external']}' binary "
            "to be installed and on PATH.")
    if name in ("NewCartoon", "Ribbons", "Tube") and not prot.get("present") \
            and not detection.get("components", {}).get("nucleic", {}).get("present"):
        warns.append(
            f"{name} follows a biopolymer backbone, but no protein or nucleic "
            "acid was detected — nothing would be drawn.")
    return warns
