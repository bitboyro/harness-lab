"""Provider abstraction.

The harness owns the agent loop. It cannot delegate to a vendor agent framework,
because that would inject an uncontrolled harness into the thing being measured —
and the thing being measured *is* the harness around the API.

Signatures only at P0. OpenAI lands at P1.

Contract: archive/reference/experiment-design.md#providers
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .packaging import Call, ToolDef


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int


@dataclass(frozen=True, slots=True)
class Capabilities:
    supports_mcp: bool
    supports_parallel_calls: bool
    native_reasoning: bool
    #: Provider-native tool search, if any. Run as a separately *labelled*
    #: variant — never silently substituted for the hand-rolled triad, which
    #: is what keeps arms comparable across providers.
    native_tool_search: bool


@dataclass(frozen=True, slots=True)
class Completion:
    text: str | None
    tool_calls: tuple[Call, ...]
    usage: Usage
    stop_reason: str
    raw: Any = None


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    model: str
    #: Explicit on every provider, always. Defaults differ between vendors and
    #: drift between releases; an unset default silently benchmarks reasoning
    #: effort instead of packaging (V3).
    reasoning_effort: str
    temperature: float
    max_turns: int
    caching: bool

    def __post_init__(self) -> None:
        if not self.reasoning_effort:
            raise ValueError(
                "reasoning_effort must be set explicitly (V3). Leaving it to the "
                "provider default benchmarks effort levels, not packaging."
            )


@runtime_checkable
class Provider(Protocol):
    name: str

    def capabilities(self) -> Capabilities: ...

    def submit(
        self,
        messages: list[dict[str, Any]],
        tools: tuple[ToolDef, ...],
        config: ProviderConfig,
    ) -> Completion: ...

    def price_per_mtok(self, model: str) -> tuple[float, float]:
        """(input, output) USD per million tokens, for cost estimation."""
