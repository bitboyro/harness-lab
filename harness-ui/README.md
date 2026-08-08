# harness-ui

One container: harness engine (installed wheel) + Spring Boot control API + Next
static PWA. Deliberately a wrapper over the CLI — **never a second implementation
of harness judgment.**

## Layout

```
harness-ui/
  TASKS.md              coordination board
  docs/contracts.md     frozen capability + REST shapes (S0)
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
  results/<runId>/{results.jsonl, manifest.json, traces/, artifacts/}
  compare/<compareId>/artifacts/
  jobs/<runId>/{job.json, console.log}
```

## Hard constraints

- Nothing under `src/harness/`, `tests/`, `docs/` (repo root), or any existing
  file outside this directory may be modified.
- Image installs the real release wheel via `install.py --download --tag=vX.Y.Z`.
- Loopback-bound (`127.0.0.1:8085`). No auth, no reverse proxy.
- Feature branch only until reviewed — no push, tag, or release.

## Local (dev)

Adapter (needs the repo's venv / installed harness):

```bash
python3 harness-ui/adapter/harness_json.py report results/auth-smoke | python3 -m json.tool | head
```

API / web / image: see stream READMEs once S2–S4 land. Compose:

```bash
cd harness-ui && docker compose up --build
```

## Safety

- Port published on `127.0.0.1` only.
- D arms require an explicit config opt-in.
- `start_run` is in the benchmark pack's `safety.forbidden_calls`.
- Artifacts served under sandbox CSP + path traversal guard.
