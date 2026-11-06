"""A conda ffmpeg on the PATH without libx264 was taken over the bundled one, so every movie failed ("Unknown encoder 'libx264'")."""
from vmd_agent import environment as E


def _setup(monkeypatch, on_path, bundled, h264):
    monkeypatch.setattr(E, "_which", lambda name: on_path)
    monkeypatch.setattr(E, "_bundled_ffmpeg", lambda: bundled)
    monkeypatch.setattr(E, "_encodes_h264", lambda exe: exe in h264)


def test_an_ffmpeg_that_cannot_encode_h264_gives_way_to_the_bundled_one(monkeypatch):
    _setup(monkeypatch, "/conda/bin/ffmpeg", "/venv/imageio/ffmpeg", {"/venv/imageio/ffmpeg"})
    assert E.find_ffmpeg() == "/venv/imageio/ffmpeg"


def test_a_capable_ffmpeg_on_the_path_is_still_preferred(monkeypatch):
    _setup(monkeypatch, "/usr/local/bin/ffmpeg", "/venv/imageio/ffmpeg", {"/usr/local/bin/ffmpeg", "/venv/imageio/ffmpeg"})
    assert E.find_ffmpeg() == "/usr/local/bin/ffmpeg"


def test_without_h264_anywhere_an_ffmpeg_is_still_returned_for_reading_videos(monkeypatch):
    _setup(monkeypatch, "/conda/bin/ffmpeg", None, set())
    assert E.find_ffmpeg() == "/conda/bin/ffmpeg"
    _setup(monkeypatch, None, None, set())
    assert E.find_ffmpeg() is None
