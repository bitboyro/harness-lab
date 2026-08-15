"""Local OpenAPI HTTP mock + MCP gateway tests."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from harness.engine.generate import load_spec
from harness.mcp_gateway import HttpForwarder, serve_mcp_in_thread
from harness.mock_http import match_operation, serve_http_in_thread, stub_body_for

SAMPLE = Path(__file__).resolve().parents[1] / "harness-ui" / "examples" / "openapi-samples" / "local-demo.yaml"


def test_stub_and_match_local_demo() -> None:
    spec = load_spec(SAMPLE)
    op = match_operation(spec, "GET", "/items")
    assert op is not None
    assert op.operation_id
    body = stub_body_for(op)
    assert body is not None


def test_http_mock_serves_health_and_path() -> None:
    spec = load_spec(SAMPLE)
    server, base, _t = serve_http_in_thread(spec, port=0)
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            assert json.loads(r.read())["status"] == "up"
        with urllib.request.urlopen(base + "/items", timeout=5) as r:
            data = json.loads(r.read())
            assert data  # stub or example
    finally:
        server.shutdown()


def test_mcp_gateway_list_and_call() -> None:
    spec = load_spec(SAMPLE)
    http_server, http_base, _ = serve_http_in_thread(spec, port=0)
    try:
        mcp_server, mcp_url, _ = serve_mcp_in_thread(spec, http_base, port=0)
        try:
            # tools/list
            req = urllib.request.Request(
                mcp_url,
                data=json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                ).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                listed = json.loads(r.read())["result"]["tools"]
            assert len(listed) == len(spec.operations)
            name = listed[0]["name"]
            # tools/call
            call = urllib.request.Request(
                mcp_url,
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": {}},
                    }
                ).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(call, timeout=5) as r:
                result = json.loads(r.read())["result"]
            assert "content" in result
            assert result.get("isError") is False or result.get("status", 200) < 400
        finally:
            mcp_server.shutdown()
    finally:
        http_server.shutdown()


def test_forwarder_missing_path_param() -> None:
    spec = load_spec(SAMPLE)
    op = next(o for o in spec.operations if "{" in o.path)
    fw = HttpForwarder("http://127.0.0.1:9")
    status, body = fw.invoke(op, {})
    assert status == 422
    assert "missing" in body["message"]
