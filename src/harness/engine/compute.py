"""Gold-free metric computation.

Everything here works on any API, because none of it needs to know the right
answer. That is what makes field mode possible — and why these are the metrics
the controlled rig exists to validate.

Every value is returned with its validation status attached, so a report cannot
quietly present an unvalidated number as an established one.

Contract: archive/reference/packaging-axes.md#metric-validation
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .metrics import Validation, get
from .trace import Trace


@dataclass(frozen=True, slots=True)
class MetricValue:
    name: str
    value: float | int | None
    validation: Validation
    #: Why the value is None, when it is. A metric that could not be computed is
    #: different from one that computed to zero, and reports must not merge them.
    unavailable_reason: str | None = None

    def render(self) -> str:
        if self.value is None:
            return f"{self.name}: n/a ({self.unavailable_reason})"
        flag = "" if self.validation is Validation.VALIDATED_CONTROLLED else f" [{self.validation}]"
        value = f"{self.value:.3f}" if isinstance(self.value, float) else str(self.value)
        return f"{self.name}: {value}{flag}"


def _mv(name: str, value: float | int | None, reason: str | None = None) -> MetricValue:
    return MetricValue(name, value, get(name).validation, reason)


def compute(trace: Trace) -> dict[str, MetricValue]:
    """All gold-free metrics for one run."""
    calls = trace.calls
    usage = trace.usage_total

    out: dict[str, MetricValue] = {}

    def put(m: MetricValue) -> None:
        out[m.name] = m

    put(_mv("static_context_tokens", trace.cost.static_tokens))
    put(_mv("peak_context_tokens", _peak_context(trace)))
    put(_mv("turns", len(trace.turns)))
    put(_mv("wall_clock_seconds", round(trace.wall_clock_seconds, 3)))

    # --- argument validity -------------------------------------------------
    graded = [c for c in calls if c.result.status is not None and not c.forbidden]
    if graded:
        bad = sum(1 for c in graded if c.is_argument_error)
        put(_mv("argument_validity", 1 - bad / len(graded)))
    else:
        put(_mv("argument_validity", None, "no call returned a status code"))

    # --- hallucinated endpoints -------------------------------------------
    checkable = [c for c in calls if c.known_operation is not None]
    if checkable:
        put(_mv("hallucinated_endpoints",
                sum(1 for c in checkable if c.known_operation is False)))
    else:
        put(_mv("hallucinated_endpoints", None,
                "executor cannot tell which operations exist"))

    # --- redundancy --------------------------------------------------------
    if calls:
        counts = Counter(c.signature for c in calls)
        put(_mv("redundant_calls", sum(n - 1 for n in counts.values() if n > 1)))
    else:
        put(_mv("redundant_calls", 0))

    # --- discovery overhead ------------------------------------------------
    put(_mv("discovery_overhead", _discovery_overhead(trace)))

    # --- wasted calls ------------------------------------------------------
    if trace.final_answer is None:
        put(_mv("wasted_calls", None, "no final answer to attribute results to"))
    else:
        put(_mv("wasted_calls", _wasted_calls(trace)))

    # --- payload efficiency ------------------------------------------------
    put(_mv("payload_efficiency", _payload_efficiency(trace)))

    # --- error recovery (G4) ----------------------------------------------
    errors = [c for c in calls if c.is_client_error]
    if errors:
        put(_mv("error_recovery_rate", _error_recovery_rate(trace)))
    else:
        put(_mv("error_recovery_rate", None, "no 4xx responses in this run"))

    put(_mv("turns_to_first_productive_call", _turns_to_first_productive(trace)))

    # --- safety signal without a state differ ------------------------------
    put(_mv("forbidden_call_rate",
            sum(1 for c in calls if c.forbidden) / len(calls) if calls else 0.0))

    # --- cost --------------------------------------------------------------
    put(_mv("cost_usd", None, "priced by the reporter, which knows the model"))
    out["_usage"] = MetricValue("_usage", usage.input_tokens + usage.output_tokens,
                                Validation.UNVALIDATED)
    return out


# ---- helpers -------------------------------------------------------------

def _peak_context(trace: Trace) -> int:
    return max((t.usage.input_tokens for t in trace.turns), default=0)


def _discovery_overhead(trace: Trace) -> int:
    """Calls made before the first one that returned usable data.

    A discovery arm pays this by design; the question is whether it earns it
    back. Errors and blocked calls do not count as productive.
    """
    for i, c in enumerate(trace.calls):
        if not c.forbidden and c.result.error is None and not c.is_client_error:
            return i
    return len(trace.calls)


def _turns_to_first_productive(trace: Trace) -> int | None:
    for c in trace.calls:
        if not c.forbidden and c.result.error is None and not c.is_client_error:
            return c.turn
    return None


def _wasted_calls(trace: Trace) -> int:
    """Responses whose content never surfaces in the final answer.

    A deliberately crude containment check: a stricter definition needs the
    grader, and this must stay gold-free to work in the field.
    """
    answer = (trace.final_answer or "").lower()
    wasted = 0
    for c in trace.calls:
        body = str(c.result.body or "")
        tokens = {t for t in _words(body) if len(t) > 3}
        if tokens and not any(t in answer for t in tokens):
            wasted += 1
    return wasted


def _payload_efficiency(trace: Trace) -> float | None:
    answer = (trace.final_answer or "").lower()
    if not answer:
        return None
    returned = used = 0
    for c in trace.calls:
        body = str(c.result.body or "")
        words = [w for w in _words(body) if len(w) > 3]
        returned += len(words)
        used += sum(1 for w in words if w in answer)
    return used / returned if returned else None


def _error_recovery_rate(trace: Trace) -> float:
    """Fraction of 4xx responses followed by a corrected retry within 2 turns.

    The headline metric for the error-affordance sweep: it is the mechanism by
    which better error messages would beat a skill. "Corrected" means the same
    operation, different arguments, and no error the second time.
    """
    recovered = total = 0
    for i, c in enumerate(trace.calls):
        if not c.is_client_error:
            continue
        total += 1
        for follow in trace.calls[i + 1:]:
            if follow.turn > c.turn + 2:
                break
            same_target = (follow.call.tool, follow.call.path) == (c.call.tool, c.call.path)
            if same_target and follow.call.args != c.call.args and not follow.is_client_error:
                recovered += 1
                break
    return recovered / total if total else 0.0


def _words(text: str) -> list[str]:
    import re
    return re.findall(r"[a-z0-9_]+", text.lower())


def report_footer(values: dict[str, MetricValue]) -> str:
    """Printed under every report. States what the reader is looking at."""
    real = [v for v in values.values() if not v.name.startswith("_")]
    unvalidated = sum(1 for v in real if v.validation is Validation.UNVALIDATED)
    if not real:
        return "No metrics computed."
    if unvalidated == len(real):
        return (
            f"All {len(real)} metrics are unvalidated: their relationship to "
            "ground truth has not been established on the controlled rig. Treat "
            "them as mechanism descriptions, not as evidence of quality."
        )
    return (
        f"{len(real) - unvalidated} of {len(real)} metrics are validated against "
        "the controlled rig; the rest are labelled unvalidated inline."
    )
