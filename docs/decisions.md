# Decision Record

**Status:** Adopted — 2026-08-05
**Supersedes:** the open-question lists in [`plan.md`](./plan.md) §7 (O1–O8), [`harness-benchmark-spec.md`](./harness-benchmark-spec.md) §11 (D1–D6), and [`plan-review.md`](./plan-review.md) Part 6 (#1–#6).

This is the durable record of *why* each decision went the way it did. `plan.md` describes the resulting system; this file explains the choices. When the two disagree, this file is the reasoning and `plan.md` is the spec — fix `plan.md`.

Decision IDs are stable. Adding a decision appends; reversing one supersedes it in place with a dated note.

---

## Framing decisions

These four set the shape of everything else.

### F1 — Tool first, study second

**Decision:** Build the reusable engine, the static lint, and field mode *before* the full controlled matrix. Research claims land later.

**⚠ Build order is not priority order.** The **mock API is the main subject of the project** — it is where Z0, the four-route harm probe, matched-pair write penalties, and the affordance sweep live, and none of them can exist on a real API. Tool-first is a scheduling decision about the reusable substrate, not a statement that the rig matters less. Field targets (including `eu-regulations`, [N1](#still-open)) are secondary throughout.

**Why:** `plan.md` §1 already argued the field tool is the durable product and the controlled experiment is its validation harness. The original phasing (§9) contradicted that by putting field mode at P4 — the product hypothesis would have stayed untested for months while the research rig was built. Given how fast the ground is moving (see F3, and the fact that [arXiv 2602.15945](https://arxiv.org/abs/2602.15945) landed on the code-execution question first), a months-long silent build is the higher risk.

**Consequence — and the honesty problem it creates:** `plan.md` §8 promised gold-free metrics would be *validated* on the controlled rig before being trusted in the field. Tool-first ships field probes before that validation exists. This is not papered over:

- **T1 (static lint) is unaffected.** It reads a spec and makes no measurement claim. It is the honest wedge, and it ships first.
- **Every metric carries a `validation` field** (`unvalidated` | `validated-controlled` | `heuristic`), printed in every report footer. T2 field reports ship with metrics marked `unvalidated` until the rig flips them.
- **Every lint rule carries a `justified_by` field** pointing at the run(s) that establish its effect size — empty at first. A rule with no justifying run renders as "heuristic", not "measured". The traceability structure is built at P0 while it is cheap, and back-filled at P4.

See [D-G2](#g2--three-tier-output-model).

### F2 — No fixed budget cap; gate per phase

**Decision:** Do not commit a total LLM spend up front. Gate spend at each phase boundary, and build a cost estimator into the run planner so every matrix prints projected spend before executing and requires confirmation.

**Why:** The spec's §7 prices were July-2026 and flagged volatile, and the added sweeps (G4, G6) roughly double Phase 1. A fixed cap chosen now would be wrong in both directions — it would either strand the sweeps or over-commit to prices that will move. Reasoning tokens are the real variance driver (~2k → ~20k output per run at high effort), so the estimator must model reasoning effort explicitly, not assume a flat output size.

**Consequence:** Both the G4 error-affordance sweep and the G6 dual-skill condition survive. `max_turns` and `reasoning_effort` are capped and logged on hit, so a runaway matrix fails loudly rather than expensively.

### F3 — Support both MCP spec revisions

**Decision:** One `McpClient` interface, two transport implementations: legacy (`initialize`/`initialized` handshake, `Mcp-Session-Id`, HTTP+SSE) and 2026-07-28 (stateless, `_meta` per request, `Mcp-Method`/`Mcp-Name` headers).

**Why:** The [2026-07-28 revision](https://blog.modelcontextprotocol.io/posts/2026-07-28/) is verified real and is a breaking reshape, not a point release. But the deprecated transport has a 12-month offramp, so for roughly a year the installed base field mode must reach is split across both. Targeting only the new revision would be cleaner but would make field mode unusable against most real servers during exactly the window when field mode is the product.

**Consequence — this is an asset, not just a tax.** The two revisions have genuinely different cost models: legacy pays a per-*session* handshake, stateless pays a per-*call* `_meta` tax that scales with call count. That asymmetry penalizes chatty arms (`eager-all` + `tool-call`) and favours arms that batch calls inside a sandbox (`code-fs` + `code`). So `mcp_revision` becomes a **variant axis**, not just run metadata, and "migrating to stateless costs chatty arms X% more and batched arms Y% less" is a timely, unclaimed finding that falls out of work already required.

**Hard rule:** `mcp_spec_revision` is recorded in every run's config snapshot, and the report layer **refuses to pool results across revisions**. A pre- and post-2026-07-28 comparison is not a comparison.

### F4 — `code-fs` sandbox is Python

**Decision:** Generated tool modules are Python packages; the model writes Python; the sandbox is a Python subprocess. One runtime for harness and sandbox.

**Why:** The effect being measured — intermediate results stay in the sandbox and never enter context — is language-independent. A second runtime (Python harness spawning Node) doubles the debugging surface for no change to the mechanism.

**Known cost, recorded rather than hidden:** the literature this positions against (Anthropic's code-execution-with-MCP writeup, and 2602.15945's CE-MCP evaluation) uses TypeScript. Our numbers are therefore not *directly* comparable to theirs. Mitigation: a TS executor is a later robustness check behind the same `PackagingMethod` interface — if arm ranking is stable across runtimes that is itself a finding; if not, the literature's claim is runtime-bound, which is a bigger finding. This caveat must appear in any published comparison.

---

## Structural decisions (from `plan-review.md`)

### G1 — Orthogonal variant axes, with code execution

**Decision:** Accept the review's orthogonal axis model in full. The entangled `tool_source` / `topology` descriptor in `plan.md` §3 is replaced. Add presets D1/D2/D3 (code execution) and E1 (retrieval). Three axes beyond the review's list: `confirmation`, `error_detail`, `mcp_revision`.

**Why:** The old descriptor could not express "MCP discovery with code execution + skill" because its axes conflated *where materials come from* with *how a call is physically made*. Code execution was absent entirely.

**Reframe — and this is the important part.** The review called `code-fs` "the cell most likely to produce the headline result." Verification says otherwise: [2602.15945](https://arxiv.org/abs/2602.15945) already formalizes context-coupled vs. context-decoupled MCP and evaluates it on MCP-Bench. Code execution is therefore **table stakes** — its absence would make the benchmark obsolete, but its presence is no longer differentiating. The headline moves to the questions that paper does *not* answer: [G4](#g4--response-and-error-design-as-manipulated-variables) (error/response affordances) and RQ3/RQ4 (harm asymmetry across mutation routes, and arm-ranking reversal between read and write classes).

Full axis list, plugin interface, and preset table: [`packaging-method.md`](./packaging-method.md).

### G2 — Three-tier output model

**Decision:** Adopt T1 (static lint, $0) / T2 (probe, ~$5–20) / T3 (benchmark, $100+). T1 is in scope and is the first shippable artifact.

**Why:** The plan measured things but never defined what a user *receives*. And nobody with a real API will fund 1,350 LLM runs to learn their error messages are bad. T1 is the adoption wedge: most rules are derivable from metrics already planned, run in reverse.

**Constraint:** every T1 rule must eventually point at a T2/T3 measurement establishing its effect size. That `rule → justifying run` link is a first-class data structure, not prose. See [F1](#f1--tool-first-study-second).

### G3 — Task Pack schema frozen at P0

**Decision:** Freeze the format before the engine exists. Includes `forbidden_calls`, `class`, `harm_tier`. The task-pack *generator* is deferred until field mode proves demand.

**Why:** It is the interop contract — everything downstream is shaped by it and it is expensive to change once traces exist in the wild. `forbidden_calls` in particular buys a harm signal on real APIs where state cannot be diffed, which partially rescues the safety metrics in field mode.

Schema: [`task-pack-schema.md`](./task-pack-schema.md).

### G4 — Response and error design as manipulated variables

**Decision:** Promote response shape and error detail from fixed API properties (spec API-5, API-8) to experimental axes. Add `response_shape: as-is | sparse | budgeted` and `error_detail: terse | field-scoped | field-scoped+remedy`. Add two metrics: **error recovery rate** (fraction of 4xx followed by a corrected retry within 2 turns) and **turns-to-first-productive-call**, split by whether an error preceded it.

**Why:** This answers the most actionable question an API owner has — *is it cheaper to fix my error messages than to ship a skill?* An agent receiving `422: validation failed` retries blindly; one receiving `422: field 'created_after' expects RFC3339, received '2024-13-01'` self-corrects in one turn. That is a one-line server change versus authoring and maintaining a skill. The trade rate is unpublished.

With code execution no longer differentiating (see [G1](#g1--orthogonal-variant-axes-with-code-execution)), **this is the strongest unclaimed result available**, and it feeds T1 lint rules directly.

### G5 — Drop V2 (equal documentation token budget)

**Decision:** Remove validity control V2. Replace with: static-context tokens reported as a measured covariate, plus an explicit doc-budget sweep (`terse` / `standard` / `verbose`) as its own axis. Causal claims come from the interaction, not from forced parity. V1 (mechanical generation from one spec) is kept.

**Why:** Forcing MCP JSON schemas and markdown curl docs to the same token count requires padding one or truncating the other — measuring artificially padded docs. The confound introduced is worse than the one removed. More fundamentally, static context size is not a nuisance variable here: it is a **real causal property of the packaging choice** and half of why the arms differ at all. Equalizing it equalizes away the effect under study.

**This is a deliberate, arguable methodology change** and the one most likely to draw reviewer disagreement in either direction. It is recorded here with its reasoning so a reader meets the argument rather than the omission.

### G6 — Two skill conditions

**Decision:** Run `skill-generated` (mechanical, preserves V1) and `skill-authored` (best-effort, human/LLM-authored) and report them separately.

**Why:** RQ1 asks what a skill layer contributes. If skills are only generated mechanically from the spec, a null result means "our generated skill was bad", not "skills don't help" — and that is an unpublishable, unfalsifiable answer. Real skills encode workflow knowledge absent from the OpenAPI spec, which is the entire reason they exist. The gap between the two conditions is itself the finding: *skill quality is worth X points; mechanical generation captures Y% of it.*

**Hard constraint:** the authored skill is committed **before any results are seen**. That commit is the pre-registration. This schedules skill authoring into the rig phase, not the matrix phase.

### G7 — Model tier is a field-mode axis

**Decision:** Model stays fixed within any controlled comparison. But tier is a first-class field-mode axis, and "your API needs a skill for cheap models but not frontier ones" is a supported finding. A cheap tier of the *same* provider comes before adding a second provider.

**Why:** Spec §1 declares the model a controlled variable — correct for the research claim, wrong for the product. The API owner's actual question is "what must I ship so my *consumers'* agents succeed", and the answer is tier-dependent. This also converts the V8 obsolescence worry (harness effects shrink as models improve) into a deliverable: packaging effect size as a function of model capability. Tier costs less than a provider and is worth more to the product.

### G8 — Statistical plan written with the rig

**Decision:** Specified in the same commit as the controlled rig, before any matrix run: mixed-effects logistic model, random intercept per core, arm as fixed effect, paired within-core contrasts; stated MDE with the power calculation behind the chosen n; multiple-comparison correction; explicit confirmatory (pre-registered, corrected) vs. exploratory (labelled, uncorrected) split.

**Why:** "≥3 repeats" is not an analysis plan. With 6+ arms × 5 task classes × 4 strata, a ranking flip that is pure noise is near-certain, and without a plan there is no way to tell. Half a day of work that determines whether the matrix is publishable at all.

**Also stated plainly:** repeats at fixed temperature measure sampling noise only. Variance over *task instances* requires more cores, not more repeats.

### G9 — Z0/Z1 in field mode as a parametric baseline

**Decision:** Run Z0 and Z1 against real APIs too. Report every field result as **lift over the parametric baseline**, with the Z0 score published alongside.

**Why:** The plan wrote field results off as unpoolable due to uncontrolled contamination. But Z0 works fine on a real API — it just measures something different there: how much the model already knows about that API parametrically. "The model already answers 40% of your API's tasks with no docs at all; your MCP server adds 22 points" is a genuinely useful number for an API owner. This converts contamination from a threat into a measurement.

### G10 — Instance-per-run isolation

**Decision:** Amend L1 to: *instance-per-run, in-memory, seeded by parameter, torn down after; containers only when the target needs them.*

**Why:** Spec §4.4 requires per-task isolation; the original L1 made reset a global re-seed, forcing mutating tasks to serialize. With an in-memory API there is no reason to accept that — process spawn is milliseconds, isolation is total, and the run parallelizes fully.

---

## `plan.md` open questions

| # | Question | Decision | Reasoning |
|---|---|---|---|
| **O1** | Language / stack | **Python**, including the `code-fs` sandbox | Eval/agent ecosystem, FastAPI-from-OpenAPI, trivial subprocess sandbox. Single runtime per [F4](#f4--code-fs-sandbox-is-python); TS comparability caveat recorded there. |
| **O2** | Discovery: hand-rolled vs. native | **Hand-rolled triad primary**, native tool-search additionally as a separate **labelled** variant | Hand-rolled gives cross-provider symmetry, which the comparison requires. Running native alongside turns the standing objection ("you benchmarked your own dispatcher") into a measured delta — *is* our dispatcher the bottleneck — instead of a caveat we absorb. |
| **O3** | Ranked / fuzzy search | **Include, frozen at seed time** | Real APIs have it, and omitting it biases against discovery arms that would naturally lean on it. Freezing ranked results at seed preserves determinism. |
| **O4** | Fictional domain theme | **Media catalog** (studio → series → season → episode → asset) | Best fan-out semantics ("tag every episode in a season"), most natural irreversible op (`:archive`), vocabulary far from compliance. Fleet added later as a domain-robustness check — if arm ranking flips across themes, the first matrix is a domain artifact and we need to know before someone else finds out. |
| **O5** | Real-API writes | **Read-only default; opt-in writes; `forbidden_calls` always on** | Plus: refuse write variants against a production-looking host without an explicit acknowledgement flag. Full state-diff harm metrics stay exclusive to the controlled rig. |
| **O6** | Grader modes | `programmatic`, `oracle-supplied`, `llm-judge` (field only, never research), **`assertion-free`** | The fourth mode — gold-free metrics with no task pack at all — is what makes T2 reachable for a user who has an API but no test set. That is the most common starting state, so it is the mode that determines adoption. |
| **O7** | Second provider | **Cheap tier of the same provider first**, then Anthropic | Per [G7](#g7--model-tier-is-a-field-mode-axis): the tier axis is worth more to the product than the provider axis and costs less. |
| **O8** | OSS release timing | **Engine + T1 lint early; controlled results held until the matrix completes** | The engine is the durable contribution, and early release recruits task packs from users — the scarce resource. Pre-registration (V4) protects the results from being scooped by our own tool. Consistent with [F1](#f1--tool-first-study-second). |

---

## `harness-benchmark-spec.md` open questions

| # | Question | Decision |
|---|---|---|
| **D1** | Fictional domain shape | Resolved by **O4**. Note the apparent contradiction and its resolution: spec §4.1 recommended mirroring a compliance/registry structure; `plan.md` L3/L4 moved away from it. **L3/L4 supersede §4.1.** The resolution is *structural* realism (nesting, pagination, CRUD verbs, error surface) with *thematic* distance (media, not compliance). Both docs now say so explicitly. |
| **D2** | Discovery arm implementation | Resolved by **O2**. |
| **D3** | Sandbox: container per run or shared | **Subprocess per run** for the controlled phases — in-memory API, no real credentials, no network egress, so container isolation buys nothing. **Container per run** for field mode against real targets, where credentials and egress are live. Do not build Docker isolation before it is needed. |
| **D4** | Second provider | **Anthropic**, after the tier axis ([G7](#g7--model-tier-is-a-field-mode-axis)). |
| **D5** | Difficulty dimensions: fix vs. sweep | **Sweep hop depth and fan-out; fix nesting depth at 3 and ambiguity at medium** for the first matrix. Hop depth and fan-out are where predictions P1/P3 locate the effects; nesting is a plausible nuisance variable. Revisit after rig validation shows which dimensions actually move metrics. |
| **D6** | OSS release timing | Resolved by **O8**. |

---

## Prior art — verification status

Checked 2026-08-05. Prior-art claims are the first thing a reviewer checks, so these are recorded with their status rather than cited on trust.

| Citation | Status | Note |
|---|---|---|
| [MCP 2026-07-28 revision](https://blog.modelcontextprotocol.io/posts/2026-07-28/) | ✅ Verified | Sessions/`Mcp-Session-Id` retired; `_meta` per request; `Mcp-Method`/`Mcp-Name` headers; MRTR via `resultType: "input_required"` → `inputResponses`; `ttlMs`/`cacheScope` on list results; Roots/Sampling/Logging deprecated; Tasks in `io.modelcontextprotocol/tasks` with poll-based `tasks/get`/`tasks/update`; 12-month HTTP+SSE offramp. |
| [arXiv 2602.15945](https://arxiv.org/abs/2602.15945) — *From Tool Orchestration to Code Execution* | ✅ Verified | Formalizes context-coupled vs. context-decoupled (CE-MCP); evaluates on MCP-Bench across 10 servers; also covers the security posture shift. **Occupies the code-execution ground** — see [G1](#g1--orthogonal-variant-axes-with-code-execution). |
| [arXiv 2605.24660](https://arxiv.org/abs/2605.24660) — *How Many Tools Should an LLM Agent See?* | ✅ Verified | Source of Bits-over-Random. Registries 20–3,251 tools; learned depth policy matches top-50 coverage showing ~7 tools. Adopt BoR for RQ2. |
| [arXiv 2511.01854](https://arxiv.org/abs/2511.01854) — *Tool-to-Agent Retrieval* | ✅ Verified | Recall@k / nDCG@k for the `retrieval` discovery mode. **Caveat:** its setting is multi-agent routing, which our non-goals exclude — borrow the metrics, not the framing. |
| [arXiv 2508.20453](https://arxiv.org/abs/2508.20453) — *MCP-Bench* | ✅ Verified | Accenture, Aug 2025; 28 live servers, 250 tools. Structural template for task design. Note it is also the substrate 2602.15945 evaluates on. |
| MCP spec discussion #1780 | ⬜ Unverified | Output-schema-brittleness objection to code-execution mode. Verify before citing. |

**Standing rule:** no external claim enters a published doc without a dated verification row here.

**One consequence worth stating:** Sampling, Roots, and Logging are deprecated as of 2026-07-28. Any prior work built on those primitives now sits on a deprecated substrate — worth a sentence when positioning against it, and a reason not to build variants on them.

---

## Still open

Non-blocking. None of these gate P0.

| # | Question | Notes |
|---|---|---|
| **N1** | First field-mode target — **secondary to the mock API**, needed at P2 | Candidate: the workspace's own `eu-regulations` MCP server (~12 tools). Live `tools/list` verified 2026-08-05; worked pack in [`task-pack-schema.md`](./task-pack-schema.md) §5. Real MCP surface, real docs, under our control, and *structurally* the registry shape spec §4.1 wanted. Using it does not violate L3, which governs the **fictional** domain, not the field target. **Caveat:** three `graphTypes` layers are declared but unpopulated — requesting them returns nothing without an error. A silent-failure trap worth measuring deliberately, and a sign the surface is still under development, so record the server version per run. |
| **N2** | Product naming | `harness-lab` names the rig, not the thing a user runs. Only matters when T1 ships. |
| **N3** | Who authors `skill-authored` | Must be written before results exist ([G6](#g6--two-skill-conditions)) — schedules into the rig phase, not the matrix phase. |
| **N4** | Publication intent and venue | Determines how hard pre-registration and the statistical plan must be, and whether an artifact-evaluation-grade release is needed. |
