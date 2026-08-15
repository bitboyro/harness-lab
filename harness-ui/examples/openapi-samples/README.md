# OpenAPI samples for harness-ui generate / lint experiments

Downloaded locally for offline wizard testing. Prefer medium surfaces first —
giant specs (Trello, PokéAPI) stress context/tool volume more than the happy path.

| File | Title | Paths | Good for |
|---|---|---:|---|
| **`local-demo.yaml`** | Local Demo Catalog | 6 | **Best e2e** — pair with `local-demo-server.py` on :8765 |
| **`museum.yaml`** | Redocly Museum API | 5 | Small clean OAS 3.1 (materials-only without staging) |
| **`petstore-v3.yaml`** | Swagger Petstore 3.0 | 13 | Classic; live staging often flaky |
| **`petstore3.json`** | same (JSON) | 13 | Same as above |
| **`apis-guru.yaml`** | APIs.guru directory | 7 | Tiny meta-API |
| **`httpbin.yaml`** | httpbin.org | 52 | Staging-friendly when httpbin is up |
| **`pokeapi.yaml`** | PokéAPI | 100 | Large read-only catalog |
| **`trello.json`** | Trello REST | 191 | Heavy real-world surface |

## Local e2e (recommended)

```bash
# Option A — wizard "Use local mock" (no separate demo server)
harness-ui/scripts/dev-start.sh
# open /experiments/new/from-openapi/ → upload local-demo.yaml → Use local mock

# Option B — real stub on :8765 (no MCP unless you also run harness mock serve)
.venv/bin/python harness-ui/examples/openapi-samples/local-demo-server.py
export TARGET_BASE_URL=http://127.0.0.1:8765
```

CLI-only mock smoke:

```bash
harness-ui/scripts/mock-sidecar-smoke.sh
```

## Suggested wizard order

1. **local-demo.yaml** — full fixtures → pack → experiment
2. **museum.yaml** — upload → lint → materials (fixtures off if no staging)
3. **petstore-v3.yaml** — only if `https://petstore3.swagger.io/api/v3` is healthy

## Sources

- Local demo: `local-demo.yaml` + `local-demo-server.py` (in this folder)
- Petstore: https://github.com/swagger-api/swagger-petstore
- Museum: https://github.com/Redocly/museum-openapi-example
- httpbin / APIs.guru: https://github.com/APIs-guru/openapi-directory
- PokéAPI: https://github.com/PokeAPI/pokeapi
- Trello: https://developer.atlassian.com/cloud/trello/swagger.v3.json
