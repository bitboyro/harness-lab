# Harness Lab — Design Plan v2

**Status:** Agreed — open questions resolved, implementation not started
**Date:** 2026-08-05 (v1: 2026-08-03)
**Companions:** [`harness-benchmark-spec.md`](./harness-benchmark-spec.md) (research requirements) · [`decisions.md`](./decisions.md) (why each choice was made) · [`packaging-method.md`](./packaging-method.md) and [`task-pack-schema.md`](./task-pack-schema.md) (frozen contracts)

v1 proposed an architecture and left 20 questions open across three documents. [`plan-review.md`](./plan-review.md) raised ten issues against it. This version folds in the resolutions. **This document is the spec; [`decisions.md`](./decisions.md) is the reasoning.** Where they disagree, the reasoning is right and this file needs fixing.

Still no code. That gate is the user's to lift.

---

## 1. Goal

Build a **reusable tool** that measures how packaging a REST API — MCP, skill, docs+curl, code execution, with or without each — affects an LLM agent's ability to use it.

Two modes:

| Mode | Purpose | What it can score |
|---|---|---|
| **Field** | Point at any real API (or live MCP / real skill / real docs) and compare packaging variants | Mechanism, cost, safety-signal metrics |
| **Controlled** | Run the research experiment on a fictional, contamination-free API | Everything, including correctness and harm |

### The mock API is the centerpiece

**The fictional media-catalog API is the main subject of this project.** It is the artifact that makes every research claim possible, the only place harm and correctness can be measured properly, and the thing that gives the gold-free metrics their credibility everywhere else. Field mode is what makes that work *useful* to someone else; it is not what the work is about.

**Build order is not priority order.** Tool-first ([F1](./decisions.md#f1--tool-first-study-second)) says the engine, lint, and field mode ship before the controlled matrix — because the engine is the reusable substrate and shipping it early recruits task packs. It does not say the mock API matters less. v1 said the field tool was the product and then scheduled it last; v2 fixes the scheduling contradiction without demoting the rig.

Concretely, the mock API is where these live and nowhere else: the Z0 contamination gate, the four-route harm asymmetry probe, matched-pair write penalties, and the error/response affordance sweep that §5 identifies as the headline. Real APIs cannot host any of them — you cannot ask a production server to re-issue the same state change four ways with different blast radii.

### The honesty constraint this creates

Shipping field mode before the controlled rig means shipping metrics whose relationship to ground truth is unestablished. That is acceptable only because it is **stated on the artifact**:

- Every metric carries `validation: unvalidated | validated-controlled | heuristic`, printed in every report footer.
- Every lint rule carries `justified_by` — the runs establishing its effect size. Empty means the rule renders as "heuristic", not "measured".
- Both structures exist from P0, empty, and are back-filled when the rig lands.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  ENGINE  (API-agnostic core — the reusable tool)             │
│                                                              │
│  OpenAPI spec  ──► generate variant materials                │
│       OR  live MCP / real skill / real docs (bring-your-own) │
│       │                                                      │
│  PackagingMethod plugins  (materialize / executor / account) │
│       │                                                      │
│  provider adapter   (OpenAI first; tier axis; then others)   │
│       │                                                      │
│  agent loop  (owned by the harness — never a vendor SDK)     │
│       │                                                      │
│  executors: MCP tool-call · shell+curl · code sandbox        │
│       │                                                      │
│  traces + usage + request logs + cost breakdown              │
│       │                                                      │
│  GOLD-FREE METRICS  (work on any API, each validation-tagged)│
└──────────────────────────────────────────────────────────────┘
              │                              │
   ┌──────────┴──────────┐      ┌────────────┴─────────────────┐
   │  EXPERIMENT         │      │  FIELD / PRODUCT             │
   │  fictional API +    │      │  T1 lint (static, $0)        │
   │  seeder + answer    │      │  T2 probe (~$5–20)           │
   │  keys + grader      │      │  T3 benchmark ($100+)        │
   │  → CORRECTNESS/HARM │      │  → verdict + diff            │
   └─────────────────────┘      └──────────────────────────────┘
```

**Rule:** `engine` must not depend on `experiment`. The experiment is a consumer — and it consumes through the *same* task-pack interface a field user does, with no special-casing. If the rig needs an engine feature no field user could reach, that is a design bug.

---

## 3. Variants

The v1 descriptor could not express "MCP discovery with code execution + skill" because its axes conflated where materials come from with how a call is made, and code execution was absent entirely. v2 uses orthogonal axes.

**Full axis list, plugin interface, and preset table: [`packaging-method.md`](./packaging-method.md).** In outline:

```yaml
variant:
  transport:      mcp | http-rest | in-process | none
  mcp_revision:   2026-07-28 | legacy          # required iff transport: mcp
  discovery:      eager-all | meta-tools | code-fs | retrieval | docs | none
  invocation:     tool-call | shell | code     # three-way, not two
  instructions:   none | skill-{generated,authored}-{flat,progressive} | docs-{flat,progressive}
  confirmation:   none | mrtr
  schema_detail:  minimal | standard | rich
  response_shape: as-is | sparse | budgeted    # manipulated, not fixed
  error_detail:   terse | field-scoped | field-scoped+remedy
  doc_budget:     terse | standard | verbose   # swept, not equalized
  surface_size:   int
  model:          <provider model id>
  reasoning_effort: explicit, never defaulted
  temperature:    fixed, logged
  caching:        on | off | list-cacheable
  repeats:        int
```

Presets: A1/A2/B1/B2 (MCP ± skill × topology), C1/C2 (shell+curl), **D1/D2/D3** (code execution), **E1** (retrieval), **M1** (MRTR confirmation), Z0/Z1 (controls). B and D arms have `-auth` twins using the authored skill.

Three things worth calling out:

- **`invocation` splits three ways.** The review wrote the C arms as "code (bash)", conflating freehand curl against docs with writing code against a generated module tree. Different mechanisms, different arms.
- **Code execution is table stakes, not the headline.** [arXiv 2602.15945](https://arxiv.org/abs/2602.15945) already formalizes context-coupled vs. context-decoupled MCP and evaluates it on MCP-Bench. Omitting `code-fs` would date the benchmark on arrival; including it does not differentiate us. The headline moves to §5.
- **The combinatorial space is large, and that is the point.** The engine enumerates; the run plan selects a declared subset with a mandatory stated rationale. Validity comes from which cells are compared, not from restricting what the tool can express.

---

## 4. Output: three tiers

v1 defined what was measured but never what a user *receives*. And nobody with a real API funds 1,350 runs to learn their error messages are bad.

| Tier | Cost | Mechanism | Output |
|---|---|---|---|
| **T1 — Lint** | $0, seconds | Static analysis of OpenAPI spec / MCP `tools/list` | Agent-readiness scorecard: naming collisions, missing descriptions, unbounded list responses, no pagination defaults, untyped errors, >N ops with no discovery layer, verb-ambiguous mutation routes |
| **T2 — Probe** | ~$5–20 | ~30 runs, 3–4 variants, gold-free metrics | "Your API costs 3.1× more tokens per task under `eager-all` than `code-fs`. Argument validity is 61%; failures cluster on `filter[]`." |
| **T3 — Benchmark** | $100+ | Full matrix + task pack + grader | Research-grade; correctness and harm included |

T1 is the adoption wedge and the first shippable artifact. Its rules are largely the planned metrics run in reverse.

**Constraint:** every T1 rule must eventually point at a T2/T3 measurement establishing its effect size. A rule with a run behind it is a defensible moat; one without is opinion, and renders as `heuristic`.

---

## 5. Metrics

| Bucket | Needs gold? | Fictional API | Real API |
|---|---|---|---|
| Mechanism / cost / safety-signal | No | Yes | Yes |
| Correctness / harm | Yes | Yes (programmatic grader) | Only with a task pack, or via `forbidden_calls` |

### Gold-free

Static and peak context tokens · turns · wall clock · $/run and $/success · argument validity (1 − 400/422 rate) · hallucinated endpoints · redundant and wasted calls · discovery overhead · payload efficiency · route consistency.

### Gold / oracle

Success rate · silent-failure rate · false-positive answering · destructive-write rate · harm per 100 tasks · write penalty · nav-vs-action split.

### New in v2 — and this is the headline

Response and error design were treated by the spec as *properties the test API must have* (API-5, API-8) and never varied. That left the most actionable question an API owner has unanswered:

> **Is it cheaper to fix my error messages than to ship a skill?**

An agent receiving `422: validation failed` retries blindly. One receiving `422: field 'created_after' expects RFC3339, received '2024-13-01'` self-corrects in a turn. That is a one-line server change versus authoring and maintaining a skill, and the trade rate is unpublished.

So `response_shape` and `error_detail` become axes, with two metrics:

- **Error recovery rate** — fraction of 4xx responses followed by a corrected retry within 2 turns
- **Turns-to-first-productive-call**, split by whether an error preceded it

With code execution no longer differentiating, this plus RQ3/RQ4 (harm asymmetry; ranking reversal between read and write classes) is what the study contributes.

### Cost accounting decomposes

Not a single number — different packaging pays in different places, and both MCP revisions are supported:

`static_tokens` · `per_call_overhead_tokens` (the `_meta` tax, scales with call count) · `session_setup_tokens` (legacy handshake, paid once) · `payload_tokens` · `sandbox_seconds` · `round_trips` (including MRTR retries and Tasks polls).

Stateless MCP moves cost from setup to per-call, penalizing chatty arms and favouring sandbox-batched ones. A totalled cost hides that; a decomposed one hands it to you.

### Report classes — never mixed

- **Controlled** — research-grade; Z0 must pass; contamination-free.
- **Field** — practical; reported as **lift over the parametric baseline**, with Z0 published alongside.

Z0 in field mode is not a gate but a measurement: how much the model already knows about your API without your docs. "The model already answers 40% of your tasks with no docs; your MCP server adds 22 points" is a real finding, and it turns contamination from a threat into a number. The report layer refuses to pool across report classes, across `mcp_revision`, and across generated vs. authored skills.

---

## 6. Locked decisions

Full reasoning for each: [`decisions.md`](./decisions.md).

| # | Topic | Decision |
|---|---|---|
| L1 | State isolation | **Amended:** instance-per-run, in-memory, seeded by parameter, torn down after. Containers only when the target needs them. Mutating tasks parallelize |
| L2 | Canonical artifact | OpenAPI 3.1 is the single source of truth for generated materials |
| L3 | Domain distance | Far from compliance/registry. aipolicies.eu is **not** the structural mirror |
| L4 | Realism target | Generic real-world REST conventions, not a product twin |
| L5 | HTTP surface | Full reads + writes. The four same-change-different-route mutations sit inside a normal CRUD API as the harm-asymmetry probe |
| L6 | Surface size | Configurable; realistic core + optional distractor modules; tasks target the core |
| L7 | Providers | Swappable interface. OpenAI first; **model tier before second provider** |
| L8 | Agent loop | Owned by the harness, never a vendor agent framework |
| L9 | Product shape | Engine is API-agnostic; the controlled experiment is a consumer via the same task-pack interface |
| **L10** | Language | **Python**, including the `code-fs` sandbox. Single runtime; TS-comparability caveat recorded in [F4](./decisions.md#f4--code-fs-sandbox-is-python) |
| **L11** | MCP revisions | **Both supported.** `mcp_spec_revision` recorded per run; revision is an axis; results never pooled across it |
| **L12** | Budget | No fixed cap. Gated per phase; the planner prints projected spend and requires confirmation before executing |
| **L13** | Skill conditions | Two — `skill-generated` and `skill-authored`, reported separately. The authored skill is committed before any results exist; that commit is the pre-registration |
| **L14** | Doc budget | **Not equalized.** V2 is dropped; static context is a measured covariate and doc budget is swept |

### On L3/L4 vs. spec §4.1 — the contradiction, resolved

Spec §4.1 recommends mirroring a compliance/registry structure. L3/L4 move away from it. This read as a contradiction in v1 and is now resolved explicitly: **L3/L4 supersede §4.1.** The resolution is *structural* realism — nesting depth, pagination, CRUD verbs, error surface, bare-ID references — with *thematic* distance. The default theme is a **media catalog** (studio → series → season → episode → asset): natural fan-out ("tag every episode in a season"), natural irreversible op (`:archive`), vocabulary nowhere near compliance. A **fleet** theme follows as a domain-robustness check — if arm ranking flips across themes, the first matrix is a domain artifact, and we want to find that before a reviewer does.

---

## 7. The mock API — controlled experiment

The centerpiece (§1). A fictional **media catalog**: studio → series → season → episode → asset. Requirements the `experiment` package must satisfy, unchanged from the spec except where noted:

- Contamination-free fictional domain; **Z0 ≈ 0 is a hard gate**
- Nested objects ≥3; bare-ID references vs. embed; `?expand=` / sparse fields; pagination; error surface; idempotency keys; optional dry-run
- Four mutation routes with asymmetric harm (`PATCH` / `PUT` / sub-collection `POST` / action `:archive`)
- Matched-pair tasks: shared navigation core, swappable terminal
- Programmatic grading only for research claims; writes graded on final state, never on the transcript
- Instance-per-run isolation (L1 as amended)
- Ranked search **included**, frozen at seed time for determinism
- Difficulty: **sweep** hop depth and fan-out; **fix** nesting at 3 and ambiguity at medium for the first matrix

### Statistical plan — written with the rig, not after

Specified in the same commit as the rig, before any matrix run: mixed-effects logistic model, random intercept per core, arm as fixed effect, paired within-core contrasts; stated MDE and the power calculation behind the chosen n; multiple-comparison correction; explicit confirmatory (pre-registered, corrected) vs. exploratory (labelled, uncorrected) split.

"≥3 repeats" is not an analysis plan. With 6+ arms × 5 task classes × 4 strata a noise-driven ranking flip is near-certain, and without a plan there is no way to tell it from a result. Also stated plainly: repeats at fixed temperature measure **sampling noise only** — variance over task instances requires more cores, not more repeats.

---

## 8. Delivery phases

| Phase | Deliverable |
|---|---|
| **P0** | Repo skeleton; **task-pack schema frozen**; **`PackagingMethod` plugin interface**; orthogonal axes + matrix selection layer; provider interface; cost estimator; `rule → justifying run` traceability (empty) |
| **P1** | Engine: agent loop, OpenAI adapter, executors for `tool-call` / `shell` / `code`, discovery modes `eager-all` / `meta-tools` / `code-fs`, dual-revision MCP client, tracing, gold-free metrics (all tagged `unvalidated`) |
| **P1.5** | **T1 static lint + agent-readiness scorecard** — first shippable artifact, $0 to run |
| **P2** | **Field mode + T2 probe**, read-only default, Z0/Z1 parametric baseline, first real target |
| **P3** | Controlled rig: fictional media-catalog API, seeder, task/answer-key generator, grader, **Z0 gate**, statistical plan; rig validation (~90 runs) |
| **P4** | Controlled matrix + error/response affordance sweep + dual skill conditions; flip metric validation flags; back-fill lint-rule justifications |
| **P5** | Surface-size sweep; model-tier axis; MCP-revision axis; second provider; second domain theme (fleet); TS `code-fs` robustness check |

P0's three contracts are pulled forward deliberately: they are cheap to fix now and expensive once traces exist in the wild.

---

## 9. Non-goals

- Not a model capability leaderboard — the model is controlled within any comparison
- Not a security or sandbox-escape study
- Not tied to aipolicies.eu or any real compliance product
- **Not human-in-the-loop.** MCP Apps / UI resources are out of scope
- **Not multi-agent.** Delegation and orchestration are out of scope; retrieval metrics are borrowed from [2511.01854](https://arxiv.org/abs/2511.01854), its multi-agent framing is not
- No LLM judge for research-grade correctness claims — field mode only, always labelled

---

## 10. What is still open

None of these gate P0. Tracked in [`decisions.md`](./decisions.md#still-open).

1. **First field-mode target** — secondary to the mock API, and needed only at P2. Candidate: the workspace's own `eu-regulations` MCP server. Its live `tools/list` was checked on 2026-08-05 and a worked pack against it is in [`task-pack-schema.md`](./task-pack-schema.md) §5; it is a usable surface with one caveat (three `graphTypes` layers are declared but unpopulated, so requesting them returns nothing *without* an error — a silent-failure trap to measure deliberately, and a sign the surface is still moving). Using it does not violate L3, which governs the *fictional* domain, not the field target.
2. **Product naming.** `harness-lab` names the rig, not the thing a user runs. Matters when T1 ships.
3. **Who authors the `skill-authored` condition** — must be written before results exist, so it schedules into P3.
4. **Publication intent and venue** — sets how hard pre-registration and the statistical plan must be.

---

## 11. Prior art status

All five arXiv citations and the MCP revision claims were verified 2026-08-05; the verification table lives in [`decisions.md`](./decisions.md#prior-art--verification-status). One consequence to carry forward: **Sampling, Roots, and Logging are deprecated** as of 2026-07-28, so any prior work built on them now sits on a deprecated substrate — worth a sentence when positioning, and a reason not to build variants on them.

**Standing rule:** no external claim enters a published document without a dated verification row.
