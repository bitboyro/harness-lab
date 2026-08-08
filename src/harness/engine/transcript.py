"""What the model actually saw and said, turn by turn.

The trace already records everything — every message sent, every completion,
every call with its arguments and its result. What was missing was any way to
read it: the only view of a run was one summary line per completed run, and a
900 KB JSON file nobody opens.

Two things follow from how the trace stores messages. `Turn.messages_in` is
*cumulative* — a snapshot of the whole conversation as sent on that turn — so
rendering every turn in full would repeat the entire prompt N times. The
renderer therefore emits only the slice that is new since the previous turn,
which is also what makes the same code usable live: a turn's slice is complete
the moment the turn is recorded, and never changes afterwards.

The second is that turn 0 carries the packaging materials, which for an
eager-all MCP arm is the entire tool surface. Those get summarised, not dumped —
their *size* is the finding (it is a reported metric), their content is not.

Contract: archive/reference/experiment-design.md#what-is-persisted
"""

from __future__ import annotations

import json
from typing import Any

from .trace import CallRecord, Trace

#: Long message bodies are elided to this many characters. A transcript is for
#: reading; the trace on disk stays authoritative for anything that needs the
#: full text.
_ELIDE = 600

_ROLE_WIDTH = 9


def _clip(text: str, limit: int = _ELIDE) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… (+{len(text) - limit:,} chars)"


def _body(value: Any, limit: int = _ELIDE) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _clip(value, limit)
    try:
        return _clip(json.dumps(value, default=str), limit)
    except (TypeError, ValueError):
        return _clip(str(value), limit)


def _indent(text: str, label: str) -> str:
    """A labelled block whose continuation lines line up under the first."""
    pad = " " * (_ROLE_WIDTH + 1)
    lines = text.splitlines() or [""]
    head = f"  {label:<{_ROLE_WIDTH}} {lines[0]}"
    return "\n".join([head] + [pad + "  " + line for line in lines[1:]])


def _message(msg: dict[str, Any], *, summarise: bool = False) -> str:
    role = str(msg.get("role", "?"))
    content = msg.get("content")
    text = content if isinstance(content, str) else _body(content)
    if summarise and len(text) > _ELIDE:
        # Static packaging material. Its size is the measurement; reprinting a
        # tool catalogue on every run helps nobody read the run.
        return _indent(f"[{len(text):,} chars of packaging material]", role)
    return _indent(_clip(text), role)


def _call(record: CallRecord) -> str:
    c, r = record.call, record.result
    if c.raw:
        target = _clip(c.raw, 200)
    elif c.tool:
        target = f"{c.tool}({_body(c.args, 200)})" if c.args else f"{c.tool}()"
    else:
        target = f"{c.method or '?'} {c.path or '?'}"

    lines = [_indent(target, "→ call")]
    if record.forbidden:
        # On a live API an *attempt* is the whole harm signal, because the
        # alternative evidence — the state change — is not ours to inspect.
        lines.append(_indent("BLOCKED — forbidden by the pack", "✖ harm"))
        return "\n".join(lines)

    status = "err" if r.error else (str(r.status) if r.status is not None else "—")
    detail = r.error or _body(r.body)
    lines.append(_indent(f"{detail}  ({r.latency_ms:.0f}ms)", f"← {status}"))
    return "\n".join(lines)


def render_turn(trace: Trace, index: int) -> str:
    """One turn: what was newly said to the model, and what came back."""
    turn = trace.turns[index]
    previous = len(trace.turns[index - 1].messages_in) if index else 0
    new = turn.messages_in[previous:]

    # The loop appends exactly one result message per call, so the head of this
    # turn's new slice is the previous turn's results coming back. They were
    # already shown as `← status` lines under the calls that produced them;
    # printing the same bodies again doubles the length of every transcript and
    # buries the part a reader is looking for.
    echoed = sum(1 for c in trace.calls if c.turn == index - 1) if index else 0
    new = new[echoed:]

    usage = turn.usage
    head = (f"  ── turn {turn.index}"
            f"   {usage.input_tokens:,} in"
            f" · {usage.output_tokens:,} out"
            f" · {turn.latency_ms / 1000:.1f}s")

    out = [head]
    out += [_message(m, summarise=(index == 0)) for m in new]
    if turn.assistant_text:
        out.append(_indent(_clip(turn.assistant_text), "assistant"))
    out += [_call(c) for c in trace.calls if c.turn == index]
    return "\n".join(out)


def _label(variant: Any) -> str:
    """The arm this run was, live or replayed.

    Both paths read `preset` off the variant — a live `Variant` carries it as a
    field and the stored JSON keeps it — so the two renderers cannot disagree
    about what a run was. They did, until a round-trip test said so.
    """
    if isinstance(variant, dict):
        return str(variant.get("preset") or "?")
    return str(getattr(variant, "preset", None) or "?")


def render(trace: Trace, *, since: int = 0, header: bool = True) -> str:
    """The whole exchange, or everything from turn `since` onward."""
    out: list[str] = []
    if header:
        out.append(f"┌─ {trace.run_id}   task={trace.task_id}"
                   f"   arm={_label(trace.variant)}")

    out += [render_turn(trace, i) for i in range(since, len(trace.turns))]

    if header:
        out.append(_footer(trace))
    return "\n".join(out)


def _footer(trace: Trace) -> str:
    if trace.error:
        # An infra death measured nothing about this arm; say which it was so a
        # reader does not take it for a packaging failure.
        kind = f" [{trace.error_kind}]" if trace.error_kind else ""
        return f"└─ ERROR{kind}: {_clip(trace.error, 200)}"
    if trace.truncated:
        return (f"└─ TRUNCATED after {len(trace.turns)} turns — out of budget, "
                f"not a wrong answer")
    answer = _clip(trace.final_answer or "(none)", 200)
    turns, calls = len(trace.turns), len(trace.calls)
    return (f"└─ answer: {answer}"
            f"   ({turns} turn{'s' * (turns != 1)}, "
            f"{calls} call{'s' * (calls != 1)})")


def load(path: str) -> dict[str, Any]:
    """A trace file as stored, compressed or not.

    Traces land as `.json.gz` — they are ~87% gzip, and a full matrix is
    hundreds of megabytes uncompressed. Plain `.json` is still accepted because
    a trace pulled out of a corpus for inspection usually has been.
    """
    import gzip

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:  # type: ignore[operator]
        return json.load(fh)


def render_stored(data: dict[str, Any]) -> str:
    """Render a trace read back from disk.

    Traces are persisted as plain JSON rather than pickled dataclasses, so the
    replay path cannot reuse `render` directly — but it must produce the same
    text, or a transcript would mean two different things depending on whether
    the run was live.
    """
    trace = _rehydrate(data)
    return render(trace)


def _rehydrate(data: dict[str, Any]) -> Trace:
    """Rebuild just enough of a Trace for the renderer.

    Deliberately partial: the renderer reads turns, calls, and the outcome
    fields, and reconstructing variants and cost breakdowns to print a heading
    would couple replay to every future schema change.
    """
    from types import SimpleNamespace

    from .packaging import Call, Result

    turns = [
        SimpleNamespace(
            index=t.get("index", i),
            messages_in=t.get("messages_in", []),
            assistant_text=t.get("assistant_text"),
            usage=SimpleNamespace(
                input_tokens=(t.get("usage") or {}).get("input_tokens", 0),
                output_tokens=(t.get("usage") or {}).get("output_tokens", 0),
            ),
            latency_ms=t.get("latency_ms", 0.0),
        )
        for i, t in enumerate(data.get("turns", []))
    ]
    calls = [
        SimpleNamespace(
            turn=c.get("turn", 0),
            call=Call(**{k: v for k, v in (c.get("call") or {}).items()
                         if k in {"tool", "method", "path", "args", "raw"}}),
            result=Result(**{k: v for k, v in (c.get("result") or {}).items()
                             if k in {"status", "body", "latency_ms", "error"}}),
            forbidden=c.get("forbidden", False),
        )
        for c in data.get("calls", [])
    ]
    return SimpleNamespace(  # type: ignore[return-value]
        run_id=data.get("run_id", "?"),
        task_id=data.get("task_id", "?"),
        variant=data.get("variant") or {},
        turns=turns,
        calls=calls,
        final_answer=data.get("final_answer"),
        truncated=data.get("truncated", False),
        error=data.get("error"),
        error_kind=data.get("error_kind"),
    )
