"""Run plan as config — shipped tiers, approval persistence, additive load."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.engine.planner import (
    BudgetNotApproved, load_approvals, load_plan, persist_approval,
)

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "plans"


@pytest.mark.parametrize("name", ["smoke", "probe", "standard", "full"])
def test_shipped_plans_load(name: str) -> None:
    plan = load_plan(PLANS / f"{name}.yaml")
    assert plan.id == name
    assert plan.rationale.strip()
    assert plan.presets
    assert plan.tasks.get("generate") or plan.task_count >= 1


def test_example_plan_still_loads() -> None:
    plan = load_plan(ROOT / "examples/plan.yaml")
    assert plan.presets == ("Z0", "A1", "A2", "C1", "D1")
    assert plan.task_count == 40


def test_approval_persists_by_digest(tmp_path, monkeypatch) -> None:
    from harness.engine import planner as planner_mod
    monkeypatch.setattr(planner_mod, "_APPROVAL_PATH", tmp_path / "approved.json")

    plan = load_plan(PLANS / "smoke.yaml")
    from harness.engine.providers import get
    estimate = plan.estimate(get("openai"))
    with pytest.raises(BudgetNotApproved):
        plan.require_approval(estimate)
    plan.approve(estimate, persist=True)
    assert plan.is_approved(estimate)
    # Fresh object, same digest — still approved on disk.
    again = load_plan(PLANS / "smoke.yaml")
    assert again.is_approved(estimate)
    stored = load_approvals(tmp_path / "approved.json")
    assert plan.digest() in stored


def test_full_plan_declares_sweep() -> None:
    plan = load_plan(PLANS / "full.yaml")
    assert "error_detail" in plan.sweep
    assert "D3" in plan.presets
