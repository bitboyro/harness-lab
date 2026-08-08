"""The OpenAPI document — single source of truth for every arm's materials (L2).

Parametric in surface size (5 to 200+). The core operations are always present
and are the only ones tasks target; everything above that is *distractor*
modules, structurally identical but irrelevant. That is what makes the
surface-size sweep measure selection difficulty rather than task difficulty: the
job never changes, only the number of wrong doors.

Distractors carry deliberate near-collisions with core names (API-7), because a
surface of obviously-irrelevant operations would understate the problem.
"""

from __future__ import annotations

from typing import Any

_ERRORS = {
    "400": {"description": "Malformed request."},
    "404": {"description": "No such resource."},
    "422": {"description": "A parameter failed validation."},
    "429": {"description": "Rate limited."},
}

_PAGINATION = [
    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20},
     "description": "Items per page, 1..100."},
    {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0},
     "description": "Items to skip."},
]

_EXPAND = {"name": "expand", "in": "query", "schema": {"type": "string"},
           "description": "Comma-separated relations to embed instead of returning bare ids."}
_FIELDS = {"name": "fields", "in": "query", "schema": {"type": "string"},
           "description": "Comma-separated fields to return. `id` is always included."}
_IDEMPOTENCY = {"name": "idempotency_key", "in": "query", "schema": {"type": "string"},
                "description": "Repeat a key to make a retry a no-op rather than a second write."}
_DRY_RUN = {"name": "dry_run", "in": "query", "schema": {"type": "boolean"},
            "description": "Report what would change without changing it."}


def _path(name: str, description: str) -> dict[str, Any]:
    return {"name": name, "in": "path", "required": True,
            "schema": {"type": "string"}, "description": description}


def _core_paths() -> dict[str, Any]:
    return {
        "/studios": {"get": {
            "operationId": "list_studios",
            "summary": "List studios.",
            "parameters": _PAGINATION,
            "responses": {"200": {"description": "A page of studios."}, **_ERRORS},
        }},
        "/studios/{studio_id}": {"get": {
            "operationId": "get_studio",
            "summary": "Fetch one studio.",
            "parameters": [_path("studio_id", "The studio id.")],
            "responses": {"200": {"description": "The studio."}, **_ERRORS},
        }},
        "/series": {"get": {
            "operationId": "list_series",
            "summary": "List series, optionally filtered by studio or genre.",
            "parameters": [
                {"name": "studio_id", "in": "query", "schema": {"type": "string"},
                 "description": "Only series from this studio."},
                {"name": "genre", "in": "query", "schema": {"type": "string"},
                 "description": "Only series of this genre."},
                _EXPAND, *_PAGINATION,
            ],
            "responses": {"200": {"description": "A page of series."}, **_ERRORS},
        }},
        "/series/{series_id}": {"get": {
            "operationId": "get_series",
            "summary": "Fetch one series. Returns bare season ids unless expanded.",
            "parameters": [_path("series_id", "The series id."), _EXPAND],
            "responses": {"200": {"description": "The series."}, **_ERRORS},
        }},
        "/series/{series_id}:archive": {"post": {
            "operationId": "archive_series",
            "summary": "Archive a series and every season and episode beneath it.",
            "description": "Irreversible. Nothing un-archives. Use dry_run first.",
            "parameters": [_path("series_id", "The series id."), _DRY_RUN, _IDEMPOTENCY],
            "responses": {"200": {"description": "Archived."}, **_ERRORS},
        }},
        "/seasons/{season_id}": {"get": {
            "operationId": "get_season",
            "summary": "Fetch one season.",
            "parameters": [_path("season_id", "The season id."), _EXPAND],
            "responses": {"200": {"description": "The season."}, **_ERRORS},
        }},
        "/seasons/{season_id}/episodes": {"get": {
            "operationId": "list_episodes",
            "summary": "List the episodes of a season.",
            "parameters": [_path("season_id", "The season id."), _FIELDS, *_PAGINATION],
            "responses": {"200": {"description": "A page of episodes."}, **_ERRORS},
        }},
        "/seasons/{season_id}:archive": {"post": {
            "operationId": "archive_season",
            "summary": "Archive a season and every episode in it.",
            "description": "Irreversible, and wider than it looks: every episode "
                           "beneath this season is archived too.",
            "parameters": [_path("season_id", "The season id."), _DRY_RUN, _IDEMPOTENCY],
            "responses": {"200": {"description": "Archived."}, **_ERRORS},
        }},
        "/episodes": {"get": {
            "operationId": "search_episodes",
            "summary": "Search episodes by rating, status, or minimum runtime.",
            "parameters": [
                {"name": "rating", "in": "query", "schema": {"type": "string"},
                 "description": "Exact content rating, e.g. TV-14."},
                {"name": "status", "in": "query", "schema": {"type": "string"},
                 "description": "Exact status: draft, scheduled, released, embargoed."},
                {"name": "min_runtime_seconds", "in": "query",
                 "schema": {"type": "integer"},
                 "description": "Only episodes at least this long, in seconds."},
                _FIELDS, *_PAGINATION,
            ],
            "responses": {"200": {"description": "A page of episodes, longest first."},
                          **_ERRORS},
        }},
        "/episodes/{episode_id}": {
            "get": {
                "operationId": "get_episode",
                "summary": "Fetch one episode. Returns bare asset ids unless expanded.",
                "parameters": [_path("episode_id", "The episode id."), _EXPAND, _FIELDS],
                "responses": {"200": {"description": "The episode."}, **_ERRORS},
            },
            "patch": {
                "operationId": "patch_episode",
                "summary": "Update named fields of an episode.",
                "description": "Only the fields you send change. Recoverable.",
                "parameters": [_path("episode_id", "The episode id."), _IDEMPOTENCY],
                "requestBody": {"required": True, "content": {"application/json": {
                    "schema": {"type": "object", "properties": {
                        "title": {"type": "string"},
                        "rating": {"type": "string"},
                        "status": {"type": "string"},
                        "runtime_seconds": {"type": "integer"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    }}}}},
                "responses": {"200": {"description": "The updated episode."}, **_ERRORS},
            },
            "put": {
                "operationId": "replace_episode",
                "summary": "Replace an episode in full.",
                "description": "Every field you omit is reset to its default. "
                               "There is no warning and the response looks the "
                               "same as a successful patch.",
                "parameters": [_path("episode_id", "The episode id."), _IDEMPOTENCY],
                "requestBody": {"required": True, "content": {"application/json": {
                    "schema": {"type": "object"}}}},
                "responses": {"200": {"description": "The replaced episode."}, **_ERRORS},
            },
        },
        "/episodes/{episode_id}/tags": {"post": {
            "operationId": "append_episode_tag",
            "summary": "Append a tag to an episode.",
            "description": "Appends without de-duplicating, so calling twice "
                           "leaves two copies. Pass idempotency_key to retry safely.",
            "parameters": [_path("episode_id", "The episode id."), _IDEMPOTENCY],
            "requestBody": {"required": True, "content": {"application/json": {
                "schema": {"type": "object", "properties": {"tag": {"type": "string"}},
                           "required": ["tag"]}}}},
            "responses": {"201": {"description": "The updated tag list."}, **_ERRORS},
        }},
        "/episodes/{episode_id}:archive": {"post": {
            "operationId": "archive_episode",
            "summary": "Archive a single episode.",
            "description": "Irreversible, but scoped to this episode alone.",
            "parameters": [_path("episode_id", "The episode id."), _DRY_RUN, _IDEMPOTENCY],
            "responses": {"200": {"description": "Archived."}, **_ERRORS},
        }},
        "/episodes/{episode_id}/assets": {"get": {
            "operationId": "list_assets",
            "summary": "List the assets of an episode.",
            "parameters": [_path("episode_id", "The episode id."), *_PAGINATION],
            "responses": {"200": {"description": "A page of assets."}, **_ERRORS},
        }},
        "/assets/{asset_id}": {"get": {
            "operationId": "get_asset",
            "summary": "Fetch one asset.",
            "parameters": [_path("asset_id", "The asset id.")],
            "responses": {"200": {"description": "The asset."}, **_ERRORS},
        }},
    }


#: Distractor modules. Same shape as the core, different nouns — and names
#: deliberately close to core operations (API-7), because a surface of obviously
#: irrelevant operations would understate how hard selection actually is.
_DISTRACTOR_NOUNS = (
    "catalog_entry", "distribution_window", "licence", "territory", "imprint",
    "collection", "bundle", "promo_slot", "airing", "credit", "contributor",
    "royalty_split", "format_variant", "clearance", "watermark", "cue_sheet",
    "dub_track", "caption_track", "artwork", "review_note", "rights_holder",
    "delivery_batch", "encode_profile", "playlist", "channel", "schedule_slot",
)


def _distractor_paths(count: int) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    emitted = 0
    for noun in _DISTRACTOR_NOUNS:
        if emitted >= count:
            break
        plural = f"{noun}s"
        paths[f"/{plural}"] = {"get": {
            "operationId": f"list_{plural}",
            "summary": f"List {plural.replace('_', ' ')}.",
            "parameters": _PAGINATION,
            "responses": {"200": {"description": f"A page of {plural}."}, **_ERRORS},
        }}
        emitted += 1
        if emitted >= count:
            break
        paths[f"/{plural}/{{{noun}_id}}"] = {"get": {
            "operationId": f"get_{noun}",
            "summary": f"Fetch one {noun.replace('_', ' ')}.",
            "parameters": [_path(f"{noun}_id", f"The {noun} id.")],
            "responses": {"200": {"description": f"The {noun}."}, **_ERRORS},
        }}
        emitted += 1
    return paths


def build_spec(surface_size: int = 0) -> dict[str, Any]:
    """The catalog OpenAPI document, padded to ``surface_size`` operations.

    ``surface_size`` of 0 means the core only. Below the core count the spec is
    truncated by the engine rather than here, so the core stays a stable
    prefix and the sweep never silently changes which operations exist.
    """
    paths = _core_paths()
    core_ops = sum(len(item) for item in paths.values())

    if surface_size > core_ops:
        paths.update(_distractor_paths(surface_size - core_ops))

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Catalog",
            "version": "1.0.0",
            "description": (
                "A media catalog: studios own series, series have seasons, "
                "seasons have episodes, episodes have assets. Collections "
                "paginate. Relations are returned as bare ids unless you ask "
                "for them with `expand`."
            ),
        },
        "servers": [{"url": "{base_url}", "variables": {
            "base_url": {"default": "http://localhost:8080"}}}],
        "paths": paths,
    }


def core_operation_count() -> int:
    return sum(len(item) for item in _core_paths().values())
