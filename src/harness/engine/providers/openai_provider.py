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
import re
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
    """OpenAI, or anything speaking its API.

    ``OPENAI_BASE_URL`` points this at a self-hosted vLLM, a gateway, or any
    compatible server. The base URL is recorded on the provider so a run against
    a self-hosted model is never mistaken for one against the vendor endpoint —
    they are different measurements even at the same model id.
    """

    name: str = "openai"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None
    #: Parameters this model rejected. Learned at run time and recorded in the
    #: config snapshot so an omitted sampling parameter is never invisible.
    unsupported: tuple[str, ...] = ()
    _client: Any = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url or os.environ.get("OPENAI_BASE_URL") or None

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
            kwargs: dict[str, Any] = {"api_key": key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_mcp=True,
            supports_parallel_calls=True,
            native_reasoning=True,
            native_tool_search=False,
        )

    def price_per_mtok(self, model: str) -> tuple[float, float]:
        """USD per million tokens.

        Raises on an unknown model rather than falling back to a default. This
        number is shown to a human approving spend, so a plausible-looking guess
        is worse than a refusal.

        Override per model with ``HARNESS_PRICE_<MODEL>="in,out"`` — the escape
        hatch for self-hosted or private models that cannot be in a public table.
        """
        env_key = "HARNESS_PRICE_" + re.sub(r"[^A-Z0-9]", "_", model.upper())
        if override := os.environ.get(env_key):
            try:
                a, b = (float(x) for x in override.split(","))
                return (a, b)
            except ValueError as e:
                raise ValueError(
                    f"{env_key} must be 'input,output' in USD per Mtok, "
                    f"got {override!r}"
                ) from e

        if model in PRICES:
            return PRICES[model]

        # A *dated snapshot* of a known model is that model. Anything else is a
        # different model: `gpt-5.6-luna` starts with `gpt-5` but is not gpt-5,
        # and prefix matching would have priced it silently and wrongly.
        for base, price in PRICES.items():
            if model.startswith(base) and re.fullmatch(
                r"-\d{4}-\d{2}-\d{2}", model[len(base):]
            ):
                return price

        raise KeyError(
            f"no price for model {model!r}. Add it to PRICES (last verified "
            f"{PRICES_VERIFIED}) or set {env_key}='input,output' — guessing here "
            "would put a wrong number in front of a spend approval."
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
        if config.temperature is not None and "temperature" not in self.unsupported:
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

        response = self._create(payload)
        return self._parse(response)

    def _create(self, payload: dict[str, Any]) -> Any:
        """Send, and adapt once to a parameter this model does not accept.

        Reasoning models reject ``temperature`` outright. Rather than hardcode a
        list of which models those are — a list that is wrong the moment a new
        model ships — the rejection is learned from the API's own error and
        recorded.

        Recorded, not swallowed: ``unsupported`` is written into the run config
        snapshot, so a run where temperature was never applied is
        distinguishable from one where it was set to the same value. Silently
        dropping a sampling parameter would leave two arms looking identically
        configured while behaving differently (V3).
        """
        try:
            return self._sdk().responses.create(**payload)
        except Exception as e:  # noqa: BLE001 — narrowed by inspecting the message
            param = _unsupported_parameter(e)
            if not param or param not in payload:
                raise
            self.unsupported = (*self.unsupported, param)
            payload.pop(param)
            return self._sdk().responses.create(**payload)

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


def _unsupported_parameter(error: Exception) -> str | None:
    """Pull the offending parameter name out of a 400.

    Matches the API's own wording rather than a status code, because a 400 that
    means "your schema is wrong" must not be retried as if it were "this model
    has no temperature".
    """
    message = str(error)
    if "nsupported parameter" not in message and "not supported with this model" not in message:
        return None
    match = re.search(r"'([a-z_]+)' is not supported", message) or \
        re.search(r"[Uu]nsupported parameter: '([a-z_]+)'", message)
    return match.group(1) if match else None
