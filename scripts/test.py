#!/usr/bin/env python3
"""Run every check in one command:  python scripts/test.py

1. lint (ruff, errors and unused names only)            skipped, with a message, if ruff is not installed
2. dead code (vulture, confident findings only)          skipped, with a message, if vulture is not installed
3. the whole test suite, with the reason for every skip

Real tools are used where they exist: set VMD_BIN to a VMD launcher (or install VMD) and the
tests that need a real VMD run instead of skipping; the same for ffmpeg. Options:

  --no-lint     only run the tests
  --live        also run the tests that spend money or need a running model server
                (needs VMD_AGENT_LIVE_TESTS=1 + ANTHROPIC_API_KEY, or VMD_AGENT_LIVE_LLM_MODEL; off by default)
  anything else is passed to pytest, e.g.  python scripts/test.py -k render -x

Exit code 0 only if every step that ran passed. A skipped test is "not verified here", never a pass.
"""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def have(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def step(title: str, argv) -> int:
    print(f"\n=== {title}\n$ {' '.join(argv)}", flush=True)
    return subprocess.run(argv, cwd=ROOT).returncode


def main(args) -> int:
    lint = "--no-lint" not in args
    live = "--live" in args
    pytest_args = [a for a in args if a not in ("--no-lint", "--live")]
    if not have("pytest"):
        print("pytest is not installed. Run:  pip install -e '.[dev]'")
        return 2
    results = {}
    if lint:
        if have("ruff"):
            results["lint (ruff)"] = step("lint", [sys.executable, "-m", "ruff", "check", "--select", "F,E9", "src", "tests", "scripts"])
        else:
            print("\n=== lint: skipped (ruff not installed; pip install ruff)")
        if have("vulture"):
            results["dead code (vulture)"] = step("dead code", [sys.executable, "-m", "vulture", "src", "--min-confidence", "80"])
        else:
            print("\n=== dead code: skipped (vulture not installed; pip install vulture)")
    env = dict(os.environ)
    if not live:
        env.pop("VMD_AGENT_LIVE_TESTS", None)
        env.pop("VMD_AGENT_LIVE_LLM_MODEL", None)
    print("\n=== tests (the header lists which real tools were found; skips are listed at the end)", flush=True)
    rc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider"] + pytest_args,
                        cwd=ROOT, env=env).returncode
    results["tests (pytest)"] = rc
    print("\n=== summary")
    for k, v in results.items():
        print(f"  {k:<22} {'ok' if v == 0 else 'FAILED'}")
    return 0 if all(v == 0 for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
