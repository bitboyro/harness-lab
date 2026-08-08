# Packaging Method — axes, plugin interface, presets

**Status:** Contract — frozen at P0
**Decisions:** [G1](./decisions.md#g1--orthogonal-variant-axes-with-code-execution), [F3](./decisions.md#f3--support-both-mcp-spec-revisions), [F4](./decisions.md#f4--code-fs-sandbox-is-python), [G4](./decisions.md#g4--response-and-error-design-as-manipulated-variables), [G5](./decisions.md#g5--drop-v2-equal-documentation-token-budget), [G6](./decisions.md#g6--two-skill-conditions)

A **packaging method** is one way of presenting an API to an agent. This document defines the axes that describe one, the plugin interface that implements one, and the named presets.

**The engine enumerates; the run plan selects.** The axis space is large (thousands of cells) and that is intentional — validity comes from *which cells are compared*, not from restricting what the tool can express.

---

## Axes

Every axis is orthogonal: it describes one property, and no axis implies another. A variant is a complete assignment. Nothing is defaulted implicitly — a variant with an unset axis is a config error, not a variant.

### Structural axes

| Axis | Values | Meaning |
|---|---|---|
| `transport` | `mcp` \| `http-rest` \| `in-process` \| `none` | How a call physically happens |
| `mcp_revision` | `2026-07-28` \| `legacy` | Which MCP spec revision. Required iff `transport: mcp`; a config error otherwise. See [F3](./decisions.md#f3--support-both-mcp-spec-revisions) |
| `discovery` | `eager-all` \| `meta-tools` \| `code-fs` \| `retrieval` \| `docs` \| `none` | How the agent learns what operations exist |
| `invocation` | `tool-call` \| `shell` \| `code` \| `none` | How the agent expresses a call |
| `instructions` | `none` \| `skill-generated-flat` \| `skill-generated-progressive` \| `skill-authored-flat` \| `skill-authored-progressive` \| `docs-flat` \| `docs-progressive` | What prose enters context, and whether it is mechanically generated or human-authored |
| `confirmation` | `none` \| `mrtr` | Whether the server demands confirmation before destructive ops, via MRTR (`resultType: "input_required"`). Requires `mcp_revision: 2026-07-28` |

**`discovery` values:**

- `eager-all` — every operation schema in context before turn 1.
- `meta-tools` — a `search` / `describe` / `invoke` triad; schemas fetched on demand. Hand-rolled by default for cross-provider symmetry ([O2](./decisions.md#planmd-open-questions)); a `native` sub-mode exists as a separately *labelled* variant where the provider offers one.
- `code-fs` — operations presented as an importable module tree the agent reads on demand. Pairs with `invocation: code`.
- `retrieval` — top-k tool retrieval over an index. Reported with Recall@k / nDCG@k.
- `docs` — a written API reference, flat or progressive per `instructions`.
- `none` — control arms only.

**`invocation` values — note the three-way split.** `plan-review.md` wrote the C arms as "code (bash)", which conflates two genuinely different things:

- `tool-call` — the provider's native function-calling channel.
- `shell` — a bash sandbox; the agent runs `curl`. Freehand HTTP against a written reference. *This is the C arms.*
- `code` — the agent writes program code against a generated module tree; intermediate results stay in the sandbox and never enter context. Python per [F4](./decisions.md#f4--code-fs-sandbox-is-python). *This is the D arms.*

Keeping them apart matters because the mechanism under test differs: `shell` tests whether an agent can read docs and construct requests; `code` tests whether keeping intermediates out of context pays for itself.

### Affordance axes

These describe the API's own design, and they are **manipulated, not fixed** — this is [G4](./decisions.md#g4--response-and-error-design-as-manipulated-variables), the strongest unclaimed result available.

| Axis | Values | Meaning |
|---|---|---|
| `schema_detail` | `minimal` \| `standard` \| `rich` | `rich` adds examples and an error taxonomy to each operation |
| `response_shape` | `as-is` \| `sparse` \| `budgeted` | Whether responses are shaped/capped before reaching the agent |
| `error_detail` | `terse` \| `field-scoped` \| `field-scoped+remedy` | `terse` = `422: validation failed`. `field-scoped+remedy` = `422: field 'created_after' expects RFC3339, received '2024-13-01'` |
| `doc_budget` | `terse` \| `standard` \| `verbose` | Length of generated prose. Swept, **not equalized** — see [G5](./decisions.md#g5--drop-v2-equal-documentation-token-budget) |

### Run axes

| Axis | Values | Notes |
|---|---|---|
| `surface_size` | int | Exposed operation count (5 / 15 / 50 / 200 / custom) |
| `model` | provider model id | Fixed within a controlled comparison; a field-mode axis ([G7](./decisions.md#g7--model-tier-is-a-field-mode-axis)) |
| `reasoning_effort` | explicit | Never defaulted — V3. An unset default silently benchmarks effort levels instead of packaging |
| `temperature` | float | Fixed and logged |
| `caching` | `on` \| `off` \| `list-cacheable` | Third value covers protocol-level `ttlMs`/`cacheScope` on `tools/list`, which is a different cache from prompt caching |
| `repeats` | int | Measures sampling noise only. Variance over task instances needs more cores, not more repeats ([G8](./decisions.md#g8--statistical-plan-written-with-the-rig)) |

---

## Presets

Named points in the space. Presets are a convenience for run plans and papers; the axis assignment is the primitive.

Every preset below is a **complete** assignment — no axis is left implicit. Affordance and run axes are omitted from the table only because they are held at their comparison-wide values (`schema_detail: standard`, `response_shape: as-is`, `error_detail: field-scoped`, `doc_budget: standard`) unless a sweep varies them.

| Preset | `transport` | `mcp_revision` | `discovery` | `invocation` | `instructions` | `confirmation` |
|---|---|---|---|---|---|---|
| **A1** | `mcp` | per run | `eager-all` | `tool-call` | `none` | `none` |
| **A2** | `mcp` | per run | `meta-tools` | `tool-call` | `none` | `none` |
| **B1** | `mcp` | per run | `eager-all` | `tool-call` | `skill-generated-flat` | `none` |
| **B2** | `mcp` | per run | `meta-tools` | `tool-call` | `skill-generated-flat` | `none` |
| **C1** | `http-rest` | n/a | `docs` | `shell` | `docs-flat` | `none` |
| **C2** | `http-rest` | n/a | `docs` | `shell` | `docs-progressive` | `none` |
| **D1** | `mcp` | per run | `code-fs` | `code` | `none` | `none` |
| **D2** | `mcp` | per run | `code-fs` | `code` | `skill-generated-progressive` | `none` |
| **D3** | `mcp` | per run | `meta-tools` | `code` | `skill-generated-flat` | `none` |
| **E1** | `mcp` | per run | `retrieval` | `tool-call` | `none` | `none` |
| **M1** | `mcp` | `2026-07-28` | `eager-all` | `tool-call` | `none` | `mrtr` |
| **Z0** | `none` | n/a | `none` | `none` | `none` | `none` |
| **Z1** | `in-process` | n/a | `none` | `none` | `none` | `none` |

**Preset notes:**

- **B-arms have an authored twin.** `B1-auth` / `B2-auth` / `D2-auth` swap `skill-generated-*` for `skill-authored-*`. Reported separately, never pooled ([G6](./decisions.md#g6--two-skill-conditions)).
- **M1** probes whether a server that *asks before archiving* beats a typed tool surface at harm reduction, and what that costs in latency and turns. Directly on RQ3, and now the protocol-sanctioned way to do it.
- **Z0** — no tool access, parametric answer only. Must score ≈0 in controlled mode (hard gate). In field mode it is not a gate but a **measurement**: how much the model already knows about the target API ([G9](./decisions.md#g9--z0z1-in-field-mode-as-a-parametric-baseline)).
- **Z1** — gold call sequence pre-executed in-process; the model only synthesizes. Establishes the achievable ceiling per task. Requires `gold_call_sequence` in the task pack.

---

## Plugin interface

**Adding a packaging method is a new plugin file. It is never a change to the engine.** This is the seam that keeps the harness from aging out when the protocol moves again — and it moved on 2026-07-28, which is the proof that it will.

```python
class PackagingMethod(Protocol):
    def materialize(self, spec: ApiSpec, config: VariantConfig) -> Materials:
        """Everything that exists before turn 1."""

    def executor(self, materials: Materials) -> Executor:
        """How a call is physically made."""

    def account(self, trace: Trace) -> CostBreakdown:
        """What this method cost, decomposed."""
```

### `Materials`

```python
@dataclass
class Materials:
    context_blocks: list[ContextBlock]   # enters the prompt before turn 1
    tool_defs: list[ToolDef]             # native function-calling surface, may be empty
    sandbox_files: dict[Path, bytes]     # module tree / docs written into the sandbox
    static_tokens: int                   # measured, never equalized (G5)
    provenance: Provenance               # which generator + spec revision produced this
```

`provenance` exists so V1 (mechanical generation from one spec) is auditable after the fact rather than asserted. For `skill-authored-*` it records the authoring commit — which is the pre-registration ([G6](./decisions.md#g6--two-skill-conditions)).

### `Executor`

```python
class Executor(Protocol):
    def invoke(self, call: Call) -> Result: ...
    def teardown(self) -> None: ...
```

Implementations: `McpToolCallExecutor` (both revisions), `ShellExecutor` (bash + curl subprocess), `CodeExecutor` (Python sandbox subprocess), `PreExecutedExecutor` (Z1), `NullExecutor` (Z0).

Sandbox isolation follows [D3](./decisions.md#experiment-designmd-open-questions): subprocess per run for controlled phases, container per run for field mode against real targets.

<a id="cost-breakdown"></a>
### `CostBreakdown`

The cost model must decompose, not total — the whole point of [F3](./decisions.md#f3--support-both-mcp-spec-revisions) is that different methods pay in different places.

```python
@dataclass
class CostBreakdown:
    static_tokens: int             # tool defs + instructions before turn 1
    per_call_overhead_tokens: int  # _meta tax (2026-07-28) — scales with call count
    session_setup_tokens: int      # handshake (legacy) — paid once
    payload_tokens: int            # tool results that entered context
    sandbox_seconds: float         # wall clock inside the sandbox
    round_trips: int               # includes MRTR retries and task polls
```

**Why this decomposition and not a single number.** Stateless MCP moves cost from `session_setup_tokens` to `per_call_overhead_tokens`, which scales with call count. That penalizes chatty arms (A1) and favours arms that batch inside a sandbox (D1/D2). A totalled cost hides the mechanism; a decomposed one makes "migrating to stateless costs chatty arms X% more" fall straight out.

`round_trips` counts MRTR retries and Tasks-extension polls, because both are round trips that cost tokens and neither existed in the original cost model.

---

## Metric validation

Every metric carries a validation flag, printed in every report footer ([F1](./decisions.md#f1--tool-first-study-second)):

| Flag | Meaning |
|---|---|
| `validated-controlled` | Correlates with ground truth on the controlled rig; safe for field claims |
| `unvalidated` | Computed and reported, but its relationship to ground truth is unestablished |
| `heuristic` | Derived from judgement, not measurement; never a research claim |

Field reports ship before the rig exists, so they ship with `unvalidated` metrics. That is acceptable **because it is stated on the artifact**, not because it is unnoticed. Flags flip per metric as the rig validates them.

---

## Matrix selection

A run is a *declared subset* with a stated rationale — never the full cross product.

```yaml
run_plan:
  id: phase1-main
  rationale: >
    RQ1 (skill contribution) and RQ2 (topology × surface size), single
    provider, single surface size, affordances held constant.
  base:
    model: <id>
    reasoning_effort: medium
    temperature: 0
    surface_size: 15
    schema_detail: standard
    response_shape: as-is
    error_detail: field-scoped
    doc_budget: standard
    mcp_revision: 2026-07-28
    caching: [on, off]
    repeats: 3
  include:
    presets: [A1, A2, B1, B2, B1-auth, B2-auth, C1, C2, D1, D2, Z0, Z1]
  exclude:
    - { preset: Z1, task_class: [W-irrev] }   # ceiling is trivially 1.0 here
  confirmatory:                                # pre-registered, corrected
    - { contrast: [A1, B1], hypothesis: P4 }
    - { contrast: [A2, B2], hypothesis: P4 }
  exploratory:                                 # labelled, uncorrected
    - { contrast: [D1, D2] }
```

Required behaviour of the planner:

1. **`rationale` is mandatory.** A matrix with no stated reason is a config error.
2. **Print projected cost and require confirmation before executing** ([F2](./decisions.md#f2--no-fixed-budget-cap-gate-per-phase)). The estimate models `reasoning_effort` explicitly — it is the dominant variance source.
3. **Refuse to pool across `mcp_revision`** at the report layer ([F3](./decisions.md#f3--support-both-mcp-spec-revisions)).
4. **Refuse to pool `skill-generated-*` with `skill-authored-*`** ([G6](./decisions.md#g6--two-skill-conditions)).
5. **Require the confirmatory/exploratory split** before any run that will be published ([G8](./decisions.md#g8--statistical-plan-written-with-the-rig)).

---

## Designed for, not yet built

Each is a plugin, not an engine change. Listed so the interface is checked against them now rather than bent around them later.

| Method | Why it matters |
|---|---|
| **TS `code-fs` executor** | Runtime-comparability check against the literature, which uses TypeScript ([F4](./decisions.md#f4--code-fs-sandbox-is-python)). Stable ranking across runtimes is a finding; unstable is a bigger one |
| **Tasks extension** (`tasks/get` / `tasks/update`) | Async/long-running jobs, now protocol-standardized. Poll-vs-callback is a packaging choice with real token cost — every poll is a round trip — and nobody has measured it |
| **`llms.txt` / `AGENTS.md` descriptors** | An `instructions` value; near-free once the seam exists |
| **Native provider tool-search** | Sub-mode of `discovery: retrieval` / `meta-tools`, separately labelled ([O2](./decisions.md#planmd-open-questions)) |

**Not planned, and explicitly out of scope:** MCP Apps / UI resources (no human in the loop) and multi-agent delegation. Both will otherwise get asked about.
