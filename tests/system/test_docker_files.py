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
@pytest.mark.parametrize("script", ["entrypoint.sh", "install_vmd.sh"])
def test_shell_scripts_parse(script):
    assert subprocess.run([SH, "-n", os.path.join(DOCKER, script)]
                          ).returncode == 0


def test_dockerfile_stages_and_guarantees():
    d = _read("Dockerfile")
    for stage in ("AS base", "AS vmd-libs", "AS with-vmd", "AS runtime"):
        assert stage in d
    assert d.rstrip().splitlines()[-1].startswith("ENTRYPOINT")
    assert 'pip install ".[server]"' in d             # the MCP SDK is in the image
    # the default (last) stage is the open-source one: no VMD copied into it
    runtime = d.split("AS runtime")[1]
    assert "vmd-dist" not in runtime and "install_vmd" not in runtime
    assert 'redistributable="false"' in d             # with-vmd is labelled
    lines = [l.strip() for l in d.splitlines() if not l.strip().startswith("#")]
    assert not any("ANTHROPIC" in l or "API_KEY" in l for l in lines)   # no key baked in


def test_compose_services_are_hardened_and_carry_no_key():
    yaml = pytest.importorskip("yaml")
    c = yaml.safe_load(_read("docker-compose.yml"))
    s = c["services"]
    assert set(s) == {"vmd-agent", "hostvmd", "withvmd"}
    for name, svc in s.items():
        assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in svc["security_opt"], name
        assert "/home/vmdagent" in svc["tmpfs"], name              # VMD needs a writable HOME
    host = s["hostvmd"]
    assert any(v.endswith(":/opt/vmd:ro") for v in host["volumes"])
    assert any(v.endswith(":/data") for v in host["volumes"])
    assert host["environment"]["VMD_BIN"] == "/opt/vmd/bin/vmd"
    assert s["withvmd"]["image"] == "vmd-agent:vmd-local"
    assert host["platform"].startswith("${VMD_PLATFORM")
    text = _read("docker-compose.yml")
    assert "sk-ant" not in text and "ANTHROPIC" not in text       # nothing in the file carries a key, or asks for one


# ------------------------------------------------ the all-in-one chat stack
ROOT_DIR = os.path.abspath(ROOT)


def test_start_without_docker_says_what_to_install_and_does_nothing_else(capsys):
    from vmd_agent import launcher
    said = []
    assert launcher.start(mode="docker", docker="no-such-docker-binary", say=said.append) == 2
    assert "Docker is not installed" in " ".join(said) and "docs.docker.com" in " ".join(said)


def test_start_down_runs_compose_down(monkeypatch):
    from vmd_agent import launcher
    seen = []
    monkeypatch.setattr(launcher, "_run", lambda cmd, *a, **k: seen.append(cmd) or type("R", (), {"returncode": 0})())
    assert launcher.stop_docker() == 0
    assert seen[0][-1] == "down" and seen[0][1] == "compose"


def test_chat_compose_wires_the_model_server_to_the_chat_and_confines_it():
    yaml = pytest.importorskip("yaml")
    with open(os.path.join(DOCKER, "chat.compose.yml")) as fh:
        c = yaml.safe_load(fh)
    s = c["services"]
    assert s["ollama"]["image"].startswith("ollama/ollama")
    assert "ollama:/root/.ollama" in s["ollama"]["volumes"]        # models persist
    assert s["ollama"]["healthcheck"]["test"][-1] == "list"
    chat = s["vmd-agent"]
    assert chat["depends_on"]["ollama"]["condition"] == "service_healthy"
    env = chat["environment"]
    assert env["VMD_AGENT_LLM_URL"] == "http://ollama:11434/v1"
    assert env["VMD_AGENT_ALLOWED_ROOTS"] == "/data"               # sandbox on
    assert chat["command"] == ["chat"] and chat["tty"] and chat["stdin_open"]
    assert chat["read_only"] and chat["cap_drop"] == ["ALL"]
    assert any(v.endswith(":/data") for v in chat["volumes"])
    assert "${VMD_TARGET" in chat["build"]["target"]               # VMD optional
    assert "ollama" in c["volumes"]
    raw = open(os.path.join(DOCKER, "chat.compose.yml")).read()
    assert "sk-" not in raw and "API_KEY" not in raw               # no keys needed


def test_gpu_override_only_touches_the_model_server():
    yaml = pytest.importorskip("yaml")
    with open(os.path.join(DOCKER, "chat.gpu.yml")) as fh:
        g = yaml.safe_load(fh)
    assert list(g["services"]) == ["ollama"]
    dev = g["services"]["ollama"]["deploy"]["resources"]["reservations"]["devices"][0]
    assert dev["driver"] == "nvidia" and "gpu" in dev["capabilities"]


def test_start_never_downloads_vmd_and_is_honest_about_its_status():
    s = open(os.path.join(ROOT_DIR, "src", "vmd_agent", "launcher.py")).read()
    assert "Never run end to end" in s           # honest about its status
    assert "curl" not in s and "wget" not in s   # VMD's licence: the user downloads it
    assert "docker/vmd-dist" in s
