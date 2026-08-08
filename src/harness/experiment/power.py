"""Power: how many cores does *this* comparison need?

The core count is not one global setting. Different comparisons need different
amounts of data, and the difference is large:

  - A **main effect** ("does B1 beat A1?") compares two numbers.
  - An **interaction** ("does the B1-vs-A1 gap differ between reads and
    writes?") compares two *differences*. Each carries its own error, so the
    combined wobble is roughly double and the detectable effect roughly doubles
    with it.

So a matrix sized for main effects is quietly underpowered for the interaction —
which is the headline result. This module makes that visible at the point where
the number is chosen, instead of leaving it in a document nobody re-reads.

Contract: archive/reference/statistics.md#power-and-mde
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

#: Terminals per core. One core yields R, W-safe, W-lossy, W-irrev, RW-fan.
TERMINALS_PER_CORE = 5

#: Correlation between runs sharing a core. Conservative default; re-estimate
#: from Phase 0 and update the plan *before* the main matrix.
DEFAULT_ICC = 0.3


class Contrast(StrEnum):
    """What is being compared. Determines how the variance stacks up."""

    #: Two arms, pooled across task classes.
    MAIN_EFFECT = "main-effect"
    #: Two arms within one task class. Fewer runs per cell.
    WITHIN_CLASS = "within-class"
    #: Whether an arm gap differs between classes. Two differences, so the
    #: standard error is ~sqrt(2)x larger and the MDE ~2x.
    INTERACTION = "interaction"


@dataclass(frozen=True, slots=True)
class PowerResult:
    contrast: Contrast
    cores: int
    repeats: int
    runs_per_arm: int
    effective_n: float
    mde_pp: float
    alpha: float
    power: float

    @property
    def adequate(self) -> bool:
        """Whether a realistic effect would be detectable.

        15 pp is the working threshold for "an effect worth acting on". Below
        that, a null result means "we could not see it", not "it is not there" —
        and those must not be reported the same way.
        """
        return self.mde_pp <= 15.0

    def render(self) -> str:
        verdict = "adequate" if self.adequate else "UNDERPOWERED"
        return (
            f"{self.contrast:<14} {self.cores:>3} cores x {self.repeats} repeats "
            f"= {self.runs_per_arm:>4} runs/arm  "
            f"MDE {self.mde_pp:>5.1f} pp  [{verdict}]"
        )


def _z(p: float) -> float:
    """Inverse normal CDF. Acklam's approximation; ample for planning."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    a = (-39.69683028665376, 220.9460984245205, -275.9285104469687,
         138.3577518672690, -30.66479806614716, 2.506628277459239)
    b = (-54.47609879822406, 161.5858368580409, -155.6989798598866,
         66.80131188771972, -13.28068155288572)
    c = (-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
         -2.549732539343734, 4.374664141464968, 2.938163982698783)
    d = (0.007784695709041462, 0.3224671290700398, 2.445134137142996,
         3.754408661907416)
    plow, phigh = 0.02425, 1 - 0.02425

    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    if p > phigh:
        return -_z(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q / \
           (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)


#: Between-core variance in the *size* of an arm effect. Even a real effect is
#: not identical on every core, and that heterogeneity does not shrink by
#: running more repeats — only more cores reduce it. Setting this to 0 would
#: claim the arm gap is exactly the same everywhere, which no packaging effect
#: plausibly is.
DEFAULT_EFFECT_HETEROGENEITY = 0.01


def analyse(
    contrast: Contrast,
    cores: int,
    *,
    repeats: int = 3,
    alpha: float = 0.0083,   # Holm's first step at six confirmatory tests
    power: float = 0.80,
    icc: float = DEFAULT_ICC,
    baseline: float = 0.5,   # worst-case variance
    effect_heterogeneity: float = DEFAULT_EFFECT_HETEROGENEITY,
) -> PowerResult:
    """Minimum detectable effect for one contrast at a given core count.

    **The core is the unit of analysis**, not the run. Each core yields one
    paired difference between the two arms, and the test is over those
    differences. That framing is what makes the arithmetic honest:

    - Pairing within a core cancels core difficulty, so the `(1 - icc)` term is
      a *benefit*, not the clustering penalty an unpaired design would pay.
    - But averaging more observations inside a core only shrinks measurement
      noise. It cannot shrink `effect_heterogeneity` — how much the arm gap
      itself varies from core to core. That term divides by the number of
      cores and by nothing else.

    Which is the formal statement of "more cores, not more repeats": repeats
    push on one term and leave the other untouched.
    """
    if cores < 1:
        raise ValueError("cores must be at least 1")

    if contrast is Contrast.WITHIN_CLASS:
        observations_per_core = repeats           # one terminal
    else:
        observations_per_core = TERMINALS_PER_CORE * repeats

    runs_per_arm = cores * observations_per_core
    variance = baseline * (1 - baseline)

    # Variance of one core's paired difference: measurement noise (shrinks with
    # observations inside the core) plus effect heterogeneity (does not).
    per_core_variance = (
        2 * variance * (1 - icc) / observations_per_core + effect_heterogeneity
    )

    # An interaction is a difference of two differences, so its errors add.
    if contrast is Contrast.INTERACTION:
        per_core_variance *= 2

    z_alpha = abs(_z(alpha / 2))
    z_beta = abs(_z(1 - power))
    mde = (z_alpha + z_beta) * math.sqrt(per_core_variance / cores)

    return PowerResult(
        contrast=contrast, cores=cores, repeats=repeats,
        runs_per_arm=runs_per_arm, effective_n=float(cores),
        mde_pp=mde * 100, alpha=alpha, power=power,
    )


def cores_for(
    contrast: Contrast,
    target_mde_pp: float,
    *,
    repeats: int = 3,
    max_cores: int = 500,
    **kw,
) -> int | None:
    """Smallest core count reaching a target MDE. None if unreachable.

    This is the function to use when designing a run: state the effect you care
    about detecting, get the size you need. Choosing a core count first and
    hoping is how a matrix ends up unable to answer its own question.
    """
    for cores in range(1, max_cores + 1):
        if analyse(contrast, cores, repeats=repeats, **kw).mde_pp <= target_mde_pp:
            return cores
    return None


def report(cores: int, *, repeats: int = 3, **kw) -> str:
    """What a given core count buys across every contrast."""
    lines = [f"Power at {cores} cores, {repeats} repeats "
             f"({cores * TERMINALS_PER_CORE * repeats} runs per arm):", ""]
    weak: list[Contrast] = []
    for contrast in Contrast:
        result = analyse(contrast, cores, repeats=repeats, **kw)
        lines.append("  " + result.render())
        if not result.adequate:
            weak.append(contrast)

    if weak:
        lines.append("")
        for contrast in weak:
            needed = cores_for(contrast, 15.0, repeats=repeats, **kw)
            fix = f"{needed} cores would reach 15 pp" if needed else "unreachable"
            lines.append(
                f"  {contrast} is underpowered — {fix}. A null here means "
                "'not detectable', not 'not present', and must be reported "
                "with its confidence interval rather than as a null."
            )
    return "\n".join(lines)
