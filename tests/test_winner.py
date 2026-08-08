"""Ranking, arm names, and the composite verdict.

The verdict is the part of the report a reader is most likely to quote without
reading the caveats, so these tests are mostly about the ways it must *refuse*
to name a winner.
"""

from __future__ import annotations

import pytest

from harness.engine.analysis import RANK_KEYS, Report
from harness.engine.axes import (Caching, DocBudget, ErrorDetail, McpRevision,
                                 ResponseShape, SchemaDetail, preset, short_name)
from harness.engine.winner import (DEFAULT_WEIGHTS, WeightError, evaluate,
                                   parse_weights)

BASE = dict(
    run_id="r1", arm="A1", task_id="t1", core_id="c1", task_class="R",
    answerable=True, repeat=0, outcome="pass", detail="", confident=False,
    clobbered=[], turns=3, calls=2, forbidden_attempts=0, truncated=False,
    error=None, wall_clock_seconds=1.0, input_tokens=1000,
    cached_input_tokens=0, output_tokens=100, reasoning_tokens=0,
    static_tokens=500, per_call_overhead_tokens=0, session_setup_tokens=0,
    model="gpt-5.6-luna", mcp_spec_revision="2026-07-28",
    skill_condition="none", report_class="controlled", seed=1, surface_size=0,
    metrics={"turns": 3},
)


def row(**over):
    return {**BASE, **over}


def rows_for(arm: str, *, passes: int, fails: int = 0, core: str = "c1",
             **over) -> list[dict]:
    out = [row(arm=arm, outcome="pass", core_id=core, task_id=f"{core}-p{i}",
               **over) for i in range(passes)]
    out += [row(arm=arm, outcome="fail", core_id=core, task_id=f"{core}-f{i}",
                **over) for i in range(fails)]
    return out


# ---- names ---------------------------------------------------------------

def _variant(name: str):
    return preset(name, schema_detail=SchemaDetail.STANDARD,
                  response_shape=ResponseShape.AS_IS,
                  error_detail=ErrorDetail.FIELD_SCOPED,
                  doc_budget=DocBudget.STANDARD, surface_size=0,
                  model="m", reasoning_effort="low", temperature=0.0,
                  caching=Caching.OFF, repeats=1,
                  mcp_revision=McpRevision.R2026_07_28)


@pytest.mark.parametrize("arm,expected", [
    ("A1", "MCP, all tools"),
    ("A2", "MCP, discovery"),
    ("B1", "MCP, all tools + skill"),
    ("B1-auth", "MCP, all tools + authored skill"),
    ("C1", "Bash + docs"),
    ("C2", "Bash + index"),
    ("D1", "Code sandbox"),
    ("D2-auth", "Code sandbox + authored skill"),
    ("E1", "MCP, retrieved"),
    ("M1", "MCP, all tools + confirm"),
    ("Z0", "No tools"),
    ("Z1", "Answers handed over"),
])
def test_short_names_are_derived_from_the_axes(arm: str, expected: str) -> None:
    assert short_name(_variant(arm)) == expected


def test_every_preset_gets_a_name() -> None:
    from harness.engine.axes import PRESET_NAMES
    for name in PRESET_NAMES:
        assert short_name(_variant(name)), f"{name} has no short name"


def test_name_falls_back_to_the_preset_on_legacy_ledgers() -> None:
    """A ledger written before `axes.name` existed must still label its arms."""
    report = Report(rows=rows_for("A1", passes=2), manifest={})
    assert report.arms["A1"].name == "MCP, all tools"
    assert report.arms["A1"].label == "A1 · MCP, all tools"


def test_name_prefers_the_recorded_assignment_over_the_preset() -> None:
    """A sweep can override an axis; the recorded value is the truth."""
    rows = rows_for("A1", passes=1, axes={"name": "MCP, all tools + docs"})
    assert Report(rows=rows, manifest={}).arms["A1"].name == "MCP, all tools + docs"


# ---- weights -------------------------------------------------------------

def test_weights_normalise_to_one() -> None:
    assert sum(parse_weights("success=2,cost=2").values()) == pytest.approx(1.0)


def test_unnamed_dimensions_are_dropped_not_defaulted() -> None:
    """`--weights harm=1` means harm alone, not harm plus the defaults."""
    assert parse_weights("harm=1") == {"harm": 1.0}


@pytest.mark.parametrize("spec", ["", "nonsense", "harm", "harm=x",
                                  "harm=-1", "harm=0", "bogus=1"])
def test_bad_weights_raise_rather_than_silently_defaulting(spec: str) -> None:
    with pytest.raises(WeightError):
        parse_weights(spec)


def test_default_weights_put_safety_above_thrift() -> None:
    """An arm must not be able to buy the top spot by being cheap and dangerous."""
    safety = DEFAULT_WEIGHTS["harm"] + DEFAULT_WEIGHTS["abstention"]
    thrift = DEFAULT_WEIGHTS["cost"] + DEFAULT_WEIGHTS["time"]
    assert safety > thrift
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


# ---- candidacy -----------------------------------------------------------

def test_controls_never_win_even_when_they_score_highest() -> None:
    rows = (rows_for("Z1", passes=10) + rows_for("A1", passes=5, fails=5)
            + rows_for("A2", passes=4, fails=6))
    verdict = evaluate(Report(rows=rows, manifest={}))
    assert "Z1" not in verdict.scores
    assert verdict.winner in {"A1", "A2"}


def test_controls_are_excluded_from_the_normalisation_range() -> None:
    """Z1's ceiling must not compress the real arms into the bottom of the scale."""
    arms = rows_for("A1", passes=5, fails=5) + rows_for("A2", passes=4, fails=6)
    without = evaluate(Report(rows=arms, manifest={})).scores
    with_ceiling = evaluate(Report(rows=arms + rows_for("Z1", passes=10),
                                   manifest={})).scores
    assert without == pytest.approx(with_ceiling)


def test_fewer_than_two_candidates_declines_to_pick() -> None:
    verdict = evaluate(Report(rows=rows_for("A1", passes=3)
                              + rows_for("Z0", passes=1), manifest={}))
    assert verdict.winner is None
    assert "nothing to rank" in verdict.reason


def test_controls_only_declines_to_pick() -> None:
    verdict = evaluate(Report(rows=rows_for("Z0", passes=2), manifest={}))
    assert verdict.winner is None
    assert "only controls" in verdict.reason


# ---- ties ----------------------------------------------------------------

def test_an_exact_tie_names_no_winner() -> None:
    """Picking whichever sorts first would be arbitrary, and read as a result."""
    rows = rows_for("A1", passes=5, fails=5) + rows_for("A2", passes=5, fails=5)
    verdict = evaluate(Report(rows=rows, manifest={}), {"success": 1.0})
    assert verdict.winner is None
    assert set(verdict.tied_leaders) == {"A1", "A2"}
    assert any("No winner" in c for c in verdict.caveats)


def test_a_flat_dimension_is_called_out() -> None:
    rows = rows_for("A1", passes=6, fails=4) + rows_for("A2", passes=4, fails=6)
    verdict = evaluate(Report(rows=rows, manifest={}), {"harm": 1.0})
    assert any("separated nothing" in c for c in verdict.caveats)


# ---- missing data --------------------------------------------------------

def test_an_unavailable_dimension_is_dropped_and_the_rest_rescaled() -> None:
    rows = [row(model="no-such-model", arm=a, outcome=o, task_id=f"{a}{i}")
            for a in ("A1", "A2")
            for i, o in enumerate(["pass", "pass", "fail"])]
    verdict = evaluate(Report(rows=rows, manifest={"model": "no-such-model"}))
    assert "cost" in verdict.dropped
    assert sum(verdict.weights.values()) == pytest.approx(1.0)
    assert any("was dropped" in c for c in verdict.caveats)


def test_a_missing_value_is_not_scored_as_zero() -> None:
    """Imputing zero turns a coverage gap into a real penalty."""
    # A2 sees no unanswerable tasks at all, so it has no abstention score.
    rows = (rows_for("A1", passes=5, fails=5)
            + [row(arm="A1", outcome="correct-refusal", answerable=False,
                   task_id="u1")]
            + rows_for("A2", passes=5, fails=5))
    verdict = evaluate(Report(rows=rows, manifest={}))
    assert "abstention" in verdict.partial
    assert "A2" in verdict.partial["abstention"]
    assert verdict.scores["A2"] > 0.0
    assert any("coverage gap" in c for c in verdict.caveats)


# ---- the honesty line ----------------------------------------------------

def test_a_lead_below_the_mde_is_reported_as_a_tie_on_success() -> None:
    rows = rows_for("A1", passes=6, fails=4) + rows_for("A2", passes=5, fails=5)
    report = Report(rows=rows, manifest={}, mde_pp=40.0)
    verdict = evaluate(report)
    assert any("TIED" in c for c in verdict.caveats)


def test_a_winner_that_harms_more_says_so() -> None:
    rows = (rows_for("A1", passes=8, fails=2, clobbered=["x"])
            + rows_for("A2", passes=3, fails=7))
    verdict = evaluate(Report(rows=rows, manifest={}), {"success": 1.0})
    assert verdict.winner == "A1"
    assert any("more harm" in c for c in verdict.caveats)


def test_a_winner_that_fabricates_more_says_so() -> None:
    rows = (rows_for("A1", passes=9, fails=1)
            + [row(arm="A1", outcome="false-positive", answerable=False,
                   task_id="u1")]
            + rows_for("A2", passes=2, fails=8)
            + [row(arm="A2", outcome="correct-refusal", answerable=False,
                   task_id="u2")])
    verdict = evaluate(Report(rows=rows, manifest={}), {"success": 1.0})
    assert verdict.winner == "A1"
    assert any("fabricates more" in c for c in verdict.caveats)


def test_correct_refusals_count_toward_success() -> None:
    """The success rate already credits abstention — abstention re-weights it."""
    rows = [row(arm="A1", outcome="correct-refusal", answerable=False,
                task_id=f"u{i}") for i in range(4)]
    assert Report(rows=rows, manifest={}).arms["A1"].success_rate == 1.0


# ---- ranking -------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(RANK_KEYS))
def test_every_rank_key_orders_without_error(key: str) -> None:
    rows = (rows_for("A1", passes=6, fails=4) + rows_for("A2", passes=4, fails=6)
            + rows_for("Z0", passes=1, fails=9))
    order = Report(rows=rows, manifest={}).ranked(key)
    assert {a.arm for a in order} == {"A1", "A2", "Z0"}


def test_ranking_puts_the_best_first() -> None:
    rows = rows_for("A1", passes=8, fails=2) + rows_for("A2", passes=2, fails=8)
    report = Report(rows=rows, manifest={})
    assert report.ranked("success")[0].arm == "A1"
    # `turns` is lower-is-better, so the direction must invert.
    rows = (rows_for("A1", passes=5, fails=5, turns=9)
            + rows_for("A2", passes=5, fails=5, turns=2))
    assert Report(rows=rows, manifest={}).ranked("turns")[0].arm == "A2"


def test_arms_with_no_value_sort_last_not_as_zero() -> None:
    """An absent number at the top of a lower-is-better column is a lie."""
    rows = (rows_for("A1", passes=5, fails=5)
            + [row(arm="A2", outcome="truncated", truncated=True,
                   task_id=f"t{i}") for i in range(4)])
    order = Report(rows=rows, manifest={}).ranked("success")
    assert order[-1].arm == "A2"  # A2 has no graded runs at all


def test_best_on_ignores_controls() -> None:
    rows = (rows_for("Z1", passes=10) + rows_for("A1", passes=5, fails=5)
            + rows_for("A2", passes=2, fails=8))
    assert Report(rows=rows, manifest={}).best_on("success") == "A1"


# ---- metric spread -------------------------------------------------------

def test_one_outlier_against_zeros_does_not_outrank_a_real_spread() -> None:
    """The bug this replaced a coefficient of variation to fix."""
    rows = []
    for i, arm in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        rows += rows_for(arm, passes=2, metrics={
            # eight-of-nine-are-zero shape: only B2 moves, and barely
            "outlier": 0.15 if arm == "B2" else 0.0,
            # a genuine spread across most arms
            "real": float(i),
        })
    report = Report(rows=rows, manifest={})
    assert report.metric_spread("real") > report.metric_spread("outlier")


def test_a_constant_metric_has_no_spread() -> None:
    rows = rows_for("A1", passes=2, metrics={"flat": 1.0}) + \
        rows_for("A2", passes=2, metrics={"flat": 1.0})
    assert Report(rows=rows, manifest={}).metric_spread("flat") == 0.0


def test_behaviour_section_filters_to_mechanism_metrics() -> None:
    """Turns and seconds are cost; they have their own tables."""
    rows = rows_for("A1", passes=2, metrics={"turns": 1.0, "wasted_calls": 1.0}) \
        + rows_for("A2", passes=2, metrics={"turns": 9.0, "wasted_calls": 5.0})
    names = Report(rows=rows, manifest={}).metrics_by_spread("mechanism")
    assert "wasted_calls" in names
    assert "turns" not in names
