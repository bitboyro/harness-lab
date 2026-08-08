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

Contract: archive/reference/experiment-design.md#what-is-persisted
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .axes import axis_summary
from .grader import GradeResult, Outcome
from .infra import RETRYABLE, ErrorKind, classify, classify_message, error_facts
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
    #: Why the run died, when it died for reasons outside the arm under test.
    #: `None` next to a non-null `error` means the arm genuinely failed and the
    #: row is real data. Anything else means the row is void: excluded from
    #: every rate, and re-run rather than skipped by `--resume`.
    error_kind: str | None
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
    #: Typed evidence behind `error_kind` (§6), and the transient failures the
    #: run survived on its way to succeeding. Defaulted because they are absent
    #: on every row written before the taxonomy existed.
    error_http_status: int | None = None
    error_provider_code: str | None = None
    error_fatal: bool = False
    retries: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    #: The axis assignment that actually ran, plus its derived description.
    #: Recorded per row rather than looked up from the preset name, because a
    #: sweep overrides axes and a preset name would then describe something the
    #: run was not.
    axes: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        from dataclasses import asdict
        return json.dumps(asdict(self), default=str)


def _labelled(row: dict[str, Any]) -> dict[str, Any]:
    """Backfill `error_kind` on a row written before the field existed.

    matrix-40 holds 28 rows reading `outcome: fail`, `detail: "run error:
    OSError: [Errno 28] No space left on device"`. Those cells measured the
    disk, not the arm, and nothing in the row said so. Reclassifying on read
    keeps the ledger append-only while making every historical result honest.

    Only rows that already carry an `error` are considered, so a graded failure
    can never be relabelled as infrastructure.
    """
    if row.get("error_kind") or not row.get("error"):
        return row
    kind = classify_message(row["error"])
    if kind is None:
        return row
    return {**row, "error_kind": str(kind),
            "outcome": str(Outcome.INFRA_ERROR),
            "detail": f"infra error ({kind}): {row['error']}"[:300]}


class ResultStore:
    """A directory of results. Append-only for rows, one file per trace."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / TRACES).mkdir(exist_ok=True)
        #: Serialises the ledger append, and *only* the append. Public because
        #: the matrix's Ctrl-C and abort paths take it before `os._exit` to
        #: guarantee no line is half-written — see `cli._run`. It lives here
        #: rather than in the caller because append-only durability is this
        #: class's guarantee to keep, and a caller that forgot to hold a lock
        #: it owned would corrupt the one file the whole run is for.
        self.ledger_lock = threading.Lock()

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
        """Persist one run. The row always lands, even if the trace cannot.

        The trace is written first so that a failure to write it can be folded
        into the row before the row is committed. Losing a 900KB trace costs us
        recomputable detail; losing the row costs us the run itself, and a cell
        that is absent from the ledger is indistinguishable from one that was
        never scheduled.

        Only the append is serialised. The trace write deliberately runs
        outside the lock: every trace has its own `{run_id}` filename so two
        writers cannot collide, and holding a global lock across a
        serialise-plus-compress made the one shared resource in the matrix
        scale with trace size — the wrong thing to do right before raising
        concurrency.
        """
        if trace is not None:
            try:
                trace.write(self.root / TRACES)
            except Exception as e:  # noqa: BLE001 — the row matters more
                kind = classify(e) or ErrorKind.UNKNOWN
                row = replace(
                    row,
                    outcome=str(Outcome.INFRA_ERROR),
                    detail=f"trace unwritable ({kind}): {type(e).__name__}: {e}"[:300],
                    error=f"{type(e).__name__}: {e}",
                    error_kind=str(kind),
                )
        line = row.to_json() + "\n"
        with self.ledger_lock, (self.root / LEDGER).open("a") as ledger:
            ledger.write(line)

    # ---- reading ---------------------------------------------------------

    def raw_rows(self) -> Iterator[dict[str, Any]]:
        """Every line as written, superseded rows included. Audit only."""
        path = self.root / LEDGER
        if not path.exists():
            return
        for line in path.read_text().splitlines():
            if line.strip():
                yield json.loads(line)

    def rows(self) -> Iterator[dict[str, Any]]:
        """One row per cell, newest wins, infra failures labelled.

        A `--resume` re-runs cells whose only row was an infra failure, so the
        same (arm, task, repeat) can legitimately appear twice. The ledger stays
        append-only — that is the durability guarantee this whole module is
        built around — and the duplicate is resolved here instead, keeping the
        superseded row on disk as evidence of what the machine did.

        Rows written before `error_kind` existed are classified on the way out
        (see :func:`infra.classify_message`), so an old ledger reports honestly
        and resumes correctly without being rewritten.
        """
        latest: dict[tuple[str, str, int], dict[str, Any]] = {}
        for row in self.raw_rows():
            latest[(row["arm"], row["task_id"], row["repeat"])] = _labelled(row)
        return iter(latest.values())

    def completed(self) -> set[tuple[str, str, int]]:
        """(arm, task, repeat) already done — so a resumed run skips them.

        Infra failures do not count as done. They measured the disk or the API
        key, not the arm, so a resume must re-run them rather than preserve a
        fake result forever. This is the difference between `--resume` meaning
        "finish the matrix" and "finish the matrix except the broken parts".
        """
        return {
            (r["arm"], r["task_id"], r["repeat"])
            for r in self.rows()
            if r.get("error_kind") not in RETRYABLE
        }

    def voided(self) -> list[dict[str, Any]]:
        """Rows a resume would re-run, so the CLI can say so before spending."""
        return [r for r in self.rows() if r.get("error_kind") in RETRYABLE]

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
        error_kind=trace.error_kind,
        error_http_status=trace.error_http_status,
        error_provider_code=trace.error_provider_code,
        error_fatal=trace.error_fatal,
        retries=tuple(trace.retries),
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


def infra_row(
    *,
    arm: str,
    task,
    repeat: int,
    exc: BaseException,
    report_class: str,
    seed: int,
    model: str,
    surface_size: int,
) -> Row:
    """A row for a cell that blew up outside the agent loop.

    `AgentRunner.run` catches its own exceptions, so anything reaching the
    matrix driver failed in metrics, row assembly or persistence — after the
    provider was already paid. Previously that was printed and dropped, which
    is how 1380 cells vanished from `matrix-40` leaving no trace but terminal
    scrollback. The run is void either way; it just has to be a *visible* void
    so `--resume` can find it and the report can count it.
    """
    kind = classify(exc) or ErrorKind.UNKNOWN
    message = f"{type(exc).__name__}: {exc}"
    return Row(
        run_id=f"lost-{arm}-{task.id}-{repeat}",
        arm=arm,
        task_id=task.id,
        core_id=getattr(task, "core_id", None),
        task_class=str(getattr(task, "task_class", "unknown")),
        answerable=bool(getattr(task, "answerable", True)),
        repeat=repeat,
        outcome=str(Outcome.INFRA_ERROR),
        detail=f"lost before persistence ({kind}): {message}"[:300],
        confident=False,
        clobbered=(),
        turns=0,
        calls=0,
        forbidden_attempts=0,
        truncated=False,
        error=message,
        wall_clock_seconds=0.0,
        **error_facts(exc),
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        static_tokens=0,
        per_call_overhead_tokens=0,
        session_setup_tokens=0,
        model=model,
        mcp_spec_revision=None,
        skill_condition="none",
        report_class=report_class,
        seed=seed,
        surface_size=surface_size,
    )
