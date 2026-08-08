# harness-ui web (S3)

Next.js App Router static export (`output: 'export'` → `out/`). Thin UI over
the control API in `docs/contracts.md`.

## Dev

```bash
cd harness-ui/web
npm ci
NEXT_PUBLIC_API_MOCK=1 npm run dev
```

Mock mode (`NEXT_PUBLIC_API_MOCK=1`) exercises pages without the Java API.

Against a local API:

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8085 npm run dev
```

Default API base is `""` (same-origin), for when Spring serves `out/`.

## Build

```bash
npm run build   # writes out/
```

## Artifact iframe

Viewer pages embed `/artifacts/{runId}/{name}` with
`sandbox="allow-scripts"` and **without** `allow-same-origin`.
