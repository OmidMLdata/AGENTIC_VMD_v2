"""'Structure' is VMD's colouring by secondary structure. It looked like a stand-in file name and was dropped before it reached VMD,
so a cartoon asked for 'coloured by Structure' was drawn coloured by element while the tool said it had done what was asked."""
from vmd_agent import toolset, vmdlink, window_tools as WT
from vmd_agent.vmdkit import forgiving as F


def test_file_words_are_placeholders_only_where_a_file_is_expected():
    assert F.is_placeholder("structure", "topology") and F.is_placeholder("topology", "trajectory") and F.is_placeholder("map", "map_file")
    assert F.is_placeholder("structure.pdb", "out_pdb") and F.is_placeholder("file", "session_dir")
    assert not F.is_placeholder("Structure", "color") and not F.is_placeholder("structure", "color_method")
    assert not F.is_placeholder("Structure", "style") and not F.is_placeholder("map", "kind")
    assert F.is_placeholder("topology")                                  # no parameter named: as before
    assert F.is_placeholder("<your_topology>", "color") and F.is_placeholder("None", "color") and F.is_placeholder("", "color")


def test_dropping_placeholders_keeps_a_real_colouring_method_and_still_drops_a_stand_in_file():
    def f(topology: str = "default.pdb", color: str = "Name"):
        return topology, color
    assert toolset._drop_placeholders(f, {"topology": "structure", "color": "Structure"}) == {"color": "Structure"}


class _Window:
    def __init__(self):
        self.added = []
    def reps(self, mid):
        return [dict(index=i, **r) for i, r in enumerate(self.added)]
    def delete_rep(self, mid, i):
        self.added.pop(i)
    def add_rep(self, mid, selection, style, color, material, params):
        self.added.append({"selection": selection, "style": style, "color": vmdlink._color(color), "material": material, "shown": True})   # names normalised as the real window does
        return {"index": len(self.added) - 1}


def test_a_cartoon_coloured_by_structure_reaches_vmd_as_structure(monkeypatch):
    win = _Window()
    monkeypatch.setattr(WT, "_window", lambda *a, **k: win)
    monkeypatch.setattr(WT, "_top", lambda w, molecule=None: 0)
    for colour in ("Structure", "structure", "secondary structure"):
        r = toolset.TOOLS["window_representation"](action="only", selection="protein", style="NewCartoon", color=colour)
        assert r["ok"] and win.added[-1]["color"] == "Structure", (colour, win.added[-1])
        assert "colored by Structure" in r["summary"]
