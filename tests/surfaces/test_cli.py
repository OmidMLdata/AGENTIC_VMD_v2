"""Command-line interface smoke tests."""
import pytest
from conftest import UBQ_MD_DIR


def run_cli(argv, capsys):
    from vmd_agent import cli
    assert cli.main(argv) == 0
    return capsys.readouterr().out


def test_cli_probe_and_renderers(capsys):
    assert "matplotlib" in run_cli(["renderers"], capsys)
    assert "recommended_renderer" in run_cli(["probe"], capsys)


def test_cli_show_style_visualize(ubq, tmp_path, capsys):
    out = run_cli(["visualize", ubq, "--out-dir", str(tmp_path), "--views",
                   "front", "--renderer", "matplotlib"], capsys)
    assert "RENDERER: matplotlib" in out and "caveat:" in out
    assert "SAVED IMAGES" in out and "ANNOTATED IMAGES" in out


def test_cli_claims(lyz, capsys):
    out = run_cli(["claims", lyz, "It has one chain", "It has a membrane"], capsys)
    assert "SUPPORTED" in out and "CONTRADICTED" in out


def test_cli_analyze_with_convergence(sample, tmp_path, capsys):
    pdb, dcd = sample
    out = run_cli(["analyze", pdb, dcd, "--do", "rmsd", "convergence",
                   "--out-dir", str(tmp_path)], capsys)
    assert '"convergence"' in out and "time (ps)" in out


def test_cli_keyframes_and_provenance(sample, ubq, tmp_path, capsys):
    pdb, dcd = sample
    out = run_cli(["keyframes", pdb, dcd, "-k", "4"], capsys)
    assert '"frames"' in out
    run_cli(["visualize", ubq, "--out-dir", str(tmp_path), "--no-render"], capsys)
    assert '"ok": true' in run_cli(["provenance", str(tmp_path)], capsys)


def test_cli_bench_commands(ubq, lyz, tmp_path, capsys):
    out = run_cli(["bench", "sampling", "--trials", "10", "--n-frames", "300"],
                  capsys)
    assert "hit: uniform" in out
    out = run_cli(["bench", "truth", ubq], capsys)
    assert '"fold_class": "mixed"' in out
    out = run_cli(["bench", "run", ubq, lyz, "--out-dir", str(tmp_path),
                   "--renderer", "matplotlib", "--conditions", "raw",
                   "legend_stats", "text_only"], capsys)
    assert "| legend_stats |" in out


def test_cli_reps_and_recipe(ubq, tmp_path, capsys):
    assert "NEWCARTOON" not in run_cli(["reps", "--name", "Licorice"], capsys)
    out = run_cli(["recipe", ubq, "-o", str(tmp_path / "r.tcl")], capsys)
    assert "recipe written" in out and (tmp_path / "r.tcl").exists()


def test_cli_bench_synth_and_dry_run(ubq, tmp_path, capsys):
    out = run_cli(["bench", "synth", "6", "--out", str(tmp_path / "s"),
                   "--seed", "1"], capsys)
    assert "wrote 6 structures" in out and "fold_class" in out
    plan = run_cli(["bench", "run", ubq, "--synthetic-dir", str(tmp_path / "s"),
                    "--dry-run", "--conditions", "raw", "text_only",
                    "--price-in", "1", "--price-out", "5"], capsys)
    assert '"n_calls"' in plan and '"est_cost"' in plan


def test_cli_validate_dssp_on_files(ubq, lyz, capsys):
    out = run_cli(["validate-dssp", ubq, lyz], capsys)
    assert '"q3"' in out


def test_cli_analyze_dt_ps(tmp_path, capsys):
    import os
    d = UBQ_MD_DIR
    out = run_cli(["analyze", os.path.join(d, "protein.pdb"),
                   os.path.join(d, "protein.dcd"), "--do", "rgyr", "--dt-ps",
                   "400", "--out-dir", str(tmp_path)], capsys)
    assert "user-supplied dt_ps" in out


@pytest.mark.parametrize("argv", [
    ["analyze", "/nope.pdb", "/nope.dcd"],
    ["validate", "/nope", "/nope"],
    ["validate-dssp", "/nope.pdb"],
    ["bench", "events", "/nope", "/nope"],
    ["report", "/proc/definitely/not/writable"],
])
def test_bad_paths_give_a_clean_error_not_a_traceback(argv, capsys):
    """Six invocations used to die with a raw Python traceback."""
    from vmd_agent import cli
    rc = cli.main(argv)
    out = capsys.readouterr()
    assert "Traceback" not in out.err + out.out
    assert rc in (0, 1)


def test_debug_switch_restores_the_traceback(monkeypatch):
    from vmd_agent import cli
    monkeypatch.setenv("VMD_AGENT_DEBUG", "1")
    with pytest.raises(Exception):
        cli.main(["validate-dssp", "/nope.pdb"])


def test_unknown_benchmark_condition_is_rejected_at_parse_time():
    from vmd_agent import cli
    with pytest.raises(SystemExit) as e:
        cli.main(["bench", "run", "x.pdb", "--conditions", "bogus"])
    assert e.value.code == 2


def test_annotate_panel_side_left_puts_the_panel_on_the_left(tmp_path):
    import numpy as np
    from PIL import Image
    from vmd_agent.visual.annotate import annotate_image
    src = tmp_path / "x.png"
    Image.new("RGB", (300, 200), (255, 0, 0)).save(src)
    kw = dict(legend_lines=["a"], title="t")
    right = annotate_image(str(src), out_path=str(tmp_path / "r.png"), **kw)
    left = annotate_image(str(src), out_path=str(tmp_path / "l.png"),
                          panel_side="left", **kw)
    assert right["size"] == left["size"]
    R = np.asarray(Image.open(right["annotated_image"]))
    L = np.asarray(Image.open(left["annotated_image"]))
    h = R.shape[0] // 2
    assert tuple(R[h, 5]) == (255, 0, 0) and tuple(L[h, 5]) != (255, 0, 0)
    assert tuple(L[h, -5]) == (255, 0, 0)
    bad = annotate_image(str(src), panel_side="top")
    assert not bad["ok"] and "panel_side" in bad["error"]
