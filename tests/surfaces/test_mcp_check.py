"""`vmd-agent mcp-check`: launches the real server and talks to it with the real
MCP client over stdio, exactly as an MCP client would. Needs the real SDK."""
import os

import pytest

pytestmark = pytest.mark.requires_mcp

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def _by_name(res):
    return {c["name"]: c for c in res["checks"]}


def test_a_good_configuration_is_ready_and_sandbox_is_verified():
    from vmd_agent.mcp_check import check_mcp_server, report_text
    res = check_mcp_server(roots=[DATA])
    by = _by_name(res)
    assert res["ready"], report_text(res)
    assert by["connect"]["status"] == "ok" and by["tools"]["status"] == "ok"
    assert by["sandbox"]["status"] == "ok" and "inside" in by["sandbox"]["detail"]
    assert by["raw_tcl_tool"]["status"] == "ok" and "disabled" in by[
        "raw_tcl_tool"]["detail"]
    assert "READY" in report_text(res)


def test_no_sandbox_is_a_warning_not_a_pass():
    from vmd_agent.mcp_check import check_mcp_server
    by = _by_name(check_mcp_server())
    assert by["sandbox"]["status"] == "warn" and "OFF" in by["sandbox"]["detail"]


def test_a_missing_root_is_a_failure(tmp_path):
    from vmd_agent.mcp_check import check_mcp_server
    res = check_mcp_server(roots=[str(tmp_path / "does_not_exist")])
    assert not res["ready"] and _by_name(res)["sandbox"]["status"] == "fail"


def test_a_wrong_command_fails_with_a_useful_message():
    from vmd_agent.mcp_check import check_mcp_server
    res = check_mcp_server(command="/nonexistent/vmd-agent-server", args=[])
    c = _by_name(res)["connect"]
    assert not res["ready"] and c["status"] == "fail"
    assert "stdout" in c["detail"] and "nonexistent" in c["detail"]


def test_the_server_only_gets_the_environment_it_is_given(monkeypatch):
    """A real client does not forward your shell: VMD_BIN set only in this
    process must NOT reach the server unless passed explicitly."""
    from vmd_agent.mcp_check import check_mcp_server
    monkeypatch.setenv("VMD_BIN", "/definitely/not/a/vmd")
    by = _by_name(check_mcp_server(roots=[DATA]))
    assert "/definitely/not/a/vmd" not in by["vmd"]["detail"]


def test_cli_exit_codes(capsys):
    from vmd_agent import cli
    assert cli.main(["mcp-check", "--roots", DATA]) == 0
    assert "READY" in capsys.readouterr().out
    assert cli.main(["mcp-check", "--roots", "/nonexistent/dir"]) == 2


def test_the_client_config_follows_the_saved_settings_and_the_contained_folder(tmp_path, monkeypatch):
    """Found in a clean-room install: the server (started by a client) saw none of the saved settings."""
    from vmd_agent import mcp_check, settings
    monkeypatch.setenv("VMD_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("VMD_AGENT_CONFIG_DIR", raising=False)
    settings.save(data_dir=str(tmp_path / "files"))
    env = mcp_check.build_mcp_config(vmd=str(tmp_path / "vmd"))["config"]["mcpServers"]["vmd-agent"]["env"]
    assert env["VMD_AGENT_HOME"] == str(tmp_path / "home")
    assert env["VMD_AGENT_ALLOWED_ROOTS"].endswith("files")                 # the folder chosen in setup is the sandbox
    given = mcp_check.build_mcp_config(roots=[str(tmp_path / "other")], vmd=str(tmp_path / "vmd"))
    assert given["config"]["mcpServers"]["vmd-agent"]["env"]["VMD_AGENT_ALLOWED_ROOTS"].endswith("other")
