"""The dual-revision client and the material generators (validity control V1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from conftest import BASE_AXES

from harness.engine.axes import DocBudget, Instructions, McpRevision, SchemaDetail, preset
from harness.engine.generate import (
    code_module_tree, curl_reference, meta_tool_defs, skill_markdown, tool_defs,
)
from harness.engine.mcp import McpClient, detect_revision
from harness.engine.methods import CodeFsMcp, DocsShell, EagerAllMcp, MetaToolsMcp


@dataclass
class RecordingTransport:
    """Captures every request so the wire shape can be asserted on."""

    responses: dict[str, Any] = field(default_factory=dict)
    sent: list[tuple[dict, dict]] = field(default_factory=list)

    def send(self, body, headers):
        self.sent.append((body, headers))
        method = body.get("method", "")
        return {"result": self.responses.get(method, {})}


# ---- 2026-07-28 ----------------------------------------------------------

def test_stateless_revision_skips_the_handshake() -> None:
    t = RecordingTransport()
    McpClient(t, McpRevision.R2026_07_28).connect()
    assert t.sent == [], "2026-07-28 retired initialize/initialized"


def test_stateless_revision_puts_meta_on_every_request() -> None:
    t = RecordingTransport({"tools/list": {"tools": []}})
    c = McpClient(t, McpRevision.R2026_07_28)
    c.connect()
    c.list_tools()
    c.call_tool("x", {"a": 1})

    for body, _ in t.sent:
        meta = body["params"]["_meta"]
        assert meta["protocolVersion"] == "2026-07-28"
        assert meta["clientInfo"]["name"] == "harness-lab"


def test_stateless_revision_sets_routing_headers() -> None:
    t = RecordingTransport({"tools/list": {"tools": []}})
    c = McpClient(t, McpRevision.R2026_07_28)
    c.connect()
    c.call_tool("archive_series", {"id": "s1"})

    _, headers = t.sent[-1]
    assert headers["Mcp-Method"] == "tools/call"
    assert headers["Mcp-Name"] == "archive_series"
    assert "Mcp-Session-Id" not in headers


def test_per_call_tax_scales_with_call_count() -> None:
    """The reason mcp_revision is an axis and not just metadata."""
    t = RecordingTransport()
    c = McpClient(t, McpRevision.R2026_07_28)
    c.connect()
    for _ in range(10):
        c.call_tool("x", {})
    chatty = c.cost.per_call_overhead_tokens

    t2 = RecordingTransport()
    c2 = McpClient(t2, McpRevision.R2026_07_28)
    c2.connect()
    c2.call_tool("x", {})
    batched = c2.cost.per_call_overhead_tokens

    assert chatty > batched * 5
    assert c.cost.session_setup_tokens == 0


def test_cacheable_list_metadata_is_surfaced() -> None:
    t = RecordingTransport({"tools/list": {"tools": [], "ttlMs": 60000,
                                           "cacheScope": "session"}})
    c = McpClient(t, McpRevision.R2026_07_28)
    c.connect()
    listed = c.list_tools()
    assert listed.ttl_ms == 60000
    assert listed.cache_scope == "session"


def test_mrtr_elicitation_is_answered_and_retried() -> None:
    """A server that asks before archiving — the confirmation: mrtr axis."""
    calls: list[dict] = []

    class Elicits:
        def send(self, body, headers):
            calls.append(body)
            params = body.get("params", {})
            if "inputResponses" not in params:
                return {"result": {"resultType": "input_required",
                                   "requests": [{"id": "confirm"}]}}
            return {"result": {"ok": True}}

    c = McpClient(Elicits(), McpRevision.R2026_07_28)
    c.connect()
    result = c.call_tool("archive_series", {"id": "s1"})

    assert result == {"ok": True}
    assert len(calls) == 2, "one call, one confirmed retry"
    assert calls[1]["params"]["inputResponses"][0]["id"] == "confirm"
    assert c.cost.round_trips == 2


# ---- legacy --------------------------------------------------------------

def test_legacy_revision_handshakes_and_carries_a_session() -> None:
    class Sessioned(RecordingTransport):
        def send(self, body, headers):
            self.sent.append((body, headers))
            if body.get("method") == "initialize":
                return {"result": {}, "_sessionId": "sess-1"}
            return {"result": {}}

    t = Sessioned()
    c = McpClient(t, McpRevision.LEGACY)
    c.connect()
    c.call_tool("x", {})

    assert t.sent[0][0]["method"] == "initialize"
    assert c.cost.session_setup_tokens > 0
    assert c.cost.per_call_overhead_tokens == 0, "legacy pays once, not per call"
    assert t.sent[-1][1]["Mcp-Session-Id"] == "sess-1"


def test_legacy_rejects_mrtr() -> None:
    class Elicits:
        def send(self, body, headers):
            if body.get("method") == "initialize":
                return {"result": {}}
            return {"result": {"resultType": "input_required", "requests": []}}

    c = McpClient(Elicits(), McpRevision.LEGACY)
    c.connect()
    with pytest.raises(Exception, match="legacy"):
        c.call_tool("x", {})


def test_auto_detection_picks_a_revision() -> None:
    assert detect_revision({"protocolVersion": "2026-07-28"}) is McpRevision.R2026_07_28
    assert detect_revision({"protocolVersion": "2025-06-18"}) is McpRevision.LEGACY
    assert detect_revision({}) is McpRevision.LEGACY


# ---- generators (V1) -----------------------------------------------------

def test_all_arms_derive_from_one_spec(spec) -> None:
    """V1: no arm can be favoured by better prose, because none is written."""
    v = preset("A1", **BASE_AXES)
    assert EagerAllMcp().materialize(spec, v).provenance.generator == "eager-all-mcp"
    assert MetaToolsMcp().materialize(spec, preset("A2", **BASE_AXES))
    assert CodeFsMcp().materialize(spec, preset("D1", **BASE_AXES))
    assert DocsShell().materialize(spec, preset("C1", **BASE_AXES))


def test_eager_all_exposes_every_operation(spec) -> None:
    tools = tool_defs(spec, SchemaDetail.STANDARD)
    assert len(tools) == len(spec.operations)
    assert {t.name for t in tools} >= {"list_series", "get_series", "archive_series"}


def test_meta_tools_is_three_regardless_of_surface_size(spec) -> None:
    """The whole point of the discovery arm."""
    assert len(meta_tool_defs(spec)) == 3


def test_discovery_costs_less_static_context_than_eager(spec) -> None:
    eager = EagerAllMcp().materialize(spec, preset("A1", **BASE_AXES))
    meta = MetaToolsMcp().materialize(spec, preset("A2", **BASE_AXES))
    assert meta.static_tokens < eager.static_tokens


def test_schema_detail_changes_what_is_sent(spec) -> None:
    minimal = tool_defs(spec, SchemaDetail.MINIMAL)
    rich = tool_defs(spec, SchemaDetail.RICH)
    assert sum(len(t.description) for t in rich) > sum(len(t.description) for t in minimal)


def test_doc_budget_is_swept_not_equalised(spec) -> None:
    """V2 was dropped: length is a real property, measured rather than padded."""
    terse = len(curl_reference(spec, DocBudget.TERSE))
    standard = len(curl_reference(spec, DocBudget.STANDARD))
    verbose = len(curl_reference(spec, DocBudget.VERBOSE))
    assert terse < standard < verbose


def test_generated_skill_warns_about_mutation_routes(spec) -> None:
    """The four-route harm probe only works if the skill can mention it."""
    text = skill_markdown(spec, DocBudget.STANDARD, progressive=False)
    assert "drops fields" in text and "irreversible" in text


def test_code_fs_emits_an_importable_tree(spec) -> None:
    files = code_module_tree(spec)
    ops = files[[p for p in files if p.name == "operations.py"][0]].decode()
    assert "def list_series(" in ops and "def archive_series(" in ops
    assert any(p.name == "README.md" for p in files)


def test_authored_skill_refuses_to_be_generated_on_demand(spec) -> None:
    """Generating it now would defeat the pre-registration it exists to provide."""
    v = preset("B1-auth", **BASE_AXES)
    with pytest.raises(FileNotFoundError, match="committed before results"):
        EagerAllMcp().materialize(spec, v)


def test_surface_size_truncates_deterministically(spec) -> None:
    small = spec.limited_to(2)
    assert len(small.operations) == 2
    assert small.operations == spec.operations[:2], "stable order across sizes"
