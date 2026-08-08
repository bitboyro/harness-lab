"""Task pack loader and validator.

The task pack is the interop contract: the engine consumes it, users author it,
and everything downstream is shaped by it. Frozen before the engine was written,
deliberately — a format that changes after traces exist in the wild invalidates
them.

The load-time rules below are the reason this module exists. They are not
defensive coding; each one blocks a specific way of producing a wrong number.

Contract: docs/design-your-test-run.md
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA_VERSION = 1

#: Hosts that look like somebody's production system. Deliberately broad — a
#: false positive costs one flag, a false negative costs real data.
_PRODUCTION_HINTS = re.compile(
    r"(^|[.\-/])(prod|production|live|www)([.\-/]|$)|"
    r"\.(com|org|net|io|eu|gov)(/|$|:)",
    re.IGNORECASE,
)
_LOCAL_HOSTS = re.compile(
    r"localhost|127\.0\.0\.1|0\.0\.0\.0|::1|\.local|\.internal|\.test|host\.docker\.internal",
    re.IGNORECASE,
)


class PackError(ValueError):
    """A task pack that cannot be trusted to produce a correct measurement."""


def _explain(exc: ValidationError) -> str:
    """Flatten pydantic's report into something a pack author can act on."""
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        msg = err["msg"].removeprefix("Value error, ")
        if err["type"] == "extra_forbidden":
            msg = f"unknown field (typo?) — {msg}" if msg else "unknown field (typo?)"
        lines.append(f"{loc}: {msg}")
    return "; ".join(lines)


class ReportClass(StrEnum):
    CONTROLLED = "controlled"
    FIELD = "field"


class TaskClass(StrEnum):
    R = "R"
    W_SAFE = "W-safe"
    W_LOSSY = "W-lossy"
    W_IRREV = "W-irrev"
    RW_FAN = "RW-fan"

    @property
    def is_write(self) -> bool:
        return self is not TaskClass.R


class IsolationMode(StrEnum):
    INSTANCE_PER_RUN = "instance-per-run"
    RESEED = "reseed"
    SNAPSHOT = "snapshot"
    NONE = "none"


class GradeType(StrEnum):
    EQUALS = "equals"
    CONTAINS = "contains"
    REGEX = "regex"
    JSONPATH = "jsonpath"
    STATE_DIFF = "state-diff"
    SCRIPT = "script"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Auth(_Model):
    type: Literal["none", "bearer", "header", "basic"] = "none"
    env: str | None = None
    header_name: str | None = None


class McpTarget(_Model):
    url: str
    spec_revision: Literal["2026-07-28", "legacy", "auto"] = "auto"


class ApiTarget(_Model):
    openapi: str | None = None
    mcp: McpTarget | None = None
    base_url_env: str | None = None
    auth: Auth = Auth()

    @model_validator(mode="after")
    def _reachable(self) -> Self:
        if not (self.openapi or self.mcp or self.base_url_env):
            raise PackError(
                "api needs at least one of openapi / mcp / base_url_env — "
                "otherwise there is nothing to run against."
            )
        return self


class Safety(_Model):
    writes_enabled: bool = False
    production_ack: bool = False
    forbidden_calls: tuple[str, ...] = ()


class Isolation(_Model):
    mode: IsolationMode = IsolationMode.NONE
    setup: str | None = None
    teardown: str | None = None
    state_snapshot: str | None = None

    @model_validator(mode="after")
    def _setup_present(self) -> Self:
        if self.mode is not IsolationMode.NONE and not self.setup:
            raise PackError(f"isolation mode {self.mode!r} requires a setup script")
        return self


class Difficulty(_Model):
    hops: int | None = None
    nesting: int | None = None
    fan_out: int | None = None
    ambiguity: Literal["low", "medium", "high"] | None = None


class Grade(_Model):
    type: GradeType
    target: Literal["answer", "state"] = "answer"
    value: Any = None
    pattern: str | None = None
    path: str | None = None
    expect: Any = None
    run: str | None = None


class GoldCall(_Model):
    method: str | None = None
    path: str | None = None
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _addressable(self) -> Self:
        if not (self.tool or self.path):
            raise PackError("a gold call needs either a tool name or an HTTP path")
        return self


class Task(_Model):
    id: str
    prompt: str
    core_id: str | None = None
    task_class: TaskClass = Field(default=TaskClass.R, alias="class")
    answerable: bool = True
    harm_tier: int = 0
    difficulty: Difficulty = Difficulty()
    grade: tuple[Grade, ...] = ()
    gold_call_sequence: tuple[GoldCall, ...] = ()
    expected_end_state: dict[str, Any] | None = None
    forbidden_calls: tuple[str, ...] = ()
    #: Why no answer exists. Only meaningful when answerable is false.
    unanswerable_because: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if not 0 <= self.harm_tier <= 3:
            raise PackError(f"task {self.id!r}: harm_tier must be 0..3")

        # An unanswerable task graded on answer content is self-contradictory:
        # the correct behaviour is refusal, and the grader scores that directly.
        if not self.answerable:
            bad = [g.type for g in self.grade
                   if g.target == "answer" and g.type in (GradeType.EQUALS, GradeType.JSONPATH)]
            if bad:
                raise PackError(
                    f"task {self.id!r}: answerable=false cannot have "
                    f"{bad[0].value!r} grading against the answer — there is no "
                    "correct answer to match. Score the refusal instead."
                )
        return self

    @property
    def needs_state(self) -> bool:
        return self.expected_end_state is not None or any(
            g.type is GradeType.STATE_DIFF or g.target == "state" for g in self.grade
        )


class PackMeta(_Model):
    id: str
    description: str = ""
    report_class: ReportClass


class TaskPack(_Model):
    schema_version: int
    pack: PackMeta
    api: ApiTarget
    safety: Safety = Safety()
    isolation: Isolation = Isolation()
    tasks: tuple[Task, ...]

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.schema_version != SCHEMA_VERSION:
            raise PackError(
                f"unsupported schema_version {self.schema_version}; this engine "
                f"reads version {SCHEMA_VERSION}. Refusing rather than guessing."
            )
        if not self.tasks:
            raise PackError("a pack with no tasks measures nothing")

        seen: set[str] = set()
        for t in self.tasks:
            if t.id in seen:
                raise PackError(f"duplicate task id {t.id!r}")
            seen.add(t.id)

        self._check_write_gate()
        self._check_state_grading()
        self._check_matched_pairs()
        return self

    def _check_write_gate(self) -> None:
        """Writes are opt-in. You cannot accidentally run mutations."""
        if self.safety.writes_enabled:
            return
        writes = [t.id for t in self.tasks if t.task_class.is_write]
        if writes:
            raise PackError(
                f"tasks {writes[:3]} mutate state but safety.writes_enabled is "
                "false. Enable it deliberately, or reclassify the tasks."
            )

    def _check_state_grading(self) -> None:
        """Writes are graded on final server state, never on the transcript."""
        needs = [t.id for t in self.tasks if t.needs_state]
        if needs and not self.isolation.state_snapshot:
            raise PackError(
                f"tasks {needs[:3]} grade on server state but isolation."
                "state_snapshot is unset. Grading writes from the transcript is "
                "never permitted — an agent that claims success without acting "
                "would score as correct."
            )

    def _check_matched_pairs(self) -> None:
        """Tasks sharing a core must match on every difficulty dimension (V7).

        This is what makes a matched pair a matched pair. If they differ, the
        write penalty measures difficulty instead of the terminal operation,
        which is the exact confound the design exists to remove.
        """
        by_core: dict[str, list[Task]] = {}
        for t in self.tasks:
            if t.core_id:
                by_core.setdefault(t.core_id, []).append(t)

        for core, tasks in by_core.items():
            if len(tasks) < 2:
                continue
            first = tasks[0]
            for other in tasks[1:]:
                if other.difficulty != first.difficulty:
                    raise PackError(
                        f"core {core!r}: tasks {first.id!r} and {other.id!r} share "
                        "a core but differ on difficulty. Matched pairs must be "
                        "identical on every dimension (V7), or the write penalty "
                        "measures difficulty rather than the terminal operation."
                    )

    @classmethod
    def parse(cls, data: Any) -> TaskPack:
        """Validate a mapping into a pack, raising :class:`PackError`.

        The public entry point. Pydantic is an implementation detail — it wraps
        our messages in its own ``ValidationError``, so callers would otherwise
        have to catch a library exception to handle a contract violation.
        """
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise PackError(_explain(e)) from e

    # ---- capability reporting -------------------------------------------

    def unavailable_metrics(self) -> dict[str, str]:
        """Metrics this pack cannot produce, and why.

        Printed in the report. A pack that yields only gold-free metrics is a
        legitimate pack (assertion-free mode) — what is not legitimate is a
        report that stays quiet about what it could not measure.
        """
        missing: dict[str, str] = {}
        if not any(t.grade for t in self.tasks):
            missing["success_rate"] = "no task defines a grade (assertion-free mode)"
            missing["cost_per_success"] = "success is undefined without grades"
        if not any(t.gold_call_sequence for t in self.tasks):
            missing["selection_accuracy"] = "no task defines a gold_call_sequence"
            missing["z1_ceiling"] = "Z1 needs a gold_call_sequence to pre-execute"
        if not self.isolation.state_snapshot:
            missing["destructive_write_rate"] = "no isolation.state_snapshot to diff"
            missing["harm_per_100_tasks"] = "no isolation.state_snapshot to diff"
        if not any(not t.answerable for t in self.tasks):
            missing["false_positive_answering"] = "no unanswerable tasks in the pack"
        return missing

    def production_risk(self, base_url: str | None) -> str | None:
        """Whether this looks like a write run against somebody's production."""
        if not self.safety.writes_enabled or not base_url:
            return None
        if _LOCAL_HOSTS.search(base_url):
            return None
        if _PRODUCTION_HINTS.search(base_url):
            return (
                f"{base_url!r} looks like a production host and this pack has "
                "writes enabled."
            )
        return None


def load(path: str | Path, *, base_url: str | None = None,
         allow_production_writes: bool = False) -> TaskPack:
    """Load and validate a task pack.

    ``allow_production_writes`` is the second of two independent gates on
    mutating a real system: the pack must set ``safety.production_ack`` *and*
    the caller must pass this. One gate is a typo away from being wrong.
    """
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise PackError(f"{path}: invalid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise PackError(f"{path}: expected a mapping at the top level")

    pack = TaskPack.parse(raw)

    risk = pack.production_risk(base_url)
    if risk:
        if not pack.safety.production_ack:
            raise PackError(f"{risk} Set safety.production_ack to proceed.")
        if not allow_production_writes:
            raise PackError(
                f"{risk} safety.production_ack is set, but the caller did not "
                "pass allow_production_writes. Both gates are required."
            )
    return pack
