"""An MCP surface over the catalog API.

Serves `tools/list` and `tools/call` from the same OpenAPI document every other
arm is generated from, so the MCP arms and the shell arms differ in *packaging*
and not in the API underneath. That equivalence is validity control V1 — if the
MCP surface exposed different capabilities than the curl reference described,
every arm comparison would be measuring two APIs.

Both spec revisions are served, because the cost asymmetry between them is
itself an axis: legacy pays a per-session handshake, 2026-07-28 pays a per-call
`_meta` tax that scales with call count.

Contract: archive/reference/packaging-axes.md; archive/reference/decisions.md F3
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from harness.engine.axes import Confirmation, SchemaDetail
from harness.engine.generate import ApiSpec, tool_defs

from .server import CatalogApi

#: Operations that destroy data irreversibly. Under `confirmation: mrtr` the
#: server asks before acting — the packaging choice M1 exists to measure.
_DESTRUCTIVE = re.compile(r"archive|delete|replace")

#: How long a client may cache tools/list (2026-07-28). Moves *static context*
#: cost specifically, which is a different cache from prompt caching and
#: flatters eager-all in particular.
LIST_TTL_MS = 300_000


@dataclass
class McpSurface:
    """JSON-RPC handler. Pair with InProcessTransport or serve over HTTP."""

    api: CatalogApi
    spec: ApiSpec
    schema_detail: SchemaDetail = SchemaDetail.STANDARD
    confirmation: Confirmation = Confirmation.NONE
    #: Elicitations already answered, keyed by request id, so a confirmed retry
    #: is not asked again.
    _confirmed: set[str] = field(default_factory=set)
    calls: list[tuple[str, dict]] = field(default_factory=list)

    # ---- JSON-RPC --------------------------------------------------------

    def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        method = body.get("method", "")
        params = body.get("params") or {}
        request_id = body.get("id")

        try:
            match method:
                case "initialize":
                    result = self._initialize()
                case "notifications/initialized":
                    result = {}
                case "tools/list":
                    result = self._list_tools()
                case "tools/call":
                    result = self._call_tool(params)
                case _:
                    return self._error(request_id, -32601, f"unknown method {method!r}")
        except Exception as e:  # noqa: BLE001 — a server fault is data, not a crash
            return self._error(request_id, -32603, f"{type(e).__name__}: {e}")

        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": code, "message": message}}

    def _initialize(self) -> dict[str, Any]:
        """Legacy only. The 2026-07-28 client never sends this."""
        return {
            "protocolVersion": "2025-06-18",
            "serverInfo": {"name": "catalog", "version": self.spec.version},
            "capabilities": {"tools": {}},
        }

    def _list_tools(self) -> dict[str, Any]:
        tools = tool_defs(self.spec, self.schema_detail)
        return {
            "tools": [
                {"name": t.name, "description": t.description, "inputSchema": t.parameters}
                for t in tools
            ],
            "ttlMs": LIST_TTL_MS,
            "cacheScope": "server",
        }

    # ---- tool dispatch ---------------------------------------------------

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = dict(params.get("arguments") or {})
        self.calls.append((str(name), arguments))

        operation = self.spec.by_id(str(name))
        if operation is None:
            # A hallucinated tool. Reported as an error result rather than a
            # transport failure, so it lands in the metrics as a bad call.
            return {"isError": True,
                    "content": [{"type": "text", "text": f"no tool named {name!r}"}]}

        if self._needs_confirmation(operation.operation_id, params):
            return {
                "resultType": "input_required",
                "requests": [{
                    "id": f"confirm:{operation.operation_id}",
                    "prompt": (
                        f"{operation.operation_id} is irreversible and may affect "
                        "more than one record. Confirm?"
                    ),
                }],
            }

        status, body = self._invoke(operation, arguments)
        return {
            "isError": status >= 400,
            "status": status,
            "content": [{"type": "text", "text": _render(body)}],
            "structuredContent": body,
        }

    def _needs_confirmation(self, operation_id: str, params: dict[str, Any]) -> bool:
        if self.confirmation is not Confirmation.MRTR:
            return False
        if not _DESTRUCTIVE.search(operation_id):
            return False
        if params.get("inputResponses"):
            self._confirmed.add(operation_id)
            return False
        return operation_id not in self._confirmed

    def _invoke(self, operation, arguments: dict[str, Any]) -> tuple[int, Any]:
        """Bind tool arguments onto the HTTP shape the API expects."""
        path = operation.path
        remaining = dict(arguments)

        # Path parameters are substituted; whatever is left is query or body.
        for match in re.findall(r"\{([^}]+)\}", operation.path):
            value = remaining.pop(match, None)
            if value is None:
                return 422, {
                    "code": "422",
                    "message": f"missing required path parameter {match!r}",
                }
            path = path.replace("{" + match + "}", str(value))

        response = self.api.handle(operation.method.upper(), path, remaining)
        return response.status, response.body


def _render(body: Any) -> str:
    import json
    return body if isinstance(body, str) else json.dumps(body, default=str)


def transport_for(api: CatalogApi, spec: ApiSpec, **kw: Any):
    """An InProcessTransport wired to a fresh surface over this API."""
    from harness.engine.mcp.transport import InProcessTransport

    surface = McpSurface(api=api, spec=spec, **kw)
    return InProcessTransport(handler=surface.handle), surface
