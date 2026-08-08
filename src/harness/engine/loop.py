"""The agent loop — owned by the harness, never by a vendor framework.

This is non-negotiable and was identified correctly in the original spec: the
benchmark must run identically across providers, so delegating the loop to a
vendor agent SDK would inject an uncontrolled harness into the measurement. The
adapter translates one request and one response; every decision about what
happens next lives here.

Contract: archive/reference/experiment-design.md#the-agent-loop
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from .axes import Invocation, Variant
from .executors import GuardedExecutor
from .generate import ApiSpec
from .infra import error_facts, with_retry
from .packaging import Call, Materials, PackagingMethod
from .provider import Provider, ProviderConfig
from .trace import CallRecord, Trace, Turn

#: Asked for once, in the system preamble. A benchmark that cannot tell an
#: answer from thinking-aloud measures parsing, not packaging.
ANSWER_SENTINEL = "FINAL ANSWER:"

_PREAMBLE = (
    "Answer the task using the tools available to you. When you have the "
    f"answer, reply with a line beginning '{ANSWER_SENTINEL}' followed by the "
    "answer itself. If the task cannot be answered with the data available, "
    f"say so on that line instead — '{ANSWER_SENTINEL} cannot be determined'. "
    "Do not guess."
)


@dataclass
class AgentRunner:
    provider: Provider
    method: PackagingMethod
    spec: ApiSpec
    variant: Variant
    config: ProviderConfig
    forbidden_calls: tuple[str, ...] = ()
    trace_dir: str | None = None
    #: Called as ``on_turn(trace, index)`` once a turn and its calls are on the
    #: trace. Exists so a run can be watched while it happens: the trace is
    #: written once, at the end, which is too late to be a live view. Never
    #: allowed to affect the run — see the guard in `_loop`.
    on_turn: Any = None

    def run(self, task_id: str, prompt: str, *, run_id: str | None = None) -> Trace:
        run_id = run_id or f"{task_id}-{uuid.uuid4().hex[:8]}"
        materials = self.method.materialize(self.spec, self.variant)

        trace = Trace(
            run_id=run_id,
            task_id=task_id,
            variant=self.variant,
            mcp_spec_revision=(
                self.variant.mcp_revision.value if self.variant.mcp_revision else None
            ),
        )
        trace.cost.static_tokens = materials.static_tokens
        trace.config_snapshot = self._snapshot()

        executor = GuardedExecutor(
            inner=self.method.executor(materials),
            forbidden=self.forbidden_calls,
        )
        try:
            self._loop(trace, materials, executor, prompt)
        except Exception as e:  # noqa: BLE001 — a failed run is a data point
            trace.error = f"{type(e).__name__}: {e}"
            # ...but only if it is a data point about the *arm*. A run killed by
            # a full disk or a dead API key measured nothing, and must not be
            # graded as though the packaging failed. Classified from the live
            # exception, never from its string.
            for key, value in error_facts(e).items():
                setattr(trace, key, value)
            trace.finish(None)
        finally:
            executor.teardown()
            merged = self.method.account(trace)
            trace.cost.per_call_overhead_tokens += merged.per_call_overhead_tokens
            trace.cost.session_setup_tokens += merged.session_setup_tokens
            if self.trace_dir:
                trace.write(self.trace_dir)
        return trace

    def _emit(self, trace: Trace, index: int) -> None:
        """Hand a finished turn to the watcher, if there is one.

        Swallowing the exception is deliberate and narrow: a broken or slow
        renderer is a display bug, and letting it abort a run would void a paid
        cell and hand `--resume` work to do over a print statement.
        """
        if self.on_turn is None:
            return
        try:
            self.on_turn(trace, index)
        except Exception:  # noqa: BLE001 — a watcher must never fail a run
            pass

    def _snapshot(self) -> dict[str, Any]:
        """How this run was actually configured, not how it was requested.

        ``unsupported_parameters`` is the important field: a model that rejects
        ``temperature`` runs at whatever its default sampling is, and a reader
        comparing two arms needs to see that rather than infer it.
        """
        rejected = tuple(getattr(self.provider, "unsupported", ()))
        return {
            "provider": getattr(self.provider, "name", "?"),
            "base_url": getattr(self.provider, "base_url", None),
            "model": self.config.model,
            "reasoning_effort": self.config.reasoning_effort,
            "temperature_requested": self.config.temperature,
            "temperature_applied": (
                None if "temperature" in rejected else self.config.temperature
            ),
            "unsupported_parameters": list(rejected),
            "max_turns": self.config.max_turns,
            "caching": self.config.caching,
            "packaging_method": getattr(self.method, "name", "?"),
        }

    # ---- the loop --------------------------------------------------------

    def _loop(
        self, trace: Trace, materials: Materials, executor: Any, prompt: str
    ) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _PREAMBLE},
            *(
                {"role": b.role, "content": b.content}
                for b in materials.context_blocks
            ),
            {"role": "user", "content": prompt},
        ]

        for index in range(self.config.max_turns):
            started = time.perf_counter()
            # Retried in place: at --concurrency 8 a 429 is the shared key
            # pushing back, and losing the whole cell to it costs a full
            # resume pass to recover a run that would have succeeded 2s later.
            completion = with_retry(
                lambda: self.provider.submit(
                    messages, materials.tool_defs, self.config
                ),
                on_retry=lambda e, n, d: trace.retries.append(
                    f"turn {index}: {type(e).__name__} — attempt {n}, waited {d:.1f}s"
                ),
            )
            latency = (time.perf_counter() - started) * 1000

            trace.record_turn(Turn(
                index=index,
                messages_in=list(messages),
                assistant_text=completion.text,
                usage=completion.usage,
                stop_reason=completion.stop_reason,
                latency_ms=latency,
            ))

            calls = self._extract_calls(completion)
            if not calls:
                answer = self._parse_answer(completion.text)
                if answer is not None or completion.stop_reason == "stop":
                    trace.finish(answer)
                    self._emit(trace, index)
                    return
                # No call, no answer: nudge once rather than burning the budget
                # on a model that has stalled.
                messages.append({"role": "assistant", "content": completion.text or ""})
                messages.append({
                    "role": "user",
                    "content": f"Continue, or give your answer on a '{ANSWER_SENTINEL}' line.",
                })
                self._emit(trace, index)
                continue

            if completion.text:
                messages.append({"role": "assistant", "content": completion.text})

            for call in calls:
                record = self._execute(trace, executor, index, call)
                messages.append({
                    "role": "user",
                    "content": self._render_result(call, record),
                })
            # After the calls, so a watcher sees the turn and its effects
            # together rather than a request with its response a turn behind.
            self._emit(trace, index)

        # Out of turns. Recorded as truncation, never as a wrong answer — the
        # two have different causes and folding them together would inflate the
        # silent-failure rate.
        trace.finish(None, truncated=True)

    def _extract_calls(self, completion: Any) -> tuple[Call, ...]:
        """Native tool calls, or a code/shell body parsed out of the text."""
        if completion.tool_calls:
            return completion.tool_calls
        if self.variant.invocation in (Invocation.SHELL, Invocation.CODE):
            body = _fenced_block(completion.text or "")
            if body:
                return (Call(raw=body),)
        return ()

    def _execute(self, trace: Trace, executor: Any, turn: int, call: Call) -> CallRecord:
        started = time.time()
        blocked_before = len(executor.blocked)
        result = executor.invoke(call)

        known: bool | None = None
        if call.path:
            known = self.spec.defines(call.method or "GET", call.path)
        elif call.tool:
            known = any(t.name == call.tool for t in self.method.materialize(
                self.spec, self.variant).tool_defs) or None

        record = CallRecord(
            turn=turn,
            call=call,
            result=result,
            started_at=started,
            forbidden=len(executor.blocked) > blocked_before,
            known_operation=known,
        )
        trace.record_call(record)
        return record

    @staticmethod
    def _render_result(call: Call, record: CallRecord) -> str:
        r = record.result
        head = f"[{call.tool or call.method or 'call'}] "
        if r.error:
            return f"{head}error: {r.error}"
        return f"{head}{r.status}: {r.body}"

    @staticmethod
    def _parse_answer(text: str | None) -> str | None:
        if not text:
            return None
        for line in text.splitlines():
            if ANSWER_SENTINEL in line:
                return line.split(ANSWER_SENTINEL, 1)[1].strip()
        return None


def _fenced_block(text: str) -> str | None:
    """Pull the first fenced code block out of a message."""
    if "```" not in text:
        return None
    _, _, rest = text.partition("```")
    body, _, _ = rest.partition("```")
    lines = body.splitlines()
    if lines and lines[0].strip() in ("sh", "bash", "shell", "python", "py", ""):
        lines = lines[1:]
    return "\n".join(lines).strip() or None
