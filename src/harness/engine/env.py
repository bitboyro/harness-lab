"""Load a local .env file.

Stdlib only — a dotenv parser is not worth a dependency, and keeping the
engine's install surface small matters more here than covering every exotic
shell quoting rule.

Real environment variables always win over the file, so `KEY=x harness probe`
overrides `.env` rather than being silently ignored.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> list[str]:
    """Read `path` into os.environ. Returns the names that were set.

    Names, never values — a caller that wants to report what loaded should not
    have to handle secrets to do it.
    """
    file = Path(path)
    if not file.is_file():
        return []

    loaded: list[str] = []
    for raw in file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not value:
            continue
        if key in os.environ and not override:
            continue
        os.environ[key] = value
        loaded.append(key)
    return loaded


def find_and_load(start: str | Path = ".") -> list[str]:
    """Walk up from `start` looking for a .env, so the CLI works from subdirs."""
    current = Path(start).resolve()
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return load_dotenv(candidate)
        if (directory / ".git").exists():
            break  # stop at the repo root; do not read a parent project's .env
    return []
