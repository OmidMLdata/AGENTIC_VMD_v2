"""Hand a built system to a simulation engine: a NAMD input file, and a SLURM job script to run things on a cluster.

Both are *generated text*. The NAMD configuration uses standard CHARMM36 settings and the parameter files that ship with
VMD; it has not been run in NAMD (none was available), so read it before you submit it. The SLURM script has not been run
on a cluster.
"""
from __future__ import annotations

import os
import shutil
from typing import List, Optional

from vmd_agent import security
from vmd_agent.vmdkit import script as S

_PAR = "[file join $::env(VMDDIR) plugins noarch tcl readcharmmpar1.5]"


def prepare_namd(psf: str, pdb: str, out_prefix: str, temperature: float = 310.0, minimize_steps: int = 1000,
                 equilibrate_ps: float = 100.0, timestep_fs: float = 2.0, ensemble: str = "npt",
                 vmd_path: Optional[str] = None) -> dict:
    """Write a NAMD configuration (`<out_prefix>.namd`) for a PSF/PDB built with CHARMM36 (see `build_system`):
    minimisation, then equilibration at `temperature` K in the NPT or NVT ensemble, with PME, rigid bonds and a
    2 fs step. The periodic box is taken from the coordinates, and the CHARMM36 parameter files are copied beside the
    file so the folder can be moved. Not run in NAMD: review it first."""
    S.choice(ensemble, ("npt", "nvt"), "ensemble")
    temp, steps, ps, dt = (S.num(temperature, "temperature"), S.whole(minimize_steps, "minimize_steps"),
                           S.num(equilibrate_ps, "equilibrate_ps"), S.num(timestep_fs, "timestep_fs"))
    if not (1 <= temp <= 1000 and steps >= 0 and ps >= 0 and 0.1 <= dt <= 4.0):
        raise security.InvalidInput("temperature must be 1-1000 K, steps and time not negative, timestep 0.1-4 fs")
    pre = os.path.abspath(out_prefix)
    S.keep_inputs([pre + ".namd"], [psf, pdb])
    os.makedirs(os.path.dirname(pre), exist_ok=True)
    body = ["mol new {%s} type psf waitfor all" % security.tcl_path(psf),
            "mol addfile {%s} type pdb waitfor all" % security.tcl_path(pdb),
            "set a [atomselect top all]", "set mm [measure minmax $a]",
            "emit BOX [join [join $mm { }] { }] [$a num] [measure sumweights $a weight charge] [[atomselect top {water and name OH2}] num]",
            f"set par {_PAR}", "emit PAR $par"]
    res = S.run(body, vmd_path)
    if not res["ok"]:
        return {"ok": False, "error": res.get("error")}
    nums = [float(x) for x in res["rows"]["BOX"][0][:6]]
    n_atoms, charge = int(res["rows"]["BOX"][0][6]), float(res["rows"]["BOX"][0][7])
    par_dir = " ".join(res["rows"]["PAR"][0])
    lo, hi = nums[:3], nums[3:]
    size = [h - l for l, h in zip(lo, hi)]
    centre = [(h + l) / 2 for l, h in zip(lo, hi)]
    if int(res["rows"]["BOX"][0][8]) == 0 or min(size) < 20:
        return {"ok": False, "error": "this system has no water (or is tiny): it is not a solvated periodic system, so there is no "
                                       "box to simulate in. Build one with build_system first."}
    files = ["par_all36_prot.prm", "toppar_water_ions_namd.str"]
    local = pre + "_toppar"
    os.makedirs(local, exist_ok=True)
    for f in files:
        shutil.copyfile(os.path.join(par_dir, f), os.path.join(local, f))
    name = os.path.basename(pre)
    steps_run = int(round(ps * 1000.0 / dt))
    cfg = f"""# NAMD configuration written by vmd-agent for {os.path.basename(psf)} / {os.path.basename(pdb)}
# {n_atoms} atoms, net charge {charge:+.3f}, CHARMM36, {ensemble.upper()} at {temp:g} K.
# NOT RUN in NAMD by the author: read it, and check the box, before you submit it.
structure           {os.path.basename(psf)}
coordinates         {os.path.basename(pdb)}
outputName          {name}_run
set temperature     {temp:g}

# force field (CHARMM36 files shipped with VMD, copied into {name}_toppar/)
paraTypeCharmm      on
parameters          {name}_toppar/par_all36_prot.prm
parameters          {name}_toppar/toppar_water_ions_namd.str
temperature         $temperature
exclude             scaled1-4
1-4scaling          1.0
switching           on
switchdist          10.0
cutoff              12.0
pairlistdist        14.0

# integrator
timestep            {dt:g}
rigidBonds          all
nonbondedFreq       1
fullElectFrequency  2
stepspercycle       10

# periodic box (from the coordinates) and PME
cellBasisVector1    {size[0]:.3f} 0 0
cellBasisVector2    0 {size[1]:.3f} 0
cellBasisVector3    0 0 {size[2]:.3f}
cellOrigin          {centre[0]:.3f} {centre[1]:.3f} {centre[2]:.3f}
wrapAll             on
PME                 yes
PMEGridSpacing      1.0

# temperature control
langevin            on
langevinDamping     1.0
langevinTemp        $temperature
langevinHydrogen    off
"""
    if ensemble == "npt":
        cfg += """
# pressure control
useGroupPressure      yes
useFlexibleCell       no
useConstantArea       no
langevinPiston        on
langevinPistonTarget  1.01325
langevinPistonPeriod  200.0
langevinPistonDecay   100.0
langevinPistonTemp    $temperature
"""
    cfg += f"""
# output
restartfreq         5000
dcdfreq             5000
xstFreq             5000
outputEnergies      500
outputPressure      500

# run
minimize            {steps}
reinitvels          $temperature
run                 {steps_run}
"""
    with open(pre + ".namd", "w") as fh:
        fh.write(cfg)
    return {"ok": True, "engine": "vmd-agent (generated text; VMD read the box)", "config": pre + ".namd",
            "parameter_files": [os.path.join(local, f) for f in files], "n_atoms": n_atoms, "net_charge": round(charge, 3),
            "box_size_A": [round(s, 2) for s in size], "equilibration_steps": steps_run,
            "run_with": f"namd3 +p8 {os.path.basename(pre)}.namd > {name}.log   (from the folder holding the files)",
            "warning": "Not run in NAMD. Copy the PSF and PDB beside the .namd file, check the box and the ensemble, and add "
                       "restraints if you need them. Only standard protein, water and ions are covered by the parameter files."}


def slurm_script(command: str, out_path: str, job_name: str = "vmd-agent", partition: Optional[str] = None,
                 nodes: int = 1, cpus: int = 8, gpus: int = 0, hours: float = 12.0, memory_gb: int = 16,
                 modules: Optional[List[str]] = None, kind: str = "shell") -> dict:
    """Write a SLURM batch script (`sbatch out_path`). `kind` says what `command` is: `namd` (a .namd file: runs
    `namd3`), `vmd` (a Tcl script: runs VMD headless) or `shell` (any command line, written as is). Not run on a cluster:
    module names and partitions differ everywhere, so check them."""
    S.choice(kind, ("namd", "vmd", "shell"), "kind")
    for what, val in (("job_name", job_name), ("partition", partition)):
        if val and not all(c.isalnum() or c in "-_." for c in val):
            raise security.InvalidInput(f"{what} may hold only letters, digits, - _ .")
    for m in modules or []:
        if not all(c.isalnum() or c in "-_./" for c in m):
            raise security.InvalidInput(f"module name {m!r} has characters a module name does not")
    if not (1 <= nodes <= 256 and 1 <= cpus <= 1024 and 0 <= gpus <= 16 and 0 < hours <= 24 * 30 and 1 <= memory_gb <= 4096):
        raise security.InvalidInput("a resource request is out of range")
    h = int(hours)
    walltime = f"{h // 24}-{h % 24:02d}:{int((hours - h) * 60):02d}:00" if h >= 24 else f"{h:02d}:{int((hours - h) * 60):02d}:00"
    cmd = {"namd": f"namd3 +p${{SLURM_CPUS_PER_TASK}} {command}" + (" +devices ${CUDA_VISIBLE_DEVICES}" if gpus else "")
           + f" > {os.path.splitext(command)[0]}.log",
           "vmd": f'vmd -dispdev text -eofexit -e "{command}" < /dev/null', "shell": command}[kind]
    lines = ["#!/bin/bash", f"#SBATCH --job-name={job_name}", f"#SBATCH --nodes={nodes}", "#SBATCH --ntasks-per-node=1",
             f"#SBATCH --cpus-per-task={cpus}", f"#SBATCH --mem={memory_gb}G", f"#SBATCH --time={walltime}",
             "#SBATCH --output=%x-%j.out"]
    if partition:
        lines.append(f"#SBATCH --partition={partition}")
    if gpus:
        lines.append(f"#SBATCH --gres=gpu:{gpus}")
    lines += ["", "set -euo pipefail", "cd \"${SLURM_SUBMIT_DIR:-.}\""]
    lines += [f"module load {m}" for m in (modules or [])]
    lines += ["", cmd, ""]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    return {"ok": True, "engine": "vmd-agent (generated text)", "script": out_path, "submit_with": f"sbatch {os.path.basename(out_path)}",
            "walltime": walltime, "warning": "Not run on a cluster: check the module names, the partition and the memory."}
