"""Executors: how a call physically happens.

One per ``invocation`` value, plus the two controls. The interceptor wrapping
them all is what gives field mode a harm signal on APIs whose state cannot be
diffed.

Sandboxing is subprocess-per-run for the controlled phases: the API is
in-memory, there are no real credentials, and there is no network egress, so
container isolation would buy nothing. Field mode against real targets is where
containers earn their cost (D3).

Contract: archive/reference/packaging-axes.md#plugin-interface
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .mcp import McpClient, McpError
from .mcp.transport import TransportError
from .packaging import Call, Materials, Result

DEFAULT_TIMEOUT_S = 30.0


class ForbiddenCall(RuntimeError):
    """A call the pack declared out of bounds."""


def _matches(pattern: str, call: Call) -> bool:
    """Patterns match either a tool name or a 'METHOD /path' string."""
    if call.tool and fnmatch.fnmatch(call.tool, pattern):
        return True
    if call.path:
        target = f"{(call.method or 'GET').upper()} {call.path}"
        if fnmatch.fnmatch(target, pattern) or fnmatch.fnmatch(call.path, pattern):
            return True
    if call.raw and fnmatch.fnmatch(call.raw, pattern):
        return True
    return False


@dataclass
class GuardedExecutor:
    """Wraps any executor with the pack's forbidden-call bounds.

    A blocked call is recorded as an attempt, not silently dropped. The attempt
    *is* the measurement: on a real API you cannot diff state, so "the agent
    tried to archive the parent season" is the harm signal you get, and throwing
    it away would leave field mode with no safety story at all.
    """

    inner: Any
    forbidden: tuple[str, ...] = ()
    blocked: list[Call] = field(default_factory=list)

    def invoke(self, call: Call) -> Result:
        for pattern in self.forbidden:
            if _matches(pattern, call):
                self.blocked.append(call)
                return Result(
                    status=None,
                    body=None,
                    latency_ms=0.0,
                    error=f"blocked by forbidden_calls: {pattern!r}",
                )
        return self.inner.invoke(call)

    def teardown(self) -> None:
        self.inner.teardown()


#: A JSON-RPC fault is the server rejecting the *request*, which is a client
#: error in the same sense a 400 is — the agent asked for something the surface
#: would not do. Mapping the JSON-RPC codes onto HTTP keeps `is_client_error`
#: (400-499) meaningful on MCP arms; the old blanket 500 fell outside it, so
#: every malformed MCP call was invisible to the 4xx metrics.
_JSONRPC_STATUS = {
    -32700: 400,  # parse error
    -32600: 400,  # invalid request
    -32601: 404,  # method not found
    -32602: 422,  # invalid params
    -32603: 500,  # internal error — genuinely the server's fault
}


def _jsonrpc_status(message: str) -> int:
    """Recover the JSON-RPC code from a stringified error object."""
    for code, status in _JSONRPC_STATUS.items():
        if f"'code': {code}" in message or f'"code": {code}' in message:
            return status
    return 400


@dataclass
class McpToolCallExecutor:
    """Native function calling over MCP. Both revisions."""

    client: McpClient
    known_tools: frozenset[str] = frozenset()

    def invoke(self, call: Call) -> Result:
        if not call.tool:
            return Result(None, None, 0.0, error="tool-call executor needs a tool name")
        started = time.perf_counter()
        try:
            body = self.client.call_tool(call.tool, call.args)
            status, error = _tool_result_status(body)
        except McpError as e:
            # The server answered, and the answer was "no". That is the agent
            # getting a call wrong, not the transport breaking.
            body, status, error = None, _jsonrpc_status(str(e)), str(e)
        except TransportError as e:
            # HTTP or network failure underneath JSON-RPC. Previously this
            # propagated and killed the whole run, so one flaky response lost
            # every turn that came before it (gap §3.3 #3). It is one failed
            # call; the agent gets to see it and carry on, and the run is only
            # void if the classifier says the *matrix* is broken.
            body, status, error = None, None, f"transport: {e}"
        latency = (time.perf_counter() - started) * 1000
        return Result(status=status, body=body, latency_ms=latency, error=error)

    def teardown(self) -> None:
        pass


def _tool_result_status(body: Any) -> tuple[int, str | None]:
    """Read the tool result's own verdict rather than assuming success.

    A JSON-RPC call that succeeds can still carry a tool result that failed —
    `isError: true`, or an embedded HTTP `status`. Reporting a flat 200 meant
    the mock's 4xx bodies never reached the error-recovery metrics on MCP arms,
    so those arms looked cleaner than the shell and code arms measuring the
    same API (gap §3.3 #4).
    """
    if not isinstance(body, dict):
        return 200, None
    status = body.get("status")
    if not isinstance(status, int):
        # A tool that flags an error without naming a status: 400 is the
        # honest floor, since the surface refused the call as asked.
        status = 400 if body.get("isError") else 200
    if status < 400:
        return status, None
    text = body.get("structuredContent")
    if text is None:
        content = body.get("content") or []
        text = content[0].get("text") if content and isinstance(content[0], dict) else None
    return status, f"tool error {status}: {str(text)[:200]}"


@dataclass
class HttpExecutor:
    """Direct HTTP, used by Z1 replay and by in-process targets."""

    send: Callable[[str, str, dict[str, Any]], tuple[int, Any]]

    def invoke(self, call: Call) -> Result:
        started = time.perf_counter()
        try:
            status, body = self.send(call.method or "GET", call.path or "/", call.args)
            error = None
        except Exception as e:  # noqa: BLE001 — a target failure is data, not a crash
            status, body, error = 500, None, str(e)
        return Result(status, body, (time.perf_counter() - started) * 1000, error)

    def teardown(self) -> None:
        pass


@dataclass
class SandboxExecutor:
    """Runs model-authored shell or code in a scratch directory.

    Shared by the C arms (``invocation: shell`` — freehand curl against written
    docs) and the D arms (``invocation: code`` — code against a generated module
    tree). The mechanisms differ but the containment does not.

    The environment is emptied rather than inherited: a sandbox that can read
    the harness's own API keys is not a sandbox.
    """

    materials: Materials
    interpreter: tuple[str, ...]
    timeout_s: float = DEFAULT_TIMEOUT_S
    env: dict[str, str] = field(default_factory=dict)
    _workdir: Path | None = None

    def __post_init__(self) -> None:
        self._workdir = Path(tempfile.mkdtemp(prefix="harness-sandbox-"))
        for rel, content in self.materials.sandbox_files.items():
            target = self._workdir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

    def invoke(self, call: Call) -> Result:
        if not call.raw:
            return Result(None, None, 0.0, error="sandbox executor needs a command body")

        script = self._workdir / f"step-{int(time.time() * 1e6)}"
        script.write_text(call.raw)

        started = time.perf_counter()
        try:
            proc = subprocess.run(  # noqa: S603 — the point is to run agent output
                [*self.interpreter, str(script)],
                cwd=self._workdir,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": str(self._workdir),
                    **self.env,
                },
            )
        except subprocess.TimeoutExpired:
            return Result(
                None, None, self.timeout_s * 1000,
                error=f"timed out after {self.timeout_s}s",
            )
        latency = (time.perf_counter() - started) * 1000

        return Result(
            status=proc.returncode,
            body={"stdout": proc.stdout, "stderr": proc.stderr},
            latency_ms=latency,
            error=None if proc.returncode == 0 else proc.stderr[:500] or "non-zero exit",
        )

    def teardown(self) -> None:
        if self._workdir and self._workdir.exists():
            shutil.rmtree(self._workdir, ignore_errors=True)


def shell_executor(materials: Materials, **kw: Any) -> SandboxExecutor:
    return SandboxExecutor(materials, interpreter=("/bin/bash",), **kw)


def code_executor(materials: Materials, **kw: Any) -> SandboxExecutor:
    """Python, per F4 — one runtime for harness and sandbox.

    Known cost: the literature this positions against uses TypeScript, so our
    numbers are not directly comparable to theirs. A TS executor behind this same
    interface is the robustness check that would settle whether the difference
    matters.
    """
    return SandboxExecutor(materials, interpreter=(sys.executable,), **kw)


@dataclass
class NullExecutor:
    """Z0: no tool access at all.

    Any call is itself the finding — in controlled mode it means the arm is
    misconfigured; the parametric baseline is supposed to have nothing to call.
    """

    def invoke(self, call: Call) -> Result:
        return Result(None, None, 0.0, error="Z0 has no tool access")

    def teardown(self) -> None:
        pass


@dataclass
class PreExecutedExecutor:
    """Z1: the gold sequence has already run; the model only synthesises.

    Establishes the achievable ceiling per task, which is what makes a low
    success rate elsewhere interpretable — without it you cannot tell a bad
    packaging from an impossible task.
    """

    results: tuple[Result, ...]
    _cursor: int = 0

    def invoke(self, call: Call) -> Result:
        if self._cursor >= len(self.results):
            return Result(None, None, 0.0, error="gold sequence exhausted")
        result = self.results[self._cursor]
        self._cursor += 1
        return result

    def teardown(self) -> None:
        pass


def transcript(materials: Materials) -> str:
    """The sandbox file tree, rendered for a context block."""
    return json.dumps(sorted(str(p) for p in materials.sandbox_files), indent=2)
