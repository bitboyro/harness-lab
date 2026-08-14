"""Deep analysis package — standings match harness report."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.deep_analysis import analyze_directory, build_sections


@pytest.fixture
def smoke_results() -> Path:
    root = Path(__file__).resolve().parents[1]
    path = root / "results" / "z-cheat-smoke"
    if not (path / "results.jsonl").is_file():
        pytest.skip(f"no fixture ledger at {path}")
    return path


def test_analyze_directory_json(smoke_results: Path) -> None:
    payload = analyze_directory(smoke_results, only=["identity", "standings"])
    assert payload["harness_version"]
    assert "identity" in payload["sections"]
    assert "standings" in payload["sections"]
    assert payload["sections"]["standings"]["headers"]
    assert payload["sections"]["standings"]["rows"]


def test_build_sections_order(smoke_results: Path) -> None:
    sections, manifest = build_sections(smoke_results)
    assert manifest
    keys = [s.key for s in sections]
    assert "identity" in keys
    assert "arms" in keys
    assert keys.index("identity") == 0
