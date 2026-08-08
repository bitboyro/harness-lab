"""Results persistence and reporting."""

from __future__ import annotations

import json

import pytest

from harness.engine.reporting import ArmSummary, render
from harness.engine.results import ResultStore, Row

BASE = dict(
    run_id="r1", arm="A1", task_id="t1", core_id="c1", task_class="R", answerable=True, repeat=0,
    outcome="pass", detail="", confident=False, clobbered=(), turns=3, calls=2,
    forbidden_attempts=0, truncated=False, error=None, error_kind=None,
    wall_clock_seconds=1.0,
    input_tokens=1000, cached_input_tokens=0, output_tokens=100,
    reasoning_tokens=0, static_tokens=500, per_call_overhead_tokens=0,
    session_setup_tokens=0, model="gpt-5.6-luna", mcp_spec_revision="2026-07-28",
    skill_condition="none", report_class="controlled", seed=1, surface_size=0,
)


def row(**kw) -> Row:
    return Row(**{**BASE, **kw})


def test_rows_are_written_immediately(tmp_path) -> None:
    """A matrix that dies two thirds through must leave two thirds on disk."""
    store = ResultStore(tmp_path)
    store.record(row(run_id="a", task_id="t1"))
    assert len(list(store.rows())) == 1
    store.record(row(run_id="b", task_id="t2"))
    assert len(list(store.rows())) == 2


def test_resume_skips_completed_runs(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store.record(row(arm="A1", task_id="t1", repeat=0))
    store.record(row(arm="A1", task_id="t2", repeat=0))
    assert store.completed() == {("A1", "t1", 0), ("A1", "t2", 0)}


def test_manifest_records_what_produced_the_results(tmp_path) -> None:
    store = ResultStore(tmp_path)
    store.write_manifest(id="phase-0", model="gpt-5.6-luna", cores=40)
    manifest = store.manifest()
    assert manifest["model"] == "gpt-5.6-luna"
    assert manifest["cores"] == 40
    assert "created_at" in manifest


def test_empty_store_reports_nothing_rather_than_crashing(tmp_path) -> None:
    assert "No results" in render(list(ResultStore(tmp_path).rows()))


# ---- the reporting rules -------------------------------------------------

def test_truncated_runs_excluded_from_success_rate() -> None:
    arm = ArmSummary("A1", [
        dict(BASE, outcome="pass", truncated=False),
        dict(BASE, outcome="truncated", truncated=True),
        dict(BASE, outcome="truncated", truncated=True),
    ])
    assert arm.success_rate == 1.0, "truncation is a budget failure, not a wrong answer"
    assert arm.truncation_rate == pytest.approx(2 / 3)


def test_z0_gate_counts_only_substantive_answers() -> None:
    """Correct refusal with no tools is expected behaviour, not leakage.

    Counting it would fail every clean rig — which is exactly what happened
    before this was fixed.
    """
    rows = [
        dict(BASE, arm="Z0", mcp_spec_revision=None, outcome="correct-refusal"),
        dict(BASE, arm="Z0", mcp_spec_revision=None, outcome="correct-refusal"),
        dict(BASE, arm="Z0", mcp_spec_revision=None, outcome="fail"),
        dict(BASE, arm="Z0", mcp_spec_revision=None, outcome="fail"),
    ]
    text = render(rows)
    assert "Z0 gate: PASS" in text
    assert "0/4" in text


def test_z0_gate_fails_on_real_leakage() -> None:
    rows = [dict(BASE, arm="Z0", mcp_spec_revision=None, outcome="pass")
            for _ in range(4)]
    assert "DOMAIN CONTAMINATED" in render(rows)


def test_control_arms_do_not_trip_the_pooling_guard() -> None:
    """Z0 has no MCP revision because it has no MCP — that is an absence, not a
    second world, and treating it as one blocked every report containing it."""
    rows = [
        dict(BASE, arm="A1", mcp_spec_revision="2026-07-28"),
        dict(BASE, arm="Z0", mcp_spec_revision=None),
    ]
    assert "REFUSING TO POOL" not in render(rows)


def test_genuinely_different_worlds_are_refused() -> None:
    rows = [
        dict(BASE, arm="A1", mcp_spec_revision="2026-07-28"),
        dict(BASE, arm="A1", mcp_spec_revision="legacy"),
    ]
    assert "REFUSING TO POOL" in render(rows)


def test_authored_and_generated_skills_are_refused() -> None:
    rows = [
        dict(BASE, arm="B1", skill_condition="generated"),
        dict(BASE, arm="B1", skill_condition="authored"),
    ]
    assert "REFUSING TO POOL" in render(rows)


def test_harm_counts_blocked_attempts_and_clobbers() -> None:
    arm = ArmSummary("C1", [
        dict(BASE, clobbered=["$.a"], forbidden_attempts=0),
        dict(BASE, clobbered=[], forbidden_attempts=1),
        dict(BASE, clobbered=[], forbidden_attempts=0),
    ])
    assert arm.harm_events == 2


def test_silent_failure_is_confident_and_wrong() -> None:
    arm = ArmSummary("A1", [
        dict(BASE, outcome="fail", confident=True),
        dict(BASE, outcome="fail", confident=False),
        dict(BASE, outcome="pass", confident=True),
    ])
    assert arm.silent_failure_rate == 0.5


def test_per_class_breakdown_is_the_rq4_view() -> None:
    arm = ArmSummary("A1", [
        dict(BASE, task_class="R", outcome="pass"),
        dict(BASE, task_class="W-safe", outcome="fail"),
        dict(BASE, task_class="W-safe", outcome="fail"),
    ])
    per = arm.by_class()
    assert per["R"] == 1.0 and per["W-safe"] == 0.0


def test_report_names_harness_errors_separately() -> None:
    rows = [dict(BASE, outcome="fail", error="provider timeout")]
    assert "harness errors" in render(rows)


def test_footer_states_the_pooling_rules() -> None:
    assert "Never pool across model" in render([dict(BASE)])
