"""Arm label parsing — legacy bare form and canonical AXIS=value form."""

from __future__ import annotations

import pytest

from harness.engine.axes import ConfigError, format_label, split_label


def test_bare_legacy_error_detail() -> None:
    assert split_label("A1@terse") == ("A1", {"error_detail": "terse"})


def test_canonical_single_axis() -> None:
    assert split_label("A1@error_detail=terse") == (
        "A1", {"error_detail": "terse"}
    )


def test_multi_axis_and_materials() -> None:
    base, overrides = split_label(
        "D-lib@skill=catalog-v2,helpers=walk_a,doc_budget=terse"
    )
    assert base == "D-lib"
    assert overrides == {
        "skill": "catalog-v2",
        "helpers": "walk_a",
        "doc_budget": "terse",
    }


def test_no_at_sign() -> None:
    assert split_label("A1") == ("A1", {})


def test_malformed_part_refused() -> None:
    with pytest.raises(ConfigError, match="missing '='"):
        split_label("A1@error_detail=terse,verbose")


def test_format_label_round_trips_legacy() -> None:
    assert format_label("A1", {"error_detail": "terse"}) == "A1@terse"
