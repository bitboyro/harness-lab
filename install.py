#!/usr/bin/env python3
"""Install harness-lab, and say plainly what is missing if it cannot.

    python3 install.py                      # the wheel next to this file
    python3 install.py --download           # fetch the latest release instead
    python3 install.py harness_lab-*.whl    # or point at one
    python3 install.py --user               # no virtualenv available
    python3 install.py --check              # report only, install nothing

Two ways to get the wheel, because there are two kinds of person running this.
Someone handed the release zip has the wheel already, next to this script, and
should not need credentials or a network to install it. Someone working from
the repo would rather not build first — `--download` pulls the latest release
for them.

`--download` needs the `gh` CLI, authenticated. That is not a convenience: the
repo is private, so the download is authenticated no matter what, and letting
`gh` hold the token means this script never handles one. A token in an argv
string is readable by every process on the machine and tends to end up in shell
history and CI logs, which is how the shell installer this replaced leaked.

Written in deliberately old Python syntax and importing nothing outside the
standard library, because the most common reason this fails is that the
interpreter running it is too old — and a SyntaxError instead of an explanation
is a terrible way to learn that. It must parse on 3.6 to be able to tell a 3.6
user to upgrade.
"""

from __future__ import print_function

import glob
import os
import subprocess
import sys
import tempfile

MINIMUM = (3, 11)
PACKAGE = "harness-lab"
REPO = "bitboyro/harness-lab"


def say(msg=""):
    print(msg)
    sys.stdout.flush()


def fail(msg):
    print("\nerror: %s" % msg, file=sys.stderr)
    return 1


def check_python():
    v = sys.version_info
    got = "%d.%d.%d" % (v[0], v[1], v[2])
    if (v[0], v[1]) < MINIMUM:
        say("  [MISS] python    %s at %s" % (got, sys.executable))
        say("         needs %d.%d or newer" % MINIMUM)
        say("")
        say("  Install a newer Python, then run this script with it:")
        say("      python3.12 %s" % os.path.basename(__file__))
        say("")
        say("  macOS:    brew install python@3.12")
        say("  Debian:   sudo apt install python3.12 python3.12-venv")
        say("  Windows:  https://www.python.org/downloads/")
        return False
    say("  [ok  ] python    %s at %s" % (got, sys.executable))
    return True


def check_pip():
    try:
        import pip  # noqa: F401
    except ImportError:
        say("  [MISS] pip       not importable")
        say("         Debian/Ubuntu: sudo apt install python3-pip")
        say("         or: python3 -m ensurepip --upgrade")
        return False
    say("  [ok  ] pip       present")
    return True


def find_wheel(argv_path):
    """The wheel to install: named on the command line, or beside this file."""
    if argv_path:
        if not os.path.isfile(argv_path):
            return None, "no such file: %s" % argv_path
        return argv_path, None

    here = os.path.dirname(os.path.abspath(__file__))
    for where in (here, os.path.join(here, "dist")):
        found = sorted(glob.glob(os.path.join(where, "harness_lab-*.whl")))
        if found:
            return found[-1], None
    return None, ("no harness_lab-*.whl found next to this script or in "
                  "./dist.\n"
                  "       Either:  python3 %s --download   (needs `gh`, "
                  "authenticated)\n"
                  "       or pass one as an argument, or run ./build.sh first."
                  % os.path.basename(__file__))


def _have(program):
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.isfile(os.path.join(directory, program)):
            return True
    return False


def download_wheel(tag):
    """Fetch a release wheel with `gh`, which already holds the credentials.

    Returns (path, problem). The wheel lands in a temp directory we do not
    clean up: pip has already read it by the time we are done, and leaving it
    means a failed install can be retried without a second download.
    """
    if not _have("gh"):
        return None, (
            "--download needs the GitHub CLI, and `gh` is not on PATH.\n"
            "       macOS:   brew install gh\n"
            "       Debian:  sudo apt install gh\n"
            "       others:  https://cli.github.com\n"
            "       Then:    gh auth login\n"
            "       Or install from a release zip, which needs neither.")

    status = subprocess.call(["gh", "auth", "status"],
                             stdout=_devnull(), stderr=subprocess.STDOUT)
    if status != 0:
        return None, ("`gh` is installed but not logged in. Run:  gh auth login\n"
                      "       %s is private, so the download is authenticated."
                      % REPO)

    target = tempfile.mkdtemp(prefix="harness-lab-")
    cmd = ["gh", "release", "download"]
    if tag:
        cmd.append(tag)
    cmd += ["--repo", REPO, "--pattern", "harness_lab-*.whl", "--dir", target]
    say("\n==> %s" % " ".join(cmd))
    if subprocess.call(cmd) != 0:
        return None, (
            "gh could not download a release wheel (see its output above).\n"
            "       If this says 'release not found', none has been published "
            "yet —\n"
            "       build one locally instead:  ./build.sh")

    found = sorted(glob.glob(os.path.join(target, "harness_lab-*.whl")))
    if not found:
        return None, "the release contains no harness_lab-*.whl"
    return found[-1], None


def _devnull():
    return open(os.devnull, "w")


def _flag_value(flags, name):
    """`--tag=v0.1.0` — the `=` form only, so the arg parser stays trivial."""
    prefix = name + "="
    for flag in flags:
        if flag.startswith(prefix):
            return flag[len(prefix):]
    return None


def in_virtualenv():
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def install(wheel, user, extras):
    target = "%s[%s]" % (wheel, extras) if extras else wheel
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", target]
    # PEP 668 marks system Pythons as externally managed; --user is the
    # sanctioned escape and is what most people actually want here.
    if user and not in_virtualenv():
        cmd.insert(4, "--user")
    say("\n==> %s" % " ".join(cmd))
    return subprocess.call(cmd)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    flags = set(a for a in argv[1:] if a.startswith("-"))

    if "-h" in flags or "--help" in flags:
        say(__doc__)
        return 0

    say("Checking this machine")
    say("")
    ok = check_python()
    if ok:
        ok = check_pip() and ok
    say("")

    if not ok:
        return fail("cannot install until the items marked MISS are fixed.")

    if "--check" in flags:
        say("Checks passed. Re-run without --check to install.")
        return 0

    if any(f == "--download" or f.startswith("--tag=") for f in flags):
        wheel, problem = download_wheel(_flag_value(flags, "--tag"))
    else:
        wheel, problem = find_wheel(args[0] if args else None)
    if problem:
        return fail(problem)
    say("Installing %s" % os.path.basename(wheel))

    if not in_virtualenv() and "--user" not in flags:
        say("")
        say("  note: not in a virtualenv. If pip refuses (PEP 668), either")
        say("        make one:   python3 -m venv .venv && . .venv/bin/activate")
        say("        or re-run:  python3 %s --user" % os.path.basename(__file__))

    extras = "" if "--no-openai" in flags else "openai"
    code = install(wheel, "--user" in flags, extras)
    if code != 0:
        return fail("pip failed with exit code %d (see its output above)." % code)

    # The install is only real if the package answers. Run the CLI's own
    # environment check rather than reimplementing it here — one source of
    # truth for what "ready" means, available forever after, not just today.
    say("\n==> harness doctor")
    doctor = subprocess.call([sys.executable, "-m", "harness", "doctor"])

    script = _console_script()
    say("")
    if script and _on_path("harness"):
        say("Run it as:")
        say("    harness lint --demo")
        say("    %s -m harness lint --demo" % os.path.basename(sys.executable))
    elif script:
        # Installed correctly; PATH simply does not include this environment,
        # which is normal for a virtualenv nobody has activated.
        say("Installed. 'harness' is not on PATH, so use either:")
        say("    %s lint --demo" % script)
        say("    %s -m harness lint --demo" % sys.executable)
        bindir = os.path.dirname(script)
        say("")
        say("To get the short form, put that directory on PATH:")
        say("    export PATH=\"%s:$PATH\"" % bindir)
    else:
        say("Installed, but the 'harness' launcher was not found. Use:")
        say("    %s -m harness lint --demo" % sys.executable)
    return doctor


def _console_script():
    """The `harness` launcher inside the environment we just installed into."""
    bindir = os.path.dirname(os.path.abspath(sys.executable))
    for name in ("harness", "harness.exe"):
        candidate = os.path.join(bindir, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _on_path(name):
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return True
    return False


if __name__ == "__main__":
    sys.exit(main(sys.argv))
