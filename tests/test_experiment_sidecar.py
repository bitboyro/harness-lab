"""Experiment sidecar scheduling and world-lock rules."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.engine.axes import ConfigError
from harness.engine.experiment_sidecar import (
    ExperimentSidecar,
    coverage_summary,
    declared_cells,
    has_sidecar,
    missing_cells,
)
from harness.engine.results import ResultStore, Row
from harness.study import resolve_tasks


PLAN = Path(__file__).resolve().parents[1] / "plans" / "baseline-experiment-80.yaml"
EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "harness-ui" / "examples" / "experiment-baseline-80.yaml"
)

_ROW = dict(
    run_id="r1", arm="A1", task_id="t1", core_id="c1", task_class="R", answerable=True,
    repeat=0, outcome="pass", detail="", confident=False, clobbered=(), turns=1, calls=0,
    forbidden_attempts=0, truncated=False, error=None, error_kind=None,
    wall_clock_seconds=0.1, input_tokens=0, cached_input_tokens=0, output_tokens=0,
    reasoning_tokens=0, static_tokens=0, per_call_overhead_tokens=0,
    session_setup_tokens=0, model="gpt-5.6-luna", mcp_spec_revision="2026-07-28",
    skill_condition="none", report_class="controlled", seed=1, surface_size=50,
)


def row(**kw) -> Row:
    return Row(**{**_ROW, **kw})


@pytest.fixture
def experiment_dir(tmp_path: Path) -> Path:
    out = tmp_path / "baseline-experiment-80"
    sidecar = ExperimentSidecar.init_from_plan(PLAN, out)
    # Small slice for scheduling tests — not in plan file, added after init.
    sidecar.data["slices"] = {
        "smoke": {"arms": ["Z0", "A1", "A2"], "cores": 2},
    }
    sidecar.save()
    assert sidecar.id == "baseline-experiment-80"
    return out


def test_init_writes_sidecar(experiment_dir: Path) -> None:
    assert has_sidecar(experiment_dir)
    sidecar = ExperimentSidecar.load(experiment_dir)
    assert sidecar.status == "draft"
    assert "A1" in sidecar.active_presets()
    assert sidecar.run_plan().id == "baseline-experiment-80"


def test_example_yaml_loads(experiment_dir: Path) -> None:
    raw = yaml.safe_load(EXAMPLE.read_text())
    sidecar = ExperimentSidecar(experiment_dir, raw)
    sidecar.validate()
    assert sidecar.data["run_plan"]["id"] == "baseline-experiment-80"
    assert "smoke" in sidecar.data["slices"]


def test_add_presets_is_additive(experiment_dir: Path) -> None:
    sidecar = ExperimentSidecar.load(experiment_dir)
    before = set(sidecar.active_presets())
    sidecar.add_presets(["E1", "A1"])
    after = set(sidecar.active_presets())
    assert "E1" in after - before
    assert sidecar.active_presets().count("A1") == 1


def test_missing_cells_empty_ledger(experiment_dir: Path) -> None:
    sidecar = ExperimentSidecar.load(experiment_dir)
    store = ResultStore(experiment_dir)
    plan = sidecar.run_plan()
    tasks = resolve_tasks(plan)
    repeats = int(plan.base.get("repeats", 1))
    missing = missing_cells(
        store,
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=repeats,
    )
    declared = declared_cells(
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=repeats,
    )
    assert missing == declared
    assert len(missing) > 0


def test_slice_reduces_declared_cells(experiment_dir: Path) -> None:
    sidecar = ExperimentSidecar.load(experiment_dir)
    store = ResultStore(experiment_dir)
    plan = sidecar.run_plan()
    tasks = resolve_tasks(plan)
    repeats = int(plan.base.get("repeats", 1))
    full = declared_cells(
        presets=sidecar.active_presets(), tasks=tasks, repeats=repeats,
    )
    smoke = declared_cells(
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=repeats,
        slice_spec=sidecar.slice_spec("smoke"),
    )
    assert 0 < len(smoke) < len(full)


def test_completed_cells_excluded_from_missing(experiment_dir: Path) -> None:
    sidecar = ExperimentSidecar.load(experiment_dir)
    store = ResultStore(experiment_dir)
    plan = sidecar.run_plan()
    tasks = resolve_tasks(plan)
    repeats = int(plan.base.get("repeats", 1))
    task = tasks[0]
    arm = sidecar.active_presets()[0]
    store.record(row(arm=arm, task_id=task.id, core_id=task.core_id))
    missing = missing_cells(
        store,
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=repeats,
    )
    assert (arm, task.id, 0) not in missing
    cov = coverage_summary(
        store,
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=repeats,
    )
    assert cov["completed_cells"] == 1
    assert cov["missing_cells"] == len(missing)


def test_world_lock_refuses_seed_change(experiment_dir: Path) -> None:
    sidecar = ExperimentSidecar.load(experiment_dir)
    store = ResultStore(experiment_dir)
    store.write_manifest(seed=1, cores=2, fan_out=8, difficulty="hard",
                         surface_size=50, pack_digest="abc")
    store.record(row(arm="A1", task_id="core-000-R", core_id="core-000"))
    plan_tasks = sidecar.data["run_plan"]["tasks"]["generate"]
    plan_tasks["seed"] = 99
    sidecar.save()
    sidecar = ExperimentSidecar.load(experiment_dir)
    with pytest.raises(ConfigError, match="seed"):
        sidecar.validate_world_lock(store)


def test_plain_resume_unchanged_without_sidecar(tmp_path: Path) -> None:
    from harness.cli import _inherit_run_config, build_parser

    out = tmp_path / "run"
    store = ResultStore(out)
    store.write_manifest(presets=["A1", "A2"], cores=3, seed=1)
    args = build_parser().parse_args(["run", "--out", str(out), "--resume",
                                      "--presets", "A1", "A2", "E1"])
    changed = _inherit_run_config(args, store.manifest())
    assert args.presets == ["A1", "A2"]
    assert any("presets" in c for c in changed)
