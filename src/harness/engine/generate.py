"""Material generators: one OpenAPI spec in, every arm's materials out.

This module *is* validity control V1. Every arm's materials come from the same
spec by the same mechanical process, so no arm can be quietly favoured by better
prose. What V1 does not do — and what V2 wrongly tried to do — is equalise
length: static context size is a real causal property of the packaging choice,
so it is measured and swept (``doc_budget``), never padded to parity.

Contract: archive/reference/decisions.md G5; archive/reference/experiment-design.md#validity-controls
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .axes import DocBudget, ErrorDetail, SchemaDetail, Variant
from .packaging import ContextBlock, Materials, Provenance, ToolDef

_HTTP_METHODS = ("get", "put", "post", "patch", "delete")


@dataclass(frozen=True, slots=True)
class Operation:
    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    parameters: tuple[dict[str, Any], ...]
    request_body: dict[str, Any] | None
    responses: dict[str, Any]

    @property
    def is_mutation(self) -> bool:
        return self.method.upper() != "GET"

    @property
    def signature(self) -> str:
        return f"{self.method.upper()} {self.path}"


@dataclass(frozen=True, slots=True)
class ApiSpec:
    """A parsed OpenAPI 3.1 document — the single source of truth (L2)."""

    title: str
    version: str
    operations: tuple[Operation, ...]
    raw: dict[str, Any]
    #: "openapi" or "mcp". Some lint rules describe HTTP conventions that an
    #: MCP surface has no way to express — firing them on every tool would bury
    #: the real findings under noise the owner cannot act on.
    source: str = "openapi"

    def limited_to(self, surface_size: int) -> ApiSpec:
        """Expose the first N operations.

        Ordering is the spec's own, so the surface-size sweep adds distractors
        in a stable order rather than resampling a different API at each size.
        """
        if surface_size <= 0 or surface_size >= len(self.operations):
            return self
        return ApiSpec(self.title, self.version, self.operations[:surface_size],
                       self.raw, self.source)

    def by_id(self, operation_id: str) -> Operation | None:
        return next((o for o in self.operations if o.operation_id == operation_id), None)

    def defines(self, method: str, path: str) -> bool:
        """Whether a path exists in the surface — hallucinated-endpoint detection."""
        want = method.upper()
        for op in self.operations:
            if op.method.upper() != want:
                continue
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", op.path)
            if re.fullmatch(pattern, path.split("?")[0]):
                return True
        return False


def spec_from_tools(tools, *, title: str = "Live MCP", version: str = "live") -> ApiSpec:
    """Build an ApiSpec from a live server's ``tools/list``.

    Field mode against a real MCP server has no OpenAPI document, and demanding
    one would mean hand-writing a spec that then drifts from the server. The
    server's own tool list *is* the surface, so it is the source of truth here —
    the same role the OpenAPI file plays for a generated target (L2).

    The mapping is deliberately thin: an MCP tool has a name, a description and
    an input schema, and that is exactly what an operation needs. Paths are
    synthetic (`/<tool>`) because MCP has no paths, and nothing downstream uses
    them for a tool-call arm.
    """
    operations = []
    for tool in tools:
        schema = tool.parameters or {}
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        operations.append(Operation(
            operation_id=tool.name,
            method="post",
            path=f"/{tool.name}",
            summary=(tool.description or "").split("\n")[0][:200],
            description=tool.description or "",
            parameters=tuple(
                {"name": name, "in": "query", "required": name in required,
                 "schema": body if isinstance(body, dict) else {"type": "string"},
                 "description": (body or {}).get("description", "")
                 if isinstance(body, dict) else ""}
                for name, body in properties.items()
            ),
            request_body=None,
            responses={"200": {"description": "ok"}},
        ))
    return ApiSpec(title=title, version=version,
                   operations=tuple(operations), raw={}, source="mcp")


def _is_url(source: str | Path) -> bool:
    return str(source).startswith(("http://", "https://"))


def _looks_like_yaml(text: str) -> bool:
    """A served spec has no extension to go on, so the body decides."""
    return not text.lstrip().startswith(("{", "["))


def _fetch(url: str, timeout: float = 30.0) -> str:
    """The spec document, over HTTP.

    stdlib only: the engine takes no dependency it does not need, and one GET
    of a static document does not justify one.
    """
    from urllib.request import Request, urlopen

    request = Request(url, headers={"Accept": "application/json, text/yaml, */*"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 — operator-supplied
        return response.read().decode("utf-8")


def load_spec(source: str | Path | dict[str, Any]) -> ApiSpec:
    """An already-parsed doc, a file, or a URL.

    URLs are accepted because "point it at your live server" is the whole offer
    of the free tier, and requiring a reader to curl the spec to a file first
    made that offer untrue for no reason. Content type is not consulted: plenty
    of servers hand back an OpenAPI document as `text/plain`, and the body
    itself says which of the two formats it is.
    """
    if isinstance(source, dict):
        doc = source
    else:
        text = _fetch(str(source)) if _is_url(source) else Path(source).read_text()
        if str(source).endswith((".yaml", ".yml")) or _looks_like_yaml(text):
            import yaml
            doc = yaml.safe_load(text)
        else:
            doc = json.loads(text)

    operations: list[Operation] = []
    for path, item in (doc.get("paths") or {}).items():
        for method in _HTTP_METHODS:
            op = item.get(method)
            if not op:
                continue
            operations.append(Operation(
                operation_id=op.get("operationId") or f"{method}_{path}",
                method=method,
                path=path,
                summary=op.get("summary", ""),
                description=op.get("description", ""),
                parameters=tuple(op.get("parameters", [])),
                request_body=op.get("requestBody"),
                responses=op.get("responses", {}),
            ))

    info = doc.get("info", {})
    return ApiSpec(
        title=info.get("title", "API"),
        version=info.get("version", "0"),
        operations=tuple(operations),
        raw=doc,
    )


# ---- tool definitions ----------------------------------------------------

def _json_schema(op: Operation, detail: SchemaDetail) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in op.parameters:
        name = param.get("name")
        if not name:
            continue
        schema = dict(param.get("schema", {"type": "string"}))
        if detail is not SchemaDetail.MINIMAL and param.get("description"):
            schema["description"] = param["description"]
        if detail is SchemaDetail.RICH and param.get("example") is not None:
            schema["examples"] = [param["example"]]
        properties[name] = schema
        if param.get("required"):
            required.append(name)

    if op.request_body:
        content = op.request_body.get("content", {})
        body_schema = content.get("application/json", {}).get("schema", {"type": "object"})
        properties["body"] = body_schema
        if op.request_body.get("required"):
            required.append("body")

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _tool_description(op: Operation, detail: SchemaDetail) -> str:
    parts = [op.summary or op.description or op.signature]
    if detail is SchemaDetail.MINIMAL:
        return parts[0]
    if op.description and op.description != op.summary:
        parts.append(op.description)
    if detail is SchemaDetail.RICH:
        codes = sorted(c for c in op.responses if c.startswith("4"))
        if codes:
            parts.append("Errors: " + ", ".join(
                f"{c} {op.responses[c].get('description', '')}".strip() for c in codes
            ))
    return "\n\n".join(p for p in parts if p)


def tool_defs(spec: ApiSpec, detail: SchemaDetail) -> tuple[ToolDef, ...]:
    return tuple(
        ToolDef(
            name=op.operation_id,
            description=_tool_description(op, detail),
            parameters=_json_schema(op, detail),
        )
        for op in spec.operations
    )


def meta_tool_defs(spec: ApiSpec) -> tuple[ToolDef, ...]:
    """The hand-rolled search / describe / invoke triad.

    Hand-rolled rather than provider-native so the arm is identical across
    providers — a native facility on one provider and not another would make the
    cross-provider comparison meaningless. Native tool search runs separately and
    *labelled*, so the delta answers "is our dispatcher the bottleneck" instead
    of leaving it as an objection we absorb.
    """
    return (
        ToolDef(
            name="search_operations",
            description=(
                f"Search the {len(spec.operations)} available operations of "
                f"{spec.title} by keyword. Returns operation ids and summaries."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        ToolDef(
            name="describe_operation",
            description="Return the full parameter schema for one operation id.",
            parameters={
                "type": "object",
                "properties": {"operation_id": {"type": "string"}},
                "required": ["operation_id"],
            },
        ),
        ToolDef(
            name="invoke_operation",
            description="Call an operation by id with an arguments object.",
            parameters={
                "type": "object",
                "properties": {
                    "operation_id": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["operation_id"],
            },
        ),
    )


# ---- prose ---------------------------------------------------------------

_BUDGET_OPS = {DocBudget.TERSE: 0, DocBudget.STANDARD: 3, DocBudget.VERBOSE: 8}


def curl_reference(spec: ApiSpec, budget: DocBudget, base_url: str = "$BASE_URL") -> str:
    lines = [f"# {spec.title} v{spec.version}", "", "Call with curl. Base URL: `$BASE_URL`.", ""]
    for op in spec.operations:
        lines.append(f"## {op.signature}")
        if op.summary:
            lines.append(op.summary)
        if budget is not DocBudget.TERSE and op.description:
            lines.append(op.description)
        params = [p for p in op.parameters if p.get("name")]
        if params and budget is not DocBudget.TERSE:
            lines.append("")
            lines.append("Parameters:")
            for p in params:
                req = " (required)" if p.get("required") else ""
                desc = f" — {p['description']}" if budget is DocBudget.VERBOSE and p.get("description") else ""
                lines.append(f"- `{p['name']}`{req}{desc}")
        if budget is DocBudget.VERBOSE:
            lines.append("")
            lines.append("```sh")
            lines.append(f"curl -X {op.method.upper()} \"{base_url}{op.path}\"")
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def skill_markdown(spec: ApiSpec, budget: DocBudget, *, progressive: bool) -> str:
    """A mechanically generated skill.

    This is the ``skill-generated`` condition, and its ceiling is the point: a
    generated skill can only restate the spec, because that is all it has. Real
    skills encode workflow knowledge that is not in the OpenAPI document, which
    is why the authored condition exists and why a null RQ1 result from
    generated skills alone would be uninterpretable.
    """
    reads = [op for op in spec.operations if not op.is_mutation]
    writes = [op for op in spec.operations if op.is_mutation]
    shown = _BUDGET_OPS[budget]

    lines = [f"# Working with {spec.title}", ""]
    if progressive:
        lines += [
            "Start with the index below. Call `describe_operation` (or read the "
            "matching section of the reference) before using an operation you "
            "have not used yet.",
            "",
        ]
    lines += [
        "## Shape",
        f"- {len(reads)} read operations, {len(writes)} write operations.",
        "- Collections paginate. Follow the pagination fields rather than guessing offsets.",
        "- Nested objects are sometimes returned as bare ids; fetch them, or use `expand` where offered.",
        "",
        "## Reads",
    ]
    for op in reads[:shown] if shown else reads[:1]:
        lines.append(f"- `{op.operation_id}` — {op.summary or op.signature}")
    if shown and len(reads) > shown:
        lines.append(f"- …and {len(reads) - shown} more; search or describe to find them.")

    if writes:
        lines += ["", "## Writes", ""]
        lines.append(
            "The same change may be reachable several ways. They are not "
            "equivalent: a full replace drops fields you did not send, and "
            "action endpoints may be irreversible. Prefer the narrowest "
            "operation that does what you were asked."
        )
        lines.append("")
        for op in writes[:shown] if shown else writes[:1]:
            lines.append(f"- `{op.operation_id}` — {op.summary or op.signature}")
    return "\n".join(lines)


def code_module_tree(spec: ApiSpec) -> dict[Path, bytes]:
    """An importable package, one module per tag, one function per operation.

    The mechanism under test: the agent reads only the modules it needs, and
    intermediate results stay in the sandbox instead of entering context. That
    is why this arm is expected to win on cost as call count grows.
    """
    index = ["Available modules:", ""]
    files: dict[Path, bytes] = {}

    body = ["from ._client import call", ""]
    for op in spec.operations:
        args = [p["name"] for p in op.parameters if p.get("name")]
        if op.request_body:
            args.append("body")
        signature = ", ".join(f"{a}=None" for a in args)
        payload = ", ".join(f'"{a}": {a}' for a in args)
        body += [
            f"def {op.operation_id}({signature}):",
            f'    """{op.summary or op.signature}"""',
            f'    return call("{op.method.upper()}", "{op.path}", {{{payload}}})',
            "",
        ]
        index.append(f"- operations.{op.operation_id}() — {op.summary or op.signature}")

    files[Path("api/__init__.py")] = b""
    files[Path("api/operations.py")] = "\n".join(body).encode()
    files[Path("api/_client.py")] = _CLIENT_STUB.encode()
    files[Path("README.md")] = "\n".join(index).encode()
    return files


def meta_tool_module(spec: ApiSpec) -> dict[Path, bytes]:
    """A module tree exposing the triad rather than one function per operation.

    The D3 arm: discovery happens *inside* the sandbox, on demand, and so do the
    intermediate results. It separates two things the other arms confound — D1
    keeps results out of context but still shows every operation up front, while
    A2 hides the operations but pulls every result into context. D3 does both,
    and is the only cell that tells you whether the two savings compose.
    """
    index = [
        "from api.discovery import search, describe, invoke",
        "",
        f"{len(spec.operations)} operations are available, but their schemas are",
        "not listed here. Use search(query) to find one, describe(id) to read its",
        "parameters, then invoke(id, args). Only what you print reaches you.",
    ]
    return {
        Path("api/__init__.py"): b"",
        Path("api/discovery.py"): _DISCOVERY_STUB.encode(),
        Path("api/_client.py"): _CLIENT_STUB.encode(),
        Path("README.md"): "\n".join(index).encode(),
    }


_DISCOVERY_STUB = '''\
"""Search, describe and invoke — the triad, callable from code.

Schemas are fetched on demand, so nothing enters your context until you ask
for it, and results stay in this process unless you print them.
"""

import json
import os
import urllib.request

from ._client import call


def _meta(path, params=None):
    base = os.environ.get("BASE_URL", "")
    url = f"{base}/_meta{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read() or "null")


def search(query, limit=10):
    """Find operations by keyword. Returns ids and one-line summaries."""
    return _meta("/search", {"query": query, "limit": limit})


def describe(operation_id):
    """Full parameter schema for one operation."""
    return _meta("/describe", {"operation_id": operation_id})


def invoke(operation_id, args=None):
    """Call an operation by id."""
    spec = describe(operation_id)
    path = spec["path"]
    args = dict(args or {})
    for key in list(args):
        token = "{" + key + "}"
        if token in path:
            path = path.replace(token, str(args.pop(key)))
    return call(spec["method"], path, args)
'''


_CLIENT_STUB = '''\
"""Transport for the generated operation modules.

Reads BASE_URL from the environment. Results stay in this process — that is the
whole point of this arm: only what you print enters the model's context.
"""

import json
import os
import urllib.request


def call(method, path, params):
    params = {k: v for k, v in (params or {}).items() if v is not None}
    body = params.pop("body", None)
    for key, value in list(params.items()):
        token = "{" + key + "}"
        if token in path:
            path = path.replace(token, str(value))
            params.pop(key)
    url = os.environ.get("BASE_URL", "") + path
    if params and method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or "null")
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.read().decode()[:500]}
'''


# ---- error shaping -------------------------------------------------------

def shape_error(status: int, field: str | None, expected: str | None,
                received: Any, detail: ErrorDetail) -> dict[str, Any]:
    """Render an error at the configured level of helpfulness.

    The G4 manipulation, and the reason it is the strongest unclaimed result:
    an agent given ``validation failed`` retries blindly, while one given the
    field, the expected format and what it actually sent usually self-corrects
    in a single turn. One is a one-line server change; the alternative is
    authoring and maintaining a skill forever.
    """
    if detail is ErrorDetail.TERSE:
        return {"code": str(status), "message": "validation failed"}
    if detail is ErrorDetail.FIELD_SCOPED:
        return {
            "code": str(status),
            "message": f"invalid value for field {field!r}" if field else "validation failed",
        }
    return {
        "code": str(status),
        "message": f"invalid value for field {field!r}" if field else "validation failed",
        "detail": (
            f"field {field!r} expects {expected}, received {received!r}"
            if field else "see the field-level errors"
        ),
    }


# ---- assembly ------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Cheap, provider-independent estimate.

    Deliberately not a provider tokeniser: tokens are not comparable across
    providers anyway (§5.6), and static context is compared *within* a
    comparison where a consistent estimator is what matters.
    """
    return max(1, len(text) // 4)


def assemble(
    spec: ApiSpec,
    variant: Variant,
    *,
    context_blocks: tuple[ContextBlock, ...],
    tools: tuple[ToolDef, ...] = (),
    sandbox_files: dict[Path, bytes] | None = None,
    generator: str,
    authored_commit: str | None = None,
) -> Materials:
    static = sum(count_tokens(b.content) for b in context_blocks)
    static += sum(
        count_tokens(t.name + t.description + json.dumps(t.parameters)) for t in tools
    )
    return Materials(
        context_blocks=context_blocks,
        tool_defs=tools,
        sandbox_files=sandbox_files or {},
        static_tokens=static,
        provenance=Provenance(
            generator=generator,
            spec_revision=f"{spec.title}@{spec.version}",
            authored_commit=authored_commit,
        ),
    )
