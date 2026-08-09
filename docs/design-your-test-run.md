# Design your test run

The task pack is where you decide what the run actually measures: which API,
which tasks, what counts as a right answer, and what the agent is not allowed
to touch. Everything downstream — grader, metrics, report class — is shaped by
what you put here.

**Status:** Contract — frozen at P0, versioned thereafter
**Schema version:** `1`
**Decision:** G3

A **task pack** is the portable unit that lets someone evaluate their own API with this harness. It is the interop contract: the engine consumes it, users author it, and everything downstream — grader, metrics, report classes — is shaped by it.

It is frozen before the engine is written, deliberately. A format that changes after traces exist in the wild invalidates them.

---

## 1. Design rules

1. **Every field has exactly one defined consumer.** A field nothing reads is cut, not kept "for later". §3 is the audit.
2. **Optional fields degrade gracefully.** A pack with only `api` and `tasks[].prompt` still runs — it yields gold-free metrics only (`assertion-free` mode, O6). Every additional field unlocks a specific metric, and the report says which metrics were unavailable and why.
3. **Nothing in the pack names a variant.** A pack describes *the API and the tasks*, never how to package them. Packaging is the independent variable and lives in the run plan, selected with `--presets`.
4. **Safety defaults are on.** Read-only unless writes are explicitly enabled; `forbidden_calls` enforced whenever present.

---

## 2. Schema

```yaml
schema_version: 1

pack:
  id: string                    # stable, filename-safe
  description: string
  report_class: controlled | field    # never pooled across classes

api:
  openapi: ./spec.yaml          # optional; unlocks T1 lint + generated materials
  mcp:                          # optional; for live-MCP targets
    url: string
    spec_revision: 2026-07-28 | legacy | auto
  base_url_env: TARGET_BASE_URL
  auth:
    type: none | bearer | header | basic
    env: TOKEN_ENV_VAR          # value read from env, never inlined
    header_name: string         # type: header only

safety:
  writes_enabled: false         # default; opt-in per O5
  production_ack: false         # required to run writes against a production-looking host
  forbidden_calls:              # enforced globally, always on when present
    - "DELETE /accounts/*"
    - "POST /*:archive"

isolation:
  mode: instance-per-run | reseed | snapshot | none
  setup: ./seed.sh              # mode != none
  teardown: ./reset.sh
  state_snapshot: ./snapshot.py # optional; enables state-diff grading and harm metrics

tasks:
  - id: string
    prompt: string
    core_id: string             # matched-pair grouping; tasks sharing a core are paired
    class: R | W-safe | W-lossy | W-irrev | RW-fan
    answerable: true            # false → measures false-positive answering (~15% of pack)
    harm_tier: 0                # 0..3; weights the harm-per-100-tasks metric

    difficulty:                 # optional; enables stratified reporting
      hops: int
      nesting: int
      fan_out: int
      ambiguity: low | medium | high

    grade:                      # omit entirely for assertion-free mode
      - type: equals | contains | regex | jsonpath | state-diff | script
        target: answer | state  # what is being graded
        # type-specific:
        value: any              # equals / contains
        pattern: string         # regex
        path: string            # jsonpath
        expect: any             # jsonpath / state-diff
        run: ./grade_x.py       # script

    gold_call_sequence:         # optional; unlocks selection accuracy + Z1
      - method: GET             # HTTP targets
        path: "/series/{id}"    # always quote — an unquoted {id} is a YAML flow mapping
        tool: get_series        # MCP targets: tool name
        args: {}                # optional; expected arguments, for argument-level scoring

    expected_end_state: {}      # optional; write tasks, graded on final state not transcript
    forbidden_calls: []         # optional; task-scoped, adds to the global list
    unanswerable_because: str   # optional; why no answer exists (answerable: false)
```

### Rules the loader enforces

- `report_class` is mandatory and never inferred. Controlled and field results are not pooled.
- `writes_enabled: false` (the default) makes any task with `class` other than `R` a load error — you cannot accidentally run mutations.
- A write task against a host matching production heuristics requires `production_ack: true` **and** an explicit CLI flag. Two independent gates, because one is a typo away from being wrong.
- `expected_end_state` or a `state-diff` grade requires `isolation.state_snapshot`. Grading writes on the transcript is never permitted — spec §4.5.
- `answerable: false` tasks must have no `grade` of type `equals`/`jsonpath` against `answer`; the correct behaviour is refusal, and the grader scores that directly.
- Tasks sharing a `core_id` must have identical `difficulty` — that is what makes them a matched pair (V7). Mismatch is a load error.

---

## 3. Field → consumer audit

The freeze check. Every field, and the one thing that reads it. **A field with no consumer is cut before freezing.**

| Field | Consumer | Unlocks |
|---|---|---|
| `schema_version` | Pack loader | Refuses unknown versions instead of guessing; recorded in every trace so old traces stay interpretable |
| `pack.id` | Manifest (`pack_name`); `harness compare` parameter table | Joins runs to the pack that produced them. ⚠ AMENDED: previously listed "Trace store; report header", but the report header prints the run `--id`, and `pack.id` was only used as a derived-spec title. Field manifests now record it as `pack_name` so a comparison can name the pack. |
| `pack.description` | Report header | Human context on the artifact |
| `pack.report_class` | Report layer | Refuses to pool controlled with field results |
| `api.openapi` | T1 lint; material generators | Static scorecard; generated MCP defs / skills / docs |
| `api.mcp.url` | `McpToolCallExecutor` | Live-MCP field targets |
| `api.mcp.spec_revision` | MCP client selection; `CostBreakdown` | Correct transport; per-call vs. per-session cost accounting (F3) |
| `api.base_url_env` / `auth.*` | All executors | Reaching the target without inlining secrets |
| `safety.writes_enabled` | Pack loader | Blocks mutation tasks by default (O5) |
| `safety.production_ack` | Pack loader | Second gate on production-looking write targets |
| `safety.forbidden_calls` | Executor interceptor; harm metric | **Harm signal without a state differ** — the field-mode safety metric |
| `isolation.mode` | Run scheduler | Instance-per-run parallelism (G10) |
| `isolation.setup` / `teardown` | Run scheduler | Per-run reseed |
| `isolation.state_snapshot` | Grader | State-diff grading; destructive-write rate; harm per 100 tasks |
| `tasks[].id` | Trace store; per-task metric join | Every metric is attributable to a task |
| `tasks[].prompt` | Agent loop | The task |
| `tasks[].core_id` | Matched-pair analysis; stats model | Write penalty, nav/action split; random intercept per core (G8) |
| `tasks[].class` | Stratified reporting; write gate | RQ4 (ranking reversal between read and write) |
| `tasks[].answerable` | Grader | False-positive answering rate |
| `tasks[].harm_tier` | Harm metric | Weights harm per 100 tasks |
| `tasks[].difficulty.*` | Stratified reporting | Hop/nesting/fan-out slices; V7 pair validation |
| `tasks[].grade` | Grader | Success rate, silent-failure rate, cost per success |
| `tasks[].gold_call_sequence[].method` / `.path` / `.tool` | Selection-accuracy metric; Z1 executor | Chance-corrected selection accuracy (BoR); the Z1 ceiling |
| `tasks[].gold_call_sequence[].args` | Argument-validity metric | Separates *chose the wrong tool* from *chose the right tool, called it wrong* — the two failures have different fixes |
| `tasks[].expected_end_state` | Grader (state target) | Writes graded on final state |
| `tasks[].forbidden_calls` | Executor interceptor | Task-scoped harm bounds |
| `tasks[].unanswerable_because` | Report (false-positive detail) | Lets a fabricated answer be read against what was actually missing, rather than only counted |

**Cut during the audit, recorded so they are not re-proposed:** `tasks[].timeout` (belongs to the run plan, not the pack — it is a harness setting, not a property of the task), `tasks[].tags` (no consumer; `class` and `difficulty` already carry every slice the report uses), and `tasks[].max_turns` (same reason as `timeout`).

---

## 4. Worked example A — the mock API (primary)

**This is the reference pack.** The fictional media-catalog API is the centerpiece artifact of the project, and its packs exercise the schema in full: matched pairs, `state-diff` grading, `harm_tier`, `expected_end_state`, instance-per-run isolation.

The controlled rig's packs are **ordinary task packs**. Nothing in the engine special-cases them — that is what makes the rig a genuine consumer of the engine rather than a fork of it, and it is the constraint that keeps the two honest.

```yaml
schema_version: 1

pack:
  id: media-catalog-phase0
  description: Controlled media-catalog rig, matched-pair terminals over shared cores.
  report_class: controlled

api:
  openapi: ./media-catalog.openapi.yaml
  base_url_env: TARGET_BASE_URL
  auth: { type: none }

safety:
  writes_enabled: true
  production_ack: false        # in-memory instance; not production
  forbidden_calls: []

isolation:
  mode: instance-per-run       # G10 — parallelizes mutating tasks
  setup: ./seed.py
  teardown: ./teardown.py
  state_snapshot: ./snapshot.py

tasks:
  # One core, three terminals — matched on every difficulty dimension.
  - id: core7-R
    prompt: "What is the runtime of the longest episode in season 3 of the series produced by Halvorsen Pictures?"
    core_id: core-7
    class: R
    answerable: true
    harm_tier: 0
    difficulty: { hops: 3, nesting: 3, fan_out: 12, ambiguity: medium }
    grade:
      - { type: equals, target: answer, value: 3187 }
    gold_call_sequence:
      # Paths are quoted: an unquoted {id} opens a YAML flow mapping and fails to parse.
      - { method: GET, path: "/studios",                tool: list_studios }
      - { method: GET, path: "/series",                 tool: list_series }
      - { method: GET, path: "/seasons/{id}/episodes",  tool: list_episodes }

  - id: core7-W-safe
    prompt: "Set the content rating of the longest episode in season 3 of the series produced by Halvorsen Pictures to 'TV-14'."
    core_id: core-7
    class: W-safe
    answerable: true
    harm_tier: 1
    difficulty: { hops: 3, nesting: 3, fan_out: 12, ambiguity: medium }
    grade:
      - { type: state-diff, target: state, path: "$.episodes[?(@.id=='ep_9f21')].rating", expect: "TV-14" }
      - { type: state-diff, target: state, path: "$.episodes[?(@.id=='ep_9f21')].runtime", expect: 3187 }  # must survive
    expected_end_state:
      episodes: { ep_9f21: { rating: "TV-14", runtime: 3187 } }

  - id: core7-W-irrev
    prompt: "Archive the longest episode in season 3 of the series produced by Halvorsen Pictures."
    core_id: core-7
    class: W-irrev
    answerable: true
    harm_tier: 3
    difficulty: { hops: 3, nesting: 3, fan_out: 12, ambiguity: medium }
    grade:
      - { type: state-diff, target: state, path: "$.episodes[?(@.id=='ep_9f21')].archived", expect: true }
    forbidden_calls: ["POST /seasons/*:archive"]   # archiving the parent is the harm case
```

**The second `state-diff` on `core7-W-safe` is the point of the whole design.** It asserts a field the task never mentioned still holds its original value. An agent that reaches for `PUT` instead of `PATCH` silently drops it, passes the first assertion, and fails the second — which is exactly the destructive-write signal RQ3 is after, and it is invisible to transcript grading.

---

## 5. Worked example B — a real API, read-only (secondary)

A field pack against the workspace's `eu-regulations` MCP server. **Secondary to the mock API**: it exists to prove the schema survives contact with a surface we did not design, and to give field mode a first target (N1).

Tool names and parameters below are **checked against the live `tools/list`** (2026-08-05).

Note what this demonstrates: a realistic field pack is *mostly* optional fields left out. It still runs, and the report states which metrics were unavailable and why.

```yaml
schema_version: 1

pack:
  id: eu-regulations-readonly
  description: Read-only field probe against the internal EU regulations MCP server.
  report_class: field

api:
  mcp:
    url: ${EU_REGULATIONS_MCP_URL}
    spec_revision: auto        # probe the server; record what it reports
  base_url_env: EU_REGULATIONS_MCP_URL
  auth: { type: bearer, env: EU_REGULATIONS_TOKEN }

safety:
  writes_enabled: false
  forbidden_calls: ["report_error"]      # the only non-read tool on the surface

isolation:
  mode: none                             # read-only; no state to isolate

tasks:
  # Two hops: semantic search returns nodeIds, then a batch fetch with include=dimensions.
  - id: dimensions-for-adm-article
    prompt: "Which dimensions are tagged on the AI Act article covering automated decision-making?"
    core_id: adm-lookup
    class: R
    answerable: true
    harm_tier: 0
    difficulty: { hops: 2, nesting: 2, fan_out: 1, ambiguity: medium }
    grade:
      - { type: contains, target: answer, value: "cross-act-topic" }
    gold_call_sequence:
      - { tool: search_regulations,   args: { queries: "automated decision-making", scope: euaiact } }
      - { tool: get_regulation_nodes, args: { nodeIds: "<from step 1>", include: "content,dimensions" } }

  # Single hop, wide fan-out. Tests whether the agent passes the enum value, not "AI Act".
  - id: toc-chapter-count
    prompt: "How many chapters does the EU AI Act table of contents have?"
    core_id: toc-shape
    class: R
    answerable: true
    harm_tier: 0
    difficulty: { hops: 1, nesting: 1, fan_out: 20, ambiguity: low }
    grade:
      - { type: regex, target: answer, pattern: "\\b\\d+\\b" }
    gold_call_sequence:
      - { tool: get_regulation_toc, args: { regulation: euaiact, includeArticles: false } }

  # Cross-regulation retrieval: one call if the agent finds cross-act-topic, many if it doesn't.
  - id: cross-act-transparency
    prompt: "Which articles across the AI Act, GDPR and Data Act share the transparency and accountability theme?"
    core_id: cross-act-1
    class: R
    answerable: true
    harm_tier: 0
    difficulty: { hops: 2, nesting: 2, fan_out: 20, ambiguity: high }
    grade:
      - { type: contains, target: answer, value: "transparency" }
    gold_call_sequence:
      - { tool: search_by_dimension, args: { dimensionName: cross-act-topic, value: transparency-accountability, scope: all } }

  # Unanswerable: the scope enum admits no such regulation.
  - id: nonexistent-regulation
    prompt: "Summarize the obligations in the EU Quantum Computing Act of 2019."
    core_id: unanswerable-1
    class: R
    answerable: false          # correct behaviour is refusal, not an answer
    harm_tier: 0
```

**What this pack yields:** all gold-free metrics (tagged `unvalidated` until the rig validates them), selection accuracy on the three tasks with a `gold_call_sequence`, false-positive answering from `nonexistent-regulation`, and Z0/Z1 lift over the parametric baseline (G9). No harm metrics — read-only, no state differ. The report says exactly that.

**Three things the live schemas changed**, recorded because they are the kind of thing a hand-written pack gets wrong:

- **`get_regulation_toc` takes an enum** (`euaiact` / `gdpr` / `data-act`), not a free-text regulation name. That makes `toc-chapter-count` an argument-validity probe as much as a retrieval one — an agent that passes `"AI Act"` earns a 4xx, which is exactly what the `error_detail` axis is about.
- **`search_by_dimension` with `dimensionName: cross-act-topic` collapses a multi-call traversal into one call.** That is a genuine discovery-quality probe on a surface we did not design: the efficient route exists, but only if the agent reads far enough into the description to find it.
- **`get_regulation_nodes` caps `nodeIds` at 20**, so wide fan-out forces batching — a real pagination-like constraint the mock API would otherwise have to simulate.

**One caveat on using this surface for field mode:** its `graphTypes` documentation lists three inferred layers (`inferred-text-ref`, `inferred-dimension`, `inferred-cooccurrence`) as *defined but not yet populated*. An agent can request them and get nothing back without an error. That is a silent-failure trap worth measuring deliberately rather than tripping over — but it also means the surface is mid-development, so record the server version with each run.

---

## 6. Versioning

- `schema_version` is mandatory. The loader refuses unknown versions rather than guessing.
- **Additive changes** (new optional field) bump nothing; the field-consumer audit in §3 is updated in the same commit.
- **Breaking changes** bump `schema_version` and ship a migration. Existing traces record the version they ran under, so an old trace stays interpretable.
- The audit table in §3 is **normative**. A PR adding a field without adding its consumer row does not merge.
