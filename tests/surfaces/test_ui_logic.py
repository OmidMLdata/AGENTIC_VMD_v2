"""The page's pure logic (console commands, Markdown) run under node. Selections are read by VMD itself, so there is no selection language in the page."""
import json
import os
import shutil
import subprocess

import pytest

ASSETS = os.path.join(os.path.dirname(__file__), "..", "..", "src", "vmd_agent", "ui_assets")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

def node(js):
    prog = f"const C=require({json.dumps(os.path.join(ASSETS, 'commands.js'))}),M=require({json.dumps(os.path.join(ASSETS, 'markdown.js'))});{js}"
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_console_commands_parse_to_actions():
    out = node("console.log(JSON.stringify(['mol modstyle 1 0 Licorice','animate goto 5','display projection Orthographic','bogus'].map(C.parse)))")
    assert out[0] == {"cmd": "mol.modrep", "rep": 1, "id": 0, "style": "Licorice"} and out[1] == {"cmd": "animate.goto", "frame": 5}
    assert out[2]["projection"] == "Orthographic" and "unknown command" in out[3]["error"]


def test_markdown_cannot_inject_html():
    html = node("console.log(JSON.stringify(M.render('<img src=x onerror=1> **b** `c`\\n\\n[x](javascript:alert(1))')))")
    assert "<img" not in html and "<strong>b</strong>" in html and "<code>c</code>" in html and "<a " not in html


def test_markdown_never_hangs_on_a_table_that_is_still_streaming():
    """While an answer streams, a table header can arrive before its separator row. That once made the renderer loop forever and froze the page."""
    out = node("""const full='Verdict\\n\\n| Level | Finding |\\n|---|---|\\n| Note | RMSD 2.36 |\\n| OK | box |\\n\\nConclusion';
      const t=Date.now(); const seen=[]; for (let n=1;n<=full.length;n++) seen.push(M.render(full.slice(0,n)).length>0);
      console.log(JSON.stringify({ok:seen.every(Boolean), ms:Date.now()-t, table:M.render(full).includes('<table>'), partial:M.render('| Level |').includes('Level')}))""")
    assert out["ok"] and out["ms"] < 2000 and out["table"] and out["partial"]


def test_terminal_lines_are_sent_to_the_real_command_line():
    out = node("console.log(JSON.stringify(['tool detect_system a.pdb','tools','vmd-agent tool inspect_files a.pdb','workflow','workflow equilibration_check a.psf a.dcd'].map(C.parse)))")
    assert [c["cmd"] for c in out] == ["terminal", "terminal", "terminal", "terminal", "workflow"]
    assert out[2]["line"] == "vmd-agent tool inspect_files a.pdb" and out[3]["line"] == "workflow"


def test_colors_and_styles_are_vmds_own_including_colorid():
    out = node("console.log(JSON.stringify(['mol modcolor 1 0 ColorID 4','mol modstyle 0 0 NewCartoon','mol modstyle 0 0 QuickSurf','mol color Structure','mol modstyle 0 0 Nonsense'].map(C.parse)))")
    assert out[0]["color"] == "ColorID 4" and out[1]["style"] == "NewCartoon" and out[2]["style"] == "QuickSurf" and out[3]["color"] == "Structure" and "error" in out[4]
