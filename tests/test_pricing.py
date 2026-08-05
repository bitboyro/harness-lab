"""Pricing: cache tiers, the long-context step, and refusing to guess."""

from __future__ import annotations

import pytest

from harness.engine.pricing import (
    CATALOGUE, ModelPricing, Rates, UnknownModel, break_even_runs, lookup,
    price_run,
)

LUNA = CATALOGUE["gpt-5.6-luna"]


def test_catalogue_matches_the_published_rates() -> None:
    assert LUNA.short == Rates(input=0.20, cached_input=0.02,
                               cache_write=0.25, output=1.20)
    assert LUNA.long == Rates(input=0.40, cached_input=0.04,
                              cache_write=0.50, output=1.80)
    sol = CATALOGUE["gpt-5.6-sol"]
    assert (sol.short.input, sol.short.output) == (5.00, 30.00)
    assert (sol.long.input, sol.long.output) == (10.00, 45.00)


def test_cached_input_is_an_order_of_magnitude_cheaper() -> None:
    """Why §5.6 requires cost reported cached and uncached."""
    assert LUNA.short.cached_input == pytest.approx(LUNA.short.input / 10)


def test_cache_writes_cost_more_than_fresh_input() -> None:
    """The subtlety a flat rate hides: a big static prefix pays a premium first."""
    assert LUNA.short.cache_write > LUNA.short.input


def test_a_large_prefix_only_pays_off_after_enough_reuse() -> None:
    """Writing costs +125%; reads save 90%. Break-even is not immediate."""
    tokens = 100_000
    fresh = price_run(LUNA, input_tokens=tokens).total_usd
    first_run = price_run(LUNA, input_tokens=tokens,
                          cache_write_tokens=tokens).total_usd
    reuse = price_run(LUNA, input_tokens=tokens,
                      cached_input_tokens=tokens).total_usd

    assert first_run > fresh, "the first cached run is more expensive, not less"
    assert reuse < fresh
    # The write premium is recovered on the very first reuse.
    assert first_run + reuse < 2 * fresh


def test_cache_write_replaces_the_input_rate_rather_than_adding_to_it() -> None:
    """Charging both would more than double a large prefix and make caching
    look like it never pays off."""
    n = 100_000
    written = price_run(LUNA, input_tokens=n, cache_write_tokens=n)
    assert written.fresh_input_usd == 0.0, "written tokens are not also fresh"
    assert written.total_usd == pytest.approx(n / 1e6 * LUNA.short.cache_write)


def test_break_even_is_the_second_run() -> None:
    """The write premium (+25%) is smaller than one reuse saving (-90%), so a
    static prefix pays for itself immediately on reuse. With repeats>=3 every
    cached arm is past break-even — which is exactly why §5.6 wants the
    uncached figure too, since a real consumer may only ever run once."""
    assert break_even_runs(LUNA, 100_000) == 2
    assert break_even_runs(CATALOGUE["gpt-5.6-sol"], 100_000) == 2


def test_break_even_is_none_when_caching_cannot_win() -> None:
    flat = Rates(input=1.0, cached_input=1.0, cache_write=1.0, output=1.0)
    assert break_even_runs(ModelPricing(short=flat, long=flat), 1000) is None


def test_long_context_reprices_every_token_not_just_the_excess() -> None:
    """A step function, not a surcharge — an arm can fall off a cliff."""
    threshold = LUNA.long_context_threshold
    just_under = price_run(LUNA, input_tokens=threshold, output_tokens=100)
    just_over = price_run(LUNA, input_tokens=threshold + 1, output_tokens=100)

    assert just_under.tier == "short" and just_over.tier == "long"
    # One extra token roughly doubles the bill for the whole request.
    assert just_over.total_usd > just_under.total_usd * 1.9


def test_fresh_input_excludes_the_cached_portion() -> None:
    """Passing both must not double-count. Sub-threshold, so short rates apply."""
    cost = price_run(LUNA, input_tokens=100_000, cached_input_tokens=40_000)
    assert cost.fresh_input_usd == pytest.approx(0.06 * LUNA.short.input)
    assert cost.cached_input_usd == pytest.approx(0.04 * LUNA.short.cached_input)


def test_siblings_are_not_priced_as_each_other() -> None:
    """luna and terra share a prefix and differ 10x."""
    assert lookup("gpt-5.6-luna").short.input == 0.20
    assert lookup("gpt-5.6-terra").short.input == 2.00
    assert lookup("gpt-5.6-sol").short.input == 5.00


def test_unknown_model_refuses_rather_than_guessing() -> None:
    with pytest.raises(UnknownModel, match="no price on record"):
        lookup("gpt-5.6-nebula")


def test_dated_snapshot_inherits_its_base_card() -> None:
    assert lookup("gpt-5.6-luna-2026-08-01") == LUNA


def test_override_accepts_two_four_or_eight_values(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_PRICE_M", "1,2")
    assert lookup("m").short.output == 2.0

    monkeypatch.setenv("HARNESS_PRICE_M", "1,0.1,1.25,2")
    assert lookup("m").short.cache_write == 1.25

    monkeypatch.setenv("HARNESS_PRICE_M", "1,0.1,1.25,2,3,0.3,3.75,6")
    card = lookup("m")
    assert card.short.input == 1.0 and card.long.input == 3.0


def test_override_with_a_wrong_shape_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_PRICE_M", "1,2,3")
    with pytest.raises(ValueError, match="needs 2"):
        lookup("m")


def test_cost_renders_its_decomposition() -> None:
    text = price_run(LUNA, input_tokens=1000, cached_input_tokens=500,
                     output_tokens=100).render()
    assert "fresh" in text and "cached" in text and "short" in text


# ---- arm-level reporting -------------------------------------------------

def test_cost_per_success_uses_real_usage() -> None:
    from conftest import BASE_AXES
    from harness.engine.axes import preset
    from harness.engine.field import ArmResult
    from harness.engine.grader import GradeResult, Outcome
    from harness.engine.provider import Usage
    from harness.engine.trace import Trace, Turn

    arm = ArmResult(preset="A1")
    for _ in range(2):
        t = Trace(run_id="r", task_id="t", variant=preset("A1", **BASE_AXES),
                  mcp_spec_revision=None)
        t.record_turn(Turn(0, [], None, Usage(10_000, 8_000, 500, 0), "stop", 1.0))
        t.finish("x")
        arm.traces.append(t)
    arm.grades = [GradeResult(Outcome.PASS, ""), GradeResult(Outcome.FAIL, "")]

    assert arm.cache_hit_rate() == pytest.approx(0.8)
    per = arm.cost_per_success(LUNA)
    assert per is not None and per == pytest.approx(arm.cost(LUNA).total_usd)


def test_cost_per_success_is_none_without_successes() -> None:
    from harness.engine.field import ArmResult
    from harness.engine.grader import GradeResult, Outcome

    arm = ArmResult(preset="A1")
    arm.grades = [GradeResult(Outcome.FAIL, "")]
    assert arm.cost_per_success(LUNA) is None
