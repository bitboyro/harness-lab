"""Paired contrasts between arms, with multiplicity control.

A report that says "A1 88%, A2 62%" states two numbers. It does not say whether
the gap is real. This module is the difference between *"A1 scored higher"* and
*"A1 is better"*.

The design follows `docs/statistical-plan.md`:

  - **Paired within core.** Arms are compared only on cores both attempted, so
    per-core difficulty cancels instead of inflating the variance. A core that
    happens to be hard makes *both* arms fail it, and pairing removes that.
  - **The core is the unit.** Runs inside a core are correlated; treating them
    as independent would shrink every standard error and make noise look
    significant.
  - **Holm correction** across the pre-registered confirmatory contrasts.
    Correlated tests make plain Bonferroni needlessly conservative; six tests
    make family-wise control affordable, so Holm rather than FDR.

Stdlib only — normal approximation on the paired core-level differences, which
is what the planning maths assumed. Anything heavier (a true mixed-effects fit)
is a `statsmodels` job and can consume the same paired table.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from .analysis import NOT_GRADED, SUCCESS, Report


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


@dataclass(frozen=True, slots=True)
class Contrast:
    """One arm-versus-arm comparison, paired within core."""

    arm_a: str
    arm_b: str
    #: Cores where both arms have at least one graded run.
    n_cores: int
    #: Mean per-core difference in success rate, a minus b.
    diff: float
    se: float
    z: float
    p_raw: float
    p_adjusted: float | None = None
    confirmatory: bool = False
    hypothesis: str | None = None

    @property
    def ci(self) -> tuple[float, float]:
        return (self.diff - 1.96 * self.se, self.diff + 1.96 * self.se)

    @property
    def significant(self) -> bool:
        """Only ever true for a pre-registered contrast at its adjusted p.

        An exploratory contrast may look striking; it does not get to be
        "significant", because its p-value was never corrected for the number
        of comparisons that were actually available to look at.
        """
        return (self.confirmatory and self.p_adjusted is not None
                and self.p_adjusted < 0.05)

    def render(self) -> str:
        stars = "*" if self.significant else " "
        p = self.p_adjusted if self.p_adjusted is not None else self.p_raw
        kind = "confirmatory" if self.confirmatory else "exploratory"
        return (
            f"  {self.arm_a} vs {self.arm_b:<4} "
            f"{self.diff:+6.1%}  95% CI [{self.ci[0]:+.1%}, {self.ci[1]:+.1%}]  "
            f"p={p:.4f}{stars}  cores={self.n_cores:<3} {kind}"
        )


def _per_core_rates(report: Report, arm: str) -> dict[str, float]:
    """Success rate per core for one arm, over graded runs only."""
    buckets: dict[str, list[bool]] = defaultdict(list)
    summary = report.arms.get(arm)
    if not summary:
        return {}
    for row in summary.rows:
        if row["outcome"] in NOT_GRADED:
            continue
        core = row.get("core_id") or row["task_id"]
        buckets[core].append(row["outcome"] in SUCCESS)
    return {core: sum(v) / len(v) for core, v in buckets.items() if v}


def compare(report: Report, arm_a: str, arm_b: str, *,
            confirmatory: bool = False,
            hypothesis: str | None = None) -> Contrast | None:
    """Paired difference between two arms. None if they share no cores."""
    a, b = _per_core_rates(report, arm_a), _per_core_rates(report, arm_b)
    shared = sorted(set(a) & set(b))
    if len(shared) < 2:
        # One core cannot produce a variance estimate, and reporting a
        # difference without one would be a number with no error bar.
        return None

    diffs = [a[core] - b[core] for core in shared]
    n = len(diffs)
    mean = sum(diffs) / n
    variance = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(variance / n)

    if se == 0:
        # Every core moved identically. p is 0 if there is any effect at all,
        # 1 if there is none — no test statistic is defined either way.
        return Contrast(arm_a, arm_b, n, mean, 0.0,
                        z=math.inf if mean else 0.0,
                        p_raw=0.0 if mean else 1.0,
                        confirmatory=confirmatory, hypothesis=hypothesis)

    z = mean / se
    p = 2 * (1 - _normal_cdf(abs(z)))
    return Contrast(arm_a, arm_b, n, mean, se, z, p,
                    confirmatory=confirmatory, hypothesis=hypothesis)


def holm(contrasts: Sequence[Contrast]) -> list[Contrast]:
    """Holm–Bonferroni over the confirmatory contrasts only.

    Exploratory contrasts pass through with `p_adjusted` unset — they are
    reported, labelled, and never called significant. Correcting them would
    imply they were pre-registered.
    """
    from dataclasses import replace

    confirmatory = [c for c in contrasts if c.confirmatory]
    exploratory = [c for c in contrasts if not c.confirmatory]

    ordered = sorted(confirmatory, key=lambda c: c.p_raw)
    m = len(ordered)
    adjusted: list[Contrast] = []
    running = 0.0
    for i, contrast in enumerate(ordered):
        value = min(1.0, (m - i) * contrast.p_raw)
        # Holm is monotone: an adjusted p never decreases down the ranking.
        running = max(running, value)
        adjusted.append(replace(contrast, p_adjusted=running))

    return adjusted + exploratory


@dataclass
class StatsReport:
    contrasts: list[Contrast] = field(default_factory=list)
    mde_pp: float | None = None

    @property
    def findings(self) -> list[Contrast]:
        return [c for c in self.contrasts if c.significant]

    def render(self) -> str:
        if not self.contrasts:
            return ("  No contrast had two shared cores — nothing is comparable "
                    "yet. Add cores, not repeats.")
        lines = ["  paired within core; * = significant after Holm correction"]
        for contrast in self.contrasts:
            lines.append(contrast.render())

        if not self.findings:
            lines.append("")
            lines.append(
                "  No confirmatory contrast survives correction. At this sample "
                "size that means 'not detectable', not 'no difference' — the "
                "confidence intervals above are the honest summary."
            )
        return "\n".join(lines)


#: The pre-registered confirmatory contrasts (statistical-plan.md §3).
#: Declared here, in code, so a run cannot quietly add one after seeing results.
CONFIRMATORY: tuple[tuple[str, str, str], ...] = (
    ("B1", "A1", "P4 — a skill layer helps on an identical MCP surface (RQ1)"),
    ("B2", "A2", "P4 — the same, under discovery"),
    ("A2", "A1", "P3 — per-operation degrades as the surface grows (RQ2)"),
    ("C1", "A1", "P2 — freehand curl versus a typed surface (RQ3)"),
    ("D1", "A1", "code execution versus eager-all (2602.15945)"),
    ("D2", "D1", "P4 — a skill on top of code execution"),
    # V9: the authored-vs-generated gap. Without these the dual condition can be
    # run and then not tested, which is the failure the condition exists to
    # prevent. Registered here, before the authored arms have ever run.
    ("B1-auth", "B1", "P9 — an authored skill beats a generated one (V9)"),
    ("B2-auth", "B2", "P9 — the same, under discovery"),
    ("D2-auth", "D2", "P9 — the same, on code execution"),
)


def analyse(report: Report, *, extra: Sequence[tuple[str, str]] = ()) -> StatsReport:
    """Every comparable contrast, corrected."""
    present = set(report.arms)
    contrasts: list[Contrast] = []

    for arm_a, arm_b, hypothesis in CONFIRMATORY:
        if {arm_a, arm_b} <= present:
            c = compare(report, arm_a, arm_b, confirmatory=True,
                        hypothesis=hypothesis)
            if c:
                contrasts.append(c)

    declared = {(a, b) for a, b, _ in CONFIRMATORY}
    for arm_a, arm_b in extra:
        if {arm_a, arm_b} <= present and (arm_a, arm_b) not in declared:
            c = compare(report, arm_a, arm_b, confirmatory=False)
            if c:
                contrasts.append(c)

    return StatsReport(contrasts=holm(contrasts), mde_pp=report.mde_pp)
