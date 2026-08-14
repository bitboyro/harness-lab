# Experiment sidecar schema (S6)

**Status:** Contract draft — additive only; does not change `manifest.json`,
`results.jsonl`, `RunPlan`, or the CLI resume behaviour until engine support
lands (stream E1 on `main`).

An **experiment** is optional metadata that sits beside an existing results
directory. A run without `experiment.yaml` behaves exactly as today. Adding the
file upgrades the directory to an experiment without moving or rewriting the
ledger.

---

## Layout decision: sidecar

The ledger stays where it is. No `experiments/` top-level directory.

```
/data/results/<id>/
  experiment.yaml      ← optional sidecar (this schema)
  manifest.json        ← unchanged; written by harness run
  results.jsonl        ← unchanged; append-only ledger
  traces/
  artifacts/
  reports/             ← optional; dated report snapshots (experiment-only)
    2026-08-13T120000-active.json
  jobs/                ← NOT here — still /data/jobs/<id>/
```

**Why sidecar:** `RunService`, `list_runs`, `get_report`, and `progress` already
key on `/data/results/<id>/`. Pointing them at the same path when
`experiment.yaml` appears avoids a migration and keeps fixture runs (`auth-smoke`)
valid with zero changes.

Importing a standalone `plans/*.yaml` into a run directory:

```bash
# future CLI — not implemented yet
harness experiment init plans/baseline-experiment-80.yaml --out results/baseline-experiment-80
# writes experiment.yaml; first `harness run` still creates manifest.json + ledger
```

---

## Design rules

1. **Additive only.** Nothing in this file replaces or rewrites `manifest.json`.
   The manifest remains the run-time snapshot the CLI wrote; `experiment.yaml`
   is the declared intent and lifecycle.
2. **`run_plan` is the existing shape.** The `run_plan:` block is byte-for-byte
   the same schema as `plans/*.yaml` and `examples/plan.yaml` — same keys,
   same loader (`RunPlan` in `engine/planner.py`). No renamed fields.
3. **Inline or reference, not both.** Either embed `run_plan:` or set `plan:` to
   a path; loaders reject both.
4. **Arms grow, world locks.** Once `results.jsonl` has non-infra rows, fields
   that reseed the catalog (`tasks.generate.seed`, `tasks.generate.cores` when
   it shrinks, `pack` identity) cannot change. Adding presets under
   `include.presets` is allowed; removing an arm moves it to `retired_arms`.
5. **Confirmatory is append-only** after any confirmatory cell has data — same
   rule as `harness plan --strict`.
6. **Slices filter, never fork.** A slice selects a subset of arms and/or cores
   from the declared experiment; it schedules missing cells only and writes
   into the same ledger.

---

## Schema

```yaml
schema_version: 1

experiment:
  id: string                    # MUST match the results directory name and manifest id
  status: draft | active | paused | complete | archived
  created_at: ISO-8601
  updated_at: ISO-8601

  # --- declaration (pick one) -----------------------------------------------

  run_plan:                     # same object as the root key in plans/*.yaml
    id: string
    rationale: string
    base: { ... }               # axis defaults; same as RunPlan.base
    include:
      presets: [string, ...]
    arms: { ... }               # optional custom arms; same as RunPlan.arms
    tasks:                      # controlled: generate{…}; field: pack path
      generate: { seed, cores, fan_out, difficulty, ... }
      # pack: ../../packs/mine.yaml
    sweep: { ... }              # optional
    budget: { max_usd: number }
    confirmatory: [{ contrast: [a, b], hypothesis: string }, ...]
    exploratory: [...]

  # plan: plans/baseline-experiment-80.yaml   # alternative to inline run_plan

  # --- additive experiment fields (not in RunPlan) --------------------------

  slices:                       # named subsets — "small experiments"
    <slice_id>:
      description: string       # optional
      arms: [string, ...]       # optional; default = all declared presets
      cores: int | [int, ...]   # optional; int = first N cores; list = explicit ids

  retired_arms: [string, ...]   # removed from scheduling; ledger rows kept

  episodes:                     # execution history (one row per spend)
    - id: string
      started_at: ISO-8601
      finished_at: ISO-8601 | null
      slice: string | null      # slice id, or null for full declared set
      arms_scheduled: [string, ...]   # preset names this episode targeted
      planned_cells: int        # cells scheduled (missing + voided)
      completed_before: int     # ledger rows before this episode
      job_id: string            # links /data/jobs/<job_id>/

  report_snapshots:
    - at: ISO-8601
      status: string            # experiment status at snapshot time
      path: string              # relative to results dir, e.g. reports/….json
      ledger_rows: int
      digest: string            # optional; hash of adapter report payload
```

### Field consumers

| Field | Read by | Notes |
|---|---|---|
| `schema_version` | loader | `1` today |
| `experiment.id` | UI, adapter | must equal directory basename |
| `experiment.status` | UI | operator lifecycle; does not gate CLI |
| `run_plan` / `plan` | planner, adapter, future `harness experiment` | declaration |
| `slices` | run scheduler | filters missing-cell set |
| `retired_arms` | scheduler | excluded from declared presets |
| `episodes` | UI timeline | append-only |
| `report_snapshots` | UI reports tab | append-only |
| `manifest.json` | everything today | **not** duplicated here |

---

## Status lifecycle

| Status | Meaning |
|---|---|
| `draft` | Declared, never spent |
| `active` | Has ledger rows; declared cells remain or voided infra rows exist |
| `paused` | Operator halt; no in-flight job required |
| `complete` | All declared cells filled (non-infra); arms may still be added → back to `active` |
| `archived` | Read-only; no new episodes |

`complete` is coverage against the **current** declaration, not "science finished."

---

## Missing-cell scheduling (engine E1 — specified here, implemented on main)

When `harness experiment run DIR [--slice SLICE]` lands:

```
declared = run_plan.include.presets − retired_arms
         × tasks from run_plan.tasks
         × run_plan.base.repeats
         [filtered by slice arms/cores if set]

done     = ResultStore.completed()
voided   = ResultStore.voided()
schedule = declared − done ∪ voided
```

This replaces today's `--resume` preset lock for experiment directories only.
Plain runs without `experiment.yaml` keep existing `--resume` behaviour.

---

## Backwards compatibility matrix

| Case | Behaviour |
|---|---|
| No `experiment.yaml` | Unchanged run directory |
| `experiment.yaml` added to existing run | Becomes experiment; ledger untouched |
| `run_plan` matches `manifest.json` presets/world | Consistent |
| `run_plan` adds presets after partial run | Next episode schedules new arm cells only |
| Field run (`pack` in tasks) | Same sidecar; `report_class: field` in pack |
| `harness report DIR` | Unchanged; ignores sidecar |
| UI `list_runs` | Returns all dirs; `hasExperiment: true` when sidecar present |

---

## Example

See [../examples/experiment-baseline-80.yaml](../examples/experiment-baseline-80.yaml) —
declaration copied from [../../plans/baseline-experiment-80.yaml](../../plans/baseline-experiment-80.yaml).

Placed beside a ledger:

```
results/baseline-experiment-80/experiment.yaml   ← this file
results/baseline-experiment-80/manifest.json       ← after first harness run
results/baseline-experiment-80/results.jsonl
```
