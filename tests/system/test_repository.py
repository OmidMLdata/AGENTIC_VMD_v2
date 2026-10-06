"""The repository is fit to publish: the right files are ignored, the right files are tracked, no secret is present."""
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GIT = shutil.which("git")

SHOULD_BE_IGNORED = ["vmd_scripts/x.tcl", "data/a.pdb", "pdb_cache/a.pdb", ".env", "config/settings.json", "settings.json",
                     "src/vmd_agent.egg-info/PKG-INFO", "build/x", "dist/x", "docker/vmd-dist/vmd.tar.gz", ".venv/bin/python",
                     "src/vmd_agent/__pycache__/x.pyc", ".DS_Store", "vmd_agent_output/a", "bench_out/a", ".hypothesis/a"]
MUST_STAY_TRACKED = ["tests/data/1ubq.pdb", "tests/data/ubq_md/protein.dcd", "docker/vmd-dist/README.md",
                     "src/vmd_agent/structure/detect.py", "src/vmd_agent/vmdkit/build.py", "src/vmd_agent/inputs/volume.py",
                     "README.md", "pyproject.toml"]


@pytest.fixture(scope="module")
def checkout(tmp_path_factory):
    """A throw-away git repository holding exactly what would be committed (nothing ignored)."""
    if GIT is None:
        pytest.skip("git is not installed")
    dest = tmp_path_factory.mktemp("repo")
    skip = shutil.ignore_patterns(".git", "__pycache__", "*.egg-info", ".pytest_cache", ".ruff_cache", ".hypothesis", ".DS_Store",
                                  "vmd_scripts")
    shutil.copytree(ROOT, dest / "r", ignore=skip)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    run = lambda *a: subprocess.run(["git", *a], cwd=dest / "r", capture_output=True, text=True, env=env)   # noqa: E731
    assert run("init", "-q").returncode == 0
    return dest / "r", run


def test_gitignore_ignores_what_it_should(checkout):
    _, run = checkout
    for path in SHOULD_BE_IGNORED:
        assert run("check-ignore", "-q", path).returncode == 0, f"{path} should be ignored"


def test_gitignore_does_not_hide_what_must_be_committed(checkout):
    root, run = checkout
    run("add", "-A")
    tracked = set(run("ls-files").stdout.split())
    for path in MUST_STAY_TRACKED:
        assert path in tracked, f"{path} would not be committed"
    assert not [t for t in tracked if re.search(r"(^|/)(__pycache__|vmd_scripts)/|\.pyc$|\.egg-info", t)]


def test_nothing_that_looks_like_a_secret_or_a_huge_file_would_be_committed(checkout):
    root, run = checkout
    run("add", "-A")
    pattern = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}")
    for rel in run("ls-files").stdout.split():
        p = root / rel
        if rel.startswith("tests/data/") or not p.is_file():
            continue
        assert p.stat().st_size < 5_000_000, f"{rel} is larger than 5 MB"
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert not pattern.search(text), f"{rel} looks like it holds a secret"


def test_the_version_is_the_same_everywhere():
    import vmd_agent
    toml = open(os.path.join(ROOT, "pyproject.toml")).read()
    assert f'version = "{vmd_agent.__version__}"' in toml
    assert f"## {vmd_agent.__version__}" in open(os.path.join(ROOT, "CHANGELOG.md")).read()
