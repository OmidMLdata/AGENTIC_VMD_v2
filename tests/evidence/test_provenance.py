"""Run provenance records and verification."""
import json
from vmd_agent.evidence import provenance


def test_record_and_verify_roundtrip(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("hello")
    path = provenance.record_run(str(tmp_path / "out"), "t", {"a": 1},
                                 inputs=[str(f)], recipe_text="mol new x")
    doc = json.load(open(path))
    run = doc["runs"][0]
    assert run["parameters"] == {"a": 1}
    assert run["inputs"][0]["sha256"] == provenance.sha256_file(str(f))
    assert run["recipe_tcl"] == "mol new x" and "recipe_sha256" in run
    assert run["environment"]["python"] and "numpy" in run["environment"]["packages"]
    assert provenance.verify_provenance(str(tmp_path / "out"))["ok"]


def test_verify_detects_modified_input(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("hello")
    provenance.record_run(str(tmp_path / "o"), "t", inputs=[str(f)])
    f.write_text("tampered")
    r = provenance.verify_provenance(str(tmp_path / "o"))
    assert not r["ok"] and "changed" in r["problems"][0]


def test_verify_detects_missing_input(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("x")
    provenance.record_run(str(tmp_path / "o"), "t", inputs=[str(f)])
    f.unlink()
    assert "missing" in provenance.verify_provenance(str(tmp_path / "o"))["problems"][0]


def test_runs_append_and_corrupt_file_is_survived(tmp_path):
    d = tmp_path / "o"
    provenance.record_run(str(d), "a")
    provenance.record_run(str(d), "b")
    assert len(json.load(open(d / "provenance.json"))["runs"]) == 2
    (d / "provenance.json").write_text("{not json")
    provenance.record_run(str(d), "c")
    assert len(json.load(open(d / "provenance.json"))["runs"]) == 1


def test_large_file_hash_skipped(tmp_path):
    f = tmp_path / "big"
    f.write_bytes(b"x" * 2048)
    d = provenance.describe_file(str(f), hash_limit_mb=0.0001)
    assert d["sha256"] is None and "skipped" in d["note"]


def test_rerun_with_new_parameters_is_not_reported_as_tampering(tmp_path):
    """Overwriting earlier outputs is normal; verification of the recorded hashes still reports it."""
    out = tmp_path / "o"
    f = tmp_path / "result.txt"
    inp = tmp_path / "in.txt"
    inp.write_text("data")
    f.write_text("first")
    provenance.record_run(str(out), "t", {"bg": "white"}, inputs=[str(inp)],
                          outputs=[str(f)])
    f.write_text("second")                              # legitimate re-run output
    provenance.record_run(str(out), "t", {"bg": "black"}, inputs=[str(inp)],
                          outputs=[str(f)])
    r = provenance.verify_provenance(str(out))
    assert r["ok"] and not r["problems"]
    assert any("result.txt" in s for s in r["superseded"])


def test_tampering_with_the_latest_record_is_still_caught(tmp_path):
    out = tmp_path / "o"
    f = tmp_path / "result.txt"
    f.write_text("a")
    provenance.record_run(str(out), "t", outputs=[str(f)])
    f.write_text("b")
    provenance.record_run(str(out), "t", outputs=[str(f)])
    f.write_text("c")                                    # changed AFTER the latest record
    r = provenance.verify_provenance(str(out))
    assert not r["ok"] and "run 1 outputs: changed" in r["problems"][0]


def test_a_path_recorded_once_is_always_checked(tmp_path):
    out = tmp_path / "o"
    f = tmp_path / "x.txt"
    f.write_text("a")
    provenance.record_run(str(out), "t", outputs=[str(f)])
    f.unlink()
    assert "missing" in provenance.verify_provenance(str(out))["problems"][0]
