"""Arms from YAML — the ladder must not move, and AXES covers Variant."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from harness.engine.arms import BUILTIN_YAML
from harness.engine.armspec import load_arms
from harness.engine.axes import (
    AXES, Caching, Confirmation, Discovery, DocBudget, ErrorDetail,
    Instructions, Invocation, McpRevision, ResponseShape, SchemaDetail,
    Transport, Variant, coerce_axis_value, preset,
)

# Frozen copy of the pre-YAML `_PRESETS` literal. This refactor must not move
# a single arm — if this fails, something in builtin.yaml drifted.
_FROZEN_LADDER = {
    "A1": dict(transport=Transport.MCP, discovery=Discovery.EAGER_ALL,
               invocation=Invocation.TOOL_CALL, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
    "A2": dict(transport=Transport.MCP, discovery=Discovery.META_TOOLS,
               invocation=Invocation.TOOL_CALL, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
    "B1": dict(transport=Transport.MCP, discovery=Discovery.EAGER_ALL,
               invocation=Invocation.TOOL_CALL,
               instructions=Instructions.SKILL_GENERATED_FLAT,
               confirmation=Confirmation.NONE),
    "B2": dict(transport=Transport.MCP, discovery=Discovery.META_TOOLS,
               invocation=Invocation.TOOL_CALL,
               instructions=Instructions.SKILL_GENERATED_FLAT,
               confirmation=Confirmation.NONE),
    "B1-auth": dict(transport=Transport.MCP, discovery=Discovery.EAGER_ALL,
                    invocation=Invocation.TOOL_CALL,
                    instructions=Instructions.SKILL_AUTHORED_FLAT,
                    confirmation=Confirmation.NONE),
    "B2-auth": dict(transport=Transport.MCP, discovery=Discovery.META_TOOLS,
                    invocation=Invocation.TOOL_CALL,
                    instructions=Instructions.SKILL_AUTHORED_FLAT,
                    confirmation=Confirmation.NONE),
    "C1": dict(transport=Transport.HTTP_REST, discovery=Discovery.DOCS,
               invocation=Invocation.SHELL, instructions=Instructions.DOCS_FLAT,
               confirmation=Confirmation.NONE),
    "C2": dict(transport=Transport.HTTP_REST, discovery=Discovery.DOCS,
               invocation=Invocation.SHELL,
               instructions=Instructions.DOCS_PROGRESSIVE,
               confirmation=Confirmation.NONE),
    "D1": dict(transport=Transport.MCP, discovery=Discovery.CODE_FS,
               invocation=Invocation.CODE, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
    "D2": dict(transport=Transport.MCP, discovery=Discovery.CODE_FS,
               invocation=Invocation.CODE,
               instructions=Instructions.SKILL_GENERATED_PROGRESSIVE,
               confirmation=Confirmation.NONE),
    "D2-auth": dict(transport=Transport.MCP, discovery=Discovery.CODE_FS,
                    invocation=Invocation.CODE,
                    instructions=Instructions.SKILL_AUTHORED_PROGRESSIVE,
                    confirmation=Confirmation.NONE),
    "D3": dict(transport=Transport.MCP, discovery=Discovery.META_TOOLS,
               invocation=Invocation.CODE,
               instructions=Instructions.SKILL_GENERATED_FLAT,
               confirmation=Confirmation.NONE),
    "E1": dict(transport=Transport.MCP, discovery=Discovery.RETRIEVAL,
               invocation=Invocation.TOOL_CALL, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
    "M1": dict(transport=Transport.MCP, discovery=Discovery.EAGER_ALL,
               invocation=Invocation.TOOL_CALL, instructions=Instructions.NONE,
               confirmation=Confirmation.MRTR,
               mcp_revision=McpRevision.R2026_07_28),
    "Z0": dict(transport=Transport.NONE, discovery=Discovery.NONE,
               invocation=Invocation.NONE, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
    "Z1": dict(transport=Transport.IN_PROCESS, discovery=Discovery.NONE,
               invocation=Invocation.NONE, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
}


def test_frozen_ladder() -> None:
    loaded = {name: dict(arm.axes) for name, arm in load_arms().items()}
    assert set(loaded) == set(_FROZEN_LADDER)
    for name, expected in _FROZEN_LADDER.items():
        assert loaded[name] == expected, f"{name} moved"


def test_builtin_yaml_exists() -> None:
    assert BUILTIN_YAML.is_file()


def test_extends_merges_one_axis() -> None:
    arms = load_arms(extra={
        "D2-terse": {
            "extends": "D2",
            "doc_budget": "terse",
            "allow_run_axes": True,
        }
    })
    assert arms["D2-terse"].axes["discovery"] is Discovery.CODE_FS
    assert arms["D2-terse"].axes["doc_budget"] is DocBudget.TERSE


def test_non_structural_pin_refused_without_flag() -> None:
    from harness.engine.axes import ConfigError
    with pytest.raises(ConfigError, match="non-structural"):
        load_arms(extra={"X": {"extends": "A1", "model": "gpt-x"}})


def test_unknown_key_refused() -> None:
    from harness.engine.axes import ConfigError
    with pytest.raises(ConfigError, match="unknown key"):
        load_arms(extra={"X": {"extends": "A1", "not_an_axis": "x"}})


def test_axes_table_covers_every_variant_field() -> None:
    """AST drift guard: every Variant field appears in AXES and vice versa."""
    skip = {"preset"}  # meta, not an axis
    variant_fields = set(Variant.__dataclass_fields__) - skip
    axis_names = {a.name for a in AXES}
    assert variant_fields == axis_names, (
        f"Variant−AXES={variant_fields - axis_names} "
        f"AXES−Variant={axis_names - variant_fields}"
    )


def test_axes_declaration_is_in_source() -> None:
    """House style: the table is data, not generated from Variant."""
    src = Path(__file__).resolve().parents[1] / "src/harness/engine/axes.py"
    tree = ast.parse(src.read_text())
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name):
                names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    assert "AXES" in names


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


def test_preset_still_builds_from_yaml() -> None:
    v = preset("B1-auth", **BASE)
    assert v.instructions is Instructions.SKILL_AUTHORED_FLAT
    assert v.discovery is Discovery.EAGER_ALL


def test_coerce_axis_value() -> None:
    assert coerce_axis_value("transport", "mcp") is Transport.MCP
    assert coerce_axis_value("surface_size", "50") == 50
