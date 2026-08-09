"""Load arm definitions from YAML.

An arm is a partial axis assignment plus optional material bindings. The
shipped ladder lives in ``engine/arms/builtin.yaml``; a run plan may add arms
with ``extends`` / ``materials`` / ``matrix``. Selection of the packaging
method is still ``packaging.resolve(variant)`` — this module never maps names
to classes.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .arms import BUILTIN_YAML
from .axes import AXES, ConfigError, axis_by_name, coerce_axis_value


#: Material slots any method may declare. Binding an unknown slot is a load
#: error, not a silently ignored key.
KNOWN_SLOTS = frozenset({"skill", "helpers", "docs", "target"})


@dataclass(frozen=True, slots=True)
class ArmDef:
    """One named point in axis space, optionally bound to concrete artifacts."""

    name: str
    axes: dict[str, Any]
    materials: dict[str, str] = field(default_factory=dict)
    family: str | None = None
    allow_run_axes: bool = False

    def structural_axes(self) -> dict[str, Any]:
        return dict(self.axes)


def load_arms(
    path: str | Path | None = None,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, ArmDef]:
    """Load builtin arms, then merge plan-declared ``extra`` arms over them."""
    path = Path(path) if path else BUILTIN_YAML
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "arms" not in raw:
        raise ConfigError(f"{path}: expected top-level 'arms' mapping")
    arms = _parse_arm_table(raw["arms"], source=str(path))
    if extra:
        overlay = _parse_arm_table(extra, source="run_plan.arms", base=arms)
        arms = {**arms, **overlay}
    return arms


def builtin_arm_names() -> tuple[str, ...]:
    return tuple(load_arms())


def expand_matrix(name: str, body: dict[str, Any],
                  resolved_axes: dict[str, Any],
                  materials: dict[str, str]) -> list[ArmDef]:
    """Cartesian product of material/target bindings → one ArmDef per cell."""
    matrix = body.get("matrix") or {}
    if not matrix:
        return [ArmDef(
            name=name, axes=resolved_axes, materials=materials,
            family=body.get("family"),
            allow_run_axes=bool(body.get("allow_run_axes", False)),
        )]

    keys = list(matrix)
    # Stem uniqueness — two files sharing a stem would collide in the label.
    for key, values in matrix.items():
        stems = [_stem(v) for v in values]
        if len(stems) != len(set(stems)):
            raise ConfigError(
                f"arm {name!r} matrix.{key}: two values share a file stem; "
                f"labels would collide. Rename one."
            )

    out: list[ArmDef] = []
    for combo in itertools.product(*(matrix[k] for k in keys)):
        bound = dict(materials)
        label_parts: list[str] = []
        for key, value in zip(keys, combo):
            if key not in KNOWN_SLOTS and key not in {a.name for a in AXES}:
                raise ConfigError(
                    f"arm {name!r} matrix key {key!r} is neither a material "
                    f"slot nor an axis"
                )
            if key in KNOWN_SLOTS:
                bound[key] = str(value)
                label_parts.append(f"{key}={_stem(value)}")
            else:
                # Axis swept inside a material matrix — rare but legal.
                resolved_axes = {**resolved_axes, key: coerce_axis_value(key, value)}
                label_parts.append(f"{key}={value}")
        label = f"{name}@" + ",".join(label_parts)
        out.append(ArmDef(
            name=label, axes=dict(resolved_axes), materials=bound,
            family=body.get("family"),
            allow_run_axes=bool(body.get("allow_run_axes", False)),
        ))
    return out


def _parse_arm_table(
    table: dict[str, Any],
    *,
    source: str,
    base: dict[str, ArmDef] | None = None,
) -> dict[str, ArmDef]:
    if not isinstance(table, dict):
        raise ConfigError(f"{source}: arms must be a mapping")
    base = base or {}
    # Two passes so `extends` can forward-reference within the same table.
    pending = dict(table)
    resolved: dict[str, ArmDef] = {}
    progress = True
    while pending and progress:
        progress = False
        for name in list(pending):
            body = pending[name]
            if not isinstance(body, dict):
                raise ConfigError(f"{source}: arm {name!r} must be a mapping")
            parent_name = body.get("extends")
            if parent_name is not None:
                parent = resolved.get(parent_name) or base.get(parent_name)
                if parent is None:
                    if parent_name in pending:
                        continue  # resolve parent first
                    raise ConfigError(
                        f"{source}: arm {name!r} extends unknown arm "
                        f"{parent_name!r}"
                    )
                parent_axes = dict(parent.axes)
                parent_materials = dict(parent.materials)
            else:
                parent_axes, parent_materials = {}, {}

            allow_run = bool(body.get("allow_run_axes", False))
            axes = dict(parent_axes)
            materials = dict(parent_materials)
            for key, value in body.items():
                if key in ("extends", "matrix", "family", "allow_run_axes",
                           "materials"):
                    continue
                _check_axis_key(key, allow_run_axes=allow_run, source=source,
                                arm=name)
                axes[key] = coerce_axis_value(key, value)
            for slot, ref in (body.get("materials") or {}).items():
                if slot not in KNOWN_SLOTS:
                    raise ConfigError(
                        f"{source}: arm {name!r} materials.{slot} is not a "
                        f"known slot ({', '.join(sorted(KNOWN_SLOTS))})"
                    )
                materials[slot] = str(ref)

            for arm in expand_matrix(name, body, axes, materials):
                if arm.name in resolved or arm.name in base:
                    # Overlaying a builtin is intentional for plan arms.
                    pass
                resolved[arm.name] = arm
            del pending[name]
            progress = True

    if pending:
        raise ConfigError(
            f"{source}: could not resolve extends for: "
            f"{', '.join(sorted(pending))}"
        )
    return resolved


def _check_axis_key(key: str, *, allow_run_axes: bool, source: str,
                    arm: str) -> None:
    axis = axis_by_name(key)
    if axis is None:
        raise ConfigError(
            f"{source}: arm {name_escape(arm)} has unknown key {key!r}. "
            f"Axes: {', '.join(a.name for a in AXES)}"
        )
    if not axis.structural and not allow_run_axes:
        raise ConfigError(
            f"{source}: arm {name_escape(arm)} pins non-structural axis "
            f"{key!r}. Affordance/run axes belong on the plan's base (or set "
            f"allow_run_axes: true for a deliberate pin)."
        )


def name_escape(name: str) -> str:
    return repr(name)


def _stem(value: Any) -> str:
    return Path(str(value)).stem


def arms_as_preset_dicts(arms: dict[str, ArmDef]) -> dict[str, dict[str, Any]]:
    """Shape expected by the historical ``_PRESETS`` consumers / frozen test."""
    return {name: dict(arm.axes) for name, arm in arms.items()}
