"""Wire transports for the MCP client.

Streamable HTTP for both revisions, plus an in-process transport so an MCP
surface can be exercised without a socket.

Deliberately stdlib-only: an HTTP client is not where this project should be
taking a dependency, and the request shapes are simple.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_TIMEOUT_S = 60.0

#: Identify ourselves. Without a User-Agent, bot protection in front of a real
#: server rejects the request before MCP is ever reached — a 403 that looks like
#: an auth failure and is not one.
USER_AGENT = "harness-lab/0.1 (+https://github.com/bitboy-ro/harness-lab)"


class TransportError(RuntimeError):
    pass


@dataclass
class HttpTransport:
    """Streamable HTTP.

    Servers may answer ``application/json`` or an SSE stream; both are accepted
    because the offramp period means field mode meets both in the wild.
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_s: float = DEFAULT_TIMEOUT_S
    #: Response headers from the last exchange. The legacy revision returns the
    #: session id in `Mcp-Session-Id`, not in the JSON body, so the client
    #: cannot find it without this.
    last_headers: dict[str, str] = field(default_factory=dict)
    #: Every request/response pair, for the trace. Server-side request logs are
    #: not available in field mode, so this is the only record of what was sent.
    log: list[tuple[dict, dict, dict]] = field(default_factory=list)

    @classmethod
    def from_env(cls, url: str, auth_type: str = "none", auth_env: str | None = None,
                 header_name: str | None = None, **kw: Any) -> HttpTransport:
        """Build with credentials read from the environment, never inlined."""
        headers: dict[str, str] = {}
        if auth_type != "none":
            if not auth_env:
                raise TransportError(f"auth type {auth_type!r} needs an env var name")
            token = os.environ.get(auth_env)
            if not token:
                raise TransportError(
                    f"{auth_env} is not set; the pack asks for {auth_type} auth"
                )
            if auth_type == "bearer":
                headers["Authorization"] = f"Bearer {token}"
            elif auth_type == "header":
                if not header_name:
                    raise TransportError("auth type 'header' needs header_name")
                headers[header_name] = token
            elif auth_type == "basic":
                headers["Authorization"] = f"Basic {token}"
        return cls(url=url, headers=headers, **kw)

    def send(self, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        # A JSON-RPC *notification* has no `id` and gets no reply. Waiting for
        # one hangs until the socket times out, because the server keeps the
        # stream open for events that never come.
        notification = "id" not in body
        payload = json.dumps(body).encode()
        request = urllib.request.Request(
            self.url,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json, text/event-stream",
                "User-Agent": USER_AGENT,
                **self.headers,
                **headers,
            },
        )
        try:
            timeout = 5.0 if notification else self.timeout_s
            with urllib.request.urlopen(request, timeout=timeout) as response:
                self.last_headers = {k.lower(): v for k, v in response.headers.items()}
                if notification:
                    self.log.append((body, headers, {}))
                    return {}
                raw = response.read().decode()
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:500]
            raise TransportError(f"{e.code} from {self.url}: {detail}") from e
        except TimeoutError:
            if notification:
                # Accepted, just never answered. Not an error.
                return {}
            raise TransportError(f"timed out after {self.timeout_s}s: {self.url}")
        except urllib.error.URLError as e:
            if notification and isinstance(getattr(e, "reason", None), TimeoutError):
                return {}
            raise TransportError(f"cannot reach {self.url}: {e.reason}") from e

        parsed = _parse_sse(raw) if "text/event-stream" in content_type else _parse_json(raw)
        self.log.append((body, headers, parsed))
        return parsed


def _parse_json(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise TransportError(f"response was not JSON: {raw[:200]}") from e


def _parse_sse(raw: str) -> dict[str, Any]:
    """Take the last ``data:`` frame.

    A JSON-RPC response arrives as one frame; multiple frames mean progress
    notifications, and the result is the final one.
    """
    frames = [
        line[len("data:"):].strip()
        for line in raw.splitlines()
        if line.startswith("data:")
    ]
    if not frames:
        raise TransportError(f"no data frames in SSE response: {raw[:200]}")
    return _parse_json(frames[-1])


@dataclass
class InProcessTransport:
    """Calls a handler directly. No socket.

    Used by the controlled rig, so the mock API can present an MCP surface
    without the harness paying for a network round trip it is trying to measure.
    """

    handler: Callable[[dict[str, Any]], dict[str, Any]]
    log: list[tuple[dict, dict, dict]] = field(default_factory=list)

    def send(self, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        response = self.handler(body)
        self.log.append((body, headers, response))
        return response


def probe_server(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Ask a server what it is, to resolve ``spec_revision: auto``.

    Asks via ``initialize`` and believes what the server reports, rather than
    inferring from whether a stateless request fails. Inference was wrong in
    both directions: a stateless request can fail for reasons that have nothing
    to do with the revision (bot protection, a bad path), and a lenient server
    can accept one while still being legacy.
    """
    transport = HttpTransport(url=url, headers=headers or {})
    try:
        response = transport.send({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "clientInfo": {"name": "harness-lab", "version": "0"},
                       "capabilities": {}},
        }, {})
        reported = (response.get("result") or {}).get("protocolVersion")
        if reported:
            return {"protocolVersion": reported}
    except TransportError:
        pass
    return {"protocolVersion": "2025-06-18"}
