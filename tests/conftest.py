from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from harness.engine.axes import (
    Caching, DocBudget, ErrorDetail, McpRevision, ResponseShape, SchemaDetail,
)
from harness.engine.generate import load_spec
from harness.engine.packaging import Call
from harness.engine.provider import Capabilities, Completion, ProviderConfig, Usage

BASE_AXES = dict(
    schema_detail=SchemaDetail.STANDARD,
    response_shape=ResponseShape.AS_IS,
    error_detail=ErrorDetail.FIELD_SCOPED,
    doc_budget=DocBudget.STANDARD,
    surface_size=10,
    model="gpt-5-mini",
    reasoning_effort="low",
    temperature=0.0,
    caching=Caching.OFF,
    repeats=1,
    mcp_revision=McpRevision.R2026_07_28,
)

STUB_SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Stub Catalog", "version": "1"},
    "paths": {
        "/series": {
            "get": {
                "operationId": "list_series",
                "summary": "List all series.",
                "parameters": [
                    {"name": "studio", "in": "query", "schema": {"type": "string"},
                     "description": "Filter by studio id."},
                ],
                "responses": {"200": {"description": "ok"},
                              "422": {"description": "bad filter"}},
            }
        },
        "/series/{id}": {
            "get": {
                "operationId": "get_series",
                "summary": "Fetch one series.",
                "parameters": [
                    {"name": "id", "in": "path", "required": True,
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "ok"}, "404": {"description": "gone"}},
            },
            "patch": {
                "operationId": "patch_series",
                "summary": "Partially update a series.",
                "parameters": [
                    {"name": "id", "in": "path", "required": True,
                     "schema": {"type": "string"}},
                ],
                "requestBody": {"required": True, "content": {
                    "application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "ok"}},
            },
            "put": {
                "operationId": "replace_series",
                "summary": "Replace a series. Drops unspecified fields.",
                "parameters": [
                    {"name": "id", "in": "path", "required": True,
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "ok"}},
            },
        },
        "/series/{id}:archive": {
            "post": {
                "operationId": "archive_series",
                "summary": "Archive a series. Irreversible.",
                "parameters": [
                    {"name": "id", "in": "path", "required": True,
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        },
    },
}


@pytest.fixture
def spec():
    return load_spec(STUB_SPEC)


@dataclass
class ScriptedProvider:
    """A provider that replays a fixed script. No network, no key.

    Lets the whole loop be tested deterministically — the alternative is testing
    the loop only when someone is willing to spend money, which means not
    testing it.
    """

    script: list[Completion]
    name: str = "scripted"
    seen: list[list[dict[str, Any]]] = field(default_factory=list)
    _cursor: int = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(True, True, True, False)

    def price_per_mtok(self, model: str) -> tuple[float, float]:
        return (1.0, 10.0)

    def submit(self, messages, tools, config: ProviderConfig) -> Completion:
        self.seen.append(list(messages))
        if self._cursor >= len(self.script):
            return say("FINAL ANSWER: done")
        item = self.script[self._cursor]
        self._cursor += 1
        return item


def say(text: str) -> Completion:
    return Completion(text=text, tool_calls=(), usage=Usage(100, 0, 20, 0),
                      stop_reason="stop")


def call(tool: str, **args: Any) -> Completion:
    return Completion(text=None, tool_calls=(Call(tool=tool, args=args),),
                      usage=Usage(100, 0, 20, 0), stop_reason="tool_calls")


def code(body: str) -> Completion:
    return Completion(text=f"```python\n{body}\n```", tool_calls=(),
                      usage=Usage(100, 0, 20, 0), stop_reason="tool_calls")
