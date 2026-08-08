# Proposal: Operation ledger — where agents spend and stumble

**Status:** Proposal — not adopted, not scheduled  
**Date:** 2026-08-07  
**Motivated by:** Customer ask for most-used / most-misused operations and resource families (e.g. program vs service), without misleading “worst endpoint” charts  
**Companions:** [`harness-benchmark-spec.md`](./harness-benchmark-spec.md) §6.4 (traces) · [`plan.md`](./plan.md) §5 (mechanism metrics) · [`task-pack-schema.md`](./task-pack-schema.md) (`core_id`, `gold_call_sequence`)

This is a design note for a later implementation. It does not change presets, axes, winner weights, or confirmatory contrasts until adopted into `decisions.md` / `plan.md`.

---

## 1. Problem

Traces already record every tool call and every sandbox/bash body. The report only surfaces **scalar** mechanism means (`wasted_calls`, `redundant_calls`, `hallucinated_endpoints`, …).

Customers ask a different question: **which parts of *their* API do agents lean on, and which ones do they misuse** — overall and per packaging arm — so they know what to document, constrain, or redesign.

A naive “ops on failed runs” chart will lie: volume confounds with task shape, discovery meta-tools look like product endpoints, and clean HTTP 200s still clobber state.

---

## 2. Proposal in one sentence

At report time, build an **operation ledger** from existing traces (joined to `results.jsonl`), score each resolved op with rate-based misuse signals, and present a small customer-facing section: **where agents spend**, **where they stumble**, and **which resource families hurt** — sliced by arm and task class.

---

## 3. What to track

### 3.1 Resolve every call to a target operation

| Arm | Resolution |
|---|---|
| Eager MCP (A1/B1) | `call.tool` |
| Meta-tools (A2/B2) | `invoke_operation` → `args.operation_id` (ignore or separately bucket `search_` / `describe_`) |
| Code sandbox (D*) | Prefer persisted server request log; else parse `operations.<id>` from `raw` |
| Shell (C*) | Prefer server request log; else parse `curl` path → op via OpenAPI map |

**Out of scope for “target API” charts:** discovery meta-tools, bare `dir()` / help probes. Show those only in a packaging footnote if volume is high.

### 3.2 Attributes per resolved call

- `op_id`, `family` (OpenAPI tag, or path/name stem: `episodes`, `assets`, … / customer: `programs`, `services`)
- `arm`, `task_class`, `answerable`, `core_id`
- flags: `http_error` (4xx/5xx or sandbox nonzero), `forbidden`, `known_operation`, `off_gold` (vs task `gold_call_sequence` when present), `redundant` (duplicate signature in-run)

### 3.3 Aggregate scores (not raw counts alone)

| Score | Definition | Customer meaning |
|---|---|---|
| **Usage share** | calls to op / all *target* calls (within slice) | Where agents spend |
| **Error rate** | http_error / calls to op | Flaky or hard-to-call surface |
| **Off-gold rate** | off_gold / calls to op (answerable tasks with gold) | Distractors & wrong routes |
| **Forbidden rate** | forbidden / calls to op | Safety / scope violations |
| **Fail association** | P(run fails \| op used) − P(fail \| class baseline) | Lift over base rate — exploratory only |

Primary “misused” rank = composite of **off-gold + forbidden + error** (weights documented). Fail-association is secondary, never the headline.

**Do not** rank by “appearances on failed runs.”

---

## 4. How (implementation shape)

Fits the existing contract: traces are full fidelity; summaries are recomputed.

1. **No change** to agent loop, grading, winner formula, or `results.jsonl` columns.
2. **New** report-time module (e.g. `engine/ops.py`): load `traces/` + rows → ledger → tables.
3. **`Report`** gains op/family tables; **`reporting.py` / `html.py`** render one section.
4. **Optional hardening (phase 2):** persist `CatalogApi.requests` (or field HTTP access log) onto the trace so C/D match A/B without fragile `raw` parse.
5. **Tests:** resolver fixtures per arm shape; aggregation rate math; “meta-tools excluded from target charts.”

Re-run `harness report` on existing matrix dirs; no new matrix required to validate.

---

## 5. What to present (customer report)

One section, after mechanism metrics. Three blocks only — insight over inventory.

### A. Where agents spend (usage)

- Top target ops **per arm** (usage share), and **family rollup** (e.g. programs vs services).
- One line of guidance: “Spend follows the task shape; use this to prioritize docs and examples, not to declare winners.”

### B. Where agents stumble (misuse)

- Top misused ops **per arm** and **overall**, ranked by the composite rate (show the rate, not count).
- Stratify or tab **by class**: reads (`R`) vs writes (`W-*` / `RW-fan`) vs unanswerable — different failure modes.
- Call out **distractors** (high off-gold, low/zero gold membership), e.g. assets when the gold path never touches them.

### C. Family snapshot

- Small table: family → usage share → misuse rate → worst op in family.
- Customer takeaway form: “Agents over-touch **X**; misuse concentrates on **Y** (`replace_*` / wrong archive scope / …). Packaging arm **Z** reduces that rate by …”

### Explicitly omit from v1

- Per-`task_id` leaderboards (case studies only).
- Mixing discovery meta-tools into the main chart.
- Claiming significance between arms on op rates without the same MDE discipline as success (label as descriptive).

---

## 6. Interpretation guards (must appear in UI copy)

- Volume ≠ blame; prefer rates.
- HTTP-clean can still harm (clobber) — pair with existing harm/clobber metrics.
- Unanswerable thrash is an abstention story, not an endpoint outage.
- Arm differences in *which* ops appear are packaging shape until rates move.

---

## 7. Success criteria

A customer can answer, from the HTML report alone:

1. Which **resource families** do agents use most under our recommended arm?
2. Which **operations** are most often wrong-route / forbidden / erroring?
3. What should we **document, hide, or redesign** first?

If the section only produces a global “`get_episode` is #1 on fails” chart, the proposal has failed.

---

## 8. Non-goals

- Changing composite winner scoring.
- Bloating every JSONL row with histograms.
- Replacing gold-free mechanism metrics; this *names* what those scalars compress.
