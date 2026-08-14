#!/usr/bin/env bash
# Harness install smoke inside the runtime-base Docker stage (T4.3).
# Usage (repo root):
#   ./harness-ui/scripts/smoke-doctor.sh
#   HARNESS_VERSION=v0.0.1 ./harness-ui/scripts/smoke-doctor.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${HARNESS_VERSION:-v0.0.1}"
IMAGE="${SMOKE_IMAGE:-harness-ui:doctor}"

echo "==> building runtime-base as ${IMAGE} (harness ${VERSION})"
docker build -f "${ROOT}/harness-ui/Dockerfile" \
  --target runtime-base \
  --build-arg "HARNESS_VERSION=${VERSION}" \
  -t "${IMAGE}" \
  "${ROOT}"

echo "==> harness doctor + version inside image"
docker run --rm "${IMAGE}" bash -lc '
  set -e
  harness --version
  harness doctor
  python3 -c "import harness; assert harness.__version__ == \"0.0.1\", harness.__version__"
'
echo "ok"
