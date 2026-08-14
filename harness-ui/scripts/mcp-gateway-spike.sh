#!/usr/bin/env bash
# Outline smoke for a field-HTTP MCP gateway (G6.1).
# Does not start a production gateway — documents the contract and fails
# clearly when prerequisites are missing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SAMPLE="${ROOT}/harness-ui/examples/openapi-samples/local-demo.yaml"
DEMO_URL="${TARGET_BASE_URL:-http://127.0.0.1:8765}"
OUT="${GENERATE_SPIKE_DIR:-/tmp/mcp-gateway-spike}"

echo "== MCP gateway spike =="
echo "sample:  $SAMPLE"
echo "base:    $DEMO_URL"
echo "out:     $OUT"
echo

if [[ ! -f "$SAMPLE" ]]; then
  echo "missing OpenAPI sample: $SAMPLE" >&2
  exit 1
fi

if ! command -v curl >/dev/null; then
  echo "curl required" >&2
  exit 1
fi

if ! curl -sf -o /dev/null --max-time 2 "$DEMO_URL/health" \
  && ! curl -sf -o /dev/null --max-time 2 "$DEMO_URL/"; then
  echo "demo API not reachable at $DEMO_URL" >&2
  echo "start: python harness-ui/examples/openapi-samples/local-demo-server.py" >&2
  exit 2
fi

mkdir -p "$OUT"
HARNESS="${ROOT}/.venv/bin/harness"
if [[ ! -x "$HARNESS" ]]; then
  HARNESS="harness"
fi

cat >"$OUT/generate.config.yaml" <<EOF
schema_version: 1
job_id: mcp-gateway-spike
mcp_gateway: false
target:
  spec: $SAMPLE
  id: local-demo
  base_url_env: TARGET_BASE_URL
  seed: 42
phases:
  analyze: true
  enrich: false
  materials:
    doc_budget: standard
    presets: [Z0, A1, A2, C1, D1]
  fixtures: false
  pack: false
output:
  dir: .
EOF

export TARGET_BASE_URL="$DEMO_URL"
echo "Running generate (mcp_gateway=false → A* presets must be dropped)…"
(cd "$OUT" && "$HARNESS" generate run generate.config.yaml --yes)

ARMS="$OUT/materials/arms.json"
if [[ ! -f "$ARMS" ]]; then
  echo "expected materials/arms.json" >&2
  exit 3
fi

if grep -E '"A[0-9]' "$ARMS" >/dev/null 2>&1; then
  echo "FAIL: A-arms present while mcp_gateway=false" >&2
  exit 4
fi
echo "OK: A/B arms gated out under mcp_gateway=false"

TOOLS="$OUT/materials/tools.json"
if [[ -f "$TOOLS" ]]; then
  echo "tools.json present — a real gateway would serve tools/list from this file"
  echo "and forward tools/call to $DEMO_URL (see harness-ui/docs/mcp-gateway.md)."
else
  echo "note: tools.json missing (materials may omit tools when only C1/D1/Z0)"
fi

echo
echo "Spike complete. Next: deploy a sidecar that loads tools.json + TARGET_* env."
