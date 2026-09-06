"""The field-run reachability gate.

A paid matrix must stop before the spend when its subject cannot complete a
fresh handshake — build success and an externally reachable protocol surface
are different facts. These exercise the gate without a provider key: an
unroutable or misconfigured target is the whole point.
"""

from __future__ import annotations

import http.server
import json
import threading
from types import SimpleNamespace

import pytest

from harness.cli import PackTargetError, _live_http_base, _verify_field_reachable
from harness.engine.taskpack import ApiTarget, Auth, McpTarget


def _pack(api: ApiTarget) -> SimpleNamespace:
    return SimpleNamespace(api=api)


_ARGS = SimpleNamespace(mcp_revision="2026-07-28", spec=None)


# ---- _live_http_base ------------------------------------------------------

def test_live_http_base_ignores_a_local_openapi_file() -> None:
    assert _live_http_base(_pack(ApiTarget(openapi="./specs/api.yaml"))) is None


def test_live_http_base_picks_a_real_url() -> None:
    api = ApiTarget(openapi="https://api.example.test/openapi.json")
    assert _live_http_base(_pack(api)) == "https://api.example.test/openapi.json"


# ---- MCP handshake ------------------------------------------------------

def test_unroutable_mcp_target_refuses_before_the_spend() -> None:
    # Port 1 is reserved and never listens: connect() fails at the transport.
    api = ApiTarget(mcp=McpTarget(url="http://127.0.0.1:1/mcp"))
    with pytest.raises(PackTargetError, match="unreachable"):
        _verify_field_reachable(_pack(api), _ARGS)


def test_missing_credential_env_var_is_an_operator_error_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FIELD_REACH_TOKEN", raising=False)
    api = ApiTarget(
        mcp=McpTarget(url="http://127.0.0.1:1/mcp"),
        auth=Auth(type="bearer", env="FIELD_REACH_TOKEN"),
    )
    with pytest.raises(PackTargetError, match="api.auth"):
        _verify_field_reachable(_pack(api), _ARGS)


def test_auto_revision_detection_uses_the_configured_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An auth-gated server 401s an unauthenticated ``initialize``; the gate
    must send the bearer token to both the revision probe and the handshake."""
    seen_auth: list[str | None] = []
    seen_methods: list[str] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            auth = self.headers.get("Authorization")
            seen_auth.append(auth)
            body = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"
            )
            seen_methods.append(body.get("method", ""))
            if auth != "Bearer s3cret":
                self.send_response(401)
                self.end_headers()
                return
            method, rpc_id = body.get("method"), body.get("id")
            if rpc_id is None:  # notifications/initialized
                self.send_response(202)
                self.end_headers()
                return
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18",
                          "capabilities": {}, "serverInfo": {"name": "t", "version": "0"}}
            elif method == "tools/list":
                result = {"tools": [{"name": "ping", "description": "d",
                                     "inputSchema": {"type": "object"}}]}
            else:
                result = {}
            payload = json.dumps(
                {"jsonrpc": "2.0", "id": rpc_id, "result": result}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_a) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("FIELD_REACH_TOKEN", "s3cret")
    try:
        api = ApiTarget(
            mcp=McpTarget(url=f"http://127.0.0.1:{srv.server_port}/mcp",
                          spec_revision="auto"),
            auth=Auth(type="bearer", env="FIELD_REACH_TOKEN"),
        )
        revision, tools = _verify_field_reachable(_pack(api), _ARGS)
    finally:
        srv.shutdown()

    assert [t.name for t in tools] == ["ping"]
    assert revision.value == "legacy"  # 2025-06-18 → pre-2026 revision
    # Every request the gate made carried the token — including the probe.
    assert seen_auth and all(a == "Bearer s3cret" for a in seen_auth)
    # Auto-detection resolves off the one handshake, not a second initialize.
    assert seen_methods.count("initialize") == 1


# ---- HTTP base URL ------------------------------------------------------

def test_unroutable_http_target_refuses_before_the_spend() -> None:
    api = ApiTarget(openapi="http://127.0.0.1:1/openapi.json")
    with pytest.raises(PackTargetError, match="unreachable"):
        _verify_field_reachable(_pack(api), _ARGS)


def test_a_reachable_http_server_passes_even_on_404() -> None:
    seen_auth: list[str | None] = []

    class _Quiet(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen_auth.append(self.headers.get("Authorization"))
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_a) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        api = ApiTarget(openapi=f"http://127.0.0.1:{srv.server_port}/openapi.json")
        _, tools = _verify_field_reachable(_pack(api), _ARGS)
        assert tools is None
    finally:
        srv.shutdown()
    assert seen_auth == [None]  # no auth configured, none sent


def test_http_probe_sends_the_packs_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_auth: list[str | None] = []

    class _Quiet(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            seen_auth.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_a) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("FIELD_REACH_TOKEN", "s3cret")
    try:
        api = ApiTarget(
            openapi=f"http://127.0.0.1:{srv.server_port}/openapi.json",
            auth=Auth(type="bearer", env="FIELD_REACH_TOKEN"),
        )
        _verify_field_reachable(_pack(api), _ARGS)
    finally:
        srv.shutdown()
    assert seen_auth == ["Bearer s3cret"]
