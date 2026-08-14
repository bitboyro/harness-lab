#!/usr/bin/env python3
"""Harness → JSON adapter for harness-ui.

The only place that imports harness internals for the UI. Numbers come from
Report / ResultStore / progress / lint / taskpack — never recomputed here.

Usage (from repo root, harness installed or src/ on PYTHONPATH):

    python harness-ui/adapter/harness_json.py report results/auth-smoke
    python harness-ui/adapter/harness_json.py progress results/auth-smoke
    python harness-ui/adapter/harness_json.py lint examples/openapi.json
    python harness-ui/adapter/harness_json.py generate-status /tmp/gen-job
    python harness-ui/adapter/harness_json.py generate-manifest /tmp/gen-job
    python harness-ui/adapter/harness_json.py pack-validate examples/plan.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EXPECT_VERSION = "0.0.1"
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VERSION = 40


def _ensure_src_on_path() -> None:
    """Local checkout: allow importing from repo ``src/`` without install."""
    # harness-ui/adapter/this.py → parents[2] is the repo root
    repo = Path(__file__).resolve().parents[2]
    src = repo / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _import_harness(expect_version: str):
    """Import harness and refuse to proceed on a version mismatch."""
    _ensure_src_on_path()
    try:
        import harness
    except ImportError as e:
        print(f"failed to import harness: {e}", file=sys.stderr)
        raise SystemExit(EXIT_VERSION) from e

    actual = getattr(harness, "__version__", None)
    if actual != expect_version:
        print(
            f"harness version mismatch: expected {expect_version!r}, got {actual!r}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_VERSION)
    return harness


def _emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, default=str, separators=(",", ":")))
    return EXIT_OK


def _validation_flag(report_class: str) -> str:
    """Controlled ledgers are validated; everything else is unvalidated."""
    if "controlled" in (report_class or "").lower():
        return "validated-controlled"
    return "unvalidated"


# ---- report --------------------------------------------------------------


def cmd_report(directory: Path) -> dict[str, Any]:
    from harness.engine.analysis import Report
    from harness.engine.results import ResultStore

    store = ResultStore(directory)
    rows = list(store.rows())
    if not rows:
        raise FileNotFoundError(f"no results in {directory}")
    manifest = store.manifest()
    report = Report(rows=rows, manifest=manifest)
    verdict = report.verdict()

    incomplete = {
        k: {"have": v[0], "expected": v[1]}
        for k, v in report.incomplete_arms.items()
    }

    z0_gate = None
    if report.z0_gate is not None:
        passed, substantive, graded = report.z0_gate
        z0_gate = {
            "passed": passed,
            "substantive_answers": substantive,
            "graded": graded,
        }

    arms_out: dict[str, Any] = {}
    for name, arm in report.arms.items():
        conf = arm.confusion
        lift = report.lift(name)
        arms_out[name] = {
            "arm": name,
            "name": arm.name,
            "label": arm.label,
            "description": arm.description,
            "is_control": arm.is_control,
            "n": arm.n,
            "graded": len(arm.graded),
            "success_rate": arm.success_rate,
            "abstention_accuracy": arm.abstention_accuracy,
            "harm_events": arm.harm_events,
            "harm_rate": arm.harm_rate,
            "truncation_rate": arm.truncation_rate,
            "lift": lift,
            "below_mde": report.below_mde(name),
            "composite_score": verdict.scores.get(name),
            "mean_wall_clock_seconds": arm.mean("wall_clock_seconds"),
            "cost_per_success_usd": arm.cost_per_success(report.pricing),
            "confusion": {
                "tp": conf.tp,
                "fp": conf.fp,
                "tn": conf.tn,
                "fn_abstained": conf.fn_abstained,
                "fn_confident": conf.fn_confident,
                "precision": conf.precision,
                "specificity": conf.specificity,
            },
            "tokens": {
                "static": arm.mean("static_tokens"),
                "per_call_overhead": arm.mean("per_call_overhead_tokens"),
                "session_setup": arm.mean("session_setup_tokens"),
            },
            "by_class": arm.by_class(),
            "outcome_counts": arm.outcome_counts(),
        }

    import harness as harness_mod

    return {
        "harness_version": harness_mod.__version__,
        "run": {
            "id": str(manifest.get("id") or report.run_id),
            "model": report.model,
            "provider": manifest.get("provider"),
            "reasoning_effort": manifest.get("reasoning_effort"),
            "difficulty": manifest.get("difficulty"),
            "report_class": report.report_class,
            "tasks": manifest.get("tasks") if manifest.get("tasks") is not None
            else report.task_count,
            "repeats": manifest.get("repeats"),
            "cores": manifest.get("cores"),
            "planned": manifest.get("planned"),
            "n_rows": len(report.rows),
            "presets": list(manifest.get("presets") or sorted(report.arms)),
            "mde_pp": report.mde_pp,
            "baseline_success": report.baseline,
            "pooling_refused": report.pooling_refused,
            "incomplete_arms": incomplete,
            "z0_gate": z0_gate,
            "task_classes": report.task_classes,
            "truncated_count": report.truncated_count,
            "error_count": len(report.error_rows),
        },
        "verdict": {
            "winner": verdict.winner,
            "leader": verdict.leader,
            "runner_up": verdict.runner_up,
            "reason": verdict.reason,
            "scores": dict(verdict.scores),
            "caveats": list(verdict.caveats),
        },
        "arms": arms_out,
        "validation": _validation_flag(report.report_class),
    }


# ---- analyze (deep-dive) -------------------------------------------------


def cmd_analyze(directory: Path, *, only: str | None = None) -> dict[str, Any]:
    """Deep-dive sections JSON — same payload as ``harness analyze --json -``."""
    from harness.deep_analysis import analyze_directory

    keys = [k.strip() for k in only.split(",")] if only else None
    return analyze_directory(directory, only=keys)


# ---- progress ------------------------------------------------------------


def _read_progress_tolerant(directory: Path):
    """Like ``engine.progress.read``, but skip torn / invalid JSONL lines.

    A live writer may leave a partial last line; crashing the progress poll
    would make the UI look stuck while the run is fine.
    """
    from harness.engine.progress import Progress

    root = Path(directory)
    ledger = root / "results.jsonl"
    rows: list[dict[str, Any]] = []
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    manifest: dict[str, Any] = {}
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    expected = manifest.get("planned")
    if expected is None and manifest.get("presets") and manifest.get("tasks"):
        expected = (
            len(manifest["presets"])
            * int(manifest["tasks"])
            * int(manifest.get("repeats", 1))
        )
    expected = int(expected) if expected else None
    if expected is not None and expected < len(rows):
        expected = len(rows)

    started_at = None
    elapsed = 0.0
    if manifest.get("created_at"):
        started_at = datetime.fromisoformat(manifest["created_at"])
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    return Progress(
        done=len(rows),
        expected=expected,
        by_arm=dict(Counter(r["arm"] for r in rows)),
        started_at=started_at,
        elapsed_seconds=elapsed,
        outcomes=dict(Counter(r["outcome"] for r in rows)),
    )


def cmd_progress(directory: Path) -> dict[str, Any]:
    from harness.engine import progress as progress_mod

    # Prefer the engine reader; fall back to a torn-line-tolerant path.
    try:
        prog = progress_mod.read(directory)
    except json.JSONDecodeError:
        prog = _read_progress_tolerant(directory)

    import harness as harness_mod

    started = None
    if prog.started_at is not None:
        started = prog.started_at.isoformat()

    return {
        "harness_version": harness_mod.__version__,
        "done": prog.done,
        "expected": prog.expected,
        "fraction": prog.fraction,
        "eta_seconds": prog.eta_seconds,
        "elapsed_seconds": prog.elapsed_seconds,
        "started_at": started,
        "by_arm": dict(prog.by_arm),
        "outcomes": dict(prog.outcomes),
    }


# ---- lint ----------------------------------------------------------------


def cmd_lint(spec_path: Path) -> dict[str, Any]:
    from harness.engine import rules as rules_mod
    from harness.engine.generate import load_spec
    from harness.engine.lint import scorecard

    rules_mod.register_defaults()
    spec = load_spec(spec_path)
    card = scorecard(spec)

    import harness as harness_mod

    return {
        "harness_version": harness_mod.__version__,
        "spec_path": str(spec_path),
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": str(f.severity),
                "confidence": str(f.confidence),
                "message": f.message,
                "location": f.location,
            }
            for f in card.findings
        ],
        "rules_run": card.rules_run,
        "rules_measured": card.rules_measured,
        "measured_fraction": card.measured_fraction,
        "footer": card.footer(),
    }


# ---- pack-validate -------------------------------------------------------


def cmd_pack_validate(path: Path, base_url: str | None) -> dict[str, Any]:
    import yaml

    from harness.engine.taskpack import PackError, TaskPack

    import harness as harness_mod

    version = harness_mod.__version__

    def _invalid(error: str) -> dict[str, Any]:
        return {
            "harness_version": version,
            "path": str(path),
            "valid": False,
            "error": error,
            "pack_id": None,
            "task_count": None,
            "production_risk": None,
        }

    try:
        raw = yaml.safe_load(path.read_text())
    except OSError as e:
        return _invalid(str(e))
    except yaml.YAMLError as e:
        return _invalid(f"{path}: invalid YAML: {e}")

    if not isinstance(raw, dict):
        return _invalid(f"{path}: expected a mapping at the top level")

    try:
        pack = TaskPack.parse(raw)
    except PackError as e:
        return _invalid(str(e))

    return {
        "harness_version": version,
        "path": str(path),
        "valid": True,
        "error": None,
        "pack_id": pack.pack.id,
        "task_count": len(pack.tasks),
        "unavailable_metrics": pack.unavailable_metrics(),
        "production_risk": pack.production_risk(base_url),
    }


# ---- experiment sidecar (S6) -----------------------------------------------


def cmd_experiment_read(directory: Path, *, slice_id: str | None = None) -> dict[str, Any]:
    from harness.engine.experiment_sidecar import ExperimentSidecar, sidecar_envelope
    from harness.study import resolve_tasks

    sidecar = ExperimentSidecar.load(directory)
    store = __import__("harness.engine.results", fromlist=["ResultStore"]).ResultStore(directory)
    tasks = resolve_tasks(sidecar.run_plan(), manifest=store.manifest() or None)
    return sidecar_envelope(sidecar, store, tasks=tasks, slice_id=slice_id)


def cmd_experiment_coverage(directory: Path, *, slice_id: str | None = None) -> dict[str, Any]:
    from harness.engine.experiment_sidecar import ExperimentSidecar, coverage_summary
    from harness.engine.results import ResultStore
    from harness.study import resolve_tasks

    sidecar = ExperimentSidecar.load(directory)
    store = ResultStore(directory)
    plan = sidecar.run_plan()
    tasks = resolve_tasks(plan, manifest=store.manifest() or None)
    repeats = int(plan.base.get("repeats", 1))
    import harness as harness_mod

    cov = coverage_summary(
        store,
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=repeats,
        slice_spec=sidecar.slice_spec(slice_id),
    )
    return {
        "harness_version": harness_mod.__version__,
        "experiment_id": sidecar.id,
        "status": sidecar.status,
        "slice": slice_id,
        "coverage": cov,
    }


def cmd_experiment_missing(directory: Path, *, slice_id: str | None = None) -> dict[str, Any]:
    from harness.engine.experiment_sidecar import ExperimentSidecar, missing_cells
    from harness.engine.results import ResultStore
    from harness.study import resolve_tasks

    sidecar = ExperimentSidecar.load(directory)
    store = ResultStore(directory)
    plan = sidecar.run_plan()
    tasks = resolve_tasks(plan, manifest=store.manifest() or None)
    repeats = int(plan.base.get("repeats", 1))
    missing = missing_cells(
        store,
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=repeats,
        slice_spec=sidecar.slice_spec(slice_id),
    )
    import harness as harness_mod

    return {
        "harness_version": harness_mod.__version__,
        "experiment_id": sidecar.id,
        "slice": slice_id,
        "missing_cells": len(missing),
        "cells": [
            {"arm": a, "task_id": t, "repeat": r}
            for a, t, r in sorted(missing)
        ],
    }


def cmd_experiment_snapshot(directory: Path) -> dict[str, Any]:
    from harness.cli import cmd_experiment_snapshot
    import argparse

    code = cmd_experiment_snapshot(argparse.Namespace(dir=directory))
    if code != 0:
        raise RuntimeError(f"snapshot failed with exit {code}")
    from harness.engine.experiment_sidecar import ExperimentSidecar

    sidecar = ExperimentSidecar.load(directory)
    snaps = sidecar.data.get("report_snapshots") or []
    latest = snaps[-1] if snaps else {}
    import harness as harness_mod

    return {
        "harness_version": harness_mod.__version__,
        "experiment_id": sidecar.id,
        "snapshot": latest,
    }


def cmd_generate_status(directory: Path) -> dict[str, Any]:
    from harness.generate_workspace import is_terminal, read_errors, read_status

    import harness as harness_mod

    status = read_status(directory)
    err = read_errors(directory)
    terminal = is_terminal(status)
    if status is None and err is None:
        raise FileNotFoundError(f"no generate workspace in {directory}")

    payload: dict[str, Any] = {
        "harness_version": harness_mod.__version__,
        "terminal": terminal,
        "status": status.to_dict() if status else None,
        "error": err.to_dict() if err else None,
    }
    return payload


def cmd_run_config() -> dict[str, Any]:
    """UI catalog: presets, defaults, experiment templates — not computed metrics."""
    import harness
    from harness.engine.axes import (
        Caching,
        DocBudget,
        ErrorDetail,
        McpRevision,
        ResponseShape,
        SchemaDetail,
        builtin_arm_names,
        describe,
        preset,
        short_name,
    )

    # Packaging axes alone define the arm; affordance/run axes are fillers so
    # ``preset()`` can build a Variant for short_name / describe (same pattern
    # as analysis._preset_variant for legacy ledgers).
    catalog_base = dict(
        schema_detail=SchemaDetail.STANDARD,
        response_shape=ResponseShape.AS_IS,
        error_detail=ErrorDetail.FIELD_SCOPED,
        doc_budget=DocBudget.STANDARD,
        surface_size=0,
        model="?",
        reasoning_effort="?",
        temperature=0.0,
        caching=Caching.OFF,
        repeats=1,
        mcp_revision=McpRevision.R2026_07_28,
    )

    presets: list[dict[str, Any]] = []
    for name in sorted(builtin_arm_names()):
        try:
            variant = preset(name, **catalog_base)
            label = short_name(variant)
            description = describe(variant)
        except Exception:  # noqa: BLE001 — catalog must still load
            label = name
            description = name
        presets.append({
            "id": name,
            "group": name[0] if name else "?",
            "label": label,
            "description": description,
            "requiresSandbox": name.startswith("D"),
        })

    return {
        "harness_version": harness.__version__,
        "presets": presets,
        "providers": ["openai"],
        "models": ["gpt-5.6-luna"],
        "reasoningEfforts": ["none", "minimal", "low", "medium", "high"],
        "mcpRevisions": ["2026-07-28", "legacy"],
        "difficulties": ["easy", "medium", "hard"],
        "presetBundles": {
            "smoke": ["Z0", "A1", "D1"],
            "probe": ["Z0", "A1", "A2", "C1", "D1"],
            "controlled-ladder": [
                "Z0", "Z1", "A1", "A2", "B1-auth", "B2-auth", "C1", "D1", "D2-auth",
            ],
        },
        "defaultRun": {
            "id": "local-smoke",
            "packId": None,
            "targetId": None,
            "presets": [],
            "model": "gpt-5.6-luna",
            "provider": "openai",
            "reasoningEffort": "low",
            "repeats": 1,
            "smoke": True,
            "probe": False,
            "resume": False,
            "dryRun": False,
            "allowCodeSandbox": True,
        },
        "experimentTemplates": [
            {
                "id": "baseline-80",
                "label": "Baseline 80-core ladder",
                "description": "Authored-skill contrasts on eager, meta-tools, and code-fs.",
                "defaults": {
                    "experimentId": "baseline-experiment-80",
                    "rationale": (
                        "Eighty cores for within-class power. Authored skill vs bare "
                        "method on eager MCP, meta-tools MCP, and code-fs."
                    ),
                    "model": "gpt-5.6-luna",
                    "reasoningEffort": "low",
                    "repeats": 3,
                    "surfaceSize": 50,
                    "mcpRevision": "2026-07-28",
                    "presets": [
                        "Z0", "Z1", "A1", "A2", "B1-auth", "B2-auth", "C1", "D1", "D2-auth",
                    ],
                    "cores": 80,
                    "seed": 1,
                    "fanOut": 8,
                    "difficulty": "hard",
                    "maxUsd": 400,
                    "includeSmokeSlice": True,
                },
            },
            {
                "id": "pipeline-smoke",
                "label": "Pipeline smoke (2 cores)",
                "description": "Cheap sidecar to verify scheduling before a full matrix.",
                "defaults": {
                    "experimentId": "experiment-smoke",
                    "rationale": "Two cores across Z0 and eager/meta-tools — pipeline check only.",
                    "model": "gpt-5.6-luna",
                    "reasoningEffort": "low",
                    "repeats": 1,
                    "surfaceSize": 50,
                    "mcpRevision": "2026-07-28",
                    "presets": ["Z0", "A1", "A2"],
                    "cores": 2,
                    "seed": 1,
                    "fanOut": 2,
                    "difficulty": "easy",
                    "maxUsd": 20,
                    "includeSmokeSlice": False,
                },
            },
        ],
    }


def cmd_generate_manifest(directory: Path) -> dict[str, Any]:
    from harness.generate_workspace import read_manifest, read_status

    import harness as harness_mod

    manifest = read_manifest(directory)
    if manifest is None:
        status = read_status(directory)
        phase = status.phase if status else "unknown"
        raise FileNotFoundError(
            f"no manifest in {directory} (phase={phase!r})"
        )
    return {
        "harness_version": harness_mod.__version__,
        "manifest": manifest,
    }


# ---- CLI -----------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness_json.py",
        description="Serialize harness Report / progress / lint / pack to JSON.",
    )
    p.add_argument(
        "--expect-version",
        default=DEFAULT_EXPECT_VERSION,
        help=f"require harness.__version__ (default {DEFAULT_EXPECT_VERSION})",
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("report", help="results directory → AdapterReport JSON")
    r.add_argument("dir", type=Path)

    an = sub.add_parser("analyze", help="results directory → deep-analysis JSON")
    an.add_argument("dir", type=Path)
    an.add_argument("--only", default=None, help="comma-separated section keys")

    pr = sub.add_parser("progress", help="results directory → AdapterProgress JSON")
    pr.add_argument("dir", type=Path)

    li = sub.add_parser("lint", help="OpenAPI path → AdapterLint JSON")
    li.add_argument("spec", type=Path)

    pv = sub.add_parser("pack-validate", help="pack YAML → AdapterPackValidate JSON")
    pv.add_argument("path", type=Path)
    pv.add_argument("--base-url", default=None)

    er = sub.add_parser("experiment", help="experiment sidecar subcommands")
    er_sub = er.add_subparsers(dest="experiment_command", required=True)

    er_read = er_sub.add_parser("read", help="experiment.yaml + coverage envelope")
    er_read.add_argument("dir", type=Path)
    er_read.add_argument("--slice", default=None)

    er_cov = er_sub.add_parser("coverage", help="coverage counts only")
    er_cov.add_argument("dir", type=Path)
    er_cov.add_argument("--slice", default=None)

    er_miss = er_sub.add_parser("missing", help="missing cell list")
    er_miss.add_argument("dir", type=Path)
    er_miss.add_argument("--slice", default=None)

    er_snap = er_sub.add_parser("snapshot", help="write dated report snapshot")
    er_snap.add_argument("dir", type=Path)

    gs = sub.add_parser("generate-status", help="generate workspace → status envelope")
    gs.add_argument("dir", type=Path)

    gm = sub.add_parser("generate-manifest", help="generate workspace → manifest JSON")
    gm.add_argument("dir", type=Path)

    sub.add_parser("run-config", help="UI defaults and preset catalog")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _import_harness(args.expect_version)

    try:
        if args.command == "report":
            if not args.dir.is_dir():
                print(f"not a directory: {args.dir}", file=sys.stderr)
                return EXIT_USAGE
            return _emit(cmd_report(args.dir.resolve()))

        if args.command == "analyze":
            if not args.dir.is_dir():
                print(f"not a directory: {args.dir}", file=sys.stderr)
                return EXIT_USAGE
            return _emit(cmd_analyze(args.dir.resolve(), only=args.only))

        if args.command == "progress":
            if not args.dir.is_dir():
                print(f"not a directory: {args.dir}", file=sys.stderr)
                return EXIT_USAGE
            return _emit(cmd_progress(args.dir.resolve()))

        if args.command == "lint":
            if not args.spec.is_file():
                print(f"not a file: {args.spec}", file=sys.stderr)
                return EXIT_USAGE
            return _emit(cmd_lint(args.spec.resolve()))

        if args.command == "pack-validate":
            if not args.path.is_file():
                print(f"not a file: {args.path}", file=sys.stderr)
                return EXIT_USAGE
            return _emit(cmd_pack_validate(args.path.resolve(), args.base_url))

        if args.command == "experiment":
            if not args.dir.is_dir():
                print(f"not a directory: {args.dir}", file=sys.stderr)
                return EXIT_USAGE
            directory = args.dir.resolve()
            if args.experiment_command == "read":
                return _emit(cmd_experiment_read(directory, slice_id=args.slice))
            if args.experiment_command == "coverage":
                return _emit(cmd_experiment_coverage(directory, slice_id=args.slice))
            if args.experiment_command == "missing":
                return _emit(cmd_experiment_missing(directory, slice_id=args.slice))
            if args.experiment_command == "snapshot":
                return _emit(cmd_experiment_snapshot(directory))
            print(f"unknown experiment command: {args.experiment_command}",
                  file=sys.stderr)
            return EXIT_USAGE

        if args.command == "run-config":
            return _emit(cmd_run_config())

        if args.command == "generate-status":
            if not args.dir.is_dir():
                print(f"not a directory: {args.dir}", file=sys.stderr)
                return EXIT_USAGE
            return _emit(cmd_generate_status(args.dir.resolve()))

        if args.command == "generate-manifest":
            if not args.dir.is_dir():
                print(f"not a directory: {args.dir}", file=sys.stderr)
                return EXIT_USAGE
            return _emit(cmd_generate_manifest(args.dir.resolve()))
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return EXIT_USAGE
    except OSError as e:
        print(str(e), file=sys.stderr)
        return EXIT_USAGE
    except Exception as e:  # noqa: BLE001 — surface as one stderr line
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_USAGE

    print(f"unknown command: {args.command}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
