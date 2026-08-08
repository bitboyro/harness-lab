#!/usr/bin/env bash
# Build what a release ships: one wheel, and one bundle for someone who has no
# access to this repo.
#
#   ./build.sh            -> dist/
#
# Only a wheel. An earlier version also produced a self-contained .pyz via shiv,
# on the theory that one downloadable file beats an install step. That does not
# survive contact with native dependencies: pydantic_core ships a compiled
# extension, so the bundle inherits its tag, and a .pyz built on CPython 3.13
# for macOS/arm64 fails on 3.12 — same machine, same OS — with `ImportError:
# module 'harness' has no attribute 'cli'`. That is one artifact per OS *per
# Python minor version*, each failing unhelpfully when a user picks wrong.
#
# The wheel is `py3-none-any`: one file, every OS, every Python 3.11+. pip
# resolves the native dependencies per machine, which is the job pip is good at.
set -euo pipefail

cd "$(dirname "$0")"
VERSION=$(python3 -c "import re,pathlib; print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('src/harness/__init__.py').read_text()).group(1))")
DIST=dist

rm -rf "$DIST"
mkdir -p "$DIST"

echo "==> wheel"
python3 -m pip wheel . --no-deps -w "$DIST" -q

echo "==> bundle (harness-lab-$VERSION.zip)"
BUNDLE=$DIST/.bundle/harness-lab-$VERSION
mkdir -p "$BUNDLE"
cp "$DIST"/harness_lab-*.whl "$BUNDLE/"
cp install.py "$BUNDLE/"
cp -r examples "$BUNDLE/"
[ -d docs ] && cp -r docs "$BUNDLE/"

# A real result, at the same path the docs use, so `harness report
# results/auth-smoke` is copy-pasteable for someone who has installed nothing
# else and spent nothing. 464 KB, and it is the only honest way to show what
# the output looks like without shipping a screenshot that renderer changes
# would silently falsify.
mkdir -p "$BUNDLE/results"
cp -r results/auth-smoke "$BUNDLE/results/"
# No ROADMAP and no reference/ contracts: both live under archive/, which is
# gitignored and does not ship. `cp -r docs` is therefore already correct — it
# copies only the five reader-facing guides.
for f in README.md CHANGELOG.md LICENSE; do
    [ -f "$f" ] && cp "$f" "$BUNDLE/"
done

cat > "$BUNDLE/START-HERE.txt" <<EOF
harness-lab $VERSION

Needs Python 3.11 or newer. Nothing else.

  python3 install.py --check     # what is missing, and what each thing blocks
  python3 install.py             # install the wheel next to this file

Then either form works, and there is no third:

  harness lint --demo
  python3 -m harness lint --demo

See what a finished run looks like, without spending anything:

  harness report results/auth-smoke
  harness transcript results/auth-smoke/traces

Point it at your own API:

  harness scaffold https://your-server/mcp -o packs/mine.yaml
  \$EDITOR packs/mine.yaml        # fill in the TODOs
  export OPENAI_API_KEY=...
  harness run --pack packs/mine.yaml --probe

Let your own coding agent drive it:

  harness init --agent claude     # or cursor, or both

Anything unclear about the environment:

  harness doctor

Note: the D arms execute model-written Python in a temp directory with no
container isolation. Run them somewhere you are happy for that to happen;
--presets without D1/D2 avoids it entirely.
EOF

( cd "$DIST/.bundle" && zip -qr "../harness-lab-$VERSION.zip" "harness-lab-$VERSION" )
rm -rf "$DIST/.bundle"

echo
echo "built:"
ls -lh "$DIST" | tail -n +2 | awk '{printf "  %-42s %s\n", $9, $5}'
