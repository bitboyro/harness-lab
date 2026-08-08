#!/usr/bin/env bash
# Build the three things a release ships: a wheel, a single-file zipapp, and
# the bundle handed to someone who has no access to this repo.
#
#   ./build.sh            -> dist/
#
# Why a zipapp and not a frozen binary: the D-arms execute agent-written Python
# via `sys.executable`. Under PyInstaller that resolves to the frozen executable
# rather than an interpreter, so those arms break — and break as *failure rows*
# rather than as an error, which is the one failure mode this tool must not
# have. A .pyz is still one file and keeps a real interpreter.
set -euo pipefail

cd "$(dirname "$0")"
SHIV=${SHIV:-$(command -v shiv || echo .venv/bin/shiv)}
VERSION=$(python3 -c "import re,pathlib; print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('src/harness/__init__.py').read_text()).group(1))")
DIST=dist

rm -rf "$DIST"
mkdir -p "$DIST"

echo "==> wheel"
python3 -m pip wheel . --no-deps -w "$DIST" -q

echo "==> single-file app (harness-$VERSION.pyz)"
# shiv, not `python -m zipapp`. pydantic_core is a compiled extension, and
# Python cannot import a .so from inside a zip — a plain zipapp builds fine and
# then dies on first run with ModuleNotFoundError. shiv wraps the same zip with
# a loader that unpacks to ~/.shiv on first execution, so extensions work.
#
# The cost is that the artifact is platform-specific: it carries wheels built
# for the machine that made it. CI builds one per platform; a hand-built .pyz
# only runs where it was built.
"$SHIV" \
    --console-script harness \
    --python "/usr/bin/env python3" \
    --compressed \
    -o "$DIST/harness-$VERSION.pyz" \
    . 2>&1 | grep -v "^ *$" || true

echo "==> bundle (harness-lab-$VERSION.zip)"
BUNDLE=$DIST/.bundle/harness-lab-$VERSION
mkdir -p "$BUNDLE"
cp "$DIST/harness-$VERSION.pyz" "$BUNDLE/harness.pyz"
cp -r examples "$BUNDLE/"
[ -d docs ] && cp -r docs "$BUNDLE/"
for f in README.md CHANGELOG.md LICENSE; do [ -f "$f" ] && cp "$f" "$BUNDLE/"; done
cp -r src/harness/agent_skills "$BUNDLE/agent-skills"
cat > "$BUNDLE/START-HERE.txt" <<EOF
harness-lab $VERSION

Needs Python 3.11+. Nothing to install.

  python3 harness.pyz --version
  python3 harness.pyz lint --demo            # free, no API key
  python3 harness.pyz lint examples/openapi.json

Point it at your own API:

  python3 harness.pyz scaffold https://your-server/mcp -o packs/mine.yaml
  \$EDITOR packs/mine.yaml                    # fill in the TODOs
  export OPENAI_API_KEY=...
  python3 harness.pyz run --pack packs/mine.yaml --probe

Install the agent skills so Claude or Cursor can drive it for you:

  python3 harness.pyz init --agent both

Note: the D-arms execute model-written Python in a temp directory with no
container isolation. Run them somewhere you are happy for that to happen.
EOF
( cd "$DIST/.bundle" && zip -qr "../harness-lab-$VERSION.zip" "harness-lab-$VERSION" )

rm -rf "$DIST/.bundle"
echo
echo "built:"
ls -lh "$DIST" | tail -n +2 | awk '{printf "  %-40s %s\n", $9, $5}'
