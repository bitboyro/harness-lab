"""T1 lint rules. Each test names the agent failure the rule predicts."""

from __future__ import annotations

import pytest

from harness.engine import rules
from harness.engine.generate import load_spec
from harness.engine.lint import Confidence, scorecard


@pytest.fixture(autouse=True)
def registered():
    rules.register_defaults()


def find(spec, rule_id):
    return [f for f in scorecard(spec).findings if f.rule_id == rule_id]


def test_missing_description_flagged(spec) -> None:
    bare = load_spec({
        "openapi": "3.1.0", "info": {"title": "T", "version": "1"},
        "paths": {"/x/{id}": {"get": {"operationId": "op_x", "responses": {"200": {}}}}},
    })
    assert find(bare, "no-description")


def test_documented_operation_not_flagged(spec) -> None:
    assert not find(spec, "no-description")


def test_unbounded_collection_flagged(spec) -> None:
    """The stub's /series has no pagination — that is the point of the rule."""
    assert find(spec, "unbounded-collection")


def test_paginated_collection_not_flagged() -> None:
    paged = load_spec({
        "openapi": "3.1.0", "info": {"title": "T", "version": "1"},
        "paths": {"/x": {"get": {
            "operationId": "list_x", "summary": "List",
            "parameters": [{"name": "limit", "in": "query",
                            "schema": {"type": "integer"}, "description": "Max"}],
            "responses": {"200": {"description": "ok"}, "422": {"description": "bad"}},
        }}},
    })
    assert not find(paged, "unbounded-collection")


def test_ambiguous_mutation_routes_flagged(spec) -> None:
    """PATCH + PUT on the same resource, with PUT silently dropping fields."""
    findings = find(spec, "ambiguous-mutation-route")
    assert findings
    assert "drops unspecified fields" in findings[0].message


def test_large_surface_without_discovery_flagged() -> None:
    paths = {
        f"/r{i}": {"get": {"operationId": f"get_r{i}", "summary": "s",
                           "responses": {"200": {"description": "ok"}}}}
        for i in range(rules.DISCOVERY_THRESHOLD + 5)
    }
    big = load_spec({"openapi": "3.1.0", "info": {"title": "T", "version": "1"},
                     "paths": paths})
    assert find(big, "no-discovery-layer")


def test_small_surface_not_flagged(spec) -> None:
    assert not find(spec, "no-discovery-layer")


def test_name_collisions_flagged() -> None:
    colliding = load_spec({
        "openapi": "3.1.0", "info": {"title": "T", "version": "1"},
        "paths": {
            "/a": {"get": {"operationId": "list_series", "summary": "s",
                           "responses": {"200": {"description": "ok"}}}},
            "/b": {"get": {"operationId": "listSeries", "summary": "s",
                           "responses": {"200": {"description": "ok"}}}},
        },
    })
    assert find(colliding, "name-collision")


def test_every_rule_is_currently_heuristic(spec) -> None:
    """Nothing has been measured yet. The scorecard must not imply otherwise."""
    card = scorecard(spec)
    assert card.rules_measured == 0
    assert all(f.confidence is Confidence.HEURISTIC for f in card.findings)
    assert "heuristic" in card.footer()


def test_findings_are_ordered_by_severity(spec) -> None:
    severities = [f.severity for f in scorecard(spec).findings]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])


def test_lint_needs_no_model_and_no_key(spec) -> None:
    """T1 is the free tier: it must never reach for a provider."""
    import os
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        assert scorecard(spec) is not None
    finally:
        if saved:
            os.environ["OPENAI_API_KEY"] = saved
