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

Two styles share that logic:

- ``plain`` — compact labelled lines; the default for ``harness transcript``
  and the shape the tests lock.
- ``showcase`` — what ``--stream`` prints: MCP envelopes unwrapped, arguments
  and payloads shaped for a human watching a pane, preamble collapsed, the
  FINAL ANSWER line called out. Same facts, less noise.

Contract: archive/reference/experiment-design.md#what-is-persisted
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from .trace import CallRecord, Trace

#: Long message bodies are elided to this many characters. A transcript is for
#: reading; the trace on disk stays authoritative for anything that needs the
#: full text.
_ELIDE = 600

#: Showcase keeps individual pretty-printed blocks shorter than this so a
#: narrow tmux pane stays scannable.
_SHOWCASE_CHARS = 720
_SHOWCASE_LIST = 6

_ROLE_WIDTH = 9

_PREAMBLE_HINT = "Answer the task using the tools"


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


def _parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "{[":
        return value
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


def _unwrap_mcp(body: Any) -> Any:
    """Pull the useful payload out of an MCP tool-result envelope.

    Live MCP returns ``{isError, status, content:[{type,text}], structuredContent}``.
    Dumping that wrapper is what made streamed turns unreadable — the answer the
    agent used is either ``structuredContent`` or the JSON inside ``content[0].text``.
    """
    body = _parse_jsonish(body)
    if not isinstance(body, dict):
        return body

    structured = body.get("structuredContent")
    if structured not in (None, {}, []):
        return structured

    content = body.get("content")
    if isinstance(content, list) and content:
        texts: list[Any] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if text is None:
                continue
            texts.append(_parse_jsonish(text))
        if len(texts) == 1:
            return texts[0]
        if texts:
            return texts

    # Drop the envelope keys when that is all the shape we have.
    if "isError" in body and "status" in body:
        rest = {k: v for k, v in body.items()
                if k not in {"isError", "status", "content", "structuredContent"}}
        if rest:
            return rest
    return body


def _fmt_scalar(value: Any) -> str:
    if isinstance(value, str):
        return value if len(value) <= 80 else _clip(value, 80)
    if isinstance(value, (int, float, bool)) or value is None:
        return json.dumps(value)
    return _clip(json.dumps(value, default=str), 80)


def _fmt_mapping(data: dict[str, Any], *, indent: str = "    ") -> list[str]:
    """Key/value lines — easier to scan in a pane than a JSON blob."""
    if not data:
        return [f"{indent}{{}}"]
    width = min(18, max((len(str(k)) for k in data), default=1))
    lines: list[str] = []
    for key, value in data.items():
        key_s = str(key)
        if isinstance(value, dict) and value and len(json.dumps(value, default=str)) > 60:
            lines.append(f"{indent}{key_s}:")
            lines.extend(_fmt_mapping(value, indent=indent + "  ")[:12])
            continue
        if isinstance(value, list) and value and not isinstance(value[0], (str, int, float, bool)):
            lines.append(f"{indent}{key_s}:  [{len(value)} items]")
            continue
        lines.append(f"{indent}{key_s:<{width}}  {_fmt_scalar(value)}")
    return lines


def _item_preview(item: Any) -> str:
    if not isinstance(item, dict):
        return _fmt_scalar(item)
    # Prefer the fields a reader is usually chasing in this catalog API.
    bits: list[str] = []
    for key in ("id", "name", "title", "number", "runtime_seconds",
                "rating", "status", "archived", "genre", "founded"):
        if key in item:
            bits.append(f"{key}={_fmt_scalar(item[key])}")
    if not bits:
        for key, value in list(item.items())[:3]:
            bits.append(f"{key}={_fmt_scalar(value)}")
    return "  ".join(bits)


def _fmt_payload(value: Any, *, limit: int = _SHOWCASE_CHARS) -> list[str]:
    """A result or argument body shaped for a human, not for a log shipper."""
    value = _unwrap_mcp(value)
    if value is None or value == "":
        return ["    (empty)"]
    if isinstance(value, str):
        return [f"    {line}" for line in _clip(value, limit).splitlines() or [""]]

    if isinstance(value, dict) and isinstance(value.get("items"), list):
        items = value["items"]
        head = [f"    {len(items)} item{'s' * (len(items) != 1)}"
                + (f" · total={value['total']}" if "total" in value else "")]
        show = items[:_SHOWCASE_LIST]
        for item in show:
            head.append(f"      · {_item_preview(item)}")
        if len(items) > len(show):
            head.append(f"      · … {len(items) - len(show)} more")
        extras = {k: v for k, v in value.items() if k not in {"items", "total"}}
        if extras:
            head.extend(_fmt_mapping(extras)[:6])
        return head

    if isinstance(value, dict):
        return _fmt_mapping(value)

    if isinstance(value, list):
        if not value:
            return ["    []"]
        lines = [f"    [{len(value)} items]"]
        for item in value[:_SHOWCASE_LIST]:
            lines.append(f"      · {_item_preview(item)}")
        if len(value) > _SHOWCASE_LIST:
            lines.append(f"      · … {len(value) - _SHOWCASE_LIST} more")
        return lines

    return [f"    {_clip(json.dumps(value, default=str), limit)}"]


class _Color:
    """ANSI only when the destination is a real terminal (Ghostty/tmux count)."""

    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def wrap(self, code: str, text: str) -> str:
        if not self.on:
            return text
        return f"\033[{code}m{text}\033[0m"

    def dim(self, t: str) -> str: return self.wrap("2", t)
    def bold(self, t: str) -> str: return self.wrap("1", t)
    def cyan(self, t: str) -> str: return self.wrap("36", t)
    def green(self, t: str) -> str: return self.wrap("32", t)
    def yellow(self, t: str) -> str: return self.wrap("33", t)
    def red(self, t: str) -> str: return self.wrap("31", t)
    def magenta(self, t: str) -> str: return self.wrap("35", t)


def _color_for(stream: Any | None = None) -> _Color:
    out = stream if stream is not None else sys.stdout
    return _Color(bool(getattr(out, "isatty", lambda: False)()))


# ---- plain (default / transcript replay) -----------------------------------

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


# ---- showcase (live --stream) ----------------------------------------------

def _showcase_message(msg: dict[str, Any], *, summarise: bool = False,
                      verbose: bool = False,
                      color: _Color) -> str | None:
    role = str(msg.get("role", "?"))
    content = msg.get("content")
    text = content if isinstance(content, str) else _body(content)

    if role == "system":
        if not verbose:
            if summarise and len(text) > _ELIDE:
                return color.dim(f"  system   [{len(text):,} chars of packaging material]")
            if text.startswith(_PREAMBLE_HINT) or len(text) > 240:
                return color.dim("  system   [task preamble]")
        limit = 50_000 if verbose else 160
        return color.dim(_indent(_clip(text, limit), "system"))

    if role == "user":
        # Tool-result echoes that slipped through: hide in showcase (shown under
        # the call already). Keep real user task text.
        if text.startswith("[call]") or text.startswith("{"):
            return None
        label = color.cyan("  user    ")
        body = _clip(text, 360)
        if "\n" not in body:
            return f"{label} {body}"
        pad = " " * 10
        lines = body.splitlines()
        return "\n".join([f"{label} {lines[0]}"] + [pad + line for line in lines[1:]])

    if role == "assistant":
        return None  # rendered from turn.assistant_text with FINAL ANSWER emphasis
    return _indent(_clip(text, 240), role)


def _showcase_assistant(text: str | None, *, has_calls: bool,
                        color: _Color) -> list[str]:
    if not text:
        return []
    answer = None
    for line in text.splitlines():
        if "FINAL ANSWER:" in line:
            answer = line.strip()
            break

    out: list[str] = []
    # When the model is driving tools, the prose/code that produced the call is
    # noise next to the call itself — keep a one-line hint, then the answer.
    if has_calls:
        blocks = len(re.findall(r"```", text)) // 2
        if blocks:
            out.append(color.dim(f"  assistant wrote {blocks} code block"
                                 f"{'s' * (blocks != 1)} → tools below"))
        elif not answer:
            preview = _clip(text.replace("\n", " "), 120)
            out.append(color.dim(f"  assistant {preview}"))
    elif answer and text.strip() == answer:
        pass  # only the ★ line below — don't print it twice
    else:
        # Strip the answer line from the body when we will highlight it separately.
        body_lines = [ln for ln in text.splitlines()
                      if "FINAL ANSWER:" not in ln]
        body = _clip("\n".join(body_lines).strip(), 400) if body_lines else ""
        if body:
            label = color.magenta("  assistant")
            pad = " " * 11
            lines = body.splitlines() or [""]
            out.append(f"{label} {lines[0]}")
            out.extend(pad + line for line in lines[1:])

    if answer:
        out.append(color.bold(color.green(f"  ★ {answer}")))
    return out


def _showcase_call(record: CallRecord, color: _Color, *, verbose: bool = False) -> str:
    c, r = record.call, record.result
    if c.raw:
        title = color.yellow("  → code")
        raw_lines = c.raw.splitlines()
        head = f"{title}  {_clip(raw_lines[0], 100)}"
        lines = [head]
        tail = raw_lines[1:] if verbose else raw_lines[1:4]
        for extra in tail:
            lines.append(f"           {_clip(extra, 100 if not verbose else 500)}")
        if not verbose and len(raw_lines) > 4:
            lines.append(color.dim(f"           … {len(raw_lines) - 4} more lines"))
    elif c.tool:
        title = color.yellow(f"  → {c.tool}")
        lines = [title]
        if isinstance(c.args, dict) and c.args:
            lines.extend(_fmt_mapping(c.args))
        elif c.args:
            lines.extend(_fmt_payload(c.args))
    else:
        lines = [color.yellow(f"  → {c.method or '?'} {c.path or '?'}")]
        if c.args:
            lines.extend(_fmt_payload(c.args))

    if record.forbidden:
        lines.append(color.red("  ✖ BLOCKED — forbidden by the pack"))
        return "\n".join(lines)

    if r.error:
        lines.append(color.red(f"  ← error  ({r.latency_ms:.0f}ms)"))
        lines.extend(_fmt_payload(r.error))
        return "\n".join(lines)

    status = r.status if r.status is not None else "—"
    ok = isinstance(status, int) and status < 400
    arrow = color.green(f"  ← {status}") if ok else color.red(f"  ← {status}")
    lines.append(f"{arrow}  {color.dim(f'({r.latency_ms:.0f}ms)')}")
    lines.extend(_fmt_payload(r.body))
    return "\n".join(lines)


def stream_run_banner(trace: Trace, *, color: _Color | None = None) -> str:
    """One-line header printed the first time a run appears under ``--stream``."""
    c = color or _color_for()
    return c.bold(
        f"┌─ {_short_run_id(trace.run_id)}"
        f"  ·  {trace.task_id}"
        f"  ·  {_label(trace.variant)}"
    )


def render_turn(trace: Trace, index: int, *, style: str = "plain",
                color: _Color | None = None, verbose: bool = False) -> str:
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
    calls = [c for c in trace.calls if c.turn == index]

    if style == "showcase":
        c = color or _color_for()
        head = c.bold(
            f"── turn {turn.index}  ·  {usage.input_tokens:,}↑"
            f"  {usage.output_tokens:,}↓  ·  {turn.latency_ms / 1000:.1f}s"
        )
        out = [head]
        for m in new:
            if verbose and index == 0 and str(m.get("role")) == "system":
                continue
            line = _showcase_message(m, summarise=(index == 0), verbose=verbose, color=c)
            if line:
                out.append(line)
        out += _showcase_assistant(turn.assistant_text, has_calls=bool(calls), color=c)
        out += [_showcase_call(call, c, verbose=verbose) for call in calls]
        return "\n".join(out)

    head = (f"  ── turn {turn.index}"
            f"   {usage.input_tokens:,} in"
            f" · {usage.output_tokens:,} out"
            f" · {turn.latency_ms / 1000:.1f}s")
    out = [head]
    out += [_message(m, summarise=(index == 0)) for m in new]
    if turn.assistant_text:
        out.append(_indent(_clip(turn.assistant_text), "assistant"))
    out += [_call(c) for c in calls]
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


def render(trace: Trace, *, since: int = 0, header: bool = True,
           style: str = "plain", verbose: bool = False) -> str:
    """The whole exchange, or everything from turn `since` onward."""
    color = _color_for() if style == "showcase" else _Color(False)
    out: list[str] = []
    if header:
        if style == "showcase":
            out.append(color.bold(
                f"┌─ {_short_run_id(trace.run_id)}  ·  {trace.task_id}"
                f"  ·  {_label(trace.variant)}"
            ))
        else:
            out.append(f"┌─ {trace.run_id}   task={trace.task_id}"
                       f"   arm={_label(trace.variant)}")

    if header and style == "showcase" and verbose and trace.turns:
        # Packaging / preamble lives in turn 0's system slice — surface it before
        # the turn loop so a reader sees what the model got first.
        c = color or _color_for()
        turn0 = trace.turns[0]
        for m in turn0.messages_in:
            if str(m.get("role")) != "system":
                continue
            line = _showcase_message(m, summarise=False, verbose=True, color=c)
            if line:
                out.append(line)
        if out and out[-1] != "":
            out.append("")

    out += [render_turn(trace, i, style=style, color=color, verbose=verbose)
            for i in range(since, len(trace.turns))]

    if header:
        out.append(_footer(trace, style=style, color=color))
    return "\n".join(out)


def _short_run_id(run_id: str) -> str:
    # run ids look like `A1:core-000-R:0` or similar; keep the readable tail.
    if len(run_id) <= 36:
        return run_id
    return "…" + run_id[-32:]


def _footer(trace: Trace, *, style: str = "plain",
            color: _Color | None = None) -> str:
    c = color or _Color(False)
    if trace.error:
        # An infra death measured nothing about this arm; say which it was so a
        # reader does not take it for a packaging failure.
        kind = f" [{trace.error_kind}]" if trace.error_kind else ""
        msg = f"└─ ERROR{kind}: {_clip(trace.error, 200)}"
        return c.red(msg) if style == "showcase" else msg
    if trace.truncated:
        msg = (f"└─ TRUNCATED after {len(trace.turns)} turns — out of budget, "
               f"not a wrong answer")
        return c.yellow(msg) if style == "showcase" else msg
    answer = _clip(trace.final_answer or "(none)", 200)
    turns, calls = len(trace.turns), len(trace.calls)
    if style == "showcase":
        return c.bold(
            f"└─ {answer}   ({turns} turn{'s' * (turns != 1)}, "
            f"{calls} call{'s' * (calls != 1)})"
        )
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


def render_stored(data: dict[str, Any], *, style: str = "plain",
                  verbose: bool = False) -> str:
    """Render a trace read back from disk.

    Traces are persisted as plain JSON rather than pickled dataclasses, so the
    replay path cannot reuse `render` directly — but it must produce the same
    text, or a transcript would mean two different things depending on whether
    the run was live.
    """
    trace = _rehydrate(data)
    return render(trace, style=style, verbose=verbose)


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
