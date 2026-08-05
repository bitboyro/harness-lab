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

def cmd_probe(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    base_url = os.environ.get("TARGET_BASE_URL")
    pack = load_pack(args.pack, base_url=base_url,
                     allow_production_writes=args.i_know_this_is_production)

    from .engine.providers import get as get_provider
    provider = get_provider(args.provider)

    axes = _base_axes(args)
    presets = tuple(args.presets or DEFAULT_PROBE_PRESETS)
    runs = len(presets) * len(pack.tasks) * args.repeats

    in_price, out_price = provider.price_per_mtok(args.model)
    rough = runs * (32_000 / 1e6 * in_price + 4_000 / 1e6 * out_price)
    print(f"about to run {runs} calls across {len(presets)} variants — "
          f"rough projection ${rough:,.2f}")
    if not args.yes and not _confirm():
        print("aborted")
        return 1

    config = ProviderConfig(
        model=args.model, reasoning_effort=args.reasoning_effort,
        temperature=args.temperature, max_turns=args.max_turns,
        caching=args.caching == "on",
    )

    for name in presets:
        variant = preset(name, **axes)
        method = _METHODS.get(name, EagerAllMcp)()
        print(f"\n=== {name} ===")
        for task in pack.tasks:
            runner = AgentRunner(
                provider=provider, method=method, spec=spec, variant=variant,
                config=config,
                forbidden_calls=pack.safety.forbidden_calls + task.forbidden_calls,
                trace_dir=args.trace_dir,
            )
            trace = runner.run(task.id, task.prompt)
            values = compute(trace)
            summary = "  ".join(
                values[k].render() for k in
                ("turns", "argument_validity", "static_context_tokens")
                if k in values
            )
            status = "truncated" if trace.truncated else (trace.error or "ok")
            print(f"  {task.id}: {status}  {summary}")

    missing = pack.unavailable_metrics()
    if missing:
        print("\nnot measurable with this pack:")
        for metric, reason in sorted(missing.items()):
            print(f"  {metric} — {reason}")
    print(f"\n{report_footer(compute(trace))}")
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

    plan_p = sub.add_parser("plan", help="cost projection and approval")
    plan_p.add_argument("plan", type=Path)
    plan_p.add_argument("--approve", action="store_true")
    plan_p.add_argument("--strict", action="store_true",
                        help="require a pre-registered confirmatory/exploratory split")
    plan_p.set_defaults(func=cmd_plan)

    for sp in (probe_p, plan_p):
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
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
