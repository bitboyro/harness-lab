#!/usr/bin/env python3
"""Shim — prefer ``harness analyze``. Kept so old invocations keep working."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from harness.deep_analysis import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
