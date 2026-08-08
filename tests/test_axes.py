from __future__ import annotations

import pytest

from harness.engine.axes import (
    Caching, ConfigError, Confirmation, Discovery, DocBudget, ErrorDetail,
    Instructions, Invocation, McpRevision, PRESET_NAMES, ResponseShape,
    SchemaDetail, Transport, Variant, preset,
)

BASE = dict(
    schema_detail=SchemaDetail.STANDARD,
    response_shape=ResponseShape.AS_IS,
    error_detail=ErrorDetail.FIELD_SCOPED,
    doc_budget=DocBudget.STANDARD,
    surface_size=15,
    model="test-model",
    reasoning_effort="medium",
    temperature=0.0,
    caching=Caching.OFF,
    repeats=3,
    mcp_revision=McpRevision.R2026_07_28,
)


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_every_preset_is_a_complete_assignment(name: str) -> None:
    """The stated verification criterion: no axis left implicit."""
    v = preset(name, **BASE)
    for f in Variant.__dataclass_fields__:
        if f in ("mcp_revision", "preset"):
            continue
        assert getattr(v, f) is not None, f"{name}: {f} is unset"


def test_preset_names_cover_the_documented_set() -> None:
    documented = {"A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2", "D3",
                  "E1", "M1", "Z0", "Z1"}
    assert documented <= set(PRESET_NAMES)


def test_non_mcp_presets_do_not_inherit_a_revision() -> None:
    """C arms are HTTP; carrying an MCP revision would be a silent lie."""
    assert preset("C1", **BASE).mcp_revision is None
    assert preset("Z0", **BASE).mcp_revision is None


def test_mcp_transport_requires_a_revision() -> None:
    with pytest.raises(ConfigError, match="mcp_revision is required"):
        preset("A1", **{**BASE, "mcp_revision": None})


def test_mrtr_requires_the_new_revision() -> None:
    """MRTR does not exist in the legacy revision."""
    with pytest.raises(ConfigError, match="requires mcp_revision"):
        preset("M1", **BASE).derive(mcp_revision=McpRevision.LEGACY)


def test_code_fs_requires_code_invocation() -> None:
    with pytest.raises(ConfigError, match="requires invocation 'code'"):
        preset("D1", **BASE).derive(invocation=Invocation.TOOL_CALL)


def test_c_arms_are_shell_not_code() -> None:
    """Freehand curl and writing code against a module tree are different arms."""
    assert preset("C1", **BASE).invocation is Invocation.SHELL
    assert preset("D1", **BASE).invocation is Invocation.CODE


def test_authored_and_generated_skills_do_not_pool() -> None:
    generated = preset("B1", **BASE)
    authored = preset("B1-auth", **BASE)
    assert generated.instructions.is_authored is False
    assert authored.instructions.is_authored is True
    assert generated.pool_key != authored.pool_key


def test_mcp_revisions_do_not_pool() -> None:
    a = preset("A1", **BASE)
    b = a.derive(mcp_revision=McpRevision.LEGACY)
    assert a.pool_key != b.pool_key


def test_unknown_preset_is_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown preset"):
        preset("nope", **BASE)


def test_variant_is_frozen() -> None:
    v = preset("A1", **BASE)
    with pytest.raises(Exception):
        v.surface_size = 50  # type: ignore[misc]


def test_control_arms_have_no_transport_or_tools() -> None:
    z0 = preset("Z0", **BASE)
    assert z0.transport is Transport.NONE
    assert z0.discovery is Discovery.NONE
    assert z0.invocation is Invocation.NONE
    assert z0.instructions is Instructions.NONE
    assert z0.confirmation is Confirmation.NONE
