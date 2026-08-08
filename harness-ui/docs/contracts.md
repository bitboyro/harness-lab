# Frozen contracts (S0)

Capability names are simultaneously MCP tool names and REST `operationId`s.
Java must **not** compute success rates, intervals, MDE, winner, pooling
refusals, cost projections, or pack validity — those come from the adapter or
the CLI subprocess.

Pinned harness wheel: assert `harness.__version__ == "0.0.1"` (release tag
`v0.0.1`) until a newer pin is agreed.

---

## Capabilities

| Constant | HTTP | Body / params | Success | Notes |
|---|---|---|---|---|
| `upload_contract` | `POST /api/v1/targets` | `multipart/form-data`: `file` (OpenAPI JSON/YAML) **or** `mcp_url` (text) | `201` → `Target` | Writes `/data/targets/<id>/` |
| `list_targets` | `GET /api/v1/targets` | — | `200` → `Target[]` | |
| `lint_target` | `POST /api/v1/targets/{id}/lint` | — | `200` → adapter `lint` JSON | Adapter subcommand |
| `draft_pack` | `POST /api/v1/packs/draft` | `{ "targetId", "outId?" }` | `201` → `PackRef` | Spawns `harness scaffold` |
| `read_pack` | `GET /api/v1/packs/{id}` | — | `200` → `{ id, yaml }` | Raw YAML text |
| `write_pack` | `PUT /api/v1/packs/{id}` | `{ "yaml": "…" }` | `200` → `{ id, valid, error? }` | Validates via adapter |
| `validate_pack` | `POST /api/v1/packs/{id}/validate` | `{ "baseUrl?" }` | `200` → adapter `pack-validate` JSON | |
| `project_run_cost` | `POST /api/v1/runs/project` | `RunRequest` | `200` → `CostProjection` | Spawns `harness run` **without** `--yes`; exit 1 is success for dry-run |
| `start_run` | `POST /api/v1/runs` | `RunRequest` + `{ "approve": true }` | `202` → `RunJob` | Spawns with `--yes --stream` unless `dryRun` |
| `get_run_progress` | `GET /api/v1/runs/{id}/progress` | — | `200` → adapter `progress` + job status | |
| `list_runs` | `GET /api/v1/runs` | — | `200` → `RunSummary[]` | |
| `get_report` | `GET /api/v1/runs/{id}/report` | — | `200` → adapter `report` JSON | |
| `get_transcript` | `GET /api/v1/runs/{id}/transcripts/{arm}/{taskId}/{repeat}` | — | `200` → `{ text }` | Spawns `harness transcript` |
| `compare_runs` | `POST /api/v1/compare` | `{ "runIds": ["…"] }` | `200` → `CompareResult` | Exit 3 → `200` with `refused: true` |
| `get_brief` | `GET /api/v1/runs/{id}/brief` | — | `200` → adapter report-shaped brief JSON | Same serializer as report (insights skill consumes) |
| `list_artifacts` | `GET /api/v1/runs/{id}/artifacts` | — | `200` → `ArtifactRef[]` | |
| `get_artifact` | `GET /api/v1/runs/{id}/artifacts/{name}` | — | `200` file + CSP headers | Path traversal rejected `400` |
| `put_artifact` | `PUT /api/v1/runs/{id}/artifacts/{name}` | raw body | `201` → `ArtifactRef` | Agent-written insights etc. |

Also served (not capabilities):

- `GET /artifacts/{runId}/**` — same files, `X-Content-Type-Options: nosniff`, restrictive CSP; UI embeds in `<iframe sandbox="allow-scripts">` (no `allow-same-origin`).
- `GET /v3/api-docs` — OpenAPI for skill regeneration.
- SPA fallback for non-API routes.

---

## Shared DTOs

### `Target`

```json
{
  "id": "string",
  "kind": "openapi" | "mcp",
  "label": "string",
  "createdAt": "ISO-8601"
}
```

### `PackRef`

```json
{
  "id": "string",
  "path": "packs/<id>.yaml",
  "valid": true,
  "error": null
}
```

### `RunRequest`

```json
{
  "id": "string",
  "packId": "string | null",
  "targetId": "string | null",
  "presets": ["A1", "Z0"],
  "model": "string",
  "provider": "openai",
  "reasoningEffort": "string",
  "repeats": 1,
  "smoke": false,
  "probe": false,
  "resume": false,
  "dryRun": false,
  "allowCodeSandbox": false
}
```

`allowCodeSandbox` must be `true` to accept presets containing `D1`/`D2`; otherwise `400`.

### `CostProjection`

```json
{
  "projectionText": "string",
  "exitCode": 1,
  "stderrNames": ["OPENAI_API_KEY"]
}
```

Parsed from CLI stdout before the TTY confirm gate. Do not re-estimate in Java.

### `RunJob`

```json
{
  "id": "string",
  "status": "queued" | "running" | "succeeded" | "failed" | "cancelled" | "declined",
  "pid": 1234,
  "exitCode": null,
  "outDir": "/data/results/<id>",
  "startedAt": "ISO-8601",
  "finishedAt": null,
  "errorKind": null,
  "message": null
}
```

Exit-code mapping (CLI → status / HTTP):

| Code | Meaning | Treatment |
|---|---|---|
| 0 | success | `succeeded` |
| 1 | nothing to do / declined / dry-run gate | informational; dry-run → `CostProjection` |
| 2 | argument error | HTTP `400` |
| 3 | pooling refusal | surface verbatim (`CompareResult.refused`) |
| 40 | config/validation/infra | HTTP `400`/`503`; message from stderr (one sentence) |
| 130 | cancelled | `cancelled`, not `failed` |

### `CompareResult`

```json
{
  "refused": false,
  "refusalText": null,
  "brokenBoundary": null,
  "artifactDir": "compare/<id>/artifacts",
  "stdout": "string"
}
```

When exit code is 3: `refused: true`, `refusalText` contains `REFUSING TO POOL` body, `brokenBoundary` is the named boundary if parseable.

### Progress envelope (API wraps adapter)

```json
{
  "job": { "...RunJob" },
  "progress": { "...adapter progress schema" },
  "terminal": true
}
```

`terminal` is true when the owned process has exited (or never started and status is terminal). Disk alone cannot prove liveness.

---

## Adapter CLI

```
harness_json.py [--expect-version 0.0.1] <subcommand> …
```

| Subcommand | Args | Schema file |
|---|---|---|
| `report DIR` | results directory | `schemas/report.json` |
| `progress DIR` | results directory | `schemas/progress.json` |
| `lint SPEC` | OpenAPI path | `schemas/lint.json` |
| `pack-validate PATH` | pack YAML; optional `--base-url` | `schemas/pack-validate.json` |

Exit codes: `0` ok, `2` usage/IO, `40` version mismatch or import failure. Always JSON on stdout on success; errors as one line on stderr.

---

## Data paths

All mutable state under `/data` (compose volume). Resolve artifact paths with
`Path.normalize` against `results/<runId>/artifacts/` and reject escapes.

Artifact cache key: ledger row count (re-render when it grows).

---

## Capability constants (Java)

```java
public final class Capabilities {
  public static final String UPLOAD_CONTRACT = "upload_contract";
  public static final String LIST_TARGETS = "list_targets";
  public static final String LINT_TARGET = "lint_target";
  public static final String DRAFT_PACK = "draft_pack";
  public static final String READ_PACK = "read_pack";
  public static final String WRITE_PACK = "write_pack";
  public static final String VALIDATE_PACK = "validate_pack";
  public static final String PROJECT_RUN_COST = "project_run_cost";
  public static final String START_RUN = "start_run";
  public static final String GET_RUN_PROGRESS = "get_run_progress";
  public static final String LIST_RUNS = "list_runs";
  public static final String GET_REPORT = "get_report";
  public static final String GET_TRANSCRIPT = "get_transcript";
  public static final String COMPARE_RUNS = "compare_runs";
  public static final String GET_BRIEF = "get_brief";
  public static final String LIST_ARTIFACTS = "list_artifacts";
  public static final String GET_ARTIFACT = "get_artifact";
  public static final String PUT_ARTIFACT = "put_artifact";
  private Capabilities() {}
}
```
