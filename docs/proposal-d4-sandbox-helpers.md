# Proposal: D4 — sandbox helpers (executable workflow prior)

**Status:** Proposal — not adopted, not scheduled  
**Date:** 2026-08-06  
**Motivated by:** [`results/matrix-10`](../results/matrix-10/) (D2-auth winner; residual misses are execution, not refusal)  
**Companions:** [`running-the-experiment.md`](./running-the-experiment.md) (arm ladder) · [`decisions.md`](./decisions.md) G6 / L13 (skill pre-registration) · [`packaging-method.md`](./packaging-method.md)

This is a design note for a later implementation. It does not change presets, axes, or confirmatory contrasts until adopted into `decisions.md` / `plan.md`.

---

## 1. Problem

matrix-10 ranked **D2-auth** (code sandbox + authored Catalog skill) first:

| Signal | D2-auth |
|---|---|
| Success | 84% |
| Correct refusals | 100% |
| Data clobbers | 0 |
| Peak context (successes) | ~6k tokens (vs ~14k bare MCP) |

On **accuracy alone** it ties D1 (78%) within the run’s MDE (~23 pp). It wins the composite on abstention and harm.

The nineteen D2-auth misses are not packaging ignorance:

- missed archive (irreversible write never applied)
- rating / status patch wrong or skipped
- incomplete fan-out tags
- occasional wrong read extraction

The authored skill already taught hierarchy, `patch` vs `replace`, and refusal. What remains looks like **last-mile procedure** — the kind of thing that belongs in a function, not another paragraph of markdown.

---

## 2. Proposal in one sentence

Add a packaging cell where the sandbox contains not only the generated `api/` modules, but an **agent-authored `helpers/` library** — executable workflow memory — produced from the API definition (and optionally distilled patterns), then measured as its own arm against D1 / D2 / D2-auth.

---

## 3. What changes (and what does not)

### New prior: executable, not instructional

| Arm | Prior in the sandbox | Form |
|---|---|---|
| D1 | None | Generated `api/` only |
| D2 / D2-auth | Prose skill | Markdown in context + `api/` |
| **D4 (proposed)** | **Helper library** | **`helpers/` Python package** + `api/` |
| D4-auth (optional) | Helpers + authored skill | Both |

D3 stays discovery-from-code. D4 is not discovery; it is **precomputed workflow code** sitting beside the raw operations.

### Suggested sandbox layout

```
catalog/                    # sandbox workdir
  api/                      # today: generate.code_module_tree(spec)
    operations.py
    …
  helpers/                  # new: HelperAuthor agent output
    __init__.py
    walk.py                 # studio → series → season with expand / fields
    patch.py                # field updates; never replace/PUT
    fanout.py               # page + per-item write + idempotency_key
    archive.py              # dry_run then narrowest archive_*
    README.md               # short index of helpers (optional; keep thin)
```

The task agent is told: prefer `helpers.*` when a procedure fits; fall back to `api.operations` otherwise. Intermediate results still stay in-process — same mechanism as D1, denser prior.

---

## 4. The HelperAuthor agent

This is the main new component. It is **not** the task-solving agent. It runs **once per materials build** (or once per committed artifact), offline from the matrix loop.

### Inputs (allowed)

1. **OpenAPI / `ApiSpec`** — primary. Operations, schemas, tags, destructive hints.
2. **Optional static policy pack** — the same knowledge the authored skill encodes, as structured rules (e.g. “prefer patch over replace”, “page before superlatives”, “archive scope”), **not** task text or gold answers.
3. **Optional held-out failure taxonomy** — aggregated patterns from a *training* split (e.g. “incomplete fan-out”, “PUT wiped title”), without task ids or expected values.

### Output

A small Python package under `helpers/` that:

- imports only from `api.*` and the stdlib
- exposes a few named procedures with clear signatures
- does **not** hard-code entity ids, titles, or answer values
- refuses to wrap `replace_*` / whole-object PUT as the default write path

### Sketch

```
OpenAPI ──► HelperAuthor (LLM or codegen+LLM) ──► helpers/*.py
                ▲
                │ optional: rule pack / held-out failure patterns
                │
Task agent  ◄── materials: api/ + helpers/ + thin README
```

### Why “from the API definition” is the default path

A pure OpenAPI→helpers codegen answers: *can we turn a spec into useful glue without seeing any eval tasks?* That is the cleanest packaging claim and the closest analogue to `skill-generated`.

A second condition (patterns from held-out runs) answers: *does learning from failures transfer?* That is valuable but must use a **core split** — see §5.

Do not bake matrix-10 task answers into helpers and then re-score matrix-10.

---

## 5. Fairness / contamination

Same spirit as skill-authored pre-registration ([decisions G6](./decisions.md), L13):

| Helper source | Allowed? | What you may claim |
|---|---|---|
| Spec-only / static rules | Yes | Codegen (or agent-from-spec) produces useful glue |
| Human or agent rules distilled without task ids | Yes, if committed before eval | Authored *executable* skill quality |
| Train on held-out cores → helpers → score on unseen cores | Yes | Transfer of learned procedures |
| Helpers that encode specific cores / gold fields | **No** | Memorization |

**Pre-registration:** either commit the `helpers/` tree (or the HelperAuthor prompt + freeze hash) before the eval set, or run HelperAuthor only on a declared training split and never on eval cores.

**Reporting:** never pool D4 (spec-only helpers) with D4-learned (failure-trained helpers). Same refusal-to-pool rule as authored vs generated skills.

---

## 6. Hypotheses (pre-register before implementing)

1. **H1 — Execution lift.** On W-safe / W-lossy / RW-fan, D4 (spec helpers) beats D1 by more than a prose skill alone does on those classes.
2. **H2 — Abstention unchanged.** D4 without an authored skill will not match D2-auth’s 100% correct refusals; refusal remains a prose (or policy) job unless helpers explicitly expose `cannot_determine()`.
3. **H3 — Harm.** Spec-authored helpers that hide `replace_*` reduce clobbers relative to eager-all MCP; a bad helper that re-exports PUT under a soft name can *increase* harm — measure clobber rate as a first-class outcome.
4. **H4 — Composition.** D4 + authored skill ≥ max(D4, D2-auth) on composite score; the interesting gap is whether helpers eat D2-auth’s residual misses.

Minimum detectable effect and confirmatory contrasts should be added to `stats.py` only when this proposal is adopted — do not invent significance after seeing a probe.

---

## 7. Implementation sketch (against current code)

Touch points when building this later:

| Piece | Likely home |
|---|---|
| HelperAuthor | new module, e.g. `engine/helper_author.py` — takes `ApiSpec` (+ optional rule pack), returns `dict[Path, bytes]` |
| Materials | extend `CodeFsMcp.materialize` (or a sibling `CodeFsHelpers` method) to merge `helpers/` into `sandbox_files` |
| Axis / preset | new preset `D4` / `D4-auth`; possibly a small axis value under `instructions` or a dedicated `workflow_prior: none \| prose \| helpers \| both` — prefer an explicit axis over overloading skill enums |
| Protocol text | teach the task agent that `helpers` exists; keep the code-exec protocol (`_CODE_PROTOCOL`) unchanged |
| Lint | static check: helpers must not contain known gold strings / core ids from the task pack |
| Field mode | same HelperAuthor over a customer OpenAPI → shippable “generate workflow library” product wedge |

Out of scope for v1 of this arm: TypeScript helpers, multi-file agent loops that keep rewriting helpers mid-task, retrieval over helper docs.

---

## 8. Suggested contrasts (when adopted)

| Contrast | Question |
|---|---|
| D4 vs D1 | Does an executable helper library help on an identical sandbox? |
| D4 vs D2 | Helpers vs generated prose skill |
| D4 vs D2-auth | Executable prior vs authored instructional prior |
| D4-auth vs D2-auth | Do helpers add anything once refusal prose exists? |
| D4-spec vs D4-learned | Spec codegen vs failure-trained helpers (split required) |

---

## 9. Open questions (resolve before coding)

1. **Axis shape** — new `workflow_prior` axis vs folding into `instructions` / a new PackagingMethod?
2. **HelperAuthor model** — same model as the task agent, or a stronger offline author? (Cost vs quality; contamination of “the harness’s best model wrote the tools.”)
3. **How much README** — thin index only, or allow progressive helper docs (risk: recreating the skill inside the sandbox)?
4. **Refusal API** — should helpers include an explicit abstain helper, or leave refusal to prose?
5. **Product surface** — is HelperAuthor a controlled-experiment arm only, or also a field-mode “generate tools from OpenAPI” command?

---

## 10. Adoption checklist

When ready to implement:

- [ ] Decide axis + preset names; append a decision in `decisions.md`
- [ ] Spec HelperAuthor I/O contract and contamination lint
- [ ] Implement materials merge on `code-fs`
- [ ] Pre-register contrasts in `stats.py`
- [ ] Probe on a small core split before a full matrix
- [ ] Update `running-the-experiment.md` arm table

Until then, this file is the only place this option is specified.
