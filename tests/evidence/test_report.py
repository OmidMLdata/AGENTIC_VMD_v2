"""Sessions and the scientific report."""
from vmd_agent.evidence import report as R
from vmd_agent import auto


def test_session_roundtrip_and_atomic(tmp_path):
    s = R.Session(str(tmp_path))
    s.add_figure("/x.png", "cap")
    s.add_image_interpretation("looks folded", "front")
    s2 = R.Session(str(tmp_path))
    assert s2.data["figures"][0]["caption"] == "cap"
    assert not (tmp_path / "session.json.tmp").exists()


def test_corrupt_session_is_quarantined_not_lost(tmp_path):
    (tmp_path / "session.json").write_text("{broken")
    s = R.Session(str(tmp_path))
    assert (tmp_path / "session.json.corrupt").exists() and s.data["figures"] == []


def test_report_sections_and_relative_figures(lyz, tmp_path):
    from vmd_agent.evidence.claims import verify_claims
    pkg = auto.visualize_and_interpret(lyz, out_dir=str(tmp_path / "o"),
                                       views=("front",), renderer="matplotlib")
    s = R.Session(str(tmp_path / "sess"))
    s.update(detection=pkg["detection"], inspection=pkg["inspection"],
             renderer=pkg["renderer"], provenance=pkg["provenance_path"])
    s.add_claims(verify_claims(lyz, ["one chain", "It has a membrane",
                                     "cats"]))
    for v, p in pkg["images"].items():
        s.add_figure(p, f"{v} view")
    out = R.assemble_report(s.data, out_path=str(tmp_path / "sess" / "r.md"))
    md = out["markdown"]
    for h in ("## A.", "## K.", "## L. Claim Verification",
              "## M. Reproducibility"):
        assert h in md
    assert "contradicted" in md and "not checked (unparsed)" in md
    assert "matplotlib" in md and "caveat:" in md
    assert "![front view](../o/views/front.png)" in md.replace("\\", "/")


def test_report_survives_missing_numbers():
    md = R.assemble_report({"analysis": {"results": {"rmsd": {"summary": {
        "mean": None}}}}})["markdown"]
    assert "n/a" in md


def test_limitations_surface_pbc_and_thin_data(sample, tmp_path):
    from vmd_agent.dynamics.analysis import analyze_trajectory
    pdb, dcd = sample
    ana = analyze_trajectory(pdb, dcd, ["rmsd"], out_dir=str(tmp_path))
    md = R.assemble_report({"analysis": ana})["markdown"]
    assert "Too few independent samples" in md
    assert "does not show convergence" in md
