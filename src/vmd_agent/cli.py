"""Command-line interface mirroring the MCP tools (works without an agent).

Examples
--------
    vmd-agent probe
    vmd-agent inspect system.psf traj.dcd
    vmd-agent detect system.psf --traj traj.dcd
    vmd-agent recipe system.psf --traj traj.dcd -o recipe.tcl
    vmd-agent analyze system.psf traj.dcd --do rmsd rmsf rgyr --sel protein
    vmd-agent render system.psf --traj traj.dcd -o frame.png
    vmd-agent report ./session --out report.md
    vmd-agent show 1UBQ --renderer matplotlib      # no VMD needed
    vmd-agent keyframes system.psf traj.dcd -k 9 --sel2 "resname LIG"
    vmd-agent claims system.pdb "The ligand is buried" "It has 4 disulfides"
    vmd-agent bench sampling                       # uniform vs event-aware study
    vmd-agent provenance vmd_agent_output
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from vmd_agent import auto as auto_mod
from vmd_agent.inputs import inspection
from vmd_agent.structure import detect as detect_mod
from vmd_agent.visual import recipes, render as render_mod
from vmd_agent.dynamics import analysis
from vmd_agent.evidence import report as report_mod, media


def _print(obj):
    print(json.dumps(obj, indent=2, default=str))


def _print_brief(pkg):
    """Human-readable summary of an interpretation package."""
    if not pkg.get("ok"):
        _print(pkg)
        return
    if pkg.get("fetched"):
        f = pkg["fetched"]
        print(f"FETCHED: {f.get('identifier')} -> {f.get('path')}"
              f"  ({f.get('source')}, {'cached' if f.get('cached') else 'downloaded'})")
    if pkg.get("database_description"):
        print("DATABASE:", pkg["database_description"])
    print("SYSTEM TYPE:", pkg["system_type"])
    if pkg.get("renderer"):
        r = pkg["renderer"]
        print(f"RENDERER: {r['used']} (requested {r['requested']})")
        for c in r.get("caveats", []):
            print("  caveat:", c)
    print("\nPRELIMINARY EXPLANATION:\n ", pkg["preliminary_explanation"])
    print("\nVISUAL LEGEND (what each shape/colour is):")
    for l in pkg["visual_legend"]:
        print("  -", l)
    print("\nWHAT TO LOOK FOR:")
    for l in pkg["what_to_look_for"]:
        print("  -", l)
    for n in pkg.get("source_notes", []):
        print("\nNOTE:", n)
    if pkg.get("stats_caption"):
        print("\nSTRUCTURE STATISTICS:")
        for l in pkg["stats_caption"]:
            print("  ", l)
    for ck in pkg.get("color_keys", []):
        print(f"\nCOLOUR KEY — {ck['method']}: {ck['description']}")
        for e in ck.get("entries", []):
            print(f"   {e['hex']}  {e['color']:9s} {e['label']}")
    if pkg.get("images"):
        print("\nSAVED IMAGES:")
        for v, p in pkg["images"].items():
            print(f"  {v:6s} {p}")
    if pkg.get("annotated_images"):
        print("\nANNOTATED IMAGES (colour key + stats drawn on):")
        for v, p in pkg["annotated_images"].items():
            print(f"  {v:6s} {p}")
    elif pkg.get("note"):
        print("\nNOTE:", pkg["note"])
    if pkg.get("render_error"):
        print("\nRENDER ERROR:", pkg["render_error"][:400])


def _make_model(spec: str):
    from vmd_agent.bench import models
    if spec == "stats-reader":
        return models.StatsReaderModel()
    if spec == "constant":
        return models.ConstantModel()
    if spec == "random":
        return models.RandomModel()
    if spec == "oracle":
        return models.OracleModel()
    if spec.startswith("anthropic:"):
        return models.AnthropicModel(spec.split(":", 1)[1])
    raise SystemExit(f"unknown model '{spec}'")


def _bench_agent(args):
    from vmd_agent.bench.agent import suite, runner, agents
    if args.bench_cmd == "agent-suite":
        import glob
        bases = [{"id": f"b{i}", "topology": t, "trajectory": d}
                 for i, (t, d) in enumerate(args.base or [])]
        syn = sorted(glob.glob(f"{args.synthetic_dir}/*.pdb")) \
            if args.synthetic_dir else []
        out = suite.build_suite(
            args.out, bases, structures=args.structures or [],
            synthetic=syn, seed=args.seed, n_events=args.events,
            n_controls=args.controls, n_keyframes=args.keyframes,
            families=args.families)
        print(f"wrote {out['suite']['n_tasks']} tasks to {args.out}: "
              f"{out['suite']['families']}")
    elif args.bench_cmd == "agent-preflight":
        from vmd_agent.bench.agent import preflight
        res = preflight.preflight(
            args.arms or ["vmd_agent"], vmd_path=args.vmd,
            allow_exec=args.allow_exec, suite_dir=args.suite,
            out_dir=args.out_dir,
            model=(args.model.split(":", 1)[1] if args.model else None),
            live_api=args.live_api,
            require_container=not args.no_require_container)
        print(preflight.report_text(res))
        if not res["ready"]:
            raise SystemExit(2)
    elif args.bench_cmd == "agent-plan":
        _print(runner.plan_agent_run(
            args.suite, args.labels, repeats=args.repeats,
            avg_turns=args.avg_turns, price_in=args.price_in,
            price_out=args.price_out))
    else:
        truth = suite.load_suite(args.suite)["truth"]
        known = {"oracle": lambda: agents.OracleAgent(truth),
                 "sloppy": agents.SloppyAgent,
                 "reference": agents.ReferenceAgent}
        runs = [{"label": n, "agent": known[n](), "arm": "vmd_agent"}
                for n in args.baselines or []]
        if args.model:
            if not args.model.startswith("anthropic:"):
                raise SystemExit("--model must look like anthropic:<model-id>")
            try:
                import anthropic
            except ImportError as e:
                raise SystemExit("pip install anthropic to run a model") from e
            mid = args.model.split(":", 1)[1]
            for arm in args.arms or ["vmd_agent"]:
                runs.append({"label": f"{mid}@{arm}", "arm": arm,
                             "agent": agents.LLMAgent(anthropic.Anthropic(),
                                                      mid)})
        if not runs:
            raise SystemExit("nothing to run: pass --baselines and/or --model")
        if not args.skip_preflight:
            from vmd_agent.bench.agent import preflight
            res = preflight.preflight(
                sorted({r["arm"] for r in runs}), vmd_path=args.vmd,
                allow_exec=args.allow_exec, suite_dir=args.suite,
                out_dir=args.out_dir,
                model=(args.model.split(":", 1)[1] if args.model else None),
                require_container=not args.no_require_container)
            if not res["ready"]:
                print(preflight.report_text(res))
                raise SystemExit("preflight failed (see above); fix it or "
                                 "pass --skip-preflight")
        runner.run_agent_benchmark(
            args.suite, runs, args.out_dir, repeats=args.repeats,
            allow_exec=args.allow_exec, vmd_path=args.vmd,
            max_steps=args.max_steps, families=args.families,
            progress=lambda m: print(m, flush=True))
        print(open(f"{args.out_dir}/summary.md").read())


def _bench(args):
    from vmd_agent import bench
    from vmd_agent.bench import sampling, rating_study, conditions
    if args.bench_cmd.startswith("agent-"):
        return _bench_agent(args)
    if args.bench_cmd == "truth":
        _print(bench.ground_truth(args.structure))
    elif args.bench_cmd == "run":
        import glob
        structures = list(args.structures)
        groups = {p: "real" for p in structures}
        if args.synthetic_dir:
            syn = sorted(glob.glob(f"{args.synthetic_dir}/*.pdb"))
            groups.update({p: "synthetic" for p in syn})
            structures += syn
        conds = args.conditions or conditions.DEFAULT_CONDITIONS
        if args.dry_run:
            _print(bench.plan_benchmark(
                structures, conds, n_repeats=args.repeats,
                price_in_per_mtok=args.price_in,
                price_out_per_mtok=args.price_out))
            return
        s = bench.run_benchmark(
            structures, _make_model(args.model), args.out_dir,
            conditions=conds, renderer=args.renderer,
            n_repeats=args.repeats, render=not args.no_render,
            groups=groups, progress=lambda m: print(m, flush=True))
        print(open(f"{s['out_dir']}/summary.md").read())
    elif args.bench_cmd == "synth":
        items = bench.synth.generate_set(args.n, args.out, seed=args.seed)
        print(f"wrote {len(items)} structures + design.json to {args.out}")
        if not args.no_validate:
            v = bench.synth.validate_generator(items)
            print("generator vs measured truth (fraction agreeing):")
            for k, x in v["agreement"].items():
                print(f"  {k:18s} {x:.2f}")
    elif args.bench_cmd == "events":
        base = bench.events.load_real_positions(args.topology, args.trajectory)
        nc = bench.events.negative_control(base, n_frames=args.frames, k=args.k)
        print(f"negative control (no event): {nc['change_points_detected']} "
              f"change point(s) in {nc['n_frames']} frames "
              f"({nc['per_100_frames']:.2f}/100)")
        st = bench.events.event_study(base, n_frames=args.frames, k=args.k,
                                      n_trials=args.trials, seed=args.seed)
        print(bench.events.table_markdown(st))
    elif args.bench_cmd == "sampling":
        st = sampling.simulate_sampling_study(
            n_frames=args.n_frames, k=args.k, n_trials=args.trials,
            seed=args.seed)
        print(sampling.table_markdown(st))
    elif args.bench_cmd == "rating-sheet":
        _print(rating_study.make_rating_sheet(
            args.structures, args.out_dir, vmd_path=args.vmd))
    elif args.bench_cmd == "rating-summary":
        _print(rating_study.summarize_ratings(args.ratings_csv,
                                              args.key_json))


def main(argv=None):
    p = argparse.ArgumentParser(prog="vmd-agent",
                                description="Agentic VMD toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe"); sp.add_argument("--vmd")
    sp = sub.add_parser("inspect"); sp.add_argument("paths", nargs="+")
    sp = sub.add_parser("detect")
    sp.add_argument("topology"); sp.add_argument("--traj")
    sp = sub.add_parser("recipe")
    sp.add_argument("topology"); sp.add_argument("--traj")
    sp.add_argument("--style", default="publication")
    sp.add_argument("--bg", default="white"); sp.add_argument("-o", "--out")
    sp.add_argument("--water", action="store_true")
    sp = sub.add_parser("analyze")
    sp.add_argument("topology"); sp.add_argument("trajectory")
    sp.add_argument("--do", nargs="+", default=["rmsd", "rgyr"])
    sp.add_argument("--sel", default="protein"); sp.add_argument("--sel2")
    sp.add_argument("--cutoff", type=float, default=4.0)
    sp.add_argument("--step", type=int, default=1); sp.add_argument("--out-dir")
    sp.add_argument("--unwrap", action="store_true",
                    help="make the selection whole across periodic boundaries")
    sp.add_argument("--dt-ps", type=float,
                    help="real time between saved frames (overrides the header)")
    sp = sub.add_parser("render")
    sp.add_argument("topology"); sp.add_argument("--traj")
    sp.add_argument("-o", "--out", default="vmd_render.png")
    sp.add_argument("--frame", type=int, default=-1); sp.add_argument("--vmd")
    sp = sub.add_parser("stats", help="bond/link counts and colour key for a structure")
    sp.add_argument("topology"); sp.add_argument("--traj")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("annotate", help="draw colour key + stats onto an image")
    sp.add_argument("image"); sp.add_argument("--topology"); sp.add_argument("--traj")
    sp.add_argument("--title", default=""); sp.add_argument("-o", "--out")
    sp.add_argument("--panel-side", choices=["right", "left"], default="right")
    sp = sub.add_parser("reps", help="list VMD representations and when to use them")
    sp.add_argument("--category", choices=["backbone", "atomic", "surface", "special"])
    sp.add_argument("--name", help="full detail for one representation")
    sp = sub.add_parser("fetch", help="download a structure (PDB ID / UniProt / URL)")
    sp.add_argument("identifier")
    sp.add_argument("--out-dir", default="structures")
    sp.add_argument("--source", default="auto",
                    choices=["auto", "rcsb", "alphafold", "url"])
    sp.add_argument("--format", dest="fmt", default="auto",
                    choices=["auto", "pdb", "cif"])
    sp = sub.add_parser("search", help="find PDB IDs by keyword")
    sp.add_argument("query", nargs="+"); sp.add_argument("--limit", type=int, default=10)
    sp = sub.add_parser("show",
                        help="fetch from the web, then render + interpret it")
    sp.add_argument("identifier")
    sp.add_argument("--out-dir", default="vmd_agent_output")
    sp.add_argument("--source", default="auto",
                    choices=["auto", "rcsb", "alphafold", "url"])
    sp.add_argument("--views", nargs="+",
                    default=["front", "side", "top", "iso"])
    sp.add_argument("--style", default="publication")
    sp.add_argument("--bg", default="white")
    sp.add_argument("--water", action="store_true"); sp.add_argument("--vmd")
    sp.add_argument("--focus", default="overview",
                    choices=["overview", "fold", "interactions", "surface",
                             "pocket", "performance"])
    sp.add_argument("--rep", help="force a representation, e.g. QuickSurf")
    sp.add_argument("--renderer", default="auto",
                    choices=["auto", "vmd", "matplotlib"])
    sp = sub.add_parser("visualize")
    sp.add_argument("topology"); sp.add_argument("--traj")
    sp.add_argument("--out-dir", default="vmd_agent_output")
    sp.add_argument("--views", nargs="+", default=["front", "side", "top"])
    sp.add_argument("--style", default="publication"); sp.add_argument("--bg", default="white")
    sp.add_argument("--no-render", action="store_true"); sp.add_argument("--vmd")
    sp.add_argument("--focus", default="overview",
                    choices=["overview", "fold", "interactions", "surface",
                             "pocket", "performance"])
    sp.add_argument("--rep", help="force a representation, e.g. QuickSurf")
    sp.add_argument("--renderer", default="auto",
                    choices=["auto", "vmd", "matplotlib"])
    sp = sub.add_parser("report")
    sp.add_argument("session_dir"); sp.add_argument("--out")
    sp.add_argument("--title", default="VMD-Agent Analysis Report")

    sp = sub.add_parser("probe-video",
                        help="read a video's metadata and prove it decodes")
    sp.add_argument("video")
    sp.add_argument("--count-frames", action="store_true",
                    help="exact frame count by decoding (slower)")

    sp = sub.add_parser("interpret-video",
                        help="verify a video and extract stills to interpret")
    sp.add_argument("video")
    sp.add_argument("-n", "--n-frames", type=int, default=9)
    sp.add_argument("--out-dir")
    sp.add_argument("--timestamps", nargs="+", type=float,
                    help="sample these video times (s) instead of a even span")
    sp.add_argument("--stride", type=int, default=1)
    sp.add_argument("--first-frame", type=int, default=0)
    sp.add_argument("--time-per-frame", type=float,
                    help="simulation time per saved trajectory frame")
    sp.add_argument("--time-unit", default="ns")
    sp.add_argument("--count-frames", action="store_true")

    sp = sub.add_parser("keyframes",
                        help="pick event-aware keyframes from a trajectory")
    sp.add_argument("topology"); sp.add_argument("trajectory")
    sp.add_argument("-k", type=int, default=9)
    sp.add_argument("--sel", default="protein"); sp.add_argument("--sel2")
    sp.add_argument("--step", type=int, default=1)
    sp.add_argument("--z-min", type=float, default=6.0)
    sp.add_argument("--out-dir"); sp.add_argument("--render", action="store_true")
    sp.add_argument("--renderer", default="auto",
                    choices=["auto", "vmd", "matplotlib"])

    sp = sub.add_parser("claims",
                        help="verify statements against measurements")
    sp.add_argument("topology"); sp.add_argument("claims", nargs="+")
    sp.add_argument("--traj"); sp.add_argument("--step", type=int, default=1)

    sp = sub.add_parser("validate",
                        help="cross-check analysis against independent NumPy")
    sp.add_argument("topology"); sp.add_argument("trajectory")
    sp.add_argument("--sel", default="protein"); sp.add_argument("--sel2")
    sp.add_argument("--cutoff", type=float, default=4.5)

    sp = sub.add_parser("validate-dssp",
                        help="compare DSSP with PDB HELIX/SHEET records")
    sp.add_argument("ids", nargs="+", help="PDB IDs (downloaded) or .pdb files")
    sp.add_argument("--cache", default="pdb_cache")

    sp = sub.add_parser("provenance",
                        help="re-hash recorded inputs/outputs of a run")
    sp.add_argument("path")

    sp = sub.add_parser("mcp-check", help="check an MCP server install the way a "
                        "real client uses it (needs the mcp SDK, Python >= 3.10)")
    sp.add_argument("--roots", nargs="+", help="allowed root directories to give the server")
    sp.add_argument("--vmd", help="VMD launcher or install directory to give the server (VMD_BIN)")
    sp.add_argument("--env", nargs="*", default=[], metavar="KEY=VALUE",
                    help="extra environment for the server, as a client's env block would")
    sp.add_argument("--command", help="server command a client will run "
                    "(default: this Python, -m vmd_agent.server)")
    sp.add_argument("--args", nargs="*", help="arguments for --command")
    sp.add_argument("--render", action="store_true",
                    help="also render a tiny structure with VMD through the server")
    sp = sub.add_parser("renderers", help="list drawing backends and status")
    sp.add_argument("--vmd")

    sp = sub.add_parser("bench", help="grounded-interpretation benchmark")
    bsub = sp.add_subparsers(dest="bench_cmd", required=True)
    b = bsub.add_parser("truth", help="ground truth for one structure")
    b.add_argument("structure")
    b = bsub.add_parser("run", help="evaluate a model on structures")
    b.add_argument("structures", nargs="+")
    b.add_argument("--out-dir", default="bench_out")
    b.add_argument("--model", default="stats-reader",
                   help="stats-reader | constant | random | oracle | "
                        "anthropic:<model-id>")
    b.add_argument("--conditions", nargs="+",
                   choices=sorted(__import__("vmd_agent.bench.conditions", fromlist=["x"]).CONDITIONS))
    b.add_argument("--renderer", default="auto",
                   choices=["auto", "vmd", "matplotlib"])
    b.add_argument("--repeats", type=int, default=1)
    b.add_argument("--no-render", action="store_true")
    b.add_argument("--synthetic-dir",
                   help="also evaluate every .pdb here as group 'synthetic' "
                        "(see `bench synth`); the others are group 'real'")
    b.add_argument("--dry-run", action="store_true",
                   help="count calls and estimate tokens; call no model")
    b.add_argument("--price-in", type=float,
                   help="USD per million input tokens (for --dry-run)")
    b.add_argument("--price-out", type=float,
                   help="USD per million output tokens (for --dry-run)")
    b = bsub.add_parser("synth", help="generate novel, contamination-free "
                                       "structures with validated truth")
    b.add_argument("n", type=int); b.add_argument("--out", default="synth")
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--no-validate", action="store_true")
    b = bsub.add_parser("events", help="uniform vs event-aware keyframes on "
                                       "real noise with injected events")
    b.add_argument("topology"); b.add_argument("trajectory")
    b.add_argument("--trials", type=int, default=100)
    b.add_argument("--frames", type=int, default=300)
    b.add_argument("-k", type=int, default=9)
    b.add_argument("--seed", type=int, default=0)
    b = bsub.add_parser("sampling",
                        help="simulate uniform vs event-aware frame selection")
    b.add_argument("--n-frames", type=int, default=1000)
    b.add_argument("-k", type=int, default=9)
    b.add_argument("--trials", type=int, default=200)
    b.add_argument("--seed", type=int, default=0)
    fam = ["measure", "event", "diagnosis", "selection", "keyframes",
           "report"]
    b = bsub.add_parser("agent-suite", help="generate automation tasks with "
                                            "known answers")
    b.add_argument("--out", required=True)
    b.add_argument("--base", nargs=2, action="append",
                   metavar=("TOPOLOGY", "TRAJECTORY"),
                   help="a real trajectory (repeat for several)")
    b.add_argument("--structures", nargs="*")
    b.add_argument("--synthetic-dir")
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--events", type=int, default=6)
    b.add_argument("--controls", type=int, default=2)
    b.add_argument("--keyframes", type=int, default=3)
    b.add_argument("--families", nargs="+", choices=fam)
    b = bsub.add_parser("agent-run", help="run agents on a task suite")
    b.add_argument("--suite", required=True)
    b.add_argument("--out-dir", default="agent_bench_out")
    b.add_argument("--baselines", nargs="*",
                   choices=["oracle", "sloppy", "reference"],
                   help="scripted agents (no model, no network)")
    b.add_argument("--model", help="anthropic:<model-id>")
    b.add_argument("--arms", nargs="+", choices=sorted(
        __import__("vmd_agent.bench.agent.tools", fromlist=["x"]).ARMS))
    b.add_argument("--repeats", type=int, default=1)
    b.add_argument("--max-steps", type=int, default=30)
    b.add_argument("--allow-exec", action="store_true",
                   help="allow model-written code (python/Tcl); only inside a "
                        "container or VM")
    b.add_argument("--vmd")
    b.add_argument("--families", nargs="+", choices=fam)
    b.add_argument("--skip-preflight", action="store_true")
    b.add_argument("--no-require-container", action="store_true",
                   help="allow model-written code outside a container "
                        "(only on a disposable VM)")
    b = bsub.add_parser("agent-preflight", help="check that a run can work: "
                        "VMD, key, container, selections, secrets")
    b.add_argument("--arms", nargs="+", choices=sorted(
        __import__("vmd_agent.bench.agent.tools", fromlist=["x"]).ARMS))
    b.add_argument("--vmd")
    b.add_argument("--allow-exec", action="store_true")
    b.add_argument("--suite")
    b.add_argument("--out-dir")
    b.add_argument("--model", help="anthropic:<model-id>")
    b.add_argument("--live-api", action="store_true",
                   help="make one tiny API call to prove the key and model work")
    b.add_argument("--no-require-container", action="store_true")
    b = bsub.add_parser("agent-plan", help="estimate calls, tokens, cost")
    b.add_argument("--suite", required=True)
    b.add_argument("--labels", type=int, default=1,
                   help="number of (model, arm) combinations")
    b.add_argument("--repeats", type=int, default=1)
    b.add_argument("--avg-turns", type=int, default=8)
    b.add_argument("--price-in", type=float)
    b.add_argument("--price-out", type=float)
    b = bsub.add_parser("rating-sheet",
                        help="build a blinded expert-rating sheet (needs VMD)")
    b.add_argument("structures", nargs="+"); b.add_argument("--out-dir",
                                                            default="rating")
    b.add_argument("--vmd")
    b = bsub.add_parser("rating-summary", help="unblind and analyse ratings")
    b.add_argument("ratings_csv"); b.add_argument("key_json")

    args = p.parse_args(argv)
    try:

        if args.cmd == "mcp-check":
            from vmd_agent import mcp_check
            res = mcp_check.check_mcp_server(
                roots=args.roots, vmd=args.vmd,
                extra_env=dict(kv.split("=", 1) for kv in args.env),
                command=args.command, args=args.args, render=args.render)
            print(mcp_check.report_text(res))
            return 0 if res["ready"] else 2
        if args.cmd == "probe":
            _print(auto_mod.probe_environment(args.vmd))
        elif args.cmd == "inspect":
            _print(inspection.inspect_files(args.paths))
        elif args.cmd == "detect":
            _print(detect_mod.detect_system(args.topology, args.traj))
        elif args.cmd == "recipe":
            det = detect_mod.detect_system(args.topology, args.traj)
            r = recipes.generate_visualization_recipe(
                det, style=args.style, background=args.bg,
                show_water=args.water, out_path=args.out)
            if args.out:
                print(f"# recipe written to {r['written_to']}")
            print(r["tcl"])
        elif args.cmd == "analyze":
            _print(analysis.analyze_trajectory(
                args.topology, args.trajectory, analyses=args.do,
                selection=args.sel, sel2=args.sel2, cutoff=args.cutoff,
                step=args.step, out_dir=args.out_dir, unwrap=args.unwrap,
                dt_ps=args.dt_ps))
        elif args.cmd == "render":
            det = detect_mod.detect_system(args.topology, args.traj)
            _print(render_mod.render_image(args.topology, args.traj,
                   frame=args.frame, detection=det, out_png=args.out,
                   vmd_path=args.vmd))
        elif args.cmd == "stats":
            from vmd_agent.structure import stats as stats_mod, detect as d_mod
            from vmd_agent import auto as a_mod
            st = stats_mod.structure_stats(args.topology, args.traj)
            if args.json:
                _print(st)
            else:
                print("STRUCTURE STATISTICS")
                for l in stats_mod.stats_caption(st):
                    print("  ", l)
                det = d_mod.detect_system(args.topology, args.traj)
                print("\nCOLOUR KEYS")
                for ck in a_mod.build_color_keys(det):
                    print(f"  {ck['method']} — {ck['description']}")
                    for e in ck["entries"]:
                        print(f"     {e['hex']}  {e['color']:9s} {e['label']}")
        elif args.cmd == "annotate":
            from vmd_agent.visual import annotate as ann_mod
            from vmd_agent.structure import stats as stats_mod
            from vmd_agent.structure import detect as d_mod
            from vmd_agent import auto as a_mod
            ck, sl, ll = [], [], []
            if args.topology:
                det = d_mod.detect_system(args.topology, args.traj)
                ck = a_mod.build_color_keys(det); ll = a_mod.visual_legend(det)
                sl = stats_mod.stats_caption(
                    stats_mod.structure_stats(args.topology, args.traj))
            _print(ann_mod.annotate_image(args.image, color_keys=ck, stats_lines=sl,
                                          legend_lines=ll, title=args.title,
                                          out_path=args.out,
                                          panel_side=args.panel_side))
        elif args.cmd == "reps":
            from vmd_agent.visual import representations as reps_mod
            if args.name:
                _print(reps_mod.describe_representation(args.name))
            else:
                cat = reps_mod.list_representations(args.category)
                for cname, blurb in cat["categories"].items():
                    if args.category and cname != args.category:
                        continue
                    print(f"\n=== {cname.upper()} — {blurb}")
                    for rname, r in cat["representations"].items():
                        if r["category"] != cname:
                            continue
                        print(f"  {rname:14s} {r['summary']}")
                        print(f"  {'':14s} {r['detail']}")
                        print(f"  {'':14s} best for: {', '.join(r['best_for'])}")
                        print(f"  {'':14s} vmd: {r['vmd_command']}")
                print("\n=== COLOUR METHODS")
                for k, v in cat["colour_methods"].items():
                    print(f"  {k:12s} {v}")
                print("\n=== FOCUS PRESETS (--focus)")
                for k, v in cat["focus_plans"].items():
                    print(f"  {k:13s} {v}")
        elif args.cmd == "fetch":
            from vmd_agent.inputs import fetch as fetch_mod
            _print(fetch_mod.fetch_structure(args.identifier, out_dir=args.out_dir,
                                             source=args.source,
                                             file_format=args.fmt))
        elif args.cmd == "search":
            from vmd_agent.inputs import fetch as fetch_mod
            _print(fetch_mod.search_pdb(" ".join(args.query), limit=args.limit))
        elif args.cmd == "show":
            pkg = auto_mod.fetch_and_visualize(
                args.identifier, out_dir=args.out_dir, source=args.source,
                views=tuple(args.views), style=args.style, background=args.bg,
                show_water=args.water, focus=args.focus, representation=args.rep,
                vmd_path=args.vmd, renderer=args.renderer)
            _print_brief(pkg)
        elif args.cmd == "visualize":
            pkg = auto_mod.visualize_and_interpret(
                args.topology, args.traj, out_dir=args.out_dir,
                views=tuple(args.views), style=args.style, background=args.bg,
                render=not args.no_render, focus=args.focus,
                representation=args.rep, vmd_path=args.vmd,
                renderer=args.renderer)
            _print_brief(pkg)
        elif args.cmd == "probe-video":
            _print(media.probe_video(args.video, count_frames=args.count_frames))
        elif args.cmd == "interpret-video":
            pkg = media.interpret_video(
                args.video, n_frames=args.n_frames, out_dir=args.out_dir,
                timestamps=args.timestamps, stride=args.stride,
                first_frame=args.first_frame, time_per_frame=args.time_per_frame,
                time_unit=args.time_unit, count_frames=args.count_frames)
            _print(pkg)
        elif args.cmd == "keyframes":
            _print(auto_mod.select_keyframes(
                args.topology, args.trajectory, k=args.k, selection=args.sel,
                sel2=args.sel2, step=args.step, z_min=args.z_min,
                out_dir=args.out_dir, render=args.render,
                renderer=args.renderer))
        elif args.cmd == "claims":
            from vmd_agent.evidence import claims as claims_mod
            r = claims_mod.verify_claims(args.topology, args.claims,
                                         args.traj, step=args.step)
            for x in r["results"]:
                text = (x["claim"] or {}).get("text") or str(x["claim"])
                print(f"{x['verdict'].upper():13s} {text}\n{'':13s} "
                      f"{x['explanation']}")
            print("\n" + json.dumps(r["counts"]) + "  contradiction rate: "
                  + str(r["contradiction_rate"]))
        elif args.cmd == "validate":
            from vmd_agent.evidence import validation
            r = validation.cross_check(args.topology, args.trajectory,
                                       selection=args.sel, sel2=args.sel2,
                                       cutoff=args.cutoff)
            print(validation.table_markdown(r) if r.get("rows") else r)
            print("AGREE" if r.get("ok") else "DISAGREEMENT — investigate")
            print(r.get("note", ""))
        elif args.cmd == "validate-dssp":
            from vmd_agent.evidence import validation
            files = [i for i in args.ids if i.lower().endswith(".pdb")]
            if files and len(files) == len(args.ids):
                _print([validation.dssp_vs_records(f) for f in files])
            else:
                _print(validation.dssp_benchmark(args.ids, args.cache))
        elif args.cmd == "provenance":
            from vmd_agent.evidence import provenance
            _print(provenance.verify_provenance(args.path))
        elif args.cmd == "renderers":
            from vmd_agent.visual.renderers import list_renderers
            _print(list_renderers(args.vmd))
        elif args.cmd == "bench":
            _bench(args)
        elif args.cmd == "report":
            s = report_mod.Session(args.session_dir)
            r = report_mod.assemble_report(s.data, title=args.title,
                                           out_path=args.out)
            if args.out:
                print(f"# report written to {r['written_to']}")
            else:
                print(r["markdown"])
        return 0
    except KeyboardInterrupt:
        print("vmd-agent: interrupted", file=sys.stderr)
        return 130
    except Exception as e:                        # noqa: BLE001
        # A bad path or argument is a user error, not a crash: say so
        # briefly. VMD_AGENT_DEBUG=1 re-raises for the full traceback.
        if os.environ.get("VMD_AGENT_DEBUG"):
            raise
        print(f"vmd-agent: error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
