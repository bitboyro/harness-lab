"""Persisted results.

Runs cost money and take wall-clock time, so nothing may be discarded. Two
things are written for every run:

  - the **full trace**, because metrics not yet conceived will need
    recomputing and summary statistics cannot be reversed
  - one **row** in a JSONL ledger, appended immediately

Append-per-run rather than write-at-the-end is deliberate: a matrix that dies
two thirds of the way through should leave two thirds of its results on disk,
not nothing. It also makes a run resumable, which matters once a matrix takes
long enough that interrupting it is normal.

Contract: docs/harness-benchmark-spec.md §6.4
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .axes import axis_summary
from .grader import GradeResult
from .trace import Trace

LEDGER = "results.jsonl"
MANIFEST = "manifest.json"
TRACES = "traces"


@dataclass(frozen=True, slots=True)
class Row:
    """One (arm, task, repeat). Flat on purpose — this is what gets analysed."""

    run_id: str
    arm: str
    task_id: str
    core_id: str | None
    task_class: str
    answerable: bool
    repeat: int
    outcome: str
    detail: str
    confident: bool
    clobbered: tuple[str, ...]
    turns: int
    calls: int
    forbidden_attempts: int
    truncated: bool
    error: str | None
    wall_clock_seconds: float
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    static_tokens: int
    per_call_overhead_tokens: int
    session_setup_tokens: int
    #: Pooling boundaries. Rows differing on any of these describe different
    #: worlds and must never be averaged together.
    model: str
    mcp_spec_revision: str | None
    skill_condition: str
    report_class: str
    seed: int
    surface_size: int
    metrics: dict[str, Any] = field(default_factory=dict)
    #: The axis assignment that actually ran, plus its derived description.
    #: Recorded per row rather than looked up from the preset name, because a
    #: sweep overrides axes and a preset name would then describe something the
    #: run was not.
    axes: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        from dataclasses import asdict
        return json.dumps(asdict(self), default=str)


class ResultStore:
    """A directory of results. Append-only for rows, one file per trace."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / TRACES).mkdir(exist_ok=True)

    # ---- writing ---------------------------------------------------------

    def write_manifest(self, **fields: Any) -> None:
        """What produced these results. Written before the first run.

        Without this a results directory is uninterpretable six weeks later —
        and 'which model was that?' is not a question the rows can answer for
        themselves once several matrices exist side by side.
        """
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        (self.root / MANIFEST).write_text(json.dumps(payload, indent=2, default=str))

    def manifest(self) -> dict[str, Any]:
        path = self.root / MANIFEST
        return json.loads(path.read_text()) if path.exists() else {}

    def record(self, row: Row, trace: Trace | None = None) -> None:
        with (self.root / LEDGER).open("a") as ledger:
            ledger.write(row.to_json() + "\n")
        if trace is not None:
            trace.write(self.root / TRACES)

    # ---- reading ---------------------------------------------------------

    def rows(self) -> Iterator[dict[str, Any]]:
        path = self.root / LEDGER
        if not path.exists():
            return
        for line in path.read_text().splitlines():
            if line.strip():
                yield json.loads(line)

    def completed(self) -> set[tuple[str, str, int]]:
        """(arm, task, repeat) already done — so a resumed run skips them."""
        return {(r["arm"], r["task_id"], r["repeat"]) for r in self.rows()}

    def pooling_keys(self) -> set[tuple]:
        """Distinct worlds present. More than one means the rows must not be
        averaged together, and the report refuses to."""
        return {
            (r["model"], r["mcp_spec_revision"], r["skill_condition"],
             r["report_class"])
            for r in self.rows()
        }


def build_row(
    *,
    arm: str,
    task,
    repeat: int,
    trace: Trace,
    grade: GradeResult,
    metrics: dict[str, Any],
    report_class: str,
    seed: int,
) -> Row:
    usage = trace.usage_total
    skill = ("authored" if trace.variant.instructions.is_authored
             else "generated" if "skill" in str(trace.variant.instructions)
             else "none")
    return Row(
        run_id=trace.run_id,
        arm=arm,
        task_id=task.id,
        core_id=task.core_id,
        task_class=str(task.task_class),
        answerable=task.answerable,
        repeat=repeat,
        outcome=str(grade.outcome),
        detail=grade.detail[:300],
        confident=grade.confident,
        clobbered=tuple(grade.clobbered),
        turns=len(trace.turns),
        calls=len(trace.calls),
        forbidden_attempts=sum(1 for c in trace.calls if c.forbidden),
        truncated=trace.truncated,
        error=trace.error,
        wall_clock_seconds=round(trace.wall_clock_seconds, 3),
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        static_tokens=trace.cost.static_tokens,
        per_call_overhead_tokens=trace.cost.per_call_overhead_tokens,
        session_setup_tokens=trace.cost.session_setup_tokens,
        model=trace.variant.model,
        mcp_spec_revision=trace.mcp_spec_revision,
        skill_condition=skill,
        report_class=report_class,
        seed=seed,
        surface_size=trace.variant.surface_size,
        metrics={k: v.value for k, v in metrics.items() if not k.startswith("_")},
        axes=axis_summary(trace.variant),
    )
