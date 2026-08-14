#!/usr/bin/env bash
# Install the built bundle the way a stranger would, and use it.
#
#   ./scripts/clean-install-check.sh              # default interpreter
#   ./scripts/clean-install-check.sh python3.12   # a specific one
#
# The point is to test the *artifact*, never the checkout. So it unpacks into a
# scratch directory outside the repo and cd's there: a test that runs from the
# source tree will pass even when the wheel is missing half its package data,
# because Python finds the files next door.
#
# What this catches: missing package data, a broken entry point, an import that
# only works from a checkout, a dependency declared in the wrong extra, and a
# `requires-python` that lies.
#
# What it does not catch: anything about *this machine* being unusual — curl and
# git are already here, and the wheel was built with a compatible interpreter.
# For that you want another machine, or the release workflow's 3.11/3.12/3.13
# matrix, which is the only place `requires-python` is really checked.
set -euo pipefail

PY=${1:-python3}
REPO=$(cd "$(dirname "$0")/.." && pwd)
BUNDLE=$(ls "$REPO"/dist/harness-lab-*.zip 2>/dev/null | tail -1 || true)

if [ -z "$BUNDLE" ]; then
    echo "no bundle in dist/ — run ./build.sh first" >&2
    exit 1
fi

command -v "$PY" >/dev/null || { echo "no such interpreter: $PY" >&2; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "==> $("$PY" -V), $(basename "$BUNDLE")"
cd "$WORK"
unzip -q "$BUNDLE"
cd harness-lab-*

# No API key: everything below must work without one, and a key leaking in from
# the developer's shell would hide a missing-credential bug.
unset OPENAI_API_KEY

"$PY" -m venv .venv
.venv/bin/python install.py >/dev/null
V=.venv/bin

check () {
    printf '    %-46s' "$1"; shift
    if "$@" >/dev/null 2>&1; then echo "ok"; else echo "FAILED"; FAIL=1; fi
}

FAIL=0
echo "  entry points"
check "harness --version"                 $V/harness --version
check "python -m harness --version"       $V/python -m harness --version
echo "  works with no API key"
check "harness doctor"                    $V/harness doctor
check "harness lint --demo"               $V/harness lint --demo
echo "  package data survived the wheel"
check "harness report (bundled result)"   $V/harness report results/auth-smoke
check "harness transcript (gzipped)"      $V/harness transcript results/auth-smoke/traces
check "harness report --html"             $V/harness report results/auth-smoke --html r.html
check "harness init --agent both"         $V/harness init --agent both --dir .
check "  └ skill file written"            test -f .claude/skills/harness-lab/SKILL.md
check "  └ insights script shipped"       test -f .claude/skills/harness-insights/scripts/extract_brief.py
check "  └ pack template written"         test -f packs/template.yaml
check "harness scaffold (offline spec)"   $V/harness scaffold examples/openapi.json -o /dev/null
echo "  refuses what it should"
check "unknown model exits non-zero"      sh -c "! $V/harness run --out x --id x --model bogus-x --yes"

[ "$FAIL" = 0 ] && echo "  PASS" || { echo "  FAIL"; exit 1; }
