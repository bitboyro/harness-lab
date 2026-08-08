"""Draft a task pack from a surface, so nobody starts from an empty file.

Authoring twenty graded tasks by hand is the step people quit on. Everything
mechanical about a pack — its shape, one stub per operation, the safety block,
the unanswerable share — can be derived from the surface itself, leaving the
author the part that actually needs a human: what the right answer is.

What this deliberately does **not** do is invent expectations. Every generated
task carries a `TODO` prompt and no grader, so a pack straight out of scaffold
loads and runs but grades nothing. A stub that quietly asserted something
plausible would be worse than an empty file: it would look finished.

Contract: docs/design-your-test-run.md
"""

from __future__ import annotations

import re
from typing import Any

from .engine.generate import ApiSpec, Operation

#: Verbs that make an operation a candidate for `forbidden_calls`. Matched on
#: the operation id and the HTTP method, never on prose: a description saying
#: "this does not delete anything" must not arm the filter.
_DESTRUCTIVE = re.compile(
    r"(^|_)(delete|destroy|remove|purge|drop|truncate|revoke|cancel|"
    r"terminate|reset|wipe|erase|archive)(_|$)", re.I,
)

#: The share of tasks that should have no valid answer. Below this a pack
#: cannot measure fabrication at all, which is half of what an agent gets
#: wrong on a real API.
UNANSWERABLE_SHARE = 0.15


#: Names that suggest an operation changes something. Only consulted for MCP
#: surfaces, where the HTTP verb carries no information (see `is_read`).
_MUTATING = re.compile(
    r"(^|_)(create|add|insert|update|patch|edit|modify|set|put|replace|write|"
    r"send|submit|post|upload|import|report|trigger|run|execute|apply|"
    r"approve|assign|move|rename|publish)(_|$)", re.I,
)


#: Prefixes that make an operation a read regardless of what follows.
_READ_PREFIX = re.compile(
    r"^(get|list|search|find|fetch|read|show|describe|query|lookup|"
    r"count|check|view|browse|export)(_|$)", re.I,
)


def is_destructive(op: Operation) -> bool:
    return bool(_DESTRUCTIVE.search(op.operation_id or "")) or (
        (op.method or "").upper() == "DELETE"
    )


def is_read(op: Operation, *, source: str = "") -> bool:
    """Whether this operation only reads.

    An MCP surface has no verbs to go on — `spec_from_tools` stamps every tool
    `POST` because MCP has no paths or methods, so trusting the verb there
    classifies the entire server as writes and scaffolds an empty pack. For MCP
    the name is the only evidence available, so it is what gets used.
    """
    name = op.operation_id or ""
    if source == "mcp":
        # A read prefix wins outright. `get_knowledge_base_report` is a read
        # whose *noun* happens to be a mutating verb, and guessing wrong here
        # costs a whole operation's worth of tasks — the pack ends up smaller
        # and quieter than the surface it was drawn from.
        if _READ_PREFIX.match(name):
            return True
        return not (_MUTATING.search(name) or is_destructive(op))
    return (op.method or "get").upper() in {"GET", "HEAD", "OPTIONS"}


def _task(op: Operation, index: int, task_class: str = "R") -> dict[str, Any]:
    """One stub. Unfilled by design — see the module docstring."""
    name = op.operation_id or f"op-{index}"
    return {
        "id": f"{name}-1",
        # Kept as a TODO rather than a generated question: a question invented
        # from a schema tests whether the model can read the schema back, which
        # is the one thing every arm can do.
        "prompt": f"TODO: ask something only answerable via {name}. "
                  f"({op.method.upper()} {op.path})",
        "core_id": name,
        "class": task_class,
        "answerable": True,
        "harm_tier": 2 if is_destructive(op) else 0,
        "grade": [],  # TODO: add a deterministic check — equals/contains/regex/jsonpath
        "gold_call_sequence": [{"tool": name}],
    }


def _unanswerable(index: int) -> dict[str, Any]:
    return {
        "id": f"unanswerable-{index}",
        "prompt": "TODO: ask for something this API genuinely cannot supply.",
        "core_id": f"unanswerable-{index}",
        "class": "R",
        "answerable": False,
        "unanswerable_because": "TODO: say why no call sequence can answer it.",
        "harm_tier": 0,
        "grade": [],
    }


def build(spec: ApiSpec, *, pack_id: str, mcp_url: str | None = None,
          openapi: str | None = None) -> dict[str, Any]:
    """A pack skeleton for this surface. Valid YAML, deliberately ungraded."""
    operations = list(spec.operations)

    # Reads only. A generated pack has to be safe to run the moment it is
    # written, and `writes_enabled: false` plus a mutating task is a pack the
    # schema refuses to load — correctly. Write coverage is a deliberate
    # second step against a staging target, not something to default into.
    readable = [op for op in operations if is_read(op, source=spec.source)]
    skipped = len(operations) - len(readable)

    # Every operation this pack does not exercise is also one it must not reach
    # by accident. Leaving a write merely *untasked* still lets an arm find it
    # and call it; naming it here turns that from an unnoticed mutation into a
    # recorded harm event, which on a live API is the only evidence available.
    forbidden = sorted(op.operation_id for op in operations
                       if op not in readable and op.operation_id)

    tasks = [_task(op, i) for i, op in enumerate(readable)]
    # Sized against the real task count, not a fixed number, so a small surface
    # still gets at least one.
    filler = max(1, round(len(tasks) * UNANSWERABLE_SHARE / (1 - UNANSWERABLE_SHARE)))
    tasks += [_unanswerable(i) for i in range(filler)]

    api: dict[str, Any] = {"auth": {"type": "none"}}
    if mcp_url:
        api["mcp"] = {"url": mcp_url, "spec_revision": "auto"}
    if openapi:
        api["openapi"] = openapi
    # Required by the schema even for a read-only MCP pack: the C/D arms shell
    # out and need somewhere to read the base URL from.
    api["base_url_env"] = "TARGET_BASE_URL"

    return {
        "schema_version": 1,
        "pack": {
            "id": pack_id,
            "description": (
                f"TODO: describe this target. Generated from {len(readable)} "
                f"read operations; every task below is a stub."
                + (f" {skipped} write operations were skipped — add them "
                   f"deliberately against a staging target." if skipped else "")
            ),
            # Never `controlled`: contamination is uncontrolled on a real API,
            # so every number here is lift over Z0 and must be labelled as such.
            "report_class": "field",
        },
        "api": api,
        "safety": {
            "writes_enabled": False,
            # On a real API an attempted call is the entire harm signal —
            # state cannot be diffed, so intent is all there is to record.
            "forbidden_calls": forbidden,
        },
        "isolation": {"mode": "none"},
        "tasks": tasks,
    }


def to_yaml(pack: dict[str, Any]) -> str:
    import yaml

    header = (
        "# Generated by `harness scaffold`. Every task is a stub:\n"
        "#   1. replace each TODO prompt with a question only your API answers\n"
        "#   2. add a deterministic `grade` to each — no grader means no result\n"
        "#   3. check `forbidden_calls` caught every destructive operation\n"
        "#\n"
        "# Then: harness run --pack this.yaml --probe --presets Z0 A1\n\n"
    )
    return header + yaml.safe_dump(pack, sort_keys=False, width=88,
                                   allow_unicode=True)
