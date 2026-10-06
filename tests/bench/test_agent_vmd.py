"""Bring-your-own-VMD wiring: preflight, scrubbed environment, VMD-syntax scoring.

No stand-ins. What can be checked without VMD (environment scrubbing, input
screening before anything launches, preflight decisions, the manifest) runs
everywhere. What needs a real VMD is marked ``requires_vmd`` and is skipped, with
the reason shown, where none is installed; those tests have **never been run by
the author**, who has no VMD.
"""
import json
import os

import pytest
from conftest import DATA, UBQ_MD_DIR, no_real_vmd

from vmd_agent.bench.agent import preflight as pf
from vmd_agent.bench.agent import scoring, suite as S, tools
from vmd_agent.bench.agent.agents import OracleAgent
from vmd_agent.bench.agent.runner import run_agent_benchmark

BASE = {"id": "b0", "topology": os.path.join(UBQ_MD_DIR, "protein.pdb"),
        "trajectory": os.path.join(UBQ_MD_DIR, "protein.dcd")}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("vsuite")) + "/s"
    out = S.build_suite(d, [BASE], structures=[os.path.join(DATA, "4hhb.pdb")],
                        seed=5, families=["selection", "keyframes", "measure"])
    return d, out


def _task(built, kind):
    return next(t for t in built[1]["tasks"] if t["kind"] == kind)


# ---------------------------------------------------------------- env scrub
def test_sanitized_env_is_a_whitelist(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("VMDDIR", "/opt/vmd/lib")
    monkeypatch.setenv("LC_ALL", "C")
    env = tools.sanitized_env({"EXTRA": "1"})
    assert "ANTHROPIC_API_KEY" not in env and "GITHUB_TOKEN" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env["VMDDIR"] == "/opt/vmd/lib" and env["LC_ALL"] == "C"
    assert env["EXTRA"] == "1" and "PATH" in env


def test_model_written_python_cannot_read_the_api_key(built, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    t = _task(built, "rmsd_last")
    env = tools.Environment(t, "python_mdanalysis", allow_exec=True)
    out = env.call("run_python", {"code": (
        "import os; print(os.environ.get('ANTHROPIC_API_KEY', 'UNSET'))")})
    assert out["stdout"].strip() == "UNSET"


def test_model_written_python_runs_in_the_workspace(built):
    t = _task(built, "rmsd_last")
    env = tools.Environment(t, "python_mdanalysis", allow_exec=True)
    r = env.call("run_python", {"code": "import os;print(os.getcwd())"})
    assert os.path.realpath(r["stdout"].strip()) == os.path.realpath(
        t["workdir"])


def test_plain_vmd_arm_needs_exec_and_screens_scripts_before_any_launch(built):
    t = _task(built, "rmsd_last")
    off = tools.Environment(t, "vmd_plain")
    assert "run_vmd_tcl" not in {s["name"] for s in off.tool_specs()}
    on = tools.Environment(t, "vmd_plain", allow_exec=True)
    r = on.call("run_vmd_tcl", {"script": "exec rm -rf /tmp/x\n"})
    assert r.get("blocked") and "exec" in r["error"]


@pytest.mark.requires_vmd
def test_real_vmd_cannot_see_the_api_key_and_runs_in_the_workspace(
        built, real_vmd, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    t = _task(built, "rmsd_last")
    env = tools.Environment(t, "vmd_plain", allow_exec=True, vmd_path=real_vmd)
    r = env.call("run_vmd_tcl", {"script": (
        'puts "CWD=[pwd]"\n'
        'puts "KEY=[info exists env(ANTHROPIC_API_KEY)]"\n')})
    assert r["ok"], r
    cwd = [l for l in r["stdout"].splitlines() if l.startswith("CWD=")][0]
    assert os.path.realpath(cwd[4:]) == os.path.realpath(t["workdir"])
    assert "KEY=0" in r["stdout"]


# -------------------------------------------------- VMD-syntax selection scoring
def test_vmd_selection_input_is_confined_to_a_tcl_free_character_set(built):
    """Refused before VMD is ever launched, so this holds with or without VMD."""
    t = _task(built, "sidechain_range")
    tr = built[1]["truth"][t["id"]]
    for evil in ('all"; exec touch /tmp/pwned; "', "all [exec ls]",
                 "$env(HOME)", "name CA}\nputs hi", "name CA\n"):
        r = scoring.score_task(t, tr, {"selection": evil}, "vmd", None)
        assert not r["valid"] and "not allowed" in r["selection_error"], evil
    assert not os.path.exists("/tmp/pwned")


@no_real_vmd
def test_vmd_syntax_without_vmd_is_a_scored_failure_not_a_crash(built):
    t = _task(built, "sidechain_range")
    r = scoring.score_task(t, built[1]["truth"][t["id"]],
                           {"selection": "index 1"}, "vmd", None)
    assert not r["success"] and not r["valid"]


@pytest.mark.requires_vmd
def test_real_vmd_evaluates_selections_to_zero_based_indices(real_vmd, ubq):
    got = scoring.vmd_selected_indices(ubq, "index 0 1 2", real_vmd)
    assert got == {0, 1, 2}


@pytest.mark.requires_vmd
@pytest.mark.parametrize("selection", ["name CA", "resname GLY and name N",
                                       "resid 10 to 20 and name CA"])
def test_real_vmd_and_mdanalysis_agree_on_simple_selections(real_vmd, ubq,
                                                            selection):
    """The two selection engines the arms use must agree where the languages
    overlap, or the selection family would not be comparable across arms."""
    import MDAnalysis as mda
    mda_sel = selection.replace(" to ", ":").replace("resid ", "resid ") \
        if "resid" in selection else selection
    u = mda.Universe(ubq)
    want = {int(i) for i in u.select_atoms(mda_sel).indices}
    got = scoring.vmd_selected_indices(ubq, selection, real_vmd)
    assert got == want and want


@pytest.mark.requires_vmd
def test_oracle_scores_full_marks_when_a_real_vmd_scores_the_selections(
        built, real_vmd, tmp_path):
    r = run_agent_benchmark(
        built[0], [{"label": "o", "agent": OracleAgent(built[1]["truth"]),
                    "arm": "vmd_plain"}], str(tmp_path), allow_exec=True,
        vmd_path=real_vmd, families=["selection"], n_boot=0)
    assert r["summary"]["o"]["success"] == 1.0


def test_runner_uses_vmd_wording_for_the_plain_vmd_arm_only(built, tmp_path):
    seen = {}

    class Recorder:
        """A real agent that submits nothing; it records the prompt it was given."""
        name, scripted = "recorder", False

        def run(self, task, env):
            seen[task["id"]] = task["prompt"]
            return {}

    def prompts(arm, sub, exec_ok):
        seen.clear()
        run_agent_benchmark(built[0], [{"label": arm, "agent": Recorder(),
                                        "arm": arm}], str(tmp_path / sub),
                            allow_exec=exec_ok, families=["selection"],
                            n_boot=0)
        return dict(seen)
    plain = prompts("vmd_plain", "a", True)
    other = prompts("vmd_agent", "b", False)
    assert plain and all("VMD atom-selection string" in p
                         and "MDAnalysis" not in p for p in plain.values())
    assert other and all("MDAnalysis selection string" in p
                         for p in other.values())


def test_manifest_records_what_a_reader_needs_and_no_secrets(
        built, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-do-not-record-me")
    run_agent_benchmark(built[0], [{"label": "o", "agent": OracleAgent(
        built[1]["truth"]), "arm": "vmd_agent"}], str(tmp_path),
        families=["selection"], n_boot=0)
    m = json.load(open(tmp_path / "manifest.json"))
    assert len(m["suite_sha256"]) == 64 and m["runs"][0]["arm"] == "vmd_agent"
    assert m["toolkit_renderer"] in ("vmd", "matplotlib")
    assert isinstance(m["in_container"], bool) and m["vmd_agent_version"]
    blob = json.dumps(m)
    assert "sk-ant" not in blob and "API_KEY" not in blob


@pytest.mark.requires_vmd
def test_manifest_names_the_real_vmd_that_was_used(built, real_vmd, tmp_path,
                                                   monkeypatch):
    monkeypatch.setenv("VMD_BIN", real_vmd)
    run_agent_benchmark(built[0], [{"label": "o", "agent": OracleAgent(
        built[1]["truth"]), "arm": "vmd_agent"}], str(tmp_path),
        families=["selection"], n_boot=0)
    m = json.load(open(tmp_path / "manifest.json"))
    assert m["vmd_path"] == real_vmd and m["vmd_version"]
    assert m["toolkit_renderer"] == "vmd"


# ---------------------------------------------------------------- preflight
@no_real_vmd
def test_preflight_blocks_plain_vmd_without_vmd_but_not_other_arms():
    plain = pf.preflight(["vmd_plain"], allow_exec=True,
                         require_container=False)
    assert not plain["ready"] and "vmd_found" in plain["blocking"]
    other = pf.preflight(["vmd_agent"])
    assert other["ready"] and other["toolkit_renderer"] == "matplotlib"


def test_preflight_demands_the_exec_flag_for_code_arms():
    no_exec = pf.preflight(["python_mdanalysis"])
    assert not no_exec["ready"] and "code_execution" in no_exec["blocking"]


@pytest.mark.skipif(pf.in_container(), reason="this IS a container")
def test_preflight_refuses_model_written_code_outside_a_container():
    bare = pf.preflight(["python_mdanalysis"], allow_exec=True)
    assert not bare["ready"] and "container" in bare["blocking"]
    waived = pf.preflight(["python_mdanalysis"], allow_exec=True,
                          require_container=False)
    assert waived["ready"]


@pytest.mark.skipif(not pf.in_container(), reason="not inside a container")
def test_preflight_accepts_model_written_code_inside_a_container():
    assert pf.preflight(["python_mdanalysis"], allow_exec=True)["ready"]


def test_preflight_scrubbing_check_passes_for_a_real_child_process(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    r = pf.preflight(["python_mdanalysis"], allow_exec=True,
                     require_container=False)
    by = {c["name"]: c for c in r["checks"]}
    assert by["secrets_scrubbed"]["status"] == "ok"


def test_preflight_reports_the_key_without_revealing_or_calling_it(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = pf.preflight(["vmd_agent"], model="some-model")
    assert "api_key" in r["blocking"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-do-not-print-me")
    r = pf.preflight(["vmd_agent"], model="some-model")
    assert "sk-do-not-print-me" not in pf.report_text(r)
    call = next(c for c in r["checks"] if c["name"] == "api_call")
    assert call["status"] == "skip"           # never called without --live-api


@pytest.mark.requires_api
def test_preflight_live_api_check_reaches_the_real_api():
    r = pf.preflight(["vmd_agent"], model=os.environ.get(
        "VMD_AGENT_LIVE_MODEL", "claude-haiku-4-5-20251001"), live_api=True)
    call = next(c for c in r["checks"] if c["name"] == "api_call")
    assert call["status"] == "ok", call


def test_preflight_checks_suite_and_output_dir(built, tmp_path):
    ok = pf.preflight(["vmd_agent"], suite_dir=built[0],
                      out_dir=str(tmp_path / "o"))
    assert ok["ready"]
    bad = pf.preflight(["vmd_agent"], suite_dir=str(tmp_path / "none"))
    assert "suite" in bad["blocking"]
    with pytest.raises(ValueError, match="unknown arms"):
        pf.preflight(["nope"])


@pytest.mark.requires_vmd
def test_preflight_passes_with_a_real_vmd(real_vmd):
    r = pf.preflight(["vmd_plain"], vmd_path=real_vmd, allow_exec=True,
                     require_container=False)
    by = {c["name"]: c for c in r["checks"]}
    assert by["vmd_found"]["status"] == "ok", pf.report_text(r)
    assert by["vmd_smoke"]["status"] == "ok", pf.report_text(r)
    assert by["vmd_selection"]["status"] == "ok", pf.report_text(r)
    assert by["tachyon_internal"]["status"] in ("ok", "warn")
    assert r["toolkit_renderer"] == "vmd"


def test_cli_preflight_exit_codes(capsys):
    from vmd_agent import cli
    cli.main(["bench", "agent-preflight", "--arms", "vmd_agent"])
    assert "READY" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        cli.main(["bench", "agent-preflight", "--arms", "python_mdanalysis"])
    assert e.value.code == 2
