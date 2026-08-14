"""OpenAPI → stub HTTP server for local generate / probe when no staging URL.

Serves each operation with example / schema-derived JSON. Not a behavioural
replica of production — enough for fixtures and C1/D1 packaging arms.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from harness.engine.generate import ApiSpec, Operation, load_spec


def stub_body_for(op: Operation) -> Any:
    """Best-effort response body from OpenAPI examples / schema."""
    responses = op.responses or {}
    for code in ("200", "201", "202", "default"):
        resp = responses.get(code)
        if not isinstance(resp, dict):
            continue
        content = resp.get("content") or {}
        media = content.get("application/json") or content.get("*/*") or {}
        if not isinstance(media, dict):
            continue
        if "example" in media:
            return media["example"]
        examples = media.get("examples")
        if isinstance(examples, dict) and examples:
            first = next(iter(examples.values()))
            if isinstance(first, dict) and "value" in first:
                return first["value"]
            return first
        schema = media.get("schema")
        if isinstance(schema, dict):
            if "example" in schema:
                return schema["example"]
            stub = _schema_stub(schema)
            if stub is not None and stub != {}:
                return stub
    return {"ok": True, "operationId": op.operation_id}


def _schema_stub(schema: dict[str, Any], depth: int = 0) -> Any:
    if depth > 4:
        return None
    if "$ref" in schema:
        return {"$ref": schema["$ref"]}
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        out: dict[str, Any] = {}
        for name, sub in props.items():
            if not isinstance(sub, dict):
                continue
            if name in required or depth == 0:
                val = _schema_stub(sub, depth + 1)
                if val is not None:
                    out[name] = val
        return out
    if t == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            one = _schema_stub(items, depth + 1)
            return [] if one is None else [one]
        return []
    if t == "integer" or t == "number":
        return 0
    if t == "boolean":
        return False
    if t == "string":
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        return "string"
    return None


def match_operation(spec: ApiSpec, method: str, path: str) -> Operation | None:
    want = method.upper()
    path_only = path.split("?", 1)[0]
    for op in spec.operations:
        if op.method.upper() != want:
            continue
        pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", op.path) + "$"
        if re.fullmatch(pattern, path_only):
            return op
    return None


def make_handler(spec: ApiSpec) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # quieter
            pass

        def _json(self, code: int, payload: object) -> None:
            body = json.dumps(payload, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _dispatch(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path == "/health":
                return self._json(200, {"status": "up", "title": spec.title})
            method = self.command.upper()
            op = match_operation(spec, method, path)
            if op is None:
                return self._json(404, {"error": "unknown", "method": method, "path": path})
            # Consume body for POST/PUT/PATCH — ignored for stub responses.
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            return self._json(200, stub_body_for(op))

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch()

        def do_PUT(self) -> None:  # noqa: N802
            self._dispatch()

        def do_PATCH(self) -> None:  # noqa: N802
            self._dispatch()

        def do_DELETE(self) -> None:  # noqa: N802
            self._dispatch()

    return Handler


def start_http_mock(
    spec: ApiSpec | str,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, str]:
    """Bind a mock HTTP server. Returns (server, base_url). Caller serves."""
    if not isinstance(spec, ApiSpec):
        spec = load_spec(spec)
    server = ThreadingHTTPServer((host, port), make_handler(spec))
    bound = server.server_address[1]
    base = f"http://{host}:{bound}"
    return server, base


def serve_http_in_thread(
    spec: ApiSpec | str,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, str, threading.Thread]:
    server, base = start_http_mock(spec, host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mock-http")
    thread.start()
    return server, base, thread
