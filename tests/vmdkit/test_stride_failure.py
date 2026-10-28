"""VMD gives every residue "C" when it cannot run STRIDE, without an error: that must be reported, not passed off as a result."""
from vmd_agent.vmdkit import script as S, structure

LOG = ("Info) VMD for MACOSXARM64\nERROR) Unable to open input file '/var/tmp/tmp.0.Y3DY9G' for writing.\n"
       "ERROR) write_ss_input_pdb(): unable to write input file for Stride\nERROR) Call to Stride program failed.\n")


def _fake_run(log):
    def run(body, vmd_path=None, **kw):
        return {"ok": True, "log": log, "rows": {"RES": [["1", "2", "3"]], "NAME": [["MET", "GLN", "ILE"]], "SS": [["0", "CCC"]],
                                                 "DONE": [[]]}}
    return run


def test_a_stride_failure_is_an_error_not_an_all_coil_answer(monkeypatch):
    monkeypatch.setattr(S, "run", _fake_run(LOG))
    r = structure.secondary_structure("protein.pdb")
    assert r["ok"] is False
    assert "STRIDE" in r["error"] and "/var/tmp" in r["error"] and "every residue as coil" in r["error"]


def test_a_clean_log_still_gives_the_result(monkeypatch):
    monkeypatch.setattr(S, "run", _fake_run("Info) VMD for MACOSXARM64\n"))
    r = structure.secondary_structure("protein.pdb")
    assert r["ok"] is True and r["per_frame"][0]["codes"] == "CCC"


def test_the_message_names_the_file_vmd_could_not_write():
    assert "/var/tmp/tmp.0.Y3DY9G" in structure.stride_failed(LOG)
    assert structure.stride_failed("") is None
