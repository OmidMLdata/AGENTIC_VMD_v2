"""OS awareness. The rules for each OS are pure functions of the OS name, checked here
for Linux, macOS and Windows from whatever OS the tests run on (no pretend programs);
probes of the real machine are checked for shape and for never raising. Behaviour on a
real Windows or Linux machine is NOT verified by the author, who has only a Mac."""
import io
import json
import ntpath
import os
import sys

import pytest

from vmd_agent import launcher, mcp_check, platform_info as P, security


# ------------------------------------------------------------------- basics
@pytest.mark.parametrize("raw,want", [("Darwin", "macos"), ("macOS", "macos"),
                                      ("Windows", "windows"), ("win32", "windows"),
                                      ("Linux", "linux"), ("FreeBSD", "freebsd")])
def test_the_os_name_is_normalised(raw, want):
    assert P.system(raw) == want


@pytest.mark.parametrize("raw,want", [("x86_64", "amd64"), ("AMD64", "amd64"),
                                      ("arm64", "arm64"), ("aarch64", "arm64"),
                                      ("riscv64", "riscv64")])
def test_the_cpu_is_normalised_and_picks_the_docker_platform(raw, want):
    assert P.arch(raw) == want
    assert P.docker_platform(raw) == ("linux/arm64" if want == "arm64" else "linux/amd64")


def test_the_real_machine_is_described_without_raising():
    info = P.detect(docker="no-such-docker-binary")
    assert info["system"] in ("linux", "macos", "windows") or info["system"]
    assert info["docker"]["installed"] is False and info["docker"]["running"] is False
    assert isinstance(info["wsl"], bool) and isinstance(info["in_container"], bool)
    assert info["docker_platform"].startswith("linux/")


def test_running_a_missing_program_reports_it_instead_of_raising():
    assert P.run(["definitely-not-a-program-xyz"]) == (127, "")


# ----------------------------------------------------- where things live, per OS
def test_vmd_search_locations_per_os():
    win = P.vmd_search_dirs("windows", home="C:/Users/me",
                            env={"PROGRAMFILES": "C:\\Program Files",
                                 "LOCALAPPDATA": "C:\\Users\\me\\AppData\\Local"})
    assert any("University of Illinois/VMD*" in d for d in win)
    assert not any("\\" in d for d in win)                      # glob-safe slashes
    mac = P.vmd_search_dirs("macos", home="/Users/me")
    assert "/Applications/VMD*.app/Contents/vmd" in mac
    assert "/Users/me/Applications/VMD*.app/Contents/vmd" in mac
    lin = P.vmd_search_dirs("linux", home="/home/me")
    assert "/opt/vmd" in lin and "/home/me/Software" in lin


def test_vmd_file_names_per_os():
    assert P.vmd_executable_names("windows")[0] == "vmd.exe"
    assert "vmd_MACOSXARM64" in P.vmd_executable_names("macos")
    assert P.vmd_executable_names("linux")[0] == "vmd"


def test_claude_desktop_config_location_per_os():
    assert P.claude_desktop_config_path("macos", home="/Users/me") == os.path.join(
        "/Users/me", "Library", "Application Support", "Claude", "claude_desktop_config.json")
    win = P.claude_desktop_config_path("windows", home="C:/Users/me",
                                       env={"APPDATA": "C:\\Users\\me\\AppData\\Roaming"})
    assert win.endswith("claude_desktop_config.json") and "Claude" in win
    assert P.claude_desktop_config_path("linux", home="/home/me") is None


def test_docker_install_pages_differ_by_os():
    urls = {s: P.docker_install_url(s) for s in ("macos", "windows", "linux")}
    assert len(set(urls.values())) == 3 and "mac" in urls["macos"]


# ---------------------------------------------------------------- advice per OS
def _info(system, arch="amd64", installed=True, running=True, compose=True,
          nvidia=None, runtime=False, ollama=False, container=False):
    return {"system": system, "arch": arch, "wsl": False, "in_container": container,
            "python": "3.12", "apple_silicon": system == "macos" and arch == "arm64",
            "docker": {"installed": installed, "running": running, "compose": compose,
                       "nvidia_runtime": runtime},
            "docker_platform": P.docker_platform(arch), "nvidia_gpu": nvidia,
            "ollama": ollama, "claude_desktop_config": None}


def test_advice_for_a_mac_explains_the_vmd_and_gpu_limits_when_docker_is_there():
    text = " ".join(P.advice(_info("macos", "arm64")))
    assert "cannot run inside Docker" in text and "cannot use the Mac's GPU" in text
    assert "arm64" in text


def test_docker_notes_stay_out_of_the_way_when_docker_is_absent():
    text = " ".join(P.advice(_info("macos", "arm64", installed=False, running=False, compose=False)))
    assert "Docker is not installed. That is fine" in text and "cannot run inside Docker" not in text


def test_advice_for_windows_and_linux_and_a_stopped_docker():
    assert "Windows VMD cannot run inside Docker" in " ".join(P.advice(_info("windows")))
    assert "No NVIDIA GPU" in " ".join(P.advice(_info("linux")))
    stopped = " ".join(P.advice(_info("macos", running=False)))
    assert "not running" in stopped
    nv = " ".join(P.advice(_info("linux", nvidia="NVIDIA RTX 4090", runtime=False)))
    assert "NVIDIA Container Toolkit" in nv


# --------------------------------------------------- Windows / case-insensitive rules
def test_windows_paths_are_compared_case_insensitively_and_by_backslash():
    n, sep = ntpath.normcase, "\\"
    assert security.is_within("C:\\Data\\Run1\\a.pdb", "c:\\data", n, sep)
    assert security.is_within("C:\\DATA", "c:\\data", n, sep)
    assert not security.is_within("C:\\Data-evil\\a.pdb", "C:\\Data", n, sep)   # sibling
    assert not security.is_within("D:\\Data\\a.pdb", "C:\\Data", n, sep)        # other drive


def test_posix_paths_stay_case_sensitive():
    assert security.is_within("/data/a.pdb", "/data", lambda x: x, "/")
    assert not security.is_within("/Data/a.pdb", "/data", lambda x: x, "/")


def test_windows_paths_become_tcl_safe_forward_slashes():
    assert security.tcl_path("C:\\Users\\me\\run 1\\a.pdb", windows=True) == \
        "C:/Users/me/run 1/a.pdb"
    assert security.tcl_path("\\\\server\\share\\a.pdb", windows=True).startswith("//server/share")
    with pytest.raises(security.SecurityError):                 # braces still refused
        security.tcl_path("C:\\x}\\a.pdb", windows=True)


def test_on_posix_a_backslash_in_a_path_is_still_refused():
    with pytest.raises(security.SecurityError):
        security.tcl_path("/data/a\\b.pdb", windows=False)


def test_windows_system_variables_reach_model_written_code(monkeypatch):
    """Without SYSTEMROOT and friends, programs often will not start on Windows."""
    from vmd_agent.bench.agent import tools
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    env = tools.sanitized_env()
    assert env["SYSTEMROOT"] == "C:\\Windows" and "ANTHROPIC_API_KEY" not in env


def test_vmd_version_check_no_longer_depends_on_dev_stdin():
    """/dev/stdin does not exist on Windows; the version script now goes in a file."""
    import inspect
    from vmd_agent import environment
    assert "/dev/stdin" not in inspect.getsource(environment)


def test_a_console_that_cannot_show_a_character_does_not_crash_printing(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="ascii")
    monkeypatch.setattr(sys, "stdout", stream)
    P.console_safe()
    print("RMSD 1.4 \u00c5 \u2014 done")                       # would raise before
    stream.flush()
    assert b"RMSD 1.4" in raw.getvalue()


# ------------------------------------------------------------------- the plan
def test_linux_with_docker_and_an_nvidia_runtime_runs_in_docker_with_the_gpu(tmp_path):
    info = _info("linux", nvidia="NVIDIA A100", runtime=True)
    plan = launcher.make_plan(info, "m", "data", str(tmp_path), "auto")
    assert plan["mode"] == "docker" and not plan["problems"]
    assert any(a.endswith("chat.gpu.yml") for a in plan["compose"])
    assert plan["env"]["VMD_TARGET"] == "runtime" and plan["env"]["MODEL"] == "m"
    assert any("NVIDIA A100" in n for n in plan["notes"])


def test_a_mac_with_ollama_runs_natively_because_of_its_vmd_and_gpu():
    plan = launcher.make_plan(_info("macos", "arm64", ollama=True), "m", "data", None, "auto")
    assert plan["mode"] == "native" and "VMD" in plan["reason"]
    assert any("GPU" in n for n in plan["notes"])


def test_a_mac_with_only_docker_uses_docker_and_says_it_will_be_slow(tmp_path):
    plan = launcher.make_plan(_info("macos", "arm64"), "m", "data", str(tmp_path), "auto")
    assert plan["mode"] == "docker"
    assert any("cannot use the Mac's GPU" in n for n in plan["notes"])


def test_windows_data_paths_are_given_to_docker_with_forward_slashes(tmp_path):
    assert launcher.compose_data_dir("C:\\Users\\me\\data", "windows") == "C:/Users/me/data"
    plan = launcher.make_plan(_info("windows"), "m", "C:\\Users\\me\\data", str(tmp_path), "auto")
    assert plan["mode"] == "docker" and "\\" not in plan["env"]["DATA_DIR"]


def test_a_vmd_tarball_selects_the_vmd_image_and_warns_on_arm(tmp_path):
    plan = launcher.make_plan(_info("macos", "arm64"), "m", "data", str(tmp_path), "docker",
                              tarball="vmd-1.9.4.bin.LINUXAMD64.tar.gz")
    assert plan["env"]["VMD_TARGET"] == "with-vmd"
    assert any("arm64" in n and "Linux ARM64" in n for n in plan["notes"])
    assert any("Never share" in n for n in plan["notes"])


def test_with_nothing_installed_the_plan_says_what_to_install():
    plan = launcher.make_plan(_info("windows", installed=False, running=False, compose=False),
                              "m", "data", None, "auto")
    assert plan["mode"] == "none" and plan["problems"]
    text = " ".join(plan["problems"])
    assert "docs.docker.com" in text and "ollama.com" in text


def test_docker_not_running_is_a_problem_not_a_crash(tmp_path):
    plan = launcher.make_plan(_info("linux", running=False), "m", "data", str(tmp_path), "docker")
    assert plan["problems"] and any("not running" in p for p in plan["problems"])


def test_a_missing_checkout_is_reported(tmp_path):
    plan = launcher.make_plan(_info("linux"), "m", "data", None, "docker")
    assert any("docker/chat.compose.yml" in p for p in plan["problems"])
    with pytest.raises(ValueError):
        launcher.make_plan(_info("linux"), "m", "data", None, "sideways")


def test_the_checkout_and_the_vmd_tarball_are_found_on_disk(tmp_path):
    (tmp_path / "docker" / "vmd-dist").mkdir(parents=True)
    (tmp_path / "docker" / "chat.compose.yml").write_text("services: {}\n")
    assert launcher.find_repo(str(tmp_path / "docker" / "vmd-dist")) == str(tmp_path)
    assert launcher.vmd_tarball(str(tmp_path)) is None
    (tmp_path / "docker" / "vmd-dist" / "vmd-1.9.4.tar.gz").write_bytes(b"x")
    assert launcher.vmd_tarball(str(tmp_path)).endswith("vmd-1.9.4.tar.gz")
    assert launcher.find_repo(str(tmp_path.parent / "elsewhere")) in (None, str(tmp_path.parent))


def test_start_print_plan_runs_on_this_machine_and_runs_nothing(capsys):
    rc = launcher.start(print_plan=True, docker="no-such-docker-binary")
    out = capsys.readouterr().out
    assert "This computer:" in out and "Plan:" in out
    assert rc in (0, 2)                                    # 2 = nothing installed here


def test_doctor_describes_this_machine(capsys):
    from vmd_agent import cli
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    for key in ("System:", "Docker:", "VMD:", "Ollama:"):
        assert key in out
    assert cli.main(["doctor", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["system"] and "next_steps" in data


# ---------------------------------------------------------------- MCP config
def test_mcp_config_per_os_uses_that_os_conventions():
    mac = mcp_check.build_mcp_config(["/Users/me/data"], "/Applications/VMD.app/x", "macos",
                                     "/Users/me/venv/bin/vmd-agent-server")
    s = mac["config"]["mcpServers"]["vmd-agent"]
    assert s["command"].endswith("vmd-agent-server") and s["env"]["VMD_BIN"].startswith("/Applications")
    assert "Application Support" in mac["claude_desktop_config"]
    assert mac["claude_code_command"][:4] == ["claude", "mcp", "add", "vmd-agent"]
    win = mcp_check.build_mcp_config(["C:\\data", "D:\\more"], "C:\\VMD\\vmd.exe", "windows",
                                     "C:\\venv\\Scripts\\vmd-agent-server.exe")
    assert win["config"]["mcpServers"]["vmd-agent"]["env"]["VMD_AGENT_ALLOWED_ROOTS"] == "C:\\data;D:\\more"
    lin = mcp_check.build_mcp_config(None, None, "linux", "/v/bin/vmd-agent-server")
    assert lin["claude_desktop_config"] is None
    assert any("sandbox would be OFF" in n for n in lin["notes"])


def test_writing_claude_desktop_config_merges_and_keeps_a_backup(tmp_path):
    path = tmp_path / "Claude" / "claude_desktop_config.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"theme": "dark",
                                "mcpServers": {"other": {"command": "x"}}}))
    block = mcp_check.build_mcp_config(["/d"], None, "macos", "/v/vmd-agent-server")["config"]
    backup = mcp_check.write_claude_desktop_config(str(path), block)
    data = json.loads(path.read_text())
    assert data["theme"] == "dark" and data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["vmd-agent"]["command"] == "/v/vmd-agent-server"
    assert json.loads(open(backup).read())["mcpServers"] == {"other": {"command": "x"}}


def test_writing_creates_a_missing_config_and_refuses_a_broken_one(tmp_path):
    block = mcp_check.build_mcp_config(["/d"], None, "macos", "/v/s")["config"]
    new = tmp_path / "new" / "claude_desktop_config.json"
    assert mcp_check.write_claude_desktop_config(str(new), block) == ""
    assert "vmd-agent" in json.loads(new.read_text())["mcpServers"]
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        mcp_check.write_claude_desktop_config(str(broken), block)
    assert broken.read_text() == "{not json"                  # untouched
