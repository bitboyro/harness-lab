---
name: harness-insights
description: >-
  Produce a narrative insights.html brief from a harness results directory
  (results.jsonl + manifest.json + report.html). Use when the user asks for
  insights, an insights report, a narrative reading of a matrix run, or a
  beautiful HTML summary of harness packaging results.
---

# Harness insights brief

Turn a completed harness run into `insights.html`: same structure and visual
system every time, numbers taken only from the extract script.

## Workflow

Copy this checklist and track it:

```
Insights progress:
- [ ] 1. Locate results dir (user path, or results/<id>/)
- [ ] 2. Extract brief JSON (script below)
- [ ] 3. Copy template → <results>/insights.html
- [ ] 4. Fill every section from the brief (no invented metrics)
- [ ] 5. Open insights.html for the user
```

### 1. Inputs

Required in the results directory:

| File | Role |
|------|------|
| `results.jsonl` | ledger of every run |
| `manifest.json` | run id, model, tasks, repeats |
| `report.html` | linked from the footer (regenerate with `harness report` if missing) |

Optional context: domain skill (e.g. `skills/catalog.md`) for mechanism
explanations — never for numbers.

### 2. Extract numbers (mandatory)

Always run before writing prose. Use the project venv:

```bash
.venv/bin/python .cursor/skills/harness-insights/scripts/extract_brief.py <results-dir> --pretty
```

Save or keep the JSON. **Every percentage, dollar, second, count, and pick in
the HTML must come from this object.** If a field is null, omit that claim.

The script chooses picks deterministically (do not re-rank):

| Pick | Rule | JSON path |
|------|------|-----------|
| Careful | max precision → abstention → −FP → −harm → success among non-Z | `picks.careful` |
| Fastest | min `mean_secs` among non-Z | `picks.fastest` |
| Cheapest | min `cost_per_success` among non-Z | `picks.cheapest` |

Composite winner is `verdict.winner` (may equal careful).

### 3. Start from the template

```bash
cp .cursor/skills/harness-insights/template.html <results-dir>/insights.html
```

Keep the `<style>` block and class names unchanged. Replace `{{PLACEHOLDERS}}`
and section bodies. Remove HTML comments when done.

### 4. Section contract (fixed order)

1. **Hero** — eyebrow `Harness lab · {run.id}`; title is a claim about what
   moved the needle for *this* API/packaging matrix, not a dump of arm codes.
2. **Verdict** — ship `{verdict.winner}`; cite success / abstention / harm from
   `arms[winner]`. If `verdict.caveats` mentions an MDE tie on success, the
   `.why` paragraph must say the composite won on other dimensions.
3. **Three jobs, three picks** — careful / fastest / cheapest cards exactly as
   in the template. Controls (Z*) never appear as picks.
4. **Four findings** — exactly four; each cites `span.fig` numbers from the
   brief. Prefer themes the data supports: authored abstention lift
   (`skill_deltas`), discovery truncation (`mechanisms`), clobber fingerprint
   (`mechanisms.clobber_fields`), sandbox efficiency (`succ_peak_tokens` /
   `succ_calls` vs a high-token MCP arm).
5. **Success ladder** — render `ladder` top to bottom; `ctl` + muted fill for
   controls; `win` for the composite winner; bar width = integer success %.
6. **Authored skill deltas** — only if `skill_deltas.pairs` non-empty; use
   `success_pp_range`, `abstention_pp_range`, `authored_zero_fp`.
7. **Where {arm} still fails** — `winner_failures` clusters (top ≤5). Danger
   callout when a high-success runner-up still has `harm_events > 0` while the
   careful/winner arm has zero.
8. **Takeaways** — exactly four actionable items; cover careful pick,
   speed/cost caveats, refusal/skill lesson, one packaging mechanism fix.
9. **Footer** — link `./report.html`; include `mde_pp` and incomplete arms.

### 5. Writing rules

- Insight over inventory: few numbers, each interpreted.
- Prefer lift / deltas / contrasts over absolute tables.
- Use `&nbsp;` in `pp` and unit compounds (`23&nbsp;pp`, `15.3&nbsp;s`).
- Do not pool skill conditions that `pooling_refused` separates — the full
  report already refuses that; the brief must not re-average them.
- Do not claim statistical significance between packaging arms when the gap is
  below `run.mde_pp`.
- Voice: direct, concrete, no hype. Name arms by code (`D2-auth`) plus short
  packaging phrase from `arms.*.short` or `name`.

### 6. Output

Write only `<results-dir>/insights.html`. Do not modify `report.html` or the
ledger. Tell the user the path when done.

## Reference

- Template (CSS + skeleton): [template.html](template.html)
- Extractor: [scripts/extract_brief.py](scripts/extract_brief.py)
- Example output: `results/matrix-10/insights.html`
