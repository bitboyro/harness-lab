# MCP gateway for field HTTP APIs

Arms **A1 / A2 / B\*** need a live MCP `tools/list` + `tools/call` surface.
The controlled catalog rig already exposes that in-process. A **customer HTTP
API** does not — unless something hosts an **MCP gateway** that wraps the same
OpenAPI the generate pipeline uses.

## Local mock (recommended when you have no staging URL)

From OpenAPI wizard → **Use local mock (no staging URL)** (or
`useLocalMock: true` on `start_generate`):

1. API starts `harness mock serve --spec <uploaded>` — OpenAPI HTTP stub + MCP
   gateway on ephemeral localhost ports.
2. Injects `TARGET_BASE_URL` into `/data/secrets/<jobId>.env`.
3. Writes `mcp_gateway: true` and `mcp_url:` into `generate.config.yaml` so the
   pack gets `api.mcp.url` for A-arms.
4. Sidecars stay alive with the API process so a following probe can call them.

CLI (manual):

```bash
.venv/bin/harness mock serve --spec harness-ui/examples/openapi-samples/local-demo.yaml
# prints: MOCK_READY {"ready":true,"httpUrl":"http://127.0.0.1:…","mcpUrl":"http://127.0.0.1:…/mcp",…}
```

Smoke: `harness-ui/scripts/mock-sidecar-smoke.sh`.

## v1 default without mock: gate A/B arms

Until a gateway is available (local mock or external):

| Flag | Materials presets | Probe arms |
|---|---|---|
| `mcp_gateway: false` (default) | `Z0`, `C1`, `D1` | docs+curl / code-fs / null |
| `mcp_gateway: true` / local mock | also `A1`, `A2`, … | MCP tool-call arms |

Enforcement:

- Engine: `generate_run._gate_presets` drops presets starting with `A`/`B`
  when `mcp_gateway` is false.
- API: `GenerateService.buildConfigYaml` emits the safe preset list and
  `mcp_gateway` / optional `mcp_url` from the request.
- UI: **Use local mock** or **MCP gateway available**.

## What a gateway must do

In-repo implementation: `src/harness/mcp_gateway.py` + `mock_http.py`.

1. Serve MCP over HTTP from the OpenAPI (`tool_defs` / same surface as materials).
2. On `tools/call`, map tool name → OpenAPI operation → `TARGET_BASE_URL`
   (or the stub HTTP base).
3. Forward status / body; surface transport errors as MCP tool errors, not
   infra kills unless the gateway process itself dies.

External gateways: set **MCP URL** in the From OpenAPI staging step (or pass
`mcpUrl` on `start_generate`) with a real staging `TARGET_BASE_URL`, and leave
local mock off. That writes `mcp_gateway: true` + `mcp_url` into
`generate.config.yaml` → pack `api.mcp.url`.

## Secrets (G6.2)

Staging URL/token **values** from the wizard (or the mock HTTP URL) are written
to `/data/secrets/<jobId>.env` and injected into generate / experiment
subprocesses. Config YAML and packs keep env **names** only. Creating an
experiment from a generate job copies that secrets file to the experiment id.

## Controlled rig

In-process catalog experiments are unchanged — no gateway, no A/B gate.
