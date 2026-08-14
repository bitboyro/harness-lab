#!/usr/bin/env bash
# G6.3 — upload → generate → create experiment (gold-free; no model spend).
# Requires API on API_BASE and a reachable staging URL (default: local-demo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
API="${API_BASE:-http://127.0.0.1:8085}"
OPENAPI="${OPENAPI_SPEC:-$ROOT/harness-ui/examples/openapi-samples/local-demo.yaml}"
STAGING="${TARGET_BASE_URL:-http://127.0.0.1:8765}"
TS="$(date +%s)"
JOB_ID="e2e-gen-${TS}"
EXP_ID="e2e-gen-exp-${TS}"

log() { printf '%s\n' "$*"; }
die() { log "FAIL: $*"; exit 1; }

log "==> generate E2E @ $API"
log "    openapi=$OPENAPI staging=$STAGING job=$JOB_ID"

[[ -f "$OPENAPI" ]] || die "missing OpenAPI sample $OPENAPI"

if ! curl -sf -o /dev/null --max-time 2 "$STAGING/" \
  && ! curl -sf -o /dev/null --max-time 2 "$STAGING/health"; then
  die "staging not reachable at $STAGING (start local-demo-server.py)"
fi

UPLOAD=$(curl -sS -X POST "$API/api/v1/targets" -F "file=@${OPENAPI}")
TARGET_ID=$(printf '%s' "$UPLOAD" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
log "  target=$TARGET_ID"

BODY=$(TARGET_ID="$TARGET_ID" JOB_ID="$JOB_ID" STAGING="$STAGING" python3 - <<'PY'
import json, os
print(json.dumps({
  "jobId": os.environ["JOB_ID"],
  "targetId": os.environ["TARGET_ID"],
  "staging": {
    "baseUrlEnv": "TARGET_BASE_URL",
    "authEnv": None,
    "seed": 42,
    "baseUrl": os.environ["STAGING"],
  },
  "phases": {
    "analyze": True,
    "materials": True,
    "fixtures": True,
    "pack": True,
    "enrich": False,
  },
  "mcpGateway": False,
}))
PY
)

HTTP=$(curl -sS -o /tmp/gen-start.json -w "%{http_code}" -X POST "$API/api/v1/generate" \
  -H 'Content-Type: application/json' \
  -d "$BODY")
[[ "$HTTP" == "202" ]] || die "start generate expected 202 got $HTTP: $(cat /tmp/gen-start.json)"
log "  start generate OK"

STATUS="running"
PROG=""
for _ in $(seq 1 90); do
  PROG=$(curl -sS "$API/api/v1/generate/${JOB_ID}/progress")
  STATUS=$(printf '%s' "$PROG" | python3 -c "import json,sys; print(json.load(sys.stdin)['job']['status'])")
  TERM=$(printf '%s' "$PROG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('terminal'))")
  if [[ "$TERM" == "True" || "$STATUS" == "complete" || "$STATUS" == "failed" ]]; then
    break
  fi
  sleep 1
done

[[ "$STATUS" == "complete" ]] || die "generate not complete: $PROG"

curl -sS "$API/api/v1/generate/${JOB_ID}/manifest" -o /tmp/gen-manifest.json
python3 - <<'PY'
import json
m = json.load(open("/tmp/gen-manifest.json"))
assert m.get("pack_id"), m
assert m.get("graded_tasks", 0) >= 1, m
arms = m.get("arms_probe") or []
assert "Z0" in arms, m
assert "A1" not in arms, m  # mcp_gateway false
print("  manifest graded_tasks=", m.get("graded_tasks"), "arms=", arms)
PY

HTTP=$(curl -sS -o /tmp/gen-exp.json -w "%{http_code}" -X POST \
  "$API/api/v1/generate/${JOB_ID}/experiment" \
  -H 'Content-Type: application/json' \
  -d "{\"experimentId\":\"${EXP_ID}\"}")
[[ "$HTTP" == "201" ]] || die "create experiment expected 201 got $HTTP: $(cat /tmp/gen-exp.json)"
log "  experiment $EXP_ID created"

curl -sS "$API/api/v1/experiments/${EXP_ID}/coverage" | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('  coverage keys', sorted(d.keys())[:8])"
log "OK generate E2E"
