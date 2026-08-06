# Testing your own API or MCP server

How to point the harness at something you own and find out which packaging your
consumers' agents actually do best with.

Three levels, cheapest first. Start at the top — most people never need the
bottom one.

| | Cost | Needs | Answers |
|---|---|---|---|
| **1. Lint** | free | a spec or a live MCP URL | "What is obviously wrong with my surface?" |
| **2. Probe** | ~$1–20 | the above, plus a model key | "Which packaging works best on my API?" |
| **3. Benchmark** | $50+ | the above, plus graded tasks | "By how much, and is it real?" |

---

## 1. Lint — free, no key, seconds

Static analysis of your surface. No model runs.

```bash
harness lint path/to/openapi.json
```

```
Catalog v1.0.0 — 16 operations

  [high]? unbounded-collection: search_episodes returns a collection with no
          pagination parameter. An unbounded response is the fastest way to
          fill an agent's context with data it did not ask for.
  [high]? ambiguous-mutation-route: /episodes/{id} is mutable via
          ['PATCH','POST','PUT']. PUT replaces the whole object and drops
          unspecified fields…

0 of 8 rules are backed by a measured effect size. Every finding below is
heuristic — treat it as a hypothesis, not a result.
```

**Read that footer.** The rules are reasoned, not yet measured. A finding is a
hypothesis about your API, not proof. The `?` marks heuristic; a `!` would mean
an effect size backs it.

The rules are MCP-aware: on an MCP-derived surface, checks that describe HTTP
conventions (error response blocks, verb ambiguity, idempotency keys) are
skipped rather than firing on every tool.

---

## 2. Probe — a few dollars

Runs a real model against your API through several packagings and compares
them.

### Step 1: describe your target

Create `packs/my-api.yaml`:

```yaml
schema_version: 1

pack:
  id: my-api-probe
  description: Read-only probe against our production search API.
  report_class: field          # never pooled with controlled results

api:
  # For a live MCP server — no OpenAPI needed, tools/list IS the surface:
  mcp:
    url: https://mcp.example.com/mcp
    spec_revision: auto        # asks the server which revision it speaks
  # For an HTTP API instead:
  # openapi: ./openapi.json
  base_url_env: MY_API_BASE_URL
  auth:
    type: bearer               # none | bearer | header | basic
    env: MY_API_TOKEN          # read from the environment, never inlined

safety:
  writes_enabled: false        # default. Mutating tasks are refused outright
  forbidden_calls:             # blocked, and every attempt recorded
    - "DELETE /*"
    - "POST /*:archive"

isolation:
  mode: none                   # read-only, so there is no state to reset

tasks:
  - id: find-owner
    prompt: "Who owns the oldest unpaid invoice for account ACME?"
    class: R
    answerable: true
    grade:
      - { type: contains, target: answer, value: "Nadia" }

  # ~15% of tasks should have NO valid answer. This is how you find out
  # whether the agent invents one — the failure that matters most.
  - id: no-such-account
    prompt: "What is the credit limit for account ZQ-9910?"
    class: R
    answerable: false
    unanswerable_because: "no such account exists"
```

Credentials live in `.env` and are read by name — nothing is ever written into
the pack.

### Step 2: run it

```bash
harness probe packs/my-api.yaml \
  --model gpt-5.6-luna \
  --presets Z0 A1 A2 C1 D1 \
  --repeats 1
```

It prints a cost projection and waits. For a live MCP target no `--spec` is
needed — the server's `tools/list` is the surface.

### Step 3: read it

```
Parametric baseline (Z0): 83% of tasks answered with no access to the API at all.

  arm         success    lift   turns  arg-valid   static
  Z0              83%     +0%       1        n/a        0
  A1              67%    -17%       3       100%    1,961
  A2              80%     -3%       5       100%      155
```

**The baseline is the point.** `Z0` runs your tasks with **no tools at all**. If
it scores high, the model already knows your domain from training and your
tools have to beat that to be worth having.

The example above is real: both packagings scored **below** the no-tools
baseline. Raw success would have read "A1 got 67%, not bad". Lift says the tools
made it worse.

If Z0 scores high on your API, that is not a bug — it is the most useful thing
the probe will tell you, and it means your task set needs questions whose
answers are *in your data* and *not* in public training data.

---

## 3. Benchmark — graded tasks, real numbers

Everything from level 2, plus enough tasks to say something defensible.

### Grading

| Type | Checks |
|---|---|
| `equals` | Exact match, whitespace and case normalised |
| `contains` | Substring |
| `regex` | Pattern |
| `jsonpath` | A field inside a JSON answer |
| `state-diff` | **Server state after the run** — for writes |
| `script` | Your own grader, receives the trace on stdin |

**Writes are graded on final state, never on the transcript.** An agent that
says "done" without acting must score as a failure, and the transcript cannot
tell you that.

```yaml
  - id: set-rating
    prompt: "Set the rating of invoice INV-88 to 'reviewed'. Change nothing else."
    class: W-safe
    grade:
      - { type: state-diff, target: state, path: "$.invoices.INV-88.rating",
          expect: "reviewed" }
      # Name a field the task never mentioned. An agent that used PUT instead
      # of PATCH silently wipes it, passes the first check, and fails this one.
      - { type: state-diff, target: state, path: "$.invoices.INV-88.amount",
          expect: 4200 }
```

That second assertion is the whole trick. Without it, a destructive write looks
like a success.

### Sizing

More *tasks* buy statistical power; more *repeats* of the same task do not.

```bash
harness rig --for-contrast main-effect --target-mde 15
```

As a rule of thumb: **under ~20 distinct tasks, expect every difference to be
within the noise.** The report says so explicitly rather than letting you read a
ranking that isn't there.

---

## Writing against a real system

**Reads are the default and writes are refused** unless you set
`safety.writes_enabled: true`. Even then, a production-looking hostname
requires **both** `safety.production_ack: true` in the pack **and**
`--i-know-this-is-production` on the command line. Two independent gates,
because one is a typo away from being wrong.

Regardless, keep `forbidden_calls` populated. On a real API you cannot diff
state, so a blocked attempt is the only harm signal you get — and it is
recorded even though it was blocked.

**Strong recommendation:** point level 3 at a staging copy. Levels 1 and 2 are
read-only and safe against production.

---

## What you get

```bash
harness report results/my-probe --html report.html --charts charts/
```

- **`results.jsonl`** — one row per run: outcome, tokens, timings, cost, the
  full axis assignment. Feed it to your own analysis, or `--csv`
- **`traces/`** — every message, call and response, per run
- **`report.html`** — self-contained page, no external requests, light and dark
- **`--glossary`** — every term explained in plain language

The report carries its own caveats: what was truncated, what is unvalidated,
which comparisons it refuses to pool, and the minimum difference this sample
size could detect.

---

## Honest limits

Read these before quoting a number.

- **Field metrics are unvalidated.** They describe what happened; their
  relationship to quality has not been established on the controlled rig. The
  report says so in every footer.
- **Contamination is measured, not removed.** `Z0` tells you how much the model
  already knew. It cannot subtract that from the model's reasoning.
- **A small task set cannot rank packagings.** It can find crashes, fabricated
  answers and cost differences — all worth knowing — but not a winner.
- **The lint rules are heuristics.** None yet points at a measured effect size,
  and the scorecard says so on every run.
- **Results are stamped to a model version.** These effects are expected to
  shrink as models improve. A result from one model is not a result about APIs
  in general.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `403` from an MCP server | Bot protection. The client sends a User-Agent; some WAFs need allowlisting |
| Connect hangs ~60s | Server on the legacy revision expecting a session handshake. `spec_revision: auto` handles it |
| `no price for model X` | Set `HARNESS_PRICE_X="in,cached,write,out"` in `.env`. It refuses to guess, because that number goes in front of a spend approval |
| An arm scores ~0% | Read its traces before believing it. A prompt bug can look exactly like a finding |
| Every difference marked "below MDE" | Too few tasks. Correct behaviour, not a fault |
