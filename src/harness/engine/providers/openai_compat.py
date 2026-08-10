"""A named OpenAI-compatible provider.

Cerebras, Groq, Together, Fireworks, OpenRouter, and every local runner
(Ollama, llama.cpp, vLLM, LM Studio) expose OpenAI's wire format. None of them
needs its own adapter — only an endpoint and a label. This is that: the OpenAI
adapter, pointed elsewhere and *named* for the service so a run against Cerebras
is never filed under ``openai``.

The label matters. ``OpenAIProvider`` already records ``base_url`` so a
self-hosted run is not mistaken for the vendor's; carrying the service name as
well is what lets the ledger, the report, and ``compare`` say *which* compatible
service produced a number, not merely that it was not OpenAI's own endpoint.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .openai_provider import OpenAIProvider


def _key_env_for(name: str) -> str:
    """Prefer a service-specific key, fall back to ``OPENAI_API_KEY``.

    ``--provider cerebras`` reads ``CEREBRAS_API_KEY`` if it is set, so several
    compatible services can be configured at once without their keys colliding
    on a single variable. When only ``OPENAI_API_KEY`` is present, that is used
    — the common case of one gateway behind one key still works with no setup.
    """
    specific = re.sub(r"[^A-Z0-9]", "_", name.upper()) + "_API_KEY"
    return specific if os.environ.get(specific) else "OPENAI_API_KEY"


@dataclass
class OpenAiCompatibleProvider(OpenAIProvider):
    name: str = "openai-compatible"
    #: Resolved from the service name in ``__post_init__`` when left unset, so
    #: the constructor stays a name plus a URL.
    api_key_env: str = ""

    def __post_init__(self) -> None:
        # Deliberately *not* calling super().__post_init__: the parent falls
        # back to OPENAI_BASE_URL, but a compatible provider with no explicit
        # endpoint has lost its only reason to exist — it would silently become
        # a mislabelled call to OpenAI's own API.
        if not self.base_url:
            raise ValueError(
                f"provider {self.name!r} needs an endpoint: pass --base-url "
                "(e.g. https://api.cerebras.ai/v1). Without it this would be an "
                "unlabelled call to OpenAI's own API."
            )
        if not self.api_key_env:
            self.api_key_env = _key_env_for(self.name)
