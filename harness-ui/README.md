# harness-ui

One container: harness engine (installed wheel) + Spring Boot control API + Next
static PWA. Deliberately a wrapper over the CLI — **never a second implementation
of harness judgment.**

**Now:** experiments (sidecar), From-OpenAPI generate wizard, local mock / customer
MCP URL, secrets under `/data/secrets/`. See [docs/contracts.md](docs/contracts.md),
[docs/mcp-gateway.md](docs/mcp-gateway.md), [docs/experiment-schema.md](docs/experiment-schema.md).

## Layout

```
harness-ui/
  TASKS.md              coordination board
  docs/contracts.md     frozen capability + REST shapes (S0)
  docs/experiment-schema.md   experiment sidecar (S6) — additive to runs
  docs/mcp-gateway.md   local mock + field MCP URL
  examples/             experiment.yaml + OpenAPI samples
  adapter/              Python: harness → JSON (only place touching internals)
  api/                  Spring Boot: REST + MCP + serves SPA
  web/                  Next.js static export
  skill/                authored SKILL.md for the B2 arm
  benchmark/            self-benchmark task pack
  Dockerfile
  docker-compose.yml
```

Workspace (mounted at `/data`):

```
/data/
  targets/<id>/{spec.json | mcp-url.txt, meta.json}
  packs/<id>.yaml
  generate/<jobId>/     OpenAPI onboarding workspace
  secrets/<id>.env      staging / mock URL values (not in packs)
  results/<runId>/
    experiment.yaml     optional sidecar (S6) — same id as run
    manifest.json       unchanged CLI output
    results.jsonl       unchanged ledger
    traces/
    artifacts/
    reports/            optional dated snapshots (experiment)
  compare/<compareId>/artifacts/
  jobs/<runId>/{job.json, console.log}
```

Plain runs without `experiment.yaml` behave exactly as before. See
[docs/experiment-schema.md](docs/experiment-schema.md).

## Hard constraints

- Prefer not to invent harness judgment in Java/UI — subprocess CLI + adapter JSON.
- Image installs the real release wheel via `install.py --download --tag=vX.Y.Z`
  (still pinned `v0.0.1` until the next wheel; generate/mock need a matching pin).
- Loopback-bound (`127.0.0.1:8085`). No auth, no reverse proxy.

## Local (dev)

```bash
# API + static UI (after web build + sync-web-static.sh)
./harness-ui/scripts/dev-start.sh   # if present; else spring-boot:run on :8085

python3 harness-ui/adapter/harness_json.py report results/auth-smoke | python3 -m json.tool | head
```

### Docker (S4)

Build context is the **repo root**. Pinned wheel: `HARNESS_VERSION` defaults to
`v0.0.1`.

```bash
docker build -f harness-ui/Dockerfile --build-arg HARNESS_VERSION=v0.0.1 -t harness-ui .
cd harness-ui && docker compose up --build
```

```bash
./harness-ui/scripts/smoke-doctor.sh
```

## Safety

- Port published on `127.0.0.1` only.
- D arms require an explicit config opt-in.
- Staging secrets never written into pack YAML.
- Artifacts served under sandbox CSP + path traversal guard.
