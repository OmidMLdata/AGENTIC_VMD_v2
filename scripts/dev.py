#!/usr/bin/env python3
"""Maintainer tasks, one file that works on every OS:

  python scripts/dev.py test                  lint, dead-code check and the whole test suite, every skip listed
  python scripts/dev.py test --no-lint        only the tests          (--live also runs the tests that need a model)
  python scripts/dev.py test -k render -x     anything else goes to pytest

  python scripts/dev.py publish               commit what is not ignored, create the GitHub repository, push
  python scripts/dev.py publish --no-push     only the local commit (a good first try)
  python scripts/dev.py publish --branch v2   publish to branch v2: a NEW branch grows from the remote's main (never
                                              overwriting a branch); the branch you are on and that the remote already
                                              has is simply brought up to date (fast-forward only, never forced)
  python scripts/dev.py publish -m "words"    the commit message
  python scripts/dev.py publish --skip-workflows   leave .github/workflows out (GitHub refuses them unless the token has the
                                              `workflow` scope: `gh auth refresh -s workflow` adds it)
  GITHUB_REPO=owner/name python scripts/dev.py publish      publish somewhere else

`publish` starts a git repository if there is none, REFUSES to commit a file that looks like a secret (an API key, a private
key, a saved key in a settings file) or a file over 5 MB outside tests/data, shows what it will commit, then pushes with the
GitHub CLI (`gh`) if you have it, or tells you the commands to run by hand. A skipped test is "not verified here", never a pass.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                    r'"llm_key": *"[^"]+"|ghp_[A-Za-z0-9]{30,}')
BIG = 5_000_000


# ------------------------------------------------------------------------------ test
def _have(mod):
    return importlib.util.find_spec(mod) is not None


def _step(title, argv):
    print(f"\n=== {title}\n$ {' '.join(argv)}", flush=True)
    return subprocess.run(argv, cwd=ROOT).returncode


def cmd_test(args):
    lint, live = "--no-lint" not in args, "--live" in args
    pytest_args = [a for a in args if a not in ("--no-lint", "--live")]
    if not _have("pytest"):
        print("pytest is not installed. Run:  pip install -e '.[dev]'")
        return 2
    results = {}
    if lint:
        if _have("ruff"):
            results["lint (ruff)"] = _step("lint", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"])
        else:
            print("\n=== lint: skipped (ruff not installed; pip install ruff)")
        if _have("vulture"):
            results["dead code (vulture)"] = _step("dead code", [sys.executable, "-m", "vulture"])
        else:
            print("\n=== dead code: skipped (vulture not installed; pip install vulture)")
    env = dict(os.environ)
    if not live:
        env.pop("VMD_AGENT_LIVE_TESTS", None)
        env.pop("VMD_AGENT_LIVE_LLM_MODEL", None)
    print("\n=== tests (the header lists which real tools were found; skips are listed at the end)", flush=True)
    results["tests (pytest)"] = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider"] + pytest_args,
                                               cwd=ROOT, env=env).returncode
    print("\n=== summary")
    for k, v in results.items():
        print(f"  {k:<22} {'ok' if v == 0 else 'FAILED'}")
    return 0 if all(v == 0 for v in results.values()) else 1


# ------------------------------------------------------------------------------ publish
def _git(*a, cwd=ROOT):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def _say(msg):
    print(f"\n==> {msg}", flush=True)


class Stop(Exception):
    pass


def _die(msg):
    raise Stop(msg)


def _files():
    tracked = _git("ls-files").stdout.split("\n")
    new = _git("ls-files", "--others", "--exclude-standard").stdout.split("\n")
    return sorted({f for f in tracked + new if f})


def _check_files():
    bad = []
    for f in _files():
        p = os.path.join(ROOT, f)
        if not os.path.isfile(p):
            continue
        size = os.path.getsize(p)
        if size > BIG and not f.startswith("tests/data/"):
            bad.append(f"  larger than 5 MB:     {f} ({size // 1_000_000} MB)")
        try:
            with open(p, encoding="utf-8") as fh:
                if SECRET.search(fh.read()):
                    bad.append(f"  looks like a secret:  {f}")
        except (UnicodeDecodeError, OSError):
            continue
    if bad:
        print("\n".join(bad), file=sys.stderr)
        _die("refusing to commit. Remove the file, or add it to .gitignore, and run this again.")


def cmd_publish(args):
    push, msg, branch, skip_wf = True, "", "main", False
    repo = os.environ.get("GITHUB_REPO", "OmidMLdata/AGENTIC_VMD_v2")
    it = iter(args)
    for a in it:
        if a == "--no-push":
            push = False
        elif a == "--skip-workflows":
            skip_wf = True
        elif a in ("-m", "--message"):
            msg = next(it, "")
        elif a == "--branch":
            branch = next(it, "")
            if not branch:
                print("--branch needs a name", file=sys.stderr)
                return 2
        else:
            print(f"unknown option: {a} (try: python scripts/dev.py --help)", file=sys.stderr)
            return 2
    try:
        _publish(push, msg, branch, skip_wf, repo)
    except Stop as e:
        print(f"\npublish: {e}", file=sys.stderr)
        return 1
    return 0


def _publish(push, msg, branch, skip_wf, repo):
    if not shutil.which("git"):
        _die("git is not installed (https://git-scm.com/downloads).")
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        _say("Starting a git repository")
        if _git("init", "-q", "-b", branch).returncode != 0:
            _git("init", "-q")
            _git("symbolic-ref", "HEAD", f"refs/heads/{branch}")
    has_head = lambda: _git("rev-parse", "--verify", "-q", "HEAD").returncode == 0     # noqa: E731
    current = lambda: _git("symbolic-ref", "--short", "HEAD").stdout.strip()           # noqa: E731
    gh = shutil.which("gh")
    if _git("remote", "get-url", "origin").returncode != 0 and gh and \
            subprocess.run([gh, "repo", "view", repo], capture_output=True).returncode == 0:
        _git("remote", "add", "origin", f"https://github.com/{repo}.git")            # the repository exists: publish into it
    based_on, updating = None, False
    if _git("remote", "get-url", "origin").returncode == 0:
        _say(f"Looking at the remote ({_git('remote', 'get-url', 'origin').stdout.strip()})")
        if _git("fetch", "-q", "origin").returncode != 0:
            _die("could not reach the remote (check your network and that you may push to it).")
        remote_has = _git("ls-remote", "--exit-code", "--heads", "origin", branch).returncode == 0
        if remote_has and has_head() and current() == branch:
            if _git("merge-base", "--is-ancestor", f"origin/{branch}", "HEAD").returncode != 0:
                _die(f"the remote {branch} has commits this folder does not have; bring them in first (git pull), or pick another "
                     "branch name with --branch. Nothing is ever forced.")
            updating = True
        elif remote_has:
            _die(f"the remote already has a branch called {branch}; choose another name with --branch (this never overwrites a branch).")
        elif not has_head() and _git("rev-parse", "--verify", "-q", "origin/main").returncode == 0:
            _git("symbolic-ref", "HEAD", f"refs/heads/{branch}")               # no commits here yet: start from the remote's main
            _git("reset", "-q", "origin/main")
            based_on = "origin/main"
    ident = lambda k, env: _git("config", k).stdout.strip() or os.environ.get(env, "")   # noqa: E731
    if not ident("user.name", "GIT_AUTHOR_NAME"):
        _die('git does not know who you are. Run:  git config --global user.name "Your Name"')
    if not ident("user.email", "GIT_AUTHOR_EMAIL"):
        _die("git does not know your email. Run:  git config --global user.email you@example.com")
    _say("Checking what would be committed")
    if not _files():
        _die("nothing to commit.")
    _check_files()
    if not has_head():
        _git("symbolic-ref", "HEAD", f"refs/heads/{branch}")                    # the first commit goes on the chosen branch
    elif current() != branch:
        if _git("checkout", "-q", "-b", branch).returncode != 0:
            _die(f"could not create the branch {branch} here (does it already exist locally?).")
    _git("add", "-A")
    if skip_wf:
        _git("reset", "-q", "--", ".github/workflows")
    status = [ln for ln in _git("status", "--short").stdout.split("\n") if ln]
    if status:
        print("\n".join(status[:25]) + (f"\n  ... and {len(status) - 25} more" if len(status) > 25 else ""))
        message = msg or ("Add vmd-agent v2 (replaces the earlier contents)" if based_on else "Update" if has_head() else "Initial commit")
        r = _git("commit", "-q", "-m", message)
        if r.returncode != 0:
            _die("the commit failed: " + (r.stderr or r.stdout).strip())
        _say(f"Committed {len(status)} changed files: {message.splitlines()[0]}")
    else:
        _say("Nothing new to commit")
    if not push:
        _say("Not pushing (--no-push). To publish later:  python scripts/dev.py publish")
        return
    if _git("remote", "get-url", "origin").returncode == 0:
        _say(f"Pushing branch {branch} to {_git('remote', 'get-url', 'origin').stdout.strip()}" + (" (an update)" if updating else ""))
        r = _git("push", "-u", "origin", branch)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            if re.search(r"without .workflow. scope", r.stderr):
                print("\nGitHub refuses .github/workflows without the 'workflow' token scope. Either run:  gh auth refresh -s workflow\n"
                      f"or publish without them:  python scripts/dev.py publish --skip-workflows --branch {branch}", file=sys.stderr)
            _die("the push failed (see above).")
    elif gh:
        if subprocess.run([gh, "auth", "status"], capture_output=True).returncode != 0:
            subprocess.run([gh, "auth", "login"])
        _say(f"Creating https://github.com/{repo} and pushing")
        r = subprocess.run([gh, "repo", "create", repo, "--public", "--source=.", "--remote=origin", "--push", "--description",
                            "Ask questions about molecular structures and simulations in plain language; VMD does the measuring "
                            "and drawing."], cwd=ROOT)
        if r.returncode != 0:
            _die("could not create the repository.")
    else:
        print(f"\nThe GitHub CLI (gh) is not installed. Do this by hand:\n  1. Create an EMPTY repository named {repo.split('/')[-1]} "
              f"at https://github.com/new  (no README, licence or .gitignore)\n  2. git remote add origin https://github.com/{repo}.git\n"
              f"  3. git push -u origin {branch}")
        return
    _say(f"Published: {_git('remote', 'get-url', 'origin').stdout.strip()} (branch {branch})")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "test":
        return cmd_test(rest)
    if cmd == "publish":
        return cmd_publish(rest)
    print(f"unknown task: {cmd} (test or publish)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
