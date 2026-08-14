"""Start local OpenAPI HTTP mock + MCP gateway; print READY line for the UI."""

from __future__ import annotations

import json
import signal
import sys
import time
from typing import Any

from harness.engine.generate import load_spec
from harness.mcp_gateway import serve_mcp_in_thread
from harness.mock_http import serve_http_in_thread


def serve_pair(
    spec_path: str,
    *,
    host: str = "127.0.0.1",
    http_port: int = 0,
    mcp_port: int = 0,
) -> dict[str, Any]:
    """Bind HTTP mock + MCP gateway. Blocks until SIGTERM/SIGINT."""
    spec = load_spec(spec_path)
    http_server, http_url, _http_t = serve_http_in_thread(
        spec, host=host, port=http_port
    )
    mcp_server, mcp_url, _mcp_t = serve_mcp_in_thread(
        spec, http_url, host=host, port=mcp_port
    )
    ready = {
        "ready": True,
        "httpUrl": http_url,
        "mcpUrl": mcp_url,
        "title": spec.title,
        "operations": len(spec.operations),
    }
    # Machine-readable handshake for GenerateService / scripts.
    print("MOCK_READY " + json.dumps(ready, separators=(",", ":")), flush=True)

    stop = {"flag": False}

    def _stop(*_args: Any) -> None:
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        while not stop["flag"]:
            time.sleep(0.4)
    finally:
        http_server.shutdown()
        mcp_server.shutdown()
    return ready


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Local OpenAPI HTTP mock + MCP gateway")
    p.add_argument("--spec", required=True, help="OpenAPI file path")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--http-port", type=int, default=0)
    p.add_argument("--mcp-port", type=int, default=0)
    args = p.parse_args(argv)
    try:
        serve_pair(
            args.spec,
            host=args.host,
            http_port=args.http_port,
            mcp_port=args.mcp_port,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
