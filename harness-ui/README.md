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

### Docker (S4)

Build context is the **repo root** (the image `COPY`s root `install.py`). Compose
sets `context: ..` and `dockerfile: harness-ui/Dockerfile`.

Pinned wheel: `HARNESS_VERSION` build-arg defaults to `v0.0.1`. The runtime
stage always runs `python3 install.py --download --tag=$HARNESS_VERSION` into
`/opt/venv` (PEP 668). Never use bare `--download`.

```bash
# Full image (needs S2 api/ + S3 web/ with package-lock and static export)
docker build -f harness-ui/Dockerfile --build-arg HARNESS_VERSION=v0.0.1 -t harness-ui .

cd harness-ui && docker compose up --build
# publishes 127.0.0.1:8085 only; mounts ./harness-data → /data
# env_file: ../.env  (repo-root credentials, same as the CLI)
```

Harness install smoke without api/web:

```bash
./harness-ui/scripts/smoke-doctor.sh
# docker build --target runtime-base … && harness doctor + version assert
```

## Safety

- Port published on `127.0.0.1` only.
- D arms require an explicit config opt-in.
- `start_run` is in the benchmark pack's `safety.forbidden_calls`.
- Artifacts served under sandbox CSP + path traversal guard.
