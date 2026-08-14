#!/usr/bin/env bash
# Copy Next.js static export into Spring's classpath static/ (local dev).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/harness-ui/web/out"
DEST="$ROOT/harness-ui/api/src/main/resources/static"
if [[ ! -f "$OUT/index.html" ]]; then
  echo "missing $OUT/index.html — run: cd harness-ui/web && npm run build" >&2
  exit 1
fi
# Wipe first: overlay left stale hashed chunks from prior Next builds,
# which the service worker / deep-link fallback can still serve.
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$OUT"/. "$DEST/"
echo "synced $OUT -> $DEST"
