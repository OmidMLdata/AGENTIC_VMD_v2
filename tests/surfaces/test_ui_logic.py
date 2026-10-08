"""The page's pure logic (selection language, console commands, Markdown) run under node, on a small real-shaped molecule."""
import json
import os
import shutil
import subprocess

import pytest

ASSETS = os.path.join(os.path.dirname(__file__), "..", "..", "src", "vmd_agent", "ui_assets")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

# two residues of a chain plus a ligand and a water, in the payload's layout (indices into the label lists)
MOL = {"n_atoms": 8, "names": ["N", "CA", "C", "O", "H1", "C1", "OH2"], "name": [0, 1, 2, 3, 0, 1, 2, 4 + 2],
       "resnames": ["ALA", "GLY", "LIG", "HOH"], "resname": [0, 0, 0, 0, 1, 1, 2, 3], "chains": ["A", "B"], "chain": [0, 0, 0, 0, 0, 0, 1, 1],
       "elements": ["N", "C", "O", "H"], "element": [0, 1, 1, 2, 0, 1, 1, 2], "resid": [1, 1, 1, 1, 2, 2, 9, 10],
       "is_protein": [1, 1, 1, 1, 1, 1, 0, 0], "is_nucleic": [0] * 8, "is_water": [0, 0, 0, 0, 0, 0, 0, 1]}
XYZ = [0, 0, 0, 1, 0, 0, 2, 0, 0, 3, 0, 0, 4, 0, 0, 5, 0, 0, 6, 0, 0, 50, 0, 0]


def node(js):
    prog = f"const S=require({json.dumps(os.path.join(ASSETS, 'selection.js'))}),C=require({json.dumps(os.path.join(ASSETS, 'commands.js'))})," \
           f"M=require({json.dumps(os.path.join(ASSETS, 'markdown.js'))});const mol={json.dumps(MOL)},xyz={json.dumps(XYZ)};" \
           f"const sel=t=>Array.from(S.compile(t,mol,xyz)).reduce((a,v,i)=>v?a.concat(i):a,[]);{js}"
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_selections_follow_vmd_spelling():
    out = node("console.log(JSON.stringify({all:sel('all'),protein:sel('protein'),water:sel('water'),ca:sel('name CA'),rng:sel('resid 1 to 2 and name N CA'),"
               "notp:sel('not protein and not water'),wild:sel('name C*'),within:sel('within 2.5 of name O'),same:sel('same residue as index 5'),or:sel('resname LIG or water')}))")
    assert out["all"] == list(range(8)) and out["protein"] == [0, 1, 2, 3, 4, 5] and out["water"] == [7] and out["ca"] == [1, 5]
    assert out["rng"] == [0, 1, 4, 5] and out["notp"] == [6] and out["wild"] == [1, 2, 5, 6] and out["within"] == [1, 2, 3, 4, 5]
    assert out["same"] == [4, 5] and out["or"] == [6, 7]


def test_a_bad_selection_says_what_is_wrong():
    out = node("const e=[];for(const t of ['','name','(protein','within x of all','protein protein']){try{S.compile(t,mol,xyz);e.push('ok')}catch(x){e.push(x.name+': '+x.message)}}console.log(JSON.stringify(e))")
    assert all(m.startswith("SyntaxError") for m in out) and "closing )" in out[2]


def test_console_commands_parse_to_actions():
    out = node("console.log(JSON.stringify(['mol modstyle 1 0 Licorice','animate goto 5','display projection Orthographic','bogus'].map(C.parse)))")
    assert out[0] == {"cmd": "mol.modrep", "rep": 1, "id": 0, "style": "Licorice"} and out[1] == {"cmd": "animate.goto", "frame": 5}
    assert out[2]["projection"] == "Orthographic" and "unknown command" in out[3]["error"]


def test_markdown_cannot_inject_html():
    html = node("console.log(JSON.stringify(M.render('<img src=x onerror=1> **b** `c`\\n\\n[x](javascript:alert(1))')))")
    assert "<img" not in html and "<strong>b</strong>" in html and "<code>c</code>" in html and "<a " not in html
