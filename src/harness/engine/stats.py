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

from .analysis import NOT_GRADED, SUCCESS, Report, wilson


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _two_sided_p(z: float) -> float:
    return 2 * (1 - _normal_cdf(abs(z)))


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


def _paired_diff(a: dict[str, float],
                 b: dict[str, float]) -> tuple[int, float, float, float, float] | None:
    """(n, mean, se, z, p) over the keys both sides share. None below two.

    The one implementation of "the core is the unit". Both the within-run
    `compare` and the cross-run `cross_compare` call it, so the two can never
    drift into disagreeing about what a paired difference is.
    """
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
        return (n, mean, 0.0, math.inf if mean else 0.0, 0.0 if mean else 1.0)

    z = mean / se
    return (n, mean, se, z, _two_sided_p(z))


def compare(report: Report, arm_a: str, arm_b: str, *,
            confirmatory: bool = False,
            hypothesis: str | None = None) -> Contrast | None:
    """Paired difference between two arms. None if they share no cores."""
    paired = _paired_diff(_per_core_rates(report, arm_a),
                          _per_core_rates(report, arm_b))
    if paired is None:
        return None
    n, mean, se, z, p = paired
    return Contrast(arm_a, arm_b, n, mean, se, z, p,
                    confirmatory=confirmatory, hypothesis=hypothesis)


def holm(contrasts: Sequence[Contrast]) -> list[Contrast]:
    """Holm–Bonferroni over the confirmatory contrasts only.

    Exploratory contrasts pass through with `p_adjusted` unset — they are
    reported, labelled, and never called significant. Correcting them would
    imply they were pre-registered.
    """
    from dataclasses import replace

    cross = [c for c in contrasts if isinstance(c, CrossContrast)]
    if cross:
        # Correcting a cross-run contrast would imply it belonged to a
        # pre-registered family. There is no such family: which runs get
        # compared is decided after both have been seen.
        raise TypeError(
            "holm() cannot correct a CrossContrast — no cross-run comparison "
            "is pre-registered, so there is no family size to correct against."
        )

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


# ---- across runs ---------------------------------------------------------
#
# Everything below compares the *same arm in two runs*. None of it is
# pre-registered and none of it is corrected: which two runs get compared is
# decided after both have been seen, so there is no family size to correct
# against. `CrossContrast` deliberately has no `significant` property.
#
# Contract: archive/reference/statistics.md#comparing-runs

#: Manifest keys that together determine which tasks a run was given. All four
#: are needed: `build_pack(build_world(seed, shape), cores=…, difficulty=…)`
#: reads every one of them.
WORLD_KEYS = ("seed", "cores", "fan_out", "difficulty")


def world_key(report: Report) -> tuple | None:
    """What generated this run's tasks, or None when the ledger cannot say.

    `core_id` is **positional, not content-addressed**: `core-000` exists in
    every run this rig has ever produced, and in two different worlds it names
    a different problem. Pairing on the string across runs would subtract the
    success rate on one problem from the success rate on another and report it
    as a within-core difference — producing a *tighter* interval than the data
    supports, which is the most dangerous direction for an error to go.

    None when any component is missing. An unrecorded world parameter cannot be
    assumed equal, so an old ledger falls back to the unpaired comparison
    rather than borrowing confidence it never earned.

    Contract: archive/reference/statistics.md#comparing-runs
    """
    manifest = report.manifest
    digest = manifest.get("pack_digest")
    if digest:
        # Content-addressed over the actual task ids. Beats the parameter tuple
        # because it survives a hand-edited manifest.
        return ("digest", str(digest))
    if any(manifest.get(k) is None for k in WORLD_KEYS):
        return None
    return tuple(str(manifest[k]) for k in WORLD_KEYS)


@dataclass(frozen=True, slots=True)
class CrossContrast:
    """One arm, measured in two runs.

    Always exploratory. `significant` is deliberately absent — see the module
    section header for why nothing here can earn that word.
    """

    arm: str
    run_a: str
    run_b: str
    #: "paired-core" | "unpaired-proportions" | "intervals-only"
    method: str
    rate_a: float | None
    rate_b: float | None
    ci_a: tuple[float, float] | None
    ci_b: tuple[float, float] | None
    n_a: int
    n_b: int
    n_cores: int = 0
    #: b minus a. Oriented against the reference run, which is always a.
    diff: float | None = None
    se: float | None = None
    z: float | None = None
    p_raw: float | None = None
    mde_a: float | None = None
    mde_b: float | None = None
    cross_world: bool = False
    #: Set by the unpaired method, which uses an asymmetric Newcombe interval
    #: rather than diff ± 1.96·se. When present it wins over the symmetric one.
    ci_diff: tuple[float, float] | None = None
    #: Empty only when the method is `paired-core`. Every weaker method has to
    #: say what it gave up.
    caveat: str = ""

    @property
    def paired(self) -> bool:
        return self.method == "paired-core"

    @property
    def comparable(self) -> bool:
        return self.diff is not None

    @property
    def ci(self) -> tuple[float, float] | None:
        if self.ci_diff is not None:
            return self.ci_diff
        if self.diff is None or self.se is None:
            return None
        return (self.diff - 1.96 * self.se, self.diff + 1.96 * self.se)

    @property
    def mde_combined(self) -> float | None:
        """The smallest gap this pair of runs could detect, in points.

        Larger than either run's own MDE: both measurements carry error and the
        errors add. An approximation — variances added over two MDEs, not a
        derivation from the power model — and labelled as one everywhere it is
        printed.
        """
        known = [m for m in (self.mde_a, self.mde_b) if m is not None]
        if not known:
            return None
        if len(known) == 1:
            return known[0]
        return math.sqrt(sum(m * m for m in known))

    @property
    def below_mde(self) -> bool:
        """Whether the gap is too small for these two samples to resolve."""
        floor = self.mde_combined
        if self.diff is None or floor is None:
            return False
        return abs(self.diff * 100) < floor

    @property
    def spans_zero(self) -> bool:
        """Whether the interval admits no difference at all."""
        interval = self.ci
        return interval is not None and interval[0] <= 0 <= interval[1]

    @property
    def notable(self) -> bool:
        """Worth reading as a difference at all.

        Three ways to fail, and any one is enough. A cross-world gap is never
        notable however large — the runs answer different questions, so their
        difference answers neither. A gap under the combined noise floor is not
        resolvable by these sample sizes. And an interval that spans zero is
        consistent with no difference whatever the point estimate says, which
        is the check that stops a 2-for-2 smoke arm reading as a finding.
        """
        if self.diff is None or self.cross_world:
            return False
        return not self.below_mde and not self.spans_zero

    def render(self) -> str:
        marks = ("*" if self.notable else " ") + ("~" if not self.paired else " ")
        marks += "‡" if self.cross_world else " "
        rate_a = "n/a" if self.rate_a is None else f"{self.rate_a:.0%}"
        rate_b = "n/a" if self.rate_b is None else f"{self.rate_b:.0%}"
        head = f"  {self.arm:<9}{marks} {rate_a:>5} -> {rate_b:>5}"
        if self.diff is None:
            return f"{head}   not comparable — {self.caveat}"
        lo, hi = self.ci
        n = (f"cores={self.n_cores}" if self.paired
             else f"n={self.n_a}/{self.n_b}")
        return (f"{head}  {self.diff:+6.1%}  95% CI [{lo:+.1%}, {hi:+.1%}]  "
                f"p={self.p_raw:.4f}  {n:<12} {self.method}")


#: The three sentences an unpaired cross-run difference has to carry. Stated
#: together because dropping any one of them makes the number look better than
#: it is.
UNPAIRED_CAVEAT = (
    "these runs answered different task sets, so per-task difficulty no longer "
    "cancels and the gap may be biased rather than merely noisy; repeats inside "
    "a core are correlated, so n overstates the independent sample and the "
    "interval is if anything optimistic; exploratory — never significant"
)


def _newcombe(succ_a: int, n_a: int, succ_b: int,
              n_b: int) -> tuple[float, float]:
    """Newcombe hybrid-score interval for `b - a`, built from two Wilson ones.

    The textbook two-proportion interval is `diff ± 1.96·sqrt(pq/n + pq/n)`,
    and at the edges it collapses: an arm that went 2-for-2 contributes
    p(1-p)=0, so the interval borrows a confidence the two runs never earned.
    A smoke run sits at exactly those edges, and cross-run comparison is where
    a smoke run most often turns up.

    Newcombe's method takes the *asymmetric* Wilson interval on each side and
    combines the distances to the relevant bounds, so a boundary proportion
    still contributes width. Same stdlib arithmetic, and it reuses the `wilson`
    the rest of the report already trusts.
    """
    p_a = succ_a / n_a
    p_b = succ_b / n_b
    lo_a, hi_a = wilson(succ_a, n_a) or (p_a, p_a)
    lo_b, hi_b = wilson(succ_b, n_b) or (p_b, p_b)
    diff = p_b - p_a
    lower = diff - math.sqrt((p_b - lo_b) ** 2 + (hi_a - p_a) ** 2)
    upper = diff + math.sqrt((hi_b - p_b) ** 2 + (p_a - lo_a) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def _graded_counts(report: Report, arm: str) -> tuple[int, int]:
    """(successes, graded) for one arm. The unpaired comparison's raw material."""
    summary = report.arms.get(arm)
    if summary is None:
        return (0, 0)
    graded = summary.graded
    return (sum(1 for r in graded if r["outcome"] in SUCCESS), len(graded))


def cross_compare(report_a: Report, report_b: Report, arm: str, *,
                  label_a: str = "a", label_b: str = "b",
                  paired: bool | None = None) -> CrossContrast | None:
    """The same arm in two runs. None when neither run has it.

    Three tiers, weakest last:

      - **paired-core** when both runs came from the same world and the arm
        shares at least two cores. Per-task difficulty cancels exactly as it
        does within a run.
      - **unpaired-proportions** otherwise. Two-proportion z over graded runs,
        carrying `UNPAIRED_CAVEAT`. This is the common case — re-running with a
        bigger world or a different model trips the world gate every time — and
        refusing outright would make the whole comparison useless for its most
        likely invocation. So it is computed, and labelled, and never called
        significant.
      - **intervals-only** when either side has too little graded data to
        support a difference at all. Both Wilson intervals are reported and
        `diff` stays None. Never a zero.

    `paired=None` decides from `world_key`; True or False overrides it.
    """
    if arm not in report_a.arms and arm not in report_b.arms:
        return None

    key_a, key_b = world_key(report_a), world_key(report_b)
    same_world = key_a is not None and key_a == key_b
    if paired is None:
        paired = same_world

    succ_a, n_a = _graded_counts(report_a, arm)
    succ_b, n_b = _graded_counts(report_b, arm)
    rate_a = succ_a / n_a if n_a else None
    rate_b = succ_b / n_b if n_b else None

    # The arm's own world tuple, not the run's: skill condition varies by arm,
    # so a run-level check would miss a generated-vs-authored swap on one arm.
    cross_world = _arm_worlds(report_a, arm) != _arm_worlds(report_b, arm)

    common = dict(
        arm=arm, run_a=label_a, run_b=label_b,
        rate_a=rate_a, rate_b=rate_b,
        ci_a=wilson(succ_a, n_a), ci_b=wilson(succ_b, n_b),
        n_a=n_a, n_b=n_b,
        mde_a=report_a.mde_pp, mde_b=report_b.mde_pp,
        cross_world=cross_world,
    )

    if paired:
        result = _paired_diff(_per_core_rates(report_b, arm),
                              _per_core_rates(report_a, arm))
        if result is not None:
            n_cores, mean, se, z, p = result
            return CrossContrast(method="paired-core", n_cores=n_cores,
                                 diff=mean, se=se, z=z, p_raw=p, **common)

    if n_a and n_b:
        diff = rate_b - rate_a
        lo, hi = _newcombe(succ_a, n_a, succ_b, n_b)
        # One interval, one standard error, one p — the se is read back off the
        # interval rather than computed separately, so the three cannot
        # disagree about how wide the uncertainty is.
        se = (hi - lo) / (2 * 1.96)
        if se == 0:
            z = math.inf if diff else 0.0
            p = 0.0 if diff else 1.0
        else:
            z = diff / se
            p = _two_sided_p(z)
        caveat = UNPAIRED_CAVEAT
        if paired:
            caveat = ("same world, but this arm shares fewer than two cores "
                      "between the runs; " + caveat)
        return CrossContrast(method="unpaired-proportions", diff=diff, se=se,
                             z=z, p_raw=p, ci_diff=(lo, hi), caveat=caveat,
                             **common)

    empty = label_a if not n_a else label_b
    return CrossContrast(
        method="intervals-only",
        caveat=f"no graded runs for this arm in {empty}",
        **common,
    )


def _arm_worlds(report: Report, arm: str) -> frozenset[tuple]:
    """The pooling tuples one arm's rows carry. Empty when the run lacks it.

    A null MCP revision is an absence — the arm has no MCP at all — not a
    second revision, so it is normalised away rather than read as a difference.
    """
    summary = report.arms.get(arm)
    if summary is None:
        return frozenset()
    return frozenset(
        (r.get("model"), r.get("mcp_spec_revision") or "none",
         r.get("skill_condition"), r.get("report_class"))
        for r in summary.rows
    )
