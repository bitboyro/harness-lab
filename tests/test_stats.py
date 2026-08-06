"""Paired contrasts and multiplicity control."""

from __future__ import annotations

import pytest

from harness.engine.analysis import Report
from harness.engine.stats import CONFIRMATORY, Contrast, analyse, compare, holm

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


def rows(arm: str, outcomes: dict[str, str]) -> list[dict]:
    return [dict(BASE, arm=arm, core_id=core, task_id=f"{core}-{arm}",
                 outcome=outcome)
            for core, outcome in outcomes.items()]


def report(*groups) -> Report:
    flat = [r for g in groups for r in g]
    return Report(rows=flat, manifest={"id": "t", "model": "gpt-5.6-luna"})


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
