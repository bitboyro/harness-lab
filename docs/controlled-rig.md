# The controlled rig

The built-in experiment. A fictional media-catalog API is generated in process
from a seed, together with an answer key from the same source of truth — so
correctness and harm are gradeable here in a way they never are on a real API.

This is the mode that produces research claims. For your own API, see
[test-your-api-harness.md](./test-your-api-harness.md).

## The smoke run

```bash
harness run --out /tmp/smoke --id smoke --smoke --yes
```

~12 runs, about a minute, about $0.05. Proves the pipeline works. **It is not a
result** — three arms over two cores cannot resolve any contrast.

## The recommended matrix

40 cores, 3 repeats, every arm with a pre-registered contrast:

```bash
harness run \
  --out results/matrix-40 --id matrix-40 \
  --model gpt-5.6-luna --reasoning-effort low \
  --difficulty hard --cores 40 --fan-out 8 --surface-size 50 \
  --repeats 3 --max-turns 12 --concurrency 24 \
  --presets Z0 Z1 A1 A2 B1 B2 B1-auth B2-auth C1 D1 D2 D2-auth
```

**~8,500 runs, roughly 2 hours, roughly $100.** It prints a projection and waits
for confirmation.

Why those values:

- **`--cores 40`** — 40 distinct navigation problems. Cores, not repeats, buy
  statistical power; 40 is where the main-effect MDE reaches ~10 pp at 3
  repeats. Repeats at fixed temperature measure sampling noise only.
- **`--difficulty hard`** — at `standard` every arm scored ~100% and nothing
  separated. `hard` identifies targets by property rather than location, so the
  agent must search instead of walking a path it was handed.
- **`--surface-size 50`** — pads the 16 core operations with distractors. Tasks
  still only target the core, so this measures *selection* difficulty rather
  than task difficulty.
- **`--presets`** — includes the `-auth` arms, the only way RQ1 gets an answer.
  Excludes `D3 E1 M1`, which have no pre-registered contrast.

Wall-clock is a function of `--concurrency`, not of the matrix: about 45 hours of
summed provider latency divided by however many runs are in flight.

## Shaping the world

| Flag | Effect |
|---|---|
| `--cores` | Navigation problems; each yields up to 5 matched tasks |
| `--fan-out` | Episodes per season — the blast radius on `RW-fan` tasks |
| `--surface-size` | Pad the surface with distractor operations |
| `--difficulty` | `standard` or `hard` |
| `--seed` | The world. Same seed, same questions |
| `--classes` | Limit to task classes, e.g. `R W-safe` |
| `--max-tasks` | Cap the task set |

`harness rig --cores N` prints the power table for a size without running
anything. It writes files that `run` does not read — it is an inspection tool,
not a prerequisite.

## Watching a run

```bash
harness progress results/matrix-40           # from a second terminal
harness run … --stream --concurrency 1       # every message, live
harness transcript results/matrix-40/traces  # replay afterwards
```

## When it breaks

Infra failures are not results. A run killed by a dead key, a full disk or a
rate limit is graded `infra-error`, excluded from every rate, and **re-run by
`--resume` rather than skipped**.

- `disk`, `auth` and `billing` abort the whole matrix immediately, exit **40**.
  Nothing is scheduled after the first one — waiting for a second identical
  failure only doubles the waste.
- Transient kinds retry in place with capped, jittered backoff.
- Classification never reads response text — only errno, typed provider codes
  and transport status. A tool result saying "unauthorized" is the mock API
  doing its job.

```bash
harness run --out results/matrix-40 --id matrix-40 --resume
```

`--resume` re-runs voided cells and inherits every run-shaping flag from
`manifest.json`. It refuses if the rebuilt world does not match the one on disk
(exit 3) — finishing it would put two different worlds in one ledger.

The ledger is append-only, written per run under a lock, so a matrix that dies
leaves what it finished.

## Comparing runs

```bash
harness compare results/a results/b
```

Prints what differed in the setup and what it changed. It **exits 3 and refuses**
when a pooling boundary breaks — different models, MCP revisions, skill
conditions or report classes. That exit code is what makes
`harness compare a b && publish` safe.

Pairing within core needs a shared world key; otherwise it falls back to an
unpaired comparison, labelled and never called significant. Arms missing from
any run are reported standalone rather than as a blank delta cell.

## Declaring a matrix in advance

```bash
harness plan examples/plan.yaml            # cost projection
harness plan examples/plan.yaml --approve  # record the approval
harness plan examples/plan.yaml --strict   # require the pre-registered split
```

The point is the `confirmatory` block: contrasts fixed before results exist, so
none can be added after seeing them. See
[examples/plan.yaml](../examples/plan.yaml); `--strict` refuses a plan whose
confirmatory set does not match the one declared in code.

## Declaring your own arm

The sixteen shipped arms are a starting ladder, not the limit. A run plan may
add its own under `arms:`, merged over the builtins:

```yaml
arms:
  A1-mine:                              # A1, plus your own hand-written skill
    extends: A1
    instructions: skill-authored-flat
    materials: {skill: skills/my-api.md}

  A1-confirm:                           # A1, but the server asks before writes
    extends: A1
    confirmation: mrtr
```

`extends` copies the parent's axes and anything you name overrides it.
`materials` binds a file to a slot — `skill`, `docs`, `helpers` or `target`.
`matrix` sweeps one arm across several values, expanding into
`A1-mine@schema_detail=minimal` and siblings.

The loader refuses rather than guesses: an unknown key, an unknown parent and an
unknown material slot are each a load error naming what would have been valid.
Pinning an affordance or run axis needs `allow_run_axes: true`:

```
arm 'D2-terse' pins non-structural axis 'doc_budget'. Affordance/run axes
belong on the plan's base (or set allow_run_axes: true for a deliberate pin).
```

That refusal is the point. An arm that quietly pinned `model` or
`reasoning_effort` would benchmark those instead of packaging (V3), and the
results would look like a packaging finding. Requiring the flag makes the pin a
decision someone made on purpose.

A declared arm still resolves its packaging method through `packaging.resolve`,
so it can reach nothing a builtin cannot.

## Disk

Traces are ~900 KB each, so the recommended matrix is several GB. `run` refuses
to start if free space cannot cover the projected traces plus 5 GB of headroom —
on a small machine the OS grows its swap file on the same volume, so filling the
disk does not merely fail a write, it gets the matrix killed at 99%.
