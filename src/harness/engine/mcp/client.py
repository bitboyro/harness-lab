"""MCP client covering both spec revisions.

The 2026-07-28 revision retired sessions: no ``initialize``/``initialized``
handshake, no ``Mcp-Session-Id``. Protocol version, client identity and
capabilities now ride in ``_meta`` on every request, and streamable requests
carry ``Mcp-Method`` / ``Mcp-Name`` so gateways can route without parsing bodies.

Both revisions are supported because the deprecated transport has a 12-month
offramp, so for about a year the installed base field mode must reach is split
across the two.

The cost asymmetry is the reason this is an axis and not just a compatibility
shim: legacy pays a per-*session* handshake, 2026-07-28 pays a per-*call* tax
that scales with call count. That penalises chatty arms and favours arms that
batch inside a sandbox — which may move the A-vs-D ranking on its own.

Contract: archive/reference/decisions.md F3
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..axes import McpRevision
from ..infra import with_retry
from ..packaging import CostBreakdown, ToolDef

PROTOCOL_VERSION = {
    McpRevision.R2026_07_28: "2026-07-28",
    McpRevision.LEGACY: "2025-06-18",
}

CLIENT_IDENTITY = {"name": "harness-lab", "version": "0.0.0"}
CLIENT_CAPABILITIES: dict[str, Any] = {}


class Transport(Protocol):
    """Moves one JSON-RPC message and returns the response."""

    def send(self, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]: ...


@dataclass(slots=True)
class ListedTools:
    tools: tuple[ToolDef, ...]
    #: 2026-07-28 only. A different cache from prompt caching: it moves the
    #: *static context* cost, which flatters eager-all specifically. Reported as
    #: its own cache condition rather than folded into `caching: on`.
    ttl_ms: int | None = None
    cache_scope: str | None = None


class McpError(RuntimeError):
    pass


class McpClient:
    """One interface, two wire shapes.

    Callers never branch on revision — that is the point. If a caller needs to
    know, the difference belongs in this class instead.
    """

    def __init__(
        self,
        transport: Transport,
        revision: McpRevision,
        *,
        token_counter: Any = None,
    ) -> None:
        self.transport = transport
        self.revision = revision
        self._session_id: str | None = None
        self._initialized = False
        self._count = token_counter or (lambda s: max(1, len(s) // 4))
        self.cost = CostBreakdown()
        self._next_id = 0

    # ---- lifecycle -------------------------------------------------------

    def connect(self) -> None:
        """Handshake on legacy; a no-op on 2026-07-28.

        Statelessness is exactly the change: every request is self-contained and
        routable to any instance behind a load balancer.
        """
        if self.revision is McpRevision.R2026_07_28:
            self._initialized = True
            return

        body = self._envelope("initialize", {
            "protocolVersion": PROTOCOL_VERSION[self.revision],
            "clientInfo": CLIENT_IDENTITY,
            "capabilities": CLIENT_CAPABILITIES,
        })
        self.cost.session_setup_tokens += self._count(json.dumps(body))
        # Retried: the handshake establishes a session and changes nothing the
        # grader looks at, so a transient failure here is safe to ride out.
        response = with_retry(
            lambda: self.transport.send(body, {"Content-Type": "application/json"})
        )
        # The header is where a real server puts it; the body fields were a
        # guess and no server actually returns them.
        headers = getattr(self.transport, "last_headers", {}) or {}
        self._session_id = (headers.get("mcp-session-id")
                            or response.get("_sessionId")
                            or response.get("sessionId"))

        notice = self._envelope("notifications/initialized", {})
        self.cost.session_setup_tokens += self._count(json.dumps(notice))
        self.transport.send(notice, self._headers("notifications/initialized"))
        self._initialized = True

    # ---- operations ------------------------------------------------------

    def list_tools(self) -> ListedTools:
        result = self._request("tools/list", {}, retry=True)
        tools = tuple(
            ToolDef(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("inputSchema", {}),
            )
            for t in result.get("tools", [])
        )
        return ListedTools(
            tools=tools,
            ttl_ms=result.get("ttlMs"),
            cache_scope=result.get("cacheScope"),
        )

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            "tools/call", {"name": name, "arguments": arguments}, mcp_name=name
        )

        # MRTR: the server can ask before acting. Introduced in 2026-07-28 as
        # the sanctioned replacement for server-initiated requests over open
        # streams, and directly relevant to harm on irreversible operations.
        if result.get("resultType") == "input_required":
            if self.revision is not McpRevision.R2026_07_28:
                raise McpError("server returned input_required on a legacy connection")
            result = self._respond_to_elicitation(name, arguments, result)
        return result

    def _respond_to_elicitation(
        self, name: str, arguments: dict[str, Any], first: dict[str, Any]
    ) -> dict[str, Any]:
        """Answer the server's questions and retry.

        Auto-confirming is the honest default for an unattended benchmark: the
        agent already decided to act, and a harness that silently declined would
        measure the harness, not the packaging. What MRTR changes is whether the
        *model* gets a second look before the write lands — that is what the
        `confirmation: mrtr` axis is testing, and it is visible in the extra
        round trip either way.
        """
        responses = [
            {"id": req.get("id"), "value": True}
            for req in first.get("requests", [])
        ]
        return self._request(
            "tools/call",
            {"name": name, "arguments": arguments, "inputResponses": responses},
            mcp_name=name,
        )

    # ---- wire ------------------------------------------------------------

    def _request(
        self, method: str, params: dict[str, Any], *, mcp_name: str | None = None,
        retry: bool = False,
    ) -> dict[str, Any]:
        """Send one JSON-RPC request.

        ``retry`` is opt-in and deliberately **off for ``tools/call``**. A
        transport failure means no response arrived, not that nothing happened —
        the write may well have landed. Writes are graded on final server state,
        so a blind retry could apply an irreversible operation twice and invent
        a harm event that the agent never caused. Discovery (`tools/list`) is
        idempotent and safe; the agent's own calls are not, and a lost one is
        recorded as a failed call the agent can see and react to.
        """
        if not self._initialized:
            raise McpError("connect() first")

        body = self._envelope(method, params)
        headers = self._headers(method, mcp_name)

        # The per-call tax. On 2026-07-28 `_meta` rides on every request, so
        # this scales with call count; on legacy it was paid once at handshake.
        overhead = self._count(json.dumps(body.get("params", {}).get("_meta", {})))
        if self.revision is McpRevision.R2026_07_28:
            self.cost.per_call_overhead_tokens += overhead
        self.cost.round_trips += 1

        send = lambda: self.transport.send(body, headers)  # noqa: E731
        response = with_retry(send) if retry else send()
        if "error" in response:
            raise McpError(str(response["error"]))
        return response.get("result", {})

    def _envelope(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": dict(params),
        }
        # Notifications carry no id, by the JSON-RPC spec. Giving one an id
        # makes the server treat it as a request and hold the stream open for a
        # reply the client is not going to read.
        if not method.startswith("notifications/"):
            self._next_id += 1
            body["id"] = self._next_id
        if self.revision is McpRevision.R2026_07_28 and method != "initialize":
            body["params"]["_meta"] = {
                "protocolVersion": PROTOCOL_VERSION[self.revision],
                "clientInfo": CLIENT_IDENTITY,
                "capabilities": CLIENT_CAPABILITIES,
            }
        return body

    def _headers(self, method: str, mcp_name: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.revision is McpRevision.R2026_07_28:
            # Required so gateways can route and authorize without parsing bodies.
            headers["Mcp-Method"] = method
            if mcp_name:
                headers["Mcp-Name"] = mcp_name
        elif self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers


def detect_revision(server_info: dict[str, Any]) -> McpRevision:
    """Resolve ``spec_revision: auto`` from what the server reports."""
    version = str(server_info.get("protocolVersion", ""))
    if version >= "2026-07-28":
        return McpRevision.R2026_07_28
    return McpRevision.LEGACY
