"""VMD orchestration.

Two kinds of test, and no stand-ins:

* **Script and policy tests** need no VMD: the Tcl the toolkit generates is built
  by pure functions and checked as text, and hostile input must be refused before
  anything is launched.
* **Real-VMD tests** (``requires_vmd``) run the real VMD and Tachyon and check what
  they produce. They are skipped, with the reason shown, on a machine without VMD.
"""
import glob
import os
import shutil
import tempfile

import numpy as np
import pytest
from PIL import Image

from vmd_agent.environment import find_vmd
from vmd_agent.security import SecurityError
from vmd_agent.structure.detect import detect_system
from vmd_agent.visual import render


def _leftovers(prefix):
    return set(glob.glob(os.path.join(tempfile.gettempdir(), prefix + "*")))


def _is_png(path):
    with open(path, "rb") as fh:
        return fh.read(8) == b"\x89PNG\r\n\x1a\n"


def _not_blank(path):
    with Image.open(path) as im:
        return float(np.asarray(im.convert("L"), dtype=float).std()) > 0.0


@pytest.fixture
def vmd_launches(monkeypatch):
    """Counts launches of VMD while still running the real one."""
    calls = []
    real = render._run_vmd_text

    def counting(*a, **k):
        calls.append(a)
        return real(*a, **k)
    monkeypatch.setattr(render, "_run_vmd_text", counting)
    return calls


# ============================================================ no VMD required
def test_topology_frame_dropped_when_trajectory_follows(sample, tmp_path):
    pdb, dcd = sample
    lines = render._load_lines(pdb, dcd)
    assert any("animate delete beg 0 end 0" in l for l in lines)
    psf_like = render._load_lines(str(tmp_path / "x.psf"), dcd)
    assert not any("animate delete" in l for l in psf_like)


def test_targa_output_is_converted_to_png(tmp_path):
    p = tmp_path / "t.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(str(p), format="BMP")  # not a PNG
    assert not _is_png(str(p))
    assert render._ensure_png(str(p)) and _is_png(str(p))


def test_reps_only_tcl_strips_standalone_lines(tmp_path):
    rec = tmp_path / "r.tcl"
    rec.write_text("mol new {/x.pdb} type {pdb} waitfor all\n"
                   "mol representation NewCartoon\nset outfile \"render\"\n"
                   "render Tachyon $outfile.dat\n")
    src = render._reps_only_tcl(str(rec), str(tmp_path))
    text = open(src.split("{")[1].split("}")[0]).read()
    assert "mol representation" in text
    assert "mol new" not in text and "render Tachyon" not in text


def test_image_script_loads_draws_and_renders_once(ubq, tmp_path):
    lines = render._image_lines(str(tmp_path), "/w/scene.dat", ubq, None, -1,
                                detect_system(ubq), None, "white")
    text = "\n".join(lines)
    assert lines[0].startswith("mol new") and lines[-1] == "quit"
    assert "animate goto end" in text
    assert text.count("render Tachyon") == 1 and "/w/scene.dat" in text
    assert "display resize" not in text      # aborts headless VMD off a TTY


def test_view_rotations_are_emitted(ubq, tmp_path):
    scenes = {v: f"/w/{v}.dat" for v in ("front", "side", "top", "iso")}
    text = "\n".join(render._views_lines(
        str(tmp_path), scenes, ubq, None, -1, detect_system(ubq), None,
        "white"))
    assert "rotate y by 90" in text and "rotate x by 90" in text
    assert "rotate x by 30" in text and "rotate y by -30" in text
    assert text.count("render Tachyon") == 4           # one session, four scenes
    assert text.count("display resetview") == 4        # reset before each view


def test_frames_script_sets_the_camera_once(sample, tmp_path):
    pdb, dcd = sample
    scenes = [f"/w/s{k}.dat" for k in range(3)]
    text = "\n".join(render._frames_lines(
        str(tmp_path), scenes, [0, 3, 7], pdb, dcd, detect_system(pdb, dcd),
        None, "white", "front"))
    assert text.count("display resetview") == 1       # camera fixed from frame 0
    assert text.count("render Tachyon") == 3
    assert [l for l in text.splitlines() if l.startswith("animate goto")] == [
        "animate goto 0", "animate goto 0", "animate goto 3", "animate goto 7"]


def test_hostile_recipe_path_never_reaches_the_script(ubq, tmp_path):
    """The recipe is read and rewritten into a private temp file, so its own
    path is never interpolated into Tcl."""
    rec = tmp_path / "r}.tcl"
    rec.write_text("mol representation Lines\n")
    text = "\n".join(render._image_lines(
        str(tmp_path), "/w/s.dat", ubq, None, -1, None, str(rec), "white"))
    assert "r}.tcl" not in text
    rewritten = text.split("source {")[1].split("}")[0]
    assert "mol representation Lines" in open(rewritten).read()


def test_run_vmd_tcl_blocks_dangerous_script():
    r = render.run_tcl("exec rm -rf /")
    assert r["blocked"] and not r["ok"]


def test_hostile_path_is_refused_before_anything_is_launched(
        tmp_path, vmd_launches):
    bad = str(tmp_path / "x.pdb} ; exec touch /tmp/vmd_agent_pwned ; set a {")
    r = render.render_image(bad, out_png=str(tmp_path / "a.png"))
    assert not r["ok"] and r["blocked"]
    r = render.render_views(bad, out_dir=str(tmp_path))
    assert not r["ok"] and r["blocked"]
    r = render.render_frames(bad, None, [0], out_dir=str(tmp_path))
    assert not r["ok"] and r["blocked"]
    r = render.render_movie(bad, bad, out_mp4=str(tmp_path / "m.mp4"))
    assert not r["ok"] and r["blocked"]
    assert vmd_launches == []                       # VMD was never started
    assert not os.path.exists("/tmp/vmd_agent_pwned")


def test_hostile_background_is_refused(ubq, tmp_path, vmd_launches):
    r = render.render_views(ubq, background="white; exec touch /tmp/x",
                            out_dir=str(tmp_path))
    assert not r["ok"] and "background" in r["error"]
    assert vmd_launches == []


def test_load_lines_refuses_hostile_trajectory_path(sample):
    with pytest.raises(SecurityError):
        render._load_lines(sample[0], "/t/x.dcd} ; exec id ; {")


@pytest.mark.skipif(find_vmd() is not None,
                    reason="a real VMD is installed here, so it would be found")
def test_no_vmd_gives_actionable_error(tmp_path, ubq):
    r = render.render_image(ubq, out_png=str(tmp_path / "x.png"),
                            vmd_path="/nonexistent")
    assert not r["ok"] and "VMD not found" in r["error"]


# ============================================================ real VMD required
@pytest.mark.requires_vmd
def test_run_vmd_tcl_runs_a_safe_script_in_real_vmd(real_vmd):
    r = render.run_tcl("puts hello_from_vmd", real_vmd)
    assert r["ok"] and "hello_from_vmd" in r["stdout"]


@pytest.mark.requires_vmd
def test_real_vmd_loads_the_structure_it_is_given(real_vmd, ubq):
    r = render.run_tcl(
        f"mol new {{{ubq}}} type pdb waitfor all\n"
        'puts "ATOMS=[[atomselect top all] num]"', real_vmd)
    n = [l for l in r["stdout"].splitlines() if l.startswith("ATOMS=")]
    from vmd_agent.inputs.molio import load_universe
    assert n and int(n[0][6:]) == len(load_universe(ubq).atoms)


@pytest.mark.requires_vmd
def test_render_image_produces_a_real_png_and_cleans_scratch(
        real_vmd, real_tachyon, ubq, tmp_path):
    before = _leftovers("vmd_render_")
    out = render.render_image(ubq, detection=detect_system(ubq),
                              out_png=str(tmp_path / "a.png"), width=400,
                              height=300, vmd_path=real_vmd)
    assert out["ok"], out
    assert _is_png(out["image"]) and _not_blank(out["image"])
    with Image.open(out["image"]) as im:
        assert im.size == (400, 300)
    assert "scene_file" not in out                       # nothing leaked
    assert _leftovers("vmd_render_") == before           # scratch removed


@pytest.mark.requires_vmd
def test_keep_work_retains_the_scene(real_vmd, real_tachyon, ubq, tmp_path):
    out = render.render_image(ubq, detection=detect_system(ubq),
                              out_png=str(tmp_path / "a.png"), width=200,
                              height=200, keep_work=True, vmd_path=real_vmd)
    try:
        assert out["ok"] and os.path.exists(out["scene_file"])
    finally:
        shutil.rmtree(out.get("work_dir", ""), ignore_errors=True)


@pytest.mark.requires_vmd
def test_render_views_is_one_vmd_session_for_many_images(
        real_vmd, real_tachyon, ubq, tmp_path, vmd_launches):
    before = _leftovers("vmd_views_work_")
    out = render.render_views(ubq, detection=detect_system(ubq),
                              views=("front", "side", "top", "iso"),
                              out_dir=str(tmp_path / "v"), width=200,
                              height=150, vmd_path=real_vmd)
    assert out["ok"] and set(out["images"]) == {"front", "side", "top", "iso"}
    assert all(_is_png(p) and _not_blank(p) for p in out["images"].values())
    assert len(vmd_launches) == 1                        # ONE VMD launch
    assert _leftovers("vmd_views_work_") == before


@pytest.mark.requires_vmd
def test_views_from_different_angles_really_differ(real_vmd, real_tachyon, ubq,
                                                   tmp_path):
    out = render.render_views(ubq, detection=detect_system(ubq),
                              views=("front", "side"), out_dir=str(tmp_path),
                              width=200, height=150, vmd_path=real_vmd)
    a = np.asarray(Image.open(out["images"]["front"]).convert("L"), float)
    b = np.asarray(Image.open(out["images"]["side"]).convert("L"), float)
    assert np.abs(a - b).mean() > 0.5


@pytest.mark.requires_vmd
def test_render_frames_single_session_in_the_order_requested(
        real_vmd, real_tachyon, sample, tmp_path, vmd_launches):
    pdb, dcd = sample
    out = render.render_frames(pdb, dcd, [0, 3, 7],
                               detection=detect_system(pdb, dcd),
                               out_dir=str(tmp_path / "f"), width=200,
                               height=150, vmd_path=real_vmd)
    assert out["ok"] and out["n_rendered"] == 3
    assert [i["frame"] for i in out["images"]] == [0, 3, 7]
    assert all(_is_png(i["path"]) for i in out["images"])
    assert len(vmd_launches) == 1


@pytest.mark.requires_vmd
def test_vmd_driver_reports_ignored_views(real_vmd, real_tachyon, ubq,
                                          tmp_path):
    out = render.render_views(ubq, detection=detect_system(ubq),
                              views=("front", "bogus"), out_dir=str(tmp_path),
                              width=100, height=80, vmd_path=real_vmd)
    assert out["ok"] and out["ignored_views"] == ["bogus"]


@pytest.mark.requires_vmd
@pytest.mark.requires_ffmpeg
def test_movie_is_one_vmd_session_not_one_per_frame(
        real_vmd, real_tachyon, sample, tmp_path, vmd_launches):
    """A movie launches VMD once, not once per frame."""
    pdb, dcd = sample
    before = _leftovers("vmd_movie_frames_")
    out = render.render_movie(pdb, dcd, detection=detect_system(pdb, dcd),
                              out_mp4=str(tmp_path / "m.mp4"), stride=2,
                              width=160, height=120, vmd_path=real_vmd)
    assert out["ok"] and os.path.getsize(out["movie"]) > 0
    assert out["n_frames"] == 4 and out["source_frames"] == [0, 2, 4, 6]
    assert len(vmd_launches) == 1
    assert _leftovers("vmd_movie_frames_") == before


@pytest.mark.requires_vmd
def test_movie_without_ffmpeg_keeps_the_rendered_frames(
        real_vmd, real_tachyon, sample, tmp_path, monkeypatch):
    monkeypatch.setattr(render, "find_ffmpeg", lambda: None)     # as if there were no ffmpeg at all
    pdb, dcd = sample
    out = render.render_movie(pdb, dcd, detection=detect_system(pdb, dcd),
                              out_mp4=str(tmp_path / "m.mp4"), width=160,
                              height=120, vmd_path=real_vmd)
    assert not out["ok"] and "ffmpeg" in out["error"]
    try:
        assert len(os.listdir(out["frames_dir"])) == 8
    finally:
        shutil.rmtree(out["frames_dir"], ignore_errors=True)
