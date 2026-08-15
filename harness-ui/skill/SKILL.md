# Working with harness-ui

Authored workflow for the harness-ui control plane at `http://127.0.0.1:8085`.
Mechanical API listings live in `generated-skill.md` and `curl-reference.md` —
regenerate those from `/v3/api-docs`; this file is the part the spec cannot
state.

## What this is

A **wrapper over the harness CLI**, not a second implementation. Spring Boot
never computes success rates, winner, pooling refusals, cost projections, or
pack validity — those come from the Python adapter or a `harness` subprocess.
Treat every number in a report as adapter output.

## Transport choice

| You have | Use |
|---|---|
| MCP client (Cursor, Claude Desktop, harness field mode) | `POST /mcp` JSON-RPC — tool names match REST `operationId`s exactly |
| Shell / curl | REST under `/api/v1/*` — see `curl-reference.md` |
| Browser | Static PWA on the same origin; deep links fall back to `index.html` |

MCP tool names match REST `operationId`s (see `Capabilities` / `contracts.md`).

## Safe command ladder

1. **LLM config** — `get_llm_config`, then `upsert_provider` / `upsert_model`
   for the OpenAI key, optional compatible endpoints, and registered models.
2. **Targets** — `upload_contract` (OpenAPI file or `mcp_url`), then optional
   `lint_target` on OpenAPI targets only.
3. **Packs** — `draft_pack` from a target, edit YAML via `read_pack` /
   `write_pack`, always `validate_pack` before spending.
4. **Projection before spend** — `project_run_cost` or `project_experiment_run`.
   Exit code **1** on the subprocess is the normal dry-run gate, not failure.
5. **Approve explicitly** — `start_run` and `start_experiment_run` require
   `"approve": true`. Without it you get HTTP 400.
6. **Poll** — `get_run_progress` until terminal; then `get_report` or
   `get_brief` (insights skill consumes brief).
7. **Compare** — `compare_runs`. Exit code 3 from the CLI becomes HTTP 200 with
   `refused: true` — read `refusalText`, never pool across the broken boundary.

## Experiment sidecars (S6)

Results dirs may carry `experiment.yaml` beside `manifest.json`. The run id is
the same for `/runs/{id}` and `/experiments/{id}`.

- `create_experiment` writes the sidecar only; the ledger starts on first run.
- `add_experiment_arms` appends presets — **additive resume** schedules missing
  cells only; plain `--resume` on dirs without a sidecar is unchanged.
- `get_experiment_coverage` and adapter `missing` define what a slice run will
  spend on.
- `snapshot_experiment_report` freezes dated JSON under `reports/`.

World-lock rules (shrink cores/difficulty after ledger rows exist) are enforced
by the engine, not Java.

## Safety defaults

- **D presets (`D1`/`D2`)** — pass `allowCodeSandbox: true` on run requests or
  the API returns 400.
- **Artifacts** — `get_artifact` rejects path traversal (`400`). Public embed
  uses `/artifacts/{runId}/**` with restrictive CSP.
- **Loopback only** — bind `127.0.0.1:8085`; no auth layer by design.
- **Self-benchmark** — the benchmark pack lists spend and LLM-config writes
  (`upsert_provider`, `delete_provider`, `upsert_model`, `delete_model`) in
  `forbidden_calls`; attempted spend is the harm signal on this API.

## MCP calling notes

- Base URL: `http://127.0.0.1:8085/mcp`
- Methods: `tools/list`, `tools/call` with `{ "name", "arguments" }`.
- `upload_contract` via MCP: pass `mcp_url` **or** `file_base64` + `filename`
  (REST multipart is unchanged).
- `put_artifact` via MCP: pass `content_base64` or `text` in arguments.

## When results look wrong

- **Empty report** — run still in flight or infra-error rows excluded from rates.
- **Compare refused** — model, MCP revision, skill condition, or report class
  differ; fix the setup, do not average.
- **Pack validate error** — Python `PackError` text is authoritative; Java only
  forwards it.
- **Version mismatch** — adapter asserts `harness.__version__ == "0.0.1"`.

## Data layout (`/data`)

```
targets/<id>/     uploaded contracts
packs/<id>.yaml   task packs
results/<id>/     manifest.json + results.jsonl [+ experiment.yaml]
jobs/<id>/        console.log for spawned runs
config/           providers.json (LLM profiles + registered models)
secrets/          provider keys and generate staging env — never in YAML
```

Pin: harness wheel `v0.0.1` until the image build-arg is bumped.
