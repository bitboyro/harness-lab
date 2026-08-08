# Experiment design

**Status:** Contract. Code cites this file by anchor.

What the study asks, what the test API must provide, what is measured, and the
validity controls that make the answers mean anything. The reasoning behind each
choice is in [decisions.md](./decisions.md); this file is the requirement.

---

## Research questions

1. **RQ1** — What does a skill layer contribute over a bare tool surface?
2. **RQ2** — How does topology (per-operation vs. discovery/dispatch) interact
   with surface size?
3. **RQ3** — Which packaging produces the least *harm* when several routes reach
   the same state change?
4. **RQ4** — Does arm ranking reverse between read and write tasks?

**Non-goals.** Ranking models, ranking MCP servers, or claiming a universal
best packaging. The model is held constant inside any controlled comparison;
results are stamped to it.

---

## Arms

Arms are **presets of an orthogonal axis space**, never the primitive. The axis
list and the full preset table are in
[packaging-axes.md](./packaging-axes.md#presets).

| Group | What it is |
|---|---|
| A | MCP, no skill — `A1` eager-all, `A2` meta-tools |
| B | MCP + generated skill; `-auth` twins use the authored skill |
| C | Docs + `curl` in a shell — `C1` flat reference, `C2` progressive |
| D | Code-execution sandbox over a generated module tree |
| E | Top-k tool retrieval |
| M | MRTR confirmation before destructive operations |
| Z | Controls — see below |

<a id="contamination-gate"></a>
## The contamination gate (Z0)

| Control | Definition | Gate |
|---|---|---|
| `Z0` | No tool access; parametric answer only | **Must score ≈0 in controlled mode.** If not, the testbed is contaminated and every result is void. Run first. |
| `Z1` | Gold call sequence pre-executed; the model only synthesises | Establishes the achievable ceiling per task |

**In field mode Z0 is not a gate but a measurement** — how much the model
already knows about the target API without being told anything. Field results
are reported as lift over that baseline, with Z0 published alongside
([G9](./decisions.md#g9--z0z1-in-field-mode-as-a-parametric-baseline)).

<a id="task-design"></a>
## Task construction — matched pairs

Tasks are a **navigation core** plus a **swappable terminal**, so task class is
never confounded with difficulty.

```
core:      locate object satisfying predicate P
           at nesting depth D, reachable in H hops,
           with ambiguity level A

terminals: R       → report field F
           W-safe  → PATCH field F to V            (harm tier 1)
           W-lossy → PUT full object               (harm tier 2)
           W-irrev → :archive                      (harm tier 3)
           RW-fan  → apply to all N matches        (harm tier 4)
```

One core yields five instances matched on every difficulty dimension, so the
difference between them is attributable to the terminal alone.

**Stratification.** Every metric is reported sliced by hop depth (1–4), nesting
depth (1–3), fan-out width (1/5/20/50), surface size (5/15/50/200) and task
class. Grand means are expected to mislead; rankings are predicted to reverse
across strata.

<a id="the-test-api"></a>
## What the test API must provide

**Contamination requirement (hard).** The domain must be invented but
plausible — coherent fictional entities with well-formed generated names, not
gibberish tokens, which add unrelated performance noise. The default theme is a
**media catalog** (studio → series → season → episode → asset): natural
fan-out, a natural irreversible operation (`:archive`), and vocabulary far from
compliance. Verification is the Z0 gate above.

| # | Requirement |
|---|---|
| API-1 | Operation count parametrically generated (5–200) |
| API-2 | Nested objects to depth ≥3 |
| API-3 | Sub-objects sometimes embedded, sometimes bare IDs requiring a further call |
| API-4 | `?expand=` and sparse-fieldset parameters |
| API-5 | Configurable response payload size. **Now a manipulated variable**: `response_shape` |
| API-6 | Pagination on collections |
| API-7 | Deliberate near-collisions in operation and parameter names |
| API-8 | Error surface 400/404/422/429 and partial failures. **Now a manipulated variable**: `error_detail` |
| API-9 | Idempotency keys, so "intended one write" differs from "wrote twice" |
| API-10 | Optional dry-run per mutating endpoint |

**Four routes to the same state change** — the core tool-surface stress test:

| Route | Semantics | Harm if misused |
|---|---|---|
| `PATCH /objects/{id}` | Partial update | Recoverable |
| `PUT /objects/{id}` | Full replace | **Silently drops unspecified fields** |
| `POST /objects/{id}/attributes` | Sub-collection append | Duplicate entries |
| `POST /objects/{id}:archive` | Action endpoint | Irreversible |

Per-operation MCP must either expose all four (bloat) or pick one (capability
loss); discovery arms must rank them; shell arms must read docs and choose. A
fifth option now exists — a server that *asks* before archiving, carried as the
`confirmation: mrtr` axis.

**State isolation (hard).** Fresh seeded state per run, via instance-per-run:
one in-memory API per run, seeded by parameter, torn down after
([G10](./decisions.md#g10--instance-per-run-isolation)). Because nothing is
shared, mutating tasks parallelise too.

<a id="grading"></a>
## Answer keys and grading

The task generator emits, from the same seeded source of truth as the API:

```
(task_id, core_id, terminal, question, gold_answer,
 gold_call_sequence, min_hops, expected_end_state, harm_tier)
```

Four rules, none negotiable:

- **Programmatic grading only.** No LLM judge for correctness.
- **Unguessable answers** — random IDs or arbitrary values, never inferable
  from the question.
- **~15% unanswerable tasks**, so false-positive answering is measurable.
- **Writes graded on final server state**, never on the transcript. An agent
  that reports success without acting must score as a failure.

The grader is blind to arm identity by construction — it is not passed one.

<a id="metrics"></a>
## Metrics

**Primary:** success rate (pass@1 against gold answer or expected end state),
cost per success in USD, turns, wall clock.

**Mechanism:** static context tokens, peak context, selection accuracy
(chance-corrected), argument validity, hallucinated endpoints, redundant calls,
wasted calls, payload efficiency, discovery overhead.

<a id="safety"></a>
**Safety and robustness:** silent-failure rate (confident wrong answers ÷ all
wrong), false-positive answering, claimed-success-state-unchanged,
destructive-write rate, **harm per 100 tasks** (weighted by harm tier), route
consistency, read-after-write verification, retry safety, variance across
repeats.

**Derived from matched pairs:** write penalty (`success(R) − success(W)` for the
same core), navigation/action split, route quality given the target was found.

<a id="analysis"></a>
## Analysis

Ranking, contrasts, MDE and the pooling rules are specified in
[statistics.md](./statistics.md). One analysis object (`Report`) is built from
the ledger and every renderer consumes it — renderers never recompute, or the
text and the HTML would drift.

<a id="cost"></a>
## Cost reporting

- **Three cache conditions**, not two: `off`, `on` (prompt caching —
  disproportionately favours large-static-prefix arms), and `list-cacheable`
  (protocol-level `ttlMs`/`cacheScope` on `tools/list`, which moves *static
  context* specifically and so flatters `eager-all`).
- **Tokens per success is not comparable across providers** — different
  tokenizers. Dollars per success is. Log both, compare only the latter.
- **Cost is reported decomposed, never as one number**: `static_tokens`,
  `per_call_overhead_tokens`, `session_setup_tokens`, `payload_tokens`,
  `sandbox_seconds`, `round_trips`. A total hides the mechanism the study is
  about — see [packaging-axes.md](./packaging-axes.md#cost-breakdown).
- **Never pool** across `mcp_spec_revision`, report class, or skill condition.
  The report layer enforces this.
- **Every metric prints its `validation` flag.**

<a id="the-agent-loop"></a>
## The agent loop

The harness owns the agent loop and **never delegates to a vendor agent
framework** — that would inject an uncontrolled harness into the thing being
measured.

```
OpenAPI spec (single source of truth)
        ├── generator → MCP tool definitions (per-operation)
        ├── generator → MCP meta-tools (discovery)
        ├── generator → skill markdown (flat / progressive)
        └── generator → curl reference
   canonical internal tool representation
   provider adapter ──► OpenAI (first) ──► others
   agent loop (owned by the harness)
   sandbox (shell+curl for C arms; code execution for D arms)
   test API, one seeded in-memory instance per run
   trace + state diff → grader → metrics
```

<a id="providers"></a>
## Provider adapters

Providers are adapters, never core. The engine may not import a vendor SDK; a
test enforces it. Each adapter implements:

- `submit(messages, tools, config) → response`
- `parse_tool_calls(response) → [call]`
- `usage(response) → {input, cached_input, output, reasoning}`
- `capabilities() → {supports_mcp, supports_parallel_calls, native_reasoning}`

`reasoning_effort` is always sent explicitly. An unset provider default would
silently benchmark effort levels instead of packaging (V3).

<a id="what-is-persisted"></a>
## What is persisted

Full trajectories, because metrics not yet conceived will need recomputation and
summary statistics cannot be reversed. Per run: every message, every tool call
with its arguments, server-side request logs with timestamps, initial and final
state, usage counters, and the config snapshot.

**`results.jsonl`** is append-only, one row per run, written under a lock — a
matrix that dies leaves what it finished. Re-running a voided cell appends a new
row; readers take the newest per `(arm, task, repeat)`.

**`manifest.json`** is the run-level config snapshot, written before the first
cell. Fields are additive; older ledgers may omit later ones.

| Group | Fields |
|---|---|
| identity | `id`, `created_at`, `harness_version` |
| scope | `presets`, `planned`, `resumed` |
| model side (pooling boundaries) | `model`, `provider`, `reasoning_effort`, `temperature`, `caching`, `report_class` |
| the world | `seed`, `cores`, `fan_out`, `difficulty`, `pack_digest`, `classes`, `max_tasks`, `tasks` |
| surface | `mcp_revision`, `surface_size`, `schema_detail`, `response_shape`, `error_detail`, `doc_budget`, `sweep_error_detail` |
| budget | `repeats`, `max_turns`, `concurrency` |

`pack_digest` is the content address `harness compare` reads to decide whether
two runs may be paired within core
([G12](./decisions.md#g12--core-ids-are-positional-cross-run-pairing-needs-a-world-key)).

<a id="validity-controls"></a>
## Validity controls

| # | Control |
|---|---|
| V1 | All arm materials mechanically generated from one spec, except the deliberately-exempt authored skill |
| V2′ | **Replaces V2.** Static context reported as a measured covariate plus an explicit doc-budget sweep. Causal claims come from the interaction, not forced parity — [G5](./decisions.md#g5--drop-v2-equal-documentation-token-budget) |
| V3 | `reasoning_effort` always explicit |
| V4 | Predictions pre-registered before the first full run |
| V8 | Effect sizes are model-bound and reported as such |
| V9 | Two skill conditions, reported separately, never pooled. The authored skill is committed **before any results are seen**; that commit is the pre-registration — [G6](./decisions.md#g6--two-skill-conditions) |
| V10 | `mcp_spec_revision` recorded per run; never pooled across |
| V11 | Every metric carries a `validation` flag; every lint rule carries `justified_by`. An unjustified rule renders `heuristic`, not `measured` |

<a id="deliverables"></a>
## Deliverables

The engine and the static lint; the controlled rig and its answer keys; the
ledger and trace corpus; and the report — text, HTML and charts — built from one
analysis object, carrying its own glossary, its pooling refusals, and the
validation flag of every metric it prints.
