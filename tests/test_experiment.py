"""The controlled rig: seeded world, four mutation routes, matched pairs, Z0."""

from __future__ import annotations

import pytest

from harness.engine.axes import ErrorDetail, ResponseShape
from harness.engine.generate import load_spec
from harness.engine.taskpack import TaskPack
from harness.experiment.domain import WorldShape, build_world
from harness.experiment.gate import (
    Z0_THRESHOLD, ContaminationError, GateResult, evaluate, require_pass,
)
from harness.experiment.openapi import build_spec, core_operation_count
from harness.experiment.server import CatalogApi
from harness.experiment.tasks import build_cores, build_pack, build_tasks


@pytest.fixture
def api():
    return CatalogApi(seed=42, shape=WorldShape(studios=2, series_per_studio=2,
                                                seasons_per_series=2,
                                                episodes_per_season=5))


# ---- determinism ---------------------------------------------------------

def test_same_seed_gives_the_same_world() -> None:
    """Instance-per-run only works if the fixture is byte-identical each time."""
    a = build_world(7).snapshot()
    b = build_world(7).snapshot()
    assert a == b


def test_different_seeds_give_different_worlds() -> None:
    assert build_world(1).snapshot() != build_world(2).snapshot()


def test_names_are_pronounceable_not_gibberish() -> None:
    """Random tokens would add noise unrelated to packaging."""
    world = build_world(3)
    titles = [s.title for s in world.series.values()]
    assert all(" " in t and t[0].isupper() for t in titles)
    assert len(set(titles)) == len(titles), "titles must be unique to be referable"


def test_ids_are_opaque() -> None:
    """An id inferable from its entity would let a task be answered by guessing."""
    world = build_world(5)
    for episode in world.episodes.values():
        assert episode.id.startswith("ep_")
        assert not any(word.lower() in episode.id.lower()
                       for word in episode.title.split())


def test_runtimes_are_unguessable() -> None:
    """Unguessable means a wide, flat distribution — not the absence of any
    round number. A runtime that happens to divide by 60 is still one of
    thousands of possibilities; what would be guessable is a *clustering* on
    tidy values, so that is what this asserts."""
    world = build_world(9)
    runtimes = [e.runtime_seconds for e in world.episodes.values()]
    distinct = set(runtimes)

    assert len(distinct) > 20, "a small set of values would be guessable"
    assert max(distinct) - min(distinct) > 1_000, "the range must be wide"

    # Round values must appear no more often than chance (~1/60), not never.
    round_share = sum(1 for r in runtimes if r % 60 == 0) / len(runtimes)
    assert round_share < 0.1, "runtimes must not cluster on tidy values"

    # And no single value may dominate, which would make one guess pay off.
    from collections import Counter
    assert Counter(runtimes).most_common(1)[0][1] / len(runtimes) < 0.1


# ---- structural requirements ---------------------------------------------

def test_relations_are_bare_ids_until_expanded(api) -> None:
    """API-3: nesting costs a call unless the agent asks for expansion."""
    series_id = next(iter(api.world.series))
    plain = api.handle("GET", f"/series/{series_id}").body
    assert "season_ids" in plain and "seasons" not in plain

    expanded = api.handle("GET", f"/series/{series_id}", {"expand": "seasons"}).body
    assert "seasons" in expanded and "season_ids" not in expanded


def test_collections_paginate(api) -> None:
    body = api.handle("GET", "/episodes", {"limit": 2}).body
    assert len(body["items"]) == 2
    assert body["total"] > 2
    assert body["next_offset"] == 2


def test_sparse_fieldsets(api) -> None:
    episode_id = next(iter(api.world.episodes))
    body = api.handle("GET", f"/episodes/{episode_id}",
                      {"fields": "runtime_seconds"}).body
    assert set(body) == {"id", "runtime_seconds"}


def test_idempotency_key_makes_a_retry_a_noop(api) -> None:
    """API-9: 'intended one write' must be distinguishable from 'wrote twice'."""
    episode_id = next(iter(api.world.episodes))
    before = len(api.world.episodes[episode_id].tags)
    for _ in range(3):
        api.handle("POST", f"/episodes/{episode_id}/tags",
                   {"body": {"tag": "x"}, "idempotency_key": "k1"})
    assert len(api.world.episodes[episode_id].tags) == before + 1


def test_append_without_a_key_duplicates(api) -> None:
    """The un-guarded path must actually be unsafe, or the probe is toothless."""
    episode_id = next(iter(api.world.episodes))
    before = len(api.world.episodes[episode_id].tags)
    api.handle("POST", f"/episodes/{episode_id}/tags", {"body": {"tag": "x"}})
    api.handle("POST", f"/episodes/{episode_id}/tags", {"body": {"tag": "x"}})
    assert len(api.world.episodes[episode_id].tags) == before + 2


def test_dry_run_changes_nothing(api) -> None:
    season_id = next(iter(api.world.seasons))
    before = api.snapshot()
    body = api.handle("POST", f"/seasons/{season_id}:archive", {"dry_run": True}).body
    assert body["dry_run"] and body["would_archive"]
    assert api.snapshot() == before


# ---- the four mutation routes --------------------------------------------

def test_patch_changes_only_named_fields(api) -> None:
    episode = next(iter(api.world.episodes.values()))
    runtime, title = episode.runtime_seconds, episode.title

    api.handle("PATCH", f"/episodes/{episode.id}", {"body": {"rating": "TV-14"}})

    assert episode.rating == "TV-14"
    assert episode.runtime_seconds == runtime, "patch must not touch other fields"
    assert episode.title == title


def test_put_silently_drops_unspecified_fields(api) -> None:
    """The destructive-write signal the harm axis is built on.

    No error, no warning, and a 200 that looks exactly like a successful patch.
    """
    episode = next(iter(api.world.episodes.values()))
    assert episode.runtime_seconds > 0

    response = api.handle("PUT", f"/episodes/{episode.id}",
                          {"body": {"rating": "TV-14"}})

    assert response.status == 200, "the destruction is not reported as an error"
    assert episode.rating == "TV-14"
    assert episode.runtime_seconds == 0, "runtime was silently reset"
    assert episode.title == ""


def test_archiving_a_season_archives_every_episode(api) -> None:
    """Blast radius: reaching for the wrong route destroys far more than asked."""
    season_id = next(iter(api.world.seasons))
    episodes = api.world.episodes_of(season_id)
    assert not any(e.archived for e in episodes)

    api.handle("POST", f"/seasons/{season_id}:archive")

    assert all(e.archived for e in episodes)
    assert len(episodes) > 1, "fan-out must be wide enough to matter"


def test_archiving_one_episode_leaves_its_siblings_alone(api) -> None:
    season_id = next(iter(api.world.seasons))
    episodes = api.world.episodes_of(season_id)
    target = episodes[0]

    api.handle("POST", f"/episodes/{target.id}:archive")

    assert target.archived
    assert not any(e.archived for e in episodes[1:])


def test_all_four_routes_reach_the_same_field(api) -> None:
    """The core tool-surface stress test: one change, four doors."""
    episode = next(iter(api.world.episodes.values()))
    assert api.handle("PATCH", f"/episodes/{episode.id}",
                      {"body": {"tags": ["a"]}}).status == 200
    assert api.handle("PUT", f"/episodes/{episode.id}",
                      {"body": {"tags": ["b"]}}).status == 200
    assert api.handle("POST", f"/episodes/{episode.id}/tags",
                      {"body": {"tag": "c"}}).status == 201
    assert api.handle("POST", f"/episodes/{episode.id}:archive").status == 200


# ---- affordance axes (G4) ------------------------------------------------

def test_error_detail_axis_changes_the_response_body() -> None:
    shape = WorldShape(studios=1, series_per_studio=1, seasons_per_series=1,
                       episodes_per_season=2)
    terse = CatalogApi(seed=1, shape=shape, error_detail=ErrorDetail.TERSE)
    helpful = CatalogApi(seed=1, shape=shape,
                         error_detail=ErrorDetail.FIELD_SCOPED_REMEDY)

    episode_id = next(iter(terse.world.episodes))
    bad = {"body": {"rating": "NOT-A-RATING"}}

    t = terse.handle("PATCH", f"/episodes/{episode_id}", bad).body
    h = helpful.handle("PATCH", f"/episodes/{episode_id}", bad).body

    assert t["message"] == "validation failed"
    assert "rating" in h["message"]
    assert "detail" in h and "NOT-A-RATING" in h["detail"]


def test_response_shape_axis_changes_payload_size(api) -> None:
    shape = WorldShape(studios=1, series_per_studio=1, seasons_per_series=1,
                       episodes_per_season=3)
    full = CatalogApi(seed=2, shape=shape, response_shape=ResponseShape.AS_IS)
    sparse = CatalogApi(seed=2, shape=shape, response_shape=ResponseShape.SPARSE)
    episode_id = next(iter(full.world.episodes))

    assert len(str(sparse.handle("GET", f"/episodes/{episode_id}").body)) < \
        len(str(full.handle("GET", f"/episodes/{episode_id}").body))


def test_invalid_pagination_is_a_422_not_a_crash(api) -> None:
    assert api.handle("GET", "/episodes", {"limit": "many"}).status == 422
    assert api.handle("GET", "/episodes", {"limit": 9999}).status == 422


def test_unknown_route_is_a_404(api) -> None:
    assert api.handle("GET", "/nonexistent").status == 404


# ---- spec ----------------------------------------------------------------

def test_spec_parses_with_the_engine_loader() -> None:
    spec = load_spec(build_spec())
    assert spec.title == "Catalog"
    assert len(spec.operations) == core_operation_count()


def test_surface_size_pads_with_distractors_and_keeps_the_core() -> None:
    """The task never changes; only the number of wrong doors does."""
    core = load_spec(build_spec())
    big = load_spec(build_spec(surface_size=50))

    assert len(big.operations) >= 50
    core_ids = {o.operation_id for o in core.operations}
    assert core_ids <= {o.operation_id for o in big.operations}


def test_every_spec_operation_is_routable(api) -> None:
    """A documented operation that 404s would poison hallucination metrics."""
    spec = load_spec(build_spec())
    world = api.world
    sample = {
        "studio_id": next(iter(world.studios)),
        "series_id": next(iter(world.series)),
        "season_id": next(iter(world.seasons)),
        "episode_id": next(iter(world.episodes)),
        "asset_id": next(iter(world.assets)),
    }
    for op in spec.operations:
        path = op.path
        for key, value in sample.items():
            path = path.replace("{" + key + "}", value)
        assert "{" not in path, f"unsubstituted parameter in {op.operation_id}"
        response = api.handle(op.method, path, {"body": {"tag": "t"}})
        assert response.status != 404, f"{op.operation_id} is documented but unroutable"


# ---- matched pairs -------------------------------------------------------

def test_one_core_yields_five_matched_terminals(api) -> None:
    core = build_cores(api.world, 1, seed=0)[0]
    tasks = build_tasks(core, api.world)

    assert [t.task_class for t in tasks] == \
        ["R", "W-safe", "W-lossy", "W-irrev", "RW-fan"]
    difficulties = {tuple(sorted(t.difficulty.items())) for t in tasks}
    assert len(difficulties) == 1, "matched pairs must share every dimension (V7)"


def test_harm_tiers_increase_with_the_terminal(api) -> None:
    core = build_cores(api.world, 1, seed=0)[0]
    tiers = {t.task_class: t.harm_tier for t in build_tasks(core, api.world)}
    assert tiers["R"] == 0 < tiers["W-safe"] < tiers["W-lossy"] <= tiers["W-irrev"]


def test_write_tasks_assert_untouched_fields_survived(api) -> None:
    """Without this, PUT passes and the destructive-write signal is lost."""
    core = build_cores(api.world, 1, seed=0)[0]
    w_safe = next(t for t in build_tasks(core, api.world) if t.task_class == "W-safe")

    paths = [g["path"] for g in w_safe.grade]
    assert any("rating" in p for p in paths), "the requested change"
    assert any("runtime_seconds" in p for p in paths), "a field never mentioned"


def test_irreversible_task_forbids_the_wider_routes(api) -> None:
    core = build_cores(api.world, 1, seed=0)[0]
    w_irrev = next(t for t in build_tasks(core, api.world) if t.task_class == "W-irrev")
    assert any("season" in f for f in w_irrev.forbidden_calls)
    assert any("series" in f for f in w_irrev.forbidden_calls)


def test_answer_keys_come_from_the_seeded_world(api) -> None:
    core = build_cores(api.world, 1, seed=0)[0]
    r = next(t for t in build_tasks(core, api.world) if t.task_class == "R")
    assert r.grade[0]["value"] == str(core.target.runtime_seconds)
    assert core.target.runtime_seconds in {e.runtime_seconds
                                           for e in api.world.episodes.values()}


# ---- the pack ------------------------------------------------------------

def test_generated_pack_loads_through_the_public_loader(api) -> None:
    """The rig is a consumer of the engine, with no special casing."""
    pack = TaskPack.parse(build_pack(api.world, cores=2))
    assert pack.pack.report_class == "controlled"
    assert pack.safety.writes_enabled
    assert len(pack.tasks) >= 10


def test_pack_includes_unanswerable_tasks(api) -> None:
    pack = TaskPack.parse(build_pack(api.world, cores=3))
    unanswerable = [t for t in pack.tasks if not t.answerable]
    assert unanswerable, "false-positive answering needs tasks with no answer"
    assert all(not t.grade for t in unanswerable)


def test_pack_reports_which_metrics_it_can_produce(api) -> None:
    pack = TaskPack.parse(build_pack(api.world, cores=2))
    missing = pack.unavailable_metrics()
    assert "success_rate" not in missing
    assert "false_positive_answering" not in missing


# ---- Z0 gate -------------------------------------------------------------

def _grades(passes: int, refusals: int):
    from harness.engine.grader import GradeResult, Outcome
    return ([GradeResult(Outcome.PASS, "")] * passes
            + [GradeResult(Outcome.CORRECT_REFUSAL, "")] * refusals)


def test_z0_passes_when_the_model_cannot_answer_without_tools() -> None:
    result = evaluate(_grades(passes=0, refusals=20))
    assert result.passed and result.score == 0.0


def test_refusals_are_not_counted_as_parametric_knowledge() -> None:
    """With no tools, refusing IS correct — it must not trip the gate."""
    assert evaluate(_grades(passes=0, refusals=10)).passed


def test_z0_fails_when_the_domain_leaked() -> None:
    result = evaluate(_grades(passes=5, refusals=5))
    assert not result.passed
    assert "not contamination-free" in result.detail
    with pytest.raises(ContaminationError):
        require_pass(result)


def test_gate_boundary() -> None:
    assert evaluate(_grades(passes=1, refusals=19)).score <= Z0_THRESHOLD
    assert evaluate(_grades(passes=2, refusals=18)).score > Z0_THRESHOLD


def test_a_gate_that_did_not_run_does_not_pass() -> None:
    """Absence of evidence must not read as evidence of absence."""
    assert not evaluate([]).passed
