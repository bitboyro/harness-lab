"""``harness generate`` phase implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .bundle import copy_spec_source, write_materials
from .engine import rules as rules_mod
from .engine.generate import ApiSpec, load_spec
from .engine.lint import scorecard
from .enrich import run_enrich
from .generate_config import GenerateConfig
from .generate_fixtures import run_fixtures_from_config
from .generate_pack import run_pack
from .generate_workspace import (
    ANALYZE_FILE,
    ENRICHED_SPEC,
    MATERIALS_DIR,
    GenerateError,
    GeneratePhase,
    begin_phase,
    complete_phase,
    init_workspace,
    mark_complete,
    mark_failed,
    read_manifest,
    spec_path_in_workspace,
    utc_now,
    write_manifest,
    workspace_root,
)


def run_analyze(spec_source: str | Path, workspace: str | Path, *,
                job_id: str | None = None) -> dict[str, Any]:
    """Lint a spec and write ``analyze.json`` into the workspace."""
    workspace = workspace_root(workspace)
    job_id = job_id or workspace.name
    init_workspace(workspace, job_id)
    begin_phase(workspace, GeneratePhase.ANALYZE, message="Linting OpenAPI spec", fraction=0.05)

    spec = load_spec(spec_source)
    dest_spec = spec_path_in_workspace(workspace)
    copy_spec_source(Path(spec_source), dest_spec)

    rules_mod.register_defaults()
    card = scorecard(spec)
    payload = {
        "harness_version": __version__,
        "spec_title": spec.title,
        "spec_version": spec.version,
        "operation_count": len(spec.operations),
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
    (workspace / ANALYZE_FILE).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    complete_phase(
        workspace,
        GeneratePhase.ANALYZE,
        message=f"{len(card.findings)} lint findings",
        fraction=0.2,
    )
    return payload


def run_materials(
    spec_source: str | Path | ApiSpec,
    workspace: str | Path,
    *,
    doc_budget=None,
    presets: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Write mechanical materials under ``materials/``."""
    from .engine.axes import DocBudget

    workspace = workspace_root(workspace)
    if doc_budget is None:
        doc_budget = DocBudget.STANDARD

    begin_phase(workspace, GeneratePhase.MATERIALS,
                message="Generating packaging materials", fraction=0.4)

    if isinstance(spec_source, ApiSpec):
        spec = spec_source
    else:
        path = Path(spec_source)
        if path.is_file():
            spec = load_spec(path)
        else:
            spec = load_spec(spec_source)

    enriched = spec_path_in_workspace(workspace, enriched=True)
    if enriched.is_file():
        spec = load_spec(enriched)
    else:
        original = spec_path_in_workspace(workspace)
        if original.is_file():
            spec = load_spec(original)

    summary = write_materials(
        spec,
        workspace / MATERIALS_DIR,
        doc_budget=doc_budget,
        presets=presets or None,
    )
    complete_phase(
        workspace,
        GeneratePhase.MATERIALS,
        message=f"{summary['tool_count']} tools, {summary['operation_count']} operations",
        fraction=0.7,
    )
    return summary


def run_pipeline(config: GenerateConfig, *, yes: bool = True) -> dict[str, Any]:
    """Run configured phases and write ``manifest.json``."""
    workspace = workspace_root(config.workspace)
    analyze_payload: dict[str, Any] | None = None
    materials_summary: dict[str, Any] | None = None
    pack_summary: dict[str, Any] | None = None
    enrich_summary: dict[str, Any] | None = None
    active_phase = GeneratePhase.ANALYZE

    try:
        if config.run_analyze:
            active_phase = GeneratePhase.ANALYZE
            analyze_payload = run_analyze(config.spec, workspace, job_id=config.job_id)
        else:
            init_workspace(workspace, config.job_id)
            dest = spec_path_in_workspace(workspace)
            if not dest.is_file():
                copy_spec_source(config.spec, dest)

        if config.enrich is not None:
            active_phase = GeneratePhase.ENRICH
            enrich_summary = run_enrich(workspace, plan=config.enrich, yes=yes)

        # Plan order: fixtures (inject examples into enriched spec) before
        # materials so tools/docs see captured response examples (G2.2).
        if config.run_fixtures:
            active_phase = GeneratePhase.FIXTURES
            run_fixtures_from_config(config)

        if config.run_materials:
            active_phase = GeneratePhase.MATERIALS
            materials_summary = run_materials(
                config.spec,
                workspace,
                doc_budget=config.doc_budget,
                presets=_gate_presets(config),
            )

        if config.run_pack:
            active_phase = GeneratePhase.PACK
            pack_summary = run_pack(workspace, config)

        spec_used = spec_path_in_workspace(workspace, enriched=True)
        if not spec_used.is_file():
            spec_used = spec_path_in_workspace(workspace)
        spec_used = spec_used.resolve()

        arms_probe: list[str] = []
        arms_path = workspace / MATERIALS_DIR / "arms.json"
        if arms_path.is_file():
            arms_probe = json.loads(arms_path.read_text())["probe"]

        try:
            enriched_rel = str(spec_used.relative_to(workspace))
        except ValueError:
            enriched_rel = spec_used.name

        manifest: dict[str, Any] = {
            "job_id": config.job_id,
            "target_id": config.target_id,
            "harness_version": __version__,
            "created_at": utc_now(),
            "enriched_spec": enriched_rel,
            "materials_dir": MATERIALS_DIR,
            "analyze_path": ANALYZE_FILE if analyze_payload else None,
            "arms_probe": arms_probe,
            "operation_count": (analyze_payload or {}).get("operation_count")
            or (materials_summary or {}).get("operation_count"),
            "validation": "unvalidated",
            "phases_done": [],
            "mcp_gateway": config.mcp_gateway,
        }
        if enrich_summary:
            manifest["enrich"] = {
                "llm_used": enrich_summary.get("llm_used"),
                "enrich_model": enrich_summary.get("enrich_model"),
                "operations_patched": enrich_summary.get("operations_patched"),
                "estimated_usd": enrich_summary.get("estimated_usd"),
                "authored_skill": enrich_summary.get("authored_skill"),
                "doc_gaps": enrich_summary.get("doc_gaps"),
            }
        if pack_summary:
            manifest.update(pack_summary)
        status_path = workspace / "status.json"
        if status_path.is_file():
            manifest["phases_done"] = json.loads(status_path.read_text()).get("phases_done", [])

        write_manifest(workspace, manifest)
        mark_complete(workspace, message="generate complete")
        return manifest
    except GenerateError:
        raise
    except Exception as exc:
        mark_failed(
            workspace,
            GenerateError(
                exit_code=40,
                kind="generate",
                message=str(exc),
                phase=active_phase.value,
            ),
        )
        raise


#: Field HTTP without an MCP gateway cannot execute A/B tool-call arms.
_FIELD_HTTP_SAFE = ("Z0", "C1", "D1")


def _gate_presets(config: GenerateConfig) -> tuple[str, ...]:
    presets = config.presets
    if config.mcp_gateway or not presets:
        return presets
    gated = tuple(p for p in presets if not p.startswith(("A", "B")))
    return gated or _FIELD_HTTP_SAFE
