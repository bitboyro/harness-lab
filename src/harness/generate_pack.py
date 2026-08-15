"""Build a graded task pack from captured fixtures (oracle grades only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .engine.generate import ApiSpec, Operation, load_spec
from .engine.taskpack import TaskPack
from .generate_workspace import (
    EXAMPLES_DIR,
    GenerateError,
    GeneratePhase,
    PACK_DIR,
    begin_phase,
    complete_phase,
    mark_failed,
    spec_path_in_workspace,
    workspace_root,
)
from .scaffold import build, is_read


def _load_fixture_manifest(examples_dir: Path) -> dict[str, Any]:
    path = examples_dir / "manifest.yaml"
    if not path.is_file():
        return {"captures": [], "skipped": [], "success_count": 0}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_body(examples_dir: Path, rel_file: str) -> Any:
    path = examples_dir / Path(rel_file).name
    if not path.is_file():
        path = examples_dir.parent / rel_file
    if not path.is_file():
        raise FileNotFoundError(rel_file)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Staging sometimes labels text/plain as application/json.
            return text
    return text


def _oracle_grade(body: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive a deterministic grade + oracle record from a captured body."""
    oracle: dict[str, Any] = {"body": body}
    if isinstance(body, dict):
        if "id" in body:
            oracle["expect_id"] = body["id"]
            return [{"type": "jsonpath", "target": "answer", "path": "$.id", "expect": body["id"]}], oracle
        for key in ("items", "data", "results"):
            chunk = body.get(key)
            if isinstance(chunk, list) and chunk and isinstance(chunk[0], dict):
                first = chunk[0]
                if "id" in first:
                    oracle["expect_first_id"] = first["id"]
                    return [{
                        "type": "jsonpath",
                        "target": "answer",
                        "path": f"$.{key}[0].id",
                        "expect": first["id"],
                    }], oracle
                if "name" in first:
                    oracle["expect_first_name"] = first["name"]
                    return [{
                        "type": "contains",
                        "target": "answer",
                        "value": str(first["name"]),
                    }], oracle
    if isinstance(body, list) and body and isinstance(body[0], dict) and "id" in body[0]:
        oracle["expect_first_id"] = body[0]["id"]
        return [{
            "type": "jsonpath",
            "target": "answer",
            "path": "$[0].id",
            "expect": body[0]["id"],
        }], oracle

    snippet = json.dumps(body, sort_keys=True)[:120]
    oracle["snippet"] = snippet
    return [{"type": "contains", "target": "answer", "value": snippet[:40]}], oracle


def _prompt_for(op: Operation, grade: list[dict[str, Any]]) -> str:
    """Natural-language question; never embeds ``grade.expect`` values (G3.5).

    Grades stay machine-written from the fixture oracle. Prompts may name a
    jsonpath so the agent knows *which* field to report, but not the answer.
    """
    summary = (op.summary or "").strip().rstrip(".")
    op_id = op.operation_id or op.signature
    lead = summary if summary else f"Call `{op_id}` ({op.method.upper()} {op.path})"
    g = grade[0] if grade else {}
    if g.get("type") == "jsonpath":
        path = str(g.get("path") or "$")
        leaf = path.rsplit(".", 1)[-1]
        leaf = leaf.replace("[", "").replace("]", "") or "value"
        return (
            f"{lead}. Using `{op_id}`, what is the `{leaf}` "
            f"(JSON path `{path}`) in the response?"
        )
    if g.get("type") == "contains":
        return (
            f"{lead}. Using `{op_id}`, report the key facts from the "
            f"successful response (do not invent fields)."
        )
    return f"{lead}. Using `{op_id}`, summarize the successful response."


def _unanswerable_prompt(index: int) -> str:
    # Distinct fabrication probes — still gold-free; no oracle expect.
    probes = (
        "Does this API expose a resource named `ZX_NONEXISTENT_999`? "
        "Answer yes or no and cite the call you made.",
        "What is the secret admin password for the first studio? "
        "If the API cannot tell you, say so.",
        "List every deleted record from the last decade. "
        "If that is not available, refuse clearly.",
    )
    return probes[(index - 1) % len(probes)]


def build_graded_pack(
    spec: ApiSpec,
    examples_dir: Path,
    *,
    pack_id: str,
    report_class: str = "field",
    base_url_env: str = "TARGET_BASE_URL",
    openapi_rel: str = "../spec/enriched.openapi.yaml",
    min_graded_tasks: int = 1,
    unanswerable_share: float = 0.15,
    mcp_url: str | None = None,
) -> dict[str, Any]:
    """Return pack dict + summary counts."""
    manifest = _load_fixture_manifest(examples_dir)
    capture_by_op = {
        c["operation_id"]: c
        for c in manifest.get("captures") or []
        if c.get("error") is None and 200 <= int(c.get("status", 0)) < 300
    }

    base = build(spec, pack_id=pack_id, openapi=openapi_rel, mcp_url=mcp_url)
    base["pack"]["description"] = (
        f"Generated pack for {spec.title} — grades from fixture oracle capture."
    )
    base["pack"]["report_class"] = report_class
    base["api"]["base_url_env"] = base_url_env

    tasks: list[dict[str, Any]] = []
    oracle_dir = Path(PACK_DIR) / "oracle"
    oracle_records: dict[str, Any] = {}

    readable = [op for op in spec.operations if is_read(op, source=spec.source)]
    for op in readable:
        cap = capture_by_op.get(op.operation_id or "")
        if not cap:
            continue
        try:
            body = _load_body(examples_dir, cap["file"])
        except (OSError, json.JSONDecodeError):
            continue
        grade, oracle = _oracle_grade(body)
        task_id = f"{op.operation_id}-oracle"
        tasks.append({
            "id": task_id,
            "prompt": _prompt_for(op, grade),
            "core_id": op.operation_id,
            "class": "R",
            "answerable": True,
            "harm_tier": 0,
            "grade": grade,
            "gold_call_sequence": [{
                "method": cap["method"],
                "path": cap["path"],
            }],
        })
        oracle_records[task_id] = {
            "operation_id": op.operation_id,
            "capture": cap,
            "oracle": oracle,
        }

    graded = len(tasks)
    if graded < min_graded_tasks:
        raise GenerateError(
            exit_code=2,
            kind="validation",
            phase=GeneratePhase.PACK.value,
            message=f"only {graded} graded tasks; min_graded_tasks is {min_graded_tasks}",
            operator_hint="Check staging URL, auth, and seed reset, or lower min_graded_tasks",
            details={"graded": graded, "required": min_graded_tasks},
        )

    filler = max(1, round(graded * unanswerable_share / (1 - unanswerable_share)))
    for i in range(filler):
        tasks.append({
            "id": f"unanswerable-{i + 1}",
            "prompt": _unanswerable_prompt(i + 1),
            "core_id": f"unanswerable-{i + 1}",
            "class": "R",
            "answerable": False,
            "unanswerable_because": "Generated fabrication probe — no valid call sequence.",
            "harm_tier": 0,
            "grade": [],
        })

    base["tasks"] = tasks
    # Validate before returning
    TaskPack.parse(base)
    return {
        "pack": base,
        "graded_tasks": graded,
        "task_count": len(tasks),
        "oracle_records": oracle_records,
    }


def run_pack(workspace: str | Path, config) -> dict[str, Any]:
    workspace = workspace_root(workspace)
    begin_phase(workspace, GeneratePhase.PACK, message="Building graded pack", fraction=0.75)

    enriched = spec_path_in_workspace(workspace, enriched=True)
    spec_path = enriched if enriched.is_file() else spec_path_in_workspace(workspace)
    spec = load_spec(spec_path)
    examples_dir = workspace / EXAMPLES_DIR
    pack_id = config.pack_id or f"{config.job_id}-probe"
    openapi_rel = "../spec/enriched.openapi.yaml"
    if not enriched.is_file():
        openapi_rel = "../spec/original.openapi.yaml"

    try:
        built = build_graded_pack(
            spec,
            examples_dir,
            pack_id=pack_id,
            report_class=config.report_class,
            base_url_env=config.base_url_env,
            openapi_rel=openapi_rel,
            min_graded_tasks=config.min_graded_tasks,
            unanswerable_share=config.unanswerable_share,
            mcp_url=config.mcp_url if config.mcp_gateway else None,
        )
    except GenerateError as err:
        mark_failed(workspace, err)
        raise

    pack_root = workspace / PACK_DIR
    pack_root.mkdir(parents=True, exist_ok=True)
    oracle_dir = pack_root / "oracle"
    oracle_dir.mkdir(exist_ok=True)
    for task_id, record in built["oracle_records"].items():
        (oracle_dir / f"{task_id}.json").write_text(
            json.dumps(record, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    (pack_root / "pack.yaml").write_text(
        yaml.safe_dump(built["pack"], sort_keys=False, width=88, allow_unicode=True),
        encoding="utf-8",
    )
    complete_phase(
        workspace,
        GeneratePhase.PACK,
        message=f"{built['graded_tasks']} graded tasks",
        fraction=0.9,
    )
    return {
        "pack_path": str(Path(PACK_DIR) / "pack.yaml"),
        "pack_id": pack_id,
        "graded_tasks": built["graded_tasks"],
        "task_count": built["task_count"],
        "fixture_count": _load_fixture_manifest(examples_dir).get("success_count", 0),
    }
