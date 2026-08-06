"""The HTML results report.

Self-contained: inline style, inline SVG, no external requests of any kind.

The ordering is deliberate. Caveats sit at the **top**, not in a footer, because
they change how every chart below should be read — a reader who learns about the
MDE after looking at the bars has already formed an impression the bars did not
earn.

Contract: docs/harness-benchmark-spec.md deliverable 7
"""

from __future__ import annotations

from html import escape
from typing import Any

from .analysis import OUTCOME_ORDER, Report
from .svg import bar_chart, Bar, grouped_bars, heatmap, legend, palette_css, scatter, stacked_bars

#: Outcome severity, light (benign) to dark (dangerous). Truncation sits off the
#: ramp entirely on a neutral fill: it is the absence of a grade, not a worse
#: one, and colouring it as a severity step would misstate what happened.
OUTCOME_FILLS = ("var(--ord-1)", "var(--ord-2)", "var(--ord-3)",
                 "var(--ord-4)", "var(--ord-5)", "var(--neutral)")

_CSS = """
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, sans-serif;
         background: var(--surface-1); color: var(--text-primary); }
  .wrap { max-width: 860px; margin: 0 auto; padding: 32px 20px 72px; }
  h1 { font-size: 20px; margin: 0 0 4px; letter-spacing: -0.01em; }
  h2 { font-size: 15px; margin: 34px 0 10px; letter-spacing: -0.005em; }
  h3 { font-size: 12px; margin: 18px 0 6px; color: var(--text-secondary);
       font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  p  { margin: 0 0 10px; color: var(--text-secondary); }
  .sub { color: var(--text-muted); font-size: 12px; }
  .note { font-size: 12px; color: var(--text-muted); margin: 6px 0 0; }
  .banner { border-left: 3px solid var(--status-warning); padding: 10px 14px;
            background: var(--band); border-radius: 0 6px 6px 0; margin: 6px 0; }
  .banner.stop { border-left-color: var(--status-critical); }
  .banner.ok { border-left-color: var(--status-good); }
  .banner b { color: var(--text-primary); }
  .legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 8px 0 4px;
            font-size: 11px; color: var(--text-secondary); }
  .chip { display: inline-flex; align-items: center; gap: 5px; }
  .chip i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  .scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 12px;
          font-variant-numeric: tabular-nums; }
  th, td { text-align: right; padding: 5px 9px; border-bottom: 1px solid var(--grid); }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--text-secondary); font-weight: 600; white-space: nowrap; }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
           gap: 18px; }
  .card { border: 1px solid var(--grid); border-radius: 8px; padding: 12px 14px; }
  .card h4 { margin: 0 0 8px; font-size: 13px; }
  .kv { display: flex; justify-content: space-between; font-size: 11px;
        color: var(--text-secondary); padding: 2px 0; }
  .kv b { color: var(--text-primary); font-weight: 600; }
  footer { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--grid);
           font-size: 11px; color: var(--text-muted); }
"""


def _e(v: Any) -> str:
    return escape(str(v), quote=True)


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

    # 7. Metrics that actually vary.
    for metric in report.varying_metrics():
        bars = [Bar(label=a, value=report.arms[a].metric_mean(metric), slot=1)
                for a in arms]
        if any(b.value is not None for b in bars):
            charts[f"metric-{metric}"] = bar_chart(
                bars, title=metric.replace("_", " "), unit="")
    return charts


def render_html(report: Report) -> str:
    charts = build_charts(report)
    arms = sorted(report.arms)
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
    for name in arms:
        c = report.arms[name].confusion
        if not c.total:
            continue
        out.append(f'<div class="card"><h4>{_e(name)}</h4>')
        out.append(charts.get(f"confusion-{name}", ""))
        for label, value in (("precision", c.precision), ("recall", c.recall),
                             ("F1", c.f1), ("accuracy", c.accuracy),
                             ("balanced acc.", c.balanced_accuracy),
                             ("specificity", c.specificity)):
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

    # ---- efficiency ------------------------------------------------------
    varying = report.varying_metrics()
    if varying:
        out.append("<h2>Mechanism</h2>")
        for metric in varying:
            key = f"metric-{metric}"
            if key in charts:
                out.append(charts[key])
    constant = report.constant_metrics()
    if constant:
        names = ", ".join(f"{k} = {v:g}" for k, v in constant.items())
        out.append(f'<p class="note">No variation across any run on: {_e(names)}. '
                   f"Charting these would imply a difference that is not there.</p>")
    out.append('<p class="note">Every metric above is <b>unvalidated</b>: its '
               "relationship to ground truth has not been established on the "
               "controlled rig.</p>")

    # ---- tables ----------------------------------------------------------
    out.append("<h2>Details</h2>")
    out.append(_arm_table(report))
    if len(report.task_classes) > 1:
        out.append("<h3>Success by class</h3>")
        out.append(_class_table(report))
    if report.error_rows:
        out.append("<h3>Harness errors</h3>")
        out.append(_error_table(report))

    out.append(_footer(report))

    body = "\n".join(out)
    return (
        "<style>\n" + palette_css() + "\n" + _CSS + "\n</style>\n"
        f'<div class="viz"><div class="wrap">{body}</div></div>'
    )


def standalone_html(report: Report) -> str:
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
        f"<body>{render_html(report)}</body></html>"
    )


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


def _arm_table(report: Report) -> str:
    pricing = report.pricing
    head = ("<tr><th>arm</th><th>n</th><th>success</th><th>95% CI</th>"
            "<th>lift</th><th>turns</th><th>calls</th><th>static</th>"
            "<th>trunc</th><th>harm</th><th>$/success</th><th>cached</th></tr>")
    rows = []
    for name in sorted(report.arms):
        a = report.arms[name]
        ci = a.success_ci
        lift = report.lift(name)
        cps = a.cost_per_success(pricing)
        rows.append(
            f"<tr><td>{_e(name)}</td><td>{a.n}</td>"
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


def _class_table(report: Report) -> str:
    classes = report.task_classes
    head = "<tr><th>arm</th>" + "".join(f"<th>{_e(c)}</th>" for c in classes) + "</tr>"
    rows = []
    for name in sorted(report.arms):
        per = report.arms[name].by_class()
        cells = "".join(f"<td>{_pct(per.get(c))}</td>" for c in classes)
        rows.append(f"<tr><td>{_e(name)}</td>{cells}</tr>")
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
    lines.append("Never pool across model, MCP revision, skill condition, or "
                 "report class.")
    return "<footer>" + "<br>".join(_e(x) for x in lines) + "</footer>"
