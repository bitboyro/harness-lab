"""The load-time rules are the contract. Each test names the wrong number it blocks."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.engine.taskpack import PackError, TaskPack, load

MINIMAL = {
    "schema_version": 1,
    "pack": {"id": "p", "report_class": "field"},
    "api": {"base_url_env": "URL"},
    "tasks": [{"id": "t1", "prompt": "q", "class": "R"}],
}


def build(**overrides) -> dict:
    import copy
    d = copy.deepcopy(MINIMAL)
    for k, v in overrides.items():
        d[k] = v
    return d


def test_minimal_pack_loads() -> None:
    """Only api + prompt: assertion-free mode is a legitimate pack."""
    pack = TaskPack.parse(MINIMAL)
    assert pack.tasks[0].id == "t1"


def test_unknown_schema_version_is_refused_not_guessed() -> None:
    with pytest.raises(PackError, match="unsupported schema_version"):
        TaskPack.parse(build(schema_version=99))


def test_report_class_is_mandatory() -> None:
    """Controlled and field results must never be pooled, so it can't be inferred."""
    d = build()
    del d["pack"]["report_class"]
    with pytest.raises(Exception):
        TaskPack.parse(d)


def test_writes_blocked_unless_explicitly_enabled() -> None:
    """You cannot accidentally run mutations."""
    d = build(tasks=[{"id": "w", "prompt": "delete it", "class": "W-irrev"}])
    with pytest.raises(PackError, match="writes_enabled is false"):
        TaskPack.parse(d)


def test_writes_run_when_enabled_with_a_snapshotter() -> None:
    d = build(
        safety={"writes_enabled": True},
        isolation={"mode": "instance-per-run", "setup": "s.py",
                   "state_snapshot": "snap.py"},
        tasks=[{"id": "w", "prompt": "patch it", "class": "W-safe",
                "expected_end_state": {"a": 1}}],
    )
    assert TaskPack.parse(d).tasks[0].needs_state


def test_state_grading_requires_a_snapshotter() -> None:
    """Grading a write from the transcript scores a liar as correct."""
    d = build(
        safety={"writes_enabled": True},
        tasks=[{"id": "w", "prompt": "patch", "class": "W-safe",
                "expected_end_state": {"a": 1}}],
    )
    with pytest.raises(PackError, match="state_snapshot is unset"):
        TaskPack.parse(d)


def test_matched_pairs_must_share_difficulty() -> None:
    """Otherwise the write penalty measures difficulty, not the terminal."""
    d = build(
        safety={"writes_enabled": True},
        isolation={"mode": "instance-per-run", "setup": "s.py",
                   "state_snapshot": "snap.py"},
        tasks=[
            {"id": "a", "prompt": "q", "class": "R", "core_id": "c1",
             "difficulty": {"hops": 3, "fan_out": 12}},
            {"id": "b", "prompt": "q", "class": "W-safe", "core_id": "c1",
             "difficulty": {"hops": 1, "fan_out": 12}},
        ],
    )
    with pytest.raises(PackError, match="differ on difficulty"):
        TaskPack.parse(d)


def test_matched_pairs_with_identical_difficulty_pass() -> None:
    d = build(
        tasks=[
            {"id": "a", "prompt": "q", "class": "R", "core_id": "c1",
             "difficulty": {"hops": 3, "fan_out": 12}},
            {"id": "b", "prompt": "q2", "class": "R", "core_id": "c1",
             "difficulty": {"hops": 3, "fan_out": 12}},
        ],
    )
    assert len(TaskPack.parse(d).tasks) == 2


def test_unanswerable_task_cannot_be_graded_on_answer_equality() -> None:
    d = build(tasks=[{
        "id": "u", "prompt": "q", "class": "R", "answerable": False,
        "grade": [{"type": "equals", "target": "answer", "value": 5}],
    }])
    with pytest.raises(PackError, match="answerable=false"):
        TaskPack.parse(d)


def test_duplicate_task_ids_rejected() -> None:
    d = build(tasks=[{"id": "x", "prompt": "a"}, {"id": "x", "prompt": "b"}])
    with pytest.raises(PackError, match="duplicate task id"):
        TaskPack.parse(d)


def test_harm_tier_bounds() -> None:
    d = build(tasks=[{"id": "t", "prompt": "q", "harm_tier": 9}])
    with pytest.raises(PackError, match="harm_tier"):
        TaskPack.parse(d)


def test_unavailable_metrics_are_reported_not_silent() -> None:
    pack = TaskPack.parse(MINIMAL)
    missing = pack.unavailable_metrics()
    assert "success_rate" in missing
    assert "selection_accuracy" in missing
    assert "harm_per_100_tasks" in missing
    assert "false_positive_answering" in missing
    assert all(reason for reason in missing.values())


def test_production_write_needs_both_gates(tmp_path: Path) -> None:
    d = build(
        safety={"writes_enabled": True},
        isolation={"mode": "instance-per-run", "setup": "s.py",
                   "state_snapshot": "snap.py"},
        tasks=[{"id": "w", "prompt": "patch", "class": "W-safe"}],
    )
    p = tmp_path / "pack.yaml"
    p.write_text(yaml.safe_dump(d))
    url = "https://api.acme-corp.com"

    with pytest.raises(PackError, match="production_ack"):
        load(p, base_url=url)

    d["safety"]["production_ack"] = True
    p.write_text(yaml.safe_dump(d))
    with pytest.raises(PackError, match="allow_production_writes"):
        load(p, base_url=url)

    assert load(p, base_url=url, allow_production_writes=True)


def test_local_hosts_are_not_production(tmp_path: Path) -> None:
    d = build(
        safety={"writes_enabled": True},
        isolation={"mode": "instance-per-run", "setup": "s.py",
                   "state_snapshot": "snap.py"},
        tasks=[{"id": "w", "prompt": "patch", "class": "W-safe"}],
    )
    p = tmp_path / "pack.yaml"
    p.write_text(yaml.safe_dump(d))
    assert load(p, base_url="http://localhost:8080")


def test_read_only_pack_never_trips_the_production_gate(tmp_path: Path) -> None:
    p = tmp_path / "pack.yaml"
    p.write_text(yaml.safe_dump(MINIMAL))
    assert load(p, base_url="https://api.acme-corp.com")


def test_typos_are_rejected_rather_than_ignored() -> None:
    """extra=forbid: a misspelled field silently doing nothing is the worst case."""
    d = build(tasks=[{"id": "t", "prompt": "q", "harm_teir": 2}])
    with pytest.raises(Exception):
        TaskPack.parse(d)


def test_documented_examples_load() -> None:
    """The worked examples in the contract must actually be valid packs."""
    import re
    doc = Path(__file__).resolve().parents[1] / "docs" / "design-your-test-run.md"
    blocks = re.findall(r"```yaml\n(.*?)```", doc.read_text(), re.S)
    packs = [b for b in blocks if "schema_version" in b and "pack:" in b]
    assert len(packs) >= 2, "expected the mock-API and field examples"

    loaded = 0
    for block in packs:
        data = yaml.safe_load(block)
        if data["pack"]["id"] == "string":  # the schema template, not an example
            continue
        TaskPack.parse(data)
        loaded += 1
    assert loaded == 2
