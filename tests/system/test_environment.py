"""Locating VMD/Tachyon and probing the environment.

Tests of finding a *real* VMD are marked ``requires_vmd`` and skipped, with the
reason shown, where none is installed. Nothing here pretends to be VMD.
"""
import os

import pytest

from vmd_agent.auto import probe_environment
from vmd_agent.environment import find_tachyon, find_vmd, vmd_runtime_env

NO_REAL_VMD = pytest.mark.skipif(
    find_vmd() is not None,
    reason="a real VMD is installed here, so 'no VMD' cannot be tested")


@NO_REAL_VMD
def test_probe_without_vmd_still_offers_a_renderer(monkeypatch):
    monkeypatch.setenv("PATH", "")
    r = probe_environment("/nonexistent")
    assert not r["vmd_found"] and r["recommended_renderer"] == "matplotlib"
    assert r["can_render_any"]
    assert any("not bundled" in n for n in r["notes"])


@pytest.mark.requires_vmd
def test_a_real_vmd_is_found_and_its_version_read(real_vmd):
    assert os.access(real_vmd, os.X_OK)
    r = probe_environment(real_vmd)
    assert r["vmd_found"] and r["recommended_renderer"] == "vmd"
    assert r["vmd_version"] and r["vmd_version"] != "unknown"


@pytest.mark.requires_vmd
def test_find_vmd_honours_the_env_variable_and_a_hint(real_vmd, monkeypatch):
    assert find_vmd(real_vmd) == real_vmd
    monkeypatch.setenv("VMD_BIN", real_vmd)
    assert find_vmd() == real_vmd


@pytest.mark.requires_vmd
def test_vmd_bin_may_be_an_install_directory(real_vmd, monkeypatch):
    """Documented in the README: a directory is searched like an install dir."""
    monkeypatch.setenv("VMD_BIN", os.path.dirname(os.path.realpath(real_vmd)))
    found = find_vmd()
    assert found and os.access(found, os.X_OK)


@pytest.mark.requires_vmd
def test_real_tachyon_is_found_next_to_vmd(real_vmd):
    t = find_tachyon(real_vmd)
    assert t is None or os.access(t, os.X_OK)        # absent on some installs


def test_probe_reports_every_optional_analysis_library():
    from vmd_agent.environment import probe_environment as host_probe
    libs = host_probe()["analysis_libs"]
    for name in ("MDAnalysis", "freesasa", "numpy", "scipy", "matplotlib",
                 "mdtraj", "networkx", "pandas"):
        assert name in libs and isinstance(libs[name], bool)


def test_vmddir_is_derived_from_the_macos_app_layout(tmp_path):
    """VMD.app ships a bare vmd_MACOSX* binary beside scripts/ and plugins/ and
    relies on the app's startup script. Pure path logic over a real directory
    layout (no executable involved)."""
    app = tmp_path / "Applications" / "VMD 1.9.4.app" / "Contents" / "vmd"
    (app / "scripts").mkdir(parents=True)
    exe = str(app / "vmd_MACOSXARM64")
    assert vmd_runtime_env(exe, {})["VMDDIR"] == str(app)
    # a value the user already set is never overridden
    assert vmd_runtime_env(exe, {"VMDDIR": "/mine"})["VMDDIR"] == "/mine"
    # an ordinary launcher, or a directory that is not VMD's, is left alone
    assert "VMDDIR" not in vmd_runtime_env(str(tmp_path / "vmd"), {})
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert "VMDDIR" not in vmd_runtime_env(str(other / "vmd_x"), {})
