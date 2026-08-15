"""Generate-job workspace I/O for harness-ui and ``harness generate``.

The UI polls ``status.json``; failures land in ``errors.json``; success is
summarized in ``manifest.json``. All three are written atomically (tmp + rename)
so a subprocess crash mid-write never leaves a half file the poller has to guess
about.

Contract: harness-ui/docs/plan-openapi-to-experiment.md
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

STATUS_FILE = "status.json"
ERRORS_FILE = "errors.json"
MANIFEST_FILE = "manifest.json"
ANALYZE_FILE = "analyze.json"

SPEC_DIR = "spec"
MATERIALS_DIR = "materials"
EXAMPLES_DIR = "examples"
PACK_DIR = "pack"
ORIGINAL_SPEC = "original.openapi.yaml"
ENRICHED_SPEC = "enriched.openapi.yaml"


class GeneratePhase(StrEnum):
    ANALYZE = "analyze"
    ENRICH = "enrich"
    FIXTURES = "fixtures"
    MATERIALS = "materials"
    PACK = "pack"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(slots=True)
class GenerateStatus:
    job_id: str
    phase: str
    phases_done: list[str] = field(default_factory=list)
    message: str = ""
    fraction: float | None = None
    started_at: str = ""
    updated_at: str = ""
    cost_usd_so_far: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GenerateStatus:
        return cls(
            job_id=str(data["job_id"]),
            phase=str(data["phase"]),
            phases_done=list(data.get("phases_done") or []),
            message=str(data.get("message") or ""),
            fraction=data.get("fraction"),
            started_at=str(data.get("started_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            cost_usd_so_far=data.get("cost_usd_so_far"),
        )


@dataclass(slots=True)
class GenerateError(Exception):
    """Typed generate failure — also raised so ``except GenerateError`` works."""

    exit_code: int
    kind: str
    message: str
    phase: str | None = None
    operator_hint: str | None = None
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover - repr for logs
        return self.message

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "exit_code": self.exit_code,
            "kind": self.kind,
            "message": self.message,
        }
        if self.phase is not None:
            out["phase"] = self.phase
        if self.operator_hint is not None:
            out["operator_hint"] = self.operator_hint
        if self.details is not None:
            out["details"] = self.details
        return out


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def workspace_root(path: str | Path) -> Path:
    return Path(path).resolve()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_status(root: str | Path) -> GenerateStatus | None:
    path = workspace_root(root) / STATUS_FILE
    if not path.is_file():
        return None
    return GenerateStatus.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_status(root: str | Path, status: GenerateStatus) -> None:
    status.updated_at = utc_now()
    if not status.started_at:
        status.started_at = status.updated_at
    _atomic_write_json(workspace_root(root) / STATUS_FILE, status.to_dict())


def read_errors(root: str | Path) -> GenerateError | None:
    path = workspace_root(root) / ERRORS_FILE
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return GenerateError(
        exit_code=int(data["exit_code"]),
        kind=str(data["kind"]),
        message=str(data["message"]),
        phase=data.get("phase"),
        operator_hint=data.get("operator_hint") or data.get("operator_fix"),
        details=data.get("details"),
    )


def write_errors(root: str | Path, error: GenerateError) -> None:
    _atomic_write_json(workspace_root(root) / ERRORS_FILE, error.to_dict())


def read_manifest(root: str | Path) -> dict[str, Any] | None:
    path = workspace_root(root) / MANIFEST_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(root: str | Path, manifest: dict[str, Any]) -> None:
    _atomic_write_json(workspace_root(root) / MANIFEST_FILE, manifest)


def init_workspace(root: str | Path, job_id: str) -> None:
    """Ensure layout exists and status shows a fresh job."""
    root = workspace_root(root)
    (root / SPEC_DIR).mkdir(parents=True, exist_ok=True)
    (root / MATERIALS_DIR).mkdir(parents=True, exist_ok=True)
    write_status(
        root,
        GenerateStatus(
            job_id=job_id,
            phase=GeneratePhase.ANALYZE.value,
            phases_done=[],
            message="starting",
            fraction=0.0,
        ),
    )


def begin_phase(root: str | Path, phase: GeneratePhase, *,
                message: str = "", fraction: float | None = None) -> GenerateStatus:
    root = workspace_root(root)
    current = read_status(root)
    if current is None:
        raise FileNotFoundError(f"{root}: no {STATUS_FILE}")
    current.phase = phase.value
    current.message = message or phase.value
    if fraction is not None:
        current.fraction = fraction
    write_status(root, current)
    return current


def complete_phase(root: str | Path, phase: GeneratePhase, *,
                     message: str = "", fraction: float | None = None) -> GenerateStatus:
    root = workspace_root(root)
    current = read_status(root)
    if current is None:
        raise FileNotFoundError(f"{root}: no {STATUS_FILE}")
    if phase.value not in current.phases_done:
        current.phases_done.append(phase.value)
    current.message = message or f"{phase.value} complete"
    if fraction is not None:
        current.fraction = fraction
    write_status(root, current)
    return current


def mark_complete(root: str | Path, message: str = "complete") -> GenerateStatus:
    root = workspace_root(root)
    current = read_status(root)
    if current is None:
        raise FileNotFoundError(f"{root}: no {STATUS_FILE}")
    current.phase = GeneratePhase.COMPLETE.value
    current.message = message
    current.fraction = 1.0
    write_status(root, current)
    return current


def mark_failed(root: str | Path, error: GenerateError) -> None:
    root = workspace_root(root)
    current = read_status(root)
    if current is not None:
        current.phase = GeneratePhase.FAILED.value
        current.message = error.message
        write_status(root, current)
    write_errors(root, error)


def is_terminal(status: GenerateStatus | None) -> bool:
    if status is None:
        return False
    return status.phase in (GeneratePhase.COMPLETE.value, GeneratePhase.FAILED.value)


def spec_path_in_workspace(root: str | Path, *, enriched: bool = False) -> Path:
    name = ENRICHED_SPEC if enriched else ORIGINAL_SPEC
    return workspace_root(root) / SPEC_DIR / name
