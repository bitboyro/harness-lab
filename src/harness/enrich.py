"""Agentic / heuristic enrich for ``harness generate``.

Produces ``spec/enriched.openapi.yaml``, ``spec/enrichment.patch.yaml``,
``materials/skills/authored.md``, and ``doc_gaps.md``.

Heuristic enrich is free and always runs when the enrich phase is enabled.
Optional LLM enrich (``phases.enrich.model``) spends real money and requires
``--yes`` plus a cost cap (``max_usd``).

Contract: harness-ui/docs/plan-openapi-to-experiment.md
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from .engine.axes import ConfigError
from .engine.generate import ApiSpec, load_spec
from .engine.pricing import lookup
from .generate_workspace import (
    ANALYZE_FILE,
    ENRICHED_SPEC,
    MATERIALS_DIR,
    GenerateError,
    GeneratePhase,
    begin_phase,
    complete_phase,
    init_workspace,
    mark_failed,
    spec_path_in_workspace,
    workspace_root,
)

DOC_GAPS = "doc_gaps.md"
ENRICHMENT_PATCH = "enrichment.patch.yaml"
AUTHORED_SKILL = Path(MATERIALS_DIR) / "skills" / "authored.md"

#: Injected in tests — ``(system, user, model) -> JSON object``.
LlmComplete = Callable[[str, str, str], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class EnrichPlan:
    model: str | None
    max_usd: float
    use_llm: bool


@dataclass(frozen=True, slots=True)
class EnrichEstimate:
    model: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_usd: float
    max_usd: float

    def within_cap(self) -> bool:
        return self.estimated_usd <= self.max_usd


def parse_enrich_phase(raw: Any) -> EnrichPlan | None:
    """``false``/absent → None; ``true`` → heuristic; mapping → optional LLM."""
    if raw is False or raw is None:
        return None
    if raw is True:
        return EnrichPlan(model=None, max_usd=0.0, use_llm=False)
    if not isinstance(raw, dict):
        raise ConfigError("phases.enrich must be a boolean or a mapping")
    model = raw.get("model")
    max_usd = float(raw.get("max_usd", 2.0))
    if model:
        return EnrichPlan(model=str(model), max_usd=max_usd, use_llm=True)
    return EnrichPlan(model=None, max_usd=max_usd, use_llm=False)


def estimate_enrich_cost(spec: ApiSpec, plan: EnrichPlan) -> EnrichEstimate:
    if not plan.use_llm or not plan.model:
        return EnrichEstimate(
            model="heuristic",
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            estimated_usd=0.0,
            max_usd=plan.max_usd,
        )
    # Rough: ~80 tokens per operation of prompt + ~120 tokens of patch output.
    n = max(1, len(spec.operations))
    inp = 400 + n * 80
    out = 200 + n * 120
    rates = lookup(plan.model).short
    usd = (inp / 1_000_000) * rates.input + (out / 1_000_000) * rates.output
    # Pad — enrich prompts include the whole thin spec excerpt.
    usd *= 1.5
    return EnrichEstimate(
        model=plan.model,
        estimated_input_tokens=inp,
        estimated_output_tokens=out,
        estimated_usd=round(usd, 4),
        max_usd=plan.max_usd,
    )


def _humanize(operation_id: str) -> str:
    text = re.sub(r"[_\-/]+", " ", operation_id)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return text.strip().capitalize() or operation_id


def _doc_gaps(spec: ApiSpec, findings: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for op in spec.operations:
        if not (op.summary or "").strip():
            gaps.append(f"- `{op.operation_id}` ({op.method.upper()} {op.path}): missing summary")
        if not (op.description or "").strip():
            gaps.append(
                f"- `{op.operation_id}` ({op.method.upper()} {op.path}): missing description"
            )
        for param in op.parameters:
            name = param.get("name")
            if name and not (param.get("description") or "").strip():
                gaps.append(
                    f"- `{op.operation_id}` parameter `{name}`: missing description"
                )
    for f in findings:
        if f.get("severity") in {"high", "medium"}:
            gaps.append(
                f"- lint `{f.get('rule_id')}` ({f.get('severity')}): {f.get('message')}"
            )
    return gaps


def heuristic_enrich(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fill thin summaries/descriptions without an LLM. Returns (doc, patch)."""
    patch: dict[str, Any] = {"operations": {}}
    paths = doc.get("paths") or {}
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.startswith("x-") or not isinstance(op, dict):
                continue
            if method not in {
                "get", "put", "post", "delete", "options", "head", "patch", "trace",
            }:
                continue
            op_id = op.get("operationId") or f"{method}_{path}"
            changes: dict[str, Any] = {}
            if not (op.get("summary") or "").strip():
                summary = _humanize(str(op_id))
                op["summary"] = summary
                changes["summary"] = summary
            if not (op.get("description") or "").strip():
                desc = (
                    f"{op.get('summary') or _humanize(str(op_id))}. "
                    f"HTTP {method.upper()} `{path}`."
                )
                op["description"] = desc
                changes["description"] = desc
            params = op.get("parameters") or []
            param_changes: dict[str, str] = {}
            for param in params:
                if not isinstance(param, dict):
                    continue
                name = param.get("name")
                if not name or (param.get("description") or "").strip():
                    continue
                where = param.get("in", "query")
                text = f"{name} ({where} parameter for {op_id})"
                param["description"] = text
                param_changes[str(name)] = text
            if param_changes:
                changes["parameters"] = param_changes
            if changes:
                patch["operations"][str(op_id)] = changes
    return doc, patch


def _authored_skill_markdown(spec: ApiSpec) -> str:
    lines = [
        f"# {spec.title} — authored skill",
        "",
        "Workflow knowledge for packaging arms that bind an authored skill "
        "(`B1-auth`, `B2-auth`, `D2-auth`). Generated by `harness generate enrich`.",
        "",
        "## When to use which call",
        "",
    ]
    for op in spec.operations[:40]:
        summary = op.summary or _humanize(op.operation_id)
        lines.append(f"- **{op.operation_id}** (`{op.method.upper()} {op.path}`): {summary}")
    if len(spec.operations) > 40:
        lines.append(f"- …and {len(spec.operations) - 40} more operations on the surface.")
    lines.extend([
        "",
        "## Conventions",
        "",
        "- Prefer list/search endpoints before get-by-id when the id is unknown.",
        "- Do not invent identifiers; read them from prior responses.",
        "- Treat write operations as harmful unless the task explicitly asks.",
        "",
    ])
    return "\n".join(lines)


def _write_doc_gaps(workspace: Path, gaps: list[str], *, llm_used: bool) -> None:
    body = [
        "# Documentation gaps",
        "",
        f"Enrich mode: {'heuristic + LLM' if llm_used else 'heuristic'}.",
        "",
        "## Outstanding / noted",
        "",
    ]
    body.extend(gaps or ["- No gaps detected."])
    body.append("")
    (workspace / DOC_GAPS).write_text("\n".join(body), encoding="utf-8")


def _load_raw_doc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"} or text.lstrip().startswith(("openapi:", "swagger:")):
        doc = yaml.safe_load(text)
    else:
        doc = json.loads(text)
    if not isinstance(doc, dict):
        raise GenerateError(
            exit_code=2,
            kind="config",
            message=f"spec is not a mapping: {path}",
            phase=GeneratePhase.ENRICH.value,
        )
    return doc


def _default_llm_complete(system: str, user: str, model: str) -> dict[str, Any]:
    """One-shot JSON completion via the OpenAI SDK (lazy import)."""
    try:
        from openai import OpenAI
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "openai package missing; pip install -e '.[openai]'"
        ) from e
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    kwargs: dict[str, Any] = {"api_key": key}
    base = os.environ.get("OPENAI_BASE_URL")
    if base:
        kwargs["base_url"] = base
    client = OpenAI(**kwargs)
    # Some current OpenAI models (e.g. gpt-5.6-*) reject temperature=0 and
    # only accept the default — omit the field rather than force a value.
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = resp.choices[0].message.content or "{}"
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError("enrich LLM returned non-object JSON")
    return data


def _apply_llm_patch(doc: dict[str, Any], llm_patch: dict[str, Any]) -> dict[str, Any]:
    ops = (llm_patch.get("operations") or {}) if isinstance(llm_patch, dict) else {}
    paths = doc.get("paths") or {}
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId") or f"{method}_{path}"
            change = ops.get(str(op_id))
            if not isinstance(change, dict):
                continue
            if change.get("summary"):
                op["summary"] = str(change["summary"])
            if change.get("description"):
                op["description"] = str(change["description"])
            param_map = change.get("parameters") or {}
            if isinstance(param_map, dict):
                for param in op.get("parameters") or []:
                    if isinstance(param, dict) and param.get("name") in param_map:
                        param["description"] = str(param_map[param["name"]])
    return doc


def run_enrich(
    workspace: str | Path,
    *,
    plan: EnrichPlan,
    yes: bool = False,
    llm_complete: LlmComplete | None = None,
) -> dict[str, Any]:
    """Enrich the workspace spec. Raises ``GenerateError`` on hard failure."""
    workspace = workspace_root(workspace)
    init_workspace(workspace, workspace.name)
    begin_phase(
        workspace,
        GeneratePhase.ENRICH,
        message="Enriching OpenAPI + authored skill",
        fraction=0.25,
    )

    try:
        original = spec_path_in_workspace(workspace)
        if not original.is_file():
            raise GenerateError(
                exit_code=2,
                kind="config",
                message="no original spec in workspace; run analyze first",
                phase=GeneratePhase.ENRICH.value,
            )
        doc = _load_raw_doc(original)
        spec = load_spec(doc)
        estimate = estimate_enrich_cost(spec, plan)

        if plan.use_llm and not yes:
            raise GenerateError(
                exit_code=1,
                kind="approval",
                message=(
                    f"enrich LLM estimated ${estimate.estimated_usd:.4f} "
                    f"(cap ${estimate.max_usd:.2f}) on {estimate.model}; "
                    "re-run with --yes to spend"
                ),
                phase=GeneratePhase.ENRICH.value,
                operator_hint="Pass --yes after reviewing the projection",
                details={
                    "estimated_usd": estimate.estimated_usd,
                    "max_usd": estimate.max_usd,
                    "model": estimate.model,
                },
            )

        if plan.use_llm and not estimate.within_cap():
            raise GenerateError(
                exit_code=2,
                kind="budget",
                message=(
                    f"enrich estimate ${estimate.estimated_usd:.4f} exceeds "
                    f"max_usd ${estimate.max_usd:.2f}"
                ),
                phase=GeneratePhase.ENRICH.value,
            )

        doc, patch = heuristic_enrich(doc)
        llm_used = False
        authored_extra = ""

        if plan.use_llm and plan.model:
            complete = llm_complete or _default_llm_complete
            findings: list[dict[str, Any]] = []
            analyze_path = workspace / ANALYZE_FILE
            if analyze_path.is_file():
                findings = json.loads(analyze_path.read_text()).get("findings") or []
            system = (
                "You enrich thin OpenAPI docs for LLM agents. "
                "Return JSON only: "
                '{"operations":{"opId":{"summary":"...","description":"...",'
                '"parameters":{"name":"..."}}},'
                '"authored_skill_extra":"markdown tips"}'
            )
            thin = []
            for op in spec.operations[:60]:
                thin.append({
                    "operation_id": op.operation_id,
                    "method": op.method,
                    "path": op.path,
                    "summary": op.summary,
                    "description": (op.description or "")[:240],
                })
            user = json.dumps({
                "title": spec.title,
                "operations": thin,
                "lint_findings": findings[:20],
            })
            try:
                llm_patch = complete(system, user, plan.model)
            except Exception as exc:  # noqa: BLE001
                raise GenerateError(
                    exit_code=40,
                    kind="provider",
                    message=f"enrich LLM failed: {exc}",
                    phase=GeneratePhase.ENRICH.value,
                ) from exc
            doc = _apply_llm_patch(doc, llm_patch)
            patch["llm"] = {
                "model": plan.model,
                "operations": llm_patch.get("operations") or {},
            }
            authored_extra = str(llm_patch.get("authored_skill_extra") or "").strip()
            llm_used = True

        enriched_path = workspace / "spec" / ENRICHED_SPEC
        enriched_path.parent.mkdir(parents=True, exist_ok=True)
        enriched_path.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        (workspace / "spec" / ENRICHMENT_PATCH).write_text(
            yaml.safe_dump(patch, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        enriched_spec = load_spec(doc)
        skill = _authored_skill_markdown(enriched_spec)
        if authored_extra:
            skill += "\n## Model notes\n\n" + authored_extra + "\n"
        authored_path = workspace / AUTHORED_SKILL
        authored_path.parent.mkdir(parents=True, exist_ok=True)
        authored_path.write_text(skill, encoding="utf-8")

        findings = []
        if (workspace / ANALYZE_FILE).is_file():
            findings = json.loads((workspace / ANALYZE_FILE).read_text()).get("findings") or []
        gaps = _doc_gaps(enriched_spec, findings)
        _write_doc_gaps(workspace, gaps, llm_used=llm_used)

        summary = {
            "enriched_spec": f"spec/{ENRICHED_SPEC}",
            "patch_path": f"spec/{ENRICHMENT_PATCH}",
            "authored_skill": str(AUTHORED_SKILL),
            "doc_gaps": DOC_GAPS,
            "operations_patched": len(patch.get("operations") or {}),
            "llm_used": llm_used,
            "estimated_usd": estimate.estimated_usd if llm_used else 0.0,
            "enrich_model": plan.model if llm_used else None,
        }
        complete_phase(
            workspace,
            GeneratePhase.ENRICH,
            message=(
                f"enriched {summary['operations_patched']} operations"
                + (" + LLM" if llm_used else " (heuristic)")
            ),
            fraction=0.35,
        )
        return summary
    except GenerateError as err:
        mark_failed(workspace, err)
        raise
    except Exception as exc:
        err = GenerateError(
            exit_code=40,
            kind="generate",
            message=str(exc),
            phase=GeneratePhase.ENRICH.value,
        )
        mark_failed(workspace, err)
        raise err from exc
