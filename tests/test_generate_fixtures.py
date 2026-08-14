"""G2 — fixture capture and graded pack generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from harness.generate_config import GenerateConfig
from harness.generate_run import run_analyze, run_pipeline
from harness.generate_workspace import read_manifest


@pytest.fixture
def openapi_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "openapi.json"
    assert path.is_file()
    return path


class _CatalogHandler(BaseHTTPRequestHandler):
    studios = [{"id": "s1", "name": "Acme Studios"}]
    series = [{"id": "ser1", "title": "Demo Series", "studio_id": "s1"}]

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        del format, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/studios/") and self.path != "/studios":
            body = {"id": "s1", "name": "Acme Studios"}
        elif self.path.startswith("/studios"):
            body = {"items": self.studios}
        elif self.path.startswith("/series/") and self.path != "/series":
            body = {"id": "ser1", "title": "Demo Series", "studio_id": "s1"}
        elif self.path.startswith("/series"):
            body = {"items": self.series}
        else:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def staging_server():
    server = HTTPServer(("127.0.0.1", 0), _CatalogHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    yield base
    server.shutdown()


def test_fixtures_and_pack_pipeline(
    tmp_path: Path,
    openapi_path: Path,
    staging_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = tmp_path / "gen-g2"
    ws.mkdir()
    config_path = ws / "generate.config.yaml"
    config_path.write_text(
        f"""\
schema_version: 1
job_id: gen-g2
target:
  spec: {openapi_path}
  base_url_env: TARGET_BASE_URL
phases:
  analyze: true
  materials: false
  fixtures: true
  pack: true
pack:
  id: catalog-probe
  min_graded_tasks: 2
  unanswerable_share: 0.15
output:
  dir: .
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGET_BASE_URL", staging_server)

    config = GenerateConfig.load(config_path)
    run_analyze(openapi_path, ws, job_id="gen-g2")
    manifest = run_pipeline(config)

    assert manifest["pack_id"] == "catalog-probe"
    assert manifest["graded_tasks"] >= 2
    assert (ws / "examples" / "manifest.yaml").is_file()
    assert (ws / "pack" / "pack.yaml").is_file()
    assert (ws / "pack" / "oracle").is_dir()

    # G2.2 — fixtures inject response examples into enriched OpenAPI.
    enriched = ws / "spec" / "enriched.openapi.yaml"
    assert enriched.is_file()
    import yaml

    doc = yaml.safe_load(enriched.read_text())
    list_resp = (
        doc["paths"]["/studios"]["get"]["responses"]["200"]["content"]["application/json"]
    )
    assert "example" in list_resp
    assert list_resp["example"]["items"][0]["id"] == "s1"

    # G3.5 — prompts must not embed oracle expect values.
    pack_yaml = yaml.safe_load((ws / "pack" / "pack.yaml").read_text())
    for task in pack_yaml["tasks"]:
        if not task.get("answerable"):
            continue
        prompt = task["prompt"]
        for g in task.get("grade") or []:
            if "expect" in g:
                assert str(g["expect"]) not in prompt
            if "value" in g:
                assert str(g["value"]) not in prompt
        assert "response" in prompt.lower()

    proc = subprocess.run(
        [sys.executable, "-m", "harness", "generate", "run", str(config_path), "--yes"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        env={**os.environ, "TARGET_BASE_URL": staging_server, "PYTHONPATH": "src"},
    )
    assert proc.returncode == 0, proc.stderr

    adapter = Path(__file__).resolve().parents[1] / "harness-ui" / "adapter" / "harness_json.py"
    if adapter.is_file():
        val = subprocess.run(
            [sys.executable, str(adapter), "pack-validate", str(ws / "pack" / "pack.yaml")],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        assert val.returncode == 0, val.stderr
        assert '"valid":true' in val.stdout.replace(" ", "")

    final = read_manifest(ws)
    assert final is not None
    assert final.get("fixture_count", 0) >= 2
