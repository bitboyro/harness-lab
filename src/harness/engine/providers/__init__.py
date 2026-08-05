"""Provider adapters. Import lazily — the engine stays offline without a key."""

from __future__ import annotations

from typing import Any

_KNOWN = {"openai": ("harness.engine.providers.openai_provider", "OpenAIProvider")}


def get(name: str) -> Any:
    if name not in _KNOWN:
        raise KeyError(f"unknown provider {name!r}; known: {', '.join(_KNOWN)}")
    module_path, attr = _KNOWN[name]
    import importlib
    return getattr(importlib.import_module(module_path), attr)()


def available() -> tuple[str, ...]:
    return tuple(_KNOWN)
