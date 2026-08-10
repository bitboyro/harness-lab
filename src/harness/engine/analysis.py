"""One computation layer, three renderers.

Text, HTML and SVG all read a `Report` built here. That is the point: a number
on the page and the same number in an exported chart cannot disagree, because
neither recomputes it.

The classification metrics exist because a success rate cannot distinguish an
agent that *fabricates* an answer from one that *gives up*. Both are failures;
only one is dangerous. The grader already produces a clean 2x2 over the
answerable/unanswerable decision, and precision, recall and MCC read it
directly.

Contract: archive/reference/experiment-design.md#analysis
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .pricing import Cost, ModelPricing, UnknownModel, lookup, price_run

#: Excluded from every rate. Truncation is a budget failure, ungraded is an
#: absent assertion, and infra-error is the harness or the machine breaking;
#: none of the three is a wrong answer.
NOT_GRADED = frozenset({"truncated", "ungraded", "infra-error"})
SUCCESS = frozenset({"pass", "correct-refusal"})

#: Outcomes in the order the failure taxonomy stacks them, best to worst.
OUTCOME_ORDER = ("pass", "correct-refusal", "fail-hedged", "fail-confident",
                 "false-positive", "declined-but-clobbered", "truncated")

#: The dimensions a report can be ranked on: key -> (column label, higher is
#: better, one-line meaning). Declared once so the CLI's `--sort` choices, the
#: standings columns and the sortable HTML headers cannot drift apart.
RANK_KEYS: dict[str, tuple[str, bool, str]] = {
    "score":      ("SCORE", True,  "weighted composite across every dimension"),
    "success":    ("success", True,
                   "share of tasks got right, counting correct refusals"),
    "lift":       ("lift", True, "success minus Z0's — what the packaging added"),
    "abstention": ("abstain", True,
                   "share of unanswerable tasks correctly declined"),
    "cost":       ("cost/succ", False, "dollars per task actually solved"),
    "tokens":     ("tokens", False, "mean input tokens per run"),
    "time":       ("secs", False, "mean wall-clock seconds per run"),
    "turns":      ("turns", False, "mean model-to-tool round trips"),
    "harm":       ("harm", False,
                   "share of runs that destroyed data or tried a forbidden call"),
    "trunc":      ("trunc", False, "share of runs that ran out of turns"),
    "name":       ("arm", True, "alphabetical by arm code"),
}


#: Arms that are not packaging choices. They anchor the scale — Z0 the floor,
#: Z1 the ceiling — and neither is something you could ship, so they are ranked
#: and displayed but never eligible to win.
CONTROL_ARMS = frozenset({"Z0", "Z1"})

#: The boundary no average may cross. Declared once because three footers state
#: it and a rule that drifts between renderers is not a rule.
POOLING_RULE = ("Never pool across model, MCP revision, skill condition, or "
                "report class.")

#: The row fields that define one world. Rows differing on any of these describe
#: different experiments, and `Report.worlds` refuses to average over them.
POOLING_FIELDS = ("model", "mcp_spec_revision", "skill_condition", "report_class")


def is_control(arm: str) -> bool:
    from .axes import split_label
    return split_label(arm)[0] in CONTROL_ARMS


def _preset_variant(arm: str):
    """Reconstruct a Variant from a preset name alone (legacy ledgers)."""
    from .axes import (Caching, DocBudget, ErrorDetail, McpRevision,
                       ResponseShape, SchemaDetail, preset, split_label)
    base, overrides = split_label(arm)
    axes = dict(
        schema_detail=SchemaDetail.STANDARD,
        response_shape=ResponseShape.AS_IS,
        error_detail=ErrorDetail.FIELD_SCOPED,
        doc_budget=DocBudget.STANDARD, surface_size=0,
        model="?", reasoning_effort="?", temperature=0.0,
        caching=Caching.OFF, repeats=1,
        mcp_revision=McpRevision.R2026_07_28,
    )
    for axis, value in overrides.items():
        if axis == "error_detail":
            axes["error_detail"] = ErrorDetail(value)
        elif axis == "response_shape":
            axes["response_shape"] = ResponseShape(value)
        elif axis == "doc_budget":
            axes["doc_budget"] = DocBudget(value)
        elif axis == "schema_detail":
            axes["schema_detail"] = SchemaDetail(value)
    return preset(base, **axes)


def _describe_preset(arm: str) -> str:
    """Best-effort description from a preset name alone (legacy ledgers)."""
    from .axes import describe
    try:
        return describe(_preset_variant(arm))
    except Exception:  # noqa: BLE001 — an unknown arm just has no description
        return ""


def _name_preset(arm: str) -> str:
    """Best-effort short name from a preset name alone (legacy ledgers)."""
    from .axes import short_name
    try:
        return short_name(_preset_variant(arm))
    except Exception:  # noqa: BLE001
        return ""


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

      pass                   -> TP   answered an answerable task correctly
      fail                   -> FN   failed an answerable task
      correct-refusal        -> TN   declined an unanswerable task cleanly
      false-positive         -> FP   answered a task that has no answer
      declined-but-clobbered ->      refused in text but mutated state —
                                     not TN; counted against specificity and
                                     treated as FP for MCC so the 2x2 cannot
                                     ignore a write that hid behind a refusal

    The FN split matters more than the total: an agent that hedges when it does
    not know is behaving well and failing; one that asserts confidently is
    failing *and* misleading. Only the second is a silent failure.
    """

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn_abstained: int = 0
    fn_confident: int = 0
    #: Unanswerable: refused in the transcript while mutating server state.
    declined_clobbered: int = 0

    @property
    def fn(self) -> int:
        return self.fn_abstained + self.fn_confident

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn + self.declined_clobbered

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
        """Of the unanswerable tasks, how many were correctly declined.

        A refusal that clobbered state is not a correct decline — it sits in
        the denominator with FP so abstention cannot ignore write-fabrication.
        """
        return self._ratio(
            self.tn, self.tn + self.fp + self.declined_clobbered)

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

        Declined-but-clobbered is folded into FP here: the classical 2x2 has no
        third cell, and treating a mutating refusal as a clean TN would let MCC
        ignore the failure mode this field exists to catch.
        """
        tp, tn, fn = self.tp, self.tn, self.fn
        fp = self.fp + self.declined_clobbered
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
    def is_control(self) -> bool:
        return is_control(self.arm)

    @property
    def description(self) -> str:
        """What this arm actually was.

        Prefers the assignment recorded on the row, which is exact even when a
        sweep overrode an axis. Falls back to the preset name for ledgers
        written before that field existed — without the fallback the section
        silently disappears on older results, which is worse than an
        approximate description.
        """
        for row in self.rows:
            if row.get("axes", {}).get("description"):
                return str(row["axes"]["description"])
        return _describe_preset(self.arm)

    @property
    def name(self) -> str:
        """Two or three words, for use beside the arm code.

        Same provenance rule as `description`: the recorded assignment first,
        the preset second. A bare `D2-auth` is unreadable to anyone who has not
        memorised the design, and the codes are the least informative thing on
        the page.
        """
        for row in self.rows:
            if row.get("axes", {}).get("name"):
                return str(row["axes"]["name"])
        return _name_preset(self.arm)

    @property
    def label(self) -> str:
        """`A1 · MCP, all tools` — the form used in every table."""
        name = self.name
        return f"{self.arm} · {name}" if name else self.arm

    @property
    def harm_rate(self) -> float:
        return self.harm_events / self.n if self.n else 0.0

    @property
    def abstention_accuracy(self) -> float | None:
        """Specificity: of the unanswerable tasks, the share correctly declined.

        Scored on its own rather than left inside the success rate. Correct
        refusals *do* count as successes, but with ~15% of tasks unanswerable an
        arm that fabricates on every one of them loses at most 15 points of
        success — far too little weight for the failure mode that matters most.
        """
        return self.confusion.specificity

    @property
    def confusion(self) -> Confusion:
        tp = fp = tn = abstained = confident = declined_clobbered = 0
        for r in self.graded:
            outcome = r["outcome"]
            if outcome == "pass":
                tp += 1
            elif outcome == "false-positive":
                fp += 1
            elif outcome == "correct-refusal":
                tn += 1
            elif outcome == "declined-but-clobbered":
                declined_clobbered += 1
            elif outcome == "fail":
                if r.get("confident"):
                    confident += 1
                else:
                    abstained += 1
        return Confusion(tp=tp, fp=fp, tn=tn,
                         fn_abstained=abstained, fn_confident=confident,
                         declined_clobbered=declined_clobbered)

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
    #: Composite-score weights. None uses `winner.DEFAULT_WEIGHTS`.
    weights: dict[str, float] | None = None
    #: Operation ledger (Phase 9). Built at report time from traces; None when
    #: the results directory has no traces/ to join.
    op_ledger: Any = None
    arms: dict[str, ArmSummary] = field(default_factory=dict, init=False)
    _verdict: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        for row in self.rows:
            self.arms.setdefault(row["arm"], ArmSummary(row["arm"])).rows.append(row)

    def verdict(self):
        """The scored ranking. Computed once — sorting on `score` asks per arm."""
        if self._verdict is None:
            from .winner import evaluate
            self._verdict = evaluate(self, self.weights)
        return self._verdict

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

    # ---- ranking ---------------------------------------------------------

    def rank_value(self, arm: str, key: str) -> float | None:
        """One arm's value on one ranking dimension."""
        summary = self.arms.get(arm)
        if summary is None:
            return None
        if key == "score":
            return self.verdict().scores.get(arm)
        return {
            "success": lambda: summary.success_rate,
            "lift": lambda: self.lift(arm),
            "abstention": lambda: summary.abstention_accuracy,
            "cost": lambda: summary.cost_per_success(self.pricing),
            "tokens": lambda: summary.mean("input_tokens"),
            "time": lambda: summary.mean("wall_clock_seconds"),
            "turns": lambda: summary.mean("turns"),
            "harm": lambda: summary.harm_rate,
            "trunc": lambda: summary.truncation_rate,
            "name": lambda: None,
        }.get(key, lambda: None)()

    def ranked(self, key: str = "score") -> list[ArmSummary]:
        """Arms best-first on one dimension.

        Both renderers call this rather than sorting themselves, so the terminal
        and the HTML can never disagree about who came first. Arms with no value
        on the chosen dimension sort last — an absent number is not a zero, and
        letting it rank as one would put a crashed arm at the top of a
        lower-is-better column.
        """
        if key == "name" or key not in RANK_KEYS:
            return [self.arms[a] for a in sorted(self.arms)]
        higher_is_better = RANK_KEYS[key][1]

        def sort_key(summary: ArmSummary) -> tuple:
            value = self.rank_value(summary.arm, key)
            if value is None:
                return (1, 0.0, summary.arm)
            return (0, -value if higher_is_better else value, summary.arm)

        return sorted(self.arms.values(), key=sort_key)

    def candidates(self) -> list[str]:
        """Arms eligible to win: the packagings, not the controls."""
        return [a for a in sorted(self.arms) if not is_control(a)]

    def best_on(self, key: str) -> str | None:
        """Which arm leads one dimension, controls excluded."""
        ranked = [s for s in self.ranked(key) if not s.is_control
                  and self.rank_value(s.arm, key) is not None]
        return ranked[0].arm if ranked else None

    # ---- metric variance -------------------------------------------------

    def metric_spread(self, name: str) -> float:
        """How much this metric actually separated the arms, in 0..1.

        Used to decide which metrics are worth charting. A metric that came out
        the same everywhere explains nothing about why one packaging beat
        another, however interesting it is in the abstract — so the section
        adapts to what the run found rather than following a fixed list.

        Deliberately *not* a coefficient of variation. CV divides by the mean,
        so a metric that is zero for eight arms and 0.15 for the ninth scores
        enormously and outranks one that runs 0 → 2.8 across four arms. That is
        backwards: one outlier against a field of zeros separated a single arm,
        not the arms. So spread is dispersion relative to the largest value,
        scaled by how many arms actually moved.
        """
        values = [v for v in (self.arms[a].metric_mean(name) for a in self.arms)
                  if v is not None]
        if len(values) < 2:
            return 0.0
        lo, hi = min(values), max(values)
        if hi == lo or hi == 0:
            return 0.0
        mean = sum(values) / len(values)
        deviation = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        participation = sum(1 for v in values if v != lo) / len(values)
        return (deviation / abs(hi)) * participation

    def metrics_by_spread(self, bucket: str | None = None) -> list[str]:
        """Varying metrics, most discriminating first.

        `bucket` filters to one metric family. The behaviour section asks for
        `mechanism` only: turns, tokens and seconds are cost, they already have
        their own tables, and left unfiltered they crowd out the metrics that
        actually explain the result.
        """
        from .metrics import get

        names = self.varying_metrics()
        if bucket is not None:
            kept = []
            for name in names:
                try:
                    if str(get(name).bucket) == bucket:
                        kept.append(name)
                except KeyError:  # a metric the registry does not know
                    continue
            names = kept
        return sorted(names, key=self.metric_spread, reverse=True)

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
