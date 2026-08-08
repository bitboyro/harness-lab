"""Variant axes and presets.

The axis assignment is the primitive; a preset is shorthand for a complete
assignment. Nothing is defaulted implicitly — a variant with an unset axis is a
config error, not a variant.

Contract: archive/reference/packaging-axes.md
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Self


class Transport(StrEnum):
    MCP = "mcp"
    HTTP_REST = "http-rest"
    IN_PROCESS = "in-process"
    NONE = "none"


class McpRevision(StrEnum):
    R2026_07_28 = "2026-07-28"
    LEGACY = "legacy"


class Discovery(StrEnum):
    EAGER_ALL = "eager-all"
    META_TOOLS = "meta-tools"
    CODE_FS = "code-fs"
    RETRIEVAL = "retrieval"
    DOCS = "docs"
    NONE = "none"


class Invocation(StrEnum):
    """Three-way, not two.

    ``SHELL`` is freehand curl against written docs (the C arms). ``CODE`` is
    writing program code against a generated module tree, where intermediate
    results stay in the sandbox (the D arms). Conflating them would merge the
    two arms and hide the mechanism each one tests.
    """

    TOOL_CALL = "tool-call"
    SHELL = "shell"
    CODE = "code"
    NONE = "none"


class Instructions(StrEnum):
    NONE = "none"
    SKILL_GENERATED_FLAT = "skill-generated-flat"
    SKILL_GENERATED_PROGRESSIVE = "skill-generated-progressive"
    SKILL_AUTHORED_FLAT = "skill-authored-flat"
    SKILL_AUTHORED_PROGRESSIVE = "skill-authored-progressive"
    DOCS_FLAT = "docs-flat"
    DOCS_PROGRESSIVE = "docs-progressive"

    @property
    def is_authored(self) -> bool:
        """Authored and generated skill results are never pooled (V9)."""
        return self.value.startswith("skill-authored")


class Confirmation(StrEnum):
    NONE = "none"
    MRTR = "mrtr"


class SchemaDetail(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    RICH = "rich"


class ResponseShape(StrEnum):
    AS_IS = "as-is"
    SPARSE = "sparse"
    BUDGETED = "budgeted"


class ErrorDetail(StrEnum):
    TERSE = "terse"
    FIELD_SCOPED = "field-scoped"
    FIELD_SCOPED_REMEDY = "field-scoped+remedy"


class DocBudget(StrEnum):
    """Swept, never equalized. V2 was dropped; see decisions.md G5."""

    TERSE = "terse"
    STANDARD = "standard"
    VERBOSE = "verbose"


class Caching(StrEnum):
    ON = "on"
    OFF = "off"
    LIST_CACHEABLE = "list-cacheable"  # protocol-level ttlMs/cacheScope


class ConfigError(ValueError):
    """A variant that cannot be run as specified."""


@dataclass(frozen=True, slots=True)
class Variant:
    """A complete axis assignment.

    Every field is required. There are no defaults here on purpose: an
    unset ``reasoning_effort`` silently benchmarks effort levels instead of
    packaging (V3), and the same failure mode applies to every other axis.
    Defaults belong in a run plan's ``base``, where they are written down.
    """

    transport: Transport
    discovery: Discovery
    invocation: Invocation
    instructions: Instructions
    confirmation: Confirmation
    schema_detail: SchemaDetail
    response_shape: ResponseShape
    error_detail: ErrorDetail
    doc_budget: DocBudget
    surface_size: int
    model: str
    reasoning_effort: str
    temperature: float
    caching: Caching
    repeats: int
    mcp_revision: McpRevision | None = None
    preset: str | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.transport is Transport.MCP and self.mcp_revision is None:
            raise ConfigError(
                "mcp_revision is required when transport is 'mcp' — results are "
                "never pooled across revisions (V10), so it cannot be inferred."
            )
        if self.transport is not Transport.MCP and self.mcp_revision is not None:
            raise ConfigError(
                f"mcp_revision is meaningless for transport {self.transport!r}; "
                "leave it unset."
            )
        if self.confirmation is Confirmation.MRTR and self.mcp_revision is not McpRevision.R2026_07_28:
            raise ConfigError(
                "confirmation 'mrtr' requires mcp_revision '2026-07-28' — MRTR "
                "does not exist in the legacy revision."
            )
        if self.discovery is Discovery.CODE_FS and self.invocation is not Invocation.CODE:
            raise ConfigError(
                "discovery 'code-fs' presents an importable module tree; it "
                "requires invocation 'code'."
            )
        if self.surface_size < 0:
            raise ConfigError("surface_size must be non-negative")
        if self.repeats < 1:
            raise ConfigError("repeats must be at least 1")

    def derive(self, **overrides: Any) -> Self:
        """A copy with axes overridden, re-validated."""
        return replace(self, **overrides)

    @property
    def pool_key(self) -> tuple[str, ...]:
        """Axes across which results must never be pooled.

        Enforced by the report layer. Two runs with different pool keys
        describe different worlds and averaging them is meaningless.
        """
        return (
            str(self.mcp_revision or "n/a"),
            "authored" if self.instructions.is_authored else "generated",
            self.model,
        )


#: What each axis value means in plain words. The report renders arm
#: descriptions from these rather than from a hand-written blurb per preset:
#: a blurb drifts the moment a preset changes, and the whole point of the
#: orthogonal axes is that the assignment IS the description.
_MEANING = {
    "discovery": {
        Discovery.EAGER_ALL: "every operation schema loaded upfront",
        Discovery.META_TOOLS: "3 meta-tools (search/describe/invoke); schemas on demand",
        Discovery.CODE_FS: "operations as an importable module tree, read on demand",
        Discovery.RETRIEVAL: "top-k operations retrieved for it; it never asks",
        Discovery.DOCS: "a written API reference",
        Discovery.NONE: "nothing to discover",
    },
    "invocation": {
        Invocation.TOOL_CALL: "calls them as native tools",
        Invocation.SHELL: "writes bash and curls the API",
        Invocation.CODE: "writes code in a sandbox; intermediate results stay there",
        Invocation.NONE: "makes no calls",
    },
    "instructions": {
        Instructions.NONE: "no skill or docs",
        Instructions.SKILL_GENERATED_FLAT: "+ a generated skill (mechanical, from the spec)",
        Instructions.SKILL_GENERATED_PROGRESSIVE: "+ a generated skill, progressive",
        Instructions.SKILL_AUTHORED_FLAT: "+ the AUTHORED skill (hand-written)",
        Instructions.SKILL_AUTHORED_PROGRESSIVE: "+ the AUTHORED skill, progressive",
        Instructions.DOCS_FLAT: "+ the full written reference",
        Instructions.DOCS_PROGRESSIVE: "+ an index, details on demand",
    },
    "confirmation": {
        Confirmation.MRTR: "; the server asks before destructive operations",
        Confirmation.NONE: "",
    },
}

#: Why each control exists. Controls are not packaging choices, so describing
#: them by their axes alone would be true and useless.
_CONTROL_ROLE = {
    "Z0": "CONTROL — no tools at all. Measures what the model already knows, "
          "so every other arm is read as lift over this.",
    "Z1": "CEILING — the correct API responses are pre-fetched and handed over. "
          "Shows what is achievable when packaging is not the obstacle. "
          "Read tasks only: with no tools it cannot perform a write.",
}

#: The controls' short names. Same reason as `_CONTROL_ROLE`: "no transport:
#: nothing to discover" is accurate and tells a reader nothing.
_CONTROL_NAME = {
    "Z0": "No tools",
    "Z1": "Answers handed over",
}

#: Short-name fragments, one per axis value. Deliberately parallel to `_MEANING`
#: — the long description and the short name are two renderings of the same
#: assignment, and neither is written down per preset.
_NAME_PART = {
    "transport": {
        Transport.MCP: "MCP",
        Transport.HTTP_REST: "Bash",
        Transport.IN_PROCESS: "In-process",
        Transport.NONE: "No tools",
    },
    "discovery": {
        Discovery.EAGER_ALL: ", all tools",
        Discovery.META_TOOLS: ", discovery",
        Discovery.CODE_FS: " sandbox",
        Discovery.RETRIEVAL: ", retrieved",
        Discovery.DOCS: "",
        Discovery.NONE: "",
    },
    "instructions": {
        Instructions.NONE: "",
        Instructions.SKILL_GENERATED_FLAT: " + skill",
        Instructions.SKILL_GENERATED_PROGRESSIVE: " + skill",
        Instructions.SKILL_AUTHORED_FLAT: " + authored skill",
        Instructions.SKILL_AUTHORED_PROGRESSIVE: " + authored skill",
        Instructions.DOCS_FLAT: " + docs",
        Instructions.DOCS_PROGRESSIVE: " + index",
    },
    "confirmation": {
        Confirmation.MRTR: " + confirm",
        Confirmation.NONE: "",
    },
}


def short_name(variant: Variant) -> str:
    """Two or three words for an arm, for use beside its code.

    Derived from the axes for the same reason `describe` is: a hand-written name
    per preset drifts the moment the preset changes, and then a chart is labelled
    with something the run was not. `A1` on its own is unreadable; `A1 · MCP, all
    tools` needs no legend.
    """
    if variant.preset in _CONTROL_NAME:
        return _CONTROL_NAME[variant.preset]

    # `code-fs` names the transport after what the model actually touches: the
    # module tree, not the MCP server behind it.
    head = ("Code" if variant.invocation is Invocation.CODE
            else _NAME_PART["transport"][variant.transport])
    return (head
            + _NAME_PART["discovery"][variant.discovery]
            + _NAME_PART["instructions"][variant.instructions]
            + _NAME_PART["confirmation"][variant.confirmation])


def describe(variant: Variant) -> str:
    """One sentence for an arm, built from its axis assignment.

    Derived, never written down twice: if a preset changes, this changes with
    it, and a report can never describe an arm as something it was not.
    """
    if variant.preset in _CONTROL_ROLE:
        return _CONTROL_ROLE[variant.preset]

    transport = {
        Transport.MCP: "MCP",
        Transport.HTTP_REST: "HTTP",
        Transport.IN_PROCESS: "in-process",
        Transport.NONE: "no transport",
    }[variant.transport]

    parts = [
        f"{transport}: {_MEANING['discovery'][variant.discovery]}",
        _MEANING["invocation"][variant.invocation],
    ]
    instructions = _MEANING["instructions"][variant.instructions]
    if instructions:
        parts.append(instructions)
    return ", ".join(parts) + _MEANING["confirmation"][variant.confirmation]


def axis_summary(variant: Variant) -> dict[str, str]:
    """The assignment itself, for the ledger. What ran, not what a name implies."""
    return {
        "transport": str(variant.transport),
        "mcp_revision": str(variant.mcp_revision) if variant.mcp_revision else "",
        "discovery": str(variant.discovery),
        "invocation": str(variant.invocation),
        "instructions": str(variant.instructions),
        "confirmation": str(variant.confirmation),
        "schema_detail": str(variant.schema_detail),
        "response_shape": str(variant.response_shape),
        "error_detail": str(variant.error_detail),
        "doc_budget": str(variant.doc_budget),
        "surface_size": str(variant.surface_size),
        "description": describe(variant),
        "name": short_name(variant),
    }


# Partial axis assignments. Structural axes only — affordance and run axes come
# from the run plan's `base`, so a preset never silently pins them.
_PRESETS: dict[str, dict[str, Any]] = {
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
               confirmation=Confirmation.MRTR, mcp_revision=McpRevision.R2026_07_28),
    "Z0": dict(transport=Transport.NONE, discovery=Discovery.NONE,
               invocation=Invocation.NONE, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
    "Z1": dict(transport=Transport.IN_PROCESS, discovery=Discovery.NONE,
               invocation=Invocation.NONE, instructions=Instructions.NONE,
               confirmation=Confirmation.NONE),
}

PRESET_NAMES = tuple(_PRESETS)


def preset(name: str, **base: Any) -> Variant:
    """Build a Variant from a preset name plus the run plan's base axes.

    ``base`` supplies the affordance and run axes. A preset never pins those —
    they belong to the comparison, not to the packaging method.
    """
    if name not in _PRESETS:
        raise ConfigError(f"unknown preset {name!r}; known: {', '.join(PRESET_NAMES)}")
    fields = {**_PRESETS[name], **base, "preset": name}
    # Presets that do not use MCP must not inherit a revision from `base`.
    if fields.get("transport") is not Transport.MCP:
        fields.pop("mcp_revision", None)
    try:
        return Variant(**fields)
    except TypeError as e:
        raise ConfigError(f"preset {name!r} is missing base axes: {e}") from e
