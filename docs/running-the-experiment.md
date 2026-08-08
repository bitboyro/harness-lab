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

40 cores, 3 repeats, every arm, concurrency 24.

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
  --concurrency 24 \
  --presets Z0 Z1 A1 A2 B1 B2 B1-auth B2-auth C1 D1 D2 D2-auth
```

**~8,500 runs, roughly 2 hours, roughly $100.** It prints a projection and
waits for confirmation; add `--yes` to skip that.

The hours are a function of `--concurrency`, not of the matrix: ~45 hours of
summed provider latency divided by however many runs are in flight. At the old
default of 8 this was 4–5 hours. See the note on `--concurrency` below before
raising it further.

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

### When the machine breaks, not the arm

A run can fail for reasons that have nothing to do with the packaging being
measured — the disk fills, the API key expires, the provider 429s. Those rows
are graded `infra-error`, carry an `error_kind` (`disk`, `auth`, `billing`,
`rate_limit`, `timeout`, …), are **excluded from every rate**, and are **re-run
by `--resume` rather than skipped**. A cell that measured the disk is not a
result about the arm.

Classification never reads response text. A tool result saying "unauthorized"
is the mock API doing its job; only errno, typed provider codes and transport
status can mark a run as infra.

On `disk`, `auth` or `billing` the matrix **aborts immediately** and exits 40 —
every subsequent cell would fail the same way. Fix the cause and `--resume`.
`harness run` also refuses to start if free space cannot cover the projected
traces plus 5 GB of headroom, because the swap file shares that volume.

Re-running a voided cell appends a new row; the ledger stays append-only and
the superseded row remains on disk as evidence. Readers take the newest row per
`(arm, task, repeat)`.

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

## Running it on a remote box

A 4–5 hour matrix is a poor fit for a laptop that sleeps, and the traces are
large enough to matter. The harness ports cleanly: two runtime dependencies
plus the provider SDK, no Docker, no node, no browser. Charts are emitted as
`<svg>` strings rather than drawn by a plotting library, so `report --html`
produces the same artifact on a headless VM as it does locally.

**Nothing needs to be reachable from outside.** The mock API binds `127.0.0.1`
on port `0` — one ephemeral loopback server per run — so there are no ports to
open and no reverse proxy to configure. The only outbound traffic is to the
provider.

### Sizing

**Disk is the constraint, not CPU or RAM.** The matrix is
`ThreadPoolExecutor`-parallel over work that is almost entirely provider
latency, so 2 vCPU keeps up at `--concurrency 16`; the live object graph scales
with concurrency rather than matrix size, and 4 GB is comfortable. But every
run writes a trace:

```
free space needed  =  runs × 230 KB  +  5 GB reserve
recommended matrix ≈  8,500 × 230 KB +  5 GB   ≈  7 GB
```

**⚠ AMENDED 2026-08-08:** traces are written gzipped (`.json.gz`) and the
figure above was ~900 KB before that. Measured on `matrix-40`: 870 KB of
indented JSON compresses to ~227 KB, so a full matrix costs ~2 GB of traces
rather than 6.5 GB. The change was forced rather than chosen — the machine that
produced `matrix-40` had 7 GB free and its 6.5 GB of traces plus the 5 GB
reserve no longer fit, so the next matrix would have been refused by the very
check described below. Compression costs ~18 ms of CPU against a ~19 s run.

Traces stay indented inside the gzip: compressed, `indent=2` costs 4% over
compact separators, and `gunzip -c trace.json.gz | less` on a published trace
is worth more than 4%. Nothing in the harness reads traces back — they are an
artifact for other people, and `.json.gz` says what it is without a reader.

The 5 GB is not slack. On a small machine the swap file shares the volume the
traces land on, so filling the disk does not merely fail a write — it takes
away the kernel's ability to page, and the matrix dies at 99%. `harness run`
checks this before the spend prompt and refuses to start rather than discover
it eight hours in.

A 40 GB volume therefore holds the recommended matrix several times over. If
you plan to run many, keep `--out` on a data volume you can grow.

### What to install

```bash
apt install -y python3-venv git curl tmux
git clone <repo> && cd harness-lab
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,openai]'
```

Python ≥3.11. `curl` is not optional if you are running the **C arms** — they
are freehand curl against a written reference, executed through `/bin/bash`, so
a box without curl scores C1 at zero and it will look like a finding.

**Clone, do not upload a tarball.** The `-auth` arms record the commit that last
touched `skills/` as their V9 pre-registration — the evidence the authored skill
predates the results. Outside a git checkout that lookup fails soft and records
`uncommitted`, which does not fail the run and does quietly destroy the claim.

`/tmp` must be writable **and exec-mounted**: the code and shell sandboxes run
scripts out of `mkdtemp`. Hardened images that mount `/tmp` `noexec` will fail
the C and D arms only.

### The tmux recipe

```bash
tmux new -s matrix
harness run --out results/matrix-40 --id matrix-40 ... --concurrency 16 --yes
# Ctrl-B D to detach; the run survives the ssh session dying
```

**`--yes` is mandatory here**, and not only as a convenience. The confirmation
prompt treats a non-TTY stdin as a refusal, so under `nohup`, systemd, or
`ssh host 'harness run …'` the command does not block waiting for input — it
prints `aborted` and exits 1. Inside tmux you are on a real TTY and it would
genuinely wait, which is worse: you detach, come back in an hour, and nothing
has run.

Watch it from a second pane, or a second ssh session:

```bash
watch -n 30 harness progress results/matrix-40
```

`progress` only reads the ledger, so it cannot disturb a run in flight.

### If it dies

```bash
harness run --out results/matrix-40 --id matrix-40 --resume --yes
```

Every matrix-shaping flag is read back from the manifest, so those are the only
arguments a resume needs — see [`--resume`](#every-parameter) above. Add
`--concurrency` if you want to change speed; it is deliberately not inherited.

**Prefer tmux over systemd for the run itself.** `SIGTERM` is not handled, so
`systemctl stop` terminates without flushing and without the interrupt message;
`Ctrl-C` in the tmux pane takes the graceful path. Durability holds either way —
rows are appended per run under a write lock, so whatever finished is on disk —
but only the graceful path tells you where it stopped.

Exit codes are worth wiring into a notification if you are going to walk away:
`0` finished · `40` the machine or provider broke and every subsequent cell
would have failed the same way · `3` refused to resume because the task pack no
longer matches the manifest · `130` you stopped it.

### Getting the results back

```bash
harness report results/matrix-40 --html results/matrix-40/report.html \
                                 --charts results/matrix-40/charts
scp -r vm:harness-lab/results/matrix-40/{report.html,charts,results.jsonl,manifest.json} .
```

`report.html` is self-contained — no external requests — so it opens straight
from disk. Pull `results.jsonl` and `manifest.json` too: those are what let
someone re-render or check a claim without the VM. **Leave `traces/` behind**
unless you need them; that is the multi-gigabyte part, and the report does not
read it.

You can also just run `harness report results/matrix-40` over ssh and read the
verdict in the terminal.

### Field mode

One extra dependency, and it is not on the VM: the target API has to be
reachable from it. `TARGET_BASE_URL` pointing at `localhost` means the VM's own
localhost. Task packs that grade with an external script invoke `python`, not
`python3` — on a stock Debian image that binary does not exist, so install
`python-is-python3` or make the pack call `python3` itself. The controlled
matrix never takes that path.

---

## Comparing runs

`harness report` reads one directory. When you have two (or more) and want to
know what changed — a bigger world, a different model, a field run before and
after an API fix — use `compare`. The first directory is the **reference**;
every delta is measured against it. Swapping the order flips every sign.

```bash
# same model, different worlds — the common case
harness compare results/matrix-10 results/legend-check --glossary

# no shared arms: expect a stop banner, not an empty table
harness compare results/legend-check results/auth-smoke

# every output format
harness compare results/matrix-10 results/auth-smoke \
    --html /tmp/cmp.html --charts /tmp/cmp-charts --csv /tmp/cmp-csv
```

**What you will see, in this order:**

1. **What differed in the setup** — before any result. A delta table read
   without knowing the runs used different `difficulty` is worse than no table.
2. **Not compared** — arms missing from at least one run, shown standalone.
   They are excluded from every delta rather than left as a blank cell (a blank
   reads as a zero).
3. **Head-to-head** — shared arms only, with Δ columns against the reference.
4. **Cross-run contrasts** — usually `~ unpaired`, because most re-runs change
   the world. Pairing within core needs a matching world key; see
   [`statistical-plan.md` §6](./statistical-plan.md#6-comparing-runs).

**Stop banner.** If the runs differ on model, MCP revision, skill condition, or
report class, the report leads with `REFUSING TO POOL` naming the exact
parameter. Deltas are still shown, marked `‡`, and are not findings. Exit code
**3** so `harness compare a b && publish` refuses — suppress with
`--allow-cross-world`.

**`--csv` takes a directory**, unlike `report --csv` which dumps one table to
stdout. Three files land there: `arms.csv` (one row per run×arm, including
exclusive arms), `params.csv` (one row per run plus a `__differs__` flag row),
`rows.csv` (the raw ledger with a leading `run` column).

**Exit codes:** `0` rendered · `1` a named directory has no `results.jsonl` ·
`2` bad arguments (fewer than two paths, bad `--weights`, `--label` count
mismatch, more than eight runs) · `3` rendered but a pooling boundary is broken.

**Older ledgers.** Every parameter that shapes a run now lands in
`manifest.json` so `compare` can see it. Ledgers written before that extension
read `not recorded` for those fields and produce a large "cannot be ruled out
as a difference" block. That is correct behaviour — unknown, not equal — not a
bug.

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
| `--resume` | off | Continue from what is in `--out`. Skips finished runs, re-runs infra failures. Safe after a crash — see below |
| `--yes` | off | Skip the spend confirmation |
| `--concurrency N` | `16` | Runs in flight at once |

Every parameter above, plus `temperature`, `caching`, `max_turns`,
`schema_detail`, `response_shape`, `error_detail`, `doc_budget`,
`mcp_revision`, `classes`, `max_tasks`, `pack_digest` and `harness_version`,
is written into `manifest.json` so `harness compare` can name what changed
between two runs. Pre-existing ledgers that lack those keys read as
`not recorded` — see [Comparing runs](#comparing-runs).

**On `--resume`:** ⚠ AMENDED 2026-08-07 — a resume now reads those manifest
keys back and **overrides this invocation's flags with them**, printing every
field it had to correct. Before this, `harness run --out D --id X --resume`
with no other flags rebuilt the matrix from argparse defaults: a different
`--cores` reseeds the world, so the re-run cells were about to be graded
against a *different* catalog than their siblings, and a different `--model`
or `--mcp-revision` would have appended rows across a pooling boundary. Both
are unrecoverable once written, because a row does not record which invocation
produced it. So `--out` and `--id` are the only flags a resume needs; anything
else you pass that shapes the matrix is ignored in favour of the manifest, out
loud. `--concurrency` is not inherited — it changes speed, never results.

Inheriting the parameters only makes the *inputs* match, so the resume then
rebuilds the task pack and checks it against the stored `pack_digest`. That
digest hashes prompts, not just ids, so it catches what no flag describes: a
change to task generation, the domain seeder or the difficulty ladder between
the original matrix and the resume produces identical parameters and different
questions. On a mismatch the resume **exits 3 without spending** — the same
code `compare` uses for a pooling refusal, because it is the same refusal
caught earlier. Check out the commit the manifest's `harness_version` names,
or start a fresh matrix in a new `--out`.

**On `--concurrency`:** almost all of a run is waiting on the provider, so this
is close to a linear speedup — 8 turns a 20-hour matrix into 2.5 hours. Runs
are independent by construction (each gets its own seeded API instance and
ephemeral port), so raising it does not affect results, only rate limits. If
you hit one, failed runs are recorded and `--resume` picks them up.

**⚠ AMENDED 2026-08-08: the default was 8 and is now 16, and you should
probably go higher.** `matrix-40` ran 7,802 cells at 8 and recorded **zero
retries** — not one 429 in 41.6 hours of summed provider time, meaning the
account's ceiling was never approached and the run took roughly twice as long
as it needed to. The honest limit is unknown, because nothing has yet found it.
Step up rather than guessing: run at 24–32 and watch the `retries` column in
the ledger. A handful of retries is the signal you have found the edge and
should stay there; zero means there is still headroom. The measurement is cheap
to take and it is the single largest speed lever in the harness — everything
local is noise beside it (rig setup is 6 ms against a ~19 s run).

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
| `--model` | `gpt-5.6-luna` | Must be in the pricing table or have `HARNESS_PRICE_<MODEL>` set |
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
