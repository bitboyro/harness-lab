"""The transcript renderer: what the model saw, without saying it twice."""

from __future__ import annotations

import json

from conftest import BASE_AXES

from harness.engine.axes import preset
from harness.engine.packaging import Call, Result
from harness.engine.provider import Usage
from harness.engine.trace import CallRecord, Trace, Turn
from harness.engine.transcript import render, render_turn


def _trace(**kw) -> Trace:
    return Trace(run_id="r1", task_id="t1",
                 variant=preset("A1", **BASE_AXES),
                 mcp_spec_revision="2026-07-28", **kw)


def _turn(index, messages, text=None, tokens=(100, 10)):
    return Turn(index=index, messages_in=list(messages), assistant_text=text,
                usage=Usage(tokens[0], 0, tokens[1], 0), stop_reason="stop",
                latency_ms=1200.0)


def _call(turn, tool, status=200, body="ok", forbidden=False):
    return CallRecord(turn=turn, call=Call(tool=tool, args={"id": "x"}),
                      result=Result(status, body, 42.0), started_at=0.0,
                      forbidden=forbidden)


# ---- the cumulative-messages problem --------------------------------------

def test_a_turn_shows_only_what_is_new() -> None:
    """`messages_in` is cumulative; rendering it whole repeats the prompt."""
    t = _trace()
    first = [{"role": "system", "content": "sys"},
             {"role": "user", "content": "the question"}]
    t.record_turn(_turn(0, first))
    t.record_turn(_turn(1, first + [{"role": "user", "content": "later"}]))

    second = render_turn(t, 1)
    assert "later" in second
    assert "the question" not in second


def test_tool_results_are_not_printed_twice() -> None:
    """A result is shown under the call that produced it, and nowhere else.

    The loop appends one result message per call, so it reappears at the head
    of the next turn's slice — the same body, one turn later.
    """
    t = _trace()
    first = [{"role": "user", "content": "q"}]
    t.record_turn(_turn(0, first))
    t.record_call(_call(0, "get_thing", body="THE-PAYLOAD"))
    t.record_turn(_turn(1, first + [{"role": "user", "content": "THE-PAYLOAD"}]))

    assert render_turn(t, 0).count("THE-PAYLOAD") == 1
    assert "THE-PAYLOAD" not in render_turn(t, 1)


def test_turn_zero_summarises_packaging_material() -> None:
    """Its size is the measurement; its content is not worth 2,000 lines."""
    t = _trace()
    t.record_turn(_turn(0, [{"role": "system", "content": "x" * 5_000},
                            {"role": "user", "content": "q"}]))
    out = render_turn(t, 0)
    assert "5,000 chars of packaging material" in out
    assert "xxxxxxxxxx" not in out
    assert "q" in out


# ---- calls -----------------------------------------------------------------

def test_a_call_shows_its_arguments_and_result() -> None:
    t = _trace()
    t.record_turn(_turn(0, [{"role": "user", "content": "q"}]))
    t.record_call(_call(0, "get_thing"))
    out = render_turn(t, 0)
    assert "get_thing" in out and '"id": "x"' in out
    assert "← 200" in out


def test_a_blocked_call_is_marked_as_harm() -> None:
    """On a live API the attempt is the whole signal — state cannot be diffed."""
    t = _trace()
    t.record_turn(_turn(0, [{"role": "user", "content": "q"}]))
    t.record_call(_call(0, "delete_everything", forbidden=True))
    out = render_turn(t, 0)
    assert "harm" in out and "BLOCKED" in out


def test_showcase_unwraps_mcp_envelope_and_lists_items() -> None:
    """Live --stream must not dump the MCP wrapper the agent already peeled."""
    body = {
        "isError": False,
        "status": 200,
        "content": [{
            "type": "text",
            "text": json.dumps({
                "items": [
                    {"id": "ep_1", "title": "A", "runtime_seconds": 10},
                    {"id": "ep_2", "title": "B", "runtime_seconds": 99},
                ],
                "total": 2,
            }),
        }],
        "structuredContent": {
            "items": [
                {"id": "ep_1", "title": "A", "runtime_seconds": 10},
                {"id": "ep_2", "title": "B", "runtime_seconds": 99},
            ],
            "total": 2,
        },
    }
    t = _trace()
    t.record_turn(_turn(0, [
        {"role": "system", "content": "Answer the task using the tools available."},
        {"role": "user", "content": "How long is the longest episode?"},
    ]))
    t.record_call(CallRecord(
        turn=0,
        call=Call(tool="list_episodes", args={"season_id": "sn_1", "limit": 100}),
        result=Result(200, body, 3.0),
        started_at=0.0,
    ))
    out = render_turn(t, 0, style="showcase")
    assert "isError" not in out
    assert "structuredContent" not in out
    assert "list_episodes" in out
    assert "season_id" in out and "sn_1" in out
    assert "2 items" in out
    assert "ep_2" in out and "runtime_seconds=99" in out
    assert "task preamble" in out
    assert "How long is the longest episode?" in out


def test_showcase_highlights_final_answer() -> None:
    t = _trace()
    t.record_turn(_turn(0, [{"role": "user", "content": "q"}],
                         text="thinking…\nFINAL ANSWER: 3466 seconds"))
    out = render_turn(t, 0, style="showcase")
    assert "★ FINAL ANSWER: 3466 seconds" in out


def test_showcase_verbose_expands_collapsed_sections() -> None:
    preamble = "Answer the task using the tools available." + (" x" * 200)
    code = "\n".join(f"line {i}" for i in range(8))
    t = _trace()
    t.record_turn(_turn(0, [
        {"role": "system", "content": "x" * 5_000},
        {"role": "system", "content": preamble},
        {"role": "user", "content": "q"},
    ]))
    t.record_call(CallRecord(
        turn=0,
        call=Call(tool=None, raw=code),
        result=Result(200, "ok", 1.0),
        started_at=0.0,
    ))
    compact = render(t, style="showcase")
    assert "task preamble" in compact
    assert "more lines" in compact
    assert "xxxxx" not in compact

    verbose = render(t, style="showcase", verbose=True)
    assert "task preamble" not in verbose
    assert "Answer the task using the tools" in verbose
    assert "5,000 chars of packaging material" not in verbose
    assert "xxxxx" in verbose
    assert "line 7" in verbose
    assert "more lines" not in verbose
    # Preamble is hoisted above the first turn header.
    assert verbose.index("Answer the task") < verbose.index("── turn 0")


# ---- outcomes --------------------------------------------------------------

def test_truncation_reads_as_budget_not_wrong_answer() -> None:
    t = _trace()
    t.record_turn(_turn(0, [{"role": "user", "content": "q"}]))
    t.finish(None, truncated=True)
    assert "TRUNCATED" in render(t)
    assert "not a wrong answer" in render(t)


def test_an_infra_error_names_its_kind() -> None:
    """So a reader does not take a dead key for a packaging failure."""
    t = _trace()
    t.record_turn(_turn(0, [{"role": "user", "content": "q"}]))
    t.error = "AuthenticationError: 401"
    t.error_kind = "auth"
    out = render(t)
    assert "ERROR" in out and "auth" in out


def test_the_footer_counts_turns_and_calls() -> None:
    t = _trace()
    t.record_turn(_turn(0, [{"role": "user", "content": "q"}]))
    t.record_call(_call(0, "one"))
    t.finish("42")
    footer = render(t).splitlines()[-1]
    assert "42" in footer and "1 turn," in footer and "1 call)" in footer


def test_replay_matches_the_live_render(tmp_path) -> None:
    """A transcript must not mean two things depending on when it was read.

    The live path renders dataclasses; replay renders JSON off disk. They are
    separate code paths, so nothing but a test keeps them producing the same
    text.
    """
    from harness.engine.transcript import load, render_stored

    t = _trace()
    t.record_turn(_turn(0, [{"role": "system", "content": "sys"},
                            {"role": "user", "content": "q"}]))
    t.record_call(_call(0, "get_thing"))
    t.record_turn(_turn(1, [{"role": "system", "content": "sys"},
                            {"role": "user", "content": "q"},
                            {"role": "user", "content": "ok"}],
                        text="FINAL ANSWER: 42"))
    t.finish("42")

    live = render(t)
    path = t.write(tmp_path)
    assert render_stored(load(str(path))) == live
