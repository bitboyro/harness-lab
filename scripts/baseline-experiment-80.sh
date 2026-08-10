#!/usr/bin/env bash
# Local throwaway helpers for baseline-experiment-80 (gitignored under /scripts/).
#
#   ./scripts/baseline-experiment-80.sh bait          # write pack.yaml at bait path
#   ./scripts/baseline-experiment-80.sh smoke-c1      # C1 only (bash+docs, no cheat) + transcript
#   ./scripts/baseline-experiment-80.sh smoke-zcheat  # bait + Z-cheat-only smoke + transcript
#   ./scripts/baseline-experiment-80.sh full          # bait + full matrix + html report
#   ./scripts/baseline-experiment-80.sh report        # html/charts from an existing out dir
#
# Why bait is separate from harness run: controlled mode builds the pack in
# memory and does not dump gold answers to disk (C/D arms can read absolute
# paths). Z-cheat needs the file on purpose — place it here before any Z-cheat
# cell runs. C1 is the same DocsShell transport with normal curl docs (no bait).
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

HARNESS="${HARNESS:-$REPO/.venv/bin/harness}"
PYTHON="${PYTHON:-$REPO/.venv/bin/python}"
PLAN="${PLAN:-plans/baseline-experiment-80.yaml}"
OUT="${OUT:-results/baseline-experiment-80}"
BAIT_DIR="${BAIT_DIR:-/var/lib/harness/baseline-experiment-80}"
BAIT_PACK="$BAIT_DIR/pack.yaml"

# Must match plans/baseline-experiment-80.yaml tasks.generate
CORES="${CORES:-80}"
SEED="${SEED:-1}"
FAN_OUT="${FAN_OUT:-8}"
DIFFICULTY="${DIFFICULTY:-hard}"
CONCURRENCY="${CONCURRENCY:-24}"

die() { echo "error: $*" >&2; exit 1; }

need_venv() {
  [[ -x "$HARNESS" ]] || die "missing $HARNESS — create .venv and pip install -e '.[dev,openai]'"
  [[ -x "$PYTHON" ]] || die "missing $PYTHON"
  [[ -f "$PLAN" ]] || die "missing $PLAN"
}

write_bait_pack() {
  need_venv
  if [[ ! -d "$BAIT_DIR" ]]; then
    if mkdir -p "$BAIT_DIR" 2>/dev/null; then
      :
    else
      echo "==> $BAIT_DIR needs root to create"
      sudo mkdir -p "$BAIT_DIR"
      sudo chown "$(id -u):$(id -g)" "$BAIT_DIR"
    fi
  fi
  if [[ ! -w "$BAIT_DIR" ]]; then
    echo "==> fixing write access on $BAIT_DIR"
    sudo chown "$(id -u):$(id -g)" "$BAIT_DIR"
  fi

  echo "==> writing $BAIT_PACK (cores=$CORES seed=$SEED fan_out=$FAN_OUT difficulty=$DIFFICULTY)"
  CORES="$CORES" SEED="$SEED" FAN_OUT="$FAN_OUT" DIFFICULTY="$DIFFICULTY" \
  BAIT_PACK="$BAIT_PACK" "$PYTHON" - <<'PY'
from pathlib import Path
import os
import yaml
from harness.experiment.domain import WorldShape, build_world, shape_for_cores
from harness.experiment.tasks import build_pack

cores = int(os.environ["CORES"])
seed = int(os.environ["SEED"])
fan_out = int(os.environ["FAN_OUT"])
difficulty = os.environ["DIFFICULTY"]
out = Path(os.environ["BAIT_PACK"])

shape = shape_for_cores(cores, WorldShape(episodes_per_season=fan_out))
pack = build_pack(
    build_world(seed, shape),
    cores=cores,
    seed=seed,
    difficulty=difficulty,
)
out.write_text(yaml.safe_dump(pack, sort_keys=False))
print(f"wrote {out} ({len(pack['tasks'])} tasks)")
PY
}

cmd_plan() {
  need_venv
  "$HARNESS" plan "$PLAN" --explain
}

cmd_smoke_c1() {
  # Same DocsShell as Z-cheat (bash + docs), but instructions are the generated
  # curl reference — no bait path. No pack.yaml required.
  need_venv
  local smoke_out="${SMOKE_OUT:-results/c1-smoke}"
  echo "==> C1 smoke (bash+docs, no cheat) → $smoke_out"
  "$HARNESS" run --plan "$PLAN" \
    --presets C1 \
    --out "$smoke_out" --id c1-smoke \
    --smoke --yes
  echo "==> transcript"
  "$HARNESS" transcript "$smoke_out/traces"
}

cmd_smoke_zcheat() {
  write_bait_pack
  local smoke_out="${SMOKE_OUT:-results/z-cheat-smoke}"
  echo "==> Z-cheat smoke → $smoke_out"
  "$HARNESS" run --plan "$PLAN" \
    --presets Z-cheat \
    --out "$smoke_out" --id z-cheat-smoke \
    --smoke --yes
  echo "==> transcript (look for cat/grep/head of pack.yaml)"
  "$HARNESS" transcript "$smoke_out/traces"
}

cmd_full() {
  write_bait_pack
  cmd_plan
  echo "==> full matrix → $OUT  (concurrency=$CONCURRENCY)"
  echo "    tip: second terminal → $HARNESS progress $OUT"
  # No --stream: at concurrency>1 turns interleave and flood the log.
  # Text summary prints at the end; HTML is a separate render (below).
  "$HARNESS" run --plan "$PLAN" \
    --out "$OUT" --id baseline-experiment-80 \
    --concurrency "$CONCURRENCY"
  cmd_report
}

cmd_report() {
  need_venv
  [[ -d "$OUT" ]] || die "no results at $OUT — run full first or set OUT="
  echo "==> html + charts → $OUT"
  "$HARNESS" report "$OUT" --html "$OUT/report.html" --charts "$OUT/charts"
  echo "open $OUT/report.html"
}

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

case "${1:-}" in
  bait)          write_bait_pack ;;
  plan)          cmd_plan ;;
  smoke-c1)      cmd_smoke_c1 ;;
  smoke-zcheat)  cmd_smoke_zcheat ;;
  full)          cmd_full ;;
  report)        cmd_report ;;
  -h|--help|"")  usage 0 ;;
  *)             echo "unknown command: $1" >&2; usage 1 ;;
esac
