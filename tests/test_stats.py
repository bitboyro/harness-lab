"""Paired contrasts and multiplicity control."""

from __future__ import annotations

import pytest

from harness.engine.analysis import Report, wilson
from harness.engine.stats import (CONFIRMATORY, Contrast, analyse, compare,
                                  cross_compare, holm, world_key)

BASE = dict(
    run_id="r", task_id="t", task_class="R", answerable=True, repeat=0,
    detail="", confident=False, clobbered=[], turns=3, calls=2,
    forbidden_attempts=0, truncated=False, error=None, wall_clock_seconds=1.0,
    input_tokens=100, cached_input_tokens=0, output_tokens=10,
    reasoning_tokens=0, static_tokens=10, per_call_overhead_tokens=0,
    session_setup_tokens=0, model="gpt-5.6-luna",
    mcp_spec_revision="2026-07-28", skill_condition="none",
    report_class="controlled", seed=1, surface_size=0, metrics={},
)

_WORLD = dict(seed=1, cores=4, fan_out=8, difficulty="standard")


def rows(arm: str, outcomes: dict[str, str]) -> list[dict]:
    return [dict(BASE, arm=arm, core_id=core, task_id=f"{core}-{arm}",
                 outcome=outcome)
            for core, outcome in outcomes.items()]


def report(*groups, manifest: dict | None = None) -> Report:
    flat = [r for g in groups for r in g]
    return Report(rows=flat,
                  manifest={"id": "t", "model": "gpt-5.6-luna", **(manifest or {})})


# ---- pairing -------------------------------------------------------------

def test_paired_difference_uses_only_shared_cores() -> None:
    """A core only one arm attempted cannot contribute to a paired difference."""
    r = report(
        rows("A1", {"c1": "pass", "c2": "pass", "c3": "pass"}),
        rows("B1", {"c1": "fail", "c2": "fail"}),
    )
    c = compare(r, "A1", "B1")
    assert c is not None
    assert c.n_cores == 2, "c3 is unpaired and excluded"
    assert c.diff == pytest.approx(1.0)


def test_too_few_shared_cores_returns_none() -> None:
    """One core gives no variance estimate — a difference with no error bar."""
    r = report(rows("A1", {"c1": "pass"}), rows("B1", {"c1": "fail"}))
    assert compare(r, "A1", "B1") is None


def test_truncated_runs_excluded_from_contrasts() -> None:
    r = report(
        rows("A1", {"c1": "pass", "c2": "pass", "c3": "truncated"}),
        rows("B1", {"c1": "pass", "c2": "pass", "c3": "pass"}),
    )
    c = compare(r, "A1", "B1")
    assert c.n_cores == 2, "a truncated run is a budget failure, not a data point"


def test_identical_arms_show_no_difference() -> None:
    same = {"c1": "pass", "c2": "fail", "c3": "pass", "c4": "fail"}
    c = compare(report(rows("A1", same), rows("B1", same)), "A1", "B1")
    assert c.diff == 0.0
    assert c.p_raw == 1.0


def test_a_consistent_gap_is_detected() -> None:
    r = report(
        rows("A1", {f"c{i}": "pass" for i in range(8)}),
        rows("B1", {f"c{i}": "fail" for i in range(8)}),
    )
    c = compare(r, "A1", "B1", confirmatory=True)
    assert c.diff == pytest.approx(1.0)
    assert c.p_raw < 0.05


def test_a_noisy_gap_is_not_detected() -> None:
    """Same mean direction, inconsistent per core — must not reach significance."""
    r = report(
        rows("A1", {"c1": "pass", "c2": "fail", "c3": "pass", "c4": "fail"}),
        rows("B1", {"c1": "fail", "c2": "pass", "c3": "fail", "c4": "pass"}),
    )
    c = compare(r, "A1", "B1", confirmatory=True)
    assert abs(c.diff) < 1e-9
    assert c.p_raw > 0.05


# ---- Holm ----------------------------------------------------------------

def _c(p: float, confirmatory: bool = True) -> Contrast:
    return Contrast("A", "B", 5, 0.2, 0.05, 4.0, p, confirmatory=confirmatory)


def test_holm_is_less_conservative_than_bonferroni() -> None:
    adjusted = holm([_c(0.01), _c(0.02), _c(0.03)])
    smallest = min(c.p_adjusted for c in adjusted)
    assert smallest == pytest.approx(0.03)          # 3 x 0.01
    assert smallest < 0.01 * 3 + 1e-9


def test_holm_adjusted_p_never_decreases() -> None:
    adjusted = sorted(holm([_c(0.001), _c(0.04), _c(0.5)]),
                      key=lambda c: c.p_raw)
    values = [c.p_adjusted for c in adjusted]
    assert values == sorted(values), "Holm must be monotone"


def test_exploratory_contrasts_are_never_significant() -> None:
    """However striking it looks, an uncorrected p was not pre-registered."""
    adjusted = holm([_c(0.0001, confirmatory=False)])
    assert adjusted[0].p_adjusted is None
    assert not adjusted[0].significant


def test_confirmatory_contrast_can_be_significant() -> None:
    adjusted = holm([_c(0.0001)])
    assert adjusted[0].significant


# ---- the registry --------------------------------------------------------

def test_confirmatory_set_is_declared_in_code() -> None:
    """So a run cannot quietly add a contrast after seeing the results."""
    pairs = {(a, b) for a, b, _ in CONFIRMATORY}
    assert ("B1", "A1") in pairs, "RQ1 must be pre-registered"
    assert ("A2", "A1") in pairs, "RQ2 must be pre-registered"
    assert all(reason for _, _, reason in CONFIRMATORY)


def test_analyse_skips_absent_arms() -> None:
    r = report(rows("A1", {f"c{i}": "pass" for i in range(4)}),
               rows("A2", {f"c{i}": "fail" for i in range(4)}))
    stats = analyse(r)
    assert all({c.arm_a, c.arm_b} <= {"A1", "A2"} for c in stats.contrasts)


def test_report_says_when_nothing_survives() -> None:
    r = report(rows("A1", {"c1": "pass", "c2": "fail", "c3": "pass"}),
               rows("A2", {"c1": "pass", "c2": "fail", "c3": "pass"}))
    text = analyse(r).render()
    assert "not detectable" in text and "no difference" in text


def test_empty_report_is_stated_not_crashed() -> None:
    assert "nothing is comparable" in analyse(report()).render()


# ---- across runs ---------------------------------------------------------

def _same_world_pair():
    """Two reports sharing a world key and enough cores to pair."""
    outcomes_a = {f"c{i}": "pass" if i % 2 == 0 else "fail" for i in range(6)}
    outcomes_b = {f"c{i}": "pass" for i in range(6)}
    a = report(rows("A1", outcomes_a), manifest=_WORLD)
    b = report(rows("A1", outcomes_b), manifest=_WORLD)
    return a, b


def test_a_different_seed_refuses_to_pair() -> None:
    """core_id is positional — pairing across worlds invents precision.

    The dominant correctness risk in the whole feature: two runs both contain
    core-000, but they are different problems. Pairing would report a tighter
    interval than the data supports.
    """
    a = report(rows("A1", {f"c{i}": "pass" for i in range(4)}),
               manifest={**_WORLD, "seed": 1})
    b = report(rows("A1", {f"c{i}": "fail" for i in range(4)}),
               manifest={**_WORLD, "seed": 2})
    c = cross_compare(a, b, "A1")
    assert c is not None
    assert c.method == "unpaired-proportions"
    assert not c.paired
    assert "biased" in c.caveat


def test_a_missing_difficulty_refuses_to_pair() -> None:
    """An unrecorded world parameter cannot be assumed equal."""
    partial = {k: v for k, v in _WORLD.items() if k != "difficulty"}
    a = report(rows("A1", {f"c{i}": "pass" for i in range(4)}),
               manifest=partial)
    b = report(rows("A1", {f"c{i}": "pass" for i in range(4)}),
               manifest=partial)
    assert world_key(a) is None
    c = cross_compare(a, b, "A1")
    assert c.method == "unpaired-proportions"


def test_a_matching_pack_digest_pairs_without_the_other_keys() -> None:
    """Content address beats the parameter tuple."""
    a = report(rows("A1", {f"c{i}": "pass" for i in range(4)}),
               manifest={"pack_digest": "abc123"})
    b = report(rows("A1", {f"c{i}": "fail" for i in range(4)}),
               manifest={"pack_digest": "abc123"})
    assert world_key(a) == ("digest", "abc123")
    c = cross_compare(a, b, "A1")
    assert c.method == "paired-core"
    assert c.paired


def test_cross_compare_pairs_when_the_world_matches() -> None:
    a, b = _same_world_pair()
    c = cross_compare(a, b, "A1")
    assert c.method == "paired-core"
    assert c.caveat == ""


def test_the_unpaired_interval_keeps_width_where_wald_collapses() -> None:
    """Wald se is 0 at the boundary; Newcombe must not invent that certainty.

    An arm that went 0-for-2 against 2-for-2 contributes p(1-p)=0 on both
    sides, so the textbook interval collapses to a point. That is the
    failure Newcombe exists to prevent — and the shape a smoke run always
    has.
    """
    from harness.engine.stats import _newcombe
    lo, hi = _newcombe(0, 2, 2, 2)
    assert hi - lo > 0.5
    # Wald: diff ± 1.96·sqrt(0/2 + 0/2) = 1.0 ± 0
    wald_width = 2 * 1.96 * ((0.0 + 0.0) ** 0.5)
    assert (hi - lo) > wald_width


def test_cross_compare_actually_uses_newcombe_not_just_defines_it() -> None:
    """The boundary fix has to be wired in, not merely available.

    `_newcombe` passes its own unit test while `cross_compare` quietly computes
    Wald — which is precisely the state this code was in before the interval
    was swapped. Pinning the contrast's interval to the function's output is
    the only assertion that notices the wiring coming loose.

    0-for-2 against 2-for-2 is the shape that separates them: Wald's se is
    exactly zero on both sides, so it reports a 100-point difference with no
    interval at all.
    """
    from harness.engine.stats import _newcombe

    a = Report(rows=rows("A1", {"c1": "fail", "c2": "fail"}),
               manifest={**_WORLD, "seed": 1}, mde_pp=20.0)
    b = Report(rows=rows("A1", {"c1": "pass", "c2": "pass"}),
               manifest={**_WORLD, "seed": 2}, mde_pp=20.0)
    c = cross_compare(a, b, "A1")

    assert c.method == "unpaired-proportions"
    assert c.ci == pytest.approx(_newcombe(0, 2, 2, 2))
    # Wald would be 1.0 ± 0: a point estimate with no interval, and a certainty
    # two runs of two never earned. Newcombe keeps real width here.
    #
    # It does not span zero, and that is Newcombe behaving as designed rather
    # than a gap in the guard — at the extreme 0-vs-1 shape it is known to be
    # anticonservative. What stops this reading as a finding in practice is the
    # noise floor: a real two-core run carries an MDE near 100pp, not the 20pp
    # hardcoded here. `notable` is deliberately not asserted either way.
    assert c.ci[1] - c.ci[0] > 0.5


def test_a_two_for_two_arm_does_not_produce_a_significant_gap() -> None:
    """A smoke 2-for-2 against a moderate baseline must not read as a finding.

    Real case that shipped wrong under Wald: +32.7pp with a CI that excluded
    zero and p≈0. Newcombe on the same shape spans zero.
    """
    # ~67% (4/6) → 100% (2/2) ≈ +33pp — the smoke-vs-matrix shape.
    a = Report(
        rows=rows("A1", {"c1": "pass", "c2": "pass", "c3": "pass",
                         "c4": "pass", "c5": "fail", "c6": "fail"}),
        manifest={**_WORLD, "seed": 1}, mde_pp=20.0)
    b = Report(
        rows=rows("A1", {"c1": "pass", "c2": "pass"}),
        manifest={**_WORLD, "seed": 2}, mde_pp=20.0)
    c = cross_compare(a, b, "A1")
    assert c.diff == pytest.approx(1 / 3, abs=0.01)
    assert c.spans_zero or c.below_mde
    assert not c.notable


def test_too_few_graded_runs_reports_intervals_only() -> None:
    a = report(rows("A1", {"c1": "pass"}), manifest=_WORLD)
    # Arm exists but has no graded runs — truncation is a budget failure.
    b = report([dict(BASE, arm="A1", core_id="c1", task_id="c1-A1",
                     outcome="truncated", truncated=True)],
               manifest=_WORLD)
    c = cross_compare(a, b, "A1")
    assert c.method == "intervals-only"
    assert c.diff is None
    assert c.ci_a is not None
    assert c.n_b == 0


def test_holm_refuses_a_cross_contrast() -> None:
    """Nothing cross-run is pre-registered, so there is no family to correct."""
    a, b = _same_world_pair()
    c = cross_compare(a, b, "A1")
    with pytest.raises(TypeError, match="CrossContrast"):
        holm([c])


def test_cross_run_mde_exceeds_either_runs_own() -> None:
    a = Report(
        rows=rows("A1", {f"c{i}": "pass" for i in range(4)}),
        manifest=_WORLD, mde_pp=10.0)
    b = Report(
        rows=rows("A1", {f"c{i}": "fail" for i in range(4)}),
        manifest=_WORLD, mde_pp=10.0)
    c = cross_compare(a, b, "A1")
    assert c.mde_combined == pytest.approx((10.0 ** 2 + 10.0 ** 2) ** 0.5)
    assert c.mde_combined > 10.0


def test_a_gap_under_the_cross_run_mde_is_not_notable() -> None:
    a = Report(
        rows=rows("A1", {f"c{i}": "pass" if i < 5 else "fail" for i in range(8)}),
        manifest={**_WORLD, "seed": 1}, mde_pp=40.0)
    b = Report(
        rows=rows("A1", {f"c{i}": "pass" if i < 6 else "fail" for i in range(8)}),
        manifest={**_WORLD, "seed": 2}, mde_pp=40.0)
    c = cross_compare(a, b, "A1")
    assert c.below_mde
    assert not c.notable


def test_cross_intervals_come_from_wilson() -> None:
    a = report(rows("A1", {f"c{i}": "pass" for i in range(4)}),
               manifest={**_WORLD, "seed": 1})
    b = report(rows("A1", {f"c{i}": "fail" for i in range(4)}),
               manifest={**_WORLD, "seed": 2})
    c = cross_compare(a, b, "A1")
    assert c.ci_a == wilson(4, 4)
    assert c.ci_b == wilson(0, 4)


def test_paired_and_within_run_compare_share_one_implementation() -> None:
    """Same data through both doors must produce the same se."""
    outcomes_a = {f"c{i}": "pass" if i % 2 == 0 else "fail" for i in range(6)}
    outcomes_b = {f"c{i}": "pass" for i in range(6)}
    # Within-run: two arms in one report.
    within = report(rows("A1", outcomes_a), rows("B1", outcomes_b),
                    manifest=_WORLD)
    # Cross-run: same numbers, one arm each, same world.
    a = report(rows("A1", outcomes_a), manifest=_WORLD)
    b = report(rows("A1", outcomes_b), manifest=_WORLD)
    # compare(A1, B1) is B1 - A1 in the within-run convention? Check:
    # compare uses _paired_diff(rates_a, rates_b) => a - b.
    # cross_compare uses _paired_diff(rates_b, rates_a) => b - a (vs reference).
    # So compare(A1, B1).diff == -cross_compare(a,b).diff when A1 is reference.
    within_c = compare(within, "A1", "B1")
    cross_c = cross_compare(a, b, "A1")
    assert within_c is not None and cross_c is not None
    assert within_c.se == pytest.approx(cross_c.se)
    assert within_c.diff == pytest.approx(-cross_c.diff)
