#!/usr/bin/env python3
"""Tiny JSON API for local generate fixture e2e. Bind :8765."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ITEMS = [
    {"id": "item-1", "name": "Northern Lights", "year": 2021},
    {"id": "item-2", "name": "Glass Harbor", "year": 2019},
]
STUDIOS = [
    {"id": "studio-a", "name": "Aurora House"},
    {"id": "studio-b", "name": "Tideworks"},
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter
        pass

    def _json(self, code: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            return self._json(200, {"id": "ok", "status": "up"})
        if path == "/items":
            return self._json(200, {"items": ITEMS})
        if path.startswith("/items/"):
            item_id = path.rsplit("/", 1)[-1]
            for it in ITEMS:
                if it["id"] == item_id:
                    return self._json(200, it)
            return self._json(404, {"error": "not found"})
        if path == "/studios":
            return self._json(200, {"items": STUDIOS})
        if path.startswith("/studios/"):
            studio_id = path.rsplit("/", 1)[-1]
            for st in STUDIOS:
                if st["id"] == studio_id:
                    return self._json(200, st)
            return self._json(404, {"error": "not found"})
        if path == "/search":
            return self._json(200, {"results": ITEMS[:1], "q": "lights"})
        return self._json(404, {"error": "unknown"})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("local-demo listening on http://127.0.0.1:8765", flush=True)
    server.serve_forever()
