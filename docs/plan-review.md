# Review of `plan.md` (+ `harness-benchmark-spec.md`)

> **Status: addressed, 2026-08-05.** This review is retained as a historical record. Every issue (G1–G10) and every open decision (Part 6 #1–#6) is resolved in [`decisions.md`](./decisions.md); the resulting design is [`plan.md`](./plan.md) v2.
>
> **Three places the review was overtaken by verification.** Its Part 3 MCP claims all check out, but:
> - **G1's headline call was wrong in emphasis.** `code-fs` is not "the cell most likely to produce the headline result" — [arXiv 2602.15945](https://arxiv.org/abs/2602.15945) already formalizes context-coupled vs. context-decoupled MCP on MCP-Bench. Code execution is table stakes; the headline moves to G4 and RQ3/RQ4.
> - **The arXiv IDs the appendix flagged as unverified all resolve correctly**, and match their descriptions. One caveat the review did not catch: 2511.01854's setting is *multi-agent* routing, which our non-goals exclude — borrow its metrics, not its framing.
> - **"C1/C2 = invocation: code (bash)" conflates two mechanisms.** Freehand curl against docs and writing code against a generated module tree are different arms. Resolved by splitting `invocation` three ways: `tool-call` / `shell` / `code`.
>
> One recommendation was **not** taken: the TypeScript `code-fs` sandbox. Python was chosen for single-runtime simplicity, with the comparability cost recorded in [F4](./decisions.md#f4--code-fs-sandbox-is-python) and a TS executor kept as a later robustness check.

**Reviewer pass:** 2026-08-03
**Verdict:** Structurally sound, ~70% of the way there. The engine/experiment split and the field/controlled distinction are the right calls and should be kept. But the plan cannot express the variants the product is being asked to measure, and it has no defined output artifact. Ten issues below, ranked. Recommendations on every open decision at the end.

---

## Part 1 — What is already right (keep, don't relitigate)

- **Engine / experiment split with the dependency rule** (`engine` must not depend on `experiment`). This is the single most important decision in the plan and it is correct.
- **Controlled rig as validation harness for the gold-free metrics.** This is the argument that makes field mode credible instead of hand-wavy. It is a genuinely good idea and is currently underplayed — it deserves to be the headline of the methodology section, not a footnote in §8.
- **Harness owns the agent loop.** Non-negotiable and correctly identified.
- **Z0 as a hard gate.** Correct.
- **Programmatic-only grading for research claims; LLM judge quarantined to field mode.** Correct.
- **Pre-registration (V4) and report-class separation (§5).** Correct and rare. Keep.

---

## Part 2 — Structural issues

### G1 — The variant descriptor cannot express the variants you asked for  🔴 blocking

You asked for "mcp discovery with code execution + skill." The descriptor in §3 cannot represent that, because its axes are entangled:

- `tool_source: generated-from-openapi | live-mcp | curl-docs` mixes **where materials come from** with **what transport the agent uses**. `curl-docs` is not a source, it's a transport + an instruction format.
- `topology: per-operation | discovery-dispatch` conflates **how tools are discovered** with **how they are invoked**.
- **Code execution does not appear anywhere.** The C arms are bash+curl against REST, which is a different thing entirely from the code-execution-with-MCP pattern (tools presented as an importable module tree; the model writes code that calls them; intermediate results stay in the sandbox and never enter context). That pattern is the main thing the 2025–26 literature is arguing about, it is on the MCP 2026 roadmap as "composable tool execution," and it is the single variant most likely to win. Its absence is the biggest hole in the plan.

**Replace presets-with-entangled-axes with orthogonal axes.** Presets become named points in the space, not the primitive:

```yaml
variant:
  transport:      mcp | http-rest | in-process          # how a call physically happens
  discovery:      eager-all                              # every schema in context turn 1
                | meta-tools                             # search/describe/invoke triad
                | code-fs                                # importable module tree, read on demand
                | retrieval                              # top-k tool retrieval over an index
  invocation:     tool-call | code                       # direct call vs. model writes code
  instructions:   none | skill-flat | skill-progressive
                | docs-flat | docs-progressive
  schema_detail:  minimal | standard | rich              # rich = examples + error taxonomy
  response_shape: as-is | sparse | budgeted              # see G4
  surface_size:   int
  model:          <id>                                   # see G7
  reasoning_effort: <explicit>
  caching:        on | off
```

The original arms fall out as presets, and the interesting cells become expressible:

| Preset | transport | discovery | invocation | instructions |
|---|---|---|---|---|
| A1 | mcp | eager-all | tool-call | none |
| A2 | mcp | meta-tools | tool-call | none |
| B1 | mcp | eager-all | tool-call | skill-flat |
| B2 | mcp | meta-tools | tool-call | skill-flat |
| C1 | http-rest | — | code (bash) | docs-flat |
| C2 | http-rest | — | code (bash) | docs-progressive |
| **D1** *(new)* | mcp | **code-fs** | **code** | none |
| **D2** *(new)* | mcp | **code-fs** | **code** | skill-progressive |
| **D3** *(new)* | mcp | meta-tools | **code** | skill-flat |
| **E1** *(new)* | mcp | **retrieval** | tool-call | none |

D2 is the current state-of-the-art recommendation and is the cell most likely to produce the headline result. Not having it would make the benchmark obsolete on publication.

The combinatorial space is now large (~thousands of cells). That is fine and is the point — the engine enumerates, the **run plan** selects. Add an explicit `matrix:` / `include:` / `exclude:` config layer so a run is a declared subset with a stated rationale, and so field users can run 6 cells instead of 600. Validity is enforced by *which cells you compare*, not by restricting what the tool can express.

### G2 — The product has no defined output  🔴 blocking

The plan describes what is measured but never what the user receives. "Best-in-class tool for how any API should expose itself to an agent" implies a **verdict and a diff**, not a metrics dump. Also: nobody with a real API is going to pay for 1,350 LLM runs to find out their error messages are bad.

Add a **three-tier output model**, cheapest first:

| Tier | Cost | Mechanism | Output |
|---|---|---|---|
| **T1 — Lint** | $0, seconds | Static analysis of the OpenAPI spec / MCP `tools/list` | Agent-readiness scorecard: naming collisions, missing/empty descriptions, unbounded list responses, no pagination defaults, untyped errors, >N ops with no discovery layer, verb-ambiguous mutation routes |
| **T2 — Probe** | ~$5–20 | ~30 runs, 3–4 variants, gold-free metrics only | "Your API costs 3.1× more tokens per task under eager-all than under code-fs. Argument validity is 61% — the failures cluster on `filter[]`." |
| **T3 — Benchmark** | $100+ | Full matrix + user task pack + grader | Research-grade, correctness and harm included |

T1 is the adoption wedge and the thing that makes this a *product* rather than a study. It is also cheap: most of the rules are derivable from the metrics you already plan to collect, run in reverse. **Every T1 rule must eventually be justified by a T2/T3 measurement** — a lint rule you can point at an effect size for is a defensible moat; one you can't is just opinion. That traceability (rule → the run that justifies it) should be a first-class data structure, not prose.

### G3 — The Task Pack format is the interop contract, and it is unspecified  🟠 high

"Given we have a test set for that particular API" is the crux of the bring-your-own story, and the plan handles it in one line (O6 `oracle-supplied`). This format is what makes the tool adoptable or not — it should be **frozen at P0**, before the engine, because everything downstream is shaped by it.

Minimum:

```yaml
task_pack:
  api: { openapi: ./spec.yaml, base_url_env: TARGET_BASE_URL, auth: { type: bearer, env: TOKEN } }
  isolation: { mode: reseed | snapshot | none, setup: ./seed.sh, teardown: ./reset.sh }
  tasks:
    - id: find-overdue-invoice-owner
      prompt: "Who owns the oldest unpaid invoice for account ACME?"
      class: R | W-safe | W-lossy | W-irrev | RW-fan
      answerable: true
      grade:
        - type: equals | contains | regex | jsonpath | state-diff | script
          ...
      gold_call_sequence: [...]   # optional; enables selection-accuracy + Z1
      harm_tier: 0..3
      forbidden_calls: ["DELETE /accounts/*"]   # harm detection without a state differ
```

Two things worth building alongside it:
- **`forbidden_calls`** gives you a harm signal on real APIs where you cannot diff state. Cheap, and it partially rescues the safety metrics in field mode (see G9).
- **A task-pack generator** — propose candidate tasks from the OpenAPI spec (and optionally real traffic logs), human confirms/edits. Authoring 50 graded tasks by hand is the actual adoption barrier, and assisted authoring is what clears it.

### G4 — Response and error design is treated as a fixed API property, not a manipulated variable  🟠 high — and this is your best unclaimed finding

Spec API-5 (payload size) and API-8 (error surface) are listed as *properties the test API must have*. They are never varied as experimental conditions. That leaves the most actionable question an API owner has completely unanswered:

> Is it cheaper to fix my error messages than to ship a skill?

An agent that gets `422: validation failed` retries blindly; one that gets `422: field 'created_after' expects RFC3339, received '2024-13-01'` self-corrects in one turn. That is a one-line server change, versus writing and maintaining a skill. Nobody has published the trade rate, and the packaging-vs-payload framing is exactly the "how should my API expose itself" question — broader than "which wrapper should I put on it."

Add two axes and two metrics:

- `response_shape: as-is | sparse | budgeted` — does capping/shaping the response beat adding instructions?
- `error_detail: terse | field-scoped | field-scoped+remedy`
- **Error recovery rate** — fraction of 4xx responses followed by a corrected retry within 2 turns
- **Turns-to-first-productive-call**, split by whether an error preceded it

Cost: one extra sweep on the controlled rig. Payoff: the most quotable and most actionable result in the study, and it directly feeds T1 lint rules.

### G5 — V2 (equal documentation token budget) is the wrong control  🟠 high

Forcing MCP JSON schemas and markdown curl docs to the same token count means either padding the docs or truncating them. You would then be measuring *artificially padded docs*, and the confound you introduce is worse than the one you remove. Static context size is also not a nuisance variable here — it is **a real, causal property of the packaging choice**, and it is half of why the arms differ at all. Equalizing it equalizes away the effect.

**Replace V2 with:** report static-context tokens as a measured covariate; run a **doc-budget sweep** (terse / standard / verbose) as its own axis; make the causal claim from the interaction, not from forced parity. Keep V1 (mechanical generation from one spec) — that control is sound and does the anti-favouritism work V2 was reaching for.

### G6 — Skill quality is an uncontrolled confound, and RQ1 rests entirely on it  🟠 high

RQ1 is "what does a skill layer contribute." If skills are generated mechanically from the spec, a null result means *"our generated skill was bad,"* not *"skills don't help"* — and that is the result you'd have to publish. Real skills encode workflow knowledge that is not in the OpenAPI spec, which is the whole reason they exist.

Run **two skill conditions** and report separately:
- `skill-generated` — mechanical, preserves V1
- `skill-authored` — best-effort human/LLM-authored, versioned in the repo, **written before seeing any results** and pre-registered

The gap between them is itself a finding worth publishing ("skill quality is worth X points; mechanical generation captures Y% of it"), and it's the difference between an honest RQ1 and an unfalsifiable one.

### G7 — Model tier belongs on the axis list, not in the "controlled variable" bin  🟡 medium

Spec §1 declares the model a controlled variable — correct for the research claim, wrong for the product. The API owner's real question is "what do I need to ship so that *my consumers'* agents succeed," and the answer is tier-dependent: a small model may need a progressive skill where a frontier model does fine with curl and docs.

Keep the model fixed within a controlled comparison. But make **model tier a first-class field-mode axis**, and make "your API needs a skill for cheap models but not frontier ones" a supported finding. This also gives you a cheap, high-value published result: the packaging effect size as a function of model capability, which is exactly the V8 obsolescence worry turned into a deliverable.

### G8 — No statistical plan  🟡 medium

"≥3 repeats" is not an analysis plan, and §7's n's look underpowered for the claims in §3.5. Tasks are nested in cores; arms are compared within core; there are 6+ arms × 5 task classes × 4 strata. Without a plan you will get a ranking flip that is noise and no way to tell.

Specify before Phase 1: mixed-effects logistic model, random intercept per core, arm as fixed effect, paired within-core contrasts; a stated MDE and the power calculation behind the chosen n; the multiple-comparison correction; and which comparisons are confirmatory (pre-registered, corrected) versus exploratory (labelled, uncorrected). Also state that repeats at fixed temperature measure sampling noise only — if you want variance over task instances you need more cores, not more repeats. This is a half-day of work that determines whether Phase 1 is publishable.

### G9 — Field mode declares contamination "uncontrolled" when it is measurable  🟡 medium

The plan writes off field results as unpoolable. But Z0 works on real APIs too — it just measures something different there: **how much the model already knows about your API parametrically**. Run Z0 and Z1 in field mode and report every field result as **lift over the parametric baseline**, with the Z0 score published alongside.

That converts an unusable caveat into a genuinely useful number. "GPT-x already knows 40% of your API without your docs; your MCP server adds 22 points" is a real finding for an API owner, and it turns contamination from a threat into a measurement.

### G10 — L1 (in-memory, reset = reseed) serializes the whole run  🟢 minor

§4.4 requires per-task isolation; L1 makes reset a global re-seed, which forces mutating tasks to serialize (the plan acknowledges this). With an in-memory API there is no reason to accept that: **one API process per run, seeded by parameter, torn down after.** Process spawn is milliseconds, isolation is total, and it parallelizes fully. Amend L1 to "instance-per-run, in-memory, seeded by parameter; containers only when the target needs them."

---

## Part 3 — "What else is coming"

The plan is a snapshot of mid-2026 practice with no extension seam — and the ground moved under it last week.

**The [2026-07-28 spec](https://blog.modelcontextprotocol.io/posts/2026-07-28/) turned MCP from a bidirectional stateful protocol into a stateless request/response one.** This is not a minor revision, and several parts of `plan.md` and the spec assume the old shape:

- **Sessions are gone.** The `initialize`/`initialized` handshake and the `Mcp-Session-Id` header are retired; protocol version, identity, and capabilities now ride in `_meta` on every request. Every request is self-contained and routable to any instance behind a load balancer.
- **Header-based routing.** Streamable requests must carry `Mcp-Method` and `Mcp-Name` so gateways can route without parsing the body.
- **Multi Round-Trip Requests (MRTR)** replace server-initiated requests over open streams: the server returns `resultType: "input_required"`, the client retries with `inputResponses` attached.
- **Cacheable list results** — `tools/list` etc. now carry `ttlMs` and `cacheScope`.
- **Deprecated: Roots, Sampling, and Logging.** Legacy HTTP+SSE transport is on a 12-month offramp.
- **Tasks moved to an extension framework** with poll-based `tasks/get` / `tasks/update`.
- Authorization hardened: RFC 9207 issuer validation, DCR → Client ID Metadata Documents.

**Three direct consequences for this plan:**

1. **`_meta` on every request is a new per-call token tax** that did not exist before, and it scales with call count. That penalizes chatty arms (`eager-all` + `tool-call`) and favours arms that batch calls inside a sandbox (`code-fs` + `code`). The cost model in spec §5 has to account for per-request protocol overhead, not just tool-definition overhead — and this alone may shift the A-vs-D ranking.
2. **The harness's MCP client must be version-aware, and every run must record the target's spec revision.** Field-mode results against a pre- and post-2026-07-28 server are not comparable. Add `mcp_spec_revision` to the run config snapshot (§6.4).
3. **Statelessness weakens one of the standing arguments for MCP over plain HTTP.** If MCP is now request/response with per-request identity, the honest framing of the C arms shifts: they are closer to MCP-minus-schemas than they were, which sharpens rather than weakens RQ3.

Anything hardcoded to today's shape ages in months, which is the argument for the plugin seam below.

**Make a packaging method a plugin, not an enum value.** One interface, three methods:

```
PackagingMethod:
  materialize(spec, config) -> materials      # what enters context before turn 1
  executor(materials)       -> Executor       # how a call is made
  account(trace)            -> CostBreakdown  # tokens / sandbox / round-trips
```

Everything in G1's axis table is then an instance of this, and so is everything below. Adding a method should be a new plugin file, never a change to the engine.

Candidates to design for now and implement later:

| Emerging method | Why it matters to this benchmark |
|---|---|
| **Code execution over MCP** (`code-fs` + `code`) | Not emerging — current, and missing from the plan. See G1. Ship in P1. |
| **Cacheable `tools/list`** (`ttlMs` / `cacheScope`) | Changes the static-context cost model. §5.6's cached/uncached reporting rule needs a third condition: cacheable-list. |
| **Stateless transport / `_meta` per request** | Removes per-session setup cost but adds a per-*call* tax. Net effect differs by arm — must be measured, not assumed. Version-stamp every run. |
| **MRTR elicitation** (server asks the client mid-call, e.g. to confirm a destructive op) | Directly relevant to RQ3, and now the *sanctioned* way to do it. A server that *asks before archiving* may beat a typed tool surface at harm reduction, at some latency cost. This is a packaging choice an API owner controls and it belongs on the harm axis. Add `confirmation: none \| mrtr` as an axis. |
| **Tasks extension** (poll-based `tasks/get` / `tasks/update`) | The async/long-running job protocol, now standardized. See the async row below — this is no longer speculative, it has a spec-blessed shape to implement against. |
| **Sampling / Roots / Logging deprecated** | Don't build variants on these. If any prior-art paper the plan positions against used them, its results are on a deprecated substrate — worth a sentence in §2. |
| **Tool retrieval / progressive tool loading** | `discovery: retrieval` in G1. Retrieval metrics (Recall@k, nDCG@k) are already cited in the spec's prior-art table but no arm uses them. |
| **MCP Apps / UI resources** | Out of scope — no human in the loop. Say so explicitly in non-goals. |
| **`llms.txt` / `AGENTS.md`-style API descriptors** | An `instructions:` variant; near-free to add once the plugin seam exists. |
| **Async / long-running job protocols** | Your own `linker` and `sc-core-jobs` work is exactly this shape, and MCP just standardized it as the Tasks extension. Poll-vs-callback is a packaging choice with a real token cost (every poll is a round trip) and nobody has measured it. Strong Phase 3+ candidate, and one where you have domain experience others don't. |

---

## Part 4 — Recommendations on the open decisions

**From `plan.md`:**

| # | Question | Recommendation |
|---|---|---|
| O1 | Language | **Python.** Agreed, for the ecosystem reasons stated. One correction: the `code-fs` arm needs a sandbox with a real module system — generate **TypeScript** modules and run them under Node, since that is the pattern the literature uses and you want comparability. Python harness spawning a Node sandbox is fine and normal. Don't let language preference distort the arm. |
| O2 | Discovery: hand-rolled vs native | **Hand-rolled triad as the primary**, for cross-provider symmetry. Additionally run native tool-search as a *separate labelled variant* where available — the delta between hand-rolled and native is a publishable finding ("your dispatcher is/isn't the bottleneck") and it defuses the "you benchmarked your own dispatcher" objection instead of just accepting it. |
| O3 | Ranked search | **Include, frozen at seed time.** Real APIs have it, and its absence would bias against discovery arms that would naturally lean on it. Determinism is preserved by freezing. |
| O4 | Domain theme | **Media catalog.** Best fan-out semantics ("tag every episode in a season"), most natural irreversible op (`:archive`), and the vocabulary is far from compliance. Note the tension with spec §4.1, which recommended a registry mirror: L3/L4 supersede it, and the resolution is *structural* realism with *thematic* distance. Worth stating that explicitly in the plan, since it reads as a contradiction right now. **Add a second theme (fleet) in Phase 3** as a domain-robustness check — if the arm ranking flips across themes, everything in Phase 1 is a domain artifact, and you want to know that before someone else finds it. |
| O5 | Real-API writes | **Read-only default, opt-in writes, `forbidden_calls` always on.** Agreed as written. Add: refuse to run write variants against a target whose base URL matches a production-looking host without an explicit `--i-know` flag. |
| O6 | Grader modes | Agreed. Add a fourth: **`assertion-free`** — gold-free metrics only, no task pack at all. This is what makes T2 (G2) possible for a user who has an API but no test set, and it is the most common starting state. |
| O7 | Second provider | **Anthropic**, and add a cheap-tier model of the same provider before adding a second provider — per G7, the tier axis is worth more to the product than the provider axis, and costs less. |
| O8 | OSS release timing | **Release the engine + T1 lint early; hold the controlled results until Phase 1 completes.** The engine is the durable contribution and early release recruits task packs from users, which is the scarce resource. Pre-registration (V4) protects the results from being scooped by your own tool. |

**From `harness-benchmark-spec.md` (§11), which `plan.md` leaves partly unaddressed:**

| # | Question | Recommendation |
|---|---|---|
| D3 | Sandbox: container per run or shared | **Subprocess per run for P1–P3** (in-memory API, no real credentials, no network egress). Container per run only for field mode against real targets, where egress and credentials are live. Don't build Docker isolation before you need it. |
| D5 | Which difficulty dimensions to fix vs sweep | **Sweep hop depth and fan-out; fix nesting depth at 3 and ambiguity at medium** for Phase 1. Hop depth and fan-out are where P1/P3 predict the effects; nesting is a plausible nuisance. Revisit after Phase 0 shows which dimensions actually move the metrics. |

---

## Part 5 — Revised phasing

The current plan puts field mode at P4. If field mode is the durable product, that is backwards — it means the product hypothesis stays untested for months while the research rig gets built.

| Phase | Deliverable | Change from plan |
|---|---|---|
| **P0** | Repo skeleton; **Task Pack schema frozen**; **PackagingMethod plugin interface**; variant axes (G1); provider interface; config + matrix selection layer | Task Pack and plugin seam pulled forward — both are contracts, cheap now, expensive later |
| **P1** | Engine: agent loop, OpenAI adapter, executors for `tool-call` + `code`, discovery modes `eager-all` / `meta-tools` / `code-fs`, tracing, gold-free metrics | `code-fs` + `code` added (G1) |
| **P1.5** | **T1 static lint + scorecard** | New. Cheap, standalone, and the adoption wedge (G2) |
| **P2** | Experiment: fictional media-catalog API, seeder, task/answer-key generator, grader, **Z0 gate**, statistical plan (G8) | Instance-per-run isolation (G10) |
| **P3** | Controlled Phase 0 (~90 runs) → Phase 1 matrix; response/error-affordance sweep (G4); dual skill conditions (G6) | G4 and G6 folded in |
| **P4** | **Field mode + T2 probe**, read-only, Z0/Z1 parametric baseline (G9) | Moved earlier relative to the full matrix |
| **P5** | Surface-size sweep; model-tier axis; second provider; second domain theme | Tier before provider (G7); second theme added (O4) |

---

## Part 6 — Decisions I need from you

1. **G1 axis model** — accept the orthogonal axes and add the code-execution variants (D1/D2/D3)? Everything downstream depends on this.
2. **G2 three-tier output** — is T1 lint in scope, or is this a research rig only? This changes what the product *is*.
3. **G4 response/error sweep** — worth the extra sweep? I think it's your strongest unclaimed result, but it widens the controlled experiment.
4. **G5** — drop equal-token-budget (V2) in favour of budget-as-covariate + sweep? This is a real methodology change and the one most likely to draw reviewer argument either way.
5. **Phasing** — pull field mode ahead of the full controlled matrix, or keep research-first?
6. **MCP spec revision** — target 2026-07-28 (stateless) only, or support both revisions so field mode can hit the large installed base still on the old transport? Supporting both costs real client work but is probably unavoidable for a year; targeting only the new one is cleaner and dates the results in the honest direction.

Everything else above I'd apply as written unless you object.

---

## Appendix — Smaller notes

- **Verify the arXiv IDs in spec §2 before publishing.** Four are cited (2602.15945, 2605.24660, 2511.01854, 2508.20453) and I have not confirmed any of them resolve to the described papers. Prior-art claims are the easiest thing for a reviewer to check first.
- **Spec §5.6** ("report cached and uncached") needs a third condition now that `tools/list` is cacheable at the protocol level — that is a different cache from prompt caching and it moves the static-context cost for `eager-all` specifically.
- **Spec §7 budget** was priced July 2026 and flagged volatile; the added sweeps (G4, G6, dual skill conditions) roughly double Phase 1. Re-price before committing.
- **Non-goals should explicitly exclude** human-in-the-loop UI surfaces (MCP Apps) and multi-agent delegation. Both will otherwise get asked about.
- **Naming:** `harness-lab` describes the rig, not the product. If T1/T2 ship, the user-facing thing wants a name about the API's readiness, not about your test harness.
