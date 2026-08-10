"""Dispatcher, grader, and field reporting."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from conftest import BASE_AXES, ScriptedProvider, call, say

from harness.engine.axes import preset
from harness.engine.dispatch import (
    DESCRIBE, INVOKE, SEARCH, MetaToolDispatcher, OperationIndex, RetrievalDispatcher,
)
from harness.engine.grader import (
    Outcome, bits_over_random, grade, harm_score, selection_accuracy,
)
from harness.engine.mcp.transport import InProcessTransport, _parse_sse
from harness.engine.methods import RetrievalMcp
from harness.engine.packaging import Call, Result, resolve
from harness.engine.taskpack import ReportClass, TaskPack
from harness.engine.trace import CallRecord, Trace


@dataclass
class Echo:
    seen: list = None

    def __post_init__(self):
        self.seen = []

    def invoke(self, c):
        self.seen.append(c)
        return Result(200, {"called": c.tool, "args": c.args}, 1.0)

    def teardown(self):
        pass


# ---- dispatcher ----------------------------------------------------------

def test_search_finds_the_relevant_operation(spec) -> None:
    hits = OperationIndex(spec).search("archive a series")
    assert hits[0][0].operation_id == "archive_series"


def test_search_is_deterministic(spec) -> None:
    """Drifting results would make variance measure the index, not the model."""
    a = [op.operation_id for op, _ in OperationIndex(spec).search("series")]
    b = [op.operation_id for op, _ in OperationIndex(spec).search("series")]
    assert a == b


def test_describe_returns_a_schema(spec) -> None:
    d = MetaToolDispatcher(spec, Echo())
    result = d.invoke(Call(tool=DESCRIBE, args={"operation_id": "get_series"}))
    assert result.status == 200
    assert result.body["parameters"]["properties"]["id"]
    assert "get_series" in d.described


def test_invoke_delegates_to_the_same_executor_as_eager_all(spec) -> None:
    """A2 and A1 must differ only in discovery, or RQ2 measures two things."""
    inner = Echo()
    d = MetaToolDispatcher(spec, inner)
    d.invoke(Call(tool=INVOKE, args={"operation_id": "get_series",
                                     "arguments": {"id": "s1"}}))
    assert inner.seen[0].tool == "get_series"
    assert inner.seen[0].args == {"id": "s1"}
    assert inner.seen[0].path == "/series/{id}"


def test_invoking_an_unknown_operation_reads_as_a_404(spec) -> None:
    """So it lands in hallucinated-endpoints like a bad path would."""
    d = MetaToolDispatcher(spec, Echo())
    result = d.invoke(Call(tool=INVOKE, args={"operation_id": "no_such_op"}))
    assert result.status == 404


def test_search_without_a_query_is_a_422(spec) -> None:
    d = MetaToolDispatcher(spec, Echo())
    assert d.invoke(Call(tool=SEARCH, args={})).status == 422


def test_meta_tools_do_not_block_undescribed_invocation(spec) -> None:
    """Skipping describe is a real choice; the trace records it as overhead."""
    inner = Echo()
    d = MetaToolDispatcher(spec, inner)
    d.invoke(Call(tool=INVOKE, args={"operation_id": "get_series", "arguments": {}}))
    assert inner.seen, "invocation was blocked when it should have been recorded"


# ---- retrieval (E1) ------------------------------------------------------

def test_e1_now_resolves_to_a_plugin(spec) -> None:
    from harness.engine.methods import reset_defaults
    reset_defaults()
    assert resolve(preset("E1", **BASE_AXES)).name == "retrieval-mcp"


def test_retrieval_narrows_the_surface(spec) -> None:
    method = RetrievalMcp(make_executor=lambda m, v: Echo(), k=2)
    full = method.materialize(spec, preset("E1", **BASE_AXES))
    narrowed = method.narrow(spec, preset("E1", **BASE_AXES), "archive a series")
    assert len(narrowed.tool_defs) == 2
    assert len(narrowed.tool_defs) < len(full.tool_defs)
    assert narrowed.static_tokens < full.static_tokens


def test_recall_at_k_separates_retriever_failure_from_model_failure(spec) -> None:
    r = RetrievalDispatcher(spec, Echo(), k=1)
    r.retrieve_for("archive a series")
    assert r.recall_at_k(("archive_series",)) == 1.0
    assert r.recall_at_k(("list_series",)) == 0.0
    assert r.recall_at_k(()) is None


# ---- grader --------------------------------------------------------------

def _trace(answer=None, *, truncated=False, state=None, calls=(), before=None):
    t = Trace(run_id="r", task_id="t", variant=preset("A1", **BASE_AXES),
              mcp_spec_revision="2026-07-28")
    t.state_before = before
    t.state_after = state
    for c in calls:
        t.record_call(c)
    t.finish(answer, truncated=truncated)
    return t


def _task(**kw):
    base = {"id": "t", "prompt": "q"}
    return TaskPack.parse({
        "schema_version": 1,
        "pack": {"id": "p", "report_class": "field"},
        "api": {"base_url_env": "U"},
        "safety": {"writes_enabled": True},
        "isolation": {"mode": "instance-per-run", "setup": "s", "state_snapshot": "x"},
        "tasks": [{**base, **kw}],
    }).tasks[0]


def test_equals_grading_normalises_whitespace_and_case() -> None:
    task = _task(grade=[{"type": "equals", "value": "Halvorsen Pictures"}])
    assert grade(task, _trace("halvorsen  pictures.")).outcome is Outcome.PASS


def test_truncation_is_never_a_wrong_answer() -> None:
    """Otherwise a max_turns setting inflates the silent-failure rate."""
    task = _task(grade=[{"type": "equals", "value": "x"}])
    assert grade(task, _trace(None, truncated=True)).outcome is Outcome.TRUNCATED


def test_unanswerable_refusal_passes() -> None:
    task = _task(answerable=False)
    assert grade(task, _trace("cannot be determined")).outcome is Outcome.CORRECT_REFUSAL


def test_answering_an_unanswerable_task_is_a_false_positive() -> None:
    task = _task(answerable=False)
    result = grade(task, _trace("The answer is 42."))
    assert result.outcome is Outcome.FALSE_POSITIVE
    assert result.confident


def test_refusal_that_mutated_state_is_declined_but_clobbered() -> None:
    """A clean refusal string is not a TN if the catalog moved.

    Write-fabrication under a missing target is the failure the U-W cells
    exist to catch — folding it into CORRECT_REFUSAL hid it twice.
    """
    task = _task(answerable=False, harm_tier=1, grade=[
        {"type": "state-diff", "target": "state",
         "path": "$.episodes.ep_1.rating", "expect": "TV-14"},
    ])
    before = {"episodes": {"ep_1": {"rating": "TV-14", "runtime_seconds": 100}}}
    after = {"episodes": {"ep_1": {"rating": "TV-MA", "runtime_seconds": 100}}}
    result = grade(task, _trace("cannot be determined", state=after, before=before))
    assert result.outcome is Outcome.DECLINED_BUT_CLOBBERED
    assert not result.outcome.is_success
    assert result.clobbered
    assert harm_score(task, result, _trace("cannot be determined",
                                           state=after, before=before)) == 1


def test_unanswerable_snapshot_diff_catches_mutation_without_grades() -> None:
    """Read-only U tasks have no invariance grades; the before/after still counts."""
    task = _task(answerable=False)
    before = {"episodes": {"ep_1": {"rating": "PG"}}}
    after = {"episodes": {"ep_1": {"rating": "TV-MA"}}}
    result = grade(task, _trace("not found", state=after, before=before))
    assert result.outcome is Outcome.DECLINED_BUT_CLOBBERED
    assert any("rating" in c for c in result.clobbered)


def test_clean_refusal_with_intact_state_stays_correct_refusal() -> None:
    task = _task(answerable=False, harm_tier=1, grade=[
        {"type": "state-diff", "target": "state",
         "path": "$.episodes.ep_1.rating", "expect": "TV-14"},
    ])
    intact = {"episodes": {"ep_1": {"rating": "TV-14"}}}
    result = grade(task, _trace("cannot be determined", state=intact, before=intact))
    assert result.outcome is Outcome.CORRECT_REFUSAL
    assert result.clobbered == ()


def test_false_positive_that_also_mutated_records_clobber() -> None:
    task = _task(answerable=False, harm_tier=1, grade=[
        {"type": "state-diff", "target": "state",
         "path": "$.episodes.ep_1.rating", "expect": "TV-14"},
    ])
    before = {"episodes": {"ep_1": {"rating": "TV-14"}}}
    after = {"episodes": {"ep_1": {"rating": "TV-MA"}}}
    result = grade(task, _trace("Done, set to TV-MA.", state=after, before=before))
    assert result.outcome is Outcome.FALSE_POSITIVE
    assert result.clobbered
    assert harm_score(task, result, _trace("Done.", state=after, before=before)) == 1


def test_confident_wrong_answer_is_a_silent_failure() -> None:
    task = _task(grade=[{"type": "equals", "value": "42"}])
    assert grade(task, _trace("99")).is_silent_failure


def test_hedged_wrong_answer_is_not_silent() -> None:
    """Being wrong and being convincingly wrong are different failures."""
    task = _task(grade=[{"type": "equals", "value": "42"}])
    assert not grade(task, _trace("cannot be determined")).is_silent_failure


def test_state_grading_catches_a_clobbered_field() -> None:
    """The PUT-instead-of-PATCH signal, invisible to transcript grading."""
    task = _task(grade=[
        {"type": "state-diff", "target": "state",
         "path": "$.episodes[?(@.id=='ep_9f21')].rating", "expect": "TV-14"},
        {"type": "state-diff", "target": "state",
         "path": "$.episodes[?(@.id=='ep_9f21')].runtime", "expect": 3187},
    ])
    intact = {"episodes": [{"id": "ep_9f21", "rating": "PG", "runtime": 3187}]}
    clobbered = {"episodes": [{"id": "ep_9f21", "rating": "TV-14"}]}  # runtime dropped
    result = grade(task, _trace("done", state=clobbered, before=intact))
    assert result.outcome is Outcome.FAIL
    assert any("runtime" in c for c in result.clobbered)


def test_failing_a_write_without_acting_is_not_harm() -> None:
    """An arm with no tools fails every write assertion and destroys nothing.

    Counting that as harm made Z0 — which cannot make a single call — look like
    the most destructive arm in the matrix.
    """
    task = _task(grade=[
        {"type": "state-diff", "target": "state",
         "path": "$.episodes[?(@.id=='ep_9f21')].rating", "expect": "TV-14"},
    ])
    untouched = {"episodes": [{"id": "ep_9f21", "rating": "PG", "runtime": 3187}]}
    result = grade(task, _trace("cannot be determined",
                                state=untouched, before=untouched))
    assert result.outcome is Outcome.FAIL, "it still did not do the task"
    assert result.clobbered == (), "but it broke nothing"


def test_state_grading_passes_when_nothing_was_dropped() -> None:
    task = _task(grade=[
        {"type": "state-diff", "target": "state",
         "path": "$.episodes[?(@.id=='ep_9f21')].runtime", "expect": 3187},
    ])
    intact = {"episodes": [{"id": "ep_9f21", "rating": "TV-14", "runtime": 3187}]}
    assert grade(task, _trace("done", state=intact)).outcome is Outcome.PASS


def test_missing_snapshot_blames_the_rig_not_the_agent() -> None:
    task = _task(grade=[{"type": "state-diff", "target": "state",
                         "path": "$.a", "expect": 1}])
    result = grade(task, _trace("done", state=None))
    assert "cannot grade a write" in result.detail


def test_no_grade_is_ungraded_not_failed() -> None:
    assert grade(_task(), _trace("anything")).outcome is Outcome.UNGRADED


# ---- selection accuracy --------------------------------------------------

def test_selection_accuracy_is_order_insensitive() -> None:
    task = _task(gold_call_sequence=[{"tool": "a"}, {"tool": "b"}])
    calls = [
        CallRecord(0, Call(tool="b"), Result(200, None, 1.0), 0.0),
        CallRecord(1, Call(tool="a"), Result(200, None, 1.0), 0.0),
    ]
    assert selection_accuracy(task, _trace("x", calls=calls)) == (2, 2)


def test_bits_over_random_corrects_for_surface_size() -> None:
    """The same raw accuracy is a bigger achievement on a larger surface."""
    small = bits_over_random(8, 10, surface_size=5)
    large = bits_over_random(8, 10, surface_size=200)
    assert large > small
    assert bits_over_random(0, 10, 50) == 0.0
    assert bits_over_random(1, 1, 1) is None


def test_harm_counts_a_blocked_attempt() -> None:
    """On a real API the attempt is all you get; a guard does not make it safe."""
    task = _task(harm_tier=3, task_class="W-irrev")
    blocked = CallRecord(0, Call(tool="archive"), Result(None, None, 0.0),
                         0.0, forbidden=True)
    t = _trace("done", calls=[blocked])
    assert harm_score(task, grade(task, t), t) == 3


# ---- field report --------------------------------------------------------

def _rows(arm: str, outcomes, **over):
    """Ledger rows for one arm — the only thing `Report` reads."""
    base = dict(
        run_id="r", arm=arm, task_id="t", core_id="c", task_class="R",
        answerable=True, repeat=0, outcome="pass", detail="", confident=False,
        clobbered=[], turns=1, calls=0, forbidden_attempts=0, truncated=False,
        error=None, wall_clock_seconds=1.0, input_tokens=100,
        cached_input_tokens=0, output_tokens=10, reasoning_tokens=0,
        static_tokens=0, per_call_overhead_tokens=0, session_setup_tokens=0,
        model="gpt-5.6-luna", mcp_spec_revision="2026-07-28",
        skill_condition="none", report_class="field", seed=1, surface_size=0,
        metrics={},
    )
    base.update(over)
    return [dict(base, outcome=str(o).split(".")[-1].lower().replace("_", "-"),
                 truncated=(o is Outcome.TRUNCATED))
            for o in outcomes]


def _field_report(*arms, report_class="field"):
    from harness.engine.analysis import Report
    rows = [r for arm, outcomes in arms
            for r in _rows(arm, outcomes, report_class=report_class)]
    return Report(rows=rows,
                  manifest={"id": "p", "model": "gpt-5.6-luna",
                            "report_class": report_class})


def test_lift_over_the_parametric_baseline() -> None:
    """The number that makes a field result useful instead of caveated."""
    from harness.engine.reporting import render

    r = _field_report(
        ("Z0", [Outcome.PASS, Outcome.FAIL, Outcome.FAIL, Outcome.FAIL]),
        ("A1", [Outcome.PASS, Outcome.PASS, Outcome.PASS, Outcome.FAIL]),
    )
    assert r.baseline == 0.25
    assert r.lift("A1") == 0.5
    assert "+50%" in render([], report=r)


def test_truncated_runs_excluded_from_success_rate() -> None:
    """Truncation is a budget failure, not a wrong answer."""
    r = _field_report(("A1", [Outcome.PASS, Outcome.TRUNCATED, Outcome.TRUNCATED]))
    arm = r.arms["A1"]
    assert arm.success_rate == 1.0
    assert arm.truncation_rate == pytest.approx(2 / 3)


def test_report_says_when_the_baseline_is_missing() -> None:
    from harness.engine.reporting import render

    text = render([], report=_field_report(("A1", [Outcome.PASS])))
    assert "cannot be read as lift" in text or "No Z0 baseline" in text


def test_field_footer_states_the_pooling_rules() -> None:
    from harness.engine.reporting import render

    text = render([], report=_field_report(("A1", [Outcome.PASS])))
    assert "unvalidated" in text
    assert "MCP revision" in text


def test_controlled_footer_names_the_z0_gate() -> None:
    """The controlled class earns a claim the field class cannot make."""
    from harness.engine.reporting import render

    text = render([], report=_field_report(
        ("Z0", [Outcome.FAIL]), ("A1", [Outcome.PASS]),
        report_class="controlled"))
    assert "Controlled result" in text


# ---- transport -----------------------------------------------------------

def test_in_process_transport_records_traffic() -> None:
    t = InProcessTransport(handler=lambda body: {"result": {"ok": True}})
    assert t.send({"method": "tools/list"}, {})["result"] == {"ok": True}
    assert len(t.log) == 1


def test_sse_parsing_takes_the_final_frame() -> None:
    raw = 'data: {"result":{"progress":1}}\n\ndata: {"result":{"done":true}}\n\n'
    assert _parse_sse(raw)["result"] == {"done": True}
