import os

import pytest

from vmd_agent.security import SecurityError, check_path, check_tcl


def test_unrestricted_by_default(tmp_path):
    assert check_path("/etc/hosts") == "/etc/hosts"


def test_sandbox_allows_inside_blocks_outside(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.pdb").write_text("x")
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(root))
    assert check_path(str(root / "a.pdb"))
    assert check_path(str(root / "new" / "out.png"))        # not yet existing
    with pytest.raises(SecurityError):
        check_path("/etc/passwd")
    with pytest.raises(SecurityError):
        check_path(str(root / ".." / "secret"))


def test_sandbox_blocks_symlink_escape(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    os.symlink(outside, root / "link")
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(root))
    with pytest.raises(SecurityError):
        check_path(str(root / "link"))


def test_sandbox_blocks_prefix_sibling(tmp_path, monkeypatch):
    """/data must not admit /data-evil."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data-evil").mkdir()
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path / "data"))
    with pytest.raises(SecurityError):
        check_path(str(tmp_path / "data-evil" / "x"))


def test_none_and_empty_pass_through(monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", "/data")
    assert check_path(None) is None and check_path("") == ""


@pytest.mark.parametrize("script", [
    "exec rm -rf /", "catch {exec ls}", "set x [exec ls]", "open |ls r",
    "eval {puts hi}", "file delete foo", "socket localhost 80",
    "puts hi; exec ls", "uplevel #0 {puts hi}", "load /tmp/x.so",
])
def test_dangerous_tcl_rejected(script):
    with pytest.raises(SecurityError):
        check_tcl(script)


@pytest.mark.parametrize("script", [
    "mol load pdb x.pdb\nmol representation NewCartoon\nputs [molinfo top get numatoms]",
    "# exec is only a comment here\nset a 1",
    "mol color Name\nanimate goto 0\nrotate y by 90",
    "set sel [atomselect top {protein and name CA}]\n$sel num",
])
def test_ordinary_vmd_tcl_allowed(script):
    check_tcl(script)


def test_unsafe_tcl_can_be_enabled(monkeypatch):
    monkeypatch.setenv("VMD_AGENT_ALLOW_UNSAFE_TCL", "1")
    check_tcl("exec ls")


# ------------------------------------------------ audit: deny-list bypasses
@pytest.mark.parametrize("script", [
    'catch "exec touch /tmp/pwned"',                       # quoted command position
    'set f [open /data/x.tcl w]\nputs $f "exec id"\nclose $f\nsource /data/x.tcl',
    'play /data/x.tcl',
    'render Tachyon /tmp/s.dat "touch /tmp/pwned %s"',      # VMD runs the 3rd arg
    'set f [open /etc/passwd r]\nputs [read $f]',
    'mol urlload pdb http://evil.example/x.pdb',
])
def test_known_deny_list_bypasses_are_closed(script):
    with pytest.raises(SecurityError):
        check_tcl(script)


def test_two_argument_render_is_still_allowed():
    check_tcl("render Tachyon /tmp/scene.dat")
    check_tcl("render snapshot /tmp/frame.tga")


# ------------------------------------- audit: values written into our own Tcl
def test_tcl_path_rejects_brace_backslash_and_control_characters():
    from vmd_agent.security import tcl_path
    assert tcl_path("/data/with space/x.pdb").endswith("with space/x.pdb")
    for bad in ("/d/x}y", "/d/x{y", "/d/a\\b", "/d/line\nbreak", "/d/nul\x00"):
        with pytest.raises(SecurityError):
            tcl_path(bad)


def test_tcl_selection_is_a_character_whitelist():
    from vmd_agent.security import tcl_selection
    for ok in ("protein", "resname LIG HEM", "not (protein or nucleic or water)"):
        assert tcl_selection(ok) == ok
    for bad in ("resname x} ; exec touch /tmp/x", "name [exec id]", "a;b"):
        with pytest.raises(SecurityError):
            tcl_selection(bad)


def test_tcl_word_and_resname_filters():
    from vmd_agent.security import tcl_word, safe_resnames
    assert tcl_word("NewCartoon") == "NewCartoon" and tcl_word("ColorID 6")
    for bad in ("Lines} ; exec", "x\ny", "", "1abc"):
        with pytest.raises(SecurityError):
            tcl_word(bad)
    ok, bad = safe_resnames(["LIG", "NA+", "x} ; exec", "Ä", "A" * 30])
    assert ok == ["LIG", "NA+"] and len(bad) == 3


@pytest.mark.parametrize("script", ["source /data/x.tcl", "catch {source /data/x.tcl}"])
def test_source_alone_is_denied(script):
    """Earlier test combined `open` and `source`, so removing the `source`
    rule went unnoticed (found by mutation testing)."""
    with pytest.raises(SecurityError):
        check_tcl(script)


@pytest.mark.parametrize("fn", ["tcl_selection", "tcl_word"])
def test_trailing_newline_is_not_smuggled_past_the_validators(fn):
    """`$` matches before a final newline; the validators must not."""
    from vmd_agent import security as sec
    with pytest.raises(sec.SecurityError):
        getattr(sec, fn)("name CA\n")
    assert getattr(sec, fn)("name CA") == "name CA"


def test_a_residue_name_with_a_trailing_newline_is_rejected():
    from vmd_agent import security as sec
    ok, bad = sec.safe_resnames(["ALA\n", "ALA"])
    assert ok == ["ALA"] and bad == ["ALA\n"]


def test_a_nul_byte_in_a_path_is_a_policy_error_on_every_python(tmp_path, monkeypatch):
    """Found on Python 3.12: realpath raised ValueError instead of the policy
    error, so the sandbox check crashed rather than refusing."""
    from vmd_agent import security as sec
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", str(tmp_path))
    with pytest.raises(sec.SecurityError, match="NUL"):
        sec.check_path(str(tmp_path / "a\x00b"))
    monkeypatch.delenv("VMD_AGENT_ALLOWED_ROOTS")
    with pytest.raises(sec.SecurityError, match="NUL"):
        sec.check_path("x\x00")


def test_relative_paths_are_taken_relative_to_the_first_root(tmp_path, monkeypatch):
    """The server's working directory is usually outside the sandbox, so a
    relative default such as `vmd_agent_output` must land inside it."""
    from vmd_agent import security as sec
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    monkeypatch.setenv("VMD_AGENT_ALLOWED_ROOTS", os.pathsep.join([str(a), str(b)]))
    monkeypatch.chdir("/")                      # a cwd outside every root
    got = sec.check_path("vmd_agent_output")
    assert got == os.path.join(os.path.realpath(str(a)), "vmd_agent_output")
    assert sec.check_path(str(b / "x.pdb")) == str(b / "x.pdb")     # absolute: unchanged
    with pytest.raises(sec.SecurityError):
        sec.check_path("../escape")             # relative paths cannot climb out
    with pytest.raises(sec.SecurityError):
        sec.check_path("/etc/hosts")


def test_without_roots_relative_paths_are_untouched(monkeypatch):
    from vmd_agent import security as sec
    monkeypatch.delenv("VMD_AGENT_ALLOWED_ROOTS", raising=False)
    assert sec.check_path("out/dir") == "out/dir"
