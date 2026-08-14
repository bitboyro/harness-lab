"""Enrich phase — heuristic + optional mocked LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.enrich import EnrichPlan, estimate_enrich_cost, run_enrich
from harness.engine.generate import load_spec
from harness.generate_config import GenerateConfig
from harness.generate_run import run_pipeline
from harness.generate_workspace import read_status


@pytest.fixture
def openapi_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "openapi.json"
    assert path.is_file()
    return path


def test_heuristic_enrich(tmp_path: Path, openapi_path: Path) -> None:
    ws = tmp_path / "enrich-h"
    ws.mkdir()
    (ws / "generate.config.yaml").write_text(
        f"""\
schema_version: 1
job_id: enrich-h
target:
  spec: {openapi_path}
phases:
  analyze: true
  enrich: true
  materials: true
  fixtures: false
  pack: false
output:
  dir: .
""",
        encoding="utf-8",
    )
    config = GenerateConfig.load(ws / "generate.config.yaml")
    assert config.enrich is not None
    assert not config.enrich.use_llm
    manifest = run_pipeline(config, yes=True)
    assert (ws / "spec" / "enriched.openapi.yaml").is_file()
    assert (ws / "spec" / "enrichment.patch.yaml").is_file()
    assert (ws / "doc_gaps.md").is_file()
    assert (ws / "materials" / "skills" / "authored.md").is_file()
    authored = (ws / "materials" / "skills" / "authored.md").read_text()
    assert "authored skill" in authored.lower()
    status = read_status(ws)
    assert status is not None
    assert "enrich" in status.phases_done
    assert manifest.get("enrich", {}).get("llm_used") is False


def test_llm_enrich_mocked(tmp_path: Path, openapi_path: Path) -> None:
    from harness.generate_run import run_analyze
    from harness.generate_workspace import init_workspace

    ws = tmp_path / "enrich-llm"
    init_workspace(ws, "enrich-llm")
    run_analyze(openapi_path, ws, job_id="enrich-llm")

    def fake_llm(system: str, user: str, model: str) -> dict:
        assert model == "gpt-5.6-luna"
        return {
            "operations": {
                "listTitles": {
                    "summary": "List every title",
                    "description": "Returns catalog titles for agents.",
                }
            },
            "authored_skill_extra": "Prefer listTitles before guessing ids.",
        }

    plan = EnrichPlan(model="gpt-5.6-luna", max_usd=2.0, use_llm=True)
    est = estimate_enrich_cost(load_spec(openapi_path), plan)
    assert est.estimated_usd > 0
    assert est.within_cap()

    summary = run_enrich(ws, plan=plan, yes=True, llm_complete=fake_llm)
    assert summary["llm_used"] is True
    assert (ws / "spec" / "enriched.openapi.yaml").is_file()
    assert (ws / "materials" / "skills" / "authored.md").read_text().find("Prefer listTitles") >= 0
    assert summary["enrich_model"] == "gpt-5.6-luna"


def test_field_http_gates_ab_arms(tmp_path: Path, openapi_path: Path) -> None:
    ws = tmp_path / "gate"
    ws.mkdir()
    (ws / "generate.config.yaml").write_text(
        f"""\
schema_version: 1
job_id: gate
mcp_gateway: false
target:
  spec: {openapi_path}
phases:
  analyze: true
  enrich: false
  materials:
    presets: [Z0, A1, A2, B1, C1, D1]
  fixtures: false
  pack: false
""",
        encoding="utf-8",
    )
    manifest = run_pipeline(GenerateConfig.load(ws / "generate.config.yaml"), yes=True)
    arms = manifest["arms_probe"]
    assert "A1" not in arms and "A2" not in arms and "B1" not in arms
    assert "Z0" in arms and "C1" in arms and "D1" in arms


def test_mcp_gateway_keeps_ab_arms(tmp_path: Path, openapi_path: Path) -> None:
    ws = tmp_path / "gw"
    ws.mkdir()
    (ws / "generate.config.yaml").write_text(
        f"""\
schema_version: 1
job_id: gw
mcp_gateway: true
target:
  spec: {openapi_path}
phases:
  analyze: true
  materials:
    presets: [Z0, A1, C1]
  fixtures: false
  pack: false
""",
        encoding="utf-8",
    )
    manifest = run_pipeline(GenerateConfig.load(ws / "generate.config.yaml"), yes=True)
    assert "A1" in manifest["arms_probe"]
