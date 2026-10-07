"""First-run experience: remembered settings, the guided setup, the menu, the installers.

The conversation is driven by a list of typed answers (what a person would type); every
tool the menu then runs is the real one. Nothing here pretends to be Ollama, Claude,
uv or GitHub: steps that need them are not exercised, and the installers are checked
statically only. The installers and the Ollama/Claude steps have NEVER been run."""
import io
import json
import os
import shutil
import socket
import stat
import subprocess
import sys

import pytest
from conftest import DATA, SAMPLE_DIR

from vmd_agent import cli, models, settings, wizard

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SH = shutil.which("sh")


class Typed(wizard.IO):
    """Keyboard input from a list; output collected."""

    def __init__(self, answers=()):
        self.answers, self.said = list(answers), []

    def say(self, msg=""):
        self.said.append(str(msg))

    def ask(self, prompt, default=None):
        a = self.answers.pop(0) if self.answers else ""
        return a or (default or "")

    def secret(self, prompt):
        return self.ask(prompt)

    @property
    def text(self):
        return "\n".join(self.said)


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ---------------------------------------------------------------- settings
def test_settings_are_remembered_and_unknown_keys_refused():
    assert settings.load() == {} and settings.get("data_dir", "x") == "x"
    settings.save(data_dir="/d", llm_model="m")
    assert settings.get("data_dir") == "/d" and settings.load()["llm_model"] == "m"
    settings.save(llm_model=None)
    assert "llm_model" not in settings.load()
    with pytest.raises(KeyError):
        settings.save(favourite_colour="red")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_the_settings_file_is_private_and_the_key_is_hidden_when_shown():
    settings.save(llm_key="sk-secret")
    assert stat.S_IMODE(os.stat(settings.path()).st_mode) == 0o600
    assert settings.describe()["llm_key"] == "(saved)"
    assert "sk-secret" not in json.dumps(settings.describe())


def test_a_broken_settings_file_is_ignored_not_fatal():
    os.makedirs(settings.config_dir(), exist_ok=True)
    with open(settings.path(), "w") as fh:
        fh.write("{not json")
    assert settings.load() == {}
    settings.save(data_dir="/ok")                         # and it recovers
    assert settings.get("data_dir") == "/ok"


def test_the_settings_folder_follows_each_operating_systems_convention():
    assert settings.config_dir("macos", "/Users/me", {}).endswith(
        os.path.join("Library", "Application Support", "vmd-agent"))
    assert "AppData" in settings.config_dir("windows", "C:/Users/me", {}) or \
        settings.config_dir("windows", "C:/Users/me", {"APPDATA": "C:/A"}).startswith("C:/A")
    assert settings.config_dir("linux", "/home/me", {}).endswith(
        os.path.join(".config", "vmd-agent"))
    assert settings.config_dir("linux", "/home/me", {"VMD_AGENT_CONFIG_DIR": "/x"}) == "/x"


def test_the_saved_files_folder_becomes_the_sandbox_and_the_saved_vmd_is_used(tmp_path):
    from vmd_agent import security
    assert security.allowed_roots() is None
    settings.save(data_dir=str(tmp_path))
    assert security.allowed_roots() == [os.path.realpath(str(tmp_path))]
    with pytest.raises(security.SecurityError):
        security.check_path("/etc/hosts")


def test_the_chat_picks_up_the_saved_model_without_flags(capsys, monkeypatch):
    for var in ("VMD_AGENT_LLM_URL", "VMD_AGENT_LLM_MODEL"):         # the environment would win over the saved values
        monkeypatch.delenv(var, raising=False)
    settings.save(llm_url=f"http://127.0.0.1:{_closed_port()}/v1", llm_model="mine")
    from vmd_agent import chat
    assert chat.main(prompt="hi") == 2                  # reaches the SAVED (dead) address
    assert "127.0.0.1" in capsys.readouterr().out


# ------------------------------------------------------------------- the setup
def test_setup_with_defaults_creates_the_folder_and_remembers_everything(tmp_path):
    io_ = Typed()
    folder = tmp_path / "my files"
    rc = wizard.setup(io_, assume_yes=True, data_dir=str(folder), model_choice=4)
    assert rc == 0 and folder.is_dir()
    s = settings.load()
    assert s["data_dir"] == str(folder) and s["setup_done"] is True
    assert "All set" in io_.text and "vmd-agent" in io_.text


def test_setup_explains_the_steps_in_plain_words(tmp_path):
    io_ = Typed()
    wizard.setup(io_, assume_yes=True, data_dir=str(tmp_path), model_choice=4)
    for phrase in ("Step 1 of 4", "Step 2 of 4", "Step 3 of 4", "Step 4 of 4",
                   "installs nothing without asking", "can only see that folder"):
        assert phrase in io_.text, phrase


def test_when_vmd_is_missing_setup_says_it_is_optional_and_where_to_get_it():
    from vmd_agent.environment import find_vmd
    if find_vmd():
        pytest.skip("a real VMD is installed here")
    io_ = Typed(["", "n"])                               # Enter to skip, no browser
    assert wizard.step_vmd(io_) is None
    assert "fine" in io_.text and "ks.uiuc.edu" in io_.text


def test_a_wrong_vmd_folder_is_reported_kindly_not_saved(tmp_path):
    from vmd_agent.environment import find_vmd
    if find_vmd():
        pytest.skip("a real VMD is installed here")
    io_ = Typed([str(tmp_path), "n"])
    assert wizard.step_vmd(io_) is None
    assert "could not find a VMD program" in io_.text and "vmd_path" not in settings.load()


@pytest.mark.requires_vmd
def test_a_real_vmd_is_found_and_remembered(real_vmd):
    io_ = Typed()
    assert wizard.step_vmd(io_) == real_vmd and settings.get("vmd_path") == real_vmd


def test_online_model_details_are_saved_privately_and_checked(tmp_path):
    url = f"http://127.0.0.1:{_closed_port()}/v1"
    io_ = Typed()
    assert wizard.setup_online_model(io_, url, "some-model", "sk-abc")
    assert settings.get("llm_model") == "some-model" and settings.get("llm_key") == "sk-abc"
    assert "could not confirm" in io_.text and "sk-abc" not in io_.text   # key never echoed
    assert not wizard.setup_online_model(Typed(), "", "", "")           # incomplete: nothing saved


@pytest.mark.skipif(shutil.which("ollama") is not None,
                    reason="Ollama is installed here; this would try to use it")
def test_local_model_without_ollama_explains_and_does_not_install_unasked():
    io_ = Typed(["2", "n", "n"])        # size 2, decline installing, decline the browser
    ok = wizard.setup_local_model(io_, "linux")
    assert ok is False
    assert settings.get("llm_model") == models.DEFAULT_MODEL
    assert "ollama.com" in io_.text and "saved your choice" in io_.text


def test_connecting_to_claude_desktop_merges_and_backs_up(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))            # so nothing real is touched
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    from vmd_agent import platform_info as P
    system = P.system()
    cfg = P.claude_desktop_config_path(system)
    if cfg is None:
        pytest.skip("Claude Desktop has no config location on this OS")
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    with open(cfg, "w") as fh:
        json.dump({"mcpServers": {"other": {"command": "x"}}}, fh)
    io_ = Typed(["y", "n"])                              # yes Desktop, no Claude Code
    folder = tmp_path / "data"
    folder.mkdir()
    assert wizard.setup_ai_app(io_, str(folder), system_name=system)
    data = json.load(open(cfg))
    assert "other" in data["mcpServers"] and "vmd-agent" in data["mcpServers"]
    assert os.path.exists(cfg + ".vmd-agent.bak") and "Restart Claude Desktop" in io_.text


def test_status_shows_each_setting_and_whether_the_model_answers(tmp_path):
    settings.save(data_dir=str(tmp_path), llm_url=f"http://127.0.0.1:{_closed_port()}/v1",
                  llm_model="m")
    io_ = Typed()
    assert wizard.show_status(io_) == 0
    assert str(tmp_path) in io_.text and "NOT reachable" in io_.text
    assert wizard.setup(Typed(), check_only=True) == 0


# -------------------------------------------------------------------- the menu
def test_the_menu_quits_and_offers_setup_on_a_first_visit():
    io_ = Typed(["n", "9"])                              # no setup, quit
    assert wizard.menu(io_) == 0
    assert "first time" in io_.text and "What would you like to do?" in io_.text


def test_the_menu_runs_a_real_check_of_a_statement(tmp_path):
    settings.save(data_dir=str(tmp_path), setup_done=True)
    shutil.copy(os.path.join(DATA, "1lyz.pdb"), tmp_path / "lysozyme.pdb")
    out = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, out
    try:
        wizard.menu(Typed(["5", "lysozyme.pdb", "It has 4 disulfide bridges", "9"]))
    finally:
        sys.stdout = real_stdout
    assert "supported" in out.getvalue()                 # the real verifier ran


def test_the_menu_runs_a_real_analysis_on_files_in_the_users_folder(tmp_path):
    settings.save(data_dir=str(tmp_path), setup_done=True)
    for f in ("sample.pdb", "sample.dcd"):
        shutil.copy(os.path.join(SAMPLE_DIR, f), tmp_path / f)
    out = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, out
    try:
        wizard.menu(Typed(["4", "sample.pdb", "sample.dcd", "rgyr", "9"]))
    finally:
        sys.stdout = real_stdout
    assert "rgyr" in out.getvalue().lower()


def test_ending_the_input_stream_leaves_the_menu_cleanly(monkeypatch):
    settings.save(setup_done=True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert cli.main([]) == 130                           # plain `vmd-agent`, no keyboard


def test_the_menu_never_shows_a_traceback_for_a_bad_file(tmp_path):
    settings.save(data_dir=str(tmp_path), setup_done=True)
    io_ = Typed(["5", "missing.pdb", "It has a membrane", "9"])
    assert wizard.menu(io_) == 0


# ------------------------------------------------------------- help and docs
def test_every_command_has_a_plain_language_description():
    r = subprocess.run([sys.executable, "-m", "vmd_agent.cli", "--help"],
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONWARNINGS": "ignore"})
    out = r.stdout
    for cmd in ("setup", "chat", "doctor", "probe", "inspect", "analyze", "visualize",
                "claims", "show", "mcp-config"):
        assert f"  {cmd} " in out or f"    {cmd} " in out, cmd
    assert "Just type  vmd-agent" in out and "First time?" in out


# ------------------------------------------------------------------ installers
@pytest.mark.skipif(SH is None, reason="no sh")
def test_install_script_parses():
    assert subprocess.run([SH, "-n", os.path.join(ROOT, "install.sh")]).returncode == 0


@pytest.mark.parametrize("name", ["install.sh", "install.ps1"])
def test_the_installers_are_honest_and_conservative(name):
    s = open(os.path.join(ROOT, name)).read()
    assert "NEVER RUN" in s                              # says what is unverified
    assert "astral.sh/uv" in s                           # uv's official installer only
    import re
    assert not re.search(r"^\s*sudo\b", s, re.M)          # never runs sudo itself
    assert "rm -rf" not in s and "Remove-Item" not in s  # deletes nothing
    assert "AGENTIC_VMD_v2/archive/refs/heads/main.zip" in s    # no Git needed
    assert "vmd-agent[server] @" in s and "setup" in s


def test_the_one_line_installer_gives_the_setup_the_keyboard():
    s = open(os.path.join(ROOT, "install.sh")).read()
    assert "< /dev/tty" in s                              # the script itself arrives on a pipe


def test_the_readme_install_lines_point_at_files_that_exist():
    readme = open(os.path.join(ROOT, "README.md")).read()
    for f in ("install.sh", "install.ps1"):
        assert f"main/{f}" in readme and os.path.exists(os.path.join(ROOT, f))


def test_the_menu_opens_the_web_page_first():
    seen = []
    assert wizard.menu(Typed(["n", "1", "9"]), run_cli=lambda argv: seen.append(argv) or 0) == 0
    assert seen == [["ui"]]
    assert wizard.MENU[0].startswith("The web page") and wizard.MENU[-1] == "Quit"
