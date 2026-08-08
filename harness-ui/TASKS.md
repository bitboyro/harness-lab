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
| T2.1 | Maven module, config, loopback bind | S2 | T0.3 | `api/` | `mvnw verify` green | todo | |
| T2.2 | `HarnessCli` subprocess + exit-code mapping | S2 | T0.1 | `api/core/` | All 6 exit codes mapped | todo | |
| T2.3 | Targets: upload contract, list | S2 | T2.2 | `api/` | `curl -F file=@examples/openapi.json` | todo | |
| T2.4 | Lint + pack endpoints (draft/read/write/validate) | S2 | T2.2 | `api/` | Typo returns Python `PackError` text | todo | |
| T2.5 | Runs: projection, approval, spawn, JobRegistry | S2 | T2.2 | `api/core/` | Dry-run spends nothing | todo | |
| T2.6 | Progress polling + terminal detection | S2 | T2.5 | `api/` | Torn last line survived | todo | |
| T2.7 | Artifacts: render-on-demand, sandbox CSP, traversal guard | S2 | T2.2 | `api/` | `../../etc/passwd` rejected | todo | |
| T2.8 | Compare endpoint incl. exit-3 refusal payload | S2 | T2.2 | `api/` | Cross-model pair refuses | todo | |
| T2.9 | SPA fallback controller | S2 | T2.1 | `api/web/` | Deep link survives refresh | todo | |
| T3.1 | Next app, static export, Tailwind, API client | S3 | T0.1 | `web/` | `npm run build` → `out/` | todo | |
| T3.2 | Targets + Lint pages | S3 | T3.1 | `web/` | Against stub API | todo | |
| T3.3 | Pack editor with live validation | S3 | T3.1 | `web/` | Bad pack shows Python message | todo | |
| T3.4 | Run config → projection → approve → progress | S3 | T3.1 | `web/` | Polling stops when terminal | todo | |
| T3.5 | Results, artifact viewer iframe, compare page | S3 | T3.1 | `web/` | Sorting works, `window.parent` fails | todo | |
| T3.6 | PWA manifest + service worker | S3 | T3.2–T3.5 | `web/public/` | Offline report opens | todo | |
| T4.1 | Dockerfile: 3 stages, pinned `--tag` | S4 | T0.3 | `Dockerfile` | `docker build` clean | blocked | s4 — files written; full `docker build` needs S2 `api/src` + S3 `web/` (`package-lock.json`, `output: 'export'` → `out/`); daemon also down here |
| T4.2 | compose: loopback, env_file, /data volume | S4 | T4.1 | `docker-compose.yml` | `ps` shows `127.0.0.1:8085->` | blocked | s4 — compose written (`127.0.0.1:8085`, `../.env`, `./harness-data:/data`); `compose config` ok; `up` blocked on T4.1 |
| T4.3 | `harness doctor` green inside the image | S4 | T4.1 | `scripts/smoke-doctor.sh` | python, curl, version | blocked | s4 — `smoke-doctor.sh` builds `--target runtime-base`; Docker daemon not running in this environment |
| T5.1 | `@Tool` annotations on the same services | S5 | T2.4, T2.5 | `api/mcp/` | `tools/list` returns all | todo | |
| T5.2 | Capability parity test | S5 | T5.1 | `api/` | Red build when one removed | todo | |
| T5.3 | Authored `SKILL.md` + `authored_commit` | S5 | T5.1 | `skill/` | Committed before T7.1 | todo | |
| T5.4 | Generated docs + curl reference from `/v3/api-docs` | S5 | T5.1 | `skill/` | Regenerates identically | todo | |
| T7.1 | Self-benchmark pack (`start_run` forbidden) | S7 | T5.3 | `benchmark/` | `pack validate` passes | todo | |
| T7.2 | Probe run against dry-run mode | S7 | T7.1 | — | Z0 floor recorded | todo | |
