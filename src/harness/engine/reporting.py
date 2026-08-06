"""Render stored results.

Reads the ledger back, so a report can be produced long after the run and
recomputed when the analysis changes. Nothing here re-runs anything.

Every table carries the caveats that make it readable honestly: what was
truncated, what is unvalidated, and which comparisons are refused outright.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .analysis import NOT_GRADED, SUCCESS, ArmSummary, Report

def _pct(v: float | None) -> str:
    return "  n/a" if v is None else f"{v:5.0%}"


def _num(v: float | None, width: int = 6) -> str:
    return "n/a".rjust(width) if v is None else f"{v:{width},.1f}"


def render(rows: list[dict[str, Any]], manifest: dict[str, Any] | None = None,
           report: Report | None = None) -> str:
    """The whole report, as text.

    Accepts a prebuilt `Report` so the text and HTML renderers cannot drift:
    both read one analysis object rather than each computing its own numbers.
    """
    if not rows and report is None:
        return "No results. Run `harness run` first."

    report = report or Report(rows=rows, manifest=manifest or {})
    rows = report.rows
    if not rows:
        return "No results. Run `harness run` first."
    manifest = report.manifest
    arms = report.arms

    lines: list[str] = []
    model = manifest.get("model") or rows[0].get("model", "?")
    report_class = rows[0].get("report_class", "?")
    lines.append(f"{manifest.get('id', 'results')}  [{report_class}]  model={model}")
    lines.append(f"{len(rows)} runs across {len(arms)} arms, "
                 f"{len({r['task_id'] for r in rows})} tasks")
    lines.append("")

    # --- refuse to pool ---------------------------------------------------
    # Arms with no MCP transport at all (Z0, the shell arms) carry a null
    # revision. That is an absence, not a different revision, and treating it
    # as one would make every run containing a control look unpoolable.
    worlds = report.worlds
    if report.pooling_refused:
        lines.append("REFUSING TO POOL — these rows describe different worlds:")
        for w in sorted(map(str, worlds)):
            lines.append(f"  {w}")
        lines.append("Split them by model / mcp_spec_revision / skill_condition "
                     "and report separately.")
        lines.append("")

    # --- baseline ---------------------------------------------------------
    baseline = report.baseline
    gate = report.z0_gate
    if baseline is None:
        lines.append("No Z0 baseline in this run — without it these numbers "
                     "cannot be read as lift.")
    elif report_class == "controlled":
        # The gate counts only *substantive* correct answers. With no tools,
        # correctly declining an unanswerable task is the expected behaviour —
        # scoring it as knowledge of the domain would fail every clean rig.
        passed, answered, gated = gate
        score = answered / gated if gated else 0.0
        verdict = "PASS" if passed else "FAIL — DOMAIN CONTAMINATED"
        lines.append(f"Z0 gate: {verdict} — {answered}/{gated} tasks answered "
                     f"correctly with no API access ({score:.0%})")
        if baseline != score:
            lines.append(f"  (Z0 'success' below reads {baseline:.0%} because it "
                         "also credits correct refusals, which the gate does not)")
    else:
        lines.append(f"Parametric baseline (Z0): {baseline:.0%}")
    lines.append("")

    # --- main table -------------------------------------------------------
    header = (f"  {'arm':<8} {'success':>7} {'lift':>6} {'turns':>6} {'calls':>6} "
              f"{'static':>8} {'trunc':>6} {'harm':>5}")
    lines += [header, "  " + "-" * (len(header) - 2)]
    for name, arm in sorted(arms.items()):
        lift = report.lift(name)
        lines.append(
            f"  {name:<8} {_pct(arm.success_rate)} "
            f"{('  n/a' if lift is None else f'{lift:+5.0%}')} "
            f"{_num(arm.mean('turns'))} {_num(arm.mean('calls'))} "
            f"{_num(arm.mean('static_tokens'), 8)} "
            f"{_pct(arm.truncation_rate)} {arm.harm_events:>5}"
        )

    # --- by task class ----------------------------------------------------
    classes = report.task_classes
    if len(classes) > 1:
        lines += ["", "  success by task class (RQ4 — does the ranking reverse?):"]
        lines.append("    " + "arm".ljust(8) + "".join(c.rjust(9) for c in classes))
        for name, arm in sorted(arms.items()):
            per = arm.by_class()
            lines.append("    " + name.ljust(8)
                         + "".join(_pct(per.get(c)).rjust(9) for c in classes))

    # --- cost -------------------------------------------------------------
    pricing = report.pricing
    if pricing:
        lines += ["", "  cost (actual usage):"]
        lines.append(f"    {'arm':<8} {'total':>10} {'per success':>12} {'cached':>8}")
        for name, arm in sorted(arms.items()):
            per = arm.cost_per_success(pricing)
            hit = arm.cache_hit_rate() or 0.0
            lines.append(
                f"    {name:<8} {'$' + format(arm.cost(pricing).total_usd, '.4f'):>10} "
                f"{('$' + format(per, '.4f')) if per else 'n/a':>12} {hit:>7.0%}"
            )

    # --- safety -----------------------------------------------------------
    silent = {n: a.silent_failure_rate for n, a in arms.items()
              if a.silent_failure_rate}
    if silent:
        lines += ["", "  silent failures (confident and wrong, as a share of wrong):"]
        for name, rate in sorted(silent.items()):
            lines.append(f"    {name}: {rate:.0%}")

    errors = report.error_rows
    if errors:
        lines += ["", f"  {len(errors)} harness errors (excluded from rates):"]
        for r in errors[:5]:
            lines.append(f"    {r['arm']} {r['task_id']}: {str(r['error'])[:70]}")

    lines += ["", _footer(report_class, report.truncated_count)]
    return "\n".join(lines)


def _footer(report_class: str, truncated: int) -> str:
    parts = [
        "All metrics are unvalidated: their relationship to ground truth has "
        "not been established on the controlled rig."
        if report_class == "field" else
        "Controlled result. Programmatic grading only; writes graded on final "
        "server state, never on the transcript.",
    ]
    if truncated:
        parts.append(
            f"{truncated} runs hit max_turns and are excluded from success "
            "rates — a budget failure, not a wrong answer."
        )
    parts.append("Never pool across model, MCP revision, skill condition, or "
                 "report class.")
    return "\n".join("  " + p for p in parts)
