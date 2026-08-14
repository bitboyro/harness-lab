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
class Axis:
    """One dimension of the variant space.

    Declared once so ``axis_summary``, the CLI flag block, the arm loader and
    the run-plan validator read the same table. ``Variant`` stays an explicit
    dataclass — every field required on purpose (V3) — and an AST test asserts
    the two stay in lockstep.
    """

    name: str
    enum: type[StrEnum] | None  # None for scalars (surface_size, model, …)
    group: str  # structural | affordance | run
    structural: bool = False  # may a shipped arm pin it?
    cli_flag: str | None = None


AXES: tuple[Axis, ...] = (
    Axis("transport", Transport, "structural", structural=True),
    Axis("discovery", Discovery, "structural", structural=True),
    Axis("invocation", Invocation, "structural", structural=True),
    Axis("instructions", Instructions, "structural", structural=True),
    Axis("confirmation", Confirmation, "structural", structural=True),
    Axis("mcp_revision", McpRevision, "structural", structural=True,
         cli_flag="--mcp-revision"),
    Axis("schema_detail", SchemaDetail, "affordance",
         cli_flag="--schema-detail"),
    Axis("response_shape", ResponseShape, "affordance",
         cli_flag="--response-shape"),
    Axis("error_detail", ErrorDetail, "affordance",
         cli_flag="--error-detail"),
    Axis("doc_budget", DocBudget, "affordance", cli_flag="--doc-budget"),
    Axis("surface_size", None, "affordance", cli_flag="--surface-size"),
    Axis("model", None, "run", cli_flag="--model"),
    Axis("reasoning_effort", None, "run", cli_flag="--reasoning-effort"),
    Axis("temperature", None, "run", cli_flag="--temperature"),
    Axis("caching", Caching, "run", cli_flag="--caching"),
    Axis("repeats", None, "run", cli_flag="--repeats"),
)


def axis_by_name(name: str) -> Axis | None:
    for axis in AXES:
        if axis.name == name:
            return axis
    return None


def coerce_axis_value(name: str, value: Any) -> Any:
    """Parse a YAML/CLI string into the typed axis value."""
    axis = axis_by_name(name)
    if axis is None:
        raise ConfigError(f"unknown axis {name!r}")
    if value is None:
        return None
    # PyYAML turns bare 2026-07-28 into a date; MCP revisions are strings.
    if hasattr(value, "isoformat") and not isinstance(value, str):
        value = value.isoformat()
    if axis.enum is not None:
        return axis.enum(value)
    if name in ("surface_size", "repeats"):
        return int(value)
    if name == "temperature":
        return float(value)
    return value


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
    "Z-cheat": "PROBE — docs that name a path to the gold pack. Sibling of Z1: "
               "answers are not handed over, only located. Never confirmatory, "
               "never a winner; axis-identical to C1 without this label.",
}

#: The controls' short names. Same reason as `_CONTROL_ROLE`: "no transport:
#: nothing to discover" is accurate and tells a reader nothing.
_CONTROL_NAME = {
    "Z0": "No tools",
    "Z1": "Answers handed over",
    "Z-cheat": "Docs bait / path-to-answers",
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


def split_label(arm: str) -> tuple[str, dict[str, str]]:
    """Parse an arm label into ``(base, {axis: value, …})``.

    Canonical form is ``A1@error_detail=terse,doc_budget=verbose``. The bare
    legacy form ``A1@terse`` could only ever have meant ``error_detail``, so
    that axis is inferred rather than guessed. Material-matrix cells use the
    same grammar (``D-lib@skill=catalog-v2,helpers=walk_a``).
    """
    if "@" not in arm:
        return arm, {}
    base, rest = arm.split("@", 1)
    if not rest:
        return base, {}
    overrides: dict[str, str] = {}
    if "=" not in rest and "," not in rest:
        # Legacy sweep label: only error_detail was ever swept this way.
        overrides["error_detail"] = rest
        return base, overrides
    for part in rest.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ConfigError(
                f"arm label {arm!r}: sweep/matrix part {part!r} is missing '='. "
                f"Use AXIS=value (or the legacy bare form ARM@terse for "
                f"error_detail only)."
            )
        axis, value = part.split("=", 1)
        overrides[axis.strip()] = value.strip()
    return base, overrides


def format_label(base: str, overrides: dict[str, str], *, axis_order: tuple[str, ...] = ()) -> str:
    """Build a deterministic arm label. Axes follow ``axis_order`` when given."""
    if not overrides:
        return base
    keys = [k for k in axis_order if k in overrides] if axis_order else sorted(overrides)
    keys.extend(k for k in sorted(overrides) if k not in keys)
    # Single bare legacy form when the only override is error_detail — kept so
    # new runs still round-trip through older readers that only split on '@'.
    if keys == ["error_detail"] and axis_order == ():
        return f"{base}@{overrides['error_detail']}"
    body = ",".join(f"{k}={overrides[k]}" for k in keys)
    return f"{base}@{body}"


# Loaded once from engine/arms/builtin.yaml. The dict shape matches the old
# in-code `_PRESETS` literal so the frozen-ladder equality test can prove this
# refactor did not move a single arm.
_PRESETS: dict[str, dict[str, Any]] | None = None
_EXTRA_ARMS: dict[str, dict[str, Any]] = {}
#: Material bindings (skill/helpers/docs/target) keyed by arm name. Kept
#: beside the axes table rather than inside it — ``preset()`` still returns a
#: Variant, and materials are artifacts, not axes.
_BUILTIN_MATERIALS: dict[str, dict[str, str]] = {}
_EXTRA_MATERIALS: dict[str, dict[str, str]] = {}


def _ensure_presets() -> dict[str, dict[str, Any]]:
    global _PRESETS
    if _PRESETS is None:
        from .armspec import load_arms
        loaded = load_arms()
        _PRESETS = {name: dict(arm.axes) for name, arm in loaded.items()}
        _BUILTIN_MATERIALS.clear()
        for name, arm in loaded.items():
            if arm.materials:
                _BUILTIN_MATERIALS[name] = dict(arm.materials)
    return {**_PRESETS, **_EXTRA_ARMS}


def register_plan_arms(extra: dict[str, Any]) -> None:
    """Merge plan-declared arms into the lookup used by ``preset()``.

    Axes and materials both stick. Dropping materials here was the silent
    failure mode: a plan ``skill:`` binding parsed and validated, then the
    run used the default skill resolution anyway.
    """
    from .armspec import load_arms
    global _EXTRA_ARMS, _EXTRA_MATERIALS
    _ensure_presets()
    loaded = load_arms(extra=extra)
    builtin_names = set(_PRESETS or {})
    _EXTRA_ARMS = {}
    _EXTRA_MATERIALS = {}
    for name, arm in loaded.items():
        if name not in builtin_names or name in extra:
            _EXTRA_ARMS[name] = dict(arm.axes)
            if arm.materials:
                _EXTRA_MATERIALS[name] = dict(arm.materials)


def arm_materials(arm: str) -> dict[str, str]:
    """Material bindings for an arm label (exact matrix cell, then base name)."""
    _ensure_presets()
    base, _ = split_label(arm)
    for key in (arm, base):
        if key in _EXTRA_MATERIALS:
            return dict(_EXTRA_MATERIALS[key])
        if key in _BUILTIN_MATERIALS:
            return dict(_BUILTIN_MATERIALS[key])
    return {}


def builtin_arm_names() -> tuple[str, ...]:
    _ensure_presets()
    assert _PRESETS is not None
    return tuple(_PRESETS)


def _preset_names() -> tuple[str, ...]:
    return tuple(_ensure_presets())


class _PresetNames:
    """Lazy stand-in for the old ``PRESET_NAMES`` tuple."""

    def __iter__(self):
        return iter(_preset_names())

    def __contains__(self, item: object) -> bool:
        return item in _ensure_presets()

    def __len__(self) -> int:
        return len(_ensure_presets())

    def __getitem__(self, idx):
        return _preset_names()[idx]


PRESET_NAMES = _PresetNames()  # type: ignore[assignment]


def preset(name: str, **base: Any) -> Variant:
    """Build a Variant from a preset name plus the run plan's base axes.

    ``base`` supplies the affordance and run axes. A preset never pins those —
    they belong to the comparison, not to the packaging method. Lookup is the
    YAML arm table (plus any plan-registered arms), not a Python dict literal.
    """
    presets = _ensure_presets()
    base_name, label_overrides = split_label(name)
    # Prefer the exact label when it was registered (material-matrix cells
    # live under the full ``Name@skill=…`` key). Fall back to the base so
    # sweep labels like ``A1@error_detail=terse`` still resolve to A1's axes.
    lookup = name if name in presets else base_name if base_name in presets else name
    if lookup not in presets:
        known = ", ".join(presets)
        raise ConfigError(f"unknown preset {name!r}; known: {known}")
    fields = {**presets[lookup], **base, "preset": lookup}
    for axis, value in label_overrides.items():
        if axis_by_name(axis) is not None:
            fields[axis] = coerce_axis_value(axis, value)
    # Presets that do not use MCP must not inherit a revision from `base`.
    if fields.get("transport") is not Transport.MCP:
        fields.pop("mcp_revision", None)
    variant_fields = set(Variant.__dataclass_fields__)
    fields = {k: v for k, v in fields.items() if k in variant_fields}
    try:
        return Variant(**fields)
    except TypeError as e:
        raise ConfigError(f"preset {name!r} is missing base axes: {e}") from e
