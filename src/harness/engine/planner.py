"""Run plan: matrix selection and cost estimation.

A run is a *declared subset* with a stated rationale — never the full cross
product. The engine enumerates; the run plan selects. Validity comes from which
cells are compared, not from restricting what the tool can express.

No total budget is committed. Spend is gated per phase, and nothing executes
until a human has seen the projected cost.

Contract: archive/reference/packaging-axes.md#matrix-selection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .axes import ConfigError, Variant, preset
from .provider import Provider

#: Reasoning effort is the dominant variance source in run cost: high effort can
#: push output from ~2k to ~20k tokens. Estimating with a flat output size is how
#: a matrix quietly costs 10x its estimate.
_REASONING_MULTIPLIER = {
    "none": 1.0,
    "minimal": 1.2,
    "low": 2.0,
    "medium": 5.0,
    "high": 10.0,
}


@dataclass(frozen=True, slots=True)
class Contrast:
    """A comparison the plan intends to make."""

    presets: tuple[str, str]
    hypothesis: str | None = None

    def pooling_error(self, variants: dict[str, Variant]) -> str | None:
        """Whether these two cells describe different worlds.

        Averaging across an MCP revision boundary, a skill-authorship boundary,
        or a model boundary produces a number that means nothing. The planner
        refuses rather than reporting it.
        """
        a, b = (variants.get(p) for p in self.presets)
        if a is None or b is None:
            return None
        if a.pool_key == b.pool_key:
            return None
        labels = ("mcp_revision", "skill authorship", "model")
        differing = [
            lab for lab, x, y in zip(labels, a.pool_key, b.pool_key) if x != y
        ]
        return (
            f"contrast {self.presets[0]} vs {self.presets[1]} crosses "
            f"{' and '.join(differing)}. Results are never pooled across these — "
            "compare within, then report the difference separately."
        )


@dataclass(frozen=True, slots=True)
class CostEstimate:
    runs: int
    projected_usd: float
    input_tokens: int
    output_tokens: int
    assumptions: str

    def render(self) -> str:
        return (
            f"  runs:      {self.runs:,}\n"
            f"  input:     ~{self.input_tokens:,} tokens\n"
            f"  output:    ~{self.output_tokens:,} tokens\n"
            f"  projected: ~${self.projected_usd:,.2f}\n"
            f"  {self.assumptions}"
        )


class BudgetNotApproved(RuntimeError):
    """A matrix that has not been shown to a human and approved."""


@dataclass
class RunPlan:
    id: str
    rationale: str
    base: dict[str, Any]
    presets: tuple[str, ...]
    task_count: int
    confirmatory: tuple[Contrast, ...] = ()
    exploratory: tuple[Contrast, ...] = ()
    exclude: tuple[dict[str, Any], ...] = ()
    #: Plan-declared arms merged over builtins (extends / materials / matrix).
    arms: dict[str, Any] = field(default_factory=dict)
    #: ``{generate: {...}}`` or ``{pack: path}``. Empty → use task_count only.
    tasks: dict[str, Any] = field(default_factory=dict)
    #: Axis sweep block. Expanded by the CLI / Phase 4; stored here as declared.
    sweep: dict[str, Any] = field(default_factory=dict)
    #: ``{max_usd, calibrate_from}``. Cap is hard; calibration is optional.
    budget: dict[str, Any] = field(default_factory=dict)
    #: Path the plan was loaded from, for approval digests and the manifest.
    path: str | None = field(default=None, compare=False)
    #: Set only by an explicit human approval step.
    approved: bool = field(default=False, compare=False)

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ConfigError(
                f"run plan {self.id!r} has no rationale. A matrix with no stated "
                "reason is how a run becomes unanalysable after the fact."
            )
        if not self.presets:
            raise ConfigError(f"run plan {self.id!r} selects no presets")
        if self.arms:
            from .axes import register_plan_arms
            register_plan_arms(self.arms)

    def variants(self) -> dict[str, Variant]:
        """Materialise every selected cell. Raises on an invalid assignment."""
        # Coerce string axis values from YAML into typed enums.
        from .axes import axis_by_name, coerce_axis_value
        base: dict[str, Any] = {}
        for key, value in self.base.items():
            if axis_by_name(key) is not None:
                base[key] = coerce_axis_value(key, value)
            else:
                base[key] = value
        return {name: preset(name, **base) for name in self.presets}

    def digest(self) -> str:
        """Content address of the resolved plan — approval is keyed on this."""
        import hashlib
        import json
        payload = {
            "id": self.id,
            "rationale": self.rationale,
            "base": self.base,
            "presets": list(self.presets),
            "task_count": self.task_count,
            "arms": self.arms,
            "tasks": self.tasks,
            "sweep": self.sweep,
            "budget": self.budget,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

    @property
    def max_usd(self) -> float | None:
        raw = self.budget.get("max_usd")
        return float(raw) if raw is not None else None

    def validate_contrasts(self) -> None:
        variants = self.variants()
        problems = [
            err
            for c in (*self.confirmatory, *self.exploratory)
            if (err := c.pooling_error(variants))
        ]
        if problems:
            raise ConfigError("; ".join(problems))

    def require_preregistration(self) -> None:
        """Publishable runs need the confirmatory/exploratory split up front.

        Declared after the fact, every result is confirmatory and every
        correction is optional. Declared before, the distinction means
        something.
        """
        if not self.confirmatory:
            raise ConfigError(
                f"run plan {self.id!r} declares no confirmatory contrasts. "
                "Pre-register which comparisons are confirmatory (corrected) and "
                "which are exploratory (labelled, uncorrected) before running."
            )

    def estimate(
        self,
        provider: Provider,
        *,
        avg_input_tokens: int = 32_000,
        avg_output_tokens: int = 2_000,
    ) -> CostEstimate:
        variants = self.variants()
        runs = sum(v.repeats for v in variants.values()) * self.task_count

        effort = str(self.base.get("reasoning_effort", "medium"))
        mult = _REASONING_MULTIPLIER.get(effort, 5.0)
        out_per_run = int(avg_output_tokens * mult)

        total_in = runs * avg_input_tokens
        total_out = runs * out_per_run

        model = str(self.base.get("model", ""))
        in_price, out_price = provider.price_per_mtok(model)
        usd = (total_in / 1e6) * in_price + (total_out / 1e6) * out_price

        return CostEstimate(
            runs=runs,
            projected_usd=usd,
            input_tokens=total_in,
            output_tokens=total_out,
            assumptions=(
                f"assumes {avg_input_tokens:,} in / {avg_output_tokens:,} out per "
                f"run at reasoning_effort={effort!r} (x{mult:g} output). "
                "Batch discounts do not apply — the loop needs each result "
                "before the next turn."
            ),
        )

    def approve(self, estimate: CostEstimate, *, persist: bool = False) -> None:
        """Record that a human has seen the projected cost.

        Persistence is opt-in: the CLI passes ``persist=True`` so
        ``harness run --plan`` can find the approval later. In-process tests
        keep the old in-memory behaviour and must not write ``.harness/``.
        """
        self.approved = True
        self._approved_for = estimate.runs  # type: ignore[attr-defined]
        if persist:
            persist_approval(self, estimate)

    def require_approval(self, estimate: CostEstimate) -> None:
        if self.is_approved(estimate):
            self.approved = True
            self._approved_for = estimate.runs  # type: ignore[attr-defined]
            return
        if not self.approved:
            raise BudgetNotApproved(
                f"run plan {self.id!r} projects ~${estimate.projected_usd:,.2f} "
                f"across {estimate.runs:,} runs and has not been approved. "
                "Run `harness plan --approve` first, or pass --yes."
            )
        if getattr(self, "_approved_for", None) != estimate.runs:
            raise BudgetNotApproved(
                f"run plan {self.id!r} was approved for a different matrix size. "
                "Re-approve after changing the plan."
            )

    def is_approved(self, estimate: CostEstimate) -> bool:
        """Whether `.harness/approved.json` covers this digest + run count."""
        record = load_approvals().get(self.digest())
        if not record:
            return False
        return int(record.get("runs", -1)) == estimate.runs


_APPROVAL_PATH = Path(".harness/approved.json")


def persist_approval(plan: RunPlan, estimate: CostEstimate,
                     path: Path | None = None) -> None:
    """Write approval keyed on ``(plan digest, estimate.runs)``."""
    import json
    target = path or _APPROVAL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    data = load_approvals(target)
    data[plan.digest()] = {
        "plan_id": plan.id,
        "runs": estimate.runs,
        "projected_usd": estimate.projected_usd,
        "path": plan.path,
    }
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_approvals(path: Path | None = None) -> dict[str, Any]:
    import json
    target = path or _APPROVAL_PATH
    if not target.is_file():
        return {}
    try:
        raw = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_plan(path: str | Path) -> RunPlan:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "run_plan" not in raw:
        raise ConfigError(f"{path}: expected a top-level 'run_plan' mapping")
    rp = raw["run_plan"]

    def contrasts(key: str) -> tuple[Contrast, ...]:
        return tuple(
            Contrast(presets=tuple(c["contrast"]), hypothesis=c.get("hypothesis"))
            for c in rp.get(key, [])
        )

    tasks = dict(rp.get("tasks") or {})
    task_count = int(rp.get("task_count", 1))
    # tasks.generate.cores drives the controlled world size; prefer it over a
    # bare task_count when both appear, so a plan file is self-describing.
    if "generate" in tasks:
        gen = tasks["generate"] or {}
        cores = int(gen.get("cores", 0) or 0)
        # Rough: each core yields ~5 matched tasks in the controlled pack.
        if cores and "task_count" not in rp:
            task_count = cores * 5

    return RunPlan(
        id=rp["id"],
        rationale=rp.get("rationale", ""),
        base=rp.get("base", {}),
        presets=tuple(rp.get("include", {}).get("presets", [])),
        task_count=task_count,
        confirmatory=contrasts("confirmatory"),
        exploratory=contrasts("exploratory"),
        exclude=tuple(rp.get("exclude", [])),
        arms=dict(rp.get("arms") or {}),
        tasks=tasks,
        sweep=dict(rp.get("sweep") or {}),
        budget=dict(rp.get("budget") or {}),
        path=str(path),
    )
