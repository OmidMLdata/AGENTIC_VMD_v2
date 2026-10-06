"""Containment (everything in one folder), the model catalogue, and the VMD self-test.

Real files, real archives and a real local HTTP server are used. Nothing is downloaded
from the internet except in the tests marked ``requires_network``."""
import http.server
import io
import json
import os
import shutil
import tarfile
import threading
import zipfile

import pytest

from vmd_agent import environment, models, ollama_local, settings

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


# ------------------------------------------------------------ one folder for everything
def test_the_home_folder_holds_settings_and_downloads():
    env = {"VMD_AGENT_HOME": "/x/vmd-agent"}
    assert settings.config_dir(env=env) == os.path.join("/x/vmd-agent", "config")
    assert settings.home_dir(env=env) == "/x/vmd-agent"


def test_an_explicit_config_dir_still_wins():
    env = {"VMD_AGENT_HOME": "/x/h", "VMD_AGENT_CONFIG_DIR": "/y/c"}
    assert settings.config_dir(env=env) == "/y/c"


@pytest.mark.parametrize("system,expect", [("linux", ".local"), ("darwin", "Application Support"),
                                           ("windows", "AppData")])
def test_without_a_home_folder_each_os_gets_its_usual_data_place(system, expect):
    assert expect in settings.home_dir(system, home="/h", env={})


def test_the_model_server_is_told_to_keep_everything_inside_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_HOME", str(tmp_path))
    env = ollama_local.server_env({"PATH": "/bin"})
    assert env["OLLAMA_MODELS"].startswith(str(tmp_path))
    assert env["OLLAMA_HOST"].startswith("127.0.0.1:")          # not reachable from other computers
    assert ollama_local.port() != 11434                         # never collides with a system Ollama


@pytest.mark.parametrize("system,machine,name", [
    ("darwin", "arm64", "ollama-darwin.tgz"), ("darwin", "x86_64", "ollama-darwin.tgz"),
    ("linux", "x86_64", "ollama-linux-amd64.tar.zst"), ("linux", "aarch64", "ollama-linux-arm64.tar.zst"),
    ("windows", "AMD64", "ollama-windows-amd64.zip"), ("windows", "arm64", "ollama-windows-arm64.zip")])
def test_the_right_standalone_archive_is_chosen_for_each_os_and_cpu(system, machine, name):
    assert ollama_local.asset_name(system, machine) == name
    assert name in ollama_local.APPROX_GB


def test_checksums_are_read_from_the_release_file():
    txt = "AA11  ollama-darwin.tgz\nbb22 *ollama-windows-amd64.zip\n"
    assert ollama_local.checksum_for(txt, "ollama-darwin.tgz") == "aa11"
    assert ollama_local.checksum_for(txt, "ollama-windows-amd64.zip") == "bb22"
    assert ollama_local.checksum_for(txt, "missing.zip") is None


def test_file_sha256_matches_hashlib(tmp_path):
    import hashlib
    p = tmp_path / "f"
    p.write_bytes(b"abc" * 1000)
    assert ollama_local.file_sha256(str(p)) == hashlib.sha256(b"abc" * 1000).hexdigest()


def test_extract_zip_and_tgz_and_refuse_paths_that_escape(tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("bin/ollama", "x")
    ollama_local.extract(str(z), str(tmp_path / "z"))
    assert (tmp_path / "z" / "bin" / "ollama").read_text() == "x"

    t = tmp_path / "a.tgz"
    with tarfile.open(t, "w:gz") as f:
        info = tarfile.TarInfo("ollama")
        info.size = 1
        f.addfile(info, io.BytesIO(b"x"))
    ollama_local.extract(str(t), str(tmp_path / "t"))
    assert (tmp_path / "t" / "ollama").exists()

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as f:
        f.writestr("../escape.txt", "no")
    with pytest.raises(RuntimeError):
        ollama_local.extract(str(bad), str(tmp_path / "b"))
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.skipif(shutil.which("zstd") is None or shutil.which("tar") is None,
                    reason="needs the zstd and tar programs to build a real .tar.zst")
def test_extract_tar_zst(tmp_path):
    import subprocess
    src = tmp_path / "src"
    (src / "bin").mkdir(parents=True)
    (src / "bin" / "ollama").write_text("x")
    arc = tmp_path / "a.tar.zst"
    subprocess.run(["tar", "--use-compress-program=zstd", "-cf", str(arc), "-C", str(src), "."], check=True)
    ollama_local.extract(str(arc), str(tmp_path / "out"))
    assert (tmp_path / "out" / "bin" / "ollama").exists()


def test_find_binary_looks_inside_the_folder_but_not_in_the_models(tmp_path):
    (tmp_path / "models").mkdir()
    sneaky = tmp_path / "models" / "ollama"
    sneaky.write_text("x"); sneaky.chmod(0o755)
    assert ollama_local.find_binary(str(tmp_path)) is None
    (tmp_path / "bin").mkdir()
    real = tmp_path / "bin" / ("ollama.exe" if os.name == "nt" else "ollama")
    real.write_text("x"); real.chmod(0o755)
    assert ollama_local.find_binary(str(tmp_path)) == str(real)


def test_install_never_runs_without_a_checksum(monkeypatch, tmp_path):
    monkeypatch.setenv("VMD_AGENT_HOME", str(tmp_path))
    monkeypatch.setattr(ollama_local, "latest_release",
                        lambda name: {"tag": "t", "url": "http://x", "size": 1, "sha256": None})
    with pytest.raises(RuntimeError, match="checksum"):
        ollama_local.install()


@pytest.mark.parametrize("name", ["install.sh", "install.ps1"])
def test_the_installers_confine_uv_to_one_folder(name):
    s = open(os.path.join(ROOT, name)).read()
    for var in ("UV_INSTALL_DIR", "UV_UNMANAGED_INSTALL", "UV_NO_MODIFY_PATH", "UV_CACHE_DIR",
                "UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "UV_PYTHON_INSTALL_DIR", "VMD_AGENT_HOME"):
        assert var in s, var
    assert "update-shell" not in s                    # never edits the shell's startup files


# ------------------------------------------------------------------ the model catalogue
def test_the_catalogue_is_consistent():
    tags = [m.tag for m in models.CATALOGUE]
    assert len(tags) == len(set(tags))
    assert models.DEFAULT_MODEL in tags
    assert all(m.gb > 0 and m.licence for m in models.CATALOGUE)
    assert models.MODELS_CHECKED in models.table()


def test_the_readme_lists_exactly_the_catalogue_with_its_date():
    readme = open(os.path.join(ROOT, "README.md")).read()
    assert models.MODELS_CHECKED in readme
    for m in models.CATALOGUE:
        assert f"`{m.tag}`" in readme, m.tag


class _Registry(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/granite/manifests/8b":
            body = json.dumps({"layers": [{"size": 3_000_000_000}, {"size": 500_000_000}]}).encode()
            self.send_response(200)
        else:
            body, _ = b"{}", self.send_response(404)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_check_tells_exists_from_missing_from_unreachable():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Registry)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        ok = models.check("granite:8b", registry=base)
        assert ok["exists"] is True and ok["gb"] == 3.5
        assert models.check("nope:1b", registry=base)["exists"] is False
    finally:
        srv.shutdown()
    assert models.check("granite:8b", timeout=1, registry="http://127.0.0.1:9")["exists"] is None


@pytest.mark.requires_network
@pytest.mark.parametrize("tag", [m.tag for m in models.CATALOGUE])
def test_every_catalogue_model_exists_in_the_live_ollama_registry(tag):
    r = models.check(tag)
    if r["exists"] is None:
        pytest.skip("the Ollama registry could not be reached: " + str(r["error"]))
    assert r["exists"] is True, f"{tag} is no longer in the Ollama library; update models.py"
    m = next(c for c in models.CATALOGUE if c.tag == tag)
    assert abs(r["gb"] - m.gb) < max(0.3, 0.05 * m.gb), f"{tag}: registry says {r['gb']} GB, catalogue {m.gb}"


# --------------------------------------------------------------------- the VMD self-test
@pytest.mark.skipif(shutil.which("false") is None, reason="no 'false' program")
def test_a_program_that_is_not_vmd_fails_the_self_test_with_a_reason():
    r = environment.vmd_self_test(shutil.which("false"))
    assert r["ok"] is False and r["problem"] and r["advice"]


def test_a_missing_file_fails_the_self_test_without_raising(tmp_path):
    r = environment.vmd_self_test(str(tmp_path / "nope"))
    assert r["ok"] is False and "could not be started" in r["problem"]


@pytest.mark.requires_vmd
def test_real_vmd_passes_the_self_test():
    r = environment.vmd_self_test(environment.find_vmd())
    assert r["ok"] is True and r["version"]


def test_models_command_prints_the_dated_table(capsys):
    from vmd_agent import cli
    assert cli.main(["models"]) == 0
    out = capsys.readouterr().out
    assert models.MODELS_CHECKED in out and models.DEFAULT_MODEL in out


# ------------------------------------------------------------------ the VMD version policy
def test_no_version_is_claimed_tested_without_evidence():
    # a version is listed only after the real-VMD tests passed against it (1.9.4a57, 2026-10-06)
    assert environment.VMD_VERSIONS_TESTED == ("1.9.4a57",)
    assert "tested with this toolkit" in environment.vmd_version_note("1.9.4a57")
    other = environment.vmd_version_note("1.9.3")
    assert "not been tested with this version" in other and "outside" not in other


@pytest.mark.parametrize("v", ["2.0.0a3", "1.8.7", "2.1"])
def test_a_version_outside_the_targeted_series_is_flagged(v):
    assert "outside that series" in environment.vmd_version_note(v)


def test_an_unreadable_version_is_said_so():
    assert "could not be read" in environment.vmd_version_note(None)


def test_the_readme_says_which_vmd_version_and_that_none_was_tested():
    r = open(os.path.join(ROOT, "README.md")).read()
    assert "## Which VMD version?" in r and "1.9.x" in r and "1.9.4a57" in r and "Not tested:" in r
