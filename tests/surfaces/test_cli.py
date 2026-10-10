"""Command-line interface smoke tests."""
import json

import pytest
from conftest import UBQ_MD_DIR


def run_cli(argv, capsys):
    from vmd_agent import cli
    assert cli.main(argv) == 0
    return capsys.readouterr().out


def test_cli_tool_probe_environment(capsys):
    assert "recommended_renderer" in run_cli(["tool", "probe_environment"], capsys)


def test_cli_tool_visualize_reads_like_a_report(ubq, tmp_path, capsys):
    out = run_cli(["tool", "visualize_and_interpret", ubq, "--out", str(tmp_path), "--views", "front", "--renderer", "matplotlib"], capsys)
    assert "RENDERER: matplotlib" in out and "caveat:" in out
    assert "SAVED IMAGES" in out and "ANNOTATED IMAGES" in out


def test_cli_tool_verify_claims(lyz, capsys):
    out = json.loads(run_cli(["tool", "verify_claims", lyz, "It has one chain", "It has a membrane"], capsys))
    assert sorted(c["verdict"] for c in out["results"]) == ["contradicted", "supported"]


def test_cli_tool_analyze_with_convergence(sample, tmp_path, capsys):
    pdb, dcd = sample
    out = run_cli(["tool", "analyze_trajectory", pdb, dcd, "--analyses", "rmsd", "convergence", "--out", str(tmp_path)], capsys)
    assert '"convergence"' in out and "time (ps)" in out


def test_cli_tool_keyframes_and_provenance(sample, ubq, tmp_path, capsys):
    pdb, dcd = sample
    out = run_cli(["tool", "select_keyframes", pdb, dcd, "--k", "4"], capsys)
    assert '"frames"' in out
    run_cli(["tool", "visualize_and_interpret", ubq, "--out", str(tmp_path), "--renderer", "matplotlib", "--views", "front"], capsys)
    assert '"ok": true' in run_cli(["tool", "verify_provenance", str(tmp_path)], capsys)


def test_cli_tool_representations_and_recipe(ubq, tmp_path, capsys):
    assert "Licorice" in run_cli(["tool", "list_representations", "--name", "Licorice"], capsys)
    run_cli(["tool", "generate_visualization_recipe", ubq, "--out", str(tmp_path / "r.tcl")], capsys)
    assert (tmp_path / "r.tcl").exists()


def test_cli_bench_synth(tmp_path, capsys):
    out = run_cli(["bench", "synth", "6", "--out", str(tmp_path / "s"), "--seed", "1"], capsys)
    assert "wrote 6 structures" in out and "fold_class" in out


def test_cli_validate_dssp_on_files(ubq, lyz, capsys):
    out = run_cli(["bench", "validate-dssp", ubq, lyz], capsys)
    assert '"q3"' in out


def test_cli_analyze_dt_ps(tmp_path, capsys):
    import os
    d = UBQ_MD_DIR
    out = run_cli(["tool", "analyze_trajectory", os.path.join(d, "protein.pdb"), os.path.join(d, "protein.dcd"),
                   "--analyses", "rgyr", "--dt-ps", "400", "--out", str(tmp_path)], capsys)
    assert "user-supplied dt_ps" in out


@pytest.mark.parametrize("argv", [
    ["tool", "analyze_trajectory", "/nope.pdb", "/nope.dcd", "--analyses", "rmsd"],
    ["bench", "validate", "/nope", "/nope"],
    ["bench", "validate-dssp", "/nope.pdb"],
    ["tool", "assemble_report", "/proc/definitely/not/writable"],
])
def test_bad_paths_give_a_clean_error_not_a_traceback(argv, capsys):
    """Six bad invocations end with a plain message, not a raw Python traceback."""
    from vmd_agent import cli
    rc = cli.main(argv)
    out = capsys.readouterr()
    assert "Traceback" not in out.err + out.out
    assert rc in (0, 1)


def test_debug_switch_restores_the_traceback(monkeypatch):
    from vmd_agent import cli
    monkeypatch.setenv("VMD_AGENT_DEBUG", "1")
    with pytest.raises(Exception):
        cli.main(["bench", "validate-dssp", "/nope.pdb"])


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
    assert "1. Set up" in out and "The tool library" in out and "vmd-agent tool" in out
    assert out.count("\n") < 80                                  # one screen or two, not a wall of flags


def test_every_tool_is_a_command_with_a_summary_and_a_valid_example():
    import shlex
    from vmd_agent import cli, toolcli, toolset
    p, _, _ = _all_commands()
    names = toolset.library_tools()
    assert len(names) == 57 and set(toolcli.SUMMARY) == set(names) == set(toolcli.EXAMPLES)
    for n in names:
        example = toolcli.EXAMPLES[n]
        words = shlex.split(example)
        assert words[words.index("vmd-agent") + 1:][:2] == ["tool", n], n
        argv = [a if a != "scene.json" else '{"reps": [{}]}' for a in words[words.index("vmd-agent") + 1:]]    # a file name stands for JSON here
        args = p.parse_args(argv)                                                                                 # the documented example parses
        assert args._tool == n
    assert cli.main(["tool"]) == 0


def test_tool_flags_come_from_the_tool_signatures():
    p, _, _ = _all_commands()
    a = p.parse_args(["tool", "measure_with_vmd", "a.pdb", "a.dcd", "--kind", "rmsd", "--selection", "name CA", "--no-align", "--step", "5"])
    assert (a.topology, a.trajectory, a.kind, a.selection, a.align, a.step) == ("a.pdb", "a.dcd", "rmsd", "name CA", False, 5)
    b = p.parse_args(["tool", "convert_trajectory", "a.pdb", "--out", "x.dcd", "--wrap"])
    assert b.trajectory is None and b.out_path == "x.dcd" and b.wrap is True
    c = p.parse_args(["tool", "mutate_residue", "a.psf", "a.pdb", "P0", "6", "ALA", "--out", "m"])
    assert (c.segid, c.resid, c.new_resname, c.out_prefix) == ("P0", 6, "ALA", "m")
    d = p.parse_args(["tool", "analyze_trajectory", "a.pdb", "a.dcd", "--analyses", "rmsd", "rgyr", "--dt-ps", "400"])
    assert d.analyses == ["rmsd", "rgyr"] and d.dt_ps == 400
    e = p.parse_args(["tool", "inspect_files", "a.psf", "a.dcd"])
    assert e.paths == ["a.psf", "a.dcd"]
    with pytest.raises(SystemExit):
        p.parse_args(["tool", "measure_with_vmd", "a.pdb", "--kind", "bogus"])           # choices are enforced
    with pytest.raises(SystemExit):
        p.parse_args(["tool", "convert_trajectory", "a.pdb"])                            # --out is required


def test_a_tool_command_gives_the_same_answer_as_the_tool(tmp_path, capsys, monkeypatch):
    from vmd_agent import cli
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    dx = tmp_path / "m.dx"
    dx.write_text("object 1 class gridpositions counts 2 2 2\norigin 0 0 0\ndelta 1 0 0\ndelta 0 1 0\ndelta 0 0 1\n"
                  "object 2 class gridconnections counts 2 2 2\nobject 3 class array type double rank 0 items 8 data follows\n"
                  "1 2 3\n4 5 6\n7 8\n")
    assert cli.main(["tool", "inspect_map", str(dx)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["shape"] == [2, 2, 2] and out["integral"] == 36
    assert cli.main(["tool", "inspect_map", str(tmp_path / "missing.mrc")]) == 1


def _flags_of(sub, command):
    parser = sub.choices[command]
    flags = {o for a in parser._actions for o in a.option_strings}
    nested = getattr(parser, "_subparsers", None)
    if nested is not None:                                # `tool` and `bench` have their own sub-commands
        for sp in nested._group_actions[0].choices.values():
            flags |= {o for a in sp._actions for o in a.option_strings}
    return flags


def _docs_text():
    """README and every page of docs/: the manual a user reads."""
    import glob
    import os
    base = os.path.join(os.path.dirname(__file__), "..", "..")
    paths = [os.path.join(base, "README.md")] + sorted(glob.glob(os.path.join(base, "docs", "**", "*.md"), recursive=True))
    return "\n".join(open(p, encoding="utf-8").read() for p in paths)


def test_every_command_and_every_flag_the_manual_names_exists():
    """The README tables are the user's manual: a command or flag that is not real fails here."""
    import re
    readme = _docs_text()
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
    missing = cmds - seen - {"menu", "bench", "tool"}
    assert not missing, f"commands the README's tables do not describe: {sorted(missing)}"


def test_every_tool_is_in_the_manual_with_its_group():
    from vmd_agent import toolset
    readme = _docs_text()
    for n in toolset.library_tools():
        assert f"`{n}`" in readme, n
    for group, _d, _t in toolset.LIBRARY:
        assert group in readme, group


def test_the_version_can_be_asked_for_and_doctor_prints_it(capsys):
    import vmd_agent
    from vmd_agent import cli
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert vmd_agent.__version__ in capsys.readouterr().out
    assert cli.main(["doctor"]) == 0 and f"vmd-agent:   {vmd_agent.__version__}" in capsys.readouterr().out
