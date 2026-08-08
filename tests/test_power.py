"""Power sizing. Each test names the design mistake it prevents."""

from __future__ import annotations

import pytest

from harness.experiment.domain import WorldShape, build_world, shape_for_cores
from harness.experiment.power import (
    Contrast, analyse, cores_for, report,
)
from harness.experiment.tasks import build_cores


def test_interaction_needs_more_data_than_a_main_effect() -> None:
    """It compares two differences, so the errors add."""
    main = analyse(Contrast.MAIN_EFFECT, 25).mde_pp
    interaction = analyse(Contrast.INTERACTION, 25).mde_pp
    assert interaction > main


def test_more_cores_shrink_the_detectable_effect() -> None:
    assert analyse(Contrast.INTERACTION, 60).mde_pp < \
        analyse(Contrast.INTERACTION, 15).mde_pp


def test_repeats_cannot_substitute_for_cores() -> None:
    """The whole justification for sizing on cores.

    Effect heterogeneity — how much the arm gap varies between cores — divides
    by cores and by nothing else. Ten times the repeats buys less than tripling
    the cores, at ten times the cost.
    """
    many_repeats = analyse(Contrast.INTERACTION, 25, repeats=30).mde_pp
    more_cores = analyse(Contrast.INTERACTION, 81, repeats=3).mde_pp
    assert more_cores < many_repeats

    # And repeats have a floor they cannot cross, however many you run.
    absurd = analyse(Contrast.INTERACTION, 25, repeats=1000).mde_pp
    assert absurd > 0
    assert absurd > analyse(Contrast.INTERACTION, 200, repeats=3).mde_pp


def test_zero_heterogeneity_would_claim_a_uniform_effect() -> None:
    """Sanity-check the term that makes repeats insufficient."""
    with_het = analyse(Contrast.INTERACTION, 25, repeats=1000).mde_pp
    without = analyse(Contrast.INTERACTION, 25, repeats=1000,
                      effect_heterogeneity=0.0).mde_pp
    assert with_het > without * 5


def test_the_specced_15_cores_is_underpowered_for_the_interaction() -> None:
    """The finding that changed the plan."""
    assert not analyse(Contrast.INTERACTION, 15).adequate
    assert analyse(Contrast.MAIN_EFFECT, 40).adequate
    assert analyse(Contrast.INTERACTION, 40).adequate


def test_cores_for_finds_the_smallest_adequate_size() -> None:
    needed = cores_for(Contrast.INTERACTION, 15.0)
    assert needed is not None
    assert analyse(Contrast.INTERACTION, needed).mde_pp <= 15.0
    assert analyse(Contrast.INTERACTION, needed - 1).mde_pp > 15.0


def test_impossible_targets_return_none_rather_than_a_huge_number() -> None:
    assert cores_for(Contrast.INTERACTION, 0.001, max_cores=50) is None


def test_report_names_what_is_underpowered_and_the_fix() -> None:
    text = report(15)
    assert "UNDERPOWERED" in text
    assert "cores would reach 15 pp" in text
    assert "not detectable" in text, "a null must not read as an absence"


def test_within_class_stays_expensive() -> None:
    """Why it is exploratory by construction rather than confirmatory."""
    assert cores_for(Contrast.WITHIN_CLASS, 15.0) > cores_for(Contrast.INTERACTION, 15.0)


def test_zero_cores_is_rejected() -> None:
    with pytest.raises(ValueError):
        analyse(Contrast.MAIN_EFFECT, 0)


# ---- the silent-undersizing bug ------------------------------------------

def test_asking_for_more_cores_than_exist_raises() -> None:
    """Silently returning fewer would make the printed power table a lie."""
    small = build_world(1, WorldShape(studios=1, series_per_studio=1,
                                      seasons_per_series=2))
    with pytest.raises(ValueError, match="power figures no longer describe"):
        build_cores(small, 40, seed=1)


def test_world_grows_to_fit_the_requested_cores() -> None:
    for cores in (10, 36, 40, 60, 200):
        world = build_world(1, shape_for_cores(cores))
        assert len(build_cores(world, cores, seed=1)) == cores


def test_growing_widens_studios_rather_than_deepening_seasons() -> None:
    """A series with 40 seasons would be a conspicuous artifact."""
    shape = shape_for_cores(200)
    assert shape.seasons_per_series == WorldShape().seasons_per_series
    assert shape.studios > WorldShape().studios


def test_growing_preserves_the_fan_out_the_sweep_set() -> None:
    shape = shape_for_cores(100, WorldShape(episodes_per_season=50))
    assert shape.episodes_per_season == 50
