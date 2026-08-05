"""OpenAI adapter.

The harness owns the agent loop; this adapter only translates one request and
one response. Anything that decides *what to do next* belongs in ``loop.py`` —
delegating that to a vendor agent framework would inject an uncontrolled harness
into the thing being measured.

The SDK is imported lazily so the engine stays offline and importable without a
key, which is what keeps P0's test suite honest.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from ..packaging import Call, ToolDef
from ..provider import Capabilities, Completion, ProviderConfig, Usage

#: USD per million tokens, (input, output). Verified at time of writing and
#: volatile — the run planner prints projections from these, so stale numbers
#: mislead a budget decision rather than crashing.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
}
PRICES_VERIFIED = "2026-08-05"


@dataclass
class OpenAIProvider:
    name: str = "openai"
    api_key_env: str = "OPENAI_API_KEY"
    _client: Any = None

    def _sdk(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "the openai package is not installed; run "
                    "`pip install -e '.[openai]'`"
                ) from e
            key = os.environ.get(self.api_key_env)
            if not key:
                raise RuntimeError(
                    f"{self.api_key_env} is not set. The engine runs offline "
                    "until a provider is actually called."
                )
            self._client = OpenAI(api_key=key)
        return self._client

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_mcp=True,
            supports_parallel_calls=True,
            native_reasoning=True,
            native_tool_search=False,
        )

    def price_per_mtok(self, model: str) -> tuple[float, float]:
        for prefix, price in PRICES.items():
            if model.startswith(prefix):
                return price
        raise KeyError(
            f"no price for model {model!r}; add it to PRICES (verified "
            f"{PRICES_VERIFIED}) rather than guessing — the planner shows this "
            "number to a human approving spend."
        )

    def submit(
        self,
        messages: list[dict[str, Any]],
        tools: tuple[ToolDef, ...],
        config: ProviderConfig,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": config.model,
            "input": messages,
            # Explicit on every call. Provider defaults differ and drift; an
            # unset default silently benchmarks reasoning effort (V3).
            "reasoning": {"effort": config.reasoning_effort},
        }
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
                for t in tools
            ]

        response = self._sdk().responses.create(**payload)
        return self._parse(response)

    def _parse(self, response: Any) -> Completion:
        text_parts: list[str] = []
        calls: list[Call] = []

        for item in getattr(response, "output", []) or []:
            kind = getattr(item, "type", None)
            if kind == "function_call":
                raw_args = getattr(item, "arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    # Malformed arguments are data: this is exactly the
                    # argument-validity failure the benchmark measures, so it
                    # must reach the executor rather than raising here.
                    args = {"__unparsed__": raw_args}
                calls.append(Call(tool=getattr(item, "name", None), args=args))
            elif kind == "message":
                for part in getattr(item, "content", []) or []:
                    if getattr(part, "type", None) in ("output_text", "text"):
                        text_parts.append(getattr(part, "text", ""))

        u = getattr(response, "usage", None)
        details = getattr(u, "input_tokens_details", None) if u else None
        out_details = getattr(u, "output_tokens_details", None) if u else None
        usage = Usage(
            input_tokens=getattr(u, "input_tokens", 0) if u else 0,
            cached_input_tokens=getattr(details, "cached_tokens", 0) if details else 0,
            output_tokens=getattr(u, "output_tokens", 0) if u else 0,
            reasoning_tokens=getattr(out_details, "reasoning_tokens", 0) if out_details else 0,
        )

        return Completion(
            text="\n".join(p for p in text_parts if p) or None,
            tool_calls=tuple(calls),
            usage=usage,
            stop_reason="tool_calls" if calls else "stop",
            raw=response,
        )
