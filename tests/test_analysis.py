"""The analysis layer: confusion metrics, Wilson intervals, and anti-drift."""

from __future__ import annotations

import pytest

from harness.engine.analysis import Confusion, Report, wilson
from harness.engine.html import render_html, standalone_html
from harness.engine.reporting import render

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


# ---- confusion -----------------------------------------------------------

def test_outcomes_map_to_the_right_cells() -> None:
    c = Confusion(tp=6, fp=1, tn=2, fn_abstained=2, fn_confident=1)
    assert c.fn == 3
    assert c.total == 12


def test_precision_and_recall_by_hand() -> None:
    c = Confusion(tp=6, fp=2, tn=4, fn_abstained=1, fn_confident=1)
    assert c.precision == pytest.approx(6 / 8)
    assert c.recall == pytest.approx(6 / 8)
    assert c.specificity == pytest.approx(4 / 6)
    assert c.f1 == pytest.approx(0.75)
    assert c.accuracy == pytest.approx(10 / 14)


def test_zero_denominators_return_none_not_zero() -> None:
    """None means 'not measurable'; 0.0 means 'measured and bad'."""
    empty = Confusion()
    assert empty.precision is None
    assert empty.recall is None
    assert empty.f1 is None
    assert empty.accuracy is None
    assert empty.mcc is None
    assert Confusion(tp=1).specificity is None


def test_mcc_exposes_an_agent_that_answers_everything() -> None:
    """The reason MCC sits next to accuracy rather than instead of it.

    With ~15% unanswerable tasks, an agent that never declines scores high
    accuracy while being maximally unsafe — MCC collapses to 0.
    """
    reckless = Confusion(tp=85, fp=15, tn=0, fn_abstained=0, fn_confident=0)
    assert reckless.accuracy == pytest.approx(0.85)
    assert reckless.mcc is None or abs(reckless.mcc) < 1e-9
    assert reckless.specificity == 0.0

    careful = Confusion(tp=80, fp=1, tn=14, fn_abstained=5, fn_confident=0)
    assert careful.accuracy == pytest.approx(0.94)
    assert careful.mcc is not None and careful.mcc > 0.6


def test_balanced_accuracy_diverges_from_accuracy_on_skew() -> None:
    c = Confusion(tp=85, fp=15, tn=0, fn_abstained=0, fn_confident=0)
    assert c.balanced_accuracy == pytest.approx(0.5)
    assert c.accuracy == pytest.approx(0.85)


def test_perfect_classifier() -> None:
    c = Confusion(tp=6, fp=0, tn=2, fn_abstained=0, fn_confident=0)
    assert c.mcc == pytest.approx(1.0)
    assert c.f1 == pytest.approx(1.0)


def test_failure_split_separates_hedged_from_confident() -> None:
    """Wrong and hedged is a different failure from wrong and convincing."""
    c = Confusion(tp=1, fn_abstained=3, fn_confident=2)
    assert c.fn_abstained == 3 and c.fn_confident == 2


# ---- Wilson --------------------------------------------------------------

def test_wilson_stays_inside_zero_and_one() -> None:
    """The normal approximation runs past the bounds at exactly these n."""
    lo, hi = wilson(8, 8)
    assert 0 <= lo <= hi <= 1
    assert hi == pytest.approx(1.0)
    assert lo < 1.0

    lo, hi = wilson(0, 8)
    assert lo == pytest.approx(0.0)
    assert 0 < hi < 1


def test_wilson_narrows_with_n() -> None:
    small = wilson(5, 10)
    large = wilson(50, 100)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_wilson_known_value() -> None:
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)


def test_wilson_on_empty_is_none() -> None:
    assert wilson(0, 0) is None


# ---- report ---------------------------------------------------------------

def _report(rows, **kw) -> Report:
    return Report(rows=rows, manifest={"id": "t", "model": "gpt-5.6-luna"}, **kw)


def test_confusion_built_from_rows() -> None:
    rows = [
        dict(BASE, outcome="pass"),
        dict(BASE, outcome="fail", confident=True, answerable=True),
        dict(BASE, outcome="correct-refusal", answerable=False),
        dict(BASE, outcome="false-positive", answerable=False, confident=True),
        dict(BASE, outcome="truncated", truncated=True),
    ]
    c = _report(rows).arms["A1"].confusion
    assert (c.tp, c.fp, c.tn, c.fn_confident) == (1, 1, 1, 1)
    assert c.total == 4, "truncated is excluded, as everywhere else"


def test_declined_but_clobbered_is_not_a_true_negative() -> None:
    """Mutating while refusing must lower abstention, not inflate TN."""
    rows = [
        dict(BASE, outcome="correct-refusal", answerable=False),
        dict(BASE, outcome="declined-but-clobbered", answerable=False,
             clobbered=["$.episodes.ep_1.rating"]),
        dict(BASE, outcome="false-positive", answerable=False, confident=True),
    ]
    arm = _report(rows).arms["A1"]
    c = arm.confusion
    assert c.tn == 1 and c.declined_clobbered == 1 and c.fp == 1
    assert c.specificity == pytest.approx(1 / 3)
    assert arm.abstention_accuracy == c.specificity
    assert arm.outcome_counts()["declined-but-clobbered"] == 1
    assert arm.harm_events == 1


def test_below_mde_flags_small_differences() -> None:
    rows = [dict(BASE, arm="Z0", outcome="fail", mcp_spec_revision=None),
            dict(BASE, arm="A1", outcome="pass")]
    r = _report(rows, mde_pp=200.0)
    assert r.below_mde("A1"), "a 100pp lift is below a 200pp MDE"
    assert not _report(rows, mde_pp=10.0).below_mde("A1")


def test_incomplete_arms_are_named() -> None:
    """A missing cell is not a zero."""
    rows = ([dict(BASE, arm="A1", task_id=f"t{i}") for i in range(8)]
            + [dict(BASE, arm="D1", task_id=f"t{i}") for i in range(5)])
    assert _report(rows).incomplete_arms == {"D1": (5, 8)}


def test_varying_and_constant_metrics_are_separated() -> None:
    rows = [dict(BASE, metrics={"turns": 3, "flat": 0}),
            dict(BASE, metrics={"turns": 7, "flat": 0})]
    r = _report(rows)
    assert r.varying_metrics() == ["turns"]
    assert r.constant_metrics() == {"flat": 0}


def test_inferred_answerable_detected_on_old_ledgers() -> None:
    old = dict(BASE)
    del old["answerable"]
    assert _report([old]).inferred_answerable
    assert not _report([dict(BASE)]).inferred_answerable


# ---- anti-drift ----------------------------------------------------------

def _fixture_rows() -> list[dict]:
    return [
        dict(BASE, arm="Z0", outcome="fail", mcp_spec_revision=None),
        dict(BASE, arm="Z0", outcome="correct-refusal", answerable=False,
             mcp_spec_revision=None),
        dict(BASE, arm="A1", outcome="pass"),
        dict(BASE, arm="A1", outcome="fail", confident=True),
        dict(BASE, arm="A1", outcome="correct-refusal", answerable=False),
        dict(BASE, arm="C1", outcome="pass", truncated=True, outcome_x=None),
    ]


def test_text_and_html_agree_on_every_rate() -> None:
    """The whole point of the shared analysis layer.

    Both renderers read one Report; if either recomputed anything, this is
    where the drift would show.
    """
    rows = [r for r in _fixture_rows()]
    for r in rows:
        r.pop("outcome_x", None)
    report = Report(rows=rows, manifest={"id": "t", "model": "gpt-5.6-luna"})

    text = render(rows, report.manifest, report=report)
    html = render_html(report)

    for name, arm in report.arms.items():
        if arm.success_rate is None:
            continue
        rendered = f"{arm.success_rate:.0%}"
        assert rendered in text, f"{name} {rendered} missing from text"
        assert rendered in html, f"{name} {rendered} missing from html"


def test_html_has_no_external_requests() -> None:
    """Self-contained: a report must render with no network at all."""
    rows = [dict(BASE)]
    html = standalone_html(Report(rows=rows, manifest={"id": "t"}))
    external = [line for line in html.split('"')
                if line.startswith(("http://", "https://"))
                and "www.w3.org/2000/svg" not in line]
    assert not external, f"external references: {external[:3]}"


def test_html_declares_a_charset() -> None:
    """Without it a browser guesses latin-1 and every em dash becomes mojibake."""
    html = standalone_html(Report(rows=[dict(BASE)], manifest={"id": "t"}))
    assert '<meta charset="utf-8">' in html


def test_pooling_banner_appears_when_worlds_differ() -> None:
    rows = [dict(BASE, mcp_spec_revision="2026-07-28"),
            dict(BASE, mcp_spec_revision="legacy")]
    html = render_html(_report(rows))
    assert "Refusing to pool" in html


def test_no_pooling_banner_for_control_arms() -> None:
    rows = [dict(BASE, arm="A1", mcp_spec_revision="2026-07-28"),
            dict(BASE, arm="Z0", mcp_spec_revision=None)]
    assert "Refusing to pool" not in render_html(_report(rows))


def test_unpriced_model_says_so_instead_of_empty_axes() -> None:
    rows = [dict(BASE, model="some-unpriced-model")]
    html = render_html(Report(rows=rows, manifest={"id": "t",
                                                   "model": "some-unpriced-model"}))
    assert "not in the pricing table" in html


def test_incomplete_banner_names_the_short_arm() -> None:
    rows = ([dict(BASE, arm="A1", task_id=f"t{i}") for i in range(8)]
            + [dict(BASE, arm="D1", task_id=f"t{i}") for i in range(5)])
    html = render_html(_report(rows))
    assert "Incomplete" in html and "D1 (5 of 8 runs)" in html


def test_mde_banner_states_the_threshold() -> None:
    html = render_html(_report([dict(BASE)], mde_pp=23.2))
    assert "23 pp" in html and "not findings" in html


def test_empty_report_does_not_crash() -> None:
    assert "No results" in render([])
