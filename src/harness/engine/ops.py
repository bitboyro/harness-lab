"""Operation ledger — where agents spend and stumble on a target API.

Built at report time from traces joined to ``results.jsonl``. No change to the
agent loop, grading, winner weights, or ledger columns.

Resolution is by **axes**, never by arm name. Core rates stay separate; a
composite stumble rank is derived and secondary. Signals we cannot measure
(no gold, parsed-only arms) are marked unavailable — never silently zero.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal

from .axes import Discovery, Invocation, Transport
from .dispatch import DESCRIBE, INVOKE, SEARCH

#: Meta-tool names that are packaging machinery, not the target API.
_DISCOVERY_TOOLS = frozenset({SEARCH, DESCRIBE, INVOKE})

#: How a call was resolved to an operation id — fidelity the report must state.
ResolutionKind = Literal["tool", "operation_id", "parsed", "excluded"]

#: Score fields that may be marked unavailable on an OpScore.
Unavailable = Literal[
    "off_gold_rate", "excess_usage", "distractors", "stumble_rank",
]


@dataclass(frozen=True, slots=True)
class ResolvedCall:
    """One call mapped onto a target operation (or marked discovery/excluded)."""

    op_id: str | None
    family: str
    arm: str
    task_class: str
    answerable: bool
    core_id: str
    resolution: ResolutionKind
    discovery: bool = False
    http_error: bool = False
    forbidden: bool = False
    known_operation: bool | None = None
    off_gold: bool = False
    #: True when this task had a gold sequence so off_gold is meaningful.
    gold_defined: bool = False
    redundant: bool = False
    run_failed: bool = False


@dataclass(frozen=True, slots=True)
class OpScore:
    """Core per-op rates within a slice. Derived fields may be unavailable."""

    op_id: str
    family: str
    calls: int
    usage_share: float
    error_rate: float
    forbidden_rate: float
    off_gold_rate: float | None
    redundant_rate: float
    known_rate: float | None
    resolution: ResolutionKind
    unavailable: frozenset[str] = frozenset()
    expected_share: float | None = None
    excess_usage: float | None = None
    #: Secondary composite — only when off_gold is available.
    stumble_rate: float | None = None

    def rank_key(self) -> tuple[float, float]:
        rate = self.stumble_rate if self.stumble_rate is not None else self.error_rate
        return (rate, self.usage_share)


@dataclass(frozen=True, slots=True)
class FamilyScore:
    family: str
    usage_share: float
    error_rate: float
    off_gold_rate: float | None
    worst_op: str
    calls: int


@dataclass(frozen=True, slots=True)
class ArmDelta:
    """Descriptive packaging contrast on one op — not a confirmatory finding."""

    op_id: str
    family: str
    arm_a: str
    arm_b: str
    metric: str
    delta: float  # arm_b - arm_a (negative ⇒ arm_b improved)


@dataclass
class OpLedger:
    """Core call rows plus derived views for the customer report section."""

    calls: list[ResolvedCall] = field(default_factory=list)
    excluded_arms: dict[str, str] = field(default_factory=dict)
    discovery_calls: int = 0
    #: task_id → gold op ids. Empty ⇒ off-gold / excess / distractors unavailable.
    gold_by_task: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Expected usage share from gold frequency (answerable tasks with gold).
    expected_share: dict[str, float] = field(default_factory=dict)

    @property
    def has_gold(self) -> bool:
        return bool(self.gold_by_task)

    @property
    def unavailable_globally(self) -> frozenset[str]:
        missing: set[str] = set()
        if not self.has_gold:
            missing.update({"off_gold_rate", "excess_usage", "distractors"})
        return frozenset(missing)

    def usage(self, *, arm: str | None = None, top: int = 10) -> list[OpScore]:
        return sorted(
            self._scores(arm=arm),
            key=lambda s: (-s.usage_share, s.op_id),
        )[:top]

    def excess_usage(self, *, arm: str | None = None, top: int = 10) -> list[OpScore] | None:
        """Observed share minus gold-expected share. None if gold is absent."""
        if not self.has_gold:
            return None
        scored = [s for s in self._scores(arm=arm) if s.excess_usage is not None]
        return sorted(scored, key=lambda s: (-(s.excess_usage or 0), s.op_id))[:top]

    def distractors(self, *, arm: str | None = None, top: int = 10) -> list[OpScore] | None:
        """High off-gold, low/zero gold membership — candidates to hide."""
        if not self.has_gold:
            return None
        out = []
        for s in self._scores(arm=arm):
            if s.off_gold_rate is None:
                continue
            expected = self.expected_share.get(s.op_id, 0.0)
            if s.off_gold_rate >= 0.5 and expected <= 0.05:
                out.append(s)
        return sorted(out, key=lambda s: (-(s.off_gold_rate or 0), -s.usage_share))[:top]

    def stumble_by_kind(
        self,
        kind: Literal["wrong_route", "call_error", "forbidden"],
        *,
        arm: str | None = None,
        top: int = 10,
    ) -> list[OpScore] | None:
        """Rank by one misuse kind. wrong_route needs gold."""
        if kind == "wrong_route" and not self.has_gold:
            return None
        key = {
            "wrong_route": lambda s: s.off_gold_rate or 0.0,
            "call_error": lambda s: s.error_rate,
            "forbidden": lambda s: s.forbidden_rate,
        }[kind]
        scored = [s for s in self._scores(arm=arm) if s.calls > 0]
        return sorted(scored, key=lambda s: (-key(s), -s.usage_share, s.op_id))[:top]

    def misuse(self, *, arm: str | None = None, top: int = 10) -> list[OpScore]:
        """Secondary composite stumble rank — only ops with a full rate set."""
        scored = [
            s for s in self._scores(arm=arm)
            if s.stumble_rate is not None and s.calls > 0
        ]
        return sorted(
            scored,
            key=lambda s: (-(s.stumble_rate or 0), -s.usage_share, s.op_id),
        )[:top]

    def families(self, *, arm: str | None = None) -> list[FamilyScore]:
        by_family: dict[str, list[OpScore]] = defaultdict(list)
        for score in self._scores(arm=arm):
            by_family[score.family].append(score)
        total = sum(s.calls for scores in by_family.values() for s in scores) or 1
        out: list[FamilyScore] = []
        for family, scores in by_family.items():
            calls = sum(s.calls for s in scores)
            err = sum(s.error_rate * s.calls for s in scores) / calls if calls else 0.0
            if self.has_gold and all(s.off_gold_rate is not None for s in scores):
                off: float | None = (
                    sum((s.off_gold_rate or 0) * s.calls for s in scores) / calls
                )
            else:
                off = None
            worst = max(scores, key=lambda s: (
                s.stumble_rate if s.stumble_rate is not None else s.error_rate,
                s.usage_share,
            ))
            out.append(FamilyScore(
                family=family,
                usage_share=calls / total,
                error_rate=err,
                off_gold_rate=off,
                worst_op=worst.op_id,
                calls=calls,
            ))
        return sorted(out, key=lambda f: (-f.usage_share, f.family))

    def arm_deltas(
        self,
        *,
        metric: Literal["off_gold_rate", "error_rate", "forbidden_rate"] = "off_gold_rate",
        top: int = 8,
    ) -> list[ArmDelta] | None:
        """Per-op packaging deltas. Descriptive — not confirmatory / not MDE."""
        if metric == "off_gold_rate" and not self.has_gold:
            return None
        arms = sorted({c.arm for c in self.calls if not c.discovery and c.op_id})
        if len(arms) < 2:
            return None
        by_arm = {a: {s.op_id: s for s in self._scores(arm=a)} for a in arms}
        deltas: list[ArmDelta] = []
        # Pair consecutive arms in sorted order; also cover first vs last for span.
        pairs = [(arms[i], arms[i + 1]) for i in range(len(arms) - 1)]
        if len(arms) > 2:
            pairs.append((arms[0], arms[-1]))
        for a, b in pairs:
            shared = set(by_arm[a]) & set(by_arm[b])
            for op_id in shared:
                sa, sb = by_arm[a][op_id], by_arm[b][op_id]
                va = getattr(sa, metric)
                vb = getattr(sb, metric)
                if va is None or vb is None:
                    continue
                deltas.append(ArmDelta(
                    op_id=op_id, family=sa.family, arm_a=a, arm_b=b,
                    metric=metric, delta=float(vb) - float(va),
                ))
        # Prefer improvements (negative delta) then magnitude.
        deltas.sort(key=lambda d: (d.delta, -abs(d.delta), d.op_id))
        return deltas[:top]

    def by_class(self, task_class: str, *, arm: str | None = None) -> list[OpScore]:
        rows = [
            c for c in self.calls
            if not c.discovery and c.op_id
            and c.task_class == task_class
            and (arm is None or c.arm == arm)
        ]
        return self._scores_from(rows)

    def fail_association(
        self, *, arm: str | None = None, top: int = 5,
    ) -> list[tuple[str, float]]:
        """P(fail|op) − P(fail) within the slice. Exploratory footnote only."""
        rows = [
            c for c in self.calls
            if not c.discovery and c.op_id
            and (arm is None or c.arm == arm)
        ]
        if not rows:
            return []
        # One outcome per (run) approximated via calls sharing run_failed flag.
        # Group by op: among calls to op, share whose run failed.
        baseline = sum(1 for c in rows if c.run_failed) / len(rows)
        by_op: dict[str, list[ResolvedCall]] = defaultdict(list)
        for c in rows:
            by_op[c.op_id].append(c)  # type: ignore[arg-type]
        out: list[tuple[str, float]] = []
        for op_id, group in by_op.items():
            rate = sum(1 for c in group if c.run_failed) / len(group)
            out.append((op_id, rate - baseline))
        out.sort(key=lambda x: (-x[1], x[0]))
        return out[:top]

    def render(self) -> str:
        lines = [
            "  operation ledger — where agents spend and stumble",
            "  (rates, not raw counts; volume follows task shape)",
            "",
        ]
        if self.excluded_arms:
            lines.append("  excluded (no target calls — not shown as zero):")
            for arm, reason in sorted(self.excluded_arms.items()):
                lines.append(f"    {arm:<12} {reason}")
            lines.append("")

        if self.unavailable_globally:
            lines.append(
                "  unavailable on this run: "
                + ", ".join(sorted(self.unavailable_globally))
                + " (no gold_call_sequence — not shown as zero)"
            )
            lines.append("")

        # A. over-touch (excess) or raw usage
        excess = self.excess_usage()
        if excess is not None:
            lines.append("  A. over-touch (usage − gold-expected)")
            lines.append(
                "     Spend beyond the task path — prioritize docs/hide here, "
                "not declare winners."
            )
            for s in excess:
                if (s.excess_usage or 0) <= 0:
                    continue
                tag = _fidelity_tag(s.resolution)
                lines.append(
                    f"    {s.op_id:<28} excess={s.excess_usage:+.0%}  "
                    f"use={s.usage_share:5.0%} exp={s.expected_share or 0:5.0%}"
                    f"{tag}"
                )
            lines.append("")
        else:
            usage = self.usage()
            if usage:
                lines.append("  A. where agents spend (usage share)")
                lines.append(
                    "     Excess usage unavailable without gold — raw share "
                    "follows the task shape."
                )
                for s in usage:
                    tag = _fidelity_tag(s.resolution)
                    lines.append(
                        f"    {s.op_id:<28} {s.usage_share:5.0%}  "
                        f"family={s.family}{tag}"
                    )
                lines.append("")

        # B. stumble by kind
        lines.append("  B. where agents stumble (by kind, not one blended score)")
        for kind, label in (
            ("wrong_route", "wrong-route (off-gold)"),
            ("call_error", "call-error (4xx/5xx)"),
            ("forbidden", "forbidden"),
        ):
            ranked = self.stumble_by_kind(kind)  # type: ignore[arg-type]
            if ranked is None:
                lines.append(f"    {label}: unavailable (needs gold)")
                continue
            # Skip empty-looking tops (all zeros).
            key = {
                "wrong_route": lambda s: s.off_gold_rate or 0.0,
                "call_error": lambda s: s.error_rate,
                "forbidden": lambda s: s.forbidden_rate,
            }[kind]
            ranked = [s for s in ranked if key(s) > 0][:5]
            if not ranked:
                lines.append(f"    {label}: (none)")
                continue
            lines.append(f"    {label}:")
            for s in ranked:
                tag = _fidelity_tag(s.resolution)
                if kind == "wrong_route":
                    val = s.off_gold_rate or 0.0
                elif kind == "call_error":
                    val = s.error_rate
                else:
                    val = s.forbidden_rate
                lines.append(f"      {s.op_id:<26} {val:5.0%}{tag}")
        distractors = self.distractors()
        if distractors:
            lines.append("    distractors (high off-gold, rare in gold):")
            for s in distractors[:5]:
                lines.append(
                    f"      {s.op_id:<26} off_gold={s.off_gold_rate:5.0%}"
                )
        lines.append("")

        # C. family + arm deltas
        fams = self.families()
        if fams:
            lines.append("  C. family snapshot")
            for f in fams:
                off = ("n/a" if f.off_gold_rate is None
                       else f"{f.off_gold_rate:5.0%}")
                lines.append(
                    f"    {f.family:<20} usage={f.usage_share:5.0%}  "
                    f"err={f.error_rate:5.0%}  off_gold={off}  "
                    f"worst={f.worst_op}"
                )
            lines.append("")

        metric = "off_gold_rate" if self.has_gold else "error_rate"
        deltas = self.arm_deltas(metric=metric)  # type: ignore[arg-type]
        if deltas:
            lines.append(f"  arm deltas on {metric} (descriptive, not confirmatory):")
            for d in deltas:
                if abs(d.delta) < 0.05:
                    continue
                direction = "lower" if d.delta < 0 else "higher"
                lines.append(
                    f"    {d.op_id}: {d.arm_b} {direction} than {d.arm_a} "
                    f"by {abs(d.delta):.0%}"
                )
            lines.append("")

        if self.discovery_calls:
            lines.append(
                f"  discovery footnote: {self.discovery_calls} meta-tool "
                f"calls (search/describe/invoke) excluded from target charts"
            )
            lines.append("")

        parsed = sum(1 for c in self.calls if c.resolution == "parsed")
        if parsed:
            lines.append(
                f"  fidelity: {parsed} calls resolved by parsing shell/code "
                f"bodies [parsed] — best-effort, not a server request log"
            )
            lines.append("")

        lines.append(
            "  interpretation: volume ≠ blame; HTTP-clean can still harm; "
            "unanswerable thrash is abstention, not an outage; arm differences "
            "in which ops appear are packaging shape until rates move."
        )
        return "\n".join(lines)

    def _scores(self, *, arm: str | None) -> list[OpScore]:
        rows = [
            c for c in self.calls
            if not c.discovery and c.op_id
            and (arm is None or c.arm == arm)
        ]
        return self._scores_from(rows)

    def _scores_from(self, rows: list[ResolvedCall]) -> list[OpScore]:
        if not rows:
            return []
        total = len(rows)
        by_op: dict[str, list[ResolvedCall]] = defaultdict(list)
        for c in rows:
            by_op[c.op_id].append(c)  # type: ignore[index]
        gold_capable = any(c.gold_defined for c in rows)
        scores: list[OpScore] = []
        for op_id, group in by_op.items():
            n = len(group)
            err = sum(1 for c in group if c.http_error) / n
            forb = sum(1 for c in group if c.forbidden) / n
            red = sum(1 for c in group if c.redundant) / n
            known_vals = [c.known_operation for c in group
                          if c.known_operation is not None]
            known = (sum(1 for k in known_vals if k) / len(known_vals)
                     if known_vals else None)
            if gold_capable:
                gold_rows = [c for c in group if c.gold_defined]
                off: float | None = (
                    sum(1 for c in gold_rows if c.off_gold) / len(gold_rows)
                    if gold_rows else None
                )
            else:
                off = None
            unavailable: set[str] = set()
            if off is None:
                unavailable.add("off_gold_rate")
            expected = self.expected_share.get(op_id) if self.has_gold else None
            excess = None
            if expected is not None:
                excess = (n / total) - expected
            elif self.has_gold:
                excess = (n / total) - 0.0  # never in gold ⇒ all usage is excess
            else:
                unavailable.add("excess_usage")
            if off is not None:
                stumble: float | None = (err + forb + off) / 3.0
            else:
                stumble = None
                unavailable.add("stumble_rank")
            resolution: ResolutionKind = group[0].resolution
            if any(c.resolution == "parsed" for c in group):
                resolution = "parsed"
            scores.append(OpScore(
                op_id=op_id,
                family=group[0].family,
                calls=n,
                usage_share=n / total,
                error_rate=err,
                forbidden_rate=forb,
                off_gold_rate=off,
                redundant_rate=red,
                known_rate=known,
                resolution=resolution,
                unavailable=frozenset(unavailable),
                expected_share=expected if self.has_gold else None,
                excess_usage=excess,
                stumble_rate=stumble,
            ))
        return scores


def _fidelity_tag(resolution: str) -> str:
    return " [parsed]" if resolution == "parsed" else ""


def resolve_call(
    call: dict[str, Any],
    variant: dict[str, Any],
    *,
    gold: Iterable[str] | None = None,
    seen_signatures: set[str] | None = None,
) -> tuple[str | None, ResolutionKind, bool]:
    """Map one persisted call onto ``(op_id, resolution, is_discovery)``.

    Predicates on ``trace.variant`` axes — never on preset name.
    """
    del gold, seen_signatures  # used by callers around the resolve, not here
    transport = variant.get("transport")
    discovery = variant.get("discovery")
    invocation = variant.get("invocation")
    body = call.get("call") or {}

    if transport in (Transport.NONE.value, Transport.IN_PROCESS.value,
                     "none", "in-process"):
        return None, "excluded", False

    tool = body.get("tool")
    args = body.get("args") or {}

    if discovery in (Discovery.META_TOOLS.value, "meta-tools"):
        if tool in (SEARCH, DESCRIBE) or tool in _DISCOVERY_TOOLS - {INVOKE}:
            return tool, "operation_id", True
        if tool == INVOKE or tool == "invoke_operation":
            op = args.get("operation_id")
            return (str(op) if op else None), "operation_id", False
        if tool:
            return str(tool), "tool", False

    if invocation in (Invocation.TOOL_CALL.value, "tool-call"):
        if tool in _DISCOVERY_TOOLS:
            return tool, "tool", True
        return (str(tool) if tool else None), "tool", False

    if invocation in (Invocation.SHELL.value, Invocation.CODE.value,
                      "shell", "code"):
        parsed = _parse_raw(body.get("raw") or "", tool=tool)
        return parsed, "parsed", False

    return (str(tool) if tool else None), "tool", False


def family_of(op_id: str, *, tags: dict[str, str] | None = None) -> str:
    """OpenAPI tag if known; else the resource stem after the verb prefix."""
    if tags and op_id in tags:
        return tags[op_id]
    for prefix in (
        "get_", "list_", "create_", "update_", "patch_", "replace_",
        "delete_", "archive_", "search_", "describe_", "invoke_",
    ):
        if op_id.startswith(prefix):
            return op_id[len(prefix):] or op_id
    return op_id


def gold_ops_from_sequence(sequence: Iterable[Any]) -> tuple[str, ...]:
    """Normalize a task's gold_call_sequence into op id strings."""
    out: list[str] = []
    for call in sequence:
        if isinstance(call, dict):
            tool = call.get("tool")
        else:
            tool = getattr(call, "tool", None)
        if tool:
            out.append(str(tool))
    return tuple(out)


def gold_by_task_from_rows(rows: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    """Pull optional ``gold_ops`` lists off ledger rows (tests / future packs)."""
    out: dict[str, tuple[str, ...]] = {}
    for row in rows:
        ops = row.get("gold_ops")
        tid = row.get("task_id")
        if ops and tid:
            out[str(tid)] = tuple(str(o) for o in ops)
    return out


def expected_share_from_gold(
    gold_by_task: dict[str, tuple[str, ...]],
) -> dict[str, float]:
    """Frequency of each op across gold sequences → expected usage share."""
    counts: Counter[str] = Counter()
    for ops in gold_by_task.values():
        counts.update(ops)
    total = sum(counts.values()) or 1
    return {op: n / total for op, n in counts.items()}


def build_ledger(
    rows: list[dict[str, Any]],
    traces_dir: str | Path,
    *,
    gold_by_task: dict[str, list[str] | tuple[str, ...]] | None = None,
) -> OpLedger:
    """Join ledger rows to traces and resolve every call."""
    traces_dir = Path(traces_dir)
    from_rows = gold_by_task_from_rows(rows)
    merged: dict[str, tuple[str, ...]] = dict(from_rows)
    if gold_by_task:
        for tid, ops in gold_by_task.items():
            merged[str(tid)] = tuple(str(o) for o in ops)

    ledger = OpLedger(
        gold_by_task=merged,
        expected_share=expected_share_from_gold(merged),
    )
    by_run = {r.get("run_id"): r for r in rows if r.get("run_id")}

    for trace in _iter_traces(traces_dir):
        row = by_run.get(trace.get("run_id")) or {}
        variant = trace.get("variant") or {}
        arm = row.get("arm") or variant.get("preset") or "?"
        transport = variant.get("transport")
        if transport in ("none", "in-process", Transport.NONE.value,
                         Transport.IN_PROCESS.value):
            ledger.excluded_arms.setdefault(
                arm,
                "transport has no target calls",
            )
            continue

        task_id = str(trace.get("task_id") or row.get("task_id") or "")
        gold = set(merged.get(task_id, ()))
        gold_defined = bool(gold)
        run_failed = row.get("outcome") not in (None, "pass", "abstain")
        answerable = bool(row.get("answerable", True))
        task_class = str(row.get("task_class") or "?")
        core_id = str(row.get("core_id") or "")

        seen: set[str] = set()
        for call in trace.get("calls") or []:
            op_id, kind, is_discovery = resolve_call(call, variant)
            if is_discovery:
                ledger.discovery_calls += 1
                continue
            if kind == "excluded" or op_id is None:
                continue
            sig = json.dumps(call.get("call") or {}, sort_keys=True, default=str)
            redundant = sig in seen
            seen.add(sig)
            result = call.get("result") or {}
            status = result.get("status")
            http_error = (
                (isinstance(status, int) and status >= 400)
                or bool(result.get("error"))
            )
            off_gold = gold_defined and answerable and op_id not in gold
            ledger.calls.append(ResolvedCall(
                op_id=op_id,
                family=family_of(op_id),
                arm=arm,
                task_class=task_class,
                answerable=answerable,
                core_id=core_id,
                resolution=kind,
                discovery=False,
                http_error=http_error,
                forbidden=bool(call.get("forbidden")),
                known_operation=call.get("known_operation"),
                off_gold=off_gold,
                gold_defined=gold_defined and answerable,
                redundant=redundant,
                run_failed=bool(run_failed),
            ))
    return ledger


def _parse_raw(raw: str, *, tool: str | None) -> str | None:
    """Best-effort extraction from shell/code bodies. Labelled ``parsed``."""
    if tool and re.fullmatch(r"[A-Za-z_][\w]*", tool):
        return tool
    m = re.search(r"operations\.([A-Za-z_][\w]*)", raw)
    if m:
        return m.group(1)
    m = re.search(r"\$BASE_URL(/[^\s\"'|]+)", raw)
    if m:
        path = m.group(1).split("?")[0]
        parts = [p for p in path.split("/") if p and not p.startswith("{")]
        if parts:
            return "_".join(parts[:2])
    return None


def _iter_traces(directory: Path) -> Iterator[dict[str, Any]]:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.json*")):
        try:
            if path.suffix == ".gz" or path.name.endswith(".json.gz"):
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    yield json.load(fh)
            else:
                yield json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
