"""Experiment task resolution — bridges sidecar declarations to task lists.

Lives outside ``engine/`` so it may import the controlled rig. The engine stays
API-agnostic; this module is the harness-level glue the CLI and UI adapter share.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .engine.experiment_sidecar import ExperimentSidecar
from .engine.planner import RunPlan
from .engine.results import ResultStore
from .engine.taskpack import TaskPack, load as load_pack


def resolve_tasks(plan: RunPlan, *, manifest: dict[str, Any] | None = None) -> list[Any]:
    """Materialise task objects for cell scheduling."""
    tasks_cfg = plan.tasks or {}
    if "pack" in tasks_cfg:
        pack_path = tasks_cfg["pack"]
        return list(load_pack(pack_path).tasks)
    if "generate" not in tasks_cfg:
        raise ValueError("run_plan.tasks must contain generate or pack")
    gen = tasks_cfg["generate"] or {}
    from .experiment.domain import WorldShape, build_world, shape_for_cores
    from .experiment.tasks import build_pack

    seed = int(gen.get("seed", 0))
    cores = int(gen.get("cores", 1))
    fan_out = int(gen.get("fan_out", 8))
    difficulty = str(gen.get("difficulty", "standard"))
    shape = shape_for_cores(cores, WorldShape(episodes_per_season=fan_out))
    if manifest:
        # Resume path: honour the world that produced existing rows.
        seed = int(manifest.get("seed", seed))
        cores = int(manifest.get("cores", cores))
        fan_out = int(manifest.get("fan_out", fan_out))
        difficulty = str(manifest.get("difficulty", difficulty))
        shape = shape_for_cores(cores, WorldShape(episodes_per_season=fan_out))
    pack = TaskPack.parse(build_pack(
        build_world(seed, shape),
        cores=cores,
        seed=seed,
        difficulty=difficulty,
    ))
    return list(pack.tasks)


def load_sidecar_tasks(root: str | Path) -> tuple[ExperimentSidecar, ResultStore, list[Any]]:
    store = ResultStore(root)
    sidecar = ExperimentSidecar.load(root)
    sidecar.validate_world_lock(store)
    tasks = resolve_tasks(sidecar.run_plan(), manifest=store.manifest() or None)
    return sidecar, store, tasks
