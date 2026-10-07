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


def test_the_tool_counts_in_the_docs_match_the_code():
    from vmd_agent import toolset
    page = open(os.path.join(ROOT, "docs", "tools.md"), encoding="utf-8").read()
    missing = [n for n in toolset.TOOLS if f"`{n}`" not in page]
    assert not missing, f"tools the page does not list: {missing}"
    total, core = len(toolset.TOOLS), len(toolset.CORE_TOOLS)
    assert f"# The {total} tools" in page and f"{core} + {total - core - 2} + 2 = {total}" in page
    for f in FILES:
        if f.endswith("CHANGELOG.md") or f.endswith("tools.md"):
            continue                                   # the history, and the page that explains where the old count came from
        text = open(f, encoding="utf-8").read()
        assert "47 tools" not in text, f"{f} still says 47 tools"
    assert f"**{total} tools**" in open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()


def test_every_page_of_the_docs_is_in_the_index():
    index = open(os.path.join(ROOT, "docs", "index.md"), encoding="utf-8").read()
    pages = [os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "docs", "*.md"))]
    assert [p for p in pages if p != "index.md" and f"]({p})" not in index] == []
