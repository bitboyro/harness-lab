"""Deep-dive analysis over a finished results directory. Reads, never runs.

Borrowed by ``harness analyze`` and the UI adapter. Standings come from
``cli._build_report`` so they cannot drift from ``harness report``.

Sections are ``(title, headers, rows)`` triples so console, CSV, and JSON
are the same data three ways.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from harness.engine.analysis import OUTCOME_ORDER, SUCCESS

# ---------------------------------------------------------------------------


@dataclass
class Section:
    """One table. `key` names it in the CSV filename and the JSON object.

    `percent` and `money` are declared per section rather than inferred from the
    header text: matching on a substring turned `ktokens_per_success` into a
    percentage because it contains "success". CSV and JSON always carry the raw
    float — only the console formats.
    """

    key: str
    title: str
    headers: list[str]
    rows: list[list[Any]]
    note: str = ""
    percent: frozenset[str] = frozenset()
    money: frozenset[str] = frozenset()


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def _num(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:,.{digits}f}"


def _pctile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile. Explicit because the mean hides the tail that
    actually decides whether a run finishes inside its turn budget."""
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * len(s))) - 1))]


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def s_identity(report, manifest: dict) -> Section:
    keys = ("id", "created_at", "harness_version", "model", "provider",
            "reasoning_effort", "temperature", "caching", "report_class",
            "seed", "cores", "fan_out", "difficulty", "surface_size",
            "repeats", "tasks", "planned", "resumed", "max_turns",
            "concurrency", "mcp_revision", "pack_digest", "plan_id")
    rows = [[k, manifest.get(k, "—")] for k in keys if k in manifest]
    rows.append(["arms", ", ".join(sorted(report.arms))])
    rows.append(["MDE (pp)", _num(report.mde_pp, 1)])
    return Section("identity", "Run identity", ["field", "value"], rows)


def s_standings(report, order: list[str]) -> Section:
    """The report's own numbers, so this file can be checked against it."""
    rows = []
    for a in order:
        x = report.arms[a]
        ci = x.success_ci
        rows.append([
            a, x.name, x.n, len(x.graded),
            x.success_rate, (ci[0] if ci else None), (ci[1] if ci else None),
            report.lift(a), x.abstention_accuracy, x.harm_rate,
            x.truncation_rate, x.silent_failure_rate,
            x.cost_per_success(report.pricing),
            x.mean("wall_clock_seconds"),
            report.rank_value(a, "score"),
            "yes" if report.below_mde(a) else "",
        ])
    return Section(
        "standings", "Standings (matches report.html)",
        ["arm", "name", "n", "graded", "success", "ci_lo", "ci_hi", "lift",
         "abstain", "harm", "truncation", "silent_failure", "cost_per_success",
         "mean_secs", "score", "below_mde"],
        rows,
        note="lift is success minus Z0's. below_mde: the lead is inside the noise floor.",
        percent=frozenset({"success", "ci_lo", "ci_hi", "lift", "abstain", "harm",
                           "truncation", "silent_failure"}),
        money=frozenset({"cost_per_success"}),
    )


def s_outcomes(report, order: list[str]) -> Section:
    rows = []
    for a in order:
        c = report.arms[a].outcome_counts()
        rows.append([a, *[c.get(o, 0) for o in OUTCOME_ORDER], sum(c.values())])
    return Section("outcomes", "Outcome distribution",
                   ["arm", *OUTCOME_ORDER, "total"], rows,
                   note="ledger 'fail' splits into fail-hedged / fail-confident by the `confident` flag.")


def s_classifier(report, order: list[str]) -> Section:
    """Answer-or-decline treated as a binary decision — the abstention view."""
    rows = []
    for a in order:
        cm = report.arms[a].confusion
        rows.append([a, cm.tp, cm.fp, cm.fn, cm.tn, cm.precision, cm.recall,
                     cm.specificity, cm.f1, cm.mcc, cm.balanced_accuracy])
    return Section("classifier", "Answered-vs-declined as a classifier",
                   ["arm", "tp", "fp", "fn", "tn", "precision", "recall",
                    "specificity", "f1", "mcc", "balanced_accuracy"], rows,
                   note="fp = answered something unanswerable (fabrication).",
                   percent=frozenset({"precision", "recall", "specificity",
                                      "f1", "balanced_accuracy"}))


def s_tokens(rows_by_arm: dict, order: list[str]) -> Section:
    """Decomposed, never totalled — a single number hides the mechanism.

    `cached` is a subset of `input` and `reasoning` a subset of `output` (both
    are provider subsets), so `uncached` is what actually bills at full rate.
    """
    out = []
    for a in order:
        rs = rows_by_arm[a]
        f = lambda k: [r.get(k) or 0 for r in rs]  # noqa: E731
        inp, cac = st.mean(f("input_tokens")), st.mean(f("cached_input_tokens"))
        out.append([
            a, inp, inp - cac, (cac / inp if inp else None),
            st.mean(f("output_tokens")), st.mean(f("reasoning_tokens")),
            st.mean(f("static_tokens")),
            st.mean(f("per_call_overhead_tokens")),
            st.mean(f("session_setup_tokens")),
            sum(f("input_tokens")), sum(f("output_tokens")),
        ])
    return Section("tokens", "Token decomposition (mean per run, totals at right)",
                   ["arm", "input", "uncached", "cache_rate", "output",
                    "reasoning", "static", "per_call_overhead", "session_setup",
                    "total_input", "total_output"], out,
                   percent=frozenset({"cache_rate"}))


def s_efficiency(report, rows_by_arm: dict, cells: dict, order: list[str]) -> Section:
    """The metrics the report does not compute.

    `flaky` is the one that needed `repeats` to exist: the share of (arm, task)
    cells whose repeats disagreed on success. Two arms can tie on success while
    one of them is far less predictable, and success rate alone cannot say so.
    """
    out = []
    for a in order:
        rs = rows_by_arm[a]
        calls = sum(r.get("calls") or 0 for r in rs)
        turns = sum(r.get("turns") or 0 for r in rs)
        wasted = sum((r.get("metrics") or {}).get("wasted_calls") or 0 for r in rs)
        redund = sum((r.get("metrics") or {}).get("redundant_calls") or 0 for r in rs)
        wall = [r.get("wall_clock_seconds") or 0.0 for r in rs]
        succ = sum(1 for r in rs if r["outcome"] in SUCCESS)
        toks = sum((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in rs)
        inp = st.mean([r.get("input_tokens") or 0 for r in rs]) or 1
        stat = st.mean([r.get("static_tokens") or 0 for r in rs])
        disagreed = [v for v in cells[a] if len(v) > 1]
        out.append([
            a,
            (st.mean([0 < sum(v) < len(v) for v in disagreed]) if disagreed else None),
            (calls / turns if turns else None),
            (wasted / calls if calls else None),
            (redund / calls if calls else None),
            _pctile(wall, .50), _pctile(wall, .95), _pctile(wall, .99), max(wall),
            (calls / len(rs) if rs else None),
            (toks / succ / 1000 if succ else None),
            stat / inp,
        ])
    return Section("efficiency", "Derived efficiency and stability",
                   ["arm", "flaky_rate", "calls_per_turn", "wasted_call_rate",
                    "redundant_call_rate", "p50_secs", "p95_secs", "p99_secs",
                    "max_secs", "calls_per_run", "ktokens_per_success",
                    "static_share_of_input"], out,
                   note="flaky_rate: share of (arm,task) cells whose repeats disagreed on success.",
                   percent=frozenset({"flaky_rate", "wasted_call_rate",
                                      "redundant_call_rate",
                                      "static_share_of_input"}))


def s_by_class(report, order: list[str]) -> Section:
    classes = report.task_classes
    rows = [[a, *[report.arms[a].by_class().get(c) for c in classes]] for a in order]
    return Section("by_class", "Success by task class", ["arm", *classes], rows,
                   percent=frozenset(classes))


def s_fabrication(rows_by_arm: dict, order: list[str]) -> Section:
    """Fabrication measured against the tasks where it is possible at all.

    Dividing false positives by *every* task understates it — only the
    unanswerable ones offer the opportunity to invent an answer.
    """
    rows = []
    for a in order:
        rs = rows_by_arm[a]
        una = [r for r in rs if not r.get("answerable")]
        fp = sum(1 for r in una if r["outcome"] == "false-positive")
        wrong_confident = sum(1 for r in rs if r.get("confident")
                              and r["outcome"] in ("fail", "false-positive"))
        rows.append([a, len(una), fp, (fp / len(una) if una else None),
                     wrong_confident, (wrong_confident / len(rs) if rs else None)])
    return Section("fabrication", "Fabrication and confident wrongness",
                   ["arm", "unanswerable_n", "false_positives",
                    "fabrication_rate", "confident_wrong", "confident_wrong_rate"],
                   rows,
                   percent=frozenset({"fabrication_rate", "confident_wrong_rate"}))


def s_metrics(rows: list[dict], order: list[str]) -> Section:
    """Every `metrics.*` key: coverage first, because a mean over 11 of 1,380
    observations is not comparable with a mean over 1,309."""
    per: dict[str, list] = defaultdict(list)
    for r in rows:
        for k, v in (r.get("metrics") or {}).items():
            per[k].append(v)
    out = []
    for k in sorted(per):
        vals = [v for v in per[k] if isinstance(v, (int, float)) and not isinstance(v, bool)]
        nulls = len(per[k]) - len(vals)
        out.append([k, len(vals), nulls, round(100 * nulls / len(per[k]), 1),
                    (min(vals) if vals else None),
                    (st.mean(vals) if vals else None),
                    (max(vals) if vals else None)])
    return Section("metrics", "metrics.* coverage and range",
                   ["metric", "n", "nulls", "null_pct", "min", "mean", "max"], out)


def s_cores(rows: list[dict]) -> Section:
    """Grades the TASKS, not the arms.

    A core every arm fails is far more often a broken task than a hard one, and
    a core every arm passes buys no discrimination for the money it costs. Both
    are worth knowing before paying for the next matrix.
    """
    by_core: dict[str, list] = defaultdict(list)
    arms_per: dict[str, set] = defaultdict(set)
    for r in rows:
        by_core[r["core_id"]].append(r["outcome"] in SUCCESS)
        arms_per[r["core_id"]].add(r["arm"])
    rows_out = []
    for core in sorted(by_core):
        v = by_core[core]
        rate = sum(v) / len(v)
        rows_out.append([core, len(v), len(arms_per[core]), rate,
                         "all-fail" if rate == 0 else
                         "all-pass" if rate == 1 else ""])
    rows_out.sort(key=lambda r: r[3])
    return Section("cores", "Per-core difficulty (task diagnostics)",
                   ["core_id", "n", "arms", "success_rate", "flag"], rows_out,
                   percent=frozenset({"success_rate"}),
                   note="all-fail is usually a broken task; all-pass discriminates nothing.")


def s_dead_fields(rows: list[dict]) -> Section:
    """What the run did NOT measure.

    A field that is always zero looks like a measurement until you check it.
    Naming them keeps a reader from reading 'no forbidden calls' as evidence
    when the counter was simply never incremented.
    """
    top: dict[str, list] = defaultdict(list)
    for r in rows:
        for k, v in r.items():
            if k in ("metrics", "axes", "retries", "clobbered"):
                continue
            top[k].append(v)
        for k, v in (r.get("metrics") or {}).items():
            top[f"metrics.{k}"].append(v)
    out = []
    for k in sorted(top):
        vals = top[k]
        nn = [v for v in vals if v is not None]
        nulls = len(vals) - len(nn)
        verdict = ""
        if not nn:
            verdict = "ALWAYS NULL"
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0
                 for v in nn):
            verdict = "ALWAYS ZERO"
        elif len(set(map(str, nn))) == 1:
            verdict = f"CONSTANT ({nn[0]})"
        elif nulls / len(vals) > 0.9:
            verdict = f"{100 * nulls / len(vals):.1f}% NULL"
        if verdict:
            out.append([k, len(vals), nulls, verdict])
    return Section("dead_fields", "Fields carrying no signal in this run",
                   ["field", "n", "nulls", "verdict"], out,
                   note="constants are usually run-level config; zeros and nulls are unmeasured.")


def s_verdict(report, order: list[str]) -> list[Section]:
    """The report's own grading, dimension by dimension.

    The composite is one number and it hides the trade. Printing each dimension's
    winner beside it is what shows that the most accurate arm and the least
    destructive arm are usually not the same arm — which makes "best" a
    preference someone stated, not a fact the run measured.
    """
    from harness.engine.winner import evaluate
    v = evaluate(report, report.weights)
    dims = [d for d in v.dimensions]

    grid = []
    for a in order:
        if a not in v.scores:
            continue
        row = [a, v.scores[a]]
        for d in dims:
            row += [d.raw.get(a), d.normalised.get(a)]
        grid.append(row)
    headers = ["arm", "score"]
    for d in dims:
        headers += [f"{d.key}_raw", f"{d.key}_norm"]
    grid_sec = Section("verdict_grid", "Composite grading, per dimension", headers, grid,
                       note="norm is 0..1 with higher always better; score is the weighted sum.",
                       percent=frozenset(f"{d.key}_norm" for d in dims))

    summary = [["winner", ", ".join(v.tied_leaders) or "—"],
               ["reason", v.reason or "—"]]
    for d in dims:
        best = max(d.normalised, key=lambda k: d.normalised[k]) if d.normalised else None
        summary.append([f"best on {d.key} (w={d.weight:g})",
                        f"{best}{' — SEPARATED NOTHING' if d.flat else ''}"])
    for k, why in v.dropped.items():
        summary.append([f"dropped: {k}", why])
    for c in v.caveats:
        summary.append(["caveat", c])
    return [Section("verdict", "Verdict", ["field", "value"], summary), grid_sec]


#: The authored skill was applied on top of three different packagings. Holding
#: the file constant and varying only what it sits on is the cleanest read the
#: matrix offers on what a skill is actually worth.
SKILL_PAIRS = (("A1", "B1-auth"), ("A2", "B2-auth"), ("D1", "D2-auth"))


def s_skill_effect(report) -> Section | None:
    """What the identical authored skill bought, per packaging family."""
    rows = []
    for base, withskill in SKILL_PAIRS:
        if base not in report.arms or withskill not in report.arms:
            continue
        b, w = report.arms[base], report.arms[withskill]
        def d(x, y):  # noqa: E306
            return None if x is None or y is None else y - x
        rows.append([
            f"{base} → {withskill}",
            b.success_rate, w.success_rate, d(b.success_rate, w.success_rate),
            b.abstention_accuracy, w.abstention_accuracy,
            d(b.abstention_accuracy, w.abstention_accuracy),
            b.harm_rate, w.harm_rate, d(b.harm_rate, w.harm_rate),
            b.confusion.fp, w.confusion.fp,
            b.truncation_rate, w.truncation_rate,
            d(b.truncation_rate, w.truncation_rate),
        ])
    if not rows:
        return None
    return Section("skill_effect", "What the authored skill bought (same file, three packagings)",
                   ["pair", "success_before", "success_after", "success_delta",
                    "abstain_before", "abstain_after", "abstain_delta",
                    "harm_before", "harm_after", "harm_delta",
                    "fp_before", "fp_after",
                    "trunc_before", "trunc_after", "trunc_delta"], rows,
                   note="delta is after minus before; the skill file is identical across all three.",
                   percent=frozenset({"success_before", "success_after", "success_delta",
                                      "abstain_before", "abstain_after", "abstain_delta",
                                      "harm_before", "harm_after", "harm_delta",
                                      "trunc_before", "trunc_after", "trunc_delta"}))


def s_harm_detail(rows: list[dict]) -> Section:
    """Which fields actually got destroyed, and by whom.

    `harm_rate` says how often; this says *what*. A single field taking most of
    the damage across every arm is a property of the API, not of the packaging —
    and that is a finding about the target, not the tooling.
    """
    leaf: Counter = Counter()
    by_arm: Counter = Counter()
    paths: Counter = Counter()
    for r in rows:
        for f in (r.get("clobbered") or []):
            s = str(f)
            paths[s] += 1
            leaf[s.rsplit(".", 1)[-1]] += 1
            by_arm[r["arm"]] += 1
    out = [["field: " + k, v, ""] for k, v in leaf.most_common(10)]
    out += [["arm: " + k, v, ""] for k, v in by_arm.most_common()]
    out.append(["distinct paths", len(paths), ""])
    out.append(["total events", sum(paths.values()), ""])
    return Section("harm_detail", "What got destroyed", ["what", "events", ""], out,
                   note="clobbered JSONPaths, aggregated by leaf field name and by arm.")


def s_payload(rows_by_arm: dict, order: list[str]) -> Section:
    """How much of what the API returned was ever used.

    Low payload efficiency is a property of the response shape, so it moves the
    blame from the packaging to the API's own verbosity.
    """
    out = []
    for a in order:
        vals = [(r.get("metrics") or {}).get("payload_efficiency") for r in rows_by_arm[a]]
        v = [x for x in vals if x is not None]
        arg = [(r.get("metrics") or {}).get("argument_validity") for r in rows_by_arm[a]]
        arg = [x for x in arg if x is not None]
        out.append([a, len(v), (st.mean(v) if v else None),
                    (1 - st.mean(v) if v else None),
                    (_pctile(v, .95) if v else None),
                    (st.mean(arg) if arg else None)])
    return Section("payload", "Payload efficiency and argument validity",
                   ["arm", "n", "payload_efficiency", "payload_wasted",
                    "p95_efficiency", "argument_validity"], out,
                   note="payload_wasted = 1 - efficiency: share of returned bytes never used in an answer.",
                   percent=frozenset({"payload_efficiency", "payload_wasted",
                                      "p95_efficiency", "argument_validity"}))


def s_contrasts(report) -> Section:
    from harness.engine.stats import analyse
    try:
        sr = analyse(report)
    except Exception as e:  # noqa: BLE001 — a missing contrast must not kill the run
        return Section("contrasts", "Contrasts", ["error"], [[str(e)]])
    rows = []
    for c in sr.contrasts:
        ci = c.ci
        rows.append([c.arm_a, c.arm_b, "confirmatory" if c.confirmatory else "exploratory",
                     c.n_cores, c.diff, (ci[0] if ci else None), (ci[1] if ci else None),
                     c.p_raw, c.p_adjusted,
                     "yes" if c.significant else "", c.hypothesis])
    return Section("contrasts", "Contrasts (confirmatory are Holm-corrected)",
                   ["arm_a", "arm_b", "kind", "n_cores", "diff", "ci_lo", "ci_hi",
                    "p_raw", "p_adjusted", "significant", "hypothesis"], rows,
                   note="exploratory contrasts are never called significant — no family to correct against.",
                   percent=frozenset({"diff", "ci_lo", "ci_hi"}))


def s_ops(report) -> Section | None:
    """The operation ledger, when traces were present to build it."""
    ledger = getattr(report, "op_ledger", None)
    if not ledger:
        return None
    rows = []
    for entry in getattr(ledger, "rows", []) or []:
        rows.append([getattr(entry, k, "") for k in
                     ("arm", "operation", "calls", "on_gold", "off_gold", "excess")])
    if not rows:
        return None
    return Section("operations", "Operation ledger",
                   ["arm", "operation", "calls", "on_gold", "off_gold", "excess"], rows)


# ---------------------------------------------------------------------------


def s_arms_wide(sections: list[Section], sort: str | None, desc: bool) -> Section:
    """Every per-arm number in one row, sortable by any of them.

    Assembled by joining the sections that are already keyed by arm, rather than
    recomputing: a wide table that recomputed its columns could disagree with the
    detail table three screens up, and then neither could be trusted. A column
    name that appears in two sections is prefixed with its section key, so
    `payload.n` and `standings.n` stay distinct.
    """
    seen: Counter = Counter()
    cols: list[tuple[str, str, int]] = []          # (out_name, section_key, idx)
    percent: set[str] = set()
    money: set[str] = set()
    data: dict[str, dict[str, Any]] = defaultdict(dict)

    for sec in sections:
        if sec.key == "arms" or not sec.headers or sec.headers[0] != "arm":
            continue
        for i, h in enumerate(sec.headers[1:], start=1):
            seen[h] += 1
            name = h if seen[h] == 1 else f"{sec.key}.{h}"
            cols.append((name, sec.key, i))
            if h in sec.percent:
                percent.add(name)
            if h in sec.money:
                money.add(name)
        for row in sec.rows:
            for i, h in enumerate(sec.headers[1:], start=1):
                seen_name = h if seen[h] == 1 else f"{sec.key}.{h}"
                data[row[0]][seen_name] = row[i]

    headers = ["arm"] + [c[0] for c in cols]
    rows = [[arm] + [data[arm].get(c[0]) for c in cols] for arm in data]

    if sort:
        if sort not in headers:
            print(f"warning: --sort {sort!r} is not a column; leaving order alone.\n"
                  f"  available: {', '.join(headers)}", file=sys.stderr)
        else:
            j = headers.index(sort)
            # None sinks to the bottom whichever way we sort — an absent value is
            # not a small one, and letting it win a "lowest cost" sort would lie.
            rows.sort(key=lambda r: (r[j] is None,
                                     r[j] if isinstance(r[j], (int, float)) else str(r[j])),
                      reverse=desc)
    return Section("arms", "Every per-arm metric (sortable)", headers, rows,
                   note=("sorted by " + sort if sort else
                         "pass --sort COLUMN [--desc] to reorder; --list-columns to see them all"),
                   percent=frozenset(percent), money=frozenset(money))


def render_console(sec: Section) -> str:
    def cell(v: Any, header: str) -> str:
        if v is None:
            return "n/a"
        if isinstance(v, float):
            if header in sec.percent:
                return _pct(v)
            if header in sec.money:
                return f"${v:,.4f}"
            return f"{v:,.4g}"
        return str(v)

    body = [[cell(v, sec.headers[i]) for i, v in enumerate(r)] for r in sec.rows]
    widths = [max(len(sec.headers[i]), *(len(r[i]) for r in body)) if body
              else len(sec.headers[i]) for i in range(len(sec.headers))]
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(sec.headers))
    out = [f"\n{'=' * len(sec.title)}\n{sec.title}\n{'=' * len(sec.title)}", line,
           "  ".join("-" * w for w in widths)]
    out += ["  ".join(r[i].ljust(widths[i]) for i in range(len(r))) for r in body]
    if sec.note:
        out.append(f"\n  note: {sec.note}")
    return "\n".join(out)


def build_sections(
    results: Path,
    *,
    sort: str | None = None,
    desc: bool = False,
    only: Iterable[str] | None = None,
) -> tuple[list[Section], dict[str, Any]]:
    """Return (sections, manifest) for a finished results directory."""
    from harness.cli import _build_report
    from harness.engine.results import ResultStore

    results = Path(results)
    if not (results / "results.jsonl").is_file():
        raise FileNotFoundError(f"no results.jsonl in {results}")

    store = ResultStore(results)
    report = _build_report(store)
    manifest = store.manifest()
    rows = list(store.rows())

    graded = [r for r in rows if r["outcome"] != "infra-error"]
    by_arm: dict[str, list] = defaultdict(list)
    for r in graded:
        by_arm[r["arm"]].append(r)
    cells: dict[str, list] = defaultdict(list)
    tmp: dict[tuple, list] = defaultdict(list)
    for r in graded:
        tmp[(r["arm"], r["task_id"])].append(r["outcome"] in SUCCESS)
    for (arm, _), v in tmp.items():
        cells[arm].append(v)

    order = [s.arm for s in report.ranked("score")]

    sections = [s for s in (
        s_identity(report, manifest),
        s_standings(report, order),
        *s_verdict(report, order),
        s_outcomes(report, order),
        s_classifier(report, order),
        s_skill_effect(report),
        s_tokens(by_arm, order),
        s_efficiency(report, by_arm, cells, order),
        s_by_class(report, order),
        s_fabrication(by_arm, order),
        s_harm_detail(graded),
        s_payload(by_arm, order),
        s_metrics(graded, order),
        s_contrasts(report),
        s_cores(graded),
        s_dead_fields(rows),
        s_ops(report),
    ) if s is not None]

    sections.insert(1, s_arms_wide(sections, sort, desc))

    if only is not None:
        keep = {k.strip() for k in only if k and k.strip()}
        if keep:
            sections = [s for s in sections if s.key in keep]

    return sections, manifest


def sections_to_payload(
    sections: list[Section],
    *,
    results: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    from harness import __version__

    return {
        "harness_version": __version__,
        "run": {
            "id": manifest.get("id"),
            "model": manifest.get("model"),
            "report_class": manifest.get("report_class"),
        },
        "generated_from": str(Path(results).resolve()),
        "sections": {
            s.key: {
                "title": s.title,
                "note": s.note,
                "headers": s.headers,
                "rows": [dict(zip(s.headers, r)) for r in s.rows],
            }
            for s in sections
        },
    }


def analyze_directory(
    results: Path,
    *,
    sort: str | None = None,
    desc: bool = False,
    only: Iterable[str] | None = None,
) -> dict[str, Any]:
    """JSON envelope for adapter / UI (free; re-runs nothing)."""
    sections, manifest = build_sections(results, sort=sort, desc=desc, only=only)
    return sections_to_payload(sections, results=results, manifest=manifest)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Deep-dive analysis over a finished results directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("results", type=Path, help="a finished results directory")
    p.add_argument("--csv", type=Path, metavar="DIR", help="write one CSV per section")
    p.add_argument(
        "--json",
        type=str,
        metavar="PATH",
        help="write every section as JSON (use - for stdout)",
    )
    p.add_argument("--only", metavar="KEYS", help="comma-separated section keys")
    p.add_argument("--quiet", action="store_true", help="suppress console tables")
    p.add_argument("--sort", metavar="COLUMN",
                   help="sort the wide per-arm table by this column (e.g. f1, uncached)")
    p.add_argument("--desc", action="store_true", help="sort descending")
    p.add_argument("--list-columns", action="store_true",
                   help="print the sortable column names and exit")
    args = p.parse_args(argv)

    only = [k.strip() for k in args.only.split(",")] if args.only else None

    try:
        sections, manifest = build_sections(
            args.results, sort=args.sort, desc=args.desc, only=only,
        )
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.list_columns:
        wide = next((s for s in sections if s.key == "arms"), None)
        if wide is None:
            # Rebuild without --only so columns exist.
            sections, _ = build_sections(args.results, sort=args.sort, desc=args.desc)
            wide = next(s for s in sections if s.key == "arms")
        print("\n".join(wide.headers))
        return 0

    if not args.quiet and args.json != "-":
        for s in sections:
            print(render_console(s))
        print()

    if args.csv:
        args.csv.mkdir(parents=True, exist_ok=True)
        for s in sections:
            with (args.csv / f"{s.key}.csv").open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(s.headers)
                w.writerows(s.rows)
        print(f"wrote {len(sections)} CSVs to {args.csv}/")

    if args.json:
        payload = sections_to_payload(sections, results=args.results, manifest=manifest)
        text = json.dumps(payload, indent=2, default=str)
        if args.json == "-":
            print(text)
        else:
            path = Path(args.json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"wrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
