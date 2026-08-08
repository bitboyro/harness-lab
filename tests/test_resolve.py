"""One arm registry: resolve() replaces the deleted name→class tables."""

from __future__ import annotations

import pytest

from conftest import BASE_AXES

from harness.engine.axes import PRESET_NAMES, ConfigError, preset
from harness.engine.methods import register_defaults, reset_defaults
from harness.engine.packaging import clear_registry, resolve


# Frozen expectation of what the deleted METHOD_FOR_PRESET / _METHODS agreed
# on for every shipped arm. The anti-regression for deleting those tables.
_EXPECTED_METHOD = {
    "A1": "eager-all-mcp",
    "A2": "meta-tools-mcp",
    "B1": "eager-all-mcp",
    "B2": "meta-tools-mcp",
    "B1-auth": "eager-all-mcp",
    "B2-auth": "meta-tools-mcp",
    "C1": "docs-shell",
    "C2": "docs-shell",
    "D1": "code-fs",
    "D2": "code-fs",
    "D2-auth": "code-fs",
    "D3": "meta-tools-mcp",
    "E1": "retrieval-mcp",
    "M1": "eager-all-mcp",
    "Z0": "z0-none",
    "Z1": "z1-pre-executed",
}


@pytest.fixture(autouse=True)
def _registry():
    reset_defaults()
    yield
    clear_registry()


@pytest.mark.parametrize("name", list(PRESET_NAMES))
def test_every_preset_resolves_to_its_old_table_method(name) -> None:
    method = resolve(preset(name, **BASE_AXES))
    assert method.name == _EXPECTED_METHOD[name]


def test_probe_and_run_agree_on_skill_bearing_arms() -> None:
    """The bug this closes: probe's _METHODS dropped B1/B2's skill condition
    by falling through to EagerAllMcp on name alone. Both paths now resolve
    the same way — by axes — so B1 is still eager-all *with* a skill."""
    from harness.engine.axes import Instructions

    for name in ("B1", "B2", "B1-auth", "B2-auth", "D2-auth"):
        variant = preset(name, **BASE_AXES)
        assert resolve(variant).name == _EXPECTED_METHOD[name]
        assert variant.instructions is not Instructions.NONE

    # Previously unreachable on the probe path (missing from _METHODS).
    for name in ("E1", "M1", "Z1"):
        assert resolve(preset(name, **BASE_AXES)).name == _EXPECTED_METHOD[name]


def test_unknown_arm_is_refused_not_defaulted() -> None:
    with pytest.raises(ConfigError, match="unknown preset"):
        preset("not-an-arm", **BASE_AXES)


def test_register_defaults_is_idempotent() -> None:
    register_defaults()
    register_defaults()
    assert resolve(preset("A1", **BASE_AXES)).name == "eager-all-mcp"
