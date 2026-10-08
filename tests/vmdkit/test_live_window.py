"""The live link to a VMD window (vmdlink + the window_* tools), against a real VMD started with no window (the same commands as for a window,
so a test never opens one), and checked against MDAnalysis wherever an independent value exists. What does not need VMD is tested without it."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import MDAnalysis as mda
import numpy as np
import pytest

from vmd_agent import security, toolset, vmdlink

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
vmd = pytest.mark.requires_vmd


# ------------------------------------------------------------------ no VMD needed
def test_the_bridge_and_python_agree_on_the_commands_and_nothing_is_left_unfilled():
    text = open(vmdlink.BRIDGE).read()
    listed = re.search(r"variable verbs \{([^}]*)\}", text, re.S).group(1).split()
    assert tuple(listed) == vmdlink.VERBS
    assert all(f"proc ::vmdagent_link::v_{v} " in text for v in vmdlink.VERBS)                 # each verb has its procedure
    filled = vmdlink.bridge_script(41234, "tok", headless=True)
    assert not re.search(r"@[A-Z]+@", filled)
    assert "41234" in filled and 'variable token "tok"' in filled and "NewCartoon" in filled and "variable headless 1" in filled


def test_a_request_is_one_line_and_every_argument_stays_one_word():
    line = vmdlink.request_line("tok-en_1", 7, "query", ["resname LIG and name C1", "0"])
    assert line.endswith("\n") and line.count("\n") == 1 and line.startswith("tok-en_1 7 query ")
    assert vmdlink.quote("[exit]") == "\\[exit\\]" and vmdlink.quote("a b") == "a\\ b" and vmdlink.quote("$x;{}") == "\\$x\\;\\{\\}" and vmdlink.quote("") == "{}"
    for bad in ("a\nb", "a\rb", "a\x00b", "a\x1bb"):
        with pytest.raises(security.InvalidInput):
            vmdlink.quote(bad)
    with pytest.raises(security.InvalidInput):
        vmdlink.request_line("t", 1, "eval", ["puts hi"])                                      # there is no verb that runs Tcl


@pytest.mark.skipif(shutil.which("tclsh") is None, reason="no tclsh to read a request back with")
def test_the_quoting_round_trips_through_a_real_tcl_list_without_evaluating_anything(tmp_path):
    words = ["plain", "resname LIG and name C1", "[exit]", "$HOME", "a;b", "{x}", "back\\slash", "quote\"s", "", "ünï", "within 5 of (name CA)"]
    line = vmdlink.request_line("tok", 3, "query", words).strip()
    script = tmp_path / "read_back.tcl"
    script.write_text("set line [gets stdin]\nputs [llength $line]\nforeach w $line { puts \"<$w>\" }\n")
    r = subprocess.run(["tclsh", str(script)], input=line + "\n", capture_output=True, text=True, timeout=20)
    got = r.stdout.split("\n")
    assert int(got[0]) == 3 + len(words)                                                       # each word is still one word
    assert got[1:4] == ["<tok>", "<3>", "<query>"] and got[4:4 + len(words)] == [f"<{w}>" for w in words]


def test_window_tools_say_what_to_do_when_no_window_is_open():
    for name, args in (("window_molecules", {}), ("window_snapshot", {"out_png": "x.png"}), ("window_view", {"action": "reset"})):
        r = toolset.TOOLS[name](**args)
        assert r["ok"] is False and "window_open" in r["error"]


def test_the_choices_the_window_offers_are_the_ones_the_scene_description_uses():
    from vmd_agent.vmdkit import scene
    assert set(scene.STYLES) <= set(vmdlink.STYLES) and set(scene.COLORS) <= set(vmdlink.COLORS) and set(scene.MATERIALS) == set(vmdlink.MATERIALS)
    assert vmdlink.file_type("x.cif") == "pdbx" and vmdlink.file_type("a.mrc") == "ccp4" and vmdlink.file_type("t.dcd") == "dcd"
    with pytest.raises(security.InvalidInput):
        vmdlink.file_type("x.exe")


# ------------------------------------------------------------------ a real VMD
@pytest.fixture()
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    for f in ("protein.pdb", "protein.dcd"):
        shutil.copy(os.path.join(DATA, "ubq_md", f), tmp_path / f)
    link = vmdlink.open_window(headless=True)
    yield vmdlink.Window(link), str(tmp_path)
    vmdlink.stop()


@vmd
def test_a_structure_and_trajectory_load_with_the_frames_lined_up_and_match_mdanalysis(window):
    win, d = window
    r = win.new_molecule(os.path.join(d, "protein.pdb"))
    r = win.add_file(r["id"], os.path.join(d, "protein.dcd"), drop_first=True)
    u = mda.Universe(os.path.join(d, "protein.pdb"), os.path.join(d, "protein.dcd"))
    assert r["natoms"] == len(u.atoms) and r["nframes"] == len(u.trajectory)                    # the structure's own frame is dropped
    win.animate("goto", 7)
    q = win.query("protein", 0)
    u.trajectory[7]
    assert q["natoms"] == u.select_atoms("protein").n_atoms and q["frame"] == 7
    assert q["rgyr"] == pytest.approx(float(u.select_atoms("protein").radius_of_gyration()), abs=0.05)
    assert win.measure("bond", 0, 0, 1)["value"] == pytest.approx(float(np.linalg.norm(u.atoms[0].position - u.atoms[1].position)), abs=0.01)
    with pytest.raises(vmdlink.LinkError, match="frame must be"):
        win.animate("goto", 10 ** 6)


@vmd
def test_representations_are_added_changed_and_removed_in_vmd(window):
    win, d = window
    win.new_molecule(os.path.join(d, "protein.pdb"))
    win.add_rep(0, "protein", "NewCartoon", "Structure")
    win.add_rep(0, "resname ALA", "Licorice", "ResType", "Opaque", [0.2, 12, 12])
    reps = win.reps(0)
    assert [r["style"] for r in reps][1:] == ["NewCartoon", "Licorice 0.2 12 12"] and reps[2]["selection"] == "resname ALA" and reps[2]["color"] == "ResType"
    win.modify_rep(0, 1, "color", "ColorID 4")
    win.modify_rep(0, 1, "style", "QuickSurf")
    win.modify_rep(0, 1, "show", False)
    r1 = win.reps(0)[1]
    assert r1["color"] == "ColorID 4" and r1["style"] == "QuickSurf" and r1["shown"] is False
    win.delete_rep(0, 0)
    assert len(win.reps(0)) == 2
    with pytest.raises(vmdlink.LinkError, match="cannot read that selection"):
        win.modify_rep(0, 0, "selection", "name CAA and (")                                       # VMD would accept this silently and draw nothing
    with pytest.raises(vmdlink.LinkError, match="no representation"):
        win.modify_rep(0, 9, "color", "Name")


@vmd
def test_display_view_molecule_and_state_commands_work_and_are_read_back(window):
    win, d = window
    win.new_molecule(os.path.join(d, "protein.pdb"))
    win.display("background", "white")
    win.display("projection", "Orthographic")
    win.display("depthcue", True)
    for call in (lambda: win.view("rotate", "y", 30), lambda: win.view("scale", 1.5), lambda: win.view("translate", 0.1, 0, 0), lambda: win.view("center", "resid 20", 0),
                 lambda: win.view("save", "a"), lambda: win.view("reset"), lambda: win.view("restore", "a")):
        call()
    st = win.state()
    assert st["display"]["background"] == "white" and st["display"]["projection"] == "Orthographic" and st["display"]["depthcue"] is True
    win.rename(0, "ubq")
    win.show(0, False)
    m = win.molecules()[0]
    assert m["name"] == "ubq" and m["shown"] is False and m["top"] is True
    win.label("name CA", 0, 5)
    win.clear_labels()
    with pytest.raises(vmdlink.LinkError):
        win.view("restore", "never_saved")
    win.clear()
    assert win.molecules() == []


@vmd
def test_a_snapshot_is_vmds_own_picture_and_the_saved_state_loads_the_molecule(window, tmp_path):
    win, d = window
    win.new_molecule(os.path.join(d, "protein.pdb"))
    win.add_rep(0, "protein", "NewCartoon", "Structure")
    r = win.snapshot(os.path.join(d, "shot.png"), "tachyon")
    from PIL import Image
    with Image.open(r["path"]) as im:
        assert im.format == "PNG" and np.asarray(im.convert("L")).std() > 5                      # something is drawn
    assert r["renderer"] == "TachyonInternal"
    out = win.save_state(os.path.join(d, "s.vmd"))
    assert "mol new" in open(out["path"]).read()


@vmd
def test_what_could_be_tcl_never_reaches_vmd_or_is_refused_by_it(window):
    win, d = window
    win.new_molecule(os.path.join(d, "protein.pdb"))
    for bad in ("all; exit", "[exit]", "all $x", "name CA\nexit", "{all}", 'all"'):
        with pytest.raises((security.SecurityError, security.InvalidInput)):
            win.query(bad, 0)
    with pytest.raises(security.InvalidInput):
        win.add_rep(0, "all", "Hax")
    with pytest.raises(security.InvalidInput):
        win.display("projection", "Orthographic; exit")
    with pytest.raises(security.SecurityError):
        win.new_molecule("/etc/passwd")                                                         # outside the folders the toolkit may use
    # and straight at the socket, without Python's checks: the bridge refuses on its own
    port, token = win.link.port, win.link.token

    def raw(line):
        with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
            s.sendall(line.encode())
            s.settimeout(5)
            try:
                return s.recv(4096).decode().strip()
            except OSError:
                return ""
    assert raw("not-the-token 1 ping\n") == ""                                                  # a wrong token is hung up on, with no answer
    assert json.loads(raw(f"{token} 1 exit\n"))["error"] == "unknown verb"
    assert json.loads(raw(f"{token} 2 eval puts\\ hi\n"))["error"] == "unknown verb"
    assert "not allowed" in json.loads(raw(f"{token} 3 query {{[exit]}} 0\n"))["error"]
    assert "absolute path" in json.loads(raw(f"{token} 4 mol_new relative.pdb pdb\n"))["error"]
    assert json.loads(raw(f"{token} 5 mol_new /tmp/a{{b.pdb pdb\n"))["ok"] is False
    assert win.link.call("ping")["molecules"] == 1                                              # VMD is still there and still ours


@vmd
def test_another_process_finds_the_same_window_through_the_link_file(window, tmp_path):
    win, d = window
    win.new_molecule(os.path.join(d, "protein.pdb"))
    env = {**os.environ, "VMD_AGENT_ALLOWED_ROOTS": d}
    r = subprocess.run([sys.executable, "-m", "vmd_agent.cli", "tool", "window_molecules", "--quiet"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] and out["molecules"][0]["atoms"] == 1240
    assert vmdlink.status()["connected"] is True
    assert vmdlink.stop() is True and vmdlink.status()["connected"] is False
    time.sleep(0.3)
    assert vmdlink.attach() is None                                                             # a closed window is noticed, not assumed


@vmd
def test_the_window_tools_do_what_the_agent_would_ask(window):
    win, d = window
    t = toolset.TOOLS
    r = t["window_load"](topology=os.path.join(d, "protein.pdb"), trajectory=os.path.join(d, "protein.dcd"))
    assert r["ok"] and r["loaded"]["nframes"] == 50 and "50 frame" in r["summary"]
    r = t["window_representation"](action="only", selection="protein", style="NewCartoon", color="Structure")
    assert r["ok"] and len(r["representations"]) == 1 and r["representations"][0]["style"] == "NewCartoon"
    assert t["window_representation"](action="modify", rep=0, selection="resname ALA", color="Chain")["representations"][0]["selection"] == "resname ALA"
    assert t["window_representation"](action="add", selection="all; exit")["ok"] is False
    assert t["window_animate"](action="goto", frame=12)["frame"] == 12
    assert t["window_query"](selection="resname ALA")["natoms"] == 20
    assert t["window_molecules"](action="list")["molecules"][0]["frames"] == 50
    assert t["window_scene"](scene_spec={"reps": [{"selection": "protein", "style": "Tube", "color": "Name"}]}, topology=os.path.join(d, "protein.pdb"))["ok"]
    assert len(t["window_molecules"]()["molecules"]) == 2
    shot = t["window_snapshot"](out_png=os.path.join(d, "w.png"), quality="tachyon")
    assert shot["ok"] and os.path.getsize(shot["image"]) > 1000
