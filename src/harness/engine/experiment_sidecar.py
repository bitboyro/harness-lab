"""Experiment sidecar: optional metadata beside a results directory.

A run without ``experiment.yaml`` is unchanged. The sidecar adds declaration,
lifecycle, slices, and episode history on top of the existing ledger —
``manifest.json`` and ``results.jsonl`` are never replaced.

Contract: harness-ui/docs/experiment-schema.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import yaml

from .axes import ConfigError
from .planner import RunPlan, run_plan_from_mapping
from .results import ResultStore

EXPERIMENT_FILE = "experiment.yaml"
REPORTS_DIR = "reports"

_STATUSES = frozenset({"draft", "active", "paused", "complete", "archived"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def experiment_path(root: str | Path) -> Path:
    return Path(root) / EXPERIMENT_FILE


def has_sidecar(root: str | Path) -> bool:
    return experiment_path(root).is_file()


@dataclass
class ExperimentSidecar:
    """Parsed ``experiment.yaml`` with helpers for scheduling and persistence."""

    root: Path
    raw: dict[str, Any]

    @property
    def schema_version(self) -> int:
        return int(self.raw.get("schema_version", 0))

    @property
    def data(self) -> dict[str, Any]:
        exp = self.raw.get("experiment")
        if not isinstance(exp, dict):
            raise ConfigError(f"{self.root}: experiment.yaml missing 'experiment' mapping")
        return exp

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def status(self) -> str:
        return str(self.data.get("status", "draft"))

    @classmethod
    def load(cls, root: str | Path) -> ExperimentSidecar:
        root = Path(root)
        path = experiment_path(root)
        if not path.is_file():
            raise ConfigError(f"{root}: no {EXPERIMENT_FILE} sidecar")
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: expected a mapping at the top level")
        sidecar = cls(root=root, raw=raw)
        sidecar.validate()
        return sidecar

    @classmethod
    def init_from_plan(cls, plan_path: Path, out: Path,
                       *, plan_raw: dict[str, Any] | None = None) -> ExperimentSidecar:
        """Write a new sidecar from a ``plans/*.yaml`` file."""
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        if plan_raw is None:
            plan_raw = yaml.safe_load(plan_path.read_text())
        if not isinstance(plan_raw, dict) or "run_plan" not in plan_raw:
            raise ConfigError(f"{plan_path}: expected a top-level 'run_plan' mapping")
        rp = plan_raw["run_plan"]
        exp_id = str(rp.get("id") or out.name)
        now = _utc_now()
        raw = {
            "schema_version": 1,
            "experiment": {
                "id": exp_id,
                "status": "draft",
                "created_at": now,
                "updated_at": now,
                "run_plan": rp,
                "slices": {},
                "retired_arms": [],
                "episodes": [],
                "report_snapshots": [],
            },
        }
        sidecar = cls(root=out, raw=raw)
        sidecar.validate()
        sidecar.save()
        return sidecar

    def save(self) -> None:
        self.data["updated_at"] = _utc_now()
        experiment_path(self.root).write_text(
            yaml.safe_dump(self.raw, sort_keys=False, default_flow_style=False)
        )

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ConfigError(
                f"{self.root}: unsupported experiment schema_version "
                f"{self.schema_version!r} (expected 1)"
            )
        exp = self.data
        if not str(exp.get("id", "")).strip():
            raise ConfigError(f"{self.root}: experiment.id is required")
        status = exp.get("status", "draft")
        if status not in _STATUSES:
            raise ConfigError(f"{self.root}: unknown experiment status {status!r}")
        has_inline = "run_plan" in exp and exp["run_plan"]
        has_ref = bool(exp.get("plan"))
        if has_inline and has_ref:
            raise ConfigError(
                f"{self.root}: set either run_plan or plan, not both"
            )
        if not has_inline and not has_ref:
            raise ConfigError(f"{self.root}: experiment needs run_plan or plan")
        # Eager validation of the embedded declaration.
        self.run_plan()

    def run_plan(self) -> RunPlan:
        exp = self.data
        if exp.get("plan"):
            from .planner import load_plan
            return load_plan(exp["plan"])
        return run_plan_from_mapping(exp["run_plan"], path=str(experiment_path(self.root)))

    def active_presets(self) -> tuple[str, ...]:
        retired = set(self.data.get("retired_arms") or [])
        return tuple(p for p in self.run_plan().presets if p not in retired)

    def add_presets(self, names: Sequence[str]) -> tuple[str, ...]:
        rp = self.data.setdefault("run_plan", {})
        include = rp.setdefault("include", {})
        if "presets" not in include:
            include["presets"] = []
        presets = include["presets"]
        added: list[str] = []
        for name in names:
            if name not in presets:
                presets.append(name)
                added.append(name)
        if added:
            self.save()
        return tuple(added)

    def retire_presets(self, names: Sequence[str]) -> None:
        retired = list(self.data.setdefault("retired_arms", []))
        for name in names:
            if name not in retired:
                retired.append(name)
        self.save()

    def slice_spec(self, slice_id: str | None) -> dict[str, Any] | None:
        if not slice_id:
            return None
        slices = self.data.get("slices") or {}
        if slice_id not in slices:
            raise ConfigError(f"{self.root}: unknown slice {slice_id!r}")
        spec = slices[slice_id]
        if not isinstance(spec, dict):
            raise ConfigError(f"{self.root}: slice {slice_id!r} must be a mapping")
        return spec

    def append_episode(self, episode: dict[str, Any]) -> None:
        episodes = self.data.setdefault("episodes", [])
        episodes.append(episode)
        if self.status == "draft":
            self.data["status"] = "active"
        self.save()

    def append_report_snapshot(self, snapshot: dict[str, Any]) -> None:
        snaps = self.data.setdefault("report_snapshots", [])
        snaps.append(snapshot)
        self.save()

    def validate_world_lock(self, store: ResultStore) -> None:
        """Refuse declaration changes that would reseed the catalog in place."""
        if not any(True for _ in store.raw_rows()):
            return
        manifest = store.manifest()
        if not manifest:
            return
        plan = self.run_plan()
        gen = (plan.tasks or {}).get("generate") or {}
        locked = {
            "seed": int(manifest.get("seed", gen.get("seed", 0))),
            "cores": int(manifest.get("cores", gen.get("cores", 0))),
            "fan_out": int(manifest.get("fan_out", gen.get("fan_out", 0))),
            "difficulty": str(manifest.get("difficulty", gen.get("difficulty", ""))),
            "surface_size": int(manifest.get("surface_size",
                                               plan.base.get("surface_size", 0))),
        }
        declared = {
            "seed": int(gen.get("seed", locked["seed"])),
            "cores": int(gen.get("cores", locked["cores"])),
            "fan_out": int(gen.get("fan_out", locked["fan_out"])),
            "difficulty": str(gen.get("difficulty", locked["difficulty"])),
            "surface_size": int(plan.base.get("surface_size", locked["surface_size"])),
        }
        if declared["cores"] < locked["cores"]:
            raise ConfigError(
                f"{self.root}: cannot shrink cores from {locked['cores']} to "
                f"{declared['cores']} after ledger rows exist"
            )
        for key in ("seed", "fan_out", "difficulty", "surface_size"):
            if declared[key] != locked[key]:
                raise ConfigError(
                    f"{self.root}: cannot change {key} from {locked[key]!r} to "
                    f"{declared[key]!r} after ledger rows exist"
                )
        stored_digest = manifest.get("pack_digest")
        if stored_digest and plan.tasks.get("pack"):
            raise ConfigError(
                f"{self.root}: cannot switch to a field pack after a controlled "
                "ledger exists in this directory"
            )


def _filter_tasks_by_slice(
    tasks: Sequence[Any],
    spec: dict[str, Any] | None,
) -> list[Any]:
    if not spec:
        return list(tasks)
    cores = spec.get("cores")
    if cores is None:
        return list(tasks)
    if isinstance(cores, int):
        allowed = {t.core_id for t in tasks if t.core_id}
        keep = sorted(allowed)[:cores]
        allowed_set = set(keep)
    else:
        allowed_set = {str(c) for c in cores}
    return [t for t in tasks if t.core_id in allowed_set]


def declared_cells(
    *,
    presets: Sequence[str],
    tasks: Sequence[Any],
    repeats: int,
    slice_spec: dict[str, Any] | None = None,
) -> set[tuple[str, str, int]]:
    """Every (arm, task_id, repeat) the declaration covers."""
    if slice_spec and slice_spec.get("arms"):
        preset_set = set(slice_spec["arms"])
        arms = [p for p in presets if p in preset_set]
    else:
        arms = list(presets)
    filtered = _filter_tasks_by_slice(tasks, slice_spec)
    return {
        (arm, task.id, repeat)
        for arm in arms
        for task in filtered
        for repeat in range(repeats)
    }


def missing_cells(
    store: ResultStore,
    *,
    presets: Sequence[str],
    tasks: Sequence[Any],
    repeats: int,
    slice_spec: dict[str, Any] | None = None,
) -> set[tuple[str, str, int]]:
    """Cells to schedule: declared minus done, plus infra-voided."""
    target = declared_cells(
        presets=presets, tasks=tasks, repeats=repeats, slice_spec=slice_spec,
    )
    done = store.completed()
    voided = {
        (r["arm"], r["task_id"], r["repeat"])
        for r in store.voided()
    }
    return (target - done) | (voided & target)


def coverage_summary(
    store: ResultStore,
    *,
    presets: Sequence[str],
    tasks: Sequence[Any],
    repeats: int,
    slice_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    declared = declared_cells(
        presets=presets, tasks=tasks, repeats=repeats, slice_spec=slice_spec,
    )
    done = store.completed() & declared
    voided = {
        (r["arm"], r["task_id"], r["repeat"])
        for r in store.voided()
    } & declared
    missing = declared - done
    by_arm: dict[str, dict[str, int]] = {}
    for arm in presets:
        arm_decl = {(a, t, r) for a, t, r in declared if a == arm}
        arm_done = {(a, t, r) for a, t, r in done if a == arm}
        by_arm[arm] = {
            "expected": len(arm_decl),
            "done": len(arm_done),
            "missing": len(arm_decl - arm_done),
        }
    total = len(declared)
    return {
        "declared_cells": total,
        "completed_cells": len(done),
        "missing_cells": len(missing),
        "voided_cells": len(voided),
        "complete_fraction": (len(done) / total) if total else None,
        "by_arm": by_arm,
    }


def sidecar_envelope(sidecar: ExperimentSidecar,
                     store: ResultStore,
                     *,
                     tasks: Sequence[Any],
                     slice_id: str | None = None) -> dict[str, Any]:
    """JSON-shaped read model for the UI adapter."""
    import harness as harness_mod

    plan = sidecar.run_plan()
    repeats = int(plan.base.get("repeats", 1))
    slice_spec = sidecar.slice_spec(slice_id)
    presets = sidecar.active_presets()
    cov = coverage_summary(
        store, presets=presets, tasks=tasks, repeats=repeats,
        slice_spec=slice_spec,
    )
    manifest = store.manifest()
    row_count = sum(1 for _ in store.raw_rows())
    return {
        "harness_version": harness_mod.__version__,
        "schema_version": sidecar.schema_version,
        "experiment": sidecar.data,
        "ledger": {
            "dir": str(sidecar.root.resolve()),
            "has_manifest": bool(manifest),
            "has_experiment_sidecar": True,
            "row_count": row_count,
            "manifest_id": manifest.get("id"),
        },
        "coverage": cov,
    }
