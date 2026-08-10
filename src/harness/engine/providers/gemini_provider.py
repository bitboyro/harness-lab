"""Gemini adapter (the ``google-genai`` SDK).

One request in, one response out; the loop is the harness's. Two Gemini-specific
translations:

- **``reasoning_effort`` maps to a thinking token budget**, the same way it does
  for Anthropic — Gemini exposes thinking as a budget, not an enum. The map is
  the provider's reading of the axis, kept explicit (V3).
- **Roles are ``user`` and ``model``, and the system prompt is out of band.**
  The loop's flat system/user/assistant list is split and its non-system turns
  coalesced so consecutive tool-result turns form one well-formed request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..packaging import Call, ToolDef
from ..pricing import ModelPricing, lookup
from ..provider import Capabilities, Completion, ProviderConfig, Usage

_THINKING_BUDGET = {
    "none": 0,
    "minimal": 0,
    "low": 2_048,
    "medium": 8_192,
    "high": 16_384,
}


@dataclass
class GeminiProvider:
    name: str = "gemini"
    api_key_env: str = "GEMINI_API_KEY"
    base_url: str | None = None
    unsupported: tuple[str, ...] = ()
    _client: Any = None

    def __post_init__(self) -> None:
        # Accept GOOGLE_API_KEY too: the SDK's own default, and what many
        # environments already export.
        if not os.environ.get(self.api_key_env) and os.environ.get("GOOGLE_API_KEY"):
            self.api_key_env = "GOOGLE_API_KEY"

    def _sdk(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "the google-genai package is missing — reinstall "
                    "harness-lab (`pip install -e '.[dev]'`)"
                ) from e
            key = os.environ.get(self.api_key_env)
            if not key:
                raise RuntimeError(
                    f"{self.api_key_env} is not set. The engine runs offline "
                    "until a provider is actually called."
                )
            self._client = genai.Client(api_key=key)
        return self._client

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_mcp=False,
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
        from google.genai import types

        system, contents = _split_system(messages)
        budget = _THINKING_BUDGET.get(config.reasoning_effort, 0)

        cfg: dict[str, Any] = {
            "thinking_config": types.ThinkingConfig(thinking_budget=budget),
        }
        if system:
            cfg["system_instruction"] = system
        if config.temperature is not None:
            cfg["temperature"] = config.temperature
        if tools:
            cfg["tools"] = [types.Tool(function_declarations=[
                {"name": t.name, "description": t.description,
                 "parameters": t.parameters}
                for t in tools
            ])]

        response = self._sdk().models.generate_content(
            model=config.model,
            contents=contents,
            config=types.GenerateContentConfig(**cfg),
        )
        return _parse(response)


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for m in messages:
        role, content = m.get("role"), m.get("content") or ""
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        role = "model" if role == "assistant" else "user"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].append({"text": content})
        else:
            contents.append({"role": role, "parts": [{"text": content}]})
    return "\n\n".join(system_parts), contents


def _parse(response: Any) -> Completion:
    text_parts: list[str] = []
    calls: list[Call] = []

    candidates = getattr(response, "candidates", None) or []
    for cand in candidates[:1]:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            fn = getattr(part, "function_call", None)
            if fn is not None:
                args = getattr(fn, "args", None)
                calls.append(Call(tool=getattr(fn, "name", None),
                                  args=dict(args) if args else {}))
            elif getattr(part, "text", None):
                text_parts.append(part.text)

    u = getattr(response, "usage_metadata", None)
    usage = Usage(
        input_tokens=getattr(u, "prompt_token_count", 0) or 0 if u else 0,
        cached_input_tokens=getattr(u, "cached_content_token_count", 0) or 0 if u else 0,
        output_tokens=getattr(u, "candidates_token_count", 0) or 0 if u else 0,
        reasoning_tokens=getattr(u, "thoughts_token_count", 0) or 0 if u else 0,
    )

    return Completion(
        text="\n".join(p for p in text_parts if p) or None,
        tool_calls=tuple(calls),
        usage=usage,
        stop_reason="tool_calls" if calls else "stop",
        raw=response,
    )
