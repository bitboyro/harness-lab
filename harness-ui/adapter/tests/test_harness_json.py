"""Contract tests for the harness-ui Python adapter (S1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "harness-ui" / "adapter" / "harness_json.py"
SCHEMAS = REPO / "harness-ui" / "adapter" / "schemas"
PYTHON = REPO / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)

AUTH_SMOKE = REPO / "results" / "auth-smoke"
OPENAPI = REPO / "examples" / "openapi.json"
PLAN = REPO / "examples" / "plan.yaml"

MINIMAL_PACK = {
    "schema_version": 1,
    "pack": {"id": "adapter-test", "report_class": "field"},
    "api": {"base_url_env": "URL"},
    "tasks": [{"id": "t1", "prompt": "q", "class": "R"}],
}


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = [str(PYTHON), str(ADAPTER), *args]
    return subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=check,
    )


def _maybe_validate(payload: dict, schema_name: str) -> None:
    schema_path = SCHEMAS / schema_name
    try:
        import jsonschema
    except ImportError:
        # Structural minimum when jsonschema is not installed.
        assert isinstance(payload, dict)
        assert "harness_version" in payload
        return
    schema = json.loads(schema_path.read_text())
    jsonschema.validate(payload, schema)


def test_report_auth_smoke() -> None:
    assert AUTH_SMOKE.is_dir(), "results/auth-smoke fixture missing"
    proc = _run("report", str(AUTH_SMOKE))
    data = json.loads(proc.stdout)
    _maybe_validate(data, "report.json")
    assert data["harness_version"] == "0.0.1"
    assert data["run"]["id"] == "auth-smoke"
    assert data["validation"] == "validated-controlled"
    assert "verdict" in data and "arms" in data
    assert data["arms"], "expected at least one arm"
    sample = next(iter(data["arms"].values()))
    assert "confusion" in sample
    assert "tokens" in sample
    assert "by_class" in sample
    assert "outcome_counts" in sample


def test_progress_auth_smoke() -> None:
    proc = _run("progress", str(AUTH_SMOKE))
    data = json.loads(proc.stdout)
    _maybe_validate(data, "progress.json")
    assert data["done"] >= 1
    assert data["expected"] == 9
    assert isinstance(data["by_arm"], dict)
    assert isinstance(data["outcomes"], dict)


def test_progress_skips_torn_jsonl(tmp_path: Path) -> None:
    """A partial last line must not crash the progress poll."""
    dest = tmp_path / "torn"
    dest.mkdir()
    (dest / "manifest.json").write_text(
        json.dumps({"id": "torn", "planned": 2, "created_at": "2026-01-01T00:00:00+00:00"})
    )
    good = {
        "arm": "A1",
        "outcome": "pass",
        "task_id": "t1",
    }
    # Real ledgers are richer; progress only needs arm + outcome.
    (dest / "results.jsonl").write_text(json.dumps(good) + "\n{\"arm\": \"A1\", \"outc")
    proc = _run("progress", str(dest))
    data = json.loads(proc.stdout)
    assert data["done"] == 1
    assert data["by_arm"] == {"A1": 1}


def test_lint_openapi() -> None:
    assert OPENAPI.is_file()
    proc = _run("lint", str(OPENAPI))
    data = json.loads(proc.stdout)
    _maybe_validate(data, "lint.json")
    assert data["rules_run"] >= 1
    assert isinstance(data["findings"], list)
    assert "footer" in data and data["footer"]


def test_pack_validate_plan_yaml_is_invalid() -> None:
    """examples/plan.yaml is a run plan, not a task pack."""
    assert PLAN.is_file()
    proc = _run("pack-validate", str(PLAN))
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    _maybe_validate(data, "pack-validate.json")
    assert data["valid"] is False
    assert data["error"]


def test_pack_validate_good_pack(tmp_path: Path) -> None:
    path = tmp_path / "good.yaml"
    path.write_text(yaml.dump(MINIMAL_PACK))
    proc = _run("pack-validate", str(path))
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    _maybe_validate(data, "pack-validate.json")
    assert data["valid"] is True
    assert data["pack_id"] == "adapter-test"
    assert data["task_count"] == 1
    assert isinstance(data["unavailable_metrics"], dict)
    assert "production_risk" in data


def test_pack_validate_bad_pack(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump({"schema_version": 1, "pack": {"id": "x"}}))
    proc = _run("pack-validate", str(path))
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["valid"] is False
    assert data["error"]


def test_wrong_expect_version_exits_40() -> None:
    proc = _run(
        "--expect-version", "9.9.9",
        "progress", str(AUTH_SMOKE),
        check=False,
    )
    assert proc.returncode == 40
    assert "version mismatch" in proc.stderr.lower() or "9.9.9" in proc.stderr
