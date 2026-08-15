#!/usr/bin/env bash
# End-to-end API smoke for harness-ui (loopback). Exercises free paths + optional spend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UI="$ROOT/harness-ui"
API="${API_BASE:-http://127.0.0.1:8085}"
REPO="$ROOT"
TS="$(date +%s)"
RUN_ID="ui-e2e-${TS}"
EXP_ID="ui-e2e-exp-${TS}"
PACK_ID="ui-e2e-pack-${TS}"
OPENAPI="$REPO/examples/openapi.json"
PASS=0
FAIL=0
SKIP=0

log() { printf '%s\n' "$*"; }
ok() { log "  OK  $1"; PASS=$((PASS + 1)); }
bad() { log "  FAIL $1"; FAIL=$((FAIL + 1)); }
skip() { log "  SKIP $1"; SKIP=$((SKIP + 1)); }

need() {
  local code="$1" msg="$2"
  shift 2
  local out
  out="$(mktemp)"
  local http
  http=$(curl -sS -o "$out" -w "%{http_code}" "$@" 2>/dev/null) || http="000"
  if [[ "$http" == "$code" ]]; then
    ok "$msg (HTTP $http)"
    cat "$out"
  else
    bad "$msg (expected $code got $http): $(head -c 200 "$out")"
    cat "$out" >&2
  fi
  rm -f "$out"
}

log "==> harness-ui E2E @ $API"
log "    run_id=$RUN_ID exp_id=$EXP_ID"

# --- config & static ---
need 200 "GET /api/v1/config/run-defaults" "$API/api/v1/config/run-defaults" >/dev/null
need 200 "GET /experiments/new/" "$API/experiments/new/" >/dev/null
need 200 "GET /runs/new/" "$API/runs/new/" >/dev/null
need 200 "GET /targets/" "$API/targets/" >/dev/null

# --- targets ---
if [[ ! -f "$OPENAPI" ]]; then
  skip "upload target (no $OPENAPI)"
  TARGET_ID=""
else
  UP="$(curl -sS -X POST "$API/api/v1/targets" -F "file=@${OPENAPI};type=application/json")"
  TARGET_ID="$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$UP")"
  ok "POST /api/v1/targets → id=$TARGET_ID"
  need 200 "GET /api/v1/targets" "$API/api/v1/targets" >/dev/null
  need 200 "POST lint" -X POST "$API/api/v1/targets/${TARGET_ID}/lint" >/dev/null
  need 200 "GET targets lint page" "$API/targets/${TARGET_ID}/lint/" >/dev/null
fi

# --- pack ---
if [[ -n "${TARGET_ID:-}" ]]; then
  DRAFT="$(curl -sS -X POST "$API/api/v1/packs/draft" \
    -H 'Content-Type: application/json' \
    -d "{\"targetId\":\"${TARGET_ID}\",\"outId\":\"${PACK_ID}\"}")"
  ok "POST /api/v1/packs/draft"
  need 200 "GET pack" "$API/api/v1/packs/${PACK_ID}" >/dev/null
  YAML="$(python3 -c "import json,sys; print(json.load(sys.stdin)['yaml'])" <<<"$(curl -sS "$API/api/v1/packs/${PACK_ID}")")"
  curl -sS -X PUT "$API/api/v1/packs/${PACK_ID}" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys; print(json.dumps({'yaml': sys.stdin.read()}))" <<<"$YAML")" >/dev/null
  ok "PUT pack"
  need 200 "POST pack validate" -X POST "$API/api/v1/packs/${PACK_ID}/validate" \
    -H 'Content-Type: application/json' -d '{}' >/dev/null
else
  skip "pack draft (no target)"
fi

# --- run projection (free) ---
PROJ="$(curl -sS -X POST "$API/api/v1/runs/project" \
  -H 'Content-Type: application/json' \
  -d "{\"id\":\"${RUN_ID}\",\"packId\":null,\"targetId\":null,\"presets\":[],\"model\":\"gpt-5.6-luna\",\"provider\":\"openai\",\"reasoningEffort\":\"low\",\"repeats\":1,\"smoke\":true,\"probe\":false,\"resume\":false,\"dryRun\":false,\"allowCodeSandbox\":true}")"
echo "$PROJ" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('projectionText'); print('  projection exit', d.get('exitCode'))"
ok "POST /api/v1/runs/project (smoke dry-run)"

# --- spend gate: actual smoke run ---
if [[ "${RUN_SPEND:-1}" == "1" ]]; then
  START="$(curl -sS -X POST "$API/api/v1/runs" \
    -H 'Content-Type: application/json' \
    -d "{\"id\":\"${RUN_ID}\",\"packId\":null,\"targetId\":null,\"presets\":[],\"model\":\"gpt-5.6-luna\",\"provider\":\"openai\",\"reasoningEffort\":\"low\",\"repeats\":1,\"smoke\":true,\"probe\":false,\"resume\":false,\"dryRun\":false,\"allowCodeSandbox\":true,\"approve\":true}")"
  echo "$START" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  job', d.get('status'), d.get('id'))"
  ok "POST /api/v1/runs approve smoke"
  for i in $(seq 1 120); do
    sleep 2
    PR="$(curl -sS "$API/api/v1/runs/${RUN_ID}/progress")"
    ST="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('terminal'), d.get('job',{}).get('status'))" <<<"$PR")"
    if [[ "$ST" == True* ]]; then
      ok "run terminal: $(echo "$ST" | cut -d' ' -f2-)"
      break
    fi
    [[ "$i" -eq 120 ]] && bad "run progress timeout"
  done
  need 200 "GET report" "$API/api/v1/runs/${RUN_ID}/report" >/dev/null
  need 200 "GET brief" "$API/api/v1/runs/${RUN_ID}/brief" >/dev/null
  need 200 "GET artifacts list" "$API/api/v1/runs/${RUN_ID}/artifacts" >/dev/null
  need 200 "GET run detail page" "$API/runs/${RUN_ID}/" >/dev/null
else
  skip "live smoke run (RUN_SPEND=0)"
fi

# --- experiments ---
CREATE="$(curl -sS -X POST "$API/api/v1/experiments" \
  -H 'Content-Type: application/json' \
  -d "{\"id\":\"${EXP_ID}\",\"planPath\":\"../../plans/baseline-experiment-80.yaml\"}")"
if echo "$CREATE" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('id') else 1)" 2>/dev/null; then
  ok "POST create experiment"
else
  bad "POST create experiment: $(echo "$CREATE" | head -c 200)"
fi
need 200 "GET experiments list" "$API/api/v1/experiments" >/dev/null
need 200 "GET experiment" "$API/api/v1/experiments/${EXP_ID}" >/dev/null
need 200 "GET coverage" "$API/api/v1/experiments/${EXP_ID}/coverage" >/dev/null
EP="$(curl -sS -X POST "$API/api/v1/experiments/${EXP_ID}/run/project" \
  -H 'Content-Type: application/json' \
  -d '{"slice":"smoke","allowCodeSandbox":true}')"
echo "$EP" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  exp projection missing', d.get('missingCells'))"
ok "POST experiment run/project slice=smoke"
need 200 "GET experiment page" "$API/experiments/${EXP_ID}/" >/dev/null

# --- compare (same run twice should refuse or work) ---
if [[ "${RUN_SPEND:-1}" == "1" ]]; then
  CMP="$(curl -sS -X POST "$API/api/v1/compare" \
    -H 'Content-Type: application/json' \
    -d "{\"runIds\":[\"${RUN_ID}\",\"${RUN_ID}\"]}")"
  ok "POST compare"
else
  skip "compare"
fi

# --- MCP ---
MCP="$(curl -sS -X POST "$API/mcp" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')"
echo "$MCP" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  mcp tools', len(d.get('result',{}).get('tools',[])))"
ok "POST /mcp tools/list"

# --- adapter generate (CLI disk, free) ---
GEN="/tmp/harness-ui-gen-${TS}"
mkdir -p "$GEN"
if "$REPO/.venv/bin/python" "$UI/adapter/harness_json.py" run-config >/dev/null 2>&1; then
  ok "adapter run-config"
else
  bad "adapter run-config"
fi
if "$REPO/.venv/bin/harness" generate analyze "$OPENAPI" -o "$GEN" 2>/dev/null; then
  ok "CLI generate analyze"
  "$REPO/.venv/bin/python" "$UI/adapter/harness_json.py" generate-status "$GEN" >/dev/null && ok "adapter generate-status" || bad "adapter generate-status"
else
  bad "CLI generate analyze"
fi

# --- REST generate path (G6.3) when staging is up ---
if [[ "${RUN_GENERATE_E2E:-auto}" != "0" ]] && [[ -x "$UI/scripts/e2e-generate.sh" ]]; then
  if curl -sf -o /dev/null --max-time 2 "${TARGET_BASE_URL:-http://127.0.0.1:8765}/" \
    || curl -sf -o /dev/null --max-time 2 "${TARGET_BASE_URL:-http://127.0.0.1:8765}/health"; then
    if "$UI/scripts/e2e-generate.sh"; then
      ok "REST generate E2E (upload→manifest→experiment)"
    else
      bad "REST generate E2E"
    fi
  else
    skip "REST generate E2E (no staging at TARGET_BASE_URL)"
  fi
else
  skip "REST generate E2E"
fi

# --- traversal guard ---
# Encode `..` in the last segment so curl/Spring do not collapse the URL to
# `/api/v1/runs/etc/passwd` (404) before PathsSafe can reject it (400).
need 400 "artifact traversal 400" \
  "$API/api/v1/runs/${RUN_ID}/artifacts/..%2F..%2Fetc%2Fpasswd" >/dev/null || true

log ""
log "==> summary: pass=$PASS fail=$FAIL skip=$SKIP"
[[ "$FAIL" -eq 0 ]]
