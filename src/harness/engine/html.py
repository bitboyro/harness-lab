"""The HTML results report.

Self-contained: inline style, inline SVG, no external requests of any kind.

The ordering is deliberate. Caveats sit at the **top**, not in a footer, because
they change how every chart below should be read — a reader who learns about the
MDE after looking at the bars has already formed an impression the bars did not
earn.

Contract: archive/reference/experiment-design.md#deliverables
"""

from __future__ import annotations

from html import escape
from typing import Any

from .analysis import OUTCOME_ORDER, POOLING_RULE, Report
from .svg import bar_chart, Bar, grouped_bars, heatmap, legend, palette_css, scatter, stacked_bars

#: Outcome severity, light (benign) to dark (dangerous). Truncation sits off the
#: ramp entirely on a neutral fill: it is the absence of a grade, not a worse
#: one, and colouring it as a severity step would misstate what happened.
OUTCOME_FILLS = ("var(--ord-1)", "var(--ord-2)", "var(--ord-3)",
                 "var(--ord-4)", "var(--ord-5)", "var(--neutral)")

_CSS = """
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, sans-serif; }
  /* The palette variables are scoped to `.viz`, so the surface has to be
     painted there too. Putting it on `body` reads `--surface-1` from outside
     the scope, resolves to nothing, and leaves the page white behind themed
     content in dark mode. */
  .viz { background: var(--surface-1); color: var(--text-primary);
         min-height: 100vh; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 32px 20px 72px; }
  h1 { font-size: 20px; margin: 0 0 4px; letter-spacing: -0.01em; }
  h2 { font-size: 15px; margin: 34px 0 10px; letter-spacing: -0.005em; }
  h3 { font-size: 12px; margin: 18px 0 6px; color: var(--text-secondary);
       font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  p  { margin: 0 0 10px; color: var(--text-secondary); }
  .sub { color: var(--text-muted); font-size: 12px; }
  .note { font-size: 12px; color: var(--text-muted); margin: 6px 0 0; }
  pre.ops { font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
            background: var(--surface-2, var(--surface-1));
            color: var(--text-primary); padding: 14px 16px; border-radius: 6px;
            overflow-x: auto; white-space: pre-wrap; }
  /* Each severity gets its own tinted surface, mixed from the status colour
     into the page surface, so the tint stays legible in both themes instead of
     a fixed pastel that goes muddy in dark mode. Text stays on text tokens
     throughout — the tint and the border carry identity, never the letters, so
     the block reads as one voice rather than two. */
  .banner { border-left: 3px solid var(--status-warning);
            background: color-mix(in oklab, var(--status-warning) 10%, var(--surface-1));
            color: var(--text-secondary);
            padding: 11px 15px; border-radius: 0 6px 6px 0; margin: 8px 0; }
  .banner.stop { border-left-color: var(--status-critical);
                 background: color-mix(in oklab, var(--status-critical) 10%, var(--surface-1)); }
  .banner.ok { border-left-color: var(--status-good);
               background: color-mix(in oklab, var(--status-good) 10%, var(--surface-1)); }
  .banner b { color: var(--text-primary); font-weight: 650; }
  .banner ul { margin: 8px 0; padding-left: 20px; }
  .banner code { color: var(--text-primary); font-size: 12px; }
  .legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 8px 0 4px;
            font-size: 11px; color: var(--text-secondary); }
  .chip { display: inline-flex; align-items: center; gap: 5px; }
  .chip i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 12px;
          font-variant-numeric: tabular-nums; }
  th, td { text-align: right; padding: 5px 9px; border-bottom: 1px solid var(--grid); }
  th:first-child, td:first-child { text-align: left; }
  /* Numbers right-align so digits line up; prose does not. */
  td.prose, th.prose { text-align: left; }
  th { color: var(--text-secondary); font-weight: 600; white-space: nowrap; }
  /* Click-to-sort. The affordance is the cursor plus a caret on the active
     column — the sorted direction must be visible, or a reader cannot tell a
     re-ordered table from the original one. */
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover, th.sortable:focus-visible { color: var(--text-primary); }
  th[data-dir]::after { content: " ▾"; font-size: 9px; }
  th[data-dir="asc"]::after { content: " ▴"; }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
           gap: 18px; }
  .card { border: 1px solid var(--grid); border-radius: 8px; padding: 12px 14px; }
  .card h4 { margin: 0 0 8px; font-size: 13px; }
  .kv { display: flex; justify-content: space-between; font-size: 11px;
        color: var(--text-secondary); padding: 2px 0; }
  .kv b { color: var(--text-primary); font-weight: 600; }
  /* The arm's plain-language name, wherever its code appears. Muted and a size
     down: the code is the identifier, the name is the reminder. */
  .armname { color: var(--text-muted); font-weight: 400; font-size: 11px; }
  .ctl { color: var(--text-muted); cursor: help; }
  td .why { color: var(--text-muted); font-size: 11px; font-weight: 400; }
  tr.win td { background: color-mix(in oklab, var(--status-good) 8%, var(--surface-1)); }
  tr.win td:first-child { box-shadow: inset 2px 0 0 var(--status-good); }
  /* Direction of merit. Text, not colour alone — a reader who cannot
     distinguish the tint still gets "lower is better" in words. */
  .dir { font-size: 10px; font-weight: 500; text-transform: none;
         letter-spacing: 0; padding: 2px 7px; border-radius: 10px;
         color: var(--text-secondary); border: 1px solid var(--grid);
         margin-left: 6px; white-space: nowrap; }
  .metric { margin: 18px 0 22px; }
  .metric h3 { text-transform: none; letter-spacing: 0; font-size: 13px;
               color: var(--text-primary); }
  .metric p { font-size: 12px; margin-bottom: 8px; }
  details.howto { border: 1px solid var(--grid); border-radius: 8px;
                  padding: 10px 14px; margin: 14px 0 4px; }
  details summary { cursor: pointer; color: var(--text-secondary);
                    font-size: 12px; margin: 10px 0; }
  details.howto summary { cursor: pointer; font-weight: 600;
                          color: var(--text-primary); font-size: 13px; }
  details.howto p { margin: 10px 0 0; font-size: 13px; }
  abbr { text-decoration: underline dotted; text-underline-offset: 3px;
         cursor: help; }
  dl.glossary { display: grid; grid-template-columns: minmax(120px, 180px) 1fr;
                gap: 6px 18px; font-size: 12px; margin: 12px 0 0; }
  dl.glossary dt { font-weight: 600; color: var(--text-primary); }
  dl.glossary dd { margin: 0; color: var(--text-secondary); }
  dl.glossary .why { color: var(--text-muted); }
  @media (max-width: 560px) { dl.glossary { grid-template-columns: 1fr; }
                              dl.glossary dd { margin-bottom: 8px; } }
  footer { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--grid);
           font-size: 11px; color: var(--text-muted); }
"""


def _e(v: Any) -> str:
    return escape(str(v), quote=True)


def _th(label: str, term: str | None = None) -> str:
    """A header cell that explains itself on hover.

    The definition rides on the column rather than living only in a glossary at
    the bottom: a reader meets `MCC` in the table, and that is where the
    question occurs to them."""
    from .glossary import lookup
    entry = lookup(term or label)
    if not entry:
        return f"<th>{_e(label)}</th>"
    tip = entry.long or entry.short
    return (f'<th><abbr title="{_e(entry.short)} {_e(tip)}">{_e(label)}</abbr></th>')


def _pct(v: float | None, digits: int = 0) -> str:
    return "n/a" if v is None else f"{v:.{digits}%}"


def _num(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:,.{digits}f}"


def build_charts(report: Report) -> dict[str, str]:
    """Every chart, keyed by filename stem. Rendered once, used twice."""
    charts: dict[str, str] = {}
    arms = sorted(report.arms)

    # 1. Lift over the parametric baseline.
    if report.baseline is not None:
        bars = []
        for name in arms:
            if name == "Z0":
                continue
            lift = report.lift(name)
            summary = report.arms[name]
            ci = summary.success_ci
            muted = report.below_mde(name)
            bars.append(Bar(
                label=name,
                value=None if lift is None else lift * 100,
                ci=None if ci is None or report.baseline is None
                   else ((ci[0] - report.baseline) * 100,
                         (ci[1] - report.baseline) * 100),
                muted=muted,
                note="below MDE" if muted else "",
                slot=1,
            ))
        band = ((-report.mde_pp, report.mde_pp) if report.mde_pp else None)
        charts["lift"] = bar_chart(
            bars, title="Lift over Z0 (percentage points)", unit="pp",
            band=band,
        )

    # 2. Failure taxonomy. Truncation is a segment, not a footnote.
    data = [[float(report.arms[a].outcome_counts()[o]) for o in OUTCOME_ORDER]
            for a in arms]
    charts["outcomes"] = stacked_bars(arms, list(OUTCOME_ORDER), data,
                                      fills=OUTCOME_FILLS,
                                      title="Outcome distribution per arm")

    # 3. Success by task class — the RQ4 view.
    classes = report.task_classes
    if len(classes) > 1:
        rows = [[report.arms[a].by_class().get(c) for c in classes] for a in arms]
        charts["by-class"] = grouped_bars(arms, classes, rows,
                                          title="Success by task class")

    # 4. Cost frontier — only when the model is priced.
    pricing = report.pricing
    if pricing:
        points = []
        for name in arms:
            summary = report.arms[name]
            cps, rate = summary.cost_per_success(pricing), summary.success_rate
            if cps is not None and rate is not None:
                points.append((name, cps, rate))
        if points:
            charts["cost-frontier"] = scatter(
                points, title="Cost frontier",
                x_label="USD per success (lower is better)",
                y_label="success rate",
            )

    # 5. Token components. Never totalled (§5.6).
    token_names = ["static", "per-call overhead", "session setup"]
    token_data = [[float(report.arms[a].tokens()[k] or 0.0) for k in token_names]
                  for a in arms]
    if any(any(row) for row in token_data):
        charts["tokens"] = stacked_bars(arms, token_names, token_data,
                                        show_total=False,
                                        title="Token components per run")

    # 6. Confusion matrices, one per arm.
    for name in arms:
        c = report.arms[name].confusion
        if not c.total:
            continue
        charts[f"confusion-{name}"] = heatmap(
            [("answered", "answerable", c.tp, "TP"),
             ("answered", "unanswerable", c.fp, "FP"),
             ("declined", "answerable", c.fn, "FN"),
             ("declined", "unanswerable", c.tn, "TN")],
            rows=["answered", "declined"],
            cols=["answerable", "unanswerable"],
            title=f"{name} confusion matrix",
        )

    # 7. Metrics that actually vary, best-first on the metric's own direction so
    #    the chart reads top-down like every other ranking on the page.
    from .metrics import get as get_metric
    for metric in report.varying_metrics():
        try:
            better = get_metric(metric).better
        except KeyError:
            better = None
        ordered = sorted(
            (a for a in arms if report.arms[a].metric_mean(metric) is not None),
            key=lambda a: report.arms[a].metric_mean(metric),
            reverse=(better == "higher"),
        )
        bars = [Bar(label=a, value=report.arms[a].metric_mean(metric), slot=1)
                for a in ordered]
        if bars:
            charts[f"metric-{metric}"] = bar_chart(
                bars, title=metric.replace("_", " "), unit="")
    return charts


#: How many behavioural metrics get a chart and a paragraph. The rest are still
#: shown, just in a table — a page of equally-weighted charts is how a reader
#: ends up ignoring all of them.
PROMOTED = 3


def render_html(report: Report, sort: str = "score") -> str:
    charts = build_charts(report)
    arms = sorted(report.arms)
    # One order for the whole page, so "who won" does not reset to alphabetical
    # at every section heading.
    order = report.ranked(sort)
    out: list[str] = []

    manifest = report.manifest
    out.append(f"<h1>{_e(report.run_id)}</h1>")
    out.append(
        f'<p class="sub">{_e(report.model)} · {len(report.rows)} runs · '
        f"{len(arms)} arms · {report.task_count} tasks · "
        f"{_e(report.report_class)}</p>"
    )

    # ---- banners, before any chart --------------------------------------
    out.append(_banners(report))

    # ---- Z0 --------------------------------------------------------------
    gate = report.z0_gate
    if gate is not None:
        passed, answered, graded = gate
        if report.report_class == "controlled":
            cls = "ok" if passed else "stop"
            verdict = "PASS" if passed else "FAIL — DOMAIN CONTAMINATED"
            out.append(
                f'<div class="banner {cls}"><b>Z0 gate: {verdict}</b> — '
                f"{answered}/{graded} tasks answered correctly with no API "
                f"access. Correct refusals count toward Z0's success rate but "
                f"not toward this gate; with no tools, declining is the "
                f"expected behaviour.</div>"
            )
        else:
            out.append(
                f'<div class="banner"><b>Parametric baseline: '
                f'{_pct(report.baseline)}</b> — what the model answers with no '
                f"access to the API at all. Every number below is lift over "
                f"this.</div>"
            )

    # ---- how to read this ------------------------------------------------
    out.append(
        '<details class="howto"><summary>How to read this report</summary>'
        "<p><b>Every arm answers the same tasks against the same API.</b> The "
        "only thing that changes is how the API is presented to the model. "
        "Higher is better everywhere except harm, truncation and false "
        "positives.</p>"
        "<p><b>Start with lift, not success.</b> <i>Z0</i> is the control that "
        "gets no tools at all — it shows what the model already knew. An arm "
        "scoring 67% looks fine until Z0 scored 83%, at which point the tools "
        "made things worse. Lift is success minus Z0, measured in "
        "<i>percentage points</i> (pp).</p>"
        "<p><b>Then check the interval, not the gap.</b> Every difference has a "
        "95% CI. If it spans zero, this run cannot tell the difference from "
        "nothing — however large the bar looks.</p>"
        "<p>Hover any column heading for its definition, or read the full "
        "glossary at the bottom.</p></details>"
    )

    # ---- what the arms are ----------------------------------------------
    described = [a for a in order if a.description]
    if described:
        out.append("<h2>The arms</h2>")
        out.append(
            "<p>Derived from each run's recorded axis assignment, not from the "
            "preset name — so an arm is described as what it actually was, "
            "including any sweep override.</p>"
        )
        rows = "".join(
            f"<tr><td><b>{_e(a.arm)}</b></td>"
            f'<td class="prose"><b>{_e(a.name)}</b><br>'
            f'<span class="why">{_e(a.description)}</span></td></tr>'
            for a in described
        )
        out.append(f'<div class="scroll"><table>{rows}</table></div>')

    # ---- the verdict -----------------------------------------------------
    out.append(_verdict_section(report, order))


    # ---- charts ----------------------------------------------------------
    if "lift" in charts:
        out.append("<h2>Lift over baseline</h2>")
        out.append(
            "<p>Whiskers are Wilson 95% intervals. Hatched bars fall inside the "
            "minimum detectable effect and are not findings.</p>"
        )
        out.append(charts["lift"])

    out.append("<h2>Where runs end up</h2>")
    out.append(legend(list(OUTCOME_ORDER), fills=OUTCOME_FILLS))
    out.append(charts["outcomes"])
    out.append(
        '<p class="note">Truncated runs hit <code>max_turns</code>. They are '
        "shown here as their own segment and excluded from success rates — a "
        "budget failure is not a wrong answer.</p>"
    )

    if "by-class" in charts:
        out.append("<h2>Success by task class</h2>")
        out.append("<p>Whether the arm ranking reverses between reads and "
                   "writes (RQ4).</p>")
        out.append(legend(report.task_classes))
        out.append(charts["by-class"])

    # ---- classification --------------------------------------------------
    out.append("<h2>Answer or abstain</h2>")
    out.append(
        "<p>A success rate cannot separate an agent that fabricates an answer "
        "from one that gives up. Both fail; only the first is dangerous.</p>"
    )
    if report.inferred_answerable:
        out.append(
            '<p class="note">This ledger predates the explicit '
            "<code>answerable</code> field, so labels are inferred from "
            "outcomes. The inference is exact for this grader.</p>"
        )
    out.append('<div class="grid2">')
    for a in order:
        name, c = a.arm, a.confusion
        if not c.total:
            continue
        out.append(f'<div class="card"><h4>{_e(name)} '
                   f'<span class="armname">{_e(a.name)}</span></h4>')
        out.append(charts.get(f"confusion-{name}", ""))
        for label, value in (("precision", c.precision), ("recall", c.recall),
                             ("F1", c.f1), ("accuracy", c.accuracy),
                             ("balanced acc.", c.balanced_accuracy),
                             ("specificity — declined correctly", c.specificity)):
            out.append(f'<div class="kv"><span>{label}</span>'
                       f"<b>{_pct(value, 0) if value is not None else 'n/a'}</b></div>")
        mcc = c.mcc
        out.append(f'<div class="kv"><span>MCC</span><b>'
                   f"{'n/a' if mcc is None else f'{mcc:+.2f}'}</b></div>")
        if c.fn:
            out.append(f'<div class="kv"><span>failures: hedged / confident</span>'
                       f"<b>{c.fn_abstained} / {c.fn_confident}</b></div>")
        out.append("</div>")
    out.append("</div>")
    out.append(
        '<p class="note">F1 ignores true negatives, but a correct refusal is a '
        "first-class success here — read balanced accuracy and MCC alongside it. "
        "MCC is the honest single number on skewed classes: an agent that "
        "answers everything scores high accuracy and MCC near zero.</p>"
    )

    # ---- cost ------------------------------------------------------------
    out.append("<h2>Cost</h2>")
    if "cost-frontier" in charts:
        out.append("<p>Down and to the right is better: cheaper per success, "
                   "more successes.</p>")
        out.append(charts["cost-frontier"])
    else:
        out.append(f'<div class="banner">Model <code>{_e(report.model)}</code> '
                   f"is not in the pricing table, so cost is not reported. Add "
                   f"it or set <code>HARNESS_PRICE_…</code>.</div>")

    if "tokens" in charts:
        out.append("<h3>Token components</h3>")
        out.append(legend(["static", "per-call overhead", "session setup"]))
        out.append(charts["tokens"])
        out.append('<p class="note">Reported as components and never totalled: '
                   "stateless MCP moves cost from session setup to a per-call "
                   "tax that scales with call count, and a total hides that.</p>")

    # ---- how each arm behaved --------------------------------------------
    out.append(_behaviour_section(report, order, charts))

    # ---- contrasts -------------------------------------------------------
    from .stats import analyse as analyse_stats
    stats = analyse_stats(report)
    if stats.contrasts:
        out.append("<h2>Contrasts</h2>")
        out.append(
            "<p>Paired within core, so per-core difficulty cancels. Only "
            "pre-registered contrasts can reach significance; exploratory ones "
            "are shown and labelled but never corrected.</p>"
        )
        head = ("<tr><th>contrast</th><th>difference</th><th>95% CI</th>"
                "<th>p</th><th>cores</th><th>kind</th><th>hypothesis</th></tr>")
        rows = []
        for c in stats.contrasts:
            p_value = c.p_adjusted if c.p_adjusted is not None else c.p_raw
            mark = " *" if c.significant else ""
            rows.append(
                f"<tr><td>{_e(c.arm_a)} vs {_e(c.arm_b)}</td>"
                f"<td>{c.diff:+.1%}{mark}</td>"
                f"<td>{c.ci[0]:+.1%} … {c.ci[1]:+.1%}</td>"
                f"<td>{p_value:.4f}</td><td>{c.n_cores}</td>"
                f"<td>{'confirmatory' if c.confirmatory else 'exploratory'}</td>"
                f"<td>{_e(c.hypothesis or '')}</td></tr>"
            )
        out.append(f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>')
        if not stats.findings:
            out.append(
                '<div class="banner"><b>Nothing survives correction.</b> At this '
                "sample size that means <i>not detectable</i>, not <i>no "
                "difference</i> — read the confidence intervals, not the "
                "p-values.</div>"
            )

    # ---- tables ----------------------------------------------------------
    if report.op_ledger is not None and (
            report.op_ledger.calls or report.op_ledger.excluded_arms
    ):
        out.append(_op_ledger_section(report.op_ledger))

    out.append("<h2>Details</h2>")
    out.append("<h3>Answer or abstain</h3>")
    out.append(_confusion_table(report, order))
    out.append("<h3>Effort per run (mean)</h3>")
    out.append(_effort_table(report, order))
    out.append("<h3>Outcomes</h3>")
    out.append(_arm_table(report, order))
    if len(report.task_classes) > 1:
        out.append("<h3>Success by class</h3>")
        out.append(_class_table(report, order))
    if report.error_rows:
        out.append("<h3>Harness errors</h3>")
        out.append(_error_table(report))

    # ---- glossary --------------------------------------------------------
    from .glossary import GLOSSARY
    out.append("<h2>Glossary</h2>")
    entries = "".join(
        f"<dt>{_e(t.name)}</dt><dd>{_e(t.short)}"
        + (f" <span class=\"why\">{_e(t.long)}</span>" if t.long else "")
        + "</dd>"
        for t in GLOSSARY
    )
    out.append(f"<dl class='glossary'>{entries}</dl>")

    out.append(_footer(report))

    body = "\n".join(out)
    return (
        "<style>\n" + palette_css() + "\n" + _CSS + "\n</style>\n"
        f'<div class="viz"><div class="wrap">{body}</div></div>'
        f"<script>{_SORT_JS}</script>"
    )


#: Click-to-sort for every data table. Inline and dependency-free — the report
#: is one self-contained file that has to work from a file:// URL with no
#: network, so a library is not an option.
#:
#: Values are parsed rather than compared as strings: "$0.0062" and "12.9%" and
#: "1,204" all sort as numbers, and "n/a" always sinks to the bottom whichever
#: direction is chosen, because an absent value is not a small one.
_SORT_JS = """
(function () {
  var NA = /^(n\\/a|—|-|)$/i;
  function value(cell) {
    var text = (cell.getAttribute('data-sort') || cell.textContent).trim();
    if (NA.test(text)) return null;
    var n = parseFloat(text.replace(/[$,%\\s,]/g, '').replace(/[^0-9.eE+-].*$/, ''));
    return isNaN(n) ? text.toLowerCase() : n;
  }
  document.querySelectorAll('table').forEach(function (table) {
    var head = table.rows[0];
    if (!head) return;
    Array.prototype.forEach.call(head.cells, function (th, i) {
      th.tabIndex = 0;
      th.classList.add('sortable');
      function sort() {
        var body = Array.prototype.slice.call(table.rows, 1);
        var desc = th.getAttribute('data-dir') !== 'desc';
        body.sort(function (a, b) {
          var x = value(a.cells[i]), y = value(b.cells[i]);
          if (x === null && y === null) return 0;
          if (x === null) return 1;   // absent sinks, both directions
          if (y === null) return -1;
          if (typeof x === 'string' || typeof y === 'string')
            return desc ? String(y).localeCompare(x) : String(x).localeCompare(y);
          return desc ? y - x : x - y;
        });
        Array.prototype.forEach.call(head.cells, function (o) {
          o.removeAttribute('data-dir');
        });
        th.setAttribute('data-dir', desc ? 'desc' : 'asc');
        body.forEach(function (r) { table.tBodies[0].appendChild(r); });
      }
      th.addEventListener('click', sort);
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sort(); }
      });
    });
  });
})();
"""


def standalone_html(report: Report, sort: str = "score") -> str:
    """A complete document, for writing to a file.

    The charset declaration is not optional: served over HTTP without it, a
    browser guesses latin-1 and every em dash in the caveats renders as
    mojibake — which is exactly where the text most needs to be readable.
    """
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(report.run_id)} — harness results</title></head>"
        f"<body>{render_html(report, sort)}</body></html>"
    )


def _verdict_section(report: Report, order) -> str:
    """Who won, on what, and every reason to distrust it.

    Placed above the charts because it is the question the report exists to
    answer. The caveats ship *with* the verdict rather than in a footnote: a
    composite score will always produce a ranking, including one made entirely
    of noise, and separating the number from its interval is how that gets
    quoted.
    """
    from .winner import COLUMNS, _cell
    from .analysis import RANK_KEYS

    verdict = report.verdict()
    out = ["<h2>The verdict</h2>"]
    if verdict.leader is None:
        return out[0] + f'<div class="banner">{_e(verdict.reason)}</div>'

    if verdict.winner is not None:
        champion = report.arms[verdict.winner]
        out.append(
            f'<div class="banner ok"><b>Winner: {_e(champion.arm)} · '
            f"{_e(champion.name)}</b> — composite score "
            f"{verdict.scores[verdict.winner]:.2f} across "
            f"{len(verdict.dimensions)} weighted dimensions.</div>"
        )
    else:
        tied = verdict.tied_leaders
        out.append(
            f'<div class="banner"><b>No winner — {len(tied)} arms tied at '
            f"{verdict.scores[tied[0]]:.2f}</b> ({_e(', '.join(tied))}). On the "
            f"dimensions you weighted they are indistinguishable.</div>"
        )
    out.append(
        "<p>Every dimension is rescaled 0–1 across the packaging arms, oriented "
        "so higher is always better, then weighted. Controls are shown but never "
        "scored — <code>Z0</code> has no tools and <code>Z1</code> is handed the "
        "answers, so neither is something you could ship.</p>"
    )

    head = ("<tr>" + _th("arm")
            + "".join(_th(label, RANK_KEYS[key][2]) for key, label in COLUMNS)
            + _th("SCORE", RANK_KEYS["score"][2]) + "</tr>")
    rows = []
    for a in order:
        score = verdict.scores.get(a.arm)
        cells = "".join(f"<td>{_e(_cell(report, a.arm, key))}</td>"
                        for key, _ in COLUMNS)
        is_winner = a.arm == verdict.winner  # never highlights a tied field
        score_cell = ("<td>—</td>" if score is None
                      else f"<td><b>{score:.2f}</b></td>")
        rows.append(f'<tr class="{"win" if is_winner else ""}">'
                    f"{_arm_cell(a)}{cells}{score_cell}</tr>")
    out.append(f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>')

    weights = " · ".join(f"{k} {v:.2f}" for k, v in verdict.weights.items())
    out.append(f'<p class="note">Weights: {_e(weights)}. Change them with '
               f"<code>--weights harm=1</code> to see, say, the safety ranking "
               f"alone. † marks a control, excluded from scoring.</p>")

    for caveat in verdict.caveats:
        out.append(f'<div class="banner">{_e(caveat)}</div>')
    return "\n".join(out)


def _op_ledger_section(ledger) -> str:
    """Customer payoff: which ops agents lean on and misuse.

    Renders the same text blocks as the CLI report — one analysis object, two
    surfaces — so HTML and text cannot disagree about rates or unavailable
    signals.
    """
    body = ledger.render()
    # Drop the leading indent the text report uses for nesting under the page.
    lines = [ln[2:] if ln.startswith("  ") else ln for ln in body.splitlines()]
    escaped = _e("\n".join(lines))
    return (
        "<h2>Operation ledger</h2>"
        "<p>Where agents spend and stumble on the target API. Rates, not raw "
        "counts. Discovery meta-tools are footnoted, not mixed into the "
        "product chart.</p>"
        f'<pre class="ops">{escaped}</pre>'
    )


def _behaviour_section(report: Report, order, charts: dict[str, str]) -> str:
    """Why the success rates came out the way they did.

    Ordered by how much each metric separated the arms, so the section adapts to
    what the run found rather than walking a fixed list. Restricted to mechanism
    metrics: turns, tokens and seconds are cost, they have their own tables, and
    unfiltered they crowd out the numbers that actually explain the result.
    """
    from .metrics import Bucket, get

    ranked = report.metrics_by_spread(str(Bucket.MECHANISM))
    if not ranked:
        return ""

    out = ["<h2>How each arm behaved</h2>",
           "<p>These explain <i>why</i> the success rates came out the way they "
           "did. Ranked by how much each one separated the arms — a metric that "
           "came out the same everywhere explains nothing about why one "
           "packaging beat another.</p>"]

    for name in ranked[:PROMOTED]:
        try:
            metric = get(name)
        except KeyError:
            continue
        arrow = {"higher": "↑ ", "lower": "↓ "}.get(metric.better or "", "")
        out.append('<div class="metric">')
        out.append(f"<h3>{_e(name.replace('_', ' '))}"
                   f'<span class="dir">{arrow}{_e(metric.direction_note)}</span></h3>')
        out.append(f"<p>{_e(metric.description)}</p>")
        out.append(charts.get(f"metric-{name}", ""))
        out.append("</div>")

    rest = ranked[PROMOTED:]
    if rest:
        head = ("<tr><th>metric</th><th>better</th>"
                + "".join(f"<th>{_e(a.arm)}</th>" for a in order) + "</tr>")
        rows = []
        for name in rest:
            try:
                metric = get(name)
            except KeyError:
                continue
            cells = "".join(
                f"<td>{'n/a' if (v := a.metric_mean(name)) is None else f'{v:,.2f}'}</td>"
                for a in order)
            rows.append(
                f"<tr><td><b>{_e(name.replace('_', ' '))}</b><br>"
                f'<span class="why">{_e(metric.description)}</span></td>'
                f'<td class="prose">{_e(metric.direction_note)}</td>{cells}</tr>')
        out.append(
            f"<details><summary>{len(rows)} more behavioural metrics — these "
            f"separated the arms less</summary>"
            f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>'
            f"</details>")

    constant = report.constant_metrics()
    if constant:
        names = ", ".join(f"{k} = {v:g}" for k, v in constant.items())
        out.append(f'<p class="note">No variation across any run on: '
                   f"{_e(names)}. Charting these would imply a difference that "
                   f"is not there.</p>")
    out.append('<p class="note">Every metric above is <b>unvalidated</b>: its '
               "relationship to ground truth has not been established on the "
               "controlled rig.</p>")
    return "\n".join(out)


def _banners(report: Report) -> str:
    parts = []
    if report.pooling_refused:
        worlds = "".join(f"<li><code>{_e(w)}</code></li>"
                         for w in sorted(map(str, report.worlds)))
        parts.append(
            f'<div class="banner stop"><b>Refusing to pool.</b> These rows '
            f"describe different worlds and must not be averaged:<ul>{worlds}</ul>"
            f"Split by model, MCP revision or skill condition and report "
            f"separately.</div>"
        )
    if report.mde_pp is not None:
        parts.append(
            f'<div class="banner"><b>Power.</b> The minimum detectable effect at '
            f"this sample size is <b>{report.mde_pp:.0f} pp</b>. Differences "
            f"smaller than that are not findings, however suggestive the bars "
            f"look.</div>"
        )
    incomplete = report.incomplete_arms
    if incomplete:
        named = ", ".join(f"{name} ({n} of {expected} runs)"
                          for name, (n, expected) in sorted(incomplete.items()))
        parts.append(
            f'<div class="banner stop"><b>Incomplete.</b> {named}. A missing '
            f"cell is not a zero — those arms are averaged over fewer runs and "
            f"their intervals are correspondingly wider.</div>"
        )
    if report.report_class == "field":
        parts.append(
            '<div class="banner"><b>Field result.</b> Every metric is '
            "unvalidated — its relationship to ground truth has not been "
            "established on the controlled rig.</div>"
        )
    return "\n".join(parts)


def _arm_cell(a) -> str:
    """The arm's code and its plain-language name, in one cell.

    The code alone is unreadable to anyone who has not memorised the design, and
    a table of codes is the fastest way to make a reader scroll back to the
    legend on every row.
    """
    control = ' <span class="ctl" title="control — not a shippable packaging">†</span>' if a.is_control else ""
    name = f'<span class="armname">{_e(a.name)}</span>' if a.name else ""
    return f"<td><b>{_e(a.arm)}</b>{control}<br>{name}</td>"


def _arm_table(report: Report, order) -> str:
    pricing = report.pricing
    head = ("<tr>" + _th("arm") + "<th>n</th>" + _th("success", "success rate")
            + _th("95% CI") + _th("lift") + _th("turns") + _th("calls")
            + _th("static", "static tokens") + _th("trunc", "truncated")
            + _th("harm") + _th("$/success") + _th("cached") + "</tr>")
    rows = []
    for a in order:
        name = a.arm
        ci = a.success_ci
        lift = report.lift(name)
        cps = a.cost_per_success(pricing)
        rows.append(
            f"<tr>{_arm_cell(a)}<td>{a.n}</td>"
            f"<td>{_pct(a.success_rate)}</td>"
            f"<td>{'n/a' if ci is None else f'{ci[0]:.0%}–{ci[1]:.0%}'}</td>"
            f"<td>{'n/a' if lift is None else f'{lift:+.0%}'}"
            f"{' *' if report.below_mde(name) else ''}</td>"
            f"<td>{_num(a.mean('turns'))}</td><td>{_num(a.mean('calls'))}</td>"
            f"<td>{_num(a.mean('static_tokens'), 0)}</td>"
            f"<td>{_pct(a.truncation_rate)}</td><td>{a.harm_events}</td>"
            f"<td>{'n/a' if cps is None else f'${cps:.4f}'}</td>"
            f"<td>{_pct(a.cache_hit_rate())}</td></tr>"
        )
    star = ('<p class="note">* difference falls inside the MDE.</p>'
            if any(report.below_mde(n) for n in report.arms) else "")
    return (f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>'
            + star)


def _confusion_table(report: Report, order) -> str:
    head = ("<tr>" + _th("arm") + _th("precision") + _th("recall") + _th("F1")
            + _th("accuracy") + _th("balanced", "balanced accuracy")
            + _th("specificity") + _th("MCC")
            + _th("TP", "TP / true positive") + _th("FP", "FP / false positive")
            + _th("TN", "TN / true negative") + _th("FN", "FN / false negative")
            + "</tr>")
    rows = []
    for a in order:
        c = a.confusion
        if not c.total:
            continue
        rows.append(
            f"<tr>{_arm_cell(a)}<td>{_pct(c.precision)}</td>"
            f"<td>{_pct(c.recall)}</td><td>{_pct(c.f1)}</td>"
            f"<td>{_pct(c.accuracy)}</td><td>{_pct(c.balanced_accuracy)}</td>"
            f"<td>{_pct(c.specificity)}</td>"
            f"<td>{'n/a' if c.mcc is None else f'{c.mcc:+.2f}'}</td>"
            f"<td>{c.tp}</td><td>{c.fp}</td><td>{c.tn}</td><td>{c.fn}</td></tr>"
        )
    return (f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>'
            '<p class="note">Precision falls when an arm answers what it should '
            "have declined; recall falls when it declines what it should have "
            "answered. Accuracy alone cannot tell those apart, which is why MCC "
            "sits beside it.</p>")


def _effort_table(report: Report, order) -> str:
    head = ("<tr>" + _th("arm") + "<th>total tokens</th><th>input</th>"
            + _th("cached") + "<th>output</th><th>reasoning</th>"
            + "<th>seconds</th>" + _th("turns") + _th("calls") + "</tr>")
    rows = []
    for a in order:
        total_in = a.mean("input_tokens") or 0.0
        out = a.mean("output_tokens") or 0.0
        rows.append(
            f"<tr>{_arm_cell(a)}<td>{total_in + out:,.0f}</td>"
            f"<td>{total_in:,.0f}</td>"
            f"<td>{a.mean('cached_input_tokens') or 0:,.0f}</td>"
            f"<td>{out:,.0f}</td>"
            f"<td>{a.mean('reasoning_tokens') or 0:,.0f}</td>"
            f"<td>{a.mean('wall_clock_seconds') or 0:,.1f}</td>"
            f"<td>{a.mean('turns') or 0:,.1f}</td>"
            f"<td>{a.mean('calls') or 0:,.1f}</td></tr>"
        )
    grand = sum(r["input_tokens"] + r["output_tokens"] for r in report.rows)
    return (f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>'
            f'<p class="note">{grand:,} tokens across {len(report.rows)} runs. '
            "Token counts are not comparable across providers — compare dollars "
            "per success, not tokens.</p>")


def _class_table(report: Report, order) -> str:
    classes = report.task_classes
    head = "<tr><th>arm</th>" + "".join(f"<th>{_e(c)}</th>" for c in classes) + "</tr>"
    rows = []
    for a in order:
        per = a.by_class()
        cells = "".join(f"<td>{_pct(per.get(c))}</td>" for c in classes)
        rows.append(f"<tr>{_arm_cell(a)}{cells}</tr>")
    return f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>'


def _error_table(report: Report) -> str:
    head = "<tr><th>arm</th><th>task</th><th>error</th></tr>"
    rows = "".join(
        f"<tr><td>{_e(r['arm'])}</td><td>{_e(r['task_id'])}</td>"
        f"<td>{_e(str(r['error'])[:120])}</td></tr>"
        for r in report.error_rows[:20]
    )
    return f'<div class="scroll"><table>{head}{rows}</table></div>'


def _footer(report: Report) -> str:
    lines = []
    if report.report_class == "controlled":
        lines.append("Controlled result. Programmatic grading only; writes are "
                     "graded on final server state, never on the transcript.")
    if report.truncated_count:
        lines.append(f"{report.truncated_count} runs hit max_turns and are "
                     "excluded from success rates.")
    lines.append(POOLING_RULE)
    return "<footer>" + "<br>".join(_e(x) for x in lines) + "</footer>"
