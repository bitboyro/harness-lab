"""The comparison report, as text.

Reads a `Comparison` and formats every number through `Comparison.fmt` /
`fmt_delta`, which is also what the HTML renderer does. Neither computes
anything; the anti-drift test asks the shared formatter for a string and
asserts it appears in both outputs.

Section order is fixed and matches the HTML exactly. The one rule worth stating
outright: **what differed in the setup comes before any result**. A delta read
without knowing the runs used different difficulty settings is worse than no
delta at all.
"""

from __future__ import annotations

from .analysis import POOLING_RULE, RANK_KEYS
from .comparison import NOT_RECORDED, Comparison

#: Dimensions tabulated when the caller does not say.
DEFAULT_KEYS = ("success", "lift", "score")


def _col(text: str, width: int) -> str:
    """Right-align in a fixed column, marking anything that had to be cut.

    A silently truncated parameter is worse than an obviously truncated one: a
    reader comparing two 40-character task-set digests needs to know the tail
    is missing rather than conclude the two matched.
    """
    if len(text) > width:
        return text[:width - 1] + "…"
    return text.rjust(width)


def _param_table(names: list[str], labels: list[str],
                 rows: list[tuple[str, str, list[str]]]) -> list[str]:
    """A parameter matrix sized to its content rather than to a guess."""
    name_w = max([len(n) for n in names] + [9]) + 2
    value_w = min(34, max([len(l) for l in labels]
                          + [len(v) for _, _, vs in rows for v in vs]) + 2)
    head = f"    {'':<{name_w}}{'source':<10}" + " ".join(
        _col(l, value_w) for l in labels)
    out = [head]
    for name, source, values in rows:
        out.append(f"    {name:<{name_w}}{source:<10}"
                   + " ".join(_col(v, value_w) for v in values))
    return out


def render(comparison: Comparison, *, sort: str = "score",
           keys: tuple[str, ...] = DEFAULT_KEYS,
           glossary: bool = False, all_params: bool = False) -> str:
    """The whole comparison, as text."""
    lines: list[str] = []
    lines += _header(comparison)
    lines += _pooling(comparison)
    lines += _power(comparison)
    lines += _parameters(comparison)
    lines += _not_compared(comparison)
    lines += _head_to_head(comparison, sort, keys)
    lines += _contrasts(comparison)
    if all_params or glossary:
        lines += _all_parameters(comparison)
    lines += _footer(comparison)
    if glossary:
        from .glossary import render_text as render_glossary
        lines += ["", render_glossary(78)]
    return "\n".join(lines)


def _header(c: Comparison) -> list[str]:
    lines = [f"compare: {' · '.join(c.labels)}", ""]
    for ref in c.runs:
        report = ref.report
        marker = "reference" if ref is c.reference else "vs"
        mde = ("mde n/a" if report.mde_pp is None
               else f"mde {report.mde_pp:.0f}pp")
        lines.append(
            f"  {marker:<9} {ref.label:<22} {ref.path}"
        )
        lines.append(
            f"  {'':<9} {len(report.rows):>5} runs  {len(report.arms):>2} arms  "
            f"{report.task_count:>3} tasks  model={report.model}  "
            f"[{report.report_class}]  {mde}"
        )
    lines.append("")
    lines.append("  Every delta below is measured against "
                 f"{c.reference.label}. Swapping the order flips every sign.")
    lines.append("")
    return lines


def _pooling(c: Comparison) -> list[str]:
    if not c.pooling_refused:
        return []
    lines = ["REFUSING TO POOL — these runs are not measuring the same thing:"]
    for brk in c.pooling_breaks:
        lines.append(f"  {brk.render()}")
    lines.append("Deltas across this boundary are still shown, marked ‡, and "
                 "are not findings:")
    lines.append("the rates are real, but their difference answers a question "
                 "nobody asked.")
    lines.append("")
    return lines


def _power(c: Comparison) -> list[str]:
    if c.mde_pp is None:
        return ["  Noise floor unknown — no run recorded the core count power "
                "is computed from.", ""]
    return [
        f"  Noise floor: the least-powered run here detects {c.mde_pp:.0f}pp. "
        "A cross-run gap is",
        "  read against a larger floor still — both measurements carry error "
        "and errors add",
        "  (approximated as the root sum of squares), so each contrast below "
        "states its own.",
        "",
    ]


def _parameters(c: Comparison) -> list[str]:
    """What differed in the setup. Before any result, deliberately."""
    lines = ["  what differs — the setup, before any result:"]
    differing = c.differing
    if not differing:
        lines.append("    nothing recorded differs between these runs.")
    else:
        lines += _param_table(
            [p.name for p in differing], c.labels,
            [(p.name, "/".join(sorted(set(p.sources.values()))) or "-",
              [Comparison.fmt(p.name, p.values[l]) for l in c.labels])
             for p in differing])

    uncertain = c.uncertain
    if uncertain:
        lines.append("")
        lines.append("    cannot be ruled out as a difference — recorded by "
                     "some runs, not by others:")
        for row in uncertain:
            missing = ", ".join(row.unknown_runs)
            lines.append(f"      {row.name} — not recorded by {missing}")
        lines.append("      (older ledgers predate these manifest fields; "
                     "they are unknown, not equal)")

    conflicts = c.conflicts
    if conflicts:
        lines.append("")
        lines.append("    manifest disagrees with the ledger — the rows are "
                     "what actually happened:")
        for run, name, stated, observed in conflicts:
            lines.append(f"      {run}: {name} manifest={stated} rows={observed}")

    lines.append("")
    return lines


def _not_compared(c: Comparison) -> list[str]:
    """Arms only some runs ran. Shown before the head-to-head, on purpose."""
    exclusive = c.exclusive_arms
    if not exclusive:
        return []
    lines = [
        "  not compared — these arms are missing from at least one run:",
        "    (excluded from every delta below: there is nothing to subtract "
        "from. A blank",
        "     cell reads as a zero, and a zero here would be a claim nobody "
        "measured.)",
        "",
        f"    {'arm':<10}{'n':>5} {'success':>9}  {'95% CI':<18} run",
    ]
    for arm, labels in exclusive.items():
        for label in labels:
            summary = c.summary(label, arm)
            if summary is None:
                continue
            ci = summary.success_ci
            interval = ("n/a" if ci is None
                        else f"[{ci[0]:.0%}, {ci[1]:.0%}]")
            lines.append(
                f"    {arm:<10}{summary.n:>5} "
                f"{Comparison.fmt('success', summary.success_rate):>9}  "
                f"{interval:<18} {label}"
            )
    lines.append("")
    return lines


def _head_to_head(c: Comparison, sort: str,
                  keys: tuple[str, ...]) -> list[str]:
    arms = c.ranked_arms(sort)
    if not arms:
        return ["  no arm is present in every run — there is nothing to "
                "compare head to head.",
                "  The standalone numbers above are the honest summary.", ""]

    lines = []
    for key in keys:
        label, higher_is_better, meaning = RANK_KEYS.get(key, (key, True, ""))
        if key == "score" and not c.score_comparable:
            lines += [
                "  SCORE is not comparable across these runs.",
                "    The composite min-max normalises each dimension within "
                "that run's own set of",
                "    candidate arms. These runs ran different arms, so the two "
                "scores were scaled",
                "    against different ranges and their difference would "
                "measure which arms happened",
                "    to be present, not which packaging is better.",
                "",
            ]
            continue

        direction = "higher is better" if higher_is_better else "lower is better"
        lines.append(f"  {label} by arm — {meaning} ({direction}):")
        if key == "lift":
            lines.append("    each run's lift is against its own Z0, so a "
                         "delta here is a difference of differences.")
        head = f"    {'arm':<10}" + _col(c.reference.label, 14)
        for ref in c.others:
            head += _col(ref.label, 14) + _col("Δ", 12)
        lines.append(head)

        for arm in arms:
            row = f"    {arm:<10}"
            row += _col(Comparison.fmt(key, c.value(c.reference.label, arm, key)), 14)
            for ref in c.others:
                value = Comparison.fmt(key, c.value(ref.label, arm, key))
                delta = c.delta(ref.label, arm, key)
                mark = Comparison.direction(key, delta)
                if c.cross_world(arm, ref.label):
                    mark = "‡"
                elif c.unresolved(ref.label, arm, key):
                    mark = "~"
                row += _col(value, 14) + _col(
                    f"{Comparison.fmt_delta(key, delta)} {mark}", 12)
            lines.append(row)
        lines.append("")

    if any(c.unresolved(r.label, a, k)
           for r in c.others for a in arms for k in keys):
        lines.append("    ~ these samples cannot resolve this gap — not a "
                     "finding.")
    if c.pooling_refused:
        lines.append("    ‡ across a pooling boundary — not a finding at any "
                     "sample size.")
    lines.append("")
    return lines


def _contrasts(c: Comparison) -> list[str]:
    contrasts = c.contrasts()
    if not contrasts:
        return []
    lines = ["  cross-run contrasts — the same arm, measured twice:"]
    for ref in c.others:
        mine = [x for x in contrasts if x.run_b == ref.label]
        if not mine:
            continue
        lines.append(f"    {c.reference.label} -> {ref.label}")
        for contrast in mine:
            lines.append("  " + contrast.render())
        floors = {x.mde_combined for x in mine if x.mde_combined is not None}
        if floors:
            lines.append(f"      combined noise floor "
                         f"{min(floors):.0f}–{max(floors):.0f}pp "
                         "(approximate: root sum of squares over both runs)")
    lines.append("")
    lines.append("    * a difference these samples can resolve   "
                 "~ unpaired   ‡ across a pooling boundary")

    unpaired = [x for x in contrasts if not x.paired and x.comparable]
    if unpaired:
        lines.append("")
        lines.append("    Unpaired, because these runs did not answer the same "
                     "task set:")
        for note in _split(unpaired[0].caveat):
            lines.append(f"      - {note}")
    if not c.same_world:
        lines.append("      Pairing within core needs a matching seed, core "
                     "count, fan-out and difficulty")
        lines.append("      — core ids are positional, so core-000 in one "
                     "world is a different problem.")
    lines.append("")
    return lines


def _split(caveat: str) -> list[str]:
    return [part.strip() for part in caveat.split(";") if part.strip()]


def _all_parameters(c: Comparison) -> list[str]:
    lines = ["  every parameter — the audit trail:"]
    lines += _param_table(
        [p.name for p in c.params], c.labels,
        [(("* " if p.differs else "  ") + p.name,
          "/".join(sorted(set(p.sources.values()))) or "-",
          [Comparison.fmt(p.name, p.values[l]) for l in c.labels])
         for p in c.params])
    lines.append("    * differs between runs")
    lines.append("")
    return lines


def _footer(c: Comparison) -> list[str]:
    parts = [POOLING_RULE]
    excluded = len(c.exclusive_arms)
    if excluded:
        parts.append(f"{excluded} arms were not run everywhere and are "
                     "excluded from every delta.")
    unpaired = sum(1 for x in c.contrasts() if not x.paired and x.comparable)
    if unpaired:
        parts.append(f"{unpaired} of {len(c.contrasts())} contrasts are "
                     "unpaired and can never be called significant.")
    missing = sum(1 for row in c.params
                  if any(v is NOT_RECORDED for v in row.values.values()))
    if missing:
        parts.append(f"{missing} parameters are unrecorded by at least one run "
                     "— unknown, not equal.")
    return ["  " + p for p in parts]
