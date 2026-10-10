"""Every relative link in the Markdown files points at a file (and heading) that exists."""
import glob
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FILES = [os.path.join(ROOT, f) for f in ("README.md", "docs/CHANGELOG.md", "docs/NOTICE.md")] + \
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
    page = open(os.path.join(ROOT, "docs", "guide", "tools.md"), encoding="utf-8").read()
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    names = toolset.library_tools()
    missing = [n for n in names if f"`{n}`" not in page]
    assert not missing, f"tools the tool page does not list: {missing}"
    total = len(names)
    assert f"one list of {total} tools" in page and f"**{total} tools** in eleven groups" in readme and len(toolset.LIBRARY) == 11
    for group, _what, tools in toolset.LIBRARY:
        assert f"### {group}" in page, group


def test_every_page_of_the_docs_is_in_the_index():
    index = open(os.path.join(ROOT, "docs", "index.md"), encoding="utf-8").read()
    pages = [os.path.relpath(p, os.path.join(ROOT, "docs")).replace(os.sep, "/") for p in glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True)]
    assert [p for p in pages if p != "index.md" and f"]({p})" not in index] == []


def test_the_model_benchmark_page_lists_every_category_with_its_true_task_count():
    from vmd_agent import model_tasks
    page = open(os.path.join(ROOT, "docs", "benchmarks", "model-benchmark.md"), encoding="utf-8").read()
    rows = dict(re.findall(r"^\| `(\w+)` \|.*\| (\d+) \|$", page, flags=re.M))
    assert set(rows) == set(model_tasks.CATEGORIES)
    for category, tasks in model_tasks.by_category().items():
        assert int(rows[category]) == len(tasks), f"{category}: the page says {rows[category]}, there are {len(tasks)}"


def test_the_docs_say_how_much_context_the_tool_descriptions_take():
    import json
    from vmd_agent import toolset
    from vmd_agent import toolhints
    from vmd_agent.llm_client import to_openai_tools
    page = open(os.path.join(ROOT, "docs", "guide", "tools.md"), encoding="utf-8").read()
    said = int(re.search(r"^\| `all` \|[^|]*\| about ([\d,]+) tokens \|$", page, flags=re.M).group(1).replace(",", ""))
    tokens = len(json.dumps(to_openai_tools(toolhints.enrich(toolset.tool_specs(list(toolset.ALL)))))) / 4
    assert abs(tokens - said) < 0.12 * said, f"about {tokens:.0f} tokens now, the page says about {said}: update docs/guide/tools.md"


def test_every_command_the_docs_and_ci_run_exists():
    """`vmd-agent NAME` in the manual, the CI workflow and the Docker files names a command (and `tool NAME` a tool) that exists."""
    import argparse
    from vmd_agent import cli, toolset
    sub = next(a for a in cli.build_parser()[0]._actions if isinstance(a, argparse._SubParsersAction))
    commands, tools = set(sub.choices), set(toolset.TOOLS) | {toolset.WORKFLOW_ENTRY}
    others = [os.path.join(ROOT, p) for p in (".github/workflows/ci.yml", "docker/docker-compose.yml", "docker/Dockerfile", "docs/guide/docker.md")]
    bad = []
    for f in [f for f in FILES if not f.endswith("CHANGELOG.md")] + others:
        text = open(f, encoding="utf-8").read()
        for m in re.finditer(r"`vmd-agent (?:--?[\w-]+ )*([a-z][a-z-]+)(?: ([a-z_]+))?|vmd-agent:\w+ (?:tool )?([a-z][a-z_-]+)|hostvmd (?:tool )?([a-z][a-z_-]+)", text):
            cmd, arg = m.group(1), m.group(2)
            if cmd and cmd not in commands and cmd not in ("is", "and", "to", "does", "the", "then"):
                bad.append((os.path.basename(f), cmd))
            elif cmd == "tool" and arg and arg not in tools:
                bad.append((os.path.basename(f), "tool " + arg))
            for g in (m.group(3), m.group(4)):
                if g and g not in commands | tools | {"tool"} and not g.startswith(("run", "tool")):
                    bad.append((os.path.basename(f), g))
    assert bad == []
