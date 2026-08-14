#!/usr/bin/env bash
# Side-by-side model compare: one Ghostty window, tmux split, screen recording.
#
# Both panes run the SAME sequence of tests in lock-step:
#   start together → whoever finishes first waits → both done → review pause
#   → next test. Only --model differs between panes.
#
# Default steps are the smoke arms (Z0, A1, D1), each with the same world
# (seed/cores/max-tasks). Override with --steps or EXTRA_ARGS via -- .
#
# Usage:
#   ./scripts/record-model-compare.sh
#   ./scripts/record-model-compare.sh --left gpt-5.6-luna --right gpt-5.6-sol
#   ./scripts/record-model-compare.sh --review 10 --read 20
#
# Requires: Ghostty.app, tmux, ffmpeg (screen capture), .venv with harness.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LEFT_MODEL="${LEFT_MODEL:-gpt-5.6-luna}"
RIGHT_MODEL="${RIGHT_MODEL:-gpt-5.6-sol}"
READ_SECS="${READ_SECS:-15}"
COUNTDOWN_SECS="${COUNTDOWN_SECS:-5}"
SIDE_PAUSE_SECS="${SIDE_PAUSE_SECS:-8}"
REVIEW_SECS="${REVIEW_SECS:-10}"
AUTO_YES=0
# Shared flags for every step (model/out/id/presets are set per pane/step).
BASE_ARGS=(--yes --stream --concurrency 1 --cores 2 --max-tasks 4 --repeats 1 --seed 1)
# One harness invocation per entry; both panes run the same entry at the same time.
STEPS=(Z0 A1 D1)
OUT_BASE=""
GHOSTTY_APP="${GHOSTTY_APP:-/Applications/Ghostty.app}"
HARNESS="${HARNESS:-$ROOT/.venv/bin/harness}"
TMUX_BIN="${TMUX_BIN:-$(command -v tmux || true)}"
FFMPEG_BIN="${FFMPEG_BIN:-$(command -v ffmpeg || true)}"
MAX_RECORD_SECS="${MAX_RECORD_SECS:-3600}"
# AVFoundation screen index; empty = auto-detect "Capture screen 0".
SCREEN_DEVICE="${SCREEN_DEVICE:-}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

  --left MODEL          Left pane model   (default: $LEFT_MODEL)
  --right MODEL         Right pane model  (default: $RIGHT_MODEL)
  --read SECONDS        Briefing pause before start (default: $READ_SECS)
  --countdown SECONDS   Final countdown after Enter / read (default: $COUNTDOWN_SECS)
  --side-pause SECONDS  Pause inside each pane before step 1 (default: $SIDE_PAUSE_SECS)
  --review SECONDS      After both panes finish a step, wait this long before
                        starting the next (default: $REVIEW_SECS)
  --steps LIST          Comma-separated presets / step names (default: Z0,A1,D1)
  --out DIR             Session directory (default: results/compare-TIMESTAMP)
  --harness PATH        harness binary (default: .venv/bin/harness)
  --ghostty PATH        Ghostty.app path
  --tmux PATH           tmux binary
  --ffmpeg PATH         ffmpeg binary (used for screen recording)
  --screen-device N     AVFoundation screen index (default: auto-detect)
  --yes                 Skip the "press Enter" gate; just wait --read seconds
  --                    Extra flags appended to every harness run
                        (default base: ${BASE_ARGS[*]})

Lock-step: both panes get a "go" for step N together. Early finishers wait.
When both are done, a ${REVIEW_SECS}s review pause, then go for step N+1.

Screen recording uses ffmpeg (not screencapture): macOS screencapture -V only
writes the file when the full timer ends, so stopping early left an empty path.

Environment: LEFT_MODEL, RIGHT_MODEL, READ_SECS, REVIEW_SECS, SIDE_PAUSE_SECS, HARNESS, SCREEN_DEVICE
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --left) LEFT_MODEL="$2"; shift 2 ;;
    --right) RIGHT_MODEL="$2"; shift 2 ;;
    --read) READ_SECS="$2"; shift 2 ;;
    --countdown) COUNTDOWN_SECS="$2"; shift 2 ;;
    --side-pause) SIDE_PAUSE_SECS="$2"; shift 2 ;;
    --review) REVIEW_SECS="$2"; shift 2 ;;
    --steps)
      IFS=',' read -r -a STEPS <<<"$2"
      shift 2
      ;;
    --out) OUT_BASE="$2"; shift 2 ;;
    --harness) HARNESS="$2"; shift 2 ;;
    --ghostty) GHOSTTY_APP="$2"; shift 2 ;;
    --tmux) TMUX_BIN="$2"; shift 2 ;;
    --ffmpeg) FFMPEG_BIN="$2"; shift 2 ;;
    --screen-device) SCREEN_DEVICE="$2"; shift 2 ;;
    --yes) AUTO_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; BASE_ARGS+=("$@"); break ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

die() { echo "error: $*" >&2; exit 1; }

[[ -d "$GHOSTTY_APP" ]] || die "Ghostty not found at $GHOSTTY_APP"
[[ -x "$HARNESS" ]] || die "harness not executable at $HARNESS (run: python3 -m venv .venv && .venv/bin/pip install -e '.[dev,openai]')"
[[ -n "$TMUX_BIN" && -x "$TMUX_BIN" ]] || die "tmux not found (brew install tmux)"
[[ -n "$FFMPEG_BIN" && -x "$FFMPEG_BIN" ]] || die "ffmpeg not found (brew install ffmpeg) — required for screen recording"
(( ${#STEPS[@]} >= 1 )) || die "need at least one --steps entry"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_BASE="${OUT_BASE:-$ROOT/results/compare-$STAMP}"
SESSION="harness-compare-$STAMP"
SYNC="$OUT_BASE/sync"
mkdir -p "$OUT_BASE"/{bin,left,right} "$SYNC"
VIDEO="$OUT_BASE/screen.mp4"
REC_LOG="$OUT_BASE/ffmpeg-record.log"
REC_FIFO="$OUT_BASE/bin/ffmpeg.fifo"
LEFT_DONE="$OUT_BASE/left.done"
RIGHT_DONE="$OUT_BASE/right.done"
LEFT_EXIT="$OUT_BASE/left.exit"
RIGHT_EXIT="$OUT_BASE/right.exit"
STEPS_FILE="$OUT_BASE/bin/steps.txt"
ARGS_FILE="$OUT_BASE/bin/base.args"

rm -f "$LEFT_DONE" "$RIGHT_DONE" "$LEFT_EXIT" "$RIGHT_EXIT"
rm -f "$SYNC"/*

# Persist step list + shared argv for the pane runners.
printf '%s\n' "${STEPS[@]}" > "$STEPS_FILE"
: > "$ARGS_FILE"
for a in "${BASE_ARGS[@]}"; do
  printf '%s\0' "$a" >> "$ARGS_FILE"
done

# ---------------------------------------------------------------------------
# Per-pane runner: lock-step through STEPS under orchestrator gates.
# ---------------------------------------------------------------------------
cat > "$OUT_BASE/bin/run-side.sh" <<'RUNNER'
#!/usr/bin/env bash
set -uo pipefail
SIDE="${1:?side}"
MODEL="${2:?model}"
ROOT="${3:?root}"
OUT="${4:?out}"
HARNESS="${5:?harness}"
PAUSE="${6:?pause}"
STEPS_FILE="${7:?steps-file}"
ARGS_FILE="${8:?args-file}"

SYNC="$OUT/sync"
DONE_ALL="$OUT/${SIDE}.done"
EXITF="$OUT/${SIDE}.exit"
mkdir -p "$OUT/$SIDE" "$SYNC"

base=()
if [[ -s "$ARGS_FILE" ]]; then
  while IFS= read -r -d '' a; do
    base+=("$a")
  done < "$ARGS_FILE"
fi

STEPS=()
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -n "$line" ]] && STEPS+=("$line")
done < "$STEPS_FILE"
N_STEPS=${#STEPS[@]}

clear
cat <<EOF
══════════════════════════════════════════════════════════
  pane    : ${SIDE}
  model   : ${MODEL}
  steps   : ${STEPS[*]}
  lockstep: wait for peer after each step, then review pause
══════════════════════════════════════════════════════════

EOF

if [[ "$PAUSE" =~ ^[0-9]+$ ]] && (( PAUSE > 0 )); then
  for ((i = PAUSE; i >= 1; i--)); do
    printf '\r  first step in %2d...   ' "$i"
    sleep 1
  done
  printf '\r  ready.                \n\n'
fi

cd "$ROOT"
final_status=0

for ((idx = 0; idx < N_STEPS; idx++)); do
  step="${STEPS[$idx]}"
  step_id="$(printf '%02d-%s' "$idx" "$step")"
  go="$SYNC/${step_id}.go"
  peer_wait="$SYNC/${SIDE}.${step_id}.done"
  results="$OUT/${SIDE}/${step_id}"
  mkdir -p "$results"

  echo
  echo "──────────────────────────────────────────────────────────"
  echo "  step $((idx + 1))/${N_STEPS}  ·  ${step}  ·  waiting for go"
  echo "──────────────────────────────────────────────────────────"

  # Gate: orchestrator drops .go when BOTH panes should start this step.
  while [[ ! -f "$go" ]]; do
    if [[ -f "$SYNC/abort" ]]; then
      echo "aborted by orchestrator"
      echo 1 > "$EXITF"
      : > "$DONE_ALL"
      exit 1
    fi
    sleep 0.25
  done

  echo
  echo "  GO  ${step}  (model=${MODEL})"
  echo

  set +e
  "$HARNESS" run \
    --out "$results" \
    --id "compare-${SIDE}-${step_id}" \
    --model "$MODEL" \
    --presets "$step" \
    "${base[@]}"
  status=$?
  set -e
  if (( status != 0 )); then
    final_status=$status
  fi

  # Tell the orchestrator (and the peer pane's status line) we are done.
  echo "$status" > "$SYNC/${SIDE}.${step_id}.exit"
  : > "$peer_wait"
  sync "$peer_wait" 2>/dev/null || true

  echo
  echo "  finished ${step}  exit=${status}"
  echo "  waiting for the other pane (then a shared review pause)..."

  # Stay parked until the orchestrator opens the next gate (or all-done).
  # That is what keeps an early finisher from racing into the next test.
  if (( idx + 1 < N_STEPS )); then
    next_id="$(printf '%02d-%s' "$((idx + 1))" "${STEPS[$((idx + 1))]}")"
    next_go="$SYNC/${next_id}.go"
    while [[ ! -f "$next_go" && ! -f "$SYNC/all-done" && ! -f "$SYNC/abort" ]]; do
      sleep 0.25
    done
  else
    while [[ ! -f "$SYNC/all-done" && ! -f "$SYNC/abort" ]]; do
      sleep 0.25
    done
  fi
done

echo "$final_status" > "$EXITF"
: > "$DONE_ALL"
sync "$DONE_ALL" "$EXITF" 2>/dev/null || true

echo
echo "──────────────────────────────────────────────────────────"
echo "  all ${N_STEPS} steps done  ·  pane=${SIDE}  ·  exit=${final_status}"
echo "  leaving this bash open — detach/close when done reading"
echo "──────────────────────────────────────────────────────────"
echo
exec /bin/bash -l
RUNNER
chmod +x "$OUT_BASE/bin/run-side.sh"

# ---------------------------------------------------------------------------
# Orchestrator helpers
# ---------------------------------------------------------------------------

start_tmux_session() {
  "$TMUX_BIN" kill-session -t "$SESSION" 2>/dev/null || true

  "$TMUX_BIN" new-session -d -s "$SESSION" -n compare -c "$ROOT" -- \
    "$OUT_BASE/bin/run-side.sh" left "$LEFT_MODEL" "$ROOT" "$OUT_BASE" \
    "$HARNESS" "$SIDE_PAUSE_SECS" "$STEPS_FILE" "$ARGS_FILE"
  "$TMUX_BIN" split-window -h -t "${SESSION}:compare" -c "$ROOT" -- \
    "$OUT_BASE/bin/run-side.sh" right "$RIGHT_MODEL" "$ROOT" "$OUT_BASE" \
    "$HARNESS" "$SIDE_PAUSE_SECS" "$STEPS_FILE" "$ARGS_FILE"
  "$TMUX_BIN" select-layout -t "${SESSION}:compare" even-horizontal

  "$TMUX_BIN" set-option -t "$SESSION" pane-border-status top
  "$TMUX_BIN" set-option -t "$SESSION" pane-border-format ' #{pane_title} '
  "$TMUX_BIN" select-pane -t "${SESSION}:compare.0" -T "left · ${LEFT_MODEL}"
  "$TMUX_BIN" select-pane -t "${SESSION}:compare.1" -T "right · ${RIGHT_MODEL}"
  "$TMUX_BIN" set-option -t "$SESSION" status-left "[ compare ] "
  "$TMUX_BIN" set-option -t "$SESSION" status-right " #{session_name} "
  "$TMUX_BIN" set-option -t "$SESSION" mouse on
  "$TMUX_BIN" set-option -t "$SESSION" remain-on-exit on
}

open_ghostty() {
  open -na "$GHOSTTY_APP" --args \
    --title="harness · ${LEFT_MODEL} vs ${RIGHT_MODEL}" \
    --command=/bin/bash \
    --working-directory="$ROOT" \
    --maximize=true \
    -e "$TMUX_BIN" attach-session -t "$SESSION"
}

countdown() {
  local n="$1" label="$2"
  (( n <= 0 )) && return 0
  local i
  for ((i = n; i >= 1; i--)); do
    printf '\r%s in %2d...   ' "$label" "$i"
    sleep 1
  done
  printf '\r%s now.        \n' "$label"
}

wait_enter_or_timeout() {
  local secs="$1"
  if (( AUTO_YES )); then
    countdown "$secs" "Starting"
    return 0
  fi
  echo
  echo "  Press Enter to continue early, or wait ${secs}s…"
  if read -r -t "$secs" _; then
    echo "  (Enter received)"
  else
    echo "  (timer elapsed)"
  fi
}

briefing() {
  cat <<EOF

┌─────────────────────────────────────────────────────────────┐
│  harness-lab · model compare recording (lock-step)          │
└─────────────────────────────────────────────────────────────┘

What will happen:

  1. You get ${READ_SECS}s to read this (or press Enter).
  2. A short ${COUNTDOWN_SECS}s countdown, then screen recording starts.
  3. One Ghostty window opens with a tmux left/right split.
  4. Both panes run the SAME steps in lock-step (only model differs).
  5. After each step: wait for the slower pane, then ${REVIEW_SECS}s to review,
     then the next step starts on both sides together.

Steps (${#STEPS[@]}):
EOF
  local i=1 s
  for s in "${STEPS[@]}"; do
    printf '  %2d. %s\n' "$i" "$s"
    i=$((i + 1))
  done
  cat <<EOF

Left pane   model=${LEFT_MODEL}
Right pane  model=${RIGHT_MODEL}

Shared harness flags:
  ${BASE_ARGS[*]}

Artifacts
  session : ${OUT_BASE}
  video   : ${VIDEO}
  tmux    : ${SESSION}

Notes
  • Screen Recording permission is required for the app that runs this script
    (Terminal / Cursor / iTerm) — ffmpeg captures via AVFoundation.
  • Video is screen.mp4 (finalized cleanly when the run ends).
  • Ctrl-C aborts once and stops the recorder.

EOF
}

detect_screen_device() {
  # Prefer "Capture screen 0" from ffmpeg's AVFoundation list.
  local listed idx
  listed="$("$FFMPEG_BIN" -f avfoundation -list_devices true -i "" 2>&1 || true)"
  idx="$(printf '%s\n' "$listed" | sed -n 's/.*\[\([0-9][0-9]*\)\] Capture screen 0.*/\1/p' | head -1)"
  if [[ -z "$idx" ]]; then
    idx="$(printf '%s\n' "$listed" | sed -n 's/.*\[\([0-9][0-9]*\)\] Capture screen.*/\1/p' | head -1)"
  fi
  [[ -n "$idx" ]] || die "no AVFoundation 'Capture screen' device found. Grant Screen Recording permission to Terminal/Cursor (System Settings → Privacy & Security → Screen Recording), then retry. ffmpeg devices were:\n$listed"
  SCREEN_DEVICE="$idx"
}

start_recording() {
  if [[ -z "$SCREEN_DEVICE" ]]; then
    detect_screen_device
  fi
  echo "  ffmpeg screen device: $SCREEN_DEVICE"

  rm -f "$VIDEO" "$REC_FIFO" "$REC_LOG"
  mkfifo "$REC_FIFO"

  # stdin stays open on the fifo so we can send `q` later to finalize the mp4
  # (SIGINT alone leaves a truncated file with no moov atom).
  "$FFMPEG_BIN" -y -loglevel info \
    -f avfoundation -capture_cursor 1 -framerate 30 \
    -i "${SCREEN_DEVICE}:none" \
    -c:v libx264 -pix_fmt yuv420p -preset ultrafast -crf 23 \
    "$VIDEO" <"$REC_FIFO" >"$REC_LOG" 2>&1 &
  REC_PID=$!
  # Keep the write end open for the life of the recording.
  exec 3>"$REC_FIFO"

  # Wait until ffmpeg has actually written bytes — proves capture works before
  # we spend money on the matrix.
  local i size=0
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.5
    if ! kill -0 "$REC_PID" 2>/dev/null; then
      exec 3>&- 2>/dev/null || true
      die "ffmpeg exited before producing video. See $REC_LOG — usually Screen Recording permission is missing for the app running this script."
    fi
    size="$(stat -f%z "$VIDEO" 2>/dev/null || echo 0)"
    if (( size > 1000 )); then
      echo "  recording (ffmpeg pid $REC_PID, ${size} bytes so far)"
      return 0
    fi
  done
  exec 3>&- 2>/dev/null || true
  kill -KILL "$REC_PID" 2>/dev/null || true
  wait "$REC_PID" 2>/dev/null || true
  die "ffmpeg ran but wrote no video after 5s. See $REC_LOG — check Screen Recording permission / --screen-device."
}

stop_recording() {
  # Idempotent: traps + normal path both call this.
  if [[ -z "${REC_PID:-}" ]]; then
    return 0
  fi
  local pid="$REC_PID"
  REC_PID=""

  if kill -0 "$pid" 2>/dev/null; then
    # Graceful quit finalizes the mp4 container.
    echo q >&3 2>/dev/null || true
    exec 3>&- 2>/dev/null || true
    local i
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.4
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
      sleep 0.5
    fi
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
  else
    exec 3>&- 2>/dev/null || true
  fi
  rm -f "$REC_FIFO"

  if [[ ! -s "$VIDEO" ]]; then
    echo "warning: no video at $VIDEO (see $REC_LOG)" >&2
    return 1
  fi
  local size
  size="$(stat -f%z "$VIDEO" 2>/dev/null || echo 0)"
  echo "  video saved: $VIDEO ($size bytes)"
  return 0
}

wait_step_done() {
  local step_id="$1"
  local left_m="$SYNC/left.${step_id}.done"
  local right_m="$SYNC/right.${step_id}.done"
  local started=$SECONDS
  local left_s right_s

  set +e
  while true; do
    if [[ -f "$left_m" && -f "$right_m" ]]; then
      printf '\n  both panes finished %s\n' "$step_id"
      set -e
      return 0
    fi
    if [[ -n "${REC_PID:-}" ]] && ! kill -0 "$REC_PID" 2>/dev/null; then
      printf '\n'
      echo "recording ended early — see $REC_LOG" >&2
      set -e
      return 1
    fi
    if (( SECONDS - started >= MAX_RECORD_SECS )); then
      printf '\n'
      echo "timed out waiting for step $step_id" >&2
      set -e
      return 1
    fi
    left_s="...."
    right_s="...."
    [[ -f "$left_m" ]] && left_s="done"
    [[ -f "$right_m" ]] && right_s="done"
    printf '\r  step %-12s  left=%-4s  right=%-4s  %ss   ' \
      "$step_id" "$left_s" "$right_s" "$((SECONDS - started))"
    sleep 0.5
  done
}

conduct_steps() {
  local idx step step_id
  local n=${#STEPS[@]}

  # Give panes a moment to print their headers / side-pause.
  sleep 1

  for ((idx = 0; idx < n; idx++)); do
    step="${STEPS[$idx]}"
    step_id="$(printf '%02d-%s' "$idx" "$step")"

    echo
    echo "→ GO step $((idx + 1))/${n}: ${step}"
    : > "$SYNC/${step_id}.go"
    sync "$SYNC/${step_id}.go" 2>/dev/null || true

    wait_step_done "$step_id" || {
      : > "$SYNC/abort"
      return 1
    }

    if (( idx + 1 < n )); then
      echo "→ review pause (${REVIEW_SECS}s) before next step"
      countdown "$REVIEW_SECS" "Next step"
    fi
  done

  : > "$SYNC/all-done"
  sync "$SYNC/all-done" 2>/dev/null || true
  echo "→ all steps complete"
  return 0
}

CLEANED=0
cleanup() {
  local ec=$?
  (( CLEANED )) && return 0
  CLEANED=1
  : > "$SYNC/abort" 2>/dev/null || true
  stop_recording || true
  if [[ $ec -ne 0 ]]; then
    echo "aborted (exit $ec). partial artifacts in $OUT_BASE" >&2
    echo "tmux session (if any): $SESSION — kill with: tmux kill-session -t $SESSION" >&2
  fi
}
trap cleanup EXIT INT TERM

briefing
wait_enter_or_timeout "$READ_SECS"
countdown "$COUNTDOWN_SECS" "Recording + Ghostty"

echo "→ starting screen recording → $VIDEO"
start_recording

echo "→ creating tmux session $SESSION (left/right split)"
start_tmux_session

echo "→ opening Ghostty attached to that session"
open_ghostty

conduct_steps || true

echo "→ stopping recording"
stop_recording || true
trap - EXIT INT TERM
CLEANED=1

LEFT_EC="$(cat "$LEFT_EXIT" 2>/dev/null || echo '?')"
RIGHT_EC="$(cat "$RIGHT_EXIT" 2>/dev/null || echo '?')"

if [[ -s "$VIDEO" ]]; then
  VIDEO_LINE="$VIDEO  ($(stat -f%z "$VIDEO") bytes)"
else
  VIDEO_LINE="MISSING — see $REC_LOG"
fi

cat <<EOF

Done.
  video        : $VIDEO_LINE
  left exit    : $LEFT_EC   ($LEFT_MODEL)
  right exit   : $RIGHT_EC  ($RIGHT_MODEL)
  left results : $OUT_BASE/left/
  right results: $OUT_BASE/right/
  steps        : ${STEPS[*]}
  tmux session : $SESSION

Ghostty/tmux stay open for reading.
  reattach: tmux attach -t $SESSION
  cleanup : tmux kill-session -t $SESSION
EOF
