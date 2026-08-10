"""Provider adapters, and how a name resolves to one.

Import lazily — the engine stays offline and importable without a key. The SDK
for any given provider is only touched when that provider is actually called.

Resolution order, most specific first, so an operator can always override the
built-ins without editing this file:

1. ``module:attr`` — an explicit import path. The zero-ceremony escape hatch for
   a provider that lives in a local file.
2. an entry point in group ``harness.providers`` — a *separate* pip package can
   register a provider without touching this repo. This is the actual plugin
   seam: `pip install harness-something` and `--provider something` works.
3. a built-in (``openai``, ``anthropic``, ``gemini``).
4. anything else, *if* ``--base-url`` was given — treated as an OpenAI-compatible
   endpoint under that label. This is what makes Cerebras, Groq, Together,
   Ollama, vLLM and LM Studio usable with no adapter and no code change: they
   all speak OpenAI's wire format, so a name plus a URL is enough.

Adding a provider is a new file plus (for the built-ins) one row below — never a
change to the engine core, which the layering test forbids from importing a
vendor SDK at all.
"""

from __future__ import annotations

import inspect
from typing import Any

#: name → (module path, class attribute). Built-ins only; everything else is
#: discovered (entry points) or explicit (``module:attr``).
_KNOWN = {
    "openai": ("harness.engine.providers.openai_provider", "OpenAIProvider"),
    "anthropic": ("harness.engine.providers.anthropic_provider", "AnthropicProvider"),
    "gemini": ("harness.engine.providers.gemini_provider", "GeminiProvider"),
}


def _load(module_path: str, attr: str) -> Any:
    import importlib

    return getattr(importlib.import_module(module_path), attr)


def _construct(cls: Any, base_url: str | None) -> Any:
    """Instantiate ``cls``, passing ``base_url`` only if it accepts it.

    A third-party plugin need not know about base URLs; a built-in that speaks a
    self-hostable API does. Rather than force every adapter to carry the
    parameter, we hand it over only when the signature has somewhere to put it.
    """
    try:
        params = inspect.signature(cls).parameters
    except (TypeError, ValueError):  # C-level callable without a signature
        params = {}
    if base_url is not None and "base_url" in params:
        return cls(base_url=base_url)
    return cls()


def _entry_point(name: str) -> Any | None:
    from importlib.metadata import entry_points

    for ep in entry_points(group="harness.providers"):
        if ep.name == name:
            return ep.load()
    return None


def get(name: str, *, base_url: str | None = None) -> Any:
    """Resolve a provider name to a ready instance.

    ``base_url`` points a provider at a self-hosted server or gateway. For a
    name that matches nothing else it is also the signal to treat the name as an
    OpenAI-compatible endpoint, since that is the only way an unknown label can
    mean anything runnable.
    """
    if ":" in name:
        module_path, _, attr = name.partition(":")
        return _construct(_load(module_path, attr), base_url)

    if (cls := _entry_point(name)) is not None:
        return _construct(cls, base_url)

    if name in _KNOWN:
        return _construct(_load(*_KNOWN[name]), base_url)

    if base_url is not None:
        from .openai_compat import OpenAiCompatibleProvider

        return OpenAiCompatibleProvider(name=name, base_url=base_url)

    raise KeyError(
        f"unknown provider {name!r}. Built in: {', '.join(sorted(_KNOWN))}. "
        f"For any OpenAI-compatible server (Cerebras, Groq, Together, Ollama, "
        f"vLLM, …) pass --base-url and this name is used as the label. Or give "
        f"an explicit 'module:Class' path, or install a package that registers "
        f"a 'harness.providers' entry point."
    )


def available() -> tuple[str, ...]:
    """Built-in names plus anything an installed package registered."""
    from importlib.metadata import entry_points

    discovered = tuple(ep.name for ep in entry_points(group="harness.providers"))
    return tuple(sorted({*_KNOWN, *discovered}))
