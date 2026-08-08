# Tool Harness Benchmark — Requirements & Specification

**Working title:** MCP vs. Skill vs. Bash: A Controlled Comparison
**Status:** Draft v0.1 — pre-implementation, **amended 2026-08-05**
**Date:** 2026-07-30

> **Amendment note (2026-08-05).** This document remains the research-requirements source. Several sections were superseded by [`decisions.md`](./decisions.md) after review; each is marked inline with **⚠ AMENDED**. The design that implements these requirements is [`plan.md`](./plan.md) v2. §11's open decisions D1–D6 are all resolved.
>
> Changed here: §2 (verification status), §4.1 (domain), §4.4 (isolation), §5.6 (cacheable lists), §7 (budget gating), §8 (V2 dropped), §11 (resolved).

---

## 1. Purpose

Measure how the *packaging* of a REST API affects an LLM agent's ability to use it, holding the API, the task set, and the model constant.

Three things vary:

- **Access path** — MCP server alone, MCP + skill, skill + bash/curl
- **Tool topology** — one tool per operation vs. a discovery/dispatch mechanism
- **Task class** — read-only vs. state-mutating

### Research questions

| # | Question | Type |
|---|---|---|
| RQ1 | What does adding a skill layer contribute on top of an identical MCP surface? | True ablation (nested) |
| RQ2 | How does per-operation tool exposure compare to discovery/dispatch as surface size grows? | Comparison |
| RQ3 | Does a typed tool surface reduce harm on irreversible operations relative to freehand curl? | Comparison |
| RQ4 | Do arm rankings differ between read-only and mutating tasks? | Interaction |
| RQ5 | Do findings transfer across model providers? | Replication |

RQ3 and RQ4 are the differentiated contributions — existing literature covers efficiency but not error cost asymmetry.

### Non-goals

- Not a model capability benchmark. Model is a controlled variable, not the object of study. **⚠ Refined:** fixed *within* a controlled comparison, but a first-class axis in field mode — "your API needs a skill for cheap models but not frontier ones" is a supported finding.
- Not tested against production data (see §4 on contamination).
- Not a security/sandbox-escape study.
- **⚠ ADDED — not human-in-the-loop.** MCP Apps and UI resources are out of scope.
- **⚠ ADDED — not multi-agent.** Delegation and orchestration are out of scope; retrieval metrics are borrowed from 2511.01854, its multi-agent framing is not.

---

## 2. Prior art to position against

**⚠ AMENDED** — verification status added. Full table with dates: [`decisions.md`](./decisions.md#prior-art--verification-status). Standing rule: no external claim enters a published document without a dated verification row.

| Work | Status | Relevance |
|---|---|---|
| Anthropic, *Code execution with MCP* | ✅ | The token-savings claim this benchmark tests on a controlled API. Uses TypeScript — see the runtime-comparability caveat in [F4](./decisions.md#f4--code-fs-sandbox-is-python) |
| [*From Tool Orchestration to Code Execution*](https://arxiv.org/abs/2602.15945) (arXiv 2602.15945) | ✅ | Closest published comparison; formalizes context-coupled vs. context-decoupled (CE-MCP) on MCP-Bench. **Occupies the code-execution ground** — our contribution moves to error/response affordances and harm asymmetry |
| [*How Many Tools Should an LLM Agent See?*](https://arxiv.org/abs/2605.24660) (arXiv 2605.24660) | ✅ | Source of chance-corrected Bits-over-Random — adopt for RQ2 |
| [*Tool-to-Agent Retrieval*](https://arxiv.org/abs/2511.01854) (arXiv 2511.01854) | ✅ | Recall@k / nDCG@k for the retrieval discovery mode. **Caveat:** its setting is multi-agent routing, which our non-goals exclude — borrow the metrics, not the framing |
| [MCP-Bench](https://arxiv.org/abs/2508.20453) (arXiv 2508.20453) | ✅ | Structural template for task design; also the substrate 2602.15945 evaluates on |
| MCP spec discussion #1780 | ⬜ Unverified | The output-schema-brittleness objection to code-execution mode; unquantified, addressable here. **Verify before citing** |

**⚠ Substrate note.** The [2026-07-28 MCP revision](https://blog.modelcontextprotocol.io/posts/2026-07-28/) deprecates Sampling, Roots, and Logging, and retires sessions in favour of stateless request/response with `_meta` per request. Prior work built on those primitives now sits on a deprecated substrate — worth a sentence when positioning against it, and a reason not to build variants on them. It also weakens one standing argument for MCP over plain HTTP: if MCP is now request/response with per-request identity, the C arms are closer to MCP-minus-schemas than they were, which **sharpens** RQ3 rather than weakening it.

---

## 3. Experimental design

### 3.1 Arms

| ID | Access path | Topology | Model sees |
|---|---|---|---|
| A1 | MCP only | per-operation | All tool schemas loaded upfront |
| A2 | MCP only | discovery/dispatch | 2–3 meta-tools (search / describe / invoke) |
| B1 | MCP + skill | per-operation | A1 + skill with workflows and recipes |
| B2 | MCP + skill | discovery/dispatch | A2 + same skill |
| C1 | Skill + bash | flat docs | curl + full API reference inline |
| C2 | Skill + bash | progressive docs | curl + index file, details on demand |

**⚠ AMENDED — arms are no longer the primitive.** These six are *presets* of an orthogonal axis space, and four more exist: **D1/D2/D3** (code execution), **E1** (retrieval), **M1** (MRTR confirmation), plus `-auth` twins of the skill arms. The full axis list and preset table live in [`packaging-method.md`](./packaging-method.md).

Two of these changes matter for reading the rest of this document:

- **Code execution was missing entirely.** Its absence would have dated the benchmark on arrival. Its presence does not differentiate us either — 2602.15945 got there first — so the contribution moves to the affordance sweep (API-5/API-8, now manipulated) and to RQ3/RQ4.
- **The C arms are `invocation: shell`, not "code".** Freehand curl against written docs is a different mechanism from writing code against a generated module tree, and conflating them would have merged the C and D arms.

### 3.2 Controls

| ID | Definition | Gate |
|---|---|---|
| Z0 | No tool access; parametric answer only | **Must score ≈0.** If not, testbed is contaminated and all results void. Run first. |
| Z1 | Gold call sequence pre-executed; model only synthesizes | Establishes achievable ceiling per task |

### 3.3 Task construction — matched pairs

Tasks are generated as a **navigation core** plus a **swappable terminal operation**, so task class is never confounded with difficulty.

```
core:      locate object satisfying predicate P
           at nesting depth D, reachable in H hops,
           with ambiguity level A

terminals: R      → report field F
           W-safe → PATCH field F to V           (tier 1)
           W-lossy→ PUT full object               (tier 2)
           W-irrev→ :archive                      (tier 3)
           RW-fan → apply to all N matches        (tier 4)
```

One core yields five instances matched on every difficulty dimension. Difference between them is attributable to the terminal alone.

### 3.4 Stratification axes

Every metric is reported sliced by:

- Hop depth: 1 / 2 / 3 / 4
- Nesting depth: 1 / 2 / 3
- Fan-out width: 1 / 5 / 20 / 50
- Surface size: 5 / 15 / 50 / 200 exposed operations
- Task class: R / W-safe / W-lossy / W-irrev / RW-fan

Grand means are expected to be misleading; arm rankings are predicted to reverse across strata.

### 3.5 Pre-registered predictions

Record before first full run. Written down so the rig can be audited against motivated reasoning.

| # | Prediction |
|---|---|
| P1 | C arms win cost-per-success on read-heavy, high-fan-out tasks |
| P2 | C arms show the highest destructive-write rate (tier 2–4) |
| P3 | A1/B1 selection accuracy degrades sharply above ~15 operations |
| P4 | Skill layer (RQ1) helps most on multi-hop and mutation-route selection, least on single lookups |
| P5 | Arm ranking differs between R and W classes — the headline result if confirmed |
| **P6** | **⚠ NEW.** `error_detail: field-scoped+remedy` with no skill beats `error_detail: terse` plus a skill, on cost per success. *If confirmed, this is the most actionable result in the study: fixing error messages is cheaper than shipping a skill.* |
| **P7** | **⚠ NEW.** Moving from `legacy` to `2026-07-28` raises cost per success for `eager-all` + `tool-call` arms (per-call `_meta` tax) and lowers it for `code-fs` + `code` arms (calls batched inside the sandbox) |
| **P8** | **⚠ NEW.** `confirmation: mrtr` (M1) reduces harm per 100 tasks on tier-3 terminals relative to A1, at a cost in turns — i.e. asking beats typing, for irreversible operations |
| **P9** | **⚠ NEW.** `skill-authored` beats `skill-generated` by a margin large enough that a null RQ1 result under generated-only would have been an artifact of skill quality |

Predictions P6–P9 are recorded here **before** any run, per V4. Disconfirmed predictions are reported.

---

## 4. Test API requirements

### 4.1 Contamination requirement (hard)

The domain must be **invented but plausible**. Coherent fictional entities with well-formed generated names — not gibberish tokens, which introduce unrelated performance noise.

~~Recommended shape: a fictional standards/registry domain with documents → sections → nodes → dimensions → cross-references.~~ **⚠ AMENDED — superseded by `plan.md` L3/L4.** The registry mirror is *not* used. The resolution is **structural realism with thematic distance**: keep the structural properties §4.2 requires (nesting, pagination, CRUD verbs, error surface, bare-ID references) but move the vocabulary far from compliance, so generality is arguable rather than assumed.

Default theme: **media catalog** — studio → series → season → episode → asset. Natural fan-out ("tag every episode in a season"), natural irreversible operation (`:archive`), no compliance vocabulary. A **fleet** theme follows as a domain-robustness check; if arm ranking flips across themes, the first matrix is a domain artifact.

**Verification:** Z0 must score ≈0. This is the gate on the entire experiment.

**⚠ In field mode Z0 is not a gate but a measurement** — how much the model already knows about the target API parametrically. Field results are reported as lift over that baseline, with Z0 published alongside ([G9](./decisions.md#g9--z0z1-in-field-mode-as-a-parametric-baseline)).

### 4.2 Structural requirements

| # | Requirement |
|---|---|
| API-1 | Endpoint count parametrically generated from a template (support 5–200 operations) |
| API-2 | Nested objects to depth ≥3 |
| API-3 | Sub-objects sometimes **embedded**, sometimes returned as **bare IDs requiring a further call** |
| API-4 | `?expand=` and sparse-fieldset params |
| API-5 | Configurable response payload size (small → large), to expose context-pollution effects. **⚠ AMENDED — now a manipulated variable**, not just a property: `response_shape: as-is \| sparse \| budgeted` |
| API-6 | Pagination on collection endpoints |
| API-7 | Deliberate near-collisions: confusable endpoint and parameter names, configurable rate |
| API-8 | Error surface: 400/404/422/429, partial failures. **⚠ AMENDED — now a manipulated variable**: `error_detail: terse \| field-scoped \| field-scoped+remedy` |
| API-9 | Idempotency-key support, so "intended one write" is distinguishable from "wrote twice" |
| API-10 | Optional dry-run mode per mutating endpoint |

### 4.3 Multiple mutation routes (required)

The same state change must be reachable four ways:

| Route | Semantics | Harm if misused |
|---|---|---|
| `PATCH /objects/{id}` | Partial update | Recoverable |
| `PUT /objects/{id}` | Full replace | **Silently drops unspecified fields** |
| `POST /objects/{id}/attributes` | Sub-collection append | Duplicate entries |
| `POST /objects/{id}:archive` | Action endpoint | Irreversible |

This is the core tool-surface stress test: per-operation MCP must either expose all four (bloat) or pick one (capability loss); discovery arms must rank them; bash must read docs and choose.

**⚠ ADDED — a fifth option now exists.** The 2026-07-28 MRTR mechanism lets a server *ask before archiving* (`resultType: "input_required"` → `inputResponses`). That is a packaging choice the API owner controls, and it may beat a typed tool surface at harm reduction at some cost in turns and latency. Carried as the `confirmation: none | mrtr` axis and preset M1. Directly on RQ3.

### 4.4 State isolation (hard requirement)

Mutating tasks contaminate each other. Required: **fresh seeded state per task per repeat**.

**⚠ AMENDED — mechanism and consequence both changed.** The mechanism is **instance-per-run: one in-memory API process per run, seeded by parameter, torn down after** (`plan.md` L1). Not snapshot/restore, and not a global re-seed.

~~Consequence: read-only tasks parallelize; mutating tasks serialize.~~ With instance-per-run there is no shared mutable state, so **mutating tasks parallelize too**. Process spawn is milliseconds and isolation is total. The original serialization was a consequence of the global-reseed design, not of the isolation requirement.

Still true: design it in from the first commit — discovering it late invalidates completed runs.

### 4.5 Answer key generation

The API is backed by a seeded generated dataset. The task generator emits, from the same source of truth:

```
(task_id, core_id, terminal, question,
 gold_answer, gold_call_sequence, min_hops,
 expected_end_state, harm_tier)
```

Requirements:

- **Programmatic grading only** — no LLM judge for correctness
- **Unguessable answers** — random IDs / arbitrary values, never inferable from the question
- **~15% unanswerable tasks** — no valid answer exists, to measure false-positive answering
- **Writes graded on final server state**, never on the transcript

---

## 5. Metrics

### 5.1 Primary

| Metric | Definition | Source |
|---|---|---|
| Success rate | pass@1 vs. gold answer / expected end state | Runner |
| Cost per success | (tokens × price) ÷ successes, USD | Provider usage |
| Turns | Model↔tool round trips | Runner |
| Wall clock | Seconds, end to end | Runner |

### 5.2 Mechanism

| Metric | Definition | Source |
|---|---|---|
| Static context | Tokens of tool defs + skill before turn 1 | Token count |
| Peak context | Max window occupancy | Runner |
| Selection accuracy | vs. gold operation, chance-corrected (BoR) | Runner |
| Argument validity | 1 − (400/422 rate) | Server logs |
| Hallucinated endpoints | 404s on non-existent paths | Server logs |
| Redundant calls | Identical request repeated | Server logs |
| Wasted calls | Response never used in final answer | Logs + trace |
| Payload efficiency | Bytes used ÷ bytes returned | Logs + trace |
| Discovery overhead | Calls before first productive call | Server logs |

### 5.3 Safety / robustness

| Metric | Definition | Source |
|---|---|---|
| Silent failure rate | Confident wrong answers ÷ all wrong | Grader |
| False-positive answering | Answered an unanswerable task | Grader |
| Claimed success, state unchanged | Reported done, DB unchanged | State diff |
| Destructive-write rate | Fields clobbered that should have survived | State diff |
| **Harm per 100 tasks** | Destructive writes weighted by harm tier | State diff |
| Route consistency | Same intent → same route chosen | Server logs |
| Read-after-write verification | Did it confirm the mutation landed? | Server logs |
| Retry safety | Duplicate writes on retry | Idempotency keys |
| Variance | SD of success rate across ≥3 repeats | Runner |

### 5.4 Derived (from matched pairs)

| Metric | Definition |
|---|---|
| Write penalty | success(R) − success(W) for the same core, per arm |
| Nav/action split | Correct GET preceded incorrect write? Separates retrieval failure from action failure |
| Route quality \| found | Correct route, conditional on locating the target |

### 5.5 Engineering cost (qualitative)

Lines/tokens of spec to maintain per arm; time to add an endpoint; breakage under schema change.

### 5.6 Reporting rules

- Report cost per success across **three** cache conditions, not two — **⚠ AMENDED**. Prompt caching and protocol-level list caching are different mechanisms that move different costs:
  - `off` — no caching
  - `on` — prompt caching; disproportionately favours large-static-prefix arms and would flatter A1/B1
  - `list-cacheable` — the 2026-07-28 `ttlMs` / `cacheScope` on `tools/list`. This moves **static context** cost specifically, and so specifically flatters `eager-all`
- **Tokens-per-success is not comparable across providers** (differing tokenizers). Dollars-per-success is. Log both, compare only the latter.
- Grader blind to arm identity
- **⚠ ADDED — cost is reported decomposed, never as a single number**: `static_tokens`, `per_call_overhead_tokens` (the stateless `_meta` tax, scales with call count), `session_setup_tokens` (legacy handshake, paid once), `payload_tokens`, `sandbox_seconds`, `round_trips` (including MRTR retries and Tasks polls). A total hides the mechanism the study is about
- **⚠ ADDED — never pool** across `mcp_spec_revision`, across report class (controlled vs. field), or across skill condition (generated vs. authored). The report layer enforces this
- **⚠ ADDED — every metric prints its `validation` flag** (`validated-controlled` / `unvalidated` / `heuristic`). Field reports ship before the rig validates the gold-free metrics; that is acceptable only because it is stated on the artifact

---

## 6. Harness architecture

### 6.1 Provider abstraction

Provider is configurable; **OpenAI first**. Because the benchmark must run identically across providers, the harness owns the agent loop — it cannot delegate to any vendor-specific agent framework, since that would inject an uncontrolled harness.

```
OpenAPI spec (single source of truth)
        │
        ├── generator → MCP tool definitions (per-op)
        ├── generator → MCP meta-tools (discovery)
        ├── generator → skill markdown (flat)
        ├── generator → skill markdown (progressive)
        └── generator → curl reference
        │
   canonical internal tool representation
        │
   provider adapter  ──► OpenAI  (first)
                     ──► Anthropic
                     ──► (others)
        │
   agent loop (owned by harness)
        │
   sandbox (shell+curl for C arms; code execution for D arms)
        │
   test API, one seeded in-memory instance per run
        │
   trace log + state diff → grader → metrics
```

### 6.2 Adapter interface

Each adapter implements:

- `submit(messages, tools, config) → response`
- `parse_tool_calls(response) → [call]`
- `usage(response) → {input, cached_input, output, reasoning}`
- `capabilities() → {supports_mcp, supports_parallel_calls, native_reasoning}`

### 6.3 Configuration surface

| Key | Values |
|---|---|
| `provider` | `openai` \| `anthropic` \| … |
| `model` | provider model ID |
| `reasoning_effort` | explicit, never defaulted (see §8) |
| `temperature` | fixed, logged |
| ~~`arm`~~ | ~~A1 \| A2 \| B1 \| B2 \| C1 \| C2 \| Z0 \| Z1~~ **⚠ REPLACED** by the orthogonal variant axes — see [`packaging-method.md`](./packaging-method.md). A preset name is shorthand for a complete axis assignment, never a primitive |
| `surface_size` | 5 \| 15 \| 50 \| 200 \| custom |
| `max_turns` | cap, logged on hit |
| `caching` | **⚠ AMENDED:** `on` \| `off` \| `list-cacheable` — three conditions, see §5.6 |
| `repeats` | ≥3. **Note:** at fixed temperature this measures sampling noise only. Variance over task instances needs more cores, not more repeats |
| **`mcp_spec_revision`** | **⚠ NEW.** `2026-07-28` \| `legacy`. Recorded in every run snapshot; results never pooled across it |

### 6.4 Logging requirements

Full trajectories persisted — metrics not yet conceived will need recomputation, and summary stats cannot be reversed. Per run: all messages, all tool calls with params, all server-side request logs with timestamps, initial and final DB state, usage counters, config snapshot.

**Config snapshot = `manifest.json`**, written before the first cell runs.
Fields (additive; older ledgers may omit the later ones):

| Field | Purpose |
|---|---|
| `id`, `created_at`, `harness_version` | identity |
| `presets`, `planned`, `resumed` | what was asked for / already on disk |
| `model`, `provider`, `reasoning_effort`, `temperature`, `caching`, `report_class` | model side (pooling boundaries marked) |
| `seed`, `cores`, `fan_out`, `difficulty`, `pack_digest`, `classes`, `max_tasks`, `tasks` | the world — `pack_digest` is the content address used by `harness compare` to decide whether two runs may be paired within core |
| `mcp_revision`, `surface_size`, `schema_detail`, `response_shape`, `error_detail`, `doc_budget`, `sweep_error_detail` | surface |
| `repeats`, `max_turns`, `concurrency` | budget |

Per-row pooling fields (`model`, `mcp_spec_revision`, `skill_condition`,
`report_class`) remain on every ledger row; the manifest is the run-level
authoritative copy that `harness compare` reads first.

---

## 7. Run plan

### Phase 0 — Rig validation (~90 runs)

3 cores × 5 terminals × 6 arms × 1 repeat. Purpose: catch rig bugs, confirm Z0 ≈ 0, confirm terminals produce differentiated behaviour, confirm state isolation works. **Do not proceed until Z0 passes.**

### Phase 1 — Main matrix (~1,350 runs)

15 cores × 5 terminals × 6 arms × 3 repeats, single provider, single surface size.

### Phase 2 — Surface-size sweep

Arms A1/A2/B1/B2 across 4 surface sizes. Answers RQ2 and produces the scaling curve.

### Phase 3 — Provider replication (~250 runs)

Top 2 and bottom 1 arms only, second provider. Answers RQ5 cheaply. A ranking flip here is a more valuable finding than anything in Phase 1.

### Budget

At mid-tier rates (~$2.50/$15 per MTok, blended ~32k input / 2k output per run):

| Phase | Est. cost |
|---|---|
| Phase 0 | ~$7 |
| Phase 1 | ~$165 uncached, ~$85 cached |
| Phase 2 | ~$120 |
| Phase 3 | ~$25 |

**Batch discounts do not apply** — the agent loop needs each tool result before the next turn.

**Reasoning tokens are the cost risk.** High effort can push output from ~2k to ~20k per run, moving totals into the $300–500 range. Prices verified July 2026 and volatile; re-check before committing budget.

**⚠ AMENDED — the figures above are stale and the phasing changed.** Three things:

1. **Re-price before any run.** These were July-2026 prices, already flagged volatile.
2. **The sweeps roughly double Phase 1.** The error/response affordance sweep and the dual skill conditions were added after this was priced.
3. **No total budget is committed** (`plan.md` L12). Spend is gated per phase, and the run planner **prints projected cost and requires confirmation before executing any matrix**. The estimator models `reasoning_effort` explicitly, since it is the dominant variance source. `max_turns` and `reasoning_effort` are capped and logged on hit, so a runaway matrix fails loudly rather than expensively.

**Also changed: the phase order.** `plan.md` §8 puts the engine, static lint, and field mode *before* the controlled matrix. The run plan below still describes the controlled phases correctly; they now happen at P3–P4.

---

## 8. Validity controls

| # | Control |
|---|---|
| V1 | All arm materials generated mechanically from one OpenAPI spec — no handwritten docs. **Scope narrowed:** applies to the `skill-generated` condition. The `skill-authored` condition (V9) is deliberately exempt and reported separately |
| ~~V2~~ | ~~Equal documentation token budget across arms, generator-enforced~~ **⚠ DROPPED** — see below |
| V3 | Reasoning effort fixed explicitly on every provider. Defaults differ and drift; an unset default silently benchmarks effort levels instead of harnesses |
| V4 | Predictions pre-registered (§3.5) before the matrix |
| V5 | Grader blind to arm |
| V6 | Equal n per (core × terminal) cell |
| V7 | Identical hop/nesting/fan-out/ambiguity distributions across terminal classes. Enforced by the task-pack loader: tasks sharing a `core_id` with mismatched `difficulty` are a load error |
| V8 | Results timestamped to model version; harness effects are expected to shrink as models improve |
| **V2′** | **⚠ REPLACES V2.** Static context tokens reported as a **measured covariate**, plus an explicit doc-budget sweep (`terse` / `standard` / `verbose`) as its own axis. Causal claims come from the interaction, not from forced parity |
| **V9** | **⚠ NEW.** Two skill conditions — `skill-generated` and `skill-authored` — reported separately, never pooled. The authored skill is committed **before any results are seen**; that commit is the pre-registration |
| **V10** | **⚠ NEW.** `mcp_spec_revision` recorded in every run's config snapshot. Results are never pooled across revisions |
| **V11** | **⚠ NEW.** Every metric carries a `validation` flag; every lint rule carries `justified_by`. An unjustified rule renders as `heuristic`, not `measured` |

### Why V2 was dropped

Forcing MCP JSON schemas and markdown curl docs to the same token count requires padding one or truncating the other — which measures *artificially padded docs*, a worse confound than the one being removed.

More fundamentally: static context size is **not a nuisance variable here**. It is a real causal property of the packaging choice and half of why the arms differ at all. Equalizing it equalizes away the effect under study.

V1 is kept — mechanical generation from a single spec does the anti-favouritism work V2 was reaching for, without the padding.

This is a deliberate and arguable methodology change, recorded with its reasoning so a reader meets the argument rather than the omission. See [G5](./decisions.md#g5--drop-v2-equal-documentation-token-budget).

### Why V9 was added

RQ1 asks what a skill layer contributes. If skills are only ever generated mechanically from the spec, a null result means *"our generated skill was bad"*, not *"skills don't help"* — an unfalsifiable answer, and the one we would be obliged to publish. Real skills encode workflow knowledge absent from the OpenAPI spec, which is why they exist at all.

The gap between the two conditions is itself the finding: *skill quality is worth X points; mechanical generation captures Y% of it.*

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Domain leaks into pretraining | Z0 gate; generated names; no real-world entities |
| Cross-task state contamination | Per-task DB isolation (§4.4) |
| Unconscious favouritism in docs | V1, V2, V4 |
| API accidentally designed to favour one arm | Pre-registration; report disconfirmed predictions |
| Payloads too small to show context effects | API-5 configurable payload size |
| Findings don't transfer to real APIs | Mirror real API structure (§4.1); state the limitation |
| Results obsolete on model release | V8; the reusable testbed is the durable output |

---

## 10. Deliverables

1. Test API (OpenAPI spec + implementation + seeded generator)
2. Arm generators (**⚠ now: `PackagingMethod` plugins**, one per packaging method, from one spec)
3. Harness with provider adapters, OpenAI first
4. Task generator with answer keys
5. Grader + metrics pipeline
6. Trace corpus
7. Results report
8. Pre-registration record
9. **⚠ NEW — frozen [task-pack schema](./task-pack-schema.md)**, the interop contract that makes bring-your-own-API possible
10. **⚠ NEW — T1 static lint + agent-readiness scorecard**, with `rule → justifying run` traceability
11. **⚠ NEW — statistical analysis plan**, written with the rig and before any matrix run

The **testbed is the durable contribution** — results are stamped to a model version and will age within months; a contamination-free parametric harness benchmark is reusable and no good public one exists. Design for release.

**⚠ Sharpened.** The durable contribution is the *engine plus its contracts*, and the build order now reflects that: engine, lint, and field mode ship before the controlled matrix (`plan.md` §8). Two structural commitments protect it from aging out — packaging methods are **plugins**, not enum values, so a protocol change is a new file rather than an engine change; and the task-pack schema is **frozen before the engine**, so traces stay interpretable. The 2026-07-28 revision landing mid-design is the proof both were needed.

---

## 11. Open decisions — **all resolved 2026-08-05**

Reasoning for each: [`decisions.md`](./decisions.md#harness-benchmark-specmd-open-questions).

| # | Question | Resolution |
|---|---|---|
| D1 | Fictional domain — registry mirror or further away? | **Further.** Media catalog; structural realism with thematic distance. §4.1 amended |
| D2 | Discovery arm: native tool-search or hand-rolled triad? | **Hand-rolled triad primary** for cross-provider symmetry; native additionally as a separate *labelled* variant, so the delta answers "is our dispatcher the bottleneck" instead of leaving it as a caveat |
| D3 | Sandbox: container per run or shared? | **Subprocess per run** for controlled phases — in-memory API, no credentials, no egress, so containers buy nothing. **Container per run** for field mode against real targets |
| D4 | Second provider | **Anthropic** — but a cheap tier of the *same* provider comes first. Tier is worth more to the product than provider and costs less |
| D5 | Difficulty dimensions: fix vs. sweep | **Sweep** hop depth and fan-out; **fix** nesting at 3 and ambiguity at medium. Revisit after rig validation shows which dimensions move metrics |
| D6 | OSS release timing | **Engine + T1 lint early; controlled results held** until the matrix completes. Early release recruits task packs, which are the scarce resource; pre-registration protects the results |
