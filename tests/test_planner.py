from __future__ import annotations

import pytest

from harness.engine.axes import (
    Caching, ConfigError, DocBudget, ErrorDetail, McpRevision, ResponseShape,
    SchemaDetail,
)
from harness.engine.metrics import Validation, all_metrics, gold_free
from harness.engine.lint import (
    Confidence, Finding, Justification, Rule, Severity, register, scorecard,
)
from harness.engine.packaging import CostBreakdown, Provenance
from harness.engine.planner import BudgetNotApproved, Contrast, RunPlan

BASE = dict(
    schema_detail=SchemaDetail.STANDARD,
    response_shape=ResponseShape.AS_IS,
    error_detail=ErrorDetail.FIELD_SCOPED,
    doc_budget=DocBudget.STANDARD,
    surface_size=15,
    model="test-model",
    reasoning_effort="medium",
    temperature=0.0,
    caching=Caching.OFF,
    repeats=3,
    mcp_revision=McpRevision.R2026_07_28,
)


class FakeProvider:
    name = "fake"

    def capabilities(self): ...
    def submit(self, messages, tools, config): ...
    def price_per_mtok(self, model: str) -> tuple[float, float]:
        return (2.50, 15.00)


def plan(**kw) -> RunPlan:
    return RunPlan(
        id=kw.pop("id", "p1"),
        rationale=kw.pop("rationale", "test the thing"),
        base=kw.pop("base", BASE),
        presets=kw.pop("presets", ("A1", "B1")),
        task_count=kw.pop("task_count", 10),
        **kw,
    )


def test_rationale_is_mandatory() -> None:
    with pytest.raises(ConfigError, match="no rationale"):
        plan(rationale="   ")


def test_plan_materialises_every_selected_cell() -> None:
    v = plan(presets=("A1", "C1", "D1", "Z0")).variants()
    assert set(v) == {"A1", "C1", "D1", "Z0"}


def test_contrast_across_mcp_revision_is_refused() -> None:
    p = plan(presets=("A1", "M1"), confirmatory=(Contrast(("A1", "M1")),))
    p.base = {**BASE, "mcp_revision": McpRevision.LEGACY}
    with pytest.raises(ConfigError, match="mcp_revision"):
        p.validate_contrasts()


def test_contrast_across_skill_authorship_is_refused() -> None:
    p = plan(presets=("B1", "B1-auth"), confirmatory=(Contrast(("B1", "B1-auth")),))
    with pytest.raises(ConfigError, match="skill authorship"):
        p.validate_contrasts()


def test_within_revision_contrast_is_allowed() -> None:
    p = plan(presets=("A1", "B1"), confirmatory=(Contrast(("A1", "B1"), "P4"),))
    p.validate_contrasts()  # no raise


def test_preregistration_required_before_publishable_runs() -> None:
    with pytest.raises(ConfigError, match="no confirmatory contrasts"):
        plan().require_preregistration()
    plan(confirmatory=(Contrast(("A1", "B1"), "P4"),)).require_preregistration()


def test_estimate_scales_with_reasoning_effort() -> None:
    """Estimating with flat output is how a matrix costs 10x its estimate."""
    low = plan(base={**BASE, "reasoning_effort": "low"}).estimate(FakeProvider())
    high = plan(base={**BASE, "reasoning_effort": "high"}).estimate(FakeProvider())
    assert high.output_tokens > low.output_tokens * 4
    assert high.projected_usd > low.projected_usd


def test_estimate_counts_repeats_and_tasks() -> None:
    e = plan(presets=("A1", "B1"), task_count=10).estimate(FakeProvider())
    assert e.runs == 2 * 3 * 10


def test_nothing_executes_without_approval() -> None:
    p = plan()
    est = p.estimate(FakeProvider())
    with pytest.raises(BudgetNotApproved, match="has not been approved"):
        p.require_approval(est)
    p.approve(est)
    p.require_approval(est)


def test_changing_the_matrix_invalidates_approval() -> None:
    p = plan()
    p.approve(p.estimate(FakeProvider()))
    p.presets = ("A1", "B1", "C1", "D1")
    with pytest.raises(BudgetNotApproved, match="different matrix size"):
        p.require_approval(p.estimate(FakeProvider()))


# ---- metrics -------------------------------------------------------------

def test_every_metric_starts_unvalidated() -> None:
    """The rig has not run. Claiming otherwise would be the dishonest default."""
    assert all(m.validation is Validation.UNVALIDATED for m in all_metrics())


def test_validated_status_requires_a_citation() -> None:
    from harness.engine.metrics import Bucket, Metric
    with pytest.raises(ValueError, match="names no validating run"):
        Metric(name="x", bucket=Bucket.COST, description="", needs_gold=False,
               validation=Validation.VALIDATED_CONTROLLED)


def test_gold_free_metrics_exist_for_field_mode() -> None:
    names = {m.name for m in gold_free()}
    assert {"argument_validity", "error_recovery_rate", "static_context_tokens"} <= names


# ---- lint ----------------------------------------------------------------

def test_unjustified_rule_is_labelled_heuristic() -> None:
    r = Rule(id="r-unjust", severity=Severity.HIGH, summary="s",
             check=lambda spec: [Finding("r-unjust", Severity.HIGH,
                                         Confidence.HEURISTIC, "m")])
    assert r.confidence is Confidence.HEURISTIC
    assert r.run(None)[0].confidence is Confidence.HEURISTIC


def test_justified_rule_is_labelled_measured() -> None:
    r = Rule(id="r-just", severity=Severity.HIGH, summary="s",
             check=lambda spec: [Finding("r-just", Severity.HIGH,
                                         Confidence.HEURISTIC, "m")],
             justified_by=(Justification("run-1", "argument_validity", "+19pp"),))
    assert r.confidence is Confidence.MEASURED
    # The rule's own status overrides whatever the check function claims.
    assert r.run(None)[0].confidence is Confidence.MEASURED


def test_scorecard_footer_states_how_much_is_measured() -> None:
    from harness.engine.lint import _REGISTRY

    # Other tests register the built-in rules into this module-level dict and
    # leave them there. scorecard(None) would then walk those checks, which
    # expect an ApiSpec — isolate so this assertion is order-independent.
    saved = dict(_REGISTRY)
    _REGISTRY.clear()
    try:
        register(Rule(id="z-demo", severity=Severity.LOW, summary="s",
                      check=lambda spec: []))
        card = scorecard(None)
        assert "heuristic" in card.footer()
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(saved)


# ---- packaging -----------------------------------------------------------

def test_cost_breakdown_separates_per_call_from_per_session() -> None:
    """The A-vs-D ranking turns on this decomposition."""
    chatty = CostBreakdown(static_tokens=8000, per_call_overhead_tokens=40 * 120)
    batched = CostBreakdown(static_tokens=2000, per_call_overhead_tokens=3 * 120)
    assert chatty.per_call_overhead_tokens > batched.per_call_overhead_tokens
    assert chatty.total_tokens() > batched.total_tokens()


def test_authored_materials_require_a_preregistration_commit() -> None:
    with pytest.raises(ValueError, match="authored_commit"):
        Provenance(generator="authored", spec_revision="1")
    Provenance(generator="authored", spec_revision="1", authored_commit="abc123")
