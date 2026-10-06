"""Whole-pipeline invariants on random PDB files: results are always dicts, never
exceptions; generated recipes never contain stray commands."""
import os
import tempfile

import MDAnalysis as mda
from hypothesis import HealthCheck, assume, given, settings, strategies as st

S = settings(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
NAMES = ["N","CA","C","O","CB","CG","SG","NZ","OD1","OE1","P","O5'","C1","H","HA","OW","HW1","NA","CL","FE","ZN","C2","N1","O1"]
RES = ["ALA","GLY","CYS","LYS","ASP","LIG","HOH","NA","CL","POPC","HEM","DA","DG","XYZ","UNK","TIP3","SOL","ZN"]
ELS = ["C","N","O","S","P","H","NA","CL","FE","ZN","  ","AU"]

@st.composite
def pdb_text(draw):
    n = draw(st.integers(1, 80)); lines = []
    for i in range(1, n + 1):
        name = draw(st.sampled_from(NAMES)); res = draw(st.sampled_from(RES))
        chain = draw(st.sampled_from(list("ABCD ")))
        resid = draw(st.integers(1, 40))
        x, y, z = (draw(st.floats(-30, 30)) for _ in range(3))
        el = draw(st.sampled_from(ELS))
        rec = "HETATM" if res in ("LIG","HOH","NA","CL","HEM","ZN","XYZ","UNK") else "ATOM  "
        lines.append(f"{rec}{i:5d} {name:<4s} {res:>3s} {chain}{resid:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {el:>2s}")
    return "\n".join(lines) + "\nEND\n"

def write(txt):
    f = tempfile.NamedTemporaryFile("w", suffix=".pdb", delete=False); f.write(txt); f.close(); return f.name

from vmd_agent.structure.detect import detect_system
from vmd_agent.structure.stats import structure_stats, stats_caption
from vmd_agent.structure.dssp import assign_dssp, three_state
from vmd_agent.visual.renderers import MatplotlibRenderer
from vmd_agent.evidence.claims import verify_claims
from vmd_agent.auto import visualize_and_interpret

@S
@given(pdb_text())
def test_detect_and_stats_always_return_dicts(txt):
    p = write(txt)
    try:
        d = detect_system(p); assert isinstance(d, dict)
        s = structure_stats(p); assert isinstance(s, dict)
        if "error" not in s: assert isinstance(stats_caption(s), list)
    finally: os.unlink(p)

@S
@given(pdb_text())
def test_dssp_shape_and_alphabet(txt):
    p = write(txt)
    try:
        try:
            u = mda.Universe(p)
        except Exception:                      # MDAnalysis cannot parse this random file: discard
            assume(False)
        prot = u.select_atoms("protein")
        r = assign_dssp(u.atoms)
        assert len(r["codes"]) == len(prot.residues) == len(r["resids"]) == len(r["chains"])
        assert set(r["codes"]) <= set("HGIEBTS-?")
        assert len(three_state(r["codes"])) == len(r["codes"])
    finally: os.unlink(p)

@S
@given(pdb_text())
def test_renderer_never_raises(txt):
    p = write(txt); out = tempfile.mkdtemp()
    try:
        r = MatplotlibRenderer().render_views(p, out_dir=out, views=("front",), width=120, height=90)
        assert isinstance(r, dict) and "ok" in r
        if r["ok"]: assert all(os.path.exists(i) for i in r["images"].values())
    finally: os.unlink(p)

@S
@given(pdb_text(), st.lists(st.sampled_from([
    "It has one chain","The protein has no ligand","It has a membrane","It is mostly helical",
    "It has 2 disulfide bridges","The ligand is buried in a pocket","It is a dimer"]), min_size=1, max_size=4))
def test_verify_claims_total_and_counts_add_up(txt, claims):
    p = write(txt)
    try:
        r = verify_claims(p, claims)
        assert r["n_claims"] == len(claims) == sum(r["counts"].values())
        assert all(x["verdict"] in {"supported","contradicted","unverifiable","unparsed"} for x in r["results"])
    finally: os.unlink(p)

@S
@given(pdb_text())
def test_full_pipeline_returns_dict(txt):
    p = write(txt); out = tempfile.mkdtemp()
    try:
        pkg = visualize_and_interpret(p, out_dir=out, views=("front",), renderer="matplotlib")
        assert isinstance(pkg, dict) and "ok" in pkg
        if pkg.get("ok"):                                   # a recipe is always written and contains no stray commands
            rec = open(pkg["recipe_path"]).read()
            assert "exec" not in rec and "{*}" not in rec
    finally: os.unlink(p)
