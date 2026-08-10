"""Provider resolution: built-ins, base-url compatibles, and plugin seams.

Construction must not touch a vendor SDK — the engine stays offline and
importable without a key, so every adapter imports its SDK lazily. These tests
therefore only *resolve and construct*; none calls `submit`.
"""

from __future__ import annotations

import pytest

from harness.engine.providers import available, get
from harness.engine.providers.anthropic_provider import (
    AnthropicProvider, _split_system as split_anthropic,
)
from harness.engine.providers.gemini_provider import (
    GeminiProvider, _split_system as split_gemini,
)
from harness.engine.providers.openai_compat import OpenAiCompatibleProvider
from harness.engine.providers.openai_provider import OpenAIProvider


def test_builtins_resolve_to_their_adapters() -> None:
    assert isinstance(get("openai"), OpenAIProvider)
    assert isinstance(get("anthropic"), AnthropicProvider)
    assert isinstance(get("gemini"), GeminiProvider)


def test_available_lists_the_builtins() -> None:
    assert {"openai", "anthropic", "gemini"} <= set(available())


def test_base_url_threads_into_a_builtin_that_accepts_it() -> None:
    p = get("openai", base_url="https://gateway.internal/v1")
    assert p.base_url == "https://gateway.internal/v1"


def test_an_unknown_name_with_a_base_url_is_an_openai_compatible() -> None:
    """Cerebras/Groq/Ollama/vLLM: a label plus an endpoint, no adapter."""
    p = get("cerebras", base_url="https://api.cerebras.ai/v1")
    assert isinstance(p, OpenAiCompatibleProvider)
    assert p.name == "cerebras"
    assert p.base_url == "https://api.cerebras.ai/v1"


def test_an_unknown_name_without_a_base_url_is_a_clear_error() -> None:
    with pytest.raises(KeyError, match="unknown provider"):
        get("mystery-service")


def test_a_compatible_provider_demands_an_endpoint() -> None:
    """Without a base URL it would be an unlabelled call to OpenAI's own API."""
    with pytest.raises(ValueError, match="needs an endpoint"):
        OpenAiCompatibleProvider(name="cerebras", base_url=None)


def test_a_compatible_provider_prefers_a_service_specific_key(monkeypatch) -> None:
    monkeypatch.setenv("CEREBRAS_API_KEY", "sk-cere")
    p = OpenAiCompatibleProvider(name="cerebras", base_url="https://x/v1")
    assert p.api_key_env == "CEREBRAS_API_KEY"


def test_a_compatible_provider_falls_back_to_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    p = OpenAiCompatibleProvider(name="groq", base_url="https://x/v1")
    assert p.api_key_env == "OPENAI_API_KEY"


def test_module_attr_path_is_an_escape_hatch() -> None:
    """`--provider module:Class` imports a local adapter with no registration."""
    p = get("harness.engine.providers.openai_provider:OpenAIProvider")
    assert isinstance(p, OpenAIProvider)


# ---- message translation (pure, no SDK) ----------------------------------

_MESSAGES = [
    {"role": "system", "content": "be brief"},
    {"role": "user", "content": "task"},
    {"role": "assistant", "content": "thinking"},
    {"role": "user", "content": "tool result A"},
    {"role": "user", "content": "tool result B"},
]


def test_anthropic_split_hoists_system_and_coalesces_user_turns() -> None:
    system, turns = split_anthropic(_MESSAGES)
    assert system == "be brief"
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    # The two consecutive tool results become one well-formed user turn.
    assert turns[-1]["content"] == "tool result A\ntool result B"


def test_gemini_split_maps_assistant_to_model_and_coalesces() -> None:
    system, contents = split_gemini(_MESSAGES)
    assert system == "be brief"
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert [p["text"] for p in contents[-1]["parts"]] == [
        "tool result A", "tool result B",
    ]
