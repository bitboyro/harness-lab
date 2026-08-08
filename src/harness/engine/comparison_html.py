"""The comparison report, as a self-contained HTML page.

Same rules as `html.py`: inline style, inline SVG, no external requests of any
kind, and the caveats sit at the **top** rather than in a footer — a reader who
learns the runs used different task sets after looking at the bars has already
formed an impression the bars did not earn.

Every number is formatted through `Comparison.fmt` / `fmt_delta`, which is what
`comparison_text.py` does too. That is not a coincidence to be preserved by
discipline: the anti-drift test asks the shared formatter for a string and
asserts it appears in both outputs.

The stylesheet is imported from `html.py` rather than copied. Two stylesheets
drift within a release, and the comparison page has to look like the run page.
"""

from __future__ import annotations

from .analysis import POOLING_RULE, RANK_KEYS
from .comparison import NOT_RECORDED, Comparison
from .comparison_text import DEFAULT_KEYS
from .html import _CSS, _SORT_JS, _e, _th
from .svg import Bar, bar_chart, grouped_bars, legend, palette_css

#: Additions to `html._CSS`, not a replacement for it.
_COMPARE_CSS = """
  .runs { display: grid; gap: 8px; margin: 14px 0 18px; }
  .runchip { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px;
             border: 1px solid var(--grid); border-radius: 8px;
             padding: 9px 13px; font-size: 12px; color: var(--text-secondary); }
  .runchip b { color: var(--text-primary); font-weight: 650; font-size: 13px; }
  .runchip .tag { font-size: 10px; text-transform: uppercase;
                  letter-spacing: 0.05em; color: var(--text-muted);
                  border: 1px solid var(--grid); border-radius: 10px;
                  padding: 1px 7px; }
  .runchip .path { color: var(--text-muted); font-family: ui-monospace, monospace;
                   font-size: 11px; }
  /* The parameter matrix. The first column stays put while the run columns
     scroll, because a value with no parameter name beside it is unreadable. */
  table.params td:first-child, table.params th:first-child {
      position: sticky; left: 0; background: var(--surface-1);
      box-shadow: 1px 0 0 var(--grid); }
  table.params td { vertical-align: top; }
  table.params td.val { text-align: left; font-family: ui-monospace, monospace;
                        font-size: 11px; word-break: break-word; }
  .src { color: var(--text-muted); font-size: 10px; }
  /* Direction of a delta. The glyph carries it, never the tint alone. */
  .delta { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .delta.up   { color: var(--status-good); }
  .delta.down { color: var(--status-critical); }
  .delta.flat, .delta.weak { color: var(--text-muted); }
  .delta .mk { font-size: 10px; margin-left: 3px; }
  td.ref { box-shadow: inset -1px 0 0 var(--grid); }
  .unrec { color: var(--text-muted); font-style: italic; }
"""


def _delta_cell(c: Comparison, label: str, arm: str, key: str) -> str:
    """One delta, with the reason it may not mean anything attached."""
    value = c.delta(label, arm, key)
    text = Comparison.fmt_delta(key, value)
    if value is None:
        return f'<td class="delta flat">{_e(text)}</td>'

    if c.cross_world(arm, label):
        cls, mark, why = "weak", "‡", "across a pooling boundary — not a finding"
    elif c.unresolved(label, arm, key):
        cls, mark, why = "weak", "~", "these samples cannot resolve this gap"
    else:
        mark = Comparison.direction(key, value)
        cls = {"↑": "up", "↓": "down"}.get(mark, "flat")
        why = "higher is better" if RANK_KEYS.get(key, ("", True, ""))[1] \
            else "lower is better"
    return (f'<td class="delta {cls}" data-sort="{value:.6f}">'
            f'<abbr title="{_e(why)}">{_e(text)}'
            f'<span class="mk">{_e(mark)}</span></abbr></td>')


def build_charts(c: Comparison) -> dict[str, str]:
    """Every chart on the page, by name. `--charts` writes these as SVG files."""
    charts: dict[str, str] = {}
    arms = c.ranked_arms("success")
    if not arms:
        return charts

    series = c.labels
    charts["success-by-run"] = grouped_bars(
        arms, series,
        [[c.value(label, arm, "success") for label in series] for arm in arms],
        title="Success by arm, one bar per run")
    charts["success-by-run-legend"] = legend(series)

    # One delta chart per non-reference run. The MDE band and the hatched fill
    # both already mean "not a finding" everywhere else in this codebase, so a
    # delta inside the noise floor is drawn exactly the way a below-MDE lift is.
    for index, ref in enumerate(c.others, start=2):
        bars = []
        for arm in arms:
            delta = c.delta(ref.label, arm, "success")
            # Points, not a fraction: `bar_chart(unit="pp")` labels the value
            # verbatim, and the single-run lift chart already feeds it the
            # same way. A fraction here renders every delta as "0pp".
            cross = c.cross_world(arm, ref.label)
            weak = c.unresolved(ref.label, arm, "success")
            bars.append(Bar(
                label=arm,
                value=None if delta is None else delta * 100,
                muted=delta is None or weak or cross,
                note=("different worlds" if cross
                      else "below MDE" if weak else ""),
                slot=index,
            ))
        floor = next((x.mde_combined for x in c.contrasts()
                      if x.run_b == ref.label and x.mde_combined is not None),
                     None)
        band = None if floor is None else (-floor, floor)
        charts[f"delta-success-{_slug(ref.label)}"] = bar_chart(
            bars, unit="pp", band=band,
            title=f"Success delta in points: {ref.label} minus "
                  f"{c.reference.label}")

    for key in ("abstention", "harm", "trunc"):
        values = [[c.value(label, arm, key) for label in series] for arm in arms]
        if any(v is not None for row in values for v in row):
            charts[f"metric-{key}"] = grouped_bars(
                arms, series, values,
                title=f"{RANK_KEYS[key][0]} by arm, one bar per run")
    return charts


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in text).strip("-").lower()


def render_html(c: Comparison, *, sort: str = "score",
                keys: tuple[str, ...] = DEFAULT_KEYS,
                glossary: bool = True) -> str:
    """The page body. Section order matches `comparison_text.render` exactly."""
    out: list[str] = [
        f"<style>{palette_css()}{_CSS}{_COMPARE_CSS}</style>",
        '<div class="viz"><div class="wrap">',
        f"<h1>compare: {_e(' · '.join(c.labels))}</h1>",
        '<p class="sub">Every delta is measured against '
        f"<b>{_e(c.reference.label)}</b>. Swapping the order flips every "
        "sign.</p>",
        _runs(c),
    ]
    out += [_pooling(c), _power(c), _parameters(c), _not_compared(c)]
    out += [_head_to_head(c, sort, keys), _contrasts(c), _charts(c)]
    out += [_all_parameters(c), _glossary() if glossary else "", _footer(c)]
    out.append("</div></div>")
    out.append(f"<script>{_SORT_JS}</script>")
    return "\n".join(part for part in out if part)


def standalone_html(c: Comparison, *, sort: str = "score",
                    keys: tuple[str, ...] = DEFAULT_KEYS) -> str:
    """A complete document, for writing to a file.

    The charset declaration is not optional: without it a browser guesses
    latin-1 and every em dash in the caveats renders as mojibake — which is
    exactly where the text most needs to be readable.
    """
    title = " vs ".join(c.labels)
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)} — harness comparison</title></head>"
        f"<body>{render_html(c, sort=sort, keys=keys)}</body></html>"
    )


def _runs(c: Comparison) -> str:
    chips = []
    for ref in c.runs:
        report = ref.report
        tag = "reference" if ref is c.reference else "vs"
        mde = ("mde n/a" if report.mde_pp is None
               else f"mde {report.mde_pp:.0f}pp")
        chips.append(
            f'<div class="runchip"><span class="tag">{_e(tag)}</span>'
            f"<b>{_e(ref.label)}</b>"
            f'<span class="path">{_e(ref.path)}</span>'
            f"<span>{len(report.rows):,} runs</span>"
            f"<span>{len(report.arms)} arms</span>"
            f"<span>{report.task_count} tasks</span>"
            f"<span>{_e(report.model)}</span>"
            f"<span>[{_e(report.report_class)}]</span>"
            f"<span>{_e(mde)}</span></div>"
        )
    return '<div class="runs">' + "".join(chips) + "</div>"


def _pooling(c: Comparison) -> str:
    if not c.pooling_refused:
        return ""
    items = "".join(f"<li>{_e(b.render())}</li>" for b in c.pooling_breaks)
    return (
        '<div class="banner stop"><b>Refusing to pool — these runs are not '
        "measuring the same thing.</b>"
        f"<ul>{items}</ul>"
        "Deltas across this boundary are still shown, marked ‡, and are not "
        "findings: the rates are real, but their difference answers a question "
        "nobody asked.</div>"
    )


def _power(c: Comparison) -> str:
    if c.mde_pp is None:
        return ('<div class="banner">Noise floor unknown — no run recorded the '
                "core count power is computed from.</div>")
    return (
        f'<div class="banner">The least-powered run here detects '
        f"<b>{c.mde_pp:.0f}pp</b>. A cross-run gap is read against a larger "
        "floor still: both measurements carry error and errors add "
        "(approximated as the root sum of squares), so each contrast below "
        "states its own.</div>"
    )


def _value_cell(row, label: str, extra: str = "") -> str:
    value = row.values[label]
    text = Comparison.fmt(row.name, value)
    cls = "val unrec" if value is NOT_RECORDED else "val"
    return f'<td class="{cls}{extra}">{_e(text)}</td>'


def _param_table(c: Comparison, rows, *, mark_differs: bool = False) -> str:
    head = ("<tr>" + _th("parameter", "parameter diff")
            + "<th>source</th>"
            + "".join(f"<th>{_e(l)}</th>" for l in c.labels) + "</tr>")
    body = []
    for row in rows:
        source = "/".join(sorted(set(row.sources.values()))) or "—"
        name = ("★ " if mark_differs and row.differs else "") + row.name
        body.append(
            f'<tr><td><abbr title="{_e(row.parameter.meaning)}">{_e(name)}</abbr></td>'
            f'<td class="src">{_e(source)}</td>'
            + "".join(_value_cell(row, l) for l in c.labels) + "</tr>"
        )
    return ('<div class="scroll"><table class="params">' + head
            + "<tbody>" + "".join(body) + "</tbody></table></div>")


def _parameters(c: Comparison) -> str:
    """What differed in the setup. Above every result, deliberately."""
    out = ["<h2>What differs — the setup, before any result</h2>",
           "<p>A delta read without knowing the runs used different settings "
           "is worse than no delta.</p>"]
    if not c.differing:
        out.append('<div class="banner ok">Nothing recorded differs between '
                   "these runs.</div>")
    else:
        out.append(_param_table(c, c.differing))

    if c.uncertain:
        items = "".join(
            f"<li>{_e(row.name)} — not recorded by "
            f"{_e(', '.join(row.unknown_runs))}</li>" for row in c.uncertain)
        out.append(
            '<div class="banner"><b>Cannot be ruled out as a difference.</b> '
            "Recorded by some runs and not by others — older ledgers predate "
            f"these manifest fields, so they are unknown, not equal.<ul>{items}"
            "</ul></div>")

    if c.conflicts:
        items = "".join(
            f"<li>{_e(run)}: {_e(name)} manifest=<code>{_e(stated)}</code> "
            f"rows=<code>{_e(observed)}</code></li>"
            for run, name, stated, observed in c.conflicts)
        out.append('<div class="banner stop"><b>The manifest disagrees with '
                   "the ledger.</b> The rows are what actually happened — a "
                   f"manifest copied from another directory is a real "
                   f"mistake.<ul>{items}</ul></div>")
    return "".join(out)


def _not_compared(c: Comparison) -> str:
    """Arms only some runs ran. Above the head-to-head, on purpose."""
    exclusive = c.exclusive_arms
    if not exclusive:
        return ""
    head = ("<tr>" + _th("arm") + _th("run", "reference run") + "<th>n</th>"
            + _th("success", "success rate")
            + _th("95% CI", "confidence interval") + "</tr>")
    body = []
    for arm, labels in exclusive.items():
        for label in labels:
            summary = c.summary(label, arm)
            if summary is None:
                continue
            ci = summary.success_ci
            interval = "n/a" if ci is None else f"[{ci[0]:.0%}, {ci[1]:.0%}]"
            body.append(
                f"<tr><td>{_e(arm)}</td><td>{_e(label)}</td>"
                f"<td>{summary.n}</td>"
                f"<td>{_e(Comparison.fmt('success', summary.success_rate))}</td>"
                f"<td>{_e(interval)}</td></tr>")
    return (
        "<h2>Not compared</h2>"
        "<p>These arms are missing from at least one run, so they are excluded "
        "from every delta below: there is nothing to subtract from. A blank "
        "cell reads as a zero, and a zero here would be a claim nobody "
        "measured.</p>"
        '<div class="scroll"><table>' + head + "<tbody>"
        + "".join(body) + "</tbody></table></div>"
    )


def _head_to_head(c: Comparison, sort: str, keys: tuple[str, ...]) -> str:
    arms = c.ranked_arms(sort)
    if not arms:
        return ('<h2>Head to head</h2><div class="banner stop"><b>No arm is '
                "present in every run.</b> There is nothing to compare head to "
                "head; the standalone numbers above are the honest summary."
                "</div>")

    out = ["<h2>Head to head</h2>"]
    for key in keys:
        label, higher_is_better, meaning = RANK_KEYS.get(key, (key, True, ""))
        if key == "score" and not c.score_comparable:
            out.append(
                '<div class="banner"><b>SCORE is not comparable across these '
                "runs.</b> The composite min-max normalises each dimension "
                "within that run's own set of candidate arms. These runs ran "
                "different arms, so the two scores were scaled against "
                "different ranges — their difference would measure which arms "
                "happened to be present, not which packaging is better.</div>")
            continue

        direction = "higher is better" if higher_is_better else "lower is better"
        out.append(f"<h3>{_e(label)}"
                   f'<span class="dir">{_e(direction)}</span></h3>')
        out.append(f"<p>{_e(meaning)}.")
        if key == "lift":
            out.append(" Each run's lift is against its own Z0, so a delta "
                       "here is a difference of differences.")
        out.append("</p>")

        head = ["<tr>" + _th("arm")]
        head.append(f"<th>{_e(c.reference.label)}</th>")
        for ref in c.others:
            head.append(f"<th>{_e(ref.label)}</th>")
            head.append(_th("Δ", "Δ / delta"))
        head.append("</tr>")

        body = []
        for arm in arms:
            cells = [f"<td>{_e(arm)}</td>"]
            value = c.value(c.reference.label, arm, key)
            cells.append(f'<td class="ref">{_e(Comparison.fmt(key, value))}</td>')
            for ref in c.others:
                other = c.value(ref.label, arm, key)
                cells.append(f"<td>{_e(Comparison.fmt(key, other))}</td>")
                cells.append(_delta_cell(c, ref.label, arm, key))
            body.append("<tr>" + "".join(cells) + "</tr>")
        out.append('<div class="scroll"><table>' + "".join(head)
                   + "<tbody>" + "".join(body) + "</tbody></table></div>")

    marks = []
    if any(c.unresolved(r.label, a, k)
           for r in c.others for a in arms for k in keys):
        marks.append("<b>~</b> these samples cannot resolve this gap — not a "
                     "finding")
    if c.pooling_refused:
        marks.append("<b>‡</b> across a pooling boundary — not a finding at "
                     "any sample size")
    if marks:
        out.append('<p class="note">' + " &nbsp; ".join(marks) + "</p>")
    return "".join(out)


def _contrasts(c: Comparison) -> str:
    contrasts = c.contrasts()
    if not contrasts:
        return ""
    head = ("<tr>" + _th("arm") + _th("run", "reference run")
            + _th("method", "unpaired comparison") + "<th>n</th>"
            + f"<th>{_e(c.reference.label)}</th><th>then</th>"
            + _th("Δ", "Δ / delta")
            + _th("95% CI", "confidence interval") + "<th>p</th></tr>")
    body = []
    for contrast in contrasts:
        marks = ""
        if contrast.notable:
            marks += "*"
        if not contrast.paired:
            marks += "~"
        if contrast.cross_world:
            marks += "‡"
        n = (f"{contrast.n_cores} cores" if contrast.paired
             else f"{contrast.n_a}/{contrast.n_b}")
        if contrast.diff is None:
            diff = ci = p = "n/a"
        else:
            lo, hi = contrast.ci
            diff = Comparison.fmt_delta("success", contrast.diff)
            ci = f"[{lo * 100:+.0f}, {hi * 100:+.0f}] pp"
            p = f"{contrast.p_raw:.4f}"
        tip = contrast.caveat or "paired within core — per-task difficulty cancels"
        body.append(
            f"<tr><td>{_e(contrast.arm)}{_e(marks)}</td>"
            f"<td>{_e(contrast.run_b)}</td>"
            f'<td><abbr title="{_e(tip)}">{_e(contrast.method)}</abbr></td>'
            f"<td>{_e(n)}</td>"
            f"<td>{_e(Comparison.fmt('success', contrast.rate_a))}</td>"
            f"<td>{_e(Comparison.fmt('success', contrast.rate_b))}</td>"
            f'<td class="delta">{_e(diff)}</td>'
            f"<td>{_e(ci)}</td><td>{_e(p)}</td></tr>")

    out = ["<h2>Cross-run contrasts</h2>",
           "<p>The same arm, measured twice. None of these is pre-registered "
           "and none is corrected for multiplicity: which runs get compared is "
           "decided after both have been seen, so nothing here can be called "
           "significant.</p>",
           '<div class="scroll"><table>' + head + "<tbody>"
           + "".join(body) + "</tbody></table></div>"]

    unpaired = [x for x in contrasts if not x.paired and x.comparable]
    if unpaired:
        items = "".join(f"<li>{_e(part.strip())}</li>"
                        for part in unpaired[0].caveat.split(";") if part.strip())
        out.append('<div class="banner"><b>Unpaired, because these runs did '
                   f"not answer the same task set.</b><ul>{items}</ul></div>")
    if not c.same_world:
        out.append('<p class="note">Pairing within core needs a matching seed, '
                   "core count, fan-out and difficulty. Core ids are "
                   "positional — <code>core-000</code> in one world is a "
                   "different problem from <code>core-000</code> in another.</p>")
    return "".join(out)


def _charts(c: Comparison) -> str:
    charts = build_charts(c)
    if not charts:
        return ""
    out = ["<h2>Charts</h2>"]
    if "success-by-run" in charts:
        out.append('<div class="metric"><h3>Success by arm</h3>'
                   + charts["success-by-run"]
                   + charts.get("success-by-run-legend", "") + "</div>")
    for ref in c.others:
        svg = charts.get(f"delta-success-{_slug(ref.label)}")
        if svg:
            out.append(f'<div class="metric"><h3>Success delta — '
                       f"{_e(ref.label)} minus {_e(c.reference.label)}</h3>"
                       f"{svg}"
                       '<p class="note">Hatched bars are inside the combined '
                       "noise floor or across a pooling boundary — not "
                       "findings.</p></div>")
    for key in ("abstention", "harm", "trunc"):
        svg = charts.get(f"metric-{key}")
        if not svg:
            continue
        label, higher_is_better, meaning = RANK_KEYS[key]
        direction = "higher is better" if higher_is_better else "lower is better"
        out.append(f'<div class="metric"><h3>{_e(label)}'
                   f'<span class="dir">{_e(direction)}</span></h3>'
                   f'<p class="note">{_e(meaning)}.</p>{svg}'
                   + charts.get("success-by-run-legend", "") + "</div>")
    return "".join(out)


def _all_parameters(c: Comparison) -> str:
    return ("<details><summary>Every parameter — the audit trail</summary>"
            + _param_table(c, c.params, mark_differs=True)
            + '<p class="note">★ differs between runs.</p></details>')


def _glossary() -> str:
    from .glossary import GLOSSARY
    items = "".join(
        f"<dt>{_e(t.name)}</dt><dd>{_e(t.short)}"
        + (f'<br><span class="why">{_e(t.long)}</span>' if t.long else "")
        + "</dd>" for t in GLOSSARY)
    return ("<details><summary>Glossary</summary>"
            f'<dl class="glossary">{items}</dl></details>')


def _footer(c: Comparison) -> str:
    lines = [POOLING_RULE]
    excluded = len(c.exclusive_arms)
    if excluded:
        lines.append(f"{excluded} arms were not run everywhere and are "
                     "excluded from every delta.")
    unpaired = sum(1 for x in c.contrasts() if not x.paired and x.comparable)
    if unpaired:
        lines.append(f"{unpaired} of {len(c.contrasts())} contrasts are "
                     "unpaired and can never be called significant.")
    missing = sum(1 for row in c.params
                  if any(v is NOT_RECORDED for v in row.values.values()))
    if missing:
        lines.append(f"{missing} parameters are unrecorded by at least one run "
                     "— unknown, not equal.")
    return "<footer>" + "<br>".join(_e(x) for x in lines) + "</footer>"
