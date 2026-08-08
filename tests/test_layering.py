"""The dependency rule, enforced rather than promised.

`engine` must not depend on `experiment`. This is the single most important
structural decision in the plan, and a promise in a document does not survive
contact with a deadline.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "src" / "harness" / "engine"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", sorted(ENGINE.glob("*.py")), ids=lambda p: p.name)
def test_engine_does_not_import_experiment(path: Path) -> None:
    offending = {n for n in _imports(path) if "experiment" in n}
    assert not offending, (
        f"{path.name} imports {offending}. The engine must stay API-agnostic; "
        "the rig is a consumer of the engine, not a peer."
    )


def test_engine_has_no_provider_sdk_dependency() -> None:
    """P0 is offline. A vendor SDK here means the loop leaked into the core."""
    banned = {"openai", "anthropic", "google", "litellm"}
    for path in ENGINE.glob("*.py"):
        hits = {n.split(".")[0] for n in _imports(path)} & banned
        assert not hits, f"{path.name} imports {hits}; providers are adapters, not core"
