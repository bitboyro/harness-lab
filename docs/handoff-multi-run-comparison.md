# Handoff — `harness compare` (multi-run comparison)

**Original plan:** `/Users/romanbotnari/.claude/plans/i-want-to-be-sunny-nygaard.md`
Read it first. It carries the Context section, the full design reasoning, and the
design-risk list. This file records what is **done**, what is **left**, and the
decisions taken during implementation that the plan did not anticipate.

**Status:** phases 1–9 complete. 474 tests passing.

---

## What the feature is

`harness compare <dirA> <dirB> [<dirC> ...]` — compare N runs. The first is the
reference; every delta is measured against it. Four decisions were settled with
the user before implementation and are not open:

1. **N runs**, not just two.
2. **Pooling breaks render anyway**, behind a stop banner naming the exact
   parameter — never a silent refusal.
3. **Arms not present in every run are eliminated from the head-to-head** and
   reported standalone in a "not compared" section. Never a blank delta cell.
4. **CSV writes three files to a directory**: `arms.csv`, `params.csv`, `rows.csv`.

---

## Done

### 1. `src/harness/engine/stats.py` — cross-run primitives

- `_paired_diff(a, b)` extracted from `compare`, so `compare` and
  `cross_compare` share one implementation of "the core is the unit".
- `WORLD_KEYS` + `world_key(report)` — the gate that decides whether two runs may
  be paired within core. Prefers `pack_digest`, falls back to
  `(seed, cores, fan_out, difficulty)`, returns `None` when any is missing.
- `CrossContrast` — one arm measured in two runs. Deliberately **has no
  `significant` property**; nothing cross-run is pre-registered.
- `cross_compare(report_a, report_b, arm, *, label_a, label_b, paired=None)` —
  three tiers: `paired-core`, `unpaired-proportions`, `intervals-only`.
- `holm()` now raises `TypeError` on a `CrossContrast`.
- `UNPAIRED_CAVEAT`, `_arm_worlds`, `_graded_counts`, `_two_sided_p`, `_newcombe`.

### 2. `src/harness/cli.py` — manifest extension + `cmd_compare`

`cmd_run`'s `write_manifest` call also records `harness_version`,
`temperature`, `caching`, `max_turns`, `concurrency`, `schema_detail`,
`response_shape`, `error_detail`, `doc_budget`, `mcp_revision`,
`sweep_error_detail`, `classes`, `max_tasks`, `pack_digest`.

`_pack_digest(tasks)` — sha256 over the sorted
`(id, core_id, task_class, answerable)` tuples of the **filtered** task list,
truncated to 16 hex.

`cmd_compare` + subparser: checks `results.jsonl` before `ResultStore` (which
mkdirs), injects `mde_pp` per run through `_build_report`, exit codes
`0`/`1`/`2`/`3` as specified. `--csv` takes a **DIR**.

### 3. `src/harness/engine/comparison.py` — the computation object

`NOT_RECORDED`, `Mixed`, `Parameter`, `PARAMETERS` (30 entries), `ParamRow`,
`PoolingBreak`, `RunRef`, `ComparisonError`, `label_runs`, `extract`,
`Comparison`.

### 4. `comparison_text.py` + `comparison_html.py` — two renderers

Section order is identical in both and fixed:
header → **stop banner (pooling)** → power banner → **what differs** →
**not compared** → head-to-head → cross-run contrasts → charts (HTML) →
every parameter → glossary → footer.

### 5. `comparison_csv.py` — three files

`write(comparison, out) -> list[Path]`: `arms.csv`, `params.csv`, `rows.csv`.
`rows.csv` takes the **union** of fieldnames across runs (does not reproduce
the `report --csv` first-row bug).

### 6. Glossary

`# ---- comparing runs ----` block in `glossary.py`: `reference run`,
`Δ / delta`, `shared arm`, `not compared`, `not recorded`, `same world`,
`unpaired comparison`, `cross-world delta`, `cross-run MDE`, `parameter diff`,
`confidence interval`.

### 7. Tests

- `tests/test_comparison.py` — arm intersection, parameter diff (incl. AST
  drift guard), pooling, anti-drift, CSV, CLI.
- `tests/test_stats.py` — `# ---- across runs ----` (world key, Newcombe,
  holm refusal, MDE, shared `_paired_diff`).

### 8. Docs

- `docs/running-the-experiment.md` — `## Comparing runs`
- `docs/statistical-plan.md` — new §6 (old 6→7, 7→8); unblocks the
  dangling `stats.py` pointers
- `docs/harness-benchmark-spec.md` §6.4 — `manifest.json` field table
- `docs/decisions.md` — G12 (world key), G13 (no blank delta cells)
- `docs/testing-your-own-api.md` — before/after paragraph

### 9. `analysis.py` — small refactor

`POOLING_RULE` and `POOLING_FIELDS` extracted; footers read `POOLING_RULE`.

---

## Decisions taken during implementation

These were **not** in the original plan. They came out of running the code
against real ledgers, and each fixed something the plan would have shipped wrong.

### A. Absence is a property of the parameter, not a hardcoded key check

`axis_summary` writes `""` for an arm with no MCP transport while the ledger row
writes `None`. Both mean the same absence. Fixed by giving `Parameter` an
`absent_values` tuple (and `absent_label`), applied uniformly.

### B. The unpaired interval is Newcombe, not Wald

Wald collapses at the boundary (`p(1-p)=0`). Replaced with the **Newcombe
hybrid-score interval**. Real data that used to read
`+32.7% 95% CI [+24.0%, +41.5%] p=0.0000` now reads
`+32.7% 95% CI [-33.5%, +41.9%] p=0.0892`.

### C. `notable` also requires the interval not to span zero

### D. The head-to-head consults the contrast, not the MDE

`Comparison.unresolved` for `success` returns `not contrast.notable`.

### E. `Comparison.fmt` handles non-numeric values

### F. Text truncation is marked

### G. Delta charts take points, not fractions

---

## Verified

```bash
.venv/bin/python -m pytest tests/ -q          # 474 passed

.venv/bin/harness compare results/matrix-10 results/legend-check --glossary
# unpaired fallback; B1 = +32.7% CI [-33.5%, +41.9%] p=0.0892; 8 arms not compared

.venv/bin/harness compare results/legend-check results/auth-smoke
# "no arm is present in every run"

.venv/bin/harness compare results/matrix-10 results/auth-smoke \
  --html /tmp/cmp.html --charts /tmp/cmp-charts --csv /tmp/cmp-csv
# self-contained HTML, 6 charts, three CSVs
```

**Optional follow-up (not blocking):** `report --csv` still takes fieldnames from
the first row and raises `ValueError` when mixing ledgers with different keys.
Flagged in the plan; do not bundle with this feature.

**Note on test material:** `results/full` no longer has a ledger (only `traces/`).
Usable dirs: `matrix-10`, `legend-check`, `auth-smoke`. Every ledger in
`results/` today predates the manifest extension, so newly-recorded parameters
read `not recorded` — correct behaviour.

---

## Do not disturb

A `watch -n 30 harness progress results/matrix-40` may be running in another
terminal. `results/matrix-40/` is currently staged-then-deleted in git and does
not exist on disk. `results/full/` has only `traces/` — no ledger.
