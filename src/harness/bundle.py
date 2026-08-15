"""Write packaging materials from one OpenAPI spec (Output A).

Mechanical generation only — same functions every arm uses at run time (V1).
Authored skill and enriched spec are separate files the enrich phase adds later.

Contract: harness-ui/docs/plan-openapi-to-experiment.md
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .engine.axes import DocBudget, SchemaDetail
from .engine.generate import (
    ApiSpec,
    code_module_tree,
    curl_reference,
    meta_tool_defs,
    meta_tool_module,
    skill_markdown,
    tool_defs,
)
from .engine.packaging import ToolDef

#: Default probe arms — matches ``DEFAULT_PROBE_PRESETS`` in cli.py.
PROBE_PRESETS: tuple[str, ...] = ("Z0", "A1", "A2", "C1", "D1")
STANDARD_PRESETS: tuple[str, ...] = (*PROBE_PRESETS, "D2")
FIELD_PROBE_PRESETS: tuple[str, ...] = ("Z0", "A1", "A2", "B1", "B1-auth", "C1", "D1")


def _tool_json(tool: ToolDef) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


def write_materials(
    spec: ApiSpec,
    dest: str | Path,
    *,
    doc_budget: DocBudget = DocBudget.STANDARD,
    schema_detail: SchemaDetail = SchemaDetail.STANDARD,
    presets: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Materialize tools, skills, docs, and code trees under ``dest``."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    tools = [_tool_json(t) for t in tool_defs(spec, schema_detail)]
    meta = [_tool_json(t) for t in meta_tool_defs(spec)]
    (dest / "tools.json").write_text(
        json.dumps({"operations": tools, "meta_tools": meta}, indent=2) + "\n",
        encoding="utf-8",
    )

    skills = dest / "skills"
    skills.mkdir(exist_ok=True)
    (skills / "generated.md").write_text(
        skill_markdown(spec, doc_budget, progressive=False) + "\n",
        encoding="utf-8",
    )
    authored = skills / "authored.md"
    if not authored.is_file():
        # Placeholder until enrich lands; B1-auth binds this path at run time.
        authored.write_text(
            "# Authored skill\n\n"
            "TODO: run `harness generate enrich` or paste workflow knowledge here.\n",
            encoding="utf-8",
        )

    docs = dest / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "curl.md").write_text(
        curl_reference(spec, doc_budget) + "\n",
        encoding="utf-8",
    )

    _write_tree(dest / "code", code_module_tree(spec))
    _write_tree(dest / "code-discovery", meta_tool_module(spec))

    probe = list(presets or FIELD_PROBE_PRESETS)
    arms = {
        "probe": probe,
        "standard": list(STANDARD_PRESETS),
        "presets": probe,
    }
    (dest / "arms.json").write_text(json.dumps(arms, indent=2) + "\n", encoding="utf-8")

    return {
        "materials_dir": str(dest),
        "operation_count": len(spec.operations),
        "tool_count": len(tools),
        "arms_probe": probe,
    }


def _write_tree(base: Path, files: dict[Path, bytes]) -> None:
    if base.exists():
        shutil.rmtree(base)
    for rel, content in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def copy_spec_source(source: str | Path, dest: Path) -> None:
    """Copy or serialize a spec into the workspace ``spec/`` directory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    if source.is_file():
        shutil.copy2(source, dest)
        return
    # Already-parsed dict path: caller should write YAML/JSON separately.
    raise FileNotFoundError(source)
