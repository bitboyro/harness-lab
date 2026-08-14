"""Field MCP gateway: tools/list from OpenAPI, tools/call → HTTP base URL.

Platform sidecar for A/B probe arms when the customer API is plain HTTP.
Loads the same OpenAPI materials are generated from (V1). Does not import
``experiment`` — field-safe.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlencode

from harness.engine.axes import SchemaDetail
from harness.engine.generate import ApiSpec, Operation, load_spec, tool_defs

LIST_TTL_MS = 300_000
USER_AGENT = "harness-lab-mcp-gateway/0.1"


class HttpForwarder:
    """Map MCP tool arguments onto HTTP against ``base_url``."""

    def __init__(self, base_url: str, *, auth_header: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header

    def invoke(self, operation: Operation, arguments: dict[str, Any]) -> tuple[int, Any]:
        path = operation.path
        remaining = dict(arguments)
        for match in re.findall(r"\{([^}]+)\}", operation.path):
            value = remaining.pop(match, None)
            if value is None:
                return 422, {
                    "code": "422",
                    "message": f"missing required path parameter {match!r}",
                }
            path = path.replace("{" + match + "}", str(value))

        body_obj = remaining.pop("body", None)
        query: dict[str, str] = {}
        # Path/query params are top-level in tool schemas; leftovers become query
        # for GET and merge into JSON body for writes when no explicit body.
        for key, val in list(remaining.items()):
            if val is None:
                continue
            query[str(key)] = str(val) if not isinstance(val, (dict, list)) else json.dumps(val)
            remaining.pop(key, None)

        url = self.base_url + path
        if query and operation.method.upper() == "GET":
            url = url + ("&" if "?" in url else "?") + urlencode(query)

        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        data: bytes | None = None
        method = operation.method.upper()
        if method in {"POST", "PUT", "PATCH"}:
            payload = body_obj if body_obj is not None else (query or {})
            data = json.dumps(payload, default=str).encode()
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310
                raw = resp.read().decode()
                status = resp.status
                try:
                    parsed: Any = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = raw
                return status, parsed
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:2000]
            try:
                parsed = json.loads(detail) if detail else {"error": e.reason}
            except json.JSONDecodeError:
                parsed = {"error": detail or e.reason}
            return e.code, parsed
        except urllib.error.URLError as e:
            return 503, {"error": f"upstream unreachable: {e.reason}"}


class McpGateway:
    """JSON-RPC MCP handler over an OpenAPI surface + HTTP forwarder."""

    def __init__(
        self,
        spec: ApiSpec,
        forwarder: HttpForwarder,
        *,
        schema_detail: SchemaDetail = SchemaDetail.STANDARD,
    ) -> None:
        self.spec = spec
        self.forwarder = forwarder
        self.schema_detail = schema_detail

    def handle(self, body: dict[str, Any]) -> dict[str, Any] | None:
        method = body.get("method", "")
        params = body.get("params") or {}
        request_id = body.get("id")
        # Notifications have no id and get no reply.
        if "id" not in body and str(method).startswith("notifications/"):
            return None

        try:
            match method:
                case "initialize":
                    result = {
                        "protocolVersion": "2025-06-18",
                        "serverInfo": {
                            "name": "harness-mcp-gateway",
                            "version": self.spec.version,
                        },
                        "capabilities": {"tools": {}},
                    }
                case "notifications/initialized":
                    return None
                case "tools/list":
                    tools = tool_defs(self.spec, self.schema_detail)
                    result = {
                        "tools": [
                            {
                                "name": t.name,
                                "description": t.description,
                                "inputSchema": t.parameters,
                            }
                            for t in tools
                        ],
                        "ttlMs": LIST_TTL_MS,
                        "cacheScope": "server",
                    }
                case "tools/call":
                    result = self._call_tool(params if isinstance(params, dict) else {})
                case "ping":
                    result = {}
                case _:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"unknown method {method!r}"},
                    }
        except Exception as e:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"},
            }

        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = dict(params.get("arguments") or {})
        operation = self.spec.by_id(str(name))
        if operation is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"no tool named {name!r}"}],
            }
        status, body = self.forwarder.invoke(operation, arguments)
        text = body if isinstance(body, str) else json.dumps(body, default=str)
        return {
            "isError": status >= 400,
            "status": status,
            "content": [{"type": "text", "text": text}],
            "structuredContent": body if not isinstance(body, str) else {"text": body},
        }


def make_mcp_handler(gateway: McpGateway) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return
            reply = gateway.handle(body if isinstance(body, dict) else {})
            if reply is None:
                self.send_response(202)
                self.end_headers()
                return
            payload = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            # Legacy session echo — harmless for 2026-07-28 clients.
            session = self.headers.get("Mcp-Session-Id")
            if session:
                self.send_header("Mcp-Session-Id", session)
            elif body.get("method") == "initialize":
                self.send_header("Mcp-Session-Id", "mock-session")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/").endswith("health") or self.path in {"/", "/mcp"}:
                payload = json.dumps({"status": "up", "mcp": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

    return Handler


def start_mcp_gateway(
    spec: ApiSpec | str,
    base_url: str,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    auth_header: str | None = None,
) -> tuple[ThreadingHTTPServer, str]:
    if not isinstance(spec, ApiSpec):
        spec = load_spec(spec)
    gateway = McpGateway(spec, HttpForwarder(base_url, auth_header=auth_header))
    server = ThreadingHTTPServer((host, port), make_mcp_handler(gateway))
    bound = server.server_address[1]
    # Probe arms POST to this URL (HttpTransport).
    mcp_url = f"http://{host}:{bound}/mcp"
    return server, mcp_url


def serve_mcp_in_thread(
    spec: ApiSpec | str,
    base_url: str,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    auth_header: str | None = None,
) -> tuple[ThreadingHTTPServer, str, threading.Thread]:
    server, mcp_url = start_mcp_gateway(
        spec, base_url, host=host, port=port, auth_header=auth_header
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mock-mcp")
    thread.start()
    return server, mcp_url, thread
