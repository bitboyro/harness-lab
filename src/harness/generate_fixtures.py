"""Capture staging HTTP responses as fixture files for pack grading."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .engine.generate import ApiSpec, Operation, load_spec
from .generate_workspace import (
    ENRICHED_SPEC,
    EXAMPLES_DIR,
    GeneratePhase,
    begin_phase,
    complete_phase,
    spec_path_in_workspace,
    workspace_root,
)
from .scaffold import is_read

USER_AGENT = "harness-lab/0.1 (+https://github.com/bitboy-ro/harness-lab)"


@dataclass(slots=True)
class FixtureCapture:
    operation_id: str
    method: str
    path: str
    status: int
    content_type: str
    file: str
    request_url: str
    error: str | None = None


@dataclass(slots=True)
class FixtureResult:
    captures: list[FixtureCapture] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for c in self.captures if c.error is None and 200 <= c.status < 300)


def _auth_headers(
    auth_type: str,
    auth_env: str | None,
    header_name: str | None = None,
) -> dict[str, str]:
    if auth_type == "none" or not auth_env:
        return {}
    token = os.environ.get(auth_env)
    if not token:
        raise RuntimeError(f"{auth_env} is not set; fixtures need auth type {auth_type!r}")
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {token}"}
    if auth_type == "header":
        name = header_name or "X-Api-Key"
        return {name: token}
    if auth_type == "basic":
        return {"Authorization": f"Basic {token}"}
    raise RuntimeError(f"unsupported auth type: {auth_type!r}")


def _path_params(op: Operation) -> list[str]:
    names: list[str] = []
    for param in op.parameters:
        if param.get("in") == "path" and param.get("required"):
            names.append(str(param["name"]))
    # Also catch {id} tokens not declared (shouldn't happen in valid specs).
    for token in re.findall(r"\{([^}]+)\}", op.path):
        if token not in names:
            names.append(token)
    return names


def _query_params(op: Operation) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for param in op.parameters:
        if param.get("in") != "query":
            continue
        schema = param.get("schema") or {}
        if "default" in schema:
            out[str(param["name"])] = schema["default"]
        elif schema.get("type") == "integer":
            out[str(param["name"])] = 1
    return out


def _extract_ids(body: Any) -> list[str]:
    if isinstance(body, list):
        return [str(item["id"]) for item in body if isinstance(item, dict) and "id" in item]
    if isinstance(body, dict):
        for key in ("items", "data", "results", "studios", "series"):
            chunk = body.get(key)
            if isinstance(chunk, list):
                return _extract_ids(chunk)
        if "id" in body:
            return [str(body["id"])]
    return []


def _substitute_path(path: str, values: dict[str, str]) -> str | None:
    out = path
    for key in re.findall(r"\{([^}]+)\}", path):
        if key not in values:
            return None
        out = out.replace("{" + key + "}", urllib.parse.quote(str(values[key]), safe=""))
    return out


def _fetch(
    base_url: str,
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    headers: dict[str, str],
    timeout: float = 30.0,
) -> tuple[int, str, bytes]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    req = urllib.request.Request(
        url,
        method=method.upper(),
        headers={"Accept": "*/*", "User-Agent": USER_AGENT, **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "application/octet-stream")
            return resp.status, ctype.split(";")[0].strip(), body
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "text/plain"), e.read()


def _extension(content_type: str) -> str:
    if "json" in content_type:
        return ".json"
    if "xml" in content_type:
        return ".xml"
    if "yaml" in content_type:
        return ".yaml"
    return ".txt"


def _ordered_reads(spec: ApiSpec) -> list[Operation]:
    reads = [op for op in spec.operations if is_read(op, source=spec.source)]
    # Lists before gets so path ids can be harvested.
    def sort_key(op: Operation) -> tuple[int, str]:
        params = _path_params(op)
        return (len(params), op.operation_id or op.path)

    return sorted(reads, key=sort_key)


def capture_fixtures(
    workspace: str | Path,
    *,
    base_url: str,
    auth_type: str = "none",
    auth_env: str | None = None,
    header_name: str | None = None,
    path_overrides: dict[str, dict[str, str]] | None = None,
) -> FixtureResult:
    """Execute read operations against staging and write ``examples/``."""
    workspace = workspace_root(workspace)
    begin_phase(workspace, GeneratePhase.FIXTURES, message="Capturing fixtures", fraction=0.45)

    enriched = spec_path_in_workspace(workspace, enriched=True)
    spec_path = enriched if enriched.is_file() else spec_path_in_workspace(workspace)
    spec = load_spec(spec_path)

    examples = workspace / EXAMPLES_DIR
    examples.mkdir(parents=True, exist_ok=True)
    headers = _auth_headers(
        auth_type,
        auth_env,
        header_name,
    )
    overrides = path_overrides or {}
    id_pool: dict[str, str] = {}
    result = FixtureResult()

    for op in _ordered_reads(spec):
        params_needed = _path_params(op)
        param_values = dict(overrides.get(op.operation_id or "", {}))
        for name in params_needed:
            if name not in param_values and name in id_pool:
                param_values[name] = id_pool[name]
            # Common suffix patterns: studio_id, series_id, …
            stem = name.replace("_id", "")
            for key, val in id_pool.items():
                if key == stem or key.endswith(stem):
                    param_values.setdefault(name, val)

        path = _substitute_path(op.path, param_values)
        if path is None:
            result.skipped.append(op.operation_id or op.path)
            continue

        status, ctype, body = _fetch(
            base_url,
            op.method,
            path,
            query=_query_params(op),
            headers=headers,
        )
        rel_name = f"{op.operation_id or 'op'}{_extension(ctype)}"
        # operationIds sometimes contain path separators (httpbin: get_/anything).
        safe_name = re.sub(r"[^\w.-]+", "_", rel_name).strip("._") or "op"
        dest = examples / safe_name
        dest.write_bytes(body)

        capture = FixtureCapture(
            operation_id=op.operation_id or safe_name,
            method=op.method.upper(),
            path=op.path,
            status=status,
            content_type=ctype,
            file=str(Path(EXAMPLES_DIR) / safe_name),
            request_url=base_url.rstrip("/") + path,
        )
        if status >= 400:
            capture.error = f"HTTP {status}"
        result.captures.append(capture)

        if 200 <= status < 300 and "json" in ctype:
            try:
                parsed = json.loads(body.decode())
                for stem, val in _id_pool_from_response(op, parsed):
                    id_pool.setdefault(stem, val)
            except json.JSONDecodeError:
                pass

    manifest = {
        "captures": [
            {
                "operation_id": c.operation_id,
                "method": c.method,
                "path": c.path,
                "status": c.status,
                "content_type": c.content_type,
                "file": c.file,
                "request_url": c.request_url,
                "error": c.error,
            }
            for c in result.captures
        ],
        "skipped": result.skipped,
        "success_count": result.success_count,
    }
    (examples / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, width=88),
        encoding="utf-8",
    )
    inject_examples_into_spec(workspace, result.captures)
    complete_phase(
        workspace,
        GeneratePhase.FIXTURES,
        message=f"{result.success_count} fixtures captured",
        fraction=0.6,
    )
    return result


def inject_examples_into_spec(
    workspace: str | Path,
    captures: list[FixtureCapture],
) -> Path:
    """Patch response examples into ``spec/enriched.openapi.yaml`` (G2.2).

    Creates the enriched file from the original when enrich was skipped so
    materials/tools always see captured examples when fixtures ran.
    """
    workspace = workspace_root(workspace)
    enriched = spec_path_in_workspace(workspace, enriched=True)
    source = enriched if enriched.is_file() else spec_path_in_workspace(workspace)
    if not source.is_file():
        raise FileNotFoundError(f"no OpenAPI spec in workspace: {workspace}")

    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("OpenAPI root must be a mapping")

    paths = raw.setdefault("paths", {})
    for cap in captures:
        if cap.error or not (200 <= cap.status < 300):
            continue
        body_path = workspace / cap.file
        if not body_path.is_file():
            continue
        example_value = _example_value(body_path, cap.content_type)
        if example_value is None:
            # Point at the on-disk fixture when the body is not JSON.
            example_value = {"externalValue": f"../{cap.file}"}

        op_node = _find_operation_node(paths, cap.path, cap.method)
        if op_node is None:
            continue
        responses = op_node.setdefault("responses", {})
        # Prefer the captured status; fall back to a generic 200 bucket.
        status_key = str(cap.status)
        resp = responses.get(status_key) or responses.get("200") or {}
        if not isinstance(resp, dict):
            resp = {}
        responses[status_key] = resp
        content = resp.setdefault("content", {})
        media = content.setdefault(cap.content_type or "application/json", {})
        if not isinstance(media, dict):
            media = {}
            content[cap.content_type or "application/json"] = media
        if isinstance(example_value, dict) and "externalValue" in example_value:
            media["externalValue"] = example_value["externalValue"]
            media.pop("example", None)
        else:
            media["example"] = example_value
            media.pop("externalValue", None)

    enriched.parent.mkdir(parents=True, exist_ok=True)
    enriched.write_text(
        yaml.safe_dump(raw, sort_keys=False, width=88, allow_unicode=True),
        encoding="utf-8",
    )
    return enriched


def _example_value(body_path: Path, content_type: str) -> Any | None:
    data = body_path.read_bytes()
    if "json" in (content_type or "") or body_path.suffix == ".json":
        try:
            return json.loads(data.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return data.decode("utf-8", errors="replace")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text


def _find_operation_node(
    paths: dict[str, Any],
    path: str,
    method: str,
) -> dict[str, Any] | None:
    node = paths.get(path)
    if not isinstance(node, dict):
        # Tolerate trailing-slash drift between capture and spec.
        alt = path.rstrip("/") or "/"
        node = paths.get(alt) if alt != path else None
        if not isinstance(node, dict):
            slash = path if path.endswith("/") else path + "/"
            node = paths.get(slash)
    if not isinstance(node, dict):
        return None
    op = node.get(method.lower())
    return op if isinstance(op, dict) else None


def _id_pool_from_response(op: Operation, body: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    ids = _extract_ids(body)
    if not ids:
        return out
    op_id = op.operation_id or ""
    if op_id.startswith("list_"):
        stem = op_id.removeprefix("list_").rstrip("s")  # studios -> studio
        out.append((stem, ids[0]))
        out.append((stem + "_id", ids[0]))
    elif op_id.startswith("get_"):
        stem = op_id.removeprefix("get_")
        out.append((stem, ids[0]))
        out.append((stem + "_id", ids[0]))
    out.append(("id", ids[0]))
    return out


def run_fixtures_from_config(config) -> FixtureResult:
    """Resolve base URL from env and capture fixtures."""
    base_url = os.environ.get(config.base_url_env)
    if not base_url:
        raise RuntimeError(
            f"{config.base_url_env} is not set; fixtures need a staging base URL"
        )
    auth = config.auth
    return capture_fixtures(
        config.workspace,
        base_url=base_url,
        auth_type=auth.type if auth else "none",
        auth_env=auth.env if auth else None,
        header_name=auth.header_name if auth else None,
        path_overrides=config.fixture_path_params,
    )
