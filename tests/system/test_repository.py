"""The repository is fit to publish: the right files are ignored, the right files are tracked, no secret is present."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GIT = shutil.which("git")

def _without_gh():
    """The environment with the GitHub CLI hidden and a repository name that cannot exist: no test may reach GitHub."""
    gh = shutil.which("gh")
    path = os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep) if not (gh and d == os.path.dirname(gh)))
    return {"GITHUB_REPO": "nobody/this-repository-does-not-exist", "PATH": path}


NO_REAL_REMOTE = _without_gh()

SHOULD_BE_IGNORED = ["vmd_scripts/x.tcl", "data/a.pdb", "pdb_cache/a.pdb", ".env", "config/settings.json", "settings.json",
                     "src/vmd_agent.egg-info/PKG-INFO", "build/x", "dist/x", "docker/vmd-dist/vmd.tar.gz", ".venv/bin/python",
                     "src/vmd_agent/__pycache__/x.pyc", ".DS_Store", "vmd_agent_output/a", "bench_out/a", ".hypothesis/a"]
MUST_STAY_TRACKED = ["tests/data/1ubq.pdb", "tests/data/ubq_md/protein.dcd", "docker/vmd-dist/README.md",
                     "src/vmd_agent/structure/detect.py", "src/vmd_agent/vmdkit/build.py", "src/vmd_agent/inputs/volume.py",
                     "README.md", "pyproject.toml", "scripts/dev.py"]


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


def test_the_publish_command_refuses_a_secret(checkout, tmp_path):
    root, run = checkout
    script = str(root / "scripts" / "dev.py")              # the copy: the script works on the folder it sits in
    fake_key = "sk-" + "ant-api03-" + "abcdefghijklmnopqrstuvwxyz"          # built here so this file does not itself look like a secret
    (root / "notes.json").write_text(json.dumps({"llm_" + "key": fake_key}))
    env = {**os.environ, **NO_REAL_REMOTE, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t"}
    r = subprocess.run([sys.executable, script, "publish", "--no-push"], cwd=root, capture_output=True, text=True, env=env)
    (root / "notes.json").unlink()
    assert r.returncode != 0 and "looks like a secret" in r.stderr and "notes.json" in r.stderr


def test_the_version_is_the_same_everywhere():
    import vmd_agent
    toml = open(os.path.join(ROOT, "pyproject.toml")).read()
    assert f'version = "{vmd_agent.__version__}"' in toml
    assert f"## {vmd_agent.__version__}" in open(os.path.join(ROOT, "CHANGELOG.md")).read()


def test_publishing_to_a_new_branch_starts_from_the_remote_main_and_never_overwrites(checkout, tmp_path):
    """Against a real (local) remote that already has a main branch holding older files."""
    root, _ = checkout
    env = {**os.environ, **NO_REAL_REMOTE, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}

    def git(cwd, *a):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=env)

    remote = tmp_path / "remote.git"
    assert git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote)).returncode == 0
    old = tmp_path / "old"
    old.mkdir()
    git(old, "init", "-q", "-b", "main")
    (old / "OLD.txt").write_text("the earlier contents")
    git(old, "add", "-A")
    git(old, "commit", "-q", "-m", "earlier")
    git(old, "push", "-q", str(remote), "main")
    main_before = git(remote, "rev-parse", "main").stdout.strip()

    work = tmp_path / "work"                               # a fresh folder: no .git yet, like the real one
    shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git"))
    git(work, "init", "-q", "-b", "scratch")
    git(work, "remote", "add", "origin", str(remote))
    r = subprocess.run([sys.executable, "scripts/dev.py", "publish", "--branch", "v2"], cwd=work, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert git(remote, "rev-parse", "main").stdout.strip() == main_before                  # main is untouched
    assert git(remote, "rev-parse", "v2~1").stdout.strip() == main_before                  # v2 grows from main
    files = git(remote, "ls-tree", "-r", "--name-only", "v2").stdout.split()
    assert "README.md" in files and "src/vmd_agent/cli.py" in files and "OLD.txt" not in files
    assert ".github/workflows/ci.yml" in files                                              # normally the CI file goes too
    again = subprocess.run([sys.executable, "scripts/dev.py", "publish", "--branch", "v2"], cwd=work, capture_output=True, text=True, env=env)
    assert again.returncode == 0, again.stdout + again.stderr                               # same branch, nothing new: an update
    assert git(remote, "rev-parse", "v2").stdout.strip() == git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "NEW.txt").write_text("a later change")
    upd = subprocess.run([sys.executable, "scripts/dev.py", "publish", "--branch", "v2", "-m", "later"], cwd=work, capture_output=True, text=True, env=env)
    assert upd.returncode == 0, upd.stdout + upd.stderr
    assert "NEW.txt" in git(remote, "ls-tree", "-r", "--name-only", "v2").stdout.split()
    assert git(remote, "rev-parse", "v2~1").stdout.strip() != main_before                  # a fast-forward: history kept
    other = subprocess.run([sys.executable, "scripts/dev.py", "publish", "--branch", "main"], cwd=work, capture_output=True, text=True, env=env)
    assert other.returncode != 0 and "already has a branch" in other.stderr                 # never overwrites a branch


def test_skip_workflows_leaves_the_ci_file_out(checkout, tmp_path):
    root, _ = checkout
    env = {**os.environ, **NO_REAL_REMOTE, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True, env=env)
    work = tmp_path / "work"
    shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git"))
    subprocess.run(["git", "init", "-q", "-b", "scratch"], cwd=work, check=True, env=env)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=work, check=True, env=env)
    r = subprocess.run([sys.executable, "scripts/dev.py", "publish", "--branch", "v3", "--skip-workflows"], cwd=work, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", "v3"], cwd=remote, capture_output=True, text=True).stdout.split()
    assert "README.md" in files and not [f for f in files if f.startswith(".github/workflows")]
