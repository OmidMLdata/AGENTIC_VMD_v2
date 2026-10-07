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


def test_the_model_benchmark_page_lists_every_category_with_its_true_task_count():
    from vmd_agent import model_tasks
    page = open(os.path.join(ROOT, "docs", "model-benchmark.md"), encoding="utf-8").read()
    rows = dict(re.findall(r"^\| `(\w+)` \|.*\| (\d+) \|$", page, flags=re.M))
    assert set(rows) == set(model_tasks.CATEGORIES)
    for category, tasks in model_tasks.by_category().items():
        assert int(rows[category]) == len(tasks), f"{category}: the page says {rows[category]}, there are {len(tasks)}"


def test_the_docs_say_how_much_context_the_tool_descriptions_take():
    import json
    from vmd_agent import toolset
    from vmd_agent.llm_client import to_openai_tools
    page = open(os.path.join(ROOT, "docs", "tools.md"), encoding="utf-8").read()
    said = {m.group(1): int(m.group(2).replace(",", "")) for m in re.finditer(r"^\| `(all|core|vmd)`[^|]*\| \d+ \| about ([\d,]+) tokens \|$", page, flags=re.M)}
    assert set(said) == {"all", "core", "vmd"}
    for profile, tokens_said in said.items():
        tokens = len(json.dumps(to_openai_tools(toolset.tool_specs(list(toolset.PROFILES[profile]))))) / 4
        assert abs(tokens - tokens_said) < 0.12 * tokens_said, f"{profile}: about {tokens:.0f} tokens now, the page says about {tokens_said}: update docs/tools.md"
