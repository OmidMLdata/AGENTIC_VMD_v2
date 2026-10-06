"""Static checks of the Docker wiring. Docker is not run here; these catch the
mistakes that can be caught without it (syntax, structure, secrets, guarantees
the docs make)."""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DOCKER = os.path.join(ROOT, "docker")
SH = shutil.which("sh")


def _read(*p):
    with open(os.path.join(DOCKER, *p)) as fh:
        return fh.read()


@pytest.mark.skipif(SH is None, reason="no sh")
@pytest.mark.parametrize("script", ["entrypoint.sh", "install_vmd.sh",
                                    "bench.sh"])
def test_shell_scripts_parse(script):
    assert subprocess.run([SH, "-n", os.path.join(DOCKER, script)]
                          ).returncode == 0


def test_dockerfile_stages_and_guarantees():
    d = _read("Dockerfile")
    for stage in ("AS base", "AS vmd-libs", "AS with-vmd", "AS runtime"):
        assert stage in d
    assert d.rstrip().splitlines()[-1].startswith("ENTRYPOINT")
    assert 'pip install ".[server,bench]"' in d       # the SDK is in the image
    # the default (last) stage is the open-source one: no VMD copied into it
    runtime = d.split("AS runtime")[1]
    assert "vmd-dist" not in runtime and "install_vmd" not in runtime
    assert 'redistributable="false"' in d             # with-vmd is labelled
    lines = [l.strip() for l in d.splitlines() if not l.strip().startswith("#")]
    assert not any("ANTHROPIC" in l for l in lines)   # no key baked in


def test_compose_services_secrets_and_hardening():
    yaml = pytest.importorskip("yaml")
    c = yaml.safe_load(_read("docker-compose.yml"))
    s = c["services"]
    for name in ("bench", "bench-hostvmd", "bench-withvmd"):
        svc = s[name]
        assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in svc["security_opt"]
        assert svc["pids_limit"] and svc["mem_limit"]
        env = svc["environment"]
        assert "ANTHROPIC_API_KEY" in env             # by name, no value
        assert not any(str(e).startswith("ANTHROPIC_API_KEY=") for e in env)
        assert "/home/vmdagent" in svc["tmpfs"]       # VMD needs a writable HOME
    host = s["bench-hostvmd"]
    assert any(v.endswith(":/opt/vmd:ro") for v in host["volumes"])
    assert any(v.endswith(":/data") for v in host["volumes"])
    assert "VMD_BIN=/opt/vmd/bin/vmd" in host["environment"]
    assert s["bench-withvmd"]["image"] == "vmd-agent:vmd-local"
    assert host["platform"].startswith("${VMD_PLATFORM")
    # nothing in the file carries a literal key
    assert "sk-ant" not in _read("docker-compose.yml")


@pytest.mark.skipif(SH is None or shutil.which("file") is None,
                    reason="needs sh and file")
def test_bench_script_refuses_a_macos_vmd_for_a_linux_container(tmp_path):
    home = tmp_path / "vmd"
    (home / "bin").mkdir(parents=True)
    exe = home / "bin" / "vmd"
    exe.write_bytes(b"\xcf\xfa\xed\xfe\x07\x00\x00\x01\x03\x00\x00\x00"
                    b"\x02\x00\x00\x00" + b"\x00" * 16)
    exe.chmod(0o755)
    r = subprocess.run([SH, os.path.join(DOCKER, "bench.sh"), "check-vmd"],
                       env={**os.environ, "MODE": "hostvmd",
                            "VMD_HOME": str(home)},
                       capture_output=True, text=True)
    assert r.returncode == 1 and "macOS binary" in r.stderr
    exe.write_text("#!/bin/sh\necho hi\n")
    ok = subprocess.run([SH, os.path.join(DOCKER, "bench.sh"), "check-vmd"],
                        env={**os.environ, "MODE": "hostvmd",
                             "VMD_HOME": str(home)},
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "found" in ok.stdout
    missing = subprocess.run([SH, os.path.join(DOCKER, "bench.sh"),
                              "check-vmd"],
                             env={**os.environ, "MODE": "hostvmd",
                                  "VMD_HOME": str(tmp_path / "none")},
                             capture_output=True, text=True)
    assert missing.returncode == 1


@pytest.mark.skipif(SH is None, reason="no sh")
def test_bench_script_rejects_unknown_mode_and_command():
    for env, args in (({"MODE": "nope"}, ["run"]), ({}, ["frobnicate"])):
        r = subprocess.run([SH, os.path.join(DOCKER, "bench.sh"), *args],
                           env={**os.environ, **env}, capture_output=True,
                           text=True)
        assert r.returncode == 2
