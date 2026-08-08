"""End-to-end: the loop, executors, and gold-free metrics, with no network."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from conftest import BASE_AXES, ScriptedProvider, call, code, say

from harness.engine.axes import ErrorDetail, Invocation, preset
from harness.engine.compute import compute, report_footer
from harness.engine.executors import GuardedExecutor
from harness.engine.generate import shape_error
from harness.engine.loop import AgentRunner
from harness.engine.metrics import Validation
from harness.engine.packaging import Call, Materials, Provenance, Result
from harness.engine.provider import ProviderConfig

CONFIG = ProviderConfig(model="gpt-5-mini", reasoning_effort="low",
                        temperature=0.0, max_turns=6, caching=False)


@dataclass
class FakeMethod:
    """A packaging method backed by a canned executor."""

    name: str
    results: dict[str, Result]
    tools: tuple = ()

    def supports(self, v) -> bool:
        return True

    def materialize(self, spec, v) -> Materials:
        return Materials(
            context_blocks=(), tool_defs=self.tools, sandbox_files={},
            static_tokens=1234,
            provenance=Provenance(generator="fake", spec_revision="1"),
        )

    def executor(self, materials):
        return _CannedExecutor(self.results)

    def account(self, trace):
        return trace.cost


@dataclass
class _CannedExecutor:
    results: dict

    def invoke(self, c: Call) -> Result:
        key = c.tool or c.path or "raw"
        return self.results.get(key, Result(404, None, 1.0, error="no such operation"))

    def teardown(self) -> None:
        pass


def runner(spec, script, results, *, preset_name="A1", **kw):
    return AgentRunner(
        provider=ScriptedProvider(script),
        method=FakeMethod("fake", results),
        spec=spec,
        variant=preset(preset_name, **BASE_AXES),
        config=CONFIG,
        **kw,
    )


# ---- the loop ------------------------------------------------------------

def test_loop_calls_a_tool_then_answers(spec) -> None:
    r = runner(spec,
               [call("get_series", id="s1"), say("FINAL ANSWER: 42")],
               {"get_series": Result(200, {"runtime": 42}, 5.0)})
    trace = r.run("t1", "How long is series s1?")

    assert trace.final_answer == "42"
    assert not trace.truncated
    assert len(trace.calls) == 1
    assert trace.calls[0].result.status == 200


def test_static_tokens_recorded_before_turn_one(spec) -> None:
    trace = runner(spec, [say("FINAL ANSWER: x")], {}).run("t", "q")
    assert trace.cost.static_tokens == 1234


def test_running_out_of_turns_is_truncation_not_a_wrong_answer(spec) -> None:
    """Folding the two together would inflate the silent-failure rate."""
    script = [call("get_series", id="s1")] * 10
    trace = runner(spec, script, {"get_series": Result(200, {}, 1.0)}).run("t", "q")
    assert trace.truncated
    assert trace.final_answer is None


def test_unanswerable_is_expressible(spec) -> None:
    trace = runner(spec, [say("FINAL ANSWER: cannot be determined")], {}).run("t", "q")
    assert trace.final_answer == "cannot be determined"


def test_provider_exception_becomes_a_data_point(spec) -> None:
    class Exploding(ScriptedProvider):
        def submit(self, messages, tools, config):
            raise RuntimeError("provider is down")

    r = runner(spec, [], {})
    r.provider = Exploding([])
    trace = r.run("t", "q")
    assert "provider is down" in (trace.error or "")
    assert trace.ended_at is not None


def test_shell_arm_extracts_a_fenced_block(spec) -> None:
    r = runner(spec, [code("curl $BASE_URL/series"), say("FINAL ANSWER: ok")],
               {"raw": Result(0, {"stdout": "[]"}, 3.0)}, preset_name="C1")
    trace = r.run("t", "q")
    assert trace.calls and trace.calls[0].call.raw.startswith("curl")


def test_hallucinated_endpoint_is_detected_against_the_spec(spec) -> None:
    r = runner(spec, [say("x")], {})
    trace = r.run("t", "q")
    assert spec.defines("GET", "/series/abc")
    assert not spec.defines("GET", "/nonexistent")


def test_trace_records_mcp_revision(spec) -> None:
    """Without this, a pre- and post-2026-07-28 run cannot be told apart later."""
    trace = runner(spec, [say("FINAL ANSWER: x")], {}).run("t", "q")
    assert trace.mcp_spec_revision == "2026-07-28"


def test_trace_persists_to_disk(spec, tmp_path) -> None:
    r = runner(spec, [call("get_series", id="s1"), say("FINAL ANSWER: 42")],
               {"get_series": Result(200, {"runtime": 42}, 5.0)},
               trace_dir=str(tmp_path))
    trace = r.run("t1", "q")
    written = tmp_path / f"{trace.run_id}.json.gz"
    assert written.exists()
    # Uncompressed is not merely a different name — a matrix that writes plain
    # JSON needs 7x the disk and the preflight refuses to start it.
    assert not (tmp_path / f"{trace.run_id}.json").exists()

    import gzip
    import json
    data = json.loads(gzip.decompress(written.read_bytes()))
    assert data["calls"][0]["call"]["tool"] == "get_series"
    assert data["mcp_spec_revision"] == "2026-07-28"


def test_trace_gzip_header_carries_no_timestamp(spec, tmp_path) -> None:
    """The container must not add variance the payload does not have.

    Traces are not byte-reproducible — they record real latencies — but gzip
    stamps mtime into its header by default, which is a difference between two
    copies of one trace that says nothing about the run. Bytes 4-8 are that
    field; a published corpus should not carry it.
    """
    r = runner(spec, [call("get_series", id="s1"), say("FINAL ANSWER: 42")],
               {"get_series": Result(200, {"runtime": 42}, 5.0)},
               trace_dir=str(tmp_path))
    trace = r.run("t1", "q")
    raw = (tmp_path / f"{trace.run_id}.json.gz").read_bytes()
    assert raw[4:8] == b"\x00\x00\x00\x00"


# ---- forbidden calls -----------------------------------------------------

def test_forbidden_call_is_blocked_but_recorded(spec) -> None:
    """The attempt is the harm signal where state cannot be diffed."""
    r = runner(spec,
               [call("archive_series", id="s1"), say("FINAL ANSWER: done")],
               {"archive_series": Result(200, {}, 1.0)},
               forbidden_calls=("archive_series",))
    trace = r.run("t", "archive it")

    assert trace.calls[0].forbidden
    assert trace.calls[0].result.status is None
    assert "forbidden_calls" in (trace.calls[0].result.error or "")


def test_forbidden_patterns_match_http_targets() -> None:
    g = GuardedExecutor(inner=_CannedExecutor({}), forbidden=("POST /series/*:archive",))
    blocked = g.invoke(Call(method="POST", path="/series/s1:archive"))
    assert blocked.error and "blocked" in blocked.error
    allowed = g.invoke(Call(method="GET", path="/series/s1"))
    assert allowed.error != blocked.error


# ---- gold-free metrics ---------------------------------------------------

def test_metrics_computed_without_any_gold(spec) -> None:
    r = runner(spec,
               [call("list_series", studio="bad"),
                call("list_series", studio="s1"),
                say("FINAL ANSWER: halvorsen")],
               {"list_series": Result(200, {"items": ["halvorsen"]}, 2.0)})
    trace = r.run("t", "q")
    m = compute(trace)

    assert m["turns"].value == 3
    assert m["static_context_tokens"].value == 1234
    assert m["argument_validity"].value == 1.0


def test_argument_validity_counts_4xx(spec) -> None:
    r = runner(spec,
               [call("list_series", studio="bad"), say("FINAL ANSWER: x")],
               {"list_series": Result(422, {"code": "422"}, 1.0)})
    m = compute(r.run("t", "q"))
    assert m["argument_validity"].value == 0.0


def test_error_recovery_rate_sees_a_correction(spec) -> None:
    """The mechanism by which better errors could beat a skill."""
    results = iter([Result(422, {"code": "422"}, 1.0), Result(200, {"ok": True}, 1.0)])

    @dataclass
    class Sequenced:
        def invoke(self, c): return next(results)
        def teardown(self): pass

    r = runner(spec, [call("list_series", studio="bad"),
                      call("list_series", studio="good"),
                      say("FINAL ANSWER: ok")], {})
    r.method.executor = lambda materials: Sequenced()  # type: ignore[method-assign]
    m = compute(r.run("t", "q"))
    assert m["error_recovery_rate"].value == 1.0


def test_unavailable_metrics_say_why(spec) -> None:
    """n/a and zero are different, and a report must not merge them."""
    trace = runner(spec, [say("FINAL ANSWER: x")], {}).run("t", "q")
    m = compute(trace)
    assert m["argument_validity"].value is None
    assert "no call returned a status" in (m["argument_validity"].unavailable_reason or "")
    assert m["error_recovery_rate"].value is None


def test_every_metric_is_labelled_unvalidated(spec) -> None:
    trace = runner(spec, [say("FINAL ANSWER: x")], {}).run("t", "q")
    m = compute(trace)
    real = [v for k, v in m.items() if not k.startswith("_")]
    assert all(v.validation is Validation.UNVALIDATED for v in real)
    assert "unvalidated" in report_footer(m)


def test_redundant_calls_detected(spec) -> None:
    r = runner(spec, [call("get_series", id="s1"), call("get_series", id="s1"),
                      say("FINAL ANSWER: x")],
               {"get_series": Result(200, {"a": 1}, 1.0)})
    m = compute(r.run("t", "q"))
    assert m["redundant_calls"].value == 1


# ---- error shaping (G4) --------------------------------------------------

@pytest.mark.parametrize("detail,expect_field,expect_detail", [
    (ErrorDetail.TERSE, False, False),
    (ErrorDetail.FIELD_SCOPED, True, False),
    (ErrorDetail.FIELD_SCOPED_REMEDY, True, True),
])
def test_error_detail_axis_changes_what_the_agent_sees(detail, expect_field, expect_detail):
    err = shape_error(422, "created_after", "RFC3339", "2024-13-01", detail)
    assert ("created_after" in err["message"]) is expect_field
    assert ("detail" in err) is expect_detail
    if expect_detail:
        assert "RFC3339" in err["detail"] and "2024-13-01" in err["detail"]
