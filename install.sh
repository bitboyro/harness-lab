#!/usr/bin/env sh
# harness-lab installer.
#
#   curl -fsSL <raw-url>/install.sh | sh
#   curl -fsSL <raw-url>/install.sh | sh -s -- --ref v0.1.0
#
# The repo is private, so this needs a token with read access:
#
#   export GITHUB_TOKEN=ghp_...
#
# Customers who should not have repo access get the release bundle instead —
# one .pyz plus docs, no install and no GitHub account. See build.sh.
#
# Deliberately POSIX sh, not bash: this is piped into whatever /bin/sh is on a
# machine we have never seen, and Debian's is dash.
set -eu

REPO="${HARNESS_REPO:-bitboyro/harness-lab}"
REF="main"

while [ $# -gt 0 ]; do
    case "$1" in
        --ref) REF="$2"; shift 2 ;;
        --ref=*) REF="${1#*=}"; shift ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# --- interpreter ------------------------------------------------------------
# uv brings its own Python if it has to, so this check is about giving a clear
# message now rather than a confusing one later.
python_ok=false
for py in python3.13 python3.12 python3.11 python3; do
    if command -v "$py" >/dev/null 2>&1; then
        if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            python_ok=true
            break
        fi
    fi
done

# --- uv ---------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    say "==> installing uv"
    curl -fsSL https://astral.sh/uv/install.sh | sh || die "could not install uv"
    # The installer puts it here and edits a shell profile this process will
    # never re-read, so PATH is fixed up by hand for the rest of this script.
    PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    export PATH
fi
command -v uv >/dev/null 2>&1 || die "uv is not on PATH — open a new shell and re-run"

if [ "$python_ok" = false ]; then
    say "==> no Python 3.11+ found; letting uv fetch one"
    uv python install 3.12 || die "could not install a Python"
fi

# --- harness ----------------------------------------------------------------
if [ -n "${GITHUB_TOKEN:-}" ]; then
    SOURCE="git+https://x-access-token:${GITHUB_TOKEN}@github.com/${REPO}.git@${REF}"
else
    # No token: assume SSH keys are configured. Fails clearly if not.
    SOURCE="git+ssh://git@github.com/${REPO}.git@${REF}"
    say "note: no GITHUB_TOKEN set — trying SSH"
fi

say "==> installing harness-lab (${REF})"
uv tool install --force --python 3.12 --with openai "$SOURCE" \
    || die "install failed. For a private repo, set GITHUB_TOKEN or configure SSH access."

# --- confirm ----------------------------------------------------------------
if command -v harness >/dev/null 2>&1; then
    say ""
    say "installed: $(harness --version)"
else
    say ""
    say "installed, but 'harness' is not on PATH yet."
    say "Add this to your shell profile:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

cat <<'EOF'

Next:
  harness lint --demo                  free, no API key
  harness init --agent both            install the agent skills here
  harness scaffold <url> -o pack.yaml  draft a pack for your own API

Note: the D-arms execute model-written Python in a temp directory with no
container isolation. Run them somewhere you are happy for that to happen.
EOF
