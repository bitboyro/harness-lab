"""Turn sweep results into lint-rule justifications.

A T1 rule that points at a measured effect size is a defensible claim. One that
does not is an opinion with a severity label. This module is the only path from
the second state to the first.

**Only a sweep can justify a rule.** Comparing arms tells you about packaging;
the lint rules are about properties of the API itself, so the evidence has to
come from varying that property while holding everything else fixed. Comparing
A1 to D1 says nothing about whether error messages should name the field.

Contract: archive/reference/decisions.md G2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .analysis import Report
from .lint import Justification

#: Which rule each sweep axis can speak to, and which direction counts as
#: support. A sweep that moves nothing is evidence too — it argues for deleting
#: the rule rather than keeping it unjustified.
SWEEP_RULES = {
    "error_detail": ("undescribed-errors",
                     "richer errors improve success or reduce retries"),
    "response_shape": ("unbounded-collection",
                       "shaping responses improves success or cost"),
    "doc_budget": ("no-description",
                   "more description improves success"),
}


@dataclass(frozen=True, slots=True)
class SweepEffect:
    """What varying one API property did, holding packaging fixed."""

    axis: str
    baseline_level: str
    improved_level: str
    metric: str
    delta: float
    n_cores: int
    rule_id: str

    @property
    def supports_rule(self) -> bool:
        return self.delta > 0

    def as_justification(self, run_id: str) -> Justification:
        return Justification(
            run_id=run_id,
            metric=self.metric,
            effect=f"{self.baseline_level} → {self.improved_level}: "
                   f"{self.delta:+.1%} {self.metric} over {self.n_cores} cores",
        )

    def render(self) -> str:
        verdict = "supports" if self.supports_rule else "does NOT support"
        return (f"  {self.rule_id:<22} {self.baseline_level} → "
                f"{self.improved_level}: {self.delta:+.1%} {self.metric} "
                f"({self.n_cores} cores) — {verdict}")


def _sweep_levels(report: Report) -> dict[str, list[str]]:
    """Arm labels carry the swept level as `ARM@level`."""
    levels: dict[str, set[str]] = {}
    for name in report.arms:
        if "@" not in name:
            continue
        base, level = name.split("@", 1)
        levels.setdefault(base, set()).add(level)
    return {k: sorted(v) for k, v in levels.items() if len(v) > 1}


def effects(report: Report, axis: str = "error_detail") -> list[SweepEffect]:
    """Effect of each swept level against the first, per arm.

    Paired by arm rather than pooled: an arm that never sees an error cannot
    contribute evidence about error messages, and averaging it in would dilute
    the effect toward zero.
    """
    rule_id, _ = SWEEP_RULES.get(axis, (None, None))
    if rule_id is None:
        return []

    out: list[SweepEffect] = []
    for base, levels in _sweep_levels(report).items():
        baseline = levels[0]
        base_arm = report.arms.get(f"{base}@{baseline}")
        if not base_arm or base_arm.success_rate is None:
            continue
        for level in levels[1:]:
            arm = report.arms.get(f"{base}@{level}")
            if not arm or arm.success_rate is None:
                continue
            out.append(SweepEffect(
                axis=axis,
                baseline_level=f"{base}@{baseline}",
                improved_level=f"{base}@{level}",
                metric="success rate",
                delta=arm.success_rate - base_arm.success_rate,
                n_cores=len({r.get("core_id") for r in arm.rows}),
                rule_id=rule_id,
            ))
    return out


def report_status(report: Report, axis: str = "error_detail") -> str:
    found = effects(report, axis)
    if not found:
        return (f"  No {axis} sweep in these results, so no lint rule can be "
                "justified from them. Rules stay heuristic until a run varies "
                "the property they describe — comparing arms cannot do it.")
    lines = [f"  {axis} sweep — effect on the rule it speaks to:"]
    lines.extend(e.render() for e in found)
    if not any(e.supports_rule for e in found):
        lines.append("")
        lines.append("  No level improved on the baseline. That is evidence "
                     "against the rule, not an absence of evidence — a rule "
                     "that never earns a citation should be deleted.")
    return "\n".join(lines)
