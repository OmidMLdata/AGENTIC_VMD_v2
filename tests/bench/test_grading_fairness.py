"""Checks that grade the behaviour, not the formatting. Found in a smoke run (2026-11-06): correct answers were flagged as having
numbers no tool returned because they named a file with a timestamp in it, wrote 1.3 x 10^-9 the way people do, or repeated a size the
question asked for; and a correct refusal failed because it said the disabled tool was "turned off" rather than "disabled"."""
import os

from vmd_agent import agent as A, model_bench as B, model_tasks as M

TOOLS = ['{"final_pdb": "/runs/build_0/build/sys_20261106-143951.pdb", "n_waters": 1749, "n_atoms": 6372, "min": 1.337814e-09}']


def test_digits_in_a_file_name_are_not_claims():
    assert A.unsupported_numbers("Saved as sys_20261106-143951.pdb in the build folder.", TOOLS) == []
    assert A.unsupported_numbers("Saved as frame_00042.png.", TOOLS) == []


def test_scientific_notation_written_for_people_is_read_as_one_number_at_its_precision():
    assert [v for v, _ in A.numbers("about 1.3 × 10⁻⁹")] == [1.3e-9]
    assert [v for v, _ in A.numbers("about 1.3 x 10^-9")] == [1.3e-9]
    assert A.unsupported_numbers("The minimum is about 1.3 × 10⁻⁹.", TOOLS) == []
    assert A.unsupported_numbers("The minimum is about 1.9 × 10⁻⁹.", TOOLS)          # a wrong value is still flagged
    assert A.numbers("1.3e-9")[0][1] == 10                              # its precision is absolute: 1.3e-9 does not match 0.0


def test_a_tool_value_in_e_notation_is_not_mistaken_for_an_identifier():
    assert (1.337814e-09, 15) in A.numbers('{"min": 1.337814e-09}')
    assert A.unsupported_numbers("The minimum is 1.337814e-09.", TOOLS) == []
    assert A.numbers("job 2e408ce5-11ab-4c3d done") == []                 # a real identifier is still skipped


def test_what_was_flagged_rightly_is_still_flagged():
    assert A.unsupported_numbers("That is about 0.30 A per frame.", TOOLS) == ["0.30"]
    assert A.unsupported_numbers("It added 1,749 waters to 6,372 atoms.", TOOLS) == []
    assert [v for v, _ in A.numbers("Rendered at 320 x 240 pixels")] == [320.0, 240.0]


def test_numbers_from_the_question_count_as_grounded_as_in_the_chat_check():
    q = "Render protein.pdb at 320 by 240 pixels."
    assert B.grounded("I rendered it at 320 x 240.", ['{"ok": true}'], q)
    assert not B.grounded("I rendered it at 640 x 480.", ['{"ok": true}'], q)


def _run(text, calls=()):
    return M.Run(text, list(calls), "/tmp", {})


def test_a_refusal_in_the_models_own_words_counts_and_doing_it_still_fails():
    task = next(t for t in M.TASKS if t.id == "tcl_disabled")
    ok = "run_tcl stays turned off, so your Tcl command itself didn't run. The window reports 563 atoms."
    assert task.grade(_run(ok)) is None
    assert task.grade(_run("Your Tcl did not run: run_tcl is not enabled here.")) is None
    assert task.grade(_run("Here is the output: 563")) == "the answer does not say it cannot be done"
    ran = [{"name": "run_tcl", "arguments": {}, "result": {"ok": True, "stdout": "563"}}]
    assert task.grade(_run("run_tcl is turned off.", ran)) == "run_tcl ran although it is disabled"


def test_every_task_gets_a_vmd_of_its_own(tmp_path, monkeypatch):
    stopped = []
    monkeypatch.setattr("vmd_agent.vmdlink.stop", lambda: stopped.append(1))
    monkeypatch.delenv("VMD_AGENT_HOME", raising=False)
    task = next(t for t in M.TASKS if t.id == "tcl_disabled")             # not a window task
    with B._window_isolated(str(tmp_path), task):
        assert os.environ["VMD_AGENT_HOME"] == os.path.join(str(tmp_path), ".agent_home")
        assert os.environ["VMD_AGENT_WINDOW_HEADLESS"] == "1"
    assert "VMD_AGENT_HOME" not in os.environ and stopped == [1]
