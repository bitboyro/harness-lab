#!/usr/bin/env bash
# Build Next export, sync into Spring static/, start API on :8085.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UI="$ROOT/harness-ui"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}"

mkdir -p "$UI/harness-data"/{targets,packs,results,jobs,compare}

echo "==> Next.js static export"
(cd "$UI/web" && npm run build)
"$UI/scripts/sync-web-static.sh"

echo "==> Spring Boot (:8085, data=$UI/harness-data)"
cd "$UI/api"
exec ./mvnw spring-boot:run -DskipTests \
  -Dspring-boot.run.arguments="\
--harness.data=$UI/harness-data \
--harness.cli=$ROOT/.venv/bin/harness \
--harness.adapter=$ROOT/.venv/bin/python \
--harness.adapter-script=$UI/adapter/harness_json.py \
--harness.disk-reserve-gb=0" \
  "$@"
