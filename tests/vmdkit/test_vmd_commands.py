"""Every `vmd-agent vmd <action>` command, run from the command line against a real VMD (the map and cluster ones need no VMD)."""
import json
import os
import shutil

import pytest

from vmd_agent import cli

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def _run(capsys, *argv):
    rc = cli.main(["vmd", *argv])
    out = capsys.readouterr().out
    return rc, (json.loads(out) if out.strip().startswith("{") else out)


@pytest.mark.requires_vmd
@pytest.mark.requires_ffmpeg
def test_all_vmd_commands_run_from_the_command_line(tmp_path, monkeypatch, capsys, real_tachyon):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for f in ("protein.pdb", "protein.dcd"):
        shutil.copy(os.path.join(DATA, "ubq_md", f), f)
    shutil.copy(os.path.join(DATA, "1ubq.pdb"), "1ubq.pdb")
    (tmp_path / "scene.json").write_text('{"reps": [{"selection": "protein", "style": "NewCartoon", "color": "Structure"}]}')
    from vmd_agent.inputs.volume import write_dx
    from vmd_agent.vmdkit import maps
    import numpy as np
    ca = __import__("MDAnalysis").Universe(os.path.join(DATA, "1ubq.pdb")).select_atoms("protein")
    xyz = ca.positions.astype(float)
    lo, spacing = xyz.min(0) - 20, np.array([2.0] * 3)
    write_dx("target.dx", maps._simulate(xyz, ca.masses, tuple(np.ceil((xyz.max(0) + 20 - lo) / spacing).astype(int)), lo, spacing, 8.0),
             lo, spacing)
    steps = [
        ("capabilities",),
        ("measure", "protein.pdb", "protein.dcd", "--kind", "rgyr", "--step", "25"),
        ("interactions", "protein.pdb", "protein.dcd", "--kind", "salt_bridges", "--step", "10"),
        ("secondary-structure", "protein.pdb", "protein.dcd", "--step", "25"),
        ("backbone-torsions", "1ubq.pdb"),
        ("structure-check", "1ubq.pdb"),
        ("align-structures", "1ubq.pdb", "protein.pdb", "--out", "aligned.pdb"),
        ("pbc-info", "protein.pdb", "protein.dcd", "--step", "25"),
        ("convert-trajectory", "protein.pdb", "protein.dcd", "--out", "ca.dcd", "--selection", "name CA", "--step", "10"),
        ("write-structure", "protein.pdb", "protein.dcd", "--out", "f10.pdb", "--frame", "10"),
        ("volmap", "protein.pdb", "protein.dcd", "--out", "occ.dx", "--kind", "occupancy", "--selection", "resname ALA",
         "--step", "10"),
        ("volume-info", "occ.dx"),
        ("build-system", "1ubq.pdb", "--out", "b/ubq", "--padding", "6"),
        ("mutate-residue", "b/ubq.psf", "b/ubq.pdb", "P0", "6", "ALA", "--out", "b/k6a"),
        ("merge-structures", "b/ubq.psf", "b/ubq.pdb", "b/k6a.psf", "b/k6a.pdb", "--out", "b/merged"),
        ("build-membrane", "--out", "m/mem", "--x-size", "40", "--y-size", "40"),
        ("build-nanotube", "--out", "tube.pdb", "--n", "6", "--m", "6", "--length-nm", "3"),
        ("render-scene", "protein.pdb", "protein.dcd", "--scene", "scene.json", "--out", "pic.png", "--width", "200",
         "--height", "150"),
        ("render-turntable", "protein.pdb", "--scene", "scene.json", "--out", "spin.mp4", "--frames", "4", "--width", "160",
         "--height", "120"),
        ("export-session", "protein.pdb", "protein.dcd", "--scene", "scene.json", "--out", "sess"),
        ("fit-to-map", "1ubq.pdb", "target.dx", "--resolution", "8", "--out", "fitted.pdb"),
        ("map-arithmetic", "target.dx", "smooth", "--value", "3", "--out", "smooth.dx"),
        ("prepare-namd", "b/ubq_ion.psf", "b/ubq_ion.pdb", "--out", "sim/eq", "--equilibrate-ps", "10"),
        ("slurm-script", "eq.namd", "--kind", "namd", "--modules", "namd/3.0", "--out", "run.sbatch"),
    ]
    assert len(steps) == 24
    for argv in steps:
        rc, out = _run(capsys, *argv)
        assert rc == 0 and out["ok"] is True, (argv, out)
    for made in ("aligned.pdb", "ca.dcd", "f10.pdb", "occ.dx", "b/ubq_ion.psf", "b/k6a.psf", "b/merged.pdb", "m/mem.pdb",
                 "tube.pdb", "pic.png", "spin.mp4", "sess/session.tcl", "fitted.pdb", "smooth.dx", "sim/eq.namd", "run.sbatch"):
        assert os.path.getsize(tmp_path / made) > 0, made
