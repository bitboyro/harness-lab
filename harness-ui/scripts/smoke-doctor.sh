#!/usr/bin/env bash
# T4.3 — build the runtime-base stage (no api/web) and assert doctor + pin.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAG="${HARNESS_VERSION:-v0.0.1}"
IMAGE="${HARNESS_UI_DOCTOR_IMAGE:-harness-ui:doctor}"

cd "$ROOT"
docker build -f harness-ui/Dockerfile \
  --target runtime-base \
  --build-arg "HARNESS_VERSION=${TAG}" \
  -t "$IMAGE" \
  .

docker run --rm "$IMAGE" bash -c '
  set -euo pipefail
  python3 --version
  command -v curl >/dev/null
  curl --version | head -1
  harness doctor
  python3 -c "import harness; v=harness.__version__; assert v == \"0.0.1\", v; print(\"harness\", v)"
'
