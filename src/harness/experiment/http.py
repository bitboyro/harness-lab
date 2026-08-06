"""An HTTP front for the catalog API.

The shell arms (`curl`) and the code arms (a sandboxed subprocess) both need a
real socket — they run outside this process by design, which is the whole point
of measuring them. Everything else can talk to `CatalogApi` directly.

One server per run, on an ephemeral port, torn down after. Ephemeral rather than
fixed because runs parallelise: a hardcoded port would make two concurrent runs
share state, which is exactly the cross-task contamination instance-per-run
isolation exists to prevent.

stdlib only. This serves a handful of requests to localhost from a test harness;
a web framework would be a dependency bought for nothing.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .server import CatalogApi


def _coerce(value: str) -> Any:
    """Query strings are untyped; the API expects real types.

    Deliberately narrow: only unambiguous literals convert. Guessing more would
    hide argument-validity failures that are part of what we measure — an agent
    sending `limit=many` must still earn its 422.
    """
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.lstrip("-").isdigit():
        return int(value)
    return value


class _Handler(BaseHTTPRequestHandler):
    api: CatalogApi
    #: Set when the rig serves a discovery arm. Same triad the tool-call arms
    #: get, reachable from inside a sandbox.
    dispatcher: Any = None
    spec: Any = None
    schema_detail: Any = None

    def _respond(self) -> None:
        parsed = urlparse(self.path)
        params: dict[str, Any] = {
            key: _coerce(values[-1])
            for key, values in parse_qs(parsed.query).items()
        }

        if parsed.path.startswith("/_meta/"):
            self._meta(parsed.path, params)
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length:
            raw = self.rfile.read(length).decode()
            try:
                params["body"] = json.loads(raw)
            except json.JSONDecodeError:
                # Malformed JSON is the agent's error to make and to see.
                self._send(400, {"code": "400",
                                 "message": "request body is not valid JSON"})
                return

        response = self.api.handle(self.command, parsed.path, params)
        self._send(response.status, response.body)

    def _meta(self, path: str, params: dict[str, Any]) -> None:
        """The discovery triad, for arms that reach it from a sandbox (D3).

        Backed by the same index the tool-call arms use, so D3 and A2 differ in
        *how the model reaches discovery*, not in what discovery returns.
        """
        if self.dispatcher is None:
            self._send(404, {"code": "404", "message": "no discovery layer on this arm"})
            return

        from harness.engine.generate import _json_schema

        if path == "/_meta/search":
            query = params.get("query")
            if not query:
                self._send(422, {"code": "422", "message": "search needs a query"})
                return
            hits = self.dispatcher.search(str(query), int(params.get("limit") or 10))
            self._send(200, {"matches": [
                {"operation_id": op.operation_id,
                 "summary": op.summary or op.signature,
                 "score": round(score, 4)}
                for op, score in hits
            ]})
            return

        if path == "/_meta/describe":
            operation_id = params.get("operation_id")
            op = self.spec.by_id(str(operation_id)) if operation_id else None
            if op is None:
                self._send(404, {"code": "404",
                                 "message": f"no operation {operation_id!r}"})
                return
            self._send(200, {
                "operation_id": op.operation_id,
                "method": op.method.upper(),
                "path": op.path,
                "summary": op.summary,
                "description": op.description,
                "parameters": _json_schema(op, self.schema_detail),
            })
            return

        self._send(404, {"code": "404", "message": f"no discovery route {path}"})

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _respond

    def log_message(self, *args: Any) -> None:
        """Silence. The API's own request log is the record we analyse."""


class CatalogServer:
    """A running catalog, as a context manager.

        with CatalogServer(api) as server:
            os.environ["BASE_URL"] = server.base_url
    """

    def __init__(self, api: CatalogApi, host: str = "127.0.0.1",
                 spec: Any = None, schema_detail: Any = None) -> None:
        self.api = api
        dispatcher = None
        if spec is not None:
            from harness.engine.dispatch import OperationIndex
            from harness.engine.axes import SchemaDetail
            dispatcher = OperationIndex(spec)
            schema_detail = schema_detail or SchemaDetail.STANDARD
        handler = type("_BoundHandler", (_Handler,), {
            "api": api, "dispatcher": dispatcher,
            "spec": spec, "schema_detail": schema_detail,
        })
        # Port 0: the OS assigns a free one, so parallel runs never collide.
        self._server = ThreadingHTTPServer((host, 0), handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> CatalogServer:
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self) -> CatalogServer:
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()
