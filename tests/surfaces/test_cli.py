"""Command-line interface smoke tests."""
import json

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


# ------------------------------------------------------------------ the command line is organised and documented
def _all_commands():
    from vmd_agent import cli
    p, sub = cli.build_parser()
    return p, sub, set(sub.choices)


def test_every_command_is_in_exactly_one_group_of_the_help():
    from vmd_agent import cli
    _, _, cmds = _all_commands()
    listed = [c for _, group in cli.GROUPS for c in group]
    assert sorted(listed) == sorted(cmds), (set(cmds) ^ set(listed))
    assert len(listed) == len(set(listed))


def test_the_top_level_help_is_the_grouped_overview(capsys):
    from vmd_agent import cli
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "1. Set up" in out and "Drive VMD itself" in out and "vmd-agent vmd" in out
    assert out.count("\n") < 80                                  # one screen or two, not a wall of flags


def test_every_vmd_tool_is_a_vmd_command_with_a_valid_example():
    import shlex
    from vmd_agent import cli, vmd_cli
    p, _, _ = _all_commands()
    names = vmd_cli.VMD_TOOLS
    assert len(names) == 24
    for n in names:
        example = vmd_cli.EXAMPLES[n]
        assert example.startswith("vmd-agent vmd " + vmd_cli.command_name(n)), n
        assert vmd_cli.SUMMARY[n]
        argv = shlex.split(example)[1:]
        argv = [a if a != "scene.json" else '{"reps": [{}]}' for a in argv]          # a file name stands for JSON here
        args = p.parse_args(argv)                                                      # the documented example parses
        assert args._tool == n
    assert cli.main(["vmd"]) == 0


def test_vmd_command_flags_come_from_the_tool_signatures():
    p, _, _ = _all_commands()
    a = p.parse_args(["vmd", "measure", "a.pdb", "a.dcd", "--kind", "rmsd", "--selection", "name CA", "--no-align",
                      "--step", "5"])
    assert (a.topology, a.trajectory, a.kind, a.selection, a.align, a.step) == ("a.pdb", "a.dcd", "rmsd", "name CA", False, 5)
    b = p.parse_args(["vmd", "convert-trajectory", "a.pdb", "--out", "x.dcd", "--wrap"])
    assert b.trajectory is None and b.out_path == "x.dcd" and b.wrap is True
    c = p.parse_args(["vmd", "mutate-residue", "a.psf", "a.pdb", "P0", "6", "ALA", "--out", "m"])
    assert (c.segid, c.resid, c.new_resname, c.out_prefix) == ("P0", 6, "ALA", "m")
    with pytest.raises(SystemExit):
        p.parse_args(["vmd", "measure", "a.pdb", "--kind", "bogus"])           # choices are enforced
    with pytest.raises(SystemExit):
        p.parse_args(["vmd", "convert-trajectory", "a.pdb"])                   # --out is required


def test_a_vmd_command_gives_the_same_answer_as_the_tool(tmp_path, capsys, monkeypatch):
    from vmd_agent import cli
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    dx = tmp_path / "m.dx"
    dx.write_text("object 1 class gridpositions counts 2 2 2\norigin 0 0 0\ndelta 1 0 0\ndelta 0 1 0\ndelta 0 0 1\n"
                  "object 2 class gridconnections counts 2 2 2\nobject 3 class array type double rank 0 items 8 data follows\n"
                  "1 2 3\n4 5 6\n7 8\n")
    assert cli.main(["vmd", "volume-info", str(dx)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["shape"] == [2, 2, 2] and out["integral"] == 36
    assert cli.main(["vmd", "volume-info", str(tmp_path / "missing.mrc")]) == 1


def test_old_flag_spellings_still_work_and_new_aliases_exist():
    from vmd_agent import cli
    p, _, _ = _all_commands()
    assert p.parse_args(["detect", "a.pdb", "--traj", "a.dcd"]).traj == "a.dcd"
    assert p.parse_args(["detect", "a.pdb", "--trajectory", "a.dcd"]).traj == "a.dcd"
    assert p.parse_args(["analyze", "a.pdb", "a.dcd", "--selection", "name CA", "--selection2", "resname LIG"]).sel2 == "resname LIG"
    assert cli is not None


def _flags_of(sub, command):
    parser = sub.choices[command]
    flags = {o for a in parser._actions for o in a.option_strings}
    nested = getattr(parser, "_subparsers", None)
    if nested is not None:                                # `vmd` has its own sub-commands
        for sp in nested._group_actions[0].choices.values():
            flags |= {o for a in sp._actions for o in a.option_strings}
    return flags


def test_every_command_and_every_flag_the_readme_names_exists():
    """The README tables are the user's manual: a command or flag that is not real fails here."""
    import os
    import re
    readme = open(os.path.join(os.path.dirname(__file__), "..", "..", "README.md"), encoding="utf-8").read()
    _, sub, cmds = _all_commands()
    seen = set()
    for line in readme.splitlines():
        m = re.match(r"\| `vmd-agent( [^`]*)?`", line)
        if not m:
            continue
        cells = line.split("|")
        first = cells[1]
        words = [w for w in re.findall(r"vmd-agent (\w[\w-]*)", first) if w in cmds]
        if not words:
            continue
        seen.update(words)
        have = set()
        for w in words:
            have |= _flags_of(sub, w)
        for flag in re.findall(r"(?<![\w-])(--[a-z0-9][a-z0-9-]*|-[a-z](?=[ `,)·]))", " ".join(cells[2:])):
            assert flag in have, f"README says `{words[0]}` has {flag}, which it does not"
    missing = cmds - seen - {"vmd", "menu", "bench"}
    assert not missing, f"commands the README's tables do not describe: {sorted(missing)}"


def test_every_vmd_command_is_described_in_the_readme():
    import os
    from vmd_agent import vmd_cli
    readme = open(os.path.join(os.path.dirname(__file__), "..", "..", "README.md"), encoding="utf-8").read()
    for n in vmd_cli.VMD_TOOLS:
        assert f"vmd-agent vmd {vmd_cli.command_name(n)}" in readme, n
