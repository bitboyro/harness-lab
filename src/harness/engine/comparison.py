"""One computation layer for N runs, three renderers.

`analysis.Report` is the same idea one level down: every renderer reads one
object and none of them recomputes a number. `Comparison` extends that to a set
of runs. It owns *only* cross-run derivations — the parameter diff, the arm
intersection, deltas against the reference, and the dispatch into
`stats.cross_compare`. It never recomputes a per-arm rate; every value comes
back out of `report.rank_value` or an `ArmSummary` property. If it recomputed
even one, the comparison page and the single-run page could disagree, which is
the failure the whole layering exists to prevent.

Two things make comparing runs harder than comparing arms, and both shape this
module:

  - **Runs differ in their setup, not just their results.** A delta read without
    knowing the runs used different difficulty settings is worse than no delta.
    So the parameter diff is computed first, rendered first, and distinguishes
    "differs" from "one run cannot say" — `NOT_RECORDED` is not a value.
  - **Arms are the join key and they are not guaranteed to line up.** An arm two
    runs out of three have would leave a blank in a delta column, and a blank
    reads as a zero. Only `shared_arms` enter the head-to-head; the rest are
    reported standalone in their own section.

Contract: archive/reference/statistics.md#comparing-runs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .analysis import POOLING_FIELDS, RANK_KEYS, ArmSummary, Report
from .stats import CrossContrast, cross_compare, world_key


class ComparisonError(ValueError):
    """A comparison that cannot be honoured. Never silently degraded."""


class _NotRecorded:
    """This run's ledger cannot say what the parameter was.

    Deliberately not `None` and deliberately not equal to itself for the
    purposes of the diff: two runs that both cannot say might still have
    differed, and reporting that as "the same" is the lie this sentinel exists
    to prevent.
    """

    __slots__ = ()

    def __str__(self) -> str:
        return "not recorded"

    def __repr__(self) -> str:
        return "NOT_RECORDED"

    def __bool__(self) -> bool:
        return False


NOT_RECORDED = _NotRecorded()


@dataclass(frozen=True, slots=True)
class Mixed:
    """A parameter that genuinely varied *within* one run.

    A `--sweep-error-detail` run has two error-detail levels by design. That is
    a state, not an absence, and collapsing it to the first value would describe
    a run that never happened.
    """

    values: tuple[str, ...]

    def __str__(self) -> str:
        return " / ".join(self.values)


@dataclass(frozen=True, slots=True)
class Parameter:
    """One knob, declared once.

    Declared as a table for the same reason `RANK_KEYS` is: the text columns,
    the HTML columns and the CSV header all read this tuple, so they cannot
    drift apart.
    """

    name: str
    group: str
    manifest_key: str | None = None
    axes_key: str | None = None
    row_key: str | None = None
    #: Differing here forbids pooling — the report leads with a stop banner.
    pooling: bool = False
    #: Differing here means the runs were given different tasks, so they cannot
    #: be paired within core.
    world: bool = False
    #: Values meaning "this arm has none of this at all". Dropped before the
    #: distinct set is taken, and replaced by `absent_label` if nothing else
    #: remains. An absence is not a second value, and reading it as one makes
    #: every run containing a control look internally inconsistent.
    absent_values: tuple[Any, ...] = ()
    absent_label: str = "none"
    meaning: str = ""


#: Every parameter a comparison knows how to look for, in display order.
#:
#: `skill_condition` is deliberately absent. It varies *by arm* inside every run
#: (A1 has none, B1 a generated skill, B1-auth an authored one), so a run-level
#: scalar would always read Mixed and mean nothing. The pooling check for it
#: happens per shared arm instead — see `Comparison.pooling_breaks`.
PARAMETERS: tuple[Parameter, ...] = (
    # ---- identity ----
    Parameter("id", "identity", manifest_key="id",
              meaning="the run's name, from --id"),
    Parameter("created_at", "identity", manifest_key="created_at",
              meaning="when the run started (rewritten by --resume)"),
    Parameter("harness version", "identity", manifest_key="harness_version",
              meaning="the code that produced the ledger"),
    Parameter("presets", "identity", manifest_key="presets", row_key="arm",
              meaning="the arms the run was asked for"),
    Parameter("arms digest", "identity", manifest_key="arms_digest",
              meaning="content address of every resolved arm (axes + materials)"),
    Parameter("plan id", "identity", manifest_key="plan_id",
              meaning="run plan id, when the matrix came from a plan file"),
    Parameter("plan digest", "identity", manifest_key="plan_digest",
              meaning="content address of the resolved run plan"),
    Parameter("plan path", "identity", manifest_key="plan_path",
              meaning="path of the plan file that produced this matrix"),
    Parameter("planned", "identity", manifest_key="planned",
              meaning="cells the run intended to fill"),
    Parameter("resumed", "identity", manifest_key="resumed",
              meaning="cells already on disk when the run started"),
    Parameter("excluded arms", "identity", manifest_key="excluded_arms",
              meaning="arms dropped at load with the reason"),
    # ---- model ----
    Parameter("model", "model", manifest_key="model", row_key="model",
              pooling=True, meaning="the model under test"),
    Parameter("provider", "model", manifest_key="provider",
              meaning="which API served the model"),
    Parameter("reasoning effort", "model", manifest_key="reasoning_effort",
              meaning="the model's thinking budget"),
    Parameter("temperature", "model", manifest_key="temperature",
              meaning="sampling temperature requested"),
    Parameter("caching", "model", manifest_key="caching",
              meaning="whether prompt caching was on"),
    Parameter("report class", "model", manifest_key="report_class",
              row_key="report_class", pooling=True,
              meaning="controlled or field — what the numbers may claim"),
    # ---- world ----
    Parameter("seed", "world", manifest_key="seed", row_key="seed", world=True,
              meaning="regenerates an identical world"),
    Parameter("cores", "world", manifest_key="cores", world=True,
              meaning="independent problems — the unit of analysis"),
    Parameter("fan out", "world", manifest_key="fan_out", world=True,
              meaning="how wide each core's world is"),
    Parameter("difficulty", "world", manifest_key="difficulty", world=True,
              meaning="how hard the generated tasks are"),
    Parameter("pack digest", "world", manifest_key="pack_digest", world=True,
              meaning="content address of the exact task set attempted"),
    Parameter("classes", "world", manifest_key="classes", world=True,
              meaning="task classes the run was filtered to"),
    Parameter("max tasks", "world", manifest_key="max_tasks", world=True,
              meaning="cap applied to the task list"),
    Parameter("tasks", "world", manifest_key="tasks",
              meaning="tasks after filtering"),
    # ---- surface ----
    # Z0 and the shell arms have no MCP transport at all. The ledger writes
    # that as None and `axis_summary` writes it as "", and both mean the same
    # absence — so both are dropped rather than counted as a revision.
    Parameter("mcp revision", "surface", manifest_key="mcp_revision",
              axes_key="mcp_revision", row_key="mcp_spec_revision",
              pooling=True, absent_values=(None, "", "none"),
              meaning="which MCP spec the transport spoke"),
    Parameter("surface size", "surface", manifest_key="surface_size",
              axes_key="surface_size", row_key="surface_size",
              meaning="operations on the API under test"),
    Parameter("schema detail", "surface", manifest_key="schema_detail",
              axes_key="schema_detail", meaning="how much schema the tools carry"),
    Parameter("response shape", "surface", manifest_key="response_shape",
              axes_key="response_shape", meaning="what a call hands back"),
    Parameter("error detail", "surface", manifest_key="error_detail",
              axes_key="error_detail", meaning="how much an error explains"),
    Parameter("doc budget", "surface", manifest_key="doc_budget",
              axes_key="doc_budget", meaning="how much documentation was offered"),
    Parameter("sweep: error detail", "surface", manifest_key="sweep_error_detail",
              meaning="error-detail levels swept within the run"),
    # ---- budget ----
    Parameter("repeats", "budget", manifest_key="repeats",
              meaning="runs per arm-task cell"),
    Parameter("max turns", "budget", manifest_key="max_turns",
              meaning="turn budget before truncation"),
    Parameter("concurrency", "budget", manifest_key="concurrency",
              meaning="workers — affects wall clock, not outcomes"),
)

#: Manifest keys the drift test does not demand a `Parameter` row for.
#: `arms` / `targets` are per-entry tables — compared by their digests above,
#: not as a single scalar Parameter.
MANIFEST_IGNORED: frozenset[str] = frozenset({"arms", "targets"})

#: The ledger's pooling fields under the names the parameter table uses, so a
#: run-level break and an arm-level break on the same boundary say the same word.
_POOLING_LABELS = {"model": "model", "mcp_spec_revision": "mcp revision",
                   "skill_condition": "skill condition",
                   "report_class": "report class"}


@dataclass(frozen=True, slots=True)
class ParamRow:
    """One parameter across every run."""

    parameter: Parameter
    values: dict[str, Any]
    #: run label -> "manifest" | "axes" | "rows". Absent when NOT_RECORDED.
    sources: dict[str, str]

    @property
    def name(self) -> str:
        return self.parameter.name

    @property
    def known(self) -> dict[str, Any]:
        return {k: v for k, v in self.values.items() if v is not NOT_RECORDED}

    @property
    def unknown_runs(self) -> list[str]:
        return [k for k, v in self.values.items() if v is NOT_RECORDED]

    @property
    def differs(self) -> bool:
        """Two runs recorded DIFFERENT values.

        The only thing that counts as a difference. A parameter one run cannot
        report is uncertainty, not disagreement, and conflating the two would
        flag every old ledger as having changed everything.
        """
        seen = {_hashable(v) for v in self.known.values()}
        return len(seen) > 1

    @property
    def uncertain(self) -> bool:
        """Recorded somewhere, missing somewhere. Could differ; cannot tell."""
        return bool(self.unknown_runs) and bool(self.known)


def _hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    return value


@dataclass(frozen=True, slots=True)
class PoolingBreak:
    """One boundary two runs sit on opposite sides of."""

    #: "run", or the arm whose rows disagree.
    scope: str
    parameter: str
    values: dict[str, Any]

    def render(self) -> str:
        where = "" if self.scope == "run" else f" (arm {self.scope})"
        pairs = ", ".join(f"{run}={value}" for run, value in self.values.items())
        return f"{self.parameter}{where}: {pairs}"


@dataclass(frozen=True, slots=True)
class RunRef:
    """One run in the comparison, already analysed.

    Takes a built `Report` rather than a path so this module never needs the
    MDE, which lives in `experiment` and must be injected by the CLI. That is
    what keeps `engine` free of an `experiment` import.
    """

    label: str
    path: str
    report: Report


def label_runs(entries: Sequence[tuple[str, dict]],
               overrides: Sequence[str] | None = None) -> list[str]:
    """A stable display name per run.

    The manifest `id` when it is unique, else `id (dirname)`, else `id #n`.
    Deterministic because a delta's sign is meaningless without a stable name
    for what it was measured against, and `--id` has a default, so two
    directories sharing an id is likely rather than exotic.
    """
    if overrides:
        return list(overrides)

    from pathlib import Path

    ids = [str(m.get("id") or Path(p).name or p) for p, m in entries]
    qualified = [name if ids.count(name) == 1 else f"{name} ({Path(p).name})"
                 for (p, _), name in zip(entries, ids)]

    # Two directories with the same basename *and* the same id is the last
    # collision left; number them rather than emit a duplicate, which
    # `Comparison` would refuse outright.
    labels: list[str] = []
    used: dict[str, int] = {}
    for name in qualified:
        if qualified.count(name) == 1:
            labels.append(name)
            continue
        used[name] = used.get(name, 0) + 1
        labels.append(f"{name} #{used[name]}")
    return labels


def _distinct(values: Iterable[Any], absent: tuple[Any, ...] = ()) -> list[str]:
    """Distinct values in first-seen order, stringified, absences dropped."""
    out: list[str] = []
    for value in values:
        if value in absent:
            continue
        text = str(value)
        if text not in out:
            out.append(text)
    return out


def _collapse(values: list[str], parameter: Parameter, *,
              saw_absence: bool) -> Any:
    """One value, `Mixed`, the absence label, or None for nothing at all."""
    if not values:
        return parameter.absent_label if saw_absence else None
    return values[0] if len(values) == 1 else Mixed(tuple(sorted(values)))


def _from_rows(report: Report, parameter: Parameter) -> Any:
    raw = [r.get(parameter.row_key) for r in report.rows]
    values = _distinct(raw, parameter.absent_values)
    return _collapse(values, parameter,
                     saw_absence=any(v in parameter.absent_values for v in raw))


def _from_axes(report: Report, parameter: Parameter) -> Any:
    raw = [r["axes"][parameter.axes_key] for r in report.rows
           if isinstance(r.get("axes"), dict) and parameter.axes_key in r["axes"]]
    if not raw:
        return None
    values = _distinct(raw, parameter.absent_values)
    return _collapse(values, parameter,
                     saw_absence=any(v in parameter.absent_values for v in raw))


def extract(report: Report, parameter: Parameter) -> tuple[Any, str | None]:
    """One parameter's value for one run, and where it came from.

    First hit wins: the manifest is authoritative, `row["axes"]` fills in what
    older manifests omitted, and the raw row is the last resort. Anything still
    missing is NOT_RECORDED — never guessed, never defaulted.
    """
    if parameter.manifest_key:
        value = report.manifest.get(parameter.manifest_key)
        if value is not None and value != []:
            return (value, "manifest")

    if parameter.axes_key:
        value = _from_axes(report, parameter)
        if value is not None:
            return (value, "axes")

    if parameter.row_key:
        value = _from_rows(report, parameter)
        if value is not None:
            return (value, "rows")

    return (NOT_RECORDED, None)


@dataclass
class Comparison:
    """N runs, the first of which is the reference."""

    runs: list[RunRef]
    weights: dict[str, float] | None = None
    _cache: dict = field(default_factory=dict, init=False, repr=False)

    #: The categorical palette has eight slots and never cycles (svg.py). A
    #: ninth run would silently reuse a colour, so it is refused instead.
    MAX_RUNS = 8

    def __post_init__(self) -> None:
        if len(self.runs) < 2:
            raise ComparisonError("a comparison needs at least two runs")
        if len(self.runs) > self.MAX_RUNS:
            raise ComparisonError(
                f"{len(self.runs)} runs, but the chart palette has "
                f"{self.MAX_RUNS} slots and never cycles. A ninth run would "
                "reuse a colour and two series would become one."
            )
        labels = [r.label for r in self.runs]
        if len(set(labels)) != len(labels):
            raise ComparisonError(f"duplicate run labels: {sorted(labels)}")

    # ---- identity --------------------------------------------------------

    @property
    def reference(self) -> RunRef:
        return self.runs[0]

    @property
    def others(self) -> list[RunRef]:
        return self.runs[1:]

    @property
    def labels(self) -> list[str]:
        return [r.label for r in self.runs]

    def run(self, label: str) -> RunRef:
        for ref in self.runs:
            if ref.label == label:
                return ref
        raise KeyError(label)

    def report(self, label: str) -> Report:
        return self.run(label).report

    # ---- parameters ------------------------------------------------------

    @property
    def params(self) -> list[ParamRow]:
        """Every declared parameter, in declared order."""
        if "params" not in self._cache:
            rows = []
            for parameter in PARAMETERS:
                values, sources = {}, {}
                for ref in self.runs:
                    value, source = extract(ref.report, parameter)
                    values[ref.label] = value
                    if source:
                        sources[ref.label] = source
                rows.append(ParamRow(parameter, values, sources))
            self._cache["params"] = rows
        return self._cache["params"]

    @property
    def differing(self) -> list[ParamRow]:
        return [p for p in self.params if p.differs]

    @property
    def uncertain(self) -> list[ParamRow]:
        return [p for p in self.params if p.uncertain and not p.differs]

    @property
    def conflicts(self) -> list[tuple[str, str, Any, Any]]:
        """(run, parameter, manifest value, ledger value) where the two disagree.

        A manifest copied from another directory is a real mistake, and the
        rows are what actually happened.
        """
        out = []
        for parameter in PARAMETERS:
            if not (parameter.manifest_key and parameter.row_key):
                continue
            for ref in self.runs:
                stated = ref.report.manifest.get(parameter.manifest_key)
                if stated is None:
                    continue
                observed = _from_rows(ref.report, parameter)
                if observed is None or isinstance(observed, Mixed):
                    continue
                if str(stated) != str(observed):
                    out.append((ref.label, parameter.name, stated, observed))
        return out

    # ---- pooling ---------------------------------------------------------

    @property
    def pooling_breaks(self) -> list[PoolingBreak]:
        """Every boundary these runs sit on opposite sides of.

        Run-level breaks come from the parameter diff. Skill condition is
        checked per shared arm instead, because it varies by arm by design — a
        run-level check would either always fire or never fire, and neither
        tells you that B1 used a generated skill in one run and an authored one
        in the other.
        """
        if "breaks" in self._cache:
            return self._cache["breaks"]

        breaks = [
            PoolingBreak("run", row.name, dict(row.values))
            for row in self.differing if row.parameter.pooling
        ]
        run_level = {b.parameter for b in breaks}

        for arm in self.shared_arms:
            for field_name in POOLING_FIELDS:
                label = _POOLING_LABELS[field_name]
                if label in run_level:
                    continue  # already said, at the level that matters more
                values = {}
                for ref in self.runs:
                    summary = ref.report.arms.get(arm)
                    if summary is None:
                        continue
                    absent = ((None, "", "none")
                              if field_name == "mcp_spec_revision" else ())
                    seen = _distinct((r.get(field_name) for r in summary.rows),
                                     absent)
                    values[ref.label] = " / ".join(seen) if seen else "none"
                if len({str(v) for v in values.values()}) > 1:
                    breaks.append(PoolingBreak(arm, label, values))

        self._cache["breaks"] = breaks
        return breaks

    @property
    def pooling_refused(self) -> bool:
        return bool(self.pooling_breaks)

    def cross_world(self, arm: str, label: str) -> bool:
        """Whether this arm sits across a pooling boundary from the reference."""
        return any(b.scope in ("run", arm) and label in b.values
                   for b in self.pooling_breaks)

    @property
    def same_world(self) -> bool:
        """Whether every run drew its tasks from the same generated world."""
        keys = [world_key(r.report) for r in self.runs]
        return all(k is not None and k == keys[0] for k in keys)

    # ---- arms ------------------------------------------------------------

    @property
    def shared_arms(self) -> list[str]:
        """Arms every run has. The head-to-head covers only these."""
        if "shared" not in self._cache:
            sets = [set(r.report.arms) for r in self.runs]
            self._cache["shared"] = sorted(set.intersection(*sets)) if sets else []
        return self._cache["shared"]

    @property
    def exclusive_arms(self) -> dict[str, list[str]]:
        """arm -> the runs that have it, for arms not every run has.

        Reported standalone and never given a delta. Subtracting from nothing
        would put a blank in the column, and a blank reads as a zero.
        """
        shared = set(self.shared_arms)
        out: dict[str, list[str]] = {}
        for ref in self.runs:
            for arm in ref.report.arms:
                if arm not in shared:
                    out.setdefault(arm, []).append(ref.label)
        return dict(sorted(out.items()))

    def ranked_arms(self, key: str = "score") -> list[str]:
        """Shared arms in the reference run's order on `key`.

        One order down the whole page — the same rule `Report.ranked` enforces
        inside a single report, so a reader never has to re-establish who is
        winning between sections.
        """
        shared = set(self.shared_arms)
        ordered = [s.arm for s in self.reference.report.ranked(key)
                   if s.arm in shared]
        return ordered + sorted(shared - set(ordered))

    # ---- values ----------------------------------------------------------

    def summary(self, label: str, arm: str) -> ArmSummary | None:
        return self.report(label).arms.get(arm)

    def value(self, label: str, arm: str, key: str) -> float | None:
        return self.report(label).rank_value(arm, key)

    def delta(self, label: str, arm: str, key: str) -> float | None:
        """This run minus the reference.

        None when either side is None — never zero. An absent number is not an
        equal one, and a zero in a delta column is a claim that nothing changed.
        """
        here = self.value(label, arm, key)
        there = self.value(self.reference.label, arm, key)
        if here is None or there is None:
            return None
        return here - there

    # ---- power -----------------------------------------------------------

    @property
    def mde_pp(self) -> float | None:
        """The least-powered run's noise floor, in points.

        A difference between two measurements cannot be more detectable than
        the weaker of them, so the max is the conservative read — and it is a
        number the reader already saw on each single-run report.
        """
        known = [r.report.mde_pp for r in self.runs if r.report.mde_pp is not None]
        return max(known) if known else None

    def contrasts(self) -> list[CrossContrast]:
        """One per shared arm per non-reference run, against the reference."""
        if "contrasts" not in self._cache:
            out = []
            for ref in self.others:
                for arm in self.ranked_arms():
                    contrast = cross_compare(
                        self.reference.report, ref.report, arm,
                        label_a=self.reference.label, label_b=ref.label)
                    if contrast is not None:
                        out.append(contrast)
            self._cache["contrasts"] = out
        return self._cache["contrasts"]

    def contrast_for(self, arm: str, label: str) -> CrossContrast | None:
        for contrast in self.contrasts():
            if contrast.arm == arm and contrast.run_b == label:
                return contrast
        return None

    def unresolved(self, label: str, arm: str, key: str = "success") -> bool:
        """Whether this delta is too weak to read as a difference.

        For success-shaped keys the answer comes from the contrast, so the
        head-to-head table and the contrast table cannot disagree: an arrow
        saying "improved" three lines above an interval spanning zero is the
        exact contradiction this routes around. Other keys have no contrast, so
        they fall back to the combined noise floor alone.
        """
        delta = self.delta(label, arm, key)
        if delta is None:
            return False
        contrast = self.contrast_for(arm, label)
        if contrast is None:
            return False
        if key == "success":
            return not contrast.notable
        floor = contrast.mde_combined
        if key not in ("lift", "abstention") or floor is None:
            return False
        return abs(delta * 100) < floor

    # ---- score comparability ---------------------------------------------

    @property
    def score_comparable(self) -> bool:
        """Whether a SCORE delta means anything at all.

        `winner.evaluate` min-max normalises each dimension *within that run's
        candidate set*. If the runs ran different arms, the two composites were
        rescaled against different ranges and their difference is an artefact of
        which arms happened to be present. The renderers suppress the score
        table rather than print it with a footnote nobody reads.
        """
        return not self.exclusive_arms

    # ---- shared formatting -----------------------------------------------
    #
    # Both renderers format through these. The anti-drift test then asks for a
    # string and asserts it appears in both outputs, which turns "the two
    # renderers happen to use the same f-string" into arithmetic.

    #: Keys whose values are rates, so their deltas are in percentage points.
    RATE_KEYS = frozenset({"success", "lift", "abstention", "harm", "trunc"})

    @staticmethod
    def fmt(key: str, value: Any) -> str:
        """One value, formatted as `winner._cell` would format it.

        Also carries parameter values, which are not numbers at all — the same
        formatter handles both so a parameter and a metric cannot be rendered
        two different ways on the two pages.
        """
        if value is NOT_RECORDED:
            return "not recorded"
        if value is None:
            return "n/a"
        if isinstance(value, (Mixed, str, bool)):
            return str(value)
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value) if value else "none"
        if not isinstance(value, (int, float)):
            return str(value)
        if key in Comparison.RATE_KEYS:
            return f"{value:.0%}"
        if key == "cost":
            return f"${value:.4f}"
        if isinstance(value, int):
            # Counts stay counts. "10.0 cores" invites a reader to wonder what
            # half a core would be.
            return f"{value:,}"
        return f"{value:,.1f}"

    @staticmethod
    def fmt_delta(key: str, value: float | None) -> str:
        """One delta, in the unit the difference is actually in.

        Rates become percentage points, never a percentage of a percentage:
        15% of 55% is a different number from 55% plus 15 points, and the
        glossary has an entry saying so.
        """
        if value is None:
            return "n/a"
        if key in Comparison.RATE_KEYS:
            return f"{value * 100:+.0f} pp"
        if key == "cost":
            return f"{value:+.4f}"
        return f"{value:+,.1f}"

    @staticmethod
    def direction(key: str, value: float | None) -> str:
        """`↑` better, `↓` worse, `·` flat — never colour alone."""
        if value is None or abs(value) < 1e-12:
            return "·"
        higher_is_better = RANK_KEYS.get(key, ("", True, ""))[1]
        improved = (value > 0) == higher_is_better
        return "↑" if improved else "↓"
