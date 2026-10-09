"""`vmd-agent chat`: the tool loop's real parts. The full conversation needs a
model, so it is a live test (``requires_llm``); everything else runs real tools."""
import json
import os

import pytest

from vmd_agent import agent, chat

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def _session(echo=None):
    return agent.Agent("http://127.0.0.1:1/v1", "m", echo=echo)


def test_the_agent_is_confined_to_the_current_directory_by_default(
        tmp_path, monkeypatch):
    monkeypatch.delenv("VMD_AGENT_ALLOWED_ROOTS", raising=False)
    monkeypatch.chdir(tmp_path)
    roots = agent.ensure_roots()
    assert roots == [os.path.realpath(str(tmp_path))]
    assert os.environ["VMD_AGENT_ALLOWED_ROOTS"] == roots[0]


def test_configured_roots_are_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    assert agent.ensure_roots() == [os.path.realpath(str(tmp_path))]


def test_a_tool_call_runs_a_real_tool_and_returns_json_text():
    s = _session()
    out = json.loads(s.run_tool({"id": "1", "name": "detect_system", "arguments": {
        "topology": os.path.join(DATA, "1ubq.pdb")}}))
    assert out["components"]["protein"]["n_residues"] == 76


def test_the_sandbox_applies_to_the_model(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    out = json.loads(_session().run_tool({"id": "1", "name": "detect_system",
                                          "arguments": {"topology": "/etc/hosts"}}))
    assert out["blocked"] and "allowed roots" in out["error"]


def test_a_model_that_misuses_a_tool_is_told_how_to_use_it():
    s = _session()
    unknown = json.loads(s.run_tool({"id": "1", "name": "rm_everything", "arguments": {}}))
    assert "unknown tool" in unknown["error"] and "detect_system" in unknown["available"]
    bad = json.loads(s.run_tool({"id": "2", "name": "detect_system",
                                 "arguments": {"wrong": 1}}))
    assert "bad arguments" in bad["error"] and "topology" in bad["parameters"]
    assert bad["required"] == ["topology"]
    garbled = json.loads(s.run_tool({"id": "3", "name": "detect_system", "arguments": {},
                                     "arguments_error": "arguments were not a JSON object"}))
    assert "not a JSON object" in garbled["error"]


def test_tool_activity_is_shown_to_the_user():
    seen = []
    _session(seen.append).run_tool({"id": "1", "name": "probe_environment",
                                    "arguments": {}})
    assert any("probe_environment" in m for m in seen)


def test_old_tool_results_are_dropped_first_to_fit_a_context_window():
    s = agent.Agent("http://x/v1", "m", max_history_chars=3000)
    s.messages += [{"role": "user", "content": "q"},
                   {"role": "tool", "content": "A" * 2500, "tool_call_id": "1", "name": "t"},
                   {"role": "tool", "content": "B" * 2500, "tool_call_id": "2", "name": "t"}]
    s._trim()
    assert "omitted" in s.messages[2]["content"]         # oldest shrunk first
    assert s.messages[0]["role"] == "system" and s.messages[1]["content"] == "q"


def test_the_system_prompt_states_the_rules_that_matter():
    p = agent.SYSTEM_PROMPT
    for must in ("Never invent a number", "verify_claims", "cannot see images",
                 "damaged"):
        assert must in p


def test_an_unreachable_model_server_is_a_clear_message_and_exit_code_2(capsys, tmp_path):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    rc = chat.main(base_url=f"http://127.0.0.1:{port}/v1", roots=[str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 2 and "cannot reach the model server" in out and "ollama serve" in out


def test_cli_chat_reports_an_unreachable_server_with_a_failing_exit_code(tmp_path):
    from vmd_agent import cli
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert cli.main(["chat", "--base-url", f"http://127.0.0.1:{port}/v1",
                     "--roots", str(tmp_path), "hello"]) == 2


@pytest.mark.requires_llm
def test_a_real_model_uses_the_tools_to_answer_a_question_about_a_real_file(
        tmp_path, monkeypatch):
    """Live. A small local model may do this badly: the benchmark is where model
    quality is measured. This only checks that the loop works end to end."""
    import shutil
    shutil.copy(os.path.join(DATA, "1ubq.pdb"), tmp_path / "protein.pdb")
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    seen = []
    s = agent.Agent(
        os.environ.get("VMD_AGENT_LLM_URL", "http://localhost:11434/v1"),
        os.environ["VMD_AGENT_LIVE_LLM_MODEL"],
        os.environ.get("VMD_AGENT_LLM_KEY"), echo=seen.append, max_turns=8)
    answer = s.ask("Using your tools, what kind of system is protein.pdb? "
                   "Answer in one sentence.")
    assert answer.strip() and any("->" in m for m in seen), seen


@pytest.mark.parametrize("text,wanted", [
    ("What is in 1ubq.pdb?", True), ("Which salt bridges persist in the run?", True),
    ("Measure the radius of gyration", True), ("Build a solvated system", True),
    ("hello", False), ("what can you do?", False), ("thanks, that is all", False)])
def test_the_guard_recognises_questions_about_data(text, wanted):
    assert bool(agent._DATA_WORDS.search(text)) is wanted


@pytest.mark.requires_llm
def test_a_real_model_cannot_answer_a_data_question_without_a_tool(tmp_path, monkeypatch):
    """Live. The guard sends an answer given from memory back and requires a tool call."""
    import shutil
    shutil.copy(os.path.join(DATA, "1ubq.pdb"), tmp_path / "1ubq.pdb")
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    seen = []
    s = agent.Agent(os.environ.get("VMD_AGENT_LLM_URL", "http://localhost:11434/v1"),
                         os.environ["VMD_AGENT_LIVE_LLM_MODEL"], os.environ.get("VMD_AGENT_LLM_KEY"),
                         echo=seen.append, max_turns=8)
    s.ask("What is in 1ubq.pdb? Be brief.")
    assert any(m.strip().startswith("->") for m in seen), seen          # some tool ran before the answer


def test_models_are_not_shown_the_parameters_they_only_make_up():
    from vmd_agent import toolset
    props = toolset.tool_schema(toolset.TOOLS["measure_with_vmd"])["input_schema"]["properties"]
    assert "vmd_path" not in props and "topology" in props
    s = _session()
    out = json.loads(s.run_tool({"id": "1", "name": "probe_environment", "arguments": {"vmd_path": "/usr/local/vmd"}}))
    assert "blocked" not in out                          # the invented path was dropped, not tried


def test_null_frame_arguments_mean_the_default():
    from vmd_agent.vmdkit import script
    assert script.frame_args(None, None, None) == (0, -1, 1)
    assert script.frame_args(1, None, 10) == (1, -1, 10)


def test_numbers_that_no_tool_returned_are_flagged():
    tools = ['{"values": [11.934717, 11.959224], "n": 50, "occupancy": 0.6734, "frames": [0, 10]}']
    ok = "Rg was 11.93 then 11.96 over 50 frames; occupancy 67 %, 0.67 of frames, at frames 0 and 10."
    assert agent.unsupported_numbers(ok, tools) == []
    bad = agent.unsupported_numbers("Rg was 53.2 and 11.93; the box is 128.5 wide", tools)
    assert bad == ["53.2", "128.5"]
    assert agent.unsupported_numbers("```\nvmd -first 1000 -dispdev\n```\nRg 11.93", tools) == []      # code blocks are not claims


@pytest.mark.requires_llm
def test_a_real_model_streams_its_answer_in_pieces(tmp_path, monkeypatch):
    """Live: the answer arrives token by token, and the pieces add up to the answer that is returned."""
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    s = agent.Agent(os.environ.get("VMD_AGENT_LLM_URL", "http://localhost:11434/v1"),
                         os.environ["VMD_AGENT_LIVE_LLM_MODEL"], os.environ.get("VMD_AGENT_LLM_KEY"), max_turns=3)
    pieces = []
    answer = s.ask("Say hello in five words.", on_token=pieces.append)
    assert s.streamed and len(pieces) > 1 and "".join(pieces) == answer


@pytest.mark.parametrize("text,workflow", [
    ("Has my run settled? Use run.psf and run.dcd.", "equilibration_check"), ("Is the simulation equilibrated?", "equilibration_check"),
    ("Compare these two runs of the same system", "compare_runs"), ("Please set up a simulation of 1ubq.pdb", "prepare_simulation"),
    ("Fit my model into this cryo-EM map", "cryoem_fit"), ("Give me an overview of 1ubq.pdb", "structure_overview"),
    ("Which salt bridges persist?", None), ("What is the radius of gyration?", None), ("hello", None)])
def test_questions_a_workflow_answers_are_pointed_at_it(text, workflow):
    assert agent.route(text) == workflow


def test_the_hint_is_added_to_the_question_but_the_guard_still_sees_the_original(monkeypatch):
    seen = {}
    monkeypatch.setattr(agent, "chat_completion", lambda *a, **k: seen.setdefault("messages", list(a[2])) and
                        {"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]})
    s = agent.Agent("http://127.0.0.1:1/v1", "m", guard=False)
    s.ask("Has my run settled?")
    last_user = [m for m in seen["messages"] if m["role"] == "user"][-1]["content"]
    assert last_user.startswith("Has my run settled?") and "run_workflow" in last_user and "equilibration_check" in last_user


@pytest.mark.parametrize("text,wanted", [
    ("Check these statements about protein.pdb and tell me which are true: (1) it has 1 disulfide bond", True),
    ("Is it true that the protein has two chains?", True),
    ("true or false: there is a ligand", True),
    ("Verify the following about 1ubq.pdb: it has 76 residues", True),
    ("What is in protein.pdb?", False),
    ("Render the structure", False),
])
def test_a_list_of_statements_to_judge_is_pointed_at_verify_claims(text, wanted):
    assert agent.claims_hint(text) is wanted


def test_the_hint_is_added_to_the_question_only_when_the_tool_is_offered():
    from conftest import scripted_server as _server
    srv, url, requests = _server([{"content": "ok"}])
    try:
        agent.Agent(url, "m", guard=False).ask("Which of these are true: (1) a ligand")
        without = agent.Agent(url, "m", guard=False)
        without.names = [n for n in without.names if n != "verify_claims"]
        without.ask("Which of these are true: (1) a ligand")
    finally:
        srv.shutdown()
    assert "verify_claims" in requests[0]["messages"][-1]["content"] and "hint from the toolkit" in requests[0]["messages"][-1]["content"]
    assert "hint from the toolkit" not in requests[1]["messages"][-1]["content"]                       # a tool set without verify_claims


def _tool_then(*replies):
    call = {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "list_representations", "arguments": "{\"category\": \"surface\"}"}}]}
    return [call, *replies]


def test_an_answer_with_numbers_no_tool_returned_is_sent_back_once_and_the_correction_is_kept():
    from conftest import scripted_server as _server
    srv, url, requests = _server(_tool_then({"content": "The free energy is -8421.55 kcal/mol."}, {"content": "That cannot be measured with these tools."}))
    try:
        a = agent.Agent(url, "m")
        answer = a.ask("List the surface styles.")
    finally:
        srv.shutdown()
    assert answer == "That cannot be measured with these tools." and len(requests) == 3
    assert "8421.55" in requests[2]["messages"][-1]["content"] and "no tool result" in requests[2]["messages"][-1]["content"]


def test_a_second_unsupported_answer_is_flagged_not_sent_back_again():
    from conftest import scripted_server as _server
    srv, url, requests = _server(_tool_then({"content": "It is -8421.55 kcal/mol."}, {"content": "Really, -8421.55 kcal/mol."}))
    try:
        answer = agent.Agent(url, "m").ask("List the surface styles.")
    finally:
        srv.shutdown()
    assert len(requests) == 3 and "Check these numbers yourself" in answer and "8421.55" in answer


def test_a_streamed_answer_is_flagged_but_cannot_be_taken_back():
    from conftest import scripted_server as _server
    srv, url, requests = _server(_tool_then({"content": "It is -8421.55 kcal/mol."}))
    got = []
    try:
        answer = agent.Agent(url, "m").ask("List the surface styles.", on_token=got.append)
    finally:
        srv.shutdown()
    assert len(requests) == 2 and "".join(got).startswith("It is -8421.55") and "Check these numbers yourself" in answer


def test_a_grounded_answer_is_not_sent_back():
    from conftest import scripted_server as _server
    srv, url, requests = _server(_tool_then({"content": "QuickSurf and Surf draw surfaces."}))
    try:
        answer = agent.Agent(url, "m").ask("List the surface styles.")
    finally:
        srv.shutdown()
    assert len(requests) == 2 and answer == "QuickSurf and Surf draw surfaces."


def test_numbers_written_with_thousands_groups_or_inside_hex_like_words_are_read_correctly():
    assert agent.unsupported_numbers("The file is 127 906 bytes.", ['{"size": 127906}']) == []
    assert agent.unsupported_numbers("It holds 1,280 atoms.", ['{"n_atoms": 1280}']) == []
    assert agent.unsupported_numbers("See /tmp/0e6e9e2f-ba40-444e-845d-2e408ce50b16/x.pdb", ["{}"]) == []                    # no 2e408 = infinity
    assert agent.unsupported_numbers("There are 4 000 atoms.", ['{"n_atoms": 1280}']) == ["4000"]                              # a wrong number is still caught


# ------------------------------------------- claims about the VMD window and about files are checked against what the tools did
def test_a_claim_about_the_vmd_window_needs_a_tool_that_changed_it():
    said = "I drew the protein as a surface and it is now displayed in the VMD window."
    assert agent.unsupported_claims(said, [], [])                                                           # no tool at all
    assert agent.unsupported_claims(said, [{"name": "list_representations", "result": {"ok": True}}], [])   # a tool that cannot touch the window
    assert agent.unsupported_claims(said, [{"name": "run_workflow", "result": {"ok": True, "window": {"ok": True, "changed": False}}}], [])   # the window said nothing changed
    assert not agent.unsupported_claims(said, [{"name": "window_representation", "result": {"ok": True}}], [])
    assert not agent.unsupported_claims(said, [{"name": "run_workflow", "result": {"ok": True, "window": {"ok": True, "changed": True}}}], [])
    assert agent.unsupported_claims(said, [{"name": "window_load", "result": {"ok": False, "error": "no VMD"}}], [])  # a failed call changed nothing
    assert not agent.unsupported_claims("The RMSD is flat; see the report.", [], [])                       # no claim, no flag
    assert not agent.unsupported_claims("The workflow did not change what is shown in the VMD window.", [], [])        # saying that nothing was drawn is the honest answer
    assert not agent.unsupported_claims("Nothing was displayed in the VMD window.", [], [])


def test_a_claim_that_a_file_was_written_needs_a_tool_result_that_names_it():
    assert agent.unsupported_claims("The report was saved to out/report.md.", [], ["{\"other\": 1}", "question"])
    assert not agent.unsupported_claims("The report was saved to out/report.md.", [], ["{\"report\": \"/data/out/report.md\"}"])
    assert not agent.unsupported_claims("Look at protein.pdb for details.", [], [])                         # only 'saved/written/created ...' is a claim


def test_an_answer_that_says_it_drew_in_vmd_without_a_tool_is_sent_back_and_corrected():
    from conftest import scripted_server as _server
    srv, url, requests = _server(_tool_then({"content": "Done: the surface is now shown in the VMD window."}, {"content": "I could not change the VMD window; the styles are listed above."}))
    try:
        answer = agent.Agent(url, "m").ask("List the surface styles.")
    finally:
        srv.shutdown()
    assert answer.startswith("I could not change the VMD window") and len(requests) == 3
    assert "no tool changed the window" in requests[2]["messages"][-1]["content"]


def test_the_agent_is_told_what_it_cannot_do_and_to_say_only_what_tools_show():
    assert "pick atoms with the mouse" in agent.SYSTEM_PROMPT and "Tk windows" in agent.SYSTEM_PROMPT
    assert "Never say that something was drawn" in agent.SYSTEM_PROMPT


# ------------------------------------------- impossible requests are refused before the model can do 'the nearest thing'
@pytest.mark.parametrize("text", [
    "Let me click an atom in the VMD window; tell me which residue I just picked.",
    "Which residue did I hover the mouse over?",
    "Open VMD's Timeline plugin window and show me the secondary structure timeline there.",
    "Launch the Tk console in VMD.",
    "Run NAMD on the system you built and tell me the final potential energy.",
    "Please submit the simulation to the cluster and start the md run.",
])
def test_requests_for_what_the_toolkit_cannot_do_are_refused_in_plain_words(text):
    from vmd_agent import limits
    reply = limits.unsupported(text)
    assert reply and reply.startswith("I cannot")


@pytest.mark.parametrize("text", [
    "Which residue has the highest RMSF in run.dcd?",
    "Pick the three most flexible residues.",
    "What is the secondary structure timeline of protein.pdb over protein.dcd?",
    "Write a NAMD input for the built system.",
    "How do I run NAMD on a cluster?",
    "Show the protein as a surface in the VMD window.",
])
def test_ordinary_requests_are_not_mistaken_for_impossible_ones(text):
    from vmd_agent import limits
    assert limits.unsupported(text) is None


def test_an_impossible_request_is_answered_without_asking_the_model():
    from conftest import scripted_server as _server
    srv, url, requests = _server([{"content": "should never be asked"}])
    try:
        answer = agent.Agent(url, "m").ask("Let me click an atom in the VMD window; tell me which residue I just picked.")
    finally:
        srv.shutdown()
    assert answer.startswith("I cannot see or control the mouse") and requests == []
