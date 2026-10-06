"""Every relative link in the Markdown files points at a file (and heading) that exists."""
import glob
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FILES = [os.path.join(ROOT, f) for f in ("README.md", "CHANGELOG.md", "NOTICE.md")] + \
        sorted(glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True))


def _anchors(path):
    out = set()
    for ln in open(path, encoding="utf-8"):
        m = re.match(r"#{1,6}\s+(.*?)\s*$", ln)
        if m:
            t = re.sub(r"[`*_]", "", m.group(1).lower())
            out.add(re.sub(r"[^\w\- ]", "", t).strip().replace(" ", "-"))
    return out


def test_every_relative_markdown_link_resolves():
    bad = []
    for f in FILES:
        text = re.sub(r"```.*?```", "", open(f, encoding="utf-8").read(), flags=re.S)
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, frag = target.partition("#")
            dest = os.path.normpath(os.path.join(os.path.dirname(f), path)) if path else f
            if not os.path.exists(dest):
                bad.append(f"{os.path.relpath(f, ROOT)}: {target} (no such file)")
            elif frag and dest.endswith(".md") and frag not in _anchors(dest):
                bad.append(f"{os.path.relpath(f, ROOT)}: {target} (no such heading)")
    assert not bad, "\n".join(bad)
