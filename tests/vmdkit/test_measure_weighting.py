"""VMD's measure commands are unweighted by default; this toolkit weights by mass. The result says which, so a number can be
compared with one measured in VMD by hand (radius of gyration differed by 0.4% on ubiquitin for that reason alone)."""
from vmd_agent.vmdkit import measure, script as S


def _fake_run(body, vmd_path=None, **kw):
    return {"ok": True, "log": "", "rows": {"INFO": [["natoms", "10", "nframes", "2"]], "V": [["0", "1.0"], ["1", "2.0"]], "DONE": [[]]}}


def test_the_result_says_whether_it_was_mass_weighted(monkeypatch):
    monkeypatch.setattr(S, "run", _fake_run)
    assert measure.measure("protein.pdb", kind="rgyr")["weighting"] == "mass"
    assert measure.measure("protein.pdb", kind="rgyr", mass_weighted=False)["weighting"] == "none"
    assert "weighting" not in measure.measure("protein.pdb", kind="sasa")
