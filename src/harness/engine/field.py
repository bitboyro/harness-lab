"""Field mode: run a task pack against a real target.

The reporting rule that makes field results usable rather than caveated: every
number is expressed as **lift over the parametric baseline**, with Z0 published
alongside it.

Z0 on a real API is not the contamination gate it is on the rig — it is a
measurement of how much the model already knows about that API without being
told anything. "The model already answers 40% of your tasks with no docs; your
MCP server adds 22 points" is a real finding for an API owner, and it turns
contamination from a threat into a number.

Contract: docs/decisions.md G9
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .axes import Variant, preset
from .compute import compute
from .grader import GradeResult, Outcome, bits_over_random, grade, harm_score, selection_accuracy
from .generate import ApiSpec
from .loop import AgentRunner
from .metrics import Validation
from .packaging import PackagingMethod
from .provider import Provider, ProviderConfig
from .taskpack import ReportClass, TaskPack
from .trace import Trace


def _pricing_for(provider: Provider, model: str) -> Any:
    """The rate card, if the provider knows one. Absent is fine; wrong is not."""
    getter = getattr(provider, "pricing", None)
    if not getter:
        return None
    try:
        return getter(model)
    except Exception:  # noqa: BLE001 — an unpriced model still runs, just uncosted
        return None


@dataclass(slots=True)
class ArmResult:
    preset: str
    traces: list[Trace] = field(default_factory=list)
    grades: list[GradeResult] = field(default_factory=list)

    @property
    def graded(self) -> list[GradeResult]:
        """Excludes truncated and ungraded runs.

        Truncation is a budget failure, not a wrong answer; averaging it into a
        success rate would blame the model for a `max_turns` setting.
        """
        return [g for g in self.grades
                if g.outcome not in (Outcome.TRUNCATED, Outcome.UNGRADED)]

    @property
    def success_rate(self) -> float | None:
        graded = self.graded
        if not graded:
            return None
        return sum(1 for g in graded if g.outcome.is_success) / len(graded)

    @property
    def silent_failure_rate(self) -> float | None:
        wrong = [g for g in self.graded if g.outcome is Outcome.FAIL]
        if not wrong:
            return None
        return sum(1 for g in wrong if g.is_silent_failure) / len(wrong)

    @property
    def false_positive_rate(self) -> float | None:
        unanswerable = [g for g in self.grades
                        if g.outcome in (Outcome.CORRECT_REFUSAL, Outcome.FALSE_POSITIVE)]
        if not unanswerable:
            return None
        return sum(1 for g in unanswerable
                   if g.outcome is Outcome.FALSE_POSITIVE) / len(unanswerable)

    @property
    def truncation_rate(self) -> float:
        if not self.grades:
            return 0.0
        return sum(1 for g in self.grades if g.outcome is Outcome.TRUNCATED) / len(self.grades)

    def mean(self, metric: str) -> float | None:
        values = [
            v.value for t in self.traces
            if (v := compute(t).get(metric)) and v.value is not None
        ]
        return sum(values) / len(values) if values else None

    def cost(self, pricing: Any) -> Any:
        """Actual spend across this arm, from real usage.

        Computed from what the provider reported, not from the planner's
        estimate: the estimate cannot know the cache hit rate, and for a
        large-static-prefix arm that is most of the answer.
        """
        from .pricing import Cost, price_run

        total = Cost()
        for trace in self.traces:
            u = trace.usage_total
            run = price_run(
                pricing,
                input_tokens=u.input_tokens,
                cached_input_tokens=u.cached_input_tokens,
                output_tokens=u.output_tokens,
            )
            total = Cost(
                fresh_input_usd=total.fresh_input_usd + run.fresh_input_usd,
                cached_input_usd=total.cached_input_usd + run.cached_input_usd,
                cache_write_usd=total.cache_write_usd + run.cache_write_usd,
                output_usd=total.output_usd + run.output_usd,
                tier=run.tier if run.tier == "long" else total.tier,
            )
        return total

    def cost_per_success(self, pricing: Any) -> float | None:
        """Dollars per successful task.

        The comparable figure across providers — token counts are not, because
        tokenisers differ (§5.6).
        """
        successes = sum(1 for g in self.graded if g.outcome.is_success)
        if not successes:
            return None
        return self.cost(pricing).total_usd / successes

    def cache_hit_rate(self) -> float | None:
        """How much of the prompt was served from cache.

        The number that decides whether a large static prefix is an asset or a
        liability: cached reads are ~10x cheaper, but writing the cache costs
        ~25% *more* than fresh input, so a prefix only pays off once enough runs
        reuse it.
        """
        total = sum(t.usage_total.input_tokens for t in self.traces)
        cached = sum(t.usage_total.cached_input_tokens for t in self.traces)
        return cached / total if total else None


@dataclass
class FieldReport:
    pack_id: str
    report_class: ReportClass
    arms: dict[str, ArmResult] = field(default_factory=dict)
    harm: dict[str, int] = field(default_factory=dict)
    selection: dict[str, tuple[int, int]] = field(default_factory=dict)
    unavailable: dict[str, str] = field(default_factory=dict)
    surface_size: int = 0
    #: Set when the model's rate card is known, so cost can be reported from
    #: real usage rather than an estimate.
    pricing: Any = None

    # ---- the headline ----------------------------------------------------

    def baseline(self) -> float | None:
        """Z0: what the model answers with no access to the API at all."""
        z0 = self.arms.get("Z0")
        return z0.success_rate if z0 else None

    def lift(self, preset_name: str) -> float | None:
        """Percentage points this packaging adds over the parametric baseline."""
        base = self.baseline()
        arm = self.arms.get(preset_name)
        if base is None or arm is None or arm.success_rate is None:
            return None
        return arm.success_rate - base

    def render(self) -> str:
        lines: list[str] = [
            f"{self.pack_id}  [{self.report_class}]",
            "",
        ]

        base = self.baseline()
        if base is None:
            lines += [
                "No Z0 baseline in this run. Field numbers without it are not "
                "interpretable — the model may already know this API.",
                "",
            ]
        else:
            lines += [
                f"Parametric baseline (Z0): {base:.0%} of tasks answered with no "
                "access to the API at all.",
                "",
            ]

        header = f"  {'arm':<10} {'success':>8} {'lift':>7} {'turns':>7} {'arg-valid':>10} {'static':>8}"
        lines += [header, "  " + "-" * (len(header) - 2)]

        for name, arm in self.arms.items():
            success = arm.success_rate
            lift = self.lift(name)
            lines.append(
                f"  {name:<10} "
                f"{_pct(success):>8} "
                f"{_signed(lift):>7} "
                f"{_num(arm.mean('turns')):>7} "
                f"{_pct(arm.mean('argument_validity')):>10} "
                f"{_num(arm.mean('static_context_tokens')):>8}"
            )

        if self.pricing:
            lines += ["", "  cost (from actual usage):"]
            lines.append(
                f"    {'arm':<10} {'total':>10} {'per success':>12} {'cached':>8}"
            )
            for name, arm in self.arms.items():
                cost = arm.cost(self.pricing)
                per = arm.cost_per_success(self.pricing)
                lines.append(
                    f"    {name:<10} "
                    f"{'$' + format(cost.total_usd, '.4f'):>10} "
                    f"{('$' + format(per, '.4f')) if per is not None else 'n/a':>12} "
                    f"{_pct(arm.cache_hit_rate()):>8}"
                )
            if any(a.cost(self.pricing).tier == "long" for a in self.arms.values()):
                lines.append(
                    "    note: an arm crossed into long-context pricing, which "
                    "reprices every token, not just the excess."
                )

        if any(a.truncation_rate for a in self.arms.values()):
            lines += ["", "  truncated (hit max_turns, not graded as wrong):"]
            for name, arm in self.arms.items():
                if arm.truncation_rate:
                    lines.append(f"    {name}: {arm.truncation_rate:.0%}")

        if self.harm:
            lines += ["", "  harm (weighted by tier; includes blocked attempts):"]
            for name, score in sorted(self.harm.items()):
                lines.append(f"    {name}: {score}")

        if self.selection and self.surface_size > 1:
            lines += ["", "  selection accuracy (Bits-over-Random):"]
            for name, (correct, total) in sorted(self.selection.items()):
                bor = bits_over_random(correct, total, self.surface_size)
                raw = f"{correct}/{total}"
                lines.append(
                    f"    {name}: {raw:>7}"
                    + (f"  BoR {bor:.2f} bits" if bor is not None else "")
                )

        if self.unavailable:
            lines += ["", "  not measurable with this pack:"]
            for metric, reason in sorted(self.unavailable.items()):
                lines.append(f"    {metric} — {reason}")

        lines += ["", _footer(self.report_class)]
        return "\n".join(lines)


def _footer(report_class: ReportClass) -> str:
    if report_class is ReportClass.FIELD:
        return (
            "Field result. Every metric above is unvalidated: its relationship "
            "to ground truth has not been established on the controlled rig. "
            "Not poolable with controlled results, across MCP revisions, or "
            "across generated vs. authored skills."
        )
    return (
        "Controlled result. Z0 must be ~0 for these numbers to mean anything; "
        "a non-zero baseline means the domain leaked into pretraining."
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.0%}"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


# ---- execution -----------------------------------------------------------

def run_pack(
    pack: TaskPack,
    spec: ApiSpec,
    provider: Provider,
    config: ProviderConfig,
    *,
    presets: tuple[str, ...],
    base_axes: dict[str, Any],
    method_for: Any,
    repeats: int = 1,
    trace_dir: str | None = None,
    on_run: Any = None,
) -> FieldReport:
    """Run every selected arm over every task in the pack."""
    report = FieldReport(
        pack_id=pack.pack.id,
        report_class=pack.pack.report_class,
        unavailable=pack.unavailable_metrics(),
        surface_size=base_axes.get("surface_size") or len(spec.operations),
        pricing=_pricing_for(provider, config.model),
    )

    for name in presets:
        variant: Variant = preset(name, **base_axes)
        method: PackagingMethod = method_for(name)
        arm = ArmResult(preset=name)
        correct = total = 0
        harm = 0

        for task in pack.tasks:
            for _ in range(repeats):
                runner = AgentRunner(
                    provider=provider, method=method, spec=spec, variant=variant,
                    config=config,
                    forbidden_calls=pack.safety.forbidden_calls + task.forbidden_calls,
                    trace_dir=trace_dir,
                )
                trace = runner.run(task.id, task.prompt)
                result = grade(task, trace)

                arm.traces.append(trace)
                arm.grades.append(result)
                hit, of = selection_accuracy(task, trace)
                correct += hit
                total += of
                harm += harm_score(task, result, trace)

                if on_run:
                    on_run(name, task, trace, result)

        report.arms[name] = arm
        if total:
            report.selection[name] = (correct, total)
        if harm:
            report.harm[name] = harm

    return report
