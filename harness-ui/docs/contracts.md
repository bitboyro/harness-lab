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
| `list_packs` | `GET /api/v1/packs` | — | `200` → `PackRef[]` | On-disk pack catalog for pickers |
| `read_pack` | `GET /api/v1/packs/{id}` | — | `200` → `{ id, yaml }` | Raw YAML text |
| `write_pack` | `PUT /api/v1/packs/{id}` | `{ "yaml": "…" }` | `200` → `{ id, valid, error? }` | Validates via adapter |
| `validate_pack` | `POST /api/v1/packs/{id}/validate` | `{ "baseUrl?" }` | `200` → adapter `pack-validate` JSON | |
| `project_run_cost` | `POST /api/v1/runs/project` | `RunRequest` | `200` → `CostProjection` | Spawns `harness run` **without** `--yes`; exit 1 is success for dry-run |
| `start_run` | `POST /api/v1/runs` | `RunRequest` + `{ "approve": true }` | `202` → `RunJob` | Spawns with `--yes --stream` unless `dryRun` |
| `get_run_progress` | `GET /api/v1/runs/{id}/progress` | — | `200` → adapter `progress` + job status | |
| `list_runs` | `GET /api/v1/runs` | — | `200` → `RunSummary[]` | |
| `get_report` | `GET /api/v1/runs/{id}/report` | — | `200` → adapter `report` JSON | |
| `get_analysis` | `GET /api/v1/runs/{id}/analysis` | `?only=` optional comma keys | `200` → adapter `analyze` JSON | Deep-dive tables; free |
| `get_transcript` | `GET /api/v1/runs/{id}/transcripts/{arm}/{taskId}/{repeat}` | — | `200` → `{ text }` | Spawns `harness transcript` |
| `compare_runs` | `POST /api/v1/compare` | `{ "runIds": ["…"] }` | `200` → `CompareResult` | Exit 3 → `200` with `refused: true` |
| `get_brief` | `GET /api/v1/runs/{id}/brief` | — | `200` → adapter report-shaped brief JSON | Same serializer as report (insights skill consumes) |
| `list_artifacts` | `GET /api/v1/runs/{id}/artifacts` | — | `200` → `ArtifactRef[]` | |
| `get_artifact` | `GET /api/v1/runs/{id}/artifacts/{name}` | — | `200` file + CSP headers | Path traversal rejected `400` |
| `put_artifact` | `PUT /api/v1/runs/{id}/artifacts/{name}` | raw body | `201` → `ArtifactRef` | Agent-written insights etc. |

### Experiment capabilities (S6 — additive; T6.x)

Runs **without** `experiment.yaml` keep the table above unchanged. When a results
directory contains an `experiment.yaml` sidecar (see
[experiment-schema.md](./experiment-schema.md)), these capabilities apply to the
**same** `/data/results/<id>/` path:

| Constant | HTTP | Body / params | Success | Notes |
|---|---|---|---|---|
| `create_experiment` | `POST /api/v1/experiments` | `{ "id", "yaml" }` or `{ "id", "planPath" }` | `201` → `ExperimentRef` | Writes sidecar only; ledger created on first run |
| `list_experiments` | `GET /api/v1/experiments` | — | `200` → `ExperimentSummary[]` | Dirs with `experiment.yaml`; includes legacy runs when `?all=true` |
| `get_experiment` | `GET /api/v1/experiments/{id}` | — | `200` → adapter `experiment read` JSON | Same `{id}` as `/runs/{id}` |
| `update_experiment` | `PUT /api/v1/experiments/{id}` | `{ "yaml": "…" }` | `200` → `ExperimentRef` | Draft or arm-add only; world lock enforced by adapter |
| `add_experiment_arms` | `POST /api/v1/experiments/{id}/arms` | `{ "presets": ["E1"] }` | `200` → `ExperimentRef` | Appends to `run_plan.include.presets` |
| `project_experiment_run` | `POST /api/v1/experiments/{id}/run/project` | `{ "slice?", "arms?", "allowCodeSandbox?" }` | `200` → `ExperimentRunProjection` | Missing cells only; CLI dry-run |
| `start_experiment_run` | `POST /api/v1/experiments/{id}/run` | above + `{ "approve": true }` | `202` → `RunJob` | Same job registry as `start_run` |
| `get_experiment_coverage` | `GET /api/v1/experiments/{id}/coverage` | `?slice=` | `200` → adapter `experiment coverage` JSON | |
| `list_experiment_reports` | `GET /api/v1/experiments/{id}/reports` | — | `200` → `ReportSnapshotRef[]` | From `report_snapshots` + disk |
| `snapshot_experiment_report` | `POST /api/v1/experiments/{id}/reports/snapshot` | — | `201` → `ReportSnapshotRef` | Adapter report JSON → `reports/` |

### Generate capabilities (G — additive; not implemented in Java until G4)

OpenAPI onboarding jobs live under `/data/generate/<jobId>/`. The CLI writes
`status.json`, `manifest.json`, and workspace artifacts; Java subprocesses the
CLI and reads structure via adapter JSON only.

| Constant | HTTP | Body / params | Success | Notes |
|---|---|---|---|---|
| `start_generate` | `POST /api/v1/generate` | `StartGenerateRequest` | `202` → `GenerateJob` | Writes `generate.config.yaml`, spawns `harness generate run --yes` |
| `get_generate_progress` | `GET /api/v1/generate/{jobId}/progress` | — | `200` → `GenerateProgress` | Adapter `generate-status` envelope |
| `get_generate_manifest` | `GET /api/v1/generate/{jobId}/manifest` | — | `200` → `GenerateManifest` | Adapter `generate-manifest`; 404 until complete |
| `list_generate_artifacts` | `GET /api/v1/generate/{jobId}/artifacts` | — | `200` → `ArtifactRef[]` | Same shape as run artifacts |
| `get_generate_artifact` | `GET /api/v1/generate/{jobId}/artifacts/{name}` | — | `200` file + CSP | Path traversal rejected `400` |
| `create_experiment_from_generate` | `POST /api/v1/generate/{jobId}/experiment` | `{ "experimentId", "planOverrides?" }` | `201` → `ExperimentRef` | Copies `pack/pack.yaml` → `/data/packs/`; writes sidecar |

### LLM provider config

The engine adapter is `openai` (OpenAI or any compatible server). Additional
providers are named profiles that still use that adapter, each with its own
key, base URL, and registered models. Keys live in
`/data/secrets/providers.env` and are never returned.

| Constant | HTTP | Body / params | Success | Notes |
|---|---|---|---|---|
| `get_llm_config` | `GET /api/v1/config/llm` | — | `200` → `LlmConfig` | Keys redacted (`apiKeySet`, hint only) |
| `upsert_provider` | `PUT /api/v1/config/providers/{id}` | `UpsertProviderRequest` | `200` → `ProviderView` | `apiKey` omitted keeps stored key; `""` clears. Cannot change adapter off `openai`. |
| `delete_provider` | `DELETE /api/v1/config/providers/{id}` | — | `204` | Built-in `openai` cannot be deleted |
| `upsert_model` | `PUT /api/v1/config/providers/{id}/models/{modelId}` | `{ "label?", "price?" }` | `200` → `ProviderView` | `price` is `HARNESS_PRICE_*` card (`in,out` / 4 / 8 values) |
| `delete_model` | `DELETE /api/v1/config/providers/{id}/models/{modelId}` | — | `200` → `ProviderView` | |

`get_run_progress`, `get_report`, and `list_runs` **do not change** — they keep
working on `/data/results/<id>/` whether or not the sidecar exists.

Also served (not capabilities):

- `GET /api/v1/config/run-defaults` — preset catalog, run defaults, experiment templates (adapter `run-config`).
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
`provider` is a UI profile id; Java maps it to the engine adapter (`openai`) and
injects that profile's key, base URL, and optional `HARNESS_PRICE_*` override.

### `LlmConfig`

```json
{
  "adapters": ["openai"],
  "adaptersNote": "string",
  "providers": [
    {
      "id": "openai",
      "label": "OpenAI",
      "adapter": "openai",
      "baseUrl": null,
      "builtin": true,
      "apiKeySet": false,
      "apiKeyHint": null,
      "processEnvKeySet": false,
      "processBaseUrl": null,
      "models": [{ "id": "gpt-5.6-luna", "label": "gpt-5.6-luna", "price": null }]
    }
  ]
}
```

API key material never appears. `UpsertProviderRequest.apiKey` is write-only.

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

### `ExperimentSummary`

```json
{
  "id": "string",
  "status": "draft" | "active" | "paused" | "complete" | "archived",
  "hasLedger": true,
  "coverageFraction": 0.42,
  "model": "string | null",
  "updatedAt": "ISO-8601"
}
```

### `ExperimentRunProjection`

Extends `CostProjection` with missing-cell counts (from adapter, not Java):

```json
{
  "projectionText": "string",
  "exitCode": 1,
  "stderrNames": [],
  "missingCells": 1200,
  "voidedCells": 3,
  "slice": "smoke | null",
  "armsScheduled": ["A1", "A2"]
}
```

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
| `experiment read DIR` | results dir with `experiment.yaml` | `schemas/experiment-read.json` |
| `experiment coverage DIR` | optional `--slice ID` | `schemas/experiment-coverage.json` (T6.3) |
| `experiment missing DIR` | optional `--slice ID` | `schemas/experiment-missing.json` (T6.3) |
| `experiment snapshot DIR` | writes `reports/*.json` | `schemas/experiment-read.json` envelope |
| `generate-status DIR` | generate workspace | `schemas/generate-status.json` |
| `generate-manifest DIR` | complete workspace only | `schemas/generate-manifest.json` |

Exit codes: `0` ok, `2` usage/IO, `40` version mismatch or import failure. Always JSON on stdout on success; errors as one line on stderr.

---

## Data paths

All mutable state under `/data` (compose volume). Resolve artifact paths with
`Path.normalize` against `results/<runId>/artifacts/` and reject escapes.

Artifact cache key: ledger row count (re-render when it grows).

### Experiment sidecar (S6)

Ledger path is unchanged — **no** `/data/experiments/` tree:

```
/data/results/<id>/
  experiment.yaml          optional; see docs/experiment-schema.md
  manifest.json            written by harness run (unchanged)
  results.jsonl            append-only ledger (unchanged)
  traces/
  artifacts/
  reports/                 optional dated snapshots
```

A directory without `experiment.yaml` is a plain run (today's behaviour). The UI
may show `hasExperiment: false` on `RunSummary` when the sidecar is absent.

### Generate workspace (G)

```
/data/generate/<jobId>/
  generate.config.yaml
  status.json
  manifest.json
  errors.json
  spec/
  materials/
  examples/
  pack/
```

See [`plan-openapi-to-experiment.md`](./plan-openapi-to-experiment.md).

---

## Generate DTOs (G — frozen; Java G4)

### `StartGenerateRequest`

```json
{
  "jobId": "string",
  "targetId": "string",
  "staging": {
    "baseUrlEnv": "TARGET_BASE_URL",
    "authEnv": "string | null",
    "seed": 42,
    "baseUrl": "string | null",
    "authToken": "string | null"
  },
  "phases": {
    "analyze": true,
    "materials": true,
    "fixtures": true,
    "pack": true,
    "enrich": false
  },
  "approveEnrich": false,
  "mcpGateway": false,
  "useLocalMock": false,
  "mcpUrl": null
}
```

`approveEnrich` must be `true` when `phases.enrich` is enabled (LLM or heuristic via API).
`mcpGateway: true` keeps A/B materials presets; `false` (default) emits Z0/C1/D1 only for field HTTP.
`useLocalMock: true` starts `harness mock serve`, injects `TARGET_BASE_URL`, sets gateway + `mcp_url`.
`mcpUrl` (optional): customer MCP URL → pack `api.mcp.url` when not using local mock; implies gateway.

### `GenerateJob`

```json
{
  "jobId": "string",
  "status": "accepted | running | complete | failed",
  "workspace": "generate/<jobId>"
}
```

### `GenerateProgress`

```json
{
  "job": { "jobId": "string", "status": "string" },
  "terminal": true,
  "status": {
    "job_id": "string",
    "phase": "analyze | fixtures | pack | complete | failed",
    "phases_done": ["analyze"],
    "message": "string",
    "fraction": 0.55
  },
  "error": null
}
```

Adapter shape: `generate-status` envelope (`harness_version`, `terminal`, `status`, `error`).

### `GenerateManifest`

```json
{
  "job_id": "string",
  "pack_path": "pack/pack.yaml",
  "pack_id": "string",
  "graded_tasks": 24,
  "fixture_count": 18,
  "arms_probe": ["Z0", "A1"],
  "validation": "unvalidated"
}
```

Adapter wraps as `{ "harness_version", "manifest": { … } }`.

---

## Capability constants (Java)

```java
public final class Capabilities {
  public static final String UPLOAD_CONTRACT = "upload_contract";
  public static final String LIST_TARGETS = "list_targets";
  public static final String LINT_TARGET = "lint_target";
  public static final String DRAFT_PACK = "draft_pack";
  public static final String LIST_PACKS = "list_packs";
  public static final String READ_PACK = "read_pack";
  public static final String WRITE_PACK = "write_pack";
  public static final String VALIDATE_PACK = "validate_pack";
  public static final String PROJECT_RUN_COST = "project_run_cost";
  public static final String START_RUN = "start_run";
  public static final String GET_RUN_PROGRESS = "get_run_progress";
  public static final String LIST_RUNS = "list_runs";
  public static final String GET_REPORT = "get_report";
  public static final String GET_ANALYSIS = "get_analysis";
  public static final String GET_TRANSCRIPT = "get_transcript";
  public static final String COMPARE_RUNS = "compare_runs";
  public static final String GET_BRIEF = "get_brief";
  public static final String LIST_ARTIFACTS = "list_artifacts";
  public static final String GET_ARTIFACT = "get_artifact";
  public static final String PUT_ARTIFACT = "put_artifact";
  // S6 — experiment sidecar (T6.x)
  public static final String CREATE_EXPERIMENT = "create_experiment";
  public static final String LIST_EXPERIMENTS = "list_experiments";
  public static final String GET_EXPERIMENT = "get_experiment";
  public static final String UPDATE_EXPERIMENT = "update_experiment";
  public static final String ADD_EXPERIMENT_ARMS = "add_experiment_arms";
  public static final String PROJECT_EXPERIMENT_RUN = "project_experiment_run";
  public static final String START_EXPERIMENT_RUN = "start_experiment_run";
  public static final String GET_EXPERIMENT_COVERAGE = "get_experiment_coverage";
  public static final String LIST_EXPERIMENT_REPORTS = "list_experiment_reports";
  public static final String SNAPSHOT_EXPERIMENT_REPORT = "snapshot_experiment_report";
  // G — generate onboarding (G4; constants frozen in contracts.md)
  public static final String START_GENERATE = "start_generate";
  public static final String GET_GENERATE_PROGRESS = "get_generate_progress";
  public static final String GET_GENERATE_MANIFEST = "get_generate_manifest";
  public static final String LIST_GENERATE_ARTIFACTS = "list_generate_artifacts";
  public static final String GET_GENERATE_ARTIFACT = "get_generate_artifact";
  public static final String CREATE_EXPERIMENT_FROM_GENERATE = "create_experiment_from_generate";
  public static final String GET_LLM_CONFIG = "get_llm_config";
  public static final String UPSERT_PROVIDER = "upsert_provider";
  public static final String DELETE_PROVIDER = "delete_provider";
  public static final String UPSERT_MODEL = "upsert_model";
  public static final String DELETE_MODEL = "delete_model";

  private Capabilities() {}
}
```
