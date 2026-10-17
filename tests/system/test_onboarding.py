"""First-run experience: remembered settings, the guided setup, the menu, the installers.

The conversation is driven by a list of typed answers (what a person would type); every
tool the menu then runs is the real one. Nothing here pretends to be Ollama, Claude,
uv or GitHub: steps that need them are not exercised, and the installers are checked
statically only here; CI runs both installers on Linux, macOS and Windows runners, and the Claude registration steps have never been run."""
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
    rc = wizard.setup(io_, assume_yes=True, data_dir=str(folder), model_choice=5)
    assert rc == 0 and folder.is_dir()
    s = settings.load()
    assert s["data_dir"] == str(folder) and s["setup_done"] is True
    assert "All set" in io_.text and "vmd-agent" in io_.text


def test_setup_explains_the_steps_in_plain_words(tmp_path):
    io_ = Typed()
    wizard.setup(io_, assume_yes=True, data_dir=str(tmp_path), model_choice=5)
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
def test_local_model_without_ollama_explains_and_does_not_install_unasked(roomy):
    io_ = Typed(["1", "n", "n"])        # the suggestion, decline installing, decline the browser
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
    io_ = Typed(["n", "8"])                              # no setup, quit
    assert wizard.menu(io_) == 0
    assert "first time" in io_.text and "What would you like to do?" in io_.text


def test_the_menu_runs_a_real_check_of_a_statement(tmp_path):
    settings.save(data_dir=str(tmp_path), setup_done=True)
    shutil.copy(os.path.join(DATA, "1lyz.pdb"), tmp_path / "lysozyme.pdb")
    out = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, out
    try:
        wizard.menu(Typed(["5", "lysozyme.pdb", "It has 4 disulfide bridges", "8"]))
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
        wizard.menu(Typed(["4", "sample.pdb", "sample.dcd", "rgyr", "8"]))
    finally:
        sys.stdout = real_stdout
    assert "rgyr" in out.getvalue().lower()


def test_ending_the_input_stream_leaves_the_menu_cleanly(monkeypatch):
    settings.save(setup_done=True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert cli.main([]) == 130                           # plain `vmd-agent`, no keyboard


def test_the_menu_never_shows_a_traceback_for_a_bad_file(tmp_path):
    settings.save(data_dir=str(tmp_path), setup_done=True)
    io_ = Typed(["5", "missing.pdb", "It has a membrane", "8"])
    assert wizard.menu(io_) == 0


# ------------------------------------------------------------- help and docs
def test_every_command_has_a_plain_language_description():
    r = subprocess.run([sys.executable, "-m", "vmd_agent.cli", "--help"],
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONWARNINGS": "ignore"})
    out = r.stdout
    for cmd in ("setup", "chat", "doctor", "tools", "tool", "workflow", "mcp-config"):
        assert f"  {cmd} " in out or f"    {cmd} " in out, cmd
    assert "Just type  vmd-agent" in out and "First time?" in out


# ------------------------------------------------------------------ installers
@pytest.mark.skipif(SH is None, reason="no sh")
def test_install_script_parses():
    assert subprocess.run([SH, "-n", os.path.join(ROOT, "install", "install.sh")]).returncode == 0


@pytest.mark.parametrize("name", ["install.sh", "install.ps1"])
def test_the_installers_are_honest_and_conservative(name):
    s = open(os.path.join(ROOT, "install", name)).read()
    assert "STATUS:" in s and "NOT run by hand" in s       # says what is unverified
    assert "astral.sh/uv" in s                           # uv's official installer only
    import re
    assert not re.search(r"^\s*sudo\b", s, re.M)          # never runs sudo itself
    assert "rm -rf" not in s and "Remove-Item" not in s  # deletes nothing
    assert "AGENTIC_VMD_v2/archive/refs/heads/main.zip" in s    # no Git needed
    assert "vmd-agent[server] @" in s and "setup" in s


def test_the_one_line_installer_gives_the_setup_the_keyboard():
    s = open(os.path.join(ROOT, "install", "install.sh")).read()
    assert "< /dev/tty" in s                              # the script itself arrives on a pipe


def test_the_readme_install_lines_point_at_files_that_exist():
    readme = open(os.path.join(ROOT, "README.md")).read()
    for f in ("install.sh", "install.ps1"):
        assert f"main/install/{f}" in readme and os.path.exists(os.path.join(ROOT, "install", f))


def test_the_menu_opens_the_web_page_first():
    seen = []
    assert wizard.menu(Typed(["n", "1", "8"]), run_cli=lambda argv: seen.append(argv) or 0) == 0
    assert seen == [["ui"]]
    assert wizard.MENU[0].startswith("The web page") and wizard.MENU[-1] == "Quit"


def test_claude_code_is_an_alternative_to_a_model_not_an_extra_step(monkeypatch):
    """If a model runs here, nothing is registered with Claude Code unasked; Claude is one of the choices of who answers, and the menu has no step for it."""
    assert not hasattr(wizard, "offer_claude_code")
    assert not any("Claude" in item for item in wizard.MENU)
    from vmd_agent import claude_code
    monkeypatch.setattr(claude_code, "find", lambda refresh=False: "/x/claude")
    labels, default = wizard.assistant_choices()
    assert default == 1 and "recommended" in labels[0] and "found on this computer" in labels[3] and "instead" in labels[3]


def test_the_free_local_model_is_offered_first_unless_an_online_service_is_already_saved():
    labels, default = wizard.assistant_choices()
    assert default == 1 and "need its web address" in labels[2] and "API key" in labels[2]
    settings.save(llm_url="https://api.example.com/v1", llm_model="m")
    labels, default = wizard.assistant_choices()
    assert default == 3 and "api.example.com" in labels[2]
    settings.save(llm_url="http://localhost:11434/v1")                           # a server on this computer is not an online service
    assert wizard.assistant_choices()[1] == 1


def test_setup_names_the_computer_and_suggests_a_model_that_fits_it(monkeypatch, tmp_path):
    from vmd_agent import platform_info as P
    monkeypatch.setattr(P, "memory_gb", lambda s=None: 8.0)
    monkeypatch.setattr(P, "nvidia_gpu", lambda: None)
    monkeypatch.setattr(wizard, "_have_ollama", lambda: False)                  # stop after the choice: nothing is installed or started
    monkeypatch.setattr(wizard, "_install_ollama", lambda *a, **k: False)
    io_ = Typed([""])
    wizard.setup_local_model(io_, "linux")
    assert "8 GB of memory" in io_.text and "granite4.1:3b" in io_.text


# ------------------------------------------- vmd-agent's own data can live in the working folder
@pytest.fixture
def bare(monkeypatch):
    for k in (settings.ENV_DIR, settings.ENV_HOME):
        monkeypatch.delenv(k, raising=False)


def test_a_dot_folder_in_the_working_folder_holds_the_settings_and_the_window_link(tmp_path, monkeypatch, bare):
    work = tmp_path / "project"
    (work / "sub").mkdir(parents=True)
    monkeypatch.chdir(work / "sub")
    assert settings.local_home() is None and ".vmd-agent" not in settings.home_dir()
    folder = settings.make_local(str(work))
    assert folder == str(work / ".vmd-agent") and (work / ".vmd-agent" / ".gitignore").read_text().strip() == "*"
    assert settings.local_home() == os.path.realpath(folder)                 # found from a folder below it
    assert settings.home_dir() == os.path.realpath(folder) and settings.config_dir() == os.path.join(os.path.realpath(folder), "config")
    settings.save(data_dir=str(work))
    assert (work / ".vmd-agent" / "config" / "settings.json").is_file()
    from vmd_agent import ollama_local, vmdlink
    assert ollama_local.ollama_dir().startswith(os.path.realpath(folder)) and vmdlink._state_file().startswith(os.path.realpath(folder))


def test_the_environment_still_wins_over_the_working_folder(tmp_path, monkeypatch, bare):
    settings.make_local(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(settings.ENV_HOME, str(tmp_path / "elsewhere"))
    assert settings.home_dir() == str(tmp_path / "elsewhere")


def test_setup_can_keep_its_data_in_this_folder_and_carries_earlier_choices_over(tmp_path, monkeypatch, bare):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setattr("platform.system", lambda: "Linux")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    settings.save(vmd_path="/some/vmd")
    monkeypatch.setattr(wizard, "step_vmd", lambda *a, **k: None)        # whether this computer has a VMD must not matter here
    io_ = Typed()
    wizard.setup(io_, assume_yes=True, home="here", data_dir=str(work), model_choice=5)
    assert (work / ".vmd-agent" / "config" / "settings.json").is_file()
    s = settings.load()
    assert s["vmd_path"] == "/some/vmd" and s["data_dir"] == str(work)
    assert "Git ignores it" in io_.text
    again = Typed()
    wizard.step_home(again)
    assert "belongs to this working folder" in again.text


def test_the_tools_may_not_touch_the_data_folder_even_inside_the_files_folder(tmp_path, monkeypatch, bare):
    from vmd_agent import security
    settings.make_local(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(security.ENV_ROOTS, str(tmp_path))
    security.check_path(str(tmp_path / "1ubq.pdb"))
    with pytest.raises(security.SecurityError):
        security.check_path(str(tmp_path / ".vmd-agent" / "config" / "settings.json"))


def test_the_installers_folder_is_only_a_fallback_after_the_working_folder(tmp_path, monkeypatch, bare):
    inst, work = tmp_path / "inst", tmp_path / "work"
    inst.mkdir(); work.mkdir()
    monkeypatch.setenv(settings.ENV_INSTALL, str(inst))
    monkeypatch.chdir(work)
    assert settings.home_dir() == str(inst) and settings.config_dir() == str(inst / "config")
    folder = settings.make_local(str(work))
    assert settings.home_dir() == os.path.realpath(folder)


def test_setup_moves_the_model_and_settings_into_the_working_folder_only_when_agreed(tmp_path, monkeypatch, bare):
    inst, work = tmp_path / "inst", tmp_path / "work"
    (inst / "ollama" / "models").mkdir(parents=True); (inst / "ollama" / "models" / "blob").write_text("weights")
    (inst / "config").mkdir(); (inst / "config" / "settings.json").write_text('{"vmd_path": "/v"}')
    work.mkdir()
    monkeypatch.setenv(settings.ENV_INSTALL, str(inst))
    monkeypatch.chdir(work)
    monkeypatch.setattr(wizard, "_server_running", lambda: False)       # a model server running on this computer must not matter here
    no = Typed(["1", "n"])                                   # "in this folder", then decline the move
    wizard.step_home(no)
    assert (inst / "ollama").is_dir() and not (work / ".vmd-agent" / "ollama").exists()
    yes = Typed([""])
    wizard.step_home(yes)                                    # already a working folder: just offers the move
    assert (work / ".vmd-agent" / "ollama" / "models" / "blob").read_text() == "weights" and not (inst / "ollama").exists()
    assert (work / ".vmd-agent" / "config" / "settings.json").is_file() and "Moved" in yes.text
    from vmd_agent import ollama_local
    assert ollama_local.models_dir().startswith(os.path.realpath(work))


def test_a_running_model_server_is_never_moved(tmp_path, monkeypatch, bare):
    inst, work = tmp_path / "inst", tmp_path / "work"
    (inst / "ollama").mkdir(parents=True); work.mkdir()
    monkeypatch.setenv(settings.ENV_INSTALL, str(inst))
    monkeypatch.chdir(work)
    monkeypatch.setattr(wizard, "_server_running", lambda: True)
    io_ = Typed(["1", ""])
    wizard.step_home(io_)
    assert (inst / "ollama").is_dir() and "is running" in io_.text


# ------------------------------------------- saying no to a download is not final
def _local_setup_with_ollama_ready(monkeypatch, pulled):
    from vmd_agent import llm_client, ollama_local
    monkeypatch.setattr(wizard, "_have_ollama", lambda: True)
    monkeypatch.setattr(wizard, "_start_model_server", lambda io, url: True)
    monkeypatch.setattr(llm_client, "list_models", lambda *a, **k: [])
    monkeypatch.setattr(models, "check", lambda tag: {"tag": tag, "exists": True, "gb": 5.35, "tools": True, "error": ""})
    monkeypatch.setattr(ollama_local, "find_binary", lambda root=None: "/x/ollama")
    monkeypatch.setattr(ollama_local, "pull", lambda tag, on_line=None: pulled.append(tag) or True)
    monkeypatch.setattr(ollama_local, "installed_models", lambda root=None: list(pulled))
    monkeypatch.setattr(ollama_local, "free_gb", lambda path: 500.0)


def test_the_model_download_is_confirmed_with_its_size_and_a_no_says_how_to_do_it_later(monkeypatch, roomy):
    pulled = []
    _local_setup_with_ollama_ready(monkeypatch, pulled)
    io_ = Typed(["1", "n"])                                  # the suggestion (the 8B), then no to the download
    assert wizard.setup_local_model(io_, "linux") is False
    assert pulled == [] and settings.get("llm_model") == "granite4.1:8b"                     # the choice is kept
    assert "5.35 GB" in io_.text and "vmd-agent models --install granite4.1:8b" in io_.text and "web page" in io_.text


def test_a_model_declined_in_setup_can_be_downloaded_later_with_models_install(monkeypatch, capsys, roomy):
    pulled = []
    _local_setup_with_ollama_ready(monkeypatch, pulled)
    wizard.setup_local_model(Typed(["1", "n"]), "linux")
    assert cli.main(["models", "--install", "granite4.1:8b", "--yes"]) == 0
    assert pulled == ["granite4.1:8b"] and "Ready" in capsys.readouterr().out


def test_models_names_this_computer_and_what_suits_it(capsys):
    assert cli.main(["models"]) == 0
    out = capsys.readouterr().out
    assert "This computer:" in out and "Suggested:" in out and "vmd-agent models --install" in out


def test_setup_shows_how_each_model_suits_this_computer(monkeypatch):
    from vmd_agent import platform_info as P
    monkeypatch.setattr(P, "memory_gb", lambda s=None: 16.0)
    monkeypatch.setattr(P, "nvidia_gpu", lambda: None)
    monkeypatch.setattr(wizard, "_have_ollama", lambda: False)
    monkeypatch.setattr(wizard, "_install_ollama", lambda *a, **k: False)
    io_ = Typed([""])
    wizard.setup_local_model(io_, "linux")
    assert "suggested for this computer" in io_.text and "too big for this computer" in io_.text
    first = next(l for l in io_.text.splitlines() if l.strip().startswith("1."))
    assert "granite4.1:8b" in first and "suggested for this computer" in first          # the suggestion is number 1


def test_setup_never_makes_a_hidden_data_folder_in_your_home_directory(tmp_path, monkeypatch, bare):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv(settings.ENV_INSTALL, str(tmp_path / "inst"))
    monkeypatch.chdir(home)
    io_ = Typed()
    assert wizard.step_home(io_) == settings.home_dir() and not (home / ".vmd-agent").exists()
    assert "--home here" in io_.text                                   # and it says how to keep the data in a project instead


def test_after_the_installer_the_default_is_the_installers_folder(tmp_path, monkeypatch, bare):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv(settings.ENV_INSTALL, str(tmp_path / "inst"))
    monkeypatch.chdir(work)
    wizard.step_home(Typed([""]))                                      # just pressing Enter
    assert not (work / ".vmd-agent").exists()


def test_the_vmd_download_page_is_never_opened_without_a_yes_and_is_offered_only_once(monkeypatch):
    opened = []
    monkeypatch.setattr(wizard.webbrowser, "open", lambda u: opened.append(u))
    from vmd_agent import environment
    monkeypatch.setattr(environment, "find_vmd", lambda hint=None: None)
    wizard.step_vmd(Typed(["", ""]))                                  # not found; Enter for the folder; Enter for the page question
    assert opened == [] and settings.get("vmd_page_offered") is True
    io_ = Typed(["", "y"])
    wizard.step_vmd(io_)                                              # a second run does not ask about the page at all
    assert opened == [] and "Open VMD's download page" not in io_.text


def test_the_working_folders_data_is_still_found_after_the_program_changes_directory(tmp_path, monkeypatch, bare):
    """`vmd-agent ui` works inside the files folder. Before the folder was pinned, that made it lose the project's .vmd-agent and start a second set of settings and models."""
    project, files = tmp_path / "project", tmp_path / "elsewhere"
    project.mkdir(); files.mkdir()
    settings.make_local(str(project))
    monkeypatch.chdir(project)
    settings.pin()
    monkeypatch.chdir(files)
    assert settings.home_dir() == os.path.realpath(project / ".vmd-agent") and settings.config_dir().startswith(os.path.realpath(project))
    settings._PIN.clear()
    assert ".vmd-agent" not in settings.home_dir()                                    # without the pin the folder is lost, which is the bug


# ------------------------------------------- first-run answers that a new user really types
def test_the_files_folder_answer_can_be_a_file_or_a_place_that_cannot_be_made(tmp_path):
    a_file = tmp_path / "notes.txt"
    a_file.write_text("x")
    io_ = Typed([str(a_file), str(tmp_path / "ok")])               # a file first, then a real folder
    assert wizard.step_data_dir(io_) == str(tmp_path / "ok") and "is a file, not a folder" in io_.text
    io_ = Typed([str(a_file)] * 5)                                 # keeps giving a file: falls back, never a traceback
    folder = wizard.step_data_dir(io_)
    assert os.path.isdir(folder) and "Using" in io_.text
    blocked = tmp_path / "blocker"
    blocked.write_text("x")
    io_ = Typed([str(blocked / "inside"), str(tmp_path / "fine")])  # a folder under a file cannot be made
    assert wizard.step_data_dir(io_) == str(tmp_path / "fine") and "cannot make the folder" in io_.text


@pytest.mark.parametrize("address", ["7", "not a url", "api.example.com/v1", "ftp://x/v1"])
def test_an_online_service_address_that_is_not_a_web_address_is_refused_and_not_saved(address):
    io_ = Typed()
    assert wizard.setup_online_model(io_, address, "some-model", "k") is False
    assert "not a web address" in io_.text and settings.get("llm_url") is None


def test_a_listing_of_models_from_a_non_address_is_an_error_not_a_traceback():
    from vmd_agent import llm_client
    with pytest.raises(llm_client.LLMError, match="not a web address"):
        llm_client.list_models("7")


@pytest.fixture
def roomy(monkeypatch):
    """A computer with 24 GB of memory and no NVIDIA card: the 8B is the suggestion, so it is number 1 in the list."""
    from vmd_agent import platform_info as P
    monkeypatch.setattr(P, "memory_gb", lambda s=None: 24.0)
    monkeypatch.setattr(P, "nvidia_gpu", lambda: None)
    monkeypatch.setattr(P, "nvidia_vram_gb", lambda: None)


# ------------------------------------------- the model download: only models that can call tools, and a download that gives a plain answer when it cannot finish
def test_a_model_that_cannot_call_tools_is_refused_before_anything_is_downloaded(monkeypatch):
    pulled = []
    _local_setup_with_ollama_ready(monkeypatch, pulled)
    monkeypatch.setattr(models, "check", lambda tag: {"tag": tag, "exists": True, "gb": 0.29, "tools": False, "error": ""})
    io_ = Typed()
    assert wizard.setup_local_model(io_, "linux", model="gemma3:270m", assume_yes=True) is False
    assert pulled == [] and "cannot call tools" in io_.text and "Nothing was downloaded" in io_.text


def test_a_model_name_the_library_does_not_have_gets_suggestions_not_a_404(monkeypatch):
    pulled = []
    _local_setup_with_ollama_ready(monkeypatch, pulled)
    monkeypatch.setattr(models, "check", lambda tag: {"tag": tag, "exists": False, "gb": None, "tools": None, "error": "HTTP 404"})
    io_ = Typed()
    assert wizard.setup_local_model(io_, "linux", model="granit4:8b", assume_yes=True) is False
    assert pulled == [] and "no model called 'granit4:8b'" in io_.text and "granite4.1:3b" in io_.text and "404" not in io_.text


def test_a_download_stops_early_with_a_plain_message_when_the_disk_is_too_full(monkeypatch):
    pulled = []
    _local_setup_with_ollama_ready(monkeypatch, pulled)
    monkeypatch.setattr(ollama_local_module(), "free_gb", lambda path: 2.0)
    io_ = Typed()
    assert wizard.setup_local_model(io_, "linux", model="granite4.1:8b", assume_yes=True) is False
    assert pulled == [] and "Not enough free disk space" in io_.text and "2.0 GB free" in io_.text


def ollama_local_module():
    from vmd_agent import ollama_local
    return ollama_local


def test_a_dropped_connection_is_retried_and_resumes_but_a_wrong_name_is_not_retried(monkeypatch):
    from vmd_agent import ollama_local
    calls, shown = [], []
    monkeypatch.setattr(ollama_local.time, "sleep", lambda s: None)
    monkeypatch.setattr(ollama_local, "installed_models", lambda root=None: ["granite4.1:8b"] if len(calls) >= 3 else [])

    def flaky(tag, on_line=None):
        calls.append(tag)
        if len(calls) < 3:
            on_line("Error: connection reset by peer")
            return False
        on_line("success")
        return True
    monkeypatch.setattr(ollama_local, "pull", flaky)
    assert ollama_local.pull_model("granite4.1:8b", on_line=shown.append) == "" and len(calls) == 3
    assert any("trying again, it resumes" in s for s in shown)
    calls.clear()

    def wrong(tag, on_line=None):
        calls.append(tag)
        on_line("pull model manifest: file does not exist")
        return False
    monkeypatch.setattr(ollama_local, "pull", wrong)
    why = ollama_local.pull_model("nope:1b", on_line=lambda s: None)
    assert len(calls) == 1 and "no model called 'nope:1b'" in why                       # one try: another cannot help


def test_the_ollama_download_survives_a_renamed_file_and_a_refused_api(monkeypatch):
    import json
    import urllib.error
    from vmd_agent import ollama_local
    assert ollama_local.closest_asset("ollama-darwin.tgz", ["ollama-darwin.zip", "Ollama-darwin.tgz", "ollama-linux-amd64.tgz", "ollama-darwin-rocm.tgz"]) == "Ollama-darwin.tgz"
    assert ollama_local.closest_asset("ollama-linux-arm64.tar.zst", ["ollama-linux-amd64.tar.zst", "ollama-linux-arm64.tar.zst", "ollama-linux-arm64-jetpack5.tar.zst"]) == "ollama-linux-arm64.tar.zst"
    assert ollama_local.closest_asset("ollama-windows-amd64.zip", ["ollama-darwin.tgz"]) is None
    rel = [{"tag_name": "v9", "assets": [{"name": "Ollama-darwin.tgz", "browser_download_url": "http://x/Ollama-darwin.tgz", "size": 5}, {"name": "sha256sum.txt", "browser_download_url": "http://x/sums"}]}]
    monkeypatch.setattr(ollama_local, "_get", lambda u, timeout=30.0: json.dumps(rel).encode() if "api.github" in u else b"abc123  Ollama-darwin.tgz\n")
    got = ollama_local.latest_release("ollama-darwin.tgz")
    assert got["url"].endswith("Ollama-darwin.tgz") and got["sha256"] == "abc123"             # the renamed file, with its checksum

    def refuse(u, timeout=30.0):
        if "api.github" in u:
            raise urllib.error.HTTPError(u, 403, "rate limit exceeded", None, None)
        return b"def456  ollama-darwin.tgz\n"
    monkeypatch.setattr(ollama_local, "_get", refuse)
    again = ollama_local.latest_release("ollama-darwin.tgz")
    assert again["url"].startswith("https://github.com/ollama/ollama/releases/latest/download/") and again["sha256"] == "def456"


def _releases(*rels):
    import json
    return lambda u, timeout=30.0: json.dumps(list(rels)).encode() if "api.github" in u else b""


def test_the_ollama_checksum_comes_from_githubs_own_record_of_the_file_first(monkeypatch):
    from vmd_agent import ollama_local
    digest = "e" * 64
    rel = {"tag_name": "v9", "assets": [{"name": "ollama-darwin.tgz", "browser_download_url": "http://x/f", "size": 7, "digest": "sha256:" + digest}]}   # no sha256sum.txt at all
    monkeypatch.setattr(ollama_local, "_get", _releases(rel))
    assert ollama_local.latest_release("ollama-darwin.tgz")["sha256"] == digest


def test_a_release_still_being_published_is_passed_over_for_the_one_before_it(monkeypatch):
    from vmd_agent import ollama_local
    new = {"tag_name": "v10", "assets": [{"name": "ollama-darwin.tgz", "browser_download_url": "http://x/new", "size": 7}]}              # file uploaded, checksum not yet
    old = {"tag_name": "v9", "assets": [{"name": "ollama-darwin.tgz", "browser_download_url": "http://x/old", "size": 7, "digest": "sha256:" + "a" * 64}]}
    monkeypatch.setattr(ollama_local, "_get", _releases(new, old))
    got = ollama_local.latest_release("ollama-darwin.tgz")
    assert got["tag"] == "v9" and got["url"].endswith("/old") and got["sha256"] == "a" * 64


def test_when_no_recent_release_can_be_verified_the_message_says_what_to_do_instead(monkeypatch):
    from vmd_agent import ollama_local
    bare = {"tag_name": "v10", "assets": [{"name": "ollama-darwin.tgz", "browser_download_url": "http://x/new", "size": 7}]}
    monkeypatch.setattr(ollama_local, "_get", _releases(bare, bare))
    with pytest.raises(RuntimeError, match="https://ollama.com/download") as e:
        ollama_local.latest_release("ollama-darwin.tgz")
    assert "no checksum" in str(e.value) and "run `vmd-agent setup` again" in str(e.value)



# ---------------------------------------------------------------- your Claude account, online (through Claude Code)
def test_five_choices_and_a_saved_claude_account_is_not_taken_for_a_web_address(monkeypatch):
    """The saved 'claude-code:' was once offered as 'an online model service you already saved', which then asked for an address and a key."""
    from vmd_agent import claude_code
    monkeypatch.setattr(claude_code, "find", lambda refresh=False: None)
    labels, default = wizard.assistant_choices()
    assert len(labels) == 5 and wizard.CHOICES == ("local", "claude", "online", "app", "skip")
    assert "Your Claude account" in labels[1] and "no API key" in labels[1] and "API key" in labels[2] and labels[4].startswith("Skip")
    settings.save(llm_url=claude_code.URL, llm_model="claude-sonnet-5-5")
    labels, default = wizard.assistant_choices()
    assert default == 2 and "your current choice" in labels[1] and "claude-code" not in labels[2]


def _claude(monkeypatch, found="/x/claude", signed_in=True, installs="/home/u/.local/bin/claude"):
    from vmd_agent import claude_code
    state = {"found": found, "signed_in": signed_in, "installed": False, "signed": False}
    monkeypatch.setattr(claude_code, "find", lambda refresh=False: state["found"])
    monkeypatch.setattr(claude_code, "claude_version_of", lambda p: "9.9.9")

    def install(emit):
        emit("installing")
        state.update(installed=True, found=installs)
        return installs
    monkeypatch.setattr(claude_code, "install", install)
    monkeypatch.setattr(claude_code, "auth_status", lambda path=None, refresh=False: {"signed_in": state["signed_in"], "method": "claude.ai",
                                                                                      "email": "o@example.com" if state["signed_in"] else None, "plan": "pro"})

    def sign_in(path):
        state.update(signed=True, signed_in=True)
        return 0
    monkeypatch.setattr(wizard, "_claude_sign_in", sign_in)
    return state


def test_claude_account_signed_in_asks_only_for_the_model(monkeypatch):
    _claude(monkeypatch)
    io_ = Typed(["3"])                                                      # the third model in the list
    assert wizard.setup_claude_account(io_) is True
    from vmd_agent import claude_code
    assert settings.get("llm_url") == claude_code.URL and settings.get("llm_model") == claude_code.MODELS[2]["id"] and not settings.get("llm_key")
    assert "web address" not in io_.text and "API key (leave" not in io_.text and "Signed in to Claude (pro) as o@example.com" in io_.text


def test_claude_account_installs_claude_code_and_signs_in_when_asked(monkeypatch):
    state = _claude(monkeypatch, found=None, signed_in=False)
    io_ = Typed(["y", "y", ""])                                             # install: yes; sign in: yes; model: the default
    assert wizard.setup_claude_account(io_) is True
    assert state["installed"] and state["signed"] and "    installing" in io_.text and "password goes only to Claude" in io_.text
    assert "Claude Code's default model" in io_.text


def test_claude_account_without_claude_code_and_no_install_saves_nothing(monkeypatch):
    _claude(monkeypatch, found=None)
    io_ = Typed(["n"])
    assert wizard.setup_claude_account(io_) is False and not settings.get("llm_url")


def test_setup_with_the_claude_account_choice(monkeypatch, tmp_path):
    _claude(monkeypatch)
    from vmd_agent import claude_code
    rc = wizard.setup(Typed(), assume_yes=True, data_dir=str(tmp_path), model_choice=wizard.CHOICES.index("claude") + 1)
    assert rc == 0 and settings.get("llm_url") == claude_code.URL and settings.get("llm_model") == claude_code.DEFAULT
