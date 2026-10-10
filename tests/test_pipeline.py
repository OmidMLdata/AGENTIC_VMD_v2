"""The one-call pipelines: renderer choice, legend honesty, provenance."""
import json
import os

import pytest
from conftest import no_real_vmd

from vmd_agent import auto
from vmd_agent.evidence import provenance
from vmd_agent.structure.detect import detect_system


@no_real_vmd
def test_pipeline_end_to_end_without_vmd(ubq, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path),
                                       views=("front", "iso"), renderer="auto")
    assert pkg["ok"] and pkg["renderer"]["used"] == "matplotlib"
    assert pkg["render_ok"] and set(pkg["images"]) == {"front", "iso"}
    assert set(pkg["annotated_images"]) == {"front", "iso"}
    assert all(os.path.exists(p) for p in pkg["images"].values())
    # the agent is told what the renderer cannot show
    assert "renderer.caveats" in pkg["interpretation_instructions"]
    assert pkg["renderer"]["caveats"]
    assert os.path.exists(pkg["recipe_path"])


def test_legend_describes_what_the_backend_drew(ubq, tmp_path):
    pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path),
                                       views=("front",), renderer="matplotlib")
    legend = " ".join(pkg["visual_legend"])
    assert "Backbone trace" in legend and "NewCartoon" not in legend
    vmd_pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path / "v"),
                                           render=False, renderer="vmd")
    assert "Ribbon" in " ".join(vmd_pkg["visual_legend"])


def test_hidden_water_gets_no_colour_key(lyz, tmp_path):
    """The key lists swatches only for what is drawn: water that is not drawn gets none."""
    det = detect_system(lyz)
    assert det["components"]["water"]["present"]
    hidden = auto.build_color_keys(det, show_water=False)
    shown = auto.build_color_keys(det, show_water=True)
    labels = lambda keys: {e["label"] for k in keys for e in k["entries"]}
    assert not any(l.startswith("H ") for l in labels(hidden))
    assert any(l.startswith("H ") for l in labels(shown))


def test_provenance_written_and_verifiable(ubq, tmp_path):
    pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path),
                                       render=False)
    doc = json.load(open(pkg["provenance_path"]))
    run = doc["runs"][0]
    assert run["tool"] == "visualize_and_interpret"
    assert run["inputs"][0]["sha256"] == provenance.sha256_file(ubq)
    assert "mol new" in run["recipe_tcl"]
    assert provenance.verify_provenance(str(tmp_path))["ok"]


def test_render_false_is_detection_only(ubq, tmp_path):
    pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path), render=False)
    assert pkg["images"] == {} and "skipped" in pkg["note"]


@no_real_vmd
def test_requesting_unavailable_vmd_says_so(ubq, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path),
                                       renderer="vmd")
    assert pkg["ok"] and pkg["images"] == {}
    assert "not available" in pkg["note"] and "matplotlib" in pkg["note"]


def test_explicit_representation_noted_for_non_vmd_backend(ubq, tmp_path):
    pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path),
                                       views=("front",), renderer="matplotlib",
                                       representation="QuickSurf")
    assert any("honoured only by the VMD" in n for n in pkg["source_notes"])


@pytest.mark.requires_vmd
def test_with_real_vmd_the_package_uses_vmd_and_records_it(
        ubq, tmp_path, real_vmd, real_tachyon):
    pkg = auto.visualize_and_interpret(ubq, out_dir=str(tmp_path),
                                       views=("front",), vmd_path=real_vmd)
    assert pkg["renderer"]["used"] == "vmd" and pkg["render_ok"]


def test_unloadable_input_is_reported(tmp_path):
    bad = tmp_path / "bad.dcd"
    bad.write_text("x")
    pkg = auto.visualize_and_interpret(str(bad), out_dir=str(tmp_path / "o"))
    assert not pkg["ok"]


def test_pdb_stats_are_in_the_package(lyz, tmp_path):
    pkg = auto.visualize_and_interpret(lyz, out_dir=str(tmp_path), render=False)
    assert any("4 disulfide" in l for l in pkg["stats_caption"])
    assert pkg["structure_stats"]["n_bonds"] > 900
