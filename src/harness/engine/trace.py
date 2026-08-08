"""Full trajectory capture.

Metrics not yet conceived will need recomputation, and summary statistics cannot
be reversed. So the trace records everything: messages, calls with arguments,
server-side request logs with timestamps, usage counters, and the config
snapshot — including ``mcp_spec_revision``, without which a pre- and
post-2026-07-28 run cannot be told apart later.

Contract: docs/harness-benchmark-spec.md §6.4
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .axes import Variant
from .packaging import Call, CostBreakdown, Result
from .provider import Usage


@dataclass(slots=True)
class CallRecord:
    """One attempted operation and what came back."""

    turn: int
    call: Call
    result: Result
    started_at: float
    #: Set when the executor blocked the call before it reached the target.
    #: The harm signal on real APIs where state cannot be diffed.
    forbidden: bool = False
    #: Whether the path resolved to something the surface actually defines.
    #: ``None`` when the executor cannot tell (freehand shell against a real API).
    known_operation: bool | None = None

    @property
    def is_client_error(self) -> bool:
        return self.result.status is not None and 400 <= self.result.status < 500

    @property
    def is_argument_error(self) -> bool:
        return self.result.status in (400, 422)

    @property
    def signature(self) -> str:
        """Identity for redundancy detection: same target, same arguments."""
        c = self.call
        return json.dumps(
            [c.tool, c.method, c.path, c.args, c.raw], sort_keys=True, default=str
        )


@dataclass(slots=True)
class Turn:
    index: int
    messages_in: list[dict[str, Any]]
    assistant_text: str | None
    usage: Usage
    stop_reason: str
    latency_ms: float


@dataclass(slots=True)
class Trace:
    run_id: str
    task_id: str
    variant: Variant
    #: Recorded per run because results are never pooled across revisions (V10).
    mcp_spec_revision: str | None
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    turns: list[Turn] = field(default_factory=list)
    calls: list[CallRecord] = field(default_factory=list)
    final_answer: str | None = None
    #: Set when the loop stopped because it hit max_turns rather than finishing.
    truncated: bool = False
    cost: CostBreakdown = field(default_factory=CostBreakdown)
    state_before: Any = None
    state_after: Any = None
    error: str | None = None
    #: Set when `error` was infra, not experiment signal — see engine/infra.py.
    #: `None` alongside a non-null `error` means the arm genuinely failed.
    error_kind: str | None = None
    #: Everything about how this run was configured that is not on the variant:
    #: model, sampling parameters as *actually applied*, and any the provider
    #: rejected. A run where temperature was never applied must be
    #: distinguishable from one where it was set — otherwise two arms look
    #: identically configured while behaving differently (V3).
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    # ---- accumulation ----------------------------------------------------

    def record_turn(self, turn: Turn) -> None:
        self.turns.append(turn)
        self.cost.payload_tokens += turn.usage.input_tokens
        self.cost.round_trips += 1

    def record_call(self, record: CallRecord) -> None:
        self.calls.append(record)

    def finish(self, answer: str | None, *, truncated: bool = False) -> None:
        self.final_answer = answer
        self.truncated = truncated
        self.ended_at = time.time()

    # ---- derived ---------------------------------------------------------

    @property
    def wall_clock_seconds(self) -> float:
        return (self.ended_at or time.time()) - self.started_at

    @property
    def usage_total(self) -> Usage:
        return Usage(
            input_tokens=sum(t.usage.input_tokens for t in self.turns),
            cached_input_tokens=sum(t.usage.cached_input_tokens for t in self.turns),
            output_tokens=sum(t.usage.output_tokens for t in self.turns),
            reasoning_tokens=sum(t.usage.reasoning_tokens for t in self.turns),
        )

    # ---- persistence -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "variant": {
                k: (v.value if hasattr(v, "value") else v)
                for k, v in asdict(self.variant).items()
            },
            "mcp_spec_revision": self.mcp_spec_revision,
            "config_snapshot": self.config_snapshot,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "wall_clock_seconds": self.wall_clock_seconds,
            "truncated": self.truncated,
            "final_answer": self.final_answer,
            "error": self.error,
            "error_kind": self.error_kind,
            "usage": asdict(self.usage_total),
            "cost": asdict(self.cost),
            "turns": [asdict(t) for t in self.turns],
            "calls": [
                {
                    "turn": c.turn,
                    "call": asdict(c.call),
                    "result": asdict(c.result),
                    "started_at": c.started_at,
                    "forbidden": c.forbidden,
                    "known_operation": c.known_operation,
                }
                for c in self.calls
            ],
            "state_before": self.state_before,
            "state_after": self.state_after,
        }

    def write(self, directory: str | Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.run_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return path
