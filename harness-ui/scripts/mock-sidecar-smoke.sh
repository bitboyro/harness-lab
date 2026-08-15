#!/usr/bin/env bash
# Smoke: OpenAPI HTTP mock + MCP gateway (local mock path).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SAMPLE="${ROOT}/harness-ui/examples/openapi-samples/local-demo.yaml"
HARNESS="${ROOT}/.venv/bin/harness"
[[ -x "$HARNESS" ]] || HARNESS=harness
LOG="$(mktemp -t mock-smoke.XXXXXX)"

echo "== mock sidecar smoke =="
echo "sample: $SAMPLE"

"$HARNESS" mock serve --spec "$SAMPLE" --host 127.0.0.1 >"$LOG" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true; rm -f "$LOG"' EXIT

READY_LINE=""
for _ in $(seq 1 80); do
  if grep -q '^MOCK_READY ' "$LOG" 2>/dev/null; then
    READY_LINE="$(grep '^MOCK_READY ' "$LOG" | head -1)"
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "FAIL: mock process exited" >&2
    cat "$LOG" >&2 || true
    exit 2
  fi
  sleep 0.15
done

if [[ -z "$READY_LINE" ]]; then
  echo "FAIL: no MOCK_READY line" >&2
  cat "$LOG" >&2 || true
  exit 2
fi

JSON="${READY_LINE#MOCK_READY }"
HTTP_URL="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['httpUrl'])" "$JSON")"
MCP_URL="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['mcpUrl'])" "$JSON")"

echo "http: $HTTP_URL"
echo "mcp:  $MCP_URL"

curl -sf "$HTTP_URL/health" >/dev/null
curl -sf "$HTTP_URL/items" >/dev/null

LIST="$(curl -sf -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')"
python3 -c "import json,sys; t=json.load(sys.stdin)['result']['tools']; assert len(t)>=1; print(f'tools/list ok ({len(t)})')" <<<"$LIST"

NAME="$(python3 -c "import json,sys; print(json.load(sys.stdin)['result']['tools'][0]['name'])" <<<"$LIST")"
CALL="$(curl -sf -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"$NAME\",\"arguments\":{}}}")"
python3 -c "import json,sys; r=json.load(sys.stdin)['result']; assert 'content' in r; print('tools/call ok')" <<<"$CALL"

echo "OK: local mock HTTP + MCP gateway"
