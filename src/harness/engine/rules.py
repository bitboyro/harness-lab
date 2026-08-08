"""T1 lint rules: the agent-readiness scorecard.

Each rule is the reverse of a metric we plan to measure. That is deliberate — it
is what makes the back-fill possible: when the controlled rig produces an effect
size, the corresponding rule gets a ``justified_by`` citation and stops being
opinion.

**Every rule below currently has an empty ``justified_by``.** They therefore
render as ``heuristic``, and the scorecard footer says so. That is the honest
state, not an oversight: nothing has been measured yet. Filling these in is the
work of P4, and a rule that never earns a citation should be deleted rather than
quietly kept.

Contract: archive/reference/decisions.md G2
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from .generate import ApiSpec, Operation
from .lint import Finding, Rule, Severity, register

#: Above this many operations, an eager-all surface is where selection accuracy
#: is predicted to degrade (P3). The number is a hypothesis until measured.
DISCOVERY_THRESHOLD = 15


def _f(rule_id: str, severity: Severity, message: str, location: str | None = None) -> Finding:
    # Confidence is overwritten by the Rule from its justified_by; passing
    # HEURISTIC here keeps the check functions from having to know.
    from .lint import Confidence
    return Finding(rule_id, severity, Confidence.HEURISTIC, message, location)


def _missing_descriptions(spec: ApiSpec) -> Iterable[Finding]:
    for op in spec.operations:
        if not (op.summary or op.description).strip():
            yield _f("no-description", Severity.HIGH,
                     f"{op.operation_id} has no summary or description — an agent "
                     "selecting between operations has only the name to go on.",
                     op.signature)


def _undescribed_parameters(spec: ApiSpec) -> Iterable[Finding]:
    for op in spec.operations:
        bare = [p["name"] for p in op.parameters
                if p.get("name") and not p.get("description")]
        if bare:
            yield _f("undescribed-parameter", Severity.MEDIUM,
                     f"{op.operation_id}: parameters {bare} have no description. "
                     "Argument-validity failures cluster on parameters an agent "
                     "has to guess the format of.",
                     op.signature)


def _name_collisions(spec: ApiSpec) -> Iterable[Finding]:
    def normal(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    counts = Counter(normal(op.operation_id) for op in spec.operations)
    for op in spec.operations:
        if counts[normal(op.operation_id)] > 1:
            yield _f("name-collision", Severity.HIGH,
                     f"{op.operation_id} is near-identical to another operation "
                     "once case and separators are ignored. Confusable names are "
                     "a direct cause of wrong-operation selection.",
                     op.signature)


def _unbounded_collections(spec: ApiSpec) -> Iterable[Finding]:
    paged = {"page", "per_page", "limit", "offset", "cursor", "page_size",
             "topk", "top_k", "max_results", "count"}
    for op in spec.operations:
        # On MCP everything is a POST, so the HTTP verb cannot identify a
        # collection. Fall back to the name, which is what an agent reads too.
        looks_like_list = (op.operation_id.startswith(("list_", "search_"))
                           if spec.source == "mcp"
                           else op.method == "get"
                           and "{" not in op.path.rsplit("/", 1)[-1])
        if not looks_like_list:
            continue
        names = {str(p.get("name", "")).lower() for p in op.parameters}
        if not (names & paged):
            yield _f("unbounded-collection", Severity.HIGH,
                     f"{op.operation_id} returns a collection with no pagination "
                     "parameter. An unbounded response is the fastest way to fill "
                     "an agent's context with data it did not ask for.",
                     op.signature)


def _untyped_errors(spec: ApiSpec) -> Iterable[Finding]:
    if spec.source == "mcp":
        # MCP has no equivalent of an OpenAPI responses block, so this would
        # fire on every tool of every server — 24 identical findings that no
        # owner can act on, drowning the ones they can.
        return
    for op in spec.operations:
        codes = [c for c in op.responses if c.startswith(("4", "5"))]
        if not codes:
            yield _f("untyped-errors", Severity.MEDIUM,
                     f"{op.operation_id} documents no error responses. An agent "
                     "that cannot predict the failure shape cannot recover from "
                     "it in one turn.",
                     op.signature)
            continue
        vague = [c for c in codes
                 if not op.responses[c].get("description", "").strip()]
        if vague:
            yield _f("undescribed-errors", Severity.MEDIUM,
                     f"{op.operation_id}: error responses {vague} have no "
                     "description. 'validation failed' costs a retry; naming the "
                     "field and expected format usually costs none.",
                     op.signature)


def _no_discovery_layer(spec: ApiSpec) -> Iterable[Finding]:
    n = len(spec.operations)
    if n > DISCOVERY_THRESHOLD:
        yield _f("no-discovery-layer", Severity.HIGH,
                 f"{n} operations exposed with no discovery mechanism. Above "
                 f"~{DISCOVERY_THRESHOLD} operations, loading every schema "
                 "upfront is predicted to cost both context and selection "
                 "accuracy — consider a search/describe/invoke layer.")


def _ambiguous_mutation_routes(spec: ApiSpec) -> Iterable[Finding]:
    """Several routes to the same change, with different blast radii.

    This is the harm-asymmetry probe pointed at a real API: PUT silently drops
    unspecified fields, an action endpoint may be irreversible, and nothing in
    the schema says which one the caller meant.
    """
    if spec.source == "mcp":
        return  # no HTTP verbs to be ambiguous between
    by_resource: dict[str, list[Operation]] = {}
    for op in spec.operations:
        if not op.is_mutation:
            continue
        resource = re.sub(r":[a-z]+$", "", op.path)
        by_resource.setdefault(resource, []).append(op)

    for resource, ops in by_resource.items():
        methods = {o.method.upper() for o in ops}
        if len(methods) < 2:
            continue
        risky = []
        if "PUT" in methods:
            risky.append("PUT replaces the whole object and drops unspecified fields")
        if any(":" in o.path for o in ops):
            risky.append("an action endpoint may be irreversible")
        if risky:
            yield _f("ambiguous-mutation-route", Severity.HIGH,
                     f"{resource} is mutable via {sorted(methods)}. "
                     + "; ".join(risky)
                     + ". Say so in the descriptions, or an agent will pick by name alone.",
                     resource)


def _no_idempotency(spec: ApiSpec) -> Iterable[Finding]:
    if spec.source == "mcp":
        return  # every MCP tool is a POST; the rule would fire on all of them
    for op in spec.operations:
        if op.method != "post":
            continue
        names = {str(p.get("name", "")).lower() for p in op.parameters}
        if not any("idempot" in n for n in names):
            yield _f("no-idempotency-key", Severity.LOW,
                     f"{op.operation_id} accepts no idempotency key, so a retried "
                     "write cannot be distinguished from an intended second one.",
                     op.signature)


def register_defaults() -> None:
    """Register the built-in T1 rules. Idempotent."""
    from .lint import _REGISTRY
    definitions = [
        ("no-description", Severity.HIGH, "Operations need a summary", _missing_descriptions),
        ("undescribed-parameter", Severity.MEDIUM, "Parameters need descriptions", _undescribed_parameters),
        ("name-collision", Severity.HIGH, "Confusable operation names", _name_collisions),
        ("unbounded-collection", Severity.HIGH, "Collections need pagination", _unbounded_collections),
        ("untyped-errors", Severity.MEDIUM, "Errors need shapes", _untyped_errors),
        ("no-discovery-layer", Severity.HIGH, "Large surfaces need discovery", _no_discovery_layer),
        ("ambiguous-mutation-route", Severity.HIGH, "Multiple routes, different harm", _ambiguous_mutation_routes),
        ("no-idempotency-key", Severity.LOW, "Retries are indistinguishable", _no_idempotency),
    ]
    for rule_id, severity, summary, check in definitions:
        if rule_id in _REGISTRY:
            continue
        register(Rule(
            id=rule_id,
            severity=severity,
            summary=summary,
            check=check,
            # Empty on purpose. See the module docstring.
            justified_by=(),
        ))
