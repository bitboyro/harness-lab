# Testing your own API

Answers one question: **does the way you package your API change how well an
agent uses it, and which packaging is best?**

Three steps, increasing in cost. Stop at any of them.

| | Cost | What you learn |
|---|---|---|
| `lint` | $0 | Static agent-readiness findings. Hypotheses, not measurements |
| `run --probe` | ~$1–20 | Does an agent get anywhere at all, on a handful of tasks |
| `run` | $50+ | Which packaging wins, with intervals you can defend |

## 1. Lint — free

```bash
harness lint ./openapi.json
harness lint https://your-api/openapi.json
```

Findings are marked `?` for heuristic and `!` for measured. **Today every rule
is heuristic** — 0 of 8 have a measured effect size behind them, and the footer
says so on every run. Treat a finding as a hypothesis worth turning into a task,
not as a defect.

## 2. Draft a pack

A **task pack** describes your API and the tasks to run against it. Never write
one from scratch:

```bash
harness scaffold https://your-server/mcp --id your-api -o packs/your-api.yaml
harness scaffold ./openapi.json --id your-api -o packs/your-api.yaml
```

Scaffold derives the surface, writes one stub per read operation, puts every
operation it will *not* exercise into `forbidden_calls`, sets
`report_class: field` and `writes_enabled: false`, and adds ~15% unanswerable
slots.

**Nothing is graded.** Every task has a `TODO` prompt and an empty `grade`. That
is deliberate — a stub asserting something plausible would look finished. Filling
those in is the work, and it is the part that decides whether your numbers mean
anything.

What a good task looks like:

- **The answer lives in your system.** A question answerable from public
  knowledge measures pretraining, not packaging. Watch Z0 to find out.
- **The grade is deterministic** — `equals`, `contains`, `regex`, `jsonpath`, or
  a script. No grader, no result.
- **~15% have no answer at all**, with `unanswerable_because` filled in. Without
  these you cannot measure fabrication, which is half of what goes wrong.
- **Aim for ≥20 distinct cores** to rank arms; ~40 for contrasts you intend to
  publish. Power comes from more tasks, not more repeats of the same one.

Full field reference: [design-your-test-run.md](./design-your-test-run.md).

Your coding agent can do this with you — `harness init --agent claude|cursor|both`
installs skills that know the whole workflow.

## 3. Probe

```bash
export OPENAI_API_KEY=...
harness run --pack packs/your-api.yaml --probe \
    --out results/probe-1 --id probe-1
```

`--probe` means first contact: probe arms, one repeat, no resume. It prints a
cost projection and asks before spending.

**Always include Z0.** It is the arm with no tools at all, and on a real API it
measures how much the model already knows about you. Every other number is
reported as lift over it. A high Z0 is not a failure — it tells you your tasks
are answerable from public knowledge, and the fix is better tasks, not better
packaging.

To watch it happen:

```bash
harness run --pack packs/your-api.yaml --probe --stream --concurrency 1
```

`--stream` prints every message to and from the model, every tool call with its
arguments, and every result. Afterwards, `harness transcript results/probe-1/traces`
replays any run.

## 4. Read it

```bash
harness report results/probe-1
harness report results/probe-1 --html report.html --charts charts/
```

Then [reading-results.md](./reading-results.md), which covers what the numbers
mean and — more usefully — which ones you are not entitled to.

The report’s **operation ledger** names which endpoints agents over-touch and
stumble on (wrong-route / call-error / forbidden), rolled up by family with
packaging deltas. Without gold paths in the pack, excess and off-gold stay
marked unavailable — not zero. Details and interpretation guards live in
reading-results under “Operation ledger”.

## Safety

Writes are **off** by default and should stay off until you have a staging
target. `forbidden_calls` is the harm signal on a real API: state cannot be
diffed, so an *attempted* destructive call is the only evidence there is. The
harness blocks the call and records the attempt.

Anything touching production needs `production_ack: true` in the pack **and**
`--i-know-this-is-production` on the command line. Don't, for a first run.

## What you may and may not claim

- Results are **stamped to the model version** you ran. Not "APIs in general".
- Field metrics are **unvalidated** — their relationship to ground truth has not
  been established on the controlled rig. Every report says so.
- A lead smaller than the run's MDE is **a tie**, not a win.
- Controls (`Z0`, `Z1`) anchor the scale and are never shippable packaging.
- Never pool across models, MCP revisions, skill conditions, or report classes.
  `harness compare` exits 3 rather than print a comparison that crosses one.
