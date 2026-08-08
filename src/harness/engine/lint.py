"""T1 static lint: the agent-readiness scorecard.

Free to run, no model in the loop. This is the adoption wedge — but only if it
stays honest, which is what ``justified_by`` enforces.

A rule that points at a measured effect size is a defensible claim. A rule that
does not is somebody's opinion, and it renders as ``heuristic`` so a reader can
tell the difference. Back-filling those citations is the point of P4.

Contract: archive/reference/decisions.md G2
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(StrEnum):
    #: An effect size from a T2/T3 run backs this rule.
    MEASURED = "measured"
    #: Reasonable, but nothing has measured it yet.
    HEURISTIC = "heuristic"


@dataclass(frozen=True, slots=True)
class Justification:
    """The run that established a rule's effect size."""

    run_id: str
    metric: str
    effect: str


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    severity: Severity
    confidence: Confidence
    message: str
    location: str | None = None


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    severity: Severity
    summary: str
    check: Callable[[Any], Iterable[Finding]]
    #: Empty until a run justifies it. Emptiness is not a bug — it is the
    #: current, honest state, and it is printed.
    justified_by: tuple[Justification, ...] = field(default=())

    @property
    def confidence(self) -> Confidence:
        return Confidence.MEASURED if self.justified_by else Confidence.HEURISTIC

    def run(self, spec: Any) -> list[Finding]:
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                confidence=self.confidence,
                message=f.message,
                location=f.location,
            )
            for f in self.check(spec)
        ]


_REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    if rule.id in _REGISTRY:
        raise ValueError(f"lint rule {rule.id!r} already registered")
    _REGISTRY[rule.id] = rule
    return rule


def rules() -> tuple[Rule, ...]:
    return tuple(_REGISTRY[k] for k in sorted(_REGISTRY))


@dataclass(frozen=True, slots=True)
class Scorecard:
    findings: tuple[Finding, ...]
    rules_run: int
    rules_measured: int

    @property
    def measured_fraction(self) -> float:
        return self.rules_measured / self.rules_run if self.rules_run else 0.0

    def footer(self) -> str:
        """Printed on every scorecard. Says what the reader is looking at."""
        if not self.rules_run:
            return "No lint rules registered."
        if self.rules_measured == 0:
            return (
                f"0 of {self.rules_run} rules are backed by a measured effect "
                "size. Every finding below is heuristic — treat it as a "
                "hypothesis, not a result."
            )
        return (
            f"{self.rules_measured} of {self.rules_run} rules are backed by a "
            f"measured effect size ({self.measured_fraction:.0%}); the rest are "
            "heuristic and labelled as such."
        )


def scorecard(spec: Any) -> Scorecard:
    active = rules()
    findings: list[Finding] = []
    for rule in active:
        findings.extend(rule.run(spec))
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    findings.sort(key=lambda f: (order[f.severity], f.rule_id))
    return Scorecard(
        findings=tuple(findings),
        rules_run=len(active),
        rules_measured=sum(1 for r in active if r.confidence is Confidence.MEASURED),
    )
