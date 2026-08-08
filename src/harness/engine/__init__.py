"""Engine: the API-agnostic core.

The engine must not depend on ``harness.experiment``. The controlled rig is a
consumer of the engine through the same task-pack interface a field user gets —
if the rig ever needs an engine feature no field user could reach, that is a
design bug, not a shortcut.

Enforced by ``tests/test_layering.py``.
"""

from . import axes, lint, metrics, packaging, planner, provider, taskpack

__all__ = ["axes", "lint", "metrics", "packaging", "planner", "provider", "taskpack"]
