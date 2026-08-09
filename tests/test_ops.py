"""Operation ledger — axis-based resolution, core rates, derived views."""

from __future__ import annotations

import json

from harness.engine.dispatch import DESCRIBE, INVOKE, SEARCH
from harness.engine.ops import (
    augment_gold_for_controlled_tasks, build_ledger, expected_share_from_gold,
    family_of, resolve_call,
)


def test_tool_call_resolution() -> None:
    op, kind, disc = resolve_call(
        {"call": {"tool": "get_episode", "args": {}}},
        {"transport": "mcp", "discovery": "eager-all", "invocation": "tool-call"},
    )
    assert (op, kind, disc) == ("get_episode", "tool", False)


def test_meta_tools_uses_operation_id_and_buckets_discovery() -> None:
    op, kind, disc = resolve_call(
        {"call": {"tool": INVOKE, "args": {"operation_id": "archive_series"}}},
        {"transport": "mcp", "discovery": "meta-tools", "invocation": "tool-call"},
    )
    assert (op, kind, disc) == ("archive_series", "operation_id", False)

    _, _, disc = resolve_call(
        {"call": {"tool": SEARCH, "args": {"query": "x"}}},
        {"transport": "mcp", "discovery": "meta-tools", "invocation": "tool-call"},
    )
    assert disc is True

    _, _, disc = resolve_call(
        {"call": {"tool": DESCRIBE, "args": {"operation_id": "get_episode"}}},
        {"transport": "mcp", "discovery": "meta-tools", "invocation": "tool-call"},
    )
    assert disc is True


def test_shell_and_code_are_parsed() -> None:
    op, kind, disc = resolve_call(
        {"call": {"raw": "curl -sS \"$BASE_URL/series?limit=100\" | jq ."}},
        {"transport": "http-rest", "discovery": "docs", "invocation": "shell"},
    )
    assert kind == "parsed" and disc is False
    assert op is not None

    op, kind, _ = resolve_call(
        {"call": {"raw": "from api.operations import archive_episode\n"
                         "print(operations.archive_episode(id='e1'))"}},
        {"transport": "mcp", "discovery": "code-fs", "invocation": "code"},
    )
    assert kind == "parsed"
    assert op == "archive_episode"


def test_controls_excluded_from_target() -> None:
    for transport in ("none", "in-process"):
        op, kind, disc = resolve_call(
            {"call": {"tool": "get_episode"}},
            {"transport": transport, "discovery": "none", "invocation": "none"},
        )
        assert kind == "excluded" and op is None and disc is False


def test_user_arm_resolves_by_axes_not_name() -> None:
    """A custom label with A1's axes must resolve like A1 — never by name."""
    op, kind, disc = resolve_call(
        {"call": {"tool": "list_studios"}},
        {"transport": "mcp", "discovery": "eager-all", "invocation": "tool-call",
         "preset": "my-custom-arm"},
    )
    assert (op, kind, disc) == ("list_studios", "tool", False)


def test_family_rollup_from_op_id() -> None:
    assert family_of("get_episode") == "episodes"
    assert family_of("list_series") == "series"
    assert family_of("archive_episode") == "episodes"
    assert family_of("append_episode_tag") == "episodes"
    assert family_of("list_assets") == "assets"
    assert family_of("list_catalog_entrys") == "catalog_entries"


def _write_trace(dir, name: str, payload: dict) -> None:
    (dir / name).write_text(json.dumps(payload))


def test_build_ledger_excludes_z0_and_ranks_stumble_with_gold(tmp_path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_trace(traces, "z0.json", {
        "run_id": "z0", "task_id": "t1",
        "variant": {"transport": "none", "discovery": "none",
                    "invocation": "none", "preset": "Z0"},
        "calls": [],
    })
    _write_trace(traces, "a1.json", {
        "run_id": "a1", "task_id": "t1",
        "variant": {"transport": "mcp", "discovery": "eager-all",
                    "invocation": "tool-call", "preset": "A1"},
        "calls": [
            {"call": {"tool": "get_episode", "args": {}},
             "result": {"status": 200}, "forbidden": False},
            {"call": {"tool": "get_episode", "args": {}},
             "result": {"status": 200}, "forbidden": False},
            {"call": {"tool": "replace_episode", "args": {}},
             "result": {"status": 500}, "forbidden": True},
        ],
    })
    rows = [
        {"run_id": "z0", "arm": "Z0", "task_id": "t1", "outcome": "fail",
         "answerable": True, "task_class": "R", "core_id": "c0"},
        {"run_id": "a1", "arm": "A1", "task_id": "t1", "outcome": "fail",
         "answerable": True, "task_class": "R", "core_id": "c0",
         "gold_ops": ["get_episode"]},
    ]
    ledger = build_ledger(rows, traces)
    assert "Z0" in ledger.excluded_arms
    assert ledger.has_gold
    misuse = ledger.misuse()
    assert misuse[0].op_id == "replace_episode"
    assert misuse[0].stumble_rate is not None
    assert misuse[0].calls == 1


def test_excess_usage_vs_gold(tmp_path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_trace(traces, "a1.json", {
        "run_id": "a1", "task_id": "t1",
        "variant": {"transport": "mcp", "discovery": "eager-all",
                    "invocation": "tool-call", "preset": "A1"},
        "calls": [
            {"call": {"tool": "get_episode"}, "result": {"status": 200}},
            {"call": {"tool": "list_assets"}, "result": {"status": 200}},
            {"call": {"tool": "list_assets"}, "result": {"status": 200}},
        ],
    })
    rows = [{
        "run_id": "a1", "arm": "A1", "task_id": "t1", "outcome": "pass",
        "answerable": True, "task_class": "R", "core_id": "c0",
        "gold_ops": ["get_episode"],
    }]
    ledger = build_ledger(rows, traces)
    excess = ledger.excess_usage()
    assert excess is not None
    assert excess[0].op_id == "list_assets"
    assert (excess[0].excess_usage or 0) > 0
    distractors = ledger.distractors()
    assert distractors is not None
    assert any(s.op_id == "list_assets" for s in distractors)


def test_without_gold_off_gold_and_excess_are_unavailable(tmp_path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_trace(traces, "a1.json", {
        "run_id": "a1", "task_id": "t1",
        "variant": {"transport": "mcp", "discovery": "eager-all",
                    "invocation": "tool-call", "preset": "A1"},
        "calls": [
            {"call": {"tool": "get_episode"}, "result": {"status": 200}},
        ],
    })
    rows = [{
        "run_id": "a1", "arm": "A1", "task_id": "t1", "outcome": "pass",
        "answerable": True, "task_class": "R", "core_id": "c0",
    }]
    ledger = build_ledger(rows, traces)
    assert not ledger.has_gold
    assert "off_gold_rate" in ledger.unavailable_globally
    assert "excess_usage" in ledger.unavailable_globally
    assert ledger.excess_usage() is None
    assert ledger.distractors() is None
    assert ledger.stumble_by_kind("wrong_route") is None
    # call-error still works
    assert ledger.stumble_by_kind("call_error") is not None
    scores = ledger.usage()
    assert scores[0].off_gold_rate is None
    assert "off_gold_rate" in scores[0].unavailable
    # Stumble composite absent without gold — not a flattering zero.
    assert ledger.misuse() == []


def test_meta_tools_excluded_from_target_usage(tmp_path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_trace(traces, "b2.json", {
        "run_id": "b2", "task_id": "t1",
        "variant": {"transport": "mcp", "discovery": "meta-tools",
                    "invocation": "tool-call", "preset": "B2"},
        "calls": [
            {"call": {"tool": SEARCH, "args": {"query": "x"}},
             "result": {"status": 200}},
            {"call": {"tool": DESCRIBE, "args": {"operation_id": "get_episode"}},
             "result": {"status": 200}},
            {"call": {"tool": INVOKE,
                      "args": {"operation_id": "get_episode", "arguments": {}}},
             "result": {"status": 200}},
        ],
    })
    rows = [{
        "run_id": "b2", "arm": "B2", "task_id": "t1", "outcome": "pass",
        "answerable": True, "task_class": "R", "core_id": "c0",
        "gold_ops": ["get_episode"],
    }]
    ledger = build_ledger(rows, traces)
    assert ledger.discovery_calls == 2
    usage = ledger.usage()
    assert [s.op_id for s in usage] == ["get_episode"]


def test_parsed_fidelity_labelled_in_render(tmp_path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_trace(traces, "c1.json", {
        "run_id": "c1", "task_id": "t1",
        "variant": {"transport": "http-rest", "discovery": "docs",
                    "invocation": "shell", "preset": "C1"},
        "calls": [
            {"call": {"raw": "curl -sS \"$BASE_URL/episodes/e1\""},
             "result": {"status": 200}},
        ],
    })
    rows = [{
        "run_id": "c1", "arm": "C1", "task_id": "t1", "outcome": "pass",
        "answerable": True, "task_class": "R", "core_id": "c0",
    }]
    text = build_ledger(rows, traces).render()
    assert "parsing transcripts" in text or "shell/code" in text
    assert "Notes" in text


def test_expected_share_from_gold() -> None:
    shares = expected_share_from_gold({
        "t1": ("get_episode", "list_series"),
        "t2": ("get_episode",),
    })
    assert shares["get_episode"] == 2 / 3
    assert shares["list_series"] == 1 / 3


def test_augment_gold_adds_terminal_writes() -> None:
    """Controlled gold is navigation-only; ledger must count required writes."""
    raw = {
        "core-000-R": ("list_studios", "list_episodes"),
        "core-000-W-safe": ("list_studios", "list_episodes"),
        "core-000-W-irrev": ("list_studios", "list_episodes"),
        "core-000-RW-fan": ("list_studios", "list_episodes"),
    }
    out = augment_gold_for_controlled_tasks(raw)
    assert "get_episode" in out["core-000-R"]
    assert "patch_episode" in out["core-000-W-safe"]
    assert "archive_episode" in out["core-000-W-irrev"]
    assert "append_episode_tag" in out["core-000-RW-fan"]


def test_arm_cards_and_skill_contrasts(tmp_path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    # A1 leans on list_assets (errors); B1-auth leans on get_episode (clean).
    _write_trace(traces, "a1.json", {
        "run_id": "a1", "task_id": "core-000-R",
        "variant": {"transport": "mcp", "discovery": "eager-all",
                    "invocation": "tool-call", "preset": "A1"},
        "calls": [
            {"call": {"tool": "list_assets"}, "result": {"status": 500}},
            {"call": {"tool": "list_assets"}, "result": {"status": 500}},
            {"call": {"tool": "get_episode"}, "result": {"status": 200}},
        ],
    })
    _write_trace(traces, "b1.json", {
        "run_id": "b1", "task_id": "core-000-R",
        "variant": {"transport": "mcp", "discovery": "eager-all",
                    "invocation": "tool-call", "preset": "B1-auth"},
        "calls": [
            {"call": {"tool": "get_episode"}, "result": {"status": 200}},
            {"call": {"tool": "get_episode"}, "result": {"status": 200}},
            {"call": {"tool": "list_assets"}, "result": {"status": 200}},
        ],
    })
    rows = [
        {"run_id": "a1", "arm": "A1", "task_id": "core-000-R", "outcome": "fail",
         "answerable": True, "task_class": "R", "core_id": "c0",
         "gold_ops": ["get_episode"]},
        {"run_id": "b1", "arm": "B1-auth", "task_id": "core-000-R",
         "outcome": "pass", "answerable": True, "task_class": "R",
         "core_id": "c0", "gold_ops": ["get_episode"]},
    ]
    ledger = build_ledger(rows, traces)
    cards = {c.arm: c for c in ledger.arm_cards()}
    assert cards["A1"].lean_on == "list_assets"
    assert cards["B1-auth"].lean_on == "get_episode"
    text = ledger.render()
    assert "D. Per-arm cards" in text
    assert "E. Skill / discovery contrasts" in text
    contrasts = ledger.skill_contrasts(metric="error_rate", min_abs_delta=0.01)
    hit = [c for c in contrasts if c.arm_a == "A1" and c.arm_b == "B1-auth"]
    assert hit and hit[0].deltas
    assert any(d.op_id == "list_assets" and d.delta < 0 for d in hit[0].deltas)


def test_arm_deltas_descriptive(tmp_path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    for run_id, arm, err in (("a", "A1", 500), ("b", "D1", 200)):
        _write_trace(traces, f"{run_id}.json", {
            "run_id": run_id, "task_id": "t1",
            "variant": {"transport": "mcp", "discovery": "eager-all",
                        "invocation": "tool-call", "preset": arm},
            "calls": [
                {"call": {"tool": "replace_episode"},
                 "result": {"status": err}},
            ],
        })
    rows = [
        {"run_id": "a", "arm": "A1", "task_id": "t1", "outcome": "fail",
         "answerable": True, "task_class": "W-safe", "core_id": "c0"},
        {"run_id": "b", "arm": "D1", "task_id": "t1", "outcome": "pass",
         "answerable": True, "task_class": "W-safe", "core_id": "c0"},
    ]
    deltas = build_ledger(rows, traces).arm_deltas(metric="error_rate")
    assert deltas is not None
    hit = [d for d in deltas if d.op_id == "replace_episode"]
    assert hit
    # D1 lower error than A1 ⇒ negative delta when arm_a=A1, arm_b=D1
    assert any(d.delta < 0 for d in hit)
