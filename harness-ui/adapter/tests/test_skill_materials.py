"""T5.4 — skill material regeneration stays in sync with openapi.snapshot.json."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "regenerate-skill-materials.py"
PACK = REPO / "benchmark" / "harness-ui-self.yaml"


def test_skill_materials_regenerate_identically() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_benchmark_pack_validates() -> None:
    adapter = REPO / "adapter" / "harness_json.py"
    proc = subprocess.run(
        [sys.executable, str(adapter), "pack-validate", str(PACK)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert '"valid":true' in proc.stdout.replace(" ", "")
