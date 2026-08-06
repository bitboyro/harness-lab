"""Command line entry point.

Three commands matching the three output tiers:

    harness lint  <spec>              T1 — static, free, no model
    harness probe <pack> --spec <s>   T2 — a handful of runs, gold-free metrics
    harness plan  <plan.yaml>         cost projection and approval gate

Nothing here spends money without printing the projection first and asking.
"""

from __future__ import annotations

import argparse
import os

import yaml
import sys
from pathlib import Path

from .engine import lint as lint_mod
from .engine.axes import (
    Caching, DocBudget, ErrorDetail, McpRevision, ResponseShape, SchemaDetail,
    preset,
)
from .engine.compute import compute, report_footer
from .engine.generate import load_spec
from .engine.loop import AgentRunner
from .engine.methods import CodeFsMcp, DocsShell, EagerAllMcp, MetaToolsMcp, NoTools
from .engine.packaging import resolve
from .engine.planner import load_plan
from .engine.provider import ProviderConfig
from .engine.taskpack import load as load_pack

_METHODS = {
    "A1": EagerAllMcp, "B1": EagerAllMcp,
    "A2": MetaToolsMcp, "B2": MetaToolsMcp, "D3": MetaToolsMcp,
    "D1": CodeFsMcp, "D2": CodeFsMcp,
    "C1": DocsShell, "C2": DocsShell,
    "Z0": NoTools,
}

DEFAULT_PROBE_PRESETS = ("Z0", "A1", "A2", "C1", "D1")


def _base_axes(args: argparse.Namespace) -> dict:
    return dict(
        schema_detail=SchemaDetail(args.schema_detail),
        response_shape=ResponseShape(args.response_shape),
        error_detail=ErrorDetail(args.error_detail),
        doc_budget=DocBudget(args.doc_budget),
        surface_size=args.surface_size,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        temperature=args.temperature,
        caching=Caching(args.caching),
        repeats=args.repeats,
        mcp_revision=McpRevision(args.mcp_revision),
    )


# ---- T1 ------------------------------------------------------------------

def cmd_lint(args: argparse.Namespace) -> int:
    from .engine import rules
    rules.register_defaults()

    spec = load_spec(args.spec)
    card = lint_mod.scorecard(spec)

    print(f"{spec.title} v{spec.version} — {len(spec.operations)} operations\n")
    if not card.findings:
        print("  no findings")
    for f in card.findings:
        mark = "!" if f.confidence is lint_mod.Confidence.MEASURED else "?"
        print(f"  [{f.severity}]{mark} {f.rule_id}: {f.message}")
    print(f"\n{card.footer()}")
    return 0


# ---- T2 ------------------------------------------------------------------

def _mcp_executor_factory(pack, revision):
    """Build the transport-bound executor the MCP arms need.

    Connects once and reuses the client, so the legacy handshake is paid once
    per run rather than once per call — otherwise the cost comparison between
    revisions would be measuring our own client instead of the protocol.
    """
    from .engine.executors import McpToolCallExecutor
    from .engine.mcp import McpClient
    from .engine.mcp.transport import HttpTransport

    if not pack.api.mcp:
        return None

    def make(materials, _variant):
        transport = HttpTransport.from_env(
            pack.api.mcp.url,
            auth_type=pack.api.auth.type,
            auth_env=pack.api.auth.env,
            header_name=pack.api.auth.header_name,
        )
        client = McpClient(transport, revision)
        client.connect()
        return McpToolCallExecutor(client)

    return make


def cmd_probe(args: argparse.Namespace) -> int:
    from .engine.axes import McpRevision
    from .engine.field import run_pack
    from .engine.methods import register_defaults

    spec = load_spec(args.spec)
    base_url = os.environ.get("TARGET_BASE_URL")
    pack = load_pack(args.pack, base_url=base_url,
                     allow_production_writes=args.i_know_this_is_production)

    from .engine.providers import get as get_provider
    provider = get_provider(args.provider)

    # Resolve spec_revision: auto by asking the server, before spending anything.
    revision = McpRevision(args.mcp_revision)
    if pack.api.mcp and pack.api.mcp.spec_revision == "auto":
        from .engine.mcp import detect_revision
        from .engine.mcp.transport import probe_server
        revision = detect_revision(probe_server(pack.api.mcp.url))
        print(f"detected MCP revision: {revision.value}")

    axes = {**_base_axes(args), "mcp_revision": revision}
    presets = tuple(args.presets or DEFAULT_PROBE_PRESETS)

    if "Z0" not in presets:
        print("note: no Z0 in this run. Without the parametric baseline, field "
              "numbers cannot be read as lift — the model may already know this API.")

    runs = len(presets) * len(pack.tasks) * args.repeats
    in_price, out_price = provider.price_per_mtok(args.model)
    rough = runs * (32_000 / 1e6 * in_price + 4_000 / 1e6 * out_price)
    print(f"about to run {runs} runs across {len(presets)} variants — "
          f"rough projection ${rough:,.2f}")
    if not args.yes and not _confirm():
        print("aborted")
        return 1

    register_defaults(_mcp_executor_factory(pack, revision) or (lambda m, v: None))
    config = ProviderConfig(
        model=args.model, reasoning_effort=args.reasoning_effort,
        temperature=args.temperature, max_turns=args.max_turns,
        caching=args.caching == "on",
    )

    def progress(arm, task, trace, result):
        status = "truncated" if trace.truncated else result.outcome
        print(f"  {arm:<8} {task.id:<34} {status}")

    report = run_pack(
        pack, spec, provider, config,
        presets=presets,
        base_axes=axes,
        method_for=lambda name: _METHODS.get(name, EagerAllMcp)(),
        repeats=args.repeats,
        trace_dir=args.trace_dir,
        on_run=progress,
    )

    print()
    print(report.render())
    return 0


# ---- planning ------------------------------------------------------------

def cmd_plan(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    plan.validate_contrasts()
    if args.strict:
        plan.require_preregistration()

    from .engine.providers import get as get_provider
    estimate = plan.estimate(get_provider(args.provider))

    print(f"{plan.id}\n  {plan.rationale.strip()}\n")
    print(estimate.render())

    if args.approve:
        if not _confirm():
            print("\nnot approved")
            return 1
        plan.approve(estimate)
        print("\napproved for this matrix size")
    return 0


def cmd_rig(args: argparse.Namespace) -> int:
    """Generate a controlled rig: OpenAPI spec + task pack, sized deliberately.

    Core count is per-run, not a global constant, because different comparisons
    need different amounts of data. The power table prints alongside so the size
    is chosen against what it buys rather than inherited.
    """
    import json

    from .engine.taskpack import TaskPack
    from .experiment.domain import WorldShape, build_world, shape_for_cores
    from .experiment.openapi import build_spec
    from .experiment.power import Contrast, analyse, cores_for, report
    from .experiment.tasks import build_pack

    if args.for_contrast and args.target_mde:
        contrast = Contrast(args.for_contrast)
        needed = cores_for(contrast, args.target_mde, repeats=args.repeats)
        if needed is None:
            print(f"cannot reach {args.target_mde} pp on {contrast} at any "
                  "practical core count; relax the target or the design")
            return 1
        print(f"{contrast} at {args.target_mde} pp needs {needed} cores "
              f"({args.repeats} repeats) — using that")
        cores = needed
    else:
        cores = args.cores

    print()
    print(report(cores, repeats=args.repeats))
    print()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Grow the world to fit the requested cores. Too few would silently
    # invalidate the power table printed above.
    shape = shape_for_cores(cores, WorldShape(episodes_per_season=args.fan_out))
    world = build_world(args.seed, shape)
    spec = build_spec(args.surface_size)
    pack = build_pack(world, cores=cores, seed=args.seed,
                      openapi_path="./catalog.openapi.json")

    # Validate through the public loader — the rig is a consumer of the engine,
    # so a pack it cannot load is a bug in the rig, not a special case.
    loaded = TaskPack.parse(pack)

    (out / "catalog.openapi.json").write_text(json.dumps(spec, indent=2))
    (out / "pack.yaml").write_text(yaml.safe_dump(pack, sort_keys=False))

    operations = len(spec["paths"])
    print(f"wrote {out}/catalog.openapi.json  ({operations} paths, "
          f"surface_size={args.surface_size or 'core only'})")
    print(f"wrote {out}/pack.yaml            ({len(loaded.tasks)} tasks "
          f"from {cores} cores, seed={args.seed})")

    unanswerable = sum(1 for t in loaded.tasks if not t.answerable)
    print(f"  {unanswerable} unanswerable tasks (false-positive answering)")
    print(f"  fan-out {args.fan_out} episodes per season")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run the controlled rig across arms and persist everything."""
    from .engine.compute import compute
    from .engine.pricing import lookup, price_run
    from .engine.reporting import render
    from .engine.results import ResultStore, build_row
    from .engine.taskpack import TaskPack
    from .experiment.domain import WorldShape, build_world, shape_for_cores
    from .experiment.rig import run_one
    from .experiment.tasks import build_pack

    presets = tuple(args.presets or ("Z0", "A1", "A2", "C1", "D1"))
    # A sweep varies one property of the API while holding packaging fixed.
    # Each level is tagged onto the arm name so the report never averages
    # across it — that would answer the wrong question entirely.
    sweep_values = tuple(args.sweep_error_detail or ())
    shape = shape_for_cores(args.cores, WorldShape(episodes_per_season=args.fan_out))
    pack = TaskPack.parse(build_pack(build_world(args.seed, shape),
                                     cores=args.cores, seed=args.seed,
                                     difficulty=args.difficulty))

    tasks = list(pack.tasks)
    if args.classes:
        tasks = [t for t in tasks if str(t.task_class) in args.classes]
    if args.max_tasks:
        tasks = tasks[:args.max_tasks]

    store = ResultStore(args.out)
    done = store.completed() if args.resume else set()

    arm_specs = (
        [(f"{a}@{v}", a, {"error_detail": ErrorDetail(v)}) for a in presets
         for v in sweep_values]
        if sweep_values else [(a, a, {}) for a in presets]
    )
    planned = [
        (label, arm, overrides, task, repeat)
        for label, arm, overrides in arm_specs
        for task in tasks
        for repeat in range(args.repeats)
        if (label, task.id, repeat) not in done
        # Z1 pre-executes reads and hands them over; it has no tools, so it can
        # never complete a write. Running it on write tasks would spend money to
        # record a guaranteed 0% and drag its ceiling down with it — the ceiling
        # is only defined for synthesis.
        and not (arm == "Z1" and str(task.task_class) != "R")
    ]
    if done:
        print(f"resuming: {len(done)} runs already on disk, {len(planned)} to go")

    from .engine.providers import get as get_provider
    provider = get_provider(args.provider)
    pricing = lookup(args.model)
    rough = len(planned) * price_run(pricing, input_tokens=8_000,
                                     output_tokens=1_500).total_usd
    print(f"{len(planned)} runs — {len(presets)} arms x {len(tasks)} tasks "
          f"x {args.repeats} repeats. Rough projection ${rough:,.2f}")
    if not args.yes and not _confirm():
        print("aborted")
        return 1

    store.write_manifest(
        id=args.id, model=args.model, provider=args.provider,
        presets=list(presets), cores=args.cores, repeats=args.repeats,
        seed=args.seed, surface_size=args.surface_size, fan_out=args.fan_out,
        reasoning_effort=args.reasoning_effort, difficulty=args.difficulty,
        report_class=str(pack.pack.report_class), tasks=len(tasks),
        # The real count, not arms x tasks x repeats: some cells are skipped
        # deliberately (Z1 cannot do writes), and an inferred total makes the
        # ETA wrong for the whole run.
        planned=len(planned) + len(done), resumed=len(done),
    )

    axes = {**_base_axes(args), "surface_size": args.surface_size}
    config = ProviderConfig(
        model=args.model, reasoning_effort=args.reasoning_effort,
        temperature=args.temperature, max_turns=args.max_turns,
        caching=args.caching == "on",
    )

    import time as _time
    started_at = _time.time()

    for index, (label, arm, overrides, task, repeat) in enumerate(planned, 1):
        try:
            variant = preset(arm, **{**axes, **overrides})
            trace, grade = run_one(
                arm, variant, task, provider, config,
                seed=args.seed, shape=shape, surface_size=args.surface_size,
            )
            row = build_row(arm=label, task=task, repeat=repeat, trace=trace,
                            grade=grade, metrics=compute(trace),
                            report_class=str(pack.pack.report_class),
                            seed=args.seed)
            # Written immediately: a matrix that dies two thirds through must
            # leave two thirds of its results on disk, not nothing.
            store.record(row, trace)
            status = "truncated" if trace.truncated else str(grade.outcome)
            print(f"  {_progress(index, len(planned), started_at)} "
                  f"{label:<12} {task.id:<26} {status:<15} {len(trace.turns)}t",
                  # Unbuffered: redirected to a file, Python buffers stdout and
                  # the log silently lags minutes behind the actual run — which
                  # is exactly when you most want to see progress.
                  flush=True)
        except KeyboardInterrupt:
            print("\ninterrupted — results so far are on disk; --resume continues")
            break
        except Exception as e:  # noqa: BLE001 — one failed run must not end the matrix
            print(f"  {_progress(index, len(planned), started_at)} "
                  f"{label:<12} {task.id:<26} ERROR "
                  f"{type(e).__name__}: {str(e)[:50]}", flush=True)

    print()
    final = _build_report(store)
    print(render(list(store.rows()), store.manifest(), report=final))
    from .engine.stats import analyse as analyse_stats
    stats = analyse_stats(final)
    if stats.contrasts:
        print("\n  contrasts:")
        print(stats.render())
    print(f"\nresults: {args.out}/results.jsonl   traces: {args.out}/traces/")
    print(f"html:    harness report {args.out} --html {args.out}/report.html")
    return 0


def _build_report(store, *, mde_pp: float | None = None):
    """One analysis object for every renderer.

    The MDE is computed here and passed in: power lives in `experiment` and the
    engine must not import it (plan.md §2).
    """
    from .engine.analysis import Report

    manifest = store.manifest()
    if mde_pp is None and manifest.get("cores"):
        try:
            from .experiment.power import Contrast, analyse
            mde_pp = analyse(Contrast.MAIN_EFFECT, int(manifest["cores"]),
                             repeats=int(manifest.get("repeats", 1))).mde_pp
        except Exception:  # noqa: BLE001 — a missing MDE only drops one banner
            mde_pp = None
    return Report(rows=list(store.rows()), manifest=manifest, mde_pp=mde_pp)


def cmd_progress(args: argparse.Namespace) -> int:
    """Check a run in flight, from a second terminal, without disturbing it."""
    from .engine.progress import read

    progress = read(args.results)
    if not progress.done:
        print(f"no runs recorded yet in {args.results}")
        return 1
    print(progress.render())
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Render results written by a previous run. Re-runs nothing."""
    from .engine.reporting import render
    from .engine.results import ResultStore

    store = ResultStore(args.results)
    rows = list(store.rows())
    if not rows:
        print(f"no results in {args.results}")
        return 1

    report = _build_report(store)

    if args.html or args.charts:
        from .engine.html import build_charts, standalone_html
        if args.html:
            out = Path(args.html)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(standalone_html(report), encoding="utf-8")
            print(f"wrote {out}")
        if args.charts:
            charts_dir = Path(args.charts)
            charts_dir.mkdir(parents=True, exist_ok=True)
            for name, svg in build_charts(report).items():
                (charts_dir / f"{name}.svg").write_text(svg, encoding="utf-8")
            print(f"wrote {len(build_charts(report))} charts to {charts_dir}/")
        if not args.csv:
            return 0

    if args.csv:
        import csv
        import sys as _sys
        flat = [{k: v for k, v in r.items() if k != "metrics"} for r in rows]
        writer = csv.DictWriter(_sys.stdout, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
        return 0

    print(render(rows, store.manifest(), report=report))
    from .engine.stats import analyse as analyse_stats
    stats = analyse_stats(report)
    if stats.contrasts:
        print("\n  contrasts:")
        print(stats.render())
    return 0


def _progress(done: int, total: int, started_at: float) -> str:
    """`[ 42/270  16%  eta 21m]` — position, share, and time remaining.

    ETA from observed pace rather than a fixed estimate, because run duration
    varies several-fold by arm: a shell arm shelling out to curl is nothing like
    a single tool call.
    """
    import time
    elapsed = time.time() - started_at
    rate = elapsed / done if done else 0.0
    remaining = rate * (total - done)
    if remaining >= 3600:
        eta = f"{remaining / 3600:.1f}h"
    elif remaining >= 60:
        eta = f"{remaining / 60:.0f}m"
    else:
        eta = f"{remaining:.0f}s"
    return f"[{done:>4}/{total}  {done * 100 // total:>3}%  eta {eta:>4}]"


def _confirm() -> bool:
    if not sys.stdin.isatty():
        return False
    return input("proceed? [y/N] ").strip().lower() in ("y", "yes")


# ---- wiring --------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    lint_p = sub.add_parser("lint", help="T1: static agent-readiness scorecard")
    lint_p.add_argument("spec", type=Path)
    lint_p.set_defaults(func=cmd_lint)

    probe_p = sub.add_parser("probe", help="T2: a few runs, gold-free metrics")
    probe_p.add_argument("pack", type=Path)
    probe_p.add_argument("--spec", type=Path, required=True)
    probe_p.add_argument("--presets", nargs="*")
    probe_p.add_argument("--trace-dir", default="traces")
    probe_p.add_argument("--max-turns", type=int, default=12)
    probe_p.add_argument("--yes", action="store_true", help="skip the spend prompt")
    probe_p.add_argument("--i-know-this-is-production", action="store_true",
                         help="second gate on writes against a real system")
    probe_p.set_defaults(func=cmd_probe)

    rig_p = sub.add_parser("rig", help="generate the controlled rig, sized deliberately")
    rig_p.add_argument("--out", default="rig", help="output directory")
    rig_p.add_argument("--cores", type=int, default=40,
                       help="navigation cores; each yields 5 matched tasks. "
                            "Drives statistical power — see --for-contrast")
    rig_p.add_argument("--repeats", type=int, default=3,
                       help="repeats per task. Reduce measurement noise only; "
                            "they cannot substitute for cores")
    rig_p.add_argument("--for-contrast", choices=["main-effect", "within-class",
                                                  "interaction"],
                       help="size the rig for this comparison instead of --cores")
    rig_p.add_argument("--target-mde", type=float,
                       help="percentage points to detect, with --for-contrast")
    rig_p.add_argument("--seed", type=int, default=1)
    rig_p.add_argument("--surface-size", type=int, default=0,
                       help="pad with distractor operations; 0 = core only")
    rig_p.add_argument("--fan-out", type=int, default=12,
                       help="episodes per season; the blast radius on RW-fan tasks")
    rig_p.set_defaults(func=cmd_rig)

    run_p = sub.add_parser("run", help="run the controlled rig; persists everything")
    run_p.add_argument("--out", default="results", help="results directory")
    run_p.add_argument("--id", default="phase-0", help="label for this matrix")
    run_p.add_argument("--presets", nargs="*",
                       help="arms to run (default: Z0 A1 A2 C1 D1)")
    run_p.add_argument("--cores", type=int, default=3)
    run_p.add_argument("--fan-out", type=int, default=8)
    run_p.add_argument("--classes", nargs="*",
                       help="limit to task classes, e.g. R W-safe")
    run_p.add_argument("--max-tasks", type=int, help="cap tasks, for a smoke run")
    run_p.add_argument("--max-turns", type=int, default=12)
    run_p.add_argument("--seed", type=int, default=1)
    run_p.add_argument("--sweep-error-detail", nargs="*",
                       choices=[e.value for e in ErrorDetail],
                       help="run every arm once per error_detail level. Answers: "
                            "is fixing your error messages cheaper than shipping "
                            "a skill?")
    run_p.add_argument("--difficulty", default="standard",
                       choices=["standard", "hard"],
                       help="'standard' ceilinged at ~100%% for every arm; "
                            "'hard' makes the agent search rather than navigate")
    run_p.add_argument("--resume", action="store_true",
                       help="skip runs already in the results directory")
    run_p.add_argument("--yes", action="store_true", help="skip the spend prompt")
    run_p.set_defaults(func=cmd_run)

    progress_p = sub.add_parser("progress", help="how far along is a run")
    progress_p.add_argument("results", nargs="?", default="results")
    progress_p.set_defaults(func=cmd_progress)

    report_p = sub.add_parser("report", help="render stored results; re-runs nothing")
    report_p.add_argument("results", nargs="?", default="results")
    report_p.add_argument("--csv", action="store_true",
                          help="dump rows as CSV for your own analysis")
    report_p.add_argument("--html", metavar="PATH",
                          help="write a self-contained HTML report")
    report_p.add_argument("--charts", metavar="DIR",
                          help="write each chart as a standalone .svg")
    report_p.set_defaults(func=cmd_report)

    plan_p = sub.add_parser("plan", help="cost projection and approval")
    plan_p.add_argument("plan", type=Path)
    plan_p.add_argument("--approve", action="store_true")
    plan_p.add_argument("--strict", action="store_true",
                        help="require a pre-registered confirmatory/exploratory split")
    plan_p.set_defaults(func=cmd_plan)

    for sp in (probe_p, plan_p, run_p):
        sp.add_argument("--provider", default="openai")
        sp.add_argument("--model", default="gpt-5-mini")
        sp.add_argument("--reasoning-effort", default="low")
        sp.add_argument("--temperature", type=float, default=0.0)
        sp.add_argument("--caching", default="off", choices=[c.value for c in Caching])
        sp.add_argument("--repeats", type=int, default=1)
        sp.add_argument("--surface-size", type=int, default=0)
        sp.add_argument("--schema-detail", default="standard",
                        choices=[c.value for c in SchemaDetail])
        sp.add_argument("--response-shape", default="as-is",
                        choices=[c.value for c in ResponseShape])
        sp.add_argument("--error-detail", default="field-scoped",
                        choices=[c.value for c in ErrorDetail])
        sp.add_argument("--doc-budget", default="standard",
                        choices=[c.value for c in DocBudget])
        sp.add_argument("--mcp-revision", default="2026-07-28",
                        choices=[c.value for c in McpRevision])
    return p


def main(argv: list[str] | None = None) -> int:
    from .engine.env import find_and_load
    loaded = find_and_load()
    if loaded:
        # Names only. Reporting which credentials are in play is useful;
        # printing their values would put secrets in every terminal scrollback.
        print(f"loaded from .env: {', '.join(loaded)}", file=sys.stderr)

    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
