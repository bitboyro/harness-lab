"""Parse ``generate.config.yaml`` for ``harness generate run``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .engine.axes import ConfigError, DocBudget
from .enrich import EnrichPlan, parse_enrich_phase


@dataclass(frozen=True, slots=True)
class TargetAuth:
    type: str
    env: str | None = None
    header_name: str | None = None


@dataclass(frozen=True, slots=True)
class GenerateConfig:
    job_id: str
    spec: Path
    workspace: Path
    doc_budget: DocBudget
    presets: tuple[str, ...]
    run_analyze: bool
    run_materials: bool
    run_fixtures: bool
    run_pack: bool
    enrich: EnrichPlan | None
    base_url_env: str
    seed: int | None
    auth: TargetAuth | None
    min_graded_tasks: int
    unanswerable_share: float
    pack_id: str | None
    report_class: str
    fixture_path_params: dict[str, dict[str, str]]
    target_id: str | None = None
    #: When true, A/B MCP arms stay in the probe list (gateway available).
    mcp_gateway: bool = False
    #: Literal MCP HTTP URL written into the pack when mcp_gateway is true.
    mcp_url: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> GenerateConfig:
        path = Path(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: expected a mapping at the top level")
        if int(raw.get("schema_version", 0)) != 1:
            raise ConfigError(f"{path}: unsupported schema_version")

        job_id = str(raw.get("job_id") or path.parent.name)
        target = raw.get("target") or {}
        if not isinstance(target, dict):
            raise ConfigError(f"{path}: target must be a mapping")

        spec_raw = target.get("spec")
        if not spec_raw:
            raise ConfigError(f"{path}: target.spec is required")
        spec_path = Path(spec_raw)
        if not spec_path.is_absolute():
            spec_path = (path.parent / spec_path).resolve()

        output = raw.get("output") or {}
        workspace = path.parent
        if isinstance(output, dict) and output.get("dir") not in (None, "."):
            workspace = (path.parent / str(output["dir"])).resolve()

        phases = raw.get("phases") or {}
        materials = phases.get("materials") if isinstance(phases, dict) else {}
        if materials is None:
            materials = {}
        doc_raw = "standard"
        presets: tuple[str, ...] = ()
        if isinstance(materials, dict):
            doc_raw = str(materials.get("doc_budget") or "standard")
            preset_list = materials.get("presets")
            if preset_list:
                presets = tuple(str(p) for p in preset_list)

        try:
            doc_budget = DocBudget(doc_raw)
        except ValueError as e:
            raise ConfigError(f"{path}: invalid doc_budget {doc_raw!r}") from e

        run_analyze = True
        run_materials = True
        run_fixtures = False
        run_pack = False
        enrich: EnrichPlan | None = None
        if isinstance(phases, dict):
            run_analyze = bool(phases.get("analyze", True))
            run_materials = materials is not False and bool(phases.get("materials", True))
            run_fixtures = bool(phases.get("fixtures", False))
            run_pack = bool(phases.get("pack", False))
            try:
                enrich = parse_enrich_phase(phases.get("enrich"))
            except ConfigError as e:
                raise ConfigError(f"{path}: {e}") from e

        base_url_env = str(target.get("base_url_env") or "TARGET_BASE_URL")
        seed_raw = target.get("seed")
        seed = int(seed_raw) if seed_raw is not None else None

        auth: TargetAuth | None = None
        auth_raw = target.get("auth")
        if isinstance(auth_raw, dict):
            auth = TargetAuth(
                type=str(auth_raw.get("type") or "none"),
                env=auth_raw.get("env"),
                header_name=auth_raw.get("header_name"),
            )

        pack_raw = raw.get("pack") or {}
        min_graded = 20
        unanswerable_share = 0.15
        pack_id: str | None = None
        report_class = "field"
        if isinstance(pack_raw, dict):
            min_graded = int(pack_raw.get("min_graded_tasks", min_graded))
            unanswerable_share = float(pack_raw.get("unanswerable_share", unanswerable_share))
            pack_id = pack_raw.get("id")
            if pack_id is not None:
                pack_id = str(pack_id)
            report_class = str(pack_raw.get("report_class") or report_class)

        fixture_path_params: dict[str, dict[str, str]] = {}
        fixtures_raw = phases.get("fixtures") if isinstance(phases, dict) else None
        if isinstance(fixtures_raw, dict):
            overrides = fixtures_raw.get("path_params")
            if isinstance(overrides, dict):
                for op_id, params in overrides.items():
                    if isinstance(params, dict):
                        fixture_path_params[str(op_id)] = {
                            str(k): str(v) for k, v in params.items()
                        }

        target_id = target.get("id")
        if target_id is not None:
            target_id = str(target_id)

        mcp_gateway = bool(raw.get("mcp_gateway", False))
        mcp_url_raw = raw.get("mcp_url")
        mcp_url = str(mcp_url_raw) if mcp_url_raw else None

        return cls(
            job_id=job_id,
            spec=spec_path,
            workspace=workspace,
            doc_budget=doc_budget,
            presets=presets,
            run_analyze=run_analyze,
            run_materials=run_materials,
            run_fixtures=run_fixtures,
            run_pack=run_pack,
            enrich=enrich,
            base_url_env=base_url_env,
            seed=seed,
            auth=auth,
            min_graded_tasks=min_graded,
            unanswerable_share=unanswerable_share,
            pack_id=pack_id,
            report_class=report_class,
            fixture_path_params=fixture_path_params,
            target_id=target_id,
            mcp_gateway=mcp_gateway,
            mcp_url=mcp_url,
        )
