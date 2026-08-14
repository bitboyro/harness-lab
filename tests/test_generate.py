"""Generate workspace and materials bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.bundle import write_materials
from harness.generate_config import GenerateConfig
from harness.generate_run import run_analyze, run_materials, run_pipeline
from harness.generate_workspace import (
    MANIFEST_FILE,
    STATUS_FILE,
    is_terminal,
    read_manifest,
    read_status,
)


@pytest.fixture
def openapi_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "openapi.json"
    assert path.is_file()
    return path


def test_analyze_and_materials(tmp_path: Path, openapi_path: Path) -> None:
    ws = tmp_path / "job-1"
    analyze = run_analyze(openapi_path, ws, job_id="job-1")
    assert analyze["operation_count"] >= 1
    assert (ws / "analyze.json").is_file()
    assert (ws / "spec" / "original.openapi.yaml").is_file()

    summary = run_materials(openapi_path, ws)
    assert summary["tool_count"] >= 1
    assert (ws / "materials" / "tools.json").is_file()
    assert (ws / "materials" / "skills" / "generated.md").is_file()
    assert (ws / "materials" / "docs" / "curl.md").is_file()
    assert (ws / "materials" / "arms.json").is_file()

    status = read_status(ws)
    assert status is not None
    assert "analyze" in status.phases_done
    assert "materials" in status.phases_done


def test_generate_run_from_config(tmp_path: Path, openapi_path: Path) -> None:
    ws = tmp_path / "gen-run"
    ws.mkdir()
    config_path = ws / "generate.config.yaml"
    config_path.write_text(
        f"""\
schema_version: 1
job_id: gen-run
mcp_gateway: true
target:
  spec: {openapi_path}
phases:
  analyze: true
  materials:
    doc_budget: standard
    presets: [Z0, A1, C1]
output:
  dir: .
""",
        encoding="utf-8",
    )
    config = GenerateConfig.load(config_path)
    manifest = run_pipeline(config)
    assert manifest["job_id"] == "gen-run"
    assert (ws / MANIFEST_FILE).is_file()
    status = read_status(ws)
    assert status is not None
    assert is_terminal(status)
    assert status.phase == "complete"
    arms = json.loads((ws / "materials" / "arms.json").read_text())
    assert arms["probe"] == ["Z0", "A1", "C1"]


def test_write_materials_standalone(tmp_path: Path, openapi_path: Path) -> None:
    from harness.engine.generate import load_spec

    spec = load_spec(openapi_path)
    dest = tmp_path / "materials"
    summary = write_materials(spec, dest, presets=("Z0", "D1"))
    assert summary["arms_probe"] == ["Z0", "D1"]
    tools = json.loads((dest / "tools.json").read_text())
    assert tools["operations"]
    assert (dest / "code" / "api" / "operations.py").is_file()
