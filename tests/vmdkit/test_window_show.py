"""What the tools found, drawn in the VMD window (show_in_window), against a real VMD started with no window. Every claim about what is drawn is checked by asking VMD
what it holds, and the analyses are the tools' own: the window only shows them."""
import os
import shutil

import pytest

from vmd_agent import toolhints, toolset, vmdlink
from vmd_agent import tool_dataset as D

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
vmd = pytest.mark.requires_vmd
T = toolset.TOOLS


@pytest.fixture()
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VMD_AGENT_WINDOW_HEADLESS", "1")
    for f in ("protein.pdb", "protein.dcd"):
        shutil.copy(os.path.join(DATA, "ubq_md", f), tmp_path / f)
    shutil.copy(os.path.join(DATA, "1ubq.pdb"), tmp_path / "1ubq.pdb")
    yield str(tmp_path)
    vmdlink.stop()


def state():
    return vmdlink.status()


def reps_of(st):
    return [r for m in st["molecules"] for r in m["reps"]]


def test_the_tools_that_can_show_their_result_say_so_in_their_signature():
    from vmd_agent import window_present
    names = {"find_interactions", "backbone_torsions", "check_structure", "secondary_structure", "select_keyframes", "align_structures", "fit_to_map", "make_map",
             "combine_maps", "inspect_map", "build_system", "mutate_residue", "merge_structures", "build_membrane", "build_nanotube", "visualize_and_interpret",
             "render_image", "export_session", "run_workflow"}
    for n in names:
        schema = toolset.tool_schema(T[n])["input_schema"]["properties"]
        assert schema["show_in_window"] == {"type": "boolean"}, n
        enriched = toolhints.enrich([toolset.tool_schema(T[n])])[0]["input_schema"]["properties"]["show_in_window"]
        assert "VMD window" in enriched["description"], n                                              # the model is told what it does
    assert set(window_present.PRESENTERS) >= names - {"run_workflow"}
    assert "show_in_window" not in toolset.tool_schema(T["probe_video"])["input_schema"]["properties"]            # nothing to draw: no parameter


@vmd
def test_persistent_interactions_are_highlighted_in_vmd(folder):
    r = T["find_interactions"](topology=os.path.join(folder, "protein.pdb"), trajectory=os.path.join(folder, "protein.dcd"), kind="salt_bridges", step=10, show_in_window=True)
    assert r["ok"] and r["window"]["ok"], r["window"]
    shown = r["window"]["highlighted_residues"]
    assert {27, 52} <= set(shown)                                                     # the known K27-D52 salt bridge of ubiquitin
    assert any(rep["selection"].startswith("resid") and "27" in rep["selection"] for rep in reps_of(state()))
    again = T["find_interactions"](topology=os.path.join(folder, "protein.pdb"), trajectory=os.path.join(folder, "protein.dcd"), kind="salt_bridges", step=10, show_in_window=True)
    assert len(state()["molecules"]) == 1                                             # the molecule already in the window is reused, not loaded again
    assert again["window"]["molecule"] == r["window"]["molecule"]


@vmd
def test_ramachandran_outliers_and_keyframes_and_secondary_structure_are_shown(folder):
    pdb, dcd = os.path.join(folder, "protein.pdb"), os.path.join(folder, "protein.dcd")
    t = T["backbone_torsions"](topology=os.path.join(folder, "1ubq.pdb"), show_in_window=True)
    assert t["window"]["highlighted_residues"] == sorted({o["resid"] for o in t["outliers"]})
    k = T["select_keyframes"](topology=pdb, trajectory=dcd, k=4, show_in_window=True)
    assert k["window"]["ok"] and k["window"]["frames"] == k["frames"] and next(m for m in state()["molecules"] if m["file"].endswith("protein.pdb"))["frame"] == k["frames"][0]
    s = T["secondary_structure"](topology=pdb, trajectory=dcd, step=10, show_in_window=True)
    assert s["window"]["ok"]
    molecule = next(m for m in state()["molecules"] if m["file"].endswith("protein.pdb"))
    assert [(r["style"], r["color"]) for r in molecule["reps"]] == [("NewCartoon", "Structure")]


@vmd
def test_visualize_in_the_window_draws_what_the_recipe_would_and_explains_the_colours(folder):
    pdb = os.path.join(folder, "1ubq.pdb")
    r = T["window_visualize"](topology=pdb)
    assert r["ok"] and r["system_type"] and r["visual_legend"] and r["what_to_look_for"]
    from vmd_agent.structure import detect
    from vmd_agent.visual import recipes
    planned, _ = recipes.planned_reps(detect.detect_system(pdb), "Opaque")
    drawn = [(rep["selection"], rep["style"].split()[0], rep["color"]) for rep in reps_of(state())]
    assert drawn == [(p["selection"], p["style"], p["color"]) for p in planned]                      # the recipe's own choices, drawn by VMD
    st = state()
    assert st["display"]["background"] == "white" and st["display"]["projection"] == "Orthographic"
    again = T["window_visualize"](focus="surface")                                                    # redraw the molecule that is there
    assert again["ok"] and [rep["style"].split()[0] for rep in reps_of(state())][0] == "Surf"
    via_tool = T["visualize_and_interpret"](topology=pdb, out_dir=os.path.join(folder, "viz"), renderer="matplotlib", views=["front"], show_in_window=True)
    assert via_tool["window"]["ok"] and len(state()["molecules"]) == 1


@vmd
def test_a_fit_a_map_and_a_superposition_are_drawn_in_vmd(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VMD_AGENT_WINDOW_HEADLESS", "1")
    D.make_dataset(str(tmp_path))
    try:
        fit = T["fit_to_map"](model=str(tmp_path / "moved.pdb"), map_file=str(tmp_path / "target.dx"), out_pdb=str(tmp_path / "fitted.pdb"), show_in_window=True)
        assert fit["window"]["ok"], fit["window"]
        mols = state()["molecules"]
        iso = [m for m in mols if any(r["style"].startswith("Isosurface") for r in m["reps"])]
        assert len(mols) == 2 and len(iso) == 1 and iso[0]["reps"][0]["material"] == "Transparent"
        assert fit["window"]["isovalue"] > 0
        assert T["inspect_map"](path=str(tmp_path / "blob.dx"), show_in_window=True)["window"]["ok"]
        al = T["align_structures"](mobile=str(tmp_path / "moved.pdb"), reference=str(tmp_path / "protein.pdb"), out_pdb=str(tmp_path / "al.pdb"), show_in_window=True)
        assert al["window"]["ok"] and {"reference_molecule", "aligned_molecule"} <= set(al["window"])
        no_file = T["align_structures"](mobile=str(tmp_path / "moved.pdb"), reference=str(tmp_path / "protein.pdb"), show_in_window=True)
        assert no_file["window"]["ok"] is False and "out_pdb" in no_file["window"]["error"]            # said plainly, and the tool itself still succeeded
        assert no_file["ok"]
    finally:
        vmdlink.stop()


@vmd
def test_a_built_system_is_loaded_in_vmd(folder):
    r = T["build_system"](input_pdb=os.path.join(folder, "1ubq.pdb"), out_prefix=os.path.join(folder, "b", "ubq"), padding=6.0, show_in_window=True)
    assert r["ok"] and r["window"]["ok"], r.get("window")
    m = next(m for m in state()["molecules"] if m["id"] == r["window"]["molecule"])
    assert m["natoms"] == r["n_atoms"]


@vmd
def test_a_movie_of_the_window_is_drawn_by_vmd_and_the_view_is_put_back(folder):
    T["window_load"](topology=os.path.join(folder, "protein.pdb"), trajectory=os.path.join(folder, "protein.dcd"))
    T["window_animate"](action="goto", frame=3)
    before = state()["molecules"][0]["frame"]
    r = T["window_movie"](out_mp4=os.path.join(folder, "m.mp4"), action="trajectory", stride=10, fps=5, quality="tachyon")
    assert r["ok"] and r["n_frames"] == 5 and r["validation"]["ok"], r
    assert state()["molecules"][0]["frame"] == before
    s = T["window_movie"](out_mp4=os.path.join(folder, "spin.mp4"), action="spin", frames=6, fps=6, quality="tachyon")
    assert s["ok"] and s["n_frames"] == 6 and os.path.getsize(s["movie"]) > 1000
    assert T["window_movie"](out_mp4=os.path.join(folder, "x.mp4"), action="nonsense")["ok"] is False


@vmd
def test_whole_jobs_can_show_their_outcome_in_vmd(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VMD_AGENT_WINDOW_HEADLESS", "1")
    D.make_dataset(str(tmp_path))
    try:
        cryo = T["run_workflow"](name="cryoem_fit", files=[str(tmp_path / "moved.pdb"), str(tmp_path / "target.dx")], out_dir=str(tmp_path / "w1"), show_in_window=True)
        assert cryo["ok"] and cryo["window"]["ok"], cryo["window"]
        assert any(r["style"].startswith("Isosurface") for r in reps_of(state()))
        T["window_molecules"](action="clear")
        so = T["run_workflow"](name="structure_overview", files=[str(tmp_path / "protein.pdb")], out_dir=str(tmp_path / "w2"), show_in_window=True)
        assert so["window"]["ok"] and len(state()["molecules"]) == 1
        T["window_molecules"](action="clear")
        cmp_ = T["run_workflow"](name="compare_runs", files=[str(tmp_path / "protein.pdb"), str(tmp_path / "protein.dcd"), str(tmp_path / "protein.dcd")], out_dir=str(tmp_path / "w3"),
                                 show_in_window=True)
        assert cmp_["window"]["ok"] and len(state()["molecules"]) == 2
        assert {m["reps"][0]["color"] for m in state()["molecules"]} == {"ColorID 0", "ColorID 1"}
        assert T["run_workflow"](name="structure_overview", files=[str(tmp_path / "protein.pdb")], out_dir=str(tmp_path / "w4"))["ok"]       # without the flag nothing is drawn
    finally:
        vmdlink.stop()
