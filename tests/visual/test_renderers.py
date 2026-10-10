import numpy as np
import os

import pytest
from conftest import no_real_vmd
from PIL import Image

from vmd_agent.structure.detect import detect_system
from vmd_agent.visual.renderers import (
    get_renderer, list_renderers, MatplotlibRenderer,
)
from vmd_agent.visual.renderers.mpl import _VIEW_MAT


@no_real_vmd
def test_auto_falls_back_to_matplotlib_without_vmd(monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert get_renderer("auto").name == "matplotlib"


@pytest.mark.requires_vmd
def test_auto_prefers_a_real_vmd_when_available(real_vmd):
    assert get_renderer("auto", real_vmd).name == "vmd"


def test_unknown_renderer_rejected():
    with pytest.raises(ValueError):
        get_renderer("povray")


def test_list_renderers_reports_all():
    r = list_renderers()
    assert set(r) == {"vmd", "matplotlib"}
    assert r["matplotlib"]["available"] and r["matplotlib"]["caveats"]


def test_matplotlib_renders_views(ubq, tmp_path):
    out = MatplotlibRenderer().render_views(ubq, views=("front", "iso"),
                                            out_dir=str(tmp_path), width=300,
                                            height=240)
    assert out["ok"] and set(out["images"]) == {"front", "iso"}
    im = Image.open(out["images"]["front"])
    assert im.size == (300, 240)
    # something was actually drawn: not a blank canvas
    assert len(set(map(tuple, np.asarray(im.convert("RGB")).reshape(-1, 3)))) > 10
    assert out["renderer"] == "matplotlib" and out["caveats"]


def test_views_differ(ubq, tmp_path):
    out = MatplotlibRenderer().render_views(ubq, views=("front", "side"),
                                            out_dir=str(tmp_path), width=200,
                                            height=200)
    a = np.asarray(Image.open(out["images"]["front"]).convert("L")).tolist()
    b = np.asarray(Image.open(out["images"]["side"]).convert("L")).tolist()
    assert a != b


def test_view_matrices_are_rotations():
    import numpy as np
    for m in _VIEW_MAT.values():
        assert np.allclose(m @ m.T, np.eye(3)) and np.isclose(np.linalg.det(m), 1)


def test_multichain_uses_chain_colours_and_ligand_sticks(hbb, tmp_path):
    from vmd_agent.visual.renderers.mpl import _Scene
    from vmd_agent.inputs.molio import load_universe
    det = detect_system(hbb)
    scene = _Scene(load_universe(hbb), det, False, False)
    assert len(scene.traces) == 4 and scene.sticks      # 4 chains + heme bonds
    r = MatplotlibRenderer()
    assert r.protein_reps(det)[0][:2] == ("Tube", "Chain")


def test_alphafold_uses_plddt_reps(ubq):
    det = detect_system(ubq)
    assert MatplotlibRenderer().protein_reps(det, plddt_coloring=True)[0][1] == "Beta"


def test_render_frames_uses_fixed_camera(sample, tmp_path):
    pdb, dcd = sample
    out = MatplotlibRenderer().render_frames(pdb, dcd, [0, 4, 7],
                                             out_dir=str(tmp_path), width=200,
                                             height=200)
    assert out["ok"] and [i["frame"] for i in out["images"]] == [0, 4, 7]
    assert all(os.path.exists(i["path"]) for i in out["images"])


def test_unsupported_focus_is_reported(ubq, tmp_path):
    out = MatplotlibRenderer().render_views(ubq, views=("front",),
                                            out_dir=str(tmp_path), width=100,
                                            height=100, focus="surface")
    assert "not supported" in out["focus_note"]


def test_missing_file_is_structured_error(tmp_path):
    out = MatplotlibRenderer().render_views("/nonexistent.pdb",
                                            out_dir=str(tmp_path))
    assert not out["ok"] and out["error"]


@pytest.mark.parametrize("w,h", [(0, 0), (-5, 100), (100, 0), (30000, 100), ("a", 5)])
def test_unusable_image_sizes_get_a_clear_error(ubq, tmp_path, w, h):
    """width=0 is refused with a clear message, not a bare ZeroDivisionError."""
    out = MatplotlibRenderer().render_views(ubq, out_dir=str(tmp_path), width=w,
                                            height=h)
    assert not out["ok"] and ("size" in out["error"] or "integers" in out["error"])
    out = MatplotlibRenderer().render_frames(ubq, None, [0], out_dir=str(tmp_path),
                                             width=w, height=h)
    assert not out["ok"]


def test_unknown_views_are_reported_not_silently_replaced(ubq, tmp_path):
    out = MatplotlibRenderer().render_views(ubq, out_dir=str(tmp_path), width=100,
                                            height=100, views=["nope", "front"])
    assert out["ok"] and out["ignored_views"] == ["nope"]
    out = MatplotlibRenderer().render_views(ubq, out_dir=str(tmp_path), width=100,
                                            height=100, views=["nope"])
    assert out["ok"] and "unknown view" in out["view_note"]


def test_dropped_frames_are_listed(sample, tmp_path):
    out = MatplotlibRenderer().render_frames(*sample, [0, 999, -1], out_dir=str(tmp_path),
                                             width=100, height=80)
    assert out["frames_failed"] == [999, -1] and out["n_rendered"] == 1
