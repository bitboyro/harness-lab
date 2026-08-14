# Plan: OpenAPI → experiment in a few clicks

**Status:** Implementation plan — additive to [contracts.md](./contracts.md) and
[experiment-schema.md](./experiment-schema.md).

**Goal:** A customer uploads an OpenAPI document, connects staging, clicks through
a short wizard, and ends with a packaging benchmark (materials + default arms +
graded task pack + report) — without hand-authoring YAML or knowing the CLI.

**Architecture principle:** The harness CLI executes and writes files. The Java API
subprocesses the CLI and reads outputs via `harness_json.py` and workspace
artifacts. The UI never parses CLI stdout for structure.

---

## What exists today

| Step | Status |
|---|---|
| Upload OpenAPI target | Done — `POST /api/v1/targets` |
| Lint (free) | Done — adapter `lint` |
| Draft stub pack | Done — `harness scaffold` via `draft_pack` |
| Pack edit + validate | Done |
| Run project / start / progress | Done — probe/smoke/full |
| Report + transcript + artifacts | Done |
| Experiment sidecar + wizard | Done — plan import, coverage, slices |
| **Generate workspace + analyze + materials** | Done — `harness generate {analyze,materials,run}` |
| **Generate job status / manifest JSON** | Done — adapter `generate-status`, `generate-manifest` |
| **Fixture capture + graded pack** | Done — `harness generate {fixtures,pack}` (G2) |
| **Agentic enrich + authored skill** | Built (G3) — heuristic + optional LLM; UI approve gate |
| **One-click OpenAPI → experiment (REST/UI)** | Done — G4 API + G5 wizard |

---

## Target user journey (five clicks)

Assumes login/auth is handled by the hosting product (out of scope for harness-ui
v1; loopback deploy is enough for now).

```mermaid
flowchart LR
  A[1 Upload OpenAPI] --> B[2 Lint + gaps]
  B --> C[3 Generate]
  C --> D[4 Approve cost]
  D --> E[5 Run probe]
  E --> F[Report + optional full matrix]
```

| Click | UI | Backend | CLI / disk |
|---|---|---|---|
| **1** Upload | `/onboarding/upload` or targets | `upload_contract` → `/data/targets/<id>/` | stores spec file |
| **2** Review | Lint findings + doc-gap summary | `lint_target` | adapter JSON |
| **3** Generate | Staging URL + auth env names + seed; toggle enrich | `start_generate` → workspace | `harness generate run <config> --yes` |
| **4** Approve | Cost projection for probe run | `project_experiment_run` or `project_run_cost` | dry-run exit 1 |
| **5** Run | Progress bar → report | `start_experiment_run` with generated pack | `harness run --probe --yes` |

**Optional sixth step:** “Run full matrix” reuses the same experiment sidecar with
more presets / repeats — existing experiment flow.

### Wizard outputs (what the user gets)

After click 3 completes:

- **Materials bundle** — MCP tools, generated + authored skills, curl docs, code tree
- **Default arms** — `arms.json` (probe: `Z0 A1 A2 B1 B1-auth C1 D1`)
- **Task pack** — scaffold + oracle grades where staging allowed capture
- **Examples corpus** — `examples/*.{json,xml,...}` from seeded API execution
- **Enriched OpenAPI** — spec with descriptions/examples patched in

After click 5:

- **Probe report** — lift over Z0, per-arm success, cost decomposition
- **Traces** — every call/response (existing `traces/*.json.gz`)
- **Experiment sidecar** — optional auto-created beside results for “continue matrix”

---

## End-to-end system diagram

```mermaid
flowchart TB
  subgraph ui [Next.js]
    W[Wizard]
    EXP[Experiment detail]
    ART[Artifact viewers]
  end

  subgraph be [Spring API]
    GS[GenerateService]
    ES[ExperimentService]
    RS[RunService]
    ADP[AdapterService]
    JR[JobRegistry]
  end

  subgraph disk [/data]
    TW["targets/<id>/"]
    GW["generate/<jobId>/"]
    RW["results/<expId>/"]
  end

  subgraph cli [harness CLI]
    GEN["generate run"]
    RUN[run]
  end

  subgraph adapter [harness_json.py]
    JSON[read serializers]
  end

  W --> GS
  W --> ES
  GS -->|subprocess| GEN
  GEN --> GW
  RS -->|subprocess| RUN
  RUN --> RW
  GS --> ADP
  RS --> ADP
  ADP --> JSON
  JSON --> GW
  JSON --> RW
  EXP --> ES
  ART --> RW
  ART --> GW
  JR --> GS
  JR --> RS
```

---

## Generate pipeline (engine)

Single config drives all phases. Lives on **main** (`src/harness/`), not only
harness-ui.

### Config: `generate.config.yaml`

```yaml
schema_version: 1
job_id: string
target:
  spec: ./spec/original.openapi.yaml
  base_url_env: TARGET_BASE_URL          # staging; required for fixtures + pack
  seed: 42                               # when API is harness-controlled or resettable
  auth:
    type: bearer | header | none
    env: TOKEN_ENV
phases:
  analyze: true                          # lint — always free
  enrich:                                # agentic — costs $
    model: gpt-5.6-luna
    max_usd: 2.0
  fixtures: true                         # execute reads → examples/
  materials:                             # mechanical from enriched spec
    doc_budget: standard
    presets: [Z0, A1, A2, B1, B1-auth, C1, D1]
  pack:
    min_graded_tasks: 20
    unanswerable_share: 0.15
output:
  dir: .                                 # workspace root
pack:
  id: string                             # links to field task pack
  report_class: field
```

### Phases (order fixed)

| Phase | Input | Output | LLM? |
|---|---|---|---|
| `analyze` | raw spec | lint embedded in `status.json`; optional `analyze.json` | No |
| `enrich` | spec + lint gaps | `spec/enriched.openapi.yaml`, `skills/authored.md`, `doc_gaps.md`, `spec/enrichment.patch.yaml` | Yes |
| `fixtures` | enriched spec + staging | `examples/**`, `examples/manifest.yaml` | No |
| `materials` | enriched spec | `materials/**`, `materials/arms.json` | No |
| `pack` | fixtures + scaffold | `pack/pack.yaml`, `pack/oracle/*.json` | Yes (prompts only; grades from oracle) |

**Rule:** Agents write prose; machines write numbers. `grade.expect` values come
only from fixture/oracle capture, never from the LLM.

### CLI commands (main repo)

```bash
harness generate run <config.yaml> [--yes]
harness generate analyze <spec> -o <dir>
harness generate enrich <config.yaml> -o <dir> [--yes]
harness generate fixtures <config.yaml> -o <dir>
harness generate materials <enriched-spec> -o <dir>
harness generate pack <config.yaml> -o <dir> [--yes]
```

Each command updates `status.json` in the output directory.

---

## Workspace contract (generate job)

BE creates the directory; CLI owns contents.

```
/data/generate/<jobId>/
  generate.config.yaml      # BE writes before spawn
  status.json               # CLI updates — UI polls via adapter
  manifest.json             # CLI writes on success — artifact index
  errors.json               # CLI writes on failure — structured
  console.log               # BE captures subprocess stdout+stderr

  spec/
    original.openapi.yaml   # copied from target upload
    enriched.openapi.yaml
    enrichment.patch.yaml

  materials/
    tools.json
    skills/generated.md
    skills/authored.md
    docs/curl.md
    code/
    arms.json

  examples/
    manifest.yaml           # operation → file, content-type, seed
    **/*.{json,xml,...}

  pack/
    pack.yaml
    oracle/                 # per-task captured calls/responses

  doc_gaps.md               # human-readable enrich report
```

### `status.json` (polled while running)

```json
{
  "job_id": "gen-abc",
  "phase": "fixtures",
  "phases_done": ["analyze", "enrich"],
  "message": "Capturing GET /orders",
  "fraction": 0.55,
  "started_at": "2026-08-13T10:00:00Z",
  "updated_at": "2026-08-13T10:02:00Z",
  "cost_usd_so_far": 0.38
}
```

Terminal: `phase` is `complete` or `failed`.

### `manifest.json` (read when complete)

```json
{
  "job_id": "gen-abc",
  "target_id": "media-api",
  "harness_version": "0.0.1",
  "enriched_spec": "spec/enriched.openapi.yaml",
  "materials_dir": "materials",
  "pack_path": "pack/pack.yaml",
  "pack_id": "media-api-probe",
  "arms_probe": ["Z0", "A1", "A2", "B1", "B1-auth", "C1", "D1"],
  "graded_tasks": 24,
  "fixture_count": 18,
  "validation": "unvalidated",
  "provenance": {
    "enrich_model": "gpt-5.6-luna",
    "seed": 42
  }
}
```

### `errors.json` (on failure)

```json
{
  "exit_code": 2,
  "kind": "validation",
  "phase": "pack",
  "message": "only 3 graded tasks; min_graded_tasks is 20",
  "operator_fix": "Check staging URL and seed reset, or lower min_graded_tasks",
  "details": { "graded": 3, "required": 20 }
}
```

---

## Adapter extensions (harness-ui/adapter)

Add subcommands — stdout is always one JSON object; stderr is diagnostic only.

| Subcommand | Args | Returns |
|---|---|---|
| `generate-status` | `<workspaceDir>` | `status.json` contents + `terminal: bool` |
| `generate-manifest` | `<workspaceDir>` | `manifest.json` or error if incomplete |
| `generate-lint` | `<workspaceDir>` | lint on enriched spec if present, else original |

Contract tests + JSON schemas under `adapter/schemas/` (same pattern as T1.x).

Optional later: `fixtures-list`, `oracle-read` — or serve raw files via artifact
API without adapter.

---

## REST capabilities (additive to contracts.md)

New stream **G** — does not change existing run/experiment endpoints.

| Constant | HTTP | Body | Success |
|---|---|---|---|
| `start_generate` | `POST /api/v1/generate` | `{ "jobId", "targetId", "staging": { "baseUrlEnv", "authEnv?", "seed?" }, "phases?", "approveEnrich?" }` | `202` → `GenerateJob` |
| `get_generate_progress` | `GET /api/v1/generate/{jobId}/progress` | — | `200` → `{ job, status, terminal }` |
| `get_generate_manifest` | `GET /api/v1/generate/{jobId}/manifest` | — | `200` → manifest JSON |
| `list_generate_artifacts` | `GET /api/v1/generate/{jobId}/artifacts` | — | `200` → `ArtifactRef[]` |
| `get_generate_artifact` | `GET /api/v1/generate/{jobId}/artifacts/{name}` | — | file + CSP |
| `create_experiment_from_generate` | `POST /api/v1/generate/{jobId}/experiment` | `{ "experimentId", "planOverrides?" }` | `201` → `ExperimentRef` |

`create_experiment_from_generate` copies `pack/pack.yaml` → `/data/packs/`,
writes `experiment.yaml` with probe presets from `arms.json`, points
`run_plan.tasks` at the generated pack, sets `report_class: field`.

---

## OpenAPI → experiment wizard (UI)

New route: **`/experiments/new/from-openapi/`** (or extend `/experiments/new/`).

### Steps

1. **Upload** — reuse targets upload; return `targetId`.
2. **Lint** — show findings; CTA “Generate benchmark materials”.
3. **Configure staging** — base URL (stored as env name + value in server-side
   secrets file, never in pack YAML), optional seed/reset URL, enrich toggle +
   cost cap.
4. **Generate** — poll `get_generate_progress`; show phase + fraction; on
   complete show manifest summary (graded task count, arms list).
5. **Create experiment** — one button: `create_experiment_from_generate` +
   auto-open experiment detail.
6. **Probe run** — reuse existing projection → approve → progress from
   experiment detail (T3.4 / T6.9).

Gate: if `graded_tasks < min_graded_tasks`, show blocking panel with oracle
errors — allow “run gold-free probe anyway” only with explicit ack
(assertion-free metrics).

---

## MCP / HTTP proxy (when API is yours)

For arms `A1`/`A2`/`B1` against a customer HTTP API (not live MCP), the platform
must host an **MCP gateway** generated from enriched OpenAPI:

- `tools/list` from `materials/tools.json`
- `tools/call` → forward to `TARGET_BASE_URL` with customer auth

This is **platform infrastructure** (separate service or sidecar container), not
a harness CLI subcommand. v1 shortcut: run **C1 + D1 + Z0 only** if MCP proxy is
not ready; UI disables A/B arms with explanation.

When the API is the **in-process catalog rig**, no proxy — existing experiment
path unchanged.

---

## Implementation phases

### Phase 0 — Contract freeze (1–2 days)

- [x] G0.1 — This document reviewed; add G-row stubs to `TASKS.md`
- [x] G0.2 — `adapter/schemas/generate-status.json`, `generate-manifest.json`
- [x] G0.3 — Extend `contracts.md` with G capabilities + DTOs
- [x] G0.4 — Extend `web/src/lib/types.ts` mirrors

### Phase 1 — Workspace + status (engine, ~3–5 days)

**Repo:** `harness-lab` main (`src/harness/`)

- [x] G1.1 — `harness/generate_workspace.py` — write/read `status.json`, `errors.json`, atomic replace
- [x] G1.2 — `harness generate analyze` — lint → workspace
- [x] G1.3 — `harness generate materials` — mechanical bundle from spec (reuse `engine/generate.py`)
- [x] G1.4 — pytest: status transitions, materials tree shape

**Repo:** harness-ui adapter

- [x] G1.5 — `generate-status`, `generate-manifest` adapter stubs (manifest empty until G2)

**Verify:** `harness generate analyze examples/openapi.json -o /tmp/g1` + adapter returns JSON.

### Phase 2 — Fixtures + examples (engine, ~4–6 days)

- [x] G2.1 — `harness generate fixtures` — call staging reads, save bodies by content-type
- [x] G2.2 — inject examples into enriched OpenAPI (`spec/enriched.openapi.yaml`)
- [x] G2.3 — `harness generate pack` — scaffold + oracle jsonpath grades from fixtures
- [x] G2.4 — pytest with mock HTTP server

**Verify:** fixture capture against local catalog HTTP port; pack validates with `pack-validate`.

### Phase 3 — Agentic enrich (engine, ~5–7 days)

- [x] G3.1 — `harness/enrich.py` — LLM patch + authored skill (uses `openai` extra)
- [x] G3.2 — `harness generate enrich` + `harness generate run` orchestrator
- [x] G3.3 — Cost projection + `--yes` gate for enrich spend
- [x] G3.4 — `doc_gaps.md` report
- [x] G3.5 — Prompt-fill for task questions (grades still from oracle)

**Verify:** thin spec in → enriched spec with descriptions + authored skill on disk.

### Phase 4 — Backend generate service (~4–5 days)

**Repo:** harness-ui `api/`

- [x] G4.1 — `GenerateService` — create workspace, write config, spawn CLI, `JobRegistry` reuse
- [x] G4.2 — `GenerateController` — REST endpoints G0.3
- [x] G4.3 — `create_experiment_from_generate` — pack copy + experiment.yaml template
- [x] G4.4 — Artifact routes for `/data/generate/<id>/`
- [x] G4.5 — Map `errors.json` → HTTP 400/503 via `ExitCodeMapper`

**Verify:** `curl` start generate → poll progress → manifest 201.

### Phase 5 — UI wizard (~5–7 days)

**Repo:** harness-ui `web/`

- [x] G5.1 — `/experiments/new/from-openapi/` stepper component
- [x] G5.2 — Lint panel (reuse targets lint)
- [x] G5.3 — Staging form + generate progress
- [x] G5.4 — Materials/examples artifact preview (JSON + XML viewers)
- [x] G5.5 — “Create experiment & run probe” CTA → existing experiment run flow
- [x] G5.6 — Home page CTA replaces plan-path-only wizard prominence

**Verify:** mock API off; full path against loopback compose.

### Phase 6 — Hardening (~3–5 days)

- [x] G6.1 — MCP gateway spike OR document C1/D1-only mode for field HTTP APIs (`docs/mcp-gateway.md`, `scripts/mcp-gateway-spike.sh`, engine/UI gate)
- [x] G6.2 — Secrets: staging tokens in `/data/secrets/`, env injection for subprocess only
- [x] G6.3 — E2E test: upload → generate → probe → report JSON shapes (`scripts/e2e-generate.sh`)
- [x] G6.4 — Docker compose: `HARNESS_DATA` / generate+secrets volume mounts
- [ ] G6.5 — Pin bump + adapter version assert (assert path live at 0.0.1; bump when releasing wheel)

---

## Task board rows (add to TASKS.md)

| ID | Task | Stream | Deps | Paths | Verify |
|---|---|---|---|---|---|
| G0.1 | Freeze generate plan + contracts | G0 | — | `docs/plan-*.md`, `contracts.md` | Review |
| G1.1 | Generate workspace I/O | G1 | G0.1 | `src/harness/generate_*.py` | pytest |
| G1.2 | `generate analyze` + `materials` | G1 | G1.1 | `src/harness/cli.py` | CLI |
| G1.5 | Adapter generate-status/manifest | G1 | G0.2 | `adapter/` | contract test |
| G2.1 | Fixtures + pack oracle | G2 | G1.2 | `src/harness/` | pytest + pack-validate |
| G3.1 | Enrich + `generate run` | G3 | G2.1 | `src/harness/enrich.py` | cost gate |
| G4.1 | GenerateService + REST | G4 | G1.5, G3.1 | `api/` | curl e2e |
| G5.1 | OpenAPI wizard UI | G5 | G4.1 | `web/` | manual + build |
| G6.1 | MCP gateway or arm gating | G6 | G5.1 | infra doc | probe A1 or UI gate |

**Stream G engine tasks (G1–G3) modify `src/harness/` on main** — coordinate pin
bump with harness-ui `expect-version` when releasing.

---

## Non-goals (v1)

- User authentication / multi-tenant billing (host product wraps harness-ui)
- Reimplementing Schemathesis
- Pooling field results with controlled rig
- Full 40-core research matrix as default (probe preset only; full matrix opt-in)
- CLI embedded HTTP server

---

## Success criteria

1. Upload OpenAPI → lint visible in **&lt; 5 s** without spend.
2. Generate (with staging + seed) → materials + pack with **≥ 20 graded read
   tasks** for a typical CRUD API, or clear `errors.json` explaining why not.
3. One click creates experiment sidecar linked to generated pack.
4. Probe run completes → report shows lift over Z0, validation flag
   `unvalidated`, per-arm cost decomposition.
5. Every failure returns **structured** `errors.json` or adapter error — UI never
   scrapes unstructured stderr for layout.
6. All metrics in UI come from adapter/CLI — Java does not recompute winners.

---

## Related docs

- [contracts.md](./contracts.md) — REST + exit codes
- [experiment-schema.md](./experiment-schema.md) — sidecar beside results
- [TASKS.md](../TASKS.md) — coordination board
- `docs/design-your-test-run.md` (main repo) — task pack schema
- `docs/test-your-api-harness.md` (main repo) — field mode semantics
