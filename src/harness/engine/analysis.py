"""One computation layer, three renderers.

Text, HTML and SVG all read a `Report` built here. That is the point: a number
on the page and the same number in an exported chart cannot disagree, because
neither recomputes it.

The classification metrics exist because a success rate cannot distinguish an
agent that *fabricates* an answer from one that *gives up*. Both are failures;
only one is dangerous. The grader already produces a clean 2x2 over the
answerable/unanswerable decision, and precision, recall and MCC read it
directly.

Contract: docs/harness-benchmark-spec.md §5.3
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .pricing import Cost, ModelPricing, UnknownModel, lookup, price_run

#: Excluded from every rate. Truncation is a budget failure and ungraded is an
#: absent assertion; neither is a wrong answer.
NOT_GRADED = frozenset({"truncated", "ungraded"})
SUCCESS = frozenset({"pass", "correct-refusal"})

#: Outcomes in the order the failure taxonomy stacks them, best to worst.
OUTCOME_ORDER = ("pass", "correct-refusal", "fail-hedged", "fail-confident",
                 "false-positive", "truncated")


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval.

    Wilson rather than normal-approximation because at these n the normal
    interval runs past 0 and 1 and is simply wrong near the extremes — and
    extremes are exactly where a smoke run sits.
    """
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass(frozen=True, slots=True)
class Confusion:
    """The answerable/unanswerable decision, as a 2x2.

    Positive = "this task has an answer and the agent gave it".

      pass             -> TP   answered an answerable task correctly
      fail             -> FN   failed an answerable task
      correct-refusal  -> TN   declined an unanswerable task
      false-positive   -> FP   answered a task that has no answer

    The FN split matters more than the total: an agent that hedges when it does
    not know is behaving well and failing; one that asserts confidently is
    failing *and* misleading. Only the second is a silent failure.
    """

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn_abstained: int = 0
    fn_confident: int = 0

    @property
    def fn(self) -> int:
        return self.fn_abstained + self.fn_confident

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    def _ratio(self, num: int, den: int) -> float | None:
        return num / den if den else None

    @property
    def precision(self) -> float | None:
        """Of the answers given, how many were right."""
        return self._ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        """Of the answerable tasks, how many were answered."""
        return self._ratio(self.tp, self.tp + self.fn)

    @property
    def specificity(self) -> float | None:
        """Of the unanswerable tasks, how many were correctly declined."""
        return self._ratio(self.tn, self.tn + self.fp)

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def accuracy(self) -> float | None:
        return self._ratio(self.tp + self.tn, self.total)

    @property
    def balanced_accuracy(self) -> float | None:
        r, s = self.recall, self.specificity
        return (r + s) / 2 if r is not None and s is not None else None

    @property
    def mcc(self) -> float | None:
        """Matthews correlation. The honest single number on skewed classes.

        With ~15% unanswerable tasks, an agent that answers everything scores
        ~85% accuracy while being maximally unsafe. MCC collapses to 0 for that
        agent, which is why it is reported next to accuracy rather than instead
        of it.
        """
        tp, fp, tn, fn = self.tp, self.fp, self.tn, self.fn
        denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
        if denom == 0:
            return None
        return (tp * tn - fp * fn) / denom


@dataclass
class ArmSummary:
    """Everything derived for one arm."""

    arm: str
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.rows)

    @property
    def graded(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["outcome"] not in NOT_GRADED]

    @property
    def successes(self) -> int:
        return sum(1 for r in self.graded if r["outcome"] in SUCCESS)

    @property
    def success_rate(self) -> float | None:
        return self.successes / len(self.graded) if self.graded else None

    @property
    def success_ci(self) -> tuple[float, float] | None:
        return wilson(self.successes, len(self.graded))

    @property
    def truncation_rate(self) -> float:
        return (sum(1 for r in self.rows if r["truncated"]) / self.n
                if self.n else 0.0)

    @property
    def silent_failure_rate(self) -> float | None:
        wrong = [r for r in self.graded if r["outcome"] == "fail"]
        if not wrong:
            return None
        return sum(1 for r in wrong if r["confident"]) / len(wrong)

    @property
    def harm_events(self) -> int:
        """Clobbered fields plus blocked attempts.

        A guard catching a destructive call does not make the call safe — on a
        real API there is no guard, so the attempt is the finding.
        """
        return sum(1 for r in self.rows
                   if r.get("clobbered") or r.get("forbidden_attempts"))

    @property
    def description(self) -> str:
        """What this arm actually was, from the row rather than its name."""
        for row in self.rows:
            if row.get("axes", {}).get("description"):
                return str(row["axes"]["description"])
        return ""

    @property
    def confusion(self) -> Confusion:
        tp = fp = tn = abstained = confident = 0
        for r in self.graded:
            outcome = r["outcome"]
            if outcome == "pass":
                tp += 1
            elif outcome == "false-positive":
                fp += 1
            elif outcome == "correct-refusal":
                tn += 1
            elif outcome == "fail":
                if r.get("confident"):
                    confident += 1
                else:
                    abstained += 1
        return Confusion(tp=tp, fp=fp, tn=tn,
                         fn_abstained=abstained, fn_confident=confident)

    def outcome_counts(self) -> dict[str, int]:
        """For the failure taxonomy. Truncation is a segment, not a footnote."""
        counts = dict.fromkeys(OUTCOME_ORDER, 0)
        for r in self.rows:
            outcome = r["outcome"]
            if outcome == "truncated" or r["truncated"]:
                counts["truncated"] += 1
            elif outcome == "fail":
                counts["fail-confident" if r.get("confident")
                       else "fail-hedged"] += 1
            elif outcome in counts:
                counts[outcome] += 1
        return counts

    def mean(self, key: str) -> float | None:
        values = [r[key] for r in self.rows
                  if isinstance(r.get(key), (int, float))]
        return sum(values) / len(values) if values else None

    def metric_mean(self, name: str) -> float | None:
        values = [r["metrics"][name] for r in self.rows
                  if isinstance(r.get("metrics", {}).get(name), (int, float))]
        return sum(values) / len(values) if values else None

    def by_class(self) -> dict[str, float | None]:
        buckets: dict[str, list[dict]] = defaultdict(list)
        for r in self.graded:
            buckets[r["task_class"]].append(r)
        return {
            cls: sum(1 for r in rows if r["outcome"] in SUCCESS) / len(rows)
            for cls, rows in sorted(buckets.items())
        }

    def cost(self, pricing: ModelPricing | None) -> Cost | None:
        if pricing is None:
            return None
        total = Cost()
        for r in self.rows:
            run = price_run(pricing,
                            input_tokens=r["input_tokens"],
                            cached_input_tokens=r["cached_input_tokens"],
                            output_tokens=r["output_tokens"])
            total = Cost(total.fresh_input_usd + run.fresh_input_usd,
                         total.cached_input_usd + run.cached_input_usd,
                         total.cache_write_usd + run.cache_write_usd,
                         total.output_usd + run.output_usd,
                         run.tier if run.tier == "long" else total.tier)
        return total

    def cost_per_success(self, pricing: ModelPricing | None) -> float | None:
        cost = self.cost(pricing)
        if cost is None or not self.successes:
            return None
        return cost.total_usd / self.successes

    def cache_hit_rate(self) -> float | None:
        total = sum(r["input_tokens"] for r in self.rows)
        cached = sum(r["cached_input_tokens"] for r in self.rows)
        return cached / total if total else None

    def tokens(self) -> dict[str, float | None]:
        """Components only. Never totalled — spec §5.6."""
        return {
            "static": self.mean("static_tokens"),
            "per-call overhead": self.mean("per_call_overhead_tokens"),
            "session setup": self.mean("session_setup_tokens"),
        }


@dataclass
class Report:
    """The single analysis object every renderer reads."""

    rows: list[dict[str, Any]]
    manifest: dict[str, Any] = field(default_factory=dict)
    #: Minimum detectable effect in percentage points, passed in by the CLI.
    #: The engine must not import `experiment` (plan.md §2), so power is
    #: computed there and handed here.
    mde_pp: float | None = None
    arms: dict[str, ArmSummary] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for row in self.rows:
            self.arms.setdefault(row["arm"], ArmSummary(row["arm"])).rows.append(row)

    # ---- identity --------------------------------------------------------

    @property
    def run_id(self) -> str:
        return str(self.manifest.get("id", "results"))

    @property
    def model(self) -> str:
        return str(self.manifest.get("model")
                   or (self.rows[0].get("model") if self.rows else "?"))

    @property
    def report_class(self) -> str:
        return str(self.rows[0].get("report_class", "?")) if self.rows else "?"

    @property
    def task_count(self) -> int:
        return len({r["task_id"] for r in self.rows})

    @property
    def pricing(self) -> ModelPricing | None:
        try:
            return lookup(self.model)
        except (UnknownModel, ValueError):
            return None

    # ---- validity --------------------------------------------------------

    @property
    def worlds(self) -> set[tuple]:
        """Distinct (model, revision, skill, class) combinations.

        A null MCP revision means the arm has no MCP at all — an absence, not a
        second revision — so it never triggers a pooling refusal on its own.
        """
        with_mcp = {(r["model"], r["mcp_spec_revision"], r["skill_condition"],
                     r["report_class"])
                    for r in self.rows if r["mcp_spec_revision"] is not None}
        if with_mcp:
            return with_mcp
        return {(r["model"], None, r["skill_condition"], r["report_class"])
                for r in self.rows}

    @property
    def pooling_refused(self) -> bool:
        return len(self.worlds) > 1

    @property
    def baseline(self) -> float | None:
        z0 = self.arms.get("Z0")
        return z0.success_rate if z0 else None

    @property
    def z0_gate(self) -> tuple[bool, int, int] | None:
        """(passed, substantive answers, graded). Refusals do not count.

        With no tools, correctly declining is the *expected* behaviour. Counting
        it as knowledge of the domain would fail every clean rig.
        """
        z0 = self.arms.get("Z0")
        if not z0:
            return None
        graded = z0.graded
        answered = sum(1 for r in graded if r["outcome"] == "pass")
        score = answered / len(graded) if graded else 0.0
        return (score <= 0.05, answered, len(graded))

    def lift(self, arm: str) -> float | None:
        base, summary = self.baseline, self.arms.get(arm)
        if base is None or summary is None or summary.success_rate is None:
            return None
        return summary.success_rate - base

    def below_mde(self, arm: str) -> bool:
        """Whether this arm's lift is too small to call a finding."""
        lift = self.lift(arm)
        if lift is None or self.mde_pp is None:
            return False
        return abs(lift * 100) < self.mde_pp

    @property
    def incomplete_arms(self) -> dict[str, tuple[int, int]]:
        """Arms with fewer runs than the rest. A missing cell is not a zero.

        Silently averaging over a short arm makes a crashed run look like a
        smaller sample rather than the failure it was.
        """
        if not self.arms:
            return {}
        expected = max(a.n for a in self.arms.values())
        return {name: (a.n, expected) for name, a in self.arms.items()
                if a.n < expected}

    @property
    def error_rows(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r.get("error")]

    @property
    def truncated_count(self) -> int:
        return sum(1 for r in self.rows if r["truncated"])

    @property
    def task_classes(self) -> list[str]:
        return sorted({r["task_class"] for r in self.rows})

    @property
    def inferred_answerable(self) -> bool:
        """True when the ledger predates the explicit `answerable` field."""
        return any("answerable" not in r for r in self.rows)

    # ---- metric variance -------------------------------------------------

    def varying_metrics(self) -> list[str]:
        """Metrics that actually differ across runs.

        A row of flat charts communicates nothing; the constant ones collapse to
        a single sentence instead.
        """
        names = {k for r in self.rows for k in r.get("metrics", {})}
        varying = []
        for name in sorted(names):
            values = [r["metrics"].get(name) for r in self.rows]
            numeric = [v for v in values if isinstance(v, (int, float))]
            if numeric and len(set(numeric)) > 1:
                varying.append(name)
        return varying

    def constant_metrics(self) -> dict[str, float]:
        names = {k for r in self.rows for k in r.get("metrics", {})}
        constant = {}
        for name in sorted(names):
            numeric = [r["metrics"].get(name) for r in self.rows
                       if isinstance(r.get("metrics", {}).get(name), (int, float))]
            if numeric and len(set(numeric)) == 1:
                constant[name] = numeric[0]
        return constant
