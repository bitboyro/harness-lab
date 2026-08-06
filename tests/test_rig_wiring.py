"""The seam: every arm reaching the same catalog through its own surface.

These are the tests that were impossible before — each half was verified, the
join between them was not.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from conftest import BASE_AXES

from harness.engine.axes import (
    Confirmation, McpRevision, Transport, Variant, preset,
)
from harness.engine.mcp import McpClient
from harness.engine.packaging import Call
from harness.experiment.domain import WorldShape
from harness.experiment.http import CatalogServer
from harness.experiment.mcp_surface import McpSurface, transport_for
from harness.experiment.rig import METHOD_FOR_PRESET, RigInstance, _bound_method
from harness.experiment.server import CatalogApi

SMALL = WorldShape(studios=1, series_per_studio=1, seasons_per_series=1,
                   episodes_per_season=3)

RIG_AXES = {**BASE_AXES, "surface_size": 0}


@pytest.fixture
def rig():
    with RigInstance(seed=1, shape=SMALL) as instance:
        yield instance


# ---- every preset is runnable --------------------------------------------

@pytest.mark.parametrize(
    "name", [n for n in METHOD_FOR_PRESET if not n.endswith("-auth")]
)
def test_every_preset_builds_a_working_executor(name, rig) -> None:
    """The gap this whole module closes: no arm may be unrunnable."""
    variant = preset(name, **RIG_AXES)
    method = _bound_method(name, variant, rig)
    materials = method.materialize(rig.spec, variant)
    executor = method.executor(materials)

    assert executor is not None, f"{name} has no executor"
    assert hasattr(executor, "invoke")
    executor.teardown()


def test_tool_arms_see_the_whole_surface_and_discovery_arms_do_not(rig) -> None:
    """The mechanism RQ2 is about, visible in static cost."""
    def static(name: str) -> int:
        v = preset(name, **RIG_AXES)
        return _bound_method(name, v, rig).materialize(rig.spec, v).static_tokens

    assert static("A2") < static("A1")
    assert static("D1") < static("A1")


# ---- MCP surface ---------------------------------------------------------

def test_mcp_list_tools_matches_the_openapi_document(rig) -> None:
    """V1: the MCP arms and the curl arms must describe the same API."""
    client = rig.mcp_client(McpRevision.R2026_07_28)
    listed = client.list_tools()

    assert {t.name for t in listed.tools} == \
        {op.operation_id for op in rig.spec.operations}
    assert listed.ttl_ms and listed.cache_scope


def test_mcp_call_reaches_the_catalog(rig) -> None:
    client = rig.mcp_client(McpRevision.R2026_07_28)
    episode_id = next(iter(rig.api.world.episodes))

    result = client.call_tool("get_episode", {"episode_id": episode_id})

    assert result["status"] == 200
    assert result["structuredContent"]["id"] == episode_id


def test_mcp_write_actually_mutates_state(rig) -> None:
    """Without this the whole harm axis would be measuring nothing."""
    client = rig.mcp_client(McpRevision.R2026_07_28)
    episode = next(iter(rig.api.world.episodes.values()))

    client.call_tool("patch_episode",
                     {"episode_id": episode.id, "body": {"rating": "TV-14"}})

    assert rig.api.world.episodes[episode.id].rating == "TV-14"


def test_mcp_put_destroys_through_the_tool_surface_too(rig) -> None:
    """The destructive route must be reachable from MCP, not just from curl —
    otherwise RQ3 compares a safe surface against an unsafe one."""
    client = rig.mcp_client(McpRevision.R2026_07_28)
    episode = next(iter(rig.api.world.episodes.values()))
    assert episode.runtime_seconds > 0

    client.call_tool("replace_episode",
                     {"episode_id": episode.id, "body": {"rating": "TV-14"}})

    assert rig.api.world.episodes[episode.id].runtime_seconds == 0


def test_missing_path_parameter_is_a_422_not_a_crash(rig) -> None:
    client = rig.mcp_client(McpRevision.R2026_07_28)
    result = client.call_tool("get_episode", {})
    assert result["status"] == 422


def test_hallucinated_tool_is_an_error_result_not_a_transport_failure(rig) -> None:
    client = rig.mcp_client(McpRevision.R2026_07_28)
    result = client.call_tool("get_nonexistent_thing", {})
    assert result["isError"]


def test_legacy_revision_serves_the_same_catalog(rig) -> None:
    """Both revisions must expose identical capability, or the revision axis
    would be measuring a capability difference instead of a protocol one."""
    new = rig.mcp_client(McpRevision.R2026_07_28).list_tools()
    old = rig.mcp_client(McpRevision.LEGACY).list_tools()
    assert {t.name for t in new.tools} == {t.name for t in old.tools}


def test_mrtr_asks_before_archiving(rig) -> None:
    """M1: a server that asks before an irreversible op."""
    api = CatalogApi(seed=1, shape=SMALL)
    transport, surface = transport_for(api, rig.spec, confirmation=Confirmation.MRTR)
    episode = next(iter(api.world.episodes.values()))

    first = surface.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "archive_episode",
                                       "arguments": {"episode_id": episode.id}}})

    assert first["result"]["resultType"] == "input_required"
    assert not api.world.episodes[episode.id].archived, "must not act before asking"

    surface.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "archive_episode",
                               "arguments": {"episode_id": episode.id},
                               "inputResponses": [{"id": "confirm", "value": True}]}})

    assert api.world.episodes[episode.id].archived


def test_mrtr_does_not_gate_reads(rig) -> None:
    api = CatalogApi(seed=1, shape=SMALL)
    _, surface = transport_for(api, rig.spec, confirmation=Confirmation.MRTR)
    result = surface.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": "list_studios", "arguments": {}}})
    assert result["result"].get("resultType") != "input_required"


# ---- HTTP surface --------------------------------------------------------

def test_http_serves_the_catalog() -> None:
    api = CatalogApi(seed=1, shape=SMALL)
    with CatalogServer(api) as server:
        with urllib.request.urlopen(f"{server.base_url}/studios") as response:
            body = json.loads(response.read())
    assert body["items"] and body["total"] >= 1


def test_http_writes_reach_the_same_world() -> None:
    api = CatalogApi(seed=1, shape=SMALL)
    episode = next(iter(api.world.episodes.values()))
    with CatalogServer(api) as server:
        request = urllib.request.Request(
            f"{server.base_url}/episodes/{episode.id}",
            data=json.dumps({"rating": "TV-14"}).encode(),
            method="PATCH", headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request)
    assert api.world.episodes[episode.id].rating == "TV-14"


def test_http_query_params_are_typed_but_not_over_coerced() -> None:
    """`limit=many` must still earn its 422, or argument validity is unmeasurable."""
    api = CatalogApi(seed=1, shape=SMALL)
    with CatalogServer(api) as server:
        try:
            urllib.request.urlopen(f"{server.base_url}/episodes?limit=many")
            raise AssertionError("expected a 422")
        except urllib.error.HTTPError as e:
            assert e.code == 422


def test_each_instance_gets_its_own_port() -> None:
    """A fixed port would make parallel runs share state."""
    a, b = CatalogServer(CatalogApi()), CatalogServer(CatalogApi())
    with a, b:
        assert a.port != b.port


def test_discovery_routes_serve_the_sandbox_arms() -> None:
    """D3 reaches the triad over HTTP from inside its sandbox."""
    from harness.engine.generate import load_spec
    from harness.experiment.openapi import build_spec

    api = CatalogApi(seed=1, shape=SMALL)
    spec = load_spec(build_spec())
    with CatalogServer(api, spec=spec) as server:
        with urllib.request.urlopen(
            f"{server.base_url}/_meta/search?query=archive+an+episode"
        ) as response:
            matches = json.loads(response.read())["matches"]
        assert any(m["operation_id"] == "archive_episode" for m in matches)

        with urllib.request.urlopen(
            f"{server.base_url}/_meta/describe?operation_id=get_episode"
        ) as response:
            described = json.loads(response.read())
        assert described["method"] == "GET"
        assert "episode_id" in described["parameters"]["properties"]


# ---- isolation -----------------------------------------------------------

def test_each_run_gets_a_fresh_catalog() -> None:
    """Instance-per-run: a mutation must not survive into the next run."""
    with RigInstance(seed=1, shape=SMALL) as first:
        episode = next(iter(first.api.world.episodes.values()))
        first.api.handle("POST", f"/episodes/{episode.id}:archive")
        assert first.api.world.episodes[episode.id].archived

    with RigInstance(seed=1, shape=SMALL) as second:
        assert not second.api.world.episodes[episode.id].archived, \
            "state leaked between runs"


def test_same_seed_reproduces_the_same_ids() -> None:
    with RigInstance(seed=5, shape=SMALL) as a, RigInstance(seed=5, shape=SMALL) as b:
        assert set(a.api.world.episodes) == set(b.api.world.episodes)


def test_sandbox_env_exposes_only_the_target(rig) -> None:
    """A sandbox that can read the harness's own key is not a sandbox."""
    env = rig.sandbox_env()
    assert set(env) == {"BASE_URL", "TARGET_BASE_URL"}
    assert env["BASE_URL"].startswith("http://127.0.0.1:")
