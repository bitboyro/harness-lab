"""What is missing, and what it stops you doing.

Every check answers the same two questions: is it there, and what breaks if it
is not. A checklist that only prints "curl: missing" makes a reader guess
whether that matters; the C arms failing at run 40 of 400 is a much worse way
to find out.

Nothing here imports the provider stack or touches the network. `doctor` has to
work on a broken install — that is the only time anyone runs it.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

#: Below this, `enum.StrEnum` and other 3.11 syntax is unavailable and the
#: package will not even import.
MINIMUM_PYTHON = (3, 11)

OK, WARN, MISSING = "ok", "warn", "missing"

_MARK = {OK: "ok  ", WARN: "warn", MISSING: "MISS"}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    detail: str
    #: What stops working. Empty when nothing does.
    blocks: str = ""

    @property
    def fatal(self) -> bool:
        return self.status is MISSING or self.status == MISSING


def _python() -> Check:
    v = sys.version_info
    got = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < MINIMUM_PYTHON:
        return Check("python", MISSING, got,
                     f"everything — harness needs "
                     f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}+")
    return Check("python", OK, f"{got} ({sys.executable})")


def _import(module: str, *, required: bool, blocks: str, hint: str) -> Check:
    try:
        mod = __import__(module)
    except ImportError:
        return Check(module, MISSING if required else WARN, hint, blocks)
    version = getattr(mod, "__version__", "") or ""
    return Check(module, OK, version)


def _binary(name: str, *, blocks: str) -> Check:
    path = shutil.which(name)
    return (Check(name, OK, path) if path
            else Check(name, WARN, "not on PATH", blocks))


def _api_key() -> Check:
    # Name only. Printing a key's value into a terminal scrollback is how a
    # credential ends up in a screenshot.
    for env in ("OPENAI_API_KEY",):
        if os.environ.get(env):
            return Check("api key", OK, f"{env} is set")
    return Check("api key", WARN, "no OPENAI_API_KEY",
                 "any run that calls a model. `lint` does not need one")


def _disk() -> Check:
    try:
        free = shutil.disk_usage(os.getcwd()).free
    except OSError as e:  # noqa: BLE001 — an unreadable cwd is worth reporting
        return Check("disk", WARN, str(e), "trace capture")
    gb = free / 2**30
    if gb < 5:
        return Check("disk", WARN, f"{gb:.1f} GB free",
                     "a full matrix — traces are ~900 KB each, and `run` "
                     "refuses to start without 5 GB of headroom")
    return Check("disk", OK, f"{gb:.1f} GB free")


def _harness() -> Check:
    try:
        from . import __version__
        return Check("harness", OK, f"{__version__} ({os.path.dirname(__file__)})")
    except Exception as e:  # noqa: BLE001 — a broken install is the point
        return Check("harness", MISSING, str(e), "everything")


def run() -> list[Check]:
    """Every check, in the order a reader should care about them."""
    return [
        _python(),
        _harness(),
        _import("pydantic", required=True,
                blocks="everything — task packs will not load",
                hint="pip install pydantic>=2.6"),
        _import("yaml", required=True,
                blocks="everything — task packs are YAML",
                hint="pip install pyyaml>=6.0"),
        _import("openai", required=False,
                blocks="any run that calls a model. `lint` still works",
                hint="pip install 'harness-lab[openai]'"),
        _api_key(),
        _binary("curl", blocks="the C arms (docs + shell), which shell out to it"),
        _binary("git", blocks="authored-skill provenance — the -auth arms "
                              "record 'uncommitted' without it"),
        _disk(),
    ]


def render(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = []
    for c in checks:
        lines.append(f"  [{_MARK[c.status]}] {c.name:<{width}}  {c.detail}")
        if c.blocks:
            lines.append(f"         {' ' * width}  ↳ blocks: {c.blocks}")

    missing = [c for c in checks if c.status == MISSING]
    warned = [c for c in checks if c.status == WARN]

    lines.append("")
    if missing:
        lines.append(f"{len(missing)} required item(s) missing — harness will "
                     f"not run until they are fixed.")
    elif warned:
        lines.append(f"Ready. {len(warned)} optional item(s) missing; each "
                     f"blocks only what is listed above.")
    else:
        lines.append("Ready.")
    return "\n".join(lines)
