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

from .analysis import NOT_GRADED, POOLING_RULE, SUCCESS, ArmSummary, Report

def _pct(v: float | None) -> str:
    return "  n/a" if v is None else f"{v:5.0%}"


def _num(v: float | None, width: int = 6) -> str:
    return "n/a".rjust(width) if v is None else f"{v:{width},.1f}"


def render(rows: list[dict[str, Any]], manifest: dict[str, Any] | None = None,
           report: Report | None = None, glossary: bool = False,
           sort: str = "score") -> str:
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
    # Every table below walks this one order, so "who won" reads the same way
    # down the whole page instead of resetting to alphabetical each section.
    order = report.ranked(sort)

    lines: list[str] = []
    model = manifest.get("model") or rows[0].get("model", "?")
    report_class = rows[0].get("report_class", "?")
    lines.append(f"{manifest.get('id', 'results')}  [{report_class}]  model={model}")
    lines.append(f"{len(rows)} runs across {len(arms)} arms, "
                 f"{len({r['task_id'] for r in rows})} tasks")
    lines.append("")

    # --- what each arm is -------------------------------------------------
    # Printed before the numbers: a table of arm codes means nothing to a reader
    # who does not already know the design, and the codes are the least
    # informative thing on the page.
    described = [(a.arm, a.name, a.description) for a in order if a.description]
    if described:
        lines += ["  the arms — what was actually compared:"]
        for code, name, text in described:
            lines.append(f"    {code:<9} {name}")
            lines.append(f"    {'':<9} {text}")
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

    # --- the verdict ------------------------------------------------------
    # First, because it is the question everyone opens the report to answer.
    # It carries its own caveats: a composite always produces a ranking, and
    # saying which parts of it are real is the whole job.
    from .winner import render_text as render_verdict
    lines += [render_verdict(report, report.verdict()), ""]

    # --- main table -------------------------------------------------------
    lines.append(f"  ranked by {sort}:")
    header = (f"  {'arm':<30} {'success':>7} {'lift':>6} {'turns':>6} {'calls':>6} "
              f"{'static':>8} {'trunc':>6} {'harm':>5}")
    lines += [header, "  " + "-" * (len(header) - 2)]
    for arm in order:
        lift = report.lift(arm.arm)
        lines.append(
            f"  {arm.label[:30]:<30} {_pct(arm.success_rate)} "
            f"{('  n/a' if lift is None else f'{lift:+5.0%}')} "
            f"{_num(arm.mean('turns'))} {_num(arm.mean('calls'))} "
            f"{_num(arm.mean('static_tokens'), 8)} "
            f"{_pct(arm.truncation_rate)} {arm.harm_events:>5}"
        )

    # --- by task class ----------------------------------------------------
    classes = report.task_classes
    if len(classes) > 1:
        lines += ["", "  success by task class (RQ4 — does the ranking reverse?):"]
        lines.append("    " + "arm".ljust(30) + "".join(c.rjust(9) for c in classes))
        for arm in order:
            per = arm.by_class()
            lines.append("    " + arm.label[:30].ljust(30)
                         + "".join(_pct(per.get(c)).rjust(9) for c in classes))

    # --- cost -------------------------------------------------------------
    pricing = report.pricing
    if pricing:
        lines += ["", "  cost (actual usage):"]
        lines.append(f"    {'arm':<30} {'total':>10} {'per success':>12} {'cached':>8}")
        for arm in order:
            per = arm.cost_per_success(pricing)
            hit = arm.cache_hit_rate() or 0.0
            lines.append(
                f"    {arm.label[:30]:<30} "
                f"{'$' + format(arm.cost(pricing).total_usd, '.4f'):>10} "
                f"{('$' + format(per, '.4f')) if per else 'n/a':>12} {hit:>7.0%}"
            )

    # --- classification ---------------------------------------------------
    # Success rate cannot separate an agent that fabricates from one that gives
    # up. These can: precision falls when it answers what it should decline,
    # recall falls when it declines what it should answer.
    if any(a.confusion.total for a in arms.values()):
        lines += ["", "  answer-or-abstain (higher is better, except FP):"]
        lines.append(f"    {'arm':<30} {'prec':>6} {'recall':>7} {'abstain':>8} "
                     f"{'F1':>6} {'acc':>6} {'bal-acc':>8} {'MCC':>7} "
                     f"{'TP/FP/TN/FN':>14}")
        for arm in order:
            c = arm.confusion
            if not c.total:
                continue
            lines.append(
                f"    {arm.label[:30]:<30} {_pct(c.precision)} {_pct(c.recall):>7} "
                f"{_pct(c.specificity):>8} "
                f"{_pct(c.f1)} {_pct(c.accuracy)} {_pct(c.balanced_accuracy):>8} "
                f"{('n/a' if c.mcc is None else f'{c.mcc:+.2f}'):>7} "
                f"{f'{c.tp}/{c.fp}/{c.tn}/{c.fn}':>14}"
            )
        lines.append("    abstain = of the tasks with NO valid answer, the share "
                     "correctly declined.")

    # --- effort -----------------------------------------------------------
    lines += ["", "  effort per run (mean):"]
    lines.append(f"    {'arm':<30} {'tokens':>9} {'in':>8} {'cached':>8} {'out':>7} "
                 f"{'reason':>7} {'secs':>6} {'turns':>6} {'calls':>6}")
    for arm in order:
        total_in = arm.mean("input_tokens") or 0.0
        out = arm.mean("output_tokens") or 0.0
        lines.append(
            f"    {arm.label[:30]:<30} {total_in + out:>9,.0f} {total_in:>8,.0f} "
            f"{arm.mean('cached_input_tokens') or 0:>8,.0f} {out:>7,.0f} "
            f"{arm.mean('reasoning_tokens') or 0:>7,.0f} "
            f"{arm.mean('wall_clock_seconds') or 0:>6.1f} "
            f"{arm.mean('turns') or 0:>6.1f} {arm.mean('calls') or 0:>6.1f}"
        )

    grand = sum((r["input_tokens"] + r["output_tokens"]) for r in rows)
    lines.append(f"    {'ALL':<30} {grand:>9,} tokens across {len(rows)} runs")

    # --- how each arm behaved ---------------------------------------------
    lines += _behaviour_section(report, order)

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

    # --- what the sweep justifies -----------------------------------------
    from .justify import effects, report_status
    if any("@" in n for n in arms):
        lines += ["", "  lint-rule evidence:"]
        lines.append(report_status(report))

    lines += ["", _footer(report_class, report.truncated_count)]
    if glossary:
        from .glossary import render_text
        lines += ["", render_text()]
    else:
        lines.append("  every term is explained by: harness report <dir> --glossary")
    return "\n".join(lines)


#: How many behavioural metrics get the full treatment. The rest are still
#: printed, just without the paragraph — a page of equally-weighted charts is
#: how a reader ends up ignoring all of them.
PROMOTED = 3


def _behaviour_section(report: Report, order: list[ArmSummary]) -> list[str]:
    """Why the success rates came out the way they did.

    Ordered by how much each metric actually separated the arms, so the section
    adapts to what the run found instead of walking a fixed list. A metric that
    came out identical everywhere explains nothing about why one packaging beat
    another, however interesting it is in the abstract.
    """
    from .metrics import Bucket, get

    ranked = report.metrics_by_spread(str(Bucket.MECHANISM))
    if not ranked:
        return []

    lines = ["", "  how each arm behaved — why the success rates came out this way:"]
    for name in ranked[:PROMOTED]:
        try:
            metric = get(name)
        except KeyError:
            continue
        lines.append("")
        lines.append(f"    {name.replace('_', ' ')}  ({metric.direction_note})")
        lines.append("    " + _wrap(metric.description, 72, "    "))
        for arm in order:
            value = arm.metric_mean(name)
            if value is not None:
                lines.append(f"      {arm.label[:32]:<32} {value:>10,.2f}")

    rest = ranked[PROMOTED:]
    if rest:
        lines += ["", "    the rest (lower spread across arms — they separated "
                  "the arms less):"]
        width = max(len(n) for n in rest)
        lines.append("      " + " " * width + "  "
                     + "".join(a.arm.rjust(10) for a in order))
        for name in rest:
            try:
                arrow = {"higher": "↑", "lower": "↓"}.get(get(name).better or "", " ")
            except KeyError:
                arrow = " "
            cells = "".join(
                (f"{v:,.2f}".rjust(10) if (v := arm.metric_mean(name)) is not None
                 else "n/a".rjust(10))
                for arm in order
            )
            lines.append(f"      {name:<{width}} {arrow} {cells}")
        lines.append("      ↑ higher is better   ↓ lower is better")

    constant = report.constant_metrics()
    if constant:
        names = ", ".join(f"{k} = {v:g}" for k, v in constant.items())
        lines.append("")
        lines.append("    " + _wrap(
            f"No variation across any run on: {names}. Showing these would "
            "imply a difference that is not there.", 72, "    "))
    return lines


def _wrap(text: str, width: int, indent: str) -> str:
    import textwrap
    return ("\n" + indent).join(textwrap.wrap(text, width))


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
    parts.append(POOLING_RULE)
    return "\n".join("  " + p for p in parts)
