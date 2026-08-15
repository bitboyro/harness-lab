# harness-ui coordination board

Branch `feat/harness-ui`. Streams work on `feat/harness-ui-<stream>` and merge
back here. **Nothing outside `harness-ui/` may be modified.**

Rules:

- Claim a row by setting **Status** to `claimed` and putting your name in **Agent**,
  in a commit that touches only that row.
- Stay inside your stream's paths.
- A row is `done` only when its Verify column passes.
- If blocked, set `blocked` and note why in the row; do not silently work around it.

| ID | Task | Stream | Deps | Paths | Verify | Status | Agent |
|---|---|---|---|---|---|---|---|
| T0.1 | Freeze capability list + REST shapes | S0 | — | `harness-ui/TASKS.md`, `docs/contracts.md` | Peer review | done | s0 |
| T0.2 | Freeze adapter JSON schemas | S0 | — | `harness-ui/adapter/schemas/` | Peer review | done | s0 |
| T0.3 | Scaffold dirs, nested `.gitignore`, README | S0 | — | `harness-ui/` | Tree matches layout | done | s0 |
| T1.1 | `harness_json.py report` | S1 | T0.2 | `adapter/` | Runs on `results/auth-smoke` | done | s1 |
| T1.2 | `harness_json.py progress` | S1 | T0.2 | `adapter/` | Runs on `results/auth-smoke` | done | s1 |
| T1.3 | `harness_json.py lint` | S1 | T0.2 | `adapter/` | Runs on `examples/openapi.json` | done | s1 |
| T1.4 | `harness_json.py pack-validate` | S1 | T0.2 | `adapter/` | Good + bad pack both handled | done | s1 |
| T1.5 | Version assertion + contract tests | S1 | T1.1–T1.4 | `adapter/tests/` | Fails loudly on wrong version | done | s1 |
| T2.1 | Maven module, config, loopback bind | S2 | T0.3 | `api/` | `mvnw verify` green | done | s2 |
| T2.2 | `HarnessCli` subprocess + exit-code mapping | S2 | T0.1 | `api/core/` | All 6 exit codes mapped | done | s2 |
| T2.3 | Targets: upload contract, list | S2 | T2.2 | `api/` | `curl -F file=@examples/openapi.json` | done | s2 |
| T2.4 | Lint + pack endpoints (draft/read/write/validate) | S2 | T2.2 | `api/` | Typo returns Python `PackError` text | done | s2 |
| T2.5 | Runs: projection, approval, spawn, JobRegistry | S2 | T2.2 | `api/core/` | Dry-run spends nothing | done | s2 |
| T2.6 | Progress polling + terminal detection | S2 | T2.5 | `api/` | Torn last line survived | done | s2 |
| T2.7 | Artifacts: render-on-demand, sandbox CSP, traversal guard | S2 | T2.2 | `api/` | `../../etc/passwd` rejected | done | s2 |
| T2.8 | Compare endpoint incl. exit-3 refusal payload | S2 | T2.2 | `api/` | Cross-model pair refuses | done | s2 |
| T2.9 | SPA fallback controller | S2 | T2.1 | `api/web/` | Deep link survives refresh | done | s2 |
| T3.1 | Next app, static export, Tailwind, API client | S3 | T0.1 | `web/` | `npm run build` → `out/` | done | s3 |
| T3.2 | Targets + Lint pages | S3 | T3.1 | `web/` | Against stub API | done | s3 |
| T3.3 | Pack editor with live validation | S3 | T3.1 | `web/` | Bad pack shows Python message | done | s3 |
| T3.4 | Run config → projection → approve → progress | S3 | T3.1 | `web/` | Polling stops when terminal | done | s3 |
| T3.5 | Results, artifact viewer iframe, compare page | S3 | T3.1 | `web/` | Sorting works, `window.parent` fails | done | s3 |
| T3.6 | PWA manifest + service worker | S3 | T3.2–T3.5 | `web/public/` | Offline report opens | done | s3 |
| T4.1 | Dockerfile: 3 stages, pinned `--tag` | S4 | T0.3 | `Dockerfile` | `docker build` clean | blocked | s4 — S2+S3 merged; daemon still down — retry `docker build -f harness-ui/Dockerfile --build-arg HARNESS_VERSION=v0.0.1 -t harness-ui .` |
| T4.2 | compose: loopback, env_file, /data volume | S4 | T4.1 | `docker-compose.yml` | `ps` shows `127.0.0.1:8085->` | blocked | s4 — compose config ok; `up` waits on daemon / T4.1 |
| T4.3 | `harness doctor` green inside the image | S4 | T4.1 | `scripts/smoke-doctor.sh` | python, curl, version | blocked | s4 — script added; needs Docker daemon for `docker build` |
| T5.1 | `@Tool` annotations on the same services | S5 | T2.4, T2.5 | `api/mcp/` | `tools/list` returns all | done | s5 |
| T5.2 | Capability parity test | S5 | T5.1 | `api/` | Red build when one removed | done | s5 |
| T5.3 | Authored `SKILL.md` + `authored_commit` | S5 | T5.1 | `skill/` | Committed before T7.1 | done | s5 |
| T5.4 | Generated docs + curl reference from `/v3/api-docs` | S5 | T5.1 | `skill/` | Regenerates identically | done | s5 |
| T7.1 | Self-benchmark pack (`start_run` forbidden) | S7 | T5.3 | `benchmark/` | `pack validate` passes | done | s7 |
| T7.2 | Probe run against dry-run mode | S7 | T7.1 | — | Z0 floor recorded | done | s7 |
| T6.0 | Freeze `experiment.yaml` sidecar schema + layout | S6 | T0.1 | `docs/experiment-schema.md`, `examples/` | Peer review | done | s6 |
| T6.1 | Adapter JSON schema `experiment-read.json` | S6 | T6.0 | `adapter/schemas/` | Validates example envelope | done | s6 |
| T6.2 | Adapter `experiment read DIR` | S6 | T6.1, E1.2 | `adapter/` | JSON on example sidecar path | done | s6 |
| T6.3 | Adapter `experiment coverage` + `missing` + schemas | S6 | T6.2, E1.2 | `adapter/` | Counts match manual cell math | done | s6 |
| T6.4 | Adapter `experiment snapshot DIR` | S6 | T6.2, T1.1 | `adapter/` | Writes `reports/*.json`, updates sidecar | done | s6 |
| T6.5 | Contract tests for experiment adapter | S6 | T6.2–T6.4 | `adapter/tests/` | No sidecar → clear error | done | s6 |
| T6.6 | `ExperimentService` + REST controllers | S6 | T6.2, T2.5 | `api/` | Sidecar CRUD; run uses same `RunJob` | done | s6 |
| T6.7 | `project/start_experiment_run` (missing cells) | S6 | T6.6, E1.3 | `api/` | Add arm → second run schedules gap only | done | s6 |
| T6.8 | Next: `/experiments` list + detail + coverage grid | S6 | T6.6, T3.1 | `web/` | Legacy `/runs/*` still works | done | s6 |
| T6.9 | Next: experiment wizard (plan import) + slice run | S6 | T6.8, T3.4 | `web/` | `baseline-experiment-80` example loads | done | s6 |
| T6.10 | Next: report snapshots timeline | S6 | T6.4, T6.8 | `web/` | Dated picker shows frozen JSON | done | s6 |
| T6.11 | S5 parity: experiment capabilities as `@Tool` | S6 | T5.1, T6.6 | `api/mcp/` | `tools/list` includes S6 constants | done | s6 |
| E1.1 | `ExperimentSidecar` load/save + validation | E1 | T6.0 | `src/harness/engine/` on **main** | Refuses shrink world after rows | done | |
| E1.2 | `missing_cells()` from sidecar + `ResultStore` | E1 | E1.1 | `src/harness/engine/` | Matches schema §missing-cell | done | |
| E1.3 | CLI `harness experiment {init,run,arm}` | E1 | E1.2 | `src/harness/cli.py` | Additive resume on sidecar dirs only | done | |
| E1.4 | pytest: sidecar + additive arm + slice filter | E1 | E1.3 | `tests/` | Plain `--resume` unchanged | done | |

**Streams:** S6 = harness-ui experiment sidecar. E1 = engine on `main` (outside
`harness-ui/` — coordinate before pin bump). S6 adapter tasks block on E1.2 for
coverage/missing; T6.7 blocks on E1.3 for spend.

**Stream G** (OpenAPI → generate → experiment): full plan in
[`docs/plan-openapi-to-experiment.md`](docs/plan-openapi-to-experiment.md).
Engine tasks G1–G3 touch `src/harness/` on **main** — same pin-bump rule as E1.

| ID | Task | Stream | Deps | Paths | Verify | Status | Agent |
|---|---|---|---|---|---|---|---|
| G0.1 | Freeze generate contracts + plan | G0 | — | `docs/plan-openapi-to-experiment.md`, `docs/contracts.md` | Peer review | done | — |
| G0.2 | Adapter schemas `generate-status`, `generate-manifest` | G0 | G0.1 | `adapter/schemas/` | Validates examples | done | — |
| G0.3 | REST capabilities + DTOs in contracts.md | G0 | G0.1 | `docs/contracts.md`, `web/src/lib/types.ts` | Types match | done | — |
| G1.1 | Generate workspace I/O (`status`, `errors`, `manifest`) | G1 | G0.1 | `src/harness/` on main | pytest | done | — |
| G1.2 | CLI `generate analyze` + `generate materials` + `generate run` | G1 | G1.1 | `src/harness/cli.py` | CLI smoke | done | — |
| G1.5 | Adapter `generate-status` + `generate-manifest` | G1 | G0.2, G1.1 | `adapter/` | contract test | done | — |
| G2.1 | Fixtures capture + `generate pack` (oracle grades) | G2 | G1.2 | `src/harness/` on main | pack-validate | done | — |
| G2.2 | Inject fixture examples into enriched OpenAPI | G2 | G2.1 | `generate_fixtures.py` | pytest | done | fixtures before materials |
| G3.1 | Agentic enrich + `generate run` orchestrator | G3 | G2.1 | `src/harness/enrich.py` | cost gate | done | heuristic + mocked LLM; CLI `generate enrich` |
| G3.5 | Prompt-fill (no expect leak) | G3 | G2.1 | `generate_pack.py` | pytest | done | heuristic questions |
| G4.1 | `GenerateService` + REST controller | G4 | G1.5, G3.1 | `api/` | curl e2e | done | REST + MCP parity (34 caps) |
| G4.3 | `create_experiment_from_generate` | G4 | G4.1 | `api/` | sidecar + pack link | done | copies pack → `/data/packs/` |
| G4.5 | `errors.json` → HTTP 400/503 | G4 | G4.1 | `ExitCodeMapper` | unit test | done | |
| G5.1 | UI wizard `/experiments/new/from-openapi/` | G5 | G4.1 | `web/` | build + manual | done | stepper + lint + generate poll |
| G6.1 | MCP gateway spike or A/B arm gating | G6 | G5.1 | infra / UI copy | probe or gate | done | docs + spike script + preset gate |
| G6.2 | Secrets dir + env injection | G6 | G4.1 | `SecretsService` | manual | done | `/data/secrets/<job>.env` |
| G6.3 | Generate E2E script | G6 | G5.1 | `scripts/e2e-generate.sh` | script | done | upload→manifest→experiment |
| G6.4 | Compose `HARNESS_DATA` volume | G6 | G4.1 | `docker-compose.yml` | compose config | done | |
| G6.5 | Pin bump + adapter version assert | G6 | G1–G3 | `__version__` / expect-version | smoke-doctor | todo | assert live; bump on wheel release |
