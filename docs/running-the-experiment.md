# Running the controlled experiment

How to launch the matrix on the fictional mock API, and what every parameter
does. For pointing the harness at **your own** API, see
[`testing-your-own-api.md`](./testing-your-own-api.md).

---

## Setup, once

```bash
cd harness-lab
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,openai]'
```

Put your key in `.env` at the repo root (gitignored):

```
OPENAI_API_KEY=sk-...
```

Nothing needs exporting — every command reads `.env` and prints which names it
loaded. Then either `source .venv/bin/activate` and use `harness`, or call
`.venv/bin/harness` directly.

Check it works — this costs nothing and needs no key:

```bash
harness lint <(python -c "
import json;from harness.experiment.openapi import build_spec;print(json.dumps(build_spec()))")
```

---

## The recommended run

40 cores, 3 repeats, every arm, concurrency 16.

```bash
harness run \
  --out results/matrix-40 \
  --id matrix-40 \
  --model gpt-5.6-luna \
  --reasoning-effort low \
  --difficulty hard \
  --cores 40 \
  --fan-out 8 \
  --surface-size 50 \
  --repeats 3 \
  --max-turns 12 \
  --concurrency 16 \
  --presets Z0 Z1 A1 A2 B1 B2 B1-auth B2-auth C1 D1 D2 D2-auth
```

**~8,500 runs, roughly 4–5 hours, roughly $100.** It prints a projection and
waits for confirmation; add `--yes` to skip that.

Why these values:

- **`--cores 40`** — 40 distinct navigation problems. Cores, not repeats, are
  what buy statistical power (see below). 40 is where the main-effect MDE
  reaches ~10 pp at 3 repeats.
- **`--difficulty hard`** — at `standard` every arm scored ~100% and nothing
  could be distinguished. `hard` identifies targets by property rather than
  location, so the agent must search rather than walk a path it was handed.
- **`--surface-size 50`** — pads the 16 core operations with distractors.
  Tasks still only target the core, so this measures selection difficulty
  rather than task difficulty.
- **`--presets`** — includes the `-auth` arms, which are the only way RQ1 gets
  an answer. Excludes `D3 E1 M1`, which have no pre-registered contrast; add
  them if you want exploratory coverage.

### Watching it

From a second terminal:

```bash
watch -n 30 harness progress results/matrix-40
```

```
  █████████████·············  3800/8500 (44%)  eta 2h
  per arm: A1 340  A2 340  B1 340 …
  outcomes: pass 2100  fail 1200  truncated 300  correct-refusal 190
```

Results are written **per run**, so this is always current and the report works
mid-flight. If it dies, `--resume` continues from what is on disk.

### Reading it

```bash
harness report results/matrix-40                      # terminal
harness report results/matrix-40 --glossary           # every term explained
harness report results/matrix-40 --sort cost          # rank by any dimension
harness report results/matrix-40 --weights harm=1     # the safety ranking alone
harness report results/matrix-40 \
    --html results/matrix-40/report.html \
    --charts results/matrix-40/charts
harness report results/matrix-40 --csv > matrix.csv   # your own analysis
```

The report opens with a **verdict**: every arm ranked, and one named as the
winner. In the HTML, any column heading sorts the table.

---

## How the winner is chosen

Five dimensions, each rescaled 0–1 across the packaging arms, oriented so higher
is always better, then weighted:

| Dimension | What it measures | Weight |
|---|---|---|
| success | tasks got right, correct refusals included | **0.35** |
| abstention | of the tasks with *no* answer, the share correctly declined | **0.15** |
| harm | runs that destroyed data or attempted a forbidden call | **0.25** |
| cost | dollars per task actually solved | **0.15** |
| time | wall-clock seconds per run | **0.10** |

Safety (0.40 combined) outweighs thrift (0.25), so an arm cannot buy the top spot
by being cheap and dangerous. Override with
`--weights success=.5,cost=.5`; unnamed dimensions are **dropped**, not
defaulted, so `--weights harm=1` means harm alone.

**Why abstention is scored separately.** Correct refusals already count as
successes. But only ~15% of tasks are unanswerable, so an arm that fabricates an
answer on *every one of them* loses at most 15 points of success rate — about
0.05 of composite score. Far too little for the failure that matters most, so it
gets its own weight.

**Controls are never candidates.** `Z0` has no tools and `Z1` is handed the
answers; neither is something you could ship, and letting `Z1` into the range
would compress every real arm into the bottom of the scale. They are shown,
marked `†`, and excluded from scoring.

**The score is a decision aid, not evidence.** A composite will always produce a
ranking, including one built entirely out of noise. So the verdict prints
alongside it whether the leader's lead on success exceeds the run's MDE:

```
  On success, B1 and D2 are TIED: 9.7 pp apart, below the 40.2 pp this
  run can detect. The score gap is made of the other dimensions, not of
  accuracy.
```

It also refuses to pick when arms tie exactly, names any dimension that
separated nothing, and says so when the winner harms or fabricates more than its
runner-up. Read the score to shortlist; read the interval before acting.

### Sorting

`--sort` accepts `score` (default), `success`, `lift`, `abstention`, `cost`,
`tokens`, `time`, `turns`, `harm`, `trunc`, `name`. Arms with no value on the
chosen dimension sort last — an absent number is not a small one.

---

## Every parameter

### What is being run

| Flag | Default | What it does |
|---|---|---|
| `--out DIR` | `results` | Where the ledger, traces and manifest go |
| `--id NAME` | `phase-0` | Label for this matrix, shown in the report header |
| `--presets ...` | `Z0 A1 A2 C1 D1` | Which arms to run. Names below |
| `--repeats N` | `1` | Times each arm attempts each task |
| `--resume` | off | Skip runs already in `--out`. Safe to re-run after a crash |
| `--yes` | off | Skip the spend confirmation |
| `--concurrency N` | `8` | Runs in flight at once |

**On `--concurrency`:** almost all of a run is waiting on the provider, so this
is close to a linear speedup — 8 turns a 20-hour matrix into 2.5 hours. Runs
are independent by construction (each gets its own seeded API instance and
ephemeral port), so raising it does not affect results, only rate limits. If
you hit one, failed runs are recorded and `--resume` picks them up.

### The task set

| Flag | Default | What it does |
|---|---|---|
| `--cores N` | `3` | Navigation problems. Each yields 5 matched tasks |
| `--difficulty` | `standard` | `standard` or `hard` |
| `--fan-out N` | `8` | Episodes per season — the blast radius on bulk tasks |
| `--classes ...` | all | Limit to e.g. `R W-safe`. Useful for a smoke run |
| `--max-tasks N` | all | Hard cap on tasks, for a quick check |
| `--seed N` | `1` | Regenerates an identical world. Same seed, same tasks |

**On `--cores` vs `--repeats`:** they are not interchangeable. A repeat runs the
*same* problem again and only reduces measurement noise. A core is a *new*
problem, and only cores reduce the variation in how much the packaging helps.
Ten times the repeats buys less than tripling the cores. To size deliberately:

```bash
harness rig --for-contrast interaction --target-mde 15   # tells you the cores needed
harness rig --cores 40                                    # shows what 40 buys
```

### The API's own design

These change the API rather than the packaging — the "is fixing my errors
cheaper than shipping a skill?" question.

| Flag | Default | What it does |
|---|---|---|
| `--error-detail` | `field-scoped` | `terse` = "validation failed". `field-scoped` names the field. `field-scoped+remedy` adds what it expected and what it got |
| `--response-shape` | `as-is` | `sparse` returns only identifying fields; `budgeted` truncates long lists |
| `--schema-detail` | `standard` | `rich` adds examples and an error taxonomy to each tool |
| `--surface-size N` | `0` | Pad to N operations with distractors. `0` = the 16 core ones |
| `--doc-budget` | `standard` | Length of generated prose: `terse`, `standard`, `verbose` |

### Sweeps

```bash
harness run --sweep-error-detail terse field-scoped field-scoped+remedy ...
```

Runs every arm once per level, labelled `A1@terse`, `A1@field-scoped`, … The
report then tells you whether the property earned its lint rule:

```
  lint-rule evidence:
    undescribed-errors  A1@terse → A1@field-scoped+remedy: +12.0% success rate
```

Only a sweep can justify a lint rule. Comparing arms tells you about packaging;
the rules are about the API, so the evidence has to come from varying the API.

### The model

| Flag | Default | Notes |
|---|---|---|
| `--model` | `gpt-5-mini` | Must be in the pricing table or have `HARNESS_PRICE_<MODEL>` set |
| `--reasoning-effort` | `low` | Never defaulted by the provider — always sent explicitly |
| `--temperature` | `0.0` | Dropped automatically if the model rejects it, and the omission is recorded |
| `--caching` | `off` | `on`, or `list-cacheable` for protocol-level caching |
| `--max-turns` | `12` | Turn budget. Hitting it is *truncation*, not a wrong answer |
| `--mcp-revision` | `2026-07-28` | Or `legacy`. Results are never pooled across revisions |

Pricing a model that is not in the table:

```bash
# input,cached,cache-write,output  (USD per million tokens)
echo 'HARNESS_PRICE_MY_MODEL=0.20,0.02,0.25,1.20' >> .env
```

---

## The arms

| | |
|---|---|
| **Z0** — *No tools* | No tools at all. Measures what the model already knew — everything else is read as lift over this |
| **Z1** — *Answers handed over* | Correct responses pre-fetched. The ceiling: what is achievable when packaging is not the obstacle. Read tasks only |
| **A1** — *MCP, all tools* | MCP, every operation schema loaded upfront |
| **A2** — *MCP, discovery* | MCP, 3 meta-tools (search/describe/invoke); schemas on demand |
| **B1 / B2** — *… + skill* | A1 / A2 **+ a generated skill** (mechanical, from the spec) |
| **B1-auth / B2-auth** — *… + authored skill* | A1 / A2 **+ the authored skill** (`skills/catalog.md`) |
| **C1 / C2** — *Bash + docs / + index* | Bash + curl against a written reference (full / index-only) |
| **D1** — *Code sandbox* | Code sandbox; operations as an importable module tree |
| **D2 / D2-auth** — *Code sandbox + skill* | D1 + a generated / authored skill |
| **D3** — *Code, discovery* | Discovery *from* code — the triad reachable inside the sandbox |
| **E1** — *MCP, retrieved* | Top-k operations retrieved for it; it never asks |
| **M1** — *MCP, all tools + confirm* | A1, but the server asks before destructive operations |

The italic names are what the report prints beside each code. They are **derived
from the axis assignment**, not written down per preset — change a preset and the
name changes with it, so a chart can never be labelled with something the run
was not.

`Z0` is not optional. Without it there is no baseline and the numbers cannot be
read as lift.

---

## The pre-registered comparisons

Declared in code at [`stats.py`](../src/harness/engine/stats.py) `CONFIRMATORY`,
before any run — so none can be added after seeing results.

| Contrast | Question |
|---|---|
| B1 vs A1 | Does a skill help on an identical surface? (RQ1) |
| B2 vs A2 | The same, under discovery |
| A2 vs A1 | Load everything, or discover on demand? (RQ2) |
| C1 vs A1 | Typed tools vs freehand curl (RQ3) |
| D1 vs A1 | Does keeping results out of context pay off? |
| D2 vs D1 | A skill on top of code execution |
| B1-auth vs B1 | Is a hand-written skill better than a generated one? (V9) |
| B2-auth vs B2 | The same, under discovery |
| D2-auth vs D2 | The same, on code execution |

Everything else is exploratory: reported, labelled, and never called
significant.

---

## What to expect, and what would be wrong

**Should hold:**

- **Z0 gate PASS.** ~0/N answered without API access. A failure means the
  fictional domain leaked into training and the whole run is void.
- **Z1 above every other arm.** It is the ceiling by construction.
- A "refusing to pool" banner when generated and authored skills are both
  present. That is correct — they are different conditions.

**Would indicate a problem:**

- **An arm near 0%.** Read its traces before believing it. A prompt bug once
  scored code execution at 20% and it looked like a finding.
- **Truncation above ~30%** — raise `--max-turns` or the arm is thrashing.
- **Every interval spanning zero** — underpowered. Add cores, not repeats.

---

## Costs and timings, measured

At `gpt-5.6-luna` rates, `--reasoning-effort low`, ~25s per run sequential:

| Configuration | Runs | Concurrency 16 | Cost |
|---|---|---|---|
| Smoke: 2 cores, 3 arms | ~40 | ~2 min | ~$0.05 |
| Phase 0: 6 cores, 9 arms | ~280 | ~10 min | ~$1 |
| **Recommended: 40 cores × 3, 12 arms** | ~8,500 | **~4.5 h** | **~$100** |
| 40 cores × 1, 12 arms | ~2,800 | ~1.5 h | ~$35 |

The projection printed before each run is calculated from the actual rate card,
including the reasoning-effort multiplier.
