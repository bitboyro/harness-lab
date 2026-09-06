"""The field-run reachability gate.

A paid matrix must stop before the spend when its subject cannot complete a
fresh handshake — build success and an externally reachable protocol surface
are different facts. These exercise the gate without a provider key or a live
server: an unroutable target is the whole point.
"""

from __future__ import annotations

import http.server
import threading
from types import SimpleNamespace

import pytest

from harness.cli import PackTargetError, _live_http_base, _verify_field_reachable
from harness.engine.axes import McpRevision
from harness.engine.taskpack import ApiTarget, McpTarget


def _pack(api: ApiTarget) -> SimpleNamespace:
    return SimpleNamespace(api=api)


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
        _verify_field_reachable(_pack(api), McpRevision.R2026_07_28)


# ---- HTTP base URL ------------------------------------------------------

def test_unroutable_http_target_refuses_before_the_spend() -> None:
    api = ApiTarget(openapi="http://127.0.0.1:1/openapi.json")
    with pytest.raises(PackTargetError, match="unreachable"):
        _verify_field_reachable(_pack(api), McpRevision.R2026_07_28)


def test_a_reachable_http_server_passes_even_on_404() -> None:
    class _Quiet(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_a) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        api = ApiTarget(openapi=f"http://127.0.0.1:{srv.server_port}/openapi.json")
        assert _verify_field_reachable(_pack(api), McpRevision.R2026_07_28) is None
    finally:
        srv.shutdown()
