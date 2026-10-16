"""Plain wording reaches VMD as VMD's own words, and what is really wrong is still refused (with how to fix it).

The calls replayed here are the ones a model made for "show only the protein chain A in CPK colors, highlight residues 100-150 as red
Licorice, display a QuickSurf surface of the binding pocket", each of which used to be refused."""
import os

import pytest

from vmd_agent import toolset, vmdlink
from vmd_agent.vmdkit import forgiving as F, scene
import vmd_agent.window_tools  # noqa: F401  (registers the window tools)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


@pytest.mark.parametrize("said,vmd", [("red", "ColorID 1"), ("Blue", "ColorID 0"), ("#ff0000", "ColorID 1"), ("#FFFFFF", "ColorID 8"), (3, "ColorID 3"),
                                      ("colorid 7", "ColorID 7"), ("CPK", "Name"), ("CPK colors", "Name"), ("by chain", "Chain"),
                                      ("secondary structure", "Structure"), ("color by element", "Element"), ("b-factor", "Beta"), ("Chain", "Chain")])
def test_colours_and_colour_methods(said, vmd):
    assert F.color(said) == vmd


@pytest.mark.parametrize("said,vmd", [("cartoon", "NewCartoon"), ("sticks", "Licorice"), ("licorice", "Licorice"), ("ball and stick", "CPK"),
                                      ("spheres", "VDW"), ("surface", "QuickSurf"), ("quick surf", "QuickSurf"), ("NewCartoon", "NewCartoon")])
def test_styles(said, vmd):
    assert F.style(said, vmdlink.STYLES) == vmd


@pytest.mark.parametrize("said,vmd", [("chainA", "chain A"), ("protein chainA", "protein and chain A"), ("residues 100-150", "resid 100 to 150"),
                                      ("resid 100-150", "resid 100 to 150"), ("residue 100 to 150", "resid 100 to 150"),
                                      ("protein chain A and resid 100-150", "protein and chain A and resid 100 to 150"), ("ligand", F.LIGAND),
                                      ("binding pocket", F.POCKET), ("within 5 of ligand", f"within 5 of ({F.LIGAND})"),
                                      ("same residue as within 5 of resname LIG", "same residue as within 5 of resname LIG"), ("name CA", "name CA"),
                                      ("chains", "chains"), ("resid 1 to 10", "resid 1 to 10")])
def test_selections(said, vmd):
    assert F.selection(said) == vmd


def test_backgrounds_and_unknown_words():
    assert F.background("#ffffff") == "white" and F.background("#111") == "black" and F.background("Grey", vmdlink.BACKGROUNDS) == "gray"
    assert F.background("navy", vmdlink.BACKGROUNDS) == "blue"
    assert F.color("banana") == "banana" and F.style("banana", vmdlink.STYLES) == "banana"      # left for the strict check to refuse


@pytest.mark.parametrize("value", ["<your_topology>", "", "None", "null", "path/to/file.pdb", "topology", "your_trajectory.dcd", "{topology}"])
def test_placeholders_are_recognised(value):
    assert F.is_placeholder(value)


def test_real_names_are_not_placeholders():
    assert not any(F.is_placeholder(v) for v in ("1beb.pdb", "run.dcd", "structures/1ubq.pdb", "protein"))


def test_a_scene_in_plain_words_validates():
    sp = scene.validate({"background": "#ffffff", "projection": "perspective", "reps": [
        {"color": "red", "selection": "resid 100-150", "style": "licorice"}, {"color": "CPK", "selection": "protein chainA", "style": "cartoon"},
        {"color": "white", "selection": "binding pocket", "style": "QuickSurf", "material": "transparent"}]})
    assert sp["background"] == "white" and sp["projection"] == "Perspective"
    assert [(r["selection"], r["style"], r["color"], r["material"]) for r in sp["reps"]] == [
        ("resid 100 to 150", "Licorice", "ColorID 1", "Opaque"), ("protein and chain A", "NewCartoon", "Name", "Opaque"), (F.POCKET, "QuickSurf", "ColorID 8", "Transparent")]


class _Recorder:
    """Stands in for the link to VMD: records each command and holds one molecule, 1beb.pdb."""
    headless = True

    def __init__(self, path):
        self.path, self.sent, self.reps = path, [], [{"index": 0, "selection": "all", "style": "NewCartoon", "color": "Name"}]

    def call(self, verb, *args):
        self.sent.append((verb,) + args)
        if verb == "mol_list":
            return [{"id": 0, "name": "1beb.pdb", "top": True, "shown": True, "natoms": 3576, "nframes": 1, "frame": 0, "numreps": len(self.reps),
                     "files": [self.path]}]
        if verb == "rep_list":
            return [dict(r, index=i) for i, r in enumerate(self.reps)]
        if verb == "rep_delete":
            self.reps.pop(int(args[1]))
        if verb == "rep_add":
            self.reps.append({"selection": args[1], "style": args[2], "color": args[3]})
            return {"index": len(self.reps) - 1}
        if verb == "mol_new":
            raise AssertionError("1beb.pdb is already in the window and must not be loaded again")
        return {}


@pytest.fixture
def window(tmp_path, monkeypatch):
    import shutil
    path = str(tmp_path / "1beb.pdb")
    shutil.copy(os.path.join(DATA, "1beb.pdb"), path)
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    link = _Recorder(os.path.realpath(path))
    monkeypatch.setattr(vmdlink, "attach", lambda timeout=2.0: link)
    monkeypatch.setattr(vmdlink, "open_window", lambda *a, **k: link)
    return link


def _adds(link):
    return [s[1:5] for s in link.sent if s[0] == "rep_add"]


def test_the_refused_calls_from_the_chat_now_reach_vmd_in_its_own_words(window):
    T = toolset.TOOLS
    r = T["window_visualize"](focus="surface", representation="QuickSurf", show_water=False, topology="<your_topology>", trajectory="<your_trajectory>")
    assert r["ok"], r
    window.sent.clear()
    r = T["window_scene"](scene_spec={"background": "#ffffff", "projection": "perspective", "reps": [
        {"color": "red", "selection": "resid 100-150", "style": "licorice"}, {"color": "CPK", "selection": "protein chainA", "style": "cartoon"}]})
    assert r["ok"], r
    assert _adds(window) == [(0, "resid 100 to 150", "Licorice", "ColorID 1"), (0, "protein and chain A", "NewCartoon", "Name")]
    assert ("display", "background", "white") in window.sent


def test_a_request_in_three_parts_is_three_representations(window):
    T = toolset.TOOLS
    assert T["window_representation"](action="only", selection="protein chainA", style="cartoon", color="CPK colors")["ok"]
    assert T["window_representation"](action="add", selection="residues 100-150", style="Licorice", color="red")["ok"]
    r = T["window_representation"](action="add", selection="the binding pocket", style="surface", color="white", material="glass")
    assert r["ok"] and "QuickSurf" in r["summary"] and "ColorID 8" in r["summary"]                # the summary says what VMD holds
    assert _adds(window) == [(0, "protein and chain A", "NewCartoon", "Name"), (0, "resid 100 to 150", "Licorice", "ColorID 1"),
                             (0, F.POCKET, "QuickSurf", "ColorID 8")]
    assert [r["selection"] for r in window.reps] == ["protein and chain A", "resid 100 to 150", F.POCKET]


def test_a_molecule_named_without_its_extension_is_the_one_in_the_window(window):
    assert toolset.TOOLS["window_visualize"](topology="1beb", representation="surface", color_method="by chain", background="#000000")["ok"]
    assert ("display", "background", "black") in window.sent and any(a[2:4] == ("QuickSurf", "Chain") for a in _adds(window))


def test_what_is_really_wrong_is_refused_with_how_to_fix_it_and_what_the_window_holds(window):
    r = toolset.TOOLS["window_representation"](action="add", selection="protein", style="banana")
    assert r["ok"] is False and "style must be one of" in r["error"]
    assert "call the tool again" in r["next_step"] and r["window_holds"][0]["name"] == "1beb.pdb"


def test_nothing_is_cleaned_into_passing_the_security_checks():
    from vmd_agent import security
    for bad in ("name CA\n", "protein\tand chain A", "protein}; exec ls", "a{b", "chain A; exec ls"):
        assert F.selection(bad) == bad                                                           # untouched, so the check below refuses it
        with pytest.raises(security.SecurityError):
            security.tcl_selection(F.selection(bad))


def test_a_background_colour_that_is_not_allowed_is_refused_not_swapped():
    assert F.background("red") == "red" and F.background("#ff0000") == "#ff0000"
    with pytest.raises(Exception):
        scene.validate({"reps": [{}], "background": "red"})
