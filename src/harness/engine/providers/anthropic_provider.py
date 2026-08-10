"""Anthropic adapter.

Like the OpenAI one, this translates a single request and a single response and
nothing else — the agent loop stays in ``loop.py`` so the benchmark runs
identically whichever provider serves it.

Two translations are specific to Anthropic and worth stating:

- **``reasoning_effort`` maps to a thinking token budget.** There is no effort
  enum on the wire; extended thinking is a token allowance. The map below is the
  provider's interpretation of the axis, kept explicit so a reader knows exactly
  what "medium" bought (V3 — the effort must never be left to a default).
- **Extended thinking forbids ``temperature``.** When thinking is on the API
  accepts only the default sampling, so a requested temperature is dropped and
  recorded in ``unsupported`` — never applied silently, which would leave two
  arms looking identically configured while sampling differently.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..packaging import Call, ToolDef
from ..pricing import ModelPricing, lookup
from ..provider import Capabilities, Completion, ProviderConfig, Usage

#: effort → thinking budget in tokens. `minimal`/`none` disable thinking; the
#: rest are round allowances a reader can reason about. Budgets must clear the
#: API's 1024-token floor.
_THINKING_BUDGET = {
    "none": 0,
    "minimal": 0,
    "low": 2_048,
    "medium": 8_192,
    "high": 16_384,
}

#: Room for the visible answer on top of the thinking budget. Anthropic requires
#: ``max_tokens`` and requires it to exceed the thinking budget.
_OUTPUT_HEADROOM = 4_096


@dataclass
class AnthropicProvider:
    name: str = "anthropic"
    api_key_env: str = "ANTHROPIC_API_KEY"
    base_url: str | None = None
    unsupported: tuple[str, ...] = ()
    _client: Any = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url or os.environ.get("ANTHROPIC_BASE_URL") or None

    def _sdk(self) -> Any:
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "the anthropic package is missing — reinstall harness-lab "
                    "(`pip install -e '.[dev]'`)"
                ) from e
            key = os.environ.get(self.api_key_env)
            if not key:
                raise RuntimeError(
                    f"{self.api_key_env} is not set. The engine runs offline "
                    "until a provider is actually called."
                )
            kwargs: dict[str, Any] = {"api_key": key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = Anthropic(**kwargs)
        return self._client

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_mcp=True,
            supports_parallel_calls=True,
            native_reasoning=True,
            native_tool_search=False,
        )

    def pricing(self, model: str) -> ModelPricing:
        return lookup(model)

    def price_per_mtok(self, model: str) -> tuple[float, float]:
        rates = lookup(model).short
        return (rates.input, rates.output)

    def submit(
        self,
        messages: list[dict[str, Any]],
        tools: tuple[ToolDef, ...],
        config: ProviderConfig,
    ) -> Completion:
        system, turns = _split_system(messages)
        budget = _THINKING_BUDGET.get(config.reasoning_effort, 0)

        payload: dict[str, Any] = {
            "model": config.model,
            "system": system,
            "messages": turns,
            "max_tokens": (budget or 0) + _OUTPUT_HEADROOM,
        }
        if budget:
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
            # Thinking accepts only default sampling. Drop temperature and say
            # so, rather than send a value the API will reject or ignore.
            if config.temperature is not None and "temperature" not in self.unsupported:
                self.unsupported = (*self.unsupported, "temperature")
        elif config.temperature is not None and "temperature" not in self.unsupported:
            payload["temperature"] = config.temperature

        if tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description,
                 "input_schema": t.parameters}
                for t in tools
            ]

        response = self._sdk().messages.create(**payload)
        return _parse(response)


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Anthropic takes the system prompt out of band and requires the remaining
    roles to alternate.

    The harness loop emits system/user/assistant as a flat list and can append
    several ``user`` turns in a row (one per tool result). Consecutive same-role
    turns are coalesced into one so the request is well-formed without changing
    what the model sees.
    """
    system_parts: list[str] = []
    turns: list[dict[str, Any]] = []
    for m in messages:
        role, content = m.get("role"), m.get("content") or ""
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        role = "assistant" if role == "assistant" else "user"
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n" + content
        else:
            turns.append({"role": role, "content": content})
    return "\n\n".join(system_parts), turns


def _parse(response: Any) -> Completion:
    text_parts: list[str] = []
    calls: list[Call] = []
    for block in getattr(response, "content", []) or []:
        kind = getattr(block, "type", None)
        if kind == "text":
            text_parts.append(getattr(block, "text", ""))
        elif kind == "tool_use":
            args = getattr(block, "input", {})
            calls.append(Call(tool=getattr(block, "name", None),
                              args=args if isinstance(args, dict) else {}))

    u = getattr(response, "usage", None)
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0 if u else 0
    cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0 if u else 0
    fresh_in = getattr(u, "input_tokens", 0) or 0 if u else 0
    usage = Usage(
        # Our contract: input_tokens is the *whole* prompt, cached is the part
        # served from cache. Anthropic reports fresh, cache-read and
        # cache-write separately, so the whole prompt is their sum.
        input_tokens=fresh_in + cache_read + cache_write,
        cached_input_tokens=cache_read,
        output_tokens=getattr(u, "output_tokens", 0) or 0 if u else 0,
        reasoning_tokens=0,
    )

    return Completion(
        text="\n".join(p for p in text_parts if p) or None,
        tool_calls=tuple(calls),
        usage=usage,
        stop_reason="tool_calls" if calls else "stop",
        raw=response,
    )
