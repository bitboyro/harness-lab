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

from .pricing import ModelPricing, lookup, price_run

#: Outcomes excluded from success rates. Truncation is a budget failure and
#: ungraded is an absent assertion; neither is a wrong answer.
_NOT_GRADED = {"truncated", "ungraded"}
_SUCCESS = {"pass", "correct-refusal"}


@dataclass
class ArmSummary:
    arm: str
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def graded(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["outcome"] not in _NOT_GRADED]

    @property
    def success_rate(self) -> float | None:
        graded = self.graded
        if not graded:
            return None
        return sum(1 for r in graded if r["outcome"] in _SUCCESS) / len(graded)

    @property
    def truncation_rate(self) -> float:
        return (sum(1 for r in self.rows if r["truncated"]) / len(self.rows)
                if self.rows else 0.0)

    @property
    def silent_failure_rate(self) -> float | None:
        wrong = [r for r in self.graded if r["outcome"] == "fail"]
        if not wrong:
            return None
        return sum(1 for r in wrong if r["confident"]) / len(wrong)

    @property
    def harm_events(self) -> int:
        """Clobbered fields plus blocked attempts.

        A guard catching a destructive call does not make the call safe — on a
        real API there would be no guard, so the attempt is the finding.
        """
        return sum(1 for r in self.rows if r["clobbered"] or r["forbidden_attempts"])

    def mean(self, key: str) -> float | None:
        values = [r[key] for r in self.rows if r.get(key) is not None]
        return sum(values) / len(values) if values else None

    def cost(self, pricing: ModelPricing):
        from .pricing import Cost
        total = Cost()
        for r in self.rows:
            run = price_run(
                pricing,
                input_tokens=r["input_tokens"],
                cached_input_tokens=r["cached_input_tokens"],
                output_tokens=r["output_tokens"],
            )
            total = Cost(
                total.fresh_input_usd + run.fresh_input_usd,
                total.cached_input_usd + run.cached_input_usd,
                total.cache_write_usd + run.cache_write_usd,
                total.output_usd + run.output_usd,
                run.tier if run.tier == "long" else total.tier,
            )
        return total

    def cost_per_success(self, pricing: ModelPricing) -> float | None:
        successes = sum(1 for r in self.graded if r["outcome"] in _SUCCESS)
        return self.cost(pricing).total_usd / successes if successes else None

    def by_class(self) -> dict[str, float | None]:
        buckets: dict[str, list[dict]] = defaultdict(list)
        for r in self.graded:
            buckets[r["task_class"]].append(r)
        return {
            cls: sum(1 for r in rows if r["outcome"] in _SUCCESS) / len(rows)
            for cls, rows in sorted(buckets.items())
        }


def _pct(v: float | None) -> str:
    return "  n/a" if v is None else f"{v:5.0%}"


def _num(v: float | None, width: int = 6) -> str:
    return "n/a".rjust(width) if v is None else f"{v:{width},.1f}"


def render(rows: list[dict[str, Any]], manifest: dict[str, Any] | None = None) -> str:
    """The whole report."""
    if not rows:
        return "No results. Run `harness run` first."

    manifest = manifest or {}
    arms: dict[str, ArmSummary] = {}
    for row in rows:
        arms.setdefault(row["arm"], ArmSummary(row["arm"])).rows.append(row)

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
    worlds = {(r["model"], r["mcp_spec_revision"], r["skill_condition"],
               r["report_class"])
              for r in rows if r["mcp_spec_revision"] is not None}
    worlds |= {(r["model"], None, r["skill_condition"], r["report_class"])
               for r in rows if r["mcp_spec_revision"] is None
               and not any(x["mcp_spec_revision"] for x in rows)}
    if len(worlds) > 1:
        lines.append("REFUSING TO POOL — these rows describe different worlds:")
        for w in sorted(map(str, worlds)):
            lines.append(f"  {w}")
        lines.append("Split them by model / mcp_spec_revision / skill_condition "
                     "and report separately.")
        lines.append("")

    # --- baseline ---------------------------------------------------------
    z0 = arms.get("Z0")
    baseline = z0.success_rate if z0 else None
    if baseline is None:
        lines.append("No Z0 baseline in this run — without it these numbers "
                     "cannot be read as lift.")
    elif report_class == "controlled":
        # The gate counts only *substantive* correct answers. With no tools,
        # correctly declining an unanswerable task is the expected behaviour —
        # scoring it as knowledge of the domain would fail every clean rig.
        answered = sum(1 for r in z0.graded if r["outcome"] == "pass")
        gated = len(z0.graded)
        score = answered / gated if gated else 0.0
        verdict = "PASS" if score <= 0.05 else "FAIL — DOMAIN CONTAMINATED"
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
        lift = (arm.success_rate - baseline
                if baseline is not None and arm.success_rate is not None else None)
        lines.append(
            f"  {name:<8} {_pct(arm.success_rate)} "
            f"{('  n/a' if lift is None else f'{lift:+5.0%}')} "
            f"{_num(arm.mean('turns'))} {_num(arm.mean('calls'))} "
            f"{_num(arm.mean('static_tokens'), 8)} "
            f"{_pct(arm.truncation_rate)} {arm.harm_events:>5}"
        )

    # --- by task class ----------------------------------------------------
    classes = sorted({r["task_class"] for r in rows})
    if len(classes) > 1:
        lines += ["", "  success by task class (RQ4 — does the ranking reverse?):"]
        lines.append("    " + "arm".ljust(8) + "".join(c.rjust(9) for c in classes))
        for name, arm in sorted(arms.items()):
            per = arm.by_class()
            lines.append("    " + name.ljust(8)
                         + "".join(_pct(per.get(c)).rjust(9) for c in classes))

    # --- cost -------------------------------------------------------------
    try:
        pricing = lookup(model)
    except Exception:  # noqa: BLE001 — an unpriced model still reports everything else
        pricing = None
    if pricing:
        lines += ["", "  cost (actual usage):"]
        lines.append(f"    {'arm':<8} {'total':>10} {'per success':>12} {'cached':>8}")
        for name, arm in sorted(arms.items()):
            per = arm.cost_per_success(pricing)
            cached = arm.mean("cached_input_tokens")
            total_in = arm.mean("input_tokens")
            hit = cached / total_in if cached and total_in else 0.0
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

    errors = [r for r in rows if r["error"]]
    if errors:
        lines += ["", f"  {len(errors)} harness errors (excluded from rates):"]
        for r in errors[:5]:
            lines.append(f"    {r['arm']} {r['task_id']}: {str(r['error'])[:70]}")

    lines += ["", _footer(report_class, rows)]
    return "\n".join(lines)


def _footer(report_class: str, rows: list[dict[str, Any]]) -> str:
    truncated = sum(1 for r in rows if r["truncated"])
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
