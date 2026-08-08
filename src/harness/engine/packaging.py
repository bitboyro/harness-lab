"""The PackagingMethod plugin seam.

Adding a packaging method is a new plugin file. It is never a change to the
engine. The 2026-07-28 MCP revision landing mid-design is the proof this seam
was needed: a protocol reshape should cost one file, not a refactor.

Contract: archive/reference/packaging-axes.md#plugin-interface
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .axes import Variant


@dataclass(frozen=True, slots=True)
class Provenance:
    """How a set of materials came to exist.

    Exists so V1 (mechanical generation from one spec) is *auditable* after the
    fact rather than asserted. For authored skills, ``authored_commit`` is the
    pre-registration: the record that the skill predates the results (V9).
    """

    generator: str
    spec_revision: str
    authored_commit: str | None = None

    def __post_init__(self) -> None:
        if self.generator == "authored" and not self.authored_commit:
            raise ValueError(
                "authored materials require authored_commit — without it there "
                "is no evidence the skill predates the results (V9)."
            )


@dataclass(frozen=True, slots=True)
class ContextBlock:
    """Text that enters the prompt before turn 1."""

    role: str
    content: str
    label: str


@dataclass(frozen=True, slots=True)
class ToolDef:
    """One entry on the native function-calling surface."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Materials:
    """Everything that exists before turn 1."""

    context_blocks: tuple[ContextBlock, ...]
    tool_defs: tuple[ToolDef, ...]
    sandbox_files: dict[Path, bytes]
    static_tokens: int
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class Call:
    """One attempted operation, however the agent expressed it."""

    tool: str | None = None
    method: str | None = None
    path: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    raw: str | None = None  # shell command or code body, verbatim


@dataclass(frozen=True, slots=True)
class Result:
    status: int | None
    body: Any
    latency_ms: float
    error: str | None = None


@dataclass
class CostBreakdown:
    """Decomposed, never totalled into a single number.

    The whole point is that different packaging pays in different places.
    Stateless MCP moves cost from ``session_setup_tokens`` to
    ``per_call_overhead_tokens``, which scales with call count — that penalises
    chatty arms and favours arms that batch inside a sandbox. A single total
    hides exactly the mechanism under study.
    """

    static_tokens: int = 0
    per_call_overhead_tokens: int = 0
    session_setup_tokens: int = 0
    payload_tokens: int = 0
    sandbox_seconds: float = 0.0
    round_trips: int = 0

    def total_tokens(self) -> int:
        """Only for cost estimation. Never report this as the result."""
        return (
            self.static_tokens
            + self.per_call_overhead_tokens
            + self.session_setup_tokens
            + self.payload_tokens
        )


@runtime_checkable
class Executor(Protocol):
    def invoke(self, call: Call) -> Result: ...
    def teardown(self) -> None: ...


@runtime_checkable
class PackagingMethod(Protocol):
    """One way of presenting an API to an agent."""

    name: str

    def supports(self, variant: Variant) -> bool:
        """Whether this method can realise the given axis assignment."""

    def materialize(self, spec: Any, variant: Variant) -> Materials:
        """Everything that enters context before turn 1."""

    def executor(self, materials: Materials) -> Executor:
        """How a call is physically made."""

    def account(self, trace: Any) -> CostBreakdown:
        """What this method cost, decomposed."""


_REGISTRY: dict[str, PackagingMethod] = {}


def register(method: PackagingMethod) -> PackagingMethod:
    if method.name in _REGISTRY:
        raise ValueError(f"packaging method {method.name!r} already registered")
    _REGISTRY[method.name] = method
    return method


def resolve(variant: Variant) -> PackagingMethod:
    """Find the one registered method that can realise this variant."""
    candidates = [m for m in _REGISTRY.values() if m.supports(variant)]
    if not candidates:
        raise LookupError(
            f"no packaging method supports variant "
            f"(transport={variant.transport}, discovery={variant.discovery}, "
            f"invocation={variant.invocation}). Register a plugin for it."
        )
    if len(candidates) > 1:
        names = ", ".join(sorted(m.name for m in candidates))
        raise LookupError(
            f"ambiguous: {names} all claim this variant. Narrow their supports()."
        )
    return candidates[0]


def registered() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))
