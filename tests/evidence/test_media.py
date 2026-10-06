"""Video evidence: QC, source-frame mapping, validation semantics."""
import os

import pytest
from vmd_agent.evidence import media


def test_qc_flags_blank_and_frozen_frames():
    fp = [10] * 1024
    other = [200] * 512 + [20] * 512
    frames = [{"index": 0, "path": "a", "stats": {"std": 0.1, "fingerprint": fp}},
              {"index": 1, "path": "b", "stats": {"std": 40, "fingerprint": other}},
              {"index": 2, "path": "c", "stats": {"std": 40, "fingerprint": other}}]
    q = media.qc_frames(frames)
    assert q["blank_frame_indices"] == [0] and q["frozen_frame_indices"] == [2]
    assert not q["passed"] and "Mechanical checks only" in q["note"]


def test_qc_without_pillow_stats_is_not_checked():
    q = media.qc_frames([{"index": 0, "path": "a"}])
    assert q["checked_frames"] == 0 and "skipped" in q["note"]


def test_map_to_source_frames_and_times():
    frames = [{"video_frame": 0}, {"video_frame": 10}]
    media.map_to_source(frames, fps=10, stride=40, first_frame=5,
                            time_per_frame=0.01, time_unit="ns")
    assert frames[1]["source_frame"] == 405 and frames[1]["sim_time"] == 4.05
    no_time = [{"video_frame": 3}]
    media.map_to_source(no_time, fps=10, stride=2)
    assert no_time[0]["source_frame"] == 6 and "sim_time" not in no_time[0]


def test_unset_expectations_are_not_checked_not_passed(monkeypatch):
    monkeypatch.setattr(media, "probe_video", lambda *a, **k: {
        "ok": True, "path": "v.mp4", "width": 100, "height": 50, "fps": 10.0,
        "n_frames": 20, "duration_s": 2.0,
        "decode_check": {"checked": True, "decodes": True}})
    r = media.validate_video("v.mp4", expect_width=100, expect_height=60)
    assert not r["ok"] and r["checks"]["width"]["passed"] is True
    assert r["checks"]["height"]["passed"] is False
    assert r["checks"]["fps"]["passed"] is None and not r["checks"]["fps"]["checked"]


def test_is_video_and_missing_input(tmp_path):
    assert media.is_video("a.MP4") and not media.is_video("a.png")
    assert media.interpret_video(str(tmp_path / "no.mp4"))["stage"] == "input"
    t = tmp_path / "x.txt"
    t.write_text("x")
    assert "not a recognised" in media.interpret_video(str(t))["error"]


def test_ffmpeg_filter_has_no_bare_backslash_escape_warning():
    import ast, warnings
    src = open(media.__file__).read()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ast.parse(src)


def _make_mp4(tmp_path):
    """A real 64x48, 10 fps, 3 s (30 frames) H.264 video made by the real ffmpeg."""
    import subprocess
    from vmd_agent.environment import find_ffmpeg
    mp4 = tmp_path / "v.mp4"
    subprocess.run([find_ffmpeg(), "-y", "-f", "lavfi", "-i",
                    "testsrc=size=64x48:rate=10:duration=3", "-pix_fmt",
                    "yuv420p", str(mp4)], capture_output=True, check=True)
    return mp4


@pytest.mark.requires_ffmpeg
def test_probe_reads_a_real_video_with_ffmpeg_alone(tmp_path, monkeypatch):
    """The bundled ffmpeg has no ffprobe; the probe must work without one."""
    mp4 = _make_mp4(tmp_path)
    real_which = media.shutil.which
    monkeypatch.setattr(media.shutil, "which", lambda n, *a, **k: None if n == "ffprobe" else real_which(n, *a, **k))
    info = media.probe_video(str(mp4), count_frames=True)
    assert info["ok"], info
    assert (info["width"], info["height"]) == (64, 48)
    assert info["codec"] == "h264" and info["pix_fmt"] == "yuv420p"
    assert abs(info["fps"] - 10) < 0.01 and abs(info["duration_s"] - 3) < 0.2
    assert info["n_frames"] == 30 and info["n_frames_exact"] is True
    assert "mp4" in info["container"] and info["size_bytes"] == os.path.getsize(mp4)
    assert info["decode_check"]["decodes"] is True


@pytest.mark.requires_ffmpeg
def test_find_ffmpeg_finds_one_without_a_system_install(monkeypatch):
    from vmd_agent import environment
    monkeypatch.setenv("PATH", "")
    exe = environment.find_ffmpeg()
    assert exe and os.path.isfile(exe)          # the copy bundled with imageio-ffmpeg


@pytest.mark.requires_ffmpeg
def test_real_ffmpeg_exact_frame_extraction(tmp_path):
    mp4 = _make_mp4(tmp_path)
    pkg = media.interpret_video(str(mp4), n_frames=5, out_dir=str(tmp_path / "o"))
    assert pkg["ok"] and len(pkg["frames"]) == 5
    assert pkg["frames"][-1]["video_frame"] == 29
    assert pkg["verification"]["frames_visually_inspected_by_agent"] is False
